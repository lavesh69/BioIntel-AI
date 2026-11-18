# BioIntel Connect Known Limitations

- Branch coverage is 76%; the specification's 85% acceptance gate is not met.
- Calls use browser peer-to-peer WebRTC and authenticated application signaling. No bundled TURN or SFU exists.
- Recording/transcription are reported unavailable unless a real provider is implemented; no fabricated active state or media file is produced.
- Local preservation creates a verifiable ZIP plus SHA256SUMS; it does not claim permanent archival.
- Enterprise SSO, cross-network calling, production load, accessibility, browser/device matrix and penetration testing need environment-specific external qualification.
- Several advanced services have functional local persistence but are not substitutes for regulated workflow or provider certification.

