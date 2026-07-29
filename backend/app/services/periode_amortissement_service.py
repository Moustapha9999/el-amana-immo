"""Cycle chronologique des périodes trimestrielles d'amortissement."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models import ExerciceComptable, PeriodeAmortissement, User
from app.models.enums import StatutExercice, StatutPeriodeAmortissement


def date_arrete_trimestre(annee: int, trimestre: int) -> date:
    mois = trimestre * 3
    return date(annee, mois, monthrange(annee, mois)[1])


class PeriodeAmortissementService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_periodes(
        self, annee: int, *, exercice: ExerciceComptable | None = None
    ) -> list[PeriodeAmortissement]:
        exo = exercice
        if exo is None:
            exo_res = await self.db.execute(
                select(ExerciceComptable).where(ExerciceComptable.annee == annee)
            )
            exo = exo_res.scalar_one_or_none()
        if exo is None:
            raise ValidationError(
                f"L'exercice {annee} n'est pas ouvert. Ouvrez-le avant de comptabiliser."
            )

        rows_res = await self.db.execute(
            select(PeriodeAmortissement)
            .where(PeriodeAmortissement.exercice_id == exo.id)
            .order_by(PeriodeAmortissement.trimestre)
        )
        rows = list(rows_res.scalars().all())
        by_quarter = {p.trimestre: p for p in rows}
        for trimestre in range(1, 5):
            if trimestre in by_quarter:
                continue
            row = PeriodeAmortissement(
                exercice_id=exo.id,
                annee=annee,
                trimestre=trimestre,
                code=f"{annee}-Q{trimestre}",
                date_arrete=date_arrete_trimestre(annee, trimestre),
                statut=(
                    StatutPeriodeAmortissement.CLOTUREE
                    if exo.statut == StatutExercice.CLOTURE
                    else (
                        StatutPeriodeAmortissement.OUVERTE
                        if trimestre == 1
                        else StatutPeriodeAmortissement.EN_ATTENTE
                    )
                ),
            )
            self.db.add(row)
            rows.append(row)
        await self.db.flush()
        return sorted(rows, key=lambda p: p.trimestre)

    async def list_periodes(self, annee: int) -> list[PeriodeAmortissement]:
        return await self.ensure_periodes(annee)

    async def assert_validation_autorisee(
        self, annee: int, trimestre: int
    ) -> PeriodeAmortissement:
        rows = await self.ensure_periodes(annee)
        current = next(p for p in rows if p.trimestre == trimestre)
        if current.statut in (
            StatutPeriodeAmortissement.VALIDEE,
            StatutPeriodeAmortissement.CLOTUREE,
        ):
            raise ValidationError(
                f"La période T{trimestre} de l'exercice {annee} est déjà comptabilisée. "
                "Aucun nouveau calcul n'a été effectué."
            )
        if trimestre > 1:
            previous = next(p for p in rows if p.trimestre == trimestre - 1)
            if previous.statut not in (
                StatutPeriodeAmortissement.VALIDEE,
                StatutPeriodeAmortissement.CLOTUREE,
            ):
                raise ValidationError(
                    f"Impossible de comptabiliser la période T{trimestre}. "
                    f"Veuillez d'abord calculer et valider la période T{trimestre - 1}."
                )
        if current.statut == StatutPeriodeAmortissement.EN_ATTENTE:
            current.statut = StatutPeriodeAmortissement.OUVERTE
        return current

    async def enregistrer_validation(
        self,
        *,
        periode: PeriodeAmortissement,
        complete: bool,
        total_dotation: Decimal,
        nb_dotations: int,
        user: User | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        periode.calcule_at = now
        periode.total_dotation = Decimal(periode.total_dotation or 0) + total_dotation
        periode.nb_dotations = int(periode.nb_dotations or 0) + nb_dotations
        if complete:
            periode.statut = StatutPeriodeAmortissement.VALIDEE
            periode.valide_at = now
            periode.valide_by_id = user.id if user else None
            if periode.trimestre < 4:
                rows = await self.ensure_periodes(periode.annee)
                suivant = next(p for p in rows if p.trimestre == periode.trimestre + 1)
                if suivant.statut == StatutPeriodeAmortissement.EN_ATTENTE:
                    suivant.statut = StatutPeriodeAmortissement.OUVERTE
        else:
            periode.statut = StatutPeriodeAmortissement.CALCULEE
        await self.db.flush()

    async def assert_cloture_autorisee(self, annee: int) -> list[PeriodeAmortissement]:
        rows = await self.ensure_periodes(annee)
        t4 = next(p for p in rows if p.trimestre == 4)
        if t4.statut != StatutPeriodeAmortissement.VALIDEE:
            raise ValidationError(
                f"Impossible de clôturer l'exercice {annee} : la période T4 "
                "doit d'abord être calculée, validée et comptabilisée."
            )
        return rows

    async def cloturer_periodes(self, annee: int) -> None:
        rows = await self.ensure_periodes(annee)
        for periode in rows:
            periode.statut = StatutPeriodeAmortissement.CLOTUREE
        await self.db.flush()
