"""Reporting EER (KPI) calculé depuis PostgreSQL, restreint au périmètre agence de l'acteur.

Deux familles, jamais mélangées :

- **Conformité** (référence Excel + décision BEA-DIGITAL, ``conformite_historique``) :
  population = dossiers non supprimés et non ABANDONNE. Un dossier abandonné reste en base
  pour l'historique et l'audit mais n'a pas été traité jusqu'à une décision : il n'entre
  ni dans le total ni dans le dénominateur du taux. Les non classés restent comptés dans
  le total mais hors du taux (S / (S + T)).
- **Flux** (gestion des dossiers) : reçus, en cours, à compléter, abandonnés, taux d'abandon.

Nature des KPI :
- ``HISTORIQUE_EXCEL`` : global, par agence, par profil, état du compte (synthèse Excel) ;
- ``EXTENSION_BEA_DIGITAL`` : période (jour / semaine / mois / année) et autres dimensions
  (risque, PPE, FATCA, résidence, analyste, profil, sous-profil) — absents de la synthèse Excel.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, case, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.eer_referentiel import ETATS_COMPTE, TYPES_CLIENT, code_profil
from app.models import Agence, EerDossier, EerPartie, EerReferentiel, User
from app.services.eer.conformite_historique import (
    LIBELLE_EXCEL_PROFIL,
    Compteurs,
    profil_technique,
    sql_classement_bea,
    sql_classement_excel,
    sql_code_conforme,
    sql_code_non_conforme,
)
from app.services.eer.constantes import ResultatAxe
from app.services.eer.workflow import Statut
from app.services.eer_access import EerScope
from app.services.eer_lecture_service import EN_COURS, EerLectureService, FiltresDossiers, restreindre

HISTORIQUE_EXCEL = "HISTORIQUE_EXCEL"
EXTENSION_BEA_DIGITAL = "EXTENSION_BEA_DIGITAL"

GRANULARITES = {"jour": "day", "semaine": "week", "mois": "month", "annee": "year"}
DIMENSIONS = ("risque", "ppe", "fatca", "residence", "analyste", "profil", "sous_profil")
_COLONNE_DIMENSION = {
    "risque": EerDossier.risque_lbcft,
    "ppe": EerDossier.ppe_dossier,
    "fatca": EerDossier.fatca_dossier,
    "residence": EerPartie.pays_residence,
    "analyste": EerDossier.analyste_id,
    # Colonne Excel « SOUS PROFIL » = profil BEA-DIGITAL (Salarié, SARL…).
    "profil": EerDossier.profil_code,
    "sous_profil": EerDossier.sous_profil_code,
}


def _agregats() -> tuple:
    p, s, d = EerDossier.conformite_physique, EerDossier.conformite_systeme, EerDossier.decision_globale

    def somme(expr):
        return func.coalesce(func.sum(expr), 0)

    return (
        func.count().label("total"),
        somme(sql_code_conforme(p, s)).label("excel_c"),
        somme(sql_code_non_conforme(p, s)).label("excel_nc"),
        somme(case((d == ResultatAxe.CONFORME, 1), else_=0)).label("bea_c"),
        somme(case((d == ResultatAxe.NON_CONFORME, 1), else_=0)).label("bea_nc"),
        somme(case((sql_classement_excel(p, s) != sql_classement_bea(d), 1), else_=0)).label("divergences"),
    )


def _bloc(ligne: Any | None) -> dict[str, Any]:
    if ligne is None:
        return {"total": 0, "excel": Compteurs(0, 0, 0).to_dict(), "bea": Compteurs(0, 0, 0).to_dict(),
                "divergences": 0}
    total = int(ligne.total)
    return {
        "total": total,
        "excel": Compteurs(total, int(ligne.excel_c), int(ligne.excel_nc)).to_dict(),
        "bea": Compteurs(total, int(ligne.bea_c), int(ligne.bea_nc)).to_dict(),
        "divergences": int(ligne.divergences),
    }


def _pourcentage(n: int, total: int) -> Decimal | None:
    if total == 0:
        return None
    return (Decimal(n) * 100 / Decimal(total)).quantize(Decimal("0.01"))


class EerReportingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._lecture = EerLectureService(db)

    def _base(self, scope: EerScope, f: FiltresDossiers, colonnes: Sequence, *, conformite: bool = True) -> Select:
        stmt = (select(*colonnes).select_from(EerDossier)
                .join(EerPartie, EerPartie.id == EerDossier.client_partie_id))
        stmt = self._lecture._filtrer(restreindre(stmt, scope), f)
        if conformite:
            stmt = stmt.where(EerDossier.statut != Statut.ABANDONNE)
        return stmt

    async def _grouper(self, scope: EerScope, f: FiltresDossiers, cle) -> dict[Any, Any]:
        stmt = self._base(scope, f, (cle.label("cle"), *_agregats())).group_by(cle)
        return {r.cle: r for r in (await self.db.execute(stmt)).all()}

    # --- Historique Excel ------------------------------------------------------------------

    async def global_(self, scope: EerScope, f: FiltresDossiers) -> dict[str, Any]:
        ligne = (await self.db.execute(self._base(scope, f, _agregats()))).one()
        return {"nature": HISTORIQUE_EXCEL, **_bloc(ligne), "flux": await self.flux(scope, f)}

    async def flux(self, scope: EerScope, f: FiltresDossiers) -> dict[str, Any]:
        """[PROPOSITION TECHNIQUE] reçu = soumis au contrôle au moins une fois (``soumis_le``) ;
        taux d'abandon = abandonnés après réception / reçus (un brouillon abandonné n'a pas été reçu)."""
        stmt = self._base(scope, f, (EerDossier.statut, func.count(), func.count(EerDossier.soumis_le)),
                          conformite=False).group_by(EerDossier.statut)
        par_statut = {s: (n, recus) for s, n, recus in (await self.db.execute(stmt)).all()}

        def n(*statuts: str) -> int:
            return sum(par_statut.get(s, (0, 0))[0] for s in statuts)

        recus = sum(r for _, r in par_statut.values())
        abandonnes_recus = par_statut.get(Statut.ABANDONNE, (0, 0))[1]
        return {
            "recus": recus,
            "brouillons": n(Statut.BROUILLON),
            "en_cours": n(*(s for s in EN_COURS if s != Statut.BROUILLON)),
            "a_completer": n(Statut.A_COMPLETER),
            "abandonnes": n(Statut.ABANDONNE),
            "abandonnes_apres_reception": abandonnes_recus,
            "taux_abandon": _pourcentage(abandonnes_recus, recus),
        }

    async def par_agence(self, scope: EerScope, f: FiltresDossiers) -> dict[str, Any]:
        """SUMIFS(S) / SUMIFS(T) par agence ; toutes les agences du périmètre, même à zéro."""
        groupes = await self._grouper(scope, f, EerDossier.agence_id)
        stmt = select(Agence).where(Agence.deleted_at.is_(None))
        if scope.agences is not None:
            stmt = stmt.where(Agence.id.in_(scope.agences) if scope.agences else false())
        if f.agence_id:
            stmt = stmt.where(Agence.id == f.agence_id)
        agences = {a.id: a for a in (await self.db.scalars(stmt)).all()
                   if a.is_active or a.id in groupes}
        lignes = [{"code": a.code, "libelle": a.libelle, "agence_id": a.id, **_bloc(groupes.get(a.id))}
                  for a in sorted(agences.values(), key=lambda a: a.code)]
        return {"nature": HISTORIQUE_EXCEL, "lignes": lignes, "total": self._total(lignes)}

    async def par_profil(self, scope: EerScope, f: FiltresDossiers) -> dict[str, Any]:
        """SUMIFS(S) / SUMIFS(T) par colonne Excel « PROFIL » (= type client), libellés historiques."""
        groupes = await self._grouper(scope, f, EerDossier.type_client_code)
        codes = list(TYPES_CLIENT) + sorted(c for c in groupes if c not in TYPES_CLIENT)
        lignes = [{"code": c, "libelle": LIBELLE_EXCEL_PROFIL.get(c, c), "profil_technique": profil_technique(c),
                   **_bloc(groupes.get(c))} for c in codes]
        return {"nature": HISTORIQUE_EXCEL, "lignes": lignes, "total": self._total(lignes)}

    async def etats_compte(self, scope: EerScope, f: FiltresDossiers) -> dict[str, Any]:
        """COUNTIFS(état du compte) — indépendant de S/T ; % sur le total des 4 états listés."""
        stmt = self._base(scope, f, (EerDossier.etat_compte, func.count())).group_by(EerDossier.etat_compte)
        comptes = dict((await self.db.execute(stmt)).all())
        etats = [(code_profil(libelle), libelle) for libelle in ETATS_COMPTE]
        total = sum(comptes.get(code, 0) for code, _ in etats)
        return {
            "nature": HISTORIQUE_EXCEL,
            "lignes": [{"code": code, "libelle": libelle, "nombre": comptes.get(code, 0),
                        "pourcentage": _pourcentage(comptes.get(code, 0), total)} for code, libelle in etats],
            "total": total,
            "non_renseignes": sum(v for k, v in comptes.items() if k not in {c for c, _ in etats}),
        }

    @staticmethod
    def _total(lignes: list[dict[str, Any]]) -> dict[str, Any]:
        def somme(cle: str, champ: str) -> int:
            return sum(l[cle][champ] for l in lignes)

        total = sum(l["total"] for l in lignes)
        bloc = {"total": total, "divergences": sum(l["divergences"] for l in lignes)}
        for cle in ("excel", "bea"):
            bloc[cle] = Compteurs(total, somme(cle, "conformes"), somme(cle, "non_conformes")).to_dict()
        return bloc

    # --- Extensions BEA-DIGITAL ------------------------------------------------------------

    async def serie(self, scope: EerScope, f: FiltresDossiers, granularite: str) -> dict[str, Any]:
        periode = func.date_trunc(GRANULARITES[granularite], EerDossier.date_eer)
        groupes = await self._grouper(scope, f, periode)
        lignes = [{"periode": p.date() if hasattr(p, "date") else p, **_bloc(r)}
                  for p, r in sorted(groupes.items(), key=lambda kv: kv[0])]
        return {"nature": EXTENSION_BEA_DIGITAL, "granularite": granularite, "lignes": lignes}

    async def par_dimension(self, scope: EerScope, f: FiltresDossiers, dimension: str) -> dict[str, Any]:
        groupes = await self._grouper(scope, f, _COLONNE_DIMENSION[dimension])
        libelles: dict[Any, str] = {}
        if dimension == "analyste":
            ids = [k for k in groupes if k is not None]
            if ids:
                libelles = dict((await self.db.execute(select(User.id, User.full_name)
                                                       .where(User.id.in_(ids)))).all())
        elif dimension == "profil":
            libelles = dict((await self.db.execute(select(EerReferentiel.code, EerReferentiel.libelle)
                                                   .where(EerReferentiel.domaine == "PROFIL"))).all())
        lignes = []
        for cle, r in groupes.items():
            code = None if cle is None else ("OUI" if cle is True else "NON" if cle is False else str(cle))
            lignes.append({"code": code, "libelle": libelles.get(cle, code) if cle is not None else "Non renseigné",
                           **_bloc(r)})
        lignes.sort(key=lambda l: (-l["total"], l["code"] or ""))
        return {"nature": EXTENSION_BEA_DIGITAL, "dimension": dimension, "lignes": lignes,
                "total": self._total(lignes)}
