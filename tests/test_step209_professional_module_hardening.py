from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from biointel.demo_coverage_v209 import build_demo_bundle
from biointel.module_features_v208.artifacts_v209 import build_result_bundle
from biointel.module_features_v208.demos import demo_payload
from biointel.module_features_v208.ingestion_v209 import read_zip_tables_bytes, structured_payload_from_zip
from biointel.module_features_v208.execution import execute_feature
from biointel.module_features_v208.neuro import NEURO_V208_FEATURES
from biointel.module_features_v208.visuals import figures_for_result
from biointel.module_runtime_v207.core import PROTECTED_PAGE_PATHS, TARGET_CATEGORIES
from biointel.neuro_cns.catalog import MODULES
from biointel.scientific_resources_v209.catalog import resources_for_module, validate_resource_catalog
from biointel.ui.navigation import PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def _target_pages():
    return [
        page
        for page in PAGE_CATALOG
        if page.category in TARGET_CATEGORIES
        and page.path.startswith("pages/")
        and page.path not in PROTECTED_PAGE_PATHS
    ]


def test_resource_catalog_is_safe_and_covers_all_target_pages_and_neuro_modules() -> None:
    assert validate_resource_catalog() == []
    pages = _target_pages()
    assert pages
    assert len({page.path for page in pages}) == len(pages)
    for page in pages:
        resources = resources_for_module(page.key, page.title, page.category)
        assert resources, page.key
        assert all(resource.url("TP53").startswith("https://") for resource in resources)
    assert len(MODULES) == 41
    for module in MODULES:
        assert resources_for_module(module.key, module.title, "Neuro/CNS"), module.key


def test_generated_demo_bundles_are_labelled_safe_and_cover_target_modules() -> None:
    for page in _target_pages():
        bundle = build_demo_bundle(page.key, page.title, page.category)
        assert bundle.content
        assert bundle.sha256 == hashlib.sha256(bundle.content).hexdigest()
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
            assert archive.testzip() is None
            assert "manifest.json" in archive.namelist()
            assert "README.md" in archive.namelist()
            assert all(not name.startswith(("/", "\\")) and ".." not in Path(name).parts for name in archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["source_kind"] == "deterministic_synthetic_demo_input"
            assert manifest["clinical_release_eligible"] is False
            assert "synthetic" in manifest["scientific_boundary"].lower()


def test_every_neuro_module_has_downloadable_demo_input() -> None:
    for module in MODULES:
        bundle = build_demo_bundle(module.key, module.title, "Neuro/CNS")
        assert bundle.content and bundle.archive_name.endswith(".zip")


def test_all_step208_neuro_workflows_have_multiple_calculated_visuals() -> None:
    assert len(NEURO_V208_FEATURES) == 17
    for feature_key, _title, _description in NEURO_V208_FEATURES:
        result = execute_feature("Neuro/CNS", feature_key, demo_payload(feature_key))
        figures = figures_for_result(feature_key, result)
        assert len(figures) >= 2, feature_key


def test_professional_ui_has_explicit_provenance_and_fail_closed_errors() -> None:
    ui = (ROOT / "src/biointel/module_features_v208/ui.py").read_text(encoding="utf-8")
    runtime = (ROOT / "src/biointel/module_runtime_v207/ui.py").read_text(encoding="utf-8")
    assert "Labelled synthetic demo" in ui
    assert "Upload local data" in ui
    assert "will not silently substitute demo data" in ui
    assert "write_runtime_error" in ui
    assert "execute_feature" in ui
    assert "complete result & provenance bundle" in ui
    assert "render_scientific_resources_sidebar" in runtime
    assert "render_generated_demo_sidebar" in runtime



def test_safe_structured_zip_ingestion_and_result_bundle() -> None:
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as archive:
        reference_rows = ["compound_id,measured,predicted,mw,logp,tpsa,rotb"]
        for index in range(10):
            reference_rows.append(f"R{index + 1},{1.0 + index * 0.2},{0.9 + index * 0.21},{300 + index},{2.0 + index * 0.05},{70 + index},{4 + index % 3}")
        archive.writestr("reference.csv", "\n".join(reference_rows) + "\n")
        archive.writestr("query.csv", "compound_id,mw,logp,tpsa,rotb\nQ1,310,2.1,72,4\n")
    files = read_zip_tables_bytes(raw.getvalue())
    payload = structured_payload_from_zip("admet_calibration", files)
    assert set(payload) == {"reference", "query"}
    result = execute_feature("Discovery", "admet_calibration", payload)
    result["_run_provenance"] = {"source_kind": "local_upload"}
    bundle = build_result_bundle("admet_calibration", result, release="15.6.0")
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["source_kind"] == "local_upload"
        assert any(item["kind"] == "table" for item in manifest["files"])


def test_zip_ingestion_rejects_path_traversal_and_duplicate_basenames() -> None:
    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../metadata.csv", "a\n1\n")
    import pytest
    with pytest.raises(ValueError, match="unsafe path"):
        read_zip_tables_bytes(unsafe.getvalue())
    duplicate = io.BytesIO()
    with zipfile.ZipFile(duplicate, "w") as archive:
        archive.writestr("one/data.csv", "a\n1\n")
        archive.writestr("two/data.csv", "a\n2\n")
    with pytest.raises(ValueError, match="Duplicate ZIP basename"):
        read_zip_tables_bytes(duplicate.getvalue())

def test_protected_module_hashes_remain_unchanged() -> None:
    manifest = json.loads((ROOT / "PROTECTED_MODULE_HASHES_STEP205.json").read_text(encoding="utf-8"))
    entries = manifest["entries"]
    assert len(entries) == 17
    for entry in entries:
        path = ROOT / entry["path"]
        assert path.is_file(), entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["path"]


def test_current_release_contract() -> None:
    namespace: dict[str, object] = {}
    exec((ROOT / "scripts/step206_contract.py").read_text(encoding="utf-8"), namespace)
    assert namespace["PACKAGE_GENERATION"] == "V20.5"
    assert namespace["PART_COUNT"] == 4
    assert namespace["ARCHIVE_ROOT"] == "BioIntel-Step220"
