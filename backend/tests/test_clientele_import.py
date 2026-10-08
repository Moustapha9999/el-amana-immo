"""Import ORION : mapping, consolidation multi-comptes, confirmation SQL, pas de suppression."""

from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.data.module_backup_scopes import ESPACE_MODULES, MODULE_BACKUP_SCOPES
from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, PLATEFORME_MODULES, ROLE_PERMISSIONS
from app.models import ClienteleClient, ClienteleCompte, User
from app.services.clientele.consolidation import cartographier
from app.services.clientele.import_service import ClienteleImportService, _est_classeur_situation
from app.services.clientele.lecture import lire_classeur
from app.services.clientele.service import Ctx
from tests.test_clientele_consolidation import brute

EXTRACTION = date(2026, 10, 8)


def classeur(*lignes: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet 1"
    entetes = list(lignes[0].keys())
    ws.append(entetes)
    for ligne in lignes:
        ws.append([ligne[c] for c in entetes])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            pret = await conn.scalar(text("SELECT to_regclass('public.clientele_imports') IS NOT NULL"))
    except Exception:
        pret = False
    if not pret:
        await engine.dispose()
        pytest.skip("Tables clientele_imports absentes (migration 20261008_clientele_02 non appliquée)")
    session = async_sessionmaker(engine, expire_on_commit=False)()
    await session.execute(text("DELETE FROM clientele_import_anomalies"))
    await session.execute(text("DELETE FROM clientele_import_lignes"))
    await session.execute(text("DELETE FROM clientele_imports"))
    has03 = await session.scalar(text("SELECT to_regclass('public.clientele_classifications') IS NOT NULL"))
    if has03:
        await session.execute(text(
            "DELETE FROM clientele_classif_historique WHERE racine_client IN ('000001','000002')"))
        await session.execute(text(
            "DELETE FROM clientele_classifications WHERE racine_client IN ('000001','000002')"))
    await session.execute(text("DELETE FROM clientele_comptes WHERE racine_client IN ('000001','000002')"))
    await session.execute(text("DELETE FROM clientele_clients WHERE racine_client IN ('000001','000002')"))
    await session.commit()
    try:
        yield session
    finally:
        await session.rollback()
        await session.execute(text("DELETE FROM clientele_import_anomalies"))
        await session.execute(text("DELETE FROM clientele_import_lignes"))
        await session.execute(text("DELETE FROM clientele_imports"))
        if has03:
            await session.execute(text(
                "DELETE FROM clientele_classif_historique WHERE racine_client IN ('000001','000002')"))
            await session.execute(text(
                "DELETE FROM clientele_classifications WHERE racine_client IN ('000001','000002')"))
        await session.execute(text("DELETE FROM clientele_comptes WHERE racine_client IN ('000001','000002')"))
        await session.execute(text("DELETE FROM clientele_clients WHERE racine_client IN ('000001','000002')"))
        await session.commit()
        await session.close()
        await engine.dispose()


async def _svc(db) -> ClienteleImportService:
    user = await db.scalar(select(User).limit(1))
    if not user:
        pytest.skip("aucun utilisateur en base de test")
    return ClienteleImportService(db, Ctx(user=user, permissions={"clientele.admin"}))


def test_catalogue_clientele():
    module = next(m for m in PLATEFORME_MODULES if m["code"] == "clientele")
    assert module["entry_path"].startswith("/clientele/")
    perms = {c for c, _l, m in FUNCTIONAL_PERMISSIONS if m == "clientele"}
    assert {"clientele.view", "clientele.import.execute", "clientele.classif.execute",
            "clientele.filtrage.decide", "clientele.admin"} <= perms
    for role in ("clientele.lecteur", "clientele.gestionnaire", "clientele.admin"):
        assert role in ROLE_PERMISSIONS
    assert "clientele.import.execute" not in ROLE_PERMISSIONS["clientele.lecteur"]
    assert "clientele" in ESPACE_MODULES["audit-controle-conformite"]
    assert "clientele_clients" in MODULE_BACKUP_SCOPES["clientele"]["exclusive_tables"]


def test_cartographie_synonymes_et_colonne_extra():
    mapping, ignores = cartographier(["CLIENT", "COMPTE", "RIB", "CODE_AGENCE_COMPTE",
                                      "RAISON_SOCIAL", "ETAT_COMPTE", "DEVISE", "COLONNE_X"])
    assert mapping["CLIENT"] == "CLIENT"
    assert "COLONNE_X" in ignores


def test_trois_comptes_un_client_dans_le_classeur():
    contenu = classeur(
        brute("000001", "00000100001"),
        brute("000001", "00000100002"),
        brute("000001", "00000100003"),
    )
    a = lire_classeur(contenu)
    assert a.colonnes_manquantes == []
    assert (a.consolidation.nb_clients, a.consolidation.nb_comptes, a.consolidation.nb_rib) == (1, 3, 3)


def test_classeur_situation_reconnu_et_refuse():
    contenu = classeur({
        "CODE AG": "00003", "AGENCE_COMPTE": "AGENCE TEST", "CLIENT": "000001", "NOM CLIENT": "TEST",
        "date ouv": "01/01/2020", "statut": "Ouvert", "Profil ORION retraité": "PARTICULIERS",
        "Profil pointage stagiaire": "PP", "NIF": None, "NNI": None,
        "Classe risque LBC FT": "FAIBLE", "Motif de risque": None,
    })
    a = lire_classeur(contenu)
    assert "COMPTE" in a.colonnes_manquantes
    assert _est_classeur_situation(a)
    etat = lire_classeur(classeur(brute("000001", "00000100001")))
    assert not _est_classeur_situation(etat)


@pytest.mark.asyncio
async def test_import_un_client_trois_comptes_puis_deuxieme(db):
    svc = await _svc(db)
    contenu = classeur(
        brute("000001", "00000100001"),
        brute("000001", "00000100002"),
        brute("000001", "00000100003"),
    )
    analyse = await svc.analyser(contenu, "etat.xlsx")
    assert analyse["nb_clients"] == 1
    assert analyse["nb_comptes"] == 3
    assert analyse["analyse"]["apercu_ecriture"]["clients_a_creer"] == 1
    assert analyse["analyse"]["apercu_ecriture"]["comptes_a_creer"] == 3

    confirme = await svc.confirmer(uuid.UUID(analyse["id"]), {"date_extraction": EXTRACTION.isoformat()})
    assert confirme["statut"] == "IMPORTE"
    assert (confirme["clients_crees"], confirme["comptes_crees"]) == (1, 3)
    clients = await db.scalar(select(func.count()).select_from(ClienteleClient)
                              .where(ClienteleClient.racine_client == "000001"))
    comptes = await db.scalar(select(func.count()).select_from(ClienteleCompte)
                              .where(ClienteleCompte.racine_client == "000001"))
    assert (clients, comptes) == (1, 3)

    contenu2 = classeur(
        brute("000001", "00000100001"),
        brute("000001", "00000100002"),
        brute("000001", "00000100003"),
        brute("000002", "00000200001"),
    )
    a2 = await svc.analyser(contenu2, "etat2.xlsx")
    c2 = await svc.confirmer(uuid.UUID(a2["id"]), {"date_extraction": EXTRACTION.isoformat()})
    assert (c2["clients_crees"], c2["comptes_crees"]) == (1, 1)
    n_clients = await db.scalar(select(func.count()).select_from(ClienteleClient)
                                .where(ClienteleClient.racine_client.in_(("000001", "000002"))))
    n_comptes = await db.scalar(select(func.count()).select_from(ClienteleCompte)
                                .where(ClienteleCompte.racine_client.in_(("000001", "000002"))))
    assert (n_clients, n_comptes) == (2, 4)


@pytest.mark.asyncio
async def test_reimport_ne_supprime_pas_les_clients(db):
    svc = await _svc(db)
    a1 = await svc.analyser(classeur(brute("000001", "00000100001"), brute("000001", "00000100002")), "a.xlsx")
    await svc.confirmer(uuid.UUID(a1["id"]), {"date_extraction": EXTRACTION.isoformat()})
    a2 = await svc.analyser(classeur(brute("000001", "00000100001")), "b.xlsx")
    assert a2["analyse"]["apercu_ecriture"]["comptes_absents_du_fichier"] == 1
    await svc.confirmer(uuid.UUID(a2["id"]), {"date_extraction": "2026-10-09"})
    comptes = await db.scalar(select(func.count()).select_from(ClienteleCompte)
                              .where(ClienteleCompte.racine_client == "000001"))
    assert comptes == 2


@pytest.mark.asyncio
async def test_fichier_deja_importe_exige_forcer(db):
    svc = await _svc(db)
    contenu = classeur(brute("000001", "00000100001"))
    a1 = await svc.analyser(contenu, "dup.xlsx")
    await svc.confirmer(uuid.UUID(a1["id"]), {"date_extraction": EXTRACTION.isoformat()})
    a2 = await svc.analyser(contenu, "dup.xlsx")
    assert a2["analyse"]["deja_importe"]
    with pytest.raises(Exception):
        await svc.confirmer(uuid.UUID(a2["id"]), {"date_extraction": EXTRACTION.isoformat()})
    ok = await svc.confirmer(uuid.UUID(a2["id"]),
                             {"date_extraction": EXTRACTION.isoformat(), "forcer": True})
    assert ok["statut"] == "IMPORTE"


@pytest.mark.asyncio
async def test_ligne_invalide_rejetee_les_autres_importees(db):
    svc = await _svc(db)
    contenu = classeur(brute("000001", "00000100001"), brute("", "00000100002", RAISON_SOCIAL="X"))
    a = await svc.analyser(contenu, "rejet.xlsx")
    assert a["nb_rejets"] >= 1
    c = await svc.confirmer(uuid.UUID(a["id"]), {"date_extraction": EXTRACTION.isoformat()})
    assert c["comptes_crees"] == 1
