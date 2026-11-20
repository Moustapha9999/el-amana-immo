#Requires -Version 5.1
<#
.SYNOPSIS
  Neutralise une copie tampon bea_digital_prod_YYYYMMDD pour usage DEV.

.DESCRIPTION
  Voir docs/dev/prod-vers-dev/03-cdc-neutralize-dev-copy.md.
  Preserve integralement les donnees comptables. GED/uploads hors perimetre.
  Parametres admin / anonymisation obligatoires et explicites (pas de defaut metier).

.EXAMPLE
  $env:BEA_DEV_ADMIN_PASSWORD = '...'
  .\scripts\neutralize-dev-copy.ps1 -Database bea_digital_prod_20261119 `
    -DevAdminEmail 'dev.admin@localhost' -DevAdminRoleCodes 'administrateur' `
    -AnonymizePii None -ConfirmWorkerStopped -ConfirmPhrase 'OUI-NEUTRALISER-COPIE-DEV'
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Database,

    [Parameter(Mandatory = $true)]
    [string]$DevAdminEmail,

    [Parameter(Mandatory = $true)]
    [ValidateSet("None", "Minimal", "Strict")]
    [string]$AnonymizePii,

    [Parameter(Mandatory = $true)]
    [string[]]$DevAdminRoleCodes,

    [string]$DevAdminFullName = "Administrateur DEV",

    [switch]$DeactivateOtherUsers,

    [switch]$MakeSuperuser,

    [switch]$ConfirmWorkerStopped,

    [string]$ConfirmPhrase,

    [switch]$WhatIf,

    [string]$EnvFile = ".env.docker"
)

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
Set-Location (Split-Path -Parent $PSScriptRoot)

$ForbiddenDatabases = @("bea_digital", "bea_digital_test", "postgres", "template0", "template1")
$TargetPattern = '^bea_digital_prod_[0-9]{8}$'
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
    $path = Join-Path $ReportDir "neutralize-$stamp.md"
    $header = @(
        "# Rapport neutralize-dev-copy ($status)",
        "",
        "- Horodatage: $(Get-Date -Format o)",
        "- Hostname: $env:COMPUTERNAME",
        "- Database: $Database",
        "- DevAdminEmail: $DevAdminEmail",
        "- AnonymizePii: $AnonymizePii",
        "- WhatIf: $WhatIf",
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
function Table-Exists([string]$database, [string]$table) {
    $r = Invoke-Psql $database "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='$table';"
    return ($r -eq "1")
}

# --- Garde-fous ---
Write-Step "Controles de contexte"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker indisponible" }
if (-not (Test-Path -LiteralPath "docker-compose.yml")) { Fail "docker-compose.yml introuvable" }
if (-not (Test-Path -LiteralPath $EnvFile)) { Fail "$EnvFile introuvable" }
if ($EnvFile -match 'env\.production') { Fail "Env-file production refuse" }
$script:PgUser = Get-EnvValue $EnvFile "POSTGRES_USER" "admin"
if (-not $script:PgUser) { Fail "POSTGRES_USER vide" }
if ($ForbiddenDatabases -contains $Database) { Fail "Base interdite: $Database" }
if ($Database -notmatch $TargetPattern) { Fail "Base hors motif bea_digital_prod_YYYYMMDD: $Database" }
if ($DevAdminEmail -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$' -and $DevAdminEmail -notmatch '^[^@\s]+@localhost$') {
    Fail "DevAdminEmail invalide: $DevAdminEmail"
}
if (-not $DevAdminRoleCodes -or $DevAdminRoleCodes.Count -eq 0) {
    Fail "DevAdminRoleCodes obligatoire (explicite). Ex: -DevAdminRoleCodes administrateur"
}
if ((docker inspect -f "{{.State.Health.Status}}" $PG 2>$null) -ne "healthy") {
    Fail "Conteneur $PG non healthy"
}

$dbExists = Invoke-Psql "postgres" "SELECT 1 FROM pg_database WHERE datname = '$Database';"
if ($dbExists -ne "1") { Fail "Base introuvable: $Database" }

$workerStatus = docker inspect -f "{{.State.Status}}" bea-worker 2>$null
if ($workerStatus -eq "running" -and -not $ConfirmWorkerStopped -and -not $WhatIf) {
    Fail "Worker Celery encore running. Arreter le worker ou passer -ConfirmWorkerStopped apres verification SMTP vide."
}
Write-ReportLine "Worker status: $workerStatus ; ConfirmWorkerStopped=$ConfirmWorkerStopped"

$smtpHost = Get-EnvValue $EnvFile "SMTP_HOST" ""
if ($smtpHost -and $smtpHost.Trim() -ne "") {
    Write-Host "ATTENTION: SMTP_HOST est renseigne dans $EnvFile — risque d'emails si worker redemarre." -ForegroundColor Yellow
    $reportLines.Add("ATTENTION: SMTP_HOST non vide")
} else {
    Write-ReportLine "SMTP_HOST vide ou absent (OK pour DEV)"
}

# --- Snapshot comptable ---
Write-Step "Snapshot comptable pre-neutralisation"
$snapshotSql = @"
SELECT 'immos=' || (SELECT count(*) FROM immobilisations WHERE deleted_at IS NULL)
 || '|vb=' || (SELECT coalesce(sum(valeur_brute),0) FROM immobilisations WHERE deleted_at IS NULL)
 || '|orion142000=' || (SELECT coalesce((SELECT valeur_brute::text FROM soldes_compte_orion WHERE compte_immobilisation='142000' ORDER BY annee DESC LIMIT 1),'0'))
 || '|exercices=' || (SELECT count(*) FROM exercices_comptables)
 || '|alembic=' || (SELECT version_num FROM alembic_version LIMIT 1)
 || '|tables=' || (SELECT count(*) FROM pg_tables WHERE schemaname='public');
"@
$snapshotBefore = Invoke-Psql $Database $snapshotSql
Write-ReportLine "Snapshot AVANT: $snapshotBefore"

$adminPassword = $env:BEA_DEV_ADMIN_PASSWORD
if (-not $WhatIf) {
    if (-not $adminPassword -or $adminPassword.Length -lt 8) {
        Fail "Variable d'environnement BEA_DEV_ADMIN_PASSWORD absente ou trop courte (>= 8)"
    }
}

if (-not $WhatIf) {
    Write-Step "Confirmation operateur"
    if (-not $ConfirmPhrase) {
        $ConfirmPhrase = Read-Host "Taper exactement OUI-NEUTRALISER-COPIE-DEV"
    }
    if ($ConfirmPhrase -ne "OUI-NEUTRALISER-COPIE-DEV") { Fail "Confirmation refusee" }
} else {
    Write-ReportLine "WhatIf: confirmation ignoree"
}

if ($WhatIf) {
    Write-Step "WhatIf: plan d'actions (aucune ecriture)"
    Write-ReportLine "- Invalider hashed_password / TOTP de tous les users"
    Write-ReportLine "- DELETE auth_sessions, password_history, auth_login_attempts"
    Write-ReportLine "- Activer/creer admin DEV: $DevAdminEmail roles=$($DevAdminRoleCodes -join ',')"
    Write-ReportLine "- Suspendre destinations integrations ; neutraliser url_base / hotes"
    Write-ReportLine "- AnonymizePii=$AnonymizePii"
    if ($DeactivateOtherUsers) { Write-ReportLine "- Desactiver les autres users" }
    Write-ReportLine "SIMULATION OK — aucune ecriture"
    Save-Report
    Write-Host "SIMULATION OK" -ForegroundColor Green
    return
}

# --- Hashes ---
Write-Step "Generation des hashes (backend container)"
$randomHash = docker exec bea-backend python -c "import bcrypt,secrets; print(bcrypt.hashpw(secrets.token_hex(32).encode(), bcrypt.gensalt()).decode())"
if ($LASTEXITCODE -ne 0 -or $randomHash -notmatch '^\$2[aby]\$') { Fail "Generation hash aleatoire en echec" }
$randomHash = $randomHash.Trim()

$adminHash = docker exec -e "BDT_SECRET=$adminPassword" bea-backend python -c "import bcrypt,os; print(bcrypt.hashpw(os.environ['BDT_SECRET'].encode(), bcrypt.gensalt()).decode())"
if ($LASTEXITCODE -ne 0 -or $adminHash -notmatch '^\$2[aby]\$') { Fail "Hash mot de passe admin DEV en echec" }
$adminHash = $adminHash.Trim()
$adminPassword = $null
$env:BEA_DEV_ADMIN_PASSWORD = $null

# Escape for SQL literal (hashes are bcrypt, safe but still quote)
function Sql-Quote([string]$s) { return "'" + ($s -replace "'", "''") + "'" }
$emailSql = Sql-Quote $DevAdminEmail
$nameSql = Sql-Quote $DevAdminFullName
$hashAllSql = Sql-Quote $randomHash
$hashAdminSql = Sql-Quote $adminHash

Write-Step "A. Comptes / MFA / sessions"
$super = if ($MakeSuperuser) { "true" } else { "false" }
$sqlAccess = @"
BEGIN;
UPDATE users
   SET hashed_password = $hashAllSql,
       totp_secret = NULL,
       totp_enabled = false,
       updated_at = now();
DELETE FROM auth_sessions;
DELETE FROM password_history;
"@
if (Table-Exists $Database "auth_login_attempts") {
    $sqlAccess += "DELETE FROM auth_login_attempts;`n"
}
$sqlAccess += @"
INSERT INTO users (
  id, email, full_name, hashed_password, is_superuser, totp_enabled, is_active,
  must_change_password, created_at, updated_at
)
SELECT gen_random_uuid(), $emailSql, $nameSql, $hashAdminSql, $super, false, true, false, now(), now()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = $emailSql);

UPDATE users
   SET hashed_password = $hashAdminSql,
       totp_secret = NULL,
       totp_enabled = false,
       is_active = true,
       deleted_at = NULL,
       must_change_password = false,
       is_superuser = CASE WHEN $super THEN true ELSE is_superuser END,
       updated_at = now()
 WHERE email = $emailSql;
"@
if ($DeactivateOtherUsers) {
    $sqlAccess += @"
UPDATE users SET is_active = false, updated_at = now()
 WHERE email <> $emailSql AND deleted_at IS NULL;
"@
}
# Roles
foreach ($code in $DevAdminRoleCodes) {
    if ($code -notmatch '^[a-z0-9._-]+$') { Fail "Code role invalide: $code" }
    $codeSql = Sql-Quote $code
    $sqlAccess += @"
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
  FROM users u
  JOIN roles r ON r.code = $codeSql
 WHERE u.email = $emailSql
ON CONFLICT DO NOTHING;
"@
}
$sqlAccess += "COMMIT; SELECT 'access_ok';"
Invoke-Psql $Database $sqlAccess | Out-Null
Write-ReportLine "Acces neutralises; admin DEV configure"

Write-Step "B. Integrations externes"
$sqlInt = "BEGIN;`n"
if (Table-Exists $Database "integration_destinations") {
    $sqlInt += @"
UPDATE integration_destinations
   SET hotes = '[]'::jsonb,
       statut = CASE WHEN statut IN ('archivee') THEN statut ELSE 'suspendue' END,
       motif_statut = coalesce(motif_statut, '') || ' [neutralise DEV]',
       updated_at = now()
 WHERE statut <> 'archivee';
"@
}
if (Table-Exists $Database "integration_fournisseurs") {
    $sqlInt += @"
UPDATE integration_fournisseurs
   SET url_base = 'http://127.0.0.1:9',
       statut = CASE WHEN statut IN ('archive') THEN statut ELSE 'suspendu' END,
       motif_statut = coalesce(motif_statut, '') || ' [neutralise DEV]',
       updated_at = now()
 WHERE statut <> 'archive';
"@
}
if (Table-Exists $Database "integration_client_grants") {
    $sqlInt += @"
UPDATE integration_client_grants
   SET statut = CASE WHEN statut IN ('revoquee','refusee') THEN statut ELSE 'revoquee' END,
       motif = coalesce(motif, '') || ' [neutralise DEV]',
       updated_at = now()
 WHERE statut NOT IN ('revoquee','refusee');
"@
}
if (Table-Exists $Database "integration_fournisseur_operations") {
    # configuration JSON may hold auth material
    $sqlInt += @"
UPDATE integration_fournisseur_operations
   SET configuration = NULL,
       authentification = '[]'::jsonb,
       updated_at = now()
 WHERE configuration IS NOT NULL OR authentification <> '[]'::jsonb;
"@
}
$sqlInt += "COMMIT; SELECT 'integrations_ok';"
Invoke-Psql $Database $sqlInt | Out-Null
Write-ReportLine "Integrations neutralisees / suspendues"

# --- PII ---
Write-Step "D. Anonymisation PII ($AnonymizePii)"
if ($AnonymizePii -eq "None") {
    Write-ReportLine "Aucune anonymisation PII (niveau None)"
} else {
    $sqlPii = "BEGIN;`n"
    $sqlPii += @"
UPDATE users
   SET phone = NULL,
       email = CASE WHEN email = $emailSql THEN email
                    ELSE 'user_' || substr(replace(id::text, '-', ''), 1, 12) || '@anon.invalid' END,
       full_name = CASE WHEN email = $emailSql THEN full_name
                        ELSE 'Utilisateur anonymise' END,
       updated_at = now()
 WHERE email <> $emailSql OR phone IS NOT NULL;
"@
    # Fix: after email rename, admin still has original email. The CASE on email = admin works before rename for admin row.
    # Actually the UPDATE sets email for others; admin kept. Good.
    if ((Table-Exists $Database "reclamations") -and ($AnonymizePii -in @("Minimal", "Strict"))) {
        $sqlPii += @"
UPDATE reclamations
   SET client_telephone = NULL,
       client_email = CASE WHEN client_email IS NULL THEN NULL ELSE 'client_' || substr(replace(id::text,'-',''),1,12) || '@anon.invalid' END,
       client_adresse = CASE WHEN client_adresse IS NULL THEN NULL ELSE '[anonymise]' END,
       updated_at = now();
"@
    }
    if ($AnonymizePii -eq "Strict" -and (Table-Exists $Database "clientele_clients")) {
        $sqlPii += @"
UPDATE clientele_clients
   SET raison_sociale = CASE WHEN raison_sociale IS NULL THEN NULL ELSE 'CLIENT ANON ' || racine_client END,
       prenoms = NULL,
       date_naissance = NULL,
       nni = NULL,
       nif = NULL,
       rcs = NULL,
       identifiant_orion = NULL,
       updated_at = now();
"@
    }
    if ($AnonymizePii -eq "Strict" -and (Table-Exists $Database "reclamations")) {
        $sqlPii += @"
UPDATE reclamations
   SET client_nom = CASE WHEN client_nom IS NULL THEN NULL ELSE 'CLIENT ANON' END,
       updated_at = now();
"@
    }
    $sqlPii += "COMMIT; SELECT 'pii_ok';"
    Invoke-Psql $Database $sqlPii | Out-Null
    Write-ReportLine "Anonymisation $AnonymizePii appliquee"
}

# Clear random hash from memory vars
$randomHash = $null
$adminHash = $null

Write-Step "E. Controles post-neutralisation"
$sessions = Invoke-Psql $Database "SELECT count(*) FROM auth_sessions;"
if ($sessions -ne "0") { Fail "Sessions restantes: $sessions" }
$mfa = Invoke-Psql $Database "SELECT count(*) FROM users WHERE totp_enabled = true OR totp_secret IS NOT NULL;"
if ($mfa -ne "0") { Fail "MFA encore present: $mfa" }
$adminOk = Invoke-Psql $Database "SELECT count(*) FROM users WHERE email = $emailSql AND is_active = true;"
if ($adminOk -ne "1") { Fail "Compte admin DEV absent ou inactif" }

$snapshotAfter = Invoke-Psql $Database $snapshotSql
Write-ReportLine "Snapshot APRES: $snapshotAfter"
# Compare without relying on email changes affecting counts — snapshot is accounting only
if ($snapshotAfter -ne $snapshotBefore) {
    Fail "Derive comptable detectee. AVANT=$snapshotBefore APRES=$snapshotAfter"
}

Write-ReportLine "Rappel runtime: garder SMTP vide; ne pas brancher DATABASE_URL compose sur le tampon sans validation; GED/uploads hors scope."
Save-Report
Write-Host "NEUTRALISATION OK -> $Database" -ForegroundColor Green
