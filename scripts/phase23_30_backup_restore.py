from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.paths import education_paths, user_data_root  # noqa: E402
from biointel.education.phase23_30.schema import MIGRATION_ID  # noqa: E402
from biointel.education.phase23_30.service import (  # noqa: E402
    EducationEnterprisePlatform,
)
from biointel.education.platform import EducationPlatform  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_member(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and not (path.parts and ":" in path.parts[0])
    )


def backup(root: Path, output: Path) -> dict[str, object]:
    root = Path(root)
    if (root / "education.sqlite3").is_file():
        database, media = root / "education.sqlite3", root / "media"
    else:
        database, media = education_paths(root)
    platform = EducationPlatform(database, media)
    service = EducationEnterprisePlatform(platform, root=str(root))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="biointel-p30-backup-") as temp_text:
        temp = Path(temp_text)
        database_copy = temp / "education.sqlite3"
        source = sqlite3.connect(database)
        target = sqlite3.connect(database_copy)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        check = sqlite3.connect(database_copy)
        try:
            quick_check = check.execute("PRAGMA quick_check").fetchone()[0]
            migration = check.execute(
                "SELECT 1 FROM education_migrations WHERE id=?",
                (MIGRATION_ID,),
            ).fetchone()
        finally:
            check.close()
        if quick_check != "ok" or not migration:
            raise RuntimeError("Backup database verification failed.")
        files = [
            {
                "path": "database/education.sqlite3",
                "size_bytes": database_copy.stat().st_size,
                "sha256": sha256_file(database_copy),
            }
        ]
        managed = service.storage
        if managed.is_dir():
            for path in sorted(managed.rglob("*")):
                if path.is_file():
                    relative = Path("media") / path.relative_to(managed)
                    files.append(
                        {
                            "path": relative.as_posix(),
                            "size_bytes": path.stat().st_size,
                            "sha256": sha256_file(path),
                        }
                    )
        manifest = {
            "schema": "biointel.education.phase23-30.backup.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "migration": MIGRATION_ID,
            "database_quick_check": quick_check,
            "files": files,
        }
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(database_copy, "database/education.sqlite3")
            for row in files[1:]:
                source_path = managed / Path(str(row["path"])).relative_to("media")
                archive.write(source_path, str(row["path"]))
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
    return {
        "path": str(output),
        "size_bytes": output.stat().st_size,
        "sha256": sha256_file(output),
        "files": len(files),
        "quick_check": "ok",
    }


def inspect_backup(archive_path: Path) -> dict[str, object]:
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip():
            raise RuntimeError("Backup ZIP CRC verification failed.")
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        if any(not safe_member(name) for name in names) or len(names) != len(set(names)):
            raise RuntimeError("Backup contains unsafe or duplicate paths.")
        if "manifest.json" not in names or "database/education.sqlite3" not in names:
            raise RuntimeError("Backup is incomplete.")
        manifest = json.loads(archive.read("manifest.json"))
        expected = {row["path"]: row for row in manifest["files"]}
        bad = []
        for name, row in expected.items():
            data = archive.read(name)
            if (
                len(data) != int(row["size_bytes"])
                or hashlib.sha256(data).hexdigest() != row["sha256"]
            ):
                bad.append(name)
        if bad:
            raise RuntimeError(f"Backup SHA-256 verification failed for {len(bad)} file(s).")
    return {
        "valid": True,
        "archive": str(archive_path),
        "sha256": sha256_file(archive_path),
        "manifest": manifest,
    }


def restore(root: Path, archive_path: Path, confirmation: str) -> dict[str, object]:
    inspected = inspect_backup(archive_path)
    required = "RESTORE-" + str(inspected["sha256"])[:8].upper()
    if confirmation != required:
        raise RuntimeError(f"Restore confirmation must equal {required}.")
    database, media = education_paths(root)
    platform = EducationPlatform(database, media)
    service = EducationEnterprisePlatform(platform, root=str(root))
    pre_restore = (
        user_data_root(root)
        / "backups"
        / f"pre-restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
    )
    backup(root, pre_restore)
    with tempfile.TemporaryDirectory(prefix="biointel-p30-restore-") as temp_text:
        temp = Path(temp_text)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(temp)
        staged_db = temp / "database" / "education.sqlite3"
        check = sqlite3.connect(staged_db)
        try:
            if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("Staged restore database failed quick_check.")
        finally:
            check.close()
        database.parent.mkdir(parents=True, exist_ok=True)
        replacement = database.with_suffix(".restore-staged")
        shutil.copy2(staged_db, replacement)
        os.replace(replacement, database)
        staged_media = temp / "media"
        if staged_media.is_dir():
            for path in staged_media.rglob("*"):
                if path.is_file():
                    destination = (service.storage / path.relative_to(staged_media)).resolve()
                    if not destination.is_relative_to(service.storage):
                        raise RuntimeError("Restore media path escaped storage.")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, destination)
    verified = EducationEnterprisePlatform(
        EducationPlatform(database, media),
        root=str(root),
    )
    return {
        "restored": verified.db.quick_check(),
        "migration": verified.migrate(),
        "archive": str(archive_path),
        "pre_restore_backup": str(pre_restore),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    command = parser.add_subparsers(dest="command", required=True)
    create = command.add_parser("backup")
    create.add_argument("--output", required=True)
    inspect = command.add_parser("inspect")
    inspect.add_argument("--archive", required=True)
    apply = command.add_parser("restore")
    apply.add_argument("--archive", required=True)
    apply.add_argument("--confirmation", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "backup":
        result = backup(root, Path(args.output).resolve())
    elif args.command == "inspect":
        result = inspect_backup(Path(args.archive).resolve())
    else:
        result = restore(
            root,
            Path(args.archive).resolve(),
            str(args.confirmation),
        )
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
