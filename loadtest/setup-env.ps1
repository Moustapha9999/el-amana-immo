# Prepare l'environnement ISOLE de test de charge BEA DIGITAL.
# Fichier ASCII : Windows PowerShell 5.1 lit les .ps1 sans BOM en ANSI.
#
#   .\loadtest\setup-env.ps1            # cree la base si absente, puis demarre la pile
#   .\loadtest\setup-env.ps1 -Recreer   # supprime et regenere UNIQUEMENT bea_digital_loadtest
#
# Base bea_digital_loadtest sur le serveur PostgreSQL unique (bea-postgres) :
#   1. schema de bea_digital (structure seule, aucune donnee) ;
#   2. referentiels sans personnes : permissions, roles, espaces, modules, organigramme, agences,
#      categories, plan comptable, parametres (liens vers des utilisateurs remis a NULL) ;
#   3. droits du role applicatif bea_app (database/roles/bea_app.sql) ;
#   4. donnees synthetiques (loadtest/seed_loadtest.py) : comptes @loadtest.bea.local, stock,
#      immobilisations, notifications.
# Aucune ecriture dans bea_digital (lecture par pg_dump seulement). Pile : http://127.0.0.1:8081

param([switch]$Recreer)

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$BASE = "bea_digital_loadtest"
$SOURCE = "bea_digital"
$PG = "bea-postgres"
$envLt = Join-Path $PSScriptRoot ".env.loadtest"
$compose = Join-Path $PSScriptRoot "lt-compose.ps1"

$REFERENTIELS = @(
    "alembic_version", "permissions", "roles", "role_permissions",
    "plateforme_espaces", "plateforme_domaines", "plateforme_modules",
    "directions", "departements", "agences", "org_postes",
    "categories_immobilisation", "plan_comptable", "journaux", "exercices_comptables",
    "parametrage_amortissement", "parametrage_ecritures",
    "mg_article_familles", "mg_stock_motifs_sortie", "mg_stock_parametres", "mg_request_categories",
    "mg_contrat_types", "mg_note_frais_categories",
    "reclamation_referentiels", "reclamation_unites", "reclamation_parametres", "formation_referentiels"
)

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

    $existe = (Psql "postgres" "select 1 from pg_database where datname = '$BASE';") -eq "1"
    if ($existe -and $Recreer) {
        Etape "Suppression de $BASE (pile de charge arretee)"
        & $compose down --remove-orphans
        Psql "postgres" "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$BASE';" | Out-Null
        Psql "postgres" "drop database $BASE;" | Out-Null
        $existe = $false
    }

    if (-not $existe) {
        Etape "Creation de $BASE (meme encodage et collation que $SOURCE)"
        $loc = Psql "postgres" "select datcollate || '|' || datctype from pg_database where datname = '$SOURCE';"
        $collate, $ctype = $loc -split "\|"
        Psql "postgres" "create database $BASE owner admin template template0 encoding 'UTF8' lc_collate '$collate' lc_ctype '$ctype';" | Out-Null

        Etape "Schema de $SOURCE (structure seule)"
        docker exec $PG sh -c "pg_dump -U admin -d $SOURCE --schema-only --no-comments | psql -U admin -d $BASE -X -q -v ON_ERROR_STOP=1 > /dev/null"
        if ($LASTEXITCODE -ne 0) { throw "copie du schema en echec" }

        Etape "Referentiels sans donnees personnelles ($($REFERENTIELS.Count) tables)"
        $tables = ($REFERENTIELS | ForEach-Object { "-t public.$_" }) -join " "
        # Avertissements « circular foreign-key » attendus : --disable-triggers les couvre.
        docker exec $PG sh -c "set -o pipefail; pg_dump -U admin -d $SOURCE --data-only --disable-triggers $tables 2>/tmp/lt-dump.err | psql -U admin -d $BASE -X -q -v ON_ERROR_STOP=1 > /dev/null || { grep -v -e warning -e detail -e hint /tmp/lt-dump.err; exit 1; }"
        if ($LASTEXITCODE -ne 0) { throw "copie des referentiels en echec" }

        Etape "Liens vers des utilisateurs remis a NULL dans les referentiels"
        $liste = ($REFERENTIELS | ForEach-Object { "'$_'" }) -join ","
        Psql $BASE @"
do `$`$
declare r record;
begin
  for r in
    select c.conrelid::regclass as tbl, a.attname as col
    from pg_constraint c
    join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey)
    where c.contype = 'f' and c.confrelid = 'public.users'::regclass
      and c.conrelid::regclass::text = any(array[$liste])
  loop
    execute format('update %s set %I = null where %I is not null', r.tbl, r.col, r.col);
  end loop;
end `$`$;
update reclamation_unites set email = null;
-- exercices_comptables est copie sans archive_dossiers : la FK would-be casse pg_restore.
update exercices_comptables e
   set archive_dossier_id = null
 where archive_dossier_id is not null
   and not exists (select 1 from archive_dossiers a where a.id = e.archive_dossier_id);
"@ | Out-Null

        Etape "Droits du role applicatif bea_app"
        # Les droits objet (tables, sequences, audit en ajout seul, privileges par defaut) viennent du
        # schema copie ; seul le droit de connexion est propre a la base. Le role et son mot de passe
        # ne sont pas modifies.
        Psql $BASE "grant connect, temporary on database $BASE to bea_app;" | Out-Null
        $controle = Psql $BASE "select has_table_privilege('bea_app','public.users','INSERT') and not has_table_privilege('bea_app','public.audit_logs','UPDATE');"
        if ($controle -ne "t") { throw "droits bea_app incomplets sur $BASE (appliquer database/roles/bea_app.sql)" }

        Etape "Donnees synthetiques (quelques minutes)"
        & $compose up -d lt-redis
        $env:LOADTEST_PASSWORD = $mdpTest
        try { & $compose run --rm -e LOADTEST_PASSWORD lt-backend python /loadtest/seed_loadtest.py }
        finally { Remove-Item Env:LOADTEST_PASSWORD -ErrorAction SilentlyContinue }
        Psql $BASE "analyze;" | Out-Null
    }

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
    Write-Host "Comptes : lt.mg.001..., lt.compta.001..., lt.employe.001... @loadtest.bea.local"
    Write-Host "Mot de passe commun : loadtest/.env.loadtest (LOADTEST_PASSWORD)"
    Write-Host "Locust : .\loadtest\run-locust.ps1"
}
finally {
    Pop-Location
}
