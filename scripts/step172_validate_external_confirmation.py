from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.external_v172 import ALL_MODULES, PROFILES, Step172Registry, build_step172_assets, profile_matrix

assets=build_step172_assets(ROOT)
registry=Step172Registry(ROOT)
matrix=registry.matrix(refresh=True)
checks={
 'module_profiles_80':len(PROFILES)==80==len(ALL_MODULES),
 'profile_framework_10of10':bool((profile_matrix()['software_framework_score']==10.0).all()),
 'assets_at_least_800':len(assets)>=801,
 'matrix_80':len(matrix)==80,
 'fail_closed_without_external_evidence':bool((~matrix['release_eligible']).all()),
 'no_external_outcomes_inferred':bool((matrix['decision']=='research-only-fail-closed').all()),
 'registry_integrity':registry.status()['database_integrity']=='ok',
 'registry_fk_clean':registry.status()['foreign_key_violations']==0,
}
report={'schema':'biointel.step172.validation.v1','status':'passed' if all(checks.values()) else 'failed','version':'14.4.0','checks':checks,'modules':80,'assets':len(assets),'software_framework_score':10.0,'actual_release_eligible_modules':int(matrix['release_eligible'].sum()),'external_evidence_fabricated':False}
out=ROOT/'reports'/'step172_validation.json'; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2)); raise SystemExit(0 if report['status']=='passed' else 1)
