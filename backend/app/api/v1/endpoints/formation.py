"""API Formation & Sensibilisation (Conformité).

Login 2 module ``formation`` (dépendance posée au montage du router) ; permissions
``formation.*`` vérifiées par route, puis par le service pour les actions sensibles.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import auth_http_error, get_current_user
from app.db.session import get_db
from app.models import FormationEmploye, User
from app.schemas.formation import (
    ActivationIn,
    EmployeIn,
    EntiteIn,
    ImportConfirmIn,
    ParticipantsIn,
    PresencesIn,
    ReferentielCreate,
    ReferentielFusion,
    ReferentielPatch,
    RetraitIn,
    SessionCreate,
    SessionPatch,
    StatutIn,
    SuppressionIn,
)
from app.services import formation_documents, formation_export
from app.services.formation_import import FormationImportService
from app.services.formation_reporting import Filtres, FormationReporting
from app.services.formation_service import (
    DOMAINE_LIBELLES,
    STATUT_LIBELLES,
    Ctx,
    FormationService,
    Refs,
    nom_complet,
)
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

router = APIRouter(prefix="/formation", tags=["Formation & Sensibilisation"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CAPACITES = {
    "voir": ("formation.view",),
    "creer": ("formation.create",),
    "modifier": ("formation.update",),
    "annuler": ("formation.cancel",),
    "cloturer": ("formation.close",),
    "employes_voir": ("formation.employees.view",),
    "employes_gerer": ("formation.employees.manage",),
    "presences_voir": ("formation.attendance.view",),
    "presences_gerer": ("formation.attendance.manage",),
    "referentiels_voir": ("formation.references.view",),
    "referentiels_gerer": ("formation.references.manage",),
    "imports_voir": ("formation.import.view", "formation.import.execute"),
    "imports_executer": ("formation.import.execute",),
    "reporting_voir": ("formation.reporting.view",),
    "reporting_exporter": ("formation.reporting.export",),
    "admin": ("formation.admin",),
}


def ctx(*codes: str):
    async def dependance(request: Request, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)) -> Ctx:
        perms = set(await load_user_permission_codes(db, user))
        if codes and not (user.is_superuser or user_has_permission_codes(perms, *codes)):
            raise auth_http_error(status.HTTP_403_FORBIDDEN, "PERMISSION_DENIED", "Permission refusée",
                                  required=list(codes))
        return Ctx(user=user, permissions=perms, ip_address=request.client.host if request.client else None,
                   session_id=getattr(request.state, "bea_session_id", None))

    return dependance


def _fichier(contenu: bytes, nom: str, media: str) -> Response:
    return Response(content=contenu, media_type=media, headers={
        "Content-Disposition": f"attachment; filename=\"{nom}\"; filename*=UTF-8''{quote(nom)}",
        "Cache-Control": "no-store",
    })


LECTURE = ("formation.view", "formation.reporting.view", "formation.employees.view", "formation.references.view")


# ------------------------------------------------------------------ configuration
@router.get("/config")
async def config(c: Ctx = Depends(ctx(*LECTURE)), db: AsyncSession = Depends(get_db)) -> dict:
    svc = FormationService(db, c)
    refs = await svc.lister_referentiels()
    par_domaine: dict[str, list] = {d: [] for d in DOMAINE_LIBELLES}
    for r in refs:
        par_domaine[r["domaine"]].append(r)
    return {
        "capacites": {k: c.peut(*v) for k, v in CAPACITES.items()},
        "referentiels": par_domaine,
        "entites": await svc.lister_entites(),
        "statuts": [{"code": k, "libelle": v} for k, v in STATUT_LIBELLES.items()],
        "domaines": [{"code": k, "libelle": v} for k, v in DOMAINE_LIBELLES.items()],
        "aujourdhui": date.today().isoformat(),
        "utilisateur": c.user.full_name,
    }


@router.get("/recherche")
async def recherche(q: str = Query(min_length=2, max_length=100), c: Ctx = Depends(ctx(*LECTURE)),
                    db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).rechercher(q)


@router.get("/tableau-de-bord")
async def tableau_de_bord(annee: int | None = Query(None, ge=1990, le=2100),
                          c: Ctx = Depends(ctx("formation.view", "formation.reporting.view")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationReporting(db).tableau_de_bord(annee)


# ------------------------------------------------------------------ référentiels
@router.get("/referentiels")
async def referentiels(domaine: str | None = None, c: Ctx = Depends(ctx(*LECTURE)),
                       db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await FormationService(db, c).lister_referentiels(domaine)


@router.post("/referentiels", status_code=201)
async def creer_referentiel(body: ReferentielCreate, c: Ctx = Depends(ctx("formation.references.manage")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).creer_referentiel(body.domaine, body.libelle, body.description)


@router.post("/referentiels/fusion")
async def fusionner(body: ReferentielFusion, c: Ctx = Depends(ctx("formation.references.manage")),
                    db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).fusionner_referentiel(body.source_id, body.cible_id)


@router.patch("/referentiels/{rid}")
async def modifier_referentiel(rid: uuid.UUID, body: ReferentielPatch,
                               c: Ctx = Depends(ctx("formation.references.manage")),
                               db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).modifier_referentiel(rid, body.model_dump(exclude_unset=True))


@router.delete("/referentiels/{rid}", status_code=204)
async def supprimer_referentiel(rid: uuid.UUID, c: Ctx = Depends(ctx("formation.references.manage")),
                                db: AsyncSession = Depends(get_db)) -> Response:
    await FormationService(db, c).supprimer_referentiel(rid)
    return Response(status_code=204)


@router.get("/entites")
async def entites(c: Ctx = Depends(ctx(*LECTURE)), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await FormationService(db, c).lister_entites()


@router.post("/entites", status_code=201)
async def creer_entite(body: EntiteIn, c: Ctx = Depends(ctx("formation.references.manage")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).creer_entite(body.model_dump(exclude_unset=True))


@router.patch("/entites/{eid}")
async def modifier_entite(eid: uuid.UUID, body: EntiteIn, c: Ctx = Depends(ctx("formation.references.manage")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).modifier_entite(eid, body.model_dump(exclude_unset=True))


@router.delete("/entites/{eid}", status_code=204)
async def supprimer_entite(eid: uuid.UUID, c: Ctx = Depends(ctx("formation.references.manage")),
                           db: AsyncSession = Depends(get_db)) -> Response:
    await FormationService(db, c).supprimer_entite(eid)
    return Response(status_code=204)


# ---------------------------------------------------------------------- employés
EMPLOYES_LECTURE = ("formation.employees.view", "formation.create", "formation.update")


@router.get("/employes")
async def employes(
    q: str | None = None, entite_id: uuid.UUID | None = None, perimetre_id: uuid.UUID | None = None,
    fonction_id: uuid.UUID | None = None, actif: Literal["oui", "non", "tous"] = "oui",
    forme: Literal["oui", "non"] | None = None, tri: str = "nom", sens: Literal["asc", "desc"] = "asc",
    page: int = Query(1, ge=1), taille: int = Query(25, ge=1, le=500),
    c: Ctx = Depends(ctx(*EMPLOYES_LECTURE)), db: AsyncSession = Depends(get_db),
) -> dict:
    return await FormationService(db, c).lister_employes(
        q=q, entite_id=entite_id, perimetre_id=perimetre_id, fonction_id=fonction_id,
        actif={"oui": True, "non": False, "tous": None}[actif],
        forme=None if forme is None else forme == "oui", tri=tri, sens=sens, page=page, taille=taille)


@router.get("/employes/doublons")
async def doublons(nom: str = Query(min_length=1), prenom: str | None = None, exclure: uuid.UUID | None = None,
                   c: Ctx = Depends(ctx(*EMPLOYES_LECTURE)), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await FormationService(db, c).doublons(nom, prenom, exclure)


@router.post("/employes", status_code=201)
async def creer_employe(body: EmployeIn, forcer: bool = False,
                        c: Ctx = Depends(ctx("formation.employees.manage")), db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).creer_employe(body.model_dump(), forcer=forcer)


@router.get("/employes/{eid}")
async def fiche_employe(eid: uuid.UUID, c: Ctx = Depends(ctx(*EMPLOYES_LECTURE)),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).fiche_employe(eid)


@router.patch("/employes/{eid}")
async def modifier_employe(eid: uuid.UUID, body: EmployeIn, forcer: bool = False,
                           c: Ctx = Depends(ctx("formation.employees.manage")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).modifier_employe(eid, body.model_dump(exclude_unset=True), forcer=forcer)


@router.post("/employes/{eid}/activation")
async def activer_employe(eid: uuid.UUID, body: ActivationIn, c: Ctx = Depends(ctx("formation.employees.manage")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).activer_employe(eid, body.actif, body.motif)


# ---------------------------------------------------------------------- sessions
@router.get("/sessions")
async def sessions(
    q: str | None = None, statut: str | None = None, annee: int | None = None,
    date_debut: date | None = None, date_fin: date | None = None, theme_id: uuid.UUID | None = None,
    formateur_id: uuid.UUID | None = None, lieu_id: uuid.UUID | None = None, entite_id: uuid.UUID | None = None,
    perimetre_id: uuid.UUID | None = None, employe_id: uuid.UUID | None = None, a_saisir: bool = False,
    feuille: Literal["AVEC", "SANS"] | None = None, tri: str = "date", sens: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1), taille: int = Query(20, ge=1, le=500),
    c: Ctx = Depends(ctx("formation.view", "formation.attendance.view")), db: AsyncSession = Depends(get_db),
) -> dict:
    return await FormationService(db, c).lister_sessions(
        q=q, statut=statut, annee=annee, date_debut=date_debut, date_fin=date_fin, theme_id=theme_id,
        formateur_id=formateur_id, lieu_id=lieu_id, entite_id=entite_id, perimetre_id=perimetre_id,
        employe_id=employe_id, a_saisir=a_saisir, feuille=feuille, tri=tri, sens=sens, page=page, taille=taille)


@router.post("/sessions", status_code=201)
async def creer_session(body: SessionCreate, c: Ctx = Depends(ctx("formation.create")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).creer_session(body.model_dump())


@router.get("/sessions/{sid}")
async def detail_session(sid: uuid.UUID, c: Ctx = Depends(ctx("formation.view", "formation.attendance.view")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).detail_session(sid)


@router.patch("/sessions/{sid}")
async def modifier_session(sid: uuid.UUID, body: SessionPatch, c: Ctx = Depends(ctx("formation.update")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).modifier_session(sid, body.model_dump(exclude_unset=True))


@router.post("/sessions/{sid}/participants")
async def ajouter_participants(sid: uuid.UUID, body: ParticipantsIn, c: Ctx = Depends(ctx("formation.update")),
                               db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).ajouter_participants(sid, body.employe_ids, body.revision)


@router.post("/sessions/{sid}/participants/{pid}/retrait")
async def retirer_participant(sid: uuid.UUID, pid: uuid.UUID, body: RetraitIn,
                              c: Ctx = Depends(ctx("formation.update")), db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).retirer_participant(sid, pid, body.revision, body.motif)


@router.put("/sessions/{sid}/presences")
async def saisir_presences(sid: uuid.UUID, body: PresencesIn, c: Ctx = Depends(ctx("formation.attendance.manage")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).saisir_presences(sid, body.presences, body.revision, body.motif)


@router.post("/sessions/{sid}/statut")
async def changer_statut(sid: uuid.UUID, body: StatutIn,
                         c: Ctx = Depends(ctx("formation.close", "formation.cancel")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationService(db, c).changer_statut(sid, body.action, body.revision, body.motif)


@router.post("/sessions/{sid}/supprimer", status_code=204)
async def supprimer_session(sid: uuid.UUID, body: SuppressionIn, c: Ctx = Depends(ctx("formation.admin")),
                            db: AsyncSession = Depends(get_db)) -> Response:
    await FormationService(db, c).supprimer_session(sid, body.motif)
    return Response(status_code=204)


@router.get("/sessions/{sid}/historique")
async def historique_session(sid: uuid.UUID, c: Ctx = Depends(ctx("formation.view")),
                             db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationReporting(db).journal(entity="formation_session", entity_id=str(sid), taille=100)


@router.get("/sessions/{sid}/feuille-presence")
async def feuille_presence(sid: uuid.UUID, format: Literal["pdf", "xlsx"] = "pdf",
                           c: Ctx = Depends(ctx("formation.view", "formation.attendance.view")),
                           db: AsyncSession = Depends(get_db)) -> Response:
    svc = FormationService(db, c)
    s = await svc.detail_session(sid)
    nom = f"Feuille_presence_{s['reference']}.{format}"
    if format == "pdf":
        contenu, media = formation_export.feuille_presence_pdf(s), "application/pdf"
    else:
        contenu, media = formation_export.feuille_presence_excel(s), XLSX
    await svc.audit(f"formation.export.{'pdf' if format == 'pdf' else 'excel'}", "formation_export", sid,
                    after={"document": "feuille_presence", "reference": s["reference"]})
    return _fichier(contenu, nom, media)


@router.get("/sessions/{sid}/documents")
async def documents_session(sid: uuid.UUID, c: Ctx = Depends(ctx("formation.view", "formation.attendance.view")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await formation_documents.lister(FormationService(db, c), sid)


@router.post("/sessions/{sid}/documents", status_code=201)
async def deposer_document(sid: uuid.UUID, file: UploadFile = File(...),
                           c: Ctx = Depends(ctx("formation.attendance.manage")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await formation_documents.deposer(FormationService(db, c), sid, file)


@router.post("/sessions/{sid}/documents/{did}/retrait")
async def retirer_document(sid: uuid.UUID, did: uuid.UUID, body: SuppressionIn,
                           c: Ctx = Depends(ctx("formation.attendance.manage")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await formation_documents.retirer(FormationService(db, c), sid, did, body.motif)


@router.get("/sessions/{sid}/documents/{did}/fichier")
async def telecharger_document(sid: uuid.UUID, did: uuid.UUID,
                               c: Ctx = Depends(ctx("formation.view", "formation.attendance.view")),
                               db: AsyncSession = Depends(get_db)) -> Response:
    doc, chemin = await formation_documents.fichier(FormationService(db, c), sid, did)
    return _fichier(chemin.read_bytes(), doc.filename, doc.mime_type or "application/octet-stream")


# --------------------------------------------------------------------- reporting
def filtres(
    date_debut: date | None = None, date_fin: date | None = None, annee: int | None = Query(None, ge=1990, le=2100),
    theme_id: uuid.UUID | None = None, formateur_id: uuid.UUID | None = None, lieu_id: uuid.UUID | None = None,
    entite_id: uuid.UUID | None = None, perimetre_id: uuid.UUID | None = None, employe_id: uuid.UUID | None = None,
    fonction_id: uuid.UUID | None = None, presence: Literal["PRESENT", "ABSENT", "NON_SAISI"] | None = None,
) -> Filtres:
    return Filtres(date_debut=date_debut, date_fin=date_fin, annee=annee, theme_id=theme_id,
                   formateur_id=formateur_id, lieu_id=lieu_id, entite_id=entite_id, perimetre_id=perimetre_id,
                   employe_id=employe_id, fonction_id=fonction_id, presence=presence)


@router.get("/reporting")
async def reporting(f: Filtres = Depends(filtres), c: Ctx = Depends(ctx("formation.reporting.view")),
                    db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationReporting(db).reporting(f, limite_lignes=1000)


async def _noms_filtres(db: AsyncSession, f: Filtres) -> dict[str, str]:
    refs = await Refs.charger(db)
    noms = {str(k): v.libelle for k, v in refs.refs.items()}
    noms.update({str(k): v.libelle for k, v in refs.entites.items()})
    if f.employe_id:
        e = await db.get(FormationEmploye, f.employe_id)
        if e:
            noms[str(e.id)] = nom_complet(e)
    return noms


@router.get("/reporting/export")
async def exporter_reporting(format: Literal["pdf", "xlsx"], f: Filtres = Depends(filtres),
                             c: Ctx = Depends(ctx("formation.reporting.export")),
                             db: AsyncSession = Depends(get_db)) -> Response:
    data = await FormationReporting(db).reporting(f, limite_lignes=None)
    libelle = formation_export.libelle_filtres(data, await _noms_filtres(db, f))
    if format == "pdf":
        contenu, media, nom = formation_export.rapport_pdf(data, libelle), "application/pdf", "Rapport_Formation.pdf"
    else:
        contenu, media, nom = formation_export.rapport_excel(data, libelle), XLSX, "Rapport_Formation.xlsx"
    await FormationService(db, c).audit(
        f"formation.export.{'pdf' if format == 'pdf' else 'excel'}", "formation_export", None,
        after={"document": "rapport", "filtres": libelle, "lignes": data["participations_total"]})
    return _fichier(contenu, nom, media)


@router.get("/journal")
async def journal(
    q: str | None = None, action: str | None = None, entity: str | None = None,
    date_debut: date | None = None, date_fin: date | None = None,
    page: int = Query(1, ge=1), taille: int = Query(30, ge=1, le=200),
    c: Ctx = Depends(ctx("formation.view", "formation.reporting.view")), db: AsyncSession = Depends(get_db),
) -> dict:
    return await FormationReporting(db).journal(q=q, action=action, entity=entity, date_debut=date_debut,
                                                date_fin=date_fin, page=page, taille=taille)


# ----------------------------------------------------------------------- imports
@router.get("/imports")
async def imports(c: Ctx = Depends(ctx("formation.import.view", "formation.import.execute")),
                  db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await FormationImportService(db, c).lister()


@router.post("/imports/analyse", status_code=201)
async def analyser_import(fichier: UploadFile = File(...), c: Ctx = Depends(ctx("formation.import.execute")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    contenu = await fichier.read()
    return await FormationImportService(db, c).analyser(contenu, fichier.filename or "import.xlsx")


@router.get("/imports/{iid}")
async def detail_import(iid: uuid.UUID, c: Ctx = Depends(ctx("formation.import.view", "formation.import.execute")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationImportService(db, c).detail(iid)


@router.post("/imports/{iid}/confirmer")
async def confirmer_import(iid: uuid.UUID, body: ImportConfirmIn, c: Ctx = Depends(ctx("formation.import.execute")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationImportService(db, c).confirmer(iid, body.model_dump())


@router.post("/imports/{iid}/abandonner")
async def abandonner_import(iid: uuid.UUID, c: Ctx = Depends(ctx("formation.import.execute")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await FormationImportService(db, c).abandonner(iid)
