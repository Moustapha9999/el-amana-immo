"""Studio d'intégration API — applications clientes (Phase 2) et fournisseurs d'API externes (Phase 4).

Aucune donnée d'authentification : une fiche ne permet à aucune application de s'authentifier
ni d'appeler l'API. Les droits « approuvés » sont une configuration, pas une autorisation effective.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

CLIENT_STATUTS = ("brouillon", "en_preparation", "active", "suspendue", "archivee")
ENVIRONNEMENTS = ("DEV", "TEST")
GRANT_STATUTS = ("demandee", "en_attente", "approuvee", "refusee", "revoquee", "retiree")
FOURNISSEUR_STATUTS = ("brouillon", "a_valider", "valide", "suspendu", "archive")
OPERATION_ORIGINES = ("openapi", "manuelle")
OPERATION_STATUTS = ("active", "archivee")
SPEC_FORMATS = ("json", "yaml")
DESTINATION_STATUTS = ("brouillon", "a_valider", "active", "suspendue", "archivee")
EXECUTION_STATUTS = (
    "succes", "http_erreur", "refuse_securite", "timeout", "trop_volumineux",
    "dns", "tls", "redirection_refusee", "reponse_invalide", "secret_requis", "quota",
)
ALERTE_STATUTS = ("nouvelle", "en_cours", "resolue", "ignoree")
ALERTE_TYPES = (
    "echecs_consecutifs", "taux_erreur", "latence", "non_testee",
    "destination_suspendue", "refus_securite",
)


def _dans(colonne: str, valeurs: tuple[str, ...]) -> str:
    return f"{colonne} IN (" + ", ".join(f"'{v}'" for v in valeurs) + ")"


class IntegrationClient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "integration_clients"
    __table_args__ = (
        CheckConstraint(_dans("statut", CLIENT_STATUTS), name="ck_integration_clients_statut"),
        CheckConstraint(_dans("environnement", ENVIRONNEMENTS), name="ck_integration_clients_environnement"),
        UniqueConstraint("code", name="uq_integration_clients_code"),
        Index(
            "uq_integration_clients_nom_env",
            "nom_normalise",
            "environnement",
            unique=True,
            postgresql_where=text("statut <> 'archivee'"),
        ),
    )

    code: Mapped[str] = mapped_column(String(32))
    nom: Mapped[str] = mapped_column(String(120))
    nom_normalise: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    org_entite_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    contact_technique: Mapped[str | None] = mapped_column(String(160), nullable=True)
    environnement: Mapped[str] = mapped_column(String(10), index=True)
    finalite: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[str] = mapped_column(String(20), default="brouillon", server_default="brouillon", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    motif_archivage: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntegrationClientGrant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Une opération du catalogue demandée par une application : demande puis décision explicite."""

    __tablename__ = "integration_client_grants"
    __table_args__ = (
        CheckConstraint(_dans("statut", GRANT_STATUTS), name="ck_integration_client_grants_statut"),
        UniqueConstraint("client_id", "operation_id", name="uq_integration_client_grants_operation"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_clients.id", ondelete="RESTRICT"), index=True
    )
    operation_id: Mapped[str] = mapped_column(String(160))
    methode: Mapped[str] = mapped_column(String(10))
    chemin: Mapped[str] = mapped_column(String(300))
    permissions: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    exigence_permissions: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[str] = mapped_column(String(20), default="demandee", server_default="demandee", index=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    demande_par_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decide_par_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motif: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntegrationClientGrantEvent(Base, UUIDPrimaryKeyMixin):
    """Historique immuable : chaque changement de statut d'une demande de droit."""

    __tablename__ = "integration_client_grant_events"

    grant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_client_grants.id", ondelete="RESTRICT"), index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_clients.id", ondelete="RESTRICT"), index=True
    )
    operation_id: Mapped[str] = mapped_column(String(160))
    ancien_statut: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nouveau_statut: Mapped[str] = mapped_column(String(20))
    motif: Mapped[str | None] = mapped_column(Text, nullable=True)
    acteur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)


# ------------------------------------------------------------------ fournisseurs d'API externes (Phase 4)
# Configuration seulement : aucune donnée d'authentification, aucune URL appelée.


class IntegrationFournisseur(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "integration_fournisseurs"
    __table_args__ = (
        CheckConstraint(_dans("statut", FOURNISSEUR_STATUTS), name="ck_integration_fournisseurs_statut"),
        CheckConstraint(_dans("environnement", ENVIRONNEMENTS), name="ck_integration_fournisseurs_environnement"),
        UniqueConstraint("code", name="uq_integration_fournisseurs_code"),
        Index(
            "uq_integration_fournisseurs_nom_env",
            "nom_normalise",
            "environnement",
            unique=True,
            postgresql_where=text("statut <> 'archive'"),
        ),
    )

    code: Mapped[str] = mapped_column(String(32))
    nom: Mapped[str] = mapped_column(String(120))
    nom_normalise: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    org_entite_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    responsable_interne: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contact_technique: Mapped[str | None] = mapped_column(String(160), nullable=True)
    environnement: Mapped[str] = mapped_column(String(10), index=True)
    url_base: Mapped[str | None] = mapped_column(String(300), nullable=True)
    documentation: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[str] = mapped_column(String(20), default="brouillon", server_default="brouillon", index=True)
    motif_statut: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    valide_par_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    valide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    motif_archivage: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntegrationFournisseurSpec(Base, UUIDPrimaryKeyMixin):
    """Version importée d'une spécification OpenAPI (fichier fourni par un utilisateur, jamais une URL)."""

    __tablename__ = "integration_fournisseur_specs"
    __table_args__ = (
        CheckConstraint(_dans("format", SPEC_FORMATS), name="ck_integration_fournisseur_specs_format"),
        UniqueConstraint("fournisseur_id", "numero", name="uq_integration_fournisseur_specs_numero"),
        UniqueConstraint("fournisseur_id", "empreinte", name="uq_integration_fournisseur_specs_empreinte"),
    )

    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_fournisseurs.id", ondelete="RESTRICT"), index=True
    )
    numero: Mapped[int] = mapped_column(Integer)
    format: Mapped[str] = mapped_column(String(10))
    nom_fichier: Mapped[str] = mapped_column(String(255))
    taille: Mapped[int] = mapped_column(Integer)
    empreinte: Mapped[str] = mapped_column(String(64))
    openapi_version: Mapped[str] = mapped_column(String(20))
    titre: Mapped[str] = mapped_column(String(300))
    version_api: Mapped[str] = mapped_column(String(100))
    document: Mapped[dict] = mapped_column(JSONB)
    resume: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    avertissements: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    importe_par_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)


class IntegrationFournisseurOperation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Opération d'un fournisseur : issue d'une version de spécification, ou déclarée manuellement."""

    __tablename__ = "integration_fournisseur_operations"
    __table_args__ = (
        CheckConstraint(_dans("origine", OPERATION_ORIGINES), name="ck_integration_fournisseur_operations_origine"),
        CheckConstraint(_dans("statut", OPERATION_STATUTS), name="ck_integration_fournisseur_operations_statut"),
        CheckConstraint(
            "(origine = 'openapi') = (spec_id IS NOT NULL)", name="ck_integration_fournisseur_operations_spec"
        ),
        UniqueConstraint("spec_id", "methode", "chemin", name="uq_integration_fournisseur_operations_spec"),
        Index(
            "uq_integration_fournisseur_operations_manuelle",
            "fournisseur_id",
            "methode",
            "chemin",
            unique=True,
            postgresql_where=text("origine = 'manuelle' AND statut = 'active'"),
        ),
    )

    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_fournisseurs.id", ondelete="RESTRICT"), index=True
    )
    spec_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_fournisseur_specs.id", ondelete="RESTRICT"), nullable=True,
        index=True,
    )
    origine: Mapped[str] = mapped_column(String(10))
    statut: Mapped[str] = mapped_column(String(10), default="active", server_default="active")
    methode: Mapped[str] = mapped_column(String(10))
    chemin: Mapped[str] = mapped_column(String(300))
    operation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    nom: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    deprecie: Mapped[bool] = mapped_column(default=False, server_default="false")
    parametres: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    entetes: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    corps: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reponses: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    authentification: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    configuration: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    empreinte: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class IntegrationDestination(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Hôte TEST explicitement approuvé : l'URL d'appel est construite ici, jamais saisie à l'exécution."""

    __tablename__ = "integration_destinations"
    __table_args__ = (
        CheckConstraint(_dans("statut", DESTINATION_STATUTS), name="ck_integration_destinations_statut"),
        CheckConstraint("environnement = 'TEST'", name="ck_integration_destinations_environnement"),
        CheckConstraint("protocole = 'https'", name="ck_integration_destinations_protocole"),
        UniqueConstraint("code", name="uq_integration_destinations_code"),
        Index(
            "uq_integration_destinations_nom_fourn",
            "nom_normalise",
            "fournisseur_id",
            unique=True,
            postgresql_where=text("statut <> 'archivee'"),
        ),
    )

    code: Mapped[str] = mapped_column(String(32))
    nom: Mapped[str] = mapped_column(String(120))
    nom_normalise: Mapped[str] = mapped_column(String(120))
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_fournisseurs.id", ondelete="RESTRICT"), index=True
    )
    environnement: Mapped[str] = mapped_column(String(10), default="TEST", server_default="TEST")
    protocole: Mapped[str] = mapped_column(String(10), default="https", server_default="https")
    hotes: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    ports: Mapped[list] = mapped_column(JSONB, default=list, server_default="[443]")
    methodes: Mapped[list] = mapped_column(JSONB, default=list, server_default='["GET","HEAD"]')
    operations: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    statut: Mapped[str] = mapped_column(String(20), default="brouillon", server_default="brouillon", index=True)
    motif_statut: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    valide_par_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    valide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    motif_archivage: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntegrationExecution(Base, UUIDPrimaryKeyMixin):
    """Résultat d'un test explicite (Phase 5) : pas de secret, pas de corps complet."""

    __tablename__ = "integration_executions"
    __table_args__ = (
        CheckConstraint(_dans("statut", EXECUTION_STATUTS), name="ck_integration_executions_statut"),
        Index("ix_integration_executions_fourn_debut", "fournisseur_id", "started_at"),
        Index("ix_integration_executions_dest_debut", "destination_id", "started_at"),
    )

    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_fournisseurs.id", ondelete="RESTRICT"), index=True
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_fournisseur_operations.id", ondelete="RESTRICT"), index=True
    )
    destination_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_destinations.id", ondelete="RESTRICT"), index=True
    )
    environnement: Mapped[str] = mapped_column(String(10), default="TEST", server_default="TEST")
    methode: Mapped[str] = mapped_column(String(10))
    chemin: Mapped[str] = mapped_column(String(400))
    hote: Mapped[str] = mapped_column(String(253))
    port: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)
    duree_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    statut: Mapped[str] = mapped_column(String(30), index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    erreur_categorie: Mapped[str | None] = mapped_column(String(40), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    controles: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    limites: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    reponse_resume: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntegrationAlerte(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Alerte de supervision (Phase 6) : dédupliquée tant qu'elle n'est pas close."""

    __tablename__ = "integration_alertes"
    __table_args__ = (
        CheckConstraint(_dans("statut", ALERTE_STATUTS), name="ck_integration_alertes_statut"),
        CheckConstraint(_dans("type", ALERTE_TYPES), name="ck_integration_alertes_type"),
        Index(
            "uq_integration_alertes_ouverte",
            "type",
            "cle_dedup",
            unique=True,
            postgresql_where=text("statut IN ('nouvelle', 'en_cours')"),
        ),
    )

    type: Mapped[str] = mapped_column(String(40), index=True)
    statut: Mapped[str] = mapped_column(String(20), default="nouvelle", server_default="nouvelle", index=True)
    cle_dedup: Mapped[str] = mapped_column(String(200))
    fournisseur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_fournisseurs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    destination_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_destinations.id", ondelete="SET NULL"), nullable=True
    )
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_fournisseur_operations.id", ondelete="SET NULL"), nullable=True
    )
    message: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    occurences: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    derniere_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    resolue_par_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolue_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
