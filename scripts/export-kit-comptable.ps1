#Requires -Version 5.1
<#
.SYNOPSIS
  Genere UN kit USB complet pour le PC comptable :
  images Docker (backend+frontend+postgres), scripts, lanceurs .cmd, docs,
  et le dump local le plus recent (si disponible).

.PARAMETER Destination
  Dossier de sortie (defaut : dist\kit-comptable).

.PARAMETER SkipBuild
  N'appelle pas docker compose build (utilise les images deja presentes).

.PARAMETER SkipBackup
  N'appelle pas backup-local avant export.
#>
param(
    [string]$Destination = "",
    [switch]$SkipBuild,
    [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas disponible."
}

if (-not $Destination) {
    $Destination = Join-Path (Get-Location) "dist\kit-comptable"
}

# Remove previous kits
$oldKits = @(
    (Join-Path (Get-Location) "dist\kit-comptable"),
    (Join-Path (Get-Location) "dist\kit-maj-comptable")
)
foreach ($old in $oldKits) {
    if (Test-Path -LiteralPath $old) {
        Write-Host "Suppression ancien kit : $old"
        Remove-Item -LiteralPath $old -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath ".env.docker")) {
    throw ".env.docker introuvable sur la machine de developpement."
}

if (-not $SkipBuild) {
    Write-Host "Construction des images backend + frontend..."
    docker compose --env-file .env.docker build frontend backend
    docker compose --env-file .env.docker up -d frontend backend
}

if (-not $SkipBackup) {
    Write-Host "Sauvegarde locale (pour inclusion eventuelle dans le kit)..."
    try {
        & (Join-Path "scripts" "backup-local.ps1")
    } catch {
        Write-Host "Avertissement : backup-local a echoue ($($_.Exception.Message)). Suite sans dump."
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

# Scripts PowerShell
Get-ChildItem "scripts\*.ps1" | Copy-Item -Destination (Join-Path $Destination "scripts") -Force

# Lanceurs .cmd a la racine du kit (double-clic)
$cmdSrc = "scripts\windows-cmd"
if (-not (Test-Path -LiteralPath $cmdSrc)) {
    throw "Dossier manquant : $cmdSrc"
}
Copy-Item (Join-Path $cmdSrc "*.cmd") $Destination -Force

# Docs
Copy-Item "docs\DEPLOIEMENT_LOCAL.md" (Join-Path $Destination "docs\DEPLOIEMENT_LOCAL.md") -Force -ErrorAction SilentlyContinue
Copy-Item "docs\MISE_A_JOUR_COMPTABLE.md" (Join-Path $Destination "docs\MISE_A_JOUR_COMPTABLE.md") -Force -ErrorAction SilentlyContinue

# Dump le plus recent + uploads
$dump = Get-ChildItem "backups\*.dump" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($dump) {
    Copy-Item $dump.FullName (Join-Path $Destination "backups\$($dump.Name)") -Force
    Write-Host "Dump inclus : $($dump.Name)"
} else {
    Write-Host "Aucun dump local - le kit partira sans backup\*.dump"
}

$uploadsBackup = Get-ChildItem "backups" -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "uploads-*" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (Test-Path "storage\uploads") {
    Copy-Item "storage\uploads\*" (Join-Path $Destination "storage\uploads") -Recurse -Force -ErrorAction SilentlyContinue
}
if ($uploadsBackup) {
    $dstUploads = Join-Path $Destination "backups\$($uploadsBackup.Name)"
    New-Item -ItemType Directory -Force -Path $dstUploads | Out-Null
    Copy-Item (Join-Path $uploadsBackup.FullName "*") $dstUploads -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Verification des images Docker..."
$needed = @("postgres:17-alpine", "el-amana-immo-backend:latest", "el-amana-immo-frontend:latest")
foreach ($img in $needed) {
    $id = docker images -q $img
    if (-not $id) {
        throw "Image manquante : $img. Relancez sans -SkipBuild."
    }
}

Write-Host "Export des images Docker (quelques minutes)..."
$tar = Join-Path $imagesDir "immo-stack.tar"
docker save -o $tar postgres:17-alpine el-amana-immo-backend:latest el-amana-immo-frontend:latest
if (-not (Test-Path -LiteralPath $tar) -or (Get-Item $tar).Length -lt 1MB) {
    throw "Echec de docker save : $tar"
}

$lireMoi = @(
    "KIT EL AMANA IMMO - PC COMPTABLE",
    "================================",
    "",
    "OU METTRE CE DOSSIER",
    "--------------------",
    "Copier TOUT ce dossier sur le PC comptable, par exemple :",
    "  C:\immo",
    "",
    "Si C:\immo existe deja (avec des saisies) :",
    "  - Copier PAR-DESSUS (images\, scripts\, *.cmd, docker-compose.yml)",
    "  - NE PAS supprimer .env.docker",
    "  - NE PAS faire docker compose down -v",
    "  - Double-cliquer : MettreAJour.cmd",
    "",
    "Si premiere installation (aucun C:\immo) :",
    "  1. Installer Docker Desktop, attendre Running",
    "  2. Copier ce dossier vers C:\immo",
    "  3. Double-cliquer : Installer.cmd",
    "",
    "LANCEURS (double-clic)",
    "---------------------",
    "  Demarrer.cmd     Demarrer la plateforme",
    "  Arreter.cmd      Arreter (donnees conservees)",
    "  Sauvegarder.cmd  Backup dump + documents",
    "  Verifier.cmd     Conteneurs + comptages + /health",
    "  MettreAJour.cmd  Nouveau logiciel SANS perdre les saisies",
    "  Installer.cmd    Premiere installation seulement",
    "",
    "DONNEES / SAISIES",
    "-----------------",
    "MettreAJour.cmd sauvegarde puis charge les nouvelles images.",
    "Le volume PostgreSQL (saisies) n'est PAS efface.",
    "Installer.cmd ne restaure un dump QUE si la base est vide.",
    "",
    "Ouvrir : http://localhost  (Ctrl+F5 apres mise a jour)",
    "",
    "INTERDIT : docker compose down -v"
)
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines((Join-Path $Destination "LIRE_MOI.txt"), $lireMoi, $utf8NoBom)

$tarSize = [math]::Round((Get-Item $tar).Length / 1MB)
Write-Host ""
Write-Host "========================================"
Write-Host "Kit pret : $Destination"
Write-Host "  Images : $tarSize Mo"
if ($dump) { Write-Host "  Dump   : $($dump.Name)" }
Write-Host "========================================"
Write-Host "1. Copier ce dossier sur une cle USB"
Write-Host "2. Sur le PC comptable : coller dans C:\immo"
Write-Host "3. Si deja installe -> MettreAJour.cmd"
Write-Host "   Si premier install  -> Installer.cmd"
Write-Host "Ne copiez PAS le fichier .env de developpement."
