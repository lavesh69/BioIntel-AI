from __future__ import annotations

import ast
from pathlib import Path

from biointel.ui.navigation import (
    PAGE_BY_KEY,
    SIDEBAR_PRIMARY,
    SIDEBAR_WORK_MODES,
    WORKFLOW_GROUPS,
)

ROOT = Path(__file__).resolve().parents[1]


def test_step45_sidebar_is_intentionally_concise() -> None:
    assert len(SIDEBAR_PRIMARY) == 4
    assert len(SIDEBAR_WORK_MODES) == 4
    assert all(key in PAGE_BY_KEY for key in SIDEBAR_PRIMARY)
    assert all(key in PAGE_BY_KEY for key, _ in SIDEBAR_WORK_MODES)


def test_step45_workflows_are_grouped_by_user_task() -> None:
    assert tuple(WORKFLOW_GROUPS) == (
        "Start & plan",
        "Data & evidence",
        "Bioinformatics",
        "Discovery & lab",
        "AI & validation",
        "Operations & release",
    )
    for keys in WORKFLOW_GROUPS.values():
        assert keys
        assert all(key in PAGE_BY_KEY for key in keys)


def test_step45_global_shell_has_distributed_controls() -> None:
    theme = (ROOT / "src" / "biointel" / "ui" / "theme.py").read_text(encoding="utf-8")
    assert "Step 45 distributed application shell" in theme
    assert "⌕ Find a workspace" in theme
    assert "⚙ Settings" in theme
    assert "Browse by category" in theme
    assert "Search all modules from the centre" in theme


def test_step45_home_hubs_only_reference_valid_pages() -> None:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "workspace_hubs" for target in node.targets)
    )
    hubs = ast.literal_eval(assignment.value)
    assert tuple(hubs) == (
        "Analyze",
        "Data & knowledge",
        "AI & discovery",
        "Validate & release",
        "Operate",
    )
    keys = [item[0] for entries in hubs.values() for item in entries]
    assert len(keys) == 30
    assert len(set(keys)) == 30
    assert all(key in PAGE_BY_KEY for key in keys)
