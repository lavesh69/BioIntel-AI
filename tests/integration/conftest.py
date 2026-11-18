from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def isolated_workspace(tmp_path: Path) -> Path:
    for name in ("data", "reports", "models", "cache"):
        (tmp_path / name).mkdir()
    return tmp_path
