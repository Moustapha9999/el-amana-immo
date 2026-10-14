"""Libellés et regroupements métier des réclamations (statut ≠ étape du circuit)."""

from __future__ import annotations

MODULE_CODE = "reclamations"
ESPACE_CODE = "audit-controle-conformite"
GED_ENTITE = "reclamation"
PREFIXE_REFERENCE = "REC"

STATUT_LIBELLES: dict[str, str] = {
    "RECUE": "Reçue initialement",
    "RECUE_SR": "Reçue par le Service Réclamations",
    "A_QUALIFIER": "Ouverte — à qualifier",
    "AFFECTEE": "Affectée — transmise",
    "EN_TRAITEMENT": "En cours de traitement",
    "ATTENTE_INFO": "En attente d'information",
    "RETOUR_RECU": "Retour reçu — à vérifier",
    "REPONSE_A_PREPARER": "Réponse à préparer",
    "REPONSE_ENVOYEE": "Réponse envoyée — à clôturer",
    "SUSPENDUE": "Suspendue",
    "REFUSEE": "Refusée / irrecevable",
    "CLOTUREE": "Clôturée",
    "REOUVERTE": "Réouverte",
    "ANNULEE": "Annulée / doublon",
}

ETAPE_LIBELLES: dict[str, str] = {
    "RECEPTION": "Réception",
    "QUALIFICATION": "Qualification",
    "AFFECTATION": "Affectation au service",
    "TRAITEMENT": "Traitement par le service",
    "RETOUR": "Retour au Service Réclamations",
    "REPONSE": "Réponse au client",
    "CLOTURE": "Clôture",
}

# Statut simplifié affiché et utilisé par les KPI ; la chronologie garde le détail.
STATUT_GROUPES: dict[str, str] = {
    "RECUE": "RECUE",
    "RECUE_SR": "RECUE",
    "A_QUALIFIER": "A_QUALIFIER",
    "REOUVERTE": "A_QUALIFIER",
    "AFFECTEE": "EN_COURS",
    "EN_TRAITEMENT": "EN_COURS",
    "RETOUR_RECU": "EN_COURS",
    "REPONSE_A_PREPARER": "EN_COURS",
    "REPONSE_ENVOYEE": "EN_COURS",
    "ATTENTE_INFO": "EN_ATTENTE",
    "SUSPENDUE": "SUSPENDUE",
    "REFUSEE": "REFUSEE",
    "CLOTUREE": "CLOTUREE",
    "ANNULEE": "ANNULEE",
}
GROUPE_LIBELLES: dict[str, str] = {
    "RECUE": "Reçues",
    "A_QUALIFIER": "À qualifier",
    "EN_COURS": "En cours",
    "EN_ATTENTE": "En attente",
    "SUSPENDUE": "Suspendues",
    "REFUSEE": "Refusées",
    "CLOTUREE": "Clôturées",
    "ANNULEE": "Annulées / doublons",
}
# Dossiers qui ne sont plus dans le stock ouvert.
STATUTS_TERMINAUX = frozenset({"CLOTUREE", "REFUSEE", "ANNULEE"})

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
    "ORIGINAL": "Scan original de la réclamation",
    "PIECE_CLIENT": "Pièce fournie par le client",
    "TRANSMISSION": "Document de transmission",
    "FICHE_TRAITEMENT": "Fiche de traitement",
    "JUSTIFICATIF_SERVICE": "Justificatif du service",
    "RETOUR_SERVICE": "Retour du service",
    "REPONSE_CLIENT": "Réponse envoyée au client",
    "PREUVE_ENVOI": "Preuve d'envoi",
    "AUTRE": "Autre document",
}
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
    "REFUS": "Dossier refusé",
    "ANNULATION": "Dossier annulé",
    "REPONSE_BROUILLON": "Brouillon de réponse enregistré",
    "REPONSE_SOUMISE": "Réponse soumise à validation",
    "REPONSE_VALIDEE": "Réponse validée",
    "REPONSE_RENVOYEE": "Réponse renvoyée pour retravail",
    "REPONSE_ENVOYEE": "Réponse envoyée au client",
    "CLOTURE": "Dossier clôturé",
    "REOUVERTURE": "Dossier réouvert",
    "ARCHIVAGE": "Dossier archivé",
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
VALIDATION_REGLE_LIBELLES: dict[str, str] = {
    "A_VALIDER": "À valider par la Conformité",
    "VALIDEE": "Validée (présentable comme délai interne validé)",
    "REJETEE": "Rejetée",
}
UNITE_DUREE_LIBELLES: dict[str, str] = {
    "JOURS_CALENDAIRES": "Jours calendaires",
    "JOURS_OUVRES": "Jours ouvrés",
}
POINT_DEPART_LIBELLES: dict[str, str] = {
    "PREMIERE_RECEPTION": "Première réception par la banque",
    "RECEPTION_SR": "Réception par le Service Réclamations",
}
# Paramètre (``reclamation_parametres``) : la banque autorise-t-elle la référence d'enregistrement d'appel ?
PARAM_ENREGISTREMENT_APPELS = "enregistrement_appels_autorise"
