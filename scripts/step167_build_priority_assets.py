from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.priority_v167 import ensure_step167_assets, priority_matrix


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--root',default='.'); args=parser.parse_args(); root=Path(args.root).resolve(); reports=root/'reports'; reports.mkdir(exist_ok=True)
    written=ensure_step167_assets(root); matrix=priority_matrix(root); matrix.to_csv(reports/'step167_priority_module_matrix.csv',index=False)
    payload={'schema':'biointel.step167.asset-build.v1','status':'passed','assets_written':len(written),'modules':len(matrix),'software_10of10':int((matrix.software_score==10).sum()),'native_depth_10of10':int((matrix.native_research_depth_score==10).sum())}
    (reports/'step167_asset_build.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8'); print(json.dumps(payload,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
