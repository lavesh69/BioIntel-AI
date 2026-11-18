from __future__ import annotations
import argparse, json
from pathlib import Path
from biointel.priority_v166 import ensure_step166_assets, six_module_matrix

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument('--root', default='.'); args = parser.parse_args()
    root = Path(args.root).resolve(); reports = root / 'reports'; reports.mkdir(exist_ok=True)
    written = ensure_step166_assets(root); matrix = six_module_matrix(root)
    matrix.to_csv(reports / 'step166_six_module_matrix.csv', index=False)
    payload = {'schema':'biointel.step166.asset-build.v1','status':'passed','assets_written':len(written),'modules':len(matrix),'software_10of10':int((matrix.software_score==10).sum()),'native_depth_10of10':int((matrix.native_research_depth_score==10).sum())}
    (reports / 'step166_asset_build.json').write_text(json.dumps(payload, indent=2) + '\n')
    print(json.dumps(payload, indent=2)); return 0
if __name__ == '__main__': raise SystemExit(main())
