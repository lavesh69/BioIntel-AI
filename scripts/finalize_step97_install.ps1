param([string]$InstallRoot = "$env:LOCALAPPDATA\B97")
$ErrorActionPreference="Stop"
$JournalPath=Join-Path $InstallRoot "step97-install-journal.json"
$Payload=@{schema="biointel.step97.install-journal.v2";state="completed";updated_at=(Get-Date).ToUniversalTime().ToString("o")}
if(Test-Path -LiteralPath $JournalPath){
  try{$Existing=Get-Content -LiteralPath $JournalPath -Raw | ConvertFrom-Json; foreach($Property in $Existing.PSObject.Properties){$Payload[$Property.Name]=$Property.Value}}catch{}
}
$Payload["state"]="completed";$Payload["updated_at"]=(Get-Date).ToUniversalTime().ToString("o")
$Payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $JournalPath -Encoding UTF8
Write-Host "Step 97 installation journal finalized." -ForegroundColor Green
