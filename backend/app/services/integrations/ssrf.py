"""Protection SSRF pour les tests d'API externes (Phase 5).

Aucune confiance dans une URL fournie par le client ou une spécification importée.
L'hôte, le port et le protocole viennent d'une destination approuvée ; le chemin d'une
opération validée. La résolution DNS est filtrée : toute adresse non globale refuse l'appel.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode, urlsplit

HOTES_INTERDITS = frozenset({
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
    "metadata.google.internal", "metadata.google.com", "metadata",
    "kubernetes", "kubernetes.default", "kubernetes.default.svc",
})
SUFFIXES_INTERDITS = (".localhost", ".local", ".internal", ".intranet", ".corp", ".home", ".lan")
_HOTE = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
_LABEL_NUMERIQUE = re.compile(r"^\d+$")
PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_.-]+)\}")
_CHEMIN_SEG = re.compile(r"^[A-Za-z0-9._~!$&'()*+,;=:@%-]+$")


class RefusSsrf(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Resolution:
    hote: str
    ips: tuple[str, ...]
    ip_connexion: str
    interdites: tuple[str, ...] = field(default_factory=tuple)


def ip_interdite(adresse: str) -> bool:
    """True si l'adresse n'est pas une adresse unicast publique globale."""
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return True
    return (
        not ip.is_global
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_private
    )


def normaliser_hote(brut: str) -> str:
    if not isinstance(brut, str):
        raise RefusSsrf("HOTE_INVALIDE", "Nom d'hôte invalide.")
    hote = brut.strip().rstrip(".")
    if not hote or len(hote) > 253:
        raise RefusSsrf("HOTE_INVALIDE", "Nom d'hôte invalide.")
    if any(c in hote for c in "@/\\?# \t\n\r%"):
        raise RefusSsrf("HOTE_INVALIDE", "Nom d'hôte invalide.")
    if hote.startswith("[") and hote.endswith("]"):
        hote = hote[1:-1]
    try:
        ip = ipaddress.ip_address(hote)
    except ValueError:
        ip = None
    if ip is not None:
        if ip_interdite(str(ip)):
            raise RefusSsrf("IP_INTERDITE", "Adresse IP non publique interdite.")
        return str(ip)
    if _LABEL_NUMERIQUE.match(hote) or hote.lower().startswith("0x"):
        raise RefusSsrf("HOTE_AMBIGU", "Forme d'adresse interdite.")
    try:
        ascii_hote = hote.encode("idna").decode("ascii").lower()
    except (UnicodeError, UnicodeDecodeError) as exc:
        raise RefusSsrf("HOTE_INVALIDE", "Nom d'hôte invalide.") from exc
    if ascii_hote in HOTES_INTERDITS or any(ascii_hote.endswith(s) for s in SUFFIXES_INTERDITS):
        raise RefusSsrf("HOTE_INTERDIT", "Nom d'hôte réservé interdit.")
    if not _HOTE.match(ascii_hote) or ".." in ascii_hote:
        raise RefusSsrf("HOTE_INVALIDE", "Nom d'hôte invalide.")
    return ascii_hote


def normaliser_port(port: int | str, autorises: list[int]) -> int:
    try:
        n = int(port)
    except (TypeError, ValueError) as exc:
        raise RefusSsrf("PORT_INTERDIT", "Port invalide.") from exc
    if n not in autorises or not 1 <= n <= 65535:
        raise RefusSsrf("PORT_INTERDIT", "Port non autorisé.")
    return n


def resoudre(hote: str, *, getaddrinfo=socket.getaddrinfo) -> Resolution:
    hote = normaliser_hote(hote)
    try:
        infos = getaddrinfo(hote, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RefusSsrf("DNS", "Résolution DNS impossible.") from exc
    vues: list[str] = []
    for info in infos:
        adresse = info[4][0]
        if adresse not in vues:
            vues.append(adresse)
    if not vues:
        raise RefusSsrf("DNS", "Aucune adresse résolue.")
    interdites = tuple(a for a in vues if ip_interdite(a))
    if interdites:
        raise RefusSsrf("IP_INTERDITE", "La résolution DNS a renvoyé une adresse non publique.")
    return Resolution(hote=hote, ips=tuple(vues), ip_connexion=vues[0], interdites=interdites)


def substituer_chemin(gabarit: str, valeurs: dict[str, str]) -> str:
    if not gabarit.startswith("/") or "//" in gabarit or "/../" in gabarit + "/" or "/./" in gabarit + "/":
        raise RefusSsrf("CHEMIN_INVALIDE", "Chemin d'opération invalide.")
    if any(c in gabarit for c in " ?#\\"):
        raise RefusSsrf("CHEMIN_INVALIDE", "Chemin d'opération invalide.")
    places = PLACEHOLDER.findall(gabarit)
    if set(places) != set(valeurs) or len(places) != len(set(places)):
        raise RefusSsrf("PARAMETRE_CHEMIN", "Chaque paramètre de chemin doit être fourni une fois.")

    def remp(m: re.Match[str]) -> str:
        v = valeurs[m.group(1)]
        if not v or any(c in v for c in "/?#\\") or not _CHEMIN_SEG.match(v):
            raise RefusSsrf("PARAMETRE_CHEMIN", "Valeur de chemin refusée.")
        return quote(v, safe="._~-")

    return PLACEHOLDER.sub(remp, gabarit)


def construire_url(*, hote: str, port: int, chemin: str, requete: dict[str, str] | None = None) -> str:
    hote = normaliser_hote(hote)
    if ip_interdite(hote) if _est_ip(hote) else False:
        raise RefusSsrf("IP_INTERDITE", "Adresse IP non publique interdite.")
    if not chemin.startswith("/") or any(c in chemin for c in " ?#\\"):
        raise RefusSsrf("CHEMIN_INVALIDE", "Chemin d'opération invalide.")
    autorite = f"{hote}:{port}" if port != 443 else hote
    url = f"https://{autorite}{chemin}"
    if requete:
        url += "?" + urlencode([(k, v) for k, v in requete.items() if v is not None], doseq=False)
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password or "@" in (parts.netloc or ""):
        raise RefusSsrf("URL_IDENTIFIANTS", "Identifiants dans l'URL interdits.")
    if parts.hostname != hote:
        raise RefusSsrf("HOTE_INVALIDE", "Hôte de l'URL différent de la destination.")
    return url


def _est_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False
