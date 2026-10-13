from io import BytesIO

from openpyxl import Workbook, load_workbook

from pathlib import Path

from app.data.clientele_import_hebdo import (
    COLONNES_EXPORT, colonnes_export, construire_modele, date_ouverture_interdite,
    est_feuille_technique, est_valeur_consigne, ligne_export_hebdo, valider_ligne_hebdo,
)
from app.data.clientele_sources import libelle_sources
from app.services.clientele.lots import (
    _detecter, lire_ligne, resoudre_mapping, normaliser_niveau, normaliser_racine,
)

HEBDO = Path(r"C:\Users\sallm\bea-digital\File-uploade-par-semaine.xlsx")
EXPLICATIF = Path(r"C:\Users\sallm\bea-digital\file explicatif.xlsx")


def test_racine_zeros_restaures():
    assert normaliser_racine(1234) == "001234"
    assert normaliser_racine(1234.0) == "001234"
    assert normaliser_racine(" 059904 ") == "059904"


def test_racine_invalide():
    assert normaliser_racine(None) is None
    assert normaliser_racine("") is None
    assert normaliser_racine("12A456") is None
    assert normaliser_racine(1234567) is None
    assert normaliser_racine(12.5) is None


def test_niveau_normalise():
    assert normaliser_niveau("Élevé") == "ELEVE"
    assert normaliser_niveau("risque moyen") == "MOYEN"
    assert normaliser_niveau("FAIBLE") == "FAIBLE"
    assert normaliser_niveau("Interdit") == "INTERDIT"
    assert normaliser_niveau("") is None
    assert normaliser_niveau("???") is None


def _classeur(lignes: list[list]) -> object:
    wb = Workbook()
    ws = wb.active
    ws.title = "Feuil1"
    for r in lignes:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return load_workbook(BytesIO(buf.getvalue()), read_only=True, data_only=True)


def test_detection_entete_decalee():
    wb = _classeur([
        ["Situation des comptes PP et PM"],
        [],
        ["CLIENT", "RAISON SOCIALE", "CLASSE RISQUE LBC FT"],
        [1234, "ALPHA", "Moyen"],
    ])
    feuille, ligne, entetes = _detecter(wb)
    assert (feuille, ligne) == ("Feuil1", 3)
    assert entetes[:3] == ["CLIENT", "RAISON SOCIALE", "CLASSE RISQUE LBC FT"]


def test_colonne_sans_titre_selectionnable():
    wb = _classeur([[None, "NOM"], [1234, "ALPHA"]])
    _, _, entetes = _detecter(wb)
    assert entetes[0] == "(colonne A)"


def _lignes_clients(wb) -> list[dict]:
    feuille, ligne, entetes = _detecter(wb)
    cols = resoudre_mapping(entetes, None)
    ws = wb[feuille]
    out = []
    for numero, row in enumerate(ws.iter_rows(min_row=ligne + 1, values_only=True), start=ligne + 1):
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        idx = next((i for i, e in enumerate(entetes) if e == cols["racine"]), None)
        brut = row[idx] if idx is not None and idx < len(row) else None
        if brut is None or str(brut).strip() == "" or est_valeur_consigne(brut):
            continue
        out.append(lire_ligne(numero, row, entetes, cols))
    return out, feuille, ligne, cols


def test_detection_feuille_clients_prioritaire():
    wb = Workbook()
    wb.active.title = "REFERENTIELS"
    wb.active.append(["PROFIL"])
    clients = wb.create_sheet("CLIENTS")
    clients.append(["RACINE CLIENT", "NOM CLIENT", "Classe risque LBC FT", "DATE_CREATION_ENTREPRISE"])
    clients.append(["000123", "ALPHA", "Moyen", "01/01/2020"])
    bruit = wb.create_sheet("Feuil1")
    bruit.append(["CODE AGENCE", "RACINE CLIENT", "Classe risque LBC FT"])
    buf = BytesIO()
    wb.save(buf)
    lu = load_workbook(BytesIO(buf.getvalue()), read_only=True, data_only=True)
    feuille, ligne, entetes = _detecter(lu)
    assert (feuille, ligne) == ("CLIENTS", 1)
    assert "RACINE CLIENT" in entetes
    assert est_feuille_technique("NOTICE_IMPORT")
    lu.close()


def test_classeur_hebdo_listes_pas_des_clients():
    if not HEBDO.exists():
        return
    wb = load_workbook(HEBDO, read_only=True, data_only=True)
    lignes, feuille, ligne, cols = _lignes_clients(wb)
    wb.close()
    assert feuille == "Feuil1"
    assert ligne == 3
    assert cols["racine"] == "RACINE CLIENT"
    assert cols["niveau"] == "Classe risque LBC FT"
    assert cols["analyste"] == "Analyste KYC"
    assert date_ouverture_interdite(cols.get("date_eer") or "DATE EER")
    assert not date_ouverture_interdite(cols.get("date_ouverture"))
    assert cols.get("date_ouverture") is None
    assert lignes == []


def test_classeur_hebdo_une_vraie_racine():
    wb = Workbook()
    ws = wb.active
    ws.title = "Feuil1"
    ws.append([None] * 22)
    ws.append([None] * 22)
    ws.append([
        "CODE AGENCE", "NOM AGENCE", "RACINE CLIENT", "NOM CLIENT", "DATE EER", "PROFIL",
        "SOUS PROFIL", "Catégorie juridique", "Code Secteur BCM", "Libellé secteur BCM",
        "Famille BCM", "NIF", "NNI", "Nationnalité", "Résidence", "Statut compte",
        "Statut Gel", "Date mise à jour client", "Date classe risque LBC FT",
        "Classe risque LBC FT", "Motif de risque LBC FT", "Analyste KYC",
    ])
    ws.append(["Requete"] * 4 + ["Libre format date", "Liste interne"] + [None] * 16)
    ws.append([None, None, None, None, None, "Personne Morale", "GE"])
    ws.append([
        "001", "Nouakchott", "000123", "ALPHA SARL", "01/02/2024", "Personne Morale",
        "PME", "SARL", "101", "Cultures céréalières (riz,mil, sorgho, maïs)", "AGRICULTURE",
        "123456789", "1234567890", "Mauritanie", "Mauritanie", "Ouvert", "Actif",
        "15/09/2026", "15/09/2026", "Moyen", "Date création inf 1 an", "Fatimata Diallo",
    ])
    ws.append([
        "001", "Nouakchott", "12A456", "BETA", None, None, None, None, "999", "Inconnu", "X",
        "1234567890123", None, None, None, "Suspendu", None, None, None, "???", None, None,
    ])
    buf = BytesIO()
    wb.save(buf)
    lu = load_workbook(BytesIO(buf.getvalue()), read_only=True, data_only=True)
    lignes, feuille, ligne, cols = _lignes_clients(lu)
    lu.close()
    assert (feuille, ligne) == ("Feuil1", 3)
    assert cols["date_ouverture"] is None
    assert len(lignes) == 2
    ok, bad = lignes
    assert ok["racine_client"] == "000123"
    assert ok["classe_source"] == "MOYEN"
    assert ok["analyste_kyc"] == "Fatimata Diallo"
    assert bad["racine_client"] is None
    assert bad["brut"] == "12A456"
    assert any("NIF trop long" in a for a in bad["anomalies"])
    assert any("Classe de risque illisible" in a for a in bad["anomalies"])
    assert any("secteur bcm" in a.lower() for a in bad["anomalies"])


def test_date_creation_entreprise_pas_date_eer():
    wb = _classeur([
        ["RACINE CLIENT", "DATE EER", "DATE_CREATION_ENTREPRISE", "ENTREPRISE_OUVERTURE_RECENTE"],
        ["000123", "01/01/2020", "15/03/2024", "Oui"],
    ])
    feuille, ligne, entetes = _detecter(wb)
    cols = resoudre_mapping(entetes, None)
    row = next(wb[feuille].iter_rows(min_row=ligne + 1, values_only=True))
    lu = lire_ligne(2, row, entetes, cols)
    assert cols["date_ouverture"] == "DATE_CREATION_ENTREPRISE"
    assert cols["date_eer"] == "DATE EER"
    assert str(lu["date_ouverture_entreprise"]) == "2024-03-15"
    assert lu["entreprise_recente_brut"] == "Oui"


def test_modele_import_hebdo():
    wb = load_workbook(BytesIO(construire_modele()), data_only=True)
    assert {"LISEZ_MOI", "CLIENTS", "REFERENTIELS", "SECTEURS_BCM", "NOTICE_IMPORT",
            "RESULTATS_MOTEUR"} <= set(wb.sheetnames)
    clients = [c.value for c in wb["CLIENTS"][1]]
    assert clients[:4] == ["CODE AGENCE", "NOM AGENCE", "RACINE CLIENT", "NOM CLIENT"]
    assert "DATE_CREATION_ENTREPRISE" in clients
    assert "ENTREPRISE_OUVERTURE_RECENTE" in clients
    assert "DATE EER" in clients
    wb.close()


def test_coherence_secteur_et_identifiants():
    anomalies = valider_ligne_hebdo({
        "Code Secteur BCM": "101",
        "Libellé secteur BCM": "Commerce électronique",
        "Famille BCM": "COMMERCE",
        "NIF": "1234567890",
        "NNI": "123",
        "PROFIL": "Inconnu",
        "Statut compte": "Ouvert",
        "Statut Gel": "Actif",
    })
    assert any("Libellé secteur" in a for a in anomalies)
    assert any("Famille BCM" in a for a in anomalies)
    assert any("NIF trop long" in a for a in anomalies)
    assert any("PROFIL" in a for a in anomalies)
    assert any("COMPTE ni RIB" in a for a in anomalies)


def test_export_22_colonnes_modele():
    assert colonnes_export("LISTE", ["DATE_CREATION_ENTREPRISE", "FOO"]) == list(COLONNES_EXPORT)
    assert COLONNES_EXPORT[0:3] == ("CODE AGENCE", "NOM AGENCE", "RACINE CLIENT")
    assert "DATE_CREATION_ENTREPRISE" not in COLONNES_EXPORT
    row = ligne_export_hebdo({
        "CODE AGENCE": "001", "NOM AGENCE": "Nouakchott", "RACINE CLIENT": "000123",
        "NOM CLIENT": "ALPHA", "Classe risque LBC FT": "Moyen", "Analyste KYC": "Fatimata Diallo",
        "DATE_CREATION_ENTREPRISE": "2020-01-01", "Entreprise récente (fichier)": "Oui",
    })
    assert row[0:4] == ["001", "Nouakchott", "000123", "ALPHA"]
    assert row[COLONNES_EXPORT.index("Classe risque LBC FT")] == "Moyen"
    assert row[COLONNES_EXPORT.index("Analyste KYC")] == "Fatimata Diallo"
    assert len(row) == 22


def test_libelles_sources():
    assert libelle_sources("Matrice Faible / V4 100.") == (
        "Matrice des risques LBC/FT BEA Faible / Fiche de scoring 100.")
    assert libelle_sources("Conflit V1/V4") == "Conflit Matrice des risques LBC/FT BEA / Fiche de scoring"
    assert libelle_sources("MATRICE_V1 SCORING_V4 niveau_matrice") == "MATRICE_V1 SCORING_V4 niveau_matrice"
    assert libelle_sources("Matrice des risques LBC/FT BEA") == "Matrice des risques LBC/FT BEA"
