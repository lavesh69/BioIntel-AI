# Shiro AI user, privacy, provider, and operations guide

Shiro AI is BioIntel AI's local-first, evidence-grounded biomedical research assistant. It searches only the active project's indexed evidence unless an external capability is separately configured and explicitly selected. It is not a clinical decision system.

## Open Shiro on Windows

Run `RUN_APP_WINDOWS.bat`, then open **Shiro AI** from the Intelligence category. The existing **BioIntel Copilot** remains available for legacy connected-provider workflows.

For a direct development run:

```powershell
$env:PYTHONPATH = "$PWD\src"
streamlit run pages\273_Shiro_AI.py
```

## Evidence ingestion and indexing

Select the active project and attach evidence in the chat composer. Supported formats are TXT, Markdown, CSV, TSV, JSON, PDF, DOCX, HTML, FASTA, FASTQ, VCF, BED, GFF, GTF, and Jupyter notebooks.

Shiro validates filenames, extensions, size, practical signatures, parse integrity, encryption state where supported, encodings, and duplicate SHA-256 content. Text PDFs work by default. Optional image-PDF OCR is local-only, bounded, review-labelled, and never downloads an engine or language model. It stores managed originals below the Shiro data directory and persists source metadata, chunks, vectors, jobs, conversations, and messages in `shiro.sqlite3`.

Use **Background attachment indexing** for long files. Progress and cancellation are available under **Index & jobs**. Index rebuild can also run in the background. Terminal job state and error details persist in SQLite.

FASTA and FASTQ are summarized. Raw reads, sequences, and quality strings are not copied into conversational context. Uploaded macros, scripts, and code are never executed. Prompt-like instructions inside evidence are neutralized before indexing.

The **Evidence source manager** lists the active project's sources and supports explicit deletion. Deleted managed files and their chunks are removed together. Source and job endpoints require the active project ID.

## Asking questions

Shiro detects English, Hindi in Devanagari, and Hinglish. Conservative query normalization preserves genes, proteins, variants, accessions, formulas, pathway names, and units.

Local generation is evidence-only. Each citation is built from a real retrieved chunk and validated against the active project and exact answer context. Citation details include the source, location, project, source type, SHA-256 identity, internal/external status, synthetic flag, and relevance score. **Open source preview** shows indexed text and lets the local user open/download the managed original.

If evidence is insufficient, Shiro returns no scientific claim and no citation. Clinical diagnosis, dosing, or patient-specific treatment requests are blocked with a research-safety message.

Retrieval combines local hash embeddings, BM25-style keyword scoring, term coverage, metadata/source filters, and optional dependency-free local reranking. Report ID, module ID, source type, source ID, internal/external, and date filters are available through the API.

## Conversation controls

Conversations are project scoped and support create, resume, rename, clear, delete, regenerate, and JSON export. Assistant answers include a copy-ready code panel. Local streaming and request cancellation are exposed; the local extractive provider normally finishes almost immediately.

## Synthetic demo

Open **Synthetic demo** and choose **Create / restore demo**. Shiro creates the isolated `SHIRO-SYNTHETIC-DEMO` project with deterministic synthetic RNA-seq report and biomarker table evidence plus English, Hindi, Hinglish, and negative questions. Every demo source and citation is marked synthetic. **Reset demo** deletes only that demo project's managed evidence and database rows.

## BioIntel report and module integration

Curated outputs can be normalized with:

- `POST /api/shiro/integrations/report`
- `POST /api/shiro/integrations/module-result`

The report adapter stores report/module/analysis provenance. The module adapter stores a summary, parameters, QC, and at most 100 selected result rows; massive raw matrices are never ingested automatically.

## Privacy and external access

Safe defaults are local generation, local deterministic embeddings, no telemetry added by Shiro, no model download, no automatic web search, no automatic external provider call, SQL-enforced project isolation, and selected chunks only in answer context.

`SHIRO_EXTERNAL_SEARCH_ENABLED=false` remains the default. No external literature adapter is configured in this build, so the UI truthfully shows the capability as unavailable and Shiro never fabricates publications. A query-redaction boundary exists for a future explicitly approved adapter.

The optional Ollama provider is loopback-only and disabled by default. Shiro never silently falls back from local extraction to Ollama or an external provider.

## Configuration

```env
SHIRO_ENABLED=true
SHIRO_DEFAULT_MODE=local
SHIRO_PROVIDER=local
SHIRO_CHAT_MODEL=grounded-extractive-v1
SHIRO_EMBEDDING_PROVIDER=local
SHIRO_EMBEDDING_MODEL=hash-multilingual-v1
SHIRO_EMBEDDING_DIMENSION=384
SHIRO_RERANKER_ENABLED=false
SHIRO_EXTERNAL_SEARCH_ENABLED=false
SHIRO_MAX_FILE_SIZE_MB=25
SHIRO_OCR_ENABLED=false
SHIRO_OCR_LANGUAGE=eng
SHIRO_OCR_MAX_PAGES=25
SHIRO_RETRIEVAL_TOP_K=6
SHIRO_CONTEXT_LIMIT=12000
SHIRO_PROJECT_ISOLATION=true
SHIRO_CHUNK_SIZE=1600
SHIRO_CHUNK_OVERLAP=160
SHIRO_ALLOW_MODEL_DOWNLOADS=false
SHIRO_OLLAMA_ENABLED=false
SHIRO_OLLAMA_BASE_URL=http://127.0.0.1:11434
SHIRO_OLLAMA_MODEL=gemma3:1b
SHIRO_GENERATION_TIMEOUT_SECONDS=60
```

`SHIRO_DATA_DIR` moves the database and managed evidence store to an approved local directory. For scanned PDFs, install the Tesseract executable and the requested language data yourself, then set `SHIRO_OCR_ENABLED=true`. OCR is capped by `SHIRO_OCR_MAX_PAGES`; low-confidence output is evidence requiring source-image review.

## Local model setup

Basic retrieval and grounded answering require no model download. `hash-multilingual-v1` is deterministic and runs in-process.

To use a learned local embedding, install `sentence-transformers` yourself, place the model locally, set `SHIRO_EMBEDDING_PROVIDER=sentence-transformers`, and set `SHIRO_EMBEDDING_MODEL` to that local model path/name. With `SHIRO_ALLOW_MODEL_DOWNLOADS=false`, Shiro requests local files only and returns an actionable error when the model is missing. Rebuild the index after changing embedding providers or dimensions.

To use Ollama, install it and pull a model explicitly outside Shiro. Then set `SHIRO_OLLAMA_ENABLED=true`, keep `SHIRO_OLLAMA_BASE_URL` on loopback, and select Ollama in the UI. Shiro sends only selected retrieved chunks to the local Ollama process.

OpenAI/external project-evidence generation is deliberately fail-closed here. Existing BioIntel connected-provider tooling remains unchanged; no API key is stored, printed, or tested by Shiro.

## API summary

The `/api/shiro` router provides health, capabilities, providers, chat, SSE stream, request cancellation, retrieval, synchronous/background ingest, project-scoped job status/list/cancel, synchronous/background index rebuild, source list/preview/delete, conversation CRUD/clear, report/module adapters, and demo create/reset. Responses use request-ID envelopes; source responses omit managed filesystem paths.

## Troubleshooting

- **No evidence:** attach a source and check the index count or background job state.
- **Insufficient evidence:** ask with a specific gene, variant, report, module, or result term.
- **PDF has no text:** provide a text PDF, or install local Tesseract and explicitly set `SHIRO_OCR_ENABLED=true`; OCR is never silently enabled or downloaded.
- **Duplicate source:** Shiro reuses the same project source by SHA-256 without re-embedding.
- **Provider unavailable:** use local mode, or explicitly configure loopback Ollama.
- **Wrong project:** select the intended project; retrieval, jobs, sources, and conversations cannot cross boundaries.
- **Embedding mismatch:** restore the previous embedding configuration or rebuild the active project's index.

## Tests

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest tests.test_shiro_ai tests.test_shiro_ai_completion -v
python -m compileall -q src\biointel\shiro pages\273_Shiro_AI.py src\biointel\api\main.py
```