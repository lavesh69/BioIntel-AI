from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.real_evidence import import_curated_evidence, result_dict
from biointel.integrations.bindingdb import bindingdb_to_activity_frame
from biointel.integrations.chembl_evidence import download_activity_evidence
from biointel.integrations.pubchem_bioassay import pubchem_activity_export_to_frame


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="BioIntel AI Step 25 real-evidence importer")
    sub = command.add_subparsers(dest="provider", required=True)
    for provider in ("generic", "bindingdb", "pubchem"):
        item = sub.add_parser(provider)
        item.add_argument("path", type=Path)
        item.add_argument("--release", default="user_import")
        item.add_argument("--threshold", type=float, default=6.0)
    chembl = sub.add_parser("chembl")
    chembl.add_argument("--target", default=None)
    chembl.add_argument("--molecule", default=None)
    chembl.add_argument("--rows", type=int, default=250)
    chembl.add_argument("--release", default="live_api")
    chembl.add_argument("--threshold", type=float, default=6.0)
    return command


def main() -> None:
    args = parser().parse_args()
    if args.provider == "chembl":
        frame = download_activity_evidence(
            target_chembl_id=args.target, molecule_chembl_id=args.molecule, maximum_rows=args.rows
        )
        provider = "chembl"
        metadata = {"target": args.target, "molecule": args.molecule, "live_api": True}
        homepage = "https://www.ebi.ac.uk/chembl/"
    else:
        path = args.path.resolve()
        if args.provider == "bindingdb":
            frame = bindingdb_to_activity_frame(path)
            provider = "bindingdb"
        else:
            frame = pd.read_csv(
                path, sep="\t" if path.suffix.lower() in {".tsv", ".txt"} else ",", low_memory=False
            )
            provider = "pubchem_bioassay" if args.provider == "pubchem" else "generic"
            if args.provider == "pubchem":
                frame = pubchem_activity_export_to_frame(frame)
        metadata = {"input_path": str(path)}
        homepage = None
    result = import_curated_evidence(
        frame,
        provider=provider,
        source_release=args.release,
        registry_path=ROOT / "reports" / "evidence.sqlite3",
        dataset_registry_path=ROOT / "reports" / "datasets.sqlite3",
        output_directory=ROOT / "data" / "real_evidence",
        source_homepage=homepage,
        active_threshold=args.threshold,
        metadata=metadata,
    )
    output = ROOT / "reports" / "generated" / "step25_last_evidence_import.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result_dict(result), indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print(json.dumps(result_dict(result), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
