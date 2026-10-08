"""Déclaration mensuelle BCM — consommation du moteur, snapshot à la validation."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.data.clientele_bcm import (
    BCM_GRILLE_VERSION,
    RISQUE_MOTEUR,
    STATUTS_FIGES,
    STATUTS_OUVERTS,
    fiche_champ,
    fiches,
    tableaux,
)
from app.data.clientele_indicateurs import MOTEUR_VERSION
from app.models import ClienteleDeclarationBcm
from app.services.clientele.indicateurs import ClienteleIndicateursService
from app.services.clientele.periodes import (
    MOIS_FR,
    Fenetre,
    fenetre_mois_bcm,
    fin_mois_precedent,
)
from app.services.clientele.service import Ctx, ClienteleService, maintenant
from app.services.reporting_export import build_styled_pdf, build_styled_workbook_multi

PAGE_MAX = 200


def _cellule(
    *,
    code: str,
    valeur: int | float | None,
    statut: str,
    indicateur: str | None,
    cutoff: str,
    reserve: str | None = None,
    ratio: float | None = None,
    fiche: dict | None = None,
) -> dict[str, Any]:
    a_config = statut == "A_CONFIGURER"
    return {
        "code": code,
        "valeur": None if a_config else valeur,
        "ratio": None if a_config else ratio,
        "statut": statut,
        "indicateur": indicateur,
        "cutoff": cutoff,
        "reserve": reserve,
        "fiche": fiche,
    }


def _int(d: dict, *cles: str, default: int = 0) -> int:
    cur: Any = d
    for c in cles:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(c)
    try:
        return int(cur or 0)
    except (TypeError, ValueError):
        return default


class ClienteleDeclarationService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)
        self.indic = ClienteleIndicateursService(db, ctx)

    def _fenetre(self, annee: int, mois: int, aujourdhui: date | None) -> Fenetre:
        try:
            return fenetre_mois_bcm(annee, mois, aujourdhui=aujourdhui)
        except ValueError as e:
            raise AppError(str(e), 422, code="PERIODE_INVALIDE") from e

    async def _get(self, did: uuid.UUID) -> ClienteleDeclarationBcm:
        d = await self.db.get(ClienteleDeclarationBcm, did)
        if not d:
            raise AppError("Déclaration introuvable", 404, code="NOT_FOUND")
        return d

    def _exiger_ouvert(self, d: ClienteleDeclarationBcm) -> None:
        if d.statut in STATUTS_FIGES:
            raise AppError(
                "Cette déclaration est figée (validée). Elle ne se recalcule plus.",
                409, code="DECLARATION_FIGEE")

    async def grille(self) -> dict:
        self.ctx.exiger("clientele.bcm.view", "clientele.reporting.view")
        return {
            "grille_version": BCM_GRILLE_VERSION,
            "moteur_version": MOTEUR_VERSION,
            "fiches": fiches(),
        }

    async def lister(self, *, annee: int | None = None) -> list[dict]:
        self.ctx.exiger("clientele.bcm.view", "clientele.reporting.view")
        q = select(ClienteleDeclarationBcm).order_by(
            ClienteleDeclarationBcm.annee.desc(), ClienteleDeclarationBcm.mois.desc())
        if annee:
            q = q.where(ClienteleDeclarationBcm.annee == annee)
        rows = (await self.db.scalars(q.limit(120))).all()
        return [self._resume(r) for r in rows]

    async def creer(self, annee: int, mois: int, *, aujourdhui: date | None = None) -> dict:
        self.ctx.exiger("clientele.bcm.prepare")
        fenetre = self._fenetre(annee, mois, aujourdhui)
        existant = await self.db.scalar(
            select(ClienteleDeclarationBcm).where(
                ClienteleDeclarationBcm.annee == annee,
                ClienteleDeclarationBcm.mois == mois,
            ))
        if existant:
            raise AppError(
                f"Une déclaration existe déjà pour {MOIS_FR[mois]} {annee}.",
                409, code="DECLARATION_EXISTANTE")
        d = ClienteleDeclarationBcm(
            annee=annee,
            mois=mois,
            date_debut=fenetre.date_debut,
            date_fin=fenetre.date_fin,
            fin_mois_precedent=fin_mois_precedent(fenetre.date_debut),
            statut="BROUILLON",
            grille_version=BCM_GRILLE_VERSION,
            created_by_id=self.ctx.user.id,
        )
        self.db.add(d)
        await self.db.flush()
        await self.svc.audit("bcm.creer", "clientele_declaration_bcm", d.id,
                             after={"annee": annee, "mois": mois})
        await self.db.commit()
        return await self.detail(d.id, aujourdhui=aujourdhui)

    async def detail(self, did: uuid.UUID, *, aujourdhui: date | None = None) -> dict:
        self.ctx.exiger("clientele.bcm.view", "clientele.reporting.view")
        d = await self._get(did)
        return self._detail(d, aujourdhui=aujourdhui)

    async def calculer(self, did: uuid.UUID, *, aujourdhui: date | None = None) -> dict:
        self.ctx.exiger("clientele.bcm.prepare")
        d = await self._get(did)
        self._exiger_ouvert(d)
        fenetre = self._fenetre(d.annee, d.mois, aujourdhui)
        composantes = await self.indic.composantes_bcm(fenetre)
        cellules, controles, populations = self._assembler(d, fenetre, composantes)
        d.statut = "CALCULEE"
        d.moteur_version = MOTEUR_VERSION
        d.grille_version = BCM_GRILLE_VERSION
        d.cellules = cellules
        d.controles = controles
        d.populations = populations
        d.calculee_le = maintenant()
        d.calculee_par_id = self.ctx.user.id
        await self.svc.audit("bcm.calculer", "clientele_declaration_bcm", d.id,
                             after={"moteur_version": MOTEUR_VERSION})
        await self.db.commit()
        return self._detail(d, aujourdhui=aujourdhui)

    async def controler(self, did: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.bcm.prepare")
        d = await self._get(did)
        if d.statut != "CALCULEE":
            raise AppError("Soumettre au contrôle depuis une déclaration calculée.",
                           409, code="TRANSITION_REFUSEE")
        d.statut = "A_CONTROLER"
        d.controlee_le = maintenant()
        d.controlee_par_id = self.ctx.user.id
        await self.svc.audit("bcm.controler", "clientele_declaration_bcm", d.id)
        await self.db.commit()
        return self._detail(d)

    async def valider(self, did: uuid.UUID, *, commentaire: str | None = None,
                      aujourdhui: date | None = None) -> dict:
        self.ctx.exiger("clientele.bcm.valider")
        d = await self._get(did)
        if d.statut != "A_CONTROLER":
            raise AppError("Valider depuis une déclaration à contrôler.",
                           409, code="TRANSITION_REFUSEE")
        if not d.cellules:
            raise AppError("Calculez la déclaration avant de la valider.",
                           422, code="NON_CALCULEE")
        fenetre = self._fenetre(d.annee, d.mois, aujourdhui)
        if not fenetre.bcm_officielle:
            raise AppError(
                "Une déclaration BCM officielle ne se valide que pour un mois calendaire clos.",
                422, code="MOIS_NON_CLOS")
        d.statut = "VALIDEE"
        d.commentaire = (commentaire or "").strip() or d.commentaire
        d.validee_le = maintenant()
        d.validee_par_id = self.ctx.user.id
        await self.svc.audit("bcm.valider", "clientele_declaration_bcm", d.id,
                             after={"moteur_version": d.moteur_version})
        await self.db.commit()
        return self._detail(d, aujourdhui=aujourdhui)

    async def cloturer(self, did: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.bcm.cloturer")
        d = await self._get(did)
        if d.statut != "VALIDEE":
            raise AppError("Clôturer une déclaration validée.", 409, code="TRANSITION_REFUSEE")
        d.statut = "CLOTUREE"
        d.cloturee_le = maintenant()
        d.cloturee_par_id = self.ctx.user.id
        await self.svc.audit("bcm.cloturer", "clientele_declaration_bcm", d.id)
        await self.db.commit()
        return self._detail(d)

    async def archiver(self, did: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.bcm.cloturer")
        d = await self._get(did)
        if d.statut != "CLOTUREE":
            raise AppError("Archiver une déclaration clôturée.", 409, code="TRANSITION_REFUSEE")
        d.statut = "ARCHIVEE"
        d.archivee_le = maintenant()
        await self.svc.audit("bcm.archiver", "clientele_declaration_bcm", d.id)
        await self.db.commit()
        return self._detail(d)

    async def supprimer(self, did: uuid.UUID) -> None:
        self.ctx.exiger("clientele.admin")
        d = await self._get(did)
        if d.statut != "BROUILLON":
            raise AppError("Seule une déclaration en brouillon peut être supprimée.",
                           409, code="TRANSITION_REFUSEE")
        await self.svc.audit("bcm.supprimer", "clientele_declaration_bcm", d.id,
                             before={"annee": d.annee, "mois": d.mois})
        await self.db.delete(d)
        await self.db.commit()

    async def drilldown(
        self, did: uuid.UUID, code: str, *, page: int = 1, taille: int = 50,
        aujourdhui: date | None = None,
    ) -> dict:
        self.ctx.exiger("clientele.bcm.view", "clientele.reporting.view")
        d = await self._get(did)
        cellule = self._trouver_cellule(d, code)
        if not cellule:
            raise AppError("Cellule inconnue", 404, code="NOT_FOUND")
        if cellule["statut"] == "A_CONFIGURER":
            return {**cellule, "calcule": False, "total": 0, "page": 1, "taille": taille,
                    "colonnes": [], "items": [], "source": "aucune"}
        taille = min(max(taille, 1), PAGE_MAX)
        page = max(page, 1)
        pop = (d.populations or {}).get(code) or {}
        ids = pop.get("ids") or []
        if d.statut in STATUTS_FIGES and ids:
            return self._paginate_snapshot(cellule, pop, page, taille)
        if not cellule.get("indicateur"):
            return {**cellule, "calcule": False, "total": 0, "page": 1, "taille": taille,
                    "colonnes": [], "items": [], "source": "aucune"}
        fenetre = self._fenetre(d.annee, d.mois, aujourdhui)
        params = self._params_moteur(cellule, d, fenetre)
        detail = await self.indic.detail(
            cellule["indicateur"], page=page, taille=taille, **params)
        detail["source"] = "moteur"
        detail["figee"] = d.statut in STATUTS_FIGES
        return {**cellule, **detail}

    async def exporter_xlsx(self, did: uuid.UUID) -> bytes:
        self.ctx.exiger("clientele.export")
        d = await self._get(did)
        if not d.cellules:
            raise AppError("Calculez la déclaration avant l'export.", 422, code="NON_CALCULEE")
        sheets = []
        for tab in (d.cellules or {}).get("tableaux") or []:
            headers = ["Ligne"] + [c["libelle"] for c in tab["colonnes"]]
            rows = []
            for ligne in tab["lignes"]:
                row = [ligne["libelle"]]
                for col in tab["colonnes"]:
                    cell = ligne["cellules"].get(col["code"], {})
                    row.append(self._txt(cell))
                rows.append(row)
            sheets.append((tab["code"], tab["titre"], headers, rows))
        ctrl = [["Code", "Libellé", "OK", "Bloquant", "Attendu", "Observé", "Message"]]
        for c in d.controles or []:
            ctrl.append([
                c.get("code"), c.get("libelle"),
                "oui" if c.get("ok") else "non",
                "oui" if c.get("bloquant") else "non",
                c.get("attendu"), c.get("observe"), c.get("message"),
            ])
        sheets.append(("Controles", "Contrôles (non bloquants sauf mention)",
                       ctrl[0], ctrl[1:]))
        return build_styled_workbook_multi(
            report_title="Déclaration mensuelle BCM",
            sheets=sheets,
            subtitle=self._periode_libelle(d),
        )

    async def exporter_pdf(self, did: uuid.UUID) -> bytes:
        self.ctx.exiger("clientele.export")
        d = await self._get(did)
        if not d.cellules:
            raise AppError("Calculez la déclaration avant l'export.", 422, code="NON_CALCULEE")
        rows: list[list] = []
        for tab in (d.cellules or {}).get("tableaux") or []:
            for ligne in tab["lignes"]:
                for col in tab["colonnes"]:
                    cell = ligne["cellules"].get(col["code"], {})
                    rows.append([tab["code"], ligne["libelle"], col["libelle"],
                                 self._txt(cell), cell.get("statut")])
        return build_styled_pdf(
            report_title="Déclaration mensuelle BCM — préparation",
            headers=["Tableau", "Ligne", "Colonne", "Valeur", "Statut"],
            rows=rows,
            subtitle=self._periode_libelle(d),
        )

    def _assembler(
        self, d: ClienteleDeclarationBcm, fenetre: Fenetre, c: dict,
    ) -> tuple[dict, list, dict]:
        populations: dict[str, Any] = {}
        tableaux_out = []
        for tab in tableaux():
            lignes_out = []
            for ligne in tab["lignes"]:
                cellules: dict[str, dict] = {}
                if tab["code"] == "T1A":
                    cellules = self._t1a(tab, ligne, c, populations)
                elif tab["code"] == "T1B":
                    cellules = self._t1b(tab, ligne, c, populations)
                elif tab["code"] == "T2":
                    cellules = self._liste(tab, ligne, c, populations)
                elif tab["code"] == "T3":
                    cellules = self._liste(tab, ligne, c, populations)
                else:
                    cellules = self._t4(tab, ligne, c)
                lignes_out.append({
                    "code": ligne["code"],
                    "libelle": ligne["libelle"],
                    "definition": ligne["definition"],
                    "cellules": cellules,
                })
            tableaux_out.append({
                "code": tab["code"],
                "titre": tab["titre"],
                "sous_titre": tab["sous_titre"],
                "type": tab["type"],
                "colonnes": list(tab["colonnes"]),
                "lignes": lignes_out,
            })
        controles = self._controles(tableaux_out, c)
        cellules = {
            "moteur_version": MOTEUR_VERSION,
            "grille_version": BCM_GRILLE_VERSION,
            "fenetre": fenetre.as_dict(),
            "fin_mois_precedent": d.fin_mois_precedent.isoformat(),
            "mappings": {
                "eer.maj_periode": "EER date_eer dans le mois, statut VALIDE/CLOTURE, racine 6 chiffres.",
                "bcm.t2": "Alertes YTD / mapping provisoire des statuts.",
                "interdit": "INTERDIT n'entre dans aucune colonne BCM.",
            },
            "tableaux": tableaux_out,
        }
        return cellules, controles, populations

    def _t1a(self, tab: dict, ligne: dict, c: dict, populations: dict) -> dict[str, dict]:
        code = ligne["code"]
        statut = ligne["statut"]
        cutoff = ligne["cutoff"]
        if statut == "A_CONFIGURER":
            return {
                k: _cellule(code=f"bcm.t1a.{code}.{k}", valeur=None, statut=statut,
                            indicateur=None if k == "cj" else ligne["indicateur_total"],
                            cutoff=cutoff, reserve=ligne["reserve"],
                            fiche=fiche_champ(tab, ligne, k, None if k == "cj" else ligne["indicateur_total"]))
                for k, _l in (("pp", None), ("pm", None), ("cj", None), ("total", None))
            }
        if code == "stock_m1":
            stock = c["stock_m1"]
            vals = {"pp": _int(stock, "PP"), "pm": _int(stock, "PM"),
                    "cj": None, "total": _int(stock, "total")}
            indic = {"pp": "cli.pp", "pm": "cli.pm", "cj": "cli.construction_juridique",
                     "total": "cli.stock"}
        else:
            eer = c["eer"]
            vals = {"pp": _int(eer, "par_profil", "PP"), "pm": _int(eer, "par_profil", "PM"),
                    "cj": None, "total": _int(eer, "total")}
            indic = {"pp": "eer.maj_periode", "pm": "eer.maj_periode",
                     "cj": "cli.construction_juridique", "total": "eer.maj_periode"}
            populations["bcm.t1a.maj_mois.total"] = {
                "cle": "RACINE", "ids": c.get("ids_eer") or []}
        out = {}
        for k in ("pp", "pm", "cj", "total"):
            st = "A_CONFIGURER" if k == "cj" else statut
            out[k] = _cellule(
                code=f"bcm.t1a.{code}.{k}",
                valeur=None if k == "cj" else vals[k],
                statut=st,
                indicateur=indic[k],
                cutoff=cutoff,
                reserve=ligne["reserve"] if k == "total" else (
                    "Construction juridique : mapping à valider." if k == "cj" else None),
                fiche=fiche_champ(tab, ligne, k, indic[k]),
            )
        return out

    def _t1b(self, tab: dict, ligne: dict, c: dict, populations: dict) -> dict[str, dict]:
        code = ligne["code"]
        statut = ligne["statut"]
        cutoff = ligne["cutoff"]
        if statut == "A_CONFIGURER":
            return {
                k: _cellule(code=f"bcm.t1b.{code}.{k}", valeur=None, statut=statut,
                            indicateur=None, cutoff=cutoff, reserve=ligne["reserve"],
                            fiche=fiche_champ(tab, ligne, k, None))
                for k in ("eleve", "moyen", "faible", "total")
            }
        if code == "stock_m1":
            src = c["classif_m1"]
            total = _int(c["stock_m1"], "total")
            indic_col = {
                "eleve": "cli.risque.eleve", "moyen": "cli.risque.moyen",
                "faible": "cli.risque.faible", "total": "cli.stock",
            }
        else:
            src = c["eer"]["par_risque"]
            total = _int(c["eer"], "total")
            indic_col = {
                "eleve": "eer.maj_periode", "moyen": "eer.maj_periode",
                "faible": "eer.maj_periode", "total": "eer.maj_periode",
            }
            populations["bcm.t1b.maj_mois.total"] = {
                "cle": "RACINE", "ids": c.get("ids_eer") or []}
        out = {}
        for k in ("eleve", "moyen", "faible", "total"):
            val = total if k == "total" else _int(src, RISQUE_MOTEUR[k])
            out[k] = _cellule(
                code=f"bcm.t1b.{code}.{k}",
                valeur=val,
                statut=statut,
                indicateur=indic_col[k],
                cutoff=cutoff,
                reserve=ligne["reserve"] if k == "total" else None,
                fiche=fiche_champ(tab, ligne, k, indic_col[k]),
            )
        return out

    def _liste(self, tab: dict, ligne: dict, c: dict, populations: dict) -> dict[str, dict]:
        code = ligne["code"]
        cellule_code = f"bcm.{tab['code'].lower()}.{code}"
        if ligne["statut"] == "A_CONFIGURER":
            return {"valeur": _cellule(
                code=cellule_code, valeur=None, statut="A_CONFIGURER",
                indicateur=ligne["indicateur_total"], cutoff=ligne["cutoff"],
                reserve=ligne["reserve"],
                fiche=fiche_champ(tab, ligne, "valeur", ligne["indicateur_total"]))}
        t2 = c.get("t2") or {}
        val = t2.get(code)
        if code in ("extraites", "analysees", "suivi"):
            populations[cellule_code] = {
                "cle": "ALERTE", "ids": t2.get(f"ids_{code}") or []}
        return {"valeur": _cellule(
            code=cellule_code, valeur=int(val or 0), statut=ligne["statut"],
            indicateur=ligne["indicateur_total"], cutoff=ligne["cutoff"],
            reserve=ligne["reserve"],
            fiche=fiche_champ(tab, ligne, "valeur", ligne["indicateur_total"]))}

    def _t4(self, tab: dict, ligne: dict, c: dict) -> dict[str, dict]:
        code = ligne["code"]
        total = _int(c["stock_fin"], "total")
        classif = c["classif_fin"]
        if code == "total":
            val = total
            indic = "cli.stock"
        else:
            val = _int(classif, RISQUE_MOTEUR[code])
            indic = ligne["indicateur_total"]
        ratio = round(val * 100 / total, 2) if total else None
        fiche = fiche_champ(tab, ligne, "valeur", indic)
        return {
            "valeur": _cellule(
                code=f"bcm.t4.{code}", valeur=val, statut=ligne["statut"],
                indicateur=indic, cutoff=ligne["cutoff"], reserve=ligne["reserve"],
                ratio=ratio, fiche=fiche),
            "ratio": _cellule(
                code=f"bcm.t4.{code}.ratio", valeur=ratio, statut=ligne["statut"],
                indicateur=indic, cutoff=ligne["cutoff"], ratio=ratio,
                fiche={**fiche, "colonne": "ratio", "colonne_libelle": "Ratio %",
                       "formule": "catégorie / total × 100, arrondi à 2 décimales"}),
        }

    def _controles(self, tableaux_out: list, c: dict) -> list[dict]:
        t1a = next(t for t in tableaux_out if t["code"] == "T1A")
        t1b = next(t for t in tableaux_out if t["code"] == "T1B")
        t4 = next(t for t in tableaux_out if t["code"] == "T4")

        def val(tab, ligne, col) -> int | None:
            cell = next(lig for lig in tab["lignes"] if lig["code"] == ligne)["cellules"][col]
            if cell["statut"] == "A_CONFIGURER":
                return None
            v = cell["valeur"]
            return None if v is None else int(v) if not isinstance(v, float) else v

        stock_m1 = val(t1a, "stock_m1", "total")
        maj = val(t1a, "maj_mois", "total")
        t4_e = val(t4, "eleve", "valeur")
        t4_m = val(t4, "moyen", "valeur")
        t4_f = val(t4, "faible", "valeur")
        t4_t = val(t4, "total", "valeur")
        somme = (t4_e or 0) + (t4_m or 0) + (t4_f or 0)
        interdit = _int(c["classif_fin"], "INTERDIT")
        non_classes = (t4_t or 0) - somme
        identite_obs = None if stock_m1 is None or t4_t is None else t4_t - stock_m1

        def ctrl(*, code: str, libelle: str, ok: bool, bloquant: bool,
                 attendu, observe, message: str) -> dict:
            return {
                "code": code, "libelle": libelle, "ok": ok, "bloquant": bloquant,
                "attendu": attendu, "observe": observe, "message": message,
                "niveau": "CONFORME" if ok else ("ERREUR" if bloquant else "ATTENTION"),
            }

        return [
            ctrl(
                code="t4.somme",
                libelle="T4 ÉLEVÉ + MOYEN + FAIBLE = T4 total",
                ok=somme == (t4_t or 0),
                bloquant=False,
                attendu=t4_t,
                observe=somme,
                message=(
                    "Écart = non classés et/ou INTERDIT "
                    f"(INTERDIT={interdit}, hors colonnes BCM)."
                    if somme != (t4_t or 0) else "Cohérent."
                ),
            ),
            ctrl(
                code="t1b.stock_vs_t1a",
                libelle="T1B stock_m1 TOTAL = T1A stock_m1 TOTAL",
                ok=val(t1b, "stock_m1", "total") == stock_m1,
                bloquant=False,
                attendu=stock_m1,
                observe=val(t1b, "stock_m1", "total"),
                message="Même population, autre ventilation.",
            ),
            ctrl(
                code="identite_t4_t1",
                libelle="T4.total − T1.stock_m1 = EER du mois (observé en août 2026, non figé)",
                ok=identite_obs == maj,
                bloquant=False,
                attendu=maj,
                observe=identite_obs,
                message=(
                    "Identité documentée sur le fichier août 2026 ; "
                    "la Conformité ne l'a pas encore validée comme règle."
                ),
            ),
            ctrl(
                code="t4.non_classes",
                libelle="Clients du stock T4 hors ÉLEVÉ / MOYEN / FAIBLE",
                ok=non_classes == 0,
                bloquant=False,
                attendu=0,
                observe=non_classes,
                message="Inclut INTERDIT et les racines sans classification à la date.",
            ),
        ]

    def _trouver_cellule(self, d: ClienteleDeclarationBcm, code: str) -> dict | None:
        for tab in (d.cellules or {}).get("tableaux") or []:
            for ligne in tab["lignes"]:
                for cell in ligne["cellules"].values():
                    if cell.get("code") == code:
                        return {**cell, "ligne": ligne["libelle"], "tableau": tab["code"]}
        return None

    def _params_moteur(self, cellule: dict, d: ClienteleDeclarationBcm, fenetre: Fenetre) -> dict:
        cutoff = cellule.get("cutoff")
        if cutoff == "fin_mois_precedent":
            debut = fin = d.fin_mois_precedent
        elif cutoff == "ytd":
            debut, fin = date(d.annee, 1, 1), d.date_fin
        elif cutoff == "mois":
            debut, fin = d.date_debut, d.date_fin
        else:
            debut = fin = d.date_fin
        profil = None
        if cellule["code"].endswith(".pp"):
            profil = "PP"
        elif cellule["code"].endswith(".pm"):
            profil = "PM"
        return {
            "periode": "personnalisee",
            "date_debut": debut,
            "date_fin": fin,
            "profil": profil,
        }

    def _paginate_snapshot(self, cellule: dict, pop: dict, page: int, taille: int) -> dict:
        ids = pop.get("ids") or []
        total = len(ids)
        slice_ids = ids[(page - 1) * taille: page * taille]
        cle = pop.get("cle") or "RACINE"
        col = "racine_client" if cle == "RACINE" else "id"
        return {
            **cellule,
            "calcule": True,
            "total": total,
            "page": page,
            "taille": taille,
            "colonnes": [col],
            "items": [{col: i} for i in slice_ids],
            "source": "snapshot",
            "figee": True,
        }

    def _resume(self, d: ClienteleDeclarationBcm) -> dict:
        return {
            "id": str(d.id),
            "annee": d.annee,
            "mois": d.mois,
            "libelle": self._periode_libelle(d),
            "date_debut": d.date_debut.isoformat(),
            "date_fin": d.date_fin.isoformat(),
            "fin_mois_precedent": d.fin_mois_precedent.isoformat(),
            "statut": d.statut,
            "moteur_version": d.moteur_version,
            "grille_version": d.grille_version,
            "calculee_le": d.calculee_le.isoformat() if d.calculee_le else None,
            "validee_le": d.validee_le.isoformat() if d.validee_le else None,
        }

    def _detail(self, d: ClienteleDeclarationBcm, *, aujourdhui: date | None = None) -> dict:
        fenetre = self._fenetre(d.annee, d.mois, aujourdhui)
        return {
            **self._resume(d),
            "simulation": fenetre.simulation,
            "bcm_officielle": fenetre.bcm_officielle,
            "commentaire": d.commentaire,
            "cellules": d.cellules,
            "controles": d.controles or [],
            "actions": {
                "calculer": d.statut in STATUTS_OUVERTS,
                "controler": d.statut == "CALCULEE",
                "valider": d.statut == "A_CONTROLER" and fenetre.bcm_officielle,
                "cloturer": d.statut == "VALIDEE",
                "archiver": d.statut == "CLOTUREE",
                "supprimer": d.statut == "BROUILLON",
                "exporter": bool(d.cellules),
            },
        }

    def _periode_libelle(self, d: ClienteleDeclarationBcm) -> str:
        return f"{MOIS_FR[d.mois].capitalize()} {d.annee}"

    @staticmethod
    def _txt(cell: dict) -> str:
        if cell.get("statut") == "A_CONFIGURER" or cell.get("valeur") is None:
            return "À CONFIGURER"
        v = cell["valeur"]
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)
