from __future__ import annotations

import re
from pathlib import Path

from biointel.connected.providers import PROVIDERS
from biointel.contextual_research_v196.catalog import (
    ALL_MAJOR_MODULE_KEYS,
    MODULE_RESEARCH_PROFILES,
    TOP_WEBSITE_ELIGIBLE_MODULE_KEYS,
    has_relevant_top_websites,
    provider_query_url,
)

ROOT = Path(__file__).resolve().parents[1]
HOOK = re.compile(r"_render_step196_contextual_online_research\((['\"])([^'\"]+)\1")


def test_only_scientifically_relevant_modules_render_top_websites() -> None:
    assert len(TOP_WEBSITE_ELIGIBLE_MODULE_KEYS) == 61
    assert TOP_WEBSITE_ELIGIBLE_MODULE_KEYS < set(ALL_MAJOR_MODULE_KEYS)
    assert all(has_relevant_top_websites(key) for key in TOP_WEBSITE_ELIGIBLE_MODULE_KEYS)
    assert not has_relevant_top_websites("background_job_engine")
    assert not has_relevant_top_websites("store_readiness_core")
    assert not has_relevant_top_websites("plugin_marketplace_v2")
    assert not has_relevant_top_websites("synthetic_data_privacy")


def test_all_historical_hooks_are_at_the_top_after_apply_theme() -> None:
    hooks: list[str] = []
    page_files = 0
    for page in sorted((ROOT / "pages").glob("*.py")):
        text = page.read_text(encoding="utf-8")
        matches = list(HOOK.finditer(text))
        if not matches:
            continue
        page_files += 1
        lines = text.splitlines()
        apply_line = next(i for i, line in enumerate(lines) if line.strip() == "apply_theme()")
        hook_lines = [text[:match.start()].count("\n") for match in matches]
        assert min(hook_lines) > apply_line
        assert min(hook_lines) <= apply_line + 6
        # No second/bottom copy of the hook is allowed.
        assert max(hook_lines) <= apply_line + 8
        hooks.extend(match.group(2) for match in matches)
    assert page_files == 79
    assert len(hooks) == 80
    assert set(hooks) == set(ALL_MAJOR_MODULE_KEYS)


def test_relevant_modules_have_only_official_contextual_provider_links() -> None:
    for module_key in TOP_WEBSITE_ELIGIBLE_MODULE_KEYS:
        profile = MODULE_RESEARCH_PROFILES[module_key]
        assert 2 <= len(profile.providers) <= 7
        for provider in profile.providers:
            assert provider in PROVIDERS
            entity_type = profile.entity_type_for(provider)
            url = provider_query_url(provider, "TP53", entity_type)
            assert url.startswith("https://")


def test_ncbi_links_are_entity_specific() -> None:
    assert "pubmed.ncbi.nlm.nih.gov" in provider_query_url("ncbi", "TP53", "literature")
    assert "/clinvar/" in provider_query_url("ncbi", "TP53", "variant")
    assert "/gds/" in provider_query_url("ncbi", "TP53", "expression study")
    assert "/nuccore/" in provider_query_url("ncbi", "TP53", "sequence")
