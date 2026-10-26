"""Test de charge BEA DIGITAL — plateforme + modules, scénario en LECTURE SEULE.

Outil séparé : hors image Docker, hors `backend/requirements.txt`. Il vise
l'application par nginx (http://localhost), comme un vrai utilisateur.

Parcours d'un utilisateur virtuel :
  Login 1 → /auth/me (modules autorisés) → navigation plateforme
  (accueil, espaces, notifications) et, pour chaque module autorisé,
  Login 2 à la première visite puis consultations du module.

Lancement (depuis la racine du dépôt, venv activé) :

    $env:LOADTEST_EMAIL = "compte.test@bea.mr"
    $env:LOADTEST_PASSWORD = "..."
    $env:LOADTEST_MODULES = "immobilisations,stock-fournitures"   # optionnel
    locust -f loadtest/locustfile.py --host http://localhost

puis ouvrir http://localhost:8089.

Contraintes à connaître avant de lancer :

- Une seule PostgreSQL (vraies données) : uniquement des GET métier. Les
  connexions écrivent (sessions, `auth_login_attempts`, audit) ; chaque
  utilisateur virtuel se déconnecte à l'arrêt.
- Rate limit par IP (CORE ADMIN > Sécurité) : 300 requêtes API / min et
  20 connexions / min par défaut, partagés par tous les utilisateurs virtuels
  (même IP). Au-delà : 429 `RATE_LIMITED`, compté à part ("429 rate limit").
  Pour mesurer la capacité réelle, relever ces seuils en local uniquement.
- Chaque utilisateur fait 1 Login 1 + 1 Login 2 par module visité : garder un
  spawn rate bas (≈ 0,1 utilisateur/s) ou restreindre LOADTEST_MODULES.
- Compte de test sans 2FA, avec les grants espace / module à tester.
"""

from __future__ import annotations

import logging
import os
import random
import time
from datetime import date

from locust import HttpUser, between, events, task
from locust.exception import StopUser

API = "/api/v1"
TOKEN_REFRESH_SECONDS = 12 * 60

log = logging.getLogger("bea.loadtest")
_deja_signale: set[str] = set()


def _signaler_une_fois(message: str) -> None:
    if message not in _deja_signale:
        _deja_signale.add(message)
        log.error(message)


def _corps_erreur(r) -> dict:
    try:
        body = r.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _message_serveur(r) -> str:
    body = _corps_erreur(r)
    detail = body.get("message") or body.get("user_message") or body.get("detail")
    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("code")
    texte = detail if isinstance(detail, str) else (r.text[:200] if not detail else str(detail)[:200])
    code = body.get("code") or (detail.get("code") if isinstance(body.get("detail"), dict) else None)
    req = body.get("request_id") or r.headers.get("X-Request-ID")
    parties = [p for p in (f"HTTP {r.status_code}", f"code={code}" if code else None, f"req={req}" if req else None, texte) if p]
    return " | ".join(parties)

# Consultations par module (code module → [(chemin, paramètres)]).
# Uniquement des lectures légères : pas d'exports, pas d'endpoints qui
# journalisent chaque consultation.
MODULES: dict[str, list[tuple[str, dict]]] = {
    "immobilisations": [
        ("/immobilisations", {"page": 1, "size": 20}),
        ("/immobilisations", {"search": "ordinateur", "size": 20}),
        ("/dashboard/kpi", {}),
        ("/dashboard/charts", {}),
        ("/categories", {"size": 100}),
        ("/exercices/situation", {}),
        ("/reporting/recap-immobilisations", {"annee": date.today().year}),
    ],
    "clientele": [
        ("/clientele/config", {}),
        ("/clientele/tableau-de-bord", {}),
        ("/clientele/suivi/progression", {}),
    ],
    "reclamations": [
        ("/reclamations/config", {}),
        ("/reclamations/tableau-de-bord", {}),
        ("/reclamations/dossiers", {}),
    ],
    "formation": [
        ("/formation/config", {}),
        ("/formation/tableau-de-bord", {}),
        ("/formation/sessions", {}),
        ("/formation/employes", {}),
    ],
    "stock-fournitures": [
        ("/mg/stock/dashboard", {}),
        ("/mg/stock/articles", {}),
        ("/mg/stock/mouvements", {}),
        ("/mg/stock/alertes", {}),
    ],
    "demandes-mg": [
        ("/mg/requests/dashboard", {}),
        ("/mg/requests", {}),
    ],
    "achats-appro": [
        ("/mg/achats/dashboard", {}),
        ("/mg/achats/demandes", {}),
        ("/mg/achats/bons", {}),
    ],
    "notes-frais": [
        ("/mg/notes-frais/dashboard", {}),
        ("/mg/notes-frais/notes", {}),
    ],
    "contrats-echeances": [
        ("/mg/contrats/dashboard", {}),
        ("/mg/contrats", {}),
        ("/mg/contrats/echeances", {}),
    ],
    "facturation-fournisseurs": [
        ("/mg/factures/dashboard", {}),
        ("/mg/factures", {}),
    ],
    "archives-mg": [
        ("/mg/archives/dashboard", {}),
    ],
}


@events.init_command_line_parser.add_listener
def _add_args(parser) -> None:
    parser.add_argument("--bea-email", default=os.getenv("LOADTEST_EMAIL", ""), help="Compte de test")
    parser.add_argument(
        "--bea-password",
        default=os.getenv("LOADTEST_PASSWORD", ""),
        is_secret=True,
        help="Mot de passe du compte de test",
    )
    parser.add_argument(
        "--bea-modules",
        default=os.getenv("LOADTEST_MODULES", ""),
        help="Codes modules à tester, séparés par des virgules (défaut : tous ceux autorisés)",
    )


class UtilisateurBEA(HttpUser):
    wait_time = between(1, 5)

    def on_start(self) -> None:
        opts = self.environment.parsed_options
        self.email = opts.bea_email
        self.password = opts.bea_password
        demandes = {c.strip() for c in opts.bea_modules.split(",") if c.strip()}
        self.platform: dict[str, str] = {}
        self.platform_at = 0.0
        self.module_tokens: dict[str, tuple[dict[str, str], float]] = {}
        self.modules: list[str] = []
        if not self.email or not self.password:
            _signaler_une_fois("LOADTEST_EMAIL / LOADTEST_PASSWORD non définis : utilisateur virtuel arrêté.")
            self.actif = False
            return
        self.actif = self._login_platform()
        if not self.actif:
            return

        r = self._get("/auth/me", "auth/me")
        autorises = set(r.json().get("module_codes", [])) if r.ok else set()
        self.modules = sorted(autorises & MODULES.keys() & (demandes or MODULES.keys()))

    def on_stop(self) -> None:
        if self.platform:
            self.client.post(
                f"{API}/auth/logout",
                json={"refresh_token": self.platform["refresh_token"]},
                headers=self._bearer(self.platform),
                name="auth/logout",
            )

    # --- Authentification ----------------------------------------------------

    def _credentials(self) -> dict[str, str]:
        return {"email": self.email, "password": self.password}

    def _login_platform(self) -> bool:
        with self.client.post(
            f"{API}/auth/login", json=self._credentials(), name="auth/login (Login 1)", catch_response=True
        ) as r:
            if r.status_code != 200:
                r.failure(_message_serveur(r))
                conseil = {
                    422: "email ou mot de passe au mauvais format (email valide, mot de passe ≥ 8 caractères)",
                    401: "identifiants refusés (AUTH_INVALID_CREDENTIALS), 2FA requise (TOTP_REQUIRED) ou session",
                    429: "trop de tentatives (LOGIN_LOCKED 15 min ou RATE_LIMITED connexions — même IP pour tous les VU)",
                }.get(r.status_code, "voir les logs du backend (request_id)")
                _signaler_une_fois(
                    f"Login 1 refusé pour {self.email!r} — {_message_serveur(r)} "
                    f"→ {conseil}. Vérifier LOADTEST_EMAIL / LOADTEST_PASSWORD."
                )
                return False
            self.platform = r.json()
        self.platform_at = time.monotonic()
        self.module_tokens.clear()
        return True

    def _login_module(self, code: str) -> bool:
        with self.client.post(
            f"{API}/auth/modules/{code}/login",
            json=self._credentials(),
            headers=self._bearer(self.platform),
            name="auth/modules/{code}/login (Login 2)",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(_message_serveur(r))
                _signaler_une_fois(f"Login 2 {code} refusé — {_message_serveur(r)}")
                return False
            self.module_tokens[code] = (r.json(), time.monotonic())
            return True

    def _ensure_platform(self) -> None:
        if not self.actif:
            raise StopUser()
        if time.monotonic() - self.platform_at < TOKEN_REFRESH_SECONDS:
            return
        r = self.client.post(
            f"{API}/auth/refresh", json={"refresh_token": self.platform["refresh_token"]}, name="auth/refresh"
        )
        if r.status_code == 200:
            self.platform = r.json()
            self.platform_at = time.monotonic()
        elif not self._login_platform():
            self.actif = False
            raise StopUser()

    def _ensure_module(self, code: str) -> dict[str, str] | None:
        self._ensure_platform()
        entry = self.module_tokens.get(code)
        if entry and time.monotonic() - entry[1] >= TOKEN_REFRESH_SECONDS:
            r = self.client.post(
                f"{API}/auth/modules/refresh",
                json={"refresh_token": entry[0]["refresh_token"]},
                name="auth/modules/refresh",
            )
            entry = (r.json(), time.monotonic()) if r.status_code == 200 else None
            if entry:
                self.module_tokens[code] = entry
            else:
                self.module_tokens.pop(code, None)
        if entry is None and not self._login_module(code):
            return None
        return self.module_tokens[code][0]

    @staticmethod
    def _bearer(tokens: dict[str, str]) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens['access_token']}"}

    def _get(self, path: str, name: str, tokens: dict[str, str] | None = None, **params):
        with self.client.get(
            f"{API}{path}",
            params=params or None,
            headers=self._bearer(tokens or self.platform),
            name=name,
            catch_response=True,
        ) as r:
            if r.status_code == 429:
                r.failure(_message_serveur(r))
            elif r.status_code == 401:
                r.failure(_message_serveur(r))
                self.platform_at = 0.0
                self.module_tokens.clear()
            elif r.status_code not in {200, 204}:
                r.failure(_message_serveur(r))
            else:
                r.success()
            return r

    # --- Parcours -----------------------------------------------------------

    @task(3)
    def plateforme(self) -> None:
        self._ensure_platform()
        path = random.choice(["/plateforme/me/hub", "/plateforme/espaces", "/plateforme/catalogue", "/auth/me"])
        self._get(path, path.lstrip("/"))
        self._get("/notifications/unread-count", "notifications/unread-count")

    @task(7)
    def module(self) -> None:
        self._ensure_platform()
        if not self.modules:
            return
        code = random.choice(self.modules)
        tokens = self._ensure_module(code)
        if tokens is None:
            return
        for path, params in random.sample(MODULES[code], k=min(3, len(MODULES[code]))):
            self._get(path, f"[{code}] {path}", tokens, **params)
