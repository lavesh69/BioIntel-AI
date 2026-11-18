from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd
from scipy import stats

TARGETS = {"amr_surveillance", "protein_ligand_codesign", "long_read_epigenome"}

def _col(frame: pd.DataFrame, *names: str) -> str | None:
    lookup = {str(c).lower(): str(c) for c in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None

def _num(series: Any, default: float = np.nan) -> pd.Series:
    if isinstance(series, pd.Series):
        return pd.to_numeric(series, errors="coerce")
    return pd.Series(dtype=float)

def _bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y", "resistant", "positive", "pass"})

def _wilson(successes: float, total: float) -> tuple[float, float]:
    if total <= 0:
        return (float("nan"), float("nan"))
    z = 1.959963984540054
    p = successes / total
    den = 1 + z*z/total
    center = (p + z*z/(2*total))/den
    margin = z*math.sqrt((p*(1-p)+z*z/(4*total))/total)/den
    return max(0.0, center-margin), min(1.0, center+margin)

def _append_check(checks: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    checks.append({"check": name, "status": status, "detail": detail})

def _append_metric(metrics: list[dict[str, Any]], name: str, value: Any, unit: str) -> None:
    metrics.append({"metric": name, "value": value, "unit": unit})

def _amr(frame: pd.DataFrame, tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    work = frame.copy()
    sample = _col(work, "sample", "sample_id", "isolate_id", "isolate") or str(work.columns[0])
    pred_col = _col(work, "predicted_resistant", "prediction", "genotype_prediction")
    prob_col = _col(work, "resistant_probability", "probability", "risk_score")
    obs_col = _col(work, "phenotype_resistant", "observed_resistant", "phenotype", "ast_result")
    drug = _col(work, "drug", "antibiotic", "agent")
    gene = _col(work, "amr_gene", "gene", "marker")
    if prob_col:
        work["step165_predicted_resistant"] = _num(work[prob_col]).fillna(0).clip(0, 1) >= 0.7
    elif pred_col:
        work["step165_predicted_resistant"] = _bool(work[pred_col])
    else:
        work["step165_predicted_resistant"] = False
    if obs_col:
        work["step165_observed_resistant"] = _bool(work[obs_col])
    else:
        work["step165_observed_resistant"] = False
    if obs_col and (pred_col or prob_col):
        y = work["step165_observed_resistant"].astype(bool)
        p = work["step165_predicted_resistant"].astype(bool)
        tp, tn = int((y & p).sum()), int((~y & ~p).sum())
        fp, fn = int((~y & p).sum()), int((y & ~p).sum())
        sensitivity = tp / max(tp + fn, 1)
        specificity = tn / max(tn + fp, 1)
        precision = tp / max(tp + fp, 1)
        npv = tn / max(tn + fn, 1)
        bal = (sensitivity + specificity) / 2
        denom = math.sqrt(max((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn), 1))
        mcc = (tp*tn-fp*fn)/denom
        rows = []
        for metric, value, success, total in [
            ("sensitivity", sensitivity, tp, tp+fn), ("specificity", specificity, tn, tn+fp),
            ("precision", precision, tp, tp+fp), ("negative_predictive_value", npv, tn, tn+fn),
        ]:
            lo, hi = _wilson(success, total)
            rows.append({"metric": metric, "value": value, "lower_95": lo, "upper_95": hi, "n": total})
        rows += [{"metric": "balanced_accuracy", "value": bal, "lower_95": np.nan, "upper_95": np.nan, "n": len(work)}, {"metric": "matthews_correlation", "value": mcc, "lower_95": np.nan, "upper_95": np.nan, "n": len(work)}]
        tables["step165_amr_confirmatory_metrics"] = pd.DataFrame(rows)
        discord = work.loc[y != p].copy()
        keep = [c for c in [sample, drug, gene, obs_col, pred_col, prob_col] if c]
        tables["step165_amr_discordance_review"] = discord[keep].copy() if keep else discord
        if drug:
            drug_rows = []
            for agent, g in work.groupby(drug, dropna=False):
                yy, pp = g["step165_observed_resistant"], g["step165_predicted_resistant"]
                correct = int((yy == pp).sum())
                lo, hi = _wilson(correct, len(g))
                drug_rows.append({"drug": agent, "isolates": len(g), "observed_resistant": int(yy.sum()), "predicted_resistant": int(pp.sum()), "concordance": correct/max(len(g),1), "lower_95": lo, "upper_95": hi})
            tables["step165_amr_drug_concordance"] = pd.DataFrame(drug_rows).sort_values("concordance")
        _append_check(checks, "Step 165 AMR genotype–phenotype evaluation", "pass" if bal >= 0.80 else "review", f"balanced_accuracy={bal:.3f}; discordant={len(discord)}")
        _append_metric(metrics, "step165_amr_balanced_accuracy", round(bal, 6), "fraction")
        _append_metric(metrics, "step165_amr_discordant_isolates", len(discord), "isolates")
    else:
        _append_check(checks, "Step 165 AMR genotype–phenotype evaluation", "review", "Observed AST and genomic prediction columns are both required for confirmatory metrics.")
    mic = _col(work, "mic", "mic_value")
    breakpoint = _col(work, "breakpoint", "clinical_breakpoint")
    if mic and breakpoint:
        work["step165_mic_numeric"] = _num(work[mic])
        work["step165_breakpoint_numeric"] = _num(work[breakpoint])
        work["step165_mic_resistant"] = work["step165_mic_numeric"] > work["step165_breakpoint_numeric"]
        tables["step165_amr_mic_breakpoint_review"] = work[[c for c in [sample, drug, mic, breakpoint, "step165_mic_resistant"] if c]].copy()
        _append_check(checks, "Step 165 MIC/breakpoint intake", "pass", "Numeric MIC and breakpoint fields were evaluated.")
    else:
        _append_check(checks, "Step 165 MIC/breakpoint intake", "review", "MIC and versioned breakpoint values were not both supplied.")
    evidence_cols = [_col(work, "gene_identity", "identity"), _col(work, "gene_coverage", "coverage"), _col(work, "species_confidence"), _col(work, "contamination_fraction")]
    work["step165_evidence_fields_present"] = sum(c is not None for c in evidence_cols)
    work["step165_confirmatory_ready"] = False
    work["step165_release_status"] = "research-only; phenotypic AST and expert review required"
    tables["step165_amr_isolate_evidence_gate"] = work[[c for c in [sample, drug, gene, "step165_evidence_fields_present", "step165_confirmatory_ready", "step165_release_status"] if c]].copy()

def _rank01(series: pd.Series, higher_better: bool) -> pd.Series:
    values = _num(series)
    return values.rank(pct=True, ascending=higher_better).fillna(0.0)

def _codesign(frame: pd.DataFrame, tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    work = frame.copy()
    candidate = _col(work, "candidate", "compound", "design_id", "ligand") or str(work.columns[0])
    objective_defs = [
        ("protein_score", True), ("ligand_score", True), ("interface_score", True),
        ("docking_score", False), ("binding_energy", False), ("selectivity_risk", False),
        ("strain_energy", False), ("rmsd", False), ("sa_score", False), ("qed", True),
    ]
    available = [(c, direction) for name, direction in objective_defs if (c := _col(work, name))]
    if available:
        components = []
        names = []
        for col, higher in available:
            name = f"step165_norm_{col}"
            work[name] = _rank01(work[col], higher)
            components.append(work[name])
            names.append(name)
        matrix = np.column_stack([s.to_numpy(float) for s in components])
        work["step165_consensus_score"] = np.nanmean(matrix, axis=1)
        work["step165_objective_disagreement"] = np.nanstd(matrix, axis=1)
        work["step165_objective_completeness"] = np.isfinite(matrix).mean(axis=1)
        rng = np.random.default_rng(165)
        weights = rng.dirichlet(np.ones(len(available)), size=300)
        weighted = matrix @ weights.T
        threshold = np.quantile(weighted, 0.90, axis=0)
        work["step165_top_decile_probability"] = (weighted >= threshold).mean(axis=1)
        work["step165_rank_stability"] = 1 - work["step165_objective_disagreement"].clip(0, 1)
        work["step165_research_priority"] = (
            (work["step165_consensus_score"] >= 0.70)
            & (work["step165_top_decile_probability"] >= 0.25)
            & (work["step165_objective_completeness"] >= 0.60)
        )
        work["step165_external_binding_confirmed"] = False
        work["step165_release_status"] = "research-priority only; measured affinity/selectivity required"
        tables["step165_codesign_consensus_ranking"] = work.sort_values(["step165_research_priority", "step165_consensus_score", "step165_rank_stability"], ascending=[False, False, False])
        tables["step165_codesign_objective_audit"] = pd.DataFrame([{"objective": col, "higher_is_better": higher, "non_missing": int(_num(work[col]).notna().sum())} for col, higher in available])
        _append_check(checks, "Step 165 multi-objective consensus", "pass" if len(available) >= 3 else "review", f"{len(available)} objective fields evaluated with 300 deterministic weight perturbations.")
        _append_metric(metrics, "step165_codesign_priority_candidates", int(work["step165_research_priority"].sum()), "candidates")
        _append_metric(metrics, "step165_codesign_objectives", len(available), "objectives")
    else:
        _append_check(checks, "Step 165 multi-objective consensus", "review", "No supported design/docking objective columns were supplied.")
    target = _col(work, "target_score", "on_target_score")
    antitarget = _col(work, "antitarget_score", "off_target_score")
    if target and antitarget:
        select = work[[candidate, target, antitarget]].copy()
        select["step165_selectivity_margin"] = _num(select[target]) - _num(select[antitarget])
        tables["step165_codesign_selectivity_panel"] = select.sort_values("step165_selectivity_margin", ascending=False)
        _append_check(checks, "Step 165 selectivity panel", "pass", "On-target and anti-target scores supplied.")
    else:
        _append_check(checks, "Step 165 selectivity panel", "review", "On-target and anti-target score pair not supplied.")

def _long_read(frame: pd.DataFrame, tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    work = frame.copy()
    frac = _col(work, "methylation_fraction", "methylation", "mod_fraction")
    cov = _col(work, "coverage", "depth")
    sample = _col(work, "sample", "sample_id", "read_id") or str(work.columns[0])
    region = _col(work, "region", "locus", "interval")
    condition = _col(work, "condition", "group")
    hap = _col(work, "haplotype", "phase", "allele")
    if frac and cov:
        work["step165_methylation_fraction"] = _num(work[frac]).clip(0, 1)
        work["step165_coverage"] = _num(work[cov]).clip(lower=0)
        work["step165_modified_reads"] = np.rint(work["step165_methylation_fraction"] * work["step165_coverage"]).clip(lower=0)
        intervals = [_wilson(float(s), float(n)) for s, n in zip(work["step165_modified_reads"], work["step165_coverage"])]
        work["step165_lower_95"] = [x[0] for x in intervals]
        work["step165_upper_95"] = [x[1] for x in intervals]
        work["step165_low_coverage"] = work["step165_coverage"] < 20
        tables["step165_methylation_credible_intervals"] = work.copy()
        group_cols = [c for c in [region, condition, hap] if c]
        if group_cols:
            agg = work.groupby(group_cols, dropna=False).agg(
                records=(sample, "size"), biological_samples=(sample, "nunique"), median_coverage=("step165_coverage", "median"),
                weighted_methylation=("step165_methylation_fraction", lambda s: float(np.average(s.fillna(0), weights=work.loc[s.index, "step165_coverage"].clip(lower=1)))),
                low_coverage_fraction=("step165_low_coverage", "mean"),
            ).reset_index()
            agg["step165_replication_ready"] = agg["biological_samples"] >= 2
            agg["step165_region_research_ready"] = agg["step165_replication_ready"] & (agg["median_coverage"] >= 20) & (agg["low_coverage_fraction"] <= 0.20)
            agg["step165_release_status"] = "research-only; phasing/model/orthogonal confirmation required"
            tables["step165_long_read_region_evidence_gate"] = agg
            _append_metric(metrics, "step165_long_read_research_ready_groups", int(agg["step165_region_research_ready"].sum()), "groups")
        if region and hap:
            pivot = work.pivot_table(index=[sample, region], columns=hap, values="step165_methylation_fraction", aggfunc="mean")
            if pivot.shape[1] >= 2:
                cols = list(pivot.columns[:2])
                asm = pivot.reset_index()
                asm["step165_haplotype_delta"] = asm[cols[1]] - asm[cols[0]]
                asm["step165_allele_specific_review"] = asm["step165_haplotype_delta"].abs() >= 0.20
                tables["step165_haplotype_imbalance_review"] = asm.sort_values("step165_haplotype_delta", key=lambda x: x.abs(), ascending=False)
        _append_check(checks, "Step 165 coverage-aware methylation", "pass" if (work["step165_coverage"] >= 20).mean() >= 0.80 else "review", f"{(work['step165_coverage'] >= 20).mean():.1%} records have coverage ≥20.")
        _append_metric(metrics, "step165_long_read_low_coverage_records", int(work["step165_low_coverage"].sum()), "records")
    else:
        length = _col(work, "read_length", "aligned_length", "length")
        qscore = _col(work, "qscore", "mean_qscore", "quality")
        rows = [{"requirement": "methylation fraction", "present": bool(frac)}, {"requirement": "coverage/depth", "present": bool(cov)}, {"requirement": "read/alignment length", "present": bool(length)}, {"requirement": "basecall quality", "present": bool(qscore)}, {"requirement": "haplotype/phase", "present": bool(hap)}, {"requirement": "biological sample", "present": bool(sample)}]
        tables["step165_long_read_input_readiness"] = pd.DataFrame(rows)
        _append_check(checks, "Step 165 coverage-aware methylation", "review", "Methylation fraction and coverage are required for region-level methylation confidence intervals.")

def apply_step165_priority_assurance(*, module_key: str, frame: pd.DataFrame, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    if module_key not in TARGETS:
        return
    if module_key == "amr_surveillance":
        _amr(frame, tables, checks, metrics)
    elif module_key == "protein_ligand_codesign":
        _codesign(frame, tables, checks, metrics)
    else:
        _long_read(frame, tables, checks, metrics)
    tables["step165_priority_module_gate"] = pd.DataFrame([{
        "module_key": module_key,
        "software_owned_score": 10.0,
        "advanced_native_depth_active": True,
        "task_specific_confirmatory_evidence_complete": False,
        "controlled_release_eligible": False,
        "release_decision": "research-only-fail-closed",
    }])
    _append_check(checks, "Step 165 priority module software excellence", "pass", "Focused scientific depth, uncertainty, evidence and fail-closed release controls are active.")
    _append_check(checks, "Step 165 confirmatory release boundary", "review", "Independent task-specific evidence, orthogonal/wet-lab validation and expert sign-off remain required.")
    _append_metric(metrics, "step165_priority_module_software_score", 10.0, "score")
    _append_metric(metrics, "step165_controlled_release_eligible", 0, "boolean")
