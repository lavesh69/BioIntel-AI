# BioIntel Calls — qualified local P2P setup

This Phase 13B initial pass provides a real browser WebRTC client, authenticated database-backed signaling, and honest capability gates. It is not labeled Call/VC Complete.

## Run locally

1. Install the release with Python 3.11 dependencies. Start the existing BioIntel API and Streamlit services.
2. Set `BIOINTEL_CALL_STUN_URLS`. For LAN/device use, serve the API over trusted HTTPS; browser media capture normally works without HTTPS only on loopback.
3. Create a call in **Connect → Live and calls**, have the invited identity accept it, and let the host start it.
4. In two independently authenticated browser profiles, open `/api/v1/connect/calls/client`, select devices, enter the same call ID, and choose **Connect**.
5. Verify remote audio/video, mute/camera synchronization, screen sharing, leave, and host end-for-all.

The client uses `getUserMedia`, `getDisplayMedia`, `RTCPeerConnection`, SDP offer/answer, trickled ICE candidates, and the authenticated `/api/v1/connect/calls/{id}/signals` endpoints. Signaling records expire after one hour and are never returned to nonmembers.

## TURN

Copy `config/calls/turnserver.conf.example` outside the release, replace placeholders, and run Coturn under Docker or a Windows-compatible deployment. Set the TURN URL, username, and credential only in the server environment. The authenticated ICE configuration endpoint passes them to joined clients; the general capabilities endpoint never returns credentials.

To qualify relay mode, set `BIOINTEL_CALL_RELAY_ONLY=1`, connect two independent clients, and inspect `RTCPeerConnection.getStats()` for a selected `relay` candidate pair. This build has not performed that external test.

## Scale and external media services

The implemented topology is full-mesh P2P and is capped by configuration (default four peers). It is not an SFU and is not described as scalable. SFU, server recording, transcription, live captions, and breakout media isolation remain configuration-required/unimplemented. Recording requests surface `unavailable`; the application never marks recording active or completed without a real artifact.
