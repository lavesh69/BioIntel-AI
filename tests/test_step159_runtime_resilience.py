from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import pandas as pd

from biointel.scientific_depth import native_input_template, run_native_workflow
from biointel.stability_v159 import (
    ResourceSnapshot,
    assess_dataframe_admission,
    circuit_decision,
    clear_failure,
    record_failure,
    write_failure_diagnostic,
)
from biointel.stability_v159.module_health import page_source_health, reliability_summary, scientific_module_health
from biointel.ui.navigation import PAGE_BY_KEY


def test_resource_guard_downgrades_under_pressure(tmp_path: Path) -> None:
    frame = pd.DataFrame({f"f{i}": range(1_000) for i in range(40)})
    snapshot = ResourceSnapshot(
        total_memory_bytes=2 * 1024**3,
        available_memory_bytes=300 * 1024**2,
        process_rss_bytes=100 * 1024**2,
        cpu_count=4,
        disk_free_bytes=20 * 1024**3,
        source="test",
    )
    admission = assess_dataframe_admission(frame, "full", root=tmp_path, snapshot=snapshot)
    assert admission.effective_mode == "interactive"
    assert admission.downgraded is True
    assert admission.max_rows == 250_000
    assert admission.max_features == 100


def test_auto_native_run_records_resource_and_crash_controls() -> None:
    result = run_native_workflow(
        "population_gwas",
        native_input_template("population_gwas", demonstration=True),
        metadata={"analysis_mode": "auto"},
    )
    assert result.status in {"pass", "review"}
    assert result.summary["crash_loop_protection"] is True
    assert result.summary["resource_guard"]["effective_mode"] in {"interactive", "extended", "full"}
    assert result.provenance["release_step"] >= 159
    assert result.provenance["resource_snapshot"]["available_memory_bytes"] >= 0
    assert "native_execution_seconds" in set(result.metrics["metric"].astype(str))


def test_circuit_breaker_blocks_repeated_identical_failures() -> None:
    fingerprint = "step159-test-fingerprint"
    clear_failure(fingerprint)
    assert circuit_decision(fingerprint).allowed is True
    record_failure(fingerprint)
    record_failure(fingerprint)
    decision = circuit_decision(fingerprint)
    assert decision.allowed is False
    assert decision.retry_after_seconds > 0
    clear_failure(fingerprint)
    assert circuit_decision(fingerprint).allowed is True


def test_failure_diagnostic_redacts_secrets(tmp_path: Path) -> None:
    path = write_failure_diagnostic(
        tmp_path,
        module_key="population_gwas",
        fingerprint="abc",
        error_type="ValueError",
        error_message="bad input",
        metadata={"api_key": "secret-value", "nested": {"password": "hidden", "safe": "visible"}},
        resources={"available": 1},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["metadata"]["api_key"] == "[REDACTED]"
    assert payload["metadata"]["nested"]["password"] == "[REDACTED]"
    assert payload["metadata"]["nested"]["safe"] == "visible"


def test_reliability_command_center_and_page_matrix() -> None:
    assert "module_reliability_command_center" in PAGE_BY_KEY
    assert PAGE_BY_KEY["module_reliability_command_center"].path == "pages/228_Module_Reliability_Command_Center.py"
    pages = page_source_health(ROOT)
    assert len(pages) == len(PAGE_BY_KEY)
    assert pages["exists"].all()
    assert pages["syntax_ok"].all()
    modules = scientific_module_health(ROOT)
    assert len(modules) == 80
    assert modules["internal_contract_complete"].all()
    summary = reliability_summary(ROOT)
    assert summary["pages_syntax_clean"] == summary["pages"]
    assert summary["scientific_modules"] == 80


def test_renderer_uses_explicit_protected_execution() -> None:
    text = (ROOT / "src" / "biointel" / "scientific_depth" / "renderer.py").read_text(encoding="utf-8")
    assert "Run protected native analysis" in text
    assert '"auto", "interactive", "extended", "full"' in text
    assert "Step 160 native execution manifest" in text


def test_step159_release_surface_and_quick_validator() -> None:
    release = json.loads((ROOT / "STEP159_RELEASE.json").read_text(encoding="utf-8"))
    assert release["step"] == 159
    assert release["registered_screens"] >= 230
    assert "Step 159" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "VERIFY_STEP159_WINDOWS.bat" in (ROOT / "VERIFY_LATEST_WINDOWS.bat").read_text(encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "step159_validate_installation.py"), "--root", str(ROOT), "--quick"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src")},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
