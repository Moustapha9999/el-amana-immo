"""Dossiers de réclamation : enregistrement, consultation, correction, chronologie.

Règles :
- référence ``REC-AAAA-NNNNNN`` attribuée par compteur annuel verrouillé, jamais saisie ;
- dates déclarées (première réception, réception SR) ≤ maintenant, cohérentes entre elles ; chaque
  événement garde sa date métier **et** l'horodatage serveur de la saisie ;
- type → motif → sous-motif cohérents ; seules les valeurs actives sont proposables ;
- canal Téléphone : un appel (date, numéro) est obligatoire ; la référence d'enregistrement n'est
  acceptée que si la banque l'a autorisé (paramètre du module) ;
- correction d'une date clé = motif obligatoire ; dossier terminé = lecture seule ;
- concurrence optimiste : ``revision`` (409 ``CONFLIT_REVISION``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agence,
    AuditLog,
    ClienteleClient,
    ClienteleCompte,
    GedDocument,
    Reclamation,
    ReclamationAppel,
    ReclamationEvenement,
    ReclamationParametre,
    ReclamationReferentiel,
    ReclamationUnite,
)
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.outils import (
    auditer,
    conflit,
    erreur,
    iso,
    maintenant,
    noms_utilisateurs,
    propre,
    serialisable,
    texte_long,
)

TOLERANCE_HORLOGE = timedelta(minutes=5)
TAILLE_MAX_PAGE = 100
TRI_COLONNES = {
    "reference": (Reclamation.annee, Reclamation.numero),
    "date_premiere_reception": (Reclamation.date_premiere_reception,),
    "date_reception_sr": (Reclamation.date_reception_sr,),
    "echeance": (Reclamation.echeance,),
    "statut": (Reclamation.statut,),
    "client_nom": (Reclamation.client_nom,),
    "updated_at": (Reclamation.updated_at,),
    "created_at": (Reclamation.created_at,),
    "priorite": (case({"URGENTE": 4, "HAUTE": 3, "NORMALE": 2, "BASSE": 1}, value=Reclamation.priorite),),
}
# Champs remis à vide via ``effacer`` (PATCH : ``None`` = inchangé).
EFFACABLES = frozenset({
    "type_id", "motif_id", "sous_motif_id", "client_racine", "client_categorie", "client_telephone",
    "client_email", "client_adresse", "client_agence_id", "compte_reference", "carte_masquee",
    "operation_reference", "operation_date", "montant_conteste", "devise", "reclamation_liee_id",
})
CHAMPS_TEXTE = ("client_nom", "client_telephone", "client_email", "compte_reference", "carte_masquee",
                "operation_reference")
CHAMPS_LIBELLES = {
    "objet": "Objet", "description": "Description", "type_id": "Type", "motif_id": "Motif",
    "sous_motif_id": "Sous-motif", "priorite": "Priorité", "unite_reception_id": "Unité de réception",
    "client_racine": "Racine client", "client_categorie": "Catégorie de client", "client_nom": "Nom du client",
    "client_telephone": "Téléphone du client", "client_email": "E-mail du client",
    "client_adresse": "Adresse du client", "client_agence_id": "Agence du client",
    "compte_reference": "Compte concerné", "carte_masquee": "Carte (masquée)",
    "operation_reference": "Référence de l'opération", "operation_date": "Date de l'opération",
    "montant_conteste": "Montant contesté", "devise": "Devise", "reclamation_liee_id": "Réclamation liée",
    "date_premiere_reception": "Date de première réception", "date_reception_sr": "Date de réception SR",
}
DATES_CLES = ("date_premiere_reception", "date_reception_sr")


# --------------------------------------------------------------------- contexte
class Contexte:
    """Référentiels, unités et agences chargés une fois par requête (tables courtes)."""

    def __init__(self, refs: list[ReclamationReferentiel], unites: list[ReclamationUnite],
                 agences: dict[uuid.UUID, tuple[str, str]]):
        self.refs = {r.id: r for r in refs}
        self.unites = {u.id: u for u in unites}
        self.agences = agences

    @classmethod
    async def charger(cls, db: AsyncSession) -> Contexte:
        refs = list((await db.scalars(select(ReclamationReferentiel))).all())
        unites = list((await db.scalars(select(ReclamationUnite))).all())
        agences = {i: (c, lib) for i, c, lib in (await db.execute(
            select(Agence.id, Agence.code, Agence.libelle))).all()}
        return cls(refs, unites, agences)

    def ref(self, rid: uuid.UUID | None) -> dict | None:
        r = self.refs.get(rid) if rid else None
        return {"id": str(r.id), "code": r.code, "libelle": r.libelle, "actif": r.actif} if r else None

    def lib(self, rid: uuid.UUID | None) -> str | None:
        r = self.refs.get(rid) if rid else None
        return r.libelle if r else None

    def unite(self, uid: uuid.UUID | None) -> dict | None:
        u = self.unites.get(uid) if uid else None
        return {"id": str(u.id), "libelle": u.libelle, "type_unite": u.type_unite, "actif": u.actif} if u else None

    def agence(self, aid: uuid.UUID | None) -> dict | None:
        a = self.agences.get(aid) if aid else None
        return {"id": str(aid), "code": a[0], "libelle": a[1]} if a else None

    def service_central(self) -> ReclamationUnite | None:
        return next((u for u in self.unites.values() if u.est_service_reclamations and u.actif), None)


# ------------------------------------------------------------------ sérialisation
def _statut(r: Reclamation) -> dict:
    return {
        "statut": r.statut, "statut_libelle": C.STATUT_LIBELLES.get(r.statut, r.statut),
        "groupe": C.STATUT_GROUPES.get(r.statut), "groupe_libelle": C.GROUPE_LIBELLES.get(C.STATUT_GROUPES.get(r.statut, "")),
        "etape": r.etape, "etape_libelle": C.ETAPE_LIBELLES.get(r.etape, r.etape),
        "termine": r.statut in C.STATUTS_TERMINAUX,
    }


def en_retard(r: Reclamation, now: datetime | None = None) -> bool:
    return bool(r.echeance and r.statut not in C.STATUTS_TERMINAUX and r.echeance < (now or maintenant()))


def ligne(r: Reclamation, ctx: Contexte, nb_documents: int = 0) -> dict:
    return {
        "id": str(r.id), "reference": r.reference, "objet": r.objet,
        "client_nom": r.client_nom, "client_racine": r.client_racine, "client_categorie": r.client_categorie,
        "canal": ctx.lib(r.canal_id), "type": ctx.lib(r.type_id), "motif": ctx.lib(r.motif_id),
        "priorite": r.priorite, "priorite_libelle": C.PRIORITE_LIBELLES.get(r.priorite),
        **_statut(r),
        "unite_reception": (ctx.unite(r.unite_reception_id) or {}).get("libelle"),
        "unite_traitement": (ctx.unite(r.unite_traitement_id) or {}).get("libelle"),
        "date_premiere_reception": iso(r.date_premiere_reception), "date_reception_sr": iso(r.date_reception_sr),
        "date_cloture": iso(r.date_cloture), "echeance": iso(r.echeance), "en_retard": en_retard(r),
        "nb_documents": nb_documents, "revision": r.revision, "updated_at": iso(r.updated_at),
    }


def peut_modifier(s: ReclamationsScope, r: Reclamation) -> bool:
    if r.statut in C.STATUTS_TERMINAUX or r.archivee_le:
        return False
    if s.peut("reclamations.update"):
        return True
    return s.peut("reclamations.create") and r.created_by_id == s.user_id and r.statut == "RECUE"


def actions(s: ReclamationsScope, r: Reclamation) -> dict[str, bool]:
    ouvert = r.statut not in C.STATUTS_TERMINAUX and not r.archivee_le
    return {
        "modifier": peut_modifier(s, r),
        "ajouter_appel": ouvert and (s.peut("reclamations.update") or peut_modifier(s, r)),
        "documents_voir": s.peut("reclamations.document.view"),
        "documents_deposer": s.peut("reclamations.document.upload") and not r.archivee_le,
        "documents_telecharger": s.peut("reclamations.document.download"),
        "documents_retirer": s.peut("reclamations.document.remove") and not r.archivee_le,
        "audit_voir": s.peut("reclamations.audit.view"),
    }


def _appel_dict(a: ReclamationAppel, noms: dict[uuid.UUID, str]) -> dict:
    return {
        "id": str(a.id), "appel_le": iso(a.appel_le), "numero_appelant": a.numero_appelant,
        "agent": noms.get(a.agent_id) if a.agent_id else None, "identite_verifiee": a.identite_verifiee,
        "mode_verification": a.mode_verification, "reference_appel": a.reference_appel,
        "enregistrement_autorise": a.enregistrement_autorise, "reference_enregistrement": a.reference_enregistrement,
        "rappel_statut": a.rappel_statut, "rappel_statut_libelle": C.STATUT_RAPPEL_LIBELLES.get(a.rappel_statut),
        "rappel_prevu_le": iso(a.rappel_prevu_le), "rappel_effectue_le": iso(a.rappel_effectue_le),
        "commentaire": a.commentaire,
    }


async def detail(db: AsyncSession, s: ReclamationsScope, r: Reclamation, ctx: Contexte | None = None) -> dict:
    ctx = ctx or await Contexte.charger(db)
    appels = list((await db.scalars(select(ReclamationAppel).where(
        ReclamationAppel.reclamation_id == r.id).order_by(ReclamationAppel.appel_le))).all())
    noms = await noms_utilisateurs(db, {r.created_by_id, r.updated_by_id, r.gestionnaire_id,
                                        r.responsable_traitement_id, r.cloture_par_id,
                                        *(a.agent_id for a in appels)})
    nb_documents = await db.scalar(select(func.count()).select_from(GedDocument).where(
        GedDocument.module_code == C.MODULE_CODE, GedDocument.entity == C.GED_ENTITE,
        GedDocument.entity_id == str(r.id), GedDocument.deleted_at.is_(None))) or 0
    liees = {i: ref for i, ref in (await db.execute(select(Reclamation.id, Reclamation.reference).where(
        Reclamation.id.in_([i for i in (r.reclamation_liee_id, r.doublon_de_id) if i])))).all()}
    return {
        **ligne(r, ctx, nb_documents),
        "description": r.description, "source": r.source,
        "type_ref": ctx.ref(r.type_id), "motif_ref": ctx.ref(r.motif_id), "sous_motif_ref": ctx.ref(r.sous_motif_id),
        "canal_ref": ctx.ref(r.canal_id),
        "canal_telephone": bool(r.canal_id in ctx.refs and ctx.refs[r.canal_id].code == C.CANAL_TELEPHONE),
        "unite_reception_ref": ctx.unite(r.unite_reception_id), "unite_suivi_ref": ctx.unite(r.unite_suivi_id),
        "unite_traitement_ref": ctx.unite(r.unite_traitement_id),
        "client": {
            "racine": r.client_racine, "categorie": r.client_categorie,
            "categorie_libelle": C.CATEGORIE_CLIENT_LIBELLES.get(r.client_categorie or ""),
            "nom": r.client_nom, "telephone": r.client_telephone, "email": r.client_email,
            "adresse": r.client_adresse, "agence": ctx.agence(r.client_agence_id),
        },
        "operation": {
            "compte_reference": r.compte_reference, "carte_masquee": r.carte_masquee,
            "reference": r.operation_reference, "date": iso(r.operation_date),
            "montant_conteste": str(r.montant_conteste) if r.montant_conteste is not None else None,
            "devise": r.devise,
        },
        "reclamation_liee": ({"id": str(r.reclamation_liee_id), "reference": liees.get(r.reclamation_liee_id)}
                             if r.reclamation_liee_id else None),
        "doublon_de": ({"id": str(r.doublon_de_id), "reference": liees.get(r.doublon_de_id)}
                       if r.doublon_de_id else None),
        "dates": {k: iso(getattr(r, k)) for k in (
            "date_premiere_reception", "date_reception_sr", "date_qualification", "date_transmission",
            "date_reception_service", "date_retour_service", "date_reponse_client", "date_cloture",
            "date_suspension", "date_reouverture")},
        "echeance_initiale": iso(r.echeance_initiale), "regle_delai_id": str(r.regle_delai_id) if r.regle_delai_id else None,
        "gestionnaire": noms.get(r.gestionnaire_id) if r.gestionnaire_id else None,
        "responsable_traitement": noms.get(r.responsable_traitement_id) if r.responsable_traitement_id else None,
        "motif_suspension": r.motif_suspension, "conditions_reprise": r.conditions_reprise,
        "motif_refus": r.motif_refus, "motif_annulation": r.motif_annulation,
        "resultat": r.resultat, "resultat_libelle": C.RESULTAT_LIBELLES.get(r.resultat or ""),
        "motif_resolution": r.motif_resolution, "nb_reouvertures": r.nb_reouvertures, "nb_renvois": r.nb_renvois,
        "archivee_le": iso(r.archivee_le),
        "appels": [_appel_dict(a, noms) for a in appels],
        "cree_par": noms.get(r.created_by_id) if r.created_by_id else None, "created_at": iso(r.created_at),
        "modifie_par": noms.get(r.updated_by_id) if r.updated_by_id else None,
        "actions": actions(s, r),
    }


# --------------------------------------------------------------------- lecture
async def charger(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, *, verrou: bool = False) -> Reclamation:
    q = select(Reclamation).where(Reclamation.id == rid)
    if verrou:
        q = q.with_for_update()
    return await s.exiger_dossier(db, await db.scalar(q))


def _filtres(q, f: dict[str, Any]):
    if f.get("q"):
        motif = f"%{propre(f['q'])}%"
        q = q.where(or_(Reclamation.reference.ilike(motif), Reclamation.objet.ilike(motif),
                        Reclamation.client_nom.ilike(motif), Reclamation.client_racine.ilike(motif),
                        Reclamation.compte_reference.ilike(motif), Reclamation.operation_reference.ilike(motif)))
    if f.get("statut"):
        q = q.where(Reclamation.statut.in_(f["statut"]))
    if f.get("groupe"):
        q = q.where(Reclamation.statut.in_([k for k, g in C.STATUT_GROUPES.items() if g in f["groupe"]]))
    if f.get("etape"):
        q = q.where(Reclamation.etape == f["etape"])
    for champ in ("type_id", "motif_id", "sous_motif_id", "canal_id", "unite_reception_id",
                  "unite_traitement_id", "gestionnaire_id", "client_agence_id"):
        if f.get(champ):
            q = q.where(getattr(Reclamation, champ) == f[champ])
    for champ in ("priorite", "client_categorie", "client_racine"):
        if f.get(champ):
            q = q.where(getattr(Reclamation, champ) == f[champ])
    if f.get("date_debut"):
        q = q.where(Reclamation.date_premiere_reception >= datetime.combine(f["date_debut"], datetime.min.time())
                    .astimezone())
    if f.get("date_fin"):
        q = q.where(Reclamation.date_premiere_reception < datetime.combine(
            f["date_fin"] + timedelta(days=1), datetime.min.time()).astimezone())
    if f.get("ouvertes"):
        q = q.where(Reclamation.statut.not_in(C.STATUTS_TERMINAUX))
    if f.get("en_retard"):
        q = q.where(Reclamation.echeance < maintenant(), Reclamation.statut.not_in(C.STATUTS_TERMINAUX))
    if f.get("sans_echeance"):
        q = q.where(Reclamation.echeance.is_(None), Reclamation.statut.not_in(C.STATUTS_TERMINAUX))
    if f.get("archivees") is True:
        q = q.where(Reclamation.archivee_le.is_not(None))
    elif f.get("archivees") is False:
        q = q.where(Reclamation.archivee_le.is_(None))
    return q


async def lister(db: AsyncSession, s: ReclamationsScope, f: dict[str, Any], *, page: int = 1, taille: int = 25,
                 tri: str = "date_premiere_reception", ordre: str = "desc") -> dict:
    taille = max(1, min(taille, TAILLE_MAX_PAGE))
    base = _filtres(select(Reclamation).where(s.filtre_dossiers()), f)
    total = await db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    colonnes = TRI_COLONNES.get(tri, TRI_COLONNES["date_premiere_reception"])
    ordres = [c.asc().nulls_last() if ordre == "asc" else c.desc().nulls_last() for c in colonnes]
    rows = list((await db.scalars(base.order_by(*ordres, Reclamation.id.desc())
                                  .offset((max(page, 1) - 1) * taille).limit(taille))).all())
    docs: dict[str, int] = {}
    if rows:
        docs = dict((await db.execute(
            select(GedDocument.entity_id, func.count()).where(
                GedDocument.module_code == C.MODULE_CODE, GedDocument.entity == C.GED_ENTITE,
                GedDocument.entity_id.in_([str(r.id) for r in rows]), GedDocument.deleted_at.is_(None))
            .group_by(GedDocument.entity_id))).all())
    ctx = await Contexte.charger(db)
    return {"items": [ligne(r, ctx, docs.get(str(r.id), 0)) for r in rows], "total": total,
            "page": max(page, 1), "taille": taille}


async def chronologie(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID) -> list[dict]:
    r = await charger(db, s, rid)
    evts = list((await db.scalars(select(ReclamationEvenement).where(
        ReclamationEvenement.reclamation_id == r.id).order_by(
        ReclamationEvenement.date_effet, ReclamationEvenement.enregistre_le))).all())
    noms = await noms_utilisateurs(db, {e.auteur_id for e in evts})
    ctx = await Contexte.charger(db)
    return [{
        "id": str(e.id), "type": e.type_evenement,
        "libelle": C.EVENEMENT_LIBELLES.get(e.type_evenement, e.type_evenement),
        "statut_avant": C.STATUT_LIBELLES.get(e.statut_avant or ""), "statut_apres": C.STATUT_LIBELLES.get(e.statut_apres or ""),
        "etape_avant": C.ETAPE_LIBELLES.get(e.etape_avant or ""), "etape_apres": C.ETAPE_LIBELLES.get(e.etape_apres or ""),
        "date_effet": iso(e.date_effet), "enregistre_le": iso(e.enregistre_le),
        "auteur": noms.get(e.auteur_id) if e.auteur_id else None,
        "unite": (ctx.unite(e.unite_id) or {}).get("libelle"), "commentaire": e.commentaire, "donnees": e.donnees,
    } for e in evts]


async def journal_audit(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID) -> list[dict]:
    s.exiger("reclamations.audit.view")
    r = await charger(db, s, rid)
    logs = list((await db.scalars(select(AuditLog).where(
        AuditLog.module_code == C.MODULE_CODE, AuditLog.entity_id == str(r.id))
        .order_by(AuditLog.created_at.desc()).limit(500))).all())
    noms = await noms_utilisateurs(db, {lg.user_id for lg in logs})
    return [{
        "id": str(lg.id), "action": lg.action, "entity": lg.entity, "utilisateur": noms.get(lg.user_id) if lg.user_id else None,
        "date": iso(lg.created_at), "avant": lg.before_data, "apres": lg.after_data, "ip": lg.ip_address,
        "request_id": lg.request_id,
    } for lg in logs]


# ------------------------------------------------------------------ validations
def _ref_valide(ctx: Contexte, rid: uuid.UUID | None, domaine: str, *, conserver: uuid.UUID | None = None
                ) -> ReclamationReferentiel | None:
    if rid is None:
        return None
    r = ctx.refs.get(rid)
    if r is None or r.domaine != domaine:
        raise erreur(f"{C.DOMAINE_LIBELLES[domaine]} introuvable", "REFERENTIEL_INVALIDE")
    if not r.actif and rid != conserver:
        raise erreur(f"{C.DOMAINE_LIBELLES[domaine]} « {r.libelle} » désactivé", "REFERENTIEL_INACTIF")
    return r


def _classement(ctx: Contexte, type_id, motif_id, sous_motif_id, actuel: Reclamation | None = None
                ) -> tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]:
    """Type → motif → sous-motif : complète les parents manquants, refuse les incohérences."""
    sm = _ref_valide(ctx, sous_motif_id, "SOUS_MOTIF", conserver=actuel.sous_motif_id if actuel else None)
    if sm:
        if motif_id and motif_id != sm.parent_id:
            raise erreur("Le sous-motif n'appartient pas au motif choisi", "CLASSEMENT_INCOHERENT")
        motif_id = sm.parent_id
    m = _ref_valide(ctx, motif_id, "MOTIF", conserver=actuel.motif_id if actuel else None)
    if m:
        if type_id and type_id != m.parent_id:
            raise erreur("Le motif n'appartient pas au type choisi", "CLASSEMENT_INCOHERENT")
        type_id = m.parent_id
    _ref_valide(ctx, type_id, "TYPE", conserver=actuel.type_id if actuel else None)
    return type_id, motif_id, sous_motif_id


def _carte(valeur: str | None) -> str | None:
    """Numéro de carte : au plus 6 premiers + 4 derniers chiffres visibles, jamais le PAN complet."""
    v = propre(valeur) or None
    if v and sum(ch.isdigit() for ch in v) > 10:
        raise erreur("Carte : saisissez au plus les 6 premiers et 4 derniers chiffres (numéro masqué)",
                     "CARTE_NON_MASQUEE")
    return v


def _date_passee(valeur: datetime, libelle: str) -> datetime:
    if valeur.tzinfo is None:
        raise erreur(f"{libelle} : fuseau horaire manquant", "DATE_INVALIDE")
    if valeur > maintenant() + TOLERANCE_HORLOGE:
        raise erreur(f"{libelle} ne peut pas être dans le futur", "DATE_FUTURE")
    return valeur


def _unite_reception(s: ReclamationsScope, ctx: Contexte, uid: uuid.UUID | None,
                     actuelle: uuid.UUID | None = None) -> uuid.UUID:
    if uid is None:
        if len(s.unites) == 1 and not s.toutes:
            uid = next(iter(s.unites))
        else:
            raise erreur("Indiquez l'unité qui a reçu la réclamation", "UNITE_RECEPTION_OBLIGATOIRE")
    u = ctx.unites.get(uid)
    if u is None:
        raise erreur("Unité de réception introuvable", "UNITE_INCONNUE")
    if not u.actif and uid != actuelle:
        raise erreur(f"L'unité « {u.libelle} » est désactivée", "UNITE_INACTIVE")
    if not s.toutes and uid not in s.unites and uid != actuelle:
        if not s.unites:
            raise erreur("Vous n'êtes rattaché à aucune unité : demandez à l'administrateur du module de vous "
                         "rattacher à votre agence ou service.", "AUCUNE_UNITE")
        raise erreur("Vous ne pouvez enregistrer que pour une unité à laquelle vous êtes rattaché",
                     "UNITE_HORS_PERIMETRE")
    return uid


async def _client(db: AsyncSession, racine: str | None) -> ClienteleClient | None:
    if not racine:
        return None
    if not (len(racine) == 6 and racine.isdigit()):
        raise erreur("La racine client comporte 6 chiffres", "RACINE_INVALIDE")
    c = await db.scalar(select(ClienteleClient).where(ClienteleClient.racine_client == racine))
    if c is None:
        raise erreur(f"Racine {racine} inconnue de la base clientèle", "CLIENT_INCONNU")
    return c


def _categorie(c: ClienteleClient) -> str:
    return "PP" if c.type_client == "PP" else "PM"


def _nom_client(c: ClienteleClient) -> str:
    return propre(f"{c.prenoms or ''} {c.raison_sociale}") if c.prenoms else c.raison_sociale


async def apercu_client(db: AsyncSession, racine: str) -> dict:
    c = await _client(db, racine)
    comptes = (await db.execute(
        select(ClienteleCompte.compte, ClienteleCompte.etat_compte, ClienteleCompte.devise, ClienteleCompte.agence_id)
        .where(ClienteleCompte.racine_client == racine).order_by(ClienteleCompte.compte))).all()
    agences = {i: (code, lib) for i, code, lib in (await db.execute(
        select(Agence.id, Agence.code, Agence.libelle))).all()}
    return {
        "racine": c.racine_client, "nom": _nom_client(c), "categorie": _categorie(c),
        "comptes": [{"compte": cp, "etat": et, "devise": dv,
                     "agence_id": str(ag), "agence": " — ".join(agences.get(ag, ("", "")))}
                    for cp, et, dv, ag in comptes],
    }


async def _parametre(db: AsyncSession, cle_param: str, defaut: Any = None) -> Any:
    p = await db.get(ReclamationParametre, cle_param)
    return p.valeur if p is not None else defaut


async def enregistrement_autorise(db: AsyncSession) -> bool:
    return bool(await _parametre(db, C.PARAM_ENREGISTREMENT_APPELS, False))


async def _appel(db: AsyncSession, s: ReclamationsScope, r: Reclamation, data: dict) -> ReclamationAppel:
    appel_le = _date_passee(data["appel_le"], "Date de l'appel")
    if appel_le < r.date_premiere_reception - TOLERANCE_HORLOGE:
        raise erreur("L'appel ne peut pas précéder la première réception", "DATE_INCOHERENTE")
    autorise = await enregistrement_autorise(db)
    ref_enreg = propre(data.get("reference_enregistrement")) or None
    if ref_enreg and not autorise:
        raise erreur("La référence d'enregistrement d'appel n'est pas autorisée par la banque", "ENREGISTREMENT_NON_AUTORISE")
    rappel = data.get("rappel_statut") or "AUCUN"
    prevu = data.get("rappel_prevu_le")
    if rappel == "A_RAPPELER" and not prevu:
        raise erreur("Indiquez la date de rappel prévue", "RAPPEL_SANS_DATE")
    numero = propre(data.get("numero_appelant"))
    if not numero:
        raise erreur("Le numéro de l'appelant est obligatoire", "NUMERO_OBLIGATOIRE")
    a = ReclamationAppel(
        reclamation_id=r.id, appel_le=appel_le, numero_appelant=numero, agent_id=s.user_id,
        identite_verifiee=bool(data.get("identite_verifiee")),
        mode_verification=propre(data.get("mode_verification")) or None,
        reference_appel=propre(data.get("reference_appel")) or None,
        enregistrement_autorise=autorise, reference_enregistrement=ref_enreg, rappel_statut=rappel,
        rappel_prevu_le=prevu, rappel_effectue_le=maintenant() if rappel == "RAPPELE" else None,
        commentaire=texte_long(data.get("commentaire")), created_by_id=s.user_id)
    db.add(a)
    await db.flush()
    return a


def _evenement(r: Reclamation, s: ReclamationsScope, type_evenement: str, *, date_effet: datetime | None = None,
               statut_avant: str | None = None, etape_avant: str | None = None, unite_id: uuid.UUID | None = None,
               commentaire: str | None = None, donnees: dict | None = None) -> ReclamationEvenement:
    return ReclamationEvenement(
        reclamation_id=r.id, type_evenement=type_evenement, statut_avant=statut_avant, statut_apres=r.statut,
        etape_avant=etape_avant, etape_apres=r.etape, date_effet=date_effet or maintenant(),
        auteur_id=s.user_id, unite_id=unite_id, commentaire=commentaire, donnees=donnees or {})


async def _numero(db: AsyncSession, annee: int) -> int:
    return (await db.execute(text(
        "INSERT INTO reclamation_compteurs (annee, dernier) VALUES (:a, 1) "
        "ON CONFLICT (annee) DO UPDATE SET dernier = reclamation_compteurs.dernier + 1 RETURNING dernier"),
        {"a": annee})).scalar_one()


async def _liee(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID | None, propre_id: uuid.UUID | None = None
                ) -> uuid.UUID | None:
    if rid is None:
        return None
    if rid == propre_id:
        raise erreur("Une réclamation ne peut pas être liée à elle-même", "LIEN_INVALIDE")
    await s.exiger_dossier(db, await db.get(Reclamation, rid))
    return rid


# ------------------------------------------------------------------- écriture
async def creer(db: AsyncSession, s: ReclamationsScope, data: dict) -> dict:
    s.exiger("reclamations.create")
    ctx = await Contexte.charger(db)
    canal = _ref_valide(ctx, data["canal_id"], "CANAL")
    telephone = canal.code == C.CANAL_TELEPHONE
    if telephone and not data.get("appel"):
        raise erreur("Canal Téléphone : renseignez l'appel (date, numéro de l'appelant)", "APPEL_OBLIGATOIRE")
    premiere = _date_passee(data["date_premiere_reception"], "Date de première réception")
    reception_sr = data.get("date_reception_sr")
    central = ctx.service_central()
    if reception_sr is not None:
        if not (s.membre_service_central or s.peut("reclamations.qualify")):
            raise erreur("Seul le Service Réclamations enregistre une réception SR", "PERMISSION_DENIED", 403)
        _date_passee(reception_sr, "Date de réception SR")
        if reception_sr < premiere:
            raise erreur("La réception SR ne peut pas précéder la première réception", "DATE_INCOHERENTE")
    type_id, motif_id, sous_motif_id = _classement(ctx, data.get("type_id"), data.get("motif_id"),
                                                   data.get("sous_motif_id"))
    unite_reception_id = _unite_reception(s, ctx, data.get("unite_reception_id"))
    client = await _client(db, propre(data.get("client_racine")) or None)
    nom = propre(data.get("client_nom")) or (_nom_client(client) if client else "")
    if not nom:
        raise erreur("Le nom du réclamant est obligatoire", "CLIENT_NOM_OBLIGATOIRE")
    if data.get("client_agence_id") and data["client_agence_id"] not in ctx.agences:
        raise erreur("Agence du client introuvable", "AGENCE_INCONNUE")
    objet, description = propre(data.get("objet")), texte_long(data.get("description"))
    if not objet or not description:
        raise erreur("Objet et description sont obligatoires", "CHAMPS_OBLIGATOIRES")
    carte = _carte(data.get("carte_masquee"))

    now = maintenant()
    numero = await _numero(db, now.year)
    r = Reclamation(
        reference=f"{C.PREFIXE_REFERENCE}-{now.year}-{numero:06d}", annee=now.year, numero=numero,
        objet=objet, description=description, type_id=type_id, motif_id=motif_id, sous_motif_id=sous_motif_id,
        priorite=data.get("priorite") or "NORMALE",
        statut="RECUE_SR" if reception_sr else "RECUE", etape="RECEPTION",
        source="CENTRE_APPEL" if telephone else "MANUEL", canal_id=canal.id, unite_reception_id=unite_reception_id,
        client_racine=client.racine_client if client else None,
        client_categorie=data.get("client_categorie") or (_categorie(client) if client else None),
        client_nom=nom, client_telephone=propre(data.get("client_telephone")) or None,
        client_email=propre(data.get("client_email")) or None, client_adresse=texte_long(data.get("client_adresse")),
        client_agence_id=data.get("client_agence_id"), compte_reference=propre(data.get("compte_reference")) or None,
        carte_masquee=carte,
        operation_reference=propre(data.get("operation_reference")) or None, operation_date=data.get("operation_date"),
        montant_conteste=data.get("montant_conteste"), devise=(propre(data.get("devise")).upper() or None),
        reclamation_liee_id=await _liee(db, s, data.get("reclamation_liee_id")),
        date_premiere_reception=premiere, date_reception_sr=reception_sr,
        unite_suivi_id=central.id if (reception_sr and central) else None,
        gestionnaire_id=s.user_id if reception_sr else None,
        revision=1, created_by_id=s.user_id, updated_by_id=s.user_id)
    db.add(r)
    await db.flush()
    db.add(_evenement(r, s, "CREATION", date_effet=premiere, unite_id=unite_reception_id,
                      donnees={"canal": canal.libelle, "enregistre_par_service_central": bool(reception_sr)}))
    if reception_sr:
        db.add(_evenement(r, s, "RECEPTION_SR", date_effet=reception_sr, statut_avant="RECUE",
                          etape_avant="RECEPTION", unite_id=central.id if central else None))
    if data.get("appel"):
        a = await _appel(db, s, r, data["appel"])
        db.add(_evenement(r, s, "APPEL", date_effet=a.appel_le, donnees={"numero": a.numero_appelant,
                                                                         "rappel": a.rappel_statut}))
    await db.flush()
    from app.services.reclamations.delais import appliquer
    await appliquer(db, r)
    await auditer(db, s, "reclamations.dossier.create", C.GED_ENTITE, r.id, after={
        "reference": r.reference, "statut": r.statut, "canal": canal.libelle, "objet": r.objet,
        "unite_reception": ctx.unite(unite_reception_id)["libelle"],
        "date_premiere_reception": iso(premiere), "date_reception_sr": iso(reception_sr)})
    return await detail(db, s, r, ctx)


async def modifier(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await charger(db, s, rid, verrou=True)
    if not peut_modifier(s, r):
        if r.statut in C.STATUTS_TERMINAUX or r.archivee_le:
            raise conflit("Dossier terminé : il n'est plus modifiable", "DOSSIER_TERMINE")
        s.exiger("reclamations.update")
    if data["revision"] != r.revision:
        raise conflit("Le dossier a été modifié entre-temps : rechargez-le", "CONFLIT_REVISION",
                      revision=r.revision)
    ctx = await Contexte.charger(db)
    effacer = set(data.get("effacer") or [])
    inconnus = effacer - EFFACABLES
    if inconnus:
        raise erreur(f"Champs non effaçables : {', '.join(sorted(inconnus))}", "CHAMP_INVALIDE")

    cible: dict[str, Any] = {}
    for champ in ("objet", "priorite", "client_categorie", "client_agence_id", "operation_date",
                  "montant_conteste", "reclamation_liee_id", "unite_reception_id", *CHAMPS_TEXTE):
        if data.get(champ) is not None:
            cible[champ] = data[champ]
    for champ in ("description", "client_adresse"):
        if data.get(champ) is not None:
            cible[champ] = texte_long(data[champ])
    if data.get("devise") is not None:
        cible["devise"] = propre(data["devise"]).upper() or None
    for champ in effacer:
        cible[champ] = None
    for champ in CHAMPS_TEXTE + ("objet",):
        if champ in cible and cible[champ] is not None:
            cible[champ] = propre(cible[champ]) or None
    if "objet" in cible and not cible["objet"]:
        raise erreur("L'objet est obligatoire", "CHAMPS_OBLIGATOIRES")
    if "description" in cible and not cible["description"]:
        raise erreur("La description est obligatoire", "CHAMPS_OBLIGATOIRES")
    if "client_nom" in cible and not cible["client_nom"]:
        raise erreur("Le nom du réclamant est obligatoire", "CLIENT_NOM_OBLIGATOIRE")
    if cible.get("carte_masquee"):
        cible["carte_masquee"] = _carte(cible["carte_masquee"])

    if any(k in data and data[k] is not None for k in ("type_id", "motif_id", "sous_motif_id")) or \
            effacer & {"type_id", "motif_id", "sous_motif_id"}:
        def valeur(k: str):
            return None if k in effacer else (data.get(k) if data.get(k) is not None else getattr(r, k))
        t, m, sm = _classement(ctx, valeur("type_id"), valeur("motif_id"), valeur("sous_motif_id"), actuel=r)
        cible.update(type_id=t, motif_id=m, sous_motif_id=sm)
    if "unite_reception_id" in cible:
        cible["unite_reception_id"] = _unite_reception(s, ctx, cible["unite_reception_id"], r.unite_reception_id)
    if cible.get("client_agence_id") and cible["client_agence_id"] not in ctx.agences:
        raise erreur("Agence du client introuvable", "AGENCE_INCONNUE")
    if data.get("client_racine") is not None:
        client = await _client(db, propre(data["client_racine"]) or None)
        cible["client_racine"] = client.racine_client if client else None
    if "reclamation_liee_id" in cible:
        cible["reclamation_liee_id"] = await _liee(db, s, cible["reclamation_liee_id"], r.id)

    if data.get("date_premiere_reception") is not None:
        cible["date_premiere_reception"] = _date_passee(data["date_premiere_reception"], "Date de première réception")
    if data.get("date_reception_sr") is not None:
        if r.date_reception_sr is None:
            raise conflit("La réception par le Service Réclamations s'enregistre par l'action dédiée",
                          "RECEPTION_SR_PAR_ACTION")
        cible["date_reception_sr"] = _date_passee(data["date_reception_sr"], "Date de réception SR")
    premiere = cible.get("date_premiere_reception", r.date_premiere_reception)
    reception_sr = cible.get("date_reception_sr", r.date_reception_sr)
    if reception_sr and reception_sr < premiere:
        raise erreur("La réception SR ne peut pas précéder la première réception", "DATE_INCOHERENTE")

    changes = {k: v for k, v in cible.items() if getattr(r, k) != v}
    if not changes:
        return await detail(db, s, r, ctx)
    motif = texte_long(data.get("motif"))
    if set(changes) & set(DATES_CLES) and not motif:
        raise erreur("Correction d'une date clé : le motif est obligatoire", "MOTIF_OBLIGATOIRE")
    avant = {k: serialisable(getattr(r, k)) for k in changes}
    for k, v in changes.items():
        setattr(r, k, v)
    r.revision += 1
    r.updated_by_id = s.user_id
    apres = {k: serialisable(v) for k, v in changes.items()}
    db.add(_evenement(r, s, "MODIFICATION", statut_avant=r.statut, etape_avant=r.etape, commentaire=motif,
                      donnees={"champs": [CHAMPS_LIBELLES.get(k, k) for k in changes]}))
    await db.flush()
    await auditer(db, s, "reclamations.dossier.update", C.GED_ENTITE, r.id, before=avant,
                  after={**apres, **({"motif": motif} if motif else {})})
    await db.refresh(r)
    return await detail(db, s, r, ctx)


async def ajouter_appel(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    r = await charger(db, s, rid, verrou=True)
    if not actions(s, r)["ajouter_appel"]:
        if r.statut in C.STATUTS_TERMINAUX:
            raise conflit("Dossier terminé : il n'est plus modifiable", "DOSSIER_TERMINE")
        s.exiger("reclamations.update")
    a = await _appel(db, s, r, data)
    db.add(_evenement(r, s, "APPEL", date_effet=a.appel_le, statut_avant=r.statut, etape_avant=r.etape,
                      commentaire=a.commentaire, donnees={"numero": a.numero_appelant, "rappel": a.rappel_statut}))
    r.revision += 1
    r.updated_by_id = s.user_id
    await db.flush()
    await auditer(db, s, "reclamations.appel.create", C.GED_ENTITE, r.id, after={
        "appel_le": iso(a.appel_le), "numero": a.numero_appelant, "identite_verifiee": a.identite_verifiee,
        "rappel": a.rappel_statut})
    await db.refresh(r)
    return await detail(db, s, r)
