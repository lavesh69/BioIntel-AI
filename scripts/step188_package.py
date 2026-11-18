from __future__ import annotations
import argparse,json,zipfile
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parents[1]
BASE='BioIntel-AI-Step188-UNIVERSAL-MAJOR-MODULE-STANDARD-80OF80-10OF10'
ASSIGNMENT=ROOT/'STEP188_PACKAGE_PART_ASSIGNMENT.json'
SOURCE_MANIFEST=ROOT/'STEP188_SOURCE_MANIFEST_SHA256.json'
FIXED_DATE=(2026,7,15,0,0,0)
EXCLUDED_DIRS={'.git','.venv','node_modules','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache'}
EXCLUDED_SUFFIXES={'.pyc','.pyo','.tmp'}
def sha_file(path:Path)->str:
 h=sha256()
 with path.open('rb') as f:
  for c in iter(lambda:f.read(8*1024*1024),b''):h.update(c)
 return h.hexdigest()
def release_files(include_assignment=True):
 rows=[]
 for p in ROOT.rglob('*'):
  if not p.is_file() or p.is_symlink():continue
  rel=p.relative_to(ROOT)
  if any(x in EXCLUDED_DIRS for x in rel.parts) or p.suffix.lower() in EXCLUDED_SUFFIXES:continue
  if not include_assignment and p==ASSIGNMENT:continue
  rows.append(p)
 return sorted(rows,key=lambda x:x.relative_to(ROOT).as_posix())
def prior_mapping():
 result={};prev='BioIntel-AI-Step187-ALL-256-PAGES-10OF10-INTERNAL-DEMO'
 for part in range(1,5):
  z=OUT/f'{prev}-Part{part}.zip'
  if not z.is_file():continue
  with zipfile.ZipFile(z) as a:
   for name in a.namelist():
    if not name.endswith('/') and name.startswith('BioIntel-AI/'):result.setdefault(name[len('BioIntel-AI/'):],part)
 return result
def prepare():
 ASSIGNMENT.unlink(missing_ok=True);SOURCE_MANIFEST.unlink(missing_ok=True)
 entries=[]
 for p in release_files(False):
  entries.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha_file(p),'size_bytes':p.stat().st_size})
 SOURCE_MANIFEST.write_text(json.dumps({'schema':'biointel.step188.source-manifest.v1','created_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'entries':entries,'excludes':[ASSIGNMENT.name]},indent=2)+'\n')
 files=release_files(False);old=prior_mapping();sizes={1:0,2:0,3:0,4:0};assign={};new=[]
 for p in files:
  rel=p.relative_to(ROOT).as_posix();part=old.get(rel)
  if part:assign[rel]=part;sizes[part]+=p.stat().st_size
 for p in files:
  rel=p.relative_to(ROOT).as_posix()
  if rel in assign:continue
  forced=None
  if rel.startswith('.release_parts/step188_part') and rel.endswith('.ok'):forced=int(rel.split('step188_part',1)[1].split('.ok',1)[0])
  part=forced or min(sizes,key=sizes.get);assign[rel]=part;sizes[part]+=p.stat().st_size;new.append(rel)
 payload={'schema':'biointel.step188.package-assignment.v1','base':BASE,'root_prefix':'BioIntel-AI/','file_count_excluding_assignment':len(assign),'new_files':new,'part_uncompressed_bytes_excluding_assignment':sizes,'assignments':assign}
 ASSIGNMENT.write_text(json.dumps(payload,indent=2)+'\n')
 print(json.dumps({'file_count':len(assign),'new_files':len(new),'sizes':sizes},indent=2));return payload
def build_part(part:int):
 payload=json.loads(ASSIGNMENT.read_text());members=[r for r,a in payload['assignments'].items() if int(a)==part]
 if part==1:members.append(ASSIGNMENT.relative_to(ROOT).as_posix())
 out=OUT/f'{BASE}-Part{part}.zip';out.unlink(missing_ok=True)
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
  for rel in sorted(set(members)):
   p=ROOT/rel
   info=zipfile.ZipInfo(f'BioIntel-AI/{rel}',FIXED_DATE);info.compress_type=zipfile.ZIP_STORED;info.external_attr=0o100644<<16
   with p.open('rb') as src,z.open(info,'w',force_zip64=True) as dst:
    for c in iter(lambda:src.read(8*1024*1024),b''):dst.write(c)
 print(json.dumps({'part':part,'path':str(out),'size_bytes':out.stat().st_size,'sha256':sha_file(out)},indent=2));return out
def verify():
 expected={p.relative_to(ROOT).as_posix() for p in release_files(True)};seen={};crc=[];unsafe=[];hashes={}
 for part in range(1,5):
  p=OUT/f'{BASE}-Part{part}.zip';hashes[p.name]={'sha256':sha_file(p),'size_bytes':p.stat().st_size}
  with zipfile.ZipFile(p) as z:
   bad=z.testzip()
   if bad:crc.append(f'{p.name}:{bad}')
   for info in z.infolist():
    name=info.filename;pure=PurePosixPath(name)
    if name.startswith('/') or '..' in pure.parts or not name.startswith('BioIntel-AI/'):unsafe.append(f'{p.name}:{name}');continue
    if name.endswith('/'):continue
    rel=name[len('BioIntel-AI/'):];seen[rel]=seen.get(rel,0)+1
 missing=sorted(expected-set(seen));extra=sorted(set(seen)-expected);dups=sorted(k for k,v in seen.items() if v!=1);status='passed' if not(missing or extra or dups or crc or unsafe) else 'failed'
 report={'schema':'biointel.step188.package-integrity.v1','status':status,'source_files':len(expected),'packaged_files':len(seen),'missing':missing,'extra':extra,'duplicates':dups,'crc_errors':crc,'unsafe_paths':unsafe,'zip_files':hashes}
 (OUT/f'{BASE}-CHECKSUMS.json').write_text(json.dumps({'schema':'biointel.step188.package-checksums.v1','files':hashes},indent=2)+'\n');(OUT/f'{BASE}-PACKAGE-INTEGRITY.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return report
def main():
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--part',type=int,choices=(1,2,3,4));g.add_argument('--verify',action='store_true');a=p.parse_args()
 if a.prepare:prepare();return 0
 if a.part:build_part(a.part);return 0
 return 0 if verify()['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
