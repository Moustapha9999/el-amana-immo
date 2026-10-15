"""Import hebdomadaire simplifié : rapprochement, nouveaux clients, propositions, décisions, journal.

Base réelle, transaction toujours annulée (aucun commit) ; le fichier déposé est supprimé à la fin.
"""

from __future__ import annotations

import uuid
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import func, select, text

from app.core.exceptions import AppError
from app.services.clientele.lots import exclusion_groupe, identifiant, proposition, statut_decision

PERMS = {"clientele.view", "clientele.classif.view", "clientele.classif.execute", "clientele.import.execute"}
ENTETES = ["RACINE CLIENT", "NOM CLIENT", "NNI", "NIF", "DATE EER", "Classe risque LBC FT", "Analyste KYC"]


# --------------------------------------------------------------------------- unitaires
def _ligne(**kw):
    base = {"statut": "OK", "decision": None, "decision_detail": None, "classe_source": None,
            "classe_source_brut": None, "statut_moteur": None, "niveau_propose": None, "admissible": None,
            "motif_moteur": None, "donnees": {"NOM CLIENT": "X"}, "nom": "X", "anomalies": [],
            "source_actuelle": "MOTEUR", "classe_actuelle": "FAIBLE"}
    return {**base, **kw}


def test_proposition_fichier_prioritaire_moteur_affiche():
    p = proposition(_ligne(classe_source="ELEVE", classe_source_brut="Elevé", statut_moteur="EVALUE",
                           niveau_propose="FAIBLE", admissible=True))
    assert (p["etat"], p["niveau"], p["origine"], p["niveau_moteur"], p["ecart_moteur"]) == (
        "PROPOSE", "ELEVE", "FICHIER", "FAIBLE", True)


def test_proposition_moteur_si_classe_absente():
    p = proposition(_ligne(statut_moteur="EVALUE", niveau_propose="MOYEN", admissible=True))
    assert (p["etat"], p["niveau"], p["origine"]) == ("PROPOSE", "MOYEN", "MOTEUR")


@pytest.mark.parametrize(("kw", "etat", "categorie"), [
    ({"statut_moteur": "A_ARBITRER", "admissible": False}, "NON_CLASSIFIABLE", "CONFLIT_REGLES"),
    ({"statut_moteur": "NON_DISPONIBLE", "admissible": False}, "NON_CLASSIFIABLE", "DONNEES_MANQUANTES"),
    ({"classe_source_brut": "HAUT"}, "A_VERIFIER", "DONNEES_MANQUANTES"),
    ({"statut": "INVALIDE"}, "NON_CLASSIFIABLE", "IDENTIFICATION"),
    ({"statut": "AMBIGU", "decision_detail": {"identite": ["NNI déjà porté"]}}, "A_VERIFIER", "IDENTIFICATION"),
    ({}, "A_EVALUER", None),
])
def test_proposition_explicite(kw, etat, categorie):
    p = proposition(_ligne(**kw))
    assert (p["etat"], p["categorie"]) == (etat, categorie)
    assert p["raison"]


def test_contradiction_orion_a_verifier_niveau_conserve():
    p = proposition(_ligne(classe_source="MOYEN", decision_detail={"verification": ["NNI fichier 1 ≠ ORION 2"]}))
    assert (p["etat"], p["niveau"], p["categorie"]) == ("A_VERIFIER", "MOYEN", "DONNEES_CONTRADICTOIRES")


@pytest.mark.parametrize(("kw", "raison"), [
    ({"source_actuelle": "MANUEL"}, "classement manuel existant"),
    ({"classe_source": "INTERDIT"}, "niveau Interdit"),
    ({"classe_actuelle": "INTERDIT"}, "niveau Interdit"),
    ({"anomalies": ["PROFIL hors liste"]}, "anomalies à examiner"),
    ({"decision": "ACCEPTEE"}, "ligne déjà décidée"),
    ({"statut": "DOUBLON"}, "identification à vérifier"),
])
def test_exclusions_groupe(kw, raison):
    assert exclusion_groupe(_ligne(**{"classe_source": "FAIBLE", **kw})) == raison


def test_statut_decision_et_identifiant():
    assert statut_decision(_ligne()) == "EN_ATTENTE"
    assert statut_decision(_ligne(decision="ECRIT")) == "ANCIEN_CIRCUIT"
    assert statut_decision(_ligne(decision="REJETEE")) == "REJETEE"
    assert identifiant("1234567890.0") == "1234567890"
    assert identifiant(" 0012 ") == "0012"


# --------------------------------------------------------------------------- base (transaction annulée)
@pytest.fixture
async def db():
    from app.db.session import AsyncSessionLocal, engine

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


async def _jeu(db):
    from app.models import ClienteleClassification, ClienteleClient, User

    admin = await db.scalar(select(User).where(User.is_superuser.is_(True)).limit(1))
    if not admin:
        pytest.skip("Aucun administrateur")
    K, C = ClienteleClassification, ClienteleClient
    moteurs = (await db.execute(
        select(C.racine_client, C.raison_sociale, C.nni).join(K, K.racine_client == C.racine_client)
        .where(K.source == "MOTEUR", K.niveau.in_(("FAIBLE", "MOYEN")), K.niveau_propose.in_(("FAIBLE", "MOYEN")),
               C.nni.is_not(None)).order_by(C.racine_client).limit(3))).all()
    manuel = (await db.execute(
        select(C.racine_client, C.raison_sociale, K.niveau).join(K, K.racine_client == C.racine_client)
        .where(K.source == "MANUEL", K.niveau != "INTERDIT").limit(1))).first()
    if len(moteurs) < 3 or not manuel:
        pytest.skip("Base sans clients MOTEUR / MANUEL adaptés")
    pris = set((await db.scalars(select(C.racine_client).where(C.racine_client.like("99%")))).all())
    libres = [f"{n:06d}" for n in range(999_999, 990_000, -1) if f"{n:06d}" not in pris][:2]
    autre_niveau = next(n for n in ("FAIBLE", "MOYEN", "ELEVE") if n != manuel.niveau)
    a, b, c = moteurs
    rows = [
        [a.racine_client, a.raison_sociale, a.nni, None, "2020-01-15", "Faible", "Analyste Test"],   # 2
        [manuel.racine_client, manuel.raison_sociale, None, None, None, autre_niveau, "Analyste Test"],  # 3
        [libres[0], "NOUVEAU CLIENT HEBDO TEST", "7777777001", None, "2026-10-01", "Moyen", "Analyste Test"],  # 4
        [libres[1], "AUTRE NOUVEAU TEST", a.nni, None, None, "Faible", "Analyste Test"],  # 5 : NNI de a
        [a.racine_client, a.raison_sociale, None, None, None, "Moyen", "Analyste Test"],  # 6 : doublon
        [b.racine_client, b.raison_sociale, None, None, None, None, "Analyste Test"],  # 7 : sans classe
        [c.racine_client, c.raison_sociale, "1010101010", None, None, "Faible", "Analyste Test"],  # 8 : NNI ≠
    ]
    wb = Workbook()
    ws = wb.active
    ws.title = "CLIENTS"
    ws.append(ENTETES)
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    from app.services.clientele.service import Ctx

    user = SimpleNamespace(id=admin.id, is_superuser=False, full_name="Testeur hebdo", email="t@bea.mr")
    ctx = Ctx(user=user, permissions=set(PERMS))
    return ctx, buf.getvalue(), {"a": a, "b": b, "c": c, "manuel": manuel, "n1": libres[0], "n2": libres[1],
                                 "autre_niveau": autre_niveau}


@pytest.fixture
async def lot(db):
    from app.services.clientele.lots import ClienteleLotService

    ctx, contenu, jeu = await _jeu(db)
    svc = ClienteleLotService(db, ctx)
    r = await svc.analyser(contenu, "hebdo-test.xlsx", type_lot="LISTE")
    lid = uuid.UUID(r["id"])
    try:
        yield ctx, lid, jeu, {x["ligne"]: x for x in r["lignes"]}
    finally:
        p = svc._xlsx(lid)
        if p.exists():
            p.unlink()


def _svc(db, ctx):
    from app.services.clientele.hebdo import ClienteleDecisionLotService

    return ClienteleDecisionLotService(db, ctx)


async def _journal(db, lid, ligne=None):
    from app.models import ClienteleJournal as J

    q = select(J.type_action).where(J.lot_id == lid)
    if ligne:
        q = q.where(J.ligne_source == ligne)
    return list((await db.scalars(q)).all())


async def test_analyse_rapprochement_et_propositions(db, lot):
    _, lid, jeu, L = lot
    assert [L[n]["statut"] for n in range(2, 9)] == ["OK", "OK", "INCONNUE", "AMBIGU", "DOUBLON", "OK", "OK"]
    assert L[4]["statut_client"] == "NOUVEAU" and L[4]["proposition"]["etat"] == "PROPOSE"
    assert "déjà porté par la racine" in L[5]["proposition"]["raison"]
    assert L[6]["proposition"]["etat"] == "NON_CLASSIFIABLE"
    assert L[7]["proposition"]["etat"] == "A_EVALUER"
    assert L[8]["proposition"]["categorie"] == "DONNEES_CONTRADICTOIRES"
    assert L[3]["exclusion_groupe"] == "classement manuel existant"
    assert all(x["statut_decision"] == "EN_ATTENTE" for x in L.values())


async def test_accepter_nouveau_client_cree_hors_indicateurs(db, lot):
    from app.models import ClienteleClassification, ClienteleClient, ClienteleKyc, ClienteleSituation

    ctx, lid, jeu, _ = lot
    r = await _svc(db, ctx).decider(lid, {"lignes": [4], "decision": "ACCEPTER"})
    assert r["resultats"][0]["client_cree"] is True
    client = await db.scalar(select(ClienteleClient).where(ClienteleClient.racine_client == jeu["n1"]))
    assert client.source == "IMPORT_HEBDO" and client.nni == "7777777001"
    k = await db.get(ClienteleClassification, jeu["n1"])
    assert (k.niveau, k.source, k.analyste_kyc) == ("MOYEN", "MANUEL", "Analyste Test")
    assert (await db.get(ClienteleKyc, jeu["n1"])).date_eer.isoformat() == "2026-10-01"
    assert not await db.scalar(select(func.count()).select_from(ClienteleSituation)
                               .where(ClienteleSituation.racine_client == jeu["n1"]))
    assert {"CREATION", "PROPOSITION", "ACCEPTATION", "MAJ_DONNEES"} <= set(await _journal(db, lid, 4))


async def test_nouveau_client_sans_permission_import_refuse(db, lot):
    ctx, lid, _, _ = lot
    ctx.permissions.discard("clientele.import.execute")
    with pytest.raises(HTTPException) as e:
        await _svc(db, ctx).decider(lid, {"lignes": [4], "decision": "ACCEPTER"})
    assert e.value.status_code == 403


async def test_identite_ambigue_rejet_seul(db, lot):
    from app.models import ClienteleClient

    ctx, lid, jeu, _ = lot
    with pytest.raises(AppError) as e:
        await _svc(db, ctx).decider(lid, {"lignes": [5], "decision": "ACCEPTER"})
    assert e.value.code == "REJET_SEUL"
    r = await _svc(db, ctx).decider(lid, {"lignes": [5], "decision": "REJETER", "motif": "Homonymie NNI"})
    assert r["resultats"][0]["decision"] == "REJETEE"
    assert not await db.scalar(select(ClienteleClient.id).where(ClienteleClient.racine_client == jeu["n2"]))


async def test_rejet_ne_modifie_rien(db, lot):
    from app.models import ClienteleClassifHistorique, ClienteleClassification

    ctx, lid, jeu, _ = lot
    racine = jeu["a"].racine_client
    avant = (await db.get(ClienteleClassification, racine)).niveau
    nb = await db.scalar(select(func.count()).select_from(ClienteleClassifHistorique)
                         .where(ClienteleClassifHistorique.racine_client == racine))
    with pytest.raises(AppError):
        await _svc(db, ctx).decider(lid, {"lignes": [2], "decision": "REJETER"})
    await _svc(db, ctx).decider(lid, {"lignes": [2], "decision": "REJETER", "motif": "Classe à revoir"})
    await db.refresh(await db.get(ClienteleClassification, racine))
    assert (await db.get(ClienteleClassification, racine)).niveau == avant
    assert await db.scalar(select(func.count()).select_from(ClienteleClassifHistorique)
                           .where(ClienteleClassifHistorique.racine_client == racine)) == nb
    assert sorted(await _journal(db, lid, 2)) == ["PROPOSITION", "REJET"]
    with pytest.raises(AppError) as e:
        await _svc(db, ctx).decider(lid, {"lignes": [2], "decision": "ACCEPTER"})
    assert e.value.code == "DEJA_DECIDE"


async def test_classement_manuel_jamais_remplace_sans_motif(db, lot):
    from app.models import ClienteleClassification

    ctx, lid, jeu, _ = lot
    with pytest.raises(AppError) as e:
        await _svc(db, ctx).decider(lid, {"lignes": [2, 3], "decision": "ACCEPTER", "motif": "Lot"})
    assert e.value.code == "EXCLUES_DU_GROUPE" and "classement manuel existant" in e.value.message
    with pytest.raises(AppError) as e:
        await _svc(db, ctx).decider(lid, {"lignes": [3], "decision": "ACCEPTER"})
    assert e.value.code == "MOTIF_OBLIGATOIRE"
    racine = jeu["manuel"].racine_client
    assert (await db.get(ClienteleClassification, racine)).niveau == jeu["manuel"].niveau


async def test_donnees_incompletes_modifier_avec_motif(db, lot):
    from app.models import ClienteleClassification

    ctx, lid, jeu, _ = lot
    with pytest.raises(AppError) as e:
        await _svc(db, ctx).decider(lid, {"lignes": [7], "decision": "ACCEPTER"})
    assert e.value.code == "SANS_PROPOSITION"
    with pytest.raises(AppError):
        await _svc(db, ctx).decider(lid, {"lignes": [7], "decision": "MODIFIER", "niveau": "ELEVE"})
    await _svc(db, ctx).decider(lid, {"lignes": [7], "decision": "MODIFIER", "niveau": "ELEVE",
                                      "motif": "Revue KYC"})
    k = await db.get(ClienteleClassification, jeu["b"].racine_client)
    assert (k.niveau, k.source) == ("ELEVE", "MANUEL")
    assert "MODIFICATION" in await _journal(db, lid, 7)


async def test_decision_groupee_tracee_ligne_par_ligne(db, lot):
    from app.models import ClienteleJournal as J

    ctx, lid, _, _ = lot
    with pytest.raises(AppError) as e:
        await _svc(db, ctx).decider(lid, {"lignes": [2, 4], "decision": "ACCEPTER"})
    assert e.value.code == "MOTIF_OBLIGATOIRE"
    with pytest.raises(AppError) as e:
        await _svc(db, ctx).decider(lid, {"lignes": list(range(2, 203)), "decision": "ACCEPTER", "motif": "x"})
    assert e.value.code == "GROUPE_TROP_GRAND"
    r = await _svc(db, ctx).decider(lid, {"lignes": [2, 4], "decision": "ACCEPTER", "motif": "Revue hebdo"})
    gid = uuid.UUID(r["groupe_id"])
    lignes = (await db.scalars(select(J.ligne_source).where(J.groupe_id == gid, J.type_action == "ACCEPTATION")))
    assert sorted(lignes.all()) == [2, 4]
    bilan = await _svc(db, ctx).bilan(lid)
    assert bilan["decisions"]["ACCEPTEE"] == 2 and bilan["groupes"] == 1 and bilan["clients_crees"] == 1
    contenu, _ = await _svc(db, ctx).bilan_xlsx(lid)
    assert contenu[:2] == b"PK"


async def test_sans_permission_execute_refuse(db, lot):
    ctx, lid, _, _ = lot
    ctx.permissions.discard("clientele.classif.execute")
    with pytest.raises(HTTPException) as e:
        await _svc(db, ctx).decider(lid, {"lignes": [2], "decision": "REJETER", "motif": "x"})
    assert e.value.status_code == 403


async def test_lot_decide_non_supprimable_fichier_conserve(db, lot):
    from app.services.clientele.lots import ClienteleLotService

    ctx, lid, _, _ = lot
    await _svc(db, ctx).decider(lid, {"lignes": [6], "decision": "REJETER", "motif": "Doublon"})
    svc = ClienteleLotService(db, ctx)
    with pytest.raises(AppError) as e:
        await svc.supprimer(lid, motif="test")
    assert e.value.code == "LOT_DECIDE"
    await svc.fermer(lid)
    contenu, _ = await svc.fichier(lid)
    assert contenu[:2] == b"PK"


async def test_historique_et_journal_proteges(db):
    from app.models import ClienteleClassifHistorique

    h = await db.scalar(select(ClienteleClassifHistorique.id).limit(1))
    if not h:
        pytest.skip("Historique vide")
    for sql in (f"DELETE FROM clientele_classif_historique WHERE id = '{h}'",
                "UPDATE clientele_classif_historique SET nouvelle_classe = CASE WHEN nouvelle_classe = 'FAIBLE' "
                f"THEN 'MOYEN' ELSE 'FAIBLE' END WHERE id = '{h}'"):
        sp = await db.begin_nested()
        with pytest.raises(Exception, match="historique"):
            await db.execute(text(sql))
        await sp.rollback()
    sp = await db.begin_nested()
    await db.execute(text(
        "INSERT INTO clientele_journal (id, racine_client, type_action, origine) "
        "VALUES ('00000000-0000-0000-0000-00000000abcd', '000000', 'VERIFICATION', 'SAISIE')"))
    with pytest.raises(Exception, match="journal"):
        await db.execute(text("DELETE FROM clientele_journal WHERE id = '00000000-0000-0000-0000-00000000abcd'"))
    await sp.rollback()


async def test_modification_individuelle_exige_analyste(db, lot):
    from app.services.clientele.classification import ClienteleClassificationService

    ctx, _, jeu, _ = lot
    svc = ClienteleClassificationService(db, ctx)
    racine = jeu["c"].racine_client
    with pytest.raises(AppError) as e:
        await svc.modifier_individuel(racine, {"niveau": "ELEVE", "motif_classement": "Revue"})
    assert e.value.code == "ANALYSTE_OBLIGATOIRE"
    r = await svc.modifier_individuel(racine, {"niveau": "ELEVE", "motif_classement": "Revue",
                                               "analyste_kyc": "Analyste Test"})
    assert r["classification"]["niveau"] == "ELEVE" if "classification" in r else r["niveau"] == "ELEVE"
    res = await svc.rechercher(racine)
    assert res["items"][0]["racine_client"] == racine
