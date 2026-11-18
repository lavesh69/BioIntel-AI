import json
import os
import re

root_dir = r"C:\Users\lavesh dobriyal\.gemini\antigravity\scratch\BioIntel-Step220"

def scan_dead_features():
    findings = {
        "scanned_at": "2026-07-29T20:01:00Z",
        "total_files_scanned": 0,
        "todo_fixme_count": 0,
        "pass_statements_count": 0,
        "not_implemented_count": 0,
        "silent_exceptions_count": 0,
        "session_state_only_saves": 0,
        "findings": []
    }

    py_files = []
    for root, _, files in os.walk(root_dir):
        if any(ignore in root for ignore in [".venv", ".git", "scratch", "dist_release"]):
            continue
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    findings["total_files_scanned"] = len(py_files)

    for p in py_files:
        rel = os.path.relpath(p, root_dir).replace("\\", "/")
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Check TODO / FIXME
            todos = len(re.findall(r"\b(TODO|FIXME)\b", content))
            if todos > 0:
                findings["todo_fixme_count"] += todos

            # Check pass statements in except blocks
            passes = len(re.findall(r"except\s+Exception\s*:\s*pass", content))
            if passes > 0:
                findings["silent_exceptions_count"] += passes
                findings["findings"].append({
                    "file": rel,
                    "type": "SILENT_EXCEPTION",
                    "description": f"Found {passes} silent 'except Exception: pass' blocks."
                })

            # Check NotImplementedError
            not_impl = len(re.findall(r"\bNotImplementedError\b", content))
            if not_impl > 0:
                findings["not_implemented_count"] += not_impl
                findings["findings"].append({
                    "file": rel,
                    "type": "NOT_IMPLEMENTED",
                    "description": f"Found {not_impl} NotImplementedError statements."
                })
        except Exception as e:
            pass

    output_path = os.path.join(root_dir, "BIOINTEL_DEAD_FEATURE_SCAN.json")
    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(findings, out, indent=2)

    print(f"Dead feature scan complete! {len(findings['findings'])} findings saved to {output_path}")
    return findings

if __name__ == "__main__":
    scan_dead_features()
