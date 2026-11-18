from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatRequest(StrictModel):
    project_id: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=50000)
    conversation_id: str | None = Field(default=None, max_length=100)
    response_language: str = Field(default="auto", pattern="^(auto|English|Hindi|Hinglish|en|hi|hi-Latn)$")
    top_k: int = Field(default=6, ge=1, le=30)
    provider: str = Field(default="auto", pattern="^(auto|local_private|online_enhanced|offline_evidence|local|ollama|gemini|openrouter|openai)$")
    external_requested: bool = False
    cloud_consent: bool = False
    attachment_source_ids: list[str] = Field(default_factory=list, max_length=8)
    rerank: bool = False
    source_types: list[str] = Field(default_factory=list, max_length=50)


class RetrieveRequest(StrictModel):
    project_id: str = Field(min_length=1, max_length=160)
    query: str = Field(min_length=1, max_length=50000)
    top_k: int = Field(default=6, ge=1, le=30)
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    source_types: list[str] = Field(default_factory=list, max_length=50)
    module_id: str | None = Field(default=None, max_length=160)
    report_id: str | None = Field(default=None, max_length=160)
    internal_only: bool = False
    external_only: bool = False
    date_from: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    rerank: bool = False


class IndexRequest(StrictModel):
    project_id: str = Field(min_length=1, max_length=160)
    background: bool = False


class ConversationCreateRequest(StrictModel):
    project_id: str = Field(min_length=1, max_length=160)
    title: str = Field(default="New conversation", max_length=160)
    language: str = Field(default="auto", max_length=20)


class ConversationRenameRequest(StrictModel):
    project_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)


class ReportIngestRequest(StrictModel):
    project_id: str = Field(min_length=1, max_length=160)
    report_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=2000000)
    module_id: str = Field(default="", max_length=160)
    analysis_id: str = Field(default="", max_length=160)
    generated_at: str = Field(default="", max_length=80)
    synthetic: bool = False


class ModuleResultIngestRequest(StrictModel):
    project_id: str = Field(min_length=1, max_length=160)
    module_id: str = Field(min_length=1, max_length=160)
    analysis_id: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=500000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    quality_control: dict[str, Any] = Field(default_factory=dict)
    result_rows: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    synthetic: bool = False