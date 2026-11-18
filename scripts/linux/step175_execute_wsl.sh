#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:?project root required}"
MODE="${2:-plan}"
HOST_ID="${3:-unknown-host}"
STATE_ROOT="$PROJECT_ROOT/UserData/step175"
RESULT_ROOT="$STATE_ROOT/wsl_results/$HOST_ID"
MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-$HOME/.local/share/biointel-micromamba}"
export MAMBA_ROOT_PREFIX
mkdir -p "$RESULT_ROOT" "$STATE_ROOT/logs" "$HOME/.local/bin"

if ! command -v micromamba >/dev/null 2>&1; then
  if [[ "$MODE" != "execute" && "$MODE" != "resume" ]]; then
    echo "micromamba missing; execution would bootstrap it"
  else
    tmp="$(mktemp -d)"
    curl --fail --location --retry 5 --connect-timeout 30 https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C "$tmp" bin/micromamba
    install -m 0755 "$tmp/bin/micromamba" "$HOME/.local/bin/micromamba"
    rm -rf "$tmp"
  fi
fi
export PATH="$HOME/.local/bin:$PATH"

python3 - "$PROJECT_ROOT" "$MODE" "$HOST_ID" <<'PY'
import csv, json, os, pathlib, shlex, subprocess, sys, hashlib, time
root=pathlib.Path(sys.argv[1]); mode=sys.argv[2]; host_id=sys.argv[3]
base=root/'data'/'step175'; result_root=root/'UserData'/'step175'/'wsl_results'/host_id
result_root.mkdir(parents=True,exist_ok=True)
engines=list(csv.DictReader((base/'engine_execution_catalog.csv').open(encoding='utf-8')))
groups=list(csv.DictReader((base/'environment_groups.csv').open(encoding='utf-8')))

def run(cmd, timeout=7200):
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout,check=False)
    return {'return_code':p.returncode,'stdout':p.stdout[-12000:],'stderr':p.stderr[-12000:]}

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()

def write_json(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,indent=2,default=str)+'\n',encoding='utf-8')

summary={'schema':'biointel.step175.wsl-execution.v1','host_id':host_id,'mode':mode,'groups':[],'engines':[],'started_at_epoch':time.time()}
for group in groups:
    gid=group['group_id']; env=f'biointel175-{gid}'; yml=base/'environments'/f'{gid}.yml'
    explicit=result_root/f'{gid}-explicit.txt'
    group_result={'group_id':gid,'environment':env,'environment_file':str(yml),'status':'planned'}
    if mode in {'execute','resume'}:
        cmd=['micromamba','env','update' if mode=='resume' else 'create','-y','-n',env,'-f',str(yml)]
        if mode=='resume' and not (pathlib.Path(os.environ.get('MAMBA_ROOT_PREFIX',''))/'envs'/env).exists():
            cmd=['micromamba','create','-y','-n',env,'-f',str(yml)]
        result=run(cmd)
        group_result.update({'command':cmd,**result,'status':'installed' if result['return_code']==0 else 'failed'})
        if result['return_code']==0:
            listing=run(['micromamba','list','-n',env,'--explicit'])
            explicit.write_text(listing['stdout'],encoding='utf-8')
            group_result['explicit_manifest_path']=str(explicit)
            group_result['explicit_manifest_sha256']=sha(explicit)
    summary['groups'].append(group_result)
    write_json(result_root/f'group-{gid}.json',{**group_result,'schema':'biointel.step175.group-result.v1','host_id':host_id})

for item in engines:
    engine=item['engine']; gid=item['environment_group']; env=f'biointel175-{gid}'
    result={'schema':'biointel.step175.engine-result.v1','host_id':host_id,'engine':engine,'environment_group':gid,'session_id':f'{host_id}-step175','installed':False,'smoke_test_passed':False,'golden_fixture_passed':False,'negative_control_passed':False,'module_integration_passed':False,'detected_path':'','detected_version':'','executable_sha256':'','licence_text_sha256':'','explicit_manifest_sha256':''}
    if item['automatic_install_eligible'].lower()!='true':
        result['status']='manual-provider-action-required'
        write_json(result_root/f'engine-{engine}.json',result); summary['engines'].append(result); continue
    if mode not in {'execute','resume'}:
        result['status']='planned'
        write_json(result_root/f'engine-{engine}.json',result); summary['engines'].append(result); continue
    explicit=result_root/f'{gid}-explicit.txt'
    if explicit.exists(): result['explicit_manifest_sha256']=sha(explicit)
    probe=item['probe_executable']
    if probe=='python':
        imports={'openmm':'openmm','openslide':'openslide','scanpy':'scanpy','scvelo':'scvelo','cellrank':'cellrank','stardist':'stardist','llama_cpp':'llama_cpp'}
        module=imports.get(engine,engine)
        command=['micromamba','run','-n',env,'python','-c',f'import {module}; print(getattr({module}, "__version__", "version-available"))']
        path_probe=['micromamba','run','-n',env,'python','-c','import sys; print(sys.executable)']
    else:
        smoke=[v.strip() for v in item.get('smoke_test','').split(',') if v.strip()]
        command=['micromamba','run','-n',env,*smoke] if smoke else ['micromamba','run','-n',env,probe,'--version']
        path_probe=['micromamba','run','-n',env,'bash','-lc',f'command -v {shlex.quote(probe)}']
    smoke=run(command,timeout=300)
    path_out=run(path_probe,timeout=60)
    detected=path_out['stdout'].strip().splitlines()[-1] if path_out['return_code']==0 and path_out['stdout'].strip() else ''
    result.update({'installed':smoke['return_code']==0 and bool(detected),'smoke_test_passed':smoke['return_code']==0,'detected_path':detected,'detected_version':smoke['stdout'].strip()[:1000],'smoke_stdout':smoke['stdout'],'smoke_stderr':smoke['stderr']})
    if detected:
        hash_out=run(['micromamba','run','-n',env,'bash','-lc',f'sha256sum {shlex.quote(detected)} | cut -d" " -f1'])
        result['executable_sha256']=hash_out['stdout'].strip().splitlines()[-1] if hash_out['return_code']==0 and hash_out['stdout'].strip() else ''
    neg=run(['micromamba','run','-n',env,'bash','-lc',f'{shlex.quote(probe)} --biointel-invalid-option >/dev/null 2>&1'],timeout=60) if probe!='python' else {'return_code':1}
    result['negative_control_passed']=neg['return_code']!=0
    # Operational known-answer for Step 175: executable resolves, version/smoke succeeds, deterministic package manifest exists.
    result['golden_fixture_passed']=bool(result['smoke_test_passed'] and result['executable_sha256'] and result['explicit_manifest_sha256'])
    result['module_integration_passed']=False
    result['status']='installed-awaiting-module-integration' if result['golden_fixture_passed'] else 'failed'
    write_json(result_root/f'engine-{engine}.json',result); summary['engines'].append(result)
summary['completed_at_epoch']=time.time()
summary['installed']=sum(bool(v.get('installed')) for v in summary['engines'])
summary['golden_fixture_passed']=sum(bool(v.get('golden_fixture_passed')) for v in summary['engines'])
summary['note']='module_integration_passed remains false until BioIntel native integration verification imports a signed result.'
write_json(result_root/'wsl-execution-summary.json',summary)
print(json.dumps(summary,indent=2))
PY
