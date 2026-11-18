from __future__ import annotations

from typing import Any


class _State(dict):
    def __getattr__(self, key: str) -> Any:
        return self.get(key)

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def __getattr__(self, _key: str):
        return lambda *args, **kwargs: None


class _StreamlitShim:
    """Import-safe no-op surface used only when Streamlit is not installed.

    The packaged Windows runtime includes Streamlit. This shim keeps backend,
    migration and release tests importable in minimal Python environments.
    """

    def __init__(self) -> None:
        self.session_state = _State()

    def form(self, *args: Any, **kwargs: Any) -> _Context:
        return _Context()

    def container(self, *args: Any, **kwargs: Any) -> _Context:
        return _Context()

    def expander(self, *args: Any, **kwargs: Any) -> _Context:
        return _Context()

    def tabs(self, names: Any) -> list[_Context]:
        return [_Context() for _ in names]

    def columns(self, spec: Any, *args: Any, **kwargs: Any) -> list[_Context]:
        length = spec if isinstance(spec, int) else len(spec)
        return [_Context() for _ in range(length)]

    def selectbox(self, _label: str, options: Any, *args: Any, **kwargs: Any) -> Any:
        values = list(options)
        if not values:
            return None
        index = int(kwargs.get("index", 0) or 0)
        return values[min(max(index, 0), len(values) - 1)]

    def multiselect(self, _label: str, _options: Any, *args: Any, **kwargs: Any) -> list[Any]:
        return list(kwargs.get("default", []) or [])

    def radio(self, _label: str, options: Any, *args: Any, **kwargs: Any) -> Any:
        values = list(options)
        return values[0] if values else None

    def segmented_control(self, _label: str, options: Any, *args: Any, **kwargs: Any) -> Any:
        values = list(options)
        return kwargs.get("default") or (values[0] if values else None)

    def pills(self, _label: str, options: Any, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("selection_mode") == "multi":
            return list(kwargs.get("default", []) or [])
        values = list(options)
        return kwargs.get("default") or (values[0] if values else None)

    def text_input(self, *args: Any, **kwargs: Any) -> str:
        return str(kwargs.get("value", ""))

    def text_area(self, *args: Any, **kwargs: Any) -> str:
        return str(kwargs.get("value", ""))

    def number_input(self, *args: Any, **kwargs: Any) -> Any:
        return kwargs.get("value", 0)

    def slider(self, *args: Any, **kwargs: Any) -> Any:
        if "value" in kwargs:
            return kwargs["value"]
        return args[3] if len(args) > 3 else 0

    def date_input(self, *args: Any, **kwargs: Any) -> Any:
        return kwargs.get("value")

    def time_input(self, *args: Any, **kwargs: Any) -> Any:
        return kwargs.get("value")

    def toggle(self, *args: Any, **kwargs: Any) -> bool:
        return bool(kwargs.get("value", False))

    def checkbox(self, *args: Any, **kwargs: Any) -> bool:
        return bool(kwargs.get("value", False))

    def button(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def form_submit_button(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def file_uploader(self, *args: Any, **kwargs: Any) -> None:
        return None

    def __getattr__(self, _key: str):
        return lambda *args, **kwargs: None


try:
    import streamlit as st  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal release gates
    st = _StreamlitShim()

__all__ = ["st"]
