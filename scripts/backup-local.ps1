#Requires -Version 5.1
<#
.SYNOPSIS
  Sauvegarde PostgreSQL Docker (BEA DIGITAL) + documents.
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

New-Item -ItemType Directory -Force -Path "backups" | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpName = "local-$stamp.dump"

Write-Host "Dump PostgreSQL local -> backups/$dumpName"
docker compose --env-file $envFile exec -T postgres `
    pg_dump -U $pgUser -d $pgDb --format=custom --no-owner --no-acl --file="/backups/$dumpName"

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
