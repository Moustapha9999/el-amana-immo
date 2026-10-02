"""Service Stock & Fournitures (Moyens Généraux)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import Agence, User
from app.models.mg_stock import (
    MgArticle,
    MgArticleFamille,
    MgDemandeFourniture,
    MgDemandeFournitureLigne,
    MgInventaire,
    MgInventaireLigne,
    MgStockMouvement,
    MgStockParametre,
    MgStockPeriode,
    MgStockSolde,
)
from app.core.exceptions import AppError
from app.schemas.nombres import as_qty
from app.services.mg_stock_periodes import MgStockPeriodeService
from app.schemas.mg_stock import (
    ArticleCreate,
    ArticleUpdate,
    DemandeCreate,
    DemandeLigneIn,
    DemandeUpdate,
    FamilleCreate,
    FamilleUpdate,
    MouvementCreate,
    MouvementUpdate,
    ParametreCreate,
    ParametreUpdate,
    ReceptionBcIn,
)

MOUVEMENT_TYPES = frozenset({"ENTREE", "SORTIE", "AJUSTEMENT", "INVENTAIRE"})
# Mouvements pilotés par un workflow : quantité / suppression via l'opération d'origine.
WORKFLOW_SOURCES = {
    "demande_fourniture": "une demande de fournitures",
    "mg_employee_request": "une demande employé",
    "inventaire": "un inventaire",
    "achat_reception": "une réception de bon de commande",
}
MOUVEMENTS_EDITABLES = frozenset({"ENTREE", "SORTIE", "AJUSTEMENT"})
DEMANDE_STATUTS = frozenset(
    {
        "BROUILLON",
        "SOUMIS",
        "VISA_AGENCE",
        "VISA_MG",
        "PREPARATION",
        "SERVIE",
        "ARCHIVEE",
        "ACCORDEE",
        "CLOTUREE",
        "REJETEE",
        "ANNULEE",
    }
)


class MgStockService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def niveau_stock(article: MgArticle) -> str:
        qty = article.stock_actuel or Decimal("0")
        if qty <= 0:
            return "epuise"
        if qty <= (article.stock_min or Decimal("0")):
            return "faible"
        return "normal"

    async def list_familles(self) -> list[MgArticleFamille]:
        q = (
            select(MgArticleFamille)
            .where(MgArticleFamille.is_active.is_(True), MgArticleFamille.deleted_at.is_(None))
            .order_by(MgArticleFamille.sort_order, MgArticleFamille.libelle)
        )
        return list((await self.db.execute(q)).scalars().all())

    async def create_famille(self, data: FamilleCreate) -> MgArticleFamille:
        code = data.code.strip().upper()
        exists = await self.db.scalar(
            select(MgArticleFamille.id).where(MgArticleFamille.code == code)
        )
        if exists:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Code famille déjà utilisé")
        famille = MgArticleFamille(
            code=code,
            libelle=data.libelle.strip(),
            sort_order=data.sort_order or 0,
        )
        self.db.add(famille)
        await self.db.commit()
        await self.db.refresh(famille)
        return famille

    async def update_famille(self, famille_id: uuid.UUID, data: FamilleUpdate) -> MgArticleFamille:
        famille = await self.db.get(MgArticleFamille, famille_id)
        if famille is None or famille.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Famille introuvable")
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            if key == "is_active":
                continue
            setattr(famille, key, value)
        if data.is_active is False:
            famille.deleted_at = datetime.now(timezone.utc)
            famille.is_active = False
        elif data.is_active is True:
            famille.deleted_at = None
            famille.is_active = True
        await self.db.commit()
        await self.db.refresh(famille)
        return famille

    async def list_articles(
        self,
        *,
        q: str | None = None,
        famille_id: uuid.UUID | None = None,
        agence_id: uuid.UUID | None = None,
        bas_stock: bool = False,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[MgArticle], int]:
        filters = [MgArticle.is_active.is_(True), MgArticle.deleted_at.is_(None)]
        if q:
            like = f"%{q.strip()}%"
            filters.append((MgArticle.code.ilike(like)) | (MgArticle.designation.ilike(like)))
        if famille_id:
            filters.append(MgArticle.famille_id == famille_id)
        if agence_id:
            filters.append(MgArticle.agence_id == agence_id)
        if bas_stock:
            filters.append(MgArticle.stock_actuel <= MgArticle.stock_min)
        total = int(
            (await self.db.scalar(select(func.count()).select_from(MgArticle).where(*filters))) or 0
        )
        page = max(1, page)
        size = max(1, min(size, 500))
        stmt = (
            select(MgArticle)
            .where(*filters)
            .order_by(MgArticle.code)
            .offset((page - 1) * size)
            .limit(size)
        )
        return list((await self.db.execute(stmt)).scalars().all()), total

    async def create_article(self, data: ArticleCreate, user: User) -> MgArticle:
        exists = await self.db.scalar(select(MgArticle.id).where(MgArticle.code == data.code.strip()))
        if exists:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Code article déjà utilisé")
        famille = await self.db.get(MgArticleFamille, data.famille_id)
        if famille is None or not famille.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Famille invalide")
        article = MgArticle(
            code=data.code.strip().upper(),
            designation=data.designation.strip(),
            famille_id=data.famille_id,
            uom=data.uom or "U",
            stockable=bool(data.stockable),
            reference=(data.reference.strip() if data.reference else None),
            sous_famille=(data.sous_famille.strip() if data.sous_famille else None),
            stock_actuel=Decimal("0"),
            stock_min=data.stock_min,
            stock_max=data.stock_max,
            agence_id=data.agence_id,
            emplacement=data.emplacement,
            fournisseur_habituel=(
                data.fournisseur_habituel.strip() if data.fournisseur_habituel else None
            ),
        )
        self.db.add(article)
        await self.db.flush()
        if data.stock_initial and data.stock_initial > 0:
            await self._apply_mouvement(
                article=article,
                type_mouvement="ENTREE",
                quantite=data.stock_initial,
                agence_id=data.agence_id,
                initiateur=user,
                motif="Stock initial",
            )
        await self.db.commit()
        await self.db.refresh(article)
        return article

    async def get_article(self, article_id: uuid.UUID) -> MgArticle:
        article = await self.db.get(MgArticle, article_id)
        if article is None or article.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Article introuvable")
        return article

    async def get_article_fiche(self, article_id: uuid.UUID) -> dict:
        article = await self.get_article(article_id)
        famille = await self.db.get(MgArticleFamille, article.famille_id)
        agence_libelle = None
        if article.agence_id:
            ag = await self.db.get(Agence, article.agence_id)
            agence_libelle = ag.libelle if ag else None

        sums = (
            await self.db.execute(
                select(
                    MgStockMouvement.type_mouvement,
                    func.coalesce(func.sum(MgStockMouvement.quantite), 0),
                    func.count(MgStockMouvement.id),
                )
                .where(MgStockMouvement.article_id == article_id)
                .group_by(MgStockMouvement.type_mouvement)
            )
        ).all()
        by_type = {row[0]: (Decimal(row[1] or 0), int(row[2] or 0)) for row in sums}

        stock_initial = Decimal("0")
        init_row = await self.db.scalar(
            select(func.coalesce(func.sum(MgStockMouvement.quantite), 0)).where(
                MgStockMouvement.article_id == article_id,
                MgStockMouvement.type_mouvement == "ENTREE",
                MgStockMouvement.motif == "Stock initial",
            )
        )
        if init_row is not None:
            stock_initial = Decimal(init_row or 0)

        return {
            "article": article,
            "famille_libelle": famille.libelle if famille else None,
            "agence_libelle": agence_libelle,
            "stock_initial": stock_initial,
            "total_entrees": by_type.get("ENTREE", (Decimal("0"), 0))[0],
            "total_sorties": by_type.get("SORTIE", (Decimal("0"), 0))[0],
            "total_ajustements": by_type.get("AJUSTEMENT", (Decimal("0"), 0))[0],
            "total_inventaires": by_type.get("INVENTAIRE", (Decimal("0"), 0))[1],
        }

    async def update_article(
        self, article_id: uuid.UUID, data: ArticleUpdate, user: User | None = None
    ) -> MgArticle:
        article = await self.db.scalar(select(MgArticle).where(MgArticle.id == article_id).with_for_update())
        if article is None or article.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Article introuvable")
        payload = data.model_dump(exclude_unset=True)
        stock_cible = payload.pop("stock_actuel", None)
        motif = (payload.pop("motif_correction", None) or "").strip()
        if "code" in payload:
            code = (payload["code"] or "").strip().upper()
            if not code:
                raise AppError("Le code article est obligatoire.", code="ARTICLE_CODE_REQUIS")
            if code != article.code:
                pris = await self.db.scalar(
                    select(MgArticle.id).where(func.upper(MgArticle.code) == code, MgArticle.id != article.id)
                )
                if pris is not None:
                    raise AppError(f"Le code {code} est déjà utilisé par un autre article.", code="ARTICLE_CODE_PRIS")
            payload["code"] = code
        for key, value in payload.items():
            setattr(article, key, value)
        if stock_cible is not None:
            ecart = Decimal(stock_cible) - Decimal(article.stock_actuel or 0)
            if ecart != 0:
                await self._apply_mouvement(
                    article=article,
                    type_mouvement="AJUSTEMENT",
                    quantite=ecart,
                    agence_id=article.agence_id,
                    initiateur=user,
                    motif=motif or "Correction du stock depuis la fiche article",
                )
        if data.is_active is False:
            article.deleted_at = datetime.now(timezone.utc)
            article.is_active = False
        elif data.is_active is True:
            article.deleted_at = None
            article.is_active = True
        await self.db.commit()
        await self.db.refresh(article)
        return article

    async def create_mouvement(self, data: MouvementCreate, user: User) -> MgStockMouvement:
        t = data.type_mouvement.strip().upper()
        if t not in MOUVEMENT_TYPES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Type de mouvement invalide")
        article = await self.db.scalar(
            select(MgArticle)
            .where(MgArticle.id == data.article_id, MgArticle.deleted_at.is_(None))
            .with_for_update()
        )
        if article is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Article introuvable")
        if t in {"ENTREE", "SORTIE"} and data.quantite <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Quantité invalide")
        if t == "AJUSTEMENT" and data.quantite == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ajustement nul")
        mvt = await self._apply_mouvement(
            article=article,
            type_mouvement=t,
            quantite=data.quantite,
            agence_id=data.agence_id or article.agence_id,
            initiateur=user,
            motif=data.motif,
            observation=data.observation,
            departement=data.departement,
            date_mouvement=data.date_mouvement,
            source_type=data.source_type,
            source_id=data.source_id,
            allow_negative=bool(data.allow_negative),
        )
        await self.db.commit()
        await self.db.refresh(mvt)
        return mvt

    @staticmethod
    def mouvement_snapshot(mvt: MgStockMouvement) -> dict:
        return {
            "reference": mvt.reference,
            "article_id": str(mvt.article_id) if mvt.article_id else None,
            "type_mouvement": mvt.type_mouvement,
            "date_mouvement": mvt.date_mouvement.isoformat() if mvt.date_mouvement else None,
            "quantite": str(mvt.quantite),
            "agence_id": str(mvt.agence_id) if mvt.agence_id else None,
            "departement": mvt.departement,
            "motif": mvt.motif,
            "observation": mvt.observation,
        }

    async def _mouvement_locked(self, mvt_id: uuid.UUID) -> tuple[MgStockMouvement, MgStockPeriode | None]:
        mvt = await self.db.scalar(
            select(MgStockMouvement).where(MgStockMouvement.id == mvt_id).with_for_update()
        )
        if mvt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mouvement introuvable")
        periode = await self.db.get(MgStockPeriode, mvt.periode_id) if mvt.periode_id else None
        return mvt, periode

    @staticmethod
    def _assert_quantite_modifiable(mvt: MgStockMouvement, periode: MgStockPeriode | None, verbe: str) -> None:
        participe = {"modifier": "modifiées", "supprimer": "supprimées"}.get(verbe, verbe)
        origine = WORKFLOW_SOURCES.get(mvt.source_type or "")
        if origine:
            raise AppError(
                f"Mouvement généré par {origine} : impossible de le {verbe} ici. "
                "Passez par l’opération d’origine.",
                code="MVT_WORKFLOW",
            )
        if mvt.type_mouvement not in MOUVEMENTS_EDITABLES:
            raise AppError(
                f"Un mouvement d’inventaire fixe le stock : il ne peut pas être {participe[:-1]}. "
                "Saisissez un ajustement.",
                code="MVT_TYPE_VERROUILLE",
            )
        if periode is not None and periode.statut == "CLOTUREE":
            raise AppError(
                f"Période {periode.libelle} clôturée : impossible de {verbe} ce mouvement. "
                "Rouvrez la période depuis les paramètres si nécessaire.",
                code="PERIODE_CLOTUREE",
            )

    @staticmethod
    def _effet(type_mouvement: str, quantite: Decimal) -> Decimal:
        return -quantite if type_mouvement == "SORTIE" else quantite

    async def _appliquer_effet(
        self, mvt: MgStockMouvement, periode: MgStockPeriode | None, delta_qty: Decimal
    ) -> None:
        article = await self.db.scalar(
            select(MgArticle).where(MgArticle.id == mvt.article_id).with_for_update()
        )
        if article is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Article introuvable")
        if not getattr(article, "stockable", True):
            raise AppError(f"Article {article.code} non stockable.", code="ARTICLE_NON_STOCKABLE")
        current = Decimal(article.stock_actuel or 0)
        new_stock = current + self._effet(mvt.type_mouvement, delta_qty)
        if new_stock < 0:
            raise AppError(
                f"Opération refusée : le stock de {article.code} deviendrait négatif "
                f"({as_qty(new_stock)}).",
                code="STOCK_NEGATIF",
            )
        article.stock_actuel = new_stock
        if periode is not None:
            await MgStockPeriodeService(self.db).touch_solde(periode, article, mvt.type_mouvement, delta_qty)

    async def update_mouvement(
        self, mvt_id: uuid.UUID, data: MouvementUpdate
    ) -> tuple[MgStockMouvement, dict]:
        mvt, periode = await self._mouvement_locked(mvt_id)
        before = self.mouvement_snapshot(mvt)
        fields = data.model_dump(exclude_unset=True)

        nouvelle_date = fields.get("date_mouvement")
        if nouvelle_date is not None:
            if nouvelle_date.tzinfo is None:
                nouvelle_date = nouvelle_date.replace(tzinfo=timezone.utc)
            jour = nouvelle_date.date()
            if periode is not None and not (periode.date_debut <= jour <= periode.date_fin):
                raise AppError(
                    f"La date doit rester dans la période {periode.libelle} "
                    f"({periode.date_debut:%d/%m/%Y} – {periode.date_fin:%d/%m/%Y}).",
                    code="MVT_HORS_PERIODE",
                )
            mvt.date_mouvement = nouvelle_date

        ancienne_qty = Decimal(mvt.quantite)
        nouvelle_qty = Decimal(fields["quantite"]) if fields.get("quantite") is not None else ancienne_qty
        nouvel_article = fields.get("article_id") or mvt.article_id
        change_article = nouvel_article != mvt.article_id
        if change_article or nouvelle_qty != ancienne_qty:
            self._assert_quantite_modifiable(mvt, periode, "modifier")
            if mvt.type_mouvement == "AJUSTEMENT":
                if nouvelle_qty == 0:
                    raise AppError("Un ajustement ne peut pas être nul.", code="AJUSTEMENT_NUL")
            elif nouvelle_qty <= 0:
                raise AppError("La quantité doit être supérieure à 0.", code="QUANTITE_INVALIDE")
            if change_article:
                cible = await self.db.get(MgArticle, nouvel_article)
                if cible is None or cible.deleted_at is not None:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Article introuvable")
                await self._appliquer_effet(mvt, periode, -ancienne_qty)
                mvt.article_id = nouvel_article
                await self._appliquer_effet(mvt, periode, nouvelle_qty)
            else:
                await self._appliquer_effet(mvt, periode, nouvelle_qty - ancienne_qty)
            mvt.quantite = nouvelle_qty

        for key in ("agence_id", "departement", "motif", "observation"):
            if key in fields:
                value = fields[key]
                setattr(mvt, key, value.strip() or None if isinstance(value, str) else value)

        await self.db.commit()
        await self.db.refresh(mvt)
        return mvt, before

    async def delete_mouvement(self, mvt_id: uuid.UUID) -> dict:
        mvt, periode = await self._mouvement_locked(mvt_id)
        self._assert_quantite_modifiable(mvt, periode, "supprimer")
        before = self.mouvement_snapshot(mvt)
        await self._appliquer_effet(mvt, periode, -Decimal(mvt.quantite))
        await self.db.delete(mvt)
        await self.db.commit()
        return before

    async def _supprimer_force(self, mvt: MgStockMouvement) -> dict:
        """Suppression administrateur : annule l'effet du mouvement, y compris en période clôturée.

        Les soldes de la période du mouvement et de toutes les périodes suivantes
        sont recalculés (report du stock initial).
        """
        if mvt.type_mouvement == "INVENTAIRE":
            raise AppError(
                "Un mouvement de type inventaire fixe le stock : il ne peut pas être annulé. "
                "Saisissez un ajustement.",
                code="MVT_TYPE_VERROUILLE",
            )
        qty = Decimal(mvt.quantite)
        effet = -qty if mvt.type_mouvement == "SORTIE" else qty
        article = await self.db.scalar(
            select(MgArticle).where(MgArticle.id == mvt.article_id).with_for_update()
        )
        if article is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Article introuvable")
        nouveau = Decimal(article.stock_actuel or 0) - effet
        if nouveau < 0:
            raise AppError(
                f"Suppression refusée : le stock de {article.code} deviendrait négatif ({as_qty(nouveau)}). "
                "Supprimez d’abord les sorties postérieures à cette entrée.",
                code="STOCK_NEGATIF",
            )
        article.stock_actuel = nouveau

        periode = await self.db.get(MgStockPeriode, mvt.periode_id) if mvt.periode_id else None
        if periode is not None:
            from app.services.mg_stock_periodes import compute_theorique

            rows = (
                await self.db.execute(
                    select(MgStockSolde, MgStockPeriode)
                    .join(MgStockPeriode, MgStockPeriode.id == MgStockSolde.periode_id)
                    .where(
                        MgStockSolde.article_id == article.id,
                        MgStockPeriode.date_debut >= periode.date_debut,
                    )
                    .with_for_update(of=MgStockSolde)
                )
            ).all()
            for solde, p in rows:
                if p.id == periode.id:
                    if mvt.type_mouvement == "ENTREE":
                        solde.entrees = Decimal(solde.entrees or 0) - qty
                    elif mvt.type_mouvement == "SORTIE":
                        solde.sorties = Decimal(solde.sorties or 0) - qty
                    else:
                        solde.ajustements = Decimal(solde.ajustements or 0) - qty
                else:
                    solde.stock_initial = Decimal(solde.stock_initial or 0) - effet
                solde.stock_theorique = compute_theorique(
                    solde.stock_initial, solde.entrees, solde.sorties, solde.ajustements
                )
                if solde.stock_physique is not None:
                    solde.ecart = Decimal(solde.stock_physique) - Decimal(solde.stock_theorique)
                elif solde.stock_final is not None:
                    solde.stock_final = Decimal(solde.stock_final) - effet
        before = self.mouvement_snapshot(mvt)
        await self.db.delete(mvt)
        return before

    async def force_delete_mouvement(self, mvt_id: uuid.UUID) -> dict:
        mvt, _ = await self._mouvement_locked(mvt_id)
        before = await self._supprimer_force(mvt)
        await self.db.commit()
        return before

    async def supprimer_mouvements_source(self, source_type: str, source_id: uuid.UUID) -> list[dict]:
        mvts = (
            await self.db.execute(
                select(MgStockMouvement)
                .where(MgStockMouvement.source_type == source_type, MgStockMouvement.source_id == source_id)
                .order_by(MgStockMouvement.date_mouvement.desc())
                .with_for_update()
            )
        ).scalars().all()
        return [await self._supprimer_force(m) for m in mvts]

    async def list_bons_reception(self) -> list:
        """Bons VALIDE|PARTIEL disponibles pour réception stock."""
        from app.models.mg_ops import MgBonCommande

        stmt = (
            select(MgBonCommande)
            .options(selectinload(MgBonCommande.lignes))
            .where(
                MgBonCommande.deleted_at.is_(None),
                MgBonCommande.statut.in_(["VALIDE", "ENVOYE", "PARTIEL"]),
            )
            .order_by(MgBonCommande.date_bc.desc())
        )
        return list((await self.db.execute(stmt)).scalars().unique().all())

    async def receive_from_bc(self, bon_id: uuid.UUID, data: ReceptionBcIn, user: User) -> dict:
        """Voie Stock : délègue à la réception Achats (une seule source de vérité)."""
        from app.models.mg_ops import MgBcLigne, MgBonCommande
        from app.schemas.mg_achats import ReceptionCreate, ReceptionLigneIn
        from app.services.mg_achats_service import MgAchatsService

        for payload in data.lignes:
            if payload.article_id is None:
                ligne_article = await self.db.scalar(
                    select(MgBcLigne.article_id).where(MgBcLigne.id == payload.ligne_id)
                )
                if ligne_article is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail="Article requis pour chaque ligne réceptionnée en stock",
                    )
        reception = await MgAchatsService(self.db).create_reception(
            ReceptionCreate(
                bon_id=bon_id,
                date_reception=datetime.now(timezone.utc).date(),
                agence_id=data.agence_id,
                observation=data.motif,
                lignes=[
                    ReceptionLigneIn(
                        bc_ligne_id=p.ligne_id, quantite_recue=p.quantite, article_id=p.article_id
                    )
                    for p in data.lignes
                ],
            ),
            user,
            stocker_si_article=True,
        )
        mouvements_count = len([rl for rl in reception.lignes if rl.article_id])
        # Reload with lignes for response serialization
        bon = await self.db.scalar(
            select(MgBonCommande)
            .options(selectinload(MgBonCommande.lignes))
            .where(MgBonCommande.id == bon_id)
            .execution_options(populate_existing=True)
        )
        return {"bon": bon, "mouvements_count": mouvements_count}

    async def list_mouvements(
        self,
        *,
        article_id: uuid.UUID | None = None,
        type_mouvement: str | None = None,
        agence_id: uuid.UUID | None = None,
        q: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[MgStockMouvement], int]:
        filters = []
        if q and q.strip():
            like = f"%{q.strip()}%"
            articles = select(MgArticle.id).where(
                or_(MgArticle.code.ilike(like), MgArticle.designation.ilike(like))
            )
            filters.append(
                or_(
                    MgStockMouvement.reference.ilike(like),
                    MgStockMouvement.motif.ilike(like),
                    MgStockMouvement.article_id.in_(articles),
                )
            )
        if article_id:
            filters.append(MgStockMouvement.article_id == article_id)
        if type_mouvement:
            filters.append(MgStockMouvement.type_mouvement == type_mouvement.upper())
        if agence_id:
            filters.append(MgStockMouvement.agence_id == agence_id)
        count_stmt = select(func.count()).select_from(MgStockMouvement)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = int((await self.db.scalar(count_stmt)) or 0)
        page = max(1, page)
        size = max(1, min(size, 500))
        stmt = select(MgStockMouvement)
        if filters:
            stmt = stmt.where(*filters)
        stmt = (
            stmt.order_by(MgStockMouvement.date_mouvement.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list((await self.db.execute(stmt)).scalars().all()), total

    async def enrich_mouvements(self, mouvements: list[MgStockMouvement]) -> list[dict]:
        if not mouvements:
            return []
        article_ids = {m.article_id for m in mouvements if m.article_id}
        initiateur_ids = {m.initiateur_id for m in mouvements if m.initiateur_id}
        articles: dict[uuid.UUID, MgArticle] = {}
        if article_ids:
            rows = (
                await self.db.execute(select(MgArticle).where(MgArticle.id.in_(article_ids)))
            ).scalars().all()
            articles = {a.id: a for a in rows}
        users: dict[uuid.UUID, User] = {}
        if initiateur_ids:
            rows = (
                await self.db.execute(select(User).where(User.id.in_(initiateur_ids)))
            ).scalars().all()
            users = {u.id: u for u in rows}
        periode_ids = {m.periode_id for m in mouvements if m.periode_id}
        periodes: dict[uuid.UUID, MgStockPeriode] = {}
        if periode_ids:
            rows = (
                await self.db.execute(select(MgStockPeriode).where(MgStockPeriode.id.in_(periode_ids)))
            ).scalars().all()
            periodes = {p.id: p for p in rows}
        out: list[dict] = []
        for m in mouvements:
            article = articles.get(m.article_id)
            initiateur = users.get(m.initiateur_id) if m.initiateur_id else None
            periode = periodes.get(m.periode_id) if m.periode_id else None
            cloturee = bool(periode and periode.statut == "CLOTUREE")
            out.append(
                {
                    "id": m.id,
                    "reference": m.reference,
                    "date_mouvement": m.date_mouvement,
                    "type_mouvement": m.type_mouvement,
                    "article_id": m.article_id,
                    "quantite": m.quantite,
                    "agence_id": m.agence_id,
                    "departement": m.departement,
                    "motif": m.motif,
                    "observation": m.observation,
                    "source_type": m.source_type,
                    "source_id": m.source_id,
                    "initiateur_id": m.initiateur_id,
                    "initiateur_nom": initiateur.full_name if initiateur else None,
                    "article_code": article.code if article else None,
                    "article_designation": article.designation if article else None,
                    "stock_disponible": article.stock_actuel if article else None,
                    "periode_id": getattr(m, "periode_id", None),
                    "periode_libelle": periode.libelle if periode else None,
                    "periode_debut": periode.date_debut if periode else None,
                    "periode_fin": periode.date_fin if periode else None,
                    "periode_cloturee": cloturee,
                    "quantite_modifiable": (
                        not cloturee
                        and m.type_mouvement in MOUVEMENTS_EDITABLES
                        and (m.source_type or "") not in WORKFLOW_SOURCES
                    ),
                }
            )
        return out

    async def create_demande(self, data: DemandeCreate, user: User) -> MgDemandeFourniture:
        agence = await self.db.get(Agence, data.agence_id)
        if agence is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Agence invalide")
        ref = await self._next_demande_ref()
        demande = MgDemandeFourniture(
            reference=ref,
            date_demande=data.date_demande or date.today(),
            agence_id=agence.id,
            agence_libelle_snapshot=agence.libelle,
            agence_adresse_snapshot=agence.adresse,
            departement=data.departement,
            demandeur_id=user.id,
            demandeur_nom=user.full_name,
            fonction=data.fonction,
            statut="BROUILLON",
            observation=data.observation,
        )
        self.db.add(demande)
        await self.db.flush()
        self._replace_lignes(demande, data.lignes)
        await self.db.commit()
        return await self.get_demande(demande.id)

    async def update_demande(
        self, demande_id: uuid.UUID, data: DemandeUpdate, user: User
    ) -> MgDemandeFourniture:
        demande = await self.get_demande(demande_id)
        if demande.statut != "BROUILLON":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Seuls les brouillons sont modifiables")
        if data.departement is not None:
            demande.departement = data.departement
        if data.fonction is not None:
            demande.fonction = data.fonction
        if data.observation is not None:
            demande.observation = data.observation
        if data.lignes is not None:
            for ligne in list(demande.lignes):
                await self.db.delete(ligne)
            await self.db.flush()
            self._replace_lignes(demande, data.lignes)
        await self.db.commit()
        return await self.get_demande(demande_id)

    async def delete_demande(self, demande_id: uuid.UUID, *, force: bool = False) -> tuple[MgDemandeFourniture, list[dict]]:
        demande = await self.get_demande(demande_id, for_update=True)
        if force:
            annules = await self.supprimer_mouvements_source("demande_fourniture", demande.id)
            demande.deleted_at = datetime.now(timezone.utc)
            await self.db.commit()
            return demande, annules
        if demande.statut not in {"BROUILLON", "ANNULEE", "REJETEE"}:
            raise AppError(
                "Seules les demandes en brouillon, annulées ou rejetées peuvent être supprimées. "
                "Annulez d’abord la demande.",
                code="DEMANDE_NON_SUPPRIMABLE",
            )
        demande.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        return demande, []

    async def transition_demande(
        self, demande_id: uuid.UUID, action: str, user: User, lignes: list[DemandeLigneIn] | None
    ) -> MgDemandeFourniture:
        demande = await self.get_demande(demande_id, for_update=True)
        action = action.strip().lower()
        now = datetime.now(timezone.utc)

        if action == "soumettre":
            if demande.statut != "BROUILLON":
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Statut incompatible")
            demande.statut = "SOUMIS"
        elif action == "visa_agence":
            if demande.statut != "SOUMIS":
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Statut incompatible")
            demande.statut = "VISA_AGENCE"
            demande.visa_agence_at = now
            demande.visa_agence_by = user.id
        elif action == "visa_mg":
            if demande.statut != "VISA_AGENCE":
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Statut incompatible")
            if lignes:
                by_des = {lg.designation: lg for lg in lignes}
                for row in demande.lignes:
                    src = by_des.get(row.designation)
                    if src and src.quantite_accordee is not None:
                        row.quantite_accordee = src.quantite_accordee
                    elif row.quantite_accordee is None:
                        row.quantite_accordee = row.quantite_demandee
            else:
                for row in demande.lignes:
                    if row.quantite_accordee is None:
                        row.quantite_accordee = row.quantite_demandee
            demande.statut = "PREPARATION"
            demande.visa_mg_at = now
            demande.visa_mg_by = user.id
        elif action == "servir":
            # Compat: ACCORDEE (ancien flux) traité comme PREPARATION
            if demande.statut not in {"PREPARATION", "ACCORDEE"}:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Statut incompatible")
            await self._sortie_from_demande(demande, user)
            demande.statut = "SERVIE"
        elif action == "archiver":
            if demande.statut != "SERVIE":
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Statut incompatible")
            demande.statut = "ARCHIVEE"
        elif action == "rejeter":
            if demande.statut in {"ARCHIVEE", "CLOTUREE", "ANNULEE", "REJETEE", "SERVIE"}:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Statut incompatible")
            demande.statut = "REJETEE"
        elif action == "annuler":
            if demande.statut in {"ARCHIVEE", "CLOTUREE", "SERVIE"}:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Déjà servie/archivée")
            demande.statut = "ANNULEE"
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Action inconnue")

        await self.db.commit()
        return await self.get_demande(demande_id)

    async def list_demandes(
        self,
        *,
        statut: str | None = None,
        agence_id: uuid.UUID | None = None,
        article_id: uuid.UUID | None = None,
        q: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[MgDemandeFourniture], int]:
        filters = [MgDemandeFourniture.deleted_at.is_(None)]
        if q and q.strip():
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    MgDemandeFourniture.reference.ilike(like),
                    MgDemandeFourniture.agence_libelle_snapshot.ilike(like),
                    MgDemandeFourniture.demandeur_nom.ilike(like),
                )
            )
        if statut:
            s = statut.upper()
            if s in {"ARCHIVEE", "CLOTUREE"}:
                filters.append(MgDemandeFourniture.statut.in_(["ARCHIVEE", "CLOTUREE"]))
            else:
                filters.append(MgDemandeFourniture.statut == s)
        if agence_id:
            filters.append(MgDemandeFourniture.agence_id == agence_id)
        if article_id:
            filters.append(
                MgDemandeFourniture.id.in_(
                    select(MgDemandeFournitureLigne.demande_id).where(
                        MgDemandeFournitureLigne.article_id == article_id
                    )
                )
            )
        count_stmt = select(func.count()).select_from(MgDemandeFourniture).where(*filters)
        total = int((await self.db.scalar(count_stmt)) or 0)
        page = max(1, page)
        size = max(1, min(size, 500))
        stmt = (
            select(MgDemandeFourniture)
            .options(selectinload(MgDemandeFourniture.lignes))
            .where(*filters)
            .order_by(MgDemandeFourniture.date_demande.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list((await self.db.execute(stmt)).scalars().unique().all()), total

    async def get_demande(
        self, demande_id: uuid.UUID, *, for_update: bool = False
    ) -> MgDemandeFourniture:
        stmt = (
            select(MgDemandeFourniture)
            .options(selectinload(MgDemandeFourniture.lignes))
            .where(MgDemandeFourniture.id == demande_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        demande = (await self.db.execute(stmt)).scalar_one_or_none()
        if demande is None or demande.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Demande introuvable")
        return demande

    async def dashboard(
        self,
        *,
        agence_id: uuid.UUID | None = None,
        famille_id: uuid.UUID | None = None,
        period: str = "30j",
        statut_niveau: str | None = None,
    ) -> dict:
        art_stmt = select(MgArticle).where(MgArticle.deleted_at.is_(None))
        if agence_id:
            art_stmt = art_stmt.where(MgArticle.agence_id == agence_id)
        if famille_id:
            art_stmt = art_stmt.where(MgArticle.famille_id == famille_id)
        articles = list((await self.db.execute(art_stmt)).scalars().all())

        niveau_filter = (statut_niveau or "").strip().lower()
        if niveau_filter and niveau_filter not in {"", "empty", "tous", "all"}:
            articles = [a for a in articles if self.niveau_stock(a) == niveau_filter]

        actifs = [a for a in articles if a.is_active]
        inactifs = [a for a in articles if not a.is_active]
        stock_total = float(sum((a.stock_actuel or Decimal("0")) for a in actifs))
        faible = sum(1 for a in actifs if self.niveau_stock(a) == "faible")
        epuise = sum(1 for a in actifs if self.niveau_stock(a) == "epuise")

        now = datetime.now(timezone.utc)
        start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        async def _count_mvts(
            *,
            type_mouvement: str | None = None,
            since: datetime | None = None,
        ) -> int:
            stmt = select(func.count()).select_from(MgStockMouvement)
            if since is not None:
                stmt = stmt.where(MgStockMouvement.date_mouvement >= since)
            if type_mouvement:
                stmt = stmt.where(MgStockMouvement.type_mouvement == type_mouvement)
            if agence_id:
                stmt = stmt.where(MgStockMouvement.agence_id == agence_id)
            if famille_id:
                stmt = stmt.join(MgArticle, MgArticle.id == MgStockMouvement.article_id).where(
                    MgArticle.famille_id == famille_id
                )
            return int(await self.db.scalar(stmt) or 0)

        entrees_mois = await _count_mvts(type_mouvement="ENTREE", since=start_month)
        sorties_mois = await _count_mvts(type_mouvement="SORTIE", since=start_month)
        mouvements_mois = await _count_mvts(since=start_month)
        mouvements_aujourd_hui = await _count_mvts(since=start_today)

        crees_stmt = (
            select(func.count())
            .select_from(MgArticle)
            .where(
                MgArticle.deleted_at.is_(None),
                MgArticle.created_at >= start_month,
            )
        )
        if agence_id:
            crees_stmt = crees_stmt.where(MgArticle.agence_id == agence_id)
        if famille_id:
            crees_stmt = crees_stmt.where(MgArticle.famille_id == famille_id)
        articles_crees_mois = int(await self.db.scalar(crees_stmt) or 0)

        from app.models.mg_requests import MgEmployeeRequest

        # Les besoins arrivent par les demandes employés (reçues par Moyens Généraux).
        async def _count_demandes(statuts: list[str]) -> int:
            stmt = (
                select(func.count())
                .select_from(MgEmployeeRequest)
                .where(
                    MgEmployeeRequest.target_espace_code == "moyens-generaux",
                    MgEmployeeRequest.status.in_(statuts),
                )
            )
            if agence_id:
                stmt = stmt.where(MgEmployeeRequest.agency_id == agence_id)
            return int(await self.db.scalar(stmt) or 0)

        demandes_en_attente = await _count_demandes(["SOUMISE", "RECUE", "EN_ANALYSE"])
        demandes_en_cours = await _count_demandes(
            ["A_COMPLETER", "VALIDEE", "A_REGROUPER", "REGROUPEE", "ACHAT_EN_COURS", "COMMANDEE"]
        )
        demandes_validees = await _count_demandes(["SERVIE", "CLOTUREE"])
        demandes_rejetees = await _count_demandes(["REFUSEE", "ANNULEE"])

        inv_filters = [
            MgInventaire.deleted_at.is_(None),
            MgInventaire.statut.in_(["BROUILLON", "EN_COURS", "A_CONTROLER"]),
        ]
        if agence_id:
            inv_filters.append(MgInventaire.agence_id == agence_id)
        inventaires_en_cours = int(
            await self.db.scalar(select(func.count()).select_from(MgInventaire).where(*inv_filters)) or 0
        )
        a_compter, comptes = (
            await self.db.execute(
                select(
                    func.count(MgInventaireLigne.id).filter(MgInventaireLigne.statut_comptage != "EXCLU"),
                    func.count(MgInventaireLigne.id).filter(MgInventaireLigne.statut_comptage == "COMPTE"),
                )
                .join(MgInventaire, MgInventaire.id == MgInventaireLigne.inventaire_id)
                .where(*inv_filters)
            )
        ).one()
        inventaire_progression = round(100.0 * comptes / a_compter, 1) if a_compter else 0.0

        return {
            "articles_total": len(articles),
            "articles_actifs": len(actifs),
            "articles_inactifs": len(inactifs),
            "stock_total_unites": stock_total,
            "entrees_mois": entrees_mois,
            "sorties_mois": sorties_mois,
            "articles_crees_mois": articles_crees_mois,
            "stock_faible": faible,
            "stock_epuise": epuise,
            "demandes_en_attente": demandes_en_attente,
            "demandes_en_cours": demandes_en_cours,
            "demandes_validees": demandes_validees,
            "demandes_rejetees": demandes_rejetees,
            "inventaires_en_cours": inventaires_en_cours,
            "inventaire_progression": inventaire_progression,
            "mouvements_aujourd_hui": mouvements_aujourd_hui,
            "mouvements_mois": mouvements_mois,
            "evolution": await self._evolution_mouvements(
                period, agence_id=agence_id, famille_id=famille_id
            ),
            "conso_par_famille": await self._conso_par_famille(agence_id=agence_id),
            "conso_par_agence": await self._conso_par_agence(),
            "conso_par_mois": await self._conso_par_mois(agence_id=agence_id),
            **await self._dashboard_periode(),
        }

    async def list_alertes(
        self, *, agence_id: uuid.UUID | None = None
    ) -> list[dict]:
        articles, _ = await self.list_articles(bas_stock=True, agence_id=agence_id, size=500)
        out = [
            {
                "article_id": a.id,
                "code": a.code,
                "designation": a.designation,
                "stock_actuel": a.stock_actuel,
                "stock_min": a.stock_min,
                "niveau": self.niveau_stock(a),
                "agence_id": a.agence_id,
                "type_alerte": "RUPTURE" if self.niveau_stock(a) == "epuise" else "STOCK_FAIBLE",
                "titre": "Rupture" if self.niveau_stock(a) == "epuise" else "Stock faible",
                "message": f"{a.code} — {a.designation}",
                "lien": "/stock-fournitures/alertes",
            }
            for a in articles
        ]
        try:
            psvc = MgStockPeriodeService(self.db)
            periode = await psvc.periode_ouverte()
            if periode is None:
                periode = await psvc.ensure_open_periode()
            code, message = await psvc.cloture_alerte(periode)
            if code and message:
                out.insert(
                    0,
                    {
                        "article_id": None,
                        "code": code,
                        "designation": message,
                        "stock_actuel": None,
                        "stock_min": None,
                        "niveau": "warn",
                        "agence_id": None,
                        "type_alerte": code.upper(),
                        "titre": message,
                        "message": message,
                        "lien": "/stock-fournitures/inventaires",
                    },
                )
            rec_pending = await self._count_receptions_en_attente()
            if rec_pending:
                out.insert(
                    0 if not (code and message) else 1,
                    {
                        "article_id": None,
                        "code": "RECEPTION_EN_ATTENTE",
                        "designation": f"{rec_pending} bon(s) en attente de réception",
                        "stock_actuel": None,
                        "stock_min": None,
                        "niveau": "warn",
                        "agence_id": None,
                        "type_alerte": "RECEPTION_EN_ATTENTE",
                        "titre": "Réception en attente",
                        "message": f"{rec_pending} bon(s) VALIDE/PARTIEL à réceptionner",
                        "lien": "/stock-fournitures/entrees",
                    },
                )
        except Exception:
            await self.db.rollback()
        return out

    async def list_parametres(self) -> list[MgStockParametre]:
        stmt = select(MgStockParametre).order_by(MgStockParametre.cle)
        return list((await self.db.execute(stmt)).scalars().all())

    async def create_parametre(self, data: ParametreCreate) -> MgStockParametre:
        cle = data.cle.strip()
        exists = await self.db.scalar(
            select(MgStockParametre.id).where(MgStockParametre.cle == cle)
        )
        if exists:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Clé paramètre déjà utilisée")
        row = MgStockParametre(
            cle=cle,
            valeur=data.valeur.strip(),
            libelle=(data.libelle.strip() if data.libelle else None),
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_parametre(self, cle: str, data: ParametreUpdate) -> MgStockParametre:
        row = await self.db.scalar(select(MgStockParametre).where(MgStockParametre.cle == cle))
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paramètre introuvable")
        row.valeur = data.valeur.strip()
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def delete_parametre(self, cle: str) -> None:
        row = await self.db.scalar(select(MgStockParametre).where(MgStockParametre.cle == cle))
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paramètre introuvable")
        await self.db.delete(row)
        await self.db.commit()

    async def rapport_conso(
        self, *, year: int, month: int | None = None, agence_id: uuid.UUID | None = None
    ) -> dict:
        stmt = (
            select(
                MgArticleFamille.libelle.label("famille"),
                MgArticle.code,
                MgArticle.designation,
                func.coalesce(func.sum(MgStockMouvement.quantite), 0).label("quantite"),
            )
            .join(MgArticle, MgArticle.id == MgStockMouvement.article_id)
            .join(MgArticleFamille, MgArticleFamille.id == MgArticle.famille_id)
            .where(MgStockMouvement.type_mouvement == "SORTIE")
            .where(func.extract("year", MgStockMouvement.date_mouvement) == year)
            .group_by(MgArticleFamille.libelle, MgArticle.code, MgArticle.designation)
            .order_by(MgArticleFamille.libelle, MgArticle.code)
        )
        if month:
            stmt = stmt.where(func.extract("month", MgStockMouvement.date_mouvement) == month)
        if agence_id:
            stmt = stmt.where(MgStockMouvement.agence_id == agence_id)
        rows = (await self.db.execute(stmt)).all()
        return {
            "periode": f"{year}-{month:02d}" if month else str(year),
            "granularity": "mensuelle" if month else "annuelle",
            "lignes": [
                {
                    "famille": r.famille,
                    "code": r.code,
                    "designation": r.designation,
                    "quantite": as_qty(r.quantite or 0),
                }
                for r in rows
            ],
        }

    # --- internals ---

    def _replace_lignes(self, demande: MgDemandeFourniture, lignes: list[DemandeLigneIn]) -> None:
        for i, ligne in enumerate(lignes):
            self.db.add(
                MgDemandeFournitureLigne(
                    demande_id=demande.id,
                    article_id=ligne.article_id,
                    designation=ligne.designation.strip(),
                    quantite_demandee=ligne.quantite_demandee,
                    quantite_accordee=ligne.quantite_accordee,
                    sort_order=i,
                )
            )

    async def _sortie_from_demande(self, demande: MgDemandeFourniture, user: User) -> None:
        for ligne in demande.lignes:
            qty = ligne.quantite_accordee or Decimal("0")
            if qty <= 0 or ligne.article_id is None:
                continue
            already = await self.db.scalar(
                select(MgStockMouvement.id).where(
                    MgStockMouvement.source_type == "demande_fourniture",
                    MgStockMouvement.source_id == demande.id,
                    MgStockMouvement.article_id == ligne.article_id,
                    MgStockMouvement.type_mouvement == "SORTIE",
                )
            )
            if already:
                continue
            article = await self.db.scalar(
                select(MgArticle)
                .where(MgArticle.id == ligne.article_id, MgArticle.deleted_at.is_(None))
                .with_for_update()
            )
            if article is None:
                continue
            if not getattr(article, "stockable", True):
                continue
            await self._apply_mouvement(
                article=article,
                type_mouvement="SORTIE",
                quantite=qty,
                agence_id=demande.agence_id,
                initiateur=user,
                motif=f"Demande {demande.reference}",
                source_type="demande_fourniture",
                source_id=demande.id,
                departement=demande.departement,
            )

    async def record_achat_reception(
        self,
        *,
        article: MgArticle,
        quantite: Decimal,
        agence_id: uuid.UUID | None,
        initiateur: User | None,
        motif: str | None = None,
        source_id: uuid.UUID | None = None,
    ) -> MgStockMouvement:
        """API publique appelée par Achats & Approvisionnements.

        Enregistre une entrée de stock consécutive à une réception achat.
        Ne modifie ``mg_articles.stock_actuel`` qu'à travers ``_apply_mouvement``
        (source unique de vérité pour les mouvements de stock).
        """
        if not getattr(article, "stockable", True):
            return None
        return await self._apply_mouvement(
            article=article,
            type_mouvement="ENTREE",
            quantite=quantite,
            agence_id=agence_id,
            initiateur=initiateur,
            motif=motif,
            source_type="achat_reception",
            source_id=source_id,
        )

    async def annuler_achat_reception(
        self,
        *,
        article: MgArticle,
        quantite: Decimal,
        agence_id: uuid.UUID | None,
        initiateur: User | None,
        motif: str | None,
        source_id: uuid.UUID,
        legacy_source_id: uuid.UUID | None = None,
    ) -> MgStockMouvement | None:
        """API publique : contre-mouvement (SORTIE) d'une réception achat annulée.

        Sans entrée de stock d'origine, rien n'est mouvementé. ``legacy_source_id``
        couvre les réceptions historiques rattachées au BC plutôt qu'à la réception.
        Stock insuffisant → refus (jamais de stock négatif).
        """
        ids = [source_id] + ([legacy_source_id] if legacy_source_id else [])
        entree = await self.db.scalar(
            select(func.count())
            .select_from(MgStockMouvement)
            .where(
                MgStockMouvement.source_type.in_(["achat_reception", "bon_commande"]),
                MgStockMouvement.source_id.in_(ids),
                MgStockMouvement.article_id == article.id,
                MgStockMouvement.type_mouvement == "ENTREE",
            )
        )
        if not entree or not getattr(article, "stockable", True):
            return None
        return await self._apply_mouvement(
            article=article,
            type_mouvement="SORTIE",
            quantite=quantite,
            agence_id=agence_id,
            initiateur=initiateur,
            motif=motif,
            source_type="achat_reception_annulation",
            source_id=source_id,
        )

    async def _apply_mouvement(
        self,
        *,
        article: MgArticle,
        type_mouvement: str,
        quantite: Decimal,
        agence_id: uuid.UUID | None,
        initiateur: User | None,
        motif: str | None = None,
        observation: str | None = None,
        departement: str | None = None,
        source_type: str | None = None,
        source_id: uuid.UUID | None = None,
        date_mouvement: datetime | None = None,
        allow_zero: bool = False,
        force_stock: Decimal | None = None,
        allow_negative: bool = False,
    ) -> MgStockMouvement:
        qty = Decimal(quantite)
        if type_mouvement == "AJUSTEMENT":
            if qty == 0 and not allow_zero:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Quantité invalide")
        elif qty < 0 or (qty == 0 and not allow_zero):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Quantité invalide")

        if not getattr(article, "stockable", True):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Article {article.code} non stockable — aucun mouvement de stock.",
            )

        if source_type and source_id:
            existing = await self._existing_source_mvt(
                source_type, source_id, article.id, type_mouvement
            )
            if existing is not None:
                return existing

        psvc = MgStockPeriodeService(self.db)
        periode = await psvc.resolve_for_movement(date_mouvement)

        current = Decimal(article.stock_actuel or 0)
        if type_mouvement == "ENTREE":
            new_stock = current + qty
        elif type_mouvement == "SORTIE":
            new_stock = current - qty
        elif type_mouvement == "AJUSTEMENT":
            new_stock = current + qty
        elif type_mouvement == "INVENTAIRE":
            new_stock = force_stock if force_stock is not None else qty
            qty = Decimal(new_stock or 0)
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Type invalide")

        if new_stock < 0 and not allow_negative:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Stock insuffisant ({current}) pour {article.code} — stock négatif interdit.",
            )

        article.stock_actuel = new_stock

        mvt_qty = qty
        if mvt_qty == 0 and type_mouvement not in {"INVENTAIRE", "AJUSTEMENT"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Quantité invalide")

        ref = await self._next_mvt_ref(type_mouvement)
        mvt = MgStockMouvement(
            reference=ref,
            date_mouvement=date_mouvement or datetime.now(timezone.utc),
            type_mouvement=type_mouvement,
            article_id=article.id,
            quantite=mvt_qty,
            agence_id=agence_id,
            departement=departement,
            initiateur_id=initiateur.id if initiateur else None,
            motif=motif,
            observation=observation,
            source_type=source_type,
            source_id=source_id,
            periode_id=periode.id,
        )
        self.db.add(mvt)
        await self.db.flush()
        if type_mouvement in {"ENTREE", "SORTIE", "AJUSTEMENT"}:
            await psvc.touch_solde(periode, article, type_mouvement, mvt_qty)
        return mvt

    async def _next_mvt_ref(self, type_mouvement: str) -> str:
        defaults = {"ENTREE": "ENT", "SORTIE": "SOR", "AJUSTEMENT": "AJU", "INVENTAIRE": "INV"}
        param_key = {
            "ENTREE": "prefix_entree",
            "SORTIE": "prefix_sortie",
            "INVENTAIRE": "prefix_inventaire",
        }.get(type_mouvement)
        prefix = defaults.get(type_mouvement, "MVT")
        if param_key:
            row = await self.db.scalar(
                select(MgStockParametre).where(MgStockParametre.cle == param_key)
            )
            if row and row.valeur:
                prefix = row.valeur.strip() or prefix
        year = datetime.now(timezone.utc).year
        count = await self.db.scalar(
            select(func.count())
            .select_from(MgStockMouvement)
            .where(MgStockMouvement.reference.like(f"{prefix}-{year}-%"))
        )
        return f"{prefix}-{year}-{(count or 0) + 1:05d}"

    async def _next_demande_ref(self) -> str:
        prefix = "DF"
        row = await self.db.scalar(
            select(MgStockParametre).where(MgStockParametre.cle == "prefix_demande")
        )
        if row and row.valeur:
            prefix = row.valeur.strip() or prefix
        year = datetime.now(timezone.utc).year
        count = await self.db.scalar(
            select(func.count())
            .select_from(MgDemandeFourniture)
            .where(MgDemandeFourniture.reference.like(f"{prefix}-{year}-%"))
        )
        return f"{prefix}-{year}-{(count or 0) + 1:05d}"

    async def _existing_source_mvt(
        self,
        source_type: str,
        source_id: uuid.UUID,
        article_id: uuid.UUID,
        type_mouvement: str,
    ) -> MgStockMouvement | None:
        if source_type not in {"demande_fourniture", "inventaire"}:
            return None
        return await self.db.scalar(
            select(MgStockMouvement).where(
                MgStockMouvement.source_type == source_type,
                MgStockMouvement.source_id == source_id,
                MgStockMouvement.article_id == article_id,
                MgStockMouvement.type_mouvement == type_mouvement,
            )
        )

    async def _dashboard_periode(self) -> dict:
        empty = {
            "periode_active": None,
            "stock_initial_periode": 0.0,
            "entrees_qte_periode": 0.0,
            "sorties_qte_periode": 0.0,
            "ajustements_qte_periode": 0.0,
            "stock_theorique_periode": 0.0,
            "ajustements_mois": 0,
            "cloture_statut": None,
            "cloture_message": None,
        }
        try:
            psvc = MgStockPeriodeService(self.db)
            periode = await psvc.ensure_open_periode()
            totaux = await psvc.totaux_periode(periode)
            code, message = await psvc.cloture_alerte(periode)
            aj_count = int(
                await self.db.scalar(
                    select(func.count())
                    .select_from(MgStockMouvement)
                    .where(
                        MgStockMouvement.type_mouvement == "AJUSTEMENT",
                        MgStockMouvement.periode_id == periode.id,
                    )
                )
                or 0
            )
            return {
                "periode_active": psvc.serialize_periode(periode),
                "stock_initial_periode": totaux["stock_initial"],
                "entrees_qte_periode": totaux["entrees"],
                "sorties_qte_periode": totaux["sorties"],
                "ajustements_qte_periode": totaux["ajustements"],
                "stock_theorique_periode": totaux["stock_theorique"],
                "ajustements_mois": aj_count,
                "cloture_statut": code,
                "cloture_message": message,
            }
        except Exception:
            await self.db.rollback()
            return empty

    async def _count_receptions_en_attente(self) -> int:
        from app.models.mg_ops import MgBonCommande

        return int(
            await self.db.scalar(
                select(func.count())
                .select_from(MgBonCommande)
                .where(
                    MgBonCommande.deleted_at.is_(None),
                    MgBonCommande.statut.in_(["VALIDE", "ENVOYE", "PARTIEL"]),
                )
            )
            or 0
        )

    async def _evolution_mouvements(
        self,
        period: str,
        *,
        agence_id: uuid.UUID | None = None,
        famille_id: uuid.UUID | None = None,
    ) -> list[dict]:
        now = datetime.now(timezone.utc)
        period = (period or "30j").strip().lower()

        buckets: list[tuple[str, datetime, datetime]] = []
        if period == "7j":
            for i in range(6, -1, -1):
                day = (now - timedelta(days=i)).date()
                start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
                end = start + timedelta(days=1)
                buckets.append((day.strftime("%d/%m"), start, end))
        elif period == "3m":
            # 12 weekly buckets covering ~84 days
            for i in range(11, -1, -1):
                end = now - timedelta(weeks=i)
                start = end - timedelta(weeks=1)
                buckets.append((f"S{12 - i}", start, end))
        elif period == "12m":
            for i in range(11, -1, -1):
                # first day of month i months ago
                year = now.year
                month = now.month - i
                while month <= 0:
                    month += 12
                    year -= 1
                start = datetime(year, month, 1, tzinfo=timezone.utc)
                if month == 12:
                    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
                else:
                    end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
                buckets.append((f"{month:02d}/{year}", start, end))
        else:
            # 30j default: 5 weekly buckets S1..S5
            for i in range(4, -1, -1):
                end = now - timedelta(weeks=i)
                start = end - timedelta(weeks=1)
                buckets.append((f"S{5 - i}", start, end))

        range_start = buckets[0][1] if buckets else now - timedelta(days=30)
        stmt = select(
            MgStockMouvement.date_mouvement,
            MgStockMouvement.type_mouvement,
            MgStockMouvement.quantite,
        ).where(MgStockMouvement.date_mouvement >= range_start)
        if agence_id:
            stmt = stmt.where(MgStockMouvement.agence_id == agence_id)
        if famille_id:
            stmt = stmt.join(MgArticle, MgArticle.id == MgStockMouvement.article_id).where(
                MgArticle.famille_id == famille_id
            )
        rows = (await self.db.execute(stmt)).all()

        result: list[dict] = []
        for label, start, end in buckets:
            entrees = 0.0
            sorties = 0.0
            for dt, typ, qty in rows:
                if dt is None:
                    continue
                if start <= dt < end:
                    q = float(qty or 0)
                    if typ == "ENTREE":
                        entrees += q
                    elif typ == "SORTIE":
                        sorties += q
            result.append({"label": label, "entrees": as_qty(entrees), "sorties": as_qty(sorties)})
        return result

    async def _conso_par_famille(self, *, agence_id: uuid.UUID | None = None) -> list[dict]:
        stmt = (
            select(MgArticleFamille.libelle, func.coalesce(func.sum(MgStockMouvement.quantite), 0))
            .join(MgArticle, MgArticle.famille_id == MgArticleFamille.id)
            .join(MgStockMouvement, MgStockMouvement.article_id == MgArticle.id)
            .where(MgStockMouvement.type_mouvement == "SORTIE", MgArticle.is_active.is_(True))
            .group_by(MgArticleFamille.libelle)
            .order_by(MgArticleFamille.libelle)
        )
        if agence_id:
            stmt = stmt.where(MgStockMouvement.agence_id == agence_id)
        rows = (await self.db.execute(stmt)).all()
        return [{"label": r[0], "value": as_qty(r[1] or 0)} for r in rows]

    async def _conso_par_agence(self) -> list[dict]:
        stmt = (
            select(Agence.libelle, func.coalesce(func.sum(MgStockMouvement.quantite), 0))
            .join(MgStockMouvement, MgStockMouvement.agence_id == Agence.id)
            .join(MgArticle, MgArticle.id == MgStockMouvement.article_id)
            .where(MgStockMouvement.type_mouvement == "SORTIE", MgArticle.is_active.is_(True))
            .group_by(Agence.libelle)
            .order_by(Agence.libelle)
        )
        rows = (await self.db.execute(stmt)).all()
        return [{"label": r[0], "value": as_qty(r[1] or 0)} for r in rows]

    async def _conso_par_mois(self, *, agence_id: uuid.UUID | None = None) -> list[dict]:
        year = datetime.now(timezone.utc).year
        stmt = (
            select(
                func.extract("month", MgStockMouvement.date_mouvement).label("mois"),
                func.coalesce(func.sum(MgStockMouvement.quantite), 0),
            )
            .join(MgArticle, MgArticle.id == MgStockMouvement.article_id)
            .where(MgStockMouvement.type_mouvement == "SORTIE", MgArticle.is_active.is_(True))
            .where(func.extract("year", MgStockMouvement.date_mouvement) == year)
            .group_by("mois")
            .order_by("mois")
        )
        if agence_id:
            stmt = stmt.where(MgStockMouvement.agence_id == agence_id)
        rows = (await self.db.execute(stmt)).all()
        return [{"label": f"{int(r[0]):02d}/{year}", "value": as_qty(r[1] or 0)} for r in rows]
