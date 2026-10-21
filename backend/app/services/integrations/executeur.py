"""Exécuteur de tests d'API externes (Phase 5).

L'URL est construite côté serveur à partir d'une destination approuvée et d'une opération
validée. Aucun secret n'est stocké ni injecté : un mécanisme d'authentification autre que
« aucun » bloque l'appel. Transport et résolution DNS injectables pour les tests simulés.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Callable

import httpx
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.integrations import (
    IntegrationDestination,
    IntegrationExecution,
    IntegrationFournisseur,
    IntegrationFournisseurOperation,
)
from app.services.audit_helpers import record_audit
from app.services.integrations import destinations as dest
from app.services.integrations.ssrf import (
    RefusSsrf,
    construire_url,
    normaliser_hote,
    normaliser_port,
    resoudre,
    substituer_chemin,
)
from app.services.integrations.clients import _noms, _personne

P_VIEW = "core.admin.integrations.tests.view"
P_EXECUTE = "core.admin.integrations.tests.execute"

METHODES_TEST = frozenset({"GET", "HEAD"})
MECANISMES_SANS_SECRET = frozenset({"aucun"})
TIMEOUT_CONNECT = 3.0
TIMEOUT_READ = 8.0
TIMEOUT_TOTAL_MS = 12000
TAILLE_MAX = 64 * 1024
EXTRAIT_MAX = 2048
QUOTA_USER = 10
QUOTA_FOURN = 20
QUOTA_FENETRE = 600
INFLIGHT_MAX = 3
ENTETES_RESERVES = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie", "host",
    "content-length", "connection", "transfer-encoding", "x-forwarded-for",
    "x-forwarded-host", "x-real-ip",
})
ENTETES_SENSIBLES = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie", "www-authenticate",
})
_SECRET = re.compile(
    r"(?i)bearer\s+[a-z0-9._~+/=-]{8,}|eyJ[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}"
    r"|-----BEGIN |password\s*[:=]\s*\S+|api[_-]?key\s*[:=]\s*\S+"
)

# Transport / résolveur injectés uniquement par les tests (jamais depuis une requête).
_transport_test: httpx.AsyncBaseTransport | None = None
_getaddrinfo_test: Callable | None = None
_quota_test: Callable | None = None


def brancher_test(*, transport=None, getaddrinfo=None, quota=None) -> None:
    """Hook de test isolé : n'est appelé par aucune route."""
    global _transport_test, _getaddrinfo_test, _quota_test
    _transport_test, _getaddrinfo_test, _quota_test = transport, getaddrinfo, quota


def _erreur(message: str, code: str, status: int = 422) -> AppError:
    return AppError(message, status, code=code)


def _mecanisme(op: IntegrationFournisseurOperation) -> str:
    cfg = op.configuration or {}
    return (cfg.get("mecanisme_auth") or "non_precise").lower()


def _assainir(texte: str) -> str:
    propre = _SECRET.sub("<masqué>", texte)
    return "".join(c if (c == "\n" or c == "\t" or ord(c) >= 32) else " " for c in propre)[:EXTRAIT_MAX]


def _entetes_reponse(headers: httpx.Headers) -> list[dict]:
    sortis = []
    for nom, valeur in headers.items():
        if nom.lower() in ENTETES_SENSIBLES:
            continue
        sortis.append({"nom": nom, "valeur": _assainir(valeur)[:200]})
        if len(sortis) >= 20:
            break
    return sortis


class _TransportEpingle(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport, hote: str, ip: str):
        self.inner, self.hote, self.ip = inner, hote, ip

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != self.hote:
            raise RefusSsrf("HOTE_INVALIDE", "Hôte différent de la destination approuvée.")
        headers = request.headers.copy()
        headers["host"] = self.hote
        extensions = dict(request.extensions)
        extensions["sni_hostname"] = self.hote
        cible = self.ip if ":" not in self.ip else f"[{self.ip}]"
        url = request.url.copy_with(host=cible)
        clone = httpx.Request(request.method, url, headers=headers, extensions=extensions)
        return await self.inner.handle_async_request(clone)


async def _quota(user_id: uuid.UUID, fournisseur_id: uuid.UUID) -> None:
    if _quota_test is not None:
        return _quota_test(user_id, fournisseur_id)
    try:
        from redis import asyncio as aioredis
        from app.core.config import get_settings
        r = aioredis.from_url(get_settings().redis_url, socket_timeout=1.5, socket_connect_timeout=1.5)
    except Exception as exc:
        raise _erreur("Limitation de débit indisponible : test refusé", "QUOTA_INDISPONIBLE", 503) from exc
    try:
        inflight = await r.incr("integ:test:inflight")
        await r.expire("integ:test:inflight", 30)
        if inflight > INFLIGHT_MAX:
            await r.decr("integ:test:inflight")
            raise _erreur("Trop de tests simultanés", "QUOTA", 429)
        for cle, limite in (
            (f"integ:test:user:{user_id}", QUOTA_USER),
            (f"integ:test:fourn:{fournisseur_id}", QUOTA_FOURN),
        ):
            n = await r.incr(cle)
            if n == 1:
                await r.expire(cle, QUOTA_FENETRE)
            if n > limite:
                await r.decr("integ:test:inflight")
                raise _erreur("Quota de tests dépassé", "QUOTA", 429)
    except AppError:
        raise
    except Exception as exc:
        raise _erreur("Limitation de débit indisponible : test refusé", "QUOTA_INDISPONIBLE", 503) from exc
    finally:
        try:
            await r.aclose()
        except Exception:
            pass


async def _relacher_inflight() -> None:
    if _quota_test is not None:
        return
    try:
        from redis import asyncio as aioredis
        from app.core.config import get_settings
        r = aioredis.from_url(get_settings().redis_url, socket_timeout=1.5, socket_connect_timeout=1.5)
        await r.decr("integ:test:inflight")
        await r.aclose()
    except Exception:
        pass


def _valider_params(op: IntegrationFournisseurOperation, chemin_vals: dict, query_vals: dict) -> tuple[str, dict]:
    declares = {p["nom"]: p for p in (op.parametres or []) if isinstance(p, dict)}
    path_noms = {n for n, p in declares.items() if p.get("emplacement") == "path"}
    query_noms = {n for n, p in declares.items() if p.get("emplacement") == "query"}
    if set(chemin_vals) != path_noms:
        raise _erreur("Paramètres de chemin incorrects", "PARAMETRE_CHEMIN")
    extra = set(query_vals) - query_noms
    if extra:
        raise _erreur("Paramètre de requête non déclaré", "PARAMETRE_INTERDIT")
    for nom, val in {**chemin_vals, **query_vals}.items():
        if not isinstance(val, str) or len(val) > 200 or _SECRET.search(val):
            raise _erreur("Valeur de paramètre refusée", "PARAMETRE_INTERDIT")
    try:
        chemin = substituer_chemin(op.chemin, chemin_vals)
    except RefusSsrf as exc:
        raise _erreur(exc.message, exc.code) from exc
    return chemin, {k: v for k, v in query_vals.items() if v != ""}


def apercu_donnees(op: IntegrationFournisseurOperation, dest_row: IntegrationDestination,
                   chemin: str, requete: dict, hote: str, port: int) -> dict:
    url = construire_url(hote=hote, port=port, chemin=chemin, requete=requete)
    return {
        "methode": op.methode, "url": url, "hote": hote, "port": port,
        "chemin": chemin, "parametres_requete": list(requete),
        "entetes_envoyes": ["User-Agent", "Accept"],
        "authentification": "aucune — les mécanismes nécessitant un secret sont bloqués",
        "redirections": "désactivées",
        "environnement": "TEST",
        "avertissement": "Aucun secret n'est transmis. L'appel n'est pas encore exécuté.",
    }


async def preparer(db: AsyncSession, *, fournisseur_id, operation_id, destination_id,
                   parametres_chemin: dict, parametres_requete: dict) -> dict:
    f = await db.get(IntegrationFournisseur, fournisseur_id)
    op = await db.get(IntegrationFournisseurOperation, operation_id)
    d = await dest._destination(db, destination_id)
    if f is None or f.statut == "archive":
        raise _erreur("Fournisseur introuvable", "FOURNISSEUR_INTROUVABLE", 404)
    if op is None or op.fournisseur_id != f.id:
        raise _erreur("Opération introuvable", "OPERATION_INTROUVABLE", 404)
    if d.fournisseur_id != f.id:
        raise _erreur("Destination d'un autre fournisseur", "DESTINATION_ETRANGERE", 422)
    if f.statut != "valide":
        raise _erreur("Le fournisseur n'est pas validé", "FOURNISSEUR_NON_VALIDE")
    if f.environnement != "TEST" or d.environnement != "TEST":
        raise _erreur("Seuls les tests en TEST sont autorisés", "ENVIRONNEMENT_FERME")
    if op.statut != "active":
        raise _erreur("Opération archivée", "OPERATION_ARCHIVEE")
    if op.methode not in METHODES_TEST:
        raise _erreur("Méthode non autorisée pour un test", "METHODE_INTERDITE")
    if d.statut != "active":
        raise _erreur("Destination non approuvée", "DESTINATION_INACTIVE")
    if op.methode not in (d.methodes or []):
        raise _erreur("Méthode absente de la destination", "METHODE_INTERDITE")
    autorisees = [str(x) for x in (d.operations or [])]
    if autorisees and str(op.id) not in autorisees:
        raise _erreur("Opération absente de la destination", "OPERATION_NON_AUTORISEE")
    if _mecanisme(op) not in MECANISMES_SANS_SECRET:
        raise _erreur(
            "Aucun coffre de secrets approuvé : les opérations authentifiées ne peuvent pas être testées.",
            "SECRET_REQUIS",
        )
    chemin, requete = _valider_params(op, parametres_chemin, parametres_requete)
    hote = normaliser_hote((d.hotes or [None])[0] or "")
    port = normaliser_port((d.ports or [443])[0], list(d.ports or [443]))
    apercu = apercu_donnees(op, d, chemin, requete, hote, port)
    return {"fournisseur": f, "operation": op, "destination": d, "chemin": chemin,
            "requete": requete, "hote": hote, "port": port, "apercu": apercu}


async def apercu(db: AsyncSession, **kwargs) -> dict:
    prep = await preparer(db, **kwargs)
    return {**prep["apercu"], "fournisseur": prep["fournisseur"].nom, "operation": prep["operation"].nom,
            "destination": prep["destination"].nom}


def _statut_http(code: int | None, redirection: bool) -> str:
    if redirection:
        return "redirection_refusee"
    if code is None:
        return "reponse_invalide"
    if 200 <= code < 300:
        return "succes"
    return "http_erreur"


async def _appeler(url: str, methode: str, hote: str, resolution) -> tuple[str, int | None, dict, str | None]:
    inner = _transport_test or httpx.AsyncHTTPTransport(verify=True, retries=0)
    transport = _TransportEpingle(inner, hote, resolution.ip_connexion)
    timeout = httpx.Timeout(TIMEOUT_READ, connect=TIMEOUT_CONNECT, write=3, pool=3)
    headers = {"User-Agent": "BEA-DIGITAL-Studio-Test/1.0", "Accept": "application/json, text/plain;q=0.5"}
    try:
        async with httpx.AsyncClient(
            transport=transport, timeout=timeout, follow_redirects=False,
            trust_env=False, headers=headers,
        ) as client:
            reponse = await client.request(methode, url)
    except RefusSsrf:
        raise
    except httpx.TimeoutException as exc:
        raise _erreur("Délai d'attente dépassé", "TIMEOUT", 504) from exc
    except httpx.ConnectError as exc:
        msg = str(exc).lower()
        if "certificate" in msg or "ssl" in msg or "tls" in msg:
            raise _erreur("Échec de la validation TLS", "TLS", 502) from exc
        raise _erreur("Connexion impossible", "TLS", 502) from exc
    except httpx.RequestError as exc:
        raise _erreur("Réponse ou protocole invalide", "RESEAU", 502) from exc

    if reponse.is_redirect:
        return "redirection_refusee", reponse.status_code, {
            "type_contenu": reponse.headers.get("content-type"),
            "taille": 0, "extrait": None, "entetes": _entetes_reponse(reponse.headers),
            "tronque": False, "redirection": reponse.headers.get("location"),
        }, "Redirection refusée : aucune requête n'a été envoyée vers l'emplacement indiqué."

    contenu = b""
    async for chunk in reponse.aiter_bytes():
        contenu += chunk
        if len(contenu) > TAILLE_MAX:
            return "trop_volumineux", reponse.status_code, {
                "type_contenu": reponse.headers.get("content-type"),
                "taille": len(contenu), "extrait": None, "entetes": _entetes_reponse(reponse.headers),
                "tronque": True,
            }, "Réponse trop volumineuse : lecture interrompue."
    texte = _assainir(contenu.decode("utf-8", errors="replace"))
    resume = {
        "type_contenu": reponse.headers.get("content-type"),
        "taille": len(contenu), "extrait": texte or None,
        "entetes": _entetes_reponse(reponse.headers), "tronque": False,
    }
    return _statut_http(reponse.status_code, False), reponse.status_code, resume, None


async def executer(db: AsyncSession, actor: User, request: Request | None, **kwargs) -> dict:
    prep = await preparer(db, **kwargs)
    f, op, d = prep["fournisseur"], prep["operation"], prep["destination"]
    correlation = uuid.uuid4().hex[:16].upper()
    debut = time.monotonic()
    started = datetime.now(UTC)
    controles: dict[str, Any] = {
        "https": True, "hote_approuve": True, "redirections": False,
        "secrets_transmis": False, "jetons_internes": False,
    }
    limites = {"timeout_ms": TIMEOUT_TOTAL_MS, "taille_max": TAILLE_MAX, "extrait_max": EXTRAIT_MAX}
    statut, http_status, resume, message = "refuse_securite", None, None, None
    categorie = None
    quota_pris = False
    try:
        await _quota(actor.id, f.id)
        quota_pris = True
        try:
            resolution = resoudre(prep["hote"], getaddrinfo=_getaddrinfo_test or __import__("socket").getaddrinfo)
        except RefusSsrf as exc:
            raise _erreur(exc.message, exc.code) from exc
        controles["dns"] = list(resolution.ips)
        controles["ip_connexion"] = resolution.ip_connexion
        controles["ips_publiques"] = True
        url = construire_url(hote=prep["hote"], port=prep["port"], chemin=prep["chemin"], requete=prep["requete"])
        statut, http_status, resume, message = await _appeler(url, op.methode, prep["hote"], resolution)
        categorie = None if statut == "succes" else statut
    except AppError as exc:
        statut = {
            "TIMEOUT": "timeout", "TLS": "tls", "DNS": "dns", "IP_INTERDITE": "refuse_securite",
            "HOTE_INTERDIT": "refuse_securite", "HOTE_INVALIDE": "refuse_securite",
            "HOTE_AMBIGU": "refuse_securite", "PORT_INTERDIT": "refuse_securite",
            "URL_IDENTIFIANTS": "refuse_securite", "SECRET_REQUIS": "secret_requis",
            "QUOTA": "quota", "QUOTA_INDISPONIBLE": "quota", "RESEAU": "reponse_invalide",
        }.get(getattr(exc, "code", ""), "refuse_securite")
        categorie = getattr(exc, "code", None) or statut
        message = exc.message
        if statut == "refuse_securite":
            from app.services.integrations.supervision import ouvrir_alerte
            await ouvrir_alerte(
                db, "refus_securite", f"{d.id}:{categorie}", f.id, d.id, op.id,
                "Refus de sécurité lors d'un test.", {"code": categorie},
            )
    except RefusSsrf as exc:
        statut, categorie, message = "refuse_securite", exc.code, exc.message
    finally:
        if quota_pris:
            await _relacher_inflight()

    duree = int((time.monotonic() - debut) * 1000)
    row = IntegrationExecution(
        fournisseur_id=f.id, operation_id=op.id, destination_id=d.id,
        environnement="TEST", methode=op.methode, chemin=prep["chemin"],
        hote=prep["hote"], port=prep["port"], started_at=started, duree_ms=duree,
        statut=statut, http_status=http_status, erreur_categorie=categorie,
        correlation_id=correlation, user_id=actor.id, controles=controles,
        limites=limites, reponse_resume=resume, message=message,
    )
    db.add(row)
    await db.flush()
    await record_audit(
        db, user=actor, action="integration_test_execute", entity="integration_execution",
        entity_id=str(row.id), request=request,
        after={"statut": statut, "http_status": http_status, "correlation_id": correlation,
               "fournisseur_id": str(f.id), "destination_id": str(d.id)},
        module_code="core",
    )
    from app.services.integrations.supervision import evaluer_apres_execution
    await evaluer_apres_execution(db, row)
    return await execution_detail(db, row.id)


async def execution_detail(db: AsyncSession, eid: uuid.UUID) -> dict:
    row = await db.get(IntegrationExecution, eid)
    if row is None:
        raise _erreur("Exécution introuvable", "EXECUTION_INTROUVABLE", 404)
    f = await db.get(IntegrationFournisseur, row.fournisseur_id)
    op = await db.get(IntegrationFournisseurOperation, row.operation_id)
    d = await db.get(IntegrationDestination, row.destination_id)
    noms = await _noms(db, {row.user_id})
    return {
        "id": row.id, "correlation_id": row.correlation_id,
        "fournisseur_id": row.fournisseur_id, "fournisseur_nom": f.nom if f else None,
        "operation_id": row.operation_id, "methode": row.methode, "chemin": row.chemin,
        "operation_nom": op.nom if op else None,
        "destination_id": row.destination_id, "destination_nom": d.nom if d else None,
        "environnement": row.environnement, "hote": row.hote, "port": row.port,
        "started_at": row.started_at, "duree_ms": row.duree_ms, "statut": row.statut,
        "http_status": row.http_status, "erreur_categorie": row.erreur_categorie,
        "acteur": _personne(noms, row.user_id),
        "controles": row.controles, "limites": row.limites,
        "reponse": row.reponse_resume, "message": row.message,
        "disponibilite": disponibilite_depuis(row.statut, row.started_at),
    }


def disponibilite_depuis(statut: str, started_at: datetime | None) -> str:
    if started_at is None:
        return "inconnue"
    if statut == "succes":
        return "disponible_dernier_test"
    if statut in {"http_erreur", "timeout", "tls", "dns", "trop_volumineux", "reponse_invalide"}:
        return "en_erreur"
    return "testee"
