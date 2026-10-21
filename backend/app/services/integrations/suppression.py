"""Suppression définitive des objets du Studio d'intégration API.

Règles :
- une suppression n'est jamais en cascade : tout objet référencé (demandes de droits, versions,
  opérations, destinations, exécutions, alertes) bloque la suppression et l'API renvoie la liste ;
- seul un objet jamais engagé (brouillon / à valider, jamais validé, jamais testé) peut être supprimé ;
  sinon l'alternative est l'archivage ou la suspension, qui conservent l'historique ;
- une opération importée appartient à sa version de spécification : jamais supprimée individuellement ;
- les exécutions et alertes ne sont jamais supprimées ici (preuves de test et traces d'incident) ;
- chaque suppression est journalisée (``audit_logs``) avec l'état supprimé.
"""

from __future__ import annotations

import uuid

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.integrations import (
    IntegrationAlerte,
    IntegrationClient,
    IntegrationClientGrant,
    IntegrationClientGrantEvent,
    IntegrationDestination,
    IntegrationExecution,
    IntegrationFournisseur,
    IntegrationFournisseurOperation,
    IntegrationFournisseurSpec,
)
from app.services.audit_helpers import record_audit
from app.services.integrations import clients as cli
from app.services.integrations import destinations as dst
from app.services.integrations import fournisseurs as frn

ALTERNATIVE_CLIENT = "Archiver l'application : les demandes ouvertes sont closes et l'historique est conservé."
ALTERNATIVE_FOURNISSEUR = (
    "Archiver le fournisseur (ou le suspendre s'il est validé) : versions, opérations, tests et alertes restent consultables."
)
ALTERNATIVE_DESTINATION = (
    "Suspendre la destination (plus aucun test possible) ou l'archiver : l'historique des tests est conservé."
)
ALTERNATIVE_OPERATION = "Archiver l'opération manuelle : elle n'est plus proposée mais reste tracée."
ALTERNATIVE_IMPORTEE = "Importer une nouvelle version de la spécification sans cette opération."


async def _compter(db: AsyncSession, *conditions) -> int:
    return int(await db.scalar(select(func.count()).where(*conditions)) or 0)


def _bilan(conditions: list[str], dependances: list[tuple[str, str, int]], alternative: str) -> dict:
    deps = [{"code": c, "libelle": lib, "nombre": n} for c, lib, n in dependances if n]
    return {
        "supprimable": not conditions and not deps,
        "conditions": conditions,
        "dependances": deps,
        "alternative": alternative,
    }


def _avec_revision(bilan: dict, obj) -> dict:
    return {**bilan, "revision": obj.revision}


def _bloquer(bilan: dict) -> None:
    if bilan["supprimable"]:
        return
    raisons = bilan["conditions"] + [f"{d['libelle']} : {d['nombre']}" for d in bilan["dependances"]]
    raise AppError("Suppression impossible — " + " ; ".join(raisons) + ". " + bilan["alternative"], 409,
                   code="SUPPRESSION_BLOQUEE")


async def _supprimer(db: AsyncSession, obj) -> None:
    await db.delete(obj)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise AppError("Suppression impossible : l'objet vient d'être référencé. Recharger la fiche.", 409,
                       code="SUPPRESSION_BLOQUEE") from exc


# ------------------------------------------------------------------------------ applications clientes


async def dependances_client(db: AsyncSession, client_id: uuid.UUID) -> dict:
    c = await cli._client(db, client_id)
    return _avec_revision(await _bilan_client(db, c), c)


async def _bilan_client(db: AsyncSession, c: IntegrationClient) -> dict:
    conditions = []
    if c.statut != "brouillon":
        conditions.append(f"seule une fiche au statut « brouillon » peut être supprimée (statut actuel : {c.statut})")
    return _bilan(conditions, [
        ("demandes", "Demandes de droits", await _compter(db, IntegrationClientGrant.client_id == c.id)),
        ("evenements", "Décisions tracées", await _compter(db, IntegrationClientGrantEvent.client_id == c.id)),
    ], ALTERNATIVE_CLIENT)


async def supprimer_client(db: AsyncSession, actor: User, client_id: uuid.UUID, revision: int,
                           request: Request | None) -> None:
    c = await cli._client(db, client_id, verrou=True)
    if revision != c.revision:
        raise AppError("La fiche a été modifiée entre-temps : recharger avant de supprimer", 409, code="CONFLIT_REVISION")
    _bloquer(await _bilan_client(db, c))
    avant = cli._etat(c)
    await _supprimer(db, c)
    await record_audit(db, user=actor, action="integration_client_delete", entity="integration_client",
                       entity_id=str(client_id), request=request, before=avant, module_code="core")
    await db.flush()


# ------------------------------------------------------------------------------ fournisseurs


async def dependances_fournisseur(db: AsyncSession, fid: uuid.UUID) -> dict:
    f = await frn._fournisseur(db, fid)
    return _avec_revision(await _bilan_fournisseur(db, f), f)


async def _bilan_fournisseur(db: AsyncSession, f: IntegrationFournisseur) -> dict:
    conditions = []
    if f.statut not in frn.MODIFIABLES:
        conditions.append(f"seul un fournisseur « brouillon » ou « à valider » peut être supprimé (statut actuel : {f.statut})")
    elif f.valide_le is not None:
        conditions.append("ce fournisseur a déjà été validé")
    return _bilan(conditions, [
        ("specifications", "Versions de spécification importées",
         await _compter(db, IntegrationFournisseurSpec.fournisseur_id == f.id)),
        ("operations", "Opérations", await _compter(db, IntegrationFournisseurOperation.fournisseur_id == f.id)),
        ("destinations", "Destinations TEST", await _compter(db, IntegrationDestination.fournisseur_id == f.id)),
        ("executions", "Tests exécutés", await _compter(db, IntegrationExecution.fournisseur_id == f.id)),
        ("alertes", "Alertes", await _compter(db, IntegrationAlerte.fournisseur_id == f.id)),
    ], ALTERNATIVE_FOURNISSEUR)


async def supprimer_fournisseur(db: AsyncSession, actor: User, fid: uuid.UUID, revision: int,
                                request: Request | None) -> None:
    f = await frn._fournisseur(db, fid, verrou=True)
    frn._exiger_revision(f, revision)
    _bloquer(await _bilan_fournisseur(db, f))
    avant = frn._etat(f)
    await _supprimer(db, f)
    await record_audit(db, user=actor, action="integration_fournisseur_delete", entity="integration_fournisseur",
                       entity_id=str(fid), request=request, before=avant, module_code="core")
    await db.flush()


# ------------------------------------------------------------------------------ destinations


async def dependances_destination(db: AsyncSession, did: uuid.UUID) -> dict:
    d = await dst._destination(db, did)
    return _avec_revision(await _bilan_destination(db, d), d)


async def _bilan_destination(db: AsyncSession, d: IntegrationDestination) -> dict:
    conditions = []
    if d.statut not in dst.MODIFIABLES:
        conditions.append(
            f"seule une destination « brouillon » ou « à valider » peut être supprimée (statut actuel : {d.statut})")
    elif d.valide_le is not None:
        conditions.append("cette destination a déjà été approuvée")
    return _bilan(conditions, [
        ("executions", "Tests exécutés", await _compter(db, IntegrationExecution.destination_id == d.id)),
        ("alertes", "Alertes", await _compter(db, IntegrationAlerte.destination_id == d.id)),
    ], ALTERNATIVE_DESTINATION)


async def supprimer_destination(db: AsyncSession, actor: User, did: uuid.UUID, revision: int,
                                request: Request | None) -> None:
    d = await dst._destination(db, did, verrou=True)
    if revision != d.revision:
        raise AppError("La destination a été modifiée entre-temps", 409, code="CONFLIT_REVISION")
    _bloquer(await _bilan_destination(db, d))
    avant = dst._etat(d)
    await _supprimer(db, d)
    await record_audit(db, user=actor, action="integration_destination_delete", entity="integration_destination",
                       entity_id=str(did), request=request, before=avant, module_code="core")
    await db.flush()


# ------------------------------------------------------------------------------ opérations manuelles


async def dependances_operation(db: AsyncSession, fid: uuid.UUID, op_id: uuid.UUID) -> dict:
    f = await frn._fournisseur(db, fid)
    op = await frn._operation(db, fid, op_id)
    return _avec_revision(await _bilan_operation(db, f, op), op)


async def _bilan_operation(db: AsyncSession, f: IntegrationFournisseur, op: IntegrationFournisseurOperation) -> dict:
    if op.origine != "manuelle":
        return _bilan(["opération issue d'une spécification importée : elle appartient à sa version"], [],
                      ALTERNATIVE_IMPORTEE)
    conditions = []
    if f.statut not in frn.MODIFIABLES:
        conditions.append("le fournisseur est validé, suspendu ou archivé : le repasser « à valider » d'abord")
    return _bilan(conditions, [
        ("destinations", "Destinations qui autorisent cette opération",
         await _compter(db, IntegrationDestination.operations.contains([str(op.id)]))),
        ("executions", "Tests exécutés", await _compter(db, IntegrationExecution.operation_id == op.id)),
        ("alertes", "Alertes", await _compter(db, IntegrationAlerte.operation_id == op.id)),
    ], ALTERNATIVE_OPERATION)


async def supprimer_operation(db: AsyncSession, actor: User, fid: uuid.UUID, op_id: uuid.UUID, revision: int,
                              request: Request | None) -> None:
    f = await frn._fournisseur(db, fid, verrou=True)
    op = await frn._operation(db, fid, op_id, verrou=True)
    if revision != op.revision:
        raise AppError("L'opération a été modifiée entre-temps : recharger", 409, code="CONFLIT_REVISION")
    _bloquer(await _bilan_operation(db, f, op))
    trace = {"operation": str(op.id), "methode": op.methode, "chemin": op.chemin, "nom": op.nom}
    await _supprimer(db, op)
    frn._toucher(f, actor)
    await db.flush()
    await frn._audit(db, actor, "integration_fournisseur_operation_delete", f, request, before=trace)
    await db.flush()
