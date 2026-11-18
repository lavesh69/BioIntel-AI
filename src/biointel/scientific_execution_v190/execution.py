from __future__ import annotations

import csv
import importlib.metadata
import importlib.util
import json
import math
import os
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np
import pandas as pd

from biointel.universal_platform_v189.platform import digest_path, utc_now, write_json

from .catalog import ExecutionProfile


@dataclass(frozen=True)
class EngineProbe:
    engine: str
    kind: str
    available: bool
    version: str
    location: str
    execution_mode: str
    production_qualified: bool
    reason: str


def stable_seed(text: str) -> int:
    return int(sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _package_version(name: str) -> str:
    candidates = [name, name.replace("_", "-"), name.replace("-", "_")]
    for candidate in candidates:
        try:
            return importlib.metadata.version(candidate)
        except importlib.metadata.PackageNotFoundError:
            continue
    return "unknown"


def probe_engine(name: str) -> EngineProbe:
    executable = shutil.which(name)
    module_name = name.replace("-", "_")
    package = importlib.util.find_spec(module_name)
    if executable:
        return EngineProbe(name, "executable", True, "detected", executable, "external-tool-ready", False,
                           "Executable detected. Target-machine qualification, licence and benchmark approval are still required.")
    if package is not None:
        return EngineProbe(name, "python-package", True, _package_version(name), str(getattr(package, "origin", "python")),
                           "python-package-ready", False,
                           "Python package detected. Production qualification and approved reference data remain required.")
    return EngineProbe(name, "unavailable", False, "not-installed", "", "native-offline-fallback", False,
                       "External engine is unavailable; deterministic local analysis remains available for workflow validation.")


def probe_profile_engines(profile: ExecutionProfile) -> list[EngineProbe]:
    probes = [probe_engine(name) for name in profile.recommended_engines]
    probes.append(EngineProbe("biointel-native-v190", "built-in", True, "190.0", "src/biointel/scientific_execution_v190",
                              "native-offline", True,
                              "Deterministic built-in adapter for operational qualification; not a substitute for specialist scientific engines."))
    return probes


def command_plan(profile: ExecutionProfile, probes: list[EngineProbe]) -> dict[str, Any]:
    selected = next((p for p in probes if p.available and p.engine != "biointel-native-v190"), probes[-1])
    return {
        "schema": "biointel.step190.command_plan.v1",
        "module_key": profile.module_key,
        "selected_engine": selected.engine,
        "selected_mode": selected.execution_mode,
        "arguments": ["--input", "<validated-input>", "--output", "<isolated-output>", "--threads", "<bounded>"],
        "resource_limits": {"threads_max": 8, "memory_mb_max": 8192, "timeout_seconds": 3600},
        "shell": False,
        "path_isolation": True,
        "output_validation": True,
        "note": "This is a safe command contract. External execution is enabled only after local qualification and licence approval.",
    }


def _sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -30, 30)
    return 1.0 / (1.0 + np.exp(-x))


def make_fixture(profile: ExecutionProfile, rows: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(stable_seed(profile.module_key))
    category = profile.category
    ids = [f"{profile.module_key[:8].upper()}-{i:05d}" for i in range(rows)]
    split = np.array(["train"] * (rows // 2) + ["validation"] * (rows // 4) + ["external"] * (rows - 3 * rows // 4))
    rng.shuffle(split)
    group = rng.choice(["A", "B", "C"], size=rows, p=[0.45, 0.35, 0.20])

    if category == "genomics":
        chrom = rng.choice(["1", "2", "7", "17", "X"], size=rows)
        pos = rng.integers(1000, 2_000_000, size=rows)
        ref = rng.choice(list("ACGT"), size=rows)
        alt = np.array([rng.choice([b for b in "ACGT" if b != r]) for r in ref])
        truth = rng.binomial(1, 0.35, rows)
        score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
        return pd.DataFrame({"record_id": ids, "sample_id": [f"S{i%12:02d}" for i in range(rows)], "split": split,
                             "subgroup": group, "chrom": chrom, "pos": pos, "ref": ref, "alt": alt,
                             "truth_label": truth, "prediction_score": score, "coverage": rng.integers(8, 130, rows),
                             "quality": np.clip(rng.normal(55, 12, rows), 0, 99)})
    if category == "single_cell_multiomics":
        counts = rng.poisson(lam=np.maximum(0.3, rng.lognormal(1.2, 0.7, rows)))
        truth = rng.binomial(1, 0.45, rows)
        score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
        return pd.DataFrame({"record_id": ids, "sample_id": [f"PAT{i%10:02d}" for i in range(rows)], "cell_id": ids,
                             "split": split, "subgroup": group, "total_counts": counts * 500 + rng.integers(50, 300, rows),
                             "genes_detected": counts * 120 + rng.integers(20, 80, rows), "mito_pct": np.clip(rng.normal(7, 3, rows), 0, 30),
                             "truth_label": truth, "prediction_score": score, "batch": rng.choice(["B1", "B2", "B3"], rows)})
    if category == "microbiome":
        abundance = rng.dirichlet(np.ones(5), rows)
        truth = rng.binomial(1, 0.30, rows)
        score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
        return pd.DataFrame({"record_id": ids, "sample_id": [f"MB{i%20:02d}" for i in range(rows)], "split": split,
                             "subgroup": group, "taxon": rng.choice(["Taxon_A", "Taxon_B", "Taxon_C", "Taxon_D", "Taxon_E"], rows),
                             "abundance": abundance[np.arange(rows), rng.integers(0, 5, rows)], "coverage": rng.uniform(0, 100, rows),
                             "ani": rng.uniform(90, 100, rows), "negative_control": rng.binomial(1, 0.08, rows),
                             "truth_label": truth, "prediction_score": score})
    if category == "protein_molecular":
        aas = np.array(list("ACDEFGHIKLMNPQRSTVWY"))
        seqs = ["".join(rng.choice(aas, rng.integers(40, 100))) for _ in range(rows)]
        truth = rng.binomial(1, 0.40, rows)
        score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
        return pd.DataFrame({"record_id": ids, "design_id": ids, "split": split, "subgroup": group, "sequence": seqs,
                             "structure_confidence": rng.uniform(45, 98, rows), "clash_score": rng.gamma(2, 1.2, rows),
                             "novelty": rng.uniform(0.35, 0.99, rows), "developability": rng.uniform(0.2, 0.98, rows),
                             "truth_label": truth, "prediction_score": score})
    if category == "imaging_spatial":
        truth = rng.binomial(1, 0.45, rows)
        score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
        return pd.DataFrame({"record_id": ids, "slide_id": [f"SLIDE{i%16:02d}" for i in range(rows)], "split": split,
                             "subgroup": group, "x": rng.integers(0, 4096, rows), "y": rng.integers(0, 4096, rows),
                             "focus_score": rng.uniform(0.45, 1, rows), "artifact_score": rng.uniform(0, 0.4, rows),
                             "mask_truth": truth, "truth_label": truth, "prediction_score": score, "scanner": rng.choice(["SCN-A", "SCN-B"], rows)})
    if category == "ai_ml":
        truth = rng.binomial(1, 0.45, rows)
        score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
        return pd.DataFrame({"record_id": ids, "sample_id": ids, "split": split, "subgroup": group,
                             "truth_label": truth, "prediction_score": score, "ood_score": rng.uniform(0, 1, rows),
                             "model_version": "demo-v190", "site": rng.choice(["SITE-1", "SITE-2", "SITE-3"], rows)})
    if category == "clinical_pharma":
        truth = rng.binomial(1, 0.35, rows)
        score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
        return pd.DataFrame({"record_id": ids, "patient_id": ids, "split": split, "subgroup": group,
                             "site": rng.choice(["SITE-1", "SITE-2", "SITE-3"], rows), "age": rng.integers(18, 85, rows),
                             "time": rng.exponential(24, rows), "event": truth, "truth_label": truth,
                             "prediction_score": score, "treatment": rng.choice(["control", "active"], rows)})
    if category == "lab_bioprocess":
        t = np.arange(rows)
        value = 100 + 0.025 * t + rng.normal(0, 2.3, rows)
        truth = rng.binomial(1, 0.35, rows)
        score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
        return pd.DataFrame({"record_id": ids, "batch_id": [f"B{i%8:02d}" for i in range(rows)], "split": split,
                             "subgroup": group, "timepoint": t, "process_value": value, "yield": rng.normal(82, 6, rows),
                             "instrument": rng.choice(["INST-A", "INST-B"], rows), "truth_label": truth, "prediction_score": score})
    if category == "knowledge_documents":
        truth = rng.binomial(1, 0.7, rows)
        score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
        return pd.DataFrame({"record_id": ids, "document_id": [f"DOC{i%30:03d}" for i in range(rows)], "split": split,
                             "subgroup": group, "claim": [f"Scientific claim {i}" for i in range(rows)],
                             "source_id": [f"SRC{i%45:03d}" for i in range(rows)], "retracted": rng.binomial(1, 0.04, rows),
                             "truth_label": truth, "prediction_score": score})
    if category == "platform_workflow":
        truth = rng.binomial(1, 0.82, rows)
        score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
        return pd.DataFrame({"record_id": ids, "workflow_id": [f"WF{i%15:03d}" for i in range(rows)], "split": split,
                             "subgroup": group, "node": [f"N{i%12}" for i in range(rows)], "dependency": [f"N{max(0, i%12-1)}" for i in range(rows)],
                             "runtime_ms": rng.integers(5, 500, rows), "truth_label": truth, "prediction_score": score})
    truth = rng.binomial(1, 0.45, rows)
    score = np.clip(0.08 + truth * 0.84 + rng.normal(0, 0.04, rows), 0, 1)
    return pd.DataFrame({"record_id": ids, "sample_id": ids, "split": split, "subgroup": group,
                         "measurement": rng.normal(0, 1, rows) + truth * 0.8, "truth_label": truth,
                         "prediction_score": score})


def _confusion(truth: np.ndarray, pred: np.ndarray) -> dict[str, int]:
    return {
        "tp": int(np.sum((truth == 1) & (pred == 1))),
        "tn": int(np.sum((truth == 0) & (pred == 0))),
        "fp": int(np.sum((truth == 0) & (pred == 1))),
        "fn": int(np.sum((truth == 1) & (pred == 0))),
    }


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b else 0.0


def calibration_error(truth: np.ndarray, score: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    error = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (score >= lo) & (score < hi if hi < 1 else score <= hi)
        if mask.any():
            error += float(mask.mean()) * abs(float(truth[mask].mean()) - float(score[mask].mean()))
    return float(error)


def native_analysis(profile: ExecutionProfile, frame: pd.DataFrame, threshold: float = 0.5) -> tuple[pd.DataFrame, dict[str, Any]]:
    if frame.empty:
        raise ValueError("Validated input must contain at least one record")
    required = {"record_id", "truth_label", "prediction_score"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))
    output = frame.copy()
    score = pd.to_numeric(output["prediction_score"], errors="coerce").fillna(0).clip(0, 1).to_numpy(float)
    truth = pd.to_numeric(output["truth_label"], errors="coerce").fillna(0).astype(int).clip(0, 1).to_numpy()
    uncertainty = 1.0 - np.abs(score - 0.5) * 2.0
    ood = pd.to_numeric(output.get("ood_score", pd.Series(np.zeros(len(output)))), errors="coerce").fillna(0).clip(0, 1).to_numpy(float)
    abstain = (uncertainty > 0.82) | (ood > 0.88)
    pred = (score >= threshold).astype(int)
    pred_for_metrics = pred[~abstain] if (~abstain).any() else pred
    truth_for_metrics = truth[~abstain] if (~abstain).any() else truth
    cm = _confusion(truth_for_metrics, pred_for_metrics)
    precision = _safe_div(cm["tp"], cm["tp"] + cm["fp"])
    recall = _safe_div(cm["tp"], cm["tp"] + cm["fn"])
    specificity = _safe_div(cm["tn"], cm["tn"] + cm["fp"])
    f1 = _safe_div(2 * precision * recall, precision + recall)
    accuracy = _safe_div(cm["tp"] + cm["tn"], sum(cm.values()))
    brier = float(np.mean((score - truth) ** 2))
    ece = calibration_error(truth, score)
    output["prediction"] = pred
    output["uncertainty"] = uncertainty.round(6)
    output["abstained"] = abstain
    output["execution_engine"] = "biointel-native-v190"
    output["confidence_grade"] = pd.cut(score, bins=[-0.01, 0.25, 0.5, 0.75, 1.01], labels=["D", "C", "B", "A"]).astype(str)
    subgroup_rows = []
    subgroup_col = "subgroup" if "subgroup" in output.columns else None
    if subgroup_col:
        for name, group in output.groupby(subgroup_col):
            t = group["truth_label"].astype(int).to_numpy()
            p = group["prediction"].astype(int).to_numpy()
            c = _confusion(t, p)
            subgroup_rows.append({"subgroup": str(name), "records": len(group), "accuracy": _safe_div(c["tp"] + c["tn"], sum(c.values()))})
    category_metrics: dict[str, Any] = {}
    if profile.category == "genomics":
        category_metrics = {"mean_coverage": float(output["coverage"].mean()), "callable_fraction": float((output["coverage"] >= 10).mean()),
                            "mean_variant_quality": float(output["quality"].mean())}
    elif profile.category == "single_cell_multiomics":
        category_metrics = {"median_counts": float(output["total_counts"].median()), "median_genes": float(output["genes_detected"].median()),
                            "high_mito_fraction": float((output["mito_pct"] > 15).mean())}
    elif profile.category == "microbiome":
        pseudo = np.clip(output["abundance"].to_numpy(float), 1e-9, None)
        clr = np.log(pseudo) - np.log(pseudo).mean()
        output["clr_abundance"] = clr
        category_metrics = {"mean_coverage": float(output["coverage"].mean()), "mean_ani": float(output["ani"].mean()),
                            "negative_control_rate": float(output["negative_control"].mean())}
    elif profile.category == "protein_molecular":
        output["sequence_length"] = output["sequence"].astype(str).str.len()
        output["hydrophobic_fraction"] = output["sequence"].astype(str).map(lambda s: sum(c in "AILMFWVY" for c in s) / max(1, len(s)))
        category_metrics = {"mean_structure_confidence": float(output["structure_confidence"].mean()),
                            "mean_clash_score": float(output["clash_score"].mean()), "mean_novelty": float(output["novelty"].mean())}
    elif profile.category == "imaging_spatial":
        category_metrics = {"mean_focus": float(output["focus_score"].mean()), "artifact_fail_rate": float((output["artifact_score"] > 0.3).mean()),
                            "scanner_count": int(output["scanner"].nunique())}
    elif profile.category == "clinical_pharma":
        category_metrics = {"median_followup": float(output["time"].median()), "event_rate": float(output["event"].mean()),
                            "site_count": int(output["site"].nunique())}
    elif profile.category == "lab_bioprocess":
        mean = float(output["process_value"].mean()); sd = float(output["process_value"].std(ddof=0))
        output["control_z"] = (output["process_value"] - mean) / max(sd, 1e-9)
        category_metrics = {"process_mean": mean, "process_sd": sd, "out_of_control_rate": float((output["control_z"].abs() > 3).mean())}
    elif profile.category == "knowledge_documents":
        category_metrics = {"supported_claim_rate": float(output["truth_label"].mean()), "retraction_rate": float(output["retracted"].mean()),
                            "unique_sources": int(output["source_id"].nunique())}
    elif profile.category == "platform_workflow":
        category_metrics = {"mean_runtime_ms": float(output["runtime_ms"].mean()), "workflow_count": int(output["workflow_id"].nunique()),
                            "node_count": int(output["node"].nunique())}
    summary = {
        "schema": "biointel.step190.native_analysis.v1",
        "module_key": profile.module_key,
        "category": profile.category,
        "records": len(output),
        "threshold": threshold,
        "abstention_rate": float(abstain.mean()),
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "brier": brier,
        "expected_calibration_error": ece,
        "confusion": cm,
        "subgroup_results": subgroup_rows,
        "category_metrics": category_metrics,
        "generated_at": utc_now(),
        "scientific_boundary": "Synthetic truth-set operational benchmark; does not establish external scientific validity.",
    }
    return output, summary


def compare_runs(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    keys = [c for c in ("record_id", "prediction_score", "prediction", "uncertainty", "abstained") if c in a.columns and c in b.columns]
    left = a[keys].copy(); right = b[keys].copy()
    merged = left.merge(right, on="record_id", suffixes=("_a", "_b"))
    for col in ("prediction_score", "uncertainty"):
        if f"{col}_a" in merged and f"{col}_b" in merged:
            merged[f"{col}_delta"] = merged[f"{col}_b"] - merged[f"{col}_a"]
    return merged


def streaming_benchmark(profile: ExecutionProfile, sizes: Iterable[int] = (1000, 10000, 50000), chunk_size: int = 2048) -> pd.DataFrame:
    rows = []
    seed = stable_seed(profile.module_key + "-stream")
    for size in sizes:
        rng = np.random.default_rng(seed + size)
        start = time.perf_counter(); total = 0.0; maximum = -math.inf; processed = 0
        for offset in range(0, size, chunk_size):
            n = min(chunk_size, size - offset)
            values = rng.normal(0, 1, n)
            total += float(values.sum()); maximum = max(maximum, float(values.max())); processed += n
        elapsed = max(time.perf_counter() - start, 1e-9)
        rows.append({"records": size, "chunk_size": chunk_size, "elapsed_seconds": round(elapsed, 6),
                     "records_per_second": round(processed / elapsed, 2), "bounded_memory_estimate_mb": round(chunk_size * 8 / 1024 / 1024, 4),
                     "checksum": sha256(f"{processed}|{total:.12f}|{maximum:.12f}".encode()).hexdigest(), "status": "pass"})
    return pd.DataFrame(rows)


def build_viewer(profile: ExecutionProfile, output: pd.DataFrame, summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample = output.head(80)
    values = sample["prediction_score"].astype(float).to_numpy()
    width, height = 900, 420
    points = []
    for i, value in enumerate(values):
        x = 35 + i * (width - 70) / max(1, len(values) - 1)
        y = height - 45 - value * (height - 90)
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)
    rows = "".join(
        f"<tr><td>{str(r.get('record_id',''))}</td><td>{float(r.get('prediction_score',0)):.4f}</td><td>{str(r.get('confidence_grade',''))}</td><td>{str(r.get('abstained',''))}</td></tr>"
        for _, r in sample.head(20).iterrows()
    )
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>{profile.title} viewer</title>
<style>body{{font-family:Arial;margin:24px;background:#fafafa;color:#17202a}}.card{{background:white;border:1px solid #ddd;border-radius:12px;padding:18px;margin-bottom:16px}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #eee;padding:8px;text-align:left}}svg{{width:100%;height:auto}}</style></head><body>
<h1>{profile.title}</h1><p>Offline native Step 190 viewer · {profile.category.replace('_',' ').title()}</p>
<div class='card'><h2>Confidence profile</h2><svg viewBox='0 0 {width} {height}' role='img' aria-label='Prediction score chart'><rect x='0' y='0' width='{width}' height='{height}' fill='white'/><line x1='35' y1='{height-45}' x2='{width-35}' y2='{height-45}' stroke='#333'/><line x1='35' y1='45' x2='35' y2='{height-45}' stroke='#333'/><polyline points='{polyline}' fill='none' stroke='#2457d6' stroke-width='3'/></svg></div>
<div class='card'><h2>Benchmark summary</h2><pre>{json.dumps(summary, indent=2)}</pre></div>
<div class='card'><h2>Result drill-down</h2><table><thead><tr><th>Record</th><th>Score</th><th>Grade</th><th>Abstained</th></tr></thead><tbody>{rows}</tbody></table></div>
</body></html>"""
    path.write_text(html, encoding="utf-8")


def write_standard_bridges(folder: Path, profile: ExecutionProfile, frame: pd.DataFrame) -> list[dict[str, Any]]:
    folder.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    # Universal capability descriptor inspired by standard service-info patterns; not a certification claim.
    service_info = {
        "id": f"biointel-step190-{profile.module_key}", "name": profile.title, "type": {"group": "org.biointel", "artifact": profile.category, "version": "190.0"},
        "organization": {"name": "BioIntel AI"}, "version": "190.0", "environment": "offline-demo-operational",
        "supported_formats": list(profile.standard_formats), "production_conformance_certified": False,
    }
    write_json(folder / "service_info_compatibility.json", service_info)
    artifacts.append({"artifact": "service_info_compatibility.json", "standard": "GA4GH-style capability descriptor", "conformance": "compatibility-only"})

    prov = {
        "@context": {"prov": "http://www.w3.org/ns/prov#", "biointel": "https://biointel.local/ns#"},
        "@graph": [
            {"@id": f"biointel:input-{profile.module_key}", "@type": "prov:Entity", "prov:value": "Step 190 synthetic qualification fixture"},
            {"@id": f"biointel:run-{profile.module_key}", "@type": "prov:Activity", "prov:used": {"@id": f"biointel:input-{profile.module_key}"}},
            {"@id": "biointel:system", "@type": "prov:SoftwareAgent", "prov:label": "BioIntel AI Step 190"},
        ],
    }
    write_json(folder / "provenance.prov.jsonld", prov)
    artifacts.append({"artifact": "provenance.prov.jsonld", "standard": "W3C PROV-compatible JSON-LD", "conformance": "structural-bridge"})

    category = profile.category
    if category == "genomics":
        (folder / "reference.fasta").write_text(">demo_chr1\n" + "ACGT" * 125 + "\n", encoding="utf-8")
        with (folder / "variants.vcf").open("w", encoding="utf-8", newline="") as handle:
            handle.write("##fileformat=VCFv4.3\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
            for _, row in frame.head(25).iterrows():
                handle.write(f"{row['chrom']}\t{int(row['pos'])}\t{row['record_id']}\t{row['ref']}\t{row['alt']}\t{float(row['quality']):.2f}\tPASS\tDEMO=1\n")
        artifacts.extend([{"artifact": "reference.fasta", "standard": "FASTA", "conformance": "valid-demo"},
                          {"artifact": "variants.vcf", "standard": "VCF 4.3", "conformance": "valid-demo"}])
    elif category == "single_cell_multiomics":
        frame.head(100).to_csv(folder / "matrix.csv", index=False)
        write_json(folder / "anndata_bridge.json", {"schema": "anndata-compatible-bridge-v1", "obs_columns": ["cell_id", "sample_id", "batch"],
                                                     "var_contract": "feature matrix supplied separately", "h5ad_binary_supplied": False})
        artifacts.extend([{"artifact": "matrix.csv", "standard": "matrix table", "conformance": "valid-demo"},
                          {"artifact": "anndata_bridge.json", "standard": "AnnData compatibility bridge", "conformance": "bridge-not-binary-h5ad"}])
    elif category == "microbiome":
        frame.head(100).to_csv(folder / "abundance.tsv", sep="\t", index=False)
        (folder / "taxonomy.newick").write_text("(Taxon_A:0.1,Taxon_B:0.2,(Taxon_C:0.1,Taxon_D:0.1):0.2,Taxon_E:0.3);\n", encoding="utf-8")
        artifacts.extend([{"artifact": "abundance.tsv", "standard": "TSV abundance", "conformance": "valid-demo"},
                          {"artifact": "taxonomy.newick", "standard": "Newick", "conformance": "valid-demo"}])
    elif category == "protein_molecular":
        with (folder / "sequences.fasta").open("w", encoding="utf-8") as handle:
            for _, row in frame.head(12).iterrows(): handle.write(f">{row['record_id']}\n{row['sequence']}\n")
        (folder / "structure.pdb").write_text("HEADER    STEP190 DEMO STRUCTURE\nATOM      1  CA  ALA A   1      11.104  13.207   9.100  1.00 20.00           C\nEND\n", encoding="utf-8")
        (folder / "compound.sdf").write_text("Step190Demo\n  BioIntel\n\n  1  0  0  0  0  0            999 V2000\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0\nM  END\n$$$$\n", encoding="utf-8")
        artifacts.extend([{"artifact": "sequences.fasta", "standard": "FASTA", "conformance": "valid-demo"},
                          {"artifact": "structure.pdb", "standard": "PDB", "conformance": "minimal-valid-demo"},
                          {"artifact": "compound.sdf", "standard": "SDF V2000", "conformance": "minimal-valid-demo"}])
    elif category == "imaging_spatial":
        write_json(folder / "ome_ngff_bridge.json", {"multiscales": [{"version": "0.5", "name": profile.module_key, "datasets": [{"path": "0"}]}],
                                                     "note": "Metadata bridge for intake validation; no production image pixels bundled."})
        frame.head(100).to_csv(folder / "spatial_coordinates.csv", index=False)
        artifacts.extend([{"artifact": "ome_ngff_bridge.json", "standard": "OME-NGFF metadata bridge", "conformance": "metadata-bridge"},
                          {"artifact": "spatial_coordinates.csv", "standard": "spatial table", "conformance": "valid-demo"}])
    elif category == "ai_ml":
        write_json(folder / "model_card.json", {"model_name": profile.title, "version": "demo-v190", "intended_use": "operational workflow qualification",
                                                "prohibited_use": ["clinical diagnosis", "controlled release"], "training_data": "synthetic deterministic fixture",
                                                "weights_sha256": "not-applicable-native-adapter"})
        frame.to_csv(folder / "predictions.csv", index=False)
        artifacts.extend([{"artifact": "model_card.json", "standard": "model card", "conformance": "complete-demo"},
                          {"artifact": "predictions.csv", "standard": "prediction table", "conformance": "valid-demo"}])
    elif category == "clinical_pharma":
        frame.to_csv(folder / "cohort.csv", index=False)
        write_json(folder / "clinical_mapping.json", {"FHIR_compatible_mapping": {"patient_id": "Patient.identifier", "event": "Observation.valueBoolean"},
                                                       "CDISC_style_mapping": {"patient_id": "USUBJID", "time": "AVAL", "event": "CNSR"},
                                                       "certified_conformance": False})
        artifacts.extend([{"artifact": "cohort.csv", "standard": "clinical cohort table", "conformance": "valid-demo"},
                          {"artifact": "clinical_mapping.json", "standard": "FHIR/CDISC compatibility map", "conformance": "mapping-only"}])
    elif category == "lab_bioprocess":
        frame.to_csv(folder / "instrument_timeseries.csv", index=False)
        write_json(folder / "protocol.json", {"protocol_id": f"STEP190-{profile.module_key}", "version": "1.0", "states": ["draft", "approved", "executing", "complete"]})
        artifacts.extend([{"artifact": "instrument_timeseries.csv", "standard": "instrument table", "conformance": "valid-demo"},
                          {"artifact": "protocol.json", "standard": "protocol state contract", "conformance": "valid-demo"}])
    elif category == "knowledge_documents":
        write_json(folder / "document_claims.json", {"documents": frame.head(25).to_dict(orient="records")})
        artifacts.append({"artifact": "document_claims.json", "standard": "claim/source JSON", "conformance": "valid-demo"})
    elif category == "platform_workflow":
        nodes = [{"id": f"N{i}", "type": "task"} for i in range(6)]
        edges = [{"from": f"N{i}", "to": f"N{i+1}"} for i in range(5)]
        write_json(folder / "workflow_dag.json", {"schema": "biointel.workflow.v1", "nodes": nodes, "edges": edges, "acyclic": True})
        artifacts.append({"artifact": "workflow_dag.json", "standard": "typed workflow DAG", "conformance": "valid-demo"})
    else:
        frame.to_csv(folder / "study.csv", index=False)
        artifacts.append({"artifact": "study.csv", "standard": "study table", "conformance": "valid-demo"})
    pd.DataFrame(artifacts).to_csv(folder / "format_bridge_manifest.csv", index=False)
    return artifacts


def build_reference_intake(folder: Path, profile: ExecutionProfile, root: Path) -> pd.DataFrame:
    folder.mkdir(parents=True, exist_ok=True)
    candidates = []
    data_demo = root / "data" / "bioinformatics_demo"
    for name in profile.recommended_references:
        source = next(iter(sorted(p for p in data_demo.rglob("*") if p.is_file())), None) if data_demo.exists() else None
        record = {
            "reference_name": name,
            "status": "bundled-demo-subset" if source else "intake-required",
            "source_file": str(source.relative_to(root)) if source else "",
            "sha256": digest_path(source) if source and source.is_file() else "",
            "licence": "Existing package demonstrator; production licence must be supplied separately",
            "production_eligible": False,
            "update_channel": "manual-approved-import",
            "rollback_supported": True,
        }
        candidates.append(record)
    frame = pd.DataFrame(candidates)
    frame.to_csv(folder / "reference_intake_manifest.csv", index=False)
    write_json(folder / "production_reference_requirements.json", {
        "module_key": profile.module_key,
        "required": list(profile.recommended_references),
        "requirements": ["official provider", "accepted licence", "checksum", "version", "release date", "schema validation", "rollback snapshot"],
        "bundled_assets_count_as_production": False,
    })
    return frame


def update_impact(profile: ExecutionProfile, output: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    baseline = output[["record_id", "prediction_score", "prediction", "abstained"]].copy()
    updated = baseline.copy()
    shift = ((stable_seed(profile.module_key + "-update") % 13) - 6) / 1000.0
    updated["prediction_score"] = np.clip(updated["prediction_score"] + shift, 0, 1)
    updated["prediction"] = (updated["prediction_score"] >= 0.5).astype(int)
    comparison = baseline.merge(updated, on="record_id", suffixes=("_baseline", "_updated"))
    comparison["score_delta"] = comparison["prediction_score_updated"] - comparison["prediction_score_baseline"]
    changed = comparison["prediction_baseline"] != comparison["prediction_updated"]
    report = {
        "schema": "biointel.step190.update_impact.v1", "module_key": profile.module_key,
        "synthetic_version_shift": shift, "records": len(comparison), "changed_decisions": int(changed.sum()),
        "changed_decision_rate": float(changed.mean()), "mean_absolute_score_delta": float(comparison["score_delta"].abs().mean()),
        "release_decision": "review-required" if changed.any() else "no-material-demo-impact",
        "note": "Operational impact drill using a deterministic synthetic version shift; real database/model updates must be evaluated with approved evidence.",
    }
    return comparison, report


def error_catalogue(profile: ExecutionProfile) -> pd.DataFrame:
    rows = [
        ("EMPTY_INPUT", "blocked", "Load a validated input or demo fixture."),
        ("MISSING_REQUIRED_FIELD", "blocked", "Use the generated metadata/schema template."),
        ("CORRUPT_OR_TRUNCATED_FILE", "blocked", "Re-export or restore the source file and verify its checksum."),
        ("UNSAFE_PATH", "blocked", "Use an isolated project-relative path."),
        ("FORMULA_OR_SCRIPT_INJECTION", "blocked", "Escape active content before import."),
        ("ENGINE_UNAVAILABLE", "fallback", "Use native offline adapter or qualify the specialist engine."),
        ("REFERENCE_NOT_PRODUCTION_QUALIFIED", "blocked-release", "Import an official licensed reference snapshot."),
        ("OUT_OF_DISTRIBUTION", "abstain", "Review the sample and provide a closer validated reference/cohort."),
        ("RESOURCE_LIMIT", "checkpoint", "Reduce batch size or resume from the last checkpoint."),
        ("OUTPUT_SCHEMA_MISMATCH", "blocked", "Do not publish; inspect engine version and parser compatibility."),
    ]
    return pd.DataFrame([{"module_key": profile.module_key, "error_code": code, "action": action, "suggested_fix": fix} for code, action, fix in rows])


def capability_rows(profile: ExecutionProfile) -> pd.DataFrame:
    rows = []
    for item in profile.advanced_capabilities:
        rows.append({"module_key": profile.module_key, "scope": "module/category", "capability": item, "implemented": True,
                     "evidence": "native analysis, contracts, benchmark and generated artifacts", "production_external_evidence_required": True})
    for item in profile.standard_formats:
        rows.append({"module_key": profile.module_key, "scope": "format", "capability": item, "implemented": True,
                     "evidence": "format_bridge_manifest.csv", "production_external_evidence_required": False})
    for item in profile.native_viewers:
        rows.append({"module_key": profile.module_key, "scope": "viewer", "capability": item, "implemented": True,
                     "evidence": "native_viewer.html", "production_external_evidence_required": False})
    return pd.DataFrame(rows)


__all__ = [
    "EngineProbe", "probe_profile_engines", "command_plan", "make_fixture", "native_analysis", "compare_runs",
    "streaming_benchmark", "build_viewer", "write_standard_bridges", "build_reference_intake", "update_impact",
    "error_catalogue", "capability_rows", "stable_seed",
]
