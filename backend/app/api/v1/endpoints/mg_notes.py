"""API Notes de frais MG — cycle complet."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_access, require_permission
from app.models.auth import Agence, User
from app.schemas.mg_notes import (
    AlerteOut,
    CategorieIn,
    CategorieOut,
    CategorieUpdate,
    DashboardOut,
    NoteCreate,
    NoteListOut,
    NoteOut,
    NoteUpdate,
    PaiementIn,
    ParametreIn,
    ParametreOut,
    ParametreUpdate,
    TransitionIn,
)
from app.services.mg_notes_reporting import MgNotesReporting
from app.services.mg_notes_service import MgNotesService
from app.services.mg_pdf_service import pdf_note_frais

router = APIRouter(prefix="/mg/notes-frais", tags=["mg-notes-frais"])
_module = [Depends(require_module_access("notes-frais"))]


@router.get("/agences", dependencies=_module)
async def list_agences(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.view")),
):
    rows = (
        await db.execute(
            select(Agence)
            .where(Agence.is_active.is_(True), Agence.deleted_at.is_(None))
            .order_by(Agence.libelle)
        )
    ).scalars().all()
    return [
        {
            "id": str(a.id),
            "code": a.code,
            "libelle": a.libelle,
            "adresse": a.adresse,
            "ville": a.ville,
        }
        for a in rows
    ]


@router.get("/dashboard", response_model=DashboardOut, dependencies=_module)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.view")),
):
    return await MgNotesService(db).dashboard(user)


@router.get("/alertes", response_model=list[AlerteOut], dependencies=_module)
async def alertes(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.view")),
):
    return await MgNotesService(db).alertes(user)


@router.get("/categories", response_model=list[CategorieOut], dependencies=_module)
async def list_categories(
    actifs: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.view")),
):
    return await MgNotesService(db).list_categories(actifs_only=actifs)


@router.post("/categories", response_model=CategorieOut, dependencies=_module)
async def create_categorie(
    body: CategorieIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.settings")),
):
    return await MgNotesService(db).create_categorie(body)


@router.patch("/categories/{cat_id}", response_model=CategorieOut, dependencies=_module)
async def update_categorie(
    cat_id: UUID,
    body: CategorieUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.settings")),
):
    return await MgNotesService(db).update_categorie(cat_id, body)


@router.delete("/categories/{cat_id}", response_model=CategorieOut, dependencies=_module)
async def deactivate_categorie(
    cat_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.settings")),
):
    return await MgNotesService(db).deactivate_categorie(cat_id)


@router.get("/parametres", response_model=list[ParametreOut], dependencies=_module)
async def list_parametres(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.settings")),
):
    return await MgNotesService(db).list_parametres()


@router.post("/parametres", response_model=ParametreOut, dependencies=_module)
async def upsert_parametre(
    body: ParametreIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.settings")),
):
    return await MgNotesService(db).upsert_parametre(body)


@router.patch("/parametres/{cle}", response_model=ParametreOut, dependencies=_module)
async def patch_parametre(
    cle: str,
    body: ParametreUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.settings")),
):
    return await MgNotesService(db).patch_parametre(cle, body)


@router.get("/notes", response_model=NoteListOut, dependencies=_module)
async def list_notes(
    q: str | None = None,
    statut: str | None = None,
    agence_id: UUID | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    montant_min: Decimal | None = None,
    montant_max: Decimal | None = None,
    demandeur_id: UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.view")),
):
    items, total = await MgNotesService(db).list_notes(
        user,
        q=q,
        statut=statut,
        agence_id=agence_id,
        date_debut=date_debut,
        date_fin=date_fin,
        montant_min=montant_min,
        montant_max=montant_max,
        demandeur_id=demandeur_id,
        page=page,
        size=size,
    )
    return NoteListOut(items=items, total=total, page=page, size=size)


@router.post("/notes", response_model=NoteOut, dependencies=_module)
async def create_note(
    body: NoteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.create")),
):
    return await MgNotesService(db).create_note(body, user)


@router.get("/notes/{note_id}", response_model=NoteOut, dependencies=_module)
async def get_note(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.view")),
):
    return await MgNotesService(db).get_note(note_id, user)


@router.patch("/notes/{note_id}", response_model=NoteOut, dependencies=_module)
async def update_note(
    note_id: UUID,
    body: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.create")),
):
    return await MgNotesService(db).update_note(note_id, body, user)


@router.delete("/notes/{note_id}", dependencies=_module)
async def delete_note(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.create")),
):
    await MgNotesService(db).soft_delete(note_id, user)
    return {"ok": True}


@router.post("/notes/{note_id}/transition", response_model=NoteOut, dependencies=_module)
async def transition_note(
    note_id: UUID,
    body: TransitionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.view")),
):
    # Permission fine-grained checked inside service
    _ = request
    return await MgNotesService(db).transition(note_id, body.action, user, body.commentaire)


@router.post("/notes/{note_id}/paiement", response_model=NoteOut, dependencies=_module)
async def paiement_note(
    note_id: UUID,
    body: PaiementIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.payment")),
):
    return await MgNotesService(db).enregistrer_paiement(note_id, body, user)


@router.get("/notes/{note_id}/pdf", dependencies=_module)
async def note_pdf(
    note_id: UUID,
    signataire_1: str | None = Query(None, description="Nom signataire MG"),
    signataire_2: str | None = Query(None, description="Nom signataire DR"),
    signataire_1_role: str | None = Query(None),
    signataire_2_role: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.export")),
):
    note = await MgNotesService(db).get_note(note_id, user)
    data = pdf_note_frais(
        note,
        signataire_1=signataire_1,
        signataire_2=signataire_2,
        signataire_1_role=signataire_1_role,
        signataire_2_role=signataire_2_role,
    )
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{note.reference}.pdf"'},
    )


@router.get("/rapports/{report_key}", dependencies=_module)
async def rapport(
    report_key: str,
    format: str = Query("json", pattern="^(json|xlsx|pdf|csv)$"),
    annee: int | None = None,
    mois: int | None = None,
    agence_id: UUID | None = None,
    statut: str | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.export")),
):
    return await MgNotesReporting(db).export(
        user,
        report_key,
        fmt=format,
        annee=annee,
        mois=mois,
        agence_id=agence_id,
        statut=statut,
        date_debut=date_debut,
        date_fin=date_fin,
    )
