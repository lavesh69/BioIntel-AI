param(
    [switch]$ForceRepair
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-Step([string]$Text) {
    Write-Host $Text -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$false)][string[]]$Arguments = @(),
        [Parameter(Mandatory=$false)][string]$WorkingDirectory = $script:AppRoot
    )
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $FilePath @Arguments 2>&1 | Tee-Object -FilePath $script:LogPath -Append
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
        if ($code -ne 0) {
            throw ('Command failed with exit code {0}: {1} {2}' -f $code, $FilePath, ($Arguments -join ' '))
        }
    }
    finally {
        Pop-Location
    }
}

function Test-Python311([string]$Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate) -or -not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
        return $false
    }
    try {
        & $Candidate -c "import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==64 else 1)" *> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch { return $false }
}

function Find-Python311 {
    $candidates = New-Object System.Collections.Generic.List[string]
    try {
        $fromLauncher = (& py -3.11 -c "import sys;print(sys.executable)" 2>$null | Select-Object -First 1)
        if ($fromLauncher) { $candidates.Add([string]$fromLauncher) }
    } catch {}
    if ($env:LOCALAPPDATA) {
        $candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'))
    }
    try {
        $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($cmd) { $candidates.Add($cmd.Source) }
    } catch {}
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Python311 $candidate) { return $candidate }
    }
    return $null
}

try {
    $script:AppRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    Set-Location -LiteralPath $script:AppRoot

    if (-not $env:LOCALAPPDATA) {
        $env:LOCALAPPDATA = Join-Path $env:USERPROFILE 'AppData\Local'
    }
    $userData = Join-Path $env:LOCALAPPDATA 'BioIntelAI\UserData'
    $logDir = Join-Path $userData 'runtime_logs'
    $shortTemp = Join-Path $env:LOCALAPPDATA 'B97T'
    New-Item -ItemType Directory -Force -Path $logDir,$shortTemp | Out-Null
    $script:LogPath = Join-Path $logDir ('step97-install-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')

    $env:BIOINTEL_USER_DATA_DIR = $userData
    $env:BIOINTEL_TOOLS_HOME = Join-Path $env:LOCALAPPDATA 'BioIntelAI\Tools'
    $env:BIOINTEL_REFERENCE_ASSETS_DIR = Join-Path $env:LOCALAPPDATA 'BioIntelAI\ReferenceAssets'
    $env:BIOINTEL_SHORT_TEMP = $shortTemp
    $env:TEMP = $shortTemp
    $env:TMP = $shortTemp
    $env:PYTHONPATH = Join-Path $script:AppRoot 'src'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:PIP_NO_INPUT = '1'
    $env:PIP_NO_CACHE_DIR = '1'

    Write-Host '============================================================' -ForegroundColor Green
    Write-Host 'BioIntel AI Step 97 - Path-Safe Offline Installation' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host "Application folder: $script:AppRoot"
    Write-Host "Log file: $script:LogPath"

    Write-Step '[1/8] Checking extracted package...'
    $required = @(
        'app.py',
        'requirements.lock',
        'requirements.lock.sha256',
        'requirements-windows-cp311-offline.lock',
        'scripts\bootstrap.py',
        'scripts\verify_dependency_lock.py',
        'scripts\verify_windows_wheelhouse.py',
        'scripts\step97_self_test.py',
        'wheelhouse\windows-cp311-x64\MANIFEST_SHA256.txt'
    )
    $missing = @()
    foreach ($relative in $required) {
        $full = Join-Path $script:AppRoot $relative
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { $missing += $relative }
    }
    if ($missing.Count -gt 0) {
        throw ('Package is incomplete. Missing: ' + ($missing -join ', ') + '. Extract all four ZIP parts into the same destination.')
    }

    Write-Step '[2/8] Finding Python 3.11 x64...'
    $python = Find-Python311
    if (-not $python) {
        throw 'Python 3.11 x64 was not found. Install Python 3.11 x64, then rerun INSTALL_WINDOWS.bat.'
    }
    Write-Host "Python: $python"

    Write-Step '[3/8] Checking free disk space and writable folders...'
    foreach ($name in @('data','reports','workspace','exports','projects','runtime_logs','cache')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $userData $name) | Out-Null
    }
    $driveRoot = [IO.Path]::GetPathRoot($script:AppRoot)
    $driveName = $driveRoot.TrimEnd('\').TrimEnd(':')
    $free = (Get-PSDrive -Name $driveName).Free
    Write-Host ('Free disk space: {0:N2} GB' -f ($free / 1GB))
    if ($free -lt 3GB) { throw 'At least 3 GB free disk space is required.' }
    $probe = Join-Path $userData '.install-write-probe'
    Set-Content -LiteralPath $probe -Value 'ok' -Encoding UTF8
    Remove-Item -LiteralPath $probe -Force

    Write-Step '[4/8] Verifying dependency locks without absolute-path arguments...'
    Invoke-Checked -FilePath $python -Arguments @('scripts\verify_dependency_lock.py','--root','.')
    Invoke-Checked -FilePath $python -Arguments @('scripts\verify_windows_wheelhouse.py','--root','.')

    Write-Step '[5/8] Preparing a clean Python environment...'
    $venv = Join-Path $script:AppRoot '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $removeVenv = $ForceRepair.IsPresent
    if (Test-Path -LiteralPath $venv) {
        if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
            $removeVenv = $true
        }
        elseif (-not (Test-Python311 $venvPython)) {
            $removeVenv = $true
        }
    }
    if ($removeVenv -and (Test-Path -LiteralPath $venv)) {
        Write-Host 'Removing incomplete or incompatible .venv...'
        Remove-Item -LiteralPath $venv -Recurse -Force
    }

    Write-Step '[6/8] Installing 102 bundled offline wheels...'
    try {
        Invoke-Checked -FilePath $python -Arguments @('scripts\bootstrap.py','--offline')
    }
    catch {
        if (Test-Path -LiteralPath $venv) {
            Write-Host 'First environment attempt failed; rebuilding .venv once...' -ForegroundColor Yellow
            Remove-Item -LiteralPath $venv -Recurse -Force
            Invoke-Checked -FilePath $python -Arguments @('scripts\bootstrap.py','--offline')
        }
        else { throw }
    }
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw 'Virtual-environment Python was not created.'
    }
    Invoke-Checked -FilePath $venvPython -Arguments @('-m','pip','check')

    Write-Step '[7/8] Running installation self-test...'
    $selfTest = Join-Path $userData 'reports\step97-install-self-test.json'
    Invoke-Checked -FilePath $venvPython -Arguments @('scripts\step97_self_test.py','--root','.','--output',$selfTest)

    Write-Step '[8/8] Finalizing installation...'
    $marker = Join-Path $script:AppRoot '.biointel_step97_installed'
    Set-Content -LiteralPath $marker -Value ((Get-Date).ToString('o')) -Encoding UTF8

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host 'INSTALLATION COMPLETE' -ForegroundColor Green
    Write-Host 'Run RUN_BOTH_WINDOWS.bat to open BioIntel AI.' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host 'INSTALLATION FAILED' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    if ($script:LogPath) { Write-Host "Log file: $script:LogPath" }
    exit 1
}
