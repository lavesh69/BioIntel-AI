from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import pytest
from rdkit import Chem
from streamlit.testing.v1 import AppTest

from biointel.chemistry.descriptors import calculate_descriptors
from biointel.genomics.design_advanced import design_primer_pairs_advanced
from biointel.structural.visualization import (
    build_residue_network_figure,
    build_structure_figure,
    select_structure_atoms,
    structure_atom_table,
)

ROOT = Path(__file__).resolve().parents[1]


def test_descriptor_api_accepts_smiles_and_mol_without_boost_argument_error() -> None:
    from_smiles = calculate_descriptors("CC(=O)O")
    from_mol = calculate_descriptors(Chem.MolFromSmiles("CC(=O)O"))
    assert from_smiles["molecular_weight"] == pytest.approx(from_mol["molecular_weight"])
    assert from_smiles["lipinski_violations"] == 0
    with pytest.raises(ValueError, match="could not be parsed"):
        calculate_descriptors("not a smiles")
    with pytest.raises(TypeError, match="RDKit Mol or a SMILES"):
        calculate_descriptors(42)  # type: ignore[arg-type]


def test_appearance_apply_cancel_and_named_preset_are_widget_state_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = f"step68_test_{os.getpid()}"
    monkeypatch.setenv("BIOINTEL_UI_PROFILE", profile)
    app = AppTest.from_file(str(ROOT / "pages/24_Appearance_Studio.py"), default_timeout=150)
    app.run(timeout=150)
    next(item for item in app.selectbox if item.label == "Complete UI theme").select("Ocean")
    next(item for item in app.button if item.label == "Apply theme and typography").click()
    app.run(timeout=150)
    assert not app.exception

    next(item for item in app.selectbox if item.label == "Complete UI theme").select("Rose")
    next(item for item in app.button if item.label == "Cancel preview").click()
    app.run(timeout=150)
    assert not app.exception
    assert (
        next(item for item in app.selectbox if item.label == "Complete UI theme").value == "Ocean"
    )

    next(item for item in app.text_input if item.label == "Preset name").input("Step68 Safe")
    next(item for item in app.button if item.label == "Save named preset").click()
    app.run(timeout=150)
    preset = next(item for item in app.selectbox if item.label == "Saved presets")
    preset.select("Step68 Safe")
    next(item for item in app.button if item.label == "Apply preset").click()
    app.run(timeout=150)
    assert not app.exception


def test_dti_single_and_batch_interactions_do_not_raise_descriptor_errors() -> None:
    app = AppTest.from_file(str(ROOT / "pages/6_DTI_Predictor.py"), default_timeout=240)
    app.run(timeout=240)
    acknowledgement = next(item for item in app.checkbox if "exploratory/demo-only" in item.label)
    acknowledgement.check()
    app.run(timeout=240)
    next(item for item in app.button if item.label == "Predict interaction").click()
    app.run(timeout=240)
    assert not app.exception
    rendered_markdown = "\n".join(str(item.value) for item in app.markdown)
    assert 'bio-shell-premium' in rendered_markdown and 'bio-shell-kicker">Discovery' in rendered_markdown
    assert 'bio-shell-title">DTI Predictor' in rendered_markdown
    assert not any("Prediction failed" in item.value for item in app.error)
    assert not any("Boost.Python" in item.value for item in app.error)

    next(item for item in app.button if item.label == "Run batch prediction").click()
    app.run(timeout=300)
    assert not app.exception
    assert any("Processed 250 rows" in item.value for item in app.success)


def test_balanced_primer_search_is_fast_and_reports_progress() -> None:
    sequence = "ATGCGTACGTTAGCGGCGTACCTGACTGCGTACGATCGTACGGCATGCTAGCGTACGATCGTACGGC" * 16
    progress: list[tuple[str, float]] = []
    started = time.perf_counter()
    pairs = design_primer_pairs_advanced(
        sequence,
        minimum_product=70,
        maximum_product=500,
        minimum_tm=45,
        maximum_tm=75,
        maximum_pairs=100,
        search_mode="balanced",
        progress_callback=lambda label, value: progress.append((label, value)),
    )
    elapsed = time.perf_counter() - started
    assert pairs
    assert elapsed < 12
    assert any("forward" in label.lower() for label, _ in progress)
    assert any("ranking" in label.lower() for label, _ in progress)
    assert progress[-1][1] >= 0.99


def test_primer_page_default_design_completes_without_stuck_status() -> None:
    app = AppTest.from_file(
        str(ROOT / "pages/58_Primer_CRISPR_Codon_Studio.py"), default_timeout=180
    )
    app.run(timeout=180)
    next(item for item in app.button if item.label == "Design thermodynamic primer pairs").click()
    app.run(timeout=180)
    assert not app.exception
    assert not app.error
    assert len(app.dataframe) >= 1


def test_structure_view_supports_large_canvas_focus_and_network_graph() -> None:
    catalog = pd.read_csv(ROOT / "data/bioinformatics_demo/demo_structure_catalog.csv")
    structure_path = ROOT / str(catalog.iloc[0]["relative_path"])
    atoms = structure_atom_table(
        structure_path.read_text(encoding="utf-8"),
        format_hint=structure_path.suffix.lstrip("."),
    )
    displayed, summary = select_structure_atoms(
        atoms,
        selected_chains=sorted(atoms["chain"].astype(str).unique()),
        visible_groups=sorted(atoms["group"].unique()),
        preset="Ligand focus",
        maximum_atoms=8_000,
        ligand_focus_radius=10.0,
    )
    assert not displayed.empty
    assert summary.displayed_atoms == len(displayed)
    figure = build_structure_figure(displayed, height=960, point_size=6.0)
    assert figure.layout.height == 960
    assert figure.layout.scene.aspectmode == "data"
    assert len(figure.data) >= 2

    edges = pd.DataFrame({"source": ["A:1", "A:2"], "target": ["A:2", "A:3"]})
    nodes = pd.DataFrame(
        {"node": ["A:1", "A:2", "A:3"], "degree": [1, 2, 1], "hub_candidate": [False] * 3}
    )
    network = build_residue_network_figure(edges, nodes, height=840)
    assert network is not None
    assert network.layout.height == 840


def test_structural_page_renders_enhanced_viewer_without_exception() -> None:
    app = AppTest.from_file(
        str(ROOT / "pages/61_Structural_Bioinformatics.py"), default_timeout=180
    )
    app.run(timeout=180)
    assert not app.exception
    assert any(item.label == "Viewer height" for item in app.select_slider)
    assert any(item.label == "View preset" for item in app.selectbox)
    assert len(app.get("plotly_chart")) >= 4


def test_streamlit_hides_uncaught_local_stack_paths_from_end_users() -> None:
    config = (ROOT / ".streamlit/config.toml").read_text(encoding="utf-8")
    assert 'showErrorDetails = "none"' in config


def test_workspace_health_includes_discovery_and_lab_registries() -> None:
    from biointel.intelligence.data_intelligence import all_database_health, database_paths

    paths = database_paths(ROOT)
    assert "discovery_projects" in paths
    assert "lab_analytics" in paths
    health = all_database_health(ROOT)
    assert health["database_count"] == len(paths)
    assert health["healthy_count"] == health["database_count"]
