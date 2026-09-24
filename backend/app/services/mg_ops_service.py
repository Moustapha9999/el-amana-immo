"""Services Moyens Généraux Phase 2."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import Agence, User
from app.models.ged import GedDocument
from app.models.mg_ops import MgBcLigne, MgBonCommande, MgContrat, MgNoteFrais, MgNoteFraisLigne
from app.models.organisation import Fournisseur
from app.schemas.mg_ops import (
    BonCreate,
    BonUpdate,
    ContratCreate,
    ContratUpdate,
    NoteCreate,
    NoteUpdate,
)

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

NOTE_TRANSITIONS = {
    "soumettre": ("BROUILLON", "SOUMIS"),
    "visa_mg": ("SOUMIS", "VISA_MG"),
    "visa_dr": ("VISA_MG", "VISA_DR"),
    "valider": ("VISA_DR", "VALIDEE"),
    "rejeter": (None, "REJETEE"),
    "annuler": (None, "ANNULEE"),
}


class MgOpsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _next_ref(self, prefix: str, model, field) -> str:
        year = date.today().year
        like = f"{prefix}-{year}%"
        count = await self.db.scalar(select(func.count()).select_from(model).where(field.ilike(like)))
        return f"{prefix}-{year}{int(count or 0) + 1:04d}"

    async def list_fournisseurs(self) -> list[Fournisseur]:
        q = (
            select(Fournisseur)
            .where(Fournisseur.is_active.is_(True), Fournisseur.deleted_at.is_(None))
            .order_by(Fournisseur.raison_sociale)
        )
        return list((await self.db.execute(q)).scalars().all())

    # --- Bons de commande ---

    async def list_bons(self, statut: str | None = None) -> list[MgBonCommande]:
        stmt = (
            select(MgBonCommande)
            .options(selectinload(MgBonCommande.lignes))
            .where(MgBonCommande.deleted_at.is_(None))
            .order_by(MgBonCommande.date_bc.desc())
        )
        if statut:
            stmt = stmt.where(MgBonCommande.statut == statut)
        return list((await self.db.execute(stmt)).scalars().all())

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
        total = Decimal("0")
        total_tva = Decimal("0")
        total_ttc = Decimal("0")
        for i, row in enumerate(lignes):
            remise = Decimal(getattr(row, "remise_pct", None) or 0)
            taux = Decimal(getattr(row, "taux_tva", None) or 0)
            brut = (row.quantite * row.prix_unitaire).quantize(Decimal("0.01"))
            pt = (brut * (Decimal("1") - remise / Decimal("100"))).quantize(Decimal("0.01"))
            ttc = (pt * (Decimal("1") + taux / Decimal("100"))).quantize(Decimal("0.01"))
            total += pt
            total_tva += (ttc - pt).quantize(Decimal("0.01"))
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
                    prix_total=pt,
                    remise_pct=remise,
                    taux_tva=taux,
                    total_ttc=ttc,
                    stockable=bool(getattr(row, "stockable", False)),
                    sort_order=i,
                )
            )
        bon.total_ht = total
        bon.total_tva = total_tva
        bon.total_ttc = total_ttc

    async def create_bon(self, data: BonCreate, user: User) -> MgBonCommande:
        bon = MgBonCommande(
            reference=await self._next_ref("BEA", MgBonCommande, MgBonCommande.reference),
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
            conditions=data.conditions,
            incoterm=data.incoterm,
            conditions_paiement=data.conditions_paiement,
            moyen_paiement=data.moyen_paiement,
            demandeur_nom=data.demandeur_nom,
            demandeur_date=data.demandeur_date,
            observation=data.observation,
            statut="BROUILLON",
        )
        if data.fournisseur_id and not data.fournisseur_raison_sociale:
            fr = await self.db.get(Fournisseur, data.fournisseur_id)
            if fr:
                bon.fournisseur_raison_sociale = fr.raison_sociale
                bon.fournisseur_telephone = bon.fournisseur_telephone or fr.telephone
                bon.fournisseur_adresse = bon.fournisseur_adresse or fr.adresse
        self._apply_bc_lignes(bon, data.lignes)
        self.db.add(bon)
        await self.db.commit()
        return await self.get_bon(bon.id)

    async def update_bon(self, bon_id: uuid.UUID, data: BonUpdate) -> MgBonCommande:
        bon = await self.get_bon(bon_id)
        if bon.statut not in {"BROUILLON", "SOUMIS"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bon non modifiable")
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
        ):
            val = getattr(data, field)
            if val is not None:
                setattr(bon, field, val)
        if data.lignes is not None:
            self._apply_bc_lignes(bon, data.lignes)
        await self.db.commit()
        return await self.get_bon(bon.id)

    async def transition_bon(self, bon_id: uuid.UUID, action: str, user: User) -> MgBonCommande:
        bon = await self.get_bon(bon_id)
        key = action.strip().lower()
        if key not in BC_TRANSITIONS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Action invalide")
        expected, new_statut = BC_TRANSITIONS[key]
        if expected and bon.statut != expected:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Transition impossible depuis {bon.statut}",
            )
        if key in {"rejeter", "annuler"} and bon.statut in {"VALIDE", "REJETEE", "ANNULEE"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Statut final")
        now = datetime.now(timezone.utc)
        if key == "visa_mg":
            bon.visa_mg_at, bon.visa_mg_by = now, user.id
        if key == "visa_dr":
            bon.visa_dr_at, bon.visa_dr_by = now, user.id
        bon.statut = new_statut
        await self.db.commit()
        return await self.get_bon(bon.id)

    # --- Notes de frais ---

    async def list_notes(self, statut: str | None = None) -> list[MgNoteFrais]:
        stmt = (
            select(MgNoteFrais)
            .options(selectinload(MgNoteFrais.lignes))
            .where(MgNoteFrais.deleted_at.is_(None))
            .order_by(MgNoteFrais.date_demande.desc())
        )
        if statut:
            stmt = stmt.where(MgNoteFrais.statut == statut)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_note(self, note_id: uuid.UUID) -> MgNoteFrais:
        note = await self.db.scalar(
            select(MgNoteFrais)
            .options(selectinload(MgNoteFrais.lignes))
            .where(MgNoteFrais.id == note_id, MgNoteFrais.deleted_at.is_(None))
        )
        if not note:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Note de frais introuvable")
        return note

    def _apply_note_lignes(self, note: MgNoteFrais, lignes) -> None:
        note.lignes.clear()
        total = Decimal("0")
        for i, row in enumerate(lignes):
            total += row.montant
            note.lignes.append(
                MgNoteFraisLigne(
                    date_depense=row.date_depense,
                    description=row.description.strip(),
                    motif=row.motif,
                    montant=row.montant,
                    mode_reglement=row.mode_reglement,
                    sort_order=i,
                )
            )
        note.total_mru = total

    async def create_note(self, data: NoteCreate, user: User) -> MgNoteFrais:
        note = MgNoteFrais(
            reference=await self._next_ref("NF", MgNoteFrais, MgNoteFrais.reference),
            date_demande=data.date_demande,
            agence_id=data.agence_id,
            demandeur_id=user.id,
            demandeur_nom=data.demandeur_nom or user.full_name,
            departement=data.departement,
            fonction=data.fonction,
            observation=data.observation,
            statut="BROUILLON",
        )
        if data.agence_id:
            ag = await self.db.get(Agence, data.agence_id)
            if ag:
                note.agence_libelle_snapshot = ag.libelle
        self._apply_note_lignes(note, data.lignes)
        self.db.add(note)
        await self.db.commit()
        return await self.get_note(note.id)

    async def update_note(self, note_id: uuid.UUID, data: NoteUpdate) -> MgNoteFrais:
        note = await self.get_note(note_id)
        if note.statut not in {"BROUILLON", "SOUMIS"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Note non modifiable")
        for field in ("date_demande", "demandeur_nom", "departement", "fonction", "observation"):
            val = getattr(data, field)
            if val is not None:
                setattr(note, field, val)
        if data.agence_id is not None:
            note.agence_id = data.agence_id
            ag = await self.db.get(Agence, data.agence_id)
            note.agence_libelle_snapshot = ag.libelle if ag else None
        if data.lignes is not None:
            self._apply_note_lignes(note, data.lignes)
        await self.db.commit()
        return await self.get_note(note.id)

    async def transition_note(self, note_id: uuid.UUID, action: str, user: User) -> MgNoteFrais:
        note = await self.get_note(note_id)
        key = action.strip().lower()
        if key not in NOTE_TRANSITIONS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Action invalide")
        expected, new_statut = NOTE_TRANSITIONS[key]
        if expected and note.statut != expected:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Transition impossible depuis {note.statut}",
            )
        now = datetime.now(timezone.utc)
        if key == "visa_mg":
            note.visa_mg_at, note.visa_mg_by = now, user.id
        if key == "visa_dr":
            note.visa_dr_at, note.visa_dr_by = now, user.id
        note.statut = new_statut
        await self.db.commit()
        return await self.get_note(note.id)

    # --- Contrats ---

    async def list_contrats(self, statut: str | None = None) -> list[MgContrat]:
        stmt = (
            select(MgContrat)
            .where(MgContrat.deleted_at.is_(None))
            .order_by(MgContrat.date_debut.desc())
        )
        if statut:
            stmt = stmt.where(MgContrat.statut == statut)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_contrat(self, contrat_id: uuid.UUID) -> MgContrat:
        c = await self.db.scalar(
            select(MgContrat).where(MgContrat.id == contrat_id, MgContrat.deleted_at.is_(None))
        )
        if not c:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contrat introuvable")
        return c

    async def create_contrat(self, data: ContratCreate) -> MgContrat:
        c = MgContrat(
            reference=await self._next_ref("CT", MgContrat, MgContrat.reference),
            titre=data.titre.strip(),
            fournisseur_id=data.fournisseur_id,
            fournisseur_snapshot=data.fournisseur_snapshot,
            date_debut=data.date_debut,
            date_fin=data.date_fin,
            montant=data.montant,
            periodicite=data.periodicite or "ANNUEL",
            prochain_echeance=data.prochain_echeance,
            alerte_jours=data.alerte_jours,
            observation=data.observation,
            statut="ACTIF",
        )
        if data.fournisseur_id and not data.fournisseur_snapshot:
            fr = await self.db.get(Fournisseur, data.fournisseur_id)
            if fr:
                c.fournisseur_snapshot = fr.raison_sociale
        self.db.add(c)
        await self.db.commit()
        await self.db.refresh(c)
        return c

    async def update_contrat(self, contrat_id: uuid.UUID, data: ContratUpdate) -> MgContrat:
        c = await self.get_contrat(contrat_id)
        for field in (
            "titre",
            "fournisseur_id",
            "fournisseur_snapshot",
            "date_debut",
            "date_fin",
            "montant",
            "periodicite",
            "prochain_echeance",
            "alerte_jours",
            "statut",
            "observation",
        ):
            val = getattr(data, field)
            if val is not None:
                setattr(c, field, val)
        await self.db.commit()
        await self.db.refresh(c)
        return c

    async def list_alertes(self) -> list[MgContrat]:
        today = date.today()
        rows = await self.list_contrats(statut="ACTIF")
        out = []
        for c in rows:
            horizon = today + timedelta(days=c.alerte_jours or 30)
            if c.prochain_echeance and c.prochain_echeance <= horizon:
                out.append(c)
            elif c.date_fin and c.date_fin <= horizon:
                out.append(c)
        return out

    # --- Archives GED ---

    async def list_archives(
        self, *, module_code: str | None = None, q: str | None = None, page: int = 1, size: int = 50
    ) -> tuple[list[GedDocument], int]:
        filters = [
            GedDocument.espace_code == "moyens-generaux",
            GedDocument.deleted_at.is_(None),
        ]
        if module_code:
            filters.append(GedDocument.module_code == module_code)
        if q:
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    GedDocument.filename.ilike(like),
                    GedDocument.module_code.ilike(like),
                    GedDocument.entity.ilike(like),
                )
            )
        total = int(
            (await self.db.scalar(select(func.count()).select_from(GedDocument).where(*filters)))
            or 0
        )
        page = max(1, page)
        size = max(1, min(size, 500))
        stmt = (
            select(GedDocument)
            .where(*filters)
            .order_by(GedDocument.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list((await self.db.execute(stmt)).scalars().all()), total
