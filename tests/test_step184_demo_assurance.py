from pathlib import Path
import json

from biointel.demo_assurance_v184 import (
    ASSURANCE_DIMENSIONS,
    TARGET_MODULES,
    TARGET_PROFILES,
    step184_rating_matrix,
    validate_step184_module,
)

ROOT = Path(__file__).resolve().parents[1]


def test_step184_has_exactly_43_modules():
    assert len(TARGET_MODULES) == 43
    assert len(TARGET_PROFILES) == 43
    assert len(set(TARGET_MODULES)) == 43
    assert all(profile.before_demo_rating < 8.0 for profile in TARGET_PROFILES.values())


def test_step184_all_modules_are_10_of_10():
    failures = {key: validate_step184_module(ROOT, key).blockers for key in TARGET_MODULES if not validate_step184_module(ROOT, key).qualified_10_of_10}
    assert failures == {}


def test_step184_dimensions_are_complete():
    assert len(ASSURANCE_DIMENSIONS) == 10
    for key in TARGET_MODULES:
        manifest = json.loads((ROOT / "UserData" / "step184" / "advanced_demo_assurance" / key / "assurance_manifest.json").read_text(encoding="utf-8"))
        assert tuple(item["dimension"] for item in manifest["dimensions"]) == ASSURANCE_DIMENSIONS
        assert all(item["passed"] and item["score"] == 1.0 for item in manifest["dimensions"])


def test_step184_ratings_improve_without_faking_real_evidence():
    frame = step184_rating_matrix(ROOT)
    assert len(frame) == 43
    assert frame.qualified_10_of_10.all()
    assert (frame.after_demo_assurance_rating == 10.0).all()
    assert (frame.after_demo_assurance_rating > frame.before_demo_rating).all()
    assert not frame.real_external_rating_changed.any()
    assert not frame.controlled_release_eligible.any()


def test_step184_all_target_pages_have_hook():
    missing = []
    for key, profile in TARGET_PROFILES.items():
        text = (ROOT / profile.page).read_text(encoding="utf-8")
        if f'_render_step184_demo_assurance("{key}"' not in text and f"_render_step184_demo_assurance('{key}'" not in text:
            missing.append((key, profile.page))
    assert missing == []


def test_step184_negative_and_performance_artifacts_pass():
    import pandas as pd
    for key in TARGET_MODULES:
        folder = ROOT / "UserData" / "step184" / "advanced_demo_assurance" / key
        negative = pd.read_csv(folder / "negative_security_results.csv")
        perf = pd.read_csv(folder / "performance_benchmark.csv")
        assert len(negative) >= 12 and negative.passed.all()
        assert set(perf.records) == {120, 1000, 5000}
        assert (perf.status == "pass").all()
