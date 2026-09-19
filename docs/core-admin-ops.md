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

## Recovery partiel — dépendances Immobilisations

Tables **exclusives** (restaurables isolément) :

`immobilisations`, `pieces_jointes`, `amortissements`, `cessions`, `rebuts`,
`reevaluations`, `ajustements`, `ecritures_comptables`,
`soldes_ouverture_immobilisations`, `soldes_compte_orion`,
`periodes_amortissement`, `exercices_comptables`, `categories_immobilisation`,
`parametrage_amortissement`, `parametrage_ecriture`, `inventaire_scans`,
`archive_dossiers`, `archive_fichiers`, `archive_lignes`.

Tables **partagées** (jamais écrasées par un recovery module) :

`users`, `roles`, `permissions`, `agences`, `directions`, `departements`,
`centres_cout`, `fournisseurs`, `journaux`, `comptes_plan_comptable`,
`plateforme_*`, `auth_*`, `audit_logs`, `notifications`, `ged_documents`.

Fichiers : sous-dossier `storage/uploads/immobilisations` (+ chemins `pieces_jointes`).

Avant recovery module : backup de sécurité du même périmètre + avertissement
dépendances.

## Tables ops ajoutées

- `platform_backups` — inventaire des sauvegardes
- `platform_restores` — historique recovery
- `platform_module_versions` — notes de version
- `platform_ops_flags` — maintenance globale (clé/valeur)

## Permissions

`core.admin.backup.view|create|delete`, `core.admin.recovery.view|execute`,
`core.admin.monitoring.view`, `core.admin.maintenance.view|manage`,
`core.admin.module_status.view|manage`, `core.admin.versions.view|manage`.
