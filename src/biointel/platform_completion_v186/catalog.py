from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
from biointel.target_modules_v179.catalog import TARGET_PROFILES as PLATFORM_PROFILES

@dataclass(frozen=True)
class PlatformCompletionProfile:
    module_key: str
    title: str
    page: str
    focus: str
    before_demo_rating: float
    target_demo_rating: float
    baseline_practical_rating: float
    boundary: str

_root = Path(__file__).resolve().parents[3]
_frame = pd.read_csv(_root / "STEP185_80_MODULE_FINAL_DEMO_RATINGS.csv")
_current = {str(r.module_key): float(r.step185_final_demo_rating) for r in _frame.itertuples()}
TARGET_PROFILES = {
    key: PlatformCompletionProfile(
        module_key=key,
        title=profile.title,
        page=profile.page,
        focus=profile.focus,
        before_demo_rating=_current[key],
        target_demo_rating=10.0,
        baseline_practical_rating=profile.baseline_rating,
        boundary=profile.boundary,
    )
    for key, profile in PLATFORM_PROFILES.items()
    if _current.get(key, 0.0) <= 9.0
}
TARGET_MODULES = tuple(TARGET_PROFILES)
assert len(TARGET_MODULES) == 18
assert all(abs(p.before_demo_rating - 9.0) < 1e-9 for p in TARGET_PROFILES.values())

ASSURANCE_DIMENSIONS = (
    "deterministic_platform_execution",
    "golden_output_and_schema_contract",
    "negative_and_corruption_rejection",
    "concurrency_and_race_safety",
    "crash_recovery_and_checkpoint_resume",
    "tamper_evident_integrity",
    "least_privilege_and_sandbox_security",
    "secret_and_sensitive_log_redaction",
    "backup_restore_and_rollback_rehearsal",
    "scale_soak_latency_and_memory_benchmark",
    "repeatability_and_reproducible_hashes",
    "monitoring_alerts_and_owner_thresholds",
    "accessibility_and_keyboard_contract",
    "windows_install_repair_uninstall_dry_run",
    "provenance_page_and_dashboard_integration",
)
__all__=["PlatformCompletionProfile","TARGET_PROFILES","TARGET_MODULES","ASSURANCE_DIMENSIONS"]
