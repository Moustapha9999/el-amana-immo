"""Centre de reporting Stock & Fournitures — données réelles, pagination serveur."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.auth import Agence, User
from app.models.mg_stock import (
    MgArticle,
    MgArticleFamille,
    MgInventaire,
    MgInventaireLigne,
    MgStockMouvement,
    MgStockPeriode,
    MgStockSolde,
)
from app.services.mg_stock_periodes import MOIS_FR, compute_theorique, nature_ecart
from app.services.reporting_export import (
    build_styled_pdf,
    build_styled_workbook,
    export_now,
    format_export_datetime,
)

_TZ = ZoneInfo("Africa/Nouakchott")
EXPORT_MAX_ROWS = 20_000
DEPT = "Moyens Généraux — Stock & Fournitures"


@dataclass(frozen=True)
class ReportColumn:
    key: str
    label: str
    kind: str = "text"


@dataclass
class ReportDef:
    key: str
    label: str
    description: str
    icon: str
    columns: list[ReportColumn]
    filters: list[str]
    csv_enabled: bool = True
    group: str = "objets"


_COLS_ETAT = [
    ReportColumn("code", "Code"),
    ReportColumn("designation", "Article"),
    ReportColumn("famille", "Famille"),
    ReportColumn("stock_initial", "Stock initial", "number"),
    ReportColumn("entrees", "Entrées", "number"),
    ReportColumn("sorties", "Sorties", "number"),
    ReportColumn("ajustements", "Ajustements", "number"),
    ReportColumn("stock_theorique", "Stock théorique", "number"),
    ReportColumn("stock_physique", "Stock physique", "number"),
    ReportColumn("ecart", "Écart", "number"),
    ReportColumn("stock_final", "Stock final", "number"),
]

_COLS_MVT = [
    ReportColumn("id", "ID"),
    ReportColumn("date_mouvement", "Date", "date"),
    ReportColumn("reference", "Référence"),
    ReportColumn("article_code", "Code"),
    ReportColumn("article", "Article"),
    ReportColumn("famille", "Famille"),
    ReportColumn("type_mouvement", "Type"),
    ReportColumn("quantite", "Quantité", "number"),
    ReportColumn("agence", "Agence"),
    ReportColumn("departement", "Service"),
    ReportColumn("initiateur", "Utilisateur"),
    ReportColumn("source_type", "Source"),
    ReportColumn("motif", "Motif"),
]

REPORTS: dict[str, ReportDef] = {
    "vue_generale": ReportDef(
        key="vue_generale",
        label="Vue générale",
        description="Synthèse des périodes et volumes de stock.",
        icon="dashboard",
        columns=[
            ReportColumn("libelle", "Période"),
            ReportColumn("statut", "Statut"),
            ReportColumn("articles", "Articles", "number"),
            ReportColumn("stock_initial", "Stock initial", "number"),
            ReportColumn("entrees", "Entrées", "number"),
            ReportColumn("sorties", "Sorties", "number"),
            ReportColumn("ajustements", "Ajustements", "number"),
            ReportColumn("stock_theorique", "Stock théorique", "number"),
        ],
        filters=["annee"],
        group="pilotage",
    ),
    "etat_stock": ReportDef(
        key="etat_stock",
        label="États de stock",
        description="Initial, mouvements, théorique, physique, final par article.",
        icon="inventory_2",
        columns=_COLS_ETAT,
        filters=["annee", "mois", "agence_id", "famille_id", "q"],
        group="objets",
    ),
    "etat_annuel": ReportDef(
        key="etat_annuel",
        label="État annuel",
        description="12 mois : initial, entrées, sorties, ajustements, final.",
        icon="calendar_month",
        columns=[
            ReportColumn("mois", "Mois"),
            ReportColumn("stock_initial", "Stock initial", "number"),
            ReportColumn("entrees", "Entrées", "number"),
            ReportColumn("sorties", "Sorties", "number"),
            ReportColumn("ajustements", "Ajustements", "number"),
            ReportColumn("stock_final", "Stock final", "number"),
        ],
        filters=["annee", "agence_id", "famille_id"],
        group="pilotage",
    ),
    "entrees": ReportDef(
        key="entrees",
        label="Entrées",
        description="Journal des entrées (manuelles, achats, retours).",
        icon="south",
        columns=_COLS_MVT,
        filters=["annee", "mois", "agence_id", "famille_id", "q", "motif"],
        group="objets",
    ),
    "sorties": ReportDef(
        key="sorties",
        label="Sorties",
        description="Journal des sorties et consommation.",
        icon="north",
        columns=_COLS_MVT,
        filters=["annee", "mois", "agence_id", "famille_id", "departement", "q", "motif"],
        group="objets",
    ),
    "consommation": ReportDef(
        key="consommation",
        label="Consommation",
        description="Sorties agrégées par article / famille / service.",
        icon="pie_chart",
        columns=[
            ReportColumn("famille", "Famille"),
            ReportColumn("code", "Code"),
            ReportColumn("designation", "Article"),
            ReportColumn("agence", "Agence"),
            ReportColumn("departement", "Service"),
            ReportColumn("quantite", "Quantité", "number"),
        ],
        filters=["annee", "mois", "agence_id", "famille_id", "departement"],
        group="analyses",
    ),
    "journal": ReportDef(
        key="journal",
        label="Journal des mouvements",
        description="Tous les mouvements historiques.",
        icon="menu_book",
        columns=_COLS_MVT,
        filters=["annee", "mois", "agence_id", "famille_id", "type", "q"],
        group="objets",
    ),
    "inventaires": ReportDef(
        key="inventaires",
        label="Inventaires",
        description="Campagnes et lignes d'inventaire.",
        icon="fact_check",
        columns=[
            ReportColumn("inventaire", "Inventaire"),
            ReportColumn("periode", "Période"),
            ReportColumn("article_code", "Code"),
            ReportColumn("article", "Article"),
            ReportColumn("theorique", "Théorique", "number"),
            ReportColumn("physique", "Physique", "number"),
            ReportColumn("ecart", "Écart", "number"),
            ReportColumn("nature_ecart", "Nature"),
            ReportColumn("statut", "Statut"),
        ],
        filters=["annee", "mois", "agence_id", "statut", "q"],
        group="objets",
    ),
    "ecarts": ReportDef(
        key="ecarts",
        label="Écarts d'inventaire",
        description="Surplus, manquants, conformes.",
        icon="compare_arrows",
        columns=[
            ReportColumn("inventaire", "Inventaire"),
            ReportColumn("article_code", "Code"),
            ReportColumn("article", "Article"),
            ReportColumn("theorique", "Théorique", "number"),
            ReportColumn("physique", "Physique", "number"),
            ReportColumn("ecart", "Écart", "number"),
            ReportColumn("nature_ecart", "Nature"),
        ],
        filters=["annee", "mois", "nature_ecart", "agence_id"],
        group="analyses",
    ),
    "ajustements": ReportDef(
        key="ajustements",
        label="Ajustements",
        description="Ajustements journalisés (dont inventaire).",
        icon="tune",
        columns=_COLS_MVT,
        filters=["annee", "mois", "agence_id", "famille_id", "q"],
        group="objets",
    ),
    "par_agence": ReportDef(
        key="par_agence",
        label="Par agence",
        description="Stock et consommation par agence.",
        icon="store",
        columns=[
            ReportColumn("agence", "Agence"),
            ReportColumn("entrees", "Entrées", "number"),
            ReportColumn("sorties", "Sorties", "number"),
            ReportColumn("ajustements", "Ajustements", "number"),
        ],
        filters=["annee", "mois"],
        group="analyses",
    ),
    "par_direction": ReportDef(
        key="par_direction",
        label="Par direction / service",
        description="Consommation selon le service saisi sur les sorties.",
        icon="account_tree",
        columns=[
            ReportColumn("departement", "Direction / service"),
            ReportColumn("quantite", "Quantité sortie", "number"),
            ReportColumn("nb_mouvements", "Mouvements", "number"),
        ],
        filters=["annee", "mois", "agence_id"],
        group="analyses",
    ),
    "par_service": ReportDef(
        key="par_service",
        label="Par service",
        description="Détail de consommation par service et article.",
        icon="groups",
        columns=[
            ReportColumn("departement", "Service"),
            ReportColumn("code", "Code"),
            ReportColumn("designation", "Article"),
            ReportColumn("famille", "Famille"),
            ReportColumn("quantite", "Quantité", "number"),
        ],
        filters=["annee", "mois", "departement", "agence_id"],
        group="analyses",
    ),
    "par_famille": ReportDef(
        key="par_famille",
        label="Par famille",
        description="Consommation et stock par famille d'articles.",
        icon="category",
        columns=[
            ReportColumn("famille", "Famille"),
            ReportColumn("entrees", "Entrées", "number"),
            ReportColumn("sorties", "Sorties", "number"),
            ReportColumn("ajustements", "Ajustements", "number"),
        ],
        filters=["annee", "mois"],
        group="analyses",
    ),
    "personnalise": ReportDef(
        key="personnalise",
        label="Rapport personnalisé",
        description="Choisir le type, les colonnes, les filtres et exporter.",
        icon="tune",
        columns=[],
        filters=["dataset"],
        group="analyses",
    ),
}


def catalog() -> list[dict]:
    return [
        {
            "key": r.key,
            "label": r.label,
            "description": r.description,
            "icon": r.icon,
            "group": r.group,
            "csv_enabled": r.csv_enabled,
            "filters": r.filters,
            "columns": [{"key": c.key, "label": c.label, "kind": c.kind} for c in r.columns],
        }
        for r in REPORTS.values()
    ]


def _parse_uuid(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _norm_filters(raw: dict[str, Any] | None) -> dict[str, Any]:
    f = dict(raw or {})
    out: dict[str, Any] = {}
    for key in (
        "q",
        "statut",
        "motif",
        "type",
        "departement",
        "nature_ecart",
        "sort_by",
        "sort_dir",
        "date_debut",
        "date_fin",
    ):
        if f.get(key):
            out[key] = str(f[key]).strip()
    out["agence_id"] = _parse_uuid(f.get("agence_id"))
    out["famille_id"] = _parse_uuid(f.get("famille_id"))
    out["annee"] = _int(f.get("annee"))
    out["mois"] = _int(f.get("mois"))
    return out


class MgStockReportingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._agences: dict[uuid.UUID, str] = {}
        self._familles: dict[uuid.UUID, str] = {}

    async def summary(self) -> dict:
        articles = int(
            await self.db.scalar(
                select(func.count()).select_from(MgArticle).where(MgArticle.deleted_at.is_(None))
            )
            or 0
        )
        mvts = int(await self.db.scalar(select(func.count()).select_from(MgStockMouvement)) or 0)
        invs = int(
            await self.db.scalar(
                select(func.count()).select_from(MgInventaire).where(MgInventaire.deleted_at.is_(None))
            )
            or 0
        )
        periodes = int(await self.db.scalar(select(func.count()).select_from(MgStockPeriode)) or 0)
        return {
            "nb_articles": articles,
            "nb_mouvements": mvts,
            "nb_inventaires": invs,
            "nb_periodes": periodes,
        }

    async def preview(
        self,
        report_key: str,
        *,
        filters: dict | None = None,
        page: int = 1,
        size: int = 50,
        columns: list[str] | None = None,
    ) -> dict:
        spec = REPORTS.get(report_key)
        if spec is None or report_key == "personnalise":
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rapport inconnu")
        f = _norm_filters(filters)
        rows, total, totals = await self._fetch(report_key, f, ids=None, limit=None)
        page = max(1, page)
        size = max(1, min(size, 200))
        start = (page - 1) * size
        page_rows = rows[start : start + size]
        cols = spec.columns
        if columns:
            wanted = set(columns)
            cols = [c for c in spec.columns if c.key in wanted] or spec.columns
        return {
            "report_key": report_key,
            "label": spec.label,
            "total": total,
            "page": page,
            "size": size,
            "columns": [{"key": c.key, "label": c.label, "kind": c.kind} for c in cols],
            "rows": [{c.key: r.get(c.key) for c in cols} for r in page_rows],
            "totals": totals,
            "filters_label": self._filters_label(f),
            "empty_message": "Aucune donnée disponible.",
        }

    async def export(
        self,
        report_key: str,
        *,
        fmt: str,
        scope: str = "filtered",
        ids: list[uuid.UUID] | None = None,
        filters: dict | None = None,
        columns: list[str] | None = None,
        user: User | None = None,
    ) -> tuple[bytes, str, str, int]:
        spec = REPORTS.get(report_key)
        if spec is None or report_key == "personnalise":
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rapport inconnu")
        f = _norm_filters(filters)
        limit = EXPORT_MAX_ROWS
        use_ids = ids if scope == "selection" and ids else None
        rows, total, totals = await self._fetch(report_key, f, ids=use_ids, limit=limit)
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aucune donnée à exporter.")
        cols = spec.columns
        if columns:
            wanted = set(columns)
            cols = [c for c in spec.columns if c.key in wanted] or spec.columns
        headers = [c.label for c in cols]
        data_rows = [[r.get(c.key) if r.get(c.key) is not None else "" for c in cols] for r in rows]
        when = export_now()
        subtitle = f"{DEPT} · {self._filters_label(f)} · {format_export_datetime(when)}"
        if user and user.full_name:
            subtitle += f" · {user.full_name}"
        title = f"{spec.label} — Stock & Fournitures"
        stamp = when.strftime("%Y%m%d-%H%M")
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf, delimiter=";")
            writer.writerow(headers)
            writer.writerows(data_rows)
            return (
                buf.getvalue().encode("utf-8-sig"),
                "text/csv",
                f"stock-{report_key}-{stamp}.csv",
                total,
            )
        if fmt == "xlsx":
            content = build_styled_workbook(
                sheet_title="Donnees",
                report_title=title,
                headers=headers,
                rows=data_rows,
                subtitle=subtitle,
                exported_at=when,
            )
            return (
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                f"stock-{report_key}-{stamp}.xlsx",
                total,
            )
        content = build_styled_pdf(
            report_title=title,
            headers=headers,
            rows=data_rows,
            subtitle=subtitle,
            landscape_mode=True,
        )
        return content, "application/pdf", f"stock-{report_key}-{stamp}.pdf", total

    def _filters_label(self, f: dict) -> str:
        bits = []
        if f.get("annee"):
            bits.append(str(f["annee"]))
        if f.get("mois"):
            bits.append(MOIS_FR[f["mois"]] if 1 <= f["mois"] <= 12 else str(f["mois"]))
        if f.get("statut"):
            bits.append(str(f["statut"]))
        if f.get("departement"):
            bits.append(str(f["departement"]))
        return " · ".join(bits) if bits else "Tous filtres"

    async def _agence(self, aid: uuid.UUID | None) -> str:
        if not aid:
            return ""
        if aid not in self._agences:
            row = await self.db.get(Agence, aid)
            self._agences[aid] = row.libelle if row else ""
        return self._agences[aid]

    async def _famille(self, fid: uuid.UUID | None) -> str:
        if not fid:
            return ""
        if fid not in self._familles:
            row = await self.db.get(MgArticleFamille, fid)
            self._familles[fid] = row.libelle if row else ""
        return self._familles[fid]

    async def _fetch(
        self,
        key: str,
        f: dict,
        *,
        ids: list[uuid.UUID] | None,
        limit: int | None,
    ) -> tuple[list[dict], int, dict]:
        handlers = {
            "vue_generale": self._rows_vue,
            "etat_stock": self._rows_etat,
            "etat_annuel": self._rows_annuel,
            "entrees": lambda: self._rows_mvts(f, ids, limit, "ENTREE"),
            "sorties": lambda: self._rows_mvts(f, ids, limit, "SORTIE"),
            "ajustements": lambda: self._rows_mvts(f, ids, limit, "AJUSTEMENT"),
            "journal": lambda: self._rows_mvts(f, ids, limit, f.get("type")),
            "consommation": self._rows_conso,
            "inventaires": self._rows_inventaires,
            "ecarts": self._rows_ecarts,
            "par_agence": self._rows_par_agence,
            "par_direction": self._rows_par_direction,
            "par_service": self._rows_par_service,
            "par_famille": self._rows_par_famille,
        }
        h = handlers.get(key)
        if h is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rapport inconnu")
        if key in {"entrees", "sorties", "ajustements", "journal"}:
            return await h()
        if key in {"vue_generale", "etat_stock", "etat_annuel", "consommation", "inventaires", "ecarts", "par_agence", "par_direction", "par_service", "par_famille"}:
            return await h(f, ids=ids, limit=limit)
        return await h()

    async def _rows_vue(self, f, *, ids, limit):
        stmt = select(MgStockPeriode).order_by(MgStockPeriode.annee, MgStockPeriode.mois)
        if f.get("annee"):
            stmt = stmt.where(MgStockPeriode.annee == f["annee"])
        periodes = list((await self.db.execute(stmt)).scalars().all())
        if ids:
            idset = {i for i in ids}
            periodes = [p for p in periodes if p.id in idset]
        out = []
        for p in periodes:
            row = (
                await self.db.execute(
                    select(
                        func.count(MgStockSolde.id),
                        func.coalesce(func.sum(MgStockSolde.stock_initial), 0),
                        func.coalesce(func.sum(MgStockSolde.entrees), 0),
                        func.coalesce(func.sum(MgStockSolde.sorties), 0),
                        func.coalesce(func.sum(MgStockSolde.ajustements), 0),
                        func.coalesce(func.sum(MgStockSolde.stock_theorique), 0),
                    ).where(MgStockSolde.periode_id == p.id)
                )
            ).one()
            out.append(
                {
                    "id": str(p.id),
                    "libelle": p.libelle,
                    "statut": p.statut,
                    "articles": int(row[0] or 0),
                    "stock_initial": float(row[1] or 0),
                    "entrees": float(row[2] or 0),
                    "sorties": float(row[3] or 0),
                    "ajustements": float(row[4] or 0),
                    "stock_theorique": float(row[5] or 0),
                }
            )
        if limit:
            out = out[:limit]
        return out, len(out), {}

    async def _rows_etat(self, f, *, ids, limit):
        stmt = (
            select(MgStockSolde, MgArticle, MgArticleFamille, MgStockPeriode)
            .join(MgArticle, MgArticle.id == MgStockSolde.article_id)
            .join(MgArticleFamille, MgArticleFamille.id == MgArticle.famille_id)
            .join(MgStockPeriode, MgStockPeriode.id == MgStockSolde.periode_id)
        )
        if f.get("annee"):
            stmt = stmt.where(MgStockPeriode.annee == f["annee"])
        if f.get("mois"):
            stmt = stmt.where(MgStockPeriode.mois == f["mois"])
        if f.get("agence_id"):
            stmt = stmt.where(MgArticle.agence_id == f["agence_id"])
        if f.get("famille_id"):
            stmt = stmt.where(MgArticle.famille_id == f["famille_id"])
        if f.get("q"):
            like = f"%{f['q']}%"
            stmt = stmt.where((MgArticle.code.ilike(like)) | (MgArticle.designation.ilike(like)))
        if ids:
            stmt = stmt.where(MgStockSolde.id.in_(ids))
        rows = (await self.db.execute(stmt.order_by(MgArticle.code))).all()
        out = []
        for solde, art, fam, _per in rows:
            theo = compute_theorique(solde.stock_initial, solde.entrees, solde.sorties, solde.ajustements)
            final = solde.stock_final if solde.stock_final is not None else (
                solde.stock_physique if solde.stock_physique is not None else theo
            )
            out.append(
                {
                    "id": str(solde.id),
                    "code": art.code,
                    "designation": art.designation,
                    "famille": fam.libelle,
                    "stock_initial": float(solde.stock_initial or 0),
                    "entrees": float(solde.entrees or 0),
                    "sorties": float(solde.sorties or 0),
                    "ajustements": float(solde.ajustements or 0),
                    "stock_theorique": float(theo),
                    "stock_physique": float(solde.stock_physique) if solde.stock_physique is not None else None,
                    "ecart": float(solde.ecart) if solde.ecart is not None else None,
                    "stock_final": float(final or 0),
                }
            )
        if limit:
            out = out[:limit]
        return out, len(out), {}

    async def _rows_annuel(self, f, *, ids, limit):
        year = f.get("annee") or date.today().year
        periodes = list(
            (
                await self.db.execute(
                    select(MgStockPeriode)
                    .where(MgStockPeriode.annee == year)
                    .order_by(MgStockPeriode.mois)
                )
            ).scalars().all()
        )
        by_mois = {p.mois: p for p in periodes}
        out = []
        for m in range(1, 13):
            p = by_mois.get(m)
            if p is None:
                out.append(
                    {
                        "id": f"{year}-{m:02d}",
                        "mois": MOIS_FR[m],
                        "stock_initial": 0,
                        "entrees": 0,
                        "sorties": 0,
                        "ajustements": 0,
                        "stock_final": 0,
                    }
                )
                continue
            row = (
                await self.db.execute(
                    select(
                        func.coalesce(func.sum(MgStockSolde.stock_initial), 0),
                        func.coalesce(func.sum(MgStockSolde.entrees), 0),
                        func.coalesce(func.sum(MgStockSolde.sorties), 0),
                        func.coalesce(func.sum(MgStockSolde.ajustements), 0),
                        func.coalesce(func.sum(MgStockSolde.stock_final), 0),
                        func.coalesce(func.sum(MgStockSolde.stock_theorique), 0),
                    ).where(MgStockSolde.periode_id == p.id)
                )
            ).one()
            final = row[4] if row[4] else row[5]
            out.append(
                {
                    "id": str(p.id),
                    "mois": MOIS_FR[m],
                    "stock_initial": float(row[0] or 0),
                    "entrees": float(row[1] or 0),
                    "sorties": float(row[2] or 0),
                    "ajustements": float(row[3] or 0),
                    "stock_final": float(final or 0),
                }
            )
        return out, 12, {}

    async def _rows_mvts(self, f, ids, limit, type_mvt: str | None):
        stmt = (
            select(MgStockMouvement, MgArticle, MgArticleFamille)
            .join(MgArticle, MgArticle.id == MgStockMouvement.article_id)
            .join(MgArticleFamille, MgArticleFamille.id == MgArticle.famille_id)
        )
        if type_mvt:
            stmt = stmt.where(MgStockMouvement.type_mouvement == type_mvt.upper())
        if f.get("annee"):
            stmt = stmt.where(extract("year", MgStockMouvement.date_mouvement) == f["annee"])
        if f.get("mois"):
            stmt = stmt.where(extract("month", MgStockMouvement.date_mouvement) == f["mois"])
        if f.get("agence_id"):
            stmt = stmt.where(MgStockMouvement.agence_id == f["agence_id"])
        if f.get("famille_id"):
            stmt = stmt.where(MgArticle.famille_id == f["famille_id"])
        if f.get("departement"):
            stmt = stmt.where(MgStockMouvement.departement.ilike(f"%{f['departement']}%"))
        if f.get("motif"):
            stmt = stmt.where(MgStockMouvement.motif.ilike(f"%{f['motif']}%"))
        if f.get("q"):
            like = f"%{f['q']}%"
            stmt = stmt.where(
                or_(
                    MgStockMouvement.reference.ilike(like),
                    MgArticle.code.ilike(like),
                    MgArticle.designation.ilike(like),
                )
            )
        if ids:
            stmt = stmt.where(MgStockMouvement.id.in_(ids))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.db.scalar(count_stmt)) or 0)
        stmt = stmt.order_by(MgStockMouvement.date_mouvement.desc())
        if limit:
            stmt = stmt.limit(limit)
        rows = (await self.db.execute(stmt)).all()
        user_ids = {m.initiateur_id for m, *_ in rows if m.initiateur_id}
        users: dict[uuid.UUID, str] = {}
        if user_ids:
            for u in (await self.db.execute(select(User).where(User.id.in_(user_ids)))).scalars():
                users[u.id] = u.full_name
        out = []
        qty = Decimal("0")
        for m, art, fam in rows:
            qty += Decimal(m.quantite or 0)
            out.append(
                {
                    "id": str(m.id),
                    "date_mouvement": m.date_mouvement.strftime("%d/%m/%Y %H:%M")
                    if m.date_mouvement
                    else "",
                    "reference": m.reference,
                    "article_code": art.code,
                    "article": art.designation,
                    "famille": fam.libelle,
                    "type_mouvement": m.type_mouvement,
                    "quantite": float(m.quantite or 0),
                    "agence": await self._agence(m.agence_id),
                    "departement": m.departement or "",
                    "initiateur": users.get(m.initiateur_id, ""),
                    "source_type": m.source_type or "",
                    "motif": m.motif or "",
                }
            )
        return out, total, {"quantite": float(qty)}

    async def _rows_conso(self, f, *, ids, limit):
        stmt = (
            select(
                MgArticleFamille.libelle,
                MgArticle.code,
                MgArticle.designation,
                MgStockMouvement.agence_id,
                MgStockMouvement.departement,
                func.coalesce(func.sum(MgStockMouvement.quantite), 0),
            )
            .join(MgArticle, MgArticle.id == MgStockMouvement.article_id)
            .join(MgArticleFamille, MgArticleFamille.id == MgArticle.famille_id)
            .where(MgStockMouvement.type_mouvement == "SORTIE")
            .group_by(
                MgArticleFamille.libelle,
                MgArticle.code,
                MgArticle.designation,
                MgStockMouvement.agence_id,
                MgStockMouvement.departement,
            )
        )
        if f.get("annee"):
            stmt = stmt.where(extract("year", MgStockMouvement.date_mouvement) == f["annee"])
        if f.get("mois"):
            stmt = stmt.where(extract("month", MgStockMouvement.date_mouvement) == f["mois"])
        if f.get("agence_id"):
            stmt = stmt.where(MgStockMouvement.agence_id == f["agence_id"])
        if f.get("famille_id"):
            stmt = stmt.where(MgArticle.famille_id == f["famille_id"])
        if f.get("departement"):
            stmt = stmt.where(MgStockMouvement.departement.ilike(f"%{f['departement']}%"))
        rows = (await self.db.execute(stmt.order_by(MgArticleFamille.libelle, MgArticle.code))).all()
        out = []
        for fam, code, des, ag, dep, qty in rows:
            out.append(
                {
                    "id": f"{code}-{ag}-{dep}",
                    "famille": fam,
                    "code": code,
                    "designation": des,
                    "agence": await self._agence(ag),
                    "departement": dep or "",
                    "quantite": float(qty or 0),
                }
            )
        if limit:
            out = out[:limit]
        return out, len(out), {"quantite": sum(r["quantite"] for r in out)}

    async def _rows_inventaires(self, f, *, ids, limit):
        stmt = (
            select(MgInventaireLigne, MgInventaire, MgArticle)
            .join(MgInventaire, MgInventaire.id == MgInventaireLigne.inventaire_id)
            .join(MgArticle, MgArticle.id == MgInventaireLigne.article_id)
            .where(MgInventaire.deleted_at.is_(None))
        )
        if f.get("statut"):
            stmt = stmt.where(MgInventaire.statut == f["statut"].upper())
        if f.get("agence_id"):
            stmt = stmt.where(MgInventaire.agence_id == f["agence_id"])
        if f.get("annee"):
            stmt = stmt.where(extract("year", MgInventaire.date_debut) == f["annee"])
        if f.get("mois"):
            stmt = stmt.where(extract("month", MgInventaire.date_debut) == f["mois"])
        if f.get("q"):
            like = f"%{f['q']}%"
            stmt = stmt.where(
                or_(MgInventaire.reference.ilike(like), MgArticle.code.ilike(like))
            )
        rows = (await self.db.execute(stmt.order_by(MgInventaire.date_debut.desc()))).all()
        out = []
        for lig, inv, art in rows:
            out.append(
                {
                    "id": str(lig.id),
                    "inventaire": inv.reference,
                    "periode": inv.date_debut.strftime("%m/%Y") if inv.date_debut else "",
                    "article_code": art.code,
                    "article": art.designation,
                    "theorique": float(lig.stock_theorique or 0),
                    "physique": float(lig.stock_physique) if lig.stock_physique is not None else None,
                    "ecart": float(lig.ecart) if lig.ecart is not None else None,
                    "nature_ecart": lig.nature_ecart or nature_ecart(lig.ecart),
                    "statut": inv.statut,
                }
            )
        if limit:
            out = out[:limit]
        return out, len(out), {}

    async def _rows_ecarts(self, f, *, ids, limit):
        rows, total, totals = await self._rows_inventaires(f, ids=ids, limit=None)
        nature = (f.get("nature_ecart") or "").upper()
        if nature:
            rows = [r for r in rows if (r.get("nature_ecart") or "") == nature]
        else:
            rows = [r for r in rows if r.get("nature_ecart") in {"SURPLUS", "MANQUANT", "CONFORME"}]
        if limit:
            rows = rows[:limit]
        return rows, len(rows), totals

    async def _rows_par_agence(self, f, *, ids, limit):
        return await self._agg_mvt(f, group="agence")

    async def _rows_par_famille(self, f, *, ids, limit):
        return await self._agg_mvt(f, group="famille")

    async def _agg_mvt(self, f, *, group: str):
        if group == "agence":
            stmt = (
                select(
                    Agence.libelle,
                    MgStockMouvement.type_mouvement,
                    func.coalesce(func.sum(MgStockMouvement.quantite), 0),
                )
                .join(Agence, Agence.id == MgStockMouvement.agence_id)
                .group_by(Agence.libelle, MgStockMouvement.type_mouvement)
            )
        else:
            stmt = (
                select(
                    MgArticleFamille.libelle,
                    MgStockMouvement.type_mouvement,
                    func.coalesce(func.sum(MgStockMouvement.quantite), 0),
                )
                .join(MgArticle, MgArticle.id == MgStockMouvement.article_id)
                .join(MgArticleFamille, MgArticleFamille.id == MgArticle.famille_id)
                .group_by(MgArticleFamille.libelle, MgStockMouvement.type_mouvement)
            )
        if f.get("annee"):
            stmt = stmt.where(extract("year", MgStockMouvement.date_mouvement) == f["annee"])
        if f.get("mois"):
            stmt = stmt.where(extract("month", MgStockMouvement.date_mouvement) == f["mois"])
        rows = (await self.db.execute(stmt)).all()
        key_name = "agence" if group == "agence" else "famille"
        bucket: dict[str, dict] = {}
        for label, typ, qty in rows:
            rec = bucket.setdefault(
                label,
                {"id": label, key_name: label, "entrees": 0.0, "sorties": 0.0, "ajustements": 0.0},
            )
            q = float(qty or 0)
            if typ == "ENTREE":
                rec["entrees"] += q
            elif typ == "SORTIE":
                rec["sorties"] += q
            elif typ == "AJUSTEMENT":
                rec["ajustements"] += q
        out = list(bucket.values())
        return out, len(out), {}

    async def _rows_par_direction(self, f, *, ids, limit):
        stmt = (
            select(
                func.coalesce(MgStockMouvement.departement, "—"),
                func.coalesce(func.sum(MgStockMouvement.quantite), 0),
                func.count(MgStockMouvement.id),
            )
            .where(MgStockMouvement.type_mouvement == "SORTIE")
            .group_by(func.coalesce(MgStockMouvement.departement, "—"))
        )
        if f.get("annee"):
            stmt = stmt.where(extract("year", MgStockMouvement.date_mouvement) == f["annee"])
        if f.get("mois"):
            stmt = stmt.where(extract("month", MgStockMouvement.date_mouvement) == f["mois"])
        if f.get("agence_id"):
            stmt = stmt.where(MgStockMouvement.agence_id == f["agence_id"])
        rows = (await self.db.execute(stmt)).all()
        out = [
            {
                "id": dep,
                "departement": dep,
                "quantite": float(qty or 0),
                "nb_mouvements": int(nb or 0),
            }
            for dep, qty, nb in rows
        ]
        return out, len(out), {}

    async def _rows_par_service(self, f, *, ids, limit):
        return await self._rows_conso(f, ids=ids, limit=limit)
