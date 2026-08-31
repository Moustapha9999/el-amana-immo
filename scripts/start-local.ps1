#Requires -Version 5.1
<#
.SYNOPSIS
  Démarre l'instance locale Docker (comptable).
  Crée .env.docker à partir de l'exemple si besoin.
.PARAMETER Build
  Reconstruit les images (machine de développement avec Internet).
  Sans ce flag : utilise les images déjà chargées (kit USB).
#>
param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas disponible. Installez Docker Desktop, démarrez-le, puis relancez."
}

if (-not (Test-Path -LiteralPath ".env.docker")) {
    if (-not (Test-Path -LiteralPath ".env.docker.example")) {
        throw ".env.docker.example introuvable."
    }
    $secret = -join ((1..64) | ForEach-Object { "{0:x}" -f (Get-Random -Maximum 16) })
    $password = -join ((1..32) | ForEach-Object { "{0:x}" -f (Get-Random -Maximum 16) })
    $content = (Get-Content ".env.docker.example" -Raw) `
        -replace "REMPLACER_PAR_UNE_CLE_ALEATOIRE_64_CARACTERES", $secret `
        -replace "REMPLACER_PAR_UN_MOT_DE_PASSE_FORT", $password
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText((Join-Path (Get-Location) ".env.docker"), $content, $utf8NoBom)
    Write-Host "Fichier .env.docker créé avec des secrets aléatoires."
}

if ($Build) {
    Write-Host "Construction et démarrage..."
    docker compose --env-file .env.docker up -d --build
} else {
    Write-Host "Démarrage à partir des images locales (sans rebuild)..."
    docker compose --env-file .env.docker up -d --no-build --pull never
}
docker compose --env-file .env.docker ps
Write-Host ""
Write-Host "Application : http://localhost"
Write-Host "Ne jamais exécuter : docker compose down -v"
