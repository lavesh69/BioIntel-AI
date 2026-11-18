# New Modules Known Limitations

Status: **IMPLEMENTED WITH CONFIGURATION-REQUIRED FEATURES** for the tested local core.

- Publication and RSS adapters are implemented, but no live provider was called in this qualification; endpoints, credentials, rate limits and terms require operator configuration.
- Calls has authenticated small-room WebRTC signaling. TURN, SFU, server recording and transcription remain unconfigured/unavailable; no recording file is fabricated.
- FFmpeg was not qualified here. Original video upload/hash works; transcoding, adaptive playback, thumbnails and transcripts are not claimed.
- Shiro's existing local evidence assistant is preserved, but institution-scoped Classroom/Academy automation is not enabled; AI cannot change attendance, marks, results or circulars.
- Dedicated discussions, library circulation, early-warning analytics, personalized Pulse feeds, trend analytics, resumable chunk upload and CDN/object storage are not complete in this 50-credit pass.
- UI was exercised through the renderer smoke harness, not a real browser session. Windows package preflight results are recorded separately.
