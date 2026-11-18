from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.util import find_spec
from biointel.tools.runtime import tool_available


@dataclass(frozen=True)
class Capability:
    name: str
    category: str
    available: bool
    provider: str
    purpose: str
    installation_hint: str


def bioinformatics_capabilities() -> list[Capability]:
    definitions = [
        (
            "pysam",
            "Python",
            "module",
            "pysam",
            "SAM/BAM/CRAM and VCF acceleration",
            "pip install pysam",
        ),
        (
            "scipy",
            "Python",
            "module",
            "scipy",
            "advanced statistical tests and nonlinear fitting",
            "pip install scipy",
        ),
        (
            "statsmodels",
            "Python",
            "module",
            "statsmodels",
            "negative-binomial and multiple-testing models",
            "pip install statsmodels",
        ),
        (
            "scanpy",
            "Python",
            "module",
            "scanpy",
            "single-cell RNA-seq workflows",
            "pip install scanpy anndata",
        ),
        ("anndata", "Python", "module", "anndata", "H5AD single-cell data exchange", "pip install anndata"),
        ("h5py", "Python", "module", "h5py", "HDF5/H5AD matrix access", "pip install h5py"),
        ("igraph", "Python", "module", "igraph", "graph analytics and community detection", "pip install python-igraph"),
        ("leidenalg", "Python", "module", "leidenalg", "Leiden single-cell clustering", "pip install leidenalg"),
        ("umap", "Python", "module", "umap", "nonlinear UMAP embeddings", "pip install umap-learn"),
        (
            "primer3_core",
            "External",
            "binary",
            "primer3_core",
            "validated Primer3 oligonucleotide design",
            "Install Primer3 core",
        ),
        (
            "blastn",
            "External",
            "binary",
            "blastn",
            "NCBI BLAST sequence search",
            "Install NCBI BLAST+",
        ),
        ("mafft", "External", "binary", "mafft", "multiple sequence alignment", "Install MAFFT"),
        ("hmmscan", "External", "binary", "hmmscan", "profile-HMM/Pfam search", "Install HMMER"),
        (
            "mmseqs",
            "External",
            "binary",
            "mmseqs",
            "large-scale sequence clustering/search",
            "Install MMseqs2",
        ),
        (
            "minimap2",
            "External",
            "binary",
            "minimap2",
            "long-read/genome alignment",
            "Install minimap2",
        ),
        (
            "samtools",
            "External",
            "binary",
            "samtools",
            "SAM/BAM/CRAM processing",
            "Install samtools",
        ),
        (
            "bcftools",
            "External",
            "binary",
            "bcftools",
            "variant calling/filtering",
            "Install bcftools",
        ),
        ("fastqc", "External", "binary", "fastqc", "FASTQ quality-control reports", "Install FastQC"),
        ("fastp", "External", "binary", "fastp", "streaming read trimming and filtering", "Install fastp"),
        ("multiqc", "External", "binary", "multiqc", "multi-sample QC aggregation", "Install MultiQC"),
        ("bowtie2", "External", "binary", "bowtie2", "host-read depletion and short-read alignment", "Install Bowtie2"),
        ("kraken2", "External", "binary", "kraken2", "k-mer taxonomic classification", "Install Kraken2 and a licensed/current database"),
        ("bracken", "External", "binary", "bracken", "species/genus abundance re-estimation", "Install Bracken"),
        ("metaphlan", "External", "binary", "metaphlan", "marker-based taxonomic profiling", "Install MetaPhlAn"),
        ("humann", "External", "binary", "humann", "microbial gene-family and pathway profiling", "Install HUMAnN"),
        ("FastANI", "External", "binary", "fastANI", "accepted whole-genome ANI calculation", "Install FastANI"),
        ("mash", "External", "binary", "mash", "rapid genome distance screening", "Install Mash"),
        ("prokka", "External", "binary", "prokka", "prokaryotic genome annotation", "Install Prokka or Bakta"),
        ("amrfinder", "External", "binary", "amrfinder", "AMR gene screening", "Install NCBI AMRFinderPlus"),
        ("iqtree2", "External", "binary", "iqtree2", "maximum-likelihood phylogeny", "Install IQ-TREE 2"),
        ("vep", "External", "binary", "vep", "variant consequence annotation", "Install Ensembl VEP"),
        ("snpEff", "External", "binary", "snpEff", "variant effect annotation", "Install SnpEff"),
        ("vina", "External", "binary", "vina", "molecular docking", "Install AutoDock Vina"),
    ]
    result = []
    for name, category, kind, probe, purpose, hint in definitions:
        available = bool(find_spec(probe)) if kind == "module" else tool_available(probe)
        result.append(Capability(name, category, available, probe, purpose, hint))
    return result


def capabilities_dict():
    return [asdict(item) for item in bioinformatics_capabilities()]
