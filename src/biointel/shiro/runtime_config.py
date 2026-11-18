from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


MODE_LABELS = {
    "auto": "Auto · local first",
    "local_private": "Local Private",
    "online_enhanced": "Online Enhanced",
    "offline_evidence": "Offline Evidence Only",
}

PROVIDER_PUBLIC_NAMES = {
    "local": "Shiro Evidence Engine",
    "ollama": "Shiro Local Intelligence",
    "gemini": "Shiro Online Intelligence",
    "openrouter": "Shiro Backup Intelligence",
}


@dataclass
class ShiroRuntimeConfig:
    mode: str = "auto"
    cloud_consent_saved: bool = False
    cloud_eligibility_confirmed: bool = False
    local_model: str = "qwen3:4b"
    local_vision_model: str = "gemma3:4b"
    local_reasoning_model: str = "deepseek-r1:8b"
    local_embedding_model: str = "embeddinggemma"
    gemini_model: str = "gemini-3.1-flash-lite"
    openrouter_model: str = "openrouter/free"
    max_history_messages: int = 20
    max_output_tokens: int = 2048
    temperature: float = 0.2
    allow_cloud_fallback: bool = False
    updated_at: str = ""

    @classmethod
    def load(cls, data_dir: str | Path) -> "ShiroRuntimeConfig":
        path = Path(data_dir) / "provider-settings.json"
        value = cls()
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                allowed = {item.name for item in fields(cls)}
                payload = {key: item for key, item in payload.items() if key in allowed}
                value = cls(**payload)
            except (OSError, ValueError, TypeError):
                value = cls()
        # Environment variables remain the highest-precedence deployment boundary.
        value.mode = os.getenv("SHIRO_MODE", value.mode).strip().casefold() or value.mode
        value.local_model = os.getenv("SHIRO_OLLAMA_MODEL", value.local_model).strip() or value.local_model
        value.local_vision_model = os.getenv("SHIRO_OLLAMA_VISION_MODEL", value.local_vision_model).strip() or value.local_vision_model
        value.local_reasoning_model = os.getenv("SHIRO_OLLAMA_REASONING_MODEL", value.local_reasoning_model).strip() or value.local_reasoning_model
        value.gemini_model = os.getenv("SHIRO_GEMINI_MODEL", value.gemini_model).strip() or value.gemini_model
        value.openrouter_model = os.getenv("SHIRO_OPENROUTER_MODEL", value.openrouter_model).strip() or value.openrouter_model
        if value.mode not in MODE_LABELS:
            value.mode = "auto"
        defaults = cls()
        try:
            value.max_history_messages = max(2, min(int(value.max_history_messages), 100))
        except (TypeError, ValueError):
            value.max_history_messages = defaults.max_history_messages
        try:
            value.max_output_tokens = max(128, min(int(value.max_output_tokens), 8192))
        except (TypeError, ValueError):
            value.max_output_tokens = defaults.max_output_tokens
        try:
            value.temperature = max(0.0, min(float(value.temperature), 1.5))
        except (TypeError, ValueError):
            value.temperature = defaults.temperature
        return value

    def save(self, data_dir: str | Path) -> Path:
        path = Path(data_dir) / "provider-settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = asdict(self)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return path
