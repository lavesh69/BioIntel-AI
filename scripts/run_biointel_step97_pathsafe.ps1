$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Get-FreePort([int]$Start, [int]$End) {
    for ($port = $Start; $port -le $End; $port++) {
        $listener = $null
        try {
            $listener = New-Object System.Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $port)
            $listener.Start()
            return $port
        }
        catch {}
        finally { if ($listener) { try { $listener.Stop() } catch {} } }
    }
    throw "No free localhost port is available between $Start and $End."
}

function Test-Url([string]$Url, [int]$TimeoutSeconds = 2) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSeconds
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    }
    catch { return $false }
}

function Wait-Url([string]$Url, [System.Diagnostics.Process]$Process, [int]$Seconds = 120) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process -and $Process.HasExited) { return $false }
        if (Test-Url $Url 2) { return $true }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

try {
    $appRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    Set-Location -LiteralPath $appRoot
    if (-not $env:LOCALAPPDATA) { $env:LOCALAPPDATA = Join-Path $env:USERPROFILE 'AppData\Local' }
    $userData = Join-Path $env:LOCALAPPDATA 'BioIntelAI\UserData'
    $runtimeDir = Join-Path $userData 'runtime_logs'
    $runtimeTemp = Join-Path $env:LOCALAPPDATA 'B97T\runtime'
    New-Item -ItemType Directory -Force -Path $runtimeDir,$runtimeTemp | Out-Null

    $env:BIOINTEL_USER_DATA_DIR = $userData
    $env:BIOINTEL_TOOLS_HOME = Join-Path $env:LOCALAPPDATA 'BioIntelAI\Tools'
    $env:BIOINTEL_REFERENCE_ASSETS_DIR = Join-Path $env:LOCALAPPDATA 'BioIntelAI\ReferenceAssets'
    $env:BIOINTEL_RUNTIME_TEMP = $runtimeTemp
    $env:TEMP = $runtimeTemp
    $env:TMP = $runtimeTemp
    $env:MPLCONFIGDIR = Join-Path $userData 'cache\matplotlib'
    $env:PYTHONPATH = Join-Path $appRoot 'src'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = 'false'

    $python = Join-Path $appRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'The BioIntel AI environment is missing. Run INSTALL_WINDOWS.bat first.'
    }

    $statePath = Join-Path $runtimeDir 'step97-running.json'
    if (Test-Path -LiteralPath $statePath) {
        try {
            $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
            $uiAlive = $false
            $apiAlive = $false
            try { $uiProcess = Get-Process -Id ([int]$state.ui_pid) -ErrorAction Stop; $uiAlive = -not $uiProcess.HasExited } catch {}
            try { $apiProcess = Get-Process -Id ([int]$state.api_pid) -ErrorAction Stop; $apiAlive = -not $apiProcess.HasExited } catch {}
            if ($uiAlive -and $apiAlive -and (Test-Url ([string]$state.ui_url)) -and (Test-Url ([string]$state.api_url))) {
                Write-Host 'BioIntel AI is already running. Opening the existing session...' -ForegroundColor Green
                Start-Process ([string]$state.ui_url)
                exit 0
            }
        } catch {}
        Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    }

    Write-Host '[1/4] Running startup preflight...' -ForegroundColor Cyan
    Push-Location -LiteralPath $appRoot
    try {
        & $python 'scripts\step97_runtime_preflight.py' '--root' '.' '--output' (Join-Path $runtimeDir 'step97-runtime-preflight.json') *> (Join-Path $runtimeDir 'step97-preflight.log')
        if ($LASTEXITCODE -ne 0) {
            Get-Content -LiteralPath (Join-Path $runtimeDir 'step97-preflight.log') -Tail 80 -ErrorAction SilentlyContinue
            throw 'BioIntel AI startup preflight failed. Run REPAIR_BIOINTEL_STEP97_WINDOWS.bat.'
        }
    }
    finally { Pop-Location }

    $uiPort = Get-FreePort 8501 8599
    $apiPort = Get-FreePort 8000 8099
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $apiOut = Join-Path $runtimeDir "step97-api-$stamp.out.log"
    $apiErr = Join-Path $runtimeDir "step97-api-$stamp.err.log"
    $uiOut = Join-Path $runtimeDir "step97-ui-$stamp.out.log"
    $uiErr = Join-Path $runtimeDir "step97-ui-$stamp.err.log"

    Write-Host "[2/4] Starting API on 127.0.0.1:$apiPort..." -ForegroundColor Cyan
    $apiArgs = @('-m','uvicorn','biointel.api.main:app','--app-dir','src','--host','127.0.0.1','--port',[string]$apiPort)
    $api = Start-Process -FilePath $python -ArgumentList $apiArgs -WorkingDirectory $appRoot -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -PassThru -WindowStyle Hidden

    Write-Host "[3/4] Starting UI on 127.0.0.1:$uiPort..." -ForegroundColor Cyan
    $uiArgs = @('-m','streamlit','run','app.py','--server.address','127.0.0.1','--server.port',[string]$uiPort,'--server.fileWatcherType','none','--server.runOnSave','false','--browser.gatherUsageStats','false','--server.headless','true')
    $ui = Start-Process -FilePath $python -ArgumentList $uiArgs -WorkingDirectory $appRoot -RedirectStandardOutput $uiOut -RedirectStandardError $uiErr -PassThru -WindowStyle Hidden

    $apiUrl = "http://127.0.0.1:$apiPort/openapi.json"
    $uiHealth = "http://127.0.0.1:$uiPort/_stcore/health"
    $uiUrl = "http://127.0.0.1:$uiPort"

    Write-Host '[4/4] Waiting for UI and API readiness...' -ForegroundColor Cyan
    $apiReady = Wait-Url $apiUrl $api 120
    $uiReady = Wait-Url $uiHealth $ui 120
    if (-not ($apiReady -and $uiReady)) {
        try { if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force } } catch {}
        try { if ($ui -and -not $ui.HasExited) { Stop-Process -Id $ui.Id -Force } } catch {}
        Write-Host '--- API error log ---' -ForegroundColor Yellow
        Get-Content -LiteralPath $apiErr -Tail 80 -ErrorAction SilentlyContinue
        Write-Host '--- UI error log ---' -ForegroundColor Yellow
        Get-Content -LiteralPath $uiErr -Tail 80 -ErrorAction SilentlyContinue
        throw 'UI or API did not become ready. The browser was not opened.'
    }

    $state = [ordered]@{
        generated_at = (Get-Date).ToString('o')
        app_root = $appRoot
        ui_pid = $ui.Id
        api_pid = $api.Id
        ui_port = $uiPort
        api_port = $apiPort
        ui_url = $uiUrl
        api_url = $apiUrl
        ui_error_log = $uiErr
        api_error_log = $apiErr
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

    Write-Host ''
    Write-Host 'BioIntel AI is ready.' -ForegroundColor Green
    Write-Host "UI:  $uiUrl"
    Write-Host "API: http://127.0.0.1:$apiPort/docs"
    Start-Process $uiUrl
    exit 0
}
catch {
    Write-Host ''
    Write-Host 'BIOINTEL AI COULD NOT START' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Write-Host "Runtime logs: $runtimeDir"
    exit 1
}
