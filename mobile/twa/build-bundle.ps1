# Builds the Play Store app bundle (app-release-bundle.aab) from twa-manifest.json: the one command for the owner.
#   powershell -ExecutionPolicy Bypass -File mobile\twa\build-bundle.ps1
# It asks the owner, in this window, for the only things a bot may not do: accepting Google's Android SDK licence (the first time),
# choosing the upload key's password (the first time) and typing it to sign the bundle. Nothing is uploaded and no password is saved.
#
# Steps: Bubblewrap installed if missing; `bubblewrap doctor` (first time: Yes to its JDK and Android SDK, accept the licence); the upload
# key made if mobile\android\uaply-upload-key.jks does not exist; the icons served from this computer while uaply.net does not yet serve
# them (until the next release); `bubblewrap update`; the target raised to Android 16 (API 36) if the template is older (Google Play's
# rule for new apps since August 31, 2026); `bubblewrap build`; the upload key's SHA-256 fingerprint printed for UAPLY_ASSETLINKS_SHA256.
# Written October 23, 2026 and not yet run end to end: Bubblewrap and the Android SDK were not installed on the computer it was written on.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Resolve-Path (Join-Path $here "..\..")
Set-Location $here

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Install Node.js 20 or newer from https://nodejs.org first, then run this again." }
if (-not (Get-Command bubblewrap -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Bubblewrap (npm install -g @bubblewrap/cli@latest) ..."
    npm install -g "@bubblewrap/cli@latest"
}

Write-Host "`n== bubblewrap doctor (the first time: answer Yes to the JDK and the Android SDK, and accept Google's licence)"
bubblewrap doctor

$key = Join-Path $repo "mobile\android\uaply-upload-key.jks"
$jdk = Get-ChildItem (Join-Path $env:USERPROFILE ".bubblewrap\jdk") -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
$keytool = if ($jdk) { Get-ChildItem $jdk.FullName -Recurse -Filter keytool.exe | Select-Object -First 1 -ExpandProperty FullName } else { "keytool" }
if (-not (Test-Path $key)) {
    Write-Host "`n== The upload key: choose a long password now, keep it in your password manager, and back the file up privately."
    & $keytool -genkeypair -keystore $key -alias upload -keyalg RSA -keysize 2048 -validity 10000 -storetype PKCS12 -dname "CN=UAply, O=UAply, C=US"
}

# uaply.net serves the icons only after the next release: until then Bubblewrap reads them from this computer
$manifest = Join-Path $here "twa-manifest.json"
$original = Get-Content $manifest -Raw
$server = $null
$live = $true
try { Invoke-WebRequest -Uri "https://uaply.net/uaply-icon-512.png" -Method Head -UseBasicParsing | Out-Null } catch { $live = $false }
try {
    if (-not $live) {
        Write-Host "`n== uaply.net does not serve the icons yet: serving shared\ on http://127.0.0.1:8799 for this build"
        $server = Start-Process python -ArgumentList "-m", "http.server", "8799", "--bind", "127.0.0.1", "--directory", (Join-Path $repo "shared") -PassThru -WindowStyle Hidden
        Start-Sleep -Seconds 2
        [IO.File]::WriteAllText($manifest, ($original -replace 'https://uaply\.net/uaply-icon', 'http://127.0.0.1:8799/uaply-icon'))   # UTF-8, no BOM
    }
    Write-Host "`n== bubblewrap update (makes the Android project from twa-manifest.json)"
    bubblewrap update --skipVersionUpgrade
} finally {
    [IO.File]::WriteAllText($manifest, $original)                     # the manifest in git always names uaply.net
    if ($server) { Stop-Process -Id $server.Id -ErrorAction SilentlyContinue }
}

$gradle = Join-Path $here "app\build.gradle"
$g = Get-Content $gradle -Raw
if ($g -match 'targetSdkVersion\s+(\d+)' -and [int]$Matches[1] -lt 36) {
    Write-Host "`n== The template targets API $($Matches[1]); Google Play needs 36 for a new app: raising it (this build only)"
    $g = $g -replace 'targetSdkVersion\s+\d+', 'targetSdkVersion 36'
    if ($g -match 'compileSdkVersion\s+(\d+)' -and [int]$Matches[1] -lt 36) { $g = $g -replace 'compileSdkVersion\s+\d+', 'compileSdkVersion 36' }
    [IO.File]::WriteAllText($gradle, $g)
}

Write-Host "`n== bubblewrap build (type the upload key's password when it asks; it is not saved)"
bubblewrap build

Write-Host "`n== Done: $here\app-release-bundle.aab (upload it in Play Console, Test and release, Internal testing)."
Write-Host "The upload key's SHA-256 (with the App signing key's from Play Console, both go into UAPLY_ASSETLINKS_SHA256 on Render):"
& $keytool -list -v -keystore $key -alias upload | Select-String "SHA256"
