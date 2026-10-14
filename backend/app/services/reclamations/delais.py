"""Délais & alertes : règles paramétrables (versions, validation), calendrier, échéances, alertes.

Le calcul lui-même vit dans ``echeances`` (une seule définition). Ce module gère :
- le cycle de vie des règles : création (à valider), modification, activation, validation
  Conformité, versions à date d'effet, historique (journal d'audit) ;
- l'application aux dossiers : à l'enregistrement, à la qualification, sur action explicite
  « appliquer aux dossiers sans délai » (jamais de recalcul silencieux de l'historique) ;
- les alertes : une notification par franchissement de niveau (proche → retard), sans doublon.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Reclamation, ReclamationJourFerie, ReclamationRegleDelai
from app.services.reclamations import constantes as C
from app.services.reclamations import echeances as E
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.dossiers import Contexte, _evenement, charger, detail, ligne
from app.services.reclamations.notifier import destinataires_sr, membres_unite, notifier
from app.services.reclamations.outils import (
    auditer,
    conflit,
    erreur,
    iso,
    maintenant,
    noms_utilisateurs,
    propre,
    texte_long,
)

ENTITE = "reclamation_regle_delai"
# Champs qui changent le calcul d'une échéance : figés dès qu'un dossier utilise la règle.
CHAMPS_CALCUL = ("type_id", "motif_id", "sous_motif_id", "priorite", "duree", "unite_duree",
                 "point_depart", "point_arrivee", "date_effet")
ETAT_REGLE_LIBELLES = {
    "APPLIQUEE": "Validée et appliquée",
    "PROGRAMMEE": "Validée — prend effet plus tard",
    "EN_ATTENTE_VALIDATION": "En attente de validation (non appliquée)",
    "REJETEE": "Rejetée",
    "INACTIVE": "Désactivée",
    "EXPIREE": "Période terminée",
}
LIMITE_LISTE = 200

ajouter_jours = E.ajouter_jours


async def jours_feries(db: AsyncSession) -> set[date]:
    return set((await db.scalars(select(ReclamationJourFerie.jour))).all())


async def _regles(db: AsyncSession) -> list[ReclamationRegleDelai]:
    return list((await db.scalars(select(ReclamationRegleDelai))).all())


def etat_effectif(regle: ReclamationRegleDelai, jour: date) -> str:
    if regle.statut_validation == "REJETEE":
        return "REJETEE"
    if not regle.actif:
        return "INACTIVE"
    if regle.date_fin and regle.date_fin < jour:
        return "EXPIREE"
    if regle.statut_validation != "VALIDEE":
        return "EN_ATTENTE_VALIDATION"
    if regle.date_effet > jour:
        return "PROGRAMMEE"
    return "APPLIQUEE"


def _chevauche(a: ReclamationRegleDelai, b: ReclamationRegleDelai) -> bool:
    fin_a, fin_b = a.date_fin or date.max, b.date_fin or date.max
    return a.date_effet <= fin_b and b.date_effet <= fin_a


def conflits(regle: ReclamationRegleDelai, regles: list[ReclamationRegleDelai], *,
             ignorer: set[uuid.UUID] | None = None) -> list[ReclamationRegleDelai]:
    """Règles validées et actives, même portée, périodes qui se chevauchent, paramètres différents."""
    ignorer = ignorer or set()
    return [g for g in regles
            if g.id != regle.id and g.id not in ignorer and g.actif and g.statut_validation == "VALIDEE"
            and E.portee(g) == E.portee(regle) and _chevauche(g, regle) and E.signature(g) != E.signature(regle)]


def _dict(regle: ReclamationRegleDelai, ctx: Contexte | None = None, *, regles: list | None = None,
          nb_dossiers: int | None = None) -> dict:
    jour = maintenant().date()
    etat = etat_effectif(regle, jour)
    out = {
        "id": str(regle.id), "libelle": regle.libelle,
        "type_id": str(regle.type_id) if regle.type_id else None,
        "type": ctx.lib(regle.type_id) if ctx else None,
        "motif_id": str(regle.motif_id) if regle.motif_id else None,
        "motif": ctx.lib(regle.motif_id) if ctx else None,
        "sous_motif_id": str(regle.sous_motif_id) if regle.sous_motif_id else None,
        "sous_motif": ctx.lib(regle.sous_motif_id) if ctx else None,
        "priorite": regle.priorite,
        "priorite_libelle": C.PRIORITE_LIBELLES.get(regle.priorite or ""),
        "specificite": E.specificite(regle),
        "duree": regle.duree, "unite_duree": regle.unite_duree,
        "unite_duree_libelle": C.UNITE_DUREE_LIBELLES.get(regle.unite_duree),
        "point_depart": regle.point_depart,
        "point_depart_libelle": C.POINT_DEPART_LIBELLES.get(regle.point_depart),
        "point_arrivee": regle.point_arrivee,
        "point_arrivee_libelle": C.POINT_ARRIVEE_LIBELLES.get(regle.point_arrivee),
        "seuil_alerte": regle.seuil_alerte, "delai_service": regle.delai_service,
        "neutraliser_suspension": regle.neutraliser_suspension,
        "destinataires": list(regle.destinataires or []),
        "destinataires_libelles": [C.DESTINATAIRES_ALERTE.get(d, d) for d in (regle.destinataires or [])],
        "date_effet": iso(regle.date_effet), "date_fin": iso(regle.date_fin),
        "statut_validation": regle.statut_validation,
        "statut_validation_libelle": C.VALIDATION_REGLE_LIBELLES.get(regle.statut_validation),
        "valide_le": iso(regle.valide_le),
        "reglementaire": regle.statut_validation == "VALIDEE",
        "etat_effectif": etat, "etat_effectif_libelle": ETAT_REGLE_LIBELLES[etat],
        "commentaire": regle.commentaire, "actif": regle.actif,
        "remplace_id": str(regle.remplace_id) if regle.remplace_id else None,
        "updated_at": iso(regle.updated_at),
    }
    if regles is not None:
        out["conflits"] = [str(g.id) for g in conflits(regle, regles)] if regle.statut_validation == "VALIDEE" else []
        out["remplacee_par"] = next((str(g.id) for g in regles if g.remplace_id == regle.id), None)
    if nb_dossiers is not None:
        out["nb_dossiers"] = nb_dossiers
    return out


async def _usages(db: AsyncSession) -> dict[uuid.UUID, int]:
    return dict((await db.execute(select(Reclamation.regle_delai_id, func.count()).where(
        Reclamation.regle_delai_id.is_not(None)).group_by(Reclamation.regle_delai_id))).all())


async def lister_regles(db: AsyncSession) -> list[dict]:
    ctx = await Contexte.charger(db)
    regles = await _regles(db)
    usages = await _usages(db)
    regles.sort(key=lambda g: (not g.actif, g.statut_validation != "VALIDEE", -g.date_effet.toordinal(), g.libelle))
    return [_dict(g, ctx, regles=regles, nb_dossiers=usages.get(g.id, 0)) for g in regles]


async def _regle(db: AsyncSession, rid: uuid.UUID) -> ReclamationRegleDelai:
    r = await db.get(ReclamationRegleDelai, rid)
    if r is None:
        raise erreur("Règle de délai introuvable", "NOT_FOUND", 404)
    return r


def _cibles(data: dict, actuel: ReclamationRegleDelai | None = None) -> dict:
    def val(cle: str, defaut=None):
        return data[cle] if cle in data and data[cle] is not None else (getattr(actuel, cle) if actuel else defaut)

    cible = {
        "libelle": propre(data.get("libelle") or (actuel.libelle if actuel else "")),
        "type_id": val("type_id"), "motif_id": val("motif_id"), "sous_motif_id": val("sous_motif_id"),
        "priorite": val("priorite"), "duree": val("duree"),
        "unite_duree": val("unite_duree", "JOURS_CALENDAIRES"),
        "point_depart": val("point_depart", "PREMIERE_RECEPTION"),
        "point_arrivee": val("point_arrivee", "CLOTURE"),
        "seuil_alerte": val("seuil_alerte"), "delai_service": val("delai_service"),
        "neutraliser_suspension": val("neutraliser_suspension", True),
        "destinataires": list(val("destinataires", []) or []),
        "date_effet": val("date_effet"), "date_fin": val("date_fin"),
        "commentaire": texte_long(data.get("commentaire") if "commentaire" in data
                                  else (actuel.commentaire if actuel else None)),
    }
    for champ, cle in (("type_id", "detacher_type"), ("motif_id", "detacher_motif"),
                       ("sous_motif_id", "detacher_sous_motif"), ("priorite", "detacher_priorite"),
                       ("date_fin", "detacher_fin"), ("seuil_alerte", "detacher_seuil"),
                       ("delai_service", "detacher_delai_service")):
        if data.get(cle):
            cible[champ] = None
    if not cible["libelle"] or not cible["duree"] or not cible["date_effet"]:
        raise erreur("Libellé, durée et date d'effet sont obligatoires", "CHAMPS_OBLIGATOIRES")
    if cible["date_fin"] and cible["date_fin"] < cible["date_effet"]:
        raise erreur("La date de fin précède la date d'effet", "DATE_INCOHERENTE")
    if cible["seuil_alerte"] is not None and cible["seuil_alerte"] >= cible["duree"]:
        raise erreur("Le seuil d'alerte doit être inférieur à la durée du délai", "SEUIL_INVALIDE")
    if cible["delai_service"] is not None and cible["delai_service"] > cible["duree"]:
        raise erreur("Le délai du service ne peut pas dépasser le délai global", "DELAI_SERVICE_INVALIDE")
    inconnus = [d for d in cible["destinataires"] if d not in C.DESTINATAIRES_ALERTE]
    if inconnus:
        raise erreur(f"Destinataire d'alerte inconnu : {', '.join(inconnus)}", "DESTINATAIRE_INVALIDE")
    cible["destinataires"] = sorted(set(cible["destinataires"]))
    return cible


def _verifier_portee(ctx: Contexte, cible: dict) -> None:
    """Type → motif → sous-motif cohérents ; les parents manquants sont complétés."""
    def ref(rid, domaine: str):
        if rid is None:
            return None
        g = ctx.refs.get(rid)
        if g is None or g.domaine != domaine:
            raise erreur(f"{C.DOMAINE_LIBELLES[domaine]} introuvable", "REFERENTIEL_INCONNU")
        return g

    sm = ref(cible["sous_motif_id"], "SOUS_MOTIF")
    if sm:
        if cible["motif_id"] and cible["motif_id"] != sm.parent_id:
            raise erreur("Le sous-motif n'appartient pas au motif choisi", "CLASSEMENT_INCOHERENT")
        cible["motif_id"] = sm.parent_id
    m = ref(cible["motif_id"], "MOTIF")
    if m:
        if cible["type_id"] and cible["type_id"] != m.parent_id:
            raise erreur("Le motif n'appartient pas au type choisi", "CLASSEMENT_INCOHERENT")
        cible["type_id"] = m.parent_id
    ref(cible["type_id"], "TYPE")


async def creer_regle(db: AsyncSession, s: ReclamationsScope, data: dict, *,
                      remplace: ReclamationRegleDelai | None = None) -> dict:
    s.exiger("reclamations.delais.manage")
    ctx = await Contexte.charger(db)
    cible = _cibles(data, remplace)
    _verifier_portee(ctx, cible)
    r = ReclamationRegleDelai(**cible, statut_validation="A_VALIDER", actif=True,
                              remplace_id=remplace.id if remplace else None,
                              created_by_id=s.user_id, updated_by_id=s.user_id)
    db.add(r)
    await db.flush()
    await auditer(db, s, "reclamations.delai.version" if remplace else "reclamations.delai.create", ENTITE, r.id,
                  before=_dict(remplace, ctx) if remplace else None, after=_dict(r, ctx))
    return _dict(r, ctx, regles=await _regles(db), nb_dossiers=0)


async def versionner_regle(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    """Nouvelle version à date d'effet : l'ancienne reste appliquée à sa période (bornée à la validation)."""
    s.exiger("reclamations.delais.manage")
    ancienne = await _regle(db, rid)
    if not data.get("date_effet") or data["date_effet"] <= ancienne.date_effet:
        raise erreur("La nouvelle version doit prendre effet après la version actuelle", "DATE_EFFET_INVALIDE")
    if await db.scalar(select(func.count()).where(ReclamationRegleDelai.remplace_id == ancienne.id,
                                                  ReclamationRegleDelai.statut_validation != "REJETEE")):
        raise conflit("Une nouvelle version de cette règle existe déjà", "VERSION_EXISTANTE")
    # Seuil, délai service et fin peuvent être vidés ; la fin n'est jamais reprise de l'ancienne version.
    return await creer_regle(db, s, {**data, "detacher_fin": not data.get("date_fin")}, remplace=ancienne)


async def modifier_regle(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    s.exiger("reclamations.delais.manage")
    r = await _regle(db, rid)
    ctx = await Contexte.charger(db)
    avant = _dict(r, ctx)
    cible = _cibles(data, r)
    _verifier_portee(ctx, cible)
    change_calcul = [k for k in CHAMPS_CALCUL if cible[k] != getattr(r, k)]
    if change_calcul:
        n = await db.scalar(select(func.count()).where(Reclamation.regle_delai_id == r.id)) or 0
        if n:
            raise conflit(f"Règle déjà appliquée à {n} dossier(s) : ses paramètres de calcul sont figés. "
                          "Créez une nouvelle version à date d'effet.", "REGLE_UTILISEE", dossiers=n)
    for k, v in cible.items():
        setattr(r, k, v)
    if r.statut_validation != "A_VALIDER" and change_calcul:
        r.statut_validation, r.valide_par_id, r.valide_le = "A_VALIDER", None, None
    if data.get("actif") is not None:
        r.actif = bool(data["actif"])
    r.updated_by_id = s.user_id
    await db.flush()
    await auditer(db, s, "reclamations.delai.update", ENTITE, r.id, before=avant, after=_dict(r, ctx))
    regles = await _regles(db)
    return _dict(r, ctx, regles=regles, nb_dossiers=(await _usages(db)).get(r.id, 0))


async def valider_regle(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    s.exiger("reclamations.delais.validate")
    r = await _regle(db, rid)
    ctx = await Contexte.charger(db)
    avant = _dict(r, ctx)
    statut = data["statut_validation"]
    regles = await _regles(db)
    ancienne = await db.get(ReclamationRegleDelai, r.remplace_id) if r.remplace_id else None
    if statut == "VALIDEE":
        opposees = conflits(r, regles, ignorer={ancienne.id} if ancienne else set())
        if opposees:
            raise conflit("Une règle validée de même portée et de période commune fixe un délai différent : "
                          "arbitrez (désactivez ou bornez l'une des deux) avant validation.", "REGLE_CONFLIT",
                          regles=[g.libelle for g in opposees])
    r.statut_validation = statut
    r.valide_par_id = s.user_id
    r.valide_le = maintenant()
    r.commentaire = texte_long(data.get("commentaire")) or r.commentaire
    r.updated_by_id = s.user_id
    if statut == "VALIDEE" and ancienne is not None:
        borne = r.date_effet - timedelta(days=1)
        if ancienne.date_fin is None or ancienne.date_fin > borne:
            avant_anc = _dict(ancienne, ctx)
            ancienne.date_fin = borne
            ancienne.updated_by_id = s.user_id
            await auditer(db, s, "reclamations.delai.update", ENTITE, ancienne.id, before=avant_anc,
                          after={**_dict(ancienne, ctx), "remplacee_par": str(r.id)})
    await db.flush()
    await auditer(db, s, "reclamations.delai.validate", ENTITE, r.id, before=avant, after=_dict(r, ctx))
    return _dict(r, ctx, regles=await _regles(db), nb_dossiers=(await _usages(db)).get(r.id, 0))


async def historique_regle(db: AsyncSession, rid: uuid.UUID) -> dict:
    """Journal d'audit de la règle et de ses versions (création, modifications, validation)."""
    r = await _regle(db, rid)
    chaine: list[ReclamationRegleDelai] = [r]
    precedente = r
    while precedente.remplace_id:
        precedente = await db.get(ReclamationRegleDelai, precedente.remplace_id)
        if precedente is None or precedente in chaine:
            break
        chaine.append(precedente)
    suivante = r
    while True:
        suivante = await db.scalar(select(ReclamationRegleDelai).where(ReclamationRegleDelai.remplace_id == suivante.id))
        if suivante is None or suivante in chaine:
            break
        chaine.insert(0, suivante)
    logs = list((await db.scalars(select(AuditLog).where(
        AuditLog.entity == ENTITE, AuditLog.entity_id.in_([str(g.id) for g in chaine]),
    ).order_by(AuditLog.created_at.desc()).limit(LIMITE_LISTE))).all())
    noms = await noms_utilisateurs(db, {lg.user_id for lg in logs})
    ctx = await Contexte.charger(db)
    return {
        "versions": [_dict(g, ctx) for g in chaine],
        "evenements": [{
            "id": str(lg.id), "action": lg.action, "regle_id": lg.entity_id, "le": iso(lg.created_at),
            "auteur": noms.get(lg.user_id) if lg.user_id else None,
            "avant": lg.before_data, "apres": lg.after_data,
        } for lg in logs],
    }


async def lister_feries(db: AsyncSession) -> list[dict]:
    rows = list((await db.scalars(select(ReclamationJourFerie).order_by(ReclamationJourFerie.jour))).all())
    return [{"jour": iso(j.jour), "libelle": j.libelle} for j in rows]


async def ajouter_ferie(db: AsyncSession, s: ReclamationsScope, data: dict) -> list[dict]:
    s.exiger("reclamations.delais.manage")
    if await db.get(ReclamationJourFerie, data["jour"]):
        raise erreur("Ce jour est déjà enregistré", "JOUR_EXISTANT")
    db.add(ReclamationJourFerie(jour=data["jour"], libelle=propre(data["libelle"]), created_by_id=s.user_id))
    await db.flush()
    await auditer(db, s, "reclamations.ferie.create", "reclamation_jour_ferie", str(data["jour"]),
                  after={"jour": iso(data["jour"]), "libelle": data["libelle"]})
    return await lister_feries(db)


async def retirer_ferie(db: AsyncSession, s: ReclamationsScope, jour: date) -> list[dict]:
    s.exiger("reclamations.delais.manage")
    row = await db.get(ReclamationJourFerie, jour)
    if row is None:
        raise erreur("Jour férié introuvable", "NOT_FOUND", 404)
    await db.delete(row)
    await auditer(db, s, "reclamations.ferie.delete", "reclamation_jour_ferie", str(jour),
                  before={"jour": iso(jour)})
    return await lister_feries(db)


# ------------------------------------------------------------------ application aux dossiers
async def appliquer(db: AsyncSession, r: Reclamation, *, forcer: bool = False) -> None:
    """Calcule l'échéance si une règle validée s'applique. Ne remplace une échéance figée que si ``forcer``."""
    if r.echeance and not forcer:
        return
    E.poser(r, E.selectionner(await _regles(db), r), await jours_feries(db))
    await actualiser(db, r)


async def actualiser(db: AsyncSession, r: Reclamation) -> None:
    """Après chaque étape du circuit : départ survenu, arrêt du délai, remise à zéro du niveau d'alerte."""
    if r.etat_delai == "SANS_DEPART":
        E.poser(r, E.selectionner(await _regles(db), r), await jours_feries(db))
    regle = await db.get(ReclamationRegleDelai, r.regle_delai_id) if r.regle_delai_id else None
    fin = E.fin_delai(r, regle)
    if r.date_fin_delai is not None and fin is None:
        r.niveau_alerte = None
    r.date_fin_delai = fin


async def echeance_service(db: AsyncSession, r: Reclamation, transmis_le: datetime) -> datetime | None:
    if not r.regle_delai_id or not E.calcule(r):
        return None
    regle = await db.get(ReclamationRegleDelai, r.regle_delai_id)
    if not regle or not regle.delai_service:
        return None
    return E.ajouter_jours(transmis_le, regle.delai_service, regle.unite_duree, await jours_feries(db))


async def appliquer_sans_delai(db: AsyncSession, s: ReclamationsScope) -> dict:
    """Action explicite : applique les règles validées aux dossiers ouverts sans échéance.

    Les échéances déjà calculées ne sont jamais modifiées ; chaque calcul est tracé dans l'historique."""
    s.exiger("reclamations.delais.manage")
    rows = list((await db.scalars(select(Reclamation).where(
        Reclamation.supprimee_le.is_(None), Reclamation.archivee_le.is_(None),
        Reclamation.statut.not_in(C.STATUTS_TERMINAUX), Reclamation.echeance.is_(None),
    ).with_for_update())).all())
    regles, feries = await _regles(db), await jours_feries(db)
    calcules, restants = 0, {}
    for r in rows:
        E.poser(r, E.selectionner(regles, r), feries)
        if r.etat_delai == "CALCULE":
            calcules += 1
            db.add(_evenement(r, s, "DELAI_CALCULE", donnees={
                "echeance": iso(r.echeance), "regle_id": str(r.regle_delai_id)}))
        else:
            restants[r.etat_delai] = restants.get(r.etat_delai, 0) + 1
    await db.flush()
    await auditer(db, s, "reclamations.delai.apply", ENTITE, None,
                  after={"examines": len(rows), "calcules": calcules, "restants": restants})
    return {"examines": len(rows), "calcules": calcules, "restants": restants}


# ------------------------------------------------------------------------------ alertes
def niveau(r: Reclamation, now: datetime) -> str | None:
    sit = E.situation(r, now)
    return {"EN_RETARD": "RETARD", "ECHEANCE_PROCHE": "PROCHE"}.get(sit)


async def alertes(db: AsyncSession, s: ReclamationsScope) -> dict:
    """Dossiers du périmètre en retard, proches de l'échéance, ou sans délai calculable."""
    ctx = await Contexte.charger(db)
    now = maintenant()
    base = select(Reclamation).where(s.filtre_dossiers(), Reclamation.archivee_le.is_(None))
    retards = list((await db.scalars(base.where(E.sql_situation("EN_RETARD", now))
                                     .order_by(Reclamation.echeance).limit(LIMITE_LISTE))).all())
    proches = list((await db.scalars(base.where(E.sql_situation("ECHEANCE_PROCHE", now))
                                     .order_by(Reclamation.echeance).limit(LIMITE_LISTE))).all())
    sans = list((await db.scalars(base.where(
        Reclamation.statut.not_in(C.STATUTS_TERMINAUX), ~E.sql_calcule(),
    ).order_by(Reclamation.date_premiere_reception).limit(LIMITE_LISTE))).all())
    comptes = dict((await db.execute(select(func.coalesce(Reclamation.etat_delai, "NON_CONFIGURE"), func.count())
                                     .where(s.filtre_dossiers(), Reclamation.archivee_le.is_(None),
                                            Reclamation.statut.not_in(C.STATUTS_TERMINAUX), ~E.sql_calcule())
                                     .group_by(text("1")))).all())
    nb_retards = await db.scalar(select(func.count()).select_from(base.where(
        E.sql_situation("EN_RETARD", now)).subquery())) or 0
    nb_proches = await db.scalar(select(func.count()).select_from(base.where(
        E.sql_situation("ECHEANCE_PROCHE", now)).subquery())) or 0

    def item(r: Reclamation) -> dict:
        d = ligne(r, ctx)
        if r.echeance:
            d["jours_restants"] = (r.echeance.date() - now.date()).days
        return d

    return {
        "retards": [item(r) for r in retards], "alertes": [item(r) for r in proches],
        "sans_delai": [item(r) for r in sans],
        "nb_retards": nb_retards, "nb_alertes": nb_proches,
        "nb_sans_delai": sum(comptes.values()),
        "sans_delai_par_etat": [{"etat": k, "libelle": C.ETAT_DELAI_LIBELLES.get(k, k), "n": v}
                                for k, v in sorted(comptes.items())],
    }


async def _destinataires(db: AsyncSession, r: Reclamation, regle: ReclamationRegleDelai | None,
                         sr: set[uuid.UUID]) -> set[uuid.UUID]:
    choix = set((regle.destinataires if regle else None) or ("SR", "SERVICE_TRAITEMENT"))
    dest: set[uuid.UUID] = set()
    if "SR" in choix:
        dest |= sr
    if "SERVICE_TRAITEMENT" in choix:
        dest |= await membres_unite(db, r.unite_traitement_id)
        dest |= await membres_unite(db, r.unite_suivi_id)
    if "GESTIONNAIRE" in choix and r.gestionnaire_id:
        dest.add(r.gestionnaire_id)
    return dest


async def envoyer_alertes(db: AsyncSession) -> dict:
    """Job périodique : notifie au franchissement d'un niveau (proche, retard), jamais deux fois le même."""
    ctx = await Contexte.charger(db)
    now = maintenant()
    rows = list((await db.scalars(select(Reclamation).where(
        Reclamation.archivee_le.is_(None), Reclamation.supprimee_le.is_(None),
        or_(and_(E.sql_calcule(), E.sql_fin().is_(None)), Reclamation.niveau_alerte.is_not(None)),
    ))).all())
    sr = await destinataires_sr(db, ctx)
    systeme = type("S", (), {"user_id": None})()
    notifies = 0
    for r in rows:
        cible = niveau(r, now)
        if cible == r.niveau_alerte:
            continue
        valeurs: dict = {"niveau_alerte": cible, "updated_at": Reclamation.updated_at}
        if cible is not None:
            regle = await db.get(ReclamationRegleDelai, r.regle_delai_id) if r.regle_delai_id else None
            if cible == "RETARD":
                titre, msg, prio = "Réclamation en retard", f"{r.reference} a dépassé son échéance.", "haute"
            else:
                titre, msg, prio = "Échéance proche", f"{r.reference} arrive à échéance.", "normale"
            await notifier(db, systeme, r, destinataires=await _destinataires(db, r, regle, sr),
                           titre=titre, message=msg, priorite=prio)
            valeurs["alerte_notifiee_le"] = now
            notifies += 1
        await db.execute(update(Reclamation).where(Reclamation.id == r.id).values(**valeurs))
    await db.commit()
    return {"notifies": notifies}


async def recap_dossier(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID) -> dict:
    r = await charger(db, s, rid)
    ctx = await Contexte.charger(db)
    regle = await db.get(ReclamationRegleDelai, r.regle_delai_id) if r.regle_delai_id else None
    return {
        **(await detail(db, s, r, ctx)),
        "regle": _dict(regle, ctx) if regle else None,
        "reglementaire": bool(regle and regle.statut_validation == "VALIDEE"),
    }
