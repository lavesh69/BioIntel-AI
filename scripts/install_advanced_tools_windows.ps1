param(
    [string]$ToolsHome = "$env:LOCALAPPDATA\BioIntelAI\Tools",
    [ValidateSet("Menu", "Native", "WSL", "All")]
    [string]$Mode = "Menu",
    [string]$WslDistro = "Ubuntu"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ToolsHome = [Environment]::ExpandEnvironmentVariables($ToolsHome)
$Cache = Join-Path $ToolsHome "cache"
$Native = Join-Path $ToolsHome "native"
$Bin = Join-Path $ToolsHome "bin"
$State = Join-Path $ToolsHome "state"
$Logs = Join-Path $ToolsHome "logs"
foreach ($path in @($ToolsHome, $Cache, $Native, $Bin, $State, $Logs)) { New-Item -ItemType Directory -Path $path -Force | Out-Null }
$Log = Join-Path $Logs ("install-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
Start-Transcript -Path $Log -Force | Out-Null

function Write-Stage([string]$Text) { Write-Host "`n=== $Text ===" -ForegroundColor Cyan }
function Download-File([string]$Url, [string]$Name, [string]$ExpectedSha256 = "") {
    $Target = Join-Path $Cache $Name
    if (-not (Test-Path $Target)) {
        Write-Host "Downloading $Name"
        Invoke-WebRequest -Uri $Url -OutFile $Target -UseBasicParsing -Headers @{"User-Agent"="BioIntel-AI-Step157"}
    } else { Write-Host "Using cached $Name" }
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Target).Hash.ToLowerInvariant()
    if ($ExpectedSha256 -and $Hash -ne $ExpectedSha256.ToLowerInvariant()) { throw "SHA-256 mismatch for $Name" }
    return @{ Path=$Target; Sha256=$Hash; Url=$Url }
}
function Expand-Package([string]$Archive, [string]$Destination) {
    if (Test-Path $Destination) { Remove-Item -Recurse -Force $Destination }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    if ($Archive.ToLowerInvariant().EndsWith(".zip")) {
        Expand-Archive -LiteralPath $Archive -DestinationPath $Destination -Force
    } elseif ($Archive.ToLowerInvariant().EndsWith(".tar.gz") -or $Archive.ToLowerInvariant().EndsWith(".tgz")) {
        & tar.exe -xzf $Archive -C $Destination
        if ($LASTEXITCODE -ne 0) { throw "tar extraction failed: $Archive" }
    } else { throw "Unsupported package format: $Archive" }
}
function GitHub-Asset([string]$Repository, [string]$Tag, [string]$Pattern) {
    $Api = if ($Tag -eq "latest") { "https://api.github.com/repos/$Repository/releases/latest" } else { "https://api.github.com/repos/$Repository/releases/tags/$Tag" }
    $Release = Invoke-RestMethod -Uri $Api -Headers @{"User-Agent"="BioIntel-AI-Step157"; "Accept"="application/vnd.github+json"}
    $Asset = $Release.assets | Where-Object { $_.name -match $Pattern } | Select-Object -First 1
    if (-not $Asset) { throw "No GitHub release asset matched $Pattern in $Repository $Tag" }
    return $Asset
}
function Find-One([string]$Root, [string[]]$Names) {
    foreach ($Name in $Names) {
        $Hit = Get-ChildItem -LiteralPath $Root -Recurse -File -Filter $Name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($Hit) { return $Hit.FullName }
    }
    return $null
}
function Write-Cmd([string]$Name, [string]$Body) {
    $Path = Join-Path $Bin ($Name + ".cmd")
    Set-Content -LiteralPath $Path -Value ("@echo off`r`n" + $Body + "`r`n") -Encoding ASCII
}
function Quote-Cmd([string]$Path) { return '"' + $Path + '"' }

function Install-Java21 {
    $Existing = Find-One (Join-Path $Native "java") @("java.exe")
    if ($Existing) { return $Existing }
    Write-Stage "Portable Java 21 runtime"
    $Assets = Invoke-RestMethod -Uri "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jre&os=windows&vendor=eclipse" -Headers @{"User-Agent"="BioIntel-AI-Step157"}
    $Package = $Assets[0].binary.package
    $Downloaded = Download-File $Package.link ([IO.Path]::GetFileName($Package.name)) $Package.checksum
    Expand-Package $Downloaded.Path (Join-Path $Native "java")
    $Java = Find-One (Join-Path $Native "java") @("java.exe")
    if (-not $Java) { throw "Portable Java executable not found after extraction" }
    return $Java
}

function Install-NativeCore {
    Write-Stage "Native portable core"
    $Records = @()

    $Blast = Download-File "https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/ncbi-blast-2.17.0+-x64-win64.tar.gz" "ncbi-blast-2.17.0+-x64-win64.tar.gz"
    Expand-Package $Blast.Path (Join-Path $Native "blast")
    $BlastBin = Split-Path (Find-One (Join-Path $Native "blast") @("blastn.exe")) -Parent
    foreach ($Name in @("blastn","blastp","blastx","tblastn","tblastx","makeblastdb","blastdbcmd")) { Write-Cmd $Name ((Quote-Cmd (Join-Path $BlastBin ($Name + ".exe"))) + " %*") }
    $Records += @{tool="NCBI BLAST+"; sha256=$Blast.Sha256; source=$Blast.Url}

    $Mafft = Download-File "https://mafft.cbrc.jp/alignment/software/mafft-7.526-win64-signed.zip" "mafft-7.526-win64-signed.zip"
    Expand-Package $Mafft.Path (Join-Path $Native "mafft")
    $MafftCmd = Find-One (Join-Path $Native "mafft") @("mafft.bat","mafft.cmd")
    if (-not $MafftCmd) { throw "MAFFT launcher not found" }
    Write-Cmd "mafft" ((Quote-Cmd $MafftCmd) + " %*")
    $Records += @{tool="MAFFT"; sha256=$Mafft.Sha256; source=$Mafft.Url}

    $BowtieAsset = GitHub-Asset "BenLangmead/bowtie2" "v2.5.5" "windows.*x86_64.*\\.zip$|win.*\\.zip$"
    $Bowtie = Download-File $BowtieAsset.browser_download_url $BowtieAsset.name ($BowtieAsset.digest -replace '^sha256:','')
    Expand-Package $Bowtie.Path (Join-Path $Native "bowtie2")
    foreach ($Name in @("bowtie2","bowtie2-build","bowtie2-inspect")) {
        $Exe = Find-One (Join-Path $Native "bowtie2") @(($Name + ".exe"),($Name + ".bat"),($Name + ".cmd"))
        if ($Exe) { Write-Cmd $Name ((Quote-Cmd $Exe) + " %*") }
    }
    $Records += @{tool="Bowtie 2"; sha256=$Bowtie.Sha256; source=$Bowtie.Url}

    $IqAsset = GitHub-Asset "iqtree/iqtree3" "v3.1.3" "Windows\\.zip$"
    $Iq = Download-File $IqAsset.browser_download_url $IqAsset.name ($IqAsset.digest -replace '^sha256:','')
    Expand-Package $Iq.Path (Join-Path $Native "iqtree")
    $IqExe = Find-One (Join-Path $Native "iqtree") @("iqtree3.exe","iqtree.exe")
    if (-not $IqExe) { throw "IQ-TREE executable not found" }
    foreach ($Name in @("iqtree3","iqtree2","iqtree")) { Write-Cmd $Name ((Quote-Cmd $IqExe) + " %*") }
    $Records += @{tool="IQ-TREE"; sha256=$Iq.Sha256; source=$Iq.Url}

    $Java = Install-Java21
    $Fastqc = Download-File "https://www.bioinformatics.babraham.ac.uk/projects/fastqc/fastqc_v0.12.1.zip" "fastqc_v0.12.1.zip"
    Expand-Package $Fastqc.Path (Join-Path $Native "fastqc")
    $FastqcJar = Find-One (Join-Path $Native "fastqc") @("fastqc.jar")
    if (-not $FastqcJar) { throw "FastQC jar not found" }
    $FastqcDir = Split-Path $FastqcJar -Parent
    Write-Cmd "fastqc" ((Quote-Cmd $Java) + " -Xmx2g -Dfastqc.dir=" + (Quote-Cmd $FastqcDir) + " -cp " + (Quote-Cmd $FastqcJar) + " uk.ac.babraham.FastQC.FastQCApplication %*")
    $Records += @{tool="FastQC"; sha256=$Fastqc.Sha256; source=$Fastqc.Url}

    $Snp = Download-File "https://snpeff-public.s3.amazonaws.com/versions/snpEff_latest_core.zip" "snpEff_latest_core.zip"
    Expand-Package $Snp.Path (Join-Path $Native "snpeff")
    $SnpJar = Find-One (Join-Path $Native "snpeff") @("snpEff.jar")
    $SiftJar = Find-One (Join-Path $Native "snpeff") @("SnpSift.jar")
    if (-not $SnpJar) { throw "SnpEff jar not found" }
    Write-Cmd "snpEff" ((Quote-Cmd $Java) + " -Xmx4g -jar " + (Quote-Cmd $SnpJar) + " %*")
    if ($SiftJar) { Write-Cmd "snpSift" ((Quote-Cmd $Java) + " -Xmx4g -jar " + (Quote-Cmd $SiftJar) + " %*") }
    $Records += @{tool="SnpEff"; sha256=$Snp.Sha256; source=$Snp.Url}

    $VinaAsset = GitHub-Asset "ccsb-scripps/AutoDock-Vina" "latest" "windows.*x86_64.*\\.exe$|win.*64.*\\.exe$"
    $Vina = Download-File $VinaAsset.browser_download_url $VinaAsset.name ($VinaAsset.digest -replace '^sha256:','')
    $VinaDir = Join-Path $Native "vina"
    New-Item -ItemType Directory -Path $VinaDir -Force | Out-Null
    $VinaExe = Join-Path $VinaDir "vina.exe"
    Copy-Item -LiteralPath $Vina.Path -Destination $VinaExe -Force
    Write-Cmd "vina" ((Quote-Cmd $VinaExe) + " %*")
    $Records += @{tool="AutoDock Vina"; sha256=$Vina.Sha256; source=$Vina.Url}

    $Payload = @{schema="biointel.native-tools.v1"; installed_at=(Get-Date).ToUniversalTime().ToString("o"); tools=$Records}
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $State "native-tools.json") -Encoding UTF8
}

function Install-WslSuite {
    Write-Stage "WSL/Bioconda full suite"
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { throw "WSL is not available. Enable WSL 2 and install Ubuntu first." }
    $List = (& wsl.exe -l -q) -replace "`0", ""
    if (-not ($List | Where-Object { $_.Trim() -eq $WslDistro })) { throw "WSL distribution '$WslDistro' is not installed. Run: wsl --install -d Ubuntu" }

    $Packages = @(
        "mafft","hmmer","mmseqs2","minimap2","samtools","bcftools","fastp","cutadapt","multiqc","mosdepth","picard","salmon","kallisto",
        "bowtie2","kraken2","bracken","metaphlan","humann","fastani","mash","prokka",
        "bakta","ncbi-amrfinderplus","ensembl-vep","primer3","blast",
        "flye","hifiasm","canu","quast","busco","odgi","vg","minigraph",
        "macs2","deeptools","plink2","regenie","whatshap","sniffles","expansionhunter",
        "openms","comet-ms","msgf_plus","anarci","igblast","r-mats","majiq","suppa","openbabel","interproscan",
        "seqkit","diamond","foldseek","nextflow","snakemake-minimal"
    ) -join " "
    $Script = @"
set -euo pipefail
mkdir -p ~/.local/bin ~/.biointel
if [ ! -x ~/.local/bin/micromamba ]; then
  curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj -C ~/.local/bin --strip-components=1 bin/micromamba
fi
export MAMBA_ROOT_PREFIX=~/.biointel/mamba
~/.local/bin/micromamba create -y -n biointel-tools -c conda-forge -c bioconda --strict-channel-priority $Packages
~/.local/bin/micromamba run -n biointel-tools amrfinder_update || true
~/.local/bin/micromamba list -n biointel-tools --json > ~/.biointel/installed-packages.json
"@
    & wsl.exe -d $WslDistro -- bash -lc $Script
    if ($LASTEXITCODE -ne 0) { throw "WSL/Bioconda installation failed" }

    $Tools = @("mafft","hmmscan","hmmsearch","hmmbuild","hmmpress","mmseqs","minimap2","samtools","bcftools","fastp","cutadapt","multiqc","mosdepth","picard","salmon","kallisto","bowtie2","kraken2","kraken2-build","bracken","metaphlan","humann","fastANI","mash","prokka","bakta","amrfinder","vep","primer3_core","blastn","blastp","flye","hifiasm","canu","quast.py","quast","busco","odgi","vg","minigraph","macs2","bamCoverage","plink2","regenie","whatshap","sniffles","ExpansionHunter","FileInfo","FeatureFinderMetabo","comet","MSGFPlus","ANARCI","igblastn","interproscan.sh","rmats.py","majiq","suppa.py","obabel","seqkit","diamond","foldseek","nextflow","snakemake")
    foreach ($Name in $Tools) {
        $Body = "wsl.exe -d " + $WslDistro + " -- bash -lc " + ('"export MAMBA_ROOT_PREFIX=~/.biointel/mamba; ~/.local/bin/micromamba run -n biointel-tools ' + $Name + ' \"$@\"" -- %*')
        Write-Cmd $Name $Body
    }
    @{schema="biointel.wsl-tools.v1"; distro=$WslDistro; environment="biointel-tools"; installed_at=(Get-Date).ToUniversalTime().ToString("o"); tools=$Tools} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $State "wsl-tools.json") -Encoding UTF8
}

try {
    if ($Mode -eq "Menu") {
        Write-Host "1. Native portable core only"
        Write-Host "2. Full WSL/Bioconda suite only"
        Write-Host "3. Both layers"
        Write-Host "4. Exit"
        $Choice = Read-Host "Choose 1-4"
        $Mode = switch ($Choice) { "1" {"Native"} "2" {"WSL"} "3" {"All"} default {"Exit"} }
    }
    if ($Mode -eq "Exit") { Stop-Transcript | Out-Null; exit 0 }
    if ($Mode -in @("Native","All")) { Install-NativeCore }
    if ($Mode -in @("WSL","All")) { Install-WslSuite }
    Write-Host "`nTool installation completed." -ForegroundColor Green
    Stop-Transcript | Out-Null
    exit 0
} catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}
