"""Paiements des notes de frais — la note porte ce qui est dû, le paiement ce qui a été réglé."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import User
from app.models.mg_ops import MgNoteFrais, MgNoteFraisPaiement
from app.schemas.mg_notes import (
    MODES_PAIEMENT,
    NotePaiementCreate,
    NotePaiementUpdate,
)
from app.services.mg_notes_events import audit_notes, notify_notes_user
from app.services.mg_notes_service import MgNotesService

PAYABLE = {"VALIDEE", "MISE_EN_PAIEMENT", "PARTIELLEMENT_PAYEE"}
# Statuts pilotés par les paiements (recalculés à chaque opération).
PAYMENT_DRIVEN = {"VALIDEE", "MISE_EN_PAIEMENT", "PARTIELLEMENT_PAYEE", "PAYEE"}
# Note clôturée ou archivée : ses paiements sont figés.
FIGE = {"CLOTUREE", "ARCHIVEE"}

SORTS = {
    "date_paiement": MgNoteFraisPaiement.date_paiement,
    "numero": MgNoteFraisPaiement.numero,
    "montant": MgNoteFraisPaiement.montant,
    "mode_paiement": MgNoteFraisPaiement.mode_paiement,
    "statut": MgNoteFraisPaiement.statut,
    "created_at": MgNoteFraisPaiement.created_at,
    "registre": MgNoteFrais.reference,
    "beneficiaire": MgNoteFrais.demandeur_nom,
}

_ZERO = Decimal("0")


def _bad(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=detail)


def registre_out(note: MgNoteFrais, nb_paiements: int = 0) -> dict:
    total = note.total_mru or _ZERO
    paye = note.montant_paye or _ZERO
    return {
        "id": note.id,
        "reference": note.reference,
        "date_demande": note.date_demande,
        "beneficiaire": note.demandeur_nom,
        "departement": note.departement,
        "fonction": note.fonction,
        "motif": note.objet,
        "intitule": note.agence_libelle_snapshot,
        "statut": note.statut,
        "statut_paiement": note.statut_paiement,
        "montant_initial": total,
        "montant_paye": paye,
        "solde": max(_ZERO, total - paye),
        "devise": note.devise or "MRU",
        "nb_paiements": nb_paiements,
    }


def paiement_out(p: MgNoteFraisPaiement, nb_paiements: int = 0) -> dict:
    return {
        "id": p.id,
        "numero": p.numero,
        "note_id": p.note_id,
        "date_paiement": p.date_paiement,
        "montant": p.montant,
        "mode_paiement": p.mode_paiement,
        "reference": p.reference,
        "numero_cheque": p.numero_cheque,
        "banque": p.banque,
        "compte": p.compte,
        "observation": p.observation,
        "statut": p.statut,
        "motif_annulation": p.motif_annulation,
        "annule_at": p.annule_at,
        "annule_par_nom": p.annule_par_nom,
        "created_by_nom": p.created_by_nom,
        "updated_by_nom": p.updated_by_nom,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "registre": registre_out(p.note, nb_paiements),
    }


def _clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def check_mode_details(
    mode: str, *, reference: str | None, numero_cheque: str | None
) -> None:
    if mode not in MODES_PAIEMENT:
        raise _bad(f"Mode de paiement inconnu : {mode}")
    if mode == "Chèque" and not numero_cheque:
        raise _bad("Numéro de chèque obligatoire pour un paiement par chèque")
    if mode == "Virement" and not reference:
        raise _bad("Référence du virement obligatoire")
    if mode == "Amanty" and not reference:
        raise _bad("Référence de la transaction Amanty obligatoire")


class MgNotesPaiementsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.notes = MgNotesService(db)

    # --- droits ---

    def _require(self, user: User, code: str, detail: str) -> None:
        if code not in self.notes._user_perms(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=detail)

    def _access_filters(self, user: User) -> list:
        filters = [MgNoteFraisPaiement.deleted_at.is_(None), MgNoteFrais.deleted_at.is_(None)]
        if not self.notes._can_supervise(user):
            filters.append(MgNoteFrais.demandeur_id == user.id)
        return filters

    # --- lecture ---

    async def _counts(self, note_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not note_ids:
            return {}
        rows = await self.db.execute(
            select(MgNoteFraisPaiement.note_id, func.count())
            .where(
                MgNoteFraisPaiement.note_id.in_(note_ids),
                MgNoteFraisPaiement.deleted_at.is_(None),
                MgNoteFraisPaiement.statut == "VALIDE",
            )
            .group_by(MgNoteFraisPaiement.note_id)
        )
        return {nid: int(c) for nid, c in rows.all()}

    async def list_paiements(
        self,
        user: User,
        *,
        q: str | None = None,
        statut: str | None = None,
        mode_paiement: str | None = None,
        beneficiaire: str | None = None,
        note_id: uuid.UUID | None = None,
        registre: str | None = None,
        date_debut: date | None = None,
        date_fin: date | None = None,
        sort: str = "date_paiement",
        order: str = "desc",
        page: int = 1,
        size: int = 20,
    ) -> dict:
        filters = self._access_filters(user)
        if statut:
            filters.append(MgNoteFraisPaiement.statut == statut)
        if mode_paiement:
            filters.append(MgNoteFraisPaiement.mode_paiement == mode_paiement)
        if beneficiaire and beneficiaire.strip():
            filters.append(MgNoteFrais.demandeur_nom.ilike(f"%{beneficiaire.strip()}%"))
        if note_id:
            filters.append(MgNoteFraisPaiement.note_id == note_id)
        if registre and registre.strip():
            filters.append(MgNoteFrais.reference.ilike(f"%{registre.strip()}%"))
        if date_debut:
            filters.append(MgNoteFraisPaiement.date_paiement >= date_debut)
        if date_fin:
            filters.append(MgNoteFraisPaiement.date_paiement <= date_fin)
        if q and q.strip():
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    MgNoteFraisPaiement.numero.ilike(like),
                    MgNoteFraisPaiement.reference.ilike(like),
                    MgNoteFraisPaiement.numero_cheque.ilike(like),
                    MgNoteFrais.reference.ilike(like),
                    MgNoteFrais.demandeur_nom.ilike(like),
                    MgNoteFrais.objet.ilike(like),
                    MgNoteFrais.agence_libelle_snapshot.ilike(like),
                )
            )

        base = select(MgNoteFraisPaiement).join(MgNoteFrais, MgNoteFrais.id == MgNoteFraisPaiement.note_id)
        total = int(
            await self.db.scalar(
                select(func.count())
                .select_from(MgNoteFraisPaiement)
                .join(MgNoteFrais, MgNoteFrais.id == MgNoteFraisPaiement.note_id)
                .where(*filters)
            )
            or 0
        )
        montant_total = await self.db.scalar(
            select(func.coalesce(func.sum(MgNoteFraisPaiement.montant), 0))
            .select_from(MgNoteFraisPaiement)
            .join(MgNoteFrais, MgNoteFrais.id == MgNoteFraisPaiement.note_id)
            .where(*filters, MgNoteFraisPaiement.statut == "VALIDE")
        )

        col = SORTS.get(sort, MgNoteFraisPaiement.date_paiement)
        ordering = col.asc() if order == "asc" else col.desc()
        page = max(1, page)
        size = max(1, min(size, 200))
        rows = (
            await self.db.execute(
                base.options(selectinload(MgNoteFraisPaiement.note))
                .where(*filters)
                .order_by(ordering, MgNoteFraisPaiement.numero.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).scalars().all()
        counts = await self._counts(list({p.note_id for p in rows}))
        return {
            "items": [paiement_out(p, counts.get(p.note_id, 0)) for p in rows],
            "total": total,
            "page": page,
            "size": size,
            "montant_total": montant_total or _ZERO,
        }

    async def _load(self, paiement_id: uuid.UUID, *, lock: bool = False) -> MgNoteFraisPaiement:
        stmt = (
            select(MgNoteFraisPaiement)
            .options(selectinload(MgNoteFraisPaiement.note))
            .where(MgNoteFraisPaiement.id == paiement_id, MgNoteFraisPaiement.deleted_at.is_(None))
        )
        if lock:
            stmt = stmt.with_for_update(of=MgNoteFraisPaiement)
        p = await self.db.scalar(stmt)
        if not p or p.note is None or p.note.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paiement introuvable")
        return p

    async def get_paiement(self, paiement_id: uuid.UUID, user: User) -> dict:
        p = await self._load(paiement_id)
        self.notes._assert_access(p.note, user)
        counts = await self._counts([p.note_id])
        return paiement_out(p, counts.get(p.note_id, 0))

    async def get_registre(self, note_id: uuid.UUID, user: User) -> dict:
        note = await self.notes.get_note(note_id, user)
        counts = await self._counts([note.id])
        return registre_out(note, counts.get(note.id, 0))

    async def list_payables(self, user: User, q: str | None = None, limit: int = 50) -> list[dict]:
        """Notes restant à payer : validées ou en paiement, avec un solde positif."""
        filters = [
            MgNoteFrais.deleted_at.is_(None),
            MgNoteFrais.statut.in_(PAYABLE),
            MgNoteFrais.total_mru > func.coalesce(MgNoteFrais.montant_paye, 0),
        ]
        if not self.notes._can_supervise(user):
            filters.append(MgNoteFrais.demandeur_id == user.id)
        if q and q.strip():
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    MgNoteFrais.reference.ilike(like),
                    MgNoteFrais.demandeur_nom.ilike(like),
                    MgNoteFrais.objet.ilike(like),
                    MgNoteFrais.agence_libelle_snapshot.ilike(like),
                )
            )
        notes = (
            await self.db.execute(
                select(MgNoteFrais)
                .where(*filters)
                .order_by(MgNoteFrais.date_demande.asc(), MgNoteFrais.reference.asc())
                .limit(max(1, min(limit, 200)))
            )
        ).scalars().all()
        counts = await self._counts([n.id for n in notes])
        return [registre_out(n, counts.get(n.id, 0)) for n in notes]

    # --- écriture ---

    async def _next_numero(self) -> str:
        await self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext('mg_note_frais_paiements.numero'))"))
        year = date.today().year
        prefix = f"PAY-{year}-"
        count = await self.db.scalar(
            select(func.count())
            .select_from(MgNoteFraisPaiement)
            .where(MgNoteFraisPaiement.numero.like(f"{prefix}%"), ~MgNoteFraisPaiement.numero.like(f"{prefix}R%"))
        )
        return f"{prefix}{int(count or 0) + 1:04d}"

    async def _paid_total(self, note_id: uuid.UUID) -> Decimal:
        await self.db.flush()
        value = await self.db.scalar(
            select(func.coalesce(func.sum(MgNoteFraisPaiement.montant), 0)).where(
                MgNoteFraisPaiement.note_id == note_id,
                MgNoteFraisPaiement.deleted_at.is_(None),
                MgNoteFraisPaiement.statut == "VALIDE",
            )
        )
        return Decimal(value or 0)

    async def _recompute(self, note: MgNoteFrais, user: User, commentaire: str) -> None:
        """Montant payé = somme des paiements valides ; le statut en découle."""
        paid = await self._paid_total(note.id)
        note.montant_paye = paid
        last = await self.db.scalar(
            select(MgNoteFraisPaiement)
            .where(
                MgNoteFraisPaiement.note_id == note.id,
                MgNoteFraisPaiement.deleted_at.is_(None),
                MgNoteFraisPaiement.statut == "VALIDE",
            )
            .order_by(MgNoteFraisPaiement.date_paiement.desc(), MgNoteFraisPaiement.created_at.desc())
            .limit(1)
        )
        note.date_paiement = last.date_paiement if last else None
        note.mode_paiement = last.mode_paiement if last else None
        note.ref_paiement = (last.reference or last.numero_cheque) if last else None

        old = note.statut
        if old in PAYMENT_DRIVEN:
            total = note.total_mru or _ZERO
            if total > 0 and paid >= total:
                new = "PAYEE"
            elif paid > 0:
                new = "PARTIELLEMENT_PAYEE"
            else:
                new = "VALIDEE" if old == "VALIDEE" else "MISE_EN_PAIEMENT"
            if new != old:
                if old == "VALIDEE" and note.date_mise_en_paiement is None:
                    note.date_mise_en_paiement = date.today()
                note.statut = new
        self.notes._add_hist(
            note,
            action="paiement",
            from_statut=old,
            to_statut=note.statut,
            user=user,
            commentaire=commentaire,
        )

    def _assert_mutable(self, p: MgNoteFraisPaiement) -> None:
        if p.note.statut in FIGE:
            raise _bad("Note clôturée ou archivée : ses paiements ne sont plus modifiables")

    async def create(self, data: NotePaiementCreate, user: User) -> dict:
        self._require(user, "mg.notes.payment", "Permission paiement requise")
        note = await self.notes._lock_note(data.note_id)
        self.notes._assert_access(note, user)
        if note.statut not in PAYABLE:
            if note.statut in {"PAYEE", "CLOTUREE", "ARCHIVEE"}:
                raise _bad(f"La note {note.reference} est déjà totalement payée")
            raise _bad(f"La note {note.reference} doit être validée avant tout paiement")

        reste = (note.total_mru or _ZERO) - (note.montant_paye or _ZERO)
        if reste <= 0:
            raise _bad(f"La note {note.reference} est déjà totalement payée")
        if data.montant > reste:
            raise _bad(f"Montant supérieur au solde restant ({reste} {note.devise or 'MRU'})")
        if data.montant < reste and not await self.notes.paiement_partiel_actif():
            raise _bad("Paiement partiel désactivé dans les paramètres — régler le solde complet")

        reference = _clean(data.reference)
        numero_cheque = _clean(data.numero_cheque)
        check_mode_details(data.mode_paiement, reference=reference, numero_cheque=numero_cheque)

        p = MgNoteFraisPaiement(
            numero=await self._next_numero(),
            note_id=note.id,
            date_paiement=data.date_paiement,
            montant=data.montant,
            mode_paiement=data.mode_paiement,
            reference=reference,
            numero_cheque=numero_cheque,
            banque=_clean(data.banque),
            compte=_clean(data.compte),
            observation=_clean(data.observation),
            statut="VALIDE",
            created_by_id=user.id,
            created_by_nom=user.full_name,
        )
        self.db.add(p)
        await self._recompute(note, user, f"Paiement {p.numero} : {data.montant} {note.devise or 'MRU'}")
        await self.db.commit()
        await audit_notes(
            self.db,
            user,
            "notes.paiement.create",
            "note_frais_paiement",
            p.id,
            after={
                "numero": p.numero,
                "note": note.reference,
                "montant": str(p.montant),
                "mode": p.mode_paiement,
                "statut_note": note.statut,
            },
        )
        await self.db.commit()
        if note.demandeur_id:
            await notify_notes_user(
                self.db,
                note.demandeur_id,
                f"Note {note.reference}",
                f"Paiement {p.numero} enregistré ({note.statut_paiement.lower().replace('_', ' ')}).",
                entity="note_frais",
                entity_id=note.id,
                actor=user,
            )
            await self.db.commit()
        return await self.get_paiement(p.id, user)

    async def update(self, paiement_id: uuid.UUID, data: NotePaiementUpdate, user: User) -> dict:
        self._require(user, "mg.notes.payment", "Permission paiement requise")
        p = await self._load(paiement_id)
        note = await self.notes._lock_note(p.note_id)
        p = await self._load(paiement_id, lock=True)
        self.notes._assert_access(note, user)
        self._assert_mutable(p)
        if p.statut != "VALIDE":
            raise _bad("Un paiement annulé ne peut plus être modifié")

        before = {
            "montant": str(p.montant),
            "date": str(p.date_paiement),
            "mode": p.mode_paiement,
            "reference": p.reference,
        }
        montant = data.montant if data.montant is not None else p.montant
        disponible = (note.total_mru or _ZERO) - (note.montant_paye or _ZERO) + p.montant
        if montant > disponible:
            raise _bad(f"Montant supérieur au solde restant ({disponible} {note.devise or 'MRU'})")

        fields = data.model_dump(exclude_unset=True)
        for key in ("reference", "numero_cheque", "banque", "compte", "observation"):
            if key in fields:
                setattr(p, key, _clean(fields[key]))
        if data.date_paiement is not None:
            p.date_paiement = data.date_paiement
        if data.mode_paiement is not None:
            p.mode_paiement = data.mode_paiement
        p.montant = montant
        check_mode_details(p.mode_paiement, reference=p.reference, numero_cheque=p.numero_cheque)
        p.updated_by_id = user.id
        p.updated_by_nom = user.full_name

        await self._recompute(note, user, f"Paiement {p.numero} modifié : {p.montant} {note.devise or 'MRU'}")
        await self.db.commit()
        await audit_notes(
            self.db,
            user,
            "notes.paiement.update",
            "note_frais_paiement",
            p.id,
            before=before,
            after={
                "montant": str(p.montant),
                "date": str(p.date_paiement),
                "mode": p.mode_paiement,
                "reference": p.reference,
                "statut_note": note.statut,
            },
        )
        await self.db.commit()
        return await self.get_paiement(p.id, user)

    async def cancel(self, paiement_id: uuid.UUID, motif: str, user: User) -> dict:
        self._require(user, "mg.notes.payment", "Permission paiement requise")
        p = await self._load(paiement_id)
        note = await self.notes._lock_note(p.note_id)
        p = await self._load(paiement_id, lock=True)
        self.notes._assert_access(note, user)
        self._assert_mutable(p)
        if p.statut == "ANNULE":
            raise _bad("Paiement déjà annulé")

        p.statut = "ANNULE"
        p.motif_annulation = motif.strip()
        p.annule_at = datetime.now(timezone.utc)
        p.annule_par_id = user.id
        p.annule_par_nom = user.full_name
        await self._recompute(note, user, f"Paiement {p.numero} annulé : {p.motif_annulation}")
        await self.db.commit()
        await audit_notes(
            self.db,
            user,
            "notes.paiement.cancel",
            "note_frais_paiement",
            p.id,
            before={"statut": "VALIDE", "montant": str(p.montant)},
            after={"statut": "ANNULE", "motif": p.motif_annulation, "statut_note": note.statut},
        )
        await self.db.commit()
        return await self.get_paiement(p.id, user)

    async def delete(self, paiement_id: uuid.UUID, user: User) -> None:
        if not self.notes._is_notes_admin(user):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Suppression réservée à l’administrateur — utilisez l’annulation",
            )
        p = await self._load(paiement_id)
        note = await self.notes._lock_note(p.note_id)
        p = await self._load(paiement_id, lock=True)
        self._assert_mutable(p)

        p.deleted_at = datetime.now(timezone.utc)
        p.updated_by_id = user.id
        p.updated_by_nom = user.full_name
        await self._recompute(note, user, f"Paiement {p.numero} supprimé")
        await self.db.commit()
        await audit_notes(
            self.db,
            user,
            "notes.paiement.delete",
            "note_frais_paiement",
            p.id,
            before={"numero": p.numero, "montant": str(p.montant), "statut": p.statut},
            after={"statut_note": note.statut},
        )
        await self.db.commit()
