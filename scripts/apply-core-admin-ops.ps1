#Requires -Version 5.1
<#
.SYNOPSIS
  Applique la révision Alembic CORE ADMIN ops (backups / recovery / statuts).
  Ne touche pas aux tables métier immobilisations.

  Usage (instance Docker) :
    .\scripts\apply-core-admin-ops.ps1
#>
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$envFile = ".env.docker"
if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env.docker introuvable."
}

Write-Host "Backup de sécurité avant migration ops…"
& "$PSScriptRoot\backup-local.ps1"

Write-Host "Application Alembic 20260918_core_admin_ops (SKIP_MIGRATIONS temporairement contourné)…"
docker compose --env-file $envFile exec -T backend `
    sh -c "cd /app && SKIP_MIGRATIONS=0 alembic upgrade 20260918_core_admin_ops"

Write-Host "OK — tables platform_backups / platform_restores / versions / flags + permissions ops."
Write-Host "Contrôle : ouvrir CORE ADMIN → Sauvegardes / Supervision."
