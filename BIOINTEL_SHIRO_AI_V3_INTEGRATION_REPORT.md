# BioIntel Shiro AI v3 — Local-First Assistant Integration Report

**Release base:** BioIntel AI 15.6.0 R15, P0/P1/P2 Scientific Integration Runtime v2, Career Hub Theme Final  
**Upgrade:** Shiro AI local-first conversational assistant v3  
**Build date:** 2026-08-06

## Objective

Shiro AI has been upgraded from a primarily evidence-query interface into a BioIntel-native conversational assistant. The implementation preserves the existing retrieval, citation and project boundaries while adding local general conversation, multi-turn context, optional free-model routes, image attachments, module actions, secure provider setup, voice utilities and document exports.

## Runtime architecture

Shiro uses a controlled four-route architecture:

1. **Shiro Evidence Engine** — deterministic offline retrieval and citation synthesis.
2. **Shiro Local Intelligence** — loopback-only local chat, vision and reasoning through an optional Windows local-model runtime.
3. **Shiro Online Intelligence** — optional configured online provider, available only after eligibility confirmation and per-request consent.
4. **Shiro Backup Intelligence** — optional backup model router, subject to the same cloud boundaries.

Auto mode is local-first. Failure of an optional model or provider produces a controlled fallback or setup-required state instead of terminating the BioIntel application.

## Conversational capabilities

- General conversation works even when no BioIntel evidence document has been indexed.
- Retrieval-required questions retain citation-aware and insufficient-evidence behaviour.
- Real previous user and assistant messages are passed to supported model routes as bounded multi-turn history.
- Conversation history remains in BioIntel local storage and supports new, rename and delete operations.
- English, Hindi and Hinglish language handling is retained.
- Chat responses include route metadata, general-knowledge status and evidence citations where applicable.

## Local and online model integration

### Local model profiles

- Balanced chat profile: `qwen3:4b`
- Image profile: `gemma3:4b`
- Reasoning profile: `deepseek-r1:8b`
- Embedding profile: `embeddinggemma`

The model identities are exposed only in the technical setup boundary where users must know what is downloaded. Normal Shiro product surfaces use BioIntel public identities.

### Online routes

- Optional online-enhanced provider
- Optional free-model backup router
- No API keys embedded in source, reports, archives or manifests
- Provider eligibility confirmation required before online controls are enabled
- Explicit cloud consent required for each request
- Warnings block casual use with confidential, clinical, personal or unpublished research data

## Attachments and evidence

Shiro supports BioIntel ingestion and question answering over:

- PDF and DOCX documents
- TXT, Markdown, CSV and TSV
- FASTA and VCF research files
- PNG, JPG/JPEG and WebP images

Image files receive an image-evidence record with dimensions, MIME type, checksum and local file path. When the local vision profile is available, the image can be included in the model request. Evidence retrieval, source records and citations remain separate from general-model output.

## BioIntel tool and module actions

The assistant can suggest only registered BioIntel pages that exist in the delivered package. Action profiles cover sequence analysis, variant analysis, CRISPR, ADMET, pathway analysis, metagenomics, single-cell analysis, cancer genomics, multi-omics, docking, protein design, career opportunities and visual workflows. Suggestions are links/prepared actions; Shiro does not silently run destructive operations.

## Security and privacy

- On Windows, provider credentials use the current Windows account's Data Protection API.
- A local encrypted fallback is used only on platforms where Windows protection is unavailable.
- Credentials are stored outside source code and are never written to chat exports.
- Local Private mode does not call cloud providers.
- Provider access is fail-closed when eligibility or current-request consent is missing.
- The legacy paid-provider route remains explicitly disabled in this free/local integration.

## Voice and export

- Optional offline voice transcription uses the existing local speech dependency when installed.
- Windows text-to-speech uses the local Windows speech interface.
- Conversations export to JSON, Markdown, DOCX and PDF.
- Generated DOCX and PDF samples were rendered and visually checked for readable headings, role labels and wrapped text.

## Windows setup integration

New entry points:

- `SETUP_SHIRO_AI_WINDOWS.bat`
- `VERIFY_SHIRO_AI_WINDOWS.bat`
- `SHIRO_AI_SETUP_GUIDE.md`

`BIOINTEL_ENGINE_SETUP.bat` includes a direct Shiro setup option. Model installation remains optional and isolated from the core BioIntel Python environment to reduce dependency conflicts in `INSTALL_WINDOWS.bat` and `RUN_BOTH_WINDOWS.bat`.

## Preserved platform scope

- Career, Internship & Scholarship Hub remains present.
- P0, P1 and P2 scientific integrations remain present.
- Existing BioIntel modules, routes, database migrations and user data boundaries are preserved.
- No module or feature source was removed for this upgrade.
- Legally required upstream identities are retained in Legal & Component Notices and technical setup/diagnostic boundaries.

## Verification completed in the build environment

- Shiro-specific test groups passed.
- Current combined Career Hub, scientific integration, public-branding, Shiro and Windows-script regression suite passed.
- Shiro Python source and canonical page compilation passed.
- Public-branding audit passed.
- DOCX and PDF export rendering visual QA passed.
- Archive CRC, merged file-set and fresh-extraction SHA-256 verification are performed during final four-part packaging.

## Validation not executable in the build environment

The Linux packaging environment cannot establish final proof for native Windows installer dialogs, the target computer's local model runtime, live model downloads/inference, microphone permissions, Windows speech output, GPU acceleration, WSL workers or real online API credentials. These must be checked on the target Windows machine with the included setup and verification scripts.
