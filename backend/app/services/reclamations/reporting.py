"""Tableau de bord 360° et exports Excel / PDF — toujours filtrés par le périmètre de l'utilisateur.

Les indicateurs comptent des **dossiers** ; les opérations sont agrégées par dossier avant toute
répartition, de sorte qu'un dossier à plusieurs opérations n'est compté qu'une fois et que
chaque montant n'est additionné qu'une seule fois.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reclamation, ReclamationOperation
from app.services.reclamations import constantes as C
from app.services.reclamations import indicateurs as I
from app.services.reclamations import operations as ops
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.dossiers import (
    AUCUNE,
    Contexte,
    _filtres,
    libelle_motif,
    libelle_sous_motif,
    ligne,
)
from app.services.reclamations.outils import maintenant
from app.services.reporting_export import build_styled_pdf, build_styled_workbook_multi, format_period_label

ZERO = Decimal("0")
AUTRE_SAISIE = "AUTRE"
LIMITE_EXPORT = 5000


async def _resumes(db: AsyncSession, ids_query) -> dict[uuid.UUID, tuple[int, Decimal | None, str | None]]:
    """Par dossier : (nb opérations, montant si devise unique, devise) — voir ``operations.resumes``."""
    return await ops.resumes(db, ids_query)


async def _par_devise(db: AsyncSession, ids_query) -> tuple[dict[uuid.UUID, Decimal], list[dict]]:
    """Montant en devise de référence par dossier, et totaux par devise (jamais additionnés entre eux)."""
    rows = (await db.execute(
        select(ReclamationOperation.reclamation_id, ReclamationOperation.devise, func.sum(ReclamationOperation.montant))
        .where(ReclamationOperation.reclamation_id.in_(ids_query), ReclamationOperation.devise.is_not(None))
        .group_by(ReclamationOperation.reclamation_id, ReclamationOperation.devise))).all()
    reference: dict[uuid.UUID, Decimal] = {}
    totaux: dict[str, Decimal] = {}
    for rid, devise, somme in rows:
        if somme is None:
            continue
        totaux[devise] = totaux.get(devise, ZERO) + somme
        if devise == C.DEVISE:
            reference[rid] = somme
    return reference, [{"devise": d, "montant": str(m)}
                       for d, m in sorted(totaux.items(), key=lambda x: (x[0] != C.DEVISE, x[0]))]


def _repartition(rows: list[Reclamation], resumes: dict, cle: Callable[[Reclamation], object],
                 libelle: Callable[[object], str | None], *, aucun: str | None = None,
                 montants: dict[uuid.UUID, Decimal] | None = None) -> list[dict]:
    """``aucun`` : libellé de la ligne regroupant les dossiers sans valeur (sinon ignorés).
    ``montant`` : opérations en devise de référence uniquement."""
    acc: dict[object, list] = {}
    montants = montants or {}
    for r in rows:
        k = cle(r)
        if k is None:
            if aucun is None:
                continue
            k = AUCUNE
        n_ops = resumes.get(r.id, (0, None, None))[0]
        a = acc.setdefault(k, [0, 0, ZERO])
        a[0] += 1
        a[1] += n_ops
        a[2] += montants.get(r.id, ZERO)
    out = [{"id": str(k), "libelle": (aucun if k == AUCUNE else libelle(k)) or "—", "n": n,
            "nb_operations": nops, "montant": str(m)} for k, (n, nops, m) in acc.items()]
    return sorted(out, key=lambda x: (-x["n"], x["libelle"]))


def _compter(valeurs) -> list[tuple[str, int]]:
    acc: dict[str, int] = {}
    for v in valeurs:
        acc[v] = acc.get(v, 0) + 1
    return sorted(acc.items(), key=lambda kv: -kv[1])


def _performance(rows: list[Reclamation]) -> dict:
    """Délai moyen de clôture, sur les seuls dossiers clôturés."""
    cloturees = [r for r in rows if r.statut == "CLOTUREE" and r.date_cloture]
    jours = [(r.date_cloture - r.date_premiere_reception).total_seconds() / 86400 for r in cloturees]
    return {
        "cloturees": len(cloturees),
        "delai_moyen_jours": round(sum(jours) / len(jours), 1) if jours else None,
    }


TRANCHES_ANCIENNETE = (("0-7", "0 à 7 jours", 7), ("8-15", "8 à 15 jours", 15),
                       ("16-30", "16 à 30 jours", 30), ("30+", "Plus de 30 jours", None))


def _anciennete(ouvertes: list[Reclamation], now) -> list[dict]:
    n = dict.fromkeys((code for code, _, _ in TRANCHES_ANCIENNETE), 0)
    for r in ouvertes:
        age = (now - r.date_premiere_reception).days
        code = next(c for c, _, borne in TRANCHES_ANCIENNETE if borne is None or age <= borne)
        n[code] += 1
    return [{"code": c, "libelle": lib, "n": n[c]} for c, lib, _ in TRANCHES_ANCIENNETE]


MOIS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")


def _tendance(rows: list[Reclamation], now, nb_mois: int = 12) -> list[dict]:
    """Reçues et clôturées par mois calendaire, sur les ``nb_mois`` derniers mois (mois courant inclus)."""
    cles: list[tuple[int, int]] = []
    annee, mois = now.year, now.month
    for _ in range(nb_mois):
        cles.append((annee, mois))
        annee, mois = (annee - 1, 12) if mois == 1 else (annee, mois - 1)
    cles.reverse()
    recues = dict.fromkeys(cles, 0)
    cloturees = dict.fromkeys(cles, 0)
    for r in rows:
        k = (r.date_premiere_reception.year, r.date_premiere_reception.month)
        if k in recues:
            recues[k] += 1
        if r.date_cloture:
            k = (r.date_cloture.year, r.date_cloture.month)
            if k in cloturees:
                cloturees[k] += 1
    return [{"mois": f"{a}-{m:02d}", "libelle": f"{MOIS[m - 1]} {a % 100:02d}", "recues": recues[(a, m)],
             "cloturees": cloturees[(a, m)]} for a, m in cles]


def _recurrents(rows: list[Reclamation], limite: int = 5) -> list[dict]:
    """Clients (racine) ayant déposé au moins deux réclamations dans le périmètre filtré."""
    acc: dict[str, dict] = {}
    for r in rows:
        if not r.client_racine:
            continue
        a = acc.setdefault(r.client_racine, {"racine": r.client_racine, "nom": r.client_nom, "n": 0, "ouvertes": 0})
        a["n"] += 1
        if r.statut not in C.STATUTS_TERMINAUX:
            a["ouvertes"] += 1
    return sorted((a for a in acc.values() if a["n"] >= 2), key=lambda a: (-a["n"], a["nom"] or ""))[:limite]


def _jour_iso(d) -> str | None:
    return d.isoformat() if d else None


def liens_kpi(filtres: dict, aujourdhui) -> dict:
    """Paramètres de liste reproduisant exactement chaque KPI cliquable (mêmes filtres, même période)."""
    debut, fin = filtres.get("date_debut"), filtres.get("date_fin")
    debut_30j = max(d for d in (aujourdhui - timedelta(days=30), debut) if d)
    return {
        "volume_30j": {"date_debut": _jour_iso(debut_30j), "date_fin": _jour_iso(fin)},
        "ouvertes": {"date_debut": _jour_iso(debut), "date_fin": _jour_iso(fin), "ouvertes": "true"},
        "operations": {"date_debut": _jour_iso(debut), "date_fin": _jour_iso(fin), "indicateur": "avec_operations"},
        "delai_moyen": {"indicateur": "delai_cloture_termines", "kpi_debut": _jour_iso(debut),
                        "kpi_fin": _jour_iso(fin)},
        "total": {"date_debut": _jour_iso(debut), "date_fin": _jour_iso(fin)},
        "suspendues": {"date_debut": _jour_iso(debut), "date_fin": _jour_iso(fin), "statut": C.STATUT_SUSPENDU},
    }


async def tableau_de_bord(db: AsyncSession, s: ReclamationsScope, filtres: dict | None = None) -> dict:
    filtres = filtres or {}
    ctx = await Contexte.charger(db)
    q = _filtres(select(Reclamation).where(s.filtre_dossiers()), filtres)
    rows = list((await db.scalars(q)).all())
    ids_query = _filtres(select(Reclamation.id).where(s.filtre_dossiers()), filtres)
    resumes = await _resumes(db, ids_query)
    montants, par_devise = await _par_devise(db, ids_query)
    now = maintenant()
    ouvertes = [r for r in rows if r.statut not in C.STATUTS_TERMINAUX and not r.archivee_le]
    recents = sorted(rows, key=lambda r: r.updated_at or r.created_at or now, reverse=True)[:8]
    liens = liens_kpi(filtres, now.date())
    depuis = I.borne(date.fromisoformat(liens["volume_30j"]["date_debut"]))
    periode = I.Periode.de(filtres.get("date_debut"), filtres.get("date_fin"))
    d_cloture = await I.delai_cloture(db, s, filtres, periode)

    def _compte(valeurs: dict[str, str], attr: str) -> list[dict]:
        n = {k: 0 for k in valeurs}
        for r in rows:
            n[getattr(r, attr)] = n.get(getattr(r, attr), 0) + 1
        return [{"code": k, "libelle": valeurs.get(k, k), "n": v} for k, v in n.items()]

    def _motif(r: Reclamation):
        return AUTRE_SAISIE if r.motif_autre else r.motif_id

    def _lib_motif(k) -> str | None:
        return f"{C.AUTRE} (saisie libre)" if k == AUTRE_SAISIE else ctx.lib(k)

    def _lib_unite(i) -> str | None:
        return (ctx.unite(i) or {}).get("libelle")

    montant_total = sum(montants.values(), ZERO)
    return {
        "total": len(rows),
        "ouvertes": len(ouvertes),
        "suspendues": sum(1 for r in ouvertes if r.statut == C.STATUT_SUSPENDU),
        "volume_30j": sum(1 for r in rows if r.date_premiere_reception >= depuis),
        "volume_30j_precedent": sum(1 for r in rows if depuis - timedelta(days=30) <= r.date_premiere_reception < depuis),
        "cloturees_30j": sum(1 for r in rows if r.date_cloture and r.date_cloture >= depuis),
        "performance": {**_performance(rows),
                        "delai_cloture_jours": d_cloture["termines"]["moyenne_jours"],
                        "delai_cloture_n": d_cloture["termines"]["n"]},
        "liens": liens,
        "filtres": {"client_agence_id": str(filtres["client_agence_id"]) if filtres.get("client_agence_id") else None,
                    "date_debut": _jour_iso(filtres.get("date_debut")), "date_fin": _jour_iso(filtres.get("date_fin"))},
        "anciennete": _anciennete(ouvertes, now),
        "tendance": _tendance(rows, now),
        "resultats": [{"code": k, "libelle": C.RESULTAT_LIBELLES.get(k, k), "n": n}
                      for k, n in _compter(r.resultat for r in rows if r.statut == "CLOTUREE" and r.resultat)],
        "clients_recurrents": _recurrents(rows),
        "nb_operations": sum(v[0] for v in resumes.values()),
        "dossiers_avec_operations": sum(1 for v in resumes.values() if v[0]),
        "montant_total": str(montant_total),
        "devise": C.DEVISE,
        "montants_par_devise": par_devise,
        "statuts": _compte(C.STATUT_LIBELLES, "statut"),
        "etapes": _compte(C.ETAPE_LIBELLES, "etape"),
        "priorites": _compte(C.PRIORITE_LIBELLES, "priorite"),
        "types": _repartition(rows, resumes, lambda r: r.type_id, ctx.lib, montants=montants),
        "motifs": _repartition(rows, resumes, _motif, _lib_motif, montants=montants),
        "canaux": _repartition(rows, resumes, lambda r: r.canal_id, ctx.lib, montants=montants),
        "agences": _repartition(rows, resumes, lambda r: r.client_agence_id,
                                lambda i: (ctx.agence(i) or {}).get("libelle"), aucun="Sans agence",
                                montants=montants),
        "services": _repartition(rows, resumes, lambda r: r.unite_traitement_id or r.unite_concernee_id,
                                 _lib_unite, montants=montants),
        "unites_reception": _repartition(rows, resumes, lambda r: r.unite_reception_id, _lib_unite,
                                         montants=montants),
        "points_reception": _repartition(rows, resumes, lambda r: r.point_reception_id, ctx.lib,
                                         aucun="Non renseigné", montants=montants),
        "departements": _repartition(rows, resumes, lambda r: r.org_departement_id,
                                     lambda i: (ctx.entite(i) or {}).get("libelle"), aucun="Non renseigné",
                                     montants=montants),
        "regularisations": [{"code": k, "libelle": C.REGULARISATION_LIBELLES.get(k, k), "n": n}
                            for k, n in _compter(r.regularisation_statut for r in rows if r.regularisation_statut)],
        "recents": [ligne(r, ctx, resume=resumes.get(r.id)) for r in recents],
    }


def _jour(v) -> str | None:
    return v.strftime("%d/%m/%Y") if v else None


def _sous_titre(filtres: dict, total: int) -> str:
    morceaux = [f"{total} réclamation(s) — périmètre de l'utilisateur"]
    periode = format_period_label(filtres.get("date_debut"), filtres.get("date_fin"))
    if periode:
        morceaux.append(periode)
    if filtres.get("ouvertes"):
        morceaux.append("En cours uniquement")
    if filtres.get("indicateur"):
        periode_kpi = format_period_label(filtres.get("kpi_debut"), filtres.get("kpi_fin"))
        morceaux.append(f"Indicateur : {filtres['indicateur']}" + (f" ({periode_kpi})" if periode_kpi else ""))
    if total >= LIMITE_EXPORT:
        morceaux.append(f"limité aux {LIMITE_EXPORT} premières")
    return " · ".join(morceaux)


async def exporter(db: AsyncSession, s: ReclamationsScope, filtres: dict | None = None,
                   format: str = "xlsx") -> bytes:
    """Export de la liste filtrée : Excel (réclamations + opérations) ou PDF paysage, habillage banque."""
    s.exiger("reclamations.reporting.export", "reclamations.reporting.view")
    filtres = filtres or {}
    ctx = await Contexte.charger(db)
    q = select(Reclamation).where(s.filtre_dossiers()).order_by(Reclamation.date_premiere_reception.desc())
    q = _filtres(q, filtres)
    rows = list((await db.scalars(q.limit(LIMITE_EXPORT))).all())
    ids = [r.id for r in rows]
    operations = list((await db.scalars(select(ReclamationOperation).where(
        ReclamationOperation.reclamation_id.in_(ids)).order_by(
        ReclamationOperation.reclamation_id, ReclamationOperation.ordre)))) if ids else []
    par_dossier: dict[uuid.UUID, list[ReclamationOperation]] = {}
    for o in operations:
        par_dossier.setdefault(o.reclamation_id, []).append(o)
    resumes: dict[uuid.UUID, tuple[int, Decimal | None, str]] = {}
    for rid, liste in par_dossier.items():
        total, devise = ops.montant_unique(liste)
        resumes[rid] = (len(liste), total, devise or "multi-devises")
    nb_total = len(operations)
    totaux_devise = ops.par_devise(operations)
    montant_total = next((Decimal(t["montant"]) for t in totaux_devise
                          if t["devise"] == C.DEVISE and t["montant"]), ZERO)
    autres_devises = " · ".join(f"{t['devise']} : {t['montant']}" for t in totaux_devise
                                if t["devise"] not in (C.DEVISE, None) and t["montant"])

    def agence(r):
        return (ctx.agence(r.client_agence_id) or {}).get("libelle")

    def service(r):
        return (ctx.unite(r.unite_traitement_id or r.unite_concernee_id) or {}).get("libelle")

    sous_titre = " · ".join([_sous_titre(filtres, len(rows)), *_filtres_libelle(ctx, filtres),
                             *([f"Autres devises (non converties) — {autres_devises}"] if autres_devises else [])])
    titre = "Registre des réclamations clients"

    if format == "pdf":
        entetes = ["Référence", "Date", "Client", "Agence", "Canal", "Motif / sous-motif", "Objet",
                   "Service", "Statut", "Nb op.", "Montant", "Devise"]
        lignes = []
        for r in rows:
            nb, total, devise = resumes.get(r.id, (0, None, None))
            motif = libelle_motif(ctx, r) or "—"
            sous = libelle_sous_motif(ctx, r)
            lignes.append([
                r.reference, _jour(r.date_reclamation or r.date_premiere_reception), r.client_nom, agence(r),
                ctx.lib(r.canal_id), f"{motif} / {sous}" if sous else motif, r.objet, service(r),
                C.STATUT_LIBELLES.get(r.statut, r.statut), nb, total if nb else None, devise if nb else None,
            ])
        vide = " "
        lignes.append(["Total", vide, vide, vide, vide, vide, vide, vide, f"{len(rows)} dossier(s)",
                       nb_total, montant_total, C.DEVISE])
        largeurs = [36, 20, 30, 30, 28, 36, 40, 28, 22, 12, 26, 14]
        aligns = ["left", "center", "left", "left", "left", "left", "left", "left", "center", "right", "right",
                  "center"]
        return build_styled_pdf(report_title=titre, headers=entetes, rows=lignes, subtitle=sous_titre,
                                col_widths=largeurs, col_aligns=aligns)

    entetes = ["Référence", "Date réclamation", "Réception banque", "Client", "Racine", "Agence", "Canal",
               "Type", "Motif", "Sous-motif", "Objet", "Point de réception", "Agence de réception",
               "Département concerné", "Service concerné (organigramme)", "Unité concernée", "Service de traitement",
               "Priorité", "Étape", "Statut", "Nb opérations", "Montant total", "Devise", "Régularisation",
               "Clôture", "Résultat"]
    lignes = []
    for r in rows:
        nb, total, devise = resumes.get(r.id, (0, None, None))
        lignes.append([
            r.reference, _jour(r.date_reclamation), _jour(r.date_premiere_reception), r.client_nom,
            r.client_racine, agence(r), ctx.lib(r.canal_id), ctx.lib(r.type_id),
            libelle_motif(ctx, r), libelle_sous_motif(ctx, r), r.objet,
            ctx.lib(r.point_reception_id), (ctx.agence(r.agence_reception_id) or {}).get("libelle"),
            (ctx.entite(r.org_departement_id) or {}).get("libelle"),
            (ctx.entite(r.org_service_id) or {}).get("libelle"),
            (ctx.unite(r.unite_concernee_id) or {}).get("libelle"),
            (ctx.unite(r.unite_traitement_id) or {}).get("libelle"), C.PRIORITE_LIBELLES.get(r.priorite),
            C.ETAPE_LIBELLES.get(r.etape), C.STATUT_LIBELLES.get(r.statut), nb, total if nb else None,
            devise if nb else None, C.REGULARISATION_LIBELLES.get(r.regularisation_statut or ""),
            _jour(r.date_cloture), C.RESULTAT_LIBELLES.get(r.resultat or ""),
        ])
    lignes.append(["Total", f"{len(rows)} dossier(s)", *([None] * 18), nb_total, montant_total,
                   C.DEVISE, None, None, None])
    references = {r.id: r for r in rows}
    lignes_ops = [[references[o.reclamation_id].reference, references[o.reclamation_id].client_nom, o.ordre,
                   o.reference, C.NATURE_LIBELLES.get(o.nature_mouvement or ""), o.date_operation, o.montant,
                   o.montant_conteste, o.devise] for o in operations]
    for t in totaux_devise:
        lignes_ops.append([f"Total {t['devise'] or 'sans devise'}", None, t["nb"], None, None, None,
                           Decimal(t["montant"]) if t["montant"] else None,
                           Decimal(t["montant_conteste"]) if t["montant_conteste"] else None, t["devise"]])
    return build_styled_workbook_multi(
        report_title=titre,
        sheets=[
            ("Réclamations", "Dossiers", entetes, lignes),
            ("Opérations", "Opérations concernées",
             ["Réclamation", "Client", "N°", "Référence de l'opération", "Nature", "Date", "Montant initial",
              "Montant à extourner", "Devise"], lignes_ops),
        ],
        subtitle=sous_titre,
    )


def _na(v, suffixe: str = "") -> str:
    if v is None or v == "":
        return "N/A"
    if isinstance(v, float):
        return f"{v:.1f}".replace(".", ",") + suffixe
    return f"{v}{suffixe}"


def _filtres_libelle(ctx: Contexte, filtres: dict) -> list[str]:
    morceaux = []
    agence = filtres.get("client_agence_id")
    if agence == AUCUNE:
        morceaux.append("Agence : sans agence")
    elif agence:
        morceaux.append(f"Agence : {(ctx.agence(agence) or {}).get('libelle', '—')}")
    else:
        morceaux.append("Toutes les agences")
    for champ, nom in (("type_id", "Type"), ("canal_id", "Canal"), ("unite_concernee_id", "Service")):
        if filtres.get(champ):
            lib = ctx.lib(filtres[champ]) if champ != "unite_concernee_id" else (ctx.unite(filtres[champ]) or {}).get("libelle")
            morceaux.append(f"{nom} : {lib or '—'}")
    if filtres.get("org_entite_libelle"):
        morceaux.append(f"Organigramme : {filtres['org_entite_libelle']}")
    return morceaux


def _lignes_comparaison(comp: dict) -> list[list]:
    out = []
    for lg in comp["lignes"]:
        appreciation = {True: "Favorable", False: "Défavorable"}.get(lg["favorable"], "—")
        out.append([lg["libelle"], _na(lg["a"]), _na(lg["b"]), _na(lg["ecart"]),
                    _na(lg["variation"], " %"), appreciation])
    return out


async def exporter_comparaison(db: AsyncSession, s: ReclamationsScope, filtres: dict, pa, pb,
                               format: str = "xlsx") -> bytes:
    s.exiger("reclamations.reporting.export", "reclamations.reporting.view")
    ctx = await Contexte.charger(db)
    comp = await I.comparaison(db, s, filtres, pa, pb)
    titre = "Comparaison de deux périodes — réclamations"
    sous_titre = " · ".join([
        f"A (référence) : {format_period_label(pa.jour_debut, pa.jour_fin)}",
        f"B : {format_period_label(pb.jour_debut, pb.jour_fin)}", *_filtres_libelle(ctx, filtres),
        *comp["avertissements"]])
    entetes = ["Indicateur", "Période A", "Période B", "Écart (B − A)", "Variation", "Appréciation"]
    lignes = _lignes_comparaison(comp)
    if format == "pdf":
        return build_styled_pdf(report_title=titre, headers=entetes, rows=lignes, subtitle=sous_titre)
    return build_styled_workbook_multi(report_title=titre, subtitle=sous_titre, sheets=[
        ("Comparaison", "Période A / période B", entetes, lignes),
        ("Méthode", "Règles de calcul", ["Règle", "Détail"], [
            ["Variation", "Écart ÷ valeur de la période A × 100 ; N/A si la valeur de référence vaut 0"],
            ["Appréciation", "Indiquée seulement si le sens favorable est défini (délais et réouverture : "
                             "baisse favorable ; clôtures : hausse favorable)"],
            ["Périodes", "Chaque flux est daté par son propre événement (réception, clôture, réouverture, fin du délai mesuré)"],
        ]),
    ])


async def circuit(db: AsyncSession, s: ReclamationsScope) -> dict:
    """Colonnes du circuit (dossiers ouverts du périmètre, hors archives)."""
    ctx = await Contexte.charger(db)
    rows = list((await db.scalars(select(Reclamation).where(
        s.filtre_dossiers(), Reclamation.archivee_le.is_(None),
        Reclamation.statut.not_in(C.STATUTS_TERMINAUX),
    ).order_by(Reclamation.date_premiere_reception.desc()))).all())
    resumes = await _resumes(db, [r.id for r in rows]) if rows else {}
    colonnes: dict[str, list] = {e: [] for e in C.ETAPE_LIBELLES}
    for r in rows:
        colonnes.setdefault(r.etape, []).append(ligne(r, ctx, resume=resumes.get(r.id)))
    return {
        "colonnes": [{"etape": e, "libelle": C.ETAPE_LIBELLES[e], "items": colonnes.get(e, [])}
                     for e in C.ETAPE_LIBELLES],
        "total": len(rows),
    }
