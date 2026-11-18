from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.scientific_depth.capability import CAPABILITY_SPECS
from biointel.scientific_depth.native_workflows import native_workflow_spec
from biointel.scientific_depth.profiles import MODULE_PROFILES
from biointel.scientific_depth.toolchain_readiness import detect_specialist_toolchains, reference_readiness
from biointel.ui.navigation import PAGE_CATALOG

from .resource_guard import capture_resource_snapshot


def scientific_module_health(root: str | Path) -> pd.DataFrame:
    project_root = Path(root).resolve()
    tools = detect_specialist_toolchains()
    references = reference_readiness(project_root)
    tool_modules: dict[str, tuple[int, int]] = {}
    if not tools.empty:
        for _, row in tools.iterrows():
            modules = [item.strip() for item in str(row.get("modules", "")).split(",") if item.strip()]
            for module in modules:
                total, available = tool_modules.get(module, (0, 0))
                tool_modules[module] = (total + 1, available + int(bool(row.get("available"))))
    rows: list[dict[str, Any]] = []
    for module_key, profile in sorted(MODULE_PROFILES.items()):
        spec = native_workflow_spec(module_key)
        reference_rows = references.loc[references["module_key"] == module_key] if not references.empty else pd.DataFrame()
        reference_total = int(len(reference_rows))
        reference_ready = int(reference_rows["qualified_for_use"].astype(bool).sum()) if not reference_rows.empty else 0
        tool_total, tool_ready = tool_modules.get(module_key, (0, 0))
        contract_complete = module_key in CAPABILITY_SPECS and len(CAPABILITY_SPECS[module_key].stages) >= 6
        internal_score = 100 if contract_complete and spec.workflow_key else 85
        specialist_score = 100 if tool_total == 0 else round(100 * tool_ready / tool_total)
        reference_score = 100 if reference_total == 0 else round(100 * reference_ready / reference_total)
        rows.append(
            {
                "module_key": module_key,
                "title": profile.title,
                "native_family": spec.family,
                "internal_contract_complete": contract_complete,
                "internal_implementation_score": internal_score,
                "specialist_tools_available": tool_ready,
                "specialist_tools_required": tool_total,
                "specialist_runtime_score": specialist_score,
                "qualified_references": reference_ready,
                "required_references": reference_total,
                "reference_score": reference_score,
                "external_validation_required": bool(profile.validations),
                "release_ready": bool(internal_score == 100 and specialist_score == 100 and reference_score == 100 and not profile.validations),
                "boundary": profile.boundary,
            }
        )
    return pd.DataFrame(rows)


def page_source_health(root: str | Path) -> pd.DataFrame:
    project_root = Path(root).resolve()
    rows: list[dict[str, Any]] = []
    for page in PAGE_CATALOG:
        path = project_root / page.path
        exists = path.is_file()
        syntax_ok = False
        line_count = 0
        issue = ""
        if exists:
            try:
                text = path.read_text(encoding="utf-8")
                line_count = len(text.splitlines())
                ast.parse(text, filename=str(path))
                syntax_ok = True
            except (OSError, SyntaxError, UnicodeError) as exc:
                issue = f"{type(exc).__name__}: {exc}"
        else:
            issue = "Page file is missing"
        rows.append(
            {
                "page_key": page.key,
                "title": page.title,
                "category": page.category,
                "path": page.path,
                "exists": exists,
                "syntax_ok": syntax_ok,
                "line_count": line_count,
                "thin_wrapper": bool(0 < line_count <= 30),
                "issue": issue,
            }
        )
    return pd.DataFrame(rows)


def runtime_diagnostic_index(root: str | Path) -> pd.DataFrame:
    folder = Path(root).resolve() / "UserData" / "runtime_diagnostics" / "native_failures"
    rows: list[dict[str, Any]] = []
    if not folder.is_dir():
        return pd.DataFrame(columns=["file", "size_bytes", "modified_utc"])
    for path in sorted(folder.glob("NATIVE-*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        stat = path.stat()
        rows.append({"file": path.name, "size_bytes": stat.st_size, "modified_utc": pd.Timestamp(stat.st_mtime, unit="s", tz="UTC")})
    return pd.DataFrame(rows)


def reliability_summary(root: str | Path) -> dict[str, Any]:
    modules = scientific_module_health(root)
    pages = page_source_health(root)
    resources = capture_resource_snapshot(root)
    diagnostics = runtime_diagnostic_index(root)
    return {
        "schema": "biointel.step159.module-reliability-summary.v1",
        "scientific_modules": int(len(modules)),
        "internal_complete": int((modules["internal_implementation_score"] == 100).sum()) if not modules.empty else 0,
        "specialist_runtime_complete": int((modules["specialist_runtime_score"] == 100).sum()) if not modules.empty else 0,
        "references_complete": int((modules["reference_score"] == 100).sum()) if not modules.empty else 0,
        "pages": int(len(pages)),
        "pages_present": int(pages["exists"].astype(bool).sum()) if not pages.empty else 0,
        "pages_syntax_clean": int(pages["syntax_ok"].astype(bool).sum()) if not pages.empty else 0,
        "thin_wrappers": int(pages["thin_wrapper"].astype(bool).sum()) if not pages.empty else 0,
        "runtime_diagnostics": int(len(diagnostics)),
        "resources": resources.to_dict(),
    }
