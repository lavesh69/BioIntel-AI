from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.brand import (  # noqa: E402
    BRAND,
    COMPACT_MODULE_NAMES,
    PRODUCT_FAMILIES,
    about_brand_html,
    brand_header_html,
    brand_mark_svg,
    brand_trust_strip_html,
    compact_module_name,
)
from biointel.ui.style_catalog import DEFAULT_THEME, THEMES  # noqa: E402


def test_primary_brand_identity_and_tagline_are_locked() -> None:
    assert BRAND.name == "BioIntel AI"
    assert BRAND.descriptor == "Scientific Intelligence for Life Sciences"
    assert BRAND.tagline == "Biology, Engineered into Intelligence."
    assert BRAND.primary == "#22D3EE"
    assert BRAND.secondary == "#3B82F6"
    assert BRAND.accent == "#8B5CF6"
    assert DEFAULT_THEME == "BioIntel Signature"
    assert DEFAULT_THEME in THEMES


def test_founder_credit_is_professionally_scoped() -> None:
    assert BRAND.founder not in brand_header_html("13.6.0")
    assert BRAND.founder in about_brand_html("13.6.0")


def test_logo_variants_and_brand_assets_are_valid() -> None:
    for variant in ("full", "white", "dark", "mono"):
        ET.fromstring(brand_mark_svg(size=64, variant=variant))
    required = [
        ROOT / "brand/BRAND_GUIDELINES.md",
        ROOT / "brand/BIOINTEL_BRAND_GUIDELINES.pdf",
        ROOT / "brand/colors.json",
        ROOT / "brand/typography.json",
        ROOT / "brand/product_architecture.json",
        ROOT / "brand/design_tokens.css",
        ROOT / "brand/logo/biointel-ai-full.svg",
        ROOT / "brand/logo/biointel-ai-white.svg",
        ROOT / "brand/logo/biointel-ai-dark.svg",
        ROOT / "brand/logo/biointel-ai-favicon.svg",
        ROOT / "brand/store_assets/SCREENSHOT_STORYBOARD.md",
        ROOT / "brand/report_templates/report_cover.html",
    ]
    assert all(path.is_file() and path.stat().st_size > 0 for path in required)


def test_product_architecture_and_compact_naming_are_present() -> None:
    assert len(PRODUCT_FAMILIES) == 7
    assert {item.label for item in PRODUCT_FAMILIES} == {
        "BioIntel Genomics",
        "BioIntel Discovery",
        "BioIntel Lab",
        "BioIntel Omics",
        "BioIntel Models",
        "BioIntel Evidence",
        "BioIntel Operations",
    }
    assert COMPACT_MODULE_NAMES["protein_design_lab"] == "Protein Design Lab"
    assert compact_module_name("pangenome_graph", "fallback") == "Pangenome Graph Studio"


def test_trust_strip_and_brand_manifest_use_approved_language() -> None:
    strip = brand_trust_strip_html()
    for phrase in ("Evidence level", "Confidence", "Dataset status", "Model status"):
        assert phrase in strip
    manifest = json.loads((ROOT / "assets/brand/brand-manifest.json").read_text())
    assert manifest["tagline"] == BRAND.tagline
    assert manifest["descriptor"] == BRAND.descriptor
    assert "add glow" in manifest["logo_rules"]["do_not"]


def test_no_legacy_tagline_remains_in_product_text_assets() -> None:
    legacy = "Inspired by Biology." + " Powered by AI."
    extensions = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".html", ".svg", ".ts", ".js", ".css"}
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if legacy in text:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders
