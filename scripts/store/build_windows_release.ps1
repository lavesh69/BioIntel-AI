$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "../..")
$Desktop = Join-Path $Root "platform/desktop"
$Resources = Join-Path $Desktop "release-resources"
$Backend = Join-Path $Resources "backend"
$Workspace = Join-Path $Resources "workspace"

Write-Host "[1/6] Validating store release"
python (Join-Path $Root "scripts/verify_store_release.py")

Write-Host "[2/6] Building packaged Python backend"
python -m pip install --upgrade pip
python -m pip install -e $Root
python -m pip install pyinstaller==6.16.0
Push-Location $Desktop
python -m PyInstaller --noconfirm --clean BioIntelDesktop.spec
Pop-Location
Remove-Item $Backend -Recurse -Force -ErrorAction SilentlyContinue
New-Item $Backend -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $Desktop "dist/biointel-desktop-server/*") $Backend -Recurse -Force

Write-Host "[3/6] Preparing immutable workspace payload"
Remove-Item $Workspace -Recurse -Force -ErrorAction SilentlyContinue
New-Item $Workspace -ItemType Directory -Force | Out-Null
$Include = @("app.py", "VERSION", "src", "pages", "scripts", "data", "models", "config", ".streamlit", "docs/legal")
foreach ($Item in $Include) {
  $Source = Join-Path $Root $Item
  if (Test-Path $Source) { Copy-Item $Source (Join-Path $Workspace $Item) -Recurse -Force }
}
Get-ChildItem $Workspace -Recurse -Directory | Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") } | Remove-Item -Recurse -Force
Get-ChildItem $Workspace -Recurse -File | Where-Object { $_.Extension -in @(".pyc", ".pyo", ".wal", ".shm") } | Remove-Item -Force

Write-Host "[4/6] Installing desktop dependencies"
Push-Location $Desktop
npm ci

Write-Host "[5/6] Building Windows Store and installer packages"
if (-not $env:BIOINTEL_WINDOWS_PUBLISHER) { throw "BIOINTEL_WINDOWS_PUBLISHER is required from Partner Center." }
if (-not $env:BIOINTEL_WINDOWS_IDENTITY_NAME) { throw "BIOINTEL_WINDOWS_IDENTITY_NAME is required from Partner Center." }
npm run dist:windows
Pop-Location

Write-Host "[6/6] Complete"
Write-Host "Artifacts: $Desktop/dist-release"
