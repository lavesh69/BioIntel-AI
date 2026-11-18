from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from biointel.ui.module_experience_2_9 import GROUP_LABELS, MODULE_EXPERIENCE_CATALOG
from biointel.ui.navigation import PAGE_BY_PATH, PAGE_CATALOG, PageDefinition
from biointel.ui.search_quality import score_search_candidate


_EXPERIENCE_PATTERN = re.compile(r'_render_step116_module_experience\(\s*["\']([^"\']+)["\']')


@dataclass(frozen=True)
class CatalogueItem:
    key: str
    title: str
    item_type: str
    category: str
    icon: str
    description: str
    keywords: tuple[str, ...]
    page_key: str
    page_path: str
    page_title: str
    enhanced_workspace: bool = False
    auto_discovered: bool = False


@dataclass(frozen=True)
class CatalogueMatch:
    item: CatalogueItem
    score: float
    corrected_query: str
    reasons: tuple[str, ...]


@lru_cache(maxsize=4)
def experience_parent_map(project_root_text: str) -> dict[str, PageDefinition]:
    root = Path(project_root_text).resolve()
    mapping: dict[str, PageDefinition] = {}
    for page_file in sorted((root / "pages").glob("*.py")):
        page = PAGE_BY_PATH.get(page_file.relative_to(root).as_posix())
        if page is None:
            continue
        try:
            source = page_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for experience_key in _EXPERIENCE_PATTERN.findall(source):
            mapping.setdefault(experience_key, page)
    return mapping


@lru_cache(maxsize=4)
def complete_catalogue(project_root_text: str) -> tuple[CatalogueItem, ...]:
    root = Path(project_root_text).resolve()
    parent_map = experience_parent_map(str(root))
    enhanced_pages = {page.key for page in parent_map.values()}
    items: list[CatalogueItem] = []

    for page in PAGE_CATALOG:
        items.append(
            CatalogueItem(
                key=f"page:{page.key}",
                title=page.title,
                item_type="Module page",
                category=page.category,
                icon=page.icon,
                description=page.description,
                keywords=page.keywords,
                page_key=page.key,
                page_path=page.path,
                page_title=page.title,
                enhanced_workspace=page.key in enhanced_pages,
                auto_discovered=page.key.startswith("auto_"),
            )
        )

    for experience_key, spec in MODULE_EXPERIENCE_CATALOG.items():
        parent = parent_map.get(experience_key)
        if parent is None:
            # Keep the capability searchable even if a future injector forgets to
            # mount it.  The catalogue will label it as unlinked rather than hide it.
            items.append(
                CatalogueItem(
                    key=f"workspace:{experience_key}",
                    title=spec.title,
                    item_type="Embedded workspace",
                    category=GROUP_LABELS.get(spec.group, spec.group),
                    icon=spec.icon,
                    description=spec.primary_canvas,
                    keywords=(
                        experience_key.replace("_", " "),
                        spec.entity_type,
                        *spec.workflow,
                        *spec.handoffs,
                    ),
                    page_key="",
                    page_path="",
                    page_title="Not linked",
                    enhanced_workspace=True,
                )
            )
            continue
        items.append(
            CatalogueItem(
                key=f"workspace:{experience_key}",
                title=spec.title,
                item_type="Embedded workspace",
                category=GROUP_LABELS.get(spec.group, parent.category),
                icon=spec.icon,
                description=spec.primary_canvas,
                keywords=(
                    experience_key.replace("_", " "),
                    spec.entity_type,
                    *spec.workflow,
                    *spec.handoffs,
                    parent.title,
                    parent.category,
                ),
                page_key=parent.key,
                page_path=parent.path,
                page_title=parent.title,
                enhanced_workspace=True,
            )
        )

    # Stable ordering: real pages first by product domain, then embedded workspaces.
    items.sort(key=lambda item: (item.item_type != "Module page", item.category, item.title))
    return tuple(items)


def catalogue_counts(project_root: str | Path) -> dict[str, int]:
    items = complete_catalogue(str(Path(project_root).resolve()))
    page_items = [item for item in items if item.item_type == "Module page"]
    workspaces = [item for item in items if item.item_type == "Embedded workspace"]
    linked = [item for item in workspaces if item.page_path]
    return {
        "module_pages": len(page_items),
        "embedded_workspaces": len(workspaces),
        "linked_workspaces": len(linked),
        "total_searchable_items": len(items),
        "enhanced_pages": len({item.page_key for item in workspaces if item.page_key}),
        "auto_discovered_pages": sum(item.auto_discovered for item in page_items),
    }


def search_catalogue(
    project_root: str | Path,
    query: str = "",
    *,
    categories: Iterable[str] | None = None,
    item_types: Iterable[str] | None = None,
    enhanced_only: bool = False,
    sort_mode: str = "Relevance",
) -> list[CatalogueMatch]:
    normalized_query = " ".join(query.strip().lower().split())
    category_filter = {value for value in (categories or ()) if value}
    type_filter = {value for value in (item_types or ()) if value}
    matches: list[CatalogueMatch] = []

    for item in complete_catalogue(str(Path(project_root).resolve())):
        if category_filter and item.category not in category_filter:
            continue
        if type_filter and item.item_type not in type_filter:
            continue
        if enhanced_only and not item.enhanced_workspace:
            continue
        detail = score_search_candidate(
            normalized_query,
            title=item.title,
            description=item.description,
            category=item.category,
            keywords=item.keywords,
            key=item.key,
        )
        if normalized_query and detail.score < 2.15:
            continue
        matches.append(
            CatalogueMatch(
                item=item,
                score=detail.score,
                corrected_query=detail.corrected_query,
                reasons=detail.reasons,
            )
        )

    if sort_mode == "A–Z":
        matches.sort(key=lambda match: (match.item.title.lower(), match.item.item_type))
    elif sort_mode == "Domain":
        matches.sort(key=lambda match: (match.item.category, match.item.title.lower()))
    elif sort_mode == "Newest first":
        def page_number(item: CatalogueItem) -> int:
            match = re.search(r"pages/(\d+)_", item.page_path)
            return int(match.group(1)) if match else -1
        matches.sort(key=lambda match: (-page_number(match.item), match.item.title.lower()))
    else:
        matches.sort(
            key=lambda match: (
                -match.score if normalized_query else 0,
                match.item.item_type != "Module page",
                match.item.category,
                match.item.title.lower(),
            )
        )
    return matches
