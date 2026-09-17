#Requires -Version 5.1
<#
.SYNOPSIS
  Opérations BEA DIGITAL sur Supabase (défaut) ou le Postgres Docker local.

.PARAMETER Action
  backup | migrate | sql | verify | status | droits

.PARAMETER Target
  supabase (.env) | docker (.env.docker → localhost:5432)

.PARAMETER EnvFile
  Fichier d'environnement (surcharge Target).

Ne jamais lancer docker compose down -v.
Ne pas pointer Alembic sur une base vide.
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("backup", "migrate", "sql", "verify", "status", "droits")]
    [string]$Action = "status",

    [ValidateSet("supabase", "docker")]
    [string]$Target = "supabase",

    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Get-EnvValue([string]$path, [string]$key) {
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    foreach ($line in Get-Content -LiteralPath $path) {
        $trim = $line.Trim()
        if ($trim.StartsWith("#") -or $trim -eq "") { continue }
        if ($trim -match "^$key=(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

function ConvertTo-PsqlUrl([string]$url, [bool]$requireSsl) {
    $psql = $url -replace "^postgresql\+asyncpg://", "postgresql://"
    if ($requireSsl -and $psql -notmatch "sslmode=") {
        if ($psql.Contains("?")) { $psql += "&sslmode=require" } else { $psql += "?sslmode=require" }
    }
    return $psql
}

if (-not $EnvFile) {
    if ($Target -eq "docker") { $EnvFile = ".env.docker" } else { $EnvFile = ".env" }
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Fichier $EnvFile introuvable."
}

$url = Get-EnvValue $EnvFile "DATABASE_URL"
if (-not $url) { throw "DATABASE_URL manquant dans $EnvFile" }

$isDocker = $Target -eq "docker"
if ($isDocker) {
    $pgUser = Get-EnvValue $EnvFile "POSTGRES_USER"
    $pgPass = Get-EnvValue $EnvFile "POSTGRES_PASSWORD"
    $pgDb = Get-EnvValue $EnvFile "POSTGRES_DB"
    if (-not $pgUser) { $pgUser = "immo_user" }
    if (-not $pgDb) { $pgDb = "bea_digital" }
    if (-not $pgPass) { throw "POSTGRES_PASSWORD manquant dans $EnvFile" }
    $url = "postgresql+asyncpg://${pgUser}:${pgPass}@localhost:5432/${pgDb}"
}

$psqlUrl = ConvertTo-PsqlUrl $url (-not $isDocker)
$backend = Join-Path (Get-Location) "backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "Python introuvable (ni backend\\.venv ni python PATH)." }
    $python = $cmd.Source
}
$sqlDir = Join-Path (Get-Location) "scripts\supabase"

function Invoke-BackendPython([string[]]$PyArgs) {
    $prevUrl = $env:DATABASE_URL
    $prevSsl = $env:DATABASE_SSL
    $prevPath = $env:PYTHONPATH
    $env:DATABASE_URL = $url
    if ($isDocker) { $env:DATABASE_SSL = "false" } else { $env:DATABASE_SSL = "true" }
    $env:PYTHONPATH = "."
    $env:APP_DEBUG = "false"
    Push-Location $backend
    try {
        & $python @PyArgs
        if ($LASTEXITCODE -ne 0) { throw "python exit $LASTEXITCODE" }
    }
    finally {
        Pop-Location
        if ($null -eq $prevUrl) { Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue } else { $env:DATABASE_URL = $prevUrl }
        if ($null -eq $prevSsl) { Remove-Item Env:DATABASE_SSL -ErrorAction SilentlyContinue } else { $env:DATABASE_SSL = $prevSsl }
        if ($null -eq $prevPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $prevPath }
    }
}

function Invoke-PsqlFile([string]$rel) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker est requis pour exécuter les fichiers SQL (postgres:17-alpine + psql)."
    }
    $fileName = Split-Path -Leaf $rel
    $full = Join-Path $sqlDir $fileName
    if (-not (Test-Path -LiteralPath $full)) { throw "SQL manquant : $full" }
    Write-Host "SQL $fileName ($Target)..."
    if ($isDocker) {
        Get-Content -LiteralPath $full -Raw -Encoding UTF8 |
            docker exec -i -e PGCLIENTENCODING=UTF8 bea-postgres `
                psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1
    } else {
        $sqlAbs = (Resolve-Path $sqlDir).Path
        docker run --rm `
            -e "DATABASE_URL=$psqlUrl" `
            -v "${sqlAbs}:/sql:ro" `
            postgres:17-alpine `
            sh -c "psql --dbname=`"`$DATABASE_URL`" --set ON_ERROR_STOP=1 --file=/sql/$fileName"
    }
    if ($LASTEXITCODE -ne 0) { throw "psql a échoué sur $fileName" }
}

switch ($Action) {
    "backup" {
        if ($isDocker) {
            & (Join-Path "scripts" "backup-local.ps1")
        } else {
            & (Join-Path "scripts" "backup-from-supabase.ps1") -EnvFile $EnvFile
        }
    }
    "migrate" {
        Write-Host "alembic upgrade head ($Target)..."
        Invoke-BackendPython @("-m", "alembic", "upgrade", "head")
        Invoke-BackendPython @("scripts\bea_digital_ops.py", "verify")
    }
    "sql" {
        Invoke-PsqlFile "01_upgrade.sql"
        Invoke-PsqlFile "02_catalogue.sql"
        Invoke-PsqlFile "03_comments.sql"
        if ($Action -eq "sql") {
            Invoke-PsqlFile "06_stamp.sql"
        }
        Invoke-BackendPython @("scripts\bea_digital_ops.py", "verify")
    }
    "droits" {
        Invoke-PsqlFile "05_droits_immo.sql"
    }
    "verify" {
        Invoke-BackendPython @("scripts\bea_digital_ops.py", "verify")
    }
    "status" {
        Invoke-BackendPython @("scripts\bea_digital_ops.py", "status")
    }
}
