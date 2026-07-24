from datetime import date
from decimal import Decimal

from uuid import UUID



from sqlalchemy import func, select

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload



from app.core.exceptions import NotFoundError
from app.models import Amortissement, CategorieImmobilisation, EcritureComptable, Immobilisation, ParametrageAmortissement
from app.models.enums import StatutImmobilisation
from app.repositories.base import BaseRepository
from app.schemas.immobilisation import ImmobilisationCreate, ImmobilisationUpdate

from app.services.immobilisation_defaults import (
    apply_categorie_defaults,
    apply_update_fields,
    load_categorie,
    prepare_create,
    validate_immobilisation,
)
from app.services.amortissement_service import AmortissementService

__all__ = ["AmortissementCalculator", "AmortissementService", "DashboardService", "ImmobilisationService", "ParametrageService"]





class AmortissementCalculator:

    @staticmethod

    def dotation_lineaire(valeur_brute: Decimal, valeur_residuelle: Decimal, duree_mois: int) -> Decimal:

        if duree_mois <= 0:

            return Decimal("0")

        base = valeur_brute - valeur_residuelle

        return (base / Decimal(duree_mois)).quantize(Decimal("0.01"))





class ImmobilisationService:

    entity_label = "Immobilisation"



    def __init__(self, db: AsyncSession):

        self.db = db

        self.repo = BaseRepository(db, Immobilisation)



    def _base_query(self):

        return select(Immobilisation).options(selectinload(Immobilisation.categorie))



    async def list(self, page: int, size: int, search: str | None = None) -> tuple[list[Immobilisation], int]:

        items, total = await self.repo.list(page, size, search, search_columns=("designation", "code_inventaire"))

        if not items:

            return items, total

        ids = [i.id for i in items]

        result = await self.db.execute(self._base_query().where(Immobilisation.id.in_(ids)))

        loaded = {i.id: i for i in result.scalars().all()}

        return [loaded.get(i.id, i) for i in items], total



    async def get(self, item_id: UUID) -> Immobilisation:

        result = await self.db.execute(

            self._base_query().where(Immobilisation.id == item_id, Immobilisation.deleted_at.is_(None))

        )

        item = result.scalar_one_or_none()

        if item is None:

            raise NotFoundError(self.entity_label, str(item_id))

        return item



    async def create(self, payload: ImmobilisationCreate) -> Immobilisation:

        categorie = await load_categorie(self.db, payload.categorie_id)

        assert categorie is not None

        data = prepare_create(payload, categorie)

        item = Immobilisation(**data)

        apply_categorie_defaults(item, categorie, override_comptes=not any([payload.compte_immobilisation]))

        validate_immobilisation(item, categorie)

        item.qr_code_data = f"IMMO:{item.code_inventaire}"

        item.barcode_data = item.code_inventaire

        await self.repo.add(item)
        # Recharger avec la relation categorie (évite MissingGreenlet sur ImmobilisationRead)
        return await self.get(item.id)



    async def update(self, item_id: UUID, payload: ImmobilisationUpdate) -> Immobilisation:

        item = await self.get(item_id)

        categorie = item.categorie

        if payload.categorie_id is not None:

            categorie = await load_categorie(self.db, payload.categorie_id)

            item.categorie_id = payload.categorie_id

        apply_update_fields(item, payload)

        if categorie is not None:

            apply_categorie_defaults(item, categorie, override_comptes=False)

        validate_immobilisation(item, categorie)

        await self.db.flush()

        await self.db.refresh(item, attribute_names=["categorie"])

        return item



    async def soft_delete(self, item_id: UUID) -> None:

        item = await self.get(item_id)

        await self.repo.delete_soft(item)





class ParametrageService:

    def __init__(self, db: AsyncSession):

        self.db = db



    async def get_or_create(self) -> ParametrageAmortissement:

        result = await self.db.execute(select(ParametrageAmortissement).limit(1))

        row = result.scalar_one_or_none()

        if row is None:

            row = ParametrageAmortissement()

            self.db.add(row)

            await self.db.flush()

        return row



    async def update(self, data: dict) -> ParametrageAmortissement:

        row = await self.get_or_create()

        for key, value in data.items():

            if value is not None:

                setattr(row, key, value)

        await self.db.flush()

        return row





class DashboardService:

    STATUT_LABELS = {
        "brouillon": "Brouillon",
        "en_cours_acquisition": "En cours d'acquisition",
        "en_service": "En service",
        "suspendue": "Suspendue",
        "cedee": "Cédée",
        "mise_au_rebut": "Mise au rebut",
        "transferee": "Transférée",
        "reclassee": "Reclassée",
        "archivee": "Archivée",
        "cession": "Cession",
        "rebut": "Rebut",
    }

    MOIS_NOMS = ["", "Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Aoû", "Sep", "Oct", "Nov", "Déc"]

    def __init__(self, db: AsyncSession):
        self.db = db

    def _immo_ids_select(
        self,
        statut: str | None,
        famille: str | None,
        *,
        apply_statut: bool,
        apply_famille: bool,
    ):
        stmt = select(Immobilisation.id).where(Immobilisation.deleted_at.is_(None))
        if apply_statut and statut:
            stmt = stmt.where(Immobilisation.statut == StatutImmobilisation(statut))
        if apply_famille and famille:
            stmt = stmt.join(
                CategorieImmobilisation,
                Immobilisation.categorie_id == CategorieImmobilisation.id,
            ).where(CategorieImmobilisation.famille == famille)
        return stmt

    async def _sum_valeur_brute(self, immo_ids_stmt) -> float:
        q = select(func.coalesce(func.sum(Immobilisation.valeur_brute), 0)).where(
            Immobilisation.deleted_at.is_(None),
            Immobilisation.id.in_(immo_ids_stmt),
        )
        result = await self.db.execute(q)
        return float(result.scalar_one())

    async def _sum_cumul_amort(self, immo_ids_stmt, periode_max: str | None = None) -> float:
        cumul_q = select(
            Amortissement.immobilisation_id,
            func.max(Amortissement.cumul).label("cumul"),
        ).where(
            Amortissement.valide.is_(True),
            Amortissement.annule.is_(False),
            Amortissement.immobilisation_id.in_(immo_ids_stmt),
        )
        if periode_max:
            cumul_q = cumul_q.where(Amortissement.periode <= periode_max)
        cumul_subq = cumul_q.group_by(Amortissement.immobilisation_id).subquery()
        result = await self.db.execute(select(func.coalesce(func.sum(cumul_subq.c.cumul), 0)))
        return float(result.scalar_one())

    async def kpi(
        self,
        statut: str | None = None,
        famille: str | None = None,
        mois: int | None = None,
    ) -> dict[str, float | int]:
        today = date.today()
        year_start = date(today.year, 1, 1)
        immo_ids = self._immo_ids_select(statut, famille, apply_statut=True, apply_famille=True)

        total = await self.db.execute(
            select(func.count()).select_from(Immobilisation).where(
                Immobilisation.deleted_at.is_(None),
                Immobilisation.id.in_(immo_ids),
            )
        )
        valeur_brute = await self._sum_valeur_brute(immo_ids)
        cumul_amort = await self._sum_cumul_amort(immo_ids)

        dotation_q = select(func.coalesce(func.sum(EcritureComptable.montant), 0)).where(
            EcritureComptable.compte_debit.like("681%"),
            EcritureComptable.date_ecriture >= year_start,
            EcritureComptable.date_ecriture <= today,
        )
        if statut or famille:
            dotation_q = dotation_q.where(EcritureComptable.immobilisation_id.in_(immo_ids))
        if mois:
            from sqlalchemy import extract

            dotation_q = dotation_q.where(extract("month", EcritureComptable.date_ecriture) == mois)

        dotation = await self.db.execute(dotation_q)

        return {
            "nombre_immobilisations": int(total.scalar_one()),
            "valeur_brute_totale": valeur_brute,
            "vnc_totale": max(0.0, valeur_brute - cumul_amort),
            "dotation_periode": float(dotation.scalar_one()),
            "annee_reference": today.year,
        }

    async def charts(
        self,
        statut: str | None = None,
        famille: str | None = None,
        mois: int | None = None,
    ) -> dict:
        from sqlalchemy import extract

        today = date.today()
        year_start = date(today.year, 1, 1)
        year = today.year

        immo_ids_full = self._immo_ids_select(statut, famille, apply_statut=True, apply_famille=True)
        immo_ids_for_statut = self._immo_ids_select(statut, famille, apply_statut=False, apply_famille=True)
        immo_ids_for_famille = self._immo_ids_select(statut, famille, apply_statut=True, apply_famille=False)

        statut_rows = await self.db.execute(
            select(Immobilisation.statut, func.count())
            .where(
                Immobilisation.deleted_at.is_(None),
                Immobilisation.id.in_(immo_ids_for_statut),
            )
            .group_by(Immobilisation.statut)
        )
        par_statut = [
            {
                "label": self.STATUT_LABELS.get(row[0].value, row[0].value),
                "value": float(row[1]),
                "key": row[0].value,
            }
            for row in statut_rows.all()
            if int(row[1]) > 0
        ]

        famille_rows = await self.db.execute(
            select(CategorieImmobilisation.famille, func.coalesce(func.sum(Immobilisation.valeur_brute), 0))
            .join(Immobilisation, Immobilisation.categorie_id == CategorieImmobilisation.id)
            .where(
                Immobilisation.deleted_at.is_(None),
                Immobilisation.id.in_(immo_ids_for_famille),
            )
            .group_by(CategorieImmobilisation.famille)
            .order_by(func.sum(Immobilisation.valeur_brute).desc())
            .limit(8)
        )
        par_famille = [
            {"label": row[0], "value": float(row[1]), "key": row[0]}
            for row in famille_rows.all()
            if float(row[1]) > 0
        ]

        dotation_base = select(
            extract("month", EcritureComptable.date_ecriture),
            func.coalesce(func.sum(EcritureComptable.montant), 0),
        ).where(
            EcritureComptable.compte_debit.like("681%"),
            EcritureComptable.date_ecriture >= year_start,
            EcritureComptable.date_ecriture <= today,
        )
        if statut or famille:
            dotation_base = dotation_base.where(EcritureComptable.immobilisation_id.in_(immo_ids_full))
        dotation_base = dotation_base.group_by(extract("month", EcritureComptable.date_ecriture)).order_by(
            extract("month", EcritureComptable.date_ecriture)
        )
        mois_rows = await self.db.execute(dotation_base)
        by_month = {int(r[0]): float(r[1]) for r in mois_rows.all()}
        dotations_mensuelles = [
            {
                "label": self.MOIS_NOMS[m],
                "value": by_month.get(m, 0.0),
                "key": str(m),
            }
            for m in range(1, today.month + 1)
        ]

        evolution_vnc: list[dict] = []
        for m in range(1, today.month + 1):
            periode_max = f"{year}-{m:02d}"
            brut = await self._sum_valeur_brute(immo_ids_full)
            cumul = await self._sum_cumul_amort(immo_ids_full, periode_max=periode_max)
            evolution_vnc.append(
                {
                    "label": self.MOIS_NOMS[m],
                    "value": max(0.0, brut - cumul),
                    "key": str(m),
                }
            )

        valeur_brute = await self._sum_valeur_brute(immo_ids_full)
        cumul_amort = await self._sum_cumul_amort(immo_ids_full)
        vnc = max(0.0, valeur_brute - cumul_amort)

        return {
            "par_statut": par_statut,
            "par_famille": par_famille,
            "dotations_mensuelles": dotations_mensuelles,
            "evolution_vnc": evolution_vnc,
            "composition": {
                "valeur_brute": valeur_brute,
                "cumul_amortissement": cumul_amort,
                "vnc": vnc,
            },
            "filtres_actifs": {
                "statut": statut,
                "famille": famille,
                "mois": mois,
            },
        }


