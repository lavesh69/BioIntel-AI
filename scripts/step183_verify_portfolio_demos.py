from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.portfolio_demo_v183 import portfolio_demo_detail_matrix, portfolio_demo_matrix

summary = portfolio_demo_matrix(ROOT)
details = portfolio_demo_detail_matrix(ROOT)
reports = ROOT / "reports" / "step183"
reports.mkdir(parents=True, exist_ok=True)
summary.to_csv(reports / "step183_80_module_demo_ratings.csv", index=False)
details.to_csv(reports / "step183_80_module_demo_details.csv", index=False)
(reports / "step183_80_module_demo_ratings.json").write_text(summary.to_json(orient="records", indent=2), encoding="utf-8")
(reports / "step183_80_module_demo_details.json").write_text(details.to_json(orient="records", indent=2), encoding="utf-8")
ready = int(summary.demo_ready.sum())
release = int(summary.controlled_release_eligible.sum())
real_changed = int(summary.real_external_rating_changed.sum())
print(f"STEP183_DEMO_READY={ready}/{len(summary)}; REAL_RATING_CHANGED={real_changed}; CONTROLLED_RELEASE={release}/{len(summary)}")
if ready != 80 or release != 0 or real_changed != 0:
    raise SystemExit(1)
