# Shiro AI developer architecture and API

## Canonical implementation

`src/biointel/shiro` is the canonical Shiro implementation. Existing BioIntel Copilot, connected providers, `rag_v217`, PDF RAG, project registry, report tools, scientific modules, and evidence registry remain unchanged for compatibility.

```text
Streamlit page / FastAPI router
    -> ShiroOrchestrator
        -> language detection + query routing + biomedical safety
        -> ingestion -> validators/extractors -> document-aware chunks
        -> embedding provider -> persistent SQLite vectors
        -> project-filtered hybrid retrieval -> optional local reranker
        -> metadata citation builder + citation validator
        -> grounded local generation | optional loopback Ollama
        -> project-scoped conversations, sources, and jobs
        -> report/module normalization adapters
```

## Package map

- `api/`: typed schemas, request envelopes, SSE, project-scoped routes.
- `core/`: orchestration, language, routing, safety, cancellation, background jobs.
- `ingestion/`: safe extraction, prompt-injection neutralization, chunking, batching, deletion, rebuild.
- `retrieval/`: embedding interface, hash and optional sentence-transformer providers, hybrid search, filters, reranker.
- `generation/`: evidence-only local provider and loopback-only optional Ollama provider.
- `citations/`: citation construction and active-project/context validation.
- `storage/`: SQLite repositories and migrations for sources, chunks, jobs, conversations, messages.
- `integrations/`: project discovery, normalized report/module evidence, demo evidence, external-query privacy boundary.
- `ui/`: Streamlit project workspace, chat, settings, jobs, source manager, citations, and demo controls.

## Project isolation and storage

Every source, chunk, job, conversation, message, retrieval query, preview, and mutation carries a `project_id`. SQL source/chunk/conversation/job reads include the active project boundary. Citation validation rejects any citation outside the active project or retrieved context.

Original evidence is stored below `SHIRO_DATA_DIR/evidence/<sha256(project_id)>/`. User filenames never become directories. API responses remove `file_path`. Deletes resolve and verify the managed evidence root before removing a file.

`shiro.sqlite3` uses WAL mode and stores projects, sources, chunks/vectors, job state/results/cancellation, conversations, and messages. Initialization adds missing job columns for existing Shiro databases without dropping data.

## Ingestion and chunking

The extractor supports text, Markdown, tables, JSON, text PDFs, optional reviewed local OCR for image PDFs, DOCX, HTML, FASTA/FASTQ summaries, VCF, BED, GFF/GTF, and notebooks. It validates filename/path safety, extension, maximum size, useful signatures, encodings, corruption, and encryption where practical. OCR is opt-in, page-bounded, uses the existing local Tesseract pipeline, and never downloads binaries or language data. It never executes uploaded content.

Document-aware sections preserve headings and page/row/result locations. Chunking prefers paragraph, line, sentence, semicolon, then whitespace boundaries; overlap is bounded. Source and chunk metadata store parent IDs, source hash, embedding/preprocessing/chunking versions, index time, prompt-injection findings, module/report IDs, and provenance supplied by adapters.

SHA-256 deduplication is project scoped and skips unchanged embedding. Embeddings run in batches. FASTA/FASTQ output contains statistics, not raw sequences/reads.

## Embeddings, retrieval, and reranking

`EmbeddingProvider` is provider independent. Default `HashEmbeddingProvider` is deterministic, multilingual-token aware, dependency-free, and offline. Optional `LocalSentenceTransformerEmbeddingProvider` loads only local model files unless the operator explicitly sets `SHIRO_ALLOW_MODEL_DOWNLOADS=true`; missing packages/models fail with an actionable error.

Retrieval combines cosine similarity, BM25-style keyword scoring, and term coverage. It supports source ID/type, report ID, module ID, internal/external, and upload-date filters. Fusion results are deduplicated and top-k bounded. Optional `ConservativeLocalReranker` is dependency-free and preserves the original hybrid components; disabling it returns the normal ranking.

## Generation and cancellation

`GroundedLocalProvider` produces deterministic extractive answers and requires no network/model. `OllamaLocalProvider` is optional, accepts loopback URLs only, uses low temperature, sends selected chunks rather than full documents, and maps timeouts/provider errors. It is never enabled or selected silently.

The SSE endpoint registers a request cancellation token and exposes `POST /requests/{request_id}/cancel`. Orchestration checks cancellation before processing, after retrieval, and before generation. Streamlit shows an active stop control during response construction. Job cancellation is independent and durable in SQLite.

External OpenAI-compatible evidence generation and literature/web search remain fail-closed until a separately reviewed provider/consent adapter exists. No fake external result is possible.

## Jobs

`ShiroJobManager` uses a bounded local thread pool; no Redis/Celery dependency is required. Ingestion and index rebuild jobs have queued, running, completed, failed, or cancelled states, progress, timestamps, error details, result JSON, and a cancellation flag. Status/list/cancel operations require the matching project.

Synchronous ingest/rebuild remain for compatibility. API callers select background ingest with a form flag and background rebuild with the typed request flag.

## Report and module adapters

`normalize_report` creates a curated Markdown evidence record with report, module, analysis, and generation metadata. `normalize_module_result` creates a JSON evidence record with summary, parameters, QC, and at most 100 selected rows. It explicitly marks raw results as not included. Adapters call the same validated ingestion/index/citation path as uploads.

## Synthetic demo

`SHIRO-SYNTHETIC-DEMO` contains two deterministic, clearly labelled synthetic sources, multilingual questions, and an expected negative case. Demo create is idempotent through hash deduplication. Reset deletes only this project and its managed files.

## API

Mounted under `/api/shiro`:

- `GET /health`, `/capabilities`, `/providers`
- `POST /chat`, `/chat/stream`, `/requests/{request_id}/cancel`
- `POST /retrieve`
- `POST /ingest`; `GET /ingestion/{job_id}`; `POST /ingestion/{job_id}/cancel`; `GET /jobs`
- `POST /index/rebuild`; `GET /index/status`
- `GET|POST /conversations`; `GET|PATCH|DELETE /conversations/{id}`; `POST /conversations/{id}/clear`
- `GET /sources`; `GET|DELETE /sources/{id}`
- `POST /integrations/report`; `POST /integrations/module-result`
- `POST|DELETE /demo`

Pydantic models forbid extra request fields. Responses contain a stable request ID and data envelope. Error envelopes include a request ID, code, and actionable message. Project-access failures return 403, provider failures 503, and cancellations 409 where applicable.

## Verified limitations

- Image-PDF OCR is available only when the operator installs local Tesseract and enables it; DOCX image OCR is not bundled. Shiro does not silently invoke or download OCR engines or language data.
- A learned local embedding works only after its optional dependency and model are explicitly installed by the operator.
- Ollama behavior requires an operator-installed local service/model; automated tests verify its fail-closed boundary, not a model-dependent scientific answer.
- No external literature/web or OpenAI project-evidence adapter is enabled, by design. Existing BioIntel connected tooling is preserved separately.
- The complete legacy BioIntel test matrix is much larger than the focused Shiro regression suite; Shiro tests, isolated API smoke, Streamlit AppTest, compile, and local HTTP startup are the executed release evidence for this change.