"""Helpers liés à la requête HTTP (IP client, etc.)."""

from __future__ import annotations

from fastapi import Request


def _normalize_ip(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    # IPv6 mappé IPv4 (::ffff:192.168.1.10)
    if value.lower().startswith("::ffff:"):
        value = value[7:]
    # Limite colonne audit_logs.ip_address (45)
    return value[:45]


def get_client_ip(request: Request | None) -> str | None:
    """IP réelle du client, y compris derrière proxy / reverse-proxy.

    Ordre de priorité :
    1. X-Forwarded-For (premier hop = client d'origine)
    2. X-Real-IP
    3. CF-Connecting-IP (Cloudflare)
    4. request.client.host (connexion directe)
    """
    if request is None:
        return None

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0]
        ip = _normalize_ip(first)
        if ip:
            return ip

    for header in ("x-real-ip", "cf-connecting-ip", "true-client-ip"):
        ip = _normalize_ip(request.headers.get(header))
        if ip:
            return ip

    if request.client and request.client.host:
        return _normalize_ip(request.client.host)

    return None
