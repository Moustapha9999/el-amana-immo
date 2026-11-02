"""Périodes de stock, soldes, clôture mensuelle et régularisation des périodes clôturées.

Le report N → N+1 pose le stock initial sans créer de mouvement ENTREE.

Statuts : OUVERTE (saisie courante ; le calendrier avance jusqu'au mois du jour sans exiger de
clôture, plusieurs périodes peuvent donc être ouvertes), ROUVERTE (période clôturée rouverte par un
administrateur pour régularisation), CLOTUREE. La clôture suit l'ordre chronologique.

Un mouvement enregistré dans une période antérieure reporte son effet exact (delta) sur le stock
initial de toutes les périodes suivantes, comme la suppression administrateur. L'historique importé
(reports mensuels non continus) n'est jamais reconstruit à partir des mouvements.

Réouvertures, clôtures et créations de période sont sérialisées par un verrou transactionnel
PostgreSQL ; un mouvement verrouille sa période en lecture (``FOR SHARE``) : une clôture attend la
fin des saisies en cours et une saisie concurrente voit le nouveau statut.
"""

from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import extract, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.auth import User
from app.models.mg_stock import (
    MgArticle,
    MgInventaire,
    MgStockMouvement,
    MgStockParametre,
    MgStockPeriode,
    MgStockPeriodeEvenement,
    MgStockSolde,
)
from app.schemas.nombres import format_qty

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

OUVERTE = "OUVERTE"
ROUVERTE = "ROUVERTE"
CLOTUREE = "CLOTUREE"
STATUTS_SAISIE = frozenset({OUVERTE, ROUVERTE})
STATUT_LIBELLES = {OUVERTE: "Ouverte", ROUVERTE: "Rouverte", CLOTUREE: "Clôturée"}

INV_OUVERTS = frozenset({"BROUILLON", "EN_COURS", "A_CONTROLER", "VALIDE"})
INV_TERMINES = frozenset({"AJUSTE", "ARCHIVE"})
TYPES_SOLDE = ("ENTREE", "SORTIE", "AJUSTEMENT")

# Clé du verrou transactionnel (pg_advisory_xact_lock) des opérations de période.
VERROU_PERIODES = 7_310_524_203
# Tolérance d'horloge entre poste client et serveur pour une date « maintenant ».
MARGE_DATE_FUTURE = timedelta(minutes=5)
PERMISSION_REGULARISATION = "mg.stock.period.reopen"


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def aujourdhui() -> date:
    return maintenant().date()


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


def effet_mouvement(type_mouvement: str, quantite: Decimal) -> Decimal:
    """Variation du stock théorique (les mouvements INVENTAIRE ne passent pas par les soldes)."""
    qty = Decimal(quantite or 0)
    if type_mouvement == "SORTIE":
        return -qty
    if type_mouvement in ("ENTREE", "AJUSTEMENT"):
        return qty
    return Decimal("0")


def _dec(valeur) -> Decimal | None:
    return None if valeur is None else Decimal(str(valeur))


def _controle(code: str, libelle: str, ok: bool, detail: str | None = None, *, bloquant: bool = True) -> dict:
    return {"code": code, "libelle": libelle, "ok": ok, "bloquant": bloquant and not ok, "detail": detail}


class MgStockPeriodeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ lecture
    async def list_periodes(self) -> list[MgStockPeriode]:
        stmt = select(MgStockPeriode).order_by(MgStockPeriode.annee.desc(), MgStockPeriode.mois.desc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_periode(self, periode_id: uuid.UUID, *, for_update: bool = False) -> MgStockPeriode:
        stmt = select(MgStockPeriode).where(MgStockPeriode.id == periode_id)
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        row = await self.db.scalar(stmt)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Période introuvable")
        return row

    async def periode_ouverte(self, *, for_update: bool = False) -> MgStockPeriode | None:
        """Période de saisie courante : la plus récente au statut OUVERTE."""
        stmt = (
            select(MgStockPeriode)
            .where(MgStockPeriode.statut == OUVERTE)
            .order_by(MgStockPeriode.date_debut.desc())
            .limit(1)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def periode_a_cloturer(self) -> MgStockPeriode | None:
        """Plus ancienne période non clôturée : la prochaine à clôturer."""
        return await self.db.scalar(
            select(MgStockPeriode)
            .where(MgStockPeriode.statut.in_(sorted(STATUTS_SAISIE)))
            .order_by(MgStockPeriode.date_debut)
            .limit(1)
        )

    async def periodes_non_cloturees(self) -> list[MgStockPeriode]:
        return list(
            (
                await self.db.execute(
                    select(MgStockPeriode)
                    .where(MgStockPeriode.statut.in_(sorted(STATUTS_SAISIE)))
                    .order_by(MgStockPeriode.date_debut)
                )
            ).scalars().all()
        )

    async def periode_for_date(self, when: date | datetime) -> MgStockPeriode | None:
        d = when.date() if isinstance(when, datetime) else when
        return await self.db.scalar(
            select(MgStockPeriode).where(
                MgStockPeriode.annee == d.year,
                MgStockPeriode.mois == d.month,
            )
        )

    async def periodes_suivantes(self, periode: MgStockPeriode) -> list[MgStockPeriode]:
        return list(
            (
                await self.db.execute(
                    select(MgStockPeriode)
                    .where(MgStockPeriode.date_debut > periode.date_debut)
                    .order_by(MgStockPeriode.date_debut)
                )
            ).scalars().all()
        )

    async def _a_des_suivantes(self, periode: MgStockPeriode) -> bool:
        return (
            await self.db.scalar(
                select(MgStockPeriode.id).where(MgStockPeriode.date_debut > periode.date_debut).limit(1)
            )
        ) is not None

    async def _derniere(self) -> MgStockPeriode | None:
        return await self.db.scalar(
            select(MgStockPeriode).order_by(MgStockPeriode.date_debut.desc()).limit(1)
        )

    async def verrouiller(self) -> None:
        """Sérialise réouvertures, clôtures et créations de période jusqu'à la fin de la transaction."""
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:cle)"), {"cle": VERROU_PERIODES})

    # ------------------------------------------------------- calendrier & saisie
    async def ensure_open_periode(self, user: User | None = None) -> MgStockPeriode:
        """Garantit les périodes jusqu'au mois du jour et renvoie la période de saisie courante.

        Les mois manquants sont créés à la suite (report du stock final) sans clôturer les
        précédents : une période non terminée reste ouverte tant qu'elle n'est pas clôturée.
        """
        courant = aujourdhui()
        cible = (courant.year, courant.month)
        last = await self._derniere()
        ouverte = await self.periode_ouverte()
        if last is not None and ouverte is not None and (last.annee, last.mois) >= cible:
            return ouverte
        await self.verrouiller()
        last = await self._derniere()
        if last is None:
            return await self._create_periode(courant.year, courant.month, user=user, precedente=None)
        while (last.annee, last.mois) < cible or await self.periode_ouverte() is None:
            ny, nm = next_year_month(last.annee, last.mois)
            last = await self._create_periode(ny, nm, user=user, precedente=last)
        return await self.periode_ouverte() or last

    async def resolve_for_movement(
        self,
        date_mouvement: datetime | None,
        *,
        regularisation_autorisee: bool = False,
    ) -> MgStockPeriode:
        """Période d'imputation d'un mouvement, verrouillée en lecture jusqu'à la fin de la transaction.

        Date réelle du mouvement ≤ maintenant ; période OUVERTE pour tous, ROUVERTE réservée aux
        administrateurs du stock (``mg.stock.period.reopen``), CLOTUREE interdite.
        """
        now = maintenant()
        when = date_mouvement or now
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when > now + MARGE_DATE_FUTURE:
            raise AppError(
                f"La date du mouvement ({when:%d/%m/%Y}) ne peut pas être postérieure à aujourd'hui.",
                code="MVT_DATE_FUTURE",
            )
        await self.ensure_open_periode()
        d = when.date()
        cible = await self.db.scalar(
            select(MgStockPeriode)
            .where(MgStockPeriode.annee == d.year, MgStockPeriode.mois == d.month)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if cible is None:
            raise AppError(
                f"Aucune période de stock pour {periode_libelle(d.year, d.month)} : "
                "ce mois n'est pas géré dans le module.",
                code="PERIODE_INEXISTANTE",
            )
        if cible.statut == CLOTUREE:
            raise AppError(
                f"Période {cible.libelle} clôturée — mouvement interdit. Un administrateur du stock "
                "peut la rouvrir (motif obligatoire) pour régulariser.",
                code="PERIODE_CLOTUREE",
            )
        if cible.statut == ROUVERTE and not regularisation_autorisee:
            raise AppError(
                f"Période {cible.libelle} rouverte pour régularisation : saisie réservée aux "
                f"administrateurs du stock (permission {PERMISSION_REGULARISATION}).",
                status.HTTP_403_FORBIDDEN,
                code="PERIODE_ROUVERTE_RESERVEE",
            )
        return cible

    async def periodes_saisie(self, *, regularisation_autorisee: bool) -> list[dict]:
        """Périodes dans lesquelles l'utilisateur peut dater un mouvement (formulaires)."""
        await self.ensure_open_periode()
        statuts = STATUTS_SAISIE if regularisation_autorisee else frozenset({OUVERTE})
        rows = (
            await self.db.execute(
                select(MgStockPeriode)
                .where(MgStockPeriode.statut.in_(sorted(statuts)))
                .order_by(MgStockPeriode.date_debut)
            )
        ).scalars().all()
        return [
            {
                "id": str(p.id),
                "libelle": p.libelle,
                "statut": p.statut,
                "date_debut": p.date_debut.isoformat(),
                "date_fin": p.date_fin.isoformat(),
            }
            for p in rows
        ]

    # ------------------------------------------------------------------ soldes
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
        if solde.stock_final is not None and periode.statut != CLOTUREE:
            solde.stock_final = stock_final_from_solde(solde)
        delta = effet_mouvement(type_mouvement, qty)
        if delta:
            await self.propager_report(periode, article.id, delta)
        return solde

    async def propager_report(
        self, periode: MgStockPeriode, article_id: uuid.UUID, delta: Decimal
    ) -> list[MgStockPeriode]:
        """Décale de ``delta`` le stock initial de l'article dans toutes les périodes suivantes.

        Seul le report change : les mouvements des périodes suivantes restent intacts. Un solde
        absent vaut 0 et est créé. Après un comptage physique, l'écart d'inventaire est recalculé
        (le stock final compté ne bouge pas) ; sinon le stock final déjà figé suit le décalage.
        """
        suivantes = await self.periodes_suivantes(periode)
        if not suivantes or not delta:
            return suivantes
        soldes = {
            s.periode_id: s
            for s in (
                await self.db.execute(
                    select(MgStockSolde)
                    .where(
                        MgStockSolde.article_id == article_id,
                        MgStockSolde.periode_id.in_([p.id for p in suivantes]),
                    )
                    .with_for_update()
                )
            ).scalars().all()
        }
        for p in suivantes:
            solde = soldes.get(p.id)
            if solde is None:
                solde = MgStockSolde(
                    periode_id=p.id,
                    article_id=article_id,
                    stock_initial=Decimal("0"),
                    entrees=Decimal("0"),
                    sorties=Decimal("0"),
                    ajustements=Decimal("0"),
                    stock_theorique=Decimal("0"),
                )
                self.db.add(solde)
            solde.stock_initial = Decimal(solde.stock_initial or 0) + delta
            solde.stock_theorique = compute_theorique(
                solde.stock_initial, solde.entrees, solde.sorties, solde.ajustements
            )
            if solde.stock_physique is not None:
                solde.ecart = Decimal(solde.stock_physique) - Decimal(solde.stock_theorique)
            elif solde.stock_final is not None:
                solde.stock_final = Decimal(solde.stock_final) + delta
        await self.db.flush()
        return suivantes

    async def premier_solde_negatif(
        self,
        periode: MgStockPeriode,
        article_id: uuid.UUID,
        *,
        quand: datetime | None = None,
        effet: Decimal = Decimal("0"),
    ) -> tuple[date, Decimal] | None:
        """Rejoue chronologiquement le stock de l'article depuis le début de ``periode``.

        Le stock est contrôlé en fin de journée : la saisie ne porte que sur le jour, l'ordre
        des mouvements d'une même journée n'est pas significatif.
        Avec ``effet`` (mouvement à insérer à ``quand``), seuls les jours à partir de ``quand`` comptent.
        Renvoie le premier jour où le stock serait négatif, ou ``None``.
        """
        periodes = [periode, *await self.periodes_suivantes(periode)]
        ids = [p.id for p in periodes]
        soldes = {
            s.periode_id: s
            for s in (
                await self.db.execute(
                    select(MgStockSolde).where(
                        MgStockSolde.article_id == article_id, MgStockSolde.periode_id.in_(ids)
                    )
                )
            ).scalars().all()
        }
        par_periode: dict[uuid.UUID, list[MgStockMouvement]] = {i: [] for i in ids}
        for m in (
            await self.db.execute(
                select(MgStockMouvement)
                .where(MgStockMouvement.article_id == article_id, MgStockMouvement.periode_id.in_(ids))
                .order_by(MgStockMouvement.date_mouvement, MgStockMouvement.created_at)
            )
        ).scalars().all():
            par_periode[m.periode_id].append(m)

        depuis = quand.date() if quand is not None and effet else None
        for index, p in enumerate(periodes):
            solde = soldes.get(p.id)
            courant = Decimal(solde.stock_initial if solde else 0)
            if index > 0 and depuis is not None:
                courant += effet
            # (instant, ordre, quantité inventoriée ou None, variation) ; le mouvement inséré suit ceux du même instant.
            points: list[tuple[datetime, int, Decimal | None, Decimal]] = []
            for m in par_periode[p.id]:
                if m.type_mouvement == "INVENTAIRE":
                    points.append((m.date_mouvement, 0, Decimal(m.quantite or 0), Decimal("0")))
                else:
                    points.append((m.date_mouvement, 0, None, effet_mouvement(m.type_mouvement, m.quantite)))
            if index == 0 and depuis is not None:
                points.append((quand, 1, None, effet))
                points.sort(key=lambda x: (x[0], x[1]))
            for i, (moment, _ordre, absolu, variation) in enumerate(points):
                courant = absolu if absolu is not None else courant + variation
                jour = moment.date()
                fin_de_journee = i + 1 == len(points) or points[i + 1][0].date() != jour
                if fin_de_journee and courant < 0 and (depuis is None or jour >= depuis):
                    return jour, courant
            if not points and index > 0 and depuis is not None and courant < 0:
                return p.date_debut, courant
        return None

    async def verifier_historique_positif(
        self, periode: MgStockPeriode, article: MgArticle, quand: datetime, effet: Decimal
    ) -> None:
        """Refuse un mouvement qui rendrait le stock négatif à une date déjà passée."""
        if effet >= 0:
            return
        negatif = await self.premier_solde_negatif(periode, article.id, quand=quand, effet=effet)
        if negatif is not None:
            jour, valeur = negatif
            raise AppError(
                f"Opération refusée : le stock de {article.code} deviendrait négatif le "
                f"{jour:%d/%m/%Y} ({format_qty(valeur)}) compte tenu des mouvements déjà enregistrés "
                "après cette date.",
                code="STOCK_NEGATIF_HISTORIQUE",
            )

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
        """Reconstruit les soldes manquants à partir de stock_actuel et des mouvements du mois.

        Valable pour la dernière période seulement : ``stock_actuel`` inclut les périodes suivantes.
        """
        if await self._a_des_suivantes(periode):
            return 0
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
                        MgStockMouvement.type_mouvement.in_(TYPES_SOLDE),
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

    # -------------------------------------------------------------- sérialisation
    def serialize_periode(
        self,
        periode: MgStockPeriode,
        *,
        extras: dict | None = None,
        noms: dict[uuid.UUID, str] | None = None,
    ) -> dict:
        noms = noms or {}
        data = {
            "id": periode.id,
            "annee": periode.annee,
            "mois": periode.mois,
            "libelle": periode.libelle,
            "date_debut": periode.date_debut,
            "date_fin": periode.date_fin,
            "statut": periode.statut,
            "statut_libelle": STATUT_LIBELLES.get(periode.statut, periode.statut),
            "agence_id": periode.agence_id,
            "periode_precedente_id": periode.periode_precedente_id,
            "premiere_cloture_at": getattr(periode, "premiere_cloture_at", None),
            "premiere_cloture_par": noms.get(getattr(periode, "premiere_cloture_by", None)),
            "cloture_at": periode.cloture_at,
            "cloture_par": noms.get(periode.cloture_by),
            "reopen_at": periode.reopen_at,
            "reopen_par": noms.get(periode.reopen_by),
            "reopen_motif": periode.reopen_motif,
            "nb_reouvertures": getattr(periode, "nb_reouvertures", 0) or 0,
        }
        if extras:
            data.update(extras)
        return data

    async def noms_utilisateurs(self, periodes: list[MgStockPeriode]) -> dict[uuid.UUID, str]:
        ids = {
            i
            for p in periodes
            for i in (getattr(p, "premiere_cloture_by", None), p.cloture_by, p.reopen_by)
            if i
        }
        if not ids:
            return {}
        rows = (await self.db.execute(select(User.id, User.full_name).where(User.id.in_(list(ids))))).all()
        return {i: nom for i, nom in rows}

    async def serialize_periodes(self, periodes: list[MgStockPeriode]) -> list[dict]:
        noms = await self.noms_utilisateurs(periodes)
        return [self.serialize_periode(p, noms=noms) for p in periodes]

    # --------------------------------------------------------------- historique
    async def _evenement(
        self,
        periode: MgStockPeriode,
        action: str,
        user: User | None,
        *,
        resultat: str = "SUCCES",
        statut_avant: str | None = None,
        statut_apres: str | None = None,
        motif: str | None = None,
        details: dict | None = None,
    ) -> MgStockPeriodeEvenement:
        evt = MgStockPeriodeEvenement(
            periode_id=periode.id,
            action=action,
            resultat=resultat,
            statut_avant=statut_avant,
            statut_apres=statut_apres,
            motif=motif,
            user_id=user.id if user else None,
            user_nom=user.full_name if user else None,
            details=details,
        )
        self.db.add(evt)
        await self.db.flush()
        return evt

    async def journaliser_echec(
        self, periode_id: uuid.UUID, action: str, user: User | None, *, motif: str | None, erreur: str
    ) -> bool:
        """Trace un refus (permission, contrôle bloquant…) ; à appeler après rollback de l'opération."""
        periode = await self.db.get(MgStockPeriode, periode_id)
        if periode is None:
            return False
        await self._evenement(
            periode,
            action,
            user,
            resultat="ECHEC",
            statut_avant=periode.statut,
            statut_apres=periode.statut,
            motif=(motif or "").strip() or None,
            details={"erreur": erreur},
        )
        return True

    async def historique(self, periode_id: uuid.UUID) -> list[dict]:
        await self.get_periode(periode_id)
        rows = (
            await self.db.execute(
                select(MgStockPeriodeEvenement)
                .where(MgStockPeriodeEvenement.periode_id == periode_id)
                .order_by(MgStockPeriodeEvenement.created_at.desc())
            )
        ).scalars().all()
        out = []
        for e in rows:
            details = dict(e.details or {})
            instantane = details.pop("instantane", None)
            if instantane is not None:
                details["articles_reference"] = len(instantane)
            out.append(
                {
                    "id": e.id,
                    "action": e.action,
                    "resultat": e.resultat,
                    "statut_avant": e.statut_avant,
                    "statut_apres": e.statut_apres,
                    "motif": e.motif,
                    "user_id": e.user_id,
                    "user_nom": e.user_nom,
                    "created_at": e.created_at,
                    "details": details,
                }
            )
        return out

    async def _derniere_reouverture(self, periode: MgStockPeriode) -> MgStockPeriodeEvenement | None:
        return await self.db.scalar(
            select(MgStockPeriodeEvenement)
            .where(
                MgStockPeriodeEvenement.periode_id == periode.id,
                MgStockPeriodeEvenement.action == "REOUVERTURE",
                MgStockPeriodeEvenement.resultat == "SUCCES",
            )
            .order_by(MgStockPeriodeEvenement.created_at.desc())
            .limit(1)
        )

    # -------------------------------------------------------------- instantané
    async def _derniers_theoriques(self, article_ids: set[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
        """Stock théorique de chaque article dans sa période la plus récente (fin de chaîne)."""
        if not article_ids:
            return {}
        rang = (
            func.row_number()
            .over(partition_by=MgStockSolde.article_id, order_by=MgStockPeriode.date_debut.desc())
            .label("rang")
        )
        sub = (
            select(MgStockSolde.article_id, MgStockSolde.stock_theorique, rang)
            .join(MgStockPeriode, MgStockPeriode.id == MgStockSolde.periode_id)
            .where(MgStockSolde.article_id.in_(list(article_ids)))
            .subquery()
        )
        rows = (await self.db.execute(select(sub.c.article_id, sub.c.stock_theorique).where(sub.c.rang == 1))).all()
        return {a: Decimal(t or 0) for a, t in rows}

    async def _ecarts_chaine(self, article_ids: set[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
        """Stock actuel − fin de chaîne des soldes ; doit rester constant pendant une régularisation."""
        if not article_ids:
            return {}
        fins = await self._derniers_theoriques(article_ids)
        actuels = {
            a: Decimal(s or 0)
            for a, s in (
                await self.db.execute(
                    select(MgArticle.id, MgArticle.stock_actuel).where(MgArticle.id.in_(list(article_ids)))
                )
            ).all()
        }
        return {a: actuels.get(a, Decimal("0")) - fins.get(a, Decimal("0")) for a in article_ids}

    async def _soldes(self, periode: MgStockPeriode, *, for_update: bool = False) -> list[MgStockSolde]:
        stmt = select(MgStockSolde).where(MgStockSolde.periode_id == periode.id)
        if for_update:
            stmt = stmt.with_for_update()
        return list((await self.db.execute(stmt)).scalars().all())

    async def instantane(self, periode: MgStockPeriode) -> dict[str, dict]:
        """Référence prise à la réouverture : stock final, écart d'inventaire et écart de chaîne."""
        soldes = await self._soldes(periode)
        chaine = await self._ecarts_chaine({s.article_id for s in soldes})
        return {
            str(s.article_id): {
                "final": str(stock_final_from_solde(s)),
                "theorique": str(compute_theorique(s.stock_initial, s.entrees, s.sorties, s.ajustements)),
                "ecart": None if s.ecart is None else str(s.ecart),
                "chaine": str(chaine.get(s.article_id, Decimal("0"))),
            }
            for s in soldes
        }

    # -------------------------------------------------------------- réouverture
    async def _inventaires_periode(self, periode: MgStockPeriode) -> list[MgInventaire]:
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
        if invs:
            return invs
        return list(
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

    async def _mouvements_par_periode(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not ids:
            return {}
        rows = (
            await self.db.execute(
                select(MgStockMouvement.periode_id, func.count())
                .where(MgStockMouvement.periode_id.in_(ids))
                .group_by(MgStockMouvement.periode_id)
            )
        ).all()
        return {i: int(n) for i, n in rows}

    async def preview_reouverture(self, periode_id: uuid.UUID) -> dict:
        """Conséquences d'une réouverture, affichées avant confirmation."""
        periode = await self.get_periode(periode_id)
        blocages: list[str] = []
        if periode.statut != CLOTUREE:
            blocages.append(f"{periode.libelle} n'est pas clôturée ({STATUT_LIBELLES.get(periode.statut)}).")
        autre = await self.db.scalar(
            select(MgStockPeriode).where(MgStockPeriode.statut == ROUVERTE, MgStockPeriode.id != periode.id)
        )
        if autre is not None:
            blocages.append(
                f"{autre.libelle} est déjà rouverte : clôturez-la de nouveau avant d'en rouvrir une autre."
            )
        suivantes = await self.periodes_suivantes(periode)
        mvts = await self._mouvements_par_periode([p.id for p in suivantes])
        soldes = await self._soldes(periode)
        invs = [i for i in await self._inventaires_periode(periode) if i.statut in INV_TERMINES]

        consequences = [
            f"Les mouvements datés de {periode.libelle} pourront être saisis par les administrateurs du stock ; "
            "les mouvements déjà enregistrés ne sont ni supprimés ni modifiés.",
            "Chaque régularisation met à jour immédiatement le stock actuel des articles concernés.",
        ]
        if suivantes:
            consequences.append(
                "Le stock initial des périodes suivantes ("
                + ", ".join(p.libelle for p in suivantes)
                + ") sera décalé exactement de la régularisation ; leurs mouvements restent inchangés."
            )
        if invs:
            consequences.append(
                f"{len(invs)} inventaire(s) ajusté(s) sur la période : une régularisation antérieure au comptage "
                "fera réapparaître un écart, à corriger par ajustement avant la nouvelle clôture."
            )
        if periode.cloture_at:
            consequences.append(
                f"La clôture du {periode.cloture_at:%d/%m/%Y %H:%M} reste dans l'historique de la période."
            )
        return {
            "periode": self.serialize_periode(periode, noms=await self.noms_utilisateurs([periode])),
            "peut_rouvrir": not blocages,
            "blocages": blocages,
            "consequences": consequences,
            "articles": len(soldes),
            "stock_final": float(sum((stock_final_from_solde(s) for s in soldes), Decimal("0"))),
            "inventaires_ajustes": len(invs),
            "periodes_suivantes": [
                {
                    "id": str(p.id),
                    "libelle": p.libelle,
                    "statut": p.statut,
                    "mouvements": mvts.get(p.id, 0),
                    "a_verifier": True,
                }
                for p in suivantes
            ],
        }

    async def rouvrir(self, periode_id: uuid.UUID, user: User, motif: str) -> tuple[MgStockPeriode, dict]:
        motif = (motif or "").strip()
        if len(motif) < 5:
            raise AppError(
                "Motif de réouverture obligatoire (5 caractères minimum).", code="MOTIF_OBLIGATOIRE"
            )
        await self.verrouiller()
        periode = await self.get_periode(periode_id, for_update=True)
        impact = await self.preview_reouverture(periode.id)
        if impact["blocages"]:
            raise AppError(" ".join(impact["blocages"]), status.HTTP_409_CONFLICT, code="REOUVERTURE_IMPOSSIBLE")
        reference = await self.instantane(periode)
        now = maintenant()
        periode.statut = ROUVERTE
        periode.reopen_at = now
        periode.reopen_by = user.id
        periode.reopen_motif = motif
        periode.nb_reouvertures = (periode.nb_reouvertures or 0) + 1
        await self._evenement(
            periode,
            "REOUVERTURE",
            user,
            statut_avant=CLOTUREE,
            statut_apres=ROUVERTE,
            motif=motif,
            details={
                "cloture_precedente_at": periode.cloture_at.isoformat() if periode.cloture_at else None,
                "periodes_suivantes": impact["periodes_suivantes"],
                "instantane": reference,
            },
        )
        await self.db.flush()
        return periode, impact

    # ------------------------------------------------------------------ clôture
    async def preview_cloture(self, periode_id: uuid.UUID) -> dict:
        periode = await self.get_periode(periode_id)
        await self.bootstrap_soldes(periode)
        soldes = await self._soldes(periode)
        invs = await self._inventaires_periode(periode)
        ouverts = [i for i in invs if i.statut in INV_OUVERTS]
        termines = [i for i in invs if i.statut in INV_TERMINES]
        with_ecart = sum(1 for s in soldes if s.ecart not in (None, Decimal("0")))

        controles: list[dict] = []
        avertissements: list[str] = []
        anterieures = (
            await self.db.execute(
                select(MgStockPeriode)
                .where(MgStockPeriode.date_debut < periode.date_debut, MgStockPeriode.statut != CLOTUREE)
                .order_by(MgStockPeriode.date_debut)
            )
        ).scalars().all()
        controles.append(
            _controle(
                "periodes_anterieures",
                "Périodes antérieures clôturées",
                not anterieures,
                (
                    "Clôturez d'abord " + ", ".join(p.libelle for p in anterieures)
                    if anterieures
                    else None
                ),
            )
        )
        controles.append(
            _controle(
                "inventaires_en_cours",
                "Aucun inventaire en cours",
                not ouverts,
                f"{len(ouverts)} inventaire(s) non clôturé(s)" if ouverts else None,
            )
        )
        obligatoire = await self._param_bool("inventaire_obligatoire")
        inventaire_ok = not (obligatoire and not termines and not periode.reopen_at)
        controles.append(
            _controle(
                "inventaire_obligatoire",
                "Inventaire mensuel réalisé",
                inventaire_ok,
                None if inventaire_ok else "Inventaire mensuel obligatoire non réalisé",
            )
        )

        regularisation = await self._controles_regularisation(periode, soldes) if periode.statut == ROUVERTE else None
        if regularisation:
            controles.extend(regularisation["controles"])
            avertissements.extend(regularisation["avertissements"])

        actifs = set(
            (await self.db.execute(select(MgArticle.id).where(MgArticle.is_active.is_(True)))).scalars().all()
        )
        stock_final = sum((stock_final_from_solde(s) for s in soldes if s.article_id in actifs), Decimal("0"))
        anomalies = [c["detail"] or c["libelle"] for c in controles if c["bloquant"]]
        suivantes = await self.periodes_suivantes(periode)
        return {
            "periode": self.serialize_periode(periode, noms=await self.noms_utilisateurs([periode])),
            "articles": len(soldes),
            "stock_final": float(stock_final),
            "articles_avec_ecarts": with_ecart,
            "ajustements": sum(1 for s in soldes if Decimal(s.ajustements or 0) != 0),
            "inventaires": len(invs),
            "inventaires_ouverts": len(ouverts),
            "controles": controles,
            "avertissements": avertissements,
            "anomalies": anomalies,
            "bloquant": bool(anomalies),
            "periode_suivante": (
                suivantes[0].libelle if suivantes else periode_libelle(*next_year_month(periode.annee, periode.mois))
            ),
            "regularisation": regularisation and {
                k: v for k, v in regularisation.items() if k not in {"controles", "avertissements"}
            },
        }

    async def _controles_regularisation(self, periode: MgStockPeriode, soldes: list[MgStockSolde]) -> dict:
        """Contrôles d'une période rouverte, par rapport à l'instantané pris à la réouverture."""
        evt = await self._derniere_reouverture(periode)
        reference: dict[str, dict] = ((evt.details or {}).get("instantane") if evt else None) or {}
        depuis = periode.reopen_at or (evt.created_at if evt else None)
        corrections = []
        if depuis is not None:
            corrections = list(
                (
                    await self.db.execute(
                        select(MgStockMouvement)
                        .where(MgStockMouvement.periode_id == periode.id, MgStockMouvement.created_at >= depuis)
                        .order_by(MgStockMouvement.date_mouvement, MgStockMouvement.created_at)
                    )
                ).scalars().all()
            )
        touches = {m.article_id for m in corrections}
        # Modifications / suppressions administrateur pendant la réouverture : stock final ≠ instantané.
        for s in soldes:
            ref = reference.get(str(s.article_id))
            if ref is not None and _dec(ref.get("final")) != stock_final_from_solde(s):
                touches.add(s.article_id)
        articles = {
            a.id: a
            for a in (
                await self.db.execute(
                    select(MgArticle).where(MgArticle.id.in_(list(touches | {s.article_id for s in soldes})))
                )
            ).scalars().all()
        }
        initiateurs = list({m.initiateur_id for m in corrections if m.initiateur_id})
        noms: dict[uuid.UUID, str] = {}
        if initiateurs:
            rows = (await self.db.execute(select(User.id, User.full_name).where(User.id.in_(initiateurs)))).all()
            noms = {i: n for i, n in rows}

        def code(article_id) -> str:
            a = articles.get(article_id)
            return a.code if a else str(article_id)

        controles: list[dict] = []
        avertissements: list[str] = []
        par_solde = {s.article_id: s for s in soldes}

        # 1. Soldes = somme des mouvements de la période (articles régularisés).
        incoherents = []
        if touches:
            sommes: dict[tuple, Decimal] = {
                (a, t): Decimal(q or 0)
                for a, t, q in (
                    await self.db.execute(
                        select(
                            MgStockMouvement.article_id,
                            MgStockMouvement.type_mouvement,
                            func.coalesce(func.sum(MgStockMouvement.quantite), 0),
                        )
                        .where(MgStockMouvement.periode_id == periode.id, MgStockMouvement.article_id.in_(list(touches)))
                        .group_by(MgStockMouvement.article_id, MgStockMouvement.type_mouvement)
                    )
                ).all()
            }
            for a in touches:
                s = par_solde.get(a)
                attendu = (
                    sommes.get((a, "ENTREE"), Decimal("0")),
                    sommes.get((a, "SORTIE"), Decimal("0")),
                    sommes.get((a, "AJUSTEMENT"), Decimal("0")),
                )
                reel = (
                    (Decimal(s.entrees or 0), Decimal(s.sorties or 0), Decimal(s.ajustements or 0))
                    if s
                    else (Decimal("0"),) * 3
                )
                if attendu != reel:
                    incoherents.append(code(a))
        controles.append(
            _controle(
                "soldes_mouvements",
                "Soldes conformes aux mouvements de la période",
                not incoherents,
                ("Soldes différents des mouvements : " + ", ".join(sorted(incoherents))) if incoherents else None,
            )
        )

        # 2. Stock jamais négatif, date par date, depuis le début de la période.
        negatifs = []
        for a in sorted(touches, key=code):
            neg = await self.premier_solde_negatif(periode, a)
            if neg is not None:
                negatifs.append(f"{code(a)} le {neg[0]:%d/%m/%Y} ({format_qty(neg[1])})")
        controles.append(
            _controle(
                "historique_positif",
                "Stock jamais négatif après régularisation",
                not negatifs,
                ("Stock négatif : " + " ; ".join(negatifs)) if negatifs else None,
            )
        )

        # 3. Écarts d'inventaire de la période inchangés (sinon ajustement à saisir).
        ecarts = []
        for s in soldes:
            ref = reference.get(str(s.article_id))
            if s.stock_physique is None or ref is None:
                continue
            if _dec(ref.get("ecart")) != (None if s.ecart is None else Decimal(s.ecart)):
                ecarts.append(
                    f"{code(s.article_id)} (écart {format_qty(_dec(ref.get('ecart')) or 0)} → {format_qty(s.ecart or 0)})"
                )
        controles.append(
            _controle(
                "ecarts_inventaire",
                "Écarts d'inventaire inchangés",
                not ecarts,
                (
                    "Régularisation antérieure au comptage — saisissez un ajustement : " + " ; ".join(ecarts)
                    if ecarts
                    else None
                ),
            )
        )

        # 4. Cohérence stock actuel ↔ fin de chaîne des soldes (aucune dérive introduite).
        chaine = await self._ecarts_chaine({uuid.UUID(k) for k in reference})
        derives = [
            code(a)
            for a, valeur in chaine.items()
            if _dec(reference[str(a)].get("chaine")) != valeur
        ]
        controles.append(
            _controle(
                "coherence_stock_actuel",
                "Stock actuel cohérent avec les soldes reportés",
                not derives,
                ("Stock actuel et soldes divergent pour : " + ", ".join(sorted(derives))) if derives else None,
            )
        )

        # 5. Doublons probables (avertissement) : même article, type, quantité et jour.
        doublons = []
        for m in corrections:
            jour = m.date_mouvement.date()
            autre = await self.db.scalar(
                select(MgStockMouvement.reference).where(
                    MgStockMouvement.id != m.id,
                    MgStockMouvement.article_id == m.article_id,
                    MgStockMouvement.type_mouvement == m.type_mouvement,
                    MgStockMouvement.quantite == m.quantite,
                    func.date(MgStockMouvement.date_mouvement) == jour,
                ).limit(1)
            )
            if autre:
                doublons.append(f"{m.reference} ≈ {autre}")
        controles.append(
            _controle(
                "doublons",
                "Aucun doublon probable",
                not doublons,
                ("À vérifier : " + " ; ".join(doublons)) if doublons else None,
                bloquant=False,
            )
        )
        if doublons:
            avertissements.append("Doublons probables : " + " ; ".join(doublons))

        # Corrections, articles modifiés, périodes suivantes impactées.
        delta_article: dict[uuid.UUID, Decimal] = {}
        for m in corrections:
            delta_article[m.article_id] = delta_article.get(m.article_id, Decimal("0")) + effet_mouvement(
                m.type_mouvement, m.quantite
            )
        modifies = []
        for s in soldes:
            ref = reference.get(str(s.article_id))
            avant = _dec(ref.get("final")) if ref else None
            apres = stock_final_from_solde(s)
            if avant is None and s.article_id not in touches:
                continue
            if avant != apres or s.article_id in touches:
                modifies.append(
                    {
                        "article_id": str(s.article_id),
                        "article_code": code(s.article_id),
                        "article_designation": articles[s.article_id].designation if s.article_id in articles else None,
                        "stock_final_avant": float(avant) if avant is not None else None,
                        "stock_final_apres": float(apres),
                        "variation": float(apres - (avant or Decimal("0"))),
                        "variation_mouvements": float(delta_article.get(s.article_id, Decimal("0"))),
                    }
                )
        suivantes = await self.periodes_suivantes(periode)
        mvts = await self._mouvements_par_periode([p.id for p in suivantes])
        impactes = [a for a, d in delta_article.items() if d]
        physiques_suivants = 0
        if impactes and suivantes:
            physiques_suivants = int(
                await self.db.scalar(
                    select(func.count())
                    .select_from(MgStockSolde)
                    .where(
                        MgStockSolde.periode_id.in_([p.id for p in suivantes]),
                        MgStockSolde.article_id.in_(impactes),
                        MgStockSolde.stock_physique.is_not(None),
                    )
                )
                or 0
            )
        if physiques_suivants:
            avertissements.append(
                f"{physiques_suivants} comptage(s) physique(s) des périodes suivantes concernent des articles "
                "régularisés : leur écart d'inventaire a été recalculé, à vérifier."
            )
        return {
            "controles": controles,
            "avertissements": avertissements,
            "motif": periode.reopen_motif,
            "reouverte_le": periode.reopen_at,
            "reouverte_par": (await self.noms_utilisateurs([periode])).get(periode.reopen_by),
            "cloture_precedente_at": (evt.details or {}).get("cloture_precedente_at") if evt else None,
            "corrections": [
                {
                    "id": str(m.id),
                    "reference": m.reference,
                    "type_mouvement": m.type_mouvement,
                    "article_code": code(m.article_id),
                    "quantite": float(m.quantite),
                    "date_mouvement": m.date_mouvement,
                    "date_enregistrement": m.created_at,
                    "saisi_par": noms.get(m.initiateur_id),
                }
                for m in corrections
            ],
            "articles_modifies": modifies,
            "periodes_suivantes": [
                {
                    "id": str(p.id),
                    "libelle": p.libelle,
                    "statut": p.statut,
                    "mouvements": mvts.get(p.id, 0),
                    "articles_impactes": len(impactes),
                    "variation_stock_initial": float(sum((delta_article[a] for a in impactes), Decimal("0"))),
                }
                for p in suivantes
            ],
        }

    async def cloturer(self, periode_id: uuid.UUID, user: User) -> dict:
        await self.verrouiller()
        periode = await self.get_periode(periode_id, for_update=True)
        if periode.statut == CLOTUREE:
            raise AppError("Période déjà clôturée.", status.HTTP_409_CONFLICT, code="PERIODE_DEJA_CLOTUREE")
        preview = await self.preview_cloture(periode.id)
        if preview["bloquant"]:
            raise AppError(
                "Clôture bloquée : " + " ; ".join(preview["anomalies"]),
                status.HTTP_409_CONFLICT,
                code="CLOTURE_BLOQUEE",
            )
        soldes = await self._soldes(periode, for_update=True)
        statut_avant = periode.statut
        now = maintenant()
        periode.statut = CLOTUREE
        periode.cloture_at = now
        periode.cloture_by = user.id
        if periode.premiere_cloture_at is None:
            periode.premiere_cloture_at = now
            periode.premiere_cloture_by = user.id
        for solde in soldes:
            solde.stock_theorique = compute_theorique(
                solde.stock_initial, solde.entrees, solde.sorties, solde.ajustements
            )
            solde.stock_final = stock_final_from_solde(solde)

        ny, nm = next_year_month(periode.annee, periode.mois)
        suivante = await self.db.scalar(
            select(MgStockPeriode).where(MgStockPeriode.annee == ny, MgStockPeriode.mois == nm)
        )
        reports = 0
        if suivante is None:
            suivante = await self._create_periode(ny, nm, user=user, precedente=periode)
        else:
            suivante.periode_precedente_id = periode.id
            initiaux = {
                s.article_id: Decimal(s.stock_initial or 0)
                for s in await self._soldes(suivante, for_update=True)
            }
            for solde in soldes:
                delta = Decimal(solde.stock_final or 0) - initiaux.get(solde.article_id, Decimal("0"))
                if delta:
                    await self.propager_report(periode, solde.article_id, delta)
                    reports += 1
        await self.db.flush()
        regularisation = preview.get("regularisation") or {}
        await self._evenement(
            periode,
            "RECLOTURE" if statut_avant == ROUVERTE else "CLOTURE",
            user,
            statut_avant=statut_avant,
            statut_apres=CLOTUREE,
            motif=periode.reopen_motif if statut_avant == ROUVERTE else None,
            details={
                "controles": preview["controles"],
                "avertissements": preview["avertissements"],
                "articles": len(soldes),
                "stock_final": preview["stock_final"],
                "reports_corriges": reports,
                "corrections": len(regularisation.get("corrections") or []),
                "articles_modifies": regularisation.get("articles_modifies") or [],
                "periodes_suivantes": regularisation.get("periodes_suivantes") or [],
            },
        )
        return {
            "periode": self.serialize_periode(periode),
            "periode_suivante": self.serialize_periode(suivante),
            "articles": len(soldes),
            "stock_final": preview["stock_final"],
            "reports_corriges": reports,
            "controles": preview["controles"],
            "regularisation": regularisation or None,
        }

    async def cloture_alerte(self, periode: MgStockPeriode | None) -> tuple[str | None, str | None]:
        if periode is None:
            return None, None
        if periode.statut == ROUVERTE:
            return (
                "periode_rouverte",
                f"Période {periode.libelle} rouverte — régularisation en cours, à clôturer de nouveau",
            )
        today = aujourdhui()
        invs = await self._inventaires_periode(periode)
        clotures = [i for i in invs if i.statut in INV_TERMINES]
        en_cours = [i for i in invs if i.statut in INV_OUVERTS]

        if periode.statut == CLOTUREE:
            suivante = await self.db.scalar(
                select(MgStockPeriode).where(MgStockPeriode.periode_precedente_id == periode.id)
            )
            if suivante and suivante.statut == OUVERTE:
                return "periode_suivante_ouverte", f"Clôture terminée — {suivante.libelle} ouverte"
            return "cloture_terminee", f"Clôture {periode.libelle} terminée"

        fin_proche = today >= periode.date_fin or (
            today.year == periode.annee and today.month == periode.mois and today.day >= 25
        )
        if clotures and periode.statut == OUVERTE:
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
        now = maintenant()
        periode = MgStockPeriode(
            annee=year,
            mois=month,
            libelle=periode_libelle(year, month),
            date_debut=debut,
            date_fin=fin,
            statut=OUVERTE,
            periode_precedente_id=precedente.id if precedente else None,
            opened_at=now,
            opened_by=user.id if user else None,
            nb_reouvertures=0,
        )
        self.db.add(periode)
        await self.db.flush()
        if precedente is not None:
            prev_soldes = await self._soldes(precedente)
            for solde in prev_soldes:
                final = stock_final_from_solde(solde)
                if solde.stock_final is None and precedente.statut == CLOTUREE:
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
                )
                .join(MgArticle, MgArticle.id == MgStockSolde.article_id)
                .where(MgStockSolde.periode_id == periode.id, MgArticle.is_active.is_(True))
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
