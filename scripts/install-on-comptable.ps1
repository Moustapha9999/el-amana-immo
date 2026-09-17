#Requires -Version 5.1
<#
.SYNOPSIS
  Installe l'instance sur le PC du comptable a partir du kit USB.
  Charge les images, demarre Docker.
  Si la base contient deja des saisies : NE PAS restaurer (conservation).
  Sinon : restaure le dump le plus recent dans backups\.
#>
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas disponible. Installez Docker Desktop, demarrez-le, puis relancez."
}

function Get-StackTar {
    foreach ($name in @("bea-digital-stack.tar", "immo-stack.tar")) {
        $p = Join-Path "images" $name
        if (Test-Path -LiteralPath $p) { return $p }
    }
    throw "images\bea-digital-stack.tar introuvable. Copiez le kit complet (dossier images inclus)."
}

$tar = Get-StackTar

Write-Host "1/4 Chargement des images Docker (quelques minutes)..."
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
    Write-Host "Fichier .env.docker cree."
}

Write-Host "2/4 Demarrage de PostgreSQL..."
docker compose --env-file .env.docker up -d --no-build --pull never postgres

$deadline = (Get-Date).AddMinutes(3)
$pg = $null
do {
    Start-Sleep -Seconds 3
    $cid = docker compose --env-file .env.docker ps -q postgres
    $pg = docker inspect --format "{{.State.Health.Status}}" $cid 2>$null
    if ($pg -eq "healthy") { break }
} while ((Get-Date) -lt $deadline)

if ($pg -ne "healthy") {
    docker compose --env-file .env.docker ps
    throw "PostgreSQL n'est pas pret. Verifiez Docker Desktop puis relancez."
}

# Detect existing business data (preserve accountant saisies)
$existingCount = $null
try {
    $pgUser = "immo_user"
    $pgDb = "bea_digital"
    if (Test-Path -LiteralPath ".env.docker") {
        foreach ($line in Get-Content ".env.docker") {
            $trim = $line.Trim()
            if ($trim -match "^POSTGRES_USER=(.*)$") { $pgUser = $Matches[1].Trim().Trim('"').Trim("'") }
            if ($trim -match "^POSTGRES_DB=(.*)$") { $pgDb = $Matches[1].Trim().Trim('"').Trim("'") }
        }
    }
    $existingCount = (
        docker compose --env-file .env.docker exec -T postgres `
            psql -U $pgUser -d $pgDb -tAc "SELECT count(*) FROM immobilisations;" 2>$null
    ).Trim()
} catch {
    $existingCount = $null
}

$hasData = $false
if ($existingCount -match '^\d+$' -and [int]$existingCount -gt 0) {
    $hasData = $true
}

if ($hasData) {
    Write-Host "3/4 Base deja peuplee ($existingCount immobilisations) - restauration IGNOREES."
    Write-Host "    Les saisies du PC comptable sont conservees."
} else {
    $dump = Get-ChildItem "backups\*.dump" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($dump) {
        Write-Host "3/4 Restauration de $($dump.Name) (base vide)..."
        & (Join-Path "scripts" "restore-local.ps1") -DumpFile $dump.FullName
    } else {
        Write-Host "3/4 Aucun dump dans backups\ et base vide - demarrage a vide."
    }
}

Write-Host "4/4 Demarrage backend + frontend..."
docker compose --env-file .env.docker up -d --no-build --pull never

$deadline2 = (Get-Date).AddMinutes(4)
do {
    Start-Sleep -Seconds 4
    $cid = docker compose --env-file .env.docker ps -q backend
    $st = docker inspect --format "{{.State.Health.Status}}" $cid 2>$null
    if ($st -eq "healthy") { break }
} while ((Get-Date) -lt $deadline2)

Write-Host ""
Write-Host "Installation terminee."
Write-Host "Ouvrir : http://localhost"
Write-Host "INTERDIT : docker compose down -v"
Write-Host "Usage quotidien : Demarrer.cmd / Arreter.cmd / Sauvegarder.cmd / Verifier.cmd"
