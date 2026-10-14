"""Gestion des réclamations clients (Audit, Contrôle & Conformité → Management & Qualité).

Pilotage centralisé par le Service Réclamations : réception, qualification, affectation à
une unité (direction, département, service, agence), retour du service, réponse au client,
clôture. Le **statut** d'un dossier est distinct de son **étape** dans le circuit.

Traçabilité : les dates clés sont portées par le dossier (cycle courant, filtres et KPI) et
chaque événement est conservé dans ``reclamation_evenements`` (table en ajout seul, protégée
par trigger). Les transferts sont des lignes ``reclamation_affectations`` successives, jamais
réécrites. Pièces jointes : ``ged_documents`` (module ``reclamations``) + métadonnées métier
dans ``reclamation_documents``. Aucune table CORE dupliquée (users, agences, audit_logs).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

DOMAINES_REFERENTIEL = ("TYPE", "MOTIF", "SOUS_MOTIF", "CANAL", "CANAL_REPONSE")
TYPES_UNITE = ("DIRECTION", "DEPARTEMENT", "SERVICE", "AGENCE", "CELLULE")
ROLES_MEMBRE = ("RESPONSABLE", "AGENT")
STATUTS = (
    "A_QUALIFIER",
    "A_AFFECTER",
    "EN_TRAITEMENT",
    "RETOUR_RECU",
    "A_CLOTURER",
    "CLOTUREE",
    "REJETEE",
    "ANNULEE",
    "REOUVERTE",
)
ETAPES = ("RECEPTION", "AFFECTATION", "TRAITEMENT", "CLOTURE")
PRIORITES = ("BASSE", "NORMALE", "HAUTE", "URGENTE")
CATEGORIES_CLIENT = ("PP", "PM", "NON_CLIENT")
RESULTATS = ("FAVORABLE", "PARTIELLEMENT_FAVORABLE", "DEFAVORABLE", "SANS_SUITE", "AUTRE")
SOURCES = ("MANUEL", "CENTRE_APPEL", "IMPORT", "API")
STATUTS_AFFECTATION = ("TRANSMISE", "RECUE", "EN_TRAITEMENT", "RETOURNEE", "ANNULEE")
EVALUATIONS_RETOUR = ("SUFFISANT", "INSUFFISANT")
STATUTS_REPONSE = ("BROUILLON", "A_VALIDER", "VALIDEE", "ENVOYEE", "ANNULEE")
CATEGORIES_DOCUMENT = (
    "NOTE",
    "COURRIER",
    "JUSTIFICATIF",
    "ORIGINAL",
    "PIECE_CLIENT",
    "TRANSMISSION",
    "FICHE_TRAITEMENT",
    "JUSTIFICATIF_SERVICE",
    "RETOUR_SERVICE",
    "REPONSE_CLIENT",
    "PREUVE_ENVOI",
    "AUTRE",
)
STATUTS_RAPPEL = ("AUCUN", "A_RAPPELER", "RAPPELE", "ECHEC")
UNITES_DUREE = ("JOURS_CALENDAIRES", "JOURS_OUVRES", "HEURES")
POINTS_DEPART = ("PREMIERE_RECEPTION", "RECEPTION_SR")
POINTS_ARRIVEE = ("CLOTURE", "REPONSE_CLIENT")
VALIDATIONS_REGLE = ("A_VALIDER", "VALIDEE", "REJETEE")
VALIDATIONS_REFERENTIEL = ("PROPOSEE", "VALIDEE")
ETATS_DELAI = ("CALCULE", "NON_CONFIGURE", "EN_ATTENTE_VALIDATION", "CONFLIT", "SANS_DEPART")
NIVEAUX_ALERTE = ("PROCHE", "RETARD")


def _in(colonne: str, valeurs: tuple[str, ...], nullable: bool = False) -> str:
    liste = ",".join(f"'{v}'" for v in valeurs)
    return f"{colonne} IS NULL OR {colonne} IN ({liste})" if nullable else f"{colonne} IN ({liste})"


def _fk(cible: str, ondelete: str = "RESTRICT") -> ForeignKey:
    return ForeignKey(cible, ondelete=ondelete)


def _user_fk() -> Mapped:
    return mapped_column(UUID(as_uuid=True), _fk("users.id", "SET NULL"), nullable=True)


def _ref_fk(nullable: bool = True) -> Mapped:
    return mapped_column(UUID(as_uuid=True), _fk("reclamation_referentiels.id"), nullable=nullable, index=True)


def _unite_fk() -> Mapped:
    return mapped_column(UUID(as_uuid=True), _fk("reclamation_unites.id"), nullable=True, index=True)


def _ts(nullable: bool = True) -> Mapped:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class ReclamationReferentiel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Types, motifs (parent = type), sous-motifs (parent = motif), canaux de réception et
    canaux d'envoi de la réponse. Une valeur utilisée se désactive, elle ne se supprime pas."""

    __tablename__ = "reclamation_referentiels"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(_in("domaine", DOMAINES_REFERENTIEL), name="ck_reclamation_referentiels_domaine"),
        CheckConstraint(_in("statut_validation", VALIDATIONS_REFERENTIEL),
                        name="ck_reclamation_referentiels_validation"),
    )

    domaine: Mapped[str] = mapped_column(String(20), index=True)
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    libelle: Mapped[str] = mapped_column(String(200))
    cle: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_referentiels.id"), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    # PROPOSEE tant que la banque n'a pas validé la nomenclature : affiché « en attente », jamais « officiel ».
    statut_validation: Mapped[str] = mapped_column(String(20), default="PROPOSEE", server_default="PROPOSEE")
    valide_par_id: Mapped[uuid.UUID | None] = _user_fk()
    valide_le: Mapped[datetime | None] = _ts()
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_by_id: Mapped[uuid.UUID | None] = _user_fk()


class ReclamationUnite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Direction, département, service, agence ou cellule pouvant recevoir ou traiter un dossier.

    ``est_service_reclamations`` désigne l'unique unité centrale de pilotage (index partiel)."""

    __tablename__ = "reclamation_unites"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(_in("type_unite", TYPES_UNITE), name="ck_reclamation_unites_type"),
    )

    type_unite: Mapped[str] = mapped_column(String(20), index=True)
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    libelle: Mapped[str] = mapped_column(String(200))
    cle: Mapped[str] = mapped_column(String(200), unique=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_unites.id"), nullable=True, index=True)
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("agences.id", "SET NULL"), nullable=True, index=True)
    est_service_reclamations: Mapped[bool] = mapped_column(Boolean, default=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_by_id: Mapped[uuid.UUID | None] = _user_fk()


class ReclamationUniteMembre(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Rattachement utilisateur → unité : détermine les dossiers visibles hors périmètre global."""

    __tablename__ = "reclamation_unite_membres"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("unite_id", "user_id", name="uq_reclamation_unite_membres_unite_user"),
        CheckConstraint(_in("role_membre", ROLES_MEMBRE), name="ck_reclamation_unite_membres_role"),
    )

    unite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_unites.id", "CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("users.id", "CASCADE"), index=True)
    role_membre: Mapped[str] = mapped_column(String(20), default="AGENT")
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_by_id: Mapped[uuid.UUID | None] = _user_fk()


class ReclamationRegleDelai(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Délai cible paramétrable (sous-motif > motif > type > règle générale). Jamais appliqué ni
    présenté comme réglementaire tant que ``statut_validation`` ≠ VALIDEE (validation Conformité).

    Une règle déjà appliquée à un dossier ne se modifie plus : une nouvelle version (``remplace_id``)
    prend effet à sa ``date_effet`` et l'ancienne est bornée par ``date_fin``."""

    __tablename__ = "reclamation_regles_delai"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("duree > 0", name="ck_reclamation_regles_delai_duree"),
        CheckConstraint("seuil_alerte IS NULL OR seuil_alerte >= 0", name="ck_reclamation_regles_delai_seuil"),
        CheckConstraint("delai_service IS NULL OR delai_service > 0", name="ck_reclamation_regles_delai_service"),
        CheckConstraint("date_fin IS NULL OR date_fin >= date_effet", name="ck_reclamation_regles_delai_periode"),
        CheckConstraint(_in("unite_duree", UNITES_DUREE), name="ck_reclamation_regles_delai_unite"),
        CheckConstraint(_in("point_depart", POINTS_DEPART), name="ck_reclamation_regles_delai_depart"),
        CheckConstraint(_in("point_arrivee", POINTS_ARRIVEE), name="ck_reclamation_regles_delai_arrivee"),
        CheckConstraint(_in("priorite", PRIORITES, nullable=True), name="ck_reclamation_regles_delai_priorite"),
        CheckConstraint(_in("statut_validation", VALIDATIONS_REGLE), name="ck_reclamation_regles_delai_validation"),
    )

    libelle: Mapped[str] = mapped_column(String(200))
    type_id: Mapped[uuid.UUID | None] = _ref_fk()
    motif_id: Mapped[uuid.UUID | None] = _ref_fk()
    sous_motif_id: Mapped[uuid.UUID | None] = _ref_fk()
    priorite: Mapped[str | None] = mapped_column(String(10), nullable=True)
    duree: Mapped[int] = mapped_column(Integer)
    unite_duree: Mapped[str] = mapped_column(String(20), default="JOURS_CALENDAIRES")
    point_depart: Mapped[str] = mapped_column(String(30), default="PREMIERE_RECEPTION")
    point_arrivee: Mapped[str] = mapped_column(String(30), default="CLOTURE", server_default="CLOTURE")
    remplace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_regles_delai.id", "SET NULL"), nullable=True)
    seuil_alerte: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delai_service: Mapped[int | None] = mapped_column(Integer, nullable=True)
    neutraliser_suspension: Mapped[bool] = mapped_column(Boolean, default=True)
    destinataires: Mapped[list] = mapped_column(JSONB, default=list)
    date_effet: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    statut_validation: Mapped[str] = mapped_column(String(20), default="A_VALIDER")
    valide_par_id: Mapped[uuid.UUID | None] = _user_fk()
    valide_le: Mapped[datetime | None] = _ts()
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_by_id: Mapped[uuid.UUID | None] = _user_fk()


class Reclamation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Dossier de réclamation. Référence ``REC-AAAA-NNNNNN`` attribuée par compteur, jamais saisie."""

    __tablename__ = "reclamations"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(_in("statut", STATUTS), name="ck_reclamations_statut"),
        CheckConstraint(_in("etape", ETAPES), name="ck_reclamations_etape"),
        CheckConstraint(_in("priorite", PRIORITES), name="ck_reclamations_priorite"),
        CheckConstraint(_in("client_categorie", CATEGORIES_CLIENT, nullable=True), name="ck_reclamations_client"),
        CheckConstraint(_in("resultat", RESULTATS, nullable=True), name="ck_reclamations_resultat"),
        CheckConstraint(_in("source", SOURCES), name="ck_reclamations_source"),
        CheckConstraint("client_racine IS NULL OR client_racine ~ '^[0-9]{6}$'", name="ck_reclamations_racine"),
        CheckConstraint("montant_conteste IS NULL OR montant_conteste >= 0", name="ck_reclamations_montant"),
        CheckConstraint("date_reception_sr IS NULL OR date_reception_sr >= date_premiere_reception",
                        name="ck_reclamations_date_reception_sr"),
        CheckConstraint("date_reponse_client IS NULL OR date_reponse_client >= date_premiere_reception",
                        name="ck_reclamations_date_reponse"),
        CheckConstraint("date_cloture IS NULL OR date_cloture >= date_premiere_reception",
                        name="ck_reclamations_date_cloture"),
        CheckConstraint("doublon_de_id IS NULL OR doublon_de_id <> id", name="ck_reclamations_doublon"),
        CheckConstraint("reclamation_liee_id IS NULL OR reclamation_liee_id <> id", name="ck_reclamations_liee"),
        CheckConstraint(_in("etat_delai", ETATS_DELAI, nullable=True), name="ck_reclamations_etat_delai"),
        CheckConstraint(_in("niveau_alerte", NIVEAUX_ALERTE, nullable=True), name="ck_reclamations_niveau_alerte"),
        UniqueConstraint("annee", "numero", name="uq_reclamations_annee_numero"),
        Index("ix_reclamations_actives_echeance", "echeance",
              postgresql_where=text("supprimee_le IS NULL AND archivee_le IS NULL "
                                    "AND statut NOT IN ('CLOTUREE', 'REJETEE', 'ANNULEE')")),
        Index("ix_reclamations_racine_reception", "client_racine", "date_premiere_reception",
              postgresql_where=text("client_racine IS NOT NULL")),
    )

    reference: Mapped[str] = mapped_column(String(30), unique=True)
    annee: Mapped[int] = mapped_column(Integer)
    numero: Mapped[int] = mapped_column(Integer)
    objet: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    type_id: Mapped[uuid.UUID | None] = _ref_fk()
    motif_id: Mapped[uuid.UUID | None] = _ref_fk()
    sous_motif_id: Mapped[uuid.UUID | None] = _ref_fk()
    motif_autre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sous_motif_autre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    priorite: Mapped[str] = mapped_column(String(10), default="NORMALE", index=True)
    statut: Mapped[str] = mapped_column(String(30), index=True)
    etape: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(20), default="MANUEL")

    canal_id: Mapped[uuid.UUID] = _ref_fk(nullable=False)
    unite_reception_id: Mapped[uuid.UUID | None] = _unite_fk()
    unite_concernee_id: Mapped[uuid.UUID | None] = _unite_fk()

    client_racine: Mapped[str | None] = mapped_column(String(6), nullable=True, index=True)
    client_categorie: Mapped[str | None] = mapped_column(String(12), nullable=True)
    client_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_telephone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_adresse: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("agences.id", "SET NULL"), nullable=True, index=True)
    compte_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    carte_masquee: Mapped[str | None] = mapped_column(String(25), nullable=True)
    operation_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    operation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    montant_conteste: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    devise: Mapped[str | None] = mapped_column(String(3), nullable=True)

    reclamation_liee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamations.id", "SET NULL"), nullable=True, index=True)
    doublon_de_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamations.id", "SET NULL"), nullable=True, index=True)

    date_reclamation: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_premiere_reception: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    date_reception_sr: Mapped[datetime | None] = _ts()
    date_qualification: Mapped[datetime | None] = _ts()
    date_transmission: Mapped[datetime | None] = _ts()
    date_reception_service: Mapped[datetime | None] = _ts()
    date_retour_service: Mapped[datetime | None] = _ts()
    date_reponse_client: Mapped[datetime | None] = _ts()
    date_cloture: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    date_suspension: Mapped[datetime | None] = _ts()
    date_reouverture: Mapped[datetime | None] = _ts()

    unite_suivi_id: Mapped[uuid.UUID | None] = _unite_fk()
    gestionnaire_id: Mapped[uuid.UUID | None] = _user_fk()
    unite_traitement_id: Mapped[uuid.UUID | None] = _unite_fk()
    responsable_traitement_id: Mapped[uuid.UUID | None] = _user_fk()
    affectation_courante_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reclamation_affectations.id", ondelete="SET NULL", use_alter=True,
                   name="fk_reclamations_affectation_courante"),
        nullable=True,
    )

    regle_delai_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_regles_delai.id", "SET NULL"), nullable=True)
    echeance: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    echeance_initiale: Mapped[datetime | None] = _ts()
    # Pourquoi une échéance existe (CALCULE) ou non (règle absente, en attente, en conflit, départ manquant).
    etat_delai: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Dernier niveau notifié : une alerte par franchissement de seuil, jamais une par passage du batch.
    niveau_alerte: Mapped[str | None] = mapped_column(String(10), nullable=True)
    alerte_notifiee_le: Mapped[datetime | None] = _ts()
    # Début de la zone « échéance proche » (échéance − seuil de la règle) et arrêt du délai (événement de fin).
    date_alerte: Mapped[datetime | None] = _ts()
    date_fin_delai: Mapped[datetime | None] = _ts()

    statut_avant_suspension: Mapped[str | None] = mapped_column(String(30), nullable=True)
    motif_suspension: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions_reprise: Mapped[str | None] = mapped_column(Text, nullable=True)
    motif_refus: Mapped[str | None] = mapped_column(Text, nullable=True)
    motif_annulation: Mapped[str | None] = mapped_column(Text, nullable=True)
    resultat: Mapped[str | None] = mapped_column(String(30), nullable=True)
    motif_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    cloture_par_id: Mapped[uuid.UUID | None] = _user_fk()
    nb_reouvertures: Mapped[int] = mapped_column(Integer, default=0)
    nb_renvois: Mapped[int] = mapped_column(Integer, default=0)
    archivee_le: Mapped[datetime | None] = _ts()
    archivee_par_id: Mapped[uuid.UUID | None] = _user_fk()
    # Suppression logique (corbeille) : hors des listes, KPI et exports ; restaurable.
    supprimee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    supprimee_par_id: Mapped[uuid.UUID | None] = _user_fk()
    motif_suppression: Mapped[str | None] = mapped_column(Text, nullable=True)

    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_by_id: Mapped[uuid.UUID | None] = _user_fk()


class ReclamationAffectation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Fiche de traitement : une transmission à une unité, sa réception, l'analyse et le retour.

    Un renvoi pour complément crée une nouvelle ligne (``parent_id``) : l'historique reste intact."""

    __tablename__ = "reclamation_affectations"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("reclamation_id", "numero", name="uq_reclamation_affectations_numero"),
        CheckConstraint(_in("statut", STATUTS_AFFECTATION), name="ck_reclamation_affectations_statut"),
        CheckConstraint(_in("evaluation", EVALUATIONS_RETOUR, nullable=True),
                        name="ck_reclamation_affectations_evaluation"),
        CheckConstraint(_in("decision_proposee", RESULTATS, nullable=True),
                        name="ck_reclamation_affectations_decision"),
        CheckConstraint("recu_le IS NULL OR recu_le >= transmis_le", name="ck_reclamation_affectations_reception"),
        CheckConstraint("retour_le IS NULL OR (recu_le IS NOT NULL AND retour_le >= recu_le)",
                        name="ck_reclamation_affectations_retour"),
    )

    reclamation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("reclamations.id", "CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_affectations.id", "SET NULL"), nullable=True)
    unite_emettrice_id: Mapped[uuid.UUID | None] = _unite_fk()
    unite_destinataire_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_unites.id"), index=True)
    statut: Mapped[str] = mapped_column(String(20), default="TRANSMISE", index=True)
    transmis_le: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    transmis_par_id: Mapped[uuid.UUID | None] = _user_fk()
    motif_transfert: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    echeance_service: Mapped[datetime | None] = _ts()
    recu_le: Mapped[datetime | None] = _ts()
    recu_par_id: Mapped[uuid.UUID | None] = _user_fk()
    responsable_id: Mapped[uuid.UUID | None] = _user_fk()
    analyse: Mapped[str | None] = mapped_column(Text, nullable=True)
    actions_menees: Mapped[str | None] = mapped_column(Text, nullable=True)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_proposee: Mapped[str | None] = mapped_column(String(30), nullable=True)
    retour_le: Mapped[datetime | None] = _ts()
    retour_par_id: Mapped[uuid.UUID | None] = _user_fk()
    evaluation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    evaluation_commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    evalue_le: Mapped[datetime | None] = _ts()
    evalue_par_id: Mapped[uuid.UUID | None] = _user_fk()
    revision: Mapped[int] = mapped_column(Integer, default=1)


class ReclamationReponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Réponse au client : brouillon → à valider → validée → envoyée (canal, date, preuve)."""

    __tablename__ = "reclamation_reponses"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("reclamation_id", "numero", name="uq_reclamation_reponses_numero"),
        CheckConstraint(_in("statut", STATUTS_REPONSE), name="ck_reclamation_reponses_statut"),
        CheckConstraint(_in("resultat", RESULTATS, nullable=True), name="ck_reclamation_reponses_resultat"),
        CheckConstraint("statut <> 'ENVOYEE' OR (envoye_le IS NOT NULL AND canal_envoi_id IS NOT NULL)",
                        name="ck_reclamation_reponses_envoi"),
    )

    reclamation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("reclamations.id", "CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    statut: Mapped[str] = mapped_column(String(20), default="BROUILLON", index=True)
    objet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contenu: Mapped[str] = mapped_column(Text)
    resultat: Mapped[str | None] = mapped_column(String(30), nullable=True)
    canal_envoi_id: Mapped[uuid.UUID | None] = _ref_fk()
    destinataire: Mapped[str | None] = mapped_column(String(255), nullable=True)
    redige_par_id: Mapped[uuid.UUID | None] = _user_fk()
    soumis_le: Mapped[datetime | None] = _ts()
    valide_par_id: Mapped[uuid.UUID | None] = _user_fk()
    valide_le: Mapped[datetime | None] = _ts()
    commentaire_validation: Mapped[str | None] = mapped_column(Text, nullable=True)
    envoye_le: Mapped[datetime | None] = _ts()
    envoye_par_id: Mapped[uuid.UUID | None] = _user_fk()
    reference_envoi: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class ReclamationDocument(Base):
    """Métadonnées métier d'une pièce GED : catégorie, rattachement (fiche, réponse), commentaire.

    Le fichier vit dans ``ged_documents`` ; un retrait = corbeille GED motivée, jamais d'écrasement."""

    __tablename__ = "reclamation_documents"
    __table_args__ = (
        CheckConstraint(_in("categorie", CATEGORIES_DOCUMENT), name="ck_reclamation_documents_categorie"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("ged_documents.id", "CASCADE"), primary_key=True)
    reclamation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("reclamations.id", "CASCADE"), index=True)
    categorie: Mapped[str] = mapped_column(String(30), index=True)
    affectation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_affectations.id", "SET NULL"), nullable=True)
    reponse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_reponses.id", "SET NULL"), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()


class ReclamationAppel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Canal Téléphone / Centre d'appel : appel(s) rattaché(s) au dossier, rappels prévus.

    L'enregistrement de l'appel n'est référencé que si la banque l'autorise."""

    __tablename__ = "reclamation_appels"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(_in("rappel_statut", STATUTS_RAPPEL), name="ck_reclamation_appels_rappel"),
        CheckConstraint("reference_enregistrement IS NULL OR enregistrement_autorise",
                        name="ck_reclamation_appels_enregistrement"),
    )

    reclamation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("reclamations.id", "CASCADE"), index=True)
    appel_le: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    numero_appelant: Mapped[str | None] = mapped_column(String(40), nullable=True)
    agent_id: Mapped[uuid.UUID | None] = _user_fk()
    identite_verifiee: Mapped[bool] = mapped_column(Boolean, default=False)
    mode_verification: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reference_appel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    enregistrement_autorise: Mapped[bool] = mapped_column(Boolean, default=False)
    reference_enregistrement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rappel_statut: Mapped[str] = mapped_column(String(20), default="AUCUN")
    rappel_prevu_le: Mapped[datetime | None] = _ts()
    rappel_effectue_le: Mapped[datetime | None] = _ts()
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()


class ReclamationOperation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Opération contestée (référence + montant) : une réclamation en porte 0..N."""

    __tablename__ = "reclamation_operations"
    __table_args__ = (
        CheckConstraint("montant IS NULL OR montant > 0", name="ck_reclamation_operations_montant"),
        CheckConstraint("length(btrim(reference)) > 0", name="ck_reclamation_operations_reference"),
        UniqueConstraint("reclamation_id", "reference", name="uq_reclamation_operations_reference"),
    )

    reclamation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("reclamations.id", "CASCADE"), index=True)
    ordre: Mapped[int] = mapped_column(Integer, default=1)
    reference: Mapped[str] = mapped_column(String(120))
    montant: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    devise: Mapped[str] = mapped_column(String(3), default="MRU")
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()


class ReclamationEvenement(UUIDPrimaryKeyMixin, Base):
    """Chronologie en ajout seul (UPDATE / DELETE refusés par trigger).

    ``date_effet`` = date métier déclarée (ex. première réception) ; ``enregistre_le`` = horodatage
    serveur de la saisie. Les deux sont conservés pour qu'aucune date ne soit falsifiable."""

    __tablename__ = "reclamation_evenements"

    reclamation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("reclamations.id", "CASCADE"), index=True)
    type_evenement: Mapped[str] = mapped_column(String(40), index=True)
    statut_avant: Mapped[str | None] = mapped_column(String(30), nullable=True)
    statut_apres: Mapped[str | None] = mapped_column(String(30), nullable=True)
    etape_avant: Mapped[str | None] = mapped_column(String(20), nullable=True)
    etape_apres: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_effet: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enregistre_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    auteur_id: Mapped[uuid.UUID | None] = _user_fk()
    unite_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_unites.id", "SET NULL"), nullable=True)
    affectation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_affectations.id", "SET NULL"), nullable=True)
    reponse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("reclamation_reponses.id", "SET NULL"), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    donnees: Mapped[dict] = mapped_column(JSONB, default=dict)


class ReclamationJourFerie(Base):
    """Jours non ouvrés ponctuels (calendrier des délais en jours ouvrés)."""

    __tablename__ = "reclamation_jours_feries"

    jour: Mapped[date] = mapped_column(Date, primary_key=True)
    libelle: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()


class ReclamationParametre(Base):
    __tablename__ = "reclamation_parametres"

    cle: Mapped[str] = mapped_column(String(80), primary_key=True)
    valeur: Mapped[dict | list | str | int | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[uuid.UUID | None] = _user_fk()


class ReclamationCompteur(Base):
    __tablename__ = "reclamation_compteurs"

    annee: Mapped[int] = mapped_column(Integer, primary_key=True)
    dernier: Mapped[int] = mapped_column(Integer, default=0)
