from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path: sys.path.insert(0, str(SRC))
from biointel.priority_v168 import ensure_step168_assets, ensure_step168_database, priority_matrix, universal_evidence_matrix
from biointel.scientific_depth.profiles import MODULE_PROFILES

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--root',default='.'); args=parser.parse_args(); root=Path(args.root).resolve()
    reports=root/'reports'; reports.mkdir(exist_ok=True)
    written=ensure_step168_assets(root)
    db=ensure_step168_database(root,[(k,v.title) for k,v in MODULE_PROFILES.items()])
    matrix=priority_matrix(root); universal=universal_evidence_matrix()
    matrix.to_csv(reports/'step168_priority_module_matrix.csv',index=False)
    universal.to_csv(reports/'step168_universal_evidence_matrix.csv',index=False)
    payload={'schema':'biointel.step168.asset-build.v1','status':'passed','focused_modules':len(matrix),'all_modules':len(universal),'json_assets_written':len(written),'evidence_database':str(db.relative_to(root)),'focused_software_10of10':int((matrix.software_score==10).sum()),'universal_framework_10of10':int((universal.framework_score==10).sum())}
    (reports/'step168_asset_build.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
