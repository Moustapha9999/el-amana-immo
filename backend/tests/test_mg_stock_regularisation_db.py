"""Stock — réouverture de période, saisie rétroactive et reclôture, sur PostgreSQL.

Données SYNTHÉTIQUES uniquement, sur la base isolée ``bea_digital_stock_test`` (schéma seul, migrée) :
chaque test vide les tables du module puis reconstruit son jeu de données. Ignoré sur toute autre base.

Scénario de départ (M = mois courant) :
    M-3 : entrée 100      → stock final 100 (clôturée)
    M-2 : sortie 30       → stock final  70 (clôturée)
    M-1 : sortie 20       → stock final  50 (clôturée)
    M   : ouverte, stock initial 50 ; stock actuel de l'article = 50
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api.v1.endpoints import mg_stock as ep
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models.associations import role_permissions_table, user_roles_table
from app.models.auth import Agence, Permission, Role, User
from app.models.audit import AuditLog
from app.models.mg_stock import (
    MgArticle,
    MgArticleFamille,
    MgStockMotifSortie,
    MgStockMouvement,
    MgStockPeriode,
    MgStockPeriodeEvenement,
    MgStockSolde,
)
from app.schemas.mg_stock import MouvementCreate, MouvementUpdate, PeriodeReopenIn, SortieCreate
from app.services.mg_stock_periodes import CLOTUREE, OUVERTE, ROUVERTE, MgStockPeriodeService
from app.services.mg_stock_service import MgStockService
from app.services.mg_stock_sorties import MgStockSortieService

BASE_TEST = "bea_digital_stock_test"
DOMAINE = "@synthetique-stock.test"
PREFIXE_ROLE = "tst-stock-"
AGENCE = "TST01"
# Vidées dans cet ordre (clés étrangères) ; jamais de TRUNCATE CASCADE (tables protégées par trigger).
TABLES_STOCK = (
    "mg_stock_periode_evenements", "mg_stock_soldes", "mg_stock_alertes", "mg_stock_mouvements",
    "mg_inventaire_lignes", "mg_inventaires", "mg_stock_periodes", "mg_articles", "mg_article_familles",
    "mg_stock_motifs_sortie", "mg_stock_parametres",
)
# Tables partagées avec les autres modules : seules les lignes synthétiques de ce fichier sont supprimées.
_SYNTH = f"SELECT id FROM users WHERE email LIKE '%{DOMAINE}'"
NETTOYAGE_PARTAGE = (
    f"DELETE FROM audit_logs WHERE entity LIKE 'mg\\_stock%' OR user_id IN ({_SYNTH})",
    f"DELETE FROM notifications WHERE user_id IN ({_SYNTH}) OR actor_user_id IN ({_SYNTH})",
    f"DELETE FROM auth_sessions WHERE user_id IN ({_SYNTH})",
    f"DELETE FROM user_roles WHERE user_id IN ({_SYNTH})",
    f"DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE code LIKE '{PREFIXE_ROLE}%')",
    f"DELETE FROM roles WHERE code LIKE '{PREFIXE_ROLE}%'",
    f"DELETE FROM agences WHERE code = '{AGENCE}'",
    f"DELETE FROM users WHERE email LIKE '%{DOMAINE}'",
)


async def _vider(engine) -> None:
    async with engine.begin() as conn:
        for table in TABLES_STOCK:
            await conn.execute(text(f"DELETE FROM {table}"))
        for requete in NETTOYAGE_PARTAGE:
            await conn.execute(text(requete))
PERMS_ADMIN = (
    "mg.stock.view",
    "mg.stock.entry",
    "mg.stock.exit",
    "mg.stock.period.view",
    "mg.stock.period.close",
    "mg.stock.period.reopen",
)
PERMS_MAGASINIER = ("mg.stock.view", "mg.stock.entry", "mg.stock.exit", "mg.stock.period.view")
MOTIF = "Facture fournisseur du mois oubliée"


def _url() -> str:
    url = get_settings().database_url.replace("@localhost:", "@127.0.0.1:")
    return url.rsplit("/", 1)[0] + "/" + BASE_TEST


def _mois(decalage: int) -> tuple[int, int]:
    today = date.today()
    index = today.year * 12 + today.month - 1 - decalage
    return index // 12, index % 12 + 1


def _jour(decalage: int, jour: int) -> datetime:
    annee, mois = _mois(decalage)
    return datetime(annee, mois, jour, 12, tzinfo=timezone.utc)


def _requete() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b"",
                    "client": ("127.0.0.1", 1)})


@pytest.fixture
async def moteur():
    engine = create_async_engine(_url(), pool_size=3)
    try:
        async with engine.connect() as conn:
            base = await conn.scalar(text("SELECT current_database()"))
            pret = await conn.scalar(text("SELECT to_regclass('public.mg_stock_periode_evenements') IS NOT NULL"))
    except Exception:
        await engine.dispose()
        pytest.skip(f"Base isolée {BASE_TEST} indisponible")
    if base != BASE_TEST or not pret:
        await engine.dispose()
        pytest.skip(f"Base isolée {BASE_TEST} absente ou non migrée")
    await _vider(engine)
    try:
        yield engine
    finally:
        await _vider(engine)
        await engine.dispose()


@pytest.fixture
def sessions(moteur):
    return async_sessionmaker(moteur, expire_on_commit=False)


async def _utilisateur(db, code: str, perms: tuple[str, ...]) -> User:
    user = User(email=f"{code}{DOMAINE}", full_name=f"Test {code}", hashed_password="x")
    role = Role(code=f"{PREFIXE_ROLE}{code}", label=code)
    db.add_all([user, role])
    await db.flush()
    for p in perms:
        perm_id = await db.scalar(select(Permission.id).where(Permission.code == p))
        if perm_id is None:
            perm = Permission(code=p, label=p, module="stock-fournitures")
            db.add(perm)
            await db.flush()
            perm_id = perm.id
        await db.execute(insert(role_permissions_table).values(role_id=role.id, permission_id=perm_id))
    await db.execute(insert(user_roles_table).values(user_id=user.id, role_id=role.id))
    return user


@pytest.fixture
async def monde(sessions):
    """Jeu de données synthétique committé : 3 périodes clôturées, la période courante ouverte."""
    async with sessions() as db:
        admin = await _utilisateur(db, "admin", PERMS_ADMIN)
        magasinier = await _utilisateur(db, "magasinier", PERMS_MAGASINIER)
        famille = MgArticleFamille(code="TST", libelle="Famille test")
        agence = Agence(code=AGENCE, libelle="Agence test")
        motif = MgStockMotifSortie(code="TST-SORTIE", sens="SORTIE", libelle="Consommation test")
        db.add_all([famille, agence, motif])
        await db.flush()
        article = MgArticle(code="TST-0001", designation="Ramette test", famille_id=famille.id, uom="U",
                            stock_actuel=Decimal("0"))
        db.add(article)
        await db.flush()

        psvc = MgStockPeriodeService(db)
        await psvc._create_periode(*_mois(3), user=admin, precedente=None)
        await psvc.ensure_open_periode(admin)
        await db.commit()

        svc = MgStockService(db)
        await svc._apply_mouvement(article=article, type_mouvement="ENTREE", quantite=Decimal("100"),
                                   agence_id=None, initiateur=admin, date_mouvement=_jour(3, 5))
        await db.commit()
        sorties = MgStockSortieService(db)
        for decalage, qty in ((2, "30"), (1, "20")):
            await sorties.creer(_sortie(article, agence, motif, qty, _jour(decalage, 10)), magasinier)
        ids = {}
        for decalage in (3, 2, 1):
            periode = await psvc.periode_for_date(_jour(decalage, 1))
            await psvc.cloturer(periode.id, admin)
            await db.commit()
            ids[decalage] = periode.id
        ids[0] = (await psvc.periode_for_date(_jour(0, 1))).id
    return SimpleNamespace(admin=admin, magasinier=magasinier, article=article, agence=agence, motif=motif,
                           periodes=ids)


def _sortie(article, agence, motif, qty, quand, **kw) -> SortieCreate:
    return SortieCreate(article_id=article.id, quantite=Decimal(qty), destination_type="AGENCE",
                        agence_id=agence.id, demandeur_nom="Agent Synthétique", motif_id=motif.id,
                        date_mouvement=quand, **kw)


def _entree(article, qty, quand) -> MouvementCreate:
    return MouvementCreate(article_id=article.id, type_mouvement="ENTREE", quantite=Decimal(qty),
                           date_mouvement=quand, motif="Régularisation test")


async def _solde(db, periode_id, article_id) -> MgStockSolde:
    return await db.scalar(
        select(MgStockSolde)
        .where(MgStockSolde.periode_id == periode_id, MgStockSolde.article_id == article_id)
        .execution_options(populate_existing=True)
    )


async def _periode(db, periode_id) -> MgStockPeriode:
    return await db.scalar(
        select(MgStockPeriode).where(MgStockPeriode.id == periode_id).execution_options(populate_existing=True)
    )


async def _evenements(db, periode_id) -> list[MgStockPeriodeEvenement]:
    return list((await db.scalars(
        select(MgStockPeriodeEvenement)
        .where(MgStockPeriodeEvenement.periode_id == periode_id)
        .order_by(MgStockPeriodeEvenement.created_at)
    )).all())


async def _stock(db, article_id) -> Decimal:
    return await db.scalar(
        select(MgArticle.stock_actuel).where(MgArticle.id == article_id).execution_options(populate_existing=True)
    )


async def _rouvrir(db, m, decalage=2, motif=MOTIF, user=None):
    return await ep.rouvrir_periode(m.periodes[decalage], PeriodeReopenIn(motif=motif), _requete(), db,
                                    user or m.admin)


async def _chaine(db, m) -> list[tuple]:
    """(stock initial, stock théorique, stock final) de M-3 à M."""
    out = []
    for decalage in (3, 2, 1, 0):
        s = await _solde(db, m.periodes[decalage], m.article.id)
        out.append((s.stock_initial, s.stock_theorique, s.stock_final))
    return out


# ---------------------------------------------------------------- état initial
async def test_scenario_initial_coherent(sessions, monde):
    async with sessions() as db:
        assert await _chaine(db, monde) == [
            (Decimal("0"), Decimal("100"), Decimal("100")),
            (Decimal("100"), Decimal("70"), Decimal("70")),
            (Decimal("70"), Decimal("50"), Decimal("50")),
            (Decimal("50"), Decimal("50"), None),
        ]
        assert await _stock(db, monde.article.id) == Decimal("50")
        statuts = [(await _periode(db, monde.periodes[d])).statut for d in (3, 2, 1, 0)]
        assert statuts == [CLOTUREE, CLOTUREE, CLOTUREE, OUVERTE]


# ------------------------------------------------------- 1. réouverture autorisée
async def test_01_reouverture_autorisee(sessions, monde):
    async with sessions() as db:
        avant = await _periode(db, monde.periodes[2])
        cloture_initiale = avant.cloture_at
        resultat = await _rouvrir(db, monde)
        assert resultat["statut"] == ROUVERTE
        assert [p["libelle"] for p in resultat["impact"]["periodes_suivantes"]] == [
            (await _periode(db, monde.periodes[1])).libelle,
            (await _periode(db, monde.periodes[0])).libelle,
        ]
    async with sessions() as db:
        p = await _periode(db, monde.periodes[2])
        assert p.statut == ROUVERTE
        assert p.cloture_at == cloture_initiale  # la clôture précédente n'est pas effacée
        assert p.premiere_cloture_at == cloture_initiale
        assert (p.reopen_by, p.reopen_motif, p.nb_reouvertures) == (monde.admin.id, MOTIF, 1)
        evts = await _evenements(db, p.id)
        assert [(e.action, e.resultat) for e in evts] == [("CLOTURE", "SUCCES"), ("REOUVERTURE", "SUCCES")]
        assert evts[1].user_nom == "Test admin" and evts[1].motif == MOTIF
        assert "instantane" in evts[1].details
        audit = await db.scalar(select(AuditLog).where(AuditLog.action == "reouverture_periode"))
        assert audit is not None and audit.after_data["motif"] == MOTIF
        # Les autres périodes ne sont ni rouvertes ni clôturées d'office.
        assert (await _periode(db, monde.periodes[1])).statut == CLOTUREE
        assert (await _periode(db, monde.periodes[0])).statut == OUVERTE


# --------------------------------------------- 2. refus utilisateur non autorisé
async def test_02_reouverture_refusee_sans_permission(sessions, monde):
    async with sessions() as db:
        with pytest.raises(AppError) as exc:
            await _rouvrir(db, monde, user=monde.magasinier)
        assert (exc.value.status_code, exc.value.code) == (403, "PERMISSION_REFUSEE")
    async with sessions() as db:
        p = await _periode(db, monde.periodes[2])
        assert p.statut == CLOTUREE and p.nb_reouvertures == 0
        echec = (await _evenements(db, p.id))[-1]
        assert (echec.action, echec.resultat, echec.user_id) == ("REOUVERTURE_REFUSEE", "ECHEC", monde.magasinier.id)
        assert "mg.stock.period.reopen" in echec.details["erreur"]
        assert await db.scalar(select(func.count()).select_from(AuditLog)
                               .where(AuditLog.action == "reouverture_refusee")) == 1


# ------------------------------------------------------------ 3. refus sans motif
@pytest.mark.parametrize("motif", ["", "   ", "abc"])
async def test_03_reouverture_refusee_sans_motif(sessions, monde, motif):
    async with sessions() as db:
        with pytest.raises(AppError) as exc:
            await _rouvrir(db, monde, motif=motif)
        assert exc.value.code == "MOTIF_OBLIGATOIRE"
    async with sessions() as db:
        p = await _periode(db, monde.periodes[2])
        assert p.statut == CLOTUREE
        assert (await _evenements(db, p.id))[-1].action == "REOUVERTURE_REFUSEE"


# ------------------------------------------------- 4. mouvement rétroactif valide
async def test_04_mouvement_retroactif_valide(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        quand = _jour(2, 20)
        mvt = await MgStockService(db).create_mouvement(_entree(monde.article, "10", quand), monde.admin,
                                                         regularisation_autorisee=True)
        assert mvt.periode_id == monde.periodes[2]
        assert mvt.date_mouvement == quand
        assert mvt.created_at.date() == date.today()  # date d'enregistrement distincte
        enrichi = (await MgStockService(db).enrich_mouvements([mvt]))[0]
        assert enrichi["saisie_retroactive"] is True
        assert enrichi["periode_statut"] == ROUVERTE
        assert await _stock(db, monde.article.id) == Decimal("60")


# ----------------------------------------------------- 5. mouvement invalide refusé
async def test_05_mouvements_invalides_refuses(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        svc = MgStockService(db)
        cas = [
            (_entree(monde.article, "5", _jour(3, 15)), True, "PERIODE_CLOTUREE"),
            (_entree(monde.article, "5", datetime(2099, 1, 1, tzinfo=timezone.utc)), True, "MVT_DATE_FUTURE"),
            (_entree(monde.article, "5", _jour(2, 15)), False, "PERIODE_ROUVERTE_RESERVEE"),
        ]
        for data, autorise, code in cas:
            with pytest.raises(AppError) as exc:
                await svc.create_mouvement(data, monde.admin, regularisation_autorisee=autorise)
            assert exc.value.code == code
            await db.rollback()

        # Sortie antidatée qui rendrait le stock négatif avant une sortie déjà enregistrée.
        await svc.create_mouvement(_entree(monde.article, "100", None), monde.admin)  # stock 150 aujourd'hui
        with pytest.raises(AppError) as exc:
            await MgStockSortieService(db).creer(
                _sortie(monde.article, monde.agence, monde.motif, "80", _jour(2, 1)), monde.admin,
                regularisation_autorisee=True,
            )
        assert exc.value.code == "STOCK_NEGATIF_HISTORIQUE"
        await db.rollback()
        assert await _stock(db, monde.article.id) == Decimal("150")
        assert (await _solde(db, monde.periodes[2], monde.article.id)).sorties == Decimal("30")


async def test_05b_stock_controle_en_fin_de_journee(sessions, monde):
    """Sortie du jour J saisie après coup : la livraison du même jour (heure plus tardive) la couvre."""
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        await MgStockService(db).create_mouvement(
            _entree(monde.article, "50", _jour(2, 20).replace(hour=15, minute=42)), monde.admin,
            regularisation_autorisee=True,
        )
        sorties = MgStockSortieService(db)
        with pytest.raises(AppError) as exc:  # la veille, le stock (70) ne couvre pas 100
            await sorties.creer(_sortie(monde.article, monde.agence, monde.motif, "100", _jour(2, 19)), monde.admin,
                                regularisation_autorisee=True)
        assert exc.value.code == "STOCK_NEGATIF_HISTORIQUE"
        await db.rollback()
        # Même jour que la livraison, heure par défaut (12:00) antérieure : fin de journée = 70 + 50 − 100.
        await sorties.creer(_sortie(monde.article, monde.agence, monde.motif, "100", _jour(2, 20)), monde.admin,
                            regularisation_autorisee=True)
    async with sessions() as db:
        assert (await _solde(db, monde.periodes[2], monde.article.id)).stock_theorique == Decimal("20")
        assert await _stock(db, monde.article.id) == Decimal("0")
        psvc = MgStockPeriodeService(db)
        assert await psvc.premier_solde_negatif(await _periode(db, monde.periodes[2]), monde.article.id) is None


# ------------------------------------------------------------------ 6. doublons
async def test_06_doublon_probable(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        sorties = MgStockSortieService(db)
        meme = _sortie(monde.article, monde.agence, monde.motif, "30", _jour(2, 10))
        with pytest.raises(AppError) as exc:
            await sorties.creer(meme, monde.admin, regularisation_autorisee=True)
        assert (exc.value.status_code, exc.value.code) == (409, "DOUBLON_PROBABLE")
        await db.rollback()

        sans_justif = _sortie(monde.article, monde.agence, monde.motif, "30", _jour(2, 10), doublon_confirme=True)
        with pytest.raises(AppError) as exc:
            await sorties.creer(sans_justif, monde.admin, regularisation_autorisee=True)
        assert exc.value.code == "OBSERVATION_OBLIGATOIRE"
        await db.rollback()

        confirme = _sortie(monde.article, monde.agence, monde.motif, "30", _jour(2, 10), doublon_confirme=True,
                           observation="Deuxième remise distincte, bon n° 42")
        mvt, rejoue = await sorties.creer(confirme, monde.admin, cle_idempotence="cle-test-1",
                                          regularisation_autorisee=True)
        assert not rejoue
        # Double envoi (même clé d'idempotence) : aucun second mouvement.
        mvt2, rejoue2 = await sorties.creer(confirme, monde.admin, cle_idempotence="cle-test-1",
                                            regularisation_autorisee=True)
        assert rejoue2 and mvt2.id == mvt.id
        assert (await _solde(db, monde.periodes[2], monde.article.id)).sorties == Decimal("60")
        assert await _stock(db, monde.article.id) == Decimal("20")


# ------------------------------------- 7. recalcul des soldes après saisie rétroactive
async def test_07_recalcul_exact_des_soldes(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        await MgStockService(db).create_mouvement(_entree(monde.article, "10", _jour(2, 20)), monde.admin,
                                                  regularisation_autorisee=True)
    async with sessions() as db:
        assert await _chaine(db, monde) == [
            (Decimal("0"), Decimal("100"), Decimal("100")),  # période antérieure inchangée
            (Decimal("100"), Decimal("80"), Decimal("80")),
            (Decimal("80"), Decimal("60"), Decimal("60")),
            (Decimal("60"), Decimal("60"), None),
        ]
        # Le dernier stock théorique de la chaîne = stock actuel (rejoué à partir des mouvements).
        assert await _stock(db, monde.article.id) == Decimal("60")
        mvts = (await db.execute(select(MgStockMouvement.type_mouvement, MgStockMouvement.quantite)
                                 .where(MgStockMouvement.article_id == monde.article.id))).all()
        total = sum((q if t == "ENTREE" else -q) for t, q in mvts)
        assert total == Decimal("60")


# ------------------------------------- 8. sortie enregistrée après cette entrée
async def test_08_sortie_apres_entree_retroactive(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        sorties = MgStockSortieService(db)
        with pytest.raises(AppError) as exc:  # sans l'entrée oubliée, le stock (50) ne suffit pas
            await sorties.creer(_sortie(monde.article, monde.agence, monde.motif, "60", None), monde.magasinier)
        assert exc.value.code == "STOCK_INSUFFISANT"
        await db.rollback()
        await MgStockService(db).create_mouvement(_entree(monde.article, "10", _jour(2, 20)), monde.admin,
                                                  regularisation_autorisee=True)
        # Sortie antidatée dans la période rouverte, après l'entrée régularisée…
        await sorties.creer(_sortie(monde.article, monde.agence, monde.motif, "5", _jour(2, 25)), monde.admin,
                            regularisation_autorisee=True)
        # … puis sortie du jour par un magasinier, qui consomme le stock régularisé.
        await sorties.creer(_sortie(monde.article, monde.agence, monde.motif, "55", None), monde.magasinier)
    async with sessions() as db:
        assert await _stock(db, monde.article.id) == Decimal("0")
        chaine = await _chaine(db, monde)
        assert chaine[1] == (Decimal("100"), Decimal("75"), Decimal("75"))
        assert chaine[3] == (Decimal("55"), Decimal("0"), None)
        psvc = MgStockPeriodeService(db)
        assert await psvc.premier_solde_negatif(await _periode(db, monde.periodes[3]), monde.article.id) is None


# ----------------------------------------------------- 9. périodes suivantes
async def test_09_impact_sur_les_periodes_suivantes(sessions, monde):
    async with sessions() as db:
        # Comptage physique déjà validé sur M-1 (50, conforme).
        await db.execute(update(MgStockSolde)
                         .where(MgStockSolde.periode_id == monde.periodes[1],
                                MgStockSolde.article_id == monde.article.id)
                         .values(stock_physique=Decimal("50"), ecart=Decimal("0")))
        await db.commit()
        apercu = await MgStockPeriodeService(db).preview_reouverture(monde.periodes[2])
        assert apercu["peut_rouvrir"]
        assert len(apercu["periodes_suivantes"]) == 2
        await _rouvrir(db, monde)
    async with sessions() as db:
        await MgStockService(db).create_mouvement(_entree(monde.article, "10", _jour(2, 20)), monde.admin,
                                                  regularisation_autorisee=True)
    async with sessions() as db:
        m1 = await _solde(db, monde.periodes[1], monde.article.id)
        assert (m1.stock_initial, m1.stock_theorique) == (Decimal("80"), Decimal("60"))
        assert (m1.stock_physique, m1.ecart, m1.stock_final) == (Decimal("50"), Decimal("-10"), Decimal("50"))
        assert (await _solde(db, monde.periodes[0], monde.article.id)).stock_initial == Decimal("60")
        preview = await MgStockPeriodeService(db).preview_cloture(monde.periodes[2])
        suivantes = preview["regularisation"]["periodes_suivantes"]
        assert [s["variation_stock_initial"] for s in suivantes] == [10.0, 10.0]
        assert any("comptage(s) physique(s)" in a for a in preview["avertissements"])


# ------------------------------------------------------- 10. reclôture réussie
async def test_10_recloture_reussie(sessions, monde):
    async with sessions() as db:
        initiale = (await _periode(db, monde.periodes[2])).cloture_at
        await _rouvrir(db, monde)
    async with sessions() as db:
        await MgStockService(db).create_mouvement(_entree(monde.article, "10", _jour(2, 20)), monde.admin,
                                                  regularisation_autorisee=True)
    async with sessions() as db:
        preview = await MgStockPeriodeService(db).preview_cloture(monde.periodes[2])
        assert not preview["bloquant"], preview["anomalies"]
        corr = preview["regularisation"]["corrections"]
        assert len(corr) == 1 and corr[0]["date_mouvement"] == _jour(2, 20)
        assert corr[0]["date_enregistrement"].date() == date.today()
        codes = {c["code"]: c["ok"] for c in preview["controles"]}
        assert codes["soldes_mouvements"] and codes["historique_positif"] and codes["coherence_stock_actuel"]
        resultat = await ep.cloturer_periode(monde.periodes[2], _requete(), db, monde.admin)
        assert resultat["reports_corriges"] == 0
    async with sessions() as db:
        p = await _periode(db, monde.periodes[2])
        assert p.statut == CLOTUREE and p.cloture_at > initiale and p.premiere_cloture_at == initiale
        assert (await _periode(db, monde.periodes[1])).statut == CLOTUREE
        assert (await _periode(db, monde.periodes[0])).statut == OUVERTE
        assert (await _evenements(db, p.id))[-1].action == "RECLOTURE"
        assert (await _chaine(db, monde))[3] == (Decimal("60"), Decimal("60"), None)
        with pytest.raises(AppError) as exc:  # plus aucune saisie possible après la reclôture
            await MgStockService(db).create_mouvement(_entree(monde.article, "1", _jour(2, 21)), monde.admin,
                                                      regularisation_autorisee=True)
        assert exc.value.code == "PERIODE_CLOTUREE"


# ---------------------------------------------- 11. reclôture bloquée (anomalies)
async def test_11_recloture_bloquee_ecart_inventaire_puis_corrigee(sessions, monde):
    async with sessions() as db:
        await db.execute(update(MgStockSolde)
                         .where(MgStockSolde.periode_id == monde.periodes[2],
                                MgStockSolde.article_id == monde.article.id)
                         .values(stock_physique=Decimal("70"), ecart=Decimal("0")))
        await db.commit()
        await _rouvrir(db, monde)
    async with sessions() as db:
        await MgStockService(db).create_mouvement(_entree(monde.article, "10", _jour(2, 5)), monde.admin,
                                                  regularisation_autorisee=True)
    async with sessions() as db:
        with pytest.raises(AppError) as exc:
            await ep.cloturer_periode(monde.periodes[2], _requete(), db, monde.admin)
        assert (exc.value.status_code, exc.value.code) == (409, "CLOTURE_BLOQUEE")
        assert "TST-0001" in exc.value.message
    async with sessions() as db:
        p = await _periode(db, monde.periodes[2])
        assert p.statut == ROUVERTE
        echec = (await _evenements(db, p.id))[-1]
        assert (echec.action, echec.resultat) == ("CLOTURE_REFUSEE", "ECHEC")
        # Correction : ajustement de -10 daté dans la période → écart d'inventaire inchangé → reclôture.
        article = await db.get(MgArticle, monde.article.id)
        await MgStockService(db)._apply_mouvement(
            article=article, type_mouvement="AJUSTEMENT", quantite=Decimal("-10"), agence_id=None,
            initiateur=monde.admin, motif="Écart constaté au comptage", date_mouvement=_jour(2, 28),
            regularisation_autorisee=True,
        )
        await db.commit()
    async with sessions() as db:
        await ep.cloturer_periode(monde.periodes[2], _requete(), db, monde.admin)
        assert (await _periode(db, monde.periodes[2])).statut == CLOTUREE
        assert await _stock(db, monde.article.id) == Decimal("50")


async def test_11b_recloture_bloquee_solde_incoherent(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        await MgStockService(db).create_mouvement(_entree(monde.article, "10", _jour(2, 20)), monde.admin,
                                                  regularisation_autorisee=True)
        # Altération directe d'un solde (hors application) : détectée et bloquante.
        await db.execute(update(MgStockSolde)
                         .where(MgStockSolde.periode_id == monde.periodes[2],
                                MgStockSolde.article_id == monde.article.id)
                         .values(entrees=Decimal("115")))
        await db.commit()
        preview = await MgStockPeriodeService(db).preview_cloture(monde.periodes[2])
        bloquants = {c["code"] for c in preview["controles"] if c["bloquant"]}
        assert "soldes_mouvements" in bloquants
        with pytest.raises(AppError):
            await ep.cloturer_periode(monde.periodes[2], _requete(), db, monde.admin)


async def test_11c_cloture_dans_l_ordre_chronologique(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde, decalage=3)
    async with sessions() as db:
        # M-2 est clôturée : on ne peut ni la rouvrir en parallèle ni clôturer M (M-3 rouverte).
        apercu = await MgStockPeriodeService(db).preview_reouverture(monde.periodes[2])
        assert not apercu["peut_rouvrir"]
        preview = await MgStockPeriodeService(db).preview_cloture(monde.periodes[0])
        assert {c["code"] for c in preview["controles"] if c["bloquant"]} == {"periodes_anterieures"}


# ------------------------------------------------- 12. historique des clôtures
async def test_12_historique_conserve(sessions, monde):
    async with sessions() as db:
        initiale = (await _periode(db, monde.periodes[2])).premiere_cloture_at
        nb_mvts = await db.scalar(select(func.count()).select_from(MgStockMouvement))
    for i in range(2):
        async with sessions() as db:
            await _rouvrir(db, monde, motif=f"{MOTIF} ({i + 1})")
        async with sessions() as db:
            await MgStockService(db).create_mouvement(_entree(monde.article, "1", _jour(2, 20 + i)), monde.admin,
                                                      regularisation_autorisee=True)
        async with sessions() as db:
            await ep.cloturer_periode(monde.periodes[2], _requete(), db, monde.admin)
    async with sessions() as db:
        p = await _periode(db, monde.periodes[2])
        assert p.nb_reouvertures == 2 and p.premiere_cloture_at == initiale
        actions = [e.action for e in await _evenements(db, p.id)]
        assert actions == ["CLOTURE", "REOUVERTURE", "RECLOTURE", "REOUVERTURE", "RECLOTURE"]
        historique = await MgStockPeriodeService(db).historique(p.id)
        assert [h["action"] for h in historique][0] == "RECLOTURE"
        assert all("instantane" not in h["details"] for h in historique)
        assert [h["motif"] for h in historique if h["action"] == "REOUVERTURE"] == [f"{MOTIF} (2)", f"{MOTIF} (1)"]
        assert await db.scalar(select(func.count()).select_from(MgStockMouvement)) == nb_mvts + 2


# ------------------------------------------------------------- 13. concurrence
async def test_13_reouvertures_concurrentes_serialisees(sessions, monde):
    async with sessions() as a, sessions() as b:
        await MgStockPeriodeService(a).rouvrir(monde.periodes[2], monde.admin, MOTIF)  # verrou tenu
        tache = asyncio.create_task(MgStockPeriodeService(b).rouvrir(monde.periodes[1], monde.admin, MOTIF))
        await asyncio.sleep(1.0)
        assert not tache.done()  # B attend la fin de la transaction de A
        await a.commit()
        with pytest.raises(AppError) as exc:
            await tache
        assert exc.value.code == "REOUVERTURE_IMPOSSIBLE"  # une seule période rouverte à la fois
        await b.rollback()
    async with sessions() as db:
        assert (await _periode(db, monde.periodes[2])).statut == ROUVERTE
        assert (await _periode(db, monde.periodes[1])).statut == CLOTUREE


async def test_13b_cloture_attend_la_saisie_en_cours(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as a, sessions() as b:
        article = await a.get(MgArticle, monde.article.id)
        await MgStockService(a)._apply_mouvement(
            article=article, type_mouvement="ENTREE", quantite=Decimal("10"), agence_id=None,
            initiateur=monde.admin, date_mouvement=_jour(2, 20), regularisation_autorisee=True,
        )
        tache = asyncio.create_task(MgStockPeriodeService(b).cloturer(monde.periodes[2], monde.admin))
        await asyncio.sleep(1.0)
        assert not tache.done()  # la clôture attend la saisie (verrou de période)
        await a.commit()
        resultat = await tache
        await b.commit()
        assert len(resultat["regularisation"]["corrections"]) == 1  # la saisie concurrente est prise en compte
    async with sessions() as db:
        assert (await _chaine(db, monde))[1] == (Decimal("100"), Decimal("80"), Decimal("80"))
        assert await _stock(db, monde.article.id) == Decimal("60")


async def test_13c_saisie_apres_cloture_concurrente_refusee(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as a, sessions() as b:
        await MgStockPeriodeService(a).cloturer(monde.periodes[2], monde.admin)
        tache = asyncio.create_task(MgStockService(b).create_mouvement(
            _entree(monde.article, "10", _jour(2, 20)), monde.admin, regularisation_autorisee=True))
        await asyncio.sleep(1.0)
        assert not tache.done()
        await a.commit()
        with pytest.raises(AppError) as exc:
            await tache
        assert exc.value.code == "PERIODE_CLOTUREE"
        await b.rollback()
    async with sessions() as db:
        assert await _stock(db, monde.article.id) == Decimal("50")


# ------------------------------------------------- 14. permissions backend
async def test_14_permissions_backend(sessions, monde):
    async with sessions() as db:
        with pytest.raises(AppError) as exc:
            await ep.cloturer_periode(monde.periodes[0], _requete(), db, monde.magasinier)
        assert (exc.value.status_code, exc.value.code) == (403, "PERMISSION_REFUSEE")
    async with sessions() as db:
        assert (await _periode(db, monde.periodes[0])).statut == OUVERTE
        assert (await _evenements(db, monde.periodes[0]))[-1].action == "CLOTURE_REFUSEE"
        await _rouvrir(db, monde)
    async with sessions() as db:
        # Formulaire : la période rouverte n'est proposée qu'aux administrateurs.
        mag = await ep._dates_saisie(db, monde.magasinier)
        adm = await ep._dates_saisie(db, monde.admin)
        assert ROUVERTE not in {p["statut"] for p in mag["periodes_saisie"]} and not mag["peut_regulariser"]
        assert ROUVERTE in {p["statut"] for p in adm["periodes_saisie"]} and adm["peut_regulariser"]
        # Saisie et correction dans la période rouverte refusées au magasinier.
        with pytest.raises(AppError) as exc:
            await MgStockSortieService(db).creer(
                _sortie(monde.article, monde.agence, monde.motif, "1", _jour(2, 21)), monde.magasinier,
                regularisation_autorisee=await ep._peut_regulariser(db, monde.magasinier),
            )
        assert (exc.value.status_code, exc.value.code) == (403, "PERIODE_ROUVERTE_RESERVEE")
        await db.rollback()
        mvt_id = await db.scalar(select(MgStockMouvement.id).where(MgStockMouvement.periode_id == monde.periodes[2]))
        with pytest.raises(AppError) as exc:
            await ep.update_mouvement(mvt_id, MouvementUpdate(quantite=Decimal("31")), _requete(), db,
                                      monde.magasinier)
        assert exc.value.code == "PERIODE_ROUVERTE_RESERVEE"
        with pytest.raises(AppError):
            await ep.delete_mouvement(mvt_id, _requete(), False, None, db, monde.magasinier)
        with pytest.raises(HTTPException) as http:
            await ep.delete_mouvement(mvt_id, _requete(), True, "Suppression test", db, monde.magasinier)
        assert http.value.status_code == 403
        await db.rollback()
        assert (await _solde(db, monde.periodes[2], monde.article.id)).sorties == Decimal("30")


def _codes_route(route) -> set[str]:
    codes: set[str] = set()
    pile = list(route.dependant.dependencies)
    while pile:
        dep = pile.pop()
        pile.extend(dep.dependencies)
        for cell in getattr(dep.call, "__closure__", None) or ():
            if isinstance(cell.cell_contents, tuple) and all(isinstance(c, str) for c in cell.cell_contents):
                codes |= set(cell.cell_contents)
    return codes


def test_14b_permissions_des_routes_de_periode():
    routes = {(r.path, tuple(sorted(r.methods))): r for r in ep.router.routes}
    attendu = {
        ("/mg/stock/periodes/{periode_id}/preview-reouverture", ("GET",)): {"mg.stock.period.reopen"},
        ("/mg/stock/periodes/{periode_id}/historique", ("GET",)): {"mg.stock.period.view"},
        ("/mg/stock/periodes/{periode_id}/preview-cloture", ("GET",)): {"mg.stock.view"},
    }
    for cle, codes in attendu.items():
        assert _codes_route(routes[cle]) == codes, cle
    # Réouverture / clôture : permission vérifiée dans l'endpoint (refus journalisés).
    import inspect

    assert 'PERMISSION_REGULARISATION)' in inspect.getsource(ep.rouvrir_periode)
    assert '"mg.stock.period.close"' in inspect.getsource(ep.cloturer_periode)
