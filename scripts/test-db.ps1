# Cree la base de test UNIQUE de BEA DIGITAL : bea_digital_test (serveur bea-postgres).
# Fichier ASCII : Windows PowerShell 5.1 lit les .ps1 sans BOM en ANSI.
#
#   .\scripts\test-db.ps1            # cree la base si absente
#   .\scripts\test-db.ps1 -Recreer   # supprime et regenere UNIQUEMENT bea_digital_test
#
# Contenu :
#   1. copie complete de bea_digital (pg_dump lu seulement, pg_restore dans la base de test) ;
#   2. Base Clientele : les tables clientele_* VIDES de la copie sont rechargees depuis
#      backups/avant_purge_clientele_20261022_104012.dump (lecture seule du dump) ;
#   3. acces neutralises : mot de passe des comptes copies remplace par un secret aleatoire
#      jamais affiche, TOTP retire, sessions et historique des mots de passe supprimes ;
#      limites de debit retirees de la politique de securite copiee (l'environnement decide) ;
#      seul admin@el-amana.mr recoit le mot de passe des tests (BEA_TEST_PASSWORD, defaut des tests) ;
#   4. droit de connexion du role applicatif bea_app.
# Les comptes et donnees synthetiques de charge sont ajoutes par loadtest/setup-env.ps1.
# Aucune ecriture dans bea_digital.

param([switch]$Recreer)

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
$racine = Split-Path -Parent $PSScriptRoot
$BASE = "bea_digital_test"
$SOURCE = "bea_digital"
$PG = "bea-postgres"
$DUMP_CLIENTELE = "avant_purge_clientele_20261022_104012.dump"

function Etape($texte) { Write-Host "==> $texte" -ForegroundColor Cyan }
function Psql($base, $sql) {
    $sortie = $sql | docker exec -i $PG psql -U admin -d $base -X -q -v ON_ERROR_STOP=1 -At 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql ($base) : $sortie" }
    return $sortie
}
function Sh($script) {
    # PowerShell 5.1 ajoute un BOM et des CR a l'entree standard : retires avant sh (scripts ASCII).
    $sortie = $script | docker exec -i $PG sh -c "tr -d '\r\357\273\277' | sh" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "commande en echec : $sortie" }
    return $sortie
}

if ($BASE -eq $SOURCE -or $BASE -notmatch '^bea_digital_test$') { throw "garde-fou : cible $BASE refusee" }

Push-Location $racine
try {
    if ((docker inspect -f "{{.State.Health.Status}}" $PG 2>$null) -ne "healthy") {
        throw "$PG n'est pas demarre : docker compose --env-file .env.docker up -d postgres"
    }
    if (-not (Test-Path (Join-Path $racine "backups\$DUMP_CLIENTELE"))) {
        throw "dump Base Clientele absent : backups\$DUMP_CLIENTELE"
    }

    $existe = (Psql "postgres" "select 1 from pg_database where datname = '$BASE';") -eq "1"
    if ($existe -and -not $Recreer) {
        Write-Host "$BASE existe deja (-Recreer pour la regenerer)." -ForegroundColor Yellow
        return
    }
    if ($existe) {
        Etape "Suppression de $BASE"
        Psql "postgres" "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$BASE';" | Out-Null
        Psql "postgres" "drop database $BASE;" | Out-Null
    }

    Etape "Creation de $BASE (meme encodage et collation que $SOURCE)"
    $loc = Psql "postgres" "select datcollate || '|' || datctype from pg_database where datname = '$SOURCE';"
    $collate, $ctype = $loc -split "\|"
    Psql "postgres" "create database $BASE owner admin template template0 encoding 'UTF8' lc_collate '$collate' lc_ctype '$ctype';" | Out-Null

    Etape "Copie de $SOURCE (pg_dump -Fc puis pg_restore)"
    Sh @"
set -e
trap 'rm -f /tmp/bdt_source.dump' EXIT
pg_dump -U admin -Fc -d $SOURCE -f /tmp/bdt_source.dump
pg_restore -U admin -d $BASE --exit-on-error /tmp/bdt_source.dump
"@ | Out-Null

    Etape "Base Clientele depuis $DUMP_CLIENTELE (tables vides de la copie uniquement)"
    $charge = Sh @"
set -e
D=/backups/$DUMP_CLIENTELE
trap 'rm -f /tmp/bdt_toc /tmp/bdt_toc_all' EXIT
pg_restore -l "`$D" > /tmp/bdt_toc_all
: > /tmp/bdt_toc
grep ' TABLE DATA public clientele_' /tmp/bdt_toc_all | while read -r ligne; do
  t=`$(echo "`$ligne" | awk '{print `$(NF-1)}')
  n=`$(psql -U admin -d $BASE -Atc "select count(*) from public.`$t")
  if [ "`$n" = "0" ]; then echo "`$ligne" >> /tmp/bdt_toc; fi
done
pg_restore -U admin -d $BASE --data-only --disable-triggers --exit-on-error -L /tmp/bdt_toc "`$D"
grep -c 'TABLE DATA' /tmp/bdt_toc
"@
    Write-Host "    tables clientele rechargees : $charge"

    Etape "Sequences et references orphelines des tables clientele"
    $orphelins = Psql $BASE @"
do `$`$
declare r record; n bigint; total bigint := 0;
begin
  perform set_config('session_replication_role', 'replica', true);
  for r in
    select s.oid::regclass as seq, t.oid::regclass as tbl, a.attname as col
    from pg_class s
    join pg_depend d on d.objid = s.oid and d.deptype in ('a', 'i')
    join pg_class t on t.oid = d.refobjid
    join pg_attribute a on a.attrelid = t.oid and a.attnum = d.refobjsubid
    where s.relkind = 'S' and t.relname like 'clientele\_%'
  loop
    execute format('select setval(%L, greatest((select coalesce(max(%I), 0) from %s), 1))', r.seq, r.col, r.tbl);
  end loop;
  for r in
    select c.conrelid::regclass as tbl, a.attname as col, c.confrelid::regclass as ref, fa.attname as refcol,
           a.attnotnull as obligatoire
    from pg_constraint c
    join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
    join pg_attribute fa on fa.attrelid = c.confrelid and fa.attnum = c.confkey[1]
    where c.contype = 'f' and array_length(c.conkey, 1) = 1
      and c.conrelid::regclass::text like 'clientele\_%'
  loop
    execute format('select count(*) from %s x where x.%I is not null and not exists (select 1 from %s y where y.%I = x.%I)',
                   r.tbl, r.col, r.ref, r.refcol, r.col) into n;
    if n > 0 then
      if r.obligatoire then
        raise exception 'reference obligatoire orpheline : %.% -> % (% lignes)', r.tbl, r.col, r.ref, n;
      end if;
      execute format('update %s x set %I = null where x.%I is not null and not exists (select 1 from %s y where y.%I = x.%I)',
                     r.tbl, r.col, r.col, r.ref, r.refcol, r.col);
      raise notice '%.% -> % : % references remises a NULL', r.tbl, r.col, r.ref, n;
      total := total + n;
    end if;
  end loop;
  perform set_config('bdt.orphelins', total::text, true);
end `$`$;
select 'ok';
"@
    Write-Host "    $orphelins"

    Etape "Neutralisation des acces des comptes copies"
    $hash = docker exec bea-backend python -c "import bcrypt, secrets; print(bcrypt.hashpw(secrets.token_hex(32).encode(), bcrypt.gensalt()).decode())"
    if ($LASTEXITCODE -ne 0 -or $hash -notmatch '^\$2[aby]\$') { throw "generation du secret aleatoire en echec" }
    $sql = @'
update users set hashed_password = '__HASH__', totp_secret = null, totp_enabled = false;
delete from auth_sessions;
delete from password_history;
update platform_ops_flags
   set value = value - 'rate_limit_api_per_minute' - 'rate_limit_login_per_minute' - 'rate_limit_sensitive_per_minute'
 where key = 'security_policy';
'@
    Psql $BASE $sql.Replace("__HASH__", $hash.Trim()) | Out-Null
    $hash = $null

    Etape "Compte de test admin@el-amana.mr (mot de passe des tests : BEA_TEST_PASSWORD)"
    $secretTest = if ($env:BEA_TEST_PASSWORD) { $env:BEA_TEST_PASSWORD } else { "Admin@2026" }
    $hashTest = docker exec -e "BDT_SECRET=$secretTest" bea-backend python -c "import bcrypt, os; print(bcrypt.hashpw(os.environ['BDT_SECRET'].encode(), bcrypt.gensalt()).decode())"
    if ($LASTEXITCODE -ne 0 -or $hashTest -notmatch '^\$2[aby]\$') { throw "hachage du mot de passe de test en echec" }
    $sqlTest = @'
update users set hashed_password = '__HASH__', must_change_password = false where email = 'admin@el-amana.mr';
'@
    Psql $BASE $sqlTest.Replace("__HASH__", $hashTest.Trim()) | Out-Null
    $hashTest = $null; $secretTest = $null

    Etape "Droits du role applicatif bea_app"
    Psql $BASE "grant connect, temporary on database $BASE to bea_app;" | Out-Null
    # Base de test uniquement : les tests de stock suppriment leurs comptes synthetiques et donc
    # leurs lignes d'audit (FK sans cascade). En production audit_logs reste INSERT/SELECT.
    Psql $BASE "grant delete on public.audit_logs to bea_app;" | Out-Null
    $controle = Psql $BASE "select has_table_privilege('bea_app','public.users','INSERT') and not has_table_privilege('bea_app','public.audit_logs','UPDATE');"
    if ($controle -ne "t") { throw "droits bea_app incomplets sur $BASE (appliquer database/roles/bea_app.sql)" }
    Psql $BASE "analyze;" | Out-Null

    $stats = Psql $BASE "select (select version_num from alembic_version) || ' | ' || (select count(*) from pg_tables where schemaname = 'public') || ' tables | ' || (select count(*) from users) || ' comptes | ' || (select count(*) from clientele_clients) || ' clients | ' || (select count(*) from immobilisations) || ' immobilisations | ' || (select count(*) from mg_stock_mouvements) || ' mouvements';"
    Write-Host ""
    Write-Host "Base de test prete : $BASE ($stats)" -ForegroundColor Green
}
finally {
    Pop-Location
}
