param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$UserData,
    [string]$Distribution = "Ubuntu",
    [string]$EnvironmentName = "biointel-engines-v196",
    [switch]$AcceptNetworkDownloads
)
$ErrorActionPreference = "Stop"
if (-not $AcceptNetworkDownloads) {
    throw "Network downloads were not authorized. Re-run with -AcceptNetworkDownloads after reviewing licences and disk requirements."
}
$Root = (Resolve-Path $Root).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "BioIntel managed Python is missing. Run INSTALL_WINDOWS.bat first." }
$Acquisition = Join-Path $UserData "engine_packs\v19.6-acquisition\biointel-wsl2-environment.yml"
if (-not (Test-Path $Acquisition)) {
    & $Python (Join-Path $Root "scripts\step214_prepare_engine_acquisition.py") --root $Root --output (Split-Path $Acquisition)
    if ($LASTEXITCODE -ne 0) { throw "Could not prepare the engine acquisition bundle." }
}
$WslStatus = & wsl.exe --status 2>&1
if ($LASTEXITCODE -ne 0) { throw "WSL2 is unavailable. Enable WSL2 and install an approved Linux distribution." }
$Distros = (& wsl.exe -l -q) | ForEach-Object { $_.Trim([char]0).Trim() } | Where-Object { $_ }
if ($Distros -notcontains $Distribution) { throw "WSL distribution '$Distribution' is not installed. Available: $($Distros -join ', ')" }
$WslEnvironment = (& wsl.exe -d $Distribution -- wslpath -a $Acquisition).Trim()
if (-not $WslEnvironment) { throw "Could not convert the engine environment path for WSL2." }
$Bootstrap = @'
set -euo pipefail
mkdir -p "$HOME/.local/bin" "$HOME/.cache/biointel-engine-install"
if [ ! -x "$HOME/.local/bin/micromamba" ]; then
  curl -fL --retry 3 https://micro.mamba.pm/api/micromamba/linux-64/latest -o "$HOME/.cache/biointel-engine-install/micromamba.tar.bz2"
  tar -xjf "$HOME/.cache/biointel-engine-install/micromamba.tar.bz2" -C "$HOME/.cache/biointel-engine-install" bin/micromamba
  install -m 0755 "$HOME/.cache/biointel-engine-install/bin/micromamba" "$HOME/.local/bin/micromamba"
fi
"$HOME/.local/bin/micromamba" create -y -n "$1" -f "$2" || "$HOME/.local/bin/micromamba" update -y -n "$1" -f "$2"
"$HOME/.local/bin/micromamba" clean -a -y
'@
& wsl.exe -d $Distribution -- bash -lc $Bootstrap biointel-wsl-bootstrap $EnvironmentName $WslEnvironment
if ($LASTEXITCODE -ne 0) { throw "WSL2 engine environment installation failed." }
$Report = Join-Path $UserData "reports\step214-wsl2-engine-registration.json"
& $Python (Join-Path $Root "scripts\step214_register_wsl_environment.py") --root $Root --user-data $UserData --distribution $Distribution --environment $EnvironmentName --output $Report
if ($LASTEXITCODE -ne 0) { throw "WSL2 engine registration failed." }
Write-Host "BioIntel WSL2 engine environment installed and registered. Qualification remains fail-closed until smoke evidence passes."
