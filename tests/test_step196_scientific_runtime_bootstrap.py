from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup_scientific_runtime_windows.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("step196_scientific_runtime_bootstrap_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_weak_module_plan_is_complete_and_honest() -> None:
    module = _load_module()
    plan = module.build_priority_plan(ROOT)

    assert len(plan["weak_modules"]) == 25
    assert plan["automatic_engine_count_targeted"] == 34
    assert plan["manual_or_provider_engine_count_targeted"] == 5
    assert plan["automatic_reference_count_targeted"] == 7
    assert plan["automatic_reference_storage_gb_targeted"] == 1.8
    assert plan["total_reference_storage_gb_targeted"] > 2800
    assert plan["large_or_authorised_references_remain_operator_controlled"] is True
    assert plan["external_evidence_is_not_installable_or_fabricated"] is True


def test_plan_mode_writes_no_system_changes(tmp_path: Path) -> None:
    module = _load_module()
    output = tmp_path / "scientific-runtime.json"

    assert module.main(["--root", str(ROOT), "--mode", "plan", "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    plan = json.loads((tmp_path / "step196-weak-module-install-plan.json").read_text(encoding="utf-8"))

    assert payload["runtime_state"] == "planned-no-system-changes"
    assert payload["targeted_weak_module_count"] == 25
    assert plan["automatic_engine_count_targeted"] == 34


def test_current_installer_starts_integrated_runtime_preparation() -> None:
    installer = (ROOT / "scripts" / "install_windows_step196.py").read_text(encoding="utf-8")
    validator = (ROOT / "scripts" / "step196_validate_release.py").read_text(encoding="utf-8")

    assert "setup_scientific_runtime_windows.py" in installer
    assert "launch_scientific_runtime_setup" in installer
    assert "--attempt-wsl-bootstrap" in installer
    assert "setup_scientific_runtime_windows.py" in validator
