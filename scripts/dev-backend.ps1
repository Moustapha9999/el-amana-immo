$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..\backend
$env:PYTHONPATH = "."
if (-not (Test-Path .\.venv\Scripts\python.exe)) {
  python -m venv .venv
  .\.venv\Scripts\pip install -r requirements.txt
}
Write-Host "Test connexion Supabase/Postgres..."
.\.venv\Scripts\python scripts\test_db_connection.py
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "Astuce: si getaddrinfo failed, testez le pooler IPv4:" -ForegroundColor Yellow
  Write-Host "  python scripts/find_pooler_region.py" -ForegroundColor Yellow
  exit $LASTEXITCODE
}
Write-Host "Seed (tables + admin)..."
.\.venv\Scripts\python scripts\seed_data.py
Write-Host "Demarrage API..."
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
