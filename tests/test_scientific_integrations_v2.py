from __future__ import annotations

import json
from pathlib import Path

import pytest

from biointel.integrations import execute_integration, integration_catalog, integration_status_rows, integration_summary
from biointel.integrations.runtime_manager import _cli_arguments

ROOT = Path(__file__).resolve().parents[1]


def test_all_p0_p1_p2_integrations_are_registered() -> None:
    catalog = integration_catalog()
    assert len(catalog) == 20
    assert {item.priority for item in catalog} == {"P0", "P1", "P2"}
    counts = {priority: sum(item.priority == priority for item in catalog) for priority in ("P0", "P1", "P2")}
    assert counts == {"P0": 7, "P1": 10, "P2": 3}
    assert all("technical_diagnostic" in item.operations for item in catalog)
    assert all(item.runtime_profile for item in catalog)
    assert all(item.module_pages for item in catalog)


def test_every_target_page_has_biointel_integration_panel() -> None:
    for spec in integration_catalog():
        for relative in spec.module_pages:
            path = ROOT / relative
            assert path.is_file(), relative
            source = path.read_text(encoding="utf-8")
            assert "render_page_integrations" in source, relative
            assert relative in source, relative


def test_public_status_is_white_labelled_and_has_no_probe_identifiers() -> None:
    serialized = json.dumps(integration_status_rows()).casefold()
    assert "python_modules" not in serialized
    assert "distributions" not in serialized
    assert "tool_ids" not in serialized
    assert "github.com" not in serialized
    assert all(row["name"].startswith("BioIntel ") for row in integration_status_rows())


def test_summary_reports_priority_coverage() -> None:
    summary = integration_summary()
    assert summary["total"] == 20
    assert summary["priorities"]["P0"]["total"] == 7
    assert summary["priorities"]["P1"]["total"] == 10
    assert summary["priorities"]["P2"]["total"] == 3
    assert summary["ready"] + summary["setup_required"] == 20


def test_core_sequence_execution_is_real_and_audited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path))
    result = execute_integration("sequence_intelligence", "sequence_summary", {"sequence": "ATGCGCGTAA"})
    assert result.status == "completed"
    assert result.metrics["total_length"] == 10
    assert result.metrics["mean_gc_percent"] == 50.0
    assert Path(result.internal_manifest).is_file()


def test_core_molecular_execution_is_real_and_audited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path))
    result = execute_integration("molecular_intelligence", "molecule_summary", {"smiles": "CCO"})
    assert result.status == "completed"
    assert result.metrics["canonical_smiles"] == "CCO"
    assert result.metrics["molecular_weight"] > 40


def test_cli_builders_use_argument_vectors_and_biointel_output_paths(tmp_path: Path) -> None:
    tool, args = _cli_arguments(
        "molecular_docking",
        "dock",
        {"receptor_path": "receptor.pdbqt", "ligand_path": "ligand.pdbqt"},
        tmp_path,
    )
    assert tool == "vina"
    assert "--receptor" in args and "--ligand" in args and "--out" in args
    assert any("biointel_docking_output" in value for value in args)

    tool, args = _cli_arguments(
        "workflow_automation",
        "dry_run",
        {"workflow_path": "Snakefile", "cores": 2},
        tmp_path,
    )
    assert tool == "snakemake"
    assert "--dry-run" in args

    tool, args = _cli_arguments(
        "taxonomy_classification",
        "database_check",
        {"database_path": "database"},
        tmp_path,
    )
    assert tool == "kraken2-inspect"
    assert args == ["--db", "database"]


def test_runtime_profile_contracts_cover_every_non_core_profile() -> None:
    payload = json.loads((ROOT / "config" / "biointel_scientific_runtime_profiles.json").read_text(encoding="utf-8"))
    profile_ids = {item["profile_id"] for item in payload["profiles"]}
    for spec in integration_catalog():
        if spec.runtime_profile != "core":
            assert spec.runtime_profile in profile_ids


def test_all_isolated_runtime_requirements_contracts_exist() -> None:
    payload = json.loads((ROOT / "config" / "biointel_scientific_runtime_profiles.json").read_text(encoding="utf-8"))
    requirement_profiles = [item for item in payload["profiles"] if item["mode"] == "micromamba_python"]
    assert len(requirement_profiles) == 7
    for profile in requirement_profiles:
        requirements = ROOT / profile["requirements_file"]
        assert requirements.is_file(), profile["profile_id"]
        lines = [line.strip() for line in requirements.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
        assert lines, profile["profile_id"]
        assert all("==0.0" not in line for line in lines)


def test_setup_installer_is_focused_and_does_not_reinstall_full_legacy_tool_suite() -> None:
    source = (ROOT / "scripts" / "install_scientific_integrations_windows.ps1").read_text(encoding="utf-8")
    assert "Install-P1CliWorkers" in source
    assert "Install-P2CliWorkers" in source
    assert "install_advanced_tools_windows.ps1" not in source
    assert 'Install-WslRuntime @("kraken2", "snakemake-minimal")' in source
    assert 'Install-WslRuntime @("nf-core", "nextflow", "git")' in source
    assert "model weights" not in source.casefold()
    assert "reference database" not in source.casefold()


def test_windows_setup_and_verifier_have_balanced_contract_blocks() -> None:
    for relative in (
        "scripts/install_scientific_integrations_windows.ps1",
        "scripts/verify_scientific_integrations_windows.ps1",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert source.count("{") == source.count("}"), relative
        assert source.count("(") == source.count(")"), relative
        assert "ConvertTo-Json" in source
        if relative.endswith("verify_scientific_integrations_windows.ps1"):
            assert "runtime-state.json" in source
        else:
            assert "verify_scientific_integrations_windows.ps1" in source


def test_normal_integration_surfaces_do_not_expose_upstream_brand_names() -> None:
    surfaces = [
        ROOT / "pages" / "356_BioIntel_Scientific_Integration_Center.py",
        ROOT / "src" / "biointel" / "ui" / "scientific_integrations.py",
    ]
    upstream_names = (
        "biopython", "pysam", "scikit-bio", "scanpy", "scvi", "muon", "squidpy",
        "rdkit", "deepchem", "autodock", "openmm", "mdanalysis", "proteinmpnn",
        "gseapy", "kraken", "monai", "napari", "snakemake", "nextflow", "nf-core",
    )
    rendered_source = "\n".join(path.read_text(encoding="utf-8").casefold() for path in surfaces)
    for upstream in upstream_names:
        assert upstream not in rendered_source, upstream


def test_legal_notice_preserves_integrated_component_identities() -> None:
    notice = (ROOT / "docs" / "legal" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8").casefold()
    for identity in (
        "biopython", "pysam", "scikit-bio", "scanpy", "scvi-tools", "muon", "squidpy",
        "rdkit", "deepchem", "autodock vina", "openmm", "mdanalysis", "esm", "proteinmpnn",
        "gseapy", "kraken 2", "monai", "napari", "snakemake", "nextflow", "nf-core",
    ):
        assert identity in notice, identity
