"""Indicateurs enrichis du tableau de bord réclamations — calculs purs, sans base."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.reclamations.reporting import _anciennete, _performance, _recurrents, _tendance

NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)


def _r(jours: int, statut: str = "EN_COURS", cloture_j: int | None = None, echeance_j: int | None = None,
       racine: str | None = None) -> SimpleNamespace:
    recu = NOW - timedelta(days=jours)
    return SimpleNamespace(
        statut=statut, date_premiere_reception=recu, client_racine=racine, client_nom=f"Client {racine}",
        date_cloture=recu + timedelta(days=cloture_j) if cloture_j is not None else None,
        echeance=recu + timedelta(days=echeance_j) if echeance_j is not None else None,
        etat_delai=None, date_fin_delai=None, date_alerte=None,
    )


def test_performance_delai_moyen_et_respect_echeance():
    rows = [_r(40, "CLOTUREE", cloture_j=4, echeance_j=10), _r(40, "CLOTUREE", cloture_j=12, echeance_j=10),
            _r(20, "CLOTUREE", cloture_j=2), _r(5)]
    p = _performance(rows)
    assert p == {"cloturees": 3, "delai_moyen_jours": 6.0, "dans_delai": 1, "hors_delai": 1, "taux_dans_delai": 50.0}
    assert _performance([_r(3)])["delai_moyen_jours"] is None


def test_anciennete_par_tranche():
    t = {x["code"]: x["n"] for x in _anciennete([_r(0), _r(7), _r(8), _r(30), _r(31), _r(400)], NOW)}
    assert t == {"0-7": 2, "8-15": 1, "16-30": 1, "30+": 2}


def test_tendance_douze_mois_glissants():
    rows = [_r(0, "CLOTUREE", cloture_j=0), _r(0), _r(45), _r(400)]
    t = _tendance(rows, NOW)
    assert len(t) == 12 and t[-1]["mois"] == "2026-10" and t[0]["mois"] == "2025-11"
    assert t[-1] == {"mois": "2026-10", "libelle": "oct. 26", "recues": 2, "cloturees": 1}
    assert sum(m["recues"] for m in t) == 3


def test_clients_recurrents():
    rows = [_r(1, racine="000001"), _r(2, "CLOTUREE", racine="000001"), _r(3, racine="000002"), _r(4)]
    assert _recurrents(rows) == [{"racine": "000001", "nom": "Client 000001", "n": 2, "ouvertes": 1}]
