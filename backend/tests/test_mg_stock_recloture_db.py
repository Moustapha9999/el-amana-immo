"""Stock — nouvelle clôture d'une période rouverte : écarts d'inventaire, reports, doublons, idempotence.

Données SYNTHÉTIQUES sur la base isolée ``bea_digital_stock_test`` (voir test_mg_stock_regularisation_db).
Reproduit le cas d'Octobre 2026 : période rouverte sans comptage, corrections rétroactives, puis
inventaire ajusté pendant la réouverture (écart final nul) ; l'ancien contrôle bloquait « écart 0 → 0 ».
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.core.exceptions import AppError
from app.models.mg_stock import MgArticle, MgStockMouvement, MgStockSolde
from app.services.mg_stock_periodes import CLOTUREE, MgStockPeriodeService
from app.services.mg_stock_service import MgStockService
from app.services.mg_stock_sorties import MgStockSortieService
from tests.test_mg_stock_regularisation_db import (  # noqa: F401 (fixtures)
    _chaine,
    _entree,
    _evenements,
    _jour,
    _periode,
    _requete,
    _rouvrir,
    _solde,
    _sortie,
    _stock,
    ep,
    monde,
    moteur,
    sessions,
)


def _controles(preview) -> dict[str, dict]:
    return {c["code"]: c for c in preview["controles"]}


async def _preview(db, m, decalage=2):
    return await MgStockPeriodeService(db).preview_cloture(m.periodes[decalage])


async def _comptage(db, m, quantite: Decimal, decalage=2):
    """Comptage physique enregistré sur la période (chemin de l'ajustement d'inventaire)."""
    psvc = MgStockPeriodeService(db)
    article = await db.get(MgArticle, m.article.id)
    await psvc.apply_physique(await _periode(db, m.periodes[decalage]), article, quantite)
    await db.commit()


async def _ajustement(db, m, quantite: str, jour=28, decalage=2):
    article = await db.get(MgArticle, m.article.id)
    await MgStockService(db)._apply_mouvement(
        article=article, type_mouvement="AJUSTEMENT", quantite=Decimal(quantite), agence_id=None,
        initiateur=m.admin, motif="Ajustement inventaire", date_mouvement=_jour(decalage, jour),
        regularisation_autorisee=True,
    )
    await db.commit()


async def _sortie_retro(db, m, qty, jour, demandeur_nom="Agent Synthétique", **kw):
    data = _sortie(m.article, m.agence, m.motif, qty, _jour(2, jour), **kw).model_copy(
        update={"demandeur_nom": demandeur_nom}
    )
    return await MgStockSortieService(db).creer(data, m.admin, regularisation_autorisee=True)


async def _soldes_bruts(db) -> list[tuple]:
    rows = (await db.execute(
        select(MgStockSolde.periode_id, MgStockSolde.stock_initial, MgStockSolde.entrees, MgStockSolde.sorties,
               MgStockSolde.ajustements, MgStockSolde.stock_theorique, MgStockSolde.stock_physique,
               MgStockSolde.ecart, MgStockSolde.stock_final)
        .order_by(MgStockSolde.periode_id).execution_options(populate_existing=True)
    )).all()
    return [tuple(r) for r in rows]


# ------------------------------------- 1. rétroactif antérieur au comptage, écart final nul
async def test_01_retroactif_avant_comptage_ecart_nul(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)  # aucun comptage à la réouverture : écart de référence absent
    async with sessions() as db:
        await _sortie_retro(db, monde, "5", 12)
        # Inventaire ajusté pendant la réouverture : physique compté = théorique recalculé (65).
        await _comptage(db, monde, Decimal("65"))
    async with sessions() as db:
        s = await _solde(db, monde.periodes[2], monde.article.id)
        assert (s.stock_theorique, s.stock_physique, s.ecart) == (Decimal("65"), Decimal("65"), Decimal("0"))
        c = _controles(await _preview(db, monde))["ecarts_inventaire"]
        assert c["ok"] and not c["bloquant"], c["detail"]


# ------------------------------------------- 2. rétroactif provoquant un véritable écart
async def test_02_retroactif_ecart_reel_bloquant(sessions, monde):
    async with sessions() as db:
        await db.execute(update(MgStockSolde)
                         .where(MgStockSolde.periode_id == monde.periodes[2],
                                MgStockSolde.article_id == monde.article.id)
                         .values(stock_physique=Decimal("70"), ecart=Decimal("0")))
        await db.commit()
        await _rouvrir(db, monde)
    async with sessions() as db:
        await _sortie_retro(db, monde, "4", 8)  # antérieure au comptage : théorique 66, physique 70
    async with sessions() as db:
        c = _controles(await _preview(db, monde))["ecarts_inventaire"]
        assert c["bloquant"]
        assert "TST-0001 (théorique 66, physique 70, écart 4)" in c["detail"]
        assert "0 → 0" not in c["detail"]
        # Le physique enregistré n'est jamais modifié silencieusement.
        assert (await _solde(db, monde.periodes[2], monde.article.id)).stock_physique == Decimal("70")


# ---------------------------------------------------- 3. ajustement déjà enregistré
async def test_03_ajustement_deja_enregistre(sessions, monde):
    async with sessions() as db:
        await db.execute(update(MgStockSolde)
                         .where(MgStockSolde.periode_id == monde.periodes[2],
                                MgStockSolde.article_id == monde.article.id)
                         .values(stock_physique=Decimal("68"), ecart=Decimal("-2")))  # écart accepté
        await db.commit()
        await _rouvrir(db, monde)
    async with sessions() as db:
        await MgStockService(db).create_mouvement(_entree(monde.article, "10", _jour(2, 5)), monde.admin,
                                                  regularisation_autorisee=True)
        assert _controles(await _preview(db, monde))["ecarts_inventaire"]["bloquant"]  # écart -12
        await _ajustement(db, monde, "-10")
    async with sessions() as db:
        # L'écart revient à celui accepté à la clôture précédente (-2) : pas d'ajustement artificiel.
        c = _controles(await _preview(db, monde))["ecarts_inventaire"]
        assert c["ok"], c["detail"]
        assert not (await _preview(db, monde))["bloquant"]


# ------------------------------------------- 4. recalculs successifs sans duplication
async def test_04_recalculs_idempotents(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        await _sortie_retro(db, monde, "5", 12)
    async with sessions() as db:
        avant = await _soldes_bruts(db)
        chaine = await _chaine(db, monde)
        for _ in range(3):
            await _preview(db, monde)
            await MgStockPeriodeService(db).bootstrap_soldes(await _periode(db, monde.periodes[2]))
        await db.commit()
    async with sessions() as db:
        assert await _soldes_bruts(db) == avant
        assert await _chaine(db, monde) == chaine
        assert await _stock(db, monde.article.id) == Decimal("45")


# ------------------------------- 5. report vers la période suivante, 6. stock final positif
async def test_05_report_vers_periode_suivante(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        await _sortie_retro(db, monde, "5", 12)
    async with sessions() as db:
        preview = await _preview(db, monde)
        assert _controles(preview)["reports_suivante"]["ok"]
        assert preview["regularisation"]["periodes_suivantes"][0]["variation_stock_initial"] == -5.0
        resultat = await ep.cloturer_periode(monde.periodes[2], _requete(), db, monde.admin)
        assert resultat["reports_corriges"] == 0
    async with sessions() as db:
        chaine = await _chaine(db, monde)
        assert chaine[1][2] == Decimal("65") and chaine[2][0] == Decimal("65")  # final M-2 = initial M-1
        assert chaine[2][2] == Decimal("45") and chaine[3][0] == Decimal("45")  # final M-1 = initial M
        assert chaine[3][0] > 0


async def test_05b_report_realigne_apres_comptage(sessions, monde):
    """Article compté : la correction ne change pas le stock final (physique) ; la clôture réaligne le report."""
    async with sessions() as db:
        await db.execute(update(MgStockSolde)
                         .where(MgStockSolde.periode_id == monde.periodes[2],
                                MgStockSolde.article_id == monde.article.id)
                         .values(stock_physique=Decimal("70"), ecart=Decimal("0")))
        await db.commit()
        await _rouvrir(db, monde)
    async with sessions() as db:
        await _sortie_retro(db, monde, "5", 12)
        c = _controles(await _preview(db, monde))["reports_suivante"]
        assert not c["ok"] and not c["bloquant"] and "TST-0001 (65 → 70)" in c["detail"]
        await _ajustement(db, monde, "5")  # physique 70 confirmé : écart régularisé
    async with sessions() as db:
        assert _controles(await _preview(db, monde))["reports_suivante"]["ok"]
        await ep.cloturer_periode(monde.periodes[2], _requete(), db, monde.admin)
    async with sessions() as db:
        assert (await _chaine(db, monde))[2][0] == Decimal("70")
        assert await _stock(db, monde.article.id) == Decimal("50")


# ------------------------------------- 7. stock final nul, 8. article qui deviendrait négatif
async def test_07_stock_final_nul(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        await _sortie_retro(db, monde, "50", 12)
    async with sessions() as db:
        assert not (await _preview(db, monde))["bloquant"]
        await ep.cloturer_periode(monde.periodes[2], _requete(), db, monde.admin)
    async with sessions() as db:
        chaine = await _chaine(db, monde)
        assert chaine[1][2] == Decimal("20") and chaine[2][2] == Decimal("0") and chaine[3][0] == Decimal("0")
        assert await _stock(db, monde.article.id) == Decimal("0")


async def test_08_article_qui_deviendrait_negatif(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        await MgStockService(db).create_mouvement(_entree(monde.article, "100", None), monde.admin)  # stock 150
        nb = await db.scalar(select(func.count()).select_from(MgStockMouvement))
        with pytest.raises(AppError) as exc:  # M-1 sort 20 ensuite : 70 − 51 − 20 < 0
            await _sortie_retro(db, monde, "51", 12)
        assert exc.value.code == "STOCK_NEGATIF_HISTORIQUE"
        await db.rollback()
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(MgStockMouvement)) == nb
        assert await _stock(db, monde.article.id) == Decimal("150")


# ----------------------------------------------------------------- 9. / 10. doublons
async def test_09_sorties_identiques_distinctes(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        await _sortie_retro(db, monde, "5", 12, demandeur_nom="Penda")
        await _sortie_retro(db, monde, "5", 12, demandeur_nom="Oumana", doublon_confirme=True,
                            observation="Remise distincte à un autre bénéficiaire")
    async with sessions() as db:
        c = _controles(await _preview(db, monde))["doublons"]
        assert c["ok"], c["detail"]


async def test_10_veritable_doublon_signale_sans_blocage(sessions, monde):
    async with sessions() as db:
        await _rouvrir(db, monde)
    async with sessions() as db:
        await _sortie_retro(db, monde, "5", 12, demandeur_nom="Penda")
        await _sortie_retro(db, monde, "5", 12, demandeur_nom=" penda ", doublon_confirme=True,
                            observation="Saisie à vérifier")
    async with sessions() as db:
        preview = await _preview(db, monde)
        c = _controles(preview)["doublons"]
        assert not c["ok"] and not c["bloquant"]
        assert c["detail"].count("≈") == 1  # une paire, signalée une seule fois
        assert not preview["bloquant"]
        assert await db.scalar(select(func.count()).select_from(MgStockMouvement)
                               .where(MgStockMouvement.periode_id == monde.periodes[2],
                                      MgStockMouvement.type_mouvement == "SORTIE")) == 3  # rien fusionné


# --------------------------- 11. nouvelle clôture après régularisation, 12. historique conservé
async def test_11_nouvelle_cloture_cas_octobre(sessions, monde):
    async with sessions() as db:
        initiale = (await _periode(db, monde.periodes[2])).cloture_at
        await _rouvrir(db, monde)
    async with sessions() as db:
        await MgStockService(db).create_mouvement(_entree(monde.article, "10", _jour(2, 6)), monde.admin,
                                                  regularisation_autorisee=True)
        await _sortie_retro(db, monde, "12", 12, demandeur_nom="Penda")
        await _sortie_retro(db, monde, "12", 12, demandeur_nom="Oumana", doublon_confirme=True,
                            observation="Remise distincte")
        await _ajustement(db, monde, "-1")  # inventaire : 55 comptés pour 56 théoriques
        await _comptage(db, monde, Decimal("55"))
    async with sessions() as db:
        preview = await _preview(db, monde)
        assert not preview["bloquant"], preview["anomalies"]
        assert all(c["ok"] for c in preview["controles"]), [c for c in preview["controles"] if not c["ok"]]
        assert len(preview["regularisation"]["corrections"]) == 4
        await ep.cloturer_periode(monde.periodes[2], _requete(), db, monde.admin)
    async with sessions() as db:
        p = await _periode(db, monde.periodes[2])
        assert p.statut == CLOTUREE and p.premiere_cloture_at == initiale and p.cloture_at > initiale
        evts = await _evenements(db, p.id)
        assert [e.action for e in evts] == ["CLOTURE", "REOUVERTURE", "RECLOTURE"]
        assert evts[0].created_at < evts[2].created_at and evts[2].user_id == monde.admin.id
        assert evts[2].details["corrections"] == 4
        chaine = await _chaine(db, monde)
        assert chaine[1] == (Decimal("100"), Decimal("55"), Decimal("55"))
        assert chaine[2][0] == Decimal("55") and chaine[3][0] == Decimal("35")
        assert await _stock(db, monde.article.id) == Decimal("35")
