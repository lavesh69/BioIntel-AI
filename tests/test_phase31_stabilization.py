from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from biointel.training.trainers import (
    TrainingConfig,
    TrainingError,
    _make_estimator,
    train_dti_model,
)
from scripts.step207_install_external_scientific_tools import safe_extract_zip


def test_dti_parallelism_is_windows_safe_and_explicit() -> None:
    estimator = _make_estimator(TrainingConfig())
    assert estimator.n_jobs == 1
    with pytest.raises(TrainingError, match="parallel_jobs"):
        train_dti_model(pd.DataFrame(), TrainingConfig(parallel_jobs=0))


def test_external_tool_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    destination = tmp_path / "tools"
    escaped = tmp_path / "escaped.txt"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escaped.txt", "must not be written")

    with pytest.raises(ValueError, match="Unsafe archive path"):
        safe_extract_zip(archive_path, destination)

    assert not escaped.exists()


def test_external_tool_archive_extracts_bounded_regular_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "safe.zip"
    destination = tmp_path / "tools"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("bundle/tool.exe", b"verified fixture")

    safe_extract_zip(archive_path, destination)

    assert (destination / "bundle" / "tool.exe").read_bytes() == b"verified fixture"
