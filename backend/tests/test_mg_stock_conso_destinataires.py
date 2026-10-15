"""Rapport « Consommation par destinataire » — agrégation par axe."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.services.mg_stock_reporting import (
    REPORTS,
    _colonnes,
    _norm_filters,
    agreger_consommation,
)

DG, DIR, DEP, SRV = (uuid.uuid4() for _ in range(4))
AG = uuid.uuid4()
USER = uuid.uuid4()
ART1, ART2 = uuid.uuid4(), uuid.uuid4()

ENTITES = {
    DG: {"libelle": "Direction Générale", "sigle": "DG", "type": "DIRECTION_GENERALE", "parent_id": None},
    DIR: {"libelle": "Direction Financière", "sigle": None, "type": "DIRECTION", "parent_id": DG},
    DEP: {"libelle": "Comptabilité", "sigle": None, "type": "DEPARTEMENT", "parent_id": DIR},
    SRV: {"libelle": "Service Paie", "sigle": None, "type": "SERVICE", "parent_id": DEP},
}
AGENCES = {AG: {"code": "AG01", "libelle": "Agence Tevragh Zeina"}}
USERS = {USER: "Aïcha Mint Ahmed"}


def _ligne(**kw):
    base = {
        "destination_type": None,
        "org_entite_id": None,
        "service_id": None,
        "agence_id": None,
        "demandeur_id": None,
        "demandeur_nom": None,
        "article_id": ART1,
        "article_code": "A1",
        "article": "Rame papier A4",
        "quantite": Decimal("1"),
        "nb": 1,
        "derniere": datetime(2026, 10, 1, 10, tzinfo=timezone.utc),
    }
    base.update(kw)
    return base


LIGNES = [
    _ligne(destination_type="DEPARTEMENT", org_entite_id=DEP, service_id=SRV, demandeur_id=USER,
           quantite=Decimal("6"), nb=2),
    _ligne(destination_type="DEPARTEMENT", org_entite_id=DEP, demandeur_nom="  moussa   diallo ",
           article_id=ART2, article_code="A2", article="Stylo", quantite=Decimal("4")),
    _ligne(destination_type="AGENCE", agence_id=AG, demandeur_nom="Moussa Diallo", quantite=Decimal("10"),
           derniere=datetime(2026, 10, 5, 9, tzinfo=timezone.utc)),
    # Sortie antérieure au formulaire : entité = service, pas de demandeur.
    _ligne(org_entite_id=SRV, quantite=Decimal("5")),
]


def _agg(axe, detail=False, q=None):
    return agreger_consommation(
        LIGNES, axe=axe, detail=detail, entites=ENTITES, agences=AGENCES, users=USERS, q=q
    )


def test_axe_departement_remonte_le_service_et_exclut_les_agences():
    rows, totals = _agg("departement")
    assert len(rows) == 1
    r = rows[0]
    assert r["destinataire"] == "Comptabilité"
    assert r["rattachement"] == "Direction Financière"
    assert r["quantite"] == 15.0
    assert r["nb_sorties"] == 4
    assert r["nb_articles"] == 2
    assert r["part"] == "100,0 %"
    assert totals["quantite"] == 15.0


def test_axe_service_inclut_les_sorties_historiques_rattachees_au_service():
    rows, _ = _agg("service")
    assert [(r["destinataire"], r["quantite"]) for r in rows] == [("Service Paie", 11.0)]
    assert rows[0]["rattachement"] == "Comptabilité"


def test_axe_agence_ne_compte_que_les_sorties_vers_agence():
    rows, _ = _agg("agence")
    assert [(r["destinataire"], r["rattachement"], r["quantite"]) for r in rows] == [
        ("Agence Tevragh Zeina", "AG01", 10.0)
    ]
    assert rows[0]["derniere_sortie"] == "05/10/2026"


def test_axe_demandeur_regroupe_les_noms_libres_et_isole_les_non_renseignes():
    rows, totals = _agg("demandeur")
    par_nom = {r["destinataire"]: r for r in rows}
    assert par_nom["moussa diallo"]["quantite"] == 14.0
    assert par_nom["Aïcha Mint Ahmed"]["quantite"] == 6.0
    assert par_nom["Non renseigné"]["quantite"] == 5.0
    assert "Agence Tevragh Zeina" in par_nom["moussa diallo"]["rattachement"]
    assert rows[0]["destinataire"] == "moussa diallo"
    assert totals["quantite"] == 25.0


def test_detail_par_article_et_recherche():
    rows, _ = _agg("departement", detail=True)
    assert [(r["article_code"], r["quantite"]) for r in rows] == [("A1", 11.0), ("A2", 4.0)]
    rows, _ = _agg("demandeur", q="stylo")
    assert rows == []
    rows, _ = _agg("demandeur", detail=True, q="stylo")
    assert [r["article"] for r in rows] == ["Stylo"]


def test_libelles_historiques_non_rattaches_restent_visibles_par_departement():
    lignes = LIGNES + [
        _ligne(departement=" COMPTABILITE ", quantite=Decimal("3")),
        _ligne(departement="comptabilite", quantite=Decimal("2")),
    ]
    rows, totals = agreger_consommation(
        lignes, axe="departement", detail=False, entites=ENTITES, agences=AGENCES, users=USERS
    )
    hist = [r for r in rows if r["rattachement"].startswith("Libellé historique")]
    assert [(r["destinataire"], r["quantite"]) for r in hist] == [("COMPTABILITE", 5.0)]
    assert totals["quantite"] == 20.0
    rows, _ = agreger_consommation(
        lignes, axe="service", detail=False, entites=ENTITES, agences=AGENCES, users=USERS
    )
    assert all(not r["rattachement"].startswith("Libellé historique") for r in rows)


def test_colonnes_et_filtres():
    spec = REPORTS["consommation_destinataires"]
    f = _norm_filters({"axe": "inconnu", "date_debut": "2026-10-01", "date_fin": "pas-une-date"})
    assert f["axe"] == "departement"
    assert f["date_debut"].isoformat() == "2026-10-01"
    assert f["date_fin"] is None
    keys = [c.key for c in _colonnes(spec, f, None)]
    assert "article" not in keys and "nb_articles" in keys
    keys = [c.key for c in _colonnes(spec, {**f, "detail": "1"}, None)]
    assert "article" in keys and "nb_articles" not in keys
