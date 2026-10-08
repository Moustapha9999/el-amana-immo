# CORE ADMIN — Ops (Backup, Recovery, Supervision, Maintenance)

Complement de [core-admin.md](core-admin.md). Pas de stack Prometheus/Grafana :
le pilotage reste dans CORE ADMIN (Login 1).

## Analyse (réutiliser)

| Brique | Existant | Action |
|--------|----------|--------|
| Modules | `plateforme_modules.statut` (`actif`/`bientot`/`inactif`) | Étendre statuts + message + version + fenêtres maintenance |
| Espaces | `plateforme_espaces` | Idem léger (maintenance département) |
| Backup | `scripts/backup-local.ps1` → `backups/` | Métadonnées DB + déclenchement API (même dump custom) |
| Restore | `scripts/db-restore*.ps1` | Recovery UI = safety backup puis restore **périmètre** |
| Audit | `record_audit` / `audit_logs` | Nouvelles actions `backup_*`, `recovery_*`, `module_status_*` |
| Permissions | `core.admin.*` | Ajouter `backup` / `recovery` / `monitoring` / `maintenance` / `versions` |
| Immo métier | tables immo | **Ne pas modifier** le schéma métier |

## Recovery partiel — périmètres des modules

Source de vérité code : `backend/app/data/module_backup_scopes.py`
(`make_module_scope`, `SHARED_CORE_TABLES`, `MODULE_BACKUP_SCOPES`).
Nouveau module = une entrée factory, sans recopier le CORE :

- `exclusive_tables` + `table_prefixes` (ex. `formation_`, `mg_achat_`) : les tables
  sont résolues **dynamiquement** contre `pg_tables` (`resolve_tables`) — une
  nouvelle table préfixée est sauvegardée sans modifier le code ;
- `uploads_subdirs` (ex. immobilisations : `pieces`, `archives`) ;
- `ged_module_codes` : lignes `ged_documents` + dossier `storage/ged/{code}` du module
  (`None` = code du module, `[]` = pas de GED).

Tables **partagées** (jamais écrasées par un recovery module ou département) :
`SHARED_CORE_TABLES` — `users`, `roles`, `permissions`, `agences`, `directions`,
`departements`, `centres_cout`, `fournisseurs`, `journaux`, `plan_comptable`,
`plateforme_*`, `auth_*`, `audit_logs`, `notifications`, `ged_documents`
(seules les lignes GED du périmètre sont restaurées), etc.

Tests d'invariants : `backend/tests/test_core_admin_backups.py` (aucune table CORE
revendiquée par un module, aucune table revendiquée par deux modules).

## Tables ops ajoutées

- `platform_backups` — inventaire des sauvegardes
- `platform_restores` — historique recovery
- `platform_module_versions` — notes de version
- `platform_ops_flags` — maintenance globale (clé/valeur)

## Permissions

`core.admin.backup.view|create|delete|download`, `core.admin.recovery.view|execute`,
`core.admin.monitoring.view`, `core.admin.maintenance.view|manage`,
`core.admin.module_status.view|manage`, `core.admin.versions.view|manage`.

## Sauvegardes & Recovery (format v2)

UI CORE ADMIN (Login 1) — groupe « Sauvegardes & Recovery » :

| Route | Écran | Permission |
|-------|-------|------------|
| `/admin/sauvegardes` | Vue générale (KPI, dernières opérations, erreurs) | `backup.view` |
| `/admin/sauvegardes/sauvegarde` | Sauvegarde globale / département / module | `backup.create` |
| `/admin/sauvegardes/recovery` | Restauration globale / département / module | `recovery.execute` |
| `/admin/sauvegardes/historique` | Historique unifié + actions | `backup.view` (+ `download`, `recovery.execute`) |

`/admin/backups` et `/admin/recovery` redirigent vers ces écrans. Le masquage UI
n'est qu'un confort : **chaque endpoint revérifie la permission**.

### API (`/api/v1/plateforme/admin`)

| Méthode | Route | Rôle |
|---------|-------|------|
| GET | `/backups/catalogue` | Départements (`plateforme_espaces`) → modules (`plateforme_modules`) + tables résolues |
| GET | `/backups/preview?level&espace_code&module_code` | Récapitulatif avant exécution (modules, tables, lignes, taille estimée, admin) |
| POST | `/backups` | Lance la sauvegarde (`level`, `espace_code`, `module_code`) |
| GET | `/backups` | Liste filtrable (`level`, `espace_code`, `module_code`, `status`) |
| GET | `/backups/history` | Historique unifié sauvegardes + restaurations (paginé, filtres) |
| GET | `/backups/dashboard` | KPI |
| GET | `/backups/{id}` | Détail + manifeste + restaurations liées |
| POST | `/backups/{id}/verify` | Contrôle d'intégrité (SHA-256, `pg_restore -l`, archive lisible) |
| GET | `/backups/{id}/download` | Archive `.tar` des artefacts (`backup.download`) |
| DELETE | `/backups/{id}` | Supprime la sauvegarde et ses artefacts (`backup.delete`) |
| POST | `/backups/bulk-delete` | Suppression multiple `{ids: [...]}` (max 200) → `{deleted, failed}` (`backup.delete`) |
| GET | `/recovery/{id}/preview?include_security` | Impact : tables, lignes actuelles/sauvegardées, dépendances, tables préservées |
| POST | `/recovery/{id}` | Restauration (`confirmation`, `reason`, `acknowledge_dependencies`, `include_security`) |
| GET | `/recovery/restores/{id}` | Détail d'une restauration |

### Artefacts d'une sauvegarde (`backups/`, volume `./backups`)

`<base>.dump` (pg_dump custom, tables du périmètre), `<base>.ged.copy` (lignes
`ged_documents` du périmètre), `<base>.files.tar.gz` (uploads + GED fichiers),
`<base>.manifest.json`. Chaque artefact a son SHA-256 (`platform_backups.artifacts`) ;
`checksum_sha256` = empreinte du dump. Migration : `20261008_backup_recovery_v2`
(colonnes `checksum_sha256`, `artifacts`, `manifest`, `duration_ms`, `integrity_*`,
`ip_address` ; `platform_restores.reason|options|details|duration_ms|ip_address`).

### Mécanisme de restauration (jamais silencieuse)

1. Confirmation forte côté **backend** : phrase `RESTAURER GLOBAL` /
   `RESTAURER <CODE_DEPARTEMENT>` / `RESTAURER <CODE_MODULE>`, motif ≥ 10 caractères,
   `acknowledge_dependencies`. Une seule restauration à la fois (409 sinon).
2. Sauvegarde de **sécurité** du même périmètre (abandon si elle échoue).
3. Un seul `psql --single-transaction` : `lock_timeout 30s`,
   `session_replication_role = replica`, `DELETE` des tables du périmètre (+ lignes GED),
   données du dump (TOC filtrée : TABLE DATA + SEQUENCE SET), lignes GED,
   puis **contrôle d'intégrité référentielle** sur toutes les FK touchant le périmètre
   (`BEA_FK_VIOLATION` → ROLLBACK complet, message explicite).
4. Fichiers remplacés **après** succès SQL ; un échec fichiers = statut `partial`.
5. Audit `recovery_start` / `recovery_success|partial|failed` (utilisateur, IP,
   `request_id`, périmètre, ID sauvegarde, motif, erreur) + notification à tous les
   administrateurs recovery.

Restauration **globale** : les journaux (`GLOBAL_RESTORE_JOURNAL_TABLES` : audit,
notifications, sauvegardes, restaurations, sessions…) ne sont jamais réécrits ; le
plan sécurité (`SECURITY_PLANE_TABLES` : users, rôles, permissions, espaces, modules)
n'est restauré que sur option explicite `include_security`.

**DSI / TEST-PROD** : si le compte PostgreSQL applicatif n'est pas superutilisateur,
accorder `GRANT SET ON PARAMETER session_replication_role TO <compte>;` (PG ≥ 15),
sinon la restauration est refusée proprement (aucune donnée modifiée).

Audit des sauvegardes : `backup_create`, `backup_failed`, `backup_verify`,
`backup_verify_failed`, `backup_download`, `backup_delete`.

### Suppression des sauvegardes

L'administrateur (`core.admin.backup.delete`) peut supprimer n'importe quelle
sauvegarde, y compris les sauvegardes de sécurité, depuis l'historique (sélection
multiple ou icône par ligne) ou depuis le détail. Confirmation obligatoire
(`BeaAdminDialogService`), suppression irréversible (ligne + artefacts disque).

Seuls refus (409) : sauvegarde en cours (`BACKUP_RUNNING`) ou utilisée par une
restauration en cours (`BACKUP_IN_USE`). En suppression multiple, chaque ID est
traité dans un savepoint : un refus n'annule pas les autres.

L'historique des restaurations est conservé : migration `20261008_admin_powers`
(`platform_restores.backup_id` nullable, FK `ON DELETE SET NULL`) ; la trace de la
sauvegarde supprimée (libellé, niveau, dates, auteur) est copiée dans
`platform_restores.details.deleted_backup`.
