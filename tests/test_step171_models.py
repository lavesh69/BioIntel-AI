from pathlib import Path
import json
import sys

import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from biointel.models_v171 import APPLICABLE_MODULES, Step171Registry, qualification_matrix, sha256_file


def test_step171_catalog_and_assets():
    assert len(APPLICABLE_MODULES) == 12
    assert len(list((ROOT / "data" / "step171" / "module_contracts").glob("*/model_qualification_contract.json"))) == 12
    assert len(list((ROOT / "data" / "step171" / "model_packages").glob("*/model_card.json"))) == 8
    assert len(list((ROOT / "data" / "step171" / "acquisition_manifests").glob("*/acquisition_manifest.json"))) == 4


def test_step171_authentic_packages_hash_and_load():
    for card_path in (ROOT / "data" / "step171" / "model_packages").glob("*/model_card.json"):
        card = json.loads(card_path.read_text(encoding="utf-8"))
        artifact = ROOT / card["model_artifact"]
        assert artifact.exists()
        assert sha256_file(artifact) == card["model_sha256"]
        assert card["synthetic_models_eligible"] is False
        assert card["release_eligible"] is False
        if artifact.suffix == ".joblib":
            assert joblib.load(artifact) is not None


def test_step171_registry_and_matrix_are_honest():
    status = Step171Registry(ROOT, rebuild=True).status()
    matrix = qualification_matrix(ROOT)
    assert status["database_integrity"] == "ok"
    assert status["foreign_key_violations"] == 0
    assert status["authentic_research_packages"] == 8
    assert status["real_cohorts"] == 8
    assert status["locked_benchmarks"] == 8
    assert status["acquisition_pending"] == 4
    assert status["independent_external_sites"] == 0
    assert status["release_eligible_models"] == 0
    assert int(matrix["research_benchmark_qualified"].sum()) == 8
    assert int(matrix["release_eligible"].sum()) == 0


def test_step171_split_leakage_is_zero():
    for path in (ROOT / "data" / "step171" / "model_packages").glob("*/split_manifest.json"):
        split = json.loads(path.read_text(encoding="utf-8"))
        assert all(value == 0 for value in split["overlap_counts"].values())


def test_step171_blocked_modules_do_not_use_demo_substitution():
    blocked = {"protein_language_design", "protein_ligand_codesign", "spatial_omics_pathology", "strain_microbiome"}
    found = {path.parent.name for path in (ROOT / "data" / "step171" / "acquisition_manifests").glob("*/acquisition_manifest.json")}
    assert found == blocked
    for path in (ROOT / "data" / "step171" / "acquisition_manifests").glob("*/acquisition_manifest.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["downloaded"] is False
        assert payload["benchmark_executed"] is False
        assert payload["release_eligible"] is False
