"""Service métier — Notes de frais MG."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import Agence, User
from app.models.mg_ops import (
    MgNoteFrais,
    MgNoteFraisCategorie,
    MgNoteFraisHistorique,
    MgNoteFraisLigne,
    MgNoteFraisParametre,
)
from app.schemas.mg_notes import (
    CategorieIn,
    CategorieUpdate,
    NoteCreate,
    NoteUpdate,
    PaiementIn,
    ParametreIn,
    ParametreUpdate,
)
from app.services.mg_notes_events import audit_notes, notify_notes_roles, notify_notes_user

EDITABLE = {"BROUILLON", "CORRECTION_REQUISE"}
LOCKED = {"VALIDEE", "MISE_EN_PAIEMENT", "PARTIELLEMENT_PAYEE", "PAYEE", "CLOTUREE", "ARCHIVEE"}
# Paiement, clôture et archive : plus de modification ni de suppression.
MUTATION_LOCKED = {"MISE_EN_PAIEMENT", "PARTIELLEMENT_PAYEE", "PAYEE", "CLOTUREE", "ARCHIVEE"}

# action -> (from_statuts | None=any allowed set, to_statut, permission)
# Circuit simplifié : visas papier (PDF signé à la main) — pas d'étapes VISA_MG / VISA_DR obligatoires.
NOTE_TRANSITIONS: dict[str, tuple[set[str] | None, str, str]] = {
    "soumettre": ({"BROUILLON"}, "SOUMIS", "mg.notes.create"),
    "prendre_controle": ({"SOUMIS"}, "EN_CONTROLE", "mg.notes.control"),
    "demander_correction": (
        {"SOUMIS", "EN_CONTROLE", "VISA_MG", "VISA_DR"},
        "CORRECTION_REQUISE",
        "mg.notes.control",
    ),
    "resoumettre": ({"CORRECTION_REQUISE"}, "SOUMIS", "mg.notes.create"),
    "visa_mg": ({"EN_CONTROLE"}, "VISA_MG", "mg.notes.approve"),
    "visa_dr": ({"VISA_MG", "EN_CONTROLE"}, "VISA_DR", "mg.notes.approve"),
    # Validation directe après soumission (signatures manuscrites sur PDF)
    "valider": (
        {"SOUMIS", "EN_CONTROLE", "VISA_MG", "VISA_DR"},
        "VALIDEE",
        "mg.notes.approve",
    ),
    "mettre_en_paiement": ({"VALIDEE"}, "MISE_EN_PAIEMENT", "mg.notes.payment"),
    "cloturer": ({"PAYEE"}, "CLOTUREE", "mg.notes.payment"),
    "archiver": ({"CLOTUREE"}, "ARCHIVEE", "mg.notes.archive"),
    "rejeter": (
        {"SOUMIS", "EN_CONTROLE", "VISA_MG", "VISA_DR", "CORRECTION_REQUISE"},
        "REJETEE",
        "mg.notes.reject",
    ),
    "annuler": (
        {"BROUILLON", "SOUMIS", "EN_CONTROLE", "CORRECTION_REQUISE", "VISA_MG", "VISA_DR", "VALIDEE"},
        "ANNULEE",
        "mg.notes.reject",
    ),
}

DEFAULT_CATEGORIES = [
    ("TRANSPORT", "Transport"),
    ("HEBERGEMENT", "Hébergement"),
    ("RESTAURATION", "Restauration"),
    ("CARBURANT", "Carburant"),
    ("COMMUNICATION", "Communication"),
    ("FOURNITURES", "Fournitures"),
    ("MISSION", "Mission"),
    ("DEPLACEMENT", "Déplacement"),
    ("REPRESENTATION", "Représentation"),
    ("AUTRE", "Autre"),
]

DEFAULT_PARAMS = [
    ("notes.paiement_partiel", "false", "Autoriser le paiement partiel"),
    ("notes.prefixe", "NF", "Préfixe numérotation"),
    ("notes.alerte_jours_controle", "5", "Jours avant alerte contrôle"),
    ("notes.alerte_jours_paiement", "15", "Jours avant alerte paiement"),
]


class MgNotesService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_defaults(self) -> None:
        for code, libelle in DEFAULT_CATEGORIES:
            exists = await self.db.scalar(
                select(MgNoteFraisCategorie.id).where(
                    MgNoteFraisCategorie.code == code,
                    MgNoteFraisCategorie.deleted_at.is_(None),
                )
            )
            if not exists:
                self.db.add(
                    MgNoteFraisCategorie(code=code, libelle=libelle, actif=True, sort_order=0)
                )
        for cle, valeur, libelle in DEFAULT_PARAMS:
            exists = await self.db.scalar(
                select(MgNoteFraisParametre.id).where(MgNoteFraisParametre.cle == cle)
            )
            if not exists:
                self.db.add(MgNoteFraisParametre(cle=cle, valeur=valeur, libelle=libelle))
        await self.db.commit()

    async def get_param(self, cle: str, default: str = "") -> str:
        row = await self.db.scalar(
            select(MgNoteFraisParametre).where(MgNoteFraisParametre.cle == cle)
        )
        return row.valeur if row else default

    async def paiement_partiel_actif(self) -> bool:
        return (await self.get_param("notes.paiement_partiel", "false")).lower() in {
            "1",
            "true",
            "oui",
            "yes",
        }

    async def _next_ref(self) -> str:
        prefix = await self.get_param("notes.prefixe", "NF")
        year = date.today().year
        like = f"{prefix}-{year}%"
        count = await self.db.scalar(
            select(func.count())
            .select_from(MgNoteFrais)
            .where(MgNoteFrais.reference.ilike(like))
        )
        return f"{prefix}-{year}-{int(count or 0) + 1:04d}"

    def _can_supervise(self, user: User) -> bool:
        if user.is_superuser:
            return True
        codes = {p.code for r in (user.roles or []) for p in (r.permissions or [])}
        return bool(
            codes
            & {
                "mg.notes.control",
                "mg.notes.approve",
                "mg.notes.payment",
                "mg.notes.archive",
                "mg.notes.reject",
            }
        )

    def _assert_access(self, note: MgNoteFrais, user: User) -> None:
        if self._can_supervise(user):
            return
        if note.demandeur_id and note.demandeur_id == user.id:
            return
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Accès refusé à cette note")

    async def _lock_note(self, note_id: uuid.UUID) -> MgNoteFrais:
        note = await self.db.scalar(
            select(MgNoteFrais)
            .options(
                selectinload(MgNoteFrais.lignes),
                selectinload(MgNoteFrais.historique),
            )
            .where(MgNoteFrais.id == note_id, MgNoteFrais.deleted_at.is_(None))
            .with_for_update()
        )
        if not note:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Note de frais introuvable")
        return note

    async def get_note(self, note_id: uuid.UUID, user: User | None = None) -> MgNoteFrais:
        note = await self.db.scalar(
            select(MgNoteFrais)
            .options(
                selectinload(MgNoteFrais.lignes),
                selectinload(MgNoteFrais.historique),
            )
            .where(MgNoteFrais.id == note_id, MgNoteFrais.deleted_at.is_(None))
        )
        if not note:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Note de frais introuvable")
        if user is not None:
            self._assert_access(note, user)
        return note

    def _filters(
        self,
        *,
        q: str | None,
        statut: str | None,
        agence_id: uuid.UUID | None,
        date_debut: date | None,
        date_fin: date | None,
        montant_min: Decimal | None,
        montant_max: Decimal | None,
        demandeur_id: uuid.UUID | None,
        user: User,
    ) -> list:
        filters = [MgNoteFrais.deleted_at.is_(None)]
        if not self._can_supervise(user):
            filters.append(MgNoteFrais.demandeur_id == user.id)
        elif demandeur_id:
            filters.append(MgNoteFrais.demandeur_id == demandeur_id)
        if statut:
            filters.append(MgNoteFrais.statut == statut)
        if agence_id:
            filters.append(MgNoteFrais.agence_id == agence_id)
        if date_debut:
            filters.append(MgNoteFrais.date_demande >= date_debut)
        if date_fin:
            filters.append(MgNoteFrais.date_demande <= date_fin)
        if montant_min is not None:
            filters.append(MgNoteFrais.total_mru >= montant_min)
        if montant_max is not None:
            filters.append(MgNoteFrais.total_mru <= montant_max)
        if q and q.strip():
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    MgNoteFrais.reference.ilike(like),
                    MgNoteFrais.demandeur_nom.ilike(like),
                    MgNoteFrais.agence_libelle_snapshot.ilike(like),
                    MgNoteFrais.departement.ilike(like),
                    MgNoteFrais.objet.ilike(like),
                )
            )
        return filters

    async def list_notes(
        self,
        user: User,
        *,
        q: str | None = None,
        statut: str | None = None,
        agence_id: uuid.UUID | None = None,
        date_debut: date | None = None,
        date_fin: date | None = None,
        montant_min: Decimal | None = None,
        montant_max: Decimal | None = None,
        demandeur_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[MgNoteFrais], int]:
        filters = self._filters(
            q=q,
            statut=statut,
            agence_id=agence_id,
            date_debut=date_debut,
            date_fin=date_fin,
            montant_min=montant_min,
            montant_max=montant_max,
            demandeur_id=demandeur_id,
            user=user,
        )
        total = int(
            (await self.db.scalar(select(func.count()).select_from(MgNoteFrais).where(*filters)))
            or 0
        )
        page = max(1, page)
        size = max(1, min(size, 200))
        stmt: Select = (
            select(MgNoteFrais)
            .options(selectinload(MgNoteFrais.lignes), selectinload(MgNoteFrais.historique))
            .where(*filters)
            .order_by(MgNoteFrais.date_demande.desc(), MgNoteFrais.reference.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list((await self.db.execute(stmt)).scalars().all()), total

    async def _snapshot_agence(self, note: MgNoteFrais, agence_id: uuid.UUID) -> None:
        ag = await self.db.get(Agence, agence_id)
        if not ag or ag.deleted_at is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Agence invalide")
        note.agence_id = ag.id
        note.agence_libelle_snapshot = ag.libelle
        note.agence_code_snapshot = ag.code
        parts = [p for p in (ag.adresse, ag.ville) if p]
        note.agence_adresse_snapshot = ", ".join(parts) if parts else None

    async def _apply_intitule(
        self,
        note: MgNoteFrais,
        *,
        agence_id: uuid.UUID | None,
        intitule: str | None,
        clear_agence: bool = False,
    ) -> None:
        """Agence référentiel OU intitulé libre (ex. Frais Carburant)."""
        if agence_id:
            await self._snapshot_agence(note, agence_id)
            return
        titre = (intitule or "").strip()
        if titre:
            if clear_agence or note.agence_id is None:
                note.agence_id = None
                note.agence_code_snapshot = None
                note.agence_adresse_snapshot = None
            note.agence_libelle_snapshot = titre
            return
        if not note.agence_libelle_snapshot:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Choisir une agence ou saisir un intitulé (ex. Frais Carburant)",
            )

    async def _apply_lignes(self, note: MgNoteFrais, lignes, *, require_lines: bool = False) -> None:
        if require_lines and not lignes:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Au moins une ligne de dépense est requise")
        note.lignes.clear()
        total = Decimal("0")
        for i, row in enumerate(lignes or []):
            if row.montant <= 0:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Montant invalide ligne {i + 1}")
            cat_label = None
            if row.categorie_id:
                cat = await self.db.get(MgNoteFraisCategorie, row.categorie_id)
                if not cat or cat.deleted_at is not None or not cat.actif:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST, detail=f"Catégorie invalide ligne {i + 1}"
                    )
                cat_label = cat.libelle
                if cat.plafond is not None and row.montant > cat.plafond:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=f"Plafond dépassé pour {cat.libelle} (max {cat.plafond})",
                    )
            total += row.montant
            note.lignes.append(
                MgNoteFraisLigne(
                    date_depense=row.date_depense,
                    description=row.description.strip(),
                    motif=row.motif,
                    montant=row.montant,
                    mode_reglement=row.mode_reglement,
                    categorie_id=row.categorie_id,
                    categorie_libelle_snapshot=cat_label,
                    devise=row.devise or note.devise or "MRU",
                    commentaire=row.commentaire,
                    sort_order=i,
                )
            )
        note.total_mru = total

    def _add_hist(
        self,
        note: MgNoteFrais,
        *,
        action: str,
        from_statut: str | None,
        to_statut: str | None,
        user: User,
        commentaire: str | None = None,
    ) -> None:
        note.historique.append(
            MgNoteFraisHistorique(
                action=action,
                from_statut=from_statut,
                to_statut=to_statut,
                user_id=user.id,
                user_nom=user.full_name,
                commentaire=commentaire,
            )
        )

    async def create_note(self, data: NoteCreate, user: User) -> MgNoteFrais:
        await self.ensure_defaults()
        note = MgNoteFrais(
            reference=await self._next_ref(),
            date_demande=data.date_demande,
            demandeur_id=user.id,
            demandeur_nom=data.demandeur_nom or user.full_name,
            departement=data.departement,
            fonction=data.fonction,
            objet=data.objet,
            periode_debut=data.periode_debut,
            periode_fin=data.periode_fin,
            devise=data.devise or "MRU",
            observation=data.observation,
            statut="BROUILLON",
        )
        await self._apply_intitule(note, agence_id=data.agence_id, intitule=data.intitule, clear_agence=True)
        await self._apply_lignes(note, data.lignes or [])
        self._add_hist(note, action="creer", from_statut=None, to_statut="BROUILLON", user=user)
        self.db.add(note)
        await self.db.commit()
        await audit_notes(self.db, user, "notes.create", "note_frais", note.id, after={"ref": note.reference})
        await self.db.commit()
        return await self.get_note(note.id, user)

    def _assert_can_mutate(self, note: MgNoteFrais, user: User, *, deleting: bool) -> None:
        """Brouillon / correction : le demandeur. Sinon : un superviseur, hors paiement et archive."""
        if note.statut in MUTATION_LOCKED:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Note non modifiable : déjà en paiement, payée, clôturée ou archivée",
            )
        if self._can_supervise(user):
            return
        if deleting:
            if note.statut != "BROUILLON" or note.demandeur_id != user.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Suppression refusée")
            return
        if note.statut not in EDITABLE or note.demandeur_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Modification refusée")

    async def update_note(self, note_id: uuid.UUID, data: NoteUpdate, user: User) -> MgNoteFrais:
        note = await self._lock_note(note_id)
        self._assert_access(note, user)
        self._assert_can_mutate(note, user, deleting=False)
        before = {"statut": note.statut, "total": str(note.total_mru)}
        for field in (
            "date_demande",
            "demandeur_nom",
            "departement",
            "fonction",
            "objet",
            "periode_debut",
            "periode_fin",
            "devise",
            "observation",
        ):
            val = getattr(data, field)
            if val is not None:
                setattr(note, field, val)
        if data.agence_id is not None or data.intitule is not None:
            await self._apply_intitule(
                note,
                agence_id=data.agence_id,
                intitule=data.intitule,
                clear_agence=data.agence_id is None and data.intitule is not None,
            )
        if data.lignes is not None:
            await self._apply_lignes(note, data.lignes)
        note.pdf_version = (note.pdf_version or 1) + 1
        self._add_hist(
            note,
            action="modifier",
            from_statut=note.statut,
            to_statut=note.statut,
            user=user,
        )
        await self.db.commit()
        await audit_notes(
            self.db,
            user,
            "notes.update",
            "note_frais",
            note.id,
            before=before,
            after={"total": str(note.total_mru)},
        )
        await self.db.commit()
        return await self.get_note(note.id, user)

    async def soft_delete(self, note_id: uuid.UUID, user: User) -> None:
        note = await self._lock_note(note_id)
        self._assert_access(note, user)
        self._assert_can_mutate(note, user, deleting=True)
        old = note.statut
        note.deleted_at = datetime.now(timezone.utc)
        self._add_hist(note, action="supprimer", from_statut=old, to_statut=None, user=user)
        await self.db.commit()
        await audit_notes(self.db, user, "notes.delete", "note_frais", note.id)
        await self.db.commit()

    def _user_perms(self, user: User) -> set[str]:
        if user.is_superuser:
            return {
                "mg.notes.view",
                "mg.notes.create",
                "mg.notes.control",
                "mg.notes.approve",
                "mg.notes.reject",
                "mg.notes.payment",
                "mg.notes.archive",
                "mg.notes.export",
                "mg.notes.settings",
            }
        return {p.code for r in (user.roles or []) for p in (r.permissions or [])}

    async def transition(
        self,
        note_id: uuid.UUID,
        action: str,
        user: User,
        commentaire: str | None = None,
    ) -> MgNoteFrais:
        key = action.strip().lower()
        if key not in NOTE_TRANSITIONS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Action invalide")
        allowed_from, new_statut, need_perm = NOTE_TRANSITIONS[key]
        perms = self._user_perms(user)
        if need_perm not in perms:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Permission insuffisante")

        note = await self._lock_note(note_id)
        self._assert_access(note, user)

        # Idempotence : déjà dans l'état cible
        if note.statut == new_statut:
            return await self.get_note(note.id, user)

        if allowed_from is not None and note.statut not in allowed_from:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Transition impossible depuis {note.statut}",
            )

        if key in {"soumettre", "resoumettre"}:
            if not note.lignes:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Au moins une ligne requise")
            if not note.agence_id and not (note.agence_libelle_snapshot or "").strip():
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Agence ou intitulé obligatoire",
                )
            if note.total_mru <= 0:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Total doit être > 0")

        if key in {"demander_correction", "rejeter", "annuler"}:
            if not (commentaire or "").strip():
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Motif obligatoire")

        old = note.statut
        now = datetime.now(timezone.utc)

        if key == "prendre_controle":
            note.controle_at, note.controle_by = now, user.id
        elif key == "visa_mg":
            note.visa_mg_at, note.visa_mg_by = now, user.id
        elif key == "visa_dr":
            note.visa_dr_at, note.visa_dr_by = now, user.id
        elif key == "mettre_en_paiement":
            note.date_mise_en_paiement = date.today()
        elif key == "demander_correction":
            note.motif_correction = commentaire
        elif key == "rejeter":
            note.motif_rejet = commentaire
        elif key == "annuler":
            note.motif_rejet = commentaire

        note.statut = new_statut
        self._add_hist(
            note,
            action=key,
            from_statut=old,
            to_statut=new_statut,
            user=user,
            commentaire=commentaire,
        )
        await self.db.commit()

        await audit_notes(
            self.db,
            user,
            f"notes.{key}",
            "note_frais",
            note.id,
            before={"statut": old},
            after={"statut": new_statut},
        )
        await self.db.commit()

        titre = f"Note {note.reference}"
        msg = f"{note.reference} : {old} → {new_statut}"
        if note.demandeur_id and note.demandeur_id != user.id:
            await notify_notes_user(
                self.db,
                note.demandeur_id,
                titre,
                msg,
                entity="note_frais",
                entity_id=note.id,
                actor=user,
            )
            await self.db.commit()
        if key in {"soumettre", "resoumettre"}:
            await notify_notes_roles(
                self.db,
                {"notes-frais.valideur", "notes-frais.admin"},
                titre,
                f"{note.reference} nécessite un contrôle.",
                entity="note_frais",
                entity_id=note.id,
                actor=user,
            )
            await self.db.commit()

        return await self.get_note(note.id, user)

    async def enregistrer_paiement(
        self, note_id: uuid.UUID, data: PaiementIn, user: User
    ) -> MgNoteFrais:
        perms = self._user_perms(user)
        if "mg.notes.payment" not in perms:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Permission paiement requise")

        note = await self._lock_note(note_id)
        self._assert_access(note, user)

        if note.statut not in {"MISE_EN_PAIEMENT", "PARTIELLEMENT_PAYEE"}:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Paiement possible uniquement après mise en paiement",
            )

        reste = note.total_mru - (note.montant_paye or Decimal("0"))
        if data.montant > reste:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Montant supérieur au reste à payer")

        partiel = await self.paiement_partiel_actif()
        if data.montant < reste and not partiel:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Paiement partiel désactivé — régler le montant total",
            )

        old = note.statut
        note.montant_paye = (note.montant_paye or Decimal("0")) + data.montant
        note.date_paiement = data.date_paiement or date.today()
        if data.mode_paiement:
            note.mode_paiement = data.mode_paiement
        if data.ref_paiement:
            note.ref_paiement = data.ref_paiement
        if data.commentaire:
            note.commentaire_paiement = data.commentaire

        if note.montant_paye >= note.total_mru:
            note.statut = "PAYEE"
            note.montant_paye = note.total_mru
        else:
            note.statut = "PARTIELLEMENT_PAYEE"

        self._add_hist(
            note,
            action="payer",
            from_statut=old,
            to_statut=note.statut,
            user=user,
            commentaire=data.commentaire or f"Paiement {data.montant}",
        )
        await self.db.commit()
        await audit_notes(
            self.db,
            user,
            "notes.payer",
            "note_frais",
            note.id,
            before={"statut": old, "paye": str(note.montant_paye - data.montant)},
            after={"statut": note.statut, "paye": str(note.montant_paye)},
        )
        await self.db.commit()
        if note.demandeur_id:
            await notify_notes_user(
                self.db,
                note.demandeur_id,
                f"Note {note.reference}",
                f"Paiement enregistré ({note.statut}).",
                entity="note_frais",
                entity_id=note.id,
                actor=user,
            )
            await self.db.commit()
        return await self.get_note(note.id, user)

    # --- Catégories / paramètres ---

    async def list_categories(self, *, actifs_only: bool = False) -> list[MgNoteFraisCategorie]:
        await self.ensure_defaults()
        stmt = (
            select(MgNoteFraisCategorie)
            .where(MgNoteFraisCategorie.deleted_at.is_(None))
            .order_by(MgNoteFraisCategorie.sort_order, MgNoteFraisCategorie.libelle)
        )
        if actifs_only:
            stmt = stmt.where(MgNoteFraisCategorie.actif.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    async def create_categorie(self, data: CategorieIn) -> MgNoteFraisCategorie:
        exists = await self.db.scalar(
            select(MgNoteFraisCategorie.id).where(
                MgNoteFraisCategorie.code == data.code.upper().strip(),
                MgNoteFraisCategorie.deleted_at.is_(None),
            )
        )
        if exists:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Code catégorie déjà utilisé")
        row = MgNoteFraisCategorie(
            code=data.code.upper().strip(),
            libelle=data.libelle.strip(),
            actif=data.actif,
            justificatif_obligatoire=data.justificatif_obligatoire,
            plafond=data.plafond,
            sort_order=data.sort_order,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_categorie(
        self, cat_id: uuid.UUID, data: CategorieUpdate
    ) -> MgNoteFraisCategorie:
        row = await self.db.get(MgNoteFraisCategorie, cat_id)
        if not row or row.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Catégorie introuvable")
        for field in ("libelle", "actif", "justificatif_obligatoire", "plafond", "sort_order"):
            val = getattr(data, field)
            if val is not None:
                setattr(row, field, val)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def deactivate_categorie(self, cat_id: uuid.UUID) -> MgNoteFraisCategorie:
        row = await self.db.get(MgNoteFraisCategorie, cat_id)
        if not row or row.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Catégorie introuvable")
        row.actif = False
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def list_parametres(self) -> list[MgNoteFraisParametre]:
        await self.ensure_defaults()
        return list(
            (
                await self.db.execute(select(MgNoteFraisParametre).order_by(MgNoteFraisParametre.cle))
            ).scalars().all()
        )

    async def upsert_parametre(self, data: ParametreIn) -> MgNoteFraisParametre:
        row = await self.db.scalar(
            select(MgNoteFraisParametre).where(MgNoteFraisParametre.cle == data.cle)
        )
        if row:
            row.valeur = data.valeur
            if data.libelle is not None:
                row.libelle = data.libelle
        else:
            row = MgNoteFraisParametre(cle=data.cle, valeur=data.valeur, libelle=data.libelle)
            self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def patch_parametre(self, cle: str, data: ParametreUpdate) -> MgNoteFraisParametre:
        row = await self.db.scalar(
            select(MgNoteFraisParametre).where(MgNoteFraisParametre.cle == cle)
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paramètre introuvable")
        row.valeur = data.valeur
        if data.libelle is not None:
            row.libelle = data.libelle
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def dashboard(self, user: User) -> dict:
        filters = [MgNoteFrais.deleted_at.is_(None)]
        if not self._can_supervise(user):
            filters.append(MgNoteFrais.demandeur_id == user.id)

        async def count_statut(*statuts: str) -> int:
            return int(
                (
                    await self.db.scalar(
                        select(func.count())
                        .select_from(MgNoteFrais)
                        .where(*filters, MgNoteFrais.statut.in_(statuts))
                    )
                )
                or 0
            )

        total = int(
            (await self.db.scalar(select(func.count()).select_from(MgNoteFrais).where(*filters)))
            or 0
        )
        montant_total = (
            await self.db.scalar(select(func.coalesce(func.sum(MgNoteFrais.total_mru), 0)).where(*filters))
        ) or Decimal("0")
        montant_paye = (
            await self.db.scalar(
                select(func.coalesce(func.sum(MgNoteFrais.montant_paye), 0)).where(*filters)
            )
        ) or Decimal("0")
        a_payer_rows = await self.db.execute(
            select(MgNoteFrais.total_mru, MgNoteFrais.montant_paye).where(
                *filters,
                MgNoteFrais.statut.in_(
                    {"VALIDEE", "MISE_EN_PAIEMENT", "PARTIELLEMENT_PAYEE"}
                ),
            )
        )
        montant_a_payer = Decimal("0")
        for tot, paye in a_payer_rows.all():
            montant_a_payer += (tot or Decimal("0")) - (paye or Decimal("0"))

        return {
            "total": total,
            "brouillons": await count_statut("BROUILLON"),
            "soumises": await count_statut("SOUMIS"),
            "en_controle": await count_statut("EN_CONTROLE", "CORRECTION_REQUISE"),
            "en_visa": await count_statut("VISA_MG", "VISA_DR"),
            "validees": await count_statut("VALIDEE"),
            "a_payer": await count_statut("VALIDEE", "MISE_EN_PAIEMENT"),
            "partiellement_payees": await count_statut("PARTIELLEMENT_PAYEE"),
            "payees": await count_statut("PAYEE", "CLOTUREE", "ARCHIVEE"),
            "rejetees": await count_statut("REJETEE", "ANNULEE"),
            "montant_total": montant_total,
            "montant_a_payer": montant_a_payer,
            "montant_paye": montant_paye,
        }

    async def alertes(self, user: User) -> list[dict]:
        notes, _ = await self.list_notes(user, page=1, size=200)
        out: list[dict] = []
        for n in notes:
            if n.statut == "SOUMIS":
                out.append(
                    {
                        "type": "controle",
                        "titre": "En attente de contrôle",
                        "message": f"{n.reference} soumise",
                        "note_id": n.id,
                        "reference": n.reference,
                        "statut": n.statut,
                    }
                )
            elif n.statut in {"EN_CONTROLE", "VISA_MG", "VISA_DR"}:
                out.append(
                    {
                        "type": "visa",
                        "titre": "En attente de visa",
                        "message": f"{n.reference} — {n.statut}",
                        "note_id": n.id,
                        "reference": n.reference,
                        "statut": n.statut,
                    }
                )
            elif n.statut == "CORRECTION_REQUISE":
                out.append(
                    {
                        "type": "correction",
                        "titre": "Correction demandée",
                        "message": n.motif_correction or n.reference,
                        "note_id": n.id,
                        "reference": n.reference,
                        "statut": n.statut,
                    }
                )
            elif n.statut == "REJETEE":
                out.append(
                    {
                        "type": "rejet",
                        "titre": "Note rejetée",
                        "message": n.motif_rejet or n.reference,
                        "note_id": n.id,
                        "reference": n.reference,
                        "statut": n.statut,
                    }
                )
            elif n.statut in {"VALIDEE", "MISE_EN_PAIEMENT", "PARTIELLEMENT_PAYEE"}:
                out.append(
                    {
                        "type": "paiement",
                        "titre": "Paiement en attente",
                        "message": f"{n.reference} — reste {n.total_mru - (n.montant_paye or 0)}",
                        "note_id": n.id,
                        "reference": n.reference,
                        "statut": n.statut,
                    }
                )
        return out[:50]
