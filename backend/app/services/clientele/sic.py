"""Déclaration SIC : préparation, contrôles, validation, génération et dépôt (saisi manuellement).

Lecture seule sur les données clients : aucune classification, donnée KYC ou compte n'est modifié.
Cycle : BROUILLON → (contrôle) A_CORRIGER / CONTROLEE → VALIDEE_EXPORT → GENEREE → DEPOSEE.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from datetime import date, datetime, timezone

from sqlalchemy import delete, func, insert, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.data.clientele_sic import (
    COLONNES,
    RESULTATS_DEPOT,
    STATUTS_SIC_MODIFIABLES,
    TYPES_SIC,
)
from app.models import ClienteleDeclarationBcm, ClienteleDeclarationSic, ClienteleSicLigne
from app.services.clientele.bcm_referentiel import ClienteleBcmReferentielService
from app.services.clientele.bcm_regles import ClienteleBcmReglesService
from app.services.clientele.service import Ctx, ClienteleService
from app.services.clientele.sic_calcul import (
    A_CORRIGER,
    AVERTISSEMENT,
    BLOQUANTE,
    CandidatSic,
    ContexteSic,
    construire,
    ecrire_xlsx,
    rapport_anomalies_xlsx,
    verifier_xlsx,
)

EER_STATUTS_REALISE = ("VALIDE", "CLOTURE", "ARCHIVE")
LIBELLES_STATUT = {"BROUILLON": "Brouillon", "A_CORRIGER": "À corriger", "CONTROLEE": "Contrôlée",
                   "VALIDEE_EXPORT": "Validée pour export", "GENEREE": "Générée", "DEPOSEE": "Déposée"}

_SQL_CANDIDATS = f"""
WITH eer AS (
    SELECT DISTINCT ON (d.racine_client) d.racine_client, pp.sexe,
           coalesce(nullif(trim(p.telephone_1), ''), nullif(trim(p.telephone_2), ''),
                    nullif(trim(p.telephone_3), '')) AS telephone
    FROM eer_dossiers d
    JOIN eer_parties p ON p.id = d.client_partie_id
    LEFT JOIN eer_parties_physiques pp ON pp.partie_id = p.id
    WHERE d.deleted_at IS NULL AND d.racine_client IS NOT NULL
      AND d.statut IN ({", ".join(f"'{s}'" for s in EER_STATUTS_REALISE)})
    ORDER BY d.racine_client, coalesce(d.valide_le, d.date_eer::timestamptz) DESC NULLS LAST
)
SELECT s.racine_client, s.profil_derive, s.categorie_juridique, s.statut_resident, s.nni, s.nif, s.nom_client,
       s.prenoms, s.secteur_activite, s.date_ouverture, a.id AS agence_id, s.code_agence, s.nb_comptes,
       s.nb_agences, eer.sexe, eer.telephone, k.genre, k.telephone, k.code_csp_bcm, k.code_secteur_bcm
FROM clientele_situation s
LEFT JOIN agences a ON a.code = s.code_agence
LEFT JOIN eer ON eer.racine_client = s.racine_client
LEFT JOIN clientele_kyc k ON k.racine_client = s.racine_client
WHERE (s.profil_derive = :type OR s.profil_derive IS NULL OR s.profil_derive NOT IN ('PP', 'PM'))
  AND s.date_ouverture <= :ref
  AND (:perimetre <> 'COMPTE_OUVERT' OR s.nb_comptes_ouverts > 0)
  AND (:perimetre <> 'NOUVEAUX_PERIODE' OR s.date_ouverture >= :debut)
  AND (CAST(:prefixe AS text) IS NULL OR s.racine_client LIKE :prefixe || '%')
ORDER BY s.racine_client
"""


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v) -> str | None:
    return v.isoformat() if v else None


def _decl_dict(d: ClienteleDeclarationSic, version: str | None = None) -> dict:
    return {
        "id": str(d.id), "type": d.type, "date_reference": _iso(d.date_reference), "date_debut": _iso(d.date_debut),
        "statut": d.statut, "statut_libelle": LIBELLES_STATUT.get(d.statut, d.statut),
        "ref_version_id": str(d.ref_version_id) if d.ref_version_id else None, "ref_version": version,
        "regles": d.regles or [], "controles": d.controles or [],
        "nb_candidats": d.nb_candidats, "nb_lignes": d.nb_lignes, "nb_exclus": d.nb_exclus,
        "nb_bloquantes": d.nb_bloquantes, "nb_a_corriger": d.nb_a_corriger, "nb_avertissements": d.nb_avertissements,
        "fichier_nom": d.fichier_nom, "fichier_sha256": d.fichier_sha256, "controle_fichier": d.controle_fichier,
        "commentaire_validation": d.commentaire_validation,
        "depot_le": _iso(d.depot_le), "depot_resultat": d.depot_resultat, "depot_commentaire": d.depot_commentaire,
        "created_at": _iso(d.created_at), "controlee_le": _iso(d.controlee_le), "validee_le": _iso(d.validee_le),
        "generee_le": _iso(d.generee_le), "depot_saisi_le": _iso(d.depot_saisi_le),
        "colonnes": list(COLONNES[d.type]),
    }


class ClienteleSicService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)
        self.ref = ClienteleBcmReferentielService(db, ctx)

    async def _noms(self, ids: set) -> dict:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = await self.db.execute(text(
            "SELECT id, coalesce(nullif(full_name, ''), email) FROM users WHERE id = ANY(:ids)"), {"ids": list(ids)})
        return {r[0]: r[1] for r in rows.all()}

    async def _version_libelle(self, vid) -> str | None:
        if not vid:
            return None
        return await self.db.scalar(text("SELECT libelle FROM clientele_bcm_ref_versions WHERE id = :i"), {"i": vid})

    async def _get(self, did: uuid.UUID) -> ClienteleDeclarationSic:
        d = await self.db.get(ClienteleDeclarationSic, did)
        if not d:
            raise AppError("Déclaration SIC introuvable", 404, code="NOT_FOUND")
        return d

    async def _detail(self, d: ClienteleDeclarationSic) -> dict:
        out = _decl_dict(d, await self._version_libelle(d.ref_version_id))
        noms = await self._noms({d.created_by_id, d.controlee_par_id, d.validee_par_id, d.generee_par_id,
                                 d.depot_par_id})
        out.update({"cree_par": noms.get(d.created_by_id), "controlee_par": noms.get(d.controlee_par_id),
                    "validee_par": noms.get(d.validee_par_id), "generee_par": noms.get(d.generee_par_id),
                    "depot_par": noms.get(d.depot_par_id)})
        par_champ = (await self.db.execute(text("""
            SELECT a->>'gravite', a->>'champ', count(*)
            FROM clientele_sic_lignes l, jsonb_array_elements(l.anomalies) a
            WHERE l.declaration_id = :d GROUP BY 1, 2 ORDER BY 3 DESC
        """), {"d": d.id})).all()
        out["synthese_anomalies"] = [{"gravite": g, "champ": c, "nombre": n} for g, c, n in par_champ]
        out["nb_incompletes"] = await self.db.scalar(
            select(func.count()).select_from(ClienteleSicLigne).where(
                ClienteleSicLigne.declaration_id == d.id, ClienteleSicLigne.gravite_max == BLOQUANTE)) or 0
        out["actions"] = {
            "controler": d.statut in STATUTS_SIC_MODIFIABLES and self.ctx.peut("clientele.bcm.prepare"),
            "valider": d.statut in ("CONTROLEE", "A_CORRIGER") and self.ctx.peut("clientele.bcm.valider"),
            "generer": d.statut == "VALIDEE_EXPORT" and self.ctx.peut("clientele.bcm.prepare"),
            "deposer": d.statut == "GENEREE" and self.ctx.peut("clientele.sic.depot"),
            "telecharger": d.statut in ("GENEREE", "DEPOSEE"),
        }
        return out

    # ------------------------------------------------------------------ consultation
    async def lister(self, type_sic: str | None = None, statut: str | None = None) -> list[dict]:
        self.ctx.exiger("clientele.bcm.view")
        D = ClienteleDeclarationSic
        stmt = select(D).order_by(D.created_at.desc())
        if type_sic:
            stmt = stmt.where(D.type == type_sic.upper())
        if statut:
            stmt = stmt.where(D.statut == statut.upper())
        rows = (await self.db.scalars(stmt.limit(500))).all()
        noms = await self._noms({d.created_by_id for d in rows} | {d.generee_par_id for d in rows})
        versions = {}
        out = []
        for d in rows:
            if d.ref_version_id not in versions:
                versions[d.ref_version_id] = await self._version_libelle(d.ref_version_id)
            item = _decl_dict(d, versions[d.ref_version_id])
            item.pop("regles")
            item.update({"cree_par": noms.get(d.created_by_id), "generee_par": noms.get(d.generee_par_id)})
            out.append(item)
        return out

    async def detail(self, did: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.bcm.view")
        return await self._detail(await self._get(did))

    async def lignes(self, did: uuid.UUID, statut: str | None, gravite: str | None, champ: str | None,
                     racine: str | None, page: int, taille: int) -> dict:
        self.ctx.exiger("clientele.bcm.view")
        d = await self._get(did)
        L = ClienteleSicLigne
        stmt = select(L).where(L.declaration_id == d.id)
        if statut in ("EXPORTEE", "EXCLUE"):
            stmt = stmt.where(L.statut == statut)
        elif statut == "INCOMPLETE":
            stmt = stmt.where(L.gravite_max == BLOQUANTE)
        elif statut == "COMPLETE":
            stmt = stmt.where(or_(L.gravite_max.is_(None), L.gravite_max != BLOQUANTE))
        if gravite == "AUCUNE":
            stmt = stmt.where(L.gravite_max.is_(None))
        elif gravite:
            stmt = stmt.where(L.anomalies.contains([{"gravite": gravite}]))
        if champ:
            stmt = stmt.where(L.anomalies.contains([{"champ": champ}]))
        if racine and racine.strip():
            stmt = stmt.where(L.racine_client.like(f"{racine.strip()}%"))
        total = await self.db.scalar(select(func.count()).select_from(stmt.subquery()))
        taille = max(1, min(taille, 200))
        rows = (await self.db.scalars(stmt.order_by(L.racine_client).offset((max(page, 1) - 1) * taille)
                                      .limit(taille))).all()
        return {"total": total or 0, "colonnes": list(COLONNES[d.type]),
                "items": [{"racine": r.racine_client, "statut": r.statut, "gravite_max": r.gravite_max,
                           "valeurs": r.valeurs, "anomalies": r.anomalies} for r in rows]}

    # ------------------------------------------------------------------ préparation
    async def creer(self, type_sic: str, date_reference: date, date_debut: date | None,
                    prefixe: str | None = None) -> dict:
        self.ctx.exiger("clientele.bcm.prepare")
        type_sic = (type_sic or "").upper()
        if type_sic not in TYPES_SIC:
            raise AppError("Type attendu : PP ou PM", 422, code="TYPE_INVALIDE")
        if date_reference > date.today():
            raise AppError("La date de référence ne peut pas être future", 422, code="DATE_INVALIDE")
        if date_debut and date_debut > date_reference:
            raise AppError("La date de début doit précéder la date de référence", 422, code="DATE_INVALIDE")
        d = ClienteleDeclarationSic(type=type_sic, date_reference=date_reference, date_debut=date_debut,
                                    statut="BROUILLON", created_by_id=self.ctx.user.id)
        self.db.add(d)
        await self.db.flush()
        await self.svc.audit("sic.creer", "clientele_declaration_sic", d.id,
                             after={"type": type_sic, "date_reference": date_reference.isoformat(),
                                    "date_debut": _iso(date_debut)})
        await self.db.commit()
        return await self.controler(d.id, prefixe=prefixe)

    async def _contexte(self) -> tuple[ContexteSic, list[dict], object]:
        regles_svc = ClienteleBcmReglesService(self.db, self.ctx)
        sic = await regles_svc.courantes("SIC")
        bcm = {r["code"]: r["valeur"] for r in await regles_svc.courantes("BCM")}
        version = await self.ref.version_active()
        ctx = ContexteSic(
            regles={r["code"]: r["valeur"] for r in sic},
            regles_bcm={"forme.correspondance": bcm.get("forme.correspondance"),
                        "forme.repli_profil": bcm.get("forme.repli_profil")},
            codes_ref=await self.ref.codes_version(version.id) if version else {},
            agences=await self.ref.table_agences(),
            secteurs=await self.ref.table_secteurs(),
        )
        return ctx, sic, version

    async def candidats(self, type_sic: str, date_reference: date, date_debut: date | None, perimetre: str,
                        prefixe: str | None = None) -> list[CandidatSic]:
        rows = (await self.db.execute(text(_SQL_CANDIDATS), {
            "type": type_sic, "ref": date_reference, "debut": date_debut or date(1900, 1, 1),
            "perimetre": perimetre, "prefixe": prefixe})).all()
        return [CandidatSic(racine=r[0], profil=r[1], categorie=r[2], statut_resident=r[3], nni=r[4], nif=r[5],
                            nom_complet=r[6], prenoms=r[7], secteur_orion=r[8], date_entree=r[9],
                            agence_id=str(r[10]) if r[10] else None, agence_code=r[11], nb_comptes=r[12] or 0,
                            nb_agences=r[13] or 0, eer_sexe=r[14], eer_telephone=r[15], kyc_genre=r[16],
                            kyc_telephone=r[17], kyc_csp=r[18], kyc_secteur=r[19]) for r in rows]

    async def controler(self, did: uuid.UUID, prefixe: str | None = None) -> dict:
        """(Re)calcule les lignes et les anomalies. ``prefixe`` : restriction de racines réservée aux tests."""
        self.ctx.exiger("clientele.bcm.prepare")
        d = await self._get(did)
        if d.statut not in STATUTS_SIC_MODIFIABLES:
            raise AppError(f"Déclaration {LIBELLES_STATUT[d.statut]} : plus de recalcul possible", 409,
                           code="STATUT_INVALIDE")
        ctx, regles, version = await self._contexte()
        perimetre = ctx.regles.get("sic.perimetre") or "COMPTE_OUVERT"
        if perimetre == "NOUVEAUX_PERIODE" and not d.date_debut:
            raise AppError("Périmètre « nouveaux clients de la période » : date de début obligatoire", 422,
                           code="DATE_DEBUT_OBLIGATOIRE")
        cands = await self.candidats(d.type, d.date_reference, d.date_debut, perimetre, prefixe)
        lignes = construire(cands, d.type, ctx)

        await self.db.execute(delete(ClienteleSicLigne).where(ClienteleSicLigne.declaration_id == d.id))
        for i in range(0, len(lignes), 2000):
            await self.db.execute(insert(ClienteleSicLigne), [
                {"id": uuid.uuid4(), "declaration_id": d.id, "racine_client": lg["racine"], "statut": lg["statut"],
                 "gravite_max": lg["gravite_max"], "valeurs": lg["valeurs"], "anomalies": lg["anomalies"]}
                for lg in lignes[i:i + 2000]])

        compte = Counter(a["gravite"] for lg in lignes for a in lg["anomalies"])
        exportees = sum(lg["statut"] == "EXPORTEE" for lg in lignes)
        exclues = len(lignes) - exportees
        d.regles = [{"code": r["code"], "libelle": r["libelle"], "valeur": r["valeur"], "statut": r["statut"]}
                    for r in regles]
        d.ref_version_id = version.id if version else None
        d.nb_candidats, d.nb_lignes, d.nb_exclus = len(lignes), exportees, exclues
        d.nb_bloquantes, d.nb_a_corriger, d.nb_avertissements = (compte[BLOQUANTE], compte[A_CORRIGER],
                                                                  compte[AVERTISSEMENT])
        hors_vue = await self.db.scalar(text(
            "SELECT count(*) FROM clientele_clients c WHERE EXISTS (SELECT 1 FROM clientele_comptes k "
            "WHERE k.racine_client = c.racine_client) AND NOT EXISTS (SELECT 1 FROM clientele_situation s "
            "WHERE s.racine_client = c.racine_client)")) or 0
        d.controles = self._controles(d, lignes, regles, version, ctx, perimetre)
        d.controles.append({"code": "perimetre.hors_vue", "libelle": "Aucun client avec compte hors périmètre de "
                            "calcul (compte sans agence)", "ok": not hors_vue, "bloquant": False,
                            "detail": f"{hors_vue} client(s) non évalué(s)" if hors_vue else ""})
        d.statut = "A_CORRIGER" if (compte[BLOQUANTE] or compte[A_CORRIGER]
                                    or any(c["bloquant"] and not c["ok"] for c in d.controles)) else "CONTROLEE"
        d.controlee_le, d.controlee_par_id = _maintenant(), self.ctx.user.id
        await self.db.flush()
        await self.svc.audit("sic.controler", "clientele_declaration_sic", d.id,
                             after={"statut": d.statut, "candidats": len(lignes), "exportees": exportees,
                                    "exclues": exclues, "bloquantes": compte[BLOQUANTE],
                                    "a_corriger": compte[A_CORRIGER], "avertissements": compte[AVERTISSEMENT],
                                    "ref_version_id": str(d.ref_version_id) if d.ref_version_id else None})
        await self.db.commit()
        return await self._detail(d)

    @staticmethod
    def _controles(d, lignes: list[dict], regles: list[dict], version, ctx: ContexteSic, perimetre: str) -> list:
        def c(code, libelle, ok, detail="", bloquant=False):
            return {"code": code, "libelle": libelle, "ok": bool(ok), "detail": detail, "bloquant": bloquant}

        a_valider = [r["libelle"] for r in regles if r["statut"] != "CONFIRMEE"]
        champs = Counter((a["champ"], a["gravite"]) for lg in lignes for a in lg["anomalies"])
        racines = Counter(lg["racine"] for lg in lignes)
        agences_manquantes = sorted({a["valeur"] or "—" for lg in lignes for a in lg["anomalies"]
                                     if a["champ"] == "MoughataaAgence" and a["gravite"] == BLOQUANTE})
        incompletes = sum(lg["gravite_max"] == BLOQUANTE for lg in lignes)
        return [
            c("referentiel.actif", "Version active du référentiel BCM", version is not None,
              f"Version « {version.libelle} »" if version else "Aucune version active : codes CSP / secteur non "
              "contrôlables"),
            c("regles.a_valider", "Règles SIC confirmées", not a_valider,
              ("À valider : " + " ; ".join(a_valider)) if a_valider else ""),
            c("perimetre", "Périmètre appliqué", True, f"{perimetre} au {d.date_reference:%d/%m/%Y}"),
            c("colonnes", f"Structure du fichier {d.type}", True,
              f"{len(COLONNES[d.type])} colonnes : {', '.join(COLONNES[d.type])}"),
            c("candidats", "Clients candidats", bool(lignes), f"{len(lignes)} candidat(s)", bloquant=True),
            c("unicite", "Une ligne par racine client", all(n == 1 for n in racines.values()), bloquant=True),
            c("completude", "Lignes complètes", not incompletes,
              f"{incompletes} ligne(s) exportée(s) avec des cellules vides, listées dans le rapport d'anomalies"),
            c("agences", "Correspondance MoughataaAgence complète", not agences_manquantes,
              ("Agences sans valeur : " + ", ".join(agences_manquantes[:20])) if agences_manquantes else ""),
            c("anomalies.champs", "Répartition des anomalies", not champs,
              " ; ".join(f"{ch} ({g}) : {n}" for (ch, g), n in champs.most_common(12))),
        ]

    # ------------------------------------------------------------------ validation, génération, dépôt
    async def valider(self, did: uuid.UUID, commentaire: str | None) -> dict:
        self.ctx.exiger("clientele.bcm.valider")
        d = await self._get(did)
        if d.statut not in ("CONTROLEE", "A_CORRIGER"):
            raise AppError("Seule une déclaration contrôlée peut être validée pour export", 409,
                           code="STATUT_INVALIDE")
        commentaire = (commentaire or "").strip()
        bloquants = [c["libelle"] for c in d.controles or [] if c.get("bloquant") and not c.get("ok")]
        if bloquants:
            raise AppError("Contrôles bloquants non satisfaits : " + " ; ".join(bloquants), 409,
                           code="CONTROLES_BLOQUANTS")
        avant = d.statut
        d.statut = "VALIDEE_EXPORT"
        d.commentaire_validation = commentaire or None
        d.validee_le, d.validee_par_id = _maintenant(), self.ctx.user.id
        await self.db.flush()
        await self.svc.audit("sic.valider", "clientele_declaration_sic", d.id, before={"statut": avant},
                             after={"statut": d.statut, "commentaire": commentaire, "bloquantes": d.nb_bloquantes,
                                    "a_corriger": d.nb_a_corriger})
        await self.db.commit()
        return await self._detail(d)

    async def generer(self, did: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.bcm.prepare")
        d = await self._get(did)
        if d.statut != "VALIDEE_EXPORT":
            raise AppError("La déclaration doit être validée pour export avant génération", 409,
                           code="STATUT_INVALIDE")
        L = ClienteleSicLigne
        valeurs = [r for r in (await self.db.scalars(
            select(L.valeurs).where(L.declaration_id == d.id, L.statut == "EXPORTEE").order_by(L.racine_client)
        )).all()]
        if not valeurs:
            raise AppError("Aucun client exportable", 409, code="AUCUNE_LIGNE")
        regles = {r["code"]: r["valeur"] for r in d.regles or []}
        fmt = regles.get("sic.format_date") or "TEXTE_JJ_MM_AAAA"
        contenu = ecrire_xlsx(d.type, valeurs, fmt)
        codes = await self.ref.codes_version(d.ref_version_id) if d.ref_version_id else {}
        verif = verifier_xlsx(contenu, d.type, valeurs, fmt, codes, regles)
        d.controle_fichier = verif
        if not verif["ok"]:
            await self.db.commit()
            ko = [c["libelle"] for c in verif["controles"] if not c["ok"]]
            raise AppError("Contrôle du fichier généré en échec : " + " ; ".join(ko), 409, code="CONTROLE_FICHIER")
        d.fichier = contenu
        d.fichier_sha256 = hashlib.sha256(contenu).hexdigest()
        d.fichier_nom = f"SIC_{d.type}_BEA_{d.date_reference:%Y%m%d}.xlsx"
        d.statut = "GENEREE"
        d.generee_le, d.generee_par_id = _maintenant(), self.ctx.user.id
        await self.db.flush()
        await self.svc.audit("sic.generer", "clientele_declaration_sic", d.id,
                             after={"statut": d.statut, "fichier": d.fichier_nom, "sha256": d.fichier_sha256,
                                    "lignes": len(valeurs)})
        await self.db.commit()
        return await self._detail(d)

    async def fichier(self, did: uuid.UUID) -> tuple[bytes, str]:
        self.ctx.exiger("clientele.bcm.view")
        d = await self._get(did)
        if not d.fichier:
            raise AppError("Fichier non généré", 404, code="NOT_FOUND")
        await self.svc.audit("sic.telecharger", "clientele_declaration_sic", d.id,
                             after={"fichier": d.fichier_nom, "sha256": d.fichier_sha256})
        await self.db.commit()
        return d.fichier, d.fichier_nom or "sic.xlsx"

    async def rapport(self, did: uuid.UUID) -> tuple[bytes, str]:
        self.ctx.exiger("clientele.bcm.view")
        d = await self._get(did)
        L = ClienteleSicLigne
        rows = (await self.db.scalars(select(L).where(L.declaration_id == d.id, L.gravite_max.is_not(None))
                                      .order_by(L.statut, L.racine_client))).all()
        entete = [
            ("Déclaration SIC", d.type), ("Date de référence", f"{d.date_reference:%d/%m/%Y}"),
            ("Statut", LIBELLES_STATUT.get(d.statut, d.statut)),
            ("Référentiel BCM", await self._version_libelle(d.ref_version_id) or "—"),
            ("Clients candidats", d.nb_candidats), ("Clients exportés", d.nb_lignes),
            ("Anomalies bloquantes", d.nb_bloquantes), ("Anomalies à corriger", d.nb_a_corriger),
            ("Avertissements", d.nb_avertissements),
            ("Édité le", f"{_maintenant():%d/%m/%Y %H:%M} UTC"),
        ]
        contenu = rapport_anomalies_xlsx(entete, [{"racine": r.racine_client, "statut": r.statut,
                                                    "anomalies": r.anomalies} for r in rows])
        await self.svc.audit("sic.rapport", "clientele_declaration_sic", d.id, after={"lignes": len(rows)})
        await self.db.commit()
        return contenu, f"SIC_{d.type}_BEA_{d.date_reference:%Y%m%d}_anomalies.xlsx"

    async def deposer(self, did: uuid.UUID, depot_le: date, resultat: str, commentaire: str | None) -> dict:
        """Saisie manuelle du dépôt effectué par l'utilisateur sur la plateforme SIC. Aucun envoi automatique."""
        self.ctx.exiger("clientele.sic.depot")
        d = await self._get(did)
        if d.statut != "GENEREE":
            raise AppError("Seul un fichier généré peut être déclaré déposé", 409, code="STATUT_INVALIDE")
        resultat = (resultat or "").upper()
        if resultat not in RESULTATS_DEPOT:
            raise AppError(f"Résultat attendu : {', '.join(RESULTATS_DEPOT)}", 422, code="RESULTAT_INVALIDE")
        if depot_le > date.today() or (d.generee_le and depot_le < d.generee_le.date()):
            raise AppError("Date de dépôt incohérente (future ou antérieure à la génération)", 422,
                           code="DATE_INVALIDE")
        commentaire = (commentaire or "").strip()
        if resultat in ("REJETE", "ACCEPTE_PARTIELLEMENT") and not commentaire:
            raise AppError("Commentaire obligatoire pour un rejet ou une acceptation partielle", 422,
                           code="MOTIF_OBLIGATOIRE")
        d.statut = "DEPOSEE"
        d.depot_le, d.depot_resultat, d.depot_commentaire = depot_le, resultat, commentaire or None
        d.depot_par_id, d.depot_saisi_le = self.ctx.user.id, _maintenant()
        await self.db.flush()
        await self.svc.audit("sic.deposer", "clientele_declaration_sic", d.id, before={"statut": "GENEREE"},
                             after={"statut": "DEPOSEE", "depot_le": depot_le.isoformat(), "resultat": resultat,
                                    "commentaire": commentaire})
        await self.db.commit()
        return await self._detail(d)

    # ------------------------------------------------------------------ historique commun
    async def historique(self) -> list[dict]:
        self.ctx.exiger("clientele.bcm.view")
        B = ClienteleDeclarationBcm
        bcm = (await self.db.scalars(select(B).order_by(B.annee.desc(), B.mois.desc()).limit(200))).all()
        sic = await self.lister()
        noms = await self._noms({b.created_by_id for b in bcm} | {b.validee_par_id for b in bcm})
        items = [{
            "id": str(b.id), "famille": "MENSUELLE", "type": "Déclaration mensuelle BCM",
            "periode": f"{b.mois:02d}/{b.annee}", "date_reference": _iso(b.date_fin), "statut": b.statut,
            "cree_le": _iso(b.created_at), "cree_par": noms.get(b.created_by_id),
            "generee_le": _iso(b.validee_le), "generee_par": noms.get(b.validee_par_id),
            "ref_version": b.grille_version, "nb_candidats": None, "nb_lignes": None,
            "nb_bloquantes": None, "nb_a_corriger": None, "nb_avertissements": None,
            "fichier_nom": None, "lien": f"/clientele/declarations/{b.id}",
        } for b in bcm]
        items += [{
            "id": s["id"], "famille": "SIC", "type": f"Déclaration SIC {s['type']}",
            "periode": f"au {date.fromisoformat(s['date_reference']):%d/%m/%Y}", "date_reference": s["date_reference"],
            "statut": s["statut"], "statut_libelle": s["statut_libelle"], "cree_le": s["created_at"],
            "cree_par": s["cree_par"], "generee_le": s["generee_le"], "generee_par": s["generee_par"],
            "ref_version": s["ref_version"], "nb_candidats": s["nb_candidats"], "nb_lignes": s["nb_lignes"],
            "nb_bloquantes": s["nb_bloquantes"], "nb_a_corriger": s["nb_a_corriger"],
            "nb_avertissements": s["nb_avertissements"], "fichier_nom": s["fichier_nom"],
            "depot_resultat": s["depot_resultat"], "lien": f"/clientele/sic/{s['id']}",
        } for s in sic]
        items.sort(key=lambda x: x["cree_le"] or "", reverse=True)
        return items
