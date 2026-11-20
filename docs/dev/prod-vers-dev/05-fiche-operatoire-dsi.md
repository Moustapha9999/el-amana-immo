  # Fiche opératoire DSI — dump PROD `bea_digital` → DEV

  **Phase :** préparation uniquement — **aucune exécution** tant que l’autorisation écrite n’est pas délivrée.  
  **Verdict technique local :** environnement DEV Debian prêt ; scripts restore/neutralize prêts.

  ## 1. Cohérence doc ↔ scripts (contrôle)

  | Attendu documenté | Script | Statut |
  |-------------------|--------|--------|
  | Dump base **complète** ; pas de filtre immo | `prod-to-dev-restore.ps1` refuse TOC pauvre / marqueurs absents | OK |
  | Cible `bea_digital_prod_YYYYMMDD` uniquement | Motif + refus `bea_digital` / `bea_digital_test` | OK |
  | Pas d’écrasement auto | Refus si la base cible existe | OK |
  | GED / uploads exclus | Aucune restauration fichiers dans les scripts | OK |
  | Comptabilité préservée | Snapshot immos / VB / Orion 142000 / exercices avant-après neutralize | OK |
  | Admin DEV + PII explicites | `-DevAdminEmail`, `-DevAdminRoleCodes`, `-AnonymizePii`, `BEA_DEV_ADMIN_PASSWORD` | OK |
  | Postgres DEV Debian | Migration locale faite (`postgres:17`, volume `bea_postgres_data_debian`) | OK |

  Écarts mineurs (non bloquants) : le README § séquence cite encore « migrer Alpine→Debian » comme étape future (déjà faite) ; le runbook § décisions liste encore le « go Debian » — à cocher comme **fait** lors de l’ordre DSI.

  ## 2. Procédure opérationnelle — côté PROD (AnyDesk)

  ### 2.1 Source

  | Élément | Valeur |
  |---------|--------|
  | Serveur | `srvsuividep-virtual-machine` (`192.168.1.55`) |
  | Racine | `/opt/bea-digital` |
  | Compose | `deployment/docker-compose.prod.yml` + `.env.production` |
  | Base source | **`bea_digital`** (complète) |
  | Conteneur | service `postgres` (image attendue `postgres:17` Debian) |
  | Exclus | `storage/ged`, `storage/uploads`, dump partiel `-t` |

  ### 2.2 Pré-contrôles (lecture seule)

  ```bash
  cd /opt/bea-digital
  docker compose --env-file .env.production -f deployment/docker-compose.prod.yml ps
  curl -ksS https://127.0.0.1/health/ready -H 'Host: 192.168.1.55'
  curl -ksS https://127.0.0.1/version -H 'Host: 192.168.1.55'

  # Espace disque (besoin >= 3 x taille DB)
  df -h /opt/bea-digital /var/lib/docker 2>/dev/null || df -h

  # Taille DB + version Postgres + pg_dump disponible dans le conteneur
  docker compose --env-file .env.production -f deployment/docker-compose.prod.yml \
    exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT pg_size_pretty(pg_database_size(current_database())); SELECT version();"
  docker compose --env-file .env.production -f deployment/docker-compose.prod.yml \
    exec -T postgres pg_dump --version
  ```

  `$POSTGRES_USER` / `$POSTGRES_DB` : les charger depuis `.env.production` **sans les afficher** dans le ticket.

  Si unhealthy, disque insuffisant, ou `pg_dump` absent → **STOP**.

  ### 2.3 Dump complet (`pg_dump -Fc`)

  **Recommandé pour ce workflow** (DB seule, sans archive GED/uploads) :

  ```bash
  cd /opt/bea-digital
  set -a; source .env.production; set +a   # ou export manuel des 2 variables DB
  STAMP=$(date +%Y%m%d-%H%M%S)
  NOM="bea_prod_to_dev_${STAMP}"

  docker compose --env-file .env.production -f deployment/docker-compose.prod.yml \
    exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --format=custom --no-owner --no-acl \
    --file="/backups/${NOM}.dump"
  ```

  Alternative : `BEA_VERSION=prod_to_dev_manuel ./deployment/scripts/backup-pre-deploy.sh`  
  → **ne transférer que** le `.dump` (+ `.sha256`) ; **ignorer** toute archive `*_fichiers.tar.gz` (GED/uploads hors périmètre).

  ### 2.4 Contrôles dump

  ```bash
  DUMP="backups/${NOM}.dump"
  ls -lh "$DUMP"
  test $(wc -c < "$DUMP") -ge 102400

  docker compose --env-file .env.production -f deployment/docker-compose.prod.yml \
    exec -T postgres pg_restore --list "/backups/$(basename "$DUMP")" \
    > "backups/${NOM}.toc.txt"

  sha256sum "$DUMP" | tee "${DUMP}.sha256"

  # Spot-check TOC (base complete)
  grep -E 'alembic_version|TABLE DATA public (users|immobilisations|exercices_comptables|soldes_compte_orion)' \
    "backups/${NOM}.toc.txt"
  ```

  Échec taille / list / SHA / TOC → **ne pas transférer**.

  ### 2.5 Transfert sécurisé → DEV

  1. Canal **uniquement** celui validé par la DSI (pas d’e-mail / cloud public / Git).
  2. Fichiers : `${NOM}.dump` + `${NOM}.dump.sha256` (+ `${NOM}.toc.txt` recommandé).
  3. Ticket : nom, taille, SHA-256, horodatage, opérateur — **jamais** le dump ni `.env.production`.
  4. Accusé de réception DEV (voir § 2.6) avant purge éventuelle côté serveur (politique DSI).

  ### 2.6 Dépôt et confirmation de réception (poste DEV)

  | Élément | Valeur |
  |---------|--------|
  | Emplacement dépôt | `c:\Users\sallm\bea-digital\backups\` (monté `/backups` dans `bea-postgres`) |
  | Noms conseillés | conserver `${NOM}.dump` / `${NOM}.dump.sha256` / `${NOM}.toc.txt` |
  | Confirmation | recalcul SHA-256 local = fichier DSI ; `pg_restore --list` OK ; ticket « RECU OK » |

  ```powershell
  # Sur le poste DEV uniquement, apres arrivee des fichiers
  Get-FileHash -Algorithm SHA256 .\backups\<NOM>.dump
  # comparer a .\backups\<NOM>.dump.sha256
  docker exec bea-postgres pg_restore --list /backups/<NOM>.dump | Select-Object -First 5
  ```

  Puis seulement (ordre DSI) :

  ```powershell
  .\scripts\prod-to-dev-restore.ps1 -DumpPath .\backups\<NOM>.dump `
    -Sha256Path .\backups\<NOM>.dump.sha256 `
    -TargetDatabase bea_digital_prod_YYYYMMDD `
    -RequireDebianPostgres `
    -ConfirmPhrase 'OUI-RESTAURER-DEV-TAMPON'

  $env:BEA_DEV_ADMIN_PASSWORD = '<secret DEV — jamais dans le ticket>'
  .\scripts\neutralize-dev-copy.ps1 -Database bea_digital_prod_YYYYMMDD `
    -DevAdminEmail '<email valide DSI>' `
    -DevAdminRoleCodes administrateur `
    -AnonymizePii <None|Minimal|Strict> `
    -ConfirmWorkerStopped `
    -ConfirmPhrase 'OUI-NEUTRALISER-COPIE-DEV'
  ```

  `-WhatIf` possible avant exécution réelle.  
  **Ne pas** utiliser `scripts/restore-local.ps1` (écrase `bea_digital`).

  ## 3. Paramètres obligatoires avant restauration

  À remplir / joindre à l’ordre écrit DSI :

  | # | Paramètre | Statut |
  |---|-----------|--------|
  | 1 | Autorisation écrite DSI (ticket, date, périmètre « base complète, sans GED/uploads ») | **MANQUANT** |
  | 2 | Opérateur PROD (AnyDesk) + opérateur DEV + créneau | **MANQUANT** |
  | 3 | E-mail administrateur DEV (`-DevAdminEmail`) + rôles (`-DevAdminRoleCodes`) | **MANQUANT** |
  | 4 | Mot de passe admin DEV via `BEA_DEV_ADMIN_PASSWORD` (canal secret, hors ticket) | **MANQUANT** |
  | 5 | Politique PII : `None` / `Minimal` / `Strict` (`-AnonymizePii`) | **MANQUANT** |
  | 6 | Conservation / purge du dump sur PROD et sur le poste DEV (délai, responsable) | **MANQUANT** |
  | 7 | Nom cible `bea_digital_prod_YYYYMMDD` (date du jour d’import) | À fixer le jour J |
  | 8 | Accusé réception SHA-256 DEV | Après transfert |
  | 9 | Bascule éventuelle de l’appli DEV vers le tampon (manuel, hors scripts) | **Optionnel / MANQUANT** si usage immédiat |

  Déjà satisfaits côté technique DEV : Postgres Debian 17 ; scripts ; exclusion GED/uploads ; préservation `bea_digital` / `bea_digital_test`.

  ## 4. Interdits (rappel)

  Pas de `docker compose down -v` ; pas de restore sur PROD ; pas de dump partiel ; pas de copie de `.env.production` ; pas de transfert hors canal DSI.

  ## 5. Verdict

  **PRÊT POUR AUTORISATION DSI**

  L’opération réelle (dump PROD, transfert, restore, neutralize) ne démarre qu’après complétion des lignes **MANQUANT** du tableau § 3.
