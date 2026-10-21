"""IP cliente d'une requête HTTP, derrière des reverse proxys explicitement déclarés.

Règle (``TRUSTED_PROXIES``, liste d'IP, de CIDR ou de noms de service Docker) :

1. Le pair réseau (``request.client.host``) est le point de départ.
2. Tant que l'adresse courante est un proxy de confiance, on remonte ``X-Forwarded-For``
   de droite à gauche : chaque proxy de confiance a ajouté à droite l'adresse qu'il a vue.
3. Le premier saut non fiable (ou le dernier élément de la chaîne) est l'IP cliente.
   Un élément mal formé arrête la remontée sur la dernière adresse établie.
4. ``X-Real-IP`` n'est lu que si le pair est fiable et que ``X-Forwarded-For`` est absent.

Sans proxy de confiance configuré, seuls le pair réseau compte : aucun en-tête n'est lu.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
import time

from fastapi import Request

from app.core.config import get_settings

log = logging.getLogger("bea.request_client")

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

_HOSTNAME_TTL_SECONDS = 30.0


def parse_ip(raw: str | None) -> IpAddress | None:
    """Adresse IP stricte (IPv4 / IPv6, IPv6 mappé IPv4 ramené en IPv4), sinon None."""
    if not raw:
        return None
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


class TrustedProxies:
    """Liste de proxys de confiance : IP, CIDR et noms d'hôte (résolus, cache court)."""

    def __init__(self, raw: str) -> None:
        self.networks: list[IpNetwork] = []
        self.hostnames: list[str] = []
        for item in (raw or "").split(","):
            entry = item.strip()
            if not entry:
                continue
            try:
                self.networks.append(ipaddress.ip_network(entry, strict=False))
                continue
            except ValueError:
                pass
            self.hostnames.append(entry.lower())
        self._lock = threading.Lock()
        self._resolved: set[IpAddress] = set()
        self._resolved_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.networks or self.hostnames)

    def _hostname_ips(self) -> set[IpAddress]:
        if not self.hostnames:
            return set()
        with self._lock:
            if time.monotonic() - self._resolved_at < _HOSTNAME_TTL_SECONDS:
                return self._resolved
            ips: set[IpAddress] = set()
            for host in self.hostnames:
                try:
                    for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP):
                        ip = parse_ip(str(info[4][0]))
                        if ip is not None:
                            ips.add(ip)
                except OSError:
                    log.warning("proxy de confiance non résolu : %s", host)
            self._resolved = ips
            self._resolved_at = time.monotonic()
            return ips

    def contains(self, ip: IpAddress | None) -> bool:
        if ip is None:
            return False
        if any(ip.version == net.version and ip in net for net in self.networks):
            return True
        return ip in self._hostname_ips()


_cache: tuple[str, TrustedProxies] | None = None


def trusted_proxies() -> TrustedProxies:
    global _cache
    raw = get_settings().trusted_proxies
    if _cache is None or _cache[0] != raw:
        _cache = (raw, TrustedProxies(raw))
    return _cache[1]


def resolve_client_ip(
    peer: str | None,
    forwarded_for: str | None,
    real_ip: str | None,
    trusted: TrustedProxies,
) -> str | None:
    client = parse_ip(peer)
    if client is None:
        return None
    if not trusted.contains(client):
        return str(client)
    hops = [h.strip() for h in (forwarded_for or "").split(",") if h.strip()]
    if not hops:
        forwarded = parse_ip(real_ip)
        return str(forwarded or client)
    for hop in reversed(hops):
        if not trusted.contains(client):
            break
        ip = parse_ip(hop)
        if ip is None:
            break
        client = ip
    return str(client)


def get_client_ip(request: Request | None) -> str | None:
    """IP cliente selon ``TRUSTED_PROXIES`` (voir docstring du module). Longueur ≤ 45."""
    if request is None:
        return None
    ip = resolve_client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        request.headers.get("x-real-ip"),
        trusted_proxies(),
    )
    return ip[:45] if ip else None
