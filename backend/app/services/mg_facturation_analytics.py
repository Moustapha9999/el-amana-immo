"""Gestion des factures — tableau de bord 360°, alertes, échéances, analyses, rapports.

Aucune statistique stockée : tout est recalculé depuis les factures (origine FACTURATION).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select

from app.models.auth import Agence, User
from app.models.mg_ops import MgPointFacturation
from app.models.organisation import Fournisseur
from app.services.mg_facturation_service import (
    MOIS_COURTS,
    MOIS_LABELS,
    PERIODICITES_POINT,
    STATUT_LABELS,
    STATUT_PAIEMENT_LABELS,
    STATUTS_COMPTES,
    STATUTS_OUVERTS,
    TYPE_POINT_LABELS,
    TYPES_FACTURE,
    MgFacturationService,
    libelle_periode,
    tranche_echeance,
    variation_pct,
)
from app.services.reporting_export import build_styled_pdf, build_styled_workbook, export_now

LIEN_FACTURE = "/contrats-echeances/factures/liste?facture={id}"
LIEN_POINT = "/contrats-echeances/factures/points?point={id}"

FILTRES_DASHBOARD = ("agence_id", "point_id", "fournisseur_id", "type_point", "type_facture", "statut")
NIVEAUX = {"critique": 0, "attention": 1, "info": 2}


def _montant(r: dict) -> float:
    return float(r.get("montant_ttc") or 0)


def _grouper(rows: list[dict], key, label) -> list[dict]:
    acc: dict = {}
    for r in rows:
        k = key(r)
        if k is None:
            continue
        item = acc.setdefault(k, {"id": k, "label": label(r), "montant": 0.0, "nb": 0, "reste": 0.0})
        item["montant"] += _montant(r)
        item["nb"] += 1
        if r["statut"] in STATUTS_OUVERTS:
            item["reste"] += float(r.get("reste") or 0)
    return sorted(acc.values(), key=lambda x: -x["montant"])


def mois_attendus(debut: date, today: date, pas: int, delai_jours: int, horizon_mois: int = 12) -> list[tuple[int, int]]:
    """Périodes (année, mois) pour lesquelles une facture devrait déjà être reçue."""
    if pas <= 0:
        return []
    start = date(debut.year, debut.month, 1)
    limite = date(today.year, today.month, 1)
    plancher = limite.year * 12 + limite.month - 1 - horizon_mois
    out: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) < (limite.year, limite.month):
        fin_mois = date(y, m, calendar.monthrange(y, m)[1])
        if fin_mois + timedelta(days=delai_jours) < today and y * 12 + m - 1 >= plancher:
            out.append((y, m))
        total = y * 12 + (m - 1) + pas
        y, m = total // 12, total % 12 + 1
    return out


def periode_couverte(factures: set[int], annee: int, mois: int, pas: int) -> bool:
    """Une facture du point couvre la période (tolérance : fenêtre de la périodicité)."""
    cle = annee * 12 + mois - 1
    return any((cle - k) in factures for k in range(max(pas, 1)))


def detecter_hausse(montant: float, historique: list[float], seuil_pct: int) -> float | None:
    """% au-dessus de la moyenne des 6 dernières factures si supérieur au seuil, sinon None."""
    valeurs = [v for v in historique[:6] if v > 0]
    if len(valeurs) < 2 or montant <= 0:
        return None
    moyenne = sum(valeurs) / len(valeurs)
    pct = (montant - moyenne) / moyenne * 100
    return round(pct, 1) if pct >= seuil_pct else None


class MgFacturationAnalytics:
    def __init__(self, svc: MgFacturationService):
        self.svc = svc
        self.db = svc.db

    @staticmethod
    def _base_filtres(filtres: dict) -> dict:
        return {k: filtres[k] for k in FILTRES_DASHBOARD if filtres.get(k)}

    async def _rows_annee(self, annee: int, base: dict) -> list[dict]:
        rows = await self.svc.fetch_rows({**base, "annee": annee, "inclure_historique": True})
        return [r for r in rows if r["statut"] in STATUTS_COMPTES]

    def _evolution(self, rows: list[dict], rows_n1: list[dict]) -> list[dict]:
        out = []
        for m in range(1, 13):
            courant = [r for r in rows if r["mois"] == m]
            precedent = [r for r in rows_n1 if r["mois"] == m]
            out.append(
                {
                    "mois": m,
                    "label": MOIS_COURTS[m - 1],
                    "montant": round(sum(_montant(r) for r in courant), 2),
                    "nb": len(courant),
                    "paye": round(sum(float(r["montant_paye"] or 0) for r in courant), 2),
                    "n1": round(sum(_montant(r) for r in precedent), 2),
                }
            )
        return out

    # ——— Tableau de bord 360° ———

    async def dashboard(self, filtres: dict) -> dict:
        today = date.today()
        annee = int(filtres.get("annee") or today.year)
        mois = int(filtres["mois"]) if filtres.get("mois") else None
        base = self._base_filtres(filtres)
        rows_annee = await self._rows_annee(annee, base)
        rows_n1 = await self._rows_annee(annee - 1, base)
        if filtres.get("date_from") or filtres.get("date_to"):
            df, dt = filtres.get("date_from"), filtres.get("date_to")
            rows_annee = [
                r for r in rows_annee
                if (not df or r["date_facture"] >= df.isoformat()) and (not dt or r["date_facture"] <= dt.isoformat())
            ]
        periode = [r for r in rows_annee if not mois or r["mois"] == mois]
        if mois:
            reference = [r for r in rows_n1 if r["mois"] == mois]
        elif annee == today.year:
            reference = [r for r in rows_n1 if (r["mois"] or 0) <= today.month]
        else:
            reference = rows_n1

        ouvertes = await self.svc.fetch_rows({**base, "statut": ",".join(sorted(STATUTS_OUVERTS))})
        ouvertes = [r for r in ouvertes if r["statut_paiement"] != "PAYEE"]
        buckets = {k: {"nb": 0, "montant": 0.0} for k in ("retard", "j7", "j30", "plus30")}
        sans_echeance = {"nb": 0, "montant": 0.0}
        for r in ouvertes:
            if r["jours_echeance"] is None:
                sans_echeance["nb"] += 1
                sans_echeance["montant"] += float(r["reste"] or 0)
                continue
            b = buckets[tranche_echeance(r["jours_echeance"])]
            b["nb"] += 1
            b["montant"] += float(r["reste"] or 0)

        total = sum(_montant(r) for r in periode)
        total_ref = sum(_montant(r) for r in reference)
        par_statut: dict[str, dict] = {}
        tous = await self.svc.fetch_rows({**base, "annee": annee, "inclure_historique": True})
        for r in tous:
            if mois and r["mois"] != mois:
                continue
            key = r["statut_affiche"]
            item = par_statut.setdefault(key, {"code": key, "nb": 0, "montant": 0.0})
            item["nb"] += 1
            item["montant"] += _montant(r)
        libelles = {**STATUT_LABELS, **STATUT_PAIEMENT_LABELS, "EN_RETARD": "En retard"}
        for item in par_statut.values():
            item["label"] = libelles.get(item["code"], item["code"])

        alertes = await self.alertes(base)
        return {
            "annee": annee,
            "mois": mois,
            "periode_label": libelle_periode(annee, mois),
            "kpis": {
                "nb_factures": len(periode),
                "total": round(total, 2),
                "total_reference": round(total_ref, 2),
                "variation_pct": variation_pct(total, total_ref) if total_ref else None,
                "paye": round(sum(float(r["montant_paye"] or 0) for r in periode), 2),
                "a_payer": round(sum(float(r["reste"] or 0) for r in ouvertes), 2),
                "nb_a_payer": len(ouvertes),
                "en_retard": buckets["retard"]["nb"],
                "montant_retard": round(buckets["retard"]["montant"], 2),
                "a_controler": sum(1 for r in tous if r["statut"] in {"RECUE", "A_CONTROLER"}),
                "moyenne_mensuelle": round(total / (1 if mois else max(1, len({r["mois"] for r in periode if r["mois"]}))), 2),
                "nb_alertes": len(alertes["items"]),
            },
            "monthly_evolution": self._evolution(rows_annee, rows_n1),
            "by_agency": _grouper(periode, lambda r: r["agence_id"], lambda r: r["agence"] or "—")[:15],
            "by_pdv": _grouper(
                [r for r in periode if r["type_point"] == "PDV"], lambda r: r["point_facturation_id"], lambda r: r["point_nom"]
            )[:15],
            "by_supplier": _grouper(periode, lambda r: r["fournisseur_id"], lambda r: r["fournisseur"] or "—")[:15],
            "by_type": [
                {**g, "label": dict(TYPES_FACTURE).get(g["id"], g["id"])}
                for g in _grouper(periode, lambda r: r["type_facture"] or "AUTRE", lambda r: r["type_facture"] or "AUTRE")
            ],
            "by_type_point": [
                {**g, "label": TYPE_POINT_LABELS.get(g["id"], g["id"])}
                for g in _grouper(periode, lambda r: r["type_point"] or "SANS_POINT", lambda r: r["type_point"] or "Sans point")
            ],
            "by_status": sorted(par_statut.values(), key=lambda x: -x["nb"]),
            "echeances": {**{k: {"nb": v["nb"], "montant": round(v["montant"], 2)} for k, v in buckets.items()},
                          "sans_echeance": {"nb": sans_echeance["nb"], "montant": round(sans_echeance["montant"], 2)}},
            "top_points": _grouper(
                [r for r in periode if r["point_facturation_id"]], lambda r: r["point_facturation_id"], lambda r: r["point_nom"]
            )[:8],
            "recentes": (await self.svc.fetch_rows({**base, "inclure_historique": True}, limit=8)),
            "alerts": alertes["items"][:8],
            "alerts_count": alertes["compteurs"],
        }

    # ——— Alertes ———

    async def alertes(self, filtres: dict | None = None) -> dict:
        today = date.today()
        seuils = await self.svc.seuils()
        base = self._base_filtres(filtres or {})
        items: list[dict] = []

        historique = await self.svc.fetch_rows(
            {**{k: v for k, v in base.items() if k != "statut"}, "date_from": today - timedelta(days=760), "inclure_historique": True}
        )
        vivantes = [r for r in historique if r["statut"] != "ANNULEE"]

        for r in vivantes:
            if r["etat_echeance"] == "EN_RETARD":
                items.append(self._alerte_facture(
                    r, "retard", "critique", "Facture en retard",
                    f"Échéance dépassée de {abs(r['jours_echeance'])} j — reste {r['reste']:.2f} {r['devise']}",
                ))
            elif r["etat_echeance"] == "PROCHE":
                items.append(self._alerte_facture(
                    r, "proche", "attention", "Échéance proche",
                    "Échéance aujourd'hui" if r["jours_echeance"] == 0 else f"Échéance dans {r['jours_echeance']} j",
                ))

        par_point: dict[str, list[dict]] = defaultdict(list)
        for r in vivantes:
            if r["point_facturation_id"] and r["statut"] in STATUTS_COMPTES:
                par_point[r["point_facturation_id"]].append(r)
        limite_hausse = today - timedelta(days=95)
        for rows in par_point.values():
            rows.sort(key=lambda x: ((x["annee"] or 0) * 100 + (x["mois"] or 0), x["date_facture"]), reverse=True)
            for idx, r in enumerate(rows):
                if r["date_facture"] < limite_hausse.isoformat():
                    break
                pct = detecter_hausse(_montant(r), [_montant(x) for x in rows[idx + 1: idx + 7]], seuils["seuil_hausse_pct"])
                if pct is not None:
                    items.append(self._alerte_facture(
                        r, "hausse", "attention", "Hausse importante",
                        f"+{pct} % par rapport à la moyenne des dernières factures du point",
                    ))

        groupes: dict[tuple, list[dict]] = defaultdict(list)
        for r in vivantes:
            if r["point_facturation_id"] and r["annee"] and r["mois"]:
                groupes[(r["point_facturation_id"], r["annee"], r["mois"])].append(r)
        for (_pid, annee, mois), rows in groupes.items():
            if len(rows) > 1:
                r = rows[0]
                items.append(self._alerte_facture(
                    r, "doublon", "attention", "Doublon possible",
                    f"{len(rows)} factures pour {r['point_nom']} sur {libelle_periode(annee, mois)} : "
                    + ", ".join(x["reference"] for x in rows),
                ))

        items.extend(await self._manquantes(base, vivantes, seuils["delai_reception_jours"], today))
        items.sort(key=lambda a: (NIVEAUX.get(a["niveau"], 9), a.get("date") or ""))
        compteurs = {t: 0 for t in ("manquante", "proche", "retard", "hausse", "doublon")}
        for a in items:
            compteurs[a["type"]] = compteurs.get(a["type"], 0) + 1
        return {"items": items, "compteurs": compteurs, "seuils": seuils}

    def _alerte_facture(self, r: dict, type_: str, niveau: str, titre: str, message: str) -> dict:
        return {
            "type": type_,
            "niveau": niveau,
            "titre": titre,
            "message": message,
            "facture_id": r["id"],
            "reference": r["reference"],
            "point_id": r["point_facturation_id"],
            "point_nom": r["point_nom"],
            "agence": r["agence"],
            "fournisseur": r["fournisseur"],
            "periode_label": r["periode_label"],
            "montant": r["montant_a_payer"],
            "date": r["date_echeance"] or r["date_facture"],
            "lien": LIEN_FACTURE.format(id=r["id"]),
        }

    async def _manquantes(self, base: dict, vivantes: list[dict], delai: int, today: date) -> list[dict]:
        P = MgPointFacturation
        stmt = (
            select(P, Fournisseur.raison_sociale, Agence.libelle)
            .outerjoin(Fournisseur, Fournisseur.id == P.fournisseur_id)
            .outerjoin(Agence, Agence.id == P.agence_id)
            .where(P.deleted_at.is_(None), P.statut == "ACTIF")
        )
        if self.svc.scope_agence:
            stmt = stmt.where(P.agence_id == self.svc.scope_agence)
        if base.get("agence_id"):
            stmt = stmt.where(P.agence_id == base["agence_id"])
        if base.get("fournisseur_id"):
            stmt = stmt.where(P.fournisseur_id == base["fournisseur_id"])
        if base.get("point_id"):
            stmt = stmt.where(P.id == base["point_id"])
        if base.get("type_point"):
            stmt = stmt.where(P.type_point == str(base["type_point"]).upper())
        points = (await self.db.execute(stmt)).all()
        periodes: dict[str, set[int]] = defaultdict(set)
        for r in vivantes:
            if r["point_facturation_id"] and r["annee"] and r["mois"]:
                periodes[r["point_facturation_id"]].add(r["annee"] * 12 + r["mois"] - 1)
        out = []
        for p, fournisseur, agence in points:
            pas = PERIODICITES_POINT.get(p.periodicite, 1)
            debut = p.date_debut or (p.created_at.date() if p.created_at else today)
            if p.date_fin and p.date_fin < today:
                continue
            manquants = [
                (y, m) for (y, m) in mois_attendus(debut, today, pas, delai)
                if not periode_couverte(periodes.get(str(p.id), set()), y, m, pas)
            ]
            if not manquants:
                continue
            labels = ", ".join(libelle_periode(y, m) for y, m in manquants[-6:])
            if len(manquants) > 6:
                labels = f"… {labels}"
            out.append(
                {
                    "type": "manquante",
                    "niveau": "critique" if len(manquants) >= 2 else "attention",
                    "titre": "Facture manquante" if len(manquants) == 1 else f"{len(manquants)} factures manquantes",
                    "message": f"Aucune facture reçue pour : {labels}",
                    "facture_id": None,
                    "reference": p.code,
                    "point_id": str(p.id),
                    "point_nom": p.nom,
                    "agence": agence,
                    "fournisseur": fournisseur,
                    "periode_label": libelle_periode(*manquants[-1]),
                    "periodes": [{"annee": y, "mois": m} for y, m in manquants],
                    "montant": None,
                    "date": date(manquants[-1][0], manquants[-1][1], 1).isoformat(),
                    "lien": LIEN_POINT.format(id=p.id),
                }
            )
        return out

    # ——— Échéances ———

    async def echeances(self, filtres: dict) -> dict:
        base = self._base_filtres(filtres)
        base.pop("statut", None)
        rows = await self.svc.fetch_rows(
            {**base, "statut": ",".join(sorted(STATUTS_OUVERTS)), "echeance": filtres.get("echeance")},
            order=None,
        )
        rows = [r for r in rows if r["statut_paiement"] != "PAYEE" and r["date_echeance"]]
        rows.sort(key=lambda r: r["date_echeance"])
        buckets = {k: {"nb": 0, "montant": 0.0} for k in ("retard", "j7", "j30", "plus30")}
        for r in rows:
            b = buckets[tranche_echeance(r["jours_echeance"])]
            b["nb"] += 1
            b["montant"] = round(b["montant"] + float(r["reste"] or 0), 2)
            r["tranche"] = tranche_echeance(r["jours_echeance"])
        return {"items": rows, "buckets": buckets}

    # ——— Analyses ———

    async def monthly(self, filtres: dict) -> dict:
        annee = int(filtres.get("annee") or date.today().year)
        base = self._base_filtres(filtres)
        rows = await self._rows_annee(annee, base)
        rows_n1 = await self._rows_annee(annee - 1, base)
        evolution = self._evolution(rows, rows_n1)
        for e in evolution:
            e["variation_pct"] = variation_pct(e["montant"], e["n1"]) if e["n1"] else None
        total = sum(e["montant"] for e in evolution)
        return {"annee": annee, "items": evolution, "total": round(total, 2), "total_n1": round(sum(e["n1"] for e in evolution), 2)}

    async def annual(self, filtres: dict) -> dict:
        base = self._base_filtres(filtres)
        rows = await self.svc.fetch_rows({**base, "inclure_historique": True})
        par_annee: dict[int, dict] = {}
        for r in rows:
            if r["statut"] not in STATUTS_COMPTES or not r["annee"]:
                continue
            item = par_annee.setdefault(r["annee"], {"annee": r["annee"], "montant": 0.0, "nb": 0, "paye": 0.0})
            item["montant"] += _montant(r)
            item["nb"] += 1
            item["paye"] += float(r["montant_paye"] or 0)
        items = sorted(par_annee.values(), key=lambda x: x["annee"])
        for idx, item in enumerate(items):
            prev = items[idx - 1]["montant"] if idx else None
            item["variation_pct"] = variation_pct(item["montant"], prev) if prev else None
            item["moyenne_mensuelle"] = round(item["montant"] / 12, 2)
        return {"items": items}

    async def _par_dimension(self, filtres: dict, key, label, extra=None) -> dict:
        annee = int(filtres.get("annee") or date.today().year)
        base = self._base_filtres(filtres)
        rows = await self._rows_annee(annee, base)
        rows_n1 = await self._rows_annee(annee - 1, base)
        if extra:
            rows = [r for r in rows if extra(r)]
            rows_n1 = [r for r in rows_n1 if extra(r)]
        courant = {g["id"]: g for g in _grouper(rows, key, label)}
        precedent = {g["id"]: g for g in _grouper(rows_n1, key, label)}
        items = []
        for gid in set(courant) | set(precedent):
            c = courant.get(gid) or {**precedent[gid], "montant": 0.0, "nb": 0, "reste": 0.0}
            n1 = precedent.get(gid, {}).get("montant", 0.0)
            mensuel = [0.0] * 12
            for r in rows:
                if key(r) == gid and r["mois"]:
                    mensuel[r["mois"] - 1] += _montant(r)
            mois_actifs = sum(1 for v in mensuel if v)
            items.append(
                {
                    **c,
                    "montant": round(c["montant"], 2),
                    "n1": round(n1, 2),
                    "variation_pct": variation_pct(c["montant"], n1) if n1 else None,
                    "moyenne_mensuelle": round(c["montant"] / mois_actifs, 2) if mois_actifs else 0.0,
                    "mensuel": [round(v, 2) for v in mensuel],
                }
            )
        items.sort(key=lambda x: -x["montant"])
        total = sum(i["montant"] for i in items)
        for i in items:
            i["part_pct"] = round(i["montant"] / total * 100, 1) if total else 0.0
        return {"annee": annee, "items": items, "total": round(total, 2)}

    async def agencies(self, filtres: dict) -> dict:
        return await self._par_dimension(filtres, lambda r: r["agence_id"], lambda r: r["agence"] or "—")

    async def pdv(self, filtres: dict) -> dict:
        return await self._par_dimension(
            filtres, lambda r: r["point_facturation_id"], lambda r: r["point_nom"], extra=lambda r: r["type_point"] == "PDV"
        )

    async def suppliers(self, filtres: dict) -> dict:
        return await self._par_dimension(filtres, lambda r: r["fournisseur_id"], lambda r: r["fournisseur"] or "—")

    async def points(self, filtres: dict) -> dict:
        return await self._par_dimension(
            filtres, lambda r: r["point_facturation_id"], lambda r: f"{r['point_nom']} ({r['point_code']})"
        )

    async def comparison(self, filtres: dict) -> dict:
        today = date.today()
        annee = int(filtres.get("annee") or today.year)
        reference = int(filtres.get("annee_reference") or annee - 1)
        base = self._base_filtres(filtres)
        rows = await self._rows_annee(annee, base)
        rows_ref = await self._rows_annee(reference, base)
        mois_max = today.month if annee == today.year else 12
        items = []
        for m in range(1, 13):
            a = sum(_montant(r) for r in rows if r["mois"] == m)
            b = sum(_montant(r) for r in rows_ref if r["mois"] == m)
            items.append(
                {
                    "mois": m, "label": MOIS_LABELS[m - 1], "montant": round(a, 2), "reference": round(b, 2),
                    "ecart": round(a - b, 2), "variation_pct": variation_pct(a, b) if b else None,
                }
            )
        cumul = sum(i["montant"] for i in items[:mois_max])
        cumul_ref = sum(i["reference"] for i in items[:mois_max])
        return {
            "annee": annee,
            "annee_reference": reference,
            "items": items,
            "cumul": round(cumul, 2),
            "cumul_reference": round(cumul_ref, 2),
            "cumul_mois": mois_max,
            "variation_pct": variation_pct(cumul, cumul_ref) if cumul_ref else None,
            "agences": (await self.agencies({**filtres, "annee": annee}))["items"][:20],
        }

    # ——— Rapports ———

    RAPPORTS = {
        "mensuel": "Rapport mensuel des factures",
        "annuel": "Rapport annuel des factures",
        "agences": "Factures par agence",
        "pdv": "Factures des PDV Amanty",
        "fournisseurs": "Factures par fournisseur",
        "factures": "Registre des factures",
        "retards": "Factures en retard",
        "paiements": "Paiements de factures",
        "manquantes": "Factures manquantes",
    }

    async def rapport(self, key: str, filtres: dict) -> dict:
        if key not in self.RAPPORTS:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rapport inconnu")
        today = date.today()
        annee = int(filtres.get("annee") or today.year)
        mois = int(filtres["mois"]) if filtres.get("mois") else None
        title = self.RAPPORTS[key]
        entetes_factures = [
            "Référence", "N° fournisseur", "Période", "Fournisseur", "Agence", "Point", "Réf. fournisseur",
            "Date facture", "Échéance", "Montant TTC", "À payer", "Payé", "Reste", "Statut",
        ]

        def ligne_facture(r: dict) -> list:
            statut = STATUT_PAIEMENT_LABELS.get(r["statut_paiement"] or "", None) or STATUT_LABELS.get(r["statut"], r["statut"])
            if r["etat_echeance"] == "EN_RETARD":
                statut = f"{statut} (en retard)"
            return [
                r["reference"], r["numero_fournisseur"] or "", r["periode_label"] or "", r["fournisseur"] or "",
                r["agence"] or "", r["point_nom"] or "", r["reference_fournisseur"] or "",
                _fr(r["date_facture"]), _fr(r["date_echeance"]), float(r["montant_ttc"] or 0),
                float(r["montant_a_payer"] or 0), float(r["montant_paye"] or 0), float(r["reste"] or 0), statut,
            ]

        base = self._base_filtres(filtres)
        if key == "mensuel":
            mois = mois or today.month
            rows = await self.svc.fetch_rows({**base, "annee": annee, "mois": mois, "inclure_historique": True})
            rows = [r for r in rows if r["statut"] != "ANNULEE"]
            return {"title": f"{title} — {libelle_periode(annee, mois)}", "headers": entetes_factures,
                    "rows": [ligne_facture(r) for r in rows] + _total_row(rows, len(entetes_factures))}
        if key == "factures":
            rows = await self.svc.fetch_rows({**filtres, "inclure_historique": True})
            return {"title": title, "headers": entetes_factures, "rows": [ligne_facture(r) for r in rows]}
        if key == "retards":
            rows = await self.svc.fetch_rows({**base, "vue": "retard"}, order=None)
            rows.sort(key=lambda r: r["date_echeance"] or "")
            return {"title": title, "headers": entetes_factures + ["Jours de retard"],
                    "rows": [ligne_facture(r) + [abs(r["jours_echeance"] or 0)] for r in rows]}
        if key == "annuel":
            data = await self.monthly({**filtres, "annee": annee})
            rows = [[e["label"], e["nb"], e["montant"], e["paye"], e["n1"],
                     f"{e['variation_pct']} %" if e["variation_pct"] is not None else "—"] for e in data["items"]]
            rows.append(["Total", sum(e["nb"] for e in data["items"]), data["total"],
                         round(sum(e["paye"] for e in data["items"]), 2), data["total_n1"],
                         f"{variation_pct(data['total'], data['total_n1'])} %" if data["total_n1"] else "—"])
            return {"title": f"{title} {annee}", "headers": ["Mois", "Nb factures", f"Montant {annee}", "Payé",
                                                             f"Montant {annee - 1}", "Variation"], "rows": rows}
        if key in {"agences", "pdv", "fournisseurs"}:
            fn = {"agences": self.agencies, "pdv": self.pdv, "fournisseurs": self.suppliers}[key]
            data = await fn({**filtres, "annee": annee})
            libelle = {"agences": "Agence", "pdv": "PDV", "fournisseurs": "Fournisseur"}[key]
            rows = [[i["label"], i["nb"], i["montant"], i["moyenne_mensuelle"], i["n1"],
                     f"{i['variation_pct']} %" if i["variation_pct"] is not None else "—", f"{i['part_pct']} %",
                     i["reste"]] for i in data["items"]]
            return {"title": f"{title} — {annee}", "headers": [libelle, "Nb factures", f"Montant {annee}",
                                                                "Moyenne mensuelle", f"Montant {annee - 1}", "Variation",
                                                                "Part", "Reste à payer"], "rows": rows}
        if key == "paiements":
            rows = await self.svc.list_paiements({**filtres, "annee": annee if not filtres.get("date_from") else None})
            return {"title": f"{title} — {annee}", "headers": ["Référence", "Date", "Facture", "Période", "Fournisseur",
                                                                "Agence", "Point", "Mode", "Réf. paiement", "Montant", "Statut"],
                    "rows": [[p["reference"], _fr(p["date_paiement"]), p["facture_reference"], p["periode_label"] or "",
                              p["fournisseur"] or "", p["agence"] or "", p["point_nom"] or "", p["mode_paiement"] or "",
                              p["reference_paiement"] or "", float(p["montant"] or 0),
                              "Annulé" if p["statut"] == "ANNULE" else "Payé"] for p in rows]}
        alertes = await self.alertes(base)
        rows = [a for a in alertes["items"] if a["type"] == "manquante"]
        return {"title": title, "headers": ["Point", "Code", "Agence", "Fournisseur", "Nb périodes", "Périodes manquantes"],
                "rows": [[a["point_nom"], a["reference"], a["agence"] or "", a["fournisseur"] or "", len(a["periodes"]),
                          ", ".join(libelle_periode(p["annee"], p["mois"]) for p in a["periodes"])] for a in rows]}

    async def export(self, user: User, key: str, fmt: str, filtres: dict):
        data = await self.rapport(key, filtres)
        headers, rows, title = data["headers"], data["rows"], data["title"]
        if fmt == "json":
            return {"key": key, "title": title, "headers": headers, "rows": rows, "count": len(rows)}
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aucune donnée pour ce rapport")
        await self.svc._audit(user, "factures.export", None, after={"rapport": key, "format": fmt,
                                                                   "filtres": {k: str(v) for k, v in filtres.items() if v}},
                              entity="rapport")
        await self.db.commit()
        when = export_now()
        full_title = f"BEA DIGITAL — {title}"
        subtitle = f"Généré par {user.full_name or user.email}"
        filename = f"factures-{key}"
        if fmt == "pdf":
            return Response(
                content=build_styled_pdf(report_title=full_title, headers=headers, rows=rows, subtitle=subtitle,
                                         exported_at=when, landscape_mode=True),
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
            )
        return Response(
            content=build_styled_workbook(sheet_title="Factures", report_title=full_title, headers=headers, rows=rows,
                                          subtitle=subtitle, exported_at=when),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
        )


def _fr(iso: str | None) -> str:
    if not iso:
        return ""
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def _total_row(rows: list[dict], width: int) -> list[list]:
    if not rows:
        return []
    line: list = ["Total"] + [""] * (width - 1)
    line[9] = round(sum(float(r["montant_ttc"] or 0) for r in rows), 2)
    line[10] = round(sum(float(r["montant_a_payer"] or 0) for r in rows), 2)
    line[11] = round(sum(float(r["montant_paye"] or 0) for r in rows), 2)
    line[12] = round(sum(float(r["reste"] or 0) for r in rows), 2)
    return [line]
