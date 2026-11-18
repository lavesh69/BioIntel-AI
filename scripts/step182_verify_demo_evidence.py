from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.external_demo_v182 import demo_detail_matrix, demo_qualification_matrix

summary = demo_qualification_matrix(ROOT)
details = demo_detail_matrix(ROOT)
reports = ROOT / "reports" / "step182"
reports.mkdir(parents=True, exist_ok=True)
summary.to_csv(reports / "step182_demo_module_summary.csv", index=False)
details.to_csv(reports / "step182_demo_pack_details.csv", index=False)
(reports / "step182_demo_module_summary.json").write_text(summary.to_json(orient="records", indent=2), encoding="utf-8")
(reports / "step182_demo_pack_details.json").write_text(details.to_json(orient="records", indent=2), encoding="utf-8")
ready = int(details.demo_ready.sum())
print(f"STEP182_DEMO_PACKS_READY={ready}/{len(details)}; REAL_EVIDENCE=0/25; CONTROLLED_RELEASE=NO")
if ready != len(details):
    raise SystemExit(1)
