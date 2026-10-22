# Risques et recommandations — BEA DIGITAL

> Audit du 22/10/2026. Chaque risque s'appuie sur une preuve (fichier, configuration, observation).
> Aucun scan offensif. Distinction : **défaut avéré** (constaté), **risque potentiel** (conséquence
> plausible), **question ouverte** (à confirmer).

## 1. Synthèse des priorités

| ID | Risque | Nature | Priorité | Interlocuteur |
|---|---|---|---|---|
| R1 | Absence de HTTPS et ports de données exposés en local | Défaut avéré | Critique | DSI / réseau |
| R2 | Compte PostgreSQL superuser | Défaut avéré | Haute | DSI / DBA |
| R3 | Jetons JWT dans `localStorage` + HTTP | Défaut avéré | Haute | DSI / sécurité applicative |
| R4 | MFA CORE ADMIN non imposée, aucun compte enrôlé | Défaut avéré (instance locale) | Haute | Gouvernance CORE ADMIN |
| R5 | Sauvegardes uniquement sur le même hôte, sans copie externe | Défaut avéré (local) | Haute | DSI / exploitation |
| R6 | Restauration et SQL libre depuis l'interface CORE ADMIN | Défaut avéré | Haute | DSI / gouvernance |
| R7 | Pas d'environnement TEST / PROD, inventaire vide | Défaut avéré | Haute | DSI |
| R8 | Écart schéma / code si une instance n’applique pas les révisions Stock / notifications | Risque potentiel | Moyenne | Équipe BEA DIGITAL |
| R9 | `SECRET_KEY` unique, rotation destructive, démarrage non bloqué | Risque potentiel | Haute | DSI / sécurité |
| R10 | Journal d'accès structuré non émis ; pas de SIEM | Défaut avéré | Moyenne | DSI / exploitation |
| R11 | Rate limiting non distribué | Risque potentiel | Moyenne | Équipe BEA DIGITAL |
| R12 | Redis sans authentification | Risque potentiel | Moyenne | DSI / réseau |
| R13 | `python-jose` 3.3.0 peu maintenu | Risque potentiel | Moyenne | Équipe BEA DIGITAL |
| R14 | CI sans PostgreSQL, 7 tests frontend, 5 échecs historiques | Défaut avéré | Moyenne | Équipe BEA DIGITAL |
| R15 | Antivirus et SMTP non configurés | Question ouverte | Moyenne | DSI |
| R16 | Conservation des données personnelles non définie | Question ouverte | Haute | Conformité / DSI |
| R17 | Intégration ORION uniquement manuelle | Question ouverte | Haute | DSI / métier |
| R18 | Dette `app/` + `alembic/` racine, Material/Tailwind | Défaut avéré | Basse | Équipe BEA DIGITAL |

## 2. Fiches

### R1 — Exposition réseau (HTTPS absent, ports de données ouverts)

- **Constat** : l'instance locale écoute en HTTP sur le port 80, PostgreSQL sur 5432 et pgAdmin
  sur 5050, **toutes interfaces** (`0.0.0.0`).
- **Preuve** : `docker ps` du 22/10/2026 ; `curl http://localhost/health` sans TLS.
- **Impact** : interception des identifiants et jetons sur le réseau local ; accès direct à la base
  (superuser) et à pgAdmin depuis tout poste joignant l'hôte.
- **Priorité** : critique.
- **Recommandation** : restreindre 5432 et 5050 à `127.0.0.1` immédiatement sur toute instance
  Windows ; ne pas exposer PostgreSQL ni pgAdmin hors de l'hôte. En TEST/PROD, appliquer le compose
  prévu (ports internes uniquement) derrière un reverse proxy HTTPS géré par l'IT. Remplir
  `docs/deployment/00-inventaire-bea.md`.
- **Interlocuteur** : DSI / réseau.

### R2 — Compte applicatif PostgreSQL superuser

- **Constat** : `rolsuper = t` pour l'utilisateur courant de la base locale.
- **Preuve** : `SELECT rolsuper FROM pg_roles WHERE rolname = current_user`.
- **Impact** : une injection SQL ou une utilisation du mode administrateur de CORE QUERY donne un
  accès DBA (lecture des secrets, modification des journaux, `DROP DATABASE`).
- **Priorité** : haute.
- **Recommandation** : compte applicatif non superuser, droits `SELECT/INSERT/UPDATE/DELETE`
  (et `CREATE` limité si nécessaire) ; rôle `bea_core_query_reader` déjà prévu ; envisager RLS
  ensuite (`docs/conformite/README.md`).
- **Interlocuteur** : DSI / DBA.

### R3 — Jetons dans `localStorage` sur un canal HTTP

- **Constat** : access et refresh tokens stockés dans `localStorage` ; canal HTTP en local.
- **Preuve** : `frontend/angular20/src/app/core/services/auth.service.ts` ; `curl` HTTP.
- **Impact** : vol de session par XSS (la SPA n'a pas de CSP) ou par écoute réseau.
- **Priorité** : haute.
- **Recommandation** : HTTPS obligatoire avant toute mise en TEST/PROD ; ajouter une CSP
  concrète sur nginx ; évaluer cookies `HttpOnly` + `Secure` + `SameSite` (évolution à concevoir,
  aujourd'hui tout est Bearer).
- **Interlocuteur** : DSI / sécurité applicative.

### R4 — MFA non imposée

- **Constat** : politique locale `mfa_required_for_core_admin = false` ; 0 utilisateur actif avec
  TOTP activé ; 1 superuser.
- **Preuve** : `platform_ops_flags.security_policy` et agrégat `users` (lecture seule).
- **Impact** : un mot de passe unique ouvre CORE ADMIN (SQL libre, restauration).
- **Priorité** : haute.
- **Recommandation** : activer `MFA_REQUIRED_FOR_CORE_ADMIN` (déjà `true` dans le modèle de
  production) et enrôler tous les administrateurs avant ouverture.
- **Interlocuteur** : gouvernance CORE ADMIN.

### R5 — Sauvegardes sur le même disque

- **Constat** : 201 fichiers dans `backups/` du poste (616 Mo), mêmes montages que PostgreSQL.
  Aucune copie hors serveur documentée.
- **Preuve** : listing `backups/` (métadonnées) ; `docs/deployment/00-inventaire-bea.md` vide.
- **Impact** : perte simultanée de la base et des sauvegardes (panne disque, rançongiciel, `docker
  compose down -v`).
- **Priorité** : haute.
- **Recommandation** : réplication hors serveur, chiffrement, test de restauration périodique,
  politique de rétention écrite. Ne jamais lancer `docker compose down -v`.
- **Interlocuteur** : DSI / exploitation.

### R6 — Pouvoirs de restauration et SQL libre dans CORE ADMIN

- **Constat** : un détenteur de `core.admin.query.admin` exécute du SQL (y compris DDL) avec le
  compte superuser ; un détenteur des permissions de sauvegarde télécharge et restaure un dump.
- **Preuve** : `docs/core-query.md` § Mode administrateur ; `core_admin_control.py`.
- **Impact** : altération ou exfiltration de toute la base depuis le navigateur.
- **Priorité** : haute.
- **Recommandation** : attribuer ces permissions à un rôle dédié, jamais au quotidien ; journaliser
  hors application ; interdire le téléchargement de dump depuis l'interface en PROD ou le
  conditionner à un second administrateur. Décision DSI.
- **Interlocuteur** : DSI / gouvernance.

### R7 — Pas de TEST / PROD

- **Constat** : seule une instance locale (et éventuellement le poste du comptable) existe. Les
  scripts de déploiement n'ont été validés que sur un serveur Linux simulé (documentation).
- **Preuve** : inventaire vide ; `/version` = `0.0.0-local`.
- **Impact** : toute évolution est testée sur des données réelles ; pas de recette formelle.
- **Priorité** : haute.
- **Recommandation** : ouvrir TEST puis PROD selon `docs/deployment/` ; images taguées, jamais
  `latest` ; validation écrite avant PROD.
- **Interlocuteur** : DSI.

### R8 — Migrations Stock / notifications à appliquer sur chaque instance

- **Constat** : les révisions `20261022_notifications_01` et `20261022_mg_stock_alertes` sont
  additives (`retour_arriere = compatible`). Elles sont déjà appliquées sur l’instance locale
  d’audit ; les autres bases (poste comptable, futur TEST) resteront en retard tant que
  `alembic upgrade head` n’aura pas été lancé après sauvegarde.
- **Preuve** : `backend/alembic/versions/20261022_*.py` ; `docs/runbook-migrations.md`.
- **Impact** : code récent sur un schéma ancien → erreurs à l’exécution (colonne `portee`,
  table `mg_stock_alertes`).
- **Priorité** : moyenne.
- **Recommandation** : appliquer les migrations via la procédure habituelle (sauvegarde puis
  `alembic upgrade head`), jamais sur une base vide.
- **Interlocuteur** : équipe BEA DIGITAL.

### R9 — Gestion de `SECRET_KEY`

- **Constat** : une seule clé pour JWT et chiffrement TOTP ; défaut `change-me` accepté au
  démarrage ; rotation = invalidation de toutes les sessions et perte des secrets TOTP chiffrés.
- **Preuve** : `core/config.py`, `core/secret_box.py`, `core_admin_ops_service.py`.
- **Impact** : compromission de la clé = usurpation de toute session + lecture des secrets MFA.
- **Priorité** : haute.
- **Recommandation** : interdire le démarrage si la clé est une valeur par défaut ; séparer clé JWT
  et clé de coffre ; procédure de rotation documentée. Ne jamais réutiliser cette clé pour du M2M
  (déjà interdit par `docs/studio-integration-api.md`).
- **Interlocuteur** : DSI / sécurité.

### R10 — Observabilité limitée

- **Constat** : le journal d'accès JSON prévu n'est pas émis (niveau INFO) ; seuls Uvicorn (chaînes
  de requête) et 26 WARNING en 3 h sont visibles. Pas de SIEM.
- **Preuve** : absence de configuration de logging ; comptage `docker logs`.
- **Impact** : reconstruction d'incident incomplète ; fuite possible de paramètres dans les journaux
  Uvicorn.
- **Priorité** : moyenne.
- **Recommandation** : configurer le logger `bea.access` ; centraliser les journaux ; masquer les
  chaînes de requête ; définir une rétention.
- **Interlocuteur** : DSI / exploitation.

### R11 — Rate limiting en mémoire

- **Constat** : compteurs dans le processus Uvicorn unique ; reset au redémarrage.
- **Preuve** : `middleware/rate_limit.py`.
- **Impact** : inefficace dès qu'il y a plusieurs processus ou un redémarrage fréquent.
- **Priorité** : moyenne.
- **Recommandation** : déplacer les compteurs dans Redis (déjà utilisé) avant toute mise à
  l'échelle ; documenté comme option dans `docs/securite-bea-digital.md`.
- **Interlocuteur** : équipe BEA DIGITAL.

### R12 — Redis sans mot de passe

- **Constat** : `redis://redis:6379` sans AUTH ; isolation par le réseau Docker uniquement.
- **Preuve** : compose.
- **Impact** : un processus du même réseau peut vider les files, rejouer des réponses d'idempotence
  ou saturer les quotas.
- **Priorité** : moyenne.
- **Recommandation** : mot de passe Redis et publication nulle (déjà le cas en compose TEST/PROD).
- **Interlocuteur** : DSI / réseau.

### R13 — Bibliothèque JWT

- **Constat** : `python-jose` 3.3.0, peu maintenue ; CVE documentées par le projet ; algorithme
  restreint dans le code.
- **Preuve** : `requirements.txt`, `docs/studio-integration-api.md` § 12.1.
- **Impact** : surface cryptographique à maintenir.
- **Priorité** : moyenne.
- **Recommandation** : planifier le remplacement (PyJWT + `cryptography`) pour les jetons
  utilisateurs, indépendamment de la Phase 3 M2M.
- **Interlocuteur** : équipe BEA DIGITAL.

### R14 — Couverture de tests et CI

- **Constat** : 1 159 tests backend, 7 spécifications frontend ; CI sans PostgreSQL ; 5 échecs
  historiques documentés (données copiées) ; couverture non mesurée.
- **Preuve** : `backend/tests/`, `.github/workflows/ci.yml`, `docs/studio-integration-api.md` § 11.7.
- **Impact** : régressions métier non détectées avant livraison.
- **Priorité** : moyenne.
- **Recommandation** : service PostgreSQL jetable en CI ; ne pas livrer tant que les 5 échecs
  historiques ne sont pas classés ; étendre les tests frontend aux parcours Login 1 / Login 2.
- **Interlocuteur** : équipe BEA DIGITAL.

### R15 — Antivirus et messagerie

- **Constat** : code présent, variables vides.
- **Preuve** : `core/fichiers.py`, `services/mailer.py`, `.env.docker.example`.
- **Impact** : pièces jointes non analysées ; rappels contrats uniquement in-app.
- **Priorité** : moyenne.
- **Recommandation** : décider si ClamAV et SMTP interne sont exigés avant TEST ; fail-closed déjà
  implémenté pour ClamAV.
- **Interlocuteur** : DSI.

### R16 — Conservation des données personnelles

- **Constat** : Base Clientèle, EER, réclamations, GED (OCR en clair), `audit_logs` sans durée de
  conservation ; copies de test documentées à partir de la base réelle.
- **Preuve** : [architecture-donnees.md](architecture-donnees.md).
- **Impact** : conservation excessive, copies de test nominatives.
- **Priorité** : haute (réglementaire, non technique).
- **Recommandation** : politique de conservation, anonymisation des copies de test, contrôle des
  fichiers `backend/storage/rapports/` présents sur le poste.
- **Interlocuteur** : Conformité / DSI.

### R17 — Intégration ORION manuelle

- **Constat** : aucun connecteur ; dépendance à des extractions Excel.
- **Preuve** : [flux-integrations.md](flux-integrations.md).
- **Impact** : décalage, erreurs de fichier, responsabilité floue en cas d'écart.
- **Priorité** : haute (métier).
- **Recommandation** : formaliser la procédure actuelle ; décider d'une interface technique (DSI).
- **Interlocuteur** : DSI / métier.

### R18 — Dette technique

- **Constat** : `app/` (103 fichiers) et `alembic/` (13 révisions) à la racine, non déployés ;
  Angular Material dans les modules métier (182 fichiers) et Tailwind en dépendance, alors que
  `AGENTS.md` interdit d'ajouter ces bibliothèques dans `src/app/plateforme/` (règle respectée
  pour le chrome) ; `@ngx-translate` déclaré sans usage.
- **Preuve** : inventaire du dépôt.
- **Impact** : risque de coder au mauvais endroit ; surface de dépendances.
- **Priorité** : basse.
- **Recommandation** : ne pas déployer `app/` racine ; ne pas ajouter de dépendance au chrome
  plateforme ; retirer `@ngx-translate` s'il reste inutilisé.
- **Interlocuteur** : équipe BEA DIGITAL.

## 3. Questions encore ouvertes

Voir aussi [architecture-generale.md](architecture-generale.md#14-questions-à-valider-avec-la-dsi).

1. Serveurs TEST et PROD : existence, OS, dimensionnement, réseau.
2. Domaine, certificats, reverse proxy réel.
3. Politique de sauvegarde hors serveur et tests de restauration.
4. Supervision et astreinte.
5. Architecture et interfaces d'ORION.
6. SMTP interne, ClamAV, annuaire / SSO.
7. Décision M2M (IdP, serveur interne ou mTLS).
8. Classification et conservation des données.
9. Gouvernance des comptes CORE ADMIN (quatre yeux, révocation).
10. Statut juridique et réglementaire attendu (LBC-FT, BCM) — hors périmètre de cet audit.
