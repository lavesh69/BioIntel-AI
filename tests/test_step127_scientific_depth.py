from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from biointel.step127 import ALL_MODULE_SPECS, assess_module, bh_fdr, build_protected_plan, format_support, statistical_audit
from biointel.step127.domain_checks import (
    audit_fastq_pairs,
    build_design_matrix,
    filter_qpcr_roles,
    normalize_variant,
    safe_calibration_inverse,
    split_bioprocess_batches,
    validate_column_mapping,
)
from biointel.step127.plans import PlanValidationError
from biointel.step127.references import audit_reference_manifest, template_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_version_and_module_counts() -> None:
    assert (ROOT / "VERSION").read_text().strip() == "13.2.0"
    counts = Counter(spec.domain for spec in ALL_MODULE_SPECS)
    assert counts == {"Bioinformatics": 17, "Discovery": 9, "Lab Analytics": 7}
    assert len({spec.key for spec in ALL_MODULE_SPECS}) == 33
    assert len({spec.page_path for spec in ALL_MODULE_SPECS}) == 33


def test_all_specs_assess_and_pages_exist() -> None:
    for spec in ALL_MODULE_SPECS:
        assert (ROOT / spec.page_path).is_file()
        assessment = assess_module(spec.key)
        assert assessment.tier in {"A", "B", "C"}
        assert 0 <= assessment.execution_readiness <= 1
        assert len(assessment.stages) == len(spec.stages)
        assert assessment.evidence_boundary


def test_unlocked_pages_receive_full_panel_and_locked_pages_are_unchanged() -> None:
    for spec in ALL_MODULE_SPECS:
        source = (ROOT / spec.page_path).read_text(encoding="utf-8")
        marker = f"STEP127_SCIENTIFIC_DEPTH_{spec.key.upper()}"
        if spec.locked_source:
            assert marker not in source
        else:
            assert marker in source
    expected = {
        "pages/6_DTI_Predictor.py": "10767f9c1654df364b2321b743117f9367e24f1d17c6642ace8e378c2fedcf1a",
        "pages/109_Lab_Instrument_Import_Center.py": "6b8b24f0549593cbe96e6baabc1929b208772d21f48e92ec4630c6835a91d73f",
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_command_center_and_sidebar_integration() -> None:
    assert (ROOT / "pages/172_Scientific_Depth_Command_Center.py").is_file()
    theme = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    assert "render_step127_sidebar_for_page" in theme


def test_native_format_support() -> None:
    assert format_support("sample.h5ad")["mode"] == "adapter"
    assert format_support("reads.fastq.gz")["mode"] == "native"
    assert format_support("variants.bcf")["mode"] == "adapter"
    assert format_support("unknown.xyz")["mode"] == "staged"


def test_statistical_audit_and_fdr() -> None:
    frame = pd.DataFrame({
        "group": ["A", "A", "A", "B", "B", "B"],
        "sample": ["a1", "a2", "a3", "b1", "b2", "b3"],
        "value": [1.0, 1.2, 0.9, 2.0, 2.2, 2.1],
    })
    audit = statistical_audit(frame, group_column="group", replicate_column="sample")
    assert audit.status in {"ready", "review"}
    assert audit.groups == 2
    adjusted = bh_fdr([0.01, 0.04, 0.2])
    assert np.all(adjusted >= np.array([0.01, 0.04, 0.2]))
    assert np.all(adjusted <= 1)


def test_fastq_pair_and_variant_checks() -> None:
    audit = audit_fastq_pairs(["S1_R1.fastq.gz", "S1_R2.fastq.gz", "S2_R1.fastq.gz"])
    assert audit.paired == 1
    assert audit.missing_mates == ("S2",)
    assert normalize_variant("chr1", 100, "AT", "AC") == ("chr1", 101, "T", "C")


def test_design_qpcr_calibration_and_bioprocess_safeguards() -> None:
    metadata = pd.DataFrame({"group": ["A", "A", "B", "B"], "batch": ["X", "Y", "X", "Y"]})
    design = build_design_matrix(metadata, group="group", covariates=("batch",))
    assert design.shape[0] == 4
    roles = filter_qpcr_roles(pd.DataFrame({"role": ["target", "reference", "ignore", "NTC"], "ct": [20, 21, 22, 40]}), role_column="role")
    assert len(roles["ignore"]) == 1
    assert len(roles["ntc"]) == 1
    value, label = safe_calibration_inverse(12, response_min=1, response_max=10, inverse_function=lambda x: x)
    assert value is None and "Above" in label
    batches = split_bioprocess_batches(
        pd.DataFrame({"batch": ["A", "A", "A", "B", "B", "B"], "time": [0, 1, 2, 0, 1, 2], "x": range(6)}),
        batch_column="batch", time_column="time",
    )
    assert set(batches) == {"A", "B"}


def test_duplicate_mapping_is_blocked() -> None:
    with pytest.raises(ValueError):
        validate_column_mapping({"target_ct": "Ct", "reference_ct": "Ct"})


def test_protected_plans_are_bounded_and_shell_free(tmp_path: Path) -> None:
    plan = build_protected_plan(
        "fastq_qc",
        "fastp",
        [tmp_path / "R1.fastq.gz", tmp_path / "R2.fastq.gz"],
        tmp_path / "out",
        parameters={"threads": 4},
    )
    assert plan.argv[0] == "fastp"
    assert "--thread" in plan.argv
    assert not any(";" in item or "&&" in item for item in plan.argv)
    with pytest.raises(PlanValidationError):
        build_protected_plan("fastq_qc", "rm", [tmp_path / "x"], tmp_path / "out")
    with pytest.raises(PlanValidationError):
        build_protected_plan("fastq_qc", "fastp", [tmp_path / "x"], tmp_path / "out2", parameters={"threads": 1000})


def test_tool_manifest_expansion() -> None:
    payload = json.loads((ROOT / "config/advanced_tools_manifest.json").read_text())
    ids = {item["id"] for item in payload["tools"]}
    assert len(payload["tools"]) >= 86
    assert {"dorado", "interproscan", "signalp6", "deeptmhmm", "nextclade", "pangolin", "sourmash"}.issubset(ids)


def test_reference_contract_requires_version_checksum_and_licence(tmp_path: Path) -> None:
    template = template_manifest("variant_annotation")
    assert template["references"]
    audit = audit_reference_manifest("variant_annotation", template)
    assert not audit.ready
    assert audit.missing or audit.invalid
