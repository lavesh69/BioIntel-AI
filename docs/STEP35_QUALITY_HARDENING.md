# Step 35 — Platform Quality Hardening

Step 35 converts the professional UI rebuild into a measurable quality program. It improves software architecture, security, deployment, model governance, observability and user experience while refusing to inflate scientific scores that require real external evidence.

## User interface

- Native Streamlit multipage navigation is hidden to remove the 70+ page visual overload.
- BioIntel Studio, Platform Quality Center, Quick Start and Scientific Readiness are the primary entry points.
- All advanced tools remain available through fuzzy search, workflow groups, favourites and recent work.
- Historical Step labels were replaced by consistent Professional Workspace branding.
- Home launch order was fixed; `safe_page_link` is now defined before first use.
- The Platform Quality Center provides group scores, dimension evidence, model blockers and downloadable reports.

## Scientific and model quality

- Every model sidecar is audited for synthetic status, immutable dataset hash, held-out performance, calibration, robust split strategy and independent validation.
- Synthetic or otherwise blocked models cannot be promoted to active/default through the lifecycle UI.
- The strict release policy requires verified authenticity, independent sources, publication coverage, leakage-safe robust splitting, uncertainty calibration and blinded prospective validation.
- User-supplied generic evidence is no longer automatically described as verified experimental evidence; it remains unverified unless explicitly attested.

## Security and production

- Production mode fails closed when API identities or required service variables are missing.
- API-key entropy, trusted hosts and official-host download policy are validated.
- Reviewer write access is limited to non-destructive review operations.
- Redis-backed distributed rate limiting is used when configured, with SQLite/memory fallback.
- Production responses include HSTS and additional browser security headers.
- The production image is multi-stage and runs as a non-root user.
- Docker services use pinned images, health checks, log rotation, PID limits, no-new-privileges and explicit production mode.

## Observability and operations

- Added `/live`, `/ready`, `/metrics`, `/quality/scorecard`, `/quality/models` and `/production/configuration`.
- Built-in Prometheus text metrics cover request count, latency and exceptions without requiring an external package.
- Step 35 upgrade and verification scripts install integrity guards, optimize registries and export a quality report.

## Honest limitation

Code changes improve governance and reliability, but they cannot create genuine clinical data, independent wet-lab validation, prospective results, regulatory certification or production-scale repository integration. Those dimensions remain blocked until the corresponding real evidence and infrastructure are supplied.
