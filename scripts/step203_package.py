from __future__ import annotations
import argparse, hashlib, json, os, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE_ROOT='BioIntel-AI-Step196-WINDOWS-RELEASE-V16'
PART_COUNT=5
STEP196_MANIFEST='STEP196_SOURCE_MANIFEST_SHA256.json'
STEP203_MANIFEST='STEP203_SOURCE_MANIFEST_SHA256.json'
STEP196_ASSIGNMENT='STEP196_PACKAGE_PART_ASSIGNMENT.json'
STEP203_ASSIGNMENT='STEP203_PACKAGE_PART_ASSIGNMENT.json'
METADATA={STEP196_MANIFEST,STEP203_MANIFEST,STEP196_ASSIGNMENT,STEP203_ASSIGNMENT}
EXCLUDED_DIRS={'.git','.venv','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','.release_parts','.hotfix_backups'}
# ``reports`` contains the bundled demo database as well as live application
# state (SQLite journals, generated reports and user-triggered exports).  It
# must travel in the ZIP package, but it cannot be part of the immutable
# source-hash gate: normal use can legitimately change those files and used to
# make the next startup look like a corrupted installation.
IMMUTABLE_EXCLUDED_DIRS=EXCLUDED_DIRS|{'reports'}
EXCLUDED_SUFFIXES={'.pyc','.pyo'}
RUNTIME_EXCLUDES={'.biointel_step196_installed','reports/step196/validation.json','reports/step196_release_metadata_repair.json','reports/step196/v16-preinstall.json','reports/step196/v16-validation-prebuild.json','reports/step203-preflight.json','reports/step203-preflight-runtime.json'}
PRECOMP={'.whl','.zip','.gz','.bz2','.xz','.7z','.rar','.png','.jpg','.jpeg','.webp','.gif','.ico','.pdf','.mp4','.avi','.npy','.npz','.parquet','.sqlite','.sqlite3','.db'}

def sha256(path:Path)->str:
 d=hashlib.sha256()
 with path.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): d.update(c)
 return d.hexdigest()

def safe(name:str)->bool:
 p=PurePosixPath(name); return bool(p.parts) and not p.is_absolute() and '..' not in p.parts

def source_files(include_metadata:bool, *, immutable_only:bool=False)->list[Path]:
 out=[]
 excluded_dirs=IMMUTABLE_EXCLUDED_DIRS if immutable_only else EXCLUDED_DIRS
 for p in ROOT.rglob('*'):
  if not p.is_file(): continue
  rel=p.relative_to(ROOT); txt=rel.as_posix()
  if any(part in excluded_dirs for part in rel.parts): continue
  if p.suffix.lower() in EXCLUDED_SUFFIXES or p.name.endswith(('-wal','-shm')): continue
  if rel.parts[:2]==('UserData','proof_gates_v10'): continue
  if txt in RUNTIME_EXCLUDES: continue
  if not include_metadata and p.name in METADATA: continue
  out.append(p)
 return sorted(out)

def entries(files:list[Path])->list[dict]:
 workers=min(16,max(4,os.cpu_count() or 4))
 with ThreadPoolExecutor(max_workers=workers) as ex: hashes=list(ex.map(sha256,files))
 return [{'path':p.relative_to(ROOT).as_posix(),'size_bytes':p.stat().st_size,'sha256':h} for p,h in zip(files,hashes,strict=True)]

def write_manifests():
 base=source_files(False,immutable_only=True); rows=entries(base)
 (ROOT/STEP196_MANIFEST).write_text(json.dumps({'schema':'biointel.step196.source-manifest.v1','release_step':196,'release_version':'15.4.0','hash_algorithm':'sha256','excluded_runtime_paths':sorted(RUNTIME_EXCLUDES),'entries':rows},indent=2)+'\n',encoding='utf-8')
 files=[p for p in source_files(False,immutable_only=True) if p.name!=STEP203_MANIFEST]+[ROOT/STEP196_MANIFEST]
 dedup={r['path']:r for r in entries(files)}
 (ROOT/STEP203_MANIFEST).write_text(json.dumps({'schema':'biointel.step203.python-startup-hotfix.source-manifest.v1','release_step':203,'base_release_step':196,'generated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'hash_algorithm':'sha256','entries':[dedup[k] for k in sorted(dedup)]},indent=2)+'\n',encoding='utf-8')

def allocate(files:list[Path]):
 buckets=[[] for _ in range(PART_COUNT)]; sizes=[0]*PART_COUNT
 for p in sorted(files,key=lambda x:x.stat().st_size,reverse=True):
  i=min(range(PART_COUNT),key=lambda j:sizes[j]); buckets[i].append(p); sizes[i]+=p.stat().st_size
 return buckets,sizes

def compression(p:Path):
 return zipfile.ZIP_STORED

def build_part(dest:Path,files:list[Path],part:int):
 tmp=dest.with_suffix('.zip.tmp'); tmp.unlink(missing_ok=True)
 with zipfile.ZipFile(tmp,'w',allowZip64=True) as z:
  for p in sorted(files):
   z.write(p,f'{ARCHIVE_ROOT}/{p.relative_to(ROOT).as_posix()}',compress_type=compression(p),compresslevel=6)
  for step in (196,200,201,202,203):
   z.writestr(f'{ARCHIVE_ROOT}/.release_parts/step{step}_part{part}.ok',f'BioIntel AI Step{step} compatibility marker for Step203 part {part}\n')
 with zipfile.ZipFile(tmp) as z:
  bad=z.testzip(); names=z.namelist()
  if bad or any(not safe(n) for n in names): raise RuntimeError(f'bad archive {dest.name}: {bad}')
 os.replace(tmp,dest)
 return {'file':dest.name,'size_bytes':dest.stat().st_size,'sha256':sha256(dest),'source_entries':len(files)}

def verify(parts:list[Path],expected_files:list[Path]):
 expected={f'{ARCHIVE_ROOT}/{p.relative_to(ROOT).as_posix()}' for p in expected_files}; seen={}; markers={s:[] for s in (196,200,201,202,203)}; crc=[]; unsafe=[]
 for part in parts:
  with zipfile.ZipFile(part) as z:
   bad=z.testzip()
   if bad: crc.append(f'{part.name}:{bad}')
   for i in z.infolist():
    n=i.filename
    if not safe(n): unsafe.append(n)
    matched=False
    for s in markers:
     if f'/.release_parts/step{s}_part' in n: markers[s].append(n); matched=True; break
    if not matched: seen[n]=seen.get(n,0)+1
 missing=sorted(expected-set(seen)); extra=sorted(set(seen)-expected); dup=sorted(n for n,c in seen.items() if c!=1)
 marker_ok=True
 for s in markers:
  exp=[f'{ARCHIVE_ROOT}/.release_parts/step{s}_part{i}.ok' for i in range(1,6)]
  marker_ok &= sorted(markers[s])==exp
 passed=not any((missing,extra,dup,crc,unsafe)) and marker_ok
 return {'schema':'biointel.step203.package-integrity.v1','status':'passed' if passed else 'failed','source_files':len(expected),'packaged_source_files':len(seen),'missing_files':missing,'extra_files':extra,'duplicate_files':dup,'crc_errors':crc,'unsafe_paths':unsafe,'markers':markers}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--output-dir',type=Path,required=True); ap.add_argument('--name',default='BioIntel-AI-Step203-PYTHON-STARTUP-HOTFIX-WINDOWS-V16-5PART'); a=ap.parse_args(); out=a.output_dir.resolve(); out.mkdir(parents=True,exist_ok=True)
 for n in METADATA: (ROOT/n).unlink(missing_ok=True)
 write_manifests()
 initial=[p for p in source_files(True) if p.name not in {STEP196_ASSIGNMENT,STEP203_ASSIGNMENT}]
 buckets,sizes=allocate(initial)
 rows=[]
 for idx,b in enumerate(buckets,1):
  for p in b: rows.append({'path':p.relative_to(ROOT).as_posix(),'part':idx,'size_bytes':p.stat().st_size})
 payload={'schema':'biointel.step203.package-assignment.v1','step':203,'part_count':5,'generated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'estimated_uncompressed_part_bytes':sizes,'entries':rows}
 text=json.dumps(payload,indent=2)+'\n'; (ROOT/STEP203_ASSIGNMENT).write_text(text,encoding='utf-8'); (ROOT/STEP196_ASSIGNMENT).write_text(text.replace('step203.package-assignment','step196.compatible-step203.package-assignment'),encoding='utf-8')
 for p in (ROOT/STEP196_ASSIGNMENT,ROOT/STEP203_ASSIGNMENT):
  i=min(range(PART_COUNT),key=lambda j:sizes[j]); buckets[i].append(p); sizes[i]+=p.stat().st_size
 parts=[out/f'{a.name}-Part{i}.zip' for i in range(1,6)]
 with ThreadPoolExecutor(max_workers=5) as ex: results=list(ex.map(lambda t:build_part(*t),[(parts[i],buckets[i],i+1) for i in range(5)]))
 integ=verify(parts,source_files(True)); integ['parts']=results; integ['part_uncompressed_bytes']=sizes
 (out/'STEP203_PACKAGE_INTEGRITY.json').write_text(json.dumps(integ,indent=2)+'\n',encoding='utf-8')
 (out/'SHA256SUMS.txt').write_text(''.join(f"{r['sha256']}  {r['file']}\n" for r in sorted(results,key=lambda x:x['file'])),encoding='utf-8')
 print(json.dumps(integ,indent=2)); return 0 if integ['status']=='passed' else 1
if __name__=='__main__': raise SystemExit(main())
