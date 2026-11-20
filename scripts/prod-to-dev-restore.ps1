#Requires -Version 5.1
<#
.SYNOPSIS
  Restaure un dump PROD complet dans une base tampon DEV bea_digital_prod_YYYYMMDD.

.DESCRIPTION
  Voir docs/dev/prod-vers-dev/02-cdc-prod-to-dev-restore.md.
  Ne touche jamais bea_digital ni bea_digital_test. GED/uploads hors perimetre.
  -WhatIf : controles uniquement, aucune creation de base.

.EXAMPLE
  .\scripts\prod-to-dev-restore.ps1 -DumpPath backups\x.dump -Sha256Path backups\x.dump.sha256 `
    -TargetDatabase bea_digital_prod_20261119 -ConfirmPhrase 'OUI-RESTAURER-DEV-TAMPON' -RequireDebianPostgres
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$DumpPath,

    [string]$Sha256Path,

    [string]$Sha256,

    [Parameter(Mandatory = $true)]
    [string]$TargetDatabase,

    [string]$ConfirmPhrase,

    [switch]$RequireDebianPostgres,

    [switch]$WhatIf,

    [int]$MinDumpBytes = 102400,

    [int]$MinFreeBytes = 0,

    [int]$MinPublicTables = 5,

    [string]$EnvFile = ".env.docker"
)

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
Set-Location (Split-Path -Parent $PSScriptRoot)

$ForbiddenDatabases = @(
    "bea_digital", "bea_digital_test", "postgres", "template0", "template1"
)
$TargetPattern = '^bea_digital_prod_[0-9]{8}$'
$RequiredTocMarkers = @(
    "alembic_version",
    "TABLE DATA public immobilisations",
    "TABLE DATA public users",
    "TABLE DATA public exercices_comptables"
)
$PG = "bea-postgres"
$ReportDir = Join-Path "backups" "rapports"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportLines = New-Object System.Collections.Generic.List[string]

function Write-Step([string]$msg) {
    Write-Host "==> $msg" -ForegroundColor Cyan
    $reportLines.Add("## $msg")
}

function Write-ReportLine([string]$msg) {
    Write-Host $msg
    $reportLines.Add($msg)
}

function Fail([string]$msg) {
    Write-Host "ERREUR: $msg" -ForegroundColor Red
    $reportLines.Add("ERREUR: $msg")
    Save-Report -failed
    throw $msg
}

function Save-Report([switch]$failed) {
    New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
    $status = if ($failed) { "FAILED" } else { "OK" }
    $path = Join-Path $ReportDir "prod-to-dev-$stamp.md"
    $header = @(
        "# Rapport prod-to-dev-restore ($status)",
        "",
        "- Horodatage: $(Get-Date -Format o)",
        "- Hostname: $env:COMPUTERNAME",
        "- Operateur: $env:USERNAME",
        "- WhatIf: $WhatIf",
        "- TargetDatabase: $TargetDatabase",
        "- DumpPath: $DumpPath",
        ""
    )
    ($header + $reportLines) | Set-Content -Encoding utf8 -LiteralPath $path
    Write-Host "Rapport: $path"
}

function Get-EnvValue([string]$path, [string]$key, [string]$default) {
    if (-not (Test-Path -LiteralPath $path)) { return $default }
    foreach ($line in Get-Content -LiteralPath $path -Encoding UTF8) {
        $trim = $line.Trim()
        if ($trim.StartsWith("#") -or $trim -eq "") { continue }
        if ($trim -match "^$key=(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $default
}

function Invoke-Psql([string]$database, [string]$sql) {
    $out = $sql | docker exec -i $PG psql -U $script:PgUser -d $database -X -q -v ON_ERROR_STOP=1 -At 2>&1
    if ($LASTEXITCODE -ne 0) { Fail "psql ($database) : $out" }
    return (($out | Out-String).Trim())
}

# --- Controles prealables ---
Write-Step "Controles de contexte DEV"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker indisponible" }
if (-not (Test-Path -LiteralPath "docker-compose.yml")) { Fail "docker-compose.yml introuvable (racine depot)" }
if (-not (Test-Path -LiteralPath $EnvFile)) { Fail "$EnvFile introuvable" }
if ($EnvFile -match 'env\.production') { Fail "Env-file production refuse: $EnvFile" }
$script:PgUser = Get-EnvValue $EnvFile "POSTGRES_USER" "admin"
if (-not $script:PgUser) { Fail "POSTGRES_USER vide" }
if ((docker inspect -f "{{.State.Health.Status}}" $PG 2>$null) -ne "healthy") {
    Fail "Conteneur $PG non healthy"
}

$composeImage = docker inspect -f "{{.Config.Image}}" $PG 2>$null
Write-ReportLine "Image Postgres: $composeImage"
$isAlpine = ($composeImage -match "alpine")
$isDebian = ($composeImage -eq "postgres:17" -or $composeImage -match "postgres:17$")
$pgVersion = Invoke-Psql "postgres" "SHOW server_version;"
Write-ReportLine "server_version: $pgVersion"
if ($pgVersion -notmatch '^17\.') { Fail "PostgreSQL majeure attendue 17, obtenu: $pgVersion" }
if ($isAlpine) {
    $msg = "Image Alpine detectee ($composeImage). Dump PROD attendu depuis Debian."
    if ($RequireDebianPostgres) { Fail $msg }
    Write-Host "ATTENTION: $msg" -ForegroundColor Yellow
    $reportLines.Add("ATTENTION: $msg")
} elseif (-not $isDebian) {
    Write-ReportLine "Image non reconnue comme postgres:17 Debian stricte: $composeImage"
}

# --- Cible ---
Write-Step "Validation de la base cible"
if ($ForbiddenDatabases -contains $TargetDatabase) {
    Fail "Base cible interdite: $TargetDatabase"
}
if ($TargetDatabase -notmatch $TargetPattern) {
    Fail "Cible hors motif bea_digital_prod_YYYYMMDD: $TargetDatabase"
}

$exists = Invoke-Psql "postgres" "SELECT 1 FROM pg_database WHERE datname = '$TargetDatabase';"
if ($exists -eq "1") {
    Fail "La base cible existe deja ($TargetDatabase). Aucun remplacement automatique."
}
$preserved = Invoke-Psql "postgres" "SELECT string_agg(datname, ',' ORDER BY 1) FROM pg_database WHERE datname IN ('bea_digital','bea_digital_test');"
if ($preserved -notmatch 'bea_digital' -or $preserved -notmatch 'bea_digital_test') {
    Fail "Bases DEV attendues absentes avant restore: $preserved"
}
Write-ReportLine "Bases preservees presentes: $preserved"

# --- Dump + SHA ---
Write-Step "Verification dump et SHA-256"
if (-not (Test-Path -LiteralPath $DumpPath)) {
    $alt = Join-Path "backups" $DumpPath
    if (Test-Path -LiteralPath $alt) { $DumpPath = (Resolve-Path $alt).Path }
}
if (-not (Test-Path -LiteralPath $DumpPath)) { Fail "Dump introuvable: $DumpPath" }
$DumpPath = (Resolve-Path -LiteralPath $DumpPath).Path
$dumpItem = Get-Item -LiteralPath $DumpPath
if ($dumpItem.Length -lt $MinDumpBytes) {
    Fail "Dump trop petit ($($dumpItem.Length) o < $MinDumpBytes o)"
}
Write-ReportLine "Dump taille: $($dumpItem.Length) octets"

$expectedSha = $null
if ($Sha256) {
    $expectedSha = $Sha256.Trim().ToUpperInvariant()
} elseif ($Sha256Path) {
    if (-not (Test-Path -LiteralPath $Sha256Path)) {
        $altSha = Join-Path "backups" $Sha256Path
        if (Test-Path -LiteralPath $altSha) { $Sha256Path = $altSha }
    }
    if (-not (Test-Path -LiteralPath $Sha256Path)) { Fail "Fichier SHA introuvable: $Sha256Path" }
    $raw = (Get-Content -LiteralPath $Sha256Path -Raw).Trim()
    if ($raw -match '([A-Fa-f0-9]{64})') { $expectedSha = $Matches[1].ToUpperInvariant() }
    else { Fail "SHA-256 illisible dans $Sha256Path" }
} else {
    Fail "Fournir -Sha256Path ou -Sha256"
}

$actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $DumpPath).Hash.ToUpperInvariant()
Write-ReportLine "SHA attendu: $expectedSha"
Write-ReportLine "SHA calcule: $actualSha"
if ($actualSha -ne $expectedSha) { Fail "SHA-256 non concordant" }

# Copier le dump sous backups/ pour le conteneur si besoin
$backupsAbs = (Resolve-Path "backups").Path
$dumpName = Split-Path -Leaf $DumpPath
if (-not $DumpPath.ToLowerInvariant().StartsWith($backupsAbs.ToLowerInvariant())) {
    $dest = Join-Path "backups" $dumpName
    if (-not $WhatIf) {
        Copy-Item -LiteralPath $DumpPath -Destination $dest -Force
    }
    $containerDump = "/backups/$dumpName"
    Write-ReportLine "Dump copie vers backups/ pour le conteneur: $dumpName"
} else {
    $rel = $DumpPath.Substring($backupsAbs.Length).TrimStart('\', '/')
    $containerDump = "/backups/" + ($rel -replace '\\', '/')
}

# --- TOC ---
Write-Step "TOC pg_restore --list"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
$tocHost = Join-Path $ReportDir "toc-$stamp-$TargetDatabase.txt"
if ($WhatIf) {
    # Lecture TOC possible meme en simulation (lecture seule)
}
$tocOut = docker exec $PG pg_restore --list $containerDump 2>&1
if ($LASTEXITCODE -ne 0) { Fail "pg_restore --list en echec: $tocOut" }
$tocText = ($tocOut | Out-String)
$tocText | Set-Content -Encoding utf8 -LiteralPath $tocHost
Write-ReportLine "TOC enregistre: $tocHost"
foreach ($marker in $RequiredTocMarkers) {
    if ($tocText -notmatch [regex]::Escape($marker)) {
        Fail "TOC incomplet (dump non exhaustif?) — marqueur absent: $marker"
    }
}
$tableDataCount = ([regex]::Matches($tocText, "TABLE DATA public ")).Count
Write-ReportLine "Entrees TABLE DATA public: $tableDataCount"
if ($tableDataCount -lt 20) {
    Fail "TOC trop pauvre ($tableDataCount TABLE DATA) — refus d'un dump partiel"
}

# --- Disque ---
Write-Step "Espace disque"
$free = (Get-PSDrive -Name C).Free
$need = [Math]::Max(3L * [int64]$dumpItem.Length, [int64]$MinFreeBytes)
Write-ReportLine "Libre: $free octets ; requis: $need octets"
if ($free -lt $need) { Fail "Espace disque insuffisant" }

# --- Confirmation ---
if (-not $WhatIf) {
    Write-Step "Confirmation operateur"
    if (-not $ConfirmPhrase) {
        $ConfirmPhrase = Read-Host "Taper exactement OUI-RESTAURER-DEV-TAMPON pour continuer"
    }
    if ($ConfirmPhrase -ne "OUI-RESTAURER-DEV-TAMPON") {
        Fail "Confirmation refusee"
    }
} else {
    Write-ReportLine "WhatIf: confirmation ignoree"
}

# --- Backup local prealable ---
if ($WhatIf) {
    Write-Step "WhatIf: sauvegarde locale bea_digital ignoree"
} else {
    Write-Step "Sauvegarde locale prealable de bea_digital"
    $preName = "local-pre-prod-import-$stamp.dump"
    docker exec $PG pg_dump -U $script:PgUser -d bea_digital --format=custom --no-owner --no-acl -f "/backups/$preName"
    if ($LASTEXITCODE -ne 0) { Fail "pg_dump bea_digital prealable en echec" }
    $preHost = Join-Path "backups" $preName
    if (-not (Test-Path $preHost) -or (Get-Item $preHost).Length -lt 1024) {
        Fail "Backup local prealable manquant ou vide"
    }
    Write-ReportLine "Backup local: $preHost ($((Get-Item $preHost).Length) o)"
}

if ($WhatIf) {
    Write-Step "WhatIf: arret avant CREATE DATABASE / pg_restore"
    Write-ReportLine "SIMULATION OK — aucune base creee"
    Save-Report
    Write-Host "SIMULATION OK" -ForegroundColor Green
    return
}

# --- Create + restore ---
Write-Step "CREATE DATABASE $TargetDatabase"
$loc = Invoke-Psql "postgres" "SELECT datcollate || '|' || datctype FROM pg_database WHERE datname = 'bea_digital';"
$collate, $ctype = $loc -split "\|"
$sqlCreate = @"
CREATE DATABASE $TargetDatabase
  OWNER $script:PgUser
  TEMPLATE template0
  ENCODING 'UTF8'
  LC_COLLATE '$collate'
  LC_CTYPE '$ctype';
"@
Invoke-Psql "postgres" $sqlCreate | Out-Null

Write-Step "pg_restore complet vers $TargetDatabase"
$restoreOut = docker exec $PG pg_restore -U $script:PgUser -d $TargetDatabase --no-owner --no-acl --exit-on-error $containerDump 2>&1
$restoreRc = $LASTEXITCODE
$restoreOut | ForEach-Object { $reportLines.Add("restore: $_") }
if ($restoreRc -ne 0) {
    Fail "pg_restore en echec (code $restoreRc). Base $TargetDatabase laisse en place pour analyse — pas de drop automatique."
}

Write-Step "Post-restore"
$tables = Invoke-Psql $TargetDatabase "SELECT count(*) FROM pg_tables WHERE schemaname='public';"
Write-ReportLine "Tables public: $tables"
if ([int]$tables -lt $MinPublicTables) { Fail "Trop peu de tables apres restore: $tables" }

$alembic = Invoke-Psql $TargetDatabase "SELECT version_num FROM alembic_version LIMIT 1;"
Write-ReportLine "alembic_version: $alembic"

$counts = Invoke-Psql $TargetDatabase @"
SELECT 'users=' || (SELECT count(*) FROM users)
 || ';immos=' || (SELECT count(*) FROM immobilisations WHERE deleted_at IS NULL)
 || ';vb=' || (SELECT coalesce(sum(valeur_brute),0) FROM immobilisations WHERE deleted_at IS NULL)
 || ';orion142000=' || (SELECT coalesce((SELECT valeur_brute::text FROM soldes_compte_orion WHERE compte_immobilisation='142000' ORDER BY annee DESC LIMIT 1),'0'))
 || ';exercices=' || (SELECT count(*) FROM exercices_comptables);
"@
Write-ReportLine "Counts: $counts"

Invoke-Psql $TargetDatabase "GRANT CONNECT, TEMPORARY ON DATABASE $TargetDatabase TO bea_app;" | Out-Null
# GRANT ON DATABASE must run connected to postgres sometimes — also:
Invoke-Psql "postgres" "GRANT CONNECT, TEMPORARY ON DATABASE $TargetDatabase TO bea_app;" | Out-Null

$preservedAfter = Invoke-Psql "postgres" "SELECT string_agg(datname, ',' ORDER BY 1) FROM pg_database WHERE datname IN ('bea_digital','bea_digital_test');"
Write-ReportLine "Bases preservees apres: $preservedAfter"
if ($preservedAfter -ne $preserved) {
    Fail "Les bases DEV ont change pendant le restore"
}

Write-ReportLine "GED/uploads: non restaures (hors perimetre)"
Write-ReportLine "DATABASE_URL compose: inchange (toujours bea_digital)"
Write-ReportLine "Prochaine etape: .\scripts\neutralize-dev-copy.ps1 -Database $TargetDatabase ..."

Save-Report
Write-Host "RESTORE OK -> $TargetDatabase" -ForegroundColor Green
