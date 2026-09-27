"""Demandes internes employés : workflow, stock, regroupement → DA Achats."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import Agence, User
from app.data.demandes_engine import ESPACE_LABELS
from app.models.mg_requests import (
    MgEmployeeRequest,
    MgEmployeeRequestItem,
    MgProcurementBatch,
    MgProcurementBatchItem,
    MgRequestApproval,
    MgRequestCategory,
    MgRequestComment,
)
from app.models.mg_stock import MgArticle
from app.models.organisation import Departement
from app.schemas.mg_achats import DemandeCreate, DemandeLigneIn
from app.schemas.mg_requests import (
    BatchCreate,
    BatchItemsIn,
    BatchOut,
    BatchUpdate,
    CategoryIn,
    ConsolidatedLineOut,
    GrantedIn,
    RequestCreate,
    RequestItemIn,
    RequestOut,
    RequestUpdate,
    StockHintOut,
)
from app.schemas.mg_stock import MouvementCreate
from app.services.mg_achats_service import MgAchatsService
from app.services.mg_requests_events import audit_request, notify_mg_roles, notify_requester
from app.services.mg_stock_service import MgStockService

EDITABLE = {"BROUILLON", "A_COMPLETER"}
OPEN_FOR_MG = {"SOUMISE", "RECUE", "EN_ANALYSE"}
GROUPABLE = {"VALIDEE", "A_REGROUPER"}
CLOSED = {"REFUSEE", "ANNULEE", "SERVIE", "CLOTUREE"}
URGENT = {"URGENTE", "HAUTE", "URGENT"}
DELETE_LOCKED = {
    "VALIDEE",
    "A_REGROUPER",
    "REGROUPEE",
    "ACHAT_EN_COURS",
    "COMMANDEE",
    "SERVIE",
    "CLOTUREE",
}
EN_COURS = {
    "SOUMISE",
    "RECUE",
    "EN_ANALYSE",
    "VALIDEE",
    "A_REGROUPER",
    "REGROUPEE",
    "ACHAT_EN_COURS",
    "COMMANDEE",
}
APPROVAL_LABELS = {
    "CREATED": "Brouillon créé",
    "SUBMITTED": "Soumise au destinataire",
    "RECEIVED": "Reçue par les Moyens Généraux",
    "REQUESTED_INFO": "Complément demandé",
    "VALIDATED": "Validée par les Moyens Généraux",
    "REJECTED": "Refusée",
    "CANCELLED": "Désactivée",
    "SERVED": "Servie",
    "COMMENTED": "Commentaire",
    "ASSIGNED": "Affectée",
    "RECATEGORIZED": "Recatégorisée",
}
STATUS_LABELS = {
    "BROUILLON": "Brouillon",
    "SOUMISE": "Soumise",
    "RECUE": "Reçue",
    "EN_ANALYSE": "En analyse",
    "A_COMPLETER": "À compléter",
    "VALIDEE": "Validée",
    "A_REGROUPER": "Validée",
    "REGROUPEE": "Regroupée",
    "ACHAT_EN_COURS": "En achat",
    "COMMANDEE": "Commandée",
    "SERVIE": "Servie",
    "CLOTUREE": "Clôturée",
    "REFUSEE": "Refusée",
    "ANNULEE": "Désactivée",
}

DEFAULT_CATEGORIES = (
    {
        "code": "FOURNITURES",
        "name": "Fournitures",
        "description": "Demander des fournitures de bureau",
        "icon": "inventory_2",
        "requires_stock_check": True,
        "requires_purchase": True,
        "can_create_purchase": True,
        "owner_espace_code": "moyens-generaux",
        "target_espace_code": "moyens-generaux",
        "source_espaces": ["*"],
        "sort_order": 1,
    },
    {
        "code": "CARNET_BUVETTE",
        "name": "Carnet de buvette",
        "description": "Demander un carnet",
        "icon": "local_cafe",
        "requires_stock_check": True,
        "requires_purchase": False,
        "can_create_purchase": False,
        "owner_espace_code": "moyens-generaux",
        "target_espace_code": "moyens-generaux",
        "source_espaces": ["*"],
        "sort_order": 2,
    },
    {
        "code": "DEMANDE_ACHAT",
        "name": "Demande d'achat",
        "description": "Demander un achat spécifique",
        "icon": "shopping_cart",
        "requires_stock_check": False,
        "requires_purchase": True,
        "can_create_purchase": True,
        "owner_espace_code": "moyens-generaux",
        "target_espace_code": "moyens-generaux",
        "source_espaces": ["*"],
        "sort_order": 3,
    },
    {
        "code": "MATERIEL_BUREAU",
        "name": "Matériel de bureau",
        "description": "Demander du matériel",
        "icon": "computer",
        "requires_stock_check": True,
        "requires_purchase": True,
        "can_create_purchase": True,
        "owner_espace_code": "moyens-generaux",
        "target_espace_code": "moyens-generaux",
        "source_espaces": ["*"],
        "sort_order": 4,
    },
    {
        "code": "AUTRE",
        "name": "Autre demande MG",
        "description": "Demande interne hors catalogue",
        "icon": "more_horiz",
        "requires_stock_check": False,
        "requires_purchase": True,
        "can_create_purchase": True,
        "owner_espace_code": "moyens-generaux",
        "target_espace_code": "moyens-generaux",
        "source_espaces": ["*"],
        "sort_order": 5,
    },
)


class MgRequestsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_categories(self) -> None:
        rows = list((await self.db.execute(select(MgRequestCategory))).scalars())
        by_code = {r.code: r for r in rows}
        for spec in DEFAULT_CATEGORIES:
            row = by_code.get(spec["code"])
            if row is None:
                self.db.add(MgRequestCategory(**spec, active=True))
                continue
            if not row.owner_espace_code:
                row.owner_espace_code = spec["owner_espace_code"]
            if not row.target_espace_code:
                row.target_espace_code = spec["target_espace_code"]
            if not row.source_espaces:
                row.source_espaces = spec["source_espaces"]
        await self.db.flush()

    async def _next_number(self, model, field, prefix: str, width: int = 6) -> str:
        year = date.today().year
        like = f"{prefix}-{year}-%"
        count = int(
            (await self.db.scalar(select(func.count()).select_from(model).where(field.like(like))))
            or 0
        )
        return f"{prefix}-{year}-{count + 1:0{width}d}"

    async def _agence(self, agency_id: uuid.UUID) -> Agence:
        ag = await self.db.get(Agence, agency_id)
        if not ag or getattr(ag, "deleted_at", None) is not None or not ag.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Agence invalide")
        return ag

    def _apply_items(self, row: MgEmployeeRequest, items: list[RequestItemIn]) -> None:
        row.items.clear()
        for it in items:
            qty = Decimal(it.quantity)
            price = Decimal(it.estimated_unit_price or 0)
            row.items.append(
                MgEmployeeRequestItem(
                    article_id=it.article_id,
                    description=it.description.strip(),
                    quantity=qty,
                    unit=(it.unit or "U").strip()[:20],
                    estimated_unit_price=price,
                    estimated_total=(qty * price).quantize(Decimal("0.01")),
                )
            )

    async def _stock_hints(self, row: MgEmployeeRequest) -> list[StockHintOut]:
        hints: list[StockHintOut] = []
        for it in row.items:
            if not it.article_id:
                continue
            art = await self.db.get(MgArticle, it.article_id)
            if not art or getattr(art, "deleted_at", None):
                continue
            actuel = Decimal(art.stock_actuel or 0)
            after = actuel - Decimal(it.quantity)
            available = after >= 0
            it.stock_checked = True
            it.stock_available = available
            it.stock_actuel = actuel
            hints.append(
                StockHintOut(
                    article_id=art.id,
                    designation=art.designation,
                    stock_actuel=actuel,
                    stock_min=art.stock_min,
                    quantity=it.quantity,
                    after=after,
                    available=available,
                )
            )
        return hints

    async def serialize(self, row: MgEmployeeRequest, *, with_stock: bool = False) -> RequestOut:
        await self.db.refresh(row, ["items", "approvals", "category", "comments"])
        requester = await self.db.get(User, row.requester_id)
        agence = await self.db.get(Agence, row.agency_id)
        dept = await self.db.get(Departement, row.department_id) if row.department_id else None
        assignee = await self.db.get(User, row.assigned_to_id) if row.assigned_to_id else None
        batch_number = None
        if row.batch_id:
            batch = await self.db.get(MgProcurementBatch, row.batch_id)
            batch_number = batch.batch_number if batch else None
        hints = await self._stock_hints(row) if with_stock else []
        comments = []
        for c in sorted(row.comments, key=lambda x: x.created_at):
            author = await self.db.get(User, c.author_id)
            comments.append(
                {
                    "id": c.id,
                    "author_id": c.author_id,
                    "author_name": author.full_name if author else None,
                    "body": c.body,
                    "visibility": c.visibility,
                    "created_at": c.created_at,
                }
            )
        return RequestOut(
            id=row.id,
            request_number=row.request_number,
            requester_id=row.requester_id,
            requester_name=requester.full_name if requester else None,
            department_id=row.department_id,
            department_label=dept.libelle if dept else None,
            agency_id=row.agency_id,
            agency_label=agence.libelle if agence else None,
            category_id=row.category_id,
            category_code=row.category.code if row.category else None,
            category_name=row.category.name if row.category else None,
            source_espace_code=row.source_espace_code,
            source_espace_label=ESPACE_LABELS.get(row.source_espace_code, row.source_espace_code),
            target_espace_code=row.target_espace_code,
            target_espace_label=ESPACE_LABELS.get(row.target_espace_code, row.target_espace_code),
            assigned_to_id=row.assigned_to_id,
            assigned_to_name=assignee.full_name if assignee else None,
            title=row.title,
            description=row.description,
            priority=row.priority,
            status=row.status,
            period=row.period,
            submitted_at=row.submitted_at,
            received_at=row.received_at,
            validated_at=row.validated_at,
            rejected_at=row.rejected_at,
            closed_at=row.closed_at,
            rejection_reason=row.rejection_reason,
            validation_comment=row.validation_comment,
            complement_comment=row.complement_comment,
            achat_demande_id=row.achat_demande_id,
            batch_id=row.batch_id,
            batch_number=batch_number,
            created_at=row.created_at,
            items=row.items,
            approvals=row.approvals,
            comments=comments,
            stock_hints=hints,
        )

    async def _load(self, request_id: uuid.UUID) -> MgEmployeeRequest:
        row = await self.db.scalar(
            select(MgEmployeeRequest)
            .options(
                selectinload(MgEmployeeRequest.items),
                selectinload(MgEmployeeRequest.approvals),
                selectinload(MgEmployeeRequest.comments),
                selectinload(MgEmployeeRequest.category),
            )
            .where(MgEmployeeRequest.id == request_id)
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Demande introuvable")
        return row

    async def _approve(
        self, row: MgEmployeeRequest, user: User, action: str, comment: str | None = None
    ) -> None:
        self.db.add(
            MgRequestApproval(
                request_id=row.id,
                approver_id=user.id,
                action=action,
                status=row.status,
                comment=comment,
                acted_at=datetime.now(timezone.utc),
            )
        )

    async def list_categories(
        self, *, active_only: bool = True, source_espace: str | None = None
    ) -> list[MgRequestCategory]:
        await self.ensure_categories()
        stmt = select(MgRequestCategory).order_by(MgRequestCategory.sort_order, MgRequestCategory.name)
        if active_only:
            stmt = stmt.where(MgRequestCategory.active.is_(True))
        rows = list((await self.db.execute(stmt)).scalars().all())
        if not source_espace:
            return rows
        out = []
        for row in rows:
            allowed = row.source_espaces or ["*"]
            if "*" in allowed or source_espace in allowed:
                out.append(row)
        return out

    async def upsert_category(self, data: CategoryIn) -> MgRequestCategory:
        await self.ensure_categories()
        code = data.code.strip().upper()
        owner = (data.owner_espace_code or "moyens-generaux").strip()
        row = await self.db.scalar(
            select(MgRequestCategory).where(
                MgRequestCategory.code == code,
                MgRequestCategory.owner_espace_code == owner,
            )
        )
        if row is None:
            row = MgRequestCategory(code=code, owner_espace_code=owner)
            self.db.add(row)
        row.name = data.name.strip()
        row.description = data.description
        row.icon = data.icon
        row.form_schema = data.form_schema
        row.requires_stock_check = data.requires_stock_check
        row.requires_purchase = data.requires_purchase
        row.can_create_purchase = data.can_create_purchase
        row.requires_attachment = data.requires_attachment
        row.owner_espace_code = (data.owner_espace_code or "moyens-generaux").strip()
        row.target_espace_code = (data.target_espace_code or "moyens-generaux").strip()
        row.source_espaces = data.source_espaces or ["*"]
        row.active = data.active
        row.sort_order = data.sort_order
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def create_request(
        self,
        data: RequestCreate,
        user: User,
        *,
        source_espace_code: str = "comptabilite",
        source_module_code: str = "demandes-comptabilite",
    ) -> MgEmployeeRequest:
        await self.ensure_categories()
        cat = await self.db.get(MgRequestCategory, data.category_id)
        if cat is None or not cat.active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Catégorie inactive ou inconnue")
        allowed = getattr(cat, "source_espaces", None) or ["*"]
        if "*" not in allowed and source_espace_code not in allowed:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Type de demande non disponible ici")
        agency_id = data.agency_id or user.agence_id
        if agency_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Agence obligatoire")
        await self._agence(agency_id)
        if not data.items:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Au moins un article est obligatoire")
        title = (data.title or "").strip() or f"{cat.name} — {user.full_name}"
        target = getattr(cat, "target_espace_code", None) or "moyens-generaux"
        row = MgEmployeeRequest(
            request_number=await self._next_number(
                MgEmployeeRequest, MgEmployeeRequest.request_number, "DEM", 6
            ),
            requester_id=user.id,
            department_id=data.department_id,
            agency_id=agency_id,
            category_id=cat.id,
            source_espace_code=source_espace_code,
            target_espace_code=target,
            title=title[:255],
            description=data.description,
            priority=(data.priority or "NORMALE").strip().upper(),
            period=data.period,
            status="BROUILLON",
        )
        self._apply_items(row, data.items)
        self.db.add(row)
        await self.db.flush()
        await self._approve(row, user, "CREATED")
        await audit_request(
            self.db, user, "REQUEST_CREATED", "mg_employee_request", row.id,
            after={"number": row.request_number},
            espace_code=source_espace_code,
            module_code=source_module_code,
        )
        await self.db.commit()
        return await self._load(row.id)

    async def update_request(
        self, request_id: uuid.UUID, data: RequestUpdate, user: User, *, owner_only: bool
    ) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if owner_only and row.requester_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Demande non autorisée")
        if row.status not in EDITABLE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cette demande n’est plus modifiable")
        if data.agency_id is not None:
            await self._agence(data.agency_id)
            row.agency_id = data.agency_id
        if data.category_id is not None:
            cat = await self.db.get(MgRequestCategory, data.category_id)
            if cat is None or not cat.active:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Catégorie invalide")
            row.category_id = cat.id
        if data.department_id is not None:
            row.department_id = data.department_id
        if data.title is not None:
            row.title = data.title.strip()[:255]
        if data.description is not None:
            row.description = data.description
        if data.priority is not None:
            row.priority = data.priority.strip().upper()
        if data.period is not None:
            row.period = data.period
        if data.items is not None:
            if not data.items:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Au moins un article est obligatoire")
            self._apply_items(row, data.items)
        await audit_request(self.db, user, "REQUEST_UPDATED", "mg_employee_request", row.id)
        await self.db.commit()
        return await self._load(row.id)

    async def submit(self, request_id: uuid.UUID, user: User) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if row.requester_id != user.id and not user.is_superuser:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Demande non autorisée")
        if row.status not in EDITABLE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Soumission impossible")
        if not row.items:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ajoutez au moins un article")
        row.status = "SOUMISE"
        row.submitted_at = datetime.now(timezone.utc)
        row.complement_comment = None
        await self._approve(row, user, "SUBMITTED")
        await audit_request(self.db, user, "REQUEST_SUBMITTED", "mg_employee_request", row.id)
        await notify_requester(
            self.db, row.requester_id, "Demande soumise",
            f"Votre demande {row.request_number} a été soumise aux Moyens Généraux.",
            entity_id=row.id, actor=user,
        )
        prio = "urgente " if row.priority in URGENT else ""
        await notify_mg_roles(
            self.db, "Nouvelle demande employé",
            f"{prio}{row.request_number} — {row.title}",
            entity_id=row.id, actor=user,
        )
        await self.db.commit()
        return await self._load(row.id)

    async def cancel(self, request_id: uuid.UUID, user: User, comment: str | None) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if row.requester_id != user.id and not user.is_superuser:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Demande non autorisée")
        if row.status in CLOSED or row.status in {"REGROUPEE", "ACHAT_EN_COURS", "COMMANDEE"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cette demande ne peut plus être annulée")
        row.status = "ANNULEE"
        row.closed_at = datetime.now(timezone.utc)
        await self._approve(row, user, "CANCELLED", comment)
        await audit_request(self.db, user, "REQUEST_CANCELLED", "mg_employee_request", row.id)
        await self.db.commit()
        return await self._load(row.id)

    async def mg_cancel(self, request_id: uuid.UUID, user: User, comment: str | None) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if row.status in CLOSED or row.status in {"REGROUPEE", "ACHAT_EN_COURS", "COMMANDEE"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cette demande ne peut plus être désactivée")
        row.status = "ANNULEE"
        row.closed_at = datetime.now(timezone.utc)
        await self._approve(row, user, "CANCELLED", comment or "Désactivée par les Moyens Généraux")
        await audit_request(self.db, user, "REQUEST_CANCELLED", "mg_employee_request", row.id)
        await notify_requester(
            self.db, row.requester_id, "Demande désactivée",
            f"Votre demande {row.request_number} a été désactivée par les Moyens Généraux.",
            entity_id=row.id, actor=user,
        )
        await self.db.commit()
        return await self._load(row.id)

    async def mg_delete(self, request_id: uuid.UUID, user: User) -> None:
        row = await self._load(request_id)
        if row.status in DELETE_LOCKED or row.batch_id or row.achat_demande_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Cette demande est déjà engagée et ne peut plus être supprimée.",
            )
        await audit_request(self.db, user, "REQUEST_DELETED", "mg_employee_request", row.id)
        await self.db.delete(row)
        await self.db.commit()

    async def delete_draft(self, request_id: uuid.UUID, user: User) -> None:
        row = await self._load(request_id)
        if row.requester_id != user.id and not user.is_superuser:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Demande non autorisée")
        if row.status in DELETE_LOCKED or row.batch_id or row.achat_demande_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Cette demande est déjà engagée (validation, regroupement ou achat) et ne peut plus être supprimée.",
            )
        await audit_request(self.db, user, "REQUEST_DELETED", "mg_employee_request", row.id)
        await self.db.delete(row)
        await self.db.commit()

    async def mark_received(self, row: MgEmployeeRequest, user: User) -> None:
        if row.status != "SOUMISE":
            return
        row.status = "RECUE"
        row.received_at = datetime.now(timezone.utc)
        await self._approve(row, user, "RECEIVED")
        await notify_requester(
            self.db, row.requester_id, "Demande reçue",
            f"Votre demande {row.request_number} a été reçue par les Moyens Généraux.",
            entity_id=row.id, actor=user,
        )

    async def get_mg(
        self, request_id: uuid.UUID, user: User, *, target_espace: str | None = None
    ) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if (
            target_espace
            and not user.is_superuser
            and row.target_espace_code != target_espace
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Demande hors de votre périmètre")
        if row.status == "SOUMISE":
            await self.mark_received(row, user)
            await audit_request(self.db, user, "REQUEST_RECEIVED", "mg_employee_request", row.id)
            await self.db.commit()
            row = await self._load(request_id)
        return row

    async def set_granted_quantities(
        self, request_id: uuid.UUID, user: User, data: GrantedIn
    ) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if row.status in CLOSED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cette demande n’est plus modifiable")
        by_id = {it.id: it for it in row.items}
        for line in data.lines:
            item = by_id.get(line.item_id)
            if item is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ligne inconnue")
            if line.quantity_granted is None:
                item.quantity_granted = None
                continue
            if line.quantity_granted > item.quantity:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"La quantité accordée dépasse la quantité demandée ({item.description})",
                )
            item.quantity_granted = line.quantity_granted
        await audit_request(self.db, user, "REQUEST_UPDATED", "mg_employee_request", row.id)
        await self.db.commit()
        return await self._load(request_id)

    async def request_info(self, request_id: uuid.UUID, user: User, comment: str | None) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if row.status not in OPEN_FOR_MG | {"A_COMPLETER"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Complément impossible à ce stade")
        row.status = "A_COMPLETER"
        row.complement_comment = comment
        await self._approve(row, user, "REQUESTED_INFO", comment)
        await audit_request(self.db, user, "REQUEST_COMPLEMENT_REQUESTED", "mg_employee_request", row.id)
        await notify_requester(
            self.db, row.requester_id, "Complément demandé",
            f"Votre demande {row.request_number} nécessite des informations complémentaires.",
            entity_id=row.id, actor=user,
        )
        await self.db.commit()
        return await self._load(row.id)

    async def validate(self, request_id: uuid.UUID, user: User, comment: str | None) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if row.status not in OPEN_FOR_MG:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Validation impossible à ce stade")
        row.status = "A_REGROUPER"
        row.validated_at = datetime.now(timezone.utc)
        row.validated_by = user.id
        row.validation_comment = comment
        await self._approve(row, user, "VALIDATED", comment)
        await audit_request(self.db, user, "REQUEST_VALIDATED", "mg_employee_request", row.id)
        await notify_requester(
            self.db, row.requester_id, "Demande validée",
            f"Votre demande {row.request_number} a été validée.",
            entity_id=row.id, actor=user,
        )
        await self.db.commit()
        return await self._load(row.id)

    async def reject(self, request_id: uuid.UUID, user: User, comment: str | None) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if row.status in CLOSED or row.status in {"REGROUPEE", "ACHAT_EN_COURS", "COMMANDEE"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Refus impossible à ce stade")
        if not comment:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Le motif de refus est obligatoire")
        row.status = "REFUSEE"
        row.rejected_at = datetime.now(timezone.utc)
        row.rejected_by = user.id
        row.rejection_reason = comment
        row.closed_at = datetime.now(timezone.utc)
        await self._approve(row, user, "REJECTED", comment)
        await audit_request(self.db, user, "REQUEST_REJECTED", "mg_employee_request", row.id)
        await notify_requester(
            self.db, row.requester_id, "Demande refusée",
            f"Votre demande {row.request_number} a été refusée.",
            entity_id=row.id, actor=user,
        )
        await self.db.commit()
        return await self._load(row.id)

    async def serve_from_stock(self, request_id: uuid.UUID, user: User) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if row.status not in GROUPABLE | OPEN_FOR_MG:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Service stock impossible à ce stade")
        stockable = [it for it in row.items if it.article_id]
        if not stockable:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Aucun article lié au stock — passez par un regroupement achat",
            )
        stock = MgStockService(self.db)
        for it in stockable:
            await stock.create_mouvement(
                MouvementCreate(
                    article_id=it.article_id,
                    type_mouvement="SORTIE",
                    quantite=it.quantity,
                    agence_id=row.agency_id,
                    motif=f"Demande {row.request_number}",
                    source_type="mg_employee_request",
                    source_id=it.id,
                ),
                user,
            )
            it.status = "SERVIE"
        row.status = "SERVIE"
        row.closed_at = datetime.now(timezone.utc)
        await self._approve(row, user, "SERVED")
        await audit_request(self.db, user, "REQUEST_SERVED", "mg_employee_request", row.id)
        await notify_requester(
            self.db, row.requester_id, "Demande servie",
            f"Votre demande {row.request_number} a été servie depuis le stock.",
            entity_id=row.id, actor=user,
        )
        await self.db.commit()
        return await self._load(row.id)

    def _filters(
        self,
        *,
        q: str | None,
        statut: str | None,
        category_id: uuid.UUID | None,
        agency_id: uuid.UUID | None,
        requester_id: uuid.UUID | None,
        priority: str | None,
        mine: uuid.UUID | None,
        source_espace: str | None = None,
        target_espace: str | None = None,
    ):
        filters = []
        if mine is not None:
            filters.append(MgEmployeeRequest.requester_id == mine)
        if source_espace:
            filters.append(MgEmployeeRequest.source_espace_code == source_espace)
        if target_espace:
            filters.append(MgEmployeeRequest.target_espace_code == target_espace)
        if statut:
            if statut == "a_traiter":
                filters.append(MgEmployeeRequest.status.in_(["SOUMISE", "RECUE", "EN_ANALYSE"]))
            elif statut == "urgentes":
                filters.append(MgEmployeeRequest.priority.in_(list(URGENT)))
                filters.append(MgEmployeeRequest.status.notin_(list(CLOSED)))
            elif statut == "a_regrouper":
                filters.append(MgEmployeeRequest.status.in_(list(GROUPABLE)))
            else:
                filters.append(MgEmployeeRequest.status == statut.upper())
        if category_id:
            filters.append(MgEmployeeRequest.category_id == category_id)
        if agency_id:
            filters.append(MgEmployeeRequest.agency_id == agency_id)
        if requester_id:
            filters.append(MgEmployeeRequest.requester_id == requester_id)
        if priority:
            filters.append(MgEmployeeRequest.priority == priority.upper())
        if q:
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    MgEmployeeRequest.request_number.ilike(like),
                    MgEmployeeRequest.title.ilike(like),
                    MgEmployeeRequest.description.ilike(like),
                )
            )
        return filters

    async def list_requests(
        self,
        *,
        q: str | None = None,
        statut: str | None = None,
        category_id: uuid.UUID | None = None,
        agency_id: uuid.UUID | None = None,
        requester_id: uuid.UUID | None = None,
        priority: str | None = None,
        mine: uuid.UUID | None = None,
        source_espace: str | None = None,
        target_espace: str | None = None,
        page: int = 1,
        size: int = 30,
    ) -> tuple[list[MgEmployeeRequest], int]:
        filters = self._filters(
            q=q, statut=statut, category_id=category_id, agency_id=agency_id,
            requester_id=requester_id, priority=priority, mine=mine,
            source_espace=source_espace, target_espace=target_espace,
        )
        stmt = select(MgEmployeeRequest)
        if filters:
            stmt = stmt.where(*filters)
        total = int((await self.db.scalar(select(func.count()).select_from(stmt.subquery()))) or 0)
        page = max(1, page)
        size = min(100, max(1, size))
        rows = list(
            (
                await self.db.execute(
                    stmt.options(
                        selectinload(MgEmployeeRequest.items),
                        selectinload(MgEmployeeRequest.approvals),
                        selectinload(MgEmployeeRequest.comments),
                        selectinload(MgEmployeeRequest.category),
                    )
                    .order_by(MgEmployeeRequest.created_at.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).scalars().all()
        )
        return rows, total

    async def dashboard(self, *, target_espace: str | None = None) -> dict:
        today = date.today()
        start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        scope = []
        if target_espace:
            scope.append(MgEmployeeRequest.target_espace_code == target_espace)
        statuses = (
            await self.db.execute(
                select(MgEmployeeRequest.status, func.count())
                .where(*scope)
                .group_by(MgEmployeeRequest.status)
            )
        ).all()
        counts = {s: int(n) for s, n in statuses}
        urgentes = int(
            (
                await self.db.scalar(
                    select(func.count()).select_from(MgEmployeeRequest).where(
                        *scope,
                        MgEmployeeRequest.priority.in_(list(URGENT)),
                        MgEmployeeRequest.status.notin_(list(CLOSED)),
                    )
                )
            )
            or 0
        )
        aujourd_hui = int(
            (
                await self.db.scalar(
                    select(func.count()).select_from(MgEmployeeRequest).where(
                        *scope,
                        MgEmployeeRequest.submitted_at >= start
                    )
                )
            )
            or 0
        )
        par_cat_stmt = (
            select(MgRequestCategory.code, MgRequestCategory.name, func.count())
            .join(MgEmployeeRequest, MgEmployeeRequest.category_id == MgRequestCategory.id)
            .group_by(MgRequestCategory.code, MgRequestCategory.name)
            .order_by(func.count().desc())
        )
        if scope:
            par_cat_stmt = par_cat_stmt.where(*scope)
        par_cat = [
            {"code": code or "—", "name": name or "—", "count": int(n)}
            for code, name, n in (await self.db.execute(par_cat_stmt)).all()
        ]
        par_agence_stmt = (
            select(Agence.libelle, func.count())
            .join(MgEmployeeRequest, MgEmployeeRequest.agency_id == Agence.id)
            .group_by(Agence.libelle)
            .order_by(func.count().desc())
        )
        if scope:
            par_agence_stmt = par_agence_stmt.where(*scope)
        par_agence = [
            {"label": label or "—", "count": int(n)}
            for label, n in (await self.db.execute(par_agence_stmt)).all()
        ]
        par_src_stmt = (
            select(MgEmployeeRequest.source_espace_code, func.count())
            .group_by(MgEmployeeRequest.source_espace_code)
            .order_by(func.count().desc())
        )
        if scope:
            par_src_stmt = par_src_stmt.where(*scope)
        par_source = [
            {
                "code": code or "—",
                "name": ESPACE_LABELS.get(code or "", code or "—"),
                "count": int(n),
            }
            for code, n in (await self.db.execute(par_src_stmt)).all()
        ]
        a_traiter = counts.get("SOUMISE", 0) + counts.get("RECUE", 0) + counts.get("EN_ANALYSE", 0)
        return {
            "a_traiter": a_traiter,
            "a_completer": counts.get("A_COMPLETER", 0),
            "validees": counts.get("VALIDEE", 0) + counts.get("A_REGROUPER", 0),
            "refusees": counts.get("REFUSEE", 0),
            "urgentes": urgentes,
            "a_regrouper": counts.get("A_REGROUPER", 0) + counts.get("VALIDEE", 0),
            "en_achat": counts.get("ACHAT_EN_COURS", 0) + counts.get("REGROUPEE", 0) + counts.get("COMMANDEE", 0),
            "servies": counts.get("SERVIE", 0) + counts.get("CLOTUREE", 0),
            "aujourd_hui": aujourd_hui,
            "par_categorie": par_cat,
            "par_agence": par_agence,
            "par_source": par_source,
        }

    async def mine_dashboard(self, user_id: uuid.UUID) -> dict:
        from app.models.audit import Notification

        scope = [MgEmployeeRequest.requester_id == user_id]
        statuses = (
            await self.db.execute(
                select(MgEmployeeRequest.status, func.count())
                .where(*scope)
                .group_by(MgEmployeeRequest.status)
            )
        ).all()
        counts = {s: int(n) for s, n in statuses}
        total = sum(counts.values())
        brouillons = counts.get("BROUILLON", 0)
        a_completer = counts.get("A_COMPLETER", 0)
        soumises = counts.get("SOUMISE", 0)
        recues = counts.get("RECUE", 0) + counts.get("EN_ANALYSE", 0)
        validees = (
            counts.get("VALIDEE", 0)
            + counts.get("A_REGROUPER", 0)
            + counts.get("REGROUPEE", 0)
            + counts.get("ACHAT_EN_COURS", 0)
            + counts.get("COMMANDEE", 0)
        )
        refusees = counts.get("REFUSEE", 0)
        servies = counts.get("SERVIE", 0) + counts.get("CLOTUREE", 0)
        annulees = counts.get("ANNULEE", 0)
        en_cours = sum(counts.get(s, 0) for s in EN_COURS)
        urgentes = int(
            (
                await self.db.scalar(
                    select(func.count()).select_from(MgEmployeeRequest).where(
                        *scope,
                        MgEmployeeRequest.priority.in_(list(URGENT)),
                        MgEmployeeRequest.status.notin_(list(CLOSED)),
                    )
                )
            )
            or 0
        )
        unread = int(
            (
                await self.db.scalar(
                    select(func.count()).select_from(Notification).where(
                        Notification.user_id == user_id,
                        Notification.archived.is_(False),
                        Notification.lu.is_(False),
                        Notification.entity == "mg_employee_request",
                    )
                )
            )
            or 0
        )
        par_cat_stmt = (
            select(MgRequestCategory.code, MgRequestCategory.name, func.count())
            .join(MgEmployeeRequest, MgEmployeeRequest.category_id == MgRequestCategory.id)
            .where(*scope)
            .group_by(MgRequestCategory.code, MgRequestCategory.name)
            .order_by(func.count().desc())
        )
        par_categorie = [
            {"code": code or "—", "name": name or "—", "count": int(n)}
            for code, name, n in (await self.db.execute(par_cat_stmt)).all()
        ]
        par_statut = [
            {"code": code, "name": STATUS_LABELS.get(code, code), "count": n}
            for code, n in sorted(counts.items(), key=lambda x: -x[1])
        ]
        recentes_rows, _ = await self.list_requests(mine=user_id, page=1, size=6)
        recentes = [await self.serialize(r) for r in recentes_rows]
        insights: list[dict] = []
        if a_completer:
            insights.append({
                "tone": "warn",
                "title": "Complément demandé",
                "text": f"{a_completer} demande(s) attendent un complément de votre part avant de repartir vers les Moyens Généraux.",
                "statut": "A_COMPLETER",
            })
        if brouillons:
            insights.append({
                "tone": "info",
                "title": "Brouillons à finaliser",
                "text": f"{brouillons} brouillon(s) n’ont pas encore été soumis. Ils restent visibles seulement de vous.",
                "statut": "BROUILLON",
            })
        if soumises:
            insights.append({
                "tone": "info",
                "title": "En attente de réception",
                "text": f"{soumises} demande(s) ont quitté votre service et attendent d’être ouvertes par les Moyens Généraux.",
                "statut": "SOUMISE",
            })
        if recues:
            insights.append({
                "tone": "ok",
                "title": "Chez les Moyens Généraux",
                "text": f"{recues} demande(s) sont reçues et en cours d’analyse (stock, regroupement ou achat).",
                "statut": "RECUE",
            })
        if urgentes:
            insights.append({
                "tone": "danger",
                "title": "Priorité haute",
                "text": f"{urgentes} demande(s) urgente(s) ou haute(s) sont encore ouvertes.",
                "statut": None,
            })
        if refusees:
            insights.append({
                "tone": "danger",
                "title": "Refus",
                "text": f"{refusees} demande(s) ont été refusées. Consultez le motif dans le détail.",
                "statut": "REFUSEE",
            })
        if servies:
            insights.append({
                "tone": "ok",
                "title": "Servies",
                "text": f"{servies} demande(s) ont été servies ou clôturées.",
                "statut": "SERVIE",
            })
        if not total:
            insights.append({
                "tone": "info",
                "title": "Aucune demande",
                "text": "Créez votre première demande interne. Elle sera routée automatiquement vers le département destinataire.",
                "statut": None,
            })
        return {
            "total": total,
            "brouillons": brouillons,
            "a_completer": a_completer,
            "en_cours": en_cours,
            "soumises": soumises,
            "recues": recues,
            "validees": validees,
            "refusees": refusees,
            "servies": servies,
            "annulees": annulees,
            "urgentes": urgentes,
            "notifications_non_lues": unread,
            "par_categorie": par_categorie,
            "par_statut": par_statut,
            "recentes": recentes,
            "insights": insights,
        }

    async def mine_documents(self, user_id: uuid.UUID) -> list[dict]:
        from app.models.ged import GedDocument

        rows, _ = await self.list_requests(mine=user_id, page=1, size=100)
        id_map = {str(r.id): r for r in rows}
        if not id_map:
            return []
        docs = list(
            (
                await self.db.execute(
                    select(GedDocument)
                    .where(
                        GedDocument.entity == "MG_EMPLOYEE_REQUEST",
                        GedDocument.entity_id.in_(list(id_map)),
                        GedDocument.deleted_at.is_(None),
                    )
                    .order_by(GedDocument.created_at.desc())
                )
            ).scalars().all()
        )
        out: list[dict] = []
        for d in docs:
            req = id_map.get(d.entity_id)
            if req is None:
                continue
            out.append({
                "id": d.id,
                "filename": d.filename,
                "title": d.title,
                "description": d.description,
                "doc_type": d.doc_type,
                "mime_type": d.mime_type,
                "size_bytes": d.size_bytes or 0,
                "ocr_status": getattr(d, "ocr_status", None),
                "archived_at": d.archived_at,
                "created_at": d.created_at,
                "request_id": req.id,
                "request_number": req.request_number,
                "request_title": req.title,
                "request_status": req.status,
            })
        return out

    async def mine_history(self, user_id: uuid.UUID) -> list[dict]:
        rows, _ = await self.list_requests(mine=user_id, page=1, size=100)
        actor_ids = {a.approver_id for r in rows for a in r.approvals}
        actors: dict[uuid.UUID, str] = {}
        if actor_ids:
            users = list(
                (await self.db.execute(select(User).where(User.id.in_(list(actor_ids))))).scalars().all()
            )
            actors = {u.id: (u.full_name or u.email or "Utilisateur") for u in users}
        events: list[dict] = []
        for r in rows:
            for a in r.approvals:
                events.append({
                    "id": str(a.id),
                    "request_id": r.id,
                    "request_number": r.request_number,
                    "title": r.title,
                    "action": a.action,
                    "action_label": APPROVAL_LABELS.get(a.action, a.action),
                    "status": a.status or r.status,
                    "comment": a.comment,
                    "actor_name": actors.get(a.approver_id),
                    "acted_at": a.acted_at,
                })
        events.sort(key=lambda e: e["acted_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return events

    def _serialize_batch(self, batch: MgProcurementBatch, category_name: str | None = None) -> BatchOut:
        req_ids = {it.request_id for it in batch.items}
        totals = sum((it.estimated_total or 0) for it in batch.items)
        groups: dict[str, ConsolidatedLineOut] = {}
        for it in batch.items:
            key = str(it.article_id) if it.article_id else it.description.strip().lower()
            if key not in groups:
                groups[key] = ConsolidatedLineOut(
                    key=key,
                    article_id=it.article_id,
                    description=it.description,
                    quantity=Decimal("0"),
                    estimated_total=Decimal("0"),
                    request_count=0,
                )
            groups[key].quantity += it.quantity
            groups[key].estimated_total += it.estimated_total
            groups[key].request_count += 1
        return BatchOut(
            id=batch.id,
            batch_number=batch.batch_number,
            category_id=batch.category_id,
            category_name=category_name,
            department_id=batch.department_id,
            agency_id=batch.agency_id,
            period=batch.period,
            title=batch.title,
            description=batch.description,
            priority=batch.priority,
            status=batch.status,
            created_by=batch.created_by,
            validated_by=batch.validated_by,
            achat_demande_id=batch.achat_demande_id,
            created_at=batch.created_at,
            request_count=len(req_ids),
            item_count=len(batch.items),
            employee_count=0,
            estimated_total=Decimal(totals),
            items=batch.items,
            consolidated=list(groups.values()),
        )

    async def _load_batch(self, batch_id: uuid.UUID) -> MgProcurementBatch:
        row = await self.db.scalar(
            select(MgProcurementBatch)
            .options(selectinload(MgProcurementBatch.items))
            .where(MgProcurementBatch.id == batch_id)
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Regroupement introuvable")
        return row

    async def _attach_requests(self, batch: MgProcurementBatch, request_ids: list[uuid.UUID]) -> None:
        taken = {
            r
            for (r,) in (
                await self.db.execute(
                    select(MgProcurementBatchItem.request_item_id).where(
                        MgProcurementBatchItem.request_item_id.in_(
                            select(MgEmployeeRequestItem.id).where(
                                MgEmployeeRequestItem.request_id.in_(request_ids)
                            )
                        )
                    )
                )
            ).all()
        }
        for rid in request_ids:
            req = await self._load(rid)
            if req.status not in GROUPABLE and req.status != "REGROUPEE":
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"{req.request_number} n’est pas validée pour regroupement",
                )
            for it in req.items:
                if it.id in taken or it.status == "GROUPEE":
                    continue
                batch.items.append(
                    MgProcurementBatchItem(
                        request_id=req.id,
                        request_item_id=it.id,
                        article_id=it.article_id,
                        description=it.description,
                        quantity=it.quantity,
                        estimated_unit_price=it.estimated_unit_price,
                        estimated_total=it.estimated_total,
                    )
                )
                it.status = "GROUPEE"
                taken.add(it.id)
            req.status = "REGROUPEE"
            req.batch_id = batch.id

    async def create_batch(self, data: BatchCreate, user: User) -> MgProcurementBatch:
        batch = MgProcurementBatch(
            batch_number=await self._next_number(
                MgProcurementBatch, MgProcurementBatch.batch_number, "RG-MG", 4
            ),
            category_id=data.category_id,
            department_id=data.department_id,
            agency_id=data.agency_id,
            period=data.period,
            title=data.title.strip()[:255],
            description=data.description,
            priority=(data.priority or "NORMALE").strip().upper(),
            status="BROUILLON",
            created_by=user.id,
        )
        self.db.add(batch)
        await self.db.flush()
        if data.request_ids:
            await self._attach_requests(batch, data.request_ids)
        await audit_request(self.db, user, "BATCH_CREATED", "mg_procurement_batch", batch.id)
        await self.db.commit()
        return await self._load_batch(batch.id)

    async def delete_batch(self, batch_id: uuid.UUID, user: User) -> None:
        batch = await self._load_batch(batch_id)
        if batch.status != "BROUILLON":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Un regroupement validé ne peut pas être supprimé")
        request_ids = {it.request_id for it in batch.items}
        item_ids = {it.request_item_id for it in batch.items}
        for request_id in request_ids:
            req = await self._load(request_id)
            if req.batch_id == batch.id:
                req.batch_id = None
                if req.status == "REGROUPEE":
                    req.status = "A_REGROUPER"
            for item in req.items:
                if item.id in item_ids and item.status == "GROUPEE":
                    item.status = "OUVERT"
        await audit_request(self.db, user, "BATCH_DELETED", "mg_procurement_batch", batch.id)
        await self.db.flush()
        await self.db.delete(batch)
        await self.db.commit()

    async def update_batch(self, batch_id: uuid.UUID, data: BatchUpdate, user: User) -> MgProcurementBatch:
        batch = await self._load_batch(batch_id)
        if batch.status != "BROUILLON":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Regroupement déjà validé")
        for field in ("title", "description", "category_id", "department_id", "agency_id", "period", "priority"):
            val = getattr(data, field)
            if val is not None:
                setattr(batch, field, val.strip().upper() if field == "priority" and isinstance(val, str) else val)
        await audit_request(self.db, user, "BATCH_UPDATED", "mg_procurement_batch", batch.id)
        await self.db.commit()
        return await self._load_batch(batch.id)

    async def add_batch_items(self, batch_id: uuid.UUID, data: BatchItemsIn, user: User) -> MgProcurementBatch:
        batch = await self._load_batch(batch_id)
        if batch.status != "BROUILLON":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Regroupement déjà validé")
        await self._attach_requests(batch, data.request_ids)
        await self.db.commit()
        return await self._load_batch(batch.id)

    async def remove_batch_item(self, batch_id: uuid.UUID, item_id: uuid.UUID, user: User) -> MgProcurementBatch:
        batch = await self._load_batch(batch_id)
        if batch.status != "BROUILLON":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Regroupement déjà validé")
        item = next((i for i in batch.items if i.id == item_id), None)
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ligne introuvable")
        src = await self.db.get(MgEmployeeRequestItem, item.request_item_id)
        if src:
            src.status = "OUVERT"
        req = await self._load(item.request_id)
        batch.items.remove(item)
        await self.db.flush()
        remaining = any(i.request_id == req.id for i in batch.items)
        if not remaining:
            req.batch_id = None
            req.status = "A_REGROUPER"
        await self.db.commit()
        return await self._load_batch(batch.id)

    async def validate_batch(self, batch_id: uuid.UUID, user: User) -> MgProcurementBatch:
        batch = await self._load_batch(batch_id)
        if batch.status != "BROUILLON":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Regroupement déjà validé")
        if not batch.items:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ajoutez au moins une demande")
        groups: dict[tuple, list[MgProcurementBatchItem]] = defaultdict(list)
        for it in batch.items:
            key = (it.article_id, it.description.strip().lower())
            groups[key].append(it)
        lignes: list[DemandeLigneIn] = []
        for items in groups.values():
            first = items[0]
            qty = sum((i.quantity for i in items), Decimal("0"))
            price = first.estimated_unit_price or Decimal("0")
            lignes.append(
                DemandeLigneIn(
                    designation=first.description,
                    quantite=qty,
                    uom="U",
                    prix_estime=price,
                    article_id=first.article_id,
                )
            )
        agency_id = batch.agency_id or next(
            (r.agency_id for r in [await self._load(batch.items[0].request_id)]),
            None,
        )
        if agency_id is None:
            first_req = await self._load(batch.items[0].request_id)
            agency_id = first_req.agency_id
        da = await MgAchatsService(self.db).create_demande(
            DemandeCreate(
                date_demande=date.today(),
                agence_id=agency_id,
                departement_id=batch.department_id,
                demandeur_nom=user.full_name,
                type_achat="FOURNITURE",
                priorite="HAUTE" if batch.priority in URGENT else "NORMAL",
                motif=f"Regroupement {batch.batch_number} — {batch.title}",
                observation=f"source_type=MG_EMPLOYEE_BATCH {batch.batch_number}",
                source_type="MG_EMPLOYEE_BATCH",
                source_id=batch.id,
                lignes=lignes,
            ),
            user,
        )
        batch.status = "VALIDE"
        batch.validated_by = user.id
        batch.achat_demande_id = da.id
        req_ids = {it.request_id for it in batch.items}
        for rid in req_ids:
            req = await self._load(rid)
            req.status = "ACHAT_EN_COURS"
            req.achat_demande_id = da.id
            await notify_requester(
                self.db, req.requester_id, "Demande regroupée",
                f"Votre demande {req.request_number} a été regroupée dans {batch.batch_number}.",
                entity_id=req.id, actor=user,
            )
        await audit_request(self.db, user, "BATCH_VALIDATED", "mg_procurement_batch", batch.id)
        await audit_request(self.db, user, "REQUEST_TO_PURCHASE_CREATED", "mg_achat_demande", da.id)
        await self.db.commit()
        return await self._load_batch(batch.id)

    async def list_batches(self, *, page: int = 1, size: int = 30) -> tuple[list[MgProcurementBatch], int]:
        total = int((await self.db.scalar(select(func.count()).select_from(MgProcurementBatch))) or 0)
        page = max(1, page)
        size = min(100, max(1, size))
        rows = list(
            (
                await self.db.execute(
                    select(MgProcurementBatch)
                    .options(selectinload(MgProcurementBatch.items))
                    .order_by(MgProcurementBatch.created_at.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).scalars().all()
        )
        return rows, total

    async def serialize_batch(self, batch: MgProcurementBatch) -> BatchOut:
        cat = await self.db.get(MgRequestCategory, batch.category_id) if batch.category_id else None
        out = self._serialize_batch(batch, cat.name if cat else None)
        req_ids = {it.request_id for it in batch.items}
        if req_ids:
            requesters = (
                await self.db.execute(
                    select(func.count(func.distinct(MgEmployeeRequest.requester_id))).where(
                        MgEmployeeRequest.id.in_(req_ids)
                    )
                )
            ).scalar()
            out.employee_count = int(requesters or 0)
        return out

    async def add_comment(self, request_id: uuid.UUID, user: User, body: str) -> MgEmployeeRequest:
        row = await self._load(request_id)
        text = (body or "").strip()
        if not text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Commentaire obligatoire")
        self.db.add(MgRequestComment(request_id=row.id, author_id=user.id, body=text[:4000]))
        await self._approve(row, user, "COMMENTED", text)
        await audit_request(self.db, user, "REQUEST_UPDATED", "mg_employee_request", row.id)
        await self.db.commit()
        return await self._load(row.id)

    async def assign(self, request_id: uuid.UUID, user: User, assigned_to_id: uuid.UUID | None) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if assigned_to_id is not None:
            assignee = await self.db.get(User, assigned_to_id)
            if assignee is None or getattr(assignee, "deleted_at", None):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Utilisateur introuvable")
        row.assigned_to_id = assigned_to_id
        await self._approve(row, user, "ASSIGNED")
        await audit_request(self.db, user, "REQUEST_UPDATED", "mg_employee_request", row.id)
        await self.db.commit()
        return await self._load(row.id)

    async def recategorize(self, request_id: uuid.UUID, user: User, category_id: uuid.UUID) -> MgEmployeeRequest:
        row = await self._load(request_id)
        if row.status in CLOSED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Catégorisation impossible")
        cat = await self.db.get(MgRequestCategory, category_id)
        if cat is None or not cat.active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Catégorie invalide")
        row.category_id = cat.id
        row.target_espace_code = cat.target_espace_code or row.target_espace_code
        await self._approve(row, user, "RECATEGORIZED", cat.code)
        await audit_request(self.db, user, "REQUEST_UPDATED", "mg_employee_request", row.id)
        await self.db.commit()
        return await self._load(row.id)

    async def refs(self) -> dict:
        agences = list(
            (
                await self.db.execute(
                    select(Agence).where(Agence.is_active.is_(True), Agence.deleted_at.is_(None)).order_by(Agence.libelle)
                )
            ).scalars().all()
        )
        depts = list(
            (
                await self.db.execute(
                    select(Departement).where(Departement.deleted_at.is_(None)).order_by(Departement.libelle)
                )
            ).scalars().all()
        )
        articles = list(
            (
                await self.db.execute(
                    select(MgArticle)
                    .where(MgArticle.deleted_at.is_(None), MgArticle.is_active.is_(True))
                    .order_by(MgArticle.designation)
                    .limit(400)
                )
            ).scalars().all()
        )
        return {
            "agences": [{"id": a.id, "label": a.libelle, "extra": a.code} for a in agences],
            "departements": [{"id": d.id, "label": d.libelle, "extra": d.code} for d in depts],
            "articles": [
                {"id": a.id, "label": a.designation, "extra": a.code} for a in articles
            ],
        }
