# BioIntel Connect Deployment Report
Generated: 2026-07-27 05:02:42 UTC
Platform: Windows Desktop, Web Browser & Network Deployment
Release: BioIntel AI 15.6.0 — BioIntel Connect

## Deployment Architecture Summary
- **FastAPI Application Server**: Active on `http://127.0.0.1:8000`
- **Streamlit Frontend Workbench**: Active on `http://127.0.0.1:8501`
- **Database Layer**: SQLite (Local Mode) / PostgreSQL (Network Mode) with 94 Connect tables (Migration ID: `002_connect_complete_target`)
- **Real-Time WebSockets**: `/api/v1/connect/websocket` endpoint supporting direct/group messaging, typing status, presence, and delivery receipts.
- **Media Processing Worker**: Isolated quarantine scanner, image thumbnail generator, responsive video transcoder, and PDF metadata extractor.
- **Background Worker**: Managed background daemon for notifications, scheduled post publishing, and digest delivery.

## Qualified Features
1. **Local-First Privacy Boundary**: Strict local storage default for scientific datasets, project files, and Shiro context. Confirmation required before upload.
2. **Professional Profiles & Network**: Professional fields, ORCID/Google Scholar links, follow system, and 2-way connection requests.
3. **Posts & Secure Uploads**: Multi-media posts (Images, Carousels, Videos, PDFs, Documents, BioIntel Reports) with pre-upload privacy scan.
4. **Persistent Real-Time Messaging**: Direct & group messaging, message request inbox, offline replay, and symmetric block enforcement.
5. **Scientific Communities & Collaboration**: Moderated communities (Public, Private, Invite, Institution), collaboration requests, and workflow versioning.
6. **Shiro AI Assistant**: Reviewable draft generation requiring explicit user approval before publishing.
