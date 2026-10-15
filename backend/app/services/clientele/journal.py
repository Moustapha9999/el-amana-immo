"""Journal des actions clients (append-only) : qui, quoi, quand, pourquoi, depuis quelle source."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClienteleClient, ClienteleJournal
from app.models.clientele import ORIGINES_JOURNAL, TYPES_ACTION_JOURNAL
from app.services.clientele.service import Ctx

LIBELLES_ACTION = {
    "CREATION": "Création de la fiche",
    "MAJ_DONNEES": "Mise à jour de données",
    "PROPOSITION": "Proposition de classement",
    "ACCEPTATION": "Proposition acceptée",
    "MODIFICATION": "Classement modifié",
    "REJET": "Proposition rejetée",
    "VERIFICATION": "Envoi en vérification manuelle",
}


def _texte(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    return s or None


async def journaliser(db: AsyncSession, ctx: Ctx, racine: str, type_action: str, *, origine: str,
                      champ: str | None = None, avant: Any = None, apres: Any = None, motif: str | None = None,
                      analyste: str | None = None, lot_id: uuid.UUID | None = None, ligne: int | None = None,
                      groupe_id: uuid.UUID | None = None, detail: dict | None = None) -> None:
    if type_action not in TYPES_ACTION_JOURNAL:
        raise ValueError(f"type_action inconnu : {type_action}")
    if origine not in ORIGINES_JOURNAL:
        raise ValueError(f"origine inconnue : {origine}")
    db.add(ClienteleJournal(
        racine_client=racine, type_action=type_action, champ=champ, ancienne_valeur=_texte(avant),
        nouvelle_valeur=_texte(apres), motif=(motif or "").strip()[:4000] or None,
        analyste_kyc=(analyste or "").strip()[:120] or None, origine=origine, lot_id=lot_id,
        ligne_source=ligne, groupe_id=groupe_id, detail=detail, utilisateur_id=ctx.user.id,
        utilisateur_nom=(ctx.user.full_name or ctx.user.email or "")[:255] or None))
    await db.flush()


def journal_dict(j: ClienteleJournal, nom_client: str | None = None) -> dict:
    return {
        "id": str(j.id), "racine_client": j.racine_client, "nom_client": nom_client,
        "type_action": j.type_action, "libelle_action": LIBELLES_ACTION.get(j.type_action, j.type_action),
        "champ": j.champ, "ancienne_valeur": j.ancienne_valeur, "nouvelle_valeur": j.nouvelle_valeur,
        "motif": j.motif, "analyste_kyc": j.analyste_kyc, "origine": j.origine,
        "lot_id": str(j.lot_id) if j.lot_id else None, "ligne_source": j.ligne_source,
        "groupe_id": str(j.groupe_id) if j.groupe_id else None, "detail": j.detail,
        "utilisateur": j.utilisateur_nom, "date": j.created_at.isoformat() if j.created_at else None,
    }


async def lister_journal(db: AsyncSession, *, racine: str | None = None, lot_id: uuid.UUID | None = None,
                         type_action: str | None = None, origine: str | None = None, page: int = 1,
                         taille: int = 50) -> dict:
    q = (select(ClienteleJournal, ClienteleClient.raison_sociale)
         .outerjoin(ClienteleClient, ClienteleClient.racine_client == ClienteleJournal.racine_client))
    if racine:
        q = q.where(ClienteleJournal.racine_client == racine)
    if lot_id:
        q = q.where(ClienteleJournal.lot_id == lot_id)
    if type_action in TYPES_ACTION_JOURNAL:
        q = q.where(ClienteleJournal.type_action == type_action)
    if origine in ORIGINES_JOURNAL:
        q = q.where(ClienteleJournal.origine == origine)
    page, taille = max(1, page), min(max(1, taille), 500)
    total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = (await db.execute(q.order_by(ClienteleJournal.created_at.desc(), ClienteleJournal.id)
                             .offset((page - 1) * taille).limit(taille))).all()
    return {"total": int(total), "page": page, "taille": taille,
            "items": [journal_dict(j, nom) for j, nom in rows]}
