"""Réclamations — fondations : catalogue, profils, périmètre d'accès, intégrité du schéma.

Les tests base tournent dans une transaction externe annulée à la fin : aucune donnée laissée.
Ignorés si la migration ``20261013_reclamations_01`` n'est pas appliquée.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.data.module_backup_scopes import ESPACE_MODULES, MODULE_BACKUP_SCOPES
from app.data.plateforme_catalogue import (
    FUNCTIONAL_PERMISSIONS,
    PLATEFORME_DOMAINES,
    PLATEFORME_MODULES,
    RBAC_ROLES,
    ROLE_PERMISSIONS,
)
from app.models import (
    Reclamation,
    ReclamationAffectation,
    ReclamationEvenement,
    ReclamationReferentiel,
    ReclamationUnite,
    ReclamationUniteMembre,
    User,
)
from app.services.reclamations.acces import (
    CAPACITES,
    PERMISSIONS,
    ReclamationsScope,
    charger_scope,
    permissions_effectives,
)

ROLES = (
    "reclamations.point_reception",
    "reclamations.agent_traitement",
    "reclamations.responsable_service",
    "reclamations.agent_sr",
    "reclamations.responsable_sr",
    "reclamations.lecteur",
    "reclamations.admin",
)


# ----------------------------------------------------------------------- catalogue
def test_catalogue_module_et_domaine():
    module = next(m for m in PLATEFORME_MODULES if m["code"] == "reclamations")
    assert module["domaine_code"] == "management-qualite"
    assert module["entry_path"] == "/reclamations/dashboard"
    assert module["statut"] != "actif"
    domaine = next(d for d in PLATEFORME_DOMAINES if d["code"] == "management-qualite")
    assert domaine["statut"] == "actif"
    assert "reclamations" in ESPACE_MODULES["audit-controle-conformite"]
    assert "reclamation_evenements" in MODULE_BACKUP_SCOPES["reclamations"]["exclusive_tables"]


def test_profils_reclamations():
    perms = {c for c, _l, m in FUNCTIONAL_PERMISSIONS if m == "reclamations"}
    assert set(CAPACITES.values()) <= perms
    assert {code for code, _l, _d in RBAC_ROLES} >= set(ROLES)
    for role in ROLES:
        accordees = set(ROLE_PERMISSIONS[role])
        assert accordees <= perms, role
        assert "reclamations.view" in accordees, role
        # Pièces clients : jamais via la GED générique / Archive Générale.
        assert not any(p.startswith("ged.") for p in accordees), role
    assert set(ROLE_PERMISSIONS["reclamations.admin"]) == perms
    # Clôture et validation de la réponse : Service Réclamations (responsable) uniquement.
    for role in ("reclamations.agent_traitement", "reclamations.responsable_service", "reclamations.agent_sr"):
        assert "reclamations.close" not in ROLE_PERMISSIONS[role]
        assert "reclamations.response.validate" not in ROLE_PERMISSIONS[role]
    assert "reclamations.close" in ROLE_PERMISSIONS["reclamations.responsable_sr"]
    # Les services destinataires ne voient que leurs dossiers.
    for role in ("reclamations.point_reception", "reclamations.agent_traitement",
                 "reclamations.responsable_service"):
        assert "reclamations.scope.all" not in ROLE_PERMISSIONS[role]
    # Consultation / audit : aucune action métier.
    lecteur = set(ROLE_PERMISSIONS["reclamations.lecteur"])
    assert not lecteur & {"reclamations.create", "reclamations.update", "reclamations.treat",
                          "reclamations.close", "reclamations.document.upload"}


def test_permissions_effectives():
    assert permissions_effectives({"reclamations.admin"}) == frozenset(PERMISSIONS)
    assert permissions_effectives({"*"}) == frozenset(PERMISSIONS)
    assert permissions_effectives({"formation.admin", "reclamations.view"}) == {"reclamations.view"}


def _scope(*perms: str, unites: set[uuid.UUID] | None = None) -> ReclamationsScope:
    user = User(id=uuid.uuid4(), email="t@bea.test", full_name="Test", hashed_password="x")
    return ReclamationsScope(user=user, permissions=frozenset(perms), unites=frozenset(unites or set()))


def test_capacites_et_perimetre_sans_base():
    s = _scope("reclamations.view", "reclamations.treat")
    assert s.capacites()["traiter"] and not s.capacites()["cloturer"]
    assert s.to_dict()["perimetre"] == "PERSONNEL"
    assert _scope("reclamations.view", "reclamations.scope.all").to_dict()["perimetre"] == "TOUS"
    with pytest.raises(Exception) as exc:
        s.exiger("reclamations.close")
    assert getattr(exc.value, "status_code", None) == 403


# ----------------------------------------------------------------------- base
@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            pret = await conn.scalar(text("SELECT to_regclass('public.reclamation_evenements') IS NOT NULL"))
    except Exception:
        pret = False
    if not pret:
        await engine.dispose()
        pytest.skip("Migration 20261013_reclamations_01 non appliquée")
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


async def _user(db: AsyncSession) -> User:
    u = User(email=f"rec-{uuid.uuid4().hex[:10]}@bea.test", full_name="Agent test", hashed_password="x")
    db.add(u)
    await db.flush()
    return u


async def _unite(db: AsyncSession) -> ReclamationUnite:
    libelle = f"Unité test {uuid.uuid4().hex[:8]}"
    u = ReclamationUnite(type_unite="SERVICE", libelle=libelle, cle=libelle.lower())
    db.add(u)
    await db.flush()
    return u


async def _reclamation(db: AsyncSession, auteur: User, **champs) -> Reclamation:
    canal = await db.scalar(select(ReclamationReferentiel.id).where(
        ReclamationReferentiel.domaine == "CANAL", ReclamationReferentiel.code == "EMAIL"))
    numero = int(uuid.uuid4().int % 900_000) + 100_000
    r = Reclamation(reference=f"REC-1999-{numero}", annee=1999, numero=numero, objet="Test",
                    description="Dossier de test", statut="RECUE", etape="RECEPTION", canal_id=canal,
                    date_premiere_reception=datetime.now(UTC) - timedelta(days=2), created_by_id=auteur.id,
                    **champs)
    db.add(r)
    await db.flush()
    return r


async def test_referentiels_initiaux(db: AsyncSession):
    canaux = set((await db.scalars(select(ReclamationReferentiel.code).where(
        ReclamationReferentiel.domaine == "CANAL"))).all())
    assert {"PAPIER", "COURRIER", "EMAIL", "DIGITAL", "BOITE_LETTRES", "AMANTY_WALLET", "TELEPHONE"} <= canaux
    centrales = (await db.scalars(select(ReclamationUnite).where(
        ReclamationUnite.est_service_reclamations.is_(True), ReclamationUnite.actif.is_(True)))).all()
    assert len(centrales) == 1


async def test_un_seul_service_central(db: AsyncSession):
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(ReclamationUnite(type_unite="SERVICE", libelle="Second central", cle="second central test",
                                    est_service_reclamations=True))
            await db.flush()


async def test_dates_incoherentes_refusees(db: AsyncSession):
    auteur = await _user(db)
    r = await _reclamation(db, auteur)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(text("UPDATE reclamations SET date_reception_sr = date_premiere_reception "
                                  "- interval '1 day' WHERE id = :id"), {"id": r.id})


async def test_chronologie_en_ajout_seul(db: AsyncSession):
    auteur = await _user(db)
    r = await _reclamation(db, auteur)
    ev = ReclamationEvenement(reclamation_id=r.id, type_evenement="CREATION", statut_apres="RECUE",
                              etape_apres="RECEPTION", date_effet=r.date_premiere_reception, auteur_id=auteur.id)
    db.add(ev)
    await db.flush()
    for requete in ("UPDATE reclamation_evenements SET commentaire = 'falsifié' WHERE id = :id",
                    "UPDATE reclamation_evenements SET date_effet = now() WHERE id = :id",
                    "DELETE FROM reclamation_evenements WHERE id = :id"):
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text(requete), {"id": ev.id})
    # Seule exception : la mise à NULL d'une référence (clé étrangère ON DELETE SET NULL).
    await db.execute(text("UPDATE reclamation_evenements SET auteur_id = NULL WHERE id = :id"), {"id": ev.id})
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text("DELETE FROM reclamations WHERE id = :id"), {"id": r.id})


async def test_perimetre_par_unite(db: AsyncSession):
    sr, agent, autre = await _user(db), await _user(db), await _user(db)
    service = await _unite(db)
    db.add(ReclamationUniteMembre(unite_id=service.id, user_id=agent.id, role_membre="RESPONSABLE"))
    await db.flush()
    affecte = await _reclamation(db, sr)
    non_affecte = await _reclamation(db, sr)
    propre = await _reclamation(db, autre)
    db.add(ReclamationAffectation(reclamation_id=affecte.id, numero=1, unite_destinataire_id=service.id,
                                  transmis_le=datetime.now(UTC), transmis_par_id=sr.id))
    await db.flush()

    s = await charger_scope(db, agent)
    assert s.unites == {service.id} and s.unites_responsable == {service.id}
    s = ReclamationsScope(user=agent, permissions=frozenset({"reclamations.view"}), unites=s.unites)
    ids = {affecte.id, non_affecte.id, propre.id}
    visibles = set((await db.scalars(select(Reclamation.id).where(
        Reclamation.id.in_(ids), s.filtre_dossiers()))).all())
    assert visibles == {affecte.id}
    assert await s.couvre(db, affecte) and not await s.couvre(db, non_affecte)

    perso = ReclamationsScope(user=autre, permissions=frozenset({"reclamations.view"}))
    assert set((await db.scalars(select(Reclamation.id).where(
        Reclamation.id.in_(ids), perso.filtre_dossiers()))).all()) == {propre.id}

    global_ = ReclamationsScope(user=sr, permissions=frozenset({"reclamations.view", "reclamations.scope.all"}))
    assert set((await db.scalars(select(Reclamation.id).where(
        Reclamation.id.in_(ids), global_.filtre_dossiers()))).all()) == ids

    sans_droit = ReclamationsScope(user=agent, permissions=frozenset(), unites=frozenset({service.id}))
    assert not await sans_droit.couvre(db, affecte)
