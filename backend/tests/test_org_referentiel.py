"""Référentiel organisationnel central (organigramme BEA, CORE ADMIN).

Les tests base tournent dans une transaction externe annulée à la fin : aucune donnée laissée.
Ignorés si la migration ``20261015_org_01`` n'est pas appliquée.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.data.organigramme_bea_2024 import ORGANIGRAMME, RATTACHEMENTS_AGENCES, SOURCE, aplatir
from app.data.plateforme_catalogue import CORE_ADMIN_PERMISSIONS, CORE_PERMISSIONS
from app.models import OrgAffectation, OrgEntite, ReclamationUnite, User
from app.services import org_referentiel as org
from app.services.reclamations import organisation as rc_org
from app.services.reclamations.acces import charger_scope


# ---------------------------------------------------------------------- sans base
def test_catalogue_permissions():
    assert "core.admin.organisation" in {p[0] for p in CORE_ADMIN_PERMISSIONS}
    assert "org.scope.all" in {p[0] for p in CORE_PERMISSIONS}


def test_donnees_organigramme_coherentes():
    lignes = list(aplatir(ORGANIGRAMME))
    codes = [ligne["code"] for ligne in lignes]
    assert len(codes) == len(set(codes)), "codes d'entité uniques"
    vus: set[str] = set()
    for ligne in lignes:
        assert ligne["parent_code"] is None or ligne["parent_code"] in vus, "parent avant enfant"
        vus.add(ligne["code"])
        for poste in ligne.get("postes", []):
            # Postes = fonctions, jamais des noms de personnes.
            assert "titulaire" not in poste
    # Les points ambigus de l'organigramme sont signalés, pas tranchés.
    a_confirmer = {ligne["code"] for ligne in lignes if ligne.get("a_confirmer")}
    assert {"DSI", "DCF"} <= a_confirmer
    assert set(RATTACHEMENTS_AGENCES.values()) <= set(codes)


def test_perimetre_sans_base():
    uid = uuid.uuid4()
    perso = org.PerimetreOrg(user_id=uid)
    assert perso.niveau == "PERSONNEL" and not perso.couvre_entite(uuid.uuid4())
    e = uuid.uuid4()
    elargi = org.PerimetreOrg(user_id=uid, entites=frozenset({e}))
    assert elargi.niveau == "ENTITES" and elargi.couvre_entite(e) and not elargi.couvre_entite(uuid.uuid4())
    assert org.PerimetreOrg(user_id=uid, global_=True).couvre_entite(uuid.uuid4())


# ---------------------------------------------------------------------- base
@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            pret = await conn.scalar(text("SELECT to_regclass('public.org_affectations') IS NOT NULL"))
    except Exception:
        pret = False
    if not pret:
        await engine.dispose()
        pytest.skip("Migration 20261015_org_01 non appliquée")
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


async def _user(db: AsyncSession) -> User:
    u = User(email=f"org-{uuid.uuid4().hex[:10]}@bea.test", full_name="Agent org test", hashed_password="x",
             is_active=True)
    db.add(u)
    await db.flush()
    return u


async def _par_code(db: AsyncSession, code: str) -> OrgEntite:
    e = await db.scalar(select(OrgEntite).where(OrgEntite.code == code, OrgEntite.deleted_at.is_(None)))
    assert e is not None, code
    return e


async def _entite(db: AsyncSession, admin: User, parent: OrgEntite | None, type_entite: str = "SERVICE",
                  libelle: str | None = None) -> dict:
    return await org.creer_entite(db, admin, {
        "libelle": libelle or f"Entité test {uuid.uuid4().hex[:8]}", "type_entite": type_entite,
        "parent_id": parent.id if parent else None,
    })


async def _attendre_erreur(db: AsyncSession, code: str, coro) -> None:
    with pytest.raises(AppError) as exc:
        async with db.begin_nested():
            await coro
    assert exc.value.code == code, exc.value.code


async def test_seed_organigramme(db: AsyncSession):
    lignes = list(aplatir(ORGANIGRAMME))
    n = await db.scalar(text("SELECT count(*) FROM departements WHERE source = :s AND deleted_at IS NULL"),
                        {"s": SOURCE})
    assert n == len(lignes)
    dg, dsi = await _par_code(db, "DG"), await _par_code(db, "DSI")
    assert dg.type_entite == "DIRECTION_GENERALE" and dsi.parent_id == dg.id
    assert dsi.a_confirmer and dsi.note_confirmation
    ca = await _par_code(db, "CA")
    assert ca.parent_id is None and ca.type_entite == "CONSEIL"
    # Aucun nom de personne : aucun poste importé n'a de titulaire.
    assert await db.scalar(text(
        "SELECT count(*) FROM org_postes WHERE source = :s AND titulaire_user_id IS NOT NULL"), {"s": SOURCE}) == 0
    for code_agence, code_entite in RATTACHEMENTS_AGENCES.items():
        lie = await db.scalar(text(
            "SELECT d.code FROM agences a JOIN departements d ON d.id = a.org_entite_id WHERE a.code = :c"),
            {"c": code_agence})
        assert lie in (None, code_entite)


async def test_crud_hierarchie_et_historique(db: AsyncSession):
    admin = await _user(db)
    dsi = await _par_code(db, "DSI")
    cree = await _entite(db, admin, dsi, "SERVICE", "Service Test Hiérarchie")
    eid = uuid.UUID(cree["id"])
    assert cree["code"].startswith("DSI") and cree["parent_id"] == str(dsi.id)
    e = await db.get(OrgEntite, eid)
    assert e.cle == "service test hierarchie"
    fiche = await org.fiche_entite(db, eid)
    assert fiche["entite"]["libelle"] == "Service Test Hiérarchie"
    assert [c["code"] for c in fiche["chemin"]][-2:] == ["DSI", cree["code"]]

    modif = await org.modifier_entite(db, admin, eid, {"libelle": "Service Test Renommé", "sigle": "STR"})
    assert modif["libelle"] == "Service Test Renommé" and modif["sigle"] == "STR"

    dcf = await _par_code(db, "DCF")
    deplace = await org.modifier_entite(db, admin, eid, {"parent_id": dcf.id})
    assert deplace["parent_id"] == str(dcf.id)
    assert eid in (await org.charger_arbre(db)).descendants(dcf.id)

    actions = (await db.scalars(text(
        "SELECT action FROM audit_logs WHERE entity_id = :id ORDER BY created_at"), {"id": str(eid)})).all()
    assert {"org.entite.create", "org.entite.update", "org.entite.move"} <= set(actions)
    hist = await org.historique(db, entite_id=eid)
    assert hist["total"] >= 3


async def test_cycle_interdit_service_et_base(db: AsyncSession):
    admin = await _user(db)
    dsi = await _par_code(db, "DSI")
    parent = await _entite(db, admin, dsi, "DEPARTEMENT")
    enfant = await _entite(db, admin, await db.get(OrgEntite, uuid.UUID(parent["id"])), "SERVICE")
    pid, cid = uuid.UUID(parent["id"]), uuid.UUID(enfant["id"])
    await _attendre_erreur(db, "HIERARCHIE_CIRCULAIRE", org.modifier_entite(db, admin, pid, {"parent_id": cid}))
    # Même écrit en SQL direct, le déclencheur refuse le cycle.
    with pytest.raises(Exception) as exc:
        async with db.begin_nested():
            await db.execute(text("UPDATE departements SET parent_id = :c WHERE id = :p"), {"c": cid, "p": pid})
    assert "ck_departements_sans_cycle" in str(exc.value) or "circulaire" in str(exc.value)


async def test_doublon_meme_niveau_interdit(db: AsyncSession):
    admin = await _user(db)
    dsi = await _par_code(db, "DSI")
    await _entite(db, admin, dsi, "SERVICE", "Service Doublon Test")
    await _attendre_erreur(db, "ENTITE_EXISTANTE", _entite(db, admin, dsi, "SERVICE", "SERVICE  doublon test"))
    # Même libellé sous un autre parent : autorisé (ex. « Service Commercial » DWA / DCOM).
    await _entite(db, admin, await _par_code(db, "DCF"), "SERVICE", "Service Doublon Test")


async def test_desactivation_conserve_les_donnees(db: AsyncSession):
    admin = await _user(db)
    dsi = await _par_code(db, "DSI")
    parent = await _entite(db, admin, dsi, "DEPARTEMENT")
    enfant = await _entite(db, admin, await db.get(OrgEntite, uuid.UUID(parent["id"])), "SERVICE")
    pid, cid = uuid.UUID(parent["id"]), uuid.UUID(enfant["id"])
    await db.execute(text(
        "INSERT INTO mg_notes_frais (id, reference, date_demande, departement, org_entite_id) "
        "VALUES (gen_random_uuid(), :r, current_date, 'Texte libre conservé', :e)"),
        {"r": f"NF-ORG-{uuid.uuid4().hex[:6]}", "e": cid})

    await _attendre_erreur(db, "SOUS_ENTITES_ACTIVES", org.changer_statut_entite(db, admin, pid, False))
    res = await org.changer_statut_entite(db, admin, cid, False, "Réorganisation")
    assert res["actif"] is False
    assert any(u["liaison"] == "mg_notes_frais" and u["nombre"] >= 1 for u in res["donnees_conservees"])
    lignes = await db.scalar(text(
        "SELECT count(*) FROM mg_notes_frais WHERE org_entite_id = :e AND departement = 'Texte libre conservé'"),
        {"e": cid})
    assert lignes == 1
    # Entité désactivée : plus de nouvelle affectation, réactivation possible.
    user = await _user(db)
    await _attendre_erreur(db, "ENTITE_INACTIVE", org.creer_affectation(db, admin, {"user_id": user.id,
                                                                                    "entite_id": cid}))
    assert (await org.changer_statut_entite(db, admin, cid, True))["actif"] is True


async def test_affectations_principale_et_secondaire(db: AsyncSession):
    admin, user = await _user(db), await _user(db)
    dsi, dcf = await _par_code(db, "DSI"), await _par_code(db, "DCF")
    a1 = await org.creer_affectation(db, admin, {"user_id": user.id, "entite_id": dsi.id,
                                                 "date_debut": date.today() - timedelta(days=30)})
    assert a1["type_affectation"] == "PRINCIPALE" and a1["perimetre"] == "PERSONNEL"
    await org.creer_affectation(db, admin, {"user_id": user.id, "entite_id": dcf.id,
                                            "type_affectation": "SECONDAIRE"})
    a2 = await org.creer_affectation(db, admin, {"user_id": user.id, "entite_id": dcf.id})
    lignes = await org.lister_affectations_utilisateur(db, user.id)
    principales = [a for a in lignes if a["type_affectation"] == "PRINCIPALE"]
    assert len(principales) == 2 and sum(a["actif"] for a in principales) == 1
    ancienne = next(a for a in principales if a["id"] == a1["id"])
    assert ancienne["actif"] is False and ancienne["date_fin"] == date.today().isoformat()
    await _attendre_erreur(db, "AFFECTATION_EXISTANTE", org.creer_affectation(
        db, admin, {"user_id": user.id, "entite_id": dcf.id, "type_affectation": "SECONDAIRE"}))
    close = await org.cloturer_affectation(db, admin, uuid.UUID(a2["id"]))
    assert close["actif"] is False
    # Poste d'une autre entité refusé.
    poste = await org.creer_poste(db, admin, dsi.id, {"intitule": "Poste test", "est_responsable": False})
    await _attendre_erreur(db, "POSTE_INVALIDE", org.creer_affectation(
        db, admin, {"user_id": user.id, "entite_id": dcf.id, "poste_id": uuid.UUID(poste["id"])}))


async def test_perimetre_jamais_automatique(db: AsyncSession):
    admin, user = await _user(db), await _user(db)
    dsi = await _par_code(db, "DSI")
    await org.creer_affectation(db, admin, {"user_id": user.id, "entite_id": dsi.id})
    p = await org.charger_perimetre(db, user, permissions=set())
    assert p.niveau == "PERSONNEL" and p.entite_principale_id == dsi.id and not p.couvre_entite(dsi.id)

    a = (await org.lister_affectations_utilisateur(db, user.id))[0]
    await org.modifier_affectation(db, admin, uuid.UUID(a["id"]), {"perimetre": "ENTITE"})
    p = await org.charger_perimetre(db, user, permissions=set())
    sous = [e for e in (await org.charger_arbre(db)).descendants(dsi.id) if e != dsi.id]
    assert p.couvre_entite(dsi.id) and sous and not p.couvre_entite(sous[0])

    await org.modifier_affectation(db, admin, uuid.UUID(a["id"]), {"perimetre": "ENTITE_ET_SOUS_ENTITES"})
    p = await org.charger_perimetre(db, user, permissions=set())
    assert all(p.couvre_entite(e) for e in sous)
    assert not p.couvre_entite((await _par_code(db, "DCF")).id)
    assert (await org.charger_perimetre(db, user, permissions={"org.scope.all"})).global_


async def test_declencheur_texte_libre_exact_seulement(db: AsyncSession):
    dg = await _par_code(db, "DG")
    ref = f"NF-ORG-{uuid.uuid4().hex[:6]}"
    await db.execute(text(
        "INSERT INTO mg_notes_frais (id, reference, date_demande, departement) VALUES "
        "(gen_random_uuid(), :r || '-1', current_date, '  direction   GÉNÉRALE '), "
        "(gen_random_uuid(), :r || '-2', current_date, 'Direction Generale Adjointe ?')"), {"r": ref})
    rows = dict((await db.execute(text(
        "SELECT reference, org_entite_id FROM mg_notes_frais WHERE reference LIKE :r || '%'"), {"r": ref})).all())
    assert rows[f"{ref}-1"] == dg.id
    assert rows[f"{ref}-2"] is None, "aucun rattachement deviné"


async def test_correspondance_appliquee_et_memorisee(db: AsyncSession):
    admin = await _user(db)
    mg = await _par_code(db, "DRES-RHMG-MG")
    ref = f"NF-ORG-{uuid.uuid4().hex[:6]}"
    valeur = f"Moyens gx {uuid.uuid4().hex[:4]}"
    await db.execute(text(
        "INSERT INTO mg_notes_frais (id, reference, date_demande, departement) "
        "VALUES (gen_random_uuid(), :r, current_date, :v)"), {"r": ref, "v": valeur})
    detail = await org.lister_correspondances(db, "mg_notes_frais")
    cle = next(v["cle"] for v in detail["valeurs"] if v["exemples"] and valeur in v["exemples"])
    res = await org.appliquer_correspondance(db, admin, "mg_notes_frais", cle, mg.id)
    assert res["lignes_rattachees"] == 1 and res["alias_ajoute"]
    texte, lie = (await db.execute(text(
        "SELECT departement, org_entite_id FROM mg_notes_frais WHERE reference = :r"), {"r": ref})).one()
    assert texte == valeur and lie == mg.id
    # Alias mémorisé : la prochaine saisie identique est rattachée automatiquement.
    await db.execute(text(
        "INSERT INTO mg_notes_frais (id, reference, date_demande, departement) "
        "VALUES (gen_random_uuid(), :r || 'b', current_date, :v)"), {"r": ref, "v": valeur.upper()})
    assert await db.scalar(text("SELECT org_entite_id FROM mg_notes_frais WHERE reference = :r || 'b'"),
                           {"r": ref}) == mg.id


async def test_controles_et_agences(db: AsyncSession):
    c = await org.controles(db)
    assert c["resume"]["a_confirmer"] >= 2
    assert {x["liaison"] for x in c["correspondances"]} >= {"mg_stock_mouvements", "mg_notes_frais"}
    agences = await org.lister_agences(db)
    assert agences


async def test_reclamations_filtre_et_perimetre_org(db: AsyncSession):
    admin, directeur = await _user(db), await _user(db)
    dsi = await _par_code(db, "DSI")
    service = await _entite(db, admin, dsi, "SERVICE")
    libelle = f"Unité RC org {uuid.uuid4().hex[:6]}"
    unite = ReclamationUnite(type_unite="SERVICE", libelle=libelle, cle=libelle.lower(),
                             org_entite_id=uuid.UUID(service["id"]))
    db.add(unite)
    await db.flush()

    ids, chemin = await rc_org.unites_de_entite(db, dsi.id)
    assert unite.id in ids and chemin
    ids_dcf, _ = await rc_org.unites_de_entite(db, (await _par_code(db, "DCF")).id)
    assert unite.id not in ids_dcf

    # Sans périmètre élargi : rien de plus que ses propres dossiers.
    await org.creer_affectation(db, admin, {"user_id": directeur.id, "entite_id": dsi.id})
    s = await charger_scope(db, directeur)
    assert unite.id not in s.unites_perimetre_org
    a = (await org.lister_affectations_utilisateur(db, directeur.id))[0]
    await org.modifier_affectation(db, admin, uuid.UUID(a["id"]), {"perimetre": "ENTITE_ET_SOUS_ENTITES"})
    s = await charger_scope(db, directeur)
    assert unite.id in s.unites_perimetre_org
    # Le périmètre n'est pas une appartenance : aucune action de service n'en découle.
    assert not s.membre_de(unite.id) and not s.responsable_de(unite.id)


async def test_affectation_unique_principale_en_base(db: AsyncSession):
    admin, user = await _user(db), await _user(db)
    dsi = await _par_code(db, "DSI")
    await org.creer_affectation(db, admin, {"user_id": user.id, "entite_id": dsi.id})
    with pytest.raises(Exception):
        async with db.begin_nested():
            db.add(OrgAffectation(user_id=user.id, entite_id=(await _par_code(db, "DCF")).id,
                                  type_affectation="PRINCIPALE", perimetre="PERSONNEL",
                                  date_debut=date.today(), actif=True))
            await db.flush()
