$ErrorActionPreference = "Stop"

function Set-UserValue([string]$Name, [string]$Prompt, [string]$DefaultValue) {
    $current = [Environment]::GetEnvironmentVariable($Name, "User")
    $shown = if ($current) { $current } elseif ($DefaultValue) { $DefaultValue } else { "" }
    $value = Read-Host "$Prompt [$shown]"
    if ([string]::IsNullOrWhiteSpace($value)) { $value = $shown }
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        [Environment]::SetEnvironmentVariable($Name, $value.Trim(), "User")
    }
}

function Set-UserSecret([string]$Name, [string]$Label) {
    $existing = [Environment]::GetEnvironmentVariable($Name, "User")
    $state = if ($existing) { "configured" } else { "missing" }
    $choice = Read-Host "Update $Label? Current status: $state (y/N/clear)"
    if ($choice -eq "clear") {
        [Environment]::SetEnvironmentVariable($Name, $null, "User")
        Write-Host "$Label cleared." -ForegroundColor Yellow
        return
    }
    if ($choice -notmatch '^[Yy]$') { return }
    $secure = Read-Host "Enter $Label" -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if ([string]::IsNullOrWhiteSpace($plain)) { throw "$Label cannot be empty." }
        [Environment]::SetEnvironmentVariable($Name, $plain.Trim(), "User")
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $plain = $null
    }
}

Write-Host "BioIntel AI Step 52 connection setup" -ForegroundColor Cyan
Write-Host "Secrets are stored in your Windows user environment, not inside the project folder." -ForegroundColor Gray

Set-UserSecret "OPENAI_API_KEY" "OpenAI API key"
Set-UserValue "OPENAI_MODEL" "OpenAI model" "gpt-5.5"
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://api.openai.com/v1", "User")
[Environment]::SetEnvironmentVariable("OPENAI_ALLOW_CUSTOM_BASE_URL", "0", "User")
Set-UserValue "OPENAI_PROJECT" "Optional OpenAI project ID (press Enter to keep/skip)" ""
Set-UserValue "OPENAI_ORGANIZATION" "Optional OpenAI organization ID (press Enter to keep/skip)" ""
[Environment]::SetEnvironmentVariable("OPENAI_STORE_RESPONSES", "0", "User")

Set-UserSecret "NCBI_API_KEY" "NCBI API key"
Set-UserValue "NCBI_EMAIL" "NCBI contact email" ""
Set-UserValue "NCBI_TOOL" "NCBI tool name" "BioIntelAI"
Set-UserValue "STRING_CALLER_IDENTITY" "STRING caller identity" "BioIntelAI"

[Environment]::SetEnvironmentVariable("BIOINTEL_INTERNET_ENABLED", "1", "User")
[Environment]::SetEnvironmentVariable("BIOINTEL_ALLOW_PUBLIC_HTTPS", "1", "User")
[Environment]::SetEnvironmentVariable("BIOINTEL_OFFICIAL_HOSTS_ONLY", "1", "User")
[Environment]::SetEnvironmentVariable("BIOINTEL_RESOLVE_DNS", "1", "User")
[Environment]::SetEnvironmentVariable("BIOINTEL_CONNECTED_TIMEOUT", "30", "User")
[Environment]::SetEnvironmentVariable("BIOINTEL_CONNECTED_CONNECT_TIMEOUT", "8", "User")
[Environment]::SetEnvironmentVariable("BIOINTEL_CONNECTED_RETRIES", "3", "User")
[Environment]::SetEnvironmentVariable("BIOINTEL_CONNECTED_CACHE_TTL", "86400", "User")

Write-Host "" 
Write-Host "Configuration saved." -ForegroundColor Green
Write-Host "Close all old BioIntel terminals. Open a NEW terminal and run RUN_STEP52_CONNECTED_WINDOWS.bat." -ForegroundColor Yellow
