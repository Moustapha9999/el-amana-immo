#Requires -Version 5.1
<#
.SYNOPSIS
  Arrête les conteneurs SANS supprimer les volumes (données conservées).
#>
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

docker compose --env-file .env.docker down
Write-Host "Conteneurs arrêtés. Volume PostgreSQL et documents conservés."
Write-Host "Interdit : docker compose down -v"
