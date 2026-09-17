#Requires -Version 5.1
# Relais : le script canonique est à la racine du dépôt.
$rootScript = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "scripts\bea-supabase.ps1"
if (-not (Test-Path -LiteralPath $rootScript)) {
    throw "Script introuvable : $rootScript"
}
& $rootScript @args
