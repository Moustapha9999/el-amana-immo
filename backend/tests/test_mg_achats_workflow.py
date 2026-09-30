"""Achats MG — workflow unitaire (AsyncMock, sans DB)."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.mg_achats import (
    ReceptionCreate,
    ReceptionLigneIn,
)
from app.services.mg_achats_service import BC_TRANSITIONS, DEMANDE_TRANSITIONS, MgAchatsService


def _user():
    u = MagicMock()
    u.id = uuid4()
    u.full_name = "Acheteur Test"
    return u


def _demande(*, statut: str = "BROUILLON"):
    return SimpleNamespace(
        id=uuid4(),
        reference="DA-20260001",
        statut=statut,
        deleted_at=None,
        lignes=[],
    )


def _bc_ligne(
    *,
    quantite: Decimal = Decimal("10"),
    quantite_recue: Decimal = Decimal("0"),
    stockable: bool = False,
    article_id=None,
    description: str = "Article",
    prix_unitaire: Decimal = Decimal("100"),
    taux_tva: Decimal = Decimal("0"),
):
    return SimpleNamespace(
        id=uuid4(),
        description=description,
        quantite=quantite,
        quantite_recue=quantite_recue,
        stockable=stockable,
        article_id=article_id,
        prix_unitaire=prix_unitaire,
        remise_pct=Decimal("0"),
        taux_tva=taux_tva,
        uom="U",
        sort_order=0,
    )


def _bon(*, statut: str = "VALIDE", lignes=None, total_ttc: Decimal = Decimal("1000")):
    return SimpleNamespace(
        id=uuid4(),
        reference="BEA-20260001",
        statut=statut,
        deleted_at=None,
        lignes=lignes or [],
        total_ht=total_ttc,
        total_ttc=total_ttc,
        agence_livraison_id=None,
        fournisseur_id=uuid4(),
        envoye_at=None,
    )


def _fac_ligne(bc, quantite, prix_unitaire, taux_tva=Decimal("0")):
    return SimpleNamespace(
        bc_ligne_id=bc.id if bc is not None else None,
        designation=bc.description if bc is not None else "Hors BC",
        quantite=Decimal(quantite),
        prix_unitaire=Decimal(prix_unitaire),
        taux_tva=taux_tva,
    )


@pytest.mark.asyncio
async def test_demande_transition_brouillon_to_soumise():
    db = MagicMock()
    svc = MgAchatsService(db)
    dem = _demande(statut="BROUILLON")
    dem.lignes = [SimpleNamespace(id=uuid4(), description="Article")]
    svc.get_demande = AsyncMock(return_value=dem)
    svc._append_event = AsyncMock()
    db.commit = AsyncMock()

    result = await svc.transition_demande(dem.id, "soumettre", _user())
    assert result.statut == "SOUMISE"
    assert "soumettre" in DEMANDE_TRANSITIONS


@pytest.mark.asyncio
async def test_demande_transition_refuse_statut():
    db = MagicMock()
    svc = MgAchatsService(db)
    dem = _demande(statut="CLOTUREE")
    svc.get_demande = AsyncMock(return_value=dem)

    with pytest.raises(HTTPException) as exc:
        await svc.transition_demande(dem.id, "soumettre", _user())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bc_envoyer_valide_to_envoye():
    db = MagicMock()
    svc = MgAchatsService(db)
    bon = _bon(statut="VALIDE")
    svc.get_bon = AsyncMock(return_value=bon)
    svc._append_event = AsyncMock()
    db.commit = AsyncMock()
    user = _user()

    result = await svc.transition_bon(bon.id, "envoyer", user)
    assert result.statut == "ENVOYE"
    assert result.envoye_by == user.id and result.envoye_at is not None
    assert BC_TRANSITIONS["envoyer"] == (frozenset({"VALIDE"}), "ENVOYE")


@pytest.mark.asyncio
async def test_bc_envoyer_refuse_si_non_valide():
    db = MagicMock()
    svc = MgAchatsService(db)
    bon = _bon(statut="BROUILLON")
    svc.get_bon = AsyncMock(return_value=bon)

    with pytest.raises(HTTPException) as exc:
        await svc.transition_bon(bon.id, "envoyer", _user())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_reception_partielle():
    db = MagicMock()
    svc = MgAchatsService(db)
    ligne = _bc_ligne(quantite=Decimal("10"), quantite_recue=Decimal("0"), stockable=False)
    bon = _bon(statut="ENVOYE", lignes=[ligne])
    bon.envoye_at = object()
    svc.get_bon = AsyncMock(return_value=bon)
    svc._next_ref = AsyncMock(return_value="REC-20260001")
    svc._append_event = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    svc.get_reception = AsyncMock(side_effect=lambda _id: SimpleNamespace(id=_id, statut="PARTIEL"))

    with patch("app.services.mg_stock_service.MgStockService") as MockStock:
        MockStock.return_value.record_achat_reception = AsyncMock()
        data = ReceptionCreate(
            bon_id=bon.id,
            date_reception=__import__("datetime").date.today(),
            lignes=[ReceptionLigneIn(bc_ligne_id=ligne.id, quantite_recue=Decimal("4"))],
        )
        result = await svc.create_reception(data, _user())

    assert ligne.quantite_recue == Decimal("4")
    assert bon.statut == "PARTIEL"
    assert result.statut == "PARTIEL"
    MockStock.return_value.record_achat_reception.assert_not_awaited()
    svc.get_bon.assert_awaited_with(bon.id, for_update=True)


@pytest.mark.asyncio
async def test_reception_refuse_quantite_superieure_reste():
    db = MagicMock()
    svc = MgAchatsService(db)
    ligne = _bc_ligne(quantite=Decimal("10"), quantite_recue=Decimal("8"))
    bon = _bon(statut="PARTIEL", lignes=[ligne])
    svc.get_bon = AsyncMock(return_value=bon)
    svc._next_ref = AsyncMock(return_value="REC-001")

    data = ReceptionCreate(
        bon_id=bon.id,
        date_reception=__import__("datetime").date.today(),
        lignes=[ReceptionLigneIn(bc_ligne_id=ligne.id, quantite_recue=Decimal("5"))],
    )
    with pytest.raises(HTTPException) as exc:
        await svc.create_reception(data, _user())
    assert exc.value.status_code == 400
    assert "reste" in exc.value.detail.lower()


def _svc_sans_deja():
    svc = MgAchatsService(MagicMock())
    svc._quantites_facturees = AsyncMock(return_value={})
    return svc


@pytest.mark.asyncio
async def test_three_way_match_conforme():
    svc = _svc_sans_deja()
    ligne = _bc_ligne(quantite=Decimal("2"), quantite_recue=Decimal("2"), prix_unitaire=Decimal("100"))
    bon = _bon(statut="RECU", lignes=[ligne], total_ttc=Decimal("200"))
    facture = SimpleNamespace(id=uuid4(), montant_ttc=Decimal("200"), lignes=[_fac_ligne(ligne, 2, 100)])
    match = await svc.three_way_match(bon, facture)
    assert match.resultat == "CONFORME"
    assert match.ecart_quantite is False
    assert match.ecart_montant is False
    assert match.attendu_ttc == Decimal("200.00")


@pytest.mark.asyncio
async def test_three_way_match_anomalie_montant():
    svc = _svc_sans_deja()
    ligne = _bc_ligne(quantite=Decimal("2"), quantite_recue=Decimal("2"))
    bon = _bon(statut="RECU", lignes=[ligne], total_ttc=Decimal("200"))
    facture = SimpleNamespace(id=uuid4(), montant_ttc=Decimal("250"), lignes=[_fac_ligne(ligne, 2, 125)])
    match = await svc.three_way_match(bon, facture)
    assert match.resultat == "ANOMALIE"
    assert match.ecart_montant is True
    assert match.lignes[0].ok is False


@pytest.mark.asyncio
async def test_three_way_match_facture_partielle_conforme():
    """7 facturés sur 10 reçus : facturation partielle, pas une anomalie."""
    svc = _svc_sans_deja()
    ligne = _bc_ligne(quantite=Decimal("10"), quantite_recue=Decimal("10"))
    bon = _bon(statut="RECU", lignes=[ligne], total_ttc=Decimal("1000"))
    facture = SimpleNamespace(id=uuid4(), montant_ttc=Decimal("700"), lignes=[_fac_ligne(ligne, 7, 100)])
    match = await svc.three_way_match(bon, facture)
    assert match.resultat == "CONFORME"


@pytest.mark.asyncio
async def test_three_way_match_anomalie_quantite():
    svc = _svc_sans_deja()
    ligne = _bc_ligne(quantite=Decimal("10"), quantite_recue=Decimal("5"))
    bon = _bon(statut="PARTIEL", lignes=[ligne], total_ttc=Decimal("1000"))
    facture = SimpleNamespace(id=uuid4(), montant_ttc=Decimal("700"), lignes=[_fac_ligne(ligne, 7, 100)])
    match = await svc.three_way_match(bon, facture)
    assert match.resultat == "ANOMALIE"
    assert match.ecart_quantite is True


def _bon_facturable():
    l1 = _bc_ligne(description="Ramette A4", quantite=Decimal("40"), quantite_recue=Decimal("40"), prix_unitaire=Decimal("1500"))
    l2 = _bc_ligne(description="Stylo", quantite=Decimal("5"), quantite_recue=Decimal("0"), prix_unitaire=Decimal("250"))
    for i, (lg, tva) in enumerate(((l1, Decimal("16")), (l2, Decimal("0")))):
        lg.taux_tva = tva
        lg.sort_order = i
    bon = _bon(statut="PARTIEL", lignes=[l1, l2], total_ttc=Decimal("70850"))
    bon.total_ht = Decimal("61250")
    bon.total_tva = Decimal("9600")
    bon.fournisseur_raison_sociale = "MAURITEL"
    bon.conditions_paiement = "Paiement à 30 jours"
    bon.devise = "MRU"
    return bon


@pytest.mark.asyncio
async def test_proposition_facture_reprend_le_recu():
    from datetime import date

    svc = MgAchatsService(MagicMock())
    bon = _bon_facturable()
    rec = SimpleNamespace(id=uuid4(), reference="REC-1", statut="PARTIEL")
    with (
        patch.object(svc, "get_bon", AsyncMock(return_value=bon)),
        patch.object(svc, "list_factures", AsyncMock(return_value=[])),
        patch.object(svc, "list_receptions", AsyncMock(return_value=[rec])),
        patch.object(svc, "_quantites_facturees", AsyncMock(return_value={})),
    ):
        p = await svc.propose_facture(bon.id, date_facture=date(2026, 9, 30))

    assert p.fournisseur_id == bon.fournisseur_id
    assert p.reception_id == rec.id
    assert p.date_echeance == date(2026, 10, 30)
    # Seul le reçu est proposé (le stylo n'est pas encore livré).
    assert [(lg.designation, lg.quantite) for lg in p.lignes] == [("Ramette A4", Decimal("40"))]
    assert p.lignes[0].bc_ligne_id == bon.lignes[0].id
    assert p.montant_ht == Decimal("60000.00")
    assert p.montant_tva == Decimal("9600.00")
    assert p.montant_ttc == Decimal("69600.00")


@pytest.mark.asyncio
async def test_proposition_facture_deduit_le_deja_facture():
    svc = MgAchatsService(MagicMock())
    bon = _bon_facturable()
    deja = SimpleNamespace(id=uuid4(), statut="RECUE", montant_ttc=Decimal("34800"), lignes=[])
    with (
        patch.object(svc, "get_bon", AsyncMock(return_value=bon)),
        patch.object(svc, "list_factures", AsyncMock(return_value=[deja])),
        patch.object(svc, "list_receptions", AsyncMock(return_value=[])),
        patch.object(svc, "_quantites_facturees", AsyncMock(return_value={bon.lignes[0].id: Decimal("25")})),
    ):
        p = await svc.propose_facture(bon.id)

    assert p.lignes[0].quantite == Decimal("15")
    assert p.lignes[0].quantite_deja_facturee == Decimal("25")
    assert p.deja_facture_ttc == Decimal("34800.00")
    assert p.nb_factures == 1


def _facture_dossier(**kw):
    base = dict(
        id=uuid4(),
        fournisseur_id=uuid4(),
        numero_fournisseur="FAC0001",
        montant_ttc=Decimal("61250"),
        ecart_quantite=False,
        ecart_montant=False,
        date_echeance=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_controles_facture_sans_preuve():
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)
    svc = MgAchatsService(db)
    bon = _bon_facturable()
    c = {x.code: x for x in await svc._controles_facture(_facture_dossier(), bon, [], Decimal("61250"))}
    assert c["JUSTIFICATIF"].ok is False
    assert c["NUMERO"].ok is True
    assert "OCR_MONTANT" not in c
    assert c["RECEPTION"].ok is True
    assert c["DOUBLON"].ok is True


@pytest.mark.asyncio
async def test_controles_facture_ocr_et_doublon():
    db = MagicMock()
    db.scalar = AsyncMock(return_value="FAC-20260001")
    svc = MgAchatsService(db)
    doc = SimpleNamespace(ocr_status="done", ocr_text="MAURITEL Facture N° FAC 0001 Total TTC : 61 250,00 MRU")
    c = {
        x.code: x
        for x in await svc._controles_facture(_facture_dossier(), _bon_facturable(), [doc], Decimal("61250"))
    }
    assert c["JUSTIFICATIF"].ok is True
    assert c["OCR_MONTANT"].ok is True
    assert c["OCR_NUMERO"].ok is True
    assert c["DOUBLON"].ok is False
    assert "FAC-20260001" in c["DOUBLON"].detail


def test_taux_tva_facture_repris_du_bc():
    svc = MgAchatsService(MagicMock())
    bon = _bon_facturable()
    assert svc._taux_tva_bc(bon, "RAMETTE a4") == Decimal("16")
    # Désignation inconnue → taux moyen du BC (9 600 / 61 250).
    assert svc._taux_tva_bc(bon, "Autre") == Decimal("15.67")
