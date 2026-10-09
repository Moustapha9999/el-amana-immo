"""API Référentiel clients — imports ORION, situation, rapprochement, classification, filtrage, indicateurs, déclaration BCM."""

from __future__ import annotations

import uuid
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import auth_http_error, get_current_user
from app.db.session import get_db
from app.models import Agence, User
from app.schemas.clientele import (
    AlerteDecisionIn,
    ClassifBacktestIn,
    ClassifEvaluerIn,
    ClassifExcelIn,
    ClassifManuelIn,
    ClassifMoteurIn,
    ClassifRegleIn,
    ClassifVersionIn,
    FiltrageEntreeIn,
    DeclarationBcmCreerIn,
    DeclarationBcmValiderIn,
    ImportConfirmIn,
    ImportMappingIn,
    LotClasserIn,
    LotMappingIn,
    RapprochementIn,
)
from app.services.clientele.lots import ClienteleLotService
from app.services.clientele.classification import ClienteleClassificationService
from app.services.clientele.declaration import ClienteleDeclarationService
from app.services.clientele.filtrage import ClienteleFiltrageService
from app.services.clientele.import_service import ClienteleImportService
from app.services.clientele.indicateurs import ClienteleIndicateursService
from app.services.clientele.rapprochement import ClienteleRapprochementService
from app.services.clientele.service import Ctx
from app.services.clientele.situation import ClienteleSituationService, SOURCES_COLONNES
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

router = APIRouter(prefix="/clientele", tags=["Référentiel clients"])

CAPACITES = {
    "voir": ("clientele.view",),
    "imports_voir": ("clientele.import.view", "clientele.import.execute"),
    "imports_executer": ("clientele.import.execute",),
    "rapprochement_voir": ("clientele.rapprochement.view",),
    "rapprochement_executer": ("clientele.rapprochement.execute",),
    "classif_voir": ("clientele.classif.view",),
    "classif_executer": ("clientele.classif.execute",),
    "classif_admin": ("clientele.classif.admin",),
    "filtrage_voir": ("clientele.filtrage.view",),
    "filtrage_executer": ("clientele.filtrage.execute",),
    "filtrage_decider": ("clientele.filtrage.decide",),
    "reporting_voir": ("clientele.reporting.view", "clientele.view"),
    "bcm_voir": ("clientele.bcm.view", "clientele.reporting.view"),
    "bcm_preparer": ("clientele.bcm.prepare",),
    "bcm_valider": ("clientele.bcm.valider",),
    "bcm_cloturer": ("clientele.bcm.cloturer",),
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


@router.post("/lots/analyse", status_code=201)
async def lot_analyser(fichier: UploadFile = File(...), type: str = Query("LISTE"),
                       c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    contenu = await fichier.read()
    return await ClienteleLotService(db, c).analyser(contenu, fichier.filename or "lot.xlsx", type_lot=type)


@router.get("/lots/{lid}")
async def lot_detail(lid: uuid.UUID, statut: str | None = None, page: int = 1,
                     c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute")),
                     db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleLotService(db, c).detail(lid, statut=statut, page=page)


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


@router.delete("/lots/{lid}", status_code=204)
async def lot_supprimer(lid: uuid.UUID,
                        c: Ctx = Depends(ctx("clientele.import.execute", "clientele.classif.execute")),
                        db: AsyncSession = Depends(get_db)) -> Response:
    await ClienteleLotService(db, c).supprimer(lid)
    return Response(status_code=204)


def _xlsx(contenu: bytes, nom: str) -> Response:
    return Response(content=contenu, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"{nom}\"; filename*=UTF-8''{quote(nom)}",
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
    page: int = 1, taille: int = 50,
    c: Ctx = Depends(ctx("clientele.classif.view")), db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleClassificationService(db, c).lister(
        niveau=niveau, source=source, q=q, page=page, taille=taille)


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


@router.get("/filtrage/listes")
async def filtrage_listes(c: Ctx = Depends(ctx("clientele.filtrage.view")),
                          db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await ClienteleFiltrageService(db, c).listes()


@router.get("/filtrage/listes/{lid}/entrees")
async def filtrage_entrees(lid: uuid.UUID, page: int = 1, taille: int = 50,
                           c: Ctx = Depends(ctx("clientele.filtrage.view")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    return await ClienteleFiltrageService(db, c).entrees(lid, page=page, taille=taille)


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
    page: int = 1, taille: int = 50,
    c: Ctx = Depends(ctx("clientele.filtrage.view")), db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleFiltrageService(db, c).lister(
        statut=statut, racine=racine, motif=motif, page=page, taille=taille)


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
    c: Ctx = Depends(ctx("clientele.bcm.view", "clientele.reporting.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ClienteleDeclarationService(db, c).drilldown(did, code, page=page, taille=taille)


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


@router.delete("/declarations/{did}", status_code=204)
async def supprimer_declaration(
    did: uuid.UUID,
    c: Ctx = Depends(ctx("clientele.admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await ClienteleDeclarationService(db, c).supprimer(did)
    return Response(status_code=204)
