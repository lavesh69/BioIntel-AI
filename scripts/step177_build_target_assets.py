from __future__ import annotations
import argparse,csv,json
from pathlib import Path
from biointel.target_modules_v177 import TARGET_MODULES,TARGET_PROFILES,required_engines,required_references

def false_manifest(asset_id:str,kind:str)->dict:
    base={'schema':f'biointel.step177.{kind}-qualification.v1','asset_id':asset_id,'present':False}
    flags={'reference':['release_pinned','checksum_verified','licence_accepted','schema_validated','scientific_reviewed'],'model':['weights_hash_verified','provenance_recorded','licence_accepted','benchmark_passed','leakage_audit_passed','calibration_passed','subgroup_analysis_passed','external_site_passed'],'cohort':['use_permission_recorded','schema_validated','split_locked','leakage_audit_passed','subgroup_coverage_reviewed','independent','external_site_passed']}
    base.update({f:False for f in flags[kind]});return base

def main(root:Path)->None:
    out=root/'data/step177';(out/'target_modules').mkdir(parents=True,exist_ok=True)
    index=[]
    for key in TARGET_MODULES:
        p=TARGET_PROFILES[key];folder=out/'target_modules'/key;folder.mkdir(parents=True,exist_ok=True)
        contract={'schema':'biointel.step177.21-module-contract.v1','module_key':key,'module_title':p.title,'workflow':list(p.workflow),'quality_gates':list(p.quality_gates),'required_outputs':list(p.required_outputs),'boundary':p.boundary,'model_assets':list(p.model_assets),'cohort_assets':list(p.cohort_assets)}
        (folder/'qualification_contract.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
        required_engines(key).to_csv(folder/'engine_plan.csv',index=False);required_references(key).to_csv(folder/'reference_plan.csv',index=False)
        for kind,ids in [('model',p.model_assets),('cohort',p.cohort_assets)]:
            kdir=folder/f'{kind}_manifest_templates';kdir.mkdir(exist_ok=True)
            for aid in ids:(kdir/f'{aid}.json').write_text(json.dumps(false_manifest(aid,kind),indent=2),encoding='utf-8')
        evidence={'schema':'biointel.step177.external-evidence.v1','module_key':key,'wet_lab_or_orthogonal_complete':False,'expert_signoff_complete':False,'formal_release_review_complete':False,'rollback_plan_tested':False,'monitoring_plan_approved':False}
        (folder/'external_evidence_manifest_template.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        index.append({'module_key':key,'module_title':p.title,'folder':str(folder.relative_to(root))})
    (out/'asset_index.json').write_text(json.dumps({'schema':'biointel.step177.asset-index.v1','modules':index},indent=2),encoding='utf-8')
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);a=ap.parse_args();main(a.root.resolve())
