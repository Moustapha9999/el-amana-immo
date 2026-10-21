# Sécurité BEA-DIGITAL — architecture, procédures, checklist serveur

Document de référence du **centre de contrôle** CORE ADMIN → Paramètres → Sécurité.
La sécurité réelle est appliquée côté backend, base et infrastructure — jamais uniquement côté frontend.

## 1. Architecture actuelle (défense en profondeur)

```
Internet
  → Reverse proxy / TLS (à configurer en TEST/PROD)
  → nginx (frontend Docker, port 80 en local)
  → FastAPI `/api/v1` (auth, rate-limit, headers, RBAC)
  → PostgreSQL 17 (volume `bea_postgres_data`)
  → Stockage fichiers (`storage/uploads`, `storage/ged`)
  → audit_logs + alertes login + backups/recovery
```

### Couches déjà en place

| Couche | Mécanisme |
|--------|-----------|
| Login 1 / Login 2 | Sessions `auth_sessions` parent/enfant, JWT HS256, révocation serveur |
| Lockout | `auth_login_attempts` — échecs / fenêtre (politique DB) |
| Rate limit | Middleware mémoire (Login, API, sensible, reset) |
| Headers | `X-Content-Type-Options`, `X-Frame-Options`, CSP, HSTS hors local |
| MDP | bcrypt + politique éditable + historique N (migration) |
| MFA | TOTP ; secrets chiffrés at-rest (`enc:v1:`) |
| CORE ADMIN | Permissions `core.admin.*`, Login 1 uniquement |
| Reset MDP | **Centralisé** CORE ADMIN → Sécurité (public forgot/reset **désactivés**) |
| Audit | `audit_logs` |
| Backups | Continuité → Sauvegardes / Recovery |

## 2. Variables d’environnement critiques

- `SECRET_KEY` — **jamais** `change-me` en TEST/PROD
- `DATABASE_URL` / `POSTGRES_PASSWORD`
- `DATABASE_SSL` / `DATABASE_SSL_VERIFY` (prod)
- `CORS_ORIGINS` (liste stricte)
- `APP_DEBUG=false` en prod
- `APP_ENV=production`
- `SECURITY_HEADERS_ENABLED=true`
- Politique sécurité aussi en DB (`platform_ops_flags` / `security_policy`)

Ne jamais committer `.env`, `.env.docker`, dumps, clés.

### IP cliente (rate limiting, audit, tentatives de connexion, erreurs API)

Une seule fonction : `get_client_ip` (`backend/app/core/request_client.py`), utilisée par le
rate limiting, `auth_login_attempts`, `auth_sessions`, `audit_logs`, `api_error_events` et les
contextes des modules.

- Point de départ : le pair réseau (`request.client.host`).
- `X-Forwarded-For` / `X-Real-IP` ne sont lus **que** si ce pair figure dans `TRUSTED_PROXIES`
  (IP, CIDR ou nom de service Docker, résolu avec un cache de 30 s). Vide = aucun en-tête lu.
- `X-Forwarded-For` est remonté **de droite à gauche** tant que l'adresse courante est un proxy
  de confiance ; le premier saut non fiable est l'IP cliente. Le premier élément (fourni par le
  navigateur) n'est jamais pris d'office. Un élément mal formé arrête la remontée.
- Jamais `0.0.0.0/0` ni un réseau public dans `TRUSTED_PROXIES`.

| Environnement | Chaîne | `TRUSTED_PROXIES` |
|---------------|--------|-------------------|
| Local hors Docker (`ng serve` + uvicorn) | navigateur → proxy Angular (127.0.0.1) → uvicorn | vide (uvicorn relit déjà `X-Forwarded-For` depuis 127.0.0.1, `FORWARDED_ALLOW_IPS`) |
| Local Docker (`docker-compose.yml`, `.dev.yml`) | navigateur → nginx `frontend` → backend | `frontend` (défaut du compose) |
| TEST / PROD (`deployment/`) | navigateur → reverse proxy HTTPS hôte → nginx `frontend` → backend | `frontend,<adresse du reverse proxy vue par le conteneur frontend>` (à relever par l'IT) |

Sans l'adresse du reverse proxy hôte en TEST/PROD, l'IP retenue est celle de ce proxy pour tous
les agents : pas de falsification possible, mais un compteur de rate limiting commun.

## 3. Checklist serveur (intervention manuelle)

### HTTPS / TLS

- [ ] Certificat valide devant nginx (ou reverse proxy banque)
- [ ] Redirection HTTP → HTTPS
- [ ] Cookies Secure / HttpOnly / SameSite si cookies introduits plus tard
- [ ] HSTS activé une fois HTTPS stable

### Réseau

- [ ] PostgreSQL **non** exposé à Internet (compose local mappe 5432 — à fermer en prod)
- [ ] Seuls 80/443 publics
- [ ] Firewall : deny by default

### PostgreSQL

- [ ] Compte applicatif **non-superuser**
- [ ] SSL vers la base en TEST/PROD
- [ ] Backups planifiés + copie hors serveur
- [ ] Volume unique `bea_postgres_data` — **jamais** `docker compose down -v`

### GED / fichiers

- [ ] Monter `storage/ged` en compose si utilisé
- [ ] Permissions filesystem restrictives
- [ ] Uploads via API authentifiée uniquement (pas de serve static public)

### Rate-limit distribué (option)

- [ ] Redis partagé si multi-workers / multi-instances
- [ ] Aujourd’hui : rate-limit **in-process** (reset au restart)

### SMTP (option futur)

- [ ] Configurer SMTP avant de réactiver forgot/reset publics
- [ ] Utiliser table `password_reset_jtis` pour anti-rejeu

### SSH / OS

- [ ] Clés SSH, pas de root password
- [ ] Mises à jour sécurité OS
- [ ] Services inutiles désactivés
- [ ] Surveillance disque / logs

## 4. Migration schéma sécurité

Révision Alembic : `20260919_security_hardening`

- `password_history`
- `security_incidents`
- `password_reset_jtis`
- élargissement `users.totp_secret`

**Rappel AGENTS.md** : ne pas lancer Alembic sur base vide ; appliquer après restore dump Supabase. Tant que `SKIP_MIGRATIONS=1`, les tables incidents/historique peuvent être absentes — le code dégrade gracieusement.

## 5. Procédure backup

1. CORE ADMIN → Continuité → Sauvegardes
2. Niveau global / département / module selon besoin
3. Avant maintenance, migration ou mise à jour : backup manuel
4. Vérifier statut `success` + taille
5. Auditer l’opération

## 6. Procédure recovery

1. Vérifier le backup (intégrité / date)
2. Analyser dépendances (ne pas écraser CORE)
3. Recovery crée un backup de sécurité avant restauration
4. Confirmer
5. Exécuter
6. Vérifier application + audit

## 7. Procédure incident

```
Détection → Alerte → Identification → Containment
  → Révocation sessions si besoin → Analyse audit
  → Correction → Recovery si besoin → Vérification → Clôture
```

Enregistrer dans `security_incidents` (API `/plateforme/admin/settings/security/incidents`) ou ticket banque.

Mode maintenance : Continuité → Maintenance / État des modules.

## 8. Dépendances (supply chain)

Procédure recommandée :

1. Backup
2. `npm audit` / `pip-audit` (hors prod)
3. Mise à jour ciblée
4. Tests auth + immo amortissement (VNC)
5. Validation
6. Rollback image Docker si échec

Ne pas mettre à jour automatiquement une dépendance critique sans test.

## 9. Ce que CORE ADMIN n’affiche jamais

- JWT secret, DB password, clés, secrets MFA, tokens complets
- Uniquement statuts : Configuré / Non configuré / Non vérifié / À changer
- Secret ou jeton d’application cliente (aucun n’existe : M2M non activé)
- Secret fournisseur, mot de passe ou `Authorization` dans une fiche « API externes »

## 9 bis. Studio d’intégration API

- **M2M** : aucun jeton d’application n’est émis. Ne pas réutiliser les JWT
  utilisateurs ni `SECRET_KEY` comme secret universel. Décision DSI requise
  avant toute émission ([studio-integration-api.md](studio-integration-api.md) § 12).
- **API externes** : les URL et spécifications sont des métadonnées. Le parseur
  OpenAPI ne sort jamais du processus (pas de `$ref` distant, pas de
  téléchargement). Un exemple d’appel n’est pas une exécution.
- **Exécution (Phase 5)** : aucun proxy générique. L’URL est construite
  serveur (destination TEST approuvée + chemin d’opération). SSRF :
  HTTPS, pas de `userinfo`, DNS `is_global` sur toutes les adresses,
  épinglage IP + SNI, redirections refusées, timeouts et taille bornés.
  Pas de cookie ni jeton Login 1/2. Opérations authentifiées bloquées
  (pas de coffre de secrets approuvé). Quotas Redis fail-closed.
- **Supervision (Phase 6)** : historique technique sans secret ni corps
  complet ; alertes dédupliquées ; aucune sonde automatique ; export CSV
  neutralisé. Login 2 refusé.
- **Interface Studio** : menu filtré comme le serveur, accès direct sans
  permission = message explicite sans appel réseau ; aucune exécution sans
  aperçu puis confirmation, aperçu invalidé à toute modification ; aucune
  nouvelle fonction d’appel sortant ajoutée pour l’interface.
- **Suppressions Studio** : bilan des dépendances côté serveur, jamais de
  cascade, révision vérifiée, journal d’audit ; exécutions et alertes jamais
  supprimables (preuves) ; opérations importées non supprimables
  individuellement ([studio-integration-api.md](studio-integration-api.md) § 17).
- `python-jose` 3.3.0 signe les JWT **utilisateurs** uniquement (HS256,
  `algorithms` restreint). Ne pas l’étendre à un serveur d’autorisation M2M
  ni aux appels sortants.

## 10. Limite honnête

BEA-DIGITAL n’est **pas** « impossible à pirater ». Le centre affiche protections actives, contrôles, points **Non vérifiés** (HTTPS, réseau, serveur) et actions recommandées. La sécurité est un processus continu.
