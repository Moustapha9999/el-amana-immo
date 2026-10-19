"""Règles de calcul de la Déclaration mensuelle BCM.

Chaque règle a une valeur par défaut et un statut :
- ``CONFIRMEE`` : définition métier communiquée ou arbitrage explicite (date et origine dans ``origine``) ;
- ``A_VALIDER`` : proposition technique, appliquée mais signalée dans les contrôles.

Une décision de la Conformité (table ``clientele_bcm_regles``, append-only) remplace la valeur et le statut.
Les règles effectivement appliquées sont figées dans chaque déclaration calculée.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

StatutRegle = Literal["CONFIRMEE", "A_VALIDER"]
STATUTS_REGLE = ("CONFIRMEE", "A_VALIDER")

FORMES_BCM = ("PP", "PM", "CJ")
INTERDIT_OPTIONS = ("HORS_COLONNES", "ELEVE")
FENETRE_OPTIONS = ("CALENDAIRE", "GLISSANTE")


class RegleDef(TypedDict):
    code: str
    libelle: str
    valeur: Any
    statut: StatutRegle
    origine: str
    explication: str


CORRESPONDANCE_FORMES: dict[str, list[str]] = {
    "PP": ["PERSONNE PHYSIQUE"],
    "PM": [
        "SOCIETE COMMERCIALE",
        "AUT PERS MORALE IMMAT. AU RCS",
        "PERS MORALE SOUMIS DROIT ADMIN",
        "PERS.MOR. PUB SOUMIS DROIT COMM",
        "ORGANISME PRIVE SPECIALISE",
        "PERSONNE MORALE DROIT ETRANGER",
    ],
    "CJ": [],
}

REGLES: tuple[RegleDef, ...] = (
    {
        "code": "stock.date_entree",
        "libelle": "Date d'entrée en relation",
        "valeur": "PREMIER_COMPTE_ORION",
        "statut": "CONFIRMEE",
        "origine": "Arbitrage du 19/10/2026",
        "explication": "Un client existe à une date D si son premier compte ORION (date d'ouverture minimale) "
                       "est ouvert au plus tard à D. La date d'import dans BEA DIGITAL n'est pas utilisée.",
    },
    {
        "code": "stock.perimetre",
        "libelle": "Périmètre « actifs + inactifs »",
        "valeur": "TOUS",
        "statut": "CONFIRMEE",
        "origine": "Arbitrage du 19/10/2026",
        "explication": "Tous les clients entrés en relation à la date, y compris ceux dont tous les comptes "
                       "sont fermés aujourd'hui (ORION ne date pas la fermeture d'un compte).",
    },
    {
        "code": "actif.valeurs_gel",
        "libelle": "Valeurs du statut de gel signifiant « actif »",
        "valeur": ["ACTIF"],
        "statut": "A_VALIDER",
        "origine": "Définition métier : actif = compte ouvert et statut de gel actif (non inactif)",
        "explication": "Valeurs observées dans le fichier hebdomadaire : Actif, Inactif, Cloturé. Seule « Actif » "
                       "rend le client actif ; « Cloturé » n'est pas assimilé à actif. Le statut de compte et le "
                       "statut de gel restent deux données distinctes.",
    },
    {
        "code": "actif.agregation",
        "libelle": "Agrégation multi-comptes du statut actif",
        "valeur": "UN_COMPTE_OUVERT_ET_GEL_CLIENT_ACTIF",
        "statut": "A_VALIDER",
        "origine": "Proposition (cahier des charges §1.1), adaptée à la donnée disponible",
        "explication": "Actif si au moins un compte ORION est ouvert et si le statut de gel du client est actif. "
                       "Le gel n'est connu qu'au niveau client (fichier hebdomadaire, sans compte) : la règle "
                       "« au moins un compte ouvert et non gelé » ne peut pas être appliquée compte par compte. "
                       "Statut de gel inconnu → client « indéterminé », jamais compté actif ni inactif.",
    },
    {
        "code": "eer.source",
        "libelle": "EER du mois",
        "valeur": "PREMIER_COMPTE_ORION",
        "statut": "CONFIRMEE",
        "origine": "Arbitrage du 19/10/2026",
        "explication": "Clients distincts dont le premier compte ORION a été ouvert pendant le mois. Le module "
                       "EER (dossiers VALIDE / CLOTURE / ARCHIVE, date EER dans le mois) sert de contrôle croisé.",
    },
    {
        "code": "maj.fenetre",
        "libelle": "Fenêtre « cinq dernières années »",
        "valeur": {"type": "CALENDAIRE", "annees": 5},
        "statut": "A_VALIDER",
        "origine": "Proposition (cahier des charges §1.4)",
        "explication": "CALENDAIRE : du 1er janvier de Y-5 à la fin du mois de déclaration, bornes incluses. "
                       "GLISSANTE : les 12 × années mois précédant la fin du mois de déclaration.",
    },
    {
        "code": "maj.evenements",
        "libelle": "Événements de mise à jour des données client",
        "valeur": ["CLASSEMENT_VALIDE", "DONNEES_VALIDEES", "DATE_MAJ_KYC"],
        "statut": "A_VALIDER",
        "origine": "Cahier des charges §1.2",
        "explication": "CLASSEMENT_VALIDE : décision manuelle ou acceptation de classement (journal, historique "
                       "MANUEL). DONNEES_VALIDEES : mise à jour de données décidée (journal MAJ_DONNEES). "
                       "DATE_MAJ_KYC : date de mise à jour client déclarée par le KYC. Une consultation, un "
                       "import ou un classement automatique du moteur ne sont pas des mises à jour.",
    },
    {
        "code": "interdit.rattachement",
        "libelle": "Rattachement des clients INTERDIT",
        "valeur": "HORS_COLONNES",
        "statut": "A_VALIDER",
        "origine": "Le modèle BCM n'a pas de colonne « Interdit »",
        "explication": "HORS_COLONNES : décomptés à part, inclus dans le total. ELEVE : comptés en risque élevé "
                       "dans la déclaration seulement (le classement du client n'est jamais modifié). Tant que "
                       "la règle n'est pas confirmée, la validation est bloquée s'il existe des clients INTERDIT.",
    },
    {
        "code": "forme.correspondance",
        "libelle": "Correspondance catégorie juridique ORION → colonne BCM",
        "valeur": CORRESPONDANCE_FORMES,
        "statut": "A_VALIDER",
        "origine": "Proposition (cahier des charges §2)",
        "explication": "Catégorie juridique ORION absente de la table, vide ou non rattachée (groupements, "
                       "associations…) → exception listée, jamais affectée par défaut. Aucune catégorie n'est "
                       "rattachée aux constructions juridiques sans décision.",
    },
    {
        "code": "forme.repli_profil",
        "libelle": "Repli sur le profil PP / PM de BEA DIGITAL si la catégorie est vide",
        "valeur": False,
        "statut": "A_VALIDER",
        "origine": "Option, désactivée par défaut",
        "explication": "Le profil PP / PM de la vue Situation est une déduction technique, pas une forme "
                       "juridique déclarée. Activable seulement sur décision.",
    },
    {
        "code": "risque.date_reference",
        "libelle": "Niveau de risque retenu à une date",
        "valeur": "DERNIER_HISTORIQUE_A_LA_DATE",
        "statut": "CONFIRMEE",
        "origine": "Cahier des charges §6",
        "explication": "Dernière entrée de l'historique de classification au plus tard à la date (jour civil "
                       "de Nouakchott). Sans historique couvrant la date, les cellules par risque ne sont pas "
                       "calculées et la validation est bloquée.",
    },
)

PAR_CODE: dict[str, RegleDef] = {r["code"]: r for r in REGLES}


def _norm(v: Any) -> str:
    return " ".join(str(v or "").upper().split())


def valider_valeur(code: str, valeur: Any) -> Any:
    """Contrôle de forme d'une valeur décidée. Lève ValueError avec un message lisible."""
    if code not in PAR_CODE:
        raise ValueError(f"Règle inconnue : {code}")
    if code in ("stock.date_entree", "eer.source", "risque.date_reference", "actif.agregation",
                "stock.perimetre"):
        if valeur != PAR_CODE[code]["valeur"]:
            raise ValueError("Seule la valeur documentée est disponible pour cette règle")
        return valeur
    if code == "interdit.rattachement":
        if valeur not in INTERDIT_OPTIONS:
            raise ValueError(f"Valeur attendue : {', '.join(INTERDIT_OPTIONS)}")
        return valeur
    if code == "maj.fenetre":
        if not isinstance(valeur, dict) or valeur.get("type") not in FENETRE_OPTIONS:
            raise ValueError("Fenêtre attendue : {type: CALENDAIRE | GLISSANTE, annees: entier}")
        annees = valeur.get("annees")
        if not isinstance(annees, int) or not 1 <= annees <= 10:
            raise ValueError("Nombre d'années attendu entre 1 et 10")
        return {"type": valeur["type"], "annees": annees}
    if code == "maj.evenements":
        permis = set(PAR_CODE[code]["valeur"])
        if not isinstance(valeur, list) or not valeur or not set(valeur) <= permis:
            raise ValueError(f"Événements attendus parmi : {', '.join(sorted(permis))}")
        return sorted(set(valeur))
    if code == "actif.valeurs_gel":
        if not isinstance(valeur, list) or not valeur:
            raise ValueError("Liste de valeurs de gel attendue")
        return sorted({_norm(v) for v in valeur if _norm(v)})
    if code == "forme.repli_profil":
        if not isinstance(valeur, bool):
            raise ValueError("Valeur attendue : vrai ou faux")
        return valeur
    if code == "forme.correspondance":
        if not isinstance(valeur, dict) or set(valeur) != set(FORMES_BCM):
            raise ValueError("Correspondance attendue avec les clés PP, PM, CJ")
        vues: dict[str, str] = {}
        propre: dict[str, list[str]] = {}
        for forme in FORMES_BCM:
            liste = valeur[forme]
            if not isinstance(liste, list):
                raise ValueError(f"{forme} : liste de catégories attendue")
            propre[forme] = sorted({_norm(x) for x in liste if _norm(x)})
            for cat in propre[forme]:
                if cat in vues:
                    raise ValueError(f"Catégorie « {cat} » rattachée à {vues[cat]} et à {forme}")
                vues[cat] = forme
        return propre
    raise ValueError(f"Règle non paramétrable : {code}")
