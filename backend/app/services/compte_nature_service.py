"""Création d'un compte plan lié à une nature IMMO (taux / durée / trio de comptes)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.data.el_amana_referentiel import COMPTES_NON_AMORTISSABLES_EL_AMANA, LIBELLE_ECRITURE_MODELE
from app.models import CategorieImmobilisation, ComptePlanComptable, ParametrageEcriture
from app.models.enums import ModeAmortissement, TypeComptePlan, TypeImmobilisation
from app.schemas.comptabilite import ComptePlanCreate, ComptePlanCreateLinked, ComptePlanRead
from app.services.amortissement_rate import taux_lineaire_from_duree_annees
from app.services.nature_immo_referentiel import suggest_paired_accounts as _suggest_pairs


def suggest_paired_accounts(numero_immo: str) -> tuple[str, str]:
    """Propose 148/681 via Types officiels (ex. 142010 → 148211), sinon suffixe."""
    try:
        return _suggest_pairs(numero_immo)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


async def _ensure_compte(
    db: AsyncSession,
    numero: str,
    libelle: str,
    type_compte: TypeComptePlan,
) -> ComptePlanComptable:
    existing = (
        await db.execute(
            select(ComptePlanComptable).where(
                ComptePlanComptable.numero == numero,
                ComptePlanComptable.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.type_compte != type_compte:
            raise ValidationError(
                f"Le compte {numero} existe déjà avec le type « {existing.type_compte.value} »."
            )
        return existing
    row = ComptePlanComptable(numero=numero, libelle=libelle, type_compte=type_compte)
    db.add(row)
    await db.flush()
    return row


class CompteNatureService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_linked(self, payload: ComptePlanCreateLinked) -> ComptePlanRead:
        numero = payload.numero.strip()
        libelle = payload.libelle.strip()
        if not numero or not libelle:
            raise ValidationError("Numéro et libellé obligatoires.")

        # Compte « simple » (amort / dotation / autres) sans nature
        if payload.type_compte != TypeComptePlan.IMMOBILISATION:
            existing = (
                await self.db.execute(
                    select(ComptePlanComptable).where(
                        ComptePlanComptable.numero == numero,
                        ComptePlanComptable.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                raise ValidationError(f"Le compte « {numero} » existe déjà.")
            row = ComptePlanComptable(
                numero=numero,
                libelle=libelle,
                type_compte=payload.type_compte,
                centre_analytique=payload.centre_analytique,
            )
            self.db.add(row)
            await self.db.flush()
            return ComptePlanRead.model_validate(row)

        duree = payload.duree_annees
        has_duree = duree is not None and duree >= 1
        # Sans durée → nature non amortissable (ex. Terrain / Titres / Immo en cours)
        amortissable = has_duree and numero not in COMPTES_NON_AMORTISSABLES_EL_AMANA

        amort_num = (payload.compte_amortissement or "").strip() or None
        dot_num = (payload.compte_dotation or "").strip() or None
        taux: Decimal | None = None

        if amortissable:
            if not amort_num or not dot_num:
                sug_a, sug_d = suggest_paired_accounts(numero)
                amort_num = amort_num or sug_a
                dot_num = dot_num or sug_d
            taux = payload.taux_lineaire
            if taux is None:
                taux = taux_lineaire_from_duree_annees(duree)
            if taux is None:
                raise ValidationError("Impossible de calculer le taux à partir de la durée.")
            taux = Decimal(taux).quantize(Decimal("0.0001"))

        # Compte immo
        immo = await _ensure_compte(
            self.db, numero, libelle, TypeComptePlan.IMMOBILISATION
        )
        immo.centre_analytique = payload.centre_analytique

        if amortissable and amort_num and dot_num:
            await _ensure_compte(
                self.db,
                amort_num,
                f"Amortissements {libelle}",
                TypeComptePlan.AMORTISSEMENT,
            )
            await _ensure_compte(
                self.db,
                dot_num,
                f"Dotations amortissements {libelle}",
                TypeComptePlan.DOTATION,
            )

        code = (payload.nature_code or f"TY-{numero}").strip().upper()
        famille = (payload.nature_libelle or libelle).strip()

        existing_nat = (
            await self.db.execute(
                select(CategorieImmobilisation).where(
                    CategorieImmobilisation.code == code,
                    CategorieImmobilisation.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing_nat:
            raise ValidationError(
                f"La nature « {code} » existe déjà. Modifiez-la dans l’onglet Types."
            )

        # Une seule nature par compte immo
        clash = (
            await self.db.execute(
                select(CategorieImmobilisation).where(
                    CategorieImmobilisation.compte_immobilisation == numero,
                    CategorieImmobilisation.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if clash:
            raise ValidationError(
                f"Le compte {numero} est déjà lié à la nature « {clash.famille} » ({clash.code})."
            )

        categorie = CategorieImmobilisation(
            code=code,
            famille=famille,
            type_immobilisation=TypeImmobilisation.AUTRES,
            compte_immobilisation=numero,
            compte_amortissement=amort_num if amortissable else None,
            compte_dotation=dot_num if amortissable else None,
            amortissable=amortissable,
            duree_annees_defaut=duree if amortissable else None,
            taux_lineaire_defaut=taux if amortissable else None,
            mode_amortissement_defaut=ModeAmortissement.LINEAIRE,
            periodicite_defaut="trimestriel",
            prorata_temporis=True,
            journal_code="OD",
        )
        self.db.add(categorie)
        await self.db.flush()

        if amortissable and amort_num and dot_num:
            self.db.add(
                ParametrageEcriture(
                    categorie_id=categorie.id,
                    journal_code="OD",
                    compte_debit=dot_num,
                    compte_credit=amort_num,
                    libelle_modele=LIBELLE_ECRITURE_MODELE,
                )
            )
            await self.db.flush()
        return ComptePlanRead.model_validate(immo)

    async def create_simple(self, payload: ComptePlanCreate) -> ComptePlanRead:
        linked = ComptePlanCreateLinked(
            numero=payload.numero,
            libelle=payload.libelle,
            type_compte=payload.type_compte,
            centre_analytique=payload.centre_analytique,
        )
        return await self.create_linked(linked)
