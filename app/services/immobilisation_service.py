from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models import Amortissement, CategorieImmobilisation, Immobilisation, ParametrageAmortissement
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
from app.services.amortissement_engine import parse_period_end
from app.services.amortissement_service import AmortissementService
from app.services.exercice_guard import ensure_exercice_ouvert_pour_date

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



    async def list(
        self,
        page: int,
        size: int,
        search: str | None = None,
        *,
        amortissable: bool | None = None,
        statuts: list[StatutImmobilisation] | None = None,
        famille: str | None = None,
    ) -> tuple[list[Immobilisation], int]:

        from sqlalchemy import String, cast, or_

        from app.core.pagination import page_offset

        filters = [Immobilisation.deleted_at.is_(None)]
        need_cat_join = amortissable is not None or bool(famille and famille.strip())
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            need_cat_join = True
            filters.append(
                or_(
                    Immobilisation.designation.ilike(pattern),
                    Immobilisation.code_inventaire.ilike(pattern),
                    Immobilisation.numero_serie.ilike(pattern),
                    Immobilisation.compte_immobilisation.ilike(pattern),
                    cast(Immobilisation.statut, String).ilike(pattern),
                    cast(Immobilisation.valeur_brute, String).ilike(pattern),
                    CategorieImmobilisation.famille.ilike(pattern),
                    CategorieImmobilisation.code.ilike(pattern),
                )
            )
        if statuts:
            filters.append(Immobilisation.statut.in_(statuts))
        if famille and famille.strip():
            filters.append(CategorieImmobilisation.famille.ilike(famille.strip()))

        stmt = self._base_query()
        count_stmt = select(func.count()).select_from(Immobilisation)
        if need_cat_join:
            join_on = Immobilisation.categorie_id == CategorieImmobilisation.id
            # outerjoin pour ne pas exclure les biens sans catégorie lors d'une recherche texte
            if amortissable is not None or (famille and famille.strip()):
                stmt = stmt.join(CategorieImmobilisation, join_on)
                count_stmt = count_stmt.join(CategorieImmobilisation, join_on)
            else:
                stmt = stmt.outerjoin(CategorieImmobilisation, join_on)
                count_stmt = count_stmt.outerjoin(CategorieImmobilisation, join_on)
        if amortissable is not None:
            amort_filter = CategorieImmobilisation.amortissable.is_(amortissable)
            stmt = stmt.where(amort_filter)
            count_stmt = count_stmt.where(amort_filter)
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

        total = int((await self.db.execute(count_stmt)).scalar_one())
        result = await self.db.execute(
            stmt.order_by(Immobilisation.code_inventaire.asc())
            .offset(page_offset(page, size))
            .limit(size)
        )
        return list(result.scalars().all()), total



    async def get(self, item_id: UUID) -> Immobilisation:

        result = await self.db.execute(

            self._base_query().where(Immobilisation.id == item_id, Immobilisation.deleted_at.is_(None))

        )

        item = result.scalar_one_or_none()

        if item is None:

            raise NotFoundError(self.entity_label, str(item_id))

        return item



    async def create(self, payload: ImmobilisationCreate) -> Immobilisation:

        await ensure_exercice_ouvert_pour_date(
            self.db, payload.date_acquisition, contexte="Création d'immobilisation"
        )

        categorie = await load_categorie(self.db, payload.categorie_id)

        assert categorie is not None

        data = prepare_create(payload, categorie)

        raw_code = data.get("code_inventaire") or payload.code_inventaire
        code = str(raw_code).strip() if raw_code else ""
        if not code:
            from app.services.code_inventaire import next_code_inventaire

            code = await next_code_inventaire(
                self.db, categorie.code, payload.date_acquisition.year
            )
            data["code_inventaire"] = code
        else:
            data["code_inventaire"] = code
        existing = await self.db.execute(
            select(Immobilisation.id).where(Immobilisation.code_inventaire == code).limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            raise ValidationError(f"Le code inventaire « {code} » existe déjà. Choisissez un autre numéro.")

        item = Immobilisation(**data)

        apply_categorie_defaults(
            item,
            categorie,
            override_comptes=not any([payload.compte_immobilisation]),
            preserve_taux=payload.taux is not None,
        )

        validate_immobilisation(item, categorie)

        item.qr_code_data = f"IMMO:{item.code_inventaire}"

        item.barcode_data = item.code_inventaire

        await self.repo.add(item)
        # Recharger avec la relation categorie (évite MissingGreenlet sur ImmobilisationRead)
        return await self.get(item.id)



    async def update(self, item_id: UUID, payload: ImmobilisationUpdate) -> Immobilisation:

        item = await self.get(item_id)
        await ensure_exercice_ouvert_pour_date(
            self.db, item.date_acquisition, contexte="Modification d'immobilisation"
        )
        if payload.date_acquisition is not None:
            await ensure_exercice_ouvert_pour_date(
                self.db, payload.date_acquisition, contexte="Modification d'immobilisation"
            )

        categorie = item.categorie

        if payload.categorie_id is not None:

            categorie = await load_categorie(self.db, payload.categorie_id)

            item.categorie_id = payload.categorie_id

        new_code = (payload.code_inventaire or "").strip() if payload.code_inventaire is not None else ""
        if new_code and new_code != item.code_inventaire:
            existing = await self.db.execute(
                select(Immobilisation.id)
                .where(
                    Immobilisation.code_inventaire == new_code,
                    Immobilisation.id != item.id,
                )
                .limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                raise ValidationError(
                    f"Le code inventaire « {new_code} » existe déjà. Choisissez un autre numéro."
                )

        apply_update_fields(item, payload)
        if new_code:
            item.code_inventaire = new_code
            item.qr_code_data = f"IMMO:{new_code}"
            item.barcode_data = new_code

        if categorie is not None:

            # conserve le taux saisi / existant (surcharge utilisateur autorisée)
            apply_categorie_defaults(item, categorie, override_comptes=False, preserve_taux=True)

        validate_immobilisation(item, categorie)

        await self.db.flush()

        await self.db.refresh(item, attribute_names=["categorie"])

        return item



    async def soft_delete(self, item_id: UUID) -> None:
        """Suppression définitive : enlève l'immobilisation et ses dépendances en base."""
        item = await self.get(item_id)
        await ensure_exercice_ouvert_pour_date(
            self.db, item.date_acquisition, contexte="Suppression d'immobilisation"
        )
        await self._hard_delete(item)

    async def _hard_delete(self, item: Immobilisation) -> None:
        immo_id = item.id
        # Ordre : enfants qui référencent évent. les écritures, puis écritures, puis immo
        for table in (
            "cessions",
            "rebuts",
            "reevaluations",
            "ajustements",
            "inventaire_scans",
            "pieces_jointes",
            "amortissements",
            "ecritures_comptables",
        ):
            await self.db.execute(
                text(f"DELETE FROM {table} WHERE immobilisation_id = :id"),
                {"id": immo_id},
            )
        await self.db.execute(delete(Immobilisation).where(Immobilisation.id == immo_id))
        await self.db.flush()





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

    async def _fin_dernier_trimestre_comptabilise(self, annee: int) -> date | None:
        """Date d'arrêté du dernier trimestre déjà comptabilisé sur l'exercice."""
        result = await self.db.execute(
            select(Amortissement.periode).where(
                Amortissement.valide.is_(True),
                Amortissement.annule.is_(False),
                Amortissement.simule.is_(False),
                Amortissement.periode.like(f"{annee}-%"),
            )
        )
        ends: list[date] = []
        for (periode,) in result.all():
            end = parse_period_end(str(periode))
            if end is not None and end.year == annee:
                ends.append(end)
        return max(ends) if ends else None

    async def _bornes_dotation_exercice(
        self, ref: date | None = None
    ) -> tuple[date, date | None, int]:
        """Début d'exercice → fin du dernier trimestre comptabilisé (ex. 30/06)."""
        today = ref or date.today()
        year = today.year
        year_start = date(year, 1, 1)
        year_end = await self._fin_dernier_trimestre_comptabilise(year)
        return year_start, year_end, year

    async def kpi(
        self,
        statut: str | None = None,
        famille: str | None = None,
        mois: int | None = None,
    ) -> dict[str, float | int]:
        _year_start, year_end, year = await self._bornes_dotation_exercice()
        immo_ids = self._immo_ids_select(statut, famille, apply_statut=True, apply_famille=True)

        total = await self.db.execute(
            select(func.count()).select_from(Immobilisation).where(
                Immobilisation.deleted_at.is_(None),
                Immobilisation.id.in_(immo_ids),
            )
        )
        valeur_brute = await self._sum_valeur_brute(immo_ids)
        cumul_amort = await self._sum_cumul_amort(immo_ids)

        # Dotation 681 : somme des amortissements COMPTABILISÉS de l'exercice
        # (jusqu'à la fin du dernier trimestre validé — pas la date du jour ni le 31/12)
        if year_end is None:
            dotation_valeur = 0.0
        else:
            periodes_rows = await self.db.execute(
                select(Amortissement.periode, Amortissement.montant).where(
                    Amortissement.valide.is_(True),
                    Amortissement.annule.is_(False),
                    Amortissement.simule.is_(False),
                    Amortissement.periode.like(f"{year}-%"),
                    Amortissement.immobilisation_id.in_(immo_ids),
                )
            )
            total_dot = 0.0
            for periode, montant in periodes_rows.all():
                end = parse_period_end(str(periode))
                if end is None or end > year_end:
                    continue
                if mois is not None and end.month != mois:
                    continue
                total_dot += float(montant)
            dotation_valeur = total_dot

        return {
            "nombre_immobilisations": int(total.scalar_one()),
            "valeur_brute_totale": valeur_brute,
            "vnc_totale": max(0.0, valeur_brute - cumul_amort),
            "dotation_periode": dotation_valeur,
            "annee_reference": year,
        }

    async def charts(
        self,
        statut: str | None = None,
        famille: str | None = None,
        mois: int | None = None,
    ) -> dict:
        _year_start, year_end, year = await self._bornes_dotation_exercice()
        # Mois affichés : jusqu'à la fin du trimestre comptabilisé (sinon aucun)
        mois_max = year_end.month if year_end is not None else 0

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

        by_month: dict[int, float] = {}
        if year_end is not None:
            # Agrégation par mois d'arrêté du trimestre comptabilisé (31/03, 30/06, …)
            periodes_rows = await self.db.execute(
                select(Amortissement.periode, Amortissement.montant).where(
                    Amortissement.valide.is_(True),
                    Amortissement.annule.is_(False),
                    Amortissement.simule.is_(False),
                    Amortissement.periode.like(f"{year}-%"),
                    Amortissement.immobilisation_id.in_(immo_ids_full),
                )
            )
            for periode, montant in periodes_rows.all():
                end = parse_period_end(str(periode))
                if end is None or end > year_end:
                    continue
                by_month[end.month] = by_month.get(end.month, 0.0) + float(montant)

        dotations_mensuelles = [
            {
                "label": self.MOIS_NOMS[m],
                "value": by_month.get(m, 0.0),
                "key": str(m),
            }
            for m in range(1, mois_max + 1)
        ]

        evolution_vnc: list[dict] = []
        for m in range(1, mois_max + 1):
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


