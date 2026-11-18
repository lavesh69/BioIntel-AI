from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.util import find_spec
import shutil


@dataclass(frozen=True)
class ToolRequirement:
    name: str
    probe: str
    kind: str
    purpose: str
    required: bool = False


_SHARED = (
    ToolRequirement("pandas", "pandas", "python", "bounded tabular analysis", True),
    ToolRequirement("NumPy", "numpy", "python", "numeric transforms and embeddings", True),
    ToolRequirement("SciPy", "scipy", "python", "statistical screening", True),
    ToolRequirement("Plotly", "plotly", "python", "interactive scientific visuals", True),
)

TOOL_REQUIREMENTS: dict[str, tuple[ToolRequirement, ...]] = {
    "population_gwas_peak": (
        ToolRequirement("PLINK 2", "plink2", "binary", "genotype QC and association models"),
        ToolRequirement("REGENIE", "regenie", "binary", "large-cohort whole-genome regression"),
        ToolRequirement("BCFtools", "bcftools", "binary", "VCF harmonisation"),
    ),
    "epigenomics_peak": (
        ToolRequirement("MACS3", "macs3", "binary", "peak calling"),
        ToolRequirement("deepTools", "deeptools", "python", "coverage and heatmaps"),
        ToolRequirement("BEDTools", "bedtools", "binary", "genomic interval operations"),
    ),
    "pharmacogenomics_peak": (
        ToolRequirement("Aldy", "aldy", "binary", "pharmacogene star-allele calling"),
        ToolRequirement("Stargazer", "stargazer", "binary", "pharmacogene haplotypes"),
        ToolRequirement("VEP", "vep", "binary", "variant annotation"),
    ),
    "structural_variant_peak": (
        ToolRequirement("SURVIVOR", "SURVIVOR", "binary", "SV caller merging"),
        ToolRequirement("ExpansionHunter", "ExpansionHunter", "binary", "repeat expansions"),
        ToolRequirement("CNVkit", "cnvkit.py", "binary", "copy-number analysis"),
    ),
    "rna_splicing_peak": (
        ToolRequirement("STAR", "STAR", "binary", "splice-aware alignment"),
        ToolRequirement("RegTools", "regtools", "binary", "junction extraction"),
        ToolRequirement("MAJIQ", "majiq", "binary", "local splicing variations"),
    ),
    "immune_repertoire": (
        ToolRequirement("MiXCR", "mixcr", "binary", "TCR/BCR clonotype assembly"),
        ToolRequirement("IgBLAST", "igblastn", "binary", "V(D)J annotation"),
        ToolRequirement("Scirpy", "scirpy", "python", "single-cell immune repertoire analysis"),
    ),
    "single_cell_multiome": (
        ToolRequirement("Scanpy", "scanpy", "python", "single-cell analysis"),
        ToolRequirement("MuData", "mudata", "python", "multimodal containers"),
        ToolRequirement("MuON", "muon", "python", "multimodal integration"),
    ),
    "proteogenomics_peak": (
        ToolRequirement("VEP", "vep", "binary", "variant consequences"),
        ToolRequirement("NetMHCpan", "netMHCpan", "binary", "HLA binding predictions"),
        ToolRequirement("MSFragger", "MSFragger", "binary", "proteomics peptide search"),
    ),
    "gene_regulatory_network": (
        ToolRequirement("pySCENIC", "pyscenic", "binary", "regulon inference"),
        ToolRequirement("HOMER", "findMotifsGenome.pl", "binary", "motif enrichment"),
        ToolRequirement("BEDTools", "bedtools", "binary", "peak-to-gene overlaps"),
    ),
    "federated_genomic_discovery": (
        ToolRequirement("Phenopackets", "phenopackets", "python", "machine-readable clinical phenotypes"),
        ToolRequirement("GA4GH VRS", "ga4gh.vrs", "python", "variant representation"),
    ),
    "viral_within_host": (
        ToolRequirement("iVar", "ivar", "binary", "viral consensus and variants"),
        ToolRequirement("Nextclade", "nextclade", "binary", "lineage and QC"),
        ToolRequirement("LoFreq", "lofreq", "binary", "low-frequency variants"),
    ),
    "genome_annotation": (
        ToolRequirement("BRAKER", "braker.pl", "binary", "eukaryotic gene annotation"),
        ToolRequirement("Bakta", "bakta", "binary", "prokaryotic annotation"),
        ToolRequirement("BUSCO", "busco", "binary", "annotation completeness"),
    ),
    "circular_dna_instability": (
        ToolRequirement("AmpliconArchitect", "AmpliconArchitect.py", "binary", "focal amplification reconstruction"),
        ToolRequirement("Circle-Map", "Circle-Map", "binary", "circular DNA detection"),
        ToolRequirement("MELT", "MELT", "binary", "mobile-element insertions"),
    ),
    "environmental_edna": (
        ToolRequirement("QIIME 2", "qiime", "binary", "metabarcoding workflows"),
        ToolRequirement("DADA2", "R", "binary", "ASV inference via R environment"),
        ToolRequirement("OBITools", "obi", "binary", "DNA metabarcoding processing"),
    ),
    "comparative_regulatory_genomics": (
        ToolRequirement("HAL tools", "halLiftover", "binary", "comparative genome coordinates"),
        ToolRequirement("BEDTools", "bedtools", "binary", "regulatory interval comparison"),
        ToolRequirement("phastCons", "phastCons", "binary", "evolutionary conservation"),
    ),
}


def readiness(module_key: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in (*_SHARED, *TOOL_REQUIREMENTS.get(module_key, ())):
        if item.kind == "python":
            try:
                available = find_spec(item.probe) is not None
            except (ModuleNotFoundError, ValueError):
                available = False
        else:
            available = shutil.which(item.probe) is not None
        payload = asdict(item)
        payload["available"] = available
        payload["status"] = "Available" if available else "Optional external tool not detected"
        rows.append(payload)
    return rows
