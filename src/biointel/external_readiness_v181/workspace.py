from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .catalog import PROFILES, TARGET_MODULES
from .validators import VALIDATORS


HEADERS: dict[str, tuple[str, ...]] = {key: columns for key, (columns, _) in VALIDATORS.items()}


def _empty_manifest(module_key: str, evidence_id: str, title: str, data_file: str | None) -> dict[str, Any]:
    files = [] if data_file is None else [{"path": data_file, "sha256": "REPLACE_WITH_SHA256_AFTER_ADDING_REAL_DATA"}]
    return {
        "schema": "biointel.step181.evidence-manifest.v1",
        "module_key": module_key,
        "evidence_id": evidence_id,
        "evidence_title": title,
        "source_organization": "",
        "source_contact": "",
        "acquisition_date": "",
        "licence_or_permission": "",
        "provenance_record": "",
        "real_world_evidence": False,
        "synthetic_or_demo": False,
        "independent_from_development_team": False,
        "deidentified_or_nonhuman": False,
        "reviewer_name": "",
        "reviewer_role": "",
        "review_signed": False,
        "review_date": "",
        "files": files,
        "notes": "Do not mark qualified until real evidence, permissions and reviewer approval are complete.",
    }


def build_workspaces(root: str | Path) -> dict[str, object]:
    project = Path(root).resolve()
    base = project / "UserData" / "step181" / "evidence"
    created: list[str] = []
    for module_key in TARGET_MODULES:
        profile = PROFILES[module_key]
        for requirement in profile.requirements:
            folder = base / module_key / requirement.evidence_id
            folder.mkdir(parents=True, exist_ok=True)
            manifest = folder / "qualification_manifest.json"
            if not manifest.exists():
                manifest.write_text(
                    json.dumps(_empty_manifest(module_key, requirement.evidence_id, requirement.title, requirement.data_file), indent=2) + "\n",
                    encoding="utf-8",
                )
                created.append(str(manifest.relative_to(project)))
            if requirement.data_file:
                data_path = folder / requirement.data_file
                if not data_path.exists():
                    headers = HEADERS[requirement.validator]
                    data_path.write_text(",".join(headers) + "\n", encoding="utf-8")
                    created.append(str(data_path.relative_to(project)))
            readme = folder / "README.md"
            if not readme.exists():
                readme.write_text(
                    f"# {requirement.title}\n\n"
                    f"Module: **{profile.title}**\n\n"
                    f"{requirement.description}\n\n"
                    f"Acceptance: {requirement.acceptance_summary}\n\n"
                    "## Qualification rules\n\n"
                    "- Use real, permissioned evidence only.\n"
                    "- Keep `synthetic_or_demo` false.\n"
                    "- Add every evidence file to `files` with its SHA-256.\n"
                    "- Complete source, licence/permission, provenance and reviewer fields.\n"
                    "- Run `VERIFY_STEP181_EXTERNAL_EVIDENCE_WINDOWS.bat`.\n",
                    encoding="utf-8",
                )
                created.append(str(readme.relative_to(project)))
    inbox = project / "UserData" / "step181" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    index = {
        "schema": "biointel.step181.external-evidence-workspace.v1",
        "module_count": len(TARGET_MODULES),
        "evidence_pack_count": sum(len(PROFILES[key].requirements) for key in TARGET_MODULES),
        "base": str(base),
        "created_files": created,
    }
    (project / "data" / "step181").mkdir(parents=True, exist_ok=True)
    (project / "data" / "step181" / "workspace_index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return index


def write_sha256(path: str | Path) -> str:
    target = Path(path)
    digest = sha256(target.read_bytes()).hexdigest()
    return digest


__all__ = ["HEADERS", "build_workspaces", "write_sha256"]
