from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from biointel.models_v171 import Step171Registry, build_step171_assets, qualification_matrix

matrix = build_step171_assets(ROOT)
registry = Step171Registry(ROOT, rebuild=True)
(ROOT / "reports").mkdir(exist_ok=True)
matrix = qualification_matrix(ROOT)
matrix.to_csv(ROOT / "reports" / "step171_model_benchmark_matrix.csv", index=False)
print(matrix.to_string(index=False))
print(registry.status())
