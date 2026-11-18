from __future__ import annotations

from pathlib import Path

import pandas as pd

DRUGS = [
    ("D01", "CCO"),
    ("D02", "CC(=O)O"),
    ("D03", "CCN"),
    ("D04", "c1ccccc1"),
    ("D05", "CCOC(=O)C"),
    ("D06", "CC(C)O"),
    ("D07", "CC(=O)NC1=CC=CC=C1"),
    ("D08", "CC(=O)OC1=CC=CC=C1C(=O)O"),
    ("D09", "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"),
    ("D10", "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"),
    ("D11", "COC1=CC=CC=C1O"),
    ("D12", "C1CCCCC1"),
]

TARGETS = [
    ("T01", "MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE"),
    ("T02", "MALWMRLLPLLALLALWGPGPGAGGQGAPGAAAAAAGGPGAG"),
    ("T03", "MSTNPKPQRKTKRNTNRRPQDVKFPGGGQIVGGVYLLPRRG"),
    ("T04", "MARGKKIGYSAPRQTKEAIEKLAEAGVEVEVKPANDPEVLE"),
    ("T05", "MNIFEMLRIDEGLRLKIYKDTEGYYTIGIGHLLTKSPSLNAA"),
    ("T06", "MKKTAIAIAVALAGFATVAQAAPVAAAPAPAPVVAEAKKAA"),
    ("T07", "MAEKKKIGMTRSAEQLKAAEAGVEVEVKPANDPEVLELVE"),
    ("T08", "MSTAGKVIKCKAAVLWGKVGAHAGEYGAEALERMFLSFPTT"),
]


def build_demo_dataset() -> pd.DataFrame:
    """Create deterministic synthetic pairs for software demonstration only."""

    rows: list[dict[str, object]] = []
    for drug_index, (drug_id, smiles) in enumerate(DRUGS):
        for target_index, (target_id, sequence) in enumerate(TARGETS):
            score = (drug_index * 5 + target_index * 3 + drug_index * target_index) % 11
            label = int(score <= 4)
            p_activity = round(4.7 + 0.28 * score + 0.03 * (drug_index % 3), 3)
            rows.append(
                {
                    "drug_id": drug_id,
                    "canonical_smiles": smiles,
                    "target_id": target_id,
                    "protein_sequence": sequence,
                    "activity_type": "SYNTHETIC_SCORE",
                    "p_activity": p_activity,
                    "label": label,
                    "source": "Synthetic demonstration data—not scientific evidence",
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "data" / "examples" / "synthetic_dti_demo.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    dataframe = build_demo_dataset()
    dataframe.to_csv(output, index=False)
    print(f"Created {output} with {len(dataframe)} synthetic rows.")


if __name__ == "__main__":
    main()
