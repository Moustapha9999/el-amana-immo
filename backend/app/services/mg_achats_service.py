"""Services Achats & Approvisionnements — cycle d'achat complet."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.auth import Agence, User
from app.schemas.nombres import as_qty
from app.services import mg_achats_regles as R
from app.services.reporting_export import format_montant
from app.models.mg_achats import (
    ORIGINE_ACHAT,
    MgAchatBl,
    MgAchatComparaison,
    MgAchatConsultation,
    MgAchatConsultationFournisseur,
    MgAchatDemande,
    MgAchatDemandeLigne,
    MgAchatDevis,
    MgAchatDevisLigne,
    MgAchatEvenement,
    MgAchatFacture,
    MgAchatFactureLigne,
    MgAchatPaiement,
    MgAchatParametre,
    MgAchatReception,
    MgAchatReceptionLigne,
)
from app.models.ged import GedDocument
from app.models.mg_ops import MgBcLigne, MgBonCommande
from app.models.mg_stock import MgArticle
from app.models.organisation import Fournisseur
from app.schemas.mg_achats import (
    BlCreate,
    ComparaisonCreate,
    ComparaisonUpdate,
    ComparaisonValidateIn,
    ConsultationCreate,
    ConsultationUpdate,
    DemandeCreate,
    DemandeUpdate,
    DevisCreate,
    DevisUpdate,
    DossierControleOut,
    DossierEtapeOut,
    DossierEvenementOut,
    FactureCreate,
    FactureDossierOut,
    FactureLigneIn,
    JustificatifOut,
    FactureLigneProposee,
    FacturePropositionOut,
    FactureUpdate,
    PaiementCreate,
    PaiementUpdate,
    ParametreCreate,
    ParametreUpdate,
    BlOut,
    ReceptionCreate,
    ReceptionOut,
    ReceptionUpdate,
    RapprochementLigneOut,
    ThreeWayMatchOut,
)
from app.schemas.mg_ops import BonCreate, BonUpdate
from app.schemas.organisation import FournisseurCreate, FournisseurUpdate

DEMANDE_TRANSITIONS = {
    "soumettre": ("BROUILLON", "SOUMISE"),
    "valider": ("SOUMISE", "VALIDEE"),
    "lancer_consultation": ("VALIDEE", "CONSULTATION"),
    "commander": ({"VALIDEE", "CONSULTATION"}, "COMMANDE"),
    "cloturer": ("COMMANDE", "CLOTUREE"),
    "rejeter": ({"SOUMISE", "VALIDEE", "CONSULTATION"}, "REJETEE"),
    # Une demande commandée se termine par la clôture ; on annule le BC, pas la demande.
    "annuler": ({"BROUILLON", "SOUMISE", "VALIDEE", "CONSULTATION"}, "ANNULEE"),
}

BC_TRANSITIONS = R.BC_TRANSITIONS
BC_STATUTS_BL = R.BC_STATUTS_RECEPTION
BC_STATUTS_RECEPTION = R.BC_STATUTS_RECEPTION

DEMANDE_STATUTS_MODIFIABLES = frozenset({"BROUILLON", "SOUMISE"})
DEMANDE_STATUTS_SUPPRIMABLES = frozenset({"BROUILLON", "REJETEE", "ANNULEE"})

CONSULTATION_TRANSITIONS = {
    "ouvrir": ("BROUILLON", "OUVERTE"),
    "cloturer": ("OUVERTE", "CLOTUREE"),
    "annuler": (None, "ANNULEE"),
}

_money = R.arrondi_montant
_qty = R.arrondi_quantite
_cle_designation = R.cle_designation


def _line_ht(qty: Decimal, pu: Decimal, remise_pct: Decimal = Decimal("0")) -> Decimal:
    return R.calculer_ligne(qty, pu, remise_pct).ht


GED_MODULE_ACHATS = "achats-appro"
GED_ENTITY_FACTURE = "achat_facture"


def _echeance_depuis_conditions(conditions: str | None, depart: date) -> date | None:
    """« 30 jours », « 45 j fin de mois »… → date de départ + N jours (sinon None)."""
    m = re.search(r"(\d{1,3})\s*(?:jours?|j\b)", conditions or "", re.IGNORECASE)
    return depart + timedelta(days=int(m.group(1))) if m else None


class MgAchatsService:
    def __init__(self, db: AsyncSession, *, mode_test: bool | None = None):
        self.db = db
        # Phase de test (ACHATS_MODE_TEST=1) : verrous de statut levés, suppression en cascade.
        self.mode_test = get_settings().achats_mode_test if mode_test is None else mode_test

    # --- Paramètres / numérotation ---

    async def get_parametre(self, cle: str, default: str = "") -> str:
        row = await self.db.get(MgAchatParametre, cle)
        return row.valeur if row else default

    async def list_parametres(self) -> list[MgAchatParametre]:
        rows = (
            await self.db.execute(select(MgAchatParametre).order_by(MgAchatParametre.cle))
        ).scalars().all()
        return list(rows)

    async def create_parametre(self, data: ParametreCreate) -> MgAchatParametre:
        existing = await self.db.get(MgAchatParametre, data.cle)
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Paramètre déjà existant")
        row = MgAchatParametre(cle=data.cle, valeur=data.valeur, description=data.description)
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_parametre(self, cle: str, data: ParametreUpdate) -> MgAchatParametre:
        row = await self.db.get(MgAchatParametre, cle)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paramètre introuvable")
        if data.valeur is not None:
            row.valeur = data.valeur
        if data.description is not None:
            row.description = data.description
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def delete_parametre(self, cle: str) -> None:
        row = await self.db.get(MgAchatParametre, cle)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paramètre introuvable")
        await self.db.delete(row)
        await self.db.commit()

    async def _next_ref(self, prefix_key: str, model, field, default_prefix: str) -> str:
        prefix = await self.get_parametre(prefix_key, default_prefix)
        year = date.today().year
        like = f"{prefix}-{year}%"
        count = await self.db.scalar(select(func.count()).select_from(model).where(field.ilike(like)))
        return f"{prefix}-{year}{int(count or 0) + 1:04d}"

    async def _append_event(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        message: str | None = None,
        user: User | None = None,
    ) -> None:
        self.db.add(
            MgAchatEvenement(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                message=message,
                user_id=user.id if user else None,
            )
        )

    async def list_evenements(
        self, entity_type: str, entity_id: uuid.UUID
    ) -> list[MgAchatEvenement]:
        stmt = (
            select(MgAchatEvenement)
            .where(
                MgAchatEvenement.entity_type == entity_type,
                MgAchatEvenement.entity_id == entity_id,
            )
            .order_by(MgAchatEvenement.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # --- Dashboard / alertes / rapports ---

    async def dashboard(self) -> dict:
        today = date.today()
        month_start = today.replace(day=1)

        async def _count(model, *filters) -> int:
            return int(
                await self.db.scalar(
                    select(func.count()).select_from(model).where(*filters)
                )
                or 0
            )

        demandes_ouvertes = await _count(
            MgAchatDemande,
            MgAchatDemande.deleted_at.is_(None),
            MgAchatDemande.statut.in_(
                ["BROUILLON", "SOUMISE", "VALIDEE", "CONSULTATION", "COMMANDE"]
            ),
        )
        consultations_ouvertes = await _count(
            MgAchatConsultation,
            MgAchatConsultation.deleted_at.is_(None),
            MgAchatConsultation.statut.in_(["BROUILLON", "OUVERTE", "EN_COURS"]),
        )
        devis_ouverts = await _count(
            MgAchatDevis,
            MgAchatDevis.deleted_at.is_(None),
            MgAchatDevis.statut == "RECU",
        )
        comparaisons_ouvertes = await _count(
            MgAchatComparaison,
            MgAchatComparaison.deleted_at.is_(None),
            MgAchatComparaison.statut.in_(["BROUILLON", "EN_COURS"]),
        )
        bons_en_cours = await _count(
            MgBonCommande,
            MgBonCommande.deleted_at.is_(None),
            MgBonCommande.statut.in_(
                ["BROUILLON", "SOUMIS", "VALIDE", "ENVOYE", "PARTIEL"]
            ),
        )
        bons_partiels = await _count(
            MgBonCommande,
            MgBonCommande.deleted_at.is_(None),
            MgBonCommande.statut == "PARTIEL",
        )
        receptions_mois = await _count(
            MgAchatReception,
            MgAchatReception.deleted_at.is_(None),
            MgAchatReception.date_reception >= month_start,
        )
        factures_ouvertes = await _count(
            MgAchatFacture,
            MgAchatFacture.deleted_at.is_(None),
            MgAchatFacture.origine == ORIGINE_ACHAT,
            MgAchatFacture.statut.in_(["RECUE", "VALIDEE", "ANOMALIE"]),
        )
        paiements_a_payer = await _count(
            MgAchatPaiement,
            MgAchatPaiement.deleted_at.is_(None),
            MgAchatPaiement.origine == ORIGINE_ACHAT,
            MgAchatPaiement.statut == "A_PAYER",
        )
        montant_bc_mois = await self.db.scalar(
            select(func.coalesce(func.sum(MgBonCommande.total_ttc), 0)).where(
                MgBonCommande.deleted_at.is_(None),
                MgBonCommande.date_bc >= month_start,
            )
        )
        montant_factures_mois = await self.db.scalar(
            select(func.coalesce(func.sum(MgAchatFacture.montant_ttc), 0)).where(
                MgAchatFacture.deleted_at.is_(None),
                MgAchatFacture.origine == ORIGINE_ACHAT,
                MgAchatFacture.date_facture >= month_start,
            )
        )
        alertes = len(await self.list_alertes())
        return {
            "demandes_ouvertes": demandes_ouvertes,
            "consultations_ouvertes": consultations_ouvertes,
            "devis_ouverts": devis_ouverts,
            "comparaisons_ouvertes": comparaisons_ouvertes,
            "bons_en_cours": bons_en_cours,
            "bons_partiels": bons_partiels,
            "receptions_mois": receptions_mois,
            "factures_ouvertes": factures_ouvertes,
            "paiements_a_payer": paiements_a_payer,
            "montant_bc_mois": Decimal(montant_bc_mois or 0),
            "montant_factures_mois": Decimal(montant_factures_mois or 0),
            "alertes": alertes,
        }

    async def list_alertes(self) -> list[dict]:
        alerte_jours = int(await self.get_parametre("alerte_jours", "15") or 15)
        horizon = date.today() + timedelta(days=alerte_jours)
        out: list[dict] = []

        factures = (
            await self.db.execute(
                select(MgAchatFacture).where(
                    MgAchatFacture.deleted_at.is_(None),
                    MgAchatFacture.origine == ORIGINE_ACHAT,
                    MgAchatFacture.date_echeance.is_not(None),
                    MgAchatFacture.date_echeance <= horizon,
                    MgAchatFacture.statut.in_(["RECUE", "VALIDEE", "ANOMALIE"]),
                )
            )
        ).scalars().all()
        for f in factures:
            out.append(
                {
                    "type": "FACTURE_ECHEANCE",
                    "reference": f.reference,
                    "entity_id": f.id,
                    "message": f"Facture {f.reference} échéance {f.date_echeance}",
                    "date_echeance": f.date_echeance,
                    "priorite": "URGENT" if f.date_echeance and f.date_echeance <= date.today() else "NORMAL",
                }
            )

        paiements = (
            await self.db.execute(
                select(MgAchatPaiement).where(
                    MgAchatPaiement.deleted_at.is_(None),
                    MgAchatPaiement.origine == ORIGINE_ACHAT,
                    MgAchatPaiement.statut == "A_PAYER",
                    MgAchatPaiement.date_echeance.is_not(None),
                    MgAchatPaiement.date_echeance <= horizon,
                )
            )
        ).scalars().all()
        for p in paiements:
            out.append(
                {
                    "type": "PAIEMENT_ECHEANCE",
                    "reference": p.reference,
                    "entity_id": p.id,
                    "message": f"Paiement {p.reference} à régler avant {p.date_echeance}",
                    "date_echeance": p.date_echeance,
                    "priorite": "URGENT" if p.date_echeance and p.date_echeance <= date.today() else "NORMAL",
                }
            )

        bons = (
            await self.db.execute(
                select(MgBonCommande).where(
                    MgBonCommande.deleted_at.is_(None),
                    MgBonCommande.statut.in_(["VALIDE", "ENVOYE", "PARTIEL"]),
                    MgBonCommande.date_livraison_prevue.is_not(None),
                    MgBonCommande.date_livraison_prevue <= horizon,
                )
            )
        ).scalars().all()
        for b in bons:
            out.append(
                {
                    "type": "LIVRAISON_PREVUE",
                    "reference": b.reference,
                    "entity_id": b.id,
                    "message": f"BC {b.reference} livraison prévue {b.date_livraison_prevue}",
                    "date_echeance": b.date_livraison_prevue,
                    "priorite": "NORMAL",
                }
            )

        anomalies = (
            await self.db.execute(
                select(MgAchatFacture).where(
                    MgAchatFacture.deleted_at.is_(None),
                    MgAchatFacture.origine == ORIGINE_ACHAT,
                    MgAchatFacture.statut == "ANOMALIE",
                )
            )
        ).scalars().all()
        for f in anomalies:
            out.append(
                {
                    "type": "FACTURE_3WM",
                    "reference": f.reference,
                    "entity_id": f.id,
                    "message": f"Facture {f.reference} : écart contrôle 3 voies",
                    "date_echeance": f.date_echeance,
                    "priorite": "URGENT",
                }
            )
        return out

    async def rapports_summary(self) -> dict:
        nb_demandes = int(
            await self.db.scalar(
                select(func.count()).select_from(MgAchatDemande).where(
                    MgAchatDemande.deleted_at.is_(None)
                )
            )
            or 0
        )
        nb_consultations = int(
            await self.db.scalar(
                select(func.count()).select_from(MgAchatConsultation).where(
                    MgAchatConsultation.deleted_at.is_(None)
                )
            )
            or 0
        )
        nb_devis = int(
            await self.db.scalar(
                select(func.count()).select_from(MgAchatDevis).where(
                    MgAchatDevis.deleted_at.is_(None)
                )
            )
            or 0
        )
        nb_comparaisons = int(
            await self.db.scalar(
                select(func.count()).select_from(MgAchatComparaison).where(
                    MgAchatComparaison.deleted_at.is_(None)
                )
            )
            or 0
        )
        nb_bons = int(
            await self.db.scalar(
                select(func.count()).select_from(MgBonCommande).where(
                    MgBonCommande.deleted_at.is_(None)
                )
            )
            or 0
        )
        nb_receptions = int(
            await self.db.scalar(
                select(func.count()).select_from(MgAchatReception).where(
                    MgAchatReception.deleted_at.is_(None)
                )
            )
            or 0
        )
        nb_factures = int(
            await self.db.scalar(
                select(func.count()).select_from(MgAchatFacture).where(
                    MgAchatFacture.deleted_at.is_(None), MgAchatFacture.origine == ORIGINE_ACHAT
                )
            )
            or 0
        )
        montant_bons = await self.db.scalar(
            select(func.coalesce(func.sum(MgBonCommande.total_ttc), 0)).where(
                MgBonCommande.deleted_at.is_(None)
            )
        )
        montant_factures = await self.db.scalar(
            select(func.coalesce(func.sum(MgAchatFacture.montant_ttc), 0)).where(
                MgAchatFacture.deleted_at.is_(None), MgAchatFacture.origine == ORIGINE_ACHAT
            )
        )
        montant_paiements = await self.db.scalar(
            select(func.coalesce(func.sum(MgAchatPaiement.montant), 0)).where(
                MgAchatPaiement.deleted_at.is_(None),
                MgAchatPaiement.origine == ORIGINE_ACHAT,
                MgAchatPaiement.statut == "PAYE",
            )
        )
        return {
            "nb_demandes": nb_demandes,
            "nb_consultations": nb_consultations,
            "nb_devis": nb_devis,
            "nb_comparaisons": nb_comparaisons,
            "nb_bons": nb_bons,
            "nb_receptions": nb_receptions,
            "nb_factures": nb_factures,
            "montant_bons": Decimal(montant_bons or 0),
            "montant_factures": Decimal(montant_factures or 0),
            "montant_paiements": Decimal(montant_paiements or 0),
        }

    # --- Fournisseurs ---

    _FRS_FIELDS = (
        "code",
        "raison_sociale",
        "nom_commercial",
        "type_fournisseur",
        "contact",
        "contact_fonction",
        "telephone",
        "telephone_secondaire",
        "email",
        "site_web",
        "adresse",
        "ville",
        "pays",
        "nif",
        "rc",
        "devise_defaut",
        "mode_paiement_defaut",
        "delai_paiement_jours",
        "conditions_commerciales",
    )

    def _frs_snapshot(self, fr: Fournisseur) -> dict:
        return {
            "id": str(fr.id),
            "code": fr.code,
            "raison_sociale": fr.raison_sociale,
            "nom_commercial": fr.nom_commercial,
            "type_fournisseur": fr.type_fournisseur,
            "contact": fr.contact,
            "contact_fonction": fr.contact_fonction,
            "telephone": fr.telephone,
            "telephone_secondaire": fr.telephone_secondaire,
            "email": fr.email,
            "site_web": fr.site_web,
            "adresse": fr.adresse,
            "ville": fr.ville,
            "pays": fr.pays,
            "nif": fr.nif,
            "rc": fr.rc,
            "devise_defaut": fr.devise_defaut,
            "mode_paiement_defaut": fr.mode_paiement_defaut,
            "delai_paiement_jours": fr.delai_paiement_jours,
            "conditions_commerciales": fr.conditions_commerciales,
            "is_active": fr.is_active,
        }

    async def _assert_fournisseur_unique(
        self,
        *,
        code: str,
        raison_sociale: str,
        email: str | None = None,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        code_n = code.strip().upper()
        rs_n = raison_sociale.strip()
        filters_code = [
            func.upper(Fournisseur.code) == code_n,
            Fournisseur.deleted_at.is_(None),
        ]
        filters_rs = [
            func.lower(Fournisseur.raison_sociale) == rs_n.lower(),
            Fournisseur.deleted_at.is_(None),
        ]
        if exclude_id:
            filters_code.append(Fournisseur.id != exclude_id)
            filters_rs.append(Fournisseur.id != exclude_id)
        if await self.db.scalar(select(func.count()).select_from(Fournisseur).where(*filters_code)):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Un fournisseur avec le code « {code_n} » existe déjà",
            )
        if await self.db.scalar(select(func.count()).select_from(Fournisseur).where(*filters_rs)):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Un fournisseur « {rs_n} » existe déjà",
            )
        if email and email.strip():
            em = email.strip().lower()
            filters_em = [
                func.lower(Fournisseur.email) == em,
                Fournisseur.deleted_at.is_(None),
            ]
            if exclude_id:
                filters_em.append(Fournisseur.id != exclude_id)
            if await self.db.scalar(select(func.count()).select_from(Fournisseur).where(*filters_em)):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Un fournisseur avec l’e-mail « {em} » existe déjà",
                )

    async def list_fournisseurs(
        self,
        *,
        q: str | None = None,
        statut: str | None = None,
        type_fournisseur: str | None = None,
        ville: str | None = None,
        pays: str | None = None,
        actifs_seulement: bool = True,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[dict], int]:
        filters = [Fournisseur.deleted_at.is_(None)]
        if actifs_seulement and statut != "INACTIF":
            filters.append(Fournisseur.is_active.is_(True))
        if statut == "ACTIF":
            filters.append(Fournisseur.is_active.is_(True))
        elif statut == "INACTIF":
            filters.append(Fournisseur.is_active.is_(False))
        if type_fournisseur:
            filters.append(Fournisseur.type_fournisseur == type_fournisseur.strip().upper())
        if ville:
            filters.append(Fournisseur.ville.ilike(f"%{ville.strip()}%"))
        if pays:
            filters.append(Fournisseur.pays.ilike(f"%{pays.strip()}%"))
        if q:
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    Fournisseur.code.ilike(like),
                    Fournisseur.raison_sociale.ilike(like),
                    Fournisseur.nom_commercial.ilike(like),
                    Fournisseur.telephone.ilike(like),
                    Fournisseur.email.ilike(like),
                    Fournisseur.nif.ilike(like),
                )
            )
        total = int(
            await self.db.scalar(select(func.count()).select_from(Fournisseur).where(*filters)) or 0
        )
        stmt = (
            select(Fournisseur)
            .where(*filters)
            .order_by(Fournisseur.raison_sociale)
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list((await self.db.execute(stmt)).scalars().all())
        # Compteurs batch pour la liste
        ids = [r.id for r in rows]
        counts: dict[uuid.UUID, dict[str, int]] = {i: {"nb_bons": 0, "nb_devis": 0, "nb_factures": 0} for i in ids}
        if ids:
            for model, key, col, extra in (
                (MgBonCommande, "nb_bons", MgBonCommande.fournisseur_id, ()),
                (MgAchatDevis, "nb_devis", MgAchatDevis.fournisseur_id, ()),
                (MgAchatFacture, "nb_factures", MgAchatFacture.fournisseur_id, (MgAchatFacture.origine == ORIGINE_ACHAT,)),
            ):
                result = await self.db.execute(
                    select(col, func.count())
                    .where(col.in_(ids), model.deleted_at.is_(None), *extra)
                    .group_by(col)
                )
                for fid, n in result.all():
                    counts[fid][key] = int(n)
        out = []
        for fr in rows:
            snap = self._frs_snapshot(fr)
            snap.update(counts.get(fr.id, {}))
            out.append(snap)
        return out, total

    async def get_fournisseur(self, fournisseur_id: uuid.UUID) -> Fournisseur:
        fr = await self.db.get(Fournisseur, fournisseur_id)
        if not fr or fr.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Fournisseur introuvable")
        return fr

    async def get_fournisseur_summary(self, fournisseur_id: uuid.UUID) -> dict:
        fr = await self.get_fournisseur(fournisseur_id)
        nb_consultations = int(
            await self.db.scalar(
                select(func.count())
                .select_from(MgAchatConsultationFournisseur)
                .where(MgAchatConsultationFournisseur.fournisseur_id == fournisseur_id)
            )
            or 0
        )
        nb_bons = int(
            await self.db.scalar(
                select(func.count()).select_from(MgBonCommande).where(
                    MgBonCommande.fournisseur_id == fournisseur_id,
                    MgBonCommande.deleted_at.is_(None),
                )
            )
            or 0
        )
        nb_devis = int(
            await self.db.scalar(
                select(func.count()).select_from(MgAchatDevis).where(
                    MgAchatDevis.fournisseur_id == fournisseur_id,
                    MgAchatDevis.deleted_at.is_(None),
                )
            )
            or 0
        )
        nb_factures = int(
            await self.db.scalar(
                select(func.count()).select_from(MgAchatFacture).where(
                    MgAchatFacture.fournisseur_id == fournisseur_id,
                    MgAchatFacture.deleted_at.is_(None),
                    MgAchatFacture.origine == ORIGINE_ACHAT,
                )
            )
            or 0
        )
        nb_paiements = int(
            await self.db.scalar(
                select(func.count()).select_from(MgAchatPaiement).where(
                    MgAchatPaiement.fournisseur_id == fournisseur_id,
                    MgAchatPaiement.deleted_at.is_(None),
                    MgAchatPaiement.origine == ORIGINE_ACHAT,
                )
            )
            or 0
        )
        # Réceptions via BC du fournisseur
        nb_receptions = int(
            await self.db.scalar(
                select(func.count())
                .select_from(MgAchatReception)
                .join(MgBonCommande, MgAchatReception.bon_id == MgBonCommande.id)
                .where(
                    MgBonCommande.fournisseur_id == fournisseur_id,
                    MgAchatReception.deleted_at.is_(None),
                    MgBonCommande.deleted_at.is_(None),
                )
            )
            or 0
        )
        montant_bons = await self.db.scalar(
            select(func.coalesce(func.sum(MgBonCommande.total_ttc), 0)).where(
                MgBonCommande.fournisseur_id == fournisseur_id,
                MgBonCommande.deleted_at.is_(None),
            )
        )
        montant_factures = await self.db.scalar(
            select(func.coalesce(func.sum(MgAchatFacture.montant_ttc), 0)).where(
                MgAchatFacture.fournisseur_id == fournisseur_id,
                MgAchatFacture.deleted_at.is_(None),
                MgAchatFacture.origine == ORIGINE_ACHAT,
            )
        )
        snap = self._frs_snapshot(fr)
        snap.update(
            {
                "nb_consultations": nb_consultations,
                "nb_devis": nb_devis,
                "nb_bons": nb_bons,
                "nb_receptions": nb_receptions,
                "nb_factures": nb_factures,
                "nb_paiements": nb_paiements,
                "montant_bons": Decimal(montant_bons or 0),
                "montant_factures": Decimal(montant_factures or 0),
            }
        )
        return snap

    async def create_fournisseur(self, data: FournisseurCreate, user: User) -> Fournisseur:
        await self._assert_fournisseur_unique(
            code=data.code,
            raison_sociale=data.raison_sociale,
            email=data.email,
        )
        payload = data.model_dump()
        payload["code"] = data.code.strip().upper()
        payload["raison_sociale"] = data.raison_sociale.strip()
        payload["type_fournisseur"] = (data.type_fournisseur or "FOURNITURE").strip().upper()
        fr = Fournisseur(**payload, created_by=user.id, updated_by=user.id, is_active=True)
        self.db.add(fr)
        await self.db.flush()
        await self._append_event("fournisseur", fr.id, "create", fr.code, user)
        await self.db.commit()
        await self.db.refresh(fr)
        return fr

    async def update_fournisseur(
        self, fournisseur_id: uuid.UUID, data: FournisseurUpdate, user: User
    ) -> Fournisseur:
        fr = await self.get_fournisseur(fournisseur_id)
        before = self._frs_snapshot(fr)
        patch = data.model_dump(exclude_unset=True)
        if "code" in patch and patch["code"]:
            patch["code"] = patch["code"].strip().upper()
        if "raison_sociale" in patch and patch["raison_sociale"]:
            patch["raison_sociale"] = patch["raison_sociale"].strip()
        if "type_fournisseur" in patch and patch["type_fournisseur"]:
            patch["type_fournisseur"] = patch["type_fournisseur"].strip().upper()
        await self._assert_fournisseur_unique(
            code=patch.get("code") or fr.code,
            raison_sociale=patch.get("raison_sociale") or fr.raison_sociale,
            email=patch["email"] if "email" in patch else fr.email,
            exclude_id=fr.id,
        )
        for key, val in patch.items():
            if key in self._FRS_FIELDS or key == "is_active":
                setattr(fr, key, val)
        fr.updated_by = user.id
        await self._append_event("fournisseur", fr.id, "update", fr.code, user)
        await self.db.commit()
        await self.db.refresh(fr)
        fr._audit_before = before  # type: ignore[attr-defined]
        return fr

    async def set_fournisseur_active(
        self, fournisseur_id: uuid.UUID, active: bool, user: User
    ) -> Fournisseur:
        fr = await self.get_fournisseur(fournisseur_id)
        fr.is_active = active
        fr.updated_by = user.id
        await self._append_event(
            "fournisseur",
            fr.id,
            "activate" if active else "deactivate",
            fr.code,
            user,
        )
        await self.db.commit()
        await self.db.refresh(fr)
        return fr

    async def count_fournisseur_usage(self, fournisseur_id: uuid.UUID) -> dict[str, int]:
        from app.models.immobilisation import Immobilisation
        from app.models.mg_ops import MgContrat, MgPointFacturation

        usage = {
            "consultations": int(
                await self.db.scalar(
                    select(func.count())
                    .select_from(MgAchatConsultationFournisseur)
                    .where(MgAchatConsultationFournisseur.fournisseur_id == fournisseur_id)
                )
                or 0
            ),
            "devis": int(
                await self.db.scalar(
                    select(func.count()).select_from(MgAchatDevis).where(
                        MgAchatDevis.fournisseur_id == fournisseur_id,
                        MgAchatDevis.deleted_at.is_(None),
                    )
                )
                or 0
            ),
            "comparaisons": int(
                await self.db.scalar(
                    select(func.count()).select_from(MgAchatComparaison).where(
                        MgAchatComparaison.fournisseur_retenu_id == fournisseur_id,
                        MgAchatComparaison.deleted_at.is_(None),
                    )
                )
                or 0
            ),
            "bons": int(
                await self.db.scalar(
                    select(func.count()).select_from(MgBonCommande).where(
                        MgBonCommande.fournisseur_id == fournisseur_id,
                        MgBonCommande.deleted_at.is_(None),
                    )
                )
                or 0
            ),
            "bl": int(
                await self.db.scalar(
                    select(func.count()).select_from(MgAchatBl).where(
                        MgAchatBl.fournisseur_id == fournisseur_id,
                        MgAchatBl.deleted_at.is_(None),
                    )
                )
                or 0
            ),
            "factures": int(
                await self.db.scalar(
                    select(func.count()).select_from(MgAchatFacture).where(
                        MgAchatFacture.fournisseur_id == fournisseur_id,
                        MgAchatFacture.deleted_at.is_(None),
                    )
                )
                or 0
            ),
            "paiements": int(
                await self.db.scalar(
                    select(func.count()).select_from(MgAchatPaiement).where(
                        MgAchatPaiement.fournisseur_id == fournisseur_id,
                        MgAchatPaiement.deleted_at.is_(None),
                    )
                )
                or 0
            ),
            "immobilisations": int(
                await self.db.scalar(
                    select(func.count()).select_from(Immobilisation).where(
                        Immobilisation.fournisseur_id == fournisseur_id,
                        Immobilisation.deleted_at.is_(None),
                    )
                )
                or 0
            ),
            "contrats": int(
                await self.db.scalar(
                    select(func.count()).select_from(MgContrat).where(
                        MgContrat.fournisseur_id == fournisseur_id,
                        MgContrat.deleted_at.is_(None),
                    )
                )
                or 0
            ),
            "points_facturation": int(
                await self.db.scalar(
                    select(func.count()).select_from(MgPointFacturation).where(
                        MgPointFacturation.fournisseur_id == fournisseur_id,
                        MgPointFacturation.deleted_at.is_(None),
                    )
                )
                or 0
            ),
        }
        return usage

    async def soft_delete_fournisseur(self, fournisseur_id: uuid.UUID, user: User) -> Fournisseur:
        fr = await self.get_fournisseur(fournisseur_id)
        fr.is_active = False
        fr.deleted_at = datetime.now(timezone.utc)
        fr.updated_by = user.id
        await self._append_event("fournisseur", fr.id, "delete", fr.code, user)
        await self.db.commit()
        return fr

    # --- Demandes ---

    async def list_demandes(
        self, *, statut: str | None = None, q: str | None = None, page: int = 1, size: int = 50
    ) -> tuple[list[MgAchatDemande], int]:
        filters = [MgAchatDemande.deleted_at.is_(None)]
        if statut:
            filters.append(MgAchatDemande.statut == statut)
        if q:
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    MgAchatDemande.reference.ilike(like),
                    MgAchatDemande.demandeur_nom.ilike(like),
                    MgAchatDemande.projet.ilike(like),
                    MgAchatDemande.motif.ilike(like),
                )
            )
        total = int(
            await self.db.scalar(select(func.count()).select_from(MgAchatDemande).where(*filters))
            or 0
        )
        page, size = max(1, page), max(1, min(size, 500))
        stmt = (
            select(MgAchatDemande)
            .options(selectinload(MgAchatDemande.lignes))
            .where(*filters)
            .order_by(MgAchatDemande.date_demande.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list((await self.db.execute(stmt)).scalars().all()), total

    async def get_demande(self, demande_id: uuid.UUID) -> MgAchatDemande:
        row = await self.db.scalar(
            select(MgAchatDemande)
            .options(selectinload(MgAchatDemande.lignes))
            .where(MgAchatDemande.id == demande_id, MgAchatDemande.deleted_at.is_(None))
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Demande introuvable")
        return row

    async def _demande_links(self, demande_id: uuid.UUID) -> dict:
        cons_id = await self.db.scalar(
            select(MgAchatConsultation.id)
            .where(
                MgAchatConsultation.demande_id == demande_id,
                MgAchatConsultation.deleted_at.is_(None),
            )
            .order_by(MgAchatConsultation.created_at.desc())
            .limit(1)
        )
        bon_id = await self.db.scalar(
            select(MgBonCommande.id)
            .where(
                MgBonCommande.demande_id == demande_id,
                MgBonCommande.deleted_at.is_(None),
            )
            .order_by(MgBonCommande.created_at.desc())
            .limit(1)
        )
        return {"consultation_id": cons_id, "bon_id": bon_id}

    async def serialize_demande(self, demande: MgAchatDemande) -> dict:
        from app.schemas.mg_achats import DemandeOut

        links = await self._demande_links(demande.id)
        data = DemandeOut.model_validate(demande).model_dump()
        data.update(links)
        return data

    def _apply_demande_lignes(self, demande: MgAchatDemande, lignes) -> None:
        demande.lignes.clear()
        for i, row in enumerate(lignes):
            montant = _line_ht(row.quantite, row.prix_estime)
            demande.lignes.append(
                MgAchatDemandeLigne(
                    designation=row.designation.strip(),
                    description=row.description,
                    quantite=row.quantite,
                    uom=row.uom or "U",
                    prix_estime=row.prix_estime,
                    montant_estime=montant,
                    article_id=row.article_id,
                    sort_order=i,
                )
            )

    async def create_demande(self, data: DemandeCreate, user: User) -> MgAchatDemande:
        if not data.lignes:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Au moins une ligne est obligatoire",
            )
        ag = await self.db.get(Agence, data.agence_id)
        if not ag or getattr(ag, "deleted_at", None) is not None or not ag.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Agence invalide")
        demande = MgAchatDemande(
            reference=await self._next_ref(
                "prefix_demande", MgAchatDemande, MgAchatDemande.reference, "DA"
            ),
            date_demande=data.date_demande,
            agence_id=data.agence_id,
            departement_id=data.departement_id,
            demandeur_id=user.id,
            demandeur_nom=data.demandeur_nom or user.full_name,
            fonction=data.fonction,
            type_achat=(data.type_achat or "FOURNITURE").strip().upper(),
            priorite=(data.priorite or "NORMAL").strip().upper(),
            projet=data.projet,
            motif=data.motif,
            date_souhaitee=data.date_souhaitee,
            budget_estime=data.budget_estime,
            observation=data.observation,
            source_type=data.source_type,
            source_id=data.source_id,
            statut="BROUILLON",
        )
        self._apply_demande_lignes(demande, data.lignes)
        self.db.add(demande)
        await self.db.flush()
        await self._append_event("demande", demande.id, "create", f"Création {demande.reference}", user)
        await self.db.commit()
        return await self.get_demande(demande.id)

    async def update_demande(
        self, demande_id: uuid.UUID, data: DemandeUpdate, user: User
    ) -> MgAchatDemande:
        demande = await self.get_demande(demande_id)
        self.assert_demande_editable(demande)
        if data.agence_id is not None:
            ag = await self.db.get(Agence, data.agence_id)
            if not ag or getattr(ag, "deleted_at", None) is not None or not ag.is_active:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Agence invalide")
        for field in (
            "date_demande",
            "agence_id",
            "departement_id",
            "demandeur_nom",
            "fonction",
            "type_achat",
            "priorite",
            "projet",
            "motif",
            "date_souhaitee",
            "budget_estime",
            "observation",
        ):
            val = getattr(data, field)
            if val is not None:
                if field in {"type_achat", "priorite"} and isinstance(val, str):
                    val = val.strip().upper()
                setattr(demande, field, val)
        if data.lignes is not None:
            if not data.lignes:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Au moins une ligne est obligatoire",
                )
            self._apply_demande_lignes(demande, data.lignes)
        await self._append_event("demande", demande.id, "update", demande.reference, user)
        await self.db.commit()
        return await self.get_demande(demande.id)

    @staticmethod
    def assert_demande_editable(demande: MgAchatDemande) -> None:
        if demande.statut not in DEMANDE_STATUTS_MODIFIABLES:
            raise R.verrou(
                f"Demande {demande.reference} au statut {demande.statut} : modification impossible "
                "(seules les demandes en brouillon ou soumises sont modifiables)."
            )

    async def delete_demande(self, demande_id: uuid.UUID, user: User) -> MgAchatDemande:
        demande = await self.get_demande(demande_id)
        if demande.statut not in DEMANDE_STATUTS_SUPPRIMABLES:
            raise R.verrou(
                f"Demande {demande.reference} au statut {demande.statut} : suppression impossible, utilisez Annuler."
            )
        bc_lie = await self.db.scalar(
            select(MgBonCommande.reference).where(
                MgBonCommande.demande_id == demande.id, MgBonCommande.deleted_at.is_(None)
            )
        )
        if bc_lie:
            raise R.verrou(f"Demande {demande.reference} liée au bon de commande {bc_lie} : suppression impossible.")
        demande.is_active = False
        demande.deleted_at = datetime.now(timezone.utc)
        await self._append_event("demande", demande.id, "delete", demande.reference, user)
        await self.db.commit()
        return demande

    async def transition_demande(
        self, demande_id: uuid.UUID, action: str, user: User
    ) -> MgAchatDemande:
        demande = await self.get_demande(demande_id)
        key = action.strip().lower()
        if key not in DEMANDE_TRANSITIONS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Action invalide")
        expected, new_statut = DEMANDE_TRANSITIONS[key]
        if expected is not None:
            if isinstance(expected, set):
                if demande.statut not in expected:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=f"Transition impossible depuis {demande.statut}",
                    )
            elif demande.statut != expected:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Transition impossible depuis {demande.statut}",
                )
        if key in {"rejeter", "annuler"} and demande.statut == new_statut:
            return demande
        if key == "soumettre" and not demande.lignes:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Impossible de soumettre une demande sans ligne",
            )

        created_consultation_id: uuid.UUID | None = None
        created_bon_id: uuid.UUID | None = None

        if key == "lancer_consultation":
            cons = MgAchatConsultation(
                reference=await self._next_ref(
                    "prefix_consultation",
                    MgAchatConsultation,
                    MgAchatConsultation.reference,
                    "CONS",
                ),
                date_consultation=date.today(),
                demande_id=demande.id,
                agence_id=demande.agence_id,
                objet=(demande.motif or f"Consultation suite {demande.reference}").strip()[:255],
                responsable_id=user.id,
                observation=demande.observation,
                statut="BROUILLON",
            )
            self.db.add(cons)
            await self.db.flush()
            created_consultation_id = cons.id
            await self._append_event(
                "consultation", cons.id, "create", f"Depuis {demande.reference}", user
            )

        if key == "commander":
            tva = Decimal(await self.get_parametre("tva_defaut", "0") or "0")
            if not demande.lignes:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Impossible de commander sans ligne",
                )
            bon = await self.create_bon(
                BonCreate(
                    date_bc=date.today(),
                    demande_id=demande.id,
                    agence_facturation_id=demande.agence_id,
                    agence_livraison_id=demande.agence_id,
                    type_achat=demande.type_achat,
                    projet=demande.projet,
                    demandeur_nom=demande.demandeur_nom,
                    demandeur_date=demande.date_demande,
                    observation=f"Issu de {demande.reference}",
                    lignes=[
                        {
                            "description": ln.designation,
                            "quantite": ln.quantite,
                            "uom": ln.uom or "U",
                            "prix_unitaire": ln.prix_estime or Decimal("0"),
                            "article_id": ln.article_id,
                            "taux_tva": tva,
                        }
                        for ln in sorted(demande.lignes, key=lambda x: x.sort_order)
                    ],
                ),
                user,
            )
            created_bon_id = bon.id
            demande = await self.get_demande(demande_id)

        demande.statut = new_statut
        await self._append_event(
            "demande",
            demande.id,
            key,
            f"{demande.reference} → {new_statut}",
            user,
        )
        await self.db.commit()
        demande = await self.get_demande(demande.id)
        demande._created_consultation_id = created_consultation_id  # type: ignore[attr-defined]
        demande._created_bon_id = created_bon_id  # type: ignore[attr-defined]
        return demande

    # --- Consultations ---

    async def list_consultations(
        self, *, statut: str | None = None, q: str | None = None
    ) -> list[MgAchatConsultation]:
        filters = [MgAchatConsultation.deleted_at.is_(None)]
        if statut:
            filters.append(MgAchatConsultation.statut == statut)
        if q:
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    MgAchatConsultation.reference.ilike(like),
                    MgAchatConsultation.objet.ilike(like),
                )
            )
        stmt = (
            select(MgAchatConsultation)
            .options(selectinload(MgAchatConsultation.fournisseurs))
            .where(*filters)
            .order_by(MgAchatConsultation.date_consultation.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_consultation(self, consultation_id: uuid.UUID) -> MgAchatConsultation:
        row = await self.db.scalar(
            select(MgAchatConsultation)
            .options(selectinload(MgAchatConsultation.fournisseurs))
            .where(
                MgAchatConsultation.id == consultation_id,
                MgAchatConsultation.deleted_at.is_(None),
            )
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Consultation introuvable")
        return row

    async def _assert_active_fournisseurs(self, fournisseur_ids: list[uuid.UUID]) -> None:
        if not fournisseur_ids:
            return
        unique = list(dict.fromkeys(fournisseur_ids))
        rows = list(
            (
                await self.db.execute(
                    select(Fournisseur).where(
                        Fournisseur.id.in_(unique),
                        Fournisseur.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
        )
        by_id = {r.id: r for r in rows}
        for fid in unique:
            fr = by_id.get(fid)
            if not fr:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Fournisseur introuvable ({fid})",
                )
            if not fr.is_active:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Le fournisseur « {fr.raison_sociale} » est inactif et ne peut pas être invité",
                )

    def _set_consultation_fournisseurs(
        self, consultation: MgAchatConsultation, fournisseur_ids: list[uuid.UUID]
    ) -> None:
        consultation.fournisseurs.clear()
        for fid in dict.fromkeys(fournisseur_ids):
            consultation.fournisseurs.append(
                MgAchatConsultationFournisseur(fournisseur_id=fid)
            )

    async def create_consultation(
        self, data: ConsultationCreate, user: User
    ) -> MgAchatConsultation:
        ag = await self.db.get(Agence, data.agence_id)
        if not ag or getattr(ag, "deleted_at", None) is not None or not ag.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Agence invalide")
        if data.demande_id:
            dem = await self.get_demande(data.demande_id)
            if dem.statut in {"ANNULEE", "REJETEE"}:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Impossible de lier une demande annulée ou rejetée",
                )
        await self._assert_active_fournisseurs(data.fournisseur_ids)
        row = MgAchatConsultation(
            reference=await self._next_ref(
                "prefix_consultation",
                MgAchatConsultation,
                MgAchatConsultation.reference,
                "CONS",
            ),
            date_consultation=data.date_consultation,
            demande_id=data.demande_id,
            agence_id=data.agence_id,
            objet=data.objet.strip(),
            date_limite=data.date_limite,
            responsable_id=user.id,
            observation=data.observation,
            statut="BROUILLON",
        )
        self._set_consultation_fournisseurs(row, data.fournisseur_ids)
        self.db.add(row)
        await self.db.flush()
        await self._append_event("consultation", row.id, "create", row.reference, user)
        await self.db.commit()
        return await self.get_consultation(row.id)

    async def update_consultation(
        self, consultation_id: uuid.UUID, data: ConsultationUpdate, user: User
    ) -> MgAchatConsultation:
        row = await self.get_consultation(consultation_id)
        if data.agence_id is not None:
            ag = await self.db.get(Agence, data.agence_id)
            if not ag or getattr(ag, "deleted_at", None) is not None or not ag.is_active:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Agence invalide")
        for field in (
            "date_consultation",
            "demande_id",
            "agence_id",
            "objet",
            "date_limite",
            "observation",
        ):
            val = getattr(data, field)
            if val is not None:
                setattr(row, field, val if field != "objet" else val.strip())
        if data.fournisseur_ids is not None:
            await self._assert_active_fournisseurs(data.fournisseur_ids)
            self._set_consultation_fournisseurs(row, data.fournisseur_ids)
        await self._append_event("consultation", row.id, "update", row.reference, user)
        await self.db.commit()
        return await self.get_consultation(row.id)

    async def transition_consultation(
        self, consultation_id: uuid.UUID, action: str, user: User
    ) -> MgAchatConsultation:
        row = await self.get_consultation(consultation_id)
        key = action.strip().lower()
        if key not in CONSULTATION_TRANSITIONS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Action invalide")
        expected, new_statut = CONSULTATION_TRANSITIONS[key]
        if expected is not None and row.statut != expected:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Transition impossible depuis {row.statut}",
            )
        if key == "ouvrir" and not row.fournisseurs:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Invitez au moins un fournisseur avant d’ouvrir la consultation",
            )
        if key == "annuler" and row.statut == "ANNULEE":
            return row
        row.statut = new_statut
        await self._append_event(
            "consultation", row.id, key, f"{row.reference} → {new_statut}", user
        )
        await self.db.commit()
        return await self.get_consultation(row.id)

    async def delete_consultation(
        self, consultation_id: uuid.UUID, user: User
    ) -> MgAchatConsultation:
        row = await self.get_consultation(consultation_id)
        row.is_active = False
        row.deleted_at = datetime.now(timezone.utc)
        await self._append_event("consultation", row.id, "delete", row.reference, user)
        await self.db.commit()
        return row

    async def consultation_to_out(self, row: MgAchatConsultation) -> dict:
        ids = [f.fournisseur_id for f in row.fournisseurs]
        fournisseurs: list[dict] = []
        if ids:
            frs = list(
                (
                    await self.db.execute(
                        select(Fournisseur).where(Fournisseur.id.in_(ids))
                    )
                ).scalars().all()
            )
            by_id = {f.id: f for f in frs}
            for fid in ids:
                fr = by_id.get(fid)
                if fr:
                    fournisseurs.append(
                        {
                            "id": str(fr.id),
                            "code": fr.code,
                            "raison_sociale": fr.raison_sociale,
                            "is_active": fr.is_active,
                        }
                    )
        dem_ref = None
        if row.demande_id:
            dem_ref = await self.db.scalar(
                select(MgAchatDemande.reference).where(MgAchatDemande.id == row.demande_id)
            )
        nb_devis = int(
            await self.db.scalar(
                select(func.count()).select_from(MgAchatDevis).where(
                    MgAchatDevis.consultation_id == row.id,
                    MgAchatDevis.deleted_at.is_(None),
                )
            )
            or 0
        )
        return {
            "id": row.id,
            "reference": row.reference,
            "date_consultation": row.date_consultation,
            "demande_id": row.demande_id,
            "agence_id": row.agence_id,
            "objet": row.objet,
            "date_limite": row.date_limite,
            "responsable_id": row.responsable_id,
            "statut": row.statut,
            "observation": row.observation,
            "fournisseur_ids": ids,
            "fournisseurs": fournisseurs,
            "demande_reference": dem_ref,
            "nb_devis": nb_devis,
            "nb_fournisseurs": len(ids),
        }

    # --- Devis ---

    async def list_devis(
        self, *, consultation_id: uuid.UUID | None = None, fournisseur_id: uuid.UUID | None = None
    ) -> list[MgAchatDevis]:
        stmt = (
            select(MgAchatDevis)
            .options(selectinload(MgAchatDevis.lignes))
            .where(MgAchatDevis.deleted_at.is_(None))
            .order_by(MgAchatDevis.date_devis.desc())
        )
        if consultation_id:
            stmt = stmt.where(MgAchatDevis.consultation_id == consultation_id)
        if fournisseur_id:
            stmt = stmt.where(MgAchatDevis.fournisseur_id == fournisseur_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_devis(self, devis_id: uuid.UUID) -> MgAchatDevis:
        row = await self.db.scalar(
            select(MgAchatDevis)
            .options(selectinload(MgAchatDevis.lignes))
            .where(MgAchatDevis.id == devis_id, MgAchatDevis.deleted_at.is_(None))
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Devis introuvable")
        return row

    def _apply_devis_lignes(self, devis: MgAchatDevis, lignes) -> None:
        devis.lignes.clear()
        total_ht = Decimal("0")
        total_tva = Decimal("0")
        for i, row in enumerate(lignes):
            ht = _line_ht(row.quantite, row.prix_unitaire, row.remise_pct)
            tva = _money(ht * Decimal(row.taux_tva or 0) / Decimal("100"))
            total_ht += ht
            total_tva += tva
            devis.lignes.append(
                MgAchatDevisLigne(
                    designation=row.designation.strip(),
                    quantite=row.quantite,
                    prix_unitaire=row.prix_unitaire,
                    remise_pct=row.remise_pct or Decimal("0"),
                    taux_tva=row.taux_tva or Decimal("0"),
                    total_ht=ht,
                    sort_order=i,
                )
            )
        devis.montant_ht = _money(total_ht)
        devis.montant_tva = _money(total_tva)
        devis.montant_ttc = _money(total_ht + total_tva)

    async def create_devis(self, data: DevisCreate, user: User) -> MgAchatDevis:
        if not data.lignes:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Au moins une ligne est requise pour le devis",
            )
        if data.consultation_id:
            invited = await self.db.scalar(
                select(MgAchatConsultationFournisseur.id).where(
                    MgAchatConsultationFournisseur.consultation_id == data.consultation_id,
                    MgAchatConsultationFournisseur.fournisseur_id == data.fournisseur_id,
                )
            )
            if not invited:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Ce fournisseur n'est pas invité sur la consultation sélectionnée",
                )
        row = MgAchatDevis(
            reference=await self._next_ref(
                "prefix_devis", MgAchatDevis, MgAchatDevis.reference, "DEV"
            ),
            fournisseur_id=data.fournisseur_id,
            consultation_id=data.consultation_id,
            date_devis=data.date_devis,
            date_validite=data.date_validite,
            devise=data.devise or await self.get_parametre("devise_defaut", "MRU"),
            conditions=data.conditions,
            delai_livraison=data.delai_livraison,
            conditions_paiement=data.conditions_paiement,
            observation=data.observation,
            statut="RECU",
        )
        self._apply_devis_lignes(row, data.lignes)
        self.db.add(row)
        await self.db.flush()
        await self._append_event("devis", row.id, "create", row.reference, user)
        await self.db.commit()
        return await self.get_devis(row.id)

    async def update_devis(self, devis_id: uuid.UUID, data: DevisUpdate) -> MgAchatDevis:
        row = await self.get_devis(devis_id)
        if data.lignes is not None and not data.lignes:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Au moins une ligne est requise pour le devis",
            )
        for field in (
            "date_devis",
            "date_validite",
            "devise",
            "conditions",
            "delai_livraison",
            "conditions_paiement",
            "observation",
            "statut",
        ):
            val = getattr(data, field)
            if val is not None:
                setattr(row, field, val)
        if data.lignes is not None:
            self._apply_devis_lignes(row, data.lignes)
        await self.db.commit()
        return await self.get_devis(row.id)

    # --- Comparaisons ---

    async def list_comparaisons(self) -> list[MgAchatComparaison]:
        stmt = (
            select(MgAchatComparaison)
            .where(MgAchatComparaison.deleted_at.is_(None))
            .order_by(MgAchatComparaison.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_comparaison(self, comparaison_id: uuid.UUID) -> MgAchatComparaison:
        row = await self.db.scalar(
            select(MgAchatComparaison).where(
                MgAchatComparaison.id == comparaison_id,
                MgAchatComparaison.deleted_at.is_(None),
            )
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Comparaison introuvable")
        return row

    async def create_comparaison(
        self, data: ComparaisonCreate, user: User
    ) -> MgAchatComparaison:
        devis_rows = await self.list_devis(consultation_id=data.consultation_id)
        snapshot = {
            "devis": [
                {
                    "id": str(d.id),
                    "ref": d.reference,
                    "fournisseur_id": str(d.fournisseur_id),
                    "montant_ttc": str(d.montant_ttc),
                }
                for d in devis_rows
            ]
        }
        snapshot_json = data.snapshot_json or json.dumps(snapshot, ensure_ascii=False)
        row = MgAchatComparaison(
            reference=await self._next_ref(
                "prefix_comparaison",
                MgAchatComparaison,
                MgAchatComparaison.reference,
                "CMP",
            ),
            consultation_id=data.consultation_id,
            demande_id=data.demande_id,
            observation=data.observation,
            snapshot_json=snapshot_json,
            statut="BROUILLON",
        )
        self.db.add(row)
        await self.db.flush()
        await self._append_event("comparaison", row.id, "create", row.reference, user)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_comparaison(
        self, comparaison_id: uuid.UUID, data: ComparaisonUpdate
    ) -> MgAchatComparaison:
        row = await self.get_comparaison(comparaison_id)
        for field in ("observation", "snapshot_json", "motif_choix", "fournisseur_retenu_id"):
            val = getattr(data, field)
            if val is not None:
                setattr(row, field, val)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def validate_comparaison(
        self, comparaison_id: uuid.UUID, data: ComparaisonValidateIn, user: User
    ) -> MgAchatComparaison:
        row = await self.get_comparaison(comparaison_id)
        devis_list = await self.list_devis(consultation_id=row.consultation_id)
        if not any(d.fournisseur_id == data.fournisseur_retenu_id for d in devis_list):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Aucun devis du fournisseur retenu sur cette consultation",
            )
        row.fournisseur_retenu_id = data.fournisseur_retenu_id
        row.motif_choix = data.motif_choix
        row.statut = "VALIDEE"
        for d in devis_list:
            if d.fournisseur_id == data.fournisseur_retenu_id:
                d.statut = "RETENU"
            elif d.statut not in {"ANNULE", "REJETE"}:
                d.statut = "REJETE"
        await self._append_event(
            "comparaison",
            row.id,
            "valider",
            f"Fournisseur retenu {data.fournisseur_retenu_id}",
            user,
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    # --- Bons de commande ---

    async def list_bons(
        self,
        *,
        page: int = 1,
        size: int = 50,
        statut: str | None = None,
        q: str | None = None,
        fournisseur_id: uuid.UUID | None = None,
    ) -> tuple[list[MgBonCommande], int]:
        filters = [MgBonCommande.deleted_at.is_(None)]
        if statut:
            filters.append(MgBonCommande.statut == statut)
        if fournisseur_id:
            filters.append(MgBonCommande.fournisseur_id == fournisseur_id)
        if q:
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    MgBonCommande.reference.ilike(like),
                    MgBonCommande.fournisseur_raison_sociale.ilike(like),
                    MgBonCommande.projet.ilike(like),
                )
            )
        total = int(
            await self.db.scalar(select(func.count()).select_from(MgBonCommande).where(*filters))
            or 0
        )
        page, size = max(1, page), max(1, min(size, 500))
        stmt = (
            select(MgBonCommande)
            .options(selectinload(MgBonCommande.lignes))
            .where(*filters)
            .order_by(MgBonCommande.date_bc.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list((await self.db.execute(stmt)).scalars().all()), total

    async def get_bon(self, bon_id: uuid.UUID, *, for_update: bool = False) -> MgBonCommande:
        stmt = (
            select(MgBonCommande)
            .options(selectinload(MgBonCommande.lignes))
            .where(MgBonCommande.id == bon_id, MgBonCommande.deleted_at.is_(None))
        )
        if for_update:
            stmt = stmt.with_for_update()
        bon = await self.db.scalar(stmt)
        if not bon:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bon de commande introuvable")
        return bon

    async def _lignes_bc_referencees(self, bon: MgBonCommande) -> set[uuid.UUID]:
        ids = [lg.id for lg in bon.lignes if lg.id is not None]
        if not ids:
            return set()
        rec = await self.db.scalars(
            select(MgAchatReceptionLigne.bc_ligne_id).where(MgAchatReceptionLigne.bc_ligne_id.in_(ids))
        )
        fac = await self.db.scalars(
            select(MgAchatFactureLigne.bc_ligne_id).where(MgAchatFactureLigne.bc_ligne_id.in_(ids))
        )
        return set(rec.all()) | set(fac.all())

    async def _apply_bc_lignes(self, bon: MgBonCommande, lignes) -> None:
        """Mise à jour en place (jamais DELETE + INSERT de lignes suivies)."""
        existantes = sorted(bon.lignes, key=lambda lg: lg.sort_order or 0)
        referencees = await self._lignes_bc_referencees(bon) if existantes else set()
        if not self.mode_test and any(Decimal(lg.quantite_recue or 0) > 0 for lg in existantes):
            raise R.verrou(
                f"Bon {bon.reference} : des quantités ont déjà été reçues, les lignes ne peuvent plus être modifiées."
            )
        montants: list[R.MontantsLigne] = []
        for i, row in enumerate(lignes):
            remise = getattr(row, "remise_pct", None) or Decimal("0")
            tva = getattr(row, "taux_tva", None) or Decimal("0")
            m = R.calculer_ligne(row.quantite, row.prix_unitaire, remise, tva)
            montants.append(m)
            if i < len(existantes):
                lg = existantes[i]
                if _qty(row.quantite) < _qty(lg.quantite_recue):
                    raise R.refus(
                        f"« {lg.description} » : quantité {as_qty(row.quantite)} inférieure au déjà reçu "
                        f"({as_qty(lg.quantite_recue)}). Supprimez d'abord la réception."
                    )
            else:
                lg = MgBcLigne(quantite_recue=Decimal("0"))
                bon.lignes.append(lg)
            lg.code_produit = row.code_produit
            lg.departement = row.departement
            lg.description = row.description.strip()
            lg.quantite = row.quantite
            lg.article_id = getattr(row, "article_id", None)
            lg.uom = row.uom or "U"
            lg.prix_unitaire = row.prix_unitaire
            lg.prix_total = m.ht
            lg.remise_pct = remise
            lg.taux_tva = tva
            lg.total_ttc = m.ttc
            lg.stockable = bool(getattr(row, "stockable", False))
            lg.sort_order = i
        for lg in existantes[len(lignes):]:
            if lg.id in referencees:
                raise R.verrou(
                    f"La ligne « {lg.description} » est référencée par une réception ou une facture : suppression impossible."
                )
            bon.lignes.remove(lg)
        tot = R.totaliser(montants)
        bon.total_ht, bon.total_tva, bon.total_ttc = tot.ht, tot.tva, tot.ttc

    async def _resolve_agence_snapshot(self, agence_id: uuid.UUID | None) -> str | None:
        if not agence_id:
            return None
        ag = await self.db.get(Agence, agence_id)
        if not ag:
            return None
        parts = [ag.libelle or "", ag.adresse or "", ag.ville or ""]
        return " — ".join(p for p in parts if p) or ag.libelle

    async def create_bon(self, data: BonCreate, user: User) -> MgBonCommande:
        bon = MgBonCommande(
            reference=await self._next_ref(
                "prefix_bc", MgBonCommande, MgBonCommande.reference, "BEA"
            ),
            date_bc=data.date_bc,
            fournisseur_id=data.fournisseur_id,
            fournisseur_raison_sociale=data.fournisseur_raison_sociale,
            fournisseur_nif=data.fournisseur_nif,
            fournisseur_telephone=data.fournisseur_telephone,
            fournisseur_adresse=data.fournisseur_adresse,
            departement=data.departement,
            projet=data.projet,
            acheteur_id=user.id,
            acheteur_nom=data.acheteur_nom or user.full_name,
            acheteur_tel=data.acheteur_tel,
            adresse_facturation=data.adresse_facturation,
            adresse_livraison=data.adresse_livraison,
            conditions=data.conditions or "Voir pièce jointe",
            incoterm=data.incoterm or "N/A",
            conditions_paiement=data.conditions_paiement,
            moyen_paiement=data.moyen_paiement,
            ref_paiement=(data.ref_paiement or "").strip() or None,
            montant_paiement=data.montant_paiement,
            demandeur_nom=data.demandeur_nom,
            demandeur_date=data.demandeur_date,
            observation=data.observation,
            demande_id=data.demande_id,
            consultation_id=data.consultation_id,
            comparaison_id=data.comparaison_id,
            contrat_id=data.contrat_id,
            agence_facturation_id=data.agence_facturation_id,
            agence_livraison_id=data.agence_livraison_id,
            type_achat=data.type_achat or "FOURNITURE",
            devise=data.devise or await self.get_parametre("devise_defaut", "MRU"),
            date_livraison_prevue=data.date_livraison_prevue,
            statut="BROUILLON",
        )
        if data.fournisseur_id and not data.fournisseur_raison_sociale:
            fr = await self.db.get(Fournisseur, data.fournisseur_id)
            if fr:
                bon.fournisseur_raison_sociale = fr.raison_sociale
                bon.fournisseur_telephone = bon.fournisseur_telephone or fr.telephone
                bon.fournisseur_adresse = bon.fournisseur_adresse or fr.adresse
        bon.agence_facturation_snapshot = await self._resolve_agence_snapshot(
            data.agence_facturation_id
        )
        bon.agence_livraison_snapshot = await self._resolve_agence_snapshot(
            data.agence_livraison_id
        )
        await self._apply_bc_lignes(bon, data.lignes)
        self.db.add(bon)
        await self.db.flush()
        await self._append_event("bon", bon.id, "create", bon.reference, user)
        await self.db.commit()
        return await self.get_bon(bon.id)

    @staticmethod
    def _norm_champ(v):
        if isinstance(v, str):
            return v.strip() or None
        if isinstance(v, Decimal):
            return _money(v)
        return v

    def assert_bc_editable(self, bon: MgBonCommande, data: BonUpdate) -> None:
        """Refuse toute modification d'un champ verrouillé par le statut du BC.

        Le client envoie le formulaire complet : on ne refuse que les valeurs
        réellement différentes de l'existant.
        """
        if self.mode_test:
            return
        champs = R.champs_bc_modifiables(bon.statut)
        if champs is None:
            return
        if not champs:
            raise R.verrou(f"Bon {bon.reference} au statut {bon.statut} : aucune modification possible.")
        modifies: list[str] = []
        for field in data.model_fields_set - {"lignes"} - champs:
            new = self._norm_champ(getattr(data, field))
            if new is None:
                continue
            if new != self._norm_champ(getattr(bon, field, None)):
                modifies.append(field)
        if data.lignes is not None:
            actuelles = [R.signature_ligne_bc(lg) for lg in sorted(bon.lignes, key=lambda x: x.sort_order or 0)]
            if [R.signature_ligne_bc(lg) for lg in data.lignes] != actuelles:
                modifies.append("lignes")
        if modifies:
            raise R.verrou(
                f"Bon {bon.reference} au statut {bon.statut} : champs verrouillés ({', '.join(sorted(modifies))}). "
                "Seules la livraison, les contacts et les modalités de paiement restent modifiables."
            )

    async def update_bon(self, bon_id: uuid.UUID, data: BonUpdate, user: User | None = None) -> MgBonCommande:
        bon = await self.get_bon(bon_id, for_update=True)
        self.assert_bc_editable(bon, data)
        brouillon = bon.statut == R.BC_BROUILLON
        for field in (
            "date_bc",
            "fournisseur_id",
            "fournisseur_raison_sociale",
            "fournisseur_nif",
            "fournisseur_telephone",
            "fournisseur_adresse",
            "departement",
            "projet",
            "acheteur_nom",
            "acheteur_tel",
            "adresse_facturation",
            "adresse_livraison",
            "conditions",
            "incoterm",
            "conditions_paiement",
            "demandeur_nom",
            "demandeur_date",
            "observation",
            "demande_id",
            "consultation_id",
            "comparaison_id",
            "contrat_id",
            "type_achat",
            "devise",
            "date_livraison_prevue",
        ):
            val = getattr(data, field)
            if val is not None:
                setattr(bon, field, val)
        # Le détail dépend du moyen choisi : un null explicite efface l'ancienne valeur.
        for field in ("moyen_paiement", "ref_paiement", "montant_paiement"):
            if field in data.model_fields_set:
                val = getattr(data, field)
                if isinstance(val, str):
                    val = val.strip() or None
                setattr(bon, field, val)
        if data.agence_facturation_id is not None:
            bon.agence_facturation_id = data.agence_facturation_id
            bon.agence_facturation_snapshot = await self._resolve_agence_snapshot(
                data.agence_facturation_id
            )
        if data.agence_livraison_id is not None:
            bon.agence_livraison_id = data.agence_livraison_id
            bon.agence_livraison_snapshot = await self._resolve_agence_snapshot(
                data.agence_livraison_id
            )
        if data.lignes is not None and (brouillon or self.mode_test):
            await self._apply_bc_lignes(bon, data.lignes)
            if bon.statut in R.BC_STATUTS_RECEPTION | {R.BC_RECU, R.BC_CLOTURE}:
                bon.statut = R.statut_bc_selon_receptions(bon.lignes, envoye=bon.envoye_at is not None)
        if user is not None:
            await self._append_event("bon", bon.id, "update", bon.reference, user)
        await self.db.commit()
        return await self.get_bon(bon.id)

    async def delete_bon(self, bon_id: uuid.UUID, user: User) -> MgBonCommande:
        """Suppression logique réservée aux brouillons ; sinon il faut annuler."""
        bon = await self.get_bon(bon_id, for_update=True)
        if self.mode_test:
            return await self._supprimer_bon_cascade(bon, user)
        if bon.statut != R.BC_BROUILLON:
            raise R.verrou(
                f"Bon {bon.reference} au statut {bon.statut} : suppression impossible, utilisez Annuler."
            )
        if await self._lignes_bc_referencees(bon):
            raise R.verrou(f"Bon {bon.reference} référencé par une réception ou une facture : suppression impossible.")
        bon.deleted_at = datetime.now(timezone.utc)
        await self._append_event("bon", bon.id, "delete", bon.reference, user)
        await self.db.commit()
        return bon

    async def _bc_a_des_suites_actives(self, bon_id: uuid.UUID) -> str | None:
        rec = await self.db.scalar(
            select(MgAchatReception.reference).where(
                MgAchatReception.bon_id == bon_id,
                MgAchatReception.deleted_at.is_(None),
                MgAchatReception.statut != "ANNULEE",
            ).limit(1)
        )
        if rec:
            return f"la réception {rec}"
        fac = await self.db.scalar(
            select(MgAchatFacture.reference).where(
                MgAchatFacture.bon_id == bon_id,
                MgAchatFacture.deleted_at.is_(None),
                MgAchatFacture.statut != R.FAC_ANNULEE,
            ).limit(1)
        )
        return f"la facture {fac}" if fac else None

    async def transition_bon(
        self, bon_id: uuid.UUID, action: str, user: User, *, motif: str | None = None
    ) -> MgBonCommande:
        bon = await self.get_bon(bon_id, for_update=True)
        key = action.strip().lower()
        if key not in BC_TRANSITIONS:
            raise R.refus(f"Action « {action} » invalide sur un bon de commande.")
        expected, new_statut = BC_TRANSITIONS[key]
        if bon.statut not in expected:
            raise R.verrou(
                f"Transition « {key} » impossible depuis {bon.statut} (attendu : {', '.join(sorted(expected))})."
            )
        motif = (motif or "").strip() or None
        if key in {"rejeter", "annuler"} and not motif:
            raise R.refus("Un motif est obligatoire pour rejeter ou annuler un bon de commande.")
        if key == "soumettre" and not bon.lignes:
            raise R.refus("Impossible de soumettre un bon de commande sans ligne.")
        if key == "annuler":
            suite = await self._bc_a_des_suites_actives(bon.id)
            if suite:
                raise R.verrou(f"Bon {bon.reference} : annulation impossible, {suite} est active (annulez-la d'abord).")
        now = datetime.now(timezone.utc)
        if key == "soumettre":
            bon.soumis_at, bon.soumis_by = now, user.id
        elif key == "retour_brouillon":
            bon.soumis_at = bon.soumis_by = None
        elif key == "valider":
            bon.valide_at, bon.valide_by = now, user.id
        elif key == "envoyer":
            bon.envoye_at, bon.envoye_by = now, user.id
        elif key == "cloturer":
            bon.cloture_at, bon.cloture_by = now, user.id
        elif key in {"rejeter", "annuler"}:
            bon.annule_at, bon.annule_by = now, user.id
            bon.motif_annulation = motif
        ancien = bon.statut
        bon.statut = new_statut
        libelle = f"{bon.reference} : {ancien} → {new_statut}" + (f" — {motif}" if motif else "")
        await self._append_event("bon", bon.id, key, libelle, user)
        await self.db.commit()
        return await self.get_bon(bon.id)

    async def submit_bc(self, bon_id: uuid.UUID, user: User) -> MgBonCommande:
        return await self.transition_bon(bon_id, "soumettre", user)

    async def return_bc_to_draft(self, bon_id: uuid.UUID, user: User) -> MgBonCommande:
        return await self.transition_bon(bon_id, "retour_brouillon", user)

    async def validate_bc(self, bon_id: uuid.UUID, user: User) -> MgBonCommande:
        return await self.transition_bon(bon_id, "valider", user)

    async def send_bc(self, bon_id: uuid.UUID, user: User) -> MgBonCommande:
        return await self.transition_bon(bon_id, "envoyer", user)

    async def reject_bc(self, bon_id: uuid.UUID, user: User, motif: str | None) -> MgBonCommande:
        return await self.transition_bon(bon_id, "rejeter", user, motif=motif)

    async def cancel_bc(self, bon_id: uuid.UUID, user: User, motif: str | None) -> MgBonCommande:
        return await self.transition_bon(bon_id, "annuler", user, motif=motif)

    async def close_bc(self, bon_id: uuid.UUID, user: User) -> MgBonCommande:
        return await self.transition_bon(bon_id, "cloturer", user)

    # --- BL ---

    async def _bon_references_map(
        self, bon_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        if not bon_ids:
            return {}
        rows = await self.db.execute(
            select(MgBonCommande.id, MgBonCommande.reference).where(
                MgBonCommande.id.in_(bon_ids)
            )
        )
        return {row[0]: row[1] for row in rows.all()}

    async def serialize_bl(self, row: MgAchatBl) -> BlOut:
        refs = await self._bon_references_map({row.bon_id})
        return BlOut.model_validate(row).model_copy(
            update={"bon_reference": refs.get(row.bon_id)}
        )

    async def serialize_bl_list(self, rows: list[MgAchatBl]) -> list[BlOut]:
        refs = await self._bon_references_map({r.bon_id for r in rows})
        return [
            BlOut.model_validate(r).model_copy(
                update={"bon_reference": refs.get(r.bon_id)}
            )
            for r in rows
        ]

    async def serialize_reception(self, row: MgAchatReception) -> ReceptionOut:
        refs = await self._bon_references_map({row.bon_id})
        return ReceptionOut.model_validate(row).model_copy(
            update={"bon_reference": refs.get(row.bon_id)}
        )

    async def serialize_reception_list(
        self, rows: list[MgAchatReception]
    ) -> list[ReceptionOut]:
        refs = await self._bon_references_map({r.bon_id for r in rows})
        return [
            ReceptionOut.model_validate(r).model_copy(
                update={"bon_reference": refs.get(r.bon_id)}
            )
            for r in rows
        ]

    async def list_bl(self, *, bon_id: uuid.UUID | None = None) -> list[MgAchatBl]:
        stmt = (
            select(MgAchatBl)
            .where(MgAchatBl.deleted_at.is_(None))
            .order_by(MgAchatBl.date_bl.desc())
        )
        if bon_id:
            stmt = stmt.where(MgAchatBl.bon_id == bon_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_bl(self, bl_id: uuid.UUID) -> MgAchatBl:
        row = await self.db.scalar(
            select(MgAchatBl).where(MgAchatBl.id == bl_id, MgAchatBl.deleted_at.is_(None))
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="BL introuvable")
        return row

    async def create_bl(self, data: BlCreate, user: User) -> MgAchatBl:
        bon = await self.get_bon(data.bon_id)
        if bon.statut not in BC_STATUTS_BL:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"BL impossible pour statut BC {bon.statut}",
            )
        fournisseur_id = data.fournisseur_id or bon.fournisseur_id
        if not fournisseur_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Fournisseur requis")
        row = MgAchatBl(
            reference=await self._next_ref("prefix_bl", MgAchatBl, MgAchatBl.reference, "BL"),
            bon_id=bon.id,
            fournisseur_id=fournisseur_id,
            date_bl=data.date_bl,
            date_livraison=data.date_livraison,
            agence_id=data.agence_id or bon.agence_livraison_id,
            transporteur=data.transporteur,
            observation=data.observation,
            statut="RECU",
        )
        self.db.add(row)
        await self.db.flush()
        await self._append_event("bl", row.id, "create", f"{row.reference} / {bon.reference}", user)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    # --- Réceptions ---

    async def list_receptions(self, *, bon_id: uuid.UUID | None = None) -> list[MgAchatReception]:
        stmt = (
            select(MgAchatReception)
            .options(selectinload(MgAchatReception.lignes))
            .where(MgAchatReception.deleted_at.is_(None))
            .order_by(MgAchatReception.date_reception.desc())
        )
        if bon_id:
            stmt = stmt.where(MgAchatReception.bon_id == bon_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_reception(self, reception_id: uuid.UUID) -> MgAchatReception:
        row = await self.db.scalar(
            select(MgAchatReception)
            .options(selectinload(MgAchatReception.lignes))
            .where(MgAchatReception.id == reception_id, MgAchatReception.deleted_at.is_(None))
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Réception introuvable")
        return row

    async def create_reception(
        self, data: ReceptionCreate, user: User, *, stocker_si_article: bool = False
    ) -> MgAchatReception:
        """Réception (partielle ou totale) d'un BC validé / envoyé.

        ``stocker_si_article`` : voie Stock — toute ligne portant un article
        génère une entrée, même si la ligne BC n'est pas marquée stockable.
        """
        from app.services.mg_stock_service import MgStockService

        bon = await self.get_bon(data.bon_id, for_update=True)
        if bon.statut not in BC_STATUTS_RECEPTION:
            raise R.verrou(
                f"Réception impossible : le bon {bon.reference} est au statut {bon.statut} "
                "(attendu : VALIDE, ENVOYE ou PARTIEL)."
            )
        cumul: dict[uuid.UUID, Decimal] = {}
        for payload in data.lignes:
            cumul[payload.bc_ligne_id] = cumul.get(payload.bc_ligne_id, Decimal("0")) + _qty(payload.quantite_recue)
        if data.bl_id is not None:
            bl = await self.get_bl(data.bl_id)
            if bl.bon_id != bon.id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Le BL ne correspond pas au bon de commande",
                )
        by_id = {lg.id: lg for lg in bon.lignes}
        for lid, total in cumul.items():
            ligne = by_id.get(lid)
            if ligne is None:
                raise R.refus(f"Ligne {lid} absente du bon {bon.reference}.")
            reste = _qty(ligne.quantite) - _qty(ligne.quantite_recue)
            if total > reste:
                raise R.refus(
                    f"Quantité reçue {as_qty(total)} > reste à recevoir {as_qty(max(reste, Decimal('0')))} "
                    f"pour « {ligne.description} »."
                )
        reception = MgAchatReception(
            id=uuid.uuid4(),
            reference=await self._next_ref(
                "prefix_reception", MgAchatReception, MgAchatReception.reference, "REC"
            ),
            bon_id=bon.id,
            bl_id=data.bl_id,
            date_reception=data.date_reception,
            agence_id=data.agence_id or bon.agence_livraison_id,
            observation=data.observation,
            created_by=user.id,
            statut="PARTIEL",
        )
        stock_svc = MgStockService(self.db)

        for payload in data.lignes:
            ligne = by_id[payload.bc_ligne_id]
            deja = _qty(ligne.quantite_recue)
            qty = _qty(payload.quantite_recue)
            article_id = payload.article_id or ligne.article_id
            if article_id and (ligne.stockable or stocker_si_article):
                article = await self.db.scalar(
                    select(MgArticle)
                    .where(MgArticle.id == article_id, MgArticle.deleted_at.is_(None))
                    .with_for_update()
                )
                if article is None:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Article introuvable")
                # Passage par l'API publique du Stock — jamais d'UPDATE direct
                # sur mg_articles.stock_actuel depuis Achats & Approvisionnements.
                await stock_svc.record_achat_reception(
                    article=article,
                    quantite=qty,
                    agence_id=data.agence_id or article.agence_id or bon.agence_livraison_id,
                    initiateur=user,
                    motif=f"Réception achat {reception.reference} / {bon.reference}",
                    source_id=reception.id,
                )
                if ligne.article_id is None:
                    ligne.article_id = article_id
            ligne.quantite_recue = deja + qty
            reception.lignes.append(
                MgAchatReceptionLigne(
                    bc_ligne_id=ligne.id,
                    quantite_recue=qty,
                    article_id=article_id,
                )
            )

        bon.statut = R.statut_bc_selon_receptions(bon.lignes, envoye=bon.envoye_at is not None)
        reception.statut = "COMPLETE" if bon.statut == R.BC_RECU else "PARTIEL"

        self.db.add(reception)
        await self.db.flush()
        await self._append_event(
            "reception",
            reception.id,
            "create",
            f"{reception.reference} → BC {bon.statut}",
            user,
        )
        await self.db.commit()
        return await self.get_reception(reception.id)

    async def update_reception(
        self, reception_id: uuid.UUID, data: ReceptionUpdate, user: User
    ) -> MgAchatReception:
        row = await self.get_reception(reception_id)
        if data.date_reception is not None:
            row.date_reception = data.date_reception
        if data.agence_id is not None:
            row.agence_id = data.agence_id
        if data.observation is not None:
            row.observation = data.observation
        if data.statut is not None and data.statut.strip().upper() != row.statut:
            raise R.refus("Le statut d'une réception est calculé ; utilisez Annuler pour l'invalider.")
        await self._append_event("reception", row.id, "update", row.reference, user)
        await self.db.commit()
        return await self.get_reception(row.id)

    async def _quantites_facturees(
        self, bon_id: uuid.UUID, *, sauf_facture_id: uuid.UUID | None = None
    ) -> dict[uuid.UUID, Decimal]:
        """Quantités déjà facturées par ligne BC (factures actives uniquement)."""
        stmt = (
            select(MgAchatFactureLigne.bc_ligne_id, func.coalesce(func.sum(MgAchatFactureLigne.quantite), 0))
            .join(MgAchatFacture, MgAchatFacture.id == MgAchatFactureLigne.facture_id)
            .where(
                MgAchatFacture.bon_id == bon_id,
                MgAchatFacture.deleted_at.is_(None),
                MgAchatFacture.statut != R.FAC_ANNULEE,
                MgAchatFactureLigne.bc_ligne_id.is_not(None),
            )
            .group_by(MgAchatFactureLigne.bc_ligne_id)
        )
        if sauf_facture_id is not None:
            stmt = stmt.where(MgAchatFacture.id != sauf_facture_id)
        return {lid: _qty(q) for lid, q in (await self.db.execute(stmt)).all()}

    async def _contrepasser_reception(
        self, bon: MgBonCommande, row: MgAchatReception, user: User, libelle: str
    ) -> None:
        """Sortie de stock inverse + quantités reçues restituées au BC (row.lignes chargées)."""
        from app.services.mg_stock_service import MgStockService

        by_id = {lg.id: lg for lg in bon.lignes}
        stock_svc = MgStockService(self.db)
        for rl in row.lignes:
            lg = by_id.get(rl.bc_ligne_id)
            if lg is None:
                continue
            if rl.article_id:
                article = await self.db.scalar(
                    select(MgArticle).where(MgArticle.id == rl.article_id).with_for_update()
                )
                if article is not None:
                    await stock_svc.annuler_achat_reception(
                        article=article,
                        quantite=_qty(rl.quantite_recue),
                        agence_id=row.agence_id or article.agence_id,
                        initiateur=user,
                        motif=libelle,
                        source_id=row.id,
                        legacy_source_id=bon.id,
                    )
            lg.quantite_recue = max(Decimal("0"), _qty(lg.quantite_recue) - _qty(rl.quantite_recue))

    async def cancel_reception(
        self, reception_id: uuid.UUID, user: User, motif: str | None
    ) -> MgAchatReception:
        """Annulation par contre-passation : quantités reçues et stock sont restitués."""
        motif = (motif or "").strip()
        if not motif:
            raise R.refus("Un motif est obligatoire pour annuler une réception.")
        row = await self.get_reception(reception_id)
        bon = await self.get_bon(row.bon_id, for_update=True)
        row = await self.db.scalar(
            select(MgAchatReception)
            .options(selectinload(MgAchatReception.lignes))
            .where(MgAchatReception.id == reception_id)
            .with_for_update()
        )
        if row.statut == "ANNULEE":
            raise R.verrou(f"La réception {row.reference} est déjà annulée.")
        if bon.statut in R.BC_STATUTS_FIGES:
            raise R.verrou(f"Bon {bon.reference} au statut {bon.statut} : réception non annulable.")
        by_id = {lg.id: lg for lg in bon.lignes}
        retrait: dict[uuid.UUID, Decimal] = {}
        for rl in row.lignes:
            retrait[rl.bc_ligne_id] = retrait.get(rl.bc_ligne_id, Decimal("0")) + _qty(rl.quantite_recue)
        facture = await self._quantites_facturees(bon.id)
        for lid, q in retrait.items():
            lg = by_id.get(lid)
            if lg is None:
                continue
            nouveau = _qty(lg.quantite_recue) - q
            if facture.get(lid, Decimal("0")) > nouveau:
                raise R.verrou(
                    f"« {lg.description} » : {as_qty(facture[lid])} déjà facturé(s), l'annulation ramènerait "
                    f"le reçu à {as_qty(max(nouveau, Decimal('0')))}. Annulez d'abord la facture."
                )
        await self._contrepasser_reception(bon, row, user, f"Annulation réception {row.reference} — {motif}")
        now = datetime.now(timezone.utc)
        row.statut = "ANNULEE"
        row.annule_at, row.annule_by, row.motif_annulation = now, user.id, motif
        bon.statut = R.statut_bc_selon_receptions(bon.lignes, envoye=bon.envoye_at is not None)
        await self._append_event(
            "reception", row.id, "annuler", f"{row.reference} annulée — BC {bon.statut} — {motif}", user
        )
        await self.db.commit()
        return await self.get_reception(row.id)

    # --- Factures / 3-way match ---

    async def list_factures(self, *, bon_id: uuid.UUID | None = None) -> list[MgAchatFacture]:
        stmt = (
            select(MgAchatFacture)
            .options(selectinload(MgAchatFacture.lignes))
            .where(MgAchatFacture.deleted_at.is_(None), MgAchatFacture.origine == ORIGINE_ACHAT)
            .order_by(MgAchatFacture.date_facture.desc())
        )
        if bon_id:
            stmt = stmt.where(MgAchatFacture.bon_id == bon_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_facture(self, facture_id: uuid.UUID) -> MgAchatFacture:
        row = await self.db.scalar(
            select(MgAchatFacture)
            .options(selectinload(MgAchatFacture.lignes))
            .where(
                MgAchatFacture.id == facture_id,
                MgAchatFacture.deleted_at.is_(None),
                MgAchatFacture.origine == ORIGINE_ACHAT,
            )
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
        return row

    @staticmethod
    def _taux_tva_bc(bon: MgBonCommande, designation: str) -> Decimal:
        """Taux de la ligne BC de même désignation, sinon taux moyen du BC."""
        cle = _cle_designation(designation)
        for lg in bon.lignes or []:
            if _cle_designation(lg.description) == cle:
                return Decimal(lg.taux_tva or 0)
        ht = Decimal(bon.total_ht or 0)
        if ht <= 0:
            return Decimal("0")
        return (Decimal(bon.total_tva or 0) * Decimal("100") / ht).quantize(Decimal("0.01"))

    def _apply_facture_lignes(self, facture: MgAchatFacture, lignes, bon: MgBonCommande) -> None:
        """Lignes rattachées au BC (id prioritaire), TVA arrondie par ligne, mise à jour en place."""
        existantes = sorted(facture.lignes or [], key=lambda lg: lg.sort_order or 0)
        montants: list[R.MontantsLigne] = []
        for i, row in enumerate(lignes):
            bc = R.associer_ligne_bc(bon.lignes or [], row.bc_ligne_id, row.designation)
            if row.taux_tva is not None:
                taux = Decimal(row.taux_tva)
            elif bc is not None:
                taux = Decimal(bc.taux_tva or 0)
            else:
                taux = self._taux_tva_bc(bon, row.designation)
            m = R.calculer_ligne(row.quantite, row.prix_unitaire, Decimal("0"), taux)
            montants.append(m)
            if i < len(existantes):
                lg = existantes[i]
            else:
                lg = MgAchatFactureLigne()
                facture.lignes.append(lg)
            lg.bc_ligne_id = bc.id if bc is not None else None
            lg.designation = row.designation.strip()
            lg.quantite = _qty(row.quantite)
            lg.prix_unitaire = _money(row.prix_unitaire)
            lg.taux_tva = _money(taux)
            lg.total_ht, lg.montant_tva, lg.total_ttc = m.ht, m.tva, m.ttc
            lg.sort_order = i
        for lg in existantes[len(lignes):]:
            facture.lignes.remove(lg)
        if lignes:
            tot = R.totaliser(montants)
            facture.montant_ht, facture.montant_tva, facture.montant_ttc = tot.ht, tot.tva, tot.ttc

    async def recalculate_invoice_reconciliation(
        self, bon: MgBonCommande, facture: MgAchatFacture, *, plafond: bool = True
    ) -> R.Rapprochement:
        """Plafond commandé (refus dur) puis rapprochement ligne à ligne (écarts stockés)."""
        deja = await self._quantites_facturees(bon.id, sauf_facture_id=facture.id)
        if plafond:
            par_ligne: dict[uuid.UUID, Decimal] = {}
            for fl in facture.lignes or []:
                if fl.bc_ligne_id is not None:
                    par_ligne[fl.bc_ligne_id] = par_ligne.get(fl.bc_ligne_id, Decimal("0")) + _qty(fl.quantite)
            R.verifier_plafond_commande(bon.lignes or [], par_ligne, deja)
        rap = R.rapprocher_facture(bon.lignes or [], facture.lignes or [], deja, facture.montant_ttc)
        facture.ecart_quantite = rap.ecart_quantite
        facture.ecart_montant = rap.ecart_montant
        if facture.statut in (R.FAC_BROUILLON, R.FAC_RECUE, R.FAC_ANOMALIE):
            facture.statut = R.FAC_ANOMALIE if rap.resultat == "ANOMALIE" else R.FAC_RECUE
        return rap

    def assert_facture_editable(self, facture: MgAchatFacture) -> None:
        if self.mode_test and facture.statut != R.FAC_ANNULEE:
            return
        if facture.statut not in R.FACTURE_STATUTS_MODIFIABLES:
            raise R.verrou(
                f"Facture {facture.reference} au statut {facture.statut} : modification impossible "
                "(une facture validée ou payée est figée)."
            )

    async def _derniere_reception(self, bon_id: uuid.UUID) -> MgAchatReception | None:
        for rec in await self.list_receptions(bon_id=bon_id):
            if rec.statut != "ANNULEE":
                return rec
        return None

    async def propose_facture(
        self, bon_id: uuid.UUID, *, date_facture: date | None = None, exclure_facture_id: uuid.UUID | None = None
    ) -> FacturePropositionOut:
        """Lignes à facturer = reçu (commandé si rien reçu) − déjà facturé, par ligne BC."""
        bon = await self.get_bon(bon_id)
        factures = [
            f
            for f in await self.list_factures(bon_id=bon.id)
            if f.statut != R.FAC_ANNULEE and f.id != exclure_facture_id
        ]
        deja = await self._quantites_facturees(bon.id, sauf_facture_id=exclure_facture_id)
        rien_recu = not any(_qty(lg.quantite_recue) > 0 for lg in bon.lignes or [])

        lignes: list[FactureLigneProposee] = []
        montants: list[R.MontantsLigne] = []
        for lg in sorted(bon.lignes or [], key=lambda x: x.sort_order or 0):
            cmd = _qty(lg.quantite)
            recu = _qty(lg.quantite_recue)
            base = cmd if rien_recu else recu
            consomme = deja.get(lg.id, Decimal("0"))
            reste = base - consomme
            if reste <= 0:
                continue
            pu = R.prix_net(lg.prix_unitaire, lg.remise_pct)
            taux = Decimal(lg.taux_tva or 0)
            m = R.calculer_ligne(reste, pu, Decimal("0"), taux)
            montants.append(m)
            lignes.append(
                FactureLigneProposee(
                    bc_ligne_id=lg.id,
                    designation=lg.description,
                    uom=lg.uom or "U",
                    quantite=reste,
                    prix_unitaire=pu,
                    taux_tva=taux,
                    total_ht=m.ht,
                    quantite_commandee=cmd,
                    quantite_recue=recu,
                    quantite_deja_facturee=consomme,
                )
            )

        rec = await self._derniere_reception(bon.id)
        message = None
        attente: list[str] = []
        attente_ttc: list[R.MontantsLigne] = []
        for lg in sorted(bon.lignes or [], key=lambda x: x.sort_order or 0):
            manque = _qty(lg.quantite) - _qty(lg.quantite_recue)
            if manque > 0 and not rien_recu:
                attente.append(f"{format(manque.normalize(), 'f')} × {lg.description}")
                attente_ttc.append(
                    R.calculer_ligne(manque, R.prix_net(lg.prix_unitaire, lg.remise_pct), Decimal("0"), Decimal(lg.taux_tva or 0))
                )
        if not lignes and attente:
            message = (
                "Tout ce qui a été reçu est déjà facturé. Reste à recevoir : "
                f"{', '.join(attente)} ({format_montant(R.totaliser(attente_ttc).ttc)} MRU). "
                "Enregistrez la réception de ces articles pour pouvoir les facturer."
            )
        elif not lignes:
            message = "Toutes les quantités de ce BC sont déjà facturées."
        elif attente:
            message = (
                f"Seules les quantités reçues sont proposées. Encore à recevoir : {', '.join(attente)} "
                f"({format_montant(R.totaliser(attente_ttc).ttc)} MRU)."
            )
        elif rien_recu:
            message = (
                "Aucune réception enregistrée : quantités proposées = quantités commandées "
                "(la facture sera signalée en anomalie tant que rien n'est reçu)."
            )
        tot = R.totaliser(montants)
        total_ht, total_tva = tot.ht, tot.tva
        return FacturePropositionOut(
            bon_id=bon.id,
            bon_reference=bon.reference,
            bon_statut=bon.statut,
            fournisseur_id=bon.fournisseur_id,
            fournisseur_raison_sociale=bon.fournisseur_raison_sociale,
            reception_id=rec.id if rec else None,
            reception_reference=rec.reference if rec else None,
            date_echeance=_echeance_depuis_conditions(bon.conditions_paiement, date_facture or date.today()),
            conditions_paiement=bon.conditions_paiement,
            devise=bon.devise or "MRU",
            lignes=lignes,
            montant_ht=total_ht,
            montant_tva=total_tva,
            montant_ttc=_money(total_ht + total_tva),
            bc_total_ttc=_money(Decimal(bon.total_ttc or bon.total_ht or 0)),
            deja_facture_ttc=_money(sum((Decimal(f.montant_ttc or 0) for f in factures), Decimal("0"))),
            nb_factures=len(factures),
            message=message,
        )

    async def create_facture(self, data: FactureCreate, user: User) -> MgAchatFacture:
        # Verrou BC : deux factures simultanées ne peuvent pas dépasser le commandé.
        bon = await self.get_bon(data.bon_id, for_update=True)
        if bon.statut not in R.BC_STATUTS_FACTURATION:
            raise R.verrou(
                f"Facturation impossible : le bon {bon.reference} est au statut {bon.statut} "
                "(il doit être validé)."
            )
        fournisseur_id = data.fournisseur_id or bon.fournisseur_id
        if fournisseur_id is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="Fournisseur requis (le BC n'en a pas)"
            )
        if bon.fournisseur_id and fournisseur_id != bon.fournisseur_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Le BC {bon.reference} appartient à un autre fournisseur",
            )
        fr = await self.db.scalar(
            select(Fournisseur).where(
                Fournisseur.id == fournisseur_id,
                Fournisseur.deleted_at.is_(None),
            )
        )
        if fr is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Fournisseur introuvable"
            )
        if data.bl_id is not None:
            bl = await self.get_bl(data.bl_id)
            if bl.bon_id != bon.id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Le BL ne correspond pas au bon de commande",
                )
        reception_id = data.reception_id
        if reception_id is not None:
            rec = await self.get_reception(reception_id)
            if rec.bon_id != bon.id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="La réception ne correspond pas au bon de commande",
                )
        else:
            rec = await self._derniere_reception(bon.id)
            reception_id = rec.id if rec else None
        lignes = data.lignes
        if not lignes:
            proposition = await self.propose_facture(bon.id, date_facture=data.date_facture)
            lignes = [
                FactureLigneIn(
                    bc_ligne_id=lg.bc_ligne_id,
                    designation=lg.designation,
                    quantite=lg.quantite,
                    prix_unitaire=lg.prix_unitaire,
                    taux_tva=lg.taux_tva,
                )
                for lg in proposition.lignes
            ]
        if not lignes:
            raise R.refus(
                proposition.message
                if not data.lignes and proposition.message
                else f"Rien à facturer sur le bon {bon.reference} : toutes les quantités sont déjà facturées."
            )
        row = MgAchatFacture(
            id=uuid.uuid4(),
            reference=await self._next_ref(
                "prefix_facture", MgAchatFacture, MgAchatFacture.reference, "FAC"
            ),
            numero_fournisseur=data.numero_fournisseur,
            fournisseur_id=fournisseur_id,
            bon_id=bon.id,
            bl_id=data.bl_id,
            reception_id=reception_id,
            date_facture=data.date_facture,
            date_echeance=data.date_echeance
            or _echeance_depuis_conditions(bon.conditions_paiement, data.date_facture),
            montant_ht=data.montant_ht or Decimal("0"),
            montant_tva=data.montant_tva or Decimal("0"),
            montant_ttc=data.montant_ttc or Decimal("0"),
            devise=data.devise or bon.devise or "MRU",
            observation=data.observation,
            statut=R.FAC_RECUE,
        )
        self._apply_facture_lignes(row, lignes, bon)
        self._appliquer_entete_montants(row, data)
        rap = await self.recalculate_invoice_reconciliation(bon, row)
        self.db.add(row)
        await self.db.flush()
        await self._append_event(
            "facture", row.id, "create", f"{row.reference} ({rap.resultat})", user
        )
        await self.db.commit()
        return await self.get_facture(row.id)

    @staticmethod
    def _appliquer_entete_montants(row: MgAchatFacture, data) -> None:
        """Montants saisis depuis la facture fournisseur ; à défaut, somme des lignes."""
        fields = data.model_fields_set
        for field in ("montant_ht", "montant_tva", "montant_ttc"):
            if field in fields and getattr(data, field) is not None:
                setattr(row, field, _money(getattr(data, field)))
        if "montant_ttc" not in fields or data.montant_ttc is None:
            if any(f in fields and getattr(data, f) is not None for f in ("montant_ht", "montant_tva")):
                row.montant_ttc = _money(Decimal(row.montant_ht or 0) + Decimal(row.montant_tva or 0))

    async def update_facture(
        self, facture_id: uuid.UUID, data: FactureUpdate, user: User | None = None
    ) -> MgAchatFacture:
        row = await self.get_facture(facture_id)
        bon = await self.get_bon(row.bon_id, for_update=True)
        if data.statut is not None and data.statut.strip().upper() != row.statut:
            raise R.refus(
                "Le statut d'une facture est calculé : utilisez Valider, Annuler ou enregistrez un paiement."
            )
        self.assert_facture_editable(row)
        for field in ("numero_fournisseur", "date_facture", "date_echeance", "devise", "observation"):
            val = getattr(data, field)
            if val is not None:
                setattr(row, field, val)
        if data.lignes is not None:
            if not data.lignes:
                raise R.refus("Une facture doit comporter au moins une ligne.")
            self._apply_facture_lignes(row, data.lignes, bon)
        self._appliquer_entete_montants(row, data)
        rap = await self.recalculate_invoice_reconciliation(bon, row)
        if row.statut not in R.FACTURE_STATUTS_MODIFIABLES:
            row.statut = R.statut_paiement_facture(row.montant_ttc, row.montant_paye)
        if user is not None:
            await self._append_event("facture", row.id, "update", f"{row.reference} ({rap.resultat})", user)
        await self.db.commit()
        return await self.get_facture(row.id)

    async def validate_invoice(
        self, facture_id: uuid.UUID, user: User, motif: str | None = None
    ) -> MgAchatFacture:
        """Bon à payer. Une anomalie ne peut être acceptée qu'avec un motif tracé."""
        row = await self.get_facture(facture_id)
        bon = await self.get_bon(row.bon_id, for_update=True)
        if row.statut not in R.FACTURE_STATUTS_MODIFIABLES:
            raise R.verrou(f"Facture {row.reference} au statut {row.statut} : validation impossible.")
        rap = await self.recalculate_invoice_reconciliation(bon, row)
        motif = (motif or "").strip() or None
        if rap.resultat == "ANOMALIE" and not motif:
            raise R.refus(
                "Facture en anomalie : un motif est obligatoire pour la valider ("
                + "; ".join(rap.details[:3])
                + ")."
            )
        row.valide_at, row.valide_by, row.motif_validation = datetime.now(timezone.utc), user.id, motif
        row.statut = R.statut_paiement_facture(row.montant_ttc, row.montant_paye)
        await self._append_event(
            "facture",
            row.id,
            "valider",
            f"{row.reference} → {row.statut}" + (f" (écart accepté : {motif})" if motif else ""),
            user,
        )
        await self.db.commit()
        return await self.get_facture(row.id)

    async def cancel_invoice(self, facture_id: uuid.UUID, user: User, motif: str | None) -> MgAchatFacture:
        motif = (motif or "").strip()
        if not motif:
            raise R.refus("Un motif est obligatoire pour annuler une facture.")
        row = await self.get_facture(facture_id)
        await self.get_bon(row.bon_id, for_update=True)
        if row.statut == R.FAC_ANNULEE:
            raise R.verrou(f"La facture {row.reference} est déjà annulée.")
        pay = await self.db.scalar(
            select(MgAchatPaiement.reference).where(
                MgAchatPaiement.facture_id == row.id,
                MgAchatPaiement.deleted_at.is_(None),
                MgAchatPaiement.statut != R.PAY_ANNULE,
            ).limit(1)
        )
        if pay:
            raise R.verrou(f"Facture {row.reference} : le paiement {pay} est actif, annulez-le d'abord.")
        row.statut = R.FAC_ANNULEE
        row.annule_at, row.annule_by = datetime.now(timezone.utc), user.id
        row.observation = ((row.observation or "") + f"\n[Annulée] {motif}").strip()
        await self._append_event("facture", row.id, "annuler", f"{row.reference} annulée — {motif}", user)
        await self.db.commit()
        return await self.get_facture(row.id)

    async def three_way_match(self, bon: MgBonCommande, facture: MgAchatFacture) -> ThreeWayMatchOut:
        """Lecture seule : rapprochement ligne à ligne de CETTE facture (facturation partielle)."""
        qty_cmd = sum((_qty(lg.quantite) for lg in (bon.lignes or [])), Decimal("0"))
        qty_rec = sum((_qty(lg.quantite_recue) for lg in (bon.lignes or [])), Decimal("0"))
        bc_ttc = _money(bon.total_ttc or bon.total_ht or 0)
        fac_ttc = _money(facture.montant_ttc)
        if not facture.lignes:
            ecart_m = abs(fac_ttc - bc_ttc) > R.TOLERANCE
            return ThreeWayMatchOut(
                resultat="ANOMALIE" if ecart_m else "CONFORME",
                ecart_quantite=False,
                ecart_montant=ecart_m,
                detail=f"Montant TTC facture {format_montant(fac_ttc)} ≠ BC {format_montant(bc_ttc)}" if ecart_m else None,
                bc_total_ttc=bc_ttc,
                attendu_ttc=bc_ttc,
                facture_ttc=fac_ttc,
                qty_commandee=qty_cmd,
                qty_recue=qty_rec,
            )
        deja = await self._quantites_facturees(bon.id, sauf_facture_id=facture.id)
        rap = R.rapprocher_facture(bon.lignes or [], facture.lignes, deja, fac_ttc)
        return ThreeWayMatchOut(
            resultat=rap.resultat,
            ecart_quantite=rap.ecart_quantite,
            ecart_montant=rap.ecart_montant,
            detail="; ".join(rap.details) if rap.details else None,
            bc_total_ttc=bc_ttc,
            attendu_ttc=rap.attendu_ttc,
            facture_ttc=fac_ttc,
            qty_commandee=qty_cmd,
            qty_recue=qty_rec,
            qty_facturee=sum((_qty(lg.quantite) for lg in facture.lignes), Decimal("0")),
            lignes=[RapprochementLigneOut(**vars(e)) for e in rap.lignes],
        )

    async def justificatifs_facture(self, facture_ids: list[uuid.UUID]) -> dict[str, list[GedDocument]]:
        if not facture_ids:
            return {}
        rows = (
            await self.db.execute(
                select(GedDocument)
                .where(
                    GedDocument.module_code == GED_MODULE_ACHATS,
                    GedDocument.entity == GED_ENTITY_FACTURE,
                    GedDocument.entity_id.in_([str(i) for i in facture_ids]),
                    GedDocument.deleted_at.is_(None),
                )
                .order_by(GedDocument.created_at.desc())
            )
        ).scalars().all()
        out: dict[str, list[GedDocument]] = {}
        for d in rows:
            out.setdefault(d.entity_id, []).append(d)
        return out

    async def dossier_facture(self, facture_id: uuid.UUID, *, avec_ocr: bool = True) -> FactureDossierOut:
        facture = await self.get_facture(facture_id)
        bon = await self.db.scalar(
            select(MgBonCommande)
            .options(selectinload(MgBonCommande.lignes))
            .where(MgBonCommande.id == facture.bon_id)
        )
        docs = (await self.justificatifs_facture([facture.id])).get(str(facture.id), [])

        demande = None
        if bon is not None and bon.demande_id:
            dem = await self.db.get(MgAchatDemande, bon.demande_id)
            if dem is not None and dem.deleted_at is None:
                demande = DossierEtapeOut(
                    id=dem.id, reference=dem.reference, statut=dem.statut, date_op=dem.date_demande
                )
        receptions = [
            DossierEtapeOut(id=r.id, reference=r.reference, statut=r.statut, date_op=r.date_reception)
            for r in await self.list_receptions(bon_id=facture.bon_id)
        ]
        paiements_rows = [p for p in await self.list_paiements(facture_id=facture.id) if p.statut != "ANNULE"]
        paiements = [
            DossierEtapeOut(
                id=p.id,
                reference=p.reference,
                statut=p.statut,
                date_op=p.date_paiement or p.date_echeance,
                montant=p.montant,
            )
            for p in paiements_rows
        ]
        autres = [
            f
            for f in await self.list_factures(bon_id=facture.bon_id)
            if f.id != facture.id and f.statut != "ANNULEE"
        ]
        total_paye = _money(
            sum((Decimal(p.montant or 0) for p in paiements_rows if p.statut == R.PAY_PAYE), Decimal("0"))
        )
        reste = _money(max(Decimal("0"), Decimal(facture.montant_ttc or 0) - total_paye))
        attendu = (await self.three_way_match(bon, facture)).attendu_ttc if bon is not None else None

        controles = await self._controles_facture(facture, bon, docs, reste, attendu)

        events = await self.list_evenements("facture", facture.id)
        noms: dict[uuid.UUID, str] = {}
        user_ids = {e.user_id for e in events if e.user_id}
        if user_ids:
            for u in (await self.db.execute(select(User).where(User.id.in_(user_ids)))).scalars():
                noms[u.id] = u.full_name or u.email
        return FactureDossierOut(
            facture_id=facture.id,
            justificatifs=[
                JustificatifOut(
                    id=d.id,
                    filename=d.filename,
                    title=d.title,
                    mime_type=d.mime_type,
                    size_bytes=d.size_bytes or 0,
                    doc_type=d.doc_type,
                    created_at=d.created_at,
                    ocr_status=d.ocr_status or "pending",
                    ocr_extrait=(" ".join((d.ocr_text or "").split())[:600] or None) if avec_ocr else None,
                )
                for d in docs
            ],
            demande=demande,
            bon=(
                DossierEtapeOut(
                    id=bon.id,
                    reference=bon.reference,
                    statut=bon.statut,
                    date_op=bon.date_bc,
                    montant=bon.total_ttc,
                )
                if bon is not None
                else None
            ),
            receptions=receptions,
            paiements=paiements,
            autres_factures=[
                DossierEtapeOut(
                    id=f.id, reference=f.reference, statut=f.statut, date_op=f.date_facture, montant=f.montant_ttc
                )
                for f in autres
            ],
            controles=controles,
            evenements=[
                DossierEvenementOut(
                    action=e.action,
                    message=e.message,
                    user_nom=noms.get(e.user_id) if e.user_id else None,
                    created_at=e.created_at,
                )
                for e in events
            ],
            total_paye=total_paye,
            reste_a_payer=reste,
        )

    async def _controles_facture(
        self,
        facture: MgAchatFacture,
        bon: MgBonCommande | None,
        docs: list[GedDocument],
        reste: Decimal,
        attendu_ttc: Decimal | None = None,
    ) -> list[DossierControleOut]:
        c: list[DossierControleOut] = []
        c.append(
            DossierControleOut(
                code="JUSTIFICATIF",
                libelle="Facture du fournisseur jointe",
                ok=bool(docs),
                detail=f"{len(docs)} pièce(s)" if docs else "Joindre la facture papier / PDF reçue du fournisseur",
            )
        )
        numero = (facture.numero_fournisseur or "").strip()
        c.append(
            DossierControleOut(
                code="NUMERO",
                libelle="N° de facture fournisseur renseigné",
                ok=bool(numero),
                detail=numero or None,
            )
        )
        ocr_docs = [d for d in docs if d.ocr_status == "done" and d.ocr_text]
        if docs:
            if ocr_docs:
                texte = " ".join(d.ocr_text or "" for d in ocr_docs)
                chiffres = re.sub(r"\D", "", texte)
                montant = str(int(_money(facture.montant_ttc)))
                trouve_montant = montant in chiffres
                c.append(
                    DossierControleOut(
                        code="OCR_MONTANT",
                        libelle="Montant TTC retrouvé dans la pièce",
                        ok=trouve_montant,
                        detail=format_montant(facture.montant_ttc)
                        + (" lu sur la facture" if trouve_montant else " introuvable dans le texte lu"),
                    )
                )
                if numero:
                    compact = re.sub(r"\s", "", texte).lower()
                    trouve_num = re.sub(r"\s", "", numero).lower() in compact
                    c.append(
                        DossierControleOut(
                            code="OCR_NUMERO",
                            libelle="N° fournisseur retrouvé dans la pièce",
                            ok=trouve_num,
                            detail=numero,
                        )
                    )
            else:
                c.append(
                    DossierControleOut(
                        code="OCR_MONTANT",
                        libelle="Lecture automatique (OCR) de la pièce",
                        ok=None,
                        detail="Analyse en cours ou indisponible",
                    )
                )
        c.append(
            DossierControleOut(
                code="QUANTITES",
                libelle="Quantités conformes ligne à ligne (reçu non encore facturé)",
                ok=not facture.ecart_quantite,
            )
        )
        c.append(
            DossierControleOut(
                code="MONTANT",
                libelle="Prix, TVA et montant conformes au BC",
                ok=not facture.ecart_montant,
                detail=(
                    f"Attendu {format_montant(attendu_ttc)} · facture {format_montant(facture.montant_ttc)}"
                    if attendu_ttc is not None
                    else None
                ),
            )
        )
        recu = bon is not None and any(Decimal(lg.quantite_recue or 0) > 0 for lg in bon.lignes or [])
        c.append(
            DossierControleOut(
                code="RECEPTION",
                libelle="Marchandise réceptionnée",
                ok=recu,
                detail=None if recu else "Aucune quantité reçue sur le BC",
            )
        )
        if numero:
            doublon = await self.db.scalar(
                select(MgAchatFacture.reference).where(
                    MgAchatFacture.id != facture.id,
                    MgAchatFacture.fournisseur_id == facture.fournisseur_id,
                    func.lower(func.trim(MgAchatFacture.numero_fournisseur)) == numero.lower(),
                    MgAchatFacture.statut != "ANNULEE",
                    MgAchatFacture.deleted_at.is_(None),
                )
            )
            c.append(
                DossierControleOut(
                    code="DOUBLON",
                    libelle="Pas de doublon chez ce fournisseur",
                    ok=doublon is None,
                    detail=f"Même n° que {doublon}" if doublon else None,
                )
            )
        if facture.date_echeance and reste > 0:
            en_retard = facture.date_echeance < date.today()
            c.append(
                DossierControleOut(
                    code="ECHEANCE",
                    libelle="Échéance respectée",
                    ok=not en_retard,
                    detail=f"Reste {format_montant(reste)}" + (" — échéance dépassée" if en_retard else ""),
                )
            )
        return c

    async def match_facture(self, facture_id: uuid.UUID) -> ThreeWayMatchOut:
        facture = await self.get_facture(facture_id)
        bon = await self.get_bon(facture.bon_id)
        match = await self.three_way_match(bon, facture)
        if facture.statut in R.FACTURE_STATUTS_MODIFIABLES:
            facture.ecart_quantite = match.ecart_quantite
            facture.ecart_montant = match.ecart_montant
            facture.statut = R.FAC_ANOMALIE if match.resultat == "ANOMALIE" else R.FAC_RECUE
            await self.db.commit()
        return match

    # --- Paiements ---

    async def list_paiements(
        self, *, facture_id: uuid.UUID | None = None
    ) -> list[MgAchatPaiement]:
        stmt = (
            select(MgAchatPaiement)
            .where(MgAchatPaiement.deleted_at.is_(None), MgAchatPaiement.origine == ORIGINE_ACHAT)
            .order_by(MgAchatPaiement.created_at.desc())
        )
        if facture_id:
            stmt = stmt.where(MgAchatPaiement.facture_id == facture_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_paiement(self, paiement_id: uuid.UUID) -> MgAchatPaiement:
        row = await self.db.scalar(
            select(MgAchatPaiement).where(
                MgAchatPaiement.id == paiement_id,
                MgAchatPaiement.deleted_at.is_(None),
                MgAchatPaiement.origine == ORIGINE_ACHAT,
            )
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paiement introuvable")
        return row

    async def _facture_pour_paiement(self, facture_id: uuid.UUID) -> MgAchatFacture:
        facture = await self.db.scalar(
            select(MgAchatFacture)
            .where(
                MgAchatFacture.id == facture_id,
                MgAchatFacture.deleted_at.is_(None),
                MgAchatFacture.origine == ORIGINE_ACHAT,
            )
            .with_for_update()
        )
        if facture is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
        return facture

    async def _montant_engage(self, facture_id: uuid.UUID, *, sauf_id: uuid.UUID | None = None) -> Decimal:
        """Paiements non annulés (payés ou programmés) de la facture."""
        stmt = select(func.coalesce(func.sum(MgAchatPaiement.montant), 0)).where(
            MgAchatPaiement.facture_id == facture_id,
            MgAchatPaiement.deleted_at.is_(None),
            MgAchatPaiement.statut != R.PAY_ANNULE,
        )
        if sauf_id is not None:
            stmt = stmt.where(MgAchatPaiement.id != sauf_id)
        return _money(await self.db.scalar(stmt))

    async def recalculate_invoice_payment(self, facture: MgAchatFacture) -> None:
        await self.db.flush()
        paye = _money(
            await self.db.scalar(
                select(func.coalesce(func.sum(MgAchatPaiement.montant), 0)).where(
                    MgAchatPaiement.facture_id == facture.id,
                    MgAchatPaiement.deleted_at.is_(None),
                    MgAchatPaiement.statut == R.PAY_PAYE,
                )
            )
        )
        facture.montant_paye = paye
        if facture.statut in R.FACTURE_STATUTS_VALIDES:
            facture.statut = R.statut_paiement_facture(facture.montant_ttc, paye)

    async def create_paiement(self, data: PaiementCreate, user: User) -> MgAchatPaiement:
        facture = await self._facture_pour_paiement(data.facture_id)
        if facture.statut not in R.FACTURE_STATUTS_PAYABLES:
            raise R.verrou(
                f"Facture {facture.reference} au statut {facture.statut} : paiement impossible "
                "(la facture doit être validée et non soldée)."
            )
        if data.fournisseur_id and data.fournisseur_id != facture.fournisseur_id:
            raise R.refus("Le fournisseur du paiement doit être celui de la facture.")
        R.verifier_montant_paiement(
            data.montant, facture.montant_ttc, await self._montant_engage(facture.id)
        )
        mode, ref = (data.mode_paiement or "").strip(), (data.reference_paiement or "").strip()
        if not mode or not ref:
            bon = await self.db.get(MgBonCommande, facture.bon_id)
            if bon is not None:
                mode = mode or (bon.moyen_paiement or "").strip()
                if not ref and mode == (bon.moyen_paiement or "").strip():
                    ref = (bon.ref_paiement or "").strip()
        row = MgAchatPaiement(
            reference=await self._next_ref(
                "prefix_paiement", MgAchatPaiement, MgAchatPaiement.reference, "PAY"
            ),
            facture_id=facture.id,
            fournisseur_id=facture.fournisseur_id,
            montant=_money(data.montant),
            date_echeance=data.date_echeance or facture.date_echeance,
            date_paiement=data.date_paiement,
            mode_paiement=mode[:80] or None,
            reference_paiement=ref[:120] or None,
            observation=data.observation,
            statut=R.PAY_PAYE if data.date_paiement else R.PAY_A_PAYER,
        )
        self.db.add(row)
        await self.recalculate_invoice_payment(facture)
        await self._append_event(
            "paiement",
            row.id,
            "create",
            f"{row.reference} {format_montant(row.montant)} ({row.statut}) — facture {facture.reference} {facture.statut}",
            user,
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_paiement(
        self, paiement_id: uuid.UUID, data: PaiementUpdate, user: User | None = None
    ) -> MgAchatPaiement:
        row = await self.get_paiement(paiement_id)
        facture = await self._facture_pour_paiement(row.facture_id)
        row = await self.db.scalar(
            select(MgAchatPaiement).where(MgAchatPaiement.id == paiement_id).with_for_update()
        )
        if row.statut == R.PAY_ANNULE:
            raise R.verrou(f"Paiement {row.reference} annulé : modification impossible.")
        if data.statut is not None:
            cible = data.statut.strip().upper()
            if cible == R.PAY_ANNULE:
                raise R.refus("Utilisez Annuler (avec motif) pour annuler un paiement.")
            if cible not in (row.statut, R.PAY_PAYE):
                raise R.refus(f"Statut de paiement « {cible} » invalide.")
        if row.statut == R.PAY_PAYE and self.mode_test:
            if data.montant is not None and _money(data.montant) != _money(row.montant):
                R.verifier_montant_paiement(
                    data.montant, facture.montant_ttc, await self._montant_engage(facture.id, sauf_id=row.id)
                )
                row.montant = _money(data.montant)
            if data.date_paiement is not None:
                row.date_paiement = data.date_paiement
        elif row.statut == R.PAY_PAYE:
            if data.montant is not None and _money(data.montant) != _money(row.montant):
                raise R.verrou(f"Paiement {row.reference} déjà payé : le montant est figé (annulez-le puis ressaisissez).")
            if data.date_paiement is not None and data.date_paiement != row.date_paiement:
                raise R.verrou(f"Paiement {row.reference} déjà payé : la date de paiement est figée.")
        elif data.montant is not None and _money(data.montant) != _money(row.montant):
            R.verifier_montant_paiement(
                data.montant, facture.montant_ttc, await self._montant_engage(facture.id, sauf_id=row.id)
            )
            row.montant = _money(data.montant)
        for field in ("date_echeance", "mode_paiement", "reference_paiement", "observation"):
            val = getattr(data, field)
            if val is not None:
                setattr(row, field, val)
        passe_paye = row.statut == R.PAY_A_PAYER and (
            data.date_paiement is not None or (data.statut or "").strip().upper() == R.PAY_PAYE
        )
        if passe_paye:
            if facture.statut not in R.FACTURE_STATUTS_PAYABLES:
                raise R.verrou(f"Facture {facture.reference} au statut {facture.statut} : paiement impossible.")
            row.date_paiement = data.date_paiement or row.date_paiement or date.today()
            row.statut = R.PAY_PAYE
        await self.recalculate_invoice_payment(facture)
        if user is not None:
            await self._append_event(
                "paiement", row.id, "update", f"{row.reference} ({row.statut}) — facture {facture.statut}", user
            )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def cancel_payment(self, paiement_id: uuid.UUID, user: User, motif: str | None) -> MgAchatPaiement:
        motif = (motif or "").strip()
        if not motif:
            raise R.refus("Un motif est obligatoire pour annuler un paiement.")
        row = await self.get_paiement(paiement_id)
        facture = await self._facture_pour_paiement(row.facture_id)
        if row.statut == R.PAY_ANNULE:
            raise R.verrou(f"Le paiement {row.reference} est déjà annulé.")
        row.statut = R.PAY_ANNULE
        row.annule_at, row.annule_by = datetime.now(timezone.utc), user.id
        row.observation = ((row.observation or "") + f"\n[Annulé] {motif}").strip()
        await self.recalculate_invoice_payment(facture)
        await self._append_event(
            "paiement", row.id, "annuler", f"{row.reference} annulé — {motif} — facture {facture.statut}", user
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    # --- Mode test : suppression logique en cascade, quel que soit le statut ---

    async def _supprimer_paiements(self, facture_id: uuid.UUID, user: User, now: datetime) -> None:
        rows = (
            await self.db.execute(
                select(MgAchatPaiement).where(
                    MgAchatPaiement.facture_id == facture_id, MgAchatPaiement.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        for p in rows:
            p.deleted_at = now
            await self._append_event("paiement", p.id, "delete", f"{p.reference} (mode test)", user)

    async def _supprimer_facture(self, facture: MgAchatFacture, user: User, now: datetime) -> None:
        await self._supprimer_paiements(facture.id, user, now)
        facture.deleted_at = now
        await self._append_event("facture", facture.id, "delete", f"{facture.reference} (mode test)", user)

    async def _supprimer_reception(
        self, reception_id: uuid.UUID, bon: MgBonCommande, user: User, now: datetime
    ) -> MgAchatReception:
        row = await self.db.scalar(
            select(MgAchatReception)
            .options(selectinload(MgAchatReception.lignes))
            .where(MgAchatReception.id == reception_id, MgAchatReception.deleted_at.is_(None))
            .with_for_update()
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Réception introuvable")
        if row.statut != "ANNULEE":
            await self._contrepasser_reception(bon, row, user, f"Suppression réception {row.reference} (mode test)")
        row.deleted_at = now
        await self._append_event("reception", row.id, "delete", f"{row.reference} (mode test)", user)
        return row

    async def _supprimer_bon_cascade(self, bon: MgBonCommande, user: User) -> MgBonCommande:
        now = datetime.now(timezone.utc)
        for f in await self.list_factures(bon_id=bon.id):
            await self._supprimer_facture(f, user, now)
        rec_ids = (
            await self.db.execute(
                select(MgAchatReception.id).where(
                    MgAchatReception.bon_id == bon.id, MgAchatReception.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        for rid in rec_ids:
            await self._supprimer_reception(rid, bon, user, now)
        bon.deleted_at = now
        await self._append_event("bon", bon.id, "delete", f"{bon.reference} + suites (mode test)", user)
        await self.db.commit()
        return bon

    async def _supprimer_en_mode_test(self, kind: str, entity_id: uuid.UUID, user: User):
        now = datetime.now(timezone.utc)
        if kind == "paiement":
            row = await self.get_paiement(entity_id)
            facture = await self._facture_pour_paiement(row.facture_id)
            row.deleted_at = now
            await self._append_event("paiement", row.id, "delete", f"{row.reference} (mode test)", user)
            await self.recalculate_invoice_payment(facture)
        elif kind == "facture":
            row = await self.get_facture(entity_id)
            await self.get_bon(row.bon_id, for_update=True)
            await self._supprimer_facture(row, user, now)
        else:
            rec = await self.get_reception(entity_id)
            bon = await self.get_bon(rec.bon_id, for_update=True)
            row = await self._supprimer_reception(entity_id, bon, user, now)
            if bon.statut in R.BC_STATUTS_RECEPTION | {R.BC_RECU, R.BC_CLOTURE}:
                bon.statut = R.statut_bc_selon_receptions(bon.lignes, envoye=bon.envoye_at is not None)
        await self.db.commit()
        return row

    # --- Désactivation / suppression logique (toutes fiches) ---

    async def soft_delete_entity(
        self,
        kind: str,
        entity_id: uuid.UUID,
        user: User,
    ):
        getters = {
            "demande": self.get_demande,
            "consultation": self.get_consultation,
            "devis": self.get_devis,
            "comparaison": self.get_comparaison,
            "bl": self.get_bl,
            "reception": self.get_reception,
            "facture": self.get_facture,
            "paiement": self.get_paiement,
        }
        if kind in {"reception", "facture", "paiement"} and self.mode_test:
            return await self._supprimer_en_mode_test(kind, entity_id, user)
        if kind in {"reception", "facture", "paiement"}:
            raise R.verrou(
                "Suppression interdite : une réception, une facture ou un paiement s'annule "
                "(avec motif) pour conserver la traçabilité."
            )
        if kind == "demande":
            return await self.delete_demande(entity_id, user)
        getter = getters.get(kind)
        if getter is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Type inconnu")
        row = await getter(entity_id)
        row.deleted_at = datetime.now(timezone.utc)
        ref = getattr(row, "reference", None) or str(entity_id)
        await self._append_event(kind, row.id, "delete", ref, user)
        await self.db.commit()
        return row

    async def deactivate_entity(
        self,
        kind: str,
        entity_id: uuid.UUID,
        user: User,
        motif: str | None = None,
    ):
        """Désactivation métier : statut ANNULE(E) ou is_active=False (fournisseur).

        Les pièces du circuit passent par leur annulation contrôlée (motif, contre-passation).
        """
        if kind == "fournisseur":
            return await self.set_fournisseur_active(entity_id, False, user)
        if kind == "bon":
            return await self.cancel_bc(entity_id, user, motif)
        if kind == "reception":
            return await self.cancel_reception(entity_id, user, motif)
        if kind == "facture":
            return await self.cancel_invoice(entity_id, user, motif)
        if kind == "paiement":
            return await self.cancel_payment(entity_id, user, motif)
        if kind == "demande":
            return await self.transition_demande(entity_id, "annuler", user)

        getters = {
            "demande": (self.get_demande, "ANNULEE"),
            "consultation": (self.get_consultation, "ANNULEE"),
            "devis": (self.get_devis, "ANNULE"),
            "comparaison": (self.get_comparaison, "ANNULEE"),
            "bl": (self.get_bl, "ANNULE"),
            "reception": (self.get_reception, "ANNULEE"),
            "facture": (self.get_facture, "ANNULEE"),
            "paiement": (self.get_paiement, "ANNULE"),
            "bon": (self.get_bon, "ANNULEE"),
        }
        conf = getters.get(kind)
        if conf is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Type inconnu")
        getter, statut = conf
        row = await getter(entity_id)
        row.statut = statut
        ref = getattr(row, "reference", None) or str(entity_id)
        await self._append_event(kind, row.id, "deactivate", f"{ref} → {statut}", user)
        await self.db.commit()
        return row
