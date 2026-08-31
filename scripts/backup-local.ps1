#Requires -Version 5.1
<#
.SYNOPSIS
  Sauvegarde PostgreSQL local (conteneur) + documents.
  À lancer quotidiennement pendant la saisie 2026.
#>
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas disponible."
}

$envFile = ".env.docker"
if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env.docker introuvable. Copiez .env.docker.example vers .env.docker."
}

New-Item -ItemType Directory -Force -Path "backups" | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpName = "local-$stamp.dump"

Write-Host "Dump PostgreSQL local -> backups/$dumpName"
docker compose --env-file $envFile exec -T postgres `
    pg_dump -U immo_user -d immobilisations --format=custom --no-owner --no-acl --file="/backups/$dumpName"

$hostDump = Join-Path "backups" $dumpName
if (-not (Test-Path -LiteralPath $hostDump) -or (Get-Item $hostDump).Length -lt 1024) {
    throw "Dump vide ou manquant : $hostDump"
}

$uploadsSrc = "storage/uploads"
$uploadsDst = Join-Path "backups" "uploads-$stamp"
if (Test-Path -LiteralPath $uploadsSrc) {
    Write-Host "Copie documents -> $uploadsDst"
    Copy-Item -LiteralPath $uploadsSrc -Destination $uploadsDst -Recurse -Force
}

Write-Host "Backup local OK : $hostDump"
