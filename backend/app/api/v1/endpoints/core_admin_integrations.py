"""CORE ADMIN — Studio d'intégration API (Login 1, core.admin.integrations.view).

Phase 1 : catalogue documenté des routes existantes et console de consultation en lecture seule.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.core.config import get_settings
from app.core.request_client import get_client_ip
from app.db.session import get_db
from app.models import User
from app.schemas.integrations import (
    IntegrationCataloguePage,
    IntegrationConsoleOperations,
    IntegrationConsoleRequete,
    IntegrationConsoleResultat,
    IntegrationExemples,
    IntegrationOperationFiche,
)
from app.services.audit_helpers import record_audit
from app.services.integrations import catalogue as cat
from app.services.integrations import console
from app.services.integrations.exemples import generer
from app.services.plateforme_access_service import PlateformeAccessService

router = APIRouter(prefix="/plateforme/admin/integrations", tags=["core-admin"])

_VIEW = require_platform_permission("core.admin.integrations.view")

Auth = Literal["login1", "login2", "login1_ou_login2", "indeterminee", "aucune_detectee"]
PermStatut = Literal["identifiee", "non_determinee", "non_verifiee"]
Dispo = Literal["documentee", "restreinte", "exclue"]
SchemaStatut = Literal["explicite", "generique", "absent"]
Methode = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "OPERATION_INTROUVABLE", "message": "Opération introuvable dans le catalogue"},
    )


async def _etats_modules(db: AsyncSession, operations: list[cat.Operation]) -> dict[str, str]:
    access = PlateformeAccessService(db)
    etats: dict[str, str] = {}
    for code in sorted({op.module_code for op in operations if op.module_code}):
        module = await access.get_module(code)
        if module is None:
            etats[code] = "introuvable"
        elif not module.is_active:
            etats[code] = "desactive"
        else:
            etats[code] = module.statut or "inconnu"
    return etats


def _resume(op: cat.Operation, etats: dict[str, str]) -> dict:
    admissible, motif = console.eligibilite(op)
    return {
        "operation_id": op.operation_id,
        "nom": op.nom,
        "methode": op.methode,
        "chemin": op.chemin,
        "module": op.module,
        "module_code": op.module_code,
        "module_etat": etats.get(op.module_code, "introuvable") if op.module_code else "non_applicable",
        "authentification": op.authentification,
        "permissions": op.permissions,
        "exigence_permissions": cat.exigence_texte(op.exigences),
        "permission_statut": op.permission_statut,
        "schema_reponse_statut": op.schema_reponse_statut,
        "disponibilite": op.disponibilite,
        "categorie_exclusion": op.categorie_exclusion,
        "motifs": op.motifs,
        "exemples_disponibles": op.exemples_disponibles,
        "console": admissible,
        "console_motif": motif,
    }


@router.get("/catalogue", response_model=IntegrationCataloguePage)
async def lister_catalogue(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    module: str | None = Query(None, max_length=80),
    methode: Methode | None = None,
    authentification: Auth | None = None,
    permission_statut: PermStatut | None = None,
    schema: SchemaStatut | None = None,
    permission: str | None = Query(None, max_length=120),
    disponibilite: Dispo | None = None,
    console_seulement: bool | None = Query(None, alias="console"),
    q: str | None = Query(None, max_length=120),
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    operations, index = cat.operations_de(request.app)
    console_ids = console.ids_console(index)
    filtrees = cat.filtrer(
        operations,
        module=module,
        methode=methode,
        authentification=authentification,
        permission_statut=permission_statut,
        schema_reponse=schema,
        permission=permission,
        disponibilite=disponibilite,
        console_ids=console_ids,
        console=console_seulement,
        recherche=q,
    )
    debut = (page - 1) * size
    page_ops = filtrees[debut : debut + size]
    etats = await _etats_modules(db, page_ops)
    return {
        "items": [_resume(op, etats) for op in page_ops],
        "total": len(filtrees),
        "page": page,
        "size": size,
        "kpis": cat.kpis(operations, console_ids),
        "filtres": {
            "modules": sorted({op.module for op in operations}),
            "methodes": sorted({op.methode for op in operations}),
            "authentifications": sorted({op.authentification for op in operations}),
        },
        "avertissement": cat.AVERTISSEMENT,
    }


@router.get("/catalogue/{operation_id}", response_model=IntegrationOperationFiche)
async def fiche_operation(
    operation_id: str,
    request: Request,
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    _ops, index = cat.operations_de(request.app)
    op = index.get(operation_id)
    if op is None:
        raise _not_found()
    etats = await _etats_modules(db, [op])
    return {
        **_resume(op, etats),
        **cat.detail_expose(op),
        "dans_openapi": op.dans_openapi,
        "dependances_non_analysees": op.dependances_non_analysees,
        "avertissement": cat.AVERTISSEMENT,
    }


@router.get("/catalogue/{operation_id}/exemples", response_model=IntegrationExemples)
async def exemples_operation(
    operation_id: str,
    request: Request,
    _: User = Depends(_VIEW),
):
    _ops, index = cat.operations_de(request.app)
    op = index.get(operation_id)
    if op is None:
        raise _not_found()
    return generer(op)


@router.get("/console/operations", response_model=IntegrationConsoleOperations)
async def operations_console(
    request: Request,
    _: User = Depends(_VIEW),
):
    _ops, index = cat.operations_de(request.app)
    items = []
    for op_id in sorted(console.ids_console(index)):
        op = index[op_id]
        items.append(
            {
                "operation_id": op.operation_id,
                "nom": op.nom,
                "methode": op.methode,
                "chemin": op.chemin,
                "module": op.module,
                "permissions": op.permissions,
                "justification": console.CONSOLE_OPERATIONS[op_id],
                "parametres": console.parametres_console(op),
            }
        )
    return {
        "items": items,
        "environnement": get_settings().app_env,
        "limites": {
            "methodes": ["GET"],
            "taille_max_octets": console.TAILLE_MAX_OCTETS,
            "delai_max_secondes": console.DELAI_MAX_SECONDES,
        },
        "avertissement": (
            "Console en lecture seule : seules les opérations GET de la liste revue sont exécutables, "
            "avec vos propres droits. Les champs sensibles sont masqués et aucun corps de réponse n'est conservé."
        ),
    }


@router.post("/console/executer", response_model=IntegrationConsoleResultat)
async def executer_console(
    payload: IntegrationConsoleRequete,
    request: Request,
    actor: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    _ops, index = cat.operations_de(request.app)
    op = index.get(payload.operation_id)
    try:
        if op is None:
            raise console.ConsoleRefus(
                403, "CONSOLE_OPERATION_NON_AUTORISEE", "Hors liste d'autorisation revue de la console."
            )
        resultat = await console.executer(
            request.app,
            op,
            parametres_chemin=payload.parametres_chemin,
            parametres_requete=payload.parametres_requete,
            authorization=request.headers.get("authorization"),
            client_ip=get_client_ip(request),
        )
    except console.ConsoleRefus as exc:
        await record_audit(
            db,
            user=actor,
            action="console_refus",
            entity="integration_operation",
            entity_id=payload.operation_id[:64],
            request=request,
            after={"code": exc.code},
            module_code="core",
        )
        await db.commit()
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}
        ) from exc
    await record_audit(
        db,
        user=actor,
        action="console_execute",
        entity="integration_operation",
        entity_id=op.operation_id[:64],
        request=request,
        after={"statut_http": resultat["statut_http"], "duree_ms": resultat["duree_ms"]},
        module_code="core",
    )
    return {**resultat, "environnement": get_settings().app_env}
