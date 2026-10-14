"""API Gestion des réclamations.

Login 2 module ``reclamations`` (dépendance posée au montage du router) ; permissions
``reclamations.*`` vérifiées par route, puis périmètre des dossiers par ``ReclamationsScope``.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import auth_http_error, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.reclamations import (
    ActionIn,
    AffecterIn,
    AnnulerIn,
    AppelIn,
    CloturerIn,
    DossierCreate,
    DossierPatch,
    EvaluerIn,
    JourFerieIn,
    MembreIn,
    MembrePatch,
    OperationsIn,
    QualifierIn,
    ReferentielCreate,
    ReferentielPatch,
    RegleDelaiCreate,
    RegleDelaiPatch,
    ReponseEnvoyeeIn,
    RetournerIn,
    RetraitIn,
    UniteCreate,
    UnitePatch,
    ValidationRegleIn,
)
from app.services.reclamations import constantes as C
from app.services.reclamations import circuit, delais, documents, dossiers, organisation, reporting, reponses
from app.services.reclamations.acces import ReclamationsScope, charger_scope

router = APIRouter(prefix="/reclamations", tags=["Gestion des réclamations"])


def scope(*codes: str):
    async def dependance(request: Request, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)) -> ReclamationsScope:
        s = await charger_scope(db, user, ip_address=request.client.host if request.client else None,
                                session_id=getattr(request.state, "bea_session_id", None))
        if codes and not s.peut(*codes):
            raise auth_http_error(403, "PERMISSION_DENIED", "Permission refusée", required=list(codes))
        return s

    return dependance


def _libelles(d: dict[str, str]) -> list[dict[str, str]]:
    return [{"code": k, "libelle": v} for k, v in d.items()]


def _fichier(contenu: bytes, nom: str, media: str, *, inline: bool = False) -> Response:
    mode = "inline" if inline else "attachment"
    return Response(content=contenu, media_type=media, headers={
        "Content-Disposition": f"{mode}; filename=\"{quote(nom)}\"; filename*=UTF-8''{quote(nom)}",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


VUE = "reclamations.view"
REFERENTIELS = ("reclamations.references.view", "reclamations.references.manage")


# ------------------------------------------------------------------ configuration
@router.get("/config")
async def config(s: ReclamationsScope = Depends(scope(VUE)), db: AsyncSession = Depends(get_db)) -> dict:
    refs = await organisation.lister_referentiels(db)
    par_domaine: dict[str, list[dict]] = {d: [] for d in C.DOMAINE_LIBELLES}
    for r in refs:
        par_domaine[r["domaine"]].append(r)
    return {
        "acces": s.to_dict(),
        "referentiels": par_domaine,
        "unites": await organisation.lister_unites(db),
        "agences": [{"id": str(i), "code": c, "libelle": lib}
                    for i, (c, lib) in sorted((await dossiers.Contexte.charger(db)).agences.items(),
                                              key=lambda x: x[1][0])],
        "libelles": {
            "statuts": _libelles(C.STATUT_LIBELLES),
            "etapes": _libelles(C.ETAPE_LIBELLES),
            "groupes": _libelles(C.GROUPE_LIBELLES),
            "statut_groupes": C.STATUT_GROUPES,
            "etape_du_statut": C.ETAPE_DU_STATUT,
            "priorites": _libelles(C.PRIORITE_LIBELLES),
            "resultats": _libelles(C.RESULTAT_LIBELLES),
            "categories_client": _libelles(C.CATEGORIE_CLIENT_LIBELLES),
            "categories_document": _libelles(C.CATEGORIE_DOCUMENT_LIBELLES),
            "types_unite": _libelles(C.TYPE_UNITE_LIBELLES),
            "domaines": _libelles(C.DOMAINE_LIBELLES),
            "statuts_rappel": _libelles(C.STATUT_RAPPEL_LIBELLES),
            "statuts_affectation": _libelles(C.STATUT_AFFECTATION_LIBELLES),
            "statuts_reponse": _libelles(C.STATUT_REPONSE_LIBELLES),
            "evaluations": _libelles(C.EVALUATION_LIBELLES),
            "validations_regle": _libelles(C.VALIDATION_REGLE_LIBELLES),
            "unites_duree": _libelles(C.UNITE_DUREE_LIBELLES),
            "points_depart": _libelles(C.POINT_DEPART_LIBELLES),
        },
        "parametres": {"enregistrement_appels_autorise": await dossiers.enregistrement_autorise(db)},
        "aujourdhui": date.today().isoformat(),
        "utilisateur": s.user.full_name,
    }


# ------------------------------------------------------------------ référentiels
@router.get("/referentiels")
async def referentiels(domaine: str | None = None, s: ReclamationsScope = Depends(scope(VUE, *REFERENTIELS)),
                       db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await organisation.lister_referentiels(db, domaine)


@router.post("/referentiels", status_code=201)
async def creer_referentiel(body: ReferentielCreate, s: ReclamationsScope = Depends(scope(
        "reclamations.references.manage")), db: AsyncSession = Depends(get_db)) -> dict:
    return await organisation.creer_referentiel(db, s, body.model_dump())


@router.patch("/referentiels/{rid}")
async def modifier_referentiel(rid: uuid.UUID, body: ReferentielPatch, s: ReclamationsScope = Depends(scope(
        "reclamations.references.manage")), db: AsyncSession = Depends(get_db)) -> dict:
    return await organisation.modifier_referentiel(db, s, rid, body.model_dump(exclude_unset=True))


@router.delete("/referentiels/{rid}", status_code=204)
async def supprimer_referentiel(rid: uuid.UUID, s: ReclamationsScope = Depends(scope(
        "reclamations.references.manage")), db: AsyncSession = Depends(get_db)) -> Response:
    await organisation.supprimer_referentiel(db, s, rid)
    return Response(status_code=204)


# ---------------------------------------------------------------------- unités
@router.get("/unites")
async def unites(s: ReclamationsScope = Depends(scope(VUE)), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await organisation.lister_unites(db)


@router.post("/unites", status_code=201)
async def creer_unite(body: UniteCreate, s: ReclamationsScope = Depends(scope("reclamations.services.manage")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return await organisation.creer_unite(db, s, body.model_dump())


@router.patch("/unites/{uid}")
async def modifier_unite(uid: uuid.UUID, body: UnitePatch,
                         s: ReclamationsScope = Depends(scope("reclamations.services.manage")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    return await organisation.modifier_unite(db, s, uid, body.model_dump(exclude_unset=True))


@router.get("/unites/{uid}/membres")
async def membres(uid: uuid.UUID, s: ReclamationsScope = Depends(scope("reclamations.services.manage",
                                                                         "reclamations.scope.all")),
                  db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await organisation.lister_membres(db, uid)


@router.post("/unites/{uid}/membres", status_code=201)
async def ajouter_membre(uid: uuid.UUID, body: MembreIn,
                         s: ReclamationsScope = Depends(scope("reclamations.services.manage")),
                         db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await organisation.ajouter_membre(db, s, uid, body.model_dump())


@router.patch("/unites/{uid}/membres/{mid}")
async def modifier_membre(uid: uuid.UUID, mid: uuid.UUID, body: MembrePatch,
                          s: ReclamationsScope = Depends(scope("reclamations.services.manage")),
                          db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await organisation.modifier_membre(db, s, uid, mid, body.model_dump(exclude_unset=True))


@router.get("/utilisateurs")
async def utilisateurs(q: str = Query(min_length=2, max_length=100),
                       s: ReclamationsScope = Depends(scope("reclamations.services.manage")),
                       db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await organisation.rechercher_utilisateurs(db, q)


# ------------------------------------------------------------------ clients
@router.get("/clients/{racine}")
async def apercu_client(racine: str, s: ReclamationsScope = Depends(scope("reclamations.create",
                                                                           "reclamations.update")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await dossiers.apercu_client(db, racine)


# ------------------------------------------------------------------ dossiers
@router.get("/dossiers")
async def lister_dossiers(
    q: str | None = Query(None, max_length=100),
    statut: list[str] | None = Query(None),
    groupe: list[str] | None = Query(None),
    etape: str | None = None,
    type_id: uuid.UUID | None = None,
    motif_id: uuid.UUID | Literal["AUTRE"] | None = None,
    sous_motif_id: uuid.UUID | None = None,
    canal_id: uuid.UUID | None = None,
    priorite: str | None = None,
    client_categorie: str | None = None,
    client_racine: str | None = Query(None, max_length=6),
    client_agence_id: uuid.UUID | None = None,
    unite_reception_id: uuid.UUID | None = None,
    unite_concernee_id: uuid.UUID | None = None,
    unite_traitement_id: uuid.UUID | None = None,
    gestionnaire_id: uuid.UUID | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    ouvertes: bool = False,
    en_retard: bool = False,
    sans_echeance: bool = False,
    archivees: bool | None = None,
    page: int = Query(1, ge=1),
    taille: int = Query(25, ge=1, le=100),
    tri: str = "date_premiere_reception",
    ordre: Literal["asc", "desc"] = "desc",
    s: ReclamationsScope = Depends(scope(VUE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    filtres = {
        "q": q, "statut": statut, "groupe": groupe, "etape": etape, "type_id": type_id, "motif_id": motif_id,
        "sous_motif_id": sous_motif_id, "canal_id": canal_id, "priorite": priorite,
        "client_categorie": client_categorie, "client_racine": client_racine, "client_agence_id": client_agence_id,
        "unite_reception_id": unite_reception_id, "unite_concernee_id": unite_concernee_id,
        "unite_traitement_id": unite_traitement_id,
        "gestionnaire_id": gestionnaire_id, "date_debut": date_debut, "date_fin": date_fin, "ouvertes": ouvertes,
        "en_retard": en_retard, "sans_echeance": sans_echeance, "archivees": archivees,
    }
    return await dossiers.lister(db, s, filtres, page=page, taille=taille, tri=tri, ordre=ordre)


@router.post("/dossiers", status_code=201)
async def creer_dossier(body: DossierCreate, s: ReclamationsScope = Depends(scope("reclamations.create")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await dossiers.creer(db, s, body.model_dump())


@router.get("/dossiers/{rid}")
async def lire_dossier(rid: uuid.UUID, s: ReclamationsScope = Depends(scope(VUE)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.fiche(db, s, await dossiers.charger(db, s, rid))


@router.patch("/dossiers/{rid}")
async def modifier_dossier(rid: uuid.UUID, body: DossierPatch,
                           s: ReclamationsScope = Depends(scope("reclamations.update", "reclamations.create")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    await dossiers.modifier(db, s, rid, body.model_dump(exclude_unset=True))
    return await circuit.fiche(db, s, await dossiers.charger(db, s, rid))


@router.put("/dossiers/{rid}/operations")
async def remplacer_operations(rid: uuid.UUID, body: OperationsIn,
                               s: ReclamationsScope = Depends(scope("reclamations.update", "reclamations.create")),
                               db: AsyncSession = Depends(get_db)) -> dict:
    await dossiers.remplacer_operations(db, s, rid, body.model_dump())
    return await circuit.fiche(db, s, await dossiers.charger(db, s, rid))


@router.post("/dossiers/{rid}/appels", status_code=201)
async def ajouter_appel(rid: uuid.UUID, body: AppelIn,
                        s: ReclamationsScope = Depends(scope("reclamations.update", "reclamations.create")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await dossiers.ajouter_appel(db, s, rid, body.model_dump())


@router.get("/dossiers/{rid}/chronologie")
async def chronologie(rid: uuid.UUID, s: ReclamationsScope = Depends(scope(VUE)),
                      db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await dossiers.chronologie(db, s, rid)


# ------------------------------------------------------------------ documents
@router.get("/dossiers/{rid}/documents")
async def lister_documents(rid: uuid.UUID, s: ReclamationsScope = Depends(scope("reclamations.document.view")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await documents.lister(db, s, rid)


@router.post("/dossiers/{rid}/documents", status_code=201)
async def deposer_document(rid: uuid.UUID, file: UploadFile = File(...), categorie: str = Form(...),
                           commentaire: str | None = Form(None, max_length=2000),
                           s: ReclamationsScope = Depends(scope("reclamations.document.upload")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await documents.deposer(db, s, rid, file, categorie, commentaire)


@router.post("/dossiers/{rid}/documents/{did}/retrait")
async def retirer_document(rid: uuid.UUID, did: uuid.UUID, body: RetraitIn,
                           s: ReclamationsScope = Depends(scope("reclamations.document.remove")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await documents.retirer(db, s, rid, did, body.motif)


@router.get("/dossiers/{rid}/documents/{did}/fichier")
async def telecharger_document(rid: uuid.UUID, did: uuid.UUID, apercu: bool = False,
                               s: ReclamationsScope = Depends(scope("reclamations.document.download")),
                               db: AsyncSession = Depends(get_db)) -> Response:
    doc, chemin = await documents.fichier(db, s, rid, did, apercu=apercu)
    return _fichier(chemin.read_bytes(), doc.filename, doc.mime_type or "application/octet-stream", inline=apercu)


# ------------------------------------------------------------------ circuit
@router.post("/dossiers/{rid}/qualifier")
async def qualifier(rid: uuid.UUID, body: QualifierIn, s: ReclamationsScope = Depends(scope("reclamations.qualify")),
                    db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.qualifier(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/affecter")
async def affecter(rid: uuid.UUID, body: AffecterIn, s: ReclamationsScope = Depends(scope("reclamations.assign")),
                   db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.affecter(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/traiter-interne")
async def traiter_interne(rid: uuid.UUID, body: ActionIn,
                          s: ReclamationsScope = Depends(scope("reclamations.qualify")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.traiter_interne(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/retourner")
async def retourner(rid: uuid.UUID, body: RetournerIn, s: ReclamationsScope = Depends(scope("reclamations.treat")),
                    db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.retourner(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/evaluer")
async def evaluer(rid: uuid.UUID, body: EvaluerIn, s: ReclamationsScope = Depends(scope("reclamations.review")),
                  db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.evaluer(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/reponse")
async def enregistrer_reponse(rid: uuid.UUID, body: ReponseEnvoyeeIn,
                              s: ReclamationsScope = Depends(scope("reclamations.response.send")),
                              db: AsyncSession = Depends(get_db)) -> dict:
    return await reponses.enregistrer_envoi(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/cloturer")
async def cloturer(rid: uuid.UUID, body: CloturerIn, s: ReclamationsScope = Depends(scope("reclamations.close")),
                   db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.cloturer(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/refuser")
async def refuser(rid: uuid.UUID, body: ActionIn, s: ReclamationsScope = Depends(scope("reclamations.reject")),
                  db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.refuser(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/annuler")
async def annuler(rid: uuid.UUID, body: AnnulerIn, s: ReclamationsScope = Depends(scope("reclamations.cancel")),
                  db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.annuler(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/rouvrir")
async def rouvrir(rid: uuid.UUID, body: ActionIn, s: ReclamationsScope = Depends(scope("reclamations.reopen")),
                  db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.rouvrir(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/archiver")
async def archiver(rid: uuid.UUID, body: ActionIn, s: ReclamationsScope = Depends(scope("reclamations.archive")),
                   db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.archiver(db, s, rid, body.model_dump())


# ------------------------------------------------------------------ délais
@router.get("/regles-delai")
async def lister_regles(s: ReclamationsScope = Depends(scope(VUE, "reclamations.delais.manage")),
                        db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await delais.lister_regles(db)


@router.post("/regles-delai", status_code=201)
async def creer_regle(body: RegleDelaiCreate, s: ReclamationsScope = Depends(scope("reclamations.delais.manage")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return await delais.creer_regle(db, s, body.model_dump())


@router.patch("/regles-delai/{rid}")
async def modifier_regle(rid: uuid.UUID, body: RegleDelaiPatch,
                         s: ReclamationsScope = Depends(scope("reclamations.delais.manage")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    return await delais.modifier_regle(db, s, rid, body.model_dump(exclude_unset=True))


@router.post("/regles-delai/{rid}/validation")
async def valider_regle(rid: uuid.UUID, body: ValidationRegleIn,
                        s: ReclamationsScope = Depends(scope("reclamations.delais.validate")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await delais.valider_regle(db, s, rid, body.model_dump())


@router.get("/jours-feries")
async def lister_feries(s: ReclamationsScope = Depends(scope(VUE)), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await delais.lister_feries(db)


@router.post("/jours-feries", status_code=201)
async def ajouter_ferie(body: JourFerieIn, s: ReclamationsScope = Depends(scope("reclamations.delais.manage")),
                        db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await delais.ajouter_ferie(db, s, body.model_dump())


@router.delete("/jours-feries/{jour}", status_code=204)
async def retirer_ferie(jour: date, s: ReclamationsScope = Depends(scope("reclamations.delais.manage")),
                        db: AsyncSession = Depends(get_db)) -> Response:
    await delais.retirer_ferie(db, s, jour)
    return Response(status_code=204)


@router.get("/alertes")
async def alertes(s: ReclamationsScope = Depends(scope(VUE)), db: AsyncSession = Depends(get_db)) -> dict:
    return await delais.alertes(db, s)


# ------------------------------------------------------------------ pilotage
@router.get("/tableau-de-bord")
async def tableau_de_bord(date_debut: date | None = None, date_fin: date | None = None,
                          s: ReclamationsScope = Depends(scope(VUE)), db: AsyncSession = Depends(get_db)) -> dict:
    return await reporting.tableau_de_bord(db, s, {"date_debut": date_debut, "date_fin": date_fin})


@router.get("/circuit")
async def vue_circuit(s: ReclamationsScope = Depends(scope(VUE)), db: AsyncSession = Depends(get_db)) -> dict:
    return await reporting.circuit(db, s)


@router.get("/export")
async def exporter(q: str | None = Query(None, max_length=100), groupe: list[str] | None = Query(None),
                   statut: list[str] | None = Query(None), etape: str | None = None,
                   ouvertes: bool = False, en_retard: bool = False, archivees: bool | None = None,
                   date_debut: date | None = None, date_fin: date | None = None,
                   s: ReclamationsScope = Depends(scope("reclamations.reporting.view")),
                   db: AsyncSession = Depends(get_db)) -> Response:
    contenu = await reporting.exporter(db, s, {
        "q": q, "groupe": groupe, "statut": statut, "etape": etape,
        "ouvertes": ouvertes, "en_retard": en_retard, "archivees": archivees,
        "date_debut": date_debut, "date_fin": date_fin,
    })
    return _fichier(contenu, f"reclamations-{date.today().isoformat()}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
