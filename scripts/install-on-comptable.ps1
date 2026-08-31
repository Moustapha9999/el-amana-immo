#Requires -Version 5.1
<#
.SYNOPSIS
  Installe l'instance sur le PC du comptable à partir du kit USB.
  Charge les images, démarre Docker, restaure le dump.
#>
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas disponible. Installez Docker Desktop, démarrez-le, puis relancez."
}

$tar = Join-Path "images" "immo-stack.tar"
if (-not (Test-Path -LiteralPath $tar)) {
    throw "images\immo-stack.tar introuvable. Copiez le kit complet (dossier images inclus)."
}

Write-Host "Chargement des images Docker (quelques minutes)..."
docker load -i $tar

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
    Write-Host "Fichier .env.docker créé."
}

Write-Host "Démarrage de PostgreSQL..."
docker compose --env-file .env.docker up -d --no-build --pull never postgres

$deadline = (Get-Date).AddMinutes(3)
do {
    Start-Sleep -Seconds 3
    $pg = docker inspect --format "{{.State.Health.Status}}" immo-postgres 2>$null
    if ($pg -eq "healthy") { break }
} while ((Get-Date) -lt $deadline)

if ($pg -ne "healthy") {
    docker compose --env-file .env.docker ps
    throw "PostgreSQL n'est pas prêt. Vérifiez Docker Desktop puis relancez."
}

$dump = Get-ChildItem "backups\*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($dump) {
    Write-Host "Restauration de $($dump.Name)..."
    & (Join-Path "scripts" "restore-local.ps1") -DumpFile $dump.FullName
} else {
    Write-Host "Aucun dump dans backups\ — base vide. Restaurez un dump plus tard."
}

Write-Host ""
Write-Host "Installation terminée."
Write-Host "Ouvrir : http://localhost"
Write-Host "Ne jamais exécuter : docker compose down -v"
