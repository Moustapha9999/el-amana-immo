"""Sortie de stock (Stock & Fournitures) : destination, demandeur, motif configurable.

Une seule opération, deux destinations exclusives :
- DEPARTEMENT : entité de l'organigramme (``org_entite_id``) + service facultatif de son sous-arbre ;
- AGENCE : agence BEA (``agence_id``), sans département ni service.

Référentiels CORE réutilisés (``departements``, ``agences``, ``users``) : aucune liste locale.
Le stock n'est décrémenté qu'à travers ``MgStockService._apply_mouvement``, dans la même transaction
que la création du mouvement, l'article étant verrouillé (``FOR UPDATE``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.auth import Agence, User
from app.models.mg_stock import MgArticle, MgStockMotifSortie, MgStockMouvement, MgStockParametre
from app.models.organisation import OrgAffectation, OrgEntite
from app.schemas.mg_stock import MotifSortieCreate, MotifSortieUpdate, SortieCreate
from app.schemas.nombres import format_qty
from app.services import org_referentiel as org
from app.services.mg_stock_service import MgStockService

DESTINATIONS = ("DEPARTEMENT", "AGENCE")
TYPES_DEPARTEMENT = frozenset({"DIRECTION_GENERALE", "DIRECTION", "DEPARTEMENT"})
TYPES_SERVICE = frozenset({"SERVICE", "SECTION", "CELLULE"})
# Unités mesurées (poids, volume, longueur) : seules à accepter une quantité décimale.
UNITES_FRACTIONNABLES = frozenset(
    {"KG", "G", "GR", "L", "LITRE", "LITRES", "CL", "ML", "M", "METRE", "METRES", "M2", "M3"}
)
PARAM_DEMANDEUR_LIBRE = "sortie_demandeur_libre"
SOURCE_SORTIE = "sortie_manuelle"


@dataclass(frozen=True)
class Destination:
    type: str
    departement_id: uuid.UUID | None
    service_id: uuid.UUID | None
    agence_id: uuid.UUID | None


def normaliser_destination(data: SortieCreate) -> Destination:
    """Ne garde que les champs de la destination choisie ; les champs masqués à l'écran sont ignorés."""
    if data.destination_type == "DEPARTEMENT":
        if data.departement_id is None:
            raise AppError("Choisissez le département destinataire.", code="DEPARTEMENT_OBLIGATOIRE")
        return Destination("DEPARTEMENT", data.departement_id, data.service_id, None)
    if data.agence_id is None:
        raise AppError("Choisissez l'agence destinataire.", code="AGENCE_OBLIGATOIRE")
    return Destination("AGENCE", None, None, data.agence_id)


def quantite_entiere_requise(uom: str | None) -> bool:
    return (uom or "U").strip().upper().replace(".", "") not in UNITES_FRACTIONNABLES


def libelle_unite(uom: str | None, quantite: Decimal) -> str:
    u = (uom or "U").strip()
    if u.upper() in {"U", "UNITE", "UNITES", "UNITÉ", "UNITÉS"}:
        return "unité" if quantite <= 1 else "unités"
    return u


def verifier_quantite(quantite: Decimal, uom: str | None, stock: Decimal) -> None:
    if quantite <= 0:
        raise AppError("La quantité doit être strictement positive.", code="QUANTITE_INVALIDE")
    if quantite_entiere_requise(uom) and quantite != quantite.to_integral_value():
        raise AppError(
            f"Cet article se compte à l'unité ({uom or 'U'}) : saisissez une quantité entière.",
            code="QUANTITE_ENTIERE",
        )
    if quantite > stock:
        raise AppError(
            f"Stock insuffisant. Stock disponible : {format_qty(stock)} {libelle_unite(uom, stock)}. "
            f"Quantité demandée : {format_qty(quantite)} {libelle_unite(uom, quantite)}.",
            code="STOCK_INSUFFISANT",
        )


def demandeur_libre_autorise(valeur: str | None) -> bool:
    return (valeur or "1").strip().lower() not in {"0", "non", "false", "no"}


class MgStockSortieService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ référentiels
    async def demandeur_libre(self) -> bool:
        valeur = await self.db.scalar(
            select(MgStockParametre.valeur).where(MgStockParametre.cle == PARAM_DEMANDEUR_LIBRE)
        )
        return demandeur_libre_autorise(valeur)

    async def articles_disponibles(self) -> list[MgArticle]:
        stmt = (
            select(MgArticle)
            .where(
                MgArticle.deleted_at.is_(None),
                MgArticle.is_active.is_(True),
                MgArticle.stockable.is_(True),
                MgArticle.stock_actuel > 0,
            )
            .order_by(MgArticle.code)
        )
        return list((await self.db.scalars(stmt)).all())

    async def list_motifs(
        self, *, actifs_seulement: bool = True, sens: str | None = "SORTIE"
    ) -> list[MgStockMotifSortie]:
        stmt = select(MgStockMotifSortie).where(MgStockMotifSortie.deleted_at.is_(None))
        if sens:
            stmt = stmt.where(MgStockMotifSortie.sens == sens)
        if actifs_seulement:
            stmt = stmt.where(MgStockMotifSortie.is_active.is_(True))
        stmt = stmt.order_by(MgStockMotifSortie.ordre, MgStockMotifSortie.libelle)
        return list((await self.db.scalars(stmt)).all())

    async def rechercher_demandeurs(self, q: str, *, limite: int = 20) -> list[dict]:
        motif = f"%{q.strip()}%"
        users = (
            await self.db.scalars(
                select(User)
                .where(
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                    or_(User.full_name.ilike(motif), User.email.ilike(motif)),
                )
                .order_by(User.full_name)
                .limit(limite)
            )
        ).all()
        if not users:
            return []
        affectations = (
            await self.db.execute(
                select(OrgAffectation.user_id, OrgEntite.libelle)
                .join(OrgEntite, OrgEntite.id == OrgAffectation.entite_id)
                .where(
                    OrgAffectation.user_id.in_([u.id for u in users]),
                    OrgAffectation.actif.is_(True),
                    OrgAffectation.type_affectation == "PRINCIPALE",
                )
            )
        ).all()
        entites = {uid: libelle for uid, libelle in affectations}
        return [
            {"id": str(u.id), "nom": u.full_name, "email": u.email, "entite": entites.get(u.id)}
            for u in users
        ]

    # ----------------------------------------------------------------------- motifs
    async def create_motif(self, data: MotifSortieCreate) -> MgStockMotifSortie:
        code = data.code.strip().upper()
        if await self.db.scalar(select(MgStockMotifSortie.id).where(MgStockMotifSortie.code == code)):
            raise AppError("Code motif déjà utilisé.", 409, code="MOTIF_EXISTANT")
        motif = MgStockMotifSortie(
            code=code,
            sens=data.sens,
            libelle=data.libelle.strip(),
            observation_obligatoire=data.observation_obligatoire,
            ordre=data.ordre,
        )
        self.db.add(motif)
        await self.db.commit()
        await self.db.refresh(motif)
        return motif

    async def update_motif(self, motif_id: uuid.UUID, data: MotifSortieUpdate) -> MgStockMotifSortie:
        motif = await self.db.get(MgStockMotifSortie, motif_id)
        if motif is None or motif.deleted_at is not None:
            raise AppError("Motif introuvable.", 404, code="MOTIF_INTROUVABLE")
        champs = data.model_dump(exclude_unset=True)
        if "libelle" in champs:
            motif.libelle = champs["libelle"].strip()
        for cle in ("observation_obligatoire", "ordre", "is_active"):
            if cle in champs and champs[cle] is not None:
                setattr(motif, cle, champs[cle])
        await self.db.commit()
        await self.db.refresh(motif)
        return motif

    # ------------------------------------------------------------------------ sortie
    async def creer(
        self, data: SortieCreate, user: User, *, cle_idempotence: str | None = None
    ) -> tuple[MgStockMouvement, bool]:
        """Crée la sortie et décrémente le stock une seule fois. Renvoie (mouvement, rejoué)."""
        destination = normaliser_destination(data)
        cle = (cle_idempotence or "").strip()[:120] or None

        # Verrou article d'abord : deux envois de la même action sont sérialisés sur cette ligne,
        # le second retrouve alors la sortie déjà validée au lieu d'en créer une autre.
        article = await self.db.scalar(
            select(MgArticle).where(MgArticle.id == data.article_id).with_for_update()
        )
        if cle:
            existante = await self.db.scalar(
                select(MgStockMouvement).where(MgStockMouvement.cle_idempotence == cle)
            )
            if existante is not None:
                return existante, True
        if article is None or article.deleted_at is not None:
            raise AppError("Article introuvable.", 404, code="ARTICLE_INTROUVABLE")
        if not article.is_active or not getattr(article, "stockable", True):
            raise AppError(
                f"L'article {article.code} a été désactivé ou n'est pas stockable : sortie impossible.",
                code="ARTICLE_INACTIF",
            )

        motif = await self._motif(data.motif_id)
        observation = (data.observation or "").strip() or None
        if motif.observation_obligatoire and not observation:
            raise AppError(
                f"Le motif « {motif.libelle} » exige une observation.", code="OBSERVATION_OBLIGATOIRE"
            )
        departement, service = await self._verifier_departement(destination)
        if destination.type == "AGENCE":
            await self._agence(destination.agence_id)
        demandeur_id, demandeur_nom = await self._demandeur(data)

        stock = Decimal(article.stock_actuel or 0)
        if data.stock_attendu is not None and Decimal(data.stock_attendu) != stock:
            raise AppError(
                f"Le stock de {article.code} a changé depuis l'ouverture du formulaire "
                f"({format_qty(data.stock_attendu)} → {format_qty(stock)}). Vérifiez la quantité puis validez à nouveau.",
                409,
                code="STOCK_MODIFIE",
            )
        quantite = Decimal(data.quantite)
        verifier_quantite(quantite, article.uom, stock)

        mvt = await MgStockService(self.db)._apply_mouvement(
            article=article,
            type_mouvement="SORTIE",
            quantite=quantite,
            agence_id=destination.agence_id,
            initiateur=user,
            motif=motif.libelle,
            observation=observation,
            departement=departement.libelle if departement else None,
            source_type=SOURCE_SORTIE,
            extra={
                "destination_type": destination.type,
                "org_entite_id": departement.id if departement else None,
                "service_id": service.id if service else None,
                "demandeur_id": demandeur_id,
                "demandeur_nom": demandeur_nom,
                "motif_id": motif.id,
                "cle_idempotence": cle,
            },
        )
        await self.db.commit()
        await self.db.refresh(mvt)
        return mvt, False

    async def _motif(self, motif_id: uuid.UUID, sens: str = "SORTIE") -> MgStockMotifSortie:
        motif = await self.db.get(MgStockMotifSortie, motif_id)
        if (
            motif is None
            or motif.deleted_at is not None
            or not motif.is_active
            or (getattr(motif, "sens", None) or "SORTIE") != sens
        ):
            libelle = "d'entrée" if sens == "ENTREE" else "de sortie"
            raise AppError(f"Motif {libelle} invalide ou désactivé.", code="MOTIF_INVALIDE")
        return motif

    async def _verifier_departement(
        self, destination: Destination
    ) -> tuple[OrgEntite | None, OrgEntite | None]:
        if destination.type != "DEPARTEMENT":
            return None, None
        departement = await self.db.get(OrgEntite, destination.departement_id)
        if (
            departement is None
            or departement.deleted_at is not None
            or not departement.is_active
            or departement.type_entite not in TYPES_DEPARTEMENT
        ):
            raise AppError("Département destinataire invalide ou désactivé.", code="DEPARTEMENT_INVALIDE")
        if destination.service_id is None:
            return departement, None
        service = await self.db.get(OrgEntite, destination.service_id)
        if (
            service is None
            or service.deleted_at is not None
            or not service.is_active
            or service.type_entite not in TYPES_SERVICE
        ):
            raise AppError("Service invalide ou désactivé.", code="SERVICE_INVALIDE")
        if service.id not in await org.sous_arbre(self.db, departement.id):
            raise AppError(
                f"Le service « {service.libelle} » n'appartient pas à « {departement.libelle} ».",
                code="SERVICE_HORS_DEPARTEMENT",
            )
        return departement, service

    async def _agence(self, agence_id: uuid.UUID | None) -> Agence:
        agence = await self.db.get(Agence, agence_id) if agence_id else None
        if agence is None or agence.deleted_at is not None or not agence.is_active:
            raise AppError("Agence destinataire invalide ou désactivée.", code="AGENCE_INVALIDE")
        return agence

    async def _demandeur(self, data: SortieCreate) -> tuple[uuid.UUID | None, str]:
        if data.demandeur_id is not None:
            demandeur = await self.db.get(User, data.demandeur_id)
            if demandeur is None or demandeur.deleted_at is not None or not demandeur.is_active:
                raise AppError("Demandeur introuvable ou compte désactivé.", code="DEMANDEUR_INVALIDE")
            return demandeur.id, demandeur.full_name
        nom = " ".join((data.demandeur_nom or "").split())
        if len(nom) < 3:
            raise AppError("Indiquez la personne qui a demandé l'article.", code="DEMANDEUR_OBLIGATOIRE")
        if not await self.demandeur_libre():
            raise AppError(
                "Sélectionnez le demandeur parmi les utilisateurs BEA DIGITAL (saisie libre désactivée).",
                code="DEMANDEUR_REFERENCE_REQUIS",
            )
        return None, nom
