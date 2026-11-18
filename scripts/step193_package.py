from __future__ import annotations
import argparse, hashlib, json, os, zipfile
from pathlib import Path, PurePosixPath
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_NAME='BioIntel-AI-Step193-MANDATORY-MODULE-COMPLETION-INSTALLATION-REPAIR-80OF80'
MANIFEST_NAME='STEP193_SOURCE_MANIFEST_SHA256.json'
ASSIGNMENT_NAME='STEP193_PACKAGE_PART_ASSIGNMENT.json'
EXCLUDED_DIRS={'.git','.venv','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','.release_parts'}
EXCLUDED_SUFFIXES={'.pyc','.pyo'}

def sha256(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
 return h.hexdigest()

def safe_relative(name:str)->bool:
 p=PurePosixPath(name);return not p.is_absolute() and '..' not in p.parts and all(p.parts)

def source_files(include_metadata:bool)->list[Path]:
 files=[]
 for path in ROOT.rglob('*'):
  if not path.is_file():continue
  rel=path.relative_to(ROOT)
  if any(part in EXCLUDED_DIRS for part in rel.parts):continue
  if path.suffix.lower() in EXCLUDED_SUFFIXES:continue
  if not include_metadata and rel.as_posix() in {MANIFEST_NAME,ASSIGNMENT_NAME}:continue
  files.append(path)
 return sorted(files)

def write_source_manifest()->dict[str,Any]:
 entries=[{'path':p.relative_to(ROOT).as_posix(),'size_bytes':p.stat().st_size,'sha256':sha256(p)} for p in source_files(False)]
 payload={'schema':'biointel.step193.source-manifest.v1','release_step':193,'release_version':'15.1.0','entries':entries}
 (ROOT/MANIFEST_NAME).write_text(json.dumps(payload,indent=2)+'\n')
 return payload

def allocate(files:list[Path])->tuple[list[list[Path]],list[int]]:
 buckets=[[] for _ in range(4)];sizes=[0]*4
 for p in sorted(files,key=lambda x:x.stat().st_size,reverse=True):
  i=min(range(4),key=lambda j:sizes[j]);buckets[i].append(p);sizes[i]+=p.stat().st_size
 return buckets,sizes

def build_zip(dest:Path,files:list[Path],part:int)->dict[str,Any]:
 tmp=dest.with_suffix(dest.suffix+'.tmp');tmp.unlink(missing_ok=True)
 with zipfile.ZipFile(tmp,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
  for src in sorted(files):z.write(src,(Path('BioIntel-AI')/src.relative_to(ROOT)).as_posix())
  z.writestr(f'BioIntel-AI/.release_parts/step193_part{part}.ok','step193\n')
 with zipfile.ZipFile(tmp) as z:
  bad=z.testzip();names=z.namelist();unsafe=[n for n in names if not safe_relative(n)];marker=f'BioIntel-AI/.release_parts/step193_part{part}.ok'
  if bad or unsafe or marker not in names:
   tmp.unlink(missing_ok=True);raise RuntimeError(f'Part {part} invalid: bad={bad} unsafe={unsafe[:3]} marker={marker in names}')
 os.replace(tmp,dest)
 return {'sha256':sha256(dest),'size_bytes':dest.stat().st_size,'entries':len(files)+1}

def verify(parts:list[Path],expected_files:list[Path])->dict[str,Any]:
 expected={f'BioIntel-AI/{p.relative_to(ROOT).as_posix()}' for p in expected_files};seen={};markers=[];crc=[];unsafe=[]
 for part in parts:
  with zipfile.ZipFile(part) as z:
   bad=z.testzip()
   if bad:crc.append(f'{part.name}:{bad}')
   for info in z.infolist():
    n=info.filename
    if not safe_relative(n):unsafe.append(n)
    if '/.release_parts/step193_part' in n:markers.append(n);continue
    seen[n]=seen.get(n,0)+1
 actual=set(seen);missing=sorted(expected-actual);extra=sorted(actual-expected);dupes=sorted(n for n,c in seen.items() if c!=1)
 expected_markers=[f'BioIntel-AI/.release_parts/step193_part{i}.ok' for i in range(1,5)]
 ok=not any((missing,extra,dupes,crc,unsafe)) and sorted(markers)==expected_markers
 return {'schema':'biointel.step193.package-integrity.v1','status':'passed' if ok else 'failed','source_files':len(expected),'packaged_source_files':len(actual),'package_entries_including_markers':sum(seen.values())+len(markers),'release_markers':sorted(markers),'missing_files':missing,'extra_files':extra,'duplicate_files':dupes,'crc_errors':crc,'unsafe_paths':unsafe}

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=ROOT.parent);p.add_argument('--name',default=DEFAULT_NAME);args=p.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
 (ROOT/MANIFEST_NAME).unlink(missing_ok=True);(ROOT/ASSIGNMENT_NAME).unlink(missing_ok=True);write_source_manifest()
 initial=source_files(True);buckets,sizes=allocate(initial)
 assignment={'schema':'biointel.step193.package-assignment.v1','release_step':193,'release_version':'15.1.0','assignments':{p.relative_to(ROOT).as_posix():i+1 for i,b in enumerate(buckets) for p in b},'part_uncompressed_bytes':sizes}
 i=min(range(4),key=lambda j:sizes[j]);assignment['assignments'][ASSIGNMENT_NAME]=i+1;(ROOT/ASSIGNMENT_NAME).write_text(json.dumps(assignment,indent=2)+'\n');buckets[i].append(ROOT/ASSIGNMENT_NAME);sizes[i]+=(ROOT/ASSIGNMENT_NAME).stat().st_size
 parts=[];checks={}
 for n,b in enumerate(buckets,1):
  dest=out/f'{args.name}-Part{n}.zip';checks[dest.name]=build_zip(dest,b,n);parts.append(dest)
 integrity=verify(parts,source_files(True));integrity['checksums']={k:{'sha256':v['sha256'],'size_bytes':v['size_bytes']} for k,v in checks.items()};integrity['part_uncompressed_bytes']=sizes
 (out/f'{args.name}-CHECKSUMS.json').write_text(json.dumps(integrity['checksums'],indent=2)+'\n')
 ip=out/f'{args.name}-PACKAGE-INTEGRITY.json';ip.write_text(json.dumps(integrity,indent=2)+'\n')
 print(json.dumps({'outputs':[str(x) for x in parts],'integrity':integrity},indent=2));return 0 if integrity['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
