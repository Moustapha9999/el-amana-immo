# Docker Compose de l'environnement de charge isole (projet bea-loadtest).
# Fichier ASCII : Windows PowerShell 5.1 lit les .ps1 sans BOM en ANSI.
#
#   .\loadtest\lt-compose.ps1 ps
#   .\loadtest\lt-compose.ps1 logs -f lt-backend
#   .\loadtest\lt-compose.ps1 down          # arrete la pile de charge (jamais -v)
#
# Le mot de passe du role bea_app est lu dans .env.docker le temps de la commande, sans copie.

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$envLt = Join-Path $PSScriptRoot ".env.loadtest"
if (-not (Test-Path $envLt)) { throw "loadtest/.env.loadtest absent : lancer d'abord .\loadtest\setup-env.ps1" }
if ($args -contains "-v" -or $args -contains "--volumes") { throw "Option -v interdite." }

$ligne = Select-String -Path (Join-Path $racine ".env.docker") -Pattern '^BEA_APP_DB_PASSWORD=(.+)$'
if (-not $ligne) { throw "BEA_APP_DB_PASSWORD absent de .env.docker" }
$env:BEA_APP_DB_PASSWORD = $ligne.Matches[0].Groups[1].Value.Trim()
try {
    docker compose -f (Join-Path $PSScriptRoot "docker-compose.loadtest.yml") --env-file $envLt @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose a echoue (code $LASTEXITCODE)" }
}
finally {
    Remove-Item Env:BEA_APP_DB_PASSWORD -ErrorAction SilentlyContinue
}
