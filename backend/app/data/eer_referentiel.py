"""Référentiel initial EER — valeurs issues des fiches officielles BEA uniquement.

Sources : 7 PDF interactifs (fiches PP, PM privée, PM publique, associations, mandataire,
actionnaire PM, spécimen de signature) + Cahier-charge-gestion-ouverture-compte.docx.
Voir docs/conformite/eer-matrices.md. Les pièces justificatives exactes par profil ne
figurent dans aucune source : elles se paramètrent dans les règles de checklist, sans code.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.services.eer.constantes import (
    Axe,
    NatureElement,
    OperationType,
    Risque,
    RoleDossier,
    TypeClient,
    TypeControle,
)

TRANCHES_PP = [
    ("PP_LT_50K", "Moins de 50 000 MRU"),
    ("PP_50K_100K", "Entre 50 000 MRU et 100 000 MRU"),
    ("PP_100K_200K", "Entre 100 000 MRU et 200 000 MRU"),
    ("PP_GT_200K", "Plus de 200 000 MRU"),
]
TRANCHES_PM = [
    ("PM_LT_100K", "Moins de 100 000 MRU"),
    ("PM_100K_1M", "Entre 100 000 MRU et 1 000 000 MRU"),
    ("PM_1M_5M", "Entre 1 000 000 MRU et 5 000 000 MRU"),
    ("PM_GT_5M", "Plus de 5 000 000 MRU"),
]

TYPES_CLIENT: dict[TypeClient, dict[str, Any]] = {
    TypeClient.PP: {
        "libelle": "Personne physique",
        "libelle_excel": "Personne_Physique",
        "identifiant": "IDP",
        "profils": [
            "Salarié", "Retraité", "Etudiant", "Sans Emploi",
            "Professionnel", "Entrepreneur", "Rentier", "Personnel BEA",
        ],
        "tranches": TRANCHES_PP,
        "ppe_fatca": True,
        "actionnariat": False,
        "risque_impose": None,
    },
    TypeClient.PM_PRIVEE: {
        "libelle": "Personne morale privée",
        "libelle_excel": "Personne_Morale_Privée",
        "identifiant": "IDM",
        "profils": [
            "SA", "SARL", "SUARL", "Succursale", "Groupement", "Etablissement", "Projet Privé",
            "Professions Libérales", "Institutions financières", "SNC", "SCS", "SP", "SAS", "SCA",
        ],
        "tranches": TRANCHES_PM,
        "ppe_fatca": True,
        "actionnariat": True,
        "risque_impose": None,
    },
    TypeClient.PM_PUBLIQUE: {
        "libelle": "Personne morale publique",
        "libelle_excel": "Personne_Morale_Publique",
        "identifiant": "IDP",
        "profils": [
            "EPIC", "EPA", "Collectivités", "Administration Centrale", "Institution Nationale",
            "Institution Internationale", "Institution financière public", "Ambassade", "Projet public",
        ],
        "tranches": TRANCHES_PM,
        # La fiche PM publique n'a ni section PPE ni section FATCA.
        "ppe_fatca": False,
        "actionnariat": True,
        "risque_impose": None,
    },
    TypeClient.ASSOCIATION: {
        "libelle": "Personne morale associations",
        "libelle_excel": "Personne_Morale_Association",
        "identifiant": "IDM",
        "profils": ["Association", "ONG", "Fondation", "Coopérative", "Parti politique", "Projet"],
        "tranches": TRANCHES_PM,
        "ppe_fatca": True,
        "actionnariat": False,
        # « Un client de ce profil est automatiquement classé à risque élevé ».
        "risque_impose": Risque.ELEVE,
    },
}

OPERATIONS_ACTIVES_V1 = frozenset({OperationType.ENTREE_RELATION})

SITUATIONS_MATRIMONIALES = ["Célibataire", "Marié(e)", "Divorcé(e)", "Veuf(ve)"]
TYPES_PIECE = [("NNI", "NNI"), ("CARTE_SEJOUR", "Carte séjour"),
               ("CARTE_DIPLOMATIQUE", "Carte diplomatique"), ("PASSEPORT", "Passeport")]
FORMES_MANDAT = [("MANDATAIRE_SOCIAL", "Mandataire social"), ("PROCURATION", "Procuration")]
TYPES_SIGNATURE = [("UNIQUE", "Unique"), ("CONJOINTES", "Conjointes"), ("SEPAREES", "Séparées")]
ETATS_COMPTE = ["Actif", "Inactif", "Bloqué", "Fermé"]

PARAMETRES_INITIAUX: dict[str, Any] = {
    # Fiches PM : « au moins 10 % » — règle documentée, modifiable sans code.
    "be.seuil_pourcentage": 10,
    # Décision du 04/10/2026 : tout agent du module fait toutes les étapes (créateur, analyste,
    # avis, validation) ; réactivable par un nouveau paramètre daté.
    "workflow.separation_roles": False,
    # Valeurs non fournies par la banque : laissées vides jusqu'à validation.
    "controle.expiration_proche_jours": None,
    "complement.delai_regularisation_jours": None,
    "acces.portee": None,
}


def code_profil(libelle: str) -> str:
    """Code stable d'un profil à partir du libellé des fiches (« Projet Privé » → PROJET_PRIVE)."""
    sans_accent = unicodedata.normalize("NFKD", libelle).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", sans_accent.upper()).strip("_")


def referentiels_initiaux() -> list[dict[str, Any]]:
    """Lignes de ``eer_referentiels`` : uniquement les listes des fiches officielles."""
    lignes: list[dict[str, Any]] = []

    def ajouter(domaine: str, code: str, libelle: str, ordre: int, parent: tuple[str, str] | None = None,
                meta: dict | None = None) -> None:
        lignes.append({"domaine": domaine, "code": code, "libelle": libelle, "ordre": ordre,
                       "parent": parent, "meta": meta or {}})

    for i, (type_client, d) in enumerate(TYPES_CLIENT.items(), 1):
        ajouter("TYPE_CLIENT", type_client, d["libelle"], i, meta={
            "libelle_excel": d["libelle_excel"], "identifiant": d["identifiant"],
            "ppe_fatca": d["ppe_fatca"], "actionnariat": d["actionnariat"],
            "risque_impose": d["risque_impose"]})
        for j, profil in enumerate(d["profils"], 1):
            ajouter("PROFIL", code_profil(profil), profil, j, parent=("TYPE_CLIENT", type_client))
    for domaine, liste in (("TRANCHE_PP", TRANCHES_PP), ("TRANCHE_PM", TRANCHES_PM), ("TYPE_PIECE", TYPES_PIECE),
                           ("FORME_MANDAT", FORMES_MANDAT), ("TYPE_SIGNATURE", TYPES_SIGNATURE)):
        for i, (code, libelle) in enumerate(liste, 1):
            ajouter(domaine, code, libelle, i)
    for domaine, valeurs in (("SITUATION_MATRIMONIALE", SITUATIONS_MATRIMONIALES), ("ETAT_COMPTE", ETATS_COMPTE)):
        for i, libelle in enumerate(valeurs, 1):
            ajouter(domaine, code_profil(libelle), libelle, i)
    for i, operation in enumerate(OperationType, 1):
        ajouter("OPERATION_TYPE", operation, operation.replace("_", " ").capitalize(), i,
                meta={"actif_v1": operation in OPERATIONS_ACTIVES_V1})
    return lignes


def _f(chemin: str, libelle: str, section: str, *, obligatoire: bool = True,
       condition: dict | None = None) -> dict[str, Any]:
    return {"chemin": chemin, "libelle": libelle, "section": section,
            "obligatoire": obligatoire, "condition": condition}


_ENTETE = [
    _f("dossier.operation_type", "Motif de la fiche", "Motif de la fiche client"),
    _f("dossier.date_eer", "Date", "Motif de la fiche client"),
    _f("dossier.agence_code", "Code agence", "Motif de la fiche client"),
    _f("dossier.racine_client", "Racine client", "Motif de la fiche client",
       condition={"fact": "compte_ouvert", "op": "eq", "value": True}),
    _f("dossier.profil", "Profil client", "Profil client"),
]
_IDENTITE_PP = [
    _f("{p}.pp.sexe", "Sexe", "Fiche signalétique"),
    _f("{p}.pp.prenom", "Prénom", "Fiche signalétique"),
    _f("{p}.pp.prenom_pere", "Prénom du père", "Fiche signalétique"),
    _f("{p}.nom", "Nom de famille", "Fiche signalétique"),
    _f("{p}.pp.date_naissance", "Date de naissance", "Fiche signalétique"),
    _f("{p}.pp.lieu_naissance", "Lieu de naissance", "Fiche signalétique"),
    _f("{p}.adresse", "Adresse de résidence", "Fiche signalétique"),
    _f("{p}.pays_residence", "Pays de résidence", "Fiche signalétique"),
    _f("{p}.piece.type", "Type de pièce d'identité", "Pièce d'identité"),
    _f("{p}.piece.numero", "Numéro PI", "Pièce d'identité"),
    _f("{p}.piece.date_delivrance", "Date délivrance", "Pièce d'identité"),
    _f("{p}.piece.date_expiration", "Date expiration", "Pièce d'identité"),
    _f("{p}.nationalite", "Nationalité", "Pièce d'identité"),
]
_CONTACTS = [
    _f("{p}.telephone_1", "Téléphone (1)", "Coordonnées"),
    _f("{p}.telephone_2", "Téléphone (2)", "Coordonnées", obligatoire=False),
    _f("{p}.telephone_3", "Téléphone (3)", "Coordonnées", obligatoire=False),
    _f("{p}.email", "Email", "Coordonnées"),
]
_FONDS = [
    _f("dossier.tranche_mouvement", "Estimation des mouvements mensuels", "Mouvements"),
    _f("dossier.origine_fonds", "Origine des fonds", "Mouvements"),
    _f("dossier.destination_fonds", "Destination des fonds", "Mouvements"),
]
_CADRE_PPE_FATCA = [
    _f("client.ppe", "Statut PPE", "Cadre réservé à la banque"),
    _f("client.ppe_motif", "Motif PPE", "Cadre réservé à la banque",
       condition={"fact": "client_ppe", "op": "eq", "value": True}),
    _f("client.fatca_indice", "Indice d'américanité (client ou mandataire)", "Cadre réservé à la banque"),
]
_CADRE_RISQUE = [
    _f("dossier.risque_lbcft", "Segmentation LBC FT", "Cadre réservé à la banque"),
    _f("dossier.commentaire_profil", "Commentaire sur le profil du client", "Cadre réservé à la banque"),
]
_SIGNALETIQUE_PM = [
    _f("client.pm.date_creation", "Date création", "Fiche signalétique"),
    _f("client.pm.activites", "Activités principales", "Fiche signalétique"),
    _f("client.adresse", "Adresse siège social", "Fiche signalétique"),
    _f("client.pm.effectif", "Effectif", "Fiche signalétique"),
    _f("client.email", "E-mail", "Fiche signalétique"),
    _f("client.pm.site_web", "Site web", "Fiche signalétique", obligatoire=False),
]
_RC_FISCAL = [
    _f("client.pm.rc_chronologique", "Numéro RC chronologique", "Fiche signalétique"),
    _f("client.pm.rc_analytique", "Numéro RC analytique", "Fiche signalétique"),
    _f("client.pm.nif", "NIF", "Fiche signalétique"),
    _f("client.pm.residence_fiscale", "Pays de résidence fiscale", "Fiche signalétique"),
]


def _pp(champs: list[dict[str, Any]], prefixe: str) -> list[dict[str, Any]]:
    return [{**c, "chemin": c["chemin"].format(p=prefixe)} for c in champs]


FICHES: dict[str, dict[str, Any]] = {
    "FICHE_PP": {
        "titre": "Fiche client personne physique",
        "type_client": TypeClient.PP,
        "champs": [
            *_ENTETE,
            _f("dossier.numero_idp", "Numéro IDP", "Motif de la fiche client"),
            *_pp(_IDENTITE_PP, "client"),
            _f("client.pp.situation_matrimoniale", "Situation matrimoniale", "Fiche signalétique"),
            _f("client.pp.profession", "Profession", "Profession"),
            _f("client.pp.employeur", "Employeur", "Profession"),
            _f("client.pp.salaire_net", "Salaire net", "Profession"),
            _f("client.pp.date_embauche", "Date embauche", "Profession"),
            _f("client.pp.type_contrat", "Type de contrat", "Profession"),
            *_pp(_CONTACTS, "client"),
            *_FONDS, *_CADRE_PPE_FATCA, *_CADRE_RISQUE,
        ],
    },
    "FICHE_PM_PRIVEE": {
        "titre": "Fiche client personne morale privée",
        "type_client": TypeClient.PM_PRIVEE,
        "champs": [
            *_ENTETE,
            _f("dossier.numero_idm", "Numéro IDM", "Motif de la fiche client"),
            _f("client.nom", "Raison sociale", "Fiche signalétique"),
            *_SIGNALETIQUE_PM, *_RC_FISCAL,
            _f("client.pm.impact_rse", "Impact RSE", "Fiche signalétique"),
            _f("client.pm.domaines_rse", "Domaines RSE", "Fiche signalétique",
               condition={"fact": "impact_rse", "op": "eq", "value": True}),
            *_FONDS, *_CADRE_PPE_FATCA, *_CADRE_RISQUE,
        ],
    },
    "FICHE_PM_PUBLIQUE": {
        "titre": "Fiche client personne morale publique",
        "type_client": TypeClient.PM_PUBLIQUE,
        "champs": [
            *_ENTETE,
            _f("dossier.numero_idp", "Numéro IDP", "Motif de la fiche client"),
            _f("client.nom", "Nom de l'entité", "Fiche signalétique"),
            *_SIGNALETIQUE_PM, *_RC_FISCAL,
            *_FONDS, *_CADRE_RISQUE,
        ],
    },
    "FICHE_ASSOCIATION": {
        "titre": "Fiche client personne morale associations",
        "type_client": TypeClient.ASSOCIATION,
        "champs": [
            *_ENTETE,
            _f("dossier.numero_idm", "Numéro IDM", "Motif de la fiche client"),
            _f("client.nom", "Nom de l'association", "Fiche signalétique"),
            *_SIGNALETIQUE_PM,
            _f("client.pm.numero_agrement", "Numéro d'agrément", "Fiche signalétique"),
            _f("client.pm.nif", "NIF", "Fiche signalétique"),
            *_FONDS, *_CADRE_PPE_FATCA, *_CADRE_RISQUE,
        ],
    },
    "FICHE_MANDATAIRE": {
        "titre": "Fiche client mandataire",
        "role": RoleDossier.MANDATAIRE,
        "champs": [
            _f("role.forme_mandat", "Forme du mandat", "Information mandataire"),
            _f("role.lien_client", "Lien entre le client et le mandataire", "Information mandataire"),
            *_pp(_IDENTITE_PP, "partie"),
            _f("partie.pp.profession", "Profession", "Fiche signalétique"),
            _f("partie.pp.employeur", "Employeur", "Fiche signalétique"),
            _f("role.comptes_mandat", "Liste des autres comptes avec mandat en cours", "Fiche signalétique",
               obligatoire=False),
            *_pp(_CONTACTS, "partie"),
            _f("role.ppe", "Statut PPE", "Cadre réservé à la banque"),
            _f("role.ppe_motif", "Motif PPE", "Cadre réservé à la banque",
               condition={"fact": "partie.ppe", "op": "eq", "value": True}),
            _f("role.fatca_indice", "Indice d'américanité du mandataire", "Cadre réservé à la banque"),
            _f("role.risque_lbcft", "Segmentation LBC FT", "Cadre réservé à la banque"),
            _f("role.gestionnaire_id", "Gestionnaire du compte", "Cadre réservé à la banque"),
            _f("role.responsable_agence_id", "Responsable d'agence", "Cadre réservé à la banque"),
        ],
    },
    "SPECIMEN_SIGNATURE": {
        "titre": "Spécimen de signature",
        "champs": [
            _f("dossier.numero_compte", "Numéro de compte", "Compte",
               condition={"fact": "compte_ouvert", "op": "eq", "value": True}),
            _f("dossier.date_ouverture_compte", "Date ouverture du compte", "Compte",
               condition={"fact": "compte_ouvert", "op": "eq", "value": True}),
            _f("dossier.nombre_signataires", "Nombre total de signataires", "Signature"),
            _f("dossier.type_signature", "Type de signature", "Signature"),
        ],
    },
}


# Élément de checklist → (fiche, champs de cette fiche qui le portent) pour la colonne
# « Donnée connue ». CLIENT = fiche du type de client, MANDATAIRE = fiche de la partie.
# Absent = l'élément ne dépend d'aucun champ de fiche (contrôle, avis, calcul BE…).
CHAMPS_PAR_REGLE: dict[str, tuple[str, tuple[str, ...]]] = {
    "FICHE_CLIENT": ("CLIENT", ("*",)),
    "INFOS_CLIENT": ("CLIENT", ("*",)),
    "PIECE_IDENTITE": ("CLIENT", ("client.piece.type", "client.piece.numero")),
    "PIECE_VALIDITE": ("CLIENT", ("client.piece.date_expiration",)),
    "SPECIMEN_SIGNATURE": ("SPECIMEN_SIGNATURE", ("*",)),
    "MOUVEMENTS": ("CLIENT", ("dossier.tranche_mouvement",)),
    "ORIGINE_FONDS": ("CLIENT", ("dossier.origine_fonds",)),
    "DESTINATION_FONDS": ("CLIENT", ("dossier.destination_fonds",)),
    "PPE_STATUT": ("CLIENT", ("client.ppe",)),
    "PPE_MOTIF": ("CLIENT", ("client.ppe_motif",)),
    "FATCA_STATUT": ("CLIENT", ("client.fatca_indice",)),
    "LBCFT_RISQUE": ("CLIENT", ("dossier.risque_lbcft",)),
    "RSE_DOMAINES": ("CLIENT", ("client.pm.domaines_rse",)),
    "MANDATAIRE_FICHE": ("MANDATAIRE", ("*",)),
    "MANDATAIRE_PIECE": ("MANDATAIRE", ("partie.piece.type", "partie.piece.numero")),
    "MANDATAIRE_VALIDITE": ("MANDATAIRE", ("partie.piece.date_expiration",)),
    "MANDATAIRE_PPE_FATCA_RISQUE": ("MANDATAIRE", ("role.ppe", "role.fatca_indice", "role.risque_lbcft")),
}


def _regle(code: str, libelle: str, categorie: str, axe: Axe, nature: NatureElement, *,
           condition: dict | None = None, portee: str = "DOSSIER", role_cible: RoleDossier | None = None,
           obligatoire: bool = True, ordre: int = 0, type_controle: TypeControle = TypeControle.MANUEL,
           document_type: str | None = None) -> dict[str, Any]:
    return {
        "code": code, "libelle": libelle, "categorie": categorie, "axe": axe, "nature": nature,
        "condition": condition, "portee": portee, "role_cible": role_cible, "obligatoire": obligatoire,
        "ordre": ordre, "type_controle": type_controle, "document_type": document_type,
    }


_PM = {"fact": "type_client", "op": "in", "value": [TypeClient.PM_PRIVEE, TypeClient.PM_PUBLIQUE]}
_AVEC_PPE_FATCA = {"fact": "type_client", "op": "in",
                   "value": [TypeClient.PP, TypeClient.PM_PRIVEE, TypeClient.ASSOCIATION]}

REGLES_CHECKLIST_INITIALES: list[dict[str, Any]] = [
    _regle("FICHE_CLIENT", "Fiche client renseignée et signée", "IDENTITE", Axe.PHYSIQUE,
           NatureElement.DOCUMENT, ordre=10, type_controle=TypeControle.AUTO_PRESENCE, document_type="FICHE_CLIENT"),
    _regle("PIECE_IDENTITE", "Pièce d'identité du client", "IDENTITE", Axe.PHYSIQUE, NatureElement.DOCUMENT,
           condition={"fact": "type_client", "op": "eq", "value": TypeClient.PP}, ordre=20,
           type_controle=TypeControle.AUTO_PRESENCE, document_type="PIECE_IDENTITE"),
    _regle("PIECE_VALIDITE", "Validité de la pièce d'identité", "IDENTITE", Axe.PHYSIQUE, NatureElement.CONTROLE,
           condition={"fact": "type_client", "op": "eq", "value": TypeClient.PP}, ordre=21,
           type_controle=TypeControle.AUTO_EXPIRATION),
    _regle("COHERENCE_IDENTITE", "Cohérence fiche ↔ pièce ↔ système", "IDENTITE", Axe.COHERENCE,
           NatureElement.CONTROLE, ordre=22, type_controle=TypeControle.AUTO_COHERENCE),
    _regle("SPECIMEN_SIGNATURE", "Spécimen de signature", "SIGNATURES", Axe.PHYSIQUE, NatureElement.DOCUMENT,
           ordre=30, type_controle=TypeControle.AUTO_PRESENCE, document_type="SPECIMEN_SIGNATURE"),
    _regle("CONTACT_URGENCE", "Contact en cas d'urgence", "IDENTITE", Axe.PHYSIQUE, NatureElement.INFORMATION,
           condition={"fact": "type_client", "op": "eq", "value": TypeClient.PP}, ordre=40),
    _regle("INFOS_CLIENT", "Informations client complètes (fiche)", "KYC", Axe.SYSTEME,
           NatureElement.INFORMATION, ordre=50, type_controle=TypeControle.AUTO_PRESENCE),
    _regle("MOUVEMENTS", "Estimation des mouvements renseignée", "KYC", Axe.SYSTEME, NatureElement.INFORMATION,
           ordre=60),
    _regle("ORIGINE_FONDS", "Origine des fonds", "LBC_FT", Axe.SYSTEME, NatureElement.INFORMATION, ordre=61),
    _regle("DESTINATION_FONDS", "Destination des fonds", "LBC_FT", Axe.SYSTEME, NatureElement.INFORMATION,
           ordre=62),
    _regle("PPE_STATUT", "Statut PPE renseigné", "PPE", Axe.SYSTEME, NatureElement.INFORMATION,
           condition=_AVEC_PPE_FATCA, ordre=70),
    _regle("PPE_MOTIF", "Motif PPE du client", "PPE", Axe.SYSTEME, NatureElement.INFORMATION,
           condition={"fact": "client_ppe", "op": "eq", "value": True}, ordre=71),
    _regle("PPE_CONTROLE_RENFORCE", "Contrôle renforcé PPE", "PPE", Axe.PHYSIQUE, NatureElement.CONTROLE,
           condition={"fact": "ppe", "op": "eq", "value": True}, ordre=72),
    _regle("FATCA_STATUT", "Indice d'américanité renseigné (client ou mandataire)", "FATCA", Axe.SYSTEME,
           NatureElement.INFORMATION, condition=_AVEC_PPE_FATCA, ordre=80),
    _regle("FATCA_REVUE_KYC", "Revue du Service Conformité KYC (indice d'américanité)", "FATCA", Axe.PHYSIQUE,
           NatureElement.CONTROLE, condition={"fact": "fatca_indice", "op": "eq", "value": True}, ordre=81),
    _regle("LBCFT_RISQUE", "Risque LBC-FT évalué et justifié", "LBC_FT", Axe.SYSTEME, NatureElement.INFORMATION,
           ordre=90),
    _regle("DIRECTION", "Gérant / signataire et membres de direction identifiés", "DIRECTION", Axe.PHYSIQUE,
           NatureElement.INFORMATION,
           condition={"fact": "type_client", "op": "ne", "value": TypeClient.PP}, ordre=100),
    _regle("RSE_DOMAINES", "Domaines RSE précisés", "KYC", Axe.SYSTEME, NatureElement.INFORMATION,
           condition={"fact": "impact_rse", "op": "eq", "value": True}, ordre=101),
    _regle("ACTIONNARIAT", "Structure d'actionnariat complète", "ACTIONNARIAT", Axe.PHYSIQUE,
           NatureElement.INFORMATION, condition=_PM, ordre=110, type_controle=TypeControle.AUTO_CALCUL),
    _regle("BE_IDENTIFIES", "Bénéficiaires effectifs identifiés (≥ seuil)", "BE", Axe.PHYSIQUE,
           NatureElement.CONTROLE, condition=_PM, ordre=111, type_controle=TypeControle.AUTO_CALCUL),
    _regle("BE_PIECE", "Pièce d'identité du bénéficiaire effectif", "BE", Axe.PHYSIQUE, NatureElement.DOCUMENT,
           portee="PARTIE", role_cible=RoleDossier.BENEFICIAIRE_EFFECTIF, ordre=112,
           type_controle=TypeControle.AUTO_PRESENCE, document_type="PIECE_IDENTITE"),
    _regle("MANDATAIRE_FICHE", "Fiche client mandataire", "MANDATAIRES", Axe.PHYSIQUE, NatureElement.DOCUMENT,
           portee="PARTIE", role_cible=RoleDossier.MANDATAIRE, ordre=120,
           type_controle=TypeControle.AUTO_PRESENCE, document_type="FICHE_MANDATAIRE"),
    _regle("MANDATAIRE_PIECE", "Pièce d'identité du mandataire", "MANDATAIRES", Axe.PHYSIQUE,
           NatureElement.DOCUMENT, portee="PARTIE", role_cible=RoleDossier.MANDATAIRE, ordre=121,
           type_controle=TypeControle.AUTO_PRESENCE, document_type="PIECE_IDENTITE"),
    _regle("MANDATAIRE_VALIDITE", "Validité de la pièce du mandataire", "MANDATAIRES", Axe.PHYSIQUE,
           NatureElement.CONTROLE, portee="PARTIE", role_cible=RoleDossier.MANDATAIRE, ordre=122,
           type_controle=TypeControle.AUTO_EXPIRATION),
    _regle("MANDAT_DOCUMENT", "Mandat / procuration", "MANDATAIRES", Axe.PHYSIQUE, NatureElement.DOCUMENT,
           portee="PARTIE", role_cible=RoleDossier.MANDATAIRE, ordre=123,
           type_controle=TypeControle.AUTO_PRESENCE, document_type="MANDAT"),
    _regle("MANDATAIRE_PPE_FATCA_RISQUE", "PPE, FATCA et risque du mandataire", "MANDATAIRES", Axe.SYSTEME,
           NatureElement.INFORMATION, portee="PARTIE", role_cible=RoleDossier.MANDATAIRE, ordre=124),
    _regle("MANDATAIRE_AVIS", "Avis du Service Conformité KYC sur le mandataire", "MANDATAIRES", Axe.PHYSIQUE,
           NatureElement.AVIS, portee="PARTIE", role_cible=RoleDossier.MANDATAIRE, ordre=125),
    _regle("VISAS_BANQUE", "Tableau des signataires (visas internes)", "AVIS", Axe.PHYSIQUE, NatureElement.AVIS,
           ordre=200),
    _regle("AVIS_KYC", "Avis du Service Conformité KYC", "AVIS", Axe.PHYSIQUE, NatureElement.AVIS,
           condition={"fact": "avis_kyc_requis", "op": "eq", "value": True}, ordre=210),
]
