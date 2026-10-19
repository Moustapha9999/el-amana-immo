"""Déclaration mensuelle BCM — calcul selon les règles enregistrées, snapshot des règles et des données d'entrée.

Tableaux 1 et 4 : ``bcm_calcul`` (une ligne par client, puis agrégation pure). Tableaux 2 et 3 : source absente.
À chaque calcul, la déclaration conserve les règles appliquées et les données client utilisées : le détail des
populations et l'export reproduisent exactement les chiffres affichés. Une déclaration VALIDEE ne se recalcule plus.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.data.clientele_bcm import (
    BCM_GRILLE_VERSION,
    STATUTS_FIGES,
    STATUTS_OUVERTS,
    fiche_champ,
    fiches,
    tableaux,
)
from app.data.clientele_indicateurs import MOTEUR_VERSION
from app.models import ClienteleDeclarationBcm, User
from app.services.clientele.bcm_calcul import (
    LIGNES_T1,
    ClientBcm,
    DatesBcm,
    agreger,
    charger,
    debut_fenetre_maj,
    exception,
    forme_client,
    risque_bcm,
    selection,
    statut_actif,
)
from app.services.clientele.bcm_regles import ClienteleBcmReglesService
from app.services.clientele.declaration_modele import classeur_modele
from app.services.clientele.periodes import (
    MOIS_FR,
    Fenetre,
    fenetre_mois_bcm,
    fin_mois_precedent,
)
from app.services.clientele.service import Ctx, ClienteleService, maintenant
from app.services.reporting_export import build_styled_pdf

PAGE_MAX = 200
SNAPSHOT_VERSION = 2
LIBELLES_EXCEPTIONS = {
    "forme_EXC_FORME_VIDE": "Catégorie juridique vide",
    "forme_EXC_FORME_NON_RATTACHEE": "Catégorie juridique non rattachée",
    "t4_INTERDIT": "Clients INTERDIT (hors colonnes BCM)",
    "t4_NON_CLASSE": "Clients sans classement à la fin du mois",
    "t4_INVALIDE": "Classement invalide à la fin du mois",
    "gel_indetermine": "Statut de gel inconnu (compte ouvert)",
}


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, date) else v


def _date(v: Any) -> date | None:
    return date.fromisoformat(v) if isinstance(v, str) and v else v


class ClienteleDeclarationService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

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
        if d.statut == "DESACTIVEE":
            raise AppError("Cette déclaration est désactivée. Réactivez-la avant de la recalculer.",
                           409, code="DECLARATION_DESACTIVEE")

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
            suite = (" Elle est désactivée : réactivez-la ou supprimez-la."
                     if existant.statut == "DESACTIVEE" else "")
            raise AppError(
                f"Une déclaration existe déjà pour {MOIS_FR[mois]} {annee}.{suite}",
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
        return await self._detail_complet(d, aujourdhui=aujourdhui)

    async def _detail_complet(self, d: ClienteleDeclarationBcm, *, aujourdhui: date | None = None) -> dict:
        """Détail + journal (auteurs nommés) + synthèse, pour la fiche et l'aperçu."""
        etapes = [
            ("Créée", d.created_at, d.created_by_id),
            ("Calculée", d.calculee_le, d.calculee_par_id),
            ("Soumise au contrôle", d.controlee_le, d.controlee_par_id),
            ("Validée", d.validee_le, d.validee_par_id),
            ("Clôturée", d.cloturee_le, d.cloturee_par_id),
            ("Archivée", d.archivee_le, None),
            ("Désactivée", d.desactivee_le, d.desactivee_par_id),
        ]
        ids = {u for _l, _d, u in etapes if u}
        noms = dict((await self.db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all()) \
            if ids else {}
        cellules = [c for tab in (d.cellules or {}).get("tableaux") or []
                    for ligne in tab.get("lignes") or [] for c in (ligne.get("cellules") or {}).values()]
        controles = d.controles or []
        return {
            **self._detail(d, aujourdhui=aujourdhui),
            "journal": [{"etape": lib, "le": le.isoformat(), "par": noms.get(u)}
                        for lib, le, u in etapes if le],
            "synthese": {
                "tableaux": len((d.cellules or {}).get("tableaux") or []),
                "cellules": len(cellules),
                "a_configurer": sum(1 for c in cellules if c.get("statut") == "A_CONFIGURER"),
                "non_calculables": sum(1 for c in cellules if c.get("statut") == "NON_CALCULABLE"),
                "controles": len(controles),
                "controles_ok": sum(1 for c in controles if c.get("ok")),
                "controles_bloquants": sum(1 for c in controles if not c.get("ok") and c.get("bloquant")),
                "etats": sorted({c.get("etat") for c in controles if c.get("etat")}),
            },
        }

    async def calculer(self, did: uuid.UUID, *, aujourdhui: date | None = None) -> dict:
        self.ctx.exiger("clientele.bcm.prepare")
        d = await self._get(did)
        self._exiger_ouvert(d)
        fenetre = self._fenetre(d.annee, d.mois, aujourdhui)
        courantes = await ClienteleBcmReglesService(self.db, self.ctx).courantes()
        regles = {r["code"]: r["valeur"] for r in courantes}
        statuts = {r["code"]: r["statut"] for r in courantes}
        dates = DatesBcm(debut=d.date_debut, fin=d.date_fin, fin_mois_precedent=d.fin_mois_precedent,
                         fenetre_maj_debut=debut_fenetre_maj(d.date_fin, regles["maj.fenetre"]))
        clients, couverture = await charger(self.db, dates, regles)
        agg = agreger(clients, regles, statuts, dates, couverture)
        cellules, controles = self._assembler(fenetre, agg, courantes)
        d.statut = "CALCULEE"
        d.moteur_version = MOTEUR_VERSION
        d.grille_version = BCM_GRILLE_VERSION
        d.cellules = cellules
        d.controles = controles
        d.populations = {
            "version": SNAPSHOT_VERSION,
            "colonnes": ["racine", "d_entree", "a_ouvert", "categorie", "profil", "gel", "risque_m1",
                         "risque_fin", "d_maj"],
            "clients": [[c.racine, _iso(c.d_entree), c.a_ouvert, c.categorie, c.profil, c.gel, c.risque_m1,
                         c.risque_fin, _iso(c.d_maj)] for c in clients],
        }
        d.calculee_le = maintenant()
        d.calculee_par_id = self.ctx.user.id
        await self.svc.audit("bcm.calculer", "clientele_declaration_bcm", d.id, after={
            "moteur_version": MOTEUR_VERSION, "grille_version": BCM_GRILLE_VERSION, "clients": len(clients),
            "regles": {r["code"]: {"valeur": r["valeur"], "statut": r["statut"]} for r in courantes}})
        await self.db.commit()
        return await self._detail_complet(d, aujourdhui=aujourdhui)

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
        return await self._detail_complet(d)

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
        bloquants = [c for c in (d.controles or []) if not c.get("ok") and c.get("bloquant")]
        if bloquants:
            codes = ", ".join(c["code"] for c in bloquants)
            raise AppError(
                "Validation refusée : contrôle bloquant non levé "
                f"({codes}). La déclaration ne peut pas être présentée comme fiable.",
                409, code="CONTROLES_BLOQUANTS")
        d.statut = "VALIDEE"
        d.commentaire = (commentaire or "").strip() or d.commentaire
        d.validee_le = maintenant()
        d.validee_par_id = self.ctx.user.id
        await self.svc.audit("bcm.valider", "clientele_declaration_bcm", d.id,
                             after={"moteur_version": d.moteur_version})
        await self.db.commit()
        return await self._detail_complet(d, aujourdhui=aujourdhui)

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
        return await self._detail_complet(d)

    async def archiver(self, did: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.bcm.cloturer")
        d = await self._get(did)
        if d.statut != "CLOTUREE":
            raise AppError("Archiver une déclaration clôturée.", 409, code="TRANSITION_REFUSEE")
        d.statut = "ARCHIVEE"
        d.archivee_le = maintenant()
        await self.svc.audit("bcm.archiver", "clientele_declaration_bcm", d.id)
        await self.db.commit()
        return await self._detail_complet(d)

    async def desactiver(self, did: uuid.UUID, *, motif: str | None) -> dict:
        """Met de côté une déclaration non validée (motif obligatoire). Réactivable."""
        self.ctx.exiger("clientele.bcm.prepare")
        d = await self._get(did)
        if d.statut not in STATUTS_OUVERTS:
            raise AppError("Seule une déclaration non validée (brouillon, calculée, à contrôler) peut être "
                           "désactivée. Une déclaration validée suit clôture puis archivage.",
                           409, code="TRANSITION_REFUSEE")
        motif = (motif or "").strip()
        if not motif:
            raise AppError("Motif de désactivation obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        avant = d.statut
        d.statut = "DESACTIVEE"
        d.desactivee_le = maintenant()
        d.desactivee_par_id = self.ctx.user.id
        d.motif_desactivation = motif[:2000]
        await self.svc.audit("bcm.desactiver", "clientele_declaration_bcm", d.id,
                             before={"statut": avant}, after={"statut": d.statut, "motif": motif})
        await self.db.commit()
        return await self._detail_complet(d)

    async def reactiver(self, did: uuid.UUID) -> dict:
        """Retour en brouillon (sans calcul) ou en calculée : le contrôle doit être refait."""
        self.ctx.exiger("clientele.bcm.prepare")
        d = await self._get(did)
        if d.statut != "DESACTIVEE":
            raise AppError("Cette déclaration n'est pas désactivée.", 409, code="TRANSITION_REFUSEE")
        d.statut = "CALCULEE" if d.cellules else "BROUILLON"
        d.controlee_le = d.controlee_par_id = None
        await self.svc.audit("bcm.reactiver", "clientele_declaration_bcm", d.id,
                             before={"statut": "DESACTIVEE", "motif": d.motif_desactivation},
                             after={"statut": d.statut})
        d.desactivee_le = d.desactivee_par_id = d.motif_desactivation = None
        await self.db.commit()
        return await self._detail_complet(d)

    async def supprimer(self, did: uuid.UUID, *, motif: str | None = None) -> None:
        """Suppression définitive d'une déclaration non validée. Une déclaration validée, clôturée ou
        archivée est une pièce réglementaire : jamais supprimée."""
        self.ctx.exiger("clientele.admin")
        d = await self._get(did)
        if d.statut in STATUTS_FIGES:
            raise AppError("Déclaration validée, clôturée ou archivée : pièce réglementaire, suppression "
                           "interdite. Utilisez la clôture puis l'archivage.", 409, code="DECLARATION_FIGEE")
        motif = (motif or "").strip()
        if d.statut != "BROUILLON" and not motif:
            raise AppError("Motif de suppression obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        await self.svc.audit("bcm.supprimer", "clientele_declaration_bcm", d.id,
                             before={"annee": d.annee, "mois": d.mois, "statut": d.statut,
                                     "moteur_version": d.moteur_version,
                                     "calculee_le": d.calculee_le.isoformat() if d.calculee_le else None},
                             after={"motif": motif or None})
        await self.db.delete(d)
        await self.db.commit()

    # ------------------------------------------------------------------ populations (snapshot)
    def _snapshot(self, d: ClienteleDeclarationBcm) -> tuple[list[ClientBcm], dict, DatesBcm] | None:
        pop = d.populations or {}
        cel = d.cellules or {}
        if pop.get("version") != SNAPSHOT_VERSION or not cel.get("regles"):
            return None
        clients = [ClientBcm(racine=r[0], d_entree=_date(r[1]), a_ouvert=bool(r[2]), categorie=r[3],
                             profil=r[4], gel=r[5], risque_m1=r[6], risque_fin=r[7], d_maj=_date(r[8]))
                   for r in pop.get("clients") or []]
        regles = {r["code"]: r["valeur"] for r in cel["regles"]}
        dt = cel["dates"]
        dates = DatesBcm(debut=_date(dt["debut"]), fin=_date(dt["fin"]),
                         fin_mois_precedent=_date(dt["fin_mois_precedent"]),
                         fenetre_maj_debut=_date(dt["fenetre_maj_debut"]))
        return clients, regles, dates

    async def drilldown(
        self, did: uuid.UUID, code: str, *, page: int = 1, taille: int = 50, racine: str | None = None,
        aujourdhui: date | None = None,
    ) -> dict:
        self.ctx.exiger("clientele.bcm.view", "clientele.reporting.view")
        d = await self._get(did)
        taille = min(max(taille, 1), PAGE_MAX)
        page = max(page, 1)
        vide = {"calcule": False, "total": 0, "page": 1, "taille": taille, "colonnes": [], "items": [],
                "source": "aucune"}
        if code.startswith("bcm.exc."):
            cellule: dict = {"code": code, "statut": "CONTROLE", "ligne": LIBELLES_EXCEPTIONS.get(code[8:], code[8:]),
                             "tableau": "Contrôle"}
        else:
            cellule = self._trouver_cellule(d, code)
            if not cellule:
                raise AppError("Cellule inconnue", 404, code="NOT_FOUND")
            if cellule["statut"] == "A_CONFIGURER":
                return {**cellule, **vide}
        snap = self._snapshot(d)
        if not snap:
            return {**cellule, **vide, "reserve": "Déclaration calculée avec une version antérieure du moteur : "
                    "recalculez-la pour consulter les populations."}
        clients, regles, dates = snap
        try:
            racines = self._racines(code, clients, regles, dates)
        except ValueError as e:
            raise AppError("Cellule inconnue", 404, code="NOT_FOUND") from e
        if racine and racine.strip():
            racines = [r for r in racines if r.startswith(racine.strip())]
        index = {c.racine: c for c in clients}
        tranche = racines[(page - 1) * taille: page * taille]
        ligne_code = code.split(".")[2] if code.count(".") >= 2 else ""
        colonnes = ["racine_client", "date_entree", "categorie_juridique", "forme_bcm", "statut_actif",
                    "statut_gel", "risque", "derniere_maj"]
        items = []
        for r in tranche:
            c = index[r]
            niveau = c.risque_m1 if ligne_code == "stock_m1" else c.risque_fin
            items.append({
                "racine_client": c.racine, "date_entree": _iso(c.d_entree), "categorie_juridique": c.categorie,
                "forme_bcm": forme_client(c, regles), "statut_actif": statut_actif(c, regles),
                "statut_gel": c.gel, "risque": f"{niveau or '—'} → {risque_bcm(niveau, regles)}",
                "derniere_maj": _iso(c.d_maj),
            })
        return {**cellule, "calcule": True, "total": len(racines), "page": page, "taille": taille,
                "colonnes": colonnes, "items": items, "source": "snapshot",
                "figee": d.statut in STATUTS_FIGES}

    @staticmethod
    def _racines(code: str, clients: list[ClientBcm], regles: dict, dates: DatesBcm) -> list[str]:
        parts = code.split(".")
        if parts[:2] == ["bcm", "exc"]:
            return exception(clients, regles, dates, ".".join(parts[2:]))
        if len(parts) >= 4 and parts[1] in ("t1a", "t1b") and parts[2] in LIGNES_T1:
            return selection(clients, regles, dates, parts[2], parts[3])
        if len(parts) >= 3 and parts[1] == "t4":
            return selection(clients, regles, dates, "t4", None if parts[2] == "total" else parts[2])
        raise ValueError(code)

    # ------------------------------------------------------------------ exports
    async def exporter_xlsx(self, did: uuid.UUID) -> bytes:
        """Classeur au format du modèle officiel BEA → BCM. Préparation : aucune transmission."""
        self.ctx.exiger("clientele.export")
        d = await self._get(did)
        if not d.cellules:
            raise AppError("Calculez la déclaration avant l'export.", 422, code="NON_CALCULEE")
        genere_le = maintenant()
        meta = {
            "periode": self._periode_libelle(d), "statut": d.statut, "genere_le": genere_le,
            "genere_par": self.ctx.user.full_name or self.ctx.user.email,
            "calculee_le": d.calculee_le, "validee_le": d.validee_le,
            "moteur_version": d.moteur_version, "grille_version": d.grille_version,
            "regles": (d.cellules or {}).get("regles") or [],
            "exceptions": (d.cellules or {}).get("exceptions") or {},
        }
        contenu = classeur_modele(d.cellules, d.controles, meta)
        await self._tracer_export(d, "xlsx", genere_le)
        return contenu

    async def _tracer_export(self, d: ClienteleDeclarationBcm, fmt: str, genere_le) -> None:
        await self.svc.audit("bcm.exporter", "clientele_declaration_bcm", d.id, after={
            "format": fmt, "annee": d.annee, "mois": d.mois, "statut": d.statut,
            "genere_le": genere_le.isoformat(), "moteur_version": d.moteur_version})

    async def exporter_pdf(self, did: uuid.UUID) -> bytes:
        self.ctx.exiger("clientele.export")
        d = await self._get(did)
        if not d.cellules:
            raise AppError("Calculez la déclaration avant l'export.", 422, code="NON_CALCULEE")
        await self._tracer_export(d, "pdf", maintenant())
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

    # ------------------------------------------------------------------ assemblage
    @staticmethod
    def _statut(c: dict) -> str:
        if not c["calculable"]:
            return "NON_CALCULABLE"
        return "PRET_SOUS_RESERVE" if c["regles_a_valider"] else "PRET"

    def _cell(self, tab: dict, ligne: dict, col: str, code: str, c: dict, *, ratio: float | None = None) -> dict:
        return {
            "code": code, "valeur": c["valeur"], "ratio": ratio, "statut": self._statut(c),
            "indicateur": ligne["indicateur_total"], "cutoff": ligne["cutoff"],
            "reserve": c["raison"] or ligne["reserve"], "raison": c["raison"],
            "fiche": fiche_champ(tab, ligne, col, ligne["indicateur_total"]),
            "fiabilite": c["fiabilite"], "regles_a_valider": c["regles_a_valider"],
        }

    def _assembler(self, fenetre: Fenetre, agg: dict, courantes: list[dict]) -> tuple[dict, list]:
        tableaux_out = []
        for tab in tableaux():
            lignes_out = []
            for ligne in tab["lignes"]:
                code = ligne["code"]
                if tab["code"] in ("T1A", "T1B"):
                    src = agg[tab["code"].lower()][code]
                    cellules = {col["code"]: self._cell(tab, ligne, col["code"],
                                                        f"bcm.{tab['code'].lower()}.{code}.{col['code']}",
                                                        src[col["code"]])
                                for col in tab["colonnes"]}
                elif tab["code"] == "T4":
                    v, r = agg["t4"][code]["valeur"], agg["t4"][code]["ratio"]
                    cellules = {
                        "valeur": self._cell(tab, ligne, "valeur", f"bcm.t4.{code}", v, ratio=r["valeur"]),
                        "ratio": {**self._cell(tab, ligne, "ratio", f"bcm.t4.{code}.ratio", r, ratio=r["valeur"]),
                                  "fiche": {**fiche_champ(tab, ligne, "valeur", ligne["indicateur_total"]),
                                            "colonne": "ratio", "colonne_libelle": "Ratio %",
                                            "formule": "nombre du niveau / total × 100, arrondi à 2 décimales"}},
                    }
                else:
                    cellules = {"valeur": {
                        "code": f"bcm.{tab['code'].lower()}.{code}", "valeur": None, "ratio": None,
                        "statut": "A_CONFIGURER", "indicateur": ligne["indicateur_total"],
                        "cutoff": ligne["cutoff"], "reserve": ligne["reserve"], "raison": ligne["reserve"],
                        "fiche": fiche_champ(tab, ligne, "valeur", ligne["indicateur_total"]),
                        "fiabilite": "SOURCE_ABSENTE", "regles_a_valider": [],
                    }}
                lignes_out.append({"code": code, "libelle": ligne["libelle"], "definition": ligne["definition"],
                                   "cellules": cellules})
            tableaux_out.append({"code": tab["code"], "titre": tab["titre"], "sous_titre": tab["sous_titre"],
                                 "type": tab["type"], "colonnes": list(tab["colonnes"]), "lignes": lignes_out})
        cellules = {
            "moteur_version": MOTEUR_VERSION,
            "grille_version": BCM_GRILLE_VERSION,
            "fenetre": fenetre.as_dict(),
            "dates": agg["dates"],
            "fin_mois_precedent": agg["dates"]["fin_mois_precedent"],
            "couverture": agg["couverture"],
            "exceptions": agg["exceptions"],
            "repartition": agg["repartition"],
            "regles": [{k: r[k] for k in ("code", "libelle", "valeur", "statut", "origine", "explication")}
                       for r in courantes],
            "tableaux": tableaux_out,
        }
        return cellules, self._controles(tableaux_out, agg, courantes)

    def _controles(self, tableaux_out: list, agg: dict, courantes: list[dict]) -> list[dict]:
        def val(tab_code: str, ligne: str, col: str) -> int | float | None:
            tab = next(t for t in tableaux_out if t["code"] == tab_code)
            return next(lig for lig in tab["lignes"] if lig["code"] == ligne)["cellules"][col]["valeur"]

        def ctrl(code: str, libelle: str, ok: bool, bloquant: bool, attendu, observe, message: str,
                 etat: str | None = None) -> dict:
            niveau = "CONFORME" if ok else ("ERREUR" if bloquant else "ATTENTION")
            return {"code": code, "libelle": libelle, "ok": ok, "bloquant": bloquant and not ok,
                    "attendu": attendu, "observe": observe, "message": message, "niveau": niveau,
                    "etat": etat or ("CONFORME" if ok else ("BLOQUANT" if bloquant else "AVEC_RESERVE"))}

        exc = agg["exceptions"]
        cov = agg["couverture"]
        dates = agg["dates"]
        statuts = {r["code"]: r for r in courantes}
        out: list[dict] = []

        a_valider = [r["libelle"] for r in courantes if r["statut"] != "CONFIRMEE"]
        out.append(ctrl("regles.a_valider", "Règles de calcul en attente de validation", not a_valider, False,
                        0, len(a_valider), "Appliquées, à confirmer par la Conformité : " + "; ".join(a_valider)
                        if a_valider else "Toutes les règles appliquées sont confirmées."))
        out.append(ctrl("dates.reference", "Dates de référence appliquées", True, False, None, None,
                        f"Fin du mois précédent {dates['fin_mois_precedent']} ; mois {dates['debut']} → "
                        f"{dates['fin']} ; fenêtre des mises à jour à partir du {dates['fenetre_maj_debut']}."))
        out.append(ctrl("unicite.clients", "Un client compté une seule fois", exc["doublons"] == 0, True,
                        0, exc["doublons"], "Clé = racine client (COUNT DISTINCT)."))

        n_interdit = max(exc["risque_fin"]["INTERDIT"], exc["risque_m1"]["INTERDIT"])
        regle_interdit = statuts["interdit.rattachement"]
        approuvee = regle_interdit["statut"] == "CONFIRMEE"
        out.append(ctrl(
            "interdit.rattachement", "Clients INTERDIT : règle de rattachement BCM", n_interdit == 0 or approuvee,
            True, "règle confirmée", n_interdit,
            f"{n_interdit} client(s) INTERDIT. Règle appliquée : {regle_interdit['valeur']} "
            f"({'confirmée' if approuvee else 'non approuvée' + (' — validation bloquée' if n_interdit else '')}). "
            "Le classement des clients n'est pas modifié."))

        for cle, d_ref in (("m1", dates["fin_mois_precedent"]), ("fin", dates["fin"])):
            ok = cov[f"classif_{cle}"]
            out.append(ctrl(
                f"classif.historique_{cle}", f"Historique de classification au {d_ref}", ok, True,
                d_ref, cov["historique_classif_min"],
                "Niveau de risque retenu = dernière entrée de l'historique à la date." if ok else
                f"Premier événement d'historique : {cov['historique_classif_min'] or '—'}. "
                "Les cellules par risque ne sont pas calculées.",
                None if ok else "HISTORIQUE_INDISPONIBLE"))

        libelles_forme = {"EXC_FORME_VIDE": "catégorie vide", "EXC_FORME_NON_RATTACHEE": "catégorie non rattachée"}
        for ligne in LIGNES_T1:
            rep = agg["repartition"][ligne]
            total = val("T1A", ligne, "total")
            if total is None:
                continue
            somme_a = sum(_int(val("T1A", ligne, c)) for c in ("pp", "pm", "cj"))
            hors_a = {libelles_forme[k]: v for k, v in rep["formes"].items() if k in libelles_forme}
            out.append(ctrl(f"t1a.{ligne}.somme", f"T1A {ligne} : PP + PM + CJ = TOTAL", somme_a == total, False,
                            total, somme_a, "Écart = exceptions de forme juridique : "
                            + (", ".join(f"{k} {v}" for k, v in hors_a.items()) or "aucune")))
            if val("T1B", ligne, "eleve") is not None:
                somme_b = sum(_int(val("T1B", ligne, c)) for c in ("eleve", "moyen", "faible"))
                hors_b = {k: v for k, v in rep["risques"].items() if k in ("INTERDIT", "NON_CLASSE", "INVALIDE")}
                out.append(ctrl(f"t1b.{ligne}.somme", f"T1B {ligne} : élevé + moyen + faible = TOTAL",
                                somme_b == total, False, total, somme_b,
                                "Écart = " + (", ".join(f"{k} {v}" for k, v in hors_b.items()) or "aucun")))
            out.append(ctrl(f"t1.{ligne}.perimetre", f"T1A {ligne} TOTAL = T1B {ligne} TOTAL",
                            val("T1B", ligne, "total") == total, True, total, val("T1B", ligne, "total"),
                            "Même population, deux ventilations."))

        t4_total = val("T4", "total", "valeur")
        stock_m1, eer = val("T1A", "stock_m1", "total"), val("T1A", "maj_mois", "total")
        out.append(ctrl("t4.identite", "T4 total = T1 fin du mois précédent + entrées du mois",
                        t4_total == _int(stock_m1) + _int(eer), True, _int(stock_m1) + _int(eer), t4_total,
                        "Identité structurelle : stock de fin de mois = stock de début + entrées en relation."))
        if val("T4", "eleve", "valeur") is not None:
            somme4 = sum(_int(val("T4", c, "valeur")) for c in ("eleve", "moyen", "faible"))
            hors4 = exc["risque_fin"]
            out.append(ctrl("t4.somme", "T4 élevé + moyen + faible = total", somme4 == t4_total, False, t4_total,
                            somme4, f"Écart = INTERDIT {hors4['INTERDIT']}, non classés {hors4['NON_CLASSE']}, "
                            f"invalides {hors4['INVALIDE']} (inclus dans le total, hors colonnes)."))
            ratios_ok = all(
                val("T4", c, "ratio") == (round(_int(val("T4", c, "valeur")) * 100 / t4_total, 2) if t4_total else None)
                for c in ("eleve", "moyen", "faible"))
            couverture_ratio = round(sum(float(val("T4", c, "ratio") or 0) for c in ("eleve", "moyen", "faible")), 2)
            out.append(ctrl("t4.ratios", "Ratios T4 = nombre / total × 100 (2 décimales)", ratios_ok, True,
                            "cohérent", couverture_ratio,
                            f"Somme des ratios = {couverture_ratio} % ; le complément à 100 % correspond aux "
                            "clients hors colonnes."))
        out.append(ctrl("t4.non_classes", "Clients sans classement à la fin du mois",
                        exc["risque_fin"]["NON_CLASSE"] == 0, False, 0, exc["risque_fin"]["NON_CLASSE"],
                        "Inclus dans le total, jamais affectés à une catégorie."))
        out.append(ctrl("t4.invalides", "Classements invalides à la fin du mois",
                        exc["risque_fin"]["INVALIDE"] == 0, False, 0, exc["risque_fin"]["INVALIDE"],
                        "Valeur hors FAIBLE / MOYEN / ELEVE / INTERDIT."))
        n_forme = sum(exc["forme"].values())
        cats = exc.get("categories_non_rattachees") or {}
        out.append(ctrl("forme.exceptions", "Clients sans forme juridique exploitable", n_forme == 0, False, 0,
                        n_forme, f"Catégorie vide : {exc['forme'].get('EXC_FORME_VIDE', 0)} ; non rattachée : "
                        f"{exc['forme'].get('EXC_FORME_NON_RATTACHEE', 0)}"
                        + (" (" + ", ".join(f"{k} {v}" for k, v in list(cats.items())[:6]) + ")" if cats else "")
                        + ". Aucune affectation par défaut."))
        out.append(ctrl("actif.gel", "Statut de gel connu pour les clients ayant un compte ouvert",
                        exc["gel_indetermine"] == 0, False, 0, exc["gel_indetermine"],
                        "Sans statut de gel, le nombre cible d'actifs n'est pas calculé (source : fichier "
                        "hebdomadaire KYC).", None if exc["gel_indetermine"] == 0 else "SOURCE_ABSENTE"))
        out.append(ctrl("maj.couverture", "Historique des mises à jour couvrant la fenêtre", cov["maj"], False,
                        dates["fenetre_maj_debut"], cov["maj_min"],
                        "Événements : décisions de classement, mises à jour de données validées, date de mise à "
                        "jour KYC.", None if cov["maj"] else "HISTORIQUE_INDISPONIBLE"))
        e = exc["eer_module"]
        out.append(ctrl("eer.croise", "EER : entrées en relation ORION vs dossiers du module EER",
                        e["hors_premier_compte"] == 0, False, e["realises"], _int(eer),
                        f"Dossiers EER réalisés dans le mois : {e['realises']} ; dont hors premières ouvertures : "
                        f"{e['hors_premier_compte']} ; premières ouvertures sans dossier EER : "
                        f"{e['premier_compte_sans_dossier']}."))
        out.append(ctrl("perimetre.sans_compte", "Fiches sans compte ORION (hors déclaration)",
                        exc["sans_compte_orion"] == 0 and exc["sans_date_entree"] == 0, False, 0,
                        exc["sans_compte_orion"] + exc["sans_date_entree"],
                        "Une fiche sans compte (création par l'import hebdomadaire) n'a pas de date d'entrée "
                        "ORION : exclue jusqu'à sa reprise par ORION."))
        out.append(ctrl("t2.source", "Source des opérations inhabituelles (T2)", False, False, None, None,
                        "Aucun registre d'opérations inhabituelles, d'analyses ni de déclarations UMEF. "
                        "clientele_alertes = correspondances de listes ORION, non assimilées.", "SOURCE_ABSENTE"))
        out.append(ctrl("t3.source", "Source des opérations suspectes (T3)", False, False, None, None,
                        "Aucun registre de signalements des employés ni de lien vers les analyses et "
                        "déclarations UMEF.", "SOURCE_ABSENTE"))
        return out

    def _trouver_cellule(self, d: ClienteleDeclarationBcm, code: str) -> dict | None:
        for tab in (d.cellules or {}).get("tableaux") or []:
            for ligne in tab["lignes"]:
                for cell in ligne["cellules"].values():
                    if cell.get("code") == code:
                        return {**cell, "ligne": ligne["libelle"], "tableau": tab["code"]}
        return None

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
            "desactivee_le": d.desactivee_le.isoformat() if d.desactivee_le else None,
            "motif_desactivation": d.motif_desactivation,
            "actions": self._actions_cycle(d),
        }

    @staticmethod
    def _actions_cycle(d: ClienteleDeclarationBcm) -> dict:
        return {
            "desactiver": d.statut in STATUTS_OUVERTS,
            "reactiver": d.statut == "DESACTIVEE",
            "supprimer": d.statut not in STATUTS_FIGES,
        }

    def _detail(self, d: ClienteleDeclarationBcm, *, aujourdhui: date | None = None) -> dict:
        fenetre = self._fenetre(d.annee, d.mois, aujourdhui)
        bloquants = sum(1 for c in (d.controles or []) if not c.get("ok") and c.get("bloquant"))
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
                "valider": d.statut == "A_CONTROLER" and fenetre.bcm_officielle and bloquants == 0,
                "cloturer": d.statut == "VALIDEE",
                "archiver": d.statut == "CLOTUREE",
                "exporter": bool(d.cellules),
                **self._actions_cycle(d),
            },
        }

    def _periode_libelle(self, d: ClienteleDeclarationBcm) -> str:
        return f"{MOIS_FR[d.mois].capitalize()} {d.annee}"

    @staticmethod
    def _txt(cell: dict) -> str:
        if cell.get("statut") == "A_CONFIGURER":
            return "Source absente" if cell.get("fiabilite") == "SOURCE_ABSENTE" else "À CONFIGURER"
        if cell.get("valeur") is None:
            return "Non calculable"
        v = cell["valeur"]
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)
