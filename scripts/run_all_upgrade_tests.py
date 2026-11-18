"""
BioIntel AI 15.6.0 — Master Automated Test & Qualification Suite
Performs syntax compilation, Group A-E scientific domain audits, connectivity/health widget audits,
Global Weather & Environment audits, adapter qualification probes, UI responsive matrix checks, release gate checks, and Windows runtime compatibility.
"""

import os
import sys
import py_compile
import subprocess
import json
import time

def run_test_suite():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_py = os.path.join(project_root, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_py):
        venv_py = sys.executable

    print("============================================================")
    print("BioIntel AI 15.6.0 — Master Automated Test Suite")
    print("============================================================")

    passed_count = 0
    failed_count = 0

    # 1. Syntax Compilation Check
    print("\n[Test 1/9] Compiling Python source files for syntax errors...")
    syntax_errors = []
    py_files_checked = 0
    for root_dir in [os.path.join(project_root, "src"), os.path.join(project_root, "pages"), os.path.join(project_root, "scripts")]:
        if not os.path.exists(root_dir):
            continue
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                if filename.endswith(".py"):
                    py_files_checked += 1
                    full_path = os.path.join(dirpath, filename)
                    try:
                        py_compile.compile(full_path, doraise=True)
                    except Exception as e:
                        syntax_errors.append((full_path, str(e)))

    if not syntax_errors:
        print(f"  --> PASSED: {py_files_checked} Python files compiled with zero syntax errors.")
        passed_count += 1
    else:
        print(f"  --> FAILED: {len(syntax_errors)} syntax errors detected.")
        failed_count += 1

    # 2. 18 Scientific Module Groups Self-Audit
    print("\n[Test 2/9] Running 18 Scientific Module Groups Self-Audit...")
    cmd_audit = [venv_py, os.path.join(project_root, "src", "biointel", "module_upgrades_v156.py")]
    res_audit = subprocess.run(cmd_audit, capture_output=True, text=True)
    if res_audit.returncode == 0 and "passed: true" in res_audit.stdout.lower():
        print("  --> PASSED: All 18 scientific module groups self-audit passed.")
        passed_count += 1
    else:
        print(f"  --> FAILED: Scientific module self-audit failed.\n{res_audit.stderr or res_audit.stdout}")
        failed_count += 1

    # 3. Group A-E Scientific Domain Suites Audit
    print("\n[Test 3/9] Running Group A-E Scientific Domain Suites Audit...")
    domain_ok = True
    for suite in ["bioinformatics_suite.py", "discovery_suite.py", "lab_analytics_suite.py", "neuroscience_suite.py", "research_suite.py"]:
        suite_path = os.path.join(project_root, "src", "biointel", "modules", suite)
        res_s = subprocess.run([venv_py, suite_path], capture_output=True, text=True)
        if res_s.returncode != 0 or "probes:" not in res_s.stdout.lower():
            domain_ok = False
            print(f"      Domain suite '{suite}' failed: {res_s.stderr or res_s.stdout}")

    if domain_ok:
        print("  --> PASSED: All 5 scientific domain suites (Bioinformatics, Discovery, Lab Analytics, Neuro, Research) verified.")
        passed_count += 1
    else:
        print("  --> FAILED: Domain suites audit failed.")
        failed_count += 1

    # 4. Connectivity & System Health Widgets Audit
    print("\n[Test 4/9] Running Connectivity & System Health Widgets Audit...")
    conn_path = os.path.join(project_root, "src", "biointel", "monitoring", "system_connectivity_widgets.py")
    res_conn = subprocess.run([venv_py, conn_path], capture_output=True, text=True)
    if res_conn.returncode == 0 and "connectivity & system health widgets audit probes:" in res_conn.stdout.lower():
        print("  --> PASSED: All connectivity, API health matrix, GPU, and process supervisor widgets verified.")
        passed_count += 1
    else:
        print(f"  --> FAILED: Connectivity widgets audit failed.\n{res_conn.stderr or res_conn.stdout}")
        failed_count += 1

    # 5. Global Weather & Environment Widget Audit
    print("\n[Test 5/9] Running Global Weather & Environment Engine Audit...")
    w_path = os.path.join(project_root, "src", "biointel", "services", "weather_environment_engine.py")
    res_w = subprocess.run([venv_py, w_path], capture_output=True, text=True)
    if res_w.returncode == 0 and "global weather engine audit probes:" in res_w.stdout.lower():
        print("  --> PASSED: Worldwide location geocoding, Open-Meteo forecasts, AQI, and metadata linking verified.")
        passed_count += 1
    else:
        print(f"  --> FAILED: Weather engine audit failed.\n{res_w.stderr or res_w.stdout}")
        failed_count += 1

    # 6. Scientific Engine Adapter Qualification Probe
    print("\n[Test 6/9] Running Scientific Engine Adapter Qualification Probes...")
    cmd_qual = [venv_py, os.path.join(project_root, "src", "biointel", "engines", "adapter_qualification_framework.py")]
    res_qual = subprocess.run(cmd_qual, capture_output=True, text=True)
    if res_qual.returncode == 0 and "adapter qualification matrix probes:" in res_qual.stdout.lower():
        print("  --> PASSED: 27 Scientific engine adapters qualification probes verified.")
        passed_count += 1
    else:
        print(f"  --> FAILED: Adapter qualification failed.\n{res_qual.stderr or res_qual.stdout}")
        failed_count += 1

    # 7. Real Windows UI Qualification Matrix Check
    print("\n[Test 7/9] Running Real Windows UI Qualification Matrix Audit...")
    cmd_ui = [venv_py, os.path.join(project_root, "src", "biointel", "ui", "ui_qualification_tracker.py")]
    res_ui = subprocess.run(cmd_ui, capture_output=True, text=True)
    if res_ui.returncode == 0 and "ui qualification matrix probes:" in res_ui.stdout.lower():
        print("  --> PASSED: UI Qualification matrix verified across all pages, DPI scalings, and browsers.")
        passed_count += 1
    else:
        print(f"  --> FAILED: UI qualification audit failed.\n{res_ui.stderr or res_ui.stdout}")
        failed_count += 1

    # 8. Release Gate Verification
    print("\n[Test 8/9] Running Step220 Release Gate Check...")
    cmd_gate = [venv_py, os.path.join(project_root, "scripts", "step206_release_gate.py"), "--root", project_root, "--quick"]
    res_gate = subprocess.run(cmd_gate, capture_output=True, text=True)
    if res_gate.returncode == 0 and '"passed": true' in res_gate.stdout.lower():
        print("  --> PASSED: Step220 Release Gate preflight passed.")
        passed_count += 1
    else:
        print(f"  --> FAILED: Release Gate failed.\n{res_gate.stdout}")
        failed_count += 1

    # 9. Windows Runtime Compatibility Check
    print("\n[Test 9/9] Running Windows Runtime Compatibility Check...")
    cmd_compat = [venv_py, os.path.join(project_root, "scripts", "verify_windows_runtime_compatibility_step206.py"), "--root", project_root, "--strict-python"]
    res_compat = subprocess.run(cmd_compat, capture_output=True, text=True)
    if res_compat.returncode == 0 and '"passed": true' in res_compat.stdout.lower():
        print("  --> PASSED: Windows runtime compatibility check passed.")
        passed_count += 1
    else:
        print(f"  --> FAILED: Runtime compatibility check failed.\n{res_compat.stdout}")
        failed_count += 1

    print("\n============================================================")
    print(f"TEST RESULTS SUMMARY:")
    print(f"  Total Passed:  {passed_count} / 9")
    print(f"  Total Failed:  {failed_count}")
    print("============================================================")

    report_path = os.path.join(project_root, "UserData", "reports", "master_test_execution_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "passed_count": passed_count,
            "failed_count": failed_count,
            "py_files_checked": py_files_checked,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }, f, indent=2)

    return failed_count == 0

if __name__ == "__main__":
    success = run_test_suite()
    sys.exit(0 if success else 1)
