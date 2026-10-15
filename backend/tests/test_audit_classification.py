import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_classification import MAX_NIF, MAX_NNI, _controle_id, _rapprocher_forme  # noqa: E402


def test_identifiant_conforme_garde_les_zeros():
    assert _controle_id("0012345678", MAX_NNI) == ["CONFORME"]
    assert _controle_id("000123456", MAX_NIF) == ["CONFORME"]


def test_identifiant_vide():
    assert _controle_id(None, MAX_NNI) == ["VIDE"]
    assert _controle_id("", MAX_NIF) == ["VIDE"]
    assert _controle_id("   ", MAX_NIF) == ["VIDE (espaces seulement)"]


def test_identifiant_non_conforme_jamais_corrige():
    a = _controle_id(" 123-456 ", MAX_NIF)
    assert "ESPACES EN BORDURE" in a
    assert "SÉPARATEURS INTERNES" in a
    assert any("NON appliqué" in x for x in a)
    assert "CARACTÈRES NON NUMÉRIQUES" in _controle_id("AB12345", MAX_NIF)
    assert any(x.startswith("TROP LONG") for x in _controle_id("1234567890123456", MAX_NNI))
    assert any(x.startswith("TROP LONG") for x in _controle_id("1234567890", MAX_NIF))


def test_rapprochement_forme_distingue_exact_propose_inconnu():
    assert _rapprocher_forme("SARL")[0] == "EXACTE"
    assert _rapprocher_forme("GROUPEMENT DE DROIT PRIVE")[0] == "PROPOSÉE"
    statut, cible, _ = _rapprocher_forme("SOCIETE COMMERCIALE")
    assert statut == "NON RECONNUE" and cible is None
