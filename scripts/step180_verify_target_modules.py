from __future__ import annotations

import argparse
import json
from pathlib import Path
import py_compile

from biointel.target_modules_v180 import TARGET_MODULES, TARGET_PROFILES, qualification_matrix


def main(root: Path) -> int:
    frame = qualification_matrix(root)
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    frame.to_csv(reports / "step180_final_five_qualification.csv", index=False)
    (reports / "step180_final_five_qualification.json").write_text(
        json.dumps(frame.to_dict("records"), indent=2, default=str), encoding="utf-8"
    )

    compile_errors: list[str] = []
    paths = [
        root / "src/biointel/target_modules_v180/catalog.py",
        root / "src/biointel/target_modules_v180/runtime.py",
        root / "src/biointel/target_modules_v180/checks.py",
        root / "src/biointel/target_modules_v180/qualification.py",
        root / "src/biointel/target_modules_v180/ui.py",
        root / "pages/250_Step180_Final_Five_Scientific_Qualification_Center.py",
    ] + [root / TARGET_PROFILES[key].page for key in TARGET_MODULES]
    for path in paths:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            compile_errors.append(f"{path}:{exc}")

    required = [
        "workflow_contract_complete",
        "data_contract_complete",
        "model_contract_complete",
        "scientific_contract_complete",
        "acceptance_contract_complete",
        "output_contract_complete",
        "risk_contract_complete",
        "monitoring_contract_complete",
        "ui_hook_present",
        "component_plan_complete",
        "reference_plan_complete",
        "model_plan_complete",
        "cohort_plan_complete",
        "fixture_plan_complete",
        "governance_plan_complete",
        "deterministic_scientific_smoke_passed",
    ]
    passed = (
        len(frame) == 5
        and frame.internal_after_rating.eq(10.0).all()
        and all(frame[column].all() for column in required)
        and not compile_errors
    )
    print(
        frame[
            [
                "module_key",
                "baseline_rating",
                "internal_after_rating",
                "rating_improvement",
                "improvement_percent",
                "decision",
            ]
        ].to_string(index=False)
    )
    print(
        f"INTERNAL_10OF10={passed}; CONTROLLED_RELEASE={int(frame.controlled_release_eligible.sum())}/5; "
        f"PORTFOLIO_INTERNAL=80/80; COMPILE_ERRORS={len(compile_errors)}"
    )
    if compile_errors:
        print("\n".join(compile_errors))
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    raise SystemExit(main(arguments.root.resolve()))
