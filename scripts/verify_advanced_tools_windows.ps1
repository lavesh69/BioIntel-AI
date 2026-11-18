param([string]$ToolsHome = "$env:LOCALAPPDATA\BioIntelAI\Tools")
$ErrorActionPreference = "Continue"
$ToolsHome = [Environment]::ExpandEnvironmentVariables($ToolsHome)
$Bin = Join-Path $ToolsHome "bin"
$Names = @("blastn","mafft","hmmscan","mmseqs","minimap2","samtools","bcftools","fastqc","fastp","cutadapt","multiqc","mosdepth","picard","salmon","kallisto","bowtie2","kraken2","bracken","metaphlan","humann","fastANI","mash","prokka","bakta","amrfinder","iqtree3","vep","snpEff","primer3_core","vina","macs2","bamCoverage","plink2","regenie","whatshap","sniffles","ExpansionHunter","FileInfo","FeatureFinderMetabo","comet","MSGFPlus","ANARCI","igblastn","interproscan.sh","rmats.py","majiq","suppa.py","obabel")
$Rows = foreach ($Name in $Names) {
    $Local = Join-Path $Bin ($Name + ".cmd")
    $System = Get-Command $Name -ErrorAction SilentlyContinue
    [pscustomobject]@{Tool=$Name; AppLocal=(Test-Path $Local); SystemPath=[bool]$System; Path=if(Test-Path $Local){$Local}elseif($System){$System.Source}else{""}}
}
$Rows | Format-Table -AutoSize
$Available = @($Rows | Where-Object {$_.AppLocal -or $_.SystemPath}).Count
Write-Host "Available launchers: $Available / $($Rows.Count)"
$Out = Join-Path $ToolsHome "state\verification.json"
New-Item -ItemType Directory -Path (Split-Path $Out -Parent) -Force | Out-Null
@{schema="biointel.step157.tool-verification.v3"; checked_at=(Get-Date).ToUniversalTime().ToString("o"); available=$Available; total=$Rows.Count; rows=$Rows} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Out -Encoding UTF8
if ($Available -eq 0) { exit 2 }
exit 0
