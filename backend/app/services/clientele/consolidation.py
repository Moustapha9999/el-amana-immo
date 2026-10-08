"""Lecture et consolidation de l'État Compte ORION, sans base de données.

Une ligne ORION = un compte. Plusieurs lignes portent le même CLIENT (racine, 6 chiffres) :
elles produisent **un** client et autant de comptes. Les identifiants restent des chaînes ;
une valeur numérique (zéros initiaux perdus par Excel) est refusée, jamais complétée.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

RE_RACINE = re.compile(r"^[0-9]{6}$")
RE_COMPTE = re.compile(r"^[0-9]{11}$")
RE_RIB = re.compile(r"^[0-9]{23}$")
RE_AGENCE = re.compile(r"^[0-9]{5}$")
RE_DATE_FR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
# IDENTIFIANT_LISTE regroupe parfois plusieurs pièces (« NNI/passeport », titulaires multiples).
RE_SEPARATEURS = re.compile(r"[,;/]")
EXCEL_EPOCH = date(1899, 12, 30)

# En-têtes de l'État Compte ORION (normalisés : majuscules, sans accents ni espaces superflus).
COLONNES_OBLIGATOIRES = ("RIB", "COMPTE", "CODE_AGENCE_COMPTE", "CLIENT", "RAISON_SOCIAL", "ETAT_COMPTE", "DEVISE")
COLONNE_RESIDENT = "R/N"
# Champ canonique → synonymes d'en-têtes (déjà normalisés).
SYNONYMES_COLONNES: dict[str, tuple[str, ...]] = {
    "RIB": ("RIB", "IBAN"),
    "COMPTE": ("COMPTE", "NUMERO COMPTE", "N COMPTE", "NO COMPTE"),
    "CODE_AGENCE_COMPTE": ("CODE_AGENCE_COMPTE", "CODE AGENCE COMPTE", "CODE AG", "CODE AGENCE"),
    "AGENCE_COMPTE": ("AGENCE_COMPTE", "AGENCE COMPTE", "AGENCE"),
    "CLIENT": ("CLIENT", "RACINE", "RACINE CLIENT", "CODE CLIENT"),
    "NCG": ("NCG",),
    "RUBRIQUE_COMPTABLE": ("RUBRIQUE_COMPTABLE", "RUBRIQUE COMPTABLE"),
    "RAISON_SOCIAL": ("RAISON_SOCIAL", "RAISON SOCIALE", "NOM CLIENT", "NOM"),
    "DATE_NAISSANCE": ("DATE_NAISSANCE", "DATE NAISSANCE"),
    "NATIONALITE": ("NATIONALITE", "NATIONNALITE"),
    "LISTE_IDP_PRENOMS": ("LISTE_IDP_PRENOMS", "PRENOMS", "PRENOM"),
    "ETAT_COMPTE": ("ETAT_COMPTE", "ETAT COMPTE", "ETAT"),
    "AGENT_ECONOMIQUE": ("AGENT_ECONOMIQUE", "AGENT ECONOMIQUE"),
    "SITUATION_JURIDIQUE": ("SITUATION_JURIDIQUE", "SITUATION JURIDIQUE"),
    "CATEGORIE_JURIDIQUE": ("CATEGORIE_JURIDIQUE", "CATEGORIE JURIDIQUE"),
    "R/N": ("R/N", "R/N - STATUT RESIDENT", "STATUT RESIDENT", "RESIDENT"),
    "SECTEUR_ACTIVITE": ("SECTEUR_ACTIVITE", "SECTEUR ACTIVITE", "SECTEUR D ACTIVITE"),
    "FAMILLE_SECTEUR_ACTIVITE": ("FAMILLE_SECTEUR_ACTIVITE", "FAMILLE SECTEUR ACTIVITE"),
    "LISTE_INTERDICTION": ("LISTE_INTERDICTION", "INTERDICTION"),
    "IDENTIFIANT_LISTE": ("IDENTIFIANT_LISTE", "IDENTIFIANT"),
    "TYPE_IDENTIFIANT": ("TYPE_IDENTIFIANT", "TYPE IDENTIFIANT"),
    "RCS_LISTE": ("RCS_LISTE", "RCS"),
    "CONFORMITE_COMPTE": ("CONFORMITE_COMPTE", "CONFORMITE COMPTE", "CONFORMITE"),
    "DATOUV": ("DATOUV", "DATE OUV", "DATE OUVERTURE"),
    "DDC": ("DDC",),
    "DDD": ("DDD",),
    "DEVISE": ("DEVISE",),
}
LIBELLES_COLONNES = {
    "RIB": "RIB", "COMPTE": "Compte", "CODE_AGENCE_COMPTE": "Code agence", "CLIENT": "Client (racine)",
    "RAISON_SOCIAL": "Raison sociale", "ETAT_COMPTE": "État du compte", "DEVISE": "Devise",
    "AGENCE_COMPTE": "Agence", "NCG": "NCG", "RUBRIQUE_COMPTABLE": "Rubrique comptable",
    "DATE_NAISSANCE": "Date de naissance", "NATIONALITE": "Nationalité",
    "LISTE_IDP_PRENOMS": "Prénoms", "AGENT_ECONOMIQUE": "Agent économique",
    "SITUATION_JURIDIQUE": "Situation juridique", "CATEGORIE_JURIDIQUE": "Catégorie juridique",
    "R/N": "Statut résident", "SECTEUR_ACTIVITE": "Secteur d'activité",
    "FAMILLE_SECTEUR_ACTIVITE": "Famille secteur", "LISTE_INTERDICTION": "Liste d'interdiction",
    "IDENTIFIANT_LISTE": "Identifiant", "TYPE_IDENTIFIANT": "Type d'identifiant", "RCS_LISTE": "RCS",
    "CONFORMITE_COMPTE": "Conformité", "DATOUV": "Date d'ouverture", "DDC": "DDC", "DDD": "DDD",
}


class LigneInvalide(ValueError):
    def __init__(self, numero: int, motifs: list[str]):
        super().__init__(f"Ligne {numero} : " + " ; ".join(motifs))
        self.numero = numero
        self.motifs = motifs


@dataclass(frozen=True)
class ClientOrion:
    racine_client: str
    raison_sociale: str
    prenoms: str | None = None
    date_naissance: date | None = None
    date_naissance_orion: str | None = None
    nationalite: str | None = None
    statut_resident: str | None = None
    agent_economique: str | None = None
    situation_juridique: str | None = None
    categorie_juridique: str | None = None
    secteur_activite: str | None = None
    famille_secteur_activite: str | None = None
    type_identifiant: str | None = None
    identifiant_orion: str | None = None
    nni: str | None = None
    nif: str | None = None
    rcs: str | None = None


@dataclass(frozen=True)
class CompteOrion:
    compte: str
    rib: str
    racine_client: str
    code_agence: str
    etat_compte: str
    devise: str
    ncg: str | None = None
    rubrique_comptable: str | None = None
    date_ouverture: date | None = None
    ddc: date | None = None
    ddd: date | None = None
    conformite_compte: str | None = None
    liste_interdiction: str | None = None


@dataclass(frozen=True)
class LigneOrion:
    numero: int
    client: ClientOrion
    compte: CompteOrion


@dataclass(frozen=True)
class Anomalie:
    numero: int
    racine_client: str | None
    code: str
    message: str
    bloquante: bool


@dataclass
class Consolidation:
    clients: dict[str, ClientOrion] = field(default_factory=dict)
    comptes: dict[str, CompteOrion] = field(default_factory=dict)
    anomalies: list[Anomalie] = field(default_factory=list)
    nb_lignes: int = 0

    @property
    def nb_clients(self) -> int:
        return len(self.clients)

    @property
    def nb_comptes(self) -> int:
        return len(self.comptes)

    @property
    def nb_rib(self) -> int:
        return len({c.rib for c in self.comptes.values()})

    @property
    def bloquante(self) -> bool:
        return any(a.bloquante for a in self.anomalies)


def cle_rib(banque: str, guichet: str, compte: str) -> int:
    return 97 - ((89 * int(banque) + 15 * int(guichet) + 3 * int(compte)) % 97)


def cartographier(entetes: list[str]) -> tuple[dict[str, str], list[str]]:
    """Associe chaque champ canonique à un en-tête du fichier ; le reste est « supplémentaire »."""
    index: dict[str, str] = {}
    for brut in entetes:
        cle = normaliser_entete(brut)
        if not cle:
            continue
        for champ, synonymes in SYNONYMES_COLONNES.items():
            if champ in index:
                continue
            if cle == champ or cle in synonymes or (champ == COLONNE_RESIDENT and cle.startswith(COLONNE_RESIDENT)):
                index[champ] = brut
                break
    ignores = [e for e in entetes if e and e not in index.values()]
    return index, ignores


def appliquer_mapping(valeurs: Mapping[object, object], mapping: Mapping[str, str]) -> dict[str, object]:
    """Reconstruit une ligne aux clés canoniques à partir du mapping champ → en-tête d'origine."""
    origine = {str(k): v for k, v in valeurs.items()}
    return {champ: origine.get(entete) for champ, entete in mapping.items()}


def normaliser_entete(nom: object) -> str:
    texte = unicodedata.normalize("NFKD", str(nom or "")).encode("ascii", "ignore").decode()
    return " ".join(texte.upper().split())


def _texte(valeur: object) -> str | None:
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte or None


def _sans_accents(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().upper()


def _identifiant(valeurs: Mapping[str, object], colonne: str, motif: re.Pattern[str], libelle: str,
                 erreurs: list[str]) -> str:
    brut = valeurs.get(colonne)
    if isinstance(brut, (int, float)) and not isinstance(brut, bool):
        erreurs.append(f"{libelle} lu comme un nombre ({brut}) : zéros initiaux perdus, colonne à exporter en texte")
        return ""
    texte = _texte(brut) or ""
    if not motif.match(texte):
        erreurs.append(f"{libelle} invalide ({texte!r})")
    return texte


def _date(valeur: object) -> date | None:
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        return EXCEL_EPOCH + timedelta(days=int(valeur))
    m = RE_DATE_FR.match(str(valeur).strip())
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _etat(valeur: object, erreurs: list[str]) -> str:
    texte = _sans_accents(_texte(valeur) or "")
    if texte == "OUVERT":
        return "OUVERT"
    if texte == "FERME":
        return "FERME"
    erreurs.append(f"ETAT_COMPTE inconnu ({valeur!r})")
    return ""


def _conformite(valeur: object, erreurs: list[str]) -> str | None:
    texte = _sans_accents(_texte(valeur) or "")
    if not texte:
        return None
    if texte == "COMPTES CONFORMES":
        return "CONFORME"
    if texte == "COMPTES NON CONFORMES":
        return "NON_CONFORME"
    erreurs.append(f"CONFORMITE_COMPTE inconnue ({valeur!r})")
    return None


def lire_ligne(brute: Mapping[object, object], numero: int) -> LigneOrion:
    """Convertit une ligne ORION (en-tête → valeur) ; lève ``LigneInvalide`` avec tous les motifs."""
    valeurs = {normaliser_entete(k): v for k, v in brute.items()}
    resident_cle = next((k for k in valeurs if k.startswith(COLONNE_RESIDENT)), None)
    erreurs: list[str] = []
    manquantes = [c for c in COLONNES_OBLIGATOIRES if c not in valeurs]
    if manquantes:
        raise LigneInvalide(numero, [f"colonne absente : {c}" for c in manquantes])

    racine = _identifiant(valeurs, "CLIENT", RE_RACINE, "CLIENT (racine, 6 chiffres)", erreurs)
    compte = _identifiant(valeurs, "COMPTE", RE_COMPTE, "COMPTE (11 chiffres)", erreurs)
    rib = _identifiant(valeurs, "RIB", RE_RIB, "RIB (23 chiffres)", erreurs)
    agence = _identifiant(valeurs, "CODE_AGENCE_COMPTE", RE_AGENCE, "CODE_AGENCE_COMPTE (5 chiffres)", erreurs)
    if RE_RIB.match(rib) and RE_COMPTE.match(compte) and rib[10:21] != compte:
        erreurs.append("le RIB ne contient pas le COMPTE (positions 11 à 21)")
    if RE_RIB.match(rib) and RE_AGENCE.match(agence) and rib[5:10] != agence:
        erreurs.append("le code guichet du RIB diffère de CODE_AGENCE_COMPTE")
    raison_sociale = _texte(valeurs.get("RAISON_SOCIAL"))
    if not raison_sociale:
        erreurs.append("RAISON_SOCIAL vide")
    etat = _etat(valeurs.get("ETAT_COMPTE"), erreurs)
    devise = (_texte(valeurs.get("DEVISE")) or "").upper()
    if not re.match(r"^[A-Z]{3}$", devise):
        erreurs.append(f"DEVISE invalide ({devise!r})")
    conformite = _conformite(valeurs.get("CONFORMITE_COMPTE"), erreurs)
    resident = (_texte(valeurs.get(resident_cle)) or "").upper() if resident_cle else ""
    if resident and resident not in ("R", "N"):
        erreurs.append(f"statut résident inconnu ({resident!r})")
    type_identifiant = (_texte(valeurs.get("TYPE_IDENTIFIANT")) or "").upper() or None
    if type_identifiant and type_identifiant not in ("NNI", "NIF"):
        erreurs.append(f"TYPE_IDENTIFIANT inconnu ({type_identifiant!r})")
    if erreurs:
        raise LigneInvalide(numero, erreurs)

    identifiant = _texte(valeurs.get("IDENTIFIANT_LISTE"))
    unique = identifiant if identifiant and not RE_SEPARATEURS.search(identifiant) else None
    naissance_brute = _texte(valeurs.get("DATE_NAISSANCE"))
    client = ClientOrion(
        racine_client=racine,
        raison_sociale=raison_sociale or "",
        prenoms=_texte(valeurs.get("LISTE_IDP_PRENOMS")),
        date_naissance=_date(naissance_brute) if naissance_brute and "," not in naissance_brute else None,
        date_naissance_orion=naissance_brute,
        nationalite=_texte(valeurs.get("NATIONALITE")),
        statut_resident=resident or None,
        agent_economique=_texte(valeurs.get("AGENT_ECONOMIQUE")),
        situation_juridique=_texte(valeurs.get("SITUATION_JURIDIQUE")),
        categorie_juridique=_texte(valeurs.get("CATEGORIE_JURIDIQUE")),
        secteur_activite=_texte(valeurs.get("SECTEUR_ACTIVITE")),
        famille_secteur_activite=_texte(valeurs.get("FAMILLE_SECTEUR_ACTIVITE")),
        type_identifiant=type_identifiant,
        identifiant_orion=identifiant,
        nni=unique if type_identifiant == "NNI" else None,
        nif=unique if type_identifiant == "NIF" else None,
        rcs=_texte(valeurs.get("RCS_LISTE")),
    )
    return LigneOrion(numero=numero, client=client, compte=CompteOrion(
        compte=compte,
        rib=rib,
        racine_client=racine,
        code_agence=agence,
        etat_compte=etat,
        devise=devise,
        ncg=_texte(valeurs.get("NCG")),
        rubrique_comptable=_texte(valeurs.get("RUBRIQUE_COMPTABLE")),
        date_ouverture=_date(valeurs.get("DATOUV")),
        ddc=_date(valeurs.get("DDC")),
        ddd=_date(valeurs.get("DDD")),
        conformite_compte=conformite,
        liste_interdiction=_texte(valeurs.get("LISTE_INTERDICTION")),
    ))


def consolider(lignes: Iterable[LigneOrion]) -> Consolidation:
    """Regroupe les comptes par racine : un client par racine, quel que soit le nombre de lignes."""
    resultat = Consolidation()
    rib_vus: dict[str, str] = {}
    for ligne in lignes:
        resultat.nb_lignes += 1
        client, compte = ligne.client, ligne.compte
        racine = client.racine_client

        connu = resultat.clients.get(racine)
        if connu is None:
            resultat.clients[racine] = client
        elif connu != client:
            ecarts = [nom for nom in ClientOrion.__dataclass_fields__ if getattr(connu, nom) != getattr(client, nom)]
            resultat.anomalies.append(Anomalie(
                ligne.numero, racine, "CLIENT_INCOHERENT",
                "données client différentes d'un compte à l'autre : " + ", ".join(ecarts), True))

        if compte.compte in resultat.comptes:
            resultat.anomalies.append(Anomalie(
                ligne.numero, racine, "COMPTE_DUPLIQUE", f"compte {compte.compte} présent plusieurs fois", True))
            continue
        if compte.rib in rib_vus:
            resultat.anomalies.append(Anomalie(
                ligne.numero, racine, "RIB_DUPLIQUE", f"RIB déjà porté par le compte {rib_vus[compte.rib]}", True))
            continue
        resultat.comptes[compte.compte] = compte
        rib_vus[compte.rib] = compte.compte

        if racine not in (compte.compte[0:6], compte.compte[1:7]):
            resultat.anomalies.append(Anomalie(
                ligne.numero, racine, "RACINE_HORS_COMPTE",
                f"le compte {compte.compte} ne contient pas la racine {racine}", False))
        attendue = cle_rib(compte.rib[0:5], compte.rib[5:10], compte.rib[10:21])
        if int(compte.rib[21:23]) != attendue:
            resultat.anomalies.append(Anomalie(
                ligne.numero, racine, "CLE_RIB_INVALIDE",
                f"clé RIB {compte.rib[21:23]} (attendue {attendue:02d})", False))
    return resultat
