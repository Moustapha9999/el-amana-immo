<#
.SYNOPSIS
  Prépare une version livrable de BEA DIGITAL (machine de développement).

.DESCRIPTION
  1. Vérifie que le code est commité et que la version n'existe pas déjà.
  2. Contrôles : import de l'API, tests backend (optionnel, base de test locale).
  3. Construit les images backend et frontend avec le même numéro de version.
  4. Produit dist\releases\<version>\ :
       images.tar (+ .sha256)   backend, frontend, postgres:17, redis:7-alpine
       deploiement.tar.gz       compose, scripts, modèles .env, nginx, docs (fins de ligne LF)
       manifest.json            version, commit, date, révision de base, images
       LISEZMOI.txt             commandes à lancer sur le serveur
  5. Crée le tag Git annoté (sauf -SansTag) et le pousse (si -PousserTag).

.EXAMPLE
  .\scripts\release.ps1 -Version v1.0.0 -Tests -PousserTag
#>
param(
  [Parameter(Mandatory = $true)][string]$Version,
  [switch]$Tests,
  [switch]$SansTag,
  [switch]$PousserTag,
  [switch]$SansArchive
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

function Etape($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Echec($m) { Write-Host "ERREUR: $m" -ForegroundColor Red; exit 1 }

if ($Version -notmatch '^v\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$') { Echec "version attendue au format vX.Y.Z (ex. v1.0.0)" }

Etape "Contrôles Git"
git diff --quiet HEAD -- backend frontend deployment docs database docker-compose.yml
if ($LASTEXITCODE -ne 0) { Echec "modifications non commitées dans le code : commiter avant de livrer" }
if (-not $SansTag -and (git tag -l $Version)) { Echec "le tag $Version existe déjà" }
$sha = (git rev-parse --short HEAD).Trim()
$branche = (git branch --show-current).Trim()
Write-Host "Commit $sha (branche $branche)"

Etape "Contrôle de l'API (import de l'application)"
& backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'backend'); from app.main import app; print('API OK :', len(app.routes), 'routes')"
if ($LASTEXITCODE -ne 0) { Echec "l'application backend ne démarre pas" }
$head = (& backend\.venv\Scripts\python.exe -c "import sys,os; os.chdir('backend'); from alembic.config import Config; from alembic.script import ScriptDirectory; print(','.join(ScriptDirectory.from_config(Config('alembic.ini')).get_heads()))").Trim()
if ($head -match ',') { Echec "plusieurs têtes de migration ($head) : fusionner avant de livrer" }
Write-Host "Révision de base attendue : $head"

if ($Tests) {
  Etape "Tests backend (base de test locale bea_digital_clientele_test)"
  $u = docker exec bea-backend printenv DATABASE_URL
  $env:DATABASE_URL = ($u -replace '@postgres:5432/[^/?]+', '@localhost:5432/bea_digital_clientele_test')
  Push-Location backend
  & .\.venv\Scripts\python.exe -m pytest tests -q -p no:warnings
  $rc = $LASTEXITCODE
  Pop-Location
  Remove-Item Env:DATABASE_URL
  if ($rc -ne 0) {
    Write-Host "Des tests échouent : vérifier qu'il s'agit uniquement d'échecs connus avant de livrer." -ForegroundColor Yellow
    $r = Read-Host "Continuer quand même ? (oui/non)"
    if ($r -ne 'oui') { Echec "livraison interrompue" }
  }
}

$imgBe = "bea-digital/backend:$Version"
$imgFe = "bea-digital/frontend:$Version"

Etape "Construction des images $Version"
docker build --pull --build-arg "APP_VERSION=$Version" --build-arg "GIT_SHA=$sha" -t $imgBe backend
if ($LASTEXITCODE -ne 0) { Echec "construction backend" }
docker build --pull -t $imgFe frontend
if ($LASTEXITCODE -ne 0) { Echec "construction frontend (build Angular production)" }

$v = docker run --rm --entrypoint python $imgBe -c "import os; print(os.environ.get('APP_VERSION'))"
if ($v.Trim() -ne $Version) { Echec "l'image backend annonce '$v' au lieu de $Version" }

$out = "dist\releases\$Version"
New-Item -ItemType Directory -Force $out | Out-Null

if (-not $SansArchive) {
  Etape "Images tierces (postgres:17, redis:7-alpine)"
  foreach ($i in 'postgres:17', 'redis:7-alpine') {
    docker pull $i
    if ($LASTEXITCODE -ne 0) {
      docker image inspect $i *> $null
      if ($LASTEXITCODE -ne 0) { Echec "image $i indisponible (pas d'accès Internet ?)" }
      Write-Host "  $i : copie locale utilisée"
    }
  }
  Etape "Archive des images → $out\images.tar"
  docker save -o "$out\images.tar" $imgBe $imgFe postgres:17 redis:7-alpine
  if ($LASTEXITCODE -ne 0) { Echec "docker save" }
  $h = (Get-FileHash "$out\images.tar" -Algorithm SHA256).Hash.ToLower()
  [IO.File]::WriteAllText((Join-Path (Resolve-Path $out) 'images.tar.sha256'), "$h  images.tar`n")
}

Etape "Paquet de déploiement (scripts, compose, modèles .env, docs)"
git archive --format=tar.gz -o "$out\deploiement.tar.gz" HEAD deployment docs/deployment docs/runbook-migrations.md database/init
if ($LASTEXITCODE -ne 0) { Echec "git archive" }

$idBe = (docker image inspect $imgBe --format '{{.Id}}').Trim()
$idFe = (docker image inspect $imgFe --format '{{.Id}}').Trim()
$manifest = [ordered]@{
  version = $Version; commit = $sha; branche = $branche
  date = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK')
  revision_base = $head
  images = [ordered]@{ backend = "$imgBe ($idBe)"; frontend = "$imgFe ($idFe)"; postgres = 'postgres:17'; redis = 'redis:7-alpine' }
}
$manifest | ConvertTo-Json | Set-Content "$out\manifest.json" -Encoding UTF8

$lisezmoi = @"
BEA DIGITAL $Version (commit $sha, révision de base $head)

Sur le serveur (Linux, dossier d'installation /opt/bea-digital) :

  1. Copier ce dossier dans /opt/bea-digital/releases/$Version/
  2. Première installation uniquement :
       cd /opt/bea-digital && tar -xzf releases/$Version/deploiement.tar.gz
       cp deployment/env.production.example .env.production   (puis renseigner les secrets)
  3. Mise à jour (ou installation) :
       cd /opt/bea-digital
       tar -xzf releases/$Version/deploiement.tar.gz           (scripts à jour)
       BEA_VERSION=$Version IMAGES_TAR=releases/$Version/images.tar ./deployment/scripts/deploy.sh
  4. En cas de problème : ./deployment/scripts/rollback.sh

Le script vérifie l'archive, sauvegarde la base et les fichiers, applique les migrations,
redémarre et contrôle la santé. En cas d'échec, il revient automatiquement à la version précédente.
Ne jamais lancer : docker compose down -v
"@
$lisezmoi | Set-Content "$out\LISEZMOI.txt" -Encoding UTF8

if (-not $SansTag) {
  Etape "Tag Git $Version"
  git tag -a $Version -m "BEA DIGITAL $Version (révision de base $head)"
  if ($PousserTag) { git push origin $Version }
}

Etape "Livraison prête"
Get-ChildItem $out | Select-Object Name, @{ n = 'Taille (Mo)'; e = { [math]::Round($_.Length / 1MB, 1) } } | Format-Table -AutoSize
Write-Host "RELEASE_OK $Version → $out" -ForegroundColor Green
