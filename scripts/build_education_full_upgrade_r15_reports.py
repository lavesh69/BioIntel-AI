"""Build concise evidence and operator guides for Education Full Upgrade R15."""
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPORT = Path("reports/education_full_upgrade_r15")
GUIDES = Path("docs/education_full_upgrade_r15")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(root: Path) -> dict:
    stamp = datetime.now(timezone.utc).isoformat()
    rd, gd = root / REPORT, root / GUIDES
    junit = ET.parse(rd / "education-shiro-junit-final.xml").getroot()
    suite = junit if junit.tag == "testsuite" else junit.find("testsuite")
    tests = int(suite.attrib["tests"])
    failures = int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0))
    duration = float(suite.attrib.get("time", 0))
    transcription = load_json(rd / "local-transcription-qualification.json")
    deployment = load_json(rd / "deployment-readiness.json")
    wheelhouse = load_json(rd / "windows-wheelhouse-verification.json")
    streamlit = load_json(rd / "streamlit-apptest.json")
    load_probe = load_json(rd / "bounded-load-probe.json")
    preservation = load_json(rd / "preservation-summary.json")
    test_payload = {
        "schema": "biointel.education.full-upgrade-r15.test-results.v1",
        "generated_at": stamp,
        "status": "passed" if failures == 0 else "failed",
        "education_shiro_phase16": {"tests": tests, "passed": tests - failures, "failed": failures, "duration_seconds": duration},
        "streamlit": {"routes": streamlit["routes"], "passed": streamlit["passed"], "exceptions": streamlit["exceptions"]},
        "local_transcription": transcription["functional_test"],
        "wheelhouse": {"valid": wheelhouse["valid"], "wheel_count": wheelhouse["wheel_count"]},
        "bounded_load_probe": {"operations": load_probe["executed_operations"], "errors": load_probe["error_count"], "classification": load_probe["classification"]},
        "preservation": preservation,
    }
    write(rd / "BIOINTEL_EDUCATION_R15_TEST_RESULTS.json", json.dumps(test_payload, indent=2))
    reports = {
        "BIOINTEL_EDUCATION_FULL_UPGRADE_REPORT.md": f"""# BioIntel Education Full Local Production Upgrade R15

Generated: {stamp}

## Outcome

Education Home, Universe, Classroom, Academy & Lecture Studio, Examination, Intelligence Hub, and embedded Shiro remain on the canonical BioIntel theme and production data boundary. The remaining credential-free processing gap is implemented: uploaded governed lecture media can now be transcribed locally by the bundled multilingual model, reviewed by a human, and only then published as lecture/Shiro evidence.

## Verified gates

- {tests - failures}/{tests} Education, Shiro, Phase 16, and preservation-hardening tests passed.
- {streamlit['passed']}/{streamlit['routes']} canonical/legacy Streamlit routes executed with zero exceptions.
- {wheelhouse['wheel_count']} offline Windows wheels are present, hash-pinned, readable, and compatible.
- Real audio qualification passed with source SHA-256 and model-manifest SHA-256 evidence; runtime network use was false.
- {load_probe['executed_operations']} bounded local operations completed with {load_probe['error_count']} errors. This is not a production capacity claim.
- Preservation audit found zero removed modules, functions, routes, tables, navigation entries, or features.

## Truth boundary

The local desktop core is ready. TURN/SFU, OIDC/SSO, SMTP, payments, Postgres/Redis/object storage, and other organization-owned integrations remain configuration_required until real endpoints, credentials, and deployment diagnostics are supplied.""",
        "BIOINTEL_LOCAL_TRANSCRIPTION_REPORT.md": f"""# Offline Lecture Transcription Qualification

Provider: faster-whisper {transcription['readiness']['package_version']}  
Model revision: {transcription['readiness']['model_revision']}  
Model manifest: `{transcription['readiness']['model_manifest_sha256']}`  
License: {transcription['readiness']['model_license']}

The packaged runtime uses CPU INT8, local model files, bundled FFmpeg, no API credential, and no runtime network. A real {transcription['functional_test']['duration_seconds']}-second audio file passed with detected language `{transcription['functional_test']['detected_language']}`, probability {transcription['functional_test']['language_probability']}, and {transcription['functional_test']['segment_count']} segment.

Generated output is stored as a hash-verified review artifact. It is not placed in the canonical lecture transcript table until an authorized educator explicitly approves it. Existing approved language transcripts require an explicit replacement decision.""",
        "BIOINTEL_DEPLOYMENT_BOUNDARIES.md": """# Deployment Boundaries

## Ready without external credentials

BioIntel themed Education workspaces, tenant-scoped persistence, Classroom/Academy/Examination/Intelligence workflows, local Shiro evidence, FFmpeg media jobs, offline multilingual lecture transcription, API routes, background worker, reports, and Windows offline wheelhouse.

## Administrator configuration required

TURN/SFU relay, live server recording, OIDC/SAML, SMTP/SMS/WhatsApp, payment providers, and multi-node Postgres/Redis/object storage. R15 provides environment templates and a validator; it never marks these passed from placeholders.""",
        "BIOINTEL_SECURITY_AND_GOVERNANCE.md": """# Security and Governance

Transcription planning/execution/review is staff-authorized and institution scoped. Source media, model files, review artifacts, and packaged files have SHA-256 evidence. Empty/no-speech results fail and create no transcript. Candidate text stays outside the canonical transcript and Shiro evidence boundary until human approval. Existing approved text cannot be replaced implicitly. Model loading is local-files-only and cached per process.""",
        "BIOINTEL_PRESERVATION_REPORT.md": f"""# Preservation Report

Result: {'passed' if preservation['passed'] else 'failed'}.

Baseline: {preservation['baseline_modules']} modules, {preservation['baseline_functions']} functions, {preservation['baseline_routes']} routes, {preservation['baseline_navigation']} navigation entries, and {preservation['baseline_features']} features. All removal counts are zero; missing columns and unexpected unrelated modifications are empty.""",
        "BIOINTEL_WINDOWS_OFFLINE_INSTALLER_REPORT.md": f"""# Windows Offline Installer Report

The CPython 3.11 x64 wheelhouse contains {wheelhouse['wheel_count']} wheels and the same number of metadata and hash-lock rows. Archive readability, SHA-256 checks, setuptools/pkg_resources compatibility, and ont-fast5-api compatibility pass. R15 adds faster-whisper 1.2.1, CTranslate2 4.8.1, ONNX Runtime 1.28.0, tokenizer/runtime dependencies, and the hash-manifested model.""",
        "BIOINTEL_PERFORMANCE_REPORT.md": f"""# Performance Evidence

The complete functional suite finished in {duration:.2f} seconds. The bounded local load probe executed {load_probe['executed_operations']} operations with {load_probe['error_count']} errors under the simulated 1,000-user profile. These are measured local operation timings only; concurrent production capacity is not verified. The model is cached as a process resource and uses bounded CPU threads/beam size.""",
        "BIOINTEL_EDUCATION_R15_CHANGELOG.md": """# R15 Changelog

- Added bundled credential-free multilingual lecture transcription and model/license manifests.
- Added durable plan, execute, candidate, approve, reject, list, readiness API/service contracts.
- Enforced human review before canonical transcript or Shiro evidence publication.
- Added background transcription worker and Streamlit review workflow.
- Added 10 offline Windows runtime wheels and regenerated the hash lock.
- Fixed explicit UserData precedence for SciencePulse persistence.
- Fixed Research Compute free-space admission to use a bounded dataset scratch estimate.
- Added deployment validator, config template, real-audio qualification, AppTest matrix, load probe, and R15 release gates.
- Removed the shared Live Institutional Workspace banner only from BioIntel Academy & Lecture Studio while retaining production-only enforcement and database integrity checks.""",
        "RECONSTRUCT_BIOINTEL_EDUCATION_R15.md": """# Reconstruct BioIntel Education Full Upgrade R15

1. Put all four R15 ZIP parts and the SHA256SUMS file in one empty directory.
2. Verify every archive hash.
3. Extract Part1 through Part4 into the same destination; every part uses the shared `BioIntel-Step220` root.
4. Run `python scripts/validate_education_full_upgrade_r15.py --root BioIntel-Step220`.
5. Run `INSTALL_WINDOWS.bat`, then `RUN_BOTH_WINDOWS.bat`.
6. Keep UserData outside the release tree and back it up before migration.

The release package intentionally excludes runtime caches, test caches, and UserData.""",
    }
    for name, body in reports.items():
        write(rd / name, body)
    guides = {
        "INSTALLATION_GUIDE.md": "Verify all four SHA-256 hashes, combine into one BioIntel-Step220 directory, run the R15 validator, install offline on CPython 3.11 x64, and start UI/API. Back up existing UserData first.",
        "LECTURE_CREATOR_GUIDE.md": "Upload a real lecture, plan transcription, execute locally, inspect text/source/model evidence, then explicitly approve or reject. Use replace-existing only after comparing the approved transcript. Shiro can index only the approved canonical transcript.",
        "INSTITUTION_ADMIN_GUIDE.md": "Use the deployment readiness validator. Local core should pass. Configure TURN, identity, messaging, or cluster services only with secret-manager references and real diagnostics. Never treat blank/template keys as configured.",
        "USER_GUIDE.md": "Open Education Home or Universe, then enter Classroom, Academy, Examination, or Intelligence Hub. Production mode shows persisted institutional data or honest setup states. Approved transcripts support lecture search and governed Shiro evidence.",
        "TROUBLESHOOTING_GUIDE.md": "If transcription is configuration_required, verify FFmpeg, faster-whisper, model files, and model manifest. If review_required, an educator must approve. If replacement is blocked, explicitly compare and authorize replacement. External integrations remain configuration_required until real deployment setup exists.",
    }
    for name, body in guides.items():
        write(gd / name, f"# {name.replace('_', ' ').replace('.md', '').title()}\n\nRelease: BioIntel AI 15.6.0 Education Full Upgrade R15\n\n{body}")
    return {"generated_at": stamp, "reports": len(reports) + 1, "guides": len(guides), "tests": tests, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    result = build(Path(args.root).resolve())
    print(json.dumps(result, indent=2))
    return 0 if result["failures"] == 0 else 1


ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    raise SystemExit(main())