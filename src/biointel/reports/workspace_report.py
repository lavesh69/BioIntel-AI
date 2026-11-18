from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_report_path

import html
import json
from datetime import UTC, datetime
from pathlib import Path

from biointel.data.dataset_registry import list_datasets
from biointel.governance.governance_registry import governance_portfolio_summary
from biointel.operations.executive_summary import build_executive_summary
from biointel.portfolio.project_registry import list_projects
from biointel.training.experiment_registry import list_experiments
from biointel.training.model_catalog import sync_model_catalog
from biointel.ui.brand import BRAND
from biointel.utils.audit_log import verify_audit_chain
from biointel.utils.diagnostics import diagnostic_summary, run_diagnostics
from biointel.utils.workflow_status import build_workflow_status


def build_workspace_report_data(
    project_root: str | Path,
    title: str,
    notes: str = "",
) -> dict[str, object]:
    root = Path(project_root).resolve()
    diagnostic_checks = run_diagnostics(root, profile="quick")
    workflow_status = build_workflow_status(root, diagnostic_checks=diagnostic_checks)
    executive_summary = build_executive_summary(root, workflow_status=workflow_status)
    return {
        "title": title.strip() or "BioIntel AI Workspace Report",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "notes": notes.strip(),
        "workflow_status": workflow_status,
        "models": [entry.__dict__ for entry in sync_model_catalog(root / "models")],
        "datasets": [
            record.__dict__ for record in list_datasets(runtime_database_path(root, "datasets.sqlite3"))
        ],
        "experiments": list_experiments(runtime_database_path(root, "experiments.sqlite3"))[:25],
        "projects": [
            project.__dict__ for project in list_projects(runtime_database_path(root, "projects.sqlite3"))
        ],
        "executive_summary": executive_summary,
        "governance_summary": governance_portfolio_summary(runtime_database_path(root, "projects.sqlite3")),
        "audit_integrity": verify_audit_chain(runtime_report_path(root, "audit.jsonl")),
        "diagnostics": {
            "summary": diagnostic_summary(diagnostic_checks),
            "checks": [check.to_dict() for check in diagnostic_checks],
        },
    }


def _table(headers: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return '<div class="empty">No records available.</div>'
    header_html = "".join(f"<th>{html.escape(str(value))}</th>" for value in headers)
    row_html = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in row)
        row_html.append(f"<tr>{cells}</tr>")
    return (
        "<div class='table-wrap'><table>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(row_html)}</tbody>"
        "</table></div>"
    )


def build_workspace_report_html(
    report: dict[str, object],
) -> str:
    status = report["workflow_status"]
    models = report["models"]
    datasets = report["datasets"]
    experiments = report["experiments"]
    diagnostics = report["diagnostics"]
    projects = report.get("projects", [])
    executive = report.get("executive_summary", {})
    governance = report.get("governance_summary", {})
    audit = report.get("audit_integrity", {})

    model_rows = [
        [
            item.get("filename", ""),
            item.get("state", ""),
            "Yes" if item.get("is_default") else "No",
            item.get("updated_at_utc", ""),
        ]
        for item in models
    ]
    dataset_rows = [
        [
            item.get("dataset_name", ""),
            item.get("dataset_version", ""),
            item.get("task_type", ""),
            item.get("row_count", ""),
            str(item.get("dataset_sha256", ""))[:16] + "…",
        ]
        for item in datasets
    ]
    experiment_rows = [
        [
            item.get("experiment_id", ""),
            item.get("model_name", ""),
            item.get("task_type", ""),
            item.get("dataset_name", ""),
            item.get("trained_at_utc", ""),
        ]
        for item in experiments
    ]

    project_rows = [
        [
            item.get("project_code", ""),
            item.get("name", ""),
            item.get("status", ""),
            item.get("priority", ""),
            item.get("target_date", "") or "",
            "Yes" if item.get("dataset_sha256") else "No",
            "Yes" if item.get("model_filename") else "No",
        ]
        for item in projects
    ]

    notes = html.escape(str(report.get("notes", "")))
    notes_block = f"<section><h2>Research notes</h2><p>{notes}</p></section>" if notes else ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(str(report["title"]))}</title>
<style>
:root {{
  --bg:#07111F; --surface:#111C30; --line:#263B58;
  --text:#F8FAFC; --muted:#9DB6C8; --purple:#8B5CF6;
  --cyan:#22D3EE; --blue:#3B82F6; --green:#22C55E;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; font-family:Inter,Segoe UI,sans-serif; color:var(--text);
  background:
    radial-gradient(circle at 8% 0%,rgba(34,211,238,.12),transparent 30%),
    radial-gradient(circle at 92% 8%,rgba(59,130,246,.10),transparent 28%),
    var(--bg);
}}
main {{ max-width:1120px; margin:auto; padding:48px 28px 72px; }}
.hero {{
  padding:42px; border:1px solid var(--line); border-radius:28px;
  background:linear-gradient(135deg,rgba(18,27,49,.96),rgba(10,17,32,.82));
  box-shadow:0 28px 90px rgba(2,6,23,.55);
}}
.eyebrow {{ color:#c4b5fd; font-weight:800; letter-spacing:.12em;
  text-transform:uppercase; font-size:12px; }}
h1 {{ font-size:48px; line-height:1.02; letter-spacing:-.05em; margin:14px 0; }}
h2 {{ margin:0 0 18px; font-size:22px; }}
p {{ color:var(--muted); line-height:1.7; }}
.grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:22px 0; }}
.metric, section {{
  border:1px solid var(--line); border-radius:18px;
  background:rgba(16,25,46,.82); padding:20px;
}}
.metric span {{ color:var(--muted); display:block; font-size:12px; font-weight:700; }}
.metric strong {{ display:block; font-size:26px; margin-top:8px; }}
section {{ margin-top:18px; }}
.table-wrap {{ overflow:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:left; padding:11px 12px; border-bottom:1px solid var(--line); }}
th {{ color:#cbd5e1; background:rgba(34,211,238,.08); }}
td {{ color:#dbe5f2; }}
.badge {{ display:inline-block; padding:7px 11px; border-radius:999px;
  color:#a7f3d0; background:rgba(16,185,129,.12);
  border:1px solid rgba(52,211,153,.3); font-weight:800; font-size:12px; }}
.empty {{ color:var(--muted); padding:16px; border:1px dashed var(--line); border-radius:12px; }}
pre {{ white-space:pre-wrap; color:#c4b5fd; background:#080d19; padding:16px; border-radius:14px; }}
footer {{ color:var(--muted); text-align:center; margin-top:32px; font-size:12px; }}
@media(max-width:760px) {{
  .grid {{ grid-template-columns:repeat(2,1fr); }}
  h1 {{ font-size:34px; }} .hero {{ padding:26px; }}
}}
@media print {{
  body {{ background:white; color:#111827; }}
  main {{ max-width:none; padding:0; }}
  .hero,section,.metric {{ color:#111827; background:white; box-shadow:none; }}
  p,td,footer {{ color:#374151; }}
  .badge {{ color:#065f46; }}
}}
</style>
</head>
<body>
<main>
  <div class="hero">
    <div class="eyebrow">{html.escape(BRAND.name)} · {html.escape(BRAND.descriptor)}</div>
    <h1>{html.escape(str(report["title"]))}</h1>
    <p><strong>{html.escape(BRAND.tagline)}</strong></p>
    <p>Generated {html.escape(str(report["generated_at_utc"]))}</p>
    <span class="badge">No-login local workspace</span>
  </div>
  <div class="grid">
    <div class="metric"><span>Datasets</span><strong>{status["datasets"]["total"]}</strong></div>
    <div class="metric"><span>Models</span><strong>{status["models"]["total"]}</strong></div>
    <div class="metric"><span>Experiments</span><strong>{status["experiments"]["total"]}</strong></div>
    <div class="metric"><span>Diagnostics</span><strong>{diagnostics["summary"]["overall"]}</strong></div>
    <div class="metric"><span>Projects</span><strong>{executive.get("portfolio", {}).get("total", 0)}</strong></div>
    <div class="metric"><span>Maturity</span><strong>{executive.get("maturity_score", 0)}/100</strong></div>
  </div>
  {notes_block}
  <section><h2>Executive summary</h2><pre>{html.escape(json.dumps(executive, indent=2, default=str))}</pre></section>
  <section><h2>Governance summary</h2><pre>{html.escape(json.dumps(governance, indent=2, default=str))}</pre></section>
  <section><h2>Audit integrity</h2><pre>{html.escape(json.dumps(audit, indent=2, default=str))}</pre></section>
  <section><h2>Project portfolio</h2>{_table(["Code", "Project", "Status", "Priority", "Target", "Dataset", "Model"], project_rows)}</section>
  <section><h2>Model lifecycle</h2>{_table(["Model", "State", "Default", "Updated"], model_rows)}</section>
  <section><h2>Dataset registry</h2>{_table(["Dataset", "Version", "Task", "Rows", "SHA-256"], dataset_rows)}</section>
  <section><h2>Recent experiments</h2>{_table(["Experiment", "Model", "Task", "Dataset", "Trained"], experiment_rows)}</section>
  <section><h2>Diagnostics summary</h2><pre>{html.escape(json.dumps(diagnostics["summary"], indent=2))}</pre></section>
  <footer>Generated with {html.escape(BRAND.name)} · Evidence-aware scientific intelligence · Research use only; experimental validation is required.</footer>
</main>
</body>
</html>"""
