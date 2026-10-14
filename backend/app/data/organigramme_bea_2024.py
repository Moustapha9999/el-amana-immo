"""Organigramme officiel BEA — juillet 2024 (« Organigramme présentation BEA- juillet 2024.pdf »).

Base initiale du référentiel organisationnel central (table ``departements``). Chargé une seule
fois par la migration ``20261015_org_01`` : les corrections ultérieures se font dans CORE ADMIN
(Organigramme), jamais en modifiant ce fichier.

Aucun nom d'employé : seulement des entités et des postes. Ce qui n'est pas lisible sans
ambiguïté dans le document est importé avec ``a_confirmer`` et une note expliquant le doute.
"""

from __future__ import annotations

SOURCE = "ORGANIGRAMME_2024_07"

# Note commune aux mentions « (2) » du document : effectif, doublon de service ou renvoi ?
NOTE_MENTION_2 = "Mention « (2) » dans l'organigramme de juillet 2024 : signification à confirmer (effectif, renvoi ou doublon)."
NOTE_MONETIQUE = (
    "Service Monétique présent à deux endroits (Département Opérations Domestiques et Département "
    "Informatique) : un seul service, ou deux services distincts ? À confirmer."
)
NOTE_NIVEAU = "Niveau hiérarchique non précisé dans l'organigramme (pas de mention « Serv. ») : à confirmer."


def _e(code: str, type_entite: str, libelle: str, *, enfants: list | None = None, postes: list | None = None,
       note: str | None = None) -> dict:
    return {
        "code": code, "type_entite": type_entite, "libelle": libelle, "enfants": enfants or [],
        "postes": postes or [], "a_confirmer": note is not None, "note": note,
    }


def _p(intitule: str, *, responsable: bool = False, note: str | None = None) -> dict:
    return {"intitule": intitule, "est_responsable": responsable, "a_confirmer": note is not None, "note": note}


ORGANIGRAMME: list[dict] = [
    _e("CA", "CONSEIL", "Conseil d'Administration", enfants=[
        _e("COMITE-AUDIT", "COMITE", "Comité d'Audit Interne",
           note="Rattachement au Conseil d'Administration ou à la Direction Générale à confirmer."),
        _e("COMITE-RISQUE", "COMITE", "Comité de Risque",
           note="Rattachement au Conseil d'Administration ou à la Direction Générale à confirmer."),
        _e("DG", "DIRECTION_GENERALE", "Direction Générale", postes=[
            _p("Directeur Général", responsable=True),
            _p("Administrateur, Auditeur", note="Poste proche de la Direction Générale : rattachement exact à confirmer."),
            _p("Chargé de mission", note="Poste proche de la Direction Générale : rattachement exact à confirmer."),
        ], enfants=[
            _e("CODIR", "COMITE", "Comité de Direction",
               note="Positionné entre le Conseil et la Direction Générale dans le document : rattachement à confirmer."),
            _e("COMITE-CREDIT", "COMITE", "Comité de Crédit",
               note="Rattachement au Conseil d'Administration ou à la Direction Générale à confirmer."),
            _e("DG-CASH", "CELLULE", "Cash Payment",
               note="Unité rattachée à la Direction Générale : niveau (direction, département, cellule) à confirmer."),
            _e("DG-QUALITE", "CELLULE", "Qualité",
               note="Unité rattachée à la Direction Générale : niveau (direction, département, cellule) à confirmer."),
            _e("DRES", "DIRECTION", "Direction des Ressources", postes=[
                _p("Directeur des Ressources", responsable=True),
            ], enfants=[
                _e("DRES-DOI", "DEPARTEMENT", "Département Opérations Internationales", enfants=[
                    _e("DRES-DOI-SDM", "SERVICE", "Salle des Marchés", postes=[
                        _p("Trader"), _p("Trésorier Salle des Marchés"),
                    ]),
                    _e("DRES-DOI-TRADE", "SERVICE", "Service Trade"),
                    _e("DRES-DOI-DOCS", "SERVICE", "Service Opérations Documentaires"),
                ]),
                _e("DRES-DOD", "DEPARTEMENT", "Département Opérations Domestiques", enfants=[
                    _e("DRES-DOD-MPD", "SERVICE", "Service Moyens de Paiement Domestiques", note=NOTE_MENTION_2),
                    _e("DRES-DOD-MEPCD", "SERVICE", "Service Mise en place Concours Directs"),
                    _e("DRES-DOD-AG", "SERVICE", "Service Actes & Garanties", note=NOTE_MENTION_2),
                    _e("DRES-DOD-MEPES", "SERVICE", "Service Mise en place Engagements par Signature"),
                    _e("DRES-DOD-MONET", "SERVICE", "Service Monétique", note=NOTE_MONETIQUE),
                ]),
                _e("DRES-RHMG", "DEPARTEMENT", "Département RH / Moyens Généraux", enfants=[
                    _e("DRES-RHMG-GC", "SERVICE", "Service Gestion Courante"),
                    _e("DRES-RHMG-DCH", "SERVICE", "Service Développement du Capital Humain"),
                    _e("DRES-RHMG-MG", "SERVICE", "Service Moyens Généraux"),
                ]),
            ]),
            _e("DWA", "DIRECTION", "Direction du Wallet Amanty", postes=[
                _p("Directeur Amanty", responsable=True),
            ], enfants=[
                _e("DWA-RD", "SERVICE", "Service Réseau de Distribution"),
                _e("DWA-OPS", "SERVICE", "Service des Opérations"),
                _e("DWA-COM", "SERVICE", "Service Commercial"),
            ]),
            _e("DCOM", "DIRECTION", "Direction Commerciale", postes=[
                _p("Directeur Commercial", responsable=True),
                _p("Responsable suivi des engagements",
                   note="Rattachement direct à la Direction Commerciale ou à un département : à confirmer."),
                _p("Responsable suivi de la production",
                   note="Rattachement direct à la Direction Commerciale ou à un département : à confirmer."),
            ], enfants=[
                _e("DCOM-ENT", "DEPARTEMENT", "Département Commercial (Entreprises)", postes=[
                    _p("Chargé d'Affaires Entreprises"), _p("Attaché Relation Clientèle"),
                    _p("Agent d'Accueil"), _p("Caissier"),
                ]),
                _e("DCOM-RET", "DEPARTEMENT", "Département Retail (Particuliers)", postes=[
                    _p("Conseiller Clientèle"), _p("Agent d'Accueil"), _p("Caissier"),
                ]),
            ]),
            _e("DRRJ", "DIRECTION", "Direction Risque, Recouvrement & Juridique", postes=[
                _p("Directeur Risque, Recouvrement & Juridique", responsable=True),
            ], enfants=[
                _e("DRRJ-EA", "DEPARTEMENT", "Département Études & Analyses", enfants=[
                    _e("DRRJ-EA-ANA", "SERVICE", "Service Analyses", note=NOTE_MENTION_2),
                    _e("DRRJ-EA-SE", "SERVICE", "Service Suivi des Engagements"),
                    _e("DRRJ-EA-GG", "SERVICE", "Service Gestion des Garanties"),
                ]),
                _e("DRRJ-REC", "DEPARTEMENT", "Département Recouvrement", enfants=[
                    _e("DRRJ-REC-RC", "SERVICE", "Service Relations Clients"),
                    _e("DRRJ-REC-SC", "SERVICE", "Service Suivi Contentieux"),
                ]),
                _e("DRRJ-JUR", "DEPARTEMENT", "Département Juridique & Contentieux", enfants=[
                    _e("DRRJ-JUR-EJ", "SERVICE", "Service Études Juridiques"),
                ]),
            ]),
            _e("DSI", "DEPARTEMENT", "Département Informatique", postes=[
                _p("Chef Département Informatique", responsable=True),
            ], note=(
                "Département rattaché directement à la Direction Générale dans le document : "
                "niveau (département ou direction) et rattachement à confirmer."
            ), enfants=[
                _e("DSI-PROD", "SERVICE", "Service Production, Administration Système & Bases de Données", enfants=[
                    _e("DSI-PROD-PRD", "SECTION", "Section Production"),
                    _e("DSI-PROD-EXP", "SECTION", "Section Exploitation"),
                ]),
                _e("DSI-INFRA", "SERVICE", "Service Infrastructure & Support Technique", enfants=[
                    _e("DSI-INFRA-SUP", "SECTION", "Section Support"),
                    _e("DSI-INFRA-MNT", "SECTION", "Section Maintenance"),
                ]),
                _e("DSI-SSI", "SERVICE", "Service Sécurité des Systèmes d'Information"),
                _e("DSI-MONET", "SERVICE", "Service Monétique", postes=[_p("Responsable GAB")], note=NOTE_MONETIQUE),
            ]),
            _e("DCF", "DEPARTEMENT", "Département Comptable & Financier", postes=[
                _p("Chef Département Comptable & Financier", responsable=True),
                _p("Contrôleur de Gestion"),
                _p("Analyste Financier"),
            ], note=(
                "Département rattaché directement à la Direction Générale dans le document : "
                "niveau (département ou direction) et rattachement à confirmer."
            ), enfants=[
                _e("DCF-CG", "SERVICE", "Service Comptabilité Générale", enfants=[
                    _e("DCF-CG-RAP", "SECTION", "Section Rapprochement"),
                ]),
                _e("DCF-TRES", "SERVICE", "Service Trésorerie", enfants=[
                    _e("DCF-TRES-CC", "SECTION", "Caisse Centrale"),
                ]),
            ]),
            _e("DMKT", "DIRECTION", "Direction Marketing", postes=[
                _p("Directeur Marketing", responsable=True),
            ], enfants=[
                _e("DMKT-COM", "SERVICE", "Communication et Publicité", note=NOTE_NIVEAU),
                _e("DMKT-ANA", "SERVICE", "Analyse et Stratégie Marketing", note=NOTE_NIVEAU),
            ]),
            _e("DCG", "DIRECTION", "Direction du Contrôle de Gestion", postes=[
                _p("Directeur du Contrôle de Gestion", responsable=True),
            ], enfants=[
                _e("DCG-BUD", "SERVICE", "Suivi Budgétaire", note=NOTE_NIVEAU),
                _e("DCG-PERF", "SERVICE", "Analyses de Performances et Reporting", note=NOTE_NIVEAU),
            ]),
            _e("DCOAI", "DIRECTION", "Direction Conformité, Organisation, Contrôle Permanent & Audit Interne", enfants=[
                _e("DCOAI-AUD", "DEPARTEMENT", "Département Audit", postes=[
                    _p("Auditeur"), _p("Inspecteur"),
                ]),
                _e("DCOAI-CONF", "SERVICE", "Conformité", postes=[
                    _p("Responsable Conformité", responsable=True), _p("Chargé de conformité"),
                ], note=NOTE_NIVEAU),
                _e("DCOAI-CP", "SERVICE", "Contrôle Permanent", postes=[
                    _p("Responsable Contrôle Permanent", responsable=True), _p("Contrôleur"),
                ], note=NOTE_NIVEAU),
            ]),
        ]),
    ]),
]

# Agences physiques explicitement placées dans l'organigramme (page 5). Les autres agences
# restent non rattachées : à compléter par la banque dans CORE ADMIN.
RATTACHEMENTS_AGENCES: dict[str, str] = {
    "00005": "DCOM-ENT",  # Agence Centrale Entreprises → Département Commercial (Entreprises)
    "00001": "DCOM-RET",  # Agence Centrale Particuliers → Département Retail (Particuliers)
}


def aplatir(noeuds: list[dict] | None = None, parent: str | None = None, profondeur: int = 0):
    """Parcours en largeur d'abord par branche : chaque parent précède ses enfants."""
    for ordre, n in enumerate(noeuds if noeuds is not None else ORGANIGRAMME, start=1):
        yield {**n, "parent_code": parent, "ordre": ordre, "profondeur": profondeur}
        yield from aplatir(n["enfants"], n["code"], profondeur + 1)
