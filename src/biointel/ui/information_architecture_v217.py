from __future__ import annotations

from collections import Counter
from typing import Iterable, Protocol


class PageLike(Protocol):
    key: str
    title: str
    category: str
    keywords: tuple[str, ...]


OPERATIONAL_CATEGORIES = frozenset(
    {
        "Start",
        "Data",
        "AI Lab",
        "Bioinformatics",
        "Discovery",
        "Lab Analytics",
        "Neuro/CNS",
        "Clinical Research",
        "Research Planning",
        "Documents",
        "Intelligence",
    }
)
ASSURANCE_TOKENS = frozenset(
    {
        "assurance",
        "qualification",
        "release gate",
        "readiness",
        "validation center",
        "evidence center",
        "compliance",
        "governance",
        "audit",
        "quality center",
        "external validation",
    }
)
INTERNAL_TOKENS = frozenset(
    {
        "step",
        "internal",
        "implementation report",
        "mandatory completion",
        "target module",
        "platform core",
        "module excellence",
        "quality hardening",
    }
)


def page_surface(page: PageLike) -> str:
    text = " ".join((page.key, page.title, page.category, *page.keywords)).lower()
    if page.key == "home" or page.category == "Start":
        return "Operational"
    if page.category == "Settings":
        return "Administration"
    if page.category == "Governance":
        return "Assurance"
    if any(token in text for token in INTERNAL_TOKENS):
        return "Internal"
    if any(token in text for token in ASSURANCE_TOKENS):
        return "Assurance"
    if page.category == "Operations":
        return "Platform"
    if page.category in OPERATIONAL_CATEGORIES:
        return "Operational"
    return "Internal"


def filter_pages(pages: Iterable[PageLike], view: str) -> list[PageLike]:
    selected = str(view or "Operational").strip().lower()
    if selected == "all":
        return list(pages)
    allowed = {
        "operational": {"Operational"},
        "platform": {"Platform", "Administration"},
        "assurance": {"Assurance"},
        "internal": {"Internal"},
    }.get(selected, {"Operational"})
    return [page for page in pages if page_surface(page) in allowed]


def surface_summary(pages: Iterable[PageLike]) -> dict[str, int]:
    counts = Counter(page_surface(page) for page in pages)
    return {
        "Operational": counts.get("Operational", 0),
        "Platform": counts.get("Platform", 0),
        "Assurance": counts.get("Assurance", 0),
        "Administration": counts.get("Administration", 0),
        "Internal": counts.get("Internal", 0),
        "Total": sum(counts.values()),
    }
