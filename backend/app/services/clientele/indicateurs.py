"""Moteur SQL commun (reporting interne + Déclaration BCM).

Un indicateur ``A_CONFIGURER`` n'a jamais de valeur numérique.
Comptage client = COUNT(DISTINCT racine_client).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Any
from uuid import UUID

from openpyxl import Workbook
from sqlalchemy import Date, Select, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.data.clientele_indicateurs import (
    MOTEUR_VERSION,
    PERIODES_ANALYSE,
    IndicateurDef,
    indicateurs as catalogue,
    par_code,
)
from app.models import (
    ClienteleAlerte,
    ClienteleClassifHistorique,
    ClienteleClient,
    ClienteleCompte,
    ClienteleSituation,
    EerDossier,
)
from app.services.clientele.periodes import (
    Fenetre,
    LIBELLES_PERIODES,
    appliquer,
    fin_mois_precedent,
    resoudre,
)
from app.services.clientele.service import Ctx, ClienteleService

PAGE_MAX = 200
EXPORT_MAX = 20_000
TZ_NOM = "Africa/Nouakchott"

# Mappings documentés, pas encore validés par la Conformité (PRET_SOUS_RESERVE).
EER_STATUTS_MAJ = ("VALIDE", "CLOTURE")
ALERTE_ANALYSEES = ("EN_INVESTIGATION", "CONFIRMEE", "CLOTUREE", "REJETEE")
ALERTE_SUIVI = ("NOUVELLE", "A_ANALYSER", "EN_INVESTIGATION")

RANG = {"FAIBLE": 1, "MOYEN": 2, "ELEVE": 3, "INTERDIT": 4}

MAPPINGS = {
    "cli.stock": "Stock = racines avec premiere_extraction ≤ cutoff (à valider comme « actifs + inactifs »).",
    "eer.maj_periode": f"EER date_eer dans le mois, statut ∈ {EER_STATUTS_MAJ}, racine 6 chiffres.",
    "bcm.t2.extraites": "Toutes les alertes créées YTD (statuts à valider).",
    "bcm.t2.analysees": f"Alertes YTD statut ∈ {ALERTE_ANALYSEES}.",
    "bcm.t2.suivi": f"Alertes encore ouvertes à la date, statut ∈ {ALERTE_SUIVI}.",
}


@dataclass(frozen=True)
class Filtres:
    agence: str | None = None
    profil: str | None = None
    residence: str | None = None

    def appliquer(self, q: Select, sit=ClienteleSituation) -> Select:
        if self.agence:
            q = q.where(sit.code_agence == self.agence)
        if self.profil:
            q = q.where(sit.profil_derive == self.profil)
        if self.residence:
            q = q.where(sit.statut_resident == self.residence)
        return q

    def actif(self) -> bool:
        return bool(self.agence or self.profil or self.residence)

    def as_dict(self) -> dict:
        return {"agence": self.agence, "profil": self.profil, "residence": self.residence}


def jour_nktt(col):
    return func.timezone(TZ_NOM, col).cast(Date)


def _cell(v: Any) -> Any:
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def _rang(col, attr: str):
    return case(*[(getattr(col, attr) == k, v) for k, v in RANG.items()])


class ClienteleIndicateursService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    def _fenetre(self, periode: str, date_debut: date | None, date_fin: date | None) -> Fenetre:
        try:
            return resoudre(periode, date_debut=date_debut, date_fin=date_fin)
        except ValueError as e:
            raise AppError(str(e), 422, code="PERIODE_INVALIDE") from e

    def _filtres(self, agence: str | None, profil: str | None, residence: str | None) -> Filtres:
        if profil and profil not in ("PP", "PM", "NON_IDENTIFIE"):
            raise AppError("Profil invalide (PP, PM, NON_IDENTIFIE)", 422, code="PROFIL_INVALIDE")
        if residence and residence not in ("R", "N"):
            raise AppError("Résidence invalide (R, N)", 422, code="RESIDENCE_INVALIDE")
        return Filtres(
            agence=agence.strip() if agence else None,
            profil=profil,
            residence=residence,
        )

    async def tableau(
        self,
        *,
        periode: str = "mois_courant",
        date_debut: date | None = None,
        date_fin: date | None = None,
        agence: str | None = None,
        profil: str | None = None,
        residence: str | None = None,
    ) -> dict:
        self.ctx.exiger("clientele.reporting.view", "clientele.view")
        fenetre = self._fenetre(periode, date_debut, date_fin)
        filtres = self._filtres(agence, profil, residence)
        valeurs = await self._agreger(fenetre, filtres)
        return {
            "moteur_version": MOTEUR_VERSION,
            "fenetre": fenetre.as_dict(),
            "filtres": filtres.as_dict(),
            "periodes": [{"code": c, "libelle": LIBELLES_PERIODES[c]} for c in PERIODES_ANALYSE],
            "bcm_periodicite_officielle": "mois",
            "indicateurs": [self._item(defn, fenetre, valeurs) for defn in catalogue()],
        }

    async def detail(
        self,
        code: str,
        *,
        periode: str = "mois_courant",
        date_debut: date | None = None,
        date_fin: date | None = None,
        agence: str | None = None,
        profil: str | None = None,
        residence: str | None = None,
        page: int = 1,
        taille: int = 50,
    ) -> dict:
        self.ctx.exiger("clientele.reporting.view", "clientele.view")
        defn = par_code(code)
        if not defn:
            raise AppError("Indicateur inconnu", 404, code="NOT_FOUND")
        fenetre = self._fenetre(periode, date_debut, date_fin)
        filtres = self._filtres(agence, profil, residence)
        item = self._item(defn, fenetre, {} if defn["statut"] == "A_CONFIGURER" else
                          {code: (await self._agreger(fenetre, filtres)).get(code, 0)})
        if defn["statut"] == "A_CONFIGURER":
            return {**item, "calcule": False, "total": 0, "page": 1, "taille": taille,
                    "colonnes": [], "items": []}
        taille = min(max(taille, 1), PAGE_MAX)
        page = max(page, 1)
        total, colonnes, rows = await self._population(
            defn, appliquer(fenetre, defn["periode"]), filtres,
            offset=(page - 1) * taille, limite=taille)
        return {**item, "calcule": True, "total": total, "page": page, "taille": taille,
                "colonnes": colonnes, "items": rows}

    async def exporter_tableau(self, **kwargs) -> bytes:
        self.ctx.exiger("clientele.export")
        data = await self.tableau(**kwargs)
        wb = Workbook()
        ws = wb.active
        ws.title = "Indicateurs"
        ws.append(["Code", "Libellé", "Valeur", "Statut", "Période appliquée", "Réserve", "BCM"])
        for i in data["indicateurs"]:
            val = "À CONFIGURER" if i["valeur"] is None else i["valeur"]
            f = i["fenetre_appliquee"]
            ws.append([i["code"], i["libelle"], val, i["statut"],
                       f"{f['date_debut']} → {f['date_fin']}", i.get("reserve") or "",
                       i.get("bcm_tableau") or ""])
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    async def exporter_lignes(self, code: str, **kwargs) -> bytes:
        self.ctx.exiger("clientele.export")
        d = await self.detail(code, page=1, taille=EXPORT_MAX, **kwargs)
        if not d["calcule"]:
            raise AppError("Cet indicateur n'est pas calculable (À CONFIGURER).", 422,
                           code="INDICATEUR_A_CONFIGURER")
        wb = Workbook()
        ws = wb.active
        ws.title = code[:31]
        ws.append(d["colonnes"])
        for row in d["items"]:
            ws.append([row.get(c) for c in d["colonnes"]])
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def _item(self, defn: IndicateurDef, fenetre: Fenetre, valeurs: dict[str, int]) -> dict:
        appl = appliquer(fenetre, defn["periode"])
        a_config = defn["statut"] == "A_CONFIGURER"
        return {
            **defn,
            "valeur": None if a_config else int(valeurs.get(defn["code"], 0)),
            "fenetre_appliquee": appl.as_dict(),
            "mapping_provisoire": None if a_config else MAPPINGS.get(defn["code"]),
        }

    async def _agreger(self, fenetre: Fenetre, filtres: Filtres) -> dict[str, int]:
        point = appliquer(fenetre, "POINT")
        intervalle = appliquer(fenetre, "INTERVALLE")
        mois = appliquer(fenetre, "MOIS")
        ytd = appliquer(fenetre, "YTD")
        stock = await self._stock_profil(point.date_fin, filtres)
        comptes = await self._comptes(point.date_fin, filtres)
        nouveaux = await self._nouveaux(intervalle, filtres)
        risque = await self._classif_au(point.date_fin, filtres)
        reclass = await self._reclass(intervalle, filtres)
        alertes_i = await self._alertes_intervalle(intervalle, filtres)
        alertes_y = await self._alertes_intervalle(ytd, filtres)
        suivi = await self._alertes_suivi(point.date_fin, filtres)
        eer = await self._eer_mois(mois, filtres)
        return {
            "cli.stock": sum(stock.values()),
            "cli.comptes": comptes,
            "cli.pp": stock.get("PP", 0),
            "cli.pm": stock.get("PM", 0),
            "cli.nouveaux": nouveaux,
            "cli.risque.faible": risque.get("FAIBLE", 0),
            "cli.risque.moyen": risque.get("MOYEN", 0),
            "cli.risque.eleve": risque.get("ELEVE", 0),
            "cli.risque.interdit": risque.get("INTERDIT", 0),
            "cli.reclass.faible_moyen": reclass.get(("FAIBLE", "MOYEN"), 0),
            "cli.reclass.faible_eleve": reclass.get(("FAIBLE", "ELEVE"), 0),
            "cli.reclass.moyen_faible": reclass.get(("MOYEN", "FAIBLE"), 0),
            "cli.reclass.moyen_eleve": reclass.get(("MOYEN", "ELEVE"), 0),
            "cli.reclass.eleve_moyen": reclass.get(("ELEVE", "MOYEN"), 0),
            "cli.reclass.eleve_faible": reclass.get(("ELEVE", "FAIBLE"), 0),
            "cli.reclass.vers_eleve": reclass.get(("*", "ELEVE"), 0),
            "cli.reclass.diminution": reclass.get(("DIMINUTION",), 0),
            "eer.maj_periode": eer,
            "alerte.stock": sum(alertes_i.values()),
            "alerte.faux_positifs": alertes_i.get("FAUX_POSITIF", 0),
            "bcm.t2.extraites": sum(alertes_y.values()),
            "bcm.t2.analysees": sum(alertes_y.get(s, 0) for s in ALERTE_ANALYSEES),
            "bcm.t2.suivi": suivi,
        }

    def _join_sit(self, q: Select, left) -> Select:
        return q.join(ClienteleSituation, ClienteleSituation.racine_client == left.racine_client)

    async def _stock_profil(self, cutoff: date, filtres: Filtres) -> dict[str, int]:
        q = (
            select(
                ClienteleSituation.profil_derive,
                func.count(func.distinct(ClienteleClient.racine_client)),
            )
            .select_from(ClienteleClient)
            .join(ClienteleSituation, ClienteleSituation.racine_client == ClienteleClient.racine_client)
            .where(ClienteleClient.premiere_extraction <= cutoff)
        )
        q = filtres.appliquer(q).group_by(ClienteleSituation.profil_derive)
        return {str(p): int(n or 0) for p, n in (await self.db.execute(q)).all()}

    async def _comptes(self, cutoff: date, filtres: Filtres) -> int:
        q = select(func.count()).select_from(ClienteleCompte).where(
            ClienteleCompte.premiere_extraction <= cutoff)
        if filtres.actif():
            q = self._join_sit(q, ClienteleCompte)
            q = filtres.appliquer(q)
        return int(await self.db.scalar(q) or 0)

    async def _nouveaux(self, fenetre: Fenetre, filtres: Filtres) -> int:
        q = (
            select(func.count(func.distinct(ClienteleClient.racine_client)))
            .select_from(ClienteleClient)
            .where(
                ClienteleClient.premiere_extraction >= fenetre.date_debut,
                ClienteleClient.premiere_extraction <= fenetre.date_fin,
            )
        )
        if filtres.actif():
            q = self._join_sit(q, ClienteleClient)
            q = filtres.appliquer(q)
        return int(await self.db.scalar(q) or 0)

    async def _classif_au(self, cutoff: date, filtres: Filtres) -> dict[str, int]:
        histo = (
            select(
                ClienteleClassifHistorique.racine_client.label("racine_client"),
                ClienteleClassifHistorique.nouvelle_classe.label("niveau"),
            )
            .distinct(ClienteleClassifHistorique.racine_client)
            .where(jour_nktt(ClienteleClassifHistorique.created_at) <= cutoff)
            .order_by(
                ClienteleClassifHistorique.racine_client,
                ClienteleClassifHistorique.created_at.desc(),
            )
            .subquery()
        )
        q = (
            select(histo.c.niveau, func.count(func.distinct(histo.c.racine_client)))
            .select_from(histo)
            .join(ClienteleSituation, ClienteleSituation.racine_client == histo.c.racine_client)
        )
        q = filtres.appliquer(q).group_by(histo.c.niveau)
        return {str(n): int(c or 0) for n, c in (await self.db.execute(q)).all()}

    async def _reclass(self, fenetre: Fenetre, filtres: Filtres) -> dict[tuple, int]:
        jour = jour_nktt(ClienteleClassifHistorique.created_at)
        q = (
            select(
                ClienteleClassifHistorique.ancienne_classe,
                ClienteleClassifHistorique.nouvelle_classe,
                func.count(func.distinct(ClienteleClassifHistorique.racine_client)),
            )
            .select_from(ClienteleClassifHistorique)
            .where(jour >= fenetre.date_debut, jour <= fenetre.date_fin)
        )
        if filtres.actif():
            q = self._join_sit(q, ClienteleClassifHistorique)
            q = filtres.appliquer(q)
        q = q.group_by(
            ClienteleClassifHistorique.ancienne_classe,
            ClienteleClassifHistorique.nouvelle_classe,
        )
        out: dict[tuple, int] = {}
        vers_eleve: set[str] = set()
        dim: set[str] = set()
        # Second pass for vers_eleve / diminution with DISTINCT racines.
        racines_q = (
            select(
                ClienteleClassifHistorique.racine_client,
                ClienteleClassifHistorique.ancienne_classe,
                ClienteleClassifHistorique.nouvelle_classe,
            )
            .where(jour >= fenetre.date_debut, jour <= fenetre.date_fin)
        )
        if filtres.actif():
            racines_q = self._join_sit(racines_q, ClienteleClassifHistorique)
            racines_q = filtres.appliquer(racines_q)
        for ancienne, nouvelle, n in (await self.db.execute(q)).all():
            if ancienne:
                out[(ancienne, nouvelle)] = int(n or 0)
        for racine, ancienne, nouvelle in (await self.db.execute(racines_q)).all():
            if nouvelle == "ELEVE":
                vers_eleve.add(racine)
            if ancienne and RANG.get(nouvelle, 0) < RANG.get(ancienne, 0):
                dim.add(racine)
        out[("*", "ELEVE")] = len(vers_eleve)
        out[("DIMINUTION",)] = len(dim)
        return out

    async def _alertes_intervalle(self, fenetre: Fenetre, filtres: Filtres) -> dict[str, int]:
        jour = jour_nktt(ClienteleAlerte.created_at)
        q = (
            select(ClienteleAlerte.statut, func.count())
            .select_from(ClienteleAlerte)
            .where(jour >= fenetre.date_debut, jour <= fenetre.date_fin)
        )
        if filtres.actif():
            q = self._join_sit(q, ClienteleAlerte)
            q = filtres.appliquer(q)
        q = q.group_by(ClienteleAlerte.statut)
        return {str(s): int(n or 0) for s, n in (await self.db.execute(q)).all()}

    async def _alertes_suivi(self, cutoff: date, filtres: Filtres) -> int:
        jour = jour_nktt(ClienteleAlerte.created_at)
        cloture = jour_nktt(ClienteleAlerte.cloturee_le)
        q = (
            select(func.count())
            .select_from(ClienteleAlerte)
            .where(
                jour <= cutoff,
                ClienteleAlerte.statut.in_(ALERTE_SUIVI),
                (ClienteleAlerte.cloturee_le.is_(None)) | (cloture > cutoff),
            )
        )
        if filtres.actif():
            q = self._join_sit(q, ClienteleAlerte)
            q = filtres.appliquer(q)
        return int(await self.db.scalar(q) or 0)

    async def _eer_mois(self, fenetre: Fenetre, filtres: Filtres) -> int:
        return (await self._eer_repartition(fenetre, filtres, fenetre.date_fin))["total"]

    async def _eer_repartition(
        self, fenetre: Fenetre, filtres: Filtres, cutoff_classif: date,
    ) -> dict:
        vide: dict = {"total": 0, "par_profil": {}, "par_risque": {}, "racines": []}
        if not await self.db.scalar(text("SELECT to_regclass('public.eer_dossiers')")):
            return vide
        q = select(EerDossier.racine_client).where(
            EerDossier.deleted_at.is_(None),
            EerDossier.date_eer >= fenetre.date_debut,
            EerDossier.date_eer <= fenetre.date_fin,
            EerDossier.statut.in_(EER_STATUTS_MAJ),
            EerDossier.racine_client.op("~")(r"^[0-9]{6}$"),
        )
        if filtres.actif():
            q = self._join_sit(q, EerDossier)
            q = filtres.appliquer(q)
        racines = sorted({r for (r,) in (await self.db.execute(q)).all() if r})
        if not racines:
            return vide
        pq = (
            select(ClienteleSituation.profil_derive, func.count())
            .where(ClienteleSituation.racine_client.in_(racines))
            .group_by(ClienteleSituation.profil_derive)
        )
        par_profil = {str(p): int(n or 0) for p, n in (await self.db.execute(pq)).all()}
        connus = sum(par_profil.values())
        if connus < len(racines):
            par_profil["ABSENT_REFERENTIEL"] = len(racines) - connus
        histo = (
            select(
                ClienteleClassifHistorique.racine_client.label("racine_client"),
                ClienteleClassifHistorique.nouvelle_classe.label("niveau"),
            )
            .distinct(ClienteleClassifHistorique.racine_client)
            .where(
                ClienteleClassifHistorique.racine_client.in_(racines),
                jour_nktt(ClienteleClassifHistorique.created_at) <= cutoff_classif,
            )
            .order_by(
                ClienteleClassifHistorique.racine_client,
                ClienteleClassifHistorique.created_at.desc(),
            )
            .subquery()
        )
        rq = select(histo.c.niveau, func.count()).group_by(histo.c.niveau)
        par_risque = {str(n): int(c or 0) for n, c in (await self.db.execute(rq)).all()}
        classes = sum(par_risque.values())
        if classes < len(racines):
            par_risque["NON_CLASSE"] = len(racines) - classes
        return {
            "total": len(racines),
            "par_profil": par_profil,
            "par_risque": par_risque,
            "racines": racines,
        }

    async def composantes_bcm(self, fenetre: Fenetre) -> dict:
        """Agrégats du moteur pour une déclaration mensuelle (sans filtres agence)."""
        filtres = Filtres()
        m1 = fin_mois_precedent(fenetre.date_debut)
        mois = appliquer(fenetre, "MOIS")
        ytd = appliquer(fenetre, "YTD")
        stock_m1 = await self._stock_profil(m1, filtres)
        stock_fin = await self._stock_profil(fenetre.date_fin, filtres)
        classif_m1 = await self._classif_au(m1, filtres)
        classif_fin = await self._classif_au(fenetre.date_fin, filtres)
        alertes_y = await self._alertes_intervalle(ytd, filtres)
        suivi = await self._alertes_suivi(fenetre.date_fin, filtres)
        eer = await self._eer_repartition(mois, filtres, fenetre.date_fin)
        t2_extraites = sum(alertes_y.values())
        t2_analysees = sum(alertes_y.get(s, 0) for s in ALERTE_ANALYSEES)
        ids_eer = eer["racines"]
        _tot, _cols, rows_t2e = await self._pop_alertes(
            "bcm.t2.extraites", ytd, filtres, 0, EXPORT_MAX)
        _tot2, _c2, rows_t2a = await self._pop_alertes(
            "bcm.t2.analysees", ytd, filtres, 0, EXPORT_MAX)
        _tot3, _c3, rows_t2s = await self._pop_alertes(
            "bcm.t2.suivi", appliquer(fenetre, "POINT"), filtres, 0, EXPORT_MAX)
        return {
            "stock_m1": {**stock_m1, "total": sum(stock_m1.values())},
            "stock_fin": {**stock_fin, "total": sum(stock_fin.values())},
            "classif_m1": classif_m1,
            "classif_fin": classif_fin,
            "eer": eer,
            "t2": {
                "extraites": t2_extraites,
                "analysees": t2_analysees,
                "suivi": suivi,
                "ids_extraites": [str(r["id"]) for r in rows_t2e],
                "ids_analysees": [str(r["id"]) for r in rows_t2a],
                "ids_suivi": [str(r["id"]) for r in rows_t2s],
            },
            "ids_eer": ids_eer,
        }

    async def _population(
        self, defn: IndicateurDef, fenetre: Fenetre, filtres: Filtres, *, offset: int, limite: int,
    ) -> tuple[int, list[str], list[dict]]:
        code = defn["code"]
        if defn["cle"] == "COMPTE":
            return await self._pop_comptes(fenetre.date_fin, filtres, offset, limite)
        if defn["cle"] == "ALERTE":
            return await self._pop_alertes(code, fenetre, filtres, offset, limite)
        if defn["cle"] == "EER":
            return await self._pop_eer(fenetre, filtres, offset, limite)
        if code.startswith("cli.risque."):
            niveau = code.rsplit(".", 1)[-1].upper()
            if niveau == "ELEVE":
                niveau = "ELEVE"
            return await self._pop_classif(fenetre.date_fin, niveau, filtres, offset, limite)
        if code.startswith("cli.reclass."):
            return await self._pop_reclass(code, fenetre, filtres, offset, limite)
        profil = {"cli.pp": "PP", "cli.pm": "PM"}.get(code)
        nouveaux = code == "cli.nouveaux"
        return await self._pop_clients(fenetre, filtres, offset, limite, profil=profil, nouveaux=nouveaux)

    async def _pop_clients(
        self, fenetre: Fenetre, filtres: Filtres, offset: int, limite: int,
        *, profil: str | None, nouveaux: bool,
    ) -> tuple[int, list[str], list[dict]]:
        cols = ["racine_client", "nom_client", "profil_derive", "code_agence", "etat_client",
                "nb_comptes", "premiere_extraction"]
        q = (
            select(
                ClienteleSituation.racine_client, ClienteleSituation.nom_client,
                ClienteleSituation.profil_derive, ClienteleSituation.code_agence,
                ClienteleSituation.etat_client, ClienteleSituation.nb_comptes,
                ClienteleClient.premiere_extraction,
            )
            .select_from(ClienteleClient)
            .join(ClienteleSituation, ClienteleSituation.racine_client == ClienteleClient.racine_client)
        )
        if nouveaux:
            q = q.where(
                ClienteleClient.premiere_extraction >= fenetre.date_debut,
                ClienteleClient.premiere_extraction <= fenetre.date_fin,
            )
        else:
            q = q.where(ClienteleClient.premiere_extraction <= fenetre.date_fin)
        if profil:
            q = q.where(ClienteleSituation.profil_derive == profil)
        q = filtres.appliquer(q)
        total = int(await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0)
        rows = (await self.db.execute(
            q.order_by(ClienteleSituation.racine_client).offset(offset).limit(limite)
        )).mappings().all()
        return total, cols, [{k: _cell(v) for k, v in dict(r).items()} for r in rows]

    async def _pop_comptes(
        self, cutoff: date, filtres: Filtres, offset: int, limite: int,
    ) -> tuple[int, list[str], list[dict]]:
        cols = ["racine_client", "compte", "rib", "etat_compte", "code_agence",
                "date_ouverture", "premiere_extraction"]
        q = select(
            ClienteleCompte.racine_client, ClienteleCompte.compte, ClienteleCompte.rib,
            ClienteleCompte.etat_compte, ClienteleCompte.code_agence,
            ClienteleCompte.date_ouverture, ClienteleCompte.premiere_extraction,
        ).where(ClienteleCompte.premiere_extraction <= cutoff)
        if filtres.actif():
            q = self._join_sit(q, ClienteleCompte)
            q = filtres.appliquer(q)
        total = int(await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0)
        rows = (await self.db.execute(
            q.order_by(ClienteleCompte.racine_client, ClienteleCompte.compte)
            .offset(offset).limit(limite)
        )).mappings().all()
        return total, cols, [{k: _cell(v) for k, v in dict(r).items()} for r in rows]

    async def _pop_classif(
        self, cutoff: date, niveau: str, filtres: Filtres, offset: int, limite: int,
    ) -> tuple[int, list[str], list[dict]]:
        cols = ["racine_client", "nom_client", "niveau", "profil_derive", "code_agence"]
        histo = (
            select(
                ClienteleClassifHistorique.racine_client.label("racine_client"),
                ClienteleClassifHistorique.nouvelle_classe.label("niveau"),
            )
            .distinct(ClienteleClassifHistorique.racine_client)
            .where(jour_nktt(ClienteleClassifHistorique.created_at) <= cutoff)
            .order_by(
                ClienteleClassifHistorique.racine_client,
                ClienteleClassifHistorique.created_at.desc(),
            )
            .subquery()
        )
        q = (
            select(
                histo.c.racine_client, ClienteleSituation.nom_client, histo.c.niveau,
                ClienteleSituation.profil_derive, ClienteleSituation.code_agence,
            )
            .select_from(histo)
            .join(ClienteleSituation, ClienteleSituation.racine_client == histo.c.racine_client)
            .where(histo.c.niveau == niveau)
        )
        q = filtres.appliquer(q)
        total = int(await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0)
        rows = (await self.db.execute(
            q.order_by(histo.c.racine_client).offset(offset).limit(limite)
        )).mappings().all()
        return total, cols, [{k: _cell(v) for k, v in dict(r).items()} for r in rows]

    async def _pop_reclass(
        self, code: str, fenetre: Fenetre, filtres: Filtres, offset: int, limite: int,
    ) -> tuple[int, list[str], list[dict]]:
        cols = ["racine_client", "nom_client", "ancienne_classe", "nouvelle_classe", "created_at"]
        jour = jour_nktt(ClienteleClassifHistorique.created_at)
        q = (
            select(
                ClienteleClassifHistorique.racine_client,
                ClienteleSituation.nom_client,
                ClienteleClassifHistorique.ancienne_classe,
                ClienteleClassifHistorique.nouvelle_classe,
                ClienteleClassifHistorique.created_at,
            )
            .select_from(ClienteleClassifHistorique)
            .join(ClienteleSituation,
                  ClienteleSituation.racine_client == ClienteleClassifHistorique.racine_client)
            .where(jour >= fenetre.date_debut, jour <= fenetre.date_fin)
        )
        q = filtres.appliquer(q)
        if code == "cli.reclass.vers_eleve":
            q = q.where(ClienteleClassifHistorique.nouvelle_classe == "ELEVE")
        elif code == "cli.reclass.diminution":
            q = q.where(
                ClienteleClassifHistorique.ancienne_classe.isnot(None),
                _rang(ClienteleClassifHistorique, "nouvelle_classe")
                < _rang(ClienteleClassifHistorique, "ancienne_classe"),
            )
        else:
            paire = {
                "cli.reclass.faible_moyen": ("FAIBLE", "MOYEN"),
                "cli.reclass.faible_eleve": ("FAIBLE", "ELEVE"),
                "cli.reclass.moyen_faible": ("MOYEN", "FAIBLE"),
                "cli.reclass.moyen_eleve": ("MOYEN", "ELEVE"),
                "cli.reclass.eleve_moyen": ("ELEVE", "MOYEN"),
                "cli.reclass.eleve_faible": ("ELEVE", "FAIBLE"),
            }[code]
            q = q.where(
                ClienteleClassifHistorique.ancienne_classe == paire[0],
                ClienteleClassifHistorique.nouvelle_classe == paire[1],
            )
        inner = q.distinct(ClienteleClassifHistorique.racine_client).order_by(
            ClienteleClassifHistorique.racine_client,
            ClienteleClassifHistorique.created_at.desc(),
        )
        total = int(await self.db.scalar(
            select(func.count()).select_from(inner.subquery())) or 0)
        rows = (await self.db.execute(inner.offset(offset).limit(limite))).mappings().all()
        return total, cols, [{k: _cell(v) for k, v in dict(r).items()} for r in rows]

    async def _pop_alertes(
        self, code: str, fenetre: Fenetre, filtres: Filtres, offset: int, limite: int,
    ) -> tuple[int, list[str], list[dict]]:
        cols = ["id", "racine_client", "statut", "motif", "created_at"]
        jour = jour_nktt(ClienteleAlerte.created_at)
        q = select(
            ClienteleAlerte.id, ClienteleAlerte.racine_client, ClienteleAlerte.statut,
            ClienteleAlerte.motif, ClienteleAlerte.created_at,
        ).select_from(ClienteleAlerte)
        if code == "bcm.t2.suivi":
            cloture = jour_nktt(ClienteleAlerte.cloturee_le)
            q = q.where(
                jour <= fenetre.date_fin,
                ClienteleAlerte.statut.in_(ALERTE_SUIVI),
                (ClienteleAlerte.cloturee_le.is_(None)) | (cloture > fenetre.date_fin),
            )
        else:
            q = q.where(jour >= fenetre.date_debut, jour <= fenetre.date_fin)
            if code == "alerte.faux_positifs":
                q = q.where(ClienteleAlerte.statut == "FAUX_POSITIF")
            elif code == "bcm.t2.analysees":
                q = q.where(ClienteleAlerte.statut.in_(ALERTE_ANALYSEES))
        if filtres.actif():
            q = self._join_sit(q, ClienteleAlerte)
            q = filtres.appliquer(q)
        total = int(await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0)
        rows = (await self.db.execute(
            q.order_by(ClienteleAlerte.created_at.desc()).offset(offset).limit(limite)
        )).mappings().all()
        return total, cols, [{k: _cell(v) for k, v in dict(r).items()} for r in rows]

    async def _pop_eer(
        self, fenetre: Fenetre, filtres: Filtres, offset: int, limite: int,
    ) -> tuple[int, list[str], list[dict]]:
        cols = ["reference", "racine_client", "date_eer", "statut", "operation_type"]
        if not await self.db.scalar(text("SELECT to_regclass('public.eer_dossiers')")):
            return 0, cols, []
        q = select(
            EerDossier.reference, EerDossier.racine_client, EerDossier.date_eer,
            EerDossier.statut, EerDossier.operation_type,
        ).where(
            EerDossier.deleted_at.is_(None),
            EerDossier.date_eer >= fenetre.date_debut,
            EerDossier.date_eer <= fenetre.date_fin,
            EerDossier.statut.in_(EER_STATUTS_MAJ),
            EerDossier.racine_client.op("~")(r"^[0-9]{6}$"),
        )
        if filtres.actif():
            q = self._join_sit(q, EerDossier)
            q = filtres.appliquer(q)
        total = int(await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0)
        rows = (await self.db.execute(
            q.order_by(EerDossier.date_eer.desc(), EerDossier.reference)
            .offset(offset).limit(limite)
        )).mappings().all()
        return total, cols, [{k: _cell(v) for k, v in dict(r).items()} for r in rows]
