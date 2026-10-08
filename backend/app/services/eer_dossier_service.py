"""Service EER : persistance du cycle réel autour du moteur pur (``app.services.eer``).

Création du dossier → checklist dynamique → fiches pré-remplies → contrôles → décision
→ avis KYC → validation ; non-conformité → complément sur le même dossier, nouvelle version.

Le service vérifie lui-même les permissions reçues (le frontend n'est jamais une protection),
écrit l'historique + l'audit CORE, et ne fait que ``flush`` : l'appelant valide la transaction.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cached_property
from typing import Any

from fastapi import status
from sqlalchemy import Boolean, Date, Integer, Numeric, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.data.eer_referentiel import (
    CHAMPS_PAR_REGLE,
    FICHES,
    OPERATIONS_ACTIVES_V1,
    PARAMETRES_INITIAUX,
    TYPES_CLIENT,
)
from app.models import (
    Agence,
    EerAnomalie,
    EerChampEtat,
    EerChecklistItem,
    EerChecklistRegle,
    EerComplement,
    EerComplementElement,
    EerControle,
    EerDecision,
    EerDetention,
    EerDossier,
    EerDossierPartie,
    EerHistorique,
    EerParametre,
    EerPartie,
    EerPartieMorale,
    EerPartiePhysique,
    EerPieceIdentite,
    EerReferentiel,
    EerVersion,
    EerVisa,
    GedDocument,
    User,
)
from app.services import eer_notifications
from app.services.audit_service import AuditService
from app.services.eer import checklist_engine as ce
from app.services.eer import prefill
from app.services.eer.beneficiaires import Detention, ResultatBE, calculer_beneficiaires
from app.services.eer.conformite_engine import Anomalie, Decision, decider, proposer_anomalies
from app.services.eer.constantes import (
    ANOMALIES_OUVERTES,
    EtatChamp,
    GraviteAnomalie,
    Presence,
    ResultatAxe,
    RoleDossier,
    StatutAnomalie,
    StatutElement,
    TypeClient,
)
from app.services.eer.clientele_pont import apercu as apercu_clientele
from app.services.eer.clientele_pont import charger_client, normaliser_racine, propositions
from app.services.eer.faits import PartieDossier, construire_faits, faits_partie
from app.services.eer_access import EerScope, charger_permissions_eer, resolve_eer_access_scope
from app.services.eer_controles_auto import jours_parametre
from app.services.eer.workflow import (
    Demande,
    Etape,
    EtatDossier,
    Statut,
    TransitionRefusee,
    avancer_etape,
    etape_reprise,
    peut_relancer,
    verifier,
)

ESPACE_CODE = "audit-controle-conformite"
MODULE_CODE = "eer"
GED_ENTITE = "eer_dossier"

CHAMPS_PARTIE = {"nom", "nationalite", "pays_residence", "adresse", "telephone_1", "telephone_2", "telephone_3",
                 "email", "racine_client"}
CHAMPS_PHYSIQUE = {"sexe", "prenom", "prenom_pere", "date_naissance", "lieu_naissance", "situation_matrimoniale",
                   "profession", "employeur", "salaire_net", "date_embauche", "type_contrat"}
CHAMPS_MORALE = {"forme", "date_creation", "activites", "effectif", "rc_chronologique", "rc_analytique", "nif",
                 "residence_fiscale", "site_web", "numero_agrement", "impact_rse", "domaines_rse"}
CHAMPS_PIECE = {"type", "numero", "date_delivrance", "date_expiration", "pays_emission"}
CHAMPS_ROLE = {"forme_mandat", "lien_client", "fonction", "comptes_mandat", "ppe", "ppe_motif", "fatca_indice",
               "fatca_detail", "risque_lbcft", "gestionnaire_id", "responsable_agence_id", "ordre"}
CHAMPS_ROLE_PPE_FATCA = {"ppe", "ppe_motif", "fatca_indice", "fatca_detail", "risque_lbcft"}
CHAMPS_DOSSIER = {"date_eer", "racine_client", "numero_idp", "numero_idm", "numero_compte", "date_ouverture_compte",
                  "nombre_signataires", "type_signature", "tranche_mouvement_code", "origine_fonds",
                  "destination_fonds", "commentaire_profil", "risque_lbcft", "moment_controle", "etat_compte",
                  "sous_profil_code", "type_compte_code"}
ALIAS_DOSSIER = {"profil": "profil_code", "tranche_mouvement": "tranche_mouvement_code"}
TYPES_SIGNATURE = ("UNIQUE", "CONJOINTES", "SEPAREES")
# Champs à valeur codée (contrainte SQL) : saisie contrôlée contre le référentiel EER → message clair.
DOMAINE_PAR_CHAMP = {"type_signature": "TYPE_SIGNATURE", "forme_mandat": "FORME_MANDAT"}
CHEMINS_LECTURE_SEULE = {"dossier.agence_code", "dossier.operation_type", "dossier.profil"}
FICHE_PAR_TYPE = {TypeClient.PP: "FICHE_PP", TypeClient.PM_PRIVEE: "FICHE_PM_PRIVEE",
                  TypeClient.PM_PUBLIQUE: "FICHE_PM_PUBLIQUE", TypeClient.ASSOCIATION: "FICHE_ASSOCIATION"}
EVENEMENTS_VERSION = {Statut.SOUMIS, Statut.RESOUMIS, Statut.CONFORME, Statut.NON_CONFORME, Statut.AVIS_CONFORMITE,
                      Statut.VALIDE, Statut.CLOTURE, Statut.ABANDONNE, Statut.A_COMPLETER}


class EerErreur(AppError):
    """Règle métier refusée (400)."""

    def __init__(self, message: str):
        super().__init__(message, status.HTTP_400_BAD_REQUEST, code="EER_REGLE_METIER")


class EerAccesRefuse(AppError):
    """Permission, périmètre ou séparation des rôles (403)."""

    def __init__(self, message: str):
        super().__init__(message, status.HTTP_403_FORBIDDEN, code="EER_ACCES_REFUSE")


class EerIntrouvable(AppError):
    """Dossier absent ou hors périmètre agence (404 : l'existence n'est pas révélée)."""

    def __init__(self, message: str = "Dossier EER introuvable"):
        super().__init__(message, status.HTTP_404_NOT_FOUND, code="EER_INTROUVABLE")


class EerConflit(AppError):
    """Révision périmée : le dossier a été modifié entre-temps (409)."""

    def __init__(self, attendue: int, actuelle: int):
        super().__init__(
            f"Le dossier a été modifié entre-temps (révision {actuelle}, attendue {attendue}). "
            "Rechargez-le avant de recommencer.",
            status.HTTP_409_CONFLICT, code="EER_CONFLIT_REVISION")
        self.attendue, self.actuelle = attendue, actuelle


@dataclass(frozen=True)
class Acteur:
    user: User
    permissions: frozenset[str]
    session_id: uuid.UUID | None = None
    ip_address: str | None = None

    @cached_property
    def perimetre(self) -> EerScope:
        return resolve_eer_access_scope(self.user, self.permissions)

    def exiger(self, *codes: str) -> None:
        manquantes = [c for c in codes if not self.perimetre.peut(c)]
        if manquantes:
            raise EerAccesRefuse("Permission requise : " + ", ".join(manquantes))

    def exiger_perimetre(self, d: EerDossier) -> None:
        if not self.perimetre.couvre(d.agence_id):
            raise EerIntrouvable()


@dataclass
class CibleComplement:
    item_ids: list[uuid.UUID] = field(default_factory=list)
    anomalie_ids: list[uuid.UUID] = field(default_factory=list)
    champs: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.item_ids) + len(self.anomalie_ids) + len(self.champs)


def _maintenant() -> datetime:
    return datetime.now(UTC)


def _serialiser(valeur: Any) -> Any:
    if isinstance(valeur, dict):
        return {str(k): _serialiser(v) for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple, set)):
        return [_serialiser(v) for v in valeur]
    if isinstance(valeur, (uuid.UUID, Decimal)):
        return str(valeur)
    if isinstance(valeur, (date, datetime)):
        return valeur.isoformat()
    return valeur


def _ligne(obj: Any, exclure: Collection[str] = ()) -> dict[str, Any]:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns if c.key not in exclure}


def _convertir(colonne, valeur: Any) -> Any:
    if valeur is None or valeur == "":
        return None
    type_ = colonne.type
    if isinstance(type_, Boolean):
        if not isinstance(valeur, bool):
            raise EerErreur(f"{colonne.key} : booléen attendu")
        return valeur
    if isinstance(type_, Date) and isinstance(valeur, str):
        try:
            return date.fromisoformat(valeur)
        except ValueError as exc:
            raise EerErreur(f"{colonne.key} : date invalide") from exc
    if isinstance(type_, Numeric) and not isinstance(valeur, Decimal):
        try:
            return Decimal(str(valeur))
        except ArithmeticError as exc:
            raise EerErreur(f"{colonne.key} : nombre invalide") from exc
    if isinstance(type_, Integer) and not isinstance(valeur, int):
        try:
            return int(valeur)
        except (TypeError, ValueError) as exc:
            raise EerErreur(f"{colonne.key} : entier invalide") from exc
    if colonne.key.endswith("_id") and isinstance(valeur, str):
        return uuid.UUID(valeur)
    if isinstance(valeur, str):
        return valeur.strip()
    return valeur


def _affecter(obj: Any, data: dict[str, Any], autorises: Collection[str]) -> None:
    inconnus = set(data) - set(autorises)
    if inconnus:
        raise EerErreur(f"Champs non autorisés : {sorted(inconnus)}")
    colonnes = obj.__table__.columns
    for cle, valeur in data.items():
        setattr(obj, cle, _convertir(colonnes[cle], valeur))


class EerDossierService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    # --- Paramètres, référentiels, règles -------------------------------------------------

    async def parametres(self, a_date: date | None = None) -> dict[str, Any]:
        a_date = a_date or date.today()
        lignes = (await self.db.execute(
            select(EerParametre).where(EerParametre.date_effet <= a_date)
            .order_by(EerParametre.code, EerParametre.date_effet.desc())
        )).scalars()
        valeurs: dict[str, Any] = {}
        for p in lignes:
            valeurs.setdefault(p.code, p.valeur)
        manquants = set(PARAMETRES_INITIAUX) - set(valeurs)
        if "be.seuil_pourcentage" in manquants or "workflow.separation_roles" in manquants:
            raise EerErreur("Référentiel EER non initialisé (scripts/eer_init_referentiel.py)")
        return valeurs

    async def separation_active(self, d: EerDossier) -> bool:
        """Séparation des rôles : figée sur le dossier ET encore en vigueur (paramètre daté).
        Désactiver le paramètre la lève donc aussi sur les dossiers déjà ouverts."""
        if not d.parametres_snapshot.get("workflow.separation_roles", True):
            return False
        return bool((await self.parametres()).get("workflow.separation_roles", True))

    async def _referentiel(self, domaine: str, code: str) -> EerReferentiel | None:
        return await self.db.scalar(select(EerReferentiel).where(
            EerReferentiel.domaine == domaine, EerReferentiel.code == code, EerReferentiel.actif.is_(True)))

    async def _regles_actives(self) -> dict[str, tuple[EerChecklistRegle, ce.Regle]]:
        lignes = (await self.db.execute(
            select(EerChecklistRegle).where(EerChecklistRegle.date_effet <= date.today())
            .order_by(EerChecklistRegle.code, EerChecklistRegle.version.desc())
        )).scalars()
        regles: dict[str, tuple[EerChecklistRegle, ce.Regle]] = {}
        for r in lignes:
            if r.code in regles:
                continue
            regles[r.code] = (r, ce.Regle(
                code=r.code, libelle=r.libelle, categorie=r.categorie, axe=r.axe, nature=r.nature,
                condition=r.condition, portee=r.portee, role_cible=r.role_cible, obligatoire=r.obligatoire,
                ordre=r.ordre, type_controle=r.type_controle, document_type=r.document_type_code,
                version=r.version, actif=r.actif))
        return regles

    async def prochaine_reference(self, annee: int | None = None) -> str:
        annee = annee or date.today().year
        numero = await self.db.scalar(text(
            "INSERT INTO eer_reference_compteurs (annee, dernier) VALUES (:a, 1) "
            "ON CONFLICT (annee) DO UPDATE SET dernier = eer_reference_compteurs.dernier + 1 "
            "RETURNING dernier"), {"a": annee})
        return f"EER-{annee}-{numero:06d}"

    # --- Chargement -----------------------------------------------------------------------

    async def charger(self, dossier_id: uuid.UUID, *, verrou: bool = False,
                      acteur: Acteur | None = None) -> EerDossier:
        """Charge le dossier ; avec ``acteur``, refuse (404) un dossier hors de son périmètre agence."""
        stmt = select(EerDossier).where(EerDossier.id == dossier_id).options(
            selectinload(EerDossier.parties).selectinload(EerDossierPartie.partie),
            selectinload(EerDossier.items))
        if verrou:
            stmt = stmt.with_for_update(of=EerDossier)
        dossier = await self.db.scalar(stmt.execution_options(populate_existing=True))
        if dossier is None or dossier.deleted_at is not None:
            raise EerIntrouvable()
        if acteur is not None:
            acteur.exiger_perimetre(dossier)
        return dossier

    async def verrouiller(self, acteur: Acteur, dossier_id: uuid.UUID, revision: int) -> EerDossier:
        """Verrou pessimiste (FOR UPDATE) + contrôle optimiste de la révision connue du client.

        Deux agents qui partent de la même révision : le second reçoit un 409 au lieu
        d'écraser silencieusement le travail du premier. La révision est incrémentée dans
        la même transaction que la mutation (annulée avec elle en cas d'échec).
        """
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        if d.revision != revision:
            raise EerConflit(revision, d.revision)
        d.revision += 1
        await self.db.flush()
        return d

    async def supprimer(self, acteur: Acteur, dossier_id: uuid.UUID, revision: int, motif: str | None) -> EerDossier:
        """Suppression logique (décision du 04/10/2026) : le dossier sort des listes et de l'API ;
        versions, historique, décisions et visas restent en base (tables immuables)."""
        if not acteur.perimetre.peut("eer.admin"):
            raise EerAccesRefuse("Suppression réservée aux agents du module EER")
        if not motif or not motif.strip():
            raise EerErreur("Motif de suppression obligatoire")
        d = await self.verrouiller(acteur, dossier_id, revision)
        await self._historique(d, acteur, "SUPPRESSION", de=d.statut, vers=d.statut, motif=motif.strip())
        d.deleted_at = _maintenant()
        d.deleted_by_id = acteur.user.id
        d.motif_suppression = motif.strip()
        await self.db.flush()
        await self._audit(acteur, "eer.dossier.delete", d, before={"statut": d.statut}, after={"supprime": True})
        return d

    # --- Parties ---------------------------------------------------------------------------

    async def _partie(self, nature: str, data: dict[str, Any], acteur: Acteur) -> EerPartie:
        data = dict(data)
        piece = data.pop("piece", None)
        physique = data.pop("pp", None) or {}
        morale = data.pop("pm", None) or {}
        if piece:
            if set(piece) - CHAMPS_PIECE:
                raise EerErreur(f"Champs pièce non autorisés : {sorted(set(piece) - CHAMPS_PIECE)}")
            existante = await self.db.scalar(select(EerPieceIdentite).where(
                EerPieceIdentite.type_piece == piece.get("type"),
                EerPieceIdentite.numero == str(piece.get("numero", "")).strip(),
                EerPieceIdentite.pays_emission.is_not_distinct_from(piece.get("pays_emission"))))
            if existante is not None:
                # Même pièce = même personne : réutilisée sans ressaisie (saisie unique).
                return await self.db.get(EerPartie, existante.partie_id)
        if not str(data.get("nom", "")).strip():
            raise EerErreur("Nom / raison sociale obligatoire")
        partie = EerPartie(nature=nature, created_by_id=acteur.user.id)
        _affecter(partie, data, CHAMPS_PARTIE)
        if nature == "PHYSIQUE":
            partie.physique = EerPartiePhysique()
            _affecter(partie.physique, physique, CHAMPS_PHYSIQUE)
        else:
            partie.morale = EerPartieMorale()
            _affecter(partie.morale, morale, CHAMPS_MORALE)
        if piece:
            p = EerPieceIdentite(type_piece=piece.get("type"), numero=str(piece.get("numero", "")).strip())
            _affecter(p, {k: v for k, v in piece.items() if k not in {"type", "numero"}}, CHAMPS_PIECE)
            if not p.type_piece or not p.numero:
                raise EerErreur("Pièce d'identité : type et numéro obligatoires")
            partie.pieces.append(p)
        self.db.add(partie)
        await self.db.flush()
        return partie

    def _verifier_role_attrs(self, role: RoleDossier, attrs: dict[str, Any]) -> None:
        if role not in (RoleDossier.CLIENT, RoleDossier.MANDATAIRE) and set(attrs) & CHAMPS_ROLE_PPE_FATCA:
            raise EerErreur("PPE / FATCA / risque : uniquement sur les fiches client et mandataire")

    # --- Création --------------------------------------------------------------------------

    async def creer_dossier(self, acteur: Acteur, *, agence_id: uuid.UUID, type_client: str, profil: str,
                            client: dict[str, Any], client_role: dict[str, Any] | None = None,
                            dossier: dict[str, Any] | None = None,
                            operation_type: str = "ENTREE_RELATION") -> EerDossier:
        acteur.exiger("eer.create")
        if operation_type not in OPERATIONS_ACTIVES_V1:
            raise EerErreur("V1 : seule l'entrée en relation est ouverte")
        if await self._referentiel("TYPE_CLIENT", type_client) is None:
            raise EerErreur(f"Type client inconnu : {type_client}")
        ref_profil = await self._referentiel("PROFIL", profil)
        ref_type = await self._referentiel("TYPE_CLIENT", type_client)
        if ref_profil is None or ref_profil.parent_id != ref_type.id:
            raise EerErreur(f"Profil {profil} invalide pour le type {type_client}")
        if not acteur.perimetre.couvre(agence_id):
            raise EerAccesRefuse("Création hors de votre périmètre agence")
        agence = await self.db.get(Agence, agence_id)
        if agence is None or not agence.is_active:
            raise EerErreur("Agence inconnue ou inactive")
        client_role = client_role or {}
        if not TYPES_CLIENT[TypeClient(type_client)]["ppe_fatca"] and set(client_role) & {"ppe", "fatca_indice"}:
            raise EerErreur("La fiche de ce type ne comporte ni PPE ni FATCA")

        racine = normaliser_racine(
            client.get("racine_client") or (dossier or {}).get("racine_client"))
        if racine:
            client = {**client, "racine_client": racine}
            dossier = {**(dossier or {}), "racine_client": racine}

        nature = "PHYSIQUE" if type_client == TypeClient.PP else "MORALE"
        partie = await self._partie(nature, client, acteur)
        params = await self.parametres()
        d = EerDossier(
            reference=await self.prochaine_reference(), operation_type=operation_type, agence_id=agence.id,
            type_client_code=type_client, profil_code=profil, client_partie_id=partie.id,
            date_eer=date.today(), statut=Statut.BROUILLON, created_by_id=acteur.user.id,
            parametres_snapshot=_serialiser(params), version_courante=1, nb_relances=0,
            moment_controle="PREALABLE", ppe_dossier=False, fatca_dossier=False, avis_requis=False)
        _affecter(d, dossier or {}, CHAMPS_DOSSIER)
        d.racine_client = d.racine_client or partie.racine_client
        await self._verifier_codes_dossier(d)
        self.db.add(d)
        await self.db.flush()

        dp = EerDossierPartie(dossier_id=d.id, partie_id=partie.id, role=RoleDossier.CLIENT, ordre=0)
        _affecter(dp, client_role, CHAMPS_ROLE)
        self.db.add(dp)
        await self.db.flush()

        await self._historique(d, acteur, "CREATION", vers=Statut.BROUILLON)
        await self._audit(acteur, "eer.dossier.create", d, after={"reference": d.reference, "type": type_client})
        dossier_charge = await self.charger(d.id)
        await self.synchroniser(dossier_charge, acteur, journaliser=False)
        if racine:
            await self.prefill_depuis_clientele(acteur, dossier_charge.id, racine, ignorer_absent=True)
            dossier_charge = await self.charger(d.id)
        return dossier_charge

    async def _verifier_codes_dossier(self, d: EerDossier) -> None:
        if d.risque_lbcft is not None and d.risque_lbcft not in ("FAIBLE", "MOYEN", "ELEVE"):
            raise EerErreur("Risque LBC-FT : FAIBLE, MOYEN ou ELEVE")
        if d.type_signature is not None and d.type_signature not in TYPES_SIGNATURE:
            raise EerErreur("Type de signature : UNIQUE, CONJOINTES ou SEPAREES")
        domaine_tranche = "TRANCHE_PP" if d.type_client_code == TypeClient.PP else "TRANCHE_PM"
        for domaine, code in ((domaine_tranche, d.tranche_mouvement_code), ("ETAT_COMPTE", d.etat_compte)):
            if code is not None and await self._referentiel(domaine, code) is None:
                raise EerErreur(f"Code {code} inconnu ({domaine})")

    def _verifier_modifiable(self, acteur: Acteur, d: EerDossier) -> None:
        if d.statut == Statut.BROUILLON:
            acteur.exiger("eer.update")
        elif d.statut == Statut.EN_CONTROLE:
            acteur.exiger("eer.control")
            if d.analyste_id and d.analyste_id != acteur.user.id:
                raise EerAccesRefuse("Seul l'analyste affecté modifie le dossier en contrôle")
        elif d.statut == Statut.A_COMPLETER:
            acteur.exiger("eer.complement.receive")
        else:
            raise EerErreur(f"Dossier non modifiable à l'état {d.statut}")

    async def ajouter_partie(self, acteur: Acteur, dossier_id: uuid.UUID, role: str, partie: dict[str, Any],
                             role_attrs: dict[str, Any] | None = None, *, nature: str = "PHYSIQUE",
                             partie_id: uuid.UUID | None = None) -> EerDossierPartie:
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._verifier_modifiable(acteur, d)
        role = RoleDossier(role)
        if role == RoleDossier.CLIENT:
            raise EerErreur("Le client est fixé à la création du dossier")
        role_attrs = role_attrs or {}
        self._verifier_role_attrs(role, role_attrs)
        if role == RoleDossier.MANDATAIRE and nature != "PHYSIQUE":
            raise EerErreur("Un mandataire est une personne physique (fiche mandataire)")
        if role in (RoleDossier.ACTIONNAIRE,) and d.type_client_code not in (TypeClient.PM_PRIVEE,
                                                                              TypeClient.PM_PUBLIQUE):
            raise EerErreur("Actionnariat : uniquement PM privée et PM publique")
        p = await self.db.get(EerPartie, partie_id) if partie_id else await self._partie(nature, partie, acteur)
        if p is None:
            raise EerErreur("Partie introuvable")
        if any(x.partie_id == p.id and x.role == role for x in d.parties):
            raise EerErreur("Cette partie a déjà ce rôle dans le dossier")
        dp = EerDossierPartie(dossier_id=d.id, partie_id=p.id, role=role, ordre=len(d.parties))
        _affecter(dp, role_attrs, CHAMPS_ROLE)
        self.db.add(dp)
        await self.db.flush()
        await self._historique(d, acteur, "PARTIE_AJOUTEE", details={"role": role, "partie_id": str(p.id)})
        await self._audit(acteur, "eer.partie.add", d, after={"role": role, "partie_id": str(p.id)})
        await self.synchroniser(await self.charger(d.id), acteur)
        return dp

    # --- Checklist dynamique --------------------------------------------------------------

    def _parties_moteur(self, d: EerDossier) -> list[PartieDossier]:
        return [PartieDossier(str(dp.id), RoleDossier(dp.role), {
            "ppe": dp.ppe, "fatca_indice": dp.fatca_indice, "risque_lbcft": dp.risque_lbcft,
            "nature": dp.partie.nature}) for dp in d.parties]

    def _faits(self, d: EerDossier) -> dict[str, Any]:
        morale = d.client.morale if d.client else None
        base = {
            "type_client": d.type_client_code, "profil": d.profil_code, "sous_profil": d.sous_profil_code,
            "type_compte": d.type_compte_code, "operation_type": d.operation_type, "risque": d.risque_lbcft,
            "etat_compte": d.etat_compte, "racine_client": d.racine_client,
            "impact_rse": morale.impact_rse if morale else None,
        }
        return construire_faits(base, self._parties_moteur(d))

    @staticmethod
    def _element(item: EerChecklistItem) -> ce.Element:
        return ce.Element(
            regle_code=item.regle_code, partie_id=str(item.dossier_partie_id) if item.dossier_partie_id else None,
            axe=item.axe, nature=item.nature, obligatoire=item.obligatoire, statut=StatutElement(item.statut),
            presence=Presence(item.presence) if item.presence else None, motif=item.motif,
            neutralise_auto=item.neutralise_auto, derogation_acceptee=item.derogation_acceptee)

    async def synchroniser(self, d: EerDossier, acteur: Acteur, *, journaliser: bool = True) -> ce.PlanRegeneration:
        """Recalcule les faits et la checklist ; n'efface jamais un élément."""
        faits = self._faits(d)
        d.ppe_dossier = bool(faits["ppe"])
        d.fatca_dossier = bool(faits["fatca_indice"])
        d.avis_requis = bool(faits["avis_kyc_requis"])
        if faits["risque"] != d.risque_lbcft:
            d.risque_lbcft = faits["risque"]

        regles = await self._regles_actives()
        attendus = ce.generer([r for _, r in regles.values()], faits, self._parties_moteur(d))
        items = {(i.regle_code, str(i.dossier_partie_id) if i.dossier_partie_id else None): i for i in d.items}
        plan = ce.regenerer([self._element(i) for i in items.values()], attendus)

        motifs = dict(plan.a_neutraliser)
        for cle, item in items.items():
            if cle in motifs:
                item.statut, item.motif, item.neutralise_auto = StatutElement.NON_APPLICABLE, motifs[cle], True
            elif cle in plan.a_reactiver:
                item.statut, item.presence, item.motif, item.neutralise_auto = (
                    StatutElement.NON_CONTROLE, None, None, False)
        for attendu in plan.a_creer:
            ligne, regle = regles[attendu.regle.code]
            d.items.append(EerChecklistItem(
                dossier_id=d.id, regle_id=ligne.id, regle_code=regle.code, regle_version=regle.version,
                dossier_partie_id=uuid.UUID(attendu.partie_id) if attendu.partie_id else None,
                libelle=regle.libelle, categorie=regle.categorie, axe=regle.axe, nature=regle.nature,
                obligatoire=regle.obligatoire, ordre=regle.ordre, statut=StatutElement.NON_CONTROLE,
                neutralise_auto=False, derogation_acceptee=False,
                raison_applicabilite=list(attendu.explication)))
        await self.db.flush()
        if journaliser and plan.modifie:
            await self._historique(d, acteur, "CHECKLIST_REGENEREE", details={
                "ajoutes": [a.regle.code for a in plan.a_creer],
                "neutralises": [c[0] for c, _ in plan.a_neutraliser],
                "reactives": [c[0] for c in plan.a_reactiver]})
        return plan

    async def regenerer_checklist(self, acteur: Acteur, dossier_id: uuid.UUID) -> ce.PlanRegeneration:
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._verifier_modifiable(acteur, d)
        return await self.synchroniser(d, acteur)

    async def _item(self, acteur: Acteur, item_id: uuid.UUID) -> tuple[EerDossier, EerChecklistItem]:
        item = await self.db.get(EerChecklistItem, item_id)
        if item is None:
            raise EerIntrouvable("Élément de checklist introuvable")
        d = await self.charger(item.dossier_id, verrou=True, acteur=acteur)
        return d, next(i for i in d.items if i.id == item_id)

    async def _document(self, d: EerDossier, document_id: uuid.UUID | None) -> uuid.UUID | None:
        """Pièce de la GED CORE rattachée à ce dossier (jamais un document d'un autre module)."""
        if document_id is None:
            return None
        doc = await self.db.get(GedDocument, document_id)
        if (doc is None or doc.deleted_at is not None or doc.module_code != MODULE_CODE
                or doc.entity != GED_ENTITE or doc.entity_id != str(d.id)):
            raise EerErreur("Document GED inconnu ou non rattaché à ce dossier")
        return doc.id

    def _exiger_controle(self, acteur: Acteur, d: EerDossier, etapes: Collection[Etape]) -> None:
        acteur.exiger("eer.control")
        if d.statut != Statut.EN_CONTROLE:
            raise EerErreur("Le dossier n'est pas en contrôle")
        if d.analyste_id != acteur.user.id:
            raise EerAccesRefuse("Seul l'analyste affecté contrôle le dossier")
        if d.etape not in etapes:
            raise EerErreur(f"Action impossible à l'étape {d.etape}")

    async def pointer(self, acteur: Acteur, item_id: uuid.UUID, presence: str, motif: str | None = None,
                      document_id: uuid.UUID | None = None) -> EerChecklistItem:
        d, item = await self._item(acteur, item_id)
        self._exiger_controle(acteur, d, {Etape.CHECKLIST})
        try:
            e = ce.pointer(self._element(item), Presence(presence), motif)
        except ce.ErreurChecklist as exc:
            raise EerErreur(str(exc)) from exc
        item.presence, item.statut, item.motif = e.presence, e.statut, e.motif
        item.document_id = await self._document(d, document_id) or item.document_id
        item.pointe_par_id, item.pointe_le = acteur.user.id, _maintenant()
        await self.db.flush()
        return item

    async def valider_checklist(self, acteur: Acteur, dossier_id: uuid.UUID) -> EerDossier:
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._exiger_controle(acteur, d, {Etape.CHECKLIST})
        non_pointes = ce.elements_non_pointes(self._element(i) for i in d.items)
        try:
            avancer_etape(Etape.CHECKLIST, elements_non_pointes=len(non_pointes))
        except TransitionRefusee as exc:
            raise EerErreur(str(exc)) from exc
        d.etape = Etape.FICHES
        await self._historique(d, acteur, "CHECKLIST_VALIDEE", etape=Etape.CHECKLIST_VALIDEE)
        await self.db.flush()
        return d

    async def controler(self, acteur: Acteur, item_id: uuid.UUID, conforme: bool, motif: str | None = None,
                        motif_code: str | None = None) -> EerChecklistItem:
        d, item = await self._item(acteur, item_id)
        self._exiger_controle(acteur, d, {Etape.CONTROLES})
        try:
            e = ce.controler(self._element(item), conforme, motif)
        except ce.ErreurChecklist as exc:
            raise EerErreur(str(exc)) from exc
        item.statut, item.motif = e.statut, e.motif
        item.motif_code = None if conforme else motif_code
        item.controle_par_id, item.controle_le = acteur.user.id, _maintenant()
        self.db.add(EerControle(dossier_id=d.id, item_id=item.id, code=item.regle_code, type_controle="MANUEL",
                                resultat=item.statut, detail={"motif": item.motif, "motif_code": item.motif_code},
                                version=d.version_courante, execute_par_id=acteur.user.id))
        await self.db.flush()
        return item

    # --- Fiches pré-remplies --------------------------------------------------------------

    def _source_partie(self, p: EerPartie) -> dict[str, Any]:
        source = {k: getattr(p, k) for k in CHAMPS_PARTIE}
        if p.physique:
            source["pp"] = {k: getattr(p.physique, k) for k in CHAMPS_PHYSIQUE}
        if p.morale:
            source["pm"] = {k: getattr(p.morale, k) for k in CHAMPS_MORALE}
        piece = p.pieces[-1] if p.pieces else None
        if piece:
            source["piece"] = {"type": piece.type_piece, "numero": piece.numero,
                               "date_delivrance": piece.date_delivrance, "date_expiration": piece.date_expiration,
                               "pays_emission": piece.pays_emission}
        return source

    async def _source(self, d: EerDossier, dp: EerDossierPartie | None = None) -> dict[str, Any]:
        agence = await self.db.get(Agence, d.agence_id)
        dossier = {k: getattr(d, k) for k in CHAMPS_DOSSIER}
        dossier.update(operation_type=d.operation_type, agence_code=agence.code if agence else None,
                       profil=d.profil_code, tranche_mouvement=d.tranche_mouvement_code)
        client_dp = next(x for x in d.parties if x.role == RoleDossier.CLIENT)
        client = self._source_partie(client_dp.partie)
        client.update({k: getattr(client_dp, k) for k in ("ppe", "ppe_motif", "fatca_indice")})
        source = {"dossier": dossier, "client": client}
        if dp is not None:
            source["partie"] = self._source_partie(dp.partie)
            source["role"] = {k: getattr(dp, k) for k in CHAMPS_ROLE}
        return source

    async def _etats(self, d: EerDossier, dp_id: uuid.UUID | None
                     ) -> tuple[dict[str, prefill.EtatEnregistre], dict[str, str]]:
        lignes = list((await self.db.execute(select(EerChampEtat).where(
            EerChampEtat.dossier_id == d.id, EerChampEtat.dossier_partie_id.is_not_distinct_from(dp_id)))).scalars())
        etats = {e.chemin: prefill.EtatEnregistre(EtatChamp(e.etat), e.empreinte) for e in lignes}
        origines = {e.chemin: e.source for e in lignes if e.source}
        return etats, origines

    async def fiches(self, dossier_id: uuid.UUID) -> dict[str, list[prefill.ChampFiche]]:
        d = await self.charger(dossier_id)
        faits = self._faits(d)
        source = await self._source(d)
        etats, origines = await self._etats(d, None)
        resultat = {
            code: prefill.pre_remplir(FICHES[code], source, faits, etats=etats, origines=origines)
            for code in (FICHE_PAR_TYPE[TypeClient(d.type_client_code)], "SPECIMEN_SIGNATURE")
        }
        for dp in d.parties:
            if dp.role == RoleDossier.MANDATAIRE:
                pd = next(p for p in self._parties_moteur(d) if p.partie_id == str(dp.id))
                et, orig = await self._etats(d, dp.id)
                resultat[f"FICHE_MANDATAIRE:{dp.id}"] = prefill.pre_remplir(
                    FICHES["FICHE_MANDATAIRE"], await self._source(d, dp), faits_partie(faits, pd),
                    etats=et, origines=orig)
        return resultat

    async def donnees_connues(self, dossier_id: uuid.UUID) -> dict[uuid.UUID, bool | None]:
        """Colonne « Donnée connue » de la checklist, déduite des fiches (``CHAMPS_PAR_REGLE``)."""
        d = await self.charger(dossier_id)
        fiches = await self.fiches(dossier_id)
        resultat: dict[uuid.UUID, bool | None] = {}
        for item in d.items:
            cible = CHAMPS_PAR_REGLE.get(item.regle_code)
            if cible is None:
                resultat[item.id] = None
                continue
            fiche, chemins = cible
            cle = {"CLIENT": FICHE_PAR_TYPE[TypeClient(d.type_client_code)],
                   "MANDATAIRE": f"FICHE_MANDATAIRE:{item.dossier_partie_id}"}.get(fiche, fiche)
            champs = fiches.get(cle)
            resultat[item.id] = prefill.donnee_connue(chemins, champs) if champs is not None else None
        return resultat

    @staticmethod
    def colonne_chemin(chemin: str) -> tuple[type, str]:
        """Modèle et colonne qui stockent la donnée d'un chemin de fiche (source unique)."""
        tete, _, reste = chemin.partition(".")
        if tete == "dossier":
            return EerDossier, ALIAS_DOSSIER.get(reste, reste)
        if tete == "role":
            return EerDossierPartie, reste
        if tete in ("client", "partie"):
            if tete == "client" and reste in ("ppe", "ppe_motif", "fatca_indice"):
                return EerDossierPartie, reste
            sous, _, attr = reste.partition(".")
            if sous == "pp":
                return EerPartiePhysique, attr
            if sous == "pm":
                return EerPartieMorale, attr
            if sous == "piece":
                return EerPieceIdentite, {"type": "type_piece"}.get(attr, attr)
            return EerPartie, reste
        raise EerErreur(f"Chemin inconnu : {chemin}")

    def _cible_ecriture(self, d: EerDossier, chemin: str, dp: EerDossierPartie | None) -> tuple[Any, str]:
        modele, attr = self.colonne_chemin(chemin)
        tete = chemin.partition(".")[0]
        client_dp = next(x for x in d.parties if x.role == RoleDossier.CLIENT)
        cible_dp = client_dp if tete == "client" else dp
        if modele is EerDossier:
            return d, attr
        if cible_dp is None:
            raise EerErreur("Partie non précisée")
        if modele is EerDossierPartie:
            return cible_dp, attr
        p = cible_dp.partie
        if modele is EerPieceIdentite:
            if not p.pieces:
                raise EerErreur("Aucune pièce d'identité : la saisir d'abord (type + numéro)")
            return p.pieces[-1], attr
        instance = {EerPartie: p, EerPartiePhysique: p.physique, EerPartieMorale: p.morale}[modele]
        if instance is None:
            raise EerErreur(f"Champ incompatible avec la nature de la partie : {chemin}")
        return instance, attr

    async def completer_champ(self, acteur: Acteur, dossier_id: uuid.UUID, chemin: str, valeur: Any, *,
                              dossier_partie_id: uuid.UUID | None = None) -> None:
        """Écrit la valeur dans la donnée source unique ; la fiche n'est qu'une vue."""
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._verifier_modifiable(acteur, d)
        dp = next((x for x in d.parties if x.id == dossier_partie_id), None) if dossier_partie_id else None
        fiches = ["FICHE_MANDATAIRE"] if dp is not None else [FICHE_PAR_TYPE[TypeClient(d.type_client_code)],
                                                               "SPECIMEN_SIGNATURE"]
        if dp is not None and dp.role != RoleDossier.MANDATAIRE:
            raise EerErreur("Fiche de partie : mandataire uniquement")
        if chemin in CHEMINS_LECTURE_SEULE or not any(c["chemin"] == chemin for f in fiches
                                                      for c in FICHES[f]["champs"]):
            raise EerErreur(f"Champ non modifiable : {chemin}")
        if d.statut == Statut.A_COMPLETER:
            element = await self._element_complement(d, champ=chemin)
            if element is None:
                raise EerErreur("En complément, seuls les éléments demandés sont modifiables")
            element.fourni = True
        cible, attr = self._cible_ecriture(d, chemin, dp)
        if attr not in cible.__table__.columns:
            raise EerErreur(f"Chemin inconnu : {chemin}")
        if chemin in ("dossier.racine_client", "client.racine_client") and valeur:
            valeur = normaliser_racine(str(valeur), obligatoire=True)
        converti = _convertir(cible.__table__.columns[attr], valeur)
        domaine = DOMAINE_PAR_CHAMP.get(attr)
        if domaine and converti is not None and await self._referentiel(domaine, converti) is None:
            raise EerErreur(f"Valeur « {converti} » inconnue pour ce champ (référentiel {domaine})")
        setattr(cible, attr, converti)
        if cible is d:
            await self._verifier_codes_dossier(d)
        await self._etat_champ(d, chemin, dossier_partie_id, EtatChamp.CONNU, source="SAISIE")
        await self.db.flush()
        await self._historique(d, acteur, "CHAMP_COMPLETE", details={"chemin": chemin})
        await self._audit(acteur, "eer.champ.update", d, after={"chemin": chemin})
        await self.synchroniser(await self.charger(d.id), acteur)
        if chemin == "dossier.racine_client" and converti:
            client_dp = next(x for x in d.parties if x.role == RoleDossier.CLIENT)
            if not client_dp.partie.racine_client:
                client_dp.partie.racine_client = converti
                await self.db.flush()

    async def apercu_orion(self, racine: str) -> dict:
        return await apercu_clientele(self.db, racine)

    async def prefill_depuis_clientele(
        self, acteur: Acteur, dossier_id: uuid.UUID, racine: str, *, ignorer_absent: bool = False,
    ) -> dict:
        """Remplit les champs EER vides depuis ORION. N'écrase jamais une saisie existante."""
        d = await self.charger(dossier_id, acteur=acteur)
        if d.statut != Statut.BROUILLON:
            raise EerErreur("Préremplissage ORION réservé aux brouillons")
        racine = normaliser_racine(racine, obligatoire=True)  # type: ignore[assignment]
        client = await charger_client(self.db, racine)
        d.racine_client = racine
        client_dp = next(x for x in d.parties if x.role == RoleDossier.CLIENT)
        if not client_dp.partie.racine_client:
            client_dp.partie.racine_client = racine
        if client is None:
            await self.db.flush()
            if ignorer_absent:
                return {"present": False, "racine_client": racine, "remplis": [], "conserves": [],
                        "ecarts": [], "reserves": []}
            raise AppError(
                "Client absent du référentiel ORION. La racine est enregistrée : l'EER peut précéder ORION.",
                404, code="CLIENTELE_ABSENTE")
        props, reserves = propositions(client, type_client=d.type_client_code)
        piece_type = next((v for c, v in props if c == "client.piece.type"), None)
        piece_num = next((v for c, v in props if c == "client.piece.numero"), None)
        piece_creee = False
        if piece_type and piece_num and not client_dp.partie.pieces:
            client_dp.partie.pieces.append(EerPieceIdentite(type_piece=str(piece_type), numero=str(piece_num)))
            await self.db.flush()
            piece_creee = True
        remplis: list[str] = []
        conserves: list[str] = []
        ecarts: list[dict] = []
        for chemin, valeur in props:
            try:
                cible, attr = self._cible_ecriture(d, chemin, None)
            except EerErreur:
                continue
            actuel = getattr(cible, attr, None)
            if actuel not in (None, "") and not (piece_creee and chemin.startswith("client.piece.")):
                conserves.append(chemin)
                converti_cmp = _convertir(cible.__table__.columns[attr], valeur)
                if str(actuel) != str(converti_cmp):
                    ecarts.append({"chemin": chemin, "eer": str(actuel), "orion": str(valeur)})
                continue
            setattr(cible, attr, _convertir(cible.__table__.columns[attr], valeur))
            await self._etat_champ(d, chemin, None, EtatChamp.A_CONFIRMER, source="ORION")
            remplis.append(chemin)
        await self.db.flush()
        await self._historique(d, acteur, "PREFILL_ORION", details={
            "racine": racine, "remplis": remplis, "conserves": conserves})
        await self._audit(acteur, "eer.clientele.prefill", d, after={"racine": racine, "remplis": remplis})
        await self.synchroniser(await self.charger(d.id), acteur, journaliser=False)
        return {"present": True, "racine_client": racine, "remplis": remplis, "conserves": conserves,
                "ecarts": ecarts, "reserves": reserves}

    async def confirmer_champ(self, acteur: Acteur, dossier_id: uuid.UUID, chemin: str, *,
                              dossier_partie_id: uuid.UUID | None = None) -> None:
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._exiger_controle(acteur, d, {Etape.FICHES, Etape.CONTROLES})
        cle = f"FICHE_MANDATAIRE:{dossier_partie_id}" if dossier_partie_id else None
        fiches = await self.fiches(dossier_id)
        champs = fiches[cle] if cle else [c for k, v in fiches.items() if ":" not in k for c in v]
        champ = next((c for c in champs if c.chemin == chemin), None)
        if champ is None:
            raise EerErreur(f"Champ inconnu : {chemin}")
        try:
            etat = prefill.confirmer(champ)
        except ValueError as exc:
            raise EerErreur(str(exc)) from exc
        ligne = await self._etat_champ(d, chemin, dossier_partie_id, etat.etat, empreinte=etat.empreinte)
        ligne.confirme_par_id, ligne.confirme_le = acteur.user.id, _maintenant()
        await self.db.flush()

    async def _etat_champ(self, d: EerDossier, chemin: str, dp_id: uuid.UUID | None, etat: EtatChamp, *,
                          source: str | None = None, empreinte: str | None = None) -> EerChampEtat:
        ligne = await self.db.scalar(select(EerChampEtat).where(
            EerChampEtat.dossier_id == d.id, EerChampEtat.chemin == chemin,
            EerChampEtat.dossier_partie_id.is_not_distinct_from(dp_id)))
        if ligne is None:
            ligne = EerChampEtat(dossier_id=d.id, dossier_partie_id=dp_id, chemin=chemin, etat=etat)
            self.db.add(ligne)
        ligne.etat, ligne.empreinte = etat, empreinte
        if source:
            ligne.source = source
        return ligne

    async def terminer_fiches(self, acteur: Acteur, dossier_id: uuid.UUID) -> EerDossier:
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._exiger_controle(acteur, d, {Etape.FICHES})
        bloquants = [c for champs in (await self.fiches(dossier_id)).values() for c in prefill.champs_a_completer(champs)]
        try:
            avancer_etape(Etape.FICHES, champs_bloquants=len(bloquants))
        except TransitionRefusee as exc:
            raise EerErreur(f"{exc} : " + ", ".join(sorted({c.libelle for c in bloquants}))) from exc
        d.etape = Etape.CONTROLES
        await self._historique(d, acteur, "FICHES_COMPLETEES", etape=Etape.FICHES)
        await self.db.flush()
        return d

    # --- Actionnariat / bénéficiaires effectifs -------------------------------------------

    async def ajouter_detention(self, acteur: Acteur, dossier_id: uuid.UUID, detenteur_partie_id: uuid.UUID,
                                detenue_partie_id: uuid.UUID, pourcentage: Decimal | None,
                                lien: str | None = None) -> EerDetention:
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._verifier_modifiable(acteur, d)
        if d.type_client_code not in (TypeClient.PM_PRIVEE, TypeClient.PM_PUBLIQUE):
            raise EerErreur("Actionnariat : uniquement PM privée et PM publique")
        membres = {dp.partie_id for dp in d.parties if dp.role in (RoleDossier.CLIENT, RoleDossier.ACTIONNAIRE)}
        if detenteur_partie_id not in membres or detenue_partie_id not in membres:
            raise EerErreur("Détenteur et détenue doivent être le client ou des actionnaires du dossier")
        det = EerDetention(dossier_id=d.id, detenteur_partie_id=detenteur_partie_id,
                           detenue_partie_id=detenue_partie_id,
                           pourcentage=None if pourcentage is None else Decimal(str(pourcentage)), lien=lien)
        self.db.add(det)
        await self.db.flush()
        await self._historique(d, acteur, "DETENTION_AJOUTEE", details={
            "detenteur": str(detenteur_partie_id), "detenue": str(detenue_partie_id),
            "pourcentage": None if pourcentage is None else str(pourcentage)})
        return det

    async def beneficiaires(self, dossier_id: uuid.UUID) -> ResultatBE:
        d = await self.charger(dossier_id)
        detentions = (await self.db.execute(select(EerDetention).where(EerDetention.dossier_id == d.id))).scalars()
        natures = {dp.partie_id: "PP" if dp.partie.nature == "PHYSIQUE" else "PM" for dp in d.parties}
        seuil = d.parametres_snapshot.get("be.seuil_pourcentage")
        if seuil is None:
            raise EerErreur("Seuil BE absent des paramètres du dossier")
        return calculer_beneficiaires(
            str(d.client_partie_id),
            [Detention(str(x.detenteur_partie_id), str(x.detenue_partie_id), x.pourcentage) for x in detentions],
            {str(k): v for k, v in natures.items()}, seuil)

    async def appliquer_beneficiaires(self, acteur: Acteur, dossier_id: uuid.UUID) -> ResultatBE:
        """Crée le rôle BE (source CALCULE) des personnes au-dessus du seuil figé du dossier."""
        resultat = await self.beneficiaires(dossier_id)
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._verifier_modifiable(acteur, d)
        existants = {dp.partie_id: dp for dp in d.parties if dp.role == RoleDossier.BENEFICIAIRE_EFFECTIF}
        for be in resultat.beneficiaires:
            pid = uuid.UUID(be.partie_id)
            dp = existants.get(pid)
            if dp is None:
                dp = EerDossierPartie(dossier_id=d.id, partie_id=pid, role=RoleDossier.BENEFICIAIRE_EFFECTIF,
                                      be_source="CALCULE", ordre=len(d.parties))
                self.db.add(dp)
            dp.be_pourcentage_calcule = be.pourcentage
        await self.db.flush()
        await self._historique(d, acteur, "BE_CALCULES", details={
            "seuil": str(resultat.seuil), "beneficiaires": [[b.partie_id, str(b.pourcentage)]
                                                            for b in resultat.beneficiaires],
            "a_verifier": [b.partie_id for b in resultat.a_verifier],
            "problemes": [p.code for p in resultat.problemes]})
        await self.synchroniser(await self.charger(d.id), acteur)
        return resultat

    # --- Conformité et anomalies ----------------------------------------------------------

    async def _anomalies(self, d: EerDossier) -> list[EerAnomalie]:
        return list((await self.db.execute(select(EerAnomalie).where(EerAnomalie.dossier_id == d.id))).scalars())

    def _anomalies_moteur(self, d: EerDossier, anomalies: Iterable[EerAnomalie]) -> list[Anomalie]:
        items = {i.id: i for i in d.items}
        resultat = []
        for a in anomalies:
            item = items.get(a.item_id) if a.item_id else None
            cle = (item.regle_code, str(item.dossier_partie_id) if item.dossier_partie_id else None) if item else None
            resultat.append(Anomalie(a.type_code, GraviteAnomalie(a.gravite), StatutAnomalie(a.statut), cle,
                                     a.description))
        return resultat

    async def calculer_decision(self, acteur: Acteur, dossier_id: uuid.UUID) -> Decision:
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._exiger_controle(acteur, d, {Etape.CONTROLES})
        return await self._decider(d, acteur)

    async def _decider(self, d: EerDossier, acteur: Acteur) -> Decision:
        decision = decider([self._element(i) for i in d.items], self._anomalies_moteur(d, await self._anomalies(d)))
        d.conformite_physique = decision.axes["PHYSIQUE"].resultat
        d.conformite_systeme = decision.axes["SYSTEME"].resultat
        d.conformite_coherence = decision.axes["COHERENCE"].resultat
        d.decision_globale = decision.resultat
        self.db.add(EerDecision(
            dossier_id=d.id, version=d.version_courante, resultat=decision.resultat,
            conformite_physique=d.conformite_physique, conformite_systeme=d.conformite_systeme,
            conformite_coherence=d.conformite_coherence, explication=decision.explication,
            parametres=d.parametres_snapshot, decide_par_id=acteur.user.id))
        await self.db.flush()
        return decision

    async def ouvrir_anomalies(self, acteur: Acteur, dossier_id: uuid.UUID) -> list[EerAnomalie]:
        """Ouvre une anomalie par élément en échec qui n'en a pas (gravité proposée)."""
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._exiger_controle(acteur, d, {Etape.CONTROLES})
        existantes = await self._anomalies(d)
        par_cle = {(i.regle_code, str(i.dossier_partie_id) if i.dossier_partie_id else None): i for i in d.items}
        creees = []
        for p in proposer_anomalies([self._element(i) for i in d.items], self._anomalies_moteur(d, existantes)):
            item = par_cle[p.element]
            a = EerAnomalie(dossier_id=d.id, item_id=item.id, dossier_partie_id=item.dossier_partie_id,
                            type_code=item.motif_code or ("MANQUANT" if item.statut == StatutElement.MANQUANT
                                                          else "NON_CONFORME"),
                            gravite=p.gravite, description=p.libelle, statut=StatutAnomalie.OUVERTE,
                            version_detection=d.version_courante, created_by_id=acteur.user.id)
            self.db.add(a)
            creees.append(a)
        await self.db.flush()
        return creees

    async def accepter_anomalie(self, acteur: Acteur, anomalie_id: uuid.UUID, justification: str) -> EerAnomalie:
        """Dérogation : justification obligatoire, autre agent que l'analyste (séparation)."""
        acteur.exiger("eer.validate")
        a = await self.db.get(EerAnomalie, anomalie_id)
        if a is None:
            raise EerIntrouvable("Anomalie introuvable")
        d = await self.charger(a.dossier_id, verrou=True, acteur=acteur)
        if not (justification and justification.strip()):
            raise EerErreur("Justification obligatoire pour une dérogation")
        if await self.separation_active(d) and acteur.user.id in (d.analyste_id, d.created_by_id):
            raise EerAccesRefuse("Séparation des rôles : la dérogation doit venir d'un autre agent")
        if a.statut not in ANOMALIES_OUVERTES:
            raise EerErreur("Anomalie déjà traitée")
        a.statut, a.justification = StatutAnomalie.ACCEPTEE, justification.strip()
        a.resolved_by_id, a.resolved_at, a.version_resolution = acteur.user.id, _maintenant(), d.version_courante
        item = next((i for i in d.items if i.id == a.item_id), None)
        if item is not None:
            item.derogation_acceptee = True
        await self.db.flush()
        await self._historique(d, acteur, "DEROGATION", motif=a.justification, details={"anomalie": str(a.id)})
        await self._audit(acteur, "eer.anomalie.accept", d, after={"anomalie": str(a.id)})
        return a

    async def creer_anomalie(self, acteur: Acteur, dossier_id: uuid.UUID, *, type_code: str, gravite: str,
                             description: str, item_id: uuid.UUID | None = None, champ: str | None = None,
                             observation: str | None = None, action_attendue: str | None = None) -> EerAnomalie:
        """Anomalie constatée par l'analyste (incohérence, information erronée…)."""
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        self._exiger_controle(acteur, d, {Etape.CHECKLIST, Etape.FICHES, Etape.CONTROLES})
        if not (description and description.strip()) or not (type_code and type_code.strip()):
            raise EerErreur("Type et description de l'anomalie obligatoires")
        item = next((i for i in d.items if i.id == item_id), None) if item_id else None
        if item_id and item is None:
            raise EerErreur("Élément ciblé hors du dossier")
        a = EerAnomalie(dossier_id=d.id, item_id=item_id, dossier_partie_id=item.dossier_partie_id if item else None,
                        champ=champ, type_code=type_code.strip(), gravite=GraviteAnomalie(gravite),
                        description=description.strip(), observation=observation, action_attendue=action_attendue,
                        statut=StatutAnomalie.OUVERTE, version_detection=d.version_courante,
                        created_by_id=acteur.user.id)
        self.db.add(a)
        await self.db.flush()
        await self._historique(d, acteur, "ANOMALIE_CREEE", details={"anomalie": str(a.id), "gravite": a.gravite})
        return a

    async def modifier_anomalie(self, acteur: Acteur, anomalie_id: uuid.UUID, *, gravite: str | None = None,
                                observation: str | None = None, action_attendue: str | None = None,
                                annuler_motif: str | None = None) -> EerAnomalie:
        a = await self.db.get(EerAnomalie, anomalie_id)
        if a is None:
            raise EerIntrouvable("Anomalie introuvable")
        d = await self.charger(a.dossier_id, verrou=True, acteur=acteur)
        self._exiger_controle(acteur, d, {Etape.CHECKLIST, Etape.FICHES, Etape.CONTROLES})
        if a.statut not in ANOMALIES_OUVERTES:
            raise EerErreur("Anomalie déjà traitée")
        if gravite is not None:
            a.gravite = GraviteAnomalie(gravite)
        if observation is not None:
            a.observation = observation
        if action_attendue is not None:
            a.action_attendue = action_attendue
        if annuler_motif is not None:
            if not annuler_motif.strip():
                raise EerErreur("Motif d'annulation obligatoire")
            a.statut, a.justification = StatutAnomalie.ANNULEE, annuler_motif.strip()
            a.resolved_by_id, a.resolved_at, a.version_resolution = acteur.user.id, _maintenant(), d.version_courante
        await self.db.flush()
        await self._historique(d, acteur, "ANOMALIE_MODIFIEE", details={"anomalie": str(a.id), "statut": a.statut})
        return a

    # --- Workflow ---------------------------------------------------------------------------

    async def _element_complement(self, d: EerDossier, *, champ: str | None = None,
                                  item_id: uuid.UUID | None = None) -> EerComplementElement | None:
        complement = await self.db.scalar(select(EerComplement).where(
            EerComplement.dossier_id == d.id, EerComplement.statut == "OUVERT"))
        if complement is None:
            return None
        return next((e for e in complement.elements
                     if (champ and e.champ == champ) or (item_id and e.item_id == item_id)), None)

    async def marquer_fourni(self, acteur: Acteur, dossier_id: uuid.UUID, item_id: uuid.UUID,
                             document_id: uuid.UUID | None = None) -> None:
        """Réception d'une pièce demandée en complément."""
        acteur.exiger("eer.complement.receive")
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        if d.statut != Statut.A_COMPLETER:
            raise EerErreur("Le dossier n'est pas en attente de complément")
        element = await self._element_complement(d, item_id=item_id)
        if element is None:
            raise EerErreur("Élément non demandé dans le complément en cours")
        element.fourni = True
        item = next(i for i in d.items if i.id == item_id)
        item.document_id = await self._document(d, document_id) or item.document_id
        await self.db.flush()
        await self._historique(d, acteur, "COMPLEMENT_RECU", details={"item": item.regle_code})

    async def relancer(self, acteur: Acteur, dossier_id: uuid.UUID, commentaire: str | None = None) -> EerDossier:
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        raisons = peut_relancer(self._etat(d), acteur.perimetre.permissions)
        if raisons:
            raise EerErreur("; ".join(raisons))
        d.nb_relances += 1
        d.derniere_relance_le = _maintenant()
        await self._historique(d, acteur, "RELANCE", motif=commentaire, details={"numero": d.nb_relances})
        await self.db.flush()
        await eer_notifications.relance(self.db, d, acteur.user.id)
        return d

    def _etat(self, d: EerDossier) -> EtatDossier:
        return EtatDossier(
            statut=Statut(d.statut), createur_id=str(d.created_by_id),
            analyste_id=str(d.analyste_id) if d.analyste_id else None,
            controleur_id=str(d.controleur_id) if d.controleur_id else None,
            etape=Etape(d.etape) if d.etape else None,
            decision=ResultatAxe(d.decision_globale) if d.decision_globale else None,
            avis_requis=d.avis_requis, nb_relances=d.nb_relances,
            champs_socle_manquants=tuple(c for c, v in (("client", d.client_partie_id), ("date_eer", d.date_eer),
                                                         ("agence", d.agence_id)) if not v))

    async def transition(self, acteur: Acteur, dossier_id: uuid.UUID, cible: str, *, motif: str | None = None,
                         analyste_id: uuid.UUID | None = None, avis_favorable: bool | None = None,
                         cibles: CibleComplement | None = None, echeance: date | None = None,
                         fonction_visa: str = "Service Conformité KYC") -> EerDossier:
        d = await self.charger(dossier_id, verrou=True, acteur=acteur)
        cible = Statut(cible)
        origine = Statut(d.statut)
        cibles = cibles or CibleComplement()
        if origine == Statut.EN_CONTROLE:
            await self._decider(d, acteur)
        fournis = True
        if cible == Statut.RESOUMIS:
            complement = await self.db.scalar(select(EerComplement).where(
                EerComplement.dossier_id == d.id, EerComplement.statut == "OUVERT"))
            fournis = complement is not None and all(e.fourni for e in complement.elements)
        demande = Demande(
            cible=cible, acteur_id=str(acteur.user.id),
            permissions=acteur.perimetre.permissions,
            motif=motif, elements_cibles=len(cibles), elements_cibles_fournis=fournis,
            avis_favorable=avis_favorable, analyste_cible_id=str(analyste_id) if analyste_id else None,
            separation_roles=await self.separation_active(d))
        try:
            verifier(self._etat(d), demande)
        except TransitionRefusee as exc:
            refus = EerAccesRefuse if any(r.startswith(("Permission", "Séparation", "Seul")) for r in exc.raisons) \
                else EerErreur
            raise refus("; ".join(exc.raisons)) from exc

        await self._effets(d, acteur, origine, cible, motif=motif, analyste_id=analyste_id,
                           avis_favorable=avis_favorable, cibles=cibles, echeance=echeance,
                           fonction_visa=fonction_visa)
        d.statut = cible
        await self._historique(d, acteur, "TRANSITION", de=origine, vers=cible, motif=motif)
        await self._audit(acteur, f"eer.dossier.{cible.lower()}", d, before={"statut": origine},
                          after={"statut": cible})
        if origine == Statut.AVIS_CONFORMITE:
            await self._audit(acteur, "eer.avis." + ("favorable" if avis_favorable else "defavorable"), d,
                              after={"version": d.version_courante})
        await self.db.flush()
        if cible in EVENEMENTS_VERSION:
            await self._version(d, acteur, cible)
        if cible == Statut.SOUMIS:
            verifier(self._etat(d), Demande(Statut.A_AFFECTER, None, systeme=True))
            d.statut = Statut.A_AFFECTER
            await self._historique(d, None, "TRANSITION", de=Statut.SOUMIS, vers=Statut.A_AFFECTER)
            await self.db.flush()
        await eer_notifications.apres_transition(self.db, d, acteur.user.id)
        return d

    async def _effets(self, d: EerDossier, acteur: Acteur, origine: Statut, cible: Statut, *, motif: str | None,
                      analyste_id: uuid.UUID | None, avis_favorable: bool | None, cibles: CibleComplement,
                      echeance: date | None, fonction_visa: str) -> None:
        maintenant = _maintenant()
        if cible == Statut.SOUMIS:
            d.soumis_le = maintenant
        elif cible == Statut.AFFECTE:
            analyste = await self.db.get(User, analyste_id, options=[selectinload(User.roles)])
            if analyste is None or not analyste.is_active or analyste.deleted_at is not None:
                raise EerErreur("Analyste inconnu ou inactif")
            portee = resolve_eer_access_scope(analyste, await charger_permissions_eer(self.db, analyste))
            if not portee.peut("eer.control") or not portee.couvre(d.agence_id):
                raise EerErreur("L'agent affecté doit détenir eer.control sur l'agence du dossier")
            d.analyste_id = analyste_id
        elif cible == Statut.EN_CONTROLE and origine == Statut.AFFECTE:
            d.etape = Etape.CHECKLIST
        elif cible in (Statut.CONFORME, Statut.NON_CONFORME):
            d.controleur_id = acteur.user.id
        elif cible == Statut.A_COMPLETER:
            await self._ouvrir_complement(d, acteur, cibles, motif, echeance,
                                          "AVIS_DEFAVORABLE" if origine == Statut.AVIS_CONFORMITE else "NON_CONFORMITE")
            if origine == Statut.AVIS_CONFORMITE:
                self.db.add(EerVisa(dossier_id=d.id, user_id=acteur.user.id, fonction=fonction_visa,
                                    avis="DEFAVORABLE", commentaire=motif, version=d.version_courante))
        elif cible == Statut.RESOUMIS:
            await self._recevoir_complement(d, acteur)
        elif cible == Statut.VALIDE:
            if origine == Statut.AVIS_CONFORMITE:
                self.db.add(EerVisa(dossier_id=d.id, user_id=acteur.user.id, fonction=fonction_visa,
                                    avis="FAVORABLE", commentaire=motif, version=d.version_courante))
            d.valide_le = maintenant
            for a in await self._anomalies(d):
                if a.statut == StatutAnomalie.CORRIGEE:
                    a.statut = StatutAnomalie.CLOSE
        elif cible == Statut.ABANDONNE:
            d.motif_abandon = motif.strip() if motif else None
            complement = await self.db.scalar(select(EerComplement).where(
                EerComplement.dossier_id == d.id, EerComplement.statut == "OUVERT"))
            if complement is not None:
                complement.statut = "ANNULE"
        elif cible == Statut.ARCHIVE:
            d.archived_at = maintenant

    async def _ouvrir_complement(self, d: EerDossier, acteur: Acteur, cibles: CibleComplement, consigne: str | None,
                                 echeance: date | None, origine: str) -> EerComplement:
        items = {i.id: i for i in d.items}
        anomalies = {a.id: a for a in await self._anomalies(d)}
        if any(i not in items for i in cibles.item_ids) or any(a not in anomalies for a in cibles.anomalie_ids):
            raise EerErreur("Élément ciblé hors du dossier")
        if echeance is None:
            delai = jours_parametre((await self.parametres()).get("complement.delai_regularisation_jours"))
            echeance = date.today() + timedelta(days=delai) if delai is not None else None
        numero = (await self.db.scalar(select(func.coalesce(func.max(EerComplement.numero), 0)).where(
            EerComplement.dossier_id == d.id))) + 1
        complement = EerComplement(dossier_id=d.id, numero=numero, origine=origine, consigne=consigne,
                                   echeance=echeance, statut="OUVERT", version_demande=d.version_courante,
                                   demande_par_id=acteur.user.id)
        item_ids = set(cibles.item_ids)
        for aid in cibles.anomalie_ids:
            a = anomalies[aid]
            a.statut = StatutAnomalie.EN_COMPLEMENT
            if a.echeance_regularisation is None and echeance and d.etat_compte:
                a.echeance_regularisation = echeance
            complement.elements.append(EerComplementElement(anomalie_id=aid, item_id=a.item_id, fourni=False))
            if a.item_id:
                item_ids.discard(a.item_id)
        for iid in item_ids:
            complement.elements.append(EerComplementElement(item_id=iid, fourni=False))
        for champ in cibles.champs:
            complement.elements.append(EerComplementElement(champ=champ, fourni=False))
        self.db.add(complement)
        await self.db.flush()
        return complement

    async def _recevoir_complement(self, d: EerDossier, acteur: Acteur) -> None:
        complement = await self.db.scalar(select(EerComplement).where(
            EerComplement.dossier_id == d.id, EerComplement.statut == "OUVERT"))
        complement.statut, complement.recu_par_id, complement.recu_le = "RECU", acteur.user.id, _maintenant()
        d.version_courante += 1
        cibles = {e.item_id for e in complement.elements if e.item_id}
        for item in d.items:
            if item.id in cibles:
                # Seuls les éléments demandés sont re-pointés et re-contrôlés ; le reste est conservé.
                item.presence, item.statut, item.motif, item.motif_code = None, StatutElement.NON_CONTROLE, None, None
                item.derogation_acceptee = False
        for a in await self._anomalies(d):
            if a.statut == StatutAnomalie.EN_COMPLEMENT:
                a.statut, a.version_resolution = StatutAnomalie.CORRIGEE, d.version_courante
        d.decision_globale = None
        await self.db.flush()
        plan = await self.synchroniser(await self.charger(d.id), acteur)
        bloquants = sum(len(prefill.champs_a_completer(c)) for c in (await self.fiches(d.id)).values())
        d.etape = etape_reprise(checklist_modifiee=plan.modifie or bool(cibles), champs_bloquants=bloquants)

    # --- Versions, historique, audit ------------------------------------------------------

    async def instantane(self, d: EerDossier) -> dict[str, Any]:
        d = await self.charger(d.id)
        detentions = (await self.db.execute(select(EerDetention).where(EerDetention.dossier_id == d.id))).scalars()
        decision = await self.db.scalar(select(EerDecision).where(EerDecision.dossier_id == d.id)
                                        .order_by(EerDecision.decide_le.desc()).limit(1))
        return _serialiser({
            "dossier": _ligne(d),
            "parties": [{**_ligne(dp), "partie": self._source_partie(dp.partie), "nature": dp.partie.nature}
                        for dp in d.parties],
            "detentions": [_ligne(x) for x in detentions],
            "checklist": [_ligne(i, exclure={"created_at", "updated_at"}) for i in d.items],
            "anomalies": [_ligne(a, exclure={"created_at", "updated_at"}) for a in await self._anomalies(d)],
            "decision": _ligne(decision) if decision else None,
        })

    async def _version(self, d: EerDossier, acteur: Acteur, evenement: Statut) -> EerVersion:
        contenu = await self.instantane(d)
        brut = json.dumps(contenu, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        version = EerVersion(dossier_id=d.id, numero=d.version_courante, evenement=evenement, contenu=contenu,
                             empreinte=hashlib.sha256(brut.encode("utf-8")).hexdigest(), cree_par_id=acteur.user.id)
        self.db.add(version)
        await self.db.flush()
        return version

    async def _historique(self, d: EerDossier, acteur: Acteur | None, action: str, *, de: str | None = None,
                          vers: str | None = None, etape: str | None = None, motif: str | None = None,
                          details: dict | None = None) -> None:
        self.db.add(EerHistorique(dossier_id=d.id, action=action, de_statut=de, vers_statut=vers,
                                  etape=etape or d.etape, version=d.version_courante, motif=motif,
                                  details=_serialiser(details or {}), acteur_id=acteur.user.id if acteur else None))
        await self.db.flush()

    async def _audit(self, acteur: Acteur, action: str, d: EerDossier, *, before: dict | None = None,
                     after: dict | None = None) -> None:
        # Identifiants et statuts uniquement : les données personnelles restent dans les versions.
        await self.audit.log(user=acteur.user, action=action, entity="eer_dossier", entity_id=str(d.id),
                             before=_serialiser(before), after=_serialiser({"reference": d.reference, **(after or {})}),
                             ip_address=acteur.ip_address, espace_code=ESPACE_CODE, module_code=MODULE_CODE,
                             session_id=acteur.session_id)

