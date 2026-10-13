"""Verrou serveur du classement de masse par le moteur SCORE (sans base : le verrou passe avant tout accès)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services.clientele.classification import (
    ClienteleClassificationService,
    autorisation_classement_masse,
    exiger_classement_masse_autorise,
)
from app.services.clientele.lots import ClienteleLotService
from app.services.clientele.service import Ctx
from app.services.clientele.taches import ClienteleTacheService

PERMS = {"clientele.view", "clientele.classif.view", "clientele.classif.execute"}


class _BaseInterdite:
    """Toute utilisation de la session échoue : prouve que le refus intervient avant la base."""

    def __getattr__(self, nom):
        raise AssertionError(f"Accès base inattendu : {nom}")


def _ctx() -> Ctx:
    return Ctx(user=SimpleNamespace(id=uuid.uuid4(), is_superuser=False), permissions=set(PERMS))


def _suspendu(e: pytest.ExceptionInfo) -> None:
    assert e.value.code == "CLASSEMENT_MASSE_SUSPENDU" and e.value.status_code == 409


def test_verrou_ferme_par_defaut():
    a = autorisation_classement_masse()
    assert a["actif"] is False and a["reference_validation"] is None and "Conformité" in a["message"]
    with pytest.raises(AppError) as e:
        exiger_classement_masse_autorise()
    _suspendu(e)


@pytest.mark.parametrize("reference", ["", "   "])
def test_actif_sans_reference_reste_bloque(monkeypatch, reference):
    s = get_settings()
    monkeypatch.setattr(s, "clientele_classement_masse_actif", True)
    monkeypatch.setattr(s, "clientele_classement_masse_validation", reference)
    assert autorisation_classement_masse()["actif"] is False
    with pytest.raises(AppError):
        exiger_classement_masse_autorise()


def test_reference_sans_actif_reste_bloque(monkeypatch):
    monkeypatch.setattr(get_settings(), "clientele_classement_masse_validation", "PV Conformité")
    assert autorisation_classement_masse()["actif"] is False


def test_ouverture_exige_actif_et_reference(masse_autorisee):
    a = autorisation_classement_masse()
    assert a == {"actif": True, "reference_validation": "TEST-PYTEST", "message": None}
    assert exiger_classement_masse_autorise() == "TEST-PYTEST"


async def test_classement_masse_moteur_refuse():
    svc = ClienteleClassificationService(_BaseInterdite(), _ctx())
    with pytest.raises(AppError) as e:
        await svc.classer_masse_moteur({"motif": "Test"})
    _suspendu(e)


async def test_appel_indirect_paquet_refuse():
    svc = ClienteleClassificationService(_BaseInterdite(), _ctx())
    with pytest.raises(AppError) as e:
        await svc.traiter_paquet_moteur(["000001"], "Test", {})
    _suspendu(e)


async def test_appliquer_moteur_global_refuse():
    svc = ClienteleClassificationService(_BaseInterdite(), _ctx())
    with pytest.raises(AppError) as e:
        await svc.appliquer_moteur()
    _suspendu(e)


async def test_tache_lancer_et_reprendre_refuses():
    svc = ClienteleTacheService(_BaseInterdite(), _ctx())
    with pytest.raises(AppError) as e:
        await svc.lancer({"motif": "Test", "population": "PM"})
    _suspendu(e)
    with pytest.raises(AppError) as e2:
        await svc.reprendre(uuid.uuid4())
    _suspendu(e2)


async def test_lot_origine_moteur_refuse():
    svc = ClienteleLotService(_BaseInterdite(), _ctx())
    with pytest.raises(AppError) as e:
        await svc.classer(uuid.uuid4(), {"origine": "MOTEUR", "motif": "Test"})
    _suspendu(e)


async def test_lot_origine_fichier_non_concerne():
    svc = ClienteleLotService(_BaseInterdite(), _ctx())
    with pytest.raises(AssertionError, match="Accès base inattendu"):
        await svc.classer(uuid.uuid4(), {"origine": "FICHIER", "motif": "Test"})


def test_autorisation_service_exige_permission_lecture():
    from fastapi import HTTPException

    ctx = Ctx(user=SimpleNamespace(id=uuid.uuid4(), is_superuser=False), permissions=set())
    with pytest.raises(HTTPException):
        ClienteleTacheService(_BaseInterdite(), ctx).autorisation()
    assert ClienteleTacheService(_BaseInterdite(), _ctx()).autorisation()["actif"] is False
