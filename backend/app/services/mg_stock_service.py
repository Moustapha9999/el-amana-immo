"""Service Stock & Fournitures (Moyens Généraux)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
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
    FamilleCreate,
    FamilleUpdate,
    InventaireCreate,
    InventaireLigneIn,
    MouvementCreate,
    ParametreCreate,
    ParametreUpdate,
    ReceptionBcIn,
)

MOUVEMENT_TYPES = frozenset({"ENTREE", "SORTIE", "AJUSTEMENT", "INVENTAIRE"})
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

    async def update_article(self, article_id: uuid.UUID, data: ArticleUpdate) -> MgArticle:
        article = await self.db.get(MgArticle, article_id)
        if article is None or article.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Article introuvable")
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(article, key, value)
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
        )
        await self.db.commit()
        await self.db.refresh(mvt)
        return mvt

    async def list_bons_reception(self) -> list:
        """Bons VALIDE|PARTIEL disponibles pour réception stock."""
        from app.models.mg_ops import MgBonCommande

        stmt = (
            select(MgBonCommande)
            .options(selectinload(MgBonCommande.lignes))
            .where(
                MgBonCommande.deleted_at.is_(None),
                MgBonCommande.statut.in_(["VALIDE", "PARTIEL"]),
            )
            .order_by(MgBonCommande.date_bc.desc())
        )
        return list((await self.db.execute(stmt)).scalars().unique().all())

    async def receive_from_bc(self, bon_id: uuid.UUID, data: ReceptionBcIn, user: User) -> dict:
        from app.models.mg_ops import MgBonCommande

        bon = await self.db.scalar(
            select(MgBonCommande)
            .options(selectinload(MgBonCommande.lignes))
            .where(MgBonCommande.id == bon_id, MgBonCommande.deleted_at.is_(None))
        )
        if bon is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bon de commande introuvable")
        if bon.statut not in {"VALIDE", "PARTIEL"}:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Statut incompatible pour réception ({bon.statut})",
            )

        by_id = {ligne.id: ligne for ligne in bon.lignes}
        motif = data.motif or f"Réception {bon.reference}"
        mouvements_count = 0

        for payload in data.lignes:
            ligne = by_id.get(payload.ligne_id)
            if ligne is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Ligne {payload.ligne_id} absente du bon",
                )
            article_id = payload.article_id or ligne.article_id
            if article_id is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Article requis pour la ligne {ligne.description}",
                )
            deja = Decimal(ligne.quantite_recue or 0)
            reste = Decimal(ligne.quantite or 0) - deja
            if payload.quantite > reste:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Quantité {payload.quantite} > reste {reste} "
                        f"pour « {ligne.description} »"
                    ),
                )
            article = await self.db.scalar(
                select(MgArticle)
                .where(MgArticle.id == article_id, MgArticle.deleted_at.is_(None))
                .with_for_update()
            )
            if article is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Article introuvable")
            await self._apply_mouvement(
                article=article,
                type_mouvement="ENTREE",
                quantite=payload.quantite,
                agence_id=data.agence_id or article.agence_id,
                initiateur=user,
                motif=motif,
                source_type="bon_commande",
                source_id=bon.id,
            )
            ligne.quantite_recue = deja + Decimal(payload.quantite)
            if ligne.article_id is None:
                ligne.article_id = article_id
            mouvements_count += 1

        if all(
            Decimal(l.quantite_recue or 0) >= Decimal(l.quantite or 0) for l in bon.lignes
        ):
            bon.statut = "RECU"
        else:
            bon.statut = "PARTIEL"

        await self.db.commit()
        # Reload with lignes for response serialization
        bon = await self.db.scalar(
            select(MgBonCommande)
            .options(selectinload(MgBonCommande.lignes))
            .where(MgBonCommande.id == bon_id)
        )
        return {"bon": bon, "mouvements_count": mouvements_count}

    async def list_mouvements(
        self,
        *,
        article_id: uuid.UUID | None = None,
        type_mouvement: str | None = None,
        agence_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[MgStockMouvement], int]:
        filters = []
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
        out: list[dict] = []
        for m in mouvements:
            article = articles.get(m.article_id)
            initiateur = users.get(m.initiateur_id) if m.initiateur_id else None
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
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[MgDemandeFourniture], int]:
        filters = [MgDemandeFourniture.deleted_at.is_(None)]
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

        async def _count_demandes(statuts: list[str]) -> int:
            stmt = (
                select(func.count())
                .select_from(MgDemandeFourniture)
                .where(
                    MgDemandeFourniture.deleted_at.is_(None),
                    MgDemandeFourniture.statut.in_(statuts),
                )
            )
            if agence_id:
                stmt = stmt.where(MgDemandeFourniture.agence_id == agence_id)
            return int(await self.db.scalar(stmt) or 0)

        demandes_en_attente = await _count_demandes(
            ["BROUILLON", "SOUMIS", "VISA_AGENCE", "VISA_MG", "PREPARATION", "ACCORDEE"]
        )
        demandes_en_cours = await _count_demandes(["PREPARATION", "SERVIE"])
        demandes_validees = await _count_demandes(["ARCHIVEE", "CLOTUREE"])
        demandes_rejetees = await _count_demandes(["REJETEE", "ANNULEE"])

        inv_stmt = (
            select(MgInventaire)
            .options(selectinload(MgInventaire.lignes))
            .where(
                MgInventaire.deleted_at.is_(None),
                MgInventaire.statut.in_(["OUVERT", "EN_COURS"]),
            )
        )
        if agence_id:
            inv_stmt = inv_stmt.where(MgInventaire.agence_id == agence_id)
        inventaires = list((await self.db.execute(inv_stmt)).scalars().unique().all())
        inventaires_en_cours = len(inventaires)
        total_lignes = sum(len(inv.lignes or []) for inv in inventaires)
        saisies = sum(
            1
            for inv in inventaires
            for ligne in (inv.lignes or [])
            if ligne.stock_physique is not None
        )
        inventaire_progression = (
            round(100.0 * saisies / total_lignes, 1) if total_lignes else 0.0
        )

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
        }

    async def list_alertes(
        self, *, agence_id: uuid.UUID | None = None
    ) -> list[dict]:
        articles, _ = await self.list_articles(bas_stock=True, agence_id=agence_id, size=500)
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

        articles, _ = await self.list_articles(
            agence_id=data.agence_id, famille_id=data.famille_id, size=500
        )
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
            result.append({"label": label, "entrees": entrees, "sorties": sorties})
        return result

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
