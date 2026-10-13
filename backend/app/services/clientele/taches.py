"""Classement de masse SCORE en tâche de fond, suivie en base.

La progression affichée provient uniquement de ``clientele_classif_taches`` (clients réellement
traités / total du périmètre). Le traitement réutilise ``traiter_paquet_moteur`` : mêmes règles,
mêmes protections (décisions manuelles et classes de fichier préservées, réexamen si écart).
Une seule tâche active à la fois ; une tâche interrompue (redémarrage) reprend après sa dernière racine.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.core.exceptions import AppError, NotFoundError
from app.db.session import AsyncSessionLocal
from app.models import ClienteleClassifTache, ClienteleClient, ClienteleSituation, User
from app.services.clientele.classification import (
    ClienteleClassificationService,
    autorisation_classement_masse,
    exiger_classement_masse_autorise,
)
from app.services.clientele.service import ClienteleService, Ctx, maintenant
from app.services.permission_service import load_user_permission_codes

log = logging.getLogger(__name__)

ACTIFS = ("EN_ATTENTE", "EN_COURS")
REPRENABLES = ("INTERROMPU", "ECHEC")
POPULATIONS = {"TOUS": None, "PP": "PP", "PM": "PM"}
MAX_ERREURS_CONSERVEES = 200
# Paquets plus petits que le classement synchrone : progression rafraîchie toutes les quelques secondes.
TAILLE_PAQUET_TACHE = 100
# Sans nouvelle de la tâche pendant ce délai (et absente de ce processus) : considérée interrompue.
DELAI_INACTIVITE = timedelta(minutes=2)

_EN_COURS: dict[uuid.UUID, asyncio.Task] = {}


def tache_dict(t: ClienteleClassifTache) -> dict:
    bilan = dict(t.bilan or {})
    classes = bilan.get("ECRIT", 0) + bilan.get("INCHANGE", 0)
    preserves = bilan.get("MANUEL_PRESERVE", 0) + bilan.get("FICHIER_PRESERVE", 0)
    total = max(t.total or 0, t.traites or 0)
    return {
        "id": str(t.id), "statut": t.statut, "population": t.profil or "TOUS", "code_agence": t.code_agence,
        "motif": t.motif, "total": total, "traites": t.traites or 0,
        "pourcentage": round((t.traites or 0) * 100 / total, 1) if total else (100.0 if t.fin else 0.0),
        "bilan": bilan,
        "resume": {"classes": classes, "preserves": preserves,
                   "non_classes": bilan.get("NON_ADMISSIBLE", 0), "erreurs": bilan.get("ERREUR", 0)},
        "erreurs": list(t.erreurs or [])[:20], "message": t.message,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "debut": t.debut.isoformat() if t.debut else None, "fin": t.fin.isoformat() if t.fin else None,
        "maj_le": t.maj_le.isoformat() if t.maj_le else None,
        "reprenable": t.statut in REPRENABLES,
    }


class ClienteleTacheService:
    def __init__(self, db, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    async def _marquer_inactives(self) -> None:
        limite = maintenant() - DELAI_INACTIVITE
        for t in (await self.db.scalars(select(ClienteleClassifTache).where(
                ClienteleClassifTache.statut.in_(ACTIFS)))).all():
            vu = t.maj_le or t.created_at
            if t.id not in _EN_COURS and (vu is None or vu < limite):
                t.statut = "INTERROMPU"
                t.message = ("Traitement interrompu (redémarrage du serveur). Les clients déjà traités sont "
                             "enregistrés ; « Reprendre » continue après le dernier client traité.")
        await self.db.flush()

    async def _active(self) -> ClienteleClassifTache | None:
        return await self.db.scalar(select(ClienteleClassifTache).where(
            ClienteleClassifTache.statut.in_(ACTIFS)).order_by(ClienteleClassifTache.created_at.desc()).limit(1))

    async def perimetre(self) -> dict:
        self.ctx.exiger("clientele.classif.view")
        rows = (await self.db.execute(
            select(ClienteleSituation.profil_derive, func.count())
            .select_from(ClienteleClient)
            .join(ClienteleSituation, ClienteleSituation.racine_client == ClienteleClient.racine_client,
                  isouter=True)
            .group_by(ClienteleSituation.profil_derive))).all()
        par = {(p or "NON_IDENTIFIE"): int(n) for p, n in rows}
        return {"TOUS": sum(par.values()), "PP": par.get("PP", 0), "PM": par.get("PM", 0),
                "NON_IDENTIFIE": par.get("NON_IDENTIFIE", 0)}

    async def courante(self) -> dict | None:
        self.ctx.exiger("clientele.classif.view")
        await self._marquer_inactives()
        t = await self._active() or await self.db.scalar(
            select(ClienteleClassifTache).order_by(ClienteleClassifTache.created_at.desc()).limit(1))
        return tache_dict(t) if t else None

    async def detail(self, tid: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.classif.view")
        await self._marquer_inactives()
        t = await self.db.get(ClienteleClassifTache, tid)
        if not t:
            raise NotFoundError("Tâche de classification")
        return tache_dict(t)

    async def _exiger_aucune_active(self) -> None:
        await self._marquer_inactives()
        if await self._active():
            raise AppError("Une classification est déjà en cours. Attendez sa fin avant d’en lancer une autre.",
                           409, code="TACHE_EN_COURS")

    def autorisation(self) -> dict:
        self.ctx.exiger("clientele.classif.view")
        return autorisation_classement_masse()

    async def lancer(self, payload: dict) -> dict:
        self.ctx.exiger("clientele.classif.execute")
        validation = exiger_classement_masse_autorise()
        motif = (payload.get("motif") or "").strip()
        if not motif:
            raise AppError("Motif de classement obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        population = (payload.get("population") or "TOUS").strip().upper()
        if population not in POPULATIONS:
            raise AppError("Population attendue : TOUS, PP ou PM", 422, code="POPULATION_INVALIDE")
        filtres = {"profil": POPULATIONS[population], "code_agence": (payload.get("code_agence") or "").strip() or None}
        await self._exiger_aucune_active()
        q, filtres = ClienteleClassificationService(self.db, self.ctx)._perimetre_masse(filtres)
        total = int(await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0)
        t = ClienteleClassifTache(statut="EN_ATTENTE", profil=filtres["profil"], code_agence=filtres["code_agence"],
                                  motif=motif[:2000], total=total, traites=0, bilan={}, erreurs=[],
                                  created_by_id=self.ctx.user.id, created_at=maintenant(), maj_le=maintenant())
        self.db.add(t)
        await self.db.flush()
        await self.svc.audit("clientele.classif.tache.lancer", "clientele_classif_tache", t.id,
                             after={"population": population, **filtres, "total": total, "motif": motif,
                                    "validation": validation})
        await self.db.commit()
        demarrer(t.id, self.ctx.user.id)
        return tache_dict(t)

    async def reprendre(self, tid: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.classif.execute")
        exiger_classement_masse_autorise()
        await self._exiger_aucune_active()
        t = await self.db.get(ClienteleClassifTache, tid)
        if not t:
            raise NotFoundError("Tâche de classification")
        if t.statut not in REPRENABLES:
            raise AppError("Seule une classification interrompue ou en échec peut être reprise.", 409,
                           code="TACHE_NON_REPRENABLE")
        t.statut, t.message, t.fin, t.maj_le = "EN_ATTENTE", None, None, maintenant()
        await self.svc.audit("clientele.classif.tache.reprendre", "clientele_classif_tache", t.id,
                             after={"curseur": t.curseur, "traites": t.traites})
        await self.db.commit()
        demarrer(t.id, self.ctx.user.id)
        return tache_dict(t)


def demarrer(tid: uuid.UUID, user_id: uuid.UUID) -> None:
    tache = asyncio.create_task(_executer(tid, user_id))
    _EN_COURS[tid] = tache
    tache.add_done_callback(lambda _t: _EN_COURS.pop(tid, None))


async def _terminer(tid: uuid.UUID, statut: str, message: str | None) -> None:
    async with AsyncSessionLocal() as db:
        t = await db.get(ClienteleClassifTache, tid)
        if t and t.statut in ACTIFS:
            t.statut, t.message, t.maj_le = statut, message, maintenant()
            await db.commit()


async def _executer(tid: uuid.UUID, user_id: uuid.UUID) -> None:
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            t = await db.get(ClienteleClassifTache, tid)
            if not user or not t:
                return
            ctx = Ctx(user=user, permissions=set(await load_user_permission_codes(db, user)))
            filtres = {"profil": t.profil, "code_agence": t.code_agence}
            t.statut, t.debut, t.maj_le = "EN_COURS", t.debut or maintenant(), maintenant()
            await db.commit()
        while True:
            async with AsyncSessionLocal() as db:
                classif = ClienteleClassificationService(db, ctx)
                q, filtres = classif._perimetre_masse(filtres)
                t = await db.get(ClienteleClassifTache, tid)
                if not t or t.statut != "EN_COURS":
                    return
                if not autorisation_classement_masse()["actif"]:
                    t.statut, t.maj_le = "INTERROMPU", maintenant()
                    t.message = ("Classement de masse suspendu côté serveur pendant le traitement. Les clients "
                                 "déjà traités sont enregistrés ; reprise possible après réactivation.")
                    await db.commit()
                    return
                racines = list((await db.scalars(
                    q.where(ClienteleClient.racine_client > (t.curseur or "")).order_by(ClienteleClient.racine_client)
                    .limit(TAILLE_PAQUET_TACHE))).all())
                if not racines:
                    erreurs = (t.bilan or {}).get("ERREUR", 0)
                    t.statut = "TERMINE_ERREURS" if erreurs else "TERMINE"
                    t.total = max(t.total or 0, t.traites or 0)
                    t.fin = t.maj_le = maintenant()
                    await classif.svc.audit("clientele.classif.tache.fin", "clientele_classif_tache", t.id,
                                            after={"statut": t.statut, "traites": t.traites, **(t.bilan or {})})
                    await db.commit()
                    return
                bilan, erreurs = await classif.traiter_paquet_moteur(racines, t.motif, filtres, isoler_erreurs=True)
                cumul = dict(t.bilan or {})
                for k, v in bilan.items():
                    cumul[k] = cumul.get(k, 0) + v
                t.bilan = cumul
                t.erreurs = (list(t.erreurs or []) + erreurs)[:MAX_ERREURS_CONSERVEES]
                t.traites = (t.traites or 0) + len(racines)
                t.curseur = racines[-1]
                t.maj_le = maintenant()
                await db.commit()
            await asyncio.sleep(0)
    except asyncio.CancelledError:
        await asyncio.shield(_terminer(tid, "INTERROMPU", "Traitement interrompu (arrêt du serveur). "
                                       "« Reprendre » continue après le dernier client traité."))
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("Classement de masse SCORE : tâche %s en échec", tid)
        await _terminer(tid, "ECHEC", f"Erreur technique ({exc.__class__.__name__}). Les clients déjà traités "
                                      "sont enregistrés ; « Reprendre » continue après le dernier client traité.")
