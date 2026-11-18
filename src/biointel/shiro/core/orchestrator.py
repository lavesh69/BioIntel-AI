from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from biointel.shiro.citations.builder import build_citations
from biointel.shiro.citations.validator import validate_citations
from biointel.shiro.config import ShiroSettings
from biointel.shiro.core.jobs import ShiroJobManager
from biointel.shiro.core.language import detect_language
from biointel.shiro.core.query_router import route_query
from biointel.shiro.core.safety import clinical_safety_message
from biointel.shiro.exceptions import ExternalAccessDisabledError, ProviderUnavailableError, UserCancellationError
from biointel.shiro.generation.providers.gemini import GeminiProvider
from biointel.shiro.generation.providers.ollama import OllamaLocalProvider
from biointel.shiro.generation.providers.openrouter import OpenRouterProvider
from biointel.shiro.generation.service import GroundedLocalProvider, ProviderStatus
from biointel.shiro.ingestion.service import IngestionService
from biointel.shiro.integrations.demo import DEMO_PROJECT_ID, DEMO_PROJECT_NAME, DEMO_QUESTIONS, DEMO_REPORT, DEMO_TABLE
from biointel.shiro.integrations.evidence import NormalizedEvidence
from biointel.shiro.integrations.modules import normalize_module_result
from biointel.shiro.integrations.projects import ProjectOption, list_project_options
from biointel.shiro.integrations.reports import normalize_report
from biointel.shiro.integrations.tools import suggest_actions
from biointel.shiro.models import ChatResponse, IngestionResult, RetrievalResult, SourceRecord
from biointel.shiro.retrieval.reranker import ConservativeLocalReranker
from biointel.shiro.retrieval.service import RetrievalService
from biointel.shiro.retrieval.vector_store import build_embedding_provider
from biointel.shiro.runtime_config import PROVIDER_PUBLIC_NAMES, ShiroRuntimeConfig
from biointel.shiro.secure_store import ShiroSecretStore
from biointel.shiro.storage.repositories import ShiroRepository


class ShiroOrchestrator:
    def __init__(self, root: str | Path | None = None, data_dir: str | Path | None = None) -> None:
        self.settings = ShiroSettings.from_environment(root, data_dir)
        self.runtime = ShiroRuntimeConfig.load(self.settings.data_dir)
        self.secrets = ShiroSecretStore(self.settings.data_dir)
        self.repository = ShiroRepository(self.settings.database_path)
        self.embeddings = build_embedding_provider(
            self.settings.embedding_provider,
            self.settings.embedding_model,
            self.settings.embedding_dimension,
            allow_downloads=self.settings.allow_model_downloads,
        )
        self.ingestion = IngestionService(self.settings, self.repository, self.embeddings)
        self.reranker = ConservativeLocalReranker()
        self.retrieval = RetrievalService(self.repository, self.embeddings, self.reranker)
        self.local_provider = GroundedLocalProvider()
        self.ollama_provider = OllamaLocalProvider(
            self.runtime.local_model,
            self.settings.ollama_base_url,
            self.settings.generation_timeout_seconds,
            vision_model=self.runtime.local_vision_model,
            reasoning_model=self.runtime.local_reasoning_model,
            max_output_tokens=self.runtime.max_output_tokens,
            temperature=self.runtime.temperature,
        ) if self.settings.ollama_enabled else None
        gemini_key = self.secrets.get("gemini_api_key", "GEMINI_API_KEY")
        openrouter_key = self.secrets.get("openrouter_api_key", "OPENROUTER_API_KEY")
        self.gemini_provider = GeminiProvider(
            gemini_key,
            self.runtime.gemini_model,
            self.settings.generation_timeout_seconds,
            self.runtime.max_output_tokens,
            self.runtime.temperature,
        ) if gemini_key else None
        self.openrouter_provider = OpenRouterProvider(
            openrouter_key,
            self.runtime.openrouter_model,
            self.settings.generation_timeout_seconds,
            self.runtime.max_output_tokens,
            self.runtime.temperature,
        ) if openrouter_key else None
        self.jobs = ShiroJobManager(self.repository, self.ingestion)

    def reload_runtime(self) -> None:
        self.__init__(self.settings.root, self.settings.data_dir)

    def projects(self) -> tuple[ProjectOption, ...]:
        values = {item.project_id: item for item in list_project_options(self.settings.root)}
        for item in self.repository.list_projects():
            project_id = str(item["project_id"])
            values[project_id] = ProjectOption(project_id, str(item["name"]), "shiro", synthetic=project_id == DEMO_PROJECT_ID)
        return tuple(sorted(values.values(), key=lambda item: item.name.casefold()))

    def providers(self) -> tuple[ProviderStatus, ...]:
        mode = self.runtime.mode
        return (
            ProviderStatus("local", self.local_provider.model, True, False, mode == "offline_evidence", "Deterministic evidence-only response engine; no network or model download.", PROVIDER_PUBLIC_NAMES["local"], True),
            ProviderStatus("ollama", self.runtime.local_model, self.ollama_provider is not None, False, mode in {"auto", "local_private"}, "Private loopback model runtime with multi-turn chat and optional local vision.", PROVIDER_PUBLIC_NAMES["ollama"], None),
            ProviderStatus("gemini", self.runtime.gemini_model, self.gemini_provider is not None, True, mode == "online_enhanced", "Optional online enhancement; requires an API key and explicit cloud consent for every request.", PROVIDER_PUBLIC_NAMES["gemini"], None),
            ProviderStatus("openrouter", self.runtime.openrouter_model, self.openrouter_provider is not None, True, False, "Optional free-model fallback; availability and free limits can change.", PROVIDER_PUBLIC_NAMES["openrouter"], None),
        )

    def provider_health(self, provider: str) -> dict[str, Any]:
        if provider == "local":
            return {"healthy": True, "public_name": PROVIDER_PUBLIC_NAMES[provider], "detail": "Ready without network."}
        if provider == "ollama":
            if self.ollama_provider is None:
                return {"healthy": False, "public_name": PROVIDER_PUBLIC_NAMES[provider], "detail": "Local runtime is disabled."}
            result = self.ollama_provider.health()
            result.update({"public_name": PROVIDER_PUBLIC_NAMES[provider], "model": self.runtime.local_model})
            return result
        if provider == "gemini":
            if self.gemini_provider is None:
                return {"healthy": False, "public_name": PROVIDER_PUBLIC_NAMES[provider], "detail": "API key is not configured."}
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.runtime.gemini_model}"
            request = Request(url, headers={"x-goog-api-key": self.gemini_provider.api_key})
        elif provider == "openrouter":
            if self.openrouter_provider is None:
                return {"healthy": False, "public_name": PROVIDER_PUBLIC_NAMES[provider], "detail": "API key is not configured."}
            request = Request("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {self.openrouter_provider.api_key}"})
        else:
            raise ValueError("Unknown provider.")
        try:
            with urlopen(request, timeout=8) as response:
                healthy = 200 <= int(response.status) < 300
            return {"healthy": healthy, "public_name": PROVIDER_PUBLIC_NAMES[provider], "model": getattr(self, f"{provider}_provider").model, "detail": "Connection verified." if healthy else "Connection failed."}
        except (OSError, URLError) as exc:
            return {"healthy": False, "public_name": PROVIDER_PUBLIC_NAMES[provider], "detail": f"{type(exc).__name__}: {exc}"}

    def capabilities(self) -> dict[str, object]:
        return {
            "enabled": self.settings.enabled,
            "local_first": True,
            "project_isolation": self.settings.project_isolation,
            "cloud_requires_per_request_consent": True,
            "languages": ["English", "Hindi", "Hinglish"],
            "supported_extensions": sorted(["txt", "md", "csv", "tsv", "json", "pdf", "docx", "html", "fasta", "fastq", "vcf", "bed", "gff", "gtf", "ipynb", "png", "jpg", "jpeg", "webp"]),
            "embedding": {"provider": self.settings.embedding_provider, "model": self.settings.embedding_model, "dimension": self.embeddings.dimension, "downloads_allowed": self.settings.allow_model_downloads},
            "generation": {"mode": self.runtime.mode, "multi_turn": True, "local_model": self.runtime.local_model, "vision_model": self.runtime.local_vision_model, "reasoning_model": self.runtime.local_reasoning_model, "online_configured": self.gemini_provider is not None, "backup_configured": self.openrouter_provider is not None},
            "reranker": {"available": True, "enabled_by_default": self.settings.reranker_enabled, "model": self.reranker.name},
            "jobs": {"background": True, "cancellation": True, "persistent_status": True},
            "source_lifecycle": {"delete": True, "rebuild": True, "deduplicate": True},
            "integrations": {"reports": True, "module_results": True, "module_actions": True, "external_literature": False},
            "exports": ["json", "markdown", "docx", "pdf"],
            "voice": {"input": True, "local_transcription": True, "windows_tts": True},
            "ocr": {"available": True, "enabled": self.settings.ocr_enabled, "engine": "local-tesseract", "language": self.settings.ocr_language, "max_pages": self.settings.ocr_max_pages, "downloads_allowed": False},
            "synthetic_demo": {"available": True, "project_id": DEMO_PROJECT_ID},
        }

    def health(self) -> dict[str, object]:
        return {"status": "ok" if self.settings.enabled else "disabled", "database": str(self.settings.database_path), "privacy_mode": self.runtime.mode, "cloud_calls": "per-request consent required", "providers": [item.__dict__ for item in self.providers()]}

    def ingest(self, project_id: str, content: bytes, filename: str, **kwargs: object) -> IngestionResult:
        return self.ingestion.ingest_bytes(project_id, content, filename, **kwargs)

    def ingest_normalized(self, project_id: str, evidence: NormalizedEvidence, *, project_name: str = "") -> IngestionResult:
        return self.ingest(project_id, evidence.content, evidence.filename, project_name=project_name or project_id, source_type=evidence.source_type, internal=evidence.internal, external=evidence.external, synthetic=evidence.synthetic, confidential=evidence.confidential, metadata=evidence.metadata)

    def ingest_report(self, project_id: str, report_id: str, title: str, body: str, **kwargs: object) -> IngestionResult:
        return self.ingest_normalized(project_id, normalize_report(report_id, title, body, **kwargs))

    def ingest_module_result(self, project_id: str, module_id: str, analysis_id: str, summary: str, **kwargs: object) -> IngestionResult:
        return self.ingest_normalized(project_id, normalize_module_result(module_id, analysis_id, summary, **kwargs))

    def submit_ingestion(self, project_id: str, content: bytes, filename: str, **kwargs: object) -> dict[str, object]:
        return self.jobs.submit_ingestion(project_id, content, filename, **kwargs)

    def submit_index_rebuild(self, project_id: str) -> dict[str, object]:
        return self.jobs.submit_rebuild(project_id)

    def retrieve(self, project_id: str, query: str, *, top_k: int | None = None, source_ids: list[str] | None = None, source_types: list[str] | None = None, module_id: str | None = None, report_id: str | None = None, internal_only: bool = False, external_only: bool = False, date_from: str | None = None, date_to: str | None = None, rerank: bool | None = None) -> tuple[RetrievalResult, ...]:
        return self.retrieval.search(project_id, query, top_k=top_k or self.settings.retrieval_top_k, source_ids=source_ids, source_types=source_types, module_id=module_id, report_id=report_id, internal_only=internal_only, external_only=external_only, date_from=date_from, date_to=date_to, rerank=self.settings.reranker_enabled if rerank is None else rerank)

    def create_demo(self) -> dict[str, object]:
        self.repository.upsert_project(DEMO_PROJECT_ID, DEMO_PROJECT_NAME)
        first = self.ingest(DEMO_PROJECT_ID, DEMO_REPORT, "synthetic-rnaseq-report.md", project_name=DEMO_PROJECT_NAME, source_type="biointel_report", synthetic=True, metadata={"report_id": "DEMO-RNA-001", "module_id": "rna_seq", "demo": True})
        second = self.ingest(DEMO_PROJECT_ID, DEMO_TABLE, "synthetic-biomarkers.tsv", project_name=DEMO_PROJECT_NAME, source_type="module_result", synthetic=True, metadata={"analysis_id": "DEMO-BIOMARKER-001", "module_id": "biomarker_discovery", "demo": True})
        return {"project_id": DEMO_PROJECT_ID, "project_name": DEMO_PROJECT_NAME, "source_ids": [first.source.source_id, second.source.source_id], "questions": list(DEMO_QUESTIONS), "synthetic": True}

    def reset_demo(self) -> dict[str, object]:
        paths = self.repository.delete_project(DEMO_PROJECT_ID)
        evidence_root = (self.settings.data_dir / "evidence").resolve()
        deleted = 0
        for value in paths:
            path = Path(value).resolve()
            if path.is_relative_to(evidence_root) and path.is_file():
                path.unlink()
                deleted += 1
        return {"project_id": DEMO_PROJECT_ID, "deleted_sources": deleted, "reset": True}

    def _provider_chain(self, requested: str, cloud_allowed: bool) -> tuple[object, ...]:
        requested = (requested or self.runtime.mode).strip().casefold()
        if requested == "openai":
            # Legacy compatibility: the earlier paid external provider remains disabled.
            # Shiro's supported optional online paths are the explicitly configured
            # Online Intelligence and Backup Intelligence providers.
            raise ExternalAccessDisabledError("The legacy external provider is disabled in Shiro AI.")
        aliases = {"local": "offline_evidence", "ollama": "local_private", "gemini": "gemini", "openrouter": "openrouter"}
        mode = aliases.get(requested, requested)
        local = [self.ollama_provider, self.local_provider]
        cloud = [self.gemini_provider, self.openrouter_provider]
        if mode == "offline_evidence":
            candidates = [self.local_provider]
        elif mode == "local_private":
            candidates = local
        elif mode == "online_enhanced":
            if not cloud_allowed:
                raise ExternalAccessDisabledError("Online Enhanced mode requires explicit cloud consent for this request.")
            candidates = cloud + local
        elif mode == "gemini":
            if not cloud_allowed:
                raise ExternalAccessDisabledError("Shiro Online Intelligence requires explicit cloud consent.")
            candidates = [self.gemini_provider]
        elif mode == "openrouter":
            if not cloud_allowed:
                raise ExternalAccessDisabledError("Shiro Backup Intelligence requires explicit cloud consent.")
            candidates = [self.openrouter_provider]
        else:  # auto
            candidates = [self.ollama_provider]
            if cloud_allowed and self.runtime.allow_cloud_fallback:
                candidates.extend(cloud)
            candidates.append(self.local_provider)
        return tuple(item for item in candidates if item is not None)

    def _attachments(self, project_id: str, source_ids: list[str] | None) -> tuple[SourceRecord, ...]:
        values: list[SourceRecord] = []
        for source_id in (source_ids or [])[:8]:
            source = self.repository.get_source(project_id, source_id)
            values.append(source)
        return tuple(values)

    def chat(self, project_id: str, message: str, *, conversation_id: str | None = None, response_language: str = "auto", top_k: int | None = None, provider: str = "auto", external_requested: bool = False, cloud_consent: bool = False, attachment_source_ids: list[str] | None = None, rerank: bool | None = None, source_types: list[str] | None = None, cancelled: Callable[[], bool] | None = None, request_id: str | None = None) -> ChatResponse:
        if cancelled and cancelled():
            raise UserCancellationError("Shiro generation was cancelled before processing.")
        clean = " ".join(message.strip().split())
        if not clean:
            raise ValueError("A message is required.")
        language = detect_language(clean, response_language)
        if external_requested and cloud_consent and not self.runtime.cloud_eligibility_confirmed:
            raise ExternalAccessDisabledError(
                "Online services are disabled until provider eligibility and current service terms are confirmed in Shiro AI setup."
            )
        cloud_allowed = bool(cloud_consent and external_requested and self.runtime.cloud_eligibility_confirmed)
        plan = route_query(clean, language, external_requested=cloud_allowed, external_enabled=cloud_allowed)
        title = clean[:80]
        conversation = self.repository.ensure_conversation(project_id, conversation_id, title, response_language)
        history = self.repository.list_messages(project_id, conversation)[-self.runtime.max_history_messages:]
        self.repository.save_message(conversation, project_id, "user", clean, language=language.code)
        attachments = self._attachments(project_id, attachment_source_ids)
        evidence: tuple[RetrievalResult, ...] = ()
        citations = ()
        actions = tuple(action.to_dict() for action in suggest_actions(clean, self.settings.root))
        active_provider: object = self.local_provider
        attempted: list[str] = []
        general_knowledge = False

        if plan.clinical_safety:
            answer = clinical_safety_message(language.code)
            evidence_status = "safety_blocked"
        else:
            if plan.retrieval_required:
                evidence = self.retrieve(project_id, language.normalized_query, top_k=top_k, source_types=source_types, rerank=rerank)
                if evidence:
                    citations = build_citations(evidence, self.repository.project_name(project_id))
                    validate_citations(project_id, citations, evidence)
                    evidence_status = "grounded"
                else:
                    # Evidence-seeking questions remain explicitly insufficient when
                    # only the deterministic offline engine is available. A capable
                    # conversational model may still answer them as general knowledge,
                    # but that transition is recorded only after a provider succeeds.
                    evidence_status = "insufficient"
                    general_knowledge = False
            else:
                evidence_status = "general_knowledge"
                general_knowledge = True
            last_error: Exception | None = None
            for candidate in self._provider_chain(provider or self.runtime.mode, cloud_allowed):
                active_provider = candidate
                attempted.append(str(getattr(candidate, "name", "unknown")))
                try:
                    answer = candidate.generate(clean, evidence, citations, language, history=history, attachments=attachments, cancelled=cancelled)
                    if plan.retrieval_required and not evidence and getattr(candidate, "name", "local") != "local":
                        evidence_status = "general_knowledge"
                        general_knowledge = True
                    break
                except ProviderUnavailableError as exc:
                    last_error = exc
                    continue
            else:
                if last_error:
                    raise last_error
                raise ProviderUnavailableError("No Shiro generation provider is available.")

        resolved_request = request_id or "req-" + uuid4().hex
        response = ChatResponse(
            answer,
            project_id,
            conversation,
            citations,
            language,
            plan,
            str(getattr(active_provider, "name", "local")),
            str(getattr(active_provider, "model", "")),
            evidence_status,
            resolved_request,
            actions=actions,
            provider_route=tuple(attempted),
            general_knowledge=general_knowledge,
        )
        self.repository.save_message(
            conversation,
            project_id,
            "assistant",
            answer,
            citations=[citation.to_dict() for citation in citations],
            provider=response.provider,
            model=response.model,
            retrieval={"result_count": len(evidence), "intent": plan.intent, "evidence_status": evidence_status, "general_knowledge": general_knowledge, "provider_route": attempted, "actions": list(actions)},
            source_filters=source_types or plan.allowed_sources,
            language=language.code,
        )
        return response

    def source_preview(self, project_id: str, source_id: str) -> dict[str, object]:
        return self.repository.source_preview(project_id, source_id)
