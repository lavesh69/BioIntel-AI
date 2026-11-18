from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.scientific import analyse, demo_frame, normalise
from biointel.nextgen.visual_intelligence_v132 import (
    MODULE_VISUALS,
    VISUAL_CATALOG,
    build_visual_artifact,
    database_summary,
    list_bookmarks,
    list_workspace_layouts,
    record_replay_events,
    record_visual_command,
    save_bookmark,
    save_presenter_session,
    save_workspace_layout,
    visuals_for_module,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE_KEYS = (
    "digital_pathology_foundation", "long_read_epigenome", "single_cell_long_read_isoforms",
    "biomedical_foundation_model_hub", "amr_surveillance", "spatial_medicine_tme",
    "gene_therapy_vector", "cell_therapy_cart", "federated_biomedical_ai",
    "clinical_biomarker_survival", "protein_ligand_codesign", "pangenome_population_medicine",
    "pharmacovigilance_intelligence", "synthetic_cohort_trial", "autonomous_lab_planner",
)


def _analysis(module_key: str):
    module = MODULE_BY_KEY[module_key]
    data = normalise(demo_frame(module, 90), module)
    result, summary, secondary, extras = analyse(data, module, 0.70)
    return data, result, secondary, extras


def test_step132_catalog_has_thirty_unique_visuals_and_all_modules() -> None:
    assert len(VISUAL_CATALOG) == 30
    assert len({item.key for item in VISUAL_CATALOG}) == 30
    assert set(MODULE_KEYS).issubset(MODULE_VISUALS)
    assert all(len(visuals_for_module(key)) >= 6 for key in MODULE_KEYS)


def test_step132_every_visual_builds_and_serialises() -> None:
    data, result, secondary, extras = _analysis("protein_ligand_codesign")
    for visual in VISUAL_CATALOG:
        figure, source, interpretation, limitation = build_visual_artifact(
            visual.key,
            module_key="protein_ligand_codesign",
            data=data,
            result=result,
            secondary=secondary,
            extras=extras,
        )
        assert figure is not None
        figure.to_json()
        assert isinstance(source, pd.DataFrame)
        assert interpretation
        assert limitation


def test_step132_curated_visuals_build_for_all_fifteen_modules() -> None:
    for module_key in MODULE_KEYS:
        data, result, secondary, extras = _analysis(module_key)
        for visual_key in visuals_for_module(module_key):
            figure, source, _, _ = build_visual_artifact(
                visual_key,
                module_key=module_key,
                data=data,
                result=result,
                secondary=secondary,
                extras=extras,
            )
            assert figure is not None
            assert not source.empty


def test_step132_persistence_bookmarks_layouts_presenter_commands_and_replay() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        db = root / "visual.sqlite3"
        bookmark = save_bookmark(root, module_key="amr_surveillance", visual_key="phylogenetic_mutation_movie", title="AMR replay", state={"zoom": 2}, path=db)
        layout = save_workspace_layout(root, module_key="amr_surveillance", name="Four monitors", monitors=[{"monitor": 1, "workspace": "Raw data"}], path=db)
        presenter = save_presenter_session(root, module_key="amr_surveillance", title="AMR review", slides=[{"title": "Trend"}], path=db)
        command = record_visual_command(root, module_key="amr_surveillance", command="Replay", action={"action": "experiment_replay"}, path=db)
        replay = pd.DataFrame([{"stage": "Import", "records": 100}, {"stage": "Analyse", "records": 30}])
        events = record_replay_events(root, module_key="amr_surveillance", run_id="RUN-1", replay=replay, path=db)
        assert bookmark.startswith("VBM-") and layout.startswith("LAY-")
        assert presenter.startswith("PRS-") and command.startswith("CMD-")
        assert len(events) == 2
        assert len(list_bookmarks(root, "amr_surveillance", path=db)) == 1
        assert len(list_workspace_layouts(root, "amr_surveillance", path=db)) == 1
        assert database_summary(root, path=db) == {"bookmarks": 1, "layouts": 1, "presenter_sessions": 1, "commands": 1, "replay_events": 2}


def test_step132_release_contract_and_integration() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    assert (ROOT / "STEP132_RELEASE.json").exists()
    assert (ROOT / "config/step132_visual_intelligence.json").exists()
    assert (ROOT / "pages/196_Multi_Scale_Scientific_Visual_Intelligence_Studio.py").exists()
    renderer = (ROOT / "src/biointel/ui/nextgen_intelligence.py").read_text(encoding="utf-8")
    navigation = (ROOT / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    assert "render_module_visual_intelligence" in renderer
    assert "Multi-scale visual intelligence" in renderer
    assert "196_Multi_Scale_Scientific_Visual_Intelligence_Studio.py" in navigation
