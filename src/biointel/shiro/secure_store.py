from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Mapping


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _dpapi_encrypt(data: bytes) -> bytes:
    source, keepalive = _blob(data)
    result = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "BioIntel Shiro AI", None, None, None, 0, ctypes.byref(result)
    ):
        raise OSError("Windows credential protection failed.")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)
        del keepalive


def _dpapi_decrypt(data: bytes) -> bytes:
    source, keepalive = _blob(data)
    result = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)
    ):
        raise OSError("Windows credential recovery failed.")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)
        del keepalive


class ShiroSecretStore:
    """Machine-local secret storage. Windows uses DPAPI; other platforms use Fernet."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "provider-secrets.bin"
        self.key_path = self.data_dir / ".provider-secrets.key"

    def _encrypt(self, data: bytes) -> bytes:
        if os.name == "nt":
            return b"DPAPI1\n" + base64.b64encode(_dpapi_encrypt(data))
        from cryptography.fernet import Fernet

        key = self.key_path.read_bytes() if self.key_path.is_file() else Fernet.generate_key()
        if not self.key_path.is_file():
            self.key_path.write_bytes(key)
            try:
                self.key_path.chmod(0o600)
            except OSError:
                pass
        return b"FERNET1\n" + Fernet(key).encrypt(data)

    def _decrypt(self, data: bytes) -> bytes:
        if data.startswith(b"DPAPI1\n") and os.name == "nt":
            return _dpapi_decrypt(base64.b64decode(data.split(b"\n", 1)[1]))
        if data.startswith(b"FERNET1\n"):
            from cryptography.fernet import Fernet

            if not self.key_path.is_file():
                return b"{}"
            return Fernet(self.key_path.read_bytes()).decrypt(data.split(b"\n", 1)[1])
        return b"{}"

    def load(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self._decrypt(self.path.read_bytes()).decode("utf-8"))
            return {str(key): str(value) for key, value in payload.items() if str(value).strip()}
        except Exception:
            return {}

    def save(self, values: Mapping[str, str]) -> None:
        clean = {str(key): str(value).strip() for key, value in values.items() if str(value).strip()}
        self.path.write_bytes(self._encrypt(json.dumps(clean).encode("utf-8")))
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def get(self, name: str, env_name: str = "") -> str:
        if env_name and os.getenv(env_name, "").strip():
            return os.environ[env_name].strip()
        return self.load().get(name, "")

    def update(self, **values: str) -> None:
        current = self.load()
        for key, value in values.items():
            if value.strip():
                current[key] = value.strip()
            else:
                current.pop(key, None)
        self.save(current)
