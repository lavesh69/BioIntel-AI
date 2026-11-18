from __future__ import annotations

from itertools import combinations
import math
import re
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score
from sklearn.preprocessing import StandardScaler

from .assessment import bh_fdr
from .native_integrity import parse_scientific_bool


def _column(frame: pd.DataFrame, *names: str) -> str | None:
    direct = {str(column).lower(): str(column) for column in frame.columns}
    normalized = {re.sub(r"[^a-z0-9]", "", str(column).lower()): str(column) for column in frame.columns}
    for name in names:
        if name.lower() in direct:
            return direct[name.lower()]
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in normalized:
            return normalized[key]
    return None


def _check(rows: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    rows.append({"check": name, "status": status, "detail": str(detail)})


def _metric(rows: list[dict[str, Any]], name: str, value: Any, unit: str = "") -> None:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        value = None
    rows.append({"metric": name, "value": value, "unit": unit})


def _safe_numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame[columns].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _flow_enhancement(frame, metadata, tables, checks, metrics):
    fluorescence = metadata.get("fluorescence_channels")
    if not fluorescence:
        fluorescence = [
            str(column)
            for column in frame.select_dtypes(include=[np.number]).columns
            if not str(column).upper().startswith(("FSC", "SSC", "TIME"))
        ]
    fluorescence = list(fluorescence or [])
    if len(fluorescence) < 2:
        return
    single_stains = metadata.get("single_stain_events")
    if isinstance(single_stains, Mapping) and single_stains:
        try:
            from biointel.biotech.flow_cytometry import apply_compensation, derive_compensation_matrix

            controls = {str(key): value for key, value in single_stains.items() if isinstance(value, pd.DataFrame)}
            unstained = metadata.get("unstained_events")
            matrix, provenance = derive_compensation_matrix(
                controls,
                fluorescence,
                unstained_events=unstained if isinstance(unstained, pd.DataFrame) else None,
                positive_quantile=float(metadata.get("positive_quantile", 0.80)),
                minimum_positive_events=max(20, int(metadata.get("minimum_positive_events", 50))),
            )
            compensated, summary = apply_compensation(frame, fluorescence, matrix)
            tables["derived_compensation_matrix"] = matrix.reset_index(names="detector_channel")
            tables["derived_compensated_events"] = compensated
            tables["compensation_derivation_provenance"] = pd.DataFrame(provenance.get("source_controls", []))
            _check(checks, "Single-stain compensation derivation", "pass", f"{len(fluorescence)} channels; condition={summary['condition_number']:.3g}")
            _metric(metrics, "derived_compensation_condition", summary["condition_number"], "condition number")
        except Exception as exc:
            _check(checks, "Single-stain compensation derivation", "fail", f"{type(exc).__name__}: {exc}")
    fmo_controls = metadata.get("fmo_controls")
    if isinstance(fmo_controls, Mapping) and fmo_controls:
        from biointel.biotech.flow_cytometry import fmo_threshold

        rows = []
        for channel, control in fmo_controls.items():
            if not isinstance(control, pd.DataFrame):
                continue
            try:
                threshold = fmo_threshold(control, str(channel), float(metadata.get("fmo_quantile", 0.995)))
                positive_fraction = float((pd.to_numeric(frame[str(channel)], errors="coerce") > threshold).mean()) if str(channel) in frame else np.nan
                rows.append({"channel": str(channel), "threshold": threshold, "positive_fraction": positive_fraction, "control_events": len(control)})
            except Exception as exc:
                rows.append({"channel": str(channel), "threshold": np.nan, "positive_fraction": np.nan, "control_events": len(control), "error": f"{type(exc).__name__}: {exc}"})
        if rows:
            table = pd.DataFrame(rows)
            tables["fmo_thresholds"] = table
            errors = int(table.get("error", pd.Series(dtype=str)).notna().sum()) if "error" in table else 0
            _check(checks, "FMO threshold derivation", "fail" if errors else "pass", f"{len(table)-errors}/{len(table)} channels derived")
    gate_specs = metadata.get("gate_specs")
    if isinstance(gate_specs, list) and gate_specs:
        try:
            from biointel.biotech.flow_cytometry import audit_gate_hierarchy, polygon_gate, rectangular_gate

            populations: dict[str, pd.DataFrame] = {"All events": frame}
            gates = []
            for index, spec in enumerate(gate_specs):
                if not isinstance(spec, Mapping):
                    continue
                parent = str(spec.get("parent", "All events"))
                source = populations.get(parent)
                if source is None:
                    raise ValueError(f"Unknown parent gate: {parent}")
                kind = str(spec.get("kind", "rectangle")).lower()
                name = str(spec.get("name", f"Gate {index+1}"))
                if kind == "polygon":
                    gate = polygon_gate(source, str(spec["x_channel"]), str(spec["y_channel"]), spec["vertices"], name=name, parent=parent)
                else:
                    gate = rectangular_gate(
                        source,
                        str(spec["x_channel"]),
                        str(spec["y_channel"]),
                        x_min=float(spec["x_min"]), x_max=float(spec["x_max"]),
                        y_min=float(spec["y_min"]), y_max=float(spec["y_max"]),
                        name=name, parent=parent,
                    )
                gates.append(gate)
                populations[name] = gate.events
            audit = audit_gate_hierarchy(gates, minimum_events=max(1, int(metadata.get("minimum_gate_events", 50))))
            tables["gate_hierarchy_audit"] = audit
            tables["population_summary"] = pd.DataFrame([{"population": key, "events": len(value), "fraction_all": len(value) / max(len(frame), 1)} for key, value in populations.items()])
            blocked = int(audit.status.eq("block").sum())
            _check(checks, "Gate hierarchy", "fail" if blocked else ("review" if audit.status.eq("review").any() else "pass"), f"{blocked} blocked gates")
        except Exception as exc:
            _check(checks, "Gate hierarchy", "fail", f"{type(exc).__name__}: {exc}")


def _metabolomics_enhancement(frame, metadata, tables, checks, metrics):
    feature = _column(frame, "feature", "feature_id", "metabolite", "compound", "lipid")
    sample = _column(frame, "sample", "sample_id", "injection", "run")
    intensity = _column(frame, "intensity", "abundance", "area", "peak_area", "signal")
    sample_type = _column(frame, "sample_type", "type", "role")
    if not (feature and sample and intensity):
        return
    work = frame[[feature, sample, intensity] + ([sample_type] if sample_type else [])].copy()
    work["raw_intensity"] = pd.to_numeric(work[intensity], errors="coerce")
    blank_median = pd.Series(dtype=float)
    if sample_type:
        role = work[sample_type].astype(str).str.lower()
        blank_median = work[role.str.contains("blank", na=False)].groupby(feature)["raw_intensity"].median()
    work["blank_median"] = work[feature].map(blank_median).fillna(0.0)
    work["blank_corrected_intensity"] = (work["raw_intensity"] - work["blank_median"]).clip(lower=0)
    internal_standard = str(metadata.get("internal_standard_feature", "") or "").strip()
    if internal_standard:
        standards = work[work[feature].astype(str) == internal_standard].groupby(sample)["blank_corrected_intensity"].median()
        reference = float(standards.median()) if standards.notna().any() else np.nan
        factors = (reference / standards.replace(0, np.nan)).rename("internal_standard_factor")
        work = work.join(factors, on=sample)
        work["normalized_intensity"] = work["blank_corrected_intensity"] * work["internal_standard_factor"]
        valid = int(factors.notna().sum())
        _check(checks, "Internal-standard normalization", "pass" if valid else "fail", f"{valid} samples normalized using {internal_standard}")
    else:
        work["internal_standard_factor"] = 1.0
        work["normalized_intensity"] = work["blank_corrected_intensity"]
        _check(checks, "Internal-standard normalization", "review", "No internal_standard_feature supplied")
    tables["blank_and_internal_standard_normalization"] = work
    mz = _column(frame, "mz", "m_z", "mass_to_charge")
    rt = _column(frame, "rt", "retention_time", "retention_time_min")
    if mz and rt:
        features = frame[[feature, mz, rt]].drop_duplicates(feature).copy()
        features["mz_numeric"] = pd.to_numeric(features[mz], errors="coerce")
        features["rt_numeric"] = pd.to_numeric(features[rt], errors="coerce")
        features = features.dropna(subset=["mz_numeric", "rt_numeric"]).sort_values(["rt_numeric", "mz_numeric"])
        cluster_ids = []
        current = 0
        previous_mz = previous_rt = None
        ppm = float(metadata.get("adduct_ppm_tolerance", 10.0))
        rt_tol = float(metadata.get("adduct_rt_tolerance", 0.15))
        for _, row in features.iterrows():
            if previous_mz is None or abs(row.rt_numeric - previous_rt) > rt_tol or abs(row.mz_numeric - previous_mz) / max(previous_mz, 1e-9) * 1e6 > ppm:
                current += 1
            cluster_ids.append(current)
            previous_mz, previous_rt = float(row.mz_numeric), float(row.rt_numeric)
        features["coelution_mass_cluster"] = cluster_ids
        tables["coelution_mass_clusters"] = features
        _metric(metrics, "coelution_mass_clusters", int(features.coelution_mass_cluster.nunique()), "clusters")


def _gwas_association(frame, tables, checks, metrics):
    variant = _column(frame, "variant_id", "variant", "rsid")
    sample = _column(frame, "sample_id", "sample", "subject")
    genotype = _column(frame, "genotype", "gt")
    phenotype = _column(frame, "phenotype", "case_control", "outcome")
    if not all((variant, sample, genotype, phenotype)):
        return
    work = frame[[variant, sample, genotype, phenotype]].copy()
    work["dosage"] = work[genotype].astype(str).str.replace("|", "/", regex=False).map({"0/0": 0, "0/1": 1, "1/0": 1, "1/1": 2, "0": 0, "1": 1, "2": 2})
    pheno_raw = work[phenotype]
    if pd.api.types.is_numeric_dtype(pheno_raw):
        y = pd.to_numeric(pheno_raw, errors="coerce")
        binary = set(y.dropna().unique()).issubset({0, 1})
    else:
        y = pheno_raw.astype(str).str.lower().map({"case": 1, "control": 0, "affected": 1, "unaffected": 0, "true": 1, "false": 0})
        binary = True
    work["_phenotype"] = y
    rows = []
    chi_values = []
    for vid, subset in work.groupby(variant, dropna=False):
        valid = subset.dropna(subset=["dosage", "_phenotype"])
        if len(valid) < 8 or valid["dosage"].nunique() < 2:
            continue
        if binary and valid["_phenotype"].nunique() == 2:
            cases = valid[valid._phenotype == 1].dosage
            controls = valid[valid._phenotype == 0].dosage
            alt_case = float(cases.sum()); ref_case = float(2 * len(cases) - alt_case)
            alt_ctrl = float(controls.sum()); ref_ctrl = float(2 * len(controls) - alt_ctrl)
            contingency = np.array([[alt_case, ref_case], [alt_ctrl, ref_ctrl]], dtype=float) + 0.5
            odds_ratio = float((contingency[0, 0] * contingency[1, 1]) / (contingency[0, 1] * contingency[1, 0]))
            chi2, p_value, _, _ = stats.chi2_contingency(contingency, correction=False)
            beta = math.log(odds_ratio)
            rows.append({"variant_id": vid, "n": len(valid), "effect": beta, "odds_ratio": odds_ratio, "p_value": float(p_value), "test": "allelic_chi_square"})
            chi_values.append(float(chi2))
        elif not binary:
            slope, intercept, r, p_value, stderr = stats.linregress(valid.dosage, valid._phenotype)
            rows.append({"variant_id": vid, "n": len(valid), "effect": float(slope), "standard_error": float(stderr), "p_value": float(p_value), "test": "linear_regression"})
    association = pd.DataFrame(rows)
    if not association.empty:
        association["fdr"] = bh_fdr(association.p_value.to_numpy(dtype=float))
        association = association.sort_values("p_value")
        tables["native_association_screen"] = association
        _check(checks, "Native association screening", "pass", f"{len(association)} variants tested; exploratory unadjusted screen")
        _metric(metrics, "association_variants_tested", len(association), "variants")
        if chi_values:
            lambda_gc = float(np.median(chi_values) / 0.4549364)
            tables["genomic_inflation_summary"] = pd.DataFrame([{"lambda_gc": lambda_gc, "variants": len(chi_values), "expected_median_chi2_1df": 0.4549364}])
            _check(checks, "Genomic inflation", "pass" if 0.8 <= lambda_gc <= 1.2 else "review", f"lambda_GC={lambda_gc:.3f}")
            _metric(metrics, "lambda_gc", lambda_gc, "ratio")


def _variant_enhancement(module_key, frame, metadata, tables, checks, metrics):
    if module_key == "population_gwas":
        _gwas_association(frame, tables, checks, metrics)
    elif module_key == "structural_variant_repeat":
        chrom = _column(frame, "chrom", "chromosome")
        start = _column(frame, "start", "pos", "position")
        end = _column(frame, "end", "stop")
        support = _column(frame, "read_support", "supporting_reads", "split_reads")
        svtype = _column(frame, "svtype", "sv_type", "type")
        if chrom and start:
            table = frame[[c for c in (chrom, start, end, support, svtype) if c]].copy()
            table["start_numeric"] = pd.to_numeric(table[start], errors="coerce")
            table["end_numeric"] = pd.to_numeric(table[end], errors="coerce") if end else table.start_numeric
            table["support_numeric"] = pd.to_numeric(table[support], errors="coerce") if support else np.nan
            table["breakpoint_bin"] = table[chrom].astype(str) + ":" + (table.start_numeric // int(metadata.get("breakpoint_bin_size", 1000))).astype("Int64").astype(str)
            table["support_tier"] = pd.cut(table.support_numeric, [-np.inf, 2, 5, 10, np.inf], labels=["weak", "review", "moderate", "strong"])
            tables["sv_breakpoint_review"] = table
            _check(checks, "Breakpoint clustering", "pass", f"{table.breakpoint_bin.nunique()} breakpoint bins")
        proband = _column(frame, "proband_gt", "child_gt")
        mother = _column(frame, "mother_gt", "maternal_gt")
        father = _column(frame, "father_gt", "paternal_gt")
        if proband and mother and father:
            inherited = frame[[proband, mother, father]].copy()
            inherited["de_novo_candidate"] = inherited[proband].astype(str).ne("0/0") & inherited[mother].astype(str).eq("0/0") & inherited[father].astype(str).eq("0/0")
            tables["sv_inheritance_review"] = inherited
            _check(checks, "Trio inheritance screen", "review" if inherited.de_novo_candidate.any() else "pass", f"{int(inherited.de_novo_candidate.sum())} de-novo candidates")
    elif module_key == "pharmacogenomics":
        sample = _column(frame, "sample_id", "sample", "subject")
        gene = _column(frame, "gene", "pharm_gene")
        diplotype = _column(frame, "diplotype", "star_allele", "allele_call")
        cn = _column(frame, "copy_number", "cn")
        phase = _column(frame, "phased", "phase_status")
        if sample and gene:
            review = frame[[c for c in (sample, gene, diplotype, cn, phase) if c]].copy()
            review["diplotype_present"] = review[diplotype].notna() if diplotype else False
            review["copy_number_present"] = review[cn].notna() if cn else False
            review["phase_present"] = review[phase].notna() if phase else False
            review["evidence_completeness"] = review[["diplotype_present", "copy_number_present", "phase_present"]].mean(axis=1)
            review["release_ready"] = review.evidence_completeness.eq(1.0) & bool(metadata.get("allele_definition_release")) & bool(metadata.get("guideline_release"))
            tables["pharmacogenomic_call_readiness"] = review
            _check(checks, "PGx call completeness", "pass" if review.release_ready.all() else "review", f"{int(review.release_ready.sum())}/{len(review)} calls complete")


def _single_cell_enhancement(frame, tables, checks, metrics):
    cell = _column(frame, "cell_id", "cell", "barcode")
    donor = _column(frame, "sample_id", "donor", "sample")
    excluded = {c for c in (cell, donor, _column(frame, "batch"), _column(frame, "group")) if c}
    genes = [str(c) for c in frame.columns if str(c) not in excluded and pd.to_numeric(frame[c], errors="coerce").notna().mean() >= 0.8]
    if not cell or len(genes) < 3:
        return
    counts = _safe_numeric(frame, genes).fillna(0).clip(lower=0)
    library = counts.sum(axis=1)
    detected = counts.gt(0).sum(axis=1)
    mt_genes = [g for g in genes if g.upper().startswith(("MT-", "MT_"))]
    mt_fraction = counts[mt_genes].sum(axis=1).div(library.replace(0, np.nan)) if mt_genes else pd.Series(np.nan, index=frame.index)
    qc = pd.DataFrame({"cell_id": frame[cell].astype(str), "library_size": library, "detected_features": detected, "mitochondrial_fraction": mt_fraction})
    low_library = library < max(1.0, float(library.quantile(0.01)))
    high_mt = mt_fraction > 0.20 if mt_genes else pd.Series(False, index=frame.index)
    qc["qc_flag"] = low_library | high_mt
    normalized = counts.div(library.replace(0, np.nan), axis=0).mul(10_000).fillna(0)
    lognorm = np.log1p(normalized)
    mean = lognorm.mean(axis=0)
    variance = lognorm.var(axis=0, ddof=1)
    dispersion = variance.div(mean.replace(0, np.nan))
    hvg = pd.DataFrame({"feature": genes, "mean_log_expression": mean.to_numpy(), "variance": variance.to_numpy(), "dispersion": dispersion.to_numpy()}).sort_values("dispersion", ascending=False)
    selected = hvg.head(min(50, len(hvg))).feature.tolist()
    valid_mask = ~qc.qc_flag & library.gt(0)
    embedding = pd.DataFrame()
    if valid_mask.sum() >= 5 and len(selected) >= 2:
        matrix = StandardScaler().fit_transform(lognorm.loc[valid_mask, selected])
        components = min(10, matrix.shape[0] - 1, matrix.shape[1])
        pca = PCA(n_components=max(2, components), random_state=155)
        coords = pca.fit_transform(matrix)
        clusters = KMeans(n_clusters=max(2, min(8, int(round(math.sqrt(len(coords) / 2))))), random_state=155, n_init=10).fit_predict(coords)
        embedding = pd.DataFrame(coords, columns=[f"PC{i+1}" for i in range(coords.shape[1])])
        embedding.insert(0, "cell_id", frame.loc[valid_mask, cell].astype(str).to_numpy())
        embedding["cluster"] = clusters.astype(str)
        if donor:
            embedding["donor"] = frame.loc[valid_mask, donor].astype(str).to_numpy()
        _metric(metrics, "single_cell_pca_variance", float(pca.explained_variance_ratio_[:2].sum()), "fraction")
    tables["single_cell_qc_advanced"] = qc
    tables["highly_variable_features"] = hvg
    tables["single_cell_embedding_clusters"] = embedding
    if donor:
        pseudo = counts.assign(_donor=frame[donor].astype(str)).groupby("_donor").sum().reset_index(names="donor")
        tables["donor_pseudobulk_counts"] = pseudo
        _check(checks, "Donor-level pseudobulk", "pass" if pseudo.donor.nunique() >= 2 else "review", f"{pseudo.donor.nunique()} donors")
    _check(checks, "Single-cell QC and clustering", "review" if qc.qc_flag.any() else "pass", f"{int(qc.qc_flag.sum())}/{len(qc)} cells flagged")


def _epigenomics_enhancement(frame, tables, checks, metrics):
    chrom = _column(frame, "chrom", "chromosome")
    start = _column(frame, "start")
    end = _column(frame, "end")
    rep = _column(frame, "replicate", "rep", "sample")
    signal = _column(frame, "signal", "score", "enrichment")
    if not all((chrom, start, end, rep)):
        return
    work = frame[[c for c in (chrom, start, end, rep, signal) if c]].copy()
    work["start_numeric"] = pd.to_numeric(work[start], errors="coerce")
    work["end_numeric"] = pd.to_numeric(work[end], errors="coerce")
    work["bin_key"] = work[chrom].astype(str) + ":" + (work.start_numeric // 250).astype("Int64").astype(str)
    rows = []
    reps = [str(v) for v in work[rep].dropna().unique()]
    for a, b in combinations(reps, 2):
        set_a = set(work.loc[work[rep].astype(str) == a, "bin_key"])
        set_b = set(work.loc[work[rep].astype(str) == b, "bin_key"])
        union = len(set_a | set_b)
        jaccard = len(set_a & set_b) / union if union else np.nan
        row = {"replicate_a": a, "replicate_b": b, "peak_bin_jaccard": jaccard, "shared_bins": len(set_a & set_b), "union_bins": union}
        if signal:
            pivot = work[work[rep].astype(str).isin([a, b])].pivot_table(index="bin_key", columns=rep, values=signal, aggfunc="mean")
            if a in pivot and b in pivot and pivot[[a, b]].dropna().shape[0] >= 3:
                rho, p = stats.spearmanr(pd.to_numeric(pivot[a], errors="coerce"), pd.to_numeric(pivot[b], errors="coerce"), nan_policy="omit")
                row.update({"signal_spearman": float(rho), "signal_p": float(p)})
        rows.append(row)
    pairwise = pd.DataFrame(rows)
    if not pairwise.empty:
        tables["replicate_pairwise_concordance"] = pairwise
        median = float(pairwise.peak_bin_jaccard.median())
        _check(checks, "Pairwise replicate concordance", "pass" if median >= 0.5 else "review", f"median Jaccard={median:.3f}")
        _metric(metrics, "median_peak_jaccard", median, "fraction")


def _pathology_enhancement(frame, tables, checks, metrics):
    patient = _column(frame, "patient_id", "subject_id", "patient")
    truth = _column(frame, "ground_truth", "truth", "label")
    prediction = _column(frame, "prediction", "predicted_label")
    split = _column(frame, "split", "dataset_split", "partition")
    site = _column(frame, "site", "scanner_site", "hospital")
    if patient and split:
        leakage = frame.groupby(patient)[split].nunique().rename("splits").reset_index()
        leakage = leakage[leakage.splits > 1]
        tables["patient_split_leakage"] = leakage
        _check(checks, "Patient-level split isolation", "fail" if not leakage.empty else "pass", f"{len(leakage)} patients span multiple splits")
    if patient and truth and prediction:
        rows = []
        for pid, subset in frame.groupby(patient):
            y = subset[truth].astype(str)
            p = subset[prediction].astype(str)
            rows.append({"patient_id": pid, "records": len(subset), "accuracy": accuracy_score(y, p), "truth_positive_fraction": float(y.str.lower().isin({"1", "true", "positive", "tumor", "tumour"}).mean())})
        patient_perf = pd.DataFrame(rows)
        tables["patient_level_performance"] = patient_perf
        _check(checks, "Patient-level performance", "pass" if patient_perf.accuracy.median() >= 0.8 else "review", f"median accuracy={patient_perf.accuracy.median():.3f}")
    if site and truth and prediction:
        site_rows = []
        for value, subset in frame.groupby(site):
            site_rows.append({"site": value, "records": len(subset), "accuracy": accuracy_score(subset[truth].astype(str), subset[prediction].astype(str))})
        site_perf = pd.DataFrame(site_rows)
        tables["site_performance"] = site_perf
        if len(site_perf) > 1:
            gap = float(site_perf.accuracy.max() - site_perf.accuracy.min())
            _check(checks, "Site performance heterogeneity", "pass" if gap <= 0.10 else "review", f"max-min accuracy gap={gap:.3f}")


def _survival_enhancement(frame, tables, checks, metrics):
    time = _column(frame, "time", "duration", "follow_up", "survival_time")
    event = _column(frame, "event", "status", "event_observed")
    group = _column(frame, "group", "arm", "stratum")
    if not (time and event):
        return
    duration = pd.to_numeric(frame[time], errors="coerce")
    status = frame[event].map(lambda value: int(parse_scientific_bool(value, default=False)))
    excluded = {time, event}
    design = pd.DataFrame(index=frame.index)
    if group:
        design = pd.concat([design, pd.get_dummies(frame[group].astype(str), prefix="group", drop_first=True, dtype=float)], axis=1)
        excluded.add(group)
    numeric = [str(c) for c in frame.columns if str(c) not in excluded and pd.to_numeric(frame[c], errors="coerce").notna().mean() >= 0.9]
    for column in numeric[:5]:
        design[column] = pd.to_numeric(frame[column], errors="coerce")
    valid = duration.gt(0) & duration.notna() & status.notna()
    if design.empty or valid.sum() < max(12, design.shape[1] * 4):
        _check(checks, "Multivariable Cox model", "review", "Insufficient covariates or events")
        return
    complete = valid & design.notna().all(axis=1)
    if complete.sum() < max(12, design.shape[1] * 4):
        _check(checks, "Multivariable Cox model", "review", "Insufficient complete cases")
        return

    def scipy_cox_fit() -> pd.DataFrame:
        """Fit a bounded Cox PH model with Breslow ties using required SciPy."""
        from scipy.optimize import minimize

        observed_duration = duration[complete].to_numpy(dtype=float)
        observed_status = status[complete].to_numpy(dtype=int)
        model_design = design.loc[complete].astype(float).copy()
        effect_scale: list[str] = []
        for column in model_design.columns:
            values = model_design[column].to_numpy(dtype=float)
            if np.unique(values).size > 2:
                deviation = float(np.std(values, ddof=0))
                if deviation > 1e-12:
                    model_design[column] = (values - float(np.mean(values))) / deviation
                    effect_scale.append("per SD")
                    continue
            effect_scale.append("per unit")

        matrix = model_design.to_numpy(dtype=float)
        event_indices = np.flatnonzero(observed_status == 1)
        if not event_indices.size:
            raise ValueError("At least one observed event is required")
        ridge = 1e-8

        def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
            eta = np.clip(matrix @ beta, -50.0, 50.0)
            loss = 0.5 * ridge * float(beta @ beta)
            gradient = ridge * beta.copy()
            for index in event_indices:
                risk = observed_duration >= observed_duration[index]
                risk_eta = eta[risk]
                maximum = float(np.max(risk_eta))
                weights = np.exp(risk_eta - maximum)
                denominator = float(weights.sum())
                normalized = weights / denominator
                loss += -float(eta[index]) + maximum + math.log(denominator)
                gradient += -matrix[index] + normalized @ matrix[risk]
            return loss, gradient

        fitted = minimize(
            lambda beta: objective(beta)[0],
            np.zeros(matrix.shape[1], dtype=float),
            jac=lambda beta: objective(beta)[1],
            method="BFGS",
            options={"maxiter": 1_000, "gtol": 1e-7},
        )
        if not np.isfinite(fitted.fun) or not np.isfinite(fitted.x).all():
            raise RuntimeError("Cox partial-likelihood optimization did not converge")

        beta = np.asarray(fitted.x, dtype=float)
        eta = np.clip(matrix @ beta, -50.0, 50.0)
        information = np.eye(matrix.shape[1], dtype=float) * ridge
        for index in event_indices:
            risk = observed_duration >= observed_duration[index]
            risk_eta = eta[risk]
            weights = np.exp(risk_eta - float(np.max(risk_eta)))
            weights /= float(weights.sum())
            risk_matrix = matrix[risk]
            mean = weights @ risk_matrix
            centered = risk_matrix - mean
            information += (centered.T * weights) @ centered
        covariance = np.linalg.pinv(information, hermitian=True)
        standard_error = np.sqrt(np.clip(np.diag(covariance), 0.0, np.inf))
        z_score = np.divide(
            beta,
            standard_error,
            out=np.zeros_like(beta),
            where=standard_error > 1e-12,
        )
        p_value = 2.0 * stats.norm.sf(np.abs(z_score))
        return pd.DataFrame(
            {
                "covariate": list(model_design.columns),
                "effect_scale": effect_scale,
                "log_hazard_ratio": beta,
                "hazard_ratio": np.exp(np.clip(beta, -50.0, 50.0)),
                "ci95_low": np.exp(np.clip(beta - 1.96 * standard_error, -50.0, 50.0)),
                "ci95_high": np.exp(np.clip(beta + 1.96 * standard_error, -50.0, 50.0)),
                "p_value": p_value,
            }
        )

    try:
        try:
            from statsmodels.duration.hazard_regression import PHReg

            fit = PHReg(
                duration[complete],
                design.loc[complete].astype(float),
                status=status[complete],
            ).fit(disp=False)
            params = np.asarray(fit.params, dtype=float)
            se = np.asarray(fit.bse, dtype=float)
            p = np.asarray(fit.pvalues, dtype=float)
            result = pd.DataFrame(
                {
                    "covariate": design.columns,
                    "effect_scale": "per unit",
                    "log_hazard_ratio": params,
                    "hazard_ratio": np.exp(params),
                    "ci95_low": np.exp(params - 1.96 * se),
                    "ci95_high": np.exp(params + 1.96 * se),
                    "p_value": p,
                }
            )
            backend = "statsmodels PHReg"
        except (ImportError, ModuleNotFoundError):
            result = scipy_cox_fit()
            backend = "SciPy partial likelihood"
        result["fdr"] = bh_fdr(result.p_value.to_numpy())
        tables["multivariable_cox_model"] = result
        _check(
            checks,
            "Multivariable Cox model",
            "pass",
            f"n={int(complete.sum())}; covariates={len(result)}; backend={backend}",
        )
        _metric(metrics, "cox_complete_cases", int(complete.sum()), "subjects")
    except Exception as exc:
        _check(checks, "Multivariable Cox model", "review", f"{type(exc).__name__}: {exc}")


def _structural_enhancement(frame, tables, checks, metrics):
    smiles = _column(frame, "smiles", "canonical_smiles")
    if not smiles:
        return
    try:
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
        from rdkit.Chem.Scaffolds import MurckoScaffold
    except Exception:
        _check(checks, "RDKit molecular preparation", "review", "RDKit unavailable")
        return
    rows = []
    for index, value in frame[smiles].items():
        mol = Chem.MolFromSmiles(str(value))
        if mol is None:
            rows.append({"row_index": index, "valid": False, "canonical_smiles": ""})
            continue
        canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
        rows.append({
            "row_index": index, "valid": True, "canonical_smiles": canonical, "murcko_scaffold": scaffold,
            "molecular_weight": Descriptors.MolWt(mol), "logp": Crippen.MolLogP(mol),
            "tpsa": rdMolDescriptors.CalcTPSA(mol), "hbd": Lipinski.NumHDonors(mol),
            "hba": Lipinski.NumHAcceptors(mol), "rotatable_bonds": Lipinski.NumRotatableBonds(mol),
            "fraction_csp3": rdMolDescriptors.CalcFractionCSP3(mol),
        })
    table = pd.DataFrame(rows)
    if not table.empty:
        table["duplicate_structure"] = table.valid & table.canonical_smiles.duplicated(keep=False)
        table["duplicate_scaffold"] = table.valid & table.murcko_scaffold.ne("") & table.murcko_scaffold.duplicated(keep=False)
        tables["rdkit_ligand_standardization"] = table
        invalid = int((~table.valid).sum())
        _check(checks, "RDKit ligand standardization", "fail" if invalid else "pass", f"{invalid} invalid structures; {int(table.duplicate_structure.sum())} duplicate rows")
        _metric(metrics, "unique_murcko_scaffolds", int(table.loc[table.valid, "murcko_scaffold"].nunique()), "scaffolds")


def _vaccine_enhancement(frame, metadata, tables, checks, metrics):
    allele = _column(frame, "hla", "allele", "hla_allele")
    candidate = _column(frame, "candidate", "selected", "predicted_binder")
    frequencies = metadata.get("allele_frequencies")
    if not allele or not isinstance(frequencies, Mapping):
        return
    selected = frame if not candidate else frame[frame[candidate].map(lambda value: parse_scientific_bool(value, default=False))]
    alleles = set(selected[allele].astype(str))
    used = {key: float(value) for key, value in frequencies.items() if str(key) in alleles and 0 <= float(value) <= 1}
    coverage = 1.0 - float(np.prod([(1.0 - value) ** 2 for value in used.values()])) if used else 0.0
    tables["hla_population_coverage"] = pd.DataFrame([{"alleles_used": len(used), "alleles": ", ".join(sorted(used)), "estimated_diploid_coverage": coverage, "frequency_release": metadata.get("allele_frequency_release", "")}])
    _check(checks, "Estimated HLA population coverage", "pass" if coverage >= 0.8 else "review", f"coverage={coverage:.1%}; alleles={len(used)}")
    _metric(metrics, "estimated_hla_population_coverage", coverage, "fraction")


def _amr_enhancement(frame, tables, checks, metrics):
    drug = _column(frame, "drug", "antibiotic")
    prediction = _column(frame, "predicted_resistant", "genotype_call", "prediction")
    phenotype = _column(frame, "phenotype_resistant", "phenotype", "ast_result")
    if not all((drug, prediction, phenotype)):
        return
    rows = []
    for value, subset in frame.groupby(drug, dropna=False):
        y = subset[phenotype].astype(str).str.lower().isin({"1", "true", "r", "resistant"})
        p = subset[prediction].astype(str).str.lower().isin({"1", "true", "r", "resistant"})
        tn, fp, fn, tp = confusion_matrix(y, p, labels=[False, True]).ravel()
        rows.append({"drug": value, "n": len(subset), "sensitivity": tp / max(tp + fn, 1), "specificity": tn / max(tn + fp, 1), "ppv": tp / max(tp + fp, 1), "npv": tn / max(tn + fn, 1), "discordant": int((y != p).sum())})
    table = pd.DataFrame(rows)
    tables["per_drug_genotype_phenotype_performance"] = table
    worst = float(table[["sensitivity", "specificity"]].min(axis=1).min()) if not table.empty else 0.0
    _check(checks, "Per-drug AMR concordance", "pass" if worst >= 0.9 else "review", f"worst sensitivity/specificity={worst:.3f}")


def _federated_enhancement(frame, tables, checks, metrics):
    site = _column(frame, "site", "client", "centre")
    round_col = _column(frame, "round", "federated_round")
    metric_col = _column(frame, "accuracy", "metric", "score")
    weight = _column(frame, "sample_count", "samples", "weight")
    epsilon = _column(frame, "epsilon", "privacy_epsilon")
    if not all((site, round_col, metric_col)):
        return
    work = frame[[c for c in (site, round_col, metric_col, weight, epsilon) if c]].copy()
    work["metric_numeric"] = pd.to_numeric(work[metric_col], errors="coerce")
    work["weight_numeric"] = pd.to_numeric(work[weight], errors="coerce").fillna(1.0) if weight else 1.0
    rows = []
    for rnd, subset in work.groupby(round_col):
        valid = subset.dropna(subset=["metric_numeric", "weight_numeric"])
        aggregate = np.average(valid.metric_numeric, weights=valid.weight_numeric) if len(valid) else np.nan
        median = valid.metric_numeric.median() if len(valid) else np.nan
        mad = (valid.metric_numeric - median).abs().median() if len(valid) else np.nan
        for _, row in valid.iterrows():
            robust_z = 0.6745 * (row.metric_numeric - median) / mad if pd.notna(mad) and mad > 0 else 0.0
            rows.append({"round": rnd, "site": row[site], "site_metric": row.metric_numeric, "sample_weight": row.weight_numeric, "weighted_global_metric": aggregate, "robust_site_z": robust_z, "poisoning_review": abs(robust_z) > 3.5})
    audit = pd.DataFrame(rows)
    tables["federated_weighted_aggregation_audit"] = audit
    flagged = int(audit.poisoning_review.sum()) if not audit.empty else 0
    _check(checks, "Federated site outlier screen", "review" if flagged else "pass", f"{flagged} site-round updates flagged")
    if epsilon:
        eps = pd.to_numeric(work[epsilon], errors="coerce").dropna()
        composed = float(eps.sum())
        tables["privacy_budget_composition"] = pd.DataFrame([{"rounds_reported": len(eps), "basic_composed_epsilon": composed, "composition_method": "basic upper bound"}])
        _check(checks, "Privacy budget composition", "review" if composed > float(10) else "pass", f"basic epsilon upper bound={composed:.3g}")


def _trial_enhancement(frame, tables, checks, metrics):
    arm = _column(frame, "arm", "group", "treatment")
    if not arm or frame[arm].nunique() != 2:
        return
    numeric = [str(c) for c in frame.columns if str(c) != arm and pd.to_numeric(frame[c], errors="coerce").notna().mean() >= 0.9]
    rows = []
    groups = list(frame[arm].dropna().unique())
    for column in numeric[:20]:
        a = pd.to_numeric(frame.loc[frame[arm] == groups[0], column], errors="coerce").dropna()
        b = pd.to_numeric(frame.loc[frame[arm] == groups[1], column], errors="coerce").dropna()
        if len(a) < 2 or len(b) < 2:
            continue
        pooled = math.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / max(len(a) + len(b) - 2, 1))
        smd = (b.mean() - a.mean()) / pooled if pooled > 0 else np.nan
        rows.append({"covariate": column, "arm_a": groups[0], "arm_b": groups[1], "mean_a": a.mean(), "mean_b": b.mean(), "standardized_mean_difference": smd, "balanced_abs_smd_lt_0_1": bool(pd.notna(smd) and abs(smd) < 0.1)})
    balance = pd.DataFrame(rows)
    if not balance.empty:
        tables["randomization_covariate_balance"] = balance
        unbalanced = int((balance.standardized_mean_difference.abs() >= 0.1).sum())
        _check(checks, "Randomization covariate balance", "review" if unbalanced else "pass", f"{unbalanced}/{len(balance)} covariates |SMD|≥0.1")


def apply_step155_enhancements(
    *,
    module_key: str,
    family: str,
    frame: pd.DataFrame,
    metadata: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    checks: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    if family == "flow-cytometry":
        _flow_enhancement(frame, metadata, tables, checks, metrics)
    elif family == "mass-spectrometry":
        _metabolomics_enhancement(frame, metadata, tables, checks, metrics)
    elif family == "genomic-variant":
        _variant_enhancement(module_key, frame, metadata, tables, checks, metrics)
    elif family == "single-cell":
        _single_cell_enhancement(frame, tables, checks, metrics)
    elif family == "epigenomics":
        _epigenomics_enhancement(frame, tables, checks, metrics)
    elif family == "pathology-ai":
        _pathology_enhancement(frame, tables, checks, metrics)
    elif family == "clinical-survival":
        _survival_enhancement(frame, tables, checks, metrics)
    elif family == "structural-chemistry":
        _structural_enhancement(frame, tables, checks, metrics)
    elif family == "vaccine-design":
        _vaccine_enhancement(frame, metadata, tables, checks, metrics)
    elif family == "amr-analysis":
        _amr_enhancement(frame, tables, checks, metrics)
    elif family == "federated-ai":
        _federated_enhancement(frame, tables, checks, metrics)
    elif family == "trial-design":
        _trial_enhancement(frame, tables, checks, metrics)


__all__ = ["apply_step155_enhancements"]
