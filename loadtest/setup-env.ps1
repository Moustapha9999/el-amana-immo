# Prepare l'environnement ISOLE de test de charge BEA DIGITAL.
# Fichier ASCII : Windows PowerShell 5.1 lit les .ps1 sans BOM en ANSI.
#
#   .\loadtest\setup-env.ps1            # cree la base de test si absente, puis demarre la pile
#   .\loadtest\setup-env.ps1 -Recreer   # supprime et regenere UNIQUEMENT bea_digital_test
#
# Base de test unique bea_digital_test sur le serveur PostgreSQL unique (bea-postgres) :
#   1. construite par scripts/test-db.ps1 (copie de bea_digital, Base Clientele, acces neutralises) ;
#   2. donnees synthetiques (loadtest/seed_loadtest.py) : comptes @loadtest.example.com, stock,
#      immobilisations, notifications (idempotent : rien si les comptes existent).
# Les tests de stock (pytest) vident les tables de stock : recreer la base avant une campagne de charge.
# Aucune ecriture dans bea_digital. Pile : http://127.0.0.1:8081

param([switch]$Recreer)

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$BASE = "bea_digital_test"
$PG = "bea-postgres"
$envLt = Join-Path $PSScriptRoot ".env.loadtest"
$compose = Join-Path $PSScriptRoot "lt-compose.ps1"

function Etape($texte) { Write-Host "==> $texte" -ForegroundColor Cyan }
function Psql($base, $sql) {
    $sortie = $sql | docker exec -i $PG psql -U admin -d $base -X -q -v ON_ERROR_STOP=1 -At 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql ($base) : $sortie" }
    return $sortie
}
function Secret([int]$octets) {
    $b = New-Object byte[] $octets
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return ([BitConverter]::ToString($b) -replace "-", "").ToLower()
}

Push-Location $racine
try {
    if ((docker inspect -f "{{.State.Health.Status}}" $PG 2>$null) -ne "healthy") {
        throw "$PG n'est pas demarre : docker compose --env-file .env.docker up -d postgres"
    }
    foreach ($image in "bea-digital-backend:latest", "bea-digital-frontend:latest") {
        docker image inspect $image *> $null
        if ($LASTEXITCODE -ne 0) { throw "Image $image absente : docker compose --env-file .env.docker build" }
    }

    if (-not (Test-Path $envLt)) {
        Etape "Secrets propres a l'environnement de charge (loadtest/.env.loadtest, ignore par git)"
        $mdp = "Lt-" + (Secret 9) + "-Aa9!"
        @(
            "# Environnement de charge ISOLE - genere par setup-env.ps1, ne pas committer.",
            "LT_SECRET_KEY=$(Secret 32)",
            "LOADTEST_PASSWORD=$mdp"
        ) | Out-File -FilePath $envLt -Encoding ascii
    }
    $mdpTest = (Select-String -Path $envLt -Pattern '^LOADTEST_PASSWORD=(.+)$').Matches[0].Groups[1].Value.Trim()
    New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot ".storage\uploads"), (Join-Path $PSScriptRoot ".storage\ged") | Out-Null

    if ($Recreer) {
        Etape "Arret de la pile de charge avant regeneration de $BASE"
        & $compose down --remove-orphans
    }
    & (Join-Path $racine "scripts\test-db.ps1") -Recreer:$Recreer

    Etape "Donnees synthetiques (quelques minutes)"
    & $compose up -d lt-redis
    $env:LOADTEST_PASSWORD = $mdpTest
    try { & $compose run --rm -e LOADTEST_PASSWORD lt-backend python /loadtest/seed_loadtest.py }
    finally { Remove-Item Env:LOADTEST_PASSWORD -ErrorAction SilentlyContinue }
    if ($LASTEXITCODE -ne 0) { throw "seed_loadtest.py en echec" }
    Psql $BASE "analyze;" | Out-Null

    Etape "Demarrage de la pile de charge"
    & $compose up -d
    $ok = $false
    foreach ($i in 1..30) {
        try { if ((Invoke-WebRequest "http://127.0.0.1:8081/health" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200) { $ok = $true; break } } catch {}
        Start-Sleep -Seconds 3
    }
    if (-not $ok) { throw "http://127.0.0.1:8081/health ne repond pas : .\loadtest\lt-compose.ps1 logs lt-backend" }

    $stats = Psql $BASE "select (select count(*) from users) || ' comptes, ' || (select count(*) from mg_articles) || ' articles, ' || (select count(*) from mg_stock_mouvements) || ' mouvements, ' || (select count(*) from immobilisations) || ' immobilisations';"
    Write-Host ""
    Write-Host "Environnement de charge pret : http://127.0.0.1:8081  ($stats)" -ForegroundColor Green
    Write-Host "Comptes : lt.mg.001..., lt.compta.001..., lt.employe.001... @loadtest.example.com"
    Write-Host "Mot de passe commun : loadtest/.env.loadtest (LOADTEST_PASSWORD)"
    Write-Host "Locust : .\loadtest\run-locust.ps1"
}
finally {
    Pop-Location
}
