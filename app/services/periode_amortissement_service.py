"""Cycle chronologique des périodes trimestrielles d'amortissement."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models import (
    CategorieImmobilisation,
    ExerciceComptable,
    Immobilisation,
    PeriodeAmortissement,
    PeriodeAmortissementCategorie,
    User,
)
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
        self,
        annee: int,
        trimestre: int,
        categorie_ids: list[UUID] | None = None,
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

        if categorie_ids is None and trimestre > 1:
            previous = next(p for p in rows if p.trimestre == trimestre - 1)
            if previous.statut not in (
                StatutPeriodeAmortissement.VALIDEE,
                StatutPeriodeAmortissement.CLOTUREE,
            ):
                raise ValidationError(
                    f"Impossible de comptabiliser la période T{trimestre}. "
                    f"Veuillez d'abord calculer et valider la période T{trimestre - 1}."
                )

        if categorie_ids is not None:
            requested = set(categorie_ids)
            if not requested:
                raise ValidationError("Sélectionnez au moins une catégorie à comptabiliser.")
            current_details = await self._details(current.id, requested)
            if requested.issubset(
                {
                    row.categorie_id
                    for row in current_details
                    if row.statut
                    in (
                        StatutPeriodeAmortissement.VALIDEE,
                        StatutPeriodeAmortissement.CLOTUREE,
                    )
                }
            ):
                raise ValidationError(
                    f"Les catégories sélectionnées sont déjà comptabilisées pour T{trimestre}."
                )
            if trimestre > 1:
                previous = next(p for p in rows if p.trimestre == trimestre - 1)
                previous_details = await self._details(previous.id, requested)
                validated = {
                    row.categorie_id
                    for row in previous_details
                    if row.statut
                    in (
                        StatutPeriodeAmortissement.VALIDEE,
                        StatutPeriodeAmortissement.CLOTUREE,
                    )
                }
                missing = requested - validated
                if missing:
                    labels = await self._category_labels(missing)
                    raise ValidationError(
                        f"Impossible de comptabiliser T{trimestre} pour : "
                        f"{', '.join(labels)}. Validez d'abord T{trimestre - 1} "
                        "pour ces catégories."
                    )
        if current.statut == StatutPeriodeAmortissement.EN_ATTENTE:
            current.statut = StatutPeriodeAmortissement.OUVERTE
        return current

    async def enregistrer_validation(
        self,
        *,
        periode: PeriodeAmortissement,
        categorie_ids: list[UUID] | None,
        total_dotation: Decimal,
        nb_dotations: int,
        user: User | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        periode.calcule_at = now
        periode.total_dotation = Decimal(periode.total_dotation or 0) + total_dotation
        periode.nb_dotations = int(periode.nb_dotations or 0) + nb_dotations

        all_categories = await self._amortissable_category_ids()
        targets = all_categories if categorie_ids is None else set(categorie_ids)
        details = await self._details(periode.id, targets)
        details_by_category = {row.categorie_id: row for row in details}
        for categorie_id in targets:
            detail = details_by_category.get(categorie_id)
            if detail is None:
                detail = PeriodeAmortissementCategorie(
                    periode_id=periode.id,
                    categorie_id=categorie_id,
                )
                self.db.add(detail)
            detail.statut = StatutPeriodeAmortissement.VALIDEE
            detail.valide_at = now
            detail.valide_by_id = user.id if user else None

        active_categories = await self._active_amortissable_category_ids()
        validated_details = await self._details(periode.id, active_categories)
        validated_categories = {
            row.categorie_id
            for row in validated_details
            if row.statut
            in (
                StatutPeriodeAmortissement.VALIDEE,
                StatutPeriodeAmortissement.CLOTUREE,
            )
        }
        complete = categorie_ids is None or active_categories.issubset(
            validated_categories | targets
        )
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

    async def category_statuses(
        self, periode_ids: set[UUID]
    ) -> dict[UUID, list[PeriodeAmortissementCategorie]]:
        if not periode_ids:
            return {}
        result = await self.db.execute(
            select(PeriodeAmortissementCategorie).where(
                PeriodeAmortissementCategorie.periode_id.in_(periode_ids)
            )
        )
        grouped: dict[UUID, list[PeriodeAmortissementCategorie]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.periode_id, []).append(row)
        return grouped

    async def _details(
        self, periode_id: UUID, categorie_ids: set[UUID]
    ) -> list[PeriodeAmortissementCategorie]:
        if not categorie_ids:
            return []
        result = await self.db.execute(
            select(PeriodeAmortissementCategorie).where(
                PeriodeAmortissementCategorie.periode_id == periode_id,
                PeriodeAmortissementCategorie.categorie_id.in_(categorie_ids),
            )
        )
        return list(result.scalars().all())

    async def _amortissable_category_ids(self) -> set[UUID]:
        result = await self.db.execute(
            select(CategorieImmobilisation.id).where(
                CategorieImmobilisation.amortissable.is_(True),
                CategorieImmobilisation.deleted_at.is_(None),
            )
        )
        return set(result.scalars().all())

    async def _active_amortissable_category_ids(self) -> set[UUID]:
        result = await self.db.execute(
            select(CategorieImmobilisation.id)
            .join(
                Immobilisation,
                Immobilisation.categorie_id == CategorieImmobilisation.id,
            )
            .where(
                CategorieImmobilisation.amortissable.is_(True),
                CategorieImmobilisation.deleted_at.is_(None),
                Immobilisation.deleted_at.is_(None),
            )
            .distinct()
        )
        return set(result.scalars().all())

    async def _category_labels(self, categorie_ids: set[UUID]) -> list[str]:
        result = await self.db.execute(
            select(
                CategorieImmobilisation.id,
                CategorieImmobilisation.code,
                CategorieImmobilisation.famille,
            ).where(CategorieImmobilisation.id.in_(categorie_ids))
        )
        by_id = {
            row.id: row.code or row.famille or str(row.id)
            for row in result.all()
        }
        return [by_id.get(category_id, str(category_id)) for category_id in categorie_ids]

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
        details = await self.category_statuses({p.id for p in rows})
        for period_details in details.values():
            for detail in period_details:
                detail.statut = StatutPeriodeAmortissement.CLOTUREE
        await self.db.flush()
