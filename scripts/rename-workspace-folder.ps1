#Requires -Version 5.1
<#
.SYNOPSIS
  Renomme le dossier du dépôt en bea-digital (à lancer après avoir fermé Cursor).
#>
$ErrorActionPreference = "Stop"
$src = "C:\Users\sallm\el-amana-immo"
$dst = "C:\Users\sallm\bea-digital"

if (-not (Test-Path -LiteralPath $src)) {
    throw "Source introuvable : $src"
}

Set-Location $src
if (Test-Path ".env.docker") {
    docker compose --env-file .env.docker down
}

if (Test-Path -LiteralPath $dst) {
    $item = Get-Item -LiteralPath $dst -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        cmd /c rmdir "$dst"
    } else {
        throw "$dst existe déjà et n'est pas une jonction. Arrêt."
    }
}

Rename-Item -LiteralPath $src -NewName "bea-digital"
Write-Host "Dossier : $dst"
Write-Host "Rouvrir ce dossier dans Cursor, puis : docker compose --env-file .env.docker up -d"
Write-Host "Application : http://localhost"
