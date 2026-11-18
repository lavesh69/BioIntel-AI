from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel.api import main as api_main
from biointel.chemistry.chemical_space import (
    activity_cliffs,
    butina_clusters,
    chemical_space_embedding,
    consensus_similarity,
    similarity_matrix,
)
from biointel.discovery.admet_plugins import EndpointModelCard, qualify_endpoint_model
from biointel.discovery.docking import evaluate_docking_qualification
from biointel.discovery.preparation import prepare_molecular_states
from biointel.discovery.registry import (
    add_evidence,
    add_target_assessment,
    create_project,
    export_project_bundle,
    list_compounds,
    project_snapshot,
    save_ranking,
    upsert_compound,
)
from biointel.discovery.target_intelligence import build_target_evidence_profile
from biointel.discovery.workflow import rank_discovery_hits
from biointel.integrations.chembl_dataset import ChEMBLActivityQuery, build_chembl_activity_dataset
from biointel.integrations.http_client import HttpResponse

ROOT = Path(__file__).resolve().parents[1]


def test_missing_cost_value_is_never_best():
    frame = pd.DataFrame(
        {
            "compound_id": ["low", "high", "missing"],
            "developability_score": [80, 80, 80],
            "risk_score": [10.0, 90.0, None],
        }
    )
    ranked = rank_discovery_hits(
        frame,
        id_column="compound_id",
        benefit_columns={"developability_score": 0.5},
        cost_columns={"risk_score": 0.5},
        method="minmax",
        missing_penalty=0.5,
    )
    scores = ranked.set_index("compound_id")["multi_objective_score"]
    assert scores["low"] > scores["high"] > scores["missing"]
    missing = ranked.set_index("compound_id").loc["missing"]
    assert missing["missing_objective_count"] == 1
    assert "worst-value" in missing["ranking_warning"]


def test_registry_persists_identity_events_and_bundle(tmp_path):
    database = tmp_path / "discovery.sqlite3"
    project_id = create_project("Alpha", indication="oncology", path=database)
    scoring = {"target_id": "EGFR", "total_score": 75}
    add_target_assessment(project_id, target_id="EGFR", scoring=scoring, path=database)
    first = upsert_compound(
        project_id,
        compound_id="A",
        original_smiles="CCO",
        standardized_smiles="CCO",
        inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        profile={"developability_score": 80, "risk_score": 20, "qed": 0.6, "synthetic_accessibility_heuristic": 2.0},
        duplicate_policy="merge_exact",
        path=database,
    )
    second = upsert_compound(
        project_id,
        compound_id="A-renamed",
        original_smiles="OCC",
        standardized_smiles="CCO",
        inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        profile={"developability_score": 82, "risk_score": 18, "qed": 0.61, "synthetic_accessibility_heuristic": 2.0},
        duplicate_policy="merge_exact",
        path=database,
    )
    assert first["action"] == "inserted"
    assert second["action"] == "merged"
    assert len(list_compounds(project_id, path=database)) == 1
    add_evidence(
        project_id,
        entity_type="target",
        entity_id="EGFR",
        evidence_type="genetics",
        source="study",
        payload={"score": 90},
        path=database,
    )
    ranked = pd.DataFrame([{"hit_rank": 1, "compound_id": "A", "multi_objective_score": 90.0}])
    save_ranking(project_id, result=ranked, method="robust_percentile", parameters={}, path=database)
    snapshot = project_snapshot(project_id, path=database)
    assert snapshot["project"]["active_target_id"] == "EGFR"
    assert snapshot["snapshot_sha256"]
    bundle = export_project_bundle(project_id, path=database)
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert {"manifest.json", "discovery_project.json", "compounds.csv"} <= set(archive.namelist())


def test_duplicate_reject_and_connectivity_merge(tmp_path):
    database = tmp_path / "discovery.sqlite3"
    project_id = create_project("Identity", path=database)
    upsert_compound(
        project_id,
        compound_id="stereo-1",
        original_smiles="C[C@H](O)C(=O)O",
        standardized_smiles="C[C@H](O)C(=O)O",
        inchikey="JVTAAEKCZFNVCJ-REOHCLBHSA-N",
        profile={},
        path=database,
    )
    with pytest.raises(ValueError, match="Duplicate molecular identity"):
        upsert_compound(
            project_id,
            compound_id="same",
            original_smiles="C[C@H](O)C(=O)O",
            standardized_smiles="C[C@H](O)C(=O)O",
            inchikey="JVTAAEKCZFNVCJ-REOHCLBHSA-N",
            profile={},
            duplicate_policy="reject_exact",
            path=database,
        )
    result = upsert_compound(
        project_id,
        compound_id="stereo-2",
        original_smiles="C[C@@H](O)C(=O)O",
        standardized_smiles="C[C@@H](O)C(=O)O",
        inchikey="JVTAAEKCZFNVCJ-UWTATZPHSA-N",
        profile={},
        duplicate_policy="merge_connectivity",
        path=database,
    )
    assert result["action"] == "merged"


def test_target_intelligence_weights_confidence_conflicts_and_gates():
    evidence = [
        {"dimension": "genetic_evidence", "score": 95, "confidence": 0.9, "source_type": "human_genetics", "source": "GWAS", "source_id": "1"},
        {"dimension": "genetic_evidence", "score": 20, "confidence": 0.8, "source_type": "peer_reviewed_literature", "source": "Paper", "source_id": "2"},
        {"dimension": "disease_relevance", "score": 80, "confidence": 0.9, "source_type": "clinical"},
        {"dimension": "pathway_evidence", "score": 60, "confidence": 0.7, "source_type": "curated_database"},
        {"dimension": "tractability", "score": 75, "confidence": 0.8, "source_type": "curated_database"},
        {"dimension": "safety_window", "score": 30, "confidence": 0.8, "source_type": "primary_experiment"},
        {"dimension": "experimental_validation", "score": 70, "confidence": 0.8, "source_type": "primary_experiment"},
    ]
    profile = build_target_evidence_profile(
        "EGFR",
        evidence,
        template="oncology",
        hard_gates={"safety_window": 40},
    )
    assert profile.evidence_count == 7
    assert profile.conflicts
    assert profile.gate_failures
    assert profile.priority_tier.startswith("D")
    assert profile.confidence_adjusted_score <= profile.total_score


def test_molecular_preparation_is_transparent_about_ph_and_ensembles():
    assay = prepare_molecular_states("NCC(=O)O", mode="assay_context", ph=7.4)
    assert assay.requested_ph == 7.4
    assert assay.ionizable_groups
    assert assay.exact_microspecies_assigned is False
    assert any("pH-dependent" in warning for warning in assay.warnings)
    stereo = prepare_molecular_states("CC(O)C(=O)O", mode="stereoisomer_ensemble")
    assert stereo.stereoisomer_count >= 2


def test_admet_model_qualification_gate():
    blocked = EndpointModelCard(
        model_id="x",
        endpoint="hERG",
        version="1",
        artifact_sha256="bad",
        training_dataset_sha256="bad",
        licence="",
        endpoint_definition="",
        units="probability",
        split_strategies=["random"],
        metrics={},
        calibration={},
        applicability_domain={},
        independent_validation={},
        intended_use="",
        limitations=[],
    )
    assert qualify_endpoint_model(blocked).eligible is False
    valid_hash = "a" * 64
    qualified = EndpointModelCard(
        model_id="herg-1",
        endpoint="hERG",
        version="1.0",
        artifact_sha256=valid_hash,
        training_dataset_sha256="b" * 64,
        licence="approved internal licence",
        endpoint_definition="Binary hERG inhibition at defined threshold",
        units="probability",
        split_strategies=["scaffold", "external"],
        metrics={"roc_auc": 0.8},
        calibration={"ece": 0.04},
        applicability_domain={"method": "fingerprint distance"},
        independent_validation={"dataset": "external", "roc_auc": 0.76},
        intended_use="early screening",
        limitations=["not clinical"],
    )
    result = qualify_endpoint_model(qualified)
    assert result.eligible is True
    assert result.status == "qualified"


def test_chemical_space_and_activity_cliffs():
    frame = pd.DataFrame(
        {
            "compound_id": ["a", "b", "c"],
            "standardized_smiles": ["CCO", "CCCO", "c1ccccc1"],
            "p_activity": [8.0, 6.0, 5.0],
        }
    )
    matrix = similarity_matrix(frame)
    assert matrix.shape == (3, 3)
    assert matrix.loc["a", "a"] == 1
    assert consensus_similarity("CCO", "CCCO")["consensus_mean"] > 0
    clusters = butina_clusters(frame, similarity_threshold=0.3)
    assert len(clusters) == 3
    embedding = chemical_space_embedding(frame)
    assert {"PC1", "PC2"} <= set(embedding)
    cliffs = activity_cliffs(frame, similarity_threshold=0.3, activity_difference=1.0)
    assert not cliffs.empty


def test_chembl_multicomponent_target_is_blocked_and_selectable():
    def transport(url, timeout, headers):
        if "target/" in url:
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "target_components": [
                            {"accession": "P11111"},
                            {"accession": "P22222"},
                        ],
                        "target_type": "PROTEIN COMPLEX",
                    }
                ).encode(),
                "application/json",
            )
        if "uniprot" in url:
            return HttpResponse(200, b">x\nACDEFGHIKLMNPQRSTVWY\n", "text/plain")
        return HttpResponse(
            200,
            json.dumps(
                {
                    "activities": [
                        {"activity_id": 1, "molecule_chembl_id": "CHEMBL1", "canonical_smiles": "CCO", "standard_relation": "=", "pchembl_value": "7.5", "assay_chembl_id": "A1", "document_chembl_id": "D1"},
                        {"activity_id": 2, "molecule_chembl_id": "CHEMBL1", "canonical_smiles": "CCO", "standard_relation": "=", "pchembl_value": "5.5", "assay_chembl_id": "A2", "document_chembl_id": "D2"},
                    ],
                    "page_meta": {"next": None},
                }
            ).encode(),
            "application/json",
        )

    with pytest.raises(ValueError, match="Multi-component"):
        build_chembl_activity_dataset(
            ChEMBLActivityQuery("CHEMBL204", max_records=10), transport=transport
        )
    result = build_chembl_activity_dataset(
        ChEMBLActivityQuery(
            "CHEMBL204",
            max_records=10,
            multi_component_policy="select",
            selected_uniprot_accession="P22222",
            aggregate_replicates=True,
            conflict_threshold_log_units=1.0,
        ),
        transport=transport,
    )
    assert result.metadata["uniprot_accession"] == "P22222"
    assert len(result.dataset) == 1
    assert result.dataset.iloc[0]["replicate_count"] == 2
    assert bool(result.dataset.iloc[0]["conflicting_measurements"])


def test_docking_protocol_gate_requires_redocking_and_pose_review():
    blocked = evaluate_docking_qualification(
        receptor_prepared=True,
        ligand_prepared=True,
        grid_defined=True,
        reference_ligand_available=True,
        redocking_rmsd_angstrom=3.0,
        enrichment_factor_1_percent=3.0,
        pose_review_completed=False,
    )
    assert blocked.qualified is False
    qualified = evaluate_docking_qualification(
        receptor_prepared=True,
        ligand_prepared=True,
        grid_defined=True,
        reference_ligand_available=True,
        redocking_rmsd_angstrom=1.5,
        enrichment_factor_1_percent=3.0,
        pose_review_completed=True,
    )
    assert qualified.qualified is True


def test_discovery_api_project_compound_and_ranking(tmp_path, monkeypatch):
    database = tmp_path / "api_discovery.sqlite3"
    monkeypatch.setattr(api_main, "DISCOVERY_DATABASE", database)
    client = TestClient(api_main.app)
    created = client.post(
        "/discovery/projects",
        json={"project_name": "API program", "indication": "test"},
    )
    assert created.status_code == 200
    project_id = created.json()["project"]["project_id"]
    compound = client.post(
        f"/discovery/projects/{project_id}/compounds",
        json={"compound_id": "ethanol", "smiles": "CCO"},
    )
    assert compound.status_code == 200
    ranking = client.post(
        f"/discovery/projects/{project_id}/rankings",
        json={
            "benefit_columns": {"developability_score": 0.5, "qed": 0.2},
            "cost_columns": {"risk_score": 0.2, "synthetic_accessibility_heuristic": 0.1},
        },
    )
    assert ranking.status_code == 200
    bundle = client.get(f"/discovery/projects/{project_id}/bundle")
    assert bundle.status_code == 200
    assert bundle.headers["content-type"] == "application/zip"


@pytest.mark.parametrize(
    "page",
    [
        "pages/88_Discovery_Command_Center.py",
        "pages/62_ADMET_Drug_Discovery.py",
        "pages/61_Structural_Bioinformatics.py",
        "pages/13_ChEMBL_Dataset_Builder.py",
    ],
)
def test_step63_discovery_pages_render_without_exceptions(page):
    app = AppTest.from_file(str(ROOT / page), default_timeout=180).run()
    assert not app.exception


def test_lead_optimization_and_patent_evidence_gates():
    from biointel.discovery.lead_optimization import (
        assess_patent_evidence,
        assess_synthesis_feasibility,
        optimization_recommendations,
    )

    recommendations = optimization_recommendations(
        {"modifiable_liabilities": ["High lipophilicity", "Low solubility"]}
    )
    assert {row["liability"] for row in recommendations} == {
        "High lipophilicity",
        "Low solubility",
    }
    synthesis = assess_synthesis_feasibility(
        "C[C@H]1CC[C@@H](C)C1",
        estimated_steps=12,
        commercially_available_building_blocks=False,
        hazardous_steps=1,
        protecting_groups=3,
        precedent_documented=False,
    )
    assert synthesis.score < 80
    assert synthesis.methodology["warning"].startswith("Not a retrosynthesis")
    patent = assess_patent_evidence(
        exact_structure_search=True,
        substructure_search=False,
        similarity_search=True,
        sequence_or_target_search=True,
        jurisdiction_coverage=["US", "EP"],
        family_status_reviewed=False,
        claims_reviewed=False,
    )
    assert patent.complete is False
    assert "Substructure/Markush search" in patent.missing_evidence
    assert any("freedom to operate" in warning for warning in patent.warnings)


def test_endpoint_model_card_is_persisted(tmp_path):
    from dataclasses import asdict

    from biointel.discovery.registry import (
        list_endpoint_model_cards,
        register_endpoint_model_card,
    )

    card = EndpointModelCard(
        model_id="ames-v1",
        endpoint="Ames mutagenicity",
        version="1.0",
        artifact_sha256="a" * 64,
        training_dataset_sha256="b" * 64,
        licence="documented licence",
        endpoint_definition="Binary Ames call under a locked protocol",
        units="probability",
        split_strategies=["scaffold", "external"],
        metrics={"roc_auc": 0.81},
        calibration={"ece": 0.03},
        applicability_domain={"method": "distance"},
        independent_validation={"dataset": "external", "roc_auc": 0.78},
        intended_use="early screening",
        limitations=["not clinical"],
    )
    qualification = qualify_endpoint_model(card)
    database = tmp_path / "discovery.sqlite3"
    saved = register_endpoint_model_card(
        model_card=asdict(card),
        qualification=asdict(qualification),
        path=database,
    )
    assert saved["status"] == "qualified"
    rows = list_endpoint_model_cards(path=database)
    assert len(rows) == 1
    assert rows.iloc[0]["model_card"]["endpoint"] == "Ames mutagenicity"


def test_discovery_batch_worker_executes_and_deduplicates(tmp_path):
    from biointel.jobs.worker import LocalWorker

    worker = LocalWorker(tmp_path)
    job = worker.queue.submit(
        "discovery_batch_triage",
        {
            "rows": [
                {"compound_id": "ethanol-a", "smiles": "CCO"},
                {"compound_id": "ethanol-b", "smiles": "OCC"},
                {"compound_id": "bad", "smiles": "not-smiles"},
            ],
            "preparation_mode": "neutral_parent",
            "deduplicate": True,
        },
    )
    result = worker.run_once()
    assert result.status == "completed"
    completed = worker.queue.get(job.job_id)
    assert completed.result["profile_count"] == 1
    assert completed.result["failure_count"] == 1


def test_dti_page_requires_exploratory_acknowledgement():
    app = AppTest.from_file(str(ROOT / "pages" / "6_DTI_Predictor.py"), default_timeout=40)
    app.run(timeout=40)
    assert not app.exception
    acknowledgements = [
        checkbox
        for checkbox in app.checkbox
        if "exploratory/demo-only" in checkbox.label
    ]
    assert acknowledgements
    predict_buttons = [button for button in app.button if button.label == "Predict interaction"]
    assert predict_buttons and predict_buttons[0].disabled is True


def test_target_evidence_query_plan_is_explicitly_unretrieved():
    from biointel.discovery.target_intelligence import target_evidence_query_plan

    plan = target_evidence_query_plan("EGFR", "lung cancer")
    assert len(plan) >= 7
    assert all(row["status"] == "planned / not retrieved" for row in plan)
    assert all("checksum-bound" in row["scientific_boundary"] for row in plan)
    assert {"Open Targets", "ChEMBL / BindingDB", "GTEx / Human Protein Atlas"} <= {
        row["provider"] for row in plan
    }


def test_target_scoring_validation_custom_weights_and_all_tiers():
    from biointel.discovery.workflow import score_target_priority

    base = dict(
        target_id="T",
        disease_relevance=80,
        genetic_evidence=80,
        pathway_evidence=80,
        tractability=80,
        safety_window=80,
        experimental_validation=80,
    )
    assert score_target_priority(**base).priority_tier.startswith("A")
    assert score_target_priority(**{**base, "disease_relevance": 65, "genetic_evidence": 65, "pathway_evidence": 65, "tractability": 65, "safety_window": 65, "experimental_validation": 65}).priority_tier.startswith("B")
    assert score_target_priority(**{**base, "disease_relevance": 52, "genetic_evidence": 52, "pathway_evidence": 52, "tractability": 52, "safety_window": 52, "experimental_validation": 52}).priority_tier.startswith("C")
    assert score_target_priority(**{**base, "disease_relevance": 20}).limiting_factors
    custom = score_target_priority(
        **base,
        weights={
            "disease_relevance": 1,
            "genetic_evidence": 1,
            "pathway_evidence": 1,
            "tractability": 1,
            "safety_window": 1,
            "experimental_validation": 1,
        },
    )
    assert custom.methodology["template"] == "custom"
    with pytest.raises(ValueError, match="between 0 and 100"):
        score_target_priority(**{**base, "safety_window": 101})
    with pytest.raises(ValueError, match="Unknown"):
        score_target_priority(**base, template="unknown")
    with pytest.raises(ValueError, match="exactly"):
        score_target_priority(**base, weights={"disease_relevance": 1})
    with pytest.raises(ValueError, match="negative"):
        score_target_priority(
            **base,
            weights={
                "disease_relevance": -1,
                "genetic_evidence": 1,
                "pathway_evidence": 1,
                "tractability": 1,
                "safety_window": 1,
                "experimental_validation": 1,
            },
        )
    with pytest.raises(ValueError, match="positive"):
        score_target_priority(
            **base,
            weights={name: 0 for name in [
                "disease_relevance", "genetic_evidence", "pathway_evidence",
                "tractability", "safety_window", "experimental_validation",
            ]},
        )


def test_ranking_methods_validation_constant_all_missing_and_pareto():
    from biointel.discovery.workflow import rank_discovery_hits

    empty = rank_discovery_hits(pd.DataFrame(), id_column="id")
    assert empty.empty
    frame = pd.DataFrame(
        {
            "id": ["a", "b", "c", "d"],
            "benefit": [1.0, 2.0, 100.0, None],
            "cost": [5.0, 5.0, 5.0, None],
        }
    )
    for method in ["robust_percentile", "winsorized_minmax", "minmax", "zscore"]:
        ranked = rank_discovery_hits(
            frame,
            id_column="id",
            benefit_columns={"benefit": 0.5},
            cost_columns={"cost": 0.5},
            method=method,
            winsor_fraction=0.5,
            minimum_completeness=0.75,
        )
        assert len(ranked) == 4
        assert ranked["pareto_front"].dtype == bool
        assert ranked.loc[ranked["id"] == "d", "ranking_eligible"].item() is False
    all_missing = rank_discovery_hits(
        pd.DataFrame({"id": ["x", "y"], "benefit": [None, None]}),
        id_column="id",
        benefit_columns={"benefit": 1.0},
        cost_columns={},
    )
    assert (all_missing["multi_objective_score"] <= 0).all()
    with pytest.raises(ValueError, match="identifier"):
        rank_discovery_hits(frame, id_column="missing", benefit_columns={"benefit": 1}, cost_columns={})
    with pytest.raises(ValueError, match="Missing ranking"):
        rank_discovery_hits(frame, id_column="id", benefit_columns={"absent": 1}, cost_columns={})
    with pytest.raises(ValueError, match="both benefit and cost"):
        rank_discovery_hits(frame, id_column="id", benefit_columns={"benefit": 1}, cost_columns={"benefit": 1})
    with pytest.raises(ValueError, match="Unsupported"):
        rank_discovery_hits(frame, id_column="id", benefit_columns={"benefit": 1}, cost_columns={}, method="bad")
    with pytest.raises(ValueError, match="positive"):
        rank_discovery_hits(frame, id_column="id", benefit_columns={"benefit": 0}, cost_columns={})
    with pytest.raises(ValueError, match="missing_penalty"):
        rank_discovery_hits(frame, id_column="id", benefit_columns={"benefit": 1}, cost_columns={}, missing_penalty=2)
    with pytest.raises(ValueError, match="minimum_completeness"):
        rank_discovery_hits(frame, id_column="id", benefit_columns={"benefit": 1}, cost_columns={}, minimum_completeness=-1)


def test_registry_update_errors_keep_separate_and_model_status(tmp_path):
    from biointel.discovery.registry import (
        create_project,
        get_project,
        list_compounds,
        list_endpoint_model_cards,
        list_projects,
        register_endpoint_model_card,
        registry_summary,
        update_project,
        upsert_compound,
    )

    database = tmp_path / "registry.sqlite3"
    with pytest.raises(ValueError, match="project_name"):
        create_project("   ", path=database)
    with pytest.raises(KeyError):
        get_project("missing", path=database)
    project_id = create_project("Registry", owner="", settings={"mode": "strict"}, path=database)
    update_project(
        project_id,
        project_name="Registry 2",
        indication="Disease",
        objective="Objective",
        status="paused",
        active_target_id="T1",
        settings={"mode": "review"},
        path=database,
    )
    assert get_project(project_id, path=database)["settings"]["mode"] == "review"
    with pytest.raises(ValueError, match="Unsupported project status"):
        update_project(project_id, status="bad", path=database)
    with pytest.raises(KeyError):
        update_project("missing", objective="x", path=database)
    with pytest.raises(ValueError, match="Unsupported duplicate_policy"):
        upsert_compound(project_id, compound_id="x", original_smiles="CC", standardized_smiles="CC", inchikey=None, profile={}, duplicate_policy="bad", path=database)
    with pytest.raises(KeyError):
        upsert_compound("missing", compound_id="x", original_smiles="CC", standardized_smiles="CC", inchikey=None, profile={}, path=database)
    upsert_compound(project_id, compound_id="a", original_smiles="CCO", standardized_smiles="CCO", inchikey="KEY-AAA-B", profile={}, path=database)
    kept = upsert_compound(project_id, compound_id="b", original_smiles="CCO", standardized_smiles="CCO", inchikey="KEY-AAA-B", profile={}, duplicate_policy="keep_separate", path=database)
    assert kept["action"] == "kept_separate"
    assert len(list_compounds(project_id, path=database)) == 2
    assert len(list_projects(limit=0, path=database)) == 1
    with pytest.raises(ValueError, match="confidence"):
        add_evidence(project_id, entity_type="target", entity_id="T", evidence_type="x", source="s", payload={}, confidence=2, path=database)
    with pytest.raises(ValueError, match="required"):
        register_endpoint_model_card(model_card={}, qualification={}, path=database)
    saved = register_endpoint_model_card(
        model_card={"model_id": "m", "endpoint": "e", "version": "1"},
        qualification={"status": "unexpected"},
        path=database,
    )
    assert saved["status"] == "blocked"
    assert len(list_endpoint_model_cards(path=database)) == 1
    assert registry_summary(path=database)["endpoint_models"] == 1


def test_target_evidence_validation_empty_sources_and_recency():
    profile = build_target_evidence_profile("T", [], indication="D")
    assert len(profile.gaps) == 6
    assert profile.source_count == 0
    rows = [
        {"dimension": "disease relevance", "score": 60, "confidence": 80, "source_quality": 90, "evidence_date": "not-a-date", "source": "S"},
        {"dimension": "genetic_evidence", "score": 70, "confidence": 0.8, "source_type": "unknown", "evidence_date": "2000-01-01"},
        {"dimension": "pathway_evidence", "score": 50, "confidence": 0, "source_type": "curated_database"},
        {"dimension": "tractability", "score": 50, "confidence": 0, "source_type": "curated_database"},
        {"dimension": "safety_window", "score": 50, "confidence": 0, "source_type": "curated_database"},
        {"dimension": "experimental_validation", "score": 50, "confidence": 0, "source_type": "curated_database"},
    ]
    profile = build_target_evidence_profile("T", rows, custom_weights={name: 1 for name in profile.dimension_scores})
    assert profile.template == "custom"
    assert profile.dimension_scores["pathway_evidence"] == 50
    with pytest.raises(ValueError, match="unsupported dimension"):
        build_target_evidence_profile("T", [{"dimension": "bad", "score": 1}])
    with pytest.raises(ValueError, match="0–100"):
        build_target_evidence_profile("T", [{"dimension": "tractability", "score": 101}])
    with pytest.raises(ValueError, match="0–1 or 0–100"):
        build_target_evidence_profile("T", [{"dimension": "tractability", "score": 50, "confidence": 101}])


def test_endpoint_plugin_registry_and_docking_branches():
    from biointel.discovery.admet_plugins import EndpointPluginRegistry
    from biointel.discovery.docking import external_docking_readiness, readiness_dict

    registry = EndpointPluginRegistry()
    assert registry.predict("hERG", "CCO")["status"] == "not assessed"
    valid = EndpointModelCard(
        model_id="x", endpoint="hERG", version="1", artifact_sha256="a" * 64,
        training_dataset_sha256="b" * 64, licence="lic", endpoint_definition="e",
        units="probability", split_strategies=["external"], metrics={"auc": 0.8},
        calibration={"ece": 0.1}, applicability_domain={"x": 1},
        independent_validation={"x": 1}, intended_use="screen", limitations=["limit"],
    )
    registry.register(valid, lambda smiles: {"value": 0.2, "input": smiles})
    predicted = registry.predict("hERG", "CCO")
    assert predicted["status"] == "model" and predicted["model_id"] == "x"
    blocked = EndpointModelCard(**{**valid.__dict__, "artifact_sha256": "bad"})
    with pytest.raises(ValueError, match="not qualified"):
        registry.register(blocked, lambda smiles: {})
    readiness = readiness_dict(external_docking_readiness())
    assert "engines" in readiness and "preparation_tools" in readiness
    qualified = evaluate_docking_qualification(
        receptor_prepared=True, ligand_prepared=True, grid_defined=True,
        reference_ligand_available=True, redocking_rmsd_angstrom=1.5,
        enrichment_factor_1_percent=5.0, pose_review_completed=True,
        protocol={"engine": "validated external engine"},
    )
    assert qualified.qualified is True
    blocked_gate = evaluate_docking_qualification(
        receptor_prepared=False, ligand_prepared=False, grid_defined=False,
        reference_ligand_available=False, redocking_rmsd_angstrom=4.0,
        enrichment_factor_1_percent=None, pose_review_completed=False,
    )
    assert blocked_gate.qualified is False and blocked_gate.blockers
