"""Lots de clients : un fichier Excel avec une colonne Racine client (+ colonnes libres).

Deux usages :
- ``LISTE``     : import hebdomadaire / liste reçue → évaluation moteur, divergences, classement, export ;
- ``SITUATION`` : classeur Conformité « Situation des comptes PP et PM » → reprise de la
  classe de risque historique (source ``EXCEL_CONFORMITE``).

Workflow : Import → Mapping → Contrôles → Aperçu → Évaluation → Divergences → Enregistrement →
Historique → Export. Le lot et ses lignes sont conservés en base (``clientele_classif_lots``) ;
seul le fichier brut est temporaire (7 jours, pour recartographier). Un lot peut être fermé
(conservé) ou supprimé (lignes retirées, classifications clients inchangées). La racine n'est
jamais modifiée ; une racine absente n'est jamais créée ici.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.data.clientele_classif_matrice import VERSION_MOTEUR, VERSION_REGLES
from app.data.clientele_import_hebdo import (
    colonnes_export, date_ouverture_interdite, est_feuille_clients, est_feuille_technique,
    est_ligne_consigne, est_valeur_consigne, ligne_export_hebdo, valider_ligne_hebdo,
)
from app.models import (
    ClienteleClassifEvaluation,
    ClienteleClassifLot,
    ClienteleClassifLotLigne,
    ClienteleClassification,
    ClienteleClient,
)
from app.services.clientele.classification import (
    NIVEAUX, SOURCES_MANUELLES, ClienteleClassificationService, trace_evaluation,
)
from app.services.clientele.consolidation import normaliser_entete
from app.services.clientele.scoring import INVALIDE, lire_oui_non
from app.services.clientele.service import Ctx, ClienteleService, maintenant
from app.services.reporting_export import build_styled_workbook_multi

TAILLE_MAX = 40 * 1024 * 1024
LIGNES_MAX = 80_000
LIMITE_EVALUATION = 2_000
APERCU = 300
DUREE_VIE_S = 7 * 24 * 3600
TYPES = ("LISTE", "SITUATION")

ENTETES_RACINE = ("RACINE_CLIENT", "RACINE CLIENT", "RACINE", "CLIENT", "CODE CLIENT", "NUMERO CLIENT")
ENTETES_NIVEAU = (
    "NIVEAU", "CLASSE RISQUE LBC FT", "CLASSE DE RISQUE LBC FT", "CLASSE DE RISQUE", "CLASSE RISQUE",
    "NIVEAU RISQUE", "NIVEAU DE RISQUE", "RISQUE LBC FT", "CLASSIFICATION",
)
ENTETES_MOTIF = ("MOTIF DE RISQUE", "MOTIF RISQUE", "MOTIF_RISQUE", "MOTIF", "MOTIF_CLASSEMENT",
                 "MOTIF CLASSEMENT", "OBSERVATION")
ENTETES_NOM = ("RAISON_SOCIAL", "RAISON SOCIALE", "NOM", "NOM CLIENT", "INTITULE")
ENTETES_ENTREPRISE_RECENTE = ("ENTREPRISE OUVERTURE RECENTE", "ENTREPRISE A OUVERTURE RECENTE",
                              "ENTREPRISE RECENTE", "OUVERTURE RECENTE")
ENTETES_DATE_OUVERTURE = ("DATE CREATION ENTREPRISE", "DATE DE CREATION ENTREPRISE",
                          "DATE_CREATION_ENTREPRISE", "DATE OUVERTURE ENTREPRISE",
                          "DATE D OUVERTURE ENTREPRISE", "DATE OUVERTURE", "DATE D OUVERTURE",
                          "DATE CREATION", "DATE DE CREATION")
ENTETES_DATE_MAJ = ("DATE MISE A JOUR CLIENT", "DATE DE MISE A JOUR CLIENT",
                    "DATE DE MISE A JOUR", "DATE MISE A JOUR", "DATE MAJ", "MISE A JOUR", "DATE DE MAJ")
ENTETES_ANALYSTE = ("ANALYSTE KYC", "ANALYSTE", "ANALYSTE CONFORMITE")
ENTETES_DATE_EER = ("DATE EER", "DATE D EER", "DATE ENTREE EN RELATION")
ENTETES_DATE_CLASSE = ("DATE CLASSE RISQUE LBC FT", "DATE DE CLASSE RISQUE LBC FT",
                       "DATE CLASSE RISQUE", "DATE CLASSIFICATION")

# Colonne cible → (clé du mapping, candidats d'en-tête).
CIBLES: dict[str, tuple[str, ...]] = {
    "racine": ENTETES_RACINE,
    "niveau": ENTETES_NIVEAU,
    "motif": ENTETES_MOTIF,
    "entreprise_recente": ENTETES_ENTREPRISE_RECENTE,
    "date_ouverture": ENTETES_DATE_OUVERTURE,
    "date_maj": ENTETES_DATE_MAJ,
    "analyste": ENTETES_ANALYSTE,
    "nom": ENTETES_NOM,
    "date_eer": ENTETES_DATE_EER,
    "date_classe": ENTETES_DATE_CLASSE,
}
_FORMATS_DATE = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y")
_EPOQUE_EXCEL = date(1899, 12, 30)


def _norm(v: Any) -> str:
    if v is None:
        return ""
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", normaliser_entete(str(v))).split())


def normaliser_racine(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float):
        if not v.is_integer():
            return None
        v = int(v)
    s = str(v).strip()
    if not s or not s.isdigit() or len(s) > 6:
        return None
    return s.zfill(6)


def normaliser_niveau(v: Any) -> str | None:
    s = _norm(v).replace("RISQUE", "").strip()
    if not s:
        return None
    if s.startswith("INTERDIT"):
        return "INTERDIT"
    if s.startswith("ELEV") or s in ("HAUT", "FORT"):
        return "ELEVE"
    if s.startswith("MOY"):
        return "MOYEN"
    if s.startswith("FAIBL") or s == "BAS":
        return "FAIBLE"
    return None


def lire_date(v: Any) -> date | str | None:
    """Date Excel / texte. None = vide ; ``INVALIDE`` = illisible (jamais devinée)."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 1 <= v <= 80_000 and float(v).is_integer():
            return _EPOQUE_EXCEL + timedelta(days=int(v))
        return INVALIDE
    s = str(v).strip()
    if not s:
        return None
    s = s.split(" ")[0].split("T")[0]
    for fmt in _FORMATS_DATE:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return INVALIDE


def _cherche(entetes: list[str], candidats: tuple[str, ...]) -> str | None:
    norm = {_norm(e): e for e in entetes if e}
    for c in candidats:
        if _norm(c) in norm:
            return norm[_norm(c)]
    return None


def _entetes(row: tuple) -> list[str]:
    out = []
    for i, c in enumerate(row):
        s = str(c).strip() if c is not None else ""
        out.append(s or f"(colonne {get_column_letter(i + 1)})")
    return out


def _detecter(wb) -> tuple[str, int, list[str]]:
    connus = {_norm(x) for cands in CIBLES.values() for x in cands}
    meilleur: tuple[int, str, int, list[str]] | None = None
    preferes = [ws for ws in wb.worksheets if est_feuille_clients(ws.title)]
    autres = [ws for ws in wb.worksheets
              if not est_feuille_clients(ws.title) and not est_feuille_technique(ws.title)]
    for ws in preferes + autres:
        bonus_feuille = 20 if est_feuille_clients(ws.title) else 0
        for i, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), start=1):
            if est_ligne_consigne(row or ()):
                continue
            entetes = _entetes(row)
            score = bonus_feuille + sum(1 for e in entetes if e and _norm(e) in connus)
            if _cherche(entetes, ENTETES_RACINE):
                score += 5
            if score and (meilleur is None or score > meilleur[0]):
                meilleur = (score, ws.title, i, entetes)
    if not meilleur:
        ws = preferes[0] if preferes else wb.worksheets[0]
        row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        return ws.title, 1, _entetes(row)
    return meilleur[1], meilleur[2], meilleur[3]


def resoudre_mapping(entetes: list[str], demande: dict | None) -> dict[str, str | None]:
    """Mapping explicite prioritaire ("" = aucune colonne), sinon reconnaissance des en-têtes."""
    demande = demande or {}
    out: dict[str, str | None] = {}
    for cible, candidats in CIBLES.items():
        if cible in demande and demande[cible] is not None:
            choix = demande[cible]
            out[cible] = choix if choix in entetes else None
        else:
            out[cible] = _cherche(entetes, candidats)
    if date_ouverture_interdite(out.get("date_ouverture")):
        out["date_ouverture"] = None
    return out


def lire_ligne(numero: int, row: tuple, entetes: list[str], mapping: dict[str, str | None]) -> dict:
    """Une ligne du fichier → valeurs normalisées + toutes les colonnes + anomalies."""
    idx = {e: i for i, e in enumerate(entetes)}

    def cell(cible: str) -> Any:
        col = mapping.get(cible)
        i = idx.get(col) if col else None
        return row[i] if i is not None and i < len(row) else None

    anomalies: list[str] = []

    def texte(v: Any, n: int) -> str | None:
        if v is None or str(v).strip() == "":
            return None
        s = str(v).strip()
        if len(s) > n:
            anomalies.append(
                f"Valeur trop longue ({len(s)} caractères, {n} conservés pour le champ dédié) : "
                "non tronquée dans les colonnes source")
            return s[:n]
        return s
    brut_niveau = cell("niveau")
    niveau = normaliser_niveau(brut_niveau) if mapping.get("niveau") else None
    if texte(brut_niveau, 40) and not niveau:
        anomalies.append("Classe de risque illisible")
    brut_er = cell("entreprise_recente")
    er = lire_oui_non(brut_er) if texte(brut_er, 40) else None
    if er == INVALIDE:
        anomalies.append("Entreprise ouverture récente illisible (Oui / Non attendu)")
    brut_ouv = cell("date_ouverture")
    d_ouv = lire_date(brut_ouv)
    if d_ouv == INVALIDE:
        anomalies.append("Date d'ouverture illisible")
    brut_maj = cell("date_maj")
    d_maj = lire_date(brut_maj)
    if d_maj == INVALIDE:
        anomalies.append("Date de mise à jour illisible")
    for cible, lib in (("date_eer", "DATE EER"), ("date_classe", "Date classe risque LBC FT")):
        brut = cell(cible)
        lu = lire_date(brut) if texte(brut, 40) and not est_valeur_consigne(brut) else None
        if lu == INVALIDE:
            anomalies.append(f"{lib} illisible")
        elif est_valeur_consigne(brut):
            anomalies.append(f"{lib} : valeur de consigne, pas une date")
    racine_brut = cell("racine")
    if est_valeur_consigne(racine_brut):
        racine_brut = None
    donnees = {}
    for i, e in enumerate(entetes):
        if e and i < len(row) and row[i] is not None and str(row[i]).strip() != "":
            v = row[i]
            if isinstance(v, datetime):
                donnees[e] = v.date().isoformat()
            elif isinstance(v, date):
                donnees[e] = v.isoformat()
            else:
                s = str(v)
                if len(s) > 4000:
                    anomalies.append(f"Colonne « {e} » trop longue ({len(s)} caractères) : conservée en entier, non tronquée")
                donnees[e] = s
    anomalies.extend(valider_ligne_hebdo(donnees))
    return {
        "ligne": numero,
        "brut": texte(racine_brut, 40),
        "racine_client": normaliser_racine(racine_brut),
        "nom": texte(cell("nom"), 255),
        "donnees": donnees,
        "classe_source": niveau,
        "classe_source_brut": texte(brut_niveau, 40),
        "motif_source": texte(cell("motif"), 2000),
        "entreprise_recente_brut": texte(brut_er, 40),
        "date_ouverture_entreprise": d_ouv if isinstance(d_ouv, date) else None,
        "date_ouverture_brut": texte(brut_ouv if not isinstance(brut_ouv, datetime) else brut_ouv.date(), 40),
        "source_date_ouverture": "FICHIER" if isinstance(d_ouv, date) else None,
        "date_maj_metier": d_maj if isinstance(d_maj, date) else None,
        "date_maj_brut": texte(brut_maj if not isinstance(brut_maj, datetime) else brut_maj.date(), 40),
        "analyste_kyc": texte(cell("analyste"), 120),
        "anomalies": anomalies,
    }


class ClienteleLotService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    # ------------------------------------------------------------------ fichier temporaire
    def _dossier(self) -> Path:
        p = Path(get_settings().upload_dir) / "clientele" / "lots"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _xlsx(self, lid: uuid.UUID) -> Path:
        return self._dossier() / f"{lid}.xlsx"

    def _purger(self) -> None:
        limite = time.time() - DUREE_VIE_S
        for p in self._dossier().glob("*"):
            try:
                if p.stat().st_mtime < limite:
                    p.unlink()
            except OSError:
                pass

    async def _charger(self, lid: uuid.UUID) -> ClienteleClassifLot:
        lot = await self.db.get(ClienteleClassifLot, lid)
        if not lot or (lot.created_by_id not in (None, self.ctx.user.id) and not self.ctx.peut("clientele.admin")):
            raise AppError("Lot introuvable", 404, code="NOT_FOUND")
        return lot

    async def _lignes(self, lid: uuid.UUID) -> list[ClienteleClassifLotLigne]:
        return list((await self.db.scalars(
            select(ClienteleClassifLotLigne).where(ClienteleClassifLotLigne.lot_id == lid)
            .order_by(ClienteleClassifLotLigne.ligne))).all())

    # ------------------------------------------------------------------ analyse
    async def analyser(self, contenu: bytes, nom_fichier: str, *, type_lot: str = "LISTE",
                       mapping: dict | None = None, periode_reference: date | None = None,
                       lid: uuid.UUID | None = None) -> dict:
        if not self.ctx.peut("clientele.import.execute", "clientele.classif.execute"):
            self.ctx.exiger("clientele.classif.execute")
        type_lot = type_lot if type_lot in TYPES else "LISTE"
        if not contenu:
            raise AppError("Fichier vide", 422, code="FICHIER_VIDE")
        if len(contenu) > TAILLE_MAX:
            raise AppError("Fichier trop volumineux (40 Mo maximum)", 413, code="FICHIER_TROP_VOLUMINEUX")
        if not nom_fichier.lower().endswith((".xlsx", ".xlsm")):
            raise AppError("Format non pris en charge : fichier .xlsx attendu", 422, code="FORMAT_NON_SUPPORTE")
        try:
            wb = load_workbook(BytesIO(contenu), read_only=True, data_only=True)
        except Exception as exc:
            raise AppError("Fichier Excel illisible ou corrompu", 422, code="FICHIER_ILLISIBLE") from exc
        lignes: list[dict] = []
        try:
            feuille, ligne_entete, entetes = _detecter(wb)
            cols = resoudre_mapping(entetes, mapping)
            ignorees = 0
            if cols["racine"]:
                ws = wb[feuille]
                for numero, row in enumerate(ws.iter_rows(min_row=ligne_entete + 1, values_only=True),
                                             start=ligne_entete + 1):
                    if not row or all(c is None or str(c).strip() == "" for c in row):
                        continue
                    if est_ligne_consigne(row):
                        ignorees += 1
                        continue
                    idx_r = next((i for i, e in enumerate(entetes) if e == cols["racine"]), None)
                    brut_r = row[idx_r] if idx_r is not None and idx_r < len(row) else None
                    if brut_r is None or str(brut_r).strip() == "" or est_valeur_consigne(brut_r):
                        ignorees += 1
                        continue
                    if len(lignes) >= LIGNES_MAX:
                        raise AppError(f"Plus de {LIGNES_MAX} lignes : découpez le fichier", 422,
                                       code="TROP_DE_LIGNES")
                    lignes.append(lire_ligne(numero, row, entetes, cols))
            lot_ignorees = ignorees
        finally:
            wb.close()

        await self._controler(lignes)
        sha = hashlib.sha256(contenu).hexdigest()
        if lid:
            lot = await self._charger(lid)
            if lot.statut in ("ENREGISTRE", "FERME"):
                raise AppError("Lot déjà enregistré ou fermé : déposez un nouveau fichier pour changer le "
                               "mapping (l'historique du lot est conservé).", 409, code="LOT_FIGE")
            await self.db.execute(delete(ClienteleClassifLotLigne).where(ClienteleClassifLotLigne.lot_id == lid))
        else:
            lot = ClienteleClassifLot(id=uuid.uuid4(), created_by_id=self.ctx.user.id)
            self.db.add(lot)
        lot.fichier_nom = nom_fichier[:255]
        lot.sha256 = sha
        lot.type = type_lot
        lot.periode_reference = periode_reference or lot.periode_reference or date.today()
        lot.feuille = feuille[:120]
        lot.ligne_entete = ligne_entete
        lot.entetes = [e for e in entetes if e]
        lot.mapping = cols
        lot.stats = self._stats(lignes, ignorees=lot_ignorees)
        lot.evaluation = None
        lot.statut = "ANALYSE"
        lot.updated_at = maintenant()
        await self.db.flush()
        if lignes:
            for i in range(0, len(lignes), 2000):
                await self.db.execute(insert(ClienteleClassifLotLigne), [
                    {"id": uuid.uuid4(), "lot_id": lot.id, **x} for x in lignes[i:i + 2000]])
        self._purger()
        self._xlsx(lot.id).write_bytes(contenu)
        await self.svc.audit("clientele.lot.analyse", "clientele_classif_lot", lot.id,
                             after={"fichier": nom_fichier, "type": type_lot, "sha256": sha,
                                    "mapping": cols, **lot.stats})
        return await self._public(lot)

    async def recartographier(self, lid: uuid.UUID, payload: dict) -> dict:
        lot = await self._charger(lid)
        p = self._xlsx(lid)
        if not p.exists():
            raise AppError("Fichier du lot expiré ; déposez-le de nouveau", 409, code="FICHIER_ABSENT")
        mapping = {
            "racine": payload.get("colonne_racine"), "niveau": payload.get("colonne_niveau"),
            "motif": payload.get("colonne_motif"),
            "entreprise_recente": payload.get("colonne_entreprise_recente"),
            "date_ouverture": payload.get("colonne_date_ouverture"),
            "date_maj": payload.get("colonne_date_maj"), "analyste": payload.get("colonne_analyste"),
        }
        periode = payload.get("periode_reference")
        return await self.analyser(
            p.read_bytes(), lot.fichier_nom, type_lot=payload.get("type") or lot.type,
            mapping=mapping, lid=lid,
            periode_reference=date.fromisoformat(str(periode)) if periode else None)

    async def _controler(self, lignes: list[dict]) -> None:
        racines = sorted({x["racine_client"] for x in lignes if x["racine_client"]})
        connus: dict[str, str] = {}
        classes: dict[str, dict] = {}
        for i in range(0, len(racines), 5000):
            paquet = racines[i:i + 5000]
            for r, nom in (await self.db.execute(
                    select(ClienteleClient.racine_client, ClienteleClient.raison_sociale)
                    .where(ClienteleClient.racine_client.in_(paquet)))).all():
                connus[r] = nom
            for c in (await self.db.scalars(
                    select(ClienteleClassification).where(ClienteleClassification.racine_client.in_(paquet)))).all():
                classes[c.racine_client] = {"niveau": c.niveau, "source": c.source}
        vues: set[str] = set()
        for x in lignes:
            r = x["racine_client"]
            if not r:
                x["statut"] = "INVALIDE"
            elif r in vues:
                x["statut"] = "DOUBLON"
            elif r not in connus:
                x["statut"] = "INCONNUE"
            else:
                x["statut"] = "OK"
                vues.add(r)
            if r and connus.get(r):
                x["nom"] = connus[r][:255]
            x["classe_actuelle"] = classes.get(r, {}).get("niveau") if r else None
            x["source_actuelle"] = classes.get(r, {}).get("source") if r else None

    async def _rafraichir_classes(self, lignes: list[ClienteleClassifLotLigne]) -> None:
        racines = [x.racine_client for x in lignes if x.statut == "OK"]
        classes: dict[str, ClienteleClassification] = {}
        for i in range(0, len(racines), 5000):
            for c in (await self.db.scalars(select(ClienteleClassification).where(
                    ClienteleClassification.racine_client.in_(racines[i:i + 5000])))).all():
                classes[c.racine_client] = c
        for x in lignes:
            c = classes.get(x.racine_client or "")
            x.classe_actuelle = c.niveau if c else None
            x.source_actuelle = c.source if c else None

    @staticmethod
    def _stats(lignes: list[Any], *, ignorees: int = 0) -> dict:
        def g(x: Any, k: str) -> Any:
            return x.get(k) if isinstance(x, dict) else getattr(x, k)

        def n(pred) -> int:
            return sum(1 for x in lignes if pred(x))
        ok = [x for x in lignes if g(x, "statut") == "OK"]
        return {
            "lignes": len(lignes),
            "lignes_ignorees": ignorees,
            "racines_ok": len(ok),
            "inconnues": n(lambda x: g(x, "statut") == "INCONNUE"),
            "invalides": n(lambda x: g(x, "statut") == "INVALIDE"),
            "doublons": n(lambda x: g(x, "statut") == "DOUBLON"),
            "avec_niveau": sum(1 for x in ok if g(x, "classe_source")),
            "niveau_illisible": n(lambda x: g(x, "classe_source_brut") and not g(x, "classe_source")),
            "avec_entreprise_recente": sum(1 for x in ok if g(x, "entreprise_recente_brut")),
            "avec_date_ouverture": sum(1 for x in ok if g(x, "date_ouverture_entreprise")),
            "avec_date_maj": sum(1 for x in ok if g(x, "date_maj_metier")),
            "avec_analyste": sum(1 for x in ok if g(x, "analyste_kyc")),
            "avec_anomalie": n(lambda x: bool(g(x, "anomalies"))),
            "deja_classes": sum(1 for x in ok if g(x, "classe_actuelle")),
            "manuels": sum(1 for x in ok if g(x, "source_actuelle") in SOURCES_MANUELLES),
        }

    # ------------------------------------------------------------------ lecture
    @staticmethod
    def _ligne_dict(x: ClienteleClassifLotLigne) -> dict:
        moteur = None
        if x.statut_moteur:
            moteur = {"score": x.score, "niveau": x.niveau_propose, "statut": x.statut_moteur,
                      "motif": x.motif_moteur, "classable": bool(x.admissible),
                      "evaluation_id": str(x.evaluation_id) if x.evaluation_id else None}
        return {
            "ligne": x.ligne, "brut": x.brut, "racine": x.racine_client, "statut": x.statut,
            "nom": x.nom, "nom_fichier": x.nom,
            "niveau_fichier": x.classe_source, "niveau_fichier_brut": x.classe_source_brut,
            "motif_fichier": x.motif_source,
            "entreprise_recente": x.entreprise_recente_brut,
            "date_ouverture": x.date_ouverture_entreprise.isoformat() if x.date_ouverture_entreprise else None,
            "date_ouverture_brut": x.date_ouverture_brut, "source_date_ouverture": x.source_date_ouverture,
            "date_maj": x.date_maj_metier.isoformat() if x.date_maj_metier else None,
            "date_maj_brut": x.date_maj_brut, "analyste": x.analyste_kyc,
            "anomalies": x.anomalies or [],
            "classe_actuelle": x.classe_actuelle, "source_actuelle": x.source_actuelle,
            "colonnes": x.donnees or {}, "moteur": moteur,
            "divergence": x.divergence_fichier_moteur, "decision": x.decision,
            "decision_detail": x.decision_detail,
        }

    async def _public(self, lot: ClienteleClassifLot, *, statut: str | None = None, page: int = 1,
                      taille: int = APERCU) -> dict:
        L = ClienteleClassifLotLigne
        q = select(L).where(L.lot_id == lot.id)
        if statut == "DIVERGENCE":
            q = q.where(L.divergence_fichier_moteur.is_(True))
        elif statut == "ANOMALIE":
            q = q.where(func.jsonb_array_length(L.anomalies) > 0)
        elif statut == "A_TRAITER":
            q = q.where(L.decision.in_(("DIVERGENCE_A_TRAITER", "NON_ADMISSIBLE")))
        elif statut:
            q = q.where(L.statut == statut)
        total = await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        page = max(1, page)
        rows = (await self.db.scalars(q.order_by(L.ligne).offset((page - 1) * taille).limit(taille))).all()
        precedent = await self.db.scalar(
            select(ClienteleClassifLot).where(ClienteleClassifLot.sha256 == lot.sha256,
                                              ClienteleClassifLot.id != lot.id)
            .order_by(ClienteleClassifLot.created_at.desc()).limit(1)) if lot.sha256 else None
        m = lot.mapping or {}
        mappes = {v for v in m.values() if v}
        message = None
        if not m.get("racine"):
            message = "Colonne Racine client non reconnue : choisissez-la dans la liste."
        elif not (lot.stats or {}).get("lignes") and (lot.stats or {}).get("lignes_ignorees"):
            message = (
                "Aucune ligne client : le fichier contient des consignes ou des listes de référence "
                "(profils, secteurs BCM, statuts…) sans RACINE CLIENT. Remplissez la feuille CLIENTS, "
                "une ligne par racine. Les listes de référence ne sont jamais importées comme des clients."
            )
        elif not (lot.stats or {}).get("lignes"):
            message = "Aucune ligne client dans la feuille reconnue. Utilisez le modèle (feuille CLIENTS)."
        elif precedent:
            message = (f"Fichier identique déjà déposé le {precedent.created_at:%d/%m/%Y} "
                       f"(« {precedent.fichier_nom} »). Les classifications inchangées ne seront pas dupliquées.")
        return {
            "id": str(lot.id), "fichier_nom": lot.fichier_nom, "type": lot.type, "sha256": lot.sha256,
            "statut_lot": lot.statut, "periode_reference": lot.periode_reference.isoformat()
            if lot.periode_reference else None,
            "feuille": lot.feuille, "ligne_entete": lot.ligne_entete, "entetes": lot.entetes or [],
            "mapping": m,
            "colonne_racine": m.get("racine"), "colonne_niveau": m.get("niveau"), "colonne_motif": m.get("motif"),
            "colonne_entreprise_recente": m.get("entreprise_recente"),
            "colonne_date_ouverture": m.get("date_ouverture"), "colonne_date_maj": m.get("date_maj"),
            "colonne_analyste": m.get("analyste"),
            "colonnes_affichees": [e for e in (lot.entetes or []) if e not in mappes],
            "message": message, "doublon_de": str(precedent.id) if precedent else None,
            "stats": lot.stats or {}, "evaluation": lot.evaluation,
            "dernier_classement": lot.dernier_classement,
            "total_filtre": int(total), "page": page, "taille": taille,
            "lignes": [self._ligne_dict(x) for x in rows],
            "limite_evaluation": LIMITE_EVALUATION,
            "created_at": lot.created_at.isoformat() if lot.created_at else None,
        }

    async def detail(self, lid: uuid.UUID, *, statut: str | None = None, page: int = 1) -> dict:
        return await self._public(await self._charger(lid), statut=statut, page=page)

    async def lister(self, *, page: int = 1, taille: int = 30) -> dict:
        if not self.ctx.peut("clientele.import.execute", "clientele.classif.execute", "clientele.classif.view"):
            self.ctx.exiger("clientele.classif.view")
        q = select(ClienteleClassifLot)
        if not self.ctx.peut("clientele.admin"):
            q = q.where(ClienteleClassifLot.created_by_id == self.ctx.user.id)
        total = await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = (await self.db.scalars(q.order_by(ClienteleClassifLot.created_at.desc())
                                      .offset((max(1, page) - 1) * taille).limit(min(taille, 100)))).all()
        return {"total": int(total), "items": [{
            "id": str(x.id), "fichier_nom": x.fichier_nom, "type": x.type, "statut": x.statut,
            "periode_reference": x.periode_reference.isoformat() if x.periode_reference else None,
            "stats": x.stats or {}, "dernier_classement": x.dernier_classement,
            "created_at": x.created_at.isoformat() if x.created_at else None,
            "actions": {
                "voir": True, "exporter": True,
                "modifier": x.statut != "FERME",
                "fermer": x.statut != "FERME",
                "supprimer": True,
            },
        } for x in rows]}

    async def mettre_a_jour(self, lid: uuid.UUID, payload: dict) -> dict:
        """Met à jour le libellé et/ou la période (lot non fermé)."""
        lot = await self._charger(lid)
        if lot.statut == "FERME":
            raise AppError("Lot fermé : rouvrez-le ou déposez un nouveau fichier.", 409, code="LOT_FIGE")
        avant = {"fichier_nom": lot.fichier_nom,
                 "periode_reference": lot.periode_reference.isoformat() if lot.periode_reference else None}
        nom = (payload.get("fichier_nom") or "").strip()
        if nom:
            lot.fichier_nom = nom[:255]
        periode = payload.get("periode_reference")
        if periode:
            lot.periode_reference = date.fromisoformat(str(periode)[:10])
        elif "periode_reference" in payload and payload.get("periode_reference") in (None, ""):
            lot.periode_reference = None
        lot.updated_at = maintenant()
        await self.db.flush()
        await self.svc.audit("clientele.lot.modifier", "clientele_classif_lot", lid, before=avant,
                             after={"fichier_nom": lot.fichier_nom,
                                    "periode_reference": lot.periode_reference.isoformat()
                                    if lot.periode_reference else None})
        return await self._public(lot)

    async def fermer(self, lid: uuid.UUID) -> None:
        """Ferme le lot : fichier temporaire retiré, lot et lignes conservés."""
        lot = await self._charger(lid)
        p = self._xlsx(lid)
        if p.exists():
            p.unlink()
        lot.statut = "FERME"
        lot.updated_at = maintenant()
        await self.db.flush()
        await self.svc.audit("clientele.lot.fermer", "clientele_classif_lot", lid)

    async def supprimer(self, lid: uuid.UUID, *, motif: str | None = None) -> None:
        """Supprime définitivement le lot et ses lignes. Les classifications clients restent."""
        lot = await self._charger(lid)
        motif = (motif or "").strip()
        if not motif:
            raise AppError("Motif de suppression obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        avant = {"fichier_nom": lot.fichier_nom, "type": lot.type, "statut": lot.statut,
                 "sha256": lot.sha256, "stats": lot.stats,
                 "periode_reference": lot.periode_reference.isoformat() if lot.periode_reference else None}
        p = self._xlsx(lid)
        if p.exists():
            p.unlink()
        await self.svc.audit("clientele.lot.supprimer", "clientele_classif_lot", lid,
                             before=avant, after={"motif": motif})
        await self.db.delete(lot)
        await self.db.flush()

    # ------------------------------------------------------------------ saisie analyste
    async def saisir_date_ouverture(self, lid: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.classif.execute")
        lot = await self._charger(lid)
        if lot.statut == "FERME":
            raise AppError("Lot fermé", 409, code="LOT_FIGE")
        x = await self.db.scalar(select(ClienteleClassifLotLigne).where(
            ClienteleClassifLotLigne.lot_id == lid, ClienteleClassifLotLigne.ligne == int(payload.get("ligne") or 0)))
        if not x or x.statut != "OK":
            raise AppError("Ligne introuvable ou racine non reconnue", 404, code="NOT_FOUND")
        brut = payload.get("date_ouverture")
        valeur = lire_date(brut) if brut not in (None, "") else None
        if valeur == INVALIDE:
            raise AppError("Date d'ouverture invalide (JJ/MM/AAAA ou AAAA-MM-JJ)", 422, code="DATE_INVALIDE")
        if isinstance(valeur, date) and valeur > date.today():
            raise AppError("Date d'ouverture dans le futur", 422, code="DATE_INVALIDE")
        avant = x.date_ouverture_entreprise.isoformat() if x.date_ouverture_entreprise else None
        x.date_ouverture_entreprise = valeur
        x.source_date_ouverture = "SAISIE" if valeur else None
        x.date_ouverture_saisie_par_id = self.ctx.user.id
        x.date_ouverture_saisie_le = maintenant()
        x.anomalies = [a for a in (x.anomalies or []) if not a.startswith("Date d'ouverture")]
        x.statut_moteur = x.niveau_propose = x.motif_moteur = None
        x.score = None
        x.admissible = None
        x.evaluation_id = None
        x.divergence_fichier_moteur = False
        lot.stats = self._stats(await self._lignes(lid))
        await self.db.flush()
        await self.svc.audit("clientele.lot.date_ouverture", "clientele_classif_lot", lid,
                             before={"ligne": x.ligne, "date_ouverture": avant},
                             after={"ligne": x.ligne, "racine": x.racine_client,
                                    "date_ouverture": valeur.isoformat() if valeur else None})
        return self._ligne_dict(x)

    # ------------------------------------------------------------------ évaluation
    @staticmethod
    def _complements(x: ClienteleClassifLotLigne) -> dict:
        out: dict = {}
        if x.date_ouverture_entreprise:
            out["date_ouverture_entreprise"] = x.date_ouverture_entreprise
            out["source_date_ouverture"] = x.source_date_ouverture or "FICHIER"
        if x.entreprise_recente_brut:
            out["entreprise_recente"] = x.entreprise_recente_brut
        return out

    async def evaluer(self, lid: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.classif.view")
        lot = await self._charger(lid)
        lignes = [x for x in await self._lignes(lid) if x.statut == "OK"]
        if not lignes:
            raise AppError("Aucune racine connue du référentiel dans ce fichier", 422, code="AUCUNE_RACINE")
        if len(lignes) > LIMITE_EVALUATION:
            raise AppError(
                f"{len(lignes)} racines : l'évaluation moteur est limitée à {LIMITE_EVALUATION} par lot. "
                "Découpez le fichier.", 422, code="LOT_TROP_GRAND")
        classif = ClienteleClassificationService(self.db, self.ctx)
        compteurs: dict[str, int] = {}
        divergences = contradictions = 0
        for x in lignes:
            complements = {**(await classif._complements_connus(x.racine_client)), **self._complements(x)}
            ev = await classif.evaluer_racine(x.racine_client, persister=True, complements=complements,
                                              lot_id=lot.id, ligne=x.ligne)
            niveau = ev.get("niveau_final")
            compteurs[niveau or "NON_CLASSE"] = compteurs.get(niveau or "NON_CLASSE", 0) + 1
            x.evaluation_id = uuid.UUID(ev["evaluation_id"])
            x.score = ev.get("score_total")
            x.niveau_propose = niveau
            x.statut_moteur = ev.get("statut")
            x.motif_moteur = ev.get("motif_genere") or ev.get("motif_principal")
            x.admissible = bool(ev.get("admissible"))
            x.divergence_fichier_moteur = bool(x.classe_source and x.admissible and x.classe_source != niveau)
            divergences += x.divergence_fichier_moteur
            anomalies = [a for a in (x.anomalies or []) if not a.startswith("Entreprise récente :")]
            er = next((lg for lg in ev.get("lignes", []) if lg["critere"] == "ENTREPRISE_RECENTE"), None)
            if er and er["etat"] == "A_VERIFIER":
                anomalies.append(f"Entreprise récente : {er['motif']}")
                contradictions += 1
            x.anomalies = anomalies
            if x.classe_source and not x.admissible:
                x.decision_detail = {"comparaison": "NON_COMPARABLE",
                                     "raison": f"Moteur {ev.get('statut')} : pas de niveau proposé admissible."}
        await self._rafraichir_classes(lignes)
        lot.evaluation = {
            "nb": len(lignes), "par_niveau": compteurs,
            "classables": sum(1 for x in lignes if x.admissible),
            "a_arbitrer": sum(1 for x in lignes if x.statut_moteur == "A_ARBITRER"),
            "divergences": divergences, "contradictions_entreprise": contradictions,
            "date": maintenant().isoformat(), "version_moteur": VERSION_MOTEUR, "version_regles": VERSION_REGLES,
        }
        if lot.statut == "ANALYSE":
            lot.statut = "EVALUE"
        lot.stats = self._stats(await self._lignes(lid),
                                ignorees=(lot.stats or {}).get("lignes_ignorees", 0))
        lot.updated_at = maintenant()
        await self.db.flush()
        await self.svc.audit("clientele.lot.evaluer", "clientele_classif_lot", lid,
                             after={"nb": len(lignes), "par_niveau": compteurs, "divergences": divergences})
        return await self._public(lot)

    async def _ev_ligne(self, x: ClienteleClassifLotLigne) -> dict:
        """Résultat moteur revu par l'utilisateur (photographie de l'évaluation du lot)."""
        rec = await self.db.scalar(select(ClienteleClassifEvaluation)
                                   .where(ClienteleClassifEvaluation.id == x.evaluation_id)
                                   .options(selectinload(ClienteleClassifEvaluation.lignes)))
        return {
            "statut": x.statut_moteur, "niveau_final": x.niveau_propose, "score_total": x.score,
            "motif_genere": x.motif_moteur, "evaluation_id": str(x.evaluation_id) if x.evaluation_id else None,
            "date_reference": rec.date_reference if rec else None,
            "version_moteur": rec.version_moteur if rec else None,
            "version_regles": rec.version_regles if rec else None,
            "lignes": [{
                "critere": lg.critere, "libelle": lg.libelle, "famille": lg.famille, "valeur": lg.valeur,
                "poids": lg.poids, "niveau_retenu": lg.niveau_retenu, "motif": lg.motif,
                "contribue_au_score": lg.contribue_au_score, "blocking_propose": lg.blocking_propose,
            } for lg in (rec.lignes if rec else [])],
        }

    @staticmethod
    def _trace_ligne(lot: ClienteleClassifLot, x: ClienteleClassifLotLigne) -> dict:
        return {
            "lot_id": lot.id, "ligne_source": x.ligne, "date_maj_metier": x.date_maj_metier,
            "analyste_kyc": x.analyste_kyc, "classe_source_fichier": x.classe_source,
            "motif_source": x.motif_source,
        }

    # ------------------------------------------------------------------ enregistrement
    async def classer(self, lid: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.classif.execute")
        lot = await self._charger(lid)
        if lot.statut == "FERME":
            raise AppError("Lot fermé", 409, code="LOT_FIGE")
        origine = payload.get("origine")
        motif = (payload.get("motif") or "").strip()
        forcer = bool(payload.get("forcer"))
        confirmation = bool(payload.get("confirmation"))
        if origine not in ("MOTEUR", "FICHIER"):
            raise AppError("Origine attendue : MOTEUR ou FICHIER", 422, code="ORIGINE_INVALIDE")
        if not motif:
            raise AppError("Motif de classement obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        classif = ClienteleClassificationService(self.db, self.ctx)
        if forcer:
            classif._exiger_forcage(confirmation, motif)
        if not lot.evaluation:
            raise AppError("Lancez d'abord l'évaluation moteur du lot (comparaison fichier / moteur)", 409,
                           code="EVALUATION_ABSENTE")
        lignes = [x for x in await self._lignes(lid) if x.statut == "OK"]
        bilan = {"ECRIT": 0, "INCHANGE": 0, "MANUEL_PRESERVE": 0, "NON_ADMISSIBLE": 0,
                 "NON_CLASSABLE": 0, "DIVERGENCE_A_TRAITER": 0, "A_REEVALUER": 0}
        for x in lignes:
            if not x.statut_moteur:
                bilan["A_REEVALUER"] += 1
                continue
            trace = self._trace_ligne(lot, x)
            if origine == "MOTEUR":
                res = await classif.ecrire_resultat_moteur(
                    x.racine_client, await self._ev_ligne(x), motif, forcer=forcer,
                    confirmation=confirmation, trace=trace)
            else:
                res = await self._ecrire_fichier(classif, lot, x, motif, forcer, trace)
            bilan[res] += 1
            x.decision = res
            x.decision_detail = {**(x.decision_detail or {}), "origine": origine, "motif": motif,
                                 "par": str(self.ctx.user.id), "le": maintenant().isoformat(), "force": forcer}
        resume = {"origine": origine, "ecrits": bilan["ECRIT"], "inchanges": bilan["INCHANGE"],
                  "manuels_preserves": bilan["MANUEL_PRESERVE"],
                  "non_classables": bilan["NON_ADMISSIBLE"] + bilan["NON_CLASSABLE"],
                  "divergences_a_traiter": bilan["DIVERGENCE_A_TRAITER"], "a_reevaluer": bilan["A_REEVALUER"],
                  "force": forcer}
        await self._rafraichir_classes(lignes)
        lot.stats = self._stats(await self._lignes(lid),
                                ignorees=(lot.stats or {}).get("lignes_ignorees", 0))
        lot.dernier_classement = resume
        lot.statut = "ENREGISTRE"
        lot.updated_at = maintenant()
        await self.db.flush()
        await self.svc.audit("clientele.lot.classer", "clientele_classif_lot", lid,
                             after={**resume, "fichier": lot.fichier_nom, "motif": motif})
        return {**(await self._public(lot)), "bilan": resume}

    async def _ecrire_fichier(self, classif: ClienteleClassificationService, lot: ClienteleClassifLot,
                              x: ClienteleClassifLotLigne, motif: str, forcer: bool, trace: dict) -> str:
        niveau = x.classe_source
        if niveau not in NIVEAUX:
            return "NON_CLASSABLE"
        if x.divergence_fichier_moteur:
            return "DIVERGENCE_A_TRAITER"
        actuelle = await self.db.get(ClienteleClassification, x.racine_client)
        if actuelle and actuelle.source in SOURCES_MANUELLES and not forcer:
            if actuelle.niveau != niveau:
                await classif.ouvrir_reexamen(
                    x.racine_client, origine="LOT", source_suggestion="FICHIER", niveau_suggere=niveau,
                    actuelle=actuelle, lot_id=lot.id, ligne=x.ligne,
                    motif=f"Fichier « {lot.fichier_nom} » ligne {x.ligne} : {niveau} ; décision manuelle "
                          f"{actuelle.niveau} conservée.")
            return "MANUEL_PRESERVE"
        source = "EXCEL_CONFORMITE" if lot.type == "SITUATION" else "EXCEL"
        if actuelle and actuelle.niveau == niveau and actuelle.source == source:
            return "INCHANGE"
        force = bool(actuelle and actuelle.source in SOURCES_MANUELLES)
        ev = await self._ev_ligne(x)
        motifs = [{"critere": source, "motif": x.motif_source or motif, "niveau": niveau,
                   "fichier": lot.fichier_nom, "ligne": x.ligne, "lot_id": str(lot.id)}]
        await classif._enregistrer(
            x.racine_client, niveau, source=source, version_id=None, motifs=motifs,
            motif_risque=x.motif_source, motif_classement=motif,
            trace={**trace_evaluation(ev), **trace, "mode_decision": "FICHIER", "force": force})
        if force:
            await self.svc.audit("clientele.classif.forcage", "clientele_classification", x.racine_client,
                                 before={"niveau": actuelle.niveau, "source": actuelle.source},
                                 after={"niveau": niveau, "mode": "FICHIER", "lot_id": str(lot.id), "motif": motif})
        return "ECRIT"

    async def decider_divergences(self, lid: uuid.UUID, payload: dict) -> dict:
        """Traitement des divergences fichier / moteur : décision humaine motivée, ligne par ligne."""
        self.ctx.exiger("clientele.classif.execute")
        lot = await self._charger(lid)
        if lot.statut == "FERME":
            raise AppError("Lot fermé", 409, code="LOT_FIGE")
        decisions = payload.get("decisions") or []
        if not decisions:
            raise AppError("Aucune décision", 422, code="AUCUNE_LIGNE")
        classif = ClienteleClassificationService(self.db, self.ctx)
        par_ligne = {x.ligne: x for x in await self._lignes(lid)}
        faits = 0
        for d in decisions:
            x = par_ligne.get(int(d.get("ligne") or 0))
            if not x or x.statut != "OK" or not x.statut_moteur:
                raise AppError(f"Ligne {d.get('ligne')} : racine non reconnue ou non évaluée", 422,
                               code="LIGNE_INVALIDE")
            choix = (d.get("choix") or "").upper()
            niveau = {"MOTEUR": x.niveau_propose, "FICHIER": x.classe_source}.get(choix) or (
                (d.get("niveau") or "").upper() if choix == "AUTRE" else None)
            if niveau not in NIVEAUX:
                raise AppError(f"Ligne {x.ligne} : niveau à retenir absent ou invalide", 422, code="NIVEAU_INVALIDE")
            ev = await self._ev_ligne(x)
            await classif.decider_manuel(
                x.racine_client, niveau, d.get("motif") or "", forcer=bool(payload.get("forcer")),
                confirmation=bool(payload.get("confirmation")),
                trace={**trace_evaluation(ev), **self._trace_ligne(lot, x), "_statut_moteur": x.statut_moteur})
            x.decision = f"ARBITRE_{choix}"[:24]
            x.decision_detail = {**(x.decision_detail or {}), "choix": choix, "niveau": niveau,
                                 "motif": d.get("motif"), "par": str(self.ctx.user.id),
                                 "le": maintenant().isoformat()}
            faits += 1
        lignes = list(par_ligne.values())
        await self._rafraichir_classes(lignes)
        lot.stats = self._stats(lignes, ignorees=(lot.stats or {}).get("lignes_ignorees", 0))
        lot.updated_at = maintenant()
        await self.db.flush()
        await self.svc.audit("clientele.lot.divergences", "clientele_classif_lot", lid, after={"decisions": faits})
        return {**(await self._public(lot, statut="DIVERGENCE")), "decisions": faits}

    # ------------------------------------------------------------------ export
    async def exporter(self, lid: uuid.UUID) -> bytes:
        lot = await self._charger(lid)
        entetes = colonnes_export(lot.type, lot.entetes or [])
        lignes = []
        for x in await self._lignes(lid):
            if lot.type == "LISTE":
                lignes.append(ligne_export_hebdo(x.donnees, racine=x.racine_client or x.brut, nom=x.nom))
            else:
                d = x.donnees or {}
                lignes.append([d.get(e) for e in entetes])
        return build_styled_workbook_multi(
            report_title="Lot de classification",
            sheets=[("CLIENTS", lot.fichier_nom, entetes, lignes)],
            subtitle=None,
        )
