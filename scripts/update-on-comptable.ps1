#Requires -Version 5.1
<#
.SYNOPSIS
  Met a jour le code (images Docker) sur le PC comptable SANS toucher aux donnees.
  A utiliser quand l'instance existe deja et contient des operations metier.
#>
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas disponible. Installez / demarrez Docker Desktop, puis relancez."
}

function Get-StackTar {
    foreach ($name in @("bea-digital-stack.tar", "immo-stack.tar")) {
        $p = Join-Path "images" $name
        if (Test-Path -LiteralPath $p) { return $p }
    }
    throw "images\bea-digital-stack.tar introuvable. Copiez le kit de mise a jour complet."
}

$tar = Get-StackTar

if (-not (Test-Path -LiteralPath ".env.docker")) {
    throw ".env.docker introuvable. Ce script est pour une instance deja installee. Utilisez Installer.cmd pour une 1re install."
}

Write-Host "1/4 Sauvegarde locale avant mise a jour (nouvelles saisies preservees dans backups\)..."
& (Join-Path "scripts" "backup-local.ps1")

Write-Host ""
Write-Host "2/4 Chargement des nouvelles images (backend + frontend)..."
docker load -i $tar

Write-Host ""
Write-Host "3/4 Redemarrage des conteneurs (volume Postgres conserve)..."
docker compose --env-file .env.docker up -d --no-build --pull never --force-recreate backend frontend

Write-Host "Attente sante backend (migrations Alembic au demarrage)..."
$deadline = (Get-Date).AddMinutes(4)
$healthy = $false
do {
    Start-Sleep -Seconds 4
    $cid = docker compose --env-file .env.docker ps -q backend
    $st = docker inspect --format "{{.State.Health.Status}}" $cid 2>$null
    if ($st -eq "healthy") {
        $healthy = $true
        break
    }
    if ($st -eq "unhealthy") {
        docker compose --env-file .env.docker logs --tail=80 backend
        throw "Backend unhealthy apres mise a jour. Les donnees Postgres n'ont pas ete effacees."
    }
} while ((Get-Date) -lt $deadline)

if (-not $healthy) {
    docker compose --env-file .env.docker ps
    throw "Timeout sante backend. Verifiez les logs : docker compose --env-file .env.docker logs --tail=100 backend"
}

Write-Host ""
Write-Host "4/4 OK - mise a jour terminee."
Write-Host "Ouvrir : http://localhost  (Ctrl+F5 pour vider le cache navigateur)"
Write-Host ""
Write-Host "INTERDIT : docker compose down -v"
Write-Host "Les saisies du comptable sont conservees (volume bea_postgres_data)."
