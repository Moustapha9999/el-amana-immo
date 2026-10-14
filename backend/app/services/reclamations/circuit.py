"""Moteur du circuit : le statut n'évolue que par ces actions (jamais par un PATCH).

Quatre étapes : Réception → Affectation → Traitement → Clôture.
- Réception : enregistrement (agence, service, SR) puis qualification par le Service Réclamations ;
- Affectation : le SR transmet au service concerné ;
- Traitement : le service analyse et transmet son retour au SR ;
- Clôture : le SR examine le retour (renvoi possible), enregistre la réponse envoyée au client
  puis clôture. Seul le Service Réclamations central clôture.
Les événements détaillés (retour reçu, renvoi, réponse envoyée…) vivent dans l'historique
append-only, pas dans les étapes.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reclamation, ReclamationAffectation, ReclamationDocument, ReclamationReponse
from app.services.reclamations import constantes as C
from app.services.reclamations import suppression
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.delais import actualiser, appliquer, echeance_service
from app.services.reclamations.dossiers import (
    Contexte,
    _evenement,
    _liee,
    actions as actions_base,
    charger,
    classer,
    detail,
)
from app.services.reclamations.notifier import destinataires_sr, membres_unite, notifier
from app.services.reclamations.outils import auditer, conflit, erreur, iso, maintenant, texte_long

AVANT_AFFECTATION = frozenset({"A_QUALIFIER", "A_AFFECTER", "REOUVERTE"})
# Seules actions conservées sur un dossier supprimé (corbeille).
LECTURE_SEULE = frozenset({"documents_voir", "documents_telecharger"})


def _ouvert(r: Reclamation) -> None:
    if r.archivee_le:
        raise conflit("Dossier archivé", "DOSSIER_ARCHIVE")
    if r.statut in C.STATUTS_TERMINAUX:
        raise conflit("Dossier terminé : action impossible", "DOSSIER_TERMINE")


def _revision(r: Reclamation, data: dict) -> None:
    if data.get("revision") is not None and data["revision"] != r.revision:
        raise conflit("Le dossier a été modifié entre-temps : rechargez-le", "CONFLIT_REVISION",
                      revision=r.revision)


def _motif(data: dict, obligatoire: bool = True) -> str | None:
    m = texte_long(data.get("motif"))
    if obligatoire and not m:
        raise erreur("Le motif de l'action est obligatoire", "MOTIF_OBLIGATOIRE")
    return m


def service_central(s: ReclamationsScope) -> bool:
    """Service Réclamations central (membre de l'unité SR) ; l'administrateur du module le supplée."""
    return s.membre_service_central or s.peut("reclamations.admin")


async def _appliquer(db: AsyncSession, s: ReclamationsScope, r: Reclamation, *,
                     statut: str, type_evenement: str, commentaire: str | None = None,
                     donnees: dict | None = None, unite_id: uuid.UUID | None = None,
                     affectation_id: uuid.UUID | None = None, reponse_id: uuid.UUID | None = None,
                     destinataires: set[uuid.UUID] | None = None, titre: str | None = None) -> None:
    avant_s, avant_e = r.statut, r.etape
    r.statut, r.etape = statut, C.ETAPE_DU_STATUT[statut]
    r.revision += 1
    r.updated_by_id = s.user_id
    await actualiser(db, r)
    ev = _evenement(r, s, type_evenement, statut_avant=avant_s, etape_avant=avant_e,
                    unite_id=unite_id, commentaire=commentaire, donnees=donnees or {})
    ev.affectation_id = affectation_id
    ev.reponse_id = reponse_id
    db.add(ev)
    await db.flush()
    await auditer(db, s, f"reclamations.{type_evenement.lower()}", C.GED_ENTITE, r.id,
                  before={"statut": avant_s, "etape": avant_e},
                  after={"statut": r.statut, "etape": r.etape, **(donnees or {})})
    if destinataires and titre:
        await notifier(db, s, r, destinataires=destinataires, titre=titre,
                       message=f"{r.reference} — {C.STATUT_LIBELLES.get(statut, statut)}")


def actions(s: ReclamationsScope, r: Reclamation, *,
            a: ReclamationAffectation | None = None,
            rep: ReclamationReponse | None = None) -> dict[str, bool]:
    base = actions_base(s, r)
    ouvert = r.statut not in C.STATUTS_TERMINAUX and not r.archivee_le
    service = s.membre_de(r.unite_traitement_id) or s.peut("reclamations.scope.all")
    avant = ouvert and r.statut in AVANT_AFFECTATION
    base.update({
        "qualifier": avant and s.peut("reclamations.qualify"),
        "affecter": avant and s.peut("reclamations.assign"),
        "traiter_interne": avant and s.peut("reclamations.qualify"),
        "retourner": ouvert and r.statut == "EN_TRAITEMENT" and a is not None
                     and s.peut("reclamations.treat") and service,
        "evaluer": ouvert and r.statut == "RETOUR_RECU" and s.peut("reclamations.review"),
        "enregistrer_reponse": ouvert and r.statut == "A_CLOTURER" and s.peut("reclamations.response.send"),
        "cloturer": ouvert and r.statut == "A_CLOTURER" and bool(rep and rep.statut == "ENVOYEE")
                    and s.peut("reclamations.close") and service_central(s),
        "refuser": avant and s.peut("reclamations.reject"),
        "annuler": avant and s.peut("reclamations.cancel"),
        "rouvrir": r.statut in {"CLOTUREE", "REJETEE"} and not r.archivee_le and s.peut("reclamations.reopen"),
        "archiver": r.statut in C.STATUTS_TERMINAUX and not r.archivee_le and s.peut("reclamations.archive"),
        "gerer_service": s.responsable_de(r.unite_traitement_id) or s.peut("reclamations.service.manage"),
    })
    if r.supprimee_le:
        base = {k: v and k in LECTURE_SEULE for k, v in base.items()}
    return base


def _aff_dict(a: ReclamationAffectation, ctx: Contexte, noms: dict) -> dict:
    return {
        "id": str(a.id), "numero": a.numero, "statut": a.statut,
        "statut_libelle": C.STATUT_AFFECTATION_LIBELLES.get(a.statut),
        "unite": (ctx.unite(a.unite_destinataire_id) or {}).get("libelle"),
        "unite_id": str(a.unite_destinataire_id),
        "emetteur": (ctx.unite(a.unite_emettrice_id) or {}).get("libelle"),
        "transmis_le": iso(a.transmis_le), "transmis_par": noms.get(a.transmis_par_id),
        "motif_transfert": a.motif_transfert, "instructions": a.instructions,
        "echeance_service": iso(a.echeance_service),
        "recu_le": iso(a.recu_le), "recu_par": noms.get(a.recu_par_id),
        "responsable": noms.get(a.responsable_id),
        "analyse": a.analyse, "actions_menees": a.actions_menees, "conclusion": a.conclusion,
        "decision_proposee": a.decision_proposee,
        "decision_proposee_libelle": C.RESULTAT_LIBELLES.get(a.decision_proposee or ""),
        "retour_le": iso(a.retour_le), "retour_par": noms.get(a.retour_par_id),
        "evaluation": a.evaluation, "evaluation_libelle": C.EVALUATION_LIBELLES.get(a.evaluation or ""),
        "evaluation_commentaire": a.evaluation_commentaire, "evalue_le": iso(a.evalue_le),
        "evalue_par": noms.get(a.evalue_par_id), "revision": a.revision,
    }


def _rep_dict(p: ReclamationReponse, ctx: Contexte, noms: dict) -> dict:
    return {
        "id": str(p.id), "numero": p.numero, "statut": p.statut,
        "statut_libelle": C.STATUT_REPONSE_LIBELLES.get(p.statut),
        "objet": p.objet, "contenu": p.contenu, "resultat": p.resultat,
        "resultat_libelle": C.RESULTAT_LIBELLES.get(p.resultat or ""),
        "canal_envoi": ctx.lib(p.canal_envoi_id),
        "canal_envoi_id": str(p.canal_envoi_id) if p.canal_envoi_id else None,
        "destinataire": p.destinataire, "redige_par": noms.get(p.redige_par_id),
        "envoye_le": iso(p.envoye_le), "envoye_par": noms.get(p.envoye_par_id),
        "reference_envoi": p.reference_envoi, "revision": p.revision,
    }


async def _pieces_circuit(db: AsyncSession, r: Reclamation) -> tuple[
        list[ReclamationAffectation], ReclamationAffectation | None,
        list[ReclamationReponse], ReclamationReponse | None, bool]:
    affs = list((await db.scalars(select(ReclamationAffectation).where(
        ReclamationAffectation.reclamation_id == r.id).order_by(ReclamationAffectation.numero))).all())
    courante = next((a for a in reversed(affs) if a.statut != "ANNULEE"), None)
    reps = list((await db.scalars(select(ReclamationReponse).where(
        ReclamationReponse.reclamation_id == r.id).order_by(ReclamationReponse.numero))).all())
    courante_r = next((p for p in reversed(reps) if p.statut != "ANNULEE"), None)
    preuve = bool(await db.scalar(select(func.count()).select_from(ReclamationDocument).where(
        ReclamationDocument.reclamation_id == r.id, ReclamationDocument.categorie == "PREUVE_ENVOI")))
    return affs, courante, reps, courante_r, preuve


async def fiche(db: AsyncSession, s: ReclamationsScope, r: Reclamation, ctx: Contexte | None = None) -> dict:
    ctx = ctx or await Contexte.charger(db)
    affs, courante, reps, courante_r, preuve = await _pieces_circuit(db, r)
    from app.services.reclamations.outils import noms_utilisateurs
    noms = await noms_utilisateurs(db, {
        r.created_by_id, r.updated_by_id, r.gestionnaire_id, r.responsable_traitement_id, r.cloture_par_id,
        r.supprimee_par_id,
        *(x for a in affs for x in (a.transmis_par_id, a.recu_par_id, a.responsable_id, a.retour_par_id,
                                    a.evalue_par_id)),
        *(x for p in reps for x in (p.redige_par_id, p.envoye_par_id)),
    })
    d = await detail(db, s, r, ctx)
    d["affectations"] = [_aff_dict(a, ctx, noms) for a in affs]
    d["affectation_courante"] = _aff_dict(courante, ctx, noms) if courante else None
    d["reponses"] = [_rep_dict(p, ctx, noms) for p in reps]
    d["reponse_courante"] = _rep_dict(courante_r, ctx, noms) if courante_r else None
    d["preuve_envoi"] = preuve
    d["cloture_par"] = noms.get(r.cloture_par_id) if r.cloture_par_id else None
    d["actions"] = actions(s, r, a=courante, rep=courante_r)
    habilite = s.peut(suppression.PERMISSION)
    raisons = (await suppression.blocages(db, [r]))[r.id] if habilite else []
    d["actions"]["supprimer"] = habilite and not r.supprimee_le and not raisons
    d["actions"]["restaurer"] = habilite and bool(r.supprimee_le)
    d["suppression"] = {
        "blocages": raisons, "supprimee_le": iso(r.supprimee_le), "motif": r.motif_suppression,
        "supprimee_par": noms.get(r.supprimee_par_id) if r.supprimee_par_id else None,
    }
    return d


async def _charger(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> Reclamation:
    r = await charger(db, s, rid, verrou=True)
    _revision(r, data)
    return r


def _prise_en_compte_sr(r: Reclamation, ctx: Contexte) -> None:
    """Première intervention du SR : date de réception SR et unité de suivi, si pas encore posées."""
    now = maintenant()
    if r.date_reception_sr is None:
        r.date_reception_sr = max(now, r.date_premiere_reception)
    if r.unite_suivi_id is None and ctx.service_central():
        r.unite_suivi_id = ctx.service_central().id


# ------------------------------------------------------------------ 1. Réception
async def qualifier(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.qualify")
    if r.statut not in AVANT_AFFECTATION:
        raise conflit("Ce dossier n'est plus à qualifier", "ACTION_INVALIDE")
    ctx = await Contexte.charger(db)
    motif_saisi = data.get("motif_id") is not None or data.get("motif_autre") is not None
    sous_saisi = data.get("sous_motif_id") is not None or data.get("sous_motif_autre") is not None
    classement = classer(
        ctx, data.get("type_id") or r.type_id,
        data.get("motif_id") if motif_saisi else r.motif_id,
        data.get("sous_motif_id") if (sous_saisi or motif_saisi) else r.sous_motif_id,
        data.get("motif_autre") if motif_saisi else r.motif_autre,
        data.get("sous_motif_autre") if (sous_saisi or motif_saisi) else r.sous_motif_autre,
        actuel=r)
    if not classement["type_id"]:
        raise erreur("Le type de réclamation est obligatoire pour qualifier", "TYPE_OBLIGATOIRE")
    for k, v in classement.items():
        setattr(r, k, v)
    if data.get("priorite"):
        r.priorite = data["priorite"]
    if data.get("gestionnaire_id"):
        r.gestionnaire_id = data["gestionnaire_id"]
    _prise_en_compte_sr(r, ctx)
    r.gestionnaire_id = r.gestionnaire_id or s.user_id
    r.date_qualification = maintenant()
    await appliquer(db, r, forcer=True)
    await _appliquer(db, s, r, statut="A_AFFECTER", type_evenement="QUALIFICATION",
                     commentaire=texte_long(data.get("motif")),
                     donnees={"type": ctx.lib(classement["type_id"]),
                              "motif": ctx.lib(classement["motif_id"]) or classement["motif_autre"]})
    return await fiche(db, s, r, ctx)


# ---------------------------------------------------------------- 2. Affectation
async def _nouvelle_affectation(db: AsyncSession, s: ReclamationsScope, r: Reclamation, ctx: Contexte,
                                data: dict, *, parent: ReclamationAffectation | None = None
                                ) -> ReclamationAffectation:
    uid = data.get("unite_id") or data.get("unite_destinataire_id")
    unite = ctx.unites.get(uid)
    if unite is None or not unite.actif:
        raise erreur("Service destinataire introuvable ou inactif", "UNITE_INCONNUE")
    if unite.est_service_reclamations:
        raise erreur("Affectez un service métier, pas le Service Réclamations", "UNITE_INVALIDE")
    n = (await db.scalar(select(func.coalesce(func.max(ReclamationAffectation.numero), 0)).where(
        ReclamationAffectation.reclamation_id == r.id))) + 1
    now = maintenant()
    a = ReclamationAffectation(
        reclamation_id=r.id, numero=n, parent_id=parent.id if parent else None,
        unite_emettrice_id=(ctx.service_central().id if ctx.service_central() else None),
        unite_destinataire_id=unite.id, statut="TRANSMISE", transmis_le=now, transmis_par_id=s.user_id,
        motif_transfert=texte_long(data.get("motif_transfert") or data.get("motif")),
        instructions=texte_long(data.get("instructions")),
        responsable_id=data.get("responsable_id"),
        echeance_service=await echeance_service(db, r, now),
    )
    db.add(a)
    await db.flush()
    r.unite_traitement_id = unite.id
    r.responsable_traitement_id = data.get("responsable_id")
    r.affectation_courante_id = a.id
    r.date_transmission = now
    return a


async def affecter(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.assign")
    if r.statut not in AVANT_AFFECTATION:
        raise conflit("Ce dossier ne peut pas être affecté dans cet état", "ACTION_INVALIDE")
    if not r.type_id:
        raise erreur("Qualifiez le dossier (type) avant de l'affecter", "TYPE_OBLIGATOIRE")
    ctx = await Contexte.charger(db)
    _prise_en_compte_sr(r, ctx)
    if r.date_qualification is None:
        r.date_qualification = maintenant()
    a = await _nouvelle_affectation(db, s, r, ctx, data)
    dest = await membres_unite(db, a.unite_destinataire_id)
    await _appliquer(db, s, r, statut="EN_TRAITEMENT", type_evenement="AFFECTATION",
                     commentaire=a.motif_transfert, unite_id=a.unite_destinataire_id, affectation_id=a.id,
                     donnees={"service": ctx.unites[a.unite_destinataire_id].libelle},
                     destinataires=dest, titre="Réclamation à traiter")
    return await fiche(db, s, r, ctx)


async def traiter_interne(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    """Le SR traite lui-même le dossier : pas d'affectation, passage direct à la clôture."""
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.qualify")
    if r.statut not in AVANT_AFFECTATION:
        raise conflit("Le traitement interne n'est possible qu'avant affectation", "ACTION_INVALIDE")
    if not r.type_id:
        raise erreur("Qualifiez le dossier (type) avant de le traiter", "TYPE_OBLIGATOIRE")
    ctx = await Contexte.charger(db)
    _prise_en_compte_sr(r, ctx)
    analyse = _motif(data)
    await _appliquer(db, s, r, statut="A_CLOTURER", type_evenement="TRAITEMENT_INTERNE",
                     commentaire=analyse, donnees={"analyse": analyse})
    return await fiche(db, s, r, ctx)


# ------------------------------------------------------------------ 3. Traitement
async def retourner(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.treat")
    if r.statut != "EN_TRAITEMENT":
        raise conflit("Le dossier n'est pas en traitement", "ACTION_INVALIDE")
    if not (s.membre_de(r.unite_traitement_id) or s.peut("reclamations.scope.all")):
        raise erreur("Ce dossier n'est pas affecté à votre service", "HORS_PERIMETRE", 403)
    _, courante, *_ = await _pieces_circuit(db, r)
    if courante is None or courante.statut not in {"TRANSMISE", "RECUE", "EN_TRAITEMENT"}:
        raise conflit("Fiche de traitement introuvable", "ACTION_INVALIDE")
    analyse, conclusion = texte_long(data.get("analyse")), texte_long(data.get("conclusion"))
    if not analyse or not conclusion:
        raise erreur("Analyse et conclusion sont obligatoires", "CHAMPS_OBLIGATOIRES")
    now = maintenant()
    if courante.recu_le is None:
        courante.recu_le = max(now, courante.transmis_le)
        courante.recu_par_id = s.user_id
        r.date_reception_service = courante.recu_le
    if not courante.responsable_id:
        courante.responsable_id = s.user_id
    courante.analyse = analyse
    courante.actions_menees = texte_long(data.get("actions_menees"))
    courante.conclusion = conclusion
    courante.decision_proposee = data.get("decision_proposee")
    courante.retour_le = max(now, courante.recu_le)
    courante.retour_par_id = s.user_id
    courante.statut = "RETOURNEE"
    courante.revision += 1
    r.responsable_traitement_id = courante.responsable_id
    r.date_retour_service = courante.retour_le
    await _appliquer(db, s, r, statut="RETOUR_RECU", type_evenement="RETOUR_SERVICE",
                     commentaire=conclusion, unite_id=r.unite_traitement_id, affectation_id=courante.id,
                     destinataires=await destinataires_sr(db, await Contexte.charger(db)),
                     titre="Retour de service à examiner")
    return await fiche(db, s, r)


# --------------------------------------------------------------------- 4. Clôture
async def evaluer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.review")
    if r.statut != "RETOUR_RECU":
        raise conflit("Aucun retour à examiner", "ACTION_INVALIDE")
    _, courante, *_ = await _pieces_circuit(db, r)
    if courante is None or courante.statut != "RETOURNEE":
        raise conflit("Fiche de retour introuvable", "ACTION_INVALIDE")
    ev = data.get("evaluation")
    if ev not in {"SUFFISANT", "INSUFFISANT"}:
        raise erreur("Indiquez si le retour est suffisant", "EVALUATION_OBLIGATOIRE")
    courante.evaluation = ev
    courante.evaluation_commentaire = texte_long(data.get("commentaire") or data.get("motif"))
    courante.evalue_le = maintenant()
    courante.evalue_par_id = s.user_id
    ctx = await Contexte.charger(db)
    if ev == "SUFFISANT":
        await _appliquer(db, s, r, statut="A_CLOTURER", type_evenement="EVALUATION",
                         commentaire=courante.evaluation_commentaire, affectation_id=courante.id,
                         donnees={"evaluation": ev})
    else:
        if not courante.evaluation_commentaire:
            raise erreur("Indiquez le complément demandé au service", "MOTIF_OBLIGATOIRE")
        payload = {**data, "unite_id": data.get("unite_id") or r.unite_traitement_id,
                   "motif_transfert": courante.evaluation_commentaire}
        a = await _nouvelle_affectation(db, s, r, ctx, payload, parent=courante)
        r.nb_renvois += 1
        dest = await membres_unite(db, a.unite_destinataire_id)
        await _appliquer(db, s, r, statut="EN_TRAITEMENT", type_evenement="RENVOI",
                         commentaire=a.motif_transfert, unite_id=a.unite_destinataire_id, affectation_id=a.id,
                         donnees={"evaluation": ev, "renvoi": r.nb_renvois},
                         destinataires=dest, titre="Réclamation renvoyée — complément demandé")
    return await fiche(db, s, r, ctx)


async def cloturer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.close")
    if not service_central(s):
        raise erreur("Seul le Service Réclamations central clôture une réclamation", "CLOTURE_RESERVEE_SR", 403)
    if r.statut != "A_CLOTURER":
        raise conflit("La clôture exige le retour du service examiné (ou un traitement interne)",
                      "ACTION_INVALIDE")
    _, _, _, courante_r, _ = await _pieces_circuit(db, r)
    if not (courante_r and courante_r.statut == "ENVOYEE"):
        raise conflit("Enregistrez la réponse envoyée au client avant de clôturer", "REPONSE_NON_ENVOYEE")
    resultat = data.get("resultat") or courante_r.resultat
    if resultat not in C.RESULTAT_LIBELLES:
        raise erreur("Le résultat de la décision est obligatoire", "RESULTAT_OBLIGATOIRE")
    r.resultat = resultat
    r.motif_resolution = texte_long(data.get("motif_resolution") or data.get("motif"))
    r.date_cloture = max(maintenant(), r.date_premiere_reception)
    r.cloture_par_id = s.user_id
    await _appliquer(db, s, r, statut="CLOTUREE", type_evenement="CLOTURE",
                     commentaire=r.motif_resolution, donnees={"resultat": r.resultat})
    return await fiche(db, s, r)


async def refuser(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.reject")
    if r.statut not in AVANT_AFFECTATION:
        raise conflit("Le rejet n'est possible qu'avant l'affectation", "ACTION_INVALIDE")
    r.motif_refus = _motif(data)
    r.date_cloture = max(maintenant(), r.date_premiere_reception)
    r.cloture_par_id = s.user_id
    r.resultat = "SANS_SUITE"
    await _appliquer(db, s, r, statut="REJETEE", type_evenement="REFUS", commentaire=r.motif_refus)
    return await fiche(db, s, r)


async def annuler(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    _ouvert(r)
    s.exiger("reclamations.cancel")
    if r.statut not in AVANT_AFFECTATION:
        raise conflit("L'annulation n'est possible qu'avant l'affectation", "ACTION_INVALIDE")
    r.motif_annulation = _motif(data)
    if data.get("doublon_de_id"):
        r.doublon_de_id = await _liee(db, s, data["doublon_de_id"], r.id)
    r.date_cloture = max(maintenant(), r.date_premiere_reception)
    r.cloture_par_id = s.user_id
    await _appliquer(db, s, r, statut="ANNULEE", type_evenement="ANNULATION",
                     commentaire=r.motif_annulation,
                     donnees={"doublon": str(r.doublon_de_id) if r.doublon_de_id else None})
    return await fiche(db, s, r)


async def rouvrir(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    """La clôture précédente reste dans l'historique (événement CLOTURE, résultat, réponse envoyée)."""
    r = await _charger(db, s, rid, data)
    s.exiger("reclamations.reopen")
    if r.archivee_le:
        raise conflit("Dossier archivé", "DOSSIER_ARCHIVE")
    if r.statut not in {"CLOTUREE", "REJETEE"}:
        raise conflit("Seuls les dossiers clôturés ou rejetés se rouvrent", "ACTION_INVALIDE")
    precedente = {"statut": r.statut, "date_cloture": iso(r.date_cloture), "resultat": r.resultat}
    r.nb_reouvertures += 1
    r.date_reouverture = maintenant()
    r.date_cloture = None
    r.cloture_par_id = None
    await _appliquer(db, s, r, statut="REOUVERTE", type_evenement="REOUVERTURE",
                     commentaire=_motif(data),
                     donnees={"reouvertures": r.nb_reouvertures, "cloture_precedente": precedente})
    return await fiche(db, s, r)


async def archiver(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await _charger(db, s, rid, data)
    s.exiger("reclamations.archive")
    if r.statut not in C.STATUTS_TERMINAUX:
        raise conflit("Seuls les dossiers terminés s'archivent", "ACTION_INVALIDE")
    if r.archivee_le:
        raise conflit("Dossier déjà archivé", "DOSSIER_ARCHIVE")
    r.archivee_le = maintenant()
    r.archivee_par_id = s.user_id
    r.revision += 1
    r.updated_by_id = s.user_id
    db.add(_evenement(r, s, "ARCHIVAGE", statut_avant=r.statut, etape_avant=r.etape,
                      commentaire=texte_long(data.get("motif"))))
    await db.flush()
    await auditer(db, s, "reclamations.archivage", C.GED_ENTITE, r.id, after={"archivee_le": iso(r.archivee_le)})
    return await fiche(db, s, r)


ACTIONS = {
    "qualifier": qualifier,
    "affecter": affecter,
    "traiter_interne": traiter_interne,
    "retourner": retourner,
    "evaluer": evaluer,
    "refuser": refuser,
    "annuler": annuler,
    "cloturer": cloturer,
    "rouvrir": rouvrir,
    "archiver": archiver,
}


async def executer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, action: str, data: dict) -> dict:
    fn = ACTIONS.get(action)
    if fn is None:
        raise erreur(f"Action inconnue : {action}", "ACTION_INCONNUE")
    return await fn(db, s, rid, data)
