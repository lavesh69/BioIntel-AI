from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from biointel.ui.phase108_visuals import _BUILDERS, PHASE108_VISUAL_TITLES

ROOT = Path(__file__).resolve().parents[1]


def _contexts() -> dict[str, dict[str, object]]:
    return {
        "clinical_validation": {},
        "external_validation": {
            "result": SimpleNamespace(
                metrics={"roc_auc": 0.81, "f1": 0.72},
                drift={
                    "top_shifted_features": [
                        {"feature": "f1", "standardized_mean_shift": 1.2},
                        {"feature": "f2", "standardized_mean_shift": 0.5},
                    ]
                },
                predictions=pd.DataFrame(
                    {
                        "actual": [0, 1, 1, 0],
                        "predicted": [0, 1, 0, 0],
                        "positive_probability": [0.1, 0.8, 0.4, 0.2],
                    }
                ),
                input_rows=5,
                valid_rows=4,
                invalid_rows=1,
            )
        },
        "benchmark_leakage": {
            "result": {
                "train_rows": 10,
                "test_rows": 5,
                "exact_compound_overlap": 1,
                "scaffold_overlap": 2,
                "exact_target_overlap": 0,
                "target_cluster_overlap": 1,
                "pair_overlap": 0,
                "passed": False,
            },
            "train": pd.DataFrame(
                {"canonical_smiles": ["CC"] * 10, "protein_sequence": ["AAA"] * 10}
            ),
            "test": pd.DataFrame(
                {
                    "canonical_smiles": ["CC", "CCC", "CCCC", "CO", "CN"],
                    "protein_sequence": ["AAA", "BBB", "CCC", "DDD", "EEE"],
                }
            ),
        },
        "dti_validation": {
            "report": {
                "capabilities": [
                    {
                        "label": "A",
                        "implementation_score": 10,
                        "evidence_score": 5,
                        "status": "partial",
                    },
                    {
                        "label": "B",
                        "implementation_score": 9,
                        "evidence_score": 2,
                        "status": "blocked",
                    },
                ],
                "summary": {
                    "studies": 3,
                    "completed_external_dti": 1,
                    "completed_blinded_prospective": 0,
                    "completed_wetlab": 0,
                    "independent_sites": 0,
                    "completed_multisite": 0,
                    "release_eligible_studies": 0,
                },
            }
        },
        "data_readiness": {},
        "model_evaluation": {
            "comparison": pd.DataFrame(
                [
                    {
                        "File": "a",
                        "Task": "classification",
                        "Split": "random",
                        "Calibration": "none",
                        "Synthetic demo": True,
                        "Train rows": 100,
                        "Test rows": 20,
                        "Validation roc_auc": 0.8,
                        "Test roc_auc": 0.75,
                    },
                    {
                        "File": "b",
                        "Task": "classification",
                        "Split": "scaffold",
                        "Calibration": "isotonic",
                        "Synthetic demo": False,
                        "Train rows": 200,
                        "Test rows": 40,
                        "Validation roc_auc": 0.85,
                        "Test roc_auc": 0.8,
                    },
                ]
            )
        },
        "experiment_registry": {},
        "dataset_registry": {},
        "knowledge_graph": {
            "nodes": pd.DataFrame(
                {"node": ["A", "B", "C"], "type": ["gene", "disease", "drug"]}
            ),
            "filtered_edges": pd.DataFrame(
                {
                    "source": ["A", "A"],
                    "target": ["B", "C"],
                    "relation": ["assoc", "targeted_by"],
                    "evidence_score": [0.8, 0.6],
                    "evidence_type": ["publication", "trial"],
                    "citation": ["PMID:1", ""],
                }
            ),
            "conflicts": pd.DataFrame(),
            "gaps": pd.DataFrame(
                {"node": ["A", "B", "C"], "degree": [2, 1, 1], "gap_score": [0, 0.2, 0.3]}
            ),
        },
        "evidence_package": {
            "readiness": {
                "criteria": [
                    {"label": "Manifest", "status": "passed", "score": 100},
                    {"label": "Lineage", "status": "blocked", "score": 0},
                ],
                "blockers": ["Lineage missing"],
            },
            "manifest": {"files": [{"path": "a.json"}, {"path": "b.csv"}]},
        },
        "governance": {},
        "release_gate": {
            "result": SimpleNamespace(
                checks=pd.DataFrame(
                    {
                        "check": ["schema", "leakage"],
                        "status": ["passed", "blocked"],
                        "category": ["data", "model"],
                    }
                ),
                blockers=["leakage failed"],
                score=50,
                passed=False,
            )
        },
        "provider_integration": {},
        "reference_manager": {},
    }


def test_phase108_registry_has_fourteen_modules_and_seventy_views() -> None:
    assert len(PHASE108_VISUAL_TITLES) == 14
    assert sum(len(items) for items in PHASE108_VISUAL_TITLES.values()) == 70
    assert set(PHASE108_VISUAL_TITLES) == set(_BUILDERS)
    assert all(len(items) == 5 for items in PHASE108_VISUAL_TITLES.values())


def test_all_phase108_visual_builders_are_safe() -> None:
    contexts = _contexts()
    for module_key, builder in _BUILDERS.items():
        for index, _title in enumerate(PHASE108_VISUAL_TITLES[module_key]):
            figure, data, interpretation, method, _units = builder(
                index, ROOT, contexts[module_key]
            )
            assert figure is not None
            assert isinstance(data, pd.DataFrame)
            assert interpretation
            assert method


def test_phase108_pages_are_connected() -> None:
    expected = {
        "clinical_validation": "pages/90_Clinical_Pharma_Validation_Center.py",
        "external_validation": "pages/14_External_Validation_Drift.py",
        "benchmark_leakage": "pages/47_Benchmark_Leakage_Lab.py",
        "dti_validation": "pages/74_DTI_Validation_Evidence_Center.py",
        "data_readiness": "pages/69_Scientific_Data_Readiness.py",
        "model_evaluation": "pages/7_Model_Evaluation.py",
        "experiment_registry": "pages/11_Experiment_Registry.py",
        "dataset_registry": "pages/21_Dataset_Registry_Lineage.py",
        "knowledge_graph": "pages/101_Biomedical_Knowledge_Graph_Copilot.py",
        "evidence_package": "pages/31_Evidence_Package_Studio.py",
        "governance": "pages/30_Governance_Hub.py",
        "release_gate": "pages/45_Scientific_Release_Gate.py",
        "provider_integration": "pages/85_Provider_Integration_Center.py",
        "reference_manager": "pages/106_Reference_Database_Manager.py",
    }
    for key, relative in expected.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "render_phase108_visual_suite" in text
        assert f'"{key}"' in text


def test_release_version_is_synchronised() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    assert 'version = "13.2.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "13.2.0"' in (ROOT / "src/biointel/__init__.py").read_text(encoding="utf-8")
