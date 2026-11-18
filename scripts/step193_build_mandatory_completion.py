from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.mandatory_completion_v193 import build_all, rating_matrix

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument('--root',default='.'); args=p.parse_args(); root=Path(args.root).resolve()
 summary=build_all(root)
 frame=rating_matrix(root)
 frame.to_csv(root/'STEP193_80_MODULE_MANDATORY_COMPLETION_RATINGS.csv',index=False)
 print(json.dumps(summary,indent=2)); return 0 if summary['modules_qualified']==80 else 1
if __name__=='__main__': raise SystemExit(main())
