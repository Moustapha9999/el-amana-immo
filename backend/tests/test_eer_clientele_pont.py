"""Phase 9 : EER branché sur la racine ORION (6 chiffres), sans fusionner eer_parties."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import ClienteleClient, User
from app.services.clientele.import_service import ClienteleImportService
from app.services.clientele.service import Ctx
from app.services.eer.clientele_pont import compte_principal, normaliser_racine, propositions
from app.services.eer.constantes import EtatChamp
from app.services.eer.workflow import Statut
from app.services.eer_dossier_service import EerDossierService
from tests.test_clientele_consolidation import brute
from tests.test_clientele_import import classeur
from tests.test_eer_dossier_service import _acteurs, _agence

EXTRACTION = date(2026, 10, 31)


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            eer = await conn.scalar(text("SELECT to_regclass('public.eer_dossiers') IS NOT NULL"))
            cl = await conn.scalar(text("SELECT to_regclass('public.clientele_clients') IS NOT NULL"))
            regles = await conn.scalar(text("SELECT count(*) FROM eer_checklist_regles")) if eer else 0
    except Exception:
        eer = cl = regles = False
    if not (eer and cl and regles):
        await engine.dispose()
        pytest.skip("Tables EER ou clientèle absentes")
    session = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def test_racine_six_chiffres_refuse_compte_et_zfill():
    assert normaliser_racine(None) is None
    assert normaliser_racine("000001") == "000001"
    with pytest.raises(AppError) as err:
        normaliser_racine("1")
    assert err.value.code == "RACINE_INVALIDE"
    with pytest.raises(AppError):
        normaliser_racine("000001-1")
    with pytest.raises(AppError):
        normaliser_racine("00000100001")


@pytest.mark.asyncio
async def test_apercu_et_prefill_sans_ecrasement(db):
    charge, _agent, _sup = await _acteurs(db)
    agence = await _agence(db)
    user = await db.scalar(select(User).where(User.id == charge.user.id))
    ctx = Ctx(user=user, permissions={"clientele.admin"})
    imp = ClienteleImportService(db, ctx)
    a = await imp.analyser(classeur(
        brute("000001", "00000100001"),
        brute("000001", "00000100002"),
        brute("000001", "00000100003"),
    ), "eer-pont.xlsx")
    await imp.confirmer(uuid.UUID(a["id"]), {"date_extraction": EXTRACTION.isoformat()})

    client = await db.scalar(
        select(ClienteleClient).where(ClienteleClient.racine_client == "000001")
        .options(selectinload(ClienteleClient.comptes)))
    assert client is not None
    assert len(client.comptes) == 3
    principal = compte_principal(list(client.comptes))
    assert principal is not None
    props, reserves = propositions(client, type_client="PP")
    chemins = {c for c, _v in props}
    assert "client.nom" in chemins
    assert "dossier.numero_compte" in chemins
    assert "dossier.etat_compte" not in chemins  # OUVERT n'est pas Actif
    assert any("OUVERT/FERME" in r for r in reserves)

    svc = EerDossierService(db)
    apercu = await svc.apercu_orion("000001")
    assert apercu["present"] is True
    assert apercu["nb_comptes"] == 3

    d = await svc.creer_dossier(
        charge, agence_id=agence.id, type_client="PP", profil="SALARIE",
        client={"nom": "Nom saisi EER", "pp": {"prenom": "Test"},
                "piece": {"type": "NNI", "numero": "T-PONT-0001"},
                "racine_client": "000001"},
        client_role={"ppe": False, "fatca_indice": False},
        dossier={"risque_lbcft": "FAIBLE", "tranche_mouvement_code": "PP_LT_50K"})
    assert d.statut == Statut.BROUILLON
    assert d.racine_client == "000001"
    partie = next(p.partie for p in d.parties if p.role == "CLIENT")
    assert partie.nom == "Nom saisi EER"  # saisie conservée
    assert partie.racine_client == "000001"
    assert d.numero_compte  # prérempli depuis ORION (champ vide)

    fiches = await svc.fiches(d.id)
    racine_champ = next(c for champs in fiches.values() for c in champs if c.chemin == "dossier.racine_client")
    assert racine_champ.valeur == "000001"
    assert racine_champ.source == "ORION" or racine_champ.etat in (
        EtatChamp.A_CONFIRMER, EtatChamp.CONNU, EtatChamp.NON_APPLICABLE)

    absent = await svc.apercu_orion("000099")
    assert absent["present"] is False

    with pytest.raises(AppError):
        await svc.apercu_orion("12")
