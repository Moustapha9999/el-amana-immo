import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models import (
    Agence,
    Direction,
    Journal,
    ParametrageAmortissement,
    Permission,
    Role,
    User,
)
from app.models import entities  # noqa: F401
from app.services.agences_seed import seed_agences_el_amana
from app.services.plan_comptable_seed import seed_plan_comptable_el_amana


async def seed() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(User.id).where(User.email == "admin@el-amana.mr"))
        if existing.scalar_one_or_none() is not None:
            print("Seed déjà appliqué — admin@el-amana.mr existe.")
            return

        direction = Direction(code="DIR001", libelle="Direction Générale")
        journal = Journal(code="OD", libelle="Opérations diverses")

        admin_role = Role(code="administrateur", label="Admin", description="Accès complet")
        comptable_role = Role(code="comptable", label="Comptable")
        auditeur_role = Role(code="auditeur", label="Auditeur")
        lecture_role = Role(code="lecture_seule", label="Lecture seule")

        perm_users = Permission(code="users.read", label="Lire utilisateurs", module="users")
        perm_immo = Permission(code="immobilisations.write", label="Gérer immobilisations", module="immobilisations")
        admin_role.permissions = [perm_users, perm_immo]

        parametrage = ParametrageAmortissement()

        session.add_all(
            [
                direction,
                journal,
                admin_role,
                comptable_role,
                auditeur_role,
                lecture_role,
                perm_users,
                perm_immo,
                parametrage,
            ]
        )
        await session.flush()

        agence_stats = await seed_agences_el_amana(session)
        centrale = (
            await session.execute(select(Agence).where(Agence.code == "00001"))
        ).scalar_one()
        plan_stats = await seed_plan_comptable_el_amana(session)

        admin = User(
            email="admin@el-amana.mr",
            full_name="Administrateur Système",
            hashed_password=get_password_hash("Admin@2026"),
            is_superuser=True,
            agence_id=centrale.id,
            roles=[admin_role, comptable_role, auditeur_role, lecture_role],
        )
        session.add(admin)
        await session.commit()
        print(f"Seed OK — admin: admin@el-amana.mr / Admin@2026 ({settings.app_env})")
        print(f"Agences El Amana: {agence_stats}")
        print(f"Plan El Amana: {plan_stats}")


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
