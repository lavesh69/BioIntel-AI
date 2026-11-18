from __future__ import annotations

import json
import zipfile
from pathlib import Path

from biointel.ui.navigation import PAGE_BY_KEY

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "data" / "module_starter_kits"


def _catalog() -> dict[str, object]:
    return json.loads((LIBRARY / "catalog.json").read_text(encoding="utf-8"))


def test_starter_kit_catalog_is_complete_and_navigable() -> None:
    catalog = _catalog()
    kits = catalog["kits"]
    assert catalog["kit_count"] == len(kits) == 47
    assert set(kits).issubset(PAGE_BY_KEY)


def test_every_starter_kit_is_local_safe_and_crc_clean() -> None:
    catalog = _catalog()
    base = LIBRARY.resolve()
    for page_key, kit in catalog["kits"].items():
        directory = (LIBRARY / kit["directory"]).resolve()
        directory.relative_to(base)
        assert directory.is_dir(), page_key
        assert (directory / "FORMAT_GUIDE.md").is_file(), page_key
        assert (directory / "manifest.json").is_file(), page_key
        assert any(item["role"] == "blank" for item in kit["files"]), page_key
        assert any(item["role"] == "example" for item in kit["files"]), page_key
        assert any(item["role"] == "output" for item in kit["files"]), page_key
        for item in kit["files"]:
            path = (directory / item["name"]).resolve()
            path.relative_to(base)
            assert path.is_file(), path
            assert path.stat().st_size == item["size_bytes"]
            assert path.stat().st_size < 1_000_000, path
        zip_path = (directory / kit["zip"]).resolve()
        zip_path.relative_to(base)
        with zipfile.ZipFile(zip_path) as archive:
            assert archive.testzip() is None, page_key
            assert all(not name.startswith(("/", "\\")) for name in archive.namelist())
            assert all(".." not in Path(name).parts for name in archive.namelist())


def test_starter_library_has_direct_windows_folder_launcher() -> None:
    launcher = ROOT / "OPEN_MODULE_STARTER_KITS_WINDOWS.bat"
    text = launcher.read_text(encoding="utf-8")
    assert "data\\module_starter_kits" in text
