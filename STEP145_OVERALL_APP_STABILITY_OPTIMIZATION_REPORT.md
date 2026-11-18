# BioIntel AI Step 145 — Overall App Stability & Optimization

## Scope

Step 145 hardens the complete BioIntel AI application. It preserves the Step 144 Research Planning specialist engines and adds guarded startup, bounded process caching, SQLite lock recovery, database fleet maintenance, orphaned background-job recovery, recursive diagnostic redaction, Windows runtime resource budgets and a unified maintenance surface.

## Main stability upgrades

### Guarded startup

- Python, VERSION, writable workspace, disk and physical-memory checks.
- Blocking failures stop the UI before large workflows can corrupt or partially write results.
- Advisory conditions start in protected mode with a clear warning.
- Stale temporary files are removed only from known bounded runtime directories.

### Database stability

- All core write transactions now retry bounded SQLite lock/busy failures with exponential backoff.
- WAL auto-checkpoint is configured at 1,000 pages.
- Journal growth is limited to 64 MB per database.
- Foreign keys, busy timeout, recursive triggers and WAL mode remain enforced.
- Fleet maintenance performs quick integrity checks, foreign-key checks, passive checkpoints and PRAGMA optimize.

### Background jobs

- Local job databases are discovered automatically.
- Running jobs with stale worker heartbeats return safely to the queue.
- A failure in one queue does not prevent other queues from being recovered.

### Caching and memory

- New thread-safe TTL cache has entry-count and byte-size limits.
- Least-recently-used eviction prevents unbounded process memory growth.
- Startup checks are cached for 30 seconds and invalidate naturally.
- Maintenance clears registered caches, existing file caches and database-health caches, then requests garbage collection.

### Diagnostics

- Credentials are recursively redacted from mappings, nested messages and URL query values.
- Error reports are written atomically with stable recovery references.
- Diagnostic storage is limited by file count and total size.
- Corrupt or partially copied diagnostic files are ignored instead of crashing support views.

### Windows startup and optimization

- `RUN_BOTH_WINDOWS.bat` runs Step 145 preflight before starting the UI, API or worker.
- Scientific libraries use two threads by default and four on systems with at least eight logical processors.
- UTF-8 mode and tokenizer parallelism controls are applied consistently.
- Failed preflight writes an actionable JSON report and stops safely.

## Reliability & Optimization Center

The existing Reliability & Optimization page now includes:

- Overall startup state, blockers and advisories.
- Protected cache count.
- Safe database maintenance.
- Stale job recovery.
- Cache clearing and old log/partial-file pruning.
- Downloadable before/after maintenance report.

## Completed verification

- **158 distinct selected tests passed; 0 completed-test failures**
- **10/10 Step 145 focused tests passed**
- **1,082/1,082 Python files compiled**
- **224/224 page entrypoints passed bootstrap audit**
- **0 raw SQLite connection violations in application source**
- **40/40 SQLite databases healthy**
- **108,493 database rows inspected**
- **0 foreign-key violations**
- **40/40 database maintenance checks passed**
- **2 job queues inspected with 0 recovery failures**
- Startup preflight passed; the Linux build environment reported one non-blocking 4 GB memory advisory.

## Environment boundary

Live Streamlit browser automation was not executed because Streamlit is unavailable in the Linux build environment. Physical clean Windows qualification, real antivirus interactions, display scaling, sleep/resume and unavailable third-party scientific engines remain target-system checks. The build does not claim that unknown defects can never occur.
