from __future__ import annotations

import inspect
import re
from pathlib import Path

from biointel.connected.free_web_ai import FreeWebCopilot
from biointel.connected.providers import PROVIDERS
from biointel.contextual_research_v196.catalog import (
    ALL_MAJOR_MODULE_KEYS,
    MODULE_RESEARCH_PROFILES,
    provider_query_url,
)

ROOT = Path(__file__).resolve().parents[1]


def test_all_80_major_modules_have_explicit_profiles() -> None:
    assert len(ALL_MAJOR_MODULE_KEYS) == 80
    assert len(set(ALL_MAJOR_MODULE_KEYS)) == 80
    assert set(MODULE_RESEARCH_PROFILES) == set(ALL_MAJOR_MODULE_KEYS)


def test_every_profile_has_contextual_official_providers() -> None:
    for key, profile in MODULE_RESEARCH_PROFILES.items():
        assert profile.module_key == key
        assert profile.research_focus
        assert profile.query_hint
        assert len(profile.providers) >= 2
        assert len(set(profile.providers)) == len(profile.providers)
        assert set(profile.providers).issubset(PROVIDERS)
        assert all(profile.entity_type_for(provider) for provider in profile.providers)
        assert len(profile.quick_queries) == 3


def test_all_provider_website_links_are_safe_https() -> None:
    for profile in MODULE_RESEARCH_PROFILES.values():
        for provider in profile.providers:
            url = provider_query_url(provider, "TP53 p.R175H")
            assert url.startswith("https://")
            assert "TP53" in url or provider in {"rcsb", "string"}


def test_all_80_module_hooks_are_embedded_in_79_pages() -> None:
    hook_pattern = re.compile(r"_render_step196_contextual_online_research\((['\"])([^'\"]+)\1")
    page_count = 0
    hooked: list[str] = []
    for page in sorted((ROOT / "pages").glob("*.py")):
        text = page.read_text(encoding="utf-8")
        keys = [match.group(2) for match in hook_pattern.finditer(text)]
        if keys:
            page_count += 1
            assert "STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK" in text
            hooked.extend(keys)
    assert page_count == 79
    assert len(hooked) == 80
    assert set(hooked) == set(ALL_MAJOR_MODULE_KEYS)
    assert len(hooked) == len(set(hooked))


def test_free_web_copilot_supports_per_provider_entity_types() -> None:
    signature = inspect.signature(FreeWebCopilot.run)
    assert "provider_entity_types" in signature.parameters
