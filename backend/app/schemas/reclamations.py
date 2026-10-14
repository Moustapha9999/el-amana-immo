"""Gestion des réclamations — schémas d'entrée (les sorties sont des dictionnaires de service)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Domaine = Literal["TYPE", "MOTIF", "SOUS_MOTIF", "CANAL", "CANAL_REPONSE"]
TypeUnite = Literal["DIRECTION", "DEPARTEMENT", "SERVICE", "AGENCE", "CELLULE"]
RoleMembre = Literal["RESPONSABLE", "AGENT"]
Priorite = Literal["BASSE", "NORMALE", "HAUTE", "URGENTE"]
CategorieClient = Literal["PP", "PM", "NON_CLIENT"]
StatutRappel = Literal["AUCUN", "A_RAPPELER", "RAPPELE", "ECHEC"]


class ReferentielCreate(BaseModel):
    domaine: Domaine
    libelle: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=40)
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=2000)


class ReferentielPatch(BaseModel):
    libelle: str | None = Field(default=None, max_length=200)
    code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    ordre: int | None = Field(default=None, ge=0, le=100000)
    actif: bool | None = None


class UniteCreate(BaseModel):
    type_unite: TypeUnite
    libelle: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=40)
    parent_id: uuid.UUID | None = None
    agence_id: uuid.UUID | None = None
    email: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class UnitePatch(BaseModel):
    type_unite: TypeUnite | None = None
    libelle: str | None = Field(default=None, max_length=200)
    code: str | None = Field(default=None, max_length=40)
    parent_id: uuid.UUID | None = None
    detacher_parent: bool = False
    agence_id: uuid.UUID | None = None
    detacher_agence: bool = False
    email: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    ordre: int | None = Field(default=None, ge=0, le=100000)
    actif: bool | None = None


class MembreIn(BaseModel):
    user_id: uuid.UUID
    role_membre: RoleMembre = "AGENT"


class MembrePatch(BaseModel):
    role_membre: RoleMembre | None = None
    actif: bool | None = None


class AppelIn(BaseModel):
    appel_le: datetime
    numero_appelant: str | None = Field(default=None, max_length=40)
    identite_verifiee: bool = False
    mode_verification: str | None = Field(default=None, max_length=200)
    reference_appel: str | None = Field(default=None, max_length=120)
    reference_enregistrement: str | None = Field(default=None, max_length=200)
    rappel_statut: StatutRappel = "AUCUN"
    rappel_prevu_le: datetime | None = None
    commentaire: str | None = Field(default=None, max_length=4000)


class OperationIn(BaseModel):
    reference: str = Field(min_length=1, max_length=120)
    montant: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class _DossierChamps(BaseModel):
    objet: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=20000)
    type_id: uuid.UUID | None = None
    motif_id: uuid.UUID | None = None
    sous_motif_id: uuid.UUID | None = None
    motif_autre: str | None = Field(default=None, max_length=200)
    sous_motif_autre: str | None = Field(default=None, max_length=200)
    priorite: Priorite | None = None
    unite_reception_id: uuid.UUID | None = None
    unite_concernee_id: uuid.UUID | None = None
    date_reclamation: date | None = None
    client_racine: str | None = Field(default=None, max_length=6)
    client_categorie: CategorieClient | None = None
    client_nom: str | None = Field(default=None, max_length=255)
    client_telephone: str | None = Field(default=None, max_length=40)
    client_email: str | None = Field(default=None, max_length=255)
    client_adresse: str | None = Field(default=None, max_length=2000)
    client_agence_id: uuid.UUID | None = None
    compte_reference: str | None = Field(default=None, max_length=60)
    carte_masquee: str | None = Field(default=None, max_length=25)
    operation_reference: str | None = Field(default=None, max_length=120)
    operation_date: date | None = None
    montant_conteste: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    devise: str | None = Field(default=None, max_length=3)
    reclamation_liee_id: uuid.UUID | None = None


class DossierCreate(_DossierChamps):
    objet: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=20000)
    canal_id: uuid.UUID
    date_reclamation: date
    date_premiere_reception: datetime | None = None
    date_reception_sr: datetime | None = None
    appel: AppelIn | None = None
    operations: list[OperationIn] = Field(default_factory=list, max_length=200)


class OperationsIn(BaseModel):
    revision: int
    operations: list[OperationIn] = Field(default_factory=list, max_length=200)
    motif: str | None = Field(default=None, max_length=4000)


class DossierPatch(_DossierChamps):
    revision: int
    date_premiere_reception: datetime | None = None
    date_reception_sr: datetime | None = None
    motif: str | None = Field(default=None, max_length=4000)
    effacer: list[str] = Field(default_factory=list, max_length=40)


class RetraitIn(BaseModel):
    motif: str = Field(min_length=1, max_length=1000)


class ActionIn(BaseModel):
    revision: int
    motif: str | None = Field(default=None, max_length=4000)
    date_reception_sr: datetime | None = None
    conditions_reprise: str | None = Field(default=None, max_length=4000)


class QualifierIn(ActionIn):
    type_id: uuid.UUID | None = None
    motif_id: uuid.UUID | None = None
    sous_motif_id: uuid.UUID | None = None
    motif_autre: str | None = Field(default=None, max_length=200)
    sous_motif_autre: str | None = Field(default=None, max_length=200)
    priorite: Priorite | None = None
    gestionnaire_id: uuid.UUID | None = None


class AffecterIn(ActionIn):
    unite_id: uuid.UUID
    responsable_id: uuid.UUID | None = None
    instructions: str | None = Field(default=None, max_length=8000)
    motif_transfert: str | None = Field(default=None, max_length=4000)


class RetournerIn(ActionIn):
    analyse: str = Field(min_length=1, max_length=20000)
    actions_menees: str | None = Field(default=None, max_length=20000)
    conclusion: str = Field(min_length=1, max_length=8000)
    decision_proposee: Literal["FAVORABLE", "PARTIELLEMENT_FAVORABLE", "DEFAVORABLE", "SANS_SUITE", "AUTRE"] | None = None


class EvaluerIn(ActionIn):
    evaluation: Literal["SUFFISANT", "INSUFFISANT"]
    commentaire: str | None = Field(default=None, max_length=4000)
    instructions: str | None = Field(default=None, max_length=8000)


class AnnulerIn(ActionIn):
    motif: str = Field(min_length=1, max_length=4000)
    doublon_de_id: uuid.UUID | None = None


class RestaurerIn(BaseModel):
    revision: int
    motif: str = Field(min_length=1, max_length=4000)


class SupprimerIn(RestaurerIn):
    confirmation: str = Field(min_length=1, max_length=30)


class CloturerIn(ActionIn):
    resultat: Literal["FAVORABLE", "PARTIELLEMENT_FAVORABLE", "DEFAVORABLE", "SANS_SUITE", "AUTRE"] | None = None
    motif_resolution: str | None = Field(default=None, max_length=4000)


class ReponseEnvoyeeIn(ActionIn):
    """Réponse effectivement envoyée au client, enregistrée par le Service Réclamations avant clôture."""

    objet: str | None = Field(default=None, max_length=255)
    contenu: str = Field(min_length=1, max_length=50000)
    resultat: Literal["FAVORABLE", "PARTIELLEMENT_FAVORABLE", "DEFAVORABLE", "SANS_SUITE", "AUTRE"] | None = None
    canal_envoi_id: uuid.UUID
    destinataire: str | None = Field(default=None, max_length=255)
    envoye_le: datetime | None = None
    reference_envoi: str | None = Field(default=None, max_length=120)


class ValidationReferentielIn(BaseModel):
    statut_validation: Literal["VALIDEE", "PROPOSEE"]
    commentaire: str | None = Field(default=None, max_length=2000)
