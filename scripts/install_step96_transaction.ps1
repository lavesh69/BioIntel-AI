param(
    [Parameter(Mandatory=$true)][string]$StageRoot,
    [string]$InstallRoot = "$env:LOCALAPPDATA\B96",
    [string]$UserDataRoot = "$env:LOCALAPPDATA\BioIntelAI\UserData",
    [string]$BackupRoot = "$env:USERPROFILE\Documents\BioIntel AI Backups"
)
$ErrorActionPreference = "Stop"
$StageRoot = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($StageRoot))
$InstallRoot = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($InstallRoot))
$UserDataRoot = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($UserDataRoot))
$BackupRoot = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($BackupRoot))
$StagedApp = Join-Path $StageRoot "BioIntel-AI"
$ActiveApp = Join-Path $InstallRoot "BioIntel-AI"
$PreviousApp = Join-Path $InstallRoot "BioIntel-AI.previous"
$Persistent = @("data","reports","workspace","exports","projects")
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $BackupRoot ("BioIntel-Step96-" + $Stamp + "-" + [guid]::NewGuid().ToString("N").Substring(0,8))
$Journal = Join-Path $InstallRoot "step96-install-journal.json"

function Hash-Tree([string]$Root) {
    $Rows = @()
    if (Test-Path -LiteralPath $Root) {
        $Rows = Get-ChildItem -LiteralPath $Root -File -Recurse -Force | Where-Object {$_.Name -ne "BIOINTEL_BACKUP_MANIFEST.json"} | Sort-Object FullName | ForEach-Object {
            [pscustomobject]@{path=$_.FullName.Substring($Root.Length).TrimStart('\'); size_bytes=$_.Length; sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
        }
    }
    return @($Rows)
}
function Write-Journal([string]$State, [hashtable]$Extra=@{}) {
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    $Payload = @{schema="biointel.step96.install-journal.v2"; state=$State; updated_at=(Get-Date).ToUniversalTime().ToString("o"); active_app=$ActiveApp; previous_app=$PreviousApp; user_data=$UserDataRoot; backup=$Backup}
    foreach($Key in $Extra.Keys){$Payload[$Key]=$Extra[$Key]}
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Journal -Encoding UTF8
}
function Restore-UserDataMirror {
    foreach($Name in $Persistent){
        $From=Join-Path $Backup $Name
        $To=Join-Path $UserDataRoot $Name
        if(Test-Path -LiteralPath $To){Remove-Item -LiteralPath $To -Recurse -Force}
        if(Test-Path -LiteralPath $From){Copy-Item -LiteralPath $From -Destination $To -Recurse -Force}
        else{New-Item -ItemType Directory -Force -Path $To | Out-Null}
    }
}
function Restore-OnFailure {
    Write-Host "Restoring previous installation and exact UserData backup..." -ForegroundColor Yellow
    if (Test-Path -LiteralPath $ActiveApp) { Remove-Item -LiteralPath $ActiveApp -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $PreviousApp) { Move-Item -LiteralPath $PreviousApp -Destination $ActiveApp -Force }
    if (Test-Path -LiteralPath $Backup) { Restore-UserDataMirror }
    Write-Journal "rolled_back"
}
try {
    if (-not (Test-Path -LiteralPath $StagedApp)) { throw "Staged BioIntel-AI directory is missing: $StagedApp" }
    foreach($Required in @("VERSION","app.py","INSTALL_WINDOWS.bat","scripts\verify_windows_wheelhouse.py")){
        if(-not(Test-Path -LiteralPath (Join-Path $StagedApp $Required))){throw "Staged release is missing $Required"}
    }
    $Version=(Get-Content -LiteralPath (Join-Path $StagedApp "VERSION") -Raw).Trim()
    if($Version -ne "9.6.0"){throw "Expected staged version 9.6.0, found $Version"}
    New-Item -ItemType Directory -Force -Path $InstallRoot,$UserDataRoot,$BackupRoot | Out-Null
    Write-Journal "staging_verified"

    New-Item -ItemType Directory -Force -Path $Backup | Out-Null
    foreach($Name in $Persistent){
        $Source=Join-Path $UserDataRoot $Name
        if(Test-Path -LiteralPath $Source){Copy-Item -LiteralPath $Source -Destination (Join-Path $Backup $Name) -Recurse -Force}
    }
    $Files=Hash-Tree $Backup
    @{schema="biointel.user-data-backup.v2"; created_at_utc=(Get-Date).ToUniversalTime().ToString("o"); source_root=$UserDataRoot; persistent_directories=$Persistent; file_count=$Files.Count; files=$Files} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Backup "BIOINTEL_BACKUP_MANIFEST.json") -Encoding UTF8
    foreach($Row in $Files){
        $Path=Join-Path $Backup $Row.path
        if(-not(Test-Path -LiteralPath $Path)){throw "Backup verification missing file: $($Row.path)"}
        $Hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
        if($Hash -ne $Row.sha256){throw "Backup verification hash mismatch: $($Row.path)"}
    }
    Write-Journal "backup_verified" @{backup_file_count=$Files.Count}

    foreach($Name in $Persistent){
        $Seed=Join-Path $StagedApp $Name
        $Store=Join-Path $UserDataRoot $Name
        New-Item -ItemType Directory -Force -Path $Store | Out-Null
        if(Test-Path -LiteralPath $Seed){
            & robocopy.exe $Seed $Store /E /XO /XN /XC /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
            if($LASTEXITCODE -ge 8){throw "Seed merge failed for $Name (robocopy $LASTEXITCODE)"}
            Remove-Item -LiteralPath $Seed -Recurse -Force
        }
        cmd.exe /d /c "mklink /J `"$Seed`" `"$Store`"" | Out-Null
        if($LASTEXITCODE -ne 0 -or -not(Test-Path -LiteralPath $Seed)){throw "Could not create persistent junction for $Name"}
    }
    Set-Content -LiteralPath (Join-Path $StagedApp ".biointel-user-data-root") -Value $UserDataRoot -Encoding UTF8
    Write-Journal "user_data_linked"

    if (Test-Path -LiteralPath $PreviousApp) { Remove-Item -LiteralPath $PreviousApp -Recurse -Force }
    if (Test-Path -LiteralPath $ActiveApp) { Move-Item -LiteralPath $ActiveApp -Destination $PreviousApp -Force }
    Move-Item -LiteralPath $StagedApp -Destination $ActiveApp -Force
    Write-Journal "activated" @{version="9.6.0"}
    Write-Output $ActiveApp
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Restore-OnFailure
    exit 1
}
