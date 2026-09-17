#Requires -Version 5.1
# BEA DIGITAL se lance via Docker, pas ng serve (:4200).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
& (Join-Path "scripts" "start-local.ps1")
Write-Host "Ouvrir uniquement : http://localhost"
