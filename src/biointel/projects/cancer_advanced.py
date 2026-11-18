from __future__ import annotations

import numpy as np
import pandas as pd

CANCER_REFERENCE_VERSION = "BioIntel research cancer-gene pack 2026.07-v1"

# Research-oriented role/pathway metadata only. This is intentionally not a clinical
# actionability or pathogenicity knowledge base.
_GENE_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "DNA damage and repair": (
        "Tumor suppressor",
        (
            "TP53",
            "ATM",
            "ATR",
            "CHEK1",
            "CHEK2",
            "BRCA1",
            "BRCA2",
            "PALB2",
            "RAD51C",
            "RAD51D",
            "BARD1",
            "BRIP1",
            "MRE11",
            "NBN",
            "FANCA",
            "FANCC",
            "FANCD2",
            "FANCE",
            "FANCF",
            "ERCC2",
            "ERCC3",
            "ERCC4",
            "ERCC5",
            "POLE",
            "POLD1",
            "MUTYH",
        ),
    ),
    "Mismatch repair": ("Tumor suppressor", ("MLH1", "MSH2", "MSH6", "PMS2", "EPCAM")),
    "RAS/MAPK": (
        "Oncogene",
        ("KRAS", "NRAS", "HRAS", "BRAF", "RAF1", "MAP2K1", "MAP2K2", "NF1", "RASA1"),
    ),
    "PI3K/AKT/mTOR": (
        "Mixed",
        ("PIK3CA", "PIK3R1", "AKT1", "AKT2", "MTOR", "PTEN", "TSC1", "TSC2", "STK11", "RHEB"),
    ),
    "RTK signaling": (
        "Oncogene",
        (
            "EGFR",
            "ERBB2",
            "ERBB3",
            "ERBB4",
            "MET",
            "ALK",
            "ROS1",
            "RET",
            "NTRK1",
            "NTRK2",
            "NTRK3",
            "FGFR1",
            "FGFR2",
            "FGFR3",
            "FGFR4",
            "KIT",
            "PDGFRA",
            "FLT3",
            "JAK2",
        ),
    ),
    "Cell cycle": (
        "Mixed",
        (
            "CDKN2A",
            "CDKN2B",
            "RB1",
            "CCND1",
            "CCND2",
            "CCND3",
            "CDK4",
            "CDK6",
            "CDKN1A",
            "CDKN1B",
            "E2F1",
        ),
    ),
    "WNT/beta-catenin": ("Mixed", ("APC", "CTNNB1", "AXIN1", "AXIN2", "RNF43", "GSK3B")),
    "Chromatin and epigenetics": (
        "Mixed",
        (
            "ARID1A",
            "ARID1B",
            "ARID2",
            "SMARCA4",
            "SMARCB1",
            "PBRM1",
            "KMT2A",
            "KMT2C",
            "KMT2D",
            "KDM6A",
            "EZH2",
            "TET2",
            "DNMT3A",
            "ASXL1",
            "IDH1",
            "IDH2",
        ),
    ),
    "Transcription and differentiation": (
        "Mixed",
        ("MYC", "MYCN", "MYCL", "RUNX1", "GATA2", "CEBPA", "NPM1", "WT1", "PAX5", "IKZF1", "ETV6"),
    ),
    "TGF-beta/SMAD": ("Mixed", ("TGFBR1", "TGFBR2", "SMAD2", "SMAD3", "SMAD4")),
    "Hippo": ("Mixed", ("NF2", "YAP1", "LATS1", "LATS2")),
    "Ubiquitin/proteostasis": ("Mixed", ("FBXW7", "VHL", "KEAP1", "CUL3", "SPOP")),
    "Apoptosis": ("Mixed", ("BCL2", "BCL6", "MCL1", "CASP8", "FAS")),
}


def expanded_cancer_gene_reference() -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for pathway, (role, genes) in _GENE_GROUPS.items():
        for gene in genes:
            rows.append(
                {
                    "gene": gene,
                    "research_role": role,
                    "pathway": pathway,
                    "reference_version": CANCER_REFERENCE_VERSION,
                    "evidence_scope": "Research gene-role metadata; no clinical actionability",
                }
            )
    return pd.DataFrame(rows).drop_duplicates("gene").sort_values("gene").reset_index(drop=True)


def annotate_research_gene_pack(variants: pd.DataFrame) -> pd.DataFrame:
    reference = expanded_cancer_gene_reference().set_index("gene")
    result = variants.copy()
    genes = result["gene"].astype(str).str.upper()
    result["research_reference_gene"] = genes.isin(reference.index)
    result["research_reference_role"] = genes.map(reference["research_role"]).fillna("Unclassified")
    result["research_reference_pathway"] = genes.map(reference["pathway"]).fillna("Other/unknown")
    result["research_reference_version"] = CANCER_REFERENCE_VERSION
    return result


def matched_normal_population_filter(
    variants: pd.DataFrame,
    *,
    maximum_normal_vaf: float = 0.02,
    maximum_population_af: float = 0.001,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = variants.copy()
    normal_candidates = ("normal_vaf", "matched_normal_vaf", "n_vaf", "normal_af")
    population_candidates = ("population_af", "gnomad_af", "pop_af", "af_population")
    normal_column = next((column for column in normal_candidates if column in result.columns), None)
    population_column = next(
        (column for column in population_candidates if column in result.columns), None
    )
    if normal_column:
        result["normal_vaf_screen"] = pd.to_numeric(result[normal_column], errors="coerce")
        result["passes_matched_normal_screen"] = result["normal_vaf_screen"].fillna(0) <= float(
            maximum_normal_vaf
        )
    else:
        result["normal_vaf_screen"] = np.nan
        result["passes_matched_normal_screen"] = True
    if population_column:
        result["population_af_screen"] = pd.to_numeric(result[population_column], errors="coerce")
        percentage = result["population_af_screen"] > 1
        result.loc[percentage, "population_af_screen"] /= 100.0
        result["passes_population_screen"] = result["population_af_screen"].fillna(0) <= float(
            maximum_population_af
        )
    else:
        result["population_af_screen"] = np.nan
        result["passes_population_screen"] = True
    result["passes_somatic_support_screen"] = (
        result["passes_matched_normal_screen"] & result["passes_population_screen"]
    )
    audit = pd.DataFrame(
        [
            (
                "Matched-normal VAF",
                normal_column or "not supplied",
                maximum_normal_vaf,
                int((~result["passes_matched_normal_screen"]).sum()),
            ),
            (
                "Population allele frequency",
                population_column or "not supplied",
                maximum_population_af,
                int((~result["passes_population_screen"]).sum()),
            ),
        ],
        columns=["screen", "input_column", "maximum_threshold", "variants_flagged"],
    )
    return result, audit


def sample_specific_tmb(
    variants: pd.DataFrame,
    callable_territory: pd.DataFrame | None,
    *,
    default_callable_megabases: float = 30.0,
) -> pd.DataFrame:
    if default_callable_megabases <= 0:
        raise ValueError("Default callable megabases must be positive.")
    passing = variants[variants.get("passes_qc", True)].copy()
    coding = passing[
        passing["consequence"]
        .astype(str)
        .isin(
            {
                "missense_variant",
                "stop_gained",
                "frameshift_variant",
                "splice_acceptor_variant",
                "splice_donor_variant",
                "inframe_insertion",
                "inframe_deletion",
                "protein_altering_variant",
            }
        )
    ]
    counts = coding.groupby("sample").size().rename("coding_mutations").reset_index()
    samples = pd.DataFrame({"sample": sorted(variants["sample"].astype(str).unique())})
    result = samples.merge(counts, on="sample", how="left").fillna({"coding_mutations": 0})
    if callable_territory is not None and not callable_territory.empty:
        territory = callable_territory.copy()
        if not {"sample", "callable_megabases"}.issubset(territory.columns):
            raise ValueError(
                "Callable-territory table requires sample and callable_megabases columns."
            )
        territory["sample"] = territory["sample"].astype(str)
        if territory["sample"].duplicated().any():
            raise ValueError("Callable-territory sample identifiers must be unique.")
        territory["callable_megabases"] = pd.to_numeric(
            territory["callable_megabases"], errors="coerce"
        )
        if (
            territory["callable_megabases"].isna().any()
            or (territory["callable_megabases"] <= 0).any()
        ):
            raise ValueError("Callable megabases must be positive numeric values.")
        result = result.merge(territory[["sample", "callable_megabases"]], on="sample", how="left")
    else:
        result["callable_megabases"] = float(default_callable_megabases)
    result["callable_megabases"] = result["callable_megabases"].fillna(
        float(default_callable_megabases)
    )
    result["tmb_mutations_per_mb"] = result["coding_mutations"] / result["callable_megabases"]
    result["tmb_scope"] = "Research screen; assay-specific validation required"
    return result


def estimate_cancer_cell_fraction(
    variants: pd.DataFrame,
    sample_metadata: pd.DataFrame,
    *,
    default_purity: float = 0.6,
    default_total_copy_number: float = 2.0,
    default_mutant_copy_number: float = 1.0,
) -> pd.DataFrame:
    metadata = sample_metadata.copy()
    if "sample" not in metadata.columns:
        raise ValueError("Sample metadata requires a sample column.")
    metadata["sample"] = metadata["sample"].astype(str)
    if metadata["sample"].duplicated().any():
        raise ValueError("Sample metadata identifiers must be unique.")
    for column, default in (
        ("purity", default_purity),
        ("total_copy_number", default_total_copy_number),
        ("mutant_copy_number", default_mutant_copy_number),
    ):
        if column not in metadata.columns:
            metadata[column] = default
        metadata[column] = pd.to_numeric(metadata[column], errors="coerce").fillna(default)
    if ((metadata["purity"] <= 0) | (metadata["purity"] > 1)).any():
        raise ValueError("Purity must be in (0, 1].")
    if (metadata[["total_copy_number", "mutant_copy_number"]] <= 0).any().any():
        raise ValueError("Copy-number assumptions must be positive.")
    result = variants.merge(
        metadata[["sample", "purity", "total_copy_number", "mutant_copy_number"]],
        on="sample",
        how="left",
    )
    result[["purity", "total_copy_number", "mutant_copy_number"]] = result[
        ["purity", "total_copy_number", "mutant_copy_number"]
    ].fillna(
        {
            "purity": default_purity,
            "total_copy_number": default_total_copy_number,
            "mutant_copy_number": default_mutant_copy_number,
        }
    )
    expected_denominator = result["purity"] * result["total_copy_number"] + 2.0 * (
        1.0 - result["purity"]
    )
    result["estimated_cancer_cell_fraction"] = (
        result["vaf"] * expected_denominator / (result["purity"] * result["mutant_copy_number"])
    ).clip(lower=0, upper=1.5)
    result["ccf_review_flag"] = result["estimated_cancer_cell_fraction"] > 1.05
    result["ccf_scope"] = (
        "Approximate CCF; validate local allele-specific copy number and multiplicity"
    )
    return result


def validate_cnv_table(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(
            columns=[
                "sample",
                "chromosome",
                "start",
                "end",
                "log2_ratio",
                "copy_number",
                "event",
                "length_bp",
            ]
        )
    result = frame.copy()
    required = {"sample", "chromosome", "start", "end"}
    missing = required.difference(result.columns)
    if missing:
        raise ValueError(f"CNV table missing: {', '.join(sorted(missing))}")
    result["start"] = pd.to_numeric(result["start"], errors="coerce")
    result["end"] = pd.to_numeric(result["end"], errors="coerce")
    if result[["start", "end"]].isna().any().any() or (result["end"] < result["start"]).any():
        raise ValueError("CNV coordinates must be valid numeric intervals.")
    if "log2_ratio" in result.columns:
        result["log2_ratio"] = pd.to_numeric(result["log2_ratio"], errors="coerce")
    else:
        result["log2_ratio"] = np.nan
    if "copy_number" in result.columns:
        result["copy_number"] = pd.to_numeric(result["copy_number"], errors="coerce")
    else:
        result["copy_number"] = 2 * np.power(2.0, result["log2_ratio"].fillna(0))
    result["event"] = np.select(
        [result["copy_number"] < 1.5, result["copy_number"] > 2.5],
        ["loss", "gain"],
        default="neutral",
    )
    result["length_bp"] = result["end"] - result["start"] + 1
    return result


def validate_sv_fusion_table(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(
            columns=["sample", "event_type", "gene_1", "gene_2", "support", "passes_support"]
        )
    result = frame.copy()
    if "sample" not in result.columns:
        raise ValueError("SV/fusion table requires a sample column.")
    if "event_type" not in result.columns:
        result["event_type"] = "unspecified"
    if "gene_1" not in result.columns:
        result["gene_1"] = result.get("gene", "")
    if "gene_2" not in result.columns:
        result["gene_2"] = ""
    support_column = next(
        (
            column
            for column in ("support", "supporting_reads", "split_reads", "read_support")
            if column in result.columns
        ),
        None,
    )
    result["support"] = (
        pd.to_numeric(result[support_column], errors="coerce").fillna(0) if support_column else 0
    )
    result["passes_support"] = result["support"] >= 3
    result["event_label"] = result["gene_1"].astype(str) + np.where(
        result["gene_2"].astype(str).ne(""), "--" + result["gene_2"].astype(str), ""
    )
    return result


def trinucleotide_signature_matrix(variants: pd.DataFrame) -> pd.DataFrame:
    """Build SBS-96 channels when a trinucleotide/context column is available."""

    context_column = next(
        (
            column
            for column in ("trinucleotide_context", "context", "sequence_context")
            if column in variants.columns
        ),
        None,
    )
    if context_column is None:
        return pd.DataFrame(columns=["sample", "channel", "variants", "fraction"])
    rows: list[dict[str, object]] = []
    complements = str.maketrans("ACGT", "TGCA")
    for row in variants.itertuples(index=False):
        ref, alt = str(getattr(row, "ref", "")).upper(), str(getattr(row, "alt", "")).upper()
        context = str(getattr(row, context_column)).upper().replace("[", "").replace("]", "")
        bases = "".join(base for base in context if base in "ACGT")
        if len(ref) != 1 or len(alt) != 1 or len(bases) < 3 or ref == alt:
            continue
        tri = bases[len(bases) // 2 - 1 : len(bases) // 2 + 2]
        if len(tri) != 3:
            continue
        if ref in {"A", "G"}:
            ref = ref.translate(complements)
            alt = alt.translate(complements)
            tri = tri.translate(complements)[::-1]
        channel = f"{tri[0]}[{ref}>{alt}]{tri[2]}"
        rows.append({"sample": str(getattr(row, "sample", "Sample_1")), "channel": channel})
    if not rows:
        return pd.DataFrame(columns=["sample", "channel", "variants", "fraction"])
    result = (
        pd.DataFrame(rows).groupby(["sample", "channel"]).size().rename("variants").reset_index()
    )
    result["fraction"] = result["variants"] / result.groupby("sample")["variants"].transform("sum")
    return result


def msi_hrd_research_screen(
    variants: pd.DataFrame,
    cnv: pd.DataFrame | None = None,
) -> pd.DataFrame:
    cnv = validate_cnv_table(cnv)
    rows = []
    for sample, group in variants.groupby("sample"):
        group["consequence"].astype(str)
        indels = group[
            (group["ref"].astype(str).str.len() != 1) | (group["alt"].astype(str).str.len() != 1)
        ]
        repeat_mask = (
            group.get("repeat_context", pd.Series(False, index=group.index))
            .astype(str)
            .str.lower()
            .isin({"true", "1", "repeat", "microsatellite"})
        )
        repeat_indels = int((indels.index.to_series().isin(group.index[repeat_mask])).sum())
        repair_genes = {"BRCA1", "BRCA2", "PALB2", "RAD51C", "RAD51D", "ATM", "BARD1", "BRIP1"}
        hrd_gene_hits = int(group["gene"].astype(str).str.upper().isin(repair_genes).sum())
        sample_cnv = (
            cnv[cnv["sample"].astype(str) == str(sample)] if not cnv.empty else pd.DataFrame()
        )
        large_loh_like = (
            int(
                (
                    (sample_cnv.get("event", pd.Series(dtype=str)) == "loss")
                    & (sample_cnv.get("length_bp", pd.Series(dtype=float)) >= 10_000_000)
                ).sum()
            )
            if not sample_cnv.empty
            else 0
        )
        rows.append(
            {
                "sample": str(sample),
                "indels": int(len(indels)),
                "repeat_context_indels": repeat_indels,
                "msi_review_score": float(repeat_indels / max(len(group), 1)),
                "hr_repair_gene_hits": hrd_gene_hits,
                "large_loss_segments": large_loh_like,
                "hrd_review_score": float(hrd_gene_hits + 0.5 * large_loh_like),
                "scope": "Research triage only; validated MSI/HRD assays required",
            }
        )
    return pd.DataFrame(rows)
