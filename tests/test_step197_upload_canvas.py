from __future__ import annotations

from io import BytesIO
from pathlib import Path

from biointel.ui.operational_canvas import canvas_snapshot, safe_canvas_value
from biointel.ui.workflow import MAX_UPLOAD_BYTES, profile_streamlit_upload, stage_streamlit_upload


class _StreamUpload(BytesIO):
    name = "cohort.csv"
    type = "text/csv"

    @property
    def size(self) -> int:
        return len(self.getbuffer())


def test_large_upload_profile_requires_staging_without_a_second_buffer() -> None:
    upload = _StreamUpload(b"sample,value\n" + b"S1,1\n" * 600)
    profile = profile_streamlit_upload(
        upload,
        allowed_extensions=["csv"],
        soft_limit_mb=0.001,
        hard_limit_mb=5,
    )
    assert profile.allowed
    assert profile.within_hard_limit
    assert profile.requires_staging


def test_stage_streamlit_upload_has_a_one_gb_ceiling(tmp_path: Path) -> None:
    upload = _StreamUpload(b"sample,value\nS1,1\n")
    result = stage_streamlit_upload(upload, tmp_path / "cohort.csv", max_bytes=MAX_UPLOAD_BYTES)
    assert Path(result["path"]).is_file()
    assert result["size_bytes"] == upload.size
    assert len(result["sha256"]) == 64


def test_operational_canvas_compacts_paths_and_nested_json() -> None:
    snapshot = canvas_snapshot(
        {
            "status": "completed",
            "progress": 1.0,
            "path": "/private/build/work/demo_input.csv",
            "checkpoint_json": '{"secret": "not-a-user-facing-value"}',
        }
    )
    assert any(metric["label"] == "Status" for metric in snapshot["metrics"])
    assert all("/private/build" not in row["Value"] for row in snapshot["facts"])
    assert safe_canvas_value("path", r"C:\\BioIntel AI\\UserData\\run.csv") == "run.csv"


def test_common_lifecycle_panels_use_canvases_not_raw_json() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/biointel/major_module_standard_v188/ui.py",
        "src/biointel/universal_platform_v189/ui.py",
        "src/biointel/scientific_execution_v190/ui.py",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "render_operational_canvas" in text
        assert "st.json(" not in text
