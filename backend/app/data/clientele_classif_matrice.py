"""Matrice maître LBC/FT BEA DIGITAL — catalogue des critères, pas des règles validées.

Les niveaux et poids cités viennent des Excel (Matrice V1, Scoring V4) ou sont
explicitement marqués PROPOSITION_BEA_DIGITAL / A_ARBITRER.
Rien n'est VALIDEE tant que la Conformité n'a pas tranché.
"""
from __future__ import annotations

from typing import Any

NIVEAUX = ("FAIBLE", "MOYEN", "ELEVE", "INTERDIT")
RANG = {"FAIBLE": 1, "MOYEN": 2, "ELEVE": 3, "INTERDIT": 4}
POIDS_ECHELLE = {"FAIBLE": 100, "MOYEN": 10_000, "ELEVE": 100_000}

# CDC 1.0 §4 — seuils V4 corrigés (le libellé Excel C39 était défectueux).
SEUILS_CDC = {
    "FAIBLE_MAX": 10_000,     # score < 10000 → FAIBLE
    "MOYEN_MAX": 100_000,     # 10000 ≤ score < 100000 → MOYEN
    "ELEVE_MIN": 100_000,     # score ≥ 100000 → ELEVE
    "source": "CDC_1.0",
    "statut": "VALIDEE_CDC",
    "note_v4": (
        "Défaut Excel C39 (inégalités strictes + score==10000 incomplet) corrigé. "
        "INTERDIT n'est pas un seuil de score, c'est un blocage métier."
    ),
}
SEUILS_PROPOSITION = SEUILS_CDC  # alias rétrocompatible

VERSION_MOTEUR = "1.1.0-cdc"
VERSION_REGLES = "CLASSIFICATION-2026.01"

FAMILLES = ("CLIENT", "GEOGRAPHIE", "PRODUIT_SERVICE_OPERATION", "CANAL")

# États d'un critère pour une évaluation (jamais « absent = FAIBLE »).
ETATS_LIGNE = ("EVALUE", "NON_DISPONIBLE", "NON_APPLICABLE", "A_VERIFIER")

# Gouvernance d'une classification retenue.
GOUVERNANCES = ("AUTOMATIQUE", "MANUELLE", "MANUELLE_SURCHARGE")

STATUTS_REGLE = (
    "VALIDEE", "A_ARBITRER", "NON_DISPONIBLE", "A_CONFIGURER", "ALIGNEE",
    "INVALIDE_SOURCE", "SOURCE_V1", "SOURCE_V4",
)


def _c(
    code: str, libelle: str, *,
    source: str, disponible: str, utilisable_auto: bool,
    type_decision: str, champ: str | None, statut: str, note: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "libelle": libelle,
        "source": source,
        "disponible": disponible,
        "utilisable_auto": utilisable_auto,
        "type_decision": type_decision,
        "champ": champ,
        "statut": statut,
        "note": note,
    }


# Couverture complète des deux Excel + sources projet. Pas de suppression.
CRITERES_MAITRE: list[dict[str, Any]] = [
    _c("RACINE_CLIENT", "Racine client",
       source="ORION", disponible="OUI", utilisable_auto=True,
       type_decision="IDENTIFIANT", champ="racine_client", statut="ALIGNEE",
       note="Clé unique 6 chiffres. Classification au niveau CLIENT, jamais RIB."),
    _c("PROFIL", "Profil client",
       source="ORION", disponible="PARTIEL", utilisable_auto=True,
       type_decision="SCORE", champ="agent_economique", statut="A_ARBITRER",
       note="Matrice : PP Faible, PM publique Faible, PM privée Moyen, Association Élevé. "
            "V4 : PP/PM pub/PM priv = 100, Association = 100000. Divergence PM privée."),
    _c("FORME_JURIDIQUE", "Catégorie / forme juridique",
       source="ORION", disponible="OUI", utilisable_auto=True,
       type_decision="SCORE", champ="categorie_juridique", statut="A_ARBITRER",
       note="Matrice PM privée = Moyen ; V4 SA/SARL/… = 100 Faible."),
    _c("RESIDENCE", "Statut résident",
       source="ORION", disponible="OUI", utilisable_auto=True,
       type_decision="SCORE", champ="statut_resident", statut="ALIGNEE",
       note="Matrice : Résident Oui=Faible, Non=Élevé. V4 n'a pas R/N ; utilise le pays. "
            "Proposition : N → ÉLEVÉ (décision d'architecture, versionnée)."),
    _c("NATIONALITE", "Nationalité",
       source="ORION", disponible="OUI", utilisable_auto=True,
       type_decision="SCORE", champ="nationalite", statut="ALIGNEE",
       note="Matrice mauritanienne=Faible, étrangère=Moyen. V4 Pays Eng-FR : 100 vs 10000. "
            "Ne pas utiliser Liste!M:N."),
    _c("PAYS_RESIDENCE", "Pays de résidence",
       source="EER", disponible="APRES_LIAISON", utilisable_auto=False,
       type_decision="SCORE", champ="pays_residence", statut="SOURCE_V1",
       note="Absent d'ORION (seulement R/N). EER à brancher. "
            "Référentiel géographique = Zone V1 (CDC §17). V4 = contrôle."),
    _c("SECTEUR", "Secteur / sous-secteur d'activité",
       source="ORION", disponible="OUI", utilisable_auto=True,
       type_decision="SCORE", champ="secteur_activite", statut="SOURCE_V1",
       note="Matrice 119 sous-secteurs dont 5 INTERDIT bloquants (CDC §5, §13). "
            "V4 71 codes = contrôle, jamais substitués."),
    _c("LISTE_INTERDICTION", "Liste d'interdiction ORION",
       source="ORION", disponible="OUI", utilisable_auto=True,
       type_decision="SCORE", champ="liste_interdiction", statut="SOURCE_V1",
       note="Matrice filtrage sanctions Oui=Élevé, Non=Faible. Champ vide ORION = Non. "
            "Champ absent = NON_DISPONIBLE, jamais Faible inventé."),
    _c("FILTRAGE", "Alerte de filtrage confirmée",
       source="ALERTES", disponible="APRES_LIAISON", utilisable_auto=False,
       type_decision="HYBRIDE", champ=None, statut="A_ARBITRER",
       note="Séparée de LISTE_INTERDICTION. Confirmée → ÉLEVÉ ou INTERDIT : à trancher. "
            "Absence d'alerte ≠ Non."),
    _c("PPE", "Personne politiquement exposée",
       source="EER", disponible="APRES_LIAISON", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="ALIGNEE",
       note="Matrice Oui=Élevé, Non=Faible. V4 Oui=100000, Non=100. "
            "PPE inconnu ≠ Non. Brancher EER.ppe / ppe_dossier sur la racine."),
    _c("PPE_LISTE", "Présence sur liste PPE (filtrage)",
       source="ALERTES", disponible="APRES_LIAISON", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="NON_DISPONIBLE",
       note="Colonne matrice distincte du PPE déclaré. Pas encore de liste PPE dédiée."),
    _c("PROCURATION", "Compte avec procuration / mandataire",
       source="EER", disponible="APRES_LIAISON", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="ALIGNEE",
       note="Matrice Oui=Élevé. V4 « Compte avec procuration »=100000. "
            "Source : EER rôle MANDATAIRE / forme_mandat PROCURATION."),
    _c("ORIGINE_FONDS", "Origine des fonds",
       source="EER", disponible="A_CONFIRMER", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="A_CONFIGURER",
       note="V4 : Justifiée=100, Moyennement documentée=10000, Inconnue=100000. "
            "EER.origine_fonds est du texte libre, pas les 3 valeurs V4."),
    _c("BENEFICIAIRE_EFFECTIF", "Bénéficiaire effectif",
       source="EER", disponible="A_CONFIRMER", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="A_CONFIGURER",
       note="V4 : clairement identifié=100, difficilement/impossible=100000. "
            "Module EER calcule les BE ; mapping des 3 libellés à confirmer."),
    _c("REVENUS_PP", "Tranche de revenus PP",
       source="EER", disponible="A_CONFIRMER", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="NON_DISPONIBLE",
       note="Matrice uniquement (4 tranches). Absent du scoring V4 et d'ORION."),
    _c("REVENUS_PM", "Tranche de revenus PM",
       source="EER", disponible="A_CONFIRMER", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="NON_DISPONIBLE",
       note="Matrice uniquement (4 tranches). EER.salaire_net est PP, pas le CA PM."),
    _c("AGE_PP", "Âge personne physique (formule V4)",
       source="ORION", disponible="PARTIEL", utilisable_auto=True,
       type_decision="SCORE", champ="date_naissance", statut="A_ARBITRER",
       note="V4 H23 : si PP et (aujourd'hui - naissance) > 6580 jours → 100 sinon 10000. "
            "Absent de la matrice. Mineur = Moyen côté V4 uniquement."),
    _c("ENTREPRISE_RECENTE", "Ancienneté personne morale (formule V4)",
       source="EER", disponible="A_CONFIRMER", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="A_CONFIGURER",
       note="V4 H23 : PM publique=100 ; autre PM si >366 jours → 100 sinon 10000. "
            "Date de création = EER, pas la date d'ouverture de compte ORION."),
    _c("CANAL", "Canal d'ouverture / distribution",
       source="EER", disponible="A_CONFIRMER", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="A_ARBITRER",
       note="Matrice : Agence=Faible, À distance=Élevé. V4 : agence=100, téléphone/mail=100000."),
    _c("PRODUIT", "Produit / service / opération",
       source="OPERATIONS", disponible="NON", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="NON_DISPONIBLE",
       note="Feuille matrice Produit — pas dans ORION État des comptes."),
    _c("TYPE_OPERATION", "Type d'opération",
       source="OPERATIONS", disponible="NON", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="NON_DISPONIBLE",
       note="Même feuille Produit (guichet, middle office, monétique, engagements…)."),
    _c("PAYS_PROVENANCE_FONDS", "Pays de provenance des fonds",
       source="OPERATIONS", disponible="NON", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="NON_DISPONIBLE",
       note="Matrice Zone géographique : résidence, provenance ou destination."),
    _c("PAYS_DESTINATION_FONDS", "Pays de destination des fonds",
       source="OPERATIONS", disponible="NON", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="NON_DISPONIBLE",
       note="Même référentiel pays. Donnée opérations absente."),
    _c("JUGEMENT_TRANSACTIONS", "Jugement sur les transactions",
       source="EER", disponible="A_CONFIRMER", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="A_CONFIGURER",
       note="V4 Liste transaction : cohérentes=100, quelques incohérences=10000, "
            "majeures/suspectes=100000, surveillance=100000."),
    _c("ETAPE_EER", "Étape de l'entrée en relation",
       source="EER", disponible="OUI", utilisable_auto=False,
       type_decision="SCORE", champ=None, statut="ALIGNEE",
       note="V4 Nouvelle_ouverture / Mise_à_jour = poids 0. N'influe pas le score."),
    _c("ASSOCIATION", "Association / ONG / fondation / coop / parti",
       source="ORION", disponible="OUI", utilisable_auto=True,
       type_decision="SCORE", champ="categorie_juridique", statut="ALIGNEE",
       note="Matrice ÉLEVÉ. V4 100000. Première version moteur : ÉLEVÉ sauf décision contraire."),
    _c("RISQUE_EXISTANT", "Classification déjà présente",
       source="BEA_DIGITAL", disponible="OUI", utilisable_auto=False,
       type_decision="SCORE", champ="niveau", statut="A_CONFIGURER",
       note="Ne pas boucler : le moteur ne relit pas sa propre sortie comme critère."),
]

QUESTIONS_CONFORMITE: list[dict[str, str]] = [
    {
        "id": "Q1_PM_PRIVEE",
        "sujet": "Profil / formes PM privée",
        "question": "Matrice = Moyen, Scoring V4 = 100 Faible. Quel niveau BEA DIGITAL ?",
    },
    {
        "id": "Q2_SEUILS",
        "sujet": "Seuils de score",
        "question": "CDC 1.0 §4 : <10000 FAIBLE ; 10000≤score<100000 MOYEN ; ≥100000 ÉLEVÉ. Défaut Excel C39 corrigé.",
        "decision_cdc": "VALIDEE_CDC",
    },
    {
        "id": "Q3_INTERDIT_PAYS",
        "sujet": "Pays INTERDIT vs Inacceptable",
        "question": "CDC 1.0 §5 et §17 : les 7 pays INTERDIT de la Zone V1 sont bloquants. "
                    "V4 Inacceptable (4 pays) est un contrôle, jamais un remplacement silencieux.",
        "decision_cdc": "VALIDEE_CDC",
    },
    {
        "id": "Q4_INTERDIT_SECTEUR",
        "sujet": "Secteurs INTERDIT",
        "question": "CDC 1.0 §5 et §13 : Casino, jeux de hasard, armement, pornographie, alcool "
                    "sont INTERDIT bloquants (matrice V1). Absents du scoring V4, non substitués.",
        "decision_cdc": "VALIDEE_CDC",
    },
    {
        "id": "Q5_SANCTIONS",
        "sujet": "Filtrage / liste d'interdiction",
        "question": "Correspondance confirmée → INTERDIT bloquant ou ÉLEVÉ (matrice = Élevé) ?",
    },
    {
        "id": "Q6_PPE_ABSENT",
        "sujet": "PPE sans EER",
        "question": "Confirmer : PPE non renseigné = NON DISPONIBLE, jamais Non/Faible.",
    },
    {
        "id": "Q7_SANS_CRITERE",
        "sujet": "Aucun critère exploitable",
        "question": "Confirmer : NON CLASSÉ / À COMPLÉTER, jamais FAIBLE par défaut "
                    "(proposition de conception, absente des Excel).",
    },
    {
        "id": "Q8_AGE_PP",
        "sujet": "Mineur PP (formule V4 6580 jours)",
        "question": "Reprendre le Moyen V4 pour un PP de moins de ~18 ans ? Absent de la matrice.",
    },
    {
        "id": "Q9_PP_NON_RESIDENT_CATEGORIE",
        "sujet": "Catégorie PP « Non Résident »",
        "question": "Présente dans la matrice (Élevé), absente des 1101–1108 V4. "
                    "Le statut R/N ORION suffit-il ?",
    },
    {
        "id": "Q10_PAYS_RECONCILIATION",
        "sujet": "Table pays unique",
        "question": "Valider la table de réconciliation Matrice Zone + Pays Eng-FR "
                    "(256 lignes, divergences listées) comme version BEA DIGITAL.",
    },
]


def critere_par_code(code: str) -> dict[str, Any] | None:
    for c in CRITERES_MAITRE:
        if c["code"] == code:
            return c
    return None
