from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


@dataclass(frozen=True)
class BackendConfiguration:
    database_url: str
    redis_url: str
    object_storage_endpoint: str
    object_storage_bucket: str
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    object_storage_secure: bool = True

    @classmethod
    def from_environment(cls) -> "BackendConfiguration":
        endpoint = os.getenv("BIOINTEL_OBJECT_STORAGE_ENDPOINT", "")
        return cls(
            database_url=os.getenv("BIOINTEL_DATABASE_URL", ""),
            redis_url=os.getenv("BIOINTEL_REDIS_URL", ""),
            object_storage_endpoint=endpoint,
            object_storage_bucket=os.getenv("BIOINTEL_OBJECT_STORAGE_BUCKET", ""),
            object_storage_access_key=os.getenv("BIOINTEL_OBJECT_STORAGE_ACCESS_KEY", ""),
            object_storage_secret_key=os.getenv("BIOINTEL_OBJECT_STORAGE_SECRET_KEY", ""),
            object_storage_secure=endpoint.lower().startswith("https://"),
        )


def backend_readiness(configuration: BackendConfiguration) -> dict[str, Any]:
    checks = {
        "postgres_driver": importlib.util.find_spec("psycopg") is not None,
        "redis_driver": importlib.util.find_spec("redis") is not None,
        "object_storage_driver": importlib.util.find_spec("boto3") is not None,
        "database_configured": configuration.database_url.startswith(("postgres://", "postgresql://")),
        "redis_configured": configuration.redis_url.startswith(("redis://", "rediss://")),
        "object_storage_configured": bool(
            configuration.object_storage_endpoint and configuration.object_storage_bucket
        ),
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "claim_boundary": "Driver and configuration readiness does not prove service availability, migration completeness or production capacity.",
    }


class PostgresRecordRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("A PostgreSQL URL is required.")
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL repository requires psycopg.") from exc
        self.psycopg = psycopg
        self.database_url = database_url
        with self.psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS biointel_records_v217(
                    tenant_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    payload_json JSONB NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY(tenant_id, namespace, record_id)
                )
                """
            )

    def upsert(
        self,
        tenant_id: str,
        namespace: str,
        record_id: str,
        payload: Mapping[str, Any],
    ) -> str:
        serialized = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        with self.psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                INSERT INTO biointel_records_v217(
                    tenant_id, namespace, record_id, payload_json, payload_sha256
                ) VALUES (%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT(tenant_id,namespace,record_id) DO UPDATE SET
                    payload_json=EXCLUDED.payload_json,
                    payload_sha256=EXCLUDED.payload_sha256,
                    updated_at_utc=NOW()
                """,
                (tenant_id, namespace, record_id, serialized, digest),
            )
        return digest

    def get(self, tenant_id: str, namespace: str, record_id: str) -> dict[str, Any] | None:
        with self.psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM biointel_records_v217
                WHERE tenant_id=%s AND namespace=%s AND record_id=%s
                """,
                (tenant_id, namespace, record_id),
            ).fetchone()
        return dict(row[0]) if row else None


class RedisJobQueue:
    def __init__(self, redis_url: str, *, namespace: str = "biointel:v217") -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Distributed queue requires redis.") from exc
        self.client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
        )
        self.namespace = namespace

    def submit(self, tenant_id: str, task: Mapping[str, Any]) -> str:
        job_id = "job-" + uuid4().hex
        payload = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "task": dict(task),
            "state": "queued",
        }
        pipe = self.client.pipeline(transaction=True)
        pipe.hset(f"{self.namespace}:jobs", job_id, json.dumps(payload, sort_keys=True))
        pipe.rpush(f"{self.namespace}:queue", job_id)
        pipe.execute()
        return job_id

    def reserve(self, timeout_seconds: int = 5) -> dict[str, Any] | None:
        value = self.client.blpop(f"{self.namespace}:queue", timeout=max(1, timeout_seconds))
        if not value:
            return None
        job_id = value[1]
        raw = self.client.hget(f"{self.namespace}:jobs", job_id)
        return json.loads(raw) if raw else None


class S3ArtifactRepository:
    def __init__(self, configuration: BackendConfiguration) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("Object artifact storage requires boto3.") from exc
        if not configuration.object_storage_bucket:
            raise ValueError("Object storage bucket is required.")
        self.bucket = configuration.object_storage_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=configuration.object_storage_endpoint or None,
            aws_access_key_id=configuration.object_storage_access_key or None,
            aws_secret_access_key=configuration.object_storage_secret_key or None,
            use_ssl=configuration.object_storage_secure,
        )

    def put_file(self, tenant_id: str, source: str | Path, *, prefix: str = "artifacts") -> dict[str, str]:
        path = Path(source).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        key = f"{prefix.strip('/')}/{tenant_id}/{digest}/{path.name}"
        self.client.upload_file(
            str(path),
            self.bucket,
            key,
            ExtraArgs={"Metadata": {"sha256": digest, "tenant-id": tenant_id}},
        )
        return {"bucket": self.bucket, "key": key, "sha256": digest}
