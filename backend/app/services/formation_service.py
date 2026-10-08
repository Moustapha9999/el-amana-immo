"""Formation & Sensibilisation — règles métier (référentiels, employés, sessions, présences).

Règles clés :
- présence = PRESENT | ABSENT uniquement, jamais présumée (NULL tant que non saisie) ;
- saisie impossible avant la date de la formation ; REALISEE dès que tous les participants
  sont pointés ; CLOTUREE verrouille (réouverture motivée, ``formation.close``) ;
- modification sensible (présences déjà saisies) = motif obligatoire + audit avant / après ;
- annulation seulement sans présence ; ARCHIVEE depuis CLOTUREE / ANNULEE ;
- ``formation.admin`` supprime définitivement, quel que soit l'état : formations (présences
  comprises), employés (participations comprises), valeurs de référentiel et entités utilisées,
  feuilles signées, historique d'import. Motif obligatoire et audit « avant » complet ;
- concurrence optimiste : chaque mutation porte la ``revision`` connue du client (409).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, String, and_, cast, exists, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models import (
    FormationEmploye,
    FormationEntite,
    FormationParticipant,
    FormationReferentiel,
    FormationSession,
    FormationSessionFormateur,
    FormationSessionTheme,
    User,
)
from app.models.formation import DOMAINES_REFERENTIEL, PRESENCES
from app.services.audit_service import AuditService
from app.services.permission_service import user_has_permission_codes

MODULE_CODE = "formation"
ESPACE_CODE = "audit-controle-conformite"

STATUT_LIBELLES = {
    "PLANIFIEE": "Planifiée",
    "REALISEE": "Réalisée",
    "CLOTUREE": "Clôturée",
    "ANNULEE": "Annulée",
    "ARCHIVEE": "Archivée",
}
DOMAINE_LIBELLES = {
    "THEME": "Thème",
    "FORMATEUR": "Formateur",
    "LIEU": "Lieu",
    "FONCTION": "Fonction",
    "PERIMETRE": "Périmètre",
}


def cle(texte: str | None) -> str:
    """Clé de comparaison : minuscules, sans accents ni ponctuation, espaces réduits."""
    s = unicodedata.normalize("NFKD", texte or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def cle_identite(nom: str | None, prenom: str | None = None) -> str:
    """Jetons du nom complet triés : « Ahmed Mohamed » ≡ « MOHAMED Ahmed »."""
    return " ".join(sorted(cle(f"{prenom or ''} {nom or ''}").split()))


def propre(texte: str | None) -> str:
    return re.sub(r"\s+", " ", (texte or "").strip())


def nom_complet(e: FormationEmploye) -> str:
    return propre(f"{e.prenom or ''} {e.nom}") if e.prenom else e.nom


def maintenant() -> datetime:
    return datetime.now(UTC)


def conflit(message: str, code: str, **extra: Any) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": code, "message": message, **extra})


@dataclass
class Ctx:
    user: User
    permissions: set[str] = field(default_factory=set)
    ip_address: str | None = None
    session_id: uuid.UUID | None = None

    def peut(self, *codes: str) -> bool:
        return bool(self.user.is_superuser) or user_has_permission_codes(self.permissions, *codes)

    def exiger(self, *codes: str) -> None:
        if not self.peut(*codes):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": "Permission refusée", "required": list(codes)},
            )


class Refs:
    """Cache requête des référentiels et entités (tables courtes) pour les libellés."""

    def __init__(self, refs: list[FormationReferentiel], entites: list[FormationEntite]):
        self.refs = {r.id: r for r in refs}
        self.entites = {e.id: e for e in entites}

    @classmethod
    async def charger(cls, db: AsyncSession) -> Refs:
        refs = list((await db.scalars(select(FormationReferentiel))).all())
        entites = list((await db.scalars(select(FormationEntite))).unique().all())
        return cls(refs, entites)

    def lib(self, rid: uuid.UUID | None) -> str | None:
        r = self.refs.get(rid) if rid else None
        return r.libelle if r else None

    def ref(self, rid: uuid.UUID | None) -> dict | None:
        r = self.refs.get(rid) if rid else None
        return {"id": str(r.id), "libelle": r.libelle, "actif": r.actif} if r else None

    def entite(self, eid: uuid.UUID | None) -> dict | None:
        e = self.entites.get(eid) if eid else None
        if not e:
            return None
        return {
            "id": str(e.id),
            "libelle": e.libelle,
            "perimetre_id": str(e.perimetre_id),
            "perimetre": self.lib(e.perimetre_id),
            "lieu_id": str(e.lieu_id) if e.lieu_id else None,
            "lieu": self.lib(e.lieu_id),
            "actif": e.actif,
        }

    def entite_lib(self, eid: uuid.UUID | None) -> str | None:
        e = self.entites.get(eid) if eid else None
        return e.libelle if e else None


def employe_dict(e: FormationEmploye, refs: Refs, stats: dict | None = None) -> dict:
    ent = refs.entite(e.entite_id)
    out = {
        "id": str(e.id),
        "nom": e.nom,
        "prenom": e.prenom,
        "nom_complet": nom_complet(e),
        "fonction_id": str(e.fonction_id) if e.fonction_id else None,
        "fonction": refs.lib(e.fonction_id),
        "entite_id": str(e.entite_id) if e.entite_id else None,
        "entite": ent["libelle"] if ent else None,
        "perimetre_id": ent["perimetre_id"] if ent else None,
        "perimetre": ent["perimetre"] if ent else None,
        "email": e.email,
        "telephone": e.telephone,
        "actif": e.actif,
        "motif_desactivation": e.motif_desactivation,
        "source": e.source,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }
    if stats is not None:
        out.update(stats)
    return out


class FormationService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx

    # ------------------------------------------------------------------ audit
    async def audit(self, action: str, entity: str, entity_id: Any, *, before: dict | None = None,
                    after: dict | None = None) -> None:
        await AuditService(self.db).log(
            user=self.ctx.user, action=action, entity=entity,
            entity_id=str(entity_id) if entity_id else None, before=before, after=after,
            ip_address=self.ctx.ip_address, espace_code=ESPACE_CODE, module_code=MODULE_CODE,
            session_id=self.ctx.session_id,
        )

    # ------------------------------------------------------------ référentiels
    async def lister_referentiels(self, domaine: str | None = None) -> list[dict]:
        q = select(FormationReferentiel).order_by(
            FormationReferentiel.domaine, FormationReferentiel.ordre, FormationReferentiel.libelle)
        if domaine:
            q = q.where(FormationReferentiel.domaine == domaine)
        refs = list((await self.db.scalars(q)).all())
        usages = await self._usages_referentiels()
        return [self._ref_dict(r, usages.get(r.id, 0)) for r in refs]

    @staticmethod
    def _ref_dict(r: FormationReferentiel, usage: int = 0) -> dict:
        return {
            "id": str(r.id), "domaine": r.domaine, "libelle": r.libelle, "description": r.description,
            "ordre": r.ordre, "actif": r.actif, "usage": usage,
        }

    async def _usages_referentiels(self) -> dict[uuid.UUID, int]:
        sql = text(
            """
            SELECT id, sum(n)::int FROM (
              SELECT theme_id AS id, count(*) n FROM formation_session_themes GROUP BY 1
              UNION ALL SELECT formateur_id, count(*) FROM formation_session_formateurs GROUP BY 1
              UNION ALL SELECT lieu_id, count(*) FROM formation_sessions GROUP BY 1
              UNION ALL SELECT fonction_id, count(*) FROM formation_employes WHERE fonction_id IS NOT NULL GROUP BY 1
              UNION ALL SELECT perimetre_id, count(*) FROM formation_entites GROUP BY 1
              UNION ALL SELECT lieu_id, count(*) FROM formation_entites WHERE lieu_id IS NOT NULL GROUP BY 1
            ) u GROUP BY id
            """
        )
        return {row[0]: row[1] for row in (await self.db.execute(sql)).all()}

    async def _ref(self, rid: uuid.UUID, domaine: str | None = None) -> FormationReferentiel:
        r = await self.db.get(FormationReferentiel, rid)
        if not r or (domaine and r.domaine != domaine):
            raise AppError(f"{DOMAINE_LIBELLES.get(domaine or '', 'Valeur')} introuvable", 404, code="NOT_FOUND")
        return r

    async def creer_referentiel(self, domaine: str, libelle: str, description: str | None = None) -> dict:
        self.ctx.exiger("formation.references.manage")
        if domaine not in DOMAINES_REFERENTIEL:
            raise AppError("Domaine de référentiel inconnu", 422, code="DOMAINE_INCONNU")
        libelle = propre(libelle)
        if not cle(libelle):
            raise AppError("Libellé obligatoire", 422, code="LIBELLE_OBLIGATOIRE")
        existant = await self.db.scalar(select(FormationReferentiel).where(
            FormationReferentiel.domaine == domaine, FormationReferentiel.cle == cle(libelle)))
        if existant:
            etat = "" if existant.actif else " (désactivée — réactivez-la)"
            raise conflit(f"« {existant.libelle} » existe déjà{etat}", "REFERENTIEL_EXISTANT",
                          existant=self._ref_dict(existant))
        ordre = await self.db.scalar(select(func.coalesce(func.max(FormationReferentiel.ordre), 0)).where(
            FormationReferentiel.domaine == domaine))
        r = FormationReferentiel(domaine=domaine, libelle=libelle, cle=cle(libelle),
                                 description=propre(description) or None, ordre=(ordre or 0) + 1, actif=True,
                                 created_by_id=self.ctx.user.id, updated_by_id=self.ctx.user.id)
        self.db.add(r)
        await self.db.flush()
        await self.audit("formation.referentiel.create", "formation_referentiel", r.id,
                         after={"domaine": domaine, "libelle": libelle})
        return self._ref_dict(r)

    async def modifier_referentiel(self, rid: uuid.UUID, data: dict) -> dict:
        self.ctx.exiger("formation.references.manage")
        r = await self._ref(rid)
        avant = self._ref_dict(r)
        if "libelle" in data and data["libelle"] is not None:
            libelle = propre(data["libelle"])
            if not cle(libelle):
                raise AppError("Libellé obligatoire", 422, code="LIBELLE_OBLIGATOIRE")
            doublon = await self.db.scalar(select(FormationReferentiel.id).where(
                FormationReferentiel.domaine == r.domaine, FormationReferentiel.cle == cle(libelle),
                FormationReferentiel.id != r.id))
            if doublon:
                raise conflit(f"« {libelle} » existe déjà dans ce référentiel", "REFERENTIEL_EXISTANT")
            r.libelle, r.cle = libelle, cle(libelle)
        if "description" in data:
            r.description = propre(data.get("description")) or None
        if data.get("actif") is not None:
            r.actif = bool(data["actif"])
        if data.get("ordre") is not None:
            r.ordre = int(data["ordre"])
        r.updated_by_id = self.ctx.user.id
        await self.db.flush()
        apres = self._ref_dict(r)
        await self.audit("formation.referentiel.update", "formation_referentiel", r.id, before=avant, after=apres)
        return apres

    async def supprimer_referentiel(self, rid: uuid.UUID, forcer: bool = False) -> None:
        self.ctx.exiger("formation.references.manage")
        r = await self._ref(rid)
        usage = (await self._usages_referentiels()).get(r.id, 0)
        if usage and not (forcer and self.ctx.peut("formation.admin")):
            raise conflit("Valeur utilisée : désactivez-la plutôt que de la supprimer", "REFERENTIEL_UTILISE")
        avant = {**self._ref_dict(r, usage)}
        if usage:
            avant["detachements"] = await self._detacher_referentiel(r)
        await self.db.delete(r)
        await self.db.flush()
        await self.audit("formation.referentiel.delete", "formation_referentiel", rid, before=avant,
                         after={"force": bool(usage)})

    async def _detacher_referentiel(self, r: FormationReferentiel) -> dict:
        """Retire une valeur utilisée de partout avant suppression (administrateur).

        Lieu d'une formation et périmètre d'une entité sont obligatoires : on refuse et on
        oriente vers la fusion (remplacement par une autre valeur).
        """
        p = {"id": r.id}
        if r.domaine == "LIEU":
            n = await self.db.scalar(select(func.count()).where(FormationSession.lieu_id == r.id))
            if n:
                raise conflit(f"Lieu de {n} formation(s) : fusionnez-le d'abord avec un autre lieu",
                              "REFERENTIEL_OBLIGATOIRE", formations=n)
        if r.domaine == "PERIMETRE":
            n = await self.db.scalar(select(func.count()).where(FormationEntite.perimetre_id == r.id))
            if n:
                raise conflit(f"Périmètre de {n} entité(s) : fusionnez-le d'abord avec un autre périmètre",
                              "REFERENTIEL_OBLIGATOIRE", entites=n)
        requetes = {
            "THEME": [("themes_formations", "DELETE FROM formation_session_themes WHERE theme_id = :id")],
            "FORMATEUR": [("formateurs_formations",
                           "DELETE FROM formation_session_formateurs WHERE formateur_id = :id")],
            "FONCTION": [("employes", "UPDATE formation_employes SET fonction_id = NULL WHERE fonction_id = :id"),
                         ("participations",
                          "UPDATE formation_participants SET fonction_id = NULL WHERE fonction_id = :id")],
            "LIEU": [("entites", "UPDATE formation_entites SET lieu_id = NULL WHERE lieu_id = :id")],
            "PERIMETRE": [("participations",
                           "UPDATE formation_participants SET perimetre_id = NULL WHERE perimetre_id = :id")],
        }[r.domaine]
        out = {}
        for cle_, sql in requetes:
            out[cle_] = (await self.db.execute(text(sql), p)).rowcount or 0
        self._expirer_apres_sql(r)
        return out

    def _expirer_apres_sql(self, sauf: object) -> None:
        """Les UPDATE / DELETE SQL directs ne touchent pas les objets déjà chargés : on les périme."""
        classes = (FormationSession, FormationSessionTheme, FormationSessionFormateur, FormationParticipant,
                   FormationEmploye, FormationEntite)
        for obj in list(self.db.identity_map.values()):
            if obj is not sauf and isinstance(obj, classes):
                self.db.expire(obj)

    async def fusionner_referentiel(self, source_id: uuid.UUID, cible_id: uuid.UUID) -> dict:
        """Remplace partout ``source`` par ``cible`` (même domaine) puis désactive la source."""
        self.ctx.exiger("formation.references.manage")
        if source_id == cible_id:
            raise AppError("Choisissez une valeur cible différente", 422, code="FUSION_INVALIDE")
        src, cib = await self._ref(source_id), await self._ref(cible_id)
        if src.domaine != cib.domaine:
            raise AppError("Fusion impossible entre deux référentiels différents", 422, code="FUSION_INVALIDE")
        p = {"s": src.id, "c": cib.id}
        if src.domaine in ("THEME", "FORMATEUR"):
            table, col = (("formation_session_themes", "theme_id") if src.domaine == "THEME"
                          else ("formation_session_formateurs", "formateur_id"))
            await self.db.execute(text(
                f"DELETE FROM {table} t WHERE t.{col} = :s AND EXISTS "
                f"(SELECT 1 FROM {table} x WHERE x.session_id = t.session_id AND x.{col} = :c)"), p)
            await self.db.execute(text(f"UPDATE {table} SET {col} = :c WHERE {col} = :s"), p)
        elif src.domaine == "LIEU":
            await self.db.execute(text("UPDATE formation_sessions SET lieu_id = :c WHERE lieu_id = :s"), p)
            await self.db.execute(text("UPDATE formation_entites SET lieu_id = :c WHERE lieu_id = :s"), p)
        elif src.domaine == "FONCTION":
            await self.db.execute(text("UPDATE formation_employes SET fonction_id = :c WHERE fonction_id = :s"), p)
            await self.db.execute(text("UPDATE formation_participants SET fonction_id = :c WHERE fonction_id = :s"), p)
        elif src.domaine == "PERIMETRE":
            await self.db.execute(text("UPDATE formation_entites SET perimetre_id = :c WHERE perimetre_id = :s"), p)
            await self.db.execute(text(
                "UPDATE formation_participants SET perimetre_id = :c WHERE perimetre_id = :s"), p)
        src.actif = False
        src.updated_by_id = self.ctx.user.id
        await self.db.flush()
        sortie = self._ref_dict(cib)
        trace = ({"source": src.libelle}, {"cible": cib.libelle, "domaine": src.domaine})
        self.db.expire_all()
        await self.audit("formation.referentiel.merge", "formation_referentiel", source_id,
                         before=trace[0], after=trace[1])
        return sortie

    # ---------------------------------------------------------------- entités
    async def lister_entites(self) -> list[dict]:
        refs = await Refs.charger(self.db)
        usage = dict((await self.db.execute(text(
            "SELECT entite_id, count(*)::int FROM formation_employes WHERE entite_id IS NOT NULL GROUP BY 1"
        ))).all())
        ents = sorted(refs.entites.values(), key=lambda e: (e.ordre, e.libelle))
        out = []
        for e in ents:
            d = refs.entite(e.id) or {}
            d.update({"ordre": e.ordre, "agence_id": str(e.agence_id) if e.agence_id else None,
                      "usage": usage.get(e.id, 0)})
            out.append(d)
        return out

    async def _valider_entite(self, data: dict, exclure: uuid.UUID | None = None) -> tuple[str, uuid.UUID, uuid.UUID | None]:
        libelle = propre(data.get("libelle"))
        if not cle(libelle):
            raise AppError("Libellé de l'entité obligatoire", 422, code="LIBELLE_OBLIGATOIRE")
        q = select(FormationEntite.id).where(FormationEntite.cle == cle(libelle))
        if exclure:
            q = q.where(FormationEntite.id != exclure)
        if await self.db.scalar(q):
            raise conflit(f"L'entité « {libelle} » existe déjà", "ENTITE_EXISTANTE")
        if not data.get("perimetre_id"):
            raise AppError("Périmètre obligatoire", 422, code="PERIMETRE_OBLIGATOIRE")
        perimetre = await self._ref(uuid.UUID(str(data["perimetre_id"])), "PERIMETRE")
        lieu_id = None
        if data.get("lieu_id"):
            lieu_id = (await self._ref(uuid.UUID(str(data["lieu_id"])), "LIEU")).id
        return libelle, perimetre.id, lieu_id

    async def creer_entite(self, data: dict) -> dict:
        self.ctx.exiger("formation.references.manage")
        libelle, perimetre_id, lieu_id = await self._valider_entite(data)
        ordre = await self.db.scalar(select(func.coalesce(func.max(FormationEntite.ordre), 0)))
        e = FormationEntite(libelle=libelle, cle=cle(libelle), perimetre_id=perimetre_id, lieu_id=lieu_id,
                            agence_id=data.get("agence_id"), ordre=(ordre or 0) + 1, actif=True,
                            created_by_id=self.ctx.user.id, updated_by_id=self.ctx.user.id)
        self.db.add(e)
        await self.db.flush()
        refs = await Refs.charger(self.db)
        apres = refs.entite(e.id)
        await self.audit("formation.entite.create", "formation_entite", e.id, after=apres)
        return apres or {}

    async def modifier_entite(self, eid: uuid.UUID, data: dict) -> dict:
        self.ctx.exiger("formation.references.manage")
        e = await self.db.get(FormationEntite, eid)
        if not e:
            raise AppError("Entité introuvable", 404, code="NOT_FOUND")
        refs = await Refs.charger(self.db)
        avant = refs.entite(e.id)
        if data.get("actif") is not None and len(data) == 1:
            e.actif = bool(data["actif"])
        else:
            merged = {"libelle": e.libelle, "perimetre_id": e.perimetre_id, "lieu_id": e.lieu_id, **data}
            libelle, perimetre_id, lieu_id = await self._valider_entite(merged, exclure=e.id)
            e.libelle, e.cle, e.perimetre_id, e.lieu_id = libelle, cle(libelle), perimetre_id, lieu_id
            if data.get("actif") is not None:
                e.actif = bool(data["actif"])
            # Participations encore ouvertes : le périmètre suit l'entité (historique clôturé figé).
            await self.db.execute(text(
                """
                UPDATE formation_participants p SET perimetre_id = :per
                FROM formation_sessions s
                WHERE p.session_id = s.id AND p.entite_id = :eid AND s.statut = 'PLANIFIEE'
                """), {"per": perimetre_id, "eid": e.id})
        e.updated_by_id = self.ctx.user.id
        await self.db.flush()
        refs = await Refs.charger(self.db)
        apres = refs.entite(e.id)
        await self.audit("formation.entite.update", "formation_entite", e.id, before=avant, after=apres)
        return apres or {}

    async def supprimer_entite(self, eid: uuid.UUID, forcer: bool = False) -> None:
        self.ctx.exiger("formation.references.manage")
        e = await self.db.get(FormationEntite, eid)
        if not e:
            raise AppError("Entité introuvable", 404, code="NOT_FOUND")
        utilise = await self.db.scalar(select(
            exists().where(FormationEmploye.entite_id == eid)
            | exists().where(FormationParticipant.entite_id == eid)))
        if utilise and not (forcer and self.ctx.peut("formation.admin")):
            raise conflit("Entité utilisée : désactivez-la plutôt que de la supprimer", "ENTITE_UTILISEE")
        avant: dict[str, Any] = {"libelle": e.libelle}
        if utilise:
            p = {"id": eid}
            avant["employes_detaches"] = (await self.db.execute(text(
                "UPDATE formation_employes SET entite_id = NULL WHERE entite_id = :id"), p)).rowcount or 0
            avant["participations_detachees"] = (await self.db.execute(text(
                "UPDATE formation_participants SET entite_id = NULL WHERE entite_id = :id"), p)).rowcount or 0
            self._expirer_apres_sql(e)
        await self.db.delete(e)
        await self.db.flush()
        await self.audit("formation.entite.delete", "formation_entite", eid, before=avant,
                         after={"force": bool(utilise)})

    # --------------------------------------------------------------- employés
    def _stats_employes_subq(self):
        p = FormationParticipant
        s = FormationSession
        return (
            select(
                p.employe_id.label("eid"),
                func.count(p.id).label("nb"),
                func.count(p.id).filter(p.presence == "PRESENT").label("presents"),
                func.count(p.id).filter(p.presence == "ABSENT").label("absents"),
                func.max(s.date_session).filter(p.presence == "PRESENT").label("derniere"),
            )
            .join(s, s.id == p.session_id)
            .where(s.statut != "ANNULEE")
            .group_by(p.employe_id)
            .subquery()
        )

    async def lister_employes(self, *, q: str | None = None, entite_id: uuid.UUID | None = None,
                              perimetre_id: uuid.UUID | None = None, fonction_id: uuid.UUID | None = None,
                              actif: bool | None = True, forme: bool | None = None, tri: str = "nom",
                              sens: str = "asc", page: int = 1, taille: int = 25) -> dict:
        st = self._stats_employes_subq()
        E = FormationEmploye
        base = select(E, st.c.nb, st.c.presents, st.c.absents, st.c.derniere).outerjoin(st, st.c.eid == E.id)
        conds = []
        if q and cle(q):
            for jeton in cle(q).split():
                like = f"%{jeton}%"
                conds.append(or_(E.cle_identite.like(like), func.lower(E.email).like(like),
                                 func.coalesce(E.telephone, "").like(like)))
        if entite_id:
            conds.append(E.entite_id == entite_id)
        if perimetre_id:
            conds.append(E.entite_id.in_(select(FormationEntite.id).where(
                FormationEntite.perimetre_id == perimetre_id)))
        if fonction_id:
            conds.append(E.fonction_id == fonction_id)
        if actif is not None:
            conds.append(E.actif.is_(actif))
        if forme is True:
            conds.append(func.coalesce(st.c.presents, 0) > 0)
        elif forme is False:
            conds.append(func.coalesce(st.c.presents, 0) == 0)
        if conds:
            base = base.where(and_(*conds))
        total = await self.db.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
        tris = {
            "nom": [func.lower(E.nom), func.lower(func.coalesce(E.prenom, ""))],
            "prenom": [func.lower(func.coalesce(E.prenom, "")), func.lower(E.nom)],
            "formations": [func.coalesce(st.c.presents, 0)],
            "derniere": [st.c.derniere],
            "creation": [E.created_at],
        }
        cols = tris.get(tri, tris["nom"])
        ordre = [c.desc().nulls_last() if sens == "desc" else c.asc().nulls_last() for c in cols]
        taille = max(1, min(taille, 500))
        rows = (await self.db.execute(
            base.order_by(*ordre, E.id).offset((max(page, 1) - 1) * taille).limit(taille))).unique().all()
        refs = await Refs.charger(self.db)
        items = [
            employe_dict(e, refs, {"nb_formations": nb or 0, "nb_presents": pr or 0, "nb_absents": ab or 0,
                                   "derniere_formation": der.isoformat() if der else None})
            for e, nb, pr, ab, der in rows
        ]
        return {"items": items, "total": total or 0, "page": page, "taille": taille}

    async def _employe(self, eid: uuid.UUID) -> FormationEmploye:
        e = await self.db.get(FormationEmploye, eid)
        if not e:
            raise AppError("Employé introuvable", 404, code="NOT_FOUND")
        return e

    async def doublons(self, nom: str, prenom: str | None = None, exclure: uuid.UUID | None = None) -> list[dict]:
        """Même clé d'identité (ordre des mots indifférent) ou ≥ 2 mots communs."""
        ident = cle_identite(nom, prenom)
        jetons = [j for j in ident.split() if len(j) > 1]
        if not jetons:
            return []
        E = FormationEmploye
        conds = [E.cle_identite == ident]
        if len(jetons) >= 2:
            conds.append(and_(*[E.cle_identite.like(f"%{j}%") for j in jetons[:2]]))
        q = select(E).where(or_(*conds))
        if exclure:
            q = q.where(E.id != exclure)
        refs = await Refs.charger(self.db)
        out = []
        for e in (await self.db.scalars(q.limit(10))).unique().all():
            communs = set(e.cle_identite.split()) & set(jetons)
            if e.cle_identite == ident or len(communs) >= 2:
                d = employe_dict(e, refs)
                d["identique"] = e.cle_identite == ident
                out.append(d)
        out.sort(key=lambda d: not d["identique"])
        return out

    async def _valider_employe(self, data: dict) -> dict:
        nom = propre(data.get("nom"))
        prenom = propre(data.get("prenom")) or None
        if not cle(nom):
            raise AppError("Le nom est obligatoire", 422, code="NOM_OBLIGATOIRE")
        out = {"nom": nom, "prenom": prenom, "email": (propre(data.get("email")) or None),
               "telephone": propre(data.get("telephone")) or None}
        if out["email"] and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", out["email"]):
            raise AppError("Adresse e-mail invalide", 422, code="EMAIL_INVALIDE")
        out["fonction_id"] = (await self._ref(uuid.UUID(str(data["fonction_id"])), "FONCTION")).id \
            if data.get("fonction_id") else None
        if data.get("entite_id"):
            ent = await self.db.get(FormationEntite, uuid.UUID(str(data["entite_id"])))
            if not ent:
                raise AppError("Entité introuvable", 404, code="NOT_FOUND")
            out["entite_id"] = ent.id
        else:
            out["entite_id"] = None
        return out

    async def creer_employe(self, data: dict, *, forcer: bool = False) -> dict:
        self.ctx.exiger("formation.employees.manage")
        v = await self._valider_employe(data)
        if not forcer:
            cands = await self.doublons(v["nom"], v["prenom"])
            if cands:
                raise conflit("Un employé similaire existe déjà. Vérifiez avant de créer un doublon.",
                              "DOUBLON_EMPLOYE", candidats=cands)
        e = FormationEmploye(**v, cle_identite=cle_identite(v["nom"], v["prenom"]), actif=True, source="MANUEL",
                             created_by_id=self.ctx.user.id, updated_by_id=self.ctx.user.id)
        self.db.add(e)
        await self.db.flush()
        refs = await Refs.charger(self.db)
        apres = employe_dict(e, refs)
        await self.audit("formation.employe.create", "formation_employe", e.id, after=apres)
        return apres

    async def modifier_employe(self, eid: uuid.UUID, data: dict, *, forcer: bool = False) -> dict:
        self.ctx.exiger("formation.employees.manage")
        e = await self._employe(eid)
        refs = await Refs.charger(self.db)
        avant = employe_dict(e, refs)
        v = await self._valider_employe({**{"nom": e.nom, "prenom": e.prenom, "email": e.email,
                                            "telephone": e.telephone, "fonction_id": e.fonction_id,
                                            "entite_id": e.entite_id}, **data})
        nouvelle_cle = cle_identite(v["nom"], v["prenom"])
        if nouvelle_cle != e.cle_identite and not forcer:
            cands = await self.doublons(v["nom"], v["prenom"], exclure=e.id)
            if cands:
                raise conflit("Un autre employé porte ce nom. Confirmez s'il s'agit d'une personne différente.",
                              "DOUBLON_EMPLOYE", candidats=cands)
        for k, val in v.items():
            setattr(e, k, val)
        e.cle_identite = nouvelle_cle
        e.updated_by_id = self.ctx.user.id
        await self._resynchroniser_participations_ouvertes(e)
        await self.db.flush()
        refs = await Refs.charger(self.db)
        apres = employe_dict(e, refs)
        await self.audit("formation.employe.update", "formation_employe", e.id, before=avant, after=apres)
        return apres

    async def _resynchroniser_participations_ouvertes(self, e: FormationEmploye) -> None:
        ent = await self.db.get(FormationEntite, e.entite_id) if e.entite_id else None
        await self.db.execute(
            update(FormationParticipant)
            .where(FormationParticipant.employe_id == e.id,
                   FormationParticipant.session_id.in_(select(FormationSession.id).where(
                       FormationSession.statut == "PLANIFIEE")))
            .values(fonction_id=e.fonction_id, entite_id=e.entite_id,
                    perimetre_id=ent.perimetre_id if ent else None)
        )

    async def activer_employe(self, eid: uuid.UUID, actif: bool, motif: str | None = None) -> dict:
        self.ctx.exiger("formation.employees.manage")
        e = await self._employe(eid)
        if not actif and not propre(motif):
            raise AppError("Motif de désactivation obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        avant = {"actif": e.actif, "motif": e.motif_desactivation}
        e.actif = actif
        e.motif_desactivation = None if actif else propre(motif)
        e.updated_by_id = self.ctx.user.id
        await self.db.flush()
        await self.audit("formation.employe.reactivate" if actif else "formation.employe.deactivate",
                         "formation_employe", e.id, before=avant, after={"actif": actif, "motif": e.motif_desactivation})
        refs = await Refs.charger(self.db)
        return employe_dict(e, refs)

    async def supprimer_employe(self, eid: uuid.UUID, motif: str | None) -> str:
        """Suppression définitive (administrateur) : l'employé et toutes ses participations."""
        self.ctx.exiger("formation.admin")
        motif = propre(motif)
        if not motif:
            raise AppError("Motif obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        e = await self._employe(eid)
        refs = await Refs.charger(self.db)
        avant = employe_dict(e, refs)
        rows = (await self.db.execute(
            select(FormationParticipant, FormationSession.reference, FormationSession.statut)
            .join(FormationSession, FormationSession.id == FormationParticipant.session_id)
            .where(FormationParticipant.employe_id == e.id)
        )).all()
        avant["participations"] = [{"formation": ref, "presence": p.presence} for p, ref, _st in rows]
        sessions_touchees = {p.session_id for p, _r, _s in rows}
        for p, _r, _s in rows:
            await self.db.delete(p)
        await self.db.flush()
        if sessions_touchees:
            for s in (await self.db.scalars(self._q_session().where(
                    FormationSession.id.in_(sessions_touchees)))).unique().all():
                await self.db.refresh(s, ["participants"])
                self._recalculer_statut(s)
                s.revision += 1
        nom = nom_complet(e)
        await self.db.delete(e)
        await self.db.flush()
        await self.audit("formation.employe.delete", "formation_employe", eid, before=avant,
                         after={"motif": motif, "participations_supprimees": len(rows)})
        return nom

    async def fiche_employe(self, eid: uuid.UUID) -> dict:
        e = await self._employe(eid)
        refs = await Refs.charger(self.db)
        rows = (await self.db.execute(
            select(FormationParticipant, FormationSession)
            .join(FormationSession, FormationSession.id == FormationParticipant.session_id)
            .where(FormationParticipant.employe_id == e.id)
            .order_by(FormationSession.date_session.desc())
        )).unique().all()
        historique = []
        nb = presents = absents = 0
        par_theme: dict[str, int] = {}
        for p, s in rows:
            themes = [refs.lib(t.theme_id) for t in s.themes]
            historique.append({
                "participant_id": str(p.id), "session_id": str(s.id), "reference": s.reference,
                "date": s.date_session.isoformat(), "themes": themes, "theme": ", ".join(t for t in themes if t),
                "lieu": refs.lib(s.lieu_id), "formateurs": [refs.lib(f.formateur_id) for f in s.formateurs],
                "presence": p.presence, "statut": s.statut, "statut_libelle": STATUT_LIBELLES.get(s.statut),
                "entite": refs.entite_lib(p.entite_id), "perimetre": refs.lib(p.perimetre_id),
            })
            if s.statut == "ANNULEE":
                continue
            nb += 1
            if p.presence == "PRESENT":
                presents += 1
                for t in themes:
                    if t:
                        par_theme[t] = par_theme.get(t, 0) + 1
            elif p.presence == "ABSENT":
                absents += 1
        saisis = presents + absents
        dernier = next((h["date"] for h in historique if h["presence"] == "PRESENT"), None)
        return {
            **employe_dict(e, refs),
            "stats": {"participations": nb, "presents": presents, "absents": absents,
                      "non_saisis": nb - saisis, "taux_presence": round(presents * 100 / saisis, 1) if saisis else None,
                      "derniere_formation": dernier},
            "par_theme": [{"libelle": k, "valeur": v} for k, v in sorted(par_theme.items(), key=lambda x: -x[1])],
            "historique": historique,
        }

    # --------------------------------------------------------------- sessions
    def _q_session(self) -> Select:
        return select(FormationSession).options(
            selectinload(FormationSession.participants))

    async def _session(self, sid: uuid.UUID, *, verrou: bool = False) -> FormationSession:
        q = self._q_session().where(FormationSession.id == sid)
        if verrou:
            q = q.with_for_update(of=FormationSession)
        s = (await self.db.scalars(q)).unique().first()
        if not s:
            raise AppError("Formation introuvable", 404, code="NOT_FOUND")
        return s

    @staticmethod
    def _verifier_revision(s: FormationSession, revision: int | None) -> None:
        if revision is not None and revision != s.revision:
            raise conflit("Cette formation a été modifiée entre-temps. Rechargez la page avant de continuer.",
                          "CONFLIT_REVISION", revision=s.revision)

    @staticmethod
    def _stats(participants: list[FormationParticipant]) -> dict:
        n = len(participants)
        pr = sum(1 for p in participants if p.presence == "PRESENT")
        ab = sum(1 for p in participants if p.presence == "ABSENT")
        return {"participants": n, "presents": pr, "absents": ab, "non_saisis": n - pr - ab,
                "taux_presence": round(pr * 100 / (pr + ab), 1) if (pr + ab) else None}

    def _actions(self, s: FormationSession) -> dict:
        a_presence = any(p.presence for p in s.participants)
        complet = bool(s.participants) and all(p.presence for p in s.participants)
        ouvert = s.statut in ("PLANIFIEE", "REALISEE")
        passe = s.date_session <= date.today()
        return {
            "modifier": ouvert and self.ctx.peut("formation.update"),
            "participants": ouvert and self.ctx.peut("formation.update"),
            "saisir_presences": ouvert and passe and bool(s.participants) and self.ctx.peut("formation.attendance.manage"),
            "cloturer": s.statut == "REALISEE" and complet and self.ctx.peut("formation.close"),
            "rouvrir": s.statut == "CLOTUREE" and self.ctx.peut("formation.close"),
            "annuler": s.statut == "PLANIFIEE" and not a_presence and self.ctx.peut("formation.cancel"),
            "retablir": s.statut == "ANNULEE" and self.ctx.peut("formation.cancel"),
            "archiver": s.statut in ("CLOTUREE", "ANNULEE") and self.ctx.peut("formation.close"),
            "desarchiver": s.statut == "ARCHIVEE" and self.ctx.peut("formation.close"),
            "retirer_participants": (ouvert and self.ctx.peut("formation.update")) or self.ctx.peut("formation.admin"),
            "supprimer": self.ctx.peut("formation.admin"),
            "exporter": self.ctx.peut("formation.view"),
        }

    def session_dict(self, s: FormationSession, refs: Refs, *, avec_participants: bool = True) -> dict:
        themes = [refs.ref(t.theme_id) for t in s.themes]
        formateurs = [refs.ref(f.formateur_id) for f in s.formateurs]
        out = {
            "id": str(s.id), "reference": s.reference, "intitule": s.intitule,
            "date_session": s.date_session.isoformat(),
            "lieu": refs.ref(s.lieu_id), "themes": [t for t in themes if t],
            "formateurs": [f for f in formateurs if f],
            "theme_libelle": ", ".join(t["libelle"] for t in themes if t),
            "formateur_libelle": " / ".join(f["libelle"] for f in formateurs if f),
            "statut": s.statut, "statut_libelle": STATUT_LIBELLES.get(s.statut, s.statut),
            "a_saisir": s.statut == "PLANIFIEE" and s.date_session <= date.today() and bool(s.participants),
            "a_venir": s.date_session > date.today() and s.statut == "PLANIFIEE",
            "observations": s.observations, "motif_annulation": s.motif_annulation,
            "presences_saisies_le": s.presences_saisies_le.isoformat() if s.presences_saisies_le else None,
            "cloturee_le": s.cloturee_le.isoformat() if s.cloturee_le else None,
            "source": s.source, "revision": s.revision,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "stats": self._stats(s.participants),
            "actions": self._actions(s),
        }
        if avec_participants:
            parts = []
            for i, p in enumerate(sorted(s.participants, key=lambda p: (p.ordre, nom_complet(p.employe).lower())), 1):
                e = p.employe
                parts.append({
                    "id": str(p.id), "n": i, "employe_id": str(e.id), "nom": e.nom, "prenom": e.prenom,
                    "nom_complet": nom_complet(e), "fonction": refs.lib(p.fonction_id),
                    "entite": refs.entite_lib(p.entite_id), "perimetre": refs.lib(p.perimetre_id),
                    "employe_actif": e.actif, "presence": p.presence,
                    "presence_saisie_le": p.presence_saisie_le.isoformat() if p.presence_saisie_le else None,
                })
            out["participants"] = parts
        return out

    async def detail_session(self, sid: uuid.UUID) -> dict:
        s = await self._session(sid)
        return self.session_dict(s, await Refs.charger(self.db))

    async def lister_sessions(self, *, q: str | None = None, statut: str | None = None, annee: int | None = None,
                              date_debut: date | None = None, date_fin: date | None = None,
                              theme_id: uuid.UUID | None = None, formateur_id: uuid.UUID | None = None,
                              lieu_id: uuid.UUID | None = None, entite_id: uuid.UUID | None = None,
                              perimetre_id: uuid.UUID | None = None, employe_id: uuid.UUID | None = None,
                              a_saisir: bool = False, feuille: str | None = None, tri: str = "date",
                              sens: str = "desc", page: int = 1, taille: int = 20) -> dict:
        from app.services import formation_documents

        S = FormationSession
        conds = []
        if statut == "ACTIVES":
            conds.append(S.statut.in_(("PLANIFIEE", "REALISEE", "CLOTUREE")))
        elif statut:
            conds.append(S.statut == statut)
        else:
            conds.append(S.statut != "ARCHIVEE")
        if annee:
            conds.append(func.extract("year", S.date_session) == annee)
        if date_debut:
            conds.append(S.date_session >= date_debut)
        if date_fin:
            conds.append(S.date_session <= date_fin)
        if theme_id:
            conds.append(S.id.in_(select(FormationSessionTheme.session_id).where(
                FormationSessionTheme.theme_id == theme_id)))
        if formateur_id:
            conds.append(S.id.in_(select(FormationSessionFormateur.session_id).where(
                FormationSessionFormateur.formateur_id == formateur_id)))
        if lieu_id:
            conds.append(S.lieu_id == lieu_id)
        P = FormationParticipant
        if entite_id:
            conds.append(S.id.in_(select(P.session_id).where(P.entite_id == entite_id)))
        if perimetre_id:
            conds.append(S.id.in_(select(P.session_id).where(P.perimetre_id == perimetre_id)))
        if employe_id:
            conds.append(S.id.in_(select(P.session_id).where(P.employe_id == employe_id)))
        if a_saisir:
            conds.append(and_(S.statut == "PLANIFIEE", S.date_session <= date.today(),
                              S.id.in_(select(P.session_id))))
        if feuille in ("AVEC", "SANS"):
            avec = cast(S.id, String).in_(formation_documents.sessions_avec_feuille())
            conds.append(avec if feuille == "AVEC" else ~avec)
        if q and cle(q):
            for jeton in cle(q).split():
                like = f"%{jeton}%"
                conds.append(or_(
                    func.lower(S.reference).like(like),
                    func.lower(func.coalesce(S.intitule, "")).like(like),
                    S.lieu_id.in_(select(FormationReferentiel.id).where(FormationReferentiel.cle.like(like))),
                    S.id.in_(select(FormationSessionTheme.session_id).join(
                        FormationReferentiel, FormationReferentiel.id == FormationSessionTheme.theme_id).where(
                        FormationReferentiel.cle.like(like))),
                    S.id.in_(select(FormationSessionFormateur.session_id).join(
                        FormationReferentiel, FormationReferentiel.id == FormationSessionFormateur.formateur_id).where(
                        FormationReferentiel.cle.like(like))),
                ))
        base = select(S).where(and_(*conds)) if conds else select(S)
        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        nb_part = select(func.count(P.id)).where(P.session_id == S.id).scalar_subquery()
        tris = {"date": S.date_session, "reference": S.reference, "statut": S.statut, "participants": nb_part}
        col = tris.get(tri, S.date_session)
        taille = max(1, min(taille, 500))
        q2 = (base.options(selectinload(S.participants))
              .order_by(col.desc() if sens == "desc" else col.asc(), S.reference.desc())
              .offset((max(page, 1) - 1) * taille).limit(taille))
        sessions = list((await self.db.scalars(q2)).unique().all())
        refs = await Refs.charger(self.db)
        feuilles = await formation_documents.compter(self, [s.id for s in sessions])
        items = []
        for s in sessions:
            d = self.session_dict(s, refs, avec_participants=False)
            d["feuilles_signees"] = feuilles.get(str(s.id), 0)
            items.append(d)
        return {"items": items, "total": total or 0, "page": page, "taille": taille}

    async def _reference(self, annee: int) -> str:
        n = await self.db.scalar(text(
            """
            INSERT INTO formation_compteurs (annee, dernier) VALUES (:a, 1)
            ON CONFLICT (annee) DO UPDATE SET dernier = formation_compteurs.dernier + 1
            RETURNING dernier
            """), {"a": annee})
        return f"FOR-{annee}-{int(n):04d}"

    async def _ids_actifs(self, ids: list, domaine: str, libelle: str, *, obligatoire: bool = True) -> list[uuid.UUID]:
        uniques = list(dict.fromkeys(uuid.UUID(str(i)) for i in ids or []))
        if obligatoire and not uniques:
            raise AppError(f"{libelle} obligatoire", 422, code=f"{domaine}_OBLIGATOIRE")
        if uniques:
            trouves = {r.id: r for r in (await self.db.scalars(select(FormationReferentiel).where(
                FormationReferentiel.id.in_(uniques), FormationReferentiel.domaine == domaine))).all()}
            if len(trouves) != len(uniques):
                raise AppError(f"{libelle} introuvable", 422, code=f"{domaine}_INCONNU")
        return uniques

    async def _ajouter_participants(self, s: FormationSession, employe_ids: list, *, autoriser_inactifs: bool = False) -> int:
        ids = list(dict.fromkeys(uuid.UUID(str(i)) for i in employe_ids or []))
        if not ids:
            return 0
        deja = {p.employe_id for p in s.participants}
        employes = (await self.db.scalars(select(FormationEmploye).where(FormationEmploye.id.in_(ids)))).unique().all()
        if len(employes) != len(ids):
            raise AppError("Employé introuvable", 422, code="EMPLOYE_INCONNU")
        inactifs = [nom_complet(e) for e in employes if not e.actif and e.id not in deja]
        if inactifs and not autoriser_inactifs:
            raise AppError(f"Employé(s) désactivé(s) : {', '.join(inactifs[:5])}", 422, code="EMPLOYE_INACTIF")
        entites = {e.id: e for e in (await self.db.scalars(select(FormationEntite))).unique().all()}
        ordre = max((p.ordre for p in s.participants), default=0)
        ajoutes = 0
        par_id = {e.id: e for e in employes}
        for eid in ids:
            if eid in deja:
                continue
            e = par_id[eid]
            ent = entites.get(e.entite_id) if e.entite_id else None
            ordre += 1
            p = FormationParticipant(session_id=s.id, employe_id=e.id, fonction_id=e.fonction_id,
                                     entite_id=e.entite_id, perimetre_id=ent.perimetre_id if ent else None,
                                     ordre=ordre)
            p.employe = e
            s.participants.append(p)
            ajoutes += 1
        return ajoutes

    def _photo(self, s: FormationSession, refs: Refs) -> dict:
        return {
            "date_session": s.date_session.isoformat(), "lieu": refs.lib(s.lieu_id),
            "themes": [refs.lib(t.theme_id) for t in s.themes],
            "formateurs": [refs.lib(f.formateur_id) for f in s.formateurs],
            "intitule": s.intitule, "observations": s.observations, "statut": s.statut,
            "participants": len(s.participants),
        }

    async def creer_session(self, data: dict) -> dict:
        self.ctx.exiger("formation.create")
        d = data.get("date_session")
        if not d:
            raise AppError("Date obligatoire", 422, code="DATE_OBLIGATOIRE")
        themes = await self._ids_actifs(data.get("theme_ids"), "THEME", "Thème")
        formateurs = await self._ids_actifs(data.get("formateur_ids"), "FORMATEUR", "Formateur")
        if not data.get("lieu_id"):
            raise AppError("Lieu obligatoire", 422, code="LIEU_OBLIGATOIRE")
        lieu = await self._ref(uuid.UUID(str(data["lieu_id"])), "LIEU")
        s = FormationSession(
            reference=await self._reference(d.year), intitule=propre(data.get("intitule")) or None,
            date_session=d, lieu_id=lieu.id, statut="PLANIFIEE", observations=propre(data.get("observations")) or None,
            source="MANUEL", revision=1, created_by_id=self.ctx.user.id, updated_by_id=self.ctx.user.id,
        )
        s.themes = [FormationSessionTheme(theme_id=t, ordre=i) for i, t in enumerate(themes)]
        s.formateurs = [FormationSessionFormateur(formateur_id=f, ordre=i) for i, f in enumerate(formateurs)]
        s.participants = []
        self.db.add(s)
        await self.db.flush()
        await self._ajouter_participants(s, data.get("employe_ids") or [])
        await self.db.flush()
        refs = await Refs.charger(self.db)
        await self.audit("formation.session.create", "formation_session", s.id, after={
            "reference": s.reference, **self._photo(s, refs)})
        return self.session_dict(s, refs)

    def _exiger_ouverte(self, s: FormationSession) -> None:
        if s.statut not in ("PLANIFIEE", "REALISEE"):
            raise AppError(f"Formation {STATUT_LIBELLES.get(s.statut, s.statut).lower()} : modification impossible",
                           409, code="FORMATION_VERROUILLEE")

    @staticmethod
    def _motif_sensible(s: FormationSession, motif: str | None) -> str | None:
        if any(p.presence for p in s.participants):
            if not propre(motif):
                raise AppError("Présences déjà saisies : indiquez le motif de la modification", 422,
                               code="MOTIF_OBLIGATOIRE")
            return propre(motif)
        return propre(motif) or None

    async def modifier_session(self, sid: uuid.UUID, data: dict) -> dict:
        self.ctx.exiger("formation.update")
        s = await self._session(sid, verrou=True)
        self._verifier_revision(s, data.get("revision"))
        self._exiger_ouverte(s)
        motif = self._motif_sensible(s, data.get("motif"))
        refs = await Refs.charger(self.db)
        avant = self._photo(s, refs)
        if data.get("date_session"):
            if s.presences_saisies_le and data["date_session"] > date.today():
                raise AppError("Présences saisies : la date ne peut pas être dans le futur", 422, code="DATE_INVALIDE")
            s.date_session = data["date_session"]
        if data.get("lieu_id"):
            s.lieu_id = (await self._ref(uuid.UUID(str(data["lieu_id"])), "LIEU")).id
        if data.get("theme_ids") is not None:
            themes = await self._ids_actifs(data["theme_ids"], "THEME", "Thème")
            s.themes.clear()
            await self.db.flush()
            s.themes.extend(FormationSessionTheme(theme_id=t, ordre=i) for i, t in enumerate(themes))
        if data.get("formateur_ids") is not None:
            formateurs = await self._ids_actifs(data["formateur_ids"], "FORMATEUR", "Formateur")
            s.formateurs.clear()
            await self.db.flush()
            s.formateurs.extend(FormationSessionFormateur(formateur_id=f, ordre=i) for i, f in enumerate(formateurs))
        if "intitule" in data:
            s.intitule = propre(data.get("intitule")) or None
        if "observations" in data:
            s.observations = propre(data.get("observations")) or None
        if data.get("employe_ids") is not None:
            voulus = {uuid.UUID(str(i)) for i in data["employe_ids"]}
            retires = [p for p in s.participants if p.employe_id not in voulus]
            await self._retirer(s, retires, motif)
            await self._ajouter_participants(s, list(data["employe_ids"]))
        self._recalculer_statut(s)
        s.revision += 1
        s.updated_by_id = self.ctx.user.id
        await self.db.flush()
        apres = self._photo(s, refs)
        await self.audit("formation.session.update", "formation_session", s.id,
                         before=avant, after={**apres, "motif": motif})
        return self.session_dict(s, refs)

    async def _retirer(self, s: FormationSession, retires: list[FormationParticipant], motif: str | None) -> None:
        for p in retires:
            if p.presence and not motif:
                raise AppError("Ce participant a une présence saisie : motif obligatoire", 422, code="MOTIF_OBLIGATOIRE")
            await self.audit("formation.participant.remove", "formation_session", s.id,
                             before={"employe": nom_complet(p.employe), "presence": p.presence}, after={"motif": motif})
            s.participants.remove(p)
            await self.db.delete(p)

    async def ajouter_participants(self, sid: uuid.UUID, employe_ids: list, revision: int | None) -> dict:
        self.ctx.exiger("formation.update")
        s = await self._session(sid, verrou=True)
        self._verifier_revision(s, revision)
        self._exiger_ouverte(s)
        n = await self._ajouter_participants(s, employe_ids)
        if n:
            self._recalculer_statut(s)
            s.revision += 1
            s.updated_by_id = self.ctx.user.id
            await self.db.flush()
            await self.audit("formation.participant.add", "formation_session", s.id, after={"ajoutes": n,
                             "employes": [str(i) for i in employe_ids]})
        return self.session_dict(s, await Refs.charger(self.db))

    async def retirer_participant(self, sid: uuid.UUID, participant_id: uuid.UUID, revision: int | None,
                                  motif: str | None) -> dict:
        admin = self.ctx.peut("formation.admin")
        if not admin:
            self.ctx.exiger("formation.update")
        s = await self._session(sid, verrou=True)
        self._verifier_revision(s, revision)
        if not admin:
            self._exiger_ouverte(s)
        p = next((x for x in s.participants if x.id == participant_id), None)
        if not p:
            raise AppError("Participant introuvable", 404, code="NOT_FOUND")
        await self._retirer(s, [p], propre(motif) or None)
        self._recalculer_statut(s)
        s.revision += 1
        s.updated_by_id = self.ctx.user.id
        await self.db.flush()
        return self.session_dict(s, await Refs.charger(self.db))

    @staticmethod
    def _recalculer_statut(s: FormationSession) -> None:
        if s.statut not in ("PLANIFIEE", "REALISEE"):
            return
        complet = bool(s.participants) and all(p.presence for p in s.participants)
        s.statut = "REALISEE" if complet else "PLANIFIEE"

    async def saisir_presences(self, sid: uuid.UUID, presences: dict[str, str | None], revision: int | None,
                               motif: str | None = None) -> dict:
        self.ctx.exiger("formation.attendance.manage")
        s = await self._session(sid, verrou=True)
        self._verifier_revision(s, revision)
        self._exiger_ouverte(s)
        if s.date_session > date.today():
            raise AppError("La formation n'a pas encore eu lieu : saisie des présences impossible", 422,
                           code="FORMATION_FUTURE")
        par_id = {str(p.id): p for p in s.participants}
        inconnus = [k for k in presences if k not in par_id]
        if inconnus:
            raise AppError("Participant inconnu pour cette formation", 422, code="PARTICIPANT_INCONNU")
        changements = []
        for pid, valeur in presences.items():
            if valeur is not None and valeur not in PRESENCES:
                raise AppError("Présence invalide : PRÉSENT ou ABSENT uniquement", 422, code="PRESENCE_INVALIDE")
            p = par_id[pid]
            if p.presence != valeur:
                changements.append((p, p.presence, valeur))
        modif_existantes = [c for c in changements if c[1] is not None]
        if modif_existantes and not propre(motif):
            raise AppError("Modification de présences déjà saisies : motif obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        now = maintenant()
        for p, _old, new in changements:
            p.presence = new
            p.presence_saisie_le = now if new else None
            p.presence_saisie_par_id = self.ctx.user.id if new else None
        if changements:
            s.presences_saisies_le = now
            s.presences_saisies_par_id = self.ctx.user.id
            self._recalculer_statut(s)
            s.revision += 1
            s.updated_by_id = self.ctx.user.id
            await self.db.flush()
            await self.audit(
                "formation.presence.update", "formation_session", s.id,
                before={nom_complet(p.employe): old for p, old, _n in changements},
                after={**{nom_complet(p.employe): new for p, _o, new in changements},
                       "motif": propre(motif) or None, "statut": s.statut},
            )
        return self.session_dict(s, await Refs.charger(self.db))

    async def changer_statut(self, sid: uuid.UUID, action: str, revision: int | None, motif: str | None) -> dict:
        s = await self._session(sid, verrou=True)
        self._verifier_revision(s, revision)
        actions = self._actions(s)
        if action not in ("cloturer", "rouvrir", "annuler", "retablir", "archiver", "desarchiver"):
            raise AppError("Action inconnue", 422, code="ACTION_INCONNUE")
        perm = {"cloturer": "formation.close", "rouvrir": "formation.close", "archiver": "formation.close",
                "desarchiver": "formation.close", "annuler": "formation.cancel", "retablir": "formation.cancel"}[action]
        self.ctx.exiger(perm)
        if not actions.get(action):
            raise AppError("Action impossible dans l'état actuel de la formation", 409, code="TRANSITION_INVALIDE")
        motif = propre(motif) or None
        if action in ("annuler", "rouvrir") and not motif:
            raise AppError("Motif obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        avant = s.statut
        if action == "cloturer":
            s.statut, s.cloturee_le, s.cloturee_par_id = "CLOTUREE", maintenant(), self.ctx.user.id
        elif action == "rouvrir":
            s.statut, s.cloturee_le, s.cloturee_par_id = "REALISEE", None, None
            self._recalculer_statut(s)
        elif action == "annuler":
            s.statut, s.motif_annulation = "ANNULEE", motif
        elif action == "retablir":
            s.statut, s.motif_annulation = "PLANIFIEE", None
            self._recalculer_statut(s)
        elif action == "archiver":
            s.statut_precedent, s.statut = s.statut, "ARCHIVEE"
        elif action == "desarchiver":
            s.statut, s.statut_precedent = s.statut_precedent or "CLOTUREE", None
        s.revision += 1
        s.updated_by_id = self.ctx.user.id
        await self.db.flush()
        audit_action = {"cloturer": "close", "rouvrir": "reopen", "annuler": "cancel", "retablir": "restore",
                        "archiver": "archive", "desarchiver": "unarchive"}[action]
        await self.audit(f"formation.session.{audit_action}", "formation_session", s.id,
                         before={"statut": avant}, after={"statut": s.statut, "motif": motif})
        return self.session_dict(s, await Refs.charger(self.db))

    async def supprimer_session(self, sid: uuid.UUID, motif: str | None) -> str:
        """Suppression définitive (administrateur) quel que soit le statut, présences comprises."""
        self.ctx.exiger("formation.admin")
        if not propre(motif):
            raise AppError("Motif obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        s = await self._session(sid, verrou=True)
        from app.services import formation_documents

        refs = await Refs.charger(self.db)
        avant = {"reference": s.reference, "statut": s.statut, **self._photo(s, refs),
                 **self._stats(s.participants)}
        await formation_documents.retirer_tous(self, s.id, propre(motif))
        await self.db.delete(s)
        await self.db.flush()
        await self.audit("formation.session.delete", "formation_session", sid, before=avant,
                         after={"motif": propre(motif)})
        return s.reference

    # -------------------------------------------------------------- recherche
    async def rechercher(self, q: str, limite: int = 6) -> dict:
        jetons = cle(q).split()
        if not jetons:
            return {"employes": [], "formations": [], "referentiels": [], "entites": []}
        refs = await Refs.charger(self.db)
        E = FormationEmploye
        emps = []
        if self.ctx.peut("formation.employees.view", "formation.view"):
            rows = (await self.db.scalars(select(E).where(and_(*[E.cle_identite.like(f"%{j}%") for j in jetons]))
                                          .order_by(E.actif.desc(), E.nom).limit(limite))).unique().all()
            emps = [{"id": str(e.id), "libelle": nom_complet(e), "sous": refs.entite_lib(e.entite_id) or "",
                     "actif": e.actif} for e in rows]
        sessions = (await self.lister_sessions(q=q, statut=None, taille=limite))["items"] \
            if self.ctx.peut("formation.view") else []
        archives = (await self.lister_sessions(q=q, statut="ARCHIVEE", taille=2))["items"] \
            if self.ctx.peut("formation.view") else []
        forms = [{"id": s["id"], "libelle": f"{s['reference']} — {s['theme_libelle']}",
                  "sous": f"{s['date_session']} · {(s['lieu'] or {}).get('libelle', '')} · {s['statut_libelle']}"}
                 for s in sessions + archives]
        refs_out = [
            {"id": str(r.id), "libelle": r.libelle, "domaine": r.domaine,
             "sous": DOMAINE_LIBELLES.get(r.domaine, r.domaine)}
            for r in refs.refs.values() if all(j in r.cle for j in jetons)
        ][:limite]
        ents = [
            {"id": str(e.id), "libelle": e.libelle, "sous": refs.lib(e.perimetre_id) or ""}
            for e in refs.entites.values() if all(j in e.cle for j in jetons)
        ][:limite]
        return {"employes": emps, "formations": forms, "referentiels": refs_out, "entites": ents}
