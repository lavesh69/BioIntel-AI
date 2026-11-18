# Third-Party Notices

BioIntel AI depends on third-party Python packages and may integrate separately installed scientific engines and databases. Each component remains governed by its own licence. The Step 191 SBOM records declared dependencies; it does not grant redistribution rights for external databases, model weights or engines. Before public release, review every bundled asset and remove anything whose licence does not permit redistribution.

## Shiro AI Local and Optional Online Runtime

Shiro AI is local-first. The BioIntel package does not bundle the local model runtime, model weights, cloud credentials, or cloud quota. Users explicitly install or pull local components and accept their upstream terms. Optional online services require a user-supplied key and per-request cloud consent. Free quotas and routed model availability may change.

| BioIntel public integration | Upstream component | Licence / terms record | Official source | Packaging state |
|---|---|---|---|---|
| Shiro Local Intelligence Runtime | Ollama | MIT source licence; installed application notices remain authoritative | https://github.com/ollama/ollama | not bundled; user installed |
| Shiro Balanced Local Chat Model | Qwen3 4B | Apache-2.0 model terms | https://github.com/QwenLM/Qwen3 | not bundled; user pulled |
| Shiro Local Vision Model | Gemma 3 4B | Gemma Terms of Use | https://ai.google.dev/gemma/terms | not bundled; user terms acceptance required |
| Shiro Local Reasoning Model | DeepSeek-R1 Distill 8B | exact model-card and base-model terms must be reviewed | https://ollama.com/library/deepseek-r1:8b | not bundled; user pulled |
| Shiro Local Embedding Model | EmbeddingGemma | Gemma model terms | https://ollama.com/library/embeddinggemma | not bundled; user pulled |
| Shiro Online Intelligence | Google Gemini API | Google APIs Terms and Gemini API Additional Terms | https://ai.google.dev/gemini-api/terms | external service; user key and per-request consent |
| Shiro Backup Intelligence | OpenRouter API and routed models | OpenRouter Terms plus selected model/provider terms | https://openrouter.ai/terms | external service; user key; routed availability varies |

The exact licence or service terms shown by the upstream provider at installation or request time are authoritative. Do not submit confidential, personal, clinical, or unpublished research data to an unpaid online service without an approved data-governance basis.


## BioIntel Education Suite optional service compatibility

The BioIntel Education Suite ships BioIntel-authored local functionality and provider-neutral endpoint connectors. No upstream multi-user classroom, LMS, videoconferencing, notebook-server, search, applicant-tracking or offline-content service is bundled by this integration. Institutions selecting an external service must preserve that service's original licence and attribution. See `docs/legal/BIOINTEL_EDUCATION_COMPATIBILITY_NOTICE.md`.
