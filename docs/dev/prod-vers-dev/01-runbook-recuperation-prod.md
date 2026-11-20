# Runbook — récupération dump PROD complet (AnyDesk)

À exécuter **uniquement** sur le serveur bancaire (`srvsuividep`, `/opt/bea-digital`), sous supervision DSI.  
Lecture seule sur PostgreSQL. **Aucune** restauration, migration, restart forcé, ni `docker compose down -v`.

## Périmètre

| Inclus | Exclu |
|--------|--------|
| Dump logique **complet** de la base `bea_digital` (toutes tables, séquences, contraintes, données) | Extraction / filtre par module (Immobilisations ou autre) |
| Empreinte SHA-256 + TOC `pg_restore --list` | GED (`storage/ged`) et pièces (`storage/uploads`) |
| Transfert via **canal sécurisé DSI** | E-mail, cloud public, dépôt Git, USB personnel non validé |

Le dump doit permettre de restaurer une base relationnellement intacte (FK, index, séquences). Aucune table métier n’est omise volontairement.

## Prérequis

- Ticket DSI + accès AnyDesk autorisé ; opérateur formé.
- Espace disque hôte ≥ 3 × taille de `bea_digital` (dump + checksum + marge).
- Conteneurs healthy ; application en service normal.
- Ne pas coller de secrets dans le chat / tickets.

## 1. Contexte lecture seule

```bash
cd /opt/bea-digital
test -f .env.production && test -d backups
docker compose --env-file .env.production -f deployment/docker-compose.prod.yml ps
curl -ksS https://127.0.0.1/health/ready -H 'Host: 192.168.1.55' || true
curl -ksS https://127.0.0.1/version -H 'Host: 192.168.1.55' || true
```

Noter version applicative et état des conteneurs. Si unhealthy → **stop**, informer DSI.

## 2. Dump PostgreSQL (format custom, base entière)

Préférer le script déjà validé (taille min + list + sha256) :

```bash
cd /opt/bea-digital
BEA_VERSION=prod_to_dev_manuel ./deployment/scripts/backup-pre-deploy.sh
```

Équivalent manuel (lire `POSTGRES_USER` / `POSTGRES_DB` depuis `.env.production` **sans les afficher**) :

```bash
STAMP=$(date +%Y%m%d-%H%M%S)
NOM="bea_prod_to_dev_${STAMP}"
docker compose --env-file .env.production -f deployment/docker-compose.prod.yml \
  exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --format=custom --no-owner --no-acl --file="/backups/${NOM}.dump"
```

Règles :

- Base source = **`bea_digital` uniquement** (pas de dump partiel `-t` / `-n` sélectif métier).
- `--format=custom` uniquement.
- Pas de `--clean` / restore côté PROD.
- **Ne pas** archiver GED/uploads pour cette opération.

## 3. Intégrité et SHA-256

```bash
DUMP=backups/${NOM}.dump   # ou chemin renvoyé par backup-pre-deploy.sh
ls -lh "$DUMP"
test $(wc -c < "$DUMP") -ge 102400

docker compose --env-file .env.production -f deployment/docker-compose.prod.yml \
  exec -T postgres pg_restore --list "/backups/$(basename "$DUMP")" > "/tmp/${NOM}.toc.txt"

sha256sum "$DUMP" | tee "${DUMP}.sha256"
cp "/tmp/${NOM}.toc.txt" "backups/${NOM}.toc.txt"
```

Échec taille / list / sha256 → **ne pas transférer** ; traitement du fichier incomplet selon DSI.

## 4. Contrôles de contenu (TOC)

Le TOC doit montrer un dump de **base complète**, notamment :

- `alembic_version`
- Présence de `TABLE` / `TABLE DATA` pour le socle attendu (ex. `users`, `immobilisations`, `soldes_compte_orion`, `exercices_comptables`, tables `clientele_*`, `rbcm_*`, stock, réclamations, etc. — selon la révision PROD)
- Pas d’erreur `pg_restore --list`
- Pas d’indication d’un dump limité à quelques tables immo

Noter la révision Alembic PROD pour contrôle croisé **après** restore DEV (ne pas modifier PROD).

## 5. Précautions PROD (absolues)

| Interdit | Pourquoi |
|----------|----------|
| `docker compose down -v` | Efface le volume PostgreSQL |
| `DROP` / `TRUNCATE` / restore sur PROD | Destruction métier |
| Arrêt postgres « pour figer » | Interrompt le service |
| Copier `.env.production` hors serveur | Fuite de secrets |
| Transfert hors canal DSI | Exposition bancaire |
| Dump partiel « pour aller plus vite » | Base DEV incohérente / FK cassées |

`pg_dump` de la base entière est cohérent transactionnellement sans mode maintenance.

## 6. Transfert sécurisé (canal DSI)

1. Remise exclusivement via le **canal sécurisé validé par la DSI**.
2. Fichiers : `${NOM}.dump` + `${NOM}.dump.sha256` (+ TOC recommandé).
3. Chaîne de custody : horodatage, opérateur, ticket, empreinte départ / arrivée.
4. Purge du dump sur le serveur après accuse réception DEV : **selon politique DSI**.

## 7. Fin de session AnyDesk

- Revérifier `/health/ready`.
- Ticket : nom du dump, taille, SHA-256, heure, opérateur — **pas** le contenu du dump.

## Décisions DSI restantes

Les points métier (base complète, exclusion GED/uploads, tampon, préservation DEV, neutralisation accès, transfert DSI) sont **tranchés**. Il reste à valider formellement :

1. **Ordre écrit** d’exécution (date, opérateur, ticket).
2. **Identité du compte admin DEV** post-neutralisation (e-mail / politique mot de passe).
3. **Anonymisation PII au-delà des accès** : conserver noms/RIB/textes clients tels quels dans le tampon, ou appliquer un niveau Minimal/Strict (voir doc 03) — les **montants et historiques comptables restent intacts** dans tous les cas.
4. **Go migration Postgres DEV → Debian** avant le premier import (recommandé ; doc 04).
5. **Rétention / purge** du dump sur PROD et sur le poste DEV après import réussi.
6. **Bascule applicative** : quand et comment pointer l’appli DEV vers `bea_digital_prod_YYYYMMDD` (manuel, hors scripts actuels).
