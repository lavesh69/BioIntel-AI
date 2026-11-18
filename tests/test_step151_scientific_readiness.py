from __future__ import annotations

import numpy as np
import pandas as pd

from biointel.biotech.flow_cytometry import (
    GateResult,
    apply_compensation,
    audit_gate_hierarchy,
    derive_compensation_matrix,
    flow_qc,
    flow_release_gate,
    rectangular_gate,
    validate_control_manifest,
)
from biointel.scientific_depth import (
    CAPABILITY_SPECS,
    MODULE_PROFILES,
    assess_evidence_readiness,
    build_evidence_manifest_template,
)


def _flow_events(n: int = 2_000) -> pd.DataFrame:
    rng = np.random.default_rng(151)
    return pd.DataFrame(
        {
            "event_id": [f"E{i:05d}" for i in range(n)],
            "Time": np.arange(n, dtype=float),
            "FSC-A": rng.normal(50_000, 4_000, n),
            "SSC-A": rng.normal(20_000, 3_000, n),
            "CD3-A": rng.lognormal(7.5, 0.35, n),
            "CD19-A": rng.lognormal(7.0, 0.35, n),
        }
    )


def _complete_control_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"control_type": "unstained", "channel": "", "events": 2_000, "panel_version": "PANEL-2", "instrument_id": "CYTO-7"},
            {"control_type": "single_stain", "channel": "CD3-A", "events": 2_000, "panel_version": "PANEL-2", "instrument_id": "CYTO-7"},
            {"control_type": "single_stain", "channel": "CD19-A", "events": 2_000, "panel_version": "PANEL-2", "instrument_id": "CYTO-7"},
            {"control_type": "fmo", "channel": "CD3-A", "events": 2_000, "panel_version": "PANEL-2", "instrument_id": "CYTO-7"},
        ]
    )


def test_all_depth_profiles_have_explicit_six_stage_capability_contracts() -> None:
    assert set(MODULE_PROFILES).issubset(CAPABILITY_SPECS)
    for module_key in MODULE_PROFILES:
        spec = CAPABILITY_SPECS[module_key]
        assert len(spec.stages) >= 6, module_key
        assert any(stage.mode == "external-validation" for stage in spec.stages), module_key
        assert spec.evidence_boundary.strip()


def test_evidence_template_and_demo_source_are_safely_blocked() -> None:
    template = build_evidence_manifest_template("flow_cytometry")
    assert template["schema"] == "biointel.step151.evidence-declaration.v1"
    assert "independent_validation" in template["evidence"]

    data = pd.DataFrame(
        {
            "sample_id": [f"S{i}" for i in range(40)],
            "condition": ["A"] * 20 + ["B"] * 20,
            "signal": np.linspace(0.0, 1.0, 40),
        }
    )
    readiness = assess_evidence_readiness("flow_cytometry", data, source_mode="deterministic demonstration data")
    assert readiness.release_ready is False
    assert any("Demonstration/synthetic" in blocker for blocker in readiness.blockers)


def test_external_evidence_must_be_explicitly_verified() -> None:
    data = pd.DataFrame(
        {
            "sample_id": [f"S{i}" for i in range(60)],
            "condition": ["A"] * 30 + ["B"] * 30,
            "signal": np.linspace(1.0, 2.0, 60),
            "unstained_control": ["CTRL"] * 60,
            "single_stain_control": ["CTRL"] * 60,
            "fmo_control": ["CTRL"] * 60,
            "gating_review": ["reviewed"] * 60,
            "independent_validation": ["report-151"] * 60,
        }
    )
    metadata = {
        "input_sha256": "a" * 64,
        "software_version": "13.3.0",
        "reference_release": "PANEL-2",
        "instrument_qc": "QC-2026-07-13",
        "reviewer": "reviewer-1",
    }
    declared = assess_evidence_readiness("flow_cytometry", data, metadata=metadata, source_mode="uploaded")
    external = declared.requirements.loc[declared.requirements["external"].astype(bool)]
    assert not external.empty
    assert set(external["status"]).issubset({"review", "fail"})
    assert declared.release_ready is False

    verified_keys = external["key"].tolist()
    verified = assess_evidence_readiness(
        "flow_cytometry",
        data,
        metadata={**metadata, "verified_requirements": verified_keys},
        source_mode="uploaded",
    )
    verified_external = verified.requirements.loc[verified.requirements["external"].astype(bool)]
    assert set(verified_external["status"]) == {"pass"}
    assert verified.score >= declared.score


def test_control_manifest_detects_missing_and_complete_controls() -> None:
    incomplete = pd.DataFrame(
        [{"control_type": "unstained", "channel": "", "events": 2_000, "panel_version": "PANEL-2", "instrument_id": "CYTO-7"}]
    )
    audit = validate_control_manifest(incomplete, ["CD3-A", "CD19-A"], require_fmo_channels=["CD3-A"])
    assert audit.summary["release_ready"] is False
    assert "single_stain:CD3-A" in audit.missing_controls
    assert "fmo:CD3-A" in audit.missing_controls

    complete = validate_control_manifest(_complete_control_manifest(), ["CD3-A", "CD19-A"], require_fmo_channels=["CD3-A"])
    assert complete.summary["release_ready"] is True
    assert complete.missing_controls == ()
    assert set(complete.checks["status"]).issubset({"pass"})


def test_compensation_derivation_recovers_known_spillover() -> None:
    rng = np.random.default_rng(152)
    channels = ["CD3-A", "CD19-A"]
    spill = pd.DataFrame([[1.0, 0.08], [0.05, 1.0]], index=channels, columns=channels)
    n = 2_000
    unstained_true = rng.normal(80.0, 4.0, (n, 2))
    unstained = pd.DataFrame(unstained_true @ spill.to_numpy().T, columns=channels)

    cd3_true = np.column_stack([rng.normal(10_000.0, 500.0, n), rng.normal(80.0, 4.0, n)])
    cd19_true = np.column_stack([rng.normal(80.0, 4.0, n), rng.normal(8_000.0, 400.0, n)])
    controls = {
        "CD3-A": pd.DataFrame(cd3_true @ spill.to_numpy().T, columns=channels),
        "CD19-A": pd.DataFrame(cd19_true @ spill.to_numpy().T, columns=channels),
    }
    derived, provenance = derive_compensation_matrix(controls, channels, unstained_events=unstained)
    assert np.allclose(derived.to_numpy(), spill.to_numpy(), atol=0.015)
    assert provenance["method"] == "robust single-stain median spillover"

    mixed_true = np.column_stack([rng.normal(5_000.0, 200.0, n), rng.normal(4_000.0, 200.0, n)])
    observed = pd.DataFrame(mixed_true @ spill.to_numpy().T, columns=channels)
    corrected, _ = apply_compensation(observed, channels, derived)
    assert np.allclose(corrected[channels].to_numpy(), mixed_true, atol=35.0)


def test_gate_hierarchy_and_release_gate_are_fail_closed() -> None:
    events = _flow_events()
    gate = rectangular_gate(
        events,
        "FSC-A",
        "SSC-A",
        x_min=35_000,
        x_max=65_000,
        y_min=10_000,
        y_max=30_000,
        name="Cells",
    )
    audit = audit_gate_hierarchy([gate])
    assert audit.iloc[0]["status"] == "pass"

    invalid = GateResult(
        name="Bad child",
        parent="Missing parent",
        mask=gate.mask,
        events=gate.events,
        summary={**gate.summary, "gate": "Bad child", "parent": "Missing parent"},
    )
    invalid_audit = audit_gate_hierarchy([invalid])
    assert invalid_audit.iloc[0]["status"] == "block"

    qc = flow_qc(events, event_id_column="event_id", time_column="Time", channels=["FSC-A", "SSC-A", "CD3-A", "CD19-A"])
    controls = validate_control_manifest(_complete_control_manifest(), ["CD3-A", "CD19-A"], require_fmo_channels=["CD3-A"])
    blocked = flow_release_gate(qc, controls, {"applied": True, "method": "linear spillover inversion"}, [gate], source_mode="uploaded")
    assert blocked.release_ready is False
    assert "Compensation provenance" in blocked.blockers
    assert "Instrument QC" in blocked.blockers
    assert "Independent reviewer" in blocked.blockers

    passed = flow_release_gate(
        qc,
        controls,
        {"applied": True, "method": "instrument/export matrix", "matrix_source": "instrument/export", "control_manifest_sha256": controls.summary["manifest_sha256"]},
        [gate],
        source_mode="uploaded",
        reviewer="reviewer-151",
        instrument_qc_confirmed=True,
    )
    assert passed.release_ready is True
    assert passed.blockers == ()


def test_scientific_portfolio_manifest_covers_every_registered_profile() -> None:
    from biointel.scientific_depth import scientific_portfolio_catalog, scientific_portfolio_manifest, scientific_portfolio_summary

    catalog = scientific_portfolio_catalog()
    summary = scientific_portfolio_summary(catalog)
    manifest = scientific_portfolio_manifest()
    assert len(catalog) == len(MODULE_PROFILES)
    assert summary["all_contracts_complete"] is True
    assert summary["complete_contracts"] == summary["modules"]
    assert manifest["summary"]["modules"] == len(MODULE_PROFILES)
    assert len(manifest["modules"]) == len(MODULE_PROFILES)
    assert all(item["evidence_template"]["schema"] == "biointel.step151.evidence-declaration.v1" for item in manifest["modules"])


def test_step151_command_center_is_present_and_fail_closed() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "pages/227_Scientific_Readiness_Command_Center.py").read_text(encoding="utf-8")
    for token in ("Scientific Readiness Command Center", "assess_evidence_readiness", "scientific_portfolio_manifest", "Release ready"):
        assert token in source
