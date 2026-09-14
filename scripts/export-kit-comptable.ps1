#Requires -Version 5.1
<#
.SYNOPSIS
  Prepare un kit USB pour le PC du comptable.
.PARAMETER Destination
  Dossier de sortie (defaut : dist\kit-comptable).
.PARAMETER UpdateOnly
  Kit de MISE A JOUR : images + scripts uniquement.
  Ne force PAS de dump de cette machine (les donnees restent sur le PC comptable).
  Sans ce flag : kit d'installation initiale (images + dump + documents).
#>
param(
    [string]$Destination = "",
    [switch]$UpdateOnly
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas disponible."
}

if (-not $Destination) {
    if ($UpdateOnly) {
        $Destination = Join-Path (Get-Location) "dist\kit-maj-comptable"
    } else {
        $Destination = Join-Path (Get-Location) "dist\kit-comptable"
    }
}

$imagesDir = Join-Path $Destination "images"
New-Item -ItemType Directory -Force -Path $imagesDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Destination "backups") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Destination "storage\uploads") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Destination "database\init") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Destination "scripts") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Destination "docs") | Out-Null

$required = @(
    "docker-compose.yml",
    ".env.docker.example",
    "database\init\01-extensions.sql"
)
foreach ($rel in $required) {
    if (-not (Test-Path -LiteralPath $rel)) {
        throw "Fichier manquant : $rel"
    }
}

Copy-Item "docker-compose.yml" (Join-Path $Destination "docker-compose.yml") -Force
Copy-Item ".env.docker.example" (Join-Path $Destination ".env.docker.example") -Force
Copy-Item "database\init\01-extensions.sql" (Join-Path $Destination "database\init\01-extensions.sql") -Force
Copy-Item "docs\DEPLOIEMENT_LOCAL.md" (Join-Path $Destination "docs\DEPLOIEMENT_LOCAL.md") -Force -ErrorAction SilentlyContinue
if (Test-Path "docs\MISE_A_JOUR_COMPTABLE.md") {
    Copy-Item "docs\MISE_A_JOUR_COMPTABLE.md" (Join-Path $Destination "docs\MISE_A_JOUR_COMPTABLE.md") -Force
}

Get-ChildItem "scripts\*.ps1" | Copy-Item -Destination (Join-Path $Destination "scripts") -Force

$dump = $null
if (-not $UpdateOnly) {
    $dump = Get-ChildItem "backups\*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $dump) {
        throw "Aucun dump dans backups\. Lancez d'abord .\scripts\backup-local.ps1"
    }
    Copy-Item $dump.FullName (Join-Path $Destination "backups\$($dump.Name)") -Force

    $uploadsBackup = Get-ChildItem "backups" -Directory | Where-Object { $_.Name -like "uploads-*" } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (Test-Path "storage\uploads") {
        Copy-Item "storage\uploads\*" (Join-Path $Destination "storage\uploads") -Recurse -Force -ErrorAction SilentlyContinue
    } elseif ($uploadsBackup) {
        Copy-Item (Join-Path $uploadsBackup.FullName "*") (Join-Path $Destination "storage\uploads") -Recurse -Force
    }
    if ($uploadsBackup) {
        $dstUploads = Join-Path $Destination "backups\$($uploadsBackup.Name)"
        New-Item -ItemType Directory -Force -Path $dstUploads | Out-Null
        Copy-Item (Join-Path $uploadsBackup.FullName "*") $dstUploads -Recurse -Force
    }
}

Write-Host "Verification des images Docker locales..."
$needed = @("postgres:17-alpine", "el-amana-immo-backend:latest", "el-amana-immo-frontend:latest")
foreach ($img in $needed) {
    $id = docker images -q $img
    if (-not $id) {
        throw "Image manquante : $img. Lancez d'abord : docker compose --env-file .env.docker build"
    }
}

Write-Host "Export des images Docker (environ 1,5 Go, quelques minutes)..."
$tar = Join-Path $imagesDir "immo-stack.tar"
if (Test-Path -LiteralPath $tar) {
    Remove-Item -LiteralPath $tar -Force
}
docker save -o $tar postgres:17-alpine el-amana-immo-backend:latest el-amana-immo-frontend:latest
if (-not (Test-Path -LiteralPath $tar) -or (Get-Item $tar).Length -lt 1MB) {
    throw "Echec de docker save : $tar"
}

$lireMoiPath = Join-Path $Destination "LIRE_MOI.txt"
if ($UpdateOnly) {
    $lines = @(
        "MISE A JOUR - PC du comptable (deja installe)",
        "=============================================",
        "",
        "Ce kit met a jour le LOGICIEL uniquement.",
        "Il ne remplace PAS les donnees deja saisies sur le PC comptable.",
        "",
        "Sur le PC comptable (dans le dossier d'installation, ex. C:\immo) :",
        "",
        "1. Copier le contenu de ce kit PAR-DESSUS l'installation existante",
        "   (surtout le dossier images\ et scripts\).",
        "   Ne pas supprimer .env.docker ni le volume Docker.",
        "",
        "2. PowerShell dans C:\immo :",
        "",
        "   powershell -ExecutionPolicy Bypass -File .\scripts\update-on-comptable.ps1",
        "",
        "3. Ouvrir http://localhost puis Ctrl+F5",
        "",
        "Le script fait : backup local -> charge images -> recree backend/frontend.",
        "PostgreSQL et les operations restent en place.",
        "",
        "INTERDIT : docker compose down -v"
    )
} else {
    $lines = @(
        "INSTALLATION - PC du comptable",
        "================================",
        "",
        "1. Installer Docker Desktop pour Windows (une fois, droits administrateur).",
        "2. Demarrer Docker Desktop et attendre qu'il soit vert / Running.",
        "3. Copier TOUT ce dossier sur le disque du PC, par exemple : C:\immo",
        "4. Ouvrir PowerShell dans ce dossier et lancer :",
        "",
        "   powershell -ExecutionPolicy Bypass -File .\scripts\install-on-comptable.ps1",
        "",
        "5. Ouvrir le navigateur : http://localhost",
        "",
        "MISE A JOUR ulterieure (instance deja en place) :",
        "",
        "   powershell -ExecutionPolicy Bypass -File .\scripts\update-on-comptable.ps1",
        "",
        "INTERDIT : docker compose down -v (cela efface la base)",
        "",
        "Sauvegarde quotidienne : .\scripts\backup-local.ps1",
        "Arret propre          : .\scripts\stop-local.ps1",
        "Redemarrage           : .\scripts\start-local.ps1"
    )
}

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($lireMoiPath, $lines, $utf8NoBom)

$tarSize = [math]::Round((Get-Item $tar).Length / 1MB)
Write-Host ""
Write-Host "Kit pret : $Destination"
if ($UpdateOnly) {
    Write-Host "  Mode   : MISE A JOUR (sans dump dev)"
} else {
    Write-Host "  Mode   : INSTALLATION (+ dump)"
    Write-Host "  Dump   : $($dump.Name)"
}
Write-Host "  Images : $tarSize Mo"
Write-Host "Copiez ce dossier sur une cle USB puis sur le PC du comptable."
Write-Host "Ne copiez PAS le fichier .env de developpement (secrets cloud)."
