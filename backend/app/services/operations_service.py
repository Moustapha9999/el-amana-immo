from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models import Cession, Immobilisation, Rebut, StatutImmobilisation
from app.schemas.operations import CessionCreate, RebutCreate
from app.services.cession_amortissement import preparer_amortissements_cession
from app.services.ecriture_sortie import enregistrer_ecritures_sortie, plan_ecritures_cession, plan_ecritures_rebut
from app.services.immobilisation_vnc import compute_situation_a_date, compute_situation_comptable

_STATUTS_SORTIE_OK = {
    StatutImmobilisation.EN_SERVICE,
    StatutImmobilisation.SUSPENDUE,
    StatutImmobilisation.EN_COURS,
}


def _resultat_cession(prix_cession: Decimal, vnc: Decimal) -> tuple[Decimal, Decimal, Decimal, str]:
    """Résultat = PC − VNC → plus-value / moins-value / équilibre."""
    resultat = (prix_cession - vnc).quantize(Decimal("0.01"))
    if resultat > 0:
        return resultat, resultat, Decimal("0.00"), "plus_value"
    if resultat < 0:
        return resultat, Decimal("0.00"), (-resultat), "moins_value"
    return Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), "equilibre"


class CessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_immo(self, immobilisation_id: UUID) -> Immobilisation:
        immo = await self.db.get(
            Immobilisation,
            immobilisation_id,
            options=(selectinload(Immobilisation.categorie),),
        )
        if immo is None or immo.deleted_at is not None:
            raise NotFoundError("Immobilisation", str(immobilisation_id))
        return immo

    async def preview(self, immobilisation_id: UUID, date_cession, prix_cession: Decimal) -> dict:
        immo = await self._load_immo(immobilisation_id)
        if immo.date_acquisition and date_cession < immo.date_acquisition:
            raise ValidationError("La date de cession ne peut pas être antérieure à la date d'acquisition.")
        if prix_cession < 0:
            raise ValidationError("Le prix de cession doit être positif ou nul.")
        cumul, vnc = compute_situation_a_date(immo, date_cession)
        resultat, plus_value, moins_value, cas = _resultat_cession(prix_cession, vnc)
        return {
            "cumul_amortissement": cumul,
            "vnc": vnc,
            "prix_cession": prix_cession.quantize(Decimal("0.01")),
            "resultat": resultat,
            "plus_value": plus_value,
            "moins_value": moins_value,
            "cas": cas,
        }

    async def create(self, payload: CessionCreate) -> tuple[Cession, list[UUID]]:
        immo = await self._load_immo(payload.immobilisation_id)
        if immo.statut not in _STATUTS_SORTIE_OK:
            raise ValidationError("Seules les immobilisations en service (ou suspendues) peuvent être cédées.")
        if payload.prix_cession < 0:
            raise ValidationError("Le prix de cession doit être positif ou nul.")
        if immo.date_acquisition and payload.date_cession < immo.date_acquisition:
            raise ValidationError("La date de cession ne peut pas être antérieure à la date d'acquisition.")
        reference = (payload.reference or "").strip()
        if not reference:
            raise ValidationError("La référence de la cession est obligatoire.")

        observations = payload.observations
        if not observations and payload.libelle:
            observations = payload.libelle

        # 1) Calcul auto des amortissements jusqu'à la date de cession → VNC
        cumul, vnc = await preparer_amortissements_cession(self.db, immo, payload.date_cession)

        # 2) Résultat de cession = PC − VNC
        _, plus_value, moins_value, _cas = _resultat_cession(payload.prix_cession, vnc)

        row = Cession(
            immobilisation_id=payload.immobilisation_id,
            date_cession=payload.date_cession,
            prix_cession=payload.prix_cession,
            vnc=vnc,
            plus_value=plus_value,
            moins_value=moins_value,
            reference=reference,
            observations=observations,
            libelle=payload.libelle or reference,
        )
        # 3) Arrêt des amortissements + sortie du patrimoine
        immo.statut = StatutImmobilisation.CEDEE
        immo.date_fin = payload.date_cession
        self.db.add(row)
        await self.db.flush()

        # 4) Écritures de sortie
        ref = f"CESS-{immo.code_inventaire}-{payload.date_cession.isoformat()}"
        lines = plan_ecritures_cession(
            immo,
            cumul=cumul,
            valeur_brute=immo.valeur_brute,
            vnc=vnc,
            prix_cession=payload.prix_cession,
            plus_value=plus_value,
            moins_value=moins_value,
        )
        ecritures = await enregistrer_ecritures_sortie(
            self.db,
            immo=immo,
            date_ecriture=payload.date_cession,
            reference=ref,
            lines=lines,
        )
        if ecritures:
            row.ecriture_id = ecritures[0].id
        await self.db.flush()
        return row, [e.id for e in ecritures]


class RebutService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_immo(self, immobilisation_id: UUID) -> Immobilisation:
        immo = await self.db.get(
            Immobilisation,
            immobilisation_id,
            options=(selectinload(Immobilisation.categorie),),
        )
        if immo is None or immo.deleted_at is not None:
            raise NotFoundError("Immobilisation", str(immobilisation_id))
        return immo

    async def create(self, payload: RebutCreate) -> tuple[Rebut, list[UUID]]:
        immo = await self._load_immo(payload.immobilisation_id)
        if immo.statut not in _STATUTS_SORTIE_OK:
            raise ValidationError("Seules les immobilisations en service (ou suspendues) peuvent être mises au rebut.")

        _, cumul, vnc = await compute_situation_comptable(self.db, immo.id)
        row = Rebut(
            immobilisation_id=payload.immobilisation_id,
            date_rebut=payload.date_rebut,
            vnc=vnc,
            motif=payload.motif,
        )
        immo.statut = StatutImmobilisation.MISE_AU_REBUT
        immo.date_fin = payload.date_rebut
        self.db.add(row)
        await self.db.flush()

        ref = f"REBUT-{immo.code_inventaire}-{payload.date_rebut.isoformat()}"
        lines = plan_ecritures_rebut(immo, cumul=cumul, vnc=vnc)
        ecritures = await enregistrer_ecritures_sortie(
            self.db,
            immo=immo,
            date_ecriture=payload.date_rebut,
            reference=ref,
            lines=lines,
        )
        if ecritures:
            row.ecriture_id = ecritures[0].id
        await self.db.flush()
        return row, [e.id for e in ecritures]
