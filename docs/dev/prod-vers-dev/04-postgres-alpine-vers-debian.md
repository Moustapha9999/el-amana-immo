# PostgreSQL DEV — Alpine → Debian (`postgres:17`)

**Migration DEV exécutée** (2026-11-19) : image `postgres:17` Debian, volume actif `bea_postgres_data_debian`, volume Alpine `bea_postgres_data` conservé. Dumps + rapport : `backups/mig-alpine-debian-20261119-201540/`.

## Décision d’architecture

Aligner le Postgres DEV sur PROD (**Debian** `postgres:17`) **avant** le premier import du dump complet `bea_digital` PROD vers `bea_digital_prod_YYYYMMDD`.  
Import sous Alpine : seulement si la DSI accepte explicitement le risque collation (non recommandé).

## Écart actuel

| | DEV local | PROD banque |
|--|-----------|-------------|
| Image | `postgres:17-alpine` | `postgres:17` (Debian) |
| Volume | `bea_postgres_data` | volume serveur dédié |
| Collation DEV observée | `en_US.utf8` (musl) | collation Debian alignée dump |
| Bases à préserver | `bea_digital`, `bea_digital_test` | `bea_digital` |

## Pourquoi avant l’import PROD

Le dump PROD est une **base entière**. Un écart Alpine/Debian augmente le risque d’anomalies de collation / restore sur un volume de tables large (clientèle, immo, rbcm, etc.). Mieux vaut un cluster DEV déjà Debian, puis créer le tampon dessus.

## Conséquences

**Bénéfices :** alignement `deployment/docker-compose.prod.yml` ; restore PROD plus prévisible.  
**Coûts :** recreation de cluster (pas un simple changement de tag) ; fenêtre d’arrêt local ; rebuild éventuel de `bea_digital_test` ; image plus lourde.

## Procédure future sans perte

1. Dump logique vérifié de `bea_digital` **et** `bea_digital_test` + SHA-256 + `pg_restore --list`.  
2. Espace disque ≥ 3 × taille des bases.  
3. Stop `backend` `worker` `frontend` `pgadmin`.  
4. Après validation : compose → `image: postgres:17` + **nouveau** volume (ex. `bea_postgres_data_debian`) ; conserver l’ancien volume Alpine en filet.  
5. Premier boot Debian (init / rôles).  
6. Restore `bea_digital` puis `bea_digital_test` (ou `test-db.ps1` après).  
7. Contrôles : `alembic_version`, counts, login DEV.  
8. **Ensuite seulement** : `prod-to-dev-restore` vers `bea_digital_prod_YYYYMMDD`.  
9. Rétention de l’ancien volume Alpine N jours, puis suppression **manuelle** explicite.

## Interdits

- Changer le tag d’image sur le PGDATA Alpine existant et démarrer.  
- `docker compose down -v` sans dumps + checksums validés.  
- Migrer le volume **pendant** l’import PROD.  
- Écraser `bea_digital` / `bea_digital_test` pour « faire de la place » au tampon.

## Option DSI

| Option | Statut |
|--------|--------|
| **A. Debian avant 1er import PROD** | **Recommandé** (décision d’architecture retenue) |
| B. Import sous Alpine | Dérogation DSI écrite requise |
