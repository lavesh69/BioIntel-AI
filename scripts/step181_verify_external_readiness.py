from __future__ import annotations

import argparse
import json
from pathlib import Path
import py_compile
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.external_readiness_v181 import PROFILES, TARGET_MODULES, evidence_detail_matrix, qualification_matrix


def main(root: Path) -> int:
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    summary = qualification_matrix(root)
    details = evidence_detail_matrix(root)
    summary.to_csv(reports / "step181_external_readiness_summary.csv", index=False)
    details.to_csv(reports / "step181_external_readiness_details.csv", index=False)
    (reports / "step181_external_readiness_summary.json").write_text(
        json.dumps(summary.to_dict("records"), indent=2, default=str) + "\n", encoding="utf-8"
    )
    (reports / "step181_external_readiness_details.json").write_text(
        json.dumps(details.to_dict("records"), indent=2, default=str) + "\n", encoding="utf-8"
    )

    compile_errors: list[str] = []
    paths = list((root / "src/biointel/external_readiness_v181").glob("*.py")) + [
        root / "pages/251_Step181_External_Scientific_Evidence_Center.py",
    ] + [root / PROFILES[key].page for key in TARGET_MODULES]
    for path in paths:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            compile_errors.append(f"{path}:{exc}")

    page_hooks = []
    for key in TARGET_MODULES:
        page = root / PROFILES[key].page
        text = page.read_text(encoding="utf-8-sig") if page.is_file() else ""
        page_hooks.append("render_step181_external_readiness" in text and key in text)

    workflow_complete = (
        len(summary) == 5
        and summary.weakness_remediation_workflow_rating.eq(10.0).all()
        and len(details) == 25
        and all(page_hooks)
        and not compile_errors
    )
    controlled = int(summary.controlled_release_eligible.sum())
    print(summary.to_string(index=False))
    print(f"STEP181_WORKFLOW_10OF10={workflow_complete}; REAL_EVIDENCE_COMPLETE={controlled}/5; COMPILE_ERRORS={len(compile_errors)}")
    if compile_errors:
        print("\n".join(compile_errors))
    return 0 if workflow_complete else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    raise SystemExit(main(args.root.resolve()))
