from __future__ import annotations

"""Functional local execution contracts for the fixed P0/P1 portfolio.

This layer joins an already implemented module page to the priority evidence
registry without inventing a second scientific pipeline.  It provides durable
workspaces, disk-backed input intake, preflight manifests and a canonical
execution identity.  It deliberately does *not* treat a local code check or a
stored file as external scientific proof or a release decision.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .catalog import PRIORITY_MODULES, canonical_execution_key
from .registry import PriorityEvidenceRegistry


_HOOK_RE = re.compile(
    r"_render_step196_p0_p1_priority_workbench\(ROOT,\s*['\"](?P<key>[a-z0-9_]+)['\"]"
)

# These profiles already have a protected raw-file parser, persistent local
# queue, pause/resume controls and reference/engine readiness checks.  Import
# that implementation lazily so a dependency-free installer preflight never
# needs BioPython, pandas or a specialist executable just to inspect a release.
NATIVE_PIPELINE_KEYS = frozenset(
    {
        "digital_pathology_foundation",
        "long_read_epigenome",
        "single_cell_long_read_isoforms",
        "biomedical_foundation_model_hub",
        "amr_surveillance",
        "spatial_medicine_tme",
        "gene_therapy_vector",
        "cell_therapy_cart",
        "federated_biomedical_ai",
        "clinical_biomarker_survival",
        "protein_ligand_codesign",
        "pangenome_population_medicine",
        "pharmacovigilance_intelligence",
        "synthetic_cohort_trial",
        "autonomous_lab_planner",
    }
)

_ADAPTER_DETAILS: dict[str, dict[str, Any]] = {
    "native_pipeline": {
        "label": "Native raw-data pipeline",
        "execution_surface": "Use the current module page's Native pipeline tab for bounded parsing, persistent jobs, pause/resume and local engine/reference checks.",
        "capabilities": (
            "Checksum-bound raw input staging",
            "Bounded native parsing and QC",
            "Persistent local job queue with pause/resume",
            "Optional-engine and reference readiness",
        ),
    },
    "nextgen_workbench": {
        "label": "Scientific analysis workbench",
        "execution_surface": "Use the current module page's Prepare & run, Explore results and Export tabs for the implemented local analysis flow.",
        "capabilities": (
            "Module-specific schema validation",
            "Local analysis and result inspection",
            "Reproducible export manifest",
            "No automatic external-evidence promotion",
        ),
    },
    "expansion_workbench": {
        "label": "Specialist scientific workbench",
        "execution_surface": "Use the current module page's specialist workbench to import genuine study data and run its implemented module-specific calculations.",
        "capabilities": (
            "Module-specific input contract",
            "Local specialist calculations",
            "Visual QC and export controls",
            "Explicit scientific-boundary messaging",
        ),
    },
    "dedicated_workbench": {
        "label": "Dedicated module workflow",
        "execution_surface": "Use the current module page's dedicated workflow; this execution record tracks its local input, workspace and preflight state without replacing the module's controls.",
        "capabilities": (
            "Dedicated page controls already installed",
            "Local input and run provenance",
            "Module-specific output/export workflow",
            "Evidence and release remain fail-closed",
        ),
    },
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe_markdown(value: str) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _priority_page_bindings(root: str | Path) -> dict[str, list[Path]]:
    project_root = Path(root).resolve()
    bindings: dict[str, list[Path]] = {key: [] for key in PRIORITY_MODULES}
    pages = project_root / "pages"
    if not pages.is_dir():
        return bindings
    for page in sorted(pages.glob("*.py")):
        try:
            source = page.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        for match in _HOOK_RE.finditer(source):
            key = match.group("key")
            if key in bindings:
                bindings[key].append(page)
    return bindings


def _adapter_for_source(execution_key: str, source: str) -> str:
    if execution_key in NATIVE_PIPELINE_KEYS:
        return "native_pipeline"
    if "render_nextgen_module(" in source:
        return "nextgen_workbench"
    if "render_expansion_module(" in source:
        return "expansion_workbench"
    return "dedicated_workbench"


def module_execution_contract(root: str | Path, module_key: str) -> dict[str, Any]:
    """Describe the one installed execution route for a priority module."""
    key = str(module_key).strip()
    profile = PRIORITY_MODULES.get(key)
    if profile is None:
        raise KeyError(f"{key!r} is not a P0/P1 priority module.")
    project_root = Path(root).resolve()
    bindings = _priority_page_bindings(project_root).get(key, [])
    page = bindings[0] if len(bindings) == 1 else None
    source = ""
    if page is not None:
        try:
            source = page.read_text(encoding="utf-8-sig")
        except OSError:
            source = ""
    execution_key = canonical_execution_key(key)
    adapter = _adapter_for_source(execution_key, source)
    details = _ADAPTER_DETAILS[adapter]
    return {
        "schema": "biointel.step196.p0p1.execution-contract.v1",
        "module_key": key,
        "execution_key": execution_key,
        "module_title": profile.title,
        "priority": profile.priority,
        "adapter": adapter,
        "adapter_label": details["label"],
        "execution_surface": details["execution_surface"],
        "capabilities": list(details["capabilities"]),
        "page": page.relative_to(project_root).as_posix() if page is not None else "",
        "page_binding_count": len(bindings),
        "page_exists": bool(page and page.is_file()),
        "priority_hook_bound": len(bindings) == 1,
        "input_boundary": "User-provided inputs are staged locally with SHA-256 and a 1 GiB per-file boundary. Input staging is not scientific qualification.",
        "proof_gate_requirements": profile.gate_requirements(),
        "controlled_release_approved": False,
        "rating_promotion": "not-automated",
        "external_evidence_fabricated": False,
    }


def execution_contract_bytes(root: str | Path, module_key: str) -> bytes:
    return (json.dumps(module_execution_contract(root, module_key), indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _native_preflight(execution_key: str) -> dict[str, Any]:
    """Run only the installed native pipeline's safe readiness probe.

    A missing optional package or executable becomes a recorded blocker instead
    of an import-time application crash.
    """
    try:
        from biointel.nextgen.native_execution_v136 import pipeline_readiness

        readiness = pipeline_readiness(execution_key)
        return {
            "state": "probed",
            "pipeline_readiness": readiness,
            "adapter_available": True,
        }
    except Exception as exc:  # pragma: no cover - environment-specific runtime probes
        return {
            "state": "blocked",
            "adapter_available": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }


def run_execution_preflight(
    root: str | Path,
    module_key: str,
    *,
    registry: PriorityEvidenceRegistry | None = None,
) -> dict[str, Any]:
    """Perform and persist an honest local readiness preflight for one module."""
    project_root = Path(root).resolve()
    local_registry = registry or PriorityEvidenceRegistry(project_root)
    contract = module_execution_contract(project_root, module_key)
    workspace = local_registry.functional_workspace_root / contract["module_key"]
    inputs = local_registry.execution_input_rows(contract["module_key"])
    checks = [
        {
            "name": "one priority-page binding",
            "passed": bool(contract["priority_hook_bound"]),
            "detail": f"bindings={contract['page_binding_count']}",
        },
        {
            "name": "module page present",
            "passed": bool(contract["page_exists"]),
            "detail": contract["page"] or "No matching page found",
        },
        {
            "name": "functional workspace present",
            "passed": workspace.is_dir(),
            "detail": str(workspace),
        },
        {
            "name": "production input staged",
            "passed": bool(inputs),
            "detail": f"inputs={len(inputs)}; a missing input is expected until the user supplies one",
        },
    ]
    adapter_probe: dict[str, Any] = {"state": "not-required", "adapter_available": True}
    if contract["adapter"] == "native_pipeline":
        adapter_probe = _native_preflight(str(contract["execution_key"]))
        checks.append(
            {
                "name": "native pipeline import and readiness probe",
                "passed": bool(adapter_probe.get("adapter_available")),
                "detail": str(adapter_probe.get("state", "unknown")),
            }
        )

    page_ready = all(bool(row["passed"]) for row in checks[:2])
    workspace_ready = bool(checks[2]["passed"])
    adapter_ready = bool(adapter_probe.get("adapter_available"))
    if not page_ready or not adapter_ready:
        status = "adapter-repair-required"
    elif not workspace_ready:
        status = "workspace-preparation-required"
    elif inputs:
        status = "ready-for-local-execution-input-staged"
    else:
        status = "ready-for-local-input"
    payload = {
        "preflight_at_utc": _utc_now(),
        "contract": contract,
        "workspace": str(workspace),
        "input_count": len(inputs),
        "latest_input": inputs[0] if inputs else None,
        "storage": local_registry.storage_status(),
        "checks": checks,
        "adapter_probe": adapter_probe,
        "controlled_release_approved": False,
        "scientific_validation": "not-established-by-preflight",
    }
    record = local_registry.write_execution_record(
        contract["module_key"],
        execution_key=str(contract["execution_key"]),
        adapter=str(contract["adapter"]),
        action="execution_preflight",
        status=status,
        payload=payload,
    )
    return {**payload, "status": status, "record": record}


def _workspace_files(contract: dict[str, Any]) -> dict[str, str]:
    title = _safe_markdown(str(contract["module_title"]))
    module_key = str(contract["module_key"])
    adapter_label = _safe_markdown(str(contract["adapter_label"]))
    execution_surface = _safe_markdown(str(contract["execution_surface"]))
    capabilities = "\n".join(f"- {item}" for item in contract["capabilities"])
    return {
        "execution_contract.json": json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
        "README.md": (
            f"# {contract['priority']} priority execution workspace · {title}\n\n"
            f"Execution adapter: **{adapter_label}**\n\n"
            f"{execution_surface}\n\n"
            "## Local capabilities\n\n"
            f"{capabilities}\n\n"
            "## Safety boundary\n\n"
            "This workspace contains local intake, preflight and audit material. It cannot establish data qualification, a real benchmark, independent confirmation, licence rights, expert approval or controlled release. Do not place synthetic/demo artifacts here as proof-gate evidence.\n"
        ),
        "input/README.md": (
            "Place only user-authorised source files here through the P0/P1 workbench's local staging action. "
            "Each staged file is SHA-256 recorded; staging alone has no qualification effect.\n"
        ),
        "reference_assets/README.md": (
            "Keep provider-authorised reference bindings, licence records and checksum metadata here. "
            "Do not copy proprietary databases or model weights into a redistributable package.\n"
        ),
        "working/README.md": "Transient local working material belongs here. Preserve source and result lineage outside this folder before cleanup.\n",
        "results/README.md": "Store locally generated result manifests and checked outputs here. Results remain research-only until the required proof gates are manually reviewed.\n",
        "review/README.md": "Store responsible-reviewer notes, protocol references and independent-review artifacts here. Local files do not equal approval.\n",
        "exports/README.md": "Put reproducible exports and their manifests here. Never label an export as controlled release without the responsible governance decision.\n",
    }


def prepare_functional_workspaces(
    root: str | Path,
    module_key: str | None = None,
    *,
    registry: PriorityEvidenceRegistry | None = None,
    refresh: bool = False,
) -> list[Path]:
    """Create durable, non-destructive execution workspaces for one or all 62 modules."""
    project_root = Path(root).resolve()
    local_registry = registry or PriorityEvidenceRegistry(project_root)
    keys = [str(module_key).strip()] if module_key else list(PRIORITY_MODULES)
    for key in keys:
        if key not in PRIORITY_MODULES:
            raise KeyError(f"{key!r} is not a P0/P1 priority module.")
    written: list[Path] = []
    for key in keys:
        contract = module_execution_contract(project_root, key)
        workspace = local_registry.functional_workspace_root / key
        workspace.mkdir(parents=True, exist_ok=True)
        for name, content in _workspace_files(contract).items():
            target = workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if refresh or not target.exists():
                temporary = target.with_name(f".{target.name}.part")
                temporary.write_text(content, encoding="utf-8")
                temporary.replace(target)
                written.append(target)
        local_registry.write_execution_record(
            key,
            execution_key=str(contract["execution_key"]),
            adapter=str(contract["adapter"]),
            action="functional_workspace_prepared",
            status="prepared",
            payload={
                "workspace": str(workspace),
                "files_written": [path.relative_to(workspace).as_posix() for path in written if workspace in path.parents],
                "refresh": bool(refresh),
                "controlled_release_approved": False,
            },
        )
    return written


def execution_portfolio_rows(root: str | Path, registry: PriorityEvidenceRegistry) -> list[dict[str, Any]]:
    """Return a compact, truthful live execution inventory for the portfolio UI."""
    project_root = Path(root).resolve()
    latest: dict[str, dict[str, Any]] = {}
    for row in registry.execution_rows(limit=5_000):
        latest.setdefault(str(row["module_key"]), row)
    rows: list[dict[str, Any]] = []
    for key, profile in PRIORITY_MODULES.items():
        contract = module_execution_contract(project_root, key)
        inputs = registry.execution_input_rows(key)
        workspace = registry.functional_workspace_root / key
        last = latest.get(key)
        rows.append(
            {
                "Priority": profile.priority,
                "Module": profile.title,
                "Module key": key,
                "Execution key": contract["execution_key"],
                "Adapter": contract["adapter_label"],
                "Workspace": "Prepared" if workspace.is_dir() else "Not prepared",
                "Staged inputs": len(inputs),
                "Latest local action": last["action"] if last else "—",
                "Latest local status": last["status"] if last else "Not checked",
                "Controlled release": "Not automated",
            }
        )
    return rows


__all__ = [
    "NATIVE_PIPELINE_KEYS",
    "execution_contract_bytes",
    "execution_portfolio_rows",
    "module_execution_contract",
    "prepare_functional_workspaces",
    "run_execution_preflight",
]
