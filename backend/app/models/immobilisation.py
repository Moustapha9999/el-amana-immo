import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ModeAmortissement, StatutImmobilisation, TypeImmobilisation, TypePieceComptable
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CategorieImmobilisation(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Type d'immobilisation El Amana (référentiel métier + paramètres amortissement par défaut)."""

    __tablename__ = "categories_immobilisation"

    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    famille: Mapped[str] = mapped_column(String(120))
    sous_famille: Mapped[str | None] = mapped_column(String(120), nullable=True)
    type_immobilisation: Mapped[TypeImmobilisation] = mapped_column(Enum(TypeImmobilisation))

    compte_immobilisation: Mapped[str] = mapped_column(String(20), index=True)
    compte_amortissement: Mapped[str | None] = mapped_column(String(20), nullable=True)
    compte_dotation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    comptes_amortissement_alternatifs: Mapped[str | None] = mapped_column(String(120), nullable=True)
    amortissable: Mapped[bool] = mapped_column(Boolean, default=False)
    duree_annees_defaut: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taux_lineaire_defaut: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    mode_amortissement_defaut: Mapped[ModeAmortissement] = mapped_column(
        Enum(ModeAmortissement), default=ModeAmortissement.LINEAIRE
    )
    periodicite_defaut: Mapped[str] = mapped_column(String(20), default="annuel")
    prorata_temporis: Mapped[bool] = mapped_column(Boolean, default=True)
    journal_code: Mapped[str] = mapped_column(String(10), default="OD")

    immobilisations: Mapped[list["Immobilisation"]] = relationship(back_populates="categorie")


class Immobilisation(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "immobilisations"

    code_inventaire: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    numero_serie: Mapped[str | None] = mapped_column(String(80), nullable=True)
    numero_facture: Mapped[str | None] = mapped_column(String(80), nullable=True)
    quantite: Mapped[int] = mapped_column(Integer, default=1)
    designation: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)

    categorie_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories_immobilisation.id"), nullable=True
    )
    agence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agences.id"))
    departement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id"), nullable=True
    )
    centre_cout_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("centres_cout.id"), nullable=True
    )
    responsable_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    fournisseur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id"), nullable=True
    )

    date_acquisition: Mapped[date] = mapped_column(Date)
    date_mise_en_service: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_comptabilisation: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_fin: Mapped[date | None] = mapped_column(Date, nullable=True)

    valeur_brute: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    valeur_residuelle: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    duree_annees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duree_mois: Mapped[int] = mapped_column(Integer, default=60)
    periodicite: Mapped[str] = mapped_column(String(20), default="annuel")
    prorata_temporis: Mapped[bool] = mapped_column(Boolean, default=True)
    mode_amortissement: Mapped[ModeAmortissement] = mapped_column(
        Enum(ModeAmortissement), default=ModeAmortissement.LINEAIRE
    )
    taux: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    devise: Mapped[str] = mapped_column(String(3), default="MRU")
    statut: Mapped[StatutImmobilisation] = mapped_column(
        Enum(StatutImmobilisation), default=StatutImmobilisation.BROUILLON
    )

    categorie: Mapped[CategorieImmobilisation | None] = relationship(back_populates="immobilisations")

    compte_immobilisation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    compte_amortissement: Mapped[str | None] = mapped_column(String(20), nullable=True)
    compte_dotation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    qr_code_data: Mapped[str | None] = mapped_column(String(512), nullable=True)
    barcode_data: Mapped[str | None] = mapped_column(String(80), nullable=True)
    localisation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class PieceJointe(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Pièce comptable (facture, PV, …) archivée par journée et rattachée à une immo."""

    __tablename__ = "pieces_jointes"

    immobilisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("immobilisations.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    is_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    type_piece: Mapped[TypePieceComptable] = mapped_column(
        Enum(
            TypePieceComptable,
            name="typepiececomptable",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        default=TypePieceComptable.FACTURE,
        index=True,
    )
    date_journee: Mapped[date] = mapped_column(Date, index=True)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    libelle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    montant: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    immobilisation: Mapped["Immobilisation"] = relationship(foreign_keys=[immobilisation_id])


class InventaireScan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "inventaire_scans"

    immobilisation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("immobilisations.id"), nullable=True
    )
    code_scanne: Mapped[str] = mapped_column(String(80), index=True)
    valide: Mapped[bool] = mapped_column(Boolean, default=False)
    localisation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scanned_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    immobilisation: Mapped["Immobilisation | None"] = relationship(foreign_keys=[immobilisation_id])
