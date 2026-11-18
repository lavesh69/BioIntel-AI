from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_report_path

import hashlib
import html
import importlib.metadata
import io
import json
import platform
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from biointel import __version__
from biointel.data.dataset_registry import get_dataset
from biointel.governance.governance_registry import (
    project_governance_snapshot,
)
from biointel.portfolio.project_registry import (
    get_project,
    list_project_events,
)
from biointel.training.experiment_registry import list_experiments
from biointel.training.model_artifact import load_model_artifact
from biointel.utils.audit_log import verify_audit_chain
from biointel.utils.diagnostics import (
    diagnostic_summary,
    run_diagnostics,
)

PROJECT_PACKAGE_VERSION = "1.0"
MAX_PACKAGE_BYTES = 500 * 1024 * 1024
MAX_PACKAGE_FILES = 100


@dataclass(frozen=True)
class EvidencePackageSummary:
    project_id: str
    project_code: str
    generated_at_utc: str
    readiness_score: int
    file_count: int
    total_bytes: int
    included_model_files: bool
    files: tuple[str, ...]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and len(path.parts) <= 4


def _package_versions() -> dict[str, str]:
    packages = {
        "python": platform.python_version(),
        "biointel_ai": __version__,
    }
    for package in (
        "streamlit",
        "fastapi",
        "pandas",
        "numpy",
        "scikit-learn",
        "rdkit",
        "biopython",
        "plotly",
        "joblib",
    ):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "not-installed"
    return packages


def _linked_model(
    root: Path,
    model_filename: str | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    issues: list[str] = []
    if not model_filename:
        return None, ["No model is linked to the project."]

    models = root / "models"
    model_path = models / Path(model_filename).name
    if not model_path.is_file():
        return None, [f"Linked model file is missing: {model_path.name}"]

    try:
        artifact = load_model_artifact(
            model_path,
            trusted_root=models,
        )
    except Exception as exc:
        return None, [f"Linked model could not be loaded: {exc}"]

    metadata = asdict(artifact.metadata)
    metadata["filename"] = model_path.name
    metadata["model_sha256"] = _file_sha256(model_path)
    sidecars = {}
    for suffix in (".json", ".model_card.md"):
        path = model_path.with_suffix(suffix)
        if path.is_file():
            sidecars[path.name] = _file_sha256(path)
    metadata["sidecar_sha256"] = sidecars
    return metadata, issues


def project_readiness(
    project_root: str | Path,
    project_id: str,
) -> dict[str, object]:
    root = Path(project_root).resolve()
    registry = runtime_database_path(root, "projects.sqlite3")
    project = get_project(registry, project_id)
    if project is None:
        raise ValueError("Project not found")

    governance = project_governance_snapshot(
        registry,
        project_id,
    )
    summary = governance["summary"]
    dataset = (
        get_dataset(
            runtime_database_path(root, "datasets.sqlite3"),
            project.dataset_sha256,
        )
        if project.dataset_sha256
        else None
    )
    model_metadata, model_issues = _linked_model(
        root,
        project.model_filename,
    )
    experiments = list_experiments(
        runtime_database_path(root, "experiments.sqlite3"),
        limit=5000,
    )
    matching_experiments = [
        item
        for item in experiments
        if (project.model_filename and item.get("model_file") == project.model_filename)
        or (project.dataset_sha256 and item.get("dataset_sha256") == project.dataset_sha256)
    ]
    audit = verify_audit_chain(runtime_report_path(root, "audit.jsonl"))
    diagnostics = diagnostic_summary(run_diagnostics(root, profile="quick"))

    criteria: list[dict[str, object]] = []

    def add(
        key: str,
        label: str,
        earned: int,
        maximum: int,
        message: str,
    ) -> None:
        criteria.append(
            {
                "key": key,
                "label": label,
                "earned": earned,
                "maximum": maximum,
                "complete": earned == maximum,
                "message": message,
            }
        )

    basics = 0
    basics += 4 if project.objective else 0
    basics += 3 if project.owner_label else 0
    basics += 3 if project.target_date else 0
    add(
        "project_definition",
        "Project definition",
        basics,
        10,
        "Objective, owner label and target date.",
    )

    add(
        "dataset_linkage",
        "Dataset linkage",
        15 if dataset else 0,
        15,
        (
            "Linked dataset exists in the registry."
            if dataset
            else "Link a valid registered dataset."
        ),
    )
    add(
        "model_linkage",
        "Model linkage",
        15 if model_metadata else 0,
        15,
        ("Linked model is present and compatible." if model_metadata else "; ".join(model_issues)),
    )

    milestones_total = int(summary["milestones_total"])
    milestones_completed = int(summary["milestones_completed"])
    add(
        "milestone_plan",
        "Milestone plan",
        10 if milestones_total else 0,
        10,
        (
            f"{milestones_total} milestone(s) recorded."
            if milestones_total
            else "Create at least one milestone."
        ),
    )
    completion_points = (
        round(milestones_completed / milestones_total * 10) if milestones_total else 0
    )
    add(
        "milestone_delivery",
        "Milestone delivery",
        int(completion_points),
        10,
        (
            f"{milestones_completed}/{milestones_total} milestone(s) completed."
            if milestones_total
            else "No milestone delivery evidence."
        ),
    )

    approved_decisions = int(summary["approved_decisions"])
    add(
        "decision_log",
        "Decision log",
        10 if approved_decisions else 0,
        10,
        (
            f"{approved_decisions} approved decision(s)."
            if approved_decisions
            else "Record at least one approved decision."
        ),
    )

    gates = governance["gates"]
    rejected = int(summary["gates_rejected"])
    approved_gate_names = {str(item["gate_name"]) for item in gates if item["status"] == "Approved"}
    gate_points = 0
    gate_points += 5 if gates else 0
    gate_points += 5 if rejected == 0 and gates else 0
    gate_points += 5 if "Release approval" in approved_gate_names else 0
    add(
        "approval_gates",
        "Approval gates",
        gate_points,
        15,
        (
            f"{summary['gates_approved']} approved, "
            f"{summary['gates_pending']} pending, "
            f"{rejected} rejected."
        ),
    )

    audit_points = 5 if audit["valid"] and audit["chained_events"] else 2 if audit["valid"] else 0
    add(
        "audit_integrity",
        "Audit integrity",
        audit_points,
        5,
        (
            "Hash chain verified."
            if audit["valid"] and audit["chained_events"]
            else (
                "Audit log is valid but contains no chained events."
                if audit["valid"]
                else "Audit chain verification failed."
            )
        ),
    )
    add(
        "diagnostics",
        "System diagnostics",
        5 if diagnostics["overall"] == "PASS" else 0,
        5,
        f"Diagnostics state: {diagnostics['overall']}.",
    )
    add(
        "experiment_evidence",
        "Experiment evidence",
        5 if matching_experiments else 0,
        5,
        (
            f"{len(matching_experiments)} matching experiment(s)."
            if matching_experiments
            else "No experiment matches the linked dataset/model."
        ),
    )

    score = sum(int(item["earned"]) for item in criteria)
    maximum = sum(int(item["maximum"]) for item in criteria)
    blockers = [
        str(item["message"])
        for item in criteria
        if int(item["earned"]) == 0 and int(item["maximum"]) >= 10
    ]
    label = (
        "Release ready"
        if score >= 90 and rejected == 0
        else (
            "Validation ready"
            if score >= 75
            else "Governance developing" if score >= 50 else "Evidence incomplete"
        )
    )

    return {
        "project_id": project_id,
        "project_code": project.project_code,
        "score": score,
        "maximum": maximum,
        "percent": round(score / maximum * 100, 1),
        "label": label,
        "criteria": criteria,
        "blockers": blockers,
        "linked_dataset_found": dataset is not None,
        "linked_model_found": model_metadata is not None,
        "matching_experiments": len(matching_experiments),
        "audit_integrity": audit,
        "diagnostics": diagnostics,
    }


def build_lineage_graph(
    project_root: str | Path,
    project_id: str,
) -> dict[str, object]:
    root = Path(project_root).resolve()
    registry = runtime_database_path(root, "projects.sqlite3")
    project = get_project(registry, project_id)
    if project is None:
        raise ValueError("Project not found")

    governance = project_governance_snapshot(
        registry,
        project_id,
    )
    nodes: list[dict[str, str]] = [
        {
            "id": project.project_id,
            "type": "project",
            "label": f"{project.project_code} · {project.name}",
        }
    ]
    edges: list[dict[str, str]] = []

    if project.dataset_sha256:
        nodes.append(
            {
                "id": project.dataset_sha256,
                "type": "dataset",
                "label": f"Dataset {project.dataset_sha256[:12]}…",
            }
        )
        edges.append(
            {
                "source": project.project_id,
                "target": project.dataset_sha256,
                "relationship": "uses dataset",
            }
        )

    if project.model_filename:
        model_id = "model:" + project.model_filename
        nodes.append(
            {
                "id": model_id,
                "type": "model",
                "label": project.model_filename,
            }
        )
        edges.append(
            {
                "source": project.project_id,
                "target": model_id,
                "relationship": "uses model",
            }
        )

    for milestone in governance["milestones"]:
        node_id = str(milestone["milestone_id"])
        nodes.append(
            {
                "id": node_id,
                "type": "milestone",
                "label": str(milestone["title"]),
            }
        )
        edges.append(
            {
                "source": project.project_id,
                "target": node_id,
                "relationship": "delivers",
            }
        )

    for decision in governance["decisions"]:
        node_id = str(decision["decision_id"])
        nodes.append(
            {
                "id": node_id,
                "type": "decision",
                "label": str(decision["title"]),
            }
        )
        edges.append(
            {
                "source": project.project_id,
                "target": node_id,
                "relationship": "governed by",
            }
        )

    for gate in governance["gates"]:
        node_id = str(gate["gate_id"])
        nodes.append(
            {
                "id": node_id,
                "type": "gate",
                "label": (f"{gate['gate_name']} · {gate['status']}"),
            }
        )
        edges.append(
            {
                "source": project.project_id,
                "target": node_id,
                "relationship": "requires gate",
            }
        )

    experiments = list_experiments(
        runtime_database_path(root, "experiments.sqlite3"),
        limit=5000,
    )
    for experiment in experiments:
        if (project.model_filename and experiment.get("model_file") == project.model_filename) or (
            project.dataset_sha256 and experiment.get("dataset_sha256") == project.dataset_sha256
        ):
            node_id = "experiment:" + str(experiment["experiment_id"])
            nodes.append(
                {
                    "id": node_id,
                    "type": "experiment",
                    "label": str(experiment["experiment_id"]),
                }
            )
            edges.append(
                {
                    "source": project.project_id,
                    "target": node_id,
                    "relationship": "supported by",
                }
            )

    return {
        "project_id": project_id,
        "nodes": nodes,
        "edges": edges,
    }


def build_project_manifest(
    project_root: str | Path,
    project_id: str,
) -> dict[str, object]:
    root = Path(project_root).resolve()
    registry = runtime_database_path(root, "projects.sqlite3")
    project = get_project(registry, project_id)
    if project is None:
        raise ValueError("Project not found")

    governance = project_governance_snapshot(
        registry,
        project_id,
    )
    dataset = (
        get_dataset(
            runtime_database_path(root, "datasets.sqlite3"),
            project.dataset_sha256,
        )
        if project.dataset_sha256
        else None
    )
    model_metadata, model_issues = _linked_model(
        root,
        project.model_filename,
    )
    experiments = list_experiments(
        runtime_database_path(root, "experiments.sqlite3"),
        limit=5000,
    )
    matching_experiments = [
        item
        for item in experiments
        if (project.model_filename and item.get("model_file") == project.model_filename)
        or (project.dataset_sha256 and item.get("dataset_sha256") == project.dataset_sha256)
    ]

    config_hash = None
    config_path = root / "config" / "settings.yaml"
    if config_path.is_file():
        config_hash = _file_sha256(config_path)

    return {
        "project_package_version": PROJECT_PACKAGE_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "project": asdict(project),
        "governance": governance,
        "linked_dataset": (asdict(dataset) if dataset else None),
        "linked_model": model_metadata,
        "model_issues": model_issues,
        "matching_experiments": matching_experiments,
        "project_events": [
            asdict(item)
            for item in list_project_events(
                registry,
                project_id=project_id,
                limit=1000,
            )
        ],
        "readiness": project_readiness(
            root,
            project_id,
        ),
        "lineage": build_lineage_graph(
            root,
            project_id,
        ),
        "audit_integrity": verify_audit_chain(runtime_report_path(root, "audit.jsonl")),
        "environment": {
            "platform": platform.platform(),
            "python_implementation": (platform.python_implementation()),
            "python_executable_name": Path(sys.executable).name,
            "software_versions": _package_versions(),
            "settings_sha256": config_hash,
        },
    }


def build_project_report_html(
    manifest: dict[str, object],
) -> str:
    project = manifest["project"]
    readiness = manifest["readiness"]
    governance = manifest["governance"]
    summary = governance["summary"]

    def esc(value: object) -> str:
        return html.escape(str(value or ""))

    criteria_rows = "".join(
        f"""
        <tr>
          <td>{esc(item["label"])}</td>
          <td>{esc(item["earned"])}/{esc(item["maximum"])}</td>
          <td>{esc(item["message"])}</td>
        </tr>
        """
        for item in readiness["criteria"]
    )
    milestone_rows = (
        "".join(
            f"""
        <tr>
          <td>{esc(item["title"])}</td>
          <td>{esc(item["status"])}</td>
          <td>{esc(item["due_date"])}</td>
          <td>{esc(item["owner_label"])}</td>
        </tr>
        """
            for item in governance["milestones"]
        )
        or "<tr><td colspan='4'>No milestones recorded.</td></tr>"
    )
    decision_rows = (
        "".join(
            f"""
        <tr>
          <td>{esc(item["title"])}</td>
          <td>{esc(item["status"])}</td>
          <td>{esc(item["decision_date"])}</td>
          <td>{esc(item["approver_label"])}</td>
        </tr>
        """
            for item in governance["decisions"]
        )
        or "<tr><td colspan='4'>No decisions recorded.</td></tr>"
    )
    gate_rows = (
        "".join(
            f"""
        <tr>
          <td>{esc(item["gate_name"])}</td>
          <td>{esc(item["status"])}</td>
          <td>{esc(item["reviewer_label"])}</td>
          <td>{esc(item["decision_date"])}</td>
        </tr>
        """
            for item in governance["gates"]
        )
        or "<tr><td colspan='4'>No approval gates recorded.</td></tr>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(project["project_code"])} Evidence Report</title>
<style>
:root {{
  --navy:#07101f; --surface:#101c31; --line:#29405f;
  --text:#f8fafc; --muted:#a9bad0; --blue:#2563eb;
  --cyan:#38bdf8; --green:#14b8a6;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; color:var(--text); font-family:Inter,Segoe UI,sans-serif;
  background:
    radial-gradient(circle at 10% 0%,rgba(37,99,235,.25),transparent 32%),
    radial-gradient(circle at 90% 8%,rgba(20,184,166,.16),transparent 30%),
    var(--navy);
}}
main {{ max-width:1120px; margin:auto; padding:48px 28px 72px; }}
.hero,section,.metric {{
  border:1px solid var(--line);
  background:linear-gradient(145deg,rgba(16,28,49,.96),rgba(8,16,30,.90));
  border-radius:20px;
}}
.hero {{ padding:40px; box-shadow:0 30px 90px rgba(2,6,23,.55); }}
.eyebrow {{ color:#93c5fd; font-size:12px; font-weight:850;
  letter-spacing:.12em; text-transform:uppercase; }}
h1 {{ margin:13px 0 8px; font-size:44px; line-height:1.05; letter-spacing:-.05em; }}
h2 {{ margin:0 0 16px; font-size:21px; }}
p {{ color:var(--muted); line-height:1.65; }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:20px 0; }}
.metric {{ padding:18px; }}
.metric span {{ display:block; color:var(--muted); font-size:12px; font-weight:750; }}
.metric strong {{ display:block; font-size:27px; margin-top:8px; }}
section {{ padding:22px; margin-top:16px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ padding:11px 12px; text-align:left; border-bottom:1px solid var(--line); }}
th {{ color:#cbd5e1; background:rgba(37,99,235,.12); }}
td {{ color:#dbe5f2; }}
.badge {{ display:inline-block; padding:7px 11px; border-radius:999px;
  color:#a7f3d0; background:rgba(20,184,166,.12);
  border:1px solid rgba(20,184,166,.32); font-size:12px; font-weight:800; }}
pre {{ white-space:pre-wrap; overflow:auto; color:#bfdbfe;
  background:#07101c; padding:15px; border-radius:12px; }}
footer {{ text-align:center; color:var(--muted); font-size:12px; margin-top:30px; }}
@media(max-width:760px) {{
  .grid {{ grid-template-columns:repeat(2,1fr); }}
  .hero {{ padding:25px; }} h1 {{ font-size:32px; }}
}}
@media print {{
  body {{ background:white; color:#111827; }}
  main {{ max-width:none; padding:0; }}
  .hero,section,.metric {{ color:#111827; background:white; box-shadow:none; }}
  p,td,footer {{ color:#374151; }}
}}
</style>
</head>
<body>
<main>
  <div class="hero">
    <div class="eyebrow">BioIntel AI · Controlled evidence package</div>
    <h1>{esc(project["project_code"])} · {esc(project["name"])}</h1>
    <p>{esc(project["objective"])}</p>
    <span class="badge">{esc(readiness["label"])}</span>
  </div>
  <div class="grid">
    <div class="metric"><span>Readiness</span><strong>{esc(readiness["percent"])}%</strong></div>
    <div class="metric"><span>Milestones</span><strong>{esc(summary["milestones_total"])}</strong></div>
    <div class="metric"><span>Decisions</span><strong>{esc(summary["decisions_total"])}</strong></div>
    <div class="metric"><span>Approved gates</span><strong>{esc(summary["gates_approved"])}</strong></div>
  </div>
  <section><h2>Release-readiness criteria</h2>
    <table><thead><tr><th>Control</th><th>Score</th><th>Evidence</th></tr></thead>
    <tbody>{criteria_rows}</tbody></table>
  </section>
  <section><h2>Milestones</h2>
    <table><thead><tr><th>Milestone</th><th>Status</th><th>Due</th><th>Owner</th></tr></thead>
    <tbody>{milestone_rows}</tbody></table>
  </section>
  <section><h2>Decision log</h2>
    <table><thead><tr><th>Decision</th><th>Status</th><th>Date</th><th>Approver</th></tr></thead>
    <tbody>{decision_rows}</tbody></table>
  </section>
  <section><h2>Approval gates</h2>
    <table><thead><tr><th>Gate</th><th>Status</th><th>Reviewer</th><th>Date</th></tr></thead>
    <tbody>{gate_rows}</tbody></table>
  </section>
  <section><h2>Reproducibility environment</h2>
    <pre>{esc(json.dumps(manifest["environment"], indent=2, default=str))}</pre>
  </section>
  <section><h2>Audit integrity</h2>
    <pre>{esc(json.dumps(manifest["audit_integrity"], indent=2, default=str))}</pre>
  </section>
  <footer>Generated locally by BioIntel AI. Scientific and release decisions require independent review.</footer>
</main>
</body>
</html>"""


def build_project_evidence_package(
    project_root: str | Path,
    project_id: str,
    include_model_files: bool = False,
) -> bytes:
    root = Path(project_root).resolve()
    manifest = build_project_manifest(
        root,
        project_id,
    )
    project = manifest["project"]
    governance = manifest["governance"]

    contents: dict[str, bytes] = {
        "PROJECT_REPORT.html": build_project_report_html(manifest).encode("utf-8"),
        "project/project.json": json.dumps(
            project,
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8"),
        "governance/milestones.json": json.dumps(
            governance["milestones"],
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8"),
        "governance/decisions.json": json.dumps(
            governance["decisions"],
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8"),
        "governance/gates.json": json.dumps(
            governance["gates"],
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8"),
        "lineage/graph.json": json.dumps(
            manifest["lineage"],
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8"),
        "reproducibility/environment.json": json.dumps(
            manifest["environment"],
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8"),
        "audit/integrity.json": json.dumps(
            manifest["audit_integrity"],
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8"),
    }

    if include_model_files and project.get("model_filename"):
        model_path = root / "models" / Path(str(project["model_filename"])).name
        if model_path.is_file():
            for path in (
                model_path,
                model_path.with_suffix(".json"),
                model_path.with_suffix(".model_card.md"),
            ):
                if path.is_file():
                    contents[f"model/{path.name}"] = path.read_bytes()

    if len(contents) > MAX_PACKAGE_FILES:
        raise ValueError("Evidence package contains too many files.")
    total = sum(len(content) for content in contents.values())
    if total > MAX_PACKAGE_BYTES:
        raise ValueError("Evidence package exceeds the 500 MB limit.")

    manifest["included_model_files"] = any(name.startswith("model/") for name in contents)
    manifest["file_sha256"] = {name: _sha256(content) for name, content in contents.items()}
    manifest_bytes = json.dumps(
        manifest,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")

    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "PROJECT_MANIFEST.json",
            manifest_bytes,
        )
        for name, content in contents.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def inspect_project_evidence_package(
    package_bytes: bytes,
) -> EvidencePackageSummary:
    if len(package_bytes) > MAX_PACKAGE_BYTES:
        raise ValueError("Evidence package exceeds the supported size limit.")
    with zipfile.ZipFile(
        io.BytesIO(package_bytes),
        "r",
    ) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_PACKAGE_FILES + 1:
            raise ValueError("Evidence package contains too many files.")
        names = archive.namelist()
        if "PROJECT_MANIFEST.json" not in names:
            raise ValueError("Project manifest is missing.")
        manifest = json.loads(archive.read("PROJECT_MANIFEST.json").decode("utf-8"))
        if manifest.get("project_package_version") != PROJECT_PACKAGE_VERSION:
            raise ValueError("Unsupported project package version.")
        expected = manifest.get("file_sha256")
        if not isinstance(expected, dict):
            raise ValueError("Project package checksum manifest is invalid.")

        total = 0
        checked: list[str] = []
        for info in infos:
            if info.filename == "PROJECT_MANIFEST.json":
                continue
            if info.is_dir():
                continue
            if not _safe_name(info.filename):
                raise ValueError(f"Unsafe package path: {info.filename}")
            total += int(info.file_size)
            if total > MAX_PACKAGE_BYTES:
                raise ValueError("Evidence package exceeds the uncompressed limit.")
            content = archive.read(info.filename)
            if expected.get(info.filename) != _sha256(content):
                raise ValueError(f"Checksum mismatch: {info.filename}")
            checked.append(info.filename)

        if set(checked) != set(expected):
            raise ValueError("Evidence package file list does not match its manifest.")

        project = manifest["project"]
        readiness = manifest["readiness"]
        return EvidencePackageSummary(
            project_id=str(project["project_id"]),
            project_code=str(project["project_code"]),
            generated_at_utc=str(manifest["generated_at_utc"]),
            readiness_score=int(readiness["score"]),
            file_count=len(checked),
            total_bytes=total,
            included_model_files=bool(manifest.get("included_model_files", False)),
            files=tuple(sorted(checked)),
        )
