from __future__ import annotations

import gzip
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from biointel.io.uploads import UploadReadError, UploadSchemaError, read_uploaded_table_bytes
from biointel.projects.ppi import (
    demo_ppi_pairs,
    load_ppi_model,
    score_candidate_pairs,
    serialize_ppi_model,
    train_and_score_ppi_classifier,
)
from biointel.training.model_artifact import load_model_artifact_cached
from biointel.utils.exceptions import ModelNotFoundError


def test_csv_delimiter_and_utf8_bom_are_detected() -> None:
    payload = "name;value\nA;1\nB;2\n".encode("utf-8-sig")
    result = read_uploaded_table_bytes(payload, "table.csv")
    assert result.separator == ";"
    assert result.encoding == "utf-8-sig"
    assert result.frame.to_dict("records") == [{"name": "A", "value": 1}, {"name": "B", "value": 2}]


def test_gzip_table_is_read_and_truncated_upload_is_rejected() -> None:
    payload = gzip.compress(b"id\tvalue\nA\t1\n")
    result = read_uploaded_table_bytes(payload, "table.tsv.gz")
    assert result.frame.loc[0, "id"] == "A"
    with pytest.raises(UploadReadError, match="gzip"):
        read_uploaded_table_bytes(payload[:10], "broken.tsv.gz")


def test_single_table_zip_is_supported_and_traversal_is_blocked() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("cohort/data.csv", "id,value\nA,1\n")
    result = read_uploaded_table_bytes(buffer.getvalue(), "cohort.zip")
    assert result.archive_member == "cohort/data.csv"
    assert result.frame.shape == (1, 2)

    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../data.csv", "id,value\nA,1\n")
    with pytest.raises(UploadReadError, match="unsafe path"):
        read_uploaded_table_bytes(unsafe.getvalue(), "unsafe.zip")


def test_duplicate_headers_and_cell_limits_fail_actionably() -> None:
    with pytest.raises(UploadSchemaError, match="Duplicate column"):
        read_uploaded_table_bytes(b"id,id\nA,1\n", "duplicate.csv")
    with pytest.raises(UploadReadError, match="interactive limit"):
        read_uploaded_table_bytes(b"a,b\n1,2\n3,4\n", "large.csv", max_cells=3)


def test_excel_upload_is_supported() -> None:
    buffer = io.BytesIO()
    pd.DataFrame({"sample": ["S1"], "value": [2.5]}).to_excel(buffer, index=False)
    result = read_uploaded_table_bytes(buffer.getvalue(), "study.xlsx")
    assert result.frame.loc[0, "sample"] == "S1"
    assert result.separator == "worksheet"


def test_ppi_bundle_is_checksum_bound_and_legacy_is_blocked() -> None:
    training = demo_ppi_pairs(80)
    candidates = training.drop(columns=["label"]).head(8)
    result, expected = train_and_score_ppi_classifier(
        training,
        candidates,
        algorithm="Logistic regression",
    )
    bundle = serialize_ppi_model(result)
    assert bundle.startswith(b"PK")
    loaded = load_ppi_model(bundle)
    observed = score_candidate_pairs(loaded, candidates)
    assert observed["predicted_label"].tolist() == expected["predicted_label"].tolist()

    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        model = bytearray(archive.read("model.joblib"))
    model[-1] ^= 1
    tampered = io.BytesIO()
    with zipfile.ZipFile(tampered, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("model.joblib", model)
    with pytest.raises(ValueError, match="checksum"):
        load_ppi_model(tampered.getvalue())
    with pytest.raises(ValueError, match="Legacy raw"):
        load_ppi_model(b"not-a-bundle")


def test_missing_cached_model_raises_domain_error(tmp_path: Path) -> None:
    with pytest.raises(ModelNotFoundError, match="not found"):
        load_model_artifact_cached(tmp_path / "missing.joblib", trusted_root=tmp_path)
