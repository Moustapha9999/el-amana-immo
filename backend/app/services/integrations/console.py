"""Console de consultation en lecture seule.

La console n'est pas un proxy : elle n'accepte qu'un identifiant d'opération inscrit dans la
liste revue ``CONSOLE_OPERATIONS`` et des valeurs de paramètres déclarés. Le chemin est
reconstruit à partir du modèle de la route ; l'appel est fait en interne (ASGI, sans réseau)
avec le jeton de l'utilisateur, de sorte que les contrôles normaux de l'endpoint s'appliquent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI
from starlette.routing import Match

from app.services.integrations.catalogue import (
    AUTH_LOGIN1,
    PERM_IDENTIFIEE,
    SCHEMA_EXPLICITE,
    Operation,
)

TAILLE_MAX_OCTETS = 256 * 1024
DELAI_MAX_SECONDES = 10.0
MAX_PARAMETRES = 20
MAX_LONGUEUR_VALEUR = 200
MASQUE = "•••• (masqué)"
HOTE_INTERNE = "console.interne"


class _SansAppelConsole(logging.Filter):
    """httpx journalise l'URL complète (paramètres compris) en INFO : rien de la console ne doit y figurer."""

    def filter(self, record: logging.LogRecord) -> bool:
        return HOTE_INTERNE not in record.getMessage()


for _nom in ("httpx", "httpcore"):
    logging.getLogger(_nom).addFilter(_SansAppelConsole())

# Liste revue : GET internes, lecture seule (aucun seed ni écriture dans le traitement),
# volume borné (pagination ≤ 100), sans donnée personnelle dans la réponse.
CONSOLE_OPERATIONS: dict[str, str] = {
    "get.core_admin_integrations.lister_catalogue": (
        "Catalogue du Studio : métadonnées des routes, paginé (100 au plus), aucune écriture."
    ),
    "get.core_admin_integrations.fiche_operation": (
        "Fiche d'une opération du catalogue : métadonnées seulement, aucune écriture."
    ),
    "get.core_admin_catalogue.list_modules": (
        "Liste paginée des modules (100 au plus) : codes, libellés, statuts et compteurs agrégés ; lecture seule."
    ),
    "get.core_admin_catalogue.list_departments": (
        "Liste paginée des départements (100 au plus) : codes, libellés, statuts et compteurs agrégés ; lecture seule."
    ),
}

_VALEUR_CHEMIN = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")
_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_JWT = re.compile(r"^eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*$")
_JETONS_SENSIBLES = {
    "password", "passwd", "pwd", "secret", "token", "jeton", "authorization", "cookie", "totp", "otp",
    "iban", "rib", "cvv", "email", "courriel", "phone", "telephone", "mobile", "nni", "cin", "passport",
    "passeport", "ip", "hash", "hashed",
}
_FRAGMENTS_SENSIBLES = (
    "mot_de_passe", "motdepasse", "api_key", "apikey", "cle_api", "user_agent", "date_naissance",
    "numero_compte", "account_number", "card_number", "session_id", "refresh", "private_key",
)


class ConsoleRefus(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def eligibilite(op: Operation) -> tuple[bool, str | None]:
    """Admissible seulement si l'opération est revue ET si ses caractéristiques réelles le confirment."""
    if op.operation_id not in CONSOLE_OPERATIONS:
        return False, "Hors liste d'autorisation revue de la console."
    if op.methode != "GET":
        return False, "Seules les opérations GET sont autorisées dans la console."
    if op.authentification != AUTH_LOGIN1:
        return False, "La console n'utilise que la session BEA DIGITAL (Login 1)."
    if op.permission_statut != PERM_IDENTIFIEE:
        return False, "Permission de l'opération non identifiée."
    if op.schema_reponse_statut != SCHEMA_EXPLICITE:
        return False, "Schéma de réponse non documenté."
    if not op.dans_openapi:
        return False, "Opération absente du schéma OpenAPI."
    return True, None


def ids_console(index: dict[str, Operation]) -> set[str]:
    return {op_id for op_id, op in index.items() if eligibilite(op)[0]}


def parametres_console(op: Operation) -> list[dict]:
    return [p for p in op.parametres if p["emplacement"] in ("path", "query")]


def _cle_sensible(key: str) -> bool:
    k = key.lower()
    if any(fragment in k for fragment in _FRAGMENTS_SENSIBLES):
        return True
    return any(part in _JETONS_SENSIBLES for part in re.split(r"[_\-.\s]+", k) if part)


def masquer(value: Any) -> tuple[Any, int]:
    """Masque récursivement les champs sensibles ; renvoie la valeur masquée et le nombre de champs masqués."""
    if isinstance(value, dict):
        total = 0
        out = {}
        for key, item in value.items():
            if _cle_sensible(str(key)) and item not in (None, "", [], {}):
                out[key] = MASQUE
                total += 1
            else:
                out[key], n = masquer(item)
                total += n
        return out, total
    if isinstance(value, list):
        total = 0
        out_list = []
        for item in value:
            masked, n = masquer(item)
            out_list.append(masked)
            total += n
        return out_list, total
    if isinstance(value, str) and _JWT.match(value):
        return MASQUE, 1
    return value, 0


def _valider_valeur(nom: str, valeur: Any) -> str:
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, int | float):
        return str(valeur)
    if not isinstance(valeur, str):
        raise ConsoleRefus(400, "CONSOLE_PARAMETRE_INVALIDE", f"Valeur non prise en charge pour « {nom} ».")
    if len(valeur) > MAX_LONGUEUR_VALEUR or _CONTROLE.search(valeur):
        raise ConsoleRefus(400, "CONSOLE_PARAMETRE_INVALIDE", f"Valeur invalide pour « {nom} ».")
    return valeur


def construire_chemin(op: Operation, parametres_chemin: dict[str, str]) -> str:
    attendus = {p["nom"] for p in op.parametres if p["emplacement"] == "path"}
    if set(parametres_chemin) != attendus:
        raise ConsoleRefus(
            400,
            "CONSOLE_PARAMETRE_INVALIDE",
            "Paramètres de chemin attendus : " + (", ".join(sorted(attendus)) or "aucun") + ".",
        )
    chemin = op.route.path_format
    for nom, valeur in parametres_chemin.items():
        if not isinstance(valeur, str) or not _VALEUR_CHEMIN.match(valeur):
            raise ConsoleRefus(400, "CONSOLE_PARAMETRE_INVALIDE", f"Valeur de chemin invalide pour « {nom} ».")
        chemin = chemin.replace("{" + nom + "}", quote(valeur, safe=""))
    return chemin


def construire_requete(op: Operation, parametres_requete: dict[str, Any]) -> list[tuple[str, str]]:
    declares = {p["nom"] for p in op.parametres if p["emplacement"] == "query"}
    inconnus = sorted(set(parametres_requete) - declares)
    if inconnus:
        raise ConsoleRefus(400, "CONSOLE_PARAMETRE_INVALIDE", f"Paramètre non déclaré : « {inconnus[0]} ».")
    paires: list[tuple[str, str]] = []
    for nom, valeur in parametres_requete.items():
        valeurs = valeur if isinstance(valeur, list) else [valeur]
        for item in valeurs:
            if item is None or item == "":
                continue
            paires.append((nom, _valider_valeur(nom, item)))
    if len(paires) > MAX_PARAMETRES:
        raise ConsoleRefus(400, "CONSOLE_PARAMETRE_INVALIDE", "Trop de paramètres.")
    return paires


def _verifier_routage(app: FastAPI, op: Operation, chemin: str) -> None:
    scope = {"type": "http", "path": chemin, "method": "GET", "root_path": ""}
    for route in app.router.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            if route is not op.route:
                raise ConsoleRefus(400, "CONSOLE_ROUTAGE_INCOHERENT", "Le chemin construit ne correspond pas à l'opération.")
            return
    raise ConsoleRefus(400, "CONSOLE_ROUTAGE_INCOHERENT", "Le chemin construit ne correspond à aucune route.")


async def executer(
    app: FastAPI,
    op: Operation,
    *,
    parametres_chemin: dict[str, str],
    parametres_requete: dict[str, Any],
    authorization: str | None,
    client_ip: str | None,
) -> dict:
    admissible, motif = eligibilite(op)
    if not admissible:
        raise ConsoleRefus(403, "CONSOLE_OPERATION_NON_AUTORISEE", motif or "Opération non autorisée.")
    if not authorization:
        raise ConsoleRefus(401, "UNAUTHENTICATED", "Non authentifié")
    chemin = construire_chemin(op, parametres_chemin)
    params = construire_requete(op, parametres_requete)
    _verifier_routage(app, op, chemin)

    transport = httpx.ASGITransport(app=app, client=(client_ip or "127.0.0.1", 0))
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(transport=transport, base_url=f"http://{HOTE_INTERNE}") as client:
            response = await asyncio.wait_for(
                client.get(
                    chemin,
                    params=params,
                    headers={"Authorization": authorization, "Accept": "application/json"},
                ),
                timeout=DELAI_MAX_SECONDES,
            )
    except TimeoutError as exc:
        raise ConsoleRefus(504, "CONSOLE_DELAI_DEPASSE", "Délai maximal de la console dépassé.") from exc
    duree_ms = round((time.perf_counter() - started) * 1000, 1)

    contenu = response.content
    taille = len(contenu)
    resultat = {
        "operation_id": op.operation_id,
        "methode": "GET",
        "chemin": chemin,
        "statut_http": response.status_code,
        "duree_ms": duree_ms,
        "taille_octets": taille,
        "tronquee": False,
        "corps": None,
        "champs_masques": 0,
        "request_id": response.headers.get("X-Request-ID"),
        "message": None,
    }
    if taille > TAILLE_MAX_OCTETS:
        resultat["tronquee"] = True
        resultat["message"] = f"Réponse non affichée : {taille} octets dépassent la limite de {TAILLE_MAX_OCTETS} octets."
        return resultat
    if "application/json" not in response.headers.get("content-type", ""):
        resultat["message"] = "Réponse non JSON : contenu non affiché."
        return resultat
    try:
        corps = json.loads(contenu) if contenu else None
    except ValueError:
        resultat["message"] = "Réponse JSON illisible : contenu non affiché."
        return resultat
    resultat["corps"], resultat["champs_masques"] = masquer(corps)
    return resultat
