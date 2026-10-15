"""Compléments provisoires à l'organigramme BEA de juillet 2024 (structure bancaire classique).

Entités 🟡 « ajout suggéré » : elles ne figurent pas dans l'organigramme officiel et sont chargées
en attendant l'organigramme complet, pour que les modules disposent dès maintenant des services
usuels (achats, archives, back-office, fiscalité…). Chargées une seule fois par la migration
``20261015_org_02`` sous la source ``SUGGESTION_2026_10`` et toujours marquées ``a_confirmer`` :
dans CORE ADMIN → Organigramme, l'administrateur les confirme, les renomme, les déplace ou les
désactive. Les corrections se font là-bas, jamais en modifiant ce fichier.

Chaque bloc est rattaché à une entité officielle existante (``parent``), identifiée par son code.
"""

from __future__ import annotations

from app.data.organigramme_bea_2024 import _e, _p

SOURCE = "SUGGESTION_2026_10"

NOTE_SUGGERE = (
    "Ajout suggéré (structure bancaire classique), absent de l'organigramme officiel de juillet 2024 : "
    "à valider avec l'organigramme réel — confirmer, renommer, déplacer ou désactiver."
)
NOTE_CAISSE = (
    NOTE_SUGGERE + " Niveau (service ou section du Service Trésorerie) à confirmer."
)


def _s(code: str, type_entite: str, libelle: str, *, enfants: list | None = None,
       postes: list | None = None, note: str = NOTE_SUGGERE) -> dict:
    return _e(code, type_entite, libelle, enfants=enfants,
              postes=[{**p, "a_confirmer": True, "note": p["note"] or NOTE_SUGGERE} for p in (postes or [])],
              note=note)


# (code de l'entité officielle parente, entités suggérées à y rattacher)
SUGGESTIONS: list[tuple[str, list[dict]]] = [
    ("CA", [
        _s("CA-SEC", "CELLULE", "Secrétariat du Conseil d'Administration"),
    ]),
    ("DG", [
        _s("COMITE-ALCO", "COMITE", "Comité ALCO (Gestion Actif / Passif)"),
        _s("COMITE-CHARIA", "COMITE", "Comité Charia",
           note=NOTE_SUGGERE + " Uniquement si la banque exerce une activité de finance islamique."),
        _s("DG-SEC", "SERVICE", "Secrétariat de Direction / Courrier DG", postes=[_p("Secrétaire de Direction")]),
    ]),
    # Conformité, Organisation, Contrôle Permanent & Audit Interne
    ("DCOAI", [
        _s("DCOAI-ORG", "SERVICE", "Service Organisation & Procédures"),
        _s("DCOAI-REG", "SERVICE", "Service Reporting Réglementaire (Banque Centrale)"),
    ]),
    ("DCOAI-CONF", [
        _s("DCOAI-CONF-LCB", "CELLULE", "Cellule LCB-FT"),
        _s("DCOAI-CONF-KYC", "CELLULE", "Cellule Déclaration de Soupçon / KYC"),
    ]),
    # Direction des Ressources
    ("DRES-DOI", [
        _s("DRES-DOI-SWIFT", "SERVICE", "Service Transferts Internationaux (SWIFT)"),
        _s("DRES-DOI-CHG", "SERVICE", "Service Change"),
    ]),
    ("DRES-DOD", [
        _s("DRES-DOD-BO", "SERVICE", "Service Back-Office / Traitement des Opérations"),
        _s("DRES-DOD-CPS", "SERVICE", "Service Compensation & Règlement"),
        _s("DRES-DOD-PTF", "SERVICE", "Service Portefeuille / Effets"),
    ]),
    ("DRES-RHMG", [
        _s("DRES-RHMG-ACH", "SERVICE", "Service Achats & Logistique"),
        _s("DRES-RHMG-SEC", "SERVICE", "Service Sécurité & Sûreté des Locaux"),
        _s("DRES-RHMG-ARC", "SERVICE", "Service Courrier & Archives"),
        _s("DRES-RHMG-PARC", "SERVICE", "Service Parc Automobile / Maintenance"),
    ]),
    # Direction Commerciale
    ("DCOM", [
        _s("DCOM-RES", "DEPARTEMENT", "Département Réseau d'Agences", postes=[
            _p("Chef d'agence", responsable=True), _p("Caissier d'agence"),
        ]),
        _s("DCOM-RCL", "SERVICE", "Service Relations Clients / Réclamations"),
        _s("DCOM-KYC", "SERVICE", "Service Ouverture de Comptes & KYC"),
    ]),
    ("DCOM-ENT", [
        _s("DCOM-ENT-SCE", "SERVICE", "Service Suivi des Comptes Entreprises"),
    ]),
    ("DCOM-RET", [
        _s("DCOM-RET-DIG", "SERVICE", "Service Banque Digitale / Mobile"),
        _s("DCOM-RET-DOM", "SERVICE", "Service Domiciliation de Salaires"),
    ]),
    # Direction Risque, Recouvrement & Juridique
    ("DRRJ", [
        _s("DRRJ-RO", "SERVICE", "Service Risques Opérationnels"),
    ]),
    ("DRRJ-EA", [
        _s("DRRJ-EA-NOT", "SERVICE", "Service Notation / Scoring"),
    ]),
    ("DRRJ-REC", [
        _s("DRRJ-REC-AMI", "SERVICE", "Service Recouvrement Amiable"),
    ]),
    ("DRRJ-JUR", [
        _s("DRRJ-JUR-CC", "SERVICE", "Service Contrats & Conventions"),
        _s("DRRJ-JUR-GDC", "SERVICE", "Service Gestion des Dossiers Contentieux"),
    ]),
    # Département Comptable & Financier
    ("DCF", [
        _s("DCF-FISC", "SERVICE", "Service Fiscalité"),
        _s("DCF-REP", "SERVICE", "Service Reporting Financier & États Réglementaires"),
    ]),
    ("DCF-CG", [
        _s("DCF-CG-FI", "SECTION", "Section Comptabilité Fournisseurs / Immobilisations"),
    ]),
    ("DCF-TRES", [
        _s("DCF-TRES-ESP", "SECTION", "Caisse & Gestion des Espèces (agences et GAB)", note=NOTE_CAISSE),
        _s("DCF-TRES-POS", "SECTION", "Section Suivi de la Trésorerie / Position de Change"),
    ]),
    # Département Informatique
    ("DSI", [
        _s("DSI-DEV", "SERVICE", "Service Études & Développement Applicatif"),
        _s("DSI-DATA", "SERVICE", "Service Data / BI / Reporting"),
        _s("DSI-RES", "SERVICE", "Service Réseaux & Télécoms"),
        _s("DSI-PROJ", "SERVICE", "Service Gestion de Projets SI"),
    ]),
    ("DMKT", [
        _s("DMKT-PROD", "SERVICE", "Service Produits & Offres"),
        _s("DMKT-ETU", "SERVICE", "Service Études de Marché / Relation Client"),
    ]),
    ("DCG", [
        _s("DCG-ANA", "SERVICE", "Service Comptabilité Analytique / Rentabilité"),
    ]),
    ("DWA", [
        _s("DWA-SUP", "SERVICE", "Service Support & Relation Client (agents, marchands)"),
        _s("DWA-CONF", "SERVICE", "Service Conformité / Surveillance des Transactions"),
    ]),
]


def aplatir_suggestions():
    """Chaque entité suggérée avec son parent ; l'ordre continue après les entités officielles."""
    for parent_code, noeuds in SUGGESTIONS:
        for n in noeuds:
            yield {**n, "parent_code": parent_code}
            for enfant in n["enfants"]:
                yield {**enfant, "parent_code": n["code"]}
