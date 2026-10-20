"""Suivi de la classification PP / PM : progression, listes filtrées et exports PDF / Excel.

Client « classé » : une ligne ``clientele_classifications`` avec un niveau du référentiel
(FAIBLE, MOYEN, ELEVE, INTERDIT). Une évaluation du moteur sans décision retenue ne compte pas.
Une classe manuelle différente du moteur reste une classification valide : l'écart est compté à part.

PP et PM ne sont jamais mélangés : chaque liste, export et lot porte un seul profil.
Les fichiers produits sont des sorties ; ils ne modifient jamais la classification.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import (
    ClienteleClassifEvaluation,
    ClienteleClassification,
    ClienteleClassifLot,
    ClienteleSituation,
)
from app.services.clientele.classification import MODE_PAR_SOURCE, NIVEAUX, SOURCES_FICHIER, SOURCES_MANUELLES
from app.services.clientele.service import Ctx, ClienteleService
from app.services.reporting_export import build_styled_pdf, build_styled_workbook_multi, format_export_datetime

PROFILS = ("PP", "PM")
PERIMETRES = {"TOUS": "Tous les clients", "OUVERTS": "Clients ouverts (au moins un compte ouvert)"}
LIBELLE_PROFIL = {"PP": "personnes physiques", "PM": "personnes morales"}
STATUTS_CLASSIF = {
    "CLASSE": "Classé",
    "A_VALIDER": "Proposition moteur à valider",
    "NON_CLASSABLE": "Moteur sans résultat exploitable",
    "NON_CALCULE": "Non calculé",
}
LIBELLE_MODE = {"MOTEUR": "Moteur", "FICHIER": "Fichier", "MANUEL": "Manuelle"}
EXPORT_MAX_XLSX = 100_000
EXPORT_MAX_PDF = 5_000
# Le PDF garde une police lisible : colonnes secondaires réservées à l'Excel.
COLONNES_HORS_PDF = ("Agence", "Écart moteur")
STATUTS_MOTEUR_ADMISSIBLES = ("EVALUE", "BLOQUANT")


def pourcentage(classes: int, total: int) -> float | None:
    """Part classée en %, bornée à [0, 100] ; ``None`` (non applicable) si la population est vide."""
    if total <= 0:
        return None
    return round(min(max(classes / total * 100, 0.0), 100.0), 1)


def pourcentage_fr(valeur: float | None) -> str:
    if valeur is None:
        return "Non applicable"
    return f"{valeur:.1f}".replace(".", ",") + " %"


def _date_fr(v: date | datetime | None) -> str | None:
    return v.strftime("%d/%m/%Y") if v else None


def _texte(v: Any) -> Any:
    """Cellule Excel : une chaîne commençant par « = » serait lue comme une formule."""
    if isinstance(v, str) and v.startswith("="):
        return " " + v
    return v


def _dernier_calcul():
    E = ClienteleClassifEvaluation
    return (select(E.racine_client, E.niveau_final, E.statut, E.created_at)
            .distinct(E.racine_client)
            .order_by(E.racine_client, E.created_at.desc())
            .subquery("dernier_calcul"))


def _profil(profil: str | None) -> str:
    p = (profil or "").upper()
    if p not in PROFILS:
        raise AppError("Profil attendu : PP ou PM", 422, code="PROFIL_INVALIDE")
    return p


class ClienteleSuiviService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    # ------------------------------------------------------------------ progression
    async def progression(self, *, perimetre: str = "TOUS") -> dict:
        self.ctx.exiger("clientele.view")
        perimetre = perimetre if perimetre in PERIMETRES else "TOUS"
        S, K = ClienteleSituation, ClienteleClassification
        d = _dernier_calcul()
        classe = K.niveau.in_(NIVEAUX)
        non_classe = or_(K.niveau.is_(None), K.niveau.notin_(NIVEAUX))
        admissible = and_(d.c.statut.in_(STATUTS_MOTEUR_ADMISSIBLES), d.c.niveau_final.in_(NIVEAUX))
        stmt = (
            select(
                S.profil_derive,
                func.count(),
                func.count().filter(classe),
                func.count().filter(and_(non_classe, admissible)),
                func.count().filter(and_(non_classe, d.c.racine_client.is_not(None), ~admissible)),
                func.count().filter(and_(non_classe, d.c.racine_client.is_(None))),
                func.count().filter(and_(classe, admissible, K.niveau != d.c.niveau_final)),
                func.count().filter(and_(classe, K.source.in_(SOURCES_MANUELLES))),
            )
            .select_from(S)
            .outerjoin(K, K.racine_client == S.racine_client)
            .outerjoin(d, d.c.racine_client == S.racine_client)
            .group_by(S.profil_derive)
        )
        if perimetre == "OUVERTS":
            stmt = stmt.where(S.etat_client == "OUVERT")
        brut = {p: tuple(int(x or 0) for x in reste) for p, *reste in (await self.db.execute(stmt)).all()}

        niveaux_q = (select(S.profil_derive, K.niveau, func.count())
                     .join(K, K.racine_client == S.racine_client)
                     .where(classe).group_by(S.profil_derive, K.niveau))
        if perimetre == "OUVERTS":
            niveaux_q = niveaux_q.where(S.etat_client == "OUVERT")
        par_niveau: dict[str, dict[str, int]] = {}
        for p, niveau, nb in (await self.db.execute(niveaux_q)).all():
            par_niveau.setdefault(p, {})[niveau] = int(nb)

        def bloc(code: str, valeurs: tuple[int, ...], niveaux: dict[str, int]) -> dict:
            total, classes, a_valider, non_classables, sans_calcul, ecarts, manuels = valeurs
            return {
                "profil": code, "total": total, "classes": classes, "non_classes": total - classes,
                "a_valider": a_valider, "non_classables": non_classables, "sans_calcul": sans_calcul,
                "ecarts_moteur": ecarts, "manuels": manuels,
                "pourcentage": pourcentage(classes, total),
                "par_niveau": [{"niveau": n, "clients": int(niveaux.get(n, 0))} for n in NIVEAUX],
            }

        vide = (0,) * 7
        pp = bloc("PP", brut.get("PP", vide), par_niveau.get("PP", {}))
        pm = bloc("PM", brut.get("PM", vide), par_niveau.get("PM", {}))
        cumul = tuple(a + b for a, b in zip(brut.get("PP", vide), brut.get("PM", vide)))
        niveaux_glob = {n: par_niveau.get("PP", {}).get(n, 0) + par_niveau.get("PM", {}).get(n, 0) for n in NIVEAUX}
        lots_ouverts = int(await self.db.scalar(
            select(func.count()).select_from(ClienteleClassifLot)
            .where(ClienteleClassifLot.statut.in_(("ANALYSE", "EVALUE")))) or 0)
        return {
            "perimetre": perimetre,
            "perimetre_libelle": PERIMETRES[perimetre],
            "calcule_le": datetime.now().astimezone().isoformat(),
            "definition_classe": "Classification retenue enregistrée avec un niveau du référentiel "
                                 "(FAIBLE, MOYEN, ÉLEVÉ, INTERDIT). Un calcul moteur sans décision ne compte pas.",
            "pp": pp,
            "pm": pm,
            "global": bloc("GLOBAL", cumul, niveaux_glob),
            "hors_perimetre": {"non_identifies": brut.get("NON_IDENTIFIE", vide)[0]},
            "lots_ouverts": lots_ouverts,
        }

    # ------------------------------------------------------------------ listes
    def _requete(self, profil: str, f: dict) -> tuple[Select, Any]:
        S, K = ClienteleSituation, ClienteleClassification
        d = _dernier_calcul()
        stmt = (select(S, K, d.c.niveau_final, d.c.statut, d.c.created_at)
                .outerjoin(K, K.racine_client == S.racine_client)
                .outerjoin(d, d.c.racine_client == S.racine_client)
                .where(S.profil_derive == profil))
        classe = K.niveau.in_(NIVEAUX)
        non_classe = or_(K.niveau.is_(None), K.niveau.notin_(NIVEAUX))
        admissible = and_(d.c.statut.in_(STATUTS_MOTEUR_ADMISSIBLES), d.c.niveau_final.in_(NIVEAUX))
        if f.get("perimetre") == "OUVERTS":
            stmt = stmt.where(S.etat_client == "OUVERT")
        if f.get("etat") in ("OUVERT", "CLOTURE"):
            stmt = stmt.where(S.etat_client == f["etat"])
        if f.get("racine"):
            stmt = stmt.where(S.racine_client == f["racine"].strip())
        if f.get("nom"):
            t = f"%{f['nom'].strip()}%"
            stmt = stmt.where(or_(S.nom_client.ilike(t), S.prenoms.ilike(t)))
        if f.get("q"):
            t = f"%{f['q'].strip()}%"
            stmt = stmt.where(or_(S.racine_client.ilike(t), S.nom_client.ilike(t), S.prenoms.ilike(t),
                                  S.nni.ilike(t), S.nif.ilike(t)))
        if f.get("agence"):
            stmt = stmt.where(S.code_agence == f["agence"].strip())
        if f.get("classe") in NIVEAUX:
            stmt = stmt.where(K.niveau == f["classe"])
        statut = f.get("statut")
        if statut == "CLASSE":
            stmt = stmt.where(classe)
        elif statut == "NON_CLASSE":
            stmt = stmt.where(non_classe)
        elif statut == "A_VALIDER":
            stmt = stmt.where(non_classe, admissible)
        elif statut == "NON_CLASSABLE":
            stmt = stmt.where(non_classe, d.c.racine_client.is_not(None), ~admissible)
        elif statut == "NON_CALCULE":
            stmt = stmt.where(non_classe, d.c.racine_client.is_(None))
        elif statut == "ECART":
            stmt = stmt.where(classe, admissible, K.niveau != d.c.niveau_final)
        if f.get("analyste"):
            stmt = stmt.where(K.analyste_kyc.ilike(f"%{f['analyste'].strip()}%"))
        source = f.get("source")
        if source == "MANUELLES":
            stmt = stmt.where(K.source.in_(SOURCES_MANUELLES))
        elif source == "FICHIER":
            stmt = stmt.where(K.source.in_(SOURCES_FICHIER))
        elif source == "MOTEUR":
            stmt = stmt.where(K.source == "MOTEUR")
        if f.get("du"):
            stmt = stmt.where(func.date(K.classifie_le) >= f["du"])
        if f.get("au"):
            stmt = stmt.where(func.date(K.classifie_le) <= f["au"])
        return stmt, S

    @staticmethod
    def _ligne(s: ClienteleSituation, k: ClienteleClassification | None, niveau_moteur: str | None,
               statut_moteur: str | None, calcule_le: datetime | None) -> dict:
        admissible = statut_moteur in STATUTS_MOTEUR_ADMISSIBLES and niveau_moteur in NIVEAUX
        retenue = k.niveau if k and k.niveau in NIVEAUX else None
        if retenue:
            statut = "CLASSE"
        elif admissible:
            statut = "A_VALIDER"
        elif statut_moteur:
            statut = "NON_CLASSABLE"
        else:
            statut = "NON_CALCULE"
        mode = (k.mode_decision or MODE_PAR_SOURCE.get(k.source or "")) if k else None
        return {
            "racine_client": s.racine_client, "nom_client": s.nom_client, "prenoms": s.prenoms,
            "nni": s.nni, "nif": s.nif, "profil": s.profil_derive, "etat_client": s.etat_client,
            "code_agence": s.code_agence, "agence": s.agence,
            "classe_moteur": niveau_moteur if admissible else None,
            "statut_moteur": statut_moteur,
            "calcule_le": calcule_le.isoformat() if calcule_le else None,
            "classe_retenue": retenue,
            "source": k.source if k else None,
            "mode_decision": mode,
            "analyste_kyc": k.analyste_kyc if k else None,
            "classifie_le": k.classifie_le.isoformat() if k and k.classifie_le else None,
            "statut_classification": statut,
            "ecart_moteur": bool(retenue and admissible and retenue != niveau_moteur),
        }

    async def lister(self, *, profil: str, page: int = 1, taille: int = 50, **filtres) -> dict:
        self.ctx.exiger("clientele.classif.view")
        profil = _profil(profil)
        stmt, S = self._requete(profil, filtres)
        page, taille = max(1, page), min(max(1, taille), 200)
        total = await self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = (await self.db.execute(
            stmt.order_by(S.racine_client).offset((page - 1) * taille).limit(taille))).all()
        return {"total": int(total), "page": page, "taille": taille,
                "items": [self._ligne(*r) for r in rows]}

    # ------------------------------------------------------------------ exports
    async def apercu_export(self, *, profil: str, **filtres) -> dict:
        """Nombre de lignes exportées : filtres actuels vs tout le périmètre du profil."""
        self.ctx.exiger("clientele.export")
        self.ctx.exiger("clientele.classif.view")
        profil = _profil(profil)
        stmt_f, _ = self._requete(profil, filtres)
        stmt_t, _ = self._requete(profil, {"perimetre": filtres.get("perimetre")})
        compter = lambda s: self.db.scalar(select(func.count()).select_from(s.subquery()))  # noqa: E731
        return {"filtre": int(await compter(stmt_f) or 0), "tout": int(await compter(stmt_t) or 0),
                "max_xlsx": EXPORT_MAX_XLSX, "max_pdf": EXPORT_MAX_PDF}

    async def exporter(self, *, profil: str, format: str, portee: str = "filtre", **filtres) -> tuple[bytes, str]:
        self.ctx.exiger("clientele.export")
        self.ctx.exiger("clientele.classif.view")
        profil = _profil(profil)
        fmt = "pdf" if format == "pdf" else "xlsx"
        actifs = filtres if portee == "filtre" else {"perimetre": filtres.get("perimetre")}
        stmt, S = self._requete(profil, actifs)
        limite = EXPORT_MAX_PDF if fmt == "pdf" else EXPORT_MAX_XLSX
        total = int(await self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        if total > limite:
            raise AppError(
                f"{total} lignes : l'export {fmt.upper()} est limité à {limite:,} lignes. ".replace(",", " ")
                + ("Utilisez l'export Excel ou affinez les filtres." if fmt == "pdf" else "Affinez les filtres."),
                422, code="EXPORT_TROP_VOLUMINEUX")
        lignes = [self._ligne(*r) for r in (await self.db.execute(stmt.order_by(S.racine_client))).all()]

        identifiant = "NNI" if profil == "PP" else "NIF"
        if profil == "PP":
            entetes = ["Racine client", "NNI", "Nom", "Prénom(s)"]
        else:
            entetes = ["Racine client", "NIF", "Raison sociale"]
        entetes += ["Agence", "Classe moteur", "Classe retenue", "Source de décision", "Analyste KYC",
                    "Date de classification", "Statut de classification", "Écart moteur"]
        rows = []
        for x in lignes:
            base = [x["racine_client"], x["nni"] if profil == "PP" else x["nif"], x["nom_client"]]
            if profil == "PP":
                base.append(x["prenoms"])
            rows.append([_texte(v) for v in base + [
                x["code_agence"], x["classe_moteur"], x["classe_retenue"],
                LIBELLE_MODE.get(x["mode_decision"] or "", x["mode_decision"]), x["analyste_kyc"],
                _date_fr(datetime.fromisoformat(x["classifie_le"])) if x["classifie_le"] else None,
                STATUTS_CLASSIF[x["statut_classification"]], "Oui" if x["ecart_moteur"] else "",
            ]])

        classes = sum(1 for x in lignes if x["statut_classification"] == "CLASSE")
        perimetre = PERIMETRES.get(filtres.get("perimetre") or "TOUS", PERIMETRES["TOUS"])
        description_filtres = self._decrire(actifs)
        titre = f"Classification des {LIBELLE_PROFIL[profil]}"
        sous_titre = (f"Périmètre : {perimetre} · "
                      f"{'Filtres : ' + description_filtres if description_filtres else 'Sans filtre'} · "
                      f"Classés : {classes} / {len(lignes)} ({pourcentage_fr(pourcentage(classes, len(lignes)))})")
        jour = date.today().isoformat()
        nom = f"classification-{profil.lower()}-{'filtre' if portee == 'filtre' else 'complet'}-{jour}.{fmt}"
        if fmt == "pdf":
            garder = [i for i, h in enumerate(entetes) if h not in COLONNES_HORS_PDF]
            entetes_pdf = [entetes[i] for i in garder]
            contenu = build_styled_pdf(report_title=titre, headers=entetes_pdf,
                                       rows=[[r[i] for i in garder] for r in rows], subtitle=sous_titre,
                                       landscape_mode=len(entetes_pdf) > 6)
        else:
            synthese = [
                ["Liste", titre],
                ["Exporté le", format_export_datetime()],
                ["Périmètre", perimetre],
                ["Filtres appliqués", description_filtres or "Aucun"],
                ["Lignes exportées", len(lignes)],
                ["Clients classés", classes],
                ["Clients non classés", len(lignes) - classes],
                ["Pourcentage classé", pourcentage_fr(pourcentage(classes, len(lignes)))],
                ["Identifiant", f"{identifiant} affiché selon les droits de consultation de la Base Clientèle"],
            ]
            contenu = build_styled_workbook_multi(
                report_title=titre,
                sheets=[(f"Classification {profil}", "Liste", entetes, rows),
                        ("Synthèse", "Synthèse", ["Indicateur", "Valeur"], synthese)],
                subtitle=sous_titre,
            )
        await self.svc.audit("clientele.suivi.export", "clientele_classification", None, after={
            "profil": profil, "format": fmt, "portee": portee, "lignes": len(lignes),
            "filtres": sorted(k for k, v in actifs.items() if v),
        })
        return contenu, nom

    @staticmethod
    def _decrire(f: dict) -> str:
        parts = []
        libelles = {
            "racine": "racine", "nom": "nom", "q": "recherche", "agence": "agence", "classe": "classe",
            "statut": "statut", "analyste": "analyste", "source": "source", "etat": "état",
        }
        for cle, lib in libelles.items():
            v = f.get(cle)
            if v:
                v = STATUTS_CLASSIF.get(v, v) if cle == "statut" else v
                parts.append(f"{lib} = {v}")
        if f.get("du") or f.get("au"):
            parts.append(f"classé du {_date_fr(f.get('du')) or '…'} au {_date_fr(f.get('au')) or '…'}")
        return ", ".join(parts)

    async def exporter_progression(self, *, perimetre: str = "TOUS", format: str = "xlsx") -> tuple[bytes, str]:
        self.ctx.exiger("clientele.export")
        p = await self.progression(perimetre=perimetre)
        entetes = ["Population", "Total", "Classés", "Non classés", "% classés", "Propositions à valider",
                   "Sans résultat moteur", "Non calculés", "Écarts moteur / retenue", "Décisions manuelles"]
        rows = []
        for cle, lib in (("pp", "Personnes physiques (PP)"), ("pm", "Personnes morales (PM)"), ("global", "Total PP + PM")):
            b = p[cle]
            rows.append([lib, b["total"], b["classes"], b["non_classes"], pourcentage_fr(b["pourcentage"]),
                         b["a_valider"], b["non_classables"], b["sans_calcul"], b["ecarts_moteur"], b["manuels"]])
        niveaux = [["PP", *[x["clients"] for x in p["pp"]["par_niveau"]]],
                   ["PM", *[x["clients"] for x in p["pm"]["par_niveau"]]],
                   ["Total", *[x["clients"] for x in p["global"]["par_niveau"]]]]
        titre = "Progression de la classification"
        sous_titre = f"Périmètre : {p['perimetre_libelle']} · Hors périmètre (profil non identifié) : " \
                     f"{p['hors_perimetre']['non_identifies']}"
        jour = date.today().isoformat()
        await self.svc.audit("clientele.suivi.progression.export", "clientele_classification", None,
                             after={"format": format, "perimetre": p["perimetre"]})
        if format == "pdf":
            return (build_styled_pdf(report_title=titre, headers=entetes, rows=rows, subtitle=sous_titre),
                    f"progression-classification-{jour}.pdf")
        return (build_styled_workbook_multi(report_title=titre, subtitle=sous_titre, sheets=[
            ("Progression", "Progression", entetes, rows),
            ("Classes retenues", "Répartition par classe", ["Profil", "Faible", "Moyen", "Élevé", "Interdit"], niveaux),
        ]), f"progression-classification-{jour}.xlsx")
