# Step 196 V4 — Stale Installer Lock Recovery

## Reproduced failure

`INSTALLATION FAILED: Another BioIntel AI installation/repair is already running.`

The previous implementation treated every lock younger than two hours as active. It did not verify whether the PID that created the lock still existed. A failed or closed installer could therefore block every retry.

## Permanent correction

- Lock acquisition now uses atomic exclusive file creation.
- The lock records PID, root, Python executable, timestamp and a unique ownership token.
- Windows process liveness is checked with `OpenProcess` and `GetExitCodeProcess`.
- A lock whose owning PID is dead is removed immediately, even when it is only seconds old.
- Invalid or partially written stale locks recover automatically.
- A genuinely live concurrent installer remains blocked.
- Lock cleanup verifies the ownership token and cannot delete a replacement lock.
- No separate cleanup BAT or manual AppData deletion is required.

## User workflow

1. `INSTALL_WINDOWS.bat`
2. `RUN_BOTH_WINDOWS.bat`

## Regression coverage

- Recent lock from dead PID self-heals.
- Current live PID remains protected.
- Corrupt old lock self-heals.
- Replacement lock is not removed by an older installer context.
- Step 190–196 focused regressions pass.
