"""Catalogue d'indicateurs : pas de chiffre inventé pour un champ À CONFIGURER."""

from app.data.clientele_indicateurs import (
    BCM_PERIODICITE_OFFICIELLE,
    MOTEUR_VERSION,
    a_configurer,
    indicateurs,
    par_code,
)


def test_version_et_periodicite_bcm():
    assert MOTEUR_VERSION.startswith("2026.")
    assert BCM_PERIODICITE_OFFICIELLE == "mois"


def test_codes_uniques_et_cle_racine():
    codes = [i["code"] for i in indicateurs()]
    assert len(codes) == len(set(codes))
    racine = [i for i in indicateurs() if i["cle"] == "RACINE"]
    assert racine
    assert par_code("cli.stock")["formule"].startswith("COUNT(DISTINCT")


def test_champs_sans_definition_sans_formule_numerique():
    for i in a_configurer():
        assert i["statut"] == "A_CONFIGURER"
        assert i["code"] in {
            "cli.construction_juridique", "cli.actifs", "cli.inactifs", "bcm.map.interdit",
            "eer.maj_5ans", "bcm.t2.enregistrees", "bcm.t2.umef_mois", "bcm.t3.suspectes_personnel",
            "bcm.t3.analysees", "bcm.t3.suivi", "bcm.t3.enregistrees", "bcm.t3.umef",
        }


def test_bcm_t2_l4_et_t3_bloques():
    assert par_code("bcm.t2.enregistrees")["statut"] == "A_CONFIGURER"
    assert par_code("bcm.t3.suspectes_personnel")["statut"] == "A_CONFIGURER"
    assert par_code("cli.actifs")["source"] == "ABSENT"
