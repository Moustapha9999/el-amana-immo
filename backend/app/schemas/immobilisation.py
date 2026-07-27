from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, computed_field, field_validator

from app.models.enums import ModeAmortissement, PeriodiciteAmortissement, StatutImmobilisation, TypeImmobilisation
from app.schemas.common import ORMModel
from app.services.amortissement_rate import taux_lineaire_from_duree_annees


class CategorieCreate(BaseModel):
    code: str
    famille: str
    sous_famille: str | None = None
    type_immobilisation: TypeImmobilisation
    compte_immobilisation: str
    compte_amortissement: str | None = None
    compte_dotation: str | None = None
    comptes_amortissement_alternatifs: str | None = None
    amortissable: bool = False
    duree_annees_defaut: int | None = None
    taux_lineaire_defaut: Decimal | None = None
    mode_amortissement_defaut: ModeAmortissement = ModeAmortissement.LINEAIRE
    periodicite_defaut: str = "annuel"
    prorata_temporis: bool = True
    journal_code: str = "OD"


class CategorieUpdate(BaseModel):
    famille: str | None = None
    sous_famille: str | None = None
    compte_immobilisation: str | None = None
    compte_amortissement: str | None = None
    compte_dotation: str | None = None
    comptes_amortissement_alternatifs: str | None = None
    amortissable: bool | None = None
    duree_annees_defaut: int | None = Field(default=None, ge=0, le=100)
    taux_lineaire_defaut: Decimal | None = Field(default=None, ge=0, le=100)
    mode_amortissement_defaut: ModeAmortissement | None = None
    periodicite_defaut: str | None = None
    prorata_temporis: bool | None = None
    journal_code: str | None = None
    is_active: bool | None = None


class CategorieRead(CategorieCreate, ORMModel):
    id: UUID
    is_active: bool

    @computed_field
    @property
    def taux_lineaire_calcule(self) -> Decimal | None:
        # Affiche le taux banque stocké ; fallback 100/durée uniquement si absent
        if self.taux_lineaire_defaut is not None:
            return self.taux_lineaire_defaut
        return taux_lineaire_from_duree_annees(self.duree_annees_defaut)


class ImmobilisationBase(BaseModel):
    code_inventaire: str = Field(max_length=50)
    numero_serie: str | None = Field(default=None, max_length=80)
    numero_facture: str | None = Field(default=None, max_length=80)
    quantite: int = Field(default=1, ge=1)
    designation: str = Field(max_length=255)
    description: str | None = None
    observations: str | None = None
    categorie_id: UUID
    agence_id: UUID | None = None
    departement_id: UUID | None = None
    centre_cout_id: UUID | None = None
    responsable_id: UUID | None = None
    fournisseur_id: UUID | None = None
    date_acquisition: date
    date_mise_en_service: date | None = None
    # Date de comptabilisation d'acquisition (obligatoire à la saisie — ImmobilisationCreate)
    date_comptabilisation: date | None = None
    date_fin: date | None = None
    # Peut être négative (reclassements / régularisations banque)
    valeur_brute: Decimal
    valeur_residuelle: Decimal = Field(default=Decimal("0"), ge=0)
    duree_annees: int | None = Field(default=None, ge=0, le=100)
    duree_mois: int = Field(default=0, ge=0)
    periodicite: PeriodiciteAmortissement = PeriodiciteAmortissement.ANNUEL
    prorata_temporis: bool = True
    mode_amortissement: ModeAmortissement = ModeAmortissement.LINEAIRE
    # Taux annuel (%) — défaut catégorie, surcharge possible par utilisateur autorisé
    taux: Decimal | None = Field(default=None, ge=0, le=100)
    devise: str = Field(default="MRU", max_length=3)
    statut: StatutImmobilisation = StatutImmobilisation.BROUILLON
    compte_immobilisation: str | None = None
    compte_amortissement: str | None = None
    compte_dotation: str | None = None
    localisation: str | None = None

    @field_validator("date_mise_en_service")
    @classmethod
    def mise_en_service_after_acquisition(cls, v: date | None, info) -> date | None:
        if v is None:
            return v
        acquisition = info.data.get("date_acquisition")
        if acquisition and v < acquisition:
            raise ValueError("date_mise_en_service doit être >= date_acquisition")
        return v

    @field_validator("date_comptabilisation")
    @classmethod
    def comptabilisation_after_acquisition(cls, v: date | None, info) -> date | None:
        if v is None:
            return v
        acquisition = info.data.get("date_acquisition")
        if acquisition and v < acquisition:
            raise ValueError("date_comptabilisation doit être >= date_acquisition")
        return v


class ImmobilisationCreate(ImmobilisationBase):
    """Saisie d'acquisition — date de comptabilisation obligatoire (note banque)."""

    date_comptabilisation: date
    # Si omis : généré automatiquement (ex. AAI-2026-001) selon la nature + année d'acquisition
    code_inventaire: str | None = Field(default=None, max_length=50)

    @field_validator("code_inventaire")
    @classmethod
    def empty_code_as_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None


class NextCodeInventaireResponse(BaseModel):
    code_inventaire: str
    prefix: str
    annee: int


class ImmobilisationUpdate(BaseModel):
    designation: str | None = Field(default=None, max_length=255)
    description: str | None = None
    observations: str | None = None
    code_inventaire: str | None = Field(default=None, max_length=50)
    numero_serie: str | None = None
    numero_facture: str | None = None
    quantite: int | None = Field(default=None, ge=1)
    categorie_id: UUID | None = None
    agence_id: UUID | None = None
    departement_id: UUID | None = None
    centre_cout_id: UUID | None = None
    fournisseur_id: UUID | None = None
    date_acquisition: date | None = None
    date_mise_en_service: date | None = None
    date_comptabilisation: date | None = None
    date_fin: date | None = None
    statut: StatutImmobilisation | None = None
    valeur_brute: Decimal | None = None
    valeur_residuelle: Decimal | None = Field(default=None, ge=0)
    duree_annees: int | None = Field(default=None, ge=0, le=100)
    duree_mois: int | None = Field(default=None, ge=0)
    periodicite: PeriodiciteAmortissement | None = None
    prorata_temporis: bool | None = None
    mode_amortissement: ModeAmortissement | None = None
    taux: Decimal | None = Field(default=None, ge=0, le=100)
    compte_immobilisation: str | None = None
    compte_amortissement: str | None = None
    compte_dotation: str | None = None
    localisation: str | None = None
    is_active: bool | None = None


class ImmobilisationRead(ImmobilisationBase, ORMModel):
    id: UUID
    is_active: bool
    qr_code_data: str | None = None
    barcode_data: str | None = None
    categorie: CategorieRead | None = None


class PieceJointeRead(ORMModel):
    id: UUID
    immobilisation_id: UUID
    filename: str
    mime_type: str | None
    size_bytes: int
    is_photo: bool
    type_piece: str
    date_journee: date
    reference: str | None = None
    libelle: str | None = None
    montant: Decimal | None = None
    created_at: datetime | None = None
    code_inventaire: str | None = None
    designation: str | None = None


class PieceJointeArchiveRead(PieceJointeRead):
    """Liste archive journée — mêmes champs + libellés immo."""

    pass


class InventaireScanCreate(BaseModel):
    code_scanne: str
    localisation: str | None = None


class InventaireScanRead(ORMModel):
    id: UUID
    immobilisation_id: UUID | None
    code_scanne: str
    valide: bool
    localisation: str | None
    created_at: datetime | None = None
    code_inventaire: str | None = None
    designation: str | None = None


class QrCodeResponse(BaseModel):
    payload: str
    image_base64: str
