$ErrorActionPreference = 'SilentlyContinue'
$candidates = New-Object System.Collections.Generic.List[string]
function Add-Candidate([string]$p) {
  if (-not $p) { return }
  try { $full = [System.IO.Path]::GetFullPath($p) } catch { $full = $p }
  if ($full -match '\\WindowsApps\\python(3)?\.exe$') { return }
  if ((Test-Path -LiteralPath $full -PathType Leaf) -and -not $candidates.Contains($full)) {
    [void]$candidates.Add($full)
  }
}
function Test-Python3119([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
  try {
    & $Path -c "import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==64 else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

@(
  "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
  "$env:USERPROFILE\AppData\Local\Programs\Python\Python311\python.exe",
  "$env:ProgramFiles\Python311\python.exe"
) | ForEach-Object { Add-Candidate $_ }

try {
  $py = & py -3.11 -c "import sys;print(sys.executable)" 2>$null
  if ($LASTEXITCODE -eq 0) { Add-Candidate ($py | Select-Object -First 1) }
} catch {}
try { & where.exe python 2>$null | ForEach-Object { Add-Candidate $_ } } catch {}
try { Get-Command python.exe -All | ForEach-Object { Add-Candidate $_.Source } } catch {}

$registryRoots = @(
  'HKCU:\Software\Python\PythonCore',
  'HKLM:\Software\Python\PythonCore',
  'HKLM:\Software\WOW6432Node\Python\PythonCore'
)
foreach ($baseKey in $registryRoots) {
  try {
    Get-ChildItem -Path $baseKey | Where-Object { $_.PSChildName -like '3.11*' } | ForEach-Object {
      $installKey = Join-Path $_.PSPath 'InstallPath'
      try {
        $base = (Get-Item -Path $installKey).GetValue('')
        if ($base) { Add-Candidate (Join-Path $base 'python.exe') }
        $exe = (Get-Item -Path $installKey).GetValue('ExecutablePath')
        if ($exe) { Add-Candidate $exe }
      } catch {}
    }
  } catch {}
}

@(
  "$env:LOCALAPPDATA\Programs\Python",
  "$env:ProgramFiles\Python311"
) | ForEach-Object {
  if (Test-Path -LiteralPath $_) {
    try { Get-ChildItem -LiteralPath $_ -Filter python.exe -File -Recurse -Depth 3 | ForEach-Object { Add-Candidate $_.FullName } } catch {}
  }
}

foreach ($candidate in $candidates) {
  if (Test-Python3119 $candidate) { Write-Output $candidate; exit 0 }
}
exit 1
