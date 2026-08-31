#Requires -Version 5.1
<#
.SYNOPSIS
  Prépare un kit USB pour le PC du comptable : images Docker + dump + documents.
  Ne copie PAS le fichier .env (secrets cloud).
#>
param(
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas disponible."
}

if (-not $Destination) {
    $Destination = Join-Path (Get-Location) "dist\kit-comptable"
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

Get-ChildItem "scripts\*.ps1" | Copy-Item -Destination (Join-Path $Destination "scripts") -Force

$dump = Get-ChildItem "backups\*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $dump) {
    throw "Aucun dump dans backups\. Lancez d'abord .\scripts\backup-from-supabase.ps1 ou backup-local.ps1"
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

Write-Host "Export des images Docker (environ 1,5 Go, quelques minutes)..."
$tar = Join-Path $imagesDir "immo-stack.tar"
docker save -o $tar postgres:17-alpine el-amana-immo-backend:latest el-amana-immo-frontend:latest
if (-not (Test-Path -LiteralPath $tar) -or (Get-Item $tar).Length -lt 1MB) {
    throw "Échec de docker save : $tar"
}

$lireMoi = @"
INSTALLATION — PC du comptable
================================

1. Installer Docker Desktop pour Windows (une fois, droits administrateur).
2. Démarrer Docker Desktop et attendre qu'il soit vert / "Running".
3. Copier TOUT ce dossier sur le disque du PC, par exemple :
   C:\immo
4. Ouvrir PowerShell dans ce dossier et lancer :

   powershell -ExecutionPolicy Bypass -File .\scripts\install-on-comptable.ps1

5. Ouvrir le navigateur : http://localhost

INTERDIT : docker compose down -v
(cela efface la base)

Sauvegarde quotidienne : .\scripts\backup-local.ps1
Arrêt propre          : .\scripts\stop-local.ps1
Redémarrage           : .\scripts\start-local.ps1
"@
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Join-Path $Destination "LIRE_MOI.txt"), $lireMoi, $utf8NoBom)

$tarSize = [math]::Round((Get-Item $tar).Length / 1MB)
Write-Host ""
Write-Host "Kit prêt : $Destination"
Write-Host "  Images : $tarSize Mo"
Write-Host "  Dump   : $($dump.Name)"
Write-Host "Copiez ce dossier sur une clé USB (plusieurs Go libres) puis sur le PC du comptable."
Write-Host "Ne copiez PAS le fichier .env de développement (secrets cloud)."
