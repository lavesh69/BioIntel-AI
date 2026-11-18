from pathlib import Path

from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.dti.predictor import predict_dti_pair
from biointel.training.model_artifact import load_model_artifact_cached

ROOT = Path(__file__).resolve().parents[1]


def main():
    models = sorted((ROOT / "models").glob("*.joblib"))
    assert models
    for path in models:
        art = load_model_artifact_cached(
            path,
            trusted_root=ROOT / "models",
        )
        assert predict_dti_pair(
            art,
            "CCO",
            "ACDEFGHIKLMNPQRSTVWY",
        ).task_type
        print(f"Verified model: {path.name}", flush=True)
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["authentication_required"] is False
    assert (ROOT / "pages" / "24_Appearance_Studio.py").is_file()
    assert (ROOT / "pages" / "25_Command_Center.py").is_file()
    assert (ROOT / "pages" / "26_Research_Report_Studio.py").is_file()
    assert (ROOT / "pages" / "27_Executive_Overview.py").is_file()
    assert (ROOT / "pages" / "28_Project_Portfolio.py").is_file()
    assert (ROOT / "pages" / "29_Activity_Risk_Center.py").is_file()
    assert (ROOT / "pages" / "30_Governance_Hub.py").is_file()
    assert (ROOT / "pages" / "31_Evidence_Package_Studio.py").is_file()
    assert (ROOT / "pages" / "32_Release_Readiness_Lineage.py").is_file()
    assert (ROOT / "pages" / "33_Data_Model_Library.py").is_file()
    assert (ROOT / "pages" / "34_ML_AutoLab.py").is_file()
    assert (ROOT / "pages" / "35_Double_Data_ML.py").is_file()
    assert (ROOT / "pages" / "36_Data_Coverage_Center.py").is_file()
    assert (ROOT / "pages" / "37_5X_Data_ML.py").is_file()
    assert (ROOT / "pages" / "38_Data_Intelligence_Hub.py").is_file()
    assert (ROOT / "pages" / "39_Knowledge_Warehouse.py").is_file()
    assert (ROOT / "pages" / "40_Analytics_Observability.py").is_file()
    assert (ROOT / "pages" / "41_Research_Assets.py").is_file()
    assert (ROOT / "pages" / "42_Internet_Research_Hub.py").is_file()
    assert (ROOT / "pages" / "43_Scientific_Data_Curation.py").is_file()
    assert (ROOT / "pages" / "44_Performance_Job_Center.py").is_file()
    assert (ROOT / "pages" / "45_Scientific_Release_Gate.py").is_file()
    assert client.get("/system/capabilities").status_code == 200
    assert client.get("/jobs").status_code == 200
    assert client.get("/ui/catalog").status_code == 200
    assert client.get("/workflow/report-data").status_code == 200
    assert client.get("/portfolio/projects").status_code == 200
    assert client.get("/operations/alerts").status_code == 200
    assert client.get("/operations/timeline").status_code == 200
    assert client.get("/executive/summary").status_code == 200
    assert client.get("/governance/summary").status_code == 200
    assert client.get("/audit/integrity").status_code == 200
    assert client.get("/data/packs").status_code == 200
    assert client.get("/models/benchmark").status_code == 200
    assert client.get("/models/double-benchmark").status_code == 200
    assert client.get("/models/5x-benchmark").status_code == 200
    assert client.get("/system/cache-status").status_code == 200
    assert client.get("/data/coverage").status_code == 200
    assert client.get("/databases/status").status_code == 200
    assert client.get("/intelligence/search", params={"q": "model"}).status_code == 200
    assert client.get("/knowledge/search", params={"q": "dataset"}).status_code == 200
    assert client.get("/analytics/overview").status_code == 200
    assert client.get("/assets/search", params={"q": "model"}).status_code == 200
    assert client.get("/internet/status").status_code == 200
    assert (
        client.get(
            "/chemistry/common-compounds",
            params={"q": "aspirin", "limit": 10},
        ).status_code
        == 200
    )
    print("BioIntel Step 25 real-evidence smoke test passed")


if __name__ == "__main__":
    main()
