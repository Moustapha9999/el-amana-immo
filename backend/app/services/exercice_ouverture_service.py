"""Ouverture automatique de l'exercice N+1 après clôture définitive de N."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ValidationError
from app.models import ExerciceComptable, Immobilisation, SoldeOuvertureImmobilisation, User
from app.models.enums import StatutExercice, StatutImmobilisation
from app.services.exercice_cloture_service import ExerciceClotureService
from app.services.periode_amortissement_service import PeriodeAmortissementService
from app.services.recap_amortissement import _q, _zero

STATUTS_ACTIFS = {
    StatutImmobilisation.EN_SERVICE,
    StatutImmobilisation.SUSPENDUE,
    StatutImmobilisation.EN_COURS_ACQUISITION,
    StatutImmobilisation.EN_COURS,
    StatutImmobilisation.BROUILLON,
}


@dataclass
class OuvertureResult:
    annee_source: int
    annee_ouverture: int
    ouvertures_seed: int
    total_valeur_brute: Decimal
    total_amortissement: Decimal
    total_vnc: Decimal
    message: str


class ExerciceOuvertureService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def situation(self) -> dict:
        result = await self.db.execute(
            select(ExerciceComptable).order_by(ExerciceComptable.annee.desc())
        )
        exercices = list(result.scalars().all())
        dernier_cloture = next(
            (e.annee for e in exercices if e.statut == StatutExercice.CLOTURE),
            None,
        )
        exercice_ouvert = next(
            (e.annee for e in exercices if e.statut == StatutExercice.OUVERT),
            None,
        )
        annee_ouverture_proposee = (dernier_cloture + 1) if dernier_cloture is not None else None
        peut_ouvrir = False
        if annee_ouverture_proposee is not None:
            deja = next((e for e in exercices if e.annee == annee_ouverture_proposee), None)
            if deja is None:
                peut_ouvrir = True
            elif deja.statut == StatutExercice.OUVERT:
                # Idempotent : déjà ouvert, bouton peut rejouer sans doublon
                soldes = await self.db.execute(
                    select(SoldeOuvertureImmobilisation.id).where(
                        SoldeOuvertureImmobilisation.annee == annee_ouverture_proposee
                    ).limit(1)
                )
                peut_ouvrir = soldes.scalar_one_or_none() is None
            else:
                peut_ouvrir = False
        return {
            "dernier_cloture": dernier_cloture,
            "exercice_ouvert": exercice_ouvert,
            "annee_ouverture_proposee": annee_ouverture_proposee,
            "peut_ouvrir": peut_ouvrir,
            "exercices": exercices,
        }

    async def ouvrir_suivant(self, *, user: User | None = None) -> OuvertureResult:
        situation = await self.situation()
        annee_source = situation["dernier_cloture"]
        if annee_source is None:
            raise ValidationError(
                "Aucun exercice clôturé. Clôturez d'abord un exercice avant d'ouvrir le suivant."
            )
        annee_ouverture = annee_source + 1

        existing = await self.db.execute(
            select(ExerciceComptable).where(ExerciceComptable.annee == annee_ouverture)
        )
        exo = existing.scalar_one_or_none()
        if exo is not None and exo.statut == StatutExercice.CLOTURE:
            raise ValidationError(f"L'exercice {annee_ouverture} est déjà clôturé.")

        # Idempotence : soldes déjà présents
        if exo is not None:
            await PeriodeAmortissementService(self.db).ensure_periodes(annee_ouverture, exercice=exo)
            count_res = await self.db.execute(
                select(SoldeOuvertureImmobilisation).where(
                    SoldeOuvertureImmobilisation.exercice_id == exo.id
                )
            )
            existing_soldes = list(count_res.scalars().all())
            if existing_soldes:
                total_vb = _q(sum((s.valeur_brute_142 for s in existing_soldes), _zero()))
                total_148 = _q(sum((s.cumul_148 for s in existing_soldes), _zero()))
                total_vnc = _q(sum((s.vnc for s in existing_soldes), _zero()))
                return OuvertureResult(
                    annee_source=annee_source,
                    annee_ouverture=annee_ouverture,
                    ouvertures_seed=len(existing_soldes),
                    total_valeur_brute=total_vb,
                    total_amortissement=total_148,
                    total_vnc=total_vnc,
                    message=(
                        f"Exercice {annee_ouverture} déjà ouvert "
                        f"({len(existing_soldes)} solde(s) d'ouverture)."
                    ),
                )

        # Recalcule les soldes de clôture N (données figées par le garde d'écriture)
        cloture_svc = ExerciceClotureService(self.db)
        _lines, held = await cloture_svc._collect_snapshot_lines(annee_source)

        if exo is None:
            exo = ExerciceComptable(
                annee=annee_ouverture,
                statut=StatutExercice.OUVERT,
                ouverture_at=datetime.now(timezone.utc),
                ouverture_by_id=user.id if user else None,
            )
            self.db.add(exo)
            await self.db.flush()
            await PeriodeAmortissementService(self.db).ensure_periodes(annee_ouverture, exercice=exo)
        else:
            exo.statut = StatutExercice.OUVERT
            exo.ouverture_at = datetime.now(timezone.utc)
            exo.ouverture_by_id = user.id if user else None

        seeded = 0
        total_vb = _zero()
        total_148 = _zero()
        total_vnc = _zero()

        for immo, mvts in held:
            if not self._is_active_for_opening(immo):
                continue
            if "cumul_ouverture_n1" in mvts:
                cumul = _q(mvts["cumul_ouverture_n1"])
                vnc = _q(mvts["vnc_ouverture_n1"])
                vb = _q(mvts.get("valeur_brute") or immo.valeur_brute or 0)
            else:
                cumul = _q(mvts["amorts_cumules_n"])
                vnc = _q(mvts["vnc"])
                vb = _q(mvts.get("valeur_brute") or immo.valeur_brute or 0)

            self.db.add(
                SoldeOuvertureImmobilisation(
                    exercice_id=exo.id,
                    immobilisation_id=immo.id,
                    annee=annee_ouverture,
                    annee_source=annee_source,
                    valeur_brute_142=vb,
                    cumul_148=cumul,
                    vnc=vnc,
                    code_inventaire=immo.code_inventaire,
                )
            )
            total_vb = _q(total_vb + vb)
            total_148 = _q(total_148 + cumul)
            total_vnc = _q(total_vnc + vnc)
            seeded += 1

        exo.total_valeur_brute = total_vb
        exo.total_amortissement = total_148
        exo.total_vnc = total_vnc
        exo.total_dotation_68 = _zero()  # Compte 68 remis à 0
        exo.nb_immobilisations = seeded
        exo.message = (
            f"Ouverture {annee_ouverture} depuis clôture {annee_source} — "
            f"142/148 repris, 68 = 0, {seeded} immobilisation(s)."
        )
        await self.db.flush()
        return OuvertureResult(
            annee_source=annee_source,
            annee_ouverture=annee_ouverture,
            ouvertures_seed=seeded,
            total_valeur_brute=total_vb,
            total_amortissement=total_148,
            total_vnc=total_vnc,
            message=exo.message or "",
        )

    @staticmethod
    def _is_active_for_opening(immo: Immobilisation) -> bool:
        if immo.deleted_at is not None:
            return False
        if immo.date_fin is not None:
            return False
        statut = immo.statut
        if statut in (
            StatutImmobilisation.CEDEE,
            StatutImmobilisation.MISE_AU_REBUT,
            StatutImmobilisation.ARCHIVEE,
            StatutImmobilisation.SORTIE,
            StatutImmobilisation.CESSION,
            StatutImmobilisation.REBUT,
        ):
            return False
        return True


async def cumul_ouverture_pour(
    db: AsyncSession,
    immobilisation_id: UUID,
    annee: int,
) -> Decimal | None:
    """Cumul 148 d'ouverture pour l'exercice ``annee`` (si repris)."""
    result = await db.execute(
        select(SoldeOuvertureImmobilisation.cumul_148).where(
            SoldeOuvertureImmobilisation.immobilisation_id == immobilisation_id,
            SoldeOuvertureImmobilisation.annee == annee,
        )
    )
    value = result.scalar_one_or_none()
    if value is None:
        return None
    return _q(Decimal(value))
