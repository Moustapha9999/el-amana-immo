from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models import Amortissement, Ajustement, Immobilisation, Reevaluation
from app.models.enums import StatutImmobilisation, TypeAjustement
from app.schemas.operations import AjustementCreate, ReevaluationCreate
from app.services.amortissement_service import AmortissementService
from app.services.immobilisation_vnc import compute_situation_comptable


_SORTIE_STATUTS = {
    StatutImmobilisation.CEDEE,
    StatutImmobilisation.MISE_AU_REBUT,
    StatutImmobilisation.SORTIE,
    StatutImmobilisation.ARCHIVEE,
}


class ReevaluationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_immo(self, immobilisation_id: UUID) -> Immobilisation:
        result = await self.db.execute(
            select(Immobilisation)
            .options(selectinload(Immobilisation.categorie))
            .where(Immobilisation.id == immobilisation_id, Immobilisation.deleted_at.is_(None))
        )
        immo = result.scalar_one_or_none()
        if immo is None:
            raise NotFoundError("Immobilisation", str(immobilisation_id))
        return immo

    async def create(self, payload: ReevaluationCreate) -> tuple[Reevaluation, bool, list]:
        immo = await self._load_immo(payload.immobilisation_id)
        if immo.statut in _SORTIE_STATUTS:
            raise ValidationError("Réévaluation impossible sur une immobilisation sortie.")
        if payload.nouvelle_valeur <= 0:
            raise ValidationError("La nouvelle valeur doit être strictement positive.")
        if payload.nouvelle_valeur < immo.valeur_residuelle:
            raise ValidationError("La nouvelle valeur ne peut pas être inférieure à la valeur résiduelle.")

        _, cumul, _ = await compute_situation_comptable(self.db, immo.id)
        if payload.nouvelle_valeur < cumul:
            raise ValidationError(
                "La nouvelle valeur est inférieure au cumul d'amortissement validé — effectuer une reprise ou un ajustement."
            )

        row = Reevaluation(
            immobilisation_id=payload.immobilisation_id,
            date_reevaluation=payload.date_reevaluation,
            ancienne_valeur=immo.valeur_brute,
            nouvelle_valeur=payload.nouvelle_valeur,
            justificatif=payload.justificatif,
        )
        immo.valeur_brute = payload.nouvelle_valeur
        self.db.add(row)
        await self.db.flush()

        ecriture_ids: list = []
        delta = (payload.nouvelle_valeur - row.ancienne_valeur).quantize(Decimal("0.01"))
        from app.services.ecriture_evolution import enregistrer_ecritures_evolution, plan_ecritures_reevaluation

        lines = plan_ecritures_reevaluation(immo, delta=delta)
        if lines:
            ecritures = await enregistrer_ecritures_evolution(
                self.db,
                immo=immo,
                date_ecriture=payload.date_reevaluation,
                reference=f"REEVAL-{immo.code_inventaire}",
                lines=lines,
            )
            ecriture_ids = [e.id for e in ecritures]

        plan_regenere = False
        categorie = immo.categorie
        if (
            immo.statut == StatutImmobilisation.EN_SERVICE
            and categorie is not None
            and categorie.amortissable
        ):
            count = await self.db.execute(
                select(func.count()).select_from(Amortissement).where(
                    Amortissement.immobilisation_id == immo.id,
                    Amortissement.valide.is_(True),
                )
            )
            if int(count.scalar_one()) == 0:
                await AmortissementService(self.db).generer_plan(immo.id)
                plan_regenere = True

        return row, plan_regenere, ecriture_ids


class AjustementService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: AjustementCreate) -> tuple[Ajustement, list]:
        result = await self.db.execute(
            select(Immobilisation)
            .options(selectinload(Immobilisation.categorie))
            .where(Immobilisation.id == payload.immobilisation_id, Immobilisation.deleted_at.is_(None))
        )
        immo = result.scalar_one_or_none()
        if immo is None:
            raise NotFoundError("Immobilisation", str(payload.immobilisation_id))

        from app.services.ecriture_evolution import (
            enregistrer_ecritures_evolution,
            plan_ecritures_reprise,
            plan_ecritures_reevaluation,
        )

        ecriture_ids: list = []

        _, cumul, vnc = await compute_situation_comptable(self.db, immo.id)
        before = {
            "valeur_brute": str(immo.valeur_brute),
            "cumul_amortissement": str(cumul),
            "vnc": str(vnc),
        }

        if payload.type_ajustement == TypeAjustement.CORRECTION:
            new_brute = (immo.valeur_brute + payload.montant).quantize(Decimal("0.01"))
            if new_brute <= 0:
                raise ValidationError("La correction rendrait la valeur brute négative ou nulle.")
            immo.valeur_brute = new_brute
        elif payload.type_ajustement == TypeAjustement.REPRISE:
            if payload.montant <= 0:
                raise ValidationError("Le montant de reprise doit être positif.")
            if payload.montant > cumul:
                raise ValidationError("La reprise ne peut pas dépasser le cumul d'amortissement validé.")

        _, cumul_after, vnc_after = await compute_situation_comptable(self.db, immo.id)
        after = {
            "valeur_brute": str(immo.valeur_brute),
            "cumul_amortissement": str(cumul_after),
            "vnc": str(vnc_after),
            "montant_reprise": str(payload.montant) if payload.type_ajustement == TypeAjustement.REPRISE else None,
        }

        row = Ajustement(
            immobilisation_id=payload.immobilisation_id,
            type_ajustement=payload.type_ajustement,
            date_ajustement=payload.date_ajustement,
            montant=payload.montant,
            commentaire=payload.commentaire,
            before_json=before,
            after_json=after,
        )
        self.db.add(row)
        await self.db.flush()

        lines: list = []
        if payload.type_ajustement == TypeAjustement.REPRISE:
            lines = plan_ecritures_reprise(immo, montant=payload.montant)
        elif payload.type_ajustement == TypeAjustement.CORRECTION and payload.montant != 0:
            lines = plan_ecritures_reevaluation(immo, delta=payload.montant)
        if lines:
            ecritures = await enregistrer_ecritures_evolution(
                self.db,
                immo=immo,
                date_ecriture=payload.date_ajustement,
                reference=f"AJUST-{immo.code_inventaire}",
                lines=lines,
            )
            ecriture_ids = [e.id for e in ecritures]

        return row, ecriture_ids
