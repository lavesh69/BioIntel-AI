from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from biointel.native.formats import NATIVE_FORMATS


@dataclass(frozen=True)
class AutoEnginePlan:
    plan_key: str
    label: str
    source_parameter: str
    compatible_extensions: tuple[str, ...]
    stdout_to_output: bool = False
    extra_parameters: tuple[tuple[str, object], ...] = ()
    required_reference_labels: tuple[str, ...] = ()

    def defaults(self) -> dict[str, object]:
        return dict(self.extra_parameters)


@dataclass(frozen=True)
class NativeModuleProfile:
    module_key: str
    preferred_viewer: str
    accepted_extensions: tuple[str, ...]
    format_keys: tuple[str, ...]
    engines: tuple[str, ...]
    auto_plans: tuple[AutoEnginePlan, ...]
    reference_assets: tuple[str, ...]
    native_features: tuple[str, ...]
    comparison_identifiers: tuple[str, ...]


def _extensions_for_formats(keys: Iterable[str]) -> set[str]:
    extensions: set[str] = set()
    for key in keys:
        spec = NATIVE_FORMATS.get(key)
        if spec:
            extensions.update(spec.extensions)
    return extensions


def _profile(
    module_key: str,
    preferred_viewer: str,
    format_keys: tuple[str, ...],
    *,
    extensions: tuple[str, ...] = (),
    engines: tuple[str, ...] = (),
    plans: tuple[AutoEnginePlan, ...] = (),
    references: tuple[str, ...] = (),
    features: tuple[str, ...] = (),
    identifiers: tuple[str, ...] = (),
) -> NativeModuleProfile:
    accepted = _extensions_for_formats(format_keys)
    accepted.update(item.lower().lstrip(".") for item in extensions)
    return NativeModuleProfile(
        module_key=module_key,
        preferred_viewer=preferred_viewer,
        accepted_extensions=tuple(sorted(accepted, key=lambda value: (value.count("."), value))),
        format_keys=format_keys,
        engines=engines,
        auto_plans=plans,
        reference_assets=references,
        native_features=features,
        comparison_identifiers=identifiers,
    )


NATIVE_PROFILES: dict[str, NativeModuleProfile] = {
    "population_gwas_peak": _profile(
        "population_gwas_peak",
        "genome_browser",
        ("vcf", "bcf", "ped", "tabular"),
        extensions=("pgen", "pvar", "psam", "bed", "bim", "fam"),
        engines=("plink2", "regenie", "saige", "bcftools", "tabix"),
        plans=(
            AutoEnginePlan("bcftools_stats", "BCFtools variant statistics", "vcf", ("vcf", "vcf.gz", "bcf")),
        ),
        references=("Reference FASTA", "Genome annotation", "Ancestry reference panel", "LD reference panel", "Allele-frequency panel"),
        features=("PLINK/VCF cohort intake", "indexed variant readiness", "ancestry and kinship context", "reference-locked association planning"),
        identifiers=("variant", "sample"),
    ),
    "epigenomics_peak": _profile(
        "epigenomics_peak",
        "genome_browser",
        ("bam", "cram", "bed", "bedmethyl", "gff", "tabular"),
        extensions=("bedgraph", "bigwig", "bw"),
        engines=("samtools", "macs2", "deeptools", "bedtools", "tabix"),
        plans=(
            AutoEnginePlan("samtools_index", "Index BAM/CRAM", "alignment", ("bam", "cram")),
            AutoEnginePlan("samtools_depth", "Alignment depth profile", "alignment", ("bam", "cram")),
            AutoEnginePlan("macs2_callpeak", "MACS2 peak calling", "treatment", ("bam", "bed", "bedpe"), extra_parameters=(("name", "biointel_peak_call"), ("genome_size", "hs"), ("format", "BAM"), ("q_value", 0.05))),
            AutoEnginePlan("deeptools_bamcoverage", "deepTools coverage track", "alignment", ("bam", "cram"), extra_parameters=(("bin_size", 50), ("normalization", "CPM"))),
        ),
        references=("Reference FASTA", "Genome annotation", "Motif library", "Chromatin-state atlas", "Blacklist regions"),
        features=("BAM/CRAM metadata intake", "bedMethyl parsing", "peak and signal-track readiness", "replicate-aware engine planning"),
        identifiers=("region", "sample"),
    ),
    "pharmacogenomics_peak": _profile(
        "pharmacogenomics_peak",
        "genome_browser",
        ("vcf", "bcf", "bam", "cram", "ped", "tabular"),
        engines=("bcftools", "whatshap", "vep"),
        plans=(
            AutoEnginePlan("bcftools_stats", "BCFtools call statistics", "vcf", ("vcf", "vcf.gz", "bcf")),
            AutoEnginePlan("samtools_depth", "Pharmacogene coverage depth", "alignment", ("bam", "cram")),
        ),
        references=("Reference FASTA", "Pharmacogene definitions", "Star-allele definitions", "Guideline snapshot", "Population frequency panel"),
        features=("variant and coverage intake", "copy-number readiness", "guideline-version locking", "manual diplotype review"),
        identifiers=("sample", "gene", "variant"),
    ),
    "structural_variant_peak": _profile(
        "structural_variant_peak",
        "genome_browser",
        ("vcf", "bcf", "bam", "cram", "bed", "tabular"),
        extensions=("bedpe",),
        engines=("sniffles", "expansionhunter", "samtools", "bcftools", "whatshap"),
        plans=(
            AutoEnginePlan("bcftools_stats", "BCFtools structural-call statistics", "vcf", ("vcf", "vcf.gz", "bcf")),
            AutoEnginePlan("samtools_depth", "Breakpoint-region depth", "alignment", ("bam", "cram")),
            AutoEnginePlan("sniffles_call", "Sniffles long-read SV calling", "alignment", ("bam", "cram"), extra_parameters=(("minsupport", 10),)),
        ),
        references=("Reference FASTA", "Repeat catalogue", "Gene annotation", "Population SV catalogue", "Mappability/segdup tracks"),
        features=("raw-read evidence readiness", "multi-caller normalization", "repeat-expansion planning", "orthogonal-validation manifest"),
        identifiers=("event_id", "sample"),
    ),
    "rna_splicing_peak": _profile(
        "rna_splicing_peak",
        "genome_browser",
        ("bam", "cram", "sam", "gff", "bed", "tabular"),
        engines=("samtools", "star", "rmats", "majiq", "suppa2"),
        plans=(
            AutoEnginePlan("samtools_index", "Index splice alignment", "alignment", ("bam", "cram")),
            AutoEnginePlan("samtools_depth", "Junction-region coverage", "alignment", ("bam", "cram")),
        ),
        references=("Reference FASTA", "Transcript annotation GTF", "Tissue splicing reference", "Protein-domain annotation"),
        features=("alignment/junction readiness", "transcript-version locking", "long-read isoform integration", "read-backed event review"),
        identifiers=("gene", "transcript", "event"),
    ),
    "immune_repertoire": _profile(
        "immune_repertoire",
        "single_cell",
        ("fasta", "fastq", "jsonl", "tabular"),
        extensions=("airr",),
        engines=("igblast", "anarci"),
        plans=(
            AutoEnginePlan("anarci_number", "ANARCI receptor numbering", "fasta", ("fa", "fasta", "faa"), extra_parameters=(("scheme", "imgt"),)),
        ),
        references=("AIRR schema", "IMGT germline database", "Public clonotype reference", "HLA reference"),
        features=("AIRR/VDJ intake", "paired-chain readiness", "lineage and SHM planning", "sampling-depth normalization"),
        identifiers=("clonotype", "sample"),
    ),
    "single_cell_multiome": _profile(
        "single_cell_multiome",
        "single_cell",
        ("h5ad", "hdf5", "mtx", "tabular"),
        extensions=("h5mu", "mudata"),
        engines=("scanpy", "scvelo"),
        references=("Genome annotation", "Peak set", "Cell-type reference atlas", "Motif library"),
        features=("H5AD/MuData inventory", "backed single-cell preview", "modality-aware QC", "joint-analysis readiness"),
        identifiers=("cell", "sample"),
    ),
    "proteogenomics_peak": _profile(
        "proteogenomics_peak",
        "mass_spectrometry",
        ("vcf", "bcf", "fasta", "mzml", "mgf", "tabular"),
        engines=("bcftools", "openms", "comet", "netmhcpan", "netmhciipan"),
        plans=(
            AutoEnginePlan("bcftools_stats", "Variant source statistics", "vcf", ("vcf", "vcf.gz", "bcf")),
            AutoEnginePlan("openms_fileinfo", "OpenMS mzML validation", "mzml", ("mzml", "mzml.gz")),
        ),
        references=("Reference proteome", "Transcript annotation", "HLA allele database", "Normal tissue atlas", "Search-engine parameter set"),
        features=("variant/proteome/MS intake", "spectrum evidence readiness", "HLA model readiness", "candidate adjudication"),
        identifiers=("variant", "peptide", "sample"),
    ),
    "gene_regulatory_network": _profile(
        "gene_regulatory_network",
        "multiomics",
        ("h5ad", "bed", "gff", "tabular"),
        engines=("scanpy", "deeptools", "bedtools"),
        references=("Motif library", "TF-target knowledgebase", "Genome annotation", "Chromatin accessibility tracks"),
        features=("multi-omic evidence intake", "edge-provenance locking", "bootstrap network planning", "perturbation scenario manifest"),
        identifiers=("tf", "target", "sample"),
    ),
    "federated_genomic_discovery": _profile(
        "federated_genomic_discovery",
        "static_reporting",
        ("jsonl", "yaml", "tabular"),
        extensions=("json", "phenopacket.json"),
        references=("HPO release", "GA4GH VRS schema", "Beacon endpoint registry", "Consent/data-use policy"),
        features=("Phenopacket validation", "federated query manifest", "consent-aware review", "source response audit"),
        identifiers=("case_id", "source"),
    ),
    "viral_within_host": _profile(
        "viral_within_host",
        "genome_browser",
        ("fastq", "fasta", "vcf", "bcf", "bam", "cram", "tabular"),
        engines=("minimap2", "samtools", "bcftools", "mafft", "iqtree"),
        plans=(
            AutoEnginePlan("bcftools_stats", "Viral VCF statistics", "vcf", ("vcf", "vcf.gz", "bcf")),
            AutoEnginePlan("mafft_align", "MAFFT sequence alignment", "fasta", ("fa", "fasta", "fna", "faa"), stdout_to_output=True),
            AutoEnginePlan("samtools_depth", "Viral alignment depth", "alignment", ("bam", "cram")),
        ),
        references=("Viral reference genome", "Primer scheme", "Lineage database", "Resistance catalogue", "Antigenic-site annotation"),
        features=("raw-read/consensus intake", "primer-dropout readiness", "minor-variant manifest", "phylogeny and lineage planning"),
        identifiers=("subject", "position", "time"),
    ),
    "genome_annotation": _profile(
        "genome_annotation",
        "genome_browser",
        ("fasta", "genbank", "gff", "tabular"),
        engines=("busco", "vep"),
        plans=(
            AutoEnginePlan("busco_assembly", "BUSCO annotation/assembly completeness", "assembly", ("fa", "fasta", "fna"), extra_parameters=(("lineage", "eukaryota_odb10"), ("output_name", "biointel_busco"))),
        ),
        references=("Reference assembly", "Protein evidence", "RNA evidence", "BUSCO lineage", "Functional database releases"),
        features=("FASTA/GFF compatibility", "gene-model evidence review", "annotation transfer planning", "curated GFF export readiness"),
        identifiers=("feature_id", "genome"),
    ),
    "circular_dna_instability": _profile(
        "circular_dna_instability",
        "genome_browser",
        ("vcf", "bcf", "bam", "cram", "bed", "tabular"),
        extensions=("bedpe",),
        engines=("samtools", "bcftools", "sniffles"),
        plans=(
            AutoEnginePlan("bcftools_stats", "Instability-call statistics", "vcf", ("vcf", "vcf.gz", "bcf")),
            AutoEnginePlan("samtools_depth", "Amplicon depth profile", "alignment", ("bam", "cram")),
            AutoEnginePlan("sniffles_call", "Sniffles rearrangement calling", "alignment", ("bam", "cram"), extra_parameters=(("minsupport", 10),)),
        ),
        references=("Reference FASTA", "Gene annotation", "Cancer gene census", "Segmental duplications", "Viral integration reference"),
        features=("breakpoint and copy-number intake", "amplicon topology readiness", "ecDNA/BFB evidence review", "cohort recurrence comparison"),
        identifiers=("event_id", "sample"),
    ),
    "environmental_edna": _profile(
        "environmental_edna",
        "multiomics",
        ("fastq", "fasta", "tabular"),
        engines=("kraken2", "bracken", "humann"),
        references=("Taxonomic reference library", "Marker-gene database", "Contaminant database", "Site metadata dictionary"),
        features=("raw-read/count-table intake", "field/lab control audit", "reference coverage review", "occupancy-analysis readiness"),
        identifiers=("sample", "species", "site"),
    ),
    "comparative_regulatory_genomics": _profile(
        "comparative_regulatory_genomics",
        "genome_browser",
        ("bed", "gff", "fasta", "tabular"),
        extensions=("bedgraph", "bigwig", "bw"),
        engines=("bedtools", "mafft", "deeptools"),
        references=("Multi-species assemblies", "Whole-genome alignment", "Orthology map", "Motif library", "Constraint tracks"),
        features=("multi-species region intake", "lift-over readiness", "orthologous peak matching", "regulatory gain/loss review"),
        identifiers=("species", "region", "ortholog_group"),
    ),
}


def profile_for(module_key: str) -> NativeModuleProfile:
    try:
        return NATIVE_PROFILES[module_key]
    except KeyError as exc:
        raise KeyError(f"No native Step 139 profile is registered for {module_key}") from exc


def streamlit_upload_types(module_key: str) -> list[str]:
    values: set[str] = set()
    for extension in profile_for(module_key).accepted_extensions:
        cleaned = extension.lower().lstrip(".")
        values.add(cleaned)
        if "." in cleaned:
            values.add(cleaned.rsplit(".", 1)[-1])
    return sorted(values)


def compound_suffix(name: str) -> str:
    lower = Path(name).name.lower()
    known = sorted({extension for profile in NATIVE_PROFILES.values() for extension in profile.accepted_extensions}, key=len, reverse=True)
    for extension in known:
        if lower == extension or lower.endswith("." + extension):
            return extension
    return lower.rsplit(".", 1)[-1] if "." in lower else ""


__all__ = [
    "AutoEnginePlan",
    "NativeModuleProfile",
    "NATIVE_PROFILES",
    "compound_suffix",
    "profile_for",
    "streamlit_upload_types",
]
