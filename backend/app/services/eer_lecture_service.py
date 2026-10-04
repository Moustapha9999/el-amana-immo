"""Lectures EER (liste, tableau de bord) — toujours restreintes au périmètre agence de l'acteur."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Agence, EerDossier, EerPartie, User
from app.services.eer.workflow import Statut
from app.services.eer_access import EerScope

TRIS = {
    "created_at": EerDossier.created_at,
    "updated_at": EerDossier.updated_at,
    "reference": EerDossier.reference,
    "statut": EerDossier.statut,
    "date_eer": EerDossier.date_eer,
    "soumis_le": EerDossier.soumis_le,
    "valide_le": EerDossier.valide_le,
}

EN_COURS = (Statut.BROUILLON, Statut.SOUMIS, Statut.A_AFFECTER, Statut.AFFECTE, Statut.EN_CONTROLE,
            Statut.CONFORME, Statut.NON_CONFORME, Statut.A_COMPLETER, Statut.RESOUMIS, Statut.AVIS_CONFORMITE)


@dataclass
class FiltresDossiers:
    statut: list[str] | None = None
    agence_id: uuid.UUID | None = None
    type_client: str | None = None
    profil: str | None = None
    risque: str | None = None
    decision: str | None = None
    avis_requis: bool | None = None
    analyste_id: uuid.UUID | None = None
    q: str | None = None
    date_debut: date | None = None
    date_fin: date | None = None


def restreindre(stmt: Select, scope: EerScope) -> Select:
    stmt = stmt.where(EerDossier.deleted_at.is_(None))
    agences = scope.agences
    if agences is None:
        return stmt
    if not agences:
        return stmt.where(false())
    return stmt.where(EerDossier.agence_id.in_(agences))


class EerLectureService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _filtrer(self, stmt: Select, f: FiltresDossiers) -> Select:
        if f.statut:
            stmt = stmt.where(EerDossier.statut.in_(f.statut))
        if f.agence_id:
            stmt = stmt.where(EerDossier.agence_id == f.agence_id)
        if f.type_client:
            stmt = stmt.where(EerDossier.type_client_code == f.type_client)
        if f.profil:
            stmt = stmt.where(EerDossier.profil_code == f.profil)
        if f.risque:
            stmt = stmt.where(EerDossier.risque_lbcft == f.risque)
        if f.decision:
            stmt = stmt.where(EerDossier.decision_globale == f.decision)
        if f.avis_requis is not None:
            stmt = stmt.where(EerDossier.avis_requis.is_(f.avis_requis))
        if f.analyste_id:
            stmt = stmt.where(EerDossier.analyste_id == f.analyste_id)
        if f.date_debut:
            stmt = stmt.where(EerDossier.date_eer >= f.date_debut)
        if f.date_fin:
            stmt = stmt.where(EerDossier.date_eer <= f.date_fin)
        if f.q and f.q.strip():
            motif = f"%{f.q.strip()}%"
            stmt = stmt.where(or_(EerDossier.reference.ilike(motif), EerDossier.racine_client.ilike(motif),
                                  EerPartie.nom.ilike(motif)))
        return stmt

    async def lister(self, scope: EerScope, f: FiltresDossiers, *, page: int, size: int, tri: str,
                     ordre: str) -> tuple[list[dict], int]:
        analyste = aliased(User)
        base = (select(EerDossier.id).join(EerPartie, EerPartie.id == EerDossier.client_partie_id))
        base = self._filtrer(restreindre(base, scope), f)
        total = await self.db.scalar(select(func.count()).select_from(base.subquery())) or 0

        colonne = TRIS.get(tri, EerDossier.created_at)
        ordre_sql = colonne.asc() if ordre == "asc" else colonne.desc()
        stmt = (
            select(EerDossier, EerPartie.nom, Agence.code, Agence.libelle, analyste.full_name)
            .join(EerPartie, EerPartie.id == EerDossier.client_partie_id)
            .join(Agence, Agence.id == EerDossier.agence_id)
            .outerjoin(analyste, analyste.id == EerDossier.analyste_id)
        )
        stmt = self._filtrer(restreindre(stmt, scope), f).order_by(ordre_sql, EerDossier.id)
        stmt = stmt.offset((page - 1) * size).limit(size)
        lignes = []
        for d, nom, agence_code, agence_libelle, analyste_nom in (await self.db.execute(stmt)).all():
            lignes.append({
                "id": d.id, "reference": d.reference, "statut": d.statut, "etape": d.etape,
                "operation_type": d.operation_type, "agence_id": d.agence_id, "agence_code": agence_code,
                "agence_libelle": agence_libelle, "type_client": d.type_client_code, "profil": d.profil_code,
                "client_nom": nom, "racine_client": d.racine_client, "risque": d.risque_lbcft,
                "decision": d.decision_globale, "avis_requis": d.avis_requis, "analyste_id": d.analyste_id,
                "analyste_nom": analyste_nom, "version_courante": d.version_courante, "revision": d.revision,
                "date_eer": d.date_eer, "soumis_le": d.soumis_le, "valide_le": d.valide_le,
                "created_at": d.created_at, "updated_at": d.updated_at,
            })
        return lignes, total

    async def tableau_de_bord(self, scope: EerScope, agence_id: uuid.UUID | None = None) -> dict:
        def perimetre(stmt: Select) -> Select:
            stmt = restreindre(stmt, scope)
            return stmt.where(EerDossier.agence_id == agence_id) if agence_id else stmt

        par_statut = dict((await self.db.execute(
            perimetre(select(EerDossier.statut, func.count()).group_by(EerDossier.statut)))).all())

        def n(*statuts: str) -> int:
            return sum(par_statut.get(s, 0) for s in statuts)

        valides = await self.db.scalar(perimetre(
            select(func.count()).select_from(EerDossier).where(EerDossier.valide_le.is_not(None)))) or 0
        delai = await self.db.scalar(perimetre(
            select(func.avg(func.extract("epoch", EerDossier.valide_le - EerDossier.soumis_le)))
            .select_from(EerDossier)
            .where(and_(EerDossier.valide_le.is_not(None), EerDossier.soumis_le.is_not(None)))))

        async def repartition(*colonnes) -> list[dict]:
            stmt = perimetre(select(*colonnes, func.count()).select_from(EerDossier).group_by(*colonnes))
            if colonnes[0] is Agence.code:
                stmt = stmt.join(Agence, Agence.id == EerDossier.agence_id)
            return [{"code": r[0], "libelle": r[1] if len(colonnes) > 1 else r[0], "total": r[-1]}
                    for r in (await self.db.execute(stmt.order_by(func.count().desc()))).all()]

        return {
            "total": sum(par_statut.values()),
            "en_cours": n(*EN_COURS),
            "brouillons": n(Statut.BROUILLON),
            "a_affecter": n(Statut.A_AFFECTER),
            "affectes": n(Statut.AFFECTE),
            "en_controle": n(Statut.EN_CONTROLE, Statut.RESOUMIS),
            "non_conformes": n(Statut.NON_CONFORME),
            "a_completer": n(Statut.A_COMPLETER),
            "conformes": n(Statut.CONFORME),
            "avis_en_attente": n(Statut.AVIS_CONFORMITE),
            "valides": valides,
            "abandonnes": n(Statut.ABANDONNE),
            "delai_moyen_jours": round(float(delai) / 86400, 1) if delai is not None else None,
            "par_statut": par_statut,
            "par_agence": await repartition(Agence.code, Agence.libelle),
            "par_profil": await repartition(EerDossier.profil_code),
            "par_type_client": await repartition(EerDossier.type_client_code),
            "par_risque": await repartition(EerDossier.risque_lbcft),
        }
