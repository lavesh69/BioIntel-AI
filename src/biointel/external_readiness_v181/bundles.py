from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

from .catalog import PROFILES
from .manifests import validate_manifest


@dataclass(frozen=True)
class ImportResult:
    imported: bool
    module_key: str
    evidence_id: str
    destination: str
    blockers: tuple[str, ...]


def _safe_members(archive: zipfile.ZipFile) -> tuple[list[zipfile.ZipInfo], list[str]]:
    safe: list[zipfile.ZipInfo] = []
    blockers: list[str] = []
    for info in archive.infolist():
        pure = PurePosixPath(info.filename.replace("\\", "/"))
        if info.is_dir():
            continue
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            blockers.append(f"unsafe archive path: {info.filename}")
            continue
        if info.file_size > 5 * 1024 * 1024 * 1024:
            blockers.append(f"archive member exceeds 5 GiB safety limit: {info.filename}")
            continue
        safe.append(info)
    return safe, blockers


def import_bundle(root: str | Path, bundle: str | Path, module_key: str, evidence_id: str) -> ImportResult:
    project = Path(root).resolve()
    bundle_path = Path(bundle).resolve()
    blockers: list[str] = []
    if module_key not in PROFILES:
        return ImportResult(False, module_key, evidence_id, "", ("unknown module_key",))
    requirement = next((item for item in PROFILES[module_key].requirements if item.evidence_id == evidence_id), None)
    if requirement is None:
        return ImportResult(False, module_key, evidence_id, "", ("unknown evidence_id for module",))
    if not bundle_path.is_file():
        return ImportResult(False, module_key, evidence_id, "", ("bundle file does not exist",))
    destination = project / "UserData" / "step181" / "evidence" / module_key / evidence_id
    with tempfile.TemporaryDirectory(prefix="biointel-step181-") as temporary:
        temp = Path(temporary)
        try:
            with zipfile.ZipFile(bundle_path) as archive:
                members, archive_blockers = _safe_members(archive)
                blockers.extend(archive_blockers)
                if blockers:
                    return ImportResult(False, module_key, evidence_id, str(destination), tuple(blockers))
                for info in members:
                    archive.extract(info, temp)
        except (OSError, zipfile.BadZipFile) as exc:
            return ImportResult(False, module_key, evidence_id, str(destination), (f"cannot read evidence bundle: {exc}",))
        roots = [path.parent for path in temp.rglob("qualification_manifest.json")]
        if len(roots) != 1:
            return ImportResult(False, module_key, evidence_id, str(destination), ("bundle must contain exactly one qualification_manifest.json",))
        source = roots[0]
        manifest = validate_manifest(source, module_key, requirement)
        if not manifest.passed:
            return ImportResult(False, module_key, evidence_id, str(destination), manifest.blockers)
        backup = destination.with_name(destination.name + ".backup")
        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            destination.rename(backup)
        try:
            shutil.copytree(source, destination)
        except Exception:
            if destination.exists():
                shutil.rmtree(destination)
            if backup.exists():
                backup.rename(destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    return ImportResult(True, module_key, evidence_id, str(destination), ())


__all__ = ["ImportResult", "import_bundle"]
