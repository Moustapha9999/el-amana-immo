"""Référentiel des analystes KYC (import hebdomadaire, décisions de classification).

Un analyste est un nom géré dans l'application, éventuellement relié à un compte utilisateur.
Une valeur saisie ou lue dans un fichier est reconnue si elle correspond (sans accents, casse ni
espaces multiples) au nom d'un analyste actif, ou au nom complet / e-mail du compte relié.
Aucune valeur n'est inventée : une valeur inconnue est une anomalie, jamais une valeur par défaut.
"""

from __future__ import annotations

import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import (
    ClienteleAnalysteKyc,
    ClienteleClassification,
    ClienteleClassifLotLigne,
    ClienteleKyc,
    User,
)
from app.services.clientele.service import Ctx, ClienteleService

MESSAGE_INCONNU = ("Analyste KYC inconnu : « {v} » n'est pas dans le référentiel des analystes "
                   "(Classification › Analystes KYC).")


def normaliser_nom(valeur: str | None) -> str:
    s = unicodedata.normalize("NFKD", str(valeur or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.casefold().split())[:120]


class IndexAnalystes:
    """Correspondance valeur normalisée → nom canonique, pour un contrôle en masse sans requête par ligne."""

    def __init__(self, correspondances: dict[str, str]):
        self.correspondances = correspondances

    def resoudre(self, valeur: str | None) -> str | None:
        cle = normaliser_nom(valeur)
        return self.correspondances.get(cle) if cle else None

    @property
    def vide(self) -> bool:
        return not self.correspondances


class ClienteleAnalysteService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    async def index(self) -> IndexAnalystes:
        rows = (await self.db.execute(
            select(ClienteleAnalysteKyc.nom, ClienteleAnalysteKyc.nom_normalise, User.full_name, User.email)
            .outerjoin(User, User.id == ClienteleAnalysteKyc.user_id)
            .where(ClienteleAnalysteKyc.actif.is_(True))
        )).all()
        corr: dict[str, str] = {}
        for nom, cle, full_name, email in rows:
            for alias in (full_name, email):
                k = normaliser_nom(alias)
                if k:
                    corr.setdefault(k, nom)
        for nom, cle, _f, _e in rows:
            corr[cle] = nom
        return IndexAnalystes(corr)

    async def resoudre(self, valeur: str | None) -> str | None:
        return (await self.index()).resoudre(valeur)

    async def exiger(self, valeur: str | None) -> str:
        """Nom canonique d'un analyste actif, sinon 422 (obligatoire / inconnu)."""
        brut = (valeur or "").strip()
        if not brut:
            raise AppError("Analyste KYC obligatoire : indiquez l'analyste concerné par la décision", 422,
                           code="ANALYSTE_OBLIGATOIRE")
        nom = await self.resoudre(brut)
        if not nom:
            raise AppError(MESSAGE_INCONNU.format(v=brut[:120]), 422, code="ANALYSTE_INCONNU")
        return nom

    async def noms_actifs(self) -> list[str]:
        noms = (await self.db.scalars(
            select(ClienteleAnalysteKyc.nom).where(ClienteleAnalysteKyc.actif.is_(True)))).all()
        return sorted(noms, key=str.casefold)

    async def lister(self) -> dict:
        self.ctx.exiger("clientele.classif.view")
        rows = (await self.db.execute(
            select(ClienteleAnalysteKyc, User.full_name, User.email)
            .outerjoin(User, User.id == ClienteleAnalysteKyc.user_id)
        )).all()
        items = sorted(({
            "id": str(a.id), "nom": a.nom, "actif": a.actif,
            "user_id": str(a.user_id) if a.user_id else None, "utilisateur": full_name, "email": email,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        } for a, full_name, email in rows), key=lambda x: (not x["actif"], x["nom"].casefold()))
        return {"items": items, "candidats": await self._candidats({normaliser_nom(i["nom"]) for i in items})}

    async def _candidats(self, connus: set[str]) -> list[str]:
        """Noms déjà rencontrés (fichiers, décisions) absents du référentiel : à ajouter par un administrateur."""
        vus: dict[str, str] = {}
        for col in (ClienteleClassifLotLigne.analyste_kyc, ClienteleKyc.analyste_kyc,
                    ClienteleClassification.analyste_kyc):
            for v in (await self.db.scalars(select(col).distinct().where(col.is_not(None)))).all():
                k = normaliser_nom(v)
                if k and k not in connus:
                    vus.setdefault(k, v.strip())
        return sorted(vus.values(), key=str.casefold)

    async def utilisateurs(self, q: str | None) -> list[dict]:
        """Comptes actifs proposés pour relier un analyste (20 au plus)."""
        self.ctx.exiger("clientele.classif.admin")
        stmt = select(User.id, User.full_name, User.email).where(User.is_active.is_(True))
        if (q or "").strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where((User.full_name.ilike(like)) | (User.email.ilike(like)))
        rows = (await self.db.execute(stmt.order_by(User.full_name).limit(20))).all()
        return [{"id": str(i), "full_name": n, "email": e} for i, n, e in rows]

    async def _user(self, valeur) -> uuid.UUID | None:
        if not valeur:
            return None
        try:
            uid = uuid.UUID(str(valeur))
        except ValueError:
            raise AppError("Compte utilisateur invalide", 422, code="UTILISATEUR_INVALIDE") from None
        if not await self.db.get(User, uid):
            raise AppError("Compte utilisateur introuvable", 404, code="UTILISATEUR_INTROUVABLE")
        return uid

    async def _nom_libre(self, nom: str, exclure: uuid.UUID | None = None) -> tuple[str, str]:
        nom = " ".join((nom or "").split())[:120]
        cle = normaliser_nom(nom)
        if not cle:
            raise AppError("Nom de l'analyste obligatoire", 422, code="NOM_OBLIGATOIRE")
        existant = await self.db.scalar(
            select(ClienteleAnalysteKyc).where(ClienteleAnalysteKyc.nom_normalise == cle))
        if existant and existant.id != exclure:
            raise AppError(f"L'analyste « {existant.nom} » existe déjà", 409, code="ANALYSTE_EXISTANT")
        return nom, cle

    async def creer(self, payload: dict) -> dict:
        self.ctx.exiger("clientele.classif.admin")
        nom, cle = await self._nom_libre(payload.get("nom") or "")
        a = ClienteleAnalysteKyc(nom=nom, nom_normalise=cle, user_id=await self._user(payload.get("user_id")),
                                 actif=True, created_by_id=self.ctx.user.id)
        self.db.add(a)
        await self.db.flush()
        await self.svc.audit("clientele.analyste.create", "clientele_analyste_kyc", a.id,
                             after={"nom": nom, "user_id": str(a.user_id) if a.user_id else None})
        return await self.lister()

    async def modifier(self, aid: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.classif.admin")
        a = await self.db.get(ClienteleAnalysteKyc, aid)
        if not a:
            raise AppError("Analyste introuvable", 404, code="NOT_FOUND")
        avant = {"nom": a.nom, "actif": a.actif, "user_id": str(a.user_id) if a.user_id else None}
        if "nom" in payload and payload["nom"] is not None:
            a.nom, a.nom_normalise = await self._nom_libre(payload["nom"], exclure=a.id)
        if "user_id" in payload:
            a.user_id = await self._user(payload.get("user_id"))
        if "actif" in payload and payload["actif"] is not None:
            a.actif = bool(payload["actif"])
        await self.db.flush()
        await self.svc.audit("clientele.analyste.update", "clientele_analyste_kyc", a.id, before=avant,
                             after={"nom": a.nom, "actif": a.actif,
                                    "user_id": str(a.user_id) if a.user_id else None})
        return await self.lister()
