from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models import Cession, Immobilisation, Rebut, StatutImmobilisation
from app.schemas.operations import CessionCreate, RebutCreate
from app.services.ecriture_sortie import enregistrer_ecritures_sortie, plan_ecritures_cession, plan_ecritures_rebut
from app.services.immobilisation_vnc import compute_situation_comptable

_STATUTS_SORTIE_OK = {
    StatutImmobilisation.EN_SERVICE,
    StatutImmobilisation.SUSPENDUE,
    StatutImmobilisation.EN_COURS,
}


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

    async def create(self, payload: CessionCreate) -> tuple[Cession, list[UUID]]:
        immo = await self._load_immo(payload.immobilisation_id)
        if immo.statut not in _STATUTS_SORTIE_OK:
            raise ValidationError("Seules les immobilisations en service (ou suspendues) peuvent être cédées.")
        if payload.prix_cession < 0:
            raise ValidationError("Le prix de cession doit être positif ou nul.")

        _, cumul, vnc = await compute_situation_comptable(self.db, immo.id)
        diff = payload.prix_cession - vnc
        plus_value = diff if diff > 0 else Decimal("0")
        moins_value = (-diff) if diff < 0 else Decimal("0")

        row = Cession(
            immobilisation_id=payload.immobilisation_id,
            date_cession=payload.date_cession,
            prix_cession=payload.prix_cession,
            vnc=vnc,
            plus_value=plus_value,
            moins_value=moins_value,
            libelle=payload.libelle,
        )
        immo.statut = StatutImmobilisation.CEDEE
        immo.date_fin = payload.date_cession
        self.db.add(row)
        await self.db.flush()

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
