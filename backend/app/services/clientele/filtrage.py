"""Filtrage client : correspondance potentielle ≠ correspondance réelle.

Workflow : NOUVELLE → A_ANALYSER → EN_INVESTIGATION → CONFIRMEE | FAUX_POSITIF | REJETEE → CLOTUREE.
Un faux positif est conservé (empreinte) et signalé à une nouvelle occurrence.
"""

from __future__ import annotations

import hashlib
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import (
    ClienteleAlerte,
    ClienteleAlerteEvenement,
    ClienteleAlerteJustificatif,
    ClienteleClient,
    ClienteleCompte,
    ClienteleFiltrageEmpreinte,
    ClienteleFiltrageEntree,
    ClienteleFiltrageListe,
    User,
)
from app.services.clientele.service import Ctx, ClienteleService, maintenant

STATUTS = (
    "NOUVELLE", "A_ANALYSER", "EN_INVESTIGATION", "CONFIRMEE", "FAUX_POSITIF", "REJETEE", "CLOTUREE",
)
TRANSITIONS = {
    "NOUVELLE": ("A_ANALYSER", "REJETEE"),
    "A_ANALYSER": ("EN_INVESTIGATION", "REJETEE", "FAUX_POSITIF"),
    "EN_INVESTIGATION": ("CONFIRMEE", "FAUX_POSITIF", "REJETEE"),
    "CONFIRMEE": ("CLOTUREE",),
    "FAUX_POSITIF": ("CLOTUREE",),
    "REJETEE": ("CLOTUREE",),
    "CLOTUREE": ("A_ANALYSER",),
}
INTERDICTION_VIDE = frozenset({"", "-", "NON", "N", "AUCUN", "NEANT", "NÉANT", "NULL"})


def normaliser(texte: str | None) -> str:
    s = unicodedata.normalize("NFKD", texte or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split())


def empreinte_de(*parts: str) -> str:
    brut = "|".join(parts)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:80]


class ClienteleFiltrageService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    def _dossier(self, aid: uuid.UUID) -> Path:
        p = Path(get_settings().upload_dir) / "clientele" / "alertes" / str(aid)
        p.mkdir(parents=True, exist_ok=True)
        return p

    async def listes(self) -> list[dict]:
        self.ctx.exiger("clientele.filtrage.view")
        rows = list((await self.db.scalars(
            select(ClienteleFiltrageListe).order_by(ClienteleFiltrageListe.code))).all())
        out = []
        for liste in rows:
            n = await self.db.scalar(select(func.count()).select_from(ClienteleFiltrageEntree)
                                     .where(ClienteleFiltrageEntree.liste_id == liste.id,
                                            ClienteleFiltrageEntree.actif.is_(True)))
            out.append({"id": str(liste.id), "code": liste.code, "libelle": liste.libelle,
                        "source": liste.source, "actif": liste.actif, "nb_entrees": int(n or 0)})
        return out

    async def entrees(self, liste_id: uuid.UUID, page: int = 1, taille: int = 50) -> dict:
        self.ctx.exiger("clientele.filtrage.view")
        if not await self.db.get(ClienteleFiltrageListe, liste_id):
            raise AppError("Liste introuvable", 404, code="NOT_FOUND")
        q = select(ClienteleFiltrageEntree).where(ClienteleFiltrageEntree.liste_id == liste_id)
        total = await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = list((await self.db.scalars(
            q.order_by(ClienteleFiltrageEntree.created_at.desc())
            .offset((page - 1) * taille).limit(taille))).all())
        return {"total": int(total), "page": page, "items": [self._entree_dict(e) for e in rows]}

    async def ajouter_entree(self, liste_id: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.filtrage.execute")
        liste = await self.db.get(ClienteleFiltrageListe, liste_id)
        if not liste:
            raise AppError("Liste introuvable", 404, code="NOT_FOUND")
        e = ClienteleFiltrageEntree(
            liste_id=liste_id,
            nom=_coupe(payload.get("nom"), 160),
            prenom=_coupe(payload.get("prenom"), 160),
            raison_sociale=_coupe(payload.get("raison_sociale"), 255),
            nationalite=_coupe(payload.get("nationalite"), 80),
            identifiant=_coupe(payload.get("identifiant"), 80),
            type_identifiant=_coupe(payload.get("type_identifiant"), 12),
        )
        if payload.get("date_naissance"):
            from datetime import date as _date
            e.date_naissance = _date.fromisoformat(str(payload["date_naissance"]))
        self.db.add(e)
        await self.db.flush()
        return self._entree_dict(e)

    async def scanner(self) -> dict:
        self.ctx.exiger("clientele.filtrage.execute")
        crees = 0
        ignores = 0
        crees += await self._scanner_interdiction()
        crees += await self._scanner_listes()
        await self.svc.audit("clientele.filtrage.scan", "clientele_alerte", None,
                             after={"crees": crees, "ignores": ignores})
        return {"alertes_crees": crees, "avertissement": (
            "Une correspondance potentielle n'est pas une correspondance réelle. "
            "Chaque alerte doit être analysée."
        )}

    async def _scanner_interdiction(self) -> int:
        rows = (await self.db.execute(select(ClienteleCompte.racine_client, ClienteleCompte.compte,
                                             ClienteleCompte.liste_interdiction)
                                      .where(ClienteleCompte.liste_interdiction.is_not(None)))).all()
        n = 0
        for racine, compte, liste in rows:
            valeur = (liste or "").strip()
            if valeur.upper() in INTERDICTION_VIDE:
                continue
            emp = empreinte_de("LISTE_INTERDICTION", racine, normaliser(valeur))
            if await self._creer_si_nouvelle(racine, emp, "LISTE_INTERDICTION", 90, {
                "type": "LISTE_INTERDICTION", "compte": compte, "valeur_orion": valeur,
                "potentielle": True,
            }):
                n += 1
        return n

    async def _scanner_listes(self) -> int:
        listes = list((await self.db.scalars(
            select(ClienteleFiltrageListe).where(ClienteleFiltrageListe.actif.is_(True)))).all())
        n = 0
        for liste in listes:
            entrees = list((await self.db.scalars(
                select(ClienteleFiltrageEntree).where(
                    ClienteleFiltrageEntree.liste_id == liste.id,
                    ClienteleFiltrageEntree.actif.is_(True)))).all())
            if not entrees:
                continue
            clients = list((await self.db.scalars(select(ClienteleClient))).all())
            for client in clients:
                for entree in entrees:
                    hit = self._correspond(client, entree)
                    if not hit:
                        continue
                    emp = empreinte_de(liste.code, str(entree.id), client.racine_client, hit["cle"])
                    if await self._creer_si_nouvelle(client.racine_client, emp, hit["motif"], hit["score"], {
                        "type": hit["motif"], "liste": liste.code, "entree_id": str(entree.id),
                        "valeur_liste": hit["valeur_liste"], "valeur_client": hit["valeur_client"],
                        "potentielle": True,
                    }):
                        n += 1
        return n

    def _correspond(self, client: ClienteleClient, entree: ClienteleFiltrageEntree) -> dict | None:
        if entree.identifiant and client.nni and normaliser(entree.identifiant) == normaliser(client.nni):
            return {"motif": "IDENTIFIANT", "score": 100, "cle": "nni",
                    "valeur_liste": entree.identifiant, "valeur_client": client.nni}
        if entree.identifiant and client.nif and normaliser(entree.identifiant) == normaliser(client.nif):
            return {"motif": "IDENTIFIANT", "score": 100, "cle": "nif",
                    "valeur_liste": entree.identifiant, "valeur_client": client.nif}
        nom_liste = normaliser(entree.raison_sociale) or normaliser(
            " ".join(x for x in (entree.nom, entree.prenom) if x))
        nom_client = normaliser(client.raison_sociale)
        if nom_liste and nom_client and nom_liste == nom_client:
            return {"motif": "NOM", "score": 85, "cle": nom_liste,
                    "valeur_liste": nom_liste, "valeur_client": nom_client}
        prenom_client = normaliser(client.prenoms)
        compose = normaliser(f"{client.raison_sociale} {client.prenoms or ''}")
        if nom_liste and compose and nom_liste == compose:
            return {"motif": "NOM", "score": 80, "cle": nom_liste,
                    "valeur_liste": nom_liste, "valeur_client": compose}
        if nom_liste and prenom_client and nom_liste in compose and len(nom_liste) >= 8:
            return {"motif": "NOM_PARTIEL", "score": 55, "cle": nom_liste,
                    "valeur_liste": nom_liste, "valeur_client": compose}
        return None

    async def _creer_si_nouvelle(self, racine: str, emp: str, motif: str, score: int,
                                 correspondance: dict) -> bool:
        ouverte = await self.db.scalar(
            select(ClienteleAlerte).where(
                ClienteleAlerte.racine_client == racine, ClienteleAlerte.empreinte == emp,
                ClienteleAlerte.statut != "CLOTUREE"))
        if ouverte:
            return False
        fp = await self.db.scalar(
            select(ClienteleFiltrageEmpreinte).where(
                ClienteleFiltrageEmpreinte.racine_client == racine,
                ClienteleFiltrageEmpreinte.empreinte == emp,
                ClienteleFiltrageEmpreinte.decision == "FAUX_POSITIF")
            .order_by(ClienteleFiltrageEmpreinte.created_at.desc()).limit(1))
        alerte = ClienteleAlerte(
            racine_client=racine, statut="NOUVELLE", motif=motif, empreinte=emp, score=score,
            correspondance=correspondance, precedent_faux_positif=bool(fp))
        self.db.add(alerte)
        await self.db.flush()
        self.db.add(ClienteleAlerteEvenement(
            alerte_id=alerte.id, statut="NOUVELLE", commentaire=(
                "Occurrence précédente classée faux positif" if fp else "Correspondance potentielle"
            ), created_by_id=self.ctx.user.id))
        await self.db.flush()
        return True

    async def lister(self, *, statut: str | None = None, racine: str | None = None,
                     motif: str | None = None, page: int = 1, taille: int = 50) -> dict:
        self.ctx.exiger("clientele.filtrage.view")
        q = (select(ClienteleAlerte, ClienteleClient.raison_sociale)
             .join(ClienteleClient, ClienteleClient.racine_client == ClienteleAlerte.racine_client))
        if statut:
            q = q.where(ClienteleAlerte.statut == statut)
        if racine:
            q = q.where(ClienteleAlerte.racine_client == racine.strip())
        if motif:
            q = q.where(ClienteleAlerte.motif == motif)
        total = await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = (await self.db.execute(
            q.order_by(ClienteleAlerte.precedent_faux_positif.desc(), ClienteleAlerte.created_at.desc())
            .offset((page - 1) * taille).limit(min(taille, 200))
        )).all()
        par_statut = dict((await self.db.execute(
            select(ClienteleAlerte.statut, func.count()).group_by(ClienteleAlerte.statut)
        )).all())
        return {
            "total": int(total), "page": page, "taille": taille,
            "par_statut": {k: int(v) for k, v in par_statut.items()},
            "items": [{**self._alerte_dict(a), "raison_sociale": nom} for a, nom in rows],
        }

    async def detail(self, aid: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.filtrage.view")
        a = await self.db.get(ClienteleAlerte, aid)
        if not a:
            raise AppError("Alerte introuvable", 404, code="NOT_FOUND")
        client = await self.db.scalar(
            select(ClienteleClient).where(ClienteleClient.racine_client == a.racine_client))
        evts = list((await self.db.execute(
            select(ClienteleAlerteEvenement, User.full_name)
            .outerjoin(User, User.id == ClienteleAlerteEvenement.created_by_id)
            .where(ClienteleAlerteEvenement.alerte_id == aid)
            .order_by(ClienteleAlerteEvenement.created_at)
        )).all())
        justifs = list((await self.db.scalars(
            select(ClienteleAlerteJustificatif).where(ClienteleAlerteJustificatif.alerte_id == aid)
            .order_by(ClienteleAlerteJustificatif.created_at))).all())
        return {
            **self._alerte_dict(a),
            "client": {
                "racine_client": client.racine_client if client else a.racine_client,
                "raison_sociale": client.raison_sociale if client else None,
                "prenoms": client.prenoms if client else None,
                "nationalite": client.nationalite if client else None,
                "date_naissance": client.date_naissance.isoformat() if client and client.date_naissance else None,
                "nni": client.nni if client else None,
                "nif": client.nif if client else None,
            } if client else None,
            "transitions": list(TRANSITIONS.get(a.statut, ())),
            "evenements": [{
                "statut": e.statut, "decision": e.decision, "commentaire": e.commentaire,
                "utilisateur": nom, "date": e.created_at.isoformat() if e.created_at else None,
            } for e, nom in evts],
            "justificatifs": [{"id": str(j.id), "nom_fichier": j.nom_fichier,
                               "date": j.created_at.isoformat() if j.created_at else None} for j in justifs],
        }

    async def decider(self, aid: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.filtrage.decide")
        a = await self.db.get(ClienteleAlerte, aid)
        if not a:
            raise AppError("Alerte introuvable", 404, code="NOT_FOUND")
        statut = (payload.get("statut") or "").upper()
        if statut not in TRANSITIONS.get(a.statut, ()):
            raise AppError(f"Transition refusée : {a.statut} → {statut}", 409, code="TRANSITION_REFUSEE")
        commentaire = (payload.get("commentaire") or "").strip() or None
        if statut in ("CONFIRMEE", "FAUX_POSITIF", "REJETEE", "CLOTUREE") and not commentaire:
            raise AppError("Commentaire obligatoire pour cette décision", 422, code="COMMENTAIRE_OBLIGATOIRE")
        avant = a.statut
        a.statut = statut
        a.updated_at = maintenant()
        if statut == "CLOTUREE":
            a.cloturee_le = a.updated_at
        self.db.add(ClienteleAlerteEvenement(
            alerte_id=a.id, statut=statut, decision=statut, commentaire=commentaire,
            created_by_id=self.ctx.user.id))
        if statut == "FAUX_POSITIF":
            exist = await self.db.scalar(select(ClienteleFiltrageEmpreinte).where(
                ClienteleFiltrageEmpreinte.racine_client == a.racine_client,
                ClienteleFiltrageEmpreinte.empreinte == a.empreinte,
                ClienteleFiltrageEmpreinte.decision == "FAUX_POSITIF"))
            if not exist:
                self.db.add(ClienteleFiltrageEmpreinte(
                    racine_client=a.racine_client, empreinte=a.empreinte, decision="FAUX_POSITIF",
                    alerte_id=a.id, commentaire=commentaire))
        await self.db.flush()
        await self.svc.audit("clientele.filtrage.decision", "clientele_alerte", a.id,
                             before={"statut": avant}, after={"statut": statut})
        return await self.detail(aid)

    async def deposer_justificatif(self, aid: uuid.UUID, contenu: bytes, nom: str) -> dict:
        self.ctx.exiger("clientele.filtrage.decide")
        a = await self.db.get(ClienteleAlerte, aid)
        if not a:
            raise AppError("Alerte introuvable", 404, code="NOT_FOUND")
        if not contenu:
            raise AppError("Fichier vide", 422, code="FICHIER_VIDE")
        safe = Path(nom).name[:180] or "justificatif"
        dest = self._dossier(aid) / f"{uuid.uuid4().hex}_{safe}"
        dest.write_bytes(contenu)
        j = ClienteleAlerteJustificatif(
            alerte_id=aid, nom_fichier=safe, chemin=str(dest), created_by_id=self.ctx.user.id)
        self.db.add(j)
        self.db.add(ClienteleAlerteEvenement(
            alerte_id=aid, statut=a.statut, commentaire=f"Justificatif déposé : {safe}",
            created_by_id=self.ctx.user.id))
        await self.db.flush()
        return await self.detail(aid)

    async def lire_justificatif(self, aid: uuid.UUID, jid: uuid.UUID) -> tuple[bytes, str]:
        self.ctx.exiger("clientele.filtrage.view")
        j = await self.db.get(ClienteleAlerteJustificatif, jid)
        if not j or j.alerte_id != aid:
            raise AppError("Justificatif introuvable", 404, code="NOT_FOUND")
        path = Path(j.chemin)
        if not path.is_file():
            raise AppError("Fichier introuvable", 404, code="FICHIER_ABSENT")
        return path.read_bytes(), j.nom_fichier

    @staticmethod
    def _alerte_dict(a: ClienteleAlerte) -> dict:
        return {
            "id": str(a.id), "racine_client": a.racine_client, "statut": a.statut,
            "motif": a.motif, "score": a.score, "correspondance": a.correspondance,
            "precedent_faux_positif": a.precedent_faux_positif,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            "cloturee_le": a.cloturee_le.isoformat() if a.cloturee_le else None,
        }

    @staticmethod
    def _entree_dict(e: ClienteleFiltrageEntree) -> dict:
        return {
            "id": str(e.id), "liste_id": str(e.liste_id), "nom": e.nom, "prenom": e.prenom,
            "raison_sociale": e.raison_sociale,
            "date_naissance": e.date_naissance.isoformat() if e.date_naissance else None,
            "nationalite": e.nationalite, "identifiant": e.identifiant,
            "type_identifiant": e.type_identifiant, "actif": e.actif,
        }


def _coupe(v: Any, n: int) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s[:n] if s else None
