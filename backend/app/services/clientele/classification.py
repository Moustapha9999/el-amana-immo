"""Moteur de classification CLIENT (racine). Règles en base, jamais hardcodées.

Niveaux : FAIBLE / MOYEN / ELEVE / INTERDIT. La racine n'est jamais modifiable ici.
Une classification manuelle n'est pas écrasée par le moteur sans ``forcer``.
"""

from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models import (
    ClienteleAlerte,
    ClienteleClassifCritere,
    ClienteleClassifDivergence,
    ClienteleClassifEvaluation,
    ClienteleClassifEvaluationLigne,
    ClienteleClassifHistorique,
    ClienteleClassifNiveau,
    ClienteleClassifRegle,
    ClienteleClassifVersion,
    ClienteleClassification,
    ClienteleClient,
    ClienteleCompte,
    EerDossier,
    User,
)
from app.services.clientele.scoring import (
    SOURCES_LIBELLES, DonneesClient, divergences_dict, evaluer, matrice_maitre_dict, nommer,
    valeurs_maitre_dict,
)
from app.services.clientele.service import Ctx, ClienteleService, maintenant

NIVEAUX = ("FAIBLE", "MOYEN", "ELEVE", "INTERDIT")
CHAMPS_CLIENT = frozenset({
    "raison_sociale", "prenoms", "nationalite", "statut_resident", "agent_economique",
    "situation_juridique", "categorie_juridique", "secteur_activite", "famille_secteur_activite",
    "type_identifiant", "nni", "nif", "rcs", "type_client",
})
CHAMPS_COMPTE = frozenset({
    "etat_compte", "liste_interdiction", "conformite_compte", "devise", "ncg",
})
OPERATEURS = ("EGAL", "DIFFERENT", "IN", "NOT_IN", "CONTIENT", "VIDE", "NON_VIDE")


def _val(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _match(operateur: str, observe: Any, attendu: Any) -> bool:
    obs = _val(observe)
    if operateur == "VIDE":
        return obs is None
    if operateur == "NON_VIDE":
        return obs is not None
    if operateur == "EGAL":
        return obs is not None and obs.upper() == str(attendu).strip().upper()
    if operateur == "DIFFERENT":
        return obs is None or obs.upper() != str(attendu).strip().upper()
    if operateur == "CONTIENT":
        return obs is not None and str(attendu).strip().upper() in obs.upper()
    valeurs = attendu if isinstance(attendu, (list, tuple)) else [attendu]
    cible = {str(x).strip().upper() for x in valeurs if x is not None and str(x).strip()}
    if operateur == "IN":
        return obs is not None and obs.upper() in cible
    if operateur == "NOT_IN":
        return obs is None or obs.upper() not in cible
    return False


def _habiller_modele(ws, largeurs: list[int]) -> None:
    """Style seulement : l'en-tête reste en ligne 1, lue telle quelle par ``analyser_excel``."""
    entete = PatternFill("solid", fgColor="1E3A5F")
    bord = Border(bottom=Side(style="thin", color="CBD5E1"))
    for cell in ws[1]:
        cell.fill = entete
        cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Calibri", size=10, color="0F172A")
            cell.border = bord
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 22
    for i, largeur in enumerate(largeurs, start=1):
        ws.column_dimensions[get_column_letter(i)].width = largeur
    ws.freeze_panes = "A2"


class ClienteleClassificationService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)

    async def referentiel(self) -> dict:
        self.ctx.exiger("clientele.classif.view")
        niveaux = list((await self.db.scalars(
            select(ClienteleClassifNiveau).order_by(ClienteleClassifNiveau.rang))).all())
        criteres = list((await self.db.scalars(
            select(ClienteleClassifCritere).order_by(ClienteleClassifCritere.code))).all())
        versions = list((await self.db.scalars(
            select(ClienteleClassifVersion).order_by(ClienteleClassifVersion.numero.desc()))).all())
        return {
            "niveaux": [{"code": n.code, "libelle": n.libelle, "rang": n.rang, "actif": n.actif} for n in niveaux],
            "criteres": [{"id": str(c.id), "code": c.code, "libelle": c.libelle,
                          "description": c.description, "champ_defaut": c.champ_defaut,
                          "actif": c.actif} for c in criteres],
            "versions": [self._version_dict(v, avec_regles=False) for v in versions],
            "operateurs": list(OPERATEURS),
            "champs_client": sorted(CHAMPS_CLIENT),
            "champs_compte": sorted(CHAMPS_COMPTE),
            "avertissement": (
                "Moteur SCORE uniquement (CDC 1.0). Les valeurs du référentiel maître ne sont pas ACTIVE. "
                "INTERDIT = blocage métier, le score reste calculé. Conflit Matrice des risques LBC/FT BEA / "
                "Fiche de scoring non arbitré : exclu de la somme. Donnée absente ≠ Faible. 0 critère → NON CLASSÉ."
            ),
            "matrice": matrice_maitre_dict()["meta"],
        }

    async def version_detail(self, vid: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.classif.view")
        v = await self.db.scalar(
            select(ClienteleClassifVersion).where(ClienteleClassifVersion.id == vid)
            .options(selectinload(ClienteleClassifVersion.regles).selectinload(ClienteleClassifRegle.critere)))
        if not v:
            raise AppError("Version introuvable", 404, code="NOT_FOUND")
        return self._version_dict(v, avec_regles=True)

    async def creer_regle(self, vid: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.classif.admin")
        v = await self.db.get(ClienteleClassifVersion, vid)
        if not v:
            raise AppError("Version introuvable", 404, code="NOT_FOUND")
        if v.statut == "ARCHIVEE":
            raise AppError("Version archivée", 409, code="VERSION_ARCHIVEE")
        r = self._regle_depuis(vid, payload)
        self.db.add(r)
        await self.db.flush()
        await self.svc.audit("clientele.classif.regle.create", "clientele_classif_regle", r.id,
                             after={"version": v.numero, "niveau": r.niveau_cible})
        return await self.version_detail(vid)

    async def modifier_regle(self, rid: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.classif.admin")
        r = await self.db.get(ClienteleClassifRegle, rid)
        if not r:
            raise AppError("Règle introuvable", 404, code="NOT_FOUND")
        v = await self.db.get(ClienteleClassifVersion, r.version_id)
        if v and v.statut == "ARCHIVEE":
            raise AppError("Version archivée", 409, code="VERSION_ARCHIVEE")
        self._appliquer_payload(r, payload)
        await self.db.flush()
        await self.svc.audit("clientele.classif.regle.update", "clientele_classif_regle", rid)
        return await self.version_detail(r.version_id)

    async def supprimer_regle(self, rid: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.classif.admin")
        r = await self.db.get(ClienteleClassifRegle, rid)
        if not r:
            raise AppError("Règle introuvable", 404, code="NOT_FOUND")
        vid = r.version_id
        await self.db.delete(r)
        await self.db.flush()
        return await self.version_detail(vid)

    async def activer_version(self, vid: uuid.UUID) -> dict:
        self.ctx.exiger("clientele.classif.admin")
        v = await self.db.get(ClienteleClassifVersion, vid)
        if not v:
            raise AppError("Version introuvable", 404, code="NOT_FOUND")
        actives = list((await self.db.scalars(
            select(ClienteleClassifVersion).where(ClienteleClassifVersion.statut == "ACTIVE"))).all())
        for autre in actives:
            if autre.id != v.id:
                autre.statut = "ARCHIVEE"
                autre.date_fin = date.today()
        v.statut = "ACTIVE"
        v.date_fin = None
        await self.db.flush()
        await self.svc.audit("clientele.classif.version.activer", "clientele_classif_version", vid,
                             after={"numero": v.numero})
        return await self.version_detail(vid)

    async def creer_version(self, payload: dict) -> dict:
        self.ctx.exiger("clientele.classif.admin")
        dernier = await self.db.scalar(select(func.max(ClienteleClassifVersion.numero))) or 0
        v = ClienteleClassifVersion(
            numero=int(dernier) + 1,
            libelle=(payload.get("libelle") or f"Version {int(dernier) + 1}")[:160],
            mode=payload.get("mode") if payload.get("mode") in ("MAX_NIVEAU", "SCORE") else "MAX_NIVEAU",
            seuils=payload.get("seuils"),
            date_effet=date.fromisoformat(payload["date_effet"]) if payload.get("date_effet") else date.today(),
            statut="BROUILLON",
            created_by_id=self.ctx.user.id,
        )
        self.db.add(v)
        await self.db.flush()
        source_id = payload.get("copier_version_id")
        if source_id:
            src = await self.db.scalar(
                select(ClienteleClassifVersion).where(ClienteleClassifVersion.id == uuid.UUID(str(source_id)))
                .options(selectinload(ClienteleClassifVersion.regles)))
            if src:
                for r in src.regles:
                    self.db.add(ClienteleClassifRegle(
                        version_id=v.id, critere_id=r.critere_id, priorite=r.priorite, poids=r.poids,
                        niveau_cible=r.niveau_cible, operateur=r.operateur, champ_source=r.champ_source,
                        portee=r.portee, valeur=r.valeur, motif=r.motif, actif=r.actif))
        await self.db.flush()
        return await self.version_detail(v.id)

    async def lister(self, *, niveau: str | None = None, source: str | None = None,
                     q: str | None = None, page: int = 1, taille: int = 50) -> dict:
        self.ctx.exiger("clientele.classif.view")
        filtres = []
        if niveau:
            filtres.append(ClienteleClassification.niveau == niveau)
        if source:
            filtres.append(ClienteleClassification.source == source)
        stmt = (select(ClienteleClassification, ClienteleClient.raison_sociale)
                .join(ClienteleClient, ClienteleClient.racine_client == ClienteleClassification.racine_client))
        if filtres:
            stmt = stmt.where(*filtres)
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(ClienteleClassification.racine_client.like(like),
                                  ClienteleClient.raison_sociale.ilike(like)))
        total = await self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = (await self.db.execute(
            stmt.order_by(ClienteleClassification.niveau.desc(), ClienteleClassification.racine_client)
            .offset((page - 1) * taille).limit(min(taille, 200))
        )).all()
        return {
            "total": int(total), "page": page, "taille": taille,
            "items": [{**self._classif_dict(c), "raison_sociale": nom} for c, nom in rows],
        }

    async def historique(self, racine: str) -> list[dict]:
        self.ctx.exiger("clientele.classif.view")
        racine = self._racine(racine)
        rows = list((await self.db.execute(
            select(ClienteleClassifHistorique, User.full_name)
            .outerjoin(User, User.id == ClienteleClassifHistorique.created_by_id)
            .where(ClienteleClassifHistorique.racine_client == racine)
            .order_by(ClienteleClassifHistorique.created_at.desc())
        )).all())
        return [{
            "id": str(h.id), "ancienne_classe": h.ancienne_classe, "nouvelle_classe": h.nouvelle_classe,
            "motif_risque": h.motif_risque, "motif_classement": h.motif_classement,
            "source": h.source, "version_id": str(h.version_id) if h.version_id else None,
            "detail": h.detail, "utilisateur": nom,
            "date": h.created_at.isoformat() if h.created_at else None,
        } for h, nom in rows]

    async def modifier_individuel(self, racine: str, payload: dict) -> dict:
        self.ctx.exiger("clientele.classif.execute")
        if "racine_client" in payload and str(payload["racine_client"]).strip() not in ("", racine):
            raise AppError("La racine client n'est pas modifiable depuis la classification", 422,
                           code="RACINE_IMMUTABLE")
        racine = self._racine(racine)
        if not await self.db.scalar(select(ClienteleClient.racine_client)
                                    .where(ClienteleClient.racine_client == racine)):
            raise AppError("Client introuvable", 404, code="NOT_FOUND")
        niveau = (payload.get("niveau") or "").upper()
        if niveau not in NIVEAUX:
            raise AppError("Niveau invalide (FAIBLE, MOYEN, ELEVE, INTERDIT)", 422, code="NIVEAU_INVALIDE")
        motif_r = (payload.get("motif_risque") or "").strip() or None
        motif_c = (payload.get("motif_classement") or "").strip() or None
        if not motif_c:
            raise AppError("Motif de classement obligatoire", 422, code="MOTIF_OBLIGATOIRE")
        await self._enregistrer(
            racine, niveau, source="MANUEL", version_id=None,
            motifs=[{"critere": "MANUEL", "motif": motif_c, "niveau": niveau}],
            motif_risque=motif_r, motif_classement=motif_c)
        await self.svc.audit("clientele.classif.manuel", "clientele_classification", racine,
                             after={"niveau": niveau})
        return await self.courante(racine)

    async def courante(self, racine: str) -> dict:
        self.ctx.exiger("clientele.classif.view")
        racine = self._racine(racine)
        c = await self.db.get(ClienteleClassification, racine)
        return {"racine_client": racine, "classification": self._classif_dict(c) if c else None,
                "historique": await self.historique(racine)}

    async def appliquer_moteur(self, *, racine: str | None = None, forcer: bool = False) -> dict:
        self.ctx.exiger("clientele.classif.execute")
        version = await self._version_active()
        regles = list((await self.db.scalars(
            select(ClienteleClassifRegle)
            .where(ClienteleClassifRegle.version_id == version.id, ClienteleClassifRegle.actif.is_(True))
            .options(selectinload(ClienteleClassifRegle.critere))
        )).all())
        if not regles:
            raise AppError(
                "Aucune règle active : le moteur ne classe pas tant que le métier n'a pas validé "
                "et saisi les règles (matrice / seuils).",
                422, code="AUCUNE_REGLE")
        rangs = {n.code: n.rang for n in (await self.db.scalars(select(ClienteleClassifNiveau))).all()}
        q = select(ClienteleClient)
        if racine:
            q = q.where(ClienteleClient.racine_client == self._racine(racine))
        clients = list((await self.db.scalars(q)).all())
        traites = ignores = changes = 0
        for client in clients:
            actuelle = await self.db.get(ClienteleClassification, client.racine_client)
            if actuelle and actuelle.source == "MANUEL" and not forcer:
                ignores += 1
                continue
            comptes = list((await self.db.scalars(
                select(ClienteleCompte).where(ClienteleCompte.racine_client == client.racine_client)
            )).all())
            resultat = self._evaluer(client, comptes, regles, rangs, version.mode, version.seuils)
            traites += 1
            if not resultat:
                continue
            if actuelle and actuelle.niveau == resultat["niveau"] and actuelle.version_id == version.id:
                continue
            await self._enregistrer(
                client.racine_client, resultat["niveau"], source="MOTEUR", version_id=version.id,
                motifs=resultat["motifs"], motif_risque=resultat["motif_risque"],
                motif_classement=resultat["motif_classement"])
            changes += 1
        await self.svc.audit("clientele.classif.moteur", "clientele_classif_version", version.id,
                             after={"traites": traites, "changes": changes, "ignores": ignores})
        return {"version": version.numero, "traites": traites, "modifies": changes,
                "manuels_preserves": ignores}

    async def modele_excel(self) -> bytes:
        self.ctx.exiger("clientele.classif.execute")
        wb = Workbook()
        ws = wb.active
        ws.title = "Classification"
        ws.append(["RACINE_CLIENT", "NIVEAU", "MOTIF_RISQUE", "MOTIF_CLASSEMENT"])
        ws.append(["000001", "ELEVE", "PPE (exemple)", "Saisie manuelle — règles à valider"])
        ws2 = wb.create_sheet("Niveaux")
        ws2.append(["Code", "Libellé"])
        for code in NIVEAUX:
            ws2.append([code, code])
        note = wb.create_sheet("Lire")
        note.append(["Notes de lecture"])
        note.append(["La colonne RACINE_CLIENT identifie le client. Elle n'est jamais modifiée."])
        note.append(["Niveaux autorisés : FAIBLE, MOYEN, ELEVE, INTERDIT."])
        note.append(["Les règles métier (matrice, listes, seuils) ne sont pas déduites de ce fichier."])
        _habiller_modele(ws, [18, 14, 36, 44])
        ws["A2"].number_format = "@"
        _habiller_modele(ws2, [16, 24])
        _habiller_modele(note, [90])
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    async def analyser_excel(self, contenu: bytes) -> dict:
        self.ctx.exiger("clientele.classif.execute")
        try:
            wb = load_workbook(BytesIO(contenu), read_only=True, data_only=True)
        except Exception as exc:
            raise AppError("Fichier Excel illisible", 422, code="FICHIER_ILLISIBLE") from exc
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not rows:
            raise AppError("Feuille vide", 422, code="FICHIER_VIDE")
        entetes = [str(c).strip().upper() if c else "" for c in rows[0]]
        idx = {h: i for i, h in enumerate(entetes)}
        if "RACINE_CLIENT" not in idx or "NIVEAU" not in idx:
            raise AppError("Colonnes obligatoires : RACINE_CLIENT, NIVEAU", 422, code="COLONNES_MANQUANTES")
        if any("RACINE" in h and h != "RACINE_CLIENT" for h in entetes):
            raise AppError("Aucune colonne ne peut modifier la racine", 422, code="RACINE_IMMUTABLE")
        valides: list[dict] = []
        rejets: list[dict] = []
        vues: set[str] = set()
        for numero, row in enumerate(rows[1:], start=2):
            if not row or all(c is None or str(c).strip() == "" for c in row):
                continue
            racine = str(row[idx["RACINE_CLIENT"]] or "").strip().zfill(6)[:6]
            niveau = str(row[idx["NIVEAU"]] or "").strip().upper().replace("É", "E")
            if niveau == "ELEVEE":
                niveau = "ELEVE"
            motif_r = str(row[idx["MOTIF_RISQUE"]]).strip() if "MOTIF_RISQUE" in idx and row[idx["MOTIF_RISQUE"]] else None
            motif_c = str(row[idx["MOTIF_CLASSEMENT"]]).strip() if "MOTIF_CLASSEMENT" in idx and row[idx["MOTIF_CLASSEMENT"]] else None
            if len(racine) != 6 or not racine.isdigit():
                rejets.append({"ligne": numero, "motif": "racine invalide"})
                continue
            if niveau not in NIVEAUX:
                rejets.append({"ligne": numero, "racine": racine, "motif": "niveau invalide"})
                continue
            if racine in vues:
                rejets.append({"ligne": numero, "racine": racine, "motif": "doublon dans le fichier"})
                continue
            if not await self.db.scalar(select(ClienteleClient.racine_client)
                                        .where(ClienteleClient.racine_client == racine)):
                rejets.append({"ligne": numero, "racine": racine, "motif": "client absent du référentiel"})
                continue
            vues.add(racine)
            valides.append({"racine_client": racine, "niveau": niveau,
                            "motif_risque": motif_r, "motif_classement": motif_c or "Import Excel contrôlé"})
        return {"nb_valides": len(valides), "nb_rejets": len(rejets), "valides": valides[:200],
                "rejets": rejets[:200], "lignes": valides}

    async def confirmer_excel(self, lignes: list[dict]) -> dict:
        self.ctx.exiger("clientele.classif.execute")
        if not lignes:
            raise AppError("Aucune ligne à importer", 422, code="AUCUNE_LIGNE")
        n = 0
        for ligne in lignes:
            racine = self._racine(ligne["racine_client"])
            niveau = ligne["niveau"]
            if niveau not in NIVEAUX:
                continue
            await self._enregistrer(
                racine, niveau, source="EXCEL", version_id=None,
                motifs=[{"critere": "EXCEL", "motif": ligne.get("motif_classement"), "niveau": niveau}],
                motif_risque=ligne.get("motif_risque"),
                motif_classement=ligne.get("motif_classement") or "Import Excel contrôlé")
            n += 1
        await self.svc.audit("clientele.classif.excel", "clientele_classification", None,
                             after={"nb": n})
        return {"modifies": n}

    def _evaluer(self, client: ClienteleClient, comptes: list[ClienteleCompte],
                 regles: list[ClienteleClassifRegle], rangs: dict[str, int],
                 mode: str, seuils: dict | None) -> dict | None:
        matches: list[tuple[ClienteleClassifRegle, ClienteleClassifCritere | None]] = []
        for r in sorted(regles, key=lambda x: x.priorite):
            if self._regle_matche(r, client, comptes):
                matches.append((r, r.critere if hasattr(r, "critere") else None))
        if not matches:
            return None
        if any(r.niveau_cible == "INTERDIT" for r, _ in matches):
            retenues = [(r, c) for r, c in matches if r.niveau_cible == "INTERDIT"]
            niveau = "INTERDIT"
        elif mode == "SCORE":
            score = sum(r.poids for r, _ in matches)
            niveau = self._niveau_depuis_score(score, seuils, rangs)
            retenues = matches
        else:
            niveau = max((r.niveau_cible for r, _ in matches), key=lambda n: rangs.get(n, 0))
            retenues = [(r, c) for r, c in matches if r.niveau_cible == niveau] or matches
        motifs = [{
            "critere": (c.code if c else r.champ_source),
            "libelle": (c.libelle if c else r.champ_source),
            "motif": r.motif, "niveau": r.niveau_cible, "poids": r.poids,
        } for r, c in retenues]
        return {
            "niveau": niveau,
            "motifs": motifs,
            "motif_risque": " ; ".join(m["libelle"] for m in motifs),
            "motif_classement": " ; ".join(m["motif"] for m in motifs),
        }

    def _regle_matche(self, r: ClienteleClassifRegle, client: ClienteleClient,
                      comptes: list[ClienteleCompte]) -> bool:
        if r.portee == "COMPTE" or r.champ_source in CHAMPS_COMPTE:
            if r.operateur in ("VIDE",) and not comptes:
                return True
            return any(_match(r.operateur, getattr(c, r.champ_source, None), r.valeur) for c in comptes)
        if r.champ_source == "date_ouverture":
            dates = [c.date_ouverture for c in comptes if c.date_ouverture]
            observe = min(dates).isoformat() if dates else None
            return _match(r.operateur, observe, r.valeur)
        if r.champ_source not in CHAMPS_CLIENT:
            return False
        return _match(r.operateur, getattr(client, r.champ_source, None), r.valeur)

    @staticmethod
    def _niveau_depuis_score(score: int, seuils: dict | None, rangs: dict[str, int]) -> str:
        s = seuils or {}
        try:
            if score >= int(s.get("INTERDIT", 10**9)):
                return "INTERDIT"
            if score >= int(s.get("ELEVE", 10**9)):
                return "ELEVE"
            if score >= int(s.get("MOYEN", 10**9)):
                return "MOYEN"
        except (TypeError, ValueError):
            pass
        return "FAIBLE" if "FAIBLE" in rangs else "MOYEN"

    async def _enregistrer(self, racine: str, niveau: str, *, source: str,
                           version_id: uuid.UUID | None, motifs: list, motif_risque: str | None,
                           motif_classement: str | None) -> None:
        actuelle = await self.db.get(ClienteleClassification, racine)
        ancienne = actuelle.niveau if actuelle else None
        self.db.add(ClienteleClassifHistorique(
            racine_client=racine, ancienne_classe=ancienne, nouvelle_classe=niveau,
            motif_risque=motif_risque, motif_classement=motif_classement, source=source,
            version_id=version_id, detail={"motifs": motifs}, created_by_id=self.ctx.user.id))
        now = maintenant()
        if actuelle:
            actuelle.niveau = niveau
            actuelle.version_id = version_id
            actuelle.motifs = motifs
            actuelle.source = source
            actuelle.motif_risque = motif_risque
            actuelle.motif_classement = motif_classement
            actuelle.classifie_le = now
            actuelle.classifie_par_id = self.ctx.user.id
            actuelle.updated_at = now
        else:
            self.db.add(ClienteleClassification(
                racine_client=racine, niveau=niveau, version_id=version_id, motifs=motifs,
                source=source, motif_risque=motif_risque, motif_classement=motif_classement,
                classifie_le=now, classifie_par_id=self.ctx.user.id, updated_at=now))
        await self.db.flush()

    async def _version_active(self) -> ClienteleClassifVersion:
        v = await self.db.scalar(
            select(ClienteleClassifVersion).where(ClienteleClassifVersion.statut == "ACTIVE")
            .order_by(ClienteleClassifVersion.date_effet.desc()).limit(1))
        if not v:
            raise AppError("Aucune version ACTIVE de règles", 422, code="AUCUNE_VERSION")
        return v

    def _regle_depuis(self, vid: uuid.UUID, payload: dict) -> ClienteleClassifRegle:
        r = ClienteleClassifRegle(version_id=vid, motif="règle")
        self._appliquer_payload(r, payload)
        return r

    def _appliquer_payload(self, r: ClienteleClassifRegle, payload: dict) -> None:
        critere_id = payload.get("critere_id")
        if not critere_id:
            raise AppError("critere_id obligatoire", 422, code="CRITERE_OBLIGATOIRE")
        niveau = (payload.get("niveau_cible") or "").upper()
        if niveau not in NIVEAUX:
            raise AppError("niveau_cible invalide", 422, code="NIVEAU_INVALIDE")
        op = (payload.get("operateur") or "").upper()
        if op not in OPERATEURS:
            raise AppError("opérateur invalide", 422, code="OPERATEUR_INVALIDE")
        champ = payload.get("champ_source") or "nationalite"
        portee = payload.get("portee") if payload.get("portee") in ("CLIENT", "COMPTE") else (
            "COMPTE" if champ in CHAMPS_COMPTE else "CLIENT")
        r.critere_id = uuid.UUID(str(critere_id))
        r.niveau_cible = niveau
        r.operateur = op
        r.champ_source = str(champ)[:40]
        r.portee = portee
        r.valeur = payload.get("valeur")
        r.motif = (payload.get("motif") or "").strip() or f"{champ} {op}"
        r.priorite = int(payload.get("priorite") or 100)
        r.poids = int(payload.get("poids") or 0)
        r.actif = bool(payload.get("actif", True))

    @staticmethod
    def _racine(valeur: str) -> str:
        racine = (valeur or "").strip()
        if len(racine) != 6 or not racine.isdigit():
            raise AppError("Racine client invalide (6 chiffres)", 422, code="RACINE_INVALIDE")
        return racine

    @staticmethod
    def _classif_dict(c: ClienteleClassification | None) -> dict | None:
        if not c:
            return None
        return {
            "racine_client": c.racine_client, "niveau": c.niveau,
            "source": c.source, "motifs": c.motifs or [],
            "motif_risque": c.motif_risque, "motif_classement": c.motif_classement,
            "version_id": str(c.version_id) if c.version_id else None,
            "classifie_le": c.classifie_le.isoformat() if c.classifie_le else None,
        }

    async def matrice_maitre(self) -> dict:
        self.ctx.exiger("clientele.classif.view")
        return matrice_maitre_dict()

    async def valeurs_maitres(self, *, dimension: str | None = None, statut: str | None = None,
                              page: int = 1, taille: int = 80) -> dict:
        self.ctx.exiger("clientele.classif.view")
        out = valeurs_maitre_dict(dimension=dimension, statut=statut, page=page, taille=taille)
        try:
            from app.models.clientele import ClienteleClassifValeur
            q = select(func.count()).select_from(ClienteleClassifValeur)
            n = await self.db.scalar(q)
            out["en_base"] = int(n or 0)
        except Exception:
            out["en_base"] = None
        return out

    async def divergences(self, *, domaine: str | None = None, page: int = 1, taille: int = 80) -> dict:
        self.ctx.exiger("clientele.classif.view")
        q = select(ClienteleClassifDivergence).order_by(
            ClienteleClassifDivergence.domaine, ClienteleClassifDivergence.cle)
        if domaine:
            q = q.where(ClienteleClassifDivergence.domaine == domaine)
        try:
            total = await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
            rows = list((await self.db.scalars(q.offset((page - 1) * taille).limit(min(taille, 200)))).all())
            if rows:
                return {
                    "total": int(total), "page": page, "taille": taille,
                    "sources_libelles": SOURCES_LIBELLES,
                    "items": [{
                        "id": str(d.id), "domaine": d.domaine, "cle": d.cle,
                        "source_a": d.source_a, "valeur_a": d.valeur_a,
                        "source_a_libelle": SOURCES_LIBELLES.get(d.source_a or "", d.source_a),
                        "source_b": d.source_b, "valeur_b": d.valeur_b,
                        "source_b_libelle": SOURCES_LIBELLES.get(d.source_b or "", d.source_b),
                        "statut": d.statut, "note": nommer(d.note), "decision": nommer(d.decision),
                    } for d in rows],
                }
        except Exception:
            pass
        brut = divergences_dict()
        items = brut["items"]
        if domaine:
            items = [x for x in items if x.get("domaine") == domaine]
        debut = (page - 1) * taille
        return {"total": len(items), "page": page, "taille": taille,
                "sources_libelles": SOURCES_LIBELLES,
                "items": [
                    {**x, "source_a_libelle": SOURCES_LIBELLES.get(x.get("source_a") or "", x.get("source_a")),
                     "source_b_libelle": SOURCES_LIBELLES.get(x.get("source_b") or "", x.get("source_b"))}
                    for x in items[debut:debut + taille]
                ]}

    async def evaluer_racine(self, racine: str, *, persister: bool = True) -> dict:
        """Évalue sans écrire la classification retenue (snapshot seulement)."""
        self.ctx.exiger("clientele.classif.view")
        racine = self._racine(racine)
        client = await self.db.scalar(
            select(ClienteleClient).where(ClienteleClient.racine_client == racine))
        if not client:
            raise AppError("Client introuvable", 404, code="NOT_FOUND")
        comptes = list((await self.db.scalars(
            select(ClienteleCompte).where(ClienteleCompte.racine_client == racine))).all())
        donnees = await self._collecter(client, comptes)
        ev = evaluer(donnees)
        payload = ev.to_dict()
        if persister:
            try:
                rec = ClienteleClassifEvaluation(
                    racine_client=racine,
                    version_moteur=ev.version_moteur,
                    version_regles=ev.version_regles,
                    mode=ev.mode,
                    score_total=ev.score_total,
                    nb_evalues=ev.nb_evalues,
                    niveau_score=ev.niveau_score,
                    niveau_score_v4=ev.niveau_score_v4,
                    niveau_max=ev.niveau_max,
                    niveau_final=ev.niveau_final,
                    statut=ev.statut,
                    coherence=ev.coherence,
                    motif_principal=ev.motif_principal,
                    detail={
                        "autres_facteurs": ev.autres_facteurs,
                        "blocking_proposes": ev.blocking_proposes,
                        "divergences": ev.divergences,
                        "avertissement": ev.avertissement,
                        "scores_familles": ev.scores_familles,
                        "motif_genere": ev.motif_genere,
                    },
                    created_by_id=self.ctx.user.id,
                )
                self.db.add(rec)
                await self.db.flush()
                for lg in ev.lignes:
                    self.db.add(ClienteleClassifEvaluationLigne(
                        evaluation_id=rec.id, **{
                            k: lg.to_dict()[k] for k in (
                                "critere", "libelle", "etat", "valeur", "source_donnee", "poids",
                                "niveau_matrice", "niveau_v4", "niveau_retenu", "type_decision",
                                "motif", "divergence", "blocking_propose", "statut_regle",
                                "famille", "contribue_au_score",
                            )
                        }))
                await self.db.flush()
                payload["evaluation_id"] = str(rec.id)
            except Exception:
                payload["evaluation_id"] = None
                payload["persistance"] = "TABLES_ABSENTES"
        payload["classification_courante"] = self._classif_dict(
            await self.db.get(ClienteleClassification, racine))
        return payload

    async def backtester(self, *, limite: int = 50) -> dict:
        """Compare le moteur proposition vs classification déjà stockée. Pas d'écriture de classe."""
        self.ctx.exiger("clientele.classif.execute")
        limite = max(1, min(int(limite), 500))
        racines = list((await self.db.scalars(
            select(ClienteleClassification.racine_client).order_by(
                ClienteleClassification.racine_client).limit(limite)
        )).all())
        if not racines:
            racines = list((await self.db.scalars(
                select(ClienteleClient.racine_client).order_by(ClienteleClient.racine_client).limit(limite)
            )).all())
        compteurs: dict[str, int] = {}
        echantillon: list[dict] = []
        for racine in racines:
            ev = await self.evaluer_racine(racine, persister=False)
            hist = (ev.get("classification_courante") or {}).get("niveau")
            nouveau = ev.get("niveau_final") or "NON_CLASSE"
            cle = f"{hist or 'ABSENT'}→{nouveau}"
            compteurs[cle] = compteurs.get(cle, 0) + 1
            if hist and nouveau != "NON_CLASSE" and hist != nouveau and len(echantillon) < 30:
                echantillon.append({
                    "racine_client": racine, "historique": hist, "moteur": nouveau,
                    "score": ev.get("score_total"), "coherence": ev.get("coherence"),
                    "motif": ev.get("motif_principal"), "statut": ev.get("statut"),
                })
        return {
            "limite": limite, "nb": len(racines), "compteurs": compteurs,
            "echantillon_ecarts": echantillon,
            "avertissement": (
                "Backtest sur copie de test uniquement. Moteur SCORE CDC 1.0. "
                "Aucune classification n'est écrasée."
            ),
        }

    async def _collecter(self, client: ClienteleClient, comptes: list[ClienteleCompte]) -> DonneesClient:
        listes = [c.liste_interdiction for c in comptes if c.liste_interdiction and c.liste_interdiction.strip()]
        ppe = procuration = pays = origine = eer_op = None
        eer_present = False
        try:
            dossier = await self.db.scalar(
                select(EerDossier)
                .where(EerDossier.racine_client == client.racine_client, EerDossier.deleted_at.is_(None))
                .options(selectinload(EerDossier.client), selectinload(EerDossier.parties))
                .order_by(EerDossier.date_eer.desc(), EerDossier.created_at.desc())
                .limit(1))
            if dossier:
                eer_present = True
                eer_op = dossier.operation_type
                origine = dossier.origine_fonds
                if dossier.ppe_dossier:
                    ppe = True
                parties = list(dossier.parties or [])
                for p in parties:
                    if p.role == "CLIENT" and p.ppe is not None:
                        ppe = p.ppe
                    if p.role == "MANDATAIRE" or p.forme_mandat == "PROCURATION":
                        procuration = True
                if procuration is None and parties:
                    procuration = False
                if getattr(dossier, "client", None) and getattr(dossier.client, "pays_residence", None):
                    pays = dossier.client.pays_residence
        except Exception:
            eer_present = False
        filtrage = None
        try:
            conf = await self.db.scalar(
                select(ClienteleAlerte.id).where(
                    ClienteleAlerte.racine_client == client.racine_client,
                    ClienteleAlerte.statut == "CONFIRMEE").limit(1))
            if conf:
                filtrage = True
        except Exception:
            filtrage = None
        return DonneesClient(
            racine=client.racine_client,
            nationalite=client.nationalite,
            statut_resident=client.statut_resident,
            categorie_juridique=client.categorie_juridique,
            situation_juridique=client.situation_juridique,
            secteur_activite=client.secteur_activite,
            famille_secteur=client.famille_secteur_activite,
            agent_economique=client.agent_economique,
            type_client=client.type_client,
            date_naissance=client.date_naissance,
            liste_interdiction=listes[0] if listes else ("" if comptes else None),
            ppe=ppe,
            procuration=procuration,
            pays_residence=pays,
            origine_fonds=origine,
            filtrage_confirme=filtrage,
            eer_present=eer_present,
            eer_operation=eer_op,
        )

    def _version_dict(self, v: ClienteleClassifVersion, *, avec_regles: bool) -> dict:
        out = {
            "id": str(v.id), "numero": v.numero, "libelle": v.libelle, "mode": v.mode,
            "seuils": v.seuils, "date_effet": v.date_effet.isoformat() if v.date_effet else None,
            "date_fin": v.date_fin.isoformat() if v.date_fin else None, "statut": v.statut,
        }
        if avec_regles:
            out["regles"] = [{
                "id": str(r.id), "critere_id": str(r.critere_id),
                "critere": r.critere.code if r.critere else None,
                "critere_libelle": r.critere.libelle if r.critere else None,
                "priorite": r.priorite, "poids": r.poids, "niveau_cible": r.niveau_cible,
                "operateur": r.operateur, "champ_source": r.champ_source, "portee": r.portee,
                "valeur": r.valeur, "motif": r.motif, "actif": r.actif,
            } for r in v.regles]
        return out
