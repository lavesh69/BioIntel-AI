from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.curation import curate_activity_dataset
from biointel.training.dataset_bias import analyze_dataset_bias


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate a real DTI activity CSV.")
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--smiles-column", default="canonical_smiles")
    parser.add_argument("--sequence-column", default="protein_sequence")
    parser.add_argument("--value-column", default="standard_value")
    parser.add_argument("--unit-column", default="standard_units")
    parser.add_argument("--relation-column", default="standard_relation")
    parser.add_argument("--activity-type-column", default="activity_type")
    parser.add_argument("--active-threshold", type=float, default=6.0)
    parser.add_argument("--source-database", default="local_import")
    parser.add_argument("--keep-duplicates", action="store_true")
    args = parser.parse_args()

    source = pd.read_csv(args.input_csv, low_memory=False)
    curated, errors, summary = curate_activity_dataset(
        source,
        smiles_column=args.smiles_column,
        sequence_column=args.sequence_column,
        value_column=args.value_column,
        unit_column=args.unit_column,
        relation_column=args.relation_column,
        activity_type_column=args.activity_type_column,
        active_threshold=args.active_threshold,
        aggregate_duplicates=not args.keep_duplicates,
        source_database=args.source_database,
    )
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    curated.to_csv(args.output_csv, index=False)
    errors_path = args.output_csv.with_name(args.output_csv.stem + "_errors.csv")
    errors.to_csv(errors_path, index=False)
    bias = analyze_dataset_bias(curated)
    report_path = args.output_csv.with_name(args.output_csv.stem + "_quality.json")
    report_path.write_text(
        json.dumps(
            {"summary": asdict(summary), "bias": asdict(bias)},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"Curated rows: {len(curated):,}")
    print(f"Rejected rows: {len(errors):,}")
    print(f"Output: {args.output_csv.resolve()}")
    print(f"Quality report: {report_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
