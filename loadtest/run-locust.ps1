# Lance Locust contre l'environnement de charge ISOLE (http://127.0.0.1:8081).
# Fichier ASCII : Windows PowerShell 5.1 lit les .ps1 sans BOM en ANSI.
#
#   .\loadtest\run-locust.ps1                                  # interface web http://localhost:8089
#   .\loadtest\run-locust.ps1 -Utilisateurs 10 -Duree 5m       # palier sans interface + rapports
#   .\loadtest\run-locust.ps1 -Paliers 10,25,50,75,100 -Duree 5m
#   .\loadtest\run-locust.ps1 -Ecriture -Utilisateurs 40 -Duree 3m -Profils "mg:20,employe:20"
#
# Rapports dans loadtest/reports/<horodatage>-<N>u/ : stats CSV, rapport HTML, logs backend et nginx,
# etat PostgreSQL (connexions, verrous, transactions) avant/apres. Arret au premier palier qui
# depasse -SeuilEchecs (% de requetes en echec).

param(
    [int]$Utilisateurs = 0,
    # string[] : "powershell -File ... -Paliers 10,50,100" transmet une seule chaine "10,50,100".
    [string[]]$Paliers = @(),
    [string]$Duree = "5m",
    [double]$Rythme = 1,
    [double]$SeuilEchecs = 5,
    [string]$Profils = "mg:40,compta:30,employe:80",
    [switch]$Ecriture
)

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$HOTE = "http://127.0.0.1:8081"
$BASE = "bea_digital_loadtest"
$python = Join-Path $racine "backend\.venv\Scripts\python.exe"
$envLt = Join-Path $PSScriptRoot ".env.loadtest"

if (-not (Test-Path $python)) { throw "venv absent : backend\.venv (pip install -r loadtest/requirements.txt)" }
if (-not (Test-Path $envLt)) { throw "Environnement non prepare : .\loadtest\setup-env.ps1" }
try { Invoke-WebRequest "$HOTE/health" -UseBasicParsing -TimeoutSec 5 | Out-Null }
catch { throw "$HOTE ne repond pas : .\loadtest\setup-env.ps1" }

$env:LOADTEST_PASSWORD = (Select-String -Path $envLt -Pattern '^LOADTEST_PASSWORD=(.+)$').Matches[0].Groups[1].Value.Trim()
$env:LOADTEST_PROFILES = $Profils
if ($Ecriture) { $env:LOADTEST_WRITES = "1" } else { Remove-Item Env:LOADTEST_WRITES -ErrorAction SilentlyContinue }
Remove-Item Env:LOADTEST_EMAIL -ErrorAction SilentlyContinue
$integrite = Join-Path $PSScriptRoot "integrite.py"

function EtatPostgres($fichier) {
    $sql = @"
select now() as instant;
select state, wait_event_type, count(*) from pg_stat_activity where datname = '$BASE' group by 1, 2 order by 3 desc;
select numbackends, xact_commit, xact_rollback, deadlocks, conflicts, temp_files, blks_read, blks_hit,
       round(100.0 * blks_hit / nullif(blks_hit + blks_read, 0), 2) as cache_hit_pct
from pg_stat_database where datname = '$BASE';
select l.mode, l.granted, count(*) from pg_locks l join pg_database d on d.oid = l.database
where d.datname = '$BASE' group by 1, 2 order by 3 desc;
select setting as max_connections from pg_settings where name = 'max_connections';
"@
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $sql | docker exec -i bea-postgres psql -U admin -d $BASE -X | Out-File -FilePath $fichier -Encoding utf8
    $ErrorActionPreference = $old
}

function Palier([int]$n) {
    $dossier = Join-Path $PSScriptRoot ("reports\{0:yyyyMMdd-HHmmss}-{1}u" -f (Get-Date), $n)
    New-Item -ItemType Directory -Force -Path $dossier | Out-Null
    Write-Host "==> Palier $n utilisateurs, $Duree, rythme $Rythme/s -> $dossier" -ForegroundColor Cyan
    if ($Ecriture) {
        $env:LOADTEST_JOURNAL = Join-Path $dossier "journal.jsonl"
        & $python $integrite snapshot $dossier | Write-Host
        if ($LASTEXITCODE -ne 0) { throw "Snapshot d'integrite refuse." }
    } else {
        Remove-Item Env:LOADTEST_JOURNAL -ErrorAction SilentlyContinue
    }
    EtatPostgres (Join-Path $dossier "postgres-avant.txt")
    $debut = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $argsLocust = @(
        "-m", "locust", "-f", (Join-Path $PSScriptRoot "locustfile.py"), "--host", $HOTE, "--headless",
        "-u", $n, "-r", $Rythme, "-t", $Duree, "--stop-timeout", 30,
        "--csv", (Join-Path $dossier "locust"), "--csv-full-history",
        "--html", (Join-Path $dossier "rapport.html"), "--logfile", (Join-Path $dossier "locust.log"),
        "--only-summary"
    )
    if ($Ecriture) { $argsLocust += "--bea-writes" }
    & $python @argsLocust | Out-Host
    EtatPostgres (Join-Path $dossier "postgres-apres.txt")
    # docker logs ecrit sur stderr : cmd /c evite l'erreur NativeCommandError de PowerShell 5.1.
    foreach ($c in @(@("bea-lt-backend", "backend.log"), @("bea-lt-frontend", "nginx.log"), @("bea-lt-worker", "worker.log"))) {
        cmd /c "docker logs $($c[0]) --since $debut > `"$(Join-Path $dossier $c[1])`" 2>&1"
    }
    docker stats --no-stream --format "{{.Name}};{{.CPUPerc}};{{.MemUsage}}" bea-lt-backend bea-lt-worker bea-lt-frontend bea-lt-redis bea-postgres |
        Out-File -FilePath (Join-Path $dossier "docker-stats-fin.txt") -Encoding utf8

    $agg = Import-Csv (Join-Path $dossier "locust_stats.csv") | Where-Object { $_.Name -eq "Aggregated" }
    $req = [double]$agg."Request Count"; $ko = [double]$agg."Failure Count"
    $pct = if ($req) { [math]::Round(100 * $ko / $req, 2) } else { 100 }
    Write-Host ("    {0} requetes, {1} echecs ({2} %), mediane {3} ms, p95 {4} ms, {5} req/s" -f `
        $req, $ko, $pct, $agg."Median Response Time", $agg."95%", [math]::Round([double]$agg."Requests/s", 1))
    if ($Ecriture) {
        & $python $integrite verifier $dossier | Write-Host
        if ($LASTEXITCODE -ne 0) { $pct = [math]::Max($pct, 100) }
    }
    return $pct
}

Push-Location $racine
try {
    if ($Paliers.Count -eq 0 -and $Utilisateurs -eq 0) {
        Write-Host "Interface Locust : http://localhost:8089 (cible $HOTE)" -ForegroundColor Green
        & $python -m locust -f (Join-Path $PSScriptRoot "locustfile.py") --host $HOTE
        return
    }
    $liste = @($Paliers | ForEach-Object { $_ -split "[,; ]+" } | Where-Object { $_ } | ForEach-Object { [int]$_ })
    if ($liste.Count -eq 0) { $liste = @($Utilisateurs) }
    Write-Host ("Paliers : " + ($liste -join ", ")) -ForegroundColor Cyan
    foreach ($n in $liste) {
        $pct = Palier $n | Select-Object -Last 1
        if ($pct -gt $SeuilEchecs) {
            Write-Host "Arret : $pct % d'echecs au palier $n (seuil $SeuilEchecs %)." -ForegroundColor Yellow
            break
        }
    }
}
finally {
    Remove-Item Env:LOADTEST_PASSWORD, Env:LOADTEST_PROFILES, Env:LOADTEST_WRITES, Env:LOADTEST_JOURNAL -ErrorAction SilentlyContinue
    Pop-Location
}
