"""Indicateurs de pilotage : quatre délais, réouverture, performance des services, comparaison.

Principes (cf. ``docs/conformite/reclamations.md``) :
- tout est agrégé côté serveur, dans le périmètre de l'utilisateur et avec les mêmes filtres que
  la liste (agence — y compris « sans agence » —, type, motif, canal, priorité, unités…) ;
- la **période** porte sur la date de l'événement mesuré (fin d'un délai, clôture, réouverture,
  transmission, retour), jamais sur une date reconstituée ;
- chaque indicateur cliquable a son filtre de liste (``indicateur`` + ``kpi_debut`` / ``kpi_fin`` /
  ``kpi_unite_id``) construit avec **la même condition SQL** : le compte affiché = le total de la liste ;
- les comptes sont des dossiers distincts (``COUNT(DISTINCT)``), jamais des lignes de jointure ;
- durée négative = anomalie de saisie : exclue de la moyenne, comptée et listée ;
- aucune donnée : la moyenne vaut ``None`` (affichée « N/A »), jamais 0.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, and_, distinct, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Reclamation, ReclamationAffectation, ReclamationEvenement, ReclamationOperation
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.outils import erreur, maintenant

A = ReclamationAffectation
EV = ReclamationEvenement
EN_COURS_AFFECTATION = ("TRANSMISE", "RECUE", "EN_TRAITEMENT")
LIMITE_ANOMALIES = 20


def borne(d: date | None, *, fin: bool = False) -> datetime | None:
    """Même conversion que les filtres de date de la liste (jour local, borne de fin exclusive)."""
    if d is None:
        return None
    return datetime.combine(d + timedelta(days=1) if fin else d, datetime.min.time()).astimezone()


@dataclass(frozen=True)
class Periode:
    debut: datetime | None = None
    fin: datetime | None = None
    jour_debut: date | None = None
    jour_fin: date | None = None

    @classmethod
    def de(cls, debut: date | None, fin: date | None) -> Periode:
        if debut and fin and fin < debut:
            raise erreur("La date de fin précède la date de début", "PERIODE_INVALIDE")
        return cls(borne(debut), borne(fin, fin=True), debut, fin)

    def contient(self, col):
        conds = [col.is_not(None)]
        if self.debut is not None:
            conds.append(col >= self.debut)
        if self.fin is not None:
            conds.append(col < self.fin)
        return and_(*conds)

    @property
    def jours(self) -> int | None:
        if self.jour_debut and self.jour_fin:
            return (self.jour_fin - self.jour_debut).days + 1
        return None


# ------------------------------------------------------------------ définitions des délais
@dataclass(frozen=True)
class Delai:
    code: str
    libelle: str
    definition: str
    sur_fiches: bool = False


DELAIS = (
    Delai("prise_en_charge", "Délai de prise en charge",
          "Première réception par la banque → réception par le Service Réclamations"),
    Delai("traitement_service", "Délai de traitement du service",
          "Transmission au service → retour du service au Service Réclamations (par fiche de traitement : "
          "un dossier renvoyé pour complément compte une fiche par passage)", sur_fiches=True),
    Delai("reponse_client", "Délai de réponse au client",
          "Retour du service reçu par le Service Réclamations → envoi de la réponse au client"),
    Delai("cloture", "Délai de clôture", "Première réception par la banque → clôture (dossiers clôturés)"),
)
DELAIS_PAR_CODE = {d.code: d for d in DELAIS}


def _bornes_delai(code: str):
    if code == "prise_en_charge":
        return Reclamation.date_premiere_reception, Reclamation.date_reception_sr, None
    if code == "traitement_service":
        return A.transmis_le, A.retour_le, None
    if code == "reponse_client":
        return Reclamation.date_retour_service, Reclamation.date_reponse_client, None
    return Reclamation.date_premiere_reception, Reclamation.date_cloture, Reclamation.statut == "CLOTUREE"


def cond_delai(code: str, mode: str, p: Periode, now: datetime):
    """``mode`` : termines (durée ≥ 0, fin dans la période), anomalies (durée < 0), en_cours (départ
    dans la période, fin absente, dossier ouvert)."""
    debut, fin, extra = _bornes_delai(code)
    if mode == "en_cours":
        conds = [p.contient(debut), fin.is_(None), Reclamation.statut.not_in(C.STATUTS_TERMINAUX)]
        if code == "traitement_service":
            conds += [A.statut.in_(EN_COURS_AFFECTATION), A.id == Reclamation.affectation_courante_id]
        return and_(*conds)
    conds = [debut.is_not(None), p.contient(fin), (fin >= debut) if mode == "termines" else (fin < debut)]
    if extra is not None:
        conds.append(extra)
    return and_(*conds)


def _source(code: str, ids):
    """Requête de base : dossiers (ou fiches de traitement) de la population filtrée."""
    q = select().select_from(Reclamation).where(Reclamation.id.in_(ids))
    if DELAIS_PAR_CODE[code].sur_fiches:
        q = q.join(A, A.reclamation_id == Reclamation.id)
    return q


def _heures(fin, debut):
    return func.extract("epoch", fin - debut) / 3600.0


def _instant(now: datetime):
    return literal(now, DateTime(timezone=True))


def _arrondi(v: Any, n: int = 1) -> float | None:
    return round(float(v), n) if v is not None else None


async def _un_delai(db: AsyncSession, d: Delai, ids, p: Periode, now: datetime) -> dict:
    debut, fin, _ = _bornes_delai(d.code)
    unite = A.id if d.sur_fiches else Reclamation.id
    base = _source(d.code, ids)
    n, moy = (await db.execute(base.add_columns(func.count(distinct(unite)), func.avg(_heures(fin, debut)))
                               .where(cond_delai(d.code, "termines", p, now)))).one()
    n_anom = await db.scalar(base.add_columns(func.count(distinct(unite)))
                             .where(cond_delai(d.code, "anomalies", p, now))) or 0
    refs_anom = list((await db.scalars(base.add_columns(Reclamation.reference).distinct()
                                       .where(cond_delai(d.code, "anomalies", p, now))
                                       .order_by(Reclamation.reference).limit(LIMITE_ANOMALIES))).all())
    n_cours, age = (await db.execute(base.add_columns(func.count(distinct(unite)),
                                                      func.avg(_heures(_instant(now), debut)))
                                     .where(cond_delai(d.code, "en_cours", p, now)))).one()
    return {
        "code": d.code, "libelle": d.libelle, "definition": d.definition,
        "unite": "fiche de traitement" if d.sur_fiches else "dossier", "unite_duree": "heures",
        "termines": {"n": n or 0, "moyenne_heures": _arrondi(moy),
                     "moyenne_jours": _arrondi(moy / 24, 2) if moy is not None else None},
        "anomalies": {"n": n_anom, "references": refs_anom},
        "en_cours": {"n": n_cours or 0, "age_moyen_heures": _arrondi(age),
                     "age_moyen_jours": _arrondi(age / 24, 2) if age is not None else None},
    }


async def delais(db: AsyncSession, ids, p: Periode, now: datetime) -> list[dict]:
    return [await _un_delai(db, d, ids, p, now) for d in DELAIS]


async def delai_cloture(db: AsyncSession, s: ReclamationsScope, f: dict, p: Periode) -> dict:
    return await _un_delai(db, DELAIS_PAR_CODE["cloture"], population(s, f), p, maintenant())


# ------------------------------------------------------------------------- réouverture
def _dans(col, ids) -> list:
    return [] if ids is None else [col.in_(ids)]


def _clotures(ids, p: Periode):
    return select(EV.reclamation_id, EV.date_effet).where(
        EV.type_evenement == "CLOTURE", p.contient(EV.date_effet), *_dans(EV.reclamation_id, ids))


def ids_clotures(ids, p: Periode):
    return select(EV.reclamation_id).where(
        EV.type_evenement == "CLOTURE", p.contient(EV.date_effet), *_dans(EV.reclamation_id, ids))


def ids_reouvertes(ids, p: Periode):
    """Dossiers clôturés pendant la période puis réouverts pendant la période (après cette clôture)."""
    cl = _clotures(ids, p).subquery()
    ro = aliased(EV)
    return (select(cl.c.reclamation_id).join(ro, and_(ro.reclamation_id == cl.c.reclamation_id,
                                                       ro.type_evenement == "REOUVERTURE",
                                                       ro.date_effet > cl.c.date_effet))
            .where(p.contient(ro.date_effet)))


async def reouverture(db: AsyncSession, ids, p: Periode) -> dict:
    den = await db.scalar(select(func.count(distinct(EV.reclamation_id))).where(
        EV.type_evenement == "CLOTURE", EV.reclamation_id.in_(ids), p.contient(EV.date_effet))) or 0
    num = await db.scalar(select(func.count(distinct(ids_reouvertes(ids, p).subquery().c.reclamation_id)))) or 0
    evts = (await db.execute(select(EV.reclamation_id, func.count()).where(
        EV.type_evenement == "REOUVERTURE", EV.reclamation_id.in_(ids), p.contient(EV.date_effet))
        .group_by(EV.reclamation_id))).all()
    return {
        "cloturees": den, "reouvertes": num,
        "taux": round(100 * num / den, 1) if den else None,
        "nb_reouvertures": sum(n for _, n in evts),
        "dossiers_reouverts": len(evts),
        "dossiers_plusieurs_reouvertures": sum(1 for _, n in evts if n > 1),
        "formule": "Dossiers clôturés puis réouverts pendant la période ÷ dossiers clôturés pendant la période × 100",
    }


# ----------------------------------------------------------------- performance des services
def cond_service(mode: str, p: Periode, now: datetime):
    if mode == "affectes":
        return p.contient(A.transmis_le)
    if mode == "retournes":
        return p.contient(A.retour_le)
    courant = and_(A.statut.in_(EN_COURS_AFFECTATION), A.id == Reclamation.affectation_courante_id,
                   Reclamation.statut == "EN_TRAITEMENT")
    return courant


async def services(db: AsyncSession, ids, p: Periode, now: datetime, libelle) -> list[dict]:
    base = select(A.unite_destinataire_id).select_from(A).join(Reclamation, Reclamation.id == A.reclamation_id) \
        .where(A.reclamation_id.in_(ids)).group_by(A.unite_destinataire_id)
    out: dict[uuid.UUID, dict] = {}

    def ligne(uid) -> dict:
        return out.setdefault(uid, {"unite_id": str(uid), "libelle": libelle(uid) or "—", "affectes": 0,
                                    "en_cours": 0, "retournes": 0, "delai_moyen_heures": None,
                                    "age_moyen_heures": None})

    for uid, n in (await db.execute(base.add_columns(func.count(distinct(A.reclamation_id)))
                                    .where(cond_service("affectes", p, now)))).all():
        ligne(uid)["affectes"] = n
    for uid, n, moy in (await db.execute(base.add_columns(func.count(distinct(A.reclamation_id)),
                                                          func.avg(_heures(A.retour_le, A.transmis_le)))
                                         .where(cond_service("retournes", p, now)))).all():
        ligne(uid).update(retournes=n, delai_moyen_heures=_arrondi(moy))
    for uid, n, age in (await db.execute(base.add_columns(
            func.count(distinct(A.reclamation_id)),
            func.avg(_heures(_instant(now), A.transmis_le)))
            .where(cond_service("en_cours", p, now)))).all():
        ligne(uid).update(en_cours=n, age_moyen_heures=_arrondi(age))
    for v in out.values():
        for k in ("delai_moyen", "age_moyen"):
            h = v[f"{k}_heures"]
            v[f"{k}_jours"] = round(h / 24, 2) if h is not None else None
    return sorted(out.values(), key=lambda v: (-v["affectes"], -v["en_cours"], v["libelle"]))


# ------------------------------------------------------------------ filtres de liste (KPI)
INDICATEURS = {
    **{f"delai_{d.code}_{m}": (d.code, m) for d in DELAIS for m in ("termines", "anomalies", "en_cours")},
    "clotures": None, "reouvertes": None,
    "service_affectes": None, "service_en_cours": None, "service_retournes": None,
}


def ids_indicateur(code: str, p: Periode, now: datetime, unite_id: uuid.UUID | None, ids=None):
    """Identifiants de dossiers d'un indicateur — même condition que le calcul du KPI.

    ``ids`` = population (périmètre + filtres) ; ``None`` quand la requête englobante (liste) l'applique déjà.
    """
    if code.startswith("delai_"):
        dcode, mode = INDICATEURS[code]
        q = select(Reclamation.id).where(cond_delai(dcode, mode, p, now), *_dans(Reclamation.id, ids))
        if DELAIS_PAR_CODE[dcode].sur_fiches:
            q = q.join(A, A.reclamation_id == Reclamation.id)
        return q.correlate(None)
    if code == "clotures":
        return ids_clotures(ids, p)
    if code == "reouvertes":
        return ids_reouvertes(ids, p)
    q = select(A.reclamation_id).join(Reclamation, Reclamation.id == A.reclamation_id).where(
        cond_service(code.removeprefix("service_"), p, now), *_dans(A.reclamation_id, ids))
    q = q.where(A.unite_destinataire_id == unite_id) if unite_id else q
    return q.correlate(None)


def filtrer(q, f: dict):
    """Filtre ``indicateur`` de la liste des dossiers (même définition que le KPI cliqué)."""
    code = f.get("indicateur")
    if code == "avec_operations":
        return q.where(Reclamation.id.in_(select(ReclamationOperation.reclamation_id)))
    if code not in INDICATEURS:
        raise erreur("Indicateur inconnu", "INDICATEUR_INCONNU")
    p = Periode.de(f.get("kpi_debut"), f.get("kpi_fin"))
    return q.where(Reclamation.id.in_(ids_indicateur(code, p, maintenant(), f.get("kpi_unite_id"))))


# ------------------------------------------------------------------ synthèse d'une période
def sans_dates(f: dict) -> dict:
    return {k: v for k, v in (f or {}).items() if k not in ("date_debut", "date_fin")}


def population(s: ReclamationsScope, f: dict):
    from app.services.reclamations.dossiers import _filtres

    return _filtres(select(Reclamation.id).where(s.filtre_dossiers()), sans_dates(f)).correlate(None)


async def _compte(db: AsyncSession, q) -> int:
    sq = q.subquery()
    return await db.scalar(select(func.count(distinct(list(sq.c)[0])))) or 0


async def synthese(db: AsyncSession, s: ReclamationsScope, f: dict, p: Periode, now: datetime) -> dict:
    """Valeurs d'une période (comparaison A/B) : flux datés par leur propre événement."""
    ids = population(s, f)
    recues = select(Reclamation.id).where(Reclamation.id.in_(ids), p.contient(Reclamation.date_premiere_reception)) \
        .correlate(None)
    nb_recues = await _compte(db, recues)
    n_ops, montant, avec_ops = (await db.execute(select(
        func.count(ReclamationOperation.id), func.sum(ReclamationOperation.montant),
        func.count(distinct(ReclamationOperation.reclamation_id)),
    ).where(ReclamationOperation.reclamation_id.in_(recues)))).one()
    d = {x["code"]: x for x in await delais(db, ids, p, now)}
    ro = await reouverture(db, ids, p)
    return {
        "recues": nb_recues,
        "clotures": await _compte(db, ids_clotures(ids, p)),
        "nb_operations": n_ops or 0,
        "dossiers_avec_operations": avec_ops or 0,
        "montant": str(montant or 0),
        "taux_reouverture": ro["taux"], "reouvertes": ro["reouvertes"],
        **{f"delai_{k}": v["termines"]["moyenne_heures"] for k, v in d.items()},
        **{f"delai_{k}_n": v["termines"]["n"] for k, v in d.items()},
    }


# (code, libellé, unité, sens favorable : +1 hausse favorable, -1 baisse favorable, 0 sans sens défini,
#  indicateur de liste ou None si la liste se filtre par la date de réception)
METRIQUES = (
    ("recues", "Réclamations reçues", "dossiers", 0, None),
    ("clotures", "Réclamations clôturées", "dossiers", 1, "clotures"),
    ("nb_operations", "Opérations contestées (dossiers reçus)", "opérations", 0, None),
    ("montant", f"Montant contesté ({C.DEVISE})", C.DEVISE, 0, None),
    ("taux_reouverture", "Taux de réouverture", "%", -1, "reouvertes"),
    *((f"delai_{d.code}", d.libelle, "heures", -1, f"delai_{d.code}_termines") for d in DELAIS),
)


def _nombre(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def comparer(a: dict, b: dict) -> list[dict]:
    """Période A = référence, période B = période comparée. Variation N/A si la référence vaut 0."""
    out = []
    for code, libelle, unite, sens, indicateur in METRIQUES:
        va, vb = _nombre(a.get(code)), _nombre(b.get(code))
        ecart = round(vb - va, 2) if va is not None and vb is not None else None
        variation = round(100 * ecart / va, 1) if ecart is not None and va else None
        favorable = None
        if sens and ecart:
            favorable = (ecart > 0) == (sens > 0)
        out.append({"code": code, "libelle": libelle, "unite": unite, "a": a.get(code), "b": b.get(code),
                    "ecart": ecart, "variation": variation, "favorable": favorable,
                    "sens": {1: "hausse_favorable", -1: "baisse_favorable"}.get(sens), "indicateur": indicateur})
    return out


async def comparaison(db: AsyncSession, s: ReclamationsScope, f: dict, pa: Periode, pb: Periode) -> dict:
    for p, nom in ((pa, "A"), (pb, "B")):
        if not (p.jour_debut and p.jour_fin):
            raise erreur(f"Indiquez le début et la fin de la période {nom}", "PERIODE_INCOMPLETE")
    now = maintenant()
    a, b = await synthese(db, s, f, pa, now), await synthese(db, s, f, pb, now)
    avertissements = []
    if pa.jours != pb.jours:
        avertissements.append(f"Périodes de durées différentes ({pa.jours} j contre {pb.jours} j) : "
                              "comparez de préférence les taux et délais moyens plutôt que les volumes.")
    if pa.jour_debut <= pb.jour_fin and pb.jour_debut <= pa.jour_fin:
        avertissements.append("Les deux périodes se chevauchent : certains dossiers comptent dans les deux.")
    return {
        "a": {"debut": pa.jour_debut.isoformat(), "fin": pa.jour_fin.isoformat(), "jours": pa.jours, "valeurs": a},
        "b": {"debut": pb.jour_debut.isoformat(), "fin": pb.jour_fin.isoformat(), "jours": pb.jours, "valeurs": b},
        "lignes": comparer(a, b), "avertissements": avertissements,
    }


async def pilotage(db: AsyncSession, s: ReclamationsScope, f: dict, p: Periode, libelle_unite) -> dict:
    now = maintenant()
    ids = population(s, f)
    return {
        "periode": {"debut": p.jour_debut.isoformat() if p.jour_debut else None,
                    "fin": p.jour_fin.isoformat() if p.jour_fin else None},
        "delais": await delais(db, ids, p, now),
        "reouverture": await reouverture(db, ids, p),
        "services": await services(db, ids, p, now, libelle_unite),
    }
