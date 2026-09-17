#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$envFile = ".env.docker"
if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env.docker introuvable."
}

Write-Host "Santé des conteneurs :"
docker compose --env-file $envFile ps
Write-Host ""
Write-Host "Comptages :"
$queries = @(
    "SELECT 'immobilisations' AS objet, count(*) AS n FROM immobilisations;",
    "SELECT 'agences' AS objet, count(*) AS n FROM agences;",
    "SELECT 'users' AS objet, count(*) AS n FROM users;",
    "SELECT 'pieces_jointes' AS objet, count(*) AS n FROM pieces_jointes;",
    "SELECT annee, statut FROM exercices_comptables ORDER BY annee;"
)
foreach ($q in $queries) {
    docker compose --env-file $envFile exec -T postgres psql -U immo_user -d immobilisations -c $q
}

Write-Host "Health API :"
try {
    $h = Invoke-WebRequest -Uri "http://localhost/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "  $($h.StatusCode) $($h.Content)"
} catch {
    Write-Host "  http://localhost injoignable pour l'instant."
}
