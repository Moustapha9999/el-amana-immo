"""Services Achats & Approvisionnements — cycle d'achat complet."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import Agence, User
from app.models.mg_achats import (
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
    FactureCreate,
    FactureUpdate,
    PaiementCreate,
    PaiementUpdate,
    ParametreCreate,
    ParametreUpdate,
    ReceptionCreate,
    ThreeWayMatchOut,
)
from app.schemas.mg_ops import BonCreate, BonUpdate

DEMANDE_TRANSITIONS = {
    "soumettre": ("BROUILLON", "SOUMISE"),
    "valider": ("SOUMISE", "VALIDEE"),
    "lancer_consultation": ("VALIDEE", "CONSULTATION"),
    "commander": ({"VALIDEE", "CONSULTATION"}, "COMMANDE"),
    "cloturer": ("COMMANDE", "CLOTUREE"),
    "rejeter": (None, "REJETEE"),
    "annuler": (None, "ANNULEE"),
}

BC_TRANSITIONS = {
    "soumettre": ("BROUILLON", "SOUMIS"),
    "visa_mg": ("SOUMIS", "VISA_MG"),
    "visa_dr": ("VISA_MG", "VISA_DR"),
    "valider": ("VISA_DR", "VALIDE"),
    "envoyer": ("VALIDE", "ENVOYE"),
    "cloturer": ("RECU", "CLOTURE"),
    "rejeter": (None, "REJETEE"),
    "annuler": (None, "ANNULEE"),
}

BC_STATUTS_BL = {"VALIDE", "ENVOYE", "PARTIEL", "RECU"}
BC_STATUTS_RECEPTION = {"VALIDE", "ENVOYE", "PARTIEL"}


def _money(v: Decimal) -> Decimal:
    return Decimal(v or 0).quantize(Decimal("0.01"))


def _line_ht(qty: Decimal, pu: Decimal, remise_pct: Decimal = Decimal("0")) -> Decimal:
    brut = Decimal(qty) * Decimal(pu)
    rem = brut * Decimal(remise_pct or 0) / Decimal("100")
    return _money(brut - rem)


def _line_ttc(ht: Decimal, taux_tva: Decimal = Decimal("0")) -> Decimal:
    return _money(ht * (Decimal("1") + Decimal(taux_tva or 0) / Decimal("100")))


class MgAchatsService:
    def __init__(self, db: AsyncSession):
        self.db = db

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
        bons_en_cours = await _count(
            MgBonCommande,
            MgBonCommande.deleted_at.is_(None),
            MgBonCommande.statut.in_(
                ["BROUILLON", "SOUMIS", "VISA_MG", "VISA_DR", "VALIDE", "ENVOYE", "PARTIEL"]
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
            MgAchatFacture.statut.in_(["RECUE", "VALIDEE", "ANOMALIE"]),
        )
        paiements_a_payer = await _count(
            MgAchatPaiement,
            MgAchatPaiement.deleted_at.is_(None),
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
                MgAchatFacture.date_facture >= month_start,
            )
        )
        alertes = len(await self.list_alertes())
        return {
            "demandes_ouvertes": demandes_ouvertes,
            "consultations_ouvertes": consultations_ouvertes,
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
                    MgAchatFacture.deleted_at.is_(None)
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
                MgAchatFacture.deleted_at.is_(None)
            )
        )
        montant_paiements = await self.db.scalar(
            select(func.coalesce(func.sum(MgAchatPaiement.montant), 0)).where(
                MgAchatPaiement.deleted_at.is_(None),
                MgAchatPaiement.statut == "PAYE",
            )
        )
        return {
            "nb_demandes": nb_demandes,
            "nb_bons": nb_bons,
            "nb_receptions": nb_receptions,
            "nb_factures": nb_factures,
            "montant_bons": Decimal(montant_bons or 0),
            "montant_factures": Decimal(montant_factures or 0),
            "montant_paiements": Decimal(montant_paiements or 0),
        }

    # --- Fournisseurs ---

    async def list_fournisseurs(self, q: str | None = None) -> list[Fournisseur]:
        stmt = (
            select(Fournisseur)
            .where(Fournisseur.is_active.is_(True), Fournisseur.deleted_at.is_(None))
            .order_by(Fournisseur.raison_sociale)
        )
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    Fournisseur.raison_sociale.ilike(like),
                    Fournisseur.code.ilike(like),
                )
            )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_fournisseur_summary(self, fournisseur_id: uuid.UUID) -> dict:
        fr = await self.db.get(Fournisseur, fournisseur_id)
        if not fr or fr.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Fournisseur introuvable")
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
        return {
            "id": fr.id,
            "code": fr.code,
            "raison_sociale": fr.raison_sociale,
            "telephone": fr.telephone,
            "email": fr.email,
            "adresse": fr.adresse,
            "nb_bons": nb_bons,
            "nb_devis": nb_devis,
            "nb_factures": nb_factures,
            "montant_bons": Decimal(montant_bons or 0),
        }

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
            type_achat=data.type_achat or "FOURNITURE",
            priorite=data.priorite or "NORMAL",
            projet=data.projet,
            motif=data.motif,
            date_souhaitee=data.date_souhaitee,
            budget_estime=data.budget_estime,
            observation=data.observation,
            statut="BROUILLON",
        )
        self._apply_demande_lignes(demande, data.lignes)
        self.db.add(demande)
        await self.db.flush()
        await self._append_event("demande", demande.id, "create", f"Création {demande.reference}", user)
        await self.db.commit()
        return await self.get_demande(demande.id)

    async def update_demande(self, demande_id: uuid.UUID, data: DemandeUpdate) -> MgAchatDemande:
        demande = await self.get_demande(demande_id)
        if demande.statut not in {"BROUILLON", "SOUMISE"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Demande non modifiable")
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
                setattr(demande, field, val)
        if data.lignes is not None:
            self._apply_demande_lignes(demande, data.lignes)
        await self.db.commit()
        return await self.get_demande(demande.id)

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
        if key in {"rejeter", "annuler"} and demande.statut in {
            "CLOTUREE",
            "REJETEE",
            "ANNULEE",
        }:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Statut final")
        demande.statut = new_statut
        await self._append_event(
            "demande",
            demande.id,
            key,
            f"{demande.reference} → {new_statut}",
            user,
        )
        await self.db.commit()
        return await self.get_demande(demande.id)

    # --- Consultations ---

    async def list_consultations(
        self, *, statut: str | None = None
    ) -> list[MgAchatConsultation]:
        stmt = (
            select(MgAchatConsultation)
            .options(selectinload(MgAchatConsultation.fournisseurs))
            .where(MgAchatConsultation.deleted_at.is_(None))
            .order_by(MgAchatConsultation.date_consultation.desc())
        )
        if statut:
            stmt = stmt.where(MgAchatConsultation.statut == statut)
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

    def _set_consultation_fournisseurs(
        self, consultation: MgAchatConsultation, fournisseur_ids: list[uuid.UUID]
    ) -> None:
        consultation.fournisseurs.clear()
        for fid in fournisseur_ids:
            consultation.fournisseurs.append(
                MgAchatConsultationFournisseur(fournisseur_id=fid)
            )

    async def create_consultation(
        self, data: ConsultationCreate, user: User
    ) -> MgAchatConsultation:
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
        self, consultation_id: uuid.UUID, data: ConsultationUpdate
    ) -> MgAchatConsultation:
        row = await self.get_consultation(consultation_id)
        for field in (
            "date_consultation",
            "demande_id",
            "agence_id",
            "objet",
            "date_limite",
            "observation",
            "statut",
        ):
            val = getattr(data, field)
            if val is not None:
                setattr(row, field, val if field != "objet" else val.strip())
        if data.fournisseur_ids is not None:
            self._set_consultation_fournisseurs(row, data.fournisseur_ids)
        await self.db.commit()
        return await self.get_consultation(row.id)

    def consultation_to_out(self, row: MgAchatConsultation) -> dict:
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
            "fournisseur_ids": [f.fournisseur_id for f in row.fournisseurs],
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
            snapshot_json=data.snapshot_json,
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
        if row.statut not in {"BROUILLON", "EN_COURS"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Comparaison déjà validée")
        row.fournisseur_retenu_id = data.fournisseur_retenu_id
        row.motif_choix = data.motif_choix
        row.statut = "VALIDEE"
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

    async def get_bon(self, bon_id: uuid.UUID) -> MgBonCommande:
        bon = await self.db.scalar(
            select(MgBonCommande)
            .options(selectinload(MgBonCommande.lignes))
            .where(MgBonCommande.id == bon_id, MgBonCommande.deleted_at.is_(None))
        )
        if not bon:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bon de commande introuvable")
        return bon

    def _apply_bc_lignes(self, bon: MgBonCommande, lignes) -> None:
        bon.lignes.clear()
        total_ht = Decimal("0")
        total_tva = Decimal("0")
        total_ttc = Decimal("0")
        for i, row in enumerate(lignes):
            remise = getattr(row, "remise_pct", None) or Decimal("0")
            tva = getattr(row, "taux_tva", None) or Decimal("0")
            ht = _line_ht(row.quantite, row.prix_unitaire, remise)
            ttc = _line_ttc(ht, tva)
            tva_amt = _money(ttc - ht)
            total_ht += ht
            total_tva += tva_amt
            total_ttc += ttc
            bon.lignes.append(
                MgBcLigne(
                    code_produit=row.code_produit,
                    departement=row.departement,
                    description=row.description.strip(),
                    quantite=row.quantite,
                    quantite_recue=Decimal("0"),
                    article_id=getattr(row, "article_id", None),
                    uom=row.uom or "U",
                    prix_unitaire=row.prix_unitaire,
                    prix_total=ht,
                    remise_pct=remise,
                    taux_tva=tva,
                    total_ttc=ttc,
                    stockable=bool(getattr(row, "stockable", False)),
                    sort_order=i,
                )
            )
        bon.total_ht = _money(total_ht)
        bon.total_tva = _money(total_tva)
        bon.total_ttc = _money(total_ttc)

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
        self._apply_bc_lignes(bon, data.lignes)
        self.db.add(bon)
        await self.db.flush()
        await self._append_event("bon", bon.id, "create", bon.reference, user)
        await self.db.commit()
        return await self.get_bon(bon.id)

    async def update_bon(self, bon_id: uuid.UUID, data: BonUpdate) -> MgBonCommande:
        bon = await self.get_bon(bon_id)
        if bon.statut == "CLOTURE":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bon clôturé : non modifiable")
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
            "moyen_paiement",
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
        if data.lignes is not None:
            self._apply_bc_lignes(bon, data.lignes)
        await self.db.commit()
        return await self.get_bon(bon.id)

    async def delete_bon(self, bon_id: uuid.UUID, user: User) -> MgBonCommande:
        """Suppression logique (hors liste) — autorisée quel que soit le statut."""
        bon = await self.get_bon(bon_id)
        bon.deleted_at = datetime.now(timezone.utc)
        await self._append_event("bon", bon.id, "delete", bon.reference, user)
        await self.db.commit()
        return bon

    async def transition_bon(self, bon_id: uuid.UUID, action: str, user: User) -> MgBonCommande:
        bon = await self.get_bon(bon_id)
        key = action.strip().lower()
        if key not in BC_TRANSITIONS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Action invalide")
        expected, new_statut = BC_TRANSITIONS[key]
        if expected is not None:
            if isinstance(expected, (set, frozenset)):
                if bon.statut not in expected:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=f"Transition impossible depuis {bon.statut} (attendu : {', '.join(sorted(expected))})",
                    )
            elif bon.statut != expected:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Transition impossible depuis {bon.statut} (attendu : {expected})",
                )
        if key in {"rejeter", "annuler"} and bon.statut in {
            "RECU",
            "CLOTURE",
            "REJETEE",
            "ANNULEE",
            "PARTIEL",
        }:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Annulation impossible : statut {bon.statut}",
            )
        if key == "annuler" and any(
            (getattr(l, "quantite_recue", None) or 0) > 0 for l in (bon.lignes or [])
        ):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Annulation impossible : réception déjà commencée",
            )
        now = datetime.now(timezone.utc)
        if key == "visa_mg":
            bon.visa_mg_at, bon.visa_mg_by = now, user.id
        if key == "visa_dr":
            bon.visa_dr_at, bon.visa_dr_by = now, user.id
        bon.statut = new_statut
        await self._append_event("bon", bon.id, key, f"{bon.reference} → {new_statut}", user)
        await self.db.commit()
        return await self.get_bon(bon.id)

    # --- BL ---

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

    async def create_reception(self, data: ReceptionCreate, user: User) -> MgAchatReception:
        from app.services.mg_stock_service import MgStockService

        bon = await self.get_bon(data.bon_id)
        if bon.statut not in BC_STATUTS_RECEPTION:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Réception impossible pour statut BC {bon.statut}",
            )
        by_id = {l.id: l for l in bon.lignes}
        reception = MgAchatReception(
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
            ligne = by_id.get(payload.bc_ligne_id)
            if ligne is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Ligne {payload.bc_ligne_id} absente du bon",
                )
            deja = Decimal(ligne.quantite_recue or 0)
            reste = Decimal(ligne.quantite or 0) - deja
            qty = Decimal(payload.quantite_recue)
            if qty > reste:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Quantité {qty} > reste {reste} pour « {ligne.description} »",
                )
            article_id = payload.article_id or ligne.article_id
            if ligne.stockable and article_id:
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
                    motif=f"Réception achat {bon.reference}",
                    source_id=bon.id,
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

        if all(Decimal(l.quantite_recue or 0) >= Decimal(l.quantite or 0) for l in bon.lignes):
            bon.statut = "RECU"
            reception.statut = "COMPLETE"
        else:
            bon.statut = "PARTIEL"
            reception.statut = "PARTIEL"

        self.db.add(reception)
        await self.db.flush()
        for rl in reception.lignes:
            # patch source_id after flush if stock mvts were created — already committed via flush
            pass
        await self._append_event(
            "reception",
            reception.id,
            "create",
            f"{reception.reference} → BC {bon.statut}",
            user,
        )
        await self.db.commit()
        return await self.get_reception(reception.id)

    # --- Factures / 3-way match ---

    async def list_factures(self, *, bon_id: uuid.UUID | None = None) -> list[MgAchatFacture]:
        stmt = (
            select(MgAchatFacture)
            .options(selectinload(MgAchatFacture.lignes))
            .where(MgAchatFacture.deleted_at.is_(None))
            .order_by(MgAchatFacture.date_facture.desc())
        )
        if bon_id:
            stmt = stmt.where(MgAchatFacture.bon_id == bon_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_facture(self, facture_id: uuid.UUID) -> MgAchatFacture:
        row = await self.db.scalar(
            select(MgAchatFacture)
            .options(selectinload(MgAchatFacture.lignes))
            .where(MgAchatFacture.id == facture_id, MgAchatFacture.deleted_at.is_(None))
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
        return row

    def _apply_facture_lignes(self, facture: MgAchatFacture, lignes) -> None:
        facture.lignes.clear()
        total = Decimal("0")
        for i, row in enumerate(lignes):
            ht = _line_ht(row.quantite, row.prix_unitaire)
            total += ht
            facture.lignes.append(
                MgAchatFactureLigne(
                    designation=row.designation.strip(),
                    quantite=row.quantite,
                    prix_unitaire=row.prix_unitaire,
                    total_ht=ht,
                    sort_order=i,
                )
            )
        if lignes:
            facture.montant_ht = _money(total)

    async def create_facture(self, data: FactureCreate, user: User) -> MgAchatFacture:
        bon = await self.get_bon(data.bon_id)
        row = MgAchatFacture(
            reference=await self._next_ref(
                "prefix_facture", MgAchatFacture, MgAchatFacture.reference, "FAC"
            ),
            numero_fournisseur=data.numero_fournisseur,
            fournisseur_id=data.fournisseur_id,
            bon_id=bon.id,
            bl_id=data.bl_id,
            reception_id=data.reception_id,
            date_facture=data.date_facture,
            date_echeance=data.date_echeance,
            montant_ht=data.montant_ht or Decimal("0"),
            montant_tva=data.montant_tva or Decimal("0"),
            montant_ttc=data.montant_ttc or Decimal("0"),
            devise=data.devise or "MRU",
            observation=data.observation,
            statut="RECUE",
        )
        self._apply_facture_lignes(row, data.lignes)
        if data.lignes and data.montant_ttc is None:
            row.montant_ttc = _money(row.montant_ht + row.montant_tva)
        match = self.three_way_match(bon, row)
        row.ecart_quantite = match.ecart_quantite
        row.ecart_montant = match.ecart_montant
        if match.resultat == "ANOMALIE":
            row.statut = "ANOMALIE"
        self.db.add(row)
        await self.db.flush()
        await self._append_event(
            "facture", row.id, "create", f"{row.reference} ({match.resultat})", user
        )
        await self.db.commit()
        return await self.get_facture(row.id)

    async def update_facture(
        self, facture_id: uuid.UUID, data: FactureUpdate
    ) -> MgAchatFacture:
        row = await self.get_facture(facture_id)
        for field in (
            "numero_fournisseur",
            "date_facture",
            "date_echeance",
            "montant_ht",
            "montant_tva",
            "montant_ttc",
            "devise",
            "statut",
            "observation",
        ):
            val = getattr(data, field)
            if val is not None:
                setattr(row, field, val)
        if data.lignes is not None:
            self._apply_facture_lignes(row, data.lignes)
        bon = await self.get_bon(row.bon_id)
        match = self.three_way_match(bon, row)
        row.ecart_quantite = match.ecart_quantite
        row.ecart_montant = match.ecart_montant
        await self.db.commit()
        return await self.get_facture(row.id)

    def three_way_match(
        self, bon: MgBonCommande, facture: MgAchatFacture
    ) -> ThreeWayMatchOut:
        qty_cmd = sum((Decimal(l.quantite or 0) for l in (bon.lignes or [])), Decimal("0"))
        qty_rec = sum((Decimal(l.quantite_recue or 0) for l in (bon.lignes or [])), Decimal("0"))
        qty_fac = sum(
            (Decimal(l.quantite or 0) for l in (facture.lignes or [])), Decimal("0")
        )
        if not facture.lignes:
            qty_fac = qty_cmd  # pas de lignes → on ne flaggue pas qty
        bc_ttc = Decimal(bon.total_ttc or bon.total_ht or 0)
        fac_ttc = Decimal(facture.montant_ttc or 0)
        ecart_q = False
        ecart_m = False
        details: list[str] = []
        if facture.lignes and qty_fac != qty_rec and qty_fac != qty_cmd:
            # Facturé doit coller au reçu (idéalement) ou à la commande
            if qty_rec > 0 and qty_fac != qty_rec:
                ecart_q = True
                details.append(f"Qté facturée {qty_fac} ≠ reçue {qty_rec}")
            elif qty_rec == 0 and qty_fac != qty_cmd:
                ecart_q = True
                details.append(f"Qté facturée {qty_fac} ≠ commandée {qty_cmd}")
        if abs(fac_ttc - bc_ttc) > Decimal("0.01"):
            ecart_m = True
            details.append(f"Montant TTC facture {fac_ttc} ≠ BC {bc_ttc}")
        resultat = "ANOMALIE" if (ecart_q or ecart_m) else "CONFORME"
        return ThreeWayMatchOut(
            resultat=resultat,
            ecart_quantite=ecart_q,
            ecart_montant=ecart_m,
            detail="; ".join(details) if details else None,
            bc_total_ttc=bc_ttc,
            facture_ttc=fac_ttc,
            qty_commandee=qty_cmd,
            qty_recue=qty_rec,
            qty_facturee=qty_fac if facture.lignes else None,
        )

    async def match_facture(self, facture_id: uuid.UUID) -> ThreeWayMatchOut:
        facture = await self.get_facture(facture_id)
        bon = await self.get_bon(facture.bon_id)
        match = self.three_way_match(bon, facture)
        facture.ecart_quantite = match.ecart_quantite
        facture.ecart_montant = match.ecart_montant
        if match.resultat == "ANOMALIE" and facture.statut == "RECUE":
            facture.statut = "ANOMALIE"
        await self.db.commit()
        return match

    # --- Paiements ---

    async def list_paiements(
        self, *, facture_id: uuid.UUID | None = None
    ) -> list[MgAchatPaiement]:
        stmt = (
            select(MgAchatPaiement)
            .where(MgAchatPaiement.deleted_at.is_(None))
            .order_by(MgAchatPaiement.created_at.desc())
        )
        if facture_id:
            stmt = stmt.where(MgAchatPaiement.facture_id == facture_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_paiement(self, paiement_id: uuid.UUID) -> MgAchatPaiement:
        row = await self.db.scalar(
            select(MgAchatPaiement).where(
                MgAchatPaiement.id == paiement_id, MgAchatPaiement.deleted_at.is_(None)
            )
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paiement introuvable")
        return row

    async def create_paiement(self, data: PaiementCreate, user: User) -> MgAchatPaiement:
        facture = await self.get_facture(data.facture_id)
        row = MgAchatPaiement(
            reference=await self._next_ref(
                "prefix_paiement", MgAchatPaiement, MgAchatPaiement.reference, "PAY"
            ),
            facture_id=facture.id,
            fournisseur_id=data.fournisseur_id or facture.fournisseur_id,
            montant=data.montant,
            date_echeance=data.date_echeance or facture.date_echeance,
            date_paiement=data.date_paiement,
            mode_paiement=data.mode_paiement,
            reference_paiement=data.reference_paiement,
            observation=data.observation,
            statut="PAYE" if data.date_paiement else "A_PAYER",
        )
        self.db.add(row)
        await self.db.flush()
        await self._append_event("paiement", row.id, "create", row.reference, user)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_paiement(
        self, paiement_id: uuid.UUID, data: PaiementUpdate
    ) -> MgAchatPaiement:
        row = await self.get_paiement(paiement_id)
        for field in (
            "montant",
            "date_echeance",
            "date_paiement",
            "mode_paiement",
            "reference_paiement",
            "statut",
            "observation",
        ):
            val = getattr(data, field)
            if val is not None:
                setattr(row, field, val)
        if data.date_paiement and row.statut == "A_PAYER":
            row.statut = "PAYE"
        await self.db.commit()
        await self.db.refresh(row)
        return row
