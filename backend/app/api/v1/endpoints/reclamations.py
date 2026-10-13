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
    AppelIn,
    DossierCreate,
    DossierPatch,
    MembreIn,
    MembrePatch,
    ReferentielCreate,
    ReferentielPatch,
    RetraitIn,
    UniteCreate,
    UnitePatch,
)
from app.services.reclamations import constantes as C
from app.services.reclamations import documents, dossiers, organisation
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
            "priorites": _libelles(C.PRIORITE_LIBELLES),
            "resultats": _libelles(C.RESULTAT_LIBELLES),
            "categories_client": _libelles(C.CATEGORIE_CLIENT_LIBELLES),
            "categories_document": _libelles(C.CATEGORIE_DOCUMENT_LIBELLES),
            "types_unite": _libelles(C.TYPE_UNITE_LIBELLES),
            "domaines": _libelles(C.DOMAINE_LIBELLES),
            "statuts_rappel": _libelles(C.STATUT_RAPPEL_LIBELLES),
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
    motif_id: uuid.UUID | None = None,
    sous_motif_id: uuid.UUID | None = None,
    canal_id: uuid.UUID | None = None,
    priorite: str | None = None,
    client_categorie: str | None = None,
    client_racine: str | None = Query(None, max_length=6),
    client_agence_id: uuid.UUID | None = None,
    unite_reception_id: uuid.UUID | None = None,
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
        "unite_reception_id": unite_reception_id, "unite_traitement_id": unite_traitement_id,
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
    return await dossiers.detail(db, s, await dossiers.charger(db, s, rid))


@router.patch("/dossiers/{rid}")
async def modifier_dossier(rid: uuid.UUID, body: DossierPatch,
                           s: ReclamationsScope = Depends(scope("reclamations.update", "reclamations.create")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await dossiers.modifier(db, s, rid, body.model_dump(exclude_unset=True))


@router.post("/dossiers/{rid}/appels", status_code=201)
async def ajouter_appel(rid: uuid.UUID, body: AppelIn,
                        s: ReclamationsScope = Depends(scope("reclamations.update", "reclamations.create")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await dossiers.ajouter_appel(db, s, rid, body.model_dump())


@router.get("/dossiers/{rid}/chronologie")
async def chronologie(rid: uuid.UUID, s: ReclamationsScope = Depends(scope(VUE)),
                      db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await dossiers.chronologie(db, s, rid)


@router.get("/dossiers/{rid}/audit")
async def audit(rid: uuid.UUID, s: ReclamationsScope = Depends(scope("reclamations.audit.view")),
                db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await dossiers.journal_audit(db, s, rid)


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
