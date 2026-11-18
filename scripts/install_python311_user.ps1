param(
  [switch]$Quiet,
  [string]$PackageRoot = ""
)
$ErrorActionPreference = 'Stop'
$targetPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'

function Test-Python3119([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
  try {
    & $Path -c "import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==64 else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

function Test-OfficialInstaller([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
  try {
    $sig = Get-AuthenticodeSignature -LiteralPath $Path
    return ($sig.Status -eq 'Valid' -and $sig.SignerCertificate.Subject -match 'Python Software Foundation')
  } catch { return $false }
}

if (Test-Python3119 $targetPython) { Write-Output $targetPython; exit 0 }

$downloadDir = Join-Path $env:LOCALAPPDATA 'BioIntelAI\Downloads'
New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
$cachedInstaller = Join-Path $downloadDir 'python-3.11.9-amd64.exe'
$partial = "$cachedInstaller.partial"
$url = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
$installer = $null

$localCandidates = @()
if ($PackageRoot) {
  $localCandidates += (Join-Path $PackageRoot 'runtime\python\python-3.11.9-amd64.exe')
  $localCandidates += (Join-Path $PackageRoot 'python-3.11.9-amd64.exe')
}
$localCandidates += $cachedInstaller
foreach ($candidate in $localCandidates) {
  if (Test-OfficialInstaller $candidate) {
    $installer = $candidate
    break
  }
}

try {
  if (-not $installer) {
    Remove-Item -LiteralPath $cachedInstaller,$partial -Force -ErrorAction SilentlyContinue
    if (-not $Quiet) { Write-Host 'Downloading official signed Python 3.11.9 x64 installer...' }
    try {
      Start-BitsTransfer -Source $url -Destination $partial -ErrorAction Stop
    } catch {
      Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $partial -ErrorAction Stop
    }
    Move-Item -LiteralPath $partial -Destination $cachedInstaller -Force
    if (-not (Test-OfficialInstaller $cachedInstaller)) {
      throw 'Downloaded file does not have a valid Python Software Foundation signature.'
    }
    $installer = $cachedInstaller
  }

  if (-not $Quiet) { Write-Host 'Installing 64-bit Python 3.11.x for current Windows user...' }
  $arguments = @('/quiet','InstallAllUsers=0','PrependPath=0','Include_launcher=1','Include_test=0','Include_pip=1','Shortcuts=0')
  $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
  if ($process.ExitCode -ne 0) { throw "Python installer exited with code $($process.ExitCode)." }
} catch {
  Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
  throw "Python 3.11.9 installation failed: $($_.Exception.Message) BioIntel files and project data are intact. Connect to internet or place the official signed python-3.11.9-amd64.exe beside the package and run INSTALL_WINDOWS.bat again."
}

if (Test-Python3119 $targetPython) { Write-Output $targetPython; exit 0 }
$locator = Join-Path $PSScriptRoot 'find_python311_windows.ps1'
$found = & powershell -NoProfile -ExecutionPolicy Bypass -File $locator 2>$null | Select-Object -First 1
if ($found -and (Test-Python3119 $found)) { Write-Output $found; exit 0 }
throw 'Python installation finished but 64-bit CPython 3.11.x could not be located. Restart Windows once, then run INSTALL_WINDOWS.bat again.'
