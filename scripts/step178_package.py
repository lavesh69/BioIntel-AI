from __future__ import annotations
import argparse,json,zipfile
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT.parents[2];BASE='BioIntel-AI-Step178-19-MODULE-CLINICAL-OPERATIONAL-PRIVACY-ML-10OF10-INTERNAL';ASSIGNMENT=ROOT/'STEP178_PACKAGE_PART_ASSIGNMENT.json';SOURCE_MANIFEST=ROOT/'STEP178_SOURCE_MANIFEST_SHA256.json';FIXED_DATE=(2026,7,14,0,0,0)
EXCLUDED_DIRS={'.git','.venv','node_modules','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache'};EXCLUDED_SUFFIXES={'.pyc','.pyo','.tmp'}
def sha_file(path:Path)->str:
    h=sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def release_files(include_assignment:bool=True)->list[Path]:
    rows=[]
    for path in ROOT.rglob('*'):
        if not path.is_file() or path.is_symlink():continue
        rel=path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in rel.parts) or path.suffix.lower() in EXCLUDED_SUFFIXES:continue
        if not include_assignment and path==ASSIGNMENT:continue
        rows.append(path)
    return sorted(rows,key=lambda p:p.relative_to(ROOT).as_posix())
def prior_mapping()->dict[str,int]:
    result={}
    for part in range(1,5):
        path=OUT/f'BioIntel-AI-Step177-21-MODULE-MODEL-COHORT-RUNTIME-10OF10-INTERNAL-Part{part}.zip'
        if not path.is_file():continue
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.endswith('/') or not name.startswith('BioIntel-AI/'):continue
                result.setdefault(name[len('BioIntel-AI/'):],part)
    return result
def prepare()->dict:
    ASSIGNMENT.unlink(missing_ok=True);SOURCE_MANIFEST.unlink(missing_ok=True)
    entries=[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha_file(p),'size_bytes':p.stat().st_size} for p in release_files(False)]
    SOURCE_MANIFEST.write_text(json.dumps({'schema':'biointel.step178.source-manifest.v1','created_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'entries':entries,'excludes':[ASSIGNMENT.name]},indent=2)+'\n',encoding='utf-8')
    files=release_files(False);old=prior_mapping();sizes={1:0,2:0,3:0,4:0};assignments={};new=[]
    for path in files:
        rel=path.relative_to(ROOT).as_posix();part=old.get(rel)
        if part is not None:assignments[rel]=part;sizes[part]+=path.stat().st_size
    for path in files:
        rel=path.relative_to(ROOT).as_posix()
        if rel in assignments:continue
        forced=None
        if rel.startswith('.release_parts/step178_part') and rel.endswith('.ok'):forced=int(rel.split('step178_part',1)[1].split('.ok',1)[0])
        part=forced or min(sizes,key=sizes.get);assignments[rel]=part;sizes[part]+=path.stat().st_size;new.append(rel)
    payload={'schema':'biointel.step178.package-assignment.v1','base':BASE,'root_prefix':'BioIntel-AI/','file_count_excluding_assignment':len(assignments),'new_files':new,'part_uncompressed_bytes_excluding_assignment':sizes,'assignments':assignments};ASSIGNMENT.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8');print(json.dumps({'file_count':len(assignments),'new_files':len(new),'sizes':sizes},indent=2));return payload
def build_part(part:int)->Path:
    payload=json.loads(ASSIGNMENT.read_text(encoding='utf-8'));members=[r for r,v in payload['assignments'].items() if int(v)==part]
    if part==1:members.append(ASSIGNMENT.relative_to(ROOT).as_posix())
    output=OUT/f'{BASE}-Part{part}.zip';output.unlink(missing_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as zf:
        for rel in sorted(set(members)):
            path=ROOT/rel
            if not path.is_file() or path.is_symlink():raise FileNotFoundError(path)
            info=zipfile.ZipInfo(f'BioIntel-AI/{rel}',FIXED_DATE);info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            with path.open('rb') as src,zf.open(info,'w',force_zip64=True) as dst:
                for chunk in iter(lambda:src.read(8*1024*1024),b''):dst.write(chunk)
    print(json.dumps({'part':part,'path':str(output),'size_bytes':output.stat().st_size,'sha256':sha_file(output)},indent=2));return output
def verify()->dict:
    expected={p.relative_to(ROOT).as_posix() for p in release_files(True)};seen={};crc=[];unsafe=[];hashes={}
    for part in range(1,5):
        path=OUT/f'{BASE}-Part{part}.zip';hashes[path.name]={'sha256':sha_file(path),'size_bytes':path.stat().st_size}
        with zipfile.ZipFile(path) as zf:
            bad=zf.testzip()
            if bad:crc.append(f'{path.name}:{bad}')
            for info in zf.infolist():
                name=info.filename;pure=PurePosixPath(name)
                if name.startswith('/') or '..' in pure.parts or not name.startswith('BioIntel-AI/'):unsafe.append(f'{path.name}:{name}');continue
                if name.endswith('/'):continue
                rel=name[len('BioIntel-AI/'):];seen[rel]=seen.get(rel,0)+1
    missing=sorted(expected-set(seen));extra=sorted(set(seen)-expected);duplicates=sorted(r for r,c in seen.items() if c!=1);status='passed' if not(missing or extra or duplicates or crc or unsafe) else 'failed'
    report={'schema':'biointel.step178.package-integrity.v1','status':status,'source_files':len(expected),'packaged_files':len(seen),'missing':missing,'extra':extra,'duplicates':duplicates,'crc_errors':crc,'unsafe_paths':unsafe,'zip_files':hashes}
    (OUT/f'{BASE}-CHECKSUMS.json').write_text(json.dumps({'schema':'biointel.step178.package-checksums.v1','files':hashes},indent=2)+'\n',encoding='utf-8');(OUT/f'{BASE}-PACKAGE-INTEGRITY.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2));return report
def main()->int:
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--part',type=int,choices=(1,2,3,4));g.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.prepare:prepare();return 0
    if a.part:build_part(a.part);return 0
    return 0 if verify()['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
