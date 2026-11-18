from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


@dataclass(frozen=True)
class EngineSpec:
    key: str
    label: str
    executables: tuple[str, ...]
    category: str
    capabilities: tuple[str, ...]
    version_args: tuple[str, ...] = ("--version",)
    required_databases: tuple[str, ...] = ()
    gpu_optional: bool = False
    installation_note: str = ""


@dataclass(frozen=True)
class EngineStatus:
    key: str
    label: str
    available: bool
    executable: str
    version: str
    category: str
    capabilities: tuple[str, ...]
    required_databases: tuple[str, ...]
    gpu_optional: bool
    note: str


@dataclass(frozen=True)
class EnginePlan:
    plan_key: str
    engine_key: str
    command: tuple[str, ...]
    cwd: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    description: str
    resources: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineRunResult:
    engine_key: str
    plan_key: str
    return_code: int
    duration_seconds: float
    stdout: str
    stderr: str
    output_files: tuple[dict[str, Any], ...]
    command: tuple[str, ...]


ENGINE_REGISTRY: dict[str, EngineSpec] = {
    "samtools": EngineSpec("samtools", "SAMtools", ("samtools",), "Genomics", ("BAM/CRAM validation", "Indexing", "Coverage", "Region extraction"), installation_note="Install a current SAMtools release and keep the matching reference FASTA available for CRAM."),
    "bcftools": EngineSpec("bcftools", "BCFtools", ("bcftools",), "Genomics", ("VCF normalization", "Filtering", "Statistics", "Index-aware querying"), required_databases=("Reference FASTA",)),
    "tabix": EngineSpec("tabix", "Tabix", ("tabix",), "Genomics", ("Indexed VCF/BED querying",), installation_note="Usually distributed with HTSlib."),
    "bgzip": EngineSpec("bgzip", "BGZF compressor", ("bgzip",), "Genomics", ("Block-gzip compression",), installation_note="Usually distributed with HTSlib."),
    "minimap2": EngineSpec("minimap2", "minimap2", ("minimap2",), "Genomics", ("Long-read mapping", "Assembly alignment")),
    "dorado": EngineSpec("dorado", "Oxford Nanopore Dorado", ("dorado", "dorado.exe"), "Long-read sequencing", ("Basecalling", "Modified-base calling", "Duplex processing"), required_databases=("Dorado model weights",), gpu_optional=True),
    "bwa": EngineSpec("bwa", "BWA", ("bwa-mem2", "bwa"), "Genomics", ("Short-read mapping",)),
    "bowtie": EngineSpec("bowtie", "Bowtie 2", ("bowtie2", "bowtie2.exe"), "Genomics", ("Short-read alignment", "CRISPR off-target candidate mapping"), required_databases=("Bowtie 2 genome index",)),
    "star": EngineSpec("star", "STAR", ("STAR", "star"), "Transcriptomics", ("Splice-aware RNA alignment",), required_databases=("STAR genome index",)),
    "rmats": EngineSpec("rmats", "rMATS", ("rmats.py", "rmats"), "Transcriptomics", ("Replicate-aware alternative splicing",), required_databases=("Genome annotation GTF",)),
    "majiq": EngineSpec("majiq", "MAJIQ", ("majiq",), "Transcriptomics", ("Local splicing variation",), required_databases=("Genome annotation GFF3",)),
    "suppa2": EngineSpec("suppa2", "SUPPA2", ("suppa.py", "suppa2"), "Transcriptomics", ("Alternative-splicing event quantification",), required_databases=("Transcript annotation GTF",)),
    "macs2": EngineSpec("macs2", "MACS2", ("macs2",), "Epigenomics", ("ChIP-seq/ATAC-seq peak calling",)),
    "deeptools": EngineSpec("deeptools", "deepTools", ("bamCoverage",), "Epigenomics", ("bigWig generation", "Signal profiles")),
    "plink2": EngineSpec("plink2", "PLINK 2", ("plink2",), "Population genetics", ("Cohort QC", "Association tests", "PCA", "Kinship")),
    "mafft": EngineSpec("mafft", "MAFFT", ("mafft", "mafft.bat"), "Phylogenetics", ("Multiple sequence alignment",)),
    "iqtree": EngineSpec("iqtree", "IQ-TREE", ("iqtree2", "iqtree"), "Phylogenetics", ("Maximum-likelihood phylogeny", "Model selection", "Bootstrap")),
    "kraken2": EngineSpec("kraken2", "Kraken 2", ("kraken2",), "Metagenomics", ("Taxonomic classification",), required_databases=("Kraken 2 database",)),
    "bracken": EngineSpec("bracken", "Bracken", ("bracken",), "Metagenomics", ("Abundance re-estimation",), required_databases=("Bracken database",)),
    "humann": EngineSpec("humann", "HUMAnN", ("humann",), "Metagenomics", ("Functional profiling",), required_databases=("ChocoPhlAn", "UniRef")),
    "obabel": EngineSpec("obabel", "Open Babel", ("obabel", "obabel.exe"), "Cheminformatics", ("Ligand format conversion", "Hydrogen/protonation preparation")),
    "vina": EngineSpec("vina", "AutoDock Vina", ("vina",), "Structural biology", ("Molecular docking", "Pose scoring")),
    "gromacs": EngineSpec("gromacs", "GROMACS", ("gmx", "gmx_mpi"), "Structural biology", ("Molecular dynamics", "Trajectory analysis"), gpu_optional=True),
    "openmm": EngineSpec("openmm", "OpenMM Python", (sys.executable,), "Structural biology", ("Molecular dynamics",), version_args=("-c", "import openmm; print(openmm.__version__)"), gpu_optional=True),
    "cellpose": EngineSpec("cellpose", "Cellpose", ("cellpose",), "Bioimaging", ("Cell/nucleus segmentation",), gpu_optional=True),
    "stardist": EngineSpec("stardist", "StarDist Python", (sys.executable,), "Bioimaging", ("Star-convex object segmentation",), version_args=("-c", "import stardist; print(stardist.__version__)"), gpu_optional=True),
    "openms": EngineSpec("openms", "OpenMS", ("FileInfo", "FileInfo.exe"), "Mass spectrometry", ("mzML validation", "Peak processing", "Identification workflows")),
    "openms_featurefinder": EngineSpec("openms_featurefinder", "OpenMS FeatureFinderMetabo", ("FeatureFinderMetabo", "FeatureFinderMetabo.exe"), "Mass spectrometry", ("LC-MS feature detection", "Chromatographic peak picking")),
    "openslide": EngineSpec("openslide", "OpenSlide Python", (sys.executable,), "Digital pathology", ("Tiled whole-slide access",), version_args=("-c", "import openslide; print(openslide.__version__)")),
    "proteinmpnn": EngineSpec("proteinmpnn", "ProteinMPNN", ("protein_mpnn_run.py", "proteinmpnn"), "Protein design", ("Sequence design from structure",), gpu_optional=True),
    "rfdiffusion": EngineSpec("rfdiffusion", "RFdiffusion", ("run_inference.py", "rfdiffusion"), "Protein design", ("Generative backbone design",), gpu_optional=True, required_databases=("Model weights",)),
    "colabfold": EngineSpec("colabfold", "ColabFold", ("colabfold_batch", "colabfold_batch.exe"), "Protein structure", ("Structure prediction", "MSA-assisted confidence estimation"), gpu_optional=True, required_databases=("ColabFold/AlphaFold databases or remote MSA policy",)),
    "vep": EngineSpec("vep", "Ensembl VEP", ("vep", "vep.exe"), "Variant interpretation", ("Variant consequence annotation", "Transcript consequences"), required_databases=("VEP cache", "Reference FASTA")),
    "whatshap": EngineSpec("whatshap", "WhatsHap", ("whatshap",), "Variant interpretation", ("Read-backed phasing", "Pedigree phasing"), required_databases=("Reference FASTA",)),
    "regenie": EngineSpec("regenie", "REGENIE", ("regenie",), "Population genetics", ("Whole-genome regression", "Association testing")),
    "saige": EngineSpec("saige", "SAIGE", ("step1_fitNULLGLMM.R", "SAIGE"), "Population genetics", ("Mixed-model association", "Case-control imbalance")),
    "sniffles": EngineSpec("sniffles", "Sniffles2", ("sniffles", "sniffles2"), "Structural variation", ("Long-read SV calling", "Population SV merging")),
    "expansionhunter": EngineSpec("expansionhunter", "ExpansionHunter", ("ExpansionHunter", "expansionhunter"), "Structural variation", ("Repeat-expansion genotyping",), required_databases=("Repeat catalogue", "Reference FASTA")),
    "flye": EngineSpec("flye", "Flye", ("flye",), "Genome assembly", ("Long-read assembly", "Metagenome assembly")),
    "hifiasm": EngineSpec("hifiasm", "hifiasm", ("hifiasm",), "Genome assembly", ("HiFi assembly", "Phased assembly")),
    "busco": EngineSpec("busco", "BUSCO", ("busco",), "Genome assembly", ("Assembly completeness",), required_databases=("BUSCO lineage",)),
    "merqury": EngineSpec("merqury", "Merqury", ("merqury.sh", "merqury"), "Genome assembly", ("K-mer completeness", "Consensus quality")),
    "minigraph": EngineSpec("minigraph", "minigraph", ("minigraph",), "Pangenomics", ("Pangenome graph construction", "Assembly alignment")),
    "vg": EngineSpec("vg", "vg toolkit", ("vg",), "Pangenomics", ("Graph indexing", "Graph mapping", "Variant projection")),
    "odgi": EngineSpec("odgi", "odgi", ("odgi",), "Pangenomics", ("Graph sorting", "Path statistics", "Visualization preparation")),
    "graphaligner": EngineSpec("graphaligner", "GraphAligner", ("GraphAligner", "graphaligner"), "Pangenomics", ("Sequence-to-graph alignment",)),
    "anarci": EngineSpec("anarci", "ANARCI", ("ANARCI", "anarci"), "Antibody engineering", ("Antibody numbering", "CDR annotation")),
    "igblast": EngineSpec("igblast", "IgBLAST", ("igblastn", "igblastp"), "Antibody engineering", ("Immunoglobulin germline alignment",), required_databases=("IgBLAST germline database",)),
    "netmhcpan": EngineSpec("netmhcpan", "NetMHCpan", ("netMHCpan", "netMHCpan.exe"), "Immunoinformatics", ("MHC-I binding prediction",), required_databases=("NetMHCpan data files",)),
    "netmhciipan": EngineSpec("netmhciipan", "NetMHCIIpan", ("netMHCIIpan", "netMHCIIpan.exe"), "Immunoinformatics", ("MHC-II binding prediction",), required_databases=("NetMHCIIpan data files",)),
    "scanpy": EngineSpec("scanpy", "Scanpy Python", (sys.executable,), "Single-cell", ("Single-cell QC", "Embedding", "Clustering"), version_args=("-c", "import scanpy; print(scanpy.__version__)")),
    "scvelo": EngineSpec("scvelo", "scVelo Python", (sys.executable,), "Single-cell", ("RNA velocity",), version_args=("-c", "import scvelo; print(scvelo.__version__)")),
    "cellrank": EngineSpec("cellrank", "CellRank Python", (sys.executable,), "Single-cell", ("Fate probabilities", "Terminal-state analysis"), version_args=("-c", "import cellrank; print(cellrank.__version__)")),
    "comet": EngineSpec("comet", "Comet", ("comet", "comet.exe"), "Proteomics", ("Peptide-spectrum matching",)),
    "msgfplus": EngineSpec("msgfplus", "MS-GF+", ("MSGFPlus", "msgfplus"), "Proteomics", ("Peptide-spectrum matching",)),
    "msconvert": EngineSpec("msconvert", "ProteoWizard msconvert", ("msconvert", "msconvert.exe"), "Mass spectrometry", ("Vendor RAW conversion", "mzML export")),
    "bedtools": EngineSpec("bedtools", "BEDTools", ("bedtools",), "Genomics", ("Interval arithmetic", "Genome coverage")),
    "bowtie2": EngineSpec("bowtie2", "Bowtie 2", ("bowtie2",), "Genomics", ("Short-read alignment",), required_databases=("Bowtie2 index",)),
    "blastn": EngineSpec("blastn", "BLASTN", ("blastn",), "Genomics", ("Nucleotide similarity search",), required_databases=("BLAST database",)),
    "modkit": EngineSpec("modkit", "Oxford Nanopore Modkit", ("modkit",), "Long-read epigenomics", ("Modified-base pileup", "Modification summary"), required_databases=("Reference FASTA",)),
    "amrfinderplus": EngineSpec("amrfinderplus", "NCBI AMRFinderPlus", ("amrfinder",), "AMR", ("AMR gene and mutation detection",), required_databases=("AMRFinderPlus database",)),
    "resfinder": EngineSpec("resfinder", "ResFinder", ("run_resfinder.py", "resfinder"), "AMR", ("Acquired resistance and point-mutation detection",), required_databases=("ResFinder database", "PointFinder database")),
    "abricate": EngineSpec("abricate", "ABRicate", ("abricate",), "Microbiology", ("AMR/virulence screening",), required_databases=("ABRicate database",)),
    "llama_cpp": EngineSpec("llama_cpp", "llama.cpp", ("llama-cli", "main", "llama-server"), "Local AI", ("Local language-model inference",), required_databases=("Approved model weights",), gpu_optional=True),
    "fastqc": EngineSpec("fastqc", "FastQC", ("fastqc", "fastqc.exe"), "Sequencing QC", ("Read-quality reports", "Adapter/duplication diagnostics")),
    "multiqc": EngineSpec("multiqc", "MultiQC", ("multiqc", "multiqc.exe"), "Sequencing QC", ("Cross-sample QC aggregation", "Run-level quality reporting")),
    "fastp": EngineSpec("fastp", "fastp", ("fastp", "fastp.exe"), "Sequencing QC", ("Read trimming", "Adapter detection", "Quality filtering")),
    "cutadapt": EngineSpec("cutadapt", "Cutadapt", ("cutadapt", "cutadapt.exe"), "Sequencing QC", ("Adapter trimming", "Linked-adapter handling")),
    "snpeff": EngineSpec("snpeff", "SnpEff", ("snpEff", "snpEff.exe", "snpeff"), "Variant interpretation", ("Variant consequence annotation",), required_databases=("SnpEff genome database",)),
    "interproscan": EngineSpec("interproscan", "InterProScan", ("interproscan.sh", "interproscan", "interproscan.bat"), "Protein annotation", ("Domain annotation", "GO/pathway mapping"), required_databases=("InterPro member databases",)),
    "hmmer": EngineSpec("hmmer", "HMMER hmmsearch", ("hmmsearch", "hmmsearch.exe"), "Protein annotation", ("Profile-HMM sequence search",), required_databases=("Pinned HMM profile database",)),
    "blastp": EngineSpec("blastp", "BLASTP", ("blastp", "blastp.exe"), "Protein annotation", ("Protein similarity search",), required_databases=("BLAST protein database",)),
    "mosdepth": EngineSpec("mosdepth", "mosdepth", ("mosdepth", "mosdepth.exe"), "Genomics", ("Genome coverage", "Region coverage summaries")),
    "picard": EngineSpec("picard", "Picard", ("picard", "picard.exe"), "Genomics", ("Alignment metrics", "Duplicate/insert-size metrics"), required_databases=("Reference FASTA",)),
    "salmon": EngineSpec("salmon", "Salmon", ("salmon", "salmon.exe"), "Transcriptomics", ("Transcript quantification", "Mapping validation"), required_databases=("Salmon transcriptome index",)),
    "kallisto": EngineSpec("kallisto", "Kallisto", ("kallisto", "kallisto.exe"), "Transcriptomics", ("Pseudoalignment", "Transcript quantification"), required_databases=("Kallisto transcriptome index",)),
}


_PLAN_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "samtools_index": ("samtools",),
    "samtools_depth": ("samtools",),
    "bcftools_norm": ("bcftools",),
    "bcftools_stats": ("bcftools",),
    "tabix_vcf": ("tabix",),
    "mafft_align": ("mafft",),
    "iqtree_build": ("iqtree",),
    "plink2_pca": ("plink2",),
    "plink2_glm": ("plink2",),
    "macs2_callpeak": ("macs2",),
    "deeptools_bamcoverage": ("deeptools",),
    "whatshap_phase": ("whatshap",),
    "igblast_germline": ("igblast",),
    "comet_search": ("comet",),
    "openms_featurefinder_metabo": ("openms_featurefinder",),
    "bedtools_intersect": ("bedtools",),
    "vina_dock": ("vina",),
    "gromacs_mdrun": ("gromacs",),
    "cellpose_segment": ("cellpose",),
    "openms_fileinfo": ("openms",),
    "vep_annotate": ("vep",),
    "sniffles_call": ("sniffles",),
    "expansionhunter_call": ("expansionhunter",),
    "flye_assemble": ("flye",),
    "hifiasm_assemble": ("hifiasm",),
    "busco_assembly": ("busco",),
    "minigraph_graph": ("minigraph",),
    "anarci_number": ("anarci",),
    "msconvert_mzml": ("msconvert",),
    "bowtie2_align": ("bowtie",),
    "kraken2_classify": ("kraken2",),
    "bracken_abundance": ("bracken",),
    "humann_profile": ("humann",),
    "netmhcpan_predict": ("netmhcpan",),
    "netmhciipan_predict": ("netmhciipan",),
    "dorado_basecall": ("dorado",),
    "vg_stats": ("vg",),
    "odgi_stats": ("odgi",),
    "graphaligner_align": ("graphaligner",),
    "proteinmpnn_design": ("proteinmpnn",),
    "colabfold_predict": ("colabfold",),
}

from .engine_plans_step155 import STEP155_PLAN_DESCRIPTIONS, STEP155_PLAN_REQUIREMENTS
from .engine_plans_step156 import STEP156_PLAN_DESCRIPTIONS, STEP156_PLAN_REQUIREMENTS
from .engine_plans_step157 import STEP157_PLAN_DESCRIPTIONS, STEP157_PLAN_REQUIREMENTS

_PLAN_REQUIREMENTS.update(STEP155_PLAN_REQUIREMENTS)
_PLAN_REQUIREMENTS.update(STEP156_PLAN_REQUIREMENTS)
_PLAN_REQUIREMENTS.update(STEP157_PLAN_REQUIREMENTS)


def _clean_version(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]
    return " | ".join(lines[:3])[:500]


def detect_engine(key: str, *, timeout_seconds: float = 5.0) -> EngineStatus:
    if key not in ENGINE_REGISTRY:
        raise KeyError(key)
    spec = ENGINE_REGISTRY[key]
    executable = ""
    for candidate in spec.executables:
        if candidate == sys.executable:
            executable = candidate
            break
        located = shutil.which(candidate)
        if located:
            executable = located
            break
    if not executable:
        return EngineStatus(spec.key, spec.label, False, "", "Not detected", spec.category, spec.capabilities, spec.required_databases, spec.gpu_optional, spec.installation_note)
    try:
        completed = subprocess.run([executable, *spec.version_args], capture_output=True, text=True, timeout=timeout_seconds, shell=False, check=False)
        version = _clean_version(completed.stdout or completed.stderr) or f"Detected (exit {completed.returncode})"
        if executable == sys.executable:
            available = completed.returncode == 0
        else:
            available = completed.returncode == 0 or bool(_clean_version(completed.stdout or completed.stderr))
    except Exception as exc:
        version = f"Detected but version probe failed: {type(exc).__name__}: {exc}"
        available = True
    return EngineStatus(spec.key, spec.label, available, executable, version, spec.category, spec.capabilities, spec.required_databases, spec.gpu_optional, spec.installation_note)


def engine_status_matrix(keys: Iterable[str] | None = None) -> pd.DataFrame:
    selected = list(keys or ENGINE_REGISTRY)
    rows = []
    for key in selected:
        status = detect_engine(key)
        rows.append({
            "Engine": status.label, "Key": status.key, "Available": status.available,
            "Executable": status.executable or "Not found", "Version": status.version,
            "Category": status.category, "Capabilities": ", ".join(status.capabilities),
            "Reference data": ", ".join(status.required_databases) or "None declared",
            "GPU optional": status.gpu_optional, "Installation note": status.note,
        })
    return pd.DataFrame(rows)


def _safe_path(path: str | Path, workdir: Path, *, must_exist: bool = True) -> Path:
    resolved = Path(path).expanduser().resolve()
    root = workdir.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path is outside the protected engine workspace: {resolved}") from exc
    if must_exist and not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved


def build_engine_plan(plan_key: str, *, workdir: str | Path, **parameters: Any) -> EnginePlan:
    if plan_key not in _PLAN_REQUIREMENTS:
        raise KeyError(f"Unknown engine plan: {plan_key}")
    root = Path(workdir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    engine_key = _PLAN_REQUIREMENTS[plan_key][0]
    status = detect_engine(engine_key)
    executable = status.executable or ENGINE_REGISTRY[engine_key].executables[0]
    inputs: list[str] = []
    outputs: list[str] = []
    resources: dict[str, Any] = {"threads": int(parameters.get("threads", 2)), "memory_gb": float(parameters.get("memory_gb", 4))}

    if plan_key in STEP157_PLAN_REQUIREMENTS:
        from .engine_plans_step157 import build_step157_plan
        payload = build_step157_plan(plan_key, executable=executable, workdir=root, parameters=parameters)
        return EnginePlan(
            plan_key=plan_key,
            engine_key=engine_key,
            command=tuple(payload["command"]),
            cwd=str(root),
            inputs=tuple(payload["inputs"]),
            outputs=tuple(payload["outputs"]),
            description=str(payload["description"]),
            resources=dict(payload["resources"]),
        )

    if plan_key in STEP156_PLAN_REQUIREMENTS:
        from .engine_plans_step156 import build_step156_plan
        payload = build_step156_plan(plan_key, executable=executable, workdir=root, parameters=parameters)
        return EnginePlan(
            plan_key=plan_key,
            engine_key=engine_key,
            command=tuple(payload["command"]),
            cwd=str(root),
            inputs=tuple(payload["inputs"]),
            outputs=tuple(payload["outputs"]),
            description=str(payload["description"]),
            resources=dict(payload["resources"]),
        )

    if plan_key in STEP155_PLAN_REQUIREMENTS:
        from .engine_plans_step155 import build_step155_plan
        payload = build_step155_plan(plan_key, executable=executable, workdir=root, parameters=parameters)
        return EnginePlan(
            plan_key=plan_key,
            engine_key=engine_key,
            command=tuple(payload["command"]),
            cwd=str(root),
            inputs=tuple(payload["inputs"]),
            outputs=tuple(payload["outputs"]),
            description=str(payload["description"]),
            resources=dict(payload["resources"]),
        )

    if plan_key == "samtools_index":
        source = _safe_path(parameters["alignment"], root)
        command = (executable, "index", "-@", str(resources["threads"]), str(source))
        output = Path(str(source) + (".crai" if source.suffix.lower() == ".cram" else ".bai"))
        inputs, outputs, description = [str(source)], [str(output)], "Create BAM/CRAM index"
    elif plan_key == "samtools_depth":
        source = _safe_path(parameters["alignment"], root)
        output = _safe_path(parameters.get("output", root / "coverage.tsv"), root, must_exist=False)
        region = str(parameters.get("region", "")).strip()
        command_list = [executable, "depth", "-a"]
        if region:
            if not re.fullmatch(r"[A-Za-z0-9_.:-]+", region):
                raise ValueError("Invalid genomic region syntax")
            command_list += ["-r", region]
        command_list += ["-o", str(output), str(source)]
        command = tuple(command_list)
        inputs, outputs, description = [str(source)], [str(output)], "Generate indexed alignment depth table"
    elif plan_key == "bcftools_norm":
        source = _safe_path(parameters["vcf"], root)
        reference = _safe_path(parameters["reference"], root)
        output = _safe_path(parameters.get("output", root / "normalized.vcf.gz"), root, must_exist=False)
        command = (executable, "norm", "-f", str(reference), "-m", "-any", "-Oz", "-o", str(output), str(source))
        inputs, outputs, description = [str(source), str(reference)], [str(output)], "Normalize and split multiallelic VCF records"
    elif plan_key == "bcftools_stats":
        source = _safe_path(parameters["vcf"], root)
        output = _safe_path(parameters.get("output", root / "bcftools.stats.txt"), root, must_exist=False)
        command = (executable, "stats", "-o", str(output), str(source))
        inputs, outputs, description = [str(source)], [str(output)], "Generate VCF quality statistics"
    elif plan_key == "tabix_vcf":
        source = _safe_path(parameters["vcf_gz"], root)
        command = (executable, "-f", "-p", "vcf", str(source))
        inputs, outputs, description = [str(source)], [str(Path(str(source) + ".tbi"))], "Create tabix VCF index"
    elif plan_key == "mafft_align":
        source = _safe_path(parameters["fasta"], root)
        output = _safe_path(parameters.get("output", root / "aligned.fasta"), root, must_exist=False)
        command = (executable, "--auto", "--thread", str(resources["threads"]), str(source))
        inputs, outputs, description = [str(source)], [str(output)], "Multiple sequence alignment; stdout is captured to the declared output"
    elif plan_key == "iqtree_build":
        source = _safe_path(parameters["alignment"], root)
        prefix = _safe_path(parameters.get("prefix", root / "iqtree_run"), root, must_exist=False)
        bootstrap = max(100, min(int(parameters.get("bootstrap", 1000)), 100_000))
        command = (executable, "-s", str(source), "-m", "MFP", "-B", str(bootstrap), "-T", str(resources["threads"]), "--prefix", str(prefix))
        inputs, outputs, description = [str(source)], [str(prefix) + ".treefile", str(prefix) + ".iqtree"], "Maximum-likelihood tree with model selection and ultrafast bootstrap"
    elif plan_key == "plink2_pca":
        source = _safe_path(parameters["pfile_prefix"], root, must_exist=False)
        output_prefix = _safe_path(parameters.get("output_prefix", root / "plink_pca"), root, must_exist=False)
        pcs = max(2, min(int(parameters.get("pcs", 10)), 100))
        command = (executable, "--pfile", str(source), "--pca", str(pcs), "approx", "--threads", str(resources["threads"]), "--out", str(output_prefix))
        inputs, outputs, description = [str(source)], [str(output_prefix) + ".eigenvec", str(output_prefix) + ".eigenval"], "Ancestry-aware PCA from a PLINK 2 pfile set"
    elif plan_key == "plink2_glm":
        source = _safe_path(parameters["pfile_prefix"], root, must_exist=False)
        phenotype = _safe_path(parameters["phenotype"], root)
        output_prefix = _safe_path(parameters.get("output_prefix", root / "plink_glm"), root, must_exist=False)
        phenotype_name = str(parameters.get("phenotype_name", "phenotype"))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", phenotype_name):
            raise ValueError("Invalid phenotype column name")
        command_list = [executable, "--pfile", str(source), "--pheno", str(phenotype), "--pheno-name", phenotype_name]
        covariates = parameters.get("covariates")
        if covariates:
            covar = _safe_path(covariates, root)
            command_list += ["--covar", str(covar)]
        command_list += ["--glm", "hide-covar", "cols=+a1freq", "--threads", str(resources["threads"]), "--out", str(output_prefix)]
        command = tuple(command_list)
        inputs = [str(source), str(phenotype)] + ([str(covar)] if covariates else [])
        outputs, description = [str(output_prefix) + ".PHENO1.glm.linear", str(output_prefix) + ".PHENO1.glm.logistic.hybrid"], "Run a protected PLINK 2 association model with explicit phenotype and optional covariates"
    elif plan_key == "macs2_callpeak":
        treatment = _safe_path(parameters["treatment"], root)
        control_value = parameters.get("control")
        control = _safe_path(control_value, root) if control_value else None
        output_dir = _safe_path(parameters.get("output_dir", root / "macs2"), root, must_exist=False)
        name = str(parameters.get("name", "peak_call"))
        genome_size = str(parameters.get("genome_size", "hs"))
        file_format = str(parameters.get("format", "BAM")).upper()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not re.fullmatch(r"(?:hs|mm|ce|dm|[0-9]+(?:\.[0-9]+)?[eE][0-9]+)", genome_size):
            raise ValueError("Invalid MACS2 run name or genome-size value")
        if file_format not in {"BAM", "BAMPE", "BED", "BEDPE"}:
            raise ValueError("Unsupported MACS2 input format")
        command_list = [executable, "callpeak", "-t", str(treatment)]
        if control is not None:
            command_list += ["-c", str(control)]
        command_list += ["-f", file_format, "-g", genome_size, "-n", name, "--outdir", str(output_dir), "-q", str(max(1e-6, min(float(parameters.get("q_value", 0.05)), 1.0)))]
        command = tuple(command_list)
        inputs = [str(treatment)] + ([str(control)] if control is not None else [])
        outputs = [str(output_dir / f"{name}_peaks.narrowPeak"), str(output_dir / f"{name}_summits.bed"), str(output_dir / f"{name}_peaks.xls")]
        description = "Call ATAC-seq or ChIP-seq peaks with an explicit control, genome size and FDR threshold"
    elif plan_key == "deeptools_bamcoverage":
        alignment = _safe_path(parameters["alignment"], root)
        output = _safe_path(parameters.get("output", root / "coverage.bw"), root, must_exist=False)
        bin_size = max(1, min(int(parameters.get("bin_size", 50)), 100000))
        normalization = str(parameters.get("normalization", "CPM"))
        if normalization not in {"RPKM", "CPM", "BPM", "RPGC", "None"}:
            raise ValueError("Unsupported deepTools normalization")
        command = (executable, "-b", str(alignment), "-o", str(output), "--binSize", str(bin_size), "--normalizeUsing", normalization, "--numberOfProcessors", str(resources["threads"]))
        inputs, outputs, description = [str(alignment)], [str(output)], "Generate a normalized bigWig coverage track from an indexed alignment"
    elif plan_key == "whatshap_phase":
        vcf = _safe_path(parameters["vcf"], root)
        alignment = _safe_path(parameters["alignment"], root)
        reference = _safe_path(parameters["reference"], root)
        output = _safe_path(parameters.get("output", root / "phased.vcf.gz"), root, must_exist=False)
        command = (executable, "phase", "--reference", str(reference), "--output", str(output), str(vcf), str(alignment))
        inputs, outputs, description = [str(vcf), str(alignment), str(reference)], [str(output)], "Perform read-backed phasing in a protected workspace"
    elif plan_key == "igblast_germline":
        query = _safe_path(parameters["query"], root)
        db_v = _safe_path(parameters["db_v"], root, must_exist=False)
        db_d = _safe_path(parameters["db_d"], root, must_exist=False)
        db_j = _safe_path(parameters["db_j"], root, must_exist=False)
        output = _safe_path(parameters.get("output", root / "igblast.tsv"), root, must_exist=False)
        organism = str(parameters.get("organism", "human"))
        domain_system = str(parameters.get("domain_system", "imgt"))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", organism) or domain_system not in {"imgt", "kabat"}:
            raise ValueError("Invalid IgBLAST organism or domain system")
        command = (executable, "-query", str(query), "-germline_db_V", str(db_v), "-germline_db_D", str(db_d), "-germline_db_J", str(db_j), "-organism", organism, "-domain_system", domain_system, "-outfmt", "19", "-out", str(output))
        inputs, outputs, description = [str(query), str(db_v), str(db_d), str(db_j)], [str(output)], "Assign immunoglobulin germline genes with declared local IgBLAST databases"
    elif plan_key == "comet_search":
        spectra = _safe_path(parameters["spectra"], root)
        database = _safe_path(parameters["database"], root)
        params = _safe_path(parameters["params"], root)
        output_dir = _safe_path(parameters.get("output_dir", root / "comet"), root, must_exist=False)
        output_dir.mkdir(parents=True, exist_ok=True)
        command = (executable, f"-P{params}", f"-D{database}", str(spectra))
        inputs = [str(spectra), str(database), str(params)]
        outputs = [str(output_dir / f"{spectra.stem}.pep.xml"), str(output_dir / f"{spectra.stem}.txt")]
        description = "Run a database peptide-spectrum search with explicit parameters and FASTA database; execute with the declared output directory as workdir"
        root = output_dir
    elif plan_key == "openms_featurefinder_metabo":
        source = _safe_path(parameters["mzml"], root)
        output = _safe_path(parameters.get("output", root / "features.featureXML"), root, must_exist=False)
        noise_threshold = max(0.0, float(parameters.get("noise_threshold_int", 1000.0)))
        command = (executable, "-in", str(source), "-out", str(output), "-algorithm:common:noise_threshold_int", str(noise_threshold))
        inputs, outputs, description = [str(source)], [str(output)], "Detect chromatographic LC-MS features with OpenMS FeatureFinderMetabo"
    elif plan_key == "bedtools_intersect":
        a = _safe_path(parameters["a"], root)
        b = _safe_path(parameters["b"], root)
        output = _safe_path(parameters.get("output", root / "intersect.tsv"), root, must_exist=False)
        command = (executable, "intersect", "-a", str(a), "-b", str(b), "-wa", "-wb")
        inputs, outputs, description = [str(a), str(b)], [str(output)], "Intersect genomic intervals; stdout is captured to the declared output"
    elif plan_key == "vina_dock":
        receptor = _safe_path(parameters["receptor"], root)
        ligand = _safe_path(parameters["ligand"], root)
        output = _safe_path(parameters.get("output", root / "docked.pdbqt"), root, must_exist=False)
        center = [float(parameters.get(name, 0.0)) for name in ("center_x", "center_y", "center_z")]
        size = [max(1.0, min(float(parameters.get(name, 20.0)), 100.0)) for name in ("size_x", "size_y", "size_z")]
        command = (executable, "--receptor", str(receptor), "--ligand", str(ligand), "--center_x", str(center[0]), "--center_y", str(center[1]), "--center_z", str(center[2]), "--size_x", str(size[0]), "--size_y", str(size[1]), "--size_z", str(size[2]), "--cpu", str(resources["threads"]), "--out", str(output))
        inputs, outputs, description = [str(receptor), str(ligand)], [str(output)], "Run AutoDock Vina with an explicitly defined search box"
    elif plan_key == "gromacs_mdrun":
        tpr = _safe_path(parameters["tpr"], root)
        deffnm = _safe_path(parameters.get("deffnm", root / "md"), root, must_exist=False)
        command = (executable, "mdrun", "-s", str(tpr), "-deffnm", str(deffnm), "-nt", str(resources["threads"]), "-v")
        inputs, outputs, description = [str(tpr)], [str(deffnm) + ".xtc", str(deffnm) + ".edr", str(deffnm) + ".log"], "Run a prepared GROMACS portable binary input"
    elif plan_key == "cellpose_segment":
        image = _safe_path(parameters["image"], root)
        diameter = max(0.0, min(float(parameters.get("diameter", 0.0)), 1000.0))
        model = str(parameters.get("model", "cyto3"))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", model):
            raise ValueError("Invalid Cellpose model name")
        command = (executable, "--image_path", str(image), "--pretrained_model", model, "--diameter", str(diameter), "--save_png", "--save_tif")
        inputs, outputs, description = [str(image)], [str(image.parent)], "Segment image objects with a locally installed Cellpose model"
    elif plan_key == "openms_fileinfo":
        source = _safe_path(parameters["mzml"], root)
        output = _safe_path(parameters.get("output", root / "openms_fileinfo.txt"), root, must_exist=False)
        command = (executable, "-in", str(source), "-out", str(output))
        inputs, outputs, description = [str(source)], [str(output)], "Validate and summarise an mzML file with OpenMS"
    elif plan_key == "vep_annotate":
        source = _safe_path(parameters["vcf"], root)
        output = _safe_path(parameters.get("output", root / "vep_annotated.vcf"), root, must_exist=False)
        assembly = str(parameters.get("assembly", "GRCh38"))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", assembly):
            raise ValueError("Invalid assembly name")
        command = (executable, "--input_file", str(source), "--output_file", str(output), "--vcf", "--cache", "--offline", "--assembly", assembly, "--fork", str(resources["threads"]), "--force_overwrite")
        inputs, outputs, description = [str(source)], [str(output)], "Annotate VCF consequences with a locally installed, offline VEP cache"
    elif plan_key == "sniffles_call":
        source = _safe_path(parameters["alignment"], root)
        output = _safe_path(parameters.get("output", root / "sniffles.vcf.gz"), root, must_exist=False)
        minsupport = max(2, min(int(parameters.get("minsupport", 10)), 100000))
        command = (executable, "--input", str(source), "--vcf", str(output), "--threads", str(resources["threads"]), "--minsupport", str(minsupport))
        inputs, outputs, description = [str(source)], [str(output)], "Call structural variants from an indexed long-read alignment"
    elif plan_key == "expansionhunter_call":
        reads = _safe_path(parameters["alignment"], root)
        reference = _safe_path(parameters["reference"], root)
        catalogue = _safe_path(parameters["variant_catalog"], root)
        prefix = _safe_path(parameters.get("output_prefix", root / "expansionhunter"), root, must_exist=False)
        command = (executable, "--reads", str(reads), "--reference", str(reference), "--variant-catalog", str(catalogue), "--output-prefix", str(prefix))
        inputs, outputs, description = [str(reads), str(reference), str(catalogue)], [str(prefix) + ".vcf", str(prefix) + ".json"], "Genotype declared repeat-expansion loci"
    elif plan_key == "flye_assemble":
        reads = _safe_path(parameters["reads"], root)
        output_dir = _safe_path(parameters.get("output_dir", root / "flye_output"), root, must_exist=False)
        platform = str(parameters.get("platform", "nano-hq"))
        platform_flags = {"nano-hq": "--nano-hq", "nano-raw": "--nano-raw", "pacbio-hifi": "--pacbio-hifi", "pacbio-raw": "--pacbio-raw"}
        if platform not in platform_flags:
            raise ValueError("Unsupported Flye platform")
        genome_size = str(parameters.get("genome_size", "100m"))
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?[kKmMgG]?", genome_size):
            raise ValueError("Invalid genome-size value")
        command = (executable, platform_flags[platform], str(reads), "--out-dir", str(output_dir), "--threads", str(resources["threads"]), "--genome-size", genome_size)
        inputs, outputs, description = [str(reads)], [str(output_dir / "assembly.fasta"), str(output_dir / "assembly_graph.gfa")], "Run a platform-aware Flye assembly in the protected workspace"
    elif plan_key == "hifiasm_assemble":
        reads = _safe_path(parameters["reads"], root)
        prefix = _safe_path(parameters.get("output_prefix", root / "hifiasm"), root, must_exist=False)
        command = (executable, "-o", str(prefix), "-t", str(resources["threads"]), str(reads))
        inputs, outputs, description = [str(reads)], [str(prefix) + ".bp.p_ctg.gfa", str(prefix) + ".bp.hap1.p_ctg.gfa", str(prefix) + ".bp.hap2.p_ctg.gfa"], "Run HiFi assembly with hifiasm"
    elif plan_key == "busco_assembly":
        assembly = _safe_path(parameters["assembly"], root)
        lineage = str(parameters.get("lineage", "eukaryota_odb10"))
        output_name = str(parameters.get("output_name", "busco_run"))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", lineage) or not re.fullmatch(r"[A-Za-z0-9_.-]+", output_name):
            raise ValueError("Invalid BUSCO lineage or output name")
        output_parent = _safe_path(parameters.get("output_parent", root / "busco"), root, must_exist=False)
        command = (executable, "-i", str(assembly), "-l", lineage, "-o", output_name, "-m", "genome", "-c", str(resources["threads"]), "--out_path", str(output_parent))
        inputs, outputs, description = [str(assembly)], [str(output_parent / output_name)], "Assess assembly completeness with a pinned BUSCO lineage"
    elif plan_key == "minigraph_graph":
        reference = _safe_path(parameters["reference"], root)
        queries = [_safe_path(item, root) for item in parameters.get("queries", [])]
        if not queries:
            raise ValueError("At least one query assembly is required")
        output = _safe_path(parameters.get("output", root / "pangenome.gfa"), root, must_exist=False)
        command = (executable, "-xggs", "-t", str(resources["threads"]), str(reference), *(str(item) for item in queries))
        inputs, outputs, description = [str(reference), *(str(item) for item in queries)], [str(output)], "Construct a pangenome graph; stdout must be captured to the declared GFA output"
    elif plan_key == "anarci_number":
        fasta = _safe_path(parameters["fasta"], root)
        output = _safe_path(parameters.get("output", root / "anarci_numbering.txt"), root, must_exist=False)
        scheme = str(parameters.get("scheme", "imgt")).lower()
        if scheme not in {"imgt", "kabat", "chothia", "martin", "aho"}:
            raise ValueError("Unsupported antibody numbering scheme")
        command = (executable, "-i", str(fasta), "-o", str(output), "--scheme", scheme)
        inputs, outputs, description = [str(fasta)], [str(output)], "Number antibody sequences and identify CDR regions"
    elif plan_key == "msconvert_mzml":
        source = _safe_path(parameters["source"], root)
        output_dir = _safe_path(parameters.get("output_dir", root / "mzml"), root, must_exist=False)
        command = (executable, str(source), "--mzML", "--outdir", str(output_dir))
        output_name = source.stem + ".mzML"
        inputs, outputs, description = [str(source)], [str(output_dir / output_name)], "Convert a supported vendor or open mass-spectrometry file to mzML"
    elif plan_key == "bowtie2_align":
        reads1 = _safe_path(parameters["reads1"], root)
        reads2_value = parameters.get("reads2")
        reads2 = _safe_path(reads2_value, root) if reads2_value else None
        index_prefix = _safe_path(parameters["index_prefix"], root, must_exist=False)
        output = _safe_path(parameters.get("output", root / "bowtie2.sam"), root, must_exist=False)
        command_list = [executable, "-x", str(index_prefix), "-p", str(resources["threads"]), "-1" if reads2 else "-U", str(reads1)]
        if reads2 is not None:
            command_list += ["-2", str(reads2)]
        command_list += ["-S", str(output)]
        command = tuple(command_list)
        inputs = [str(reads1)] + ([str(reads2)] if reads2 is not None else []) + [str(index_prefix)]
        outputs, description = [str(output)], "Align short reads to a protected Bowtie 2 index"
    elif plan_key == "kraken2_classify":
        database = _safe_path(parameters["database"], root)
        reads1 = _safe_path(parameters["reads1"], root)
        reads2_value = parameters.get("reads2")
        reads2 = _safe_path(reads2_value, root) if reads2_value else None
        output = _safe_path(parameters.get("output", root / "kraken2.out"), root, must_exist=False)
        report = _safe_path(parameters.get("report", root / "kraken2.report"), root, must_exist=False)
        command_list = [executable, "--db", str(database), "--threads", str(resources["threads"]), "--report", str(report), "--output", str(output)]
        if reads2 is not None:
            command_list += ["--paired", str(reads1), str(reads2)]
        else:
            command_list += [str(reads1)]
        command = tuple(command_list)
        inputs = [str(database), str(reads1)] + ([str(reads2)] if reads2 is not None else [])
        outputs, description = [str(output), str(report)], "Classify reads with a versioned Kraken 2 database"
    elif plan_key == "bracken_abundance":
        database = _safe_path(parameters["database"], root)
        report = _safe_path(parameters["kraken_report"], root)
        output = _safe_path(parameters.get("output", root / "bracken.tsv"), root, must_exist=False)
        level = str(parameters.get("level", "S")).upper()
        if level not in {"D", "P", "C", "O", "F", "G", "S"}:
            raise ValueError("Unsupported Bracken taxonomic level")
        read_length = max(25, min(int(parameters.get("read_length", 150)), 100000))
        threshold = max(0, int(parameters.get("threshold", 10)))
        command = (executable, "-d", str(database), "-i", str(report), "-o", str(output), "-r", str(read_length), "-l", level, "-t", str(threshold))
        inputs, outputs, description = [str(database), str(report)], [str(output)], "Re-estimate taxonomic abundance from a Kraken 2 report"
    elif plan_key == "humann_profile":
        source = _safe_path(parameters["input"], root)
        output_dir = _safe_path(parameters.get("output_dir", root / "humann"), root, must_exist=False)
        command_list = [executable, "--input", str(source), "--output", str(output_dir), "--threads", str(resources["threads"])]
        nucleotide_db = parameters.get("nucleotide_database")
        protein_db = parameters.get("protein_database")
        if nucleotide_db:
            command_list += ["--nucleotide-database", str(_safe_path(nucleotide_db, root))]
        if protein_db:
            command_list += ["--protein-database", str(_safe_path(protein_db, root))]
        command = tuple(command_list)
        inputs, outputs, description = [str(source)], [str(output_dir)], "Profile microbial pathways with pinned HUMAnN databases"
    elif plan_key in {"netmhcpan_predict", "netmhciipan_predict"}:
        peptides = _safe_path(parameters["peptides"], root)
        output = _safe_path(parameters.get("output", root / f"{plan_key}.xls"), root, must_exist=False)
        allele = str(parameters.get("allele", "HLA-A02:01"))
        if not re.fullmatch(r"[A-Za-z0-9*:_,-]+", allele):
            raise ValueError("Invalid HLA allele syntax")
        length = max(8, min(int(parameters.get("peptide_length", 9)), 30))
        command = (executable, "-p", str(peptides), "-a", allele, "-l", str(length), "-xls", "-xlsfile", str(output))
        inputs, outputs, description = [str(peptides)], [str(output)], "Predict peptide-HLA binding with an explicitly selected allele and peptide length"
    elif plan_key == "dorado_basecall":
        model = _safe_path(parameters["model"], root)
        reads = _safe_path(parameters["reads"], root)
        output = _safe_path(parameters.get("output", root / "dorado_calls.bam"), root, must_exist=False)
        command_list = [executable, "basecaller", str(model), str(reads), "--emit-bam"]
        device = str(parameters.get("device", "auto"))
        if not re.fullmatch(r"[A-Za-z0-9:,_-]+", device):
            raise ValueError("Invalid Dorado device")
        command_list += ["--device", device]
        command = tuple(command_list)
        inputs, outputs, description = [str(model), str(reads)], [str(output)], "Run Dorado basecalling; stdout must be captured to the declared BAM output"
    elif plan_key == "vg_stats":
        graph = _safe_path(parameters["graph"], root)
        output = _safe_path(parameters.get("output", root / "vg_stats.txt"), root, must_exist=False)
        command = (executable, "stats", "-z", str(graph))
        inputs, outputs, description = [str(graph)], [str(output)], "Generate graph topology statistics; stdout must be captured to the declared output"
    elif plan_key == "odgi_stats":
        graph = _safe_path(parameters["graph"], root)
        output = _safe_path(parameters.get("output", root / "odgi_stats.txt"), root, must_exist=False)
        command = (executable, "stats", "-i", str(graph), "-S")
        inputs, outputs, description = [str(graph)], [str(output)], "Generate ODGI path and graph statistics; stdout must be captured to the declared output"
    elif plan_key == "graphaligner_align":
        graph = _safe_path(parameters["graph"], root)
        reads = _safe_path(parameters["reads"], root)
        output = _safe_path(parameters.get("output", root / "graphaligner.gaf"), root, must_exist=False)
        command = (executable, "-g", str(graph), "-f", str(reads), "-a", str(output), "-t", str(resources["threads"]))
        inputs, outputs, description = [str(graph), str(reads)], [str(output)], "Align sequence reads to a pangenome graph"
    elif plan_key == "proteinmpnn_design":
        jsonl = _safe_path(parameters["jsonl"], root)
        output_dir = _safe_path(parameters.get("output_dir", root / "proteinmpnn"), root, must_exist=False)
        count = max(1, min(int(parameters.get("num_seq_per_target", 8)), 1000))
        temperature = max(0.01, min(float(parameters.get("sampling_temp", 0.1)), 2.0))
        seed = max(0, int(parameters.get("seed", 153)))
        command = (executable, "--jsonl_path", str(jsonl), "--out_folder", str(output_dir), "--num_seq_per_target", str(count), "--sampling_temp", str(temperature), "--seed", str(seed))
        inputs, outputs, description = [str(jsonl)], [str(output_dir)], "Design sequences with ProteinMPNN using bounded candidate count and explicit seed"
    elif plan_key == "colabfold_predict":
        fasta = _safe_path(parameters["fasta"], root)
        output_dir = _safe_path(parameters.get("output_dir", root / "colabfold"), root, must_exist=False)
        recycles = max(1, min(int(parameters.get("num_recycle", 3)), 48))
        models = max(1, min(int(parameters.get("num_models", 5)), 20))
        command = (executable, str(fasta), str(output_dir), "--num-recycle", str(recycles), "--num-models", str(models))
        inputs, outputs, description = [str(fasta)], [str(output_dir)], "Predict protein structures with a pinned ColabFold runtime"
    else:
        raise KeyError(plan_key)

    return EnginePlan(plan_key, engine_key, tuple(command), str(root), tuple(inputs), tuple(outputs), description, resources)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def execute_engine_plan(plan: EnginePlan, *, timeout_seconds: int = 3600, stdout_to_output: bool = False) -> EngineRunResult:
    status = detect_engine(plan.engine_key)
    if not status.available:
        raise RuntimeError(f"Required engine is not available: {status.label}")
    command = list(plan.command)
    command[0] = status.executable
    cwd = Path(plan.cwd).resolve()
    cwd.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=False, timeout=max(1, int(timeout_seconds)), shell=False, check=False, env={**os.environ, "LC_ALL": "C"})
    duration = time.monotonic() - start
    stdout = completed.stdout.decode("utf-8", errors="replace")[-2_000_000:]
    stderr = completed.stderr.decode("utf-8", errors="replace")[-2_000_000:]
    if stdout_to_output and plan.outputs and completed.returncode == 0:
        output = Path(plan.outputs[0])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(stdout, encoding="utf-8")
    output_files = []
    for name in plan.outputs:
        path = Path(name)
        if path.is_file():
            output_files.append({"path": str(path), "size_bytes": path.stat().st_size, "sha256": _hash_file(path)})
    return EngineRunResult(plan.engine_key, plan.plan_key, completed.returncode, duration, stdout, stderr, tuple(output_files), tuple(command))


def plan_to_dict(plan: EnginePlan) -> dict[str, Any]:
    return asdict(plan)


def run_to_dict(result: EngineRunResult) -> dict[str, Any]:
    return asdict(result)


def plan_catalog() -> pd.DataFrame:
    descriptions = {
        "samtools_index": "Index BAM or CRAM",
        "samtools_depth": "Generate coverage table",
        "bcftools_norm": "Normalize VCF against a reference",
        "bcftools_stats": "Generate VCF QC statistics",
        "tabix_vcf": "Create tabix VCF index",
        "mafft_align": "Align FASTA sequences",
        "iqtree_build": "Build maximum-likelihood phylogeny",
        "plink2_pca": "Run cohort PCA",
        "plink2_glm": "Run covariate-aware association testing",
        "macs2_callpeak": "Call ATAC-seq or ChIP-seq peaks",
        "deeptools_bamcoverage": "Generate normalized bigWig coverage",
        "whatshap_phase": "Phase variants with read evidence",
        "igblast_germline": "Assign antibody germline genes",
        "comet_search": "Search MS/MS spectra against a FASTA database",
        "openms_featurefinder_metabo": "Detect LC-MS chromatographic features",
        "bedtools_intersect": "Intersect genomic intervals",
        "vina_dock": "Run docking in a defined box",
        "gromacs_mdrun": "Run prepared molecular dynamics job",
        "cellpose_segment": "Segment microscopy image",
        "openms_fileinfo": "Validate and inspect mzML",
        "vep_annotate": "Annotate VCF consequences",
        "sniffles_call": "Call long-read structural variants",
        "expansionhunter_call": "Genotype repeat expansions",
        "flye_assemble": "Assemble long reads with Flye",
        "hifiasm_assemble": "Assemble HiFi reads with hifiasm",
        "busco_assembly": "Assess assembly completeness",
        "minigraph_graph": "Construct a pangenome graph",
        "anarci_number": "Number antibody sequences",
        "msconvert_mzml": "Convert mass-spectrometry data to mzML",
        "bowtie2_align": "Align reads with Bowtie 2",
        "kraken2_classify": "Classify metagenomic reads",
        "bracken_abundance": "Re-estimate taxonomic abundance",
        "humann_profile": "Profile microbial pathways",
        "netmhcpan_predict": "Predict MHC-I peptide binding",
        "netmhciipan_predict": "Predict MHC-II peptide binding",
        "dorado_basecall": "Basecall nanopore reads",
        "vg_stats": "Inspect variation graph topology",
        "odgi_stats": "Inspect ODGI graph/path statistics",
        "graphaligner_align": "Align reads to a sequence graph",
        "proteinmpnn_design": "Generate structure-conditioned protein sequences",
        "colabfold_predict": "Predict protein structures",
    }
    descriptions.update(STEP155_PLAN_DESCRIPTIONS)
    descriptions.update(STEP156_PLAN_DESCRIPTIONS)
    descriptions.update(STEP157_PLAN_DESCRIPTIONS)
    return pd.DataFrame([{"Plan": key, "Engine": ENGINE_REGISTRY[engines[0]].label, "Purpose": descriptions.get(key, "External scientific-engine workflow")} for key, engines in _PLAN_REQUIREMENTS.items()])


__all__ = [
    "ENGINE_REGISTRY",
    "EnginePlan",
    "EngineRunResult",
    "EngineSpec",
    "EngineStatus",
    "build_engine_plan",
    "detect_engine",
    "engine_status_matrix",
    "execute_engine_plan",
    "plan_catalog",
    "plan_to_dict",
    "run_to_dict",
]
