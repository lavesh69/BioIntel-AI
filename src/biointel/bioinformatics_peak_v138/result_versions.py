from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import gzip

from biointel.database.core import managed_connect
from uuid import uuid4

import pandas as pd


VALID_STATES = ("Draft", "Reviewed", "Locked", "Superseded", "Retracted")


class ResultVersionStore:
    def __init__(self, project_root: str | Path):
        root = Path(project_root).resolve() / "UserData" / "workspace" / "bioinformatics_peak_v140"
        root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "result_versions.sqlite3"
        self.payload_dir = root / "version_payloads"
        self.payload_dir.mkdir(exist_ok=True)
        with managed_connect(self.db_path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS versions (version_id TEXT PRIMARY KEY, module_key TEXT NOT NULL, state TEXT NOT NULL, parent_version_id TEXT, reason TEXT NOT NULL, reviewer TEXT NOT NULL, input_hash TEXT NOT NULL, result_hash TEXT NOT NULL, payload_path TEXT NOT NULL, created_at_utc TEXT NOT NULL)")

    @staticmethod
    def frame_hash(frame: pd.DataFrame) -> str:
        return sha256(frame.to_csv(index=False, lineterminator="\n", na_rep="<NA>").encode()).hexdigest()

    def save(self, *, module_key: str, frame: pd.DataFrame, state: str, reason: str, reviewer: str, input_hash: str, parent_version_id: str | None = None) -> dict[str, str]:
        if state not in VALID_STATES:
            raise ValueError(f"Unsupported result state: {state}")
        if state == "Locked" and not reason.strip():
            raise ValueError("A reason is required before locking a result version.")
        version_id = f"VR-{uuid4().hex[:16].upper()}"
        payload = frame.to_csv(index=False).encode()
        result_hash = sha256(payload).hexdigest()
        path = self.payload_dir / f"{version_id}.csv.gz"
        path.write_bytes(gzip.compress(payload, compresslevel=6))
        created = datetime.now(timezone.utc).isoformat()
        with managed_connect(self.db_path) as db:
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?,?)", (version_id,module_key,state,parent_version_id,reason,reviewer,input_hash,result_hash,str(path),created))
        return {"version_id": version_id, "module_key": module_key, "state": state, "result_hash": result_hash, "created_at_utc": created}

    def list(self, module_key: str) -> pd.DataFrame:
        with managed_connect(self.db_path) as db:
            rows = db.execute("SELECT version_id,state,parent_version_id,reason,reviewer,input_hash,result_hash,payload_path,created_at_utc FROM versions WHERE module_key=? ORDER BY created_at_utc DESC", (module_key,)).fetchall()
        return pd.DataFrame(rows, columns=["version_id","state","parent_version_id","reason","reviewer","input_hash","result_hash","payload_path","created_at_utc"])

    def load(self, version_id: str) -> pd.DataFrame:
        with managed_connect(self.db_path) as db:
            row = db.execute("SELECT payload_path,result_hash FROM versions WHERE version_id=?", (version_id,)).fetchone()
        if not row:
            raise KeyError(version_id)
        payload = gzip.decompress(Path(row[0]).read_bytes())
        if sha256(payload).hexdigest() != row[1]:
            raise RuntimeError("Stored result version checksum mismatch.")
        return pd.read_csv(io.BytesIO(payload))


__all__ = ["VALID_STATES", "ResultVersionStore"]
