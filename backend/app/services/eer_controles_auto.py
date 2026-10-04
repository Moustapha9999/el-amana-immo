"""Contrôles automatiques EER : propositions tracées, jamais une décision.

Chaque contrôle est rattaché à une règle du référentiel (``type_controle`` AUTO_*) ou à une
contrainte déjà définie (profil client, paramètre figé du dossier). Le résultat est écrit
dans ``eer_controles`` (journal) ; l'analyste confirme ensuite élément par élément
(``controler``). Rien n'est inventé : ce qui n'est pas vérifiable automatiquement
(cohérence avec ORION, lisibilité, authenticité) est signalé ``A_VERIFIER``.

Le détail ne contient que des codes, dates et identifiants (pas de nom, NNI, adresse).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.data.eer_referentiel import TYPES_CLIENT
from app.models import EerChecklistRegle, EerControle, EerDossier, EerDossierPartie
from app.services.eer import prefill
from app.services.eer.constantes import Presence, RoleDossier, StatutElement, TypeClient, TypeControle
from app.services.eer.workflow import Etape

OK = "OK"
A_VERIFIER = "A_VERIFIER"
NON_CONFORME = "NON_CONFORME"
MANQUANT = "MANQUANT"


@dataclass
class Constat:
    code: str
    type_controle: str
    resultat: str
    message: str
    item_id: Any = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "type_controle": self.type_controle, "resultat": self.resultat,
                "message": self.message, "item_id": str(self.item_id) if self.item_id else None,
                "detail": self.detail}


def _piece(dp: EerDossierPartie | None):
    if dp is None or not dp.partie.pieces:
        return None
    return dp.partie.pieces[-1]


def _expiration(code: str, item_id, dp: EerDossierPartie | None, a_date: date) -> Constat:
    piece = _piece(dp)
    if piece is None:
        return Constat(code, TypeControle.AUTO_EXPIRATION, MANQUANT, "Aucune pièce d'identité saisie", item_id)
    if piece.date_expiration is None:
        return Constat(code, TypeControle.AUTO_EXPIRATION, A_VERIFIER, "Date d'expiration non renseignée", item_id)
    detail = {"date_expiration": piece.date_expiration.isoformat(), "date_controle": a_date.isoformat()}
    if piece.date_expiration < a_date:
        return Constat(code, TypeControle.AUTO_EXPIRATION, NON_CONFORME, "Pièce d'identité expirée", item_id, detail)
    return Constat(code, TypeControle.AUTO_EXPIRATION, OK, "Pièce en cours de validité", item_id, detail)


def _coherence_piece(code: str, item_id, dp: EerDossierPartie | None) -> list[Constat]:
    piece = _piece(dp)
    constats = []
    if piece and piece.date_delivrance and piece.date_expiration and piece.date_delivrance > piece.date_expiration:
        constats.append(Constat(code, TypeControle.AUTO_COHERENCE, NON_CONFORME,
                                "Date de délivrance postérieure à la date d'expiration", item_id))
    physique = dp.partie.physique if dp else None
    if physique and physique.date_naissance and physique.date_naissance > date.today():
        constats.append(Constat(code, TypeControle.AUTO_COHERENCE, NON_CONFORME,
                                "Date de naissance dans le futur", item_id))
    constats.append(Constat(code, TypeControle.AUTO_COHERENCE, A_VERIFIER,
                            "Cohérence avec le système (ORION) : vérification manuelle (non connecté)", item_id))
    return constats


async def executer(svc, acteur, dossier_id) -> list[Constat]:
    """Exécute les contrôles automatiques et les journalise (version courante du dossier)."""
    d: EerDossier = await svc.charger(dossier_id, verrou=True, acteur=acteur)
    svc._exiger_controle(acteur, d, {Etape.CHECKLIST, Etape.FICHES, Etape.CONTROLES})
    a_date = date.today()
    parties = {dp.id: dp for dp in d.parties}
    client_dp = next(dp for dp in d.parties if dp.role == RoleDossier.CLIENT)
    constats: list[Constat] = []

    for item in sorted(d.items, key=lambda i: (i.ordre, i.regle_code)):
        if item.statut == StatutElement.NON_APPLICABLE:
            continue
        dp = parties.get(item.dossier_partie_id) if item.dossier_partie_id else client_dp
        type_ctrl = await _type_controle(svc, item)
        if type_ctrl == TypeControle.AUTO_EXPIRATION:
            constats.append(_expiration(item.regle_code, item.id, dp, a_date))
        elif type_ctrl == TypeControle.AUTO_COHERENCE:
            constats.extend(_coherence_piece(item.regle_code, item.id, dp))
        elif type_ctrl == TypeControle.AUTO_PRESENCE and item.nature == "DOCUMENT":
            if item.presence is None:
                constats.append(Constat(item.regle_code, type_ctrl, A_VERIFIER, "Présence non pointée", item.id))
            elif item.presence == Presence.ABSENT:
                constats.append(Constat(item.regle_code, type_ctrl, MANQUANT, "Document absent", item.id))
            elif item.document_id is None:
                constats.append(Constat(item.regle_code, type_ctrl, A_VERIFIER,
                                        "Déclaré présent sans pièce GED rattachée", item.id))
            else:
                # Présent ≠ conforme : lisibilité, validité, cohérence restent à contrôler.
                constats.append(Constat(item.regle_code, type_ctrl, A_VERIFIER,
                                        "Pièce rattachée : lisibilité / validité / cohérence à contrôler",
                                        item.id, {"document_id": str(item.document_id)}))

    fiches = await svc.fiches(d.id)
    for code_fiche, champs in fiches.items():
        manquants = prefill.champs_a_completer(champs)
        info = next((i for i in d.items if i.regle_code == "INFOS_CLIENT"), None)
        if manquants:
            constats.append(Constat("CHAMPS_VIDES", TypeControle.AUTO_PRESENCE, MANQUANT,
                                    f"{len(manquants)} champ(s) obligatoire(s) à compléter",
                                    info.id if info and ":" not in code_fiche else None,
                                    {"fiche": code_fiche.split(":")[0], "chemins": sorted(c.chemin for c in manquants)}))

    profil = TYPES_CLIENT[TypeClient(d.type_client_code)]
    if d.risque_lbcft is None:
        constats.append(Constat("RISQUE_NON_EVALUE", TypeControle.AUTO_PRESENCE, MANQUANT,
                                "Risque LBC-FT non évalué", _item(d, "LBCFT_RISQUE")))
    if profil.get("risque_impose") and d.risque_lbcft and d.risque_lbcft != profil["risque_impose"]:
        constats.append(Constat("RISQUE_IMPOSE", TypeControle.AUTO_COHERENCE, NON_CONFORME,
                                f"Risque imposé pour ce type de client : {profil['risque_impose']}",
                                _item(d, "LBCFT_RISQUE"), {"risque": d.risque_lbcft}))
    for dp in d.parties:
        if dp.role not in (RoleDossier.CLIENT, RoleDossier.MANDATAIRE):
            continue
        if dp.ppe and not (dp.ppe_motif or "").strip():
            constats.append(Constat("PPE_MOTIF_ABSENT", TypeControle.AUTO_PRESENCE, MANQUANT,
                                    "PPE déclarée sans motif", _item(d, "PPE_MOTIF"),
                                    {"role": dp.role, "dossier_partie_id": str(dp.id)}))
        if dp.fatca_indice and not (dp.fatca_detail or "").strip():
            constats.append(Constat("FATCA_DETAIL_ABSENT", TypeControle.AUTO_PRESENCE, A_VERIFIER,
                                    "Indice d'américanité sans détail", _item(d, "FATCA_REVUE_KYC"),
                                    {"role": dp.role, "dossier_partie_id": str(dp.id)}))

    if d.type_client_code in (TypeClient.PM_PRIVEE, TypeClient.PM_PUBLIQUE):
        be = await svc.beneficiaires(d.id)
        for p in be.problemes:
            constats.append(Constat(f"BE_{p.code}", TypeControle.AUTO_CALCUL, NON_CONFORME,
                                    "Structure d'actionnariat : " + p.code, _item(d, "ACTIONNARIAT")))
        if be.a_verifier:
            constats.append(Constat("BE_A_VERIFIER", TypeControle.AUTO_CALCUL, A_VERIFIER,
                                    f"{len(be.a_verifier)} détention(s) sans pourcentage", _item(d, "BE_IDENTIFIES")))
        constats.append(Constat("BE_CALCUL", TypeControle.AUTO_CALCUL, OK if be.complet else A_VERIFIER,
                                f"{len(be.beneficiaires)} bénéficiaire(s) effectif(s) au seuil figé du dossier",
                                _item(d, "BE_IDENTIFIES"), {"seuil": str(be.seuil)}))

    for c in constats:
        svc.db.add(EerControle(dossier_id=d.id, item_id=c.item_id, code=c.code, type_controle=c.type_controle,
                               resultat=c.resultat, detail={"message": c.message, **c.detail},
                               version=d.version_courante, execute_par_id=acteur.user.id))
    await svc.db.flush()
    await svc._historique(d, acteur, "CONTROLES_AUTO", details={
        "total": len(constats), "anomalies": sum(1 for c in constats if c.resultat in (NON_CONFORME, MANQUANT))})
    return constats


def _item(d: EerDossier, code: str):
    item = next((i for i in d.items if i.regle_code == code and i.dossier_partie_id is None), None)
    return item.id if item else None


async def _type_controle(svc, item) -> str:
    regle = await svc.db.get(EerChecklistRegle, item.regle_id)
    return regle.type_controle if regle else TypeControle.MANUEL
