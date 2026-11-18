# Step 56 — Multi-Store Publish Candidate

## Release summary

BioIntel AI has been upgraded from a local Streamlit research workspace into a multi-platform publish-candidate repository covering web/PWA-style access, Android, iOS and Windows desktop packaging.

### Platform deliverables

- **Hosted web:** production Docker Compose stack with Caddy TLS/reverse proxy, Streamlit UI, FastAPI, PostgreSQL, Redis and MinIO.
- **Android:** Capacitor native project, target/compile SDK 36, HTTPS-only networking, minimal permissions, signed AAB build workflow, deep links and production listing assets.
- **iOS:** Capacitor/Xcode native project, iOS 15 minimum, privacy manifest embedded in app resources, manual distribution signing/export workflow, deep links and App Store assets.
- **Windows:** Electron local-first desktop shell, packaged Python/Streamlit backend, user-data workspace preservation, APPX + NSIS targets and Partner Center identity/signing pipeline.

### Security and privacy

- Production Streamlit authentication with PBKDF2-SHA256 password hashes, lockout and local audit records.
- Public mobile bootstrap/legal endpoints; protected API operations remain API-key and role controlled.
- HTTPS-only mobile server validation and external-navigation isolation.
- No advertising SDK, no cross-app tracking and no automatic scientific-file sharing.
- Local activity inventory/export/clear controls that do not accidentally delete scientific datasets or models.
- Privacy policy, terms, support pages, Google Play Data Safety and Apple App Privacy templates.

### Store presentation

- Store-specific descriptions, keywords, release notes and category metadata.
- Android/Apple/Windows icon sets.
- Three Google Play phone screenshots, three iPhone 6.9-inch screenshots and three Microsoft desktop screenshots.
- Google Play 1024×500 feature graphic.
- Research-use wording and no unsupported medical claims.

### Data and model assurance

- 24 bundled research model artifacts are SHA-256 indexed.
- 20/20 SQLite databases pass integrity checks.
- Foreign-key violations: 0.
- Existing scientific/data-rich workspace retained; no project feature or model removed.
- Release remains below the requested 2 GiB limit.

## Verification result

- Tests collected: **468**
- Passed: **452**
- Browser/environment-gated skips: **16**
- Failures: **0**
- New Step 56 tests: **5/5 passed**
- Ruff findings: **0**
- Python compilation: **passed**
- Mobile TypeScript/Vite production build: **passed**
- Mobile npm vulnerabilities: **0**
- Desktop npm vulnerabilities: **0**
- Repository secret findings: **0**
- Store verifier internal failures: **0**
- Store verifier external actions: **3**

## External actions that cannot be embedded in source

1. Google Play account, reserved application ID, Play App Signing and upload keystore.
2. Apple Developer/App Store Connect account, distribution certificate, provisioning profile and Xcode/macOS signing.
3. Microsoft Partner Center identity, code-signing certificate and certification submission.
4. A real public domain/DNS and production hosting for mobile companion access.
5. Physical-device/internal-track/TestFlight/Windows certification and store review.

These are intentionally reported as external actions rather than falsely marked complete.
