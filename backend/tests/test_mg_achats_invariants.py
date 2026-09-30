"""Invariants du circuit Achat → Réception → Facture → Paiement (sans DB)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.mg_achats import (
    FactureCreate,
    FactureLigneIn,
    PaiementCreate,
    PaiementUpdate,
    ReceptionCreate,
    ReceptionLigneIn,
)
from app.schemas.mg_ops import BcLigneIn, BonUpdate
from app.services import mg_achats_regles as R
from app.services.mg_achats_service import MgAchatsService

D = Decimal


def _user():
    u = MagicMock()
    u.id = uuid4()
    u.full_name = "Test"
    return u


def _ligne(desc="Chaise", q=10, recu=0, pu=100, tva=0, remise=0):
    return SimpleNamespace(
        id=uuid4(),
        description=desc,
        quantite=D(q),
        quantite_recue=D(recu),
        prix_unitaire=D(pu),
        remise_pct=D(remise),
        taux_tva=D(tva),
        uom="U",
        stockable=False,
        article_id=None,
        sort_order=0,
        code_produit=None,
        departement=None,
    )


def _bon(statut="VALIDE", lignes=None, **kw):
    b = SimpleNamespace(
        id=uuid4(),
        reference="BEA-1",
        statut=statut,
        lignes=lignes or [],
        total_ht=D("0"),
        total_tva=D("0"),
        total_ttc=D("0"),
        envoye_at=None,
        agence_livraison_id=None,
        fournisseur_id=uuid4(),
        fournisseur_raison_sociale="FRS",
        conditions_paiement=None,
        devise="MRU",
        date_bc=date(2026, 9, 1),
        observation=None,
        adresse_livraison=None,
    )
    for k, v in kw.items():
        setattr(b, k, v)
    return b


def _fl(bc, q, pu, tva=0):
    return SimpleNamespace(
        bc_ligne_id=bc.id, designation=bc.description, quantite=D(q), prix_unitaire=D(pu), taux_tva=D(tva)
    )


def _db():
    db = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


# --- TVA : même règle partout ---


def test_tva_arrondie_par_ligne_et_totaux_sommes_des_lignes():
    m = R.calculer_ligne(3, D("33.33"), 0, 16)
    assert (m.ht, m.tva, m.ttc) == (D("99.99"), D("16.00"), D("115.99"))
    m2 = R.calculer_ligne(1, D("0.05"), 0, 16)
    assert m2.tva == D("0.01")  # 0,008 → 0,01 (ROUND_HALF_UP)
    tot = R.totaliser([m, m2])
    assert tot.tva == m.tva + m2.tva
    assert tot.ttc == tot.ht + tot.tva


def test_remise_puis_tva():
    m = R.calculer_ligne(2, 1000, 10, 16)
    assert (m.ht, m.tva, m.ttc) == (D("1800.00"), D("288.00"), D("2088.00"))


def test_tva_zero_autorisee():
    assert R.calculer_ligne(5, 200, 0, 0).tva == D("0.00")


# --- Facturation partielle ---


def test_facturation_partielle_successive_conforme():
    """10 chaises : 5 reçues → 5 facturées (conforme), puis 5 reçues → 5 facturées (conforme)."""
    lg = _ligne(q=10, recu=5)
    r1 = R.rapprocher_facture([lg], [_fl(lg, 5, 100)], {}, D("500"))
    assert r1.resultat == "CONFORME", r1.details
    lg.quantite_recue = D(10)
    r2 = R.rapprocher_facture([lg], [_fl(lg, 5, 100)], {lg.id: D(5)}, D("500"))
    assert r2.resultat == "CONFORME", r2.details
    assert r2.attendu_ttc == D("500.00")


def test_facture_au_dela_du_recu_non_facture_en_anomalie():
    lg = _ligne(q=10, recu=5)
    r = R.rapprocher_facture([lg], [_fl(lg, 5, 100)], {lg.id: D(5)}, D("500"))
    assert r.ecart_quantite is True


# --- Quantités ligne par ligne ---


def test_compensation_entre_lignes_detectee():
    """A reçu 3 / facturé 5, B reçu 5 / facturé 3 : totaux égaux mais anomalie."""
    a = _ligne("A", q=5, recu=3)
    b = _ligne("B", q=5, recu=5)
    r = R.rapprocher_facture([a, b], [_fl(a, 5, 100), _fl(b, 3, 100)], {}, D("800"))
    assert r.ecart_quantite is True
    assert [e.ok for e in r.lignes] == [False, True]


def test_ligne_facturee_en_deux_morceaux_agregee():
    a = _ligne("A", q=5, recu=3)
    r = R.rapprocher_facture([a], [_fl(a, 2, 100), _fl(a, 2, 100)], {}, D("400"))
    assert r.ecart_quantite is True


def test_ligne_hors_bc_en_anomalie():
    a = _ligne("A", q=5, recu=5)
    hors = SimpleNamespace(bc_ligne_id=None, designation="Divers", quantite=D(1), prix_unitaire=D(10), taux_tva=D(0))
    r = R.rapprocher_facture([a], [hors], {}, D("10"))
    assert r.ecart_quantite is True


def test_prix_et_tva_differents_du_bc():
    a = _ligne("A", q=5, recu=5, pu=100, tva=16)
    r = R.rapprocher_facture([a], [_fl(a, 5, 110, 16)], {}, D("638"))
    assert r.ecart_montant is True
    r2 = R.rapprocher_facture([a], [_fl(a, 5, 100, 0)], {}, D("500"))
    assert r2.ecart_montant is True


def test_plafond_commande_refus_dur():
    a = _ligne("A", q=10, recu=10)
    with pytest.raises(HTTPException) as exc:
        R.verifier_plafond_commande([a], {a.id: D(4)}, {a.id: D(7)})
    assert "reste à facturer 3" in exc.value.detail


def test_association_par_id_puis_designation():
    a = _ligne("Chaise bureau")
    assert R.associer_ligne_bc([a], None, "  chaise   BUREAU ") is a
    with pytest.raises(HTTPException):
        R.associer_ligne_bc([a], uuid4(), "x")


# --- Paiements ---


def test_message_plafond_paiement():
    with pytest.raises(HTTPException) as exc:
        R.verifier_montant_paiement(D("40000"), D("100000"), D("70000"))
    assert exc.value.detail == "Le montant du paiement (40 000) dépasse le reste à payer (30 000)."


def test_statut_paiement_facture():
    assert R.statut_paiement_facture(1000, 0) == "A_PAYER"
    assert R.statut_paiement_facture(1000, 400) == "PARTIELLEMENT_PAYEE"
    assert R.statut_paiement_facture(1000, 1000) == "PAYEE"


def _svc_paiement(facture, engage, bon=None):
    db = _db()
    db.refresh = AsyncMock()
    db.get = AsyncMock(return_value=bon)
    svc = MgAchatsService(db)
    svc._facture_pour_paiement = AsyncMock(return_value=facture)
    svc._montant_engage = AsyncMock(return_value=D(engage))
    svc._next_ref = AsyncMock(return_value="PAY-1")
    svc._append_event = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_paiements_successifs_puis_depassement():
    facture = SimpleNamespace(
        id=uuid4(), reference="FAC-1", statut="A_PAYER", montant_ttc=D("100000"),
        montant_paye=D("0"), fournisseur_id=uuid4(), date_echeance=None, bon_id=uuid4(),
    )
    paye = {"v": D("0")}

    async def _recalc(f):
        f.montant_paye = paye["v"]
        f.statut = R.statut_paiement_facture(f.montant_ttc, f.montant_paye)

    svc = _svc_paiement(facture, 0)
    svc.recalculate_invoice_payment = AsyncMock(side_effect=_recalc)
    paye["v"] = D("70000")
    await svc.create_paiement(
        PaiementCreate(facture_id=facture.id, montant=D("70000"), date_paiement=date(2026, 9, 30)), _user()
    )
    assert facture.statut == "PARTIELLEMENT_PAYEE"

    svc._montant_engage = AsyncMock(return_value=D("70000"))
    with pytest.raises(HTTPException) as exc:
        await svc.create_paiement(PaiementCreate(facture_id=facture.id, montant=D("40000")), _user())
    assert "dépasse le reste à payer (30 000)" in exc.value.detail

    paye["v"] = D("100000")
    await svc.create_paiement(
        PaiementCreate(facture_id=facture.id, montant=D("30000"), date_paiement=date(2026, 9, 30)), _user()
    )
    assert facture.statut == "PAYEE"


@pytest.mark.asyncio
async def test_paiement_reprend_moyen_et_reference_du_bc():
    facture = SimpleNamespace(
        id=uuid4(), reference="FAC-1", statut="A_PAYER", montant_ttc=D("1000"),
        montant_paye=D("0"), fournisseur_id=uuid4(), date_echeance=None, bon_id=uuid4(),
    )
    bon = SimpleNamespace(moyen_paiement="Amanty", ref_paiement="+222 22 00 00 00")
    svc = _svc_paiement(facture, 0, bon)
    svc.recalculate_invoice_payment = AsyncMock()
    row = await svc.create_paiement(PaiementCreate(facture_id=facture.id, montant=D("500")), _user())
    assert (row.mode_paiement, row.reference_paiement) == ("Amanty", "+222 22 00 00 00")

    # Moyen choisi différent du BC : la référence du BC (RIB / téléphone) n'est pas reprise.
    row = await svc.create_paiement(
        PaiementCreate(facture_id=facture.id, montant=D("100"), mode_paiement="Cash"), _user()
    )
    assert (row.mode_paiement, row.reference_paiement) == ("Cash", None)


@pytest.mark.asyncio
async def test_paiement_refuse_sur_facture_non_validee():
    facture = SimpleNamespace(id=uuid4(), reference="FAC-1", statut="ANOMALIE", montant_ttc=D("100"), fournisseur_id=uuid4())
    svc = _svc_paiement(facture, 0)
    with pytest.raises(HTTPException) as exc:
        await svc.create_paiement(PaiementCreate(facture_id=facture.id, montant=D("10")), _user())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_paiement_paye_montant_fige():
    facture = SimpleNamespace(id=uuid4(), reference="FAC-1", statut="PARTIELLEMENT_PAYEE", montant_ttc=D("100"))
    row = SimpleNamespace(id=uuid4(), reference="PAY-1", statut="PAYE", montant=D("50"), date_paiement=date(2026, 9, 1), facture_id=facture.id)
    svc = _svc_paiement(facture, 50)
    svc.get_paiement = AsyncMock(return_value=row)
    svc.db.scalar = AsyncMock(return_value=row)
    with pytest.raises(HTTPException) as exc:
        await svc.update_paiement(row.id, PaiementUpdate(montant=D("60")))
    assert exc.value.status_code == 409


# --- Verrouillage BC ---


def _svc_bc(bon):
    svc = MgAchatsService(_db())
    svc.get_bon = AsyncMock(return_value=bon)
    svc._append_event = AsyncMock()
    return svc


def _body_lignes(bon, **override):
    lg = bon.lignes[0]
    data = dict(description=lg.description, quantite=lg.quantite, prix_unitaire=lg.prix_unitaire, taux_tva=lg.taux_tva)
    data.update(override)
    return [BcLigneIn(**data)]


@pytest.mark.asyncio
async def test_bc_partiel_lignes_verrouillees():
    bon = _bon("PARTIEL", [_ligne(q=10, recu=5)])
    svc = _svc_bc(bon)
    with pytest.raises(HTTPException) as exc:
        await svc.update_bon(bon.id, BonUpdate(lignes=_body_lignes(bon, quantite=8)))
    assert exc.value.status_code == 409
    assert bon.lignes[0].quantite_recue == D(5)


@pytest.mark.asyncio
async def test_bc_partiel_logistique_modifiable_et_formulaire_complet_accepte():
    bon = _bon("PARTIEL", [_ligne(q=10, recu=5)])
    svc = _svc_bc(bon)
    body = BonUpdate(lignes=_body_lignes(bon), date_bc=bon.date_bc, observation="Livrer au 2e étage")
    await svc.update_bon(bon.id, body)
    assert bon.observation == "Livrer au 2e étage"
    assert bon.lignes[0].quantite_recue == D(5)


@pytest.mark.asyncio
async def test_bc_fige_aucune_modification():
    bon = _bon("CLOTURE", [_ligne()])
    svc = _svc_bc(bon)
    with pytest.raises(HTTPException) as exc:
        await svc.update_bon(bon.id, BonUpdate(observation="x"))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_bc_brouillon_edition_en_place_sans_reset_recu():
    lg = _ligne(q=10)
    bon = _bon("BROUILLON", [lg])
    svc = _svc_bc(bon)
    svc._lignes_bc_referencees = AsyncMock(return_value=set())
    await svc.update_bon(bon.id, BonUpdate(lignes=_body_lignes(bon, quantite=12, taux_tva=D("16"))))
    assert bon.lignes[0] is lg and lg.quantite == 12
    assert bon.total_ttc == D("1392.00")


@pytest.mark.asyncio
async def test_suppression_bc_hors_brouillon_refusee():
    bon = _bon("VALIDE", [_ligne()])
    svc = _svc_bc(bon)
    with pytest.raises(HTTPException) as exc:
        await svc.delete_bon(bon.id, _user())
    assert exc.value.status_code == 409


# --- Transitions BC ---


@pytest.mark.asyncio
async def test_circuit_bc_sans_visa():
    bon = _bon("BROUILLON", [_ligne()])
    svc = _svc_bc(bon)
    u = _user()
    for action, attendu in (("soumettre", "SOUMIS"), ("valider", "VALIDE"), ("envoyer", "ENVOYE")):
        await svc.transition_bon(bon.id, action, u)
        assert bon.statut == attendu
    assert bon.soumis_by == bon.valide_by == bon.envoye_by == u.id
    with pytest.raises(HTTPException) as exc:
        await svc.transition_bon(bon.id, "visa_mg", u)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_annulation_bc_motif_et_suites_actives():
    bon = _bon("ENVOYE", [_ligne()])
    svc = _svc_bc(bon)
    with pytest.raises(HTTPException):
        await svc.transition_bon(bon.id, "annuler", _user())
    svc._bc_a_des_suites_actives = AsyncMock(return_value="la réception REC-1")
    with pytest.raises(HTTPException) as exc:
        await svc.transition_bon(bon.id, "annuler", _user(), motif="Doublon")
    assert exc.value.status_code == 409
    svc._bc_a_des_suites_actives = AsyncMock(return_value=None)
    await svc.transition_bon(bon.id, "annuler", _user(), motif="Doublon")
    assert bon.statut == "ANNULEE" and bon.motif_annulation == "Doublon"


@pytest.mark.asyncio
async def test_cloture_uniquement_depuis_recu():
    bon = _bon("PARTIEL", [_ligne(recu=5)])
    svc = _svc_bc(bon)
    with pytest.raises(HTTPException):
        await svc.transition_bon(bon.id, "cloturer", _user())


# --- Réceptions multiples ---


def _svc_reception(bon):
    svc = _svc_bc(bon)
    svc._next_ref = AsyncMock(return_value="REC-1")
    svc.get_reception = AsyncMock(side_effect=lambda _id: SimpleNamespace(id=_id))
    return svc


def _rec(bon, *lignes):
    return ReceptionCreate(
        bon_id=bon.id,
        date_reception=date(2026, 9, 30),
        lignes=[ReceptionLigneIn(bc_ligne_id=lg.id, quantite_recue=q) for lg, q in lignes],
    )


@pytest.mark.asyncio
async def test_receptions_multiples_jusqu_au_recu():
    a, b = _ligne("A", q=10), _ligne("B", q=4)
    bon = _bon("ENVOYE", [a, b], envoye_at=object())
    svc = _svc_reception(bon)
    with patch("app.services.mg_stock_service.MgStockService"):
        await svc.create_reception(_rec(bon, (a, 6)), _user())
        assert bon.statut == "PARTIEL"
        await svc.create_reception(_rec(bon, (a, 4), (b, 4)), _user())
    assert bon.statut == "RECU"
    assert (a.quantite_recue, b.quantite_recue) == (D(10), D(4))


@pytest.mark.asyncio
async def test_reception_doublons_agreges_contre_le_reste():
    a = _ligne("A", q=10, recu=6)
    bon = _bon("PARTIEL", [a])
    svc = _svc_reception(bon)
    with pytest.raises(HTTPException) as exc:
        await svc.create_reception(_rec(bon, (a, 3), (a, 3)), _user())
    assert "reste à recevoir 4" in exc.value.detail
    assert a.quantite_recue == D(6)


@pytest.mark.asyncio
async def test_reception_refusee_sur_bc_non_valide():
    a = _ligne("A")
    bon = _bon("SOUMIS", [a])
    svc = _svc_reception(bon)
    with pytest.raises(HTTPException) as exc:
        await svc.create_reception(_rec(bon, (a, 1)), _user())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_annulation_reception_refusee_si_deja_facturee():
    a = _ligne("A", q=10, recu=10)
    bon = _bon("RECU", [a])
    rec = SimpleNamespace(
        id=uuid4(), reference="REC-2", bon_id=bon.id, statut="COMPLETE", agence_id=None,
        lignes=[SimpleNamespace(bc_ligne_id=a.id, quantite_recue=D(5), article_id=None)],
    )
    svc = _svc_reception(bon)
    svc.get_reception = AsyncMock(return_value=rec)
    svc.db.scalar = AsyncMock(return_value=rec)
    svc._quantites_facturees = AsyncMock(return_value={a.id: D(8)})
    with pytest.raises(HTTPException) as exc:
        await svc.cancel_reception(rec.id, _user(), "Erreur de saisie")
    assert exc.value.status_code == 409
    assert a.quantite_recue == D(10)

    svc._quantites_facturees = AsyncMock(return_value={a.id: D(5)})
    with patch("app.services.mg_stock_service.MgStockService"):
        await svc.cancel_reception(rec.id, _user(), "Erreur de saisie")
    assert a.quantite_recue == D(5)
    assert rec.statut == "ANNULEE" and bon.statut == "PARTIEL"


# --- Factures multiples via le service ---


def _svc_facture(bon, deja):
    db = _db()
    db.scalar = AsyncMock(return_value=SimpleNamespace(id=bon.fournisseur_id))
    svc = MgAchatsService(db)
    svc.get_bon = AsyncMock(return_value=bon)
    svc._next_ref = AsyncMock(return_value="FAC-1")
    svc._append_event = AsyncMock()
    svc._derniere_reception = AsyncMock(return_value=None)
    svc._quantites_facturees = AsyncMock(return_value=deja)
    svc.get_facture = AsyncMock(side_effect=lambda _id: SimpleNamespace(id=_id))
    return svc


def _fac(bon, *lignes, ttc=None):
    return FactureCreate(
        bon_id=bon.id,
        date_facture=date(2026, 9, 30),
        montant_ttc=ttc,
        lignes=[
            FactureLigneIn(bc_ligne_id=lg.id, designation=lg.description, quantite=q, prix_unitaire=lg.prix_unitaire)
            for lg, q in lignes
        ],
    )


@pytest.mark.asyncio
async def test_create_facture_partielle_conforme_et_verrou_bc():
    a = _ligne("Chaise", q=10, recu=5, pu=100, tva=16)
    bon = _bon("PARTIEL", [a])
    svc = _svc_facture(bon, {})
    added = []
    svc.db.add = MagicMock(side_effect=added.append)
    await svc.create_facture(_fac(bon, (a, 5)), _user())
    fac = added[0]
    assert fac.statut == "RECUE"
    assert (fac.montant_ht, fac.montant_tva, fac.montant_ttc) == (D("500.00"), D("80.00"), D("580.00"))
    assert fac.lignes[0].bc_ligne_id == a.id and fac.lignes[0].montant_tva == D("80.00")
    svc.get_bon.assert_awaited_with(bon.id, for_update=True)


@pytest.mark.asyncio
async def test_create_facture_au_dela_du_commande_refusee():
    a = _ligne("Chaise", q=10, recu=10)
    bon = _bon("RECU", [a])
    svc = _svc_facture(bon, {a.id: D(8)})
    with pytest.raises(HTTPException) as exc:
        await svc.create_facture(_fac(bon, (a, 3)), _user())
    assert "reste à facturer 2" in exc.value.detail


@pytest.mark.asyncio
async def test_create_facture_refusee_sur_bc_brouillon():
    a = _ligne("Chaise")
    bon = _bon("BROUILLON", [a])
    svc = _svc_facture(bon, {})
    with pytest.raises(HTTPException) as exc:
        await svc.create_facture(_fac(bon, (a, 1)), _user())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_validation_facture_anomalie_exige_motif():
    a = _ligne("Chaise", q=10, recu=3)
    bon = _bon("PARTIEL", [a])
    facture = SimpleNamespace(
        id=uuid4(), reference="FAC-1", bon_id=bon.id, statut="ANOMALIE", montant_ttc=D("500"),
        montant_paye=D("0"), lignes=[_fl(a, 5, 100)], ecart_quantite=True, ecart_montant=False,
    )
    svc = _svc_facture(bon, {})
    svc.get_facture = AsyncMock(return_value=facture)
    with pytest.raises(HTTPException) as exc:
        await svc.validate_invoice(facture.id, _user())
    assert "motif" in exc.value.detail
    await svc.validate_invoice(facture.id, _user(), "Reliquat livré, BL en attente")
    assert facture.statut == "A_PAYER" and facture.motif_validation


@pytest.mark.asyncio
async def test_facture_validee_non_modifiable():
    facture = SimpleNamespace(id=uuid4(), reference="FAC-1", bon_id=uuid4(), statut="A_PAYER")
    svc = MgAchatsService(_db())
    svc.get_facture = AsyncMock(return_value=facture)
    svc.get_bon = AsyncMock(return_value=_bon("RECU"))
    from app.schemas.mg_achats import FactureUpdate

    with pytest.raises(HTTPException) as exc:
        await svc.update_facture(facture.id, FactureUpdate(observation="x"))
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException):
        await svc.update_facture(facture.id, FactureUpdate(statut="PAYEE"))


# --- Mode test (ACHATS_MODE_TEST=1) : verrous levés, cohérence conservée ---


@pytest.mark.asyncio
async def test_mode_test_bc_recu_lignes_modifiables_mais_jamais_sous_le_recu():
    bon = _bon("RECU", [_ligne(q=10, recu=5)])
    svc = _svc_bc(bon)
    svc.mode_test = True
    svc._lignes_bc_referencees = AsyncMock(return_value=set())
    await svc.update_bon(bon.id, BonUpdate(lignes=_body_lignes(bon, quantite=8, prix_unitaire=D("120"))))
    assert (bon.lignes[0].quantite, bon.lignes[0].prix_unitaire, bon.statut) == (D(8), D("120"), "PARTIEL")
    assert bon.lignes[0].quantite_recue == D(5)

    with pytest.raises(HTTPException) as exc:
        await svc.update_bon(bon.id, BonUpdate(lignes=_body_lignes(bon, quantite=3)))
    assert "inférieure au déjà reçu" in exc.value.detail


@pytest.mark.asyncio
async def test_mode_test_suppression_paiement_recalcule_la_facture():
    facture = SimpleNamespace(id=uuid4(), reference="FAC-1", statut="PAYEE")
    paiement = SimpleNamespace(id=uuid4(), reference="PAY-1", facture_id=facture.id, deleted_at=None)
    svc = MgAchatsService(_db(), mode_test=True)
    svc.get_paiement = AsyncMock(return_value=paiement)
    svc._facture_pour_paiement = AsyncMock(return_value=facture)
    svc.recalculate_invoice_payment = AsyncMock()
    svc._append_event = AsyncMock()
    await svc.soft_delete_entity("paiement", paiement.id, _user())
    assert paiement.deleted_at is not None
    svc.recalculate_invoice_payment.assert_awaited_once_with(facture)


@pytest.mark.asyncio
async def test_hors_mode_test_suppression_paiement_refusee():
    svc = MgAchatsService(_db(), mode_test=False)
    with pytest.raises(HTTPException) as exc:
        await svc.soft_delete_entity("paiement", uuid4(), _user())
    assert exc.value.status_code == 409
