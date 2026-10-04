"""EER — Gestion des Entrées en Relation (docs/conformite/eer-architecture-metier.md §3).

Réutilise users, agences, ged_documents, audit_logs : aucune table CORE dupliquée.
Un dossier n'est jamais supprimé ; versions, décisions et historique sont immuables
(trigger PostgreSQL, migration eer_04).
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
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


def _fk(cible: str, ondelete: str = "RESTRICT", **kw) -> ForeignKey:
    return ForeignKey(cible, ondelete=ondelete, **kw)


def _user_fk(nullable: bool = True, ondelete: str = "SET NULL") -> Mapped:
    return mapped_column(UUID(as_uuid=True), _fk("users.id", ondelete), nullable=nullable)


# --- Référentiels, paramètres, compteur ------------------------------------------------

class EerReferentiel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eer_referentiels"
    __table_args__ = (UniqueConstraint("domaine", "code", name="uq_eer_referentiels_domaine_code"),)

    domaine: Mapped[str] = mapped_column(String(40), index=True)
    code: Mapped[str] = mapped_column(String(60))
    libelle: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_referentiels.id"), nullable=True, index=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class EerParametre(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "eer_parametres"
    __table_args__ = (UniqueConstraint("code", "date_effet", name="uq_eer_parametres_code_effet"),)

    code: Mapped[str] = mapped_column(String(80), index=True)
    valeur: Mapped[dict | list | int | float | str | bool | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_effet: Mapped[date] = mapped_column(Date)
    valide_par_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EerReferenceCompteur(Base):
    __tablename__ = "eer_reference_compteurs"

    annee: Mapped[int] = mapped_column(Integer, primary_key=True)
    dernier: Mapped[int] = mapped_column(Integer, default=0)


# --- Parties (saisie unique, réutilisables d'un dossier à l'autre) ---------------------

class EerPartie(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eer_parties"
    __table_args__ = (CheckConstraint("nature IN ('PHYSIQUE','MORALE')", name="ck_eer_parties_nature"),)

    nature: Mapped[str] = mapped_column(String(10))
    nom: Mapped[str] = mapped_column(String(255), index=True)
    nationalite: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pays_residence: Mapped[str | None] = mapped_column(String(80), nullable=True)
    adresse: Mapped[str | None] = mapped_column(Text, nullable=True)
    telephone_1: Mapped[str | None] = mapped_column(String(40), nullable=True)
    telephone_2: Mapped[str | None] = mapped_column(String(40), nullable=True)
    telephone_3: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    racine_client: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()

    physique: Mapped[EerPartiePhysique | None] = relationship(
        back_populates="partie", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    morale: Mapped[EerPartieMorale | None] = relationship(
        back_populates="partie", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    pieces: Mapped[list[EerPieceIdentite]] = relationship(
        back_populates="partie", cascade="all, delete-orphan", lazy="selectin",
        order_by="EerPieceIdentite.created_at")


class EerPartiePhysique(Base):
    __tablename__ = "eer_parties_physiques"

    partie_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("eer_parties.id", "CASCADE"), primary_key=True)
    sexe: Mapped[str | None] = mapped_column(String(1), nullable=True)
    prenom: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prenom_pere: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date_naissance: Mapped[date | None] = mapped_column(Date, nullable=True)
    lieu_naissance: Mapped[str | None] = mapped_column(String(120), nullable=True)
    situation_matrimoniale: Mapped[str | None] = mapped_column(String(40), nullable=True)
    profession: Mapped[str | None] = mapped_column(String(120), nullable=True)
    employeur: Mapped[str | None] = mapped_column(String(200), nullable=True)
    salaire_net: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    date_embauche: Mapped[date | None] = mapped_column(Date, nullable=True)
    type_contrat: Mapped[str | None] = mapped_column(String(60), nullable=True)

    partie: Mapped[EerPartie] = relationship(back_populates="physique")


class EerPartieMorale(Base):
    __tablename__ = "eer_parties_morales"

    partie_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("eer_parties.id", "CASCADE"), primary_key=True)
    forme: Mapped[str | None] = mapped_column(String(60), nullable=True)
    date_creation: Mapped[date | None] = mapped_column(Date, nullable=True)
    activites: Mapped[str | None] = mapped_column(Text, nullable=True)
    effectif: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rc_chronologique: Mapped[str | None] = mapped_column(String(60), nullable=True)
    rc_analytique: Mapped[str | None] = mapped_column(String(60), nullable=True)
    nif: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    residence_fiscale: Mapped[str | None] = mapped_column(String(80), nullable=True)
    site_web: Mapped[str | None] = mapped_column(String(255), nullable=True)
    numero_agrement: Mapped[str | None] = mapped_column(String(60), nullable=True)
    impact_rse: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    domaines_rse: Mapped[str | None] = mapped_column(Text, nullable=True)

    partie: Mapped[EerPartie] = relationship(back_populates="morale")


class EerPieceIdentite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eer_pieces_identite"
    __table_args__ = (
        UniqueConstraint("type_piece", "numero", "pays_emission", name="uq_eer_pieces_identite",
                         postgresql_nulls_not_distinct=True),
    )

    partie_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("eer_parties.id", "CASCADE"), index=True)
    type_piece: Mapped[str] = mapped_column(String(30))
    numero: Mapped[str] = mapped_column(String(60))
    date_delivrance: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_expiration: Mapped[date | None] = mapped_column(Date, nullable=True)
    pays_emission: Mapped[str | None] = mapped_column(String(80), nullable=True)

    partie: Mapped[EerPartie] = relationship(back_populates="pieces")


# --- Dossier ---------------------------------------------------------------------------

class EerDossier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eer_dossiers"
    __table_args__ = (
        CheckConstraint("type_signature IS NULL OR type_signature IN ('UNIQUE','CONJOINTES','SEPAREES')",
                        name="ck_eer_dossiers_type_signature"),
        CheckConstraint("moment_controle IN ('PREALABLE','A_POSTERIORI')", name="ck_eer_dossiers_moment"),
        CheckConstraint("operation_type IN ('ENTREE_RELATION','MISE_A_JOUR')", name="ck_eer_dossiers_operation"),
        CheckConstraint("nb_relances >= 0", name="ck_eer_dossiers_relances"),
        CheckConstraint("statut <> 'ABANDONNE' OR motif_abandon IS NOT NULL", name="ck_eer_dossiers_abandon"),
        CheckConstraint("revision >= 0", name="ck_eer_dossiers_revision"),
        CheckConstraint("deleted_at IS NULL OR motif_suppression IS NOT NULL", name="ck_eer_dossiers_suppression"),
        CheckConstraint("version_courante >= 1", name="ck_eer_dossiers_version"),
        CheckConstraint(
            "statut IN ('BROUILLON','SOUMIS','A_AFFECTER','AFFECTE','EN_CONTROLE','CONFORME','NON_CONFORME',"
            "'A_COMPLETER','RESOUMIS','AVIS_CONFORMITE','VALIDE','CLOTURE','ARCHIVE','ABANDONNE')",
            name="ck_eer_dossiers_statut"),
        CheckConstraint("etape IS NULL OR etape IN ('CHECKLIST','CHECKLIST_VALIDEE','FICHES','CONTROLES')",
                        name="ck_eer_dossiers_etape"),
        Index("ix_eer_dossiers_agence_statut", "agence_id", "statut"),
        Index("ix_eer_dossiers_analyste_statut", "analyste_id", "statut"),
        Index("ix_eer_dossiers_created_at", "created_at"),
    )

    reference: Mapped[str] = mapped_column(String(20), unique=True)
    operation_type: Mapped[str] = mapped_column(String(20), default="ENTREE_RELATION")
    agence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("agences.id"), index=True)
    type_client_code: Mapped[str] = mapped_column(String(20), index=True)
    profil_code: Mapped[str] = mapped_column(String(60), index=True)
    sous_profil_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    type_compte_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    client_partie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_parties.id"), index=True)
    racine_client: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    numero_idp: Mapped[str | None] = mapped_column(String(40), nullable=True)
    numero_idm: Mapped[str | None] = mapped_column(String(40), nullable=True)
    date_eer: Mapped[date] = mapped_column(Date)
    numero_compte: Mapped[str | None] = mapped_column(String(40), nullable=True)
    date_ouverture_compte: Mapped[date | None] = mapped_column(Date, nullable=True)
    nombre_signataires: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type_signature: Mapped[str | None] = mapped_column(String(12), nullable=True)
    tranche_mouvement_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    origine_fonds: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination_fonds: Mapped[str | None] = mapped_column(Text, nullable=True)
    commentaire_profil: Mapped[str | None] = mapped_column(Text, nullable=True)
    risque_lbcft: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ppe_dossier: Mapped[bool] = mapped_column(Boolean, default=False)
    fatca_dossier: Mapped[bool] = mapped_column(Boolean, default=False)
    avis_requis: Mapped[bool] = mapped_column(Boolean, default=False)
    conformite_physique: Mapped[str | None] = mapped_column(String(15), nullable=True)
    conformite_systeme: Mapped[str | None] = mapped_column(String(15), nullable=True)
    conformite_coherence: Mapped[str | None] = mapped_column(String(15), nullable=True)
    decision_globale: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    moment_controle: Mapped[str] = mapped_column(String(15), default="PREALABLE")
    etat_compte: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    statut: Mapped[str] = mapped_column(String(20), default="BROUILLON", index=True)
    etape: Mapped[str | None] = mapped_column(String(20), nullable=True)
    version_courante: Mapped[int] = mapped_column(Integer, default=1)
    # Jeton de concurrence optimiste : incrémenté à chaque mutation, exigé par l'API.
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    nb_relances: Mapped[int] = mapped_column(Integer, default=0)
    derniere_relance_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motif_abandon: Mapped[str | None] = mapped_column(Text, nullable=True)
    parametres_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("users.id"))
    analyste_id: Mapped[uuid.UUID | None] = _user_fk()
    controleur_id: Mapped[uuid.UUID | None] = _user_fk()
    soumis_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Suppression logique : le dossier sort des listes et de l'API, son historique reste en base.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_id: Mapped[uuid.UUID | None] = _user_fk()
    motif_suppression: Mapped[str | None] = mapped_column(Text, nullable=True)

    client: Mapped[EerPartie] = relationship(foreign_keys=[client_partie_id], lazy="selectin")
    parties: Mapped[list[EerDossierPartie]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan", order_by="EerDossierPartie.ordre")
    items: Mapped[list[EerChecklistItem]] = relationship(back_populates="dossier", cascade="all, delete-orphan")


class EerDossierPartie(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eer_dossier_parties"
    __table_args__ = (
        UniqueConstraint("dossier_id", "partie_id", "role", name="uq_eer_dossier_parties"),
        CheckConstraint(
            "role IN ('CLIENT','MANDATAIRE','SIGNATAIRE_COMPTE','GERANT','CO_GERANT','SIGNATAIRE_ASSOCIATION',"
            "'CO_SIGNATAIRE_ASSOCIATION','MEMBRE_DIRECTION','ACTIONNAIRE','BENEFICIAIRE_EFFECTIF','CONTACT_URGENCE')",
            name="ck_eer_dossier_parties_role"),
        CheckConstraint("forme_mandat IS NULL OR forme_mandat IN ('MANDATAIRE_SOCIAL','PROCURATION')",
                        name="ck_eer_dossier_parties_mandat"),
        CheckConstraint("be_source IS NULL OR be_source IN ('CALCULE','DECLARE')", name="ck_eer_dossier_parties_be"),
        # PPE / FATCA / risque : seulement sur les fiches client et mandataire.
        CheckConstraint("role IN ('CLIENT','MANDATAIRE') OR (ppe IS NULL AND fatca_indice IS NULL "
                        "AND risque_lbcft IS NULL)", name="ck_eer_dossier_parties_ppe_fatca"),
    )

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("eer_dossiers.id", "CASCADE"), index=True)
    partie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_parties.id"), index=True)
    role: Mapped[str] = mapped_column(String(30), index=True)
    forme_mandat: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lien_client: Mapped[str | None] = mapped_column(Text, nullable=True)
    fonction: Mapped[str | None] = mapped_column(String(120), nullable=True)
    comptes_mandat: Mapped[str | None] = mapped_column(Text, nullable=True)
    ppe: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ppe_motif: Mapped[str | None] = mapped_column(Text, nullable=True)
    fatca_indice: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fatca_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    risque_lbcft: Mapped[str | None] = mapped_column(String(10), nullable=True)
    gestionnaire_id: Mapped[uuid.UUID | None] = _user_fk()
    responsable_agence_id: Mapped[uuid.UUID | None] = _user_fk()
    be_source: Mapped[str | None] = mapped_column(String(10), nullable=True)
    be_pourcentage_calcule: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)

    dossier: Mapped[EerDossier] = relationship(back_populates="parties")
    partie: Mapped[EerPartie] = relationship(lazy="selectin")


class EerDetention(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eer_detentions"
    __table_args__ = (
        UniqueConstraint("dossier_id", "detenteur_partie_id", "detenue_partie_id", name="uq_eer_detentions"),
        CheckConstraint("detenteur_partie_id <> detenue_partie_id", name="ck_eer_detentions_distinct"),
        CheckConstraint("pourcentage IS NULL OR (pourcentage > 0 AND pourcentage <= 100)",
                        name="ck_eer_detentions_pourcentage"),
        CheckConstraint("pourcentage IS NOT NULL OR lien IS NOT NULL", name="ck_eer_detentions_lien"),
    )

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("eer_dossiers.id", "CASCADE"), index=True)
    detenteur_partie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_parties.id"))
    detenue_partie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_parties.id"))
    pourcentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    lien: Mapped[str | None] = mapped_column(Text, nullable=True)
    niveau: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EerEvaluationRisque(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "eer_evaluations_risque"
    __table_args__ = (CheckConstraint("niveau IN ('FAIBLE','MOYEN','ELEVE')", name="ck_eer_eval_risque_niveau"),)

    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_dossiers.id"), index=True)
    dossier_partie_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_dossier_parties.id", "SET NULL"), nullable=True)
    niveau: Mapped[str] = mapped_column(String(10))
    niveau_declare: Mapped[str | None] = mapped_column(String(10), nullable=True)
    facteurs: Mapped[dict] = mapped_column(JSONB, default=dict)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    evalue_par_id: Mapped[uuid.UUID | None] = _user_fk()
    evalue_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Moteur ----------------------------------------------------------------------------

class EerChecklistRegle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eer_checklist_regles"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_eer_checklist_regles_code_version"),
        CheckConstraint("portee IN ('DOSSIER','PARTIE')", name="ck_eer_regles_portee"),
        CheckConstraint("portee = 'DOSSIER' OR role_cible IS NOT NULL", name="ck_eer_regles_role"),
    )

    code: Mapped[str] = mapped_column(String(60), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    libelle: Mapped[str] = mapped_column(String(255))
    categorie: Mapped[str] = mapped_column(String(30))
    axe: Mapped[str] = mapped_column(String(15))
    nature: Mapped[str] = mapped_column(String(15))
    portee: Mapped[str] = mapped_column(String(10), default="DOSSIER")
    role_cible: Mapped[str | None] = mapped_column(String(30), nullable=True)
    obligatoire: Mapped[bool] = mapped_column(Boolean, default=True)
    condition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    type_controle: Mapped[str] = mapped_column(String(20), default="MANUEL")
    document_type_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    date_effet: Mapped[date] = mapped_column(Date)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()


class EerChecklistItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eer_checklist_items"
    __table_args__ = (
        UniqueConstraint("dossier_id", "regle_code", "dossier_partie_id", name="uq_eer_checklist_items",
                         postgresql_nulls_not_distinct=True),
        CheckConstraint(
            "statut IN ('NON_CONTROLE','EN_COURS','CONFORME','NON_CONFORME','MANQUANT','NON_APPLICABLE','A_VERIFIER')",
            name="ck_eer_items_statut"),
        CheckConstraint("presence IS NULL OR presence IN ('PRESENT','ABSENT','SANS_OBJET')",
                        name="ck_eer_items_presence"),
        CheckConstraint("statut NOT IN ('NON_CONFORME','NON_APPLICABLE') OR motif IS NOT NULL",
                        name="ck_eer_items_motif"),
    )

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("eer_dossiers.id", "CASCADE"), index=True)
    regle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_checklist_regles.id"))
    regle_code: Mapped[str] = mapped_column(String(60))
    regle_version: Mapped[int] = mapped_column(Integer)
    dossier_partie_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_dossier_parties.id"), nullable=True, index=True)
    libelle: Mapped[str] = mapped_column(String(255))
    categorie: Mapped[str] = mapped_column(String(30))
    axe: Mapped[str] = mapped_column(String(15))
    nature: Mapped[str] = mapped_column(String(15))
    obligatoire: Mapped[bool] = mapped_column(Boolean, default=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    statut: Mapped[str] = mapped_column(String(20), default="NON_CONTROLE", index=True)
    presence: Mapped[str | None] = mapped_column(String(12), nullable=True)
    motif: Mapped[str | None] = mapped_column(Text, nullable=True)
    motif_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    neutralise_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    derogation_acceptee: Mapped[bool] = mapped_column(Boolean, default=False)
    raison_applicabilite: Mapped[list] = mapped_column(JSONB, default=list)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("ged_documents.id", "SET NULL"), nullable=True)
    pointe_par_id: Mapped[uuid.UUID | None] = _user_fk()
    pointe_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    controle_par_id: Mapped[uuid.UUID | None] = _user_fk()
    controle_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dossier: Mapped[EerDossier] = relationship(back_populates="items")


class EerChampEtat(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """État d'un champ de fiche ; la valeur reste dans la donnée source."""

    __tablename__ = "eer_champs_etat"
    __table_args__ = (
        UniqueConstraint("dossier_id", "dossier_partie_id", "chemin", name="uq_eer_champs_etat",
                         postgresql_nulls_not_distinct=True),
        CheckConstraint("etat IN ('CONNU','MANQUANT','A_CONFIRMER','CONFIRME','NON_APPLICABLE')",
                        name="ck_eer_champs_etat_etat"),
    )

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("eer_dossiers.id", "CASCADE"), index=True)
    dossier_partie_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_dossier_parties.id"), nullable=True)
    chemin: Mapped[str] = mapped_column(String(120))
    etat: Mapped[str] = mapped_column(String(15))
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    empreinte: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirme_par_id: Mapped[uuid.UUID | None] = _user_fk()
    confirme_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EerControle(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "eer_controles"

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("eer_dossiers.id", "CASCADE"), index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_checklist_items.id", "SET NULL"), nullable=True)
    code: Mapped[str] = mapped_column(String(60))
    type_controle: Mapped[str] = mapped_column(String(20))
    resultat: Mapped[str] = mapped_column(String(20))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer)
    execute_par_id: Mapped[uuid.UUID | None] = _user_fk()
    execute_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Suivi -----------------------------------------------------------------------------

class EerAnomalie(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eer_anomalies"
    __table_args__ = (
        CheckConstraint("gravite IN ('BLOQUANTE','MAJEURE','MINEURE')", name="ck_eer_anomalies_gravite"),
        CheckConstraint("statut IN ('OUVERTE','EN_COMPLEMENT','CORRIGEE','ACCEPTEE','CLOSE','ANNULEE')",
                        name="ck_eer_anomalies_statut"),
        CheckConstraint("statut <> 'ACCEPTEE' OR justification IS NOT NULL", name="ck_eer_anomalies_derogation"),
    )

    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_dossiers.id"), index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_checklist_items.id", "SET NULL"), nullable=True, index=True)
    controle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_controles.id", "SET NULL"), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("ged_documents.id", "SET NULL"), nullable=True)
    dossier_partie_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_dossier_parties.id", "SET NULL"), nullable=True)
    champ: Mapped[str | None] = mapped_column(String(120), nullable=True)
    type_code: Mapped[str] = mapped_column(String(60))
    gravite: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(Text)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_attendue: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[str] = mapped_column(String(15), default="OUVERTE", index=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    echeance_regularisation: Mapped[date | None] = mapped_column(Date, nullable=True)
    version_detection: Mapped[int] = mapped_column(Integer)
    version_resolution: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    resolved_by_id: Mapped[uuid.UUID | None] = _user_fk()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EerComplement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eer_complements"
    __table_args__ = (
        UniqueConstraint("dossier_id", "numero", name="uq_eer_complements_numero"),
        CheckConstraint("statut IN ('OUVERT','RECU','ANNULE')", name="ck_eer_complements_statut"),
    )

    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_dossiers.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    origine: Mapped[str] = mapped_column(String(20))
    consigne: Mapped[str | None] = mapped_column(Text, nullable=True)
    echeance: Mapped[date | None] = mapped_column(Date, nullable=True)
    statut: Mapped[str] = mapped_column(String(10), default="OUVERT")
    version_demande: Mapped[int] = mapped_column(Integer)
    demande_par_id: Mapped[uuid.UUID | None] = _user_fk()
    recu_par_id: Mapped[uuid.UUID | None] = _user_fk()
    recu_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    elements: Mapped[list[EerComplementElement]] = relationship(
        back_populates="complement", cascade="all, delete-orphan", lazy="selectin")


class EerComplementElement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "eer_complement_elements"
    __table_args__ = (
        CheckConstraint("item_id IS NOT NULL OR anomalie_id IS NOT NULL OR champ IS NOT NULL",
                        name="ck_eer_complement_elements_cible"),
    )

    complement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("eer_complements.id", "CASCADE"), index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_checklist_items.id"), nullable=True)
    anomalie_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_anomalies.id"), nullable=True)
    champ: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fourni: Mapped[bool] = mapped_column(Boolean, default=False)

    complement: Mapped[EerComplement] = relationship(back_populates="elements")


class EerVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "eer_versions"
    __table_args__ = (UniqueConstraint("dossier_id", "numero", "evenement", name="uq_eer_versions"),)

    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_dossiers.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    evenement: Mapped[str] = mapped_column(String(30))
    contenu: Mapped[dict] = mapped_column(JSONB)
    empreinte: Mapped[str] = mapped_column(String(64))
    cree_par_id: Mapped[uuid.UUID | None] = _user_fk(ondelete="RESTRICT")
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EerDecision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "eer_decisions"
    __table_args__ = (
        CheckConstraint("resultat IN ('CONFORME','NON_CONFORME','INCOMPLET')", name="ck_eer_decisions_resultat"),
    )

    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_dossiers.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    resultat: Mapped[str] = mapped_column(String(15))
    conformite_physique: Mapped[str] = mapped_column(String(15))
    conformite_systeme: Mapped[str] = mapped_column(String(15))
    conformite_coherence: Mapped[str] = mapped_column(String(15))
    explication: Mapped[list] = mapped_column(JSONB, default=list)
    parametres: Mapped[dict] = mapped_column(JSONB, default=dict)
    decide_par_id: Mapped[uuid.UUID | None] = _user_fk(ondelete="RESTRICT")
    decide_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EerHistorique(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "eer_historique"

    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_dossiers.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    de_statut: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vers_statut: Mapped[str | None] = mapped_column(String(20), nullable=True)
    etape: Mapped[str | None] = mapped_column(String(20), nullable=True)
    version: Mapped[int] = mapped_column(Integer)
    motif: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    acteur_id: Mapped[uuid.UUID | None] = _user_fk(ondelete="RESTRICT")
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class EerVisa(UUIDPrimaryKeyMixin, Base):
    """« Tableau des signataires » des fiches = visas internes (≠ signataires du compte)."""

    __tablename__ = "eer_visas"

    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("eer_dossiers.id"), index=True)
    dossier_partie_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("eer_dossier_parties.id", "SET NULL"), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("users.id"))
    fonction: Mapped[str] = mapped_column(String(120))
    avis: Mapped[str] = mapped_column(String(40))
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer)
    vise_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
