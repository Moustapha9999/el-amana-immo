"""Schémas API — module Archivage."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ArchiveDossierCreate(BaseModel):
    annee: int = Field(ge=1990, le=2100)
    libelle: str | None = None


class ArchiveFichierRead(ORMModel):
    id: UUID
    dossier_id: UUID
    kind: str
    filename: str
    mime_type: str | None
    size_bytes: int
    nature_code: str | None
    sheet_names: list | None
    parse_status: str
    parse_error: str | None
    lines_count: int
    created_at: datetime


class ArchiveDossierRead(ORMModel):
    id: UUID
    annee: int
    libelle: str | None
    created_at: datetime
    nb_fichiers: int = 0
    nb_lignes: int = 0
    natures: list[str] = Field(default_factory=list)


class ArchiveDossierDetailRead(ArchiveDossierRead):
    fichiers: list[ArchiveFichierRead] = Field(default_factory=list)


class ArchiveLigneRead(ORMModel):
    id: UUID
    fichier_id: UUID
    categorie_code: str
    feuille: str | None
    row_number: int
    date_acquisition: date | None
    quantite: int
    designation: str
    valeur_brute: Decimal
    taux: Decimal | None
    amt_n1: Decimal
    dotation: Decimal
    amt_fin: Decimal
    vnc: Decimal
    agence_label: str | None
    is_report: bool
    source_kind: str


class ArchiveTotauxRead(BaseModel):
    valeur_brute: Decimal = Decimal("0")
    amt_n1: Decimal = Decimal("0")
    dotation: Decimal = Decimal("0")
    amt_fin: Decimal = Decimal("0")
    vnc: Decimal = Decimal("0")
    nb_lignes: int = 0


class ArchiveExerciceSectionRead(BaseModel):
    """Bloc année comme le tableau banque (ouvertures + S/T cumulatif)."""

    annee: int
    label: str
    ouverture: ArchiveTotauxRead | None = None
    lignes: list[ArchiveLigneRead] = Field(default_factory=list)
    totaux: ArchiveTotauxRead  # S/T cumulatif fin d'année


class ArchiveNatureGroupeRead(BaseModel):
    nature_code: str
    nature_label: str
    lignes: list[ArchiveLigneRead]
    sections: list[ArchiveExerciceSectionRead] = Field(default_factory=list)
    totaux: ArchiveTotauxRead  # total général (somme des lignes actives)


class ArchiveAcquisitionsRead(BaseModel):
    annee: int
    groupes: list[ArchiveNatureGroupeRead]
    totaux: ArchiveTotauxRead


class ArchiveClotureRequest(BaseModel):
    annee: int = Field(ge=1990, le=2100)
    force: bool = False


class ArchiveClotureResponse(BaseModel):
    annee: int
    natures_creees: int
    lignes: int
    ouvertures_seed: int
    dossier_id: UUID
    message: str
    annee_ouverture: int
