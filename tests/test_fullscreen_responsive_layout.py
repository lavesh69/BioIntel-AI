from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_global_responsive_shell_is_loaded_after_visual_layers() -> None:
    source = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")

    assert "responsive_layout.css" in source
    assert source.index("premium_visuals.css") < source.index("responsive_layout.css")
    assert "st.components.v2.component(" in source
    assert 'window.dispatchEvent(new Event("resize"))' in source
    assert "ResizeObserver" in source


def test_responsive_shell_releases_collapsed_sidebar_width() -> None:
    css = (ROOT / "src/biointel/ui/responsive_layout.css").read_text(encoding="utf-8")

    required_tokens = (
        "--bio-sidebar-expanded-width",
        "--bio-sidebar-current-width",
        "--bio-page-gutter",
        "--bio-workspace-max-width",
        "--bio-app-header-height",
        '[data-testid="stSidebar"][aria-expanded="false"]',
        "flex: 0 0 0 !important",
        "border-right-width: 0 !important",
        '[data-testid="stMainBlockContainer"]',
        "width: 100% !important",
        "max-width: var(--bio-workspace-max-width) !important",
        ":has(.bio-shell-bar)",
        ":has(.bio-compact-breadcrumb)",
        "[data-bio-layout-observer]",
    )
    for token in required_tokens:
        assert token in css

    assert "100vw" not in css
    assert "margin-left: -" not in css
    assert 'display: block;\n  }\n\n  [data-testid="stAppViewContainer"]' not in css


def test_discovery_page_uses_global_shell_without_page_override() -> None:
    source = (ROOT / "pages/270_Discovery_Lab_Platform.py").read_text(encoding="utf-8")

    assert "apply_theme()" in source
    assert "stMainBlockContainer" not in source
    assert "width: 100vw" not in source
