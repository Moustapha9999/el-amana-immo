"""Test de charge BEA DIGITAL — plateforme + modules.

Lecture seule par défaut. --bea-writes (ou LOADTEST_WRITES=1) ajoute des écritures
concurrentes : entrées/sorties de stock sur les mêmes articles, création de demandes.
Chaque écriture acceptée est journalisée (LOADTEST_JOURNAL) pour le contrôle d'intégrité.

Outil séparé : hors image Docker, hors `backend/requirements.txt`. Il vise
l'application par nginx (http://localhost), comme un vrai utilisateur.

Parcours d'un utilisateur virtuel :
  Login 1 → /auth/me (modules autorisés) → navigation plateforme
  (accueil, espaces, notifications) et, pour chaque module autorisé,
  Login 2 à la première visite puis consultations du module.

Cible : UNIQUEMENT l'environnement de charge isolé (loadtest/setup-env.ps1),
http://127.0.0.1:8081 — base bea_digital_loadtest, données synthétiques. Toute
autre cible (dont http://localhost, qui sert les vraies données) est refusée,
sauf hôte ajouté explicitement dans LOADTEST_ALLOWED_HOSTS.

Lancement : loadtest/run-locust.ps1 (paliers, rapports et logs) ou

    $env:LOADTEST_PASSWORD = "..."          # loadtest/.env.loadtest
    locust -f loadtest/locustfile.py --host http://127.0.0.1:8081

Comptes : un compte synthétique distinct par utilisateur virtuel
(lt.<profil>.<n>@loadtest.example.com), répartis selon --bea-profiles
(défaut mg:40,compta:30,employe:80). --bea-email force un compte unique.

- Lecture : GET métier. Écriture (optionnelle) : POST /mg/stock/entrees, /sorties,
  /me/requests. Les connexions écrivent aussi (sessions, audit).
- Chaque utilisateur virtuel se déconnecte à l'arrêt.
- Rate limit par IP : tous les utilisateurs virtuels partagent l'IP du poste ;
  l'environnement de charge relève les seuils (RATE_LIMIT_* dans le compose).
- Chaque utilisateur fait 1 Login 1 + 1 Login 2 par module visité (bcrypt) :
  monter progressivement (spawn rate ≈ 1 utilisateur/s).
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import random
import threading
import time
import uuid
from datetime import date

from locust import HttpUser, between, events, task
from locust.exception import StopUser

API = "/api/v1"
TOKEN_REFRESH_SECONDS = 12 * 60
HOTES_AUTORISES = {"http://127.0.0.1:8081", "http://localhost:8081"}
DOMAINE_TEST = "loadtest.example.com"

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

# Parcours demandeur (« mes demandes ») : sans mg.request.view, les routes /mg/requests
# répondent 403 — l'application envoie ces comptes sur /me/requests.
ROUTES_DEMANDEUR: list[tuple[str, dict]] = [
    ("/me/requests/dashboard", {}),
    ("/me/requests", {}),
    ("/me/requests/categories", {}),
]
MODULES_DEMANDES = {"demandes-mg"}
MARQUE_ECRITURE = "LT-CHARGE"
NB_ARTICLES_CHAUDS = 8

_refs_lock = threading.Lock()
_refs: dict = {
    "articles": [],
    "motif_entree": None,
    "motif_sortie": None,
    "categories": [],
    "pret": False,
}
_journal_lock = threading.Lock()


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
    parser.add_argument(
        "--bea-profiles",
        default=os.getenv("LOADTEST_PROFILES", "mg:40,compta:30,employe:80"),
        help="Comptes synthétiques profil:nombre (lt.<profil>.<n>@loadtest.example.com)",
    )
    parser.add_argument(
        "--bea-writes",
        action="store_true",
        default=os.getenv("LOADTEST_WRITES", "").strip().lower() in {"1", "true", "oui"},
        help="Écritures concurrentes (stock + demandes) + journal d'intégrité",
    )


def _cible_autorisee(hote: str | None) -> bool:
    autorises = HOTES_AUTORISES | {
        h.strip().rstrip("/") for h in os.getenv("LOADTEST_ALLOWED_HOSTS", "").split(",") if h.strip()
    }
    return (hote or "").rstrip("/") in autorises


@events.test_start.add_listener
def _verifier_cible(environment, **_kw) -> None:
    if not _cible_autorisee(environment.host):
        log.error("Cible %r refusée : seul l'environnement de charge isolé est autorisé (%s).",
                  environment.host, ", ".join(sorted(HOTES_AUTORISES)))
        environment.process_exit_code = 1
        if environment.runner is not None:
            environment.runner.quit()


def _comptes(profils: str) -> list[str]:
    """Comptes entrelacés au prorata des profils : chaque palier garde la même répartition."""
    listes = []
    for item in profils.split(","):
        profil, _, nombre = item.strip().partition(":")
        if profil and nombre.isdigit():
            listes.append([f"lt.{profil}.{n:03d}@{DOMAINE_TEST}" for n in range(1, int(nombre) + 1)])
    total = sum(len(lst) for lst in listes)
    poses = sorted(
        ((i + 0.5) / len(lst), email) for lst in listes for i, email in enumerate(lst)
    ) if total else []
    return [email for _, email in poses]


_attribution_lock = threading.Lock()
_attribution: itertools.cycle | None = None


def _ecritures_actives(opts) -> bool:
    return bool(getattr(opts, "bea_writes", False))


def _journaliser(entree: dict) -> None:
    chemin = os.getenv("LOADTEST_JOURNAL", "")
    if not chemin:
        return
    with _journal_lock:
        with open(chemin, "a", encoding="utf-8") as f:
            f.write(json.dumps(entree, ensure_ascii=False) + "\n")


def _prochain_compte(profils: str) -> str:
    global _attribution
    with _attribution_lock:
        if _attribution is None:
            comptes = _comptes(profils)
            if not comptes:
                return ""
            _attribution = itertools.cycle(comptes)
        return next(_attribution)


class UtilisateurBEA(HttpUser):
    wait_time = between(1, 5)

    def on_start(self) -> None:
        opts = self.environment.parsed_options
        self.email = opts.bea_email or _prochain_compte(opts.bea_profiles)
        self.password = opts.bea_password
        demandes = {c.strip() for c in opts.bea_modules.split(",") if c.strip()}
        self.platform: dict[str, str] = {}
        self.platform_at = 0.0
        self.module_tokens: dict[str, tuple[dict[str, str], float]] = {}
        self.modules: list[str] = []
        self.routes: dict[str, list[tuple[str, dict]]] = {}
        self.agence_id = None
        self.peut_entrer = self.peut_sortir = self.peut_demander = False
        self.ecrit = False
        if not _cible_autorisee(self.host):
            _signaler_une_fois(f"Cible {self.host!r} refusée : environnement de charge isolé uniquement.")
            self.actif = False
            return
        if not self.email or not self.password:
            _signaler_une_fois("LOADTEST_EMAIL / LOADTEST_PASSWORD non définis : utilisateur virtuel arrêté.")
            self.actif = False
            return
        self.actif = self._login_platform()
        if not self.actif:
            return

        r = self._get("/auth/me", "auth/me")
        moi = r.json() if r.ok else {}
        autorises = set(moi.get("module_codes", []))
        traitant = "mg.request.view" in moi.get("permission_codes", [])
        self.modules = sorted(autorises & MODULES.keys() & (demandes or MODULES.keys()))
        self.routes = {
            code: ROUTES_DEMANDEUR if code in MODULES_DEMANDES and not traitant else MODULES[code]
            for code in self.modules
        }
        perms = set(moi.get("permission_codes", []))
        self.agence_id = moi.get("agence_id")
        self.peut_entrer = "mg.stock.entry" in perms
        self.peut_sortir = "mg.stock.exit" in perms
        self.peut_demander = "mg.request.mine.create" in perms
        self.ecrit = _ecritures_actives(opts)

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

    def _post(
        self,
        path: str,
        name: str,
        tokens: dict[str, str],
        body: dict,
        *,
        ok=(200, 201),
        attendus: set[str] | None = None,
        cle_idempotence: str | None = None,
    ):
        with self.client.post(
            f"{API}{path}",
            json=body,
            headers={
                **self._bearer(tokens),
                "Idempotency-Key": cle_idempotence or f"lt-{uuid.uuid4()}",
            },
            name=name,
            catch_response=True,
        ) as r:
            code = _corps_erreur(r).get("code") or ""
            if r.status_code in ok:
                r.success()
            elif attendus and (
                code in attendus
                or (r.status_code in {400, 409} and "stock" in (r.text or "").lower())
            ):
                r.success()
            else:
                r.failure(_message_serveur(r))
                if r.status_code == 401:
                    self.platform_at = 0.0
                    self.module_tokens.clear()
            return r

    def _charger_refs_stock(self, tokens: dict[str, str]) -> None:
        with _refs_lock:
            if _refs["pret"]:
                return
        entrees = self._get("/mg/stock/entrees/referentiels", "[stock] refs entrees", tokens)
        sorties = self._get("/mg/stock/sorties/referentiels", "[stock] refs sorties", tokens)
        if not entrees.ok or not sorties.ok:
            return
        e, s = entrees.json(), sorties.json()
        articles = sorted(e.get("articles") or [], key=lambda a: float(a.get("stock_actuel") or 0), reverse=True)
        chauds = articles[:NB_ARTICLES_CHAUDS]
        motif_e = next((m for m in (e.get("motifs") or []) if m.get("is_active")), None)
        motif_s = next((m for m in (s.get("motifs") or []) if m.get("is_active")), None)
        with _refs_lock:
            if not _refs["pret"] and chauds and motif_e and motif_s:
                _refs.update(articles=chauds, motif_entree=motif_e, motif_sortie=motif_s, pret=True)
                log.info("Écritures stock : %s articles chauds (%s)", len(chauds),
                         ", ".join(a.get("code", "?") for a in chauds))

    def _charger_refs_demandes(self, tokens: dict[str, str]) -> None:
        with _refs_lock:
            if _refs["categories"]:
                return
        r = self._get("/me/requests/categories", "[demandes-mg] /me/requests/categories", tokens)
        if r.ok:
            cats = [c for c in r.json() if c.get("active", True)]
            with _refs_lock:
                if not _refs["categories"] and cats:
                    _refs["categories"] = cats

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
        routes = self.routes[code]
        for path, params in random.sample(routes, k=min(3, len(routes))):
            self._get(path, f"[{code}] {path}", tokens, **params)

    @task(5)
    def ecrire_stock(self) -> None:
        if not getattr(self, "ecrit", False) or not (self.peut_entrer or self.peut_sortir):
            return
        tokens = self._ensure_module("stock-fournitures")
        if tokens is None:
            return
        self._charger_refs_stock(tokens)
        if not _refs["pret"]:
            return
        article = random.choice(_refs["articles"])
        marque = f"{MARQUE_ECRITURE} {uuid.uuid4()}"
        if self.peut_entrer and (not self.peut_sortir or random.random() < 0.7):
            body = {
                "article_id": article["id"],
                "quantite": random.randint(1, 5),
                "provenance_type": "AUTRE",
                "motif_id": _refs["motif_entree"]["id"],
                "observation": marque,
                "remis_par": self.email,
            }
            r = self._post("/mg/stock/entrees", "stock/entree", tokens, body)
            if r.status_code in {200, 201}:
                data = r.json()
                _journaliser({
                    "kind": "entree", "id": data.get("id"), "reference": data.get("reference"),
                    "article_id": data.get("article_id"), "quantite": str(data.get("quantite")),
                    "email": self.email,
                })
            return
        if not self.peut_sortir or not self.agence_id:
            return
        body = {
            "article_id": article["id"],
            "quantite": 1,
            "destination_type": "AGENCE",
            "agence_id": self.agence_id,
            "motif_id": _refs["motif_sortie"]["id"],
            "demandeur_nom": self.email,
            "observation": marque,
        }
        r = self._post(
            "/mg/stock/sorties",
            "stock/sortie",
            tokens,
            body,
            attendus={"STOCK_NEGATIF", "STOCK_MODIFIE"},
        )
        if r.status_code in {200, 201}:
            data = r.json()
            _journaliser({
                "kind": "sortie", "id": data.get("id"), "reference": data.get("reference"),
                "article_id": data.get("article_id"), "quantite": str(data.get("quantite")),
                "email": self.email,
            })
        elif r.status_code in {400, 409}:
            _journaliser({
                "kind": "refuse", "route": "sortie",
                "code": _corps_erreur(r).get("code") or str(r.status_code),
                "email": self.email,
            })

    @task(5)
    def creer_demande(self) -> None:
        if not getattr(self, "ecrit", False) or not self.peut_demander:
            return
        tokens = self._ensure_module("demandes-mg")
        if tokens is None:
            return
        self._charger_refs_demandes(tokens)
        cats = _refs["categories"]
        if not cats or not self.agence_id:
            return
        cat = random.choice(cats)
        titre = f"{MARQUE_ECRITURE} {uuid.uuid4()}"
        body = {
            "category_id": cat["id"],
            "agency_id": self.agence_id,
            "title": titre,
            "description": "Demande synthétique — test de charge concurrent.",
            "priority": "NORMALE",
            "items": [{"description": "Fournitures de test", "quantity": 1, "unit": "U"}],
        }
        r = self._post("/me/requests", "demandes/creation", tokens, body)
        if r.status_code in {200, 201}:
            data = r.json()
            _journaliser({
                "kind": "demande", "id": data.get("id"), "number": data.get("request_number"),
                "title": data.get("title"), "email": self.email,
            })
        elif r.status_code == 409:
            _journaliser({
                "kind": "refuse", "route": "demande",
                "code": _corps_erreur(r).get("code") or "DUPLICATE",
                "email": self.email,
            })

    @task(2)
    def double_soumission(self) -> None:
        """Deux POST identiques (même Idempotency-Key) = une seule opération."""
        if not getattr(self, "ecrit", False) or not self.peut_entrer:
            return
        tokens = self._ensure_module("stock-fournitures")
        if tokens is None:
            return
        self._charger_refs_stock(tokens)
        if not _refs["pret"]:
            return
        article = random.choice(_refs["articles"])
        marque = f"{MARQUE_ECRITURE} {uuid.uuid4()}"
        cle = f"lt-dbl-{uuid.uuid4()}"
        body = {
            "article_id": article["id"],
            "quantite": 1,
            "provenance_type": "AUTRE",
            "motif_id": _refs["motif_entree"]["id"],
            "observation": marque,
            "remis_par": self.email,
        }
        r1 = self._post("/mg/stock/entrees", "stock/entree (double-clic 1)", tokens, body, cle_idempotence=cle)
        r2 = self._post(
            "/mg/stock/entrees",
            "stock/entree (double-clic 2)",
            tokens,
            body,
            cle_idempotence=cle,
            attendus={"DUPLICATE"},
        )
        if r1.status_code not in {200, 201}:
            return
        data = r1.json()
        if r2.status_code in {200, 201}:
            autre = r2.json().get("id")
            if autre and autre != data.get("id"):
                _journaliser({
                    "kind": "refuse", "route": "double-clic",
                    "code": "DOUBLE_OPERATION",
                    "email": self.email,
                    "ids": [data.get("id"), autre],
                })
                return
        _journaliser({
            "kind": "entree", "id": data.get("id"), "reference": data.get("reference"),
            "article_id": data.get("article_id"), "quantite": str(data.get("quantite")),
            "email": self.email, "double_clic": True,
        })
