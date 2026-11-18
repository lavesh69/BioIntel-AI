from pathlib import Path

from biointel.portfolio_demo_v183 import (
    PROFILES,
    TARGET_MODULES,
    build_portfolio_demos,
    portfolio_demo_matrix,
    validate_module_demo,
)

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_has_exactly_80_unique_modules():
    assert len(PROFILES) == 80
    assert len(TARGET_MODULES) == 80
    assert len(set(TARGET_MODULES)) == 80


def test_build_and_validate_all_demo_bundles():
    assert (ROOT / "STEP183_BUILD_RESULT.json").is_file()
    failures = [key for key in TARGET_MODULES if not validate_module_demo(ROOT, key).demo_ready]
    assert failures == []


def test_demo_ratings_improve_without_changing_real_rating():
    frame = portfolio_demo_matrix(ROOT)
    assert len(frame) == 80
    assert frame.demo_ready.all()
    assert (frame.demo_operational_rating > frame.baseline_practical_rating).all()
    assert (frame.real_external_rating == frame.baseline_practical_rating).all()
    assert not frame.real_external_rating_changed.any()
    assert not frame.controlled_release_eligible.any()


def test_all_target_pages_include_step183_hook():
    missing = []
    for key, profile in PROFILES.items():
        text = (ROOT / profile.page).read_text(encoding="utf-8")
        marker = f'_render_step183_portfolio_demo("{key}"'
        marker_single = f"_render_step183_portfolio_demo('{key}'"
        if marker not in text and marker_single not in text:
            missing.append((key, profile.page))
    assert missing == []


def test_demo_manifests_never_unlock_release():
    for key in TARGET_MODULES:
        folder = ROOT / "UserData" / "step183" / "module_demos" / key
        payload = (folder / "demo_manifest.json").read_text(encoding="utf-8")
        assert '"real_external_evidence": false' in payload
        assert '"controlled_release_eligible": false' in payload
