"""Tableau de bord 360° et exports Excel / PDF — toujours filtrés par le périmètre de l'utilisateur.

Les indicateurs comptent des **dossiers** ; les opérations sont agrégées par dossier avant toute
répartition, de sorte qu'un dossier à plusieurs opérations n'est compté qu'une fois et que
chaque montant n'est additionné qu'une seule fois.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reclamation, ReclamationOperation
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.dossiers import Contexte, _filtres, libelle_motif, libelle_sous_motif, ligne
from app.services.reclamations.outils import maintenant
from app.services.reporting_export import build_styled_pdf, build_styled_workbook_multi, format_period_label

ZERO = Decimal("0")
AUTRE_SAISIE = "AUTRE"
LIMITE_EXPORT = 5000


async def _resumes(db: AsyncSession, ids_query) -> dict[uuid.UUID, tuple[int, Decimal | None]]:
    rows = (await db.execute(
        select(ReclamationOperation.reclamation_id, func.count(), func.sum(ReclamationOperation.montant))
        .where(ReclamationOperation.reclamation_id.in_(ids_query))
        .group_by(ReclamationOperation.reclamation_id))).all()
    return {rid: (n, somme) for rid, n, somme in rows}


def _repartition(rows: list[Reclamation], resumes: dict, cle: Callable[[Reclamation], object],
                 libelle: Callable[[object], str | None]) -> list[dict]:
    acc: dict[object, list] = {}
    for r in rows:
        k = cle(r)
        if k is None:
            continue
        n_ops, montant = resumes.get(r.id, (0, None))
        a = acc.setdefault(k, [0, 0, ZERO])
        a[0] += 1
        a[1] += n_ops
        a[2] += montant or ZERO
    out = [{"id": str(k), "libelle": libelle(k) or "—", "n": n, "nb_operations": nops, "montant": str(m)}
           for k, (n, nops, m) in acc.items()]
    return sorted(out, key=lambda x: (-x["n"], x["libelle"]))


async def tableau_de_bord(db: AsyncSession, s: ReclamationsScope, filtres: dict | None = None) -> dict:
    ctx = await Contexte.charger(db)
    q = _filtres(select(Reclamation).where(s.filtre_dossiers()), filtres or {})
    rows = list((await db.scalars(q)).all())
    resumes = await _resumes(db, _filtres(select(Reclamation.id).where(s.filtre_dossiers()), filtres or {}))
    now = maintenant()
    ouvertes = [r for r in rows if r.statut not in C.STATUTS_TERMINAUX and not r.archivee_le]
    retards = [r for r in ouvertes if r.echeance and r.echeance < now]
    sans_echeance = [r for r in ouvertes if r.echeance is None]
    recents = sorted(rows, key=lambda r: r.updated_at or r.created_at or now, reverse=True)[:8]
    depuis = now - timedelta(days=30)

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

    montant_total = sum((m or ZERO for _, m in resumes.values()), ZERO)
    return {
        "total": len(rows),
        "ouvertes": len(ouvertes),
        "retards": len(retards),
        "sans_echeance": len(sans_echeance),
        "volume_30j": sum(1 for r in rows if r.date_premiere_reception >= depuis),
        "cloturees_30j": sum(1 for r in rows if r.date_cloture and r.date_cloture >= depuis),
        "nb_operations": sum(n for n, _ in resumes.values()),
        "dossiers_avec_operations": sum(1 for n, _ in resumes.values() if n),
        "montant_total": str(montant_total),
        "devise": C.DEVISE,
        "statuts": _compte(C.STATUT_LIBELLES, "statut"),
        "etapes": _compte(C.ETAPE_LIBELLES, "etape"),
        "priorites": _compte(C.PRIORITE_LIBELLES, "priorite"),
        "types": _repartition(rows, resumes, lambda r: r.type_id, ctx.lib),
        "motifs": _repartition(rows, resumes, _motif, _lib_motif),
        "canaux": _repartition(rows, resumes, lambda r: r.canal_id, ctx.lib),
        "agences": _repartition(rows, resumes, lambda r: r.client_agence_id,
                                lambda i: (ctx.agence(i) or {}).get("libelle")),
        "services": _repartition(rows, resumes, lambda r: r.unite_traitement_id or r.unite_concernee_id,
                                 _lib_unite),
        "unites_reception": _repartition(rows, resumes, lambda r: r.unite_reception_id, _lib_unite),
        "recents": [ligne(r, ctx, resume=resumes.get(r.id)) for r in recents],
        "dossiers_retard": [ligne(r, ctx, resume=resumes.get(r.id)) for r in retards[:15]],
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
    if filtres.get("en_retard"):
        morceaux.append("En retard")
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
    resumes: dict[uuid.UUID, list] = {}
    for o in operations:
        a = resumes.setdefault(o.reclamation_id, [0, ZERO])
        a[0] += 1
        a[1] += o.montant or ZERO
    nb_total = sum(n for n, _ in resumes.values())
    montant_total = sum((m for _, m in resumes.values()), ZERO)

    def agence(r):
        return (ctx.agence(r.client_agence_id) or {}).get("libelle")

    def service(r):
        return (ctx.unite(r.unite_traitement_id or r.unite_concernee_id) or {}).get("libelle")

    sous_titre = _sous_titre(filtres, len(rows))
    titre = "Registre des réclamations clients"

    if format == "pdf":
        entetes = ["Référence", "Date", "Client", "Agence", "Canal", "Motif / sous-motif", "Objet",
                   "Service", "Statut", "Nb op.", f"Montant ({C.DEVISE})", "Échéance"]
        lignes = []
        for r in rows:
            nb, total = resumes.get(r.id, (0, ZERO))
            motif = libelle_motif(ctx, r) or "—"
            sous = libelle_sous_motif(ctx, r)
            lignes.append([
                r.reference, _jour(r.date_reclamation or r.date_premiere_reception), r.client_nom, agence(r),
                ctx.lib(r.canal_id), f"{motif} / {sous}" if sous else motif, r.objet, service(r),
                C.STATUT_LIBELLES.get(r.statut, r.statut), nb, total if nb else None, _jour(r.echeance),
            ])
        vide = " "
        lignes.append(["Total", vide, vide, vide, vide, vide, vide, vide, f"{len(rows)} dossier(s)",
                       nb_total, montant_total, vide])
        largeurs = [36, 20, 30, 30, 28, 36, 40, 28, 22, 12, 28, 20]
        aligns = ["left", "center", "left", "left", "left", "left", "left", "left", "center", "right", "right", "center"]
        return build_styled_pdf(report_title=titre, headers=entetes, rows=lignes, subtitle=sous_titre,
                                col_widths=largeurs, col_aligns=aligns)

    entetes = ["Référence", "Date réclamation", "Réception banque", "Client", "Racine", "Agence", "Canal",
               "Type", "Motif", "Sous-motif", "Objet", "Service concerné", "Service de traitement",
               "Priorité", "Étape", "Statut", "Nb opérations", f"Montant total ({C.DEVISE})", "Échéance",
               "Clôture", "Résultat"]
    lignes = []
    for r in rows:
        nb, total = resumes.get(r.id, (0, ZERO))
        lignes.append([
            r.reference, _jour(r.date_reclamation), _jour(r.date_premiere_reception), r.client_nom,
            r.client_racine, agence(r), ctx.lib(r.canal_id), ctx.lib(r.type_id),
            libelle_motif(ctx, r), libelle_sous_motif(ctx, r), r.objet,
            (ctx.unite(r.unite_concernee_id) or {}).get("libelle"),
            (ctx.unite(r.unite_traitement_id) or {}).get("libelle"), C.PRIORITE_LIBELLES.get(r.priorite),
            C.ETAPE_LIBELLES.get(r.etape), C.STATUT_LIBELLES.get(r.statut), nb, total if nb else None,
            _jour(r.echeance), _jour(r.date_cloture), C.RESULTAT_LIBELLES.get(r.resultat or ""),
        ])
    lignes.append(["Total", f"{len(rows)} dossier(s)", *([None] * 14), nb_total, montant_total, None, None, None])
    references = {r.id: r for r in rows}
    lignes_ops = [[references[o.reclamation_id].reference, references[o.reclamation_id].client_nom, o.ordre,
                   o.reference, o.montant, o.devise] for o in operations]
    lignes_ops.append(["Total", None, len(operations), None, montant_total, C.DEVISE])
    return build_styled_workbook_multi(
        report_title=titre,
        sheets=[
            ("Réclamations", "Dossiers", entetes, lignes),
            ("Opérations", "Opérations concernées",
             ["Réclamation", "Client", "N°", "Référence de l'opération", "Montant", "Devise"], lignes_ops),
        ],
        subtitle=sous_titre,
    )


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
