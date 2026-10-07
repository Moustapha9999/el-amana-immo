"""Formation & Sensibilisation — tableau de bord, reporting filtré, journal d'audit.

Agrégation en Python sur un jeu de lignes maigre (sessions × participants) : volumes
modestes (quelques milliers de participations) et règles multi-thèmes plus lisibles qu'en SQL.
Les formations ANNULÉES sont exclues des statistiques ; une session à plusieurs thèmes
compte pour chacun de ses thèmes dans la ventilation « par thème ».
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, fields
from datetime import date, datetime

from sqlalchemy import Text, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    FormationEmploye,
    FormationParticipant,
    FormationSession,
    FormationSessionFormateur,
    FormationSessionTheme,
    User,
)
from app.services.formation_service import MODULE_CODE, STATUT_LIBELLES, Refs

MOIS = ["Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc."]
PRESENCE_LIBELLES = {"PRESENT": "Présent", "ABSENT": "Absent", None: "Non saisi"}


@dataclass
class Filtres:
    date_debut: date | None = None
    date_fin: date | None = None
    annee: int | None = None
    theme_id: uuid.UUID | None = None
    formateur_id: uuid.UUID | None = None
    lieu_id: uuid.UUID | None = None
    entite_id: uuid.UUID | None = None
    perimetre_id: uuid.UUID | None = None
    employe_id: uuid.UUID | None = None
    fonction_id: uuid.UUID | None = None
    presence: str | None = None  # PRESENT | ABSENT | NON_SAISI

    @property
    def niveau_participant(self) -> bool:
        return any((self.entite_id, self.perimetre_id, self.employe_id, self.fonction_id, self.presence))

    def actifs(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) not in (None, "")}


def _taux(presents: int, absents: int) -> float | None:
    return round(presents * 100 / (presents + absents), 1) if (presents + absents) else None


class _Agg:
    __slots__ = ("sessions", "participants", "presents", "absents", "employes")

    def __init__(self) -> None:
        self.sessions: set = set()
        self.participants = 0
        self.presents = 0
        self.absents = 0
        self.employes: set = set()

    def ligne(self, libelle: str, **extra) -> dict:
        return {"libelle": libelle, "formations": len(self.sessions), "participants": self.participants,
                "presents": self.presents, "absents": self.absents, "employes": len(self.employes),
                "taux": _taux(self.presents, self.absents), **extra}


class FormationReporting:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _donnees(self, f: Filtres) -> tuple[list[FormationSession], list[tuple], Refs]:
        S = FormationSession
        conds = [S.statut != "ANNULEE"]
        if f.annee:
            conds.append(func.extract("year", S.date_session) == f.annee)
        if f.date_debut:
            conds.append(S.date_session >= f.date_debut)
        if f.date_fin:
            conds.append(S.date_session <= f.date_fin)
        if f.lieu_id:
            conds.append(S.lieu_id == f.lieu_id)
        if f.theme_id:
            conds.append(S.id.in_(select(FormationSessionTheme.session_id).where(
                FormationSessionTheme.theme_id == f.theme_id)))
        if f.formateur_id:
            conds.append(S.id.in_(select(FormationSessionFormateur.session_id).where(
                FormationSessionFormateur.formateur_id == f.formateur_id)))
        sessions = list((await self.db.scalars(select(S).where(and_(*conds)).order_by(
            S.date_session.desc(), S.reference.desc()))).unique().all())
        ids = [s.id for s in sessions]
        P = FormationParticipant
        lignes: list[tuple] = []
        if ids:
            pc = [P.session_id.in_(ids)]
            if f.entite_id:
                pc.append(P.entite_id == f.entite_id)
            if f.perimetre_id:
                pc.append(P.perimetre_id == f.perimetre_id)
            if f.employe_id:
                pc.append(P.employe_id == f.employe_id)
            if f.fonction_id:
                pc.append(P.fonction_id == f.fonction_id)
            if f.presence == "NON_SAISI":
                pc.append(P.presence.is_(None))
            elif f.presence in ("PRESENT", "ABSENT"):
                pc.append(P.presence == f.presence)
            lignes = list((await self.db.execute(
                select(P.session_id, P.employe_id, P.presence, P.entite_id, P.perimetre_id, P.fonction_id,
                       FormationEmploye.nom, FormationEmploye.prenom)
                .join(FormationEmploye, FormationEmploye.id == P.employe_id)
                .where(and_(*pc))
                .order_by(FormationEmploye.nom, FormationEmploye.prenom)
            )).all())
        if f.niveau_participant:
            gardes = {l[0] for l in lignes}
            sessions = [s for s in sessions if s.id in gardes]
        return sessions, lignes, await Refs.charger(self.db)

    async def reporting(self, f: Filtres, *, limite_lignes: int | None = 500) -> dict:
        sessions, lignes, refs = await self._donnees(f)
        par_session = {s.id: s for s in sessions}
        stats_session: dict = defaultdict(lambda: [0, 0, 0])
        dims = {k: defaultdict(_Agg) for k in ("annee", "mois", "theme", "entite", "perimetre", "lieu",
                                               "formateur", "fonction")}
        presents = absents = 0
        employes, formes = set(), set()

        for s in sessions:
            annee = str(s.date_session.year)
            dims["annee"][annee].sessions.add(s.id)
            dims["mois"][(s.date_session.year, s.date_session.month)].sessions.add(s.id)
            dims["lieu"][refs.lib(s.lieu_id) or "—"].sessions.add(s.id)
            for t in s.themes:
                dims["theme"][refs.lib(t.theme_id) or "—"].sessions.add(s.id)
            for fo in s.formateurs:
                dims["formateur"][refs.lib(fo.formateur_id) or "—"].sessions.add(s.id)

        participations = []
        for sid, eid, presence, entite_id, perimetre_id, fonction_id, nom, prenom in lignes:
            s = par_session.get(sid)
            if not s:
                continue
            st = stats_session[sid]
            st[0] += 1
            employes.add(eid)
            if presence == "PRESENT":
                st[1] += 1
                presents += 1
                formes.add(eid)
            elif presence == "ABSENT":
                st[2] += 1
                absents += 1
            cles = {
                "annee": [str(s.date_session.year)],
                "mois": [(s.date_session.year, s.date_session.month)],
                "theme": [refs.lib(t.theme_id) or "—" for t in s.themes],
                "entite": [refs.entite_lib(entite_id) or "Non renseignée"],
                "perimetre": [refs.lib(perimetre_id) or "Non renseigné"],
                "lieu": [refs.lib(s.lieu_id) or "—"],
                "formateur": [refs.lib(fo.formateur_id) or "—" for fo in s.formateurs],
                "fonction": [refs.lib(fonction_id) or "Non renseignée"],
            }
            for dim, valeurs in cles.items():
                for v in valeurs:
                    a = dims[dim][v]
                    a.sessions.add(sid)
                    a.participants += 1
                    a.employes.add(eid)
                    if presence == "PRESENT":
                        a.presents += 1
                    elif presence == "ABSENT":
                        a.absents += 1
            participations.append({
                "session_id": str(sid), "reference": s.reference, "date": s.date_session.isoformat(),
                "theme": ", ".join(refs.lib(t.theme_id) or "" for t in s.themes),
                "lieu": refs.lib(s.lieu_id), "formateur": " / ".join(refs.lib(x.formateur_id) or "" for x in s.formateurs),
                "employe_id": str(eid), "nom": nom, "prenom": prenom,
                "nom_complet": f"{prenom} {nom}".strip() if prenom else nom,
                "fonction": refs.lib(fonction_id), "entite": refs.entite_lib(entite_id),
                "perimetre": refs.lib(perimetre_id), "presence": presence,
                "presence_libelle": PRESENCE_LIBELLES.get(presence, presence),
            })

        participations.sort(key=lambda r: (r["date"], r["nom_complet"].lower()), reverse=False)
        participations.sort(key=lambda r: r["date"], reverse=True)

        def trier(dim: str) -> list[dict]:
            return sorted((a.ligne(k) for k, a in dims[dim].items()),
                          key=lambda r: (-r["participants"], -r["formations"], r["libelle"]))

        mois = []
        if dims["mois"]:
            annee_ref = f.annee or max(y for y, _m in dims["mois"])
            for m in range(1, 13):
                a = dims["mois"].get((annee_ref, m)) or _Agg()
                mois.append(a.ligne(MOIS[m - 1], cle=f"{annee_ref}-{m:02d}"))

        formations = []
        today = date.today()
        for s in sessions:
            n, pr, ab = stats_session.get(s.id, [0, 0, 0])
            formations.append({
                "id": str(s.id), "reference": s.reference, "date": s.date_session.isoformat(),
                "intitule": s.intitule, "theme": ", ".join(refs.lib(t.theme_id) or "" for t in s.themes),
                "lieu": refs.lib(s.lieu_id), "formateur": " / ".join(refs.lib(x.formateur_id) or "" for x in s.formateurs),
                "statut": s.statut, "statut_libelle": STATUT_LIBELLES.get(s.statut, s.statut),
                "participants": n, "presents": pr, "absents": ab, "non_saisis": n - pr - ab, "taux": _taux(pr, ab),
            })

        realisees = sum(1 for s in sessions if s.statut in ("REALISEE", "CLOTUREE", "ARCHIVEE"))
        a_venir = sum(1 for s in sessions if s.statut == "PLANIFIEE" and s.date_session > today)
        actifs = await self.db.scalar(select(func.count(FormationEmploye.id)).where(FormationEmploye.actif.is_(True)))
        n_part = len(participations)
        kpis = {
            "formations": len(sessions), "formations_realisees": realisees, "formations_a_venir": a_venir,
            "participations": n_part, "presents": presents, "absents": absents,
            "non_saisis": n_part - presents - absents, "taux_presence": _taux(presents, absents),
            "employes_concernes": len(employes), "employes_formes": len(formes),
            "employes_actifs": actifs or 0,
            "themes_couverts": len([k for k, a in dims["theme"].items() if a.sessions]),
        }
        return {
            "filtres": {k: (str(v) if isinstance(v, (uuid.UUID, date)) else v) for k, v in f.actifs().items()},
            "genere_le": datetime.now().isoformat(timespec="seconds"),
            "kpis": kpis,
            "par_annee": sorted((a.ligne(k) for k, a in dims["annee"].items()), key=lambda r: r["libelle"]),
            "par_mois": mois,
            "par_theme": trier("theme"), "par_entite": trier("entite"), "par_perimetre": trier("perimetre"),
            "par_lieu": trier("lieu"), "par_formateur": trier("formateur"), "par_fonction": trier("fonction"),
            "presence": [
                {"libelle": "Présents", "valeur": presents, "cle": "PRESENT"},
                {"libelle": "Absents", "valeur": absents, "cle": "ABSENT"},
                {"libelle": "Non saisis", "valeur": n_part - presents - absents, "cle": "NON_SAISI"},
            ],
            "formations": formations,
            "participations": participations if limite_lignes is None else participations[:limite_lignes],
            "participations_total": n_part,
        }

    async def tableau_de_bord(self, annee: int | None = None) -> dict:
        data = await self.reporting(Filtres(annee=annee), limite_lignes=0)
        refs = await Refs.charger(self.db)
        S = FormationSession
        P = FormationParticipant
        today = date.today()
        nb_part = select(func.count(P.id)).where(P.session_id == S.id).scalar_subquery()

        async def lister(q, n=6) -> list[dict]:
            out = []
            for s, np in (await self.db.execute(q.limit(n))).unique().all():
                out.append({"id": str(s.id), "reference": s.reference, "date": s.date_session.isoformat(),
                            "theme": ", ".join(refs.lib(t.theme_id) or "" for t in s.themes),
                            "lieu": refs.lib(s.lieu_id), "statut": s.statut,
                            "statut_libelle": STATUT_LIBELLES.get(s.statut), "participants": np})
            return out

        base = select(S, nb_part)
        prochaines = await lister(base.where(S.statut == "PLANIFIEE", S.date_session > today)
                                  .order_by(S.date_session.asc()))
        a_saisir = await lister(base.where(S.statut == "PLANIFIEE", S.date_session <= today, nb_part > 0)
                                .order_by(S.date_session.asc()), 8)
        nb_a_saisir = await self.db.scalar(select(func.count(S.id)).where(
            S.statut == "PLANIFIEE", S.date_session <= today, S.id.in_(select(P.session_id))))
        a_cloturer = await self.db.scalar(select(func.count(S.id)).where(S.statut == "REALISEE"))
        dernieres = await lister(base.where(S.statut.in_(("REALISEE", "CLOTUREE", "ARCHIVEE")))
                                 .order_by(S.date_session.desc()))

        # Couverture : employés actifs ayant au moins une présence, par périmètre de leur entité actuelle.
        formes_ids = select(P.employe_id).join(S, S.id == P.session_id).where(
            P.presence == "PRESENT", S.statut != "ANNULEE")
        if annee:
            formes_ids = formes_ids.where(func.extract("year", S.date_session) == annee)
        rows = (await self.db.execute(
            select(FormationEmploye.entite_id, func.count(FormationEmploye.id),
                   func.count(FormationEmploye.id).filter(FormationEmploye.id.in_(formes_ids)))
            .where(FormationEmploye.actif.is_(True)).group_by(FormationEmploye.entite_id)
        )).all()
        couverture: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        total_actifs = total_formes = 0
        for entite_id, n, nf in rows:
            ent = refs.entites.get(entite_id) if entite_id else None
            per = refs.lib(ent.perimetre_id) if ent else "Non renseigné"
            couverture[per or "Non renseigné"][0] += n
            couverture[per or "Non renseigné"][1] += nf
            total_actifs += n
            total_formes += nf
        annees = [int(r) for r in (await self.db.scalars(
            select(func.distinct(func.extract("year", S.date_session))).where(S.statut != "ANNULEE")
        )).all() if r is not None]
        data.update({
            "prochaines": prochaines, "a_saisir": a_saisir, "nb_a_saisir": nb_a_saisir or 0,
            "nb_a_cloturer": a_cloturer or 0, "dernieres": dernieres,
            "couverture": sorted(
                ({"libelle": k, "actifs": v[0], "formes": v[1],
                  "taux": round(v[1] * 100 / v[0], 1) if v[0] else None} for k, v in couverture.items()),
                key=lambda r: (-(r["taux"] or 0), r["libelle"])),
            "couverture_globale": {"actifs": total_actifs, "formes": total_formes, "jamais_formes": total_actifs - total_formes,
                                   "taux": round(total_formes * 100 / total_actifs, 1) if total_actifs else None},
            "annees": sorted(annees, reverse=True),
        })
        return data

    async def journal(self, *, q: str | None = None, action: str | None = None, entity: str | None = None,
                      entity_id: str | None = None, date_debut: date | None = None, date_fin: date | None = None,
                      page: int = 1, taille: int = 30) -> dict:
        conds = [AuditLog.module_code == MODULE_CODE]
        if action:
            conds.append(AuditLog.action.like(f"{action}%"))
        if entity:
            conds.append(AuditLog.entity == entity)
        if entity_id:
            conds.append(AuditLog.entity_id == entity_id)
        if date_debut:
            conds.append(func.date(AuditLog.created_at) >= date_debut)
        if date_fin:
            conds.append(func.date(AuditLog.created_at) <= date_fin)
        if q:
            like = f"%{q.lower()}%"
            conds.append(or_(func.lower(User.full_name).like(like), func.lower(AuditLog.action).like(like),
                             cast(AuditLog.after_data, Text).ilike(like)))
        base = select(AuditLog, User.full_name).outerjoin(User, User.id == AuditLog.user_id).where(and_(*conds))
        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        taille = max(1, min(taille, 200))
        rows = (await self.db.execute(base.order_by(AuditLog.created_at.desc())
                                      .offset((max(page, 1) - 1) * taille).limit(taille))).all()
        return {
            "items": [{
                "id": str(a.id), "action": a.action, "libelle": ACTIONS.get(a.action, a.action),
                "entity": a.entity, "entity_id": a.entity_id, "utilisateur": nom or "—",
                "date": a.created_at.isoformat() if a.created_at else None,
                "avant": a.before_data, "apres": a.after_data, "request_id": a.request_id,
            } for a, nom in rows],
            "total": total or 0, "page": page, "taille": taille,
        }


ACTIONS = {
    "formation.session.create": "Création de formation",
    "formation.session.update": "Modification de formation",
    "formation.session.cancel": "Annulation de formation",
    "formation.session.restore": "Rétablissement de formation",
    "formation.session.close": "Clôture de formation",
    "formation.session.reopen": "Réouverture de formation",
    "formation.session.archive": "Archivage de formation",
    "formation.session.unarchive": "Désarchivage de formation",
    "formation.session.delete": "Suppression de formation",
    "formation.participant.add": "Ajout de participants",
    "formation.participant.remove": "Retrait d'un participant",
    "formation.presence.update": "Saisie / modification des présences",
    "formation.employe.create": "Création d'employé",
    "formation.employe.update": "Modification d'employé",
    "formation.employe.deactivate": "Désactivation d'employé",
    "formation.employe.reactivate": "Réactivation d'employé",
    "formation.referentiel.create": "Ajout au référentiel",
    "formation.referentiel.update": "Modification du référentiel",
    "formation.referentiel.delete": "Suppression du référentiel",
    "formation.referentiel.merge": "Fusion de valeurs du référentiel",
    "formation.entite.create": "Création d'entité",
    "formation.entite.update": "Modification d'entité",
    "formation.entite.delete": "Suppression d'entité",
    "formation.import.analyse": "Analyse d'un fichier Excel",
    "formation.import.confirm": "Import Excel confirmé",
    "formation.import.abandon": "Import Excel abandonné",
    "formation.document.upload": "Dépôt d'une feuille de présence signée",
    "formation.document.delete": "Retrait d'une feuille de présence signée",
    "formation.document.download": "Consultation d'une feuille de présence signée",
    "formation.export.pdf": "Export PDF",
    "formation.export.excel": "Export Excel",
}
