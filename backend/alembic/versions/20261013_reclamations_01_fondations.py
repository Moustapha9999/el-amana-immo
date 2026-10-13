"""Réclamations — fondations : tables reclamation_*, référentiels initiaux, module ``reclamations``.

Additif : aucune table existante modifiée, hormis l'activation du domaine « Management &
Qualité » (département Audit, Contrôle & Conformité) qui accueille le module.

Référentiels insérés si absents, jamais réécrits (l'écran Paramètres reste ensuite la source
de vérité) :
- canaux de réception (dont Téléphone / Centre d'appel) et canaux d'envoi de la réponse ;
- types de réclamation = propositions initiales, à valider par la banque ;
- unités : liste des entités BEA déjà utilisée par le module Formation (agences, services du
  siège et leur département / direction) + l'unité centrale « Service Réclamations ».
Aucune règle de délai : elles sont saisies puis validées par la Conformité.

Revision ID: 20261013_reclamations_01
Revises: 20261013_clientele_10
"""

import re
import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261013_reclamations_01"
down_revision: Union[str, None] = "20261013_clientele_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ESPACE_CODE = "audit-controle-conformite"
DOMAINE_CODE = "management-qualite"
MODULE_CODE = "reclamations"

CANAUX = [
    ("PAPIER", "Papier (agence / siège)"),
    ("COURRIER", "Courrier postal"),
    ("EMAIL", "E-mail"),
    ("DIGITAL", "Canal digital"),
    ("BOITE_LETTRES", "Boîte à lettres"),
    ("AMANTY_WALLET", "Amanty Wallet"),
    ("TELEPHONE", "Téléphone / Centre d'appel"),
]
CANAUX_REPONSE = [
    ("COURRIER", "Courrier postal"),
    ("EMAIL", "E-mail"),
    ("REMISE_MAIN", "Remise en main propre"),
    ("TELEPHONE", "Appel téléphonique"),
    ("SMS", "SMS"),
    ("DIGITAL", "Canal digital / Amanty Wallet"),
]
TYPES = [
    "Opérations et virements",
    "Compte bancaire",
    "Carte bancaire",
    "Frais et commissions",
    "Crédit et remboursement",
    "Accueil et qualité de service",
    "Amanty Wallet",
    "Banque digitale et moyens de paiement",
    "Autres motifs",
]
TYPE_DESCRIPTION = "Proposition initiale — nomenclature à valider par la banque."

NKC = "Nouakchott"
# (entité, département / direction de rattachement) — liste « List entité » du module Formation.
ENTITES = [
    ("AGENCE CENTRALE PARTICULIERS", "DIRECTION COMMERCIALE"),
    ("AGENCE CENTRALE ENTREPRISES", "DIRECTION COMMERCIALE"),
    ("AGENCE ROUTE NDB", "DIRECTION COMMERCIALE"),
    ("AGENCE TEVRAGH ZEINA", "DIRECTION COMMERCIALE"),
    ("AGENCE MARCHE ETHMAN IBN AFFAN", "DIRECTION COMMERCIALE"),
    ("AGENCE KSAR", "DIRECTION COMMERCIALE"),
    ("AGENCE MOCTAR DADDAH", "DIRECTION COMMERCIALE"),
    ("AGENCE SEBKHA", "DIRECTION COMMERCIALE"),
    ("AGENCE NOUADHIBOU", "DIRECTION COMMERCIALE"),
    ("AGENCE CHAMI", "DIRECTION COMMERCIALE"),
    ("AGENCE ROSSO", "DIRECTION COMMERCIALE"),
    ("AGENCE MBERRA", "DIRECTION COMMERCIALE"),
    ("AGENCE TINTANE", "DIRECTION COMMERCIALE"),
    ("AGENCE KIFFA", "DIRECTION COMMERCIALE"),
    ("AGENCE GUEROU", "DIRECTION COMMERCIALE"),
    ("AGENCE ZOUERATE", "DIRECTION COMMERCIALE"),
    ("DIRECTION COMMERCIALE", "DIRECTION COMMERCIALE"),
    ("VIREMENTS", "Département Domestique"),
    ("COMPENSES", "Département Domestique"),
    ("CREDITS", "BO ENGAGEMENT"),
    ("MONETIQUES", "BO PRODUITS & SERVICES"),
    ("CHEQUIERS", "BO PRODUITS & SERVICES"),
    ("OPERATIONS INTERNATIONALES", "Département International"),
    ("SALLE DE MARCHE", "SALLE DE MARCHE"),
    ("MARKETING ET COMMUNICATION", "MARKETING & COMMUNICATION"),
    ("COMPTABILITE", "COMPTABILITE"),
    ("AMANTY", "AMANTY"),
    ("DSI", "DSI"),
    ("RESSOURCES HUMAINES", "RESSOURCES HUMAINES"),
    ("ARCHIVES", "MOYENS GENERAUX"),
    ("CASH PAYMENT", "CASH PAYMENT"),
    ("RISQUES", "RISQUES"),
    ("GARANTIES", "RISQUES"),
    ("CONFORMITE", "CONFORMITE"),
    ("CONTRÔLE PERMANENT", "CONTRÔLE PERMANENT"),
    ("ORGANISATION", "ORGANISATION"),
    ("CONTRÔLE PERIODIQUE", "AUDIT INTERNE"),
    ("CONTRÔLE DE GESTION", "CONTRÔLE DE GESTION"),
]
SERVICE_RECLAMATIONS = "SERVICE RÉCLAMATIONS"

STATUTS = ("RECUE", "RECUE_SR", "A_QUALIFIER", "AFFECTEE", "EN_TRAITEMENT", "ATTENTE_INFO", "RETOUR_RECU",
           "REPONSE_A_PREPARER", "REPONSE_ENVOYEE", "SUSPENDUE", "REFUSEE", "CLOTUREE", "REOUVERTE", "ANNULEE")
ETAPES = ("RECEPTION", "QUALIFICATION", "AFFECTATION", "TRAITEMENT", "RETOUR", "REPONSE", "CLOTURE")
PRIORITES = ("BASSE", "NORMALE", "HAUTE", "URGENTE")
RESULTATS = ("FAVORABLE", "PARTIELLEMENT_FAVORABLE", "DEFAVORABLE", "SANS_SUITE", "AUTRE")
CATEGORIES_DOCUMENT = ("ORIGINAL", "PIECE_CLIENT", "TRANSMISSION", "FICHE_TRAITEMENT", "JUSTIFICATIF_SERVICE",
                       "RETOUR_SERVICE", "REPONSE_CLIENT", "PREUVE_ENVOI", "AUTRE")

TABLES = (
    "reclamation_evenements", "reclamation_appels", "reclamation_documents", "reclamation_reponses",
    "reclamation_affectations", "reclamations", "reclamation_regles_delai", "reclamation_unite_membres",
    "reclamation_unites", "reclamation_referentiels", "reclamation_jours_feries", "reclamation_parametres",
    "reclamation_compteurs",
)


def _cle(texte: str) -> str:
    s = unicodedata.normalize("NFKD", texte or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _in(colonne: str, valeurs: tuple[str, ...], nullable: bool = False) -> str:
    liste = ",".join(f"'{v}'" for v in valeurs)
    return f"{colonne} IS NULL OR {colonne} IN ({liste})" if nullable else f"{colonne} IN ({liste})"


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def _user(nom: str) -> sa.Column:
    return sa.Column(nom, sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _date(nom: str) -> sa.Column:
    return sa.Column(nom, sa.DateTime(timezone=True), nullable=True)


def _ref(nom: str, nullable: bool = True) -> sa.Column:
    return sa.Column(nom, sa.UUID(), sa.ForeignKey("reclamation_referentiels.id", ondelete="RESTRICT"),
                     nullable=nullable)


def _unite(nom: str, nullable: bool = True, ondelete: str = "RESTRICT") -> sa.Column:
    return sa.Column(nom, sa.UUID(), sa.ForeignKey("reclamation_unites.id", ondelete=ondelete), nullable=nullable)


def _index(table: str, *colonnes: str) -> None:
    for col in colonnes:
        op.create_index(f"ix_{table}_{col}", table, [col])


def upgrade() -> None:
    bind = op.get_bind()
    has = sa.inspect(bind).has_table

    if not has("reclamation_referentiels"):
        op.create_table(
            "reclamation_referentiels",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("domaine", sa.String(20), nullable=False),
            sa.Column("code", sa.String(40), nullable=True),
            sa.Column("libelle", sa.String(200), nullable=False),
            sa.Column("cle", sa.String(200), nullable=False),
            sa.Column("parent_id", sa.UUID(), sa.ForeignKey("reclamation_referentiels.id", ondelete="RESTRICT"),
                      nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
            _user("created_by_id"),
            _user("updated_by_id"),
            *_ts(),
            sa.CheckConstraint(_in("domaine", ("TYPE", "MOTIF", "SOUS_MOTIF", "CANAL", "CANAL_REPONSE")),
                               name="ck_reclamation_referentiels_domaine"),
        )
        _index("reclamation_referentiels", "domaine", "parent_id")
        op.execute(
            "CREATE UNIQUE INDEX uq_reclamation_referentiels_cle ON reclamation_referentiels "
            "(domaine, COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), cle)"
        )
        op.execute(
            "CREATE UNIQUE INDEX uq_reclamation_referentiels_code ON reclamation_referentiels (domaine, code) "
            "WHERE code IS NOT NULL"
        )

    if not has("reclamation_unites"):
        op.create_table(
            "reclamation_unites",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("type_unite", sa.String(20), nullable=False),
            sa.Column("code", sa.String(40), nullable=True),
            sa.Column("libelle", sa.String(200), nullable=False),
            sa.Column("cle", sa.String(200), nullable=False, unique=True),
            sa.Column("parent_id", sa.UUID(), sa.ForeignKey("reclamation_unites.id", ondelete="RESTRICT"),
                      nullable=True),
            sa.Column("agence_id", sa.UUID(), sa.ForeignKey("agences.id", ondelete="SET NULL"), nullable=True),
            sa.Column("est_service_reclamations", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
            _user("created_by_id"),
            _user("updated_by_id"),
            *_ts(),
            sa.CheckConstraint(_in("type_unite", ("DIRECTION", "DEPARTEMENT", "SERVICE", "AGENCE", "CELLULE")),
                               name="ck_reclamation_unites_type"),
            sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_reclamation_unites_parent"),
        )
        _index("reclamation_unites", "type_unite", "parent_id", "agence_id")
        op.execute(
            "CREATE UNIQUE INDEX uq_reclamation_unites_service_central ON reclamation_unites "
            "(est_service_reclamations) WHERE est_service_reclamations AND actif"
        )

    if not has("reclamation_unite_membres"):
        op.create_table(
            "reclamation_unite_membres",
            sa.Column("id", sa.UUID(), primary_key=True),
            _unite("unite_id", nullable=False, ondelete="CASCADE"),
            sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role_membre", sa.String(20), nullable=False, server_default="AGENT"),
            sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
            _user("created_by_id"),
            _user("updated_by_id"),
            *_ts(),
            sa.UniqueConstraint("unite_id", "user_id", name="uq_reclamation_unite_membres_unite_user"),
            sa.CheckConstraint(_in("role_membre", ("RESPONSABLE", "AGENT")), name="ck_reclamation_unite_membres_role"),
        )
        _index("reclamation_unite_membres", "unite_id", "user_id")

    if not has("reclamation_regles_delai"):
        op.create_table(
            "reclamation_regles_delai",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("libelle", sa.String(200), nullable=False),
            _ref("type_id"),
            _ref("motif_id"),
            sa.Column("priorite", sa.String(10), nullable=True),
            sa.Column("duree", sa.Integer(), nullable=False),
            sa.Column("unite_duree", sa.String(20), nullable=False, server_default="JOURS_CALENDAIRES"),
            sa.Column("point_depart", sa.String(30), nullable=False, server_default="PREMIERE_RECEPTION"),
            sa.Column("seuil_alerte", sa.Integer(), nullable=True),
            sa.Column("delai_service", sa.Integer(), nullable=True),
            sa.Column("neutraliser_suspension", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("destinataires", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("date_effet", sa.Date(), nullable=False),
            sa.Column("date_fin", sa.Date(), nullable=True),
            sa.Column("statut_validation", sa.String(20), nullable=False, server_default="A_VALIDER"),
            _user("valide_par_id"),
            _date("valide_le"),
            sa.Column("commentaire", sa.Text(), nullable=True),
            sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
            _user("created_by_id"),
            _user("updated_by_id"),
            *_ts(),
            sa.CheckConstraint("duree > 0", name="ck_reclamation_regles_delai_duree"),
            sa.CheckConstraint("seuil_alerte IS NULL OR seuil_alerte >= 0", name="ck_reclamation_regles_delai_seuil"),
            sa.CheckConstraint("delai_service IS NULL OR delai_service > 0", name="ck_reclamation_regles_delai_service"),
            sa.CheckConstraint("date_fin IS NULL OR date_fin >= date_effet", name="ck_reclamation_regles_delai_periode"),
            sa.CheckConstraint(_in("unite_duree", ("JOURS_CALENDAIRES", "JOURS_OUVRES")),
                               name="ck_reclamation_regles_delai_unite"),
            sa.CheckConstraint(_in("point_depart", ("PREMIERE_RECEPTION", "RECEPTION_SR")),
                               name="ck_reclamation_regles_delai_depart"),
            sa.CheckConstraint(_in("priorite", PRIORITES, nullable=True), name="ck_reclamation_regles_delai_priorite"),
            sa.CheckConstraint(_in("statut_validation", ("A_VALIDER", "VALIDEE", "REJETEE")),
                               name="ck_reclamation_regles_delai_validation"),
        )
        _index("reclamation_regles_delai", "type_id", "motif_id")

    if not has("reclamations"):
        op.create_table(
            "reclamations",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("reference", sa.String(30), nullable=False, unique=True),
            sa.Column("annee", sa.Integer(), nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("objet", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            _ref("type_id"),
            _ref("motif_id"),
            _ref("sous_motif_id"),
            sa.Column("priorite", sa.String(10), nullable=False, server_default="NORMALE"),
            sa.Column("statut", sa.String(30), nullable=False),
            sa.Column("etape", sa.String(20), nullable=False),
            sa.Column("source", sa.String(20), nullable=False, server_default="MANUEL"),
            _ref("canal_id", nullable=False),
            _unite("unite_reception_id"),
            sa.Column("client_racine", sa.String(6), nullable=True),
            sa.Column("client_categorie", sa.String(12), nullable=True),
            sa.Column("client_nom", sa.String(255), nullable=True),
            sa.Column("client_telephone", sa.String(40), nullable=True),
            sa.Column("client_email", sa.String(255), nullable=True),
            sa.Column("client_adresse", sa.Text(), nullable=True),
            sa.Column("client_agence_id", sa.UUID(), sa.ForeignKey("agences.id", ondelete="SET NULL"), nullable=True),
            sa.Column("compte_reference", sa.String(60), nullable=True),
            sa.Column("carte_masquee", sa.String(25), nullable=True),
            sa.Column("operation_reference", sa.String(120), nullable=True),
            sa.Column("operation_date", sa.Date(), nullable=True),
            sa.Column("montant_conteste", sa.Numeric(18, 2), nullable=True),
            sa.Column("devise", sa.String(3), nullable=True),
            sa.Column("reclamation_liee_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("doublon_de_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("date_premiere_reception", sa.DateTime(timezone=True), nullable=False),
            _date("date_reception_sr"),
            _date("date_qualification"),
            _date("date_transmission"),
            _date("date_reception_service"),
            _date("date_retour_service"),
            _date("date_reponse_client"),
            _date("date_cloture"),
            _date("date_suspension"),
            _date("date_reouverture"),
            _unite("unite_suivi_id"),
            _user("gestionnaire_id"),
            _unite("unite_traitement_id"),
            _user("responsable_traitement_id"),
            sa.Column("affectation_courante_id", sa.UUID(), nullable=True),
            sa.Column("regle_delai_id", sa.UUID(),
                      sa.ForeignKey("reclamation_regles_delai.id", ondelete="SET NULL"), nullable=True),
            _date("echeance"),
            _date("echeance_initiale"),
            sa.Column("statut_avant_suspension", sa.String(30), nullable=True),
            sa.Column("motif_suspension", sa.Text(), nullable=True),
            sa.Column("conditions_reprise", sa.Text(), nullable=True),
            sa.Column("motif_refus", sa.Text(), nullable=True),
            sa.Column("motif_annulation", sa.Text(), nullable=True),
            sa.Column("resultat", sa.String(30), nullable=True),
            sa.Column("motif_resolution", sa.Text(), nullable=True),
            _user("cloture_par_id"),
            sa.Column("nb_reouvertures", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("nb_renvois", sa.Integer(), nullable=False, server_default="0"),
            _date("archivee_le"),
            _user("archivee_par_id"),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            _user("created_by_id"),
            _user("updated_by_id"),
            *_ts(),
            sa.CheckConstraint(_in("statut", STATUTS), name="ck_reclamations_statut"),
            sa.CheckConstraint(_in("etape", ETAPES), name="ck_reclamations_etape"),
            sa.CheckConstraint(_in("priorite", PRIORITES), name="ck_reclamations_priorite"),
            sa.CheckConstraint(_in("statut_avant_suspension", STATUTS, nullable=True),
                               name="ck_reclamations_statut_avant_suspension"),
            sa.CheckConstraint(_in("client_categorie", ("PP", "PM", "NON_CLIENT"), nullable=True),
                               name="ck_reclamations_client"),
            sa.CheckConstraint(_in("resultat", RESULTATS, nullable=True), name="ck_reclamations_resultat"),
            sa.CheckConstraint(_in("source", ("MANUEL", "CENTRE_APPEL", "IMPORT", "API")),
                               name="ck_reclamations_source"),
            sa.CheckConstraint("client_racine IS NULL OR client_racine ~ '^[0-9]{6}$'", name="ck_reclamations_racine"),
            sa.CheckConstraint("montant_conteste IS NULL OR montant_conteste >= 0", name="ck_reclamations_montant"),
            sa.CheckConstraint("date_reception_sr IS NULL OR date_reception_sr >= date_premiere_reception",
                               name="ck_reclamations_date_reception_sr"),
            sa.CheckConstraint("date_reponse_client IS NULL OR date_reponse_client >= date_premiere_reception",
                               name="ck_reclamations_date_reponse"),
            sa.CheckConstraint("date_cloture IS NULL OR date_cloture >= date_premiere_reception",
                               name="ck_reclamations_date_cloture"),
            sa.CheckConstraint("doublon_de_id IS NULL OR doublon_de_id <> id", name="ck_reclamations_doublon"),
            sa.CheckConstraint("reclamation_liee_id IS NULL OR reclamation_liee_id <> id",
                               name="ck_reclamations_liee"),
            sa.UniqueConstraint("annee", "numero", name="uq_reclamations_annee_numero"),
        )
        _index("reclamations", "type_id", "motif_id", "sous_motif_id", "priorite", "statut", "etape", "canal_id",
               "unite_reception_id", "client_racine", "client_agence_id", "reclamation_liee_id", "doublon_de_id",
               "date_premiere_reception", "date_cloture", "unite_suivi_id", "unite_traitement_id", "echeance")

    if not has("reclamation_affectations"):
        op.create_table(
            "reclamation_affectations",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("reclamation_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("parent_id", sa.UUID(), sa.ForeignKey("reclamation_affectations.id", ondelete="SET NULL"),
                      nullable=True),
            _unite("unite_emettrice_id"),
            _unite("unite_destinataire_id", nullable=False),
            sa.Column("statut", sa.String(20), nullable=False, server_default="TRANSMISE"),
            sa.Column("transmis_le", sa.DateTime(timezone=True), nullable=False),
            _user("transmis_par_id"),
            sa.Column("motif_transfert", sa.Text(), nullable=True),
            sa.Column("instructions", sa.Text(), nullable=True),
            _date("echeance_service"),
            _date("recu_le"),
            _user("recu_par_id"),
            _user("responsable_id"),
            sa.Column("analyse", sa.Text(), nullable=True),
            sa.Column("actions_menees", sa.Text(), nullable=True),
            sa.Column("conclusion", sa.Text(), nullable=True),
            sa.Column("decision_proposee", sa.String(30), nullable=True),
            _date("retour_le"),
            _user("retour_par_id"),
            sa.Column("evaluation", sa.String(20), nullable=True),
            sa.Column("evaluation_commentaire", sa.Text(), nullable=True),
            _date("evalue_le"),
            _user("evalue_par_id"),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            *_ts(),
            sa.UniqueConstraint("reclamation_id", "numero", name="uq_reclamation_affectations_numero"),
            sa.CheckConstraint(_in("statut", ("TRANSMISE", "RECUE", "EN_TRAITEMENT", "RETOURNEE", "ANNULEE")),
                               name="ck_reclamation_affectations_statut"),
            sa.CheckConstraint(_in("evaluation", ("SUFFISANT", "INSUFFISANT"), nullable=True),
                               name="ck_reclamation_affectations_evaluation"),
            sa.CheckConstraint(_in("decision_proposee", RESULTATS, nullable=True),
                               name="ck_reclamation_affectations_decision"),
            sa.CheckConstraint("recu_le IS NULL OR recu_le >= transmis_le", name="ck_reclamation_affectations_reception"),
            sa.CheckConstraint("retour_le IS NULL OR (recu_le IS NOT NULL AND retour_le >= recu_le)",
                               name="ck_reclamation_affectations_retour"),
        )
        _index("reclamation_affectations", "reclamation_id", "unite_destinataire_id", "unite_emettrice_id", "statut")
        op.create_foreign_key("fk_reclamations_affectation_courante", "reclamations", "reclamation_affectations",
                              ["affectation_courante_id"], ["id"], ondelete="SET NULL")

    if not has("reclamation_reponses"):
        op.create_table(
            "reclamation_reponses",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("reclamation_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("statut", sa.String(20), nullable=False, server_default="BROUILLON"),
            sa.Column("objet", sa.String(255), nullable=True),
            sa.Column("contenu", sa.Text(), nullable=False),
            sa.Column("resultat", sa.String(30), nullable=True),
            _ref("canal_envoi_id"),
            sa.Column("destinataire", sa.String(255), nullable=True),
            _user("redige_par_id"),
            _date("soumis_le"),
            _user("valide_par_id"),
            _date("valide_le"),
            sa.Column("commentaire_validation", sa.Text(), nullable=True),
            _date("envoye_le"),
            _user("envoye_par_id"),
            sa.Column("reference_envoi", sa.String(120), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            *_ts(),
            sa.UniqueConstraint("reclamation_id", "numero", name="uq_reclamation_reponses_numero"),
            sa.CheckConstraint(_in("statut", ("BROUILLON", "A_VALIDER", "VALIDEE", "ENVOYEE", "ANNULEE")),
                               name="ck_reclamation_reponses_statut"),
            sa.CheckConstraint(_in("resultat", RESULTATS, nullable=True), name="ck_reclamation_reponses_resultat"),
            sa.CheckConstraint("statut <> 'ENVOYEE' OR (envoye_le IS NOT NULL AND canal_envoi_id IS NOT NULL)",
                               name="ck_reclamation_reponses_envoi"),
        )
        _index("reclamation_reponses", "reclamation_id", "statut", "canal_envoi_id")

    if not has("reclamation_documents"):
        op.create_table(
            "reclamation_documents",
            sa.Column("document_id", sa.UUID(), sa.ForeignKey("ged_documents.id", ondelete="CASCADE"),
                      primary_key=True),
            sa.Column("reclamation_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("categorie", sa.String(30), nullable=False),
            sa.Column("affectation_id", sa.UUID(),
                      sa.ForeignKey("reclamation_affectations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reponse_id", sa.UUID(), sa.ForeignKey("reclamation_reponses.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("commentaire", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            _user("created_by_id"),
            sa.CheckConstraint(_in("categorie", CATEGORIES_DOCUMENT), name="ck_reclamation_documents_categorie"),
        )
        _index("reclamation_documents", "reclamation_id", "categorie")

    if not has("reclamation_appels"):
        op.create_table(
            "reclamation_appels",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("reclamation_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("appel_le", sa.DateTime(timezone=True), nullable=False),
            sa.Column("numero_appelant", sa.String(40), nullable=True),
            _user("agent_id"),
            sa.Column("identite_verifiee", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("mode_verification", sa.String(200), nullable=True),
            sa.Column("reference_appel", sa.String(120), nullable=True),
            sa.Column("enregistrement_autorise", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("reference_enregistrement", sa.String(200), nullable=True),
            sa.Column("rappel_statut", sa.String(20), nullable=False, server_default="AUCUN"),
            _date("rappel_prevu_le"),
            _date("rappel_effectue_le"),
            sa.Column("commentaire", sa.Text(), nullable=True),
            _user("created_by_id"),
            *_ts(),
            sa.CheckConstraint(_in("rappel_statut", ("AUCUN", "A_RAPPELER", "RAPPELE", "ECHEC")),
                               name="ck_reclamation_appels_rappel"),
            sa.CheckConstraint("reference_enregistrement IS NULL OR enregistrement_autorise",
                               name="ck_reclamation_appels_enregistrement"),
        )
        _index("reclamation_appels", "reclamation_id")

    if not has("reclamation_evenements"):
        op.create_table(
            "reclamation_evenements",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("reclamation_id", sa.UUID(), sa.ForeignKey("reclamations.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("type_evenement", sa.String(40), nullable=False),
            sa.Column("statut_avant", sa.String(30), nullable=True),
            sa.Column("statut_apres", sa.String(30), nullable=True),
            sa.Column("etape_avant", sa.String(20), nullable=True),
            sa.Column("etape_apres", sa.String(20), nullable=True),
            sa.Column("date_effet", sa.DateTime(timezone=True), nullable=False),
            sa.Column("enregistre_le", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            _user("auteur_id"),
            _unite("unite_id", ondelete="SET NULL"),
            sa.Column("affectation_id", sa.UUID(),
                      sa.ForeignKey("reclamation_affectations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reponse_id", sa.UUID(), sa.ForeignKey("reclamation_reponses.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("commentaire", sa.Text(), nullable=True),
            sa.Column("donnees", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
        _index("reclamation_evenements", "reclamation_id", "type_evenement", "enregistre_le")
        # Chronologie en ajout seul. Seule exception : la mise à NULL d'une référence par une clé
        # étrangère ON DELETE SET NULL (utilisateur, unité, fiche ou réponse supprimés).
        # Une restauration de sauvegarde (session_replication_role = replica) n'exécute pas ce trigger.
        op.execute(
            """
            CREATE OR REPLACE FUNCTION reclamation_evenements_immuable() RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'UPDATE' AND
                   (NEW.id, NEW.reclamation_id, NEW.type_evenement, NEW.statut_avant, NEW.statut_apres,
                    NEW.etape_avant, NEW.etape_apres, NEW.date_effet, NEW.enregistre_le, NEW.commentaire,
                    NEW.donnees)
                   IS NOT DISTINCT FROM
                   (OLD.id, OLD.reclamation_id, OLD.type_evenement, OLD.statut_avant, OLD.statut_apres,
                    OLD.etape_avant, OLD.etape_apres, OLD.date_effet, OLD.enregistre_le, OLD.commentaire,
                    OLD.donnees)
                   AND (NEW.auteur_id IS NOT DISTINCT FROM OLD.auteur_id OR NEW.auteur_id IS NULL)
                   AND (NEW.unite_id IS NOT DISTINCT FROM OLD.unite_id OR NEW.unite_id IS NULL)
                   AND (NEW.affectation_id IS NOT DISTINCT FROM OLD.affectation_id OR NEW.affectation_id IS NULL)
                   AND (NEW.reponse_id IS NOT DISTINCT FROM OLD.reponse_id OR NEW.reponse_id IS NULL) THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'reclamation_evenements : chronologie en ajout seul (% refusé)', TG_OP
                    USING ERRCODE = 'P0001';
            END
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            "CREATE TRIGGER trg_reclamation_evenements_immuable BEFORE UPDATE OR DELETE "
            "ON reclamation_evenements FOR EACH ROW EXECUTE FUNCTION reclamation_evenements_immuable()"
        )

    if not has("reclamation_jours_feries"):
        op.create_table(
            "reclamation_jours_feries",
            sa.Column("jour", sa.Date(), primary_key=True),
            sa.Column("libelle", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            _user("created_by_id"),
        )

    if not has("reclamation_parametres"):
        op.create_table(
            "reclamation_parametres",
            sa.Column("cle", sa.String(80), primary_key=True),
            sa.Column("valeur", postgresql.JSONB(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            _user("updated_by_id"),
        )

    if not has("reclamation_compteurs"):
        op.create_table(
            "reclamation_compteurs",
            sa.Column("annee", sa.Integer(), primary_key=True),
            sa.Column("dernier", sa.Integer(), nullable=False, server_default="0"),
        )

    _seed(bind)


def _seed(bind) -> None:
    ins_ref = sa.text(
        """
        INSERT INTO reclamation_referentiels (id, domaine, code, libelle, cle, description, ordre, actif)
        VALUES (gen_random_uuid(), :domaine, :code, :libelle, :cle, :description, :ordre, true)
        ON CONFLICT DO NOTHING
        """
    )
    for domaine, valeurs in (("CANAL", CANAUX), ("CANAL_REPONSE", CANAUX_REPONSE)):
        for i, (code, libelle) in enumerate(valeurs, start=1):
            bind.execute(ins_ref, {"domaine": domaine, "code": code, "libelle": libelle, "cle": _cle(libelle),
                                   "description": None, "ordre": i})
    for i, libelle in enumerate(TYPES, start=1):
        bind.execute(ins_ref, {"domaine": "TYPE", "code": None, "libelle": libelle, "cle": _cle(libelle),
                               "description": TYPE_DESCRIPTION, "ordre": i})

    ins_unite = sa.text(
        """
        INSERT INTO reclamation_unites (id, type_unite, libelle, cle, parent_id, agence_id, ordre, actif)
        VALUES (gen_random_uuid(), :type_unite, :libelle, :cle,
                (SELECT p.id FROM reclamation_unites p WHERE p.cle = :parent),
                (SELECT a.id FROM agences a WHERE upper(a.libelle) = upper(:libelle)
                   AND a.deleted_at IS NULL LIMIT 1),
                :ordre, true)
        ON CONFLICT (cle) DO NOTHING
        """
    )
    parents: list[str] = []
    for _entite, parent in ENTITES:
        if parent not in parents:
            parents.append(parent)
    for i, libelle in enumerate(parents, start=1):
        type_unite = "DIRECTION" if libelle.upper().startswith("DIRECTION") else "DEPARTEMENT"
        bind.execute(ins_unite, {"type_unite": type_unite, "libelle": libelle, "cle": _cle(libelle),
                                 "parent": None, "ordre": i})
    for i, (libelle, parent) in enumerate(ENTITES, start=1):
        if _cle(libelle) == _cle(parent):
            continue
        type_unite = "AGENCE" if libelle.upper().startswith("AGENCE") else "SERVICE"
        bind.execute(ins_unite, {"type_unite": type_unite, "libelle": libelle, "cle": _cle(libelle),
                                 "parent": _cle(parent), "ordre": i})
    bind.execute(
        sa.text(
            """
            INSERT INTO reclamation_unites (id, type_unite, libelle, cle, est_service_reclamations, ordre, actif,
                                            description)
            SELECT gen_random_uuid(), 'SERVICE', :libelle, :cle, true, 0, true,
                   'Unité centrale de pilotage : réception, qualification, affectation, réponse et clôture.'
            WHERE NOT EXISTS (SELECT 1 FROM reclamation_unites WHERE est_service_reclamations AND actif)
            ON CONFLICT (cle) DO NOTHING
            """
        ),
        {"libelle": SERVICE_RECLAMATIONS, "cle": _cle(SERVICE_RECLAMATIONS)},
    )

    bind.execute(
        sa.text("UPDATE plateforme_domaines SET statut = 'actif' WHERE code = :code AND statut = 'bientot'"),
        {"code": DOMAINE_CODE},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO plateforme_modules
                (id, espace_id, domaine_id, code, label, description, entry_path, statut,
                 status_message, sort_order, is_active, icon)
            SELECT gen_random_uuid(), e.id,
                   (SELECT d.id FROM plateforme_domaines d WHERE d.code = :domaine_code),
                   :code, :label, :description, '/reclamations/dashboard', 'developpement',
                   :status_message, 1, true, 'support_agent'
            FROM plateforme_espaces e
            WHERE e.code = :espace_code
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {
            "espace_code": ESPACE_CODE,
            "domaine_code": DOMAINE_CODE,
            "code": MODULE_CODE,
            "label": "Gestion des réclamations",
            "description": (
                "Réclamations clients pilotées par le Service Réclamations : réception multicanal, "
                "qualification, transfert aux services, réponse au client, clôture, délais et tableau de bord 360°."
            ),
            "status_message": "Module en cours de construction — ouverture après validation du circuit de traitement.",
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM plateforme_modules WHERE code = :c"), {"c": MODULE_CODE})
    op.execute("DROP TRIGGER IF EXISTS trg_reclamation_evenements_immuable ON reclamation_evenements")
    op.execute("DROP FUNCTION IF EXISTS reclamation_evenements_immuable()")
    if sa.inspect(bind).has_table("reclamations"):
        op.drop_constraint("fk_reclamations_affectation_courante", "reclamations", type_="foreignkey")
    for table in TABLES:
        op.drop_table(table, if_exists=True)
