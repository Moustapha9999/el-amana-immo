# Surveillance des conteneurs BEA DIGITAL pendant un test de charge Locust.
# Affiche CPU / memoire en continu et enregistre un CSV horodate dans
# loadtest/reports/ (a rapprocher des statistiques Locust). Ctrl+C pour arreter.
# Fichier volontairement en ASCII : Windows PowerShell 5.1 lit les .ps1 sans BOM en ANSI.
#
#   .\loadtest\monitor.ps1               # toutes les 5 s
#   .\loadtest\monitor.ps1 -Intervalle 2

param(
    [int]$Intervalle = 5
)

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$rapports = Join-Path $PSScriptRoot "reports"
New-Item -ItemType Directory -Force -Path $rapports | Out-Null
$fichier = Join-Path $rapports ("docker-stats-{0:yyyyMMdd-HHmmss}.csv" -f (Get-Date))

Push-Location $racine
try {
    $conteneurs = docker compose ps --format "{{.Name}}"
    if (-not $conteneurs) { throw "Aucun conteneur BEA DIGITAL demarre (docker compose ps est vide)." }

    "horodatage;conteneur;cpu_pct;memoire;memoire_pct;reseau_io;disque_io" | Out-File -FilePath $fichier -Encoding utf8
    Write-Host "Enregistrement dans $fichier (Ctrl+C pour arreter)" -ForegroundColor Cyan

    while ($true) {
        $t = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $lignes = docker stats --no-stream --format "{{.Name}};{{.CPUPerc}};{{.MemUsage}};{{.MemPerc}};{{.NetIO}};{{.BlockIO}}" $conteneurs
        $lignes | ForEach-Object { "$t;$_" } | Out-File -FilePath $fichier -Append -Encoding utf8

        try { Clear-Host } catch { Write-Host "" }
        Write-Host "BEA DIGITAL - $t - toutes les $Intervalle s - $fichier" -ForegroundColor Cyan
        $lignes | ForEach-Object {
            $c = $_ -split ";"
            [pscustomobject]@{ Conteneur = $c[0]; CPU = $c[1]; Memoire = $c[2]; "Mem %" = $c[3]; Reseau = $c[4]; Disque = $c[5] }
        } | Format-Table -AutoSize

        Start-Sleep -Seconds $Intervalle
    }
}
finally {
    Pop-Location
}
