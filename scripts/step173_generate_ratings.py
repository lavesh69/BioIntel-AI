from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from biointel.final_v173 import Step173Registry

registry = Step173Registry(ROOT)
matrix = registry.refresh()
ratings = ROOT / "reports" / "step173_final_all_module_ratings.csv"
matrix.to_csv(ratings, index=False)
summary = {
    "schema": "biointel.step173.rating-summary.v1",
    "version": "14.5.0",
    "modules": len(matrix),
    "internal_software_10of10": int((matrix["internal_software_rating"] == 10.0).sum()),
    "native_depth_10of10": int((matrix["native_research_depth_rating"] == 10.0).sum()),
    "framework_10of10": int((matrix["qualification_framework_rating"] == 10.0).sum()),
    "controlled_release_eligible": int(matrix["controlled_release_eligible"].sum()),
    "average_actual_practical_readiness": round(float(matrix["actual_practical_readiness_rating"].mean()), 2),
    "weakest_modules": matrix.head(15)[["module_key", "module_title", "actual_practical_readiness_rating", "remaining_blockers"]].to_dict(orient="records"),
    "strongest_modules": matrix.tail(15).sort_values("actual_practical_readiness_rating", ascending=False)[["module_key", "module_title", "actual_practical_readiness_rating", "readiness_stage"]].to_dict(orient="records"),
    "ratings_file": str(ratings),
}
out = ROOT / "reports" / "step173_rating_summary.json"
out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
