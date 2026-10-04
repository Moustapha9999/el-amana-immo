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
from app.models.plateforme import PlateformeDomaine, PlateformeEspace, PlateformeModule

CODE_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")

# Chemins réservés (shell immo + chrome plateforme) — route espace ≠ ces segments.
RESERVED_ESPACE_ROUTE_SEGMENTS = frozenset(
    {
        "login",
        "forgot-password",
        "reset-password",
        "accueil",
        "admin",
        "modules",
        "dashboard",
        "immobilisations",
        "inventaire",
        "amortissements",
        "amortissements-agence",
        "recap-amortissement",
        "recap-immobilisations",
        "comptes",
        "archives",
        "pieces-comptables",
        "ecritures",
        "cessions",
        "rebuts",
        "reevaluations",
        "notifications",
        "rapports",
        "utilisateurs",
        "audit",
        "parametres",
    }
)

STATUTS = {
    "actif",
    "bientot",
    "inactif",
    "developpement",
    "mise_a_jour",
    "maintenance",
    "suspendu",
    "bloque",
    "archive",
}
PROTECTED_RUNTIME_STATUTS = frozenset({"actif", "maintenance", "mise_a_jour"})


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


def default_espace_route(code: str) -> str:
    return f"/{code}"


def assert_espace_route_allowed(route: str | None, *, code: str) -> str:
    """Impose une route hub `/{code}` utilisable par la plateforme (pas un segment immo)."""
    path = normalize_path(route) or default_espace_route(code)
    segment = path.strip("/").split("/", 1)[0]
    if not segment:
        raise ValueError("Route département invalide")
    if code != DEFAULT_ESPACE_CODE and segment in RESERVED_ESPACE_ROUTE_SEGMENTS:
        raise ValueError(
            f"Route réservée (« /{segment} »). Utilisez /{code} ou un autre chemin libre."
        )
    return path


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
        domaines: list[dict] | None = None,
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
            "icon": row.icon,
            "modules_count": modules_count,
            "users_count": users_count,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        if modules is not None:
            payload["modules"] = modules
        if domaines is not None:
            payload["domaines"] = domaines
        return payload

    def serialize_module(self, row: PlateformeModule, *, users_count: int) -> dict:
        espace = row.espace
        domaine = row.domaine if row.domaine_id else None
        return {
            "id": str(row.id),
            "code": row.code,
            "label": row.label,
            "description": row.description or "",
            "entry_path": row.entry_path,
            "statut": row.statut,
            "status_message": getattr(row, "status_message", "") or "",
            "version": getattr(row, "version", None) or "1.0.0",
            "sort_order": row.sort_order,
            "is_active": row.is_active,
            "locked": row.code == DEFAULT_MODULE_CODE,
            "espace_id": str(row.espace_id),
            "espace_code": espace.code if espace else "",
            "espace_label": espace.label if espace else "",
            "icon": row.icon,
            "domaine_id": str(row.domaine_id) if row.domaine_id else None,
            "domaine_code": domaine.code if domaine else None,
            "domaine_label": domaine.label if domaine else None,
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
            .options(
                selectinload(PlateformeEspace.modules),
                selectinload(PlateformeEspace.domaines),
            )
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
            domaines=await self.list_domaines(espace_id=row.id),
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
            route=assert_espace_route_allowed(payload.route, code=code),
            statut=payload.statut,
            sort_order=payload.sort_order,
            icon=payload.icon,
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
        if "icon" in data:
            row.icon = data["icon"] or None
        if "statut" in data and data["statut"] is not None:
            if row.code == DEFAULT_ESPACE_CODE and data["statut"] != "actif":
                raise ValueError("Le département Comptabilité reste actif")
            row.statut = data["statut"]
            if data["statut"] == "inactif":
                row.is_active = False
            elif data["statut"] in {"actif", "bientot"} and not row.is_active:
                row.is_active = True
        if "route" in data:
            if row.code == DEFAULT_ESPACE_CODE:
                incoming = normalize_path(data["route"])
                if incoming != row.route:
                    raise ValueError("La route du département Comptabilité est figée")
            else:
                row.route = assert_espace_route_allowed(data["route"], code=row.code)
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
        if row.domaines:
            raise ValueError("Retirez d’abord les domaines de ce département")
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
        stmt = filtered.options(
            selectinload(PlateformeModule.espace), selectinload(PlateformeModule.domaine)
        )
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
            .options(selectinload(PlateformeModule.espace), selectinload(PlateformeModule.domaine))
            .where(PlateformeModule.id == module_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def _resolve_domaine_for(self, domaine_id: str | None, *, espace_id: UUID) -> UUID | None:
        if not domaine_id:
            return None
        dom = await self.db.scalar(
            select(PlateformeDomaine).where(PlateformeDomaine.id == UUID(str(domaine_id)))
        )
        if dom is None:
            raise ValueError("Domaine introuvable")
        if dom.espace_id != espace_id:
            raise ValueError("Le domaine doit appartenir au département du module")
        return dom.id

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
            icon=payload.icon,
            domaine_id=await self._resolve_domaine_for(payload.domaine_id, espace_id=espace.id),
            is_active=payload.statut != "inactif",
        )
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ValueError("Ce code de module existe déjà") from exc
        await self.db.refresh(row, attribute_names=["espace", "domaine"])
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
            if row.code == DEFAULT_MODULE_CODE and data["statut"] not in PROTECTED_RUNTIME_STATUTS:
                raise ValueError(
                    "Le module Immobilisations accepte uniquement actif, maintenance ou mise à jour"
                )
            row.statut = data["statut"]
            if data["statut"] == "inactif":
                row.is_active = False
            elif data["statut"] in STATUTS - {"inactif", "archive"} and not row.is_active:
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
            if new_espace.id != row.espace_id and "domaine_id" not in data:
                row.domaine_id = None
            row.espace_id = new_espace.id
        if "icon" in data:
            row.icon = data["icon"] or None
        if "domaine_id" in data:
            row.domaine_id = await self._resolve_domaine_for(data["domaine_id"], espace_id=row.espace_id)
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

    # --- Domaines / sous-domaines (regroupement de modules dans un département) ---

    async def _domaine_counts(self) -> tuple[dict[UUID, int], dict[UUID, int]]:
        modules = {
            dom_id: int(n)
            for dom_id, n in (
                await self.db.execute(
                    select(PlateformeModule.domaine_id, func.count())
                    .where(PlateformeModule.domaine_id.is_not(None))
                    .group_by(PlateformeModule.domaine_id)
                )
            ).all()
        }
        children = {
            parent_id: int(n)
            for parent_id, n in (
                await self.db.execute(
                    select(PlateformeDomaine.parent_id, func.count())
                    .where(PlateformeDomaine.parent_id.is_not(None))
                    .group_by(PlateformeDomaine.parent_id)
                )
            ).all()
        }
        return modules, children

    def serialize_domaine(
        self,
        row: PlateformeDomaine,
        *,
        by_id: dict[UUID, PlateformeDomaine],
        espace_code: str,
        modules_count: int,
        children_count: int,
    ) -> dict:
        parent = by_id.get(row.parent_id) if row.parent_id else None
        return {
            "id": str(row.id),
            "code": row.code,
            "espace_id": str(row.espace_id),
            "espace_code": espace_code,
            "parent_id": str(row.parent_id) if row.parent_id else None,
            "parent_code": parent.code if parent else None,
            "label": row.label,
            "description": row.description or "",
            "icon": row.icon,
            "statut": row.statut,
            "status_message": row.status_message or "",
            "sort_order": row.sort_order,
            "is_active": row.is_active,
            "modules_count": modules_count,
            "children_count": children_count,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    async def list_domaines(self, *, espace_id: UUID | None = None) -> list[dict]:
        stmt = select(PlateformeDomaine).options(selectinload(PlateformeDomaine.espace))
        if espace_id is not None:
            stmt = stmt.where(PlateformeDomaine.espace_id == espace_id)
        rows = list(
            (
                await self.db.execute(
                    stmt.order_by(PlateformeDomaine.sort_order.asc(), PlateformeDomaine.label.asc())
                )
            ).scalars().all()
        )
        by_id = {r.id: r for r in rows}
        mod_counts, child_counts = await self._domaine_counts()
        # Parents avant enfants, ordre d'affichage conservé.
        ordered: list[PlateformeDomaine] = []
        for root in (r for r in rows if r.parent_id is None or r.parent_id not in by_id):
            ordered.append(root)
            ordered.extend(r for r in rows if r.parent_id == root.id)
        return [
            self.serialize_domaine(
                r,
                by_id=by_id,
                espace_code=r.espace.code if r.espace else "",
                modules_count=mod_counts.get(r.id, 0),
                children_count=child_counts.get(r.id, 0),
            )
            for r in ordered
        ]

    async def get_domaine(self, domaine_id: UUID) -> PlateformeDomaine | None:
        return await self.db.scalar(
            select(PlateformeDomaine)
            .options(selectinload(PlateformeDomaine.espace))
            .where(PlateformeDomaine.id == domaine_id)
        )

    async def domaine_fiche(self, domaine_id: UUID) -> dict | None:
        row = await self.get_domaine(domaine_id)
        if row is None:
            return None
        parent = await self.get_domaine(row.parent_id) if row.parent_id else None
        mod_counts, child_counts = await self._domaine_counts()
        return self.serialize_domaine(
            row,
            by_id={parent.id: parent} if parent else {},
            espace_code=row.espace.code if row.espace else "",
            modules_count=mod_counts.get(row.id, 0),
            children_count=child_counts.get(row.id, 0),
        )

    async def _resolve_parent(
        self, parent_id: str | None, *, espace_id: UUID, self_id: UUID | None = None
    ) -> UUID | None:
        if not parent_id:
            return None
        parent = await self.get_domaine(UUID(str(parent_id)))
        if parent is None:
            raise ValueError("Domaine parent introuvable")
        if parent.espace_id != espace_id:
            raise ValueError("Le domaine parent doit appartenir au même département")
        if self_id is not None and parent.id == self_id:
            raise ValueError("Un domaine ne peut pas être son propre parent")
        # Deux niveaux : domaine → sous-domaine (pas de sous-sous-domaine).
        if parent.parent_id is not None:
            raise ValueError("Le parent doit être un domaine de premier niveau")
        return parent.id

    @staticmethod
    def _apply_domaine_statut(row: PlateformeDomaine, statut: str) -> None:
        row.statut = statut
        row.is_active = statut != "inactif"

    async def create_domaine(self, payload) -> dict:
        code = normalize_code(payload.code)
        if await self.db.scalar(select(PlateformeDomaine.id).where(PlateformeDomaine.code == code)):
            raise ValueError("Ce code de domaine existe déjà")
        espace = await self._get_espace_or_raise(UUID(str(payload.espace_id)))
        row = PlateformeDomaine(
            espace_id=espace.id,
            parent_id=await self._resolve_parent(payload.parent_id, espace_id=espace.id),
            code=code,
            label=payload.label.strip(),
            description=(payload.description or "").strip(),
            icon=payload.icon,
            status_message=(payload.status_message or "").strip(),
            sort_order=payload.sort_order,
        )
        self._apply_domaine_statut(row, payload.statut)
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ValueError("Ce code de domaine existe déjà") from exc
        return await self.domaine_fiche(row.id)  # type: ignore[return-value]

    async def update_domaine(self, domaine_id: UUID, payload) -> dict:
        row = await self.get_domaine(domaine_id)
        if row is None:
            raise ValueError("Domaine introuvable")
        data = payload.model_dump(exclude_unset=True)
        if data.get("label") is not None:
            row.label = data["label"].strip()
        if data.get("description") is not None:
            row.description = data["description"].strip()
        if data.get("status_message") is not None:
            row.status_message = data["status_message"].strip()
        if data.get("sort_order") is not None:
            row.sort_order = data["sort_order"]
        if "icon" in data:
            row.icon = data["icon"] or None
        if "parent_id" in data:
            if data["parent_id"]:
                _, child_counts = await self._domaine_counts()
                if child_counts.get(row.id, 0) > 0:
                    raise ValueError("Ce domaine a des sous-domaines : il reste au premier niveau")
            row.parent_id = await self._resolve_parent(
                data["parent_id"], espace_id=row.espace_id, self_id=row.id
            )
        if data.get("statut") is not None:
            self._apply_domaine_statut(row, data["statut"])
        await self.db.flush()
        return await self.domaine_fiche(domaine_id)  # type: ignore[return-value]

    async def set_domaine_active(self, domaine_id: UUID, *, active: bool) -> dict:
        row = await self.get_domaine(domaine_id)
        if row is None:
            raise ValueError("Domaine introuvable")
        if active:
            self._apply_domaine_statut(row, "bientot" if row.statut == "inactif" else row.statut)
        else:
            self._apply_domaine_statut(row, "inactif")
        await self.db.flush()
        return await self.domaine_fiche(domaine_id)  # type: ignore[return-value]

    async def delete_domaine(self, domaine_id: UUID) -> None:
        row = await self.get_domaine(domaine_id)
        if row is None:
            raise ValueError("Domaine introuvable")
        mod_counts, child_counts = await self._domaine_counts()
        if child_counts.get(row.id, 0) > 0:
            raise ValueError("Retirez d’abord les sous-domaines de ce domaine")
        if mod_counts.get(row.id, 0) > 0:
            raise ValueError("Des modules sont encore rattachés à ce domaine")
        await self.db.delete(row)
        await self.db.flush()
