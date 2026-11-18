# BioIntel Education Suite — Implementation Report

## Scope

This upgrade uses the Shiro AI v3 + Career Hub + P0/P1/P2 package as its base and adds missing education, classroom and career capabilities without removing existing modules.

## Native local integrations

1. Interactive Lesson Studio
2. Versioned Collaborative Notes
3. Browser-local Whiteboard
4. Question Bank
5. Smart Assessment Engine
6. Local Coding Lab
7. Notebook Assignment Grader
8. Code Integrity Review
9. Classroom Q&A
10. Learning Analytics and portable statements
11. Offline Classroom Library
12. Unified Education Search
13. Résumé Builder
14. Application Document Studio
15. Interview Preparation Workspace
16. Credential and Badge Engine
17. Roster CSV and gradebook interchange utilities

## Optional isolated service connectors

1. BioIntel Live Classroom
2. BioIntel Virtual Classroom Pro
3. BioIntel Collaborative Board Service
4. BioIntel Real-Time Notes Service
5. BioIntel Multi-User Scientific Lab
6. BioIntel Assessment Worker
7. BioIntel Code Sandbox
8. BioIntel Learning Record Store
9. BioIntel Education Search Service
10. BioIntel LMS Bridge
11. BioIntel Offline Library Sync

## Product wiring

- BioIntel Classroom includes a new **Education suite** workspace.
- A canonical `BioIntel Education Suite` page is registered in navigation.
- Career Hub includes a new **Application studio** tab.
- Education Home links directly to the suite.
- Shiro AI can suggest the Education Suite for lesson, quiz, whiteboard, notebook, classroom and learning queries.
- Normal UI surfaces use BioIntel names.
- Upstream identities, when an institution installs an external service, remain subject to legal notices and upstream terms.

## Security and truthfulness

- No heavy server platform is silently bundled or installed.
- The local Python runner uses isolated mode, source validation and timeouts, but is not described as a hardened sandbox.
- High-risk code execution is routed to an optional institution-operated BioIntel Code Sandbox.
- Code similarity is explicitly labelled as a review indicator.
- Offline resources are recorded with SHA-256 provenance.
- Opportunity, credential and learning-record governance remains institution-controlled.
