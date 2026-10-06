"""Facturation Fournisseurs — TVA par profil (taux datés) : CRUD, chevauchements, prise en compte par date.

Fonctions pures + intégration PostgreSQL (transaction externe annulée, cf. ``test_mg_facturation_profils``).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.exceptions import AppError
from app.schemas.mg_facturation import FactureCreate, NouveauFournisseurIn, ProfilCreate, ProfilIn, TvaIn, TvaUpdate
from app.services.mg_facturation_service import periodes_chevauchent, taux_applicable
from tests.test_mg_facturation_profils import _contexte, _numero, db  # noqa: F401


def _t(taux, debut=None, fin=None):
    return SimpleNamespace(taux=Decimal(taux), date_debut=debut, date_fin=fin)


def test_taux_applicable_par_date():
    d = date(2026, 1, 1)
    lignes = [_t("16", None, date(2025, 12, 31)), _t("18", d)]
    assert taux_applicable(lignes, date(2025, 6, 1)) == Decimal("16")
    assert taux_applicable(lignes, date(2026, 3, 1)) == Decimal("18")
    assert taux_applicable([], date(2026, 3, 1)) is None
    assert taux_applicable([_t("18", date(2027, 1, 1))], date(2026, 3, 1)) is None


def test_periodes_chevauchent():
    assert periodes_chevauchent(None, None, date(2026, 1, 1), None)
    assert not periodes_chevauchent(None, date(2025, 12, 31), date(2026, 1, 1), None)
    assert periodes_chevauchent(date(2026, 1, 1), date(2026, 6, 30), date(2026, 6, 30), None)


async def _profil_vierge(svc, user) -> dict:
    return await svc.create_profil(
        ProfilCreate(
            code=f"T_{uuid.uuid4().hex[:6]}", libelle="Profil TVA test",
            nouveau_fournisseur=NouveauFournisseurIn(raison_sociale=f"FOURNISSEUR TVA {uuid.uuid4().hex[:6].upper()}"),
        ),
        user,
    )


async def test_crud_tva_et_chevauchement(db):  # noqa: F811
    user, _profils, svc = await _contexte(db)
    p = await _profil_vierge(svc, user)
    pid = uuid.UUID(p["id"])
    assert p["taux_tva"] is None and p["taux_tva_liste"] == []

    debut = date.today() - timedelta(days=30)
    p = await svc.create_tva(TvaIn(profil_id=pid, taux=Decimal("16"), date_debut=debut, observation="Initial"), user)
    assert p["taux_tva"] == 16.0 and p["taux_tva_liste"][0]["etat"] == "EN_VIGUEUR"
    tva_id = uuid.UUID(p["taux_tva_liste"][0]["id"])

    with pytest.raises(AppError) as err:
        await svc.create_tva(TvaIn(profil_id=pid, taux=Decimal("18"), date_debut=date.today()), user)
    assert err.value.code == "TVA_CHEVAUCHEMENT"
    with pytest.raises(AppError) as err:
        await svc.create_tva(TvaIn(profil_id=pid, taux=Decimal("18"), date_debut=date.today(), date_fin=debut), user)
    assert err.value.code == "TVA_PERIODE_INVALIDE"

    p = await svc.update_tva(tva_id, TvaUpdate(date_fin=date.today() - timedelta(days=1)), user)
    assert p["taux_tva"] is None and p["taux_tva_liste"][0]["etat"] == "EXPIRE"
    p = await svc.create_tva(TvaIn(profil_id=pid, taux=Decimal("18"), date_debut=date.today()), user)
    assert p["taux_tva"] == 18.0 and len(p["taux_tva_liste"]) == 2

    nouveau = next(t for t in p["taux_tva_liste"] if t["taux"] == 18.0)
    p = await svc.update_tva(uuid.UUID(nouveau["id"]), TvaUpdate(taux=Decimal("17.5")), user)
    assert p["taux_tva"] == 17.5

    p = await svc.delete_tva(uuid.UUID(nouveau["id"]), user)
    assert p["taux_tva"] is None and len(p["taux_tva_liste"]) == 1
    assert (await svc._profil(pid, actif=False)).taux_tva is None

    with pytest.raises(AppError) as err:
        await svc.update_profil(pid, ProfilIn(taux_tva=Decimal("18")), user)
    assert err.value.code == "PROFIL_TVA_PARAMETRES"


async def test_controle_tva_selon_date_facture(db):  # noqa: F811
    user, _profils, svc = await _contexte(db)
    p = await _profil_vierge(svc, user)
    pid = uuid.UUID(p["id"])
    bascule = date.today() - timedelta(days=10)
    await svc.create_tva(TvaIn(profil_id=pid, taux=Decimal("16"), date_fin=bascule - timedelta(days=1)), user)
    await svc.create_tva(TvaIn(profil_id=pid, taux=Decimal("18"), date_debut=bascule), user)

    ancienne = await svc.create_facture(
        FactureCreate(profil_id=pid, date_facture=bascule - timedelta(days=5), numero_fournisseur=_numero(),
                      montant_ht=Decimal("1000"), montant_tva=Decimal("160")),
        user,
    )
    recente = await svc.create_facture(
        FactureCreate(profil_id=pid, date_facture=date.today(), numero_fournisseur=_numero(),
                      montant_ht=Decimal("1000"), montant_tva=Decimal("160")),
        user,
    )
    detail_ancienne = await svc.get_facture(uuid.UUID(ancienne["id"]), user)
    detail_recente = await svc.get_facture(uuid.UUID(recente["id"]), user)
    assert detail_ancienne["taux_tva_facture"] == 16.0 and detail_recente["taux_tva_facture"] == 18.0
    assert "tva_incoherente" not in {c["code"] for c in detail_ancienne["controles"]}
    assert "tva_incoherente" in {c["code"] for c in detail_recente["controles"]}

    file = {i["id"]: i for i in (await svc.file_controles({}))["items"]}
    assert "tva_incoherente" not in {c["code"] for c in file[ancienne["id"]]["controles"]}
    assert "tva_incoherente" in {c["code"] for c in file[recente["id"]]["controles"]}


async def test_creation_profil_avec_taux(db):  # noqa: F811
    user, _profils, svc = await _contexte(db)
    p = await svc.create_profil(
        ProfilCreate(
            code=f"T_{uuid.uuid4().hex[:6]}", libelle="Avec taux", taux_tva=Decimal("14"),
            nouveau_fournisseur=NouveauFournisseurIn(raison_sociale=f"FOURNISSEUR TX {uuid.uuid4().hex[:6].upper()}"),
        ),
        user,
    )
    assert p["taux_tva"] == 14.0 and len(p["taux_tva_liste"]) == 1
    tva = next(x for x in await svc.list_tva() if x["id"] == p["id"])
    assert tva["taux_tva"] == 14.0
