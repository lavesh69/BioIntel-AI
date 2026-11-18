from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))


@dataclass(frozen=True)
class ShiroSettings:
    root: Path
    data_dir: Path
    enabled: bool = True
    default_mode: str = "local"
    provider: str = "local"
    chat_model: str = "grounded-extractive-v1"
    embedding_provider: str = "local"
    embedding_model: str = "hash-multilingual-v1"
    embedding_dimension: int = 384
    allow_model_downloads: bool = False
    reranker_enabled: bool = False
    external_search_enabled: bool = False
    max_file_size_mb: int = 25
    ocr_enabled: bool = False
    ocr_language: str = "eng"
    ocr_max_pages: int = 25
    retrieval_top_k: int = 6
    context_limit: int = 12000
    project_isolation: bool = True
    chunk_size: int = 1600
    chunk_overlap: int = 160
    ollama_enabled: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    generation_timeout_seconds: int = 60

    @property
    def database_path(self) -> Path:
        return self.data_dir / "shiro.sqlite3"

    @classmethod
    def from_environment(
        cls,
        root: str | Path | None = None,
        data_dir: str | Path | None = None,
    ) -> "ShiroSettings":
        resolved_root = Path(root).resolve() if root else Path(__file__).resolve().parents[3]
        configured = str(data_dir or os.getenv("SHIRO_DATA_DIR", "")).strip()
        if configured:
            resolved_data = Path(configured).expanduser().resolve()
        elif os.getenv("BIOINTEL_USER_DATA_DIR", "").strip():
            resolved_data = (
                Path(os.environ["BIOINTEL_USER_DATA_DIR"]).expanduser().resolve() / "shiro"
            )
        else:
            resolved_data = resolved_root / "UserData" / "shiro"
        provider = os.getenv("SHIRO_PROVIDER", "local").strip().casefold() or "local"
        return cls(
            root=resolved_root,
            data_dir=resolved_data,
            enabled=_bool("SHIRO_ENABLED", True),
            default_mode=os.getenv("SHIRO_DEFAULT_MODE", "local").strip() or "local",
            provider=provider,
            chat_model=os.getenv("SHIRO_CHAT_MODEL", "grounded-extractive-v1").strip()
            or "grounded-extractive-v1",
            embedding_provider=os.getenv("SHIRO_EMBEDDING_PROVIDER", "local").strip()
            or "local",
            embedding_model=os.getenv("SHIRO_EMBEDDING_MODEL", "hash-multilingual-v1").strip()
            or "hash-multilingual-v1",
            embedding_dimension=_integer("SHIRO_EMBEDDING_DIMENSION", 384, 64, 4096),
            allow_model_downloads=_bool("SHIRO_ALLOW_MODEL_DOWNLOADS", False),
            reranker_enabled=_bool("SHIRO_RERANKER_ENABLED", False),
            external_search_enabled=_bool("SHIRO_EXTERNAL_SEARCH_ENABLED", False),
            max_file_size_mb=_integer("SHIRO_MAX_FILE_SIZE_MB", 25, 1, 200),
            ocr_enabled=_bool("SHIRO_OCR_ENABLED", False),
            ocr_language=os.getenv("SHIRO_OCR_LANGUAGE", "eng").strip() or "eng",
            ocr_max_pages=_integer("SHIRO_OCR_MAX_PAGES", 25, 1, 100),
            retrieval_top_k=_integer("SHIRO_RETRIEVAL_TOP_K", 6, 1, 30),
            context_limit=_integer("SHIRO_CONTEXT_LIMIT", 12000, 2000, 100000),
            project_isolation=_bool("SHIRO_PROJECT_ISOLATION", True),
            chunk_size=_integer("SHIRO_CHUNK_SIZE", 1600, 400, 6000),
            chunk_overlap=_integer("SHIRO_CHUNK_OVERLAP", 160, 0, 600),
            ollama_enabled=_bool("SHIRO_OLLAMA_ENABLED", True),
            ollama_base_url=os.getenv("SHIRO_OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434",
            ollama_model=os.getenv("SHIRO_OLLAMA_MODEL", os.getenv("BIOINTEL_OLLAMA_MODEL", "qwen3:4b")).strip() or "qwen3:4b",
            generation_timeout_seconds=_integer("SHIRO_GENERATION_TIMEOUT_SECONDS", 60, 5, 300),
        )
