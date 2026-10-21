"""Supervision des tests d'API externes (Phase 6) : historique, indicateurs, alertes.

Aucune sonde automatique. Les indicateurs sont calculés sur les exécutions réellement
enregistrées. Une alerte ne déclenche jamais d'appel sortant.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from statistics import median

from fastapi import Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import AuditLog, User
from app.models.integrations import (
    IntegrationAlerte,
    IntegrationDestination,
    IntegrationExecution,
    IntegrationFournisseur,
    IntegrationFournisseurOperation,
)
from app.services.audit_helpers import record_audit
from app.services.integrations.clients import _echapper_like, _noms, _personne
from app.services.integrations.executeur import disponibilite_depuis

P_VIEW = "core.admin.integrations.supervision.view"
P_MANAGE = "core.admin.integrations.supervision.manage"
P_EXPORT = "core.admin.integrations.supervision.export"

RETENTION_JOURS = 90
SEUIL_ECHECS = 3
SEUIL_LATENCE_MS = 5000
SEUIL_TAUX = 0.5
FENETRE_TAUX = 10
NON_TESTEE_JOURS = 7
LIBELLES_STATUT = {
    "succes": "Succès", "http_erreur": "Erreur HTTP", "refuse_securite": "Refus de sécurité",
    "timeout": "Délai dépassé", "trop_volumineux": "Réponse trop volumineuse",
    "dns": "DNS", "tls": "TLS", "redirection_refusee": "Redirection refusée",
    "reponse_invalide": "Réponse invalide", "secret_requis": "Secret requis", "quota": "Quota",
}
TYPES_ALERTE = ("echecs_consecutifs", "taux_erreur", "latence", "non_testee",
                "destination_suspendue", "refus_securite")
NIVEAU_PAR_TYPE = {
    "echecs_consecutifs": "elevee", "taux_erreur": "elevee", "refus_securite": "elevee",
    "latence": "moyenne", "destination_suspendue": "moyenne", "non_testee": "info",
}
REGLES_ALERTE = {
    "echecs_consecutifs": f"{SEUIL_ECHECS} derniers tests en échec réseau ou HTTP sur le même couple destination / opération.",
    "taux_erreur": f"Au moins {int(SEUIL_TAUX * 100)} % d'échecs sur les {FENETRE_TAUX} derniers tests d'une destination.",
    "latence": f"Durée d'un test supérieure ou égale à {SEUIL_LATENCE_MS} ms.",
    "non_testee": f"Destination active sans test depuis {NON_TESTEE_JOURS} jours (ou jamais), constatée à la lecture du tableau de bord.",
    "destination_suspendue": "Destination de test suspendue par un approbateur.",
    "refus_securite": "Test refusé par un contrôle de sécurité (SSRF, hôte, port, méthode).",
}


def _erreur(message: str, code: str, status: int = 404) -> AppError:
    return AppError(message, status, code=code)


def _maintenant() -> datetime:
    return datetime.now(UTC)


async def ouvrir_alerte(db: AsyncSession, type_: str, cle: str, fournisseur_id, destination_id,
                        operation_id, message: str, details: dict) -> IntegrationAlerte:
    q = select(IntegrationAlerte).where(
        IntegrationAlerte.type == type_, IntegrationAlerte.cle_dedup == cle,
        IntegrationAlerte.statut.in_(("nouvelle", "en_cours")),
    )
    existante = (await db.scalars(q)).first()
    if existante:
        existante.occurences += 1
        existante.derniere_le = _maintenant()
        existante.details = {**(existante.details or {}), **details}
        await db.flush()
        return existante
    row = IntegrationAlerte(
        type=type_, cle_dedup=cle, fournisseur_id=fournisseur_id, destination_id=destination_id,
        operation_id=operation_id, message=message[:500], details=details or {},
        derniere_le=_maintenant(),
    )
    db.add(row)
    await db.flush()
    return row


async def evaluer_apres_execution(db: AsyncSession, row: IntegrationExecution) -> None:
    if row.statut in {"http_erreur", "timeout", "tls", "dns", "trop_volumineux"}:
        recents = (await db.scalars(
            select(IntegrationExecution).where(
                IntegrationExecution.operation_id == row.operation_id,
                IntegrationExecution.destination_id == row.destination_id,
            ).order_by(IntegrationExecution.started_at.desc()).limit(SEUIL_ECHECS)
        )).all()
        if len(recents) >= SEUIL_ECHECS and all(
            r.statut in {"http_erreur", "timeout", "tls", "dns", "trop_volumineux"} for r in recents
        ):
            await ouvrir_alerte(
                db, "echecs_consecutifs", f"{row.destination_id}:{row.operation_id}",
                row.fournisseur_id, row.destination_id, row.operation_id,
                f"{SEUIL_ECHECS} échecs consécutifs sur le même test.",
                {"statuts": [r.statut for r in recents]},
            )
    if row.duree_ms and row.duree_ms >= SEUIL_LATENCE_MS:
        await ouvrir_alerte(
            db, "latence", f"{row.destination_id}:{row.operation_id}",
            row.fournisseur_id, row.destination_id, row.operation_id,
            f"Latence {row.duree_ms} ms supérieure au seuil ({SEUIL_LATENCE_MS} ms).",
            {"duree_ms": row.duree_ms},
        )
    fenetre = (await db.scalars(
        select(IntegrationExecution).where(
            IntegrationExecution.destination_id == row.destination_id,
        ).order_by(IntegrationExecution.started_at.desc()).limit(FENETRE_TAUX)
    )).all()
    if len(fenetre) >= FENETRE_TAUX:
        echecs = sum(1 for r in fenetre if r.statut != "succes")
        if echecs / len(fenetre) >= SEUIL_TAUX:
            await ouvrir_alerte(
                db, "taux_erreur", str(row.destination_id),
                row.fournisseur_id, row.destination_id, None,
                f"Taux d'erreur {echecs}/{len(fenetre)} sur les derniers tests.",
                {"echecs": echecs, "total": len(fenetre)},
            )


def _filtre_exec(fournisseur_id=None, destination_id=None, operation_id=None,
                 statut=None, depuis=None, jusqua=None, q=None):
    t = IntegrationExecution
    conds = []
    if q and q.strip():
        motif = f"%{_echapper_like(q.strip())}%"
        conds.append(or_(t.correlation_id.ilike(motif, escape="\\"), t.chemin.ilike(motif, escape="\\"),
                         t.hote.ilike(motif, escape="\\")))
    if fournisseur_id:
        conds.append(t.fournisseur_id == fournisseur_id)
    if destination_id:
        conds.append(t.destination_id == destination_id)
    if operation_id:
        conds.append(t.operation_id == operation_id)
    if statut:
        conds.append(t.statut == statut)
    if depuis:
        conds.append(t.started_at >= depuis)
    if jusqua:
        conds.append(t.started_at <= jusqua)
    return and_(*conds) if conds else True


async def lister_executions(db: AsyncSession, *, page=1, size=25, tri: str = "started_at", ordre: str = "desc",
                            **filtres) -> dict:
    t = IntegrationExecution
    where = _filtre_exec(**filtres)
    total = await db.scalar(select(func.count()).select_from(t).where(where))
    colonne = {"duree_ms": t.duree_ms, "statut": t.statut, "http_status": t.http_status}.get(tri, t.started_at)
    colonne = colonne.asc().nulls_last() if ordre == "asc" else colonne.desc().nulls_last()
    rows = (await db.scalars(
        select(t).where(where).order_by(colonne, t.started_at.desc(), t.id).offset((page - 1) * size).limit(size)
    )).all()
    fournisseurs = await _noms_par_id(db, IntegrationFournisseur, {r.fournisseur_id for r in rows})
    operations = await _noms_par_id(db, IntegrationFournisseurOperation, {r.operation_id for r in rows})
    destinations = await _noms_par_id(db, IntegrationDestination, {r.destination_id for r in rows})
    return {
        "items": [
            {
                "id": r.id, "correlation_id": r.correlation_id, "fournisseur_id": r.fournisseur_id,
                "fournisseur_nom": fournisseurs.get(r.fournisseur_id),
                "operation_id": r.operation_id, "operation_nom": operations.get(r.operation_id),
                "destination_id": r.destination_id, "destination_nom": destinations.get(r.destination_id),
                "environnement": r.environnement,
                "methode": r.methode, "chemin": r.chemin, "hote": r.hote,
                "started_at": r.started_at, "duree_ms": r.duree_ms, "statut": r.statut,
                "http_status": r.http_status, "erreur_categorie": r.erreur_categorie,
            }
            for r in rows
        ],
        "total": int(total or 0), "page": page, "size": size,
        "retention_jours": RETENTION_JOURS,
    }


async def tableau_bord(db: AsyncSession, *, depuis: datetime | None, jusqua: datetime | None,
                       fournisseur_id=None, destination_id=None) -> dict:
    t = IntegrationExecution
    where = _filtre_exec(fournisseur_id=fournisseur_id, destination_id=destination_id,
                         depuis=depuis, jusqua=jusqua)
    rows = (await db.scalars(select(t).where(where).order_by(t.started_at.desc()))).all()
    total = len(rows)
    succes = sum(1 for r in rows if r.statut == "succes")
    echecs = total - succes
    durees = [r.duree_ms for r in rows if r.duree_ms is not None]
    par_categorie: dict[str, int] = {}
    for r in rows:
        cle = r.erreur_categorie or r.statut
        par_categorie[cle] = par_categorie.get(cle, 0) + 1
    par_jour: dict[str, list] = {}
    par_fourn: dict[uuid.UUID, list[int]] = {}
    for r in rows:
        jour = (r.started_at.astimezone(UTC) if r.started_at.tzinfo else r.started_at).date().isoformat()
        cumul = par_jour.setdefault(jour, [0, 0, []])
        cumul[0] += 1
        cumul[1] += r.statut == "succes"
        if r.duree_ms is not None:
            cumul[2].append(r.duree_ms)
        f = par_fourn.setdefault(r.fournisseur_id, [0, 0])
        f[0] += 1
        f[1] += r.statut == "succes"
    noms_fourn = await _noms_par_id(db, IntegrationFournisseur, set(par_fourn))
    series = [
        {"jour": j, "total": c[0], "succes": c[1], "echecs": c[0] - c[1],
         "taux_succes": round(c[1] / c[0], 4) if c[0] else None,
         "latence_moyenne_ms": int(sum(c[2]) / len(c[2])) if c[2] else None}
        for j, c in sorted(par_jour.items())
    ]
    par_fournisseur = sorted(
        ({"fournisseur_id": fid, "nom": noms_fourn.get(fid), "total": c[0], "succes": c[1], "echecs": c[0] - c[1]}
         for fid, c in par_fourn.items()),
        key=lambda x: -x["total"],
    )
    dernier = rows[0] if rows else None
    dernier_ok = next((r for r in rows if r.statut == "succes"), None)
    dernier_ko = next((r for r in rows if r.statut != "succes"), None)

    dest_q = select(IntegrationDestination).where(IntegrationDestination.statut != "archivee")
    if fournisseur_id:
        dest_q = dest_q.where(IntegrationDestination.fournisseur_id == fournisseur_id)
    destinations = (await db.scalars(dest_q)).all()
    sans_mesure = []
    cutoff = _maintenant() - timedelta(days=NON_TESTEE_JOURS)
    for d in destinations:
        last = next((r for r in rows if r.destination_id == d.id), None)
        if last is None:
            sans_mesure.append({"id": d.id, "nom": d.nom, "statut": d.statut, "disponibilite": "inconnue"})
            if d.statut == "active":
                await ouvrir_alerte(
                    db, "non_testee", str(d.id), d.fournisseur_id, d.id, None,
                    f"Destination « {d.nom} » sans test depuis {NON_TESTEE_JOURS} jours (ou jamais).",
                    {},
                )
        elif last.started_at.replace(tzinfo=last.started_at.tzinfo or UTC) < cutoff and d.statut == "active":
            sans_mesure.append({"id": d.id, "nom": d.nom, "statut": d.statut, "disponibilite": "inconnue"})
    suspendues = [
        {"id": d.id, "nom": d.nom, "statut": d.statut}
        for d in destinations if d.statut == "suspendue"
    ]
    periode = {
        "depuis": depuis.isoformat() if depuis else None,
        "jusqua": jusqua.isoformat() if jusqua else None,
        "denominateur": "exécutions enregistrées sur la période",
    }
    return {
        "periode": periode,
        "total": total,
        "succes": succes,
        "echecs": echecs,
        "taux_succes": None if total == 0 else round(succes / total, 4),
        "taux_libelle": "Aucune donnée" if total == 0 else f"{succes} / {total}",
        "latence_moyenne_ms": None if not durees else int(sum(durees) / len(durees)),
        "latence_mediane_ms": None if not durees else int(median(durees)),
        "erreurs": [{"categorie": k, "nombre": v} for k, v in sorted(par_categorie.items())],
        "series": series,
        "par_fournisseur": par_fournisseur,
        "dernier": _resume_exec(dernier),
        "dernier_succes": _resume_exec(dernier_ok),
        "dernier_echec": _resume_exec(dernier_ko),
        "sans_mesure": sans_mesure,
        "destinations_suspendues": suspendues,
        "disponibilite": disponibilite_depuis(dernier.statut, dernier.started_at) if dernier else "inconnue",
        "retention_jours": RETENTION_JOURS,
        "sondes_automatiques": False,
    }


def _resume_exec(r: IntegrationExecution | None) -> dict | None:
    if r is None:
        return None
    return {
        "id": r.id, "correlation_id": r.correlation_id, "statut": r.statut,
        "http_status": r.http_status, "duree_ms": r.duree_ms, "started_at": r.started_at,
        "methode": r.methode, "chemin": r.chemin,
    }


async def _noms_par_id(db: AsyncSession, modele, ids: set) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = (await db.execute(select(modele.id, modele.nom).where(modele.id.in_(ids)))).all()
    return {r.id: r.nom for r in rows}


async def lister_alertes(db: AsyncSession, *, statut=None, type_=None, niveau=None,
                         depuis=None, jusqua=None, fournisseur_id=None, q=None, page=1, size=25) -> dict:
    t = IntegrationAlerte
    conds = []
    if fournisseur_id:
        conds.append(t.fournisseur_id == fournisseur_id)
    if q and q.strip():
        conds.append(t.message.ilike(f"%{_echapper_like(q.strip())}%", escape="\\"))
    compteurs = {s: 0 for s in ("nouvelle", "en_cours", "resolue", "ignoree")}
    for s, n in (await db.execute(
        select(t.statut, func.count()).where(and_(*conds) if conds else True).group_by(t.statut)
    )).all():
        compteurs[s] = int(n)
    if statut:
        conds.append(t.statut == statut)
    if type_:
        conds.append(t.type == type_)
    if niveau:
        conds.append(t.type.in_([k for k, v in NIVEAU_PAR_TYPE.items() if v == niveau] or [""]))
    if depuis:
        conds.append(t.derniere_le >= depuis)
    if jusqua:
        conds.append(t.derniere_le <= jusqua)
    where = and_(*conds) if conds else True
    total = await db.scalar(select(func.count()).select_from(t).where(where))
    rows = (await db.scalars(
        select(t).where(where).order_by(t.derniere_le.desc(), t.id).offset((page - 1) * size).limit(size)
    )).all()
    fournisseurs = await _noms_par_id(db, IntegrationFournisseur, {r.fournisseur_id for r in rows})
    destinations = await _noms_par_id(db, IntegrationDestination, {r.destination_id for r in rows})
    operations = await _noms_par_id(db, IntegrationFournisseurOperation, {r.operation_id for r in rows})
    noms = await _noms(db, {r.resolue_par_id for r in rows})
    return {
        "items": [
            {
                "id": r.id, "type": r.type, "statut": r.statut, "message": r.message,
                "niveau": NIVEAU_PAR_TYPE.get(r.type, "info"), "regle": REGLES_ALERTE.get(r.type),
                "occurences": r.occurences, "fournisseur_id": r.fournisseur_id,
                "fournisseur_nom": fournisseurs.get(r.fournisseur_id),
                "destination_id": r.destination_id, "destination_nom": destinations.get(r.destination_id),
                "operation_id": r.operation_id, "operation_nom": operations.get(r.operation_id),
                "details": r.details, "derniere_le": r.derniere_le, "created_at": r.created_at,
                "resolue_le": r.resolue_le, "resolue_par": _personne(noms, r.resolue_par_id),
                "transitions": sorted(TRANSITIONS_ALERTE.get(r.statut, ())),
            }
            for r in rows
        ],
        "total": int(total or 0), "page": page, "size": size,
        "compteurs": compteurs,
    }


TRANSITIONS_ALERTE: dict[str, frozenset[str]] = {
    "nouvelle": frozenset({"en_cours", "resolue", "ignoree"}),
    "en_cours": frozenset({"resolue", "ignoree"}),
    "resolue": frozenset({"nouvelle"}),
    "ignoree": frozenset({"nouvelle"}),
}
LIBELLES_ALERTE = {"nouvelle": "Nouvelle", "en_cours": "Prise en charge", "resolue": "Résolue", "ignoree": "Ignorée"}


async def changer_alerte(db: AsyncSession, actor: User, aid: uuid.UUID, statut: str,
                         request: Request | None) -> dict:
    if statut not in TRANSITIONS_ALERTE:
        raise _erreur("Statut d'alerte invalide", "STATUT_INVALIDE", 422)
    row = (await db.scalars(select(IntegrationAlerte).where(IntegrationAlerte.id == aid).with_for_update())).first()
    if row is None:
        raise _erreur("Alerte introuvable", "ALERTE_INTROUVABLE", 404)
    if statut not in TRANSITIONS_ALERTE.get(row.statut, frozenset()):
        raise _erreur(
            f"Transition interdite : {LIBELLES_ALERTE[row.statut]} → {LIBELLES_ALERTE[statut]}",
            "TRANSITION_INTERDITE", 409,
        )
    if statut == "nouvelle":
        ouverte = await db.scalar(select(IntegrationAlerte.id).where(
            IntegrationAlerte.type == row.type, IntegrationAlerte.cle_dedup == row.cle_dedup,
            IntegrationAlerte.statut.in_(("nouvelle", "en_cours")), IntegrationAlerte.id != row.id,
        ).limit(1))
        if ouverte:
            raise _erreur("Une alerte identique est déjà ouverte : traiter celle-ci plutôt que rouvrir l'ancienne",
                          "ALERTE_DEJA_OUVERTE", 409)
    avant = {"statut": row.statut}
    row.statut = statut
    if statut in ("resolue", "ignoree"):
        row.resolue_par_id, row.resolue_le = actor.id, _maintenant()
    elif statut == "nouvelle":
        row.resolue_par_id, row.resolue_le = None, None
    await db.flush()
    await record_audit(
        db, user=actor, action="integration_alerte_statut", entity="integration_alerte",
        entity_id=str(row.id), request=request, before=avant, after={"statut": statut},
        module_code="core",
    )
    return {
        "id": row.id, "type": row.type, "statut": row.statut, "message": row.message,
        "occurences": row.occurences, "derniere_le": row.derniere_le, "resolue_le": row.resolue_le,
        "transitions": sorted(TRANSITIONS_ALERTE.get(row.statut, ())),
    }


async def historique_alerte(db: AsyncSession, aid: uuid.UUID) -> dict:
    if await db.get(IntegrationAlerte, aid) is None:
        raise _erreur("Alerte introuvable", "ALERTE_INTROUVABLE", 404)
    a = AuditLog
    rows = (await db.scalars(
        select(a).where(a.entity == "integration_alerte", a.entity_id == str(aid))
        .order_by(a.created_at.desc(), a.id).limit(100)
    )).all()
    noms = await _noms(db, {r.user_id for r in rows})
    return {"items": [
        {
            "id": r.id, "acteur": _personne(noms, r.user_id), "created_at": r.created_at,
            "avant": LIBELLES_ALERTE.get((r.before_data or {}).get("statut"), (r.before_data or {}).get("statut")),
            "apres": LIBELLES_ALERTE.get((r.after_data or {}).get("statut"), (r.after_data or {}).get("statut")),
        }
        for r in rows
    ]}


def _csv_cellule(v) -> str:
    s = "" if v is None else str(v)
    if s[:1] in ("=", "+", "-", "@"):
        s = "'" + s
    return s.replace("\r", " ").replace("\n", " ")


async def exporter_csv(db: AsyncSession, actor: User, request: Request | None, **filtres) -> tuple[str, bytes]:
    data = await lister_executions(db, page=1, size=500, **filtres)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["correlation", "debut", "duree_ms", "statut", "http", "methode", "chemin", "hote", "categorie",
                "fournisseur", "operation", "destination", "environnement"])
    for r in data["items"]:
        w.writerow([
            _csv_cellule(r["correlation_id"]), _csv_cellule(r["started_at"]),
            _csv_cellule(r["duree_ms"]), _csv_cellule(r["statut"]),
            _csv_cellule(r["http_status"]), _csv_cellule(r["methode"]),
            _csv_cellule(r["chemin"]), _csv_cellule(r["hote"]),
            _csv_cellule(r["erreur_categorie"]), _csv_cellule(r["fournisseur_nom"]),
            _csv_cellule(r["operation_nom"]), _csv_cellule(r["destination_nom"]),
            _csv_cellule(r["environnement"]),
        ])
    await record_audit(
        db, user=actor, action="integration_supervision_export", entity="integration_execution",
        entity_id="export", request=request,
        after={"lignes": len(data["items"]), "total": data["total"],
               "filtres": {k: str(v) for k, v in filtres.items() if v}},
        module_code="core",
    )
    nom = f"supervision-integrations-{_maintenant().strftime('%Y%m%d')}.csv"
    return nom, buf.getvalue().encode("utf-8-sig")
