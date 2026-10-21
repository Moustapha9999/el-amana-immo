"""IP cliente : en-têtes transférés lus uniquement depuis un proxy de confiance déclaré."""

import socket
import uuid

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from app.core import request_client
from app.core.config import get_settings
from app.core.request_client import TrustedProxies, get_client_ip, parse_ip, resolve_client_ip
from app.middleware import request_context
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware

FRONTEND = "172.18.0.7"
PASSERELLE = "172.18.0.1"
CLIENT = "198.51.100.7"
FAUX = "6.6.6.6"


def _resoudre(peer, xff=None, real=None, trusted=""):
    return resolve_client_ip(peer, xff, real, TrustedProxies(trusted))


def test_ip_directe_sans_en_tete():
    assert _resoudre(CLIENT) == CLIENT
    assert _resoudre(CLIENT, trusted=FRONTEND) == CLIENT


def test_x_forwarded_for_falsifie_par_un_pair_non_fiable():
    assert _resoudre(CLIENT, xff=FAUX) == CLIENT
    assert _resoudre(CLIENT, xff=f"{FAUX}, 10.0.0.1", trusted=FRONTEND) == CLIENT


def test_x_real_ip_ignore_hors_proxy_de_confiance():
    assert _resoudre(CLIENT, real=FAUX) == CLIENT


def test_aucune_confiance_par_defaut():
    vide = TrustedProxies("")
    assert not vide.configured
    assert not vide.contains(parse_ip("127.0.0.1"))
    assert _resoudre("127.0.0.1", xff=FAUX) == "127.0.0.1"


def test_proxy_de_confiance_unique():
    assert _resoudre(FRONTEND, xff=CLIENT, trusted=FRONTEND) == CLIENT


def test_plusieurs_adresses_seul_le_dernier_saut_non_fiable_compte():
    # Le navigateur envoie « 6.6.6.6 », nginx ajoute l'adresse réellement vue.
    assert _resoudre(FRONTEND, xff=f"{FAUX}, {CLIENT}", trusted=FRONTEND) == CLIENT


def test_chaine_de_deux_proxys_de_confiance():
    xff = f"{FAUX}, {CLIENT}, {PASSERELLE}"
    assert _resoudre(FRONTEND, xff=xff, trusted=f"{FRONTEND},{PASSERELLE}") == CLIENT
    # Passerelle non déclarée : on s'arrête sur elle, jamais sur l'adresse fournie par le client.
    assert _resoudre(FRONTEND, xff=xff, trusted=FRONTEND) == PASSERELLE


def test_cidr_de_confiance():
    assert _resoudre(FRONTEND, xff=f"{FAUX}, {CLIENT}", trusted="172.18.0.0/16") == CLIENT


def test_tous_les_sauts_fiables_retient_le_plus_a_gauche():
    assert _resoudre(FRONTEND, xff="10.1.2.3, 172.18.0.9", trusted="172.18.0.0/16,10.0.0.0/8") == "10.1.2.3"


@pytest.mark.parametrize("xff", ["", "   ", ",", "pas-une-ip", "198.51.100.7:443", "999.1.1.1"])
def test_en_tete_absent_ou_mal_forme_garde_le_pair(xff):
    assert _resoudre(FRONTEND, xff=xff, trusted=FRONTEND) == FRONTEND


def test_element_mal_forme_arrete_la_remontee():
    assert _resoudre(FRONTEND, xff=f"pas-une-ip, {CLIENT}", trusted=FRONTEND) == CLIENT
    assert _resoudre(FRONTEND, xff=f"{CLIENT}, pas-une-ip", trusted=FRONTEND) == FRONTEND


def test_x_real_ip_depuis_proxy_de_confiance_sans_xff():
    assert _resoudre(FRONTEND, real=CLIENT, trusted=FRONTEND) == CLIENT
    assert _resoudre(FRONTEND, real="n'importe quoi", trusted=FRONTEND) == FRONTEND


def test_ipv6_et_ipv4_mappee():
    assert _resoudre("::ffff:198.51.100.7") == CLIENT
    assert _resoudre("2001:db8::1", xff=FAUX) == "2001:db8::1"
    assert _resoudre(FRONTEND, xff="2001:db8::5", trusted=FRONTEND) == "2001:db8::5"


def test_pair_absent_ou_invalide():
    assert _resoudre(None, xff=CLIENT, trusted=FRONTEND) is None
    assert _resoudre("testclient", xff=CLIENT, trusted=FRONTEND) is None


def test_nom_de_service_docker_resolu(monkeypatch):
    appels = []

    def faux_getaddrinfo(host, *args, **kwargs):
        appels.append(host)
        if host == "frontend":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (FRONTEND, 0))]
        raise socket.gaierror("inconnu")

    monkeypatch.setattr(request_client.socket, "getaddrinfo", faux_getaddrinfo)
    trusted = TrustedProxies("frontend,inexistant")
    assert resolve_client_ip(FRONTEND, f"{FAUX}, {CLIENT}", None, trusted) == CLIENT
    assert resolve_client_ip("172.18.0.99", f"{FAUX}, {CLIENT}", None, trusted) == "172.18.0.99"
    assert appels.count("frontend") == 1, "résolution mise en cache"


# --- Intégration : rate limiting, journal d'erreurs et IP lue par les services -------------


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/ip")
    async def ip(request: Request):
        return {"ip": get_client_ip(request)}

    @app.get("/api/erreur")
    async def erreur():
        raise HTTPException(status_code=409, detail="conflit")

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    return app


@pytest.fixture
def proxys(monkeypatch):
    settings = get_settings()

    def regler(valeur: str) -> None:
        monkeypatch.setattr(settings, "trusted_proxies", valeur)

    regler("")
    return regler


@pytest.fixture
def erreurs(monkeypatch):
    captures: list[dict] = []
    monkeypatch.setattr(request_context, "should_record", lambda path, status: path.startswith("/api/"))
    monkeypatch.setattr(request_context, "record_api_error", lambda **f: captures.append(f))
    return captures


def _ip_unique() -> str:
    b = uuid.uuid4().bytes
    return f"203.0.{b[0]}.{max(b[1], 1)}"


async def _get(peer: str, path: str, headers: dict | None = None):
    transport = ASGITransport(app=_app(), client=(peer, 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers or {})


async def test_en_tete_falsifie_ne_change_ni_ip_ni_compteur(proxys, erreurs):
    pair = _ip_unique()
    r1 = await _get(pair, "/api/ip", {"X-Forwarded-For": "1.1.1.1"})
    r2 = await _get(pair, "/api/ip", {"X-Forwarded-For": "2.2.2.2", "X-Real-IP": "3.3.3.3"})
    assert r1.json()["ip"] == r2.json()["ip"] == pair
    assert int(r1.headers["X-RateLimit-Remaining"]) - int(r2.headers["X-RateLimit-Remaining"]) == 1


async def test_proxy_de_confiance_separe_les_clients(proxys, erreurs):
    proxys(FRONTEND)
    a, b = _ip_unique(), _ip_unique()
    ra = await _get(FRONTEND, "/api/ip", {"X-Forwarded-For": f"{FAUX}, {a}"})
    rb = await _get(FRONTEND, "/api/ip", {"X-Forwarded-For": b})
    assert ra.json()["ip"] == a
    assert rb.json()["ip"] == b
    assert ra.headers["X-RateLimit-Remaining"] == rb.headers["X-RateLimit-Remaining"]


async def test_proxy_non_fiable_compte_sur_son_adresse(proxys, erreurs):
    proxys(FRONTEND)
    autre = _ip_unique()
    r = await _get(autre, "/api/ip", {"X-Forwarded-For": _ip_unique()})
    assert r.json()["ip"] == autre


async def test_journal_erreurs_meme_ip_que_rate_limit(proxys, erreurs):
    proxys(FRONTEND)
    client = _ip_unique()
    r = await _get(FRONTEND, "/api/erreur", {"X-Forwarded-For": f"{FAUX}, {client}"})
    assert r.status_code == 409
    assert erreurs and erreurs[-1]["ip_address"] == client
    erreurs.clear()
    pair = _ip_unique()
    await _get(pair, "/api/erreur", {"X-Forwarded-For": FAUX})
    assert erreurs[-1]["ip_address"] == pair
