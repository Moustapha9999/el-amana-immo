# BEA DIGITAL --- Référentiel de sécurité, fiabilité, performance et préparation à la production

**Version :** 1.0\
**Date :** 26 octobre 2026\
**Statut initial :** à auditer --- aucune mesure n'est considérée comme
validée sans preuve.

## 1. Objectif

Ce document centralise les contrôles à examiner et les actions à
planifier pour rendre BEA DIGITAL plus sûr, fiable, maintenable,
performant et prêt à évoluer. Il sert de feuille de route pour l'audit
technique, les tests, la préparation à la production et les échanges
avec la DSI.

**Règle essentielle :** un contrôle n'est « vérifié » que si une preuve
existe : test exécuté, mesure, restauration réussie, configuration revue
ou validation formelle. Une liste cochée sans preuve ne constitue pas
une validation.

## 2. Contexte connu et limites

Architecture communiquée : - Frontend : Angular 20 SPA. - Backend :
FastAPI/Uvicorn. - Base : PostgreSQL, SQLAlchemy asynchrone, Alembic. -
Tâches asynchrones : Celery et Redis. - Conteneurs : Docker Compose. -
Reverse proxy : Nginx. - Environnement actuel décrit : PC local,
PostgreSQL sur la même machine, tests avec quelques utilisateurs. -
Cible à évaluer : environ 100 utilisateurs simultanés. - Outil de test
de charge choisi : Locust.

Ces éléments doivent être vérifiés dans le dépôt et la configuration
réels.

### Interdictions durant l'audit initial

-   Ne pas déployer en production ni lancer de migration sur une base de
    production.
-   Ne pas utiliser de données clients réelles pour les tests.
-   Ne pas tester des systèmes externes bancaires (ORION, BCM/SIC ou
    autres) sans autorisation explicite.
-   Ne pas supprimer/écraser des données, modifier les contrôles
    d'authentification ou exposer des secrets.
-   Ne pas inventer de modules, routes, règles métier, intégrations ou
    outils déjà en place.
-   Ne pas lancer de test de charge avant d'avoir confirmé
    l'environnement, les scénarios, les données synthétiques et les
    seuils d'arrêt.

## 3. Méthode d'audit

1.  **Inventorier** l'architecture, les modules, routes, permissions,
    modèles DB, migrations, tests, tâches, sauvegardes, conteneurs et
    pipelines.
2.  **Établir les faits** : chaque constat doit renvoyer à un fichier,
    une configuration, un test ou une observation reproductible.
3.  **Classer les risques** selon impact métier, probabilité et
    exposition.
4.  **Proposer une correction** avec composants concernés, dépendances
    et risque de régression.
5.  **Tester** avant de déclarer la correction terminée.
6.  **Conserver les preuves** sans secrets ni données sensibles.
7.  **Ne pas déployer en production** sans autorisation et procédure
    approuvée.

Distinguer dans tous les rapports : **constaté**, **déduit**,
**recommandé**, **non vérifié**.

### Statuts

-   **NON AUDITÉ** : pas d'examen suffisant.
-   **À CORRIGER** : défaut confirmé.
-   **EN COURS** : action en cours.
-   **À VALIDER** : correction faite, preuve finale manquante.
-   **VÉRIFIÉ** : contrôle testé, preuve conservée.
-   **ACCEPTÉ AVEC RISQUE** : exception approuvée, justifiée, avec
    responsable, mesures compensatoires et date d'expiration.
-   **NON APPLICABLE** : avec justification.

### Priorités

-   **P0 Critique** : risque immédiat de compromission, perte/corruption
    de données ou exposition grave.
-   **P1 Haute** : à traiter avant mise en production.
-   **P2 Moyenne** : robustesse et maintenabilité.
-   **P3 Amélioration** : optimisation à planifier.

Les priorités définitives sont établies après audit et selon les règles
de la banque.

## 4. Sécurité applicative

### 4.1 Authentification et comptes

Examiner : - stockage des mots de passe avec un algorithme adapté et
maintenu (par exemple Argon2id, correctement configuré) ; - limitation
des tentatives, protection contre force brute et credential stuffing ; -
messages d'erreur ne révélant pas inutilement si un compte existe ; -
réinitialisation de mot de passe, MFA/TOTP selon la politique de la
banque ; - désactivation des comptes et révocation des accès ; - comptes
inactifs, comptes de test et comptes d'administration ; - journaux des
connexions réussies/échouées et événements de sécurité.

**Preuves :** tests de connexion, limitation des tentatives, compte
désactivé, MFA et paramètres de hachage.

### 4.2 Sessions et jetons

Vérifier : - durée de vie des access/refresh tokens ; - expiration et
révocation côté serveur ; - déconnexion et invalidation après
désactivation de compte ou changement de privilèges ; - cohérence des
sessions plateforme/module si cette séparation existe ; - vérification
serveur des permissions pour chaque action sensible ; - risque XSS du
stockage en `localStorage` ; - pertinence de cookies `HttpOnly`,
`Secure`, `SameSite` et protection CSRF selon l'architecture ; -
prévention du rejeu des refresh tokens.

Ne pas remplacer le mécanisme actuel sans analyser les impacts
Angular/FastAPI et les modules existants.

### 4.3 Autorisations et permissions

Contrôler : - refus par défaut ; - permissions réellement vérifiées dans
le backend, pas seulement masquées dans Angular ; - autorisation au
niveau objet/ressource (IDOR/BOLA) ; - séparation des fonctions
incompatibles ; - accès inter-agences, inter-services et
inter-utilisateurs ; - contrôle des exports, téléchargements,
suppressions et actions admin ; - tests négatifs pour chaque rôle ; -
journalisation des actions privilégiées.

**Preuves :** matrice rôles/permissions et tests positifs/négatifs sur
les routes et ressources.

### 4.4 Validation et sécurité API

Vérifier : - validation stricte des entrées, types, formats, plages et
valeurs ; - limites de taille des requêtes, imports et fichiers ; - CORS
limité aux origines autorisées ; - erreurs sans stack trace en
production ; - protection contre injection SQL, XSS, CSRF, SSRF et
désérialisation dangereuse selon les surfaces ; - pagination, limites
des listes et filtres/tris dynamiques ; - rate limiting des routes
sensibles ; - cohérence OpenAPI/routes ; - politique de version des API.

Pour toute fonctionnalité permettant d'appeler une URL configurable,
analyser le risque SSRF : localhost, réseaux privés, endpoints de
métadonnées, redirections, schémas interdits, DNS rebinding et timeouts.

### 4.5 Angular

Examiner : - absence de secrets dans le code et les builds ; - rendu sûr
du contenu et usages de HTML non fiable ; - usages de
`bypassSecurityTrust...` ; - guards considérés comme UX seulement,
jamais comme seule autorisation ; - gestion des sessions expirées et
erreurs ; - prévention des doubles soumissions ; - CSP adaptée et testée
; - dépendances npm et scripts de build ; - absence de données sensibles
dans les logs navigateur.

### 4.6 Fichiers, GED et exports

Vérifier : - extensions autorisées, type réel et taille maximale ; -
nommage sûr et stockage hors répertoire public ; - permissions à chaque
téléchargement ; - protection contre traversée de répertoires ; -
antivirus (ex. ClamAV) uniquement si réellement intégré ; - quotas et
sauvegarde du stockage ; - protection des exports contre les fuites ; -
neutralisation des formules dangereuses dans CSV/XLSX ; - rétention,
suppression et traçabilité des fichiers.

### 4.7 Docker et OS

Contrôler : - images maintenues et versions explicites ; - exécution
non-root si possible ; - privilèges et capacités minimaux ; - absence de
secrets dans Git et images ; - ports exposés limités ; - volumes
persistants identifiés et sauvegardés ; - PostgreSQL/Redis sur réseau
interne, non exposés publiquement ; - limites CPU/RAM testées ; - scans
et mises à jour d'images ; - accès admin au serveur/PC, mises à jour OS
et protection du disque.

## 5. Données, confidentialité et auditabilité

### 5.1 Classification

Définir avec la banque les catégories de données, droits d'accès, règles
de rétention, besoins de masquage et règles d'utilisation des données en
TEST. Utiliser des données synthétiques ou anonymisées approuvées pour
les tests de charge.

### 5.2 Chiffrement et secrets

Contrôler : - TLS pour les connexions réseau pertinentes ; -
certificats, renouvellement et alertes d'expiration ; - chiffrement des
sauvegardes et fichiers sensibles selon la politique ; -
gestion/rotation des clés ; - séparation des secrets TEST/PROD ; -
secrets hors du code et du frontend ; - aucun secret/token/donnée
sensible inutile dans les URLs, logs, tickets ou rapports Locust.

### 5.3 Journaux d'audit

Définir les événements sensibles à tracer : acteur, date/heure fiable,
action, objet concerné, résultat, identifiant de corrélation et motif si
requis. Ne jamais journaliser mots de passe, tokens, secrets TOTP ou
clés privées. Protéger les journaux contre l'altération et limiter leur
accès. Définir la conservation selon les règles de la banque.

## 6. Intégrité métier et concurrence

### 6.1 Transactions et contraintes

Examiner : - transactions PostgreSQL pour les opérations atomiques ; -
contraintes `NOT NULL`, `UNIQUE`, clés étrangères et `CHECK` pour les
invariants ; - cohérence entre validation applicative et contraintes DB
; - rollback en cas d'erreur ; - durée des transactions et verrous ; -
cohérence entre opération métier, audit et fichiers.

### 6.2 Deux utilisateurs sur la même opération

Identifier les opérations modifiables simultanément et choisir le
mécanisme adapté : - verrouillage optimiste par version/horodatage ; -
verrouillage pessimiste ciblé (`SELECT ... FOR UPDATE`) lorsque
nécessaire ; - contraintes transactionnelles ; - transitions d'état
contrôlées côté serveur ; - message explicite en cas de conflit.

Ne pas utiliser un verrou global partout et ne pas dépendre uniquement
de la désactivation d'un bouton Angular.

**Test obligatoire :** deux sessions modifient le même objet ; vérifier
qu'aucune mise à jour n'est silencieusement perdue et que les invariants
métier restent vrais.

### 6.3 Idempotence et doubles soumissions

Pour les opérations rejouées après double clic, timeout ou retry : -
définir l'idempotence ; - utiliser une clé d'idempotence ou contrainte
métier si adaptée ; - rendre les tâches Celery relançables sans doublons
; - traiter les résultats incertains ; - éviter de créer deux opérations
métier lors d'une requête rejouée.

### 6.4 États métier et imports

-   Transitions d'état autorisées vérifiées côté serveur.
-   Actions sensibles journalisées.
-   Tests des transitions normales, refusées, concurrentes et de
    reprise.
-   Imports avec prévisualisation, détection des doublons et erreurs.
-   Choix explicite entre import atomique et partiel.
-   Pas de modification partielle non signalée.
-   Tests de fichiers volumineux et d'erreurs en milieu de lot.

## 7. Sauvegarde, durabilité et restauration

### 7.1 Inventaire

Identifier tout ce qui doit être sauvegardé : PostgreSQL, fichiers
GED/pièces jointes, configurations indispensables, documentation et
éléments de reprise. Une sauvegarde DB seule ne suffit pas si les
fichiers associés sont nécessaires.

### 7.2 PostgreSQL

Évaluer sauvegardes logiques ou physiques, fréquence, archivage WAL/PITR
si justifié par le RPO, contrôle d'intégrité, compatibilité de version
et alertes sur les échecs. Ne pas choisir une stratégie sans objectifs
de reprise.

### 7.3 Protection

-   Copie séparée du PC/serveur principal.
-   Droits limités et chiffrement selon politique.
-   Protection contre suppression accidentelle/malveillante.
-   Rétention et rotation documentées.
-   Procédure de récupération des clés nécessaires.

### 7.4 Restauration

Réaliser des exercices en environnement isolé : restaurer DB et
fichiers, vérifier versions/migrations, relations, contrôles métier,
durée réelle et écarts. **Une sauvegarde n'est fiable qu'après une
restauration testée.**

### 7.5 RPO/RTO

-   **RPO** : perte de données maximale acceptable, exprimée en durée.
-   **RTO** : durée maximale visée pour rétablir le service.

Ces objectifs doivent être approuvés par les responsables
métier/techniques. Mesurer les résultats réels lors des exercices.

## 8. Disponibilité et continuité

Le PC local peut être un point de défaillance unique : panne électrique,
disque, arrêt du PC, réseau ou accès physique peuvent rendre le service
indisponible. Documenter les dépendances : hôte, disque, réseau,
PostgreSQL, Redis/Celery, Nginx, FastAPI, services externes et
sauvegardes.

Contrôler : - health checks sans fuite de secrets ; - redémarrages
maîtrisés et absence de boucle de crash ; - surveillance
CPU/RAM/disque/inodes/connexions ; - tests d'indisponibilité des
dépendances ; - procédure de diagnostic et de remise en service ; -
fenêtre de maintenance et communication aux utilisateurs.

### Load balancing et haute disponibilité

Ne pas déployer un cluster ou load balancer par principe. D'abord
mesurer les limites et définir les objectifs.

Avant plusieurs instances, vérifier : - état de session partagé ou
compatible ; - instances identiques et health checks ; - budget total
des connexions PostgreSQL ; - comportement Celery et prévention des
doublons ; - stockage partagé/cohérent des fichiers ; - point de
défaillance du load balancer ; - déploiement et rollback.

Un load balancer devant une seule instance ne rend pas cette instance
hautement disponible.

Préparer un plan de continuité : responsables, critères d'incident
majeur, communications, ordre de reprise, vérifications d'intégrité,
conservation des preuves et retour à la normale.

## 9. Observabilité et alertes

### Logs

Logs structurés et corrélables pour requêtes HTTP, erreurs,
authentification/autorisation, opérations sensibles, tâches Celery,
dépendances et déploiements. Ne pas y placer de secrets ou données
personnelles inutiles.

### Métriques minimales

-   disponibilité, volume de requêtes, taux d'erreur ;
-   latences p50/p95/p99 ;
-   CPU, RAM, disque et croissance des fichiers ;
-   connexions, verrous et requêtes lentes PostgreSQL ;
-   mémoire Redis, taille des files Celery, tâches en échec et âge de la
    plus ancienne ;
-   âge/résultat des sauvegardes ;
-   certificats et dates d'expiration.

### Alertes

Définir seuils après observation de la baseline. Exemples : API
indisponible, hausse durable d'erreurs/latence, disque presque plein,
saturation DB, verrous anormaux, backlog Celery croissant, sauvegarde en
échec, certificat proche de l'expiration, échecs de connexion anormaux.

Chaque alerte doit avoir une gravité, un responsable et une procédure.
Éviter les alertes sans action possible.

## 10. Résilience et erreurs

Vérifier : - timeouts sur appels réseau et base ; - retries limités,
backoff exponentiel et jitter ; - pas de retry aveugle d'opérations non
idempotentes ; - limites de ressources et de concurrence ; - erreurs
utiles sans détails internes sensibles ; - isolation des intégrations
externes ; - circuit breaker seulement si justifié ; - reprise après
interruption d'un worker ; - tâches Celery en échec et files mortes si
applicable ; - absence de retry infini ; - résultat métier vérifiable
après exécution d'une tâche.

Tester dans un environnement contrôlé timeout, refus de connexion,
réponse invalide, indisponibilité temporaire et tâche interrompue.

## 11. Performance et scalabilité

### FastAPI

Mesurer latence par route, durée métier, temps DB, appels externes,
sérialisation, tâches bloquantes, CPU/RAM et comportement sous
concurrence. Ne pas supposer qu'une fonction est non bloquante parce
qu'elle est déclarée `async`.

### PostgreSQL/SQLAlchemy

Examiner requêtes lentes/plans, index, N+1 queries, pagination,
transactions, pool SQLAlchemy, nombre total de connexions avec plusieurs
workers/instances, contention, croissance et maintenance des tables.
Ajouter des index seulement si les mesures le justifient.

### Angular

Examiner poids initial du bundle, chargement différé, appels redondants,
pagination serveur, grands tableaux, retries et réseau réaliste.

### Cache

N'ajouter un cache que si un besoin est mesuré. Définir durée de vie,
invalidation, cohérence, risque de données/permissions périmées et
comportement si Redis tombe.

### 100 utilisateurs

Distinguer sessions ouvertes, utilisateurs actifs, requêtes simultanées
et RPS. Définir un mélange de parcours : lecture, recherche,
création/modification, imports/exports et opérations coûteuses. Mesurer
les limites de l'application **et** de la base de données. Ne pas
annoncer une capacité avant un test représentatif.

## 12. Tests de charge avec Locust

Documentation officielle : https://docs.locust.io/

### 12.1 Préconditions de sécurité

-   Environnement autorisé et isolé uniquement.
-   Jamais de test en production ou vers un système bancaire externe
    sans autorisation explicite.
-   Comptes et données synthétiques.
-   Pas de secrets dans le code, les rapports ou logs.
-   Fenêtre, responsable et seuils d'arrêt définis.
-   Surveillance simultanée de FastAPI, PostgreSQL, Redis, Celery et de
    l'hôte.
-   Scénarios d'écriture réinitialisables ou données jetables.
-   Désactiver/simuler les notifications et effets externes.
-   Arrêt immédiat si saturation, erreurs anormales, latences excessives
    ou incohérence de données.

### 12.2 Scénarios

Après découverte des routes réellement disponibles, envisager : -
connexion avec comptes de test si le flux est adapté ; - tableaux de
bord ; - listes paginées et filtres ; - détail d'un enregistrement ; -
recherche ; - création/modification d'objets de test ; - opérations
concurrentes sur ressources distinctes ; - exports/rapports coûteux
s'ils peuvent être testés sans risque ; - tâches asynchrones observées
jusqu'à leur résultat.

Ne pas inventer d'endpoints : inspecter le code/OpenAPI et confirmer les
préconditions métier.

### 12.3 Profils de test

Ces profils sont des propositions à adapter, pas des objectifs de
performance déjà validés.

1.  **Smoke** : 1--3 utilisateurs, quelques minutes.
2.  **Baseline** : faible charge stable pour mesurer la référence.
3.  **Montée progressive** : paliers tels que 5, 10, 25, 50, 75 puis 100
    utilisateurs, uniquement si le système reste sain.
4.  **Charge cible** : maintenir une charge représentative autour de 100
    utilisateurs pendant une durée convenue.
5.  **Stress** : dépasser progressivement la cible pour identifier la
    saturation, en environnement autorisé avec seuils d'arrêt.
6.  **Soak** : charge modérée prolongée pour détecter fuites mémoire,
    connexions ou files qui croissent.
7.  **Pic** : hausse rapide de charge si ce scénario est pertinent.
8.  **Récupération** : réduire/arrêter la charge et mesurer le retour à
    la normale.

Commencer par smoke et baseline. Ne pas lancer tous les profils
simultanément.

### 12.4 À documenter par exécution

-   ID/date du test, commit/version et images ;
-   environnement et caractéristiques machine ;
-   configuration FastAPI/Uvicorn, PostgreSQL, Redis et Celery ;
-   version Locust et scénario ;
-   utilisateurs, taux de montée, durée et mix des parcours ;
-   p50/p95/p99, RPS, erreurs et codes HTTP ;
-   CPU/RAM/disque/réseau ;
-   connexions, verrous et requêtes lentes PostgreSQL ;
-   mémoire Redis et backlog Celery ;
-   anomalies métier, seuil d'arrêt et conclusion.

### 12.5 Interprétation

Ne pas regarder seulement la moyenne. Examiner p95/p99, erreurs, débit,
ressources et évolution temporelle. Un débit qui plafonne peut indiquer
un goulot d'étranglement ; une faible CPU n'exclut pas un pool DB saturé
ou des appels bloqués. Comparer les résultats uniquement si scénario,
données et configuration sont comparables.

### 12.6 Critères de réussite

Les seuils doivent être définis après baseline et approuvés. Le test
doit démontrer : - parcours métier corrects et données cohérentes ; -
taux d'erreur sous les limites convenues ; - latences dans les objectifs
définis ; - ressources maîtrisées ; - absence d'effets externes
inattendus ; - retour à la normale après le test ; - rapport
reproductible et limites documentées.

### 12.7 Organisation possible

-   `tests/load/locustfile.py` : scénarios ;
-   `tests/load/README.md` : prérequis, exécution et sécurité ;
-   `tests/load/data/` : données synthétiques uniquement ;
-   `reports/load/` : rapports expurgés des informations sensibles si
    leur stockage dans le dépôt est autorisé.

Utiliser des variables d'environnement pour URL et comptes de test ; ne
pas committer les mots de passe.

## 13. Tests logiciels et métier

Prévoir un ensemble équilibré : - unitaires pour les règles métier ; -
intégration pour PostgreSQL et dépendances ; - tests API
auth/permissions/validation ; - end-to-end sur parcours critiques ; -
concurrence et idempotence ; - migrations ; - sauvegarde/restauration
; - charge Locust ; - tests de sécurité automatisés et revues manuelles
; - régression après changements sensibles.

Tester les cas positifs et négatifs : accès refusés, états invalides,
doublons, erreurs de dépendances et requêtes concurrentes. La couverture
de code seule ne suffit pas.

## 14. CI/CD, dépendances et migrations

### Pipeline

Selon les outils existants : lint/format, tests unitaires, intégration,
vérification des migrations, scans de dépendances et secrets, build
d'images versionnées, tests ciblés, artefacts de rapport, approbation
avant environnement sensible, déploiement contrôlé et vérifications
post-déploiement.

### Environnements

Séparer DEV/TEST/PROD, bases et secrets. Pas de copie non contrôlée de
données production vers TEST. Restreindre et journaliser les accès de
production.

### Migrations Alembic

Revoir et tester les migrations sur une base de test représentative.
Évaluer durée, verrous, compatibilité et sauvegarde préalable. Envisager
des migrations compatibles en plusieurs étapes si nécessaire. Un
rollback du code n'annule pas automatiquement une migration DB ; définir
une stratégie de récupération.

### Supply chain

Contrôler les versions Python/npm/images, analyser les dépendances,
supprimer l'inutile, verrouiller les versions si adapté, vérifier les
vulnérabilités et prévoir une réponse aux vulnérabilités critiques.

## 15. Déploiement et rollback

Chaque version doit être identifiable. Après déploiement, contrôler
health checks, authentification, permissions, parcours critiques,
DB/Redis/Celery, logs, erreurs, tâches et intégrité. Conserver une
procédure de retour arrière testée.

Le zéro-downtime ne peut pas être promis avec une seule instance sur un
PC local. Rolling, blue-green et canary nécessitent une architecture
compatible, notamment pour sessions, migrations, fichiers et workers.
Commencer par un processus contrôlé adapté à l'environnement actuel.

## 16. Réseau, Nginx et infrastructure

Vérifier : - seuls les ports nécessaires sont exposés ; -
PostgreSQL/Redis ne sont pas accessibles directement depuis Internet ; -
pare-feu et segmentation réseau ; - TLS, certificats et alertes
d'expiration ; - limites de taille et timeouts Nginx cohérents ; -
en-têtes de sécurité adaptés ; - protection des routes administratives
; - rate limiting si nécessaire ; - synchronisation horaire ; - DNS et
procédure de changement ; - journaux d'accès et durcissement OS ; -
contrôle de l'accès physique au serveur/PC.

## 17. Celery et Redis

Contrôler : - tâches réellement exécutées en asynchrone ; - time limits,
retries et idempotence ; - tâches bloquées/échouées et files ; -
concurrence des workers ; - reprise après redémarrage ; - configuration
de persistance/acknowledgement selon le besoin ; - mémoire et accès
réseau Redis ; - supervision et procédure de reprise ; - cohérence entre
tâche envoyée et résultat métier obtenu.

L'envoi dans la file ne signifie pas que le travail est terminé :
définir comment vérifier et communiquer le résultat.

## 18. Intégrations externes

Pour chaque intégration confirmée, documenter propriétaire,
environnement, authentification, données échangées, classification,
timeouts/retries, idempotence, contrat/version API, surveillance,
comportement en panne et autorisation de test. Ne pas supposer qu'ORION,
BCM/SIC, SMTP, ClamAV ou une autre intégration fonctionne déjà :
vérifier code/configuration et autorisations. Aucun test de charge
externe sans accord explicite.

## 19. Incidents et opérations

Préparer des procédures pour : application indisponible, disque plein,
PostgreSQL indisponible, suspicion de fuite, compte compromis, secret
exposé, tâche bloquée, sauvegarde en échec, migration échouée,
déploiement régressif et restauration d'urgence.

Chaque procédure précise symptômes, actions immédiates, personnes à
prévenir, actions autorisées, protection des preuves, critères de retour
au service et compte rendu. Ne pas supprimer les preuves d'un incident.

## 20. Indicateurs de suivi

  -----------------------------------------------------------------------------
  Domaine                 Indicateur                    Preuve
  ----------------------- ----------------------------- -----------------------
  Disponibilité           Disponibilité des services    Monitoring/incidents
                          critiques                     

  Performance             p50/p95/p99                   Métriques API/Locust

  Charge                  RPS et utilisateurs simulés   Rapport Locust

  Erreurs                 Taux d'erreurs HTTP/métier    Logs/métriques

  Hôte                    CPU/RAM/disque/redémarrages   Monitoring système

  PostgreSQL              Connexions, verrous, requêtes Métriques/logs DB
                          lentes                        

  Redis/Celery            Mémoire, backlog, tâches      Monitoring
                          échouées                      

  Sauvegarde              Âge et résultat dernière      Journaux
                          sauvegarde                    

  Restauration            Dernier test réussi et durée  Rapport d'exercice

  Sécurité                Vulnérabilités par sévérité   Rapports/tickets

  Autorisations           Tests d'accès réussis         Tests automatisés

  CI/CD                   Résultats                     Historique pipeline
                          pipeline/déploiements         

  Reprise                 RTO/RPO mesurés               Exercice de reprise
  -----------------------------------------------------------------------------

Les seuils et objectifs chiffrés doivent être approuvés, pas inventés.

## 21. Plan de travail par phases

### Phase 0 --- Inventaire et baseline

Cartographier l'architecture réelle, les parcours critiques,
permissions, tests, migrations, sauvegardes et déploiements. Mesurer la
baseline. Livrable : état initial avec preuves et inconnues.

### Phase 1 --- Sécurité et intégrité

Traiter les P0/P1 confirmés ; tester auth, sessions, permissions,
concurrence, idempotence, imports, fichiers et exports. Livrable :
matrice de contrôles et résultats.

### Phase 2 --- Sauvegarde et restauration

Inventorier DB/fichiers, définir RPO/RTO avec les responsables, mettre
en place une copie protégée séparée, tester une restauration isolée.
Livrable : procédure et preuve.

### Phase 3 --- Observabilité et résilience

Logs corrélables, métriques, alertes, timeouts/retries et tests de
pannes contrôlées. Livrable : tableau de bord et procédures d'incident.

### Phase 4 --- Locust, performance et capacité

Créer scénarios synthétiques ; smoke, baseline, montée progressive,
cible 100 si stable ; analyser les goulots ; corriger et rejouer.
Livrable : rapport reproductible et limites observées.

### Phase 5 --- CI/CD et déploiement

Automatiser les contrôles adaptés, versionner les images, séparer les
environnements, tester migrations et rollback. Livrable : pipeline et
procédure.

### Phase 6 --- Disponibilité et reprise

Évaluer les points de défaillance unique, décider si plusieurs instances
ou hébergement distinct sont nécessaires, étudier le load balancing
seulement si justifié, réaliser un exercice de reprise. Livrable :
architecture cible argumentée et plan de continuité.

**Ordre recommandé :** ne pas commencer par un cluster/load balancer
avant les contrôles fondamentaux, les objectifs de reprise et les
mesures de charge.

## 22. Registre de contrôles à compléter

  ----------------------------------------------------------------------------------------------------------------------------------------------------------------
  ID         Domaine            Contrôle/risque   Composant      Priorité   Statut   Preuve     Action/test      Résultat    Responsable   Décision/dépendance
  ---------- ------------------ ----------------- -------------- ---------- -------- ---------- ---------------- ----------- ------------- -----------------------
  SEC-001    Authentification   Limitation des    FastAPI        À évaluer  NON      À relever  Vérifier et      À compléter À définir     Politique sécurité
                                tentatives                                  AUDITÉ              tester                                     

  SEC-002    Autorisations      Permissions côté  FastAPI        À évaluer  NON      À relever  Tests par        À compléter À définir     Matrice d'habilitations
                                backend                                     AUDITÉ              rôle/ressource                             

  DATA-001   Sauvegarde         Copie séparée     DB/fichiers    À évaluer  NON      À relever  Vérifier la      À compléter À définir     RPO/RTO
                                protégée                                    AUDITÉ              procédure                                  

  DATA-002   Restauration       Restauration      DB/GED         À évaluer  NON      À relever  Restaurer en     À compléter À définir     Fenêtre d'exercice
                                complète testée                             AUDITÉ              isolé                                      

  REL-001    Observabilité      Alertes           Stack complète À évaluer  NON      À relever  Panne contrôlée  À compléter À définir     Outil de monitoring
                                actionnables                                AUDITÉ                                                         

  PERF-001   Locust             Baseline          API/DB         À évaluer  NON      Aucun      Smoke puis       À compléter À définir     Environnement autorisé
                                reproductible                               AUDITÉ   rapport    baseline                                   
                                                                                     confirmé                                              

  PERF-002   Locust             Montée            Stack complète À évaluer  NON      Aucun      Paliers avec     À compléter À définir     Baseline/autorisation
                                progressive vers                            AUDITÉ   rapport    seuils d'arrêt                             
                                100                                                  confirmé                                              

  DATA-003   Concurrence        Pas de mise à     API/DB         À évaluer  NON      À relever  Deux             À compléter À définir     Règle métier
                                jour perdue                                 AUDITÉ              modifications                              
                                                                                                concurrentes                               

  CICD-001   Déploiement        Rollback testé    CI/CD/Docker   À évaluer  NON      À relever  Déployer puis    À compléter À définir     Procédure approuvée
                                                                            AUDITÉ              revenir en TEST                            
  ----------------------------------------------------------------------------------------------------------------------------------------------------------------

Les lignes d'exemple sont des contrôles à auditer, pas des défauts
confirmés.

## 23. Livrables attendus

1.  État des lieux technique.
2.  Registre des risques.
3.  Matrice rôles/permissions.
4.  Rapports de tests et de régression.
5.  Procédure et preuve de restauration.
6.  Rapport Locust reproductible.
7.  Procédure de déploiement/rollback testée.
8.  Tableau de bord et alertes.
9.  Plan de continuité avec RPO/RTO approuvés.
10. Synthèse DSI : risques ouverts, preuves, décisions attendues et
    recommandations.

## 24. Instructions à l'agent de développement

1.  Lire le dépôt, configurations, tests, migrations et workflows avant
    toute modification.
2.  Commencer par un audit en lecture seule et citer les
    chemins/fichiers qui justifient les constats.
3.  Distinguer constat, déduction, recommandation et élément non
    vérifié.
4.  Ne pas inventer de routes, modules, intégrations, règles métier ou
    outils déjà présents.
5.  Ne pas exposer de secrets ni données réelles dans les rapports.
6.  Ne pas déployer en production, migrer la production ou appeler un
    système bancaire externe.
7.  Ne pas lancer Locust avant validation de l'environnement, de
    l'autorisation, des données synthétiques, des scénarios et des
    seuils d'arrêt.
8.  Découvrir les routes réelles avant d'écrire les scénarios Locust ;
    utiliser des variables d'environnement et aucun identifiant
    committé.
9.  Ne pas modifier le code durant l'inventaire, sauf demande explicite.
10. Proposer les corrections par lots avec tests, régressions possibles
    et rollback.
11. Pour chaque point terminé, fournir une preuve de validation.
12. Terminer par les constats P0/P1, actions recommandées, décisions
    DSI, tests à exécuter et risques résiduels.

## 25. Références officielles

-   OWASP ASVS : https://asvs.owasp.org/
-   OWASP Cheat Sheet Series : https://cheatsheetseries.owasp.org/
-   OWASP Logging Cheat Sheet :
    https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
-   Locust : https://docs.locust.io/
-   PostgreSQL --- Backup and Restore :
    https://www.postgresql.org/docs/current/backup.html
-   FastAPI : https://fastapi.tiangolo.com/
-   Angular : https://angular.dev/
-   Docker : https://docs.docker.com/
-   Celery : https://docs.celeryq.dev/
-   SQLAlchemy : https://docs.sqlalchemy.org/

Vérifier les versions officielles et les politiques internes au moment
de l'audit.

## 26. Critère final de préparation à la production

Ne pas déclarer BEA DIGITAL prêt pour la production simplement parce que
la liste a été parcourue. La décision repose sur les contrôles
applicables vérifiés, les tests réussis et leurs preuves, la
restauration démontrée, les performances mesurées dans un environnement
représentatif, les risques résiduels explicitement acceptés et les
autorisations de la DSI.

**Objectif : une plateforme maîtrisée, mesurée, testable et récupérable
--- pas une architecture complexe sans preuves de fiabilité.**
