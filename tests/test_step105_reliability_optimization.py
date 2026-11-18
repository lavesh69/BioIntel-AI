from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd

from biointel.biotech.lab_import import normalize_instrument_export
from biointel.nextgen.services import NextGenStore, inspect_file_bytes

ROOT = Path(__file__).resolve().parents[1]


def test_release_surfaces_are_synchronised():
    version = (ROOT / "VERSION").read_text().strip()
    assert version == "13.2.0"
    assert json.loads((ROOT / "STEP106_RELEASE.json").read_text())["version"] == version
    assert json.loads((ROOT / "platform/desktop/package.json").read_text())["version"] == version
    assert json.loads((ROOT / "platform/mobile/package.json").read_text())["version"] == version
    assert json.loads((ROOT / "store/release-manifest.json").read_text())["release_version"] == version
    assert json.loads((ROOT / "store/model-manifest.json").read_text())["version"] == version


def test_expansion_pages_have_one_page_theme_bootstrap_and_renderers_do_not_repeat_it():
    pages = sorted((ROOT / "pages").glob("*.py"))
    expansion = [p for p in pages if 112 <= int(p.name.split("_", 1)[0]) <= 163]
    assert len(expansion) == 52
    for page in expansion:
        text = page.read_text(encoding="utf-8")
        assert "apply_theme()" in text, page.name
    for relative in ("src/biointel/expansion/renderer.py", "src/biointel/nextgen/renderer.py"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "apply_theme()" not in text


def test_generic_lab_tables_keep_their_original_schema():
    source = pd.DataFrame({"sample": ["A"], "value": [1.5], "batch": ["B1"]})
    result = normalize_instrument_export(source)
    assert list(result.columns) == list(source.columns)
    assert "instrument_format" not in result.columns


def test_file_inspector_handles_nested_json_and_headerless_reactome():
    nested = json.dumps({"metadata": {"source": "demo"}, "records": [{"id": 1, "tags": ["a"]}, {"id": 1, "tags": ["a"]}]}).encode()
    report = inspect_file_bytes(nested, "nested.json")
    assert report.detected_format == "JSON"
    assert report.preview

    reactome = b"R-HSA-123\tExample pathway\tHomo sapiens\nR-HSA-456\tSecond pathway\tHomo sapiens\n"
    pathway = inspect_file_bytes(reactome, "ReactomePathways.txt")
    assert pathway.detected_format == "Delimited table"
    assert pathway.preview[0]["pathway_id"] == "R-HSA-123"


def _plugin_archive(minimum: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("plugin.json", json.dumps({"name": f"plugin-{minimum}", "version": "1", "min_biointel_version": minimum, "permissions": []}))
        archive.writestr("module.py", "x=1")
    return buffer.getvalue()


def test_plugin_minimum_version_uses_semantic_comparison(tmp_path: Path):
    store = NextGenStore(tmp_path)
    compatible = store.inspect_plugin(_plugin_archive("13.2.0"), "compatible.zip")
    incompatible = store.inspect_plugin(_plugin_archive("13.3.0"), "incompatible.zip")
    assert compatible["safe_to_register"]
    assert not incompatible["safe_to_register"]
    assert any("incompatible" in finding.lower() for finding in incompatible["findings"])


def test_windows_and_upload_hardening_are_present():
    config = (ROOT / ".streamlit/config.toml").read_text(encoding="utf-8")
    installer = (ROOT / "INSTALL_WINDOWS.bat").read_text(encoding="utf-8")
    assert "maxUploadSize = 1024" in config
    assert "maxMessageSize = 1024" in config
    assert "verify_windows_wheelhouse.py" in installer
