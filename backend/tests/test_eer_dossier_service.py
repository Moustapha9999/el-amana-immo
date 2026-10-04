"""Service EER sur PostgreSQL — cycle réel complet, BE, versions immuables, références.

Ignoré tant que les migrations eer_01…04 ne sont pas appliquées (base réelle intacte).
Exécution : copie de la base (bea_digital_eer_test), migrations + scripts/eer_init_referentiel.py.
Chaque test travaille dans une transaction annulée à la fin (sauf le compteur de références).
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models import Agence, AuditLog, EerAnomalie, EerHistorique, EerVersion, EerVisa, GedDocument, Role, User
from app.services import eer_controles_auto
from app.services.eer.constantes import RoleDossier, StatutElement
from app.services.eer.workflow import Etape, Statut
from app.services.eer_dossier_service import (
    Acteur,
    CibleComplement,
    EerAccesRefuse,
    EerConflit,
    EerDossierService,
    EerErreur,
    EerIntrouvable,
)
from app.services.plateforme_access_service import PlateformeAccessService

CHARGE = frozenset({"eer.view", "eer.create", "eer.update", "eer.submit", "eer.complement.receive"})
AGENT = frozenset({"eer.control", "eer.complement.request", "eer.complement.receive", "eer.scope.all"})
SUPERVISEUR = frozenset({"eer.assign", "eer.validate", "eer.avis", "eer.archive", "eer.scope.all"})


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        pret = await _tables(conn) and await conn.scalar(text("SELECT count(*) FROM eer_checklist_regles"))
    if not pret:
        await engine.dispose()
        pytest.skip("Tables EER absentes ou référentiel non chargé (migrations eer_* non appliquées)")
    session = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def _tables(conn) -> bool:
    return bool(await conn.scalar(text("SELECT to_regclass('public.eer_checklist_regles') IS NOT NULL")))


async def _acteurs(db: AsyncSession) -> tuple[Acteur, Acteur, Acteur]:
    """Chargé rattaché à la 1ʳᵉ agence ; l'agent détient réellement eer.control (rôle eer.analyste)."""
    users = list((await db.execute(select(User).where(User.is_active.is_(True), User.is_superuser.is_(False))
                                   .order_by(User.email).limit(3))).scalars())
    if len(users) < 3:
        pytest.skip("Trois utilisateurs actifs non superusers nécessaires")
    users[0].agence_id = (await _agence(db)).id
    await PlateformeAccessService(db).ensure_catalogue()
    analyste = await db.scalar(select(Role).where(Role.code == "eer.analyste"))
    await db.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r) ON CONFLICT DO NOTHING"),
                     {"u": users[1].id, "r": analyste.id})
    await db.flush()
    return Acteur(users[0], CHARGE), Acteur(users[1], AGENT), Acteur(users[2], SUPERVISEUR)


async def _agence(db: AsyncSession, rang: int = 0) -> Agence:
    agences = list((await db.execute(select(Agence).where(Agence.is_active.is_(True)).order_by(Agence.code)
                                     .limit(rang + 1))).scalars())
    if len(agences) <= rang:
        pytest.skip("Agences actives insuffisantes")
    return agences[rang]


def _valeur(chemin: str, user_id) -> object:
    feuille = chemin.rsplit(".", 1)[-1]
    if feuille in ("gestionnaire_id", "responsable_agence_id"):
        return str(user_id)
    if feuille.startswith("date"):
        return "2020-01-15"
    if feuille in ("ppe", "fatca_indice", "impact_rse"):
        return False
    return {
        "nombre_signataires": 1, "type_signature": "UNIQUE", "risque_lbcft": "FAIBLE",
        "tranche_mouvement": "PP_LT_50K", "salaire_net": 1000, "effectif": 3, "forme_mandat": "PROCURATION",
        "situation_matrimoniale": "Célibataire", "sexe": "M", "email": "contact@exemple.mr",
    }.get(feuille, "Renseigné")


async def _completer_fiches(svc: EerDossierService, acteur: Acteur, dossier_id) -> None:
    for _ in range(5):
        restants = [(cle, c) for cle, champs in (await svc.fiches(dossier_id)).items() for c in champs if c.bloquant]
        if not restants:
            return
        for cle, champ in restants:
            dp_id = uuid.UUID(cle.split(":", 1)[1]) if ":" in cle else None
            await svc.completer_champ(acteur, dossier_id, champ.chemin, _valeur(champ.chemin, acteur.user.id),
                                      dossier_partie_id=dp_id)
    raise AssertionError("Fiches toujours incomplètes")


def _items(d, code: str):
    return [i for i in d.items if i.regle_code == code]


@pytest.mark.asyncio
async def test_cycle_reel_pp_mandataire_ppe_non_conforme_complement_avis(db: AsyncSession):
    svc = EerDossierService(db)
    charge, agent, sup = await _acteurs(db)
    agence = await _agence(db)

    # 1. Le chargé crée le dossier : la checklist existe dès la création.
    d = await svc.creer_dossier(
        charge, agence_id=agence.id, type_client="PP", profil="SALARIE",
        client={"nom": "Client Test", "pp": {"prenom": "Test"}, "piece": {"type": "NNI", "numero": "T-EER-0001"}},
        client_role={"ppe": False, "fatca_indice": False},
        dossier={"risque_lbcft": "FAIBLE", "tranche_mouvement_code": "PP_LT_50K"})
    reference, dossier_id = d.reference, d.id
    assert reference.startswith("EER-") and d.statut == Statut.BROUILLON
    assert _items(d, "FICHE_CLIENT") and not _items(d, "AVIS_KYC") and d.avis_requis is False

    # 2. Mandataire PPE : éléments par mandataire + avis KYC, sans ressaisie du reste.
    mandataire = await svc.ajouter_partie(
        charge, dossier_id, "MANDATAIRE",
        {"nom": "Mandataire Test", "pp": {"prenom": "M"}, "piece": {"type": "NNI", "numero": "T-EER-0002"}},
        {"ppe": True, "forme_mandat": "PROCURATION"})
    d = await svc.charger(dossier_id)
    assert {i.regle_code for i in d.items if i.dossier_partie_id == mandataire.id} >= {
        "MANDATAIRE_FICHE", "MANDATAIRE_PIECE", "MANDAT_DOCUMENT", "MANDATAIRE_AVIS"}
    assert _items(d, "AVIS_KYC") and d.avis_requis and d.ppe_dossier
    with pytest.raises(EerErreur):
        await svc.ajouter_partie(charge, dossier_id, "GERANT", {"nom": "G"}, {"ppe": True})

    # 3. Soumission → A_AFFECTER, instantané v1.
    d = await svc.transition(charge, dossier_id, "SOUMIS")
    assert d.statut == Statut.A_AFFECTER

    # 4. Affectation : le créateur ne peut pas contrôler son propre dossier.
    with pytest.raises(EerAccesRefuse):
        await svc.transition(sup, dossier_id, "AFFECTE", analyste_id=charge.user.id)
    await svc.transition(sup, dossier_id, "AFFECTE", analyste_id=agent.user.id)
    with pytest.raises(EerAccesRefuse):
        await svc.transition(Acteur(sup.user, AGENT), dossier_id, "EN_CONTROLE")
    d = await svc.transition(agent, dossier_id, "EN_CONTROLE")
    assert d.etape == Etape.CHECKLIST

    # 5. Checklist : rien n'est validable tant que tout n'est pas pointé.
    with pytest.raises(EerErreur):
        await svc.valider_checklist(agent, dossier_id)
    for item in list(d.items):
        if item.statut == StatutElement.NON_APPLICABLE:
            continue
        presence = "ABSENT" if item.regle_code == "PIECE_IDENTITE" else "PRESENT"
        await svc.pointer(agent, item.id, presence)
    d = await svc.valider_checklist(agent, dossier_id)
    assert d.etape == Etape.FICHES

    # 6. Fiches pré-remplies : seul le manquant est saisi, puis étape contrôles.
    fiches = await svc.fiches(dossier_id)
    client_fiche = {c.chemin: c for c in fiches["FICHE_PP"]}
    assert client_fiche["client.nom"].valeur == "Client Test" and not client_fiche["client.nom"].bloquant
    assert client_fiche["client.pp.prenom_pere"].bloquant
    with pytest.raises(EerErreur):
        await svc.terminer_fiches(agent, dossier_id)
    await _completer_fiches(svc, agent, dossier_id)
    d = await svc.terminer_fiches(agent, dossier_id)
    assert d.etape == Etape.CONTROLES

    # 7. Contrôles : présence ≠ conformité ; la pièce manquante rend le dossier non conforme.
    d = await svc.charger(dossier_id)
    for item in d.items:
        if item.statut == StatutElement.NON_CONTROLE:
            await svc.controler(agent, item.id, True)
    decision = await svc.calculer_decision(agent, dossier_id)
    assert decision.resultat == "NON_CONFORME"
    assert any("PIECE_IDENTITE" in r for r in decision.explication)
    anomalies = await svc.ouvrir_anomalies(agent, dossier_id)
    assert [a.gravite for a in anomalies] == ["BLOQUANTE"]
    with pytest.raises(EerErreur, match="décision calculée"):
        await svc.transition(agent, dossier_id, "CONFORME")
    await svc.transition(agent, dossier_id, "NON_CONFORME")

    # 8. Complément sur le même dossier : seuls les éléments demandés sont déverrouillés.
    with pytest.raises(EerErreur):
        await svc.transition(agent, dossier_id, "A_COMPLETER")
    await svc.transition(agent, dossier_id, "A_COMPLETER", motif="Pièce d'identité absente",
                         cibles=CibleComplement(anomalie_ids=[anomalies[0].id]))
    with pytest.raises(EerErreur):
        await svc.completer_champ(agent, dossier_id, "client.adresse", "Autre adresse")
    with pytest.raises(EerErreur):
        await svc.transition(agent, dossier_id, "RESOUMIS")
    await svc.relancer(agent, dossier_id, "Relance téléphonique")
    piece = _items(await svc.charger(dossier_id), "PIECE_IDENTITE")[0]
    await svc.marquer_fourni(charge, dossier_id, piece.id)
    d = await svc.transition(agent, dossier_id, "RESOUMIS")
    assert (d.id, d.reference, d.version_courante, d.nb_relances) == (dossier_id, reference, 2, 1)
    assert d.etape == Etape.CHECKLIST  # reprise au point d'arrêt, pas depuis le début

    # 9. Reprise : seul l'élément demandé est re-pointé et re-contrôlé.
    await svc.transition(agent, dossier_id, "EN_CONTROLE")
    d = await svc.charger(dossier_id)
    a_repointer = [i for i in d.items if i.presence is None and i.statut != StatutElement.NON_APPLICABLE]
    assert [i.regle_code for i in a_repointer] == ["PIECE_IDENTITE"]
    await svc.pointer(agent, a_repointer[0].id, "PRESENT")
    await svc.valider_checklist(agent, dossier_id)
    await svc.terminer_fiches(agent, dossier_id)
    await svc.controler(agent, a_repointer[0].id, True)
    await svc.transition(agent, dossier_id, "CONFORME")

    # 10. Avis KYC obligatoire (PPE) et séparation contrôleur ≠ auteur de l'avis.
    with pytest.raises(EerErreur):
        await svc.transition(sup, dossier_id, "VALIDE")
    await svc.transition(agent, dossier_id, "AVIS_CONFORMITE")
    with pytest.raises(EerAccesRefuse):
        await svc.transition(Acteur(agent.user, SUPERVISEUR), dossier_id, "VALIDE", avis_favorable=True)
    d = await svc.transition(sup, dossier_id, "VALIDE", avis_favorable=True)
    assert d.statut == Statut.VALIDE and d.decision_globale == "CONFORME"

    visas = list((await db.execute(select(EerVisa).where(EerVisa.dossier_id == dossier_id))).scalars())
    assert [(v.avis, v.user_id) for v in visas] == [("FAVORABLE", sup.user.id)]
    statuts = {a.statut for a in (await db.execute(select(EerAnomalie).where(
        EerAnomalie.dossier_id == dossier_id))).scalars()}
    assert statuts == {"CLOSE"}
    versions = list((await db.execute(select(EerVersion).where(EerVersion.dossier_id == dossier_id)
                                      .order_by(EerVersion.cree_le))).scalars())
    assert [(v.numero, v.evenement) for v in versions] == [
        (1, "SOUMIS"), (1, "NON_CONFORME"), (1, "A_COMPLETER"), (2, "RESOUMIS"), (2, "CONFORME"),
        (2, "AVIS_CONFORMITE"), (2, "VALIDE")]
    assert all(len(v.empreinte) == 64 for v in versions)
    actions = [h.action for h in (await db.execute(select(EerHistorique).where(
        EerHistorique.dossier_id == dossier_id).order_by(EerHistorique.cree_le))).scalars()]
    assert {"CREATION", "CHECKLIST_REGENEREE", "CHECKLIST_VALIDEE", "RELANCE", "COMPLEMENT_RECU"} <= set(actions)
    audit = (await db.execute(select(AuditLog).where(AuditLog.entity_id == str(dossier_id)))).scalars().all()
    assert audit and all(a.module_code == "eer" for a in audit)
    # L'audit ne contient pas les données personnelles saisies.
    assert not any("Client Test" in str(a.after_data) for a in audit)

    # 11. Versions et historique immuables, même en SQL direct.
    for sql in ("UPDATE eer_versions SET empreinte = 'x' WHERE dossier_id = :d",
                "DELETE FROM eer_historique WHERE dossier_id = :d"):
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text(sql), {"d": dossier_id})


@pytest.mark.asyncio
async def test_pm_sarl_beneficiaires_effectifs_seuil_fige(db: AsyncSession):
    svc = EerDossierService(db)
    charge, *_ = await _acteurs(db)
    agence = await _agence(db)
    d = await svc.creer_dossier(charge, agence_id=agence.id, type_client="PM_PRIVEE", profil="SARL",
                                client={"nom": "Société X Test"})
    dossier_id, x = d.id, d.client_partie_id
    parts = {}
    for nom, nature in (("A", "MORALE"), ("B", "MORALE"), ("P1", "PHYSIQUE"), ("P2", "PHYSIQUE"),
                        ("P3", "PHYSIQUE")):
        dp = await svc.ajouter_partie(charge, dossier_id, "ACTIONNAIRE", {"nom": f"Actionnaire {nom}"},
                                      nature=nature)
        parts[nom] = dp.partie_id
    for detenteur, detenue, pct in (("A", None, 60), ("P3", None, 40), ("B", "A", 100), ("P1", "B", 70),
                                    ("P2", "B", 30)):
        await svc.ajouter_detention(charge, dossier_id, parts[detenteur], parts[detenue] if detenue else x,
                                    Decimal(pct))

    # Un changement du paramètre ne réécrit pas un dossier existant (seuil figé à la création).
    await db.execute(text("UPDATE eer_parametres SET valeur = '50' WHERE code = 'be.seuil_pourcentage'"))
    resultat = await svc.appliquer_beneficiaires(charge, dossier_id)
    assert resultat.seuil == Decimal(10) and resultat.complet
    assert {(b.partie_id, b.pourcentage) for b in resultat.beneficiaires} == {
        (str(parts["P1"]), Decimal("42.00")), (str(parts["P3"]), Decimal("40.00")),
        (str(parts["P2"]), Decimal("18.00"))}
    d = await svc.charger(dossier_id)
    be = [dp for dp in d.parties if dp.role == RoleDossier.BENEFICIAIRE_EFFECTIF]
    assert len(be) == 3 and all(dp.be_source == "CALCULE" for dp in be)
    assert len([i for i in d.items if i.regle_code == "BE_PIECE"]) == 3
    assert d.avis_requis  # toute PM : avis KYC


@pytest.mark.asyncio
async def test_regles_de_type_association_pm_publique_v1(db: AsyncSession):
    svc = EerDossierService(db)
    charge, *_ = await _acteurs(db)
    agence = await _agence(db)
    asso = await svc.creer_dossier(charge, agence_id=agence.id, type_client="ASSOCIATION", profil="ONG",
                                   client={"nom": "Association Test"}, dossier={"risque_lbcft": "FAIBLE"})
    assert asso.risque_lbcft == "ELEVE" and asso.avis_requis
    assert not [i for i in asso.items if i.regle_code in ("ACTIONNARIAT", "BE_IDENTIFIES")]
    with pytest.raises(EerErreur):
        await svc.ajouter_partie(charge, asso.id, "ACTIONNAIRE", {"nom": "X"}, nature="MORALE")
    with pytest.raises(EerErreur):
        await svc.creer_dossier(charge, agence_id=agence.id, type_client="PM_PUBLIQUE", profil="EPA",
                                client={"nom": "Etablissement Test"}, client_role={"ppe": True})
    with pytest.raises(EerErreur):
        await svc.creer_dossier(charge, agence_id=agence.id, type_client="PP", profil="SARL", client={"nom": "X"})
    with pytest.raises(EerErreur):
        await svc.creer_dossier(charge, agence_id=agence.id, type_client="PP", profil="SALARIE",
                                client={"nom": "X"}, operation_type="MISE_A_JOUR")
    with pytest.raises(EerAccesRefuse):
        await svc.creer_dossier(Acteur(charge.user, frozenset({"eer.view"})), agence_id=agence.id,
                                type_client="PP", profil="SALARIE", client={"nom": "X"})


@pytest.mark.asyncio
async def test_saisie_unique_partie_reutilisee_par_piece(db: AsyncSession):
    svc = EerDossierService(db)
    charge, *_ = await _acteurs(db)
    agence = await _agence(db)
    client = {"nom": "Personne Unique", "piece": {"type": "PASSEPORT", "numero": "T-EER-UNIQ"}}
    d1 = await svc.creer_dossier(charge, agence_id=agence.id, type_client="PP", profil="SALARIE", client=client)
    d2 = await svc.creer_dossier(charge, agence_id=agence.id, type_client="PP", profil="ETUDIANT", client=client)
    assert d1.client_partie_id == d2.client_partie_id and d1.reference != d2.reference


@pytest.mark.asyncio
async def test_revision_perimee_refusee_sans_ecrasement(db: AsyncSession):
    svc = EerDossierService(db)
    charge, *_ = await _acteurs(db)
    d = await svc.creer_dossier(charge, agence_id=(await _agence(db)).id, type_client="PP", profil="SALARIE",
                                client={"nom": "Concurrence Test"})
    assert d.revision == 0
    # Agent A et agent B partent de la révision 0 ; A modifie, B est refusé (409) au lieu d'écraser.
    await svc.verrouiller(charge, d.id, 0)
    await svc.completer_champ(charge, d.id, "dossier.origine_fonds", "Salaire")
    with pytest.raises(EerConflit) as exc:
        await svc.verrouiller(charge, d.id, 0)
    assert exc.value.status_code == 409 and exc.value.actuelle == 1
    await svc.verrouiller(charge, d.id, 1)
    assert (await svc.charger(d.id)).origine_fonds == "Salaire"


@pytest.mark.asyncio
async def test_perimetre_agence_charge(db: AsyncSession):
    svc = EerDossierService(db)
    charge, agent, _sup = await _acteurs(db)
    agence_a, agence_b = await _agence(db, 0), await _agence(db, 1)
    d_a = await svc.creer_dossier(charge, agence_id=agence_a.id, type_client="PP", profil="SALARIE",
                                  client={"nom": "Client agence A"})
    d_b = await svc.creer_dossier(Acteur(agent.user, AGENT | {"eer.create"}), agence_id=agence_b.id,
                                  type_client="PP", profil="SALARIE", client={"nom": "Client agence B"})
    assert charge.perimetre.couvre(agence_a.id) and not charge.perimetre.couvre(agence_b.id)
    await svc.charger(d_a.id, acteur=charge)
    with pytest.raises(EerIntrouvable):
        await svc.charger(d_b.id, acteur=charge)
    with pytest.raises(EerIntrouvable):
        await svc.completer_champ(charge, d_b.id, "dossier.origine_fonds", "X")
    with pytest.raises(EerAccesRefuse):
        await svc.creer_dossier(charge, agence_id=agence_b.id, type_client="PP", profil="SALARIE",
                                client={"nom": "Hors périmètre"})
    _sup.user.agence_id = None
    sans_agence = Acteur(_sup.user, CHARGE)
    assert sans_agence.perimetre.agences == []
    with pytest.raises(EerIntrouvable):
        await svc.charger(d_a.id, acteur=sans_agence)


@pytest.mark.asyncio
async def test_eer_admin_couvre_le_module_et_document_ged_etranger_refuse(db: AsyncSession):
    svc = EerDossierService(db)
    charge, agent, sup = await _acteurs(db)
    admin = Acteur(charge.user, frozenset({"eer.admin"}))
    assert admin.perimetre.peut("eer.submit") and admin.perimetre.toutes_agences
    d = await svc.creer_dossier(admin, agence_id=(await _agence(db)).id, type_client="PP", profil="SALARIE",
                                client={"nom": "Admin Test", "piece": {"type": "NNI", "numero": "T-EER-ADM",
                                                                       "date_expiration": "2001-01-01"}})
    d = await svc.transition(admin, d.id, "SOUMIS")
    assert d.statut == Statut.A_AFFECTER
    await svc.transition(sup, d.id, "AFFECTE", analyste_id=agent.user.id)
    d = await svc.transition(agent, d.id, "EN_CONTROLE")
    autre = GedDocument(espace_code="mg", module_code="contrats-echeances", entity="contrat",
                        entity_id=str(uuid.uuid4()), filename="x.pdf", stored_path="x/x.pdf", size_bytes=1)
    db.add(autre)
    await db.flush()
    item = _items(d, "PIECE_IDENTITE")[0]
    with pytest.raises(EerErreur, match="GED"):
        await svc.pointer(agent, item.id, "PRESENT", document_id=autre.id)

    constats = await eer_controles_auto.executer(svc, agent, d.id)
    par_code = {(c.code, c.resultat) for c in constats}
    assert ("PIECE_VALIDITE", "NON_CONFORME") in par_code  # pièce expirée en 2001
    assert any(c.code == "COHERENCE_IDENTITE" and c.resultat == "A_VERIFIER" for c in constats)
    # Proposition seulement : aucun statut d'élément n'a été modifié par les contrôles automatiques.
    d = await svc.charger(d.id)
    assert _items(d, "PIECE_VALIDITE")[0].statut == StatutElement.NON_CONTROLE
    # Le journal ne contient aucune donnée personnelle.
    assert not any("Admin Test" in str(c.detail) or "T-EER-ADM" in str(c.detail) for c in constats)


@pytest.mark.asyncio
async def test_references_concurrentes_sans_doublon():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        if not await _tables(conn):
            await engine.dispose()
            pytest.skip("Tables EER absentes")
    fabrique = async_sessionmaker(engine, expire_on_commit=False)

    async def une() -> str:
        async with fabrique() as s:
            ref = await EerDossierService(s).prochaine_reference(2099)
            await s.commit()
            return ref

    try:
        refs = await asyncio.gather(*(une() for _ in range(30)))
    finally:
        await engine.dispose()
    assert len(set(refs)) == 30
    numeros = sorted(int(r.rsplit("-", 1)[1]) for r in refs)
    assert numeros == list(range(numeros[0], numeros[0] + 30))
