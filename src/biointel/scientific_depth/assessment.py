from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DepthAssessment:
    module_key: str
    summary: dict[str, Any]
    quality_checks: pd.DataFrame
    metrics: pd.DataFrame
    flagged_records: pd.DataFrame = field(default_factory=pd.DataFrame)
    recommendations: tuple[str, ...] = ()


def bh_fdr(p_values: pd.Series | list[float]) -> pd.Series:
    values = pd.to_numeric(pd.Series(p_values), errors="coerce")
    valid = values.notna() & values.between(0, 1)
    output = pd.Series(np.nan, index=values.index, dtype=float)
    if not valid.any():
        return output
    subset = values[valid]
    order = np.argsort(subset.to_numpy())
    ranked = subset.to_numpy()[order]
    n = len(ranked)
    adjusted = ranked * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0, 1)
    original_indices = subset.index.to_numpy()[order]
    output.loc[original_indices] = adjusted
    return output


def _robust_outlier_mask(series: pd.Series, threshold: float = 4.5) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    median = numeric.median()
    mad = (numeric - median).abs().median()
    if not np.isfinite(mad) or mad == 0:
        return pd.Series(False, index=series.index)
    score = 0.6745 * (numeric - median) / mad
    return score.abs() > threshold


def _common_checks(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]], pd.DataFrame]:
    rows = len(frame)
    columns = len(frame.columns)
    missing = int(frame.isna().sum().sum()) if not frame.empty else 0
    duplicate = int(frame.astype(str).duplicated().sum()) if not frame.empty else 0
    checks = [
        {"check": "Non-empty input", "status": "pass" if rows else "fail", "detail": f"{rows:,} records"},
        {"check": "Columns detected", "status": "pass" if columns else "fail", "detail": f"{columns:,} columns"},
        {"check": "Missing cells", "status": "pass" if missing == 0 else "review", "detail": f"{missing:,} missing cells"},
        {"check": "Duplicate rows", "status": "pass" if duplicate == 0 else "review", "detail": f"{duplicate:,} duplicate rows"},
    ]
    metrics = [
        {"metric": "records", "value": rows, "unit": "rows"},
        {"metric": "columns", "value": columns, "unit": "columns"},
        {"metric": "missing_fraction", "value": missing / max(rows * max(columns, 1), 1), "unit": "fraction"},
        {"metric": "duplicate_fraction", "value": duplicate / max(rows, 1), "unit": "fraction"},
    ]
    flagged = frame.loc[frame.astype(str).duplicated(keep=False)].head(250).copy() if duplicate else pd.DataFrame()
    return checks, metrics, flagged


def _sequence_liabilities(sequence: str) -> dict[str, Any]:
    seq = re.sub(r"[^ACDEFGHIKLMNPQRSTVWY]", "", str(sequence).upper())
    if not seq:
        return {"sequence_length": 0, "liability_count": 0, "hydrophobic_fraction": np.nan, "net_charge_proxy": np.nan}
    motifs = ("NG", "NS", "DG", "DP", "DD", "DS", "NT", "NN", "PP")
    liability_count = sum(seq.count(motif) for motif in motifs) + seq.count("M") + seq.count("W")
    hydrophobic = sum(seq.count(aa) for aa in "AILMFWVY") / len(seq)
    charge = (seq.count("K") + seq.count("R") + 0.1 * seq.count("H")) - (seq.count("D") + seq.count("E"))
    return {"sequence_length": len(seq), "liability_count": int(liability_count), "hydrophobic_fraction": hydrophobic, "net_charge_proxy": float(charge)}


def _add_domain_checks(module_key: str, frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> tuple[pd.DataFrame, list[str]]:
    recommendations: list[str] = []
    flagged = pd.DataFrame()
    lower = {str(column).lower(): column for column in frame.columns}

    def column(*names: str) -> str | None:
        for name in names:
            if name.lower() in lower:
                return lower[name.lower()]
        return None

    # Generic numeric outlier review.
    numeric_cols = list(frame.select_dtypes(include=[np.number]).columns)
    outlier_counts: dict[str, int] = {}
    for col in numeric_cols[:30]:
        count = int(_robust_outlier_mask(frame[col]).sum())
        if count:
            outlier_counts[str(col)] = count
    if outlier_counts:
        checks.append({"check": "Robust numeric outliers", "status": "review", "detail": "; ".join(f"{k}:{v}" for k, v in list(outlier_counts.items())[:8])})
        recommendations.append("Review robust numeric outliers before confirmatory modelling; do not delete them automatically.")
    else:
        checks.append({"check": "Robust numeric outliers", "status": "pass", "detail": "No strong MAD-based outliers in bounded numeric scan"})

    if module_key in {"antibody_biologics", "protein_language_design", "enzyme_pathway_design", "immunoinformatics_vaccine"}:
        seq_col = column("sequence", "peptide", "heavy_sequence", "protein_sequence")
        if seq_col:
            liabilities = frame[seq_col].fillna("").map(_sequence_liabilities).apply(pd.Series)
            metrics.extend([
                {"metric": "mean_sequence_length", "value": float(liabilities["sequence_length"].mean()), "unit": "residues"},
                {"metric": "mean_liability_count", "value": float(liabilities["liability_count"].mean()), "unit": "motifs"},
                {"metric": "high_hydrophobic_fraction", "value": int((liabilities["hydrophobic_fraction"] > 0.55).sum()), "unit": "records"},
            ])
            risky = liabilities["liability_count"].ge(4) | liabilities["hydrophobic_fraction"].gt(0.55)
            flagged = frame.loc[risky].head(250).copy()
            checks.append({"check": "Sequence developability screen", "status": "review" if risky.any() else "pass", "detail": f"{int(risky.sum())} candidates need liability review"})
            recommendations.append("Confirm sequence liabilities with a qualified numbering/developability workflow and experimental assays.")
        else:
            checks.append({"check": "Sequence-level evidence", "status": "review", "detail": "No sequence column detected"})

    if module_key == "metabolomics_lipidomics":
        feature_col = column("feature", "metabolite", "compound")
        intensity_col = column("intensity", "abundance", "area")
        blank_col = column("blank_intensity", "blank", "blank_area")
        if feature_col and intensity_col:
            numeric = pd.to_numeric(frame[intensity_col], errors="coerce")
            per_feature = frame.assign(_value=numeric).groupby(feature_col, dropna=False)["_value"].agg(["count", "mean", "std"])
            cv = per_feature["std"] / per_feature["mean"].abs().replace(0, np.nan)
            metrics.append({"metric": "features_with_cv_gt_30pct", "value": int((cv > 0.30).sum()), "unit": "features"})
            checks.append({"check": "Feature precision", "status": "review" if (cv > 0.30).any() else "pass", "detail": f"{int((cv > 0.30).sum())} features have CV >30%"})
            if blank_col:
                blank = pd.to_numeric(frame[blank_col], errors="coerce")
                ratio = blank / numeric.abs().replace(0, np.nan)
                metrics.append({"metric": "blank_ratio_gt_20pct", "value": int((ratio > 0.2).sum()), "unit": "records"})
                flagged = frame.loc[(ratio > 0.2).fillna(False)].head(250).copy()
            recommendations.extend(("Use pooled-QC and blank-aware filtering before differential analysis.", "Record identification confidence separately from statistical significance."))

    if module_key in {"single_cell_trajectory", "cell_atlas_mapping"}:
        cluster_col = column("cluster", "cell_type", "label")
        confidence_col = column("confidence", "annotation_confidence")
        if cluster_col:
            counts = frame[cluster_col].astype(str).value_counts()
            metrics.append({"metric": "clusters_or_labels", "value": int(len(counts)), "unit": "groups"})
            metrics.append({"metric": "small_groups_lt_20", "value": int((counts < 20).sum()), "unit": "groups"})
        if confidence_col:
            confidence = pd.to_numeric(frame[confidence_col], errors="coerce")
            low = confidence < 0.5
            checks.append({"check": "Annotation confidence", "status": "review" if low.any() else "pass", "detail": f"{int(low.sum())} cells below 0.5 confidence"})
            flagged = frame.loc[low.fillna(False)].head(250).copy()
        recommendations.append("Use biological replicates and pseudobulk or replicate-aware tests; cells are not independent replicates.")

    if module_key == "population_gwas":
        maf_col = column("maf", "minor_allele_frequency")
        missing_col = column("missingness", "call_rate")
        p_col = column("p_value", "pvalue", "p")
        if maf_col:
            maf = pd.to_numeric(frame[maf_col], errors="coerce")
            metrics.append({"metric": "variants_maf_lt_1pct", "value": int((maf < 0.01).sum()), "unit": "variants"})
        if missing_col:
            values = pd.to_numeric(frame[missing_col], errors="coerce")
            if "call_rate" in str(missing_col).lower():
                failed = values < 0.98
            else:
                failed = values > 0.02
            checks.append({"check": "Variant missingness/call rate", "status": "review" if failed.any() else "pass", "detail": f"{int(failed.sum())} variants outside 2% threshold"})
            flagged = frame.loc[failed.fillna(False)].head(250).copy()
        if p_col:
            q = bh_fdr(frame[p_col])
            metrics.append({"metric": "fdr_lt_0_05", "value": int((q < 0.05).sum()), "unit": "variants"})
        recommendations.extend(("Adjust association models for ancestry, relatedness and prespecified covariates.", "Replicate associations in an independent cohort."))

    if module_key == "structural_variant_repeat":
        svtype = column("svtype", "type")
        start = column("start", "pos", "position")
        end = column("end", "stop")
        if svtype:
            metrics.append({"metric": "sv_types", "value": int(frame[svtype].astype(str).nunique()), "unit": "types"})
        if start and end:
            size = (pd.to_numeric(frame[end], errors="coerce") - pd.to_numeric(frame[start], errors="coerce")).abs()
            invalid = size.le(0) | size.isna()
            checks.append({"check": "Breakpoint/interval validity", "status": "review" if invalid.any() else "pass", "detail": f"{int(invalid.sum())} invalid or missing intervals"})
            flagged = frame.loc[invalid].head(250).copy()
        recommendations.append("Inspect split-read/read-pair evidence and confirm clinically important SVs orthogonally.")

    if module_key == "longitudinal_multiomics":
        subject = column("subject", "patient", "sample_id")
        time_col = column("time", "visit", "timepoint")
        if subject and time_col:
            visits = frame.groupby(subject, dropna=False)[time_col].nunique()
            metrics.append({"metric": "subjects", "value": int(len(visits)), "unit": "subjects"})
            metrics.append({"metric": "subjects_with_one_visit", "value": int((visits < 2).sum()), "unit": "subjects"})
            duplicate_time = frame.astype({subject: str, time_col: str}).duplicated([subject, time_col], keep=False)
            checks.append({"check": "Subject-time uniqueness", "status": "review" if duplicate_time.any() else "pass", "detail": f"{int(duplicate_time.sum())} duplicate subject-time rows"})
            flagged = frame.loc[duplicate_time].head(250).copy()
        recommendations.append("Use mixed-effects or other repeated-measures models and report missing-visit assumptions.")

    if module_key in {"rna_isoform_splicing", "epitranscriptomics"}:
        psi_col = column("psi", "percent_spliced_in", "modification_fraction", "editing_fraction")
        if psi_col:
            values = pd.to_numeric(frame[psi_col], errors="coerce")
            invalid = ~values.between(0, 1)
            checks.append({"check": "Fraction bounds", "status": "review" if invalid.any() else "pass", "detail": f"{int(invalid.sum())} values outside [0,1]"})
            flagged = frame.loc[invalid.fillna(True)].head(250).copy()
        recommendations.append("Use strand-aware, coverage-aware and replicate-aware inference for site or junction conclusions.")

    if module_key in {"strain_microbiome", "one_health_environmental", "virology_evolution"}:
        sample = column("sample", "sample_id")
        taxon = column("taxon", "organism", "lineage", "variant")
        abundance = column("abundance", "relative_abundance", "frequency")
        if sample and taxon:
            richness = frame.groupby(sample, dropna=False)[taxon].nunique()
            metrics.append({"metric": "median_richness", "value": float(richness.median()), "unit": "features/sample"})
        if abundance:
            values = pd.to_numeric(frame[abundance], errors="coerce")
            outside = ~values.between(0, 1)
            checks.append({"check": "Abundance/frequency bounds", "status": "review" if outside.any() else "pass", "detail": f"{int(outside.sum())} values outside [0,1]"})
            flagged = frame.loc[outside.fillna(False)].head(250).copy()
        recommendations.append("Use contamination controls, pinned reference databases and replicate-aware compositional methods.")

    if module_key == "rare_variant_family":
        proband = column("proband_gt", "child_gt", "genotype")
        mother = column("mother_gt")
        father = column("father_gt")
        if proband and mother and father:
            p = frame[proband].astype(str)
            m = frame[mother].astype(str)
            f = frame[father].astype(str)
            de_novo = p.isin(["0/1", "1/1", "0|1", "1|0", "1|1"]) & m.isin(["0/0", "0|0"]) & f.isin(["0/0", "0|0"])
            metrics.append({"metric": "de_novo_candidates", "value": int(de_novo.sum()), "unit": "variants"})
            flagged = frame.loc[de_novo].head(250).copy()
        recommendations.append("Confirm pedigree identity, phasing, read evidence and inheritance with a qualified clinical workflow.")

    if module_key == "clinical_trial_biomarker":
        arm = column("arm", "treatment")
        event = column("event", "response")
        if arm:
            counts = frame[arm].astype(str).value_counts()
            metrics.append({"metric": "arms", "value": int(len(counts)), "unit": "groups"})
            imbalance = counts.max() / max(counts.min(), 1) if len(counts) > 1 else np.inf
            checks.append({"check": "Arm balance", "status": "review" if imbalance > 2 else "pass", "detail": f"max/min ratio {imbalance:.2f}"})
        if event:
            event_num = pd.to_numeric(frame[event], errors="coerce")
            metrics.append({"metric": "event_or_response_rate", "value": float(event_num.mean()), "unit": "fraction"})
        recommendations.append("Prespecify biomarker cut-offs and validate them in an independent cohort.")

    if module_key == "causal_perturbation":
        strength = column("instrument_strength", "f_statistic")
        p_col = column("p_value", "p")
        if strength:
            values = pd.to_numeric(frame[strength], errors="coerce")
            weak = values < 10
            checks.append({"check": "Instrument strength", "status": "review" if weak.any() else "pass", "detail": f"{int(weak.sum())} instruments below F=10"})
            flagged = frame.loc[weak.fillna(True)].head(250).copy()
        if p_col:
            q = bh_fdr(frame[p_col])
            metrics.append({"metric": "fdr_lt_0_05", "value": int((q < 0.05).sum()), "unit": "hypotheses"})
        recommendations.append("Run sensitivity analyses for pleiotropy, confounding and alternative model assumptions.")

    if module_key == "explainable_ai_assurance":
        pred = column("prediction", "probability")
        truth = column("truth", "label", "outcome")
        subgroup = column("subgroup", "group")
        if pred and truth:
            p = pd.to_numeric(frame[pred], errors="coerce").clip(0, 1)
            y = pd.to_numeric(frame[truth], errors="coerce")
            valid = p.notna() & y.isin([0, 1])
            if valid.any():
                brier = float(np.mean((p[valid] - y[valid]) ** 2))
                metrics.append({"metric": "brier_score", "value": brier, "unit": "score"})
        if subgroup and pred and truth:
            temp = frame.assign(_p=pd.to_numeric(frame[pred], errors="coerce"), _y=pd.to_numeric(frame[truth], errors="coerce"))
            group_error = temp.groupby(subgroup, dropna=False).apply(lambda g: float(np.nanmean(np.abs(g["_p"] - g["_y"]))))
            gap = float(group_error.max() - group_error.min()) if len(group_error) > 1 else 0.0
            metrics.append({"metric": "subgroup_absolute_error_gap", "value": gap, "unit": "score"})
            checks.append({"check": "Subgroup error gap", "status": "review" if gap > 0.1 else "pass", "detail": f"gap {gap:.3f}"})
        recommendations.append("Validate explanations for stability and evaluate calibration, OOD behaviour and subgroup performance.")

    if module_key == "bioprocess_fermentation":
        batch = column("batch", "reactor")
        time_col = column("time", "elapsed_time")
        if batch and time_col:
            bad_batches: list[str] = []
            for name, group in frame.groupby(batch, dropna=False):
                values = pd.to_numeric(group[time_col], errors="coerce")
                if values.isna().any() or not values.is_monotonic_increasing or values.duplicated().any():
                    bad_batches.append(str(name))
            checks.append({"check": "Batch-specific time order", "status": "review" if bad_batches else "pass", "detail": ", ".join(bad_batches[:10]) or "All batches have unique increasing time"})
            if bad_batches:
                flagged = frame.loc[frame[batch].astype(str).isin(bad_batches)].head(250).copy()
        recommendations.append("Model batches/reactors independently before comparing process summaries.")

    if module_key == "genome_editing_safety":
        guide = column("guide", "guide_rna", "sequence")
        off = column("off_target_count")
        if guide:
            valid = frame[guide].astype(str).str.upper().str.fullmatch(r"[ACGTUN]{17,30}", na=False)
            checks.append({"check": "Guide sequence syntax", "status": "review" if (~valid).any() else "pass", "detail": f"{int((~valid).sum())} invalid guide sequences"})
            flagged = frame.loc[~valid].head(250).copy()
        if off:
            values = pd.to_numeric(frame[off], errors="coerce")
            metrics.append({"metric": "guides_with_off_targets", "value": int((values > 0).sum()), "unit": "guides"})

    if module_key == "proteogenomics_neoantigen":
        evidence_columns = [c for c in (column("expression"), column("spectral_score"), column("hla_binding"), column("clonality")) if c]
        if evidence_columns:
            present = frame[evidence_columns].notna().sum(axis=1)
            metrics.append({"metric": "candidates_with_3plus_evidence_layers", "value": int((present >= 3).sum()), "unit": "candidates"})
            flagged = frame.loc[present < 2].head(250).copy()
            checks.append({"check": "Multi-layer support", "status": "review" if (present < 2).any() else "pass", "detail": f"{int((present < 2).sum())} candidates have <2 evidence layers"})

    if module_key == "epigenomics_chromatin":
        region = column("region", "peak", "locus")
        condition = column("condition", "group")
        sample = column("sample", "sample_id")
        signal = column("signal", "count", "accessibility")
        if region:
            parsed = frame[region].astype(str).str.extract(r"^([^:]+):(\d+)-(\d+)$")
            valid = parsed.notna().all(axis=1)
            widths = pd.to_numeric(parsed[2], errors="coerce") - pd.to_numeric(parsed[1], errors="coerce")
            invalid = (~valid) | widths.le(0)
            checks.append({"check": "Genomic region syntax", "status": "review" if invalid.any() else "pass", "detail": f"{int(invalid.sum())} invalid or non-positive regions"})
            metrics.append({"metric": "median_region_width", "value": float(widths[valid].median()) if valid.any() else np.nan, "unit": "bp"})
            if invalid.any():
                flagged = frame.loc[invalid].head(250).copy()
        if condition and sample:
            replicate_counts = frame.drop_duplicates([sample, condition]).groupby(condition)[sample].nunique()
            low_rep = replicate_counts < 2
            checks.append({"check": "Condition replicate coverage", "status": "review" if low_rep.any() else "pass", "detail": "; ".join(f"{idx}:{int(value)}" for idx, value in replicate_counts.items())})
            metrics.append({"metric": "minimum_replicates_per_condition", "value": int(replicate_counts.min()) if len(replicate_counts) else 0, "unit": "samples"})
        if signal:
            values = pd.to_numeric(frame[signal], errors="coerce")
            negative = values < 0
            checks.append({"check": "Signal non-negativity", "status": "review" if negative.any() else "pass", "detail": f"{int(negative.sum())} negative values"})
        recommendations.extend(("Pin genome build, annotation and peak-caller version in every result package.", "Use matched controls, replicate-aware statistics and an orthogonal confirmation plan."))

    if module_key == "bioimage_microscopy":
        image = column("image_id", "image", "field")
        obj = column("object_id", "object", "cell_id")
        condition = column("condition", "group")
        area = column("area", "object_area", "nucleus_area")
        calibration = column("pixel_size", "pixel_size_um", "microns_per_pixel")
        if image and obj:
            dup = frame.astype({image: str, obj: str}).duplicated([image, obj], keep=False)
            checks.append({"check": "Image-object identity", "status": "review" if dup.any() else "pass", "detail": f"{int(dup.sum())} duplicate image/object keys"})
            if dup.any():
                flagged = frame.loc[dup].head(250).copy()
        if area:
            values = pd.to_numeric(frame[area], errors="coerce")
            invalid = values.le(0) | values.isna()
            checks.append({"check": "Object area validity", "status": "review" if invalid.any() else "pass", "detail": f"{int(invalid.sum())} non-positive or missing areas"})
            metrics.append({"metric": "median_object_area", "value": float(values[values > 0].median()), "unit": "input units"})
        if condition and image:
            counts = frame.drop_duplicates(image).groupby(condition)[image].nunique()
            metrics.append({"metric": "images_per_condition_min", "value": int(counts.min()) if len(counts) else 0, "unit": "images"})
            checks.append({"check": "Image-level replication", "status": "review" if len(counts) < 2 or (counts < 2).any() else "pass", "detail": "; ".join(f"{idx}:{int(value)}" for idx, value in counts.items())})
        checks.append({"check": "Pixel calibration metadata", "status": "pass" if calibration else "review", "detail": str(calibration) if calibration else "No pixel-size column detected"})
        recommendations.extend(("Use image/field rather than segmented objects as the experimental unit when appropriate.", "Validate segmentation against representative manual ground truth using Dice/IoU and error review."))

    if module_key == "spatial_omics_pathology":
        x = column("x", "x_coord", "pxl_col_in_fullres")
        y = column("y", "y_coord", "pxl_row_in_fullres")
        spot = column("spot", "barcode", "cell")
        sample = column("sample", "section", "slide")
        region = column("region", "roi", "domain")
        if x and y:
            coords = frame[[x, y]].apply(pd.to_numeric, errors="coerce")
            invalid = coords.isna().any(axis=1)
            duplicate_coords = coords.duplicated(keep=False)
            checks.append({"check": "Spatial coordinate validity", "status": "review" if invalid.any() else "pass", "detail": f"{int(invalid.sum())} invalid coordinates"})
            checks.append({"check": "Duplicate coordinates", "status": "review" if duplicate_coords.any() else "pass", "detail": f"{int(duplicate_coords.sum())} repeated coordinate rows"})
            if invalid.any() or duplicate_coords.any():
                flagged = frame.loc[invalid | duplicate_coords].head(250).copy()
        if spot:
            dup_spot = frame[spot].astype(str).duplicated(keep=False)
            metrics.append({"metric": "unique_spots_or_cells", "value": int(frame[spot].astype(str).nunique()), "unit": "entities"})
            if dup_spot.any():
                checks.append({"check": "Spot/cell identifier uniqueness", "status": "review", "detail": f"{int(dup_spot.sum())} duplicate identifiers"})
        if sample:
            metrics.append({"metric": "spatial_samples_or_sections", "value": int(frame[sample].astype(str).nunique()), "unit": "samples"})
        else:
            checks.append({"check": "Sample/section identity", "status": "review", "detail": "No sample or section column detected"})
        if region:
            metrics.append({"metric": "annotated_regions", "value": int(frame[region].astype(str).nunique()), "unit": "regions"})
        recommendations.extend(("Record image-coordinate transform and registration residuals.", "Use section/sample replication and pathologist review for high-stakes interpretation."))

    if module_key == "docking_dynamics":
        ligand = column("ligand", "compound")
        pose = column("pose", "pose_id")
        score = column("docking_score", "score", "binding_energy")
        rmsd = column("rmsd", "pose_rmsd")
        strain = column("strain_energy", "strain")
        if ligand and pose:
            duplicate_pose = frame.astype({ligand: str, pose: str}).duplicated([ligand, pose], keep=False)
            checks.append({"check": "Ligand-pose identity", "status": "review" if duplicate_pose.any() else "pass", "detail": f"{int(duplicate_pose.sum())} duplicate pose keys"})
            if duplicate_pose.any():
                flagged = frame.loc[duplicate_pose].head(250).copy()
        if score:
            scores = pd.to_numeric(frame[score], errors="coerce")
            metrics.append({"metric": "median_docking_score", "value": float(scores.median()), "unit": "score units"})
            checks.append({"check": "Docking score completeness", "status": "review" if scores.isna().any() else "pass", "detail": f"{int(scores.isna().sum())} missing scores"})
        if rmsd:
            values = pd.to_numeric(frame[rmsd], errors="coerce")
            poor = values > 2.0
            metrics.append({"metric": "poses_rmsd_gt_2", "value": int(poor.sum()), "unit": "poses"})
            checks.append({"check": "Pose RMSD review", "status": "review" if poor.any() else "pass", "detail": f"{int(poor.sum())} poses exceed RMSD 2"})
        if strain:
            values = pd.to_numeric(frame[strain], errors="coerce")
            outlier = _robust_outlier_mask(values)
            checks.append({"check": "Ligand strain review", "status": "review" if outlier.any() else "pass", "detail": f"{int(outlier.sum())} strain outliers"})
        recommendations.extend(("Record receptor/ligand preparation, protonation, grid box, seed and engine version.", "Use redocking/positive controls and measured affinity before interpreting score rankings as binding evidence."))

    if module_key == "pharmacogenomics":
        sample = column("sample", "patient")
        gene = column("gene")
        drug = column("drug", "medication")
        phenotype = column("phenotype", "metabolizer_status")
        evidence = column("evidence_level", "guideline_level")
        build = column("genome_build", "build", "assembly")
        allele_version = column("allele_definition_version", "guideline_version", "release")
        cnv = column("copy_number", "cnv", "gene_copy_number")
        required_present = [name for name, value in (("sample", sample), ("gene", gene), ("drug", drug), ("phenotype", phenotype), ("evidence", evidence)) if value]
        checks.append({"check": "PGx core evidence fields", "status": "pass" if len(required_present) == 5 else "review", "detail": f"Detected {len(required_present)}/5 core fields"})
        checks.append({"check": "Genome build metadata", "status": "pass" if build else "review", "detail": str(build) if build else "No build/assembly column detected"})
        checks.append({"check": "Allele/guideline release metadata", "status": "pass" if allele_version else "review", "detail": str(allele_version) if allele_version else "No release/version column detected"})
        if gene:
            cyp2d6 = frame[gene].astype(str).str.upper().eq("CYP2D6")
            if cyp2d6.any():
                checks.append({"check": "CYP2D6 copy-number evidence", "status": "pass" if cnv else "review", "detail": str(cnv) if cnv else "CYP2D6 present but no copy-number field detected"})
        if evidence:
            missing_evidence = frame[evidence].isna() | frame[evidence].astype(str).str.strip().eq("")
            metrics.append({"metric": "records_without_evidence_level", "value": int(missing_evidence.sum()), "unit": "records"})
            if missing_evidence.any():
                flagged = frame.loc[missing_evidence].head(250).copy()
        recommendations.extend(("Pin allele-definition and guideline releases and retain diplotype-to-phenotype traceability.", "Require qualified human review; do not generate autonomous treatment or dose instructions."))

    if module_key == "immunoinformatics_vaccine":
        peptide = column("peptide", "sequence")
        allele = column("allele", "hla")
        conservancy = column("conservancy")
        toxicity = column("toxicity_risk", "toxicity")
        if peptide:
            seq = frame[peptide].astype(str).str.upper()
            valid = seq.str.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]{8,30}", na=False)
            checks.append({"check": "Peptide syntax and length", "status": "review" if (~valid).any() else "pass", "detail": f"{int((~valid).sum())} invalid peptides"})
            metrics.append({"metric": "unique_peptides", "value": int(seq.nunique()), "unit": "peptides"})
            if (~valid).any():
                flagged = frame.loc[~valid].head(250).copy()
        if allele:
            normalized = frame[allele].astype(str).str.upper()
            plausible = normalized.str.contains(r"HLA[-_ ]?[A-Z0-9]+[*:]", regex=True, na=False)
            checks.append({"check": "HLA allele nomenclature", "status": "review" if (~plausible).any() else "pass", "detail": f"{int((~plausible).sum())} non-standard allele labels"})
        if conservancy:
            values = pd.to_numeric(frame[conservancy], errors="coerce")
            checks.append({"check": "Conservancy bounds", "status": "review" if (~values.between(0, 1)).any() else "pass", "detail": f"{int((~values.between(0, 1)).sum())} values outside [0,1]"})
        if toxicity:
            values = pd.to_numeric(frame[toxicity], errors="coerce")
            metrics.append({"metric": "high_toxicity_risk_candidates", "value": int((values >= 0.5).sum()), "unit": "candidates"})
        recommendations.extend(("Record binding-predictor version, allele-frequency source and source-protein provenance.", "Treat binding and safety scores as hypotheses until experimental immunogenicity and safety validation."))

    if module_key == "antibody_biologics":
        variant = column("variant", "sequence_id")
        affinity = column("affinity")
        stability = column("stability")
        humanness = column("humanness")
        aggregation = column("aggregation_risk", "aggregation")
        if variant:
            duplicate = frame[variant].astype(str).duplicated(keep=False)
            checks.append({"check": "Variant identity", "status": "review" if duplicate.any() else "pass", "detail": f"{int(duplicate.sum())} duplicate variant identifiers"})
        evidence_fields = [value for value in (affinity, stability, humanness, aggregation) if value]
        if evidence_fields:
            evidence_count = frame[evidence_fields].notna().sum(axis=1)
            low = evidence_count < 3
            metrics.append({"metric": "variants_with_3plus_developability_fields", "value": int((evidence_count >= 3).sum()), "unit": "variants"})
            checks.append({"check": "Developability evidence completeness", "status": "review" if low.any() else "pass", "detail": f"{int(low.sum())} variants have fewer than 3 evidence fields"})
            if low.any():
                flagged = frame.loc[low].head(250).copy()
        recommendations.extend(("Use qualified numbering/germline assignment before CDR or humanization conclusions.", "Link computational scores to assay provenance for affinity, stability, aggregation and manufacturability."))

    if module_key == "glycomics_glycoproteomics":
        glycan = column("glycan", "composition")
        site = column("site", "position")
        confidence = column("confidence", "localization_probability")
        qvalue = column("q_value", "qvalue", "fdr")
        decoy = column("decoy", "is_decoy", "target_decoy")
        if glycan:
            blank = frame[glycan].isna() | frame[glycan].astype(str).str.strip().eq("")
            checks.append({"check": "Glycan annotation presence", "status": "review" if blank.any() else "pass", "detail": f"{int(blank.sum())} missing annotations"})
        if site:
            plausible = frame[site].astype(str).str.contains(r"[NST]?[0-9]+|[A-Z]+:[NST][0-9]+", regex=True, na=False)
            checks.append({"check": "Site annotation syntax", "status": "review" if (~plausible).any() else "pass", "detail": f"{int((~plausible).sum())} ambiguous site labels"})
        if confidence:
            values = pd.to_numeric(frame[confidence], errors="coerce")
            low = values < 0.75
            metrics.append({"metric": "low_localization_confidence", "value": int(low.sum()), "unit": "assignments"})
            checks.append({"check": "Localization confidence", "status": "review" if low.any() else "pass", "detail": f"{int(low.sum())} assignments below 0.75"})
            if low.any():
                flagged = frame.loc[low.fillna(True)].head(250).copy()
        if qvalue:
            values = pd.to_numeric(frame[qvalue], errors="coerce")
            failed = values > 0.01
            checks.append({"check": "Identification FDR", "status": "review" if failed.any() else "pass", "detail": f"{int(failed.sum())} assignments above 1%"})
        else:
            checks.append({"check": "Identification FDR evidence", "status": "review", "detail": "No q-value/FDR column detected"})
        checks.append({"check": "Target-decoy evidence", "status": "pass" if decoy else "review", "detail": str(decoy) if decoy else "No decoy indicator detected"})
        recommendations.extend(("Retain target-decoy policy, search-space hash and spectrum-level evidence.", "Require manual fragment review and orthogonal confirmation for priority sites."))

    if module_key == "synthetic_data_privacy":
        quasi = [c for c in frame.columns if str(c).lower() in {"age", "sex", "gender", "postcode", "zip", "site", "diagnosis", "group"}]
        if quasi:
            group_sizes = frame.groupby(quasi, dropna=False).size()
            k = int(group_sizes.min()) if len(group_sizes) else 0
            metrics.append({"metric": "observed_k_anonymity", "value": k, "unit": "records/group"})
            checks.append({"check": "k-anonymity proxy", "status": "review" if k < 5 else "pass", "detail": f"minimum equivalence class k={k}"})
        recommendations.append("Run membership-inference and utility benchmarks; k-anonymity alone is insufficient.")

    return flagged, recommendations


def assess_dataframe(module_key: str, frame: pd.DataFrame) -> DepthAssessment:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    checks, metrics, common_flagged = _common_checks(frame)
    flagged, recommendations = _add_domain_checks(module_key, frame, checks, metrics)
    if flagged.empty:
        flagged = common_flagged
    status_counts = pd.Series([row["status"] for row in checks]).value_counts().to_dict()
    summary = {
        "module_key": module_key,
        "records": int(len(frame)),
        "checks_passed": int(status_counts.get("pass", 0)),
        "checks_for_review": int(status_counts.get("review", 0)),
        "checks_failed": int(status_counts.get("fail", 0)),
        "flagged_records": int(len(flagged)),
    }
    return DepthAssessment(
        module_key=module_key,
        summary=summary,
        quality_checks=pd.DataFrame(checks),
        metrics=pd.DataFrame(metrics),
        flagged_records=flagged,
        recommendations=tuple(dict.fromkeys(recommendations)),
    )
