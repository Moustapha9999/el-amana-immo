"""Entrée de stock (Stock & Fournitures) : provenance, fournisseur, motif configurable.

Quatre provenances exclusives :
- FOURNISSEUR : fournisseur du référentiel CORE (``fournisseurs``) + n° de bon de livraison / facture ;
- RETOUR_DEPARTEMENT : entité de l'organigramme (``org_entite_id``) + service facultatif de son sous-arbre ;
- RETOUR_AGENCE : agence BEA (``agence_id``) ;
- AUTRE : ni fournisseur, ni département, ni agence (don, transfert…), observation obligatoire.

Les réceptions de bons de commande gardent leur propre circuit (``/receptions/bc``).
Le stock n'est incrémenté qu'à travers ``MgStockService._apply_mouvement``, article verrouillé.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from app.core.exceptions import AppError
from app.models.auth import User
from app.models.mg_stock import MgArticle, MgStockMouvement
from app.models.organisation import Fournisseur
from app.schemas.mg_stock import EntreeCreate
from app.schemas.nombres import format_qty
from app.services.mg_stock_service import MgStockService
from app.services.mg_stock_sorties import (
    Destination,
    MgStockSortieService,
    champs_autres,
    normaliser_autres,
    quantite_entiere_requise,
)

SOURCE_ENTREE = "entree_manuelle"


@dataclass(frozen=True)
class Provenance:
    type: str
    fournisseur_id: uuid.UUID | None
    departement_id: uuid.UUID | None
    service_id: uuid.UUID | None
    agence_id: uuid.UUID | None
    departement_autre: str | None = None
    service_autre: str | None = None


def normaliser_provenance(data: EntreeCreate) -> Provenance:
    """Ne garde que les champs de la provenance choisie ; les champs masqués à l'écran sont ignorés."""
    t = data.provenance_type
    if t == "FOURNISSEUR":
        if data.fournisseur_id is None:
            raise AppError("Choisissez le fournisseur.", code="FOURNISSEUR_OBLIGATOIRE")
        return Provenance(t, data.fournisseur_id, None, None, None)
    if t == "RETOUR_DEPARTEMENT":
        dep_id, srv_id, dep_autre, srv_autre = normaliser_autres(
            data.departement_id,
            data.service_id,
            getattr(data, "departement_autre", None),
            getattr(data, "service_autre", None),
            message_obligatoire="Choisissez le département qui retourne l'article.",
        )
        return Provenance(t, None, dep_id, srv_id, None, dep_autre, srv_autre)
    if t == "RETOUR_AGENCE":
        if data.agence_id is None:
            raise AppError("Choisissez l'agence qui retourne l'article.", code="AGENCE_OBLIGATOIRE")
        return Provenance(t, None, None, None, data.agence_id)
    return Provenance("AUTRE", None, None, None, None)


def verifier_quantite_entree(quantite: Decimal, uom: str | None) -> None:
    if quantite <= 0:
        raise AppError("La quantité doit être strictement positive.", code="QUANTITE_INVALIDE")
    if quantite_entiere_requise(uom) and quantite != quantite.to_integral_value():
        raise AppError(
            f"Cet article se compte à l'unité ({uom or 'U'}) : saisissez une quantité entière.",
            code="QUANTITE_ENTIERE",
        )


class MgStockEntreeService(MgStockSortieService):
    async def articles_actifs(self) -> list[MgArticle]:
        stmt = (
            select(MgArticle)
            .where(
                MgArticle.deleted_at.is_(None),
                MgArticle.is_active.is_(True),
                MgArticle.stockable.is_(True),
            )
            .order_by(MgArticle.code)
        )
        return list((await self.db.scalars(stmt)).all())

    async def fournisseurs_actifs(self) -> list[Fournisseur]:
        stmt = (
            select(Fournisseur)
            .where(Fournisseur.deleted_at.is_(None), Fournisseur.is_active.is_(True))
            .order_by(Fournisseur.raison_sociale)
        )
        return list((await self.db.scalars(stmt)).all())

    async def creer(  # type: ignore[override]
        self, data: EntreeCreate, user: User, *, cle_idempotence: str | None = None
    ) -> tuple[MgStockMouvement, bool]:
        """Crée l'entrée et incrémente le stock une seule fois. Renvoie (mouvement, rejoué)."""
        provenance = normaliser_provenance(data)
        cle = (cle_idempotence or "").strip()[:120] or None

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
                f"L'article {article.code} a été désactivé ou n'est pas stockable : entrée impossible.",
                code="ARTICLE_INACTIF",
            )

        motif = await self._motif(data.motif_id, "ENTREE")
        observation = (data.observation or "").strip() or None
        if (motif.observation_obligatoire or provenance.type == "AUTRE") and not observation:
            raise AppError(
                "Précisez l'origine de l'entrée en observation."
                if provenance.type == "AUTRE"
                else f"Le motif « {motif.libelle} » exige une observation.",
                code="OBSERVATION_OBLIGATOIRE",
            )

        fournisseur = await self._fournisseur(provenance.fournisseur_id)
        destination = Destination(
            "DEPARTEMENT" if provenance.type == "RETOUR_DEPARTEMENT" else provenance.type,
            provenance.departement_id,
            provenance.service_id,
            None,
            provenance.departement_autre,
            provenance.service_autre,
        )
        departement, service = await self._verifier_departement(destination)
        if provenance.type == "RETOUR_AGENCE":
            await self._agence(provenance.agence_id)

        stock = Decimal(article.stock_actuel or 0)
        if data.stock_attendu is not None and Decimal(data.stock_attendu) != stock:
            raise AppError(
                f"Le stock de {article.code} a changé depuis l'ouverture du formulaire "
                f"({format_qty(data.stock_attendu)} → {format_qty(stock)}). Vérifiez puis validez à nouveau.",
                409,
                code="STOCK_MODIFIE",
            )
        quantite = Decimal(data.quantite)
        verifier_quantite_entree(quantite, article.uom)

        piece = " ".join((data.piece_reference or "").split()) or None
        remis_par = " ".join((data.remis_par or "").split()) or None
        mvt = await MgStockService(self.db)._apply_mouvement(
            article=article,
            type_mouvement="ENTREE",
            quantite=quantite,
            agence_id=provenance.agence_id,
            initiateur=user,
            motif=motif.libelle,
            observation=observation,
            departement=departement.libelle if departement else provenance.departement_autre,
            source_type=SOURCE_ENTREE,
            extra={
                "provenance_type": provenance.type,
                "fournisseur_id": fournisseur.id if fournisseur else None,
                "piece_reference": piece if fournisseur else None,
                "org_entite_id": departement.id if departement else None,
                "service_id": service.id if service else None,
                **champs_autres(destination),
                "demandeur_nom": remis_par,
                "motif_id": motif.id,
                "cle_idempotence": cle,
            },
        )
        await self.db.commit()
        await self.db.refresh(mvt)
        return mvt, False

    async def _fournisseur(self, fournisseur_id: uuid.UUID | None) -> Fournisseur | None:
        if fournisseur_id is None:
            return None
        fournisseur = await self.db.get(Fournisseur, fournisseur_id)
        if fournisseur is None or fournisseur.deleted_at is not None or not fournisseur.is_active:
            raise AppError("Fournisseur introuvable ou désactivé.", code="FOURNISSEUR_INVALIDE")
        return fournisseur
