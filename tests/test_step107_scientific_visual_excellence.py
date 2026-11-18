from __future__ import annotations

from pathlib import Path

import pandas as pd

from biointel.expansion.catalog import EXPANSION_MODULES
from biointel.expansion.renderer import _analyse_detailed, _demo_frame, _normalise
from biointel.nextgen.catalog import NEXTGEN_MODULES
from biointel.nextgen.scientific import analyse, demo_frame, normalise
from biointel.ui.scientific_visuals import (
    build_dti_prediction_visuals,
    build_scientific_visuals,
    build_sequence_alignment_visuals,
)

ROOT = Path(__file__).resolve().parents[1]


def test_all_scientific_expansion_modules_have_five_visuals() -> None:
    checked = 0
    for module in EXPANSION_MODULES:
        data = _normalise(_demo_frame(module, 72), module)
        result, _, secondary, extras = _analyse_detailed(data, module, 0.70)
        visuals = build_scientific_visuals(
            module.key,
            data=data,
            result=result,
            secondary=secondary,
            extras=extras,
        )
        assert len(visuals) == 5, module.key
        for visual in visuals:
            assert visual.title
            assert visual.interpretation
            assert visual.method
            assert not visual.data.empty
            assert visual.figure.to_dict()["data"]
        checked += 1

    for module in NEXTGEN_MODULES:
        if module.kind != "scientific":
            continue
        data = normalise(demo_frame(module, 90), module)
        result, _, secondary, extras = analyse(data, module, 0.70)
        visuals = build_scientific_visuals(
            module.key,
            data=data,
            result=result,
            secondary=secondary,
            extras=extras,
        )
        assert len(visuals) == 5, module.key
        for visual in visuals:
            assert visual.figure.to_dict()["data"]
        checked += 1

    assert checked == len(EXPANSION_MODULES) + len([item for item in NEXTGEN_MODULES if item.kind == "scientific"])


def test_sequence_alignment_visuals_cover_identity_gaps_and_events() -> None:
    result = {
        "aligned_query": "ACGT-ACT",
        "aligned_target": "ACGTTAGT",
    }
    events = pd.DataFrame(
        {
            "alignment_position": [5, 7],
            "event": ["insertion", "substitution"],
        }
    )
    visuals = build_sequence_alignment_visuals(result, events)
    assert len(visuals) >= 4
    assert any("identity" in visual.title.lower() for visual in visuals)
    assert any("gap" in visual.title.lower() for visual in visuals)


def test_dti_prediction_visuals_are_safe_with_partial_payloads() -> None:
    payload = {
        "positive_probability": 0.77,
        "decision_threshold": 0.50,
        "nearest_training_drug_similarity": 0.61,
        "protein_length": 320,
        "canonical_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
    }
    descriptors = {
        "molecular_weight": 180.16,
        "logp": 1.2,
        "hbd": 1,
        "hba": 4,
        "tpsa": 63.6,
    }
    visuals = build_dti_prediction_visuals(payload, descriptors)
    assert len(visuals) >= 4
    for visual in visuals:
        assert visual.figure.to_dict()["data"]


def test_shared_renderers_use_visual_suite_and_pass_extra_tables() -> None:
    expansion = (ROOT / "src/biointel/expansion/renderer.py").read_text(encoding="utf-8")
    nextgen = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
    workbench = (ROOT / "src/biointel/ui/workbench.py").read_text(encoding="utf-8")
    for text in (expansion, nextgen):
        assert "render_scientific_visual_suite(" in text
    assert "chart_renderer(result, secondary, extras)" in workbench


def test_priority_legacy_modules_include_visual_explorers() -> None:
    pages = {
        "pages/2_Sequence_Comparison.py": "build_sequence_alignment_visuals",
        "pages/4_DTI_Feature_Builder.py": "render_generic_visual_explorer",
        "pages/6_DTI_Predictor.py": "build_dti_prediction_visuals",
        "pages/7_Model_Evaluation.py": "render_generic_visual_explorer",
        "pages/16_Batch_Sequence_Analysis.py": "render_generic_visual_explorer",
        "pages/58_Primer_CRISPR_Codon_Studio.py": "render_generic_visual_explorer",
        "pages/60_Protein_Annotation_Proteomics.py": "render_generic_visual_explorer",
        "pages/63_Pathway_Network_Analysis.py": "render_generic_visual_explorer",
        "pages/66_Omics_Integration_Hub.py": "render_generic_visual_explorer",
        "pages/68_Alignment_Phylogeny.py": "render_generic_visual_explorer",
        "pages/94_Pangenome_Variation_Graph_Studio.py": "render_generic_visual_explorer",
        "pages/99_Synthetic_Biology_Circuit_Designer.py": "render_generic_visual_explorer",
        "pages/100_Rare_Disease_Genome_Interpretation.py": "render_generic_visual_explorer",
    }
    for relative, token in pages.items():
        assert token in (ROOT / relative).read_text(encoding="utf-8"), relative


def test_chart_cards_offer_svg_export_and_underlying_data() -> None:
    components = (ROOT / "src/biointel/ui/components.py").read_text(encoding="utf-8")
    assert '"format": "svg"' in components
    assert '"View underlying data"' in components
    assert '"Download chart data"' in components
