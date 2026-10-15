"""Import Excel des opérations d'un dossier : modèle unique, analyse (aperçu), confirmation.

Une ligne = une opération (client, compte, référence, date, montant, montant contesté, motif).
L'analyse ne modifie pas le dossier : le fichier est conservé en GED (traçabilité), les lignes
contrôlées sont stockées sur l'import avec leurs erreurs / avertissements, les groupes par client
puis par compte et les totaux. La confirmation rejoue les contrôles sur l'état courant du dossier
(un autre utilisateur a pu le modifier) et n'écrit rien tant qu'une ligne est en erreur.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReclamationDocument, ReclamationImport
from app.models.reclamations import MODES_IMPORT
from app.services.ged_service import GedService
from app.services.reclamations import constantes as C
from app.services.reclamations import operations as ops
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.dossiers import _evenement, charger, peut_modifier, voit_tous_clients
from app.services.reclamations.outils import (
    auditer,
    conflit,
    erreur,
    iso,
    maintenant,
    noms_utilisateurs,
    texte_long,
)

COLONNES: list[tuple[str, str, str]] = [
    ("client_racine", "Identifiant client", "Racine client (6 chiffres). Vide : titulaire du compte, sinon client du dossier."),
    ("compte_reference", "Référence du compte", "Numéro de compte (11 chiffres) ou RIB. Vide : compte « à renseigner »."),
    ("reference", "Référence de l'opération", "Obligatoire. Une même référence peut revenir dans un autre contexte."),
    ("date_operation", "Date de l'opération", "JJ/MM/AAAA. Facultative, jamais dans le futur."),
    ("montant", "Montant de l'opération", "Obligatoire, strictement positif, deux décimales au plus."),
    ("montant_conteste", "Montant contesté", "Facultatif ; par défaut le montant de l'opération. Jamais supérieur."),
    ("motif_detail", "Motif détaillé", "Facultatif : précision propre à cette opération."),
]

_ALIAS: dict[str, tuple[str, ...]] = {
    "client_racine": ("identifiant client", "racine client", "racine", "client", "id client"),
    "compte_reference": ("reference du compte", "numero de compte", "compte", "rib", "ref compte"),
    "reference": ("reference de l operation", "reference operation", "ref operation", "reference"),
    "date_operation": ("date de l operation", "date operation", "date"),
    "montant": ("montant de l operation", "montant operation", "montant"),
    "montant_conteste": ("montant conteste",),
    "motif_detail": ("motif detaille", "motif", "commentaire"),
}
FEUILLE = "Opérations"
LIGNES_ENTETE_MAX = 10
EXTENSIONS = (".xlsx",)


def _cle(texte: Any) -> str:
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# ------------------------------------------------------------------ modèle
def modele() -> bytes:
    """Classeur vierge : feuille « Opérations » (en-têtes seuls) + feuille « Consignes »."""
    wb = Workbook()
    ws = wb.active
    ws.title = FEUILLE
    entete = PatternFill("solid", fgColor="1F4E78")
    for i, (champ, libelle, _aide) in enumerate(COLONNES, start=1):
        c = ws.cell(row=1, column=i, value=libelle)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = entete
        c.alignment = Alignment(vertical="center", wrap_text=True)
        lettre = get_column_letter(i)
        ws.column_dimensions[lettre].width = 40 if champ == "motif_detail" else 24
        fmt = {"client_racine": "@", "compte_reference": "@", "reference": "@", "date_operation": "DD/MM/YYYY",
               "montant": "#,##0.00", "montant_conteste": "#,##0.00"}.get(champ)
        if fmt:
            for ligne in range(2, C.MAX_LIGNES_IMPORT + 2):
                ws.cell(row=ligne, column=i).number_format = fmt
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 32

    aide = wb.create_sheet("Consignes")
    aide.column_dimensions["A"].width = 28
    aide.column_dimensions["B"].width = 90
    aide.append(["Import des opérations d'une réclamation"])
    aide["A1"].font = Font(bold=True, size=13)
    aide.append([])
    for texte in (
        "Une ligne par opération, à partir de la ligne 2 de la feuille « Opérations ». Ne pas modifier les en-têtes.",
        f"{C.MAX_LIGNES_IMPORT} opérations au plus par fichier.",
        "Cas normal : un client, un ou plusieurs comptes. Plusieurs clients dans un même dossier : cas "
        "exceptionnel, autorisé par la banque et justifié lors de la confirmation.",
        "Client ou compte inconnu de la base clientèle : accepté, mais « à vérifier ». Information absente : "
        "« à renseigner ». Rien n'est considéré comme vérifié par défaut.",
        "Une ligne strictement identique à une autre (ou à une opération déjà au dossier) est refusée.",
        "Rien n'est enregistré avant la confirmation : l'aperçu présente les erreurs, les avertissements et les totaux.",
    ):
        aide.append(["", texte])
    aide.append([])
    aide.append(["Colonne", "Règle"])
    aide.cell(row=aide.max_row, column=1).font = Font(bold=True)
    aide.cell(row=aide.max_row, column=2).font = Font(bold=True)
    for _champ, libelle, regle in COLONNES:
        aide.append([libelle, regle])
    for row in aide.iter_rows(min_row=1, max_row=aide.max_row):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ lecture
def lire_classeur(contenu: bytes) -> list[tuple[int, dict]]:
    """(n° de ligne Excel, valeurs brutes) des lignes non vides de la feuille des opérations."""
    try:
        wb = load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
    except Exception:
        raise erreur("Fichier Excel illisible : utilisez le modèle (.xlsx)", "FICHIER_ILLISIBLE") from None
    try:
        ws = wb[FEUILLE] if FEUILLE in wb.sheetnames else wb.worksheets[0]
        lignes = ws.iter_rows(values_only=True)
        colonnes: dict[str, int] | None = None
        numero = 0
        for numero, valeurs in enumerate(lignes, start=1):
            colonnes = _entetes(valeurs)
            if colonnes or numero >= LIGNES_ENTETE_MAX:
                break
        if not colonnes or "reference" not in colonnes or "montant" not in colonnes:
            raise erreur("En-têtes introuvables : la feuille doit contenir au moins « Référence de l'opération » "
                         "et « Montant de l'opération » (téléchargez le modèle)", "ENTETES_MANQUANTES")
        resultat: list[tuple[int, dict]] = []
        for rang, valeurs in enumerate(lignes, start=numero + 1):
            brut = {champ: valeurs[i] if i < len(valeurs) else None for champ, i in colonnes.items()}
            if all(v is None or (isinstance(v, str) and not v.strip()) for v in brut.values()):
                continue
            resultat.append((rang, brut))
            if len(resultat) > C.MAX_LIGNES_IMPORT:
                raise erreur(f"{C.MAX_LIGNES_IMPORT} opérations au plus par fichier", "TROP_D_OPERATIONS")
    finally:
        wb.close()
    if not resultat:
        raise erreur("Le fichier ne contient aucune opération", "FICHIER_VIDE")
    return resultat


def _entetes(valeurs: tuple) -> dict[str, int]:
    trouves: dict[str, int] = {}
    cles = [_cle(v) for v in valeurs]
    for champ, alias in _ALIAS.items():
        for a in alias:
            if a in cles and cles.index(a) not in trouves.values():
                trouves[champ] = cles.index(a)
                break
    return trouves if len(trouves) >= 2 else {}


# ------------------------------------------------------------------ analyse
def _autoriser(s: ReclamationsScope, r) -> None:
    if not peut_modifier(s, r):
        if r.statut in C.STATUTS_TERMINAUX or r.archivee_le:
            raise conflit("Dossier terminé : il n'est plus modifiable", "DOSSIER_TERMINE")
        s.exiger("reclamations.update")
    if not voit_tous_clients(s, r):
        raise erreur("Ce dossier concerne des clients que vous ne pouvez pas consulter", "PERMISSION_DENIED", 403)


async def _controler(db: AsyncSession, r, lignes: list[ops.Ligne], mode: str) -> list[ops.Ligne]:
    """Contrôles complets sur l'état courant ; renvoie les opérations du dossier conservées."""
    if mode == "AJOUT":
        actuelles = await ops.lister(db, r.id)
        par_p = {p.id: p for p in await ops.participants(db, r.id)}
        par_c = {c.id: c for c in await ops.comptes(db, r.id)}
        existantes = ops.lignes_existantes(actuelles, par_p, par_c)
        rattachement = await ops.comptes_du_dossier(db, r.id)
    else:
        existantes = []
        rattachement = {r.compte_reference: r.client_racine} if r.compte_reference else {}
    await ops.resoudre(db, lignes, r.client_racine, rattachement)
    ops.controler(lignes, existantes)
    return existantes


def _synthese(r, lignes: list[ops.Ligne], conservees: list[ops.Ligne], autorise: bool) -> dict:
    """Groupes client → compte, totaux du fichier et du dossier après import."""
    valides = [lg for lg in lignes if not lg.erreurs]
    groupes: dict[str | None, dict[str | None, list[ops.Ligne]]] = defaultdict(lambda: defaultdict(list))
    for lg in lignes:
        groupes[lg.client_racine][lg.compte_reference].append(lg)

    def totaux(liste: list[ops.Ligne]) -> dict:
        ok = [lg for lg in liste if not lg.erreurs]
        return {"nb": len(liste), "nb_erreurs": len(liste) - len(ok),
                "montant": ops.montant_str(ops.total([lg.montant for lg in ok])),
                "montant_conteste": ops.montant_str(ops.total([ops.conteste(lg) for lg in ok]))}

    clients = []
    for racine, par_compte in sorted(groupes.items(), key=lambda x: (x[0] != r.client_racine, x[0] or "~")):
        toutes = [lg for liste in par_compte.values() for lg in liste]
        premiere = next((lg for lg in toutes if lg.client_nom), toutes[0])
        clients.append({
            "racine": racine, "nom": premiere.client_nom if premiere.client_nom else (
                r.client_nom if racine and racine == r.client_racine else None),
            "principal": racine == r.client_racine, "statut": premiere.statut_client or "A_RENSEIGNER",
            **totaux(toutes),
            "comptes": [{"compte_reference": compte, "statut": liste[0].statut_compte or "A_RENSEIGNER",
                         **totaux(liste)}
                        for compte, liste in sorted(par_compte.items(), key=lambda x: x[0] or "~")],
        })
    racines = {lg.client_racine for lg in valides + conservees if lg.client_racine}
    if r.client_racine:
        racines.add(r.client_racine)
    multi = len(racines) > 1
    apres = conservees + valides
    return {
        "lignes": [lg.apercu() for lg in lignes],
        "clients": clients,
        "totaux": totaux(lignes),
        "nb_clients": len(racines), "multi_clients": multi, "regroupement_autorise": autorise,
        "justification_requise": multi and not r.justification_regroupement,
        "justification_actuelle": r.justification_regroupement,
        "apres_import": {"nb": len(apres), "montant": ops.montant_str(ops.total([lg.montant for lg in apres])),
                         "montant_conteste": ops.montant_str(ops.total([ops.conteste(lg) for lg in apres]))},
        "nb_conservees": len(conservees),
    }


async def analyser(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, fichier: UploadFile, mode: str) -> dict:
    if mode not in MODES_IMPORT:
        raise erreur("Mode d'import inconnu", "MODE_INVALIDE")
    nom = Path(fichier.filename or "").name
    if Path(nom).suffix.lower() not in EXTENSIONS:
        raise erreur("Format attendu : classeur Excel .xlsx (téléchargez le modèle)", "FORMAT_IMPORT")
    r = await charger(db, s, rid, verrou=True)
    _autoriser(s, r)
    contenu = await fichier.read()
    lignes = [ops.lire(brut, rang) for rang, brut in lire_classeur(contenu)]
    conservees = await _controler(db, r, lignes, mode)
    resultat = _synthese(r, lignes, conservees, await ops.regroupement_autorise(db))
    await fichier.seek(0)

    for ancien in (await db.scalars(select(ReclamationImport).where(
            ReclamationImport.reclamation_id == r.id, ReclamationImport.statut == "ANALYSE"))).all():
        ancien.statut = "ABANDONNE"
    doc = await GedService(db).upload(file=fichier, espace_code=C.ESPACE_CODE, module_code=C.MODULE_CODE,
                                      entity=C.GED_ENTITE, entity_id=str(r.id), uploaded_by_id=s.user_id)
    doc.doc_type = "RECLAMATION_IMPORT_OPERATIONS"
    doc.title = f"{C.CATEGORIE_DOCUMENT_LIBELLES['IMPORT_OPERATIONS']} — {r.reference}"[:255]
    doc.reference = r.reference
    doc.date_document = maintenant().date()
    doc.security_level = "restricted"
    doc.ocr_status = "skipped"
    db.add(ReclamationDocument(document_id=doc.id, reclamation_id=r.id, categorie="IMPORT_OPERATIONS",
                               created_by_id=s.user_id))
    nb_err = sum(1 for lg in lignes if lg.erreurs)
    nb_av = sum(1 for lg in lignes if not lg.erreurs and lg.avertissements)
    imp = ReclamationImport(
        reclamation_id=r.id, document_id=doc.id, nom_fichier=nom[:255], empreinte=hashlib.sha256(contenu).hexdigest(),
        statut="ANALYSE", mode=mode, nb_lignes=len(lignes), nb_valides=len(lignes) - nb_err, nb_erreurs=nb_err,
        nb_avertissements=nb_av, resultat=resultat, created_by_id=s.user_id)
    db.add(imp)
    await db.flush()
    db.add(_evenement(r, s, "IMPORT_ANALYSE", statut_avant=r.statut, etape_avant=r.etape,
                      donnees={"fichier": nom, "mode": mode, "lignes": len(lignes), "erreurs": nb_err,
                               "avertissements": nb_av}))
    await db.flush()
    await auditer(db, s, "reclamations.operations.import.analyse", C.GED_ENTITE, r.id, after={
        "import_id": str(imp.id), "document_id": str(doc.id), "fichier": nom, "empreinte": imp.empreinte,
        "mode": mode, "lignes": len(lignes), "erreurs": nb_err, "avertissements": nb_av})
    return await _dict(db, imp, r)


async def _import(db: AsyncSession, rid: uuid.UUID, iid: uuid.UUID) -> ReclamationImport:
    imp = await db.get(ReclamationImport, iid)
    if imp is None or imp.reclamation_id != rid:
        raise erreur("Import introuvable", "NOT_FOUND", 404)
    return imp


async def _dict(db: AsyncSession, imp: ReclamationImport, r) -> dict:
    noms = await noms_utilisateurs(db, {imp.created_by_id, imp.confirme_par_id} - {None})
    return {
        "id": str(imp.id), "reclamation_id": str(r.id), "revision": r.revision,
        "nom_fichier": imp.nom_fichier, "statut": imp.statut, "mode": imp.mode,
        "nb_lignes": imp.nb_lignes, "nb_valides": imp.nb_valides, "nb_erreurs": imp.nb_erreurs,
        "nb_avertissements": imp.nb_avertissements,
        "document_id": str(imp.document_id) if imp.document_id else None,
        "created_at": iso(imp.created_at), "par": noms.get(imp.created_by_id) if imp.created_by_id else None,
        "confirme_le": iso(imp.confirme_le),
        "confirme_par": noms.get(imp.confirme_par_id) if imp.confirme_par_id else None,
        **(imp.resultat or {}),
    }


async def lire(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, iid: uuid.UUID) -> dict:
    r = await charger(db, s, rid)
    if not voit_tous_clients(s, r):
        raise erreur("Ce dossier concerne des clients que vous ne pouvez pas consulter", "PERMISSION_DENIED", 403)
    return await _dict(db, await _import(db, r.id, iid), r)


async def confirmer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, iid: uuid.UUID, data: dict) -> None:
    r = await charger(db, s, rid, verrou=True)
    _autoriser(s, r)
    imp = await _import(db, r.id, iid)
    if imp.statut != "ANALYSE":
        raise conflit("Cet import a déjà été confirmé ou abandonné", "IMPORT_DEJA_TRAITE")
    if data["revision"] != r.revision:
        raise conflit("Le dossier a été modifié depuis l'analyse : relancez l'import", "CONFLIT_REVISION",
                      revision=r.revision)
    lignes = [ops.lire(b, int(b.get("ligne") or 0)) for b in (imp.resultat or {}).get("lignes", [])]
    await _controler(db, r, lignes, imp.mode or "AJOUT")
    en_erreur = [lg for lg in lignes if lg.erreurs]
    if en_erreur:
        lg = en_erreur[0]
        raise erreur(f"{len(en_erreur)} ligne(s) en erreur (ligne {lg.rang} : {lg.erreurs[0][1]}) : corrigez le "
                     "fichier et relancez l'import", "IMPORT_ERREURS")
    if not lignes:
        raise erreur("Aucune opération à importer", "FICHIER_VIDE")
    justification = texte_long(data.get("justification_regroupement"))
    prevus = {lg.client_racine for lg in lignes if lg.client_racine} | ({r.client_racine} if r.client_racine else set())
    if imp.mode != "REMPLACEMENT":
        prevus |= {p.client_racine for p in await ops.participants(db, r.id) if p.client_racine}
    await ops.verifier_regroupement(db, r, justification, prevus)
    actuelles = await ops.lister(db, r.id)
    avant = {"nb": len(actuelles), "total": ops.montant_str(ops.total([o.montant for o in actuelles]))}
    if imp.mode == "REMPLACEMENT":
        for o in actuelles:
            await db.delete(o)
        await db.flush()
    await ops.ecrire(db, r, lignes, s.user_id, import_id=imp.id)
    await ops.nettoyer(db, r)
    multi = await ops.verifier_regroupement(db, r, justification)
    imp.statut, imp.confirme_le, imp.confirme_par_id = "CONFIRME", maintenant(), s.user_id
    r.revision += 1
    r.updated_by_id = s.user_id
    apres_ops = await ops.lister(db, r.id)
    apres = {"nb": len(apres_ops), "total": ops.montant_str(ops.total([o.montant for o in apres_ops]))}
    db.add(_evenement(r, s, "IMPORT_CONFIRME", statut_avant=r.statut, etape_avant=r.etape,
                      donnees={"fichier": imp.nom_fichier, "mode": imp.mode, "importees": len(lignes),
                               "avant": avant, "apres": apres, **({"multi_clients": True} if multi else {})}))
    await db.flush()
    await auditer(db, s, "reclamations.operations.import.confirm", C.GED_ENTITE, r.id, before=avant, after={
        "import_id": str(imp.id), "fichier": imp.nom_fichier, "mode": imp.mode, "importees": len(lignes), **apres,
        **({"justification_regroupement": r.justification_regroupement} if multi else {})})


async def abandonner(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, iid: uuid.UUID) -> dict:
    r = await charger(db, s, rid, verrou=True)
    _autoriser(s, r)
    imp = await _import(db, r.id, iid)
    if imp.statut != "ANALYSE":
        raise conflit("Cet import a déjà été confirmé ou abandonné", "IMPORT_DEJA_TRAITE")
    imp.statut = "ABANDONNE"
    db.add(_evenement(r, s, "IMPORT_ABANDONNE", statut_avant=r.statut, etape_avant=r.etape,
                      donnees={"fichier": imp.nom_fichier}))
    await db.flush()
    await auditer(db, s, "reclamations.operations.import.abandon", C.GED_ENTITE, r.id,
                  after={"import_id": str(imp.id), "fichier": imp.nom_fichier})
    return await _dict(db, imp, r)
