# Education Phase 17–22 Known Limitations

| Capability | Status | Reason |
|---|---|---|
| Core local Education workflow | Implemented and verified | SQLite/local files, 206 target tests |
| Public internet calls/live classes | External verification required | Requires deployed TURN credentials and relay/network tests |
| Live PubMed/Europe PMC/Crossref/bioRxiv/medRxiv availability | External verification required | Provider uptime, rate limits and network policy vary |
| External AI providers | External verification required | Credentials, consent and provider policy required |
| Local Ollama generation | Implemented, configuration required | Ollama server/model must be installed separately |
| Studio structured project ZIP | Implemented and verified | Local deterministic export |
| Studio PDF/PPTX/image/video render | Unavailable in this release | No qualified renderer pipeline is connected; fake downloads are not exposed |
| SCORM/xAPI/LTI external certification | Adapter boundary only | Requires third-party LMS conformance testing |
| PostgreSQL Phase 17–22 qualification | Preserved adapter boundary, not locally verified | SQLite is the qualified zero-configuration default |
| Formal security/privacy/accessibility certification | External verification required | Independent assessment is required |
| Trained predictive ML for interventions | Unavailable | Current indicators are explicitly rule-based, never labelled trained ML |
| Native Android app | Not in scope | Responsive mobile browser support is preserved |

The broad historical repository test suite is not green; exact results and causes are in
`EDUCATION_TEST_REPORT.md`. This limitation is intentionally disclosed.

