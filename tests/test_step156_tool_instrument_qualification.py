from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from biointel.biotech.instrument_qualification import REQUIRED_METADATA, audit_instrument_import
from biointel.biotech.lab_import import read_lab_table
from biointel.expansion.catalog import MODULE_BY_KEY
from biointel.expansion.renderer import _analyse_detailed, _demo_frame, _normalise
from biointel.native.engines import EngineStatus
from biointel.native.qualification import qualify_engine


class Upload:
    def __init__(self, name: str, payload: bytes):
        self.name = name
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


def _metadata() -> dict[str, str]:
    return {
        "instrument_id": "QS7-01",
        "serial_number": "SN-123",
        "software_version": "2.7.0",
        "method_id": "QPCR-001",
        "method_version": "4",
        "operator": "qualified_user",
        "run_date_utc": "2026-07-13T08:00:00Z",
        "calibration_date_utc": "2026-01-01T00:00:00Z",
        "calibration_due_utc": "2027-01-01T00:00:00Z",
        "sop_version": "SOP-QPCR-4",
    }


def test_instrument_qualification_passes_only_with_complete_evidence() -> None:
    raw = b"Well Position,Sample Name,Target Name,Ct Mean\nA1,S1,GAPDH,22.1\n"
    frame = pd.DataFrame({"well": ["A1"], "sample": ["S1"], "gene": ["GAPDH"], "ct": [22.1]})
    result = audit_instrument_import(
        frame,
        raw_bytes=raw,
        metadata=_metadata(),
        source_map={"well": "Well Position", "sample": "Sample Name", "gene": "Target Name", "ct": "Ct Mean"},
        profile="QuantStudio",
        reviewer="qa-reviewer",
        reviewed_at_utc="2026-07-13T09:00:00Z",
        now_utc="2026-07-13T08:30:00Z",
    )
    assert result.qualification_status == "Qualified"
    assert result.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert not result.blockers


def test_instrument_qualification_blocks_duplicate_mapping_and_missing_metadata() -> None:
    result = audit_instrument_import(
        pd.DataFrame({"value": [1.0]}),
        raw_bytes=b"value\n1\n",
        metadata={},
        source_map={"target": "value", "reference": "value"},
        profile="Generic table",
        reviewer="",
        reviewed_at_utc="",
        now_utc="2026-07-13T08:30:00Z",
    )
    assert result.qualification_status == "Blocked"
    assert result.duplicate_semantic_mappings == ("value",)
    assert set(REQUIRED_METADATA).issubset(set(result.missing_metadata))
    assert any("profile" in blocker.lower() for blocker in result.blockers)


def test_read_lab_table_attaches_raw_hash_and_fail_closed_qualification() -> None:
    payload = b"Well Position,Sample Name,Target Name,Ct Mean\nA1,S1,GAPDH,22.1\n"
    frame = read_lab_table(Upload("quantstudio.csv", payload))
    assert frame.attrs["raw_sha256"] == hashlib.sha256(payload).hexdigest()
    assert frame.attrs["instrument_qualification"]["qualification_status"] == "Blocked"
    assert frame.attrs["instrument_profile"] == "QuantStudio"


def test_engine_qualification_requires_reference_checksum_licence_and_reviewer(tmp_path: Path, monkeypatch) -> None:
    reference = tmp_path / "ref.fa"
    reference.write_text(">chr1\nACGT\n", encoding="utf-8")
    digest = hashlib.sha256(reference.read_bytes()).hexdigest()

    def available(key: str, *, timeout_seconds: float = 5.0) -> EngineStatus:
        return EngineStatus(
            key=key,
            label="BCFtools",
            available=True,
            executable="bcftools",
            version="1.20",
            category="Genomics",
            capabilities=("VCF normalization",),
            required_databases=("Reference FASTA",),
            gpu_optional=False,
            note="",
        )

    monkeypatch.setattr("biointel.native.qualification.detect_engine", available)
    qualified = qualify_engine(
        "bcftools",
        reference_assets={
            "Reference FASTA": {
                "path": str(reference),
                "sha256": digest,
                "release": "GRCh38.p14",
                "licence": "Reference distribution terms",
                "licence_accepted": True,
            }
        },
        reviewer="bioinformatics-lead",
        reviewed_at_utc="2026-07-13T09:00:00Z",
    )
    assert qualified.qualification_status == "Qualified"
    assert qualified.qualified_reference_count == 1

    blocked = qualify_engine("bcftools", reference_assets={}, reviewer="", reviewed_at_utc="")
    assert blocked.qualification_status == "Blocked"
    assert blocked.blockers


def test_lims_chain_reports_cycles_duplicates_and_backward_compatible_table() -> None:
    module = MODULE_BY_KEY["lims_eln_chain"]
    data = _normalise(_demo_frame(module, 32), module)
    data.loc[0, "sample_id"] = "DUP"
    data.loc[1, "sample_id"] = "DUP"
    data.loc[2, "sample_id"] = "CYCLE-A"
    data.loc[2, "parent_id"] = "CYCLE-B"
    data.loc[3, "sample_id"] = "CYCLE-B"
    data.loc[3, "parent_id"] = "CYCLE-A"
    data.loc[4, "location"] = ""
    _, summary, _, extras = _analyse_detailed(data, module, 0.70)
    assert "lineage_integrity" in extras
    assert "sample_lineage_integrity" in extras
    assert "lineage_roots" in extras
    assert summary["duplicate_or_blank_sample_ids"] >= 2
    assert summary["lineage_cycle_samples"] >= 2
    assert summary["lineage_release_blocked_records"] >= 4
