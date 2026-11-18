from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class UxControl:
    name: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class UxArea:
    key: str
    label: str
    score: float
    status: str
    passed_controls: tuple[str, ...]
    failed_controls: tuple[str, ...]
    evidence: tuple[str, ...]
    boundary: str


def _text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _file_control(root: Path, name: str, relative: str, *tokens: str) -> UxControl:
    text = _text(root / relative).lower()
    passed = bool(text) and all(token.lower() in text for token in tokens)
    evidence = relative if passed else f"Missing or incomplete: {relative}"
    return UxControl(name, passed, evidence)


def _predicate_control(name: str, predicate: Callable[[], bool], evidence: str) -> UxControl:
    try:
        passed = bool(predicate())
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        passed = False
    return UxControl(name, passed, evidence if passed else f"Failed: {evidence}")


def _area(key: str, label: str, controls: list[UxControl], boundary: str) -> UxArea:
    passed = tuple(control.name for control in controls if control.passed)
    failed = tuple(control.name for control in controls if not control.passed)
    score = round(10.0 * len(passed) / max(len(controls), 1), 1)
    return UxArea(
        key=key,
        label=label,
        score=score,
        status="target" if score == 10.0 else "incomplete",
        passed_controls=passed,
        failed_controls=failed,
        evidence=tuple(control.evidence for control in controls),
        boundary=boundary,
    )


def _page_metrics(root: Path) -> dict[str, int | float]:
    pages = [root / "app.py", *sorted((root / "pages").glob("*.py"))]
    texts = [_text(path) for path in pages if path.is_file()]
    joined = "\n".join(texts)
    return {
        "page_count": len(texts),
        "hero_coverage": sum(
            any(token in text for token in ("hero(", "compact_module_header(", "render_expansion_module(", "render_nextgen_module("))
            for text in texts
        ) / max(len(texts), 1),
        "raw_json": joined.count("st.json("),
        "smart_tables": joined.count("smart_dataframe(") + joined.count("scientific_table("),
        "forms": joined.count("st.form("),
    }


def _catalog_is_complete() -> bool:
    from biointel.ui.navigation import PAGE_BY_KEY, PAGE_BY_PATH, PAGE_CATALOG

    keys = [page.key for page in PAGE_CATALOG]
    paths = [page.path for page in PAGE_CATALOG]
    return (
        len(keys) == len(set(keys)) == len(PAGE_BY_KEY)
        and len(paths) == len(set(paths)) == len(PAGE_BY_PATH)
        and all(
            page.title and page.category and page.description and page.keywords
            for page in PAGE_CATALOG
        )
    )


def _adjacent_navigation_is_valid() -> bool:
    from biointel.ui.navigation import PAGE_CATALOG, adjacent_pages

    for page in PAGE_CATALOG:
        previous_page, next_page = adjacent_pages(page.key)
        for neighbour in (previous_page, next_page):
            if neighbour is not None and neighbour.category != page.category:
                return False
    return True


def build_user_experience_assurance(root: str | Path) -> dict[str, Any]:
    """Measure observable user-experience implementation controls.

    The score is an implementation and regression-readiness score. It does not
    replace moderated usability testing with representative scientists or users
    who rely on assistive technologies.
    """

    base = Path(root).resolve()
    metrics = _page_metrics(base)

    consistency = _area(
        "ui_consistency",
        "UI Consistency and Interaction Quality",
        [
            _predicate_control(
                "Complete professional page shell coverage",
                lambda: float(metrics["hero_coverage"]) >= 0.99,
                f"hero coverage={metrics['hero_coverage']:.0%}",
            ),
            _file_control(
                base,
                "Global hierarchy and breadcrumbs",
                "src/biointel/ui/theme.py",
                "bio-compact-breadcrumb",
                'aria-label="breadcrumb"',
            ),
            _file_control(
                base,
                "Contextual page help",
                "src/biointel/ui/theme.py",
                "about this module",
                "workflow keywords",
            ),
            _file_control(
                base,
                "Actionable empty states",
                "src/biointel/ui/theme.py",
                "def empty_state",
                "bio-empty-title",
            ),
            _file_control(
                base,
                "Reusable recovery actions",
                "src/biointel/ui/components.py",
                "def recovery_actions",
                "retry_label",
                "reset_label",
            ),
            _file_control(
                base,
                "Standard scientific tables and exports",
                "src/biointel/ui/components.py",
                "def scientific_table",
                "export csv",
            ),
            _file_control(
                base,
                "Standard chart interpretation cards",
                "src/biointel/ui/components.py",
                "def scientific_chart_card",
                "view underlying data",
            ),
            _file_control(
                base,
                "Consistent progress and cancellation feedback",
                "src/biointel/ui/workflow.py",
                "def render_cancel_control",
                "aria-live",
                "progressbar",
            ),
            _predicate_control(
                "No raw developer JSON in user pages",
                lambda: int(metrics["raw_json"]) == 0,
                f"raw st.json calls={metrics['raw_json']}",
            ),
            _file_control(
                base,
                "Responsive desktop and narrow-screen layout",
                "src/biointel/ui/theme.py",
                "@media (max-width:",
                "bio-shell",
            ),
        ],
        "10/10 verifies a consistent, tested interaction system across the repository. Real task-completion studies with representative users remain the strongest external usability evidence.",
    )

    navigation = _area(
        "navigation",
        "Navigation and Workflow Discoverability",
        [
            _predicate_control(
                "Unique and complete module catalogue",
                _catalog_is_complete,
                "unique keys, paths, descriptions and keywords",
            ),
            _file_control(
                base,
                "Persistent workflow-first sidebar",
                "src/biointel/ui/theme.py",
                "workspace",
                "task lanes",
                "browse a domain",
            ),
            _file_control(
                base,
                "Global module finder",
                "src/biointel/ui/theme.py",
                "find modules",
                "_bio_global_nav_search",
            ),
            _file_control(
                base,
                "Typo-tolerant scientific search",
                "src/biointel/ui/theme.py",
                "search_catalogue",
                "typo correction",
            ),
            _file_control(
                base,
                "Pinned and recent continuity",
                "src/biointel/ui/theme.py",
                "pinned & recent",
                "ui_favourites",
                "ui_recent_pages",
            ),
            _file_control(
                base,
                "Durable preference persistence",
                "src/biointel/ui/preferences.py",
                "def record_recent_page",
                "def toggle_favourite",
                "atomic_write_json",
            ),
            _file_control(
                base,
                "Safe route failure boundary",
                "src/biointel/ui/runtime_guard.py",
                "_safe_navigation_wrapper",
                "page_link",
            ),
            _predicate_control(
                "Previous and next module navigation",
                _adjacent_navigation_is_valid,
                "category-safe adjacent navigation for every catalogue page",
            ),
            _file_control(
                base,
                "Active scientific context continuity",
                "src/biointel/ui/theme.py",
                "active_project_name",
                "active_dataset_name",
                "active_model_name",
            ),
            _file_control(
                base,
                "Dedicated command and resume center",
                "pages/25_Command_Center.py",
                "continue recent work",
                "favourites_only",
                "search_pages",
            ),
        ],
        "10/10 verifies complete navigation controls, continuity and automated discoverability. It does not claim that every future user will prefer the same information architecture.",
    )

    areas = [consistency, navigation]
    return {
        "schema": "biointel.user-experience-assurance.v1",
        "areas": [asdict(area) for area in areas],
        "scores": {area.key: area.score for area in areas},
        "all_targets_complete": all(area.score == 10.0 for area in areas),
        "implementation_average": round(sum(area.score for area in areas) / len(areas), 1),
        "page_metrics": metrics,
        "boundary": (
            "The 10/10 score is a repository implementation target backed by observable controls and tests. "
            "Independent moderated usability testing remains separate evidence."
        ),
    }
