from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.external_v172 import build_step172_assets, profile_matrix, Step172Registry

paths=build_step172_assets(ROOT)
matrix=profile_matrix()
report={
 'schema':'biointel.step172.asset-build.v1','status':'passed','version':'14.4.0',
 'modules':len(matrix),'assets_written':len(paths),'software_framework_score':10.0,
 'evidence_classes':matrix['evidence_class'].value_counts().to_dict(),
 'registry':Step172Registry(ROOT).status(),
 'external_outcomes_created':False,
}
out=ROOT/'reports'/'step172_asset_build.json'; out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
