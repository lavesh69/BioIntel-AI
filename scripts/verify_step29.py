from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel import __version__
from biointel.bioinformatics_capabilities import capabilities_dict
from biointel.genomics.annotations import annotation_summary, parse_gff
from biointel.genomics.fastq import fastq_qc, parse_fastq
from biointel.genomics.phylogeny import upgma_newick
from biointel.genomics.variants import parse_vcf, variant_summary
from biointel.sequence.parser import parse_sequences_text
from biointel.training.model_artifact import load_model_artifact
from biointel.ui.navigation import PAGE_CATALOG


def main():
    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert len(PAGE_CATALOG) >= 71
    demo = ROOT / "data" / "bioinformatics_demo"
    required = {
        "demo_reads.fastq",
        "demo_variants.vcf",
        "demo_annotations.gff3",
        "demo_assembly.fasta",
        "demo_expression_counts.csv",
        "demo_structure.pdb",
        "demo_qpcr.csv",
        "demo_enzyme_kinetics.csv",
        "demo_bioprocess.csv",
        "demo_taxonomy.csv",
        "demo_alignment.fasta",
    }
    assert required <= {p.name for p in demo.iterdir()}
    qc = fastq_qc(parse_fastq((demo / "demo_reads.fastq").read_text()))
    assert qc.reads == 20000
    variants = variant_summary(parse_vcf((demo / "demo_variants.vcf").read_text()))
    assert variants.variants == 5000
    annotations = annotation_summary(parse_gff((demo / "demo_annotations.gff3").read_text()))
    assert annotations.genes == 2000
    records = parse_sequences_text((demo / "demo_alignment.fasta").read_text())
    assert upgma_newick({r.header: r.sequence for r in records}).endswith(";")
    models = sorted((ROOT / "models").glob("*.joblib"))
    assert len(models) >= 23
    for model in models:
        load_model_artifact(model, trusted_root=ROOT / "models")
    with sqlite3.connect(ROOT / "reports" / "datasets.sqlite3") as connection:
        dataset_count = int(connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0])
    assert dataset_count >= 51
    payload = {
        "version": __version__,
        "screens": len(PAGE_CATALOG),
        "models": len(models),
        "datasets": dataset_count,
        "fastq_reads": qc.reads,
        "variants": variants.variants,
        "genes": annotations.genes,
        "capabilities": capabilities_dict(),
    }
    output = ROOT / "reports" / "generated" / "step29_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
