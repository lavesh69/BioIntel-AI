from pathlib import Path

import numpy as np
import pandas as pd

from biointel.ui.domain_visual_peak import (
    EXCLUDED_CATEGORIES,
    FAMILY_TEMPLATES,
    _bounded_frame,
    _demo_frame,
    _figure,
    family_for,
    specs_for,
)
from biointel.ui.navigation import PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]
MARKER = "# STEP136_NON_AI_VISUAL_PEAK_SUITE"
NATIVE_VISUAL_RENDERERS = (
    "render_nextgen_module(",
    "render_neuro_cns_studio(",
    "render_feature_center(",
    "render_synthetic_demo_workspace(",
    "from biointel.discovery_platform.service import DiscoveryPlatformService",
)


def test_requested_scope_contains_all_non_excluded_modules() -> None:
    targets = [page for page in PAGE_CATALOG if page.category not in EXCLUDED_CATEGORIES]
    assert len(targets) >= 143  # additive releases may introduce further non-excluded modules
    assert {page.category for page in targets}.isdisjoint(EXCLUDED_CATEGORIES)


def test_each_target_module_has_exactly_five_domain_visuals() -> None:
    for page in PAGE_CATALOG:
        if page.category in EXCLUDED_CATEGORIES:
            continue
        assert len(specs_for(page.key, page.title, page.category)) == 5


def test_legacy_pages_are_augmented_and_nextgen_pages_keep_native_visuals() -> None:
    for page in PAGE_CATALOG:
        path = ROOT / page.path
        text = path.read_text(encoding="utf-8")
        if page.category in EXCLUDED_CATEGORIES:
            assert MARKER not in text
            continue
        if any(renderer in text for renderer in NATIVE_VISUAL_RENDERERS):
            assert MARKER not in text
        else:
            assert MARKER in text


def test_each_visual_family_builds_without_error() -> None:
    for family, visuals in FAMILY_TEMPLATES.items():
        frame = _demo_frame(f"test_{family}", family, 72)
        for visual in visuals:
            figure, source = _figure(visual, frame, f"test_{family}", family)
            assert figure is not None
            assert source is not None
            assert len(source) > 0


def test_family_assignment_is_stable() -> None:
    expected = {
        "fastq_genomics_qc": "fastq",
        "variant_annotation": "variant",
        "transcriptomics_expression": "transcriptomics",
        "structural_bioinformatics": "structure",
        "wetlab_biotechnology": "lab_assay",
        "metagenomics_pipeline": "microbiome",
        "gene_therapy_vector": "therapy",
        "document_intelligence": "document",
        "knowledge_graph_copilot": "knowledge",
        "appearance": "settings",
    }
    lookup = {page.key: page for page in PAGE_CATALOG}
    for key, family in expected.items():
        page = lookup[key]
        assert family_for(page.key, page.title, page.category) == family

def test_bounded_frame_preserves_nested_objects_and_sanitizes_numeric_infinity() -> None:
    nested = pd.DataFrame({"value": [1, 2]})
    frame = pd.DataFrame({"nested_result": [nested], "score": [np.inf]})

    bounded = _bounded_frame(frame)

    assert isinstance(bounded.loc[0, "nested_result"], pd.DataFrame)
    assert pd.isna(bounded.loc[0, "score"])