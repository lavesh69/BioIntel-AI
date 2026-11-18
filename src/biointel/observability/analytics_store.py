from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from biointel.database.core import (
    connect,
    database_health,
    rows_as_dicts,
    transaction,
)
from biointel.ui.navigation import PAGE_CATALOG


@dataclass(frozen=True)
class AnalyticsSummary:
    run_events: int
    daily_metrics: int
    quality_snapshots: int
    system_samples: int
    alerts: int
    success_rate: float
    median_duration_ms: float
    p95_duration_ms: float
    rows_processed: int


SCHEMA = """
CREATE TABLE IF NOT EXISTS analytics_run_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at_utc TEXT NOT NULL,
    module_key TEXT NOT NULL,
    module_title TEXT NOT NULL,
    category TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    rows_processed INTEGER NOT NULL DEFAULT 0,
    memory_mb REAL NOT NULL DEFAULT 0.0,
    model_name TEXT,
    dataset_name TEXT,
    project_code TEXT,
    message TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_run_events_time
    ON analytics_run_events(occurred_at_utc);
CREATE INDEX IF NOT EXISTS idx_run_events_module
    ON analytics_run_events(module_key);
CREATE INDEX IF NOT EXISTS idx_run_events_status
    ON analytics_run_events(status);
CREATE INDEX IF NOT EXISTS idx_run_events_category
    ON analytics_run_events(category);

CREATE TABLE IF NOT EXISTS analytics_daily_metrics (
    metric_date TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    category TEXT NOT NULL,
    metric_value REAL NOT NULL,
    unit TEXT NOT NULL,
    target_value REAL,
    status TEXT NOT NULL DEFAULT 'normal',
    PRIMARY KEY(metric_date, metric_name, category)
);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_name
    ON analytics_daily_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_daily_metrics_status
    ON analytics_daily_metrics(status);

CREATE TABLE IF NOT EXISTS analytics_quality_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at_utc TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    rows_total INTEGER NOT NULL,
    invalid_rows INTEGER NOT NULL,
    duplicate_rows INTEGER NOT NULL,
    conflicting_groups INTEGER NOT NULL,
    completeness REAL NOT NULL,
    drift_score REAL NOT NULL,
    schema_score REAL NOT NULL,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quality_dataset
    ON analytics_quality_snapshots(dataset_name);
CREATE INDEX IF NOT EXISTS idx_quality_time
    ON analytics_quality_snapshots(captured_at_utc);

CREATE TABLE IF NOT EXISTS analytics_system_samples (
    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at_utc TEXT NOT NULL,
    cpu_percent REAL NOT NULL,
    memory_mb REAL NOT NULL,
    disk_mb REAL NOT NULL,
    cache_hit_rate REAL NOT NULL,
    api_latency_ms REAL NOT NULL,
    ui_latency_ms REAL NOT NULL,
    active_jobs INTEGER NOT NULL,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_system_samples_time
    ON analytics_system_samples(captured_at_utc);
CREATE INDEX IF NOT EXISTS idx_system_samples_status
    ON analytics_system_samples(status);

CREATE TABLE IF NOT EXISTS analytics_alerts (
    alert_id TEXT PRIMARY KEY,
    occurred_at_utc TEXT NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    module_key TEXT,
    resolved INTEGER NOT NULL DEFAULT 0
        CHECK(resolved IN (0, 1)),
    resolved_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_severity
    ON analytics_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_resolved
    ON analytics_alerts(resolved);
CREATE INDEX IF NOT EXISTS idx_alerts_time
    ON analytics_alerts(occurred_at_utc);
"""


def initialize_analytics_store(
    path: str | Path,
) -> None:
    with transaction(path) as connection:
        connection.executescript(SCHEMA)


def _percentile(
    values: list[float],
    percentile: float,
) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[low])
    weight = rank - low
    return float(ordered[low] * (1.0 - weight) + ordered[high] * weight)


def seed_analytics_store(
    root: str | Path,
    *,
    replace_demo: bool = True,
    seed: int = 20260721,
) -> AnalyticsSummary:
    project_root = Path(root).resolve()
    database = runtime_database_path(project_root, "analytics.sqlite3")
    initialize_analytics_store(database)

    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    pages = list(PAGE_CATALOG)
    actions = (
        "open_page",
        "load_dataset",
        "run_analysis",
        "generate_report",
        "run_prediction",
        "export_result",
        "validate_input",
        "refresh_dashboard",
    )
    status_weights = (
        ("success", 0.925),
        ("warning", 0.055),
        ("failed", 0.020),
    )
    cumulative: list[tuple[str, float]] = []
    running = 0.0
    for label, weight in status_weights:
        running += weight
        cumulative.append((label, running))

    def random_status() -> str:
        draw = rng.random()
        for label, threshold in cumulative:
            if draw <= threshold:
                return label
        return "success"

    with transaction(database) as connection:
        if replace_demo:
            connection.execute("DELETE FROM analytics_run_events")
            connection.execute("DELETE FROM analytics_daily_metrics")
            connection.execute("DELETE FROM analytics_quality_snapshots")
            connection.execute("DELETE FROM analytics_system_samples")
            connection.execute("DELETE FROM analytics_alerts")

        event_rows = []
        for index in range(15000):
            page = pages[index % len(pages)]
            age_seconds = rng.randint(
                0,
                179 * 24 * 60 * 60,
            )
            occurred = now - timedelta(seconds=age_seconds)
            action = actions[rng.randrange(len(actions))]
            status = random_status()
            base = {
                "open_page": 90,
                "load_dataset": 480,
                "run_analysis": 1100,
                "generate_report": 760,
                "run_prediction": 220,
                "export_result": 340,
                "validate_input": 420,
                "refresh_dashboard": 150,
            }[action]
            duration = max(
                18.0,
                rng.gauss(
                    base,
                    max(base * 0.35, 20),
                ),
            )
            if status == "warning":
                duration *= 1.35
            elif status == "failed":
                duration *= 1.75

            rows_processed = 0
            if action in {
                "load_dataset",
                "run_analysis",
                "run_prediction",
                "validate_input",
            }:
                rows_processed = rng.choice(
                    (
                        1,
                        96,
                        250,
                        1000,
                        1920,
                        5000,
                        5760,
                        16000,
                        32000,
                        160000,
                    )
                )

            memory_mb = max(
                18.0,
                rng.gauss(
                    72.0 + math.log10(rows_processed + 1) * 24.0,
                    22.0,
                ),
            )
            model_name = (
                rng.choice(
                    (
                        "extra_trees",
                        "random_forest",
                        "sgd_logistic",
                        "ridge",
                        "sgd_regression",
                    )
                )
                if action
                in {
                    "run_prediction",
                    "run_analysis",
                }
                else None
            )
            dataset_name = (
                rng.choice(
                    (
                        "Foundation DTI",
                        "Extended DTI",
                        "Ultra DTI",
                        "Double Ultra DTI",
                        "5X Ultra DTI",
                        "Coverage Sequence Library",
                        "Coverage Molecule Library",
                    )
                )
                if rows_processed
                else None
            )
            event_rows.append(
                (
                    occurred.isoformat(),
                    page.key,
                    page.title,
                    page.category,
                    action,
                    status,
                    round(duration, 3),
                    rows_processed,
                    round(memory_mb, 3),
                    model_name,
                    dataset_name,
                    (f"DEMO-{(index % 12) + 1:02d}" if index % 4 == 0 else None),
                    (
                        "Deterministic professional telemetry sample."
                        if status == "success"
                        else "Deterministic demonstration event requiring review."
                    ),
                )
            )

        connection.executemany(
            """
            INSERT INTO analytics_run_events(
                occurred_at_utc, module_key, module_title,
                category, action, status, duration_ms,
                rows_processed, memory_mb, model_name,
                dataset_name, project_code, message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            event_rows,
        )

        metric_names = (
            ("success_rate", "%", 95.0),
            ("median_latency", "ms", 600.0),
            ("p95_latency", "ms", 1800.0),
            ("cache_hit_rate", "%", 80.0),
            ("data_completeness", "%", 98.0),
            ("model_availability", "%", 99.0),
            ("active_projects", "count", 8.0),
            ("open_alerts", "count", 5.0),
            ("rows_processed", "rows", 50000.0),
            ("report_exports", "count", 10.0),
        )
        daily_rows = []
        for day_offset in range(180):
            metric_date = (now - timedelta(days=day_offset)).date()
            seasonal = math.sin(day_offset / 13.0)
            for metric_name, unit, target in metric_names:
                if metric_name == "success_rate":
                    value = 96.8 + seasonal * 1.2 + rng.uniform(-0.6, 0.6)
                    status = "normal" if value >= 95 else "warning"
                elif metric_name == "median_latency":
                    value = 420 + seasonal * 45 + rng.uniform(-30, 30)
                    status = "normal" if value <= target else "warning"
                elif metric_name == "p95_latency":
                    value = 1250 + seasonal * 140 + rng.uniform(-100, 100)
                    status = "normal" if value <= target else "warning"
                elif metric_name == "cache_hit_rate":
                    value = 91 + seasonal * 3 + rng.uniform(-1.4, 1.4)
                    status = "normal" if value >= target else "warning"
                elif metric_name == "data_completeness":
                    value = 99.1 + rng.uniform(-0.5, 0.4)
                    status = "normal" if value >= target else "warning"
                elif metric_name == "model_availability":
                    value = 99.8 + rng.uniform(-0.15, 0.1)
                    status = "normal" if value >= target else "warning"
                elif metric_name == "active_projects":
                    value = 8 + (day_offset % 5)
                    status = "normal"
                elif metric_name == "open_alerts":
                    value = max(
                        0,
                        3 + round(seasonal * 2) + rng.randint(-1, 1),
                    )
                    status = "normal" if value <= target else "warning"
                elif metric_name == "rows_processed":
                    value = max(
                        1000,
                        90000 + seasonal * 25000 + rng.randint(-12000, 12000),
                    )
                    status = "normal" if value >= target else "warning"
                else:
                    value = max(
                        0,
                        14 + round(seasonal * 5) + rng.randint(-2, 3),
                    )
                    status = "normal" if value >= target else "warning"
                daily_rows.append(
                    (
                        metric_date.isoformat(),
                        metric_name,
                        "workspace",
                        round(float(value), 3),
                        unit,
                        target,
                        status,
                    )
                )

        connection.executemany(
            """
            INSERT INTO analytics_daily_metrics(
                metric_date, metric_name, category,
                metric_value, unit, target_value, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            daily_rows,
        )

        quality_rows = []
        datasets = (
            ("Foundation DTI", "classification", 1920),
            ("Extended DTI", "classification", 5760),
            ("Ultra DTI", "classification", 16000),
            ("Double Ultra DTI", "classification", 32000),
            ("5X Ultra DTI", "classification", 160000),
            ("Coverage Sequence Library", "unlabelled", 800),
            ("Coverage Molecule Library", "unlabelled", 1000),
            ("External Validation Classification", "classification", 5000),
            ("External Validation Regression", "regression", 5000),
        )
        for snapshot_index in range(90):
            dataset_name, task_type, rows_total = datasets[snapshot_index % len(datasets)]
            captured = now - timedelta(
                days=snapshot_index * 2,
                hours=rng.randint(0, 23),
            )
            invalid_rows = 0 if snapshot_index % 4 else rng.randint(0, max(1, rows_total // 10000))
            duplicates = 0 if snapshot_index % 5 else rng.randint(0, max(1, rows_total // 8000))
            conflicts = 0 if snapshot_index % 7 else rng.randint(0, 2)
            completeness = max(
                96.0,
                100.0 - (invalid_rows / max(rows_total, 1)) * 100 - rng.uniform(0.0, 0.7),
            )
            drift = max(
                0.0,
                min(
                    1.0,
                    0.12 + math.sin(snapshot_index / 8.0) * 0.08 + rng.uniform(-0.03, 0.03),
                ),
            )
            schema_score = max(
                0.0,
                min(
                    1.0,
                    0.985 + rng.uniform(-0.02, 0.01),
                ),
            )
            status = (
                "pass" if completeness >= 98.0 and drift < 0.25 and conflicts == 0 else "review"
            )
            quality_rows.append(
                (
                    captured.isoformat(),
                    dataset_name,
                    task_type,
                    rows_total,
                    invalid_rows,
                    duplicates,
                    conflicts,
                    round(completeness, 4),
                    round(drift, 4),
                    round(schema_score, 4),
                    status,
                )
            )
        connection.executemany(
            """
            INSERT INTO analytics_quality_snapshots(
                captured_at_utc, dataset_name, task_type,
                rows_total, invalid_rows, duplicate_rows,
                conflicting_groups, completeness, drift_score,
                schema_score, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            quality_rows,
        )

        sample_rows = []
        for index in range(720):
            captured = now - timedelta(hours=index * 6)
            cpu = max(
                2.0,
                min(
                    96.0,
                    23.0 + math.sin(index / 9.0) * 14.0 + rng.uniform(-7, 7),
                ),
            )
            memory = max(
                240.0,
                720.0 + math.sin(index / 13.0) * 110.0 + rng.uniform(-70, 70),
            )
            disk = max(
                100.0,
                420.0 + index * 0.18 + rng.uniform(-4, 4),
            )
            cache_hit = max(
                60.0,
                min(
                    99.9,
                    91.0 + math.sin(index / 11.0) * 4 + rng.uniform(-1.8, 1.8),
                ),
            )
            api_latency = max(
                15.0,
                85.0 + math.sin(index / 17.0) * 25 + rng.uniform(-12, 12),
            )
            ui_latency = max(
                25.0,
                170.0 + math.sin(index / 15.0) * 45 + rng.uniform(-20, 20),
            )
            active_jobs = max(
                0,
                round(2 + math.sin(index / 7.0) * 2 + rng.uniform(-1, 1)),
            )
            status = "healthy" if cpu < 80 and memory < 1100 and cache_hit >= 80 else "review"
            sample_rows.append(
                (
                    captured.isoformat(),
                    round(cpu, 3),
                    round(memory, 3),
                    round(disk, 3),
                    round(cache_hit, 3),
                    round(api_latency, 3),
                    round(ui_latency, 3),
                    active_jobs,
                    status,
                )
            )
        connection.executemany(
            """
            INSERT INTO analytics_system_samples(
                captured_at_utc, cpu_percent, memory_mb,
                disk_mb, cache_hit_rate, api_latency_ms,
                ui_latency_ms, active_jobs, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sample_rows,
        )

        severities = ("info", "warning", "critical")
        alert_rows = []
        for index in range(80):
            severity = severities[2 if index % 19 == 0 else 1 if index % 5 == 0 else 0]
            occurred = now - timedelta(hours=index * 18)
            resolved = 0 if index < 6 else 1
            page = pages[index % len(pages)]
            alert_rows.append(
                (
                    f"ALERT-{index + 1:04d}",
                    occurred.isoformat(),
                    severity,
                    page.category,
                    (
                        f"{page.title} "
                        f"{'requires review' if severity != 'info' else 'status update'}"
                    ),
                    (
                        "Deterministic observability alert. Review the linked "
                        "module and supporting evidence."
                    ),
                    page.key,
                    resolved,
                    ((occurred + timedelta(hours=4 + index % 8)).isoformat() if resolved else None),
                )
            )
        connection.executemany(
            """
            INSERT INTO analytics_alerts(
                alert_id, occurred_at_utc, severity,
                category, title, detail, module_key,
                resolved, resolved_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            alert_rows,
        )

    return analytics_summary(database)


def analytics_summary(
    path: str | Path,
    *,
    days: int = 180,
) -> AnalyticsSummary:
    initialize_analytics_store(path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(int(days), 1))).isoformat()
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT
                status,
                duration_ms,
                rows_processed
            FROM analytics_run_events
            WHERE occurred_at_utc >= ?
            """,
            (cutoff,),
        ).fetchall()
        statuses = [str(row["status"]) for row in rows]
        durations = [float(row["duration_ms"]) for row in rows]
        processed = sum(int(row["rows_processed"]) for row in rows)
        total = len(rows)
        success_rate = statuses.count("success") / total * 100.0 if total else 0.0
        counts = {
            "daily_metrics": int(
                connection.execute("SELECT COUNT(*) FROM analytics_daily_metrics").fetchone()[0]
            ),
            "quality_snapshots": int(
                connection.execute("SELECT COUNT(*) FROM analytics_quality_snapshots").fetchone()[0]
            ),
            "system_samples": int(
                connection.execute("SELECT COUNT(*) FROM analytics_system_samples").fetchone()[0]
            ),
            "alerts": int(
                connection.execute("SELECT COUNT(*) FROM analytics_alerts").fetchone()[0]
            ),
        }
    return AnalyticsSummary(
        run_events=total,
        daily_metrics=counts["daily_metrics"],
        quality_snapshots=counts["quality_snapshots"],
        system_samples=counts["system_samples"],
        alerts=counts["alerts"],
        success_rate=round(success_rate, 4),
        median_duration_ms=round(
            _percentile(durations, 0.5),
            4,
        ),
        p95_duration_ms=round(
            _percentile(durations, 0.95),
            4,
        ),
        rows_processed=processed,
    )


def module_performance(
    path: str | Path,
    *,
    days: int = 30,
    limit: int = 100,
) -> list[dict[str, Any]]:
    initialize_analytics_store(path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(int(days), 1))).isoformat()
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT
                module_key,
                module_title,
                category,
                COUNT(*) AS runs,
                ROUND(
                    100.0 * SUM(
                        CASE WHEN status = 'success'
                        THEN 1 ELSE 0 END
                    ) / COUNT(*),
                    2
                ) AS success_rate,
                ROUND(AVG(duration_ms), 2) AS avg_duration_ms,
                MAX(duration_ms) AS max_duration_ms,
                SUM(rows_processed) AS rows_processed,
                ROUND(AVG(memory_mb), 2) AS avg_memory_mb
            FROM analytics_run_events
            WHERE occurred_at_utc >= ?
            GROUP BY module_key, module_title, category
            ORDER BY runs DESC, module_title
            """,
            (cutoff,),
        ).fetchall()
    records = rows_as_dicts(rows)
    bounded_limit = min(max(int(limit), 1), 500)
    if len(records) <= bounded_limit:
        return records

    # Preserve portfolio-wide totals even when the caller requests a bounded
    # table. The final row represents the lower-volume tail rather than
    # silently dropping its runs, processed rows, or resource usage.
    if bounded_limit == 1:
        head: list[dict[str, Any]] = []
        tail = records
    else:
        head = records[: bounded_limit - 1]
        tail = records[bounded_limit - 1 :]
    tail_runs = sum(int(item["runs"]) for item in tail)
    tail_rows = sum(int(item["rows_processed"]) for item in tail)
    weighted_success = (
        sum(float(item["success_rate"]) * int(item["runs"]) for item in tail) / tail_runs
        if tail_runs
        else 0.0
    )
    weighted_duration = (
        sum(float(item["avg_duration_ms"]) * int(item["runs"]) for item in tail) / tail_runs
        if tail_runs
        else 0.0
    )
    weighted_memory = (
        sum(float(item["avg_memory_mb"]) * int(item["runs"]) for item in tail) / tail_runs
        if tail_runs
        else 0.0
    )
    head.append(
        {
            "module_key": "__portfolio_tail__",
            "module_title": f"Other modules ({len(tail)})",
            "category": "Portfolio aggregate",
            "runs": tail_runs,
            "success_rate": round(weighted_success, 2),
            "avg_duration_ms": round(weighted_duration, 2),
            "max_duration_ms": max(float(item["max_duration_ms"]) for item in tail),
            "rows_processed": tail_rows,
            "avg_memory_mb": round(weighted_memory, 2),
        }
    )
    return head


def daily_metric_series(
    path: str | Path,
    metric_name: str,
    *,
    days: int = 90,
) -> list[dict[str, Any]]:
    initialize_analytics_store(path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(int(days), 1))).date().isoformat()
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM analytics_daily_metrics
            WHERE metric_name = ?
              AND metric_date >= ?
            ORDER BY metric_date
            """,
            (metric_name, cutoff),
        ).fetchall()
    return rows_as_dicts(rows)


def recent_events(
    path: str | Path,
    *,
    status: str = "all",
    module_key: str = "all",
    limit: int = 200,
) -> list[dict[str, Any]]:
    initialize_analytics_store(path)
    filters: list[str] = []
    parameters: list[object] = []
    if status != "all":
        filters.append("status = ?")
        parameters.append(status)
    if module_key != "all":
        filters.append("module_key = ?")
        parameters.append(module_key)
    where = "WHERE " + " AND ".join(filters) if filters else ""
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM analytics_run_events
            {where}
            ORDER BY occurred_at_utc DESC
            LIMIT ?
            """,
            [
                *parameters,
                min(max(int(limit), 1), 1000),
            ],
        ).fetchall()
    return rows_as_dicts(rows)


def quality_overview(
    path: str | Path,
) -> list[dict[str, Any]]:
    initialize_analytics_store(path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT q.*
            FROM analytics_quality_snapshots q
            JOIN (
                SELECT dataset_name, MAX(captured_at_utc) AS max_time
                FROM analytics_quality_snapshots
                GROUP BY dataset_name
            ) latest
              ON latest.dataset_name = q.dataset_name
             AND latest.max_time = q.captured_at_utc
            ORDER BY q.dataset_name
            """
        ).fetchall()
    return rows_as_dicts(rows)


def system_overview(
    path: str | Path,
    *,
    limit: int = 120,
) -> list[dict[str, Any]]:
    initialize_analytics_store(path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM analytics_system_samples
            ORDER BY captured_at_utc DESC
            LIMIT ?
            """,
            (min(max(int(limit), 1), 1000),),
        ).fetchall()
    return list(reversed(rows_as_dicts(rows)))


def alert_overview(
    path: str | Path,
    *,
    resolved: str = "all",
) -> list[dict[str, Any]]:
    initialize_analytics_store(path)
    with connect(path, read_only=True) as connection:
        if resolved == "all":
            rows = connection.execute(
                """
                SELECT *
                FROM analytics_alerts
                ORDER BY occurred_at_utc DESC
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT *
                FROM analytics_alerts
                WHERE resolved = ?
                ORDER BY occurred_at_utc DESC
                """,
                (1 if resolved == "resolved" else 0,),
            ).fetchall()
    return rows_as_dicts(rows)


def analytics_health(
    path: str | Path,
    summary=None,
) -> dict[str, object]:
    summary = summary or analytics_summary(path)
    health = database_health(
        path,
        name="Analytics & Observability Warehouse",
    )
    populated = summary.run_events > 0
    return {
        "database": asdict(health),
        "summary": asdict(summary),
        "populated": populated,
        "healthy": (health.exists and health.integrity == "ok" and health.table_count >= 5),
    }
