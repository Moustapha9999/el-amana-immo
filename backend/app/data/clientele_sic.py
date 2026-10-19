"""Déclaration SIC (BCM) : colonnes du modèle « SIC bcm.xlsx », règles configurables, lecture du référentiel.

Le fichier SIC est importé manuellement sur la plateforme de la BCM. BEA DIGITAL prépare, contrôle et trace ;
il ne dépose rien. Les colonnes et leur ordre sont ceux du modèle, sans ajout.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from app.data.clientele_bcm_regles import RegleDef

TypeSic = Literal["PP", "PM"]
TYPES_SIC: tuple[str, ...] = ("PP", "PM")

COLONNES: dict[str, tuple[str, ...]] = {
    "PP": ("CodeClient", "StatutResidentiel", "NNI", "Prenom", "Nom", "Genre",
           "CodeCategorieSocioprofessionnelle", "NumTel", "DateEntreeEnRelation", "MoughataaAgence"),
    "PM": ("CodeClient", "NIF", "RaisonSociale", "CodeSecteurActivite", "DateEntreeEnRelation", "MoughataaAgence"),
}
FEUILLES = {"PP": "pp", "PM": "pm"}
COLONNES_TEXTE = {"CodeClient", "NNI", "NIF", "NumTel", "CodeCategorieSocioprofessionnelle", "CodeSecteurActivite",
                  "MoughataaAgence", "StatutResidentiel", "Genre", "Prenom", "Nom", "RaisonSociale"}

STATUTS_SIC = ("BROUILLON", "A_CORRIGER", "CONTROLEE", "VALIDEE_EXPORT", "GENEREE", "DEPOSEE")
STATUTS_SIC_MODIFIABLES = ("BROUILLON", "A_CORRIGER", "CONTROLEE")
RESULTATS_DEPOT = ("ACCEPTE", "ACCEPTE_PARTIELLEMENT", "REJETE", "EN_ATTENTE")
GRAVITES = ("BLOQUANTE", "A_CORRIGER", "AVERTISSEMENT")

PERIMETRES = ("COMPTE_OUVERT", "TOUS", "NOUVEAUX_PERIODE")
FORMATS_DATE = ("TEXTE_JJ_MM_AAAA", "TEXTE_MM_JJ_AAAA_HEURE", "DATE_EXCEL")
SECTEURS_GENERIQUES = ("SANS", "DIVERS", "INCONNU", "AUTRES", "AUTRE")
SOURCES_COMPLEMENT = ("EER", "KYC")
DECOUPAGES_NOM = ("PRENOM_EN_FIN_DU_NOM_ORION", "PRENOM_EN_FIN_OU_EN_TETE")

REGLES_SIC: tuple[RegleDef, ...] = (
    {
        "code": "sic.perimetre",
        "libelle": "Clients inclus dans un fichier SIC",
        "valeur": "COMPTE_OUVERT",
        "statut": "A_VALIDER",
        "origine": "Arbitrage du 19/10/2026 (défaut configurable), périmètre SIC non documenté par la BCM",
        "explication": "COMPTE_OUVERT : entrés en relation à la date de référence et ayant au moins un compte ORION "
                       "ouvert (état actuel ORION, pas d'historique de fermeture). TOUS : entrés en relation à la "
                       "date, comptes fermés inclus. NOUVEAUX_PERIODE : entrés en relation entre la date de début "
                       "et la date de référence.",
    },
    {
        "code": "sic.date_entree",
        "libelle": "DateEntreeEnRelation et MoughataaAgence (plusieurs comptes)",
        "valeur": "PREMIER_COMPTE_ORION",
        "statut": "CONFIRMEE",
        "origine": "Arbitrage du 19/10/2026",
        "explication": "Date d'ouverture du premier compte ORION du client ; agence de ce premier compte (à date "
                       "égale, plus petit numéro de compte). Même règle que la déclaration mensuelle.",
    },
    {
        "code": "sic.format_date",
        "libelle": "Format de DateEntreeEnRelation",
        "valeur": "TEXTE_JJ_MM_AAAA",
        "statut": "A_VALIDER",
        "origine": "Arbitrage du 19/10/2026 ; le modèle indique mm/dd/yyyy hh:mm:ss",
        "explication": "TEXTE_JJ_MM_AAAA : texte 24/08/2026. TEXTE_MM_JJ_AAAA_HEURE : texte 08/24/2026 00:00:00. "
                       "DATE_EXCEL : date Excel affichée mm/dd/yyyy hh:mm:ss. Format accepté par SIC à confirmer.",
    },
    {
        "code": "sic.residence",
        "libelle": "StatutResidentiel",
        "valeur": {"R": "MR", "N": "ETR"},
        "statut": "A_VALIDER",
        "origine": "Modèle : MR si Mauritanie, ETR si résidence étrangère",
        "explication": "Source : statut de résidence ORION (R = résident, N = non-résident). La nationalité n'est "
                       "jamais utilisée. Statut vide ou inconnu → client bloqué.",
    },
    {
        "code": "sic.genre",
        "libelle": "Genre",
        "valeur": {"H": "H", "M": "H", "F": "F"},
        "statut": "A_VALIDER",
        "origine": "Modèle : H / F ; le module EER enregistre M / F",
        "explication": "Source : dossier EER validé (sexe), sinon donnée KYC complémentaire. Jamais déduit du prénom.",
    },
    {
        "code": "sic.sources_complement",
        "libelle": "Sources du genre, du téléphone et des codes BCM",
        "valeur": ["EER", "KYC"],
        "statut": "CONFIRMEE",
        "origine": "Arbitrage du 19/10/2026",
        "explication": "Ordre de priorité : dossier EER validé (VALIDE / CLOTURE / ARCHIVE) le plus récent, puis "
                       "données KYC complémentaires (import du fichier complément SIC ou saisie unitaire). La "
                       "catégorie socioprofessionnelle n'existe pas en code dans EER : KYC uniquement.",
    },
    {
        "code": "sic.telephone_format",
        "libelle": "Format accepté de NumTel",
        "valeur": r"^(\+222)?[0-9]{8}$",
        "statut": "A_VALIDER",
        "origine": "Proposition : numéro mauritanien à 8 chiffres, indicatif +222 facultatif",
        "explication": "Les espaces, points et tirets sont retirés avant contrôle ; aucun chiffre n'est ajouté ni "
                       "supprimé. Un numéro hors format bloque le client.",
    },
    {
        "code": "sic.nni_format",
        "libelle": "Format attendu du NNI",
        "valeur": r"^[0-9]{10}$",
        "statut": "A_VALIDER",
        "origine": "Proposition : NNI mauritanien à 10 chiffres",
        "explication": "NNI absent → client bloqué. NNI hors format → exporté tel quel, anomalie « à corriger ».",
    },
    {
        "code": "sic.nif_obligatoire",
        "libelle": "NIF obligatoire pour les personnes morales",
        "valeur": True,
        "statut": "A_VALIDER",
        "origine": "Modèle PM",
        "explication": "NIF absent → client bloqué. Le NNI n'est jamais utilisé à la place du NIF.",
    },
    {
        "code": "sic.nom_prenom",
        "libelle": "Découpage Nom / Prénom des PP",
        "valeur": "PRENOM_EN_FIN_DU_NOM_ORION",
        "statut": "CONFIRMEE",
        "origine": "Arbitrage du 19/10/2026",
        "explication": "Prénom = champ prénoms ORION sans le préfixe « [IDP] n° » / « [IDM] n° ». Nom = nom complet "
                       "ORION privé du prénom final. Si le nom complet ne se termine pas par le prénom (nom tronqué, "
                       "prénom identique au nom complet) → client bloqué « à corriger », jamais deviné. Option "
                       "PRENOM_EN_FIN_OU_EN_TETE : accepte aussi un prénom placé en tête du nom complet (observé "
                       "dans ORION, à valider).",
    },
    {
        "code": "sic.profil",
        "libelle": "Distinction PP / PM",
        "valeur": "PROFIL_DERIVE_ET_FORME",
        "statut": "A_VALIDER",
        "origine": "Proposition",
        "explication": "Profil PP / PM de la vue Situation (agent économique, puis catégorie juridique). Si la "
                       "catégorie juridique est rattachée à l'autre forme dans la correspondance des formes de la "
                       "déclaration mensuelle → client bloqué (confusion PP / PM). Profil non identifié → bloqué.",
    },
    {
        "code": "sic.secteur_sources",
        "libelle": "Source de CodeSecteurActivite (PM)",
        "valeur": ["KYC", "CORRESPONDANCE_ORION"],
        "statut": "CONFIRMEE",
        "origine": "Arbitrage du 19/10/2026",
        "explication": "Code BCM du KYC, sinon table de correspondance libellé secteur ORION → code BCM. SANS, "
                       "DIVERS, INCONNU ne sont jamais rattachés. Un code issu d'une correspondance « à valider » est "
                       "exporté avec une anomalie « à corriger ».",
    },
)
PAR_CODE_SIC = {r["code"]: r for r in REGLES_SIC}


def norm(v: Any) -> str:
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def valider_valeur_sic(code: str, valeur: Any) -> Any:
    if code not in PAR_CODE_SIC:
        raise ValueError(f"Règle inconnue : {code}")
    if code == "sic.perimetre":
        if valeur not in PERIMETRES:
            raise ValueError(f"Valeur attendue : {', '.join(PERIMETRES)}")
        return valeur
    if code == "sic.format_date":
        if valeur not in FORMATS_DATE:
            raise ValueError(f"Valeur attendue : {', '.join(FORMATS_DATE)}")
        return valeur
    if code in ("sic.telephone_format", "sic.nni_format"):
        if not isinstance(valeur, str) or not valeur.strip():
            raise ValueError("Expression régulière attendue")
        try:
            re.compile(valeur)
        except re.error as e:
            raise ValueError(f"Expression régulière invalide : {e}") from e
        return valeur.strip()
    if code == "sic.nif_obligatoire":
        if not isinstance(valeur, bool):
            raise ValueError("Valeur attendue : vrai ou faux")
        return valeur
    if code in ("sic.residence", "sic.genre"):
        permis = {"sic.residence": {"MR", "ETR"}, "sic.genre": {"H", "F"}}[code]
        if not isinstance(valeur, dict) or not valeur:
            raise ValueError("Correspondance attendue (valeur source → valeur SIC)")
        propre = {norm(k): str(v).strip().upper() for k, v in valeur.items() if norm(k)}
        if not set(propre.values()) <= permis:
            raise ValueError(f"Valeurs SIC autorisées : {', '.join(sorted(permis))}")
        return propre
    if code == "sic.nom_prenom":
        if valeur not in DECOUPAGES_NOM:
            raise ValueError(f"Valeur attendue : {', '.join(DECOUPAGES_NOM)}")
        return valeur
    if code == "sic.sources_complement":
        if not isinstance(valeur, list) or not valeur or not set(valeur) <= set(SOURCES_COMPLEMENT):
            raise ValueError("Sources attendues parmi : EER, KYC (ordre de priorité)")
        return list(dict.fromkeys(valeur))
    if valeur != PAR_CODE_SIC[code]["valeur"]:
        raise ValueError("Seule la valeur documentée est disponible pour cette règle")
    return valeur


OPTIONS_SIC: dict[str, tuple[str, ...]] = {"sic.perimetre": PERIMETRES, "sic.format_date": FORMATS_DATE,
                                           "sic.nom_prenom": DECOUPAGES_NOM}


# --------------------------------------------------------------------------- référentiel BCM (feuille ref)
ENTETES_REF = ("CODE", "SECTEUR D'ACTIVITE", "CATEGORIE")


def usage_code(code: str, categorie: str | None) -> str:
    """PP pour les catégories socioprofessionnelles (catégorie « Personne physique » / « Autre PP »), PM sinon."""
    cat = norm(categorie)
    if "PERSONN" in cat and "PHYSIQUE" in cat or cat in ("AUTRE PP", "AUTRES PP"):
        return "PP"
    return "PM"


def lire_referentiel(lignes: list[tuple]) -> tuple[list[dict], list[dict]]:
    """Lignes de la feuille ``ref`` (en-tête inclus) → (codes, anomalies de structure). N'invente aucun code."""
    if not lignes:
        return [], [{"ligne": 1, "code": None, "motif": "Feuille vide"}]
    entete = [norm(x) for x in lignes[0]]
    try:
        i_code = entete.index("CODE")
        i_lib = next(i for i, h in enumerate(entete) if h.startswith("SECTEUR") or h.startswith("LIBELLE"))
        i_cat = entete.index("CATEGORIE")
    except (ValueError, StopIteration):
        return [], [{"ligne": 1, "code": None, "motif": "En-têtes attendus : Code, Secteur d'activité, Catégorie"}]
    codes: list[dict] = []
    anomalies: list[dict] = []
    vus: dict[str, int] = {}
    for n, row in enumerate(lignes[1:], start=2):
        brut = row[i_code] if i_code < len(row) else None
        lib = row[i_lib] if i_lib < len(row) else None
        cat = row[i_cat] if i_cat < len(row) else None
        if brut is None and not lib and not cat:
            continue
        code = str(int(brut)) if isinstance(brut, float) and brut.is_integer() else str(brut or "").strip()
        libelle = " ".join(str(lib or "").split())
        categorie = " ".join(str(cat or "").split())
        if not re.fullmatch(r"\d{1,6}", code):
            anomalies.append({"ligne": n, "code": code or None, "motif": "Code non numérique ou absent"})
            continue
        if not libelle:
            anomalies.append({"ligne": n, "code": code, "motif": "Libellé absent"})
        if not categorie:
            anomalies.append({"ligne": n, "code": code, "motif": "Catégorie absente"})
        if code in vus:
            anomalies.append({"ligne": n, "code": code, "motif": f"Code dupliqué (déjà ligne {vus[code]})"})
        else:
            vus[code] = n
        usage = usage_code(code, categorie)
        if usage == "PP" and not code.startswith("11"):
            anomalies.append({"ligne": n, "code": code, "motif": "Catégorie PP sur un code hors plage 11xx (à vérifier)"})
        if usage == "PM" and code.startswith("11") and len(code) == 4:
            anomalies.append({"ligne": n, "code": code, "motif": "Code 11xx rattaché à une catégorie non PP (à vérifier)"})
        codes.append({"ligne": n, "code": code, "libelle": libelle, "categorie": categorie, "usage": usage})
    return codes, anomalies


# --------------------------------------------------------------------------- noms
_PREFIXE_PRENOM = re.compile(r"^\s*\[ID[A-Z]\]\s*\d*\s*")


def decouper_nom(nom_complet: str | None, prenoms: str | None,
                 en_tete: bool = False) -> tuple[str | None, str | None, str | None]:
    """(nom, prénom, motif d'échec). Le prénom est le champ ORION nettoyé ; le nom est le nom complet sans ce
    prénom final (ou initial si ``en_tete``). Aucun découpage approximatif."""
    complet = " ".join(str(nom_complet or "").split())
    prenom = " ".join(_PREFIXE_PRENOM.sub("", str(prenoms or "")).split())
    if not prenom:
        return None, None, "Prénom absent dans ORION"
    if not complet:
        return None, prenom, "Nom complet absent dans ORION"
    if norm(complet) == norm(prenom):
        return None, prenom, "Le champ prénoms ORION reprend le nom complet : nom de famille non isolable"
    n = len(prenom.split())
    if norm(complet).endswith(" " + norm(prenom)):
        nom = " ".join(complet.split()[:-n])
    elif en_tete and norm(complet).startswith(norm(prenom) + " "):
        nom = " ".join(complet.split()[n:])
    else:
        return None, prenom, ("Le nom complet ORION ne se termine pas par le prénom (nom tronqué à "
                              f"{len(complet)} caractères ou ordre différent)")
    return (nom or None), prenom, (None if nom else "Nom de famille vide après découpage")


def normaliser_telephone(v: str | None) -> str:
    return re.sub(r"[\s.\-()/]", "", str(v or ""))
