from __future__ import annotations

import math
import time
from collections import Counter
from typing import Any, Callable, Iterable, Mapping

try:
    import numpy as np
except ImportError:
    np = None

try:
    import pandas as pd
except ImportError:
    pd = None
try:
    from sklearn.metrics import (
        accuracy_score,
        average_precision_score,
        balanced_accuracy_score,
        brier_score_loss,
        confusion_matrix,
        f1_score,
        matthews_corrcoef,
        precision_score,
        recall_score,
        roc_auc_score,
    )
except ImportError:
    accuracy_score = None

from biointel.neuro_cns.catalog import MODULES, MODULE_BY_KEY
from biointel.neuro_cns.consistency import evaluate_results
from biointel.neuro_cns.hardening import safe_execute, stable_fingerprint
from biointel.neuro_cns.provenance import resource_registry_rows


def _as_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, pd.Series):
        return [value.to_dict()]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        return [dict(value)]
    return []


def evidence_knowledge_graph(results: Mapping[str, Any], *, maximum_edges: int = 5_000) -> dict[str, Any]:
    """Build a deterministic evidence graph from current module results.

    The graph only reflects supplied/current-session evidence. It does not infer
    unsupported biological links.
    """
    nodes: dict[tuple[str, str], dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def node(kind: str, identifier: Any, label: Any | None = None, **attrs: Any) -> str | None:
        text = str(identifier or "").strip()
        if not text:
            return None
        key = (kind, text.upper())
        node_id = f"{kind}:{text.upper()}"
        existing = nodes.setdefault(key, {"node_id": node_id, "kind": kind, "identifier": text, "label": str(label or text)})
        for attr, value in attrs.items():
            if value not in (None, "", [], {}):
                existing[attr] = value
        return node_id

    def edge(source: str | None, target: str | None, relation: str, module_key: str, **attrs: Any) -> None:
        if not source or not target or len(edges) >= maximum_edges:
            return
        record = {"source": source, "target": target, "relation": relation, "module_key": module_key}
        record.update({k: v for k, v in attrs.items() if v not in (None, "", [], {})})
        edges.append(record)

    for module_key, result in results.items():
        module_id = node("module", module_key, MODULE_BY_KEY.get(module_key).title if module_key in MODULE_BY_KEY else module_key)
        records = _as_records(result)
        if isinstance(result, Mapping):
            for candidate in ("results", "associations", "flags", "side_effect_estimates", "available_models"):
                if candidate in result:
                    records.extend(_as_records(result[candidate]))
            for candidate in ("comparison", "matrix", "gene_summary", "variant_board", "selected_signature_features", "reviewed_events", "region_summary"):
                if candidate in result:
                    records.extend(_as_records(result[candidate]))
        for row in records[:maximum_edges]:
            target_value = row.get("target") or row.get("target_id") or row.get("gene") or row.get("gene_symbol")
            disease_value = row.get("disease") or row.get("disease_category") or row.get("indication")
            pathway_value = row.get("pathway") or row.get("pathway_context")
            compound_value = row.get("compound_id") or row.get("compound") or row.get("drug")
            effect_value = row.get("side_effect_category") or row.get("side_effect")
            organism_value = row.get("organism") or row.get("model")
            trial_value = row.get("trial_id") or row.get("nct_id")
            target_id = node("target", target_value)
            disease_id = node("disease", disease_value)
            pathway_id = node("pathway", pathway_value)
            compound_id = node("compound", compound_value)
            effect_id = node("side_effect", effect_value)
            organism_id = node("model", organism_value)
            trial_id = node("trial", trial_value)
            for entity in (target_id, disease_id, pathway_id, compound_id, effect_id, organism_id, trial_id):
                edge(module_id, entity, "reported", module_key)
            edge(target_id, disease_id, "associated_with", module_key, confidence=row.get("confidence") or row.get("confidence_level"))
            edge(target_id, pathway_id, "participates_in", module_key)
            edge(compound_id, target_id, "interacts_with", module_key, affinity=row.get("affinity_nm") or row.get("binding_score"))
            edge(target_id, effect_id, "linked_to_effect", module_key, likelihood=row.get("likelihood"))
            edge(target_id, organism_id, "has_model", module_key)
            edge(compound_id, trial_id, "evaluated_in", module_key)
            edge(trial_id, disease_id, "studies", module_key)

    node_frame = pd.DataFrame(nodes.values())
    edge_frame = pd.DataFrame(edges).drop_duplicates(ignore_index=True) if edges else pd.DataFrame(columns=["source", "target", "relation", "module_key"])
    connected = set(edge_frame.get("source", [])) | set(edge_frame.get("target", []))
    orphan_count = int((~node_frame["node_id"].isin(connected)).sum()) if not node_frame.empty else 0
    return {
        "nodes": node_frame,
        "edges": edge_frame,
        "node_count": int(len(node_frame)),
        "edge_count": int(len(edge_frame)),
        "orphan_node_count": orphan_count,
        "truncated": len(edges) >= maximum_edges,
        "input_fingerprint_sha256": stable_fingerprint(results),
        "scientific_boundary": "Graph contains only explicit supplied/session associations; no missing edge is interpreted as biological absence.",
    }


def benchmark_validation_center(
    frame: pd.DataFrame,
    *,
    label_column: str,
    score_column: str,
    threshold: float = 0.5,
    group_column: str | None = None,
    bootstrap_iterations: int = 200,
    seed: int = 42,
) -> dict[str, Any]:
    if label_column not in frame or score_column not in frame:
        raise ValueError("label_column and score_column must exist in the benchmark table.")
    work = frame.copy()
    work[label_column] = pd.to_numeric(work[label_column], errors="coerce")
    work[score_column] = pd.to_numeric(work[score_column], errors="coerce")
    work = work.dropna(subset=[label_column, score_column])
    if len(work) < 10:
        raise ValueError("At least 10 complete benchmark rows are required.")
    labels = work[label_column].astype(int).to_numpy()
    if set(np.unique(labels)) != {0, 1}:
        raise ValueError("Benchmark labels must contain both binary classes 0 and 1.")
    scores = np.clip(work[score_column].to_numpy(float), 0.0, 1.0)
    predictions = (scores >= float(threshold)).astype(int)

    def metrics(y: np.ndarray, s: np.ndarray) -> dict[str, float]:
        p = (s >= float(threshold)).astype(int)
        return {
            "roc_auc": float(roc_auc_score(y, s)),
            "average_precision": float(average_precision_score(y, s)),
            "accuracy": float(accuracy_score(y, p)),
            "balanced_accuracy": float(balanced_accuracy_score(y, p)),
            "precision": float(precision_score(y, p, zero_division=0)),
            "sensitivity_recall": float(recall_score(y, p, zero_division=0)),
            "specificity": float(recall_score(1 - y, 1 - p, zero_division=0)),
            "f1": float(f1_score(y, p, zero_division=0)),
            "mcc": float(matthews_corrcoef(y, p)),
            "brier": float(brier_score_loss(y, s)),
        }

    observed = metrics(labels, scores)
    rng = np.random.default_rng(seed)
    bootstrap: dict[str, list[float]] = {key: [] for key in observed}
    for _ in range(max(0, min(int(bootstrap_iterations), 2_000))):
        index = rng.integers(0, len(labels), len(labels))
        y = labels[index]
        if len(np.unique(y)) < 2:
            continue
        values = metrics(y, scores[index])
        for key, value in values.items():
            bootstrap[key].append(value)
    metric_rows = []
    for key, value in observed.items():
        values = np.asarray(bootstrap[key], dtype=float)
        metric_rows.append({
            "metric": key,
            "value": round(value, 6),
            "ci95_low": round(float(np.percentile(values, 2.5)), 6) if len(values) else np.nan,
            "ci95_high": round(float(np.percentile(values, 97.5)), 6) if len(values) else np.nan,
        })
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    bins = pd.cut(scores, bins=np.linspace(0, 1, 11), include_lowest=True, duplicates="drop")
    calibration = pd.DataFrame({"score": scores, "label": labels, "bin": bins}).groupby("bin", observed=False).agg(
        count=("label", "size"), mean_predicted=("score", "mean"), observed_fraction=("label", "mean")
    ).reset_index()
    subgroup_rows: list[dict[str, Any]] = []
    if group_column and group_column in work:
        for group, group_frame in work.groupby(group_column, dropna=False):
            if len(group_frame) < 5 or group_frame[label_column].nunique() < 2:
                subgroup_rows.append({"group": str(group), "n": len(group_frame), "status": "insufficient"})
                continue
            vals = metrics(group_frame[label_column].astype(int).to_numpy(), np.clip(group_frame[score_column].to_numpy(float), 0, 1))
            subgroup_rows.append({"group": str(group), "n": len(group_frame), "status": "evaluated", **{k: round(v, 6) for k, v in vals.items()}})
    return {
        "metrics": pd.DataFrame(metric_rows),
        "confusion_matrix": pd.DataFrame([{"true_negative": int(tn), "false_positive": int(fp), "false_negative": int(fn), "true_positive": int(tp)}]),
        "calibration": calibration,
        "subgroup_performance": pd.DataFrame(subgroup_rows),
        "threshold": float(threshold),
        "n": int(len(work)),
        "positive_fraction": round(float(labels.mean()), 6),
        "scientific_boundary": "Internal benchmark summary; external-site validation, locked datasets and pre-specified acceptance criteria remain required.",
    }


def applicability_domain_inspector(
    reference_frame: pd.DataFrame,
    query_frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
    distance_quantile: float = 0.95,
) -> dict[str, Any]:
    common = [str(c) for c in (feature_columns or reference_frame.select_dtypes(include=[np.number]).columns) if c in reference_frame and c in query_frame]
    if not common:
        raise ValueError("No common numeric feature columns are available.")
    ref = reference_frame[common].apply(pd.to_numeric, errors="coerce")
    qry = query_frame[common].apply(pd.to_numeric, errors="coerce")
    medians = ref.median()
    ref = ref.fillna(medians)
    qry = qry.fillna(medians)
    mad = (ref - medians).abs().median().replace(0, np.nan)
    scale = (1.4826 * mad).fillna(ref.std(ddof=0).replace(0, 1.0)).replace(0, 1.0)
    ref_z = ((ref - medians) / scale).to_numpy(float)
    qry_z = ((qry - medians) / scale).to_numpy(float)
    centre_distance = np.sqrt(np.mean(ref_z**2, axis=1))
    threshold = float(np.quantile(centre_distance, min(max(float(distance_quantile), 0.5), 0.999)))
    rows: list[dict[str, Any]] = []
    for index, vector in enumerate(qry_z):
        distances = np.sqrt(np.mean((ref_z - vector) ** 2, axis=1))
        nearest_position = int(np.argmin(distances))
        centre = float(np.sqrt(np.mean(vector**2)))
        rows.append({
            "query_index": query_frame.index[index],
            "distance_from_reference_centre": round(centre, 6),
            "nearest_reference_index": reference_frame.index[nearest_position],
            "nearest_reference_distance": round(float(distances[nearest_position]), 6),
            "inside_applicability_domain": bool(centre <= threshold),
            "domain_margin": round(threshold - centre, 6),
        })
    output = pd.DataFrame(rows)
    return {
        "assessment": output,
        "feature_columns": common,
        "distance_threshold": round(threshold, 6),
        "inside_fraction": round(float(output["inside_applicability_domain"].mean()), 6),
        "reference_rows": int(len(ref)),
        "query_rows": int(len(qry)),
        "scientific_boundary": "Robust feature-space distance is an applicability screen, not proof of biological validity.",
    }


def uncertainty_sensitivity_lab(
    evaluator: Callable[..., float],
    base_parameters: Mapping[str, float],
    uncertainty: Mapping[str, Mapping[str, float]],
    *,
    iterations: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    count = max(50, min(int(iterations), 5_000))
    rng = np.random.default_rng(seed)
    names = list(base_parameters)
    sampled: dict[str, np.ndarray] = {}
    for name in names:
        base = float(base_parameters[name])
        spec = dict(uncertainty.get(name) or {})
        distribution = str(spec.get("distribution", "normal")).lower()
        if distribution == "uniform":
            low = float(spec.get("low", base * 0.9))
            high = float(spec.get("high", base * 1.1))
            values = rng.uniform(min(low, high), max(low, high), count)
        elif distribution == "lognormal":
            cv = max(float(spec.get("cv", 0.2)), 1e-9)
            sigma = math.sqrt(math.log(1 + cv * cv))
            mean = math.log(max(base, 1e-12)) - sigma * sigma / 2
            values = rng.lognormal(mean, sigma, count)
        else:
            sd = abs(float(spec.get("sd", max(abs(base) * 0.1, 1e-9))))
            values = rng.normal(base, sd, count)
        if "minimum" in spec:
            values = np.maximum(values, float(spec["minimum"]))
        if "maximum" in spec:
            values = np.minimum(values, float(spec["maximum"]))
        sampled[name] = values
    outputs = np.empty(count, dtype=float)
    for i in range(count):
        parameters = {name: float(sampled[name][i]) for name in names}
        outputs[i] = float(evaluator(**parameters))
    finite = np.isfinite(outputs)
    if finite.sum() < max(10, count // 2):
        raise ValueError("Evaluator produced too few finite outputs for uncertainty analysis.")
    outputs = outputs[finite]
    sensitivity_rows = []
    for name in names:
        values = sampled[name][finite]
        correlation = float(pd.Series(values).corr(pd.Series(outputs), method="spearman")) if len(np.unique(values)) > 1 else 0.0
        sensitivity_rows.append({"parameter": name, "spearman_correlation": round(correlation, 6), "absolute_influence": round(abs(correlation), 6)})
    sensitivity = pd.DataFrame(sensitivity_rows).sort_values("absolute_influence", ascending=False, ignore_index=True)
    return {
        "output_summary": {
            "iterations_requested": int(iterations),
            "iterations_valid": int(len(outputs)),
            "mean": round(float(np.mean(outputs)), 6),
            "median": round(float(np.median(outputs)), 6),
            "sd": round(float(np.std(outputs, ddof=1)), 6),
            "ci95_low": round(float(np.percentile(outputs, 2.5)), 6),
            "ci95_high": round(float(np.percentile(outputs, 97.5)), 6),
        },
        "sensitivity": sensitivity,
        "samples": pd.DataFrame({**{name: sampled[name][finite] for name in names}, "output": outputs}).head(5_000),
        "scientific_boundary": "Monte Carlo uncertainty reflects only specified parameter distributions and evaluator assumptions.",
    }


MODULE_RESOURCE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "bbb_permeability": ("bbb_reference",),
    "neuro_target_curation": ("target_registry",),
    "neurotransmitter_pathway": ("target_registry",),
    "ion_channel_classifier": ("protein_domains",),
    "gpcr_classifier": ("gpcr_reference",),
    "cns_disease_targets": ("target_registry",),
    "cns_drug_likeness": ("bbb_reference",),
    "off_target_neurotoxicity": ("target_registry",),
    "aggregation_risk": ("aggregation_method",),
    "cns_side_effects": ("side_effect_map", "side_effect_reference"),
    "neuroinflammation": ("target_registry",),
    "blood_csf_barrier": ("blood_csf_method",),
    "model_organism": ("model_organisms",),
    "cns_adme_transporters": ("adme_models",),
    "brain_exposure_pk": ("pk_validation",),
    "receptor_occupancy": ("pk_validation",),
    "neurogenetics": ("variant_evidence",),
    "brain_expression_atlas": ("brain_expression",),
    "neuro_omics_biomarkers": ("omics_external_validation",),
    "eeg_meg_analytics": ("neural_signal_adapters",),
    "neuroimaging_connectomics": ("neuroimaging_adapters",),
    "cns_clinical_trials": ("clinical_trials",),
    "precision_neurology": ("precision_external_cohort",),
    "neurovascular_research": ("neurovascular_cohort",),
    "sleep_circadian": ("sleep_circadian_benchmark",),
    "fluid_biomarkers": ("fluid_biomarker_reference",),
    "digital_neurology": ("digital_neurology_reference",),
    "neuroimmune_interactions": ("neuroimmune_reference",),
    "cognitive_trajectory": ("longitudinal_cognition_reference",),
    "neurorehabilitation": ("digital_neurology_reference",),
    "polypharmacy_cns": ("cns_medication_reference",),
    "brain_network_vulnerability": ("connectome_resilience_benchmark",),
    "neurodevelopmental_trajectory": ("longitudinal_cognition_reference",),
}


def resource_qualification_manager(resources: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    rows = [dict(row) for row in (resources or resource_registry_rows())]
    index = {str(row.get("resource_id")): row for row in rows}
    module_rows: list[dict[str, Any]] = []
    for module in MODULES:
        required = MODULE_RESOURCE_REQUIREMENTS.get(module.key, ())
        missing = []
        unqualified = []
        for resource_id in required:
            row = index.get(resource_id)
            if not row or not row.get("installed"):
                missing.append(resource_id)
            elif not row.get("release_eligible"):
                unqualified.append(resource_id)
        if missing:
            status = "blocked"
        elif unqualified:
            status = "exploratory_only"
        else:
            status = "resource_ready"
        module_rows.append({
            "module": module.number,
            "module_key": module.key,
            "title": module.title,
            "required_resources": ", ".join(required) or "none",
            "missing_resources": ", ".join(missing),
            "unqualified_resources": ", ".join(unqualified),
            "resource_status": status,
            "software_available": True,
            "controlled_release_eligible": status == "resource_ready" and bool(required),
        })
    module_frame = pd.DataFrame(module_rows)
    resource_frame = pd.DataFrame(rows)
    return {
        "resources": resource_frame,
        "modules": module_frame,
        "resource_ready_modules": int((module_frame["resource_status"] == "resource_ready").sum()),
        "blocked_modules": int((module_frame["resource_status"] == "blocked").sum()),
        "exploratory_modules": int((module_frame["resource_status"] == "exploratory_only").sum()),
        "completion_fraction": round(float((module_frame["resource_status"] == "resource_ready").mean()), 6),
    }


def contradiction_resolution_board(results: Mapping[str, Any]) -> dict[str, Any]:
    findings = evaluate_results(dict(results)).copy()
    resolution_map = {
        "BBB_PK_CONFLICT": ("Verify PK units, passive permeability and efflux parameters; rerun with measured values.", False),
        "OCCUPANCY_WITHOUT_PK": ("Link a Brain Exposure PK result or document the external free-brain concentration source.", False),
        "AFFINITY_ROWS_INVALID": ("Normalize affinity units and remove non-finite/non-positive values.", True),
        "LOW_SIDE_EFFECT_COVERAGE": ("Expand the target panel or bind an approved side-effect resource; preserve uncovered-target warnings.", False),
    }
    if findings.empty:
        board = pd.DataFrame(columns=["severity", "rule", "modules", "message", "recommended_resolution", "auto_fixable", "review_status"])
    else:
        board = findings.copy()
        board["recommended_resolution"] = board["rule"].map(lambda key: resolution_map.get(key, ("Review input assumptions, units, provenance and resource coverage before interpretation.", False))[0])
        board["auto_fixable"] = board["rule"].map(lambda key: resolution_map.get(key, ("", False))[1])
        board["review_status"] = "open"
        priority = {"high": 0, "medium": 1, "low": 2, "info": 3}
        board["_priority"] = board["severity"].astype(str).map(priority).fillna(4).astype(int)
        board = board.sort_values(["_priority", "rule"], ignore_index=True).drop(columns="_priority")
    return {
        "board": board,
        "open_count": int(len(board)),
        "high_count": int((board.get("severity", pd.Series(dtype=str)) == "high").sum()),
        "auto_fixable_count": int(board.get("auto_fixable", pd.Series(dtype=bool)).sum()),
        "scientific_boundary": "Resolution recommendations support review; they do not silently rewrite scientific results.",
    }


def batch_pipeline_orchestrator(
    tasks: Iterable[Mapping[str, Any]],
    *,
    executor: Callable[[dict[str, Any]], dict[str, Any]],
    continue_on_error: bool = True,
) -> dict[str, Any]:
    task_rows = [dict(task) for task in tasks]
    if not task_rows:
        raise ValueError("At least one task is required.")
    if len(task_rows) > 1_000:
        raise ValueError("A maximum of 1,000 tasks is supported per orchestration batch.")
    outputs: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index, task in enumerate(task_rows):
        task_id = str(task.get("task_id") or f"task_{index + 1}")
        envelope = safe_execute(
            str(task.get("module_key") or "unknown"),
            lambda task=task: executor(task),
            inputs=task,
            interactive=False,
        )
        outputs.append({
            "task_id": task_id,
            "module_key": envelope.module_key,
            "status": envelope.status,
            "elapsed_ms": envelope.elapsed_ms,
            "peak_memory_mb": envelope.peak_memory_mb,
            "input_fingerprint_sha256": envelope.input_fingerprint_sha256,
            "result": envelope.result,
            "error": envelope.error.message if envelope.error else None,
            "recovery_code": envelope.error.recovery_code if envelope.error else None,
        })
        if envelope.status == "failed" and not continue_on_error:
            break
    completed = sum(row["status"] == "completed" for row in outputs)
    return {
        "tasks": outputs,
        "submitted": len(task_rows),
        "executed": len(outputs),
        "completed": completed,
        "failed": len(outputs) - completed,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "continued_after_errors": bool(continue_on_error),
    }


def failure_recovery_center(error_records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = [dict(row) for row in error_records]
    rules = {
        "INPUT_VALIDATION": ("Correct required fields, accepted characters, ranges and table schema.", "user_input"),
        "SCHEMA_MISMATCH": ("Map/rename columns using the expected schema before rerunning.", "data_schema"),
        "UNIT_MISMATCH": ("Select a supported unit and verify all concentration/affinity dimensions.", "units"),
        "MISSING_RESOURCE": ("Install/bind the required adapter or keep the module in fail-closed exploratory mode.", "resource"),
        "RESOURCE_EXHAUSTION": ("Use background execution, split input and reduce visual/downsampling limits.", "performance"),
        "ENGINE_FAILURE": ("Capture the run fingerprint, preserve the input, and review the engine log before retry.", "engine"),
    }
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        code = str(record.get("recovery_code") or "ENGINE_FAILURE")
        recommendation, category = rules.get(code, rules["ENGINE_FAILURE"])
        rows.append({
            "error_id": str(record.get("error_id") or f"error_{index + 1}"),
            "module_key": str(record.get("module_key") or "unknown"),
            "error_type": str(record.get("error_type") or "Error"),
            "message": str(record.get("message") or record.get("error") or "Unspecified error"),
            "recovery_code": code,
            "category": category,
            "recommended_action": recommendation,
            "retry_safe": code in {"INPUT_VALIDATION", "SCHEMA_MISMATCH", "UNIT_MISMATCH", "RESOURCE_EXHAUSTION"},
            "status": "open",
        })
    frame = pd.DataFrame(rows)
    summary = Counter(frame["category"].tolist()) if not frame.empty else Counter()
    return {
        "errors": frame,
        "error_count": int(len(frame)),
        "retry_safe_count": int(frame.get("retry_safe", pd.Series(dtype=bool)).sum()),
        "category_summary": pd.DataFrame([{"category": key, "count": value} for key, value in summary.items()]),
    }


def maximum_potential_release_dashboard(
    results: Mapping[str, Any],
    *,
    test_status: Mapping[str, Any] | None = None,
    resources: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    qualification = resource_qualification_manager(resources)
    qualification_frame = qualification["modules"].set_index("module_key")
    completed_keys = set(results)
    rows: list[dict[str, Any]] = []
    for module in MODULES:
        resource_status = str(qualification_frame.loc[module.key, "resource_status"])
        output_present = module.key in completed_keys
        software_score = 10.0 if output_present else 8.5
        scientific_score = {"resource_ready": 8.5, "exploratory_only": 5.5, "blocked": 3.5}.get(resource_status, 3.0)
        if "Exploratory" in module.readiness or "exploratory" in module.boundary.lower():
            scientific_score = min(scientific_score, 4.5)
        overall = 0.45 * software_score + 0.55 * scientific_score
        rows.append({
            "module": module.number,
            "module_key": module.key,
            "title": module.title,
            "result_present": output_present,
            "resource_status": resource_status,
            "software_readiness": round(software_score, 2),
            "scientific_readiness": round(scientific_score, 2),
            "overall_readiness": round(overall, 2),
            "maximum_potential": 9.5 if module.number not in {10, 12} else 9.0,
            "release_tier": "research-qualified" if scientific_score >= 8 else "exploratory" if scientific_score >= 5 else "demo",
        })
    frame = pd.DataFrame(rows)
    consistency = evaluate_results(dict(results))
    tests_passed = int((test_status or {}).get("passed", 0) or 0)
    tests_failed = int((test_status or {}).get("failed", 0) or 0)
    blockers = []
    if qualification["blocked_modules"]:
        blockers.append(f"{qualification['blocked_modules']} module(s) have missing required scientific resources.")
    if not consistency.empty and (consistency["severity"] == "high").any():
        blockers.append("High-severity cross-module consistency findings remain open.")
    if tests_failed:
        blockers.append(f"{tests_failed} automated test(s) failed.")
    return {
        "module_dashboard": frame,
        "average_software_readiness": round(float(frame["software_readiness"].mean()), 3),
        "average_scientific_readiness": round(float(frame["scientific_readiness"].mean()), 3),
        "average_overall_readiness": round(float(frame["overall_readiness"].mean()), 3),
        "completed_module_results": int(frame["result_present"].sum()),
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "controlled_release_eligible": not blockers and bool(results) and tests_passed > 0,
        "blockers": blockers or ["Responsible scientific sign-off remains required."],
        "scientific_boundary": "Maximum-potential dashboard separates software completion from scientific qualification; scores are operational indicators, not clinical claims.",
    }


MAX_POTENTIAL_FEATURES = (
    (1, "Neuro Evidence Knowledge Graph", "evidence_knowledge_graph"),
    (2, "Benchmark Validation Center", "benchmark_validation_center"),
    (3, "Applicability Domain Inspector", "applicability_domain_inspector"),
    (4, "Uncertainty & Sensitivity Lab", "uncertainty_sensitivity_lab"),
    (5, "Scientific Resource Qualification Manager", "resource_qualification_manager"),
    (6, "Cross-Module Contradiction Resolver", "contradiction_resolution_board"),
    (7, "Resilient Batch Pipeline Orchestrator", "batch_pipeline_orchestrator"),
    (8, "Failure Mode & Recovery Center", "failure_recovery_center"),
    (9, "Maximum-Potential Release Dashboard", "maximum_potential_release_dashboard"),
)
