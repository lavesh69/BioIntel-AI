# BioIntel Connect complete-target test report

Date: 2026-07-26. Environment: Windows, Python 3.11, Streamlit 1.58.0, FastAPI 0.128.2, SQLite WAL.

## Results

- Connect unit/integration regression: **14/14 passed** in 3.822 seconds.
- Streamlit AppTest: **15/15 Connect pages passed**.
- Navigation integrity: **healthy**; 296 catalogued page files, no missing paths, duplicate keys or duplicate paths.
- Migration smoke: migrations `001` and `002` applied; 94 Connect tables; rollback removes feature tables and retains only the ledger.
- API registry: 113 operations, 92 unique paths, all master/addendum families present.
- Browser QA: Messages, Communities, Discover, Stories, Live/Calls, Onboarding, Accessibility and Admin route render checks; no Streamlit exception blocks or browser console errors. Admin access denied for an unprivileged browser identity as expected.
- Backup drill: consistent SQLite snapshot encrypted; SHA-256, decryption, ZIP CRC/path safety, `PRAGMA integrity_check=ok` and migration ledger validated in an isolated directory; production database untouched.

## Covered risk cases

Upload resume/dedupe/sensitive warning/malware block; post/privacy/blocking; messaging idempotency, receipts and offline replay; community privacy/roles; workflow fork without execution; story expiry/viewers; short-video accessibility; live/call recording consent; verification; onboarding resume; delivery dedupe/digest; drafts/scheduling/lifecycle; Shiro no-send/no-publish; admin RBAC; migration/rollback; encrypted backup restore.

No claim is made for distributed-broker scale, external email/push provider delivery, TURN media relay or a production cloud deployment; adapters and durable local fallbacks are explicit.

## Windows installer and launcher verification

- Windows workflow contract checks: **13/13 passed**.
- Step221 integration repair tests: **9/9 passed**.
- Contextual research self-test: **79/79 page files passed**.
- Full `INSTALL_WINDOWS.bat /no-pause`: exit code 0 using an isolated custom path containing spaces.
- Managed `RUN_BOTH_WINDOWS.bat /managed /no-browser /no-pause`: exit code 0.
- Runtime checks: Streamlit HTTP 200 `ok`; API `/health` `ok` at version 15.6.0; Connect health `healthy`; report PDF generation passed.
- Native Windows smoke: UI, API, local database and worker ready; graceful cleanup passed.
- Windows runtime PID-safety and graceful-stop regression: **3/3 passed**, including restricted process-inspection fallback.

The optional-database aggregate `/ready` endpoint is not claimed as passing; the supported core launch gate uses UI health, API `/health`, the local runtime database and the worker.