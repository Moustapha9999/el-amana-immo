"""Règles de calcul BCM courantes : valeur documentée, remplacée par la dernière décision enregistrée."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.data.clientele_bcm_regles import PAR_CODE, REGLES, STATUTS_REGLE, valider_valeur
from app.models import ClienteleBcmRegle
from app.services.clientele.service import Ctx, ClienteleService


class ClienteleBcmReglesService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    async def _table_presente(self) -> bool:
        return bool(await self.db.scalar(text("SELECT to_regclass('public.clientele_bcm_regles') IS NOT NULL")))

    async def courantes(self) -> list[dict]:
        """Règles appliquées au prochain calcul, avec leur dernière décision (ou la valeur documentée)."""
        decisions: dict[str, ClienteleBcmRegle] = {}
        if await self._table_presente():
            R = ClienteleBcmRegle
            for d in (await self.db.scalars(select(R).order_by(R.code, R.created_at))).all():
                decisions[d.code] = d
        out = []
        for r in REGLES:
            d = decisions.get(r["code"])
            out.append({
                "code": r["code"], "libelle": r["libelle"], "explication": r["explication"],
                "valeur": d.valeur if d else r["valeur"], "statut": d.statut if d else r["statut"],
                "origine": f"Décision du {d.created_at:%d/%m/%Y} ({d.decide_par_nom or '—'}) : {d.motif}"
                if d else r["origine"],
                "valeur_defaut": r["valeur"], "decidee": bool(d),
                "decidee_le": d.created_at.isoformat() if d and d.created_at else None,
            })
        return out

    async def lister(self) -> dict:
        self.ctx.exiger("clientele.bcm.view", "clientele.reporting.view")
        categories = (await self.db.execute(text(
            "SELECT coalesce(nullif(trim(categorie_juridique), ''), '(vide)'), count(*) FROM clientele_clients "
            "GROUP BY 1 ORDER BY 2 DESC"))).all()
        gels = (await self.db.execute(text(
            "SELECT coalesce(nullif(trim(statut_gel), ''), '(vide)'), count(*) FROM clientele_kyc "
            "GROUP BY 1 ORDER BY 2 DESC"))).all()
        return {
            "regles": await self.courantes(),
            "historique": await self._historique(),
            "observe": {"categories_juridiques": [{"valeur": v, "nombre": n} for v, n in categories],
                        "statuts_gel": [{"valeur": v, "nombre": n} for v, n in gels]},
            "modifiable": self.ctx.peut("clientele.bcm.valider"),
        }

    async def _historique(self) -> list[dict]:
        if not await self._table_presente():
            return []
        R = ClienteleBcmRegle
        rows = (await self.db.scalars(select(R).order_by(R.created_at.desc()).limit(200))).all()
        return [{"code": d.code, "valeur": d.valeur, "statut": d.statut, "motif": d.motif,
                 "par": d.decide_par_nom, "le": d.created_at.isoformat() if d.created_at else None} for d in rows]

    async def decider(self, code: str, payload: dict) -> dict:
        self.ctx.exiger("clientele.bcm.valider")
        if code not in PAR_CODE:
            raise AppError("Règle inconnue", 404, code="NOT_FOUND")
        if not await self._table_presente():
            raise AppError("Table des règles BCM absente (migration 20261019_clientele_12)", 409,
                           code="MIGRATION_REQUISE")
        statut = (payload.get("statut") or "").upper()
        if statut not in STATUTS_REGLE:
            raise AppError("Statut attendu : CONFIRMEE ou A_VALIDER", 422, code="STATUT_INVALIDE")
        motif = (payload.get("motif") or "").strip()
        if not motif:
            raise AppError("Motif de décision obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        try:
            valeur = valider_valeur(code, payload.get("valeur"))
        except ValueError as e:
            raise AppError(str(e), 422, code="VALEUR_INVALIDE") from e
        avant = next(r for r in await self.courantes() if r["code"] == code)
        self.db.add(ClienteleBcmRegle(
            code=code, valeur=valeur, statut=statut, motif=motif[:2000], decide_par_id=self.ctx.user.id,
            decide_par_nom=self.ctx.user.full_name or self.ctx.user.email))
        await self.db.flush()
        await self.svc.audit("bcm.regle.decider", "clientele_bcm_regle", None,
                             before={"code": code, "valeur": avant["valeur"], "statut": avant["statut"]},
                             after={"code": code, "valeur": valeur, "statut": statut, "motif": motif})
        await self.db.commit()
        return await self.lister()
