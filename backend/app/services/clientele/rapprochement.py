"""Rapprochement de deux imports ORION (snapshots). Jamais une suppression métier."""

from __future__ import annotations

import uuid
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import (
    ClienteleImport,
    ClienteleImportClient,
    ClienteleRapprochement,
    ClienteleRapprochementEcart,
    User,
)
from app.services.clientele.service import Ctx, ClienteleService
from app.services.reporting_export import build_styled_pdf, build_styled_workbook_multi

CHAMPS_CLIENT = [
    ("raison_sociale", "nom"),
    ("prenoms", "prénoms"),
    ("nationalite", "nationalité"),
    ("statut_resident", "résidence"),
    ("categorie_juridique", "catégorie juridique"),
    ("secteur_activite", "secteur"),
    ("famille_secteur_activite", "famille secteur"),
    ("agent_economique", "agent économique"),
    ("situation_juridique", "situation juridique"),
    ("nni", "NNI"),
    ("nif", "NIF"),
    ("rcs", "RCS"),
    ("type_identifiant", "type identifiant"),
]
CHAMPS_COMPTE = [
    ("compte", "compte"),
    ("code_agence", "agence"),
    ("etat_compte", "état"),
    ("devise", "devise"),
    ("ncg", "NCG"),
    ("conformite_compte", "conformité"),
    ("liste_interdiction", "liste d'interdiction"),
]


class ClienteleRapprochementService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    async def _import_importe(self, iid: uuid.UUID) -> ClienteleImport:
        imp = await self.db.get(ClienteleImport, iid)
        if not imp:
            raise AppError("Import introuvable", 404, code="NOT_FOUND")
        if imp.statut != "IMPORTE":
            raise AppError("Seuls les imports confirmés peuvent être rapprochés", 422,
                           code="IMPORT_NON_CONFIRME")
        return imp

    async def _exiger_snapshot(self, iid: uuid.UUID) -> None:
        n = await self.db.scalar(
            select(func.count()).select_from(ClienteleImportClient)
            .where(ClienteleImportClient.import_id == iid))
        if not n:
            raise AppError(
                "Cet import n'a pas de photographie (imports antérieurs à la phase 4). "
                "Réimportez-le pour pouvoir le rapprocher.",
                422, code="SNAPSHOT_ABSENT")

    async def lister_imports(self) -> list[dict]:
        self.ctx.exiger("clientele.rapprochement.view", "clientele.import.view")
        rows = (await self.db.execute(
            select(ClienteleImport, User.full_name)
            .outerjoin(User, User.id == ClienteleImport.importe_par_id)
            .where(ClienteleImport.statut == "IMPORTE")
            .order_by(ClienteleImport.importe_le.desc()).limit(100)
        )).all()
        out = []
        for imp, nom in rows:
            n = await self.db.scalar(
                select(func.count()).select_from(ClienteleImportClient)
                .where(ClienteleImportClient.import_id == imp.id))
            out.append({
                "id": str(imp.id), "fichier_nom": imp.fichier_nom,
                "date_extraction": imp.date_extraction.isoformat() if imp.date_extraction else None,
                "importe_le": imp.importe_le.isoformat() if imp.importe_le else None,
                "nb_clients": imp.nb_clients, "nb_comptes": imp.nb_comptes,
                "auteur": nom, "snapshot": bool(n),
            })
        return out

    async def lister(self) -> list[dict]:
        self.ctx.exiger("clientele.rapprochement.view")
        rows = (await self.db.execute(
            select(ClienteleRapprochement).order_by(ClienteleRapprochement.created_at.desc()).limit(50)
        )).all()
        out = []
        for (r,) in rows:
            out.append(await self._dict_entete(r))
        return out

    async def calculer(self, import_a_id: uuid.UUID, import_b_id: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.rapprochement.execute")
        if import_a_id == import_b_id:
            raise AppError("Choisissez deux imports distincts", 422, code="IMPORTS_IDENTIQUES")
        await self._import_importe(import_a_id)
        await self._import_importe(import_b_id)
        await self._exiger_snapshot(import_a_id)
        await self._exiger_snapshot(import_b_id)

        existant = await self.db.scalar(
            select(ClienteleRapprochement).where(
                ClienteleRapprochement.import_a_id == import_a_id,
                ClienteleRapprochement.import_b_id == import_b_id).with_for_update())
        if existant:
            await self.db.execute(delete(ClienteleRapprochementEcart).where(
                ClienteleRapprochementEcart.rapprochement_id == existant.id))
            rap = existant
        else:
            rap = ClienteleRapprochement(
                import_a_id=import_a_id, import_b_id=import_b_id, created_by_id=self.ctx.user.id)
            self.db.add(rap)
            await self.db.flush()

        synthese = await self._peupler(rap.id, import_a_id, import_b_id)
        rap.synthese = synthese
        await self.db.flush()
        await self.svc.audit("clientele.rapprochement.calcul", "clientele_rapprochement", rap.id,
                             after={"import_a": str(import_a_id), "import_b": str(import_b_id), **synthese})
        return await self.detail(rap.id)

    async def _peupler(self, rid: uuid.UUID, a: uuid.UUID, b: uuid.UUID) -> dict:
        params = {"rid": rid, "a": a, "b": b}
        await self.db.execute(text("""
            INSERT INTO clientele_rapprochement_ecarts
                (id, rapprochement_id, objet, categorie, racine_client, code)
            SELECT gen_random_uuid(), :rid, 'CLIENT', 'NOUVEAU', b.racine_client, 'CLIENT_NOUVEAU'
            FROM clientele_import_clients b
            WHERE b.import_id = :b AND NOT EXISTS (
                SELECT 1 FROM clientele_import_clients a
                WHERE a.import_id = :a AND a.racine_client = b.racine_client)
        """), params)
        await self.db.execute(text("""
            INSERT INTO clientele_rapprochement_ecarts
                (id, rapprochement_id, objet, categorie, racine_client, code)
            SELECT gen_random_uuid(), :rid, 'CLIENT', 'ABSENT_EXTRACTION', a.racine_client, 'CLIENT_ABSENT'
            FROM clientele_import_clients a
            WHERE a.import_id = :a AND NOT EXISTS (
                SELECT 1 FROM clientele_import_clients b
                WHERE b.import_id = :b AND b.racine_client = a.racine_client)
        """), params)
        for champ, libelle in CHAMPS_CLIENT:
            await self.db.execute(text(f"""
                INSERT INTO clientele_rapprochement_ecarts
                    (id, rapprochement_id, objet, categorie, racine_client, champ, libelle_champ,
                     valeur_a, valeur_b, code)
                SELECT gen_random_uuid(), :rid, 'CLIENT', 'MODIFIE', a.racine_client, :champ, :libelle,
                       a.{champ}::text, b.{champ}::text, 'CLIENT_MODIFIE'
                FROM clientele_import_clients a
                JOIN clientele_import_clients b
                  ON b.import_id = :b AND b.racine_client = a.racine_client
                WHERE a.import_id = :a AND a.{champ} IS DISTINCT FROM b.{champ}
            """), {**params, "champ": champ, "libelle": libelle})

        await self.db.execute(text("""
            INSERT INTO clientele_rapprochement_ecarts
                (id, rapprochement_id, objet, categorie, racine_client, rib, code)
            SELECT gen_random_uuid(), :rid, 'COMPTE', 'NOUVEAU', b.racine_client, b.rib, 'COMPTE_NOUVEAU'
            FROM clientele_import_comptes b
            WHERE b.import_id = :b AND NOT EXISTS (
                SELECT 1 FROM clientele_import_comptes a
                WHERE a.import_id = :a AND a.rib = b.rib)
        """), params)
        await self.db.execute(text("""
            INSERT INTO clientele_rapprochement_ecarts
                (id, rapprochement_id, objet, categorie, racine_client, rib, code)
            SELECT gen_random_uuid(), :rid, 'COMPTE', 'ABSENT_EXTRACTION', a.racine_client, a.rib, 'COMPTE_ABSENT'
            FROM clientele_import_comptes a
            WHERE a.import_id = :a AND NOT EXISTS (
                SELECT 1 FROM clientele_import_comptes b
                WHERE b.import_id = :b AND b.rib = a.rib)
        """), params)
        for champ, libelle in CHAMPS_COMPTE:
            code = "COMPTE_AGENCE" if champ == "code_agence" else (
                "COMPTE_ETAT" if champ == "etat_compte" else (
                    "COMPTE_DEVISE" if champ == "devise" else "COMPTE_MODIFIE"))
            await self.db.execute(text(f"""
                INSERT INTO clientele_rapprochement_ecarts
                    (id, rapprochement_id, objet, categorie, racine_client, rib, champ, libelle_champ,
                     valeur_a, valeur_b, code)
                SELECT gen_random_uuid(), :rid, 'COMPTE', 'MODIFIE', b.racine_client, a.rib, :champ, :libelle,
                       a.{champ}::text, b.{champ}::text, :code
                FROM clientele_import_comptes a
                JOIN clientele_import_comptes b ON b.import_id = :b AND b.rib = a.rib
                WHERE a.import_id = :a AND a.{champ} IS DISTINCT FROM b.{champ}
                  AND a.racine_client = b.racine_client
            """), {**params, "champ": champ, "libelle": libelle, "code": code})
        await self.db.execute(text("""
            INSERT INTO clientele_rapprochement_ecarts
                (id, rapprochement_id, objet, categorie, racine_client, rib, champ, libelle_champ,
                 valeur_a, valeur_b, code)
            SELECT gen_random_uuid(), :rid, 'COMPTE', 'ANOMALIE', a.racine_client, a.rib, 'racine_client',
                   'racine', a.racine_client, b.racine_client, 'RIB_AUTRE_CLIENT'
            FROM clientele_import_comptes a
            JOIN clientele_import_comptes b ON b.import_id = :b AND b.rib = a.rib
            WHERE a.import_id = :a AND a.racine_client IS DISTINCT FROM b.racine_client
        """), params)

        counts = (await self.db.execute(text("""
            SELECT objet, categorie, code, count(*)::int
            FROM clientele_rapprochement_ecarts
            WHERE rapprochement_id = :rid
            GROUP BY objet, categorie, code
        """), {"rid": rid})).all()
        par = {}
        for objet, cat, code, n in counts:
            par.setdefault(objet, {}).setdefault(cat, 0)
            par[objet][cat] += n
            par.setdefault("codes", {})[code] = n

        n_cli_a = await self.db.scalar(select(func.count()).select_from(ClienteleImportClient)
                                       .where(ClienteleImportClient.import_id == a)) or 0
        n_cli_b = await self.db.scalar(select(func.count()).select_from(ClienteleImportClient)
                                       .where(ClienteleImportClient.import_id == b)) or 0
        n_cpt_a = (await self.db.scalar(text(
            "SELECT count(*) FROM clientele_import_comptes WHERE import_id = :i"), {"i": a})) or 0
        n_cpt_b = (await self.db.scalar(text(
            "SELECT count(*) FROM clientele_import_comptes WHERE import_id = :i"), {"i": b})) or 0
        cli_nouv = par.get("CLIENT", {}).get("NOUVEAU", 0)
        cli_abs = par.get("CLIENT", {}).get("ABSENT_EXTRACTION", 0)
        cpt_nouv = par.get("COMPTE", {}).get("NOUVEAU", 0)
        cpt_abs = par.get("COMPTE", {}).get("ABSENT_EXTRACTION", 0)
        fermes = (await self.db.scalar(text("""
            SELECT count(*)::int FROM clientele_rapprochement_ecarts
            WHERE rapprochement_id = :rid AND objet = 'COMPTE' AND champ = 'etat_compte'
              AND valeur_a = 'OUVERT' AND valeur_b = 'FERME'
        """), {"rid": rid})) or 0
        clients_modifies = (await self.db.scalar(text("""
            SELECT count(DISTINCT racine_client)::int FROM clientele_rapprochement_ecarts
            WHERE rapprochement_id = :rid AND objet = 'CLIENT' AND categorie = 'MODIFIE'
        """), {"rid": rid})) or 0
        comptes_modifies = (await self.db.scalar(text("""
            SELECT count(DISTINCT rib)::int FROM clientele_rapprochement_ecarts
            WHERE rapprochement_id = :rid AND objet = 'COMPTE' AND categorie = 'MODIFIE'
        """), {"rid": rid})) or 0
        return {
            "clients_a": int(n_cli_a), "clients_b": int(n_cli_b),
            "comptes_a": int(n_cpt_a), "comptes_b": int(n_cpt_b),
            "clients_nouveaux": cli_nouv,
            "clients_absents": cli_abs,
            "clients_modifies": int(clients_modifies),
            "clients_inchanges": int(n_cli_a) - cli_abs - int(clients_modifies),
            "comptes_nouveaux": cpt_nouv,
            "comptes_absents": cpt_abs,
            "comptes_modifies": int(comptes_modifies),
            "comptes_inchanges": int(n_cpt_a) - cpt_abs - int(comptes_modifies),
            "comptes_fermes": int(fermes),
            "anomalies": par.get("COMPTE", {}).get("ANOMALIE", 0) + par.get("CLIENT", {}).get("ANOMALIE", 0),
            "detail_codes": par.get("codes", {}),
            "regle": "ABSENT_EXTRACTION n'est pas une suppression. Les clients restent en base.",
        }

    async def detail(self, rid: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.rapprochement.view")
        rap = await self.db.get(ClienteleRapprochement, rid)
        if not rap:
            raise AppError("Rapprochement introuvable", 404, code="NOT_FOUND")
        return await self._dict_entete(rap)

    async def ecarts(self, rid: uuid.UUID, *, objet: str | None = None, categorie: str | None = None,
                     champ: str | None = None, q: str | None = None, page: int = 1,
                     taille: int = 80) -> dict:
        self.ctx.exiger("clientele.rapprochement.view")
        if not await self.db.get(ClienteleRapprochement, rid):
            raise AppError("Rapprochement introuvable", 404, code="NOT_FOUND")
        filtres = [ClienteleRapprochementEcart.rapprochement_id == rid]
        if objet:
            filtres.append(ClienteleRapprochementEcart.objet == objet)
        if categorie:
            filtres.append(ClienteleRapprochementEcart.categorie == categorie)
        if champ:
            filtres.append(ClienteleRapprochementEcart.champ == champ)
        if q:
            like = f"%{q.strip()}%"
            filtres.append(or_(ClienteleRapprochementEcart.racine_client.like(like),
                               ClienteleRapprochementEcart.rib.like(like)))
        total = await self.db.scalar(
            select(func.count()).select_from(ClienteleRapprochementEcart).where(*filtres)) or 0
        rows = list((await self.db.scalars(
            select(ClienteleRapprochementEcart).where(*filtres)
            .order_by(ClienteleRapprochementEcart.objet, ClienteleRapprochementEcart.categorie,
                      ClienteleRapprochementEcart.racine_client)
            .offset((page - 1) * max(taille, 1)).limit(min(taille, 500))
        )).all())
        return {
            "total": int(total), "page": page, "taille": taille,
            "items": [self._ecart_dict(r) for r in rows],
        }

    async def exporter_excel(self, rid: uuid.UUID) -> bytes:
        self.ctx.exiger("clientele.rapprochement.view", "clientele.export")
        rap = await self._charger(rid)
        sheets = []
        for titre, cat in (("Nouveaux", "NOUVEAU"), ("Modifiés", "MODIFIE"),
                           ("Absents extraction", "ABSENT_EXTRACTION"), ("Anomalies", "ANOMALIE")):
            rows = await self._toutes_lignes(rid, categorie=cat)
            sheets.append((titre[:31], titre, ["Objet", "Catégorie", "Racine", "RIB", "Champ",
                                               "Import A", "Import B", "Code"], rows))
        synthese = [[k, v] for k, v in (rap.synthese or {}).items() if k != "detail_codes"]
        sheets.insert(0, ("Synthèse", "Synthèse", ["Indicateur", "Valeur"], synthese))
        a, b = await self._noms(rap)
        return build_styled_workbook_multi(
            report_title="Rapprochement imports ORION",
            sheets=sheets,
            subtitle=f"{a}  vs  {b} — absence ≠ suppression",
        )

    async def exporter_pdf(self, rid: uuid.UUID) -> bytes:
        self.ctx.exiger("clientele.rapprochement.view", "clientele.export")
        rap = await self._charger(rid)
        a, b = await self._noms(rap)
        rows = [[k, v] for k, v in (rap.synthese or {}).items() if k != "detail_codes"]
        return build_styled_pdf(
            report_title="Rapprochement imports ORION",
            headers=["Indicateur", "Valeur"],
            rows=rows,
            subtitle=f"{a}  vs  {b} — l'absence d'extraction n'est pas une suppression",
            landscape_mode=False,
        )

    async def _toutes_lignes(self, rid: uuid.UUID, *, categorie: str) -> list[list]:
        rows = list((await self.db.scalars(
            select(ClienteleRapprochementEcart)
            .where(ClienteleRapprochementEcart.rapprochement_id == rid,
                   ClienteleRapprochementEcart.categorie == categorie)
            .order_by(ClienteleRapprochementEcart.objet, ClienteleRapprochementEcart.racine_client)
            .limit(20000)
        )).all())
        return [[r.objet, r.categorie, r.racine_client or "", r.rib or "",
                 r.libelle_champ or r.champ or "", r.valeur_a or "", r.valeur_b or "",
                 r.code or ""] for r in rows]

    async def _charger(self, rid: uuid.UUID) -> ClienteleRapprochement:
        rap = await self.db.get(ClienteleRapprochement, rid)
        if not rap:
            raise AppError("Rapprochement introuvable", 404, code="NOT_FOUND")
        return rap

    async def _noms(self, rap: ClienteleRapprochement) -> tuple[str, str]:
        a = await self.db.get(ClienteleImport, rap.import_a_id)
        b = await self.db.get(ClienteleImport, rap.import_b_id)
        return (a.fichier_nom if a else "A", b.fichier_nom if b else "B")

    async def _dict_entete(self, rap: ClienteleRapprochement) -> dict:
        a = await self.db.get(ClienteleImport, rap.import_a_id)
        b = await self.db.get(ClienteleImport, rap.import_b_id)
        return {
            "id": str(rap.id),
            "import_a": {
                "id": str(rap.import_a_id),
                "fichier_nom": a.fichier_nom if a else None,
                "date_extraction": a.date_extraction.isoformat() if a and a.date_extraction else None,
                "importe_le": a.importe_le.isoformat() if a and a.importe_le else None,
            },
            "import_b": {
                "id": str(rap.import_b_id),
                "fichier_nom": b.fichier_nom if b else None,
                "date_extraction": b.date_extraction.isoformat() if b and b.date_extraction else None,
                "importe_le": b.importe_le.isoformat() if b and b.importe_le else None,
            },
            "synthese": rap.synthese or {},
            "created_at": rap.created_at.isoformat() if rap.created_at else None,
        }

    @staticmethod
    def _ecart_dict(r: ClienteleRapprochementEcart) -> dict:
        return {
            "objet": r.objet, "categorie": r.categorie, "racine_client": r.racine_client,
            "rib": r.rib, "champ": r.champ, "libelle_champ": r.libelle_champ,
            "valeur_a": r.valeur_a, "valeur_b": r.valeur_b, "code": r.code,
        }
