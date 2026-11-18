# Education Security and Privacy Report

## Implemented controls

- Actor, institution and resource authorization on Education OS service operations.
- Strict cross-institution resource rejection and tenant-aware file paths.
- Parameterized SQL throughout the new services.
- Foreign keys, uniqueness constraints and bounded list limits.
- Idempotency request hashes that reject key reuse with changed content.
- Optimistic Studio concurrency control.
- Executable/script attachment blocking, size limits and content/extension checks.
- Storage-path containment checks before Shiro ingestion and Studio export.
- ZIP output uses controlled internal member names.
- HTTPS-only Studio citation URLs.
- Connect delivery through persisted identities rather than untrusted display names.
- Shiro official artifacts require teacher/reviewer approval.
- Interventions are labelled `rule_based_indicator`, include provenance and require human review.
- Unknown legacy identities resolve to `guest`, not implicit student.
- Environment-variable secret references; no new hard-coded credentials.
- Audit events for role grants and human intervention decisions.

## Privacy

Education records are tenant-scoped. Guardian access continues to use the existing
verified link plus student consent workflow. Shiro conversation/feedback retention uses
the existing privacy-aware Shiro store. Real data is not seeded during normal startup.
Local mode does not require paid cloud processing.

## Minors and high-impact decisions

Risk indicators, grading assistance and progression recommendations must remain
human-reviewed. Browser behavior alone is not treated as proof of cheating. The system
records evidence and reviewer actions so a decision can be corrected or dismissed.

## External/unverified controls

- Independent penetration test and dependency vulnerability certification.
- Formal privacy impact assessment for each deploying institution.
- Formal WCAG audit with assistive-technology users.
- Public TURN relay and internet calling qualification.
- Live external provider privacy/data-processing agreements.

These items are not represented as completed.

