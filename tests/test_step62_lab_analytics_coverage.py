from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from biointel.biotech.assays import (
    bioprocess_yields,
    enzyme_kinetics,
    fit_elisa_4pl,
    four_parameter_logistic,
    growth_metrics,
    inverse_4pl,
    qpcr_delta_delta_ct,
    quantify_elisa,
)
from biointel.biotech.assays_advanced import (
    bioprocess_advanced_metrics,
    bioprocess_batch_comparison,
    bioprocess_pat_monitor,
    bioprocess_sensor_metrics,
    bootstrap_elisa_unknown_intervals,
    compare_enzyme_models,
    compare_inhibition_models,
    convert_absorbance_slope_to_rate,
    elisa_assay_qc,
    elisa_hook_effect_screen,
    elisa_parallelism_recovery_qc,
    elisa_validation_summary,
    extract_initial_rates,
    fit_elisa_calibration,
    fit_enzyme_model,
    global_inhibition_fit,
    inverse_calibration,
    inverse_calibration_with_flags,
    melt_curve_qc,
    qpcr_amplification_curve_qc,
    qpcr_control_qc,
    qpcr_group_statistics,
    qpcr_multi_reference,
    qpcr_reference_gene_stability,
    qpcr_standard_curve,
)
from biointel.biotech.experimental_design import (
    cluster_adjusted_sample_size,
    correlation_sample_size,
    equivalence_sample_size,
    noninferiority_sample_size,
    one_way_anova_sample_size,
    paired_sample_size,
    plate_randomization,
    randomized_assignment,
    repeated_measures_sample_size,
    sensitivity_curve,
    two_group_sample_size,
    two_proportion_sample_size,
)
from biointel.biotech.lab_import import list_excel_sheets, parse_rdml, read_lab_table
from biointel.biotech.lab_registry import list_runs, record_run, registry_summary
from biointel.biotech.lab_reporting import build_lab_run_bundle
from biointel.biotech.lab_schema import (
    apply_column_mapping,
    column_mapping_ready,
    infer_column_mapping,
    plate_coordinates,
    plate_map_audit,
    plate_spatial_qc,
)
from biointel.projects.metagenomics_raw_reads import (
    RawReadPlan,
    RawReadStep,
    execute_raw_read_plan,
    plan_dict,
)


def test_basic_qpcr_full_result_and_error_paths() -> None:
    frame = pd.DataFrame(
        {
            "sample": ["C", "C", "T", "T", "T"],
            "target_ct": [20.0, 20.2, 18.0, 18.2, 45.0],
            "reference_ct": [17.0, 17.1, 17.0, 17.1, 18.0],
        }
    )
    result = qpcr_delta_delta_ct(frame, calibrator_sample="C", target_efficiency=1.95, reference_efficiency=2.0)
    assert set(result["sample"]) == {"C", "T"}
    assert result.loc[result["sample"] == "T", "undetermined_measurements"].iloc[0] == 1
    assert (result["relative_expression_ci95_upper"] >= result["relative_expression"]).all()
    with pytest.raises(ValueError, match="Missing qPCR"):
        qpcr_delta_delta_ct(frame.drop(columns="target_ct"), calibrator_sample="C")
    with pytest.raises(ValueError, match="greater than"):
        qpcr_delta_delta_ct(frame, calibrator_sample="C", target_efficiency=1.0)
    with pytest.raises(ValueError, match="Calibrator"):
        qpcr_delta_delta_ct(frame, calibrator_sample="missing")
    with pytest.raises(ValueError, match="No valid"):
        qpcr_delta_delta_ct(frame.assign(target_ct=99), calibrator_sample="C")


def test_basic_enzyme_growth_and_bioprocess_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    substrate = np.array([0.05, 0.1, 0.25, 0.5, 1, 2, 5], dtype=float)
    velocity = 8 * substrate / (0.4 + substrate)
    kinetics = enzyme_kinetics(substrate, velocity)
    assert kinetics["r_squared"] > 0.99
    assert kinetics["vmax_ci95_upper"] is not None
    with pytest.raises(ValueError):
        enzyme_kinetics([1, 2], [1, 2])

    growth = growth_metrics([0, 1, 2, 3, 4], [0.1, 0.2, 0.4, 0.8, 1.0])
    assert growth["maximum_specific_growth_rate"] > 0
    fallback = growth_metrics([0, 1, 2], [1.0, 0.9, 0.8])
    assert "fallback" in fallback["method"]
    with pytest.raises(ValueError):
        growth_metrics([0, 1, 1], [0.1, 0.2, 0.3])

    process = pd.DataFrame({"time": [0, 1, 2], "biomass": [0.1, 0.2, 0.5], "substrate": [10, 8, 5], "product": [0, 1, 3]})
    yields = bioprocess_yields(process)
    assert yields["product_yield_per_substrate"] == pytest.approx(0.6)
    replicated = pd.concat([process.assign(replicate="A"), process.assign(replicate="B", product=[0, 2, 4])])
    replicate_yields = bioprocess_yields(replicated)
    assert replicate_yields["replicates"] == 2
    with pytest.raises(ValueError):
        bioprocess_yields(process.drop(columns="product"))


def test_basic_elisa_fit_inverse_quantification() -> None:
    concentration = np.array([0.25, 0.5, 1, 2, 4, 8], dtype=float)
    response = four_parameter_logistic(concentration, 0.05, 2.0, 1.5, 1.2)
    fit = fit_elisa_4pl(concentration, response)
    inverse = inverse_4pl(response, fit)
    assert np.allclose(inverse, concentration, rtol=0.15)
    result = quantify_elisa(
        concentration,
        response + 0.02,
        [0.5, 1.5, 3.0],
        blank_absorbance=0.02,
        blank_standard_deviation=0.01,
        dilution_factors=[1, 2, 5],
    )
    assert len(result["unknown_results"]) == 3
    assert result["estimated_lod"] is not None
    with pytest.raises(ValueError):
        fit_elisa_4pl([1, 2, 3], [0.1, 0.2, 0.3])
    with pytest.raises(ValueError, match="Dilution"):
        quantify_elisa(concentration, response, [0.5, 1.0], dilution_factors=[1])


def test_advanced_qpcr_long_format_statistics_controls_and_curves() -> None:
    rows = []
    for sample, group, target_ct in [("C", "control", 25.0), ("C2", "control", 25.2), ("T", "treated", 23.0)]:
        for rep in range(2):
            rows.extend(
                [
                    {"sample": sample, "group": group, "role": "target", "gene": "GENE", "ct": target_ct + rep * 0.1},
                    {"sample": sample, "group": group, "role": "reference", "gene": "GAPDH", "ct": 18 + rep * 0.1},
                    {"sample": sample, "group": group, "role": "reference", "gene": "ACTB", "ct": 19 + rep * 0.1},
                    {"sample": sample, "group": group, "role": "ignore", "gene": "IGNORE", "ct": 10},
                ]
            )
    long = pd.DataFrame(rows)
    multi = qpcr_multi_reference(long, target_column="role", reference_genes=["GAPDH", "ACTB"], calibrator_sample="C")
    assert set(multi["gene"]) == {"GENE"}
    assert multi["excluded_control_or_ignore_rows"].iloc[0] > 0
    merged = multi.merge(long[["sample", "group"]].drop_duplicates(), on="sample")
    summary, tests = qpcr_group_statistics(merged, group_column="group", reference_group="control")
    assert len(summary) == 2 and len(tests) == 1
    raw_summary, _ = qpcr_group_statistics(merged, group_column="group", reference_group="control", inference_scale="raw")
    assert set(raw_summary["inference_scale"]) == {"raw"}
    with pytest.raises(ValueError, match="Unknown qPCR role"):
        qpcr_multi_reference(long.assign(role="mystery"), target_column="role", reference_genes=["GAPDH"], calibrator_sample="C")
    with pytest.raises(ValueError, match="positive expression"):
        qpcr_group_statistics(pd.DataFrame({"group": ["A", "B"], "relative_expression": [1, 0]}), group_column="group")

    stability = qpcr_reference_gene_stability(long, candidate_genes=["GAPDH", "ACTB"])
    assert len(stability) == 2
    controls = pd.DataFrame({"role": ["ntc", "no-rt", "positive_control", "extraction_control"], "ct": [np.nan, 39.8, 22.0, 24.0]})
    assert set(qpcr_control_qc(controls)["qc_status"]) == {"Pass"}

    cycles = np.arange(1, 41)
    curves = pd.concat(
        [
            pd.DataFrame({"reaction": "good", "cycle": cycles, "fluorescence": 100 + 2 ** ((cycles - 25) / 2)}),
            pd.DataFrame({"reaction": "flat", "cycle": cycles, "fluorescence": np.full_like(cycles, 100)}),
            pd.DataFrame({"reaction": "short", "cycle": cycles[:8], "fluorescence": np.arange(8)}),
        ],
        ignore_index=True,
    )
    detail, curve_summary = qpcr_amplification_curve_qc(curves)
    assert not detail.empty
    assert set(curve_summary["curve_qc_status"]) == {"Pass", "Review"}


def test_qpcr_standard_and_melt_error_paths() -> None:
    with pytest.raises(ValueError):
        qpcr_standard_curve([1, 1, 1], [20, 21, 22])
    positive_slope = qpcr_standard_curve([1, 10, 100], [20, 21, 22])
    assert np.isnan(positive_slope["efficiency_fraction"])
    temperatures = np.linspace(60, 95, 351)
    fluorescence = 1 / (1 + np.exp((temperatures - 75) / 0.4)) + 0.5 / (1 + np.exp((temperatures - 85) / 0.4))
    melt = melt_curve_qc(temperatures, fluorescence)
    assert melt["peak_count"] >= 1
    with pytest.raises(ValueError):
        melt_curve_qc([1, 2], [1, 2])


def _elisa_standards(levels: int = 8) -> pd.DataFrame:
    concentration = np.repeat(np.geomspace(0.25, 32, levels), 3)
    response = 0.05 + 2.0 / (1 + (1.5 / concentration) ** 1.2)
    offsets = np.tile([-0.005, 0, 0.005], levels)
    return pd.DataFrame({"concentration": concentration, "absorbance": response + offsets})


def test_advanced_elisa_models_inverse_bootstrap_validation_and_qc() -> None:
    standards = _elisa_standards()
    calibration = fit_elisa_calibration(standards, candidate_models=("linear", "log-linear", "4PL", "5PL"))
    assert calibration["selected_model"] in {"4PL", "5PL", "log-linear", "linear"}
    midpoint = np.mean(calibration["response_range"])
    allowed = inverse_calibration([midpoint], model=calibration["selected_model"], parameters=calibration["parameters"], concentration_range=calibration["concentration_range"], response_range=calibration["response_range"], extrapolation="allow")
    clipped = inverse_calibration([999], model=calibration["selected_model"], parameters=calibration["parameters"], concentration_range=calibration["concentration_range"], response_range=calibration["response_range"], extrapolation="clip")
    safe = inverse_calibration_with_flags([midpoint, -100, 999], model=calibration["selected_model"], parameters=calibration["parameters"], concentration_range=calibration["concentration_range"], response_range=calibration["response_range"])
    assert np.isfinite(allowed[0])
    assert np.isfinite(clipped[0])
    assert safe.loc[0, "quantification_status"] == "In range"
    assert safe.loc[2, "recommendation"] == "Dilute and repeat"
    intervals = bootstrap_elisa_unknown_intervals(standards, [midpoint], model=calibration["selected_model"], iterations=20, random_state=2)
    assert len(intervals) == 1
    checks, summary = elisa_validation_summary(calibration, safe)
    assert len(checks) >= 4 and summary["checks"] >= 4
    with pytest.raises(ValueError):
        fit_elisa_calibration(standards.head(6), candidate_models=("5PL",))
    with pytest.raises(ValueError):
        inverse_calibration([1], model="bad", parameters={}, concentration_range=(1, 2), response_range=(1, 2))

    plate = pd.DataFrame(
        {
            "type": ["positive"] * 4 + ["negative"] * 4 + ["sample"] * 4,
            "name": ["P"] * 4 + ["N"] * 4 + ["S"] * 4,
            "absorbance": [2.0, 2.1, 1.9, 2.0, 0.1, 0.12, 0.09, 0.11, 1.0, 1.05, 0.95, 1.0],
        }
    )
    assay = elisa_assay_qc(plate)
    assert assay["positive_controls"] == 4 and not assay["replicate_qc"].empty
    quantified = pd.DataFrame({"name": ["S", "S"], "estimated_concentration": [100, 110], "dilution_factor": [10, 20], "expected_concentration": [100, 100]})
    parallel, recovery = elisa_parallelism_recovery_qc(quantified)
    assert not parallel.empty and not recovery.empty
    assert elisa_hook_effect_screen(pd.DataFrame({"concentration": [1, 2], "absorbance": [0.1, 0.2]}))["status"] == "Insufficient standards"


def test_advanced_enzyme_model_comparisons_inhibition_and_initial_rates() -> None:
    substrate = np.array([0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10], dtype=float)
    velocity = 10 * substrate / (0.5 + substrate)
    for model in ["michaelis_menten", "hill", "substrate_inhibition"]:
        fit = fit_enzyme_model(substrate, velocity, model=model)
        assert fit["model"] == model
    comparison = compare_enzyme_models(substrate, velocity)
    assert set(comparison["model"]) == {"michaelis_menten", "hill", "substrate_inhibition"}
    inhibitor = np.repeat([0.0, 0.5, 1.0], len(substrate))
    s = np.tile(substrate, 3)
    v = 10 * s / (0.5 * (1 + inhibitor / 0.8) + s)
    mechanism_table = compare_inhibition_models(s, inhibitor, v)
    assert len(mechanism_table) == 4
    for mechanism in ["competitive", "noncompetitive", "uncompetitive", "mixed"]:
        fitted = global_inhibition_fit(s, inhibitor, v, model=mechanism)
        assert fitted["model"] == mechanism
    with pytest.raises(ValueError):
        fit_enzyme_model([1, 2, 3], [1, 2], model="michaelis_menten")
    with pytest.raises(ValueError):
        global_inhibition_fit(s, inhibitor, v, model="invalid")

    assert convert_absorbance_slope_to_rate([1.0], extinction_coefficient=2.0, path_length_cm=1.0, dilution_factor=2.0)[0] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        convert_absorbance_slope_to_rate([1.0], extinction_coefficient=0, path_length_cm=1.0)
    progress = pd.concat(
        [
            pd.DataFrame({"reaction": "up", "time": np.arange(6), "signal": np.arange(6) * 2}),
            pd.DataFrame({"reaction": "down", "time": np.arange(6), "signal": 10 - np.arange(6)}),
            pd.DataFrame({"reaction": "short", "time": [0, 1], "signal": [0, 1]}),
            pd.DataFrame({"reaction": "duplicate", "time": [0, 1, 1, 2], "signal": [0, 1, 2, 3]}),
        ]
    )
    rates = extract_initial_rates(progress, expected_direction="increasing")
    assert rates.loc[rates["reaction"] == "up", "qc_status"].iloc[0] == "Pass"
    assert np.isnan(rates.loc[rates["reaction"] == "down", "initial_rate"].iloc[0])
    with pytest.raises(ValueError):
        extract_initial_rates(progress, expected_direction="sideways")


def test_bioprocess_all_modes_sensors_batches_pat_and_errors() -> None:
    base = pd.DataFrame(
        {
            "time": [0, 1, 2, 3],
            "biomass": [0.2, 0.4, 0.8, 1.2],
            "substrate": [10, 8, 5, 2],
            "product": [0, 0.2, 0.8, 1.8],
            "volume": [1.0, 1.1, 1.2, 1.3],
            "feed": [0.0, 0.1, 0.1, 0.1],
            "bleed": [0.0, 0.0, 0.05, 0.05],
            "our": [1, 2, 3, 4],
            "cer": [0.8, 1.6, 2.4, 3.2],
            "do": [7, 6, 5, 4],
            "kla": [10, 10, 10, 10],
            "oxygen_saturation": [8, 8, 8, 8],
        }
    )
    for mode in ["Batch", "Fed-batch", "Continuous", "Perfusion"]:
        trajectory, summary = bioprocess_advanced_metrics(base, process_mode=mode, volume_column="volume", feed_column="feed", bleed_column="bleed")
        assert len(trajectory) == 4 and summary["process_mode"] == mode
    incomplete, summary = bioprocess_advanced_metrics(base.drop(columns=["volume", "bleed"]), process_mode="Perfusion")
    assert str(summary["mode_specific_status"]).startswith("Review")
    batches = pd.concat([base.assign(batch="A"), base.assign(batch="B", product=[0, 0.3, 1.0, 2.1])])
    combined, aggregate = bioprocess_advanced_metrics(batches, batch_column="batch", process_mode="Fed-batch", volume_column="volume", feed_column="feed")
    assert aggregate["batch_count"] == 2 and set(combined["batch"]) == {"A", "B"}
    sensors, sensor_summary = bioprocess_sensor_metrics(base)
    assert "respiratory_quotient" in sensors and sensor_summary["final_cumulative_feed"] is not None
    aligned, batch_summary = bioprocess_batch_comparison(batches, batch_column="batch")
    assert not aligned.empty and set(batch_summary["batch"]) == {"A", "B"}
    pat_detail, pat_summary = bioprocess_pat_monitor(base.assign(ph=[7, 7, 7, 9]), variables=["ph", "do"])
    assert not pat_detail.empty and not pat_summary.empty
    with pytest.raises(ValueError):
        bioprocess_advanced_metrics(base.assign(time=[0, 1, 1, 2]))
    with pytest.raises(ValueError):
        bioprocess_advanced_metrics(base, process_mode="bad")
    with pytest.raises(ValueError):
        bioprocess_sensor_metrics(base.drop(columns="time"))


def test_experimental_design_all_paths_and_errors() -> None:
    assert two_group_sample_size(0.8, dropout_fraction=0.1)["total"] > 0
    assert paired_sample_size(0.5, dropout_fraction=0.1)["pairs"] > 0
    assert two_proportion_sample_size(0.2, 0.5, dropout_fraction=0.1)["total"] > 0
    assert one_way_anova_sample_size(0.4, 4, dropout_fraction=0.1)["total"] % 4 == 0
    curve = pd.concat([sensitivity_curve("two_group", [0.3, 0.5], power=power) for power in (0.8, 0.9)], ignore_index=True)
    assert len(curve) == 4
    samples = [f"S{i}" for i in range(12)]
    blocks = {sample: ("X" if index < 6 else "Y") for index, sample in enumerate(samples)}
    assignment = randomized_assignment(samples, ["A", "B"], blocks=blocks, variable_block_sizes=(4,), seed=None, blind_labels=True)
    assert len(assignment) == 12
    plate = plate_randomization([f"S{i}" for i in range(10)], controls={"Blank": 2}, replicates=2, seed=None)
    assert len(plate) == 22 and "layout_qc" in plate
    assert noninferiority_sample_size(0.5, assumed_standard_deviation=2, dropout_fraction=0.1)["total"] > 0
    assert equivalence_sample_size(0.5, assumed_standard_deviation=2, dropout_fraction=0.1)["total"] > 0
    assert correlation_sample_size(0.3, dropout_fraction=0.1)["participants"] > 0
    assert cluster_adjusted_sample_size(100, average_cluster_size=10, intracluster_correlation=0.05, dropout_fraction=0.1)["clusters"] > 0
    assert repeated_measures_sample_size(0.5, measurements=4, within_subject_correlation=0.5, dropout_fraction=0.1)["pairs"] > 0
    with pytest.raises(ValueError):
        randomized_assignment(["S1", "S1"], ["A", "B"])
    with pytest.raises(ValueError):
        plate_randomization([f"S{i}" for i in range(100)], plate_format=96)
    with pytest.raises(ValueError):
        sensitivity_curve("bad", [0.5])


def test_schema_import_reporting_registry_and_raw_read_resume(tmp_path: Path) -> None:
    raw = pd.DataFrame({"Sample ID": ["S1", "S2"], "Ct Target": [20, 21], "Ref Ct": [18, 18.5], "Operator": ["A", "A"], "Well": ["A1", "H12"]})
    mapping = infer_column_mapping(raw, "qpcr")
    mapped = apply_column_mapping(raw, mapping, required=["sample", "target_ct", "reference_ct"], preserve_unmapped=True)
    assert "meta__operator" in mapped
    coords = plate_coordinates(mapped, plate_format=96)
    assert coords[["plate_row", "plate_column"]].notna().all().all()
    audit = plate_map_audit(mapped, plate_format=96)
    assert audit["valid_wells"] == 2
    spatial = plate_spatial_qc(pd.DataFrame({"well": ["A1", "A2", "H11", "H12"], "signal": [1.0, 1.1, 0.9, 1.0]}), value_column="signal")
    assert not spatial.empty
    with pytest.raises(ValueError):
        apply_column_mapping(raw, {"sample": "Sample ID", "target_ct": "Ct Target", "reference_ct": "Ct Target"}, required=["sample", "target_ct", "reference_ct"])
    required = ("sample", "target_ct", "reference_ct")
    assert column_mapping_ready(mapping, required=required)
    assert not column_mapping_ready({"sample": "Sample ID", "target_ct": "Ct Target"}, required=required)
    assert not column_mapping_ready(
        {"sample": "Sample ID", "target_ct": "Ct Target", "reference_ct": "Ct Target"},
        required=required,
    )

    csv = io.BytesIO(b"a,b\n1,2\n")
    csv.name = "table.csv"
    assert list(read_lab_table(csv).columns) == ["a", "b"]
    excel_path = tmp_path / "table.xlsx"
    with pd.ExcelWriter(excel_path) as writer:
        pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="One", index=False)
        pd.DataFrame({"b": [2]}).to_excel(writer, sheet_name="Two", index=False)
    excel_upload = io.BytesIO(excel_path.read_bytes())
    excel_upload.name = "table.xlsx"
    assert set(list_excel_sheets(excel_upload)) == {"One", "Two"}
    excel_upload.seek(0)
    assert list(read_lab_table(excel_upload, sheet_name="Two").columns) == ["b"]
    rdml = b'''<?xml version="1.0"?><rdml><experiment><run><react id="R1"><sample id="S1"/><data><tar id="GENE"/><cq>22.5</cq></data></react></run></experiment></rdml>'''
    parsed = parse_rdml(rdml)
    assert parsed.loc[0, "ct"] == 22.5
    with pytest.raises(ValueError):
        parse_rdml(b"<rdml></rdml>")

    bundle = build_lab_run_bundle(workflow="test", input_frame=raw, outputs={"table": mapped, "scalar": {"x": np.float64(1.0), "nan": np.nan}}, parameters={"alpha": 1}, recommendations=["Review"])
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert "manifest.json" in archive.namelist() and "SHA256SUMS.txt" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["workflow"] == "test"

    registry = tmp_path / "lab.sqlite3"
    run_id = record_run(workflow="test", input_frame=raw, parameters={"a": 1}, outputs={"table": mapped, "summary": {"ok": True}}, path=registry)
    assert run_id in set(list_runs(path=registry)["run_id"])
    assert registry_summary(registry)["artifacts"] == 2
    with sqlite3.connect(registry) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    output = tmp_path / "done.txt"
    output.write_text("done")
    plan = RawReadPlan("S", False, "db", (RawReadStep("Done", "missing", (), (str(output),), False, "test"),), (), "r1", "abc", "image@sha256:abc")
    executed = execute_raw_read_plan(plan, resume=True)
    assert executed[0]["status"] == "resumed_existing"
    assert plan_dict(plan)["database_release"] == "r1"
