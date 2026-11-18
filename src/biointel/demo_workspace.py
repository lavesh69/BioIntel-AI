from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from biointel.database.core import managed_connect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pandas as pd

from biointel.data.dataset_registry import register_dataset
from biointel.data.evidence_registry import (
    complete_import_run,
    evidence_readiness,
    link_curated_dataset,
    record_review,
    register_publication,
    register_source,
    registry_summary,
    seed_standard_licenses,
    start_import_run,
)
from biointel.documents.history import history_summary, list_runs
from biointel.documents.service import process_document
from biointel.dti.drug_features import extract_drug_features
from biointel.dti.feature_cache import FeatureCache
from biointel.dti.protein_features import extract_protein_features
from biointel.internet.download_registry import download_summary, register_download
from biointel.jobs.local_queue import LocalJobQueue
from biointel.runtime_paths import runtime_data_directory, runtime_data_path, runtime_database_path


def _demo_frame() -> pd.DataFrame:
    compounds = [
        ("Aspirin reference", "CC(=O)OC1=CC=CC=C1C(=O)O"),
        ("Caffeine reference", "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"),
        ("Ibuprofen reference", "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"),
        ("Acetaminophen reference", "CC(=O)NC1=CC=C(C=C1)O"),
        ("Nicotinamide reference", "NC(=O)C1=CN=CC=C1"),
        ("Adenosine reference", "NC1=NC=NC2=C1N=CN2C3OC(CO)C(O)C3O"),
        ("Warfarin reference", "CC(C(=O)CC1=CC=CC=C1)C2=C(O)C=CC=C2O"),
        ("Metformin reference", "CN(C)C(=N)N=C(N)N"),
        ("Quercetin reference", "OC1=CC(O)=C(C=C1)C2=COC3=CC(O)=CC(O)=C3C2=O"),
        ("Resveratrol reference", "OC1=CC=C(C=C1)C=CC2=CC(O)=CC(O)=C2"),
    ]
    targets = [
        ("PTGS2", "MALLLARLALVGAAVA", "IC50"),
        ("ADORA2A", "MPIMGSSVYITVELAIAVLAILGNVLVCWAV", "Ki"),
        ("SIRT1", "MADEHGLKSV", "EC50"),
        ("PIK3CA", "MALNIRKILKYGKRGK", "IC50"),
        ("VKORC1", "MARGAAAAPG", "IC50"),
        ("PRKAA1", "MSSPAVTPEQ", "EC50"),
    ]
    source_names = [
        "BioIntel Demonstration Assay Pack",
        "BioIntel Demonstration Literature Pack",
        "BioIntel Demonstration Spreadsheet Import",
        "BioIntel Demonstration Document Bridge",
    ]
    rows: list[dict[str, Any]] = []
    for index in range(600):
        compound_name, smiles = compounds[index % len(compounds)]
        target, sequence, endpoint = targets[(index * 3 + index // 10) % len(targets)]
        value = float(15 + ((index * 137) % 12000))
        review = "accepted" if index % 10 < 6 else ("pending" if index % 10 < 9 else "rejected")
        rows.append(
            {
                "evidence_key": hashlib.sha256(
                    f"demo|{index}|{smiles}|{target}|{value}".encode()
                ).hexdigest(),
                "compound_name": compound_name,
                "canonical_smiles": smiles,
                "compound_inchikey": hashlib.sha1(smiles.encode()).hexdigest()[:27].upper(),
                "target_name": target,
                "protein_sequence": sequence,
                "target_sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
                "activity_type": endpoint,
                "p_activity": round(9 - math.log10(value), 4),
                "standard_value": value,
                "standard_units": "nM",
                "standard_relation": "=",
                "assay_id": f"DEMO-ASSAY-{(index % 60) + 1:03d}",
                "source_record_id": f"DEMO-ROW-{index + 1:04d}",
                "publication_id": f"DEMO-PUB-{(index % 100) + 1:03d}",
                "license_id": "LOCAL_USER_SUPPLIED",
                "assay_quality_score": round(0.58 + (index % 8) * 0.05, 2),
                "review_status": review,
                "source_database": source_names[index % len(source_names)],
                "organism": "Homo sapiens",
                "notes": "Demonstration/reference row only; not experimental evidence.",
            }
        )
    return pd.DataFrame(rows)



def _ensure_demo_corpus(root: Path) -> None:
    """Create a broad, clearly labelled local corpus for non-empty UI demonstrations."""
    folder = runtime_data_path(root, "examples", "demo_workspace", "generated_corpus")
    folder.mkdir(parents=True, exist_ok=True)
    topics = [
        ("oncology", "EGFR", "gefitinib", "non-small-cell lung cancer", "L858R", "IC50", "Homo sapiens"),
        ("cardiology", "KCNH2", "dofetilide", "cardiac arrhythmia", "T618I", "Ki", "Homo sapiens"),
        ("neurology", "ACHE", "donepezil", "Alzheimer disease", "Y337A", "IC50", "Homo sapiens"),
        ("infection", "gyrA", "ciprofloxacin", "bacterial infection", "S83L", "MIC", "Escherichia coli"),
        ("metabolism", "PPARG", "rosiglitazone", "type 2 diabetes", "P12A", "EC50", "Homo sapiens"),
        ("inflammation", "TNF", "infliximab", "rheumatoid arthritis", "G308A", "EC50", "Homo sapiens"),
        ("rare_disease", "CFTR", "ivacaftor", "cystic fibrosis", "G551D", "EC50", "Homo sapiens"),
        ("kinase", "BRAF", "vemurafenib", "melanoma", "V600E", "IC50", "Homo sapiens"),
        ("antiviral", "NS5B", "sofosbuvir", "hepatitis C", "S282T", "IC50", "Hepatitis C virus"),
        ("immunology", "JAK1", "upadacitinib", "atopic dermatitis", "V658F", "IC50", "Homo sapiens"),
    ]
    for idx, (topic, gene, drug, disease, mutation, assay, organism) in enumerate(topics, 1):
        base = {
            "document_id": f"DEMO-CORPUS-{idx:02d}",
            "topic": topic,
            "gene": gene,
            "drug": drug,
            "disease": disease,
            "mutation": mutation,
            "assay": assay,
            "activity_value_nm": 25 + idx * 73,
            "organism": organism,
            "pmid": "",
            "doi": "",
            "synthetic_reference_id": f"SYN-PAPER-{idx:04d}",
            "synthetic_doi_label": f"SYN-DOI-NOT-REAL-{idx:04d}",
            "scientific_release_eligible": False,
            "notice": "Demonstration/reference content only; not experimental or clinical evidence.",
        }
        narrative = (
            f"BioIntel demonstration record {idx}. The compound {drug} was discussed with target {gene} "
            f"in the context of {disease}. The example mutation is {mutation}. A demonstration {assay} "
            f"measurement of {base['activity_value_nm']} nM is shown for {organism}. "
            f"Synthetic reference labels: {base['synthetic_reference_id']} and {base['synthetic_doi_label']}. "
            "This content exists only to populate document search, extraction, entity recognition, "
            "history, comparison and evidence-bridge screens."
        )
        (folder / f"{idx:02d}_{topic}_brief.md").write_text(
            f"# {topic.replace('_',' ').title()} Demonstration Brief\n\n## Summary\n{narrative}\n\n"
            f"## Methods\nSynthetic reference table; {assay} endpoint.\n\n## Limitations\n{base['notice']}\n",
            encoding="utf-8",
        )
        (folder / f"{idx:02d}_{topic}_protocol.txt").write_text(
            f"DEMO PROTOCOL {idx}\nTarget: {gene}\nCompound: {drug}\nDisease: {disease}\n"
            f"Mutation: {mutation}\nAssay: {assay}\nOrganism: {organism}\n"
            f"Result: {base['activity_value_nm']} nM\n{base['notice']}\n",
            encoding="utf-8",
        )
        (folder / f"{idx:02d}_{topic}_metadata.json").write_text(
            json.dumps(base, indent=2, sort_keys=True), encoding="utf-8"
        )
        (folder / f"{idx:02d}_{topic}_table.csv").write_text(
            "record_id,compound,target,disease,mutation,assay,value_nm,organism,status\n"
            f"{base['document_id']},{drug},{gene},{disease},{mutation},{assay},{base['activity_value_nm']},{organism},demo_only\n"
            f"{base['document_id']}-B,{drug} analogue,{gene},{disease},{mutation},{assay},{base['activity_value_nm'] + 110},{organism},demo_only\n",
            encoding="utf-8",
        )
        (folder / f"{idx:02d}_{topic}_page.html").write_text(
            "<!doctype html><html><head><title>BioIntel Demo</title></head><body>"
            f"<h1>{topic.title()} reference page</h1><p>{narrative}</p>"
            f"<table><tr><th>Compound</th><th>Target</th><th>Assay</th><th>Value nM</th></tr>"
            f"<tr><td>{drug}</td><td>{gene}</td><td>{assay}</td><td>{base['activity_value_nm']}</td></tr></table>"
            f"<p><strong>Notice:</strong> {base['notice']}</p></body></html>",
            encoding="utf-8",
        )


def _ensure_download_corpus(root: Path) -> None:
    folder = runtime_data_path(root, "internet_downloads", "demo_preloaded")
    folder.mkdir(parents=True, exist_ok=True)
    providers = ["4HHB", "pubchem", "uniprot", "chembl", "bindingdb", "pubmed"]
    for provider in providers:
        for version in range(1, 13):
            if provider == "4HHB":
                name = f"4HHB_reference_demo_v{version}.cif"
                content = f"data_4HHB_demo_{version}\n_entry.id 4HHB\n# DEMO ONLY\n"
            elif provider == "uniprot":
                name = f"uniprot_ptgs2_reference_v{version}.fasta"
                content = f">sp|P35354|PTGS2_HUMAN DEMO VERSION {version}\nMALLLARLALVGAAVA{version}AAAA\n"
            elif provider == "bindingdb":
                name = f"bindingdb_reference_rows_v{version}.tsv"
                content = "Ligand\tTarget\tKi_nM\tNotice\nAspirin\tPTGS2\t125\tDEMO_ONLY\n"
            else:
                name = f"{provider}_reference_v{version}.json"
                content = json.dumps({
                    "provider": provider,
                    "version": version,
                    "resource": f"DEMO-{provider.upper()}-{version:03d}",
                    "target": ["PTGS2", "EGFR", "BRAF", "ACHE"][version % 4],
                    "compound": ["aspirin", "gefitinib", "vemurafenib", "donepezil"][version % 4],
                    "demo_only": True,
                    "notice": "Offline reference cache; not authoritative scientific data.",
                }, indent=2)
            path = folder / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")

def _seed_documents(root: Path) -> None:
    _ensure_demo_corpus(root)
    folder = runtime_data_path(root, "examples", "demo_workspace")
    if not folder.is_dir():
        return
    supported = {".pdf", ".docx", ".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".txt", ".md", ".html", ".htm", ".json", ".xml", ".yaml", ".yml", ".pptx", ".odt", ".ods"}
    paths = [path for path in sorted(folder.rglob("*")) if path.is_file() and path.suffix.lower() in supported]
    history = runtime_database_path(root, "document_history.sqlite3")
    existing_hashes = {run.source_sha256 for run in list_runs(history, include_deleted=True, limit=10000)}
    for index, path in enumerate(paths, 1):
        data = path.read_bytes()
        source_hash = hashlib.sha256(data).hexdigest()
        if source_hash in existing_hashes:
            continue
        topic = path.stem.split("_")[1] if path.parent.name == "generated_corpus" and "_" in path.stem else path.suffix.lower().lstrip(".")
        process_document(
            path.name,
            data,
            project_root=root,
            keep_source=True,
            ocr_mode="off",
            duplicate_policy="reuse",
            project_code=f"DEMO-DOC-{(index % 12) + 1:02d}",
            tags=["demo", "preloaded", topic, path.suffix.lower().lstrip(".")],
            notes="Preloaded demonstration content. Not experimental evidence.",
        )
        existing_hashes.add(source_hash)


def _seed_evidence(root: Path) -> str:
    evidence_db = runtime_database_path(root, "evidence.sqlite3")
    dataset_db = runtime_database_path(root, "datasets.sqlite3")
    seed_standard_licenses(evidence_db)
    frame = _demo_frame()
    dataset = register_dataset(
        dataset_db,
        frame,
        dataset_name="BioIntel Preloaded Demonstration Evidence",
        dataset_version="1.0",
        task_type="unlabelled",
        source_description="Preloaded synthetic/reference records for UI demonstrations.",
        activity_type="mixed",
        notes="DEMO ONLY - not scientific evidence.",
        metadata={
            "synthetic": True,
            "real_experimental_data": False,
            "scientific_release_eligible": False,
            "preloaded_demo": True,
        },
    )
    source_names = sorted(frame["source_database"].unique())
    sources = {}
    for source_name in source_names:
        sources[source_name] = register_source(
            evidence_db,
            source_name=source_name,
            source_release="demo-v1",
            license_id="LOCAL_USER_SUPPLIED",
            record_count=int((frame["source_database"] == source_name).sum()),
            metadata={
                "synthetic_demo": True,
                "scientific_release_eligible": False,
                "purpose": "Populate UI and demonstrate workflow",
            },
        )
    for index in range(1, 101):
        publication_id = f"DEMO-PUB-{index:03d}"
        register_publication(
            evidence_db,
            publication_id=publication_id,
            pmid="",
            doi="",
            title=f"BioIntel demonstration reference record {index}",
            journal="BioIntel Demo Journal",
            publication_year=2020 + (index % 6),
            metadata={"synthetic_demo": True, "synthetic_reference_id": f"SYN-PAPER-{index:04d}", "synthetic_doi_label": f"SYN-DOI-NOT-REAL-{index:04d}"},
        )
    for source_name, source in sources.items():
        subset = frame[frame["source_database"] == source_name]
        link_curated_dataset(
            evidence_db,
            dataset_sha256=dataset.dataset_sha256,
            source_id=source.source_id,
            curated=subset,
            default_license_id="LOCAL_USER_SUPPLIED",
        )
    with managed_connect(evidence_db) as connection:
        existing_runs = {
            str(row[0])
            for row in connection.execute(
                "SELECT provider FROM evidence_import_runs WHERE source_release='demo-v1'"
            )
        }
        reviewed = {
            str(row[0])
            for row in connection.execute(
                "SELECT evidence_key FROM evidence_reviews WHERE dataset_sha256=?",
                (dataset.dataset_sha256,),
            )
        }
    for source_name in source_names:
        if source_name not in existing_runs:
            subset = frame[frame["source_database"] == source_name]
            run = start_import_run(
                evidence_db,
                provider=source_name,
                source_release="demo-v1",
                parameters={"synthetic_demo": True, "preloaded": True},
            )
            complete_import_run(
                evidence_db,
                run.run_id,
                status="completed",
                input_rows=len(subset),
                curated_rows=len(subset),
                rejected_rows=0,
                report={"demo_only": True, "dataset_sha256": dataset.dataset_sha256},
            )
    for row in frame.to_dict(orient="records"):
        if row["review_status"] != "pending" and row["evidence_key"] not in reviewed:
            record_review(
                evidence_db,
                dataset_sha256=dataset.dataset_sha256,
                evidence_key=row["evidence_key"],
                decision=row["review_status"],
                reviewer="BioIntel Demo Seeder",
                comment="Preloaded demonstration decision; not a scientific approval.",
                original=row,
            )
    for subset_index in range(1, 13):
        subset = frame.iloc[(subset_index - 1) * 50 : subset_index * 50].copy()
        subset["demo_subset"] = subset_index
        register_dataset(
            dataset_db,
            subset,
            dataset_name=f"BioIntel Demo Dataset Pack {subset_index:02d}",
            dataset_version="2.0",
            task_type="classification" if subset_index % 2 else "regression",
            source_description="Preloaded synthetic/reference subset for populated UI demonstrations.",
            activity_type="mixed",
            parent_sha256=dataset.dataset_sha256,
            notes="DEMO ONLY - not scientific evidence.",
            metadata={"synthetic": True, "preloaded_demo": True, "subset_index": subset_index},
        )
    return dataset.dataset_sha256


def _seed_downloads(root: Path) -> None:
    _ensure_download_corpus(root)
    folder = runtime_data_path(root, "internet_downloads", "demo_preloaded")
    if not folder.is_dir():
        return
    provider_map = {
        "4HHB": ("RCSB PDB", "https://files.rcsb.org/download/4HHB.cif", "chemical/x-cif"),
        "pubchem": ("PubChem", "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/JSON", "application/json"),
        "uniprot": ("UniProt", "https://rest.uniprot.org/uniprotkb/P35354.fasta", "text/plain"),
        "chembl": ("ChEMBL", "https://www.ebi.ac.uk/chembl/api/data/target/CHEMBL230.json", "application/json"),
        "bindingdb": ("BindingDB", "https://www.bindingdb.org/rwd/bind/index.jsp", "text/tab-separated-values"),
        "pubmed": ("NCBI PubMed", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi", "application/json"),
    }
    database = runtime_database_path(root, "internet_downloads.sqlite3")
    existing_sha256: set[str] = set()
    if database.is_file():
        with managed_connect(database) as connection:
            existing_sha256 = {str(row[0]) for row in connection.execute("SELECT sha256 FROM internet_downloads")}
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest in existing_sha256:
            continue
        lowered = path.name.lower()
        key = next((item for item in provider_map if item.lower() in lowered), None)
        if key is None:
            continue
        provider, base_url, content_type = provider_map[key]
        register_download(
            database,
            provider=provider,
            resource_id=path.stem.upper(),
            url=f"{base_url}?biointel_demo_file={path.name}",
            filename=path.name,
            relative_path=f"data/{path.relative_to(runtime_data_directory(root)).as_posix()}",
            content_type=content_type,
            size_bytes=len(data),
            sha256=digest,
            notes="Preloaded offline demonstration cache. Not an authoritative source record.",
        )
        existing_sha256.add(digest)


def _seed_jobs(root: Path) -> None:
    queue = LocalJobQueue(runtime_database_path(root, "jobs.sqlite3"))
    current = len(queue.list(limit=1000))
    target = 120
    for index in range(current, target):
        job_type = [
            "document_extraction", "batch_prediction", "evidence_index", "database_optimization",
            "knowledge_index", "scheduled_refresh", "benchmark_validation", "report_generation",
        ][index % 8]
        job = queue.submit(
            job_type,
            {"demo": True, "record_count": 25 + index * 3, "source": f"preloaded-{index + 1}", "notice": "DEMO ONLY"},
            priority=30 + (index % 12) * 10,
            max_attempts=2,
        )
        mode = index % 10
        if mode < 6:
            claimed = queue.claim_next(job_type=job_type)
            if claimed:
                queue.complete(claimed.job_id, {"status": "demo completed", "processed": 25 + index * 3, "warnings": index % 4})
        elif mode == 6:
            claimed = queue.claim_next(job_type=job_type)
            if claimed:
                queue.fail(claimed.job_id, "Demonstration validation failure.", retry=False)
        elif mode == 7:
            queue.request_cancel(job.job_id)
        elif mode == 8:
            queue.claim_next(job_type=job_type)
        # mode 9 remains queued



def _seed_feature_cache(root: Path) -> None:
    cache = FeatureCache(runtime_database_path(root, "feature_cache.sqlite3"))
    directory = runtime_data_path(root, "chemistry", "common_compound_directory_5000.csv")
    if directory.is_file():
        values = pd.read_csv(directory, usecols=["canonical_smiles"]).dropna()["canonical_smiles"].astype(str).head(80).tolist()
    else:
        values = ["CCO", "CCN", "CC(=O)O", "c1ccccc1", "C1CCCCC1"]
    for smiles in values:
        try:
            feature = extract_drug_features(smiles, radius=2, n_bits=256, use_chirality=True)
            cache.put_drug(smiles, feature)
            cache.get_drug(smiles, radius=2, n_bits=256, use_chirality=True)
        except Exception:
            continue
    amino = "ACDEFGHIKLMNPQRSTVWY"
    sequences = ["M" + "".join(amino[(index + offset) % len(amino)] for offset in range(40 + index % 25)) for index in range(40)]
    for sequence in sequences:
        feature = extract_protein_features(sequence, include_dipeptides=False)
        cache.put_protein(sequence, feature)
        cache.get_protein(sequence, include_dipeptides=False)




def _seed_ocr_corrections(root: Path) -> None:
    from biointel.documents.history import record_ocr_correction
    history = runtime_database_path(root, "document_history.sqlite3")
    runs = list_runs(history, include_deleted=False, limit=10000)
    if not runs:
        return
    with managed_connect(history) as connection:
        existing = int(connection.execute("SELECT COUNT(*) FROM document_ocr_corrections").fetchone()[0])
    target = 30
    for index in range(existing, target):
        run = runs[index % len(runs)]
        try:
            record_ocr_correction(
                history,
                run_id=run.run_id,
                region_id=f"demo-region-{index + 1:03d}",
                original_text=["lC50 125 nM", "EGFR L858l", "PMlD 2026001"][index % 3],
                corrected_text=["IC50 125 nM", "EGFR L858I", "PMID 2026001"][index % 3],
                reviewer="BioIntel Demo Reviewer",
                comment="Demonstration correction record; not a real OCR review.",
            )
        except Exception:
            continue


def _seed_projects(root: Path) -> None:
    from biointel.governance.governance_registry import initialize_governance_registry
    from biointel.portfolio.project_registry import initialize_project_registry

    database = runtime_database_path(root, "projects.sqlite3")
    initialize_project_registry(database)
    initialize_governance_registry(database)
    now = datetime.now(UTC)
    statuses = ["Planning", "Active", "Validation", "Paused", "Completed", "Archived"]
    priorities = ["Low", "Medium", "High", "Critical"]
    gates = ["Data readiness", "Model validation", "External validation", "Reproducibility", "Release approval"]
    with managed_connect(database) as connection:
        existing = int(connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0])
        for index in range(existing, 30):
            project_id = str(uuid5(NAMESPACE_URL, f"biointel-demo-project-{index}"))
            code = f"DEMO-PROJ-{index + 1:02d}"
            created = (now - timedelta(days=180 - index * 3)).isoformat(timespec="seconds")
            connection.execute(
                "INSERT OR IGNORE INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, code, f"Demonstration Research Project {index + 1:02d}", statuses[index % len(statuses)], priorities[index % len(priorities)],
                 f"Demonstrate populated workflows for project area {index + 1}.", "BioIntel Demo Team", json.dumps(["demo", "reference", f"portfolio-{index % 5 + 1}"]),
                 (now + timedelta(days=30 + index * 5)).date().isoformat(), None, None, "DEMO ONLY - not a real research project.", created, created),
            )
            for m in range(4):
                mid = str(uuid5(NAMESPACE_URL, f"{project_id}-milestone-{m}"))
                connection.execute(
                    "INSERT OR IGNORE INTO project_milestones VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (mid, project_id, ["Data intake", "Curation", "Validation", "Review package"][m], ["Completed", "In Progress", "Planned", "Blocked"][(index + m) % 4],
                     (now + timedelta(days=10 + index + m * 14)).date().isoformat(), "Demo Owner", "Demonstration acceptance criteria", f"DEMO-EVIDENCE-{index + 1:02d}-{m + 1}", "Demo milestone", created, created),
                )
            for g, gate in enumerate(gates):
                gid = str(uuid5(NAMESPACE_URL, f"{project_id}-gate-{g}"))
                connection.execute(
                    "INSERT OR IGNORE INTO project_gates VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (gid, project_id, gate, ["Pending", "Conditional", "Approved", "Rejected"][(index + g) % 4], "Demo Reviewer", "Demonstration conditions", f"DEMO-GATE-{index + 1:02d}-{g + 1}",
                     (now - timedelta(days=g)).date().isoformat() if (index + g) % 4 in {2,3} else None, created, created),
                )
            for e in range(5):
                eid = str(uuid5(NAMESPACE_URL, f"{project_id}-event-{e}"))
                connection.execute(
                    "INSERT OR IGNORE INTO project_events VALUES (?,?,?,?,?,?)",
                    (eid, project_id, ["created", "data_update", "model_review", "risk", "status_change"][e], f"Demonstration event {e + 1} for {code}.",
                     (now - timedelta(days=index * 2 + e)).isoformat(timespec="seconds"), json.dumps({"demo": True, "sequence": e + 1})),
                )
            did = str(uuid5(NAMESPACE_URL, f"{project_id}-decision"))
            connection.execute(
                "INSERT OR IGNORE INTO project_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (did, project_id, "Demonstration workflow decision", ["Proposed", "Approved", "Superseded", "Reversed"][index % 4], (now - timedelta(days=index)).date().isoformat(),
                 "Populate governance screens", "Use clearly labelled demonstration records", "Improve learning experience without claiming scientific validity", "Leave screens empty", "UI and workflow demonstration only", "Demo Approver", f"DEMO-DECISION-{index + 1:02d}", created, created),
            )
        connection.commit()

def _spread_demo_timestamps(root: Path) -> None:
    now = datetime.now(UTC)
    plans = [
        (runtime_database_path(root, "document_history.sqlite3"), "document_extraction_runs", "run_id", "started_at_utc", "completed_at_utc"),
        (runtime_database_path(root, "internet_downloads.sqlite3"), "internet_downloads", "download_id", "downloaded_at_utc", None),
        (runtime_database_path(root, "jobs.sqlite3"), "local_jobs", "job_id", "created_at_utc", "completed_at_utc"),
        (runtime_database_path(root, "evidence.sqlite3"), "evidence_import_runs", "run_id", "started_at_utc", "completed_at_utc"),
    ]
    for database, table, key_column, start_column, end_column in plans:
        if not database.is_file():
            continue
        with managed_connect(database) as connection:
            keys = [row[0] for row in connection.execute(f'SELECT "{key_column}" FROM "{table}" ORDER BY rowid')]
            for index, key in enumerate(keys):
                started = now - timedelta(days=(len(keys) - index) * 2, hours=index % 8)
                if end_column:
                    connection.execute(
                        f'UPDATE "{table}" SET "{start_column}"=?, "{end_column}"=COALESCE("{end_column}", ?) WHERE "{key_column}"=?',
                        (started.isoformat(timespec="seconds"), (started + timedelta(minutes=5 + index)).isoformat(timespec="seconds"), key),
                    )
                else:
                    connection.execute(
                        f'UPDATE "{table}" SET "{start_column}"=? WHERE "{key_column}"=?',
                        (started.isoformat(timespec="seconds"), key),
                    )
            connection.commit()


def seed_demo_workspace(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    _seed_documents(root)
    dataset_sha256 = _seed_evidence(root)
    _seed_downloads(root)
    _seed_jobs(root)
    _seed_feature_cache(root)
    _seed_ocr_corrections(root)
    _seed_projects(root)
    _spread_demo_timestamps(root)
    queue = LocalJobQueue(runtime_database_path(root, "jobs.sqlite3"))
    return {
        "demo_only": True,
        "dataset_sha256": dataset_sha256,
        "documents": history_summary(runtime_database_path(root, "document_history.sqlite3")),
        "evidence": registry_summary(runtime_database_path(root, "evidence.sqlite3")),
        "evidence_readiness": evidence_readiness(runtime_database_path(root, "evidence.sqlite3"), dataset_sha256),
        "downloads": download_summary(runtime_database_path(root, "internet_downloads.sqlite3")),
        "jobs": {
            status: len(queue.list(status=status, limit=1000))
            for status in sorted(queue.VALID_STATUSES)
        },
        "feature_cache": FeatureCache(runtime_database_path(root, "feature_cache.sqlite3")).stats().__dict__,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
