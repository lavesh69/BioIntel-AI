from __future__ import annotations
import argparse, json
from pathlib import Path
from biointel.priority_v165 import ensure_step165_assets, priority_matrix

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--root',default='.')
    args=parser.parse_args(); root=Path(args.root).resolve()
    written=ensure_step165_assets(root)
    matrix=priority_matrix(root)
    reports=root/'reports'; reports.mkdir(exist_ok=True)
    matrix.to_csv(reports/'step165_priority_module_matrix.csv',index=False)
    payload={'schema':'biointel.step165.asset-build.v1','status':'passed','assets_written':len(written),'modules':len(matrix),'software_10of10':int((matrix.software_score==10).sum())}
    (reports/'step165_asset_build.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(payload,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
