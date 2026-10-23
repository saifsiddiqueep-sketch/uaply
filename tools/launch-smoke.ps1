# The launch-day smoke check in one command, for PowerShell (the same as tools/launch-smoke.sh; docs/runbook-launch.md, steps 3 and 4).
# Read only: it never signs up, sends email or changes anything on the site.
#   powershell -File tools\launch-smoke.ps1 https://uaply.net [folder]
# In order: one timed /healthz probe, tools/live-check.py --expect all --no-rate-limit (every SKIP with its reason), tools/ui-live.js --read-only at
# 390x844 and 1280x800, then one summary block: PASS / FAIL / SKIP counts per tool, the healthz time, the commit the site runs (from
# /api/status) and the local time. With $env:UAPLY_OWNER_PASSWORD set in this window (never typed on the command line) it also reads the
# owner's self-check. The summary and both tools' full output go to <folder>\launch-smoke-<time>.txt (folder: the second argument,
# else $env:TEMP). Exit code 0 when no tool reported a FAIL. What "read only" means: see tools/launch-smoke.sh.
param([Parameter(Mandatory = $true)][string]$Base, [string]$Folder = $env:TEMP)
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Base = $Base.TrimEnd("/")
if ($Base -notmatch '^https?://[^/]+$') { Write-Output "usage: powershell -File tools\launch-smoke.ps1 https://uaply.net [folder]"; exit 2 }
New-Item -ItemType Directory -Force -Path $Folder | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$file = Join-Path $Folder "launch-smoke-$stamp.txt"
function Counts($text) { $m = [regex]::Matches($text, '(?m)^\d+ passed, \d+ failed, \d+ skipped'); if ($m.Count) { $m[$m.Count - 1].Value } else { "" } }

# 1. healthz, timed
$hz = "no answer"
try {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $r = Invoke-WebRequest -Uri "$Base/healthz" -UseBasicParsing -TimeoutSec 60
  $hz = "$($r.StatusCode) in $([math]::Round($sw.Elapsed.TotalSeconds, 3)) s"
} catch { $hz = "no answer ($($_.Exception.Message))" }
Write-Output "healthz: $hz"

# 2. the live check, 3. a stranger's first visit (both sizes, read only)
$env:PYTHONIOENCODING = "utf-8"
Write-Output "live-check.py ..."
$lc = (& python tools/live-check.py --base $Base --expect all --no-rate-limit 2>&1 | Out-String)
Write-Output "ui-live.js (390x844 and 1280x800, read only) ..."
$ul = (& node tools/cdp.js tools/ui-live.js --base $Base --read-only 2>&1 | Out-String)
# 3b. the sign-in gate, when the server says it is on (/api/status or /api/auth/providers "gate": true), or $env:GATE = "1"
$gl = ""; $glc = "not run (the server does not report the gate on)"; $gateOn = $false
foreach ($p in "/api/status", "/api/auth/providers") { try { if ((Invoke-WebRequest -Uri "$Base$p" -UseBasicParsing -TimeoutSec 30).Content -match '"gate"\s*:\s*true') { $gateOn = $true } } catch {} }
if ($gateOn -or $env:GATE -eq "1") {
  Write-Output "ui-gate-live.js (390x844 and 1280x800, read only) ..."
  $gl = (& node tools/cdp.js tools/ui-gate-live.js --base $Base 2>&1 | Out-String)
  $m = [regex]::Matches($gl, '(?m)^\d+ passed, \d+ failed, \d+ waiting'); $glc = if ($m.Count) { $m[$m.Count - 1].Value } else { "no summary (see below)" }
}

# 4. what the site says it runs, and the owner's self-check when the password is in this window
$commit = "no /api/status answer"
try { $st = Invoke-RestMethod -Uri "$Base/api/status" -TimeoutSec 30; $commit = if ($st.commit) { $st.commit } else { "not given" } } catch {}
$self = "not read (set `$env:UAPLY_OWNER_PASSWORD in this window to read it)"
if ($env:UAPLY_OWNER_PASSWORD) {
  try {
    $pair = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("owner:" + $env:UAPLY_OWNER_PASSWORD))
    $o = Invoke-RestMethod -Uri "$Base/api/status" -Headers @{ Authorization = "Basic $pair" } -TimeoutSec 30
    $self = if (-not $o.selfCheck) { "not in this answer (wrong password, or a deploy without it)" } elseif ($o.selfCheck.ok) { "ok" } else { "WARNINGS: " + (($o.selfCheck.warnings) -join "; ") }
  } catch { $self = "no answer" }
}

$failLines = @(($lc + "`n" + $ul + "`n" + $gl) -split "`r?`n" | Where-Object { $_ -match '^(FAIL|TEST SCRIPT FAILED)' })
$skipLines = @(($lc + "`n" + $ul) -split "`r?`n" | Where-Object { $_ -match '^SKIP' })
$lcc = Counts $lc; $ulc = Counts $ul
$summary = @(
  "UAply launch smoke check of $Base",
  "  local time      $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
  "  healthz         $hz",
  "  site runs       $commit",
  "  live-check.py   $(if ($lcc) { $lcc } else { 'no summary (see below)' })",
  "  ui-live.js      $(if ($ulc) { $ulc } else { 'no summary (see below)' })   (390x844 and 1280x800, read only)",
  "  ui-gate-live.js $glc",
  "  owner check     $self",
  "  result          $(if ($failLines.Count -eq 0) { 'no FAIL' } else { "$($failLines.Count) FAIL line(s): see below" })"
) + ($failLines | ForEach-Object { "    $_" }) + @("  skips (each with its reason):") + ($skipLines | ForEach-Object { "    $_" })
$summary | ForEach-Object { Write-Output $_ }
(($summary -join "`r`n") + "`r`n`r`n===== live-check.py`r`n" + $lc + "`r`n===== ui-live.js --read-only`r`n" + $ul + "`r`n===== ui-gate-live.js`r`n" + $gl) | Out-File -FilePath $file -Encoding utf8
Write-Output "written to $file"
if ($failLines.Count -eq 0) { exit 0 } else { exit 1 }
