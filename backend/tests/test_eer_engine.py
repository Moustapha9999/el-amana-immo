"""Cœur métier EER (Python pur, sans base) — checklist, fiches, BE, conformité, workflow."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.data.eer_referentiel import (
    CHAMPS_PAR_REGLE,
    FICHES,
    PARAMETRES_INITIAUX,
    REGLES_CHECKLIST_INITIALES,
    TYPES_CLIENT,
)
from app.services.eer import conditions
from app.services.eer.beneficiaires import Detention, calculer_beneficiaires, verifier_structure
from app.services.eer.checklist_engine import (
    Element,
    ErreurChecklist,
    Regle,
    appliquer_plan,
    controler,
    elements_non_pointes,
    generer,
    pointer,
    regenerer,
)
from app.services.eer.conformite_engine import Anomalie, decider, proposer_anomalies
from app.services.eer.constantes import (
    EtatChamp,
    GraviteAnomalie,
    Presence,
    ResultatAxe,
    Risque,
    RoleDossier,
    StatutAnomalie,
    StatutElement,
    TypeClient,
)
from app.services.eer.faits import PartieDossier, construire_faits
from app.services.eer.prefill import (
    ChampFiche,
    EtatEnregistre,
    champs_a_completer,
    confirmer,
    donnee_connue,
    ecrire,
    pre_remplir,
)
from app.services.eer.workflow import (
    Demande,
    Etape,
    EtatDossier,
    Statut,
    TransitionRefusee,
    avancer_etape,
    etape_reprise,
    peut_relancer,
    raisons_refus,
    verifier,
)

REGLES = [Regle.depuis_dict(r) for r in REGLES_CHECKLIST_INITIALES]
TOUTES = frozenset({
    "eer.submit", "eer.assign", "eer.control", "eer.complement.request", "eer.complement.receive",
    "eer.validate", "eer.avis", "eer.archive",
})


def _client(**faits) -> PartieDossier:
    return PartieDossier("C", RoleDossier.CLIENT, faits)


def _codes(attendus) -> set[str]:
    return {a.regle.code for a in attendus}


def _checklist(dossier: dict, parties: list[PartieDossier]):
    faits = construire_faits(dossier, parties)
    return faits, generer(REGLES, faits, parties)


# --- Conditions -------------------------------------------------------------------------

def test_conditions_operateurs_et_combinateurs():
    faits = {"type_client": "PP", "risque": "MOYEN", "nb": 3, "vide": ""}
    assert conditions.evaluer({"fact": "type_client", "op": "eq", "value": "PP"}, faits)
    assert conditions.evaluer({"fact": "nb", "op": "gte", "value": 3}, faits)
    assert not conditions.evaluer({"fact": "absent", "op": "ne", "value": "x"}, faits)
    assert conditions.evaluer({"fact": "vide", "op": "exists", "value": False}, faits)
    assert conditions.evaluer({"all": [
        {"fact": "type_client", "op": "in", "value": ["PP"]},
        {"not": {"fact": "risque", "op": "eq", "value": "FAIBLE"}},
    ]}, faits)
    assert conditions.evaluer(None, faits)


@pytest.mark.parametrize("invalide", [
    {"fact": "x", "op": "regex", "value": "."},
    {"fact": "x", "op": "in", "value": "PP"},
    {"all": []},
    {"all": [{"fact": "x", "op": "eq", "value": 1}], "fact": "y"},
    {"fact": "x", "op": "eq"},
    "__import__('os')",
])
def test_conditions_invalides_refusees(invalide):
    with pytest.raises(conditions.ConditionInvalide):
        conditions.valider(invalide)


def test_referentiel_regles_valides_et_sans_piece_par_profil():
    codes = [r.code for r in REGLES]
    assert len(codes) == len(set(codes))
    # Aucune règle ne conditionne une pièce sur le profil : liste non fournie, à paramétrer.
    for r in REGLES:
        assert "profil" not in str(r.condition)
    assert PARAMETRES_INITIAUX["be.seuil_pourcentage"] == 10


# --- Checklist dynamique ---------------------------------------------------------------

def test_pp_salarie_base():
    faits, attendus = _checklist(
        {"type_client": TypeClient.PP, "profil": "Salarié", "risque": Risque.FAIBLE},
        [_client(ppe=False, fatca_indice=False)],
    )
    codes = _codes(attendus)
    assert {"FICHE_CLIENT", "PIECE_IDENTITE", "PIECE_VALIDITE", "SPECIMEN_SIGNATURE", "CONTACT_URGENCE",
            "PPE_STATUT", "FATCA_STATUT", "LBCFT_RISQUE", "VISAS_BANQUE"} <= codes
    assert not codes & {"PPE_MOTIF", "PPE_CONTROLE_RENFORCE", "FATCA_REVUE_KYC", "AVIS_KYC",
                        "ACTIONNARIAT", "BE_IDENTIFIES", "MANDATAIRE_FICHE", "DIRECTION"}
    assert faits["avis_kyc_requis"] is False


def test_pp_ppe_declenche_motif_controle_et_avis():
    faits, attendus = _checklist({"type_client": TypeClient.PP, "risque": Risque.FAIBLE}, [_client(ppe=True)])
    assert {"PPE_MOTIF", "PPE_CONTROLE_RENFORCE", "AVIS_KYC"} <= _codes(attendus)
    avis = next(a for a in attendus if a.regle.code == "AVIS_KYC")
    assert "avis_kyc_requis eq True" in avis.explication


def test_pp_risque_moyen_avis_requis():
    faits, attendus = _checklist({"type_client": TypeClient.PP, "risque": Risque.MOYEN}, [_client()])
    assert "AVIS_KYC" in _codes(attendus)


def test_mandataire_elements_par_partie_et_ppe_mandataire():
    parties = [_client(ppe=False), PartieDossier("M1", RoleDossier.MANDATAIRE, {"ppe": True}),
               PartieDossier("M2", RoleDossier.MANDATAIRE, {"ppe": False})]
    faits, attendus = _checklist({"type_client": TypeClient.PP, "risque": Risque.FAIBLE}, parties)
    cles = {a.cle for a in attendus}
    for m in ("M1", "M2"):
        for code in ("MANDATAIRE_FICHE", "MANDATAIRE_PIECE", "MANDAT_DOCUMENT", "MANDATAIRE_AVIS"):
            assert (code, m) in cles
    # PPE du mandataire → contrôle renforcé + avis, mais pas le motif PPE du client.
    assert {"PPE_CONTROLE_RENFORCE", "AVIS_KYC"} <= _codes(attendus)
    assert "PPE_MOTIF" not in _codes(attendus)


def test_ppe_fatca_portes_uniquement_par_client_et_mandataire():
    parties = [_client(ppe=False), PartieDossier("BE1", RoleDossier.BENEFICIAIRE_EFFECTIF, {"ppe": True}),
               PartieDossier("G", RoleDossier.GERANT, {"fatca_indice": True})]
    faits = construire_faits({"type_client": TypeClient.PM_PRIVEE}, parties)
    assert faits["ppe"] is False and faits["fatca_indice"] is False


def test_pm_publique_actionnariat_be_avis_sans_ppe_fatca():
    faits, attendus = _checklist({"type_client": TypeClient.PM_PUBLIQUE, "risque": Risque.FAIBLE}, [_client()])
    codes = _codes(attendus)
    assert {"ACTIONNARIAT", "BE_IDENTIFIES", "AVIS_KYC", "DIRECTION"} <= codes
    assert not codes & {"PPE_STATUT", "FATCA_STATUT", "PIECE_IDENTITE"}


def test_association_risque_eleve_avis_sans_actionnariat():
    faits, attendus = _checklist({"type_client": TypeClient.ASSOCIATION, "risque": Risque.FAIBLE}, [_client()])
    assert faits["risque"] == Risque.ELEVE and faits["risque_declare"] == Risque.FAIBLE
    codes = _codes(attendus)
    assert "AVIS_KYC" in codes
    assert not codes & {"ACTIONNARIAT", "BE_IDENTIFIES"}
    assert TYPES_CLIENT[TypeClient.ASSOCIATION]["actionnariat"] is False


def test_regeneration_neutralise_sans_supprimer_puis_reactive():
    dossier = {"type_client": TypeClient.PP, "risque": Risque.FAIBLE}
    _, avant = _checklist(dossier, [_client(ppe=True)])
    elements = [Element.depuis_attendu(a) for a in avant]
    elements = [pointer(e, Presence.PRESENT) if e.regle_code == "PPE_MOTIF" else e for e in elements]

    _, apres = _checklist(dossier, [_client(ppe=False)])
    plan = regenerer(elements, apres)
    neutralises = {c[0] for c, _ in plan.a_neutraliser}
    assert {"PPE_MOTIF", "PPE_CONTROLE_RENFORCE", "AVIS_KYC"} <= neutralises
    elements = appliquer_plan(elements, plan)
    assert len(elements) == len(avant)
    ppe = next(e for e in elements if e.regle_code == "PPE_MOTIF")
    assert ppe.statut == StatutElement.NON_APPLICABLE and ppe.motif and ppe.neutralise_auto

    _, encore = _checklist(dossier, [_client(ppe=True)])
    plan2 = regenerer(elements, encore)
    assert ("PPE_MOTIF", None) in plan2.a_reactiver and not plan2.a_creer
    elements = appliquer_plan(elements, plan2)
    assert next(e for e in elements if e.regle_code == "PPE_MOTIF").statut == StatutElement.NON_CONTROLE


def test_regeneration_ne_reactive_pas_un_sans_objet_manuel():
    e = pointer(Element("X", None, "PHYSIQUE", "DOCUMENT", True), Presence.SANS_OBJET, "Déjà au dossier")
    regle = Regle("X", "X", "C", "PHYSIQUE", "DOCUMENT")
    plan = regenerer([e], generer([regle], {}, []))
    assert plan.inchanges == [("X", None)] and not plan.modifie


def test_presence_n_est_pas_conformite():
    e = Element("PIECE_IDENTITE", None, "PHYSIQUE", "DOCUMENT", True)
    present = pointer(e, Presence.PRESENT)
    assert present.statut == StatutElement.NON_CONTROLE
    non_conforme = controler(present, False, "Pièce expirée")
    assert non_conforme.presence == Presence.PRESENT and non_conforme.statut == StatutElement.NON_CONFORME
    with pytest.raises(ErreurChecklist):
        controler(present, False)
    with pytest.raises(ErreurChecklist):
        controler(pointer(e, Presence.ABSENT), True)
    with pytest.raises(ErreurChecklist):
        pointer(e, Presence.SANS_OBJET)
    assert elements_non_pointes([e, present]) == [("PIECE_IDENTITE", None)]


# --- Fiches pré-remplies ---------------------------------------------------------------

def _source_pp() -> dict:
    return {
        "dossier": {"operation_type": "ENTREE_RELATION", "date_eer": "2026-10-04", "agence_code": "00001",
                    "profil": "Salarié", "nombre_signataires": 1, "type_signature": "UNIQUE"},
        "client": {"nom": "X", "pp": {"prenom": "Y"}, "ppe": False, "piece": {"type": "NNI", "numero": "123"}},
    }


def test_fiches_pre_remplies_saisie_unique():
    source = _source_pp()
    faits = construire_faits({"type_client": TypeClient.PP}, [_client(ppe=False)])
    fiche = {c.chemin: c for c in pre_remplir(FICHES["FICHE_PP"], source, faits)}
    assert fiche["client.nom"].etat == EtatChamp.CONNU
    assert fiche["client.pp.prenom_pere"].etat == EtatChamp.MANQUANT
    assert fiche["client.ppe_motif"].etat == EtatChamp.NON_APPLICABLE
    assert fiche["dossier.racine_client"].etat == EtatChamp.NON_APPLICABLE  # compte pas encore ouvert
    assert fiche["client.telephone_2"].bloquant is False

    # Une valeur écrite une fois dans la source apparaît dans toutes les fiches qui la lisent.
    ecrire(source, "dossier.type_signature", "CONJOINTES")
    specimen = {c.chemin: c for c in pre_remplir(FICHES["SPECIMEN_SIGNATURE"], source, faits)}
    assert specimen["dossier.type_signature"].valeur == "CONJOINTES"


def test_fiches_origine_externe_a_confirmer_puis_confirme():
    source = _source_pp()
    faits = construire_faits({"type_client": TypeClient.PP}, [_client()])
    champs = pre_remplir(FICHES["FICHE_PP"], source, faits, origines={"client.nom": "VERSION_PRECEDENTE"})
    nom = next(c for c in champs if c.chemin == "client.nom")
    assert nom.etat == EtatChamp.A_CONFIRMER and nom in champs_a_completer(champs)

    etats = {"client.nom": confirmer(nom)}
    champs = pre_remplir(FICHES["FICHE_PP"], source, faits, origines={"client.nom": "VERSION_PRECEDENTE"},
                         etats=etats)
    assert next(c for c in champs if c.chemin == "client.nom").etat == EtatChamp.CONFIRME

    ecrire(source, "client.nom", "Z")  # valeur modifiée après confirmation : la confirmation tombe
    champs = pre_remplir(FICHES["FICHE_PP"], source, faits, etats=etats)
    assert next(c for c in champs if c.chemin == "client.nom").etat == EtatChamp.CONNU
    with pytest.raises(ValueError):
        confirmer(next(c for c in champs if c.chemin == "client.pp.prenom_pere"))
    assert isinstance(etats["client.nom"], EtatEnregistre)


def test_chaque_champ_de_fiche_a_une_colonne_source_unique():
    from app.services.eer_dossier_service import EerDossierService

    for code, fiche in FICHES.items():
        for champ in fiche["champs"]:
            modele, colonne = EerDossierService.colonne_chemin(champ["chemin"])
            if champ["chemin"] == "dossier.agence_code":
                continue  # lecture seule, dérivé de agences.code
            assert colonne in modele.__table__.columns, f"{code} : {champ['chemin']} → {modele.__name__}.{colonne}"


def test_fiche_pm_publique_sans_ppe_fatca():
    chemins = {c["chemin"] for c in FICHES["FICHE_PM_PUBLIQUE"]["champs"]}
    assert not {"client.ppe", "client.fatca_indice"} & chemins


# --- Actionnariat / bénéficiaires effectifs ---------------------------------------------

NATURES = {"X": "PM", "A": "PM", "B": "PM", "P1": "PP", "P2": "PP", "P3": "PP"}


def test_be_produit_des_pourcentages_42():
    detentions = [Detention("A", "X", Decimal(60)), Detention("P3", "X", Decimal(40)),
                  Detention("B", "A", Decimal(100)), Detention("P1", "B", Decimal(70)),
                  Detention("P2", "B", Decimal(30))]
    r = calculer_beneficiaires("X", detentions, NATURES, 10)
    pct = {b.partie_id: b.pourcentage for b in r.beneficiaires}
    assert pct == {"P1": Decimal("42.00"), "P3": Decimal("40.00"), "P2": Decimal("18.00")}
    assert r.complet
    r20 = calculer_beneficiaires("X", detentions, NATURES, 20)
    assert {b.partie_id for b in r20.beneficiaires} == {"P1", "P3"}


def test_be_cumul_de_plusieurs_chemins():
    detentions = [Detention("A", "X", Decimal(50)), Detention("P1", "X", Decimal(5)),
                  Detention("P1", "A", Decimal(10)), Detention("P2", "A", Decimal(90)),
                  Detention("P3", "X", Decimal(45))]
    r = calculer_beneficiaires("X", detentions, NATURES, 10)
    p1 = [b for b in r.beneficiaires if b.partie_id == "P1"]
    assert p1 and p1[0].pourcentage == Decimal("10.00") and len(p1[0].chemins) == 2


def test_be_pourcentage_inconnu_a_verifier():
    detentions = [Detention("A", "X", Decimal(60)), Detention("P1", "A", None),
                  Detention("P2", "X", Decimal(40))]
    r = calculer_beneficiaires("X", detentions, NATURES, 10)
    assert [b.partie_id for b in r.a_verifier] == ["P1"]
    assert not r.complet


def test_structure_cycle_total_et_pm_sans_actionnaires():
    detentions = [Detention("A", "X", Decimal(70)), Detention("B", "A", Decimal(100)),
                  Detention("A", "B", Decimal(10)), Detention("P1", "X", Decimal(40))]
    codes = {p.code for p in verifier_structure("X", detentions, NATURES)}
    assert {"CYCLE", "TOTAL_SUPERIEUR_100"} <= codes
    codes = {p.code for p in verifier_structure("X", [Detention("A", "X", Decimal(100))], NATURES)}
    assert "PM_SANS_ACTIONNAIRES" in codes
    assert {p.code for p in verifier_structure("X", [], NATURES)} == {"ACTIONNARIAT_ABSENT"}


# --- Moteur de conformité --------------------------------------------------------------

def _el(code, axe="PHYSIQUE", statut=StatutElement.CONFORME, obligatoire=True, **kw):
    return Element(code, None, axe, "DOCUMENT", obligatoire, statut=statut,
                   presence=Presence.PRESENT, **kw)


def test_conformite_conforme_incomplet_non_conforme():
    assert decider([_el("A"), _el("B", "SYSTEME")]).resultat == ResultatAxe.CONFORME
    d = decider([_el("A"), _el("B", "SYSTEME", StatutElement.NON_CONTROLE)])
    assert d.resultat == ResultatAxe.INCOMPLET and d.axes["SYSTEME"].resultat == ResultatAxe.INCOMPLET
    d = decider([_el("A", statut=StatutElement.MANQUANT), _el("B", "SYSTEME", StatutElement.NON_CONTROLE)])
    assert d.resultat == ResultatAxe.NON_CONFORME
    assert any("A : MANQUANT" in r for r in d.explication)
    # Élément facultatif ou dérogation acceptée : ne bloque pas.
    assert decider([_el("A"), _el("F", statut=StatutElement.MANQUANT, obligatoire=False)]).resultat \
        == ResultatAxe.CONFORME
    assert decider([_el("A", statut=StatutElement.NON_CONFORME, derogation_acceptee=True)]).resultat \
        == ResultatAxe.CONFORME


def test_conformite_anomalie_bloquante_et_propositions():
    anomalie = Anomalie("NIF", GraviteAnomalie.BLOQUANTE, StatutAnomalie.OUVERTE, libelle="NIF erroné")
    assert decider([_el("A")], [anomalie]).resultat == ResultatAxe.NON_CONFORME
    close = Anomalie("NIF", GraviteAnomalie.BLOQUANTE, StatutAnomalie.CORRIGEE)
    assert decider([_el("A")], [close]).resultat == ResultatAxe.CONFORME

    elements = [_el("A", statut=StatutElement.MANQUANT), _el("B", statut=StatutElement.NON_CONFORME, motif="x"),
                _el("C", statut=StatutElement.MANQUANT)]
    deja = [Anomalie("C", GraviteAnomalie.BLOQUANTE, StatutAnomalie.OUVERTE, element=("C", None))]
    propositions = proposer_anomalies(elements, deja)
    assert [p.element for p in propositions] == [("A", None), ("B", None)]


# --- Workflow --------------------------------------------------------------------------

def test_workflow_cycle_nominal_avec_avis():
    verifier(EtatDossier(Statut.BROUILLON, createur_id="charge"),
             Demande(Statut.SOUMIS, "charge", {"eer.submit"}))
    verifier(EtatDossier(Statut.A_AFFECTER, createur_id="charge"),
             Demande(Statut.AFFECTE, "sup", TOUTES, analyste_cible_id="agent"))
    etat = EtatDossier(Statut.EN_CONTROLE, createur_id="charge", analyste_id="agent", controleur_id="agent",
                       etape=Etape.CONTROLES, decision=ResultatAxe.CONFORME, avis_requis=True)
    verifier(etat, Demande(Statut.CONFORME, "agent", TOUTES))
    conforme = EtatDossier(Statut.CONFORME, createur_id="charge", controleur_id="agent", avis_requis=True)
    assert "Avis Conformité KYC obligatoire avant validation" in raisons_refus(
        conforme, Demande(Statut.VALIDE, "kyc", TOUTES))
    verifier(conforme, Demande(Statut.AVIS_CONFORMITE, "agent", TOUTES))
    avis = EtatDossier(Statut.AVIS_CONFORMITE, createur_id="charge", controleur_id="agent", avis_requis=True)
    verifier(avis, Demande(Statut.VALIDE, "kyc", TOUTES, avis_favorable=True))


def test_workflow_separation_des_roles():
    with pytest.raises(TransitionRefusee):
        verifier(EtatDossier(Statut.A_AFFECTER, createur_id="charge"),
                 Demande(Statut.AFFECTE, "sup", TOUTES, analyste_cible_id="charge"))
    avis = EtatDossier(Statut.AVIS_CONFORMITE, createur_id="charge", controleur_id="agent", avis_requis=True)
    with pytest.raises(TransitionRefusee):
        verifier(avis, Demande(Statut.VALIDE, "agent", TOUTES, avis_favorable=True))
    verifier(avis, Demande(Statut.VALIDE, "agent", TOUTES, avis_favorable=True, separation_roles=False))
    with pytest.raises(TransitionRefusee, match="eer.avis"):
        verifier(avis, Demande(Statut.VALIDE, "kyc", {"eer.control"}, avis_favorable=True))


def test_workflow_decision_et_etapes():
    base = dict(createur_id="c", analyste_id="a", controleur_id="a")
    incomplet = EtatDossier(Statut.EN_CONTROLE, etape=Etape.CONTROLES, decision=ResultatAxe.INCOMPLET, **base)
    assert raisons_refus(incomplet, Demande(Statut.CONFORME, "a", TOUTES))
    nc = EtatDossier(Statut.EN_CONTROLE, etape=Etape.CONTROLES, decision=ResultatAxe.NON_CONFORME, **base)
    assert raisons_refus(nc, Demande(Statut.CONFORME, "a", TOUTES))
    verifier(nc, Demande(Statut.NON_CONFORME, "a", TOUTES))
    trop_tot = EtatDossier(Statut.EN_CONTROLE, etape=Etape.FICHES, decision=ResultatAxe.CONFORME, **base)
    assert raisons_refus(trop_tot, Demande(Statut.CONFORME, "a", TOUTES))

    with pytest.raises(TransitionRefusee):
        avancer_etape(Etape.CHECKLIST, elements_non_pointes=2)
    assert avancer_etape(Etape.CHECKLIST) == Etape.CHECKLIST_VALIDEE
    with pytest.raises(TransitionRefusee):
        avancer_etape(Etape.FICHES, champs_bloquants=1)
    assert etape_reprise(checklist_modifiee=False, champs_bloquants=0) == Etape.CONTROLES
    assert etape_reprise(checklist_modifiee=False, champs_bloquants=3) == Etape.FICHES
    assert etape_reprise(checklist_modifiee=True, champs_bloquants=0) == Etape.CHECKLIST


def test_workflow_complement_relance_abandon_sans_rejet():
    assert "REJETE" not in Statut.__members__
    nc = EtatDossier(Statut.NON_CONFORME)
    assert raisons_refus(nc, Demande(Statut.A_COMPLETER, "a", TOUTES))
    verifier(nc, Demande(Statut.A_COMPLETER, "a", TOUTES, elements_cibles=2))
    a_completer = EtatDossier(Statut.A_COMPLETER, nb_relances=1)
    assert peut_relancer(a_completer, TOUTES) == []
    assert peut_relancer(EtatDossier(Statut.CONFORME), TOUTES)
    assert raisons_refus(a_completer, Demande(Statut.ABANDONNE, "sup", TOUTES))
    verifier(a_completer, Demande(Statut.ABANDONNE, "sup", TOUTES, motif="Complément non reçu"))
    # Brouillon créé à tort : abandon motivé par qui peut le modifier, jamais de suppression.
    brouillon = EtatDossier(Statut.BROUILLON)
    assert raisons_refus(brouillon, Demande(Statut.ABANDONNE, "c", {"eer.update"}))
    assert raisons_refus(brouillon, Demande(Statut.ABANDONNE, "c", {"eer.view"}, motif="Doublon"))
    verifier(brouillon, Demande(Statut.ABANDONNE, "c", {"eer.update"}, motif="Doublon"))
    for etat in (Statut.A_AFFECTER, Statut.EN_CONTROLE, Statut.VALIDE):
        assert raisons_refus(EtatDossier(etat), Demande(Statut.ABANDONNE, "sup", TOUTES, motif="x"))
    assert raisons_refus(a_completer, Demande(Statut.RESOUMIS, "a", TOUTES))
    verifier(a_completer, Demande(Statut.RESOUMIS, "a", TOUTES, elements_cibles_fournis=True))
    # Avis défavorable → complément sur le même dossier, motif obligatoire.
    avis = EtatDossier(Statut.AVIS_CONFORMITE, createur_id="c", controleur_id="a", avis_requis=True)
    assert raisons_refus(avis, Demande(Statut.A_COMPLETER, "kyc", TOUTES, avis_favorable=False))
    verifier(avis, Demande(Statut.A_COMPLETER, "kyc", TOUTES, avis_favorable=False, motif="BE non identifié",
                           elements_cibles=1))


def test_workflow_transitions_interdites_et_systeme():
    assert raisons_refus(EtatDossier(Statut.BROUILLON), Demande(Statut.VALIDE, "x", TOUTES))
    assert raisons_refus(EtatDossier(Statut.ABANDONNE), Demande(Statut.A_COMPLETER, "x", TOUTES))
    assert raisons_refus(EtatDossier(Statut.SOUMIS), Demande(Statut.A_AFFECTER, "x", TOUTES))
    verifier(EtatDossier(Statut.SOUMIS), Demande(Statut.A_AFFECTER, None, systeme=True))
    assert raisons_refus(EtatDossier(Statut.BROUILLON, champs_socle_manquants=("type_client",)),
                         Demande(Statut.SOUMIS, "c", {"eer.submit"}))


def test_champs_par_regle_pointent_des_regles_et_champs_existants():
    regles = {r["code"] for r in REGLES_CHECKLIST_INITIALES}
    chemins_client = {c["chemin"] for code in ("FICHE_PP", "FICHE_PM_PRIVEE", "FICHE_PM_PUBLIQUE",
                                               "FICHE_ASSOCIATION") for c in FICHES[code]["champs"]}
    chemins = {"CLIENT": chemins_client,
               "MANDATAIRE": {c["chemin"] for c in FICHES["FICHE_MANDATAIRE"]["champs"]},
               "SPECIMEN_SIGNATURE": {c["chemin"] for c in FICHES["SPECIMEN_SIGNATURE"]["champs"]}}
    for code, (fiche, liste) in CHAMPS_PAR_REGLE.items():
        assert code in regles, code
        assert liste == ("*",) or set(liste) <= chemins[fiche], (code, set(liste) - chemins[fiche])


def test_donnee_connue():
    def champ(chemin, etat, obligatoire=True):
        return ChampFiche(chemin, chemin, "S", obligatoire, None, etat)

    champs = [champ("a", EtatChamp.CONNU), champ("b", EtatChamp.MANQUANT), champ("c", EtatChamp.A_CONFIRMER),
              champ("d", EtatChamp.NON_APPLICABLE), champ("e", EtatChamp.MANQUANT, obligatoire=False)]
    assert donnee_connue(("a", "c"), champs) is True
    assert donnee_connue(("a", "b"), champs) is False
    assert donnee_connue(("d",), champs) is None
    assert donnee_connue(("inconnu",), champs) is None
    assert donnee_connue(("*",), champs) is False
    assert donnee_connue(("*",), [champs[0], champs[4]]) is True
