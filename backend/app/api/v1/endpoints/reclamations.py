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
from app.core.exceptions import AppError
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
    ImportConfirmIn,
    MembreIn,
    MembrePatch,
    DevisesIn,
    OperationsIn,
    QualifierIn,
    ReferentielCreate,
    ReferentielPatch,
    RegleMotifIn,
    RegularisationIn,
    ReponseEnvoyeeIn,
    RestaurerIn,
    RetournerIn,
    RetraitIn,
    SupprimerIn,
    UniteCreate,
    UnitePatch,
    ValidationReferentielIn,
    VerificationOperationsIn,
)
from app.services.reclamations import constantes as C
from app.services.reclamations import (
    circuit,
    documents,
    dossiers,
    imports,
    organisation,
    reporting,
    reponses,
    suppression,
)
from app.services import org_referentiel
from app.services.reclamations import operations as ops
from app.services.reclamations import regles
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


def organigramme_concerne(ctx: dossiers.Contexte) -> dict:
    """Départements et services proposables, lus dans l'organigramme central (jamais une liste locale)."""
    arbre = ctx.arbre
    departements, services = [], []
    for e in sorted(arbre.entites.values(), key=lambda x: (arbre.libelle_chemin(x.id) or "")):
        if not e.is_active:
            continue
        if e.type_entite in C.TYPES_ORG_DEPARTEMENT:
            departements.append({"id": str(e.id), "libelle": e.libelle, "sigle": e.sigle, "type": e.type_entite,
                                 "chemin": arbre.libelle_chemin(e.id), "a_confirmer": e.a_confirmer})
        elif e.type_entite in C.TYPES_ORG_SERVICE:
            ancetres = arbre.chemin(e.id)[:-1]
            parent = next((a for a in reversed(ancetres) if a.type_entite in C.TYPES_ORG_DEPARTEMENT), None)
            services.append({"id": str(e.id), "libelle": e.libelle, "sigle": e.sigle, "type": e.type_entite,
                             "chemin": arbre.libelle_chemin(e.id), "a_confirmer": e.a_confirmer,
                             "departement_id": str(parent.id) if parent else None,
                             "ancetres": [str(a.id) for a in ancetres],
                             "unite_id": str(u) if (u := dossiers.unite_du_service(ctx, e.id)) else None})
    return {"departements": departements, "services": services}


# ------------------------------------------------------------------ configuration
@router.get("/config")
async def config(s: ReclamationsScope = Depends(scope(VUE)), db: AsyncSession = Depends(get_db)) -> dict:
    refs = await organisation.lister_referentiels(db)
    par_domaine: dict[str, list[dict]] = {d: [] for d in C.DOMAINE_LIBELLES}
    for r in refs:
        par_domaine[r["domaine"]].append(r)
    ctx = await dossiers.Contexte.charger(db)
    regles_motifs = await regles.lister(db)
    return {
        "acces": s.to_dict(),
        "referentiels": par_domaine,
        "unites": await organisation.lister_unites(db),
        "agences": [{"id": str(i), "code": c, "libelle": lib}
                    for i, (c, lib) in sorted(ctx.agences.items(), key=lambda x: x[1][0])],
        "organisation": organigramme_concerne(ctx),
        "devises": regles_motifs["devises"],
        "regles_motifs": {x["motif_id"]: x for x in regles_motifs["items"]},
        "regle_defaut": regles_motifs["defaut"],
        "champs_operation": regles_motifs["champs"],
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
            "validations_referentiel": _libelles(C.VALIDATION_REFERENTIEL_LIBELLES),
            "statuts_identification": _libelles(C.STATUT_IDENTIFICATION_LIBELLES),
            "natures_mouvement": _libelles(C.NATURE_LIBELLES),
            "roles_operation": _libelles(C.ROLE_OPERATION_LIBELLES),
            "regularisations": _libelles(C.REGULARISATION_LIBELLES),
        },
        "parametres": {"enregistrement_appels_autorise": await dossiers.enregistrement_autorise(db),
                       "regroupement_multi_clients_autorise": await ops.regroupement_autorise(db),
                       "max_operations": C.MAX_OPERATIONS},
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


@router.post("/referentiels/{rid}/validation")
async def valider_referentiel(rid: uuid.UUID, body: ValidationReferentielIn, s: ReclamationsScope = Depends(scope(
        "reclamations.references.validate")), db: AsyncSession = Depends(get_db)) -> dict:
    return await organisation.valider_referentiel(db, s, rid, body.model_dump())


@router.delete("/referentiels/{rid}")
async def supprimer_referentiel(rid: uuid.UUID, s: ReclamationsScope = Depends(scope(
        "reclamations.references.manage")), db: AsyncSession = Depends(get_db)) -> dict:
    return await organisation.supprimer_referentiel(db, s, rid)


# ------------------------------------------------------------- règles par motif
@router.get("/regles")
async def lister_regles(type_id: uuid.UUID | None = None,
                        s: ReclamationsScope = Depends(scope(VUE, *REFERENTIELS)),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await regles.lister(db, type_id)


@router.put("/regles/{motif_id}")
async def enregistrer_regle(motif_id: uuid.UUID, body: RegleMotifIn, s: ReclamationsScope = Depends(scope(
        "reclamations.references.manage")), db: AsyncSession = Depends(get_db)) -> dict:
    return await regles.enregistrer(db, s, motif_id, body.model_dump())


@router.post("/regles/{motif_id}/validation")
async def valider_regle(motif_id: uuid.UUID, body: ValidationReferentielIn, s: ReclamationsScope = Depends(scope(
        "reclamations.references.validate")), db: AsyncSession = Depends(get_db)) -> dict:
    return await regles.valider(db, s, motif_id, body.statut_validation)


@router.put("/parametres/devises")
async def modifier_devises(body: DevisesIn, s: ReclamationsScope = Depends(scope(
        "reclamations.references.manage")), db: AsyncSession = Depends(get_db)) -> list[str]:
    return await regles.modifier_devises(db, s, body.devises)


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
async def filtres_dossiers(
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
    client_agence_id: uuid.UUID | Literal["AUCUNE"] | None = None,
    unite_reception_id: uuid.UUID | None = None,
    unite_concernee_id: uuid.UUID | None = None,
    unite_traitement_id: uuid.UUID | None = None,
    gestionnaire_id: uuid.UUID | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    ouvertes: bool = False,
    archivees: bool | None = None,
    corbeille: bool = False,
    indicateur: str | None = Query(None, max_length=60, pattern=r"^[a-z_]+$"),
    kpi_debut: date | None = None,
    kpi_fin: date | None = None,
    kpi_unite_id: uuid.UUID | None = None,
    org_entite_id: uuid.UUID | None = None,
    point_reception_id: uuid.UUID | None = None,
    agence_reception_id: uuid.UUID | None = None,
    org_departement_id: uuid.UUID | None = None,
    org_service_id: uuid.UUID | None = None,
    operation_reference: str | None = Query(None, max_length=120),
    compte_reference: str | None = Query(None, max_length=60),
    devise: str | None = Query(None, pattern=r"^[A-Z]{3}$"),
    regularisation_statut: Literal["A_EFFECTUER", "EFFECTUEE"] | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Filtres communs à la liste, au tableau de bord et aux exports.

    ``corbeille`` : liste seulement ; ``indicateur`` + ``kpi_*`` : dossiers d'un KPI cliqué ;
    ``org_entite_id`` : direction / département / service de l'organigramme central, sous-entités incluses ;
    ``org_departement_id`` / ``org_service_id`` : département / service concerné (sous-entités incluses)."""
    if date_debut and date_fin and date_fin < date_debut:
        raise AppError("La date de fin précède la date de début", 422, code="PERIODE_INVALIDE")
    org_unites, org_libelle = (await organisation.unites_de_entite(db, org_entite_id)) if org_entite_id \
        else (None, None)
    arbre = await org_referentiel.charger_arbre(db) if (org_departement_id or org_service_id) else None
    return {
        "point_reception_id": point_reception_id, "agence_reception_id": agence_reception_id,
        "org_departement_ids": arbre.descendants(org_departement_id) if org_departement_id else None,
        "org_service_ids": arbre.descendants(org_service_id) if org_service_id else None,
        "operation_reference": operation_reference, "compte_reference": compte_reference, "devise": devise,
        "regularisation_statut": regularisation_statut,
        "org_entite_id": org_entite_id, "org_unites": org_unites, "org_entite_libelle": org_libelle,
        "corbeille": corbeille,
        "q": q, "statut": statut, "groupe": groupe, "etape": etape, "type_id": type_id, "motif_id": motif_id,
        "sous_motif_id": sous_motif_id, "canal_id": canal_id, "priorite": priorite,
        "client_categorie": client_categorie, "client_racine": client_racine, "client_agence_id": client_agence_id,
        "unite_reception_id": unite_reception_id, "unite_concernee_id": unite_concernee_id,
        "unite_traitement_id": unite_traitement_id,
        "gestionnaire_id": gestionnaire_id, "date_debut": date_debut, "date_fin": date_fin, "ouvertes": ouvertes,
        "archivees": archivees,
        "indicateur": indicateur, "kpi_debut": kpi_debut, "kpi_fin": kpi_fin, "kpi_unite_id": kpi_unite_id,
    }


@router.get("/dossiers")
async def lister_dossiers(
    filtres: dict = Depends(filtres_dossiers),
    page: int = Query(1, ge=1),
    taille: int = Query(25, ge=1, le=100),
    tri: str = "date_premiere_reception",
    ordre: Literal["asc", "desc"] = "desc",
    s: ReclamationsScope = Depends(scope(VUE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
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


@router.post("/operations/verifier")
async def verifier_operations(body: VerificationOperationsIn,
                              s: ReclamationsScope = Depends(scope("reclamations.update", "reclamations.create")),
                              db: AsyncSession = Depends(get_db)) -> dict:
    return await dossiers.verifier_operations(db, s, body.model_dump())


@router.get("/imports/modele")
async def modele_import(motif_id: uuid.UUID | None = None,
                        s: ReclamationsScope = Depends(scope("reclamations.update", "reclamations.create")),
                        db: AsyncSession = Depends(get_db)) -> Response:
    ex = await regles.exigences(db, motif_id)
    ctx = await dossiers.Contexte.charger(db) if motif_id else None
    motif = ctx.lib(motif_id) if ctx else None
    return _fichier(imports.modele(ex, motif), "modele-import-operations-reclamation.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/dossiers/{rid}/imports", status_code=201)
async def analyser_import(rid: uuid.UUID, file: UploadFile = File(...),
                          mode: Literal["AJOUT", "REMPLACEMENT"] = Form("AJOUT"),
                          forcer: bool = Form(False),
                          s: ReclamationsScope = Depends(scope("reclamations.update", "reclamations.create")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await imports.analyser(db, s, rid, file, mode, forcer=forcer)


@router.get("/dossiers/{rid}/imports/{iid}/rapport")
async def rapport_import(rid: uuid.UUID, iid: uuid.UUID, s: ReclamationsScope = Depends(scope(VUE)),
                         db: AsyncSession = Depends(get_db)) -> Response:
    return _fichier(await imports.rapport_erreurs(db, s, rid, iid), "rapport-import-operations.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/dossiers/{rid}/imports/{iid}")
async def lire_import(rid: uuid.UUID, iid: uuid.UUID, s: ReclamationsScope = Depends(scope(VUE)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return await imports.lire(db, s, rid, iid)


@router.post("/dossiers/{rid}/imports/{iid}/confirmer")
async def confirmer_import(rid: uuid.UUID, iid: uuid.UUID, body: ImportConfirmIn,
                           s: ReclamationsScope = Depends(scope("reclamations.update", "reclamations.create")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    await imports.confirmer(db, s, rid, iid, body.model_dump())
    return await circuit.fiche(db, s, await dossiers.charger(db, s, rid))


@router.post("/dossiers/{rid}/imports/{iid}/abandonner")
async def abandonner_import(rid: uuid.UUID, iid: uuid.UUID,
                            s: ReclamationsScope = Depends(scope("reclamations.update", "reclamations.create")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await imports.abandonner(db, s, rid, iid)


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
                           titre: str | None = Form(None, max_length=255),
                           date_document: date | None = Form(None),
                           operation_reference: str | None = Form(None, max_length=120),
                           s: ReclamationsScope = Depends(scope("reclamations.document.upload")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await documents.deposer(db, s, rid, file, categorie, commentaire, titre=titre,
                                   operation_reference=operation_reference,
                                   date_document=date_document)


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


@router.post("/dossiers/{rid}/regularisation")
async def confirmer_regularisation(rid: uuid.UUID, body: RegularisationIn,
                                   s: ReclamationsScope = Depends(scope("reclamations.regularisation.confirm")),
                                   db: AsyncSession = Depends(get_db)) -> dict:
    return await circuit.confirmer_regularisation(db, s, rid, body.model_dump())


@router.post("/dossiers/{rid}/supprimer")
async def supprimer(rid: uuid.UUID, body: SupprimerIn,
                    s: ReclamationsScope = Depends(scope(suppression.PERMISSION)),
                    db: AsyncSession = Depends(get_db)) -> dict:
    resultat, fichiers = await suppression.supprimer(db, s, rid, body.model_dump())
    await db.commit()
    suppression.effacer_fichiers(fichiers)
    return resultat


@router.post("/dossiers/{rid}/restaurer")
async def restaurer(rid: uuid.UUID, body: RestaurerIn,
                    s: ReclamationsScope = Depends(scope(suppression.PERMISSION)),
                    db: AsyncSession = Depends(get_db)) -> dict:
    r = await suppression.restaurer(db, s, rid, body.model_dump())
    return await circuit.fiche(db, s, r)


# ------------------------------------------------------------------ pilotage
@router.get("/tableau-de-bord")
async def tableau_de_bord(filtres: dict = Depends(filtres_dossiers),
                          s: ReclamationsScope = Depends(scope(VUE)), db: AsyncSession = Depends(get_db)) -> dict:
    return await reporting.tableau_de_bord(db, s, _sans_liste(filtres))


def _sans_liste(filtres: dict) -> dict:
    """Le tableau de bord et les rapports ignorent les filtres propres à la liste (corbeille, KPI cliqué)."""
    return {k: v for k, v in filtres.items()
            if k not in ("corbeille", "indicateur", "kpi_debut", "kpi_fin", "kpi_unite_id")}


def _periodes(a_debut: date, a_fin: date, b_debut: date, b_fin: date):
    from app.services.reclamations.indicateurs import Periode

    return Periode.de(a_debut, a_fin), Periode.de(b_debut, b_fin)


@router.get("/comparaison")
async def comparaison(a_debut: date, a_fin: date, b_debut: date, b_fin: date,
                      filtres: dict = Depends(filtres_dossiers),
                      s: ReclamationsScope = Depends(scope("reclamations.reporting.view")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    from app.services.reclamations import indicateurs

    pa, pb = _periodes(a_debut, a_fin, b_debut, b_fin)
    return await indicateurs.comparaison(db, s, _sans_liste(filtres), pa, pb)


@router.get("/export/comparaison")
async def exporter_comparaison(a_debut: date, a_fin: date, b_debut: date, b_fin: date,
                               format: Literal["xlsx", "pdf"] = "xlsx", filtres: dict = Depends(filtres_dossiers),
                               s: ReclamationsScope = Depends(scope("reclamations.reporting.export")),
                               db: AsyncSession = Depends(get_db)) -> Response:
    pa, pb = _periodes(a_debut, a_fin, b_debut, b_fin)
    contenu = await reporting.exporter_comparaison(db, s, _sans_liste(filtres), pa, pb, format=format)
    return _export(contenu, f"comparaison-reclamations-{a_debut}-{b_debut}", format)


def _export(contenu: bytes, base: str, format: str) -> Response:
    if format == "pdf":
        return _fichier(contenu, f"{base}.pdf", "application/pdf")
    return _fichier(contenu, f"{base}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/circuit")
async def vue_circuit(s: ReclamationsScope = Depends(scope(VUE)), db: AsyncSession = Depends(get_db)) -> dict:
    return await reporting.circuit(db, s)


@router.get("/export")
async def exporter(format: Literal["xlsx", "pdf"] = "xlsx", filtres: dict = Depends(filtres_dossiers),
                   s: ReclamationsScope = Depends(scope("reclamations.reporting.view")),
                   db: AsyncSession = Depends(get_db)) -> Response:
    contenu = await reporting.exporter(db, s, filtres, format=format)
    nom = f"reclamations-{date.today().isoformat()}.{format}"
    if format == "pdf":
        return _fichier(contenu, nom, "application/pdf")
    return _fichier(contenu, nom, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
