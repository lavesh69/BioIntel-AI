# Phase 31–35 API Specification

Base prefix: `/api/v1/education`

Phase routers:

- `/phase32`: device registration/approval/revocation, tenant sync policy, journal
  changes, conflict listing/resolution, status, and redacted diagnostics.
- `/phase33`: twin projects, synthetic data, models, scenarios, simulations, Shiro
  explanations, teacher-reviewed learning activities, and reproducibility bundles.
- `/phase34`: capabilities, approved tools, projects, datasets, resumable imports,
  workflows, run execute/cancel/retry/clone, notes, reviews, handoffs, bundles, and
  disabled-by-default remote adapters.
- `/phase35`: capabilities, twelve agent definitions, workspaces, evidence/search,
  tasks, approvals, refused consequential actions, novelty searches, hypotheses,
  transitions/links, experiments, claim-evidence graphs, workflows, and evaluations.

## Security contract

Remote API mode requires authentication. Role checks are applied to mutating and
privileged operations. Tenant IDs from resource records are compared with the
authenticated tenant context and cross-tenant access fails closed. Standalone local
operator mode remains available for the offline desktop application.

Global middleware enforces request-size limits, rate limits, security headers, and the
configured API key/authentication policy. Diagnostics redact credentials and encrypted
configuration. Upload/import paths are canonicalized and constrained to approved roots.

## Error behavior

Validation errors use FastAPI/Pydantic responses. Domain conflicts, missing resources,
permission denials, unsafe actions, quota violations, integrity errors, and invalid
state transitions are returned as bounded HTTP errors; stack traces and secrets are not
returned to clients.

The exact OpenAPI document is available from the local FastAPI application at runtime.
No public internet endpoint is enabled by this release.
