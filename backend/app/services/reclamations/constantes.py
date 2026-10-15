"""Libellés et regroupements métier des réclamations (statut ≠ étape du circuit)."""

from __future__ import annotations

MODULE_CODE = "reclamations"
ESPACE_CODE = "audit-controle-conformite"
GED_ENTITE = "reclamation"
PREFIXE_REFERENCE = "REC"

STATUT_LIBELLES: dict[str, str] = {
    "A_QUALIFIER": "À qualifier",
    "A_AFFECTER": "À affecter",
    "EN_TRAITEMENT": "En traitement",
    "RETOUR_RECU": "Retour reçu",
    "A_CLOTURER": "À clôturer",
    "CLOTUREE": "Clôturée",
    "REJETEE": "Rejetée",
    "ANNULEE": "Annulée",
    "REOUVERTE": "Réouverte",
}
# Statuts du circuit précédent (avant 20261014_reclamations_02) : lus uniquement dans l'historique.
STATUT_LIBELLES_HISTORIQUES: dict[str, str] = {
    "RECUE": "Reçue initialement",
    "RECUE_SR": "Reçue par le Service Réclamations",
    "AFFECTEE": "Affectée — transmise",
    "ATTENTE_INFO": "En attente d'information",
    "REPONSE_A_PREPARER": "Réponse à préparer",
    "REPONSE_ENVOYEE": "Réponse envoyée — à clôturer",
    "SUSPENDUE": "Suspendue",
    "REFUSEE": "Refusée / irrecevable",
}

# Circuit : Réception → Affectation → Traitement → Clôture. Le détail vit dans l'historique.
ETAPE_LIBELLES: dict[str, str] = {
    "RECEPTION": "Réception",
    "AFFECTATION": "Affectation",
    "TRAITEMENT": "Traitement",
    "CLOTURE": "Clôture",
}
ETAPE_LIBELLES_HISTORIQUES: dict[str, str] = {
    "QUALIFICATION": "Qualification",
    "RETOUR": "Retour au Service Réclamations",
    "REPONSE": "Réponse au client",
}
ETAPE_DU_STATUT: dict[str, str] = {
    "A_QUALIFIER": "RECEPTION",
    "A_AFFECTER": "AFFECTATION",
    "REOUVERTE": "AFFECTATION",
    "EN_TRAITEMENT": "TRAITEMENT",
    "RETOUR_RECU": "CLOTURE",
    "A_CLOTURER": "CLOTURE",
    "CLOTUREE": "CLOTURE",
    "REJETEE": "CLOTURE",
    "ANNULEE": "CLOTURE",
}

STATUT_GROUPES: dict[str, str] = {
    "A_QUALIFIER": "EN_COURS",
    "A_AFFECTER": "EN_COURS",
    "EN_TRAITEMENT": "EN_COURS",
    "RETOUR_RECU": "EN_COURS",
    "A_CLOTURER": "EN_COURS",
    "REOUVERTE": "EN_COURS",
    "CLOTUREE": "CLOTUREE",
    "REJETEE": "REJETEE",
    "ANNULEE": "ANNULEE",
}
GROUPE_LIBELLES: dict[str, str] = {
    "EN_COURS": "En cours",
    "CLOTUREE": "Clôturées",
    "REJETEE": "Rejetées",
    "ANNULEE": "Annulées",
}
# Dossiers qui ne sont plus dans le stock ouvert.
STATUTS_TERMINAUX = frozenset({"CLOTUREE", "REJETEE", "ANNULEE"})
# Saisie libre « Autre » à la place d'un motif / sous-motif du référentiel.
AUTRE = "Autre"
DEVISE = "MRU"
MAX_OPERATIONS = 2000

PRIORITE_LIBELLES: dict[str, str] = {
    "BASSE": "Basse",
    "NORMALE": "Normale",
    "HAUTE": "Haute",
    "URGENTE": "Urgente",
}
RESULTAT_LIBELLES: dict[str, str] = {
    "FAVORABLE": "Favorable",
    "PARTIELLEMENT_FAVORABLE": "Partiellement favorable",
    "DEFAVORABLE": "Défavorable",
    "SANS_SUITE": "Sans suite",
    "AUTRE": "Autre",
}
CATEGORIE_CLIENT_LIBELLES: dict[str, str] = {
    "PP": "Personne physique",
    "PM": "Personne morale",
    "NON_CLIENT": "Non-client / prospect",
}
CATEGORIE_DOCUMENT_LIBELLES: dict[str, str] = {
    "NOTE": "Note administrative / interne",
    "COURRIER": "Courrier",
    "JUSTIFICATIF": "Justificatif",
    "FICHE_TRAITEMENT": "Document de traitement",
    "RETOUR_SERVICE": "Retour du service",
    "ORIGINAL": "Scan original de la réclamation",
    "PIECE_CLIENT": "Pièce fournie par le client",
    "TRANSMISSION": "Document de transmission",
    "JUSTIFICATIF_SERVICE": "Justificatif du service",
    "REPONSE_CLIENT": "Réponse envoyée au client",
    "PREUVE_ENVOI": "Preuve d'envoi",
    "IMPORT_OPERATIONS": "Fichier d'import des opérations",
    "AUTRE": "Autre document",
}
# Note signée puis scannée : PDF ou image uniquement.
CATEGORIE_NOTE = "NOTE"
CATEGORIE_IMPORT = "IMPORT_OPERATIONS"
FORMATS_SCAN = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"})
# Pièces à valeur probante vis-à-vis du client : elles interdisent la suppression du dossier.
CATEGORIES_OFFICIELLES = frozenset({"REPONSE_CLIENT", "PREUVE_ENVOI"})
# Décision officielle rendue : le dossier se conserve (réouverture ou archivage, jamais suppression).
STATUTS_NON_SUPPRIMABLES = frozenset({"CLOTUREE", "REJETEE"})
TYPE_UNITE_LIBELLES: dict[str, str] = {
    "DIRECTION": "Direction",
    "DEPARTEMENT": "Département",
    "SERVICE": "Service",
    "AGENCE": "Agence",
    "CELLULE": "Cellule",
}
DOMAINE_LIBELLES: dict[str, str] = {
    "TYPE": "Type",
    "MOTIF": "Motif",
    "SOUS_MOTIF": "Sous-motif",
    "CANAL": "Canal de réception",
    "CANAL_REPONSE": "Canal d'envoi de la réponse",
}
# Hiérarchie des référentiels : domaine → domaine parent obligatoire.
DOMAINE_PARENT: dict[str, str] = {"MOTIF": "TYPE", "SOUS_MOTIF": "MOTIF"}
CANAL_TELEPHONE = "TELEPHONE"

STATUT_RAPPEL_LIBELLES: dict[str, str] = {
    "AUCUN": "Aucun rappel",
    "A_RAPPELER": "À rappeler",
    "RAPPELE": "Rappelé",
    "ECHEC": "Rappel sans réponse",
}
EVENEMENT_LIBELLES: dict[str, str] = {
    "CREATION": "Réclamation enregistrée",
    "RECEPTION_SR": "Réception par le Service Réclamations",
    "MODIFICATION": "Données modifiées",
    "OPERATIONS": "Opérations concernées modifiées",
    "MIGRATION_CIRCUIT": "Reprise dans le circuit en 4 étapes",
    "APPEL": "Appel enregistré",
    "DOCUMENT_AJOUT": "Pièce ajoutée",
    "DOCUMENT_RETRAIT": "Pièce retirée",
    "QUALIFICATION": "Dossier qualifié",
    "AFFECTATION": "Transmis au service",
    "PRISE_EN_CHARGE": "Pris en charge par le service",
    "RETOUR_SERVICE": "Retour du service",
    "EVALUATION": "Retour examiné",
    "RENVOI": "Renvoyé au service",
    "TRAITEMENT_INTERNE": "Traité par le Service Réclamations",
    "DEMANDE_INFO": "Information demandée",
    "REPRISE": "Reprise du traitement",
    "SUSPENSION": "Dossier suspendu",
    "REFUS": "Dossier rejeté",
    "ANNULATION": "Dossier annulé",
    "REPONSE_BROUILLON": "Brouillon de réponse enregistré",
    "REPONSE_SOUMISE": "Réponse soumise à validation",
    "REPONSE_VALIDEE": "Réponse validée",
    "REPONSE_RENVOYEE": "Réponse renvoyée pour retravail",
    "REPONSE_ENVOYEE": "Réponse envoyée au client",
    "CLOTURE": "Dossier clôturé",
    "REOUVERTURE": "Dossier réouvert",
    "ARCHIVAGE": "Dossier archivé",
    "SUPPRESSION": "Dossier supprimé (corbeille)",
    "RESTAURATION": "Dossier restauré",
    "DELAI_CALCULE": "Échéance calculée (règle de délai validée)",
    "IMPORT_ANALYSE": "Fichier d'opérations analysé",
    "IMPORT_CONFIRME": "Opérations importées depuis Excel",
    "IMPORT_ABANDONNE": "Import d'opérations abandonné",
}
STATUT_IDENTIFICATION_LIBELLES: dict[str, str] = {
    "VERIFIE": "Vérifié",
    "A_VERIFIER": "À vérifier",
    "A_RENSEIGNER": "À renseigner",
}
ROLE_PARTICIPANT_LIBELLES: dict[str, str] = {
    "PRINCIPAL": "Client principal",
    "ASSOCIE": "Client associé",
}
STATUT_AFFECTATION_LIBELLES: dict[str, str] = {
    "TRANSMISE": "Transmise",
    "RECUE": "Reçue par le service",
    "EN_TRAITEMENT": "En traitement",
    "RETOURNEE": "Retournée",
    "ANNULEE": "Annulée",
}
STATUT_REPONSE_LIBELLES: dict[str, str] = {
    "BROUILLON": "Brouillon",
    "A_VALIDER": "À valider",
    "VALIDEE": "Validée",
    "ENVOYEE": "Envoyée",
    "ANNULEE": "Annulée",
}
EVALUATION_LIBELLES: dict[str, str] = {
    "SUFFISANT": "Retour suffisant",
    "INSUFFISANT": "Retour insuffisant — à renvoyer",
}
VALIDATION_REFERENTIEL_LIBELLES: dict[str, str] = {
    "PROPOSEE": "Proposée — en attente de validation",
    "VALIDEE": "Validée par la banque",
}
# Paramètre (``reclamation_parametres``) : la banque autorise-t-elle la référence d'enregistrement d'appel ?
PARAM_ENREGISTREMENT_APPELS = "enregistrement_appels_autorise"
# Paramètre : un dossier peut-il réunir plusieurs clients ? (absent = oui, avec justification)
PARAM_MULTI_CLIENTS = "regroupement_multi_clients_autorise"
MAX_LIGNES_IMPORT = MAX_OPERATIONS
