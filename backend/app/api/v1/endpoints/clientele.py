"""API Base Clientèle — imports ORION, situation, rapprochement, classification, filtrage, indicateurs, déclaration BCM."""

from __future__ import annotations

import uuid
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import auth_http_error, get_current_user
from app.db.session import get_db
from app.models import Agence, User
from app.schemas.clientele import (
    AlerteAttribuerIn,
    AlerteCommentaireIn,
    AlerteDecisionIn,
    BcmRefActiverIn,
    BcmRegleDecisionIn,
    ClassifBacktestIn,
    ClassifEvaluerIn,
    ClassifExcelIn,
    ClassifManuelIn,
    ClassifMoteurIn,
    ClassifMasseIn,
    ClassifMoteurScoringIn,
    ClassifRegleIn,
    ClassifTacheIn,
    ClassifVersionIn,
    DivergenceArbitrerIn,
    FiltrageEntreeIn,
    DeclarationBcmCreerIn,
    DeclarationBcmMotifIn,
    DeclarationBcmValiderIn,
    DeclarationSicCreerIn,
    DeclarationSicDepotIn,
    DeclarationSicValiderIn,
    ImportConfirmIn,
    ImportMappingIn,
    LotClasserIn,
    LotDateOuvertureIn,
    LotMajIn,
    LotControleDecisionIn,
    LotDivergencesIn,
    LotLignesDecisionIn,
    LotMappingIn,
    LotMotifIn,
    LotPreparationIn,
    AnalysteKycIn,
    AnalysteKycMajIn,
    RapprochementIn,
    ReexamenTraiterIn,
    SicAgenceIn,
    SicComplementIn,
    SicSecteurIn,
)
from app.data.clientele_import_hebdo import construire_modele
from app.services.clientele.analystes import ClienteleAnalysteService
from app.services.clientele.hebdo import ClienteleDecisionLotService
from app.services.clientele.journal import lister_journal
from app.services.clientele.lots import ClienteleLotService
from app.services.clientele.classification import (
    ClienteleClassificationService,
    autorisation_classement_masse,
)
from app.services.clientele.bcm_referentiel import ClienteleBcmReferentielService
from app.services.clientele.bcm_regles import ClienteleBcmReglesService
from app.services.clientele.declaration import ClienteleDeclarationService
from app.services.clientele.filtrage import ClienteleFiltrageService
from app.services.clientele.import_service import ClienteleImportService
from app.services.clientele.indicateurs import ClienteleIndicateursService
from app.services.clientele.rapprochement import ClienteleRapprochementService
from app.services.clientele.service import Ctx
from app.services.clientele.sic import ClienteleSicService
from app.services.clientele.situation import ClienteleSituationService, SOURCES_COLONNES
from app.services.clientele.taches import ClienteleTacheService
from app.services.clientele.vue360 import ClienteleVue360Service, filtres_depuis
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

router = APIRouter(prefix="/clientele", tags=["Base Clientèle"])

CAPACITES = {
    "voir": ("clientele.view",),
    "imports_voir": ("clientele.import.view", "clientele.import.execute"),
    "imports_executer": ("clientele.import.execute",),
    "rapprochement_voir": ("clientele.rapprochement.view",),
    "rapprochement_executer": ("clientele.rapprochement.execute",),
    "classif_voir": ("clientele.classif.view",),
    "classif_executer": ("clientele.classif.execute",),
    "classif_admin": ("clientele.classif.admin",),
    "classif_forcer": ("clientele.classif.force",),
    "classif_arbitrer": ("clientele.classif.arbitrer",),
    "filtrage_voir": ("clientele.filtrage.view",),
    "filtrage_executer": ("clientele.filtrage.execute",),
    "filtrage_decider": ("clientele.filtrage.decide",),
    "reporting_voir": ("clientele.reporting.view", "clientele.view"),
    "bcm_voir": ("clientele.bcm.view", "clientele.reporting.view"),
    "bcm_preparer": ("clientele.bcm.prepare",),
    "bcm_valider": ("clientele.bcm.valider",),
    "bcm_cloturer": ("clientele.bcm.cloturer",),
    "bcm_referentiel": ("clientele.bcm.referentiel",),
    "sic_depot": ("clientele.sic.depot",),
    "exporter": ("clientele.export",),
    "admin": ("clientele.admin",),
}


def ctx(*codes: str):
    async def dependance(request: Request, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)) -> Ctx:
        perms = set(await load_user_permission_codes(db, user))
        if codes and not (user.is_superuser or user_has_permission_codes(perms, *codes)):
            raise auth_http_error(status.HTTP_403_FORBIDDEN, "PERMISSION_DENIED", "Permission refusée",
                                  required=list(codes))
        return Ctx(user=user, permissions=perms, ip_address=request.client.host if request.client else None,
                   session_id=getattr(request.state, "bea_session_id", None))

    return dependance


@router.get("/config")
async def config(c: Ctx = Depends(ctx("clientele.view")),
                 db: AsyncSession = Depends(get_db)) -> dict:
    agences = (await db.execute(
        select(Agence.code, Agence.libelle)
        .where(Agence.deleted_at.is_(None), Agence.is_active.is_(True))
        .order_by(Agence.code)
    )).all()
    return {
        "capacites": {k: c.peut(*v) for k, v in CAPACITES.items()},
        "sources": SOURCES_COLONNES,
        "agences": [{"code": code, "libelle": libelle} for code, libelle in agences],
        "classement_masse": autorisation_classement_masse(),
    }


@router.get("/tableau-de-bord")
async def tableau(c: Ctx = Depends(ctx("clientele.view")),
                  db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleSituationService(db, c).tableau_de_bord()


@router.get("/situation")
async def situation(
    profil: str | None = Query(None),
    q: str | None = None,
    racine: str | None = None,
    nom: str | None = None,
    compte: str | None = None,
    rib: str | None = None,
    agence: str | None = None,
    etat: str | None = None,
    type_identifiant: str | None = None,
    page: int = 1,
    taille: int = 50,
    c: Ctx = Depends(ctx("clientele.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleSituationService(db, c).lister(
        profil=profil, q=q, racine=racine, nom=nom, compte=compte, rib=rib, agence=agence,
        etat=etat, type_identifiant=type_identifiant, page=page, taille=taille)


@router.get("/clients/{racine}")
async def fiche(racine: str, c: Ctx = Depends(ctx("clientele.view")),
                db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleSituationService(db, c).fiche(racine)


@router.get("/imports")
async def imports(c: Ctx = Depends(ctx("clientele.import.view", "clientele.import.execute")),
                  db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleImportService(db, c).lister()


@router.post("/imports/analyse", status_code=201)
async def analyser_import(fichier: UploadFile = File(...), c: Ctx = Depends(ctx("clientele.import.execute")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    contenu = await fichier.read()
    return await ClienteleImportService(db, c).analyser(contenu, fichier.filename or "import.xlsx")


@router.get("/imports/{iid}")
async def detail_import(iid: uuid.UUID, c: Ctx = Depends(ctx("clientele.import.view", "clientele.import.execute")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleImportService(db, c).detail(iid)


@router.post("/imports/{iid}/mapping")
async def mapping_import(iid: uuid.UUID, body: ImportMappingIn,
                         c: Ctx = Depends(ctx("clientele.import.execute")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleImportService(db, c).recartographier(iid, body.mapping)


@router.get("/imports/{iid}/anomalies")
async def anomalies_import(
    iid: uuid.UUID,
    code: str | None = None,
    bloquante: bool | None = None,
    page: int = 1,
    taille: int = 100,
    c: Ctx = Depends(ctx("clientele.import.view", "clientele.import.execute")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleImportService(db, c).anomalies(iid, code=code, bloquante=bloquante,
                                                         page=page, taille=taille)


@router.get("/imports/{iid}/anomalies.xlsx")
async def exporter_anomalies(iid: uuid.UUID, c: Ctx = Depends(ctx("clientele.import.view", "clientele.export")),
                             db: AsyncSession = Depends(get_db)) -> Response:
    contenu = await ClienteleImportService(db, c).exporter_anomalies(iid)
    nom = f"anomalies-import-{iid}.xlsx"
    return Response(content=contenu, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"{nom}\"; filename*=UTF-8''{quote(nom)}",
                             "Cache-Control": "no-store"})


@router.post("/imports/{iid}/confirmer")
async def confirmer_import(iid: uuid.UUID, body: ImportConfirmIn,
                           c: Ctx = Depends(ctx("clientele.import.execute")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleImportService(db, c).confirmer(iid, body.model_dump())


@router.post("/imports/{iid}/abandonner")
async def abandonner_import(iid: uuid.UUID, c: Ctx = Depends(ctx("clientele.import.execute")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleImportService(db, c).abandonner(iid)


@router.delete("/imports/{iid}", status_code=204)
async def supprimer_import(iid: uuid.UUID, c: Ctx = Depends(ctx("clientele.admin")),
                           db: AsyncSession = Depends(get_db)) -> Response:
    await ClienteleImportService(db, c).supprimer(iid)
    return Response(status_code=204)


@router.get("/lots")
async def lots_lister(page: int = 1,
                      c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute",
                                           "clientele.classif.view")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleLotService(db, c).lister(page=page)


@router.get("/lots/modele.xlsx")
async def lot_modele(
    c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute", "clientele.classif.view")),
) -> Response:
    return _xlsx(construire_modele(), "modele-import-hebdomadaire-classification.xlsx")


@router.post("/lots/analyse", status_code=201)
async def lot_analyser(fichier: UploadFile = File(...), type: str = Query("LISTE"),
                       periode_reference: date | None = Query(None), forcer: bool = Query(False),
                       c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    contenu = await fichier.read()
    return await ClienteleLotService(db, c).analyser(contenu, fichier.filename or "lot.xlsx", type_lot=type,
                                                     periode_reference=periode_reference, forcer=forcer)


@router.get("/lots/{lid}/integration")
async def lot_integration_apercu(lid: uuid.UUID, c: Ctx = Depends(ctx("clientele.import.execute")),
                                 db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleDecisionLotService(db, c).apercu_integration(lid)


@router.post("/lots/{lid}/integrer")
async def lot_integrer(lid: uuid.UUID, body: LotMotifIn, c: Ctx = Depends(ctx("clientele.import.execute")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleDecisionLotService(db, c).integrer(lid, body.model_dump())


@router.get("/lots/{lid}/rejets.xlsx")
async def lot_rejets(lid: uuid.UUID,
                     c: Ctx = Depends(ctx("clientele.import.view", "clientele.import.execute",
                                          "clientele.classif.execute")),
                     db: AsyncSession = Depends(get_db)) -> Response:
    contenu, nom = await ClienteleDecisionLotService(db, c).rejets_xlsx(lid)
    return _xlsx(contenu, nom)


@router.post("/lots/{lid}/lignes/preparer")
async def lot_preparer(lid: uuid.UUID, body: LotPreparationIn, c: Ctx = Depends(ctx("clientele.classif.execute")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleDecisionLotService(db, c).preparer_decisions(lid, body.model_dump())


@router.post("/lots/{lid}/confirmer")
async def lot_confirmer(lid: uuid.UUID, body: LotMotifIn, c: Ctx = Depends(ctx("clientele.classif.execute")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleDecisionLotService(db, c).confirmer(lid, body.model_dump())


@router.post("/lots/{lid}/date-ouverture")
async def lot_date_ouverture(lid: uuid.UUID, body: LotDateOuvertureIn,
                             c: Ctx = Depends(ctx("clientele.classif.execute")),
                             db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleLotService(db, c).saisir_date_ouverture(lid, body.model_dump())


@router.post("/lots/{lid}/divergences")
async def lot_divergences(lid: uuid.UUID, body: LotDivergencesIn,
                          c: Ctx = Depends(ctx("clientele.classif.execute")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleLotService(db, c).decider_divergences(lid, body.model_dump())


@router.post("/lots/{lid}/controle/decision")
async def lot_controle_decision(lid: uuid.UUID, body: LotControleDecisionIn,
                                c: Ctx = Depends(ctx("clientele.classif.execute")),
                                db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleLotService(db, c).decider_controle(lid, body.model_dump())


@router.get("/lots/{lid}")
async def lot_detail(lid: uuid.UUID, statut: str | None = None, page: int = 1,
                     q: str | None = Query(None, max_length=120), profil: str | None = None,
                     c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute")),
                     db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleLotService(db, c).detail(lid, statut=statut, page=page, q=q, profil=profil)


@router.post("/lots/{lid}/mapping")
async def lot_mapping(lid: uuid.UUID, body: LotMappingIn,
                      c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleLotService(db, c).recartographier(lid, body.model_dump())


@router.post("/lots/{lid}/evaluer")
async def lot_evaluer(lid: uuid.UUID, c: Ctx = Depends(ctx("clientele.classif.view")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleLotService(db, c).evaluer(lid)


@router.post("/lots/{lid}/classer")
async def lot_classer(lid: uuid.UUID, body: LotClasserIn, c: Ctx = Depends(ctx("clientele.classif.execute")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleLotService(db, c).classer(lid, body.model_dump())


@router.get("/lots/{lid}/export.xlsx")
async def lot_export(lid: uuid.UUID, c: Ctx = Depends(ctx("clientele.export", "clientele.classif.execute")),
                     db: AsyncSession = Depends(get_db)) -> Response:
    return _xlsx(await ClienteleLotService(db, c).exporter(lid), f"lot-{lid}.xlsx")


@router.patch("/lots/{lid}")
async def lot_modifier(lid: uuid.UUID, body: LotMajIn,
                       c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleLotService(db, c).mettre_a_jour(lid, body.model_dump(exclude_unset=True))


@router.post("/lots/{lid}/fermer", status_code=204)
async def lot_fermer(lid: uuid.UUID,
                     c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute")),
                     db: AsyncSession = Depends(get_db)) -> Response:
    await ClienteleLotService(db, c).fermer(lid)
    return Response(status_code=204)


@router.delete("/lots/{lid}", status_code=204)
async def lot_supprimer(lid: uuid.UUID,
                        motif: str | None = Query(None, max_length=2000),
                        c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute")),
                        db: AsyncSession = Depends(get_db)) -> Response:
    await ClienteleLotService(db, c).supprimer(lid, motif=motif)
    return Response(status_code=204)


@router.post("/lots/{lid}/lignes/decision")
async def lot_lignes_decision(lid: uuid.UUID, body: LotLignesDecisionIn,
                              c: Ctx = Depends(ctx("clientele.classif.execute")),
                              db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleDecisionLotService(db, c).decider(lid, body.model_dump())


@router.get("/lots/{lid}/bilan")
async def lot_bilan(lid: uuid.UUID,
                    c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute",
                                         "clientele.classif.view")),
                    db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleDecisionLotService(db, c).bilan(lid)


@router.get("/lots/{lid}/bilan.xlsx")
async def lot_bilan_xlsx(lid: uuid.UUID, c: Ctx = Depends(ctx("clientele.export", "clientele.classif.execute")),
                         db: AsyncSession = Depends(get_db)) -> Response:
    contenu, nom = await ClienteleDecisionLotService(db, c).bilan_xlsx(lid)
    return _xlsx(contenu, nom)


@router.get("/lots/{lid}/fichier")
async def lot_fichier(lid: uuid.UUID, c: Ctx = Depends(ctx("clientele.export", "clientele.classif.execute")),
                      db: AsyncSession = Depends(get_db)) -> Response:
    contenu, nom = await ClienteleLotService(db, c).fichier(lid)
    return _xlsx(contenu, nom)


def _xlsx(contenu: bytes, nom: str) -> Response:
    ascii_nom = nom.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
    return Response(content=contenu, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"{ascii_nom}\"; "
                                                    f"filename*=UTF-8''{quote(nom)}",
                             "Cache-Control": "no-store"})


def _pdf(contenu: bytes, nom: str) -> Response:
    return Response(content=contenu, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=\"{nom}\"; filename*=UTF-8''{quote(nom)}",
                             "Cache-Control": "no-store"})


@router.get("/rapprochements/imports")
async def rapprochement_imports(
    c: Ctx = Depends(ctx("clientele.rapprochement.view", "clientele.import.view")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await ClienteleRapprochementService(db, c).lister_imports()


@router.get("/rapprochements")
async def rapprochements(c: Ctx = Depends(ctx("clientele.rapprochement.view")),
                         db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleRapprochementService(db, c).lister()


@router.post("/rapprochements", status_code=201)
async def calculer_rapprochement(body: RapprochementIn,
                                 c: Ctx = Depends(ctx("clientele.rapprochement.execute")),
                                 db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleRapprochementService(db, c).calculer(body.import_a_id, body.import_b_id)


@router.get("/rapprochements/{rid}")
async def detail_rapprochement(rid: uuid.UUID, c: Ctx = Depends(ctx("clientele.rapprochement.view")),
                               db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleRapprochementService(db, c).detail(rid)


@router.get("/rapprochements/{rid}/ecarts")
async def ecarts_rapprochement(
    rid: uuid.UUID,
    objet: str | None = None,
    categorie: str | None = None,
    champ: str | None = None,
    q: str | None = None,
    page: int = 1,
    taille: int = 80,
    c: Ctx = Depends(ctx("clientele.rapprochement.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleRapprochementService(db, c).ecarts(
        rid, objet=objet, categorie=categorie, champ=champ, q=q, page=page, taille=taille)


@router.get("/rapprochements/{rid}/export.xlsx")
async def rapprochement_xlsx(rid: uuid.UUID, c: Ctx = Depends(ctx("clientele.rapprochement.view", "clientele.export")),
                             db: AsyncSession = Depends(get_db)) -> Response:
    return _xlsx(await ClienteleRapprochementService(db, c).exporter_excel(rid), f"rapprochement-{rid}.xlsx")


@router.get("/rapprochements/{rid}/export.pdf")
async def rapprochement_pdf(rid: uuid.UUID, c: Ctx = Depends(ctx("clientele.rapprochement.view", "clientele.export")),
                            db: AsyncSession = Depends(get_db)) -> Response:
    return _pdf(await ClienteleRapprochementService(db, c).exporter_pdf(rid), f"rapprochement-{rid}.pdf")


@router.get("/classification/referentiel")
async def classif_referentiel(c: Ctx = Depends(ctx("clientele.classif.view")),
                              db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).referentiel()


@router.get("/classification/matrice")
async def classif_matrice(c: Ctx = Depends(ctx("clientele.classif.view")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).matrice_maitre()


@router.get("/classification/valeurs")
async def classif_valeurs(
    dimension: str | None = None, statut: str | None = None,
    page: int = 1, taille: int = 80,
    c: Ctx = Depends(ctx("clientele.classif.view")), db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleClassificationService(db, c).valeurs_maitres(
        dimension=dimension, statut=statut, page=page, taille=taille)


@router.get("/classification/divergences")
async def classif_divergences(
    domaine: str | None = None, page: int = 1, taille: int = 80,
    c: Ctx = Depends(ctx("clientele.classif.view")), db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleClassificationService(db, c).divergences(
        domaine=domaine, page=page, taille=taille)


@router.post("/classification/evaluer")
async def classif_evaluer(body: ClassifEvaluerIn,
                          c: Ctx = Depends(ctx("clientele.classif.view")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).evaluer_racine(
        body.racine, persister=body.persister)


@router.post("/classification/backtest")
async def classif_backtest(body: ClassifBacktestIn,
                           c: Ctx = Depends(ctx("clientele.classif.execute")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).backtester(limite=body.limite)


@router.get("/classification")
async def classif_liste(
    niveau: str | None = None, source: str | None = None, q: str | None = None,
    analyste: str | None = Query(None, max_length=120),
    page: int = 1, taille: int = 50,
    c: Ctx = Depends(ctx("clientele.classif.view")), db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleClassificationService(db, c).lister(
        niveau=niveau, source=source, q=q, analyste=analyste, page=page, taille=taille)


def _filtres_resultats(ecart: bool | None = None, niveau: str | None = None, statut: str | None = None,
                       source: str | None = None, q: str | None = Query(None, max_length=120)) -> dict:
    return {"ecart": ecart, "niveau": niveau, "statut": statut, "source": source, "q": q}


@router.get("/classification/resultats")
async def classif_resultats(f: dict = Depends(_filtres_resultats), page: int = 1, taille: int = 50,
                            c: Ctx = Depends(ctx("clientele.classif.view")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).resultats(**f, page=page, taille=taille)


@router.get("/classification/resultats.xlsx")
async def classif_resultats_xlsx(f: dict = Depends(_filtres_resultats),
                                 c: Ctx = Depends(ctx("clientele.classif.view")),
                                 db: AsyncSession = Depends(get_db)) -> Response:
    return _xlsx(await ClienteleClassificationService(db, c).resultats_xlsx(**f),
                 f"resultats-moteur-{date.today().isoformat()}.xlsx")


def _filtres_historique(q: str | None = Query(None, max_length=120), source: str | None = None,
                        analyste: str | None = Query(None, max_length=120), lot_id: uuid.UUID | None = None,
                        du: date | None = None, au: date | None = None) -> dict:
    return {"q": q, "source": source, "analyste": analyste, "lot_id": lot_id, "du": du, "au": au}


@router.get("/classification/historique")
async def classif_historique_global(f: dict = Depends(_filtres_historique), page: int = 1, taille: int = 50,
                                    c: Ctx = Depends(ctx("clientele.classif.view")),
                                    db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).historique_global(**f, page=page, taille=taille)


@router.get("/classification/historique.xlsx")
async def classif_historique_xlsx(f: dict = Depends(_filtres_historique),
                                  c: Ctx = Depends(ctx("clientele.classif.view")),
                                  db: AsyncSession = Depends(get_db)) -> Response:
    return _xlsx(await ClienteleClassificationService(db, c).historique_xlsx(**f),
                 f"historique-classifications-{date.today().isoformat()}.xlsx")


@router.get("/analystes")
async def analystes_lister(c: Ctx = Depends(ctx("clientele.classif.view")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleAnalysteService(db, c).lister()


@router.get("/analystes/utilisateurs")
async def analystes_utilisateurs(q: str | None = Query(None, max_length=120),
                                 c: Ctx = Depends(ctx("clientele.classif.admin")),
                                 db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleAnalysteService(db, c).utilisateurs(q)


@router.post("/analystes", status_code=201)
async def analystes_creer(body: AnalysteKycIn, c: Ctx = Depends(ctx("clientele.classif.admin")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleAnalysteService(db, c).creer(body.model_dump())


@router.patch("/analystes/{aid}")
async def analystes_modifier(aid: uuid.UUID, body: AnalysteKycMajIn,
                             c: Ctx = Depends(ctx("clientele.classif.admin")),
                             db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleAnalysteService(db, c).modifier(aid, body.model_dump(exclude_unset=True))


@router.get("/classification/modele.xlsx")
async def classif_modele(c: Ctx = Depends(ctx("clientele.classif.execute")),
                         db: AsyncSession = Depends(get_db)) -> Response:
    return _xlsx(await ClienteleClassificationService(db, c).modele_excel(), "modele-classification.xlsx")


@router.post("/classification/excel/analyse")
async def classif_excel_analyse(fichier: UploadFile = File(...),
                                c: Ctx = Depends(ctx("clientele.classif.execute")),
                                db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).analyser_excel(await fichier.read())


@router.post("/classification/excel/confirmer")
async def classif_excel_confirmer(body: ClassifExcelIn,
                                  c: Ctx = Depends(ctx("clientele.classif.execute")),
                                  db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).confirmer_excel(body.lignes)


@router.post("/classification/appliquer")
async def classif_appliquer(body: ClassifMoteurIn,
                            c: Ctx = Depends(ctx("clientele.classif.execute")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).appliquer_moteur(racine=body.racine, forcer=body.forcer)


@router.post("/classification/versions")
async def classif_creer_version(body: ClassifVersionIn,
                                c: Ctx = Depends(ctx("clientele.classif.admin")),
                                db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).creer_version(body.model_dump())


@router.get("/classification/versions/{vid}")
async def classif_version(vid: uuid.UUID, c: Ctx = Depends(ctx("clientele.classif.view")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).version_detail(vid)


@router.post("/classification/versions/{vid}/activer")
async def classif_activer(vid: uuid.UUID, c: Ctx = Depends(ctx("clientele.classif.admin")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).activer_version(vid)


@router.post("/classification/versions/{vid}/regles")
async def classif_creer_regle(vid: uuid.UUID, body: ClassifRegleIn,
                              c: Ctx = Depends(ctx("clientele.classif.admin")),
                              db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).creer_regle(vid, body.model_dump())


@router.patch("/classification/regles/{rid}")
async def classif_modifier_regle(rid: uuid.UUID, body: ClassifRegleIn,
                                 c: Ctx = Depends(ctx("clientele.classif.admin")),
                                 db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).modifier_regle(rid, body.model_dump())


@router.delete("/classification/regles/{rid}")
async def classif_supprimer_regle(rid: uuid.UUID, c: Ctx = Depends(ctx("clientele.classif.admin")),
                                  db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).supprimer_regle(rid)


@router.get("/clients/{racine}/classification")
async def classif_client(racine: str, c: Ctx = Depends(ctx("clientele.classif.view")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).courante(racine)


@router.post("/clients/{racine}/classification")
async def classif_client_modifier(racine: str, body: ClassifManuelIn,
                                  c: Ctx = Depends(ctx("clientele.classif.execute")),
                                  db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).modifier_individuel(racine, body.model_dump())


@router.post("/clients/{racine}/classification/moteur")
async def classif_client_moteur(racine: str, body: ClassifMoteurScoringIn,
                                c: Ctx = Depends(ctx("clientele.classif.execute")),
                                db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).classer_par_moteur(racine, body.model_dump())


@router.post("/classification/moteur-masse")
async def classif_moteur_masse(body: ClassifMasseIn, c: Ctx = Depends(ctx("clientele.classif.execute")),
                               db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).classer_masse_moteur(body.model_dump())


@router.get("/classification/taches/perimetre")
async def classif_taches_perimetre(c: Ctx = Depends(ctx("clientele.classif.view")),
                                   db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleTacheService(db, c).perimetre()


@router.get("/classification/taches/autorisation")
async def classif_taches_autorisation(c: Ctx = Depends(ctx("clientele.classif.view")),
                                      db: AsyncSession = Depends(get_db)) -> dict:
    return ClienteleTacheService(db, c).autorisation()


@router.get("/classification/taches/courante")
async def classif_tache_courante(c: Ctx = Depends(ctx("clientele.classif.view")),
                                 db: AsyncSession = Depends(get_db)) -> dict | None:
    return await ClienteleTacheService(db, c).courante()


@router.post("/classification/taches", status_code=status.HTTP_202_ACCEPTED)
async def classif_tache_lancer(body: ClassifTacheIn, c: Ctx = Depends(ctx("clientele.classif.execute")),
                               db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleTacheService(db, c).lancer(body.model_dump())


@router.get("/classification/taches/{tache_id}")
async def classif_tache_detail(tache_id: uuid.UUID, c: Ctx = Depends(ctx("clientele.classif.view")),
                               db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleTacheService(db, c).detail(tache_id)


@router.post("/classification/taches/{tache_id}/reprendre", status_code=status.HTTP_202_ACCEPTED)
async def classif_tache_reprendre(tache_id: uuid.UUID, c: Ctx = Depends(ctx("clientele.classif.execute")),
                                  db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleTacheService(db, c).reprendre(tache_id)


@router.get("/clients/{racine}/classification/historique")
async def classif_client_historique(racine: str, c: Ctx = Depends(ctx("clientele.classif.view")),
                                    db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleClassificationService(db, c).historique(racine)


@router.get("/clients/{racine}/journal")
async def client_journal(racine: str, page: int = 1, taille: int = 100,
                         c: Ctx = Depends(ctx("clientele.classif.view")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    return await lister_journal(db, racine=ClienteleClassificationService._racine(racine), page=page,
                                taille=taille)


@router.get("/classification/recherche")
async def classif_recherche(q: str = Query("", max_length=60), page: int = 1, taille: int = 25,
                            c: Ctx = Depends(ctx("clientele.classif.view")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).rechercher(q, page=page, taille=taille)


@router.get("/classification/analystes")
async def classif_analystes(c: Ctx = Depends(ctx("clientele.classif.view")),
                            db: AsyncSession = Depends(get_db)) -> list[str]:
    return await ClienteleClassificationService(db, c).analystes()


@router.get("/classification/journal")
async def classif_journal(racine: str | None = None, lot_id: uuid.UUID | None = None,
                          type_action: str | None = None, origine: str | None = None, page: int = 1,
                          taille: int = 50, c: Ctx = Depends(ctx("clientele.classif.view")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await lister_journal(db, racine=(racine or "").strip() or None, lot_id=lot_id,
                                type_action=type_action, origine=origine, page=page, taille=taille)


@router.get("/classification/reexamens")
async def classif_reexamens(statut: str | None = "OUVERT", racine: str | None = None, page: int = 1,
                            taille: int = 50, c: Ctx = Depends(ctx("clientele.classif.view")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).lister_reexamens(
        statut=statut or None, racine=racine, page=page, taille=taille)


@router.post("/classification/reexamens/{rid}/traiter")
async def classif_reexamen_traiter(rid: uuid.UUID, body: ReexamenTraiterIn,
                                   c: Ctx = Depends(ctx("clientele.classif.arbitrer")),
                                   db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).traiter_reexamen(rid, body.model_dump())


@router.post("/classification/divergences/{did}/arbitrer")
async def classif_divergence_arbitrer(did: uuid.UUID, body: DivergenceArbitrerIn,
                                      c: Ctx = Depends(ctx("clientele.classif.arbitrer")),
                                      db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).arbitrer_divergence(did, body.model_dump())


@router.get("/classification/divergences/{did}/historique")
async def classif_divergence_historique(did: uuid.UUID, c: Ctx = Depends(ctx("clientele.classif.view")),
                                        db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleClassificationService(db, c).divergence_historique(did)


@router.get("/filtrage/listes")
async def filtrage_listes(c: Ctx = Depends(ctx("clientele.filtrage.view")),
                          db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleFiltrageService(db, c).listes()


@router.get("/filtrage/listes/{lid}/entrees")
async def filtrage_entrees(lid: uuid.UUID, page: int = 1, taille: int = 50, q: str | None = None,
                           c: Ctx = Depends(ctx("clientele.filtrage.view")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleFiltrageService(db, c).entrees(lid, page=page, taille=taille, recherche=q)


@router.post("/filtrage/listes/{lid}/entrees", status_code=201)
async def filtrage_ajouter_entree(lid: uuid.UUID, body: FiltrageEntreeIn,
                                  c: Ctx = Depends(ctx("clientele.filtrage.execute")),
                                  db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleFiltrageService(db, c).ajouter_entree(lid, body.model_dump())


@router.post("/filtrage/scan")
async def filtrage_scan(c: Ctx = Depends(ctx("clientele.filtrage.execute")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleFiltrageService(db, c).scanner()


@router.get("/filtrage/alertes")
async def filtrage_alertes(
    statut: str | None = None, racine: str | None = None, motif: str | None = None,
    groupe: str | None = None, source: str | None = None, profil: str | None = None,
    agence: str | None = None, assignee: str | None = None, du: date | None = None, au: date | None = None,
    anciennete_min: int | None = Query(None, ge=0, le=3650), q: str | None = None, tri: str | None = None,
    niveau: str | None = None, profilage: str | None = None, filtrage: str | None = None,
    anomalie: str | None = None, coherence: str | None = None, completude: str | None = None,
    page: int = 1, taille: int = 50,
    c: Ctx = Depends(ctx("clientele.filtrage.view")), db: AsyncSession = Depends(get_db),
) -> dict:
    population = ClienteleVue360Service(db, c).population(filtres_depuis(
        niveau=niveau, profilage=profilage, filtrage=filtrage, anomalie=anomalie, coherence=coherence,
        completude=completude))
    return await ClienteleFiltrageService(db, c).lister(
        statut=statut, racine=racine, motif=motif, groupe=groupe, source=source, profil=profil, agence=agence,
        assignee=assignee, du=du, au=au, anciennete_min=anciennete_min, q=q, tri=tri, page=page, taille=taille,
        population=population)


@router.get("/filtrage/agents")
async def filtrage_agents(c: Ctx = Depends(ctx("clientele.filtrage.view")),
                          db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleFiltrageService(db, c).agents()


@router.post("/filtrage/alertes/{aid}/attribuer")
async def filtrage_attribuer(aid: uuid.UUID, body: AlerteAttribuerIn,
                             c: Ctx = Depends(ctx("clientele.filtrage.decide")),
                             db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleFiltrageService(db, c).attribuer(aid, body.model_dump())


@router.post("/filtrage/alertes/{aid}/commentaires")
async def filtrage_commenter(aid: uuid.UUID, body: AlerteCommentaireIn,
                             c: Ctx = Depends(ctx("clientele.filtrage.decide")),
                             db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleFiltrageService(db, c).commenter(aid, body.model_dump())


async def filtres_360(
    periode: str | None = None, du: date | None = None, au: date | None = None, profil: str | None = None,
    agence: str | None = None, niveau: str | None = None, profilage: str | None = None,
    filtrage: str | None = None, anomalie: str | None = None, coherence: str | None = None,
    completude: str | None = None, q: str | None = Query(None, max_length=80), classe_periode: bool = False,
) -> dict:
    return filtres_depuis(periode=periode, du=du, au=au, profil=profil, agence=agence, niveau=niveau,
                          profilage=profilage, filtrage=filtrage, anomalie=anomalie, coherence=coherence,
                          completude=completude, q=q, classe_periode=classe_periode or None)


@router.get("/vue360/synthese")
async def vue360_synthese(f: dict = Depends(filtres_360), c: Ctx = Depends(ctx("clientele.filtrage.view")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleVue360Service(db, c).synthese(f)


@router.get("/vue360/clients")
async def vue360_clients(f: dict = Depends(filtres_360), page: int = 1, taille: int = 50, tri: str | None = None,
                         c: Ctx = Depends(ctx("clientele.filtrage.view")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleVue360Service(db, c).clients(f, page=page, taille=taille, tri=tri)


@router.get("/vue360/clients/{racine}")
async def vue360_fiche(racine: str, c: Ctx = Depends(ctx("clientele.filtrage.view")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleVue360Service(db, c).fiche(racine)


@router.get("/vue360/journal")
async def vue360_journal(action: str | None = None, objet_id: str | None = None, du: date | None = None,
                         au: date | None = None, page: int = 1, taille: int = 50,
                         c: Ctx = Depends(ctx("clientele.filtrage.view")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleVue360Service(db, c).journal(
        action=action, objet_id=objet_id, du=du, au=au, page=page, taille=taille)


@router.get("/vue360/export.xlsx")
async def vue360_export(f: dict = Depends(filtres_360), c: Ctx = Depends(ctx("clientele.export")),
                        db: AsyncSession = Depends(get_db)) -> Response:
    contenu, _n = await ClienteleVue360Service(db, c).export_xlsx(f)
    nom = f"vue360_clientele_{date.today().isoformat()}.xlsx"
    return Response(content=contenu,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"{nom}\"", "Cache-Control": "no-store"})


@router.get("/filtrage/alertes/{aid}")
async def filtrage_alerte(aid: uuid.UUID, c: Ctx = Depends(ctx("clientele.filtrage.view")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleFiltrageService(db, c).detail(aid)


@router.post("/filtrage/alertes/{aid}/decision")
async def filtrage_decision(aid: uuid.UUID, body: AlerteDecisionIn,
                            c: Ctx = Depends(ctx("clientele.filtrage.decide")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleFiltrageService(db, c).decider(aid, body.model_dump())


@router.post("/filtrage/alertes/{aid}/justificatifs")
async def filtrage_justificatif(aid: uuid.UUID, fichier: UploadFile = File(...),
                                c: Ctx = Depends(ctx("clientele.filtrage.decide")),
                                db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleFiltrageService(db, c).deposer_justificatif(
        aid, await fichier.read(), fichier.filename or "justificatif")


@router.get("/filtrage/alertes/{aid}/justificatifs/{jid}")
async def filtrage_lire_justificatif(aid: uuid.UUID, jid: uuid.UUID,
                                     c: Ctx = Depends(ctx("clientele.filtrage.view")),
                                     db: AsyncSession = Depends(get_db)) -> Response:
    contenu, nom = await ClienteleFiltrageService(db, c).lire_justificatif(aid, jid)
    return Response(content=contenu, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename=\"{nom}\"",
                             "Cache-Control": "no-store"})


def _params_indicateurs(
    periode: str,
    date_debut: date | None,
    date_fin: date | None,
    agence: str | None,
    profil: str | None,
    residence: str | None,
) -> dict:
    return {
        "periode": periode,
        "date_debut": date_debut,
        "date_fin": date_fin,
        "agence": agence,
        "profil": profil,
        "residence": residence,
    }


@router.get("/indicateurs.xlsx")
async def exporter_indicateurs(
    periode: str = Query("mois_courant"),
    date_debut: date | None = None,
    date_fin: date | None = None,
    agence: str | None = None,
    profil: str | None = None,
    residence: str | None = None,
    c: Ctx = Depends(ctx("clientele.export")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    contenu = await ClienteleIndicateursService(db, c).exporter_tableau(
        **_params_indicateurs(periode, date_debut, date_fin, agence, profil, residence))
    return _xlsx(contenu, "indicateurs-clientele.xlsx")


@router.get("/indicateurs.pdf")
async def exporter_indicateurs_pdf(
    periode: str = Query("mois_courant"),
    date_debut: date | None = None,
    date_fin: date | None = None,
    agence: str | None = None,
    profil: str | None = None,
    residence: str | None = None,
    c: Ctx = Depends(ctx("clientele.export")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    contenu = await ClienteleIndicateursService(db, c).exporter_tableau_pdf(
        **_params_indicateurs(periode, date_debut, date_fin, agence, profil, residence))
    return _pdf(contenu, "indicateurs-clientele.pdf")


@router.get("/indicateurs")
async def lister_indicateurs(
    periode: str = Query("mois_courant"),
    date_debut: date | None = None,
    date_fin: date | None = None,
    agence: str | None = None,
    profil: str | None = None,
    residence: str | None = None,
    c: Ctx = Depends(ctx("clientele.reporting.view", "clientele.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleIndicateursService(db, c).tableau(
        **_params_indicateurs(periode, date_debut, date_fin, agence, profil, residence))


@router.get("/indicateurs/{code}/lignes.xlsx")
async def exporter_lignes_indicateur(
    code: str,
    periode: str = Query("mois_courant"),
    date_debut: date | None = None,
    date_fin: date | None = None,
    agence: str | None = None,
    profil: str | None = None,
    residence: str | None = None,
    c: Ctx = Depends(ctx("clientele.export")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    contenu = await ClienteleIndicateursService(db, c).exporter_lignes(
        code, **_params_indicateurs(periode, date_debut, date_fin, agence, profil, residence))
    return _xlsx(contenu, f"indicateur-{code}.xlsx")


@router.get("/indicateurs/{code}/lignes.pdf")
async def exporter_lignes_indicateur_pdf(
    code: str,
    periode: str = Query("mois_courant"),
    date_debut: date | None = None,
    date_fin: date | None = None,
    agence: str | None = None,
    profil: str | None = None,
    residence: str | None = None,
    c: Ctx = Depends(ctx("clientele.export")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    contenu = await ClienteleIndicateursService(db, c).exporter_lignes_pdf(
        code, **_params_indicateurs(periode, date_debut, date_fin, agence, profil, residence))
    return _pdf(contenu, f"indicateur-{code}.pdf")


@router.get("/indicateurs/{code}")
async def detail_indicateur(
    code: str,
    periode: str = Query("mois_courant"),
    date_debut: date | None = None,
    date_fin: date | None = None,
    agence: str | None = None,
    profil: str | None = None,
    residence: str | None = None,
    page: int = 1,
    taille: int = 50,
    c: Ctx = Depends(ctx("clientele.reporting.view", "clientele.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleIndicateursService(db, c).detail(
        code, page=page, taille=taille,
        **_params_indicateurs(periode, date_debut, date_fin, agence, profil, residence))


@router.get("/bcm/grille")
async def grille_bcm(
    c: Ctx = Depends(ctx("clientele.bcm.view", "clientele.reporting.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).grille()


@router.get("/bcm/regles")
async def regles_bcm(
    registre: str = Query("BCM", pattern="^(BCM|SIC)$"),
    c: Ctx = Depends(ctx("clientele.bcm.view", "clientele.reporting.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleBcmReglesService(db, c).lister(registre)


# --------------------------------------------------------------------------- référentiels BCM
_REF_LIRE = ("clientele.bcm.view", "clientele.bcm.referentiel")


@router.get("/bcm/referentiel/versions")
async def ref_versions(c: Ctx = Depends(ctx(*_REF_LIRE)), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleBcmReferentielService(db, c).versions()


@router.post("/bcm/referentiel/versions", status_code=201)
async def ref_importer(
    fichier: UploadFile = File(...),
    libelle: str | None = Form(None),
    observations: str | None = Form(None),
    c: Ctx = Depends(ctx("clientele.bcm.referentiel")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    contenu = await fichier.read()
    return await ClienteleBcmReferentielService(db, c).importer(
        contenu, fichier.filename or "referentiel.xlsx", libelle, observations)


@router.get("/bcm/referentiel/comparer")
async def ref_comparer(a: uuid.UUID, b: uuid.UUID, c: Ctx = Depends(ctx(*_REF_LIRE)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleBcmReferentielService(db, c).comparer(a, b)


@router.get("/bcm/referentiel/codes")
async def ref_codes(
    version: uuid.UUID | None = None,
    q: str | None = None,
    usage: str | None = Query(None, pattern="^(PP|PM|AUTRE)$"),
    page: int = 1,
    taille: int = 100,
    c: Ctx = Depends(ctx(*_REF_LIRE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleBcmReferentielService(db, c).codes(version, q, usage, page, taille)


@router.post("/bcm/referentiel/versions/{vid}/activer")
async def ref_activer(vid: uuid.UUID, body: BcmRefActiverIn, c: Ctx = Depends(ctx("clientele.bcm.referentiel")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleBcmReferentielService(db, c).activer(vid, body.motif)


@router.delete("/bcm/referentiel/versions/{vid}", status_code=204)
async def ref_supprimer(vid: uuid.UUID, c: Ctx = Depends(ctx("clientele.bcm.referentiel")),
                        db: AsyncSession = Depends(get_db)) -> Response:
    await ClienteleBcmReferentielService(db, c).supprimer(vid)
    return Response(status_code=204)


@router.get("/bcm/referentiel/agences")
async def ref_agences(c: Ctx = Depends(ctx(*_REF_LIRE)), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleBcmReferentielService(db, c).agences()


@router.put("/bcm/referentiel/agences/{agence_id}")
async def ref_agence_definir(agence_id: uuid.UUID, body: SicAgenceIn,
                             c: Ctx = Depends(ctx("clientele.bcm.referentiel")),
                             db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleBcmReferentielService(db, c).definir_agence(agence_id, body.valeur, body.observation)


@router.delete("/bcm/referentiel/agences/{agence_id}")
async def ref_agence_retirer(agence_id: uuid.UUID, c: Ctx = Depends(ctx("clientele.bcm.referentiel")),
                             db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleBcmReferentielService(db, c).retirer_agence(agence_id)


@router.get("/bcm/referentiel/secteurs")
async def ref_secteurs(c: Ctx = Depends(ctx(*_REF_LIRE)), db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleBcmReferentielService(db, c).secteurs()


@router.put("/bcm/referentiel/secteurs")
async def ref_secteur_definir(body: SicSecteurIn, c: Ctx = Depends(ctx("clientele.bcm.referentiel")),
                              db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleBcmReferentielService(db, c).definir_secteur(
        body.libelle_orion, body.code_bcm, body.statut, body.observation)


@router.delete("/bcm/referentiel/secteurs")
async def ref_secteur_retirer(libelle: str = Query(..., max_length=160),
                              c: Ctx = Depends(ctx("clientele.bcm.referentiel")),
                              db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleBcmReferentielService(db, c).retirer_secteur(libelle)


@router.get("/bcm/referentiel/complements")
async def ref_complements(racine: str | None = None, page: int = 1, taille: int = 50,
                          c: Ctx = Depends(ctx(*_REF_LIRE)), db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleBcmReferentielService(db, c).complements(racine, page, taille)


@router.get("/bcm/referentiel/complements/modele.xlsx")
async def ref_complements_modele(c: Ctx = Depends(ctx(*_REF_LIRE))) -> Response:
    return _xlsx(ClienteleBcmReferentielService.modele_complements(), "modele-complements-sic.xlsx")


@router.post("/bcm/referentiel/complements/import")
async def ref_complements_import(
    fichier: UploadFile = File(...),
    appliquer: bool = Query(False),
    c: Ctx = Depends(ctx("clientele.bcm.referentiel")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    contenu = await fichier.read()
    return await ClienteleBcmReferentielService(db, c).importer_complements(
        contenu, fichier.filename or "complements.xlsx", appliquer)


@router.put("/bcm/referentiel/complements/{racine}")
async def ref_complement_definir(racine: str, body: SicComplementIn,
                                 c: Ctx = Depends(ctx("clientele.bcm.referentiel")),
                                 db: AsyncSession = Depends(get_db)) -> dict:
    valeurs = body.model_dump(exclude={"motif"})
    return await ClienteleBcmReferentielService(db, c).definir_complement(racine, valeurs, body.motif)


# --------------------------------------------------------------------------- déclarations SIC
@router.get("/declarations-historique")
async def historique_declarations(c: Ctx = Depends(ctx("clientele.bcm.view")),
                                  db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleSicService(db, c).historique()


@router.get("/sic")
async def sic_lister(type: str | None = Query(None, pattern="^(PP|PM)$"), statut: str | None = None,
                     c: Ctx = Depends(ctx("clientele.bcm.view")), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleSicService(db, c).lister(type, statut)


@router.post("/sic", status_code=201)
async def sic_creer(body: DeclarationSicCreerIn, c: Ctx = Depends(ctx("clientele.bcm.prepare")),
                    db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleSicService(db, c).creer(body.type, body.date_reference, body.date_debut)


@router.get("/sic/{did}")
async def sic_detail(did: uuid.UUID, c: Ctx = Depends(ctx("clientele.bcm.view")),
                     db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleSicService(db, c).detail(did)


@router.get("/sic/{did}/lignes")
async def sic_lignes(
    did: uuid.UUID,
    statut: str | None = Query(None, pattern="^(EXPORTEE|EXCLUE|INCOMPLETE|COMPLETE)$"),
    gravite: str | None = Query(None, pattern="^(BLOQUANTE|A_CORRIGER|AVERTISSEMENT|AUCUNE)$"),
    champ: str | None = Query(None, max_length=60),
    racine: str | None = Query(None, max_length=40),
    page: int = 1,
    taille: int = 50,
    c: Ctx = Depends(ctx("clientele.bcm.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleSicService(db, c).lignes(did, statut, gravite, champ, racine, page, taille)


@router.post("/sic/{did}/controler")
async def sic_controler(did: uuid.UUID, c: Ctx = Depends(ctx("clientele.bcm.prepare")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleSicService(db, c).controler(did)


@router.post("/sic/{did}/valider")
async def sic_valider(did: uuid.UUID, body: DeclarationSicValiderIn | None = None,
                      c: Ctx = Depends(ctx("clientele.bcm.valider")), db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleSicService(db, c).valider(did, body.commentaire if body else None)


@router.post("/sic/{did}/generer")
async def sic_generer(did: uuid.UUID, c: Ctx = Depends(ctx("clientele.bcm.prepare")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleSicService(db, c).generer(did)


@router.get("/sic/{did}/fichier.xlsx")
async def sic_fichier(did: uuid.UUID, c: Ctx = Depends(ctx("clientele.bcm.view")),
                      db: AsyncSession = Depends(get_db)) -> Response:
    contenu, nom = await ClienteleSicService(db, c).fichier(did)
    return _xlsx(contenu, nom)


@router.get("/sic/{did}/anomalies.xlsx")
async def sic_rapport(did: uuid.UUID, c: Ctx = Depends(ctx("clientele.bcm.view")),
                      db: AsyncSession = Depends(get_db)) -> Response:
    contenu, nom = await ClienteleSicService(db, c).rapport(did)
    return _xlsx(contenu, nom)


@router.post("/sic/{did}/depot")
async def sic_depot(did: uuid.UUID, body: DeclarationSicDepotIn, c: Ctx = Depends(ctx("clientele.sic.depot")),
                    db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleSicService(db, c).deposer(did, body.depot_le, body.resultat, body.commentaire)


@router.post("/bcm/regles/{code}")
async def decider_regle_bcm(
    code: str,
    body: BcmRegleDecisionIn,
    c: Ctx = Depends(ctx("clientele.bcm.valider")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleBcmReglesService(db, c).decider(code, body.model_dump())


@router.get("/declarations")
async def lister_declarations(
    annee: int | None = None,
    c: Ctx = Depends(ctx("clientele.bcm.view", "clientele.reporting.view")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await ClienteleDeclarationService(db, c).lister(annee=annee)


@router.post("/declarations", status_code=201)
async def creer_declaration(
    body: DeclarationBcmCreerIn,
    c: Ctx = Depends(ctx("clientele.bcm.prepare")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).creer(body.annee, body.mois)


@router.get("/declarations/{did}/export.xlsx")
async def exporter_declaration_xlsx(
    did: uuid.UUID,
    c: Ctx = Depends(ctx("clientele.export")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    contenu = await ClienteleDeclarationService(db, c).exporter_xlsx(did)
    return _xlsx(contenu, "declaration-bcm.xlsx")


@router.get("/declarations/{did}/export.pdf")
async def exporter_declaration_pdf(
    did: uuid.UUID,
    c: Ctx = Depends(ctx("clientele.export")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    contenu = await ClienteleDeclarationService(db, c).exporter_pdf(did)
    return _pdf(contenu, "declaration-bcm.pdf")


@router.get("/declarations/{did}/cellules/{code}")
async def drilldown_declaration(
    did: uuid.UUID,
    code: str,
    page: int = 1,
    taille: int = 50,
    racine: str | None = None,
    c: Ctx = Depends(ctx("clientele.bcm.view", "clientele.reporting.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).drilldown(did, code, page=page, taille=taille, racine=racine)


@router.get("/declarations/{did}")
async def detail_declaration(
    did: uuid.UUID,
    c: Ctx = Depends(ctx("clientele.bcm.view", "clientele.reporting.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).detail(did)


@router.post("/declarations/{did}/calculer")
async def calculer_declaration(
    did: uuid.UUID,
    c: Ctx = Depends(ctx("clientele.bcm.prepare")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).calculer(did)


@router.post("/declarations/{did}/controler")
async def controler_declaration(
    did: uuid.UUID,
    c: Ctx = Depends(ctx("clientele.bcm.prepare")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).controler(did)


@router.post("/declarations/{did}/valider")
async def valider_declaration(
    did: uuid.UUID,
    body: DeclarationBcmValiderIn | None = None,
    c: Ctx = Depends(ctx("clientele.bcm.valider")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).valider(
        did, commentaire=body.commentaire if body else None)


@router.post("/declarations/{did}/cloturer")
async def cloturer_declaration(
    did: uuid.UUID,
    c: Ctx = Depends(ctx("clientele.bcm.cloturer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).cloturer(did)


@router.post("/declarations/{did}/archiver")
async def archiver_declaration(
    did: uuid.UUID,
    c: Ctx = Depends(ctx("clientele.bcm.cloturer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).archiver(did)


@router.post("/declarations/{did}/desactiver")
async def desactiver_declaration(
    did: uuid.UUID,
    body: DeclarationBcmMotifIn,
    c: Ctx = Depends(ctx("clientele.bcm.prepare")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).desactiver(did, motif=body.motif)


@router.post("/declarations/{did}/reactiver")
async def reactiver_declaration(
    did: uuid.UUID,
    c: Ctx = Depends(ctx("clientele.bcm.prepare")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).reactiver(did)


@router.delete("/declarations/{did}", status_code=204)
async def supprimer_declaration(
    did: uuid.UUID,
    motif: str | None = Query(None, max_length=2000),
    c: Ctx = Depends(ctx("clientele.admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await ClienteleDeclarationService(db, c).supprimer(did, motif=motif)
    return Response(status_code=204)
