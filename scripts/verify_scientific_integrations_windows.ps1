param(
    [string]$AppRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$RuntimeRoot = "$env:LOCALAPPDATA\BioIntelAI\ScientificRuntimes",
    [string]$ToolsHome = "$env:LOCALAPPDATA\BioIntelAI\Tools",
    [ValidateSet("P0", "P1", "P2", "All")]
    [string]$Priority = "All",
    [string]$WslDistro = "Ubuntu"
)

$ErrorActionPreference = "Continue"
$AppRoot = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($AppRoot))
$RuntimeRoot = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($RuntimeRoot))
$ToolsHome = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($ToolsHome))
$ConfigPath = Join-Path $AppRoot "config\biointel_scientific_runtime_profiles.json"
$IntegrationsPath = Join-Path $AppRoot "config\biointel_scientific_integrations.json"
if (-not (Test-Path -LiteralPath $ConfigPath) -or -not (Test-Path -LiteralPath $IntegrationsPath)) {
    Write-Host "BioIntel scientific integration configuration is incomplete."
    exit 2
}
$Config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
$Integrations = Get-Content -Raw -LiteralPath $IntegrationsPath | ConvertFrom-Json
$StateDir = Join-Path $RuntimeRoot "state"
New-Item -ItemType Directory -Path $StateDir -Force | Out-Null

$Profiles = @{}
$Failures = 0
foreach ($Profile in @($Config.profiles | Where-Object { $_.mode -eq "micromamba_python" })) {
    $ProfileId = [string]$Profile.profile_id
    $Python = Join-Path $RuntimeRoot ("mamba\envs\" + $ProfileId + "\python.exe")
    $Relevant = @($Integrations.integrations | Where-Object { [string]$_.runtime_profile -eq $ProfileId })
    $ModuleValues = New-Object System.Collections.Generic.List[string]
    foreach ($Integration in $Relevant) {
        foreach ($ModuleName in @($Integration.probe.python_modules)) {
            if ($ModuleName) { $ModuleValues.Add([string]$ModuleName) }
        }
    }
    $Modules = @($ModuleValues | Sort-Object -Unique)
    $Selected = $Priority -eq "All" -or [string]$Profile.priority -eq $Priority
    $Ready = $false
    $Detected = 0
    $Detail = "Not installed"
    if (Test-Path -LiteralPath $Python) {
        $ModuleJson = ConvertTo-Json -InputObject @($Modules) -Compress
        $Probe = "import importlib.util,json;mods=json.loads(r'''$ModuleJson''');r=[importlib.util.find_spec(x) is not None for x in mods];print(json.dumps({'ready':r}))"
        $Output = & $Python -c $Probe 2>$null
        if ($LASTEXITCODE -eq 0 -and $Output) {
            try {
                $Parsed = $Output | Select-Object -Last 1 | ConvertFrom-Json
                $Detected = @($Parsed.ready | Where-Object { [bool]$_ }).Count
                $Ready = $Modules.Count -gt 0 -and $Detected -eq $Modules.Count
                $Detail = if ($Ready) { "Ready" } else { "Dependencies incomplete" }
            } catch { $Detail = "Probe output invalid" }
        } else { $Detail = "Runtime probe failed" }
    }
    if ($Selected -and -not $Ready) { $Failures++ }
    $Freeze = Join-Path $StateDir ($ProfileId + "-resolved.txt")
    $FreezeHash = if (Test-Path -LiteralPath $Freeze) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Freeze).Hash.ToLowerInvariant() } else { "" }
    $Profiles[$ProfileId] = @{
        public_name = [string]$Profile.public_name
        priority = [string]$Profile.priority
        python = if (Test-Path -LiteralPath $Python) { $Python } else { "" }
        ready = $Ready
        detected = $Detected
        required = $Modules.Count
        detail = $Detail
        resolved_lock_sha256 = $FreezeHash
    }
}

$ToolNames = @("vina", "kraken2", "snakemake", "nextflow", "nf-core", "proteinmpnn")
$ToolRows = @()
foreach ($Name in $ToolNames) {
    $Local = Join-Path $ToolsHome ("bin\" + $Name + ".cmd")
    $System = Get-Command $Name -ErrorAction SilentlyContinue
    $Available = (Test-Path -LiteralPath $Local) -or [bool]$System
    $ResolvedPath = ""
    if (Test-Path -LiteralPath $Local) { $ResolvedPath = $Local }
    elseif ($System) { $ResolvedPath = [string]$System.Source }
    $ToolRows += [pscustomobject]@{ name = $Name; available = $Available; path = $ResolvedPath }
}
if ($Priority -in @("P1", "All")) {
    foreach ($Name in @("vina", "kraken2", "snakemake")) {
        if (-not ($ToolRows | Where-Object { $_.name -eq $Name -and $_.available })) { $Failures++ }
    }
}
if ($Priority -in @("P2", "All")) {
    foreach ($Name in @("nextflow", "nf-core", "proteinmpnn")) {
        if (-not ($ToolRows | Where-Object { $_.name -eq $Name -and $_.available })) { $Failures++ }
    }
}

$Payload = @{
    schema = "biointel.scientific-runtime-state.v2"
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    requested_priority = $Priority
    runtime_root = $RuntimeRoot
    profiles = $Profiles
    specialist_tools = $ToolRows
    failures = $Failures
}
$StatePath = Join-Path $StateDir "runtime-state.json"
$Payload | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $StatePath -Encoding UTF8
Write-Host "BioIntel scientific profiles verified: $(@($Profiles.Keys).Count)"
Write-Host "BioIntel verification failures for requested scope: $Failures"
Write-Host "State: $StatePath"
if ($Failures -gt 0) { exit 2 }
exit 0
