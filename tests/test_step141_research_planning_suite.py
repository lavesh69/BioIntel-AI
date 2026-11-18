from __future__ import annotations

from pathlib import Path

from biointel.research_planning.catalog import MODULE_BY_KEY, PLANNING_MODULES
from biointel.research_planning.export import build_bundle
from biointel.research_planning.review_store import PlanningReviewStore
from biointel.research_planning.scientific import analyse, demo_frame
from biointel.research_planning.visuals import build_figure
from biointel.ui.navigation import PAGE_CATALOG


def test_step141_catalog_is_complete_and_unique():
    assert len(PLANNING_MODULES) == 16
    assert len(MODULE_BY_KEY) == 16
    assert len({module.page_number for module in PLANNING_MODULES}) == 16
    assert len({module.title for module in PLANNING_MODULES}) == 16
    assert all(len(module.features) >= 10 for module in PLANNING_MODULES)
    assert all(len(module.visuals) == 8 for module in PLANNING_MODULES)


def test_step141_all_modules_analyse_and_visualise():
    for module in PLANNING_MODULES:
        result = analyse(module.key, demo_frame(module.key, 60))
        assert not result.primary.empty
        assert result.summary.get("input_sha256")
        assert result.main_finding
        assert result.next_step
        assert len(result.tables) >= 4
        for visual in module.visuals:
            figure, data = build_figure(visual, result)
            assert len(figure.data) >= 1
            assert data is not None


def test_step141_exports_are_reproducible_zip_payloads():
    for module in PLANNING_MODULES:
        result = analyse(module.key, demo_frame(module.key, 30))
        payload, manifest = build_bundle(module, result)
        assert payload[:2] == b"PK"
        assert len(payload) > 500
        assert len(manifest["bundle_sha256"]) == 64
        assert manifest["source_input_sha256"] == result.summary["input_sha256"]


def test_step141_review_store_persists_reviews_and_versions(tmp_path: Path):
    store = PlanningReviewStore(tmp_path / "planning.sqlite")
    store.upsert_review("study_protocol_designer", "Objectives", "Accepted", "Reviewer", "Ready")
    reviews = store.reviews("study_protocol_designer")
    assert len(reviews) == 1
    assert reviews.iloc[0]["decision"] == "Accepted"
    version_id = store.save_version(
        "study_protocol_designer",
        "Locked",
        "a" * 64,
        {"summary": "locked"},
        "Reviewer",
        "Approved planning version",
    )
    assert version_id == 1
    versions = store.versions("study_protocol_designer")
    assert len(versions) == 1
    assert versions.iloc[0]["status"] == "Locked"


def test_step141_navigation_contains_eighteen_research_planning_modules():
    planning = [page for page in PAGE_CATALOG if page.category == "Research Planning"]
    assert len(planning) >= 18
    titles = {page.title for page in planning}
    assert "Biostatistics, Power & Experimental Design Studio" in titles
    assert "Synthetic Cohort & Trial Simulation Lab" in titles
    assert {module.title for module in PLANNING_MODULES}.issubset(titles)
    root = Path(__file__).resolve().parents[1]
    assert all((root / page.path).exists() for page in planning)
