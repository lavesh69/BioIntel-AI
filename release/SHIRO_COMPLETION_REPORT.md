# Shiro AI full Windows integration report

- Canonical Shiro package, Streamlit page, and FastAPI router are integrated.
- Local persistent evidence RAG, project isolation, hybrid retrieval, citations, multilingual prompts, conversations, jobs/cancellation, source lifecycle, report/module adapters, and synthetic demo are included.
- Optional local sentence-transformer and loopback Ollama paths fail closed and never download silently.
- Image-PDF OCR can be explicitly enabled with local Tesseract; it is page-bounded, review-labelled, and never downloads an OCR engine or language data.
- The Windows offline wheelhouse contains the pinned PDF/OCR Python dependencies.
- Four balanced ZIP archives include SHA-256 source and per-part manifests and are reconstructed and hash-verified after creation.
- Windows runtime handover ignores only unverified reused PIDs, never terminates unrelated processes, and still blocks on verified BioIntel processes that cannot stop safely.
