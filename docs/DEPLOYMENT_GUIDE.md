# Installer BEA DIGITAL sur Ubuntu Server

Ce guide décrit le démarrage d’une machine Ubuntu **vierge**. Il ne modifie
pas le poste Windows ni le cluster `bea-postgres` actuel.

Le détail déjà écrit reste la référence : [déploiement](deployment/README.md),
[Docker prod](deployment/04-docker-production.md),
[secrets](deployment/03-secrets-et-environnements.md),
[livraison](deployment/08-livraison-et-mises-a-jour.md),
[sauvegarde PostgreSQL](fiabilite/sauvegarde-postgresql.md).

## Ce qui est prêt, ce qui ne l’est pas

Prêt dans le dépôt : une application, un compose, des healthchecks, un compte
`bea_app` sans superuser, des migrations Alembic, une stratégie de sauvegarde
**prouvée sur un cluster isolé**.

Pas prêt à copier tel quel en banque :

- Le compose local publie PostgreSQL sur `127.0.0.1:5432` et utilise
  `postgres:17-alpine`. En TEST/PROD : image **Debian** `postgres:17`, pas de
  port publié, TLS devant nginx ([04-docker-production.md](deployment/04-docker-production.md)).
- `archive_mode` est **off** sur l’instance qui porte les données. Le PITR
  validé utilise un second cluster et trois volumes. Ne pas l’activer sur le
  volume unique `bea_postgres_data` sans stockage WAL séparé.
- Le travail de fiabilité (4 processus, unicité des références, loadtest)
  est sur la branche `chore/audit-nettoyage-pre-deploiement` et **n’est pas
  encore commité**. Ne pas déployer `main` à `484f5db` en croyant que ces
  correctifs y sont.

## Prérequis Ubuntu

- Ubuntu Server 22.04 ou 24.04, accès sudo.
- Docker Engine et le plugin Compose v2.
- Un disque pour les données PostgreSQL, un autre chemin pour les WAL et
  les sauvegardes (pas le même volume que l’application).
- Nom de domaine et certificats : décision DSI
  ([inventaire](deployment/00-inventaire-bea.md)).

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
# Docker : dépôt officiel Docker, pas le paquet docker.io seul si la DSI impose le dépôt Docker.
docker compose version
```

## Code et secrets

```bash
sudo mkdir -p /opt/bea-digital
sudo chown "$USER":"$USER" /opt/bea-digital
git clone <dépôt> /opt/bea-digital
cd /opt/bea-digital
git checkout <révision revue>
cp .env.docker.example .env.docker   # local / répétition
# PROD : .env.production — jamais commité
```

Renseigner au minimum : `SECRET_KEY`, `POSTGRES_PASSWORD`,
`BEA_APP_DB_PASSWORD` (≥ 24 caractères), `PGADMIN_*` si pgAdmin est gardé.
Ne pas coller ces valeurs dans un ticket ni dans Git.

Le backend qui tourne est `backend/` (Dockerfile du compose). Ne pas builder
le `Dockerfile` à la racine du dépôt (`app/` est une dette).

## Démarrage

```bash
docker compose --env-file .env.docker up -d --build
docker compose ps
curl -fsS http://127.0.0.1/health
curl -fsS http://127.0.0.1/health/ready
```

`/health/ready` doit montrer la base et Redis `ok`.

Interdit : `docker compose down -v` (le `-v` supprime `bea_postgres_data`).

`SKIP_MIGRATIONS=1` tant qu’on restaure un dump déjà migré. Les migrations
passent par le service `migrate` (compte `admin`), après une sauvegarde
vérifiée ([runbook](runbook-migrations.md)).

## PostgreSQL sur cette machine

Aujourd’hui le compose n’a **qu’un** volume de données. La cible banque,
déjà expérimentée à part (`loadtest/docker-compose.pitr.yml`), est :

| Emplacement | Contenu |
|---|---|
| Volume données | `PGDATA` |
| Volume ou disque WAL | archives produites par `archive_command` |
| Disque sauvegardes | `pg_basebackup` et `pg_dump -Fc` |
| Copie hors serveur | les deux, chiffrée, rétention DSI |

Tant que ces chemins n’existent pas, laisser `archive_mode=off`.

Sauvegarde logique minimale (rôle `admin`, base arrêtée aux écritures ou
dump à chaud `-Fc`) :

```bash
docker exec bea-postgres pg_dump -U admin -Fc -d bea_digital -f /backups/bea_digital.dump
docker exec bea-postgres pg_dumpall -U admin --globals-only -f /backups/globals.sql
docker exec bea-postgres pg_restore -l /backups/bea_digital.dump
```

`pg_dump` d’une base **n’inclut pas** les rôles ni `GRANT CONNECT`.
Après restauration dans une base neuve : rôles (`globals.sql`), puis
`GRANT CONNECT, TEMPORARY ON DATABASE … TO bea_app`.

La restauration PITR se fait sur un **autre** PGDATA, avec
`recovery.signal` et `recovery_target_time`. Jamais en écrasant le volume
de production sans décision DSI.

## Vérifier que l’application répond

- Login 1 (plateforme) puis Login 2 (module).
- Une seule session module active par compte et par module
  ([socle](socle-bea-digital.md)).
- Lecture stock / immobilisations selon les droits du compte.
- Ne pas lancer Locust contre `http://localhost` de la base réelle.
  L’environnement de charge est `http://127.0.0.1:8081` /
  `bea_digital_loadtest` ([loadtest](../loadtest/setup-env.ps1)).

## Arrêt propre

```bash
docker compose --env-file .env.docker stop
```

Les volumes nommés restent. Pas de `down -v`, pas de `docker system prune
--volumes`.
