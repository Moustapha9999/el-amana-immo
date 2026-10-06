"""Facturation Fournisseurs sur PostgreSQL — profils, validation (circuit court), paiements détaillés.

Ignoré si la migration ``20261006_mg_facturation_profils`` n'est pas appliquée.
Exécution sur une copie de la base (bea_digital_eer_test) : chaque test tourne dans une transaction
externe annulée à la fin (les ``commit`` du service deviennent des savepoints).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import MgFacturationProfil, User
from app.models.ged import GedDocument
from app.schemas.mg_facturation import FactureCreate, FacturePaiementIn, FactureUpdate
from app.services.mg_facturation_service import ESPACE, GED_ENTITY, MODULE, MgFacturationService


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            pret = await conn.scalar(text("SELECT to_regclass('public.mg_facturation_profils') IS NOT NULL"))
    except Exception:
        pret = False
    if not pret:
        await engine.dispose()
        pytest.skip("Migration 20261006_mg_facturation_profils non appliquée")
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


async def _contexte(db: AsyncSession):
    user = await db.scalar(select(User).where(User.is_superuser.is_(True), User.deleted_at.is_(None)).limit(1))
    if user is None:
        pytest.skip("Aucun super-utilisateur dans la base de test")
    profils = {p.code: p for p in (await db.execute(select(MgFacturationProfil))).scalars().all()}
    return user, profils, MgFacturationService(db)


def _numero() -> str:
    return f"T-{uuid.uuid4().hex[:10]}"


def _joindre_scan(db: AsyncSession, facture_id: uuid.UUID, user: User) -> None:
    """Pièce GED rattachée à la facture (métadonnées seules : aucun fichier écrit)."""
    db.add(
        GedDocument(
            espace_code=ESPACE, module_code=MODULE, entity=GED_ENTITY, entity_id=str(facture_id),
            filename="scan.pdf", stored_path="tests/scan.pdf", mime_type="application/pdf", size_bytes=10,
            uploaded_by_id=user.id, title="Facture scannée", doc_type="FACTURE_SCANNEE",
        )
    )


async def test_profils_initiaux(db):
    _user, profils, _svc = await _contexte(db)
    assert {"SOMELEC", "MATTEL_USSD", "MATTEL_SMS", "MAURITEL_ADSL", "MAURITEL_GFU",
            "CHINGUITEL_BEA_SMS", "RIMATEL", "SNDE"} <= set(profils)
    assert profils["MATTEL_SMS"].fournisseur_id == profils["MATTEL_USSD"].fournisseur_id
    assert profils["SNDE"].taux_tva is None and profils["RIMATEL"].taux_tva is None
    assert profils["MAURITEL_ADSL"].taux_tva == Decimal("18.00")
    assert profils["RIMATEL"].champs["numero_fournisseur"] == "facultatif"


async def test_cycle_controle_validation_paiement_carte(db):
    user, profils, svc = await _contexte(db)
    mattel = profils["MATTEL_SMS"]
    base = dict(profil_id=mattel.id, date_facture=date.today(), montant_ht=Decimal("1000"), montant_tva=Decimal("180"))

    with pytest.raises(AppError) as err:
        await svc.create_facture(FactureCreate(**base), user)
    assert err.value.code == "FACTURE_CHAMPS_OBLIGATOIRES"

    f = await svc.create_facture(FactureCreate(**base, numero_fournisseur=_numero()), user)
    assert f["statut"] == "RECUE" and f["montant_ttc"] == 1180.0
    assert f["fournisseur_id"] == str(mattel.fournisseur_id) and f["profil"] == "MATTEL SMS"
    assert "valider" in f["actions"] and "valider_controle" not in f["actions"]
    assert "tva_incoherente" not in {c["code"] for c in f["controles"]}
    fid = uuid.UUID(f["id"])

    with pytest.raises(AppError) as err:
        await svc.transition(fid, "valider", user, None)
    assert err.value.code == "FACTURE_CONTROLE_BLOQUANT" and "scannée" in err.value.message
    _joindre_scan(db, fid, user)
    f = await svc.transition(fid, "valider", user, None)
    assert f["statut"] == "VALIDEE" and f["statut_paiement"] == "A_PAYER"

    with pytest.raises(AppError) as err:
        await svc.add_paiement(
            fid,
            FacturePaiementIn(date_paiement=date.today(), montant=Decimal("500"), mode_paiement="Carte",
                              carte_derniers_chiffres="4111111111111111"),
            user,
        )
    assert err.value.code == "PAIEMENT_CARTE_INVALIDE"
    with pytest.raises(AppError) as err:
        await svc.add_paiement(
            fid, FacturePaiementIn(date_paiement=date.today(), montant=Decimal("500"), mode_paiement="Chèque"), user
        )
    assert err.value.code == "PAIEMENT_DETAIL_MANQUANT"

    f = await svc.add_paiement(
        fid,
        FacturePaiementIn(date_paiement=date.today(), montant=Decimal("500"), mode_paiement="Carte",
                          carte_derniers_chiffres="4242", reference_paiement="TRX-01"),
        user,
    )
    assert f["statut_paiement"] == "PARTIELLEMENT_PAYEE" and f["reste"] == 680.0
    assert f["paiements"][0]["carte_masquee"] == "•••• 4242"


async def test_arrieres_et_modification_avant_validation(db):
    user, profils, svc = await _contexte(db)
    somelec = profils["SOMELEC"]
    f = await svc.create_facture(
        FactureCreate(profil_id=somelec.id, date_facture=date.today(), numero_fournisseur=_numero(),
                      montant_ttc=Decimal("1000"), arrieres=Decimal("200")),
        user,
    )
    assert f["montant_a_payer"] == 1200.0 and f["arrieres"] == 200.0
    assert f["montant_ht"] is None, f["montant_ht"]
    fid = uuid.UUID(f["id"])
    f = await svc.update_facture(fid, FactureUpdate(montant_ttc=Decimal("1100")), user)
    assert f["statut"] == "RECUE" and f["montant_a_payer"] == 1300.0


async def test_piece_facultative_si_parametre_non(db):
    user, profils, svc = await _contexte(db)
    await svc.set_param("factures.piece_obligatoire", "non", user)
    f = await svc.create_facture(
        FactureCreate(profil_id=profils["SNDE"].id, date_facture=date.today(), numero_fournisseur=_numero(),
                      montant_ttc=Decimal("800")),
        user,
    )
    assert {c["code"]: c["niveau"] for c in f["controles"]}["document_absent"] == "attention"
    f = await svc.transition(uuid.UUID(f["id"]), "valider", user, None)
    assert f["statut"] == "VALIDEE"
    with pytest.raises(AppError) as err:
        await svc.set_param("factures.piece_obligatoire", "peut-être", user)
    assert err.value.code == "PARAMETRE_INVALIDE"


async def test_rimatel_sans_numero(db):
    user, profils, svc = await _contexte(db)
    f = await svc.create_facture(
        FactureCreate(profil_id=profils["RIMATEL"].id, date_facture=date.today(), montant_ttc=Decimal("500")), user
    )
    assert f["statut"] == "RECUE" and f["numero_fournisseur"] is None
