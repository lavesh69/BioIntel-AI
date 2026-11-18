from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import biointel.api.main as api_main
import biointel.internet.pubchem as pubchem_module
from biointel.api.main import app
from biointel.chemistry.common_compounds import (
    DIRECTORY_SIZE,
    load_common_compound_directory,
    search_common_compounds,
)
from biointel.cli import main as cli_main
from biointel.intelligence.data_intelligence import all_database_health
from biointel.internet.connectivity import internet_configuration
from biointel.internet.download_registry import (
    download_summary,
    initialize_download_registry,
)
from biointel.internet.network_policy import (
    InternetPolicy,
    NetworkPolicyError,
    validate_public_https_url,
)
from biointel.internet.pubchem import PubChemCompound
from biointel.internet.rcsb import (
    FORMATS,
    normalize_pdb_id,
    rcsb_download_url,
)
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_step22_common_compound_directory() -> None:
    frame = load_common_compound_directory(ROOT)
    assert len(frame) == DIRECTORY_SIZE == 5000
    assert frame["compound_key"].nunique() == 5000
    assert frame["canonical_smiles"].nunique() == 5000
    assert (frame["name_type"] == "curated_common_name").sum() >= 50
    assert {
        "common_name",
        "aliases",
        "canonical_smiles",
        "name_type",
        "source",
        "molecular_formula",
        "molecular_weight",
        "logp",
        "tpsa",
    } <= set(frame.columns)

    aspirin = search_common_compounds(
        frame,
        "acetylsalicylic",
        limit=20,
    )
    assert not aspirin.empty
    assert aspirin.iloc[0]["common_name"] == "Aspirin"
    nci = search_common_compounds(
        frame,
        "NCI screening compound",
        name_type="registry_screening_name",
        limit=20,
    )
    assert not nci.empty
    assert set(nci["name_type"]) == {"registry_screening_name"}


def test_step22_network_policy_blocks_unsafe_targets() -> None:
    policy = InternetPolicy(
        enabled=True,
        resolve_dns=False,
    )
    assert validate_public_https_url(
        "https://files.rcsb.org/download/4HHB.cif",
        policy=policy,
        resolve_dns=False,
    ).startswith("https://")
    assert validate_public_https_url(
        "https://pubchem.ncbi.nlm.nih.gov/",
        policy=policy,
        resolve_dns=False,
    ).startswith("https://")
    with pytest.raises(NetworkPolicyError):
        validate_public_https_url(
            "http://example.org/data.csv",
            policy=policy,
            resolve_dns=False,
        )
    with pytest.raises(NetworkPolicyError):
        validate_public_https_url(
            "https://127.0.0.1/data.csv",
            policy=policy,
            resolve_dns=False,
        )
    with pytest.raises(NetworkPolicyError):
        validate_public_https_url(
            "https://user:pass@example.org/data.csv",
            policy=policy,
            resolve_dns=False,
        )


def test_step22_rcsb_identifier_and_urls() -> None:
    assert normalize_pdb_id("4hhb") == "4HHB"
    assert normalize_pdb_id("pdb_00006uv8") == "pdb_00006UV8"
    with pytest.raises(ValueError):
        normalize_pdb_id("bad")

    url, filename = rcsb_download_url("4HHB", "cif")
    assert url == "https://files.rcsb.org/download/4HHB.cif"
    assert filename == "4HHB.cif"
    assert set(FORMATS.values()) == {
        "cif",
        "pdb",
        "cif.gz",
        "pdb.gz",
    }
    with pytest.raises(ValueError):
        rcsb_download_url("pdb_00006UV8", "pdb")


def test_step22_pubchem_parser_with_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "PropertyTable": {
            "Properties": [
                {
                    "CID": 2244,
                    "Title": "Aspirin",
                    "CanonicalSMILES": ("CC(=O)OC1=CC=CC=C1C(=O)O"),
                    "IsomericSMILES": ("CC(=O)OC1=CC=CC=C1C(=O)O"),
                    "IUPACName": "2-acetyloxybenzoic acid",
                    "MolecularFormula": "C9H8O4",
                    "MolecularWeight": 180.16,
                    "XLogP": 1.2,
                    "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
                }
            ]
        }
    }

    def fake_fetch(*args, **kwargs):  # noqa: ANN002, ANN003
        return payload, {"status": 200}

    monkeypatch.setattr(
        pubchem_module,
        "fetch_public_json",
        fake_fetch,
    )
    result = pubchem_module.fetch_pubchem_compound_by_name(
        "aspirin",
        policy=InternetPolicy(resolve_dns=False),
    )
    assert result.cid == 2244
    assert result.title == "Aspirin"
    assert result.canonical_smiles.startswith("CC(=O)O")
    assert result.source_url.endswith("/2244")


def test_step22_download_registry_and_database_fabric(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "internet_downloads.sqlite3"
    initialize_download_registry(registry)
    summary = download_summary(registry)
    assert summary["downloads"] == 0
    assert summary["database"]["integrity"] == "ok"
    assert summary["database"]["journal_mode"] == "wal"
    assert summary["database"]["index_count"] >= 5

    health = all_database_health(ROOT)
    assert health["database_count"] >= 18
    assert health["healthy_count"] == health["database_count"]
    assert "downloads" in health["databases"]


def test_step22_api_local_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    status = client.get("/internet/status")
    assert status.status_code == 200
    assert status.json()["configuration"]["outbound_only"] is True

    directory = client.get(
        "/chemistry/common-compounds",
        params={"q": "aspirin", "limit": 20},
    )
    assert directory.status_code == 200
    payload = directory.json()
    assert payload["directory_rows"] == 5000
    assert payload["unique_structures"] == 5000
    assert payload["results"]

    fake = PubChemCompound(
        cid=2244,
        title="Aspirin",
        canonical_smiles="CC(=O)OC1=CC=CC=C1C(=O)O",
        isomeric_smiles=None,
        iupac_name="2-acetyloxybenzoic acid",
        molecular_formula="C9H8O4",
        molecular_weight=180.16,
        xlogp=1.2,
        inchikey="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        query_name="aspirin",
        source_url="https://pubchem.ncbi.nlm.nih.gov/compound/2244",
    )
    monkeypatch.setattr(
        api_main,
        "fetch_pubchem_compound_by_name",
        lambda *args, **kwargs: fake,
    )
    online = client.get("/internet/pubchem/name/aspirin")
    assert online.status_code == 200
    assert online.json()["cid"] == 2244


def test_step22_cli_local_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli_main(["internet-status"]) == 0
    output = capsys.readouterr().out
    assert "outbound_only" in output

    assert (
        cli_main(
            [
                "common-compound-search",
                "caffeine",
                "--limit",
                "10",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"directory_rows": 5000' in output
    assert "Caffeine" in output


def test_step22_navigation_launchers_and_ui() -> None:
    assert len(PAGE_CATALOG) >= 71
    assert PAGE_BY_KEY["internet_research"].path.endswith("42_Internet_Research_Hub.py")
    assert "pubchem" in PAGE_BY_KEY["internet_research"].keywords
    for relative in (
        "START_BIOINTEL_INTERNET_WINDOWS.bat",
        "CHECK_INTERNET_ACCESS_WINDOWS.bat",
        "REFRESH_COMPOUND_DIRECTORY_WINDOWS.bat",
        "pages/42_Internet_Research_Hub.py",
        "data/chemistry/common_compound_directory_5000.csv",
    ):
        assert (ROOT / relative).is_file()

    analyzer = (ROOT / "pages" / "3_Drug_SMILES_Analyzer.py").read_text(encoding="utf-8")
    assert "5,000-name compound directory" in analyzer
    assert "PubChem online name lookup" in analyzer
    assert "registry/screening name" in analyzer


def test_step22_internet_configuration() -> None:
    configuration = internet_configuration()
    assert configuration["outbound_only"] is True
    assert configuration["localhost_server"] is True
    assert "pubchem.ncbi.nlm.nih.gov" in configuration["approved_scientific_hosts"]
    assert configuration["automatic_archive_extraction"] is False
