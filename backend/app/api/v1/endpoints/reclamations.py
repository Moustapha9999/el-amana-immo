"""API Gestion des réclamations.

Login 2 module ``reclamations`` (dépendance posée au montage du router) ; permissions
``reclamations.*`` vérifiées par route, puis périmètre des dossiers par ``ReclamationsScope``.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import auth_http_error, get_current_user
from app.db.session import get_db
from app.models import ReclamationReferentiel, ReclamationUnite, User
from app.services.reclamations import constantes as C
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


@router.get("/config")
async def config(s: ReclamationsScope = Depends(scope("reclamations.view")),
                 db: AsyncSession = Depends(get_db)) -> dict:
    refs = (await db.scalars(select(ReclamationReferentiel).order_by(
        ReclamationReferentiel.domaine, ReclamationReferentiel.ordre, ReclamationReferentiel.libelle))).all()
    par_domaine: dict[str, list[dict]] = {d: [] for d in C.DOMAINE_LIBELLES}
    for r in refs:
        par_domaine[r.domaine].append({
            "id": str(r.id), "code": r.code, "libelle": r.libelle, "actif": r.actif,
            "parent_id": str(r.parent_id) if r.parent_id else None,
        })
    unites = (await db.scalars(select(ReclamationUnite).order_by(
        ReclamationUnite.ordre, ReclamationUnite.libelle))).all()
    return {
        "acces": s.to_dict(),
        "referentiels": par_domaine,
        "unites": [{
            "id": str(u.id), "libelle": u.libelle, "type_unite": u.type_unite, "actif": u.actif,
            "parent_id": str(u.parent_id) if u.parent_id else None,
            "est_service_reclamations": u.est_service_reclamations,
        } for u in unites],
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
        },
        "aujourdhui": date.today().isoformat(),
        "utilisateur": s.user.full_name,
    }
