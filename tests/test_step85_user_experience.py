from __future__ import annotations

from pathlib import Path

from biointel.quality.scorecard import build_quality_scorecard
from biointel.quality.ux_assurance import build_user_experience_assurance
from biointel.ui.navigation import PAGE_CATALOG, adjacent_pages

ROOT = Path(__file__).resolve().parents[1]


def test_step85_user_experience_controls_score_ten() -> None:
    report = build_user_experience_assurance(ROOT)
    assert report["all_targets_complete"] is True
    assert report["implementation_average"] == 10.0
    assert report["scores"] == {"ui_consistency": 10.0, "navigation": 10.0}
    assert all(not area["failed_controls"] for area in report["areas"])


def test_step85_quality_scorecard_user_experience_group_is_ten() -> None:
    report = build_quality_scorecard(ROOT)
    assert report["group_scores"]["User experience"] == 10.0
    dimensions = {
        item["key"]: item for item in report["dimensions"] if item["group"] == "User experience"
    }
    assert set(dimensions) == {
        "ui_consistency",
        "frontend_performance",
        "navigation",
        "accessibility",
    }
    assert all(item["score"] == 10.0 for item in dimensions.values())


def test_step85_adjacent_navigation_stays_inside_domain() -> None:
    for page in PAGE_CATALOG:
        previous_page, next_page = adjacent_pages(page.key)
        for neighbour in (previous_page, next_page):
            assert neighbour is None or neighbour.category == page.category
