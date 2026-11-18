# Shiro Windows runtime-stop hotfix

## Fixed

- Windows PID reuse no longer blocks installation when a stale `biointel-running.json` points to an unrelated process.
- Only a live process whose command line matches both the recorded BioIntel application root and expected role can block activation or be force-stopped.
- Unverified/reused PIDs are never terminated.
- Graceful-stop waiting is limited to verified BioIntel processes, avoiding the previous 25-second stale-PID delay.
- Verified BioIntel processes still block installation if they cannot be stopped safely.

## Validation

The regression suite covers both the reused-PID success path and the verified-owned-process failure path. The Windows installer and exact RUN BOTH entrypoint are exercised after packaging.