# Procès-verbal — première installation BEA DIGITAL

**Serveur :** `srv-classification` (`192.168.1.22`)  
**Date :** 9 novembre 2026  
**Version installée :** `v1.0.0`  
**Révision de base :** `20261105_mg_stock_mvt_ref_uq`  
**Dossier d’installation :** `/home/moustapha/bea-digital`  
**Accès métier :** `https://192.168.1.22`

Ce document décrit **ce qui a réellement été fait** pour la première mise en service. Il complète la procédure générique [08-livraison-et-mises-a-jour.md](08-livraison-et-mises-a-jour.md) et l’audit [AUDIT_TECHNIQUE_BEA_DIGITAL.md](AUDIT_TECHNIQUE_BEA_DIGITAL.md). Aucun secret (mots de passe, `SECRET_KEY`, contenu de `.env.production`) n’y figure.

---

## 1. Objet et périmètre

BEA DIGITAL est la plateforme interne de la Banque El Amana (Mauritanie). Ce n’est pas un remplacement du core banking **ORION**. CORE ADMIN (`/admin`, Login 1, permission `core.admin.access`) fait partie de la même application Angular, de la même API et de la même base PostgreSQL.

**Installé le 9 novembre 2026 :**

- plateforme Angular et console `/admin` ;
- API FastAPI, worker Celery, Redis, PostgreSQL 17 ;
- module Immobilisations & Amortissements (URLs métier inchangées) ;
- nginx de l’hôte en HTTPS sur le port 443.

**Hors périmètre :** toute intégration ou modification d’ORION.

**Modules catalogue (inchangés lors de l’install) :**

| Module | Statut catalogue | Effet |
|--------|------------------|--------|
| EER | `inactif` | Fermé. Tables `eer_*` conservées. |
| Base Clientèle | `developpement` | API fermée. Code conservé. |
| Réclamations | `actif` | Ouvert aux utilisateurs qui ont le droit. |

---

## 2. Constat serveur avant installation

| Élément | Constat |
|---------|---------|
| OS | Ubuntu 22.04.5, VM VMware, 2 vCPU, ~15 Gio RAM, disque unique ~2 To (`sda2` ext4) |
| Fuseau | Africa/Nouakchott |
| Docker | Deux démons en parallèle (voir § 3) |
| Ports 8000, 8080, 9443 | Déjà pris par le Docker **système** (juillet 2026), toutes interfaces |
| Ports 80 et 443 | Libres. `nginx` absent de l’hôte avant l’étape HTTPS |
| `/opt` | Non montable par Docker Snap (`read-only file system`) |
| `/home/moustapha` | Montable (interface Snap `home` connectée) |

Les trois conteneurs visibles par `docker ps -a` du Snap (`my-app-container`, Mongo, Mongo Express) étaient **arrêtés** depuis environ 17 mois. Ils n’écoutaient pas. Les supprimer n’aurait libéré ni 8080 ni la RAM. Ils n’ont pas été supprimés.

---

## 3. Deux Docker sur la même machine

| Démon | Client habituel | Rôle |
|-------|-----------------|------|
| Snap (`/var/snap/docker/…`) | `docker` / `docker compose` | **BEA DIGITAL** (volume `bea_postgres_data`, réseau `bea_internal`) |
| `/usr/bin/dockerd` (depuis le 10 juillet 2026) | Non vu par `docker ps` | Pile existante : ports **8000**, **8080**, **9443** (couple 8000/9443 typique Portainer ; 8080 vers un autre conteneur). Mongo / Airflow côté ce démon |

**Décision :** ne pas arrêter la pile de juillet. BEA DIGITAL n’utilise pas 8000, 8080 ni 9443.

---

## 4. Décisions d’architecture retenues

1. **Un seul dépôt vivant**, une seule application Angular, une seule PostgreSQL 17.
2. **Deux bases applicatives seulement** dans le modèle cible : `bea_digital` (réelle) et `bea_digital_test` (recette). Sur ce serveur, seule `bea_digital` a été créée. `bea_digital_test` n’a **pas** été installée.
3. **Compte PostgreSQL unique** `bea_digital_app` (superutilisateur au premier `init` de l’image officielle). Un rôle limité pourra être ajouté plus tard sans recréer le volume.
4. **Jamais Alembic sur une base vide.** Premier chargement = `pg_restore` d’un dump. `SKIP_MIGRATIONS=1` au démarrage des conteneurs.
5. **Frontend hôte :** `127.0.0.1:8088` → port interne du conteneur 8080. Variable `BEA_HTTP_BIND`.
6. **Racine d’install :** `/home/moustapha/bea-digital` (contrainte Snap).
7. **Publication utilisateurs :** nginx de l’hôte sur 80/443, pas d’ouverture de PostgreSQL ni de Redis sur le réseau.
8. **Durcissement conteneurs :** `cap_drop: ALL`, compte non root (uid 10001). `no-new-privileges` **retiré** sur ce serveur : le Docker Snap refuse alors `exec … python` (`operation not permitted`, 9 novembre 2026).

**Interdit en toutes circonstances :** `docker compose down -v` (le `-v` efface le volume PostgreSQL).

---

## 5. Chaîne de livraison (poste de développement)

Rien n’est compilé sur le serveur banque.

1. Contrôles Git et construction des images : `scripts/release.ps1 -Version v1.0.0`.
2. Artefacts : `dist/releases/v1.0.0/images.tar` (+ `.sha256`), `deploiement.tar.gz`, `manifest.json`.
3. Dump de reprise produit sur le poste local (`scripts/backup-local.ps1`) : `backups/local-20261109-114059.dump` (format custom PostgreSQL, table `alembic_version` présente).
4. Transfert vers le serveur par **AnyDesk** (le `scp` depuis le poste Windows vers `192.168.1.22:22` n’était pas joignable sur le chemin réseau utilisé ce jour-là).

Empreinte de `images.tar` v1.0.0 :  
`2963277b6c0ca489699cdc21b01ef208fb5ad61759771c7e6da75593eec6f17e`.

---

## 6. Procédure exécutée sur le serveur

Toutes les commandes ci-dessous se comprennent depuis `/home/moustapha/bea-digital`, utilisateur `moustapha`, client Docker **Snap**.

### 6.1 Arborescence et extraction

- Création du dossier d’install (y compris `releases/`, `backups/`, `storage/uploads`, `storage/ged`).
- Extraction de l’archive de déploiement (`deployment/`, `database/init/`).
- Copie du dump dans `backups/local-20261109-114059.dump`.

### 6.2 Fichier d’environnement

```text
cp deployment/env.production.example .env.production
chmod 600 .env.production
```

Renseigné sur le serveur (valeurs non secrètes) :

| Variable | Valeur retenue |
|----------|----------------|
| `APP_ENV` | `production` |
| `POSTGRES_DB` | `bea_digital` |
| `POSTGRES_USER` | `bea_digital_app` |
| `BEA_HTTP_BIND` | `127.0.0.1:8088` |
| `PUBLIC_APP_URL` | d’abord `http://127.0.0.1:8088`, puis `https://192.168.1.22` |
| `CORS_ORIGINS` | idem |
| `TRUSTED_PROXIES` | `frontend` puis `frontend,<passerelle bea_internal>` |
| `SECRET_KEY` / `POSTGRES_PASSWORD` | générés sur le serveur (`openssl`), hors Git, hors ce document |

### 6.3 Restauration de la base (avant toute application)

```bash
docker pull postgres:17
docker pull redis:7-alpine
bash deployment/scripts/restore.sh backups/local-20261109-114059.dump
```

Résultat contrôlé :

| Contrôle | Valeur |
|----------|--------|
| `RESTORE_OK` | 211 tables |
| Révision Alembic | `20261105_mg_stock_mvt_ref_uq` |
| Utilisateurs | 63 |
| Immobilisations | 1 206 |
| Valeur brute totale | 398 181 100,81 |
| Clients (base clientèle) | 0 |
| Classifications retenues | 0 |

PostgreSQL et Redis démarrés. Backend / frontend **non** démarrés à cette étape.

### 6.4 Chargement des images et déploiement applicatif

```bash
sha256sum -c releases/v1.0.0/images.tar.sha256
BEA_VERSION=v1.0.0 IMAGES_TAR=releases/v1.0.0/images.tar bash deployment/scripts/deploy.sh
```

**Incident 1 — `exec /usr/local/bin/python: operation not permitted`**  
Cause : `security_opt: no-new-privileges:true` incompatible avec Docker Snap.  
Mesure : quatre essais `docker run` (sans durcissement / `no-new-privileges` / `cap-drop ALL` / les deux). Seul `no-new-privileges` échoue.  
Correction : retrait de cette option dans `deployment/docker-compose.prod.yml` sur le serveur. `cap_drop: ALL` et uid 10001 conservés.  
La base n’avait pas changé (Alembic n’avait pas démarré). Pas de restauration.

**Relance :** même `deploy.sh`. Alembic : aucune migration à appliquer (`20261105_mg_stock_mvt_ref_uq` → même révision).

Résultat :

```text
API OK — version v1.0.0
{"status":"ok","version":"v1.0.0","checks":{"database":{"status":"ok"},"redis":{"status":"ok"}}}
Worker OK
DEPLOY_OK version=v1.0.0
```

Conteneurs : `bea-postgres`, `bea-redis`, `bea-backend`, `bea-worker`, `bea-frontend` (`127.0.0.1:8088->8080`).

### 6.5 Publication HTTPS pour les postes de la banque

L’application n’écoutait que sur `127.0.0.1:8088`. Les cookies de session exigent HTTPS hors loopback.

1. Contrôle : rien n’écoute sur 80 ni 443 ; `nginx` absent.
2. Installation de nginx sur l’hôte.
3. Certificat **auto-signé** pour l’IP `192.168.1.22` dans `/etc/ssl/bea-digital/` (à remplacer par le certificat DSI).
4. Site `/etc/nginx/sites-available/bea-digital.conf` : HTTP → HTTPS, `proxy_pass` vers `127.0.0.1:8088`.
5. Mise à jour de `PUBLIC_APP_URL`, `CORS_ORIGINS`, `TRUSTED_PROXIES` ; recréation **backend** et **worker** uniquement (PostgreSQL intact).

Accès utilisateurs : **https://192.168.1.22** (avertissement navigateur tant que le certificat DSI n’est pas en place).  
Le port **22** reste SSH. Il ne sert pas l’application.

---

## 7. Cartographie des accès

| Accès | Adresse | Public |
|-------|---------|--------|
| Application (Login 1) | `https://192.168.1.22` | Postes banque (port 443) |
| Frontend conteneur | `http://127.0.0.1:8088` | Serveur seulement |
| Santé | `https://192.168.1.22/health/ready` et `/version` | |
| PostgreSQL | réseau Docker `bea_internal`, port 5432 **non publié** | Non |
| Redis | idem | Non |
| pgAdmin (optionnel, après coup) | `http://127.0.0.1:5050` | Serveur / AnyDesk seulement |

**pgAdmin** n’est pas dans le compose de production. S’il est lancé : `docker run` sur le réseau `bea_internal`, bind **uniquement** `127.0.0.1:5050`. Connexion serveur : hôte `postgres`, base `bea_digital`, utilisateur `bea_digital_app`, mot de passe = `POSTGRES_PASSWORD` de `.env.production`. C’est **la même** base que les utilisateurs ; toute écriture SQL est une écriture de production.

Console SQL sans pgAdmin :

```bash
docker exec -it bea-postgres psql -U bea_digital_app -d bea_digital
```

---

## 8. Sauvegardes produites pendant l’install

`deploy.sh` a pris une sauvegarde avant chaque tentative de mise en service, notamment :

- `backups/bea_avant_v1.0.0_20261109-125652.dump`
- `backups/bea_avant_v1.0.0_20261109-130258.dump`

Ces fichiers sont sur le **même disque** que la base. Ils ne protègent pas contre la perte du disque. À répliquer hors serveur (politique DSI). Cron proposé, non nécessairement activé le jour J :

```cron
30 1 * * * cd /home/moustapha/bea-digital && ./deployment/scripts/backup-pre-deploy.sh nuit >> backups/backup.log 2>&1
```

---

## 9. Ce qui n’a pas été fait (reste DSI / exploitation)

1. Certificat officiel et, le cas échéant, nom DNS à la place de l’IP.
2. Réplication des `backups/` hors de `srv-classification`.
3. SMTP (mot de passe oublié, notifications courriel).
4. Copie éventuelle des pièces `storage/uploads` du poste de développement (dump SQL restauré ; fichiers binaires non transférés).
5. Création de `bea_digital_test` (uniquement sur demande, jamais restaurée par-dessus `bea_digital`).
6. Décision métier d’ouverture Clientèle / cadrage Réclamations.
7. Inventaire nominatif et sort de la pile Docker de juillet (Mongo, Airflow, 8000/8080/9443) : **ne pas arrêter sans accord**.
8. Compte PostgreSQL d’application restreint (aujourd’hui `bea_digital_app` est superutilisateur).
9. Pousser le tag Git `v1.0.0` et committer le retrait de `no-new-privileges` dans le dépôt de référence.

---

## 10. Conduite à tenir

**Faire**

- Mises à jour : `BEA_VERSION=vX.Y.Z IMAGES_TAR=releases/vX.Y.Z/images.tar ./deployment/scripts/deploy.sh`
- Retour arrière : `./deployment/scripts/rollback.sh` (selon analyse des migrations)
- Reprise de base : `REMPLACER=1 VERSION_APPLI=v1.0.0 ./deployment/scripts/restore.sh backups/<dump>.dump`

**Ne pas faire**

- `docker compose down -v`
- `docker volume rm` / `docker volume prune` / `docker system prune` sans ordre écrit
- Publier 5432, 5050, 8088 ou 6379 sur `192.168.1.22`
- Lancer le `docker-compose.yml` de développement (port 80, pgAdmin, comptes locaux) sur ce serveur
- Restaurer `bea_digital_test` ou un dump Clientèle protégé par-dessus la production
- Modifier `backend/app/services/amortissement_engine.py` ni la règle VNC

Dumps protégés (ne jamais supprimer ni restaurer à la place de la production) :  
`avant_purge_clientele_20261022_104012.dump`, `local-20261021-115657.dump`.

---

## 11. Preuve de service au 9 novembre 2026

| Contrôle | Résultat |
|----------|----------|
| `GET /version` | `"version": "v1.0.0"` |
| `GET /health/ready` | `status: ok`, PostgreSQL et Redis `ok` |
| Worker | healthcheck Celery `healthy` |
| Schéma | 211 tables, révision `20261105_mg_stock_mvt_ref_uq` |
| Publication | `https://192.168.1.22` via nginx hôte → `127.0.0.1:8088` |
