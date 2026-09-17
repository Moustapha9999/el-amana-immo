#Requires -Version 5.1
<#
.SYNOPSIS
  Restaure un dump PostgreSQL dans l'instance Docker locale.
  Recrée la base (sans toucher au volume) puis importe le dump.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$DumpFile,
    [string]$RestoreUploads
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$envFile = ".env.docker"
if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env.docker introuvable."
}

$dumpPath = $DumpFile
if (-not (Test-Path -LiteralPath $dumpPath)) {
    $alt = Join-Path "backups" $DumpFile
    if (Test-Path -LiteralPath $alt) { $dumpPath = $alt }
}
if (-not (Test-Path -LiteralPath $dumpPath)) {
    throw "Dump introuvable : $DumpFile"
}

$dumpName = Split-Path -Leaf $dumpPath
$backupsAbs = (Resolve-Path "backups").Path
$dumpAbs = (Resolve-Path $dumpPath).Path
if ($dumpAbs.ToLowerInvariant().StartsWith($backupsAbs.ToLowerInvariant()) -eq $false) {
    Copy-Item -LiteralPath $dumpAbs -Destination (Join-Path "backups" $dumpName) -Force
}

function Get-EnvValue([string]$path, [string]$key, [string]$default) {
    foreach ($line in Get-Content -LiteralPath $path) {
        $trim = $line.Trim()
        if ($trim.StartsWith("#") -or $trim -eq "") { continue }
        if ($trim -match "^$key=(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $default
}

$pgUser = Get-EnvValue $envFile "POSTGRES_USER" "immo_user"
$pgDb = Get-EnvValue $envFile "POSTGRES_DB" "bea_digital"

Write-Host "Restauration de $dumpName dans PostgreSQL local..."
docker compose --env-file $envFile stop backend frontend

docker compose --env-file $envFile exec -T postgres `
    psql -U $pgUser -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$pgDb' AND pid <> pg_backend_pid();"

docker compose --env-file $envFile exec -T postgres dropdb --if-exists -U $pgUser $pgDb
docker compose --env-file $envFile exec -T postgres createdb -U $pgUser $pgDb
docker compose --env-file $envFile exec -T postgres `
    psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE;"

docker compose --env-file $envFile exec -T postgres `
    pg_restore -U $pgUser -d $pgDb --no-owner --no-acl "/backups/$dumpName"
if ($LASTEXITCODE -ne 0) {
    Write-Host "pg_restore a renvoyé le code $LASTEXITCODE — contrôle des tables..."
}

$tableCheck = docker compose --env-file $envFile exec -T postgres `
    psql -U $pgUser -d $pgDb -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
if ([int]$tableCheck.Trim() -lt 5) {
    throw "Restauration incomplète : seulement $tableCheck table(s) dans public."
}
Write-Host "Tables public : $($tableCheck.Trim())"

if ($RestoreUploads) {
    if (-not (Test-Path -LiteralPath $RestoreUploads)) {
        throw "Dossier documents introuvable : $RestoreUploads"
    }
    Write-Host "Restauration documents -> storage/uploads"
    New-Item -ItemType Directory -Force -Path "storage/uploads" | Out-Null
    Copy-Item -Path (Join-Path $RestoreUploads "*") -Destination "storage/uploads" -Recurse -Force
}

docker compose --env-file $envFile up -d --no-build --pull never
Write-Host "Restauration terminée. Vérifiez avec : .\scripts\check-local.ps1"
