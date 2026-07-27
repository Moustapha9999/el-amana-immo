"""Campagne batch de calcul des amortissements (simulation / validation)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError, ValidationError
from app.models import Amortissement, CategorieImmobilisation, Immobilisation
from app.models.enums import StatutImmobilisation
from app.services.amortissement_engine import (
    calcul_dotation_periode,
    parse_period_end,
    period_bounds,
)
from app.services.amortissement_service import AmortissementService


@dataclass
class CalculAmortLigne:
    immobilisation_id: UUID
    code_inventaire: str
    designation: str
    statut: str
    vnc_avant: Decimal
    dotation: Decimal
    vnc_apres: Decimal
    cumul_apres: Decimal
    cumul_avant: Decimal = Decimal("0.00")
    valeur_brute: Decimal = Decimal("0.00")
    nature: str | None = None
    compte_dotation: str | None = None
    compte_amortissement: str | None = None
    taux: Decimal | None = None
    message: str | None = None


@dataclass
class CalculAmortResult:
    periodicite: str
    annee: int
    periode_index: int
    periode: str
    date_debut: date
    date_arrete: date
    date_ecriture: date
    mode: str
    nb_calcules: int = 0
    nb_ignores_vnc: int = 0
    nb_deja_comptabilises: int = 0
    nb_erreurs: int = 0
    total_dotations: Decimal = Decimal("0.00")
    lignes: list[CalculAmortLigne] = field(default_factory=list)
    ignores: list[CalculAmortLigne] = field(default_factory=list)
    deja_comptabilises: list[CalculAmortLigne] = field(default_factory=list)
    erreurs: list[CalculAmortLigne] = field(default_factory=list)


class AmortissementBatchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculer(
        self,
        *,
        periodicite: str,
        annee: int,
        periode_index: int,
        mode: str,
        categorie_ids: list[UUID] | None = None,
        date_ecriture: date | None = None,
    ) -> CalculAmortResult:
        mode_norm = (mode or "").strip().lower()
        if mode_norm not in {"simulation", "validation"}:
            raise ValidationError("Le mode doit être « simulation » ou « validation ».")

        try:
            date_debut, date_arrete, periode = period_bounds(periodicite, annee, periode_index)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        date_ecr = date_ecriture or date_arrete
        result = CalculAmortResult(
            periodicite=periodicite.strip().lower(),
            annee=annee,
            periode_index=periode_index,
            periode=periode,
            date_debut=date_debut,
            date_arrete=date_arrete,
            date_ecriture=date_ecr,
            mode=mode_norm,
        )

        immobiles = await self._load_immobilisations(categorie_ids)
        amorts_by_immo = await self._prefetch_amortissements([i.id for i in immobiles])
        amort_svc = AmortissementService(self.db)

        for immo in immobiles:
            rows = amorts_by_immo.get(immo.id, [])
            cumul = self._cumul_avant_periode(rows, date_debut)
            vb = immo.valeur_brute.quantize(Decimal("0.01"))
            vnc_avant = (vb - cumul).quantize(Decimal("0.01"))
            if vnc_avant < 0:
                vnc_avant = Decimal("0.00")

            existing = self._existing_periode(rows, periode)
            if existing is not None and existing.valide:
                ligne = self._ligne(
                    immo,
                    statut="deja_comptabilise",
                    vnc_avant=vnc_avant,
                    dotation=existing.montant,
                    vnc_apres=existing.vnc,
                    cumul_avant=cumul,
                    cumul_apres=existing.cumul,
                    message=f"Période {periode} déjà comptabilisée",
                )
                result.deja_comptabilises.append(ligne)
                result.nb_deja_comptabilises += 1
                continue

            if immo.date_acquisition is not None and immo.date_acquisition > date_arrete:
                ligne = self._ligne(
                    immo,
                    statut="ignore_vnc",
                    vnc_avant=vnc_avant,
                    dotation=Decimal("0.00"),
                    vnc_apres=vnc_avant,
                    cumul_avant=cumul,
                    cumul_apres=cumul,
                    message=f"Acquisition postérieure à l'arrêté {date_arrete.strftime('%d/%m/%Y')}",
                )
                result.ignores.append(ligne)
                result.nb_ignores_vnc += 1
                continue

            if not immo.compte_dotation or not immo.compte_amortissement:
                ligne = self._ligne(
                    immo,
                    statut="erreur",
                    vnc_avant=vnc_avant,
                    dotation=Decimal("0.00"),
                    vnc_apres=vnc_avant,
                    cumul_avant=cumul,
                    cumul_apres=cumul,
                    message="Comptes 681 / 148 manquants",
                )
                result.erreurs.append(ligne)
                result.nb_erreurs += 1
                continue

            calc = calcul_dotation_periode(immo, date_debut, date_arrete, cumul)
            if calc is None:
                ligne = self._ligne(
                    immo,
                    statut="ignore_vnc",
                    vnc_avant=vnc_avant,
                    dotation=Decimal("0.00"),
                    vnc_apres=vnc_avant,
                    cumul_avant=cumul,
                    cumul_apres=cumul,
                    message="VNC nulle ou immobilisation non amortissable sur la période",
                )
                result.ignores.append(ligne)
                result.nb_ignores_vnc += 1
                continue

            montant, cumul_apres, vnc_apres = calc
            ligne = self._ligne(
                immo,
                statut="calcule",
                vnc_avant=vnc_avant,
                dotation=montant,
                vnc_apres=vnc_apres,
                cumul_avant=cumul,
                cumul_apres=cumul_apres,
            )

            if mode_norm == "validation":
                try:
                    await self._persist_and_comptabiliser(
                        amort_svc,
                        immo=immo,
                        periode=periode,
                        montant=montant,
                        cumul_apres=cumul_apres,
                        vnc_apres=vnc_apres,
                        existing=existing,
                        date_ecriture=date_ecr,
                    )
                except AppError as exc:
                    ligne.statut = "erreur"
                    ligne.message = exc.message
                    result.erreurs.append(ligne)
                    result.nb_erreurs += 1
                    continue

            result.lignes.append(ligne)
            result.nb_calcules += 1
            result.total_dotations = (result.total_dotations + montant).quantize(Decimal("0.01"))

        return result

    def _ligne(
        self,
        immo: Immobilisation,
        *,
        statut: str,
        vnc_avant: Decimal,
        dotation: Decimal,
        vnc_apres: Decimal,
        cumul_avant: Decimal,
        cumul_apres: Decimal,
        message: str | None = None,
    ) -> CalculAmortLigne:
        cat = immo.categorie
        return CalculAmortLigne(
            immobilisation_id=immo.id,
            code_inventaire=immo.code_inventaire,
            designation=immo.designation,
            statut=statut,
            vnc_avant=vnc_avant,
            dotation=dotation,
            vnc_apres=vnc_apres,
            cumul_avant=cumul_avant,
            cumul_apres=cumul_apres,
            valeur_brute=immo.valeur_brute.quantize(Decimal("0.01")),
            nature=(cat.famille or cat.libelle) if cat is not None else None,
            compte_dotation=immo.compte_dotation,
            compte_amortissement=immo.compte_amortissement,
            taux=immo.taux,
            message=message,
        )

    async def _load_immobilisations(
        self,
        categorie_ids: list[UUID] | None,
    ) -> list[Immobilisation]:
        stmt = (
            select(Immobilisation)
            .options(selectinload(Immobilisation.categorie))
            .join(CategorieImmobilisation, Immobilisation.categorie_id == CategorieImmobilisation.id)
            .where(
                Immobilisation.deleted_at.is_(None),
                Immobilisation.statut == StatutImmobilisation.EN_SERVICE,
                CategorieImmobilisation.amortissable.is_(True),
                CategorieImmobilisation.deleted_at.is_(None),
            )
            .order_by(Immobilisation.code_inventaire.asc())
        )
        if categorie_ids:
            stmt = stmt.where(Immobilisation.categorie_id.in_(categorie_ids))
        result = await self.db.execute(stmt)
        return list(result.scalars().unique().all())

    async def _prefetch_amortissements(
        self, immobilisation_ids: list[UUID]
    ) -> dict[UUID, list[Amortissement]]:
        if not immobilisation_ids:
            return {}
        result = await self.db.execute(
            select(Amortissement).where(
                Amortissement.immobilisation_id.in_(immobilisation_ids),
                Amortissement.annule.is_(False),
                Amortissement.simule.is_(False),
            )
        )
        by_immo: dict[UUID, list[Amortissement]] = defaultdict(list)
        for row in result.scalars().all():
            by_immo[row.immobilisation_id].append(row)
        return by_immo

    @staticmethod
    def _cumul_avant_periode(rows: list[Amortissement], date_debut: date) -> Decimal:
        """Cumul 148 strictement avant le début de la période à calculer.

        Inclut l'ouverture (ex. 2025-12, montant=0, cumul=stock) et les
        trimestres validés antérieurs — ignore les périodes futures du plan.
        """
        zero = Decimal("0.00")
        best_cumul = zero
        sum_montant = zero
        for row in rows:
            if not row.valide:
                continue
            fin = parse_period_end(str(row.periode or ""))
            if fin is None or fin >= date_debut:
                continue
            montant = Decimal(row.montant or 0).quantize(Decimal("0.01"))
            cumul = Decimal(row.cumul or 0).quantize(Decimal("0.01"))
            sum_montant = (sum_montant + montant).quantize(Decimal("0.01"))
            if cumul > best_cumul:
                best_cumul = cumul
        return max(sum_montant, best_cumul)

    @staticmethod
    def _existing_periode(rows: list[Amortissement], periode: str) -> Amortissement | None:
        for row in rows:
            if str(row.periode) == periode:
                return row
        return None

    # Compat tests unitaires qui mockent encore ces helpers
    async def _cumul_valide(self, immobilisation_id: UUID, date_debut: date | None = None) -> Decimal:
        result = await self.db.execute(
            select(Amortissement).where(
                Amortissement.immobilisation_id == immobilisation_id,
                Amortissement.annule.is_(False),
                Amortissement.simule.is_(False),
            )
        )
        rows = list(result.scalars().all())
        if date_debut is None:
            date_debut = date(1900, 1, 1)
            # Sans borne : comportement historique max(sum, max cumul) validés
            zero = Decimal("0.00")
            best = zero
            total = zero
            for row in rows:
                if not row.valide:
                    continue
                total = (total + Decimal(row.montant or 0)).quantize(Decimal("0.01"))
                cumul = Decimal(row.cumul or 0).quantize(Decimal("0.01"))
                if cumul > best:
                    best = cumul
            return max(total, best)
        return self._cumul_avant_periode(rows, date_debut)

    async def _persist_and_comptabiliser(
        self,
        amort_svc: AmortissementService,
        *,
        immo: Immobilisation,
        periode: str,
        montant: Decimal,
        cumul_apres: Decimal,
        vnc_apres: Decimal,
        existing: Amortissement | None,
        date_ecriture: date,
    ) -> None:
        if existing is not None:
            if existing.valide:
                raise ValidationError(f"La période {periode} est déjà comptabilisée.")
            await self.db.execute(
                delete(Amortissement).where(Amortissement.id == existing.id)
            )
            await self.db.flush()

        row = Amortissement(
            immobilisation_id=immo.id,
            periode=periode,
            montant=montant,
            cumul=cumul_apres,
            vnc=vnc_apres,
            simule=False,
            valide=False,
            annule=False,
        )
        self.db.add(row)
        await self.db.flush()
        await amort_svc.comptabiliser(immo.id, periode, date_ecriture)
