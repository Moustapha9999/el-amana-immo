"""Seed idempotent des agences Banque El Amana."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.data.el_amana_referentiel import AGENCES_EL_AMANA, BANQUE_EL_AMANA
from app.models import Agence, User


async def seed_agences_el_amana(session: AsyncSession) -> dict[str, int]:
    """Upsert les 16 agences BEA et désactive l'ancien code AG001 si présent."""
    stats = {"created": 0, "updated": 0, "deactivated": 0, "users_relinked": 0}
    bank = BANQUE_EL_AMANA

    existing = {a.code: a for a in (await session.execute(select(Agence))).scalars().all()}

    centrale: Agence | None = None
    for row in AGENCES_EL_AMANA:
        fields = {
            "libelle": row["libelle"],
            "ville": row.get("ville"),
            "code_banque": bank["code_banque"],
            "banque_sigle": bank["sigle"],
            "banque_raison_sociale": bank["raison_sociale"],
            "code_swift": bank["code_swift"],
            "is_active": True,
            "deleted_at": None,
        }
        code = row["code"]
        if code in existing:
            agence = existing[code]
            for key, value in fields.items():
                setattr(agence, key, value)
            stats["updated"] += 1
        else:
            agence = Agence(code=code, **fields)
            session.add(agence)
            existing[code] = agence
            stats["created"] += 1
        if code == "00001":
            centrale = agence

    await session.flush()

    legacy = existing.get("AG001")
    if legacy is not None and legacy.deleted_at is None:
        if centrale is None:
            centrale = existing.get("00001")
        if centrale is not None:
            users = (
                await session.execute(
                    select(User).options(selectinload(User.roles)).where(User.agence_id == legacy.id)
                )
            ).scalars().all()
            for user in users:
                user.agence_id = centrale.id
                stats["users_relinked"] += 1
        legacy.is_active = False
        legacy.deleted_at = datetime.now(UTC)
        stats["deactivated"] += 1

    await session.flush()
    return stats
