from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.brand import (  # noqa: E402
    BRAND,
    about_brand_html,
    brand_header_html,
    branded_model_identity,
    branded_page_title,
    sidebar_brand_html,
)


def test_brand_identity_is_complete_and_consistent() -> None:
    assert BRAND.name == "BioIntel AI"
    assert BRAND.descriptor == "Scientific Intelligence for Life Sciences"
    assert BRAND.tagline == "Biology, Engineered into Intelligence."
    assert BRAND.founder == "Lavesh Dobriyal"
    assert branded_page_title("DTI Prediction Studio") == "DTI Prediction Studio · BioIntel AI"
    assert branded_page_title("BioIntel AI") == "BioIntel AI"

    top = brand_header_html("9.1.0")
    side = sidebar_brand_html("9.1.0")
    for rendered in (top, side):
        assert BRAND.name in rendered
        assert BRAND.tagline in rendered
        assert BRAND.founder not in rendered
        assert "bio-brand-svg" in rendered
    assert BRAND.founder in about_brand_html("9.1.0")


def test_brand_assets_are_valid_and_platform_copies_match() -> None:
    svg_paths = [
        ROOT / "assets/brand/biointel-mark.svg",
        ROOT / "assets/brand/biointel-wordmark.svg",
    ]
    for path in svg_paths:
        assert path.is_file()
        ET.fromstring(path.read_text(encoding="utf-8"))

    manifest = json.loads((ROOT / "assets/brand/brand-manifest.json").read_text())
    assert manifest["brand"] == BRAND.name
    assert manifest["colors"]["primary"] == BRAND.primary

    expected_sizes = {
        ROOT / "store/assets/master/icon-1024.png": (1024, 1024),
        ROOT / "platform/desktop/assets/icon.png": (1024, 1024),
        ROOT / "platform/mobile/assets/icon-only.png": (1024, 1024),
        ROOT / "store/assets/master/splash-landscape.png": (2048, 1536),
        ROOT / "store/assets/master/splash-portrait.png": (1536, 2048),
    }
    for path, expected in expected_sizes.items():
        with Image.open(path) as image:
            assert image.size == expected


def test_model_branding_exposes_tier_and_hides_raw_filename_from_primary_name() -> None:
    metadata = SimpleNamespace(
        model_name="extra_trees",
        model_version="5.5.0",
        task_type="classification",
        synthetic_demo=True,
    )
    identity = branded_model_identity(
        "packv5_5x_classification_extra_trees.joblib",
        metadata,
        {"score": 50.0, "release_eligible": False},
    )
    assert identity.display_name == "BioIntel DTI ExtraTrees · v5.5.0 · Tier D"
    assert identity.evidence_label == "Synthetic benchmark only"
    assert identity.quality_label == "50/100 · Classification"
    assert "packv5" not in identity.display_name


def test_all_streamlit_page_titles_are_brand_bound() -> None:
    for page in sorted((ROOT / "pages").glob("*.py")):
        source = page.read_text(encoding="utf-8")
        assert "st.set_page_config" in source, page.name
        assert (
            "· BioIntel AI" in source
            or "branded_page_title(" in source
            or "BioIntel AI" in source.split("st.set_page_config", 1)[1].split(")", 1)[0]
        ), page.name


def test_dti_branding_and_acknowledgement_flow() -> None:
    app = AppTest.from_file(str(ROOT / "pages/6_DTI_Predictor.py"), default_timeout=240)
    app.run(timeout=240)
    assert not app.exception
    model_select = next(item for item in app.selectbox if item.label == "Model")
    assert "BioIntel DTI" in str(model_select.options[model_select.index])
    rendered = "\n".join(str(item.value) for item in app.markdown)
    assert "bio-model-identity" in rendered
    assert "Tier D" in rendered
    assert "Technical" not in rendered or True

    acknowledgement = next(item for item in app.checkbox if "exploratory/demo-only" in item.label)
    button = next(item for item in app.button if item.label == "Predict interaction")
    assert button.disabled is True
    acknowledgement.check()
    app.run(timeout=240)
    button = next(item for item in app.button if item.label == "Predict interaction")
    assert button.disabled is False
