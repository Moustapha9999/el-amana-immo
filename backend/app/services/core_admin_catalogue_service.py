"""CORE ADMIN — départements (`plateforme_espaces`) et modules (`plateforme_modules`)."""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.data.plateforme_catalogue import DEFAULT_ESPACE_CODE, DEFAULT_MODULE_CODE
from app.models.associations import user_espace_acces_table, user_module_acces_table
from app.models.plateforme import PlateformeEspace, PlateformeModule

CODE_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
STATUTS = {"actif", "bientot", "inactif"}


def normalize_code(raw: str) -> str:
    code = (raw or "").strip().lower()
    if not CODE_RE.fullmatch(code):
        raise ValueError("Code invalide : lettres minuscules, chiffres et tirets (ex. credit, reporting-rh).")
    return code


def normalize_path(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if not trimmed.startswith("/"):
        raise ValueError("Le chemin doit commencer par /")
    return trimmed


def _iso(value) -> str | None:
    return value.isoformat() if value else None


class CoreAdminCatalogueService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _count(self, stmt) -> int:
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    def _kpis_from(self, rows: list[tuple[bool, str]]) -> dict:
        total = len(rows)
        actifs = sum(1 for active, statut in rows if active and statut == "actif")
        bientot = sum(1 for active, statut in rows if active and statut == "bientot")
        inactifs = sum(1 for active, statut in rows if (not active) or statut == "inactif")
        return {"total": total, "actifs": actifs, "bientot": bientot, "inactifs": inactifs}

    def _apply_statut(self, stmt, model, statut: str):
        if statut == "actif":
            return stmt.where(model.is_active.is_(True), model.statut == "actif")
        if statut == "bientot":
            return stmt.where(model.is_active.is_(True), model.statut == "bientot")
        if statut == "inactif":
            return stmt.where(or_(model.is_active.is_(False), model.statut == "inactif"))
        return stmt

    async def espaces_kpis(self) -> dict:
        result = await self.db.execute(select(PlateformeEspace.is_active, PlateformeEspace.statut))
        return self._kpis_from(list(result.all()))

    async def modules_kpis(self) -> dict:
        result = await self.db.execute(select(PlateformeModule.is_active, PlateformeModule.statut))
        return self._kpis_from(list(result.all()))

    async def _espace_counts(self) -> tuple[dict[UUID, int], dict[UUID, int]]:
        modules = {
            espace_id: int(n)
            for espace_id, n in (
                await self.db.execute(
                    select(PlateformeModule.espace_id, func.count()).group_by(PlateformeModule.espace_id)
                )
            ).all()
        }
        users = {
            espace_id: int(n)
            for espace_id, n in (
                await self.db.execute(
                    select(user_espace_acces_table.c.espace_id, func.count()).group_by(
                        user_espace_acces_table.c.espace_id
                    )
                )
            ).all()
        }
        return modules, users

    async def _module_user_counts(self) -> dict[UUID, int]:
        return {
            module_id: int(n)
            for module_id, n in (
                await self.db.execute(
                    select(user_module_acces_table.c.module_id, func.count()).group_by(
                        user_module_acces_table.c.module_id
                    )
                )
            ).all()
        }

    def serialize_espace(
        self,
        row: PlateformeEspace,
        *,
        modules_count: int,
        users_count: int,
        modules: list[dict] | None = None,
    ) -> dict:
        payload = {
            "id": str(row.id),
            "code": row.code,
            "label": row.label,
            "description": row.description or "",
            "route": row.route,
            "statut": row.statut,
            "sort_order": row.sort_order,
            "is_active": row.is_active,
            "locked": row.code == DEFAULT_ESPACE_CODE,
            "modules_count": modules_count,
            "users_count": users_count,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        if modules is not None:
            payload["modules"] = modules
        return payload

    def serialize_module(self, row: PlateformeModule, *, users_count: int) -> dict:
        espace = row.espace
        return {
            "id": str(row.id),
            "code": row.code,
            "label": row.label,
            "description": row.description or "",
            "entry_path": row.entry_path,
            "statut": row.statut,
            "sort_order": row.sort_order,
            "is_active": row.is_active,
            "locked": row.code == DEFAULT_MODULE_CODE,
            "espace_id": str(row.espace_id),
            "espace_code": espace.code if espace else "",
            "espace_label": espace.label if espace else "",
            "users_count": users_count,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    def _espace_filter_clauses(self, *, search: str | None, statut: str):
        clauses = []
        if search and search.strip():
            term = f"%{search.strip()}%"
            clauses.append(
                or_(
                    PlateformeEspace.code.ilike(term),
                    PlateformeEspace.label.ilike(term),
                    PlateformeEspace.description.ilike(term),
                )
            )
        stmt = select(PlateformeEspace).where(*clauses) if clauses else select(PlateformeEspace)
        return self._apply_statut(stmt, PlateformeEspace, statut)

    async def list_espaces(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        statut: str = "tous",
    ) -> tuple[list[dict], int, dict]:
        stmt = self._espace_filter_clauses(search=search, statut=statut)
        total = await self._count(select(func.count()).select_from(stmt.subquery()))
        result = await self.db.execute(
            stmt.order_by(PlateformeEspace.sort_order.asc(), PlateformeEspace.label.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list(result.scalars().all())
        mod_counts, user_counts = await self._espace_counts()
        items = [
            self.serialize_espace(
                row,
                modules_count=mod_counts.get(row.id, 0),
                users_count=user_counts.get(row.id, 0),
            )
            for row in rows
        ]
        return items, total, await self.espaces_kpis()

    async def get_espace(self, espace_id: UUID) -> PlateformeEspace | None:
        result = await self.db.execute(
            select(PlateformeEspace)
            .options(selectinload(PlateformeEspace.modules))
            .where(PlateformeEspace.id == espace_id)
        )
        return result.scalar_one_or_none()

    async def espace_fiche(self, espace_id: UUID) -> dict | None:
        row = await self.get_espace(espace_id)
        if row is None:
            return None
        mod_counts, user_counts = await self._espace_counts()
        modules = sorted(row.modules, key=lambda m: (m.sort_order, m.label))
        return self.serialize_espace(
            row,
            modules_count=mod_counts.get(row.id, 0),
            users_count=user_counts.get(row.id, 0),
            modules=[
                {
                    "id": str(mod.id),
                    "code": mod.code,
                    "label": mod.label,
                    "statut": mod.statut,
                    "is_active": mod.is_active,
                    "locked": mod.code == DEFAULT_MODULE_CODE,
                }
                for mod in modules
            ],
        )

    async def create_espace(self, payload) -> dict:
        code = normalize_code(payload.code)
        existing = await self.db.execute(select(PlateformeEspace.id).where(PlateformeEspace.code == code))
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Ce code de département existe déjà")
        if payload.statut not in STATUTS:
            raise ValueError("Statut invalide")
        row = PlateformeEspace(
            code=code,
            label=payload.label.strip(),
            description=(payload.description or "").strip(),
            route=normalize_path(payload.route),
            statut=payload.statut,
            sort_order=payload.sort_order,
            is_active=payload.statut != "inactif",
        )
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ValueError("Ce code de département existe déjà") from exc
        return self.serialize_espace(row, modules_count=0, users_count=0)

    async def update_espace(self, espace_id: UUID, payload) -> dict:
        row = await self.get_espace(espace_id)
        if row is None:
            raise ValueError("Département introuvable")
        data = payload.model_dump(exclude_unset=True)
        if "label" in data and data["label"] is not None:
            row.label = data["label"].strip()
        if "description" in data and data["description"] is not None:
            row.description = data["description"].strip()
        if "sort_order" in data and data["sort_order"] is not None:
            row.sort_order = data["sort_order"]
        if "statut" in data and data["statut"] is not None:
            if row.code == DEFAULT_ESPACE_CODE and data["statut"] != "actif":
                raise ValueError("Le département Comptabilité reste actif")
            row.statut = data["statut"]
            if data["statut"] == "inactif":
                row.is_active = False
            elif data["statut"] in {"actif", "bientot"} and not row.is_active:
                row.is_active = True
        if "route" in data:
            route = normalize_path(data["route"])
            if row.code == DEFAULT_ESPACE_CODE and route != row.route:
                raise ValueError("La route du département Comptabilité est figée")
            row.route = route
        await self.db.flush()
        return await self.espace_fiche(espace_id) or self.serialize_espace(
            row, modules_count=len(row.modules), users_count=0
        )

    async def set_espace_active(self, espace_id: UUID, *, active: bool) -> dict:
        row = await self.get_espace(espace_id)
        if row is None:
            raise ValueError("Département introuvable")
        if row.code == DEFAULT_ESPACE_CODE and not active:
            raise ValueError("Impossible de désactiver le département Comptabilité")
        row.is_active = active
        if active and row.statut == "inactif":
            row.statut = "bientot"
        if not active:
            row.statut = "inactif"
        await self.db.flush()
        return await self.espace_fiche(espace_id) or self.serialize_espace(
            row, modules_count=len(row.modules), users_count=0
        )

    async def delete_espace(self, espace_id: UUID) -> None:
        row = await self.get_espace(espace_id)
        if row is None:
            raise ValueError("Département introuvable")
        if row.code == DEFAULT_ESPACE_CODE:
            raise ValueError("Impossible de supprimer le département Comptabilité")
        if row.modules:
            raise ValueError("Retirez d’abord les modules de ce département")
        _, user_counts = await self._espace_counts()
        if user_counts.get(row.id, 0) > 0:
            raise ValueError("Des utilisateurs ont encore accès à ce département")
        await self.db.delete(row)
        await self.db.flush()

    def _module_filter_clauses(self, *, search: str | None, statut: str, espace_id: UUID | None):
        stmt = select(PlateformeModule)
        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    PlateformeModule.code.ilike(term),
                    PlateformeModule.label.ilike(term),
                    PlateformeModule.description.ilike(term),
                )
            )
        if espace_id is not None:
            stmt = stmt.where(PlateformeModule.espace_id == espace_id)
        return self._apply_statut(stmt, PlateformeModule, statut)

    async def list_modules(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        statut: str = "tous",
        espace_id: UUID | None = None,
    ) -> tuple[list[dict], int, dict]:
        filtered = self._module_filter_clauses(search=search, statut=statut, espace_id=espace_id)
        total = await self._count(select(func.count()).select_from(filtered.subquery()))
        stmt = filtered.options(selectinload(PlateformeModule.espace))
        result = await self.db.execute(
            stmt.order_by(PlateformeModule.sort_order.asc(), PlateformeModule.label.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list(result.scalars().all())
        user_counts = await self._module_user_counts()
        items = [self.serialize_module(row, users_count=user_counts.get(row.id, 0)) for row in rows]
        return items, total, await self.modules_kpis()

    async def get_module(self, module_id: UUID) -> PlateformeModule | None:
        result = await self.db.execute(
            select(PlateformeModule)
            .options(selectinload(PlateformeModule.espace))
            .where(PlateformeModule.id == module_id)
        )
        return result.scalar_one_or_none()

    async def module_fiche(self, module_id: UUID) -> dict | None:
        row = await self.get_module(module_id)
        if row is None:
            return None
        counts = await self._module_user_counts()
        return self.serialize_module(row, users_count=counts.get(row.id, 0))

    async def _get_espace_or_raise(self, espace_id: UUID) -> PlateformeEspace:
        result = await self.db.execute(select(PlateformeEspace).where(PlateformeEspace.id == espace_id))
        espace = result.scalar_one_or_none()
        if espace is None:
            raise ValueError("Département introuvable")
        return espace

    async def create_module(self, payload) -> dict:
        code = normalize_code(payload.code)
        existing = await self.db.execute(select(PlateformeModule.id).where(PlateformeModule.code == code))
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Ce code de module existe déjà")
        espace = await self._get_espace_or_raise(UUID(str(payload.espace_id)))
        if payload.statut not in STATUTS:
            raise ValueError("Statut invalide")
        row = PlateformeModule(
            espace_id=espace.id,
            code=code,
            label=payload.label.strip(),
            description=(payload.description or "").strip(),
            entry_path=normalize_path(payload.entry_path),
            statut=payload.statut,
            sort_order=payload.sort_order,
            is_active=payload.statut != "inactif",
        )
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ValueError("Ce code de module existe déjà") from exc
        await self.db.refresh(row, attribute_names=["espace"])
        return self.serialize_module(row, users_count=0)

    async def update_module(self, module_id: UUID, payload) -> dict:
        row = await self.get_module(module_id)
        if row is None:
            raise ValueError("Module introuvable")
        data = payload.model_dump(exclude_unset=True)
        if "label" in data and data["label"] is not None:
            row.label = data["label"].strip()
        if "description" in data and data["description"] is not None:
            row.description = data["description"].strip()
        if "sort_order" in data and data["sort_order"] is not None:
            row.sort_order = data["sort_order"]
        if "statut" in data and data["statut"] is not None:
            if row.code == DEFAULT_MODULE_CODE and data["statut"] != "actif":
                raise ValueError("Le module Immobilisations reste actif")
            row.statut = data["statut"]
            if data["statut"] == "inactif":
                row.is_active = False
            elif data["statut"] in {"actif", "bientot"} and not row.is_active:
                row.is_active = True
        if "entry_path" in data:
            path = normalize_path(data["entry_path"])
            if row.code == DEFAULT_MODULE_CODE and path != row.entry_path:
                raise ValueError("Le chemin d’entrée du module Immobilisations est figé")
            row.entry_path = path
        if "espace_id" in data and data["espace_id"] is not None:
            new_espace = await self._get_espace_or_raise(UUID(str(data["espace_id"])))
            if row.code == DEFAULT_MODULE_CODE and new_espace.id != row.espace_id:
                raise ValueError("Le module Immobilisations reste rattaché à Comptabilité")
            row.espace_id = new_espace.id
        await self.db.flush()
        return await self.module_fiche(module_id) or self.serialize_module(row, users_count=0)

    async def set_module_active(self, module_id: UUID, *, active: bool) -> dict:
        row = await self.get_module(module_id)
        if row is None:
            raise ValueError("Module introuvable")
        if row.code == DEFAULT_MODULE_CODE and not active:
            raise ValueError("Impossible de désactiver le module Immobilisations")
        row.is_active = active
        if active and row.statut == "inactif":
            row.statut = "bientot"
        if not active:
            row.statut = "inactif"
        await self.db.flush()
        return await self.module_fiche(module_id) or self.serialize_module(row, users_count=0)

    async def delete_module(self, module_id: UUID) -> None:
        row = await self.get_module(module_id)
        if row is None:
            raise ValueError("Module introuvable")
        if row.code == DEFAULT_MODULE_CODE:
            raise ValueError("Impossible de supprimer le module Immobilisations")
        counts = await self._module_user_counts()
        if counts.get(row.id, 0) > 0:
            raise ValueError("Des utilisateurs ont encore accès à ce module")
        await self.db.delete(row)
        await self.db.flush()
