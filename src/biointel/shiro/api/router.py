from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from biointel.shiro.api.schemas import (
    ChatRequest,
    ConversationCreateRequest,
    ConversationRenameRequest,
    IndexRequest,
    ModuleResultIngestRequest,
    ReportIngestRequest,
    RetrieveRequest,
)
from biointel.shiro.core.cancellation import CANCELLATIONS
from biointel.shiro.core.orchestrator import ShiroOrchestrator
from biointel.shiro.exceptions import ProjectAccessError, ShiroError

ROOT = Path(__file__).resolve().parents[4]
router = APIRouter(prefix="/api/shiro", tags=["Shiro AI"])


@lru_cache(maxsize=1)
def get_shiro() -> ShiroOrchestrator:
    return ShiroOrchestrator(ROOT)


def _request_id(request: Request) -> str:
    cached = getattr(request.state, "shiro_request_id", "")
    if cached:
        return str(cached)
    value = request.headers.get("X-Request-ID", "").strip()
    resolved = value[:120] if value else "req-" + uuid4().hex
    request.state.shiro_request_id = resolved
    return resolved


def _envelope(request: Request, data: object) -> dict[str, object]:
    return {"request_id": _request_id(request), "data": data}


def _raise(exc: Exception, request: Request) -> None:
    code = getattr(exc, "code", "validation_error" if isinstance(exc, ValueError) else "shiro_error")
    if isinstance(exc, ProjectAccessError):
        status = 403
    elif code in {"provider_unavailable", "external_search_failure"}:
        status = 503
    elif code == "user_cancellation":
        status = 409
    else:
        status = 400 if isinstance(exc, (ValueError, ShiroError)) else 500
    raise HTTPException(
        status_code=status,
        detail={"request_id": _request_id(request), "code": code, "message": str(exc)},
    ) from exc


def _safe_source(value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    result.pop("file_path", None)
    return result


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    return _envelope(request, get_shiro().health())


@router.get("/capabilities")
def capabilities(request: Request) -> dict[str, object]:
    return _envelope(request, get_shiro().capabilities())


@router.get("/providers")
def providers(request: Request) -> dict[str, object]:
    return _envelope(request, [item.__dict__ for item in get_shiro().providers()])


@router.post("/chat")
def chat(payload: ChatRequest, request: Request) -> dict[str, object]:
    try:
        result = get_shiro().chat(
            payload.project_id, payload.message, conversation_id=payload.conversation_id,
            response_language=payload.response_language, top_k=payload.top_k,
            provider=payload.provider, external_requested=payload.external_requested,
            cloud_consent=payload.cloud_consent, attachment_source_ids=payload.attachment_source_ids or None,
            rerank=payload.rerank, source_types=payload.source_types or None, request_id=_request_id(request),
        )
        return _envelope(request, result.to_dict())
    except Exception as exc:
        _raise(exc, request)


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    request_id = _request_id(request)

    def events() -> Iterator[str]:
        event = CANCELLATIONS.register(request_id)
        try:
            result = get_shiro().chat(
                payload.project_id, payload.message, conversation_id=payload.conversation_id,
                response_language=payload.response_language, top_k=payload.top_k,
                provider=payload.provider, external_requested=payload.external_requested,
                cloud_consent=payload.cloud_consent, attachment_source_ids=payload.attachment_source_ids or None,
                rerank=payload.rerank, source_types=payload.source_types or None,
                cancelled=event.is_set, request_id=request_id,
            )
            for paragraph in result.answer.split("\n"):
                if paragraph:
                    yield "data: " + json.dumps({"type": "text", "text": paragraph + "\n"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "complete", "response": result.to_dict()}, ensure_ascii=False) + "\n\n"
        except Exception as exc:
            yield "data: " + json.dumps(
                {"type": "error", "request_id": request_id, "code": getattr(exc, "code", "shiro_error"), "message": str(exc)},
                ensure_ascii=False,
            ) + "\n\n"
        finally:
            CANCELLATIONS.release(request_id)

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "X-Request-ID": request_id},
    )


@router.post("/requests/{request_id}/cancel")
def cancel_generation(request_id: str, request: Request) -> dict[str, object]:
    cancelled = CANCELLATIONS.cancel(request_id)
    return _envelope(request, {"request_id": request_id, "cancel_requested": cancelled})


@router.post("/retrieve")
def retrieve(payload: RetrieveRequest, request: Request) -> dict[str, object]:
    try:
        results = get_shiro().retrieve(
            payload.project_id, payload.query, top_k=payload.top_k,
            source_ids=payload.source_ids or None, source_types=payload.source_types or None,
            module_id=payload.module_id, report_id=payload.report_id,
            internal_only=payload.internal_only, external_only=payload.external_only,
            date_from=payload.date_from, date_to=payload.date_to, rerank=payload.rerank,
        )
        return _envelope(request, {"project_id": payload.project_id, "results": [item.to_dict() for item in results]})
    except Exception as exc:
        _raise(exc, request)


@router.post("/ingest")
async def ingest(
    request: Request,
    project_id: str = Form(min_length=1, max_length=160),
    project_name: str = Form(default="", max_length=200),
    synthetic: bool = Form(default=False),
    confidential: bool = Form(default=True),
    background: bool = Form(default=False),
    file: UploadFile = File(...),
) -> dict[str, object]:
    service = get_shiro()
    maximum = service.settings.max_file_size_mb * 1024 * 1024
    content = await file.read(maximum + 1)
    try:
        if background:
            result = service.submit_ingestion(
                project_id, content, file.filename or "evidence.txt",
                project_name=project_name or project_id, synthetic=synthetic, confidential=confidential,
            )
            return _envelope(request, result)
        result = await run_in_threadpool(
            service.ingest, project_id, content, file.filename or "evidence.txt",
            project_name=project_name or project_id, synthetic=synthetic, confidential=confidential,
        )
        data = result.to_dict()
        data["source"] = _safe_source(data["source"])
        return _envelope(request, data)
    except Exception as exc:
        _raise(exc, request)


@router.get("/ingestion/{job_id}")
def ingestion_status(
    job_id: str,
    request: Request,
    project_id: str = Query(min_length=1, max_length=160),
) -> dict[str, object]:
    result = get_shiro().repository.get_job(job_id, project_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"request_id": _request_id(request), "code": "job_not_found", "message": "Job not found in the active project."})
    return _envelope(request, result)


@router.get("/jobs")
def list_jobs(
    request: Request,
    project_id: str = Query(min_length=1, max_length=160),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    return _envelope(request, get_shiro().repository.list_jobs(project_id, limit))


@router.post("/ingestion/{job_id}/cancel")
def cancel_job(
    job_id: str,
    request: Request,
    project_id: str = Query(min_length=1, max_length=160),
) -> dict[str, object]:
    try:
        return _envelope(request, get_shiro().jobs.cancel(project_id, job_id))
    except Exception as exc:
        _raise(exc, request)


@router.post("/index/rebuild")
def rebuild_index(payload: IndexRequest, request: Request) -> dict[str, object]:
    try:
        result = get_shiro().submit_index_rebuild(payload.project_id) if payload.background else get_shiro().ingestion.rebuild_index(payload.project_id)
        return _envelope(request, result)
    except Exception as exc:
        _raise(exc, request)


@router.get("/index/status")
def index_status(request: Request, project_id: str = Query(min_length=1, max_length=160)) -> dict[str, object]:
    return _envelope(request, get_shiro().repository.index_status(project_id))


@router.get("/conversations")
def conversations(request: Request, project_id: str = Query(min_length=1, max_length=160)) -> dict[str, object]:
    return _envelope(request, get_shiro().repository.list_conversations(project_id))


@router.post("/conversations")
def create_conversation(payload: ConversationCreateRequest, request: Request) -> dict[str, object]:
    conversation_id = get_shiro().repository.create_conversation(payload.project_id, payload.title, payload.language)
    return _envelope(request, {"conversation_id": conversation_id, "project_id": payload.project_id})


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: str, request: Request, project_id: str = Query(min_length=1, max_length=160)) -> dict[str, object]:
    try:
        return _envelope(request, {"conversation_id": conversation_id, "messages": get_shiro().repository.list_messages(project_id, conversation_id)})
    except Exception as exc:
        _raise(exc, request)


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, payload: ConversationRenameRequest, request: Request) -> dict[str, object]:
    try:
        get_shiro().repository.rename_conversation(payload.project_id, conversation_id, payload.title)
        return _envelope(request, {"conversation_id": conversation_id, "title": payload.title})
    except Exception as exc:
        _raise(exc, request)


@router.post("/conversations/{conversation_id}/clear")
def clear_conversation(conversation_id: str, request: Request, project_id: str = Query(min_length=1, max_length=160)) -> dict[str, object]:
    try:
        get_shiro().repository.clear_conversation(project_id, conversation_id)
        return _envelope(request, {"cleared": True, "conversation_id": conversation_id})
    except Exception as exc:
        _raise(exc, request)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request, project_id: str = Query(min_length=1, max_length=160)) -> dict[str, object]:
    deleted = get_shiro().repository.delete_conversation(project_id, conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"request_id": _request_id(request), "code": "conversation_not_found", "message": "Conversation not found in the active project."})
    return _envelope(request, {"deleted": True, "conversation_id": conversation_id})


@router.get("/sources")
def list_sources(request: Request, project_id: str = Query(min_length=1, max_length=160)) -> dict[str, object]:
    return _envelope(request, [_safe_source(item.to_dict()) for item in get_shiro().repository.list_sources(project_id)])


@router.get("/sources/{source_id}")
def source_preview(source_id: str, request: Request, project_id: str = Query(min_length=1, max_length=160)) -> dict[str, object]:
    try:
        preview = get_shiro().source_preview(project_id, source_id)
        preview["source"] = _safe_source(preview["source"])
        return _envelope(request, preview)
    except Exception as exc:
        _raise(exc, request)


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, request: Request, project_id: str = Query(min_length=1, max_length=160)) -> dict[str, object]:
    try:
        source = get_shiro().ingestion.delete_source(project_id, source_id)
        return _envelope(request, {"deleted": True, "source_id": source.source_id, "filename": source.filename})
    except Exception as exc:
        _raise(exc, request)


@router.post("/integrations/report")
def ingest_report(payload: ReportIngestRequest, request: Request) -> dict[str, object]:
    try:
        result = get_shiro().ingest_report(
            payload.project_id, payload.report_id, payload.title, payload.body,
            module_id=payload.module_id, analysis_id=payload.analysis_id,
            generated_at=payload.generated_at, synthetic=payload.synthetic,
        ).to_dict()
        result["source"] = _safe_source(result["source"])
        return _envelope(request, result)
    except Exception as exc:
        _raise(exc, request)


@router.post("/integrations/module-result")
def ingest_module_result(payload: ModuleResultIngestRequest, request: Request) -> dict[str, object]:
    try:
        result = get_shiro().ingest_module_result(
            payload.project_id, payload.module_id, payload.analysis_id, payload.summary,
            parameters=payload.parameters, quality_control=payload.quality_control,
            result_rows=payload.result_rows, synthetic=payload.synthetic,
        ).to_dict()
        result["source"] = _safe_source(result["source"])
        return _envelope(request, result)
    except Exception as exc:
        _raise(exc, request)


@router.post("/demo")
def create_demo(request: Request) -> dict[str, object]:
    try:
        return _envelope(request, get_shiro().create_demo())
    except Exception as exc:
        _raise(exc, request)


@router.delete("/demo")
def reset_demo(request: Request) -> dict[str, object]:
    try:
        return _envelope(request, get_shiro().reset_demo())
    except Exception as exc:
        _raise(exc, request)