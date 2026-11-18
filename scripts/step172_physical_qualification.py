from __future__ import annotations
import argparse, hashlib, json, os, platform, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def _run(cmd):
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=30,check=False)
  return {'passed':p.returncode==0,'return_code':p.returncode,'stdout':p.stdout[-1000:],'stderr':p.stderr[-1000:]}
 except Exception as exc: return {'passed':False,'error':str(exc)}

def main():
 parser=argparse.ArgumentParser(); parser.add_argument('--output'); parser.add_argument('--instrument-tested',action='store_true'); parser.add_argument('--sleep-resume-tested',action='store_true'); parser.add_argument('--antivirus-tested',action='store_true'); parser.add_argument('--network-loss-tested',action='store_true'); args=parser.parse_args()
 checks={}
 checks['windows_tested']={'passed':platform.system().lower()=='windows','detail':platform.platform()}
 checks['python_process']=_run([sys.executable,'-c','print(172)'])
 temp_root=Path(tempfile.mkdtemp(prefix='biointel-step172-'))
 try:
  payload=os.urandom(8*1024*1024); path=temp_root/'large_file_probe.bin'; path.write_bytes(payload)
  checks['large_file_tested']={'passed':hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(payload).digest(),'bytes':len(payload)}
  checkpoint=temp_root/'checkpoint.json'; checkpoint.write_text(json.dumps({'state':'running'})); checkpoint.replace(temp_root/'checkpoint.recovered.json')
  checks['recovery_tested']={'passed':(temp_root/'checkpoint.recovered.json').is_file()}
 finally: shutil.rmtree(temp_root,ignore_errors=True)
 nvidia=shutil.which('nvidia-smi')
 checks['gpu_tested']={'passed':bool(nvidia and _run([nvidia,'--query-gpu=name,driver_version','--format=csv,noheader'])['passed']),'required_by_module':False}
 checks['instrument_tested']={'passed':bool(args.instrument_tested),'manual_evidence_required':True}
 checks['sleep_resume_tested']={'passed':bool(args.sleep_resume_tested),'manual_evidence_required':True}
 checks['antivirus_tested']={'passed':bool(args.antivirus_tested),'manual_evidence_required':True}
 checks['network_loss_tested']={'passed':bool(args.network_loss_tested),'manual_evidence_required':True}
 report={'schema':'biointel.step172.physical-qualification.v1','generated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'host':platform.node(),'platform':platform.platform(),'checks':checks,'all_automatic_checks_passed':all(v.get('passed',False) for k,v in checks.items() if not v.get('manual_evidence_required')),'all_checks_passed':all(v.get('passed',False) for v in checks.values()),'boundary':'This report records tests on the machine that executed it. It does not certify another Windows, GPU, laboratory instrument or site.'}
 out=Path(args.output).resolve() if args.output else ROOT/'reports'/'step172_physical_qualification.json'; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2)); return 0 if report['all_automatic_checks_passed'] else 1
if __name__=='__main__': raise SystemExit(main())
