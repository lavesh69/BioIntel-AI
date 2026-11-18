# Science Pulse Scheduler Specification

- High-priority news: 3,600 seconds.
- Normal news: 10,800 seconds.
- Publications and preprints: 21,600 seconds.
- Crossref Event Data trust/event check: 86,400 seconds.
- Hourly digest opportunity: at minute 0-14; daily: 06:00 UTC; weekly: Monday 06:00 UTC.
- Startup: sources become due shortly after canonical initialization.
- State: source next/last time, checkpoint, duration, failures, circuit-open-until, and complete run rows.
- Recovery: stale running rows become `recovered_after_restart` and are safely requeued.
- Shutdown: worker stop file triggers graceful lease release; no separate scheduler process is spawned.
- Desktop boundary: synchronization runs while BioIntel is running, not while the computer/application is closed.
