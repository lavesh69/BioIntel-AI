from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from biointel.innovation.advanced_engines import (
    advanced_protein_design,
    biomarker_model_advanced,
    contig_qc_advanced,
    long_read_qc_metrics,
    parse_fastq_advanced,
)
from biointel.innovation.engines import demo_fastq, demo_multiomics, demo_protein_sequence

from .provenance import atomic_write_json, atomic_write_text, artifact_record

TaskFunction = Callable[[dict[str, Any]], dict[str, Any]]


def _step_dir(context: dict[str, Any]) -> Path:
    path = Path(context["step_directory"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def _find_upstream_file(context: dict[str, Any], suffixes: tuple[str, ...]) -> Path | None:
    for artifact in reversed(context.get("upstream_artifacts", [])):
        path = Path(str(artifact.get("path", "")))
        if path.is_file() and path.suffix.lower() in suffixes:
            return path
    return None


def upload_fastq(context: dict[str, Any]) -> dict[str, Any]:
    step_dir = _step_dir(context)
    parameters = context.get("parameters", {})
    source = str(parameters.get("fastq_path", "")).strip()
    destination = step_dir / "reads.fastq"
    if source and Path(source).expanduser().is_file():
        shutil.copy2(Path(source).expanduser(), destination)
        source_kind = "user_supplied"
    else:
        destination.write_text(demo_fastq(int(parameters.get("demo_reads", 300)), int(parameters.get("seed", 95))), encoding="utf-8")
        source_kind = "deterministic_demo"
    artifact = artifact_record(destination, step_id=context["step_id"], role="reads", media_type="text/plain", metadata={"source_kind": source_kind})
    return {"status": "completed", "metrics": {"source_kind": source_kind, "bytes": destination.stat().st_size}, "artifacts": [artifact]}


def read_qc(context: dict[str, Any]) -> dict[str, Any]:
    step_dir = _step_dir(context)
    source = _find_upstream_file(context, (".fastq", ".fq", ".gz"))
    if source is None:
        raise ValueError("Read QC requires an upstream FASTQ artifact.")
    reads = parse_fastq_advanced(source.read_bytes(), source.name, int(context.get("parameters", {}).get("max_reads", 100000)))
    metrics = long_read_qc_metrics(reads, context.get("parameters", {}).get("genome_size_mb"))
    table_path = step_dir / "read_qc.csv"
    summary_path = step_dir / "read_qc_summary.json"
    reads.to_csv(table_path, index=False)
    atomic_write_json(summary_path, metrics)
    return {
        "status": "completed",
        "metrics": metrics,
        "artifacts": [
            artifact_record(table_path, step_id=context["step_id"], role="qc_table", media_type="text/csv"),
            artifact_record(summary_path, step_id=context["step_id"], role="qc_summary", media_type="application/json"),
        ],
    }


def trim_adapters(context: dict[str, Any]) -> dict[str, Any]:
    step_dir = _step_dir(context)
    source = _find_upstream_file(context, (".fastq", ".fq"))
    if source is None:
        # QC table alone cannot reconstruct sequences. Reuse the original reads artifact from any ancestor.
        for artifact in context.get("all_artifacts", []):
            path = Path(str(artifact.get("path", "")))
            if path.is_file() and path.suffix.lower() in {".fastq", ".fq"}:
                source = path
                break
    if source is None:
        raise ValueError("Adapter trimming requires an input FASTQ artifact.")
    destination = step_dir / "trimmed.fastq"
    adapter = str(context.get("parameters", {}).get("adapter_sequence", "AGATCGGAAGAGC")).upper()
    minimum_length = int(context.get("parameters", {}).get("minimum_length", 50))
    kept = 0
    removed = 0
    output: list[str] = []
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    for offset in range(0, len(lines) - 3, 4):
        header, sequence, plus, quality = lines[offset: offset + 4]
        hit = sequence.upper().find(adapter)
        if hit >= 0:
            sequence = sequence[:hit]
            quality = quality[:hit]
        if len(sequence) < minimum_length:
            removed += 1
            continue
        output.extend((header, sequence, plus, quality))
        kept += 1
    destination.write_text("\n".join(output) + ("\n" if output else ""), encoding="utf-8")
    return {
        "status": "completed",
        "metrics": {"kept_reads": kept, "removed_reads": removed, "adapter": adapter, "minimum_length": minimum_length},
        "artifacts": [artifact_record(destination, step_id=context["step_id"], role="clean_reads", media_type="text/plain")],
    }


def long_read_assembly(context: dict[str, Any]) -> dict[str, Any]:
    step_dir = _step_dir(context)
    parameters = context.get("parameters", {})
    fasta_path = str(parameters.get("assembly_fasta_path", "")).strip()
    if fasta_path and Path(fasta_path).expanduser().is_file():
        source = Path(fasta_path).expanduser()
        destination = step_dir / "assembly.fasta"
        shutil.copy2(source, destination)
        source_kind = "user_supplied_assembly"
    else:
        # Built-in deterministic fallback gives the workflow a real, inspectable artifact while making the boundary explicit.
        destination = step_dir / "assembly.fasta"
        sequence = ("ACGT" * 5000) + ("TTAGGG" * 12)
        destination.write_text(f">builtin_reference_contig\n{sequence}\n", encoding="utf-8")
        source_kind = "builtin_reference_fallback"
    contigs, summary = contig_qc_advanced(destination.read_text(encoding="utf-8"))
    table_path = step_dir / "assembly_qc.csv"
    summary_path = step_dir / "assembly_summary.json"
    contigs.to_csv(table_path, index=False)
    summary["source_kind"] = source_kind
    summary["external_assembler_executed"] = False
    atomic_write_json(summary_path, summary)
    return {
        "status": "completed",
        "metrics": summary,
        "artifacts": [
            artifact_record(destination, step_id=context["step_id"], role="assembly", media_type="text/x-fasta", metadata={"source_kind": source_kind}),
            artifact_record(table_path, step_id=context["step_id"], role="assembly_qc", media_type="text/csv"),
            artifact_record(summary_path, step_id=context["step_id"], role="assembly_summary", media_type="application/json"),
        ],
        "warnings": ["No external assembler was executed; the built-in fallback is for workflow qualification only."] if source_kind == "builtin_reference_fallback" else [],
    }


def generic_external_boundary(context: dict[str, Any]) -> dict[str, Any]:
    step_dir = _step_dir(context)
    block = str(context["block"])
    payload = {
        "block": block,
        "status": "completed_with_boundary",
        "message": "A reproducible execution hand-off was created. Configure an approved external tool command to produce study-grade output.",
        "parameters": context.get("parameters", {}),
        "upstream_artifacts": context.get("upstream_artifacts", []),
    }
    path = step_dir / "external_tool_handoff.json"
    atomic_write_json(path, payload)
    return {
        "status": "completed",
        "metrics": {"handoff_created": True, "external_execution": False},
        "artifacts": [artifact_record(path, step_id=context["step_id"], role="execution_handoff", media_type="application/json")],
        "warnings": [f"{block} requires an installed validated specialist tool for study-grade execution."],
    }


def protein_design(context: dict[str, Any]) -> dict[str, Any]:
    step_dir = _step_dir(context)
    parameters = context.get("parameters", {})
    sequence = str(parameters.get("protein_sequence", "")).strip() or demo_protein_sequence()
    frame = advanced_protein_design(
        sequence,
        str(parameters.get("protein_objective", "Balanced developability")),
        parameters.get("protected_positions", []),
        parameters.get("design_positions", list(range(1, min(40, len(sequence)) + 1))),
        int(parameters.get("candidate_limit", 100)),
    )
    path = step_dir / "protein_design_candidates.csv"
    frame.to_csv(path, index=False)
    return {
        "status": "completed",
        "metrics": {"candidates": len(frame), "pareto_candidates": int(frame.get("pareto_optimal", pd.Series(dtype=bool)).sum())},
        "artifacts": [artifact_record(path, step_id=context["step_id"], role="designed_protein_candidates", media_type="text/csv", metadata={"engine": "transparent_physicochemical_blosum"})],
    }


def biomarker_model(context: dict[str, Any]) -> dict[str, Any]:
    step_dir = _step_dir(context)
    parameters = context.get("parameters", {})
    input_path = str(parameters.get("omics_table_path", "")).strip()
    if input_path and Path(input_path).expanduser().is_file():
        frame = pd.read_csv(Path(input_path).expanduser())
        source_kind = "user_supplied"
    else:
        frame = demo_multiomics(int(parameters.get("samples", 160)), int(parameters.get("seed", 95)))
        source_kind = "deterministic_demo"
    result = biomarker_model_advanced(
        frame,
        str(parameters.get("outcome_column", "outcome")),
        str(parameters.get("batch_column", "batch")) or None,
        str(parameters.get("model_name", "Logistic L1")),
        int(parameters.get("outer_folds", 3)),
        int(parameters.get("inner_folds", 3)),
        int(parameters.get("permutations", 20)),
        int(parameters.get("seed", 95)),
    )
    predictions_path = step_dir / "biomarker_predictions.csv"
    importance_path = step_dir / "biomarker_importance.csv"
    metrics_path = step_dir / "biomarker_metrics.json"
    result["predictions"].to_csv(predictions_path, index=False)
    result["importance"].to_csv(importance_path, index=False)
    metrics = dict(result["metrics"])
    metrics["source_kind"] = source_kind
    atomic_write_json(metrics_path, metrics)
    return {
        "status": "completed",
        "metrics": metrics,
        "artifacts": [
            artifact_record(predictions_path, step_id=context["step_id"], role="predictions", media_type="text/csv"),
            artifact_record(importance_path, step_id=context["step_id"], role="feature_importance", media_type="text/csv"),
            artifact_record(metrics_path, step_id=context["step_id"], role="model_metrics", media_type="application/json"),
        ],
    }


def quality_gate(context: dict[str, Any]) -> dict[str, Any]:
    step_dir = _step_dir(context)
    parameters = context.get("parameters", {})
    minimum_score = float(parameters.get("minimum_quality_score", 7.0))
    upstream = context.get("upstream_results", [])
    blockers: list[str] = []
    warnings: list[str] = []
    for result in upstream:
        if result.get("status") not in {"completed", "skipped"}:
            blockers.append(f"Upstream step {result.get('step_id', '?')} is not complete.")
        warnings.extend(result.get("warnings", []))
    score = 10.0
    score -= min(3.0, 0.5 * len(warnings))
    score -= min(8.0, 2.0 * len(blockers))
    approved = score >= minimum_score and not blockers
    payload = {"approved": approved, "quality_score": round(score, 2), "minimum_score": minimum_score, "blockers": blockers, "warnings": warnings}
    path = step_dir / "quality_gate.json"
    atomic_write_json(path, payload)
    if not approved and bool(parameters.get("fail_on_quality_gate", True)):
        raise RuntimeError("Quality gate failed: " + "; ".join(blockers or warnings or ["score below threshold"]))
    return {
        "status": "completed",
        "metrics": payload,
        "artifacts": [artifact_record(path, step_id=context["step_id"], role="quality_gate", media_type="application/json")],
        "warnings": warnings,
    }


def generate_report(context: dict[str, Any]) -> dict[str, Any]:
    step_dir = _step_dir(context)
    run_id = html.escape(str(context["run_id"]))
    rows = []
    for result in context.get("all_results", []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(result.get('step_id', '')))}</td>"
            f"<td>{html.escape(str(result.get('block', '')))}</td>"
            f"<td>{html.escape(str(result.get('status', '')))}</td>"
            f"<td>{html.escape(str(result.get('duration_seconds', '')))}</td>"
            "</tr>"
        )
    document = f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><title>BioIntel AI workflow report</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:1100px;margin:32px auto;padding:0 20px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #bbb;padding:8px;text-align:left}}th{{background:#eee}}code{{word-break:break-all}}</style></head>
<body><h1>BioIntel AI workflow report</h1><p><strong>Run:</strong> <code>{run_id}</code></p>
<p>This report documents execution and provenance. It does not replace independent biological, clinical or regulatory validation.</p>
<table><thead><tr><th>Step</th><th>Block</th><th>Status</th><th>Seconds</th></tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""
    path = step_dir / "workflow_report.html"
    atomic_write_text(path, document)
    return {
        "status": "completed",
        "metrics": {"reported_steps": len(rows)},
        "artifacts": [artifact_record(path, step_id=context["step_id"], role="report", media_type="text/html")],
    }


BUILTIN_TASKS: dict[str, TaskFunction] = {
    "Upload FASTQ": upload_fastq,
    "Read QC": read_qc,
    "Trim adapters": trim_adapters,
    "Long-read assembly": long_read_assembly,
    "Genome alignment": generic_external_boundary,
    "Variant calling": generic_external_boundary,
    "Variant annotation": generic_external_boundary,
    "Taxonomic classification": generic_external_boundary,
    "AMR screening": generic_external_boundary,
    "Protein design": protein_design,
    "Biomarker model": biomarker_model,
    "Quality gate": quality_gate,
    "Generate report": generate_report,
}


def task_for_block(block: str) -> TaskFunction:
    try:
        return BUILTIN_TASKS[block]
    except KeyError as exc:
        raise KeyError(f"No internal execution adapter is registered for workflow block: {block}") from exc
