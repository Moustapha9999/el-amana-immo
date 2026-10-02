"""Inventaire mensuel Stock & Fournitures : campagne, comptage, écarts, validation, ajustements.

Une campagne est une photo du stock théorique d'un périmètre (agence / famille) à une date.
Le théorique est figé à la création ; le stock système n'est modifié que par les mouvements
d'AJUSTEMENT générés après validation (source_type = "inventaire", un par article).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Request, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import AppError
from app.models.audit import AuditLog
from app.models.auth import Agence, User
from app.models.mg_stock import (
    MgArticle,
    MgArticleFamille,
    MgInventaire,
    MgInventaireLigne,
    MgStockMouvement,
    MgStockPeriode,
)
from app.schemas.mg_stock import (
    InventaireCreate,
    InventaireLigneAjout,
    InventaireLigneIn,
    InventaireLigneSaisie,
    InventaireUpdate,
)
from app.schemas.nombres import as_qty
from app.services.mg_stock_events import audit_stock
from app.services.mg_stock_periodes import MOIS_FR, MgStockPeriodeService, nature_ecart
from app.services.permission_service import user_has_permission_codes

STATUTS = ("BROUILLON", "EN_COURS", "A_CONTROLER", "VALIDE", "AJUSTE", "ARCHIVE", "ANNULE")
SAISIE_OUVERTE = frozenset({"BROUILLON", "EN_COURS"})
VERROUILLES = frozenset({"VALIDE", "AJUSTE", "ARCHIVE", "ANNULE"})
ANNULABLES = frozenset({"BROUILLON", "EN_COURS", "A_CONTROLER", "VALIDE"})

PERM_SAISIE = "mg.stock.inventory"
PERM_VALIDATION = "mg.stock.inventory.validate"
PERM_AJUSTEMENT = "mg.stock.inventory.adjust"
# Pas de suffixe « .admin » : il couvrirait toutes les permissions mg.* (permission_service).
PERM_GESTION = "mg.stock.inventory.manage"

MSG_VERROU = "Cet inventaire est clôturé. Les données ne peuvent plus être modifiées."

LIGNE_TRIS = {
    "code": MgArticle.code,
    "designation": MgArticle.designation,
    "famille": MgArticleFamille.libelle,
    "theorique": MgInventaireLigne.stock_theorique,
    "physique": MgInventaireLigne.stock_physique,
    "ecart": MgInventaireLigne.ecart,
    "ecart_abs": func.abs(MgInventaireLigne.ecart),
    "statut": MgInventaireLigne.statut_comptage,
    "maj": MgInventaireLigne.updated_at,
    "ordre": MgInventaireLigne.sort_order,
}


def fin_de_journee(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def statut_ligne(statut_comptage: str, ecart: Decimal | None) -> str:
    if statut_comptage == "EXCLU":
        return "EXCLU"
    if statut_comptage != "COMPTE" or ecart is None:
        return "NON_COMPTE"
    if ecart == 0:
        return "CONFORME"
    return "ECART_NEGATIF" if ecart < 0 else "ECART_POSITIF"


def ecart_pourcentage(theorique: Decimal | None, ecart: Decimal | None) -> float | None:
    """Écart rapporté au théorique ; indéfini si théorique nul et physique non nul."""
    if ecart is None:
        return None
    theo = Decimal(theorique or 0)
    if theo == 0:
        return 0.0 if ecart == 0 else None
    return float((Decimal(ecart) * 100 / theo).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def periode_label(annee: int | None, mois: int | None) -> str | None:
    if not annee or not mois:
        return None
    return f"{MOIS_FR[mois]} {annee}"


def _stats_columns():
    lg = MgInventaireLigne
    compte = lg.statut_comptage == "COMPTE"
    return (
        func.count(lg.id).label("total"),
        func.count(lg.id).filter(lg.statut_comptage != "EXCLU").label("a_compter"),
        func.count(lg.id).filter(compte).label("comptes"),
        func.count(lg.id).filter(lg.statut_comptage == "NON_COMPTE").label("non_comptes"),
        func.count(lg.id).filter(lg.statut_comptage == "EXCLU").label("exclus"),
        func.count(lg.id).filter(compte, lg.ecart == 0).label("sans_ecart"),
        func.count(lg.id).filter(compte, lg.ecart < 0).label("ecarts_negatifs"),
        func.count(lg.id).filter(compte, lg.ecart > 0).label("ecarts_positifs"),
        func.coalesce(func.sum(lg.stock_theorique).filter(compte), 0).label("total_theorique"),
        func.coalesce(func.sum(lg.stock_physique).filter(compte), 0).label("total_physique"),
    )


def stats_from_row(row) -> dict:
    if row is None:
        return {
            "total": 0, "a_compter": 0, "comptes": 0, "non_comptes": 0, "exclus": 0,
            "sans_ecart": 0, "ecarts_negatifs": 0, "ecarts_positifs": 0,
            "total_theorique": 0, "total_physique": 0, "ecart_net": 0, "progression": 0.0,
        }
    a_compter = int(row.a_compter or 0)
    comptes = int(row.comptes or 0)
    theo = Decimal(row.total_theorique or 0)
    phys = Decimal(row.total_physique or 0)
    return {
        "total": int(row.total or 0),
        "a_compter": a_compter,
        "comptes": comptes,
        "non_comptes": int(row.non_comptes or 0),
        "exclus": int(row.exclus or 0),
        "sans_ecart": int(row.sans_ecart or 0),
        "ecarts_negatifs": int(row.ecarts_negatifs or 0),
        "ecarts_positifs": int(row.ecarts_positifs or 0),
        "total_theorique": theo,
        "total_physique": phys,
        "ecart_net": phys - theo,
        "progression": round(100.0 * comptes / a_compter, 1) if a_compter else 0.0,
    }


class MgInventaireService:
    def __init__(self, db: AsyncSession, user: User | None = None, perms: set[str] | None = None):
        self.db = db
        self.user = user
        self.perms = perms or set()

    # ------------------------------------------------------------------ droits

    def peut(self, *codes: str) -> bool:
        return user_has_permission_codes(self.perms, *codes)

    def exiger(self, *codes: str, message: str | None = None) -> None:
        if not self.peut(*codes):
            raise AppError(
                message or f"Permission requise : {' ou '.join(codes)}.",
                status.HTTP_403_FORBIDDEN,
                code="PERMISSION_REFUSEE",
            )

    @staticmethod
    def verrou(inv: MgInventaire) -> None:
        if inv.statut in VERROUILLES:
            raise AppError(MSG_VERROU, status.HTTP_409_CONFLICT, code="INVENTAIRE_VERROUILLE")

    def exiger_saisie(self, inv: MgInventaire) -> None:
        self.verrou(inv)
        if inv.statut in SAISIE_OUVERTE:
            self.exiger(PERM_SAISIE, PERM_VALIDATION)
        else:
            self.exiger(
                PERM_VALIDATION,
                PERM_GESTION,
                message="Inventaire à contrôler : seuls les contrôleurs peuvent encore modifier les comptages.",
            )

    async def _audit(self, action: str, entity: str, entity_id, *, request: Request | None = None,
                     before: dict | None = None, after: dict | None = None) -> None:
        await audit_stock(self.db, self.user, action, entity, entity_id, request=request, before=before, after=after)

    # ------------------------------------------------------------------ lecture

    async def get(self, inventaire_id: uuid.UUID, *, for_update: bool = False) -> MgInventaire:
        stmt = select(MgInventaire).where(MgInventaire.id == inventaire_id, MgInventaire.deleted_at.is_(None))
        if for_update:
            stmt = stmt.with_for_update()
        inv = await self.db.scalar(stmt)
        if inv is None:
            raise AppError("Inventaire introuvable", status.HTTP_404_NOT_FOUND, code="INVENTAIRE_INTROUVABLE")
        return inv

    async def stats(self, inventaire_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
        if not inventaire_ids:
            return {}
        rows = (
            await self.db.execute(
                select(MgInventaireLigne.inventaire_id, *_stats_columns())
                .where(MgInventaireLigne.inventaire_id.in_(inventaire_ids))
                .group_by(MgInventaireLigne.inventaire_id)
            )
        ).all()
        found = {row.inventaire_id: stats_from_row(row) for row in rows}
        return {i: found.get(i, stats_from_row(None)) for i in inventaire_ids}

    async def mouvements_depuis(self, inv: MgInventaire) -> int:
        """Mouvements saisis sur le périmètre après la photo (hors ajustements de cet inventaire)."""
        if inv.statut in {"AJUSTE", "ARCHIVE", "ANNULE"}:
            return 0
        snapshot = inv.snapshot_at or inv.created_at
        borne = fin_de_journee(inv.date_debut)
        article_ids = select(MgInventaireLigne.article_id).where(MgInventaireLigne.inventaire_id == inv.id)
        return int(
            await self.db.scalar(
                select(func.count())
                .select_from(MgStockMouvement)
                .where(
                    MgStockMouvement.article_id.in_(article_ids),
                    or_(MgStockMouvement.date_mouvement > borne, MgStockMouvement.created_at > snapshot),
                    or_(
                        MgStockMouvement.source_type.is_(None),
                        MgStockMouvement.source_type != "inventaire",
                        MgStockMouvement.source_id != inv.id,
                    ),
                )
            )
            or 0
        )

    async def nb_ajustements(self, inventaire_id: uuid.UUID) -> int:
        return int(
            await self.db.scalar(
                select(func.count())
                .select_from(MgStockMouvement)
                .where(
                    MgStockMouvement.source_type == "inventaire",
                    MgStockMouvement.source_id == inventaire_id,
                    MgStockMouvement.type_mouvement == "AJUSTEMENT",
                )
            )
            or 0
        )

    async def _noms(self, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = (await self.db.execute(select(User.id, User.full_name, User.email).where(User.id.in_(ids)))).all()
        return {r.id: (r.full_name or r.email) for r in rows}

    async def serialize(self, inv: MgInventaire, *, stats: dict | None = None, detail: bool = True) -> dict:
        state = sa_inspect(inv, raiseerr=False)
        if state is not None and state.expired_attributes:
            await self.db.refresh(inv)
        noms = await self._noms({inv.created_by, inv.valide_by, inv.ajustements_by, inv.responsable_id})
        agence = await self.db.get(Agence, inv.agence_id) if inv.agence_id else None
        famille = await self.db.get(MgArticleFamille, inv.famille_id) if inv.famille_id else None
        if stats is None:
            stats = (await self.stats([inv.id]))[inv.id]
        return {
            "id": inv.id,
            "reference": inv.reference,
            "libelle": inv.libelle,
            "date_debut": inv.date_debut,
            "date_fin": inv.date_fin,
            "annee": inv.annee,
            "mois": inv.mois,
            "periode_libelle": periode_label(inv.annee, inv.mois),
            "agence_id": inv.agence_id,
            "agence_libelle": agence.libelle if agence else None,
            "famille_id": inv.famille_id,
            "famille_libelle": famille.libelle if famille else None,
            "responsable_id": inv.responsable_id,
            "responsable_nom": inv.responsable_nom or noms.get(inv.responsable_id),
            "statut": inv.statut,
            "observation": inv.observation,
            "source": inv.source or "MANUEL",
            "import_meta": inv.import_meta if detail else None,
            "periode_id": inv.periode_id,
            "snapshot_at": inv.snapshot_at,
            "created_at": inv.created_at,
            "created_by": inv.created_by,
            "created_by_nom": noms.get(inv.created_by),
            "updated_at": inv.updated_at,
            "valide_at": inv.valide_at,
            "valide_by_nom": noms.get(inv.valide_by),
            "validation_forcee": bool(inv.validation_forcee),
            "ajustements_at": inv.ajustements_at,
            "ajustements_by_nom": noms.get(inv.ajustements_by),
            "cloture_at": inv.cloture_at,
            "annule_at": inv.annule_at,
            "motif_annulation": inv.motif_annulation,
            "stats": stats,
            "mouvements_depuis": await self.mouvements_depuis(inv) if detail else 0,
            "nb_ajustements": await self.nb_ajustements(inv.id) if detail else 0,
        }

    def _filtres_liste(self, *, q, annee, mois, statut, agence_id, responsable):
        filters = [MgInventaire.deleted_at.is_(None)]
        if q:
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    MgInventaire.reference.ilike(like),
                    MgInventaire.libelle.ilike(like),
                    MgInventaire.responsable_nom.ilike(like),
                    MgInventaire.observation.ilike(like),
                )
            )
        if annee:
            filters.append(MgInventaire.annee == annee)
        if mois:
            filters.append(MgInventaire.mois == mois)
        if statut:
            filters.append(MgInventaire.statut.in_([s.strip().upper() for s in statut.split(",") if s.strip()]))
        if agence_id:
            filters.append(MgInventaire.agence_id == agence_id)
        if responsable:
            filters.append(MgInventaire.responsable_nom.ilike(f"%{responsable.strip()}%"))
        return filters

    async def lister(
        self,
        *,
        q: str | None = None,
        annee: int | None = None,
        mois: int | None = None,
        statut: str | None = None,
        agence_id: uuid.UUID | None = None,
        responsable: str | None = None,
        ecarts: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        filters = self._filtres_liste(
            q=q, annee=annee, mois=mois, statut=statut, agence_id=agence_id, responsable=responsable
        )
        lg = MgInventaireLigne
        nb_ecarts = (
            select(func.count(lg.id))
            .where(lg.inventaire_id == MgInventaire.id, lg.statut_comptage == "COMPTE", lg.ecart != 0)
            .correlate(MgInventaire)
            .scalar_subquery()
        )
        if ecarts == "avec":
            filters.append(nb_ecarts > 0)
        elif ecarts == "sans":
            filters.append(nb_ecarts == 0)
        total = int(await self.db.scalar(select(func.count()).select_from(MgInventaire).where(*filters)) or 0)
        rows = list(
            (
                await self.db.execute(
                    select(MgInventaire)
                    .where(*filters)
                    .order_by(
                        MgInventaire.annee.desc().nulls_last(),
                        MgInventaire.mois.desc().nulls_last(),
                        MgInventaire.date_debut.desc(),
                        MgInventaire.created_at.desc(),
                    )
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).scalars().all()
        )
        stats = await self.stats([r.id for r in rows])
        items = [await self.serialize(r, stats=stats[r.id], detail=False) for r in rows]
        return {"items": items, "total": total, "page": page, "size": size}

    async def synthese(self) -> dict:
        base = [MgInventaire.deleted_at.is_(None), MgInventaire.statut != "ANNULE"]
        dernier = await self.db.scalar(
            select(MgInventaire)
            .where(*base)
            .order_by(MgInventaire.date_debut.desc(), MgInventaire.created_at.desc())
            .limit(1)
        )
        en_cours = await self.db.scalar(
            select(MgInventaire)
            .where(*base, MgInventaire.statut.in_(["BROUILLON", "EN_COURS", "A_CONTROLER"]))
            .order_by(MgInventaire.date_debut.desc())
            .limit(1)
        )
        counts = dict(
            (
                await self.db.execute(
                    select(MgInventaire.statut, func.count()).where(*base).group_by(MgInventaire.statut)
                )
            ).all()
        )
        return {
            "dernier": await self.serialize(dernier, detail=False) if dernier else None,
            "en_cours": await self.serialize(en_cours, detail=False) if en_cours else None,
            "nb_en_cours": int(counts.get("EN_COURS", 0)) + int(counts.get("BROUILLON", 0)),
            "nb_a_controler": int(counts.get("A_CONTROLER", 0)),
            "nb_total": sum(int(v) for v in counts.values()),
        }

    def _lignes_stmt(self, inventaire_id: uuid.UUID):
        compteur = aliased(User)
        return (
            select(MgInventaireLigne, MgArticle, MgArticleFamille, compteur.full_name, compteur.email)
            .join(MgArticle, MgArticle.id == MgInventaireLigne.article_id)
            .outerjoin(MgArticleFamille, MgArticleFamille.id == MgArticle.famille_id)
            .outerjoin(compteur, compteur.id == MgInventaireLigne.compte_par)
            .where(MgInventaireLigne.inventaire_id == inventaire_id)
        )

    @staticmethod
    def serialize_ligne(ligne: MgInventaireLigne, article: MgArticle | None, famille: MgArticleFamille | None,
                        compteur_nom: str | None = None) -> dict:
        ecart = ligne.ecart if ligne.statut_comptage == "COMPTE" else None
        return {
            "id": ligne.id,
            "article_id": ligne.article_id,
            "stock_theorique": ligne.stock_theorique,
            "stock_physique": ligne.stock_physique,
            "ecart": ecart,
            "ecart_absolu": abs(ecart) if ecart is not None else None,
            "ecart_pourcentage": ecart_pourcentage(ligne.stock_theorique, ecart),
            "nature_ecart": ligne.nature_ecart,
            "observation": ligne.observation,
            "sort_order": ligne.sort_order,
            "statut_comptage": ligne.statut_comptage,
            "statut_ligne": statut_ligne(ligne.statut_comptage, ecart),
            "compte_par": ligne.compte_par,
            "compte_par_nom": compteur_nom,
            "compte_at": ligne.compte_at,
            "stock_theorique_source": ligne.stock_theorique_source,
            "ajout_manuel": bool(ligne.ajout_manuel),
            "updated_at": ligne.updated_at,
            "article_code": article.code if article else None,
            "article_reference": article.reference if article else None,
            "article_designation": article.designation if article else None,
            "famille_id": article.famille_id if article else None,
            "famille_libelle": famille.libelle if famille else None,
            "unite": article.uom if article else None,
            "emplacement": article.emplacement if article else None,
        }

    async def lignes(
        self,
        inventaire_id: uuid.UUID,
        *,
        q: str | None = None,
        famille_id: uuid.UUID | None = None,
        filtre: str | None = None,
        tri: str = "ordre",
        sens: str = "asc",
        page: int = 1,
        size: int = 50,
    ) -> dict:
        await self.get(inventaire_id)
        stmt = self._lignes_stmt(inventaire_id)
        lg = MgInventaireLigne
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(MgArticle.code.ilike(like), MgArticle.designation.ilike(like), MgArticle.reference.ilike(like))
            )
        if famille_id:
            stmt = stmt.where(MgArticle.famille_id == famille_id)
        compte = lg.statut_comptage == "COMPTE"
        filtres = {
            "non_compte": lg.statut_comptage == "NON_COMPTE",
            "compte": compte,
            "conforme": and_(compte, lg.ecart == 0),
            "negatif": and_(compte, lg.ecart < 0),
            "positif": and_(compte, lg.ecart > 0),
            "ecart": and_(compte, lg.ecart != 0),
            "exclu": lg.statut_comptage == "EXCLU",
        }
        if filtre in filtres:
            stmt = stmt.where(filtres[filtre])
        total = int(await self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        col = LIGNE_TRIS.get(tri, LIGNE_TRIS["ordre"])
        order = col.desc().nulls_last() if sens == "desc" else col.asc().nulls_last()
        rows = (
            await self.db.execute(stmt.order_by(order, MgArticle.code).offset((page - 1) * size).limit(size))
        ).all()
        items = [self.serialize_ligne(lg_, art, fam, nom or mail) for lg_, art, fam, nom, mail in rows]
        return {"items": items, "total": total, "page": page, "size": size}

    async def ligne(self, inventaire_id: uuid.UUID, ligne_id: uuid.UUID) -> dict:
        row = (
            await self.db.execute(self._lignes_stmt(inventaire_id).where(MgInventaireLigne.id == ligne_id))
        ).first()
        if row is None:
            raise AppError("Ligne d'inventaire introuvable", status.HTTP_404_NOT_FOUND, code="LIGNE_INTROUVABLE")
        lg_, art, fam, nom, mail = row
        return self.serialize_ligne(lg_, art, fam, nom or mail)

    async def historique(self, *, inventaire_id: uuid.UUID, ligne_id: uuid.UUID | None = None,
                         limit: int = 200) -> list[dict]:
        if ligne_id is not None:
            cond = and_(AuditLog.entity == "mg_inventaire_ligne", AuditLog.entity_id == str(ligne_id))
        else:
            cond = or_(
                and_(AuditLog.entity == "mg_inventaire", AuditLog.entity_id == str(inventaire_id)),
                and_(
                    AuditLog.entity == "mg_inventaire_ligne",
                    AuditLog.after_data["inventaire_id"].astext == str(inventaire_id),
                ),
            )
        rows = (
            await self.db.execute(
                select(AuditLog, User.full_name, User.email)
                .outerjoin(User, User.id == AuditLog.user_id)
                .where(cond)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [
            {
                "id": log.id,
                "created_at": log.created_at,
                "action": log.action,
                "entity": log.entity,
                "user_nom": nom or mail,
                "before": log.before_data,
                "after": log.after_data,
            }
            for log, nom, mail in rows
        ]

    # ------------------------------------------------------------------ photo du stock

    async def articles_perimetre(
        self, *, agence_id: uuid.UUID | None, famille_id: uuid.UUID | None, fin: datetime | None = None
    ) -> list[MgArticle]:
        filters = [
            MgArticle.is_active.is_(True),
            MgArticle.deleted_at.is_(None),
            MgArticle.stockable.is_(True),
        ]
        if agence_id:
            filters.append(or_(MgArticle.agence_id == agence_id, MgArticle.agence_id.is_(None)))
        if famille_id:
            filters.append(MgArticle.famille_id == famille_id)
        if fin is not None:
            filters.append(MgArticle.created_at <= fin)
        stmt = select(MgArticle).where(*filters).order_by(MgArticle.code).limit(10000)
        return list((await self.db.execute(stmt)).scalars().all())

    async def stock_a_date(self, articles: list[MgArticle], fin: datetime) -> dict[uuid.UUID, Decimal]:
        """Stock système à ``fin`` = stock actuel − effet des mouvements datés après ``fin``."""
        if not articles:
            return {}
        mv = MgStockMouvement
        effet = case(
            (mv.type_mouvement == "ENTREE", mv.quantite),
            (mv.type_mouvement == "SORTIE", -mv.quantite),
            (mv.type_mouvement == "AJUSTEMENT", mv.quantite),
            else_=0,
        )
        rows = (
            await self.db.execute(
                select(mv.article_id, func.coalesce(func.sum(effet), 0))
                .where(mv.article_id.in_([a.id for a in articles]), mv.date_mouvement > fin)
                .group_by(mv.article_id)
            )
        ).all()
        apres = {aid: Decimal(v or 0) for aid, v in rows}
        return {a.id: Decimal(a.stock_actuel or 0) - apres.get(a.id, Decimal("0")) for a in articles}

    async def _photo(self, inv: MgInventaire, articles: list[MgArticle], *, start: int = 0,
                     manuel: bool = False) -> list[MgInventaireLigne]:
        stocks = await self.stock_a_date(articles, fin_de_journee(inv.date_debut))
        lignes: list[MgInventaireLigne] = []
        for i, article in enumerate(articles):
            theo = stocks.get(article.id, Decimal("0"))
            observation = None
            if theo < 0:
                observation = f"Stock système calculé négatif ({as_qty(theo)}) à la date : théorique ramené à 0."
                theo = Decimal("0")
            ligne = MgInventaireLigne(
                inventaire_id=inv.id,
                article_id=article.id,
                stock_theorique=theo,
                stock_physique=None,
                ecart=None,
                nature_ecart=None,
                observation=observation,
                statut_comptage="NON_COMPTE",
                ajout_manuel=manuel,
                sort_order=start + i,
            )
            self.db.add(ligne)
            lignes.append(ligne)
        inv.snapshot_at = datetime.now(timezone.utc)
        return lignes

    # ------------------------------------------------------------------ création

    async def _next_reference(self, annee: int, mois: int) -> str:
        prefix = f"INV-{annee}-{mois:02d}-"
        existing = (
            await self.db.execute(select(MgInventaire.reference).where(MgInventaire.reference.like(f"{prefix}%")))
        ).scalars().all()
        numeros = [int(r[len(prefix):]) for r in existing if r[len(prefix):].isdigit()]
        return f"{prefix}{(max(numeros) if numeros else 0) + 1:03d}"

    async def _assert_unique(self, *, annee: int, mois: int, agence_id, famille_id, exclude_id=None) -> None:
        stmt = select(MgInventaire).where(
            MgInventaire.deleted_at.is_(None),
            MgInventaire.statut != "ANNULE",
            MgInventaire.annee == annee,
            MgInventaire.mois == mois,
            MgInventaire.agence_id.is_(None) if agence_id is None else MgInventaire.agence_id == agence_id,
            MgInventaire.famille_id.is_(None) if famille_id is None else MgInventaire.famille_id == famille_id,
        )
        if exclude_id:
            stmt = stmt.where(MgInventaire.id != exclude_id)
        doublon = await self.db.scalar(stmt.limit(1))
        if doublon is not None:
            raise AppError(
                f"Un inventaire existe déjà pour ce périmètre et cette période : {doublon.reference} "
                f"({periode_label(annee, mois)}). Annulez-le avant d'en créer un autre.",
                status.HTTP_409_CONFLICT,
                code="INVENTAIRE_DOUBLON",
            )

    async def _resolve_periode(self, annee: int, mois: int) -> MgStockPeriode | None:
        periode = await self.db.scalar(
            select(MgStockPeriode).where(MgStockPeriode.annee == annee, MgStockPeriode.mois == mois)
        )
        if periode is not None and periode.statut == "CLOTUREE":
            raise AppError(
                f"Période {periode.libelle} clôturée : inventaire interdit (rouvrir la période d'abord).",
                status.HTTP_409_CONFLICT,
                code="PERIODE_CLOTUREE",
            )
        return periode

    async def _responsable(self, responsable_id, responsable_nom) -> tuple[uuid.UUID | None, str | None]:
        if responsable_id:
            user = await self.db.get(User, responsable_id)
            if user is None:
                raise AppError("Responsable introuvable", status.HTTP_404_NOT_FOUND)
            return user.id, (responsable_nom or user.full_name or user.email)
        if responsable_nom and responsable_nom.strip():
            return None, responsable_nom.strip()
        if self.user is not None:
            return self.user.id, (self.user.full_name or self.user.email)
        return None, None

    async def creer(self, data: InventaireCreate, *, request: Request | None = None,
                    source: str = "MANUEL", commit: bool = True) -> MgInventaire:
        self.exiger(PERM_SAISIE)
        jour = data.date_debut or date.today()
        annee = data.annee or jour.year
        mois = data.mois or jour.month
        if (jour.year, jour.month) != (annee, mois):
            raise AppError(
                f"La date d'inventaire ({jour.strftime('%d/%m/%Y')}) doit appartenir à la période "
                f"{periode_label(annee, mois)}.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="INVENTAIRE_DATE_PERIODE",
            )
        if jour > date.today():
            raise AppError("La date d'inventaire ne peut pas être dans le futur.", status.HTTP_422_UNPROCESSABLE_ENTITY)
        await self._assert_unique(annee=annee, mois=mois, agence_id=data.agence_id, famille_id=data.famille_id)
        periode = await self._resolve_periode(annee, mois)
        responsable_id, responsable_nom = await self._responsable(data.responsable_id, data.responsable_nom)

        libelle = (data.libelle or "").strip() or f"Inventaire {periode_label(annee, mois)}"
        inv = MgInventaire(
            reference=await self._next_reference(annee, mois),
            libelle=libelle,
            date_debut=jour,
            annee=annee,
            mois=mois,
            agence_id=data.agence_id,
            famille_id=data.famille_id,
            responsable_id=responsable_id,
            responsable_nom=responsable_nom,
            statut="BROUILLON",
            source=source,
            observation=(data.observation or "").strip() or None,
            created_by=self.user.id if self.user else None,
            updated_by=self.user.id if self.user else None,
            periode_id=periode.id if periode else None,
        )
        self.db.add(inv)
        await self.db.flush()

        fin = fin_de_journee(jour)
        articles = await self.articles_perimetre(agence_id=data.agence_id, famille_id=data.famille_id, fin=fin)
        if not articles:
            raise AppError(
                "Aucun article stockable actif dans ce périmètre à cette date : la campagne n'aurait aucune ligne.",
                code="INVENTAIRE_VIDE",
            )
        await self._photo(inv, articles)
        await self.db.flush()
        await self._audit(
            "create", "mg_inventaire", inv.id, request=request,
            after={
                "reference": inv.reference,
                "periode": periode_label(annee, mois),
                "date": jour.isoformat(),
                "lignes": len(articles),
                "source": source,
            },
        )
        if commit:
            await self.db.commit()
        return inv

    # ------------------------------------------------------------------ modification

    async def modifier(self, inventaire_id: uuid.UUID, data: InventaireUpdate, *,
                       request: Request | None = None) -> MgInventaire:
        inv = await self.get(inventaire_id, for_update=True)
        self.verrou(inv)
        if inv.statut == "A_CONTROLER":
            self.exiger(PERM_VALIDATION, PERM_GESTION)
        else:
            self.exiger(PERM_SAISIE)
        fields = data.model_dump(exclude_unset=True)
        before = {k: str(getattr(inv, k)) if getattr(inv, k) is not None else None for k in fields if hasattr(inv, k)}
        perimetre = {"date_debut", "agence_id", "famille_id"}
        change_perimetre = any(
            k in fields and fields[k] != getattr(inv, k) for k in perimetre
        )
        if change_perimetre:
            if inv.statut != "BROUILLON":
                raise AppError(
                    "La date et le périmètre ne sont modifiables qu'au statut Brouillon (avant tout comptage).",
                    status.HTTP_409_CONFLICT,
                    code="INVENTAIRE_PERIMETRE_FIGE",
                )
            jour = fields.get("date_debut") or inv.date_debut
            if jour > date.today():
                raise AppError("La date d'inventaire ne peut pas être dans le futur.", status.HTTP_422_UNPROCESSABLE_ENTITY)
            agence_id = fields["agence_id"] if "agence_id" in fields else inv.agence_id
            famille_id = fields["famille_id"] if "famille_id" in fields else inv.famille_id
            await self._assert_unique(
                annee=jour.year, mois=jour.month, agence_id=agence_id, famille_id=famille_id, exclude_id=inv.id
            )
            periode = await self._resolve_periode(jour.year, jour.month)
            inv.date_debut, inv.annee, inv.mois = jour, jour.year, jour.month
            inv.agence_id, inv.famille_id = agence_id, famille_id
            inv.periode_id = periode.id if periode else None
            for ligne in list(
                (
                    await self.db.execute(select(MgInventaireLigne).where(MgInventaireLigne.inventaire_id == inv.id))
                ).scalars().all()
            ):
                await self.db.delete(ligne)
            await self.db.flush()
            articles = await self.articles_perimetre(
                agence_id=agence_id, famille_id=famille_id, fin=fin_de_journee(jour)
            )
            if not articles:
                raise AppError("Aucun article stockable actif dans ce périmètre à cette date.", code="INVENTAIRE_VIDE")
            await self._photo(inv, articles)
        if fields.get("libelle"):
            inv.libelle = fields["libelle"].strip()
        if "responsable_id" in fields or "responsable_nom" in fields:
            inv.responsable_id, inv.responsable_nom = await self._responsable(
                fields.get("responsable_id"), fields.get("responsable_nom")
            )
        if "observation" in fields:
            inv.observation = (fields["observation"] or "").strip() or None
        inv.updated_by = self.user.id if self.user else None
        await self.db.flush()
        await self._audit(
            "update", "mg_inventaire", inv.id, request=request, before=before,
            after={**{k: str(v) if v is not None else None for k, v in fields.items()},
                   "photo_recalculee": change_perimetre},
        )
        await self.db.commit()
        return inv

    async def saisir_ligne(self, inventaire_id: uuid.UUID, ligne_id: uuid.UUID, data: InventaireLigneSaisie, *,
                           request: Request | None = None) -> dict:
        inv = await self.get(inventaire_id, for_update=True)
        self.exiger_saisie(inv)
        ligne = await self.db.scalar(
            select(MgInventaireLigne)
            .where(MgInventaireLigne.id == ligne_id, MgInventaireLigne.inventaire_id == inv.id)
            .with_for_update()
        )
        if ligne is None:
            raise AppError("Ligne d'inventaire introuvable", status.HTTP_404_NOT_FOUND, code="LIGNE_INTROUVABLE")
        article = await self.db.get(MgArticle, ligne.article_id)
        before = {
            "stock_physique": as_qty(ligne.stock_physique) if ligne.stock_physique is not None else None,
            "statut_comptage": ligne.statut_comptage,
            "commentaire": ligne.observation,
        }
        fields = data.model_dump(exclude_unset=True)
        if fields.get("exclure") is True:
            ligne.statut_comptage = "EXCLU"
            ligne.stock_physique = ligne.ecart = ligne.nature_ecart = None
            ligne.compte_par = ligne.compte_at = None
        elif fields.get("exclure") is False and ligne.statut_comptage == "EXCLU":
            ligne.statut_comptage = "NON_COMPTE"
        if data.effacer:
            ligne.stock_physique = ligne.ecart = ligne.nature_ecart = None
            ligne.compte_par = ligne.compte_at = None
            if ligne.statut_comptage != "EXCLU":
                ligne.statut_comptage = "NON_COMPTE"
        elif "stock_physique" in fields and fields["stock_physique"] is not None:
            if ligne.statut_comptage == "EXCLU":
                raise AppError(
                    "Article exclu du comptage : réintégrez-le avant de saisir une quantité.",
                    status.HTTP_409_CONFLICT,
                    code="LIGNE_EXCLUE",
                )
            physique = Decimal(fields["stock_physique"])
            ligne.stock_physique = physique
            ligne.ecart = physique - Decimal(ligne.stock_theorique or 0)
            ligne.nature_ecart = nature_ecart(ligne.ecart)
            ligne.statut_comptage = "COMPTE"
            ligne.compte_par = self.user.id if self.user else None
            ligne.compte_at = datetime.now(timezone.utc)
        if "commentaire" in fields:
            ligne.observation = (fields["commentaire"] or "").strip() or None
        ligne.updated_at = datetime.now(timezone.utc)

        demarre = False
        if inv.statut == "BROUILLON" and ligne.statut_comptage == "COMPTE":
            inv.statut = "EN_COURS"
            demarre = True
        inv.updated_by = self.user.id if self.user else None
        await self.db.flush()
        after = {
            "inventaire_id": str(inv.id),
            "inventaire": inv.reference,
            "article": article.code if article else None,
            "stock_theorique": as_qty(ligne.stock_theorique or 0),
            "stock_physique": as_qty(ligne.stock_physique) if ligne.stock_physique is not None else None,
            "ecart": as_qty(ligne.ecart) if ligne.ecart is not None else None,
            "statut_comptage": ligne.statut_comptage,
            "commentaire": ligne.observation,
        }
        await self._audit("saisie_physique", "mg_inventaire_ligne", ligne.id, request=request,
                          before=before, after=after)
        if demarre:
            await self._audit("demarrer", "mg_inventaire", inv.id, request=request,
                              before={"statut": "BROUILLON"}, after={"statut": "EN_COURS", "auto": True})
        inv_id, ligne_id, statut = inv.id, ligne.id, inv.statut
        await self.db.commit()
        return {
            "ligne": await self.ligne(inv_id, ligne_id),
            "stats": (await self.stats([inv_id]))[inv_id],
            "statut": statut,
        }

    async def saisir_lot(self, inventaire_id: uuid.UUID, lignes: list[InventaireLigneIn], *,
                         request: Request | None = None) -> MgInventaire:
        for payload in lignes:
            await self.saisir_ligne(
                inventaire_id,
                payload.id,
                InventaireLigneSaisie(stock_physique=payload.stock_physique, commentaire=payload.observation)
                if payload.observation is not None
                else InventaireLigneSaisie(stock_physique=payload.stock_physique),
                request=request,
            )
        return await self.get(inventaire_id)

    async def ajouter_ligne(self, inventaire_id: uuid.UUID, data: InventaireLigneAjout, *,
                            request: Request | None = None) -> dict:
        inv = await self.get(inventaire_id, for_update=True)
        self.verrou(inv)
        self.exiger(PERM_SAISIE)
        if inv.statut not in SAISIE_OUVERTE:
            raise AppError("Ajout de ligne possible uniquement en Brouillon ou En cours.", status.HTTP_409_CONFLICT)
        article = await self.db.scalar(
            select(MgArticle).where(MgArticle.id == data.article_id, MgArticle.deleted_at.is_(None))
        )
        if article is None or not article.stockable:
            raise AppError("Article introuvable ou non stockable.", status.HTTP_404_NOT_FOUND)
        deja = await self.db.scalar(
            select(MgInventaireLigne.id).where(
                MgInventaireLigne.inventaire_id == inv.id, MgInventaireLigne.article_id == article.id
            )
        )
        if deja:
            raise AppError(f"L'article {article.code} figure déjà dans cet inventaire.", status.HTTP_409_CONFLICT,
                           code="LIGNE_DOUBLON")
        ordre = int(
            await self.db.scalar(
                select(func.coalesce(func.max(MgInventaireLigne.sort_order), -1)).where(
                    MgInventaireLigne.inventaire_id == inv.id
                )
            )
            or 0
        )
        snapshot = inv.snapshot_at
        (ligne,) = await self._photo(inv, [article], start=ordre + 1, manuel=True)
        inv.snapshot_at = snapshot
        if data.commentaire:
            ligne.observation = data.commentaire.strip()
        await self.db.flush()
        await self._audit(
            "ajout_ligne", "mg_inventaire_ligne", ligne.id, request=request,
            after={"inventaire_id": str(inv.id), "inventaire": inv.reference, "article": article.code,
                   "stock_theorique": as_qty(ligne.stock_theorique)},
        )
        inv_id, ligne_id = inv.id, ligne.id
        await self.db.commit()
        return await self.ligne(inv_id, ligne_id)

    async def supprimer_ligne(self, inventaire_id: uuid.UUID, ligne_id: uuid.UUID, *,
                              request: Request | None = None) -> None:
        inv = await self.get(inventaire_id, for_update=True)
        self.verrou(inv)
        self.exiger(PERM_SAISIE)
        ligne = await self.db.scalar(
            select(MgInventaireLigne).where(
                MgInventaireLigne.id == ligne_id, MgInventaireLigne.inventaire_id == inv.id
            )
        )
        if ligne is None:
            raise AppError("Ligne d'inventaire introuvable", status.HTTP_404_NOT_FOUND)
        if not (inv.statut == "BROUILLON" or (inv.statut == "EN_COURS" and ligne.ajout_manuel)):
            raise AppError(
                "Seules les lignes ajoutées manuellement peuvent être retirées d'un inventaire commencé "
                "(excluez plutôt l'article du comptage).",
                status.HTTP_409_CONFLICT,
            )
        article = await self.db.get(MgArticle, ligne.article_id)
        await self._audit(
            "suppression_ligne", "mg_inventaire_ligne", ligne.id, request=request,
            before={"article": article.code if article else None,
                    "stock_physique": as_qty(ligne.stock_physique) if ligne.stock_physique is not None else None},
            after={"inventaire_id": str(inv.id), "inventaire": inv.reference},
        )
        await self.db.delete(ligne)
        await self.db.commit()

    # ------------------------------------------------------------------ workflow

    async def apercu_validation(self, inventaire_id: uuid.UUID) -> dict:
        inv = await self.get(inventaire_id)
        s = (await self.stats([inv.id]))[inv.id]
        ecarts = s["ecarts_negatifs"] + s["ecarts_positifs"]
        peut_forcer = self.peut(PERM_GESTION)
        message = None
        if s["a_compter"] == 0:
            message = "Aucun article à compter dans cet inventaire."
        elif s["non_comptes"]:
            message = (
                f"{s['non_comptes']} article(s) non compté(s) : validation impossible"
                + (" sans forçage." if peut_forcer else " (permission de forçage requise).")
            )
        return {
            "total": s["total"],
            "a_compter": s["a_compter"],
            "comptes": s["comptes"],
            "non_comptes": s["non_comptes"],
            "exclus": s["exclus"],
            "ecarts": ecarts,
            "ecarts_negatifs": s["ecarts_negatifs"],
            "ecarts_positifs": s["ecarts_positifs"],
            "ecart_net": s["ecart_net"],
            "mouvements_depuis": await self.mouvements_depuis(inv),
            "peut_valider": inv.statut == "A_CONTROLER" and s["a_compter"] > 0 and s["non_comptes"] == 0,
            "peut_forcer": inv.statut == "A_CONTROLER" and s["comptes"] > 0 and peut_forcer,
            "message": message,
        }

    async def transition(self, inventaire_id: uuid.UUID, action: str, *, motif: str | None = None,
                         forcer: bool = False, request: Request | None = None) -> MgInventaire:
        inv = await self.get(inventaire_id, for_update=True)
        action = (action or "").strip().lower()
        avant = inv.statut
        now = datetime.now(timezone.utc)
        details: dict = {}

        def exiger_statut(*statuts: str) -> None:
            if inv.statut not in statuts:
                if inv.statut in VERROUILLES and action not in {"generer_ajustements", "archiver", "annuler"}:
                    raise AppError(MSG_VERROU, status.HTTP_409_CONFLICT, code="INVENTAIRE_VERROUILLE")
                raise AppError(
                    f"Action « {action} » impossible au statut {inv.statut}.",
                    status.HTTP_409_CONFLICT,
                    code="INVENTAIRE_STATUT",
                )

        if action == "demarrer":
            self.exiger(PERM_SAISIE)
            exiger_statut("BROUILLON")
            inv.statut = "EN_COURS"
        elif action == "soumettre":
            self.exiger(PERM_SAISIE)
            exiger_statut("EN_COURS")
            s = (await self.stats([inv.id]))[inv.id]
            if s["comptes"] == 0:
                raise AppError("Aucun article compté : impossible de soumettre au contrôle.", code="INVENTAIRE_VIDE")
            inv.statut = "A_CONTROLER"
            details = {"non_comptes": s["non_comptes"]}
        elif action == "reprendre":
            self.exiger(PERM_VALIDATION, PERM_GESTION)
            exiger_statut("A_CONTROLER")
            inv.statut = "EN_COURS"
            details = {"motif": motif}
        elif action == "valider":
            self.exiger(PERM_VALIDATION)
            if inv.statut == "AJUSTE" or inv.statut == "VALIDE":
                raise AppError("Inventaire déjà validé.", status.HTTP_409_CONFLICT, code="INVENTAIRE_DEJA_VALIDE")
            exiger_statut("A_CONTROLER")
            s = (await self.stats([inv.id]))[inv.id]
            if s["comptes"] == 0:
                raise AppError("Aucun article compté : validation impossible.", code="INVENTAIRE_VIDE")
            if s["non_comptes"]:
                if not forcer:
                    raise AppError(
                        f"{s['non_comptes']} article(s) non compté(s) : terminez le comptage avant validation.",
                        status.HTTP_409_CONFLICT,
                        code="INVENTAIRE_INCOMPLET",
                    )
                self.exiger(PERM_GESTION, message="Forcer la validation requiert la permission mg.stock.inventory.manage.")
                if not (motif or "").strip():
                    raise AppError("Motif obligatoire pour forcer la validation.", status.HTTP_422_UNPROCESSABLE_ENTITY)
                inv.validation_forcee = True
                details = {"forcee": True, "non_comptes": s["non_comptes"], "motif": motif}
            inv.statut = "VALIDE"
            inv.valide_at = now
            inv.valide_by = self.user.id if self.user else None
            details.update({"ecarts": s["ecarts_negatifs"] + s["ecarts_positifs"], "ecart_net": as_qty(s["ecart_net"])})
        elif action == "generer_ajustements":
            self.exiger(PERM_AJUSTEMENT)
            if inv.ajustements_at is not None or inv.statut in {"AJUSTE", "ARCHIVE"}:
                raise AppError(
                    "Les ajustements de cet inventaire ont déjà été générés.",
                    status.HTTP_409_CONFLICT,
                    code="INVENTAIRE_DEJA_AJUSTE",
                )
            exiger_statut("VALIDE")
            details = await self._generer_ajustements(inv)
            inv.statut = "AJUSTE"
            inv.ajustements_at = now
            inv.ajustements_by = self.user.id if self.user else None
        elif action == "archiver":
            self.exiger(PERM_VALIDATION, PERM_GESTION)
            exiger_statut("AJUSTE")
            inv.statut = "ARCHIVE"
            inv.date_fin = inv.date_fin or date.today()
            inv.cloture_at = now
            inv.cloture_by = self.user.id if self.user else None
        elif action == "annuler":
            self.exiger(PERM_GESTION, message="Annuler un inventaire requiert la permission mg.stock.inventory.manage.")
            exiger_statut(*ANNULABLES)
            if await self.nb_ajustements(inv.id):
                raise AppError(
                    "Des ajustements de stock existent pour cet inventaire : annulation impossible.",
                    status.HTTP_409_CONFLICT,
                    code="INVENTAIRE_VERROUILLE",
                )
            if not (motif or "").strip():
                raise AppError("Motif d'annulation obligatoire.", status.HTTP_422_UNPROCESSABLE_ENTITY)
            inv.statut = "ANNULE"
            inv.annule_at = now
            inv.annule_by = self.user.id if self.user else None
            inv.motif_annulation = motif.strip()
            details = {"motif": inv.motif_annulation}
        else:
            raise AppError(f"Action inventaire inconnue : {action}", status.HTTP_400_BAD_REQUEST)

        inv.updated_by = self.user.id if self.user else None
        await self.db.flush()
        await self._audit(
            action, "mg_inventaire", inv.id, request=request,
            before={"statut": avant},
            after={"reference": inv.reference, "statut": inv.statut, **details},
        )
        await self.db.commit()
        return inv

    async def _generer_ajustements(self, inv: MgInventaire) -> dict:
        from app.services.mg_stock_service import MgStockService

        stock = MgStockService(self.db)
        date_mvt = min(fin_de_journee(inv.date_debut), datetime.now(timezone.utc))
        lignes = list(
            (
                await self.db.execute(
                    select(MgInventaireLigne)
                    .where(
                        MgInventaireLigne.inventaire_id == inv.id,
                        MgInventaireLigne.statut_comptage == "COMPTE",
                    )
                    .order_by(MgInventaireLigne.sort_order)
                )
            ).scalars().all()
        )
        periode = None
        if inv.periode_id:
            periode = await self.db.get(MgStockPeriode, inv.periode_id)
            if periode is not None and periode.statut == "CLOTUREE":
                periode = None
        psvc = MgStockPeriodeService(self.db)
        crees = 0
        total = Decimal("0")
        for ligne in lignes:
            ecart = Decimal(ligne.stock_physique or 0) - Decimal(ligne.stock_theorique or 0)
            ligne.ecart = ecart
            ligne.nature_ecart = nature_ecart(ecart)
            article = await self.db.scalar(
                select(MgArticle).where(MgArticle.id == ligne.article_id).with_for_update()
            )
            if article is None or not article.stockable:
                continue
            if ecart != 0:
                await stock._apply_mouvement(
                    article=article,
                    type_mouvement="AJUSTEMENT",
                    quantite=ecart,
                    agence_id=inv.agence_id or article.agence_id,
                    initiateur=self.user,
                    motif=f"Ajustement inventaire {inv.reference}",
                    observation=(
                        f"Théorique {as_qty(ligne.stock_theorique or 0)} · Physique {as_qty(ligne.stock_physique or 0)}"
                        f" · Écart {as_qty(ecart):+d}"
                    ),
                    source_type="inventaire",
                    source_id=inv.id,
                    date_mouvement=date_mvt,
                )
                crees += 1
                total += ecart
            if periode is not None:
                await psvc.apply_physique(periode, article, Decimal(article.stock_actuel or 0))
        return {"ajustements": crees, "ecart_net": as_qty(total)}

    async def ajustements(self, inventaire_id: uuid.UUID) -> list[dict]:
        await self.get(inventaire_id)
        rows = (
            await self.db.execute(
                select(MgStockMouvement, MgArticle)
                .join(MgArticle, MgArticle.id == MgStockMouvement.article_id)
                .where(
                    MgStockMouvement.source_type == "inventaire",
                    MgStockMouvement.source_id == inventaire_id,
                )
                .order_by(MgArticle.code)
            )
        ).all()
        return [
            {
                "id": m.id,
                "reference": m.reference,
                "date_mouvement": m.date_mouvement,
                "type_mouvement": m.type_mouvement,
                "quantite": as_qty(m.quantite),
                "article_id": a.id,
                "article_code": a.code,
                "article_designation": a.designation,
                "observation": m.observation,
            }
            for m, a in rows
        ]

    async def supprimer(self, inventaire_id: uuid.UUID, *, request: Request | None = None) -> MgInventaire:
        inv = await self.get(inventaire_id, for_update=True)
        self.exiger(PERM_GESTION, message="Supprimer un inventaire requiert la permission mg.stock.inventory.manage.")
        if inv.statut not in {"BROUILLON", "ANNULE"} or await self.nb_ajustements(inv.id):
            raise AppError(
                "Seul un inventaire en Brouillon ou Annulé peut être supprimé. Utilisez l'annulation : "
                "un inventaire validé ou archivé reste toujours consultable.",
                status.HTTP_409_CONFLICT,
                code="INVENTAIRE_VERROUILLE",
            )
        inv.deleted_at = datetime.now(timezone.utc)
        inv.is_active = False
        await self._audit("delete", "mg_inventaire", inv.id, request=request,
                          before={"reference": inv.reference, "statut": inv.statut})
        await self.db.commit()
        return inv

    async def toutes_lignes(self, inventaire_id: uuid.UUID) -> list[dict]:
        rows = (await self.db.execute(self._lignes_stmt(inventaire_id).order_by(MgInventaireLigne.sort_order))).all()
        return [self.serialize_ligne(lg_, art, fam, nom or mail) for lg_, art, fam, nom, mail in rows]
