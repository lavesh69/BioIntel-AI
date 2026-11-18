from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add("Version", version == "13.2.0", f"VERSION={version}")

    from biointel.scientific_depth.capability import CAPABILITY_SPECS
    from biointel.step121.automl import resource_bounded_automl
    from biointel.step121.citations import build_citation_workspace, export_bibtex, export_ris
    from biointel.step121.evidence import build_evidence_workspace
    from biointel.step121.family_genetics import analyse_family_variants
    from biointel.step121.microbiology_isolate import analyse_isolate, parse_fasta_text
    from biointel.step121.model_assurance import run_assurance_suite
    from biointel.step121.organoid import analyse_organoid_experiment

    selected = {
        "rare_variant_family",
        "explainable_ai_assurance",
        "microbiology_metagenomics",
        "ml_autolab",
        "evidence_citation_engine",
        "organoid_3d",
        "real_evidence_studio",
    }
    missing = sorted(selected - set(CAPABILITY_SPECS))
    stage_count = sum(len(CAPABILITY_SPECS[key].stages) for key in selected if key in CAPABILITY_SPECS)
    external = all(any(stage.mode == "external-validation" for stage in CAPABILITY_SPECS[key].stages) for key in selected if key in CAPABILITY_SPECS)
    add("Selected capability contracts", not missing and stage_count >= 42 and external, f"7 modules, {stage_count} stages; missing={missing}")

    pedigree = pd.DataFrame(
        [["F1", "F", "0", "0", 1, 1], ["F1", "M", "0", "0", 2, 1], ["F1", "C", "F", "M", 1, 2]],
        columns=["family_id", "individual_id", "father_id", "mother_id", "sex", "phenotype"],
    )
    variants = pd.DataFrame(
        [["v1", "G1", "F", "0/0", 30, 0.0, 0.0001], ["v1", "G1", "M", "0/0", 30, 0.0, 0.0001], ["v1", "G1", "C", "0/1", 40, 0.5, 0.0001]],
        columns=["variant_id", "gene", "sample_id", "genotype", "depth", "alt_fraction", "population_af"],
    )
    family = analyse_family_variants(pedigree, variants)
    add("Family genetics", len(family.de_novo_candidates) == 1 and not family.release_gate["diagnostic_release_ready"], f"de_novo={len(family.de_novo_candidates)}")

    rng = np.random.default_rng(121)
    n = 120
    assurance_frame = pd.DataFrame({"x1": rng.normal(size=n), "x2": rng.normal(size=n), "group": rng.choice(["A", "B"], n)})
    assurance_frame["target"] = (assurance_frame["x1"] - 0.5 * assurance_frame["x2"] + rng.normal(0, 0.4, n) > 0).astype(int)
    assurance = run_assurance_suite(assurance_frame, target_column="target", group_column="group", stability_repeats=3)
    add("Model assurance", not assurance.calibration.empty and not assurance.ood_scores.empty and not assurance.explanation_stability.empty, f"metrics={list(assurance.metrics.columns)}")

    locus_a = "ATGCGTACGTAGCTAGCTAGCGGATCCGATCGATCGATCGATCG"
    locus_b = "TTGCAACCGGTTAACCGGTTAACCGGTTAGCTAGCTAGCTAGCTA"
    gene = "GGTACCGGTACCGGTACCGGTACCGGTACCGGTACC"
    isolate = analyse_isolate(
        parse_fasta_text(f">c1\n{locus_a * 4}{gene * 3}\n>c2\n{locus_b * 4}\n"),
        taxonomy_references=pd.DataFrame([["Taxon A", locus_a * 3 + locus_b * 3]], columns=["taxon", "sequence"]),
        allele_catalog=pd.DataFrame([["abc", "1", locus_a], ["xyz", "4", locus_b]], columns=["locus", "allele", "sequence"]),
        mlst_profiles=pd.DataFrame([["ST1", "1", "4"]], columns=["sequence_type", "abc", "xyz"]),
        gene_catalog=pd.DataFrame([["geneA", gene, "AMR", "drugx", "2026.1"]], columns=["gene", "sequence", "category", "phenotype", "database_release"]),
        phenotype=pd.DataFrame([["drugx", "resistant"]], columns=["drug", "phenotype"]),
    )
    add("Microbiology isolate", set(isolate.mlst_calls["call_status"]) == {"called"} and bool(isolate.gene_hits.iloc[0]["present"]), f"mlst={len(isolate.mlst_calls)}; gene_hits={int(isolate.gene_hits['present'].sum())}")

    automl_frame = assurance_frame.rename(columns={"target": "label"}).drop(columns=["group"])
    automl = resource_bounded_automl(automl_frame, target_column="label", cv_folds=3, max_candidates=2, max_rows=500)
    add("Bounded AutoML", len(automl.leaderboard) == 2 and len(automl.artifact_bytes) > 500 and not automl.model_card["release_ready"], f"champion={automl.search_manifest['champion']}")

    citations = build_citation_workspace(
        pd.DataFrame(
            [["C1", "Claim", "10.1000/a", "", "Study A", "support"], ["C1", "Claim", "10.1000/b", "", "Study B", "oppose"]],
            columns=["claim_id", "claim_text", "doi", "pmid", "title", "evidence_direction"],
        )
    )
    add("Citation engine", bool(citations.claim_summary.iloc[0]["conflict_present"]) and "@article" in export_bibtex(citations.citations) and "TY  - JOUR" in export_ris(citations.citations), f"claims={len(citations.claim_summary)}")

    organoid_rows = []
    for row in "AB":
        for column in range(1, 9):
            concentration = [0.01, 0.1, 1.0, 10.0][(column - 1) % 4]
            for obj in range(3):
                organoid_rows.append({"object_id": f"{row}{column}_{obj}", "well": f"{row}{column:02d}", "plate_row": row, "plate_column": column, "compound": "Drug", "concentration": concentration, "volume_um3": 10000 / (1 + concentration) + rng.normal(0, 100), "sphericity": rng.normal(0.8, 0.03), "image_id": f"I{row}{column}", "replicate": obj + 1})
    organoid = analyse_organoid_experiment(pd.DataFrame(organoid_rows), value_column="volume_um3")
    add("Organoid analytics", "plate_normalized_value" in organoid.normalized_measurements and not organoid.morphology_embedding.empty, f"objects={len(organoid.normalized_measurements)}")

    evidence = build_evidence_workspace(
        pd.DataFrame(
            [["E1", "genomics", "V1", "Claim", "support", "cohort", "doi:x", "v1", True, "R1", "accepted", "CC-BY"], ["E1", "genomics", "V1", "Claim", "support", "cohort", "doi:x", "v1", True, "R2", "accepted", "CC-BY"]],
            columns=["evidence_id", "domain", "subject_id", "claim", "direction", "study_design", "source", "version", "independent", "reviewer_id", "review_decision", "license"],
        )
    )
    add("Cross-domain evidence", evidence.adjudication.iloc[0]["adjudication_status"] == "accepted_by_independent_reviewers" and not evidence.release_gate["scientific_release_ready"], f"domains={len(evidence.domain_summary)}")

    pages = {
        "pages/147_Rare_Variant_Burden_Family_Genetics_Lab.py": "render_family_genetics_upgrade",
        "pages/128_Explainable_AI_and_Model_Assurance_Center.py": "render_model_assurance_upgrade",
        "pages/65_Microbiology_Metagenomics.py": "render_microbiology_isolate_upgrade",
        "pages/34_ML_AutoLab.py": "render_automl_upgrade",
        "pages/155_Scientific_Evidence_Citation_Engine.py": "render_citation_upgrade",
        "pages/142_Organoid_3D_Cell_Model_Analytics.py": "render_organoid_upgrade",
        "pages/46_Real_Evidence_Studio.py": "render_real_evidence_upgrade",
    }
    missing_page_tokens = [path for path, token in pages.items() if token not in (ROOT / path).read_text(encoding="utf-8")]
    add("Page integration", not missing_page_tokens, f"{len(pages)-len(missing_page_tokens)}/{len(pages)} pages integrated; missing={missing_page_tokens}")

    templates = list((ROOT / "data" / "templates" / "step121").glob("*"))
    add("Starter templates", len(templates) >= 13, f"{len(templates)} templates")

    locked = {
        "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    changed = [relative for relative, digest in locked.items() if not (ROOT / relative).is_file() or sha256(ROOT / relative) != digest]
    add("Requested exclusions preserved", not changed, f"{len(locked)-len(changed)}/{len(locked)} byte-identical; changed={changed}")

    passed = sum(bool(item["passed"]) for item in checks)
    report = {
        "schema": "biointel.step121.verification.v1",
        "version": version,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }
    out = ROOT / "reports" / "step121_selected_module_verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for item in checks:
        print(("PASS" if item["passed"] else "FAIL") + f" | {item['check']} | {item['detail']}")
    print(f"RESULT | {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
