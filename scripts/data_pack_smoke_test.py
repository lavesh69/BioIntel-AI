from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.data_packs import (  # noqa: E402
    data_library_summary,
)
from biointel.dti.predictor import predict_dti_pair  # noqa: E402
from biointel.training.model_artifact import (  # noqa: E402
    load_model_artifact,
)


def main() -> None:
    foundation = pd.read_csv(ROOT / "data" / "packs" / "synthetic_foundation_dti_v2.csv")
    extended = pd.read_csv(ROOT / "data" / "packs" / "synthetic_extended_dti_v2.csv")
    ultra = pd.read_csv(ROOT / "data" / "packs" / "synthetic_ultra_dti_v3.csv")
    double_ultra = pd.read_csv(ROOT / "data" / "packs" / "synthetic_double_ultra_dti_v4.csv")
    five_x = pd.read_csv(ROOT / "data" / "packs" / "synthetic_5x_ultra_dti_v5.csv")
    assert len(foundation) == 1920
    assert len(extended) == 5760
    assert foundation["drug_id"].nunique() == 120
    assert extended["drug_id"].nunique() == 240
    assert extended["target_id"].nunique() == 24
    assert len(ultra) == 16000
    assert ultra["drug_id"].nunique() == 400
    assert ultra["target_id"].nunique() == 40
    assert len(double_ultra) == 32000
    assert double_ultra["drug_id"].nunique() == 640
    assert double_ultra["target_id"].nunique() == 50
    assert len(five_x) == 160000
    assert five_x["drug_id"].nunique() == 1000
    assert five_x["target_id"].nunique() == 160
    assert 0.49 <= float(five_x["label"].mean()) <= 0.51
    assert 0.45 <= float(extended["label"].mean()) <= 0.55

    summary = data_library_summary(ROOT)
    assert len(summary["manifest"]["packs"]) == 9
    best = summary["benchmark"]["best_models"]
    assert "classification" in best
    assert "regression" in best

    row = extended.iloc[0]
    for task in ("classification", "regression"):
        filename = best[task]["filename"]
        artifact = load_model_artifact(
            ROOT / "models" / filename,
            trusted_root=ROOT / "models",
        )
        prediction = predict_dti_pair(
            artifact,
            str(row["canonical_smiles"]),
            str(row["protein_sequence"]),
        )
        assert prediction.task_type == task

    assert len(summary["benchmark"]["ranking"]) >= 21
    print("BioIntel Step 24 Scientific Performance data-pack smoke test passed")


if __name__ == "__main__":
    main()
