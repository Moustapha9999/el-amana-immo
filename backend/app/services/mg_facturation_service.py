"""Moyens Généraux — Contrats & échéances : gestion des factures.

Registre unique des factures fournisseurs = ``mg_achat_factures`` (origine FACTURATION),
paiements = ``mg_achat_paiements``, historique = ``mg_achat_evenements``,
pièces = GED centrale (entity « facture »), paramètres = ``mg_contrat_parametres``.
Seule entité nouvelle : ``mg_points_facturation`` (compteur / abonnement d'un site).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import and_, func, null, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models.auth import Agence, User
from app.models.ged import GedDocument
from app.models.mg_achats import (
    ORIGINE_FACTURATION,
    MgAchatEvenement,
    MgAchatFacture,
    MgAchatFactureLigne,
    MgAchatPaiement,
)
from app.models.mg_ops import MgContrat, MgContratParametre, MgFacturationProfil, MgPointFacturation
from app.models.organisation import Fournisseur
from app.schemas.mg_facturation import (
    FactureCreate,
    FacturePaiementIn,
    FacturePaiementUpdate,
    FactureUpdate,
    PointFacturationCreate,
    PointFacturationIn,
    ProfilCreate,
    ProfilIn,
)
from app.services.audit_helpers import record_audit
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

ESPACE = "moyens-generaux"
MODULE = "facturation-fournisseurs"
GED_ENTITY = "facture"
EVT_FACTURE = "facture"
EVT_POINT = "point_facturation"

CENT = Decimal("0.01")
ZERO = Decimal("0")
TOLERANCE = Decimal("0.005")

STATUTS = ("BROUILLON", "RECUE", "A_CONTROLER", "CONTROLEE", "VALIDEE", "CONTESTEE", "ANNULEE", "ARCHIVEE")
STATUT_LABELS = {
    "BROUILLON": "Brouillon",
    "RECUE": "Reçue",
    "A_CONTROLER": "À contrôler",
    "CONTROLEE": "Contrôlée",
    "VALIDEE": "Validée",
    "CONTESTEE": "Contestée",
    "ANNULEE": "Annulée",
    "ARCHIVEE": "Archivée",
}
STATUTS_PAIEMENT = ("A_PAYER", "PARTIELLEMENT_PAYEE", "PAYEE")
STATUT_PAIEMENT_LABELS = {"A_PAYER": "À payer", "PARTIELLEMENT_PAYEE": "Partiellement payée", "PAYEE": "Payée"}
# Dette reconnue ou en cours de reconnaissance : suivie pour les échéances et retards.
STATUTS_OUVERTS = frozenset({"RECUE", "A_CONTROLER", "CONTROLEE", "VALIDEE"})
# Inclus dans les montants facturés (analyses, tableaux de bord).
STATUTS_COMPTES = frozenset({"RECUE", "A_CONTROLER", "CONTROLEE", "VALIDEE", "CONTESTEE", "ARCHIVEE"})
STATUTS_PAYABLES = frozenset({"VALIDEE", "ARCHIVEE"})
VERROUILLES = frozenset({"ANNULEE", "ARCHIVEE"})

TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "enregistrer": (frozenset({"BROUILLON"}), "RECUE"),
    "controler": (frozenset({"BROUILLON", "RECUE", "CONTROLEE", "CONTESTEE"}), "A_CONTROLER"),
    "valider_controle": (frozenset({"RECUE", "A_CONTROLER"}), "CONTROLEE"),
    "valider": (frozenset({"CONTROLEE"}), "VALIDEE"),
    "contester": (frozenset({"RECUE", "A_CONTROLER", "CONTROLEE", "VALIDEE"}), "CONTESTEE"),
    "annuler": (frozenset({"BROUILLON", "RECUE", "A_CONTROLER", "CONTROLEE", "VALIDEE", "CONTESTEE"}), "ANNULEE"),
    "archiver": (frozenset({"VALIDEE", "ANNULEE"}), "ARCHIVEE"),
}
PERMISSION_ACTION = {
    "enregistrer": "mg.factures.update",
    "controler": "mg.factures.update",
    "valider_controle": "mg.factures.update",
    "valider": "mg.factures.validate",
    "contester": "mg.factures.validate",
    "annuler": "mg.factures.delete",
    "archiver": "mg.factures.archive",
}
ACTION_LABELS = {
    "enregistrer": "Facture enregistrée (reçue)",
    "controler": "Facture mise en contrôle",
    "valider_controle": "Contrôle terminé",
    "valider": "Facture validée",
    "contester": "Facture contestée",
    "annuler": "Facture annulée",
    "archiver": "Facture archivée",
}
MOTIF_OBLIGATOIRE = frozenset({"contester", "annuler"})

TYPES_POINT = ("AGENCE", "SIEGE", "PDV", "AUTRE")
TYPE_POINT_LABELS = {"AGENCE": "Agence", "SIEGE": "Siège", "PDV": "PDV Amanty", "AUTRE": "Autre site"}
PERIODICITES_POINT = {"MENSUEL": 1, "BIMESTRIEL": 2, "TRIMESTRIEL": 3, "SEMESTRIEL": 6, "ANNUEL": 12, "PONCTUEL": 0}
TYPES_FACTURE = [
    ("ELECTRICITE", "Électricité"),
    ("EAU", "Eau"),
    ("TELEPHONE", "Téléphonie"),
    ("INTERNET", "Internet / données"),
    ("LOYER", "Loyer"),
    ("GARDIENNAGE", "Gardiennage"),
    ("NETTOYAGE", "Nettoyage"),
    ("MAINTENANCE", "Maintenance"),
    ("AUTRE", "Autre"),
]
TYPES_DOCUMENT = [
    ("FACTURE_ORIGINALE", "Facture originale"),
    ("FACTURE_SCANNEE", "Facture scannée"),
    ("JUSTIFICATIF", "Bon / justificatif"),
    ("PREUVE_PAIEMENT", "Preuve de paiement"),
    ("CORRESPONDANCE", "Correspondance"),
    ("AVOIR", "Avoir"),
    ("AUTRE", "Autre"),
]
MODES_PAIEMENT = ["Amanty", "Virement", "Carte", "Chèque", "Espèces", "Prélèvement"]
DEVISES = ["MRU", "EUR", "USD"]
MOIS_LABELS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]
MOIS_COURTS = ["Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc."]

DEFAULT_PARAMS = [
    ("factures.prefixe", "FACT", "Préfixe des références internes de factures"),
    ("factures.prefixe_point", "PF", "Préfixe des codes de points de facturation"),
    ("factures.delai_paiement_jours", "0", "Échéance par défaut : jours après la date de facture (0 = aucune)"),
    ("factures.alerte_echeance_jours", "7", "Factures — jours avant échéance pour l'alerte « échéance proche »"),
    ("factures.seuil_hausse_pct", "30", "Factures — hausse anormale (% au-dessus de la moyenne des 6 dernières)"),
    ("factures.delai_reception_jours", "5", "Factures — jours après la fin du mois avant d'alerter « facture manquante »"),
]
PARAMS_NUMERIQUES = frozenset(k for k, _, _ in DEFAULT_PARAMS if not k.startswith("factures.prefixe"))

GESTION_PERMISSIONS = ("mg.factures.create", "mg.factures.update", "mg.factures.validate", "mg.facturation.manage")

CHAMPS_FINANCIERS = frozenset(
    {"montant_ht", "montant_tva", "autres_taxes", "remise", "montant_ttc", "montant_a_payer", "devise", "lignes",
     "fournisseur_id", "numero_fournisseur", "arrieres", "reglage", "profil_id"}
)
CHAMPS_LABELS = {
    "numero_fournisseur": "N° facture fournisseur",
    "fournisseur_id": "Fournisseur",
    "profil_id": "Profil de facturation",
    "point_facturation_id": "Point de facturation",
    "agence_id": "Agence",
    "contrat_id": "Contrat",
    "type_facture": "Type",
    "reference_fournisseur": "Réf. fournisseur",
    "date_facture": "Date facture",
    "date_reception": "Date réception",
    "periode_debut": "Début période",
    "periode_fin": "Fin période",
    "mois": "Mois",
    "annee": "Année",
    "date_echeance": "Échéance",
    "montant_ht": "Montant HT",
    "montant_tva": "TVA",
    "autres_taxes": "Autres taxes",
    "remise": "Remise",
    "montant_ttc": "Montant TTC",
    "arrieres": "Arriérés",
    "reglage": "Réglage",
    "montant_a_payer": "Montant à payer",
    "devise": "Devise",
    "observation": "Observation",
}

# Champs configurables par profil de facturation (libellé par défaut). Les champs communs
# (fournisseur, point, agence, date de facture, réception, devise, observation) restent toujours affichés.
CHAMPS_PROFIL = {
    "numero_fournisseur": "N° facture",
    "reference_fournisseur": "Référence (compteur / abonnement)",
    "periode": "Période facturée",
    "periode_debut": "Début de période",
    "periode_fin": "Fin de période",
    "montant_ht": "Montant HT",
    "montant_tva": "TVA",
    "autres_taxes": "Autres taxes / redevances",
    "remise": "Remise",
    "montant_ttc": "Montant TTC",
    "arrieres": "Arriérés",
    "reglage": "Réglage",
    "montant_a_payer": "Total à payer",
    "date_echeance": "Échéance",
}
ETATS_CHAMP = ("obligatoire", "facultatif", "masque")

# Détail exigé par moyen de paiement : champ → (libellé, obligatoire).
MOYENS_PAIEMENT: dict[str, dict[str, tuple[str, bool]]] = {
    "Amanty": {"compte": ("N° / compte Amanty", True), "reference_paiement": ("Référence transaction", False)},
    "Virement": {
        "compte": ("RIB / compte émetteur", True),
        "banque": ("Banque", False),
        "reference_paiement": ("Référence du virement", False),
    },
    "Carte": {
        "carte_derniers_chiffres": ("4 derniers chiffres de la carte", True),
        "reference_paiement": ("Référence transaction", False),
    },
    "Chèque": {"numero_cheque": ("N° de chèque", True), "banque": ("Banque", False), "compte": ("Compte", False)},
    "Espèces": {"reference_paiement": ("Caisse / référence", False)},
    "Prélèvement": {"compte": ("Compte prélevé", False), "reference_paiement": ("Référence", False)},
}
CHAMPS_DETAIL_PAIEMENT = ("compte", "banque", "numero_cheque", "carte_derniers_chiffres", "reference_paiement")


# ——— Règles pures (testées unitairement) ———


def q2(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(CENT)


def to_float(value) -> float | None:
    return None if value is None else float(value)


def sans_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()


def decouper_reference(raw) -> tuple[str, str, str | None]:
    """Référence fournisseur → (affichée, chiffres seuls, compteur éventuel).

    « 41MT417(414141799184) » → ("414141799184", "414141799184", "41MT417")
    « 36 32 15 238 221 » → ("36 32 15 238 221", "363215238221", None)
    """
    if raw is None:
        return "", "", None
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    text = str(raw).strip()
    compteur = None
    m = re.match(r"^\s*([^()]*?)\s*\(\s*([^()]+?)\s*\)\s*$", text)
    if m:
        compteur = m.group(1).strip() or None
        text = m.group(2).strip()
    affichee = re.sub(r"\s+", " ", text).strip()
    return affichee, re.sub(r"\D", "", affichee), compteur


def normaliser_reference(raw) -> str:
    affichee, digits, _ = decouper_reference(raw)
    return digits or re.sub(r"\s+", "", affichee).upper()


def calculer_ttc(
    ht: Decimal | None,
    tva: Decimal | None,
    autres: Decimal | None,
    remise: Decimal | None,
    ttc_saisi: Decimal | None,
) -> Decimal:
    """TTC = HT + TVA + autres taxes − remise quand le HT est connu ; sinon TTC saisi (ou 0)."""
    if ht is None:
        return q2(ttc_saisi) if ttc_saisi is not None else ZERO
    total = Decimal(ht) + Decimal(tva or 0) + Decimal(autres or 0) - Decimal(remise or 0)
    if total < 0:
        raise AppError("Le total de la facture ne peut pas être négatif", code="FACTURE_MONTANT_INVALIDE")
    return q2(total)


def statut_paiement(statut: str, a_payer: Decimal | None, paye: Decimal | None) -> str | None:
    """0 payé → À PAYER ; partiel → PARTIELLEMENT PAYÉE ; total → PAYÉE. Seulement après validation."""
    if statut not in STATUTS_PAYABLES:
        return None
    due = Decimal(a_payer or 0)
    done = Decimal(paye or 0)
    if due <= 0 or done + TOLERANCE >= due:
        return "PAYEE"
    if done <= 0:
        return "A_PAYER"
    return "PARTIELLEMENT_PAYEE"


def etat_echeance(
    date_echeance: date | None,
    statut: str,
    paiement: str | None,
    today: date,
    proche_jours: int,
) -> tuple[str | None, int | None]:
    """(état, jours restants) — EN_RETARD / PROCHE / A_VENIR / SOLDEE."""
    if paiement == "PAYEE":
        return "SOLDEE", None
    if statut not in STATUTS_OUVERTS or date_echeance is None:
        return None, None
    jours = (date_echeance - today).days
    if jours < 0:
        return "EN_RETARD", jours
    if jours <= proche_jours:
        return "PROCHE", jours
    return "A_VENIR", jours


def tranche_echeance(jours: int) -> str:
    if jours < 0:
        return "retard"
    if jours <= 7:
        return "j7"
    if jours <= 30:
        return "j30"
    return "plus30"


def periode_facture(
    periode_debut: date | None, date_facture: date | None, mois: int | None, annee: int | None
) -> tuple[int | None, int | None]:
    """(année, mois) de rattachement : saisi, sinon début de période, sinon date de facture."""
    if mois and annee:
        return annee, mois
    ref = periode_debut or date_facture
    if ref is None:
        return annee, mois
    return annee or ref.year, mois or ref.month


def libelle_periode(annee: int | None, mois: int | None) -> str | None:
    if not annee:
        return None
    if not mois:
        return str(annee)
    return f"{MOIS_LABELS[mois - 1]} {annee}"


def mois_suivant(annee: int, mois: int, pas: int = 1) -> tuple[int, int]:
    total = annee * 12 + (mois - 1) + pas
    return total // 12, total % 12 + 1


def variation_pct(valeur, reference) -> float | None:
    if reference is None or Decimal(reference) == 0 or valeur is None:
        return None
    return round(float((Decimal(valeur) - Decimal(reference)) / Decimal(reference) * 100), 1)


def total_a_payer_auto(ttc, arrieres) -> Decimal:
    """Total à payer non saisi = TTC + arriérés (les arriérés ne sont jamais déduits ni écrasés)."""
    return q2(Decimal(ttc or 0) + Decimal(arrieres or 0))


def a_payer_effectif(f: MgAchatFacture) -> Decimal:
    if f.montant_a_payer is not None:
        return Decimal(f.montant_a_payer)
    return total_a_payer_auto(f.montant_ttc, getattr(f, "arrieres", None))


def etat_champ(champs: dict | None, champ: str) -> str:
    """État d'un champ pour un profil ; champ non configuré (ou pas de profil) = facultatif."""
    etat = (champs or {}).get(champ)
    return etat if etat in ETATS_CHAMP else "facultatif"


def _champ_renseigne(f: MgAchatFacture, champ: str) -> bool:
    if champ == "periode":
        return bool(f.annee and f.mois)
    value = getattr(f, champ, None)
    if champ == "montant_ttc":
        return value is not None and Decimal(value) > 0
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def champs_manquants(f: MgAchatFacture, champs: dict | None) -> list[str]:
    """Champs obligatoires du profil non renseignés (clés de ``CHAMPS_PROFIL``)."""
    return [c for c in CHAMPS_PROFIL if etat_champ(champs, c) == "obligatoire" and not _champ_renseigne(f, c)]


def ecart_tva(ht, tva, taux) -> Decimal | None:
    """Écart TVA saisie − HT × taux. None si le taux n'est pas configuré ou HT / TVA absents."""
    if taux is None or ht is None or tva is None:
        return None
    return q2(Decimal(tva) - Decimal(ht) * Decimal(taux) / Decimal(100))


def tolerance_tva(ht) -> Decimal:
    """Arrondis fournisseurs : 1 MRU ou 0,5 % du HT."""
    return max(Decimal("1"), Decimal(ht or 0) * Decimal("0.005"))


_PAN_RE = re.compile(r"\d(?:[ -]?\d)*")


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def contient_numero_carte(text: str | None) -> bool:
    """Détecte un numéro de carte complet dans un texte libre.

    Une suite de chiffres (espaces / tirets admis) de 13 à 19 chiffres valide Luhn ; une suite plus
    longue (RIB 24 chiffres) n'est pas une carte.
    """
    if not text:
        return False
    for m in _PAN_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            return True
    return False


def masquer_carte(raw: str | None) -> str | None:
    """« 1234 » → « •••• 1234 ». Tout autre format (dont le numéro complet) est refusé, jamais stocké."""
    if raw is None or not str(raw).strip():
        return None
    digits = re.sub(r"[\s•*xX.-]", "", str(raw))
    if not re.fullmatch(r"\d{4}", digits):
        raise AppError(
            "Carte bancaire : saisissez uniquement les 4 derniers chiffres (le numéro complet n'est jamais conservé)",
            code="PAIEMENT_CARTE_INVALIDE",
        )
    return f"•••• {digits}"


def detail_paiement(mode: str, valeurs: dict, observation: str | None = None) -> dict:
    """Colonnes de détail d'un paiement selon son moyen ; champs non applicables vidés.

    Refuse tout numéro de carte complet, quel que soit le champ (observation comprise).
    """
    if mode not in MOYENS_PAIEMENT:
        raise AppError("Moyen de paiement non pris en charge", code="PAIEMENT_MODE_INVALIDE")
    textes = [observation] + [v for v in valeurs.values() if isinstance(v, str)]
    if any(contient_numero_carte(t) for t in textes):
        raise AppError(
            "Numéro de carte bancaire complet détecté : seuls les 4 derniers chiffres sont autorisés",
            code="PAIEMENT_CARTE_INVALIDE",
        )
    attendus = MOYENS_PAIEMENT[mode]
    propres = {k: _clean(valeurs.get(k)) if k in attendus else None for k in CHAMPS_DETAIL_PAIEMENT}
    manquants = [lib for k, (lib, req) in attendus.items() if req and not propres.get(k)]
    if manquants:
        raise AppError(f"{mode} : " + ", ".join(manquants) + " obligatoire(s)", code="PAIEMENT_DETAIL_MANQUANT")
    carte = propres.pop("carte_derniers_chiffres")
    propres["carte_masquee"] = masquer_carte(carte) if carte else None
    return propres


def controles_facture(
    f: MgAchatFacture,
    profil_champs: dict | None,
    taux_tva,
    nb_documents: int,
    fournisseur_actif: bool = True,
) -> list[dict]:
    """Contrôles automatiques. « bloquant » empêche le passage à CONTRÔLÉE ; « attention » informe.

    Aucune règle fiscale n'est supposée : la TVA n'est contrôlée que si le profil porte un taux.
    """
    out: list[dict] = []

    def add(code: str, niveau: str, message: str) -> None:
        out.append({"code": code, "niveau": niveau, "message": message})

    if not fournisseur_actif:
        add("fournisseur_inactif", "bloquant", "Fournisseur inactif ou supprimé")
    manquants = champs_manquants(f, profil_champs)
    if manquants:
        add(
            "champs_obligatoires", "bloquant",
            "Champs obligatoires manquants : " + ", ".join(CHAMPS_PROFIL[c] for c in manquants),
        )
    if a_payer_effectif(f) <= 0:
        add("montant_absent", "bloquant", "Montant à payer nul ou absent")
    if f.periode_debut and f.periode_fin and f.periode_fin < f.periode_debut:
        add("periode_incoherente", "bloquant", "La fin de période précède son début")
    ecart = ecart_tva(f.montant_ht, f.montant_tva, taux_tva)
    if ecart is not None and abs(ecart) > tolerance_tva(f.montant_ht):
        add(
            "tva_incoherente", "attention",
            f"TVA saisie ≠ HT × {Decimal(taux_tva).normalize()} % (écart {ecart})",
        )
    if f.montant_a_payer is not None and f.arrieres:
        attendu = total_a_payer_auto(f.montant_ttc, f.arrieres)
        if abs(Decimal(f.montant_a_payer) - attendu) > TOLERANCE:
            add("total_a_payer", "attention", f"Total à payer ≠ TTC + arriérés ({attendu})")
    if nb_documents == 0:
        add("document_absent", "attention", "Aucune facture scannée jointe")
    if f.date_echeance is None:
        add("echeance_absente", "attention", "Aucune date limite de paiement")
    return out


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _forcer_null(f: MgAchatFacture) -> None:
    """HT / TVA absents restent NULL : sans cela le défaut ORM du circuit Achats (0) s'appliquerait à l'INSERT."""
    for champ in ("montant_ht", "montant_tva"):
        if getattr(f, champ) is None:
            setattr(f, champ, null())


def _detail_paiement(p: MgAchatPaiement) -> dict:
    return {
        "compte": p.compte,
        "banque": p.banque,
        "numero_cheque": p.numero_cheque,
        "carte_masquee": p.carte_masquee,
    }


def _profil_dict(p: MgFacturationProfil, fournisseur: str | None = None) -> dict:
    return {
        "id": str(p.id),
        "code": p.code,
        "libelle": p.libelle,
        "fournisseur_id": str(p.fournisseur_id),
        "fournisseur": fournisseur,
        "type_facture": p.type_facture,
        "taux_tva": to_float(p.taux_tva),
        "champs": {c: etat_champ(p.champs, c) for c in CHAMPS_PROFIL},
        "libelles": {c: (p.libelles or {}).get(c) or lib for c, lib in CHAMPS_PROFIL.items()},
        "description": p.description,
        "actif": p.actif,
        "ordre": p.ordre,
    }


# ——— Périmètre et capacités ———


async def agence_scope(db: AsyncSession, user: User) -> uuid.UUID | None:
    """Lecteur rattaché à une agence : ne voit que les factures de son agence."""
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
        "view": ok("mg.factures.view"),
        "create": ok("mg.factures.create"),
        "update": ok("mg.factures.update"),
        "delete": ok("mg.factures.delete"),
        "validate": ok("mg.factures.validate"),
        "archive": ok("mg.factures.archive"),
        "export": ok("mg.factures.export"),
        "payment_view": ok("mg.factures.payment.view"),
        "payment_create": ok("mg.factures.payment.create"),
        "payment_update": ok("mg.factures.payment.update"),
        "payment_delete": ok("mg.factures.payment.delete"),
        "documents_view": ok("mg.factures.documents.view"),
        "documents_create": ok("mg.factures.documents.create"),
        "documents_delete": ok("mg.factures.documents.delete"),
        "analytics": ok("mg.factures.analytics.view"),
        "reports": ok("mg.factures.reports.export"),
        "manage": ok("mg.facturation.manage"),
    }


CAPACITE_ACTION = {
    "enregistrer": "update",
    "controler": "update",
    "valider_controle": "update",
    "valider": "validate",
    "contester": "validate",
    "annuler": "delete",
    "archiver": "archive",
}


def actions_possibles(f: MgAchatFacture, caps: dict[str, bool], nb_paiements_actifs: int) -> list[str]:
    """Actions de workflow disponibles pour la fiche (le backend revérifie à l'exécution)."""
    out: list[str] = []
    for action, (sources, _cible) in TRANSITIONS.items():
        if f.statut not in sources or not caps.get(CAPACITE_ACTION[action]):
            continue
        if action in {"contester", "annuler"} and nb_paiements_actifs:
            continue
        if action == "archiver" and f.statut == "VALIDEE" and f.statut_paiement != "PAYEE":
            continue
        out.append(action)
    return out


class MgFacturationService:
    def __init__(self, db: AsyncSession, scope_agence: uuid.UUID | None = None):
        self.db = db
        self.scope_agence = scope_agence

    @classmethod
    async def for_user(cls, db: AsyncSession, user: User) -> "MgFacturationService":
        return cls(db, scope_agence=await agence_scope(db, user))

    # ——— Paramètres ———

    async def ensure_defaults(self) -> None:
        existing = set(
            (
                await self.db.execute(
                    select(MgContratParametre.cle).where(MgContratParametre.cle.like("factures.%"))
                )
            ).scalars().all()
        )
        missing = [p for p in DEFAULT_PARAMS if p[0] not in existing]
        if not missing:
            return
        for cle, valeur, libelle in missing:
            self.db.add(MgContratParametre(cle=cle, valeur=valeur, libelle=libelle))
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()

    async def _param(self, cle: str, default: str) -> str:
        row = await self.db.scalar(select(MgContratParametre).where(MgContratParametre.cle == cle))
        return row.valeur if row and row.valeur != "" else default

    async def _param_int(self, cle: str, default: int) -> int:
        try:
            return int(Decimal(await self._param(cle, str(default))))
        except (ArithmeticError, ValueError):
            return default

    async def seuils(self) -> dict[str, int]:
        return {
            "delai_paiement_jours": await self._param_int("factures.delai_paiement_jours", 0),
            "alerte_echeance_jours": await self._param_int("factures.alerte_echeance_jours", 7),
            "seuil_hausse_pct": await self._param_int("factures.seuil_hausse_pct", 30),
            "delai_reception_jours": await self._param_int("factures.delai_reception_jours", 5),
        }

    async def list_params(self) -> list[MgContratParametre]:
        await self.ensure_defaults()
        stmt = select(MgContratParametre).where(MgContratParametre.cle.like("factures.%"))
        return list((await self.db.execute(stmt.order_by(MgContratParametre.cle))).scalars().all())

    async def set_param(self, cle: str, valeur: str, user: User) -> MgContratParametre:
        if cle not in {p[0] for p in DEFAULT_PARAMS}:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paramètre introuvable")
        await self.ensure_defaults()
        row = await self.db.scalar(select(MgContratParametre).where(MgContratParametre.cle == cle))
        value = (valeur or "").strip()
        if cle in PARAMS_NUMERIQUES:
            try:
                if Decimal(value) < 0:
                    raise ValueError
            except (ArithmeticError, ValueError):
                raise AppError("Valeur numérique positive attendue", code="PARAMETRE_INVALIDE")
        elif not re.fullmatch(r"[A-Za-z0-9]{1,10}", value):
            raise AppError("Préfixe : 1 à 10 lettres ou chiffres", code="PARAMETRE_INVALIDE")
        before = row.valeur
        row.valeur = value.upper() if cle not in PARAMS_NUMERIQUES else value
        await self._audit(user, "factures.parametre", None, before={cle: before}, after={cle: row.valeur}, entity="parametre")
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def config(self, user: User) -> dict:
        await self.ensure_defaults()
        scope = None
        if self.scope_agence:
            ag = await self.db.get(Agence, self.scope_agence)
            scope = {"id": str(self.scope_agence), "libelle": ag.libelle if ag else None}
        return {
            "statuts": [{"code": c, "libelle": STATUT_LABELS[c]} for c in STATUTS],
            "statuts_paiement": [{"code": c, "libelle": STATUT_PAIEMENT_LABELS[c]} for c in STATUTS_PAIEMENT],
            "types_point": [{"code": c, "libelle": TYPE_POINT_LABELS[c]} for c in TYPES_POINT],
            "types_facture": [{"code": c, "libelle": l} for c, l in TYPES_FACTURE],
            "types_document": [{"code": c, "libelle": l} for c, l in TYPES_DOCUMENT],
            "periodicites": list(PERIODICITES_POINT.keys()),
            "modes_paiement": MODES_PAIEMENT,
            "moyens_paiement": {
                mode: [{"champ": k, "libelle": lib, "obligatoire": req} for k, (lib, req) in champs.items()]
                for mode, champs in MOYENS_PAIEMENT.items()
            },
            "champs_profil": [{"code": k, "libelle": v} for k, v in CHAMPS_PROFIL.items()],
            "profils": await self.list_profils(actifs=False),
            "devises": DEVISES,
            "devise": "MRU",
            "mois": MOIS_LABELS,
            "seuils": await self.seuils(),
            "ged_taille_max_mo": await self._param_int("contrats.ged_taille_max_mo", 15),
            "capacites": await capacites(self.db, user),
            "agence_scope": scope,
        }

    # ——— Outils internes ———

    async def _audit(self, user: User, action: str, entity_id, *, before=None, after=None, entity: str = "facture") -> None:
        await record_audit(
            self.db,
            user=user,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id else None,
            before=before,
            after=after,
            espace_code=ESPACE,
            module_code=MODULE,
        )

    def _event(self, entity_type: str, entity_id: uuid.UUID, action: str, message: str, user: User | None) -> None:
        self.db.add(
            MgAchatEvenement(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                message=message[:4000],
                user_id=user.id if user else None,
            )
        )

    async def _sequence(self, model, column, prefix: str, width: int) -> str:
        like = f"{prefix}-%"
        last = await self.db.scalar(
            select(column).select_from(model).where(column.like(like)).order_by(func.length(column).desc(), column.desc()).limit(1)
        )
        n = 0
        if last:
            m = re.search(r"(\d+)$", last)
            n = int(m.group(1)) if m else 0
        return f"{prefix}-{n + 1:0{width}d}"

    async def _next_reference(self) -> str:
        prefix = (await self._param("factures.prefixe", "FACT")).upper()
        return await self._sequence(MgAchatFacture, MgAchatFacture.reference, f"{prefix}-{date.today().year}", 5)

    async def _next_paiement_ref(self) -> str:
        return await self._sequence(MgAchatPaiement, MgAchatPaiement.reference, f"RGF-{date.today().year}", 5)

    async def _next_point_code(self) -> str:
        prefix = (await self._param("factures.prefixe_point", "PF")).upper()
        return await self._sequence(MgPointFacturation, MgPointFacturation.code, prefix, 5)

    async def _fournisseur(self, fournisseur_id) -> Fournisseur:
        fr = await self.db.get(Fournisseur, fournisseur_id)
        if not fr or fr.deleted_at is not None:
            raise AppError("Fournisseur introuvable", code="REFERENCE_INTROUVABLE")
        return fr

    async def _agence(self, agence_id) -> Agence:
        ag = await self.db.get(Agence, agence_id)
        if not ag or ag.deleted_at is not None:
            raise AppError("Agence introuvable", code="REFERENCE_INTROUVABLE")
        if self.scope_agence and ag.id != self.scope_agence:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Agence hors de votre périmètre")
        return ag

    async def _contrat(self, contrat_id) -> MgContrat:
        ct = await self.db.get(MgContrat, contrat_id)
        if not ct or ct.deleted_at is not None:
            raise AppError("Contrat introuvable", code="REFERENCE_INTROUVABLE")
        return ct

    async def _profil(self, profil_id, *, actif: bool = True) -> MgFacturationProfil:
        profil = await self.db.get(MgFacturationProfil, profil_id)
        if not profil:
            raise AppError("Profil de facturation introuvable", code="REFERENCE_INTROUVABLE")
        if actif and not profil.actif:
            raise AppError("Profil de facturation inactif", code="PROFIL_INACTIF")
        return profil

    async def _profil_champs(self, f: MgAchatFacture) -> tuple[dict | None, Decimal | None]:
        if not f.profil_id:
            return None, None
        profil = await self.db.get(MgFacturationProfil, f.profil_id)
        return (profil.champs, profil.taux_tva) if profil else (None, None)

    async def _exiger_champs(self, f: MgAchatFacture) -> None:
        """Champs obligatoires du profil : exigés dès que la facture quitte le brouillon."""
        if f.statut == "BROUILLON":
            return
        champs, _taux = await self._profil_champs(f)
        manquants = champs_manquants(f, champs)
        if manquants:
            raise AppError(
                "Champs obligatoires pour ce fournisseur : " + ", ".join(CHAMPS_PROFIL[c] for c in manquants),
                code="FACTURE_CHAMPS_OBLIGATOIRES",
            )

    async def _point(self, point_id, *, lock: bool = False) -> MgPointFacturation:
        stmt = select(MgPointFacturation).where(
            MgPointFacturation.id == point_id, MgPointFacturation.deleted_at.is_(None)
        )
        if lock:
            stmt = stmt.with_for_update()
        point = await self.db.scalar(stmt)
        if not point or (self.scope_agence and point.agence_id != self.scope_agence):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Point de facturation introuvable")
        return point

    async def _facture(self, facture_id, *, lock: bool = False) -> MgAchatFacture:
        stmt = (
            select(MgAchatFacture)
            .options(selectinload(MgAchatFacture.lignes))
            .where(
                MgAchatFacture.id == facture_id,
                MgAchatFacture.origine == ORIGINE_FACTURATION,
                MgAchatFacture.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update()
        f = await self.db.scalar(stmt)
        if not f or (self.scope_agence and f.agence_id != self.scope_agence):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
        return f

    async def _paiements_actifs(self, facture_id) -> list[MgAchatPaiement]:
        rows = await self.db.execute(
            select(MgAchatPaiement)
            .where(
                MgAchatPaiement.facture_id == facture_id,
                MgAchatPaiement.origine == ORIGINE_FACTURATION,
                MgAchatPaiement.deleted_at.is_(None),
                MgAchatPaiement.statut == "PAYE",
            )
            .order_by(MgAchatPaiement.date_paiement, MgAchatPaiement.created_at)
        )
        return list(rows.scalars().all())

    async def _recalculer_paiements(self, f: MgAchatFacture) -> None:
        await self.db.flush()
        paye = sum((Decimal(p.montant) for p in await self._paiements_actifs(f.id)), ZERO)
        f.montant_paye = q2(paye)
        f.statut_paiement = statut_paiement(f.statut, a_payer_effectif(f), paye)

    def _snapshot(self, f: MgAchatFacture) -> dict:
        return {k: _json_value(getattr(f, k)) for k in CHAMPS_LABELS if hasattr(f, k)} | {
            "statut": f.statut,
            "statut_paiement": f.statut_paiement,
            "montant_paye": _json_value(f.montant_paye),
        }

    # ——— Lecture : sélection, filtres, sérialisation ———

    def _select(self, *columns):
        P = MgPointFacturation
        return (
            select(*(columns or (MgAchatFacture, P, Fournisseur.raison_sociale, Agence.libelle, MgFacturationProfil.libelle)))
            .select_from(MgAchatFacture)
            .outerjoin(P, P.id == MgAchatFacture.point_facturation_id)
            .outerjoin(Fournisseur, Fournisseur.id == MgAchatFacture.fournisseur_id)
            .outerjoin(Agence, Agence.id == MgAchatFacture.agence_id)
            .outerjoin(MgFacturationProfil, MgFacturationProfil.id == MgAchatFacture.profil_id)
            .where(MgAchatFacture.origine == ORIGINE_FACTURATION, MgAchatFacture.deleted_at.is_(None))
        )

    def _apply_filters(self, stmt, filtres: dict, today: date):
        F = MgAchatFacture
        P = MgPointFacturation
        if self.scope_agence:
            stmt = stmt.where(F.agence_id == self.scope_agence)
        vue = (filtres.get("vue") or "").strip().lower()
        ouvert_non_paye = and_(F.statut.in_(STATUTS_OUVERTS), or_(F.statut_paiement.is_(None), F.statut_paiement != "PAYEE"))
        if vue == "agences":
            stmt = stmt.where(P.type_point.in_(("AGENCE", "SIEGE")))
        elif vue == "pdv":
            stmt = stmt.where(P.type_point == "PDV")
        elif vue == "a_controler":
            stmt = stmt.where(F.statut.in_(("RECUE", "A_CONTROLER")))
        elif vue == "a_payer":
            stmt = stmt.where(F.statut == "VALIDEE", F.statut_paiement.in_(("A_PAYER", "PARTIELLEMENT_PAYEE")))
        elif vue == "payees":
            stmt = stmt.where(F.statut_paiement == "PAYEE")
        elif vue == "retard":
            stmt = stmt.where(ouvert_non_paye, F.date_echeance < today)
        elif vue == "historique":
            stmt = stmt.where(F.statut.in_(("ANNULEE", "ARCHIVEE")))
        elif vue == "brouillons":
            stmt = stmt.where(F.statut == "BROUILLON")
        elif vue in {"", "toutes"}:
            if not filtres.get("statut") and not filtres.get("inclure_historique"):
                stmt = stmt.where(F.statut != "ARCHIVEE")

        echeance = (filtres.get("echeance") or "").strip().lower()
        if echeance == "sans":
            stmt = stmt.where(ouvert_non_paye, F.date_echeance.is_(None))
        elif echeance:
            stmt = stmt.where(ouvert_non_paye, F.date_echeance.is_not(None))
            if echeance == "retard":
                stmt = stmt.where(F.date_echeance < today)
            elif echeance == "j7":
                stmt = stmt.where(F.date_echeance >= today, F.date_echeance <= today + timedelta(days=7))
            elif echeance == "j30":
                stmt = stmt.where(F.date_echeance > today + timedelta(days=7), F.date_echeance <= today + timedelta(days=30))
            elif echeance == "plus30":
                stmt = stmt.where(F.date_echeance > today + timedelta(days=30))

        if filtres.get("statut"):
            codes = [s.strip().upper() for s in str(filtres["statut"]).split(",") if s.strip()]
            stmt = stmt.where(F.statut.in_(codes))
        if filtres.get("statut_paiement"):
            stmt = stmt.where(F.statut_paiement == str(filtres["statut_paiement"]).upper())
        if filtres.get("annee"):
            stmt = stmt.where(F.annee == int(filtres["annee"]))
        if filtres.get("mois"):
            stmt = stmt.where(F.mois == int(filtres["mois"]))
        if filtres.get("date_from"):
            stmt = stmt.where(F.date_facture >= filtres["date_from"])
        if filtres.get("date_to"):
            stmt = stmt.where(F.date_facture <= filtres["date_to"])
        if filtres.get("fournisseur_id"):
            stmt = stmt.where(F.fournisseur_id == filtres["fournisseur_id"])
        if filtres.get("profil_id"):
            stmt = stmt.where(F.profil_id == filtres["profil_id"])
        if filtres.get("agence_id"):
            stmt = stmt.where(F.agence_id == filtres["agence_id"])
        if filtres.get("point_id"):
            stmt = stmt.where(F.point_facturation_id == filtres["point_id"])
        if filtres.get("contrat_id"):
            stmt = stmt.where(F.contrat_id == filtres["contrat_id"])
        if filtres.get("type_point"):
            stmt = stmt.where(P.type_point == str(filtres["type_point"]).upper())
        if filtres.get("type_facture"):
            stmt = stmt.where(F.type_facture == str(filtres["type_facture"]).upper())

        q = (filtres.get("q") or "").strip()
        if q:
            stmt = stmt.where(or_(*self._search_conditions(q)))
        return stmt

    def _search_conditions(self, q: str) -> list:
        F = MgAchatFacture
        P = MgPointFacturation
        like = f"%{q}%"
        conds = [
            F.reference.ilike(like),
            F.numero_fournisseur.ilike(like),
            F.reference_fournisseur.ilike(like),
            F.observation.ilike(like),
            P.nom.ilike(like),
            P.code.ilike(like),
            P.compteur.ilike(like),
            Fournisseur.raison_sociale.ilike(like),
            Agence.libelle.ilike(like),
            MgFacturationProfil.libelle.ilike(like),
        ]
        digits = re.sub(r"\D", "", q)
        if len(digits) >= 4:
            conds.append(P.reference_normalisee.contains(digits))
            conds.append(func.regexp_replace(func.coalesce(F.reference_fournisseur, ""), r"\D", "", "g").contains(digits))
        if re.fullmatch(r"(19|20)\d{2}", q):
            conds.append(F.annee == int(q))
        try:
            amount = Decimal(q.replace(" ", "").replace("\u202f", "").replace(",", "."))
            if amount > 0 and re.fullmatch(r"[\d\s.,\u202f]+", q):
                conds.append(F.montant_ttc == amount)
                conds.append(F.montant_a_payer == amount)
        except (InvalidOperation, ValueError):
            pass
        norm = sans_accents(q)
        for idx, label in enumerate(MOIS_LABELS, start=1):
            if norm and sans_accents(label).startswith(norm) and len(norm) >= 3:
                conds.append(F.mois == idx)
        for code, label in STATUT_LABELS.items():
            if len(norm) >= 4 and norm in sans_accents(label):
                conds.append(F.statut == code)
        for code, label in STATUT_PAIEMENT_LABELS.items():
            if len(norm) >= 4 and norm in sans_accents(label):
                conds.append(F.statut_paiement == code)
        return conds

    def _row(
        self,
        f: MgAchatFacture,
        point: MgPointFacturation | None,
        fournisseur: str | None,
        agence: str | None,
        today: date,
        proche: int,
        nb_documents: int | None = None,
        *,
        profil: str | None = None,
    ) -> dict:
        a_payer = a_payer_effectif(f)
        paye = Decimal(f.montant_paye or 0)
        etat, jours = etat_echeance(f.date_echeance, f.statut, f.statut_paiement, today, proche)
        reste = max(a_payer - paye, ZERO) if f.statut in STATUTS_COMPTES else ZERO
        affiche = f.statut
        if etat == "EN_RETARD":
            affiche = "EN_RETARD"
        elif f.statut == "VALIDEE" and f.statut_paiement:
            affiche = f.statut_paiement
        return {
            "id": str(f.id),
            "reference": f.reference,
            "numero_fournisseur": f.numero_fournisseur,
            "fournisseur_id": str(f.fournisseur_id) if f.fournisseur_id else None,
            "fournisseur": fournisseur,
            "profil_id": str(f.profil_id) if f.profil_id else None,
            "profil": profil,
            "point_facturation_id": str(f.point_facturation_id) if f.point_facturation_id else None,
            "point_code": point.code if point else None,
            "point_nom": point.nom if point else None,
            "type_point": point.type_point if point else None,
            "agence_id": str(f.agence_id) if f.agence_id else None,
            "agence": agence,
            "contrat_id": str(f.contrat_id) if f.contrat_id else None,
            "type_facture": f.type_facture,
            "reference_fournisseur": f.reference_fournisseur,
            "date_facture": _iso(f.date_facture),
            "date_reception": _iso(f.date_reception),
            "periode_debut": _iso(f.periode_debut),
            "periode_fin": _iso(f.periode_fin),
            "mois": f.mois,
            "annee": f.annee,
            "periode_label": libelle_periode(f.annee, f.mois),
            "date_echeance": _iso(f.date_echeance),
            "jours_echeance": jours,
            "etat_echeance": etat,
            "montant_ht": to_float(f.montant_ht),
            "montant_tva": to_float(f.montant_tva),
            "autres_taxes": to_float(f.autres_taxes),
            "remise": to_float(f.remise),
            "montant_ttc": to_float(f.montant_ttc),
            "arrieres": to_float(f.arrieres),
            "reglage": to_float(f.reglage),
            "montant_a_payer": to_float(a_payer),
            "montant_paye": to_float(paye),
            "reste": to_float(reste),
            "devise": f.devise,
            "statut": f.statut,
            "statut_paiement": f.statut_paiement,
            "statut_affiche": affiche,
            "observation": f.observation,
            "nb_documents": nb_documents,
            "created_at": _iso(f.created_at),
            "updated_at": _iso(f.updated_at),
        }

    async def _nb_documents(self, ids: list[uuid.UUID]) -> dict[str, int]:
        if not ids:
            return {}
        rows = await self.db.execute(
            select(GedDocument.entity_id, func.count())
            .where(
                GedDocument.module_code == MODULE,
                GedDocument.entity == GED_ENTITY,
                GedDocument.entity_id.in_([str(i) for i in ids]),
                GedDocument.deleted_at.is_(None),
            )
            .group_by(GedDocument.entity_id)
        )
        return {eid: int(n) for eid, n in rows.all()}

    async def fetch_rows(self, filtres: dict, *, limit: int | None = None, order=None) -> list[dict]:
        """Lignes sérialisées (sans pagination) — utilisé par analyses, alertes et rapports."""
        today = date.today()
        proche = await self._param_int("factures.alerte_echeance_jours", 7)
        stmt = self._apply_filters(self._select(), filtres, today)
        stmt = stmt.order_by(*(order or [MgAchatFacture.date_facture.desc(), MgAchatFacture.reference.desc()]))
        if limit:
            stmt = stmt.limit(limit)
        rows = (await self.db.execute(stmt)).all()
        return [self._row(f, p, fr, ag, today, proche, profil=pr) for f, p, fr, ag, pr in rows]

    SORTS = {
        "date_facture": MgAchatFacture.date_facture,
        "reference": MgAchatFacture.reference,
        "periode": MgAchatFacture.annee * 100 + func.coalesce(MgAchatFacture.mois, 0),
        "montant": MgAchatFacture.montant_ttc,
        "echeance": MgAchatFacture.date_echeance,
        "statut": MgAchatFacture.statut,
        "fournisseur": Fournisseur.raison_sociale,
        "agence": Agence.libelle,
    }

    async def list_factures(self, filtres: dict, *, page: int = 1, page_size: int = 25, sort: str | None = None) -> dict:
        today = date.today()
        proche = await self._param_int("factures.alerte_echeance_jours", 7)
        base = self._apply_filters(self._select(), filtres, today)
        sub = self._apply_filters(
            self._select(
                MgAchatFacture.id, MgAchatFacture.montant_ttc, MgAchatFacture.montant_a_payer,
                MgAchatFacture.montant_paye, MgAchatFacture.statut,
            ),
            filtres,
            today,
        ).subquery()
        totals = (
            await self.db.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(sub.c.montant_ttc).filter(sub.c.statut.in_(STATUTS_COMPTES)), 0),
                    func.coalesce(
                        func.sum(func.coalesce(sub.c.montant_a_payer, sub.c.montant_ttc) - sub.c.montant_paye).filter(
                            sub.c.statut.in_(STATUTS_COMPTES)
                        ),
                        0,
                    ),
                )
            )
        ).one()
        key = (sort or "-date_facture").strip()
        desc = key.startswith("-")
        col = self.SORTS.get(key.lstrip("-"), MgAchatFacture.date_facture)
        order = [col.desc().nulls_last() if desc else col.asc().nulls_last(), MgAchatFacture.reference.desc()]
        size = max(1, min(int(page_size or 25), 200))
        current = max(1, int(page or 1))
        rows = (await self.db.execute(base.order_by(*order).offset((current - 1) * size).limit(size))).all()
        docs = await self._nb_documents([r[0].id for r in rows])
        items = [self._row(f, p, fr, ag, today, proche, docs.get(str(f.id), 0), profil=pr) for f, p, fr, ag, pr in rows]
        return {
            "items": items,
            "total": int(totals[0] or 0),
            "page": current,
            "page_size": size,
            "montant_total": float(totals[1] or 0),
            "reste_total": float(max(Decimal(totals[2] or 0), ZERO)),
        }

    async def compteurs_vues(self) -> dict[str, int]:
        today = date.today()
        out: dict[str, int] = {}
        for vue in ("toutes", "agences", "pdv", "a_controler", "a_payer", "payees", "retard", "historique"):
            stmt = self._apply_filters(self._select(func.count(MgAchatFacture.id)), {"vue": vue}, today)
            out[vue] = int(await self.db.scalar(stmt) or 0)
        return out

    async def _historique(self, entity_type: str, entity_id: uuid.UUID) -> list[dict]:
        rows = await self.db.execute(
            select(MgAchatEvenement, User.full_name)
            .outerjoin(User, User.id == MgAchatEvenement.user_id)
            .where(MgAchatEvenement.entity_type == entity_type, MgAchatEvenement.entity_id == entity_id)
            .order_by(MgAchatEvenement.created_at.desc())
            .limit(300)
        )
        return [
            {
                "id": str(e.id),
                "action": e.action,
                "message": e.message,
                "user_nom": nom,
                "created_at": _iso(e.created_at),
            }
            for e, nom in rows.all()
        ]

    def _doc_dict(self, d: GedDocument, auteurs: dict) -> dict:
        return {
            "id": str(d.id),
            "title": d.title or d.filename,
            "filename": d.filename,
            "mime_type": d.mime_type,
            "size_bytes": d.size_bytes,
            "doc_type": d.doc_type,
            "doc_type_label": dict(TYPES_DOCUMENT).get(d.doc_type or "", d.doc_type),
            "reference": d.reference,
            "date_document": _iso(d.date_document),
            "uploaded_by": auteurs.get(d.uploaded_by_id),
            "created_at": _iso(d.created_at),
        }

    async def list_documents(self, facture_id: uuid.UUID) -> list[dict]:
        f = await self._facture(facture_id)
        rows = (
            await self.db.execute(
                select(GedDocument)
                .where(
                    GedDocument.module_code == MODULE,
                    GedDocument.entity == GED_ENTITY,
                    GedDocument.entity_id == str(f.id),
                    GedDocument.deleted_at.is_(None),
                )
                .order_by(GedDocument.created_at.desc())
            )
        ).scalars().all()
        ids = {d.uploaded_by_id for d in rows if d.uploaded_by_id}
        auteurs = {}
        if ids:
            auteurs = dict((await self.db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all())
        return [self._doc_dict(d, auteurs) for d in rows]

    async def _paiements_dicts(self, facture_id: uuid.UUID) -> list[dict]:
        rows = await self.db.execute(
            select(MgAchatPaiement, User.full_name)
            .outerjoin(User, User.id == MgAchatPaiement.created_by)
            .where(
                MgAchatPaiement.facture_id == facture_id,
                MgAchatPaiement.origine == ORIGINE_FACTURATION,
                MgAchatPaiement.deleted_at.is_(None),
            )
            .order_by(MgAchatPaiement.date_paiement.desc(), MgAchatPaiement.created_at.desc())
        )
        return [
            {
                "id": str(p.id),
                "reference": p.reference,
                "date_paiement": _iso(p.date_paiement),
                "montant": to_float(p.montant),
                "mode_paiement": p.mode_paiement,
                "reference_paiement": p.reference_paiement,
                **_detail_paiement(p),
                "observation": p.observation,
                "statut": p.statut,
                "justificatif_document_id": str(p.justificatif_document_id) if p.justificatif_document_id else None,
                "created_by": nom,
                "created_at": _iso(p.created_at),
                "annule_at": _iso(p.annule_at),
            }
            for p, nom in rows.all()
        ]

    async def get_facture(self, facture_id: uuid.UUID, user: User) -> dict:
        today = date.today()
        proche = await self._param_int("factures.alerte_echeance_jours", 7)
        row = (
            await self.db.execute(
                self._select().where(MgAchatFacture.id == facture_id).options(selectinload(MgAchatFacture.lignes))
            )
        ).first()
        if not row or (self.scope_agence and row[0].agence_id != self.scope_agence):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
        f, point, fournisseur, agence, profil_libelle = row
        caps = await capacites(self.db, user)
        paiements = await self._paiements_dicts(f.id) if caps["payment_view"] else []
        documents = await self.list_documents(f.id) if caps["documents_view"] else []
        nb_actifs = sum(1 for p in paiements if p["statut"] == "PAYE") if caps["payment_view"] else len(
            await self._paiements_actifs(f.id)
        )
        nb_docs = len(documents) if caps["documents_view"] else (await self._nb_documents([f.id])).get(str(f.id), 0)
        data = self._row(f, point, fournisseur, agence, today, proche, nb_docs, profil=profil_libelle)
        contrat = await self.db.get(MgContrat, f.contrat_id) if f.contrat_id else None
        createur = await self.db.get(User, f.created_by) if f.created_by else None
        valideur = await self.db.get(User, f.valide_by) if f.valide_by else None
        controleur = await self.db.get(User, f.controle_by) if f.controle_by else None
        profil = await self.db.get(MgFacturationProfil, f.profil_id) if f.profil_id else None
        fr = await self.db.get(Fournisseur, f.fournisseur_id) if f.fournisseur_id else None
        data.update(
            {
                "profil_config": _profil_dict(profil, fournisseur) if profil else None,
                "controles": controles_facture(
                    f, profil.champs if profil else None, profil.taux_tva if profil else None, nb_docs,
                    fournisseur_actif=bool(fr and fr.deleted_at is None and fr.is_active),
                ),
                "controle_at": _iso(f.controle_at),
                "controle_by_nom": controleur.full_name if controleur else None,
                "lignes": [
                    {
                        "id": str(l.id),
                        "description": l.designation,
                        "quantite": to_float(l.quantite),
                        "unite": l.unite,
                        "prix_unitaire": to_float(l.prix_unitaire),
                        "montant": to_float(l.total_ht),
                        "type_ligne": l.type_ligne,
                    }
                    for l in sorted(f.lignes, key=lambda x: x.sort_order)
                ],
                "paiements": paiements,
                "documents": documents,
                "historique": await self._historique(EVT_FACTURE, f.id),
                "point": (
                    {
                        "id": str(point.id),
                        "code": point.code,
                        "nom": point.nom,
                        "type_point": point.type_point,
                        "reference_fournisseur": point.reference_fournisseur,
                        "compteur": point.compteur,
                        "periodicite": point.periodicite,
                        "statut": point.statut,
                    }
                    if point
                    else None
                ),
                "contrat": (
                    {"id": str(contrat.id), "reference": contrat.reference, "titre": contrat.titre, "statut": contrat.statut}
                    if contrat
                    else None
                ),
                "created_by_nom": createur.full_name if createur else None,
                "valide_at": _iso(f.valide_at),
                "valide_by_nom": valideur.full_name if valideur else None,
                "motif": f.motif_validation,
                "annule_at": _iso(f.annule_at),
                "archived_at": _iso(f.archived_at),
                "actions": actions_possibles(f, caps, nb_actifs),
                "modifiable": f.statut not in VERROUILLES and caps["update"],
                "montants_modifiables": f.statut in {"BROUILLON", "RECUE", "A_CONTROLER", "CONTROLEE", "CONTESTEE"}
                and caps["update"],
                "supprimable": f.statut in {"BROUILLON", "RECUE"} and nb_actifs == 0 and caps["delete"],
                "capacites": caps,
            }
        )
        return data

    # ——— Écriture : création, modification ———

    async def _appliquer(self, f: MgAchatFacture, data, champs: set[str], point: MgPointFacturation | None) -> None:
        simples = (
            "numero_fournisseur", "type_facture", "reference_fournisseur", "date_facture", "date_reception",
            "periode_debut", "periode_fin", "date_echeance", "observation",
        )
        for champ in simples:
            if champ in champs:
                value = getattr(data, champ)
                if isinstance(value, str):
                    value = _clean(value)
                    if champ == "type_facture" and value:
                        value = value.upper()
                setattr(f, champ, value)
        if "devise" in champs:
            devise = (_clean(data.devise) or "MRU").upper()
            if devise not in DEVISES:
                raise AppError("Devise non prise en charge", code="DEVISE_INVALIDE")
            f.devise = devise
        if point is not None:
            if not f.reference_fournisseur:
                f.reference_fournisseur = point.reference_fournisseur
            if not f.type_facture:
                f.type_facture = point.type_facture
        if f.date_facture is None:
            raise AppError("Date de facture obligatoire", code="CHAMP_OBLIGATOIRE")
        if f.periode_debut and f.periode_fin and f.periode_fin < f.periode_debut:
            raise AppError("La fin de période précède son début", code="FACTURE_PERIODE_INVALIDE")
        if f.date_echeance and f.date_echeance < f.date_facture:
            raise AppError("L'échéance ne peut pas précéder la date de facture", code="FACTURE_ECHEANCE_INVALIDE")

        mois = data.mois if "mois" in champs else f.mois
        annee = data.annee if "annee" in champs else f.annee
        if {"periode_debut", "date_facture"} & champs and not ({"mois", "annee"} & champs):
            mois, annee = None, None
        f.annee, f.mois = periode_facture(f.periode_debut, f.date_facture, mois, annee)

        # Montants : jamais inventés — seuls les montants saisis ou la somme des lignes saisies.
        if "lignes" in champs and data.lignes is not None:
            f.lignes.clear()
            total_lignes = ZERO
            for idx, ligne in enumerate(data.lignes):
                montant = ligne.montant
                if montant is None and ligne.quantite is not None and ligne.prix_unitaire is not None:
                    montant = Decimal(ligne.quantite) * Decimal(ligne.prix_unitaire)
                montant = q2(montant or 0)
                total_lignes += montant
                f.lignes.append(
                    MgAchatFactureLigne(
                        designation=ligne.description.strip()[:255],
                        quantite=ligne.quantite if ligne.quantite is not None else Decimal("1"),
                        unite=_clean(ligne.unite),
                        type_ligne=_clean(ligne.type_ligne),
                        prix_unitaire=q2(ligne.prix_unitaire) if ligne.prix_unitaire is not None else montant,
                        taux_tva=ZERO,
                        total_ht=montant,
                        montant_tva=ZERO,
                        total_ttc=montant,
                        sort_order=idx,
                    )
                )
            if data.lignes and "montant_ht" not in champs:
                f.montant_ht = q2(total_lignes)

        ancien_auto = total_a_payer_auto(f.montant_ttc, f.arrieres)
        ancien_a_payer = f.montant_a_payer
        for champ in ("arrieres", "reglage"):
            if champ in champs:
                setattr(f, champ, q2(getattr(data, champ)))
        for champ in ("montant_ht", "montant_tva", "autres_taxes", "remise"):
            if champ in champs:
                value = getattr(data, champ)
                if champ in {"autres_taxes", "remise"}:
                    value = value if value is not None else ZERO
                setattr(f, champ, q2(value))
        ttc_saisi = data.montant_ttc if "montant_ttc" in champs else (f.montant_ttc if f.montant_ht is None else None)
        f.montant_ttc = calculer_ttc(f.montant_ht, f.montant_tva, f.autres_taxes, f.remise, ttc_saisi)
        if "montant_ttc" in champs and data.montant_ttc is not None and f.montant_ht is not None:
            if abs(Decimal(data.montant_ttc) - f.montant_ttc) > TOLERANCE:
                raise AppError(
                    "Montant TTC incohérent avec HT + TVA + autres taxes − remise",
                    code="FACTURE_MONTANT_INCOHERENT",
                )
        # Total à payer : saisi tel quel, sinon TTC + arriérés (suit le TTC tant qu'il n'a pas été forcé).
        auto = total_a_payer_auto(f.montant_ttc, f.arrieres)
        if "montant_a_payer" in champs and data.montant_a_payer is not None:
            f.montant_a_payer = q2(data.montant_a_payer)
        elif "montant_a_payer" in champs or ancien_a_payer is None or Decimal(ancien_a_payer) == ancien_auto:
            f.montant_a_payer = auto if auto > 0 else None

        if f.date_echeance is None and "date_echeance" not in champs:
            delai = await self._param_int("factures.delai_paiement_jours", 0)
            if delai > 0:
                f.date_echeance = f.date_facture + timedelta(days=delai)

    async def _check_doublons(self, f: MgAchatFacture, forcer: bool) -> None:
        if f.numero_fournisseur:
            existing = await self.db.scalar(
                select(MgAchatFacture.reference).where(
                    MgAchatFacture.id != f.id,
                    MgAchatFacture.fournisseur_id == f.fournisseur_id,
                    func.lower(func.trim(MgAchatFacture.numero_fournisseur)) == f.numero_fournisseur.strip().lower(),
                    MgAchatFacture.deleted_at.is_(None),
                    MgAchatFacture.statut != "ANNULEE",
                )
            )
            if existing:
                raise AppError(
                    f"La facture n° {f.numero_fournisseur} de ce fournisseur est déjà enregistrée ({existing})",
                    status_code=409,
                    code="FACTURE_DOUBLON",
                )
        if f.point_facturation_id and f.annee and f.mois and not forcer:
            existing = await self.db.scalar(
                select(MgAchatFacture.reference).where(
                    MgAchatFacture.id != f.id,
                    MgAchatFacture.origine == ORIGINE_FACTURATION,
                    MgAchatFacture.point_facturation_id == f.point_facturation_id,
                    MgAchatFacture.annee == f.annee,
                    MgAchatFacture.mois == f.mois,
                    MgAchatFacture.deleted_at.is_(None),
                    MgAchatFacture.statut != "ANNULEE",
                )
            )
            if existing:
                raise AppError(
                    f"Une facture existe déjà pour ce point sur {libelle_periode(f.annee, f.mois)} ({existing}). "
                    "Confirmez pour enregistrer une facture complémentaire.",
                    status_code=409,
                    code="FACTURE_PERIODE_EXISTANTE",
                )

    async def _resoudre_rattachements(self, f: MgAchatFacture, data, champs: set[str]) -> MgPointFacturation | None:
        point = None
        if "point_facturation_id" in champs:
            if data.point_facturation_id:
                point = await self._point(data.point_facturation_id)
                if point.statut != "ACTIF" and point.id != f.point_facturation_id:
                    raise AppError("Point de facturation inactif", code="POINT_INACTIF")
                f.point_facturation_id = point.id
            else:
                f.point_facturation_id = None
        elif f.point_facturation_id:
            point = await self.db.get(MgPointFacturation, f.point_facturation_id)

        profil = None
        if "profil_id" in champs:
            profil = await self._profil(data.profil_id, actif=data.profil_id != f.profil_id) if data.profil_id else None
            f.profil_id = profil.id if profil else None
        elif f.profil_id:
            profil = await self.db.get(MgFacturationProfil, f.profil_id)
        elif point and point.profil_id:
            profil = await self.db.get(MgFacturationProfil, point.profil_id)
            f.profil_id = profil.id if profil else None
        fournisseur_saisi = data.fournisseur_id if "fournisseur_id" in champs else None
        if profil and "profil_id" not in champs and (
            (point and point.fournisseur_id != profil.fournisseur_id)
            or (fournisseur_saisi and fournisseur_saisi != profil.fournisseur_id)
        ):
            profil, f.profil_id = None, None
        if profil and point and point.fournisseur_id != profil.fournisseur_id:
            raise AppError("Le point de facturation appartient à un autre fournisseur que le profil", code="POINT_FOURNISSEUR_DIFFERENT")
        if profil and fournisseur_saisi and fournisseur_saisi != profil.fournisseur_id:
            raise AppError("Le profil choisi appartient à un autre fournisseur", code="PROFIL_FOURNISSEUR_DIFFERENT")
        if profil and not f.type_facture and not ("type_facture" in champs and data.type_facture):
            f.type_facture = profil.type_facture

        fournisseur_id = data.fournisseur_id if "fournisseur_id" in champs and data.fournisseur_id else None
        if fournisseur_id is None:
            fournisseur_id = (profil.fournisseur_id if profil else None) or f.fournisseur_id or (
                point.fournisseur_id if point else None
            )
        if point and fournisseur_id and point.fournisseur_id != fournisseur_id:
            if "fournisseur_id" in champs and data.fournisseur_id:
                raise AppError(
                    "Le point de facturation appartient à un autre fournisseur", code="POINT_FOURNISSEUR_DIFFERENT"
                )
            fournisseur_id = point.fournisseur_id
        if not fournisseur_id:
            raise AppError("Fournisseur obligatoire (ou point de facturation)", code="CHAMP_OBLIGATOIRE")
        fr = await self._fournisseur(fournisseur_id)
        f.fournisseur_id = fr.id

        if "agence_id" in champs:
            f.agence_id = (await self._agence(data.agence_id)).id if data.agence_id else None
        if f.agence_id is None and point and point.agence_id:
            f.agence_id = point.agence_id
        if self.scope_agence and f.agence_id != self.scope_agence:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Agence hors de votre périmètre")

        if "contrat_id" in champs:
            f.contrat_id = (await self._contrat(data.contrat_id)).id if data.contrat_id else None
        if f.contrat_id is None and point and point.contrat_id:
            f.contrat_id = point.contrat_id
        return point

    async def create_facture(self, data: FactureCreate, user: User) -> dict:
        await self.ensure_defaults()
        champs = set(data.model_fields_set) | {"date_facture"}
        f = MgAchatFacture(
            id=uuid.uuid4(),
            origine=ORIGINE_FACTURATION,
            reference=await self._next_reference(),
            bon_id=None,
            statut="RECUE" if data.enregistrer else "BROUILLON",
            devise="MRU",
            autres_taxes=ZERO,
            remise=ZERO,
            montant_ht=None,
            montant_tva=None,
            montant_ttc=ZERO,
            montant_paye=ZERO,
            created_by=user.id,
            updated_by=user.id,
        )
        f.lignes = []
        point = await self._resoudre_rattachements(f, data, champs)
        await self._appliquer(f, data, champs, point)
        if f.date_reception is None and data.enregistrer:
            f.date_reception = date.today()
        await self._exiger_champs(f)
        await self._check_doublons(f, data.forcer)
        apres = self._snapshot(f)
        _forcer_null(f)
        self.db.add(f)
        periode = libelle_periode(f.annee, f.mois)
        self._event(
            EVT_FACTURE, f.id, "CREATION",
            f"Facture {f.reference} créée ({STATUT_LABELS[f.statut]})" + (f" — {periode}" if periode else ""),
            user,
        )
        if point:
            self._event(EVT_POINT, point.id, "FACTURE", f"Facture {f.reference} saisie" + (f" — {periode}" if periode else ""), user)
        await self._audit(user, "factures.create", f.id, after=apres)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise AppError("Référence déjà attribuée, veuillez réessayer", status_code=409, code="REFERENCE_CONCURRENTE")
        return await self.get_facture(f.id, user)

    async def update_facture(self, facture_id: uuid.UUID, data: FactureUpdate, user: User) -> dict:
        f = await self._facture(facture_id, lock=True)
        if f.statut in VERROUILLES:
            raise AppError("Facture annulée ou archivée : consultation uniquement", code="FACTURE_VERROUILLEE")
        champs = set(data.model_fields_set) - {"forcer"}
        if not champs:
            return await self.get_facture(f.id, user)
        if f.statut == "VALIDEE" and champs & (CHAMPS_FINANCIERS | {"point_facturation_id", "mois", "annee", "periode_debut"}):
            raise AppError(
                "Facture validée : montants, fournisseur et période ne sont plus modifiables. "
                "Contestez-la pour la corriger.",
                code="FACTURE_VALIDEE_NON_MODIFIABLE",
            )
        before = self._snapshot(f)
        point = await self._resoudre_rattachements(f, data, champs)
        await self._appliquer(f, data, champs, point)
        await self._exiger_champs(f)
        await self._check_doublons(f, data.forcer)
        f.updated_by = user.id
        if f.statut in STATUTS_PAYABLES:
            await self._recalculer_paiements(f)
        after = self._snapshot(f)
        changes = [CHAMPS_LABELS.get(k, k) for k in CHAMPS_LABELS if before.get(k) != after.get(k)]
        if "lignes" in champs:
            changes.append("Lignes")
        recontrole = f.statut == "CONTROLEE" and any(
            before.get(k) != after.get(k) for k in CHAMPS_FINANCIERS | {"point_facturation_id", "mois", "annee", "periode_debut"}
        )
        if recontrole:
            f.statut = "A_CONTROLER"
            f.controle_at = None
            f.controle_by = None
        self._event(
            EVT_FACTURE, f.id, "MODIFICATION",
            "Modification : " + (", ".join(changes) if changes else "aucun changement de valeur")
            + (" — contrôle à refaire (À contrôler)" if recontrole else ""),
            user,
        )
        await self._audit(user, "factures.update", f.id, before=before, after=after)
        await self.db.commit()
        return await self.get_facture(f.id, user)

    async def delete_facture(self, facture_id: uuid.UUID, user: User, motif: str | None) -> None:
        f = await self._facture(facture_id, lock=True)
        if f.statut not in {"BROUILLON", "RECUE"}:
            raise AppError(
                "Seule une facture brouillon ou reçue peut être supprimée. Utilisez « Annuler » pour conserver la trace.",
                code="FACTURE_NON_SUPPRIMABLE",
            )
        if await self._paiements_actifs(f.id):
            raise AppError("Facture avec paiements : suppression impossible", code="FACTURE_NON_SUPPRIMABLE")
        f.deleted_at = datetime.now(timezone.utc)
        f.updated_by = user.id
        self._event(EVT_FACTURE, f.id, "SUPPRESSION", "Facture supprimée (logique)" + (f" — {motif}" if motif else ""), user)
        await self._audit(user, "factures.delete", f.id, before=self._snapshot(f), after={"motif": motif})
        await self.db.commit()

    async def transition(self, facture_id: uuid.UUID, action: str, user: User, motif: str | None) -> dict:
        if action not in TRANSITIONS:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Action inconnue")
        have = await load_user_permission_codes(self.db, user)
        if not (user.is_superuser or user_has_permission_codes(have, PERMISSION_ACTION[action])):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Permission insuffisante pour cette action")
        f = await self._facture(facture_id, lock=True)
        sources, cible = TRANSITIONS[action]
        if f.statut not in sources:
            raise AppError(
                f"Action impossible depuis le statut « {STATUT_LABELS.get(f.statut, f.statut)} »",
                status_code=409,
                code="FACTURE_TRANSITION_INVALIDE",
            )
        motif = _clean(motif)
        if action in MOTIF_OBLIGATOIRE and not motif:
            raise AppError("Motif obligatoire", code="MOTIF_OBLIGATOIRE")
        actifs = await self._paiements_actifs(f.id)
        if action in {"contester", "annuler"} and actifs:
            raise AppError(
                "Des paiements sont enregistrés sur cette facture : annulez-les d'abord",
                status_code=409,
                code="FACTURE_PAIEMENTS_EXISTANTS",
            )
        if action in {"enregistrer", "controler", "valider_controle", "valider"}:
            champs_profil, taux = await self._profil_champs(f)
            manquants = champs_manquants(f, champs_profil)
            if manquants:
                raise AppError(
                    "Champs obligatoires pour ce fournisseur : " + ", ".join(CHAMPS_PROFIL[c] for c in manquants),
                    code="FACTURE_CHAMPS_OBLIGATOIRES",
                )
        if action == "valider_controle":
            fr = await self.db.get(Fournisseur, f.fournisseur_id)
            nb_docs = (await self._nb_documents([f.id])).get(str(f.id), 0)
            bloquants = [
                c["message"]
                for c in controles_facture(
                    f, champs_profil, taux, nb_docs, fournisseur_actif=bool(fr and fr.deleted_at is None and fr.is_active)
                )
                if c["niveau"] == "bloquant"
            ]
            if bloquants:
                raise AppError("Contrôle non concluant : " + " ; ".join(bloquants), code="FACTURE_CONTROLE_BLOQUANT")
            await self._check_doublons(f, forcer=True)
        if action == "valider":
            if a_payer_effectif(f) <= 0:
                raise AppError("Montant à payer requis avant validation", code="FACTURE_MONTANT_REQUIS")
            await self._check_doublons(f, forcer=True)
        if action == "archiver" and f.statut == "VALIDEE":
            await self._recalculer_paiements(f)
            if f.statut_paiement != "PAYEE":
                raise AppError("Seule une facture soldée ou annulée peut être archivée", code="FACTURE_NON_SOLDEE")

        before = self._snapshot(f)
        ancien = f.statut
        now = datetime.now(timezone.utc)
        f.statut = cible
        f.updated_by = user.id
        if action == "enregistrer" and f.date_reception is None:
            f.date_reception = date.today()
        elif action == "valider_controle":
            f.controle_at = now
            f.controle_by = user.id
        elif action == "controler":
            f.controle_at = None
            f.controle_by = None
        elif action == "valider":
            f.valide_at = now
            f.valide_by = user.id
            f.motif_validation = motif
        elif action == "contester":
            f.motif_validation = motif
            f.valide_at = None
            f.valide_by = None
        elif action == "annuler":
            f.annule_at = now
            f.annule_by = user.id
        elif action == "archiver":
            f.archived_at = now
        await self._recalculer_paiements(f)
        message = f"{ACTION_LABELS[action]} ({STATUT_LABELS[ancien]} → {STATUT_LABELS[cible]})"
        if motif:
            message += f" — {motif}"
        self._event(EVT_FACTURE, f.id, action.upper(), message, user)
        await self._audit(user, f"factures.{action}", f.id, before=before, after=self._snapshot(f) | {"motif": motif})
        await self.db.commit()
        return await self.get_facture(f.id, user)

    async def dupliquer(self, facture_id: uuid.UUID, user: User) -> dict:
        """Brouillon pour la période suivante, mêmes rattachements, sans montants (jamais inventés)."""
        src = await self._facture(facture_id)
        if src.annee and src.mois:
            pas = 1
            if src.point_facturation_id:
                point = await self.db.get(MgPointFacturation, src.point_facturation_id)
                pas = PERIODICITES_POINT.get(point.periodicite if point else "MENSUEL", 1) or 1
            annee, mois = mois_suivant(src.annee, src.mois, pas)
        else:
            annee, mois = None, None
        f = MgAchatFacture(
            id=uuid.uuid4(),
            origine=ORIGINE_FACTURATION,
            reference=await self._next_reference(),
            bon_id=None,
            statut="BROUILLON",
            fournisseur_id=src.fournisseur_id,
            profil_id=src.profil_id,
            point_facturation_id=src.point_facturation_id,
            agence_id=src.agence_id,
            contrat_id=src.contrat_id,
            type_facture=src.type_facture,
            reference_fournisseur=src.reference_fournisseur,
            date_facture=date.today(),
            annee=annee,
            mois=mois,
            devise=src.devise,
            autres_taxes=ZERO,
            remise=ZERO,
            montant_ht=None,
            montant_tva=None,
            montant_ttc=ZERO,
            montant_paye=ZERO,
            created_by=user.id,
            updated_by=user.id,
        )
        if annee and mois:
            f.periode_debut = date(annee, mois, 1)
        _forcer_null(f)
        self.db.add(f)
        self._event(EVT_FACTURE, f.id, "CREATION", f"Brouillon créé par duplication de {src.reference}", user)
        self._event(EVT_FACTURE, src.id, "DUPLICATION", f"Dupliquée vers {f.reference}", user)
        await self._audit(user, "factures.duplicate", f.id, after={"source": str(src.id), "reference": f.reference})
        await self.db.commit()
        return await self.get_facture(f.id, user)

    # ——— Paiements ———

    async def add_paiement(self, facture_id: uuid.UUID, data: FacturePaiementIn, user: User) -> dict:
        f = await self._facture(facture_id, lock=True)
        if f.statut != "VALIDEE":
            raise AppError("Le paiement n'est possible que sur une facture validée", code="FACTURE_NON_VALIDEE")
        await self._recalculer_paiements(f)
        reste = a_payer_effectif(f) - Decimal(f.montant_paye or 0)
        montant = q2(data.montant)
        if montant - reste > TOLERANCE:
            raise AppError(
                f"Le paiement dépasse le reste à payer ({q2(max(reste, ZERO))} {f.devise})",
                code="PAIEMENT_SUPERIEUR_RESTE",
            )
        if data.date_paiement > date.today():
            raise AppError("Date de paiement future", code="PAIEMENT_DATE_INVALIDE")
        await self._check_justificatif(f, data.justificatif_document_id)
        mode = _clean(data.mode_paiement)
        if not mode:
            raise AppError("Moyen de paiement obligatoire", code="CHAMP_OBLIGATOIRE")
        detail = detail_paiement(mode, {k: getattr(data, k) for k in CHAMPS_DETAIL_PAIEMENT}, _clean(data.observation))
        p = MgAchatPaiement(
            id=uuid.uuid4(),
            reference=await self._next_paiement_ref(),
            origine=ORIGINE_FACTURATION,
            facture_id=f.id,
            fournisseur_id=f.fournisseur_id,
            montant=montant,
            date_echeance=f.date_echeance,
            date_paiement=data.date_paiement,
            mode_paiement=mode,
            observation=_clean(data.observation),
            justificatif_document_id=data.justificatif_document_id,
            statut="PAYE",
            created_by=user.id,
            **detail,
        )
        self.db.add(p)
        await self._recalculer_paiements(f)
        self._event(
            EVT_FACTURE, f.id, "PAIEMENT",
            f"Paiement {p.reference} : {montant} {f.devise}" + (f" ({mode})" if mode else "")
            + f" — {STATUT_PAIEMENT_LABELS.get(f.statut_paiement or '', '')}",
            user,
        )
        await self._audit(
            user, "factures.payment.create", f.id,
            after={"paiement": p.reference, "montant": str(montant), "statut_paiement": f.statut_paiement},
        )
        await self.db.commit()
        return await self.get_facture(f.id, user)

    async def _check_justificatif(self, f: MgAchatFacture, document_id) -> None:
        if not document_id:
            return
        doc = await self.db.scalar(
            select(GedDocument).where(GedDocument.id == document_id, GedDocument.deleted_at.is_(None))
        )
        if not doc or doc.entity != GED_ENTITY or doc.entity_id != str(f.id):
            raise AppError("Justificatif introuvable sur cette facture", code="REFERENCE_INTROUVABLE")

    async def _paiement(self, paiement_id: uuid.UUID) -> tuple[MgAchatPaiement, MgAchatFacture]:
        p = await self.db.scalar(
            select(MgAchatPaiement).where(
                MgAchatPaiement.id == paiement_id,
                MgAchatPaiement.origine == ORIGINE_FACTURATION,
                MgAchatPaiement.deleted_at.is_(None),
            )
        )
        if not p:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paiement introuvable")
        f = await self._facture(p.facture_id, lock=True)
        return p, f

    async def update_paiement(self, paiement_id: uuid.UUID, data: FacturePaiementUpdate, user: User) -> dict:
        p, f = await self._paiement(paiement_id)
        if p.statut != "PAYE":
            raise AppError("Paiement annulé : consultation uniquement", code="PAIEMENT_ANNULE")
        if f.statut != "VALIDEE":
            raise AppError("Facture non modifiable (archivée ou non validée)", code="FACTURE_VERROUILLEE")
        champs = data.model_fields_set
        before = {"montant": str(p.montant), "date_paiement": _iso(p.date_paiement), "mode": p.mode_paiement}
        if "montant" in champs and data.montant is not None:
            await self._recalculer_paiements(f)
            reste = a_payer_effectif(f) - Decimal(f.montant_paye or 0) + Decimal(p.montant)
            if Decimal(data.montant) - reste > TOLERANCE:
                raise AppError(
                    f"Le paiement dépasse le reste à payer ({q2(max(reste, ZERO))} {f.devise})",
                    code="PAIEMENT_SUPERIEUR_RESTE",
                )
            p.montant = q2(data.montant)
        if "date_paiement" in champs and data.date_paiement:
            if data.date_paiement > date.today():
                raise AppError("Date de paiement future", code="PAIEMENT_DATE_INVALIDE")
            p.date_paiement = data.date_paiement
        if "observation" in champs:
            p.observation = _clean(data.observation)
        if champs & ({"mode_paiement", "observation"} | set(CHAMPS_DETAIL_PAIEMENT)):
            mode = _clean(data.mode_paiement) if "mode_paiement" in champs else p.mode_paiement
            if not mode:
                raise AppError("Moyen de paiement obligatoire", code="CHAMP_OBLIGATOIRE")
            actuels = {
                "compte": p.compte, "banque": p.banque, "numero_cheque": p.numero_cheque,
                "reference_paiement": p.reference_paiement,
                "carte_derniers_chiffres": re.sub(r"\D", "", p.carte_masquee) if p.carte_masquee else None,
            }
            valeurs = {k: getattr(data, k) if k in champs else actuels[k] for k in CHAMPS_DETAIL_PAIEMENT}
            for k, v in detail_paiement(mode, valeurs, p.observation).items():
                setattr(p, k, v)
            p.mode_paiement = mode
        if "justificatif_document_id" in champs:
            await self._check_justificatif(f, data.justificatif_document_id)
            p.justificatif_document_id = data.justificatif_document_id
        await self._recalculer_paiements(f)
        self._event(EVT_FACTURE, f.id, "PAIEMENT_MODIFIE", f"Paiement {p.reference} modifié ({p.montant} {f.devise})", user)
        await self._audit(
            user, "factures.payment.update", f.id,
            before=before,
            after={"montant": str(p.montant), "date_paiement": _iso(p.date_paiement), "mode": p.mode_paiement},
        )
        await self.db.commit()
        return await self.get_facture(f.id, user)

    async def annuler_paiement(self, paiement_id: uuid.UUID, user: User, motif: str | None) -> dict:
        p, f = await self._paiement(paiement_id)
        if p.statut != "PAYE":
            raise AppError("Paiement déjà annulé", code="PAIEMENT_ANNULE")
        if f.statut == "ARCHIVEE":
            raise AppError("Facture archivée : consultation uniquement", code="FACTURE_VERROUILLEE")
        motif = _clean(motif)
        if not motif:
            raise AppError("Motif obligatoire", code="MOTIF_OBLIGATOIRE")
        p.statut = "ANNULE"
        p.annule_at = datetime.now(timezone.utc)
        p.annule_by = user.id
        p.observation = ((p.observation + "\n") if p.observation else "") + f"Annulé : {motif}"
        await self._recalculer_paiements(f)
        self._event(EVT_FACTURE, f.id, "PAIEMENT_ANNULE", f"Paiement {p.reference} annulé ({p.montant} {f.devise}) — {motif}", user)
        await self._audit(user, "factures.payment.delete", f.id, after={"paiement": p.reference, "motif": motif})
        await self.db.commit()
        return await self.get_facture(f.id, user)

    async def list_paiements(self, filtres: dict) -> list[dict]:
        F = MgAchatFacture
        P = MgAchatPaiement
        stmt = (
            select(P, F.reference, F.numero_fournisseur, F.annee, F.mois, Fournisseur.raison_sociale, Agence.libelle, MgPointFacturation.nom)
            .join(F, F.id == P.facture_id)
            .outerjoin(Fournisseur, Fournisseur.id == F.fournisseur_id)
            .outerjoin(Agence, Agence.id == F.agence_id)
            .outerjoin(MgPointFacturation, MgPointFacturation.id == F.point_facturation_id)
            .where(P.origine == ORIGINE_FACTURATION, P.deleted_at.is_(None), F.deleted_at.is_(None))
        )
        if self.scope_agence:
            stmt = stmt.where(F.agence_id == self.scope_agence)
        if filtres.get("statut"):
            stmt = stmt.where(P.statut == str(filtres["statut"]).upper())
        if filtres.get("date_from"):
            stmt = stmt.where(P.date_paiement >= filtres["date_from"])
        if filtres.get("date_to"):
            stmt = stmt.where(P.date_paiement <= filtres["date_to"])
        if filtres.get("annee"):
            stmt = stmt.where(func.extract("year", P.date_paiement) == int(filtres["annee"]))
        if filtres.get("mois"):
            stmt = stmt.where(func.extract("month", P.date_paiement) == int(filtres["mois"]))
        if filtres.get("fournisseur_id"):
            stmt = stmt.where(F.fournisseur_id == filtres["fournisseur_id"])
        if filtres.get("agence_id"):
            stmt = stmt.where(F.agence_id == filtres["agence_id"])
        if filtres.get("mode_paiement"):
            stmt = stmt.where(P.mode_paiement == filtres["mode_paiement"])
        q = (filtres.get("q") or "").strip()
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    P.reference.ilike(like), P.reference_paiement.ilike(like), F.reference.ilike(like),
                    F.numero_fournisseur.ilike(like), Fournisseur.raison_sociale.ilike(like),
                    Agence.libelle.ilike(like), MgPointFacturation.nom.ilike(like),
                )
            )
        rows = (await self.db.execute(stmt.order_by(P.date_paiement.desc(), P.created_at.desc()).limit(2000))).all()
        return [
            {
                "id": str(p.id),
                "reference": p.reference,
                "facture_id": str(p.facture_id),
                "facture_reference": ref,
                "numero_fournisseur": num,
                "periode_label": libelle_periode(annee, mois),
                "fournisseur": fr,
                "agence": ag,
                "point_nom": pt,
                "date_paiement": _iso(p.date_paiement),
                "montant": to_float(p.montant),
                "mode_paiement": p.mode_paiement,
                "reference_paiement": p.reference_paiement,
                **_detail_paiement(p),
                "statut": p.statut,
                "observation": p.observation,
            }
            for p, ref, num, annee, mois, fr, ag, pt in rows
        ]

    # ——— Documents (GED centrale) ———

    async def upload_document(
        self,
        facture_id: uuid.UUID,
        file: UploadFile,
        user: User,
        *,
        doc_type: str | None,
        title: str | None,
        reference: str | None,
        date_document: date | None,
    ) -> dict:
        from app.services.document_ingest_service import DocumentIngestService

        f = await self._facture(facture_id)
        if f.statut == "ARCHIVEE":
            raise AppError("Facture archivée : ajout de pièce impossible", code="FACTURE_VERROUILLEE")
        code = (doc_type or "FACTURE_SCANNEE").strip().upper()
        if code not in dict(TYPES_DOCUMENT):
            raise AppError("Type de document inconnu", code="DOCUMENT_TYPE_INVALIDE")
        max_mo = await self._param_int("contrats.ged_taille_max_mo", 15)
        size = getattr(file, "size", None)
        if size is not None and size > max_mo * 1024 * 1024:
            raise AppError(f"Fichier trop volumineux (max {max_mo} Mo)", status_code=413, code="FICHIER_TROP_VOLUMINEUX")
        if size == 0:
            raise AppError("Fichier vide", code="FICHIER_VIDE")
        doc = await DocumentIngestService(self.db).ingest_document(
            file=file,
            espace_code=ESPACE,
            module_code=MODULE,
            entity=GED_ENTITY,
            entity_id=str(f.id),
            uploaded_by_id=user.id,
            title=_clean(title) or None,
            doc_type=code,
            reference=_clean(reference) or f.numero_fournisseur or f.reference,
            date_document=date_document or f.date_facture,
            agence_id=f.agence_id,
            fournisseur_id=f.fournisseur_id,
            security_level="internal",
            notify=False,
        )
        self._event(EVT_FACTURE, f.id, "DOCUMENT", f"Document ajouté : {doc.title or doc.filename} ({dict(TYPES_DOCUMENT)[code]})", user)
        await self._audit(user, "factures.documents.create", f.id, after={"document_id": str(doc.id), "filename": doc.filename})
        await self.db.commit()
        return self._doc_dict(doc, {user.id: user.full_name})

    async def document_de_facture(self, facture_id: uuid.UUID, document_id: uuid.UUID) -> GedDocument:
        f = await self._facture(facture_id)
        doc = await self.db.scalar(
            select(GedDocument).where(
                GedDocument.id == document_id,
                GedDocument.deleted_at.is_(None),
                GedDocument.module_code == MODULE,
                GedDocument.entity == GED_ENTITY,
                GedDocument.entity_id == str(f.id),
            )
        )
        if not doc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document introuvable")
        return doc

    async def delete_document(self, facture_id: uuid.UUID, document_id: uuid.UUID, user: User, motif: str | None) -> None:
        from app.services.ged_service import GedService

        doc = await self.document_de_facture(facture_id, document_id)
        f = await self._facture(facture_id)
        if f.statut == "ARCHIVEE":
            raise AppError("Facture archivée : pièces figées", code="FACTURE_VERROUILLEE")
        motif = _clean(motif)
        if not motif:
            raise AppError("Motif obligatoire", code="MOTIF_OBLIGATOIRE")
        used = await self.db.scalar(
            select(func.count()).select_from(MgAchatPaiement).where(
                MgAchatPaiement.justificatif_document_id == doc.id,
                MgAchatPaiement.statut == "PAYE",
                MgAchatPaiement.deleted_at.is_(None),
            )
        )
        if used:
            raise AppError("Ce document justifie un paiement actif", code="DOCUMENT_UTILISE")
        await GedService(self.db).soft_delete(doc.id, user_id=user.id, reason=motif)
        self._event(EVT_FACTURE, f.id, "DOCUMENT_RETIRE", f"Document retiré : {doc.title or doc.filename} — {motif}", user)
        await self._audit(user, "factures.documents.delete", f.id, after={"document_id": str(doc.id), "motif": motif})
        await self.db.commit()

    # ——— Points de facturation ———

    def _point_dict(self, p: MgPointFacturation, fournisseur: str | None, agence: str | None, stats: dict | None = None) -> dict:
        s = stats or {}
        derniere = s.get("derniere")
        return {
            "id": str(p.id),
            "code": p.code,
            "type_point": p.type_point,
            "type_point_label": TYPE_POINT_LABELS.get(p.type_point, p.type_point),
            "nom": p.nom,
            "agence_id": str(p.agence_id) if p.agence_id else None,
            "agence": agence,
            "fournisseur_id": str(p.fournisseur_id),
            "fournisseur": fournisseur,
            "profil_id": str(p.profil_id) if p.profil_id else None,
            "contrat_id": str(p.contrat_id) if p.contrat_id else None,
            "reference_fournisseur": p.reference_fournisseur,
            "reference_normalisee": p.reference_normalisee,
            "compteur": p.compteur,
            "type_facture": p.type_facture,
            "periodicite": p.periodicite,
            "adresse": p.adresse,
            "telephone": p.telephone,
            "date_debut": _iso(p.date_debut),
            "date_fin": _iso(p.date_fin),
            "statut": p.statut,
            "description": p.description,
            "nb_factures": int(s.get("nb", 0)),
            "total_annee": float(s.get("total", 0) or 0),
            "derniere_periode": derniere,
            "derniere_periode_label": libelle_periode(derniere // 100, derniere % 100) if derniere else None,
            "created_at": _iso(p.created_at),
        }

    async def _stats_points(self, ids: list[uuid.UUID], annee: int) -> dict[uuid.UUID, dict]:
        if not ids:
            return {}
        F = MgAchatFacture
        compte = F.statut.in_(STATUTS_COMPTES)
        rows = await self.db.execute(
            select(
                F.point_facturation_id,
                func.count(F.id).filter(F.statut != "ANNULEE"),
                func.coalesce(func.sum(F.montant_ttc).filter(compte, F.annee == annee), 0),
                func.max(F.annee * 100 + F.mois).filter(F.statut != "ANNULEE"),
            )
            .where(F.origine == ORIGINE_FACTURATION, F.deleted_at.is_(None), F.point_facturation_id.in_(ids))
            .group_by(F.point_facturation_id)
        )
        return {pid: {"nb": nb, "total": total, "derniere": derniere} for pid, nb, total, derniere in rows.all()}

    async def list_points(self, filtres: dict) -> list[dict]:
        P = MgPointFacturation
        stmt = (
            select(P, Fournisseur.raison_sociale, Agence.libelle)
            .outerjoin(Fournisseur, Fournisseur.id == P.fournisseur_id)
            .outerjoin(Agence, Agence.id == P.agence_id)
            .where(P.deleted_at.is_(None))
        )
        if self.scope_agence:
            stmt = stmt.where(P.agence_id == self.scope_agence)
        if filtres.get("type_point"):
            stmt = stmt.where(P.type_point == str(filtres["type_point"]).upper())
        if filtres.get("statut"):
            stmt = stmt.where(P.statut == str(filtres["statut"]).upper())
        if filtres.get("fournisseur_id"):
            stmt = stmt.where(P.fournisseur_id == filtres["fournisseur_id"])
        if filtres.get("agence_id"):
            stmt = stmt.where(P.agence_id == filtres["agence_id"])
        if filtres.get("type_facture"):
            stmt = stmt.where(P.type_facture == str(filtres["type_facture"]).upper())
        q = (filtres.get("q") or "").strip()
        if q:
            like = f"%{q}%"
            conds = [
                P.nom.ilike(like), P.code.ilike(like), P.reference_fournisseur.ilike(like), P.compteur.ilike(like),
                Fournisseur.raison_sociale.ilike(like), Agence.libelle.ilike(like),
            ]
            digits = re.sub(r"\D", "", q)
            if len(digits) >= 4:
                conds.append(P.reference_normalisee.contains(digits))
            stmt = stmt.where(or_(*conds))
        rows = (await self.db.execute(stmt.order_by(P.type_point, P.nom))).all()
        annee = int(filtres.get("annee") or date.today().year)
        stats = await self._stats_points([r[0].id for r in rows], annee)
        return [self._point_dict(p, fr, ag, stats.get(p.id)) for p, fr, ag in rows]

    async def _check_point_unique(self, fournisseur_id, normalisee: str, exclude_id=None) -> None:
        stmt = select(MgPointFacturation.code).where(
            MgPointFacturation.fournisseur_id == fournisseur_id,
            MgPointFacturation.reference_normalisee == normalisee,
            MgPointFacturation.deleted_at.is_(None),
        )
        if exclude_id:
            stmt = stmt.where(MgPointFacturation.id != exclude_id)
        existing = await self.db.scalar(stmt)
        if existing:
            raise AppError(
                f"Cette référence existe déjà chez ce fournisseur (point {existing})",
                status_code=409,
                code="POINT_REFERENCE_EXISTANTE",
            )

    def _valider_point(self, type_point: str | None, periodicite: str | None, statut: str | None) -> None:
        if type_point is not None and type_point not in TYPES_POINT:
            raise AppError("Type de point inconnu", code="POINT_TYPE_INVALIDE")
        if periodicite is not None and periodicite not in PERIODICITES_POINT:
            raise AppError("Périodicité inconnue", code="PERIODICITE_INVALIDE")
        if statut is not None and statut not in {"ACTIF", "INACTIF"}:
            raise AppError("Statut inconnu", code="POINT_STATUT_INVALIDE")

    async def create_point(self, data: PointFacturationCreate, user: User, *, commit: bool = True, origine: str | None = None) -> MgPointFacturation:
        type_point = data.type_point.strip().upper()
        periodicite = (data.periodicite or "MENSUEL").strip().upper()
        self._valider_point(type_point, periodicite, (data.statut or "ACTIF").upper())
        fr = await self._fournisseur(data.fournisseur_id)
        affichee, normalisee, compteur = decouper_reference(data.reference_fournisseur)
        if not normalisee:
            raise AppError("Référence fournisseur obligatoire", code="CHAMP_OBLIGATOIRE")
        normalisee = normaliser_reference(data.reference_fournisseur)
        await self._check_point_unique(fr.id, normalisee)
        agence_id = (await self._agence(data.agence_id)).id if data.agence_id else None
        if self.scope_agence and agence_id != self.scope_agence:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Agence hors de votre périmètre")
        contrat_id = (await self._contrat(data.contrat_id)).id if data.contrat_id else None
        profil = await self._profil(data.profil_id) if data.profil_id else None
        if profil and profil.fournisseur_id != fr.id:
            raise AppError("Le profil choisi appartient à un autre fournisseur", code="PROFIL_FOURNISSEUR_DIFFERENT")
        if data.date_debut and data.date_fin and data.date_fin < data.date_debut:
            raise AppError("La date de fin précède la date de début", code="POINT_DATES_INVALIDES")
        p = MgPointFacturation(
            id=uuid.uuid4(),
            code=await self._next_point_code(),
            type_point=type_point,
            nom=data.nom.strip(),
            agence_id=agence_id,
            fournisseur_id=fr.id,
            profil_id=profil.id if profil else None,
            contrat_id=contrat_id,
            reference_fournisseur=affichee[:80],
            reference_normalisee=normalisee[:80],
            compteur=_clean(data.compteur) or compteur,
            type_facture=(_clean(data.type_facture) or "").upper() or None,
            periodicite=periodicite,
            adresse=_clean(data.adresse),
            telephone=_clean(data.telephone),
            date_debut=data.date_debut,
            date_fin=data.date_fin,
            statut=(data.statut or "ACTIF").upper(),
            description=_clean(data.description),
            created_by=user.id,
            updated_by=user.id,
        )
        self.db.add(p)
        self._event(EVT_POINT, p.id, "CREATION", f"Point {p.code} créé" + (f" ({origine})" if origine else ""), user)
        await self._audit(
            user, "factures.point.create", p.id, entity="point_facturation",
            after={"code": p.code, "nom": p.nom, "reference": p.reference_fournisseur, "origine": origine},
        )
        if commit:
            try:
                await self.db.commit()
            except IntegrityError:
                await self.db.rollback()
                raise AppError("Code ou référence déjà attribué, veuillez réessayer", status_code=409, code="POINT_CONCURRENT")
        else:
            await self.db.flush()
        return p

    async def update_point(self, point_id: uuid.UUID, data: PointFacturationIn, user: User) -> MgPointFacturation:
        p = await self._point(point_id, lock=True)
        champs = data.model_fields_set
        before = self._point_dict(p, None, None)
        if "type_point" in champs and data.type_point:
            self._valider_point(data.type_point.upper(), None, None)
            p.type_point = data.type_point.upper()
        if "periodicite" in champs and data.periodicite:
            self._valider_point(None, data.periodicite.upper(), None)
            p.periodicite = data.periodicite.upper()
        if "statut" in champs and data.statut:
            self._valider_point(None, None, data.statut.upper())
            p.statut = data.statut.upper()
        if "nom" in champs and data.nom and data.nom.strip():
            p.nom = data.nom.strip()
        if "fournisseur_id" in champs and data.fournisseur_id and data.fournisseur_id != p.fournisseur_id:
            nb = await self.db.scalar(
                select(func.count()).select_from(MgAchatFacture).where(
                    MgAchatFacture.point_facturation_id == p.id, MgAchatFacture.deleted_at.is_(None)
                )
            )
            if nb:
                raise AppError("Point déjà facturé : le fournisseur n'est plus modifiable", code="POINT_FACTURE")
            p.fournisseur_id = (await self._fournisseur(data.fournisseur_id)).id
        if "reference_fournisseur" in champs and data.reference_fournisseur:
            affichee, _, compteur = decouper_reference(data.reference_fournisseur)
            normalisee = normaliser_reference(data.reference_fournisseur)
            if not normalisee:
                raise AppError("Référence fournisseur obligatoire", code="CHAMP_OBLIGATOIRE")
            p.reference_fournisseur = affichee[:80]
            p.reference_normalisee = normalisee[:80]
            if compteur and "compteur" not in champs:
                p.compteur = compteur
        await self._check_point_unique(p.fournisseur_id, p.reference_normalisee, exclude_id=p.id)
        if "agence_id" in champs:
            p.agence_id = (await self._agence(data.agence_id)).id if data.agence_id else None
            if self.scope_agence and p.agence_id != self.scope_agence:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Agence hors de votre périmètre")
        if "contrat_id" in champs:
            p.contrat_id = (await self._contrat(data.contrat_id)).id if data.contrat_id else None
        if "profil_id" in champs:
            p.profil_id = (await self._profil(data.profil_id, actif=data.profil_id != p.profil_id)).id if data.profil_id else None
        if p.profil_id:
            profil = await self.db.get(MgFacturationProfil, p.profil_id)
            if profil and profil.fournisseur_id != p.fournisseur_id:
                if "profil_id" in champs:
                    raise AppError("Le profil choisi appartient à un autre fournisseur", code="PROFIL_FOURNISSEUR_DIFFERENT")
                p.profil_id = None
        for champ in ("compteur", "adresse", "telephone", "description"):
            if champ in champs:
                setattr(p, champ, _clean(getattr(data, champ)))
        if "type_facture" in champs:
            p.type_facture = (_clean(data.type_facture) or "").upper() or None
        for champ in ("date_debut", "date_fin"):
            if champ in champs:
                setattr(p, champ, getattr(data, champ))
        if p.date_debut and p.date_fin and p.date_fin < p.date_debut:
            raise AppError("La date de fin précède la date de début", code="POINT_DATES_INVALIDES")
        p.updated_by = user.id
        after = self._point_dict(p, None, None)
        changes = [k for k in ("nom", "type_point", "reference_fournisseur", "compteur", "agence_id", "fournisseur_id",
                               "contrat_id", "profil_id", "type_facture", "periodicite", "statut", "date_debut", "date_fin", "adresse",
                               "telephone")
                   if before.get(k) != after.get(k)]
        self._event(EVT_POINT, p.id, "MODIFICATION", "Modification : " + (", ".join(changes) or "aucun changement"), user)
        await self._audit(user, "factures.point.update", p.id, entity="point_facturation",
                          before={k: before[k] for k in changes}, after={k: after[k] for k in changes})
        await self.db.commit()
        return p

    async def set_point_statut(self, point_id: uuid.UUID, actif: bool, user: User, motif: str | None) -> MgPointFacturation:
        p = await self._point(point_id, lock=True)
        cible = "ACTIF" if actif else "INACTIF"
        if p.statut == cible:
            return p
        p.statut = cible
        if not actif and not p.date_fin:
            p.date_fin = date.today()
        if actif:
            p.date_fin = None
        p.updated_by = user.id
        label = "réactivé" if actif else "désactivé"
        self._event(EVT_POINT, p.id, cible, f"Point {label}" + (f" — {motif}" if motif else ""), user)
        await self._audit(user, f"factures.point.{'activate' if actif else 'deactivate'}", p.id,
                          entity="point_facturation", after={"statut": cible, "motif": motif})
        await self.db.commit()
        return p

    async def delete_point(self, point_id: uuid.UUID, user: User) -> dict:
        """Suppression logique si aucune facture ; sinon désactivation (historique préservé)."""
        p = await self._point(point_id, lock=True)
        nb = await self.db.scalar(
            select(func.count()).select_from(MgAchatFacture).where(MgAchatFacture.point_facturation_id == p.id)
        )
        if nb:
            await self.set_point_statut(p.id, False, user, "Suppression demandée : point déjà facturé")
            return {"desactive": True, "supprime": False}
        p.deleted_at = datetime.now(timezone.utc)
        p.statut = "INACTIF"
        p.updated_by = user.id
        self._event(EVT_POINT, p.id, "SUPPRESSION", "Point supprimé (aucune facture rattachée)", user)
        await self._audit(user, "factures.point.delete", p.id, entity="point_facturation", before={"code": p.code})
        await self.db.commit()
        return {"desactive": False, "supprime": True}

    async def _montants_mensuels(self, filtre, annee: int) -> list[float]:
        F = MgAchatFacture
        rows = await self.db.execute(
            select(F.mois, func.coalesce(func.sum(F.montant_ttc), 0))
            .where(F.origine == ORIGINE_FACTURATION, F.deleted_at.is_(None), F.statut.in_(STATUTS_COMPTES),
                   F.annee == annee, filtre)
            .group_by(F.mois)
        )
        values = [0.0] * 12
        for mois, total in rows.all():
            if mois:
                values[mois - 1] = float(total)
        return values

    async def point_synthese(self, point_id: uuid.UUID, annee: int | None, user: User) -> dict:
        annee = annee or date.today().year
        p = await self._point(point_id)
        fr = await self.db.get(Fournisseur, p.fournisseur_id)
        ag = await self.db.get(Agence, p.agence_id) if p.agence_id else None
        ct = await self.db.get(MgContrat, p.contrat_id) if p.contrat_id else None
        stats = await self._stats_points([p.id], annee)
        mensuel = await self._montants_mensuels(MgAchatFacture.point_facturation_id == p.id, annee)
        precedent = await self._montants_mensuels(MgAchatFacture.point_facturation_id == p.id, annee - 1)
        factures = await self.fetch_rows({"point_id": p.id, "inclure_historique": True}, limit=60)
        comptees = [r for r in factures if r["statut"] in STATUTS_COMPTES]
        recentes = [Decimal(str(r["montant_ttc"] or 0)) for r in comptees[:6] if r["montant_ttc"]]
        total = sum(mensuel)
        data = self._point_dict(p, fr.raison_sociale if fr else None, ag.libelle if ag else None, stats.get(p.id))
        data.update(
            {
                "annee": annee,
                "mensuel": mensuel,
                "mensuel_n1": precedent,
                "total_annee": total,
                "total_n1": sum(precedent),
                "variation_n1_pct": variation_pct(total, sum(precedent)) if sum(precedent) else None,
                "moyenne_6": float(sum(recentes) / len(recentes)) if recentes else None,
                "reste_a_payer": sum(r["reste"] or 0 for r in factures if r["statut"] in STATUTS_OUVERTS),
                "factures": factures,
                "contrat": {"id": str(ct.id), "reference": ct.reference, "titre": ct.titre} if ct else None,
                "historique": await self._historique(EVT_POINT, p.id),
                "capacites": await capacites(self.db, user),
            }
        )
        return data

    # ——— Synthèses agence / fournisseur ———

    async def agence_synthese(self, agence_id: uuid.UUID, annee: int | None) -> dict:
        annee = annee or date.today().year
        ag = await self._agence(agence_id)
        filtre = MgAchatFacture.agence_id == ag.id
        mensuel = await self._montants_mensuels(filtre, annee)
        precedent = await self._montants_mensuels(filtre, annee - 1)
        points = await self.list_points({"agence_id": ag.id, "annee": annee})
        rows = await self.fetch_rows({"agence_id": ag.id, "annee": annee, "inclure_historique": True})
        par_fournisseur: dict[str, float] = {}
        par_type: dict[str, float] = {}
        for r in rows:
            if r["statut"] not in STATUTS_COMPTES:
                continue
            par_fournisseur[r["fournisseur"] or "—"] = par_fournisseur.get(r["fournisseur"] or "—", 0) + (r["montant_ttc"] or 0)
            key = r["type_facture"] or "AUTRE"
            par_type[key] = par_type.get(key, 0) + (r["montant_ttc"] or 0)
        total = sum(mensuel)
        return {
            "id": str(ag.id),
            "code": ag.code,
            "libelle": ag.libelle,
            "ville": getattr(ag, "ville", None),
            "adresse": getattr(ag, "adresse", None),
            "annee": annee,
            "total_annee": total,
            "total_n1": sum(precedent),
            "variation_n1_pct": variation_pct(total, sum(precedent)) if sum(precedent) else None,
            "mensuel": mensuel,
            "mensuel_n1": precedent,
            "nb_factures": sum(1 for r in rows if r["statut"] in STATUTS_COMPTES),
            "reste_a_payer": sum(r["reste"] or 0 for r in rows if r["statut"] in STATUTS_OUVERTS),
            "en_retard": sum(1 for r in rows if r["etat_echeance"] == "EN_RETARD"),
            "par_fournisseur": [{"label": k, "montant": v} for k, v in sorted(par_fournisseur.items(), key=lambda x: -x[1])],
            "par_type": [{"code": k, "label": dict(TYPES_FACTURE).get(k, k), "montant": v} for k, v in sorted(par_type.items(), key=lambda x: -x[1])],
            "points": points,
            "factures": rows[:50],
        }

    async def fournisseur_synthese(self, fournisseur_id: uuid.UUID, annee: int | None) -> dict:
        annee = annee or date.today().year
        fr = await self._fournisseur(fournisseur_id)
        filtre = MgAchatFacture.fournisseur_id == fr.id
        if self.scope_agence:
            filtre = and_(filtre, MgAchatFacture.agence_id == self.scope_agence)
        mensuel = await self._montants_mensuels(filtre, annee)
        precedent = await self._montants_mensuels(filtre, annee - 1)
        rows = await self.fetch_rows({"fournisseur_id": fr.id, "annee": annee, "inclure_historique": True})
        contrats = (
            await self.db.execute(
                select(MgContrat)
                .where(MgContrat.fournisseur_id == fr.id, MgContrat.deleted_at.is_(None))
                .order_by(MgContrat.date_debut.desc())
                .limit(50)
            )
        ).scalars().all()
        total = sum(mensuel)
        return {
            "id": str(fr.id),
            "code": fr.code,
            "raison_sociale": fr.raison_sociale,
            "telephone": fr.telephone,
            "email": fr.email,
            "adresse": fr.adresse,
            "is_active": fr.is_active,
            "annee": annee,
            "total_annee": total,
            "total_n1": sum(precedent),
            "variation_n1_pct": variation_pct(total, sum(precedent)) if sum(precedent) else None,
            "mensuel": mensuel,
            "mensuel_n1": precedent,
            "nb_factures": sum(1 for r in rows if r["statut"] in STATUTS_COMPTES),
            "reste_a_payer": sum(r["reste"] or 0 for r in rows if r["statut"] in STATUTS_OUVERTS),
            "points": await self.list_points({"fournisseur_id": fr.id, "annee": annee}),
            "contrats": [
                {
                    "id": str(c.id), "reference": c.reference, "titre": c.titre, "statut": c.statut,
                    "date_debut": _iso(c.date_debut), "date_fin": _iso(c.date_fin), "montant": to_float(c.montant),
                }
                for c in contrats
            ],
            "factures": rows[:50],
        }

    async def factures_du_contrat(self, contrat_id: uuid.UUID) -> dict:
        ct = await self._contrat(contrat_id)
        rows = await self.fetch_rows({"contrat_id": ct.id, "inclure_historique": True}, limit=200)
        comptees = [r for r in rows if r["statut"] in STATUTS_COMPTES]
        return {
            "contrat_id": str(ct.id),
            "nb": len(comptees),
            "total": sum(r["montant_ttc"] or 0 for r in comptees),
            "reste": sum(r["reste"] or 0 for r in rows if r["statut"] in STATUTS_OUVERTS),
            "items": rows,
        }

    # ——— Recherche et référentiels ———

    async def recherche(self, q: str) -> dict:
        q = (q or "").strip()
        if len(q) < 2:
            return {"factures": [], "points": []}
        factures = await self.fetch_rows({"q": q, "inclure_historique": True}, limit=10)
        points = (await self.list_points({"q": q}))[:10]
        return {"factures": factures, "points": points}

    # ——— Profils de facturation (configuration par fournisseur) ———

    async def list_profils(self, *, actifs: bool = True) -> list[dict]:
        stmt = (
            select(MgFacturationProfil, Fournisseur.raison_sociale)
            .join(Fournisseur, Fournisseur.id == MgFacturationProfil.fournisseur_id)
            .order_by(MgFacturationProfil.ordre, MgFacturationProfil.libelle)
        )
        if actifs:
            stmt = stmt.where(MgFacturationProfil.actif.is_(True))
        return [_profil_dict(p, fr) for p, fr in (await self.db.execute(stmt)).all()]

    @staticmethod
    def _valider_champs_profil(champs: dict | None, libelles: dict | None) -> tuple[dict | None, dict | None]:
        if champs is not None:
            inconnus = set(champs) - set(CHAMPS_PROFIL)
            if inconnus or any(v not in ETATS_CHAMP for v in champs.values()):
                raise AppError("Configuration des champs invalide", code="PROFIL_CHAMPS_INVALIDES")
            if champs.get("montant_ttc") == "masque":
                raise AppError("Le montant TTC ne peut pas être masqué", code="PROFIL_CHAMPS_INVALIDES")
        if libelles is not None:
            if set(libelles) - set(CHAMPS_PROFIL):
                raise AppError("Libellés : champ inconnu", code="PROFIL_CHAMPS_INVALIDES")
            libelles = {k: v.strip()[:80] for k, v in libelles.items() if v and v.strip()}
        return champs, libelles

    async def create_profil(self, data: ProfilCreate, user: User) -> dict:
        code = re.sub(r"[^A-Z0-9_]", "_", data.code.strip().upper())
        if await self.db.scalar(select(MgFacturationProfil.id).where(MgFacturationProfil.code == code)):
            raise AppError("Ce code de profil existe déjà", status_code=409, code="PROFIL_CODE_EXISTANT")
        fr = await self._fournisseur(data.fournisseur_id)
        champs, libelles = self._valider_champs_profil(data.champs, data.libelles)
        p = MgFacturationProfil(
            id=uuid.uuid4(),
            code=code,
            libelle=data.libelle.strip(),
            fournisseur_id=fr.id,
            type_facture=(_clean(data.type_facture) or "").upper() or None,
            taux_tva=q2(data.taux_tva) if data.taux_tva is not None else None,
            champs=champs or {},
            libelles=libelles or {},
            description=_clean(data.description),
            actif=True if data.actif is None else data.actif,
            ordre=data.ordre or 0,
            created_by=user.id,
            updated_by=user.id,
        )
        self.db.add(p)
        await self._audit(user, "factures.profil.create", p.id, entity="profil_facturation", after=_profil_dict(p, fr.raison_sociale))
        await self.db.commit()
        return _profil_dict(p, fr.raison_sociale)

    async def update_profil(self, profil_id: uuid.UUID, data: ProfilIn, user: User) -> dict:
        p = await self._profil(profil_id, actif=False)
        champs_set = data.model_fields_set
        before = _profil_dict(p)
        if "fournisseur_id" in champs_set and data.fournisseur_id and data.fournisseur_id != p.fournisseur_id:
            utilise = await self.db.scalar(
                select(func.count()).select_from(MgAchatFacture).where(
                    MgAchatFacture.profil_id == p.id, MgAchatFacture.deleted_at.is_(None)
                )
            )
            if utilise:
                raise AppError("Profil déjà utilisé : le fournisseur n'est plus modifiable", code="PROFIL_UTILISE")
            p.fournisseur_id = (await self._fournisseur(data.fournisseur_id)).id
        champs, libelles = self._valider_champs_profil(
            data.champs if "champs" in champs_set else None, data.libelles if "libelles" in champs_set else None
        )
        if champs is not None:
            p.champs = champs
        if libelles is not None:
            p.libelles = libelles
        if "libelle" in champs_set and data.libelle and data.libelle.strip():
            p.libelle = data.libelle.strip()
        if "type_facture" in champs_set:
            p.type_facture = (_clean(data.type_facture) or "").upper() or None
        if "taux_tva" in champs_set:
            p.taux_tva = q2(data.taux_tva) if data.taux_tva is not None else None
        if "description" in champs_set:
            p.description = _clean(data.description)
        if "actif" in champs_set and data.actif is not None:
            p.actif = data.actif
        if "ordre" in champs_set and data.ordre is not None:
            p.ordre = data.ordre
        p.updated_by = user.id
        fr = await self.db.get(Fournisseur, p.fournisseur_id)
        after = _profil_dict(p, fr.raison_sociale if fr else None)
        await self._audit(user, "factures.profil.update", p.id, entity="profil_facturation", before=before, after=after)
        await self.db.commit()
        return after

    async def referentiels(self) -> dict:
        ag_stmt = select(Agence).where(Agence.is_active.is_(True), Agence.deleted_at.is_(None))
        if self.scope_agence:
            ag_stmt = ag_stmt.where(Agence.id == self.scope_agence)
        agences = (await self.db.execute(ag_stmt.order_by(Agence.libelle))).scalars().all()
        fournisseurs = (
            await self.db.execute(
                select(Fournisseur)
                .where(Fournisseur.deleted_at.is_(None), Fournisseur.is_active.is_(True))
                .order_by(Fournisseur.raison_sociale)
                .limit(1000)
            )
        ).scalars().all()
        pt_stmt = select(MgPointFacturation).where(MgPointFacturation.deleted_at.is_(None))
        if self.scope_agence:
            pt_stmt = pt_stmt.where(MgPointFacturation.agence_id == self.scope_agence)
        points = (await self.db.execute(pt_stmt.order_by(MgPointFacturation.nom))).scalars().all()
        contrats = (
            await self.db.execute(
                select(MgContrat)
                .where(MgContrat.deleted_at.is_(None), MgContrat.statut.notin_(("ANNULE", "ARCHIVE")))
                .order_by(MgContrat.reference.desc())
                .limit(500)
            )
        ).scalars().all()
        return {
            "agences": [{"id": str(a.id), "code": a.code, "libelle": a.libelle} for a in agences],
            "fournisseurs": [{"id": str(f.id), "code": f.code, "libelle": f.raison_sociale} for f in fournisseurs],
            "profils": await self.list_profils(actifs=False),
            "points": [
                {
                    "id": str(p.id), "code": p.code, "nom": p.nom, "type_point": p.type_point,
                    "fournisseur_id": str(p.fournisseur_id), "agence_id": str(p.agence_id) if p.agence_id else None,
                    "contrat_id": str(p.contrat_id) if p.contrat_id else None,
                    "reference_fournisseur": p.reference_fournisseur, "type_facture": p.type_facture,
                    "profil_id": str(p.profil_id) if p.profil_id else None,
                    "periodicite": p.periodicite, "statut": p.statut,
                }
                for p in points
            ],
            "contrats": [
                {"id": str(c.id), "reference": c.reference, "titre": c.titre,
                 "fournisseur_id": str(c.fournisseur_id) if c.fournisseur_id else None}
                for c in contrats
            ],
        }
