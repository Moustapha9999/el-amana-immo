# Studio d’intégration API — Phase 1 (catalogue + console en lecture seule)

Section CORE ADMIN. Phase 1 = **consultation uniquement**. Aucune application
cliente, aucune clé API, aucun OAuth2, aucun appel sortant, aucune table, aucune
migration. Les phases suivantes ne commencent qu’après validation explicite.

## 1. Objectif et périmètre

- Inventorier les opérations réellement exposées par le backend `backend/`.
- Documenter chaque opération sans rien inventer : paramètres, corps, réponses,
  authentification, permissions, statut de vérification.
- Proposer des exemples d’appel (cURL, Python `httpx`, TypeScript `fetch`) pour les
  seules opérations dont l’accès est établi.
- Permettre de tester quelques GET internes revus, avec la session et les droits
  de l’administrateur connecté.

Hors périmètre Phase 1 : CRUD d’applications clientes, clés API, nouvelle
authentification, enregistrement d’API externes, import OpenAPI, appel sortant,
génération de secret, déploiement TEST/PROD.

**Le catalogue n’est pas une garantie d’autorisation.** Chaque endpoint applique
toujours ses propres contrôles au moment de l’appel.

## 2. Architecture et routes

| Élément | Emplacement |
| --- | --- |
| Construction du catalogue | `backend/app/services/integrations/catalogue.py` |
| Exemples de code | `backend/app/services/integrations/exemples.py` |
| Console (liste d’autorisation, masquage, limites) | `backend/app/services/integrations/console.py` |
| Schémas Pydantic | `backend/app/schemas/integrations.py` |
| Endpoints | `backend/app/api/v1/endpoints/core_admin_integrations.py` |
| Permission | `core.admin.integrations.view` dans `CORE_ADMIN_PERMISSIONS` |
| Front | `frontend/angular20/src/app/plateforme/core-admin/core-admin-integration*.ts` |

API (préfixe `/api/v1/plateforme/admin/integrations`, toutes protégées par
`require_platform_permission("core.admin.integrations.view")`) :

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| GET | `/catalogue` | Liste paginée + KPI + filtres (`module`, `methode`, `authentification`, `permission_statut`, `schema`, `permission`, `disponibilite`, `console`, `q`) |
| GET | `/catalogue/{operation_id}` | Fiche d’une opération |
| GET | `/catalogue/{operation_id}/exemples` | Exemples, ou motif d’indisponibilité |
| GET | `/console/operations` | Opérations admissibles, environnement, limites |
| POST | `/console/executer` | Exécute une opération de la liste d’autorisation |

Routes UI (shell `/admin`, garde `coreAdminGuard` = `core.admin.access`) :
`/admin/integrations`, `/admin/integrations/catalogue`,
`/admin/integrations/catalogue/:operationId`, `/admin/integrations/console`.
Masquer le menu ne protège rien : le contrôle est dans le backend.

## 3. Construction du catalogue

Source : les routes FastAPI réelles (`app.routes`) et le schéma `app.openapi()`
de l’application en cours d’exécution. Le résultat est mis en cache par instance
d’application (environ 2 s au premier appel).

- **Identifiant stable** : `{méthode}.{module de l’endpoint}.{nom de fonction}`,
  par exemple `get.core_admin_catalogue.list_modules`. En cas de collision, un
  suffixe `.{sha1(chemin)[:8]}` est ajouté (4 cas actuellement). L’identifiant ne
  change que si le code de la route change.
- **Authentification et permissions** : lues dans l’arbre de dépendances de la
  route (`route.dependant`), et uniquement pour les dépendances connues de
  `app.api.deps` : `get_platform_user`, `get_current_user`,
  `require_platform_permission`, `require_permission`, `require_module_access`,
  `require_demandes_module`. Toute autre dépendance applicative (contextes de
  module, portées, helpers de filtres) est listée comme « contrôle non analysé ».
- **Contrôles dans le traitement** : le corps de chaque endpoint est inspecté
  (`403`, `Forbidden`, `is_superuser`, `permission_codes`, `require_*(`, `scope`,
  `périmètre`…). Tout marqueur rétrograde la permission en « non déterminée », avec
  un motif. Exemples : `get.mg_requests.me_get` (`require_owner`),
  `get.mg_achats.dossier_facture`, `post.documents.upload_document`.
- **Logique d’exigence** : chaque dépendance exige « au moins une » de ses
  permissions, et toutes les dépendances sont requises. Le catalogue restitue cette
  logique (`exigence_permissions`, par exemple
  `au moins une de (mg.batch.admin, mg.batch.update)`) au lieu d’une liste à plat.
- Une permission « identifiée » est **nécessaire, pas forcément suffisante** : un
  service peut encore restreindre selon le périmètre, le propriétaire ou l’état
  métier. Cet avertissement est servi par l’API et affiché sur chaque fiche.
- **Schéma de réponse** : `explicite` (modèle Pydantic ou conteneur typé),
  `générique` (`dict`, `list`, `Any`) ou `absent` (pas de `response_model`). Les
  routes sans schéma restent au catalogue, avec un motif de restriction.
- **Paramètres, corps, réponses** : repris d’OpenAPI ; seuls les champs de premier
  niveau sont affichés. Les valeurs par défaut ne sont affichées que si elles sont
  scalaires, courtes et non sensibles.
- Une permission exigée par le code mais absente du référentiel est **signalée**,
  jamais retirée. Cas actuel : `mg.batch.admin`, alternative à `mg.batch.update`
  sur la suppression de lot MG.

## 4. Statuts

| Axe | Valeurs |
| --- | --- |
| Authentification | `login1`, `login2`, `login1_ou_login2` (toute session), `indeterminee`, `aucune_detectee` |
| Permission | `identifiee` (permission lue dans les dépendances, aucun contrôle non analysé, ni dans les dépendances ni dans le traitement), `non_determinee` (au moins un contrôle non analysé), `non_verifiee` (authentification absente ou indéterminée) |
| Disponibilité | `documentee` (exemples générés), `restreinte` (motifs affichés, pas d’exemple), `exclue` (identité de la route seulement) |

Une route est **restreinte** dès qu’un de ces cas s’applique :
- schéma de réponse absent ou générique ;
- authentification absente ou indéterminée ;
- permission non déterminée ;
- corps de requête non JSON ;
- permission absente du référentiel ;
- doublon méthode + chemin ;
- route absente d’OpenAPI.

Une route est **exclue** dans ces cas :
- `/api/v1/auth/*` (authentification) ;
- `/api/v1/plateforme/admin*` (administration) ;
- route hors `/api/v1` (infrastructure) ;
- `include_in_schema=False` (route masquée).

Pour une route exclue, la fiche ne publie ni description, ni paramètres, ni corps,
ni réponses, ni exemples. Une méthode GET n’est jamais considérée comme sûre par
défaut.

Comptes à la date de livraison (application complète) :
- 986 opérations découvertes ;
- disponibilité : 275 documentées, 548 restreintes, 163 exclues (administration 145,
  authentification 13, infrastructure 3, masquées 2) ;
- authentification : 785 Login 2, 158 Login 1, 33 toute session, 6 sans
  authentification détectée, 4 indéterminées ;
- permission : 593 identifiées, 383 non déterminées, 10 non vérifiées ;
- schéma de réponse : 448 explicites, 244 génériques, 294 absents.

## 5. Exemples

- Générés seulement pour les opérations `documentee`. Sinon : `disponible=false`
  et le motif est affiché.
- URL de base configurable : variable `BEA_BASE_URL`, valeur par défaut fictive
  `https://bea-digital.exemple.invalid`. L’interface permet de la remplacer, avec
  validation http(s).
- Jeton : variable `BEA_ACCESS_TOKEN`. Aucune valeur réelle, chemins `<param>`,
  valeurs fictives pour les champs obligatoires.
- Le mécanisme réel est décrit :
  - Login 1 : `POST /api/v1/auth/login` ;
  - Login 2 : `POST /api/v1/auth/modules/{module}/login` avec une session Login 1
    active.

  Aucune authentification machine-à-machine n’existe ni n’est suggérée.
- Mention obligatoire : à exécuter uniquement avec un compte autorisé.

## 6. Console — règles d’admissibilité

Une opération est exécutable si **toutes** les conditions suivantes sont vraies.
Elles sont vérifiées côté serveur, à chaque appel.

1. Elle est inscrite dans `CONSOLE_OPERATIONS` (liste revue, avec justification).
2. Méthode `GET`.
3. Authentification Login 1, permission `identifiee`, schéma de réponse explicite,
   présente dans OpenAPI.
4. Le routage réel du chemin reconstruit retombe sur la même route.

Liste actuelle :
- `get.core_admin_integrations.lister_catalogue` ;
- `get.core_admin_integrations.fiche_operation` ;
- `get.core_admin_catalogue.list_modules` ;
- `get.core_admin_catalogue.list_departments`.

Exemples d’opérations écartées après revue :
- les GET plateforme qui appellent `ensure_catalogue()`, car ils écrivent en base
  (`/plateforme/espaces`, `/catalogue`, `/core`, `/modules/{code}`, `/me/hub`) ;
- le référentiel org, dont la réponse est typée `dict` ;
- tout endpoint Login 2, d’export, de téléchargement ou d’écriture.

Fonctionnement de `POST /console/executer` :
- **Corps accepté** : `operation_id`, `parametres_chemin` et `parametres_requete`.
  Tout autre champ (`url`, `methode`, `headers`, `chemin`…) est refusé avec une
  erreur 422.
- **Chemin** : reconstruit à partir du gabarit de la route. Valeurs autorisées :
  `[A-Za-z0-9._:-]{1,128}`, encodées. L’ensemble des paramètres doit être exact.
- **Paramètres de requête** : uniquement ceux déclarés par la route, au plus 20,
  chaque valeur au plus 200 caractères, sans caractères de contrôle.
- **Appel** : effectué en mémoire via `httpx.ASGITransport` sur l’application elle-même,
  avec l’en-tête `Authorization` de l’administrateur et son IP réelle. La
  permission propre de l’endpoint s’applique donc ; par exemple
  `core.admin.modules` pour `list_modules`. Aucun appel réseau, aucun proxy
  générique.
- **Limites** : réponse au plus 256 Kio (au-delà, le corps n’est pas renvoyé),
  délai 10 s (erreur 504 `CONSOLE_DELAI_DEPASSE`).
- **Masquage** : appliqué récursivement aux clés sensibles (mots de passe, jetons,
  secrets, OTP, IBAN/RIB, e-mail, téléphone, NNI/CIN/passeport, IP, hash,
  user-agent, numéro de compte…) et aux chaînes ressemblant à un JWT. Le
  nombre de champs masqués est affiché.
- **Audit** : `console_execute` (statut HTTP et durée) ou `console_refus` (code).
  L’identifiant est tronqué à 64 caractères, la taille de `entity_id`. Aucun corps
  de requête ou de réponse n’est journalisé ni stocké.
- **Journaux** : `httpx` journalise en INFO l’URL complète d’une requête,
  paramètres compris. Un filtre posé sur les loggers `httpx` et `httpcore` écarte
  tout message visant l’hôte interne de la console. Aucune valeur saisie
  n’apparaît donc dans les journaux, même en INFO ou DEBUG.
- **Interface** :
  - environnement cible (`APP_ENV`) et limites affichés ;
  - aucune exécution automatique, même avec `?operation=` dans l’URL ;
  - bouton « Exécuter » obligatoire.

## 7. Sécurité

- Login 1 obligatoire et permission dédiée. La politique MFA CORE ADMIN de
  `require_platform_permission` s’applique. Un jeton Login 2 est refusé (401).
- La permission n’est accordée à aucun rôle. Elle n’est couverte ni par
  `core.admin.access` ni par un code `*.admin`. Superuser : accès implicite.
- Aucune information d’infrastructure, aucun secret, aucune donnée personnelle
  dans les métadonnées.
- Les identifiants d’opération sont validés par recherche dans l’index : aucune
  résolution dynamique.

## 8. Tests

Vérification indépendante complémentaire : un script hors dépôt a été exécuté sur
l’application réelle et la copie jetable. Il a :
- soumis à la console les 982 opérations hors liste, plus 11 requêtes forgées ;
- confirmé qu’aucun appel interne n’était émis ;
- testé un vrai jeton Login 2 sur les 5 routes ;
- analysé les exemples, le catalogue complet, les 986 fiches, les journaux en DEBUG
  et l’audit. Recherches : secrets de configuration, JWT, IBAN, cartes (Luhn),
  e-mails réels, hôtes internes, IP privées.

Résultat : tout est conforme. La première passe a révélé deux écarts, corrigés depuis :
l’URL de la console journalisée par `httpx`, et une troncature d’audit absente.

Backend (`backend/tests/test_core_admin_integrations.py`) :
- **Accès** :
  - permission déclarée et non attribuée ;
  - Login 1 + permission → 200 ;
  - sans jeton → 401 ;
  - sans permission → 403 ;
  - jeton Login 2 → 401.
- **Catalogue** :
  - aucune permission ni aucun schéma inventé ;
  - routes sans schéma gérées ;
  - identifiants stables et uniques ;
  - exclusions sans métadonnées ;
  - filtres et KPI ;
  - la recherche ignore le contenu masqué.
- **Exemples** : aucun secret, flux Login 2 décrit.
- **Console** :
  - liste d’autorisation = ensemble éligible ;
  - opération hors liste → 403 ;
  - POST ou Login 2 refusés même s’ils sont injectés dans la liste ;
  - valeurs de chemin arbitraires refusées ;
  - champs `url`/`methode`/`headers` → 422 ;
  - GET/PUT/DELETE sur `/executer` → 405 ;
  - troncature, délai (504), corps non JSON ;
  - masquage, aucun secret dans les logs.

Les tests PostgreSQL ne s’exécutent que sur une base jetable (garde `base_jetable`).
Ils ont été lancés sur la copie isolée `bea_digital_phase0_test`, dans un conteneur
jetable (Redis DB 9–11).

Frontend (`core-admin-integrations.spec.ts`, 12 specs Karma/Jasmine, Chromium
headless dans un conteneur Docker jetable) :
- fonctions de paramètres et de requête console ;
- distinction entre accès refusé et refus console ;
- validation de l’URL de base ;
- appels du service ;
- vue d’ensemble (KPI, 403) ;
- catalogue (filtres repris de l’URL, état vide, erreur) ;
- fiche 404 ;
- console (aucune exécution automatique, POST après clic, état vide).

Non réalisé : test de bout en bout dans un navigateur sur l’application déployée
(aucun déploiement en Phase 1).

## 9. Limites connues

- L’analyse des dépendances ne lit que les contrôles de `app.api.deps`. Les
  contrôles internes aux services (`ctx`, portées, filtres) donnent « permission
  non déterminée », par prudence.
- Les champs affichés se limitent au premier niveau des schémas.
- Le masquage repose sur les noms de clés et sur la forme JWT. Une donnée sensible
  sous un nom neutre ne serait pas masquée. La liste d’autorisation reste donc
  volontairement courte.
- `mg.batch.admin` est référencée par le code mais absente du référentiel. C’est
  sans effet sur l’accès (alternative à `mg.batch.update`), mais à arbitrer.

## 10. Validation avant la Phase 2

1. Revue par le responsable sécurité de la liste `CONSOLE_OPERATIONS` et des
   motifs d’exclusion.
2. Décision d’attribution de `core.admin.integrations.view` : rôle plateforme
   dédié, procédure dans [core-admin.md](core-admin.md).
3. Vérification sur TEST après déploiement validé : comptes Login 1 avec et sans
   permission, jeton Login 2, console sur `list_modules` avec un compte sans
   `core.admin.modules` (403 attendu dans le résultat).
4. Arbitrage `mg.batch.admin` (ajout au référentiel ou retrait du code).
5. Validation explicite écrite avant tout travail Phase 2 (applications clientes,
   identifiants, authentification machine-à-machine).

## 11. Phase 2 — Gestion des applications clientes

> **Aucune authentification machine-à-machine n’existe.** Une application
> cliente est une **fiche de gouvernance** : qui demande quoi, pourquoi, avec
> quelle décision. Aucun jeton, clé API ou secret n’est généré ni stocké. Une
> opération « approuvée » n’autorise **aucun** appel : les appels restent faits
> par un utilisateur avec sa propre session et ses propres permissions.

### 11.1 Modèle de données (migration `20261021_integrations_01`)

`down_revision = 20261020_clientele_14`. Additive uniquement (3 `create_table`
+ index) ; `downgrade` supprime les 3 tables. **Pas** de table
`integration_credentials`, aucune colonne de secret, hash ou jeton.

| Table | Rôle |
|-------|------|
| `integration_clients` | Fiche : `code` public `INT-XXXXXXXX` (identifiant, pas un secret), nom, description, `org_entite_id` → `departements`, contact technique (nom/fonction), environnement `DEV`/`TEST`, finalité, statut, notes, `revision` (verrou optimiste), auteurs, archivage. Unicité (nom normalisé, environnement) hors fiches archivées. |
| `integration_client_grants` | Opération du catalogue demandée : `operation_id`, méthode, chemin, permissions et exigence (instantané), statut, justification, demandeur, décideur, date, motif. Unique (`client_id`, `operation_id`). |
| `integration_client_grant_events` | Historique immuable des décisions (avant/après, auteur, motif). |

### 11.2 Statuts et transitions

Fiche : `brouillon → en_preparation → active ⇄ suspendue`, `en_preparation →
brouillon`, `suspendue → en_preparation`, `archivee` terminal (route dédiée,
motif obligatoire). L’activation exige finalité et entité organisationnelle.
L’environnement est figé dès qu’une opération a été soumise ou décidée.
L’archivage révoque les opérations approuvées et retire celles en cours, avec
un événement pour chacune.

Opérations (permission requise par transition, vérifiée côté serveur) :

| De | Vers | Permission |
|----|------|-----------|
| `demandee` | `en_attente`, `retiree` | `grants.manage` |
| `en_attente` | `approuvee`, `refusee` (motif) | `grants.approve` |
| `en_attente` | `retiree` | `grants.manage` |
| `approuvee` | `revoquee` (motif) | `grants.approve` |
| `refusee`, `revoquee`, `retiree` | `demandee` | `grants.manage` |

L’approbation n’est possible que si la fiche est `en_preparation` ou `active`,
et l’admissibilité est revérifiée au moment de la décision (instantané
rafraîchi). Le contrôle « quatre yeux » n’est pas imposé (inexistant dans le
dépôt) : demandeur et approbateur sont tous deux tracés.

### 11.3 Admissibilité d’une opération

Une opération ne peut être demandée que si : elle existe au catalogue et est
`documentee` ; son authentification est Login 1, Login 2 ou session ; sa
permission est identifiée, non vide et présente au référentiel ; aucune
permission `core.admin*` ou `*.admin` ; méthode ≠ `DELETE` ; chemin et nom sans
motif sensible (export, téléchargement, import, upload, purge, reset,
restauration, sauvegarde, mot de passe, jeton, secret, MFA/TOTP, session,
impersonation, traitement de masse) ; module actif. Demande « tout ou rien » :
opération inconnue → 422 `OPERATION_INCONNUE`, inadmissible → 422
`OPERATION_INADMISSIBLE`, déjà ouverte → 409 `DEJA_DEMANDEE`.

### 11.4 Routes et permissions

Préfixe `/api/v1/plateforme/admin/integrations/clients`, Login 1 obligatoire
(jeton Login 2 → 401), aucune route exposée au catalogue.

| Route | Permission |
|-------|-----------|
| `GET /` , `GET /{id}` | `clients.view` |
| `POST /`, `PATCH /{id}`, `POST /{id}/archive` | `clients.manage` |
| `GET /{id}/grants`, `GET /{id}/historique` | `grants.view` |
| `GET /{id}/operations-admissibles`, `POST /{id}/grants` | `grants.manage` |
| `PATCH /{id}/grants/{grant_id}` | `grants.manage` ou `grants.approve` selon la transition |
| `GET /{id}/documentation` | `export` |

Toutes les permissions sont préfixées `core.admin.integrations.` et n’ont pas
de suffixe `.admin` (aucun joker existant ne les couvre). Elles sont seedées
par la synchronisation du catalogue au démarrage et **attribuées à aucun
rôle** ; aucun rôle existant n’a été modifié. Attribution : voir
[core-admin.md](core-admin.md). Audit : `integration_client_create`,
`_update`, `_archive`, `integration_grant_request`, `integration_grant_<statut>`,
`integration_client_documentation`.

Les textes saisis refusent les caractères de contrôle et tout contenu
ressemblant à un secret (`Bearer`, `password=`, `token=`, `api_key:`, JWT,
clé privée) ; champs inconnus refusés (`extra=forbid`).

### 11.5 Interface

`/admin/integrations/clients` (liste filtrable, filtres dans l’URL), `/nouveau`,
`/:id/modifier` (confirmation, garde de modifications non enregistrées,
`revision` envoyée), `/:id` avec onglets *API et opérations*, *Autorisations*,
*Historique*, *Documentation* (visibles selon permissions, onglet dans
`?onglet=`). États : chargement, erreur (avec `request_id`), vide, accès refusé,
indisponible. Les masquages côté UI sont du confort : le serveur décide.
La documentation (opérations approuvées, exemples avec jeton **utilisateur**
fictif `BEA_ACCESS_TOKEN`, avertissements) est téléchargeable en Markdown.

### 11.6 Application de la migration (procédure, non exécutée)

La migration n’a été exécutée **que** sur la base jetable
`bea_digital_phase2_test` (upgrade → downgrade -1 → upgrade). Pour TEST, après
validation écrite : sauvegarde `pg_dump`, puis `alembic upgrade head`, puis
contrôle `alembic current` = `20261021_integrations_01`. **Jamais** en
production sans approbation explicite. Retour arrière : `alembic downgrade -1`
(supprime les 3 tables et leurs données).

Suivi : enregistrer `integration_clients.org_entite_id` dans les LIAISONS du
référentiel organisationnel **après** application de la migration (l’ajouter
avant casserait la fiche entité sur une base sans la table).

### 11.7 Tests

- Backend `tests/test_integration_clients.py` (base jetable
  `bea_digital_phase2_test`, garde sur `current_database()`) : permissions
  déclarées et non attribuées, routes Login 1, absence de tables/colonnes
  d’authentification, migration additive et réversible, admissibilité,
  transitions, refus des secrets, 401 sans jeton et avec Login 2, 403 par
  permission manquante, création/doublons/verrou de révision, cycle complet
  demande → soumission → approbation/refus/révocation/retrait sans
  élévation de privilège (permissions et `role_permissions` inchangées),
  historique, audit, documentation, archivage, environnements.
  Phase 1 + Phase 2 + `test_migrations_retour` : 91 réussis, 0 ignoré.
  La migration déclare `retour_arriere = "compatible"` (tables nouvelles
  ignorées par le code précédent).
- Suite complète : 5 échecs, identiques avec le code `HEAD`, donc antérieurs
  et dépendants des données copiées (`test_clientele_moteur` ×3,
  `test_clientele_hebdo`, `test_eer_clientele_pont`).
- Front `core-admin-integration-clients.spec.ts` : 18 tests (29 avec la
  Phase 1) ; `ng build` réussi.

### 11.8 Limites

- Pas d’authentification machine-à-machine (Phase 3 : préparation seulement, § 12).
- Pas de contrôle quatre yeux imposé.
- Les permissions d’une opération sont un instantané : un changement du code
  rend l’opération « devenue indisponible » (indiquée dans l’UI) jusqu’à
  nouvelle décision.

## 12. Phase 3 — Authentification machine-à-machine (non activée)

**Point d’arrêt.** Aucun mécanisme d’émission ou de validation de jeton
client n’est en service. La DSI n’a pas approuvé de mécanisme dans ce
dépôt ; aucune décision technique n’est tranchée. Cette section compare
les options, propose une architecture et documente les règles
préparatoires. Elle n’autorise pas à émettre un jeton.

### 12.1 Constat sur l’existant

| Élément | État dans le dépôt |
|---------|--------------------|
| Jetons utilisateurs | JWT HS256 signés avec `SECRET_KEY` (`python-jose` 3.3.0), claims `sub`, `exp`, `type`, `sid`, `jti`. **Pas** de `iss` ni `aud`. |
| Sessions | Table `auth_sessions` parent (Login 1) / enfant (Login 2) ; révocation serveur ; idle UI 2 min. |
| Durée | Access : politique DB ou `ACCESS_TOKEN_EXPIRE_MINUTES` (15 min). Refresh Login 1 : jours. Refresh module : minutes. |
| Rate limiting | Middleware mémoire (login, API, sensible, reset). |
| Audit | `audit_logs` ; secrets, jetons et en-têtes `Authorization` ne doivent jamais y figurer. |
| MFA / lockout | Politique DB ; MFA CORE ADMIN configurable. |
| Applications clientes (Phase 2) | Fiches + grants. **Aucune** table `integration_credentials`, aucune colonne secret. Statut `active` = configuration, pas une application authentifiée. |
| Décision DSI | Absente du dépôt (pas de note, pas d’IdP documenté, pas de certificat mTLS). |

Les jetons utilisateurs **ne peuvent pas** être réutilisés tels quels comme
jetons d’application : ils identifient une personne, portent une session
révocable, n’ont pas d’audience dédiée, et sont signés avec la clé unique
`SECRET_KEY` (aussi utilisée pour le reset de mot de passe et, via
dérivation, le coffre MFA). **Ne jamais** signer un jeton M2M avec
`SECRET_KEY`.

Bibliothèques d’auth dans l’image (`python-jose[cryptography]==3.3.0`) :

- `python-jose` 3.3.0 n’est plus activement maintenu. CVEs connues
  (confusion d’algorithme / vérification d’`iss` si `algorithms` n’est
  pas restreint — CVE-2024-33663, CVE-2024-33664). Le code actuel passe
  explicitement `algorithms=[settings.jwt_algorithm]`.
- `ecdsa` (dépendance optionnelle) a des antécédents de fuites
  temporelles ; ne pas s’en servir pour signer des jetons M2M.
- `cryptography` est présent et doit rester le backend cryptographique
  si un serveur d’autorisation interne est un jour retenu.

Une future implémentation devra **changer de bibliothèque** (PyJWT +
`cryptography`, ou un IdP externe) plutôt que d’étendre `python-jose`.

### 12.2 Comparatif

Critères communs à toute option retenue : registre des applications =
tables Phase 2 ; un jeton n’autorise que les opérations `approuvee`
toujours admissibles ; DEV et TEST séparés ; PROD fermé tant que la DSI
n’ouvre pas l’environnement ; audit de l’émission, du refus et de la
révocation **sans** journaliser le secret ni le jeton ; pas d’appel
sortant depuis BEA DIGITAL pour « tester » un client.

#### Option A — IdP DSI (OAuth 2.0 Client Credentials)

Registre : l’IdP (Entra ID, AD FS, Keycloak, ou tout serveur déjà
approuvé) détient `client_id` / `client_secret` (ou certificat). BEA
DIGITAL ne stocke **pas** le secret ; il enregistre seulement
l’identifiant public et le lie à `integration_clients`.

Émetteur : l’IdP (`iss` de la DSI). BEA DIGITAL valide la signature
(JWKS), `aud` dédiée (`bea-digital-api` ou équivalent par
environnement), `exp`, et un claim d’application mappé vers la fiche.

Durée / révocation : celles de l’IdP (typiquement 5–15 min) + liste de
révocation locale (fiche `suspendue` / `archivee`, grant révoqué).
Rotation : procédure DSI.

Portées : **pas** les permissions utilisateur. Un scope IdP éventuel
n’accorde rien à lui seul : l’autorisation effective reste
`integration_client_grants` au statut `approuvee`, revérifiée à chaque
appel (`m2m_preparation.decision_appel`).

Dépendances : IdP DSI, JWKS, réseau sortant **restreint** vers l’IdP
(validation uniquement). Responsabilité DSI : cycle de vie des
secrets, certificats, journalisation IdP. Responsabilité BEA DIGITAL :
fiches, grants, validation des claims, contrôles métier des routes.

**Avantage** : mécanisme déjà connu de la banque, secrets hors de
BEA DIGITAL. **Inconvénient** : indisponible tant que la DSI n’a pas
désigné l’IdP et l’audience.

#### Option B — Serveur d’autorisation interne (OAuth 2.0 Client Credentials)

Registre : table nouvelle `integration_credentials` (à concevoir), un
secret par environnement, hash (argon2/bcrypt) **jamais** le secret en
clair, affichage une seule fois à la création. Clé de signature
**distincte** de `SECRET_KEY` : paire ES256 (P-256) ou Ed25519, privée
hors dépôt, rotation documentée.

Émetteur : BEA DIGITAL (`iss` = URL d’environnement, `aud` =
`bea-digital-m2m`). Endpoint `POST /oauth/token` **hors** du préfixe
Studio, rate-limité, sans Login 1.

Durée : access court (5–10 min), **sans** refresh token M2M (le client
redemande un jeton). Révocation : `jti` en allow-list courte **ou**
fiche/grant révoqués (le jeton déjà émis meurt à `exp`). Rotation du
secret : invalidation immédiate de l’ancien hash.

Portées : identiques à A (grants, pas les rôles utilisateur).

Dépendances : `cryptography` (déjà présent) ; **pas** `python-jose` /
`ecdsa`. Responsabilité DSI : approbation du mécanisme, conservation
hors bande du premier secret, revue de la clé. Responsabilité BEA
DIGITAL : implémentation, stockage du hash, émission, audit.

**Avantage** : autonome si la DSI n’a pas d’IdP M2M. **Inconvénient** :
BEA DIGITAL devient émetteur de secrets ; surface d’attaque nouvelle ;
à n’activer qu’après décision écrite.

#### Option C — TLS mutuel (mTLS)

Registre : certificat client (DN / empreinte) lié à la fiche,
renouvelé par la DSI. Pas de secret applicatif dans BEA DIGITAL.

Émetteur : aucun jeton applicatif — l’identité est le certificat
présenté au reverse proxy. BEA DIGITAL reçoit l’identité via un
en-tête **injecté uniquement** par le proxy de confiance
(`TRUSTED_PROXIES`), jamais par le client.

Durée / révocation : CRL ou OCSP DSI + désactivation de la fiche.
Portées : grants, comme ci-dessus.

Dépendances : PKI DSI, reverse proxy capable de mTLS, mapping
certificat → fiche. **Avantage** : pas de secret à stocker.
**Inconvénient** : infrastructure absente du dépôt ; inexploitable
sans la PKI.

#### Option D — Clés API statiques (déconseillée)

Une clé longue envoyée à chaque appel, hashée en base. Simple, mais :
révocation = rotation de tous les consommateurs ; pas d’expiration
courte ; rejeu trivial si journalisée ; confusion facile avec un
secret utilisateur. **Écartée** sauf exigence écrite de la DSI
limitée à DEV, avec rotation obligatoire et jamais en-tête
`Authorization: Bearer` partagé avec les JWT utilisateurs.

### 12.3 Proposition (en attente de validation)

1. Demander à la DSI si un IdP OAuth 2.0 Client Credentials (ou une
   PKI mTLS) est déjà approuvé pour les applications internes.
2. Si oui → **option A** (ou C si mTLS est le standard). BEA DIGITAL
   n’émet rien ; il valide.
3. Si non → **option B**, après note d’architecture signée : clé
   ES256 dédiée, secret hashé, `iss`/`aud` par environnement, durée
   ≤ 10 min, pas de refresh M2M, python-jose non utilisé.
4. Dans tous les cas : réutiliser `eligibilite_emission` et
   `decision_appel` (`backend/app/services/integrations/m2m_preparation.py`)
   **avant** d’accepter un appel. Une fiche `active` sans opération
   approuvée, un environnement `PROD`, un grant périmé ou une route
   devenue non fiable → refus.

Décisions ouvertes (la DSI tranche) : IdP vs interne vs mTLS ;
durée exacte ; présence d’un refresh ; lieu de stockage du secret
initial ; ouverture éventuelle de PROD ; bibliothèque JWT de
remplacement pour les **utilisateurs** (hors Phase 3).

### 12.4 Règles préparatoires déjà codées (non branchées)

Module `m2m_preparation.py` : **aucune route** ne l’importe.

Éligibilité à l’émission (`eligibilite_emission`) — ordre des refus :

| Code | Condition |
|------|-----------|
| `ENVIRONNEMENT_FERME` | cible hors `{DEV, TEST}` |
| `CLIENT_INCONNU` | fiche absente |
| `CLIENT_NON_ACTIF` | statut ≠ `active` |
| `ENVIRONNEMENT_DIFFERENT` | env fiche ≠ env cible |
| `AUCUNE_OPERATION_APPROUVEE` | zéro grant `approuvee` |
| `ELIGIBLE` | sinon |

Décision d’appel (`decision_appel`) — un jeton valide ne suffit pas :

| Code | Condition |
|------|-----------|
| `OPERATION_INCONNUE` | hors catalogue ou méthode/chemin différents du gabarit routeur |
| `OPERATION_NON_APPROUVEE` | pas de grant `approuvee` |
| `OPERATION_MODIFIEE` | méthode/chemin changés depuis l’approbation |
| `PERMISSIONS_MODIFIEES` | permissions catalogue ≠ instantané |
| `OPERATION_NON_FIABLE` | `admissibilite` Phase 2 (dont `*.admin`, `DELETE`, module inactif) |
| `APPROUVEE` | sinon — les contrôles métier de la route restent à appliquer |

### 12.5 Tests

`tests/test_integration_m2m_preparation.py` : aucune route
oauth / token / credential sous `/integrations` ; pas de table
`integration_credentials` ; module non branché ; JWT utilisateur sans
`iss`/`aud` ; cas d’éligibilité et de décision (paramétrés) ;
refus d’une permission `.admin`.

**Aucune** UI d’identifiants, **aucun** secret créé, **aucune**
migration Phase 3.

## 13. Phase 4 — Fournisseurs d’API externes et import OpenAPI

Configuration **seulement**. Aucun appel HTTP sortant : pas de
téléchargement d’URL, pas de test de connectivité, pas de résolution
de `$ref` distant, pas d’appel aux serveurs déclarés, pas de proxy
générique. Aucun secret n’est stocké.

### 13.1 Objectif

Enregistrer les API que BEA DIGITAL **pourrait** consommer plus tard
(fiches, spécifications, opérations, exemples non testés). « Validé »
signifie que la configuration a été examinée, pas que le fournisseur
est joignable ou fiable.

### 13.2 Tables (migration `20261021_integrations_02`)

`down_revision = 20261021_integrations_01`. Additive (`create_table` +
index) ; `downgrade` les supprime. `retour_arriere = "compatible"`.
**Jamais** appliquée sur `bea_digital` ni en production. Exécutée
uniquement sur la base jetable `bea_digital_phase4_test` (upgrade →
downgrade -1 → upgrade). Une seule tête Alembic.

| Table | Rôle |
|-------|------|
| `integration_fournisseurs` | Fiche `EXT-XXXXXXXX`, nom, `org_entite_id` → `departements`, responsable interne, contact, environnement `DEV`/`TEST`, URL de base (métadonnée), documentation, statut, notes, `revision`, auteurs, validation, archivage. Unicité partielle (nom normalisé, environnement) hors archivés. |
| `integration_fournisseur_specs` | Version importée : numéro, format, nom de fichier, taille, empreinte SHA-256, OpenAPI, titre, version API, document JSONB assaini, résumé, avertissements, importateur. Unique (`fournisseur_id`, `numero`) et (`fournisseur_id`, `empreinte`). |
| `integration_fournisseur_operations` | Opération importée (`spec_id` obligatoire) ou manuelle (`spec_id` NULL). Unique (spec, méthode, chemin) ; unique partielle manuelle active. |

Aucune colonne `secret`, `password`, `token`, `credential`.

### 13.3 Statuts fournisseur

`brouillon ⇄ a_valider → valide ⇄ a_valider`, `valide → suspendu →
a_valider`. `archive` terminal (motif obligatoire). Permissions :

| Transition | Permission |
|------------|-----------|
| brouillon → a_valider, a_valider → brouillon, valide → a_valider, suspendu → a_valider | `fournisseurs.manage` |
| a_valider → valide, valide → suspendu (motif) | `fournisseurs.validate` |

Modifiable seulement en `brouillon` / `a_valider`. La validation exige
URL, entité organisationnelle et au moins une opération. TEST exige
`https`. L’environnement se fige dès qu’une spec ou une opération
existe. Historique = `audit_logs` (`entity` = `integration_fournisseur`).

### 13.4 Import OpenAPI

Fichier `.json` / `.yaml` / `.yml`, 2 Mio max (413 au-delà). Versions
3.0.x et 3.1.x. YAML : `SafeLoader` sans ancres, alias, merge keys ni
clés dupliquées. JSON : clés uniques, pas de NaN.

Limites : profondeur 64, 200 000 nœuds, 2 000 opérations, schémas
résumés bornés. `$ref` **locaux** seulement ; une référence externe
(URL ou autre fichier) → avertissement `REFERENCE_EXTERNE`, **jamais
chargée**. Cycles → erreur. Chemins refusés s’ils contiennent espace,
`?`, `#`, `..`.

Assainissement : exemples / défauts à nom sensible masqués
(`<masqué>`) ; userinfo retiré des URL du **document stocké** ;
JWT, clé privée, `Bearer` long → erreur `SECRET_SUSPECT`.

Flux : `POST …/specs/analyse` (aperçu, diff, conflits, rien
d’enregistré) puis `POST …/specs` avec la même empreinte, la version
courante lue, et `accepter_conflits` si une opération manuelle porte
la même méthode+chemin. Un fichier déjà importé (empreinte) est
refusé. Les versions antérieures restent consultables.

### 13.5 Opérations manuelles et exemples

Saisie : méthode, chemin relatif, paramètres path/query, en-têtes
(hors `Authorization`, `Cookie`, `Host`…), schémas JSON sans `$ref`
(64 Ko, profondeur 20), mécanisme d’auth **déclaré** (pas de secret),
codes de réponse. Une opération importée ne se « corrige » pas : nouvel
import. Archivage sans suppression.

Exemples (`exemples_externes.py`) : cURL, Python `httpx`, TypeScript
`fetch`, variables `EXTERNAL_API_BASE_URL`, `EXTERNAL_API_TOKEN`,
`EXTERNAL_API_USERNAME`, `EXTERNAL_API_PASSWORD`. Marqués **non
testés**. `elements_verifies` est toujours vide. Échappement shell /
JSON / retours à la ligne (y compris U+2028).

### 13.6 Routes et permissions

Préfixe `/api/v1/plateforme/admin/integrations/fournisseurs`, Login 1,
exclues du catalogue. Permissions seedées, **attribuées à aucun rôle**,
sans suffixe `.admin`.

| Route | Permission |
|-------|-----------|
| `GET /`, `GET /{id}`, `GET /{id}/historique`, `GET /{id}/specs`, `GET /{id}/specs/{spec_id}`, `GET /{id}/operations`, `GET /{id}/operations/{op_id}` | `fournisseurs.view` |
| `POST /`, `PATCH /{id}`, `POST /{id}/archive`, analyse / import, CRUD opérations manuelles | `fournisseurs.manage` |
| `POST /{id}/statut` | `manage` ou `validate` selon la transition |

### 13.7 Interface

`/admin/integrations/fournisseurs` (menu **API externes**, permission
`fournisseurs.view`), `/nouveau`, `/:id/modifier`, `/:id` (onglets
Opérations, Import OpenAPI, Versions, Historique),
`/:id/operations/:opId`, formulaire manuel. Bandeau persistant :
**« Configuration enregistrée — aucun appel externe effectué. »**
Confirmation via `BeaAdminDialogService`, garde
`unsavedChanges`, succès après réponse serveur seulement.

### 13.8 Tests

- Backend `tests/test_integration_fournisseurs.py` (base jetable
  `bea_digital_phase4_test`, `current_database()`, garde DNS
  `getaddrinfo` + transports HTTP bloqués) : permissions, 16 routes,
  colonnes sans secret, migration, AST sans import réseau, parseur
  (JSON/YAML, versions, `$ref`, cycles, limites, secrets, chemins),
  exemples, flux import/conflits/manuel, transitions, 413.
- Phase 1–4 + préparation M2M : 195 réussis (ruff propre).
- Front `core-admin-integration-fournisseurs.spec.ts` : URL, schéma,
  menu, multipart, bandeau, refus secret, aperçu/conflits/empreinte,
  exemples non testés, cohérence manuelle. Karma Phases 1–4 : 48
  réussis ; `ng build` réussi.

### 13.9 Application de la migration (procédure, non exécutée hors jetable)

Après validation écrite, sur TEST uniquement : `pg_dump`, puis
`alembic upgrade head`, contrôle `alembic current` =
`20261021_integrations_02`. **Jamais** en production sans
approbation. Retour : `alembic downgrade -1` (supprime les 3 tables).

### 13.10 Limites

- Authentification M2M toujours non activée (§ 12).
- Les exemples ne prouvent pas que l’API existe.
- Les appels sortants sont désormais ceux de la Phase 5 (§ 14), uniquement
  vers une destination TEST approuvée, sans secret.

## 14. Phase 5 — Exécution sécurisée des API externes

Configuration (Phase 4) et exécution sont séparées. Ouvrir une fiche, importer
une spécification ou consulter l’historique **ne déclenche aucun appel**.

### 14.1 Parcours

1. Destination TEST créée puis approuvée (`destinations.approve`).
2. Opération GET/HEAD, fournisseur `valide` en TEST, mécanisme `aucun`.
3. Aperçu (`POST /tests/apercu`) : URL construite côté serveur, aucun réseau.
4. Confirmation explicite puis `POST /tests/executer` : toutes les validations
   sont refaites avant l’appel.

Le frontend n’envoie jamais d’URL. Corps : `fournisseur_id`, `operation_id`,
`destination_id`, paramètres déclarés, `confirmation: true`.

### 14.2 Destinations autorisées

Table `integration_destinations` (migration `20261021_integrations_03`).
Environnement figé `TEST`, protocole `https`, port **443** uniquement.
Hôtes normalisés (IDNA), refus des IP non globales, `localhost`, suffixes
`.local` / `.internal`, métadonnées cloud, formes numériques / `0x`.

Statuts : `brouillon` → `a_valider` (`manage`) → `active` (`approve`) →
`suspendue` (`approve` + motif). Historique via `audit_logs`.

### 14.3 Protection SSRF

Module `backend/app/services/integrations/ssrf.py` + exécuteur
`executeur.py` :

- HTTPS seulement, pas d’identifiants dans l’URL (`userinfo`).
- Résolution DNS : **toutes** les adresses doivent être `is_global`.
- Connexion épinglée sur l’IP vérifiée (`_TransportEpingle`) avec SNI / Host
  du nom approuvé (validation TLS du nom d’hôte conservée).
- Redirections **désactivées** ; un 3xx est enregistré `redirection_refusee`
  et **aucune** requête n’est envoyée vers `Location`.
- Délais : connexion 3 s, lecture 8 s. Corps max 64 Kio, extrait 2 Kio assaini.
- `trust_env=False`, pas de cookies ni jetons Login 1/2, pas d’en-têtes
  internes. Quotas Redis (10/utilisateur/10 min, 20/fournisseur/10 min,
  3 simultanés) — indisponibilité Redis = refus (503 / `quota`).

Ce n’est pas un proxy HTTP générique.

### 14.4 Secrets

Aucun coffre fournisseur n’est approuvé. `secret_box` reste réservé à la MFA.
Une opération dont `mecanisme_auth` ≠ `aucun` est refusée (`SECRET_REQUIS`).
Les tests n’utilisent que des transports simulés.

### 14.5 Permissions (non attribuées aux rôles)

`core.admin.integrations.destinations.view|manage|approve`,
`core.admin.integrations.tests.view|execute`.
Login 2 refusé. Le bouton Angular n’est pas un contrôle d’accès.

### 14.6 Routes

`/api/v1/plateforme/admin/integrations/destinations/*`,
`/tests/apercu`, `/tests/executer`, `/executions`, `/executions/{id}`.

UI : `/admin/integrations/destinations…`, onglet « Test contrôlé » sur le
fournisseur.

## 15. Phase 6 — Supervision des intégrations

Aucune sonde périodique. Les indicateurs viennent des exécutions
réellement enregistrées. Une fiche approuvée n’est pas « disponible ».
Sans test : libellé **« Aucune donnée »**, jamais 0 % de disponibilité.

### 15.1 Historique et rétention

Table `integration_executions` : corrélation, durée, statut, HTTP,
catégorie, contrôles SSRF, limites, extrait assaini (pas de corps
complet, pas de secret). Rétention documentée : **90 jours** (purge
non automatique dans ce chantier).

Disponibilité dérivée du dernier test : `disponible_dernier_test`,
`en_erreur`, `testee`, `inconnue`.

### 15.2 Alertes

Table `integration_alertes`. Types : `echecs_consecutifs` (3),
`taux_erreur` (≥ 50 % / 10), `latence` (≥ 5 000 ms), `non_testee`
(7 jours, évaluée à la lecture du tableau), `destination_suspendue`,
`refus_securite`. Déduplication tant que l’alerte est `nouvelle` ou
`en_cours`. Statuts : nouvelle, en cours, résolue, ignorée. Une alerte
ne déclenche **jamais** d’appel sortant.

### 15.3 Permissions et routes

`core.admin.integrations.supervision.view|manage|export`.
`GET /supervision`, `/supervision/alertes`, `PATCH …/alertes/{id}`,
`GET /supervision/export` (CSV `;`, préfixe `'` anti-injection de
formule, audité). UI : `/admin/integrations/supervision`.

### 15.4 Tests

- Unitaires SSRF : `backend/tests/test_ssrf.py` (pas de réseau).
- Accès + exécution simulée : `backend/tests/test_integration_execution.py`
  (MockTransport, DNS injecté, base jetable — jamais `bea_digital`).
- Karma : `core-admin-integration-execution.spec.ts`.

Aucun fournisseur public n’est contacté. Les tests de connectivité réelle
restent hors périmètre (validation DSI + destination TEST approuvée).

### 15.5 Migration `20261021_integrations_03`

Additive, `retour_arriere = compatible`. **Non appliquée** sur la base
métier. Procédure future (TEST seulement, après validation) : `pg_dump`,
`alembic upgrade head`, contrôle `20261021_integrations_03`. Retour :
`alembic downgrade -1`.

### 15.6 Risques résiduels (avant activation réelle)

- Pas de coffre de secrets : les API authentifiées restent bloquées.
- GET peut avoir des effets de bord chez un fournisseur mal conçu.
- Quotas Redis fail-closed : indisponibilité Redis = pas de test.
- Rétention 90 jours non purgée automatiquement.
- TLS et DNS réels non exercés dans la CI (simulateur seulement).
- Phase 3 M2M toujours arrêtée. Aucun appel PROD.

## 16. Finalisation UI/UX dans CORE ADMIN

### 16.1 Pourquoi le Studio n’apparaissait pas (diagnostic du 21/10/2026)

Trois causes cumulées, toutes vérifiées :

1. **Code non déployé.** L’application servie sur `http://localhost`
   (`bea-frontend`, image nginx statique du 20/10 10:51) ne contient aucune
   chaîne du Studio ; le conteneur `bea-backend` ne contient aucun fichier
   `core_admin_integration*.py`. Le code des Phases 1–6 n’existe que dans le
   dépôt (non commité, non construit dans les images).
2. **Base réelle non migrée.** `bea_digital` est à `20261020_clientele_14` :
   aucune table `integration_*`, aucune ligne `core.admin.integrations.*` dans
   `permissions`. Les lignes de permission sont créées au démarrage du backend
   (`_ensure_permissions`, additif) une fois le nouveau code déployé ; les
   tables exigent les migrations `20261021_integrations_01..03`.
3. **Permissions attribuées à aucun rôle (voulu).** Même déployé, un
   administrateur non superutilisateur ne voit que les entrées pour
   lesquelles il détient la permission. Sans aucune permission Studio, le
   groupe entier est masqué.

Défaut corrigé au passage : « Vue d’ensemble », « Catalogue » et « Console »
étaient affichés sans condition alors que le serveur exige
`core.admin.integrations.view` (liens menant à un 403). Ils sont désormais
filtrés comme le serveur.

**Déploiement local du 21/10/2026** : sauvegarde
`backups/local-20261021-115657.dump`, `alembic upgrade head` sur
`bea_digital` (`20261020_clientele_14` → `20261021_integrations_03`), images
`bea-digital-backend` et `bea-digital-frontend` reconstruites, services
`backend` / `worker` / `frontend` redémarrés, catalogue synchronisé
(18 permissions `core.admin.integrations.*`, liées à aucun rôle). Accès : le
seul compte CORE ADMIN est superutilisateur et reçoit donc toutes les
permissions ; aucun rôle créé. Retour arrière : `alembic downgrade
20261020_clientele_14` ou restauration du dump.

### 16.2 Menu « Studio d’intégration API »

| Entrée | Route | Visible si |
|---|---|---|
| Vue d’ensemble | `/admin/integrations` | au moins une permission Studio `*.view` / `tests.execute` |
| Catalogue API | `/admin/integrations/catalogue` | `core.admin.integrations.view` |
| Console (lecture) | `/admin/integrations/console` | `core.admin.integrations.view` |
| Applications clientes | `/admin/integrations/clients` | `…clients.view` |
| Fournisseurs externes | `/admin/integrations/fournisseurs` | `…fournisseurs.view` |
| Destinations TEST | `/admin/integrations/destinations` | `…destinations.view` |
| Tests d’intégration | `/admin/integrations/tests` | `…tests.execute` ou `…tests.view` |
| Historique des exécutions | `/admin/integrations/executions` | `…tests.view` |
| Supervision | `/admin/integrations/supervision` | `…supervision.view` |
| Alertes | `/admin/integrations/alertes` | `…supervision.view` |

Pas d’entrée « Paramètres » : aucun écran de paramétrage réel n’existe
(seuils et quotas sont des constantes serveur). Le superutilisateur et `*`
voient tout. Le masquage est un confort : chaque route serveur revérifie.
Accès direct à une URL sans permission : message « Accès refusé » listant les
permissions requises, sans appel réseau. Login 2 : `coreAdminGuard` exige le
jeton plateforme (Login 1) → redirection `/login` ; le serveur répond 401.

Sur la page **Tests**, préparer un test exige en plus `…fournisseurs.view` et
`…destinations.view` (lecture des opérations et destinations) ; elle le dit
explicitement au lieu d’échouer.

### 16.3 Attribution manuelle (par un administrateur autorisé uniquement)

Rien n’est attribué automatiquement. Après déploiement (code + migrations,
voir 11.6 / 13.9 / 15.5), un administrateur disposant de
`core.admin.roles` :

1. CORE ADMIN → **Rôles** → créer un rôle dédié (ex. « Studio — lecture »,
   « Studio — exploitation TEST »), ou ouvrir un rôle existant choisi par la
   gouvernance ;
2. cocher les permissions nécessaires (profils indicatifs ci-dessous) ;
3. CORE ADMIN → **Utilisateurs** → affecter le rôle ;
4. l’utilisateur se **déconnecte puis se reconnecte** (les permissions sont
   lues dans le profil à la connexion).

| Profil indicatif | Permissions |
|---|---|
| Lecture | `integrations.view`, `clients.view`, `fournisseurs.view`, `destinations.view`, `tests.view`, `supervision.view` |
| Exploitation TEST | Lecture + `tests.execute`, `supervision.manage` |
| Configuration | Lecture + `fournisseurs.manage`, `destinations.manage`, `clients.manage`, `grants.manage` |
| Validation (personne distincte) | `fournisseurs.validate`, `destinations.approve`, `grants.approve` |
| Export | `supervision.export`, `integrations.export` |

(préfixe `core.admin.integrations.` omis). Séparer configuration et
validation.

### 16.4 Écrans

- **Vue d’ensemble** : fournisseurs configurés / validés, opérations
  externes, destinations TEST approuvées (et suspendues), tests des 7 derniers
  jours et taux de succès, alertes nouvelles / en cours, 5 dernières
  exécutions, légende des statuts (validation ≠ connectivité ≠
  disponibilité), catalogue interne. Chaque indicateur n’est chargé que si la
  permission correspondante est détenue (sinon « Permission requise »).
  « Aucune donnée » quand rien n’existe. Aucun appel au tableau de
  supervision (dont la lecture peut ouvrir une alerte « non testée »).
- **Tests** : choix d’un fournisseur validé TEST, opération GET/HEAD,
  destination approuvée, paramètres déclarés ; aperçu sans réseau ; toute
  modification invalide l’aperçu ; exécution après confirmation ; résultat
  (statut, catégorie, HTTP, latence, corrélation, extrait assaini) ; messages
  dédiés quota / quota indisponible / secret requis / délai / TLS / refus.
  Opération authentifiée (mécanisme ≠ `aucun`) : test bloqué côté écran et
  serveur.
- **Historique** : paginé, filtres période (24 h / 7 j / 30 j / rétention /
  personnalisée), fournisseur, opération, destination, statut ; environnement
  affiché (TEST seul) ; détail complet ; filtres conservés dans l’URL.
- **Supervision** : mêmes périodes, fournisseur, destination ; dernier test,
  dernier succès / échec, répartition par catégorie (fournisseur /
  connectivité / blocage BEA DIGITAL), destinations sans mesure ou suspendues.
- **Alertes** : filtres niveau, type, statut, date de dernière occurrence ;
  détail de la règle ; prise en charge / résolution / ignorer après
  confirmation, journalisées.
- **Export CSV** : mêmes filtres que l’écran (dont opération et statut),
  500 lignes les plus récentes, export vide signalé sans appel, anti-injection
  conservée, colonnes fournisseur / opération / destination / environnement.
- **Destination** : opérations autorisées, motif de statut, derniers tests,
  historique des modifications, lien vers la page Tests.

Contrats ajoutés (lecture seule, aucun appel sortant) : `GET /executions`
renvoie les noms fournisseur / opération / destination et l’environnement ;
`GET /supervision/alertes` accepte `niveau`, `depuis`, `jusqua` et renvoie
`niveau`, `regle`, `resolue_le` ; `GET /supervision/export` accepte
`operation_id` et `statut`. Niveau d’alerte = correspondance fixe par type
(`echecs_consecutifs`, `taux_erreur`, `refus_securite` → élevé ; `latence`,
`destination_suspendue` → moyen ; `non_testee` → information).

## 17. Refonte UI/UX (CRUD complet, suppression sûre, assistant de test)

### 17.1 Principes visuels

Habillage commun dans `core-admin-integrations.styles.ts` (variables `--bea-*`,
aucune bibliothèque, aucune dépendance npm) : cartes, en-têtes de section
numérotés, badges, squelettes de chargement, états vides, barre d’actions
collante sur les formulaires, tableaux en cartes sous 720 px. Animations CSS
courtes (apparition, croissance des barres, spinner pendant une action), jamais
bloquantes, coupées par `prefers-reduced-motion`. Thème sombre via
`:host-context(html[data-theme='dark'])`. Graphiques en CSS/SVG
(`construireGraphe`, `courbe`) à partir des seules données serveur.

### 17.2 Suppression définitive — jamais en cascade

Parcours unique (`IntegrationSuppressionService`) : `GET …/dependances` (bilan
serveur) → si bloqué, message listant conditions et dépendances + alternative
(archiver / suspendre), aucun `DELETE` → sinon confirmation « Supprimer
définitivement » → `DELETE …?revision=` (révision du bilan, 409 si l’objet a
changé) → succès affiché seulement après la réponse → liste rechargée.

| Ressource | Supprimable si | Sinon |
|---|---|---|
| Application cliente | brouillon, aucune habilitation ni événement d’habilitation | archiver |
| Fournisseur | brouillon / à valider, jamais validé, sans spécification, opération, destination, exécution ni alerte | archiver |
| Destination | brouillon / à valider, jamais approuvée, sans exécution ni alerte | suspendre / archiver |
| Opération manuelle | fournisseur modifiable, non référencée par une destination, sans exécution ni alerte | archiver |
| Opération importée | jamais (appartient à sa version) | importer une nouvelle version |
| Exécution, alerte | jamais (preuves, traces d’incident) | rétention / statut |

Routes (Login 1, permission `…manage` correspondante) :
`GET|DELETE /clients/{id}[/dependances]`, `GET|DELETE /fournisseurs/{id}[/dependances]`,
`GET|DELETE /fournisseurs/{id}/operations/{op}[/dependances]`,
`GET|DELETE /destinations/{id}[/dependances]`. Chaque suppression est
journalisée (`integration_*_delete`). Aucune route `DELETE` sur les exécutions
ni les alertes.

### 17.3 Listes

Recherche, filtres, tri par en-tête (`aria-sort`), pagination, actualisation,
filtres conservés dans l’URL, actions par ligne masquées sans permission.
Ajouts serveur : destinations `tri`/`ordre` + `fournisseur_nom`,
`nb_operations` ; exécutions `q` (corrélation, chemin, hôte), `tri`
(`started_at`, `duree_ms`, `statut`, `http_status`), `ordre` ; alertes
`fournisseur_id`, `q`, `compteurs` par statut, noms liés, `transitions`.

### 17.4 Formulaires

Sections numérotées, libellés visibles, aide, champs obligatoires marqués,
erreurs sous le champ (`aria-invalid`, `aria-describedby`), erreur serveur en
ligne (saisies conservées), double soumission impossible, garde de
modifications non enregistrées. Destination : fournisseur choisi dans une liste
et **opérations autorisées cochées** ; la restriction existante est renvoyée à
chaque modification (l’ancien formulaire envoyait `operations: []`, ce qui
élargissait en silence la destination à toutes les opérations).

### 17.5 Assistant de test

Étapes : Sélection → Paramètres → Aperçu (sans appel sortant) → Confirmation →
Résultat. Aucun appel au chargement, au choix d’une opération, à l’aperçu ni à
l’enregistrement d’un formulaire ; l’exécution exige le clic « Exécuter le
test » puis la confirmation. États visuels distincts (texte + couleur) :
attente, en cours, succès, échec HTTP, erreur réseau, refus, secret requis,
quota, délai.

### 17.6 Alertes

Compteurs cliquables (actives, nouvelles, en cours, résolues, ignorées),
actions issues des transitions serveur : nouvelle → en cours / résolue /
ignorée ; en cours → résolue / ignorée ; résolue ou ignorée → **rouvrir**
(refusé, 409 `ALERTE_DEJA_OUVERTE`, si une alerte identique est déjà ouverte).
Transition interdite : 409 `TRANSITION_INTERDITE`. Historique du traitement :
`GET /supervision/alertes/{id}/historique` (journal d’audit). Aucune suppression.
