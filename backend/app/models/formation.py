"""Formation & Sensibilisation (Conformité) — sessions, participants, présences, référentiels.

Réutilise users, agences et audit_logs : aucune table CORE dupliquée. Un employé formé n'est
pas un utilisateur BEA DIGITAL (fiche légère : nom, prénom, fonction, entité, contact).
Le périmètre se déduit de l'entité ; il est figé sur chaque participation pour un reporting
historique fidèle.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

DOMAINES_REFERENTIEL = ("THEME", "FORMATEUR", "LIEU", "FONCTION", "PERIMETRE")
STATUTS_SESSION = ("PLANIFIEE", "REALISEE", "CLOTUREE", "ANNULEE", "ARCHIVEE")
PRESENCES = ("PRESENT", "ABSENT")


def _fk(cible: str, ondelete: str = "RESTRICT") -> ForeignKey:
    return ForeignKey(cible, ondelete=ondelete)


def _user_fk() -> Mapped:
    return mapped_column(UUID(as_uuid=True), _fk("users.id", "SET NULL"), nullable=True)


class FormationReferentiel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Listes déroulantes : thèmes, formateurs, lieux, fonctions, périmètres."""

    __tablename__ = "formation_referentiels"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("domaine", "cle", name="uq_formation_referentiels_domaine_cle"),
        CheckConstraint(
            "domaine IN ('THEME','FORMATEUR','LIEU','FONCTION','PERIMETRE')",
            name="ck_formation_referentiels_domaine",
        ),
    )

    domaine: Mapped[str] = mapped_column(String(20), index=True)
    libelle: Mapped[str] = mapped_column(String(200))
    cle: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_by_id: Mapped[uuid.UUID | None] = _user_fk()


class FormationEntite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Entité (agence, service du siège) → périmètre (et lieu par défaut)."""

    __tablename__ = "formation_entites"
    __mapper_args__ = {"eager_defaults": True}

    libelle: Mapped[str] = mapped_column(String(200))
    cle: Mapped[str] = mapped_column(String(200), unique=True)
    perimetre_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("formation_referentiels.id"), index=True)
    lieu_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("formation_referentiels.id", "SET NULL"), nullable=True)
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("agences.id", "SET NULL"), nullable=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_by_id: Mapped[uuid.UUID | None] = _user_fk()

    perimetre: Mapped[FormationReferentiel] = relationship(foreign_keys=[perimetre_id], lazy="joined")
    lieu: Mapped[FormationReferentiel | None] = relationship(foreign_keys=[lieu_id], lazy="joined")


class FormationImport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "formation_imports"
    __table_args__ = (
        CheckConstraint("statut IN ('ANALYSE','IMPORTE','ABANDONNE')", name="ck_formation_imports_statut"),
    )

    fichier_nom: Mapped[str] = mapped_column(String(255))
    fichier_sha256: Mapped[str] = mapped_column(String(64), index=True)
    statut: Mapped[str] = mapped_column(String(20), default="ANALYSE")
    nb_lignes: Mapped[int] = mapped_column(Integer, default=0)
    analyse: Mapped[dict] = mapped_column(JSONB, default=dict)
    resultat: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    importe_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    importe_par_id: Mapped[uuid.UUID | None] = _user_fk()


class FormationEmploye(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "formation_employes"
    __mapper_args__ = {"eager_defaults": True}

    nom: Mapped[str] = mapped_column(String(120))
    prenom: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Jetons normalisés triés (« ahmed mohamed ») : détection des doublons quel que soit l'ordre.
    cle_identite: Mapped[str] = mapped_column(String(260), index=True)
    fonction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("formation_referentiels.id", "SET NULL"), nullable=True, index=True)
    entite_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("formation_entites.id", "SET NULL"), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telephone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    motif_desactivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="MANUEL")
    import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("formation_imports.id", "SET NULL"), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_by_id: Mapped[uuid.UUID | None] = _user_fk()

    fonction: Mapped[FormationReferentiel | None] = relationship(lazy="joined")
    entite: Mapped[FormationEntite | None] = relationship(lazy="joined")


class FormationSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "formation_sessions"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "statut IN ('PLANIFIEE','REALISEE','CLOTUREE','ANNULEE','ARCHIVEE')",
            name="ck_formation_sessions_statut",
        ),
    )

    reference: Mapped[str] = mapped_column(String(20), unique=True)
    intitule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_session: Mapped[date] = mapped_column(Date, index=True)
    lieu_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("formation_referentiels.id"), index=True)
    statut: Mapped[str] = mapped_column(String(20), default="PLANIFIEE", index=True)
    statut_precedent: Mapped[str | None] = mapped_column(String(20), nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    motif_annulation: Mapped[str | None] = mapped_column(Text, nullable=True)
    presences_saisies_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    presences_saisies_par_id: Mapped[uuid.UUID | None] = _user_fk()
    cloturee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cloturee_par_id: Mapped[uuid.UUID | None] = _user_fk()
    source: Mapped[str] = mapped_column(String(20), default="MANUEL")
    import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("formation_imports.id", "SET NULL"), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_by_id: Mapped[uuid.UUID | None] = _user_fk()

    lieu: Mapped[FormationReferentiel] = relationship(lazy="joined")
    themes: Mapped[list[FormationSessionTheme]] = relationship(
        cascade="all, delete-orphan", order_by="FormationSessionTheme.ordre", lazy="selectin")
    formateurs: Mapped[list[FormationSessionFormateur]] = relationship(
        cascade="all, delete-orphan", order_by="FormationSessionFormateur.ordre", lazy="selectin")
    participants: Mapped[list[FormationParticipant]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="FormationParticipant.ordre")


class FormationSessionTheme(Base):
    __tablename__ = "formation_session_themes"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("formation_sessions.id", "CASCADE"), primary_key=True)
    theme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("formation_referentiels.id"), primary_key=True, index=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)

    theme: Mapped[FormationReferentiel] = relationship(lazy="joined")


class FormationSessionFormateur(Base):
    __tablename__ = "formation_session_formateurs"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("formation_sessions.id", "CASCADE"), primary_key=True)
    formateur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("formation_referentiels.id"), primary_key=True, index=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)

    formateur: Mapped[FormationReferentiel] = relationship(lazy="joined")


class FormationParticipant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "formation_participants"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("session_id", "employe_id", name="uq_formation_participants_session_employe"),
        CheckConstraint("presence IS NULL OR presence IN ('PRESENT','ABSENT')", name="ck_formation_participants_presence"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("formation_sessions.id", "CASCADE"), index=True)
    employe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("formation_employes.id"), index=True)
    presence: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    # Instantané au moment de la session (l'employé peut changer d'entité ensuite).
    fonction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("formation_referentiels.id", "SET NULL"), nullable=True)
    entite_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("formation_entites.id", "SET NULL"), nullable=True, index=True)
    perimetre_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("formation_referentiels.id", "SET NULL"), nullable=True, index=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    presence_saisie_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    presence_saisie_par_id: Mapped[uuid.UUID | None] = _user_fk()

    session: Mapped[FormationSession] = relationship(back_populates="participants")
    employe: Mapped[FormationEmploye] = relationship(lazy="joined")


class FormationCompteur(Base):
    __tablename__ = "formation_compteurs"

    annee: Mapped[int] = mapped_column(Integer, primary_key=True)
    dernier: Mapped[int] = mapped_column(Integer, default=0)
