"""Service Stock & Fournitures (Moyens Généraux)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
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
)
from app.schemas.mg_stock import (
    ArticleCreate,
    ArticleUpdate,
    DemandeCreate,
    DemandeLigneIn,
    DemandeUpdate,
    InventaireCreate,
    InventaireLigneIn,
    MouvementCreate,
    ParametreUpdate,
)

MOUVEMENT_TYPES = frozenset({"ENTREE", "SORTIE", "AJUSTEMENT", "INVENTAIRE"})
DEMANDE_STATUTS = frozenset(
    {"BROUILLON", "SOUMIS", "VISA_AGENCE", "VISA_MG", "ACCORDEE", "CLOTUREE", "REJETEE", "ANNULEE"}
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

    async def list_articles(
        self,
        *,
        q: str | None = None,
        famille_id: uuid.UUID | None = None,
        agence_id: uuid.UUID | None = None,
        bas_stock: bool = False,
    ) -> list[MgArticle]:
        stmt: Select = select(MgArticle).where(
            MgArticle.is_active.is_(True), MgArticle.deleted_at.is_(None)
        )
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                (MgArticle.code.ilike(like)) | (MgArticle.designation.ilike(like))
            )
        if famille_id:
            stmt = stmt.where(MgArticle.famille_id == famille_id)
        if agence_id:
            stmt = stmt.where(MgArticle.agence_id == agence_id)
        if bas_stock:
            stmt = stmt.where(MgArticle.stock_actuel <= MgArticle.stock_min)
        stmt = stmt.order_by(MgArticle.code)
        return list((await self.db.execute(stmt)).scalars().all())

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
            stock_actuel=Decimal("0"),
            stock_min=data.stock_min,
            stock_max=data.stock_max,
            agence_id=data.agence_id,
            emplacement=data.emplacement,
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

    async def update_article(self, article_id: uuid.UUID, data: ArticleUpdate) -> MgArticle:
        article = await self.db.get(MgArticle, article_id)
        if article is None or article.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Article introuvable")
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(article, key, value)
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
        )
        await self.db.commit()
        await self.db.refresh(mvt)
        return mvt

    async def list_mouvements(
        self,
        *,
        article_id: uuid.UUID | None = None,
        type_mouvement: str | None = None,
        agence_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[MgStockMouvement]:
        stmt = select(MgStockMouvement).order_by(MgStockMouvement.date_mouvement.desc()).limit(limit)
        if article_id:
            stmt = stmt.where(MgStockMouvement.article_id == article_id)
        if type_mouvement:
            stmt = stmt.where(MgStockMouvement.type_mouvement == type_mouvement.upper())
        if agence_id:
            stmt = stmt.where(MgStockMouvement.agence_id == agence_id)
        return list((await self.db.execute(stmt)).scalars().all())

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

    async def transition_demande(
        self, demande_id: uuid.UUID, action: str, user: User, lignes: list[DemandeLigneIn] | None
    ) -> MgDemandeFourniture:
        demande = await self.get_demande(demande_id)
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
                by_des = {l.designation: l for l in lignes}
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
            demande.statut = "ACCORDEE"
            demande.visa_mg_at = now
            demande.visa_mg_by = user.id
            await self._sortie_from_demande(demande, user)
            demande.statut = "CLOTUREE"
        elif action == "rejeter":
            if demande.statut in {"CLOTUREE", "ANNULEE", "REJETEE"}:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Statut incompatible")
            demande.statut = "REJETEE"
        elif action == "annuler":
            if demande.statut == "CLOTUREE":
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Déjà clôturée")
            demande.statut = "ANNULEE"
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Action inconnue")

        await self.db.commit()
        return await self.get_demande(demande_id)

    async def list_demandes(
        self, *, statut: str | None = None, agence_id: uuid.UUID | None = None
    ) -> list[MgDemandeFourniture]:
        stmt = (
            select(MgDemandeFourniture)
            .options(selectinload(MgDemandeFourniture.lignes))
            .where(MgDemandeFourniture.deleted_at.is_(None))
            .order_by(MgDemandeFourniture.date_demande.desc())
        )
        if statut:
            stmt = stmt.where(MgDemandeFourniture.statut == statut.upper())
        if agence_id:
            stmt = stmt.where(MgDemandeFourniture.agence_id == agence_id)
        return list((await self.db.execute(stmt)).scalars().unique().all())

    async def get_demande(self, demande_id: uuid.UUID) -> MgDemandeFourniture:
        stmt = (
            select(MgDemandeFourniture)
            .options(selectinload(MgDemandeFourniture.lignes))
            .where(MgDemandeFourniture.id == demande_id)
        )
        demande = (await self.db.execute(stmt)).scalar_one_or_none()
        if demande is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Demande introuvable")
        return demande

    async def dashboard(
        self, *, agence_id: uuid.UUID | None = None, famille_id: uuid.UUID | None = None
    ) -> dict:
        articles = await self.list_articles(agence_id=agence_id, famille_id=famille_id)
        faible = sum(1 for a in articles if self.niveau_stock(a) == "faible")
        epuise = sum(1 for a in articles if self.niveau_stock(a) == "epuise")
        dem_stmt = (
            select(func.count())
            .select_from(MgDemandeFourniture)
            .where(
                MgDemandeFourniture.deleted_at.is_(None),
                MgDemandeFourniture.statut.in_(
                    ["BROUILLON", "SOUMIS", "VISA_AGENCE", "VISA_MG", "ACCORDEE"]
                ),
            )
        )
        if agence_id:
            dem_stmt = dem_stmt.where(MgDemandeFourniture.agence_id == agence_id)
        demandes_en_cours = await self.db.scalar(dem_stmt)
        start_month = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        mvt_stmt = (
            select(func.count())
            .select_from(MgStockMouvement)
            .where(
                MgStockMouvement.date_mouvement >= start_month,
                MgStockMouvement.type_mouvement == "SORTIE",
            )
        )
        if agence_id:
            mvt_stmt = mvt_stmt.where(MgStockMouvement.agence_id == agence_id)
        mouvements_mois = await self.db.scalar(mvt_stmt)
        return {
            "articles_total": len(articles),
            "stock_faible": faible,
            "stock_epuise": epuise,
            "demandes_en_cours": int(demandes_en_cours or 0),
            "mouvements_mois": int(mouvements_mois or 0),
            "conso_par_famille": await self._conso_par_famille(agence_id=agence_id),
            "conso_par_agence": await self._conso_par_agence(),
            "conso_par_mois": await self._conso_par_mois(agence_id=agence_id),
        }

    async def list_alertes(
        self, *, agence_id: uuid.UUID | None = None
    ) -> list[dict]:
        articles = await self.list_articles(bas_stock=True, agence_id=agence_id)
        return [
            {
                "article_id": a.id,
                "code": a.code,
                "designation": a.designation,
                "stock_actuel": a.stock_actuel,
                "stock_min": a.stock_min,
                "niveau": self.niveau_stock(a),
                "agence_id": a.agence_id,
            }
            for a in articles
        ]

    async def list_parametres(self) -> list[MgStockParametre]:
        stmt = select(MgStockParametre).order_by(MgStockParametre.cle)
        return list((await self.db.execute(stmt)).scalars().all())

    async def update_parametre(self, cle: str, data: ParametreUpdate) -> MgStockParametre:
        row = await self.db.scalar(select(MgStockParametre).where(MgStockParametre.cle == cle))
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paramètre introuvable")
        row.valeur = data.valeur.strip()
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def list_inventaires(self, *, statut: str | None = None) -> list[MgInventaire]:
        stmt = (
            select(MgInventaire)
            .options(selectinload(MgInventaire.lignes).selectinload(MgInventaireLigne.article))
            .where(MgInventaire.deleted_at.is_(None))
            .order_by(MgInventaire.date_debut.desc())
        )
        if statut:
            stmt = stmt.where(MgInventaire.statut == statut.upper())
        return list((await self.db.execute(stmt)).scalars().unique().all())

    async def get_inventaire(self, inventaire_id: uuid.UUID) -> MgInventaire:
        stmt = (
            select(MgInventaire)
            .options(selectinload(MgInventaire.lignes).selectinload(MgInventaireLigne.article))
            .where(MgInventaire.id == inventaire_id)
        )
        inv = (await self.db.execute(stmt)).scalar_one_or_none()
        if inv is None or inv.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Inventaire introuvable")
        return inv

    async def create_inventaire(self, data: InventaireCreate, user: User) -> MgInventaire:
        ref = await self._next_inventaire_ref()
        inv = MgInventaire(
            reference=ref,
            libelle=data.libelle.strip(),
            date_debut=data.date_debut or date.today(),
            agence_id=data.agence_id,
            statut="OUVERT",
            observation=data.observation,
            created_by=user.id,
        )
        self.db.add(inv)
        await self.db.flush()

        articles = await self.list_articles(agence_id=data.agence_id, famille_id=data.famille_id)
        for i, article in enumerate(articles):
            theo = Decimal(article.stock_actuel or 0)
            self.db.add(
                MgInventaireLigne(
                    inventaire_id=inv.id,
                    article_id=article.id,
                    stock_theorique=theo,
                    stock_physique=None,
                    ecart=None,
                    sort_order=i,
                )
            )
        await self.db.commit()
        return await self.get_inventaire(inv.id)

    async def saisir_inventaire(
        self, inventaire_id: uuid.UUID, lignes: list[InventaireLigneIn]
    ) -> MgInventaire:
        inv = await self.get_inventaire(inventaire_id)
        if inv.statut not in {"OUVERT", "EN_COURS"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Inventaire non modifiable")
        by_id = {row.id: row for row in inv.lignes}
        for payload in lignes:
            row = by_id.get(payload.id)
            if row is None:
                continue
            row.stock_physique = Decimal(payload.stock_physique)
            row.ecart = row.stock_physique - Decimal(row.stock_theorique or 0)
            if payload.observation is not None:
                row.observation = payload.observation
        inv.statut = "EN_COURS"
        await self.db.commit()
        return await self.get_inventaire(inventaire_id)

    async def cloturer_inventaire(self, inventaire_id: uuid.UUID, user: User) -> MgInventaire:
        inv = await self.get_inventaire(inventaire_id)
        if inv.statut not in {"OUVERT", "EN_COURS"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Inventaire déjà clôturé")
        missing = [l for l in inv.lignes if l.stock_physique is None]
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"{len(missing)} ligne(s) sans comptage physique",
            )
        for ligne in inv.lignes:
            article = await self.db.scalar(
                select(MgArticle)
                .where(MgArticle.id == ligne.article_id, MgArticle.deleted_at.is_(None))
                .with_for_update()
            )
            if article is None:
                continue
            physique = Decimal(ligne.stock_physique or 0)
            await self._apply_mouvement(
                article=article,
                type_mouvement="INVENTAIRE",
                quantite=physique,
                agence_id=inv.agence_id or article.agence_id,
                initiateur=user,
                motif=f"Inventaire {inv.reference}",
                observation=f"théorique={ligne.stock_theorique} physique={physique}",
                source_type="inventaire",
                source_id=inv.id,
                allow_zero=True,
                force_stock=physique,
            )
        inv.statut = "CLOTURE"
        inv.date_fin = date.today()
        inv.cloture_at = datetime.now(timezone.utc)
        inv.cloture_by = user.id
        await self.db.commit()
        return await self.get_inventaire(inventaire_id)

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
                    "quantite": float(r.quantite or 0),
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
            article = await self.db.scalar(
                select(MgArticle)
                .where(MgArticle.id == ligne.article_id, MgArticle.deleted_at.is_(None))
                .with_for_update()
            )
            if article is None:
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
    ) -> MgStockMouvement:
        qty = Decimal(quantite)
        if qty < 0 or (qty == 0 and not allow_zero):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Quantité invalide")
        current = Decimal(article.stock_actuel or 0)
        if type_mouvement == "ENTREE":
            article.stock_actuel = current + qty
        elif type_mouvement == "SORTIE":
            if current < qty:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuffisant ({current}) pour {article.code}",
                )
            article.stock_actuel = current - qty
        elif type_mouvement == "AJUSTEMENT":
            article.stock_actuel = current + qty
        elif type_mouvement == "INVENTAIRE":
            article.stock_actuel = force_stock if force_stock is not None else qty
            qty = Decimal(article.stock_actuel or 0)
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Type invalide")

        # Mouvement journal : quantité 0 autorisée uniquement inventaire → stocker 0
        mvt_qty = qty if qty > 0 else Decimal("0")
        if mvt_qty == 0 and type_mouvement != "INVENTAIRE":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Quantité invalide")

        ref = await self._next_mvt_ref(type_mouvement)
        mvt = MgStockMouvement(
            reference=ref,
            date_mouvement=date_mouvement or datetime.now(timezone.utc),
            type_mouvement=type_mouvement,
            article_id=article.id,
            quantite=mvt_qty if mvt_qty > 0 else Decimal("0.000"),
            agence_id=agence_id,
            departement=departement,
            initiateur_id=initiateur.id if initiateur else None,
            motif=motif,
            observation=observation,
            source_type=source_type,
            source_id=source_id,
        )
        self.db.add(mvt)
        await self.db.flush()
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

    async def _next_inventaire_ref(self) -> str:
        year = datetime.now(timezone.utc).year
        count = await self.db.scalar(
            select(func.count())
            .select_from(MgInventaire)
            .where(MgInventaire.reference.like(f"INVCP-{year}-%"))
        )
        return f"INVCP-{year}-{(count or 0) + 1:05d}"

    async def _conso_par_famille(self, *, agence_id: uuid.UUID | None = None) -> list[dict]:
        stmt = (
            select(MgArticleFamille.libelle, func.coalesce(func.sum(MgStockMouvement.quantite), 0))
            .join(MgArticle, MgArticle.famille_id == MgArticleFamille.id)
            .join(MgStockMouvement, MgStockMouvement.article_id == MgArticle.id)
            .where(MgStockMouvement.type_mouvement == "SORTIE")
            .group_by(MgArticleFamille.libelle)
            .order_by(MgArticleFamille.libelle)
        )
        if agence_id:
            stmt = stmt.where(MgStockMouvement.agence_id == agence_id)
        rows = (await self.db.execute(stmt)).all()
        return [{"label": r[0], "value": float(r[1] or 0)} for r in rows]

    async def _conso_par_agence(self) -> list[dict]:
        stmt = (
            select(Agence.libelle, func.coalesce(func.sum(MgStockMouvement.quantite), 0))
            .join(MgStockMouvement, MgStockMouvement.agence_id == Agence.id)
            .where(MgStockMouvement.type_mouvement == "SORTIE")
            .group_by(Agence.libelle)
            .order_by(Agence.libelle)
        )
        rows = (await self.db.execute(stmt)).all()
        return [{"label": r[0], "value": float(r[1] or 0)} for r in rows]

    async def _conso_par_mois(self, *, agence_id: uuid.UUID | None = None) -> list[dict]:
        year = datetime.now(timezone.utc).year
        stmt = (
            select(
                func.extract("month", MgStockMouvement.date_mouvement).label("mois"),
                func.coalesce(func.sum(MgStockMouvement.quantite), 0),
            )
            .where(MgStockMouvement.type_mouvement == "SORTIE")
            .where(func.extract("year", MgStockMouvement.date_mouvement) == year)
            .group_by("mois")
            .order_by("mois")
        )
        if agence_id:
            stmt = stmt.where(MgStockMouvement.agence_id == agence_id)
        rows = (await self.db.execute(stmt)).all()
        return [{"label": f"{int(r[0]):02d}/{year}", "value": float(r[1] or 0)} for r in rows]
