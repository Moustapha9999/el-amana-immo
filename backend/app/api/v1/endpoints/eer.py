"""API EER — Gestion des Entrées en Relation (Conformité & Sécurité financière → KYC).

Login 2 module ``eer`` (dépendance posée au montage du router), permissions ``eer.*``
vérifiées par route ET par le service, périmètre agence imposé par le service.
Toute mutation porte la ``revision`` connue du client : 409 si le dossier a changé.
Aucune route n'expose de PATCH / DELETE sur versions, historique, visas ou décisions.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import auth_http_error, get_current_user
from app.db.session import get_db
from app.models import (
    Agence,
    AuditLog,
    EerAnomalie,
    EerChecklistItem,
    EerComplement,
    EerControle,
    EerDecision,
    EerDossier,
    EerHistorique,
    EerReferentiel,
    EerVersion,
    EerVisa,
    GedDocument,
    User,
)
from app.schemas.eer import (
    EerActionIn,
    EerAgenceOut,
    EerAnalysteOut,
    EerAnomalieCreate,
    EerAnomalieOut,
    EerAnomaliePatch,
    EerAssignIn,
    EerAuditOut,
    EerAvisIn,
    EerBeneficiaireOut,
    EerBeneficiairesOut,
    EerChecklistItemOut,
    EerChecklistOut,
    EerComplementFourniIn,
    EerComplementIn,
    EerComplementOut,
    EerAnomalieBloquanteOut,
    EerConfirmIn,
    EerConformiteOut,
    EerConstatOut,
    EerControleManuelIn,
    EerControleOut,
    EerControlesAutoOut,
    EerControlesOut,
    EerDecisionIn,
    EerDecisionOut,
    EerDetentionIn,
    EerDocumentOut,
    EerDossierCreate,
    EerDossierLigne,
    EerDossierOut,
    EerDossierPage,
    EerDossierPatch,
    EerFicheChampOut,
    EerHistoriqueOut,
    EerKpiEtatsCompteOut,
    EerKpiGlobalOut,
    EerKpiRepartitionOut,
    EerKpiSerieOut,
    EerMutationOut,
    EerPartieAjout,
    EerPartieOut,
    EerPerimetreOut,
    EerPointageIn,
    EerReferenceExcelOut,
    EerReferentielOut,
    EerTableauDeBordOut,
    EerVersionLigne,
    EerVersionOut,
    EerVisaOut,
)
from app.services import eer_controles_auto
from app.services.eer.checklist_engine import elements_non_pointes
from app.services.eer.conformite_historique import Classement, classer_bea, classer_excel, expliquer_ecart
from app.services.eer.constantes import ANOMALIES_OUVERTES, GraviteAnomalie
from app.services.eer.workflow import TRANSITIONS, Statut
from app.services.eer_dossier_service import (
    GED_ENTITE,
    MODULE_CODE,
    Acteur,
    CibleComplement,
    EerDossierService,
    EerIntrouvable,
)
from app.services.eer_access import charger_permissions_eer, resolve_eer_access_scope
from app.services.eer_lecture_service import TRIS, EerLectureService, FiltresDossiers
from app.services.eer_reporting_service import DIMENSIONS, EerReportingService
from app.services.permission_service import user_has_permission_codes

router = APIRouter(prefix="/eer", tags=["EER — Entrées en relation"])

_SAISIE = ("eer.update", "eer.control", "eer.complement.receive")


def _acteur(*codes: str) -> Callable[..., Awaitable[Acteur]]:
    async def dependance(
        request: Request,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Acteur:
        permissions = frozenset(await charger_permissions_eer(db, user))
        if not user_has_permission_codes(set(permissions), *codes):
            raise auth_http_error(status.HTTP_403_FORBIDDEN, "PERMISSION_DENIED", "Permission refusée",
                                  required=list(codes))
        return Acteur(user, permissions, session_id=getattr(request.state, "bea_session_id", None),
                      ip_address=request.client.host if request.client else None)

    return dependance


async def _dossier_visible(db: AsyncSession, acteur: Acteur, dossier_id: uuid.UUID) -> EerDossier:
    return await EerDossierService(db).charger(dossier_id, acteur=acteur)


def _transitions(d: EerDossier, acteur: Acteur) -> list[str]:
    return [cible for (origine, cible), permission in TRANSITIONS.items()
            if origine == d.statut and permission and acteur.perimetre.peut(permission)]


def _dossier_out(d: EerDossier, acteur: Acteur) -> EerDossierOut:
    excel = classer_excel(d.conformite_physique, d.conformite_systeme)
    bea = classer_bea(d.decision_globale)
    return EerDossierOut(
        etat_compte=d.etat_compte, conformite_excel=excel.classement, code_conforme=excel.code_conforme,
        code_non_conforme=excel.code_non_conforme, conformite_bea=bea, divergence=excel.classement != bea,
        id=d.id, reference=d.reference, statut=d.statut, etape=d.etape, operation_type=d.operation_type,
        agence_id=d.agence_id, type_client=d.type_client_code, profil=d.profil_code,
        sous_profil=d.sous_profil_code, risque=d.risque_lbcft, ppe=d.ppe_dossier, fatca=d.fatca_dossier,
        avis_requis=d.avis_requis, conformite_physique=d.conformite_physique,
        conformite_systeme=d.conformite_systeme, conformite_coherence=d.conformite_coherence,
        decision=d.decision_globale, version_courante=d.version_courante, revision=d.revision,
        nb_relances=d.nb_relances, motif_abandon=d.motif_abandon, parametres_snapshot=d.parametres_snapshot,
        created_by_id=d.created_by_id, analyste_id=d.analyste_id, controleur_id=d.controleur_id,
        date_eer=d.date_eer, soumis_le=d.soumis_le, valide_le=d.valide_le, archived_at=d.archived_at,
        created_at=d.created_at, updated_at=d.updated_at,
        parties=[EerPartieOut(
            dossier_partie_id=dp.id, partie_id=dp.partie_id, role=dp.role, nature=dp.partie.nature,
            nom=dp.partie.nom, ordre=dp.ordre, ppe=dp.ppe, fatca_indice=dp.fatca_indice,
            risque_lbcft=dp.risque_lbcft, be_source=dp.be_source, be_pourcentage_calcule=dp.be_pourcentage_calcule,
        ) for dp in d.parties],
        transitions_possibles=_transitions(d, acteur),
    )


async def _muter(db: AsyncSession, acteur: Acteur, dossier_id: uuid.UUID, revision: int,
                 operation: Callable[[EerDossierService], Awaitable[Any]], message: str) -> EerMutationOut:
    """Verrou + révision → opération → commit ; le succès n'est renvoyé qu'après le commit."""
    svc = EerDossierService(db)
    await svc.verrouiller(acteur, dossier_id, revision)
    await operation(svc)
    d = await svc.charger(dossier_id)
    out = EerMutationOut(id=d.id, statut=d.statut, etape=d.etape, revision=d.revision,
                         version_courante=d.version_courante, message=message)
    await db.commit()
    return out


async def _item_du_dossier(db: AsyncSession, dossier_id: uuid.UUID, item_id: uuid.UUID) -> None:
    item = await db.get(EerChecklistItem, item_id)
    if item is None or item.dossier_id != dossier_id:
        raise EerIntrouvable("Élément de checklist introuvable")


async def _anomalie_du_dossier(db: AsyncSession, dossier_id: uuid.UUID, anomalie_id: uuid.UUID) -> None:
    a = await db.get(EerAnomalie, anomalie_id)
    if a is None or a.dossier_id != dossier_id:
        raise EerIntrouvable("Anomalie introuvable")


def _cibles(c) -> CibleComplement:
    if c is None:
        return CibleComplement()
    return CibleComplement(item_ids=list(c.item_ids), anomalie_ids=list(c.anomalie_ids), champs=list(c.champs))


# --- Périmètre / tableau de bord / liste ----------------------------------------------------

@router.get("/perimetre", response_model=EerPerimetreOut)
async def perimetre(acteur: Acteur = Depends(_acteur("eer.view"))):
    return EerPerimetreOut(**acteur.perimetre.to_dict())


@router.get("/dashboard", response_model=EerTableauDeBordOut)
async def tableau_de_bord(
    agence_id: uuid.UUID | None = None,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    return EerTableauDeBordOut(**await EerLectureService(db).tableau_de_bord(acteur.perimetre, agence_id))


@router.get("/agences", response_model=list[EerAgenceOut])
async def agences(
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    """Agences du périmètre de l'utilisateur (création / filtres) — jamais au-delà."""
    stmt = select(Agence).where(Agence.deleted_at.is_(None), Agence.is_active.is_(True)).order_by(Agence.code)
    portee = acteur.perimetre.agences
    if portee is not None:
        if not portee:
            return []
        stmt = stmt.where(Agence.id.in_(portee))
    return [EerAgenceOut(id=a.id, code=a.code, libelle=a.libelle) for a in (await db.scalars(stmt)).all()]


@router.get("/referentiels", response_model=list[EerReferentielOut])
async def referentiels(
    domaine: str = Query(min_length=1, max_length=40),
    _: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    lignes = (await db.scalars(select(EerReferentiel).where(
        EerReferentiel.domaine == domaine, EerReferentiel.actif.is_(True)).order_by(EerReferentiel.ordre))).all()
    parents = {r.id: r.code for r in (await db.scalars(select(EerReferentiel).where(
        EerReferentiel.id.in_({r.parent_id for r in lignes if r.parent_id})))).all()} if lignes else {}
    return [EerReferentielOut(domaine=r.domaine, code=r.code, libelle=r.libelle, parent_code=parents.get(r.parent_id),
                              ordre=r.ordre, meta=r.meta or {}) for r in lignes]


@router.get("/dossiers/{dossier_id}/analystes", response_model=list[EerAnalysteOut])
async def analystes_eligibles(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.assign")),
    db: AsyncSession = Depends(get_db),
):
    """Agents affectables : actifs, détenteurs de ``eer.control`` (accès module EER ou rôle) sur l'agence
    du dossier, hors créateur si la séparation des rôles est active (mêmes règles que /assign)."""
    svc = EerDossierService(db)
    d = await svc.charger(dossier_id, acteur=acteur)
    exclu = d.created_by_id if await svc.separation_active(d) else None
    candidats = (await db.scalars(
        select(User).options(selectinload(User.roles))
        .where(User.is_active.is_(True), User.deleted_at.is_(None))
        .order_by(User.full_name))).all()
    eligibles = []
    for u in candidats:
        if u.id == exclu:
            continue
        portee = resolve_eer_access_scope(u, await charger_permissions_eer(db, u))
        if portee.peut("eer.control") and portee.couvre(d.agence_id):
            eligibles.append(EerAnalysteOut(id=u.id, nom=u.full_name))
    return eligibles


@router.get("/dossiers", response_model=EerDossierPage)
async def lister_dossiers(
    statut: list[str] | None = Query(None),
    agence_id: uuid.UUID | None = None,
    type_client: str | None = None,
    profil: str | None = None,
    risque: str | None = None,
    decision: str | None = None,
    avis_requis: bool | None = None,
    analyste_id: uuid.UUID | None = None,
    mes_dossiers: bool = False,
    q: str | None = Query(None, max_length=100),
    date_debut: date | None = None,
    date_fin: date | None = None,
    sous_profil: str | None = None,
    ppe: bool | None = None,
    fatca: bool | None = None,
    etat_compte: str | None = None,
    residence: str | None = Query(None, max_length=80),
    conformite_excel: Classement | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    tri: str = Query("created_at"),
    ordre: Literal["asc", "desc"] = "desc",
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    filtres = FiltresDossiers(
        statut=statut, agence_id=agence_id, type_client=type_client, profil=profil, risque=risque,
        decision=decision, avis_requis=avis_requis, analyste_id=acteur.user.id if mes_dossiers else analyste_id,
        q=q, date_debut=date_debut, date_fin=date_fin, sous_profil=sous_profil, ppe=ppe, fatca=fatca,
        etat_compte=etat_compte, residence=residence, conformite_excel=conformite_excel)
    items, total = await EerLectureService(db).lister(
        acteur.perimetre, filtres, page=page, size=size, tri=tri if tri in TRIS else "created_at", ordre=ordre)
    return EerDossierPage(items=[EerDossierLigne(**i) for i in items], total=total, page=page, size=size)


# --- KPI (reporting) ----------------------------------------------------------------------------

def _filtres_kpi(
    agence_id: uuid.UUID | None = None,
    type_client: str | None = None,
    profil: str | None = None,
    sous_profil: str | None = None,
    risque: str | None = None,
    ppe: bool | None = None,
    fatca: bool | None = None,
    etat_compte: str | None = None,
    residence: str | None = Query(None, max_length=80),
    analyste_id: uuid.UUID | None = None,
    statut: list[str] | None = Query(None),
    date_debut: date | None = None,
    date_fin: date | None = None,
) -> FiltresDossiers:
    return FiltresDossiers(
        statut=statut, agence_id=agence_id, type_client=type_client, profil=profil, sous_profil=sous_profil,
        risque=risque, ppe=ppe, fatca=fatca, etat_compte=etat_compte, residence=residence,
        analyste_id=analyste_id, date_debut=date_debut, date_fin=date_fin)


@router.get("/kpis", response_model=EerKpiGlobalOut)
async def kpis(
    filtres: FiltresDossiers = Depends(_filtres_kpi),
    acteur: Acteur = Depends(_acteur("eer.report.view")),
    db: AsyncSession = Depends(get_db),
):
    """Conformité (référence Excel + décision BEA-DIGITAL, abandonnés exclus) et flux des dossiers."""
    return await EerReportingService(db).global_(acteur.perimetre, filtres)


@router.get("/kpis/agencies", response_model=EerKpiRepartitionOut)
async def kpis_agences(
    filtres: FiltresDossiers = Depends(_filtres_kpi),
    acteur: Acteur = Depends(_acteur("eer.report.view")),
    db: AsyncSession = Depends(get_db),
):
    return await EerReportingService(db).par_agence(acteur.perimetre, filtres)


@router.get("/kpis/profiles", response_model=EerKpiRepartitionOut)
async def kpis_profils(
    filtres: FiltresDossiers = Depends(_filtres_kpi),
    acteur: Acteur = Depends(_acteur("eer.report.view")),
    db: AsyncSession = Depends(get_db),
):
    return await EerReportingService(db).par_profil(acteur.perimetre, filtres)


@router.get("/kpis/account-statuses", response_model=EerKpiEtatsCompteOut)
async def kpis_etats_compte(
    filtres: FiltresDossiers = Depends(_filtres_kpi),
    acteur: Acteur = Depends(_acteur("eer.report.view")),
    db: AsyncSession = Depends(get_db),
):
    return await EerReportingService(db).etats_compte(acteur.perimetre, filtres)


@router.get("/kpis/timeseries", response_model=EerKpiSerieOut)
async def kpis_serie(
    granularite: Literal["jour", "semaine", "mois", "annee"] = "mois",
    filtres: FiltresDossiers = Depends(_filtres_kpi),
    acteur: Acteur = Depends(_acteur("eer.report.view")),
    db: AsyncSession = Depends(get_db),
):
    """Extension BEA-DIGITAL (absente de la synthèse Excel), sur la date EER."""
    return await EerReportingService(db).serie(acteur.perimetre, filtres, granularite)


@router.get("/kpis/dimensions/{dimension}", response_model=EerKpiRepartitionOut)
async def kpis_dimension(
    dimension: Literal[DIMENSIONS],  # type: ignore[valid-type]
    filtres: FiltresDossiers = Depends(_filtres_kpi),
    acteur: Acteur = Depends(_acteur("eer.report.view")),
    db: AsyncSession = Depends(get_db),
):
    """Extension BEA-DIGITAL : risque, PPE, FATCA, résidence, analyste, profil, sous-profil."""
    return await EerReportingService(db).par_dimension(acteur.perimetre, filtres, dimension)


# --- Dossier ----------------------------------------------------------------------------------

@router.post("/dossiers", response_model=EerDossierOut, status_code=status.HTTP_201_CREATED)
async def creer_dossier(
    payload: EerDossierCreate,
    acteur: Acteur = Depends(_acteur("eer.create")),
    db: AsyncSession = Depends(get_db),
):
    svc = EerDossierService(db)
    d = await svc.creer_dossier(
        acteur, agence_id=payload.agence_id, type_client=payload.type_client, profil=payload.profil,
        client=payload.client.model_dump(exclude_none=True, mode="json"), client_role=payload.client_role,
        dossier=payload.dossier, operation_type=payload.operation_type)
    out = _dossier_out(await svc.charger(d.id), acteur)
    await db.commit()
    return out


@router.get("/dossiers/{dossier_id}", response_model=EerDossierOut)
async def lire_dossier(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    return _dossier_out(await _dossier_visible(db, acteur, dossier_id), acteur)


@router.patch("/dossiers/{dossier_id}", response_model=EerMutationOut)
async def modifier_dossier(
    dossier_id: uuid.UUID,
    payload: EerDossierPatch,
    acteur: Acteur = Depends(_acteur(*_SAISIE)),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        for champ in payload.champs:
            await svc.completer_champ(acteur, dossier_id, champ.chemin, champ.valeur,
                                      dossier_partie_id=champ.dossier_partie_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Dossier mis à jour")


@router.post("/dossiers/{dossier_id}/parties", response_model=EerMutationOut)
async def ajouter_partie(
    dossier_id: uuid.UUID,
    payload: EerPartieAjout,
    acteur: Acteur = Depends(_acteur(*_SAISIE)),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.ajouter_partie(acteur, dossier_id, payload.role,
                                 payload.partie.model_dump(exclude_none=True, mode="json") if payload.partie else {},
                                 payload.role_attrs, nature=payload.nature, partie_id=payload.partie_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Partie ajoutée")


@router.post("/dossiers/{dossier_id}/detentions", response_model=EerMutationOut)
async def ajouter_detention(
    dossier_id: uuid.UUID,
    payload: EerDetentionIn,
    acteur: Acteur = Depends(_acteur(*_SAISIE)),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.ajouter_detention(acteur, dossier_id, payload.detenteur_partie_id, payload.detenue_partie_id,
                                    payload.pourcentage, payload.lien)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Détention enregistrée")


@router.get("/dossiers/{dossier_id}/beneficiaires", response_model=EerBeneficiairesOut)
async def beneficiaires(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    r = await EerDossierService(db).beneficiaires(dossier_id)
    return EerBeneficiairesOut(
        seuil=str(r.seuil), complet=r.complet, aucun_be_au_seuil=r.aucun_be_au_seuil,
        beneficiaires=[EerBeneficiaireOut(partie_id=b.partie_id, pourcentage=str(b.pourcentage))
                       for b in r.beneficiaires],
        a_verifier=[EerBeneficiaireOut(partie_id=b.partie_id) for b in r.a_verifier],
        problemes=[{"code": p.code} for p in r.problemes],
    )


@router.post("/dossiers/{dossier_id}/beneficiaires/apply", response_model=EerMutationOut)
async def appliquer_beneficiaires(
    dossier_id: uuid.UUID,
    payload: EerActionIn,
    acteur: Acteur = Depends(_acteur(*_SAISIE)),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.appliquer_beneficiaires(acteur, dossier_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Bénéficiaires effectifs appliqués")


@router.get("/dossiers/{dossier_id}/fiches", response_model=dict[str, list[EerFicheChampOut]])
async def fiches(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    resultat = await EerDossierService(db).fiches(dossier_id)
    return {code: [EerFicheChampOut(chemin=c.chemin, libelle=c.libelle, section=c.section,
                                    obligatoire=c.obligatoire, etat=c.etat,
                                    valeur=c.valeur if isinstance(c.valeur, (str, int, float, bool, type(None)))
                                    else str(c.valeur), bloquant=c.bloquant)
                   for c in champs] for code, champs in resultat.items()}


@router.post("/dossiers/{dossier_id}/fiches/confirm", response_model=EerMutationOut)
async def confirmer_champ(
    dossier_id: uuid.UUID,
    payload: EerConfirmIn,
    acteur: Acteur = Depends(_acteur("eer.control")),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.confirmer_champ(acteur, dossier_id, payload.chemin, dossier_partie_id=payload.dossier_partie_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Champ confirmé")


@router.post("/dossiers/{dossier_id}/fiches/complete", response_model=EerMutationOut)
async def terminer_fiches(
    dossier_id: uuid.UUID,
    payload: EerActionIn,
    acteur: Acteur = Depends(_acteur("eer.control")),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.terminer_fiches(acteur, dossier_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Fiches complétées")


# --- Workflow -------------------------------------------------------------------------------

def _transition_route(chemin: str, cible: Statut, permission: str, message: str) -> None:
    async def route(
        dossier_id: uuid.UUID,
        payload: EerActionIn,
        acteur: Acteur = Depends(_acteur(permission)),
        db: AsyncSession = Depends(get_db),
    ):
        async def op(svc: EerDossierService) -> None:
            await svc.transition(acteur, dossier_id, cible, motif=payload.motif)

        return await _muter(db, acteur, dossier_id, payload.revision, op, message)

    route.__name__ = f"eer_{chemin.replace('-', '_')}"
    router.add_api_route(f"/dossiers/{{dossier_id}}/{chemin}", route, methods=["POST"],
                         response_model=EerMutationOut, name=route.__name__)


_transition_route("submit", Statut.SOUMIS, "eer.submit", "Dossier soumis au contrôle")
_transition_route("start-control", Statut.EN_CONTROLE, "eer.control", "Contrôle démarré")
_transition_route("request-avis", Statut.AVIS_CONFORMITE, "eer.control", "Avis Conformité KYC demandé")
_transition_route("validate", Statut.VALIDE, "eer.validate", "Dossier validé")
_transition_route("close", Statut.CLOTURE, "eer.archive", "Dossier clôturé")
_transition_route("archive", Statut.ARCHIVE, "eer.archive", "Dossier archivé")
# Permission selon l'origine (brouillon : eer.update ; à compléter : eer.validate), vérifiée par le workflow.
_transition_route("abandon", Statut.ABANDONNE, "eer.view", "Dossier abandonné")
_transition_route("resubmit", Statut.RESOUMIS, "eer.complement.receive", "Dossier resoumis (nouvelle version)")


@router.post("/dossiers/{dossier_id}/supprimer", response_model=EerMutationOut)
async def supprimer_dossier(
    dossier_id: uuid.UUID,
    payload: EerActionIn,
    acteur: Acteur = Depends(_acteur("eer.admin")),
    db: AsyncSession = Depends(get_db),
):
    d = await EerDossierService(db).supprimer(acteur, dossier_id, payload.revision, payload.motif)
    out = EerMutationOut(id=d.id, statut=d.statut, etape=d.etape, revision=d.revision,
                         version_courante=d.version_courante, message="Dossier supprimé")
    await db.commit()
    return out


@router.post("/dossiers/{dossier_id}/assign", response_model=EerMutationOut)
async def affecter(
    dossier_id: uuid.UUID,
    payload: EerAssignIn,
    acteur: Acteur = Depends(_acteur("eer.assign")),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.transition(acteur, dossier_id, Statut.AFFECTE, analyste_id=payload.analyste_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Dossier affecté")


@router.post("/dossiers/{dossier_id}/decision", response_model=EerMutationOut)
async def decider(
    dossier_id: uuid.UUID,
    payload: EerDecisionIn,
    acteur: Acteur = Depends(_acteur("eer.control")),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.transition(acteur, dossier_id, Statut(payload.resultat), motif=payload.motif)

    return await _muter(db, acteur, dossier_id, payload.revision, op, f"Dossier déclaré {payload.resultat}")


# --- Checklist ------------------------------------------------------------------------------

@router.get("/dossiers/{dossier_id}/checklist", response_model=EerChecklistOut)
async def checklist(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    d = await _dossier_visible(db, acteur, dossier_id)
    items = sorted(d.items, key=lambda i: (i.ordre, i.regle_code, str(i.dossier_partie_id or "")))
    non_pointes = elements_non_pointes(EerDossierService._element(i) for i in d.items)
    connues = await EerDossierService(db).donnees_connues(dossier_id)
    return EerChecklistOut(dossier_id=d.id, etape=d.etape, revision=d.revision,
                           items=[EerChecklistItemOut.model_validate(i).model_copy(
                               update={"donnee_connue": connues.get(i.id)}) for i in items],
                           non_pointes=len(non_pointes))


@router.post("/dossiers/{dossier_id}/checklist/generate", response_model=EerMutationOut)
async def generer_checklist(
    dossier_id: uuid.UUID,
    payload: EerActionIn,
    acteur: Acteur = Depends(_acteur(*_SAISIE)),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.regenerer_checklist(acteur, dossier_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Checklist recalculée")


@router.patch("/dossiers/{dossier_id}/checklist/items/{item_id}", response_model=EerMutationOut)
async def pointer_item(
    dossier_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: EerPointageIn,
    acteur: Acteur = Depends(_acteur("eer.control")),
    db: AsyncSession = Depends(get_db),
):
    await _item_du_dossier(db, dossier_id, item_id)

    async def op(svc: EerDossierService) -> None:
        await svc.pointer(acteur, item_id, payload.presence, payload.motif, payload.document_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Élément pointé")


@router.post("/dossiers/{dossier_id}/checklist/validate", response_model=EerMutationOut)
async def valider_checklist(
    dossier_id: uuid.UUID,
    payload: EerActionIn,
    acteur: Acteur = Depends(_acteur("eer.control")),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.valider_checklist(acteur, dossier_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Checklist validée")


# --- Contrôles ------------------------------------------------------------------------------

@router.get("/dossiers/{dossier_id}/controls", response_model=EerControlesOut)
async def controles(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    lignes = (await db.execute(select(EerControle).where(EerControle.dossier_id == dossier_id)
                               .order_by(EerControle.execute_le.desc()))).scalars()
    decisions = (await db.execute(select(EerDecision).where(EerDecision.dossier_id == dossier_id)
                                  .order_by(EerDecision.decide_le.desc()))).scalars()
    return EerControlesOut(controles=[EerControleOut.model_validate(c) for c in lignes],
                           decisions=[EerDecisionOut.model_validate(x) for x in decisions])


@router.post("/dossiers/{dossier_id}/controls", response_model=EerControlesAutoOut)
async def executer_controles(
    dossier_id: uuid.UUID,
    payload: EerActionIn,
    acteur: Acteur = Depends(_acteur("eer.control")),
    db: AsyncSession = Depends(get_db),
):
    svc = EerDossierService(db)
    d = await svc.verrouiller(acteur, dossier_id, payload.revision)
    constats = await eer_controles_auto.executer(svc, acteur, dossier_id)
    out = EerControlesAutoOut(revision=d.revision, constats=[EerConstatOut(**c.to_dict()) for c in constats])
    await db.commit()
    return out


@router.patch("/dossiers/{dossier_id}/controls/{item_id}", response_model=EerMutationOut)
async def controle_manuel(
    dossier_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: EerControleManuelIn,
    acteur: Acteur = Depends(_acteur("eer.control")),
    db: AsyncSession = Depends(get_db),
):
    await _item_du_dossier(db, dossier_id, item_id)

    async def op(svc: EerDossierService) -> None:
        await svc.controler(acteur, item_id, payload.conforme, payload.motif, payload.motif_code)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Contrôle enregistré")


# --- Conformité : référence Excel / décision BEA-DIGITAL ------------------------------------

@router.get("/dossiers/{dossier_id}/compliance", response_model=EerConformiteOut)
async def conformite(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    """Les deux résultats côte à côte, avec l'explication de leur éventuel écart."""
    d = await _dossier_visible(db, acteur, dossier_id)
    ouvertes = list((await db.execute(select(EerAnomalie).where(
        EerAnomalie.dossier_id == dossier_id, EerAnomalie.statut.in_(list(ANOMALIES_OUVERTES)))
        .order_by(EerAnomalie.created_at))).scalars())
    bloquantes = [a for a in ouvertes if a.gravite == GraviteAnomalie.BLOQUANTE]
    derniere = await db.scalar(select(EerDecision).where(EerDecision.dossier_id == dossier_id)
                               .order_by(EerDecision.decide_le.desc()).limit(1))
    excel = classer_excel(d.conformite_physique, d.conformite_systeme)
    bea = classer_bea(d.decision_globale)
    ecart = expliquer_ecart(physique=d.conformite_physique, systeme=d.conformite_systeme,
                            coherence=d.conformite_coherence, decision_globale=d.decision_globale,
                            anomalies_bloquantes=[a.description for a in bloquantes])
    # Colonne Excel « Observations éléments non conformes », générée depuis les anomalies ouvertes.
    observations = "; ".join(a.description + (f" — {a.observation}" if a.observation else "") for a in ouvertes)
    return EerConformiteOut(
        dossier_id=d.id, version_courante=d.version_courante, revision=d.revision,
        conformite_physique=d.conformite_physique, conformite_systeme=d.conformite_systeme,
        conformite_coherence=d.conformite_coherence,
        reference_excel=EerReferenceExcelOut(
            classement=excel.classement, code_conforme=excel.code_conforme,
            code_non_conforme=excel.code_non_conforme, cellule_m=excel.cellule_m, cellule_n=excel.cellule_n),
        decision_bea=d.decision_globale, conformite_bea=bea,
        anomalies_bloquantes=[EerAnomalieBloquanteOut(id=a.id, type_code=a.type_code, description=a.description,
                                                      statut=a.statut) for a in bloquantes],
        divergence=excel.classement != bea, explication_ecart=ecart, observations=observations or None,
        derniere_decision=EerDecisionOut.model_validate(derniere) if derniere else None,
    )


@router.post("/dossiers/{dossier_id}/compliance/evaluate", response_model=EerMutationOut)
async def evaluer_conformite(
    dossier_id: uuid.UUID,
    payload: EerActionIn,
    acteur: Acteur = Depends(_acteur("eer.control")),
    db: AsyncSession = Depends(get_db),
):
    """Recalcule les axes et la décision (moteur existant, décision historisée) sans changer le statut."""
    async def op(svc: EerDossierService) -> None:
        await svc.calculer_decision(acteur, dossier_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Conformité évaluée")


# --- Anomalies ------------------------------------------------------------------------------

@router.get("/dossiers/{dossier_id}/anomalies", response_model=list[EerAnomalieOut])
async def anomalies(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    lignes = (await db.execute(select(EerAnomalie).where(EerAnomalie.dossier_id == dossier_id)
                               .order_by(EerAnomalie.created_at))).scalars()
    return [EerAnomalieOut.model_validate(a) for a in lignes]


@router.post("/dossiers/{dossier_id}/anomalies", response_model=EerMutationOut)
async def creer_anomalie(
    dossier_id: uuid.UUID,
    payload: EerAnomalieCreate,
    acteur: Acteur = Depends(_acteur("eer.control")),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.creer_anomalie(acteur, dossier_id, type_code=payload.type_code, gravite=payload.gravite,
                                 description=payload.description, item_id=payload.item_id, champ=payload.champ,
                                 observation=payload.observation, action_attendue=payload.action_attendue)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Anomalie enregistrée")


@router.post("/dossiers/{dossier_id}/anomalies/open", response_model=EerMutationOut)
async def ouvrir_anomalies(
    dossier_id: uuid.UUID,
    payload: EerActionIn,
    acteur: Acteur = Depends(_acteur("eer.control")),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.ouvrir_anomalies(acteur, dossier_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Anomalies ouvertes")


@router.patch("/dossiers/{dossier_id}/anomalies/{anomalie_id}", response_model=EerMutationOut)
async def modifier_anomalie(
    dossier_id: uuid.UUID,
    anomalie_id: uuid.UUID,
    payload: EerAnomaliePatch,
    acteur: Acteur = Depends(_acteur("eer.control", "eer.validate")),
    db: AsyncSession = Depends(get_db),
):
    await _anomalie_du_dossier(db, dossier_id, anomalie_id)

    async def op(svc: EerDossierService) -> None:
        if payload.accepter_justification is not None:
            await svc.accepter_anomalie(acteur, anomalie_id, payload.accepter_justification)
        else:
            await svc.modifier_anomalie(acteur, anomalie_id, gravite=payload.gravite,
                                        observation=payload.observation, action_attendue=payload.action_attendue,
                                        annuler_motif=payload.annuler_motif)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Anomalie mise à jour")


# --- Compléments ----------------------------------------------------------------------------

@router.post("/dossiers/{dossier_id}/complement", response_model=EerMutationOut)
async def demander_complement(
    dossier_id: uuid.UUID,
    payload: EerComplementIn,
    acteur: Acteur = Depends(_acteur("eer.complement.request")),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.transition(acteur, dossier_id, Statut.A_COMPLETER, motif=payload.consigne,
                             cibles=_cibles(payload.cibles), echeance=payload.echeance)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Complément demandé")


@router.get("/dossiers/{dossier_id}/complements", response_model=list[EerComplementOut])
async def complements(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    lignes = (await db.execute(select(EerComplement).where(EerComplement.dossier_id == dossier_id)
                               .order_by(EerComplement.numero))).scalars()
    return [EerComplementOut.model_validate(c) for c in lignes]


@router.post("/dossiers/{dossier_id}/complements/fourni", response_model=EerMutationOut)
async def complement_fourni(
    dossier_id: uuid.UUID,
    payload: EerComplementFourniIn,
    acteur: Acteur = Depends(_acteur("eer.complement.receive")),
    db: AsyncSession = Depends(get_db),
):
    await _item_du_dossier(db, dossier_id, payload.item_id)

    async def op(svc: EerDossierService) -> None:
        await svc.marquer_fourni(acteur, dossier_id, payload.item_id, payload.document_id)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Élément reçu")


@router.post("/dossiers/{dossier_id}/relance", response_model=EerMutationOut)
async def relancer(
    dossier_id: uuid.UUID,
    payload: EerActionIn,
    acteur: Acteur = Depends(_acteur("eer.complement.request")),
    db: AsyncSession = Depends(get_db),
):
    async def op(svc: EerDossierService) -> None:
        await svc.relancer(acteur, dossier_id, payload.motif)

    return await _muter(db, acteur, dossier_id, payload.revision, op, "Relance enregistrée")


# --- Avis Conformité KYC -------------------------------------------------------------------

@router.post("/dossiers/{dossier_id}/avis", response_model=EerMutationOut)
async def emettre_avis(
    dossier_id: uuid.UUID,
    payload: EerAvisIn,
    acteur: Acteur = Depends(_acteur("eer.avis")),
    db: AsyncSession = Depends(get_db),
):
    cible = Statut.VALIDE if payload.favorable else Statut.A_COMPLETER

    async def op(svc: EerDossierService) -> None:
        await svc.transition(acteur, dossier_id, cible, motif=payload.commentaire, avis_favorable=payload.favorable,
                             cibles=_cibles(payload.cibles), fonction_visa=payload.fonction)

    return await _muter(db, acteur, dossier_id, payload.revision, op,
                        "Avis favorable enregistré" if payload.favorable else "Avis défavorable enregistré")


@router.get("/dossiers/{dossier_id}/avis", response_model=list[EerVisaOut])
async def lire_avis(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    lignes = (await db.execute(select(EerVisa).where(EerVisa.dossier_id == dossier_id)
                               .order_by(EerVisa.vise_le))).scalars()
    return [EerVisaOut.model_validate(v) for v in lignes]


# --- Versions, historique, documents, audit (lecture seule) ---------------------------------

@router.get("/dossiers/{dossier_id}/versions", response_model=list[EerVersionLigne])
async def versions(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    lignes = (await db.execute(select(EerVersion).where(EerVersion.dossier_id == dossier_id)
                               .order_by(EerVersion.cree_le, EerVersion.numero))).scalars()
    return [EerVersionLigne.model_validate(v) for v in lignes]


@router.get("/dossiers/{dossier_id}/versions/{version_id}", response_model=EerVersionOut)
async def version(
    dossier_id: uuid.UUID,
    version_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    v = await db.get(EerVersion, version_id)
    if v is None or v.dossier_id != dossier_id:
        raise EerIntrouvable("Version introuvable")
    brut = json.dumps(v.contenu, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return EerVersionOut(id=v.id, numero=v.numero, evenement=v.evenement, empreinte=v.empreinte,
                         cree_par_id=v.cree_par_id, cree_le=v.cree_le, contenu=v.contenu,
                         empreinte_verifiee=hashlib.sha256(brut.encode("utf-8")).hexdigest() == v.empreinte)


@router.get("/dossiers/{dossier_id}/history", response_model=list[EerHistoriqueOut])
async def historique(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    lignes = (await db.execute(select(EerHistorique).where(EerHistorique.dossier_id == dossier_id)
                               .order_by(EerHistorique.cree_le, EerHistorique.id))).scalars()
    return [EerHistoriqueOut.model_validate(h) for h in lignes]


@router.get("/dossiers/{dossier_id}/documents", response_model=list[EerDocumentOut])
async def documents(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.document.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    lignes = (await db.execute(select(GedDocument).where(
        GedDocument.module_code == MODULE_CODE, GedDocument.entity == GED_ENTITE,
        GedDocument.entity_id == str(dossier_id), GedDocument.deleted_at.is_(None))
        .order_by(GedDocument.created_at))).scalars()
    return [EerDocumentOut.model_validate(g) for g in lignes]


@router.get("/dossiers/{dossier_id}/audit", response_model=list[EerAuditOut])
async def audit(
    dossier_id: uuid.UUID,
    acteur: Acteur = Depends(_acteur("eer.audit.view")),
    db: AsyncSession = Depends(get_db),
):
    await _dossier_visible(db, acteur, dossier_id)
    lignes = (await db.execute(select(AuditLog).where(
        AuditLog.entity == "eer_dossier", AuditLog.entity_id == str(dossier_id))
        .order_by(AuditLog.created_at))).scalars()
    return [EerAuditOut(id=a.id, action=a.action, user_id=a.user_id, created_at=a.created_at, after=a.after_data)
            for a in lignes]
