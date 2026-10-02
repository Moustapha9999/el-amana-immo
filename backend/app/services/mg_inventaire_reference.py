"""Rapprochement d'un inventaire sur une référence externe (inventaire bancaire).

Le classeur de référence (onglets Inventaire_Reference, Mouvements_A_Appliquer, Ecarts_Banque,
Controle, Meta) devient la vérité de l'inventaire : physique, théorique et stock retenu par ligne.
Stock initial / entrées / sorties sont conservés en ``donnees_source`` pour traçabilité et ne
sont jamais rejoués en mouvements. Seuls les ajustements du plan seront générés à l'étape
« Appliquer les ajustements », et uniquement s'ils correspondent exactement au plan.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Request, status
from sqlalchemy import select

from app.core.exceptions import AppError
from app.models.mg_stock import MgArticle, MgInventaireLigne
from app.schemas.nombres import as_qty
from app.services.mg_inventaire_import import InventaireImportService, _quantite, normaliser
from app.services.mg_inventaire_service import MgInventaireService
from app.services.mg_stock_periodes import nature_ecart

ONGLETS = ("Inventaire_Reference", "Mouvements_A_Appliquer", "Ecarts_Banque", "Controle", "Meta")

COLONNES_REFERENCE = {
    "numero": ("n°", "n"),
    "fiche": ("fiche",),
    "code": ("ref.", "ref", "reference", "code"),
    "designation": ("article (libelle de la fiche)", "article", "designation"),
    "categorie": ("categorie", "famille"),
    "statut_agence": ("statut agence",),
    "stock_initial": ("stock initial",),
    "entrees": ("entrees",),
    "sorties": ("sorties",),
    "stock_final_theorique": ("stock final theorique",),
    "verifie": ("verifie (ok)", "verifie"),
    "stock_physique": ("stock physique constate", "stock physique"),
    "ecart": ("ecart (physique - theorique)", "ecart"),
    "statut_inventaire": ("statut inventaire",),
    "stock_actuel_agence": ("stock actuel agence",),
    "consommation": ("consommation (sorties)", "consommation"),
    "alerte": ("alerte stock", "alerte"),
    "observations": ("observations", "observation"),
}
COLONNES_PLAN = {
    "code": ("ref.", "ref"),
    "designation": ("article",),
    "stock_bea": ("stock bea actuel",),
    "theorique": ("stock final theorique banque",),
    "cible": ("stock actuel agence banque",),
    "physique": ("stock physique banque",),
    "ajustement": ("ajustement a appliquer",),
    "type": ("type mouvement",),
    "source": ("source",),
}
COLONNES_ECARTS = {
    "code": ("ref.", "ref"),
    "ecart": ("ecart",),
    "statut": ("statut",),
    "decision": ("decision",),
}
CONTROLES = {
    "references bancaires": "references",
    "articles agence actuelle": "agence_actuelle",
    "ancienne agence": "ancienne_agence",
    "erreurs formule banque": "erreurs_formule",
    "stock actuel agence banque": "stock_final",
    "stock physique agence actuelle": "stock_physique",
    "ecart physique non regularise": "ecart_restant",
    "ajustement total vers stock actuel banque": "variation",
    "nombre de mouvements a appliquer": "nb_mouvements",
}


def _table(ws, colonnes: dict[str, tuple[str, ...]]) -> list[dict]:
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    entetes = [normaliser(v) for v in rows[0]]
    idx = {}
    for champ, synonymes in colonnes.items():
        for i, e in enumerate(entetes):
            if e in synonymes and i not in idx.values():
                idx[champ] = i
                break
    out = []
    for r_num, row in enumerate(rows[1:], start=2):
        d = {champ: (row[i] if i < len(row) else None) for champ, i in idx.items()}
        d["_ligne"] = r_num
        out.append(d)
    return out


def _entier(valeur) -> int | None:
    if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
        return None
    try:
        return as_qty(valeur)
    except ValueError:
        return None


def _texte(valeur) -> str | None:
    if valeur is None:
        return None
    s = str(valeur).strip()
    return s or None


class InventaireReferenceService:
    def __init__(self, inventaires: MgInventaireService):
        self.inv = inventaires
        self.db = inventaires.db

    async def analyser(self, inventaire_id, contenu: bytes, nom_fichier: str) -> dict:
        inv = await self.inv.get(inventaire_id)
        wb = InventaireImportService(self.inv)._classeur(contenu)
        manquants = [o for o in ONGLETS if o not in wb.sheetnames]
        if manquants:
            raise AppError(
                "Classeur de référence incomplet : onglet(s) manquant(s) " + ", ".join(manquants) + ".",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="REFERENCE_INVALIDE",
            )
        meta = {
            normaliser(r[0]): r[1]
            for r in wb["Meta"].iter_rows(min_row=2, values_only=True)
            if r and r[0] is not None
        }
        controle = {}
        for r in wb["Controle"].iter_rows(min_row=2, values_only=True):
            cle = CONTROLES.get(normaliser(r[0])) if r and r[0] else None
            if cle:
                controle[cle] = _entier(r[1])
        reference = [r for r in _table(wb["Inventaire_Reference"], COLONNES_REFERENCE) if _texte(r.get("code"))]
        plan = [
            r for r in _table(wb["Mouvements_A_Appliquer"], COLONNES_PLAN)
            if _texte(r.get("code")) and normaliser(r.get("code")) != "total"
        ]
        ecarts = [r for r in _table(wb["Ecarts_Banque"], COLONNES_ECARTS) if _texte(r.get("code"))]

        lignes = {
            art.code: (lg, art)
            for lg, art in (
                await self.db.execute(
                    select(MgInventaireLigne, MgArticle)
                    .join(MgArticle, MgArticle.id == MgInventaireLigne.article_id)
                    .where(MgInventaireLigne.inventaire_id == inv.id)
                )
            ).all()
        }
        anomalies: list[str] = []
        ref_meta = _texte(meta.get("inventaire"))
        if ref_meta and ref_meta != inv.reference:
            anomalies.append(f"Le classeur concerne {ref_meta}, pas {inv.reference}.")

        decisions = {_texte(e["code"]): e for e in ecarts}
        vus: set[str] = set()
        apercu: list[dict] = []
        erreurs_formule = 0
        for r in reference:
            code = _texte(r["code"])
            if code in vus:
                anomalies.append(f"Ligne {r['_ligne']} : référence {code} en doublon.")
                continue
            vus.add(code)
            ancienne = "ancien" in normaliser(r.get("statut_agence"))
            valeurs = {}
            for champ in ("stock_initial", "entrees", "sorties", "stock_final_theorique", "stock_physique",
                          "stock_actuel_agence", "ecart", "consommation"):
                brut = r.get(champ)
                if champ == "ecart":
                    valeurs[champ] = _entier(brut)
                    continue
                q, err = _quantite(brut)
                if err:
                    anomalies.append(f"{code} : {champ.replace('_', ' ')} — {err}.")
                valeurs[champ] = as_qty(q) if q is not None else None
            si, e, s, theo = (valeurs[k] for k in ("stock_initial", "entrees", "sorties", "stock_final_theorique"))
            if None not in (si, e, s, theo) and si + e - s != theo:
                erreurs_formule += 1
                anomalies.append(f"{code} : stock initial + entrées − sorties ≠ stock final théorique.")
            if not ancienne and (valeurs["stock_physique"] is None or valeurs["stock_actuel_agence"] is None):
                anomalies.append(f"{code} : stock physique ou stock actuel agence manquant.")
            couple = lignes.get(code)
            if couple is None:
                anomalies.append(f"{code} : article absent de l'inventaire {inv.reference}.")
                continue
            lg, art = couple
            cible = None if ancienne else valeurs["stock_actuel_agence"]
            ajustement = None if cible is None else cible - as_qty(lg.stock_theorique or 0)
            reste = (
                None if ancienne or valeurs["stock_physique"] is None or cible is None
                else valeurs["stock_physique"] - cible
            )
            apercu.append(
                {
                    "code": code,
                    "designation": _texte(r.get("designation")),
                    "statut_agence": _texte(r.get("statut_agence")),
                    "ancienne_agence": ancienne,
                    "stock_systeme": as_qty(lg.stock_theorique or 0),
                    "stock_actuel_article": as_qty(art.stock_actuel or 0),
                    "theorique_reference": theo,
                    "stock_physique": valeurs["stock_physique"],
                    "stock_cible": cible,
                    "ajustement": ajustement,
                    "ecart_a_regulariser": reste,
                    "_ligne_id": lg.id,
                    "_donnees": {
                        "numero": _entier(r.get("numero")),
                        "fiche": _entier(r.get("fiche")),
                        "designation": _texte(r.get("designation")),
                        "categorie": _texte(r.get("categorie")),
                        "statut_agence": _texte(r.get("statut_agence")),
                        "ancienne_agence": ancienne,
                        "verifie": _texte(r.get("verifie")),
                        "statut_inventaire": _texte(r.get("statut_inventaire")),
                        "alerte": _texte(r.get("alerte")),
                        "observations": _texte(r.get("observations")),
                        "decision": _texte((decisions.get(code) or {}).get("decision")),
                        **{k: valeurs[k] for k in valeurs},
                    },
                }
            )
        absents = sorted(set(lignes) - vus)
        if absents:
            anomalies.append(f"{len(absents)} article(s) de l'inventaire absent(s) du classeur : {', '.join(absents[:15])}.")

        par_code = {a["code"]: a for a in apercu}
        mouvements: dict[str, int] = {}
        source_libelle = None
        for p in plan:
            code = _texte(p["code"])
            qte = _entier(p.get("ajustement"))
            a = par_code.get(code)
            source_libelle = source_libelle or _texte(p.get("source"))
            if normaliser(p.get("type")) not in ("", "ajustement"):
                anomalies.append(f"Plan {code} : type « {p.get('type')} » non autorisé (AJUSTEMENT uniquement).")
            if qte is None or qte == 0:
                anomalies.append(f"Plan {code} : ajustement absent ou nul.")
                continue
            if code in mouvements:
                anomalies.append(f"Plan {code} : ajustement en doublon.")
                continue
            mouvements[code] = qte
            if a is None:
                anomalies.append(f"Plan {code} : article inconnu de la référence.")
                continue
            if a["ancienne_agence"]:
                anomalies.append(f"Plan {code} : article d'ancienne agence — aucun ajustement autorisé.")
                continue
            stock_bea = _entier(p.get("stock_bea"))
            if stock_bea is not None and stock_bea != a["stock_systeme"]:
                anomalies.append(
                    f"Plan {code} : stock BEA du plan {stock_bea} ≠ stock système figé {a['stock_systeme']}."
                )
            if a["stock_actuel_article"] != a["stock_systeme"]:
                anomalies.append(
                    f"{code} : stock actuel {a['stock_actuel_article']} ≠ stock figé {a['stock_systeme']} "
                    "(mouvement saisi depuis la photo)."
                )
            if a["ajustement"] != qte:
                anomalies.append(f"Plan {code} : ajustement {qte:+d} ≠ stock retenu − stock BEA ({a['ajustement']:+d}).")
        hors_plan = [a["code"] for a in apercu if a["ajustement"] and a["code"] not in mouvements]
        if hors_plan:
            anomalies.append("Écart système non couvert par le plan : " + ", ".join(hors_plan[:15]) + ".")

        actuels = [a for a in apercu if not a["ancienne_agence"]]
        calcul = {
            "references": len(apercu),
            "agence_actuelle": len(actuels),
            "ancienne_agence": len(apercu) - len(actuels),
            "erreurs_formule": erreurs_formule,
            "stock_systeme": sum(a["stock_systeme"] for a in actuels),
            "stock_final": sum(a["stock_cible"] or 0 for a in actuels),
            "stock_physique": sum(a["stock_physique"] or 0 for a in actuels),
            "ecart_restant": sum(a["ecart_a_regulariser"] or 0 for a in actuels),
            "variation": sum(mouvements.values()),
            "nb_mouvements": len(mouvements),
        }
        for cle, attendu in controle.items():
            if attendu is not None and calcul.get(cle) != attendu:
                anomalies.append(f"Contrôle « {cle} » : onglet Controle {attendu}, recalculé {calcul.get(cle)}.")
        registre = sorted((a["code"], a["ecart_a_regulariser"]) for a in actuels if a["ecart_a_regulariser"])
        registre_banque = sorted((_texte(e["code"]), _entier(e.get("ecart"))) for e in ecarts)
        if registre != registre_banque:
            anomalies.append(f"Onglet Ecarts_Banque {registre_banque} ≠ écarts recalculés {registre}.")
        if inv.ajustements_at is not None or await self.inv.nb_ajustements(inv.id):
            anomalies.append("Les ajustements de cet inventaire ont déjà été appliqués.")

        return {
            "fichier": nom_fichier,
            "sha256": hashlib.sha256(contenu).hexdigest(),
            "inventaire": inv.reference,
            "source_officielle": _texte(meta.get("source autoritaire")),
            "source_libelle": source_libelle or f"Inventaire de référence {inv.reference}",
            "date_inventaire": _texte(meta.get("date inventaire")),
            "date_comptage": _texte(meta.get("comptage bancaire")),
            "calcul": calcul,
            "controle_fichier": controle,
            "mouvements": mouvements,
            "registre_ecarts": [{"code": c, "ecart": e} for c, e in registre],
            "anomalies": anomalies,
            "bloquant": bool(anomalies),
            "lignes": apercu,
        }

    async def charger(self, inventaire_id, contenu: bytes, nom_fichier: str, *, request: Request | None = None):
        inv = await self.inv.get(inventaire_id, for_update=True)
        self.inv.exiger_saisie(inv)
        analyse = await self.analyser(inventaire_id, contenu, nom_fichier)
        if analyse["bloquant"]:
            raise AppError(
                "Référence refusée : " + " ; ".join(analyse["anomalies"][:10]),
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="REFERENCE_ANOMALIES",
            )
        now = datetime.now(timezone.utc)
        user_id = self.inv.user.id if self.inv.user else None
        for a in analyse["lignes"]:
            lg = await self.db.get(MgInventaireLigne, a["_ligne_id"])
            d = a["_donnees"]
            lg.donnees_source = d
            lg.stock_theorique_source = (
                Decimal(a["theorique_reference"]) if a["theorique_reference"] is not None else None
            )
            if d.get("observations"):
                lg.observation = d["observations"][:255]
            if a["ancienne_agence"]:
                lg.statut_comptage = "EXCLU"
                lg.stock_cible = lg.stock_physique = lg.ecart = lg.nature_ecart = None
                lg.compte_par = lg.compte_at = None
                continue
            lg.stock_cible = Decimal(a["stock_cible"])
            lg.stock_physique = Decimal(a["stock_physique"])
            lg.ecart = lg.stock_physique - lg.stock_theorique_source
            lg.nature_ecart = nature_ecart(lg.ecart)
            lg.statut_comptage = "COMPTE"
            lg.compte_par = user_id
            lg.compte_at = now
        c = analyse["calcul"]
        inv.import_meta = {
            **(inv.import_meta or {}),
            "rapprochement": {
                "fichier": nom_fichier,
                "sha256": analyse["sha256"],
                "source_officielle": analyse["source_officielle"],
                "source_libelle": analyse["source_libelle"],
                "date_inventaire": analyse["date_inventaire"],
                "date_comptage": analyse["date_comptage"],
                "mouvements": analyse["mouvements"],
                "attendu": {
                    "references": c["references"],
                    "agence_actuelle": c["agence_actuelle"],
                    "ancienne_agence": c["ancienne_agence"],
                    "stock_systeme": c["stock_systeme"],
                    "stock_final": c["stock_final"],
                    "stock_physique": c["stock_physique"],
                    "ecart_restant": c["ecart_restant"],
                    "variation": c["variation"],
                    "ecarts": analyse["registre_ecarts"],
                },
                "charge_at": now.isoformat(),
                "charge_par": str(user_id) if user_id else None,
            },
        }
        if inv.statut == "BROUILLON":
            inv.statut = "EN_COURS"
        inv.updated_by = user_id
        await self.db.flush()
        await self.inv._audit(
            "chargement_reference", "mg_inventaire", inv.id, request=request,
            after={
                "reference": inv.reference,
                "fichier": nom_fichier,
                "sha256": analyse["sha256"],
                "source_officielle": analyse["source_officielle"],
                "date_inventaire": analyse["date_inventaire"],
                "date_comptage": analyse["date_comptage"],
                **c,
                "ecarts_a_regulariser": analyse["registre_ecarts"],
            },
        )
        await self.db.commit()
        return inv, analyse
