"""Délais internes : règles paramétrables, calendrier ouvré, échéance du dossier, alertes.

Aucune règle n'est présentée comme réglementaire tant que la Conformité ne l'a pas validée
(``statut_validation = VALIDEE``). Sans règle applicable, aucune échéance n'est calculée.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Reclamation,
    ReclamationJourFerie,
    ReclamationRegleDelai,
    ReclamationUniteMembre,
)
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.dossiers import Contexte, charger, detail, ligne
from app.services.reclamations.notifier import destinataires_sr, notifier
from app.services.reclamations.outils import auditer, erreur, iso, maintenant, propre, texte_long


def _dt(d: date, fin: bool = False) -> datetime:
    return datetime.combine(d, time(23, 59, 59) if fin else time.min, tzinfo=maintenant().tzinfo)


async def jours_feries(db: AsyncSession) -> set[date]:
    return set((await db.scalars(select(ReclamationJourFerie.jour))).all())


def ajouter_jours(depart: datetime, n: int, unite: str, feries: set[date]) -> datetime:
    if n <= 0:
        return depart
    if unite != "JOURS_OUVRES":
        return depart + timedelta(days=n)
    j, reste = depart.date(), n
    while reste:
        j += timedelta(days=1)
        if j.weekday() < 5 and j not in feries:
            reste -= 1
    return _dt(j, fin=True).replace(tzinfo=depart.tzinfo)


def _dict(regle: ReclamationRegleDelai, ctx: Contexte | None = None) -> dict:
    return {
        "id": str(regle.id), "libelle": regle.libelle,
        "type_id": str(regle.type_id) if regle.type_id else None,
        "type": ctx.lib(regle.type_id) if ctx else None,
        "motif_id": str(regle.motif_id) if regle.motif_id else None,
        "motif": ctx.lib(regle.motif_id) if ctx else None,
        "priorite": regle.priorite,
        "priorite_libelle": C.PRIORITE_LIBELLES.get(regle.priorite or ""),
        "duree": regle.duree, "unite_duree": regle.unite_duree,
        "unite_duree_libelle": C.UNITE_DUREE_LIBELLES.get(regle.unite_duree),
        "point_depart": regle.point_depart,
        "point_depart_libelle": C.POINT_DEPART_LIBELLES.get(regle.point_depart),
        "seuil_alerte": regle.seuil_alerte, "delai_service": regle.delai_service,
        "neutraliser_suspension": regle.neutraliser_suspension,
        "date_effet": iso(regle.date_effet), "date_fin": iso(regle.date_fin),
        "statut_validation": regle.statut_validation,
        "statut_validation_libelle": C.VALIDATION_REGLE_LIBELLES.get(regle.statut_validation),
        "reglementaire": regle.statut_validation == "VALIDEE",
        "commentaire": regle.commentaire, "actif": regle.actif,
    }


async def lister_regles(db: AsyncSession) -> list[dict]:
    ctx = await Contexte.charger(db)
    rows = list((await db.scalars(select(ReclamationRegleDelai).order_by(
        ReclamationRegleDelai.actif.desc(), ReclamationRegleDelai.date_effet.desc()))).all())
    return [_dict(r, ctx) for r in rows]


async def _regle(db: AsyncSession, rid: uuid.UUID) -> ReclamationRegleDelai:
    r = await db.get(ReclamationRegleDelai, rid)
    if r is None:
        raise erreur("Règle de délai introuvable", "NOT_FOUND", 404)
    return r


def _cibles(data: dict, actuel: ReclamationRegleDelai | None = None) -> dict:
    cible = {
        "libelle": propre(data.get("libelle") or (actuel.libelle if actuel else "")),
        "type_id": data.get("type_id", actuel.type_id if actuel else None),
        "motif_id": data.get("motif_id", actuel.motif_id if actuel else None),
        "priorite": data.get("priorite", actuel.priorite if actuel else None),
        "duree": data.get("duree", actuel.duree if actuel else None),
        "unite_duree": data.get("unite_duree") or (actuel.unite_duree if actuel else "JOURS_CALENDAIRES"),
        "point_depart": data.get("point_depart") or (actuel.point_depart if actuel else "PREMIERE_RECEPTION"),
        "seuil_alerte": data.get("seuil_alerte", actuel.seuil_alerte if actuel else None),
        "delai_service": data.get("delai_service", actuel.delai_service if actuel else None),
        "neutraliser_suspension": data.get("neutraliser_suspension",
                                           actuel.neutraliser_suspension if actuel else True),
        "date_effet": data.get("date_effet", actuel.date_effet if actuel else None),
        "date_fin": data.get("date_fin", actuel.date_fin if actuel else None),
        "commentaire": texte_long(data.get("commentaire") if "commentaire" in data
                                  else (actuel.commentaire if actuel else None)),
    }
    if data.get("detacher_type"):
        cible["type_id"] = None
    if data.get("detacher_motif"):
        cible["motif_id"] = None
    if data.get("detacher_priorite"):
        cible["priorite"] = None
    if data.get("detacher_fin"):
        cible["date_fin"] = None
    if not cible["libelle"] or not cible["duree"] or not cible["date_effet"]:
        raise erreur("Libellé, durée et date d'effet sont obligatoires", "CHAMPS_OBLIGATOIRES")
    if cible["date_fin"] and cible["date_fin"] < cible["date_effet"]:
        raise erreur("La date de fin précède la date d'effet", "DATE_INCOHERENTE")
    return cible


async def creer_regle(db: AsyncSession, s: ReclamationsScope, data: dict) -> dict:
    s.exiger("reclamations.delais.manage")
    ctx = await Contexte.charger(db)
    cible = _cibles(data)
    if cible["type_id"] and cible["type_id"] not in ctx.refs:
        raise erreur("Type introuvable", "REFERENTIEL_INCONNU")
    if cible["motif_id"] and cible["motif_id"] not in ctx.refs:
        raise erreur("Motif introuvable", "REFERENTIEL_INCONNU")
    r = ReclamationRegleDelai(**cible, statut_validation="A_VALIDER", created_by_id=s.user_id)
    db.add(r)
    await db.flush()
    await auditer(db, s, "reclamations.delai.create", "reclamation_regle_delai", r.id, after=_dict(r, ctx))
    return _dict(r, ctx)


async def modifier_regle(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    s.exiger("reclamations.delais.manage")
    r = await _regle(db, rid)
    ctx = await Contexte.charger(db)
    avant = _dict(r, ctx)
    for k, v in _cibles(data, r).items():
        setattr(r, k, v)
    if r.statut_validation == "VALIDEE" and any(k in data for k in ("duree", "unite_duree", "point_depart")):
        r.statut_validation = "A_VALIDER"
        r.valide_par_id = None
        r.valide_le = None
    r.updated_by_id = s.user_id
    if data.get("actif") is not None:
        r.actif = bool(data["actif"])
    await db.flush()
    await auditer(db, s, "reclamations.delai.update", "reclamation_regle_delai", r.id,
                  before=avant, after=_dict(r, ctx))
    return _dict(r, ctx)


async def valider_regle(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    s.exiger("reclamations.delais.validate")
    r = await _regle(db, rid)
    r.statut_validation = data["statut_validation"]
    r.valide_par_id = s.user_id
    r.valide_le = maintenant()
    r.commentaire = texte_long(data.get("commentaire")) or r.commentaire
    r.updated_by_id = s.user_id
    await db.flush()
    await auditer(db, s, "reclamations.delai.validate", "reclamation_regle_delai", r.id,
                  after={"statut": r.statut_validation})
    return _dict(r, await Contexte.charger(db))


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


def _score(regle: ReclamationRegleDelai, r: Reclamation) -> int | None:
    if not regle.actif or (regle.date_fin and r.date_premiere_reception.date() > regle.date_fin):
        return None
    if r.date_premiere_reception.date() < regle.date_effet:
        return None
    if regle.motif_id and regle.motif_id != r.motif_id:
        return None
    if regle.type_id and regle.type_id != r.type_id:
        return None
    if regle.priorite and regle.priorite != r.priorite:
        return None
    return (4 if regle.motif_id else 0) + (2 if regle.type_id else 0) + (1 if regle.priorite else 0)


async def appliquer(db: AsyncSession, r: Reclamation, *, forcer: bool = False) -> None:
    """Calcule l'échéance si une règle s'applique. Ne remplace une échéance déjà figée que si ``forcer``."""
    if r.echeance and not forcer:
        return
    regles = list((await db.scalars(select(ReclamationRegleDelai).where(ReclamationRegleDelai.actif.is_(True)))).all())
    candidates = [(sc, g) for g in regles if (sc := _score(g, r)) is not None]
    if not candidates:
        r.regle_delai_id = None
        return
    candidates.sort(key=lambda x: x[0], reverse=True)
    regle = candidates[0][1]
    depart = r.date_premiere_reception
    if regle.point_depart == "RECEPTION_SR" and r.date_reception_sr:
        depart = r.date_reception_sr
    echeance = ajouter_jours(depart, regle.duree, regle.unite_duree, await jours_feries(db))
    r.regle_delai_id = regle.id
    r.echeance = echeance
    if r.echeance_initiale is None:
        r.echeance_initiale = echeance


async def decaler_apres_suspension(db: AsyncSession, r: Reclamation) -> None:
    if not r.echeance or not r.date_suspension:
        return
    regle = await db.get(ReclamationRegleDelai, r.regle_delai_id) if r.regle_delai_id else None
    if regle and not regle.neutraliser_suspension:
        return
    r.echeance = r.echeance + (maintenant() - r.date_suspension)


async def echeance_service(db: AsyncSession, r: Reclamation, transmis_le: datetime) -> datetime | None:
    if not r.regle_delai_id:
        return None
    regle = await db.get(ReclamationRegleDelai, r.regle_delai_id)
    if not regle or not regle.delai_service:
        return None
    return ajouter_jours(transmis_le, regle.delai_service, regle.unite_duree, await jours_feries(db))


async def alertes(db: AsyncSession, s: ReclamationsScope) -> dict:
    """Dossiers du périmètre en retard ou proches du seuil d'alerte."""
    ctx = await Contexte.charger(db)
    now = maintenant()
    rows = list((await db.scalars(select(Reclamation).where(
        s.filtre_dossiers(), Reclamation.archivee_le.is_(None),
        Reclamation.statut.not_in(C.STATUTS_TERMINAUX), Reclamation.echeance.is_not(None),
    ).order_by(Reclamation.echeance))).all())
    retards, alertes_ = [], []
    for r in rows:
        item = ligne(r, ctx)
        if r.echeance < now:
            retards.append(item)
            continue
        regle = await db.get(ReclamationRegleDelai, r.regle_delai_id) if r.regle_delai_id else None
        if regle and regle.seuil_alerte is not None and r.echeance <= now + timedelta(days=regle.seuil_alerte):
            item["jours_restants"] = (r.echeance.date() - now.date()).days
            alertes_.append(item)
    return {"retards": retards, "alertes": alertes_, "nb_retards": len(retards), "nb_alertes": len(alertes_)}


async def envoyer_alertes(db: AsyncSession) -> dict:
    """Job quotidien : notifie le SR et le service destinataire des dossiers en retard / à échéance."""
    ctx = await Contexte.charger(db)
    now = maintenant()
    rows = list((await db.scalars(select(Reclamation).where(
        Reclamation.archivee_le.is_(None), Reclamation.statut.not_in(C.STATUTS_TERMINAUX),
        Reclamation.echeance.is_not(None),
    ))).all())
    sr = await destinataires_sr(db, ctx)
    systeme = type("S", (), {"user_id": None})()
    n = 0
    for r in rows:
        dest = set(sr)
        dest |= await membres_unite_safe(db, r.unite_traitement_id)
        dest |= await membres_unite_safe(db, r.unite_suivi_id)
        if r.echeance < now:
            titre, msg, prio = "Réclamation en retard", f"{r.reference} a dépassé son échéance.", "haute"
        else:
            regle = await db.get(ReclamationRegleDelai, r.regle_delai_id) if r.regle_delai_id else None
            if not (regle and regle.seuil_alerte is not None
                    and r.echeance <= now + timedelta(days=regle.seuil_alerte)):
                continue
            titre, msg, prio = "Échéance proche", f"{r.reference} arrive à échéance.", "normale"
        await notifier(db, systeme, r, destinataires=dest, titre=titre, message=msg, priorite=prio)
        n += 1
    await db.commit()
    return {"notifies": n}


async def membres_unite_safe(db: AsyncSession, unite_id: uuid.UUID | None) -> set[uuid.UUID]:
    if not unite_id:
        return set()
    return set((await db.scalars(select(ReclamationUniteMembre.user_id).where(
        ReclamationUniteMembre.unite_id == unite_id, ReclamationUniteMembre.actif.is_(True),
    ))).all())


async def recap_dossier(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID) -> dict:
    r = await charger(db, s, rid)
    ctx = await Contexte.charger(db)
    regle = await db.get(ReclamationRegleDelai, r.regle_delai_id) if r.regle_delai_id else None
    return {
        **(await detail(db, s, r, ctx)),
        "regle": _dict(regle, ctx) if regle else None,
        "reglementaire": bool(regle and regle.statut_validation == "VALIDEE"),
    }
