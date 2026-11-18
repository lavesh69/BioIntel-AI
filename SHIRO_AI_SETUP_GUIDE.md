# BioIntel Shiro AI Setup

Shiro AI supports four intelligence modes:

- **Auto · local first:** uses Shiro Local Intelligence first. A cloud fallback is used only when it is configured, enabled in setup, and approved for the current request.
- **Local Private:** uses local chat, vision, and reasoning models through the loopback runtime. No cloud provider is called.
- **Online Enhanced:** uses a configured online model and then the backup free-model router. Explicit cloud consent is required for every request.
- **Offline Evidence Only:** deterministic retrieval and citations without a generative model.

Run `SETUP_SHIRO_AI_WINDOWS.bat` to install the optional local runtime and models. Recommended local models are:

- Balanced chat: `qwen3:4b`
- Images: `gemma3:4b`
- Deep reasoning: `deepseek-r1:8b`
- Local embeddings: `embeddinggemma`

Cloud keys are not stored in source files. Online providers have age, region, organization and acceptable-use requirements. The current Gemini developer terms require an adult user and professional or business use; confirm eligibility in Shiro AI setup before enabling online mode. Open **Shiro AI → Shiro AI setup** and enter the keys there. On Windows, credentials are protected with the current Windows account's Data Protection API. Cloud processing remains blocked until both provider eligibility is confirmed in setup and the per-request consent toggle is enabled. Unpaid online services may use submitted content under their current terms, so do not submit confidential, clinical, personal, or unpublished research information.

Shiro AI is a research and education assistant. It does not establish clinical validity, provide a diagnosis, or replace qualified professional review.
