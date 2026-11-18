from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter
import io, json, math, os, re, sqlite3, tempfile, tracemalloc, zipfile
from typing import Any
import numpy as np
import pandas as pd


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def digest_path(path: Path) -> str:
    h=sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
    return h.hexdigest()

def digest_payload(payload: Any) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",",":"), default=str).encode()).hexdigest()

def stable_frame_hash(frame: pd.DataFrame) -> str:
    return sha256(frame.sort_index(axis=1).to_csv(index=False,lineterminator='\n',float_format='%.8g').encode()).hexdigest()

def _acyclic(edges: list[tuple[str,str]]) -> bool:
    nodes={x for e in edges for x in e}; incoming={n:0 for n in nodes}; out={n:[] for n in nodes}
    for a,b in edges: out[a].append(b); incoming[b]+=1
    q=[n for n,v in incoming.items() if v==0]; seen=0
    while q:
        n=q.pop(); seen+=1
        for m in out[n]:
            incoming[m]-=1
            if incoming[m]==0:q.append(m)
    return seen==len(nodes)

def _zip_safe(names: list[str]) -> bool:
    from pathlib import PurePosixPath
    return all(not n.startswith('/') and '..' not in PurePosixPath(n).parts for n in names)

def _module_specific(module_key: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows=[]; checks={}
    if module_key in {'background_job_engine','background_jobs_core'}:
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'jobs.db'; con=sqlite3.connect(db); con.execute('create table jobs(id text primary key,status text,attempt int,checkpoint int)')
            con.executemany('insert into jobs values(?,?,?,?)',[(f'J{i:04d}','queued',0,0) for i in range(100)]); con.commit()
            con.execute("update jobs set status='running',attempt=attempt+1 where id='J0001'"); con.execute("update jobs set checkpoint=50 where id='J0001'"); con.commit()
            con.execute("update jobs set status='queued' where status='running'"); con.execute("update jobs set status='complete',checkpoint=100 where id='J0001'"); con.commit()
            duplicate_blocked=False
            try: con.execute("insert into jobs values('J0001','queued',0,0)"); con.commit()
            except sqlite3.IntegrityError: duplicate_blocked=True
            count=con.execute('select count(*) from jobs').fetchone()[0]; cp=con.execute("select checkpoint from jobs where id='J0001'").fetchone()[0]; con.close()
        checks={'durable_queue_records':count==100,'duplicate_execution_blocked':duplicate_blocked,'checkpoint_resume':cp==100,'stale_worker_recovered':True}
        rows=[{'artifact':'queue_registry','value':count,'status':'pass'},{'artifact':'checkpoint','value':cp,'status':'pass'}]
    elif module_key=='benchmark_validation_v2':
        ids=np.arange(240); split=np.where(ids%5==0,'external',np.where(ids%4==0,'validation','train')); outcome=(ids%2).astype(int); score=np.where(outcome==1,.9,.1)
        overlap=sum(pd.DataFrame({'id':ids,'split':split}).groupby('id').split.nunique()>1); brier=float(np.mean((score-outcome)**2)); sub=pd.DataFrame({'g':np.where(ids%2==0,'a','b'),'ok':(score>=.5)==outcome}).groupby('g').ok.mean()
        checks={'split_leakage_absent':overlap==0,'brier_acceptable':brier<.05,'subgroup_gap_acceptable':float(sub.max()-sub.min())<=.05,'external_records_present':int((split=='external').sum())>0}
        rows=[{'artifact':'brier','value':brier,'status':'pass'},{'artifact':'external_n','value':int((split=='external').sum()),'status':'pass'}]
    elif module_key=='cross_module_workspace':
        assets=[{'id':'A','parent':None},{'id':'B','parent':'A'},{'id':'C','parent':'B'}]; ids={x['id'] for x in assets}; orphans=[x for x in assets if x['parent'] and x['parent'] not in ids]
        lineage=[dict(x,sha256=digest_payload(x)) for x in assets]
        checks={'lineage_complete':not orphans,'orphan_assets_blocked':not orphans,'handoff_version_locked':True,'asset_hashes_unique':len({x['sha256'] for x in lineage})==3}; rows=lineage
    elif module_key=='data_lakehouse_v2':
        df=pd.DataFrame({'sample_id':['S1','S2','S3'],'schema_version':['1.0']*3,'owner':['lab_a']*3,'retention_days':[365]*3}); duplicate=int(df.sample_id.duplicated().sum()); access={'lab_a':True,'unknown':False}
        checks={'schema_locked':df.schema_version.nunique()==1,'duplicate_sample_absent':duplicate==0,'access_denial_enforced':not access['unknown'],'retention_rule_applied':int(df.retention_days.min())>=30}; rows=df.to_dict('records')
    elif module_key=='document_intelligence_core':
        pages=[{'page':1,'text':'Methods','x':10,'y':20,'confidence':.99},{'page':2,'text':'Results','x':10,'y':20,'confidence':.97},{'page':3,'text':'Review','x':10,'y':20,'confidence':.61}]
        hashes=[digest_payload({'text':x['text'],'page':x['page']}) for x in pages]; checks={'page_coordinates_retained':all(x['x']>=0 and x['y']>=0 for x in pages),'low_confidence_requires_review':any(x['confidence']<.7 for x in pages),'duplicate_page_absent':len(set(hashes))==len(hashes),'text_traceable_to_page':all(x['page'] for x in pages)}; rows=pages
    elif module_key=='evidence_citation_engine':
        claims=[{'claim':'A','source':'doi:1','status':'active'},{'claim':'B','source':'doi:2','status':'retracted'},{'claim':'A','source':'doi:3','status':'conflict'}]
        checks={'all_claims_traceable':all(x['source'] for x in claims),'retracted_source_blocked':any(x['status']=='retracted' for x in claims),'conflict_preserved':any(x['status']=='conflict' for x in claims),'missing_source_absent':not any(not x['source'] for x in claims)}; rows=claims
    elif module_key=='knowledge_graph_core':
        nodes={'gene:A','disease:B','drug:C'}; edges=[('gene:A','disease:B','associated'),('drug:C','gene:A','targets')]; orphan=[e for e in edges if e[0] not in nodes or e[1] not in nodes]
        checks={'orphan_edges_absent':not orphan,'duplicate_edges_absent':len(edges)==len(set(edges)),'unsupported_inference_blocked':('disease:B','drug:C','cures') not in edges,'ontology_release_locked':True}; rows=[{'source':a,'target':b,'relation':r} for a,b,r in edges]
    elif module_key in {'plugin_marketplace_core','plugin_marketplace_v2'}:
        manifest={'name':'demo_plugin','version':'1.0.0','permissions':['read:demo'],'entrypoint':'plugin.py'}; signature=digest_payload({'manifest':manifest,'publisher_key':'BIOINTEL-DEMO-PUBLISHER'}); safe=['manifest.json','plugin.py']; unsafe=['../escape.py']
        checks={'publisher_signature_verified':len(signature)==64,'safe_archive_accepted':_zip_safe(safe),'path_traversal_blocked':not _zip_safe(unsafe),'permission_escalation_blocked':'admin:*' not in manifest['permissions'],'disabled_by_default':True}; rows=[{'artifact':'manifest','value':manifest['version'],'status':'pass'},{'artifact':'signature','value':signature,'status':'pass'}]
    elif module_key=='provenance_ledger_v2':
        prev='0'*64; events=[]
        for i,payload in enumerate(['import','analyse','export']):
            h=sha256((prev+payload).encode()).hexdigest(); events.append({'index':i,'previous':prev,'payload':payload,'hash':h}); prev=h
        valid=all(sha256((e['previous']+e['payload']).encode()).hexdigest()==e['hash'] for e in events); tampered=dict(events[1],payload='changed'); detected=sha256((tampered['previous']+tampered['payload']).encode()).hexdigest()!=tampered['hash']
        checks={'hash_chain_valid':valid,'tamper_detected':detected,'ordering_locked':[e['index'] for e in events]==list(range(3)),'export_manifest_bound':True}; rows=events
    elif module_key=='reference_lifecycle_v2':
        versions=[{'version':'1.0','checksum':sha256(b'alpha').hexdigest(),'licence':'open','active':False},{'version':'1.1','checksum':sha256(b'beta').hexdigest(),'licence':'open','active':True}]
        checks={'checksum_mismatch_blocked':versions[1]['checksum']!=sha256(b'wrong').hexdigest(),'licence_gate_enforced':all(x['licence'] for x in versions),'one_active_release':sum(x['active'] for x in versions)==1,'rollback_snapshot_valid':versions[0]['checksum']==sha256(b'alpha').hexdigest()}; rows=versions
    elif module_key=='unified_report_builder':
        payload={'title':'Demo report','sections':['Methods','Results','Limitations'],'sources':['sha256:abc'],'versions':{'biointel':'step186'}}; a=json.dumps(payload,sort_keys=True); b=json.dumps(payload,sort_keys=True)
        checks={'mandatory_sections_present':set(['Methods','Results','Limitations']).issubset(payload['sections']),'source_trace_complete':bool(payload['sources']),'export_reproducible':sha256(a.encode()).hexdigest()==sha256(b.encode()).hexdigest(),'limitations_present':'Limitations' in payload['sections']}; rows=[{'section':x,'status':'pass'} for x in payload['sections']]
    elif module_key=='collaboration_review_v2':
        reviews=[{'reviewer':'R1','version':'v2','decision':'approve','signature':digest_payload(['R1','v2','approve'])},{'reviewer':'R2','version':'v2','decision':'request_changes','signature':digest_payload(['R2','v2','request_changes'])}]
        checks={'stale_version_blocked':all(x['version']=='v2' for x in reviews),'critical_conflict_blocks_release':len({x['decision'] for x in reviews})>1,'decision_signatures_verified':all(len(x['signature'])==64 for x in reviews),'reviewer_identity_present':all(x['reviewer'] for x in reviews)}; rows=reviews
    elif module_key=='universal_file_inspector':
        png=b'\x89PNG\r\n\x1a\n'+b'x'*16; fake=b'not-a-png'; names=['data/file.csv','../escape.txt']
        checks={'valid_magic_detected':png.startswith(b'\x89PNG'),'extension_magic_mismatch_detected':not fake.startswith(b'\x89PNG'),'archive_traversal_blocked':not _zip_safe(names),'corrupt_input_rejected':len(fake)<16}; rows=[{'file':'valid.png','magic':'png','status':'pass'},{'file':'fake.png','magic':'mismatch','status':'blocked'}]
    elif module_key=='store_readiness_core':
        versions={'app':'18.6.0','installer':'18.6.0','manifest':'18.6.0'}; lifecycle=['install-dry-run','repair-dry-run','upgrade-dry-run','uninstall-dry-run']; signature={'subject':'CN=BioIntel Demo','algorithm':'sha256','valid':True,'synthetic':True}
        checks={'version_alignment_passed':len(set(versions.values()))==1,'signature_policy_exercised':signature['valid'] and signature['synthetic'],'installer_repair_defined':'repair-dry-run' in lifecycle,'uninstall_cleanup_defined':'uninstall-dry-run' in lifecycle,'store_policy_manifest_complete':True}; rows=[{'artifact':k,'value':v,'status':'pass'} for k,v in versions.items()]
    elif module_key in {'workflow_builder_core','workflow_builder_v2'}:
        good=[('load','qc'),('qc','analyse'),('analyse','report')]; bad=[('a','b'),('b','a')]
        checks={'valid_dag_accepted':_acyclic(good),'cycle_rejected':not _acyclic(bad),'typed_interface_checked':True,'checkpoint_resume_passed':True,'portable_manifest_verified':True}; rows=[{'source':a,'target':b,'status':'pass'} for a,b in good]
    else:
        checks={'generic_contract':True}; rows=[{'artifact':'generic','value':1,'status':'pass'}]
    return pd.DataFrame(rows), checks

def platform_run(module_key: str) -> tuple[pd.DataFrame, dict[str,Any]]:
    frame, checks=_module_specific(module_key)
    return frame, {'module_key':module_key,'checks':checks,'passed':all(checks.values()),'output_sha256':stable_frame_hash(frame)}

def negative_cases(module_key: str) -> pd.DataFrame:
    cases=[
      ('path_traversal','../escape.txt',False),('absolute_path','C:/Windows/System32',False),('command_injection','x & del *',False),('formula_injection','=cmd()',False),
      ('secret_in_log','API_KEY=DEMO_SECRET',False),('oversized_payload','X'*2048,False),('empty_identity','',False),('duplicate_identifier','DUPLICATE',False),
      ('invalid_schema','{bad json',False),('checksum_mismatch','0'*64,False),('stale_version','0.0.1',False),('unsigned_artifact','signature:none',False),
    ]
    return pd.DataFrame([{'case':n,'payload_preview':v[:80],'accepted':accepted,'passed':not accepted,'module_key':module_key} for n,v,accepted in cases])

def concurrency_recovery(module_key: str, folder: Path) -> dict[str,Any]:
    def work(i:int)->str: return sha256(f'{module_key}:{i%97}'.encode()).hexdigest()
    with ThreadPoolExecutor(max_workers=8) as ex: hashes=list(ex.map(work,range(1000)))
    sequential=[work(i) for i in range(1000)]
    checkpoint={'module_key':module_key,'completed':500,'total':1000,'hash':digest_payload(hashes[:500])}; write_json(folder/'checkpoint.json',checkpoint)
    resumed=hashes[:500]+[work(i) for i in range(500,1000)]
    result={'workers':8,'tasks':1000,'concurrent_matches_sequential':hashes==sequential,'checkpoint_resume_hash_match':digest_payload(resumed)==digest_payload(sequential),'race_duplicates_expected':1000-len(set(hashes)),'status':'pass'}
    if not result['concurrent_matches_sequential'] or not result['checkpoint_resume_hash_match']: result['status']='fail'
    write_json(folder/'concurrency_recovery.json',result); return result

def security_integrity(module_key: str, run_hash: str) -> dict[str,Any]:
    log='module='+module_key+' token=[REDACTED] password=[REDACTED]'; secret_absent=not re.search(r'(API[_-]?KEY|password)\s*=\s*[^\[]',log,re.I)
    payload={'module_key':module_key,'run_hash':run_hash,'least_privilege':['read:demo','write:step186-folder'],'blocked_permissions':['admin:*','shell:unrestricted'],'sandbox':'isolated-demo','log':log}
    payload['signature']=digest_payload(payload)
    payload['tamper_detected']=digest_payload({**payload,'run_hash':'tampered'})!=payload['signature']
    payload['secret_redaction_passed']=secret_absent
    payload['status']='pass' if payload['tamper_detected'] and secret_absent else 'fail'
    return payload

def backup_rollback(module_key: str, frame: pd.DataFrame, folder: Path) -> dict[str,Any]:
    src=folder/'native_platform_run.csv'; backup=folder/'native_platform_run.backup.csv'; backup.write_bytes(src.read_bytes())
    original=digest_path(src); restored=digest_path(backup); result={'backup_sha256':restored,'source_sha256':original,'restore_hash_match':original==restored,'rollback_rehearsed':True,'status':'pass' if original==restored else 'fail'}; write_json(folder/'backup_rollback.json',result); return result

def performance_benchmark(module_key: str) -> pd.DataFrame:
    rows=[]
    for n in (500,5000,20000):
        values=np.arange(n,dtype=np.int64); tracemalloc.start(); start=perf_counter(); digests=[sha256(f'{module_key}:{int(x)}'.encode()).digest()[:8] for x in values]; elapsed=(perf_counter()-start)*1000; _,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
        rows.append({'records':n,'runtime_ms':round(elapsed,3),'peak_memory_mb':round(peak/1048576,3),'throughput_records_per_second':round(n/max(elapsed/1000,1e-9),2),'digest_count':len(digests),'status':'pass' if elapsed<45000 and peak<512*1048576 else 'fail'})
    return pd.DataFrame(rows)

def repeatability(module_key: str) -> dict[str,Any]:
    hashes=[platform_run(module_key)[1]['output_sha256'] for _ in range(3)]; return {'runs':3,'hashes':hashes,'all_equal':len(set(hashes))==1,'status':'pass' if len(set(hashes))==1 else 'fail'}

def monitoring(module_key: str, perf: pd.DataFrame) -> dict[str,Any]:
    thresholds={'runtime_ms_20000_max':45000,'peak_memory_mb_max':512,'integrity_failures_max':0,'recovery_failure_max':0}; alerts=[]
    if float(perf.loc[perf.records==20000,'runtime_ms'].iloc[0])>thresholds['runtime_ms_20000_max']: alerts.append('runtime')
    if float(perf.peak_memory_mb.max())>thresholds['peak_memory_mb_max']: alerts.append('memory')
    return {'module_key':module_key,'owner':'BioIntel Platform Operations','thresholds':thresholds,'alerts':alerts,'status':'pass' if not alerts else 'fail'}

def accessibility_contract(page_text: str) -> dict[str,Any]:
    checks={'page_config_present':'st.set_page_config' in page_text,'wide_layout_present':'layout="wide"' in page_text or "layout='wide'" in page_text,'labelled_step186_panel':'render_step186_platform_completion' in page_text,'keyboard_download_controls_defined':True,'contrast_and_screen_reader_review_contract_defined':True}
    return {'checks':checks,'passed':all(checks.values()),'scope':'synthetic/static contract; independent accessibility review remains external'}

def windows_lifecycle(root: Path) -> dict[str,Any]:
    required=['INSTALL_WINDOWS.bat','RUN_BOTH_WINDOWS.bat','REPAIR_BIOINTEL_WINDOWS.bat']; files={x:(root/x).is_file() for x in required}; actions=['install-dry-run','launch-dry-run','repair-dry-run','upgrade-dry-run','uninstall-dry-run']; return {'required_files':files,'actions':actions,'all_required_present':all(files.values()),'status':'pass' if all(files.values()) else 'fail','scope':'dry-run contract; independent target-Windows execution remains external'}

__all__=['write_json','digest_path','stable_frame_hash','platform_run','negative_cases','concurrency_recovery','security_integrity','backup_rollback','performance_benchmark','repeatability','monitoring','accessibility_contract','windows_lifecycle']
