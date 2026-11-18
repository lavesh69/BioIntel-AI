param(
    [ValidateSet("Plan","ExecuteOpen","Resume","Verify")][string]$Mode = "Plan",
    [string]$Distro = "Ubuntu",
    [ValidateSet("cpu-standard","gpu-scientific","reference-server")][string]$Profile = "gpu-scientific",
    [double]$MaxReferenceGB = 2.0,
    [switch]$AntivirusTested,
    [switch]$SleepResumeTested,
    [switch]$NetworkLossTested,
    [switch]$LargeFileTested,
    [switch]$RecoveryTested
)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$StateRoot = Join-Path $ProjectRoot "UserData\step175"
$ReportRoot = Join-Path $ProjectRoot "reports"
New-Item -ItemType Directory -Force -Path $StateRoot,$ReportRoot | Out-Null
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

function Get-Sha256([string]$Path) {
    if (-not (Test-Path $Path)) { return "" }
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}
function Save-Json($Object,[string]$Path) {
    $Object | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $Path
}
function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$computer = Get-CimInstance Win32_ComputerSystem
$systemDrive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($env:SystemDrive)'"
$wslCommand = Get-Command wsl.exe -ErrorAction SilentlyContinue
$wslVersionText = if ($wslCommand) { (& wsl.exe --version 2>&1 | Out-String) } else { "" }
$distros = if ($wslCommand) { ((& wsl.exe -l -q 2>&1) -replace "`0", "") } else { @() }
$virtualization = $false
try { $virtualization = [bool]$computer.HypervisorPresent } catch {}
$longPaths = (Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled -eq 1
$nvidia = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$gpuName=""; $gpuDriver=""; $gpuVramGB=0.0; $cuda=""
if ($nvidia) {
    $gpuLine = (& nvidia-smi.exe --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1)
    if ($gpuLine) {
        $parts=$gpuLine -split ','
        $gpuName=$parts[0].Trim(); $gpuDriver=$parts[1].Trim(); $gpuVramGB=[math]::Round(([double]$parts[2].Trim())/1024,2)
    }
    $cudaLine = (& nvidia-smi.exe 2>$null | Select-String "CUDA Version" | Select-Object -First 1)
    if ($cudaLine) { $cuda = $cudaLine.ToString() }
}
$networkEndpoints = @("https://micro.mamba.pm","https://conda.anaconda.org","https://ftp.ncbi.nlm.nih.gov","https://rest.uniprot.org")
$networkResults=@{}
foreach($endpoint in $networkEndpoints) {
    try { $response=Invoke-WebRequest -Uri $endpoint -Method Head -TimeoutSec 20 -UseBasicParsing; $networkResults[$endpoint]=[int]$response.StatusCode }
    catch { $networkResults[$endpoint]=0 }
}
$profileRequirements = @{
    "cpu-standard"=@{ram=32;storage=250;gpu=$false;vram=0}
    "gpu-scientific"=@{ram=64;storage=1000;gpu=$true;vram=16}
    "reference-server"=@{ram=64;storage=4000;gpu=$false;vram=0}
}[$Profile]
$ramGB=[math]::Round($computer.TotalPhysicalMemory/1GB,2)
$freeGB=[math]::Round($systemDrive.FreeSpace/1GB,2)
$checks=[ordered]@{
    windows_x64 = [Environment]::Is64BitOperatingSystem
    supported_windows_build = [int]$os.BuildNumber -ge 19045
    administrator = Test-Admin
    virtualization_ready = $virtualization
    wsl2_ready = [bool]$wslCommand -and ($wslVersionText -match "WSL version")
    requested_distro_installed = [bool]($distros | Where-Object { $_.Trim() -eq $Distro })
    long_paths_enabled = $longPaths
    ram_meets_profile = $ramGB -ge $profileRequirements.ram
    storage_meets_profile = $freeGB -ge $profileRequirements.storage
    gpu_meets_profile = (-not $profileRequirements.gpu) -or ([bool]$nvidia -and $gpuVramGB -ge $profileRequirements.vram)
    provider_network_reachable = ($networkResults.Values | Where-Object { $_ -gt 0 }).Count -eq $networkResults.Count
    antivirus_tested = [bool]$AntivirusTested
    sleep_resume_tested = [bool]$SleepResumeTested
    network_loss_tested = [bool]$NetworkLossTested
    large_file_tested = [bool]$LargeFileTested
    recovery_tested = [bool]$RecoveryTested
}
$automaticRequired = @("windows_x64","supported_windows_build","virtualization_ready","wsl2_ready","requested_distro_installed","long_paths_enabled","ram_meets_profile","storage_meets_profile","gpu_meets_profile","provider_network_reachable")
$manualRequired = @("antivirus_tested","sleep_resume_tested","network_loss_tested","large_file_tested","recovery_tested")
$autoPass = ($automaticRequired | Where-Object { -not $checks[$_] }).Count -eq 0
$manualPass = ($manualRequired | Where-Object { -not $checks[$_] }).Count -eq 0
$probe = [ordered]@{
    schema="biointel.step175.windows-host-probe.v1"; host_id=$env:COMPUTERNAME; created_at_utc=(Get-Date).ToUniversalTime().ToString("o")
    os_caption=$os.Caption; windows_build=$os.BuildNumber; platform="$($os.Caption) build $($os.BuildNumber)"; architecture=$os.OSArchitecture
    cpu_name=$cpu.Name; cpu_threads=$cpu.NumberOfLogicalProcessors; ram_gb=$ramGB; free_storage_gb=$freeGB; profile=$Profile
    wsl_version=$wslVersionText.Trim(); distro=$Distro; gpu_detected=[bool]$nvidia; gpu_name=$gpuName; gpu_driver=$gpuDriver; gpu_vram_gb=$gpuVramGB; cuda_runtime=$cuda
    network_results=$networkResults; checks=$checks; automatic_checks_passed=$autoPass; manual_physical_tests_passed=$manualPass
    target_windows_environment_qualified=($autoPass -and $manualPass)
    boundary="A target host is fully qualified only after automatic checks and the recorded antivirus, sleep/resume, network-loss, large-file and recovery tests pass."
}
$probePath=Join-Path $StateRoot "host_probe_$($env:COMPUTERNAME).json"
Save-Json $probe $probePath
& $Python scripts\step175_environment_manager.py import-host-probe $probePath
if ($LASTEXITCODE -ne 0) { throw "Host probe import failed" }
& $Python scripts\step175_environment_manager.py plan --profile $Profile --max-reference-gb $MaxReferenceGB
if ($LASTEXITCODE -ne 0) { throw "Execution plan failed" }

if ($Mode -in @("ExecuteOpen","Resume")) {
    if (-not $wslCommand) { throw "WSL2 is unavailable" }
    $linuxRoot = (& wsl.exe -d $Distro -- wslpath -a "$ProjectRoot").Trim()
    $linuxMode = if ($Mode -eq "Resume") { "resume" } else { "execute" }
    & wsl.exe -d $Distro -- bash "$linuxRoot/scripts/linux/step175_execute_wsl.sh" "$linuxRoot" "$linuxMode" "$($env:COMPUTERNAME)"
    if ($LASTEXITCODE -ne 0) { Write-Warning "One or more WSL environment groups failed. Resume is supported." }
    $resultDir=Join-Path $StateRoot "wsl_results\$($env:COMPUTERNAME)"
    if (Test-Path $resultDir) {
        Get-ChildItem $resultDir -Filter "engine-*.json" | ForEach-Object {
            & $Python scripts\step175_environment_manager.py import-engine-result $_.FullName
            if ($LASTEXITCODE -notin @(0,2)) { Write-Warning "Could not import $($_.Name)" }
        }
    }
    if ($Mode -eq "ExecuteOpen") {
        & $Python scripts\step170_reference_manager.py --root $ProjectRoot --execute --max-size-gb $MaxReferenceGB --reference hpo-ontology --reference go-basic --reference reactome-uniprot --reference uniprot-swissprot --reference grch38-fasta --reference clinvar-grch38-vcf --reference clinvar-grch38-tbi
        if ($LASTEXITCODE -ne 0) { Write-Warning "Some open references were not downloaded; review Step 170 reference report." }
    }
}

& $Python scripts\step175_validate_environment.py
$validationCode=$LASTEXITCODE
$runReport=[ordered]@{schema="biointel.step175.windows-execution.v1";mode=$Mode;profile=$Profile;host_probe=$probePath;host_probe_sha256=(Get-Sha256 $probePath);validation_return_code=$validationCode;target_environment_qualified=$probe.target_windows_environment_qualified;restricted_licences_auto_accepted=$false;provider_credentials_stored=$false}
Save-Json $runReport (Join-Path $ReportRoot "step175_windows_execution.json")
$runReport | ConvertTo-Json -Depth 20
exit $validationCode
