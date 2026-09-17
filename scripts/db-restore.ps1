#Requires -Version 5.1
<#
.SYNOPSIS
  Restaure un dump PostgreSQL dans le Postgres unique de BEA DIGITAL.

  Refuse si le schéma public contient déjà des tables (pas d'écrasement).
  Les dumps ne sont pas versionnés — fichier local uniquement.

.PARAMETER DumpFile
  Chemin du dump (custom pg_dump) ou nom de fichier dans backups/.

.PARAMETER RestoreUploads
  Dossier source à recopier vers storage/uploads (GED).
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$DumpFile,
    [string]$RestoreUploads
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Get-DotEnvValue {
    param([string]$Path, [string]$Key, [string]$Default)
    if (-not (Test-Path -LiteralPath $Path)) { return $Default }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^\s*#" -or $line -notmatch "=") { continue }
        $n = $line.IndexOf("=")
        if ($n -lt 1) { continue }
        $k = $line.Substring(0, $n).Trim()
        if ($k -eq $Key) {
            return $line.Substring($n + 1).Trim().Trim("'").Trim('"')
        }
    }
    return $Default
}

$envFile = ".env.docker"
if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env.docker introuvable. Copiez .env.docker.example vers .env.docker."
}

$dbUser = Get-DotEnvValue $envFile "POSTGRES_USER" "immo_user"
$dbName = Get-DotEnvValue $envFile "POSTGRES_DB" "immobilisations"

$dumpPath = $DumpFile
if (-not (Test-Path -LiteralPath $dumpPath)) {
    $alt = Join-Path "backups" $DumpFile
    if (Test-Path -LiteralPath $alt) { $dumpPath = $alt }
}
if (-not (Test-Path -LiteralPath $dumpPath)) {
    throw "Dump introuvable : $DumpFile"
}

$dumpName = Split-Path -Leaf $dumpPath
$backupsAbs = (Resolve-Path "backups").Path
$dumpAbs = (Resolve-Path $dumpPath).Path
if ($dumpAbs.ToLowerInvariant().StartsWith($backupsAbs.ToLowerInvariant()) -eq $false) {
    Copy-Item -LiteralPath $dumpAbs -Destination (Join-Path "backups" $dumpName) -Force
}

Write-Host "BEA DIGITAL — restore non destructif de $dumpName"
Write-Host "  (refuse si public contient déjà des tables)"
Write-Host ""

$tableCheck = docker compose --env-file $envFile exec -T postgres `
    psql -U $dbUser -d $dbName -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
if ($LASTEXITCODE -ne 0) {
    throw "Impossible d'interroger PostgreSQL. Le service postgres est-il healthy ?"
}
$nTables = 0
if ($null -ne $tableCheck -and $tableCheck.ToString().Trim() -ne "") {
    $nTables = [int]$tableCheck.ToString().Trim()
}
if ($nTables -gt 0) {
    throw "Refus : le schéma public contient déjà $nTables table(s). Pas d'écrasement. Utilisez une instance vide (sans down -v sur un volume métier) ou un volume neuf."
}

Write-Host "public est vide — pg_restore..."
docker compose --env-file $envFile exec -T postgres `
    pg_restore -U $dbUser -d $dbName --no-owner --no-acl "/backups/$dumpName"
if ($LASTEXITCODE -ne 0) {
    Write-Host "pg_restore a renvoyé le code $LASTEXITCODE — contrôle des tables..."
}

$after = docker compose --env-file $envFile exec -T postgres `
    psql -U $dbUser -d $dbName -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
if ([int]$after.ToString().Trim() -lt 5) {
    throw "Restauration incomplète : seulement $($after.ToString().Trim()) table(s) dans public."
}
Write-Host "Tables public : $($after.ToString().Trim())"
Write-Host ""
Write-Host "Contrôles à rapprocher de la Comptabilité (nb immos, VB, cumul amort., VNC) :"

$queries = @(
    "SELECT count(*) AS nb_immobilisations FROM immobilisations;",
    "SELECT coalesce(sum(valeur_brute), 0) AS valeur_brute_totale FROM immobilisations;",
    "SELECT coalesce(sum(montant), 0) AS cumul_dotations FROM amortissements WHERE NOT annule AND NOT simule;",
    "SELECT count(*) AS nb_users FROM users;",
    "SELECT count(*) AS nb_pieces_jointes FROM pieces_jointes;"
)
foreach ($q in $queries) {
    docker compose --env-file $envFile exec -T postgres psql -U $dbUser -d $dbName -c $q
}

Write-Host ""
Write-Host "VNC métier = valeur brute − cumul (moteur amortissement) : jamais négative ; VNC = 0 → pas de dotation."
Write-Host "Rapprocher ces totaux du rapport Comptabilité. Recopier aussi storage/uploads (GED)."

if ($RestoreUploads) {
    if (-not (Test-Path -LiteralPath $RestoreUploads)) {
        throw "Dossier documents introuvable : $RestoreUploads"
    }
    Write-Host "Restauration documents -> storage/uploads"
    New-Item -ItemType Directory -Force -Path "storage/uploads" | Out-Null
    Copy-Item -Path (Join-Path $RestoreUploads "*") -Destination "storage/uploads" -Recurse -Force
} else {
    Write-Host "Pas de -RestoreUploads : vérifier manuellement que storage/uploads correspond au dump."
}

Write-Host ""
Write-Host "Restore terminé. SKIP_MIGRATIONS reste à 1 tant que vous n'appliquez pas de nouvelles révisions incrémentales."
Write-Host "Ne jamais : docker compose down -v"
