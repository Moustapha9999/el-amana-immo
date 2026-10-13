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

from datetime import UTC as _UTC, date, datetime, time, timedelta

from sqlalchemy import Select, func, or_, select
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
    ClienteleSituation,
    Permission,
    User,
)
from app.models.associations import role_permissions_table, user_roles_table
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
# Regroupements d'affichage des statuts existants ; aucun statut supplémentaire n'est créé.
GROUPES = {
    "OUVERTES": ("NOUVELLE", "A_ANALYSER", "EN_INVESTIGATION"),
    "A_EXAMINER": ("NOUVELLE", "A_ANALYSER"),
    "EN_ANALYSE": ("EN_INVESTIGATION",),
    "CONFIRMEE": ("CONFIRMEE",),
    "ECARTEE": ("FAUX_POSITIF", "REJETEE"),
    "CLOTUREE": ("CLOTUREE",),
}
MOTIF_ORION = "LISTE_INTERDICTION"
PERMS_AGENT = ("clientele.filtrage.decide", "clientele.admin")


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

    async def entrees(self, liste_id: uuid.UUID, page: int = 1, taille: int = 50,
                      recherche: str | None = None) -> dict:
        self.ctx.exiger("clientele.filtrage.view")
        if not await self.db.get(ClienteleFiltrageListe, liste_id):
            raise AppError("Liste introuvable", 404, code="NOT_FOUND")
        page, taille = max(1, page), min(max(1, taille), 200)
        q = select(ClienteleFiltrageEntree).where(ClienteleFiltrageEntree.liste_id == liste_id)
        if recherche and recherche.strip():
            t = f"%{recherche.strip()}%"
            q = q.where(or_(ClienteleFiltrageEntree.nom.ilike(t), ClienteleFiltrageEntree.prenom.ilike(t),
                            ClienteleFiltrageEntree.raison_sociale.ilike(t),
                            ClienteleFiltrageEntree.identifiant.ilike(t)))
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
        out = self._entree_dict(e)
        await self.svc.audit("clientele.filtrage.liste_entree", "clientele_filtrage_entree", str(e.id),
                             after={"liste": liste.code, **out})
        return out

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

    def _filtrer(self, q: Select, *, racine: str | None, motif: str | None, source: str | None,
                 profil: str | None, agence: str | None, assignee: str | None, du: date | None,
                 au: date | None, anciennete_min: int | None, recherche: str | None,
                 population: Any = None) -> Select:
        if population is not None:
            q = q.where(ClienteleAlerte.racine_client.in_(population))
        if racine:
            q = q.where(ClienteleAlerte.racine_client == racine.strip())
        if motif:
            q = q.where(ClienteleAlerte.motif == motif)
        if source == "ORION":
            q = q.where(ClienteleAlerte.motif == MOTIF_ORION)
        elif source == "LISTE":
            q = q.where(ClienteleAlerte.motif != MOTIF_ORION)
        if profil in ("PP", "PM", "NON_IDENTIFIE"):
            q = q.where(ClienteleSituation.profil_derive == profil)
        if agence:
            q = q.where(ClienteleSituation.code_agence == agence.strip())
        if assignee == "aucun":
            q = q.where(ClienteleAlerte.assignee_id.is_(None))
        elif assignee == "moi":
            q = q.where(ClienteleAlerte.assignee_id == self.ctx.user.id)
        elif assignee:
            try:
                q = q.where(ClienteleAlerte.assignee_id == uuid.UUID(assignee))
            except ValueError as exc:
                raise AppError("Agent invalide", 422, code="AGENT_INVALIDE") from exc
        if du:
            q = q.where(ClienteleAlerte.created_at >= datetime.combine(du, time.min, tzinfo=_UTC))
        if au:
            q = q.where(ClienteleAlerte.created_at < datetime.combine(au + timedelta(days=1), time.min, tzinfo=_UTC))
        if anciennete_min:
            q = q.where(ClienteleAlerte.created_at <= maintenant() - timedelta(days=int(anciennete_min)))
        if recherche and recherche.strip():
            t = f"%{recherche.strip()}%"
            q = q.where(or_(ClienteleAlerte.racine_client.like(t), ClienteleSituation.nom_client.ilike(t)))
        return q

    async def lister(self, *, statut: str | None = None, racine: str | None = None,
                     motif: str | None = None, groupe: str | None = None, source: str | None = None,
                     profil: str | None = None, agence: str | None = None, assignee: str | None = None,
                     du: date | None = None, au: date | None = None, anciennete_min: int | None = None,
                     q: str | None = None, tri: str | None = None, page: int = 1, taille: int = 50,
                     population: Any = None) -> dict:
        """Les compteurs ``par_statut`` suivent les mêmes filtres que la liste (sauf statut / groupe).

        ``population`` : sous-requête de racines (filtres de la Vue 360°) pour rester cohérent avec ses KPI."""
        self.ctx.exiger("clientele.filtrage.view")
        page, taille = max(1, page), min(max(1, taille), 200)
        criteres = dict(racine=racine, motif=motif, source=source, profil=profil, agence=agence,
                        assignee=assignee, du=du, au=au, anciennete_min=anciennete_min, recherche=q,
                        population=population)
        agent = User.__table__.alias("agent")
        derniere = (select(func.max(ClienteleAlerteEvenement.created_at))
                    .where(ClienteleAlerteEvenement.alerte_id == ClienteleAlerte.id).scalar_subquery())
        base = self._filtrer(
            select(ClienteleAlerte, ClienteleSituation.nom_client, ClienteleSituation.profil_derive,
                   ClienteleSituation.code_agence, agent.c.full_name, derniere.label("derniere_action"))
            .join(ClienteleSituation, ClienteleSituation.racine_client == ClienteleAlerte.racine_client)
            .outerjoin(agent, agent.c.id == ClienteleAlerte.assignee_id), **criteres)
        liste = base
        if statut:
            liste = liste.where(ClienteleAlerte.statut == statut)
        if groupe in GROUPES:
            liste = liste.where(ClienteleAlerte.statut.in_(GROUPES[groupe]))
        total = await self.db.scalar(select(func.count()).select_from(liste.subquery())) or 0
        ordre = {
            "anciennete": (ClienteleAlerte.created_at.asc(),),
            "recent": (ClienteleAlerte.created_at.desc(),),
            "similarite": (ClienteleAlerte.score.desc(), ClienteleAlerte.created_at.asc()),
        }.get(tri or "", (ClienteleAlerte.precedent_faux_positif.desc(), ClienteleAlerte.created_at.desc()))
        rows = (await self.db.execute(
            liste.order_by(*ordre, ClienteleAlerte.id).offset((page - 1) * taille).limit(taille))).all()
        compte = self._filtrer(
            select(ClienteleAlerte.statut, func.count())
            .join(ClienteleSituation, ClienteleSituation.racine_client == ClienteleAlerte.racine_client),
            **criteres).group_by(ClienteleAlerte.statut)
        par_statut = {k: int(v) for k, v in (await self.db.execute(compte)).all()}
        now = maintenant()
        return {
            "total": int(total), "page": page, "taille": taille,
            "par_statut": par_statut,
            "par_groupe": {g: sum(par_statut.get(s, 0) for s in sts) for g, sts in GROUPES.items()},
            "items": [{
                **self._alerte_dict(a), "raison_sociale": nom, "profil": profil_c, "code_agence": ag,
                "source": "ORION" if a.motif == MOTIF_ORION else "LISTE",
                "assignee": nom_agent, "derniere_action": derniere_le.isoformat() if derniere_le else None,
                "anciennete_jours": (now - a.created_at).days if a.created_at else None,
            } for a, nom, profil_c, ag, nom_agent, derniere_le in rows],
        }

    async def agents(self) -> list[dict]:
        """Utilisateurs actifs habilités à décider sur une alerte (cible d'une attribution)."""
        self.ctx.exiger("clientele.filtrage.view")
        habilites = (select(user_roles_table.c.user_id)
                     .join(role_permissions_table, role_permissions_table.c.role_id == user_roles_table.c.role_id)
                     .join(Permission, Permission.id == role_permissions_table.c.permission_id)
                     .where(Permission.code.in_(PERMS_AGENT)))
        rows = (await self.db.execute(
            select(User.id, User.full_name).where(
                User.deleted_at.is_(None), or_(User.is_superuser.is_(True), User.id.in_(habilites)))
            .order_by(User.full_name))).all()
        return [{"id": str(uid), "nom": nom} for uid, nom in rows]

    async def attribuer(self, aid: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.filtrage.decide")
        a = await self.db.get(ClienteleAlerte, aid)
        if not a:
            raise AppError("Alerte introuvable", 404, code="NOT_FOUND")
        if a.statut == "CLOTUREE":
            raise AppError("Alerte clôturée : rouvrir avant de réattribuer", 409, code="ALERTE_CLOTUREE")
        cible_id = payload.get("assignee_id")
        cible = None
        if cible_id:
            cible = await self.db.get(User, uuid.UUID(str(cible_id)))
            if not cible or cible.deleted_at is not None:
                raise AppError("Agent introuvable", 404, code="AGENT_INTROUVABLE")
            if not any(ag["id"] == str(cible.id) for ag in await self.agents()):
                raise AppError("Agent non habilité au traitement des alertes", 422, code="AGENT_NON_HABILITE")
        avant = str(a.assignee_id) if a.assignee_id else None
        if avant == (str(cible.id) if cible else None):
            return await self.detail(aid)
        a.assignee_id = cible.id if cible else None
        a.updated_at = maintenant()
        commentaire = (payload.get("commentaire") or "").strip()
        libelle = f"Attribuée à {cible.full_name}" if cible else "Attribution retirée"
        self.db.add(ClienteleAlerteEvenement(
            alerte_id=a.id, statut=a.statut,
            commentaire=f"{libelle} — {commentaire}" if commentaire else libelle,
            created_by_id=self.ctx.user.id))
        await self.db.flush()
        await self.svc.audit("clientele.filtrage.attribution", "clientele_alerte", a.id,
                             before={"assignee_id": avant}, after={"assignee_id": str(cible.id) if cible else None})
        return await self.detail(aid)

    async def commenter(self, aid: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.filtrage.decide")
        a = await self.db.get(ClienteleAlerte, aid)
        if not a:
            raise AppError("Alerte introuvable", 404, code="NOT_FOUND")
        commentaire = (payload.get("commentaire") or "").strip()
        if not commentaire:
            raise AppError("Commentaire vide", 422, code="COMMENTAIRE_OBLIGATOIRE")
        self.db.add(ClienteleAlerteEvenement(
            alerte_id=a.id, statut=a.statut, commentaire=commentaire[:2000], created_by_id=self.ctx.user.id))
        a.updated_at = maintenant()
        await self.db.flush()
        await self.svc.audit("clientele.filtrage.commentaire", "clientele_alerte", a.id,
                             after={"statut": a.statut})
        return await self.detail(aid)

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
        agent = await self.db.get(User, a.assignee_id) if a.assignee_id else None
        return {
            **self._alerte_dict(a),
            "source": "ORION" if a.motif == MOTIF_ORION else "LISTE",
            "assignee": {"id": str(agent.id), "nom": agent.full_name} if agent else None,
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
        await self.svc.audit("clientele.filtrage.justificatif", "clientele_alerte", aid,
                             after={"justificatif_id": str(j.id), "nom_fichier": safe, "taille": len(contenu)})
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
            "assignee_id": str(a.assignee_id) if a.assignee_id else None,
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
