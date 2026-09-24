"""Périodes de stock, soldes et clôture mensuelle.

Le report N → N+1 pose le stock initial sans créer de mouvement ENTREE.
"""

from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import User
from app.models.mg_stock import (
    MgArticle,
    MgInventaire,
    MgStockMouvement,
    MgStockParametre,
    MgStockPeriode,
    MgStockSolde,
)

MOIS_FR = (
    "",
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
)

INV_OUVERTS = frozenset(
    {
        "BROUILLON",
        "OUVERT",
        "EN_COMPTAGE",
        "EN_COURS",
        "COMPTAGE_TERMINE",
        "EN_CONTROLE",
        "VALIDE",
        "AJUSTEMENTS_APPLIQUES",
    }
)
INV_TERMINES = frozenset({"CLOTURE", "AJUSTEMENTS_APPLIQUES"})


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def next_year_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def periode_libelle(year: int, month: int) -> str:
    nom = MOIS_FR[month] if 1 <= month <= 12 else str(month)
    return f"{nom} {year}"


def compute_theorique(
    stock_initial: Decimal,
    entrees: Decimal,
    sorties: Decimal,
    ajustements: Decimal,
) -> Decimal:
    return Decimal(stock_initial or 0) + Decimal(entrees or 0) - Decimal(sorties or 0) + Decimal(
        ajustements or 0
    )


def nature_ecart(ecart: Decimal | None) -> str | None:
    if ecart is None:
        return None
    if ecart == 0:
        return "CONFORME"
    if ecart > 0:
        return "SURPLUS"
    return "MANQUANT"


def stock_final_from_solde(solde: MgStockSolde) -> Decimal:
    if solde.stock_physique is not None:
        return Decimal(solde.stock_physique)
    return Decimal(solde.stock_theorique or 0)


class MgStockPeriodeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_periodes(self) -> list[MgStockPeriode]:
        stmt = select(MgStockPeriode).order_by(MgStockPeriode.annee.desc(), MgStockPeriode.mois.desc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_periode(self, periode_id: uuid.UUID, *, for_update: bool = False) -> MgStockPeriode:
        stmt = select(MgStockPeriode).where(MgStockPeriode.id == periode_id)
        if for_update:
            stmt = stmt.with_for_update()
        row = await self.db.scalar(stmt)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Période introuvable")
        return row

    async def periode_ouverte(self, *, for_update: bool = False) -> MgStockPeriode | None:
        stmt = select(MgStockPeriode).where(MgStockPeriode.statut == "OUVERTE")
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def periode_for_date(self, when: date | datetime) -> MgStockPeriode | None:
        d = when.date() if isinstance(when, datetime) else when
        return await self.db.scalar(
            select(MgStockPeriode).where(
                MgStockPeriode.annee == d.year,
                MgStockPeriode.mois == d.month,
            )
        )

    async def ensure_open_periode(self, user: User | None = None) -> MgStockPeriode:
        """Une seule période ouverte. Crée le mois calendaire s'il n'existe aucune période."""
        opened = await self.periode_ouverte()
        if opened is not None:
            return opened
        last = await self.db.scalar(
            select(MgStockPeriode).order_by(MgStockPeriode.annee.desc(), MgStockPeriode.mois.desc())
        )
        today = date.today()
        if last is None:
            return await self._create_periode(today.year, today.month, user=user, precedente=None)
        if last.statut == "CLOTUREE":
            ny, nm = next_year_month(last.annee, last.mois)
            return await self._create_periode(ny, nm, user=user, precedente=last)
        return last

    async def resolve_for_movement(
        self,
        date_mouvement: datetime | None,
        *,
        allow_closed: bool = False,
    ) -> MgStockPeriode:
        when = date_mouvement or datetime.now(timezone.utc)
        d = when.date() if isinstance(when, datetime) else when
        cible = await self.periode_for_date(d)
        if cible is not None:
            if cible.statut == "CLOTUREE" and not allow_closed:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Période {cible.libelle} clôturée — mouvement interdit.",
                )
            return cible
        ouverte = await self.ensure_open_periode()
        if d < ouverte.date_debut or d > ouverte.date_fin:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Aucun mouvement hors période ouverte ({ouverte.libelle}). "
                    "Clôturez la période avant de saisir le mois suivant."
                ),
            )
        return ouverte

    async def get_or_create_solde(
        self,
        periode: MgStockPeriode,
        article: MgArticle,
        *,
        stock_initial: Decimal | None = None,
    ) -> MgStockSolde:
        solde = await self.db.scalar(
            select(MgStockSolde)
            .where(MgStockSolde.periode_id == periode.id, MgStockSolde.article_id == article.id)
            .with_for_update()
        )
        if solde is not None:
            return solde
        initial = Decimal(stock_initial if stock_initial is not None else 0)
        solde = MgStockSolde(
            periode_id=periode.id,
            article_id=article.id,
            stock_initial=initial,
            entrees=Decimal("0"),
            sorties=Decimal("0"),
            ajustements=Decimal("0"),
            stock_theorique=initial,
        )
        self.db.add(solde)
        await self.db.flush()
        return solde

    async def touch_solde(
        self,
        periode: MgStockPeriode,
        article: MgArticle,
        type_mouvement: str,
        quantite: Decimal,
    ) -> MgStockSolde:
        solde = await self.get_or_create_solde(periode, article)
        qty = Decimal(quantite)
        if type_mouvement == "ENTREE":
            solde.entrees = Decimal(solde.entrees or 0) + qty
        elif type_mouvement == "SORTIE":
            solde.sorties = Decimal(solde.sorties or 0) + qty
        elif type_mouvement == "AJUSTEMENT":
            solde.ajustements = Decimal(solde.ajustements or 0) + qty
        solde.stock_theorique = compute_theorique(
            solde.stock_initial, solde.entrees, solde.sorties, solde.ajustements
        )
        if solde.stock_physique is not None:
            solde.ecart = Decimal(solde.stock_physique) - Decimal(solde.stock_theorique)
        return solde

    async def apply_physique(
        self,
        periode: MgStockPeriode,
        article: MgArticle,
        physique: Decimal,
    ) -> MgStockSolde:
        solde = await self.get_or_create_solde(periode, article)
        solde.stock_physique = Decimal(physique)
        solde.ecart = Decimal(physique) - Decimal(solde.stock_theorique or 0)
        return solde

    async def bootstrap_soldes(self, periode: MgStockPeriode) -> int:
        """Reconstruit les soldes à partir de stock_actuel et des mouvements du mois."""
        articles = list(
            (
                await self.db.execute(
                    select(MgArticle).where(
                        MgArticle.deleted_at.is_(None),
                        MgArticle.stockable.is_(True),
                    )
                )
            ).scalars().all()
        )
        existing = {
            row.article_id
            for row in (
                await self.db.execute(
                    select(MgStockSolde.article_id).where(MgStockSolde.periode_id == periode.id)
                )
            ).all()
        }
        created = 0
        start = datetime(periode.annee, periode.mois, 1, tzinfo=timezone.utc)
        ny, nm = next_year_month(periode.annee, periode.mois)
        end = datetime(ny, nm, 1, tzinfo=timezone.utc)

        for article in articles:
            if article.id in existing:
                continue
            sums = (
                await self.db.execute(
                    select(
                        MgStockMouvement.type_mouvement,
                        func.coalesce(func.sum(MgStockMouvement.quantite), 0),
                    )
                    .where(
                        MgStockMouvement.article_id == article.id,
                        MgStockMouvement.date_mouvement >= start,
                        MgStockMouvement.date_mouvement < end,
                        MgStockMouvement.type_mouvement.in_(["ENTREE", "SORTIE", "AJUSTEMENT"]),
                    )
                    .group_by(MgStockMouvement.type_mouvement)
                )
            ).all()
            by_type = {row[0]: Decimal(row[1] or 0) for row in sums}
            entrees = by_type.get("ENTREE", Decimal("0"))
            sorties = by_type.get("SORTIE", Decimal("0"))
            ajustements = by_type.get("AJUSTEMENT", Decimal("0"))
            actuel = Decimal(article.stock_actuel or 0)
            initial = actuel - entrees + sorties - ajustements
            theo = compute_theorique(initial, entrees, sorties, ajustements)
            self.db.add(
                MgStockSolde(
                    periode_id=periode.id,
                    article_id=article.id,
                    stock_initial=initial,
                    entrees=entrees,
                    sorties=sorties,
                    ajustements=ajustements,
                    stock_theorique=theo,
                )
            )
            created += 1
        if created:
            await self.db.flush()
        return created

    async def list_soldes(
        self,
        periode_id: uuid.UUID,
        *,
        q: str | None = None,
        famille_id: uuid.UUID | None = None,
        agence_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[dict], int]:
        await self.get_periode(periode_id)
        filters = [MgStockSolde.periode_id == periode_id]
        stmt = (
            select(MgStockSolde, MgArticle)
            .join(MgArticle, MgArticle.id == MgStockSolde.article_id)
            .where(*filters)
        )
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where((MgArticle.code.ilike(like)) | (MgArticle.designation.ilike(like)))
        if famille_id:
            stmt = stmt.where(MgArticle.famille_id == famille_id)
        if agence_id:
            stmt = stmt.where(MgArticle.agence_id == agence_id)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.db.scalar(count_stmt)) or 0)
        page = max(1, page)
        size = max(1, min(size, 500))
        rows = (
            await self.db.execute(
                stmt.order_by(MgArticle.code).offset((page - 1) * size).limit(size)
            )
        ).all()
        items = [self._solde_out(solde, article) for solde, article in rows]
        return items, total

    def _solde_out(self, solde: MgStockSolde, article: MgArticle | None = None) -> dict:
        theo = compute_theorique(solde.stock_initial, solde.entrees, solde.sorties, solde.ajustements)
        final = solde.stock_final if solde.stock_final is not None else (
            solde.stock_physique if solde.stock_physique is not None else theo
        )
        return {
            "id": solde.id,
            "periode_id": solde.periode_id,
            "article_id": solde.article_id,
            "article_code": article.code if article else None,
            "article_designation": article.designation if article else None,
            "famille_id": article.famille_id if article else None,
            "uom": article.uom if article else None,
            "stock_initial": solde.stock_initial,
            "entrees": solde.entrees,
            "sorties": solde.sorties,
            "ajustements": solde.ajustements,
            "stock_theorique": theo,
            "stock_physique": solde.stock_physique,
            "ecart": solde.ecart,
            "nature_ecart": nature_ecart(solde.ecart),
            "stock_final": final,
        }

    def serialize_periode(self, periode: MgStockPeriode, *, extras: dict | None = None) -> dict:
        data = {
            "id": periode.id,
            "annee": periode.annee,
            "mois": periode.mois,
            "libelle": periode.libelle,
            "date_debut": periode.date_debut,
            "date_fin": periode.date_fin,
            "statut": periode.statut,
            "agence_id": periode.agence_id,
            "periode_precedente_id": periode.periode_precedente_id,
            "cloture_at": periode.cloture_at,
            "reopen_at": periode.reopen_at,
            "reopen_motif": periode.reopen_motif,
        }
        if extras:
            data.update(extras)
        return data

    async def preview_cloture(self, periode_id: uuid.UUID) -> dict:
        periode = await self.get_periode(periode_id)
        await self.bootstrap_soldes(periode)
        soldes = list(
            (
                await self.db.execute(select(MgStockSolde).where(MgStockSolde.periode_id == periode.id))
            ).scalars().all()
        )
        invs = list(
            (
                await self.db.execute(
                    select(MgInventaire).where(
                        MgInventaire.deleted_at.is_(None),
                        MgInventaire.periode_id == periode.id,
                    )
                )
            ).scalars().all()
        )
        if not invs:
            invs = list(
                (
                    await self.db.execute(
                        select(MgInventaire).where(
                            MgInventaire.deleted_at.is_(None),
                            extract("year", MgInventaire.date_debut) == periode.annee,
                            extract("month", MgInventaire.date_debut) == periode.mois,
                        )
                    )
                ).scalars().all()
            )
        ouverts = [i for i in invs if i.statut in INV_OUVERTS and i.statut not in INV_TERMINES]
        termines = [i for i in invs if i.statut in {"CLOTURE"}]
        with_ecart = sum(1 for s in soldes if s.ecart not in (None, Decimal("0")))
        anomalies: list[str] = []
        if ouverts:
            anomalies.append(f"{len(ouverts)} inventaire(s) non clôturé(s)")
        obligatoire = await self._param_bool("inventaire_obligatoire")
        if obligatoire and not termines and not periode.reopen_at:
            anomalies.append("Inventaire mensuel obligatoire non réalisé")
        stock_final = sum((stock_final_from_solde(s) for s in soldes), Decimal("0"))
        return {
            "periode": self.serialize_periode(periode),
            "articles": len(soldes),
            "stock_final": float(stock_final),
            "articles_avec_ecarts": with_ecart,
            "ajustements": sum(1 for s in soldes if Decimal(s.ajustements or 0) != 0),
            "inventaires": len(invs),
            "inventaires_ouverts": len(ouverts),
            "anomalies": anomalies,
            "bloquant": bool(anomalies),
            "periode_suivante": periode_libelle(*next_year_month(periode.annee, periode.mois)),
        }

    async def cloturer(self, periode_id: uuid.UUID, user: User) -> dict:
        periode = await self.get_periode(periode_id, for_update=True)
        if periode.statut == "CLOTUREE":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Période déjà clôturée")
        preview = await self.preview_cloture(periode.id)
        if preview["bloquant"]:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Clôture bloquée : " + " ; ".join(preview["anomalies"]),
            )
        soldes = list(
            (
                await self.db.execute(
                    select(MgStockSolde)
                    .where(MgStockSolde.periode_id == periode.id)
                    .with_for_update()
                )
            ).scalars().all()
        )
        now = datetime.now(timezone.utc)
        periode.statut = "CLOTUREE"
        periode.cloture_at = now
        periode.cloture_by = user.id
        for solde in soldes:
            solde.stock_theorique = compute_theorique(
                solde.stock_initial, solde.entrees, solde.sorties, solde.ajustements
            )
            solde.stock_final = stock_final_from_solde(solde)

        ny, nm = next_year_month(periode.annee, periode.mois)
        suivante = await self.db.scalar(
            select(MgStockPeriode).where(MgStockPeriode.annee == ny, MgStockPeriode.mois == nm)
        )
        if suivante is None:
            suivante = await self._create_periode(ny, nm, user=user, precedente=periode)
        else:
            suivante.periode_precedente_id = periode.id
            autre_ouverte = await self.db.scalar(
                select(MgStockPeriode).where(
                    MgStockPeriode.statut == "OUVERTE",
                    MgStockPeriode.id != periode.id,
                    MgStockPeriode.id != suivante.id,
                )
            )
            if suivante.statut != "OUVERTE" and autre_ouverte is None:
                suivante.statut = "OUVERTE"

        by_article = {
            row.article_id: row
            for row in (
                await self.db.execute(
                    select(MgStockSolde).where(MgStockSolde.periode_id == suivante.id)
                )
            ).scalars().all()
        }
        for solde in soldes:
            final = Decimal(solde.stock_final or 0)
            dest = by_article.get(solde.article_id)
            if dest is None:
                dest = MgStockSolde(
                    periode_id=suivante.id,
                    article_id=solde.article_id,
                    stock_initial=final,
                    entrees=Decimal("0"),
                    sorties=Decimal("0"),
                    ajustements=Decimal("0"),
                    stock_theorique=final,
                    stock_physique=None,
                    ecart=None,
                    stock_final=None,
                )
                self.db.add(dest)
            else:
                dest.stock_initial = final
                dest.stock_theorique = compute_theorique(
                    dest.stock_initial, dest.entrees, dest.sorties, dest.ajustements
                )
                if dest.stock_final is not None:
                    dest.stock_final = stock_final_from_solde(dest)
        await self.db.flush()
        return {
            "periode": self.serialize_periode(periode),
            "periode_suivante": self.serialize_periode(suivante),
            "articles": len(soldes),
            "stock_final": preview["stock_final"],
        }

    async def rouvrir(
        self, periode_id: uuid.UUID, user: User, motif: str
    ) -> tuple[MgStockPeriode, dict | None]:
        motif = (motif or "").strip()
        if len(motif) < 5:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Motif de réouverture obligatoire (5 caractères minimum).",
            )
        periode = await self.get_periode(periode_id, for_update=True)
        if periode.statut != "CLOTUREE":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Seule une période clôturée peut être réouverte")
        autre = await self.db.scalar(
            select(MgStockPeriode).where(
                MgStockPeriode.statut == "OUVERTE",
                MgStockPeriode.id != periode.id,
            )
        )
        locked = None
        if autre is not None:
            mvt_count = int(
                await self.db.scalar(
                    select(func.count())
                    .select_from(MgStockMouvement)
                    .where(MgStockMouvement.periode_id == autre.id)
                )
                or 0
            )
            autre.statut = "CLOTUREE"
            if autre.cloture_at is None:
                autre.cloture_at = datetime.now(timezone.utc)
                autre.cloture_by = user.id
            locked = {"id": str(autre.id), "libelle": autre.libelle, "mouvements": mvt_count}
        periode.statut = "OUVERTE"
        periode.reopen_at = datetime.now(timezone.utc)
        periode.reopen_by = user.id
        periode.reopen_motif = motif
        periode.cloture_at = None
        periode.cloture_by = None
        await self.db.flush()
        return periode, locked

    async def cloture_alerte(self, periode: MgStockPeriode | None) -> tuple[str | None, str | None]:
        if periode is None:
            return None, None
        today = date.today()
        invs = list(
            (
                await self.db.execute(
                    select(MgInventaire).where(
                        MgInventaire.deleted_at.is_(None),
                        MgInventaire.periode_id == periode.id,
                    )
                )
            ).scalars().all()
        )
        if not invs:
            invs = list(
                (
                    await self.db.execute(
                        select(MgInventaire).where(
                            MgInventaire.deleted_at.is_(None),
                            extract("year", MgInventaire.date_debut) == periode.annee,
                            extract("month", MgInventaire.date_debut) == periode.mois,
                        )
                    )
                ).scalars().all()
            )
        clotures = [i for i in invs if i.statut == "CLOTURE"]
        en_cours = [i for i in invs if i.statut in INV_OUVERTS]

        if periode.statut == "CLOTUREE":
            suivante = await self.db.scalar(
                select(MgStockPeriode).where(MgStockPeriode.periode_precedente_id == periode.id)
            )
            if suivante and suivante.statut == "OUVERTE":
                return "periode_suivante_ouverte", f"Clôture terminée — {suivante.libelle} ouverte"
            return "cloture_terminee", f"Clôture {periode.libelle} terminée"

        fin_proche = today >= periode.date_fin or (
            today.year == periode.annee and today.month == periode.mois and today.day >= 25
        )
        if clotures and periode.statut == "OUVERTE":
            return (
                "inventaire_realise_cloture_attente",
                f"Inventaire réalisé — clôture {periode.libelle} en attente",
            )
        if fin_proche and not clotures:
            return "inventaire_a_faire", f"Inventaire de {periode.libelle} à réaliser"
        if en_cours:
            return "inventaire_a_faire", f"Inventaire de {periode.libelle} en cours"
        if today > periode.date_fin:
            return "periode_a_cloturer", f"Période {periode.libelle} à clôturer"
        return None, None

    async def _create_periode(
        self,
        year: int,
        month: int,
        *,
        user: User | None,
        precedente: MgStockPeriode | None,
    ) -> MgStockPeriode:
        existing = await self.db.scalar(
            select(MgStockPeriode).where(MgStockPeriode.annee == year, MgStockPeriode.mois == month)
        )
        if existing is not None:
            return existing
        debut, fin = month_bounds(year, month)
        now = datetime.now(timezone.utc)
        periode = MgStockPeriode(
            annee=year,
            mois=month,
            libelle=periode_libelle(year, month),
            date_debut=debut,
            date_fin=fin,
            statut="OUVERTE",
            periode_precedente_id=precedente.id if precedente else None,
            opened_at=now,
            opened_by=user.id if user else None,
        )
        self.db.add(periode)
        await self.db.flush()
        if precedente is not None:
            prev_soldes = list(
                (
                    await self.db.execute(
                        select(MgStockSolde).where(MgStockSolde.periode_id == precedente.id)
                    )
                ).scalars().all()
            )
            for solde in prev_soldes:
                final = stock_final_from_solde(solde)
                if solde.stock_final is None:
                    solde.stock_final = final
                self.db.add(
                    MgStockSolde(
                        periode_id=periode.id,
                        article_id=solde.article_id,
                        stock_initial=final,
                        entrees=Decimal("0"),
                        sorties=Decimal("0"),
                        ajustements=Decimal("0"),
                        stock_theorique=final,
                    )
                )
            await self.db.flush()
        else:
            await self.bootstrap_soldes(periode)
        return periode

    async def _param_bool(self, cle: str) -> bool:
        row = await self.db.scalar(select(MgStockParametre).where(MgStockParametre.cle == cle))
        if row is None:
            return False
        return str(row.valeur).strip().lower() in {"1", "true", "oui", "yes"}

    async def totaux_periode(self, periode: MgStockPeriode) -> dict:
        await self.bootstrap_soldes(periode)
        row = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(MgStockSolde.stock_initial), 0),
                    func.coalesce(func.sum(MgStockSolde.entrees), 0),
                    func.coalesce(func.sum(MgStockSolde.sorties), 0),
                    func.coalesce(func.sum(MgStockSolde.ajustements), 0),
                    func.coalesce(func.sum(MgStockSolde.stock_theorique), 0),
                    func.count(MgStockSolde.id),
                ).where(MgStockSolde.periode_id == periode.id)
            )
        ).one()
        return {
            "stock_initial": float(row[0] or 0),
            "entrees": float(row[1] or 0),
            "sorties": float(row[2] or 0),
            "ajustements": float(row[3] or 0),
            "stock_theorique": float(row[4] or 0),
            "articles": int(row[5] or 0),
        }
