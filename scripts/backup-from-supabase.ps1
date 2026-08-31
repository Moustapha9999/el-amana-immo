#Requires -Version 5.1
<#
.SYNOPSIS
  Sauvegarde la base actuelle (Supabase / .env) et les documents locaux.
  À lancer AVANT toute installation Docker locale.
#>
param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Get-EnvValue([string]$path, [string]$key) {
    foreach ($line in Get-Content -LiteralPath $path) {
        $trim = $line.Trim()
        if ($trim.StartsWith("#") -or $trim -eq "") { continue }
        if ($trim -match "^$key=(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Fichier $EnvFile introuvable. La sauvegarde a besoin de DATABASE_URL."
}

$url = Get-EnvValue $EnvFile "DATABASE_URL"
if (-not $url) { throw "DATABASE_URL manquant dans $EnvFile" }
$url = $url -replace "^postgresql\+asyncpg://", "postgresql://"
if ($url -notmatch "sslmode=") {
    if ($url.Contains("?")) { $url += "&sslmode=require" } else { $url += "?sslmode=require" }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas disponible. Installez Docker Desktop puis relancez ce script."
}

New-Item -ItemType Directory -Force -Path "backups" | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpName = "supabase-public-$stamp.dump"
$hostDump = Join-Path "backups" $dumpName

$backupsAbs = (Resolve-Path "backups").Path
Write-Host "Dump PostgreSQL (schema public) -> $hostDump"
docker run --rm `
    -e "DATABASE_URL=$url" `
    -v "${backupsAbs}:/backups" `
    postgres:17-alpine `
    sh -c "pg_dump --dbname=`"`$DATABASE_URL`" --format=custom --no-owner --no-acl --schema=public --file=/backups/$dumpName"

if (-not (Test-Path -LiteralPath $hostDump) -or (Get-Item $hostDump).Length -lt 1024) {
    throw "Dump vide ou manquant : $hostDump"
}

Write-Host "Vérification du dump (liste des objets)..."
docker run --rm -v "${backupsAbs}:/backups" postgres:17-alpine `
    pg_restore --list "/backups/$dumpName" | Select-Object -First 20

$uploadsSrc = "storage/uploads"
$uploadsDst = Join-Path "backups" "uploads-$stamp"
if (Test-Path -LiteralPath $uploadsSrc) {
    Write-Host "Copie documents -> $uploadsDst"
    Copy-Item -LiteralPath $uploadsSrc -Destination $uploadsDst -Recurse -Force
} else {
    Write-Host "Aucun dossier $uploadsSrc (copie documents ignorée)."
}

$manifest = Join-Path "backups" "manifest-$stamp.txt"
@(
    "stamp=$stamp"
    "source=$EnvFile"
    "dump=$dumpName"
    "dump_bytes=$((Get-Item $hostDump).Length)"
    "uploads=$(if (Test-Path $uploadsDst) { $uploadsDst } else { 'none' })"
    "created=$(Get-Date -Format o)"
) | Set-Content -LiteralPath $manifest -Encoding UTF8

Write-Host ""
Write-Host "Backup OK"
Write-Host "  Dump      : $hostDump"
Write-Host "  Documents : $(if (Test-Path $uploadsDst) { $uploadsDst } else { 'n/a' })"
Write-Host "  Manifest  : $manifest"
Write-Host "Conservez une copie de backups\ hors de cette machine si la politique le permet."
