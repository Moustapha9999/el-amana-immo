"""Reporting EER sur PostgreSQL — SUMIFS par agence / profil, COUNTIFS état du compte, taux historique.

Exécuté uniquement sur une copie (bea_digital_eer_test), jamais sur la base réelle ``bea_digital``.
Les dossiers sont insérés dans une transaction annulée à la fin, sur une plage de dates EER
réservée (1901) pour isoler les comptages des dossiers déjà présents sur la copie.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import product

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models import Agence, EerDossier, EerPartie, User
from app.services.eer.conformite_historique import Classement, classer_bea, classer_excel
from app.services.eer_access import EerScope
from app.services.eer_lecture_service import EerLectureService, FiltresDossiers
from app.services.eer_reporting_service import EerReportingService

JOUR = date(1901, 3, 15)
PLAGE = {"date_debut": date(1901, 1, 1), "date_fin": date(1901, 12, 31)}
C, NC, INC = "CONFORME", "NON_CONFORME", "INCOMPLET"


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            base = await conn.scalar(text("SELECT current_database()"))
            pret = await conn.scalar(text("SELECT to_regclass('public.eer_dossiers') IS NOT NULL"))
    except Exception:
        base, pret = None, False
    if not pret or base == "bea_digital":
        await engine.dispose()
        pytest.skip("Reporting EER : copie de base avec tables EER requise (jamais la base réelle)")
    session = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _scope() -> EerScope:
    return EerScope(user_id=uuid.uuid4(), agence_id=None, toutes_agences=True, permissions=frozenset())


class _Fabrique:
    def __init__(self, db: AsyncSession, createur: User):
        self.db, self.createur = db, createur

    async def dossier(self, agence: Agence, *, physique=None, systeme=None, decision=None, type_client="PP",
                      profil="SALARIE", statut="EN_CONTROLE", etat_compte=None, ppe=False, jour=JOUR,
                      soumis=True) -> EerDossier:
        partie = EerPartie(nature="PHYSIQUE" if type_client == "PP" else "MORALE", nom="Test reporting")
        self.db.add(partie)
        await self.db.flush()
        d = EerDossier(
            reference=f"T{uuid.uuid4().hex[:15]}", operation_type="ENTREE_RELATION", agence_id=agence.id,
            type_client_code=type_client, profil_code=profil, client_partie_id=partie.id, date_eer=jour,
            statut=statut, created_by_id=self.createur.id, parametres_snapshot={}, version_courante=1,
            revision=0, nb_relances=0, moment_controle="PREALABLE", ppe_dossier=ppe, fatca_dossier=False,
            avis_requis=False, conformite_physique=physique, conformite_systeme=systeme,
            decision_globale=decision, etat_compte=etat_compte,
            motif_abandon="test" if statut == "ABANDONNE" else None,
            soumis_le=datetime.now(UTC) if soumis else None)
        self.db.add(d)
        await self.db.flush()
        return d


async def _contexte(db: AsyncSession) -> tuple[_Fabrique, list[Agence]]:
    agences = list((await db.scalars(select(Agence).where(Agence.is_active.is_(True), Agence.deleted_at.is_(None))
                                     .order_by(Agence.code).limit(3))).all())
    createur = await db.scalar(select(User).where(User.is_active.is_(True)).limit(1))
    if len(agences) < 3 or createur is None:
        pytest.skip("Trois agences actives et un utilisateur nécessaires")
    return _Fabrique(db, createur), agences


def _filtres(**kw) -> FiltresDossiers:
    return FiltresDossiers(**PLAGE, **kw)


@pytest.mark.asyncio
async def test_global_taux_hors_non_evalues_et_abandons_exclus(db: AsyncSession):
    f, (a, _, _) = await _contexte(db)
    svc = EerReportingService(db)
    vide = await svc.global_(_scope(), _filtres())
    # Test 9 : aucun dossier classé → taux non calculable, aucune division par zéro.
    assert vide["total"] == 0 and vide["excel"]["taux"] is None and vide["bea"]["taux"] is None

    for _ in range(20):
        await f.dossier(a, physique=C, systeme=C, decision=C)
    for _ in range(30):
        await f.dossier(a, physique=NC, systeme=C, decision=NC)
    for _ in range(50):
        await f.dossier(a, physique=C, systeme=None)
    # Abandonnés : conservés, exclus des KPI de conformité, comptés dans le flux.
    await f.dossier(a, physique=C, systeme=C, decision=C, statut="ABANDONNE")
    await f.dossier(a, statut="ABANDONNE", soumis=False)

    k = await svc.global_(_scope(), _filtres())
    # Test 8 : 20 / (20 + 30) = 40 %, et non 20 / 100.
    assert k["total"] == 100
    assert k["excel"] == {"total": 100, "conformes": 20, "non_conformes": 30, "non_evalues": 50,
                          "taux": Decimal("40.00")}
    assert k["bea"]["taux"] == Decimal("40.00") and k["divergences"] == 0
    assert k["flux"]["abandonnes"] == 2 and k["flux"]["abandonnes_apres_reception"] == 1
    assert k["flux"]["recus"] == 101 and k["flux"]["taux_abandon"] == Decimal("0.99")


@pytest.mark.asyncio
async def test_sql_identique_a_la_regle_python_et_divergence(db: AsyncSession):
    f, (a, _, _) = await _contexte(db)
    combinaisons = list(product((C, NC, INC, None), repeat=2))
    for physique, systeme in combinaisons:
        await f.dossier(a, physique=physique, systeme=systeme, decision=physique)
    attendu = [classer_excel(p, s) for p, s in combinaisons]
    k = await EerReportingService(db).global_(_scope(), _filtres())
    assert k["excel"]["conformes"] == sum(r.code_conforme for r in attendu)
    assert k["excel"]["non_conformes"] == sum(r.code_non_conforme for r in attendu)
    assert k["divergences"] == sum(r.classement != classer_bea(p) for r, (p, _) in zip(attendu, combinaisons))
    lecture = EerLectureService(db)
    for classement in Classement:
        lignes, total = await lecture.lister(_scope(), _filtres(conformite_excel=classement), page=1, size=100,
                                             tri="created_at", ordre="asc")
        assert total == sum(r.classement == classement for r in attendu)
        assert all(l["conformite_excel"] == classement for l in lignes)
        assert all(l["code_conforme"] + l["code_non_conforme"] <= 1 for l in lignes)


@pytest.mark.asyncio
async def test_reporting_par_agence_sumifs(db: AsyncSession):
    # Test 10 : SUM(S), SUM(T) et taux par agence ; agence sans dossier listée avec taux non calculable.
    f, (a1, a2, a3) = await _contexte(db)
    for _ in range(3):
        await f.dossier(a1, physique=C, systeme=C, decision=C)
    await f.dossier(a1, physique=C, systeme=NC, decision=NC)
    await f.dossier(a1)
    await f.dossier(a2, physique=NC, systeme=NC, decision=NC)
    await f.dossier(a2, physique=None, systeme=C)
    r = await EerReportingService(db).par_agence(_scope(), _filtres())
    lignes = {l["agence_id"]: l for l in r["lignes"]}
    assert r["nature"] == "HISTORIQUE_EXCEL"
    assert lignes[a1.id]["excel"] == {"total": 5, "conformes": 3, "non_conformes": 1, "non_evalues": 1,
                                      "taux": Decimal("75.00")}
    assert lignes[a2.id]["excel"] == {"total": 2, "conformes": 0, "non_conformes": 1, "non_evalues": 1,
                                      "taux": Decimal("0.00")}
    assert lignes[a3.id]["total"] == 0 and lignes[a3.id]["excel"]["taux"] is None
    assert r["total"]["excel"]["conformes"] == 3 and r["total"]["excel"]["non_conformes"] == 2
    assert r["total"]["excel"]["taux"] == Decimal("60.00")


@pytest.mark.asyncio
async def test_reporting_par_profil_libelles_excel(db: AsyncSession):
    # Test 11 : même contrôle par colonne Excel « PROFIL » (= type client).
    f, (a, _, _) = await _contexte(db)
    await f.dossier(a, physique=C, systeme=C, decision=C)
    await f.dossier(a, physique=NC, systeme=C, decision=NC)
    await f.dossier(a, physique=C, systeme=C, decision=C, type_client="PM_PRIVEE", profil="SARL")
    await f.dossier(a, physique=C, systeme=C, decision=C, type_client="PM_PRIVEE", profil="SARL")
    await f.dossier(a, physique=None, systeme=None, type_client="ASSOCIATION", profil="ONG")
    r = await EerReportingService(db).par_profil(_scope(), _filtres())
    lignes = {l["code"]: l for l in r["lignes"]}
    assert [l["libelle"] for l in r["lignes"]] == ["Personne_Physique", "Personne_Morale_Privée",
                                                   "Personne_Morale_Publique", "Personne_Morale_Association"]
    assert lignes["PP"]["excel"]["taux"] == Decimal("50.00") and lignes["PP"]["profil_technique"] == "PP"
    assert lignes["PM_PRIVEE"]["excel"]["conformes"] == 2 and lignes["PM_PRIVEE"]["profil_technique"] == "PM"
    assert lignes["ASSOCIATION"]["excel"]["non_evalues"] == 1 and lignes["ASSOCIATION"]["excel"]["taux"] is None
    assert lignes["PM_PUBLIQUE"]["total"] == 0
    assert r["total"]["excel"]["taux"] == Decimal("75.00")


@pytest.mark.asyncio
async def test_etat_compte_independant_de_s_et_t(db: AsyncSession):
    # Test 12 : COUNTIFS sur l'état du compte ; la conformité n'y entre pas.
    f, (a, _, _) = await _contexte(db)
    await f.dossier(a, physique=NC, systeme=NC, decision=NC, etat_compte="ACTIF")
    await f.dossier(a, physique=None, systeme=None, etat_compte="ACTIF")
    await f.dossier(a, physique=C, systeme=C, decision=C, etat_compte="BLOQUE")
    await f.dossier(a, physique=C, systeme=C, decision=C)
    await f.dossier(a, etat_compte="ACTIF", statut="ABANDONNE")
    r = await EerReportingService(db).etats_compte(_scope(), _filtres())
    lignes = {l["code"]: l for l in r["lignes"]}
    assert [l["libelle"] for l in r["lignes"]] == ["Actif", "Inactif", "Bloqué", "Fermé"]
    assert lignes["ACTIF"]["nombre"] == 2 and lignes["BLOQUE"]["nombre"] == 1 and lignes["FERME"]["nombre"] == 0
    assert r["total"] == 3 and r["non_renseignes"] == 1
    assert lignes["ACTIF"]["pourcentage"] == Decimal("66.67") and lignes["INACTIF"]["pourcentage"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_extensions_periode_et_dimensions(db: AsyncSession):
    f, (a, _, _) = await _contexte(db)
    await f.dossier(a, physique=C, systeme=C, decision=C, jour=date(1901, 3, 1), ppe=True)
    await f.dossier(a, physique=NC, systeme=C, decision=NC, jour=date(1901, 3, 20))
    await f.dossier(a, physique=C, systeme=C, decision=C, jour=date(1901, 5, 2))
    svc = EerReportingService(db)
    serie = await svc.serie(_scope(), _filtres(), "mois")
    assert serie["nature"] == "EXTENSION_BEA_DIGITAL"
    assert [(l["periode"], l["excel"]["taux"]) for l in serie["lignes"]] == [
        (date(1901, 3, 1), Decimal("50.00")), (date(1901, 5, 1), Decimal("100.00"))]
    ppe = {l["code"]: l for l in (await svc.par_dimension(_scope(), _filtres(), "ppe"))["lignes"]}
    assert ppe["OUI"]["excel"]["conformes"] == 1 and ppe["NON"]["total"] == 2
