"""Protection SSRF (Phase 5) — aucun réseau : résolution et URL injectées ou refusées localement."""

from __future__ import annotations

import pytest

from app.services.integrations.ssrf import (
    RefusSsrf,
    construire_url,
    ip_interdite,
    normaliser_hote,
    normaliser_port,
    resoudre,
    substituer_chemin,
)


@pytest.mark.parametrize("adresse", [
    "127.0.0.1", "0.0.0.0", "10.0.0.1", "192.168.1.1", "172.16.0.2",
    "169.254.169.254", "224.0.0.1", "255.255.255.255", "::1", "fe80::1", "fc00::1",
    "192.0.2.1", "203.0.113.10",
])
def test_adresses_non_globales_interdites(adresse):
    assert ip_interdite(adresse)


def test_adresse_publique_autorisee():
    assert not ip_interdite("8.8.8.8")
    assert not ip_interdite("1.1.1.1")


@pytest.mark.parametrize("hote,code", [
    ("localhost", "HOTE_INTERDIT"),
    ("metadata.google.internal", "HOTE_INTERDIT"),
    ("svc.internal", "HOTE_INTERDIT"),
    ("box.local", "HOTE_INTERDIT"),
    ("127.0.0.1", "IP_INTERDITE"),
    ("169.254.169.254", "IP_INTERDITE"),
    ("10.1.2.3", "IP_INTERDITE"),
    ("2130706433", "HOTE_AMBIGU"),
    ("0x7f000001", "HOTE_AMBIGU"),
    ("user@api.example", "HOTE_INVALIDE"),
    ("api.example/path", "HOTE_INVALIDE"),
    ("api.example%00.evil", "HOTE_INVALIDE"),
    ("", "HOTE_INVALIDE"),
    ("not a host", "HOTE_INVALIDE"),
])
def test_hotes_refusés(hote, code):
    with pytest.raises(RefusSsrf) as exc:
        normaliser_hote(hote)
    assert exc.value.code == code


def test_hote_idna_normalise():
    assert normaliser_hote("API.Test.Example.") == "api.test.example"


def test_port_443_seul_si_politique_stricte():
    assert normaliser_port(443, [443]) == 443
    with pytest.raises(RefusSsrf) as exc:
        normaliser_port(8080, [443])
    assert exc.value.code == "PORT_INTERDIT"


def test_dns_refuse_si_une_adresse_est_privee():
    def mixte(host, *a, **k):
        return [
            (2, 1, 6, "", ("8.8.8.8", 0)),
            (2, 1, 6, "", ("10.0.0.8", 0)),
        ]

    with pytest.raises(RefusSsrf) as exc:
        resoudre("api.test.example", getaddrinfo=mixte)
    assert exc.value.code == "IP_INTERDITE"


def test_dns_refuse_loopback():
    def loop(host, *a, **k):
        return [(2, 1, 6, "", ("127.0.0.1", 0))]

    with pytest.raises(RefusSsrf) as exc:
        resoudre("api.test.example", getaddrinfo=loop)
    assert exc.value.code == "IP_INTERDITE"


def test_dns_ok_adresses_publiques():
    appels = []

    def pub(host, *a, **k):
        appels.append(host)
        return [(2, 1, 6, "", ("8.8.8.8", 0)), (2, 1, 6, "", ("1.1.1.1", 0))]

    r = resoudre("api.test.example", getaddrinfo=pub)
    assert r.ips == ("8.8.8.8", "1.1.1.1") and r.ip_connexion == "8.8.8.8"
    assert appels == ["api.test.example"]


def test_chemin_refuse_traversal_et_identifiants():
    with pytest.raises(RefusSsrf):
        substituer_chemin("/v1/../admin", {})
    with pytest.raises(RefusSsrf):
        substituer_chemin("/v1/{id}", {"id": "../x"})
    with pytest.raises(RefusSsrf):
        substituer_chemin("/v1/{id}", {"id": "a/b"})
    assert substituer_chemin("/v1/{id}", {"id": "AB-12"}) == "/v1/AB-12"


def test_url_construite_https_sans_userinfo():
    url = construire_url(hote="api.test.example", port=443, chemin="/v1/ping", requete={"q": "1"})
    assert url == "https://api.test.example/v1/ping?q=1"
    with pytest.raises(RefusSsrf):
        construire_url(hote="127.0.0.1", port=443, chemin="/")
