from pathlib import Path

from biointel.ui.brand import BRAND, home_founder_credit_html


def test_home_founder_credit_contains_public_name() -> None:
    html = home_founder_credit_html()
    assert BRAND.founder == "Lavesh Dobriyal"
    assert "Created &amp; Developed by" in html
    assert "Lavesh Dobriyal" in html


def test_home_renders_founder_credit_inside_primary_hero() -> None:
    app_source = Path("app.py").read_text(encoding="utf-8")
    assert "home_founder_credit_html" in app_source
    assert "st.markdown(home_founder_credit_html(), unsafe_allow_html=True)" in app_source
    assert 'eyebrow=f"{BRAND.name} · Created & Developed by {BRAND.founder}"' in app_source
    assert 'f"Created by {BRAND.founder}"' in app_source


def test_module_finder_uses_brand_svg_icons_not_legacy_emoji() -> None:
    source = Path("src/biointel/ui/theme.py").read_text(encoding="utf-8")
    start = source.index('with st.popover("⌕  Find modules · Ctrl K"')
    end = source.index("# Step 125:", start)
    finder = source[start:end]
    assert "finder_icon = svg_icon_html(" in finder
    assert 'css_class="bio-svg-icon bio-finder-result-svg"' in finder
    assert "bio-finder-result-icon" in finder
    assert "icon=item.icon" not in finder
    assert 'f"{item.icon} {item.title}"' not in finder
