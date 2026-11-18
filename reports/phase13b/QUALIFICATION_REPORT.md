# Phase 13B qualification report — initial local P2P pass

Date: 2026-07-27
OS: Windows host (exact Windows build not captured by this sandbox)
Python test runtime: CPython 3.11
Browser versions: not tested in this pass
Topology: peer-to-peer full mesh, configured default maximum 4
STUN: configurable; default public STUN URL present, connectivity not proven
TURN: not configured; relay-only test not run
SFU: not implemented/configured
Participants in automated service test: 2 identities

## Verified

- Four archives assembled with root and `BioIntel-Step220` trees normalized.
- Calls page and all four shiro markers included in the install tree.
- Authenticated participant isolation for call state and signaling.
- Offer payload delivery, expiry filter, recipient scoping, host-only end, and durable ended state.
- Recording requests remain `unavailable`; no active/completed state or media-file claim is produced.
- Existing Connect target suite: 9 tests passed under Python 3.11 after correction/addition.
- Python compilation passed for changed backend, API, tests, and UI modules.

## Not verified

No independent browser/WebRTC media test was possible in this pass. Therefore microphone/camera tracks received, screen-share result, reconnection, ICE selected pair, RTT, jitter, packet loss, bitrate, LAN behavior, and Windows 10/11 browser smoke are unqualified. No recording file exists; codec, duration, size, and SHA-256 are not applicable. No transcription provider was configured and no transcript was generated.

Result: qualified signaling and local-P2P implementation preview; not Call/VC Complete.
