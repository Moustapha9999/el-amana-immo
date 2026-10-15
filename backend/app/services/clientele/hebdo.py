"""Import hebdomadaire : décision humaine par ligne (accepter / modifier / rejeter), application, bilan.

Une proposition n'est jamais appliquée sans décision. Accepter ou modifier :
- nouveau client (racine absente) : fiche créée seulement à ce moment, source ``IMPORT_HEBDO`` (sans compte
  ORION, donc hors indicateurs et BCM) ; NNI / NIF déjà portés par une autre racine → refus ;
- données KYC absentes d'ORION mises à jour (jamais effacées par une valeur vide) ; une donnée ORION
  n'est jamais remplacée par le fichier ;
- classement écrit par le circuit manuel (``decider_manuel`` : forçage si blocage INTERDIT, réexamens clos).
Rejeter : rien n'est modifié, seule la décision est tracée. Chaque ligne est journalisée individuellement ;
une décision groupée (accepter / rejeter, 200 lignes max, motif obligatoire) partage un ``groupe_id``.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import (
    ClienteleClassifLot,
    ClienteleClassifLotLigne,
    ClienteleClassification,
    ClienteleClient,
    ClienteleJournal,
    ClienteleKyc,
    User,
)
from app.models.clientele import SOURCE_IMPORT_HEBDO
from app.services.clientele.classification import (
    NIVEAUX, SOURCES_MANUELLES, ClienteleClassificationService, trace_evaluation,
)
from app.services.clientele.journal import LIBELLES_ACTION, journaliser
from app.services.clientele.lots import (
    ALIAS_NOM, ClienteleLotService, exclusion_groupe, identifiant, lire_date, proposition,
    statut_decision, valeur_source,
)
from app.services.clientele.service import Ctx, ClienteleService, maintenant
from app.services.reporting_export import build_styled_workbook_multi

MAX_GROUPE = 200
DECISIONS = {"ACCEPTER": "ACCEPTEE", "MODIFIER": "MODIFIEE", "REJETER": "REJETEE"}
ACTIONS_JOURNAL = {"ACCEPTER": "ACCEPTATION", "MODIFIER": "MODIFICATION", "REJETER": "REJET"}
LIBELLES_DECISION = {"ACCEPTEE": "Acceptée", "MODIFIEE": "Modifiée", "REJETEE": "Rejetée",
                     "EN_ATTENTE": "En attente", "ANCIEN_CIRCUIT": "Ancien circuit"}
# Données KYC déclarées absentes d'ORION : (champ, colonnes du fichier, longueur max ou "date").
CHAMPS_KYC: tuple[tuple[str, tuple[str, ...], int | str], ...] = (
    ("date_eer", ("DATE EER", "DATE D EER"), "date"),
    ("profil", ("PROFIL",), 80),
    ("sous_profil", ("SOUS PROFIL", "SOUS_PROFIL"), 80),
    ("statut_gel", ("STATUT GEL",), 80),
)


def _fr(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    return str(v)


class ClienteleDecisionLotService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx
        self.svc = ClienteleService(db, ctx)
        self.lots = ClienteleLotService(db, ctx)
        self.classif = ClienteleClassificationService(db, ctx)

    # ------------------------------------------------------------------ décision
    async def decider(self, lid: uuid.UUID, payload: dict) -> dict:
        self.ctx.exiger("clientele.classif.execute")
        lot = await self.lots._charger(lid)
        if lot.statut == "FERME":
            raise AppError("Lot fermé : aucune décision possible", 409, code="LOT_FIGE")
        if lot.type != "LISTE":
            raise AppError("Décision par ligne réservée à l'import hebdomadaire (liste de clients)", 409,
                           code="TYPE_LOT")
        await self.lots.preparer(lot)
        action = (payload.get("decision") or "").upper()
        if action not in DECISIONS:
            raise AppError("Décision attendue : ACCEPTER, MODIFIER ou REJETER", 422, code="DECISION_INVALIDE")
        numeros = sorted({int(n) for n in (payload.get("lignes") or [])})
        if not numeros:
            raise AppError("Aucune ligne sélectionnée", 422, code="AUCUNE_LIGNE")
        groupe = len(numeros) > 1
        motif = (payload.get("motif") or "").strip()
        if groupe:
            if len(numeros) > MAX_GROUPE:
                raise AppError(f"Décision groupée limitée à {MAX_GROUPE} lignes ({len(numeros)} sélectionnées)",
                               422, code="GROUPE_TROP_GRAND")
            if action == "MODIFIER":
                raise AppError("La modification d'un classement se décide ligne par ligne", 422,
                               code="MODIFICATION_INDIVIDUELLE")
        if (groupe or action != "ACCEPTER") and not motif:
            raise AppError("Motif obligatoire" + (" pour une décision groupée" if groupe else ""), 422,
                           code="MOTIF_OBLIGATOIRE")
        L = ClienteleClassifLotLigne
        lignes = list((await self.db.scalars(
            select(L).where(L.lot_id == lid, L.ligne.in_(numeros)).order_by(L.ligne))).all())
        manquantes = sorted(set(numeros) - {x.ligne for x in lignes})
        if manquantes:
            raise AppError(f"Ligne(s) introuvable(s) : {', '.join(map(str, manquantes[:20]))}", 404,
                           code="NOT_FOUND")
        if groupe:
            exclues = [(x.ligne, r) for x in lignes if (r := exclusion_groupe(x))]
            if exclues:
                detail = " ; ".join(f"ligne {n} ({r})" for n, r in exclues[:10])
                raise AppError(f"{len(exclues)} ligne(s) à traiter individuellement : {detail}"
                               + (" …" if len(exclues) > 10 else ""), 409, code="EXCLUES_DU_GROUPE")
        groupe_id = uuid.uuid4() if groupe else None
        resultats = [await self._decider_ligne(lot, x, action, payload, motif, groupe_id, groupe)
                     for x in lignes]
        toutes = await self.lots._lignes(lid)
        lot.stats = self.lots._stats(toutes, ignorees=(lot.stats or {}).get("lignes_ignorees", 0))
        if lot.stats.get("en_attente") == 0:
            lot.statut = "ENREGISTRE"
        lot.updated_at = maintenant()
        await self.db.flush()
        await self.svc.audit(
            "clientele.lot.decision", "clientele_classif_lot", lid,
            after={"decision": action, "lignes": numeros, "groupe_id": str(groupe_id) if groupe_id else None,
                   "motif": motif or None, "resultats": resultats})
        return {"decision": DECISIONS[action], "groupe_id": str(groupe_id) if groupe_id else None,
                "resultats": resultats, "stats": lot.stats, "statut_lot": lot.statut}

    async def _decider_ligne(self, lot: ClienteleClassifLot, x: ClienteleClassifLotLigne, action: str,
                             payload: dict, motif: str, groupe_id: uuid.UUID | None, groupe: bool) -> dict:
        if statut_decision(x) != "EN_ATTENTE":
            raise AppError(f"Ligne {x.ligne} déjà décidée : la décision est conservée", 409, code="DEJA_DECIDE")
        prop = proposition(x)
        racine = x.racine_client
        analyste = ((payload.get("analyste_kyc") or "").strip() or (x.analyste_kyc or "").strip())[:120] or None
        commun = {"origine": "IMPORT", "lot_id": lot.id, "ligne": x.ligne, "groupe_id": groupe_id,
                  "analyste": analyste}
        niveau = None
        client_cree = False
        maj_kyc: list[str] = []
        if action != "REJETER":
            if x.statut not in ("OK", "INCONNUE"):
                raise AppError(f"Ligne {x.ligne} : {prop.get('raison') or 'identification à vérifier'} — "
                               "seul le rejet est possible", 409, code="REJET_SEUL")
            if not analyste:
                raise AppError(f"Ligne {x.ligne} : analyste KYC obligatoire", 422, code="ANALYSTE_OBLIGATOIRE")
            if action == "ACCEPTER":
                niveau = prop.get("niveau")
                if not niveau:
                    raise AppError(f"Ligne {x.ligne} : aucune proposition à accepter ({prop.get('raison')}). "
                                   "Modifiez (niveau + motif) ou rejetez.", 409, code="SANS_PROPOSITION")
                if prop.get("etat") == "A_VERIFIER" and not motif:
                    raise AppError(f"Ligne {x.ligne} : proposition à vérifier — motif obligatoire pour l'accepter",
                                   422, code="MOTIF_OBLIGATOIRE")
            else:
                niveau = (payload.get("niveau") or "").upper()
                if niveau not in NIVEAUX:
                    raise AppError("Niveau attendu : FAIBLE, MOYEN, ELEVE ou INTERDIT", 422, code="NIVEAU_INVALIDE")
            actuelle = await self.db.get(ClienteleClassification, racine) if x.statut == "OK" else None
            if actuelle and actuelle.source in SOURCES_MANUELLES and actuelle.niveau != niveau and not motif:
                raise AppError(f"Ligne {x.ligne} : classement manuel existant ({actuelle.niveau}) — motif "
                               "obligatoire pour le remplacer", 422, code="MOTIF_OBLIGATOIRE")
            if x.statut == "INCONNUE":
                client_cree = await self._creer_client(lot, x, analyste, groupe_id, motif)
            maj_kyc = await self._appliquer_kyc(lot, x, analyste, groupe_id)
        await journaliser(self.db, self.ctx, racine or "", "PROPOSITION", champ="classification",
                          avant=x.classe_actuelle, apres=prop.get("niveau") or prop.get("etat"),
                          motif=prop.get("raison"), detail=prop, **commun)
        if action == "REJETER":
            await journaliser(self.db, self.ctx, racine or "", "REJET", champ="classification",
                              avant=x.classe_actuelle, apres=prop.get("niveau"), motif=motif, detail={
                                  "proposition": prop.get("etat"), "statut_ligne": x.statut}, **commun)
        else:
            origine = {"FICHIER": "classe du fichier", "MOTEUR": "moteur SCORE"}.get(prop.get("origine") or "", "")
            motif_eff = motif or (f"Proposition acceptée ({origine}) — import « {lot.fichier_nom} », "
                                  f"ligne {x.ligne}")
            ev = trace_evaluation(await self.lots._ev_ligne(x)) if x.statut_moteur and x.evaluation_id else {}
            trace = {**ev, **self.lots._trace_ligne(lot, x), "analyste_kyc": analyste,
                     "_statut_moteur": x.statut_moteur}
            await self.classif.decider_manuel(
                racine, niveau, motif_eff, motif_risque=x.motif_source,
                forcer=bool(payload.get("forcer")) and not groupe, confirmation=bool(payload.get("confirmation")),
                trace=trace, type_action=ACTIONS_JOURNAL[action], groupe_id=groupe_id,
                detail_journal={"proposition": prop.get("etat"), "origine_proposition": prop.get("origine"),
                                "niveau_propose": prop.get("niveau")})
            k = await self.db.get(ClienteleClassification, racine)
            x.classe_actuelle = k.niveau if k else None
            x.source_actuelle = k.source if k else None
        x.decision = DECISIONS[action]
        detail = {
            "decision": x.decision, "niveau": niveau, "proposition": prop.get("niveau"),
            "etat_proposition": prop.get("etat"), "motif": motif or None, "analyste_kyc": analyste,
            "client_cree": client_cree, "maj_donnees": maj_kyc, "groupe_id": str(groupe_id) if groupe_id else None,
            "par": str(self.ctx.user.id), "par_nom": self.ctx.user.full_name or self.ctx.user.email,
            "le": maintenant().isoformat(),
        }
        x.decision_detail = {**(x.decision_detail or {}), "proposition": prop, "decision_ligne": detail}
        return {"ligne": x.ligne, "racine": racine, **{k: detail[k] for k in
                                                      ("decision", "niveau", "client_cree", "maj_donnees")}}

    async def _creer_client(self, lot: ClienteleClassifLot, x: ClienteleClassifLotLigne, analyste: str | None,
                            groupe_id: uuid.UUID | None, motif: str) -> bool:
        """Fiche d'un nouveau client, après acceptation. Aucune troncature ; identité ambiguë → refus."""
        self.ctx.exiger("clientele.import.execute")
        racine = x.racine_client
        if await self.db.scalar(select(ClienteleClient.id).where(ClienteleClient.racine_client == racine)):
            return False
        d = x.donnees or {}
        nom = valeur_source(d, *ALIAS_NOM) or x.nom
        if not nom:
            raise AppError(f"Ligne {x.ligne} : nom client absent — fiche non créée", 409, code="NOM_ABSENT")
        valeurs = {
            "raison_sociale": (nom, 255), "nni": (identifiant(valeur_source(d, "NNI")), 40),
            "nif": (identifiant(valeur_source(d, "NIF")), 40),
            "nationalite": (valeur_source(d, "NATIONNALITE", "NATIONALITE"), 80),
            "categorie_juridique": (valeur_source(d, "CATEGORIE JURIDIQUE"), 80),
        }
        trop_longs = [k for k, (v, n) in valeurs.items() if v and len(v) > n]
        if trop_longs:
            raise AppError(f"Ligne {x.ligne} : valeur trop longue ({', '.join(trop_longs)}) — fiche non créée "
                           "(aucune troncature)", 409, code="VALEUR_TROP_LONGUE")
        C = ClienteleClient
        conditions = [col == valeurs[k][0] for k, col in (("nni", C.nni), ("nif", C.nif)) if valeurs[k][0]]
        if conditions:
            autre = await self.db.scalar(select(C.racine_client).where(or_(*conditions)).limit(1))
            if autre:
                raise AppError(f"Ligne {x.ligne} : NNI / NIF déjà porté par la racine {autre} — identité à "
                               "vérifier, fiche non créée", 409, code="IDENTITE_AMBIGUE")
        periode = lot.periode_reference or date.today()
        self.db.add(ClienteleClient(
            racine_client=racine, **{k: v for k, (v, _) in valeurs.items()},
            source=SOURCE_IMPORT_HEBDO, premiere_extraction=periode, date_extraction=periode))
        await self.db.flush()
        await journaliser(
            self.db, self.ctx, racine, "CREATION", origine="IMPORT", champ="fiche", apres=nom,
            motif=motif or f"Nouveau client accepté — import « {lot.fichier_nom} », ligne {x.ligne}",
            analyste=analyste, lot_id=lot.id, ligne=x.ligne, groupe_id=groupe_id,
            detail={"source": SOURCE_IMPORT_HEBDO, "sans_compte_orion": True,
                    **{k: v for k, (v, _) in valeurs.items()}})
        return True

    async def _appliquer_kyc(self, lot: ClienteleClassifLot, x: ClienteleClassifLotLigne, analyste: str | None,
                             groupe_id: uuid.UUID | None) -> list[str]:
        """Données KYC absentes d'ORION : mises à jour champ par champ, jamais effacées par une valeur vide."""
        d = x.donnees or {}
        nouvelles: dict[str, object] = {}
        for champ, alias, borne in CHAMPS_KYC:
            brut = valeur_source(d, *alias)
            if not brut:
                continue
            if borne == "date":
                v = lire_date(brut)
                if isinstance(v, date):
                    nouvelles[champ] = v
            elif len(brut) <= borne:
                nouvelles[champ] = brut
        if x.date_maj_metier:
            nouvelles["date_maj_client"] = x.date_maj_metier
        if x.date_ouverture_entreprise:
            nouvelles["date_creation_entreprise"] = x.date_ouverture_entreprise
        if analyste:
            nouvelles["analyste_kyc"] = analyste
        kyc = await self.db.get(ClienteleKyc, x.racine_client)
        changes = [k for k, v in nouvelles.items() if getattr(kyc, k, None) != v]
        if not changes:
            return []
        if kyc is None:
            kyc = ClienteleKyc(racine_client=x.racine_client, source=SOURCE_IMPORT_HEBDO)
            self.db.add(kyc)
        for champ in changes:
            avant = getattr(kyc, champ, None)
            setattr(kyc, champ, nouvelles[champ])
            await journaliser(self.db, self.ctx, x.racine_client, "MAJ_DONNEES", origine="IMPORT", champ=champ,
                              avant=avant, apres=nouvelles[champ], analyste=analyste, lot_id=lot.id,
                              ligne=x.ligne, groupe_id=groupe_id)
        kyc.source = SOURCE_IMPORT_HEBDO
        kyc.lot_id, kyc.ligne_source = lot.id, x.ligne
        kyc.maj_par_id, kyc.maj_le = self.ctx.user.id, maintenant()
        await self.db.flush()
        return changes

    # ------------------------------------------------------------------ bilan
    async def bilan(self, lid: uuid.UUID) -> dict:
        lot = await self.lots._charger(lid)
        await self.lots.preparer(lot)
        lignes = await self.lots._lignes(lid)
        decisions = Counter(statut_decision(x) for x in lignes)
        J = ClienteleJournal
        operations = {t: int(n) for t, n in (await self.db.execute(
            select(J.type_action, func.count()).where(J.lot_id == lid).group_by(J.type_action))).all()}
        groupes = int(await self.db.scalar(
            select(func.count(func.distinct(J.groupe_id))).where(J.lot_id == lid, J.groupe_id.is_not(None))) or 0)
        auteur = await self.db.get(User, lot.created_by_id) if lot.created_by_id else None
        return {
            "lot": {
                "id": str(lot.id), "fichier_nom": lot.fichier_nom, "sha256": lot.sha256, "statut": lot.statut,
                "periode_reference": lot.periode_reference.isoformat() if lot.periode_reference else None,
                "importe_le": lot.created_at.isoformat() if lot.created_at else None,
                "importe_par": (auteur.full_name or auteur.email) if auteur else None,
                "fichier_disponible": self.lots._xlsx(lot.id).exists(),
            },
            "stats": lot.stats or {},
            "decisions": {k: decisions.get(k, 0) for k in LIBELLES_DECISION},
            "operations": {k: operations.get(k, 0) for k in LIBELLES_ACTION},
            "groupes": groupes,
            "clients_crees": sum(1 for x in lignes if ((x.decision_detail or {}).get("decision_ligne") or {})
                                 .get("client_cree")),
            "evaluation": lot.evaluation,
        }

    async def bilan_xlsx(self, lid: uuid.UUID) -> tuple[bytes, str]:
        b = await self.bilan(lid)
        lot = await self.lots._charger(lid)
        s, dec, ops = b["stats"], b["decisions"], b["operations"]
        synthese = [
            ("Fichier", lot.fichier_nom), ("Empreinte SHA-256", lot.sha256),
            ("Période", _fr(lot.periode_reference)), ("Importé par", b["lot"]["importe_par"]),
            ("Importé le", lot.created_at.strftime("%d/%m/%Y %H:%M") if lot.created_at else None),
            ("Lignes", s.get("lignes")), ("Clients reconnus", s.get("racines_ok")),
            ("Nouveaux clients", s.get("nouveaux")), ("Identités ambiguës", s.get("ambigus")),
            ("Doublons", s.get("doublons")), ("Racines invalides", s.get("invalides")),
            ("Données contradictoires", s.get("contradictions")), ("Lignes avec anomalie", s.get("avec_anomalie")),
            *[(f"Décision — {LIBELLES_DECISION[k]}", v) for k, v in dec.items()],
            ("Décisions groupées", b["groupes"]), ("Fiches clients créées", b["clients_crees"]),
            *[(f"Journal — {LIBELLES_ACTION[k]}", v) for k, v in ops.items()],
        ]
        lignes = []
        for x in await self.lots._lignes(lid):
            det = x.decision_detail or {}
            prop = det.get("proposition") or proposition(x)
            dl = det.get("decision_ligne") or {}
            lignes.append([
                x.ligne, x.racine_client or x.brut, x.nom, prop.get("etat"), prop.get("niveau"),
                prop.get("origine"), prop.get("raison"), prop.get("niveau_moteur"),
                "; ".join(x.anomalies or []) or None, x.analyste_kyc,
                LIBELLES_DECISION.get(statut_decision(x)), dl.get("niveau"), dl.get("motif"),
                dl.get("analyste_kyc"), dl.get("par_nom"), dl.get("le", "")[:16].replace("T", " ") or None,
                "Oui" if dl.get("client_cree") else None, dl.get("groupe_id"),
            ])
        J = ClienteleJournal
        journal = [[
            j.created_at.strftime("%d/%m/%Y %H:%M:%S") if j.created_at else None, j.racine_client,
            LIBELLES_ACTION.get(j.type_action, j.type_action), j.champ, j.ancienne_valeur, j.nouvelle_valeur,
            j.motif, j.analyste_kyc, j.ligne_source, str(j.groupe_id) if j.groupe_id else None, j.utilisateur_nom,
        ] for j in (await self.db.scalars(
            select(J).where(J.lot_id == lid).order_by(J.created_at, J.ligne_source))).all()]
        contenu = build_styled_workbook_multi(
            report_title="Import hebdomadaire — bilan",
            subtitle=lot.fichier_nom,
            sheets=[
                ("Synthèse", "Synthèse", ["Élément", "Valeur"], synthese),
                ("Lignes", "Lignes et décisions", [
                    "Ligne", "Racine", "Nom", "Proposition", "Niveau proposé", "Origine", "Raison",
                    "Niveau moteur", "Anomalies", "Analyste (fichier)", "Décision", "Niveau retenu", "Motif",
                    "Analyste KYC", "Décidé par", "Décidé le", "Fiche créée", "Groupe"], lignes),
                ("Journal", "Journal des opérations", [
                    "Date", "Racine", "Action", "Champ", "Ancienne valeur", "Nouvelle valeur", "Motif",
                    "Analyste KYC", "Ligne", "Groupe", "Utilisateur"], journal),
            ])
        return contenu, f"bilan-import-{(lot.periode_reference or date.today()).isoformat()}.xlsx"
