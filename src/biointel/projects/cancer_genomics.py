from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REQUIRED_VARIANT_COLUMNS = ("chromosome", "position", "ref", "alt", "gene", "consequence", "vaf", "depth")

CANCER_GENE_REFERENCE: dict[str, dict[str, str]] = {
    "TP53": {"role": "Tumor suppressor", "pathway": "DNA damage response"},
    "KRAS": {"role": "Oncogene", "pathway": "RAS/MAPK"},
    "NRAS": {"role": "Oncogene", "pathway": "RAS/MAPK"},
    "BRAF": {"role": "Oncogene", "pathway": "RAS/MAPK"},
    "EGFR": {"role": "Oncogene", "pathway": "RTK signaling"},
    "ERBB2": {"role": "Oncogene", "pathway": "RTK signaling"},
    "PIK3CA": {"role": "Oncogene", "pathway": "PI3K/AKT/mTOR"},
    "PTEN": {"role": "Tumor suppressor", "pathway": "PI3K/AKT/mTOR"},
    "AKT1": {"role": "Oncogene", "pathway": "PI3K/AKT/mTOR"},
    "APC": {"role": "Tumor suppressor", "pathway": "WNT/beta-catenin"},
    "CTNNB1": {"role": "Oncogene", "pathway": "WNT/beta-catenin"},
    "BRCA1": {"role": "Tumor suppressor", "pathway": "Homologous recombination"},
    "BRCA2": {"role": "Tumor suppressor", "pathway": "Homologous recombination"},
    "ATM": {"role": "Tumor suppressor", "pathway": "DNA damage response"},
    "PALB2": {"role": "Tumor suppressor", "pathway": "Homologous recombination"},
    "CDKN2A": {"role": "Tumor suppressor", "pathway": "Cell cycle"},
    "RB1": {"role": "Tumor suppressor", "pathway": "Cell cycle"},
    "MYC": {"role": "Oncogene", "pathway": "Transcriptional control"},
    "IDH1": {"role": "Oncogene", "pathway": "Metabolism/epigenetics"},
    "IDH2": {"role": "Oncogene", "pathway": "Metabolism/epigenetics"},
    "NPM1": {"role": "Context-dependent", "pathway": "Myeloid differentiation"},
    "FLT3": {"role": "Oncogene", "pathway": "RTK signaling"},
}

HIGH_IMPACT = {
    "frameshift_variant",
    "stop_gained",
    "splice_acceptor_variant",
    "splice_donor_variant",
    "start_lost",
    "transcript_ablation",
}
MODERATE_IMPACT = {"missense_variant", "inframe_insertion", "inframe_deletion", "protein_altering_variant"}



PASS_FILTER_VALUES = {"PASS", ".", "TRUE"}


def source_filter_passes(values: pd.Series) -> pd.Series:
    """Normalize upstream caller filter semantics across all cancer workflows."""
    return values.astype(str).str.strip().str.upper().isin(PASS_FILTER_VALUES)

MAF_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "chromosome": ("Chromosome", "CHROM"),
    "position": ("Start_Position", "POS", "start"),
    "ref": ("Reference_Allele", "REF"),
    "alt": ("Tumor_Seq_Allele2", "ALT"),
    "gene": ("Hugo_Symbol", "SYMBOL", "Gene"),
    "consequence": ("Variant_Classification", "Consequence", "CSQ"),
    "vaf": ("tumor_vaf", "VAF", "AF", "t_vaf"),
    "depth": ("t_depth", "DP", "tumor_depth"),
    "sample": ("Tumor_Sample_Barcode", "SAMPLE", "sample_id"),
    "protein_change": ("HGVSp_Short", "HGVSp", "Protein_Change"),
    "filter": ("FILTER", "Filter"),
}

MAF_CONSEQUENCE_MAP = {
    "missense_mutation": "missense_variant",
    "nonsense_mutation": "stop_gained",
    "frame_shift_del": "frameshift_variant",
    "frame_shift_ins": "frameshift_variant",
    "splice_site": "splice_region_variant",
    "in_frame_del": "inframe_deletion",
    "in_frame_ins": "inframe_insertion",
    "translation_start_site": "start_lost",
    "silent": "synonymous_variant",
}


def standardize_variant_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Map common MAF/VCF-style tabular aliases into the project schema."""

    standardized = frame.copy()
    for canonical, aliases in MAF_COLUMN_ALIASES.items():
        if canonical in standardized.columns:
            continue
        match = next((alias for alias in aliases if alias in standardized.columns), None)
        if match is not None:
            standardized[canonical] = standardized[match]
    if "depth" not in standardized.columns:
        if {"t_ref_count", "t_alt_count"}.issubset(standardized.columns):
            standardized["depth"] = (
                pd.to_numeric(standardized["t_ref_count"], errors="coerce")
                + pd.to_numeric(standardized["t_alt_count"], errors="coerce")
            )
    if "vaf" not in standardized.columns and "t_alt_count" in standardized.columns:
        alt = pd.to_numeric(standardized["t_alt_count"], errors="coerce")
        depth = pd.to_numeric(standardized.get("depth"), errors="coerce")
        standardized["vaf"] = alt.divide(depth.replace(0, np.nan))
    if "consequence" in standardized.columns:
        normalized = standardized["consequence"].astype(str).str.strip().str.lower()
        standardized["consequence"] = normalized.map(MAF_CONSEQUENCE_MAP).fillna(normalized)
    return standardized


@dataclass(frozen=True)
class CancerGenomicsResult:
    variants: pd.DataFrame
    pathway_summary: pd.DataFrame
    gene_summary: pd.DataFrame
    sample_summary: pd.DataFrame
    metrics: dict[str, float | int | str]


def validate_variant_table(frame: pd.DataFrame) -> pd.DataFrame:
    frame = standardize_variant_columns(frame)
    missing = [column for column in REQUIRED_VARIANT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    cleaned = frame.copy()
    cleaned["chromosome"] = cleaned["chromosome"].astype(str).str.replace("chr", "", case=False, regex=False).str.strip()
    cleaned["position"] = pd.to_numeric(cleaned["position"], errors="coerce")
    cleaned["depth"] = pd.to_numeric(cleaned["depth"], errors="coerce")
    cleaned["vaf"] = pd.to_numeric(cleaned["vaf"], errors="coerce")
    cleaned["gene"] = cleaned["gene"].astype(str).str.upper().str.strip()
    cleaned["consequence"] = cleaned["consequence"].astype(str).str.lower().str.strip()
    cleaned["ref"] = cleaned["ref"].astype(str).str.upper().str.strip()
    cleaned["alt"] = cleaned["alt"].astype(str).str.upper().str.strip()
    numeric_values = cleaned[["position", "depth", "vaf"]].to_numpy(dtype=float)
    if cleaned[["position", "depth", "vaf"]].isna().any().any() or not np.all(np.isfinite(numeric_values)):
        raise ValueError("position, depth and vaf must be finite numeric values.")
    if cleaned["gene"].eq("").any() or cleaned["consequence"].eq("").any():
        raise ValueError("Gene and consequence values cannot be empty.")
    if cleaned["ref"].eq("").any() or cleaned["alt"].eq("").any():
        raise ValueError("Reference and alternate alleles cannot be empty.")
    allele_pattern = r"[ACGTN-]+"
    if not cleaned["ref"].str.fullmatch(allele_pattern).all() or not cleaned["alt"].str.fullmatch(allele_pattern).all():
        raise ValueError("Alleles may contain only A, C, G, T, N or '-'.")
    if (cleaned["ref"] == cleaned["alt"]).any():
        raise ValueError("Reference and alternate alleles must differ.")
    if not np.allclose(cleaned["position"], np.round(cleaned["position"])):
        raise ValueError("Variant positions must be integer-like.")
    if not np.allclose(cleaned["depth"], np.round(cleaned["depth"])):
        raise ValueError("Read depth must be integer-like.")
    if (cleaned["position"] <= 0).any() or (cleaned["depth"] < 0).any():
        raise ValueError("position must be positive and depth cannot be negative.")
    if (cleaned["vaf"] > 100).any():
        raise ValueError("vaf must be a fraction from 0 to 1 or a percentage from 0 to 100.")
    # Normalize row by row so mixed inputs such as 0.20 and 20 are both interpreted correctly.
    cleaned["vaf_original"] = cleaned["vaf"].astype(float)
    percentage_mask = cleaned["vaf"] > 1
    cleaned["vaf_input_unit"] = np.where(percentage_mask, "percent", "fraction")
    cleaned.loc[percentage_mask, "vaf"] = cleaned.loc[percentage_mask, "vaf"] / 100.0
    if (cleaned["vaf"] < 0).any() or (cleaned["vaf"] > 1).any():
        raise ValueError("vaf must be between 0 and 1.")
    if "sample" not in cleaned.columns:
        cleaned["sample"] = "Sample_1"
    else:
        cleaned["sample"] = cleaned["sample"].astype(str).str.strip()
        if cleaned["sample"].eq("").any():
            raise ValueError("Sample identifiers cannot be empty.")
    if "protein_change" not in cleaned.columns:
        cleaned["protein_change"] = ""
    if "filter" not in cleaned.columns:
        cleaned["filter"] = "PASS"
    cleaned["variant_id"] = (
        cleaned["chromosome"].astype(str)
        + ":"
        + cleaned["position"].astype(int).astype(str)
        + ":"
        + cleaned["ref"]
        + ">"
        + cleaned["alt"]
    )
    duplicate_key = ["sample", "variant_id"]
    duplicates = cleaned[cleaned.duplicated(duplicate_key, keep=False)]
    if not duplicates.empty:
        comparison_columns = ["depth", "vaf", "gene", "consequence", "filter"]
        conflicts = duplicates.groupby(duplicate_key, dropna=False)[comparison_columns].nunique(dropna=False)
        if (conflicts > 1).any(axis=None):
            raise ValueError("Conflicting duplicate sample/variant records were detected.")
    return cleaned.drop_duplicates(duplicate_key, keep="first").reset_index(drop=True)


def annotate_variants(
    frame: pd.DataFrame,
    *,
    min_depth: int = 30,
    min_vaf: float = 0.05,
) -> pd.DataFrame:
    variants = validate_variant_table(frame)
    variants["passes_qc"] = (
        (variants["depth"] >= min_depth)
        & (variants["vaf"] >= min_vaf)
        & source_filter_passes(variants["filter"])
    )
    variants["known_cancer_gene"] = variants["gene"].isin(CANCER_GENE_REFERENCE)
    variants["gene_role"] = variants["gene"].map(lambda gene: CANCER_GENE_REFERENCE.get(gene, {}).get("role", "Unclassified"))
    variants["pathway"] = variants["gene"].map(lambda gene: CANCER_GENE_REFERENCE.get(gene, {}).get("pathway", "Other/unknown"))
    variants["impact"] = np.select(
        [variants["consequence"].isin(HIGH_IMPACT), variants["consequence"].isin(MODERATE_IMPACT)],
        ["High", "Moderate"],
        default="Low/other",
    )
    impact_score = variants["impact"].map({"High": 3.0, "Moderate": 2.0, "Low/other": 0.5}).astype(float)
    gene_score = variants["known_cancer_gene"].astype(float) * 2.0
    vaf_score = np.minimum(variants["vaf"] / 0.25, 1.5)
    depth_score = np.minimum(variants["depth"] / 100.0, 1.0)
    variants["research_priority_score"] = (impact_score + gene_score + vaf_score + depth_score) * variants["passes_qc"].astype(float)
    variants["research_tier"] = pd.cut(
        variants["research_priority_score"],
        bins=[-np.inf, 2.0, 4.0, 6.0, np.inf],
        labels=["Tier 4 · low", "Tier 3 · review", "Tier 2 · elevated", "Tier 1 · high"],
    ).astype(str)
    variants["evidence_scope"] = "Research prioritization only"
    return variants.sort_values(["passes_qc", "research_priority_score"], ascending=[False, False]).reset_index(drop=True)


def run_cancer_genomics_pipeline(
    frame: pd.DataFrame,
    *,
    min_depth: int = 30,
    min_vaf: float = 0.05,
    callable_megabases: float = 30.0,
) -> CancerGenomicsResult:
    if callable_megabases <= 0:
        raise ValueError("Callable megabases must be positive.")
    variants = annotate_variants(frame, min_depth=min_depth, min_vaf=min_vaf)
    passing = variants[variants["passes_qc"]].copy()
    coding = passing[passing["consequence"].isin(HIGH_IMPACT | MODERATE_IMPACT)].copy()
    passing_summary = (
        passing.groupby("sample")
        .agg(
            passing_variants=("variant_id", "count"),
            coding_variants=("consequence", lambda series: int(series.isin(HIGH_IMPACT | MODERATE_IMPACT).sum())),
            high_priority_variants=("research_tier", lambda series: int(series.str.startswith("Tier 1").sum())),
            median_vaf=("vaf", "median"),
            median_depth=("depth", "median"),
        )
        .reset_index()
    )
    sample_summary = (
        variants.groupby("sample", as_index=False)
        .agg(input_variants=("variant_id", "count"))
        .merge(passing_summary, on="sample", how="left")
    )
    for column in ("passing_variants", "coding_variants", "high_priority_variants"):
        sample_summary[column] = sample_summary[column].fillna(0).astype(int)
    sample_summary["median_vaf"] = sample_summary["median_vaf"].fillna(0.0)
    sample_summary["median_depth"] = sample_summary["median_depth"].fillna(0.0)
    sample_summary["tmb_mutations_per_mb"] = sample_summary["coding_variants"] / float(callable_megabases)
    gene_summary = (
        passing.groupby(["gene", "gene_role", "pathway"], dropna=False)
        .agg(
            variants=("variant_id", "count"),
            samples=("sample", "nunique"),
            max_priority_score=("research_priority_score", "max"),
            median_vaf=("vaf", "median"),
        )
        .reset_index()
        .sort_values(["max_priority_score", "variants"], ascending=False)
    )
    pathway_summary = (
        passing.groupby("pathway", dropna=False)
        .agg(
            altered_genes=("gene", "nunique"),
            variants=("variant_id", "count"),
            samples=("sample", "nunique"),
            maximum_priority=("research_priority_score", "max"),
        )
        .reset_index()
        .sort_values(["variants", "maximum_priority"], ascending=False)
    )
    metrics: dict[str, float | int | str] = {
        "input_variants": len(variants),
        "qc_passing_variants": len(passing),
        "qc_pass_percent": len(passing) / max(len(variants), 1) * 100,
        "coding_variants": len(coding),
        "known_cancer_gene_variants": int(passing["known_cancer_gene"].sum()),
        "samples": int(variants["sample"].nunique()),
        "callable_megabases": float(callable_megabases),
        "maximum_research_tier": str(passing.iloc[0]["research_tier"]) if not passing.empty else "No passing variants",
    }
    return CancerGenomicsResult(variants, pathway_summary, gene_summary, sample_summary, metrics)


def demo_cancer_variants(*, samples: int = 8, variants_per_sample: int = 55, random_state: int = 31) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    driver_genes = list(CANCER_GENE_REFERENCE)
    background_genes = [f"GENE{index:03d}" for index in range(1, 121)]
    consequences = list(HIGH_IMPACT) + list(MODERATE_IMPACT) + ["synonymous_variant", "intron_variant"]
    rows = []
    for sample_index in range(samples):
        sample = f"TUMOR_{sample_index + 1:02d}"
        for variant_index in range(variants_per_sample):
            use_driver = rng.random() < 0.28
            gene = str(rng.choice(driver_genes if use_driver else background_genes))
            consequence = str(rng.choice(consequences, p=np.array([0.03] * len(HIGH_IMPACT) + [0.08] * len(MODERATE_IMPACT) + [0.17, 0.22]) / (0.03 * len(HIGH_IMPACT) + 0.08 * len(MODERATE_IMPACT) + 0.39)))
            ref = str(rng.choice(list("ACGT")))
            alt = str(rng.choice([base for base in "ACGT" if base != ref]))
            rows.append(
                {
                    "sample": sample,
                    "chromosome": str(rng.choice([*map(str, range(1, 23)), "X"])),
                    "position": int(rng.integers(10_000, 250_000_000)),
                    "ref": ref,
                    "alt": alt,
                    "gene": gene,
                    "consequence": consequence,
                    "protein_change": f"p.{rng.choice(list('ACDEFGHIKLMNPQRSTVWY'))}{int(rng.integers(10, 900))}{rng.choice(list('ACDEFGHIKLMNPQRSTVWY'))}",
                    "vaf": float(np.clip(rng.beta(2.2, 6.5), 0.01, 0.95)),
                    "depth": int(rng.integers(18, 420)),
                    "filter": "PASS" if rng.random() > 0.06 else "LowQual",
                    "source": "deterministic_demo",
                }
            )
    return pd.DataFrame(rows)


def variant_qc_report(frame: pd.DataFrame) -> pd.DataFrame:
    raw = frame.copy()
    if "sample" not in raw.columns:
        raw["sample"] = "Sample_1"
    duplicate_columns = [column for column in ("sample", "chromosome", "position", "ref", "alt") if column in raw.columns]
    duplicate_count = int(raw[duplicate_columns].astype(str).duplicated().sum()) if len(duplicate_columns) == 5 else 0
    validated = validate_variant_table(frame)
    rows = [
        {"check": "Variant records", "value": len(validated), "status": "Pass", "detail": "Rows passing schema validation after deterministic de-duplication"},
        {"check": "Samples", "value": validated["sample"].nunique(), "status": "Pass", "detail": "Distinct sample identifiers"},
        {"check": "Duplicate sample variants", "value": duplicate_count, "status": "Review" if duplicate_count else "Pass", "detail": "Same sample/locus/ref/alt repeated in the input"},
        {"check": "Non-PASS source filters", "value": int((~source_filter_passes(validated["filter"])).sum()), "status": "Review" if (~source_filter_passes(validated["filter"])).any() else "Pass", "detail": "Records flagged by upstream caller"},
        {"check": "Low depth (<20)", "value": int((validated["depth"] < 20).sum()), "status": "Review" if (validated["depth"] < 20).any() else "Pass", "detail": "Potentially unstable allele fractions"},
        {"check": "Low VAF (<0.05)", "value": int((validated["vaf"] < 0.05).sum()), "status": "Review" if (validated["vaf"] < 0.05).any() else "Pass", "detail": "Low-frequency research candidates"},
    ]
    return pd.DataFrame(rows)


def snv_spectrum(variants: pd.DataFrame) -> pd.DataFrame:
    frame = variants.copy()
    snv = frame[(frame["ref"].astype(str).str.len() == 1) & (frame["alt"].astype(str).str.len() == 1)].copy()
    complements = str.maketrans("ACGT", "TGCA")
    labels = []
    for row in snv.itertuples(index=False):
        ref = str(row.ref).upper()
        alt = str(row.alt).upper()
        if ref in {"A", "G"}:
            ref = ref.translate(complements)
            alt = alt.translate(complements)
        labels.append(f"{ref}>{alt}")
    snv["substitution_class"] = labels
    if snv.empty:
        return pd.DataFrame(columns=["sample", "substitution_class", "variants"])
    return snv.groupby(["sample", "substitution_class"], as_index=False).size().rename(columns={"size": "variants"})


def oncoprint_matrix(variants: pd.DataFrame, *, top_genes: int = 20) -> pd.DataFrame:
    passing = variants[variants.get("passes_qc", True)].copy()
    if passing.empty:
        return pd.DataFrame()
    genes = passing.groupby("gene").size().sort_values(ascending=False).head(top_genes).index
    subset = passing[passing["gene"].isin(genes)].copy()
    matrix = pd.crosstab(subset["gene"], subset["sample"])
    return (matrix > 0).astype(int).reset_index()


def gene_cooccurrence_matrix(variants: pd.DataFrame, *, top_genes: int = 15) -> pd.DataFrame:
    oncoprint = oncoprint_matrix(variants, top_genes=top_genes)
    if oncoprint.empty:
        return pd.DataFrame()
    matrix = oncoprint.set_index("gene").astype(int)
    cooccurrence = matrix @ matrix.T
    return cooccurrence


def clonality_screen(variants: pd.DataFrame) -> pd.DataFrame:
    passing = variants[variants.get("passes_qc", True)].copy()
    if passing.empty:
        return pd.DataFrame(columns=["sample", "clonal_like", "subclonal_like", "median_vaf", "high_vaf_fraction_percent"])
    passing["clonality_band"] = pd.cut(
        passing["vaf"], bins=[-np.inf, 0.10, 0.30, np.inf], labels=["Low-frequency", "Subclonal-like", "Clonal-like"]
    ).astype(str)
    rows = []
    for sample, group in passing.groupby("sample"):
        rows.append(
            {
                "sample": sample,
                "low_frequency": int((group["clonality_band"] == "Low-frequency").sum()),
                "subclonal_like": int((group["clonality_band"] == "Subclonal-like").sum()),
                "clonal_like": int((group["clonality_band"] == "Clonal-like").sum()),
                "median_vaf": float(group["vaf"].median()),
                "high_vaf_fraction_percent": float((group["vaf"] >= 0.30).mean() * 100),
            }
        )
    return pd.DataFrame(rows)


def threshold_sensitivity(
    frame: pd.DataFrame,
    *,
    depth_values: tuple[int, ...] = (20, 30, 50, 100),
    vaf_values: tuple[float, ...] = (0.03, 0.05, 0.10, 0.20),
) -> pd.DataFrame:
    validated = validate_variant_table(frame)
    rows = []
    for depth in depth_values:
        for vaf in vaf_values:
            passing = (validated["depth"] >= depth) & (validated["vaf"] >= vaf) & source_filter_passes(validated["filter"])
            rows.append(
                {
                    "minimum_depth": depth,
                    "minimum_vaf": vaf,
                    "passing_variants": int(passing.sum()),
                    "passing_percent": float(passing.mean() * 100),
                    "samples_with_variants": int(validated.loc[passing, "sample"].nunique()),
                }
            )
    return pd.DataFrame(rows)


def sample_variant_qc(variants: pd.DataFrame) -> pd.DataFrame:
    frame = variants.copy()
    rows = []
    for sample, group in frame.groupby("sample"):
        rows.append(
            {
                "sample": sample,
                "input_variants": len(group),
                "pass_filter_percent": float(source_filter_passes(group["filter"]).mean() * 100),
                "median_depth": float(group["depth"].median()),
                "median_vaf": float(group["vaf"].median()),
                "low_depth_percent": float((group["depth"] < 20).mean() * 100),
                "low_vaf_percent": float((group["vaf"] < 0.05).mean() * 100),
            }
        )
    return pd.DataFrame(rows)


def vaf_confidence_intervals(variants: pd.DataFrame, *, z: float = 1.96) -> pd.DataFrame:
    cleaned = validate_variant_table(variants)
    frame = cleaned.copy()
    alternate = np.rint(frame["vaf"].astype(float) * frame["depth"].astype(float)).clip(lower=0)
    total = frame["depth"].astype(float).clip(lower=1)
    p = alternate / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * np.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    frame["alternate_reads_estimated"] = alternate.astype(int)
    frame["vaf_ci95_lower"] = np.clip(centre - margin, 0, 1)
    frame["vaf_ci95_upper"] = np.clip(centre + margin, 0, 1)
    frame["vaf_ci95_width"] = frame["vaf_ci95_upper"] - frame["vaf_ci95_lower"]
    return frame


def recurrent_hotspot_screen(variants: pd.DataFrame) -> pd.DataFrame:
    cleaned = validate_variant_table(variants)
    key_columns = [column for column in ("chromosome", "position", "ref", "alt", "gene") if column in cleaned.columns]
    grouped = cleaned.groupby(key_columns, dropna=False).agg(samples=("sample", "nunique"), observations=("sample", "size"), mean_vaf=("vaf", "mean"), median_depth=("depth", "median")).reset_index()
    grouped["cohort_prevalence_percent"] = 100 * grouped["samples"] / max(cleaned["sample"].nunique(), 1)
    grouped["hotspot_tier"] = pd.cut(grouped["samples"], bins=[0, 1, 2, np.inf], labels=["singleton", "recurrent", "highly_recurrent"])
    return grouped.sort_values(["samples", "mean_vaf"], ascending=False).reset_index(drop=True)


def sample_mutation_similarity(variants: pd.DataFrame, *, top_genes: int = 50) -> pd.DataFrame:
    cleaned = validate_variant_table(variants)
    genes = cleaned["gene"].value_counts().head(top_genes).index
    matrix = pd.crosstab(cleaned["sample"], cleaned["gene"]).reindex(columns=genes, fill_value=0).gt(0).astype(int)
    samples = matrix.index.astype(str).tolist()
    result = pd.DataFrame(index=samples, columns=samples, dtype=float)
    for left in samples:
        a = set(matrix.columns[matrix.loc[left].astype(bool)])
        for right in samples:
            b = set(matrix.columns[matrix.loc[right].astype(bool)])
            result.loc[left, right] = len(a & b) / max(len(a | b), 1)
    result.index.name = "sample_id"
    return result.reset_index()


def gene_association_screen(variants: pd.DataFrame, *, top_genes: int = 20) -> pd.DataFrame:
    from scipy.stats import fisher_exact

    from biointel.projects.professional import benjamini_hochberg

    cleaned = validate_variant_table(variants)
    matrix = pd.crosstab(cleaned["sample"], cleaned["gene"]).gt(0).astype(int)
    genes = matrix.sum().sort_values(ascending=False).head(top_genes).index.tolist()
    rows = []
    n = len(matrix)
    for index, left in enumerate(genes):
        for right in genes[index + 1 :]:
            left_present = matrix[left] == 1
            right_present = matrix[right] == 1
            both = int((left_present & right_present).sum())
            left_only = int((left_present & ~right_present).sum())
            right_only = int((~left_present & right_present).sum())
            neither = int((~left_present & ~right_present).sum())
            expected = float(matrix[left].mean() * matrix[right].mean() * n)
            variance = max(expected * (1 - matrix[left].mean() * matrix[right].mean()), 1e-6)
            z_score = (both - expected) / np.sqrt(variance)
            odds_ratio, p_value = fisher_exact([[both, left_only], [right_only, neither]], alternative="two-sided")
            rows.append(
                {
                    "gene_a": left,
                    "gene_b": right,
                    "observed_co_mutated_samples": both,
                    "expected_co_mutated_samples": expected,
                    "association_z_score": float(z_score),
                    "fisher_odds_ratio": float(odds_ratio),
                    "fisher_p_value": float(p_value),
                }
            )
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    result["fdr_q_value"] = benjamini_hochberg(result["fisher_p_value"].to_numpy())
    result["association_type"] = np.select(
        [
            (result["fdr_q_value"] <= 0.10) & (result["fisher_odds_ratio"] > 1),
            (result["fdr_q_value"] <= 0.10) & (result["fisher_odds_ratio"] < 1),
        ],
        ["co_occurrence", "mutual_exclusion"],
        default="neutral",
    )
    return result.sort_values(["fdr_q_value", "association_z_score"], ascending=[True, False]).reset_index(drop=True)


def sample_quality_tiers(variants: pd.DataFrame) -> pd.DataFrame:
    cleaned = validate_variant_table(variants)
    summary = cleaned.groupby("sample").agg(variants=("gene", "size"), median_depth=("depth", "median"), median_vaf=("vaf", "median"), low_depth_percent=("depth", lambda values: 100 * float((values < 30).mean())), low_vaf_percent=("vaf", lambda values: 100 * float((values < 0.05).mean()))).reset_index()
    summary["quality_score"] = (100 - summary["low_depth_percent"] * 0.55 - summary["low_vaf_percent"] * 0.25).clip(0, 100)
    summary["quality_tier"] = pd.cut(summary["quality_score"], bins=[-1, 60, 80, 101], labels=["review", "acceptable", "strong"])
    return summary.sort_values("quality_score", ascending=False).reset_index(drop=True)


def six_class_signature_exposure(variants: pd.DataFrame) -> pd.DataFrame:
    spectrum = snv_spectrum(variants)
    if spectrum.empty:
        return pd.DataFrame(columns=["substitution", "count", "exposure_fraction", "exposure_percent", "interpretation"])
    aggregated = spectrum.groupby("substitution_class", as_index=False)["variants"].sum().rename(columns={"substitution_class": "substitution", "variants": "count"})
    total = max(float(aggregated["count"].sum()), 1.0)
    aggregated["exposure_fraction"] = aggregated["count"] / total
    aggregated["exposure_percent"] = 100 * aggregated["exposure_fraction"]
    aggregated["interpretation"] = "six_class_screen_not_COSMIC_signature_decomposition"
    return aggregated.sort_values("count", ascending=False).reset_index(drop=True)
