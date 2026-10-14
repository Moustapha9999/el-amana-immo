"""Tableau de bord 360° et export Excel — toujours filtrés par le périmètre de l'utilisateur.

Les indicateurs comptent des **dossiers** ; les opérations sont agrégées par dossier avant toute
répartition, de sorte qu'un dossier à plusieurs opérations n'est compté qu'une fois et que
chaque montant n'est additionné qu'une seule fois.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reclamation, ReclamationOperation
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.dossiers import Contexte, _filtres, libelle_motif, libelle_sous_motif, ligne
from app.services.reclamations.outils import iso, maintenant

ZERO = Decimal("0")
AUTRE_SAISIE = "AUTRE"


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


async def exporter(db: AsyncSession, s: ReclamationsScope, filtres: dict | None = None) -> bytes:
    s.exiger("reclamations.reporting.export", "reclamations.reporting.view")
    ctx = await Contexte.charger(db)
    q = select(Reclamation).where(s.filtre_dossiers()).order_by(Reclamation.date_premiere_reception.desc())
    q = _filtres(q, filtres or {})
    rows = list((await db.scalars(q.limit(5000))).all())
    ids = [r.id for r in rows]
    operations = list((await db.scalars(select(ReclamationOperation).where(
        ReclamationOperation.reclamation_id.in_(ids)).order_by(
        ReclamationOperation.reclamation_id, ReclamationOperation.ordre)))) if ids else []
    resumes: dict[uuid.UUID, list] = {}
    for o in operations:
        a = resumes.setdefault(o.reclamation_id, [0, ZERO])
        a[0] += 1
        a[1] += o.montant or ZERO

    wb = Workbook()
    ws = wb.active
    ws.title = "Réclamations"
    ws.append(["Référence", "Date réclamation", "Réception banque", "Client", "Racine", "Agence", "Canal",
               "Type", "Motif", "Sous-motif", "Objet", "Service concerné", "Service de traitement",
               "Priorité", "Étape", "Statut", "Nb opérations", f"Montant total ({C.DEVISE})", "Échéance",
               "Clôture", "Résultat"])
    for r in rows:
        nb, total = resumes.get(r.id, (0, ZERO))
        ws.append([
            r.reference, iso(r.date_reclamation), iso(r.date_premiere_reception), r.client_nom, r.client_racine,
            (ctx.agence(r.client_agence_id) or {}).get("libelle"), ctx.lib(r.canal_id), ctx.lib(r.type_id),
            libelle_motif(ctx, r), libelle_sous_motif(ctx, r), r.objet,
            (ctx.unite(r.unite_concernee_id) or {}).get("libelle"),
            (ctx.unite(r.unite_traitement_id) or {}).get("libelle"), C.PRIORITE_LIBELLES.get(r.priorite),
            C.ETAPE_LIBELLES.get(r.etape), C.STATUT_LIBELLES.get(r.statut), nb, float(total) if nb else None,
            iso(r.echeance), iso(r.date_cloture), C.RESULTAT_LIBELLES.get(r.resultat or ""),
        ])
    references = {r.id: r.reference for r in rows}
    wo = wb.create_sheet("Opérations")
    wo.append(["Réclamation", "N°", "Référence de l'opération", "Montant", "Devise"])
    for o in operations:
        wo.append([references.get(o.reclamation_id), o.ordre, o.reference,
                   float(o.montant) if o.montant is not None else None, o.devise])
    for feuille in (ws, wo):
        for c in feuille[1]:
            c.font = Font(bold=True)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


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
