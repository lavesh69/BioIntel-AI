from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from biointel.connected.providers import PROVIDERS
from biointel.contextual_research_v196.catalog import (
    ALL_MAJOR_MODULE_KEYS,
    MODULE_RESEARCH_PROFILES,
    TOP_WEBSITE_ELIGIBLE_MODULE_KEYS,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: object) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add("80 explicit contextual profiles", len(MODULE_RESEARCH_PROFILES) == 80, len(MODULE_RESEARCH_PROFILES))
    invalid = {
        key: [provider for provider in profile.providers if provider not in PROVIDERS]
        for key, profile in MODULE_RESEARCH_PROFILES.items()
        if any(provider not in PROVIDERS for provider in profile.providers)
    }
    add("provider catalogue references", not invalid, invalid or "all valid")

    pattern = re.compile(r"_render_step196_contextual_online_research\((['\"])([^'\"]+)\1")
    pages = 0
    hooks: list[str] = []
    for path in (ROOT / "pages").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        found = [match.group(2) for match in pattern.finditer(text)]
        if found:
            pages += 1
            hooks.extend(found)
    add("79 integrated page files", pages == 79, pages)
    add("80 unique logical module hooks", len(hooks) == 80 and len(set(hooks)) == 80, {"hooks": len(hooks), "unique": len(set(hooks))})
    add("catalog and page hook match", set(hooks) == set(ALL_MAJOR_MODULE_KEYS), {"missing": sorted(set(ALL_MAJOR_MODULE_KEYS) - set(hooks)), "extra": sorted(set(hooks) - set(ALL_MAJOR_MODULE_KEYS))})
    add("61 relevant top website modules", len(TOP_WEBSITE_ELIGIBLE_MODULE_KEYS) == 61, len(TOP_WEBSITE_ELIGIBLE_MODULE_KEYS))

    top_failures: list[str] = []
    for path in (ROOT / "pages").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        found = list(pattern.finditer(text))
        if not found:
            continue
        lines = text.splitlines()
        try:
            apply_line = next(index for index, line in enumerate(lines) if line.strip() == "apply_theme()")
        except StopIteration:
            top_failures.append(f"{path.name}:apply_theme-missing")
            continue
        hook_lines = [text[:match.start()].count("\n") for match in found]
        if min(hook_lines) <= apply_line or max(hook_lines) > apply_line + 8:
            top_failures.append(f"{path.name}:hooks={hook_lines}:apply={apply_line}")
    add("website hooks positioned at module top", not top_failures, top_failures or "79/79 page files")

    required = [
        ROOT / "src/biointel/contextual_research_v196/catalog.py",
        ROOT / "src/biointel/contextual_research_v196/service.py",
        ROOT / "src/biointel/contextual_research_v196/ui.py",
        ROOT / "src/biointel/connected/free_web_ai.py",
    ]
    add("required implementation files", all(path.is_file() for path in required), [str(path.relative_to(ROOT)) for path in required if not path.is_file()] or "complete")

    passed = all(bool(row["passed"]) for row in checks)
    payload = {
        "schema": "biointel.step196.contextual-online-research-self-test.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": passed,
        "checks": checks,
    }
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
