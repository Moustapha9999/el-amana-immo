"""Tableau de bord 360° et export Excel — toujours filtrés par le périmètre de l'utilisateur."""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reclamation
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.dossiers import Contexte, _filtres, ligne
from app.services.reclamations.outils import iso, maintenant


async def tableau_de_bord(db: AsyncSession, s: ReclamationsScope, filtres: dict | None = None) -> dict:
    ctx = await Contexte.charger(db)
    q = select(Reclamation).where(s.filtre_dossiers())
    q = _filtres(q, filtres or {})
    rows = list((await db.scalars(q)).all())
    now = maintenant()
    ouvertes = [r for r in rows if r.statut not in C.STATUTS_TERMINAUX and not r.archivee_le]
    par_groupe: dict[str, int] = {g: 0 for g in C.GROUPE_LIBELLES}
    par_etape: dict[str, int] = {e: 0 for e in C.ETAPE_LIBELLES}
    par_priorite: dict[str, int] = {p: 0 for p in C.PRIORITE_LIBELLES}
    for r in rows:
        par_groupe[C.STATUT_GROUPES.get(r.statut, "")] = par_groupe.get(C.STATUT_GROUPES.get(r.statut, ""), 0) + 1
        par_etape[r.etape] = par_etape.get(r.etape, 0) + 1
        par_priorite[r.priorite] = par_priorite.get(r.priorite, 0) + 1
    retards = [r for r in ouvertes if r.echeance and r.echeance < now]
    sans_echeance = [r for r in ouvertes if r.echeance is None]
    recents = sorted(rows, key=lambda r: r.updated_at or r.created_at or now, reverse=True)[:8]

    async def _repartition(colonne, lib):
        q2 = select(colonne, func.count()).where(s.filtre_dossiers(), colonne.is_not(None))
        q2 = _filtres(q2, filtres or {}).group_by(colonne)
        out = []
        for i, n in (await db.execute(q2)).all():
            out.append({"id": str(i), "libelle": lib(i), "n": n})
        return sorted(out, key=lambda x: -x["n"])

    depuis = now - timedelta(days=30)
    volume_30 = sum(1 for r in rows if r.date_premiere_reception >= depuis)
    cloturees_30 = sum(1 for r in rows if r.date_cloture and r.date_cloture >= depuis)
    return {
        "total": len(rows),
        "ouvertes": len(ouvertes),
        "retards": len(retards),
        "sans_echeance": len(sans_echeance),
        "volume_30j": volume_30,
        "cloturees_30j": cloturees_30,
        "groupes": [{"code": k, "libelle": C.GROUPE_LIBELLES[k], "n": v} for k, v in par_groupe.items()],
        "etapes": [{"code": k, "libelle": C.ETAPE_LIBELLES[k], "n": v} for k, v in par_etape.items()],
        "priorites": [{"code": k, "libelle": C.PRIORITE_LIBELLES[k], "n": v} for k, v in par_priorite.items()],
        "types": await _repartition(Reclamation.type_id, ctx.lib),
        "canaux": await _repartition(Reclamation.canal_id, ctx.lib),
        "unites_reception": await _repartition(
            Reclamation.unite_reception_id, lambda i: (ctx.unite(i) or {}).get("libelle")),
        "unites_traitement": await _repartition(
            Reclamation.unite_traitement_id, lambda i: (ctx.unite(i) or {}).get("libelle")),
        "recents": [ligne(r, ctx) for r in recents],
        "dossiers_retard": [ligne(r, ctx) for r in retards[:15]],
    }


async def exporter(db: AsyncSession, s: ReclamationsScope, filtres: dict | None = None) -> bytes:
    s.exiger("reclamations.reporting.export", "reclamations.reporting.view")
    ctx = await Contexte.charger(db)
    q = select(Reclamation).where(s.filtre_dossiers()).order_by(Reclamation.date_premiere_reception.desc())
    q = _filtres(q, filtres or {})
    rows = list((await db.scalars(q.limit(5000))).all())
    wb = Workbook()
    ws = wb.active
    ws.title = "Réclamations"
    entetes = ["Référence", "Objet", "Client", "Racine", "Canal", "Type", "Motif", "Priorité",
               "Statut", "Étape", "Unité réception", "Unité traitement", "Première réception",
               "Réception SR", "Échéance", "Clôture", "Résultat"]
    ws.append(entetes)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([
            r.reference, r.objet, r.client_nom, r.client_racine, ctx.lib(r.canal_id), ctx.lib(r.type_id),
            ctx.lib(r.motif_id), C.PRIORITE_LIBELLES.get(r.priorite), C.STATUT_LIBELLES.get(r.statut),
            C.ETAPE_LIBELLES.get(r.etape), (ctx.unite(r.unite_reception_id) or {}).get("libelle"),
            (ctx.unite(r.unite_traitement_id) or {}).get("libelle"), iso(r.date_premiere_reception),
            iso(r.date_reception_sr), iso(r.echeance), iso(r.date_cloture),
            C.RESULTAT_LIBELLES.get(r.resultat or ""),
        ])
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
    colonnes = {e: [] for e in C.ETAPE_LIBELLES}
    for r in rows:
        colonnes.setdefault(r.etape, []).append(ligne(r, ctx))
    return {
        "colonnes": [{"etape": e, "libelle": C.ETAPE_LIBELLES[e], "items": colonnes.get(e, [])}
                     for e in C.ETAPE_LIBELLES],
        "total": len(rows),
    }
