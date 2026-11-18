from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from biointel.neuro_cns.data import targets
from biointel.neuro_cns.schemas import table_quality_report


NEURO_GENES = {str(row.get("gene", "")).upper() for row in targets()}
NEURO_GENES.update(
    {
        "MECP2", "FMR1", "DMD", "SMN1", "SMN2", "C9ORF72", "TARDBP", "FUS", "PSEN1", "PSEN2",
        "PRNP", "ATP1A3", "ATP7B", "PARK7", "PINK1", "PRKN", "GBA1", "GRN", "TBK1", "TSC1", "TSC2",
        "DEPDC5", "PCDH19", "STXBP1", "SCN2A", "SCN8A", "KCNT1", "KCNQ3", "CACNA1A", "CACNA2D2",
    }
)

HIGH_IMPACT = {"stop_gained", "frameshift_variant", "splice_acceptor_variant", "splice_donor_variant", "start_lost"}
MODERATE_IMPACT = {"missense_variant", "inframe_deletion", "inframe_insertion", "protein_altering_variant"}
PATHOGENIC_TERMS = {"pathogenic", "likely pathogenic", "pathogenic/likely pathogenic"}
BENIGN_TERMS = {"benign", "likely benign", "benign/likely benign"}


def parse_vcf_text(text: str) -> pd.DataFrame:
    header: list[str] | None = None
    rows: list[list[str]] = []
    metadata: dict[str, Any] = {"reference": None, "contigs": [], "info_fields": []}
    for raw in str(text or "").splitlines():
        line = raw.rstrip("\n")
        if not line:
            continue
        if line.startswith("##reference="):
            metadata["reference"] = line.split("=", 1)[1]
            continue
        if line.startswith("##contig="):
            metadata["contigs"].append(line)
            continue
        if line.startswith("##INFO="):
            metadata["info_fields"].append(line)
            continue
        if line.startswith("##"):
            continue
        if line.startswith("#CHROM"):
            header = line.lstrip("#").split("\t")
            continue
        if line.startswith("#"):
            continue
        rows.append(line.split("\t"))
    if not rows:
        frame = pd.DataFrame()
        frame.attrs["vcf_metadata"] = metadata
        return frame
    if header is None:
        header = ["CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"][: len(rows[0])]
    width = max(len(header), max(len(row) for row in rows))
    header = header + [f"EXTRA_{index}" for index in range(len(header), width)]
    padded = [row + [""] * (width - len(row)) for row in rows]
    frame = pd.DataFrame(padded, columns=header)
    if "INFO" in frame:
        info = frame["INFO"].fillna("").astype(str)
        for key in ("GENE", "SYMBOL", "CONSEQUENCE", "CLINVAR", "AF", "INHERITANCE", "HPO_MATCH", "SVTYPE", "END"):
            frame[key.lower()] = info.str.extract(rf"(?:^|;){key}=([^;]+)", expand=False)
    frame.attrs["vcf_metadata"] = metadata
    return frame


def _first(row: pd.Series, names: tuple[str, ...], default: Any = None) -> Any:
    lower = {str(column).lower(): column for column in row.index}
    for name in names:
        column = lower.get(name.lower())
        if column is not None and pd.notna(row[column]) and str(row[column]).strip() != "":
            return row[column]
    return default


def prioritize_variants(
    frame: pd.DataFrame,
    *,
    genome_build: str = "unspecified",
    minimum_quality: float = 0.0,
    require_pass_filter: bool = False,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["gene", "priority_score", "priority_band", "reasons"])
    quality = table_quality_report(frame)
    output: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        gene = str(_first(row, ("gene", "symbol", "gene_symbol"), "")).strip().upper()
        consequence = str(_first(row, ("consequence", "effect", "annotation"), "unknown")).strip().lower()
        clinvar = str(_first(row, ("clinvar", "clinical_significance", "classification"), "unreported")).strip().lower()
        inheritance = str(_first(row, ("inheritance", "mode_of_inheritance"), "unspecified")).strip().lower()
        zygosity = str(_first(row, ("zygosity", "genotype"), "unspecified")).strip().lower()
        filter_status = str(_first(row, ("filter", "filter_status"), "unspecified")).strip()
        raw_quality = _first(row, ("qual", "quality"), np.nan)
        try:
            variant_quality = float(raw_quality)
        except (TypeError, ValueError):
            variant_quality = float("nan")
        try:
            phenotype = float(_first(row, ("hpo_match", "phenotype_match", "phenotype_score"), 0.0) or 0.0)
        except (TypeError, ValueError):
            phenotype = 0.0
        raw_af = _first(row, ("af", "allele_frequency", "gnomad_af"), np.nan)
        try:
            allele_frequency = float(str(raw_af).split(",")[0])
        except (TypeError, ValueError):
            allele_frequency = float("nan")

        ref = str(_first(row, ("ref", "reference"), ""))
        alt = str(_first(row, ("alt", "alternate"), ""))
        svtype = str(_first(row, ("svtype", "variant_type"), "")).upper()
        if svtype:
            variant_type = svtype
        elif len(ref) == 1 and len(alt) == 1:
            variant_type = "SNV"
        elif ref and alt:
            variant_type = "INDEL"
        else:
            variant_type = "UNKNOWN"

        score = 0.0
        reasons: list[str] = []
        evidence_components: dict[str, float] = {}
        qc_flags: list[str] = []
        if require_pass_filter and filter_status.upper() not in {"PASS", "."}:
            qc_flags.append("non-PASS FILTER")
        if math.isfinite(variant_quality) and variant_quality < minimum_quality:
            qc_flags.append(f"QUAL below {minimum_quality:g}")
        if not gene:
            qc_flags.append("missing gene annotation")
        if not ref or not alt:
            qc_flags.append("missing REF/ALT")

        if gene in NEURO_GENES:
            evidence_components["neurological_gene_panel"] = 2.0
            reasons.append("neurological gene-panel match")
        if clinvar in PATHOGENIC_TERMS:
            evidence_components["uploaded_pathogenic_label"] = 4.0
            reasons.append("uploaded pathogenic/likely-pathogenic label")
        elif clinvar in BENIGN_TERMS:
            evidence_components["uploaded_benign_label"] = -4.0
            reasons.append("uploaded benign/likely-benign label")
        if consequence in HIGH_IMPACT:
            evidence_components["high_impact_consequence"] = 2.5
            reasons.append("high-impact consequence")
        elif consequence in MODERATE_IMPACT:
            evidence_components["protein_altering_consequence"] = 1.2
            reasons.append("protein-altering consequence")
        if math.isfinite(allele_frequency):
            if not 0 <= allele_frequency <= 1:
                qc_flags.append("allele frequency outside 0-1")
            elif allele_frequency <= 1e-5:
                evidence_components["very_rare_frequency"] = 1.6
                reasons.append("very rare population frequency")
            elif allele_frequency <= 1e-3:
                evidence_components["rare_frequency"] = 0.9
                reasons.append("rare population frequency")
            elif allele_frequency >= 0.05:
                evidence_components["common_frequency"] = -1.5
                reasons.append("common population frequency")
        if phenotype > 0:
            clipped = min(1.0, max(0.0, phenotype))
            evidence_components["phenotype_match"] = 2.0 * clipped
            reasons.append(f"phenotype match {clipped:.2f}")
        if "de novo" in inheritance or "de_novo" in inheritance:
            evidence_components["de_novo_context"] = 1.0
            reasons.append("de novo inheritance context")
        if "recessive" in inheritance and zygosity in {"homozygous", "compound_heterozygous", "hom"}:
            evidence_components["recessive_compatible"] = 0.8
            reasons.append("recessive-compatible zygosity")
        score = float(sum(evidence_components.values()))
        if qc_flags:
            score -= min(2.0, 0.4 * len(qc_flags))

        output.append({
            "source_row": int(index) + 1,
            "genome_build": genome_build,
            "chrom": _first(row, ("chrom", "#chrom", "chromosome")),
            "position": _first(row, ("pos", "position")),
            "ref": ref,
            "alt": alt,
            "variant_type": variant_type,
            "gene": gene,
            "consequence": consequence,
            "clinvar_uploaded": clinvar,
            "allele_frequency": allele_frequency,
            "inheritance": inheritance,
            "zygosity": zygosity,
            "filter_status": filter_status,
            "variant_quality": variant_quality,
            "phenotype_match": phenotype,
            "priority_score": round(score, 3),
            "priority_band": "high" if score >= 6 else "moderate" if score >= 3 else "low",
            "evidence_components": evidence_components,
            "reasons": "; ".join(reasons) if reasons else "no positive evidence in supplied annotations",
            "qc_flags": "; ".join(qc_flags) if qc_flags else "none",
            "input_table_fingerprint": quality.fingerprint_sha256,
            "scientific_boundary": "Research triage; not clinical classification, diagnosis or ACMG sign-out.",
        })
    result = pd.DataFrame(output)
    return result.sort_values(["priority_score", "gene"], ascending=[False, True], ignore_index=True)



def detect_genome_build(frame: pd.DataFrame, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Infer build labels from explicit metadata without pretending certainty."""
    metadata = dict(metadata or frame.attrs.get("vcf_metadata") or {})
    evidence: list[str] = []
    reference_text = str(metadata.get("reference") or "").lower()
    build = "unspecified"
    confidence = "low"
    if any(token in reference_text for token in ("grch38", "hg38", "b38")):
        build, confidence = "GRCh38", "high"
        evidence.append(f"VCF reference metadata: {metadata.get('reference')}")
    elif any(token in reference_text for token in ("grch37", "hg19", "b37")):
        build, confidence = "GRCh37", "high"
        evidence.append(f"VCF reference metadata: {metadata.get('reference')}")
    else:
        build_columns = [column for column in frame.columns if str(column).lower() in {"genome_build", "build", "assembly", "reference_genome"}]
        for column in build_columns:
            values = frame[column].dropna().astype(str).str.lower()
            joined = " ".join(values.head(20))
            if any(token in joined for token in ("grch38", "hg38", "b38")):
                build, confidence = "GRCh38", "medium"
                evidence.append(f"Column {column} contains GRCh38/hg38 labels")
                break
            if any(token in joined for token in ("grch37", "hg19", "b37")):
                build, confidence = "GRCh37", "medium"
                evidence.append(f"Column {column} contains GRCh37/hg19 labels")
                break
    if build == "unspecified":
        contigs = " ".join(str(value) for value in metadata.get("contigs", []))
        if "length=248956422" in contigs:
            build, confidence = "GRCh38", "medium"
            evidence.append("chr1 contig length matches GRCh38")
        elif "length=249250621" in contigs:
            build, confidence = "GRCh37", "medium"
            evidence.append("chr1 contig length matches GRCh37")
    return {
        "genome_build": build,
        "confidence": confidence,
        "evidence": evidence,
        "warning": None if build != "unspecified" else "Genome build could not be established; coordinate-based interpretation must remain blocked or explicitly user-specified.",
    }


def expand_multiallelic_variants(frame: pd.DataFrame) -> pd.DataFrame:
    """Expand comma-separated ALT alleles while preserving source-row provenance."""
    if frame.empty:
        return frame.copy()
    rows: list[dict[str, Any]] = []
    for source_index, row in frame.iterrows():
        record = row.to_dict()
        alt_value = str(_first(row, ("alt", "alternate"), "") or "")
        alts = [value.strip() for value in alt_value.split(",") if value.strip()] or [alt_value]
        af_value = _first(row, ("af", "allele_frequency", "gnomad_af"), np.nan)
        afs = [value.strip() for value in str(af_value).split(",")] if pd.notna(af_value) else []
        for allele_index, alt in enumerate(alts, start=1):
            expanded = dict(record)
            expanded["ALT"] = alt
            expanded["alt"] = alt
            expanded["source_row"] = int(source_index) + 1
            expanded["allele_index"] = allele_index
            expanded["original_alt"] = alt_value
            if allele_index <= len(afs):
                expanded["af"] = afs[allele_index - 1]
            rows.append(expanded)
    result = pd.DataFrame(rows)
    result.attrs.update(frame.attrs)
    return result


def _term_set(value: Any) -> set[str]:
    text = str(value or "").replace("|", ",").replace(";", ",")
    return {token.strip().lower() for token in text.split(",") if token.strip()}


def variant_interpretation_workflow(
    frame: pd.DataFrame,
    *,
    genome_build: str | None = None,
    phenotype_terms: list[str] | tuple[str, ...] = (),
    minimum_quality: float = 0.0,
    require_pass_filter: bool = False,
) -> dict[str, Any]:
    """Create a research-only, provenance-aware variant review package."""
    if frame.empty:
        raise ValueError("Variant table is empty.")
    expanded = expand_multiallelic_variants(frame)
    build_detection = detect_genome_build(expanded)
    selected_build = str(genome_build or "").strip()
    if selected_build and selected_build.lower() not in {"auto", "unspecified"}:
        build_detection = {
            "genome_build": selected_build,
            "confidence": "user_declared",
            "evidence": ["User-selected genome build"],
            "warning": "User-declared build was not independently verified from the file.",
        }
    selected_build = build_detection["genome_build"]

    requested_terms = {str(term).strip().lower() for term in phenotype_terms if str(term).strip()}
    phenotype_scores: list[float] = []
    phenotype_overlaps: list[str] = []
    for _, row in expanded.iterrows():
        supplied = _term_set(_first(row, ("hpo", "hpo_terms", "phenotypes", "phenotype_terms"), ""))
        overlap = sorted(requested_terms & supplied)
        score = len(overlap) / max(len(requested_terms), 1) if requested_terms else 0.0
        phenotype_scores.append(round(float(score), 6))
        phenotype_overlaps.append(", ".join(overlap))
    if requested_terms:
        expanded["hpo_match"] = phenotype_scores
        expanded["matched_phenotype_terms"] = phenotype_overlaps

    prioritized = prioritize_variants(
        expanded,
        genome_build=selected_build,
        minimum_quality=minimum_quality,
        require_pass_filter=require_pass_filter,
    )
    if prioritized.empty:
        return {
            "prioritized_variants": prioritized,
            "compound_heterozygous_candidates": pd.DataFrame(),
            "evidence_conflicts": pd.DataFrame(),
            "build_detection": build_detection,
            "scientific_boundary": "Research triage only; not clinical interpretation or ACMG sign-out.",
        }

    research_tags: list[str] = []
    conflicts: list[str] = []
    for _, row in prioritized.iterrows():
        tags: list[str] = []
        row_conflicts: list[str] = []
        consequence = str(row.get("consequence") or "").lower()
        clinvar = str(row.get("clinvar_uploaded") or "").lower()
        af = pd.to_numeric(pd.Series([row.get("allele_frequency")]), errors="coerce").iloc[0]
        phenotype = float(row.get("phenotype_match") or 0.0)
        if consequence in HIGH_IMPACT:
            tags.append("PVS1-like high-impact observation")
        if pd.notna(af) and float(af) <= 1e-5:
            tags.append("PM2-like rarity observation")
        if phenotype >= 0.75:
            tags.append("PP4-like phenotype consistency observation")
        if pd.notna(af) and float(af) >= 0.05:
            tags.append("BS1-like common-frequency observation")
        if clinvar in BENIGN_TERMS:
            tags.append("BP6-like uploaded benign assertion")
        if "conflict" in clinvar:
            row_conflicts.append("uploaded clinical significance reports conflicting interpretations")
        if clinvar in PATHOGENIC_TERMS and pd.notna(af) and float(af) >= 0.05:
            row_conflicts.append("pathogenic label conflicts with common population frequency")
        if clinvar in BENIGN_TERMS and consequence in HIGH_IMPACT and pd.notna(af) and float(af) <= 1e-5:
            row_conflicts.append("benign label conflicts with rare high-impact annotation")
        research_tags.append("; ".join(tags) if tags else "none")
        conflicts.append("; ".join(row_conflicts) if row_conflicts else "none")
    prioritized["research_evidence_tags_not_classification"] = research_tags
    prioritized["evidence_conflicts"] = conflicts

    compound_rows: list[dict[str, Any]] = []
    for gene, group in prioritized.groupby("gene"):
        if not gene or len(group) < 2:
            continue
        zygosity = group["zygosity"].astype(str).str.lower()
        rare = pd.to_numeric(group["allele_frequency"], errors="coerce").fillna(0.0) <= 0.01
        candidates = group.loc[zygosity.str.contains("het") & rare].sort_values("priority_score", ascending=False)
        if len(candidates) >= 2:
            top = candidates.head(4)
            compound_rows.append({
                "gene": gene,
                "candidate_variant_count": int(len(candidates)),
                "source_rows": ", ".join(top["source_row"].astype(str)),
                "combined_priority_score": round(float(top["priority_score"].head(2).sum()), 3),
                "review_status": "candidate pair; phase/parental confirmation required",
            })
    compound = pd.DataFrame(compound_rows)
    conflict_frame = prioritized.loc[prioritized["evidence_conflicts"] != "none", [
        "source_row", "gene", "chrom", "position", "ref", "alt", "evidence_conflicts"
    ]].reset_index(drop=True)
    qc_flags = prioritized["qc_flags"].fillna("none").astype(str)
    quality = table_quality_report(frame)
    return {
        "prioritized_variants": prioritized,
        "compound_heterozygous_candidates": compound,
        "evidence_conflicts": conflict_frame,
        "build_detection": build_detection,
        "input_summary": {
            "source_rows": int(len(frame)),
            "expanded_allele_rows": int(len(expanded)),
            "multi_allelic_expansion_count": int(max(0, len(expanded) - len(frame))),
            "variants_with_qc_flags": int((qc_flags != "none").sum()),
            "phenotype_terms_requested": sorted(requested_terms),
            "input_fingerprint_sha256": quality.fingerprint_sha256,
        },
        "scientific_boundary": "Research prioritization with ACMG-like evidence observations only; no clinical classification, diagnosis, pedigree confirmation or sign-out is produced.",
    }
