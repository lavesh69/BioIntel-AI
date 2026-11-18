from __future__ import annotations

import numpy as np
import pandas as pd

from biointel.scientific_depth import (
    MODULE_PROFILES,
    is_native_engine,
    native_engine_status,
    native_portfolio_manifest,
    native_workflow_catalog,
    run_native_workflow,
    scientific_portfolio_summary,
)


def test_every_scientific_profile_has_a_locally_available_native_engine() -> None:
    assert len(MODULE_PROFILES) == 80
    for module_key, profile in MODULE_PROFILES.items():
        native = [engine for engine in profile.engines if is_native_engine(engine)]
        assert native == [f"biointel_native::{module_key}"]
        status = native_engine_status(native[0])
        assert status["available"] is True
        assert "Built-in Python workflow" in status["detected_path_or_package"]


def test_native_portfolio_covers_all_profiles_and_is_fail_honest() -> None:
    catalog = native_workflow_catalog()
    manifest = native_portfolio_manifest()
    summary = scientific_portfolio_summary()
    assert len(catalog) == len(MODULE_PROFILES)
    assert catalog["workflow_key"].is_unique
    assert manifest["workflows"] == len(MODULE_PROFILES)
    assert manifest["families"] >= 15
    assert manifest["policy"]["specialist_confirmatory_pipeline_still_required"] is True
    assert summary["native_engines"] == len(MODULE_PROFILES)
    assert summary["all_native_workflows_available"] is True


def test_flow_native_core_produces_channel_qc_drift_and_transform() -> None:
    rng = np.random.default_rng(152)
    n = 800
    data = pd.DataFrame(
        {
            "event_id": [f"E{i}" for i in range(n)],
            "Time": np.arange(n),
            "FSC-A": rng.normal(50_000, 3_000, n),
            "SSC-A": rng.normal(20_000, 2_000, n),
            "CD3-A": rng.lognormal(7.2, 0.3, n),
        }
    )
    result = run_native_workflow("flow_cytometry", data)
    assert result.status in {"pass", "review"}
    assert not result.tables["channel_qc"].empty
    assert not result.tables["time_drift"].empty
    assert not result.tables["transformed_preview"].empty
    assert result.provenance["deterministic"] is True


def test_metabolomics_native_core_filters_blank_qc_and_runs_statistics() -> None:
    rng = np.random.default_rng(153)
    rows = []
    for feature in ["M1", "M2", "M3"]:
        for index in range(10):
            rows.append(
                {
                    "feature": feature,
                    "sample": f"A{index}",
                    "group": "A",
                    "sample_type": "sample",
                    "injection_order": index,
                    "intensity": rng.normal(100 if feature != "M2" else 50, 4),
                }
            )
            rows.append(
                {
                    "feature": feature,
                    "sample": f"B{index}",
                    "group": "B",
                    "sample_type": "sample",
                    "injection_order": index + 20,
                    "intensity": rng.normal(160 if feature == "M1" else 55, 4),
                }
            )
        for index in range(5):
            rows.append({"feature": feature, "sample": f"QC{index}", "group": "QC", "sample_type": "pooled_qc", "injection_order": index + 40, "intensity": rng.normal(105, 2)})
            rows.append({"feature": feature, "sample": f"BL{index}", "group": "BL", "sample_type": "blank", "injection_order": index + 50, "intensity": rng.normal(3, 0.5)})
    result = run_native_workflow("metabolomics_lipidomics", pd.DataFrame(rows))
    assert not result.tables["feature_qc"].empty
    assert not result.tables["blank_audit"].empty
    assert not result.tables["pooled_qc"].empty
    assert not result.tables["feature_statistics"].empty
    assert "fdr" in result.tables["feature_statistics"].columns


def test_spatial_native_core_computes_neighborhoods_and_autocorrelation() -> None:
    x, y = np.meshgrid(np.arange(12), np.arange(12))
    data = pd.DataFrame(
        {
            "spot": [f"S{i}" for i in range(x.size)],
            "x": x.ravel(),
            "y": y.ravel(),
            "sample": ["P1"] * (x.size // 2) + ["P2"] * (x.size - x.size // 2),
            "signal": (x + y).ravel().astype(float),
        }
    )
    result = run_native_workflow("spatial_omics_pathology", data)
    assert not result.tables["neighborhood_qc"].empty
    assert not result.tables["spatial_autocorrelation"].empty
    assert result.tables["spatial_autocorrelation"].iloc[0]["moran_i_knn"] > 0


def test_population_native_core_calculates_call_rate_maf_and_hwe() -> None:
    rows = []
    for variant in ["v1", "v2"]:
        for sample in range(60):
            gt = "0/0" if sample < 30 else ("0/1" if sample < 50 else "1/1")
            rows.append({"variant_id": variant, "sample_id": f"S{sample}", "genotype": gt})
    result = run_native_workflow("population_gwas", pd.DataFrame(rows))
    table = result.tables["variant_qc"]
    assert len(table) == 2
    assert table["call_rate"].eq(1.0).all()
    assert table["maf"].between(0, 0.5).all()
    assert table["hwe_p"].notna().all()


def test_survival_native_core_generates_km_and_logrank() -> None:
    rng = np.random.default_rng(154)
    n = 100
    data = pd.DataFrame(
        {
            "time": np.r_[rng.exponential(8, n // 2), rng.exponential(15, n // 2)],
            "event": rng.binomial(1, 0.7, n),
            "group": ["A"] * (n // 2) + ["B"] * (n // 2),
        }
    )
    result = run_native_workflow("clinical_biomarker_survival", data)
    assert not result.tables["kaplan_meier"].empty
    assert len(result.tables["group_summary"]) == 2
    assert not result.tables["logrank"].empty
    assert result.tables["logrank"]["p_value"].between(0, 1).all()


def test_pharmacovigilance_native_core_computes_ror_prr_and_flags() -> None:
    rows = []
    for i in range(50):
        rows.append({"report_id": f"R-AE-{i}", "drug": "DrugA", "event": "EventX"})
    for i in range(10):
        rows.append({"report_id": f"R-AY-{i}", "drug": "DrugA", "event": "EventY"})
    for i in range(5):
        rows.append({"report_id": f"R-BX-{i}", "drug": "DrugB", "event": "EventX"})
    for i in range(100):
        rows.append({"report_id": f"R-BY-{i}", "drug": "DrugB", "event": "EventY"})
    result = run_native_workflow("pharmacovigilance_intelligence", pd.DataFrame(rows))
    table = result.tables["disproportionality_signals"]
    assert {"ror", "prr", "ror_ci_low", "signal_flag"}.issubset(table.columns)
    assert bool(table.loc[(table["drug"] == "DrugA") & (table["event"] == "EventX"), "signal_flag"].iloc[0])


def test_privacy_model_assurance_and_trial_workflows_are_executable() -> None:
    privacy = pd.DataFrame(
        {
            "age_band": ["20-29"] * 6 + ["30-39"] * 6,
            "region": ["N"] * 6 + ["S"] * 6,
            "diagnosis": ["A", "A", "B", "B", "C", "C"] * 2,
        }
    )
    privacy_result = run_native_workflow(
        "synthetic_data_privacy",
        privacy,
        metadata={"quasi_identifiers": ["age_band", "region"], "sensitive_attribute": "diagnosis"},
    )
    assert privacy_result.metrics.loc[privacy_result.metrics["metric"] == "minimum_k", "value"].iloc[0] == 6

    assurance = pd.DataFrame(
        {
            "y_true": [0, 0, 0, 1, 1, 1, 0, 1] * 8,
            "y_score": [0.1, 0.2, 0.3, 0.7, 0.8, 0.9, 0.4, 0.6] * 8,
            "site": ["A"] * 32 + ["B"] * 32,
        }
    )
    assurance_result = run_native_workflow("explainable_ai_assurance", assurance)
    assert not assurance_result.tables["performance"].empty
    assert not assurance_result.tables["calibration"].empty

    trial = pd.DataFrame(
        {
            "subject_id": [f"P{i}" for i in range(80)],
            "arm": ["Control"] * 40 + ["Treatment"] * 40,
            "outcome": np.r_[np.linspace(0, 1, 40), np.linspace(0.5, 1.5, 40)],
        }
    )
    trial_result = run_native_workflow("synthetic_cohort_trial", trial)
    assert len(trial_result.tables["arm_balance"]) == 2
    assert not trial_result.tables["effect_estimate"].empty


def test_native_workflow_fails_closed_on_wrong_schema() -> None:
    result = run_native_workflow("clinical_biomarker_survival", pd.DataFrame({"sample": ["A", "B"]}))
    assert result.status == "fail"
    assert result.summary["checks_failed"] >= 1
    assert result.summary["specialist_pipeline_required_for_confirmatory_use"] is True


def test_all_80_native_workflows_execute_their_runnable_demo_without_crashing() -> None:
    from biointel.scientific_depth import native_input_template

    failures: dict[str, str] = {}
    for module_key in MODULE_PROFILES:
        demo = native_input_template(module_key, demonstration=True)
        metadata = {}
        if module_key == "synthetic_data_privacy":
            metadata = {"quasi_identifiers": ["age_band", "region"], "sensitive_attribute": "diagnosis"}
        result = run_native_workflow(module_key, demo, metadata=metadata)
        if result.status == "fail":
            failures[module_key] = "; ".join(result.checks.loc[result.checks["status"] == "fail", "detail"].astype(str).tolist())
        assert result.summary["rows_analyzed"] > 0
        assert result.provenance["input_sha256"]
        assert result.provenance["deterministic"] is True
    assert failures == {}


def test_structural_causal_and_network_native_families_generate_domain_outputs() -> None:
    from biointel.scientific_depth import native_input_template

    structural = run_native_workflow("docking_dynamics", native_input_template("docking_dynamics", demonstration=True))
    assert not structural.tables["molecular_descriptors"].empty
    assert {"molecular_weight", "logp", "tpsa"}.issubset(structural.tables["molecular_descriptors"].columns)

    causal = run_native_workflow("causal_perturbation", native_input_template("causal_perturbation", demonstration=True))
    assert not causal.tables["causal_summary"].empty
    assert causal.tables["causal_summary"]["ivw_estimate"].notna().all()

    network = run_native_workflow("knowledge_graph_core", native_input_template("knowledge_graph_core", demonstration=True))
    assert not network.tables["node_centrality"].empty
    assert network.metrics.loc[network.metrics["metric"] == "connected_components", "value"].iloc[0] >= 1
