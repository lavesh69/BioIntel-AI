from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
from typing import Any

import pandas as pd

from biointel.database.core import managed_connect
from .catalog import engine_catalog, licence_catalog, reference_catalog


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_tree(path: Path) -> tuple[str, int, int]:
    digest = sha256()
    total = 0
    count = 0
    for item in sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink()):
        rel = item.relative_to(path).as_posix()
        file_hash = _sha256_file(item)
        size = item.stat().st_size
        digest.update(f"{rel}\0{file_hash}\0{size}\n".encode())
        total += size
        count += 1
    return digest.hexdigest(), total, count


def fingerprint(path: str | Path) -> dict[str, Any]:
    value = Path(path).expanduser().resolve()
    if value.is_file():
        return {"kind": "file", "sha256": _sha256_file(value), "size_bytes": value.stat().st_size, "file_count": 1}
    if value.is_dir():
        digest, total, count = _sha256_tree(value)
        return {"kind": "directory", "sha256": digest, "size_bytes": total, "file_count": count}
    raise FileNotFoundError(value)


def _run(command: list[str], *, timeout: int = 90, cwd: Path | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=timeout, cwd=cwd, check=False)
        return {"return_code": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"return_code": 127, "stdout": "", "stderr": str(exc)}


def _first_executable(smoke: str) -> str:
    return str(smoke or "").split(",", 1)[0].strip()


def probe_engines() -> pd.DataFrame:
    rows = []
    for item in engine_catalog().to_dict(orient="records"):
        exe = _first_executable(str(item.get("smoke_test") or ""))
        path = shutil.which(exe) if exe else None
        command = [part.strip() for part in str(item.get("smoke_test") or "").split(",") if part.strip()]
        result = _run(command) if path and command else {"return_code": 127, "stdout": "", "stderr": "not installed"}
        license_path = ""
        license_sha = ""
        if path:
            candidate_roots = [Path(path).resolve().parent.parent / "share" / "licenses", Path(path).resolve().parent.parent / "info" / "licenses"]
            for root in candidate_roots:
                if root.is_dir():
                    candidates = [p for p in root.rglob("*") if p.is_file() and re.search(r"licen[cs]e|copying", p.name, re.I)]
                    if candidates:
                        license_path = str(candidates[0])
                        license_sha = _sha256_file(candidates[0])
                        break
        rows.append({
            **item,
            "installed": bool(path and result["return_code"] == 0),
            "executable_detected": bool(path),
            "detected_path": path or "",
            "smoke_test_passed": result["return_code"] == 0,
            "smoke_stdout": result["stdout"],
            "smoke_stderr": result["stderr"],
            "executable_sha256": _sha256_file(Path(path)) if path and Path(path).is_file() else "",
            "licence_text_path": license_path,
            "licence_text_sha256": license_sha,
            "licence_capture_complete": bool(license_sha),
            "qualified": bool(path and result["return_code"] == 0 and license_sha),
        })
    return pd.DataFrame(rows)


def _check_schema(path: Path, checks: list[str]) -> dict[str, Any]:
    failures: list[str] = []
    if not path.exists():
        return {"passed": False, "failures": ["path missing"]}
    name = path.name.lower()
    if "gzip" in checks and not (name.endswith(".gz") or name.endswith(".bgz")):
        failures.append("expected gzip extension")
    if "vcf" in checks and path.is_file():
        import gzip
        opener = gzip.open if name.endswith(".gz") else open
        try:
            with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
                header = "".join(handle.readline() for _ in range(20))
            if "##fileformat=VCF" not in header:
                failures.append("VCF header missing")
        except OSError as exc:
            failures.append(f"VCF read failed: {exc}")
    if "fasta" in checks and path.is_file():
        import gzip
        opener = gzip.open if name.endswith(".gz") else open
        try:
            with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
                first = handle.readline()
            if not first.startswith(">"):
                failures.append("FASTA header missing")
        except OSError as exc:
            failures.append(f"FASTA read failed: {exc}")
    if "obo" in checks and path.is_file():
        text = path.read_text(encoding="utf-8", errors="replace")[:10000]
        if "format-version:" not in text or "[Term]" not in text:
            failures.append("OBO structure missing")
    if "json" in checks and path.is_file():
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"JSON invalid: {exc}")
    return {"passed": not failures, "failures": failures}


class Step170Registry:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or (self.root / "UserData")).resolve()
        self.state = user_data / "step170"
        self.downloads = self.state / "downloads"
        self.references = self.state / "references"
        self.licenses = self.state / "licenses"
        self.db_path = self.state / "runtime_reference_qualification.sqlite3"
        for path in (self.state, self.downloads, self.references, self.licenses):
            path.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = managed_connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def _init(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS licence_acknowledgements(
                    licence_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    terms_url TEXT NOT NULL DEFAULT '',
                    accepted INTEGER NOT NULL DEFAULT 0,
                    accepted_by TEXT NOT NULL DEFAULT '',
                    accepted_at_utc TEXT NOT NULL DEFAULT '',
                    licence_text_path TEXT NOT NULL DEFAULT '',
                    licence_text_sha256 TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS engine_qualifications(
                    engine TEXT PRIMARY KEY,
                    installed INTEGER NOT NULL DEFAULT 0,
                    detected_path TEXT NOT NULL DEFAULT '',
                    detected_version TEXT NOT NULL DEFAULT '',
                    executable_sha256 TEXT NOT NULL DEFAULT '',
                    smoke_test_passed INTEGER NOT NULL DEFAULT 0,
                    package_provenance_json TEXT NOT NULL DEFAULT '{}',
                    licence_id TEXT NOT NULL,
                    licence_text_sha256 TEXT NOT NULL DEFAULT '',
                    golden_fixture_passed INTEGER NOT NULL DEFAULT 0,
                    negative_control_passed INTEGER NOT NULL DEFAULT 0,
                    qualified INTEGER NOT NULL DEFAULT 0,
                    qualified_at_utc TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(licence_id) REFERENCES licence_acknowledgements(licence_id)
                );
                CREATE TABLE IF NOT EXISTS reference_qualifications(
                    reference_id TEXT PRIMARY KEY,
                    release_id TEXT NOT NULL DEFAULT '',
                    local_path TEXT NOT NULL DEFAULT '',
                    local_sha256 TEXT NOT NULL DEFAULT '',
                    provider_checksum TEXT NOT NULL DEFAULT '',
                    provider_checksum_verified INTEGER NOT NULL DEFAULT 0,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    file_count INTEGER NOT NULL DEFAULT 0,
                    licence_id TEXT NOT NULL,
                    schema_validation_passed INTEGER NOT NULL DEFAULT 0,
                    scientific_reviewer TEXT NOT NULL DEFAULT '',
                    qualified INTEGER NOT NULL DEFAULT 0,
                    qualified_at_utc TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(licence_id) REFERENCES licence_acknowledgements(licence_id)
                );
                CREATE TABLE IF NOT EXISTS qualification_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL
                );
                """
            )
            for row in licence_catalog().to_dict(orient="records"):
                con.execute(
                    "INSERT OR IGNORE INTO licence_acknowledgements(licence_id,label,terms_url,notes) VALUES(?,?,?,?)",
                    (row["licence_id"], row["label"], row["terms_url"], row.get("notes", "")),
                )
            con.commit()

    def accept_licence(self, licence_id: str, *, accepted_by: str, licence_text_path: str | Path | None = None, notes: str = "") -> dict[str, Any]:
        if not accepted_by.strip():
            raise ValueError("accepted_by is required")
        path = Path(licence_text_path).resolve() if licence_text_path else None
        digest = _sha256_file(path) if path and path.is_file() else ""
        with self._connect() as con:
            row = con.execute("SELECT licence_id FROM licence_acknowledgements WHERE licence_id=?", (licence_id,)).fetchone()
            if row is None:
                raise KeyError(licence_id)
            con.execute(
                "UPDATE licence_acknowledgements SET accepted=1,accepted_by=?,accepted_at_utc=?,licence_text_path=?,licence_text_sha256=?,notes=? WHERE licence_id=?",
                (accepted_by.strip(), _now(), str(path or ""), digest, notes, licence_id),
            )
            con.commit()
        return {"licence_id": licence_id, "accepted": True, "accepted_by": accepted_by, "licence_text_sha256": digest}

    def register_reference(self, reference_id: str, path: str | Path, *, release_id: str, provider_checksum: str = "", scientific_reviewer: str = "") -> dict[str, Any]:
        catalog = reference_catalog().set_index("reference_id")
        if reference_id not in catalog.index:
            raise KeyError(reference_id)
        item = catalog.loc[reference_id].to_dict()
        target = Path(path).resolve()
        fp = fingerprint(target)
        checks = [v.strip() for v in str(item["schema_checks"]).split(",") if v.strip()]
        schema = _check_schema(target, checks)
        provider_checksum = provider_checksum.lower().strip()
        provider_verified = False
        if provider_checksum:
            if ":" in provider_checksum:
                algorithm, expected = provider_checksum.split(":", 1)
            else:
                algorithm, expected = ("sha256", provider_checksum)
            if algorithm in {"sha256", "md5"} and target.is_file():
                digest = __import__("hashlib").new(algorithm)
                with target.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                        digest.update(chunk)
                provider_verified = digest.hexdigest() == expected
        with self._connect() as con:
            licence = con.execute("SELECT accepted FROM licence_acknowledgements WHERE licence_id=?", (item["licence_id"],)).fetchone()
            accepted = bool(licence and licence[0])
            qualified = bool(release_id.strip() and accepted and schema["passed"] and (provider_verified or not item["provider_checksum_available"]) and scientific_reviewer.strip())
            con.execute(
                """INSERT INTO reference_qualifications(reference_id,release_id,local_path,local_sha256,provider_checksum,provider_checksum_verified,size_bytes,file_count,licence_id,schema_validation_passed,scientific_reviewer,qualified,qualified_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(reference_id) DO UPDATE SET release_id=excluded.release_id,local_path=excluded.local_path,local_sha256=excluded.local_sha256,provider_checksum=excluded.provider_checksum,provider_checksum_verified=excluded.provider_checksum_verified,size_bytes=excluded.size_bytes,file_count=excluded.file_count,licence_id=excluded.licence_id,schema_validation_passed=excluded.schema_validation_passed,scientific_reviewer=excluded.scientific_reviewer,qualified=excluded.qualified,qualified_at_utc=excluded.qualified_at_utc""",
                (reference_id, release_id.strip(), str(target), fp["sha256"], provider_checksum, int(provider_verified), fp["size_bytes"], fp["file_count"], item["licence_id"], int(schema["passed"]), scientific_reviewer.strip(), int(qualified), _now() if qualified else ""),
            )
            con.execute("INSERT INTO qualification_events(kind,subject_id,status,details_json,created_at_utc) VALUES(?,?,?,?,?)", ("reference", reference_id, "qualified" if qualified else "blocked", json.dumps({"schema": schema, "fingerprint": fp}), _now()))
            con.commit()
        return {"reference_id": reference_id, "qualified": qualified, "fingerprint": fp, "schema": schema, "licence_accepted": accepted, "provider_checksum_verified": provider_verified}

    def status(self) -> dict[str, Any]:
        with self._connect() as con:
            engines = con.execute(
                "SELECT COUNT(*),SUM(installed),SUM(qualified) FROM engine_qualifications"
            ).fetchone()
            refs = con.execute(
                "SELECT COUNT(*),SUM(CASE WHEN local_path <> '' THEN 1 ELSE 0 END),SUM(qualified) FROM reference_qualifications"
            ).fetchone()
            licences = con.execute("SELECT COUNT(*),SUM(accepted) FROM licence_acknowledgements").fetchone()
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
        return {
            "schema": "biointel.step170.registry-status.v1",
            "database_integrity": integrity,
            "foreign_key_violations": len(fk),
            "engines_registered": int(engines[0] or 0),
            "engines_installed": int(engines[1] or 0),
            "engines_qualified": int(engines[2] or 0),
            "references_registered": int(refs[0] or 0),
            "references_downloaded": int(refs[1] or 0),
            "references_qualified": int(refs[2] or 0),
            "licences_registered": int(licences[0] or 0),
            "licences_accepted": int(licences[1] or 0),
        }


def qualification_matrix(root: str | Path) -> pd.DataFrame:
    registry = Step170Registry(root)
    db = registry.db_path
    with managed_connect(db) as con:
        engine_rows = {row[0]: dict(zip([d[0] for d in con.execute("SELECT * FROM engine_qualifications LIMIT 0").description], row)) for row in con.execute("SELECT * FROM engine_qualifications")}
        ref_rows = {row[0]: dict(zip([d[0] for d in con.execute("SELECT * FROM reference_qualifications LIMIT 0").description], row)) for row in con.execute("SELECT * FROM reference_qualifications")}
    rows = []
    for item in engine_catalog().to_dict(orient="records"):
        state = engine_rows.get(item["engine"], {})
        installed = bool(state.get("installed", 0))
        qualified = bool(state.get("qualified", 0))
        rows.append(
            {
                "kind": "engine",
                "id": item["engine"],
                "label": item["label"],
                "installed": installed,
                "smoke_test_passed": bool(state.get("smoke_test_passed", 0)),
                "qualified": qualified,
                "qualification_state": "qualified" if qualified else ("installed-awaiting-qualification" if installed else "not-installed"),
                "licence_id": item["licence_id"],
                "route": item["install_route"],
                "detail": state.get("detected_version", ""),
            }
        )
    for item in reference_catalog().to_dict(orient="records"):
        state = ref_rows.get(item["reference_id"], {})
        downloaded = bool(str(state.get("local_path", "")).strip())
        qualified = bool(state.get("qualified", 0))
        rows.append(
            {
                "kind": "reference",
                "id": item["reference_id"],
                "label": item["label"],
                "downloaded": downloaded,
                "schema_validation_passed": bool(state.get("schema_validation_passed", 0)),
                "qualified": qualified,
                "qualification_state": "qualified" if qualified else ("downloaded-awaiting-qualification" if downloaded else "not-downloaded"),
                "licence_id": item["licence_id"],
                "route": item["download_strategy"],
                "detail": state.get("release_id", ""),
            }
        )
    return pd.DataFrame(rows)


__all__ = ["Step170Registry", "fingerprint", "probe_engines", "qualification_matrix"]
