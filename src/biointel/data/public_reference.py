from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biointel.data.dataset_registry import register_dataset
from biointel.data.readiness import initialize_readiness_schema
from biointel.database.core import transaction


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


UNIPROT_REFERENCES = [
    ("P04637", "TP53", "Cellular tumor antigen p53", "Homo sapiens"),
    ("P00533", "EGFR", "Epidermal growth factor receptor", "Homo sapiens"),
    ("P38398", "BRCA1", "Breast cancer type 1 susceptibility protein", "Homo sapiens"),
    ("P51587", "BRCA2", "Breast cancer type 2 susceptibility protein", "Homo sapiens"),
    ("P31749", "AKT1", "RAC-alpha serine/threonine-protein kinase", "Homo sapiens"),
    ("P28482", "MAPK1", "Mitogen-activated protein kinase 1", "Homo sapiens"),
    ("P27361", "MAPK3", "Mitogen-activated protein kinase 3", "Homo sapiens"),
    ("P42336", "PIK3CA", "PI3-kinase subunit alpha", "Homo sapiens"),
    ("P15056", "BRAF", "Serine/threonine-protein kinase B-raf", "Homo sapiens"),
    ("P01116", "KRAS", "GTPase KRas", "Homo sapiens"),
    ("P01111", "NRAS", "GTPase NRas", "Homo sapiens"),
    ("P01112", "HRAS", "GTPase HRas", "Homo sapiens"),
    ("P03372", "ESR1", "Estrogen receptor", "Homo sapiens"),
    ("P10275", "AR", "Androgen receptor", "Homo sapiens"),
    ("P02768", "ALB", "Albumin", "Homo sapiens"),
    ("P01308", "INS", "Insulin", "Homo sapiens"),
    ("P69905", "HBA1", "Hemoglobin subunit alpha", "Homo sapiens"),
    ("P68871", "HBB", "Hemoglobin subunit beta", "Homo sapiens"),
    ("P02649", "APOE", "Apolipoprotein E", "Homo sapiens"),
    ("P12821", "ACE", "Angiotensin-converting enzyme", "Homo sapiens"),
    ("P05067", "APP", "Amyloid-beta precursor protein", "Homo sapiens"),
    ("P37840", "SNCA", "Alpha-synuclein", "Homo sapiens"),
    ("Q5S007", "LRRK2", "Leucine-rich repeat serine/threonine-protein kinase 2", "Homo sapiens"),
    ("P42858", "HTT", "Huntingtin", "Homo sapiens"),
    ("P13569", "CFTR", "Cystic fibrosis transmembrane conductance regulator", "Homo sapiens"),
]

NCBI_GENE_REFERENCES = [
    ("7157", "TP53"), ("1956", "EGFR"), ("672", "BRCA1"), ("675", "BRCA2"),
    ("3845", "KRAS"), ("673", "BRAF"), ("5290", "PIK3CA"), ("207", "AKT1"),
    ("5594", "MAPK1"), ("5728", "PTEN"), ("4609", "MYC"), ("7422", "VEGFA"),
    ("2064", "ERBB2"), ("348", "APOE"), ("351", "APP"),
]

RCSB_REFERENCES = [
    "4HHB", "1CRN", "1BNA", "1TUP", "1M17", "2SRC", "3ERT", "1ATP", "1AKE", "1TIM",
    "2HYY", "3PP0", "4INS", "1A3N", "1HHO", "5XNL", "6LU7", "6M0J", "7K3G", "7BV2",
]


@dataclass(frozen=True)
class PublicReferenceSummary:
    records: int
    providers: int
    protein_records: int
    gene_records: int
    structure_records: int
    public_dataset_records: int
    public_dataset_count: int
    manifest_path: str
    generated_at_utc: str


def build_public_reference_catalog(root: str | Path) -> PublicReferenceSummary:
    project_root = Path(root).resolve()
    directory = project_root / "data" / "public_reference"
    directory.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for accession, gene, name, organism in UNIPROT_REFERENCES:
        records.append({
            "provider": "UniProt",
            "record_type": "protein",
            "stable_id": accession,
            "symbol": gene,
            "label": name,
            "organism": organism,
            "official_url": f"https://www.uniprot.org/uniprotkb/{accession}/entry",
            "verification_level": "curated_identifier_reference",
            "training_eligible": False,
        })
    for gene_id, symbol in NCBI_GENE_REFERENCES:
        records.append({
            "provider": "NCBI Gene",
            "record_type": "gene",
            "stable_id": gene_id,
            "symbol": symbol,
            "label": f"NCBI Gene {symbol}",
            "organism": "Homo sapiens",
            "official_url": f"https://www.ncbi.nlm.nih.gov/gene/{gene_id}",
            "verification_level": "curated_identifier_reference",
            "training_eligible": False,
        })
    for pdb_id in RCSB_REFERENCES:
        records.append({
            "provider": "RCSB PDB",
            "record_type": "structure",
            "stable_id": pdb_id,
            "symbol": "",
            "label": f"PDB entry {pdb_id}",
            "organism": "",
            "official_url": f"https://www.rcsb.org/structure/{pdb_id}",
            "verification_level": "curated_identifier_reference",
            "training_eligible": False,
        })

    public_datasets = build_public_reference_datasets(project_root)

    csv_path = directory / "verified_public_reference_catalog.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    manifest = {
        "generated_at_utc": utc_now(),
        "record_count": len(records),
        "public_dataset_records": int(public_datasets["records"]),
        "public_dataset_count": int(public_datasets["datasets"]),
        "providers": sorted({row["provider"] for row in records} | {"UCI Machine Learning Repository"}),
        "scientific_boundary": "Identifier-level public reference metadata only; not a training or validation dataset.",
        "records_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "source_documentation": {
            "UniProt": "https://www.uniprot.org/api-documentation",
            "RCSB PDB": "https://www.rcsb.org/docs/programmatic-access/web-apis-overview",
            "NCBI": "https://www.ncbi.nlm.nih.gov/home/develop/api/",
        },
    }
    manifest_path = directory / "verified_public_reference_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    _seed_knowledge(project_root, records)
    _update_provider_counts(project_root, records)
    return PublicReferenceSummary(
        records=len(records),
        providers=len(set(row["provider"] for row in records) | {"UCI Machine Learning Repository"}),
        protein_records=sum(row["record_type"] == "protein" for row in records),
        gene_records=sum(row["record_type"] == "gene" for row in records),
        structure_records=sum(row["record_type"] == "structure" for row in records),
        public_dataset_records=int(public_datasets["records"]),
        public_dataset_count=int(public_datasets["datasets"]),
        manifest_path=manifest_path.relative_to(project_root).as_posix(),
        generated_at_utc=manifest["generated_at_utc"],
    )



def build_public_reference_datasets(project_root: Path) -> dict[str, Any]:
    """Bundle a licensed, real public biomedical reference dataset without claiming release validation."""

    from sklearn.datasets import load_breast_cancer

    directory = project_root / "data" / "public_reference"
    directory.mkdir(parents=True, exist_ok=True)
    bunch = load_breast_cancer(as_frame=True)
    frame = bunch.frame.copy()
    frame.insert(0, "sample_id", [f"WDBC-{index + 1:04d}" for index in range(len(frame))])
    frame["diagnosis_label"] = frame["target"].map({0: "malignant", 1: "benign"})
    csv_path = directory / "uci_breast_cancer_wisconsin_diagnostic.csv"
    frame.to_csv(csv_path, index=False)
    attribution = directory / "UCI_WDBC_ATTRIBUTION.md"
    attribution.write_text(
        "# Breast Cancer Wisconsin (Diagnostic) public reference\n\n"
        "Source: UCI Machine Learning Repository, Breast Cancer Wisconsin (Diagnostic).\n\n"
        "Licence: Creative Commons Attribution 4.0 International (CC BY 4.0).\n\n"
        "Bundled through scikit-learn's `load_breast_cancer` loader. This copy is a public "
        "reference dataset for UI, data-lineage and analytical workflow testing. It is not "
        "clinical advice, a prospective validation cohort, or evidence that BioIntel models are release eligible.\n",
        encoding="utf-8",
    )
    registry = runtime_database_path(project_root, "datasets.sqlite3")
    record = register_dataset(
        registry,
        frame,
        dataset_name="UCI Breast Cancer Wisconsin Diagnostic — Public Reference",
        dataset_version="1995-CC-BY-4.0",
        task_type="classification",
        source_description="UCI Machine Learning Repository public biomedical reference dataset bundled via scikit-learn",
        activity_type=None,
        notes="Real public reference data. Not a BioIntel model validation or clinical release dataset.",
        metadata={
            "source_provider": "UCI Machine Learning Repository",
            "source_dataset": "Breast Cancer Wisconsin (Diagnostic)",
            "licence": "CC BY 4.0",
            "public_reference": True,
            "synthetic": False,
            "clinical_use": False,
            "training_eligible": True,
            "scientific_release_eligible": False,
            "sklearn_loader": "load_breast_cancer",
            "official_source": "https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic",
        },
    )
    initialize_readiness_schema(project_root)
    now = utc_now()
    file_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    with transaction(registry) as connection:
        dataset_sha = record.dataset_sha256
        file_id = hashlib.sha256(f"{dataset_sha}|{csv_path.name}".encode()).hexdigest()[:28]
        connection.execute(
            """INSERT INTO dataset_files(file_id,dataset_sha256,relative_path,file_format,size_bytes,sha256,role,compression,metadata_json,created_at_utc)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(dataset_sha256,relative_path) DO UPDATE SET size_bytes=excluded.size_bytes,sha256=excluded.sha256,metadata_json=excluded.metadata_json""",
            (file_id,dataset_sha,csv_path.relative_to(project_root).as_posix(),"csv",csv_path.stat().st_size,file_sha,"primary",None,json.dumps({"public_reference":True,"licence":"CC BY 4.0"}),now),
        )
        for position, column in enumerate(frame.columns, start=1):
            semantic = "sample_identifier" if column == "sample_id" else "label" if column in {"target", "diagnosis_label"} else "feature"
            connection.execute(
                """INSERT INTO dataset_columns(dataset_sha256,column_name,ordinal_position,data_type,semantic_role,unit,description,nullable,metadata_json)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(dataset_sha256,column_name) DO UPDATE SET ordinal_position=excluded.ordinal_position,data_type=excluded.data_type,semantic_role=excluded.semantic_role""",
                (dataset_sha,str(column),position,str(frame[column].dtype),semantic,None,"UCI WDBC public reference column",0,"{}"),
            )
        for index, row in frame[["sample_id","diagnosis_label"]].iterrows():
            connection.execute(
                """INSERT INTO dataset_samples(sample_id,dataset_sha256,sample_name,organism,tissue_or_matrix,condition_name,batch_name,replicate_type,replicate_number,subject_id,timepoint,metadata_json,created_at_utc)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(dataset_sha256,sample_id) DO UPDATE SET condition_name=excluded.condition_name,metadata_json=excluded.metadata_json""",
                (row["sample_id"],dataset_sha,row["sample_id"],"Homo sapiens","fine-needle aspirate image-derived features",row["diagnosis_label"],"UCI-WDBC",None,None,row["sample_id"],None,json.dumps({"deidentified_public_reference":True}),now),
            )
        qc = {
            "row_count": float(len(frame)),
            "column_count": float(len(frame.columns)),
            "missing_cells": float(frame.isna().sum().sum()),
            "duplicate_rows": float(frame.duplicated().sum()),
            "malignant_samples": float((frame["diagnosis_label"] == "malignant").sum()),
            "benign_samples": float((frame["diagnosis_label"] == "benign").sum()),
        }
        for name, value in qc.items():
            qc_id = hashlib.sha256(f"{dataset_sha}|{name}".encode()).hexdigest()[:28]
            connection.execute(
                """INSERT INTO dataset_qc_metrics(qc_id,dataset_sha256,metric_name,metric_value,metric_text,unit,scope,scope_id,status,threshold_json,created_at_utc)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(dataset_sha256,metric_name,scope,scope_id) DO UPDATE SET metric_value=excluded.metric_value,status=excluded.status""",
                (qc_id,dataset_sha,name,value,None,"count","dataset","", "passed" if name not in {"malignant_samples","benign_samples"} else "informational","{}",now),
            )
        prov_id = hashlib.sha256(f"{dataset_sha}|uci-wdbc".encode()).hexdigest()[:28]
        connection.execute(
            """INSERT INTO dataset_provenance(provenance_id,dataset_sha256,source_type,provider,release_label,licence_id,external_id,access_method,status,retrieved_at_utc,metadata_json,created_at_utc)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(provenance_id) DO UPDATE SET status=excluded.status,metadata_json=excluded.metadata_json""",
            (prov_id,dataset_sha,"public_repository","UCI Machine Learning Repository","1995","CC-BY-4.0","UCI-17","bundled_sklearn_loader","verified_public_reference",now,json.dumps({"attribution_file":attribution.relative_to(project_root).as_posix()}),now),
        )
        connection.execute(
            """INSERT INTO dataset_readiness(dataset_sha256,file_count,column_count,sample_count,qc_count,lineage_count,provenance_count,sample_metadata_applicable,metadata_completeness,integrity_status,scientific_status,readiness_score,blockers_json,warnings_json,calculated_at_utc)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(dataset_sha256) DO UPDATE SET file_count=excluded.file_count,column_count=excluded.column_count,sample_count=excluded.sample_count,qc_count=excluded.qc_count,provenance_count=excluded.provenance_count,metadata_completeness=excluded.metadata_completeness,integrity_status=excluded.integrity_status,scientific_status=excluded.scientific_status,readiness_score=excluded.readiness_score,warnings_json=excluded.warnings_json,calculated_at_utc=excluded.calculated_at_utc""",
            (dataset_sha,1,len(frame.columns),len(frame),len(qc),0,1,1,100.0,"verified","reference_only",100.0,"[]",json.dumps(["Real public reference dataset; not an independent validation cohort for bundled BioIntel models."]),now),
        )
    _register_uci_provider(project_root, len(frame), file_sha)
    return {"datasets": 1, "records": len(frame), "dataset_sha256": record.dataset_sha256, "relative_path": csv_path.relative_to(project_root).as_posix()}


def _register_uci_provider(project_root: Path, records: int, checksum: str) -> None:
    path = runtime_database_path(project_root, "internet_downloads.sqlite3")
    with transaction(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(scientific_source_catalog)")}
        if "reference_record_count" not in columns:
            connection.execute("ALTER TABLE scientific_source_catalog ADD COLUMN reference_record_count INTEGER NOT NULL DEFAULT 0")
        if "data_scope" not in columns:
            connection.execute("ALTER TABLE scientific_source_catalog ADD COLUMN data_scope TEXT NOT NULL DEFAULT 'connector_only'")
        connection.execute(
            """INSERT INTO scientific_source_catalog(source_key,provider,resource_type,official_host,access_method,licence_profile,refresh_cadence,local_status,last_checked_at_utc,records_available,notes,metadata_json,reference_record_count,data_scope)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source_key) DO UPDATE SET local_status=excluded.local_status,last_checked_at_utc=excluded.last_checked_at_utc,records_available=excluded.records_available,metadata_json=excluded.metadata_json,reference_record_count=excluded.reference_record_count,data_scope=excluded.data_scope""",
            ("uci_wdbc","UCI Machine Learning Repository","biomedical_tabular_reference","archive.ics.uci.edu","bundled_sklearn_loader","CC-BY-4.0","static","imported_reference",utc_now(),records,"Real public reference dataset; not model-release validation.",json.dumps({"dataset":"Breast Cancer Wisconsin Diagnostic","checksum":checksum,"real_public_reference":True}),records,"public_reference_dataset"),
        )
        event_id = hashlib.sha256(b"uci_wdbc|bundled_reference_import").hexdigest()[:28]
        connection.execute(
            """INSERT INTO source_sync_events(event_id,source_key,event_type,status,message,records_seen,records_imported,checksum,metadata_json,created_at_utc)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(event_id) DO UPDATE SET status=excluded.status,message=excluded.message,records_seen=excluded.records_seen,records_imported=excluded.records_imported,checksum=excluded.checksum,metadata_json=excluded.metadata_json""",
            (event_id,"uci_wdbc","bundled_reference_import","completed","Licensed public reference dataset loaded from the installed scikit-learn package.",records,records,checksum,json.dumps({"scope":"public_reference_dataset","scientific_release_eligible":False}),utc_now()),
        )

def _seed_knowledge(project_root: Path, records: list[dict[str, Any]]) -> None:
    path = runtime_database_path(project_root, "knowledge.sqlite3")
    with transaction(path) as connection:
        connection.execute("""
        CREATE TABLE IF NOT EXISTS public_reference_records (
            reference_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            record_type TEXT NOT NULL,
            stable_id TEXT NOT NULL,
            symbol TEXT,
            label TEXT NOT NULL,
            organism TEXT,
            official_url TEXT NOT NULL,
            verification_level TEXT NOT NULL,
            training_eligible INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at_utc TEXT NOT NULL,
            UNIQUE(provider,record_type,stable_id)
        )
        """)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_public_reference_type ON public_reference_records(provider,record_type)")
        now = utc_now()
        for row in records:
            reference_id = hashlib.sha256(f"{row['provider']}|{row['record_type']}|{row['stable_id']}".encode()).hexdigest()[:28]
            connection.execute(
                """
                INSERT INTO public_reference_records(
                    reference_id,provider,record_type,stable_id,symbol,label,organism,
                    official_url,verification_level,training_eligible,metadata_json,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(reference_id) DO UPDATE SET
                    label=excluded.label,official_url=excluded.official_url,
                    verification_level=excluded.verification_level,metadata_json=excluded.metadata_json
                """,
                (reference_id,row["provider"],row["record_type"],row["stable_id"],row["symbol"],row["label"],row["organism"],row["official_url"],row["verification_level"],0,"{}",now),
            )


def _update_provider_counts(project_root: Path, records: list[dict[str, Any]]) -> None:
    path = runtime_database_path(project_root, "internet_downloads.sqlite3")
    counts = {
        "uniprot": sum(row["provider"] == "UniProt" for row in records),
        "rcsb": sum(row["provider"] == "RCSB PDB" for row in records),
        "ncbi": sum(row["provider"] == "NCBI Gene" for row in records),
    }
    with transaction(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(scientific_source_catalog)")}
        if "reference_record_count" not in columns:
            connection.execute("ALTER TABLE scientific_source_catalog ADD COLUMN reference_record_count INTEGER NOT NULL DEFAULT 0")
        if "data_scope" not in columns:
            connection.execute("ALTER TABLE scientific_source_catalog ADD COLUMN data_scope TEXT NOT NULL DEFAULT 'connector_only'")
        rows = connection.execute("SELECT source_key,provider FROM scientific_source_catalog").fetchall()
        for source_key, provider in rows:
            lowered = f"{source_key} {provider}".lower()
            count = 0
            if "uniprot" in lowered:
                count = counts["uniprot"]
            elif "rcsb" in lowered or "pdb" in lowered:
                count = counts["rcsb"]
            elif "ncbi" in lowered or "entrez" in lowered:
                count = counts["ncbi"]
            elif "uci" in lowered:
                continue
            connection.execute(
                "UPDATE scientific_source_catalog SET reference_record_count=?,data_scope=? WHERE source_key=?",
                (count, "verified_identifier_reference" if count else "connector_only", source_key),
            )
