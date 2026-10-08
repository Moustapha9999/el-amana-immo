"""Import de l'État des comptes ORION : analyse → aperçu → confirmation SQL.

Rien n'est écrit dans ``clientele_clients`` / ``clientele_comptes`` avant confirmation.
L'import ne supprime jamais un client existant. Les lignes de staging valides sont
purgées après import (minimisation) ; les anomalies restent.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import (
    ClienteleImport,
    ClienteleImportAnomalie,
    ClienteleImportLigne,
    User,
)
from app.services.clientele.consolidation import (
    COLONNES_OBLIGATOIRES,
    LIBELLES_COLONNES,
    SYNONYMES_COLONNES,
    Anomalie,
    normaliser_entete,
)
from app.services.clientele.lecture import AnalyseClasseur, lire_classeur
from app.services.clientele.persistance import enregistrer_depuis_staging
from app.services.clientele.snapshots import photographier_import
from app.services.clientele.service import Ctx, ClienteleService, conflit, maintenant

TAILLE_MAX = 40 * 1024 * 1024
LOT_STAGING = 2000
ENTETES_CLASSEUR_SITUATION = {"PROFIL ORION RETRAITE", "PROFIL POINTAGE STAGIAIRE", "CLASSE RISQUE LBC FT"}


def _est_classeur_situation(a: AnalyseClasseur) -> bool:
    if "COMPTE" not in a.colonnes_manquantes:
        return False
    return any(normaliser_entete(e) in ENTETES_CLASSEUR_SITUATION for e in a.colonnes_ignorees)


class ClienteleImportService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    def _dossier(self) -> Path:
        p = Path(get_settings().upload_dir) / "clientele"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _chemin(self, iid: uuid.UUID) -> Path:
        return self._dossier() / f"{iid}.xlsx"

    def _effacer_fichier(self, iid: uuid.UUID) -> None:
        path = self._chemin(iid)
        if path.exists():
            path.unlink()

    async def analyser(self, contenu: bytes, nom_fichier: str,
                       mapping: dict[str, str] | None = None) -> dict:
        self.ctx.exiger("clientele.import.execute")
        if not contenu:
            raise AppError("Fichier vide", 422, code="FICHIER_VIDE")
        if len(contenu) > TAILLE_MAX:
            raise AppError("Fichier trop volumineux (40 Mo maximum)", 413, code="FICHIER_TROP_VOLUMINEUX")
        if not nom_fichier.lower().endswith((".xlsx", ".xlsm")):
            raise AppError("Format non pris en charge : enregistrez le fichier au format .xlsx", 422,
                           code="FORMAT_NON_SUPPORTE")
        sha = hashlib.sha256(contenu).hexdigest()
        try:
            analyse_classeur = lire_classeur(contenu, mapping)
        except ValueError as exc:
            if str(exc) == "COLONNES_NON_RECONNUES":
                raise AppError(
                    "Colonnes non reconnues : le fichier doit contenir au moins CLIENT, COMPTE, RIB, "
                    "CODE_AGENCE_COMPTE, RAISON_SOCIAL, ETAT_COMPTE et DEVISE",
                    422, code="COLONNES_NON_RECONNUES") from exc
            raise AppError("Fichier Excel illisible ou corrompu", 422, code="FICHIER_ILLISIBLE") from exc
        except Exception as exc:
            raise AppError("Fichier Excel illisible ou corrompu", 422, code="FICHIER_ILLISIBLE") from exc
        if _est_classeur_situation(analyse_classeur):
            raise AppError(
                "Ce fichier est le classeur Conformité « Situation des comptes PP et PM » (une ligne par "
                "client, sans COMPTE ni RIB), pas l'État des comptes ORION. Utilisez l'option "
                "« Situation des comptes PP & PM » de l'écran Importer.",
                422, code="CLASSEUR_SITUATION")

        precedent = await self.db.scalar(
            select(ClienteleImport).where(
                ClienteleImport.fichier_sha256 == sha, ClienteleImport.statut == "IMPORTE")
            .order_by(ClienteleImport.importe_le.desc()).limit(1))

        imp = ClienteleImport(
            fichier_nom=nom_fichier[:255], fichier_sha256=sha, statut="ANALYSE",
            created_by_id=self.ctx.user.id)
        self.db.add(imp)
        await self.db.flush()
        self._chemin(imp.id).write_bytes(contenu)
        await self._remplir(imp, analyse_classeur, precedent)
        await self.svc.audit("clientele.import.analyse", "clientele_import", imp.id,
                             after={"fichier": nom_fichier, **(imp.analyse or {}).get("stats", {})})
        return await self._import_dict(imp, avec_analyse=True)

    async def recartographier(self, iid: uuid.UUID, mapping: dict[str, str]) -> dict:
        self.ctx.exiger("clientele.import.execute")
        imp = await self.db.scalar(select(ClienteleImport).where(ClienteleImport.id == iid).with_for_update())
        if not imp:
            raise AppError("Import introuvable", 404, code="NOT_FOUND")
        if imp.statut != "ANALYSE":
            raise conflit("Cet import n'est plus en attente", "IMPORT_TERMINE")
        path = self._chemin(imp.id)
        if not path.exists():
            raise AppError("Fichier d'analyse introuvable ; relancez l'upload", 409, code="FICHIER_ABSENT")
        contenu = path.read_bytes()
        try:
            analyse_classeur = lire_classeur(contenu, mapping)
        except Exception as exc:
            raise AppError("Nouveau mapping illisible", 422, code="MAPPING_INVALIDE") from exc
        await self.db.execute(delete(ClienteleImportLigne).where(ClienteleImportLigne.import_id == iid))
        await self.db.execute(delete(ClienteleImportAnomalie).where(ClienteleImportAnomalie.import_id == iid))
        precedent = await self.db.scalar(
            select(ClienteleImport).where(
                ClienteleImport.fichier_sha256 == imp.fichier_sha256,
                ClienteleImport.statut == "IMPORTE",
                ClienteleImport.id != iid,
            ).order_by(ClienteleImport.importe_le.desc()).limit(1))
        await self._remplir(imp, analyse_classeur, precedent)
        await self.svc.audit("clientele.import.mapping", "clientele_import", imp.id, after={"mapping": mapping})
        return await self._import_dict(imp, avec_analyse=True)

    async def _remplir(self, imp: ClienteleImport, a: AnalyseClasseur,
                       precedent: ClienteleImport | None) -> None:
        cons = a.consolidation
        anomalies = list(a.rejets) + list(cons.anomalies)
        if a.colonnes_manquantes:
            anomalies.append(Anomalie(
                1, None, "COLONNE_MANQUANTE",
                "colonnes obligatoires absentes : " + ", ".join(a.colonnes_manquantes), True))
        for extra in a.colonnes_ignorees:
            anomalies.append(Anomalie(1, None, "COLONNE_SUPPLEMENTAIRE", f"colonne ignorée : {extra}", False))

        await self._ecrire_staging(imp.id, a)
        await self._marquer_agences(imp.id, anomalies)
        await self._marquer_rattachements(imp.id, anomalies)

        for anom in anomalies:
            self.db.add(ClienteleImportAnomalie(
                import_id=imp.id, numero=anom.numero, racine_client=anom.racine_client,
                code=anom.code, message=anom.message, bloquante=anom.bloquante))
        await self.db.flush()

        rejets = (await self.db.scalar(
            select(func.count()).select_from(ClienteleImportLigne).where(
                ClienteleImportLigne.import_id == imp.id, ClienteleImportLigne.statut_ligne == "REJETEE"))) or 0
        valides = (await self.db.scalar(
            select(func.count()).select_from(ClienteleImportLigne).where(
                ClienteleImportLigne.import_id == imp.id, ClienteleImportLigne.statut_ligne == "VALIDE"))) or 0
        nb_clients = (await self.db.scalar(text("""
            SELECT count(DISTINCT racine_client) FROM clientele_import_lignes
            WHERE import_id = :iid AND statut_ligne = 'VALIDE' AND racine_client IS NOT NULL
        """), {"iid": imp.id})) or 0
        nb_comptes = (await self.db.scalar(text("""
            SELECT count(DISTINCT compte) FROM clientele_import_lignes
            WHERE import_id = :iid AND statut_ligne = 'VALIDE' AND compte IS NOT NULL
        """), {"iid": imp.id})) or 0
        apercu = await self._apercu_ecriture(imp.id)

        par_code = Counter(x.code for x in anomalies)
        imp.nb_lignes = a.nb_lues
        imp.nb_clients = int(nb_clients)
        imp.nb_comptes = int(nb_comptes)
        imp.nb_rejets = int(rejets)
        imp.nb_anomalies = len(anomalies)
        imp.analyse = {
            "feuille": a.feuille,
            "ligne_entete": a.ligne_entete,
            "mapping": a.mapping,
            "colonnes": [{"champ": c, "libelle": LIBELLES_COLONNES.get(c, c), "entete": a.mapping[c],
                          "obligatoire": c in COLONNES_OBLIGATOIRES} for c in a.mapping],
            "colonnes_ignorees": a.colonnes_ignorees,
            "colonnes_manquantes": a.colonnes_manquantes,
            "champs_disponibles": list(SYNONYMES_COLONNES),
            "apercu": a.apercu,
            "stats": {
                "lignes_lues": a.nb_lues,
                "lignes_vides": a.nb_vides,
                "lignes_valides": int(valides),
                "lignes_rejetees": int(rejets),
                "clients": int(nb_clients),
                "comptes": int(nb_comptes),
                "rib": cons.nb_rib,
                "anomalies": len(anomalies),
                "anomalies_bloquantes": sum(1 for x in anomalies if x.bloquante),
                "par_code": dict(par_code),
            },
            "apercu_ecriture": apercu,
            "deja_importe": (
                {"id": str(precedent.id),
                 "le": precedent.importe_le.isoformat() if precedent.importe_le else None}
                if precedent else None),
        }
        await self.db.flush()

    async def _ecrire_staging(self, iid: uuid.UUID, a: AnalyseClasseur) -> None:
        racines_bloquees = {x.racine_client for x in a.consolidation.anomalies
                            if x.bloquante and x.code == "CLIENT_INCOHERENT" and x.racine_client}
        lignes_bloquees = {x.numero for x in a.consolidation.anomalies
                           if x.bloquante and x.code in ("COMPTE_DUPLIQUE", "RIB_DUPLIQUE")}
        lot: list[dict] = []
        for rej in a.rejets:
            lot.append({
                "id": uuid.uuid4(), "import_id": iid, "numero_ligne": rej.numero,
                "statut_ligne": "REJETEE", "motifs": rej.message,
            })
        for ligne in a.lignes:
            client, compte = ligne.client, ligne.compte
            if ligne.numero in lignes_bloquees or client.racine_client in racines_bloquees:
                motif = "anomalie bloquante de consolidation"
                if client.racine_client in racines_bloquees:
                    motif = "données client incohérentes d'un compte à l'autre"
                lot.append({
                    "id": uuid.uuid4(), "import_id": iid, "numero_ligne": ligne.numero,
                    "statut_ligne": "REJETEE", "motifs": motif,
                    "racine_client": client.racine_client, "compte": compte.compte, "rib": compte.rib,
                })
                continue
            lot.append({
                "id": uuid.uuid4(), "import_id": iid, "numero_ligne": ligne.numero,
                "statut_ligne": "VALIDE",
                "racine_client": client.racine_client, "raison_sociale": client.raison_sociale,
                "prenoms": client.prenoms, "date_naissance": client.date_naissance,
                "date_naissance_orion": client.date_naissance_orion, "nationalite": client.nationalite,
                "statut_resident": client.statut_resident, "agent_economique": client.agent_economique,
                "situation_juridique": client.situation_juridique,
                "categorie_juridique": client.categorie_juridique,
                "secteur_activite": client.secteur_activite,
                "famille_secteur_activite": client.famille_secteur_activite,
                "type_identifiant": client.type_identifiant, "identifiant_orion": client.identifiant_orion,
                "nni": client.nni, "nif": client.nif, "rcs": client.rcs,
                "compte": compte.compte, "rib": compte.rib, "code_agence": compte.code_agence,
                "etat_compte": compte.etat_compte, "devise": compte.devise, "ncg": compte.ncg,
                "rubrique_comptable": compte.rubrique_comptable, "date_ouverture": compte.date_ouverture,
                "ddc": compte.ddc, "ddd": compte.ddd, "conformite_compte": compte.conformite_compte,
                "liste_interdiction": compte.liste_interdiction,
            })
        await self._flush_lot(lot)

    async def _flush_lot(self, lot: list[dict]) -> None:
        if not lot:
            return
        await self.db.flush()
        table = ClienteleImportLigne.__table__
        colonnes = [c.name for c in table.columns]
        conn = await self.db.connection()
        brute = (await conn.get_raw_connection()).driver_connection
        if hasattr(brute, "copy_records_to_table"):
            await brute.copy_records_to_table(
                table.name, columns=colonnes,
                records=[tuple(row.get(c) for c in colonnes) for row in lot])
            return
        for i in range(0, len(lot), LOT_STAGING):
            await self.db.execute(insert(table), lot[i:i + LOT_STAGING])

    async def _marquer_agences(self, iid: uuid.UUID, anomalies: list[Anomalie]) -> None:
        rows = (await self.db.execute(text("""
            SELECT DISTINCT l.numero_ligne, l.code_agence, l.racine_client
            FROM clientele_import_lignes l
            WHERE l.import_id = :iid AND l.statut_ligne = 'VALIDE'
              AND l.code_agence IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM agences a WHERE a.code = l.code_agence)
        """), {"iid": iid})).all()
        if not rows:
            return
        numeros = [r[0] for r in rows]
        await self.db.execute(
            update(ClienteleImportLigne)
            .where(ClienteleImportLigne.import_id == iid, ClienteleImportLigne.numero_ligne.in_(numeros))
            .values(statut_ligne="REJETEE", motifs="agence inconnue"))
        for numero, code, racine in rows:
            anomalies.append(Anomalie(numero, racine, "AGENCE_INCONNUE", f"agence inconnue : {code}", True))

    async def _marquer_rattachements(self, iid: uuid.UUID, anomalies: list[Anomalie]) -> None:
        rows = (await self.db.execute(text("""
            SELECT l.numero_ligne, l.compte, l.racine_client, c.racine_client
            FROM clientele_import_lignes l
            JOIN clientele_comptes c ON c.compte = l.compte
            WHERE l.import_id = :iid AND l.statut_ligne = 'VALIDE'
              AND c.racine_client <> l.racine_client
        """), {"iid": iid})).all()
        if not rows:
            return
        numeros = [r[0] for r in rows]
        await self.db.execute(
            update(ClienteleImportLigne)
            .where(ClienteleImportLigne.import_id == iid, ClienteleImportLigne.numero_ligne.in_(numeros))
            .values(statut_ligne="REJETEE", motifs="compte déjà rattaché à un autre client"))
        for numero, compte, racine, ancienne in rows:
            anomalies.append(Anomalie(
                numero, racine, "COMPTE_AUTRE_CLIENT",
                f"compte {compte} déjà rattaché au client {ancienne}, pas à {racine}", True))

    async def _apercu_ecriture(self, iid: uuid.UUID) -> dict:
        clients = (await self.db.execute(text("""
            SELECT
              count(*) FILTER (WHERE c.id IS NULL)::int AS crees,
              count(*) FILTER (WHERE c.id IS NOT NULL)::int AS maj
            FROM (
              SELECT DISTINCT racine_client FROM clientele_import_lignes
              WHERE import_id = :iid AND statut_ligne = 'VALIDE' AND racine_client IS NOT NULL
            ) s
            LEFT JOIN clientele_clients c ON c.racine_client = s.racine_client
        """), {"iid": iid})).one()
        comptes = (await self.db.execute(text("""
            SELECT
              count(*) FILTER (WHERE c.id IS NULL)::int AS crees,
              count(*) FILTER (WHERE c.id IS NOT NULL)::int AS maj
            FROM (
              SELECT DISTINCT compte FROM clientele_import_lignes
              WHERE import_id = :iid AND statut_ligne = 'VALIDE' AND compte IS NOT NULL
            ) s
            LEFT JOIN clientele_comptes c ON c.compte = s.compte
        """), {"iid": iid})).one()
        absents = (await self.db.scalar(text("""
            SELECT count(*)::int FROM clientele_comptes e
            WHERE e.racine_client IN (
                SELECT DISTINCT racine_client FROM clientele_import_lignes
                WHERE import_id = :iid AND statut_ligne = 'VALIDE' AND racine_client IS NOT NULL
            )
            AND NOT EXISTS (
                SELECT 1 FROM clientele_import_lignes l
                WHERE l.import_id = :iid AND l.statut_ligne = 'VALIDE' AND l.compte = e.compte
            )
        """), {"iid": iid})) or 0
        return {
            "clients_a_creer": clients[0], "clients_a_mettre_a_jour": clients[1],
            "comptes_a_creer": comptes[0], "comptes_a_mettre_a_jour": comptes[1],
            "comptes_absents_du_fichier": int(absents),
        }

    async def lister(self) -> list[dict]:
        rows = (await self.db.execute(
            select(ClienteleImport, User.full_name)
            .outerjoin(User, User.id == ClienteleImport.created_by_id)
            .order_by(ClienteleImport.created_at.desc()).limit(100)
        )).all()
        return [await self._import_dict(i, auteur=n) for i, n in rows]

    async def detail(self, iid: uuid.UUID) -> dict:
        imp = await self.db.get(ClienteleImport, iid)
        if not imp:
            raise AppError("Import introuvable", 404, code="NOT_FOUND")
        return await self._import_dict(imp, avec_analyse=True)

    async def anomalies(self, iid: uuid.UUID, *, code: str | None = None, bloquante: bool | None = None,
                        page: int = 1, taille: int = 100) -> dict:
        if not await self.db.get(ClienteleImport, iid):
            raise AppError("Import introuvable", 404, code="NOT_FOUND")
        q = select(ClienteleImportAnomalie).where(ClienteleImportAnomalie.import_id == iid)
        if code:
            q = q.where(ClienteleImportAnomalie.code == code)
        if bloquante is not None:
            q = q.where(ClienteleImportAnomalie.bloquante == bloquante)
        total = await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = list((await self.db.scalars(
            q.order_by(ClienteleImportAnomalie.bloquante.desc(), ClienteleImportAnomalie.numero)
            .offset((page - 1) * taille).limit(taille)
        )).all())
        return {
            "total": int(total), "page": page, "taille": taille,
            "items": [{"numero": r.numero, "racine_client": r.racine_client, "code": r.code,
                       "message": r.message, "bloquante": r.bloquante} for r in rows],
        }

    async def exporter_anomalies(self, iid: uuid.UUID) -> bytes:
        imp = await self.db.get(ClienteleImport, iid)
        if not imp:
            raise AppError("Import introuvable", 404, code="NOT_FOUND")
        rows = list((await self.db.scalars(
            select(ClienteleImportAnomalie).where(ClienteleImportAnomalie.import_id == iid)
            .order_by(ClienteleImportAnomalie.numero)
        )).all())
        wb = Workbook()
        ws = wb.active
        ws.title = "Anomalies"
        ws.append(["Ligne", "Racine", "Code", "Bloquante", "Message"])
        for r in rows:
            ws.append([r.numero, r.racine_client or "", r.code, "oui" if r.bloquante else "non", r.message])
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    async def confirmer(self, iid: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.import.execute")
        imp = await self.db.scalar(select(ClienteleImport).where(ClienteleImport.id == iid).with_for_update())
        if not imp:
            raise AppError("Import introuvable", 404, code="NOT_FOUND")
        if imp.statut != "ANALYSE":
            raise conflit("Cet import a déjà été confirmé ou abandonné", "IMPORT_TERMINE")
        a = imp.analyse or {}
        if a.get("deja_importe") and not payload.get("forcer"):
            raise conflit("Ce fichier a déjà été importé. Cochez la confirmation pour l'importer de nouveau "
                          "(les clients existants ne sont pas dupliqués ni supprimés).", "FICHIER_DEJA_IMPORTE")
        if a.get("colonnes_manquantes"):
            raise AppError("Colonnes obligatoires manquantes : corrigez le mapping", 422,
                           code="COLONNES_MANQUANTES")
        valides = (await self.db.scalar(select(func.count()).select_from(ClienteleImportLigne).where(
            ClienteleImportLigne.import_id == iid, ClienteleImportLigne.statut_ligne == "VALIDE"))) or 0
        if not valides:
            raise AppError("Aucune ligne valide à importer", 422, code="AUCUNE_LIGNE_VALIDE")
        extraction = payload.get("date_extraction")
        if isinstance(extraction, str):
            extraction = date.fromisoformat(extraction)
        if not isinstance(extraction, date):
            extraction = date.today()
        bilan = await enregistrer_depuis_staging(self.db, iid, extraction)
        await photographier_import(self.db, iid)
        imp.statut = "IMPORTE"
        imp.date_extraction = extraction
        imp.importe_le = maintenant()
        imp.importe_par_id = self.ctx.user.id
        imp.clients_crees = bilan.clients_crees
        imp.clients_maj = bilan.clients_mis_a_jour
        imp.comptes_crees = bilan.comptes_crees
        imp.comptes_maj = bilan.comptes_mis_a_jour
        imp.resultat = {
            "clients_crees": bilan.clients_crees, "clients_mis_a_jour": bilan.clients_mis_a_jour,
            "comptes_crees": bilan.comptes_crees, "comptes_mis_a_jour": bilan.comptes_mis_a_jour,
            "rejets": imp.nb_rejets, "anomalies": imp.nb_anomalies,
        }
        await self.db.execute(delete(ClienteleImportLigne).where(
            ClienteleImportLigne.import_id == iid, ClienteleImportLigne.statut_ligne == "VALIDE"))
        self._effacer_fichier(iid)
        await self.db.flush()
        await self.svc.audit("clientele.import.confirmer", "clientele_import", imp.id, after=imp.resultat)
        return await self._import_dict(imp, avec_analyse=True)

    async def abandonner(self, iid: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.import.execute")
        imp = await self.db.get(ClienteleImport, iid)
        if not imp:
            raise AppError("Import introuvable", 404, code="NOT_FOUND")
        if imp.statut != "ANALYSE":
            raise conflit("Cet import n'est plus en attente", "IMPORT_TERMINE")
        imp.statut = "ABANDONNE"
        await self.db.execute(delete(ClienteleImportLigne).where(ClienteleImportLigne.import_id == iid))
        self._effacer_fichier(iid)
        await self.db.flush()
        await self.svc.audit("clientele.import.abandon", "clientele_import", imp.id,
                             after={"fichier": imp.fichier_nom})
        return await self._import_dict(imp)

    async def supprimer(self, iid: uuid.UUID) -> None:
        self.ctx.exiger("clientele.admin")
        imp = await self.db.get(ClienteleImport, iid)
        if not imp:
            raise AppError("Import introuvable", 404, code="NOT_FOUND")
        avant = {"fichier": imp.fichier_nom, "statut": imp.statut, "lignes": imp.nb_lignes,
                 "resultat": imp.resultat}
        self._effacer_fichier(iid)
        await self.db.delete(imp)
        await self.db.flush()
        await self.svc.audit("clientele.import.delete", "clientele_import", iid, before=avant)

    async def _import_dict(self, imp: ClienteleImport, *, avec_analyse: bool = False,
                           auteur: str | None = None) -> dict:
        out = {
            "id": str(imp.id), "fichier_nom": imp.fichier_nom, "fichier_sha256": imp.fichier_sha256,
            "statut": imp.statut, "date_extraction": imp.date_extraction.isoformat() if imp.date_extraction else None,
            "nb_lignes": imp.nb_lignes, "nb_clients": imp.nb_clients, "nb_comptes": imp.nb_comptes,
            "nb_rejets": imp.nb_rejets, "nb_anomalies": imp.nb_anomalies,
            "clients_crees": imp.clients_crees, "clients_maj": imp.clients_maj,
            "comptes_crees": imp.comptes_crees, "comptes_maj": imp.comptes_maj,
            "created_at": imp.created_at.isoformat() if imp.created_at else None,
            "importe_le": imp.importe_le.isoformat() if imp.importe_le else None,
            "resultat": imp.resultat, "auteur": auteur, "stats": (imp.analyse or {}).get("stats"),
        }
        if avec_analyse:
            out["analyse"] = imp.analyse
        return out
