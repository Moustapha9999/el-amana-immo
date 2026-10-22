"""Alertes de stock bas (Stock & Fournitures) : détection au franchissement du seuil et suivi.

Règle : un article est « sous le seuil » quand son stock disponible (``mg_articles.stock_actuel``,
tenu à jour par les seuls mouvements validés) est ≤ au seuil (paramètre ``alerte_seuil_unites``,
5 par défaut, dans l'unité de l'article). Le périmètre est la ligne article : un article par
agence / emplacement, les stocks de plusieurs agences ne sont jamais additionnés.

- franchissement vers le bas (> seuil → ≤ seuil) : une alerte (épisode) et une notification ;
- tant que le stock reste ≤ seuil : l'épisode est mis à jour, sans nouvelle notification
  (sauf une fois, le passage en rupture à 0) ;
- retour > seuil : retour à la normale enregistré, l'épisode est fermé ; un franchissement
  ultérieur rouvre un nouvel épisode.

Un seul épisode ouvert par article (index unique partiel), même supprimé : la suppression masque
l'alerte sans boucle de recréation. Les suppressions sont logiques et auditées ; elles ne touchent
ni au stock ni aux mouvements.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models.audit import AuditLog
from app.models.auth import Agence, User
from app.models.mg_stock import MgArticle, MgArticleFamille, MgStockAlerte, MgStockParametre
from app.schemas.nombres import format_qty

PARAM_SEUIL = "alerte_seuil_unites"
PARAM_ACTIF = "alerte_seuil_actif"
SEUIL_DEFAUT = Decimal("5")

TYPE_FAIBLE = "STOCK_FAIBLE"
TYPE_RUPTURE = "RUPTURE"

NOUVELLE, EN_COURS, RESOLUE, CLOTUREE = "NOUVELLE", "EN_COURS", "RESOLUE", "CLOTUREE"
STATUTS = (NOUVELLE, EN_COURS, RESOLUE, CLOTUREE)
STATUTS_A_TRAITER = frozenset({NOUVELLE, EN_COURS})
TRANSITIONS: dict[str, frozenset[str]] = {
    NOUVELLE: frozenset({EN_COURS, RESOLUE, CLOTUREE}),
    EN_COURS: frozenset({RESOLUE, CLOTUREE}),
    RESOLUE: frozenset({EN_COURS, CLOTUREE}),
    CLOTUREE: frozenset({EN_COURS}),
}
LIBELLES_STATUT = {NOUVELLE: "Nouvelle", EN_COURS: "En cours", RESOLUE: "Résolue", CLOTUREE: "Clôturée"}
LIBELLES_TYPE = {TYPE_FAIBLE: "Stock faible", TYPE_RUPTURE: "Rupture de stock"}

FUSEAU = ZoneInfo("Africa/Nouakchott")
ROLES_DESTINATAIRES = frozenset({"stock-fournitures.magasinier", "stock-fournitures.admin"})
PREFIXE_ROLES_MODULE = "stock-fournitures."
ENTITE = "mg_stock_alerte"
SEQUENCE_REFERENCE = "mg_stock_alertes_ref_seq"
LIEN_ALERTES = "/stock-fournitures/alertes"


def niveau_alerte(quantite: Decimal, seuil: Decimal) -> str | None:
    if quantite <= 0:
        return TYPE_RUPTURE
    if quantite <= seuil:
        return TYPE_FAIBLE
    return None


def seuil_depuis_parametre(valeur: str | None) -> Decimal:
    try:
        seuil = Decimal(str(valeur).strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return SEUIL_DEFAUT
    return seuil if seuil >= 0 else SEUIL_DEFAUT


def alertes_activees(valeur: str | None) -> bool:
    return (valeur or "1").strip().lower() not in {"0", "non", "false", "no", "off"}


def verifier_transition(actuel: str, cible: str, *, episode_ouvert: bool) -> None:
    if cible not in STATUTS:
        raise AppError("Statut d'alerte inconnu.", code="ALERTE_STATUT_INVALIDE")
    if cible == actuel:
        return
    if cible not in TRANSITIONS.get(actuel, frozenset()):
        raise AppError(
            f"Passage de « {LIBELLES_STATUT.get(actuel, actuel)} » à « {LIBELLES_STATUT[cible]} » non autorisé.",
            code="ALERTE_TRANSITION_INVALIDE",
        )
    if cible == RESOLUE and episode_ouvert:
        raise AppError(
            "Le stock est toujours sous le seuil : l'alerte sera résolue automatiquement au retour "
            "au-dessus du seuil. Vous pouvez la passer en cours ou la clôturer.",
            code="ALERTE_STOCK_TOUJOURS_BAS",
        )


@dataclass(frozen=True)
class FiltresAlertes:
    statut: str | None = None
    type_alerte: str | None = None
    agence_id: uuid.UUID | None = None
    famille_id: uuid.UUID | None = None
    date_debut: date | None = None
    date_fin: date | None = None
    q: str | None = None
    actives: bool = False
    supprimees: bool = False


class MgStockAlerteService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._seuil_cache: tuple[Decimal | None] | None = None

    # ------------------------------------------------------------------ paramètres
    async def seuil(self) -> Decimal | None:
        """Seuil courant, ``None`` si les alertes sont désactivées."""
        if self._seuil_cache is None:
            rows = dict(
                (
                    await self.db.execute(
                        select(MgStockParametre.cle, MgStockParametre.valeur).where(
                            MgStockParametre.cle.in_((PARAM_SEUIL, PARAM_ACTIF))
                        )
                    )
                ).all()
            )
            seuil = seuil_depuis_parametre(rows.get(PARAM_SEUIL)) if alertes_activees(rows.get(PARAM_ACTIF)) else None
            self._seuil_cache = (seuil,)
        return self._seuil_cache[0]

    # ------------------------------------------------------------------- détection
    async def _episode_ouvert(self, article_id: uuid.UUID) -> MgStockAlerte | None:
        return await self.db.scalar(
            select(MgStockAlerte)
            .where(MgStockAlerte.article_id == article_id, MgStockAlerte.retour_normal_at.is_(None))
            .with_for_update()
        )

    async def evaluer(
        self,
        article: MgArticle,
        *,
        mouvement_id: uuid.UUID | None = None,
        mouvement_reference: str | None = None,
        origine: str = "AUTOMATIQUE",
    ) -> str | None:
        """Applique la règle de seuil au stock réel de l'article. Renvoie l'action menée."""
        if not getattr(article, "stockable", True) or getattr(article, "deleted_at", None) is not None:
            return None
        if getattr(article, "is_active", True) is False:
            return None
        seuil = await self.seuil()
        if seuil is None:
            return None
        quantite = Decimal(article.stock_actuel or 0)
        niveau = niveau_alerte(quantite, seuil)
        episode = await self._episode_ouvert(article.id)
        now = datetime.now(timezone.utc)

        if episode is None:
            if niveau is None:
                return None
            episode = MgStockAlerte(
                reference=await self._prochaine_reference(now),
                article_id=article.id,
                agence_id=article.agence_id,
                emplacement=article.emplacement,
                type_alerte=niveau,
                statut=NOUVELLE,
                origine=origine,
                seuil=seuil,
                quantite_detection=quantite,
                quantite_actuelle=quantite,
                uom=article.uom,
                detectee_at=now,
                rupture_at=now if niveau == TYPE_RUPTURE else None,
                mouvement_id=mouvement_id,
                mouvement_reference=mouvement_reference,
            )
            self.db.add(episode)
            await self.db.flush()
            await self._tracer(None, "alerte_detectee", episode, after=self.snapshot(episode))
            await self._notifier(episode, article)
            return "OUVERTE"

        episode.quantite_actuelle = quantite
        if niveau is None:
            episode.retour_normal_at = now
            episode.quantite_retour = quantite
            if episode.statut in STATUTS_A_TRAITER:
                episode.statut = RESOLUE
                episode.traite_at = now
            await self.db.flush()
            await self._tracer(None, "alerte_retour_normal", episode, after=self.snapshot(episode))
            return "RETOUR"

        episode.type_alerte = niveau
        if niveau == TYPE_RUPTURE and episode.rupture_at is None:
            episode.rupture_at = now
            await self.db.flush()
            if episode.deleted_at is None:
                await self._notifier(episode, article)
            return "RUPTURE"
        await self.db.flush()
        return None

    async def controle(self, user: User | None = None) -> dict:
        """Contrôle complet (activation, rattrapage) : idempotent, une alerte par épisode."""
        seuil = await self.seuil()
        if seuil is None:
            return {"seuil": None, "articles": 0, "ouvertes": 0, "ruptures": 0, "retours": 0}
        articles = (
            await self.db.scalars(
                select(MgArticle)
                .where(
                    MgArticle.deleted_at.is_(None),
                    MgArticle.is_active.is_(True),
                    MgArticle.stockable.is_(True),
                )
                .order_by(MgArticle.code)
                .with_for_update()
            )
        ).all()
        compte = {"OUVERTE": 0, "RUPTURE": 0, "RETOUR": 0}
        for article in articles:
            action = await self.evaluer(article, origine="CONTROLE")
            if action:
                compte[action] += 1
        resultat = {
            "seuil": seuil,
            "articles": len(articles),
            "ouvertes": compte["OUVERTE"],
            "ruptures": compte["RUPTURE"],
            "retours": compte["RETOUR"],
        }
        from app.services.mg_stock_events import audit_stock

        await audit_stock(self.db, user, "alerte_controle", ENTITE, None, after={k: str(v) for k, v in resultat.items()})
        return resultat

    async def _prochaine_reference(self, now: datetime) -> str:
        n = int(await self.db.scalar(select(func.nextval(SEQUENCE_REFERENCE))) or 0)
        return f"ALS-{now.year}-{n:06d}"

    async def _notifier(self, episode: MgStockAlerte, article: MgArticle) -> None:
        from app.services.mg_stock_events import notify_stock_roles

        rupture = episode.type_alerte == TYPE_RUPTURE
        lieu = await self._libelle_lieu(article.agence_id, article.emplacement)
        quand = episode.rupture_at if rupture and episode.rupture_at else episode.detectee_at
        message = (
            f"{article.designation} · {lieu} : {format_qty(episode.quantite_actuelle)} {article.uom or 'U'} "
            f"disponible(s), seuil {format_qty(episode.seuil)}. "
            f"Détectée le {quand.astimezone(FUSEAU):%d/%m/%Y à %H:%M} — alerte {episode.reference}."
        )
        await notify_stock_roles(
            self.db,
            set(ROLES_DESTINATAIRES),
            f"{LIBELLES_TYPE[episode.type_alerte]} — {article.code}",
            message,
            entity=ENTITE,
            entity_id=episode.id,
            event_type="stock.alerte.rupture" if rupture else "stock.alerte.faible",
            priorite="critique" if rupture else "attention",
            destinataire_label="Magasiniers et administrateurs Stock",
        )

    async def _libelle_lieu(self, agence_id: uuid.UUID | None, emplacement: str | None) -> str:
        agence = await self.db.get(Agence, agence_id) if agence_id else None
        base = agence.libelle if agence else "Stock central"
        return f"{base} ({emplacement})" if emplacement else base

    # ---------------------------------------------------------------------- lecture
    def _conditions(self, f: FiltresAlertes) -> list:
        cond = [MgStockAlerte.deleted_at.is_not(None) if f.supprimees else MgStockAlerte.deleted_at.is_(None)]
        if f.statut:
            cond.append(MgStockAlerte.statut == f.statut)
        if f.type_alerte:
            cond.append(MgStockAlerte.type_alerte == f.type_alerte)
        if f.agence_id:
            cond.append(MgStockAlerte.agence_id == f.agence_id)
        if f.famille_id:
            cond.append(MgArticle.famille_id == f.famille_id)
        if f.actives:
            cond.append(MgStockAlerte.retour_normal_at.is_(None))
            cond.append(MgStockAlerte.statut.in_(STATUTS_A_TRAITER))
        if f.date_debut:
            cond.append(MgStockAlerte.detectee_at >= datetime.combine(f.date_debut, time.min, tzinfo=timezone.utc))
        if f.date_fin:
            cond.append(
                MgStockAlerte.detectee_at
                < datetime.combine(f.date_fin + timedelta(days=1), time.min, tzinfo=timezone.utc)
            )
        if f.q and f.q.strip():
            like = f"%{f.q.strip()}%"
            cond.append(
                or_(
                    MgStockAlerte.reference.ilike(like),
                    MgArticle.code.ilike(like),
                    MgArticle.designation.ilike(like),
                    MgArticle.reference.ilike(like),
                )
            )
        return cond

    async def lister(self, f: FiltresAlertes, *, page: int = 1, size: int = 50) -> tuple[list[dict], int]:
        cond = self._conditions(f)
        base = select(MgStockAlerte).join(MgArticle, MgArticle.id == MgStockAlerte.article_id).where(*cond)
        total = int(
            (await self.db.scalar(select(func.count()).select_from(base.order_by(None).subquery()))) or 0
        )
        page, size = max(1, page), max(1, min(size, 500))
        rows = (
            await self.db.scalars(
                base.order_by(MgStockAlerte.detectee_at.desc()).offset((page - 1) * size).limit(size)
            )
        ).all()
        return await self.enrichir(list(rows)), total

    async def kpis(self, *, agence_id: uuid.UUID | None = None, famille_id: uuid.UUID | None = None) -> dict:
        seuil = await self.seuil()
        art = [
            MgArticle.deleted_at.is_(None),
            MgArticle.is_active.is_(True),
            MgArticle.stockable.is_(True),
        ]
        if agence_id:
            art.append(MgArticle.agence_id == agence_id)
        if famille_id:
            art.append(MgArticle.famille_id == famille_id)
        seuil_calcul = seuil if seuil is not None else SEUIL_DEFAUT
        faibles, ruptures = (
            await self.db.execute(
                select(
                    func.count(MgArticle.id).filter(MgArticle.stock_actuel > 0, MgArticle.stock_actuel <= seuil_calcul),
                    func.count(MgArticle.id).filter(MgArticle.stock_actuel <= 0),
                ).where(*art)
            )
        ).one()
        al = [MgStockAlerte.deleted_at.is_(None)]
        if agence_id:
            al.append(MgStockAlerte.agence_id == agence_id)
        if famille_id:
            al.append(MgArticle.famille_id == famille_id)
        par_statut = dict(
            (
                await self.db.execute(
                    select(MgStockAlerte.statut, func.count(MgStockAlerte.id))
                    .join(MgArticle, MgArticle.id == MgStockAlerte.article_id)
                    .where(*al)
                    .group_by(MgStockAlerte.statut)
                )
            ).all()
        )
        return {
            "seuil": seuil_calcul,
            "alertes_actives": seuil is not None,
            "articles_stock_faible": int(faibles or 0),
            "articles_rupture": int(ruptures or 0),
            "alertes_non_traitees": int(par_statut.get(NOUVELLE, 0)),
            "alertes_en_cours": int(par_statut.get(EN_COURS, 0)),
            "alertes_resolues": int(par_statut.get(RESOLUE, 0)),
            "alertes_cloturees": int(par_statut.get(CLOTUREE, 0)),
        }

    async def get(self, alerte_id: uuid.UUID, *, verrou: bool = False, supprimee_ok: bool = False) -> MgStockAlerte:
        stmt = select(MgStockAlerte).where(MgStockAlerte.id == alerte_id)
        if verrou:
            stmt = stmt.with_for_update()
        alerte = await self.db.scalar(stmt)
        if alerte is None or (alerte.deleted_at is not None and not supprimee_ok):
            raise AppError("Alerte introuvable.", 404, code="ALERTE_INTROUVABLE")
        return alerte

    async def historique(self, alerte_id: uuid.UUID) -> list[dict]:
        rows = (
            await self.db.execute(
                select(AuditLog, User.full_name)
                .outerjoin(User, User.id == AuditLog.user_id)
                .where(AuditLog.entity == ENTITE, AuditLog.entity_id == str(alerte_id))
                .order_by(AuditLog.created_at.desc())
            )
        ).all()
        return [
            {
                "action": log.action,
                "user_nom": nom or ("Système" if log.user_id is None else None),
                "created_at": log.created_at,
                "before": log.before_data,
                "after": log.after_data,
            }
            for log, nom in rows
        ]

    async def enrichir(self, alertes: list[MgStockAlerte]) -> list[dict]:
        if not alertes:
            return []
        article_ids = {a.article_id for a in alertes}
        articles = {
            a.id: a for a in (await self.db.scalars(select(MgArticle).where(MgArticle.id.in_(article_ids)))).all()
        }
        famille_ids = {a.famille_id for a in articles.values() if a.famille_id}
        familles = dict(
            (
                await self.db.execute(
                    select(MgArticleFamille.id, MgArticleFamille.libelle).where(MgArticleFamille.id.in_(famille_ids))
                )
            ).all()
        ) if famille_ids else {}
        agence_ids = {a.agence_id for a in alertes if a.agence_id}
        agences = dict(
            (await self.db.execute(select(Agence.id, Agence.libelle).where(Agence.id.in_(agence_ids)))).all()
        ) if agence_ids else {}
        user_ids = {i for a in alertes for i in (a.responsable_id, a.traite_par, a.deleted_by) if i}
        users = dict(
            (await self.db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))).all()
        ) if user_ids else {}
        out = []
        for a in alertes:
            art = articles.get(a.article_id)
            out.append(
                {
                    "id": a.id,
                    "reference": a.reference,
                    "article_id": a.article_id,
                    "article_code": art.code if art else None,
                    "article_reference": art.reference if art else None,
                    "article_designation": art.designation if art else None,
                    "famille_id": art.famille_id if art else None,
                    "famille_libelle": familles.get(art.famille_id) if art else None,
                    "agence_id": a.agence_id,
                    "agence_libelle": agences.get(a.agence_id) if a.agence_id else "Stock central",
                    "emplacement": a.emplacement,
                    "uom": a.uom,
                    "type_alerte": a.type_alerte,
                    "type_libelle": LIBELLES_TYPE.get(a.type_alerte, a.type_alerte),
                    "statut": a.statut,
                    "statut_libelle": LIBELLES_STATUT.get(a.statut, a.statut),
                    "origine": a.origine,
                    "seuil": a.seuil,
                    "quantite_detection": a.quantite_detection,
                    "quantite_actuelle": a.quantite_actuelle,
                    "stock_actuel": art.stock_actuel if art else None,
                    "detectee_at": a.detectee_at,
                    "rupture_at": a.rupture_at,
                    "retour_normal_at": a.retour_normal_at,
                    "quantite_retour": a.quantite_retour,
                    "episode_ouvert": a.retour_normal_at is None,
                    "mouvement_reference": a.mouvement_reference,
                    "responsable_id": a.responsable_id,
                    "responsable_nom": users.get(a.responsable_id) if a.responsable_id else None,
                    "commentaire": a.commentaire,
                    "traite_par_nom": users.get(a.traite_par) if a.traite_par else None,
                    "traite_at": a.traite_at,
                    "deleted_at": a.deleted_at,
                    "deleted_by_nom": users.get(a.deleted_by) if a.deleted_by else None,
                    "motif_suppression": a.motif_suppression,
                    "created_at": a.created_at,
                    "updated_at": a.updated_at,
                }
            )
        return out

    async def responsables(self) -> list[dict]:
        """Utilisateurs actifs titulaires d'un rôle du module : responsables assignables."""
        users = (
            await self.db.scalars(
                select(User)
                .options(selectinload(User.roles))
                .where(User.is_active.is_(True), User.deleted_at.is_(None))
                .order_by(User.full_name)
            )
        ).all()
        return [
            {"id": u.id, "nom": u.full_name or u.email}
            for u in users
            if any((r.code or "").startswith(PREFIXE_ROLES_MODULE) for r in u.roles)
        ]

    async def actives_pour_watcher(self) -> list[dict]:
        rows, _ = await self.lister(FiltresAlertes(actives=True), size=500)
        return rows

    # -------------------------------------------------------------------- écriture
    @staticmethod
    def snapshot(a: MgStockAlerte) -> dict:
        return {
            "reference": a.reference,
            "article_id": str(a.article_id),
            "type_alerte": a.type_alerte,
            "statut": a.statut,
            "seuil": str(a.seuil),
            "quantite_actuelle": str(a.quantite_actuelle),
            "responsable_id": str(a.responsable_id) if a.responsable_id else None,
            "commentaire": a.commentaire,
            "retour_normal_at": a.retour_normal_at.isoformat() if a.retour_normal_at else None,
            "deleted_at": a.deleted_at.isoformat() if a.deleted_at else None,
            "motif_suppression": a.motif_suppression,
        }

    async def _tracer(self, user: User | None, action: str, a: MgStockAlerte, *, before=None, after=None) -> None:
        from app.services.mg_stock_events import audit_stock

        await audit_stock(self.db, user, action, ENTITE, a.id, before=before, after=after)

    async def modifier(self, alerte_id: uuid.UUID, champs: dict, user: User) -> MgStockAlerte:
        alerte = await self.get(alerte_id, verrou=True)
        before = self.snapshot(alerte)
        now = datetime.now(timezone.utc)
        if "statut" in champs and champs["statut"]:
            cible = champs["statut"]
            verifier_transition(alerte.statut, cible, episode_ouvert=alerte.retour_normal_at is None)
            if cible != alerte.statut:
                alerte.statut = cible
                alerte.traite_par = user.id
                alerte.traite_at = now
        if "responsable_id" in champs:
            rid = champs["responsable_id"]
            if rid is not None and rid not in {r["id"] for r in await self.responsables()}:
                raise AppError(
                    "Le responsable doit être un utilisateur actif du module Stock & Fournitures.",
                    code="ALERTE_RESPONSABLE_INVALIDE",
                )
            alerte.responsable_id = rid
        if "commentaire" in champs:
            texte = (champs["commentaire"] or "").strip()
            alerte.commentaire = texte or None
        await self.db.flush()
        await self._tracer(user, "update", alerte, before=before, after=self.snapshot(alerte))
        return alerte

    async def supprimer(self, ids: list[uuid.UUID], motif: str, user: User) -> int:
        motif = (motif or "").strip()
        if len(motif) < 3:
            raise AppError("Indiquez le motif de la suppression.", code="ALERTE_MOTIF_SUPPRESSION")
        ids = list(dict.fromkeys(ids))
        rows = (
            await self.db.scalars(
                select(MgStockAlerte)
                .where(MgStockAlerte.id.in_(ids), MgStockAlerte.deleted_at.is_(None))
                .with_for_update()
            )
        ).all()
        if len(rows) != len(ids):
            raise AppError(
                "Une ou plusieurs alertes sont introuvables ou déjà supprimées : rechargez la liste.",
                404,
                code="ALERTE_INTROUVABLE",
            )
        now = datetime.now(timezone.utc)
        for alerte in rows:
            before = self.snapshot(alerte)
            alerte.deleted_at = now
            alerte.deleted_by = user.id
            alerte.motif_suppression = motif
            await self._tracer(user, "delete", alerte, before=before, after=self.snapshot(alerte))
        await self.db.flush()
        return len(rows)
