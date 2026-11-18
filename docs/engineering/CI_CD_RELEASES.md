# CI/CD and release governance

The protected branch requires code quality, unit-tests, integration-tests, scientific-regression, E2E, visual, security, container and Kubernetes gates. Releases are tag-driven, produce deterministic archives, SBOMs, checksums and build provenance. Promotion requires an accountable reviewer and a rollback plan. Failed canaries trigger rollback to the previous signed artifact.
