param(
    [switch]$Execute,
    [string]$Distro = "Ubuntu",
    [string]$Environment = "biointel-step170"
)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ReportDir = Join-Path $ProjectRoot "reports"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

function Write-Result($Payload) {
    $Payload | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $ReportDir "step170_windows_wsl_provisioning.json")
    $Payload | ConvertTo-Json -Depth 10
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    Write-Result @{
        schema = "biointel.step170.windows-wsl-provisioning.v1"
        status = "blocked"
        reason = "WSL2 is not installed"
        remediation = "Run in an elevated terminal: wsl --install -d Ubuntu; reboot if requested; then rerun this script."
        execute = [bool]$Execute
    }
    exit 2
}

$Distros = (& wsl.exe -l -q) -replace "`0", ""
if (-not ($Distros | Where-Object { $_.Trim() -eq $Distro })) {
    Write-Result @{
        schema = "biointel.step170.windows-wsl-provisioning.v1"
        status = "blocked"
        reason = "Requested WSL distribution is not installed"
        distro = $Distro
        remediation = "Run in an elevated terminal: wsl --install -d $Distro"
        execute = [bool]$Execute
    }
    exit 2
}

$LinuxRoot = (& wsl.exe -d $Distro -- wslpath -a "$ProjectRoot").Trim()
$EnvFile = "$LinuxRoot/data/step170/environment/step170-linux-64.yml"
$InstallMicromamba = @'
set -euo pipefail
if ! command -v micromamba >/dev/null 2>&1; then
  mkdir -p "$HOME/.local/bin"
  tmp="$(mktemp -d)"
  curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C "$tmp" bin/micromamba
  install -m 0755 "$tmp/bin/micromamba" "$HOME/.local/bin/micromamba"
  rm -rf "$tmp"
fi
export PATH="$HOME/.local/bin:$PATH"
micromamba --version
'@
$Provision = @"
set -euo pipefail
export PATH="`$HOME/.local/bin:`$PATH"
export MAMBA_ROOT_PREFIX="`$HOME/.local/share/biointel-micromamba"
export BIOINTEL_STEP170_ENV='$Environment'
bash '$LinuxRoot/scripts/linux/step170_provision_runtime.sh' '$LinuxRoot'
"@

if (-not $Execute) {
    Write-Result @{
        schema = "biointel.step170.windows-wsl-provisioning.v1"
        status = "dry-run"
        distro = $Distro
        environment = $Environment
        project_root_windows = $ProjectRoot
        project_root_wsl = $LinuxRoot
        micromamba_bootstrap = $InstallMicromamba
        provision_command = $Provision
        note = "Rerun with -Execute to download/install open-source packages. Provider/manual tools and licences remain separate."
    }
    exit 0
}

& wsl.exe -d $Distro -- bash -lc $InstallMicromamba
if ($LASTEXITCODE -ne 0) { throw "micromamba bootstrap failed" }
& wsl.exe -d $Distro -- bash -lc $Provision
$Code = $LASTEXITCODE
Write-Result @{
    schema = "biointel.step170.windows-wsl-provisioning.v1"
    status = $(if ($Code -eq 0) { "completed" } else { "failed" })
    return_code = $Code
    distro = $Distro
    environment = $Environment
    project_root_windows = $ProjectRoot
    project_root_wsl = $LinuxRoot
    provider_manual_tools_still_require_operator_action = $true
    licences_not_auto_accepted = $true
}
exit $Code
