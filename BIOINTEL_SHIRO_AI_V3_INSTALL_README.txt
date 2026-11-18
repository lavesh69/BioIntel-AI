BIOINTEL AI 15.6.0 — SHIRO AI LOCAL-FIRST ASSISTANT V3
========================================================

This four-part release contains the complete prior Career Hub and P0/P1/P2
scientific-integration build plus the Shiro AI local-first assistant upgrade.

IMPORTANT
---------
1. Download all four ZIP parts from this exact release.
2. Do not mix them with older Part1/Part2/Part3/Part4 files.
3. Place all four ZIPs in one folder.
4. Extract all four into the same destination, recommended:

   C:\BioIntel220

5. Confirm the merged application folder is:

   C:\BioIntel220\BioIntel-Step220

6. Run:

   START_HERE_WINDOWS.bat

   Or run in order:

   INSTALL_WINDOWS.bat
   RUN_BOTH_WINDOWS.bat

SHIRO LOCAL AI SETUP
--------------------
After the main application installation, run:

   SETUP_SHIRO_AI_WINDOWS.bat

You can also open:

   BIOINTEL_ENGINE_SETUP.bat

and choose the Shiro AI setup option.

The setup utility can:
- detect or install the optional local model runtime;
- install the balanced local chat model;
- install optional vision, reasoning and embedding models;
- verify the local API and installed models;
- show the setup/privacy guide.

Default recommended model profiles:
- Balanced chat: qwen3:4b
- Image understanding: gemma3:4b
- Reasoning: deepseek-r1:8b
- Local embeddings: embeddinggemma

Model files are not bundled in the four ZIPs. Their download size can be large,
and suitability depends on the target computer's RAM, storage and graphics
hardware. Start with the balanced chat model before installing every optional
model.

SHIRO INTELLIGENCE MODES
------------------------
1. Auto · local first
   Uses local Shiro intelligence first. Online fallback remains blocked unless
   it is configured, enabled, eligibility-confirmed and approved for that request.

2. Local Private
   Uses local chat/vision/reasoning models through the loopback runtime. No cloud
   provider is called.

3. Online Enhanced
   Uses the configured online provider and optional backup free-model router.
   Provider eligibility confirmation and per-request cloud consent are required.

4. Offline Evidence Only
   Uses deterministic BioIntel retrieval, citations and evidence synthesis without
   calling a generative model.

SHIRO FEATURES INCLUDED
-----------------------
- Chat-style general conversation in English, Hindi and Hinglish
- Real multi-turn conversation context and persistent local history
- New, rename and delete conversation controls
- BioIntel project/document retrieval with evidence citations
- PDF, DOCX, TXT, CSV, TSV, FASTA, VCF and image attachments
- Local image-question routing when the vision model is installed
- BioIntel module-action suggestions and direct workspace links
- Local-first automatic provider routing with controlled fallback
- Provider health checks and setup guidance
- Windows-protected online API-key storage
- Explicit cloud eligibility and per-request consent gates
- JSON, Markdown, DOCX and PDF conversation exports
- Optional local voice transcription and Windows text-to-speech
- Research-use warnings and evidence/uncertainty boundaries

ONLINE PROVIDER NOTICE
----------------------
Online API keys are not bundled. Enter them only in Shiro AI setup. Confirm that
current provider age, region, organization and acceptable-use requirements apply
to you before enabling online mode.

Unpaid online services may retain, review or use submitted content under their
current terms. Do not send confidential company data, clinical data, personal
data, patient data or unpublished research through unpaid online modes. Use Local
Private or Offline Evidence Only for sensitive work.

VALIDATION BOUNDARY
-------------------
The delivered code, archives, manifests and Linux-executable regression tests were
verified in the packaging environment. Native Windows installation, live local
model inference, GPU acceleration, microphone access and real cloud API calls must
be verified on the target Windows computer after setup.
