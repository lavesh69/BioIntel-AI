from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import biointel.ui.non_chart_scientific_visuals as visuals

ROOT = Path(__file__).resolve().parents[1]


def test_non_chart_css_is_emitted_on_every_rerun(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    def markdown(body: str, *, unsafe_allow_html: bool = False, **_: object) -> None:
        calls.append((body, unsafe_allow_html))

    monkeypatch.setattr(visuals, "st", SimpleNamespace(markdown=markdown))
    visuals._inject_css()
    visuals._inject_css()

    assert len(calls) == 2
    assert all(unsafe for _, unsafe in calls)
    assert all('id="biointel-non-chart-scientific-visuals-v2"' in body for body, _ in calls)


def test_non_chart_css_does_not_use_session_level_loaded_flag() -> None:
    source = (ROOT / "src/biointel/ui/non_chart_scientific_visuals.py").read_text(encoding="utf-8")
    assert "_step115_non_chart_css_loaded" not in source
    assert ".nc-shell{display:block!important" in source
    assert ".nc-grid{display:grid!important" in source
    assert ".nc-lane{display:block!important" in source
    assert ".nc-seg{display:block!important" in source


def test_track_and_card_markup_keep_separate_semantic_blocks() -> None:
    lane = visuals._lane("Variants", [(12, 3, "V1", "warn"), (44, 3, "V2", "alt")])
    cards = visuals._cards((("Selected evidence", "EGFR exon 18"), ("Tracks visible", "3")))

    assert '<div class="nc-lane">' in lane
    assert lane.count('class="nc-seg') == 2
    assert '<div class="nc-grid">' in cards
    assert cards.count('class="nc-card"') == 2
