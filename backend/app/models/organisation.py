import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Niveaux de l'organigramme BEA. Les agences physiques restent dans `agences` (jamais ici).
TYPES_ENTITE = (
    "CONSEIL",
    "COMITE",
    "DIRECTION_GENERALE",
    "DIRECTION",
    "DEPARTEMENT",
    "SERVICE",
    "SECTION",
    "CELLULE",
)
TYPES_AFFECTATION = ("PRINCIPALE", "SECONDAIRE", "INTERIM")
# Périmètre de données accordé par une affectation. PERSONNEL par défaut : aucun droit implicite.
PERIMETRES = ("PERSONNEL", "ENTITE", "ENTITE_ET_SOUS_ENTITES")


def _in(colonne: str, valeurs: tuple[str, ...]) -> str:
    return f"{colonne} IN ({','.join(repr(v) for v in valeurs)})"


class Direction(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Legacy (une ligne historique). Les directions sont des entités `departements` de type DIRECTION."""

    __tablename__ = "directions"

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    libelle: Mapped[str] = mapped_column(String(255))


class Departement(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Référentiel organisationnel central BEA DIGITAL (tous niveaux de l'organigramme).

    La table garde son nom historique `departements` : toutes les clés étrangères existantes
    (immobilisations, achats, demandes, GED, centres de coût) pointent donc vers l'entité
    centrale, quel que soit son niveau. Désactiver = `is_active=false`, jamais de suppression
    d'une entité référencée (FK sans cascade).
    """

    __tablename__ = "departements"
    __table_args__ = (
        CheckConstraint(_in("type_entite", TYPES_ENTITE), name="ck_departements_type_entite"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_departements_parent_soi"),
        Index(
            "uq_departements_parent_cle",
            text("COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "cle",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    libelle: Mapped[str] = mapped_column(String(255))
    direction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("directions.id"), nullable=True
    )
    type_entite: Mapped[str] = mapped_column(String(30), default="DEPARTEMENT", server_default="DEPARTEMENT", index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Calculée par trigger (`org_cle(libelle)`) : jamais écrite par le code.
    cle: Mapped[str] = mapped_column(String(255), server_default="")
    sigle: Mapped[str | None] = mapped_column(String(40), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Variantes de libellé (normalisées par `org_cle`) reconnues dans les anciennes saisies texte.
    alias: Mapped[list[str]] = mapped_column(ARRAY(String(255)), default=list, server_default="{}")
    a_confirmer: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    note_confirmation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="MANUEL", server_default="MANUEL")
    metadonnees: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


OrgEntite = Departement


class OrgPoste(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Poste / fonction d'une entité. Distinct de la personne (titulaire) et du rôle applicatif."""

    __tablename__ = "org_postes"
    __table_args__ = (
        CheckConstraint("effectif_prevu IS NULL OR effectif_prevu > 0", name="ck_org_postes_effectif"),
    )

    entite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id", ondelete="RESTRICT"), index=True
    )
    intitule: Mapped[str] = mapped_column(String(200))
    cle: Mapped[str] = mapped_column(String(200), server_default="")
    est_responsable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    effectif_prevu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    titulaire_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actif: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    a_confirmer: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    note_confirmation: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    source: Mapped[str] = mapped_column(String(40), default="MANUEL", server_default="MANUEL")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class OrgAffectation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Rattachement d'un compte utilisateur à une entité (historisé : une affectation close
    n'est jamais réécrite, une nouvelle ligne la remplace)."""

    __tablename__ = "org_affectations"
    __table_args__ = (
        CheckConstraint(_in("type_affectation", TYPES_AFFECTATION), name="ck_org_affectations_type"),
        CheckConstraint(_in("perimetre", PERIMETRES), name="ck_org_affectations_perimetre"),
        CheckConstraint("date_fin IS NULL OR date_fin >= date_debut", name="ck_org_affectations_dates"),
        Index(
            "uq_org_affectations_principale",
            "user_id",
            unique=True,
            postgresql_where=text("actif AND type_affectation = 'PRINCIPALE'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    entite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id", ondelete="RESTRICT"), index=True
    )
    poste_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_postes.id", ondelete="SET NULL"), nullable=True
    )
    type_affectation: Mapped[str] = mapped_column(String(20), default="PRINCIPALE")
    perimetre: Mapped[str] = mapped_column(String(30), default="PERSONNEL", server_default="PERSONNEL")
    date_debut: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))
    date_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", index=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class CentreCout(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "centres_cout"

    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    libelle: Mapped[str] = mapped_column(String(255))
    departement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id"), nullable=True
    )


class Fournisseur(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "fournisseurs"

    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    raison_sociale: Mapped[str] = mapped_column(String(255))
    nom_commercial: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type_fournisseur: Mapped[str] = mapped_column(String(40), default="FOURNITURE", index=True)
    contact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_fonction: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telephone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    telephone_secondaire: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    site_web: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adresse: Mapped[str | None] = mapped_column(Text, nullable=True)
    ville: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    pays: Mapped[str] = mapped_column(String(80), default="Mauritanie")
    nif: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    rc: Mapped[str | None] = mapped_column(String(60), nullable=True)
    devise_defaut: Mapped[str] = mapped_column(String(10), default="MRU")
    mode_paiement_defaut: Mapped[str | None] = mapped_column(String(80), nullable=True)
    delai_paiement_jours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conditions_commerciales: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
