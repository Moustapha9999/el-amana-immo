#Requires -Version 5.1
$rootScript = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "scripts\rename-workspace-folder.ps1"
if (-not (Test-Path -LiteralPath $rootScript)) {
    throw "Script introuvable : $rootScript"
}
& $rootScript @args
