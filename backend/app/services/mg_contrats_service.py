"""Cycle de vie des contrats MG — sur mg_contrats et les référentiels existants.

Calculs financiers (TTC, échéancier, statuts d'échéance et de paiement) exclusivement côté serveur.
"""

from __future__ import annotations

import calendar
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_DOWN, Decimal

from fastapi import HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import Notification
from app.models.auth import Agence, User
from app.models.enums import TypeNotification
from app.models.mg_ops import (
    MgContrat,
    MgContratAvenant,
    MgContratEcheance,
    MgContratHistorique,
    MgContratPaiement,
    MgContratParametre,
    MgContratType,
)
from app.models.organisation import Fournisseur
from app.schemas.mg_ops import ContratAvenantIn, ContratCreate, ContratPaiementUpdate, ContratUpdate
from app.services.audit_helpers import record_audit
from app.services.mailer import send_mail
from app.services.notification_service import NotificationService
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes
from app.services.reporting_export import build_styled_pdf, build_styled_workbook, export_now

LOCKED = {"ARCHIVE", "ANNULE"}
EDITION_LIBRE = {"BROUILLON", "EN_PREPARATION", "REJETE"}
EN_VIGUEUR = {"ACTIF", "SUSPENDU", "EXPIRE"}
MODES_AVEC_REF = {"virement", "amanty"}
TRANSITIONS: dict[str, tuple[set[str], str]] = {
    "soumettre": ({"BROUILLON", "EN_PREPARATION", "REJETE"}, "EN_VALIDATION"),
    "valider": ({"EN_VALIDATION"}, "ACTIF"),
    "rejeter": ({"EN_VALIDATION"}, "REJETE"),
    "suspendre": ({"ACTIF"}, "SUSPENDU"),
    "reprendre": ({"SUSPENDU"}, "ACTIF"),
    "expirer": ({"ACTIF", "SUSPENDU"}, "EXPIRE"),
    "annuler": ({"BROUILLON", "EN_PREPARATION", "EN_VALIDATION", "ACTIF", "SUSPENDU", "REJETE"}, "ANNULE"),
    "archiver": ({"ACTIF", "EXPIRE", "SUSPENDU", "REJETE"}, "ARCHIVE"),
}
VALIDATION_ACTIONS = frozenset({"valider", "rejeter", "annuler"})
GESTION_PERMISSIONS = ("mg.contrats.create", "mg.contrats.manage", "mg.contrats.validate", "mg.contrats.settings")
RECONDUCTIONS = {"AUCUNE", "TACITE", "EXPRESSE"}
PAS_MOIS = {"MENSUEL": 1, "TRIMESTRIEL": 3, "SEMESTRIEL": 6, "ANNUEL": 12}
PERIODICITES = set(PAS_MOIS) | {"UNIQUE"}
MODES_PAIEMENT = ["Espèces", "Virement", "Amanty", "Chèque", "Carte", "Prélèvement"]
DEVISES = ["MRU", "EUR", "USD", "XOF"]
TYPES_DOCUMENT = [
    ("CONTRAT_SIGNE", "Contrat signé"),
    ("AVENANT", "Avenant"),
    ("BON_COMMANDE", "Bon de commande"),
    ("FACTURE", "Facture"),
    ("CCTP", "CCTP"),
    ("PREUVE_PAIEMENT", "Preuve de paiement"),
    ("AUTRE", "Autre"),
]
DEFAULT_TYPES = [
    ("FOURNITURE", "Fourniture"),
    ("MAINTENANCE", "Maintenance"),
    ("LOCATION", "Location"),
    ("ASSURANCE", "Assurance"),
    ("TRANSPORT", "Transport"),
    ("TELECOM", "Télécommunication"),
    ("NETTOYAGE", "Nettoyage"),
    ("SECURITE", "Sécurité"),
    ("PRESTATION", "Prestation"),
    ("AUTRE", "Autre"),
]
DEFAULT_PARAMS = [
    ("contrats.prefixe", "CTR", "Préfixe des références"),
    ("contrats.alerte_urgent", "7", "Jours — niveau urgent"),
    ("contrats.alerte_attention", "30", "Jours — niveau attention"),
    ("contrats.alerte_info", "90", "Jours — niveau info"),
    ("contrats.taux_tva", "16", "Taux de TVA par défaut (%)"),
    ("contrats.echeance_due_jours", "7", "Jours avant échéance — statut « Due (à payer) »"),
    ("contrats.ged_taille_max_mo", "15", "Taille maximale d’une pièce jointe (Mo)"),
]
FIELD_LABELS = {
    "titre": "Objet",
    "numero_contrat": "N° contrat",
    "description": "Description",
    "type_contrat": "Type",
    "devise": "Devise",
    "fournisseur_snapshot": "Fournisseur",
    "agence_libelle_snapshot": "Agence",
    "responsable_nom": "Responsable",
    "date_signature": "Date de signature",
    "date_debut": "Date de début",
    "date_fin": "Date de fin",
    "montant_ht": "Montant HT",
    "taux_tva": "TVA",
    "montant": "Montant TTC",
    "periodicite": "Périodicité",
    "mode_paiement": "Mode de paiement",
    "ref_paiement": "Référence de paiement",
    "alerte_jours": "Alerte (jours)",
    "observation": "Observation",
    "reconduction": "Reconduction",
    "preavis_jours": "Préavis (jours)",
}
FINANCIAL_FIELDS = {"date_debut", "date_fin", "montant_ht", "taux_tva", "montant", "periodicite", "devise"}
CENT = Decimal("0.01")
TOLERANCE = Decimal("0.001")


# ——— Règles pures (testées unitairement) ———


def paiement_statut(
    *,
    date_prevue: date,
    date_reelle: date | None,
    montant_prevu: Decimal,
    montant_paye: Decimal,
    today: date | None = None,
) -> str:
    today = today or date.today()
    prevu = montant_prevu or Decimal("0")
    paye = montant_paye or Decimal("0")
    if paye <= 0 and date_reelle is None:
        return "EN_RETARD" if date_prevue < today else "A_VENIR"
    if prevu > 0 and paye + TOLERANCE < prevu:
        return "PARTIELLEMENT_PAYE"
    return "PAYE"


def echeance_statut(
    *,
    date_prevue: date,
    montant: Decimal | None,
    montant_paye: Decimal,
    statut_actuel: str | None,
    fenetre_due: int,
    today: date | None = None,
) -> str:
    """À venir → Due (à payer) → En retard ; Payée dès que les règlements couvrent le montant.

    Une échéance chiffrée n'est « Payée » que par des paiements enregistrés ; une échéance
    sans montant (préavis, révision…) peut être marquée réalisée manuellement.
    """
    today = today or date.today()
    actuel = (statut_actuel or "").upper()
    if actuel == "ANNULEE":
        return "ANNULEE"
    if montant is not None and montant > 0:
        if (montant_paye or Decimal("0")) + TOLERANCE >= montant:
            return "PAYEE"
    elif actuel in {"PAYEE", "FAITE"}:
        return actuel
    jours = (date_prevue - today).days
    if jours < 0:
        return "EN_RETARD"
    if jours <= fenetre_due:
        return "DUE"
    return "A_VENIR"


def niveau_alerte(jours: int, urgent: int, attention: int) -> str:
    if jours < 0:
        return "CRITIQUE"
    if jours <= urgent:
        return "URGENT"
    if jours <= attention:
        return "ATTENTION"
    return "INFO"


def ajouter_mois(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def repartir(total: Decimal, n: int) -> list[Decimal]:
    """Parts égales arrondies au centime, le reliquat sur la dernière."""
    if n <= 0:
        return []
    part = (total / n).quantize(CENT, rounding=ROUND_DOWN)
    return [part] * (n - 1) + [total - part * (n - 1)]


def _match_ligne(
    r: dict,
    *,
    q: str | None,
    fournisseur: str | None,
    agence: str | None,
    jour: date | None,
    date_du: date | None,
    date_au: date | None,
) -> bool:
    if fournisseur and (r.get("fournisseur") or "") != fournisseur:
        return False
    if agence and (r.get("agence") or "") != agence:
        return False
    if date_du and (jour is None or jour < date_du):
        return False
    if date_au and (jour is None or jour > date_au):
        return False
    if q and q.strip():
        needle = q.strip().lower()
        champs = ("reference", "titre", "fournisseur", "agence", "paiement_ref", "commentaire")
        if not any(needle in str(r.get(k) or "").lower() for k in champs):
            return False
    return True


def montant_annualise(montant: Decimal | None, debut: date, fin: date | None) -> Decimal:
    """Engagement ramené à 12 mois : le montant TTC couvre toute la durée [début, fin]."""
    total = montant or Decimal("0")
    if fin is None or fin < debut:
        return total
    jours = (fin - debut).days + 1
    return (total * Decimal(365) / Decimal(jours)).quantize(Decimal("0.01"))


def plan_echeancier(debut: date, fin: date | None, periodicite: str | None, total: Decimal) -> list[tuple[date, Decimal]]:
    """Échéances à terme à échoir : une par période entamée entre début et fin."""
    per = (periodicite or "ANNUEL").upper()
    if per == "UNIQUE":
        return [(debut, total)]
    pas = PAS_MOIS.get(per)
    if pas is None:
        raise AppError("Périodicité inconnue", code="PERIODICITE_INVALIDE")
    if fin is None:
        raise AppError(
            "La date de fin est obligatoire pour générer un échéancier périodique",
            code="ECHEANCIER_IMPOSSIBLE",
        )
    if fin < debut:
        raise AppError("La date de fin ne peut pas précéder la date de début", code="CONTRAT_DATES_INVALIDES")
    dates: list[date] = []
    i = 0
    while i < 1200:
        d = ajouter_mois(debut, pas * i)
        if d > fin:
            break
        dates.append(d)
        i += 1
    return list(zip(dates, repartir(total, len(dates))))


def periode_suivante(debut: date, fin: date) -> tuple[date, date]:
    """Même durée que [debut, fin], démarrant le lendemain de fin (mois entiers si alignés)."""
    nd = fin + timedelta(days=1)
    mois = (nd.year - debut.year) * 12 + nd.month - debut.month
    if mois > 0 and ajouter_mois(debut, mois) == nd:
        return nd, ajouter_mois(nd, mois) - timedelta(days=1)
    return nd, nd + (fin - debut)


def doit_rappeler(jours: int, alerte_jours: int) -> bool:
    """Jalons de rappel : J-alerte, J-30, J-15, J-7, J-1, J0 puis chaque semaine après dépassement."""
    if jours < 0:
        return (-jours) % 7 == 1
    return jours in {alerte_jours, 30, 15, 7, 1, 0}


def _json(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


async def agence_scope(db: AsyncSession, user: User) -> uuid.UUID | None:
    """Consultant (lecture seule) rattaché à une agence : ne voit que les contrats de son agence."""
    if user.is_superuser or not user.agence_id:
        return None
    have = await load_user_permission_codes(db, user)
    if user_has_permission_codes(have, *GESTION_PERMISSIONS):
        return None
    return user.agence_id


async def capacites(db: AsyncSession, user: User) -> dict[str, bool]:
    have = await load_user_permission_codes(db, user)

    def ok(code: str) -> bool:
        return user.is_superuser or user_has_permission_codes(have, code)

    return {
        "create": ok("mg.contrats.create"),
        "manage": ok("mg.contrats.manage"),
        "validate": ok("mg.contrats.validate"),
        "settings": ok("mg.contrats.settings"),
        "export": ok("mg.contrats.export"),
        "ged_write": ok("ged.write"),
    }


class MgContratsService:
    def __init__(self, db: AsyncSession, scope_agence: uuid.UUID | None = None):
        self.db = db
        self.scope_agence = scope_agence

    @classmethod
    async def for_user(cls, db: AsyncSession, user: User) -> "MgContratsService":
        return cls(db, scope_agence=await agence_scope(db, user))

    # ——— Paramètres ———

    async def ensure_defaults(self) -> None:
        ntypes = await self.db.scalar(select(func.count()).select_from(MgContratType))
        if not ntypes:
            for code, libelle in DEFAULT_TYPES:
                self.db.add(MgContratType(code=code, libelle=libelle, actif=True))
        existing = set((await self.db.execute(select(MgContratParametre.cle))).scalars().all())
        for cle, valeur, libelle in DEFAULT_PARAMS:
            if cle not in existing:
                self.db.add(MgContratParametre(cle=cle, valeur=valeur, libelle=libelle))
        await self.db.commit()

    async def _param(self, cle: str, default: str) -> str:
        row = await self.db.scalar(select(MgContratParametre).where(MgContratParametre.cle == cle))
        return row.valeur if row and row.valeur != "" else default

    async def _param_int(self, cle: str, default: int) -> int:
        try:
            return int(await self._param(cle, str(default)))
        except ValueError:
            return default

    async def _fenetre_due(self) -> int:
        return await self._param_int("contrats.echeance_due_jours", 7)

    async def config(self, user: User) -> dict:
        await self.ensure_defaults()
        taux = await self._param("contrats.taux_tva", "16")
        scope = None
        if self.scope_agence:
            ag = await self.db.get(Agence, self.scope_agence)
            scope = {"id": str(self.scope_agence), "libelle": ag.libelle if ag else None}
        return {
            "taux_tva": float(Decimal(taux)) if taux.replace(".", "", 1).isdigit() else 0.0,
            "devise": "MRU",
            "devises": DEVISES,
            "periodicites": ["MENSUEL", "TRIMESTRIEL", "SEMESTRIEL", "ANNUEL", "UNIQUE"],
            "modes_paiement": MODES_PAIEMENT,
            "alerte_jours": [30, 60, 90],
            "echeance_due_jours": await self._fenetre_due(),
            "ged_taille_max_mo": await self._param_int("contrats.ged_taille_max_mo", 15),
            "types_document": [{"code": c, "libelle": l} for c, l in TYPES_DOCUMENT],
            "capacites": await capacites(self.db, user),
            "agence_scope": scope,
        }

    # ——— Outils internes ———

    async def _next_ref(self) -> str:
        prefix = await self._param("contrats.prefixe", "CTR")
        year = date.today().year
        like = f"{prefix}-{year}-%"
        count = await self.db.scalar(
            select(func.count()).select_from(MgContrat).where(MgContrat.reference.ilike(like))
        )
        return f"{prefix}-{year}-{int(count or 0) + 1:04d}"

    def _hist(self, contrat: MgContrat, action: str, user: User, frm: str | None, to: str | None, commentaire: str | None = None) -> None:
        contrat.historique.append(
            MgContratHistorique(
                action=action,
                from_statut=frm,
                to_statut=to,
                user_id=user.id,
                user_nom=user.full_name,
                commentaire=commentaire,
            )
        )

    async def _audit(self, user: User, action: str, contrat_id, before=None, after=None) -> None:
        await record_audit(
            self.db,
            user=user,
            action=action,
            entity="contrat",
            entity_id=str(contrat_id) if contrat_id else None,
            before=before,
            after=after,
            espace_code="moyens-generaux",
            module_code="contrats-echeances",
        )

    def _check_dates(self, debut: date | None, fin: date | None) -> None:
        if debut and fin and fin < debut:
            raise AppError("La date de fin ne peut pas précéder la date de début", code="CONTRAT_DATES_INVALIDES")

    def _ref_paiement(self, mode: str | None, ref: str | None) -> str | None:
        if (mode or "").strip().lower() not in MODES_AVEC_REF:
            return None
        return (ref or "").strip() or None

    def _montants(self, ht: Decimal | None, taux: Decimal | None, montant: Decimal | None) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        if ht is None:
            return None, taux, montant
        rate = taux if taux is not None else Decimal("0")
        if rate < 0 or ht < 0:
            raise AppError("Montant ou TVA invalide", code="CONTRAT_MONTANT_INVALIDE")
        ttc = (ht * (Decimal("1") + rate / Decimal("100"))).quantize(CENT)
        return ht, rate, ttc

    def _periodicite(self, value: str | None) -> str:
        per = (value or "ANNUEL").strip().upper()
        if per not in PERIODICITES:
            raise AppError("Périodicité inconnue", code="PERIODICITE_INVALIDE")
        return per

    def _reconduction(self, value: str | None) -> str:
        rec = (value or "AUCUNE").strip().upper()
        if rec not in RECONDUCTIONS:
            raise AppError("Type de reconduction inconnu", code="RECONDUCTION_INVALIDE")
        return rec

    def _assert_modifiable(self, contrat: MgContrat) -> None:
        if contrat.statut in LOCKED:
            raise AppError("Contrat archivé ou annulé : consultation uniquement", code="CONTRAT_NON_MODIFIABLE")

    async def _apply_refs(self, contrat: MgContrat, *, agence_id, fournisseur_id, responsable_id) -> None:
        if agence_id:
            ag = await self.db.get(Agence, agence_id)
            if not ag or ag.deleted_at is not None:
                raise AppError("Agence introuvable", code="REFERENCE_INTROUVABLE")
            contrat.agence_id = ag.id
            contrat.agence_libelle_snapshot = ag.libelle
        if fournisseur_id:
            fr = await self.db.get(Fournisseur, fournisseur_id)
            if not fr or fr.deleted_at is not None:
                raise AppError("Fournisseur introuvable", code="REFERENCE_INTROUVABLE")
            contrat.fournisseur_id = fr.id
            contrat.fournisseur_snapshot = fr.raison_sociale
        if responsable_id:
            user = await self.db.get(User, responsable_id)
            if not user or user.deleted_at is not None:
                raise AppError("Responsable introuvable", code="REFERENCE_INTROUVABLE")
            contrat.responsable_id = user.id
            contrat.responsable_nom = user.full_name

    async def _lock(self, contrat_id: uuid.UUID) -> MgContrat:
        contrat = await self.db.scalar(
            select(MgContrat)
            .options(
                selectinload(MgContrat.echeances).selectinload(MgContratEcheance.paiements),
                selectinload(MgContrat.paiements),
                selectinload(MgContrat.historique),
                selectinload(MgContrat.avenants),
            )
            .where(MgContrat.id == contrat_id, MgContrat.deleted_at.is_(None))
            .execution_options(populate_existing=True)
        )
        if not contrat or (self.scope_agence and contrat.agence_id != self.scope_agence):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contrat introuvable")
        self._sync_statuts(contrat, await self._fenetre_due())
        return contrat

    def _sync_statuts(self, contrat: MgContrat, fenetre_due: int) -> None:
        today = date.today()
        for e in contrat.echeances:
            s = echeance_statut(
                date_prevue=e.date_prevue,
                montant=e.montant,
                montant_paye=e.montant_paye,
                statut_actuel=e.statut,
                fenetre_due=fenetre_due,
                today=today,
            )
            if s != e.statut:
                e.statut = s
        for p in contrat.paiements:
            s = paiement_statut(
                date_prevue=p.date_prevue,
                date_reelle=p.date_reelle,
                montant_prevu=p.montant_prevu,
                montant_paye=p.montant_paye,
                today=today,
            )
            if s != p.statut:
                p.statut = s

    def _refresh_echeance(self, contrat: MgContrat) -> None:
        dates = [e.date_prevue for e in contrat.echeances if e.statut not in {"FAITE", "PAYEE", "ANNULEE"}]
        if contrat.date_fin:
            dates.append(contrat.date_fin)
        futur = [d for d in dates if d >= date.today()]
        contrat.prochain_echeance = min(futur) if futur else (min(dates) if dates else contrat.date_fin)

    def _snapshot(self, contrat: MgContrat) -> dict:
        return {f: _json(getattr(contrat, f)) for f in FIELD_LABELS}

    async def _notify(self, user_id, contrat: MgContrat, titre: str, message: str, event: str, actor: User | None = None) -> None:
        await NotificationService(self.db).create(
            user_id=user_id,
            type_notification=TypeNotification.SYSTEME,
            titre=titre,
            message=message,
            entity="contrat",
            entity_id=str(contrat.id),
            espace_code="moyens-generaux",
            module_code="contrats-echeances",
            event_type=event,
            emetteur_type="utilisateur" if actor else "systeme",
            emetteur_label=(actor.full_name if actor else None) or "Contrats & échéances",
            actor_user_id=actor.id if actor else None,
        )

    # ——— Contrats ———

    async def list_contrats(
        self,
        *,
        q: str | None = None,
        statut: str | None = None,
        etat: str | None = None,
        agence_id: uuid.UUID | None = None,
        fournisseur_id: uuid.UUID | None = None,
        type_contrat: str | None = None,
        horizon: str | None = None,
        renouveles: bool = False,
    ) -> list[MgContrat]:
        stmt = select(MgContrat).where(MgContrat.deleted_at.is_(None))
        if self.scope_agence:
            stmt = stmt.where(MgContrat.agence_id == self.scope_agence)
        if renouveles:
            stmt = stmt.where(MgContrat.contrat_precedent_id.is_not(None))
        if statut:
            stmt = stmt.where(MgContrat.statut == statut)
        if agence_id:
            stmt = stmt.where(MgContrat.agence_id == agence_id)
        if fournisseur_id:
            stmt = stmt.where(MgContrat.fournisseur_id == fournisseur_id)
        if type_contrat:
            stmt = stmt.where(MgContrat.type_contrat == type_contrat.upper())
        if q and q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    MgContrat.reference.ilike(like),
                    MgContrat.titre.ilike(like),
                    MgContrat.numero_contrat.ilike(like),
                    MgContrat.fournisseur_snapshot.ilike(like),
                    MgContrat.agence_libelle_snapshot.ilike(like),
                    MgContrat.responsable_nom.ilike(like),
                )
            )
        rows = list((await self.db.execute(stmt.order_by(MgContrat.date_debut.desc()))).scalars().all())
        if etat:
            rows = [c for c in rows if c.etat == etat]
        if not horizon:
            return rows
        today = date.today()
        kept = []
        for c in rows:
            fin = c.prochain_echeance or c.date_fin
            if fin is None:
                continue
            delta = (fin - today).days
            if horizon == "retard" and delta < 0:
                kept.append(c)
            elif horizon in {"7", "30", "60", "90"} and 0 <= delta <= int(horizon):
                kept.append(c)
        return kept

    async def get_contrat(self, contrat_id: uuid.UUID) -> MgContrat:
        return await self._lock(contrat_id)

    async def create_contrat(self, data: ContratCreate, user: User) -> MgContrat:
        await self.ensure_defaults()
        self._check_dates(data.date_debut, data.date_fin)
        taux = data.taux_tva
        if taux is None and data.montant_ht is not None:
            taux = Decimal(await self._param("contrats.taux_tva", "0"))
        ht, taux, ttc = self._montants(data.montant_ht, taux, data.montant)
        contrat = MgContrat(
            reference=await self._next_ref(),
            titre=data.titre.strip(),
            numero_contrat=(data.numero_contrat or "").strip() or None,
            description=data.description,
            type_contrat=(data.type_contrat or "AUTRE").strip().upper(),
            date_signature=data.date_signature,
            date_debut=data.date_debut,
            date_fin=data.date_fin,
            montant_ht=ht,
            taux_tva=taux,
            montant=ttc if ttc is not None else data.montant,
            devise=(data.devise or "MRU").upper(),
            periodicite=self._periodicite(data.periodicite),
            prochain_echeance=data.prochain_echeance or data.date_fin,
            alerte_jours=data.alerte_jours,
            mode_paiement=data.mode_paiement,
            ref_paiement=self._ref_paiement(data.mode_paiement, data.ref_paiement),
            observation=data.observation,
            fournisseur_snapshot=data.fournisseur_snapshot,
            reconduction=self._reconduction(data.reconduction),
            preavis_jours=data.preavis_jours,
            version=1,
            statut="BROUILLON",
        )
        await self._apply_refs(
            contrat,
            agence_id=data.agence_id,
            fournisseur_id=data.fournisseur_id,
            responsable_id=data.responsable_id,
        )
        self._hist(contrat, "creer", user, None, "BROUILLON")
        self.db.add(contrat)
        await self.db.commit()
        await self._audit(user, "contrats.create", contrat.id, after={"ref": contrat.reference, **self._snapshot(contrat)})
        await self.db.commit()
        return await self.get_contrat(contrat.id)

    async def update_contrat(self, contrat_id: uuid.UUID, data: ContratUpdate, user: User) -> MgContrat:
        contrat = await self._lock(contrat_id)
        self._assert_modifiable(contrat)
        before = self._snapshot(contrat)
        debut = data.date_debut or contrat.date_debut
        fin = data.date_fin if data.date_fin is not None else contrat.date_fin
        self._check_dates(debut, fin)
        for field in (
            "titre",
            "numero_contrat",
            "description",
            "date_signature",
            "date_debut",
            "date_fin",
            "prochain_echeance",
            "alerte_jours",
            "observation",
            "devise",
            "type_contrat",
            "fournisseur_snapshot",
        ):
            val = getattr(data, field)
            if val is not None:
                if field in {"type_contrat", "devise"} and isinstance(val, str):
                    val = val.strip().upper()
                setattr(contrat, field, val)
        if data.periodicite is not None:
            contrat.periodicite = self._periodicite(data.periodicite)
        if data.reconduction is not None:
            contrat.reconduction = self._reconduction(data.reconduction)
        if "preavis_jours" in data.model_fields_set:
            contrat.preavis_jours = data.preavis_jours
        if "mode_paiement" in data.model_fields_set:
            contrat.mode_paiement = (data.mode_paiement or "").strip() or None
        if {"mode_paiement", "ref_paiement"} & data.model_fields_set:
            contrat.ref_paiement = self._ref_paiement(contrat.mode_paiement, data.ref_paiement)
        if data.montant_ht is not None or data.taux_tva is not None:
            ht, taux, ttc = self._montants(
                data.montant_ht if data.montant_ht is not None else contrat.montant_ht,
                data.taux_tva if data.taux_tva is not None else contrat.taux_tva,
                contrat.montant,
            )
            contrat.montant_ht, contrat.taux_tva, contrat.montant = ht, taux, ttc
        elif data.montant is not None:
            contrat.montant = data.montant
        await self._apply_refs(
            contrat,
            agence_id=data.agence_id,
            fournisseur_id=data.fournisseur_id,
            responsable_id=data.responsable_id,
        )
        after = self._snapshot(contrat)
        changes = [k for k in FIELD_LABELS if before[k] != after[k]]
        if contrat.statut not in EDITION_LIBRE and FINANCIAL_FIELDS.intersection(changes):
            await self.db.rollback()
            raise AppError(
                "Contrat validé : les montants, dates et périodicité se modifient par avenant",
                code="AVENANT_REQUIS",
            )
        if not changes:
            return contrat
        self._refresh_echeance(contrat)
        self._hist(
            contrat,
            "modifier",
            user,
            contrat.statut,
            contrat.statut,
            "Champs modifiés : " + ", ".join(FIELD_LABELS[k] for k in changes),
        )
        await self.db.commit()
        await self._audit(
            user,
            "contrats.update",
            contrat.id,
            before={k: before[k] for k in changes},
            after={k: after[k] for k in changes},
        )
        await self.db.commit()
        return await self.get_contrat(contrat.id)

    async def soft_delete(self, contrat_id: uuid.UUID, user: User) -> None:
        contrat = await self._lock(contrat_id)
        if contrat.statut not in EDITION_LIBRE | {"ANNULE"}:
            raise AppError(
                "Seuls les brouillons, contrats rejetés ou annulés peuvent être retirés du registre",
                code="SUPPRESSION_IMPOSSIBLE",
            )
        ancien = contrat.statut
        contrat.deleted_at = datetime.now(timezone.utc)
        self._hist(contrat, "supprimer", user, ancien, None)
        await self.db.commit()
        await self._audit(user, "contrats.delete", contrat.id, before={"statut": ancien, "ref": contrat.reference})
        await self.db.commit()

    async def transition(self, contrat_id: uuid.UUID, action: str, user: User, commentaire: str | None = None) -> MgContrat:
        key = action.strip().lower()
        if key not in TRANSITIONS:
            raise AppError("Action invalide", code="ACTION_INVALIDE")
        allowed, new_statut = TRANSITIONS[key]
        contrat = await self._lock(contrat_id)
        if contrat.statut == new_statut:
            return contrat
        if contrat.statut not in allowed:
            raise AppError(f"Transition impossible depuis {contrat.statut}", code="TRANSITION_INVALIDE")
        if key in {"rejeter", "annuler"} and not (commentaire or "").strip():
            raise AppError("Motif obligatoire", code="MOTIF_OBLIGATOIRE")
        if key == "soumettre":
            manquants = []
            if not contrat.fournisseur_id and not (contrat.fournisseur_snapshot or "").strip():
                manquants.append("fournisseur")
            if contrat.montant_ht is None and contrat.montant is None:
                manquants.append("montant HT")
            if contrat.periodicite != "UNIQUE" and not contrat.date_fin:
                manquants.append("date de fin")
            if manquants:
                raise AppError(
                    "Complétez avant soumission : " + ", ".join(manquants),
                    code="CONTRAT_INCOMPLET",
                )
        old = contrat.statut
        contrat.statut = new_statut
        self._hist(contrat, key, user, old, new_statut, commentaire)
        generees = 0
        if key == "valider":
            a_payer = [e for e in contrat.echeances if e.type_echeance == "PAIEMENT" and e.statut != "ANNULEE"]
            if not a_payer and contrat.montant and contrat.montant > 0:
                try:
                    generees = self._generer(contrat, remplacer=False)
                except AppError as exc:
                    self._hist(contrat, "echeancier", user, new_statut, new_statut, f"Non généré : {exc.message}")
                else:
                    self._hist(contrat, "echeancier", user, new_statut, new_statut, f"{generees} échéance(s) générée(s)")
        if key in {"soumettre", "valider", "rejeter", "annuler"} and contrat.responsable_id and contrat.responsable_id != user.id:
            await self._notify(
                contrat.responsable_id,
                contrat,
                f"Contrat {contrat.reference}",
                f"Le contrat {contrat.reference} est passé à {new_statut}."
                + (f" Motif : {commentaire}" if commentaire else "")
                + " Consulter la fiche.",
                f"contrats.{key}",
                user,
            )
        if key == "soumettre":
            await NotificationService(self.db).notify_staff(
                role_codes={"contrats-echeances.valideur", "contrats-echeances.admin"},
                type_notification=TypeNotification.SYSTEME,
                titre=f"Contrat à valider : {contrat.reference}",
                message=f"« {contrat.titre} » a été soumis pour validation par {user.full_name}.",
                entity="contrat",
                entity_id=str(contrat.id),
                espace_code="moyens-generaux",
                module_code="contrats-echeances",
                event_type="contrats.a_valider",
                emetteur_type="utilisateur",
                emetteur_label=user.full_name or "Système",
                actor_user_id=user.id,
            )
        await self.db.commit()
        await self._audit(
            user,
            f"contrats.{key}",
            contrat.id,
            before={"statut": old},
            after={"statut": new_statut, "echeances_generees": generees, "motif": commentaire},
        )
        await self.db.commit()
        return await self.get_contrat(contrat.id)

    # ——— Échéancier ———

    def _nouvelle_echeance(self, contrat: MgContrat, type_echeance: str, d: date, montant: Decimal | None, commentaire: str | None) -> MgContratEcheance:
        return MgContratEcheance(
            type_echeance=type_echeance,
            date_prevue=d,
            montant=montant,
            responsable_nom=contrat.responsable_nom,
            statut="A_VENIR",
            commentaire=commentaire,
            paiements=[],
        )

    def _ajouter_plan(self, contrat: MgContrat, plan: list[tuple[date, Decimal]], libelle: str) -> int:
        n = len(plan)
        for i, (d, m) in enumerate(plan, 1):
            contrat.echeances.append(self._nouvelle_echeance(contrat, "PAIEMENT", d, m, f"{libelle} {i}/{n}"))
        return n

    def _ajouter_preavis(self, contrat: MgContrat) -> None:
        dp = contrat.date_preavis
        if not dp:
            return
        if any(e.type_echeance == "PREAVIS" and e.date_prevue == dp and e.statut != "ANNULEE" for e in contrat.echeances):
            return
        contrat.echeances.append(
            self._nouvelle_echeance(
                contrat, "PREAVIS", dp, None, f"Date limite de préavis ({contrat.preavis_jours} j avant la fin)"
            )
        )

    def _generer(self, contrat: MgContrat, *, remplacer: bool) -> int:
        total = contrat.montant
        if total is None:
            raise AppError("Montant TTC requis pour générer l'échéancier", code="ECHEANCIER_IMPOSSIBLE")
        existants = [e for e in contrat.echeances if e.type_echeance == "PAIEMENT" and e.statut != "ANNULEE"]
        if existants and not remplacer:
            raise AppError(
                "Un échéancier de paiement existe déjà : choisissez « Régénérer » pour remplacer les échéances non réglées",
                code="ECHEANCIER_EXISTANT",
            )
        garder = [e for e in existants if e.paiements or e.statut in {"PAYEE", "FAITE"}]
        for e in existants:
            if e not in garder:
                contrat.echeances.remove(e)
        plan = plan_echeancier(contrat.date_debut, contrat.date_fin, contrat.periodicite, total)
        if garder:
            limite = max(e.date_prevue for e in garder)
            reste = total - sum((e.montant or Decimal("0")) for e in garder)
            dates = [d for d, _ in plan if d > limite]
            plan = list(zip(dates, repartir(reste, len(dates)))) if dates and reste > 0 else []
        n = self._ajouter_plan(contrat, plan, "Échéance")
        self._ajouter_preavis(contrat)
        self._refresh_echeance(contrat)
        return n

    async def generer_echeancier(self, contrat_id: uuid.UUID, user: User, *, remplacer: bool = False) -> MgContrat:
        contrat = await self._lock(contrat_id)
        self._assert_modifiable(contrat)
        n = self._generer(contrat, remplacer=remplacer)
        self._sync_statuts(contrat, await self._fenetre_due())
        self._hist(
            contrat,
            "echeancier",
            user,
            contrat.statut,
            contrat.statut,
            f"{n} échéance(s) {'régénérée(s)' if remplacer else 'générée(s)'}",
        )
        await self.db.commit()
        await self._audit(user, "contrats.echeancier", contrat.id, after={"echeances": n, "remplacer": remplacer})
        await self.db.commit()
        return await self.get_contrat(contrat.id)

    async def simuler(self, *, date_debut: date, date_fin: date | None, periodicite: str, montant_ht: Decimal | None, taux_tva: Decimal | None) -> dict:
        if taux_tva is None:
            taux_tva = Decimal(await self._param("contrats.taux_tva", "0"))
        ht, taux, ttc = self._montants(montant_ht, taux_tva, None)
        out: dict = {"montant_ht": ht, "taux_tva": taux, "montant_ttc": ttc, "echeances": [], "erreur": None}
        if ttc is None:
            return out
        try:
            plan = plan_echeancier(date_debut, date_fin, self._periodicite(periodicite), ttc)
        except AppError as exc:
            out["erreur"] = exc.message
            return out
        out["echeances"] = [{"date": d.isoformat(), "montant": m} for d, m in plan]
        return out

    async def add_echeance(self, contrat_id: uuid.UUID, data: dict, user: User) -> MgContrat:
        contrat = await self._lock(contrat_id)
        self._assert_modifiable(contrat)
        statut = (data.get("statut") or "A_VENIR").upper()
        contrat.echeances.append(
            MgContratEcheance(
                type_echeance=(data.get("type_echeance") or "AUTRE").upper(),
                date_prevue=data["date_prevue"],
                date_reelle=data.get("date_reelle"),
                montant=data.get("montant"),
                responsable_nom=data.get("responsable_nom") or contrat.responsable_nom,
                statut=statut if statut in {"FAITE", "ANNULEE"} else "A_VENIR",
                commentaire=data.get("commentaire"),
                paiements=[],
            )
        )
        self._sync_statuts(contrat, await self._fenetre_due())
        self._refresh_echeance(contrat)
        self._hist(contrat, "echeance", user, contrat.statut, contrat.statut, data.get("type_echeance"))
        await self.db.commit()
        await self._audit(user, "contrats.echeance", contrat.id, after={k: _json(v) for k, v in data.items()})
        await self.db.commit()
        return await self.get_contrat(contrat.id)

    async def _echeance_contrat(self, echeance_id: uuid.UUID) -> tuple[MgContratEcheance, MgContrat]:
        contrat_id = await self.db.scalar(select(MgContratEcheance.contrat_id).where(MgContratEcheance.id == echeance_id))
        if not contrat_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Échéance introuvable")
        contrat = await self._lock(contrat_id)
        echeance = next(e for e in contrat.echeances if e.id == echeance_id)
        return echeance, contrat

    async def update_echeance(self, echeance_id: uuid.UUID, data: dict, user: User) -> dict:
        echeance, contrat = await self._echeance_contrat(echeance_id)
        self._assert_modifiable(contrat)
        before = {"date_prevue": _json(echeance.date_prevue), "montant": _json(echeance.montant), "statut": echeance.statut}
        if data.get("type_echeance"):
            echeance.type_echeance = str(data["type_echeance"]).upper()
        if data.get("date_prevue"):
            echeance.date_prevue = data["date_prevue"]
        if "date_reelle" in data:
            echeance.date_reelle = data.get("date_reelle")
        if "montant" in data:
            montant = data.get("montant")
            if montant is not None and echeance.montant_paye > Decimal(str(montant)) + TOLERANCE:
                raise AppError("Le montant ne peut pas être inférieur au déjà payé", code="MONTANT_INVALIDE")
            echeance.montant = montant
        if "statut" in data:
            demande = str(data.get("statut") or "").upper()
            echeance.statut = demande if demande in {"FAITE", "ANNULEE"} else "A_VENIR"
        if "commentaire" in data:
            echeance.commentaire = data.get("commentaire")
        if data.get("responsable_nom") is not None:
            echeance.responsable_nom = data.get("responsable_nom")
        self._sync_statuts(contrat, await self._fenetre_due())
        self._refresh_echeance(contrat)
        self._hist(contrat, "echeance_modifier", user, contrat.statut, contrat.statut, echeance.type_echeance)
        await self.db.commit()
        await self._audit(
            user,
            "contrats.echeance.update",
            contrat.id,
            before={"echeance": str(echeance.id), **before},
            after={"date_prevue": _json(echeance.date_prevue), "montant": _json(echeance.montant), "statut": echeance.statut},
        )
        await self.db.commit()
        return {"id": str(echeance.id), "contrat_id": str(contrat.id)}

    async def delete_echeance(self, echeance_id: uuid.UUID, user: User) -> None:
        echeance, contrat = await self._echeance_contrat(echeance_id)
        self._assert_modifiable(contrat)
        if echeance.paiements:
            raise AppError(
                "Échéance déjà réglée : supprimez d'abord les paiements rattachés",
                code="ECHEANCE_REGLEE",
            )
        contrat.echeances.remove(echeance)
        await self.db.flush()
        self._refresh_echeance(contrat)
        self._hist(contrat, "echeance_supprimer", user, contrat.statut, contrat.statut, echeance.type_echeance)
        await self.db.commit()
        await self._audit(user, "contrats.echeance.delete", contrat.id, before={"echeance": str(echeance_id)})
        await self.db.commit()

    # ——— Paiements ———

    def _echeance_of(self, contrat: MgContrat, echeance_id) -> MgContratEcheance | None:
        if not echeance_id:
            return None
        echeance = next((e for e in contrat.echeances if e.id == echeance_id), None)
        if echeance is None:
            raise AppError("Échéance introuvable pour ce contrat", code="REFERENCE_INTROUVABLE")
        return echeance

    def _check_ref_unique(self, contrat: MgContrat, ref: str | None, exclude: uuid.UUID | None = None) -> None:
        if ref and any((p.reference or "").strip() == ref and p.id != exclude for p in contrat.paiements):
            raise AppError("Cette référence de paiement existe déjà", code="REF_PAIEMENT_EXISTANTE")

    def _check_surpaiement(self, contrat: MgContrat, echeance: MgContratEcheance | None, paye: Decimal, exclude: uuid.UUID | None = None) -> None:
        if echeance is None or echeance.montant is None:
            return
        deja = sum((p.montant_paye or Decimal("0") for p in echeance.paiements if p.id != exclude), Decimal("0"))
        if deja + paye > echeance.montant + TOLERANCE:
            reste = max(echeance.montant - deja, Decimal("0")).quantize(CENT)
            raise AppError(
                f"Le montant dépasse le reste dû sur l'échéance ({reste} {contrat.devise or 'MRU'})",
                code="PAIEMENT_SUPERIEUR_RESTE",
            )

    async def add_paiement(self, contrat_id: uuid.UUID, data: dict, user: User) -> MgContrat:
        contrat = await self._lock(contrat_id)
        self._assert_modifiable(contrat)
        echeance = self._echeance_of(contrat, data.get("echeance_id"))
        ref = (data.get("reference") or "").strip() or None
        self._check_ref_unique(contrat, ref)
        paye = Decimal(str(data.get("montant_paye") or 0))
        prevu_raw = data.get("montant_prevu")
        if prevu_raw is None:
            prevu = (
                max(echeance.montant - echeance.montant_paye, Decimal("0"))
                if echeance and echeance.montant is not None
                else paye
            )
        else:
            prevu = Decimal(str(prevu_raw))
        if prevu < 0 or paye < 0:
            raise AppError("Montant invalide", code="MONTANT_INVALIDE")
        date_reelle = data.get("date_reelle")
        date_prevue = data.get("date_prevue") or (echeance.date_prevue if echeance else None) or date_reelle
        if not date_prevue:
            raise AppError("Date prévue obligatoire", code="CHAMP_OBLIGATOIRE")
        if paye > 0 and not date_reelle:
            raise AppError("Date de paiement obligatoire pour un montant versé", code="DATE_PAIEMENT_OBLIGATOIRE")
        self._check_surpaiement(contrat, echeance, paye)
        paiement = MgContratPaiement(
            reference=ref,
            date_prevue=date_prevue,
            date_reelle=date_reelle,
            montant_prevu=prevu,
            montant_paye=paye,
            devise=contrat.devise or "MRU",
            statut=paiement_statut(date_prevue=date_prevue, date_reelle=date_reelle, montant_prevu=prevu, montant_paye=paye),
            mode=data.get("mode") or contrat.mode_paiement,
            commentaire=data.get("commentaire"),
        )
        contrat.paiements.append(paiement)
        if echeance is not None:
            paiement.echeance = echeance
        self._sync_statuts(contrat, await self._fenetre_due())
        self._refresh_echeance(contrat)
        self._hist(contrat, "paiement", user, contrat.statut, contrat.statut, ref)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise AppError("Cette référence de paiement existe déjà", code="REF_PAIEMENT_EXISTANTE")
        await self._audit(
            user,
            "contrats.paiement",
            contrat.id,
            after={"paiement": str(paiement.id), "ref": ref, "paye": str(paye), "prevu": str(prevu), "statut": paiement.statut},
        )
        await self.db.commit()
        return await self.get_contrat(contrat.id)

    async def _paiement_contrat(self, paiement_id: uuid.UUID) -> tuple[MgContratPaiement, MgContrat]:
        contrat_id = await self.db.scalar(select(MgContratPaiement.contrat_id).where(MgContratPaiement.id == paiement_id))
        if not contrat_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paiement introuvable")
        contrat = await self._lock(contrat_id)
        return next(p for p in contrat.paiements if p.id == paiement_id), contrat

    async def update_paiement(self, paiement_id: uuid.UUID, data: ContratPaiementUpdate, user: User) -> MgContrat:
        paiement, contrat = await self._paiement_contrat(paiement_id)
        self._assert_modifiable(contrat)
        fields = data.model_fields_set
        before = {
            "ref": paiement.reference,
            "prevu": str(paiement.montant_prevu),
            "paye": str(paiement.montant_paye),
            "date_reelle": _json(paiement.date_reelle),
        }
        if "reference" in fields:
            ref = (data.reference or "").strip() or None
            self._check_ref_unique(contrat, ref, exclude=paiement.id)
            paiement.reference = ref
        if "echeance_id" in fields:
            paiement.echeance = self._echeance_of(contrat, data.echeance_id)
        if data.date_prevue is not None:
            paiement.date_prevue = data.date_prevue
        if "date_reelle" in fields:
            paiement.date_reelle = data.date_reelle
        if data.montant_prevu is not None:
            paiement.montant_prevu = data.montant_prevu
        if data.montant_paye is not None:
            paiement.montant_paye = data.montant_paye
        if "mode" in fields:
            paiement.mode = (data.mode or "").strip() or None
        if "commentaire" in fields:
            paiement.commentaire = data.commentaire
        if paiement.montant_paye > 0 and not paiement.date_reelle:
            raise AppError("Date de paiement obligatoire pour un montant versé", code="DATE_PAIEMENT_OBLIGATOIRE")
        self._check_surpaiement(contrat, paiement.echeance, paiement.montant_paye or Decimal("0"), exclude=paiement.id)
        self._sync_statuts(contrat, await self._fenetre_due())
        self._refresh_echeance(contrat)
        self._hist(contrat, "paiement_modifier", user, contrat.statut, contrat.statut, paiement.reference)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise AppError("Cette référence de paiement existe déjà", code="REF_PAIEMENT_EXISTANTE")
        await self._audit(
            user,
            "contrats.paiement.update",
            contrat.id,
            before={"paiement": str(paiement.id), **before},
            after={
                "ref": paiement.reference,
                "prevu": str(paiement.montant_prevu),
                "paye": str(paiement.montant_paye),
                "date_reelle": _json(paiement.date_reelle),
            },
        )
        await self.db.commit()
        return await self.get_contrat(contrat.id)

    async def delete_paiement(self, paiement_id: uuid.UUID, user: User) -> MgContrat:
        paiement, contrat = await self._paiement_contrat(paiement_id)
        self._assert_modifiable(contrat)
        snapshot = {"paiement": str(paiement.id), "ref": paiement.reference, "paye": str(paiement.montant_paye)}
        paiement.echeance = None
        contrat.paiements.remove(paiement)
        await self.db.flush()
        self._sync_statuts(contrat, await self._fenetre_due())
        self._refresh_echeance(contrat)
        self._hist(contrat, "paiement_supprimer", user, contrat.statut, contrat.statut, snapshot["ref"])
        await self.db.commit()
        await self._audit(user, "contrats.paiement.delete", contrat.id, before=snapshot)
        await self.db.commit()
        return await self.get_contrat(contrat.id)

    # ——— Avenants, reconduction, renouvellement ———

    async def add_avenant(self, contrat_id: uuid.UUID, data: ContratAvenantIn, user: User) -> MgContrat:
        contrat = await self._lock(contrat_id)
        if contrat.statut not in EN_VIGUEUR:
            raise AppError("Un avenant s'applique à un contrat actif, suspendu ou expiré", code="AVENANT_IMPOSSIBLE")
        if data.nouvelle_date_fin and data.nouvelle_date_fin < contrat.date_debut:
            raise AppError("La nouvelle date de fin précède le début du contrat", code="CONTRAT_DATES_INVALIDES")
        change_montant = data.nouveau_montant_ht is not None or data.nouveau_taux_tva is not None
        change_duree = data.nouvelle_date_fin is not None and data.nouvelle_date_fin != contrat.date_fin
        change_clauses = bool((data.clauses or "").strip())
        if not (change_montant or change_duree or change_clauses):
            raise AppError("L'avenant ne modifie ni le montant, ni la durée, ni les clauses", code="AVENANT_VIDE")
        kinds = [k for k, v in (("MONTANT", change_montant), ("DUREE", change_duree), ("CLAUSES", change_clauses)) if v]
        type_avenant = (data.type_avenant or "").strip().upper() or (kinds[0] if len(kinds) == 1 else "MIXTE")
        before = self._snapshot(contrat)
        av = MgContratAvenant(
            numero=len(contrat.avenants) + 1,
            type_avenant=type_avenant,
            objet=data.objet.strip(),
            date_effet=data.date_effet,
            montant_ht_avant=contrat.montant_ht,
            montant_ttc_avant=contrat.montant,
            date_fin_avant=contrat.date_fin,
            clauses=(data.clauses or "").strip() or None,
            user_id=user.id,
            user_nom=user.full_name,
        )
        if change_montant:
            ht, taux, ttc = self._montants(
                data.nouveau_montant_ht if data.nouveau_montant_ht is not None else contrat.montant_ht or Decimal("0"),
                data.nouveau_taux_tva if data.nouveau_taux_tva is not None else contrat.taux_tva,
                contrat.montant,
            )
            contrat.montant_ht, contrat.taux_tva, contrat.montant = ht, taux, ttc
        if change_duree:
            contrat.date_fin = data.nouvelle_date_fin
            if contrat.statut == "EXPIRE" and contrat.date_fin >= date.today():
                self._hist(contrat, "reprendre", user, "EXPIRE", "ACTIF", f"Prolongé par avenant n°{av.numero}")
                contrat.statut = "ACTIF"
        contrat.version = (contrat.version or 1) + 1
        av.montant_ht_apres = contrat.montant_ht
        av.montant_ttc_apres = contrat.montant
        av.date_fin_apres = contrat.date_fin
        av.version_contrat = contrat.version
        contrat.avenants.append(av)
        if data.regenerer_echeancier and (change_montant or change_duree):
            self._generer(contrat, remplacer=True)
        self._sync_statuts(contrat, await self._fenetre_due())
        self._refresh_echeance(contrat)
        self._hist(contrat, "avenant", user, contrat.statut, contrat.statut, f"Avenant n°{av.numero} : {av.objet}")
        if contrat.responsable_id and contrat.responsable_id != user.id:
            await self._notify(
                contrat.responsable_id,
                contrat,
                f"Avenant n°{av.numero} — {contrat.reference}",
                f"Un avenant ({type_avenant.lower()}) a été enregistré sur le contrat {contrat.reference}.",
                "contrats.avenant",
                user,
            )
        await self.db.commit()
        after = self._snapshot(contrat)
        changes = [k for k in FIELD_LABELS if before[k] != after[k]]
        await self._audit(
            user,
            "contrats.avenant",
            contrat.id,
            before={k: before[k] for k in changes},
            after={"avenant": av.numero, "type": type_avenant, "version": contrat.version, **{k: after[k] for k in changes}},
        )
        await self.db.commit()
        return await self.get_contrat(contrat.id)

    @staticmethod
    def _debut_periode(contrat: MgContrat) -> date:
        """Début de la période en cours : dernière reconduction tacite, sinon début du contrat."""
        reconductions = [a.date_effet for a in contrat.avenants if a.type_avenant == "RECONDUCTION" and a.date_effet]
        return max(reconductions, default=contrat.date_debut)

    async def reconduire(self, contrat_id: uuid.UUID, user: User) -> MgContrat:
        """Reconduction tacite : même contrat prolongé d'une période identique, échéancier complété."""
        contrat = await self._lock(contrat_id)
        if contrat.statut not in {"ACTIF", "EXPIRE"}:
            raise AppError("Reconduction possible pour un contrat actif ou expiré", code="RECONDUCTION_IMPOSSIBLE")
        if not contrat.date_fin:
            raise AppError("Contrat sans date de fin : reconduction sans objet", code="RECONDUCTION_IMPOSSIBLE")
        debut, fin = periode_suivante(self._debut_periode(contrat), contrat.date_fin)
        av = MgContratAvenant(
            numero=len(contrat.avenants) + 1,
            type_avenant="RECONDUCTION",
            objet=f"Reconduction tacite du {debut.strftime('%d/%m/%Y')} au {fin.strftime('%d/%m/%Y')}",
            date_effet=debut,
            montant_ht_avant=contrat.montant_ht,
            montant_ht_apres=contrat.montant_ht,
            montant_ttc_avant=contrat.montant,
            montant_ttc_apres=contrat.montant,
            date_fin_avant=contrat.date_fin,
            date_fin_apres=fin,
            user_id=user.id,
            user_nom=user.full_name,
        )
        old = contrat.statut
        contrat.date_fin = fin
        contrat.statut = "ACTIF"
        contrat.version = (contrat.version or 1) + 1
        av.version_contrat = contrat.version
        contrat.avenants.append(av)
        generees = 0
        if contrat.montant and contrat.montant > 0:
            generees = self._ajouter_plan(
                contrat, plan_echeancier(debut, fin, contrat.periodicite, contrat.montant), "Reconduction"
            )
        self._ajouter_preavis(contrat)
        self._sync_statuts(contrat, await self._fenetre_due())
        self._refresh_echeance(contrat)
        self._hist(contrat, "reconduire", user, old, "ACTIF", av.objet)
        await self.db.commit()
        await self._audit(
            user,
            "contrats.reconduire",
            contrat.id,
            before={"statut": old, "date_fin": _json(av.date_fin_avant)},
            after={"statut": "ACTIF", "date_fin": _json(fin), "echeances": generees, "version": contrat.version},
        )
        await self.db.commit()
        return await self.get_contrat(contrat.id)

    async def renouveler(self, contrat_id: uuid.UUID, user: User) -> MgContrat:
        """Reconduction expresse : nouveau contrat en brouillon, soumis au circuit de validation."""
        src = await self._lock(contrat_id)
        if src.statut not in {"ACTIF", "EXPIRE"}:
            raise AppError("Renouvellement possible pour un contrat actif ou expiré", code="RENOUVELLEMENT_IMPOSSIBLE")
        child = await self.db.scalar(
            select(MgContrat.id).where(
                MgContrat.contrat_precedent_id == src.id,
                MgContrat.deleted_at.is_(None),
                MgContrat.statut.notin_(["ANNULE"]),
            )
        )
        if child:
            raise AppError("Un renouvellement existe déjà pour ce contrat", code="RENOUVELLEMENT_EXISTANT")
        if src.date_debut and src.date_fin:
            debut, fin = periode_suivante(self._debut_periode(src), src.date_fin)
        else:
            debut, fin = date.today(), None
        nouveau = MgContrat(
            reference=await self._next_ref(),
            titre=src.titre,
            numero_contrat=src.numero_contrat,
            description=src.description,
            type_contrat=src.type_contrat,
            fournisseur_id=src.fournisseur_id,
            fournisseur_snapshot=src.fournisseur_snapshot,
            agence_id=src.agence_id,
            agence_libelle_snapshot=src.agence_libelle_snapshot,
            responsable_id=src.responsable_id,
            responsable_nom=src.responsable_nom,
            date_debut=debut,
            date_fin=fin,
            date_signature=None,
            montant=src.montant,
            montant_ht=src.montant_ht,
            taux_tva=src.taux_tva,
            devise=src.devise or "MRU",
            periodicite=src.periodicite,
            prochain_echeance=fin,
            alerte_jours=src.alerte_jours,
            mode_paiement=src.mode_paiement,
            ref_paiement=src.ref_paiement,
            reconduction=src.reconduction or "AUCUNE",
            preavis_jours=src.preavis_jours,
            observation=src.observation,
            contrat_precedent_id=src.id,
            version=1,
            statut="BROUILLON",
        )
        self._hist(nouveau, "renouveler", user, None, "BROUILLON", f"Issu de {src.reference}")
        self._hist(src, "renouveler", user, src.statut, src.statut, f"Renouvellement préparé : {nouveau.reference}")
        self.db.add(nouveau)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise AppError("Un renouvellement existe déjà pour ce contrat", code="RENOUVELLEMENT_EXISTANT")
        await self._audit(user, "contrats.renouveler", nouveau.id, after={"precedent": src.reference, "ref": nouveau.reference})
        await self.db.commit()
        return await self.get_contrat(nouveau.id)

    async def a_renouveler(self, horizon: int = 90) -> list[dict]:
        today = date.today()
        rows = await self.list_contrats()
        renouveles = {
            c.contrat_precedent_id for c in rows if c.contrat_precedent_id and c.statut != "ANNULE"
        }
        out = []
        for c in rows:
            if c.statut not in {"ACTIF", "SUSPENDU", "EXPIRE"} or not c.date_fin or c.id in renouveles:
                continue
            jours = (c.date_fin - today).days
            if jours > horizon:
                continue
            out.append(
                {
                    "id": str(c.id),
                    "reference": c.reference,
                    "titre": c.titre,
                    "fournisseur": c.fournisseur_snapshot,
                    "agence": c.agence_libelle_snapshot,
                    "date_fin": c.date_fin.isoformat(),
                    "date_preavis": c.date_preavis.isoformat() if c.date_preavis else None,
                    "jours": jours,
                    "reconduction": c.reconduction or "AUCUNE",
                    "montant": float(c.montant or 0),
                    "devise": c.devise,
                    "statut": c.statut,
                    "etat": c.etat,
                }
            )
        out.sort(key=lambda r: r["jours"])
        return out

    # ——— Vues transverses ———

    async def _echeances_rows(self) -> list[dict]:
        stmt = (
            select(MgContratEcheance, MgContrat)
            .join(MgContrat, MgContrat.id == MgContratEcheance.contrat_id)
            .where(MgContrat.deleted_at.is_(None))
            .order_by(MgContratEcheance.date_prevue)
        )
        if self.scope_agence:
            stmt = stmt.where(MgContrat.agence_id == self.scope_agence)
        rows = (await self.db.execute(stmt)).all()
        paid_stmt = (
            select(MgContratPaiement.echeance_id, func.coalesce(func.sum(MgContratPaiement.montant_paye), 0))
            .where(MgContratPaiement.echeance_id.is_not(None))
            .group_by(MgContratPaiement.echeance_id)
        )
        paid = {eid: Decimal(str(total)) for eid, total in (await self.db.execute(paid_stmt)).all()}
        fenetre = await self._fenetre_due()
        today = date.today()
        out = []
        for e, c in rows:
            paye = paid.get(e.id, Decimal("0"))
            statut = echeance_statut(
                date_prevue=e.date_prevue,
                montant=e.montant,
                montant_paye=paye,
                statut_actuel=e.statut,
                fenetre_due=fenetre,
                today=today,
            )
            reste = max((e.montant or Decimal("0")) - paye, Decimal("0")) if statut not in {"PAYEE", "FAITE", "ANNULEE"} else Decimal("0")
            out.append(
                {
                    "id": str(e.id),
                    "contrat_id": str(c.id),
                    "reference": c.reference,
                    "titre": c.titre,
                    "type_echeance": e.type_echeance,
                    "date_prevue": e.date_prevue.isoformat(),
                    "date_reelle": e.date_reelle.isoformat() if e.date_reelle else None,
                    "jours": (e.date_prevue - today).days,
                    "statut": statut,
                    "commentaire": e.commentaire,
                    "montant": float(e.montant) if e.montant is not None else None,
                    "montant_paye": float(paye),
                    "reste": float(reste),
                    "devise": c.devise,
                    "agence": c.agence_libelle_snapshot,
                    "agence_id": str(c.agence_id) if c.agence_id else None,
                    "fournisseur": c.fournisseur_snapshot,
                    "contrat_statut": c.statut,
                    "responsable_id": c.responsable_id,
                    "responsable": c.responsable_nom,
                    "alerte_jours": c.alerte_jours,
                    "_date": e.date_prevue,
                    "_montant": e.montant,
                    "_paye": paye,
                }
            )
        return out

    @staticmethod
    def _public(rows: list[dict]) -> list[dict]:
        return [
            {k: (str(v) if k == "responsable_id" and v else v) for k, v in r.items() if not k.startswith("_")}
            for r in rows
        ]

    async def list_echeances(
        self,
        horizon: str | None = None,
        statut: str | None = None,
        type_echeance: str | None = None,
        contrat_id: uuid.UUID | None = None,
        *,
        q: str | None = None,
        fournisseur: str | None = None,
        agence: str | None = None,
        date_du: date | None = None,
        date_au: date | None = None,
    ) -> list[dict]:
        rows = await self._echeances_rows()
        kept = []
        for r in rows:
            if horizon == "retard" and r["jours"] >= 0:
                continue
            if horizon in {"7", "30", "60", "90"} and not (0 <= r["jours"] <= int(horizon)):
                continue
            if statut and r["statut"] != statut:
                continue
            if type_echeance and r["type_echeance"] != type_echeance:
                continue
            if contrat_id and r["contrat_id"] != str(contrat_id):
                continue
            if not _match_ligne(r, q=q, fournisseur=fournisseur, agence=agence, jour=r["_date"], date_du=date_du, date_au=date_au):
                continue
            kept.append(r)
        return self._public(kept)

    async def list_paiements(
        self,
        statut: str | None = None,
        contrat_id: uuid.UUID | None = None,
        *,
        q: str | None = None,
        fournisseur: str | None = None,
        agence: str | None = None,
        date_du: date | None = None,
        date_au: date | None = None,
        montant_min: Decimal | None = None,
        montant_max: Decimal | None = None,
    ) -> list[dict]:
        stmt = (
            select(MgContratPaiement, MgContrat, MgContratEcheance)
            .join(MgContrat, MgContrat.id == MgContratPaiement.contrat_id)
            .outerjoin(MgContratEcheance, MgContratEcheance.id == MgContratPaiement.echeance_id)
            .where(MgContrat.deleted_at.is_(None))
            .order_by(MgContratPaiement.date_prevue.desc())
        )
        if self.scope_agence:
            stmt = stmt.where(MgContrat.agence_id == self.scope_agence)
        if contrat_id:
            stmt = stmt.where(MgContrat.id == contrat_id)
        if montant_min is not None:
            stmt = stmt.where(MgContratPaiement.montant_paye >= montant_min)
        if montant_max is not None:
            stmt = stmt.where(MgContratPaiement.montant_paye <= montant_max)
        out = []
        for pay, contrat, ech in (await self.db.execute(stmt)).all():
            s = paiement_statut(
                date_prevue=pay.date_prevue,
                date_reelle=pay.date_reelle,
                montant_prevu=pay.montant_prevu,
                montant_paye=pay.montant_paye,
            )
            if statut and s != statut:
                continue
            ligne = {
                "reference": contrat.reference,
                "titre": contrat.titre,
                "paiement_ref": pay.reference,
                "fournisseur": contrat.fournisseur_snapshot,
                "agence": contrat.agence_libelle_snapshot,
            }
            if not _match_ligne(
                ligne, q=q, fournisseur=fournisseur, agence=agence,
                jour=pay.date_reelle or pay.date_prevue, date_du=date_du, date_au=date_au,
            ):
                continue
            out.append(
                {
                    "id": str(pay.id),
                    "contrat_id": str(contrat.id),
                    "reference": contrat.reference,
                    "titre": contrat.titre,
                    "contrat_statut": contrat.statut,
                    "paiement_ref": pay.reference,
                    "echeance_id": str(pay.echeance_id) if pay.echeance_id else None,
                    "echeance_date": ech.date_prevue.isoformat() if ech else None,
                    "date_prevue": pay.date_prevue.isoformat(),
                    "date_reelle": pay.date_reelle.isoformat() if pay.date_reelle else None,
                    "montant_prevu": float(pay.montant_prevu or 0),
                    "montant_paye": float(pay.montant_paye or 0),
                    "reste": float(max((pay.montant_prevu or 0) - (pay.montant_paye or 0), 0)),
                    "ecart": float((pay.montant_paye or 0) - (pay.montant_prevu or 0)),
                    "statut": s,
                    "mode": pay.mode,
                    "commentaire": pay.commentaire,
                    "devise": pay.devise,
                    "fournisseur": contrat.fournisseur_snapshot,
                    "agence": contrat.agence_libelle_snapshot,
                }
            )
        return out

    async def alertes(self) -> list[dict]:
        await self.ensure_defaults()
        urgent = await self._param_int("contrats.alerte_urgent", 7)
        attention = await self._param_int("contrats.alerte_attention", 30)
        info = await self._param_int("contrats.alerte_info", 90)
        today = date.today()
        out: list[dict] = []

        def push(kind: str, c: MgContrat | None, *, jours: int | None, echeance: date | None, niveau: str, message: str, statut: str, **extra) -> None:
            out.append(
                {
                    "type": kind,
                    "contrat_id": str(c.id) if c else extra.get("contrat_id"),
                    "reference": c.reference if c else extra.get("reference"),
                    "titre": c.titre if c else extra.get("titre"),
                    "fournisseur": c.fournisseur_snapshot if c else extra.get("fournisseur"),
                    "agence": c.agence_libelle_snapshot if c else extra.get("agence"),
                    "responsable": c.responsable_nom if c else extra.get("responsable"),
                    "responsable_id": str(c.responsable_id) if c and c.responsable_id else extra.get("responsable_id"),
                    "alerte_jours": (c.alerte_jours if c else extra.get("alerte_jours")) or attention,
                    "echeance": echeance.isoformat() if echeance else None,
                    "jours": jours,
                    "niveau": niveau,
                    "statut": statut,
                    "message": message,
                }
            )

        for c in await self.list_contrats():
            if c.statut not in {"ACTIF", "SUSPENDU", "EN_VALIDATION"}:
                continue
            fenetre = c.alerte_jours if c.alerte_jours and c.alerte_jours > 0 else info
            if c.date_fin:
                jours = (c.date_fin - today).days
                if jours <= fenetre:
                    msg = (
                        f"Date de fin dépassée de {-jours} j : clôturer, reconduire ou renouveler"
                        if jours < 0
                        else f"Fin du contrat dans {jours} j"
                    )
                    push("expiration", c, jours=jours, echeance=c.date_fin, niveau=niveau_alerte(jours, urgent, attention), message=msg, statut=c.statut)
            if c.date_preavis and c.statut in {"ACTIF", "SUSPENDU"}:
                jp = (c.date_preavis - today).days
                if 0 <= jp <= fenetre:
                    push(
                        "preavis",
                        c,
                        jours=jp,
                        echeance=c.date_preavis,
                        niveau=niveau_alerte(jp, urgent, attention),
                        message=f"Préavis à notifier avant le {c.date_preavis.strftime('%d/%m/%Y')}"
                        + (" (sinon reconduction tacite)" if c.reconduction == "TACITE" else ""),
                        statut=c.statut,
                    )
            if c.statut == "ACTIF" and not c.responsable_id:
                push("sans_responsable", c, jours=None, echeance=None, niveau="ATTENTION", message="Aucun responsable interne désigné", statut=c.statut)
            if c.statut == "ACTIF" and not c.fournisseur_id and not (c.fournisseur_snapshot or "").strip():
                push("sans_fournisseur", c, jours=None, echeance=None, niveau="ATTENTION", message="Aucun fournisseur renseigné", statut=c.statut)

        for r in await self._echeances_rows():
            if r["contrat_statut"] not in {"ACTIF", "SUSPENDU", "EXPIRE"}:
                continue
            if r["statut"] not in {"DUE", "EN_RETARD"}:
                continue
            paiement = r["type_echeance"] == "PAIEMENT"
            reste = f" — reste {r['reste']:,.2f} {r['devise'] or 'MRU'}".replace(",", " ") if paiement and r["reste"] else ""
            push(
                "paiement" if paiement else "echeance",
                None,
                jours=r["jours"],
                echeance=r["_date"],
                niveau=niveau_alerte(r["jours"], urgent, attention),
                message=("Paiement en retard" if r["statut"] == "EN_RETARD" else "Paiement à effectuer") + reste
                if paiement
                else f"Échéance {r['type_echeance'].lower()} {'dépassée' if r['statut'] == 'EN_RETARD' else 'imminente'}",
                statut=r["statut"],
                contrat_id=r["contrat_id"],
                reference=r["reference"],
                titre=r["titre"],
                fournisseur=r["fournisseur"],
                agence=r["agence"],
                responsable=r["responsable"],
                responsable_id=str(r["responsable_id"]) if r["responsable_id"] else None,
                alerte_jours=r["alerte_jours"],
            )

        ordre = {"CRITIQUE": 0, "URGENT": 1, "ATTENTION": 2, "INFO": 3}
        out.sort(key=lambda a: (ordre.get(a["niveau"], 9), a["jours"] if a["jours"] is not None else 9999))
        return out

    async def dashboard(self) -> dict:
        rows = await self.list_contrats()
        today = date.today()

        def count(statut: str) -> int:
            return sum(1 for c in rows if c.statut == statut)

        actifs = [c for c in rows if c.statut == "ACTIF"]
        echeances = [r for r in await self._echeances_rows() if r["contrat_statut"] in {"ACTIF", "SUSPENDU", "EXPIRE"}]
        a_venir = sum((Decimal(str(r["reste"])) for r in echeances if r["type_echeance"] == "PAIEMENT" and r["jours"] >= 0), Decimal("0"))
        en_retard = sum((Decimal(str(r["reste"])) for r in echeances if r["statut"] == "EN_RETARD"), Decimal("0"))
        debut_annee = date(today.year, 1, 1)
        paye_annee = await self.db.scalar(
            select(func.coalesce(func.sum(MgContratPaiement.montant_paye), 0))
            .join(MgContrat, MgContrat.id == MgContratPaiement.contrat_id)
            .where(
                MgContrat.deleted_at.is_(None),
                MgContratPaiement.date_reelle >= debut_annee,
                *([MgContrat.agence_id == self.scope_agence] if self.scope_agence else []),
            )
        )
        par_type: dict[str, dict] = defaultdict(lambda: {"count": 0, "montant": 0.0})
        par_fournisseur: dict[str, float] = defaultdict(float)
        for c in actifs:
            par_type[c.type_contrat]["count"] += 1
            par_type[c.type_contrat]["montant"] += float(c.montant or 0)
            par_fournisseur[c.fournisseur_snapshot or "—"] += float(c.montant or 0)
        alertes = await self.alertes() if rows else []
        prochaines = [
            r for r in echeances if r["statut"] in {"A_VENIR", "DUE", "EN_RETARD"}
        ]
        prochaines.sort(key=lambda r: r["_date"])
        annuel = sum((montant_annualise(c.montant, c.date_debut, c.date_fin) for c in actifs), Decimal("0"))
        a_renouveler = await self.a_renouveler(90) if rows else []
        return {
            "total": len(rows),
            "montant_annuel": float(annuel),
            "montant_mensuel": float((annuel / 12).quantize(Decimal("0.01"))),
            "a_renouveler": len(a_renouveler),
            "expirant_bientot": sum(1 for c in rows if c.etat == "ECHEANCE_30"),
            "actifs": len(actifs),
            "brouillons": count("BROUILLON"),
            "en_validation": count("EN_VALIDATION"),
            "rejetes": count("REJETE"),
            "suspendus": count("SUSPENDU"),
            "expires": count("EXPIRE"),
            "date_depassee": sum(1 for c in rows if c.etat == "DATE_DEPASSEE"),
            "echeance_30": sum(1 for c in rows if c.etat == "ECHEANCE_30"),
            "archives": count("ARCHIVE"),
            "annules": count("ANNULE"),
            "montant_actifs": float(sum((c.montant or Decimal("0") for c in actifs), Decimal("0"))),
            "paiements_a_venir": float(a_venir),
            "paiements_en_retard": float(en_retard),
            "paye_annee": float(paye_annee or 0),
            "alertes": len(alertes),
            "alertes_critiques": sum(1 for a in alertes if a["niveau"] in {"CRITIQUE", "URGENT"}),
            "prochaines_echeances": self._public(prochaines[:8]),
            "alertes_top": alertes[:6],
            "par_type": sorted(
                ({"type": k, **v} for k, v in par_type.items()), key=lambda x: x["montant"], reverse=True
            ),
            "top_fournisseurs": sorted(
                ({"fournisseur": k, "montant": v} for k, v in par_fournisseur.items()),
                key=lambda x: x["montant"],
                reverse=True,
            )[:5],
        }

    # ——— Rappels (notifications + e-mail) ———

    async def envoyer_rappels(self, *, force: bool = False) -> dict:
        settings = get_settings()
        debut_jour = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
        notifs = 0
        mails = 0
        for a in await self.alertes():
            if not a.get("responsable_id") or a["jours"] is None:
                continue
            if not force and not doit_rappeler(a["jours"], int(a.get("alerte_jours") or 30)):
                continue
            event = f"contrats.rappel.{a['type']}"
            user_id = uuid.UUID(a["responsable_id"])
            deja = await self.db.scalar(
                select(Notification.id).where(
                    Notification.user_id == user_id,
                    Notification.event_type == event,
                    Notification.entity_id == a["contrat_id"],
                    Notification.created_at >= debut_jour,
                ).limit(1)
            )
            if deja:
                continue
            titre = f"Rappel contrat {a['reference']} — {a['message']}"
            message = (
                f"{a['titre']} ({a.get('fournisseur') or 'fournisseur non renseigné'}). "
                f"{a['message']}"
                + (f" — échéance du {datetime.fromisoformat(a['echeance']).strftime('%d/%m/%Y')}." if a.get("echeance") else ".")
            )
            await NotificationService(self.db).create(
                user_id=user_id,
                type_notification=TypeNotification.SYSTEME,
                titre=titre[:255],
                message=message,
                entity="contrat",
                entity_id=a["contrat_id"],
                espace_code="moyens-generaux",
                module_code="contrats-echeances",
                priorite="haute" if a["niveau"] in {"CRITIQUE", "URGENT"} else None,
                event_type=event,
                emetteur_label="Contrats & échéances",
            )
            notifs += 1
            dest = await self.db.get(User, user_id)
            lien = f"{settings.public_app_url.rstrip('/')}/contrats-echeances/{a['contrat_id']}"
            if dest and await send_mail(dest.email, titre, f"Bonjour {dest.full_name},\n\n{message}\n\nOuvrir le contrat : {lien}\n\nBEA DIGITAL"):
                mails += 1
        await self.db.commit()
        return {"notifications": notifs, "emails": mails}

    # ——— Référentiels ———

    async def list_responsables(self, q: str | None = None) -> list[dict]:
        stmt = select(User).where(User.deleted_at.is_(None), User.is_active.is_(True))
        if q and q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
        rows = list((await self.db.execute(stmt.order_by(User.full_name).limit(200))).scalars().all())
        return [{"id": str(u.id), "full_name": u.full_name, "email": u.email} for u in rows]

    async def list_agences(self) -> list[Agence]:
        stmt = select(Agence).where(Agence.is_active.is_(True), Agence.deleted_at.is_(None))
        if self.scope_agence:
            stmt = stmt.where(Agence.id == self.scope_agence)
        return list((await self.db.execute(stmt.order_by(Agence.libelle))).scalars().all())

    async def list_fournisseurs(self, q: str | None = None) -> list[dict]:
        stmt = select(Fournisseur).where(Fournisseur.deleted_at.is_(None), Fournisseur.is_active.is_(True))
        if q and q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(Fournisseur.raison_sociale.ilike(like), Fournisseur.code.ilike(like)))
        rows = list((await self.db.execute(stmt.order_by(Fournisseur.raison_sociale).limit(200))).scalars().all())
        return [
            {
                "id": str(f.id),
                "code": f.code,
                "raison_sociale": f.raison_sociale,
                "telephone": f.telephone,
                "email": f.email,
                "adresse": f.adresse,
            }
            for f in rows
        ]

    async def list_types(self) -> list[MgContratType]:
        await self.ensure_defaults()
        return list((await self.db.execute(select(MgContratType).order_by(MgContratType.libelle))).scalars().all())

    async def list_params(self) -> list[MgContratParametre]:
        await self.ensure_defaults()
        return list((await self.db.execute(select(MgContratParametre).order_by(MgContratParametre.cle))).scalars().all())

    async def set_param(self, cle: str, valeur: str, libelle: str | None = None) -> MgContratParametre:
        row = await self.db.scalar(select(MgContratParametre).where(MgContratParametre.cle == cle))
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paramètre introuvable")
        if cle != "contrats.prefixe" and cle in {p[0] for p in DEFAULT_PARAMS}:
            try:
                if Decimal(valeur) < 0:
                    raise ValueError
            except (ArithmeticError, ValueError):
                raise AppError("Valeur numérique positive attendue", code="PARAMETRE_INVALIDE")
        row.valeur = valeur
        if libelle is not None:
            row.libelle = libelle.strip() or row.libelle
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def create_param(self, cle: str, valeur: str, libelle: str | None) -> MgContratParametre:
        key = cle.strip()
        if not key:
            raise AppError("Clé obligatoire", code="CHAMP_OBLIGATOIRE")
        exists = await self.db.scalar(select(MgContratParametre.id).where(MgContratParametre.cle == key))
        if exists:
            raise AppError("Ce paramètre existe déjà", code="PARAMETRE_EXISTANT")
        row = MgContratParametre(cle=key, valeur=valeur, libelle=(libelle or "").strip() or None)
        self.db.add(row)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise AppError("Ce paramètre existe déjà", code="PARAMETRE_EXISTANT")
        await self.db.refresh(row)
        return row

    async def delete_param(self, cle: str) -> None:
        if cle in {p[0] for p in DEFAULT_PARAMS}:
            raise AppError("Paramètre système : modifiable mais non supprimable", code="PARAMETRE_SYSTEME")
        row = await self.db.scalar(select(MgContratParametre).where(MgContratParametre.cle == cle))
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paramètre introuvable")
        await self.db.delete(row)
        await self.db.commit()

    async def create_type(self, code: str, libelle: str) -> MgContratType:
        key = code.strip().upper().replace(" ", "_")
        label = libelle.strip()
        if not key or not label:
            raise AppError("Code et libellé obligatoires", code="CHAMP_OBLIGATOIRE")
        row = MgContratType(code=key, libelle=label, actif=True)
        self.db.add(row)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise AppError("Ce type existe déjà", code="PARAMETRE_EXISTANT")
        await self.db.refresh(row)
        return row

    async def update_type(self, type_id: uuid.UUID, *, libelle: str | None, actif: bool | None) -> MgContratType:
        row = await self.db.get(MgContratType, type_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Type introuvable")
        if libelle is not None and libelle.strip():
            row.libelle = libelle.strip()
        if actif is not None:
            row.actif = actif
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def delete_type(self, type_id: uuid.UUID) -> dict:
        row = await self.db.get(MgContratType, type_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Type introuvable")
        used = await self.db.scalar(
            select(func.count()).select_from(MgContrat).where(
                MgContrat.deleted_at.is_(None),
                MgContrat.type_contrat == row.code,
            )
        )
        if used:
            row.actif = False
            await self.db.commit()
            return {"ok": True, "desactive": True}
        await self.db.delete(row)
        await self.db.commit()
        return {"ok": True, "desactive": False}

    # ——— Rapports ———

    async def rapport(
        self, report_key: str, *, annee: int | None = None, periode: str | None = None, filtres: dict | None = None
    ) -> dict:
        today = date.today()
        annee = annee or today.year
        types = {t.code: t.libelle for t in await self.list_types()}
        f = {k: v for k, v in (filtres or {}).items() if v not in (None, "")}

        def jj(iso: str | None) -> str:
            return datetime.fromisoformat(iso).strftime("%d/%m/%Y") if iso else ""

        if report_key == "registre":
            src = await self.list_contrats(
                q=f.get("q"), statut=f.get("statut"), etat=f.get("etat"), agence_id=f.get("agence_id"),
                fournisseur_id=f.get("fournisseur_id"), type_contrat=f.get("type_contrat"), horizon=f.get("horizon"),
            )
            return {
                "title": "Registre des contrats",
                "headers": [
                    "N° contrat", "Objet", "Fournisseur", "Type", "Agence", "Début", "Fin", "Montant TTC",
                    "Périodicité", "Statut", "Reconduction", "Prochaine échéance",
                ],
                "rows": [
                    [
                        c.reference, c.titre, c.fournisseur_snapshot or "", types.get(c.type_contrat, c.type_contrat),
                        c.agence_libelle_snapshot or "", c.date_debut.strftime("%d/%m/%Y"),
                        c.date_fin.strftime("%d/%m/%Y") if c.date_fin else "", float(c.montant or 0),
                        c.periodicite or "", c.statut, c.reconduction or "",
                        c.prochain_echeance.strftime("%d/%m/%Y") if c.prochain_echeance else "",
                    ]
                    for c in src
                ],
            }
        if report_key == "echeancier":
            src = await self.list_echeances(
                f.get("horizon"), f.get("statut"), f.get("type_echeance"), f.get("contrat_id"),
                q=f.get("q"), fournisseur=f.get("fournisseur"), agence=f.get("agence"),
                date_du=f.get("date_du"), date_au=f.get("date_au"),
            )
            return {
                "title": "Échéancier des contrats",
                "headers": ["Contrat", "Objet", "Fournisseur", "Agence", "Type", "Date prévue", "Jours", "Montant", "Payé", "Reste", "Statut"],
                "rows": [
                    [
                        r["reference"], r["titre"], r["fournisseur"] or "", r["agence"] or "", r["type_echeance"],
                        jj(r["date_prevue"]), r["jours"], r["montant"] or 0, r["montant_paye"], r["reste"], r["statut"],
                    ]
                    for r in src
                ],
            }
        if report_key == "reglements":
            src = await self.list_paiements(
                f.get("statut"), f.get("contrat_id"), q=f.get("q"), fournisseur=f.get("fournisseur"),
                agence=f.get("agence"), date_du=f.get("date_du"), date_au=f.get("date_au"),
                montant_min=f.get("montant_min"), montant_max=f.get("montant_max"),
            )
            return {
                "title": "Paiements des contrats",
                "headers": ["Contrat", "Objet", "Fournisseur", "Agence", "N° pièce", "Prévu le", "Payé le", "Prévu", "Payé", "Reste", "Mode", "Statut"],
                "rows": [
                    [
                        p["reference"], p["titre"], p["fournisseur"] or "", p["agence"] or "", p["paiement_ref"] or "",
                        jj(p["date_prevue"]), jj(p["date_reelle"]), p["montant_prevu"], p["montant_paye"], p["reste"],
                        p["mode"] or "", p["statut"],
                    ]
                    for p in src
                ],
            }

        contrats = await self.list_contrats()

        def ligne(c: MgContrat) -> list:
            return [
                c.reference,
                c.titre,
                types.get(c.type_contrat, c.type_contrat),
                c.fournisseur_snapshot or "",
                c.agence_libelle_snapshot or "",
                c.date_debut.strftime("%d/%m/%Y"),
                c.date_fin.strftime("%d/%m/%Y") if c.date_fin else "",
                float(c.montant or 0),
                c.statut,
            ]

        entetes = ["Référence", "Objet", "Type", "Fournisseur", "Agence", "Début", "Fin", "Montant TTC", "Statut"]
        if report_key in {"liste", "actifs", "expires", "echeances"}:
            src = contrats
            titre = "Liste des contrats"
            if report_key == "actifs":
                src, titre = [c for c in contrats if c.statut == "ACTIF"], "Contrats actifs"
            elif report_key == "expires":
                src = [c for c in contrats if c.statut == "EXPIRE" or c.etat == "DATE_DEPASSEE"]
                titre = "Contrats expirés ou à date dépassée"
            elif report_key == "echeances":
                src, titre = await self.list_contrats(horizon="90"), "Contrats — échéance à 90 jours"
            return {"title": titre, "headers": entetes, "rows": [ligne(c) for c in src]}

        echeances = [
            r for r in await self._echeances_rows()
            if r["type_echeance"] == "PAIEMENT" and r["contrat_statut"] not in {"ANNULE", "BROUILLON", "REJETE"}
        ]
        if report_key == "paiements":
            rows = [
                [
                    p["reference"],
                    p["titre"],
                    p["fournisseur"] or "",
                    p["paiement_ref"] or "",
                    datetime.fromisoformat(p["date_prevue"]).strftime("%d/%m/%Y"),
                    datetime.fromisoformat(p["date_reelle"]).strftime("%d/%m/%Y") if p["date_reelle"] else "",
                    p["montant_prevu"],
                    p["montant_paye"],
                    p["ecart"],
                    p["mode"] or "",
                    p["statut"],
                ]
                for p in await self.list_paiements()
                if datetime.fromisoformat(p["date_prevue"]).year == annee
            ]
            return {
                "title": f"Rapprochement des paiements {annee}",
                "headers": ["Contrat", "Objet", "Fournisseur", "N° pièce", "Prévu le", "Payé le", "Prévu", "Payé", "Écart", "Mode", "Statut"],
                "rows": rows,
            }

        if report_key in {"financier_fournisseur", "financier_agence"}:
            cle = "fournisseur" if report_key == "financier_fournisseur" else "agence"
            agg: dict[str, dict] = defaultdict(lambda: {"contrats": set(), "engagement": 0.0, "prevu": 0.0, "paye": 0.0})
            for c in contrats:
                if c.statut in {"ACTIF", "SUSPENDU"}:
                    nom = (c.fournisseur_snapshot if cle == "fournisseur" else c.agence_libelle_snapshot) or "—"
                    agg[nom]["contrats"].add(c.id)
                    agg[nom]["engagement"] += float(c.montant or 0)
            for r in echeances:
                if r["_date"].year != annee:
                    continue
                nom = r[cle] or "—"
                agg[nom]["prevu"] += float(r["_montant"] or 0)
                agg[nom]["paye"] += float(r["_paye"])
            rows = [
                [nom, len(v["contrats"]), v["engagement"], v["prevu"], v["paye"], max(v["prevu"] - v["paye"], 0)]
                for nom, v in sorted(agg.items(), key=lambda kv: kv[1]["engagement"], reverse=True)
            ]
            libelle = "Fournisseur" if cle == "fournisseur" else "Agence"
            return {
                "title": f"Engagements par {libelle.lower()} — {annee}",
                "headers": [libelle, "Contrats actifs", "Engagement TTC", f"Prévu {annee}", f"Payé {annee}", "Reste à payer"],
                "rows": rows,
            }

        if report_key == "financier_periode":
            mois = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
            prevu = [0.0] * 12
            paye = [0.0] * 12
            for r in echeances:
                if r["_date"].year == annee:
                    prevu[r["_date"].month - 1] += float(r["_montant"] or 0)
            pay_stmt = (
                select(MgContratPaiement.date_reelle, MgContratPaiement.montant_paye)
                .join(MgContrat, MgContrat.id == MgContratPaiement.contrat_id)
                .where(
                    MgContrat.deleted_at.is_(None),
                    MgContratPaiement.date_reelle >= date(annee, 1, 1),
                    MgContratPaiement.date_reelle <= date(annee, 12, 31),
                )
            )
            if self.scope_agence:
                pay_stmt = pay_stmt.where(MgContrat.agence_id == self.scope_agence)
            for d, m in (await self.db.execute(pay_stmt)).all():
                paye[d.month - 1] += float(m or 0)
            rows = [[mois[i], prevu[i], paye[i], paye[i] - prevu[i]] for i in range(12)]
            rows.append(["Total", sum(prevu), sum(paye), sum(paye) - sum(prevu)])
            return {
                "title": f"Engagements budgétaires mensuels — {annee}",
                "headers": ["Mois", "Échéances prévues", "Paiements réalisés", "Écart"],
                "rows": rows,
            }

        if report_key == "renouvellements":
            horizon = 90 if (periode or "trimestre") == "trimestre" else 365
            rows = [
                [
                    r["reference"],
                    r["titre"],
                    r["fournisseur"] or "",
                    r["agence"] or "",
                    datetime.fromisoformat(r["date_fin"]).strftime("%d/%m/%Y"),
                    r["jours"],
                    datetime.fromisoformat(r["date_preavis"]).strftime("%d/%m/%Y") if r["date_preavis"] else "",
                    {"TACITE": "Tacite", "EXPRESSE": "Expresse"}.get(r["reconduction"], "Aucune"),
                    r["montant"],
                    r["statut"],
                ]
                for r in await self.a_renouveler(horizon)
            ]
            return {
                "title": f"Contrats à renégocier — {'trimestre' if horizon == 90 else 'année'} à venir",
                "headers": ["Référence", "Objet", "Fournisseur", "Agence", "Fin", "Jours", "Préavis", "Reconduction", "Montant TTC", "Statut"],
                "rows": rows,
            }

        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rapport inconnu")

    async def export(
        self,
        user: User,
        report_key: str,
        fmt: str,
        *,
        annee: int | None = None,
        periode: str | None = None,
        filtres: dict | None = None,
    ):
        data = await self.rapport(report_key, annee=annee, periode=periode, filtres=filtres)
        headers, rows, title = data["headers"], data["rows"], data["title"]
        if fmt == "json":
            return {"key": report_key, "title": title, "headers": headers, "rows": rows, "count": len(rows)}
        if fmt not in {"pdf", "xlsx"}:
            raise AppError("Format d'export non pris en charge (PDF ou Excel)", code="FORMAT_INVALIDE")
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aucune donnée pour ce rapport")
        actifs = {k: str(v) for k, v in (filtres or {}).items() if v not in (None, "")}
        await self._audit(
            user, "contrats.export", None, after={"rapport": report_key, "format": fmt, "annee": annee, "filtres": actifs}
        )
        await self.db.commit()
        when = export_now()
        full_title = f"BEA DIGITAL — {title}"
        subtitle = f"Généré par {user.full_name or user.email}"
        if actifs:
            subtitle += f" · {len(rows)} ligne(s) · filtres appliqués"
        filename = f"contrats-{report_key}"
        if fmt == "pdf":
            content = build_styled_pdf(
                report_title=full_title,
                headers=headers,
                rows=rows,
                subtitle=subtitle,
                exported_at=when,
                landscape_mode=True,
            )
            return Response(
                content=content,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
            )
        content = build_styled_workbook(
            sheet_title="Contrats",
            report_title=full_title,
            headers=headers,
            rows=rows,
            subtitle=subtitle,
            exported_at=when,
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
        )
