from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel.api.main import app
from biointel.biotech.assays_advanced import (
    bioprocess_advanced_metrics,
    compare_enzyme_models,
    extract_initial_rates,
    fit_elisa_calibration,
    inverse_calibration_with_flags,
    qpcr_multi_reference,
)
from biointel.biotech.experimental_design import plate_randomization
from biointel.biotech.lab_import import parse_rdml
from biointel.biotech.lab_registry import list_runs, record_run, registry_summary
from biointel.biotech.lab_reporting import build_lab_run_bundle
from biointel.biotech.lab_schema import apply_column_mapping, plate_spatial_qc

ROOT = Path(__file__).resolve().parents[1]


def test_multibatch_bioprocess_is_processed_per_batch() -> None:
    frame = pd.DataFrame(
        {
            "batch": ["A"] * 4 + ["B"] * 4,
            "time": [0, 1, 2, 3, 0, 1, 2, 3],
            "biomass": [0.1, 0.2, 0.4, 0.8, 0.2, 0.3, 0.6, 1.0],
            "substrate": [10, 9, 7, 4, 10, 8, 6, 3],
            "product": [0, 0.1, 0.4, 1.0, 0, 0.2, 0.5, 1.2],
        }
    )
    trajectory, summary = bioprocess_advanced_metrics(frame, batch_column="batch")
    assert len(trajectory) == len(frame)
    assert summary["batch_count"] == 2
    assert set(trajectory["batch"]) == {"A", "B"}


def test_elisa_5pl_is_blocked_when_levels_are_insufficient() -> None:
    frame = pd.DataFrame(
        {
            "concentration": np.repeat([1.0, 2.0, 4.0, 8.0], 2),
            "absorbance": [0.1, 0.11, 0.3, 0.31, 0.7, 0.71, 1.2, 1.21],
        }
    )
    with pytest.raises(ValueError, match="requires at least 8"):
        fit_elisa_calibration(frame, candidate_models=("5PL",))


def test_elisa_out_of_range_is_not_silently_quantified() -> None:
    concentration = np.repeat(np.array([0.25, 0.5, 1, 2, 4, 8], dtype=float), 3)
    response = 0.05 + 2.0 / (1 + (1.5 / concentration) ** 1.2)
    standards = pd.DataFrame({"concentration": concentration, "absorbance": response})
    fit = fit_elisa_calibration(standards, candidate_models=("4PL",))
    result = inverse_calibration_with_flags(
        [float(standards["absorbance"].max()) + 10],
        model=fit["selected_model"],
        parameters=fit["parameters"],
        concentration_range=fit["concentration_range"],
        response_range=fit["response_range"],
    )
    assert np.isnan(result.loc[0, "estimated_concentration"])
    assert ">ULOQ" in result.loc[0, "quantification_status"]


def test_qpcr_role_column_excludes_ignore_and_controls() -> None:
    frame = pd.DataFrame(
        {
            "sample": ["C"] * 4 + ["T"] * 4,
            "gene": ["GAPDH", "ACTB", "GENE", "IGNORE_ME"] * 2,
            "ct": [18, 19, 22, 25, 18.2, 19.1, 20, 24],
            "role": ["reference", "reference", "target", "ignore"] * 2,
        }
    )
    result = qpcr_multi_reference(
        frame,
        target_column="role",
        reference_genes=["GAPDH", "ACTB"],
        calibrator_sample="C",
    )
    assert set(result["gene"]) == {"GENE"}
    assert result["excluded_control_or_ignore_rows"].iloc[0] == 2


def test_negative_progress_curve_is_review_not_valid_rate() -> None:
    frame = pd.DataFrame({"reaction": ["R1"] * 5, "time": [0, 1, 2, 3, 4], "signal": [5, 4, 3, 2, 1]})
    result = extract_initial_rates(frame, expected_direction="increasing")
    assert result.loc[0, "qc_status"] == "Review"
    assert np.isnan(result.loc[0, "initial_rate"])


def test_duplicate_mapping_is_blocked_and_metadata_can_be_preserved() -> None:
    frame = pd.DataFrame({"sample": ["S1"], "ct": [20.0], "operator": ["A"]})
    with pytest.raises(ValueError, match="only one canonical"):
        apply_column_mapping(frame, {"target_ct": "ct", "reference_ct": "ct"})
    mapped = apply_column_mapping(frame, {"sample": "sample", "target_ct": "ct"}, preserve_unmapped=True)
    assert "meta__operator" in mapped.columns


def test_plate_randomization_actually_avoids_adjacent_replicates() -> None:
    plate = plate_randomization([f"S{i}" for i in range(20)], replicates=2, seed=42)
    assert plate["adjacency_violations"].iloc[0] == 0
    assert set(plate["layout_qc"]) == {"Pass"}


def test_plate_spatial_qc_detects_large_edge_shift() -> None:
    wells = [f"A{i}" for i in range(1, 13)] + [f"D{i}" for i in range(1, 13)]
    values = [10.0] * 12 + [1.0] * 12
    result = plate_spatial_qc(pd.DataFrame({"well": wells, "signal": values}), value_column="signal")
    assert result.loc[0, "spatial_qc"] == "Review"
    assert "edge_effect" in result.loc[0, "flags"]


def test_rdml_core_fields_are_parsed() -> None:
    xml = b'''<?xml version="1.0"?><rdml><sample id="S1"><type>unkn</type></sample><experiment><run><react id="A1"><sample id="S1"/><data><tar id="GENE1"/><cq>22.5</cq></data></react></run></experiment></rdml>'''
    result = parse_rdml(xml)
    assert result.loc[0, "sample"] == "S1"
    assert result.loc[0, "gene"] == "GENE1"
    assert result.loc[0, "ct"] == 22.5


def test_reproducibility_bundle_has_manifest_and_checksums() -> None:
    frame = pd.DataFrame({"sample": ["S1"], "value": [1.0]})
    payload = build_lab_run_bundle(workflow="test", input_frame=frame, outputs={"result": frame}, parameters={"alpha": 0.05})
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "SHA256SUMS.txt", "outputs/result.csv"}.issubset(names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["input"]["sha256"]


def test_lab_registry_persists_run_and_artifacts(tmp_path: Path) -> None:
    database = tmp_path / "lab.sqlite3"
    frame = pd.DataFrame({"sample": ["S1"], "value": [1.0]})
    run_id = record_run(workflow="test", input_frame=frame, parameters={}, outputs={"result": frame}, path=database)
    assert run_id
    assert registry_summary(database) == {"runs": 1, "artifacts": 1, "reviews": 0}
    assert list_runs(path=database).iloc[0]["run_id"] == run_id


def test_enzyme_model_comparison_returns_aicc_ranking() -> None:
    substrate = np.array([0.05, 0.1, 0.25, 0.5, 1, 2, 5], dtype=float)
    velocity = 10 * substrate / (0.4 + substrate)
    result = compare_enzyme_models(substrate, velocity)
    assert result.iloc[0]["model"] == "michaelis_menten"
    assert "delta_aicc" in result.columns


def test_lab_api_endpoints() -> None:
    client = TestClient(app)
    enzyme = client.post(
        "/biotechnology/enzyme/fit",
        json={"rows": [{"substrate": value, "velocity": 10 * value / (0.4 + value)} for value in [0.05, 0.1, 0.25, 0.5, 1, 2, 5]], "model": "auto"},
    )
    assert enzyme.status_code == 200, enzyme.text
    process = client.post(
        "/biotechnology/bioprocess/analyze",
        json={"rows": [{"batch": "A", "time": t, "biomass": 0.2 + t * 0.2, "substrate": 10 - t, "product": t * 0.3} for t in [0, 1, 2, 3]], "process_mode": "Batch", "batch_column": "batch"},
    )
    assert process.status_code == 200, process.text
    design = client.post("/biotechnology/design/sample-size", json={"design_type": "noninferiority", "margin": 0.5, "assumed_standard_deviation": 2.0})
    assert design.status_code == 200, design.text


@pytest.mark.parametrize("page", ["pages/64_Wet_Lab_Biotechnology.py", "pages/82_Metagenomics_Pipeline.py", "pages/89_Lab_Analytics_Command_Center.py"])
def test_step62_lab_pages_render(page: str) -> None:
    application = AppTest.from_file(str(ROOT / page), default_timeout=180).run()
    assert not application.exception, page


def test_raw_qpcr_curve_qc_reports_threshold_crossing():
    from biointel.biotech.assays_advanced import qpcr_amplification_curve_qc

    cycles = np.arange(1, 41)
    fluorescence = 100 + 2 ** ((cycles - 25) / 2)
    frame = pd.DataFrame({"reaction": "R1", "cycle": cycles, "fluorescence": fluorescence})
    detail, summary = qpcr_amplification_curve_qc(frame)
    assert not detail.empty
    assert summary.loc[0, "curve_qc_status"] == "Pass"
    assert np.isfinite(summary.loc[0, "estimated_cq"])


def test_elisa_validation_summary_marks_safe_calibration():
    from biointel.biotech.assays_advanced import elisa_validation_summary, fit_elisa_calibration

    concentrations = np.repeat([1, 2, 4, 8, 16, 32], 2)
    response = 0.1 + 2.0 * concentrations / (8.0 + concentrations)
    standards = pd.DataFrame({"concentration": concentrations, "absorbance": response})
    calibration = fit_elisa_calibration(standards, candidate_models=("4PL", "log-linear"))
    checks, summary = elisa_validation_summary(calibration)
    assert not checks.empty
    assert summary["checks"] >= 4
    assert summary["selected_model"] in {"4PL", "log-linear"}


def test_bioprocess_pat_monitor_flags_extreme_point():
    from biointel.biotech.assays_advanced import bioprocess_pat_monitor

    frame = pd.DataFrame({"time": range(10), "ph": [7.0, 7.1, 7.0, 7.1, 7.0, 7.1, 7.0, 7.1, 7.0, 9.5]})
    detail, summary = bioprocess_pat_monitor(frame, variables=["ph"])
    assert (detail["pat_status"] == "Review").any()
    assert summary.loc[0, "status"] == "Review"
