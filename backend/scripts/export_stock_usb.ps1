# Export Dossier Mine (Excel chiffre) vers TSV. Mot de passe : env STOCK_USB_PASSWORD.
param(
  [string]$Root = "C:\Users\sallm\bea-digital\storage\imports\stock-usb",
  [string]$OutDir = "C:\Users\sallm\bea-digital\storage\imports\stock-usb\_export"
)

$ErrorActionPreference = "Stop"
$pw = $env:STOCK_USB_PASSWORD
if (-not $pw) { throw "STOCK_USB_PASSWORD manquant" }

$months = @{
  "janvier" = 1; "janv" = 1
  "fevrier" = 2; "février" = 2; "fev" = 2
  "mars" = 3
  "avril" = 4
  "mai" = 5
  "juin" = 6
  "juillet" = 7
  "aout" = 8; "août" = 8
  "septembre" = 9; "sept" = 9
  "octobre" = 10; "oct" = 10
  "novembre" = 11; "nov" = 11
  "decembre" = 12; "décembre" = 12; "dec" = 12
}

function Get-YearMonth([string]$folderYear, [string]$name) {
  $n = $name.ToLowerInvariant()
  $n = $n.Normalize([Text.NormalizationForm]::FormD)
  $n = -join ($n.ToCharArray() | Where-Object { [Globalization.CharUnicodeInfo]::GetUnicodeCategory($_) -ne [Globalization.UnicodeCategory]::NonSpacingMark })
  if ($n.StartsWith("~$")) { return $null }
  if ($n -match "version 1" -or $n -match "^copie de") { return $null }
  if (-not $n.EndsWith(".xlsx")) { return $null }
  $year = 0
  if (-not [int]::TryParse($folderYear, [ref]$year)) { return $null }
  $hit = 0
  foreach ($k in ($months.Keys | Sort-Object { $_.Length } -Descending)) {
    if ($n -match [regex]::Escape($k)) { $hit = [int]$months[$k]; break }
  }
  if ($hit -eq 0 -and $n -match "f.?vrier") { $hit = 2 }
  if ($hit -eq 0 -and $n -match "d.?cembre") { $hit = 12 }
  if ($hit -eq 0) { return $null }
  return "{0:D4}-{1:D2}" -f $year, $hit
}

function Write-SheetTsv($ws, [string]$path) {
  $used = $ws.UsedRange
  if (-not $used) {
    [System.IO.File]::WriteAllText($path, "", [System.Text.UTF8Encoding]::new($false))
    return 0
  }
  $rows = [Math]::Min([int]$used.Rows.Count, 2500)
  $cols = [Math]::Min([int]$used.Columns.Count, 24)
  $start = $ws.Cells.Item($used.Row, $used.Column)
  $end = $ws.Cells.Item($used.Row + $rows - 1, $used.Column + $cols - 1)
  $vals = $ws.Range($start, $end).Value2
  $sb = New-Object System.Text.StringBuilder
  if ($rows -eq 1 -and $cols -eq 1) {
    [void]$sb.AppendLine([string]$vals)
  } else {
    for ($r = 1; $r -le $rows; $r++) {
      $cells = New-Object System.Collections.Generic.List[string]
      for ($c = 1; $c -le $cols; $c++) {
        $v = $vals[$r, $c]
        if ($null -eq $v) {
          $cells.Add("")
        } else {
          $cells.Add((([string]$v) -replace "`t", " " -replace "`r|`n", " "))
        }
      }
      [void]$sb.AppendLine(($cells -join "`t"))
    }
  }
  [System.IO.File]::WriteAllText($path, $sb.ToString(), [System.Text.UTF8Encoding]::new($false))
  return $rows
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Get-ChildItem -LiteralPath $OutDir -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$excel.AskToUpdateLinks = $false
$excel.EnableEvents = $false
$excel.ScreenUpdating = $false

$ok = 0
$skip = 0
$fail = 0
try {
  $yearDirs = Get-ChildItem -LiteralPath $Root -Directory | Where-Object { $_.Name -match "^\d{4}$" } | Sort-Object Name -Descending
  foreach ($dir in $yearDirs) {
    $files = Get-ChildItem -LiteralPath $dir.FullName -File -Filter "*.xlsx"
    foreach ($f in $files) {
      $ym = Get-YearMonth $dir.Name $f.Name
      if (-not $ym) { $skip++; Write-Output "SKIP $($dir.Name)/$($f.Name)"; continue }
      $dest = Join-Path $OutDir $ym
      if (Test-Path -LiteralPath $dest) {
        Write-Output "DUP $ym keep existing skip $($f.Name)"
        $skip++
        continue
      }
      New-Item -ItemType Directory -Force -Path $dest | Out-Null
      try {
        $wb = $excel.Workbooks.Open($f.FullName, 0, $true, [Type]::Missing, $pw)
        $names = @()
        for ($i = 1; $i -le $wb.Worksheets.Count; $i++) {
          $ws = $wb.Worksheets.Item($i)
          $nm = [string]$ws.Name
          $slug = if ($nm -match "Journal") { "journal" } elseif ($nm -match "Etat|État") { "etat" } elseif ($nm -match "article") { "articles" } else { "sheet$i" }
          $tsv = Join-Path $dest ($slug + ".tsv")
          $nrows = Write-SheetTsv $ws $tsv
          $names += "$slug=$nrows"
        }
        $wb.Close($false)
        $meta = @(
          "year_month=$ym"
          "source=$($f.FullName)"
          "sheets=$($names -join ',')"
        )
        [System.IO.File]::WriteAllLines((Join-Path $dest "meta.txt"), $meta, [System.Text.UTF8Encoding]::new($false))
        Write-Output "OK $ym $($names -join ' | ')"
        $ok++
      } catch {
        Write-Output "FAIL $($dir.Name)/$($f.Name) $($_.Exception.Message)"
        $fail++
        if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
      }
    }
  }
} finally {
  $excel.Quit()
  [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}
Write-Output "DONE ok=$ok skip=$skip fail=$fail out=$OutDir"
