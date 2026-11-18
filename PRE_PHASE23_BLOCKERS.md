# Pre-Phase 23 blockers

## No local implementation blocker

The Phase 17–22 Education OS migration, service, API and connected pages are
present. Their focused regression evidence is green, so additive local
Phase 23–30 development can proceed.

## Existing non-green diagnostic areas

The full historical repository suite has 278 failures and 3 setup errors. The
dominant groups are stale exact-version/package assertions, source-mutating
release tests, unavailable browser/external engines, Windows sandbox process
restrictions, DTI model setup failures and older UI/theme scorecards. These
tests are preserved unchanged.

## External validation blockers

The following cannot be locally classified as production-verified without
external systems, credentials or authorized assessment:

- live Moodle, Canvas, Google Classroom, LTI and OneRoster tenants;
- live OAuth/OIDC/SAML identity providers and certification;
- public TURN/WebRTC infrastructure;
- institutional SMTP/calendar/S3 endpoints;
- PostgreSQL/Redis multi-node and high-availability infrastructure;
- paid or externally hosted AI models;
- 500/1,000/5,000 real-user institutional load;
- formal penetration test, accreditation, WCAG certification and legal review;
- institutional pilot acceptance and production-readiness sign-off.

Locally testable adapters, permission boundaries, mock-server workflows,
configuration validation and deterministic load scripts will be implemented.
External claims will remain `IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION`,
`PARTIALLY_IMPLEMENTED`, or `BLOCKED_WITH_REASON` as evidence requires.
