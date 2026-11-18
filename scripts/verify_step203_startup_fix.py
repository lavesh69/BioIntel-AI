from __future__ import annotations
import argparse, json, struct, sys
from datetime import datetime, timezone
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--output'); args=ap.parse_args()
    root=Path(args.root).resolve(); checks=[]
    def add(name, ok, detail): checks.append({'name':name,'passed':bool(ok),'detail':detail})
    required=['INSTALL_WINDOWS.bat','INSTALL_PYTHON311_WINDOWS.bat','FIX_PYTHON_STARTUP_WINDOWS.bat','REPAIR_STEP203_WINDOWS.bat','scripts/find_python311_windows.ps1','scripts/install_python311_user.ps1']
    missing=[x for x in required if not (root/x).is_file()]; add('hotfix files',not missing,missing or 'complete')
    install=(root/'INSTALL_WINDOWS.bat').read_text(encoding='utf-8-sig',errors='replace')
    locator=(root/'scripts/find_python311_windows.ps1').read_text(encoding='utf-8-sig',errors='replace')
    pyinst=(root/'scripts/install_python311_user.ps1').read_text(encoding='utf-8-sig',errors='replace')
    add('direct Python path detection', all(t in install for t in ('LOCALAPPDATA','Python311\\python.exe','find_python311_windows.ps1')), 'direct-first plus locator fallback')
    add('space-safe path handling', '"%%~fP"' in install and 'DisableDelayedExpansion' in install, 'quoted executable paths')
    add('no TEMP installer download', '%TEMP%' not in pyinst.upper() and 'BioIntelAI\\Downloads' in pyinst, 'app-local download directory')
    add('official signature verification', 'Get-AuthenticodeSignature' in pyinst and 'Python Software Foundation' in pyinst, 'signed installer required')
    add('compatible runtime policy', "sys.version_info[:2]==(3,11)" in install and '3.11.9 x64 exactly' not in install, 'any CPython 3.11.x x64 accepted; 3.11.9 preferred installer')
    add('locator breadth', all(t in locator for t in ('Python311\\python.exe','where.exe python','PythonCore','Get-Command python.exe')), 'user/local/registry/launcher/PATH')
    markers=[root/'.release_parts'/f'step203_part{i}.ok' for i in range(1,6)]
    add('Step203 markers',all(x.is_file() for x in markers),[str(x.name) for x in markers if not x.is_file()] or '5/5 present')
    runtime_ok=sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==64
    # Source-builder hosts may not be CP311; this is informational, not a package failure.
    add('builder runtime informational',True,{'version':sys.version.split()[0],'bits':struct.calcsize('P')*8,'target_runtime_ok':runtime_ok})
    passed=all(x['passed'] for x in checks)
    report={'schema':'biointel.step203.python-startup-hotfix.v1','generated_at':datetime.now(timezone.utc).isoformat(),'passed':passed,'checks':checks}
    out=Path(args.output) if args.output else root/'reports'/'step203-python-startup-hotfix.json'
    if not out.is_absolute(): out=root/out
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2)); return 0 if passed else 1
if __name__=='__main__': raise SystemExit(main())
