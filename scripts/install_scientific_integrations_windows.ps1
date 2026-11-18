param(
    [string]$AppRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$RuntimeRoot = "$env:LOCALAPPDATA\BioIntelAI\ScientificRuntimes",
    [string]$ToolsHome = "$env:LOCALAPPDATA\BioIntelAI\Tools",
    [ValidateSet("P0", "P1", "P2", "All")]
    [string]$Priority = "All",
    [string]$WslDistro = "Ubuntu"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$AppRoot = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($AppRoot))
$RuntimeRoot = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($RuntimeRoot))
$ToolsHome = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($ToolsHome))
$ConfigPath = Join-Path $AppRoot "config\biointel_scientific_runtime_profiles.json"
if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "BioIntel scientific runtime profile configuration is missing." }

$Cache = Join-Path $RuntimeRoot "cache"
$MambaRoot = Join-Path $RuntimeRoot "mamba"
$Native = Join-Path $RuntimeRoot "native"
$State = Join-Path $RuntimeRoot "state"
$Logs = Join-Path $RuntimeRoot "logs"
$ToolsBin = Join-Path $ToolsHome "bin"
$ToolsNative = Join-Path $ToolsHome "native"
$ToolsState = Join-Path $ToolsHome "state"
foreach ($Path in @($RuntimeRoot, $Cache, $MambaRoot, $Native, $State, $Logs, $ToolsHome, $ToolsBin, $ToolsNative, $ToolsState)) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}
$Log = Join-Path $Logs ("scientific-setup-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
Start-Transcript -Path $Log -Force | Out-Null

function Write-Stage([string]$Text) {
    Write-Host "`n=== $Text ===" -ForegroundColor Cyan
}

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Ensure-Micromamba {
    $TargetDir = Join-Path $Native "micromamba"
    $Target = Join-Path $TargetDir "micromamba.exe"
    if (Test-Path -LiteralPath $Target) { return $Target }
    Write-Stage "BioIntel isolated environment manager"
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    $Archive = Join-Path $Cache "biointel-runtime-manager-win-64.tar.bz2"
    if (-not (Test-Path -LiteralPath $Archive)) {
        Invoke-WebRequest -Uri "https://micro.mamba.pm/api/micromamba/win-64/latest" -OutFile $Archive -UseBasicParsing -Headers @{"User-Agent"="BioIntel-AI-Scientific-Runtime-v2"}
    }
    $Extract = Join-Path $TargetDir "extract"
    if (Test-Path -LiteralPath $Extract) { Remove-Item -Recurse -Force -LiteralPath $Extract }
    New-Item -ItemType Directory -Path $Extract -Force | Out-Null
    $Tar = Join-Path $env:SystemRoot "System32\tar.exe"
    if (-not (Test-Path -LiteralPath $Tar)) { throw "Windows tar.exe is required to prepare BioIntel isolated runtimes." }
    & $Tar -xjf $Archive -C $Extract *>> $Log
    if ($LASTEXITCODE -ne 0) { throw "BioIntel environment manager extraction failed." }
    $Found = Get-ChildItem -LiteralPath $Extract -Recurse -File -Filter "micromamba.exe" | Select-Object -First 1
    if (-not $Found) { throw "BioIntel environment manager executable was not found." }
    Copy-Item -LiteralPath $Found.FullName -Destination $Target -Force
    return $Target
}

function Install-PythonProfile($Profile, [string]$MambaExe) {
    $ProfileId = [string]$Profile.profile_id
    $PublicName = [string]$Profile.public_name
    $Environment = Join-Path $MambaRoot ("envs\" + $ProfileId)
    $Python = Join-Path $Environment "python.exe"
    $Requirements = Join-Path $AppRoot ([string]$Profile.requirements_file)
    if (-not (Test-Path -LiteralPath $Requirements)) { throw "Requirements contract missing for $PublicName" }

    Write-Stage $PublicName
    if (-not (Test-Path -LiteralPath $Python)) {
        & $MambaExe create -y -p $Environment -c conda-forge --strict-channel-priority "python=3.11" pip *>> $Log
        if ($LASTEXITCODE -ne 0) { throw "$PublicName environment creation failed." }
    }
    & $Python -m pip install --disable-pip-version-check --upgrade "pip<27" *>> $Log
    if ($LASTEXITCODE -ne 0) { throw "$PublicName package installer preparation failed." }
    & $Python -m pip install --disable-pip-version-check --prefer-binary -r $Requirements *>> $Log
    if ($LASTEXITCODE -ne 0) { throw "$PublicName dependency installation failed." }
    $Freeze = Join-Path $State ($ProfileId + "-resolved.txt")
    & $Python -m pip freeze | Set-Content -LiteralPath $Freeze -Encoding UTF8
    Write-Host "$PublicName ready."
}

function Write-CmdLauncher([string]$Name, [string]$CommandLine) {
    $Path = Join-Path $ToolsBin ($Name + ".cmd")
    $Body = "@echo off`r`n" + $CommandLine + "`r`n"
    Set-Content -LiteralPath $Path -Value $Body -Encoding ASCII
}

function Install-VinaNative {
    Write-Stage "BioIntel molecular docking runtime"
    $VinaDir = Join-Path $ToolsNative "biointel-docking"
    $VinaExe = Join-Path $VinaDir "vina.exe"
    if (-not (Test-Path -LiteralPath $VinaExe)) {
        New-Item -ItemType Directory -Path $VinaDir -Force | Out-Null
        $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/ccsb-scripps/AutoDock-Vina/releases/latest" -Headers @{"User-Agent"="BioIntel-AI-Scientific-Runtime-v2"; "Accept"="application/vnd.github+json"}
        $Asset = $Release.assets | Where-Object { $_.name -match '(?i)(win|windows).*(x86_64|64).*\.exe$|(?i)vina.*win.*\.exe$' } | Select-Object -First 1
        if (-not $Asset) { throw "BioIntel docking runtime did not publish a compatible Windows executable." }
        $Download = Join-Path $Cache ([string]$Asset.name)
        Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $Download -UseBasicParsing -Headers @{"User-Agent"="BioIntel-AI-Scientific-Runtime-v2"}
        Copy-Item -LiteralPath $Download -Destination $VinaExe -Force
        $Digest = Get-FileSha256 $VinaExe
        [pscustomobject]@{
            schema = "biointel.native-component.v2"
            installed_at = (Get-Date).ToUniversalTime().ToString("o")
            public_name = "BioIntel Molecular Docking Engine"
            upstream_release = [string]$Release.tag_name
            asset_sha256 = $Digest
            executable = $VinaExe
        } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ToolsState "biointel-docking.json") -Encoding UTF8
    }
    Write-CmdLauncher "vina" ('"' + $VinaExe + '" %*')
}

function Assert-WslReady {
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { throw "WSL 2 is required for BioIntel specialist workflow workers." }
    $List = (& wsl.exe -l -q) -replace "`0", ""
    if (-not ($List | Where-Object { $_.Trim() -eq $WslDistro })) { throw "The configured BioIntel WSL distribution is not installed." }
}

function Install-WslRuntime([string[]]$Packages) {
    Assert-WslReady
    $PackageLine = ($Packages | Sort-Object -Unique) -join " "
    $Script = @"
set -euo pipefail
mkdir -p ~/.local/bin ~/.biointel ~/.biointel/components ~/.biointel/runtimes
if [ ! -x ~/.local/bin/micromamba ]; then
  curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj -C ~/.local/bin --strip-components=1 bin/micromamba
fi
export MAMBA_ROOT_PREFIX=~/.biointel/mamba
if ~/.local/bin/micromamba env list | awk '{print `$1}' | grep -qx biointel-tools; then
  ~/.local/bin/micromamba install -y -n biointel-tools -c conda-forge -c bioconda --strict-channel-priority python=3.11 $PackageLine
else
  ~/.local/bin/micromamba create -y -n biointel-tools -c conda-forge -c bioconda --strict-channel-priority python=3.11 $PackageLine
fi
~/.local/bin/micromamba list -n biointel-tools --json > ~/.biointel/installed-packages.json
"@
    & wsl.exe -d $WslDistro -- bash -lc $Script *>> $Log
    if ($LASTEXITCODE -ne 0) { throw "BioIntel WSL scientific worker setup failed." }
    $WslHome = (& wsl.exe -d $WslDistro -- bash -lc 'printf %s "$HOME"' 2>$null)
    if (-not $WslHome) { throw "BioIntel could not resolve the WSL user home." }
    return ([string]$WslHome).Trim()
}

function Write-WslMambaLauncher([string]$Name, [string]$Command, [string]$WslHome) {
    $Mamba = "$WslHome/.local/bin/micromamba"
    $Line = 'wsl.exe -d "' + $WslDistro + '" --exec ' + $Mamba + ' run -n biointel-tools ' + $Command + ' %*'
    Write-CmdLauncher $Name $Line
}

function Write-WslDirectLauncher([string]$Name, [string]$LinuxExecutable) {
    $Line = 'wsl.exe -d "' + $WslDistro + '" --exec ' + $LinuxExecutable + ' %*'
    Write-CmdLauncher $Name $Line
}

function Update-WslMarker([string[]]$Tools) {
    $Marker = Join-Path $ToolsState "wsl-tools.json"
    $Existing = @()
    if (Test-Path -LiteralPath $Marker) {
        try { $Existing = @((Get-Content -Raw -LiteralPath $Marker | ConvertFrom-Json).tools) } catch { $Existing = @() }
    }
    $Combined = @($Existing) + @($Tools) | ForEach-Object { [string]$_ } | Sort-Object -Unique
    [pscustomobject]@{
        schema = "biointel.wsl-tools.v2"
        distro = $WslDistro
        environment = "biointel-tools"
        installed_at = (Get-Date).ToUniversalTime().ToString("o")
        tools = $Combined
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Marker -Encoding UTF8
}

function Install-P1CliWorkers {
    Install-VinaNative
    Write-Stage "BioIntel classification and workflow workers"
    $WslHome = Install-WslRuntime @("kraken2", "snakemake-minimal")
    Write-WslMambaLauncher "kraken2" "kraken2" $WslHome
    Write-WslMambaLauncher "kraken2-inspect" "kraken2-inspect" $WslHome
    Write-WslMambaLauncher "snakemake" "snakemake" $WslHome
    Update-WslMarker @("kraken2", "kraken2-inspect", "snakemake")
}

function Install-P2CliWorkers {
    Write-Stage "BioIntel reproducible pipeline and protein-design workers"
    $WslHome = Install-WslRuntime @("nf-core", "nextflow", "git")
    $Script = @'
set -euo pipefail
mkdir -p ~/.biointel/components ~/.biointel/runtimes ~/.local/bin
if [ ! -d ~/.biointel/components/protein-design/.git ]; then
  git clone --depth 1 https://github.com/dauparas/ProteinMPNN.git ~/.biointel/components/protein-design
fi
if [ ! -x ~/.biointel/runtimes/protein-ai/bin/python ]; then
  ~/.local/bin/micromamba run -n biointel-tools python -m venv ~/.biointel/runtimes/protein-ai
fi
~/.biointel/runtimes/protein-ai/bin/python -m pip install --disable-pip-version-check --upgrade 'pip<27'
~/.biointel/runtimes/protein-ai/bin/python -m pip install --disable-pip-version-check --prefer-binary 'torch>=2.5,<3' 'numpy>=1.26,<3'
cat > ~/.local/bin/biointel-protein-design <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
exec ~/.biointel/runtimes/protein-ai/bin/python ~/.biointel/components/protein-design/protein_mpnn_run.py "$@"
SCRIPT
chmod +x ~/.local/bin/biointel-protein-design
git -C ~/.biointel/components/protein-design rev-parse HEAD > ~/.biointel/protein-design-revision.txt
'@
    & wsl.exe -d $WslDistro -- bash -lc $Script *>> $Log
    if ($LASTEXITCODE -ne 0) { throw "BioIntel protein-design worker setup failed." }
    Write-WslMambaLauncher "nf-core" "nf-core" $WslHome
    Write-WslMambaLauncher "nextflow" "nextflow" $WslHome
    Write-WslDirectLauncher "proteinmpnn" "$WslHome/.local/bin/biointel-protein-design"
    Update-WslMarker @("nf-core", "nextflow", "proteinmpnn")
}

try {
    $Config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    $Selected = @($Config.profiles | Where-Object {
        $_.mode -eq "micromamba_python" -and ($Priority -eq "All" -or $_.priority -eq $Priority)
    })
    if ($Selected.Count -gt 0) {
        $MambaExe = Ensure-Micromamba
        foreach ($Profile in $Selected) { Install-PythonProfile $Profile $MambaExe }
    }

    if ($Priority -in @("P1", "All")) { Install-P1CliWorkers }
    if ($Priority -in @("P2", "All")) { Install-P2CliWorkers }

    Write-Stage "BioIntel scientific runtime verification"
    $Verifier = Join-Path $AppRoot "scripts\verify_scientific_integrations_windows.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Verifier -AppRoot $AppRoot -RuntimeRoot $RuntimeRoot -ToolsHome $ToolsHome -Priority $Priority -WslDistro $WslDistro *>> $Log
    if ($LASTEXITCODE -ne 0) { throw "BioIntel scientific runtime verification found incomplete profiles." }

    Write-Host "`nBioIntel $Priority scientific integration setup completed." -ForegroundColor Green
    Write-Host "Protected setup log: $Log"
    Stop-Transcript | Out-Null
    exit 0
} catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Protected setup log: $Log"
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}
