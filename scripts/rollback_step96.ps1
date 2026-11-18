param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\B96",
    [string]$UserDataRoot = "$env:LOCALAPPDATA\BioIntelAI\UserData",
    [string]$BackupRoot = "$env:USERPROFILE\Documents\BioIntel AI Backups",
    [switch]$FailedActivation
)
$ErrorActionPreference="Stop"
$Active=Join-Path $InstallRoot "BioIntel-AI"
$Previous=Join-Path $InstallRoot "BioIntel-AI.previous"
$JournalPath=Join-Path $InstallRoot "step96-install-journal.json"
$Backup=$null
if(Test-Path -LiteralPath $JournalPath){
    try{$Journal=Get-Content -LiteralPath $JournalPath -Raw | ConvertFrom-Json; if($Journal.backup){$Backup=[string]$Journal.backup}}catch{}
}
if(-not $Backup -or -not(Test-Path -LiteralPath $Backup)){
    $Latest=Get-ChildItem -LiteralPath $BackupRoot -Directory -Filter "BioIntel-Step96-*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if($Latest){$Backup=$Latest.FullName}
}
if(-not(Test-Path -LiteralPath $Previous) -and -not $FailedActivation){throw "No previous Step 96 application rollback point exists."}
$Failed=Join-Path $InstallRoot ("BioIntel-AI.failed-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
if(Test-Path -LiteralPath $Active){
    if($FailedActivation){Remove-Item -LiteralPath $Active -Recurse -Force}
    else{Move-Item -LiteralPath $Active -Destination $Failed -Force}
}
if(Test-Path -LiteralPath $Previous){Move-Item -LiteralPath $Previous -Destination $Active -Force}
if($Backup -and (Test-Path -LiteralPath $Backup)){
  foreach($Name in @("data","reports","workspace","exports","projects")){
    $From=Join-Path $Backup $Name; $To=Join-Path $UserDataRoot $Name
    if(Test-Path -LiteralPath $To){Remove-Item -LiteralPath $To -Recurse -Force}
    if(Test-Path -LiteralPath $From){Copy-Item -LiteralPath $From -Destination $To -Recurse -Force}else{New-Item -ItemType Directory -Force -Path $To | Out-Null}
  }
}
@{schema="biointel.step96.install-journal.v2";state=$(if($FailedActivation){"failed_activation_rolled_back"}else{"manual_rollback"});updated_at=(Get-Date).ToUniversalTime().ToString("o");backup=$Backup;failed_app=$(if($FailedActivation){""}else{$Failed})} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $JournalPath -Encoding UTF8
Write-Host "Rollback completed. Application and matching UserData state were restored." -ForegroundColor Green
