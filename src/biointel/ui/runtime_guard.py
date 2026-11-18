from __future__ import annotations

import functools
import json
import logging
import os
import re
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import streamlit as st
from streamlit.errors import StreamlitAPIException

from biointel.runtime_paths import runtime_report_path
from biointel.utils.atomic_io import atomic_write_json

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_USER_DATA_ROOT = Path(os.environ.get("BIOINTEL_USER_DATA_DIR", "")).expanduser() if os.environ.get("BIOINTEL_USER_DATA_DIR") else None
LOG_DIR = (_USER_DATA_ROOT / "runtime_logs") if _USER_DATA_ROOT else (runtime_report_path(PROJECT_ROOT, "runtime_logs"))
_MAX_RUNTIME_REPORTS = 200
_MAX_RUNTIME_REPORT_BYTES = 50 * 1024 * 1024
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|bearer)(\s*[:=]\s*)([^\s,;]+)"
)
_RELEASE_STATE_KEY = "_biointel_runtime_release"
_GUARD_INSTALLED_KEY = "_biointel_runtime_guard_installed"
_FRIENDLY_HANDLER_INSTALLED = False
_HANDLER_LOCK = threading.Lock()
_ERROR_WRITE_LOCK = threading.Lock()
_NAVIGATION_NOTICE_LOCK = threading.Lock()
_NAVIGATION_NOTICE_FINGERPRINTS: set[str] = set()
_PYARROW_FALLBACK_INSTALLED = False

_PRESERVE_PREFIXES = (
    "ui_",
    "nav_",
    "auth_",
    "privacy_",
    "favorite",
    "recent_",
    "active_project",
    "selected_project",
)

_TRANSIENT_HINTS = (
    "_result",
    "_results",
    "_data",
    "_frame",
    "_summary",
    "_audit",
    "_output",
    "_analysis",
    "_profile",
    "_failures",
    "_manifest",
    "_preview",
    "_embedding",
    "_clusters",
)


def _release_id() -> str:
    try:
        return (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def _is_transient_key(key: str) -> bool:
    lowered = key.lower()
    if key.startswith(_PRESERVE_PREFIXES):
        return False
    if key.startswith(("FormSubmitter:", "$$WIDGET_ID-")):
        return True
    if key.startswith(("step", "run_", "uploaded_", "imported_")):
        return any(hint in lowered for hint in _TRANSIENT_HINTS) or key.startswith("step")
    return any(hint in lowered for hint in _TRANSIENT_HINTS)


def heal_release_session_state() -> list[str]:
    """Clear stale calculation/widget state once after a release change.

    Appearance, navigation and project choices are deliberately preserved. The
    cleanup runs before page widgets are created, preventing incompatible old
    widget values from crashing a newer release.
    """

    current = _release_id()
    previous = st.session_state.get(_RELEASE_STATE_KEY)
    if previous == current:
        return []

    removed: list[str] = []
    if previous is not None:
        for key in list(st.session_state.keys()):
            if key == _RELEASE_STATE_KEY:
                continue
            if _is_transient_key(str(key)):
                try:
                    del st.session_state[key]
                    removed.append(str(key))
                except KeyError:
                    pass
    st.session_state[_RELEASE_STATE_KEY] = current
    return removed


def _redact_runtime_text(value: object) -> str:
    text = str(value)
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)


def _rotate_runtime_reports() -> None:
    """Bound local crash diagnostics so long-running installations stay smooth."""

    try:
        paths = sorted(LOG_DIR.glob("ERR-*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True)
    except OSError:
        return
    retained_bytes = 0
    for index, path in enumerate(paths):
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if index >= _MAX_RUNTIME_REPORTS or retained_bytes + size > _MAX_RUNTIME_REPORT_BYTES:
            try:
                path.unlink()
            except OSError:
                pass
            continue
        retained_bytes += size


def write_runtime_error(context: str, exc: BaseException) -> tuple[str, dict[str, Any]]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc)
    error_id = timestamp.strftime("ERR-%Y%m%d%H%M%S-%f")
    payload = {
        "error_id": error_id,
        "timestamp_utc": timestamp.isoformat(),
        "context": _redact_runtime_text(context),
        "exception_type": type(exc).__name__,
        "message": _redact_runtime_text(exc),
        "traceback": _redact_runtime_text(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        ),
        "python": sys.version,
        "release": _release_id(),
    }
    try:
        with _ERROR_WRITE_LOCK:
            atomic_write_json(
                LOG_DIR / f"{error_id}.json",
                payload,
                indent=2,
                sort_keys=False,
            )
            _rotate_runtime_reports()
    except OSError:
        logging.getLogger(__name__).exception("Unable to write runtime error report")
    return error_id, payload


def _write_runtime_error(context: str, exc: BaseException) -> str:
    """Backward-compatible error-id helper used by navigation wrappers."""

    return write_runtime_error(context, exc)[0]


def runtime_error_reports(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent runtime reports without failing on a partially written file."""

    if not LOG_DIR.is_dir():
        return []
    reports: list[dict[str, Any]] = []
    for path in sorted(LOG_DIR.glob("ERR-*.json"), reverse=True)[: max(1, min(int(limit), 500))]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            try:
                payload["report_path"] = str(path.relative_to(PROJECT_ROOT))
            except ValueError:
                payload["report_path"] = str(path)
            reports.append(payload)
    return reports


def runtime_diagnostic_bundle(limit: int = 50) -> bytes:
    """Build a portable JSON diagnostic bundle for support and self-service repair."""

    payload = {
        "schema": "biointel.runtime_diagnostics.v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "release": _release_id(),
        "python": sys.version,
        "reports": runtime_error_reports(limit=limit),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode("utf-8")


def _friendly_user_script_exception(exc: BaseException, on_script_error: Callable[[BaseException], Any] | None = None) -> None:
    """Replace Streamlit's red exception panel with a stable recovery surface.

    The script still stops safely, but the user sees an actionable reference ID
    and can export diagnostics. This deliberately avoids exposing a traceback in
    the UI while preserving the full local report.
    """

    error_id, payload = write_runtime_error("streamlit.page_execution", exc)
    if on_script_error is not None:
        try:
            on_script_error(exc)
        except Exception:
            logging.getLogger(__name__).exception("Streamlit script-error callback failed")
    try:
        st.error(f"The workflow stopped safely · {error_id}")
        st.caption(
            "No project data was deleted. Review the selected input and parameters, then retry or export the diagnostic report from System Diagnostics."
        )
        with st.expander("Recovery details", expanded=False):
            st.markdown(
                "- Retry with the bundled example to separate an input issue from an environment issue.\n"
                "- Reset transient analysis results in **System Diagnostics** if the page retained an old upload or widget value.\n"
                "- Run `REPAIR_WINDOWS.bat` when dependencies or the local runtime are damaged; use `DIAGNOSE_WINDOWS.bat` first when the cause is unclear."
            )
            st.code(error_id, language=None)
            st.caption(
                "Use System Diagnostics to export the complete local report. "
                "This recovery boundary intentionally avoids interactive widgets "
                "because the original failure may have occurred inside a form."
            )
    except Exception:
        logging.getLogger(__name__).exception("Unable to render friendly runtime boundary")


def _install_friendly_exception_handler() -> bool:
    global _FRIENDLY_HANDLER_INSTALLED
    if _FRIENDLY_HANDLER_INSTALLED:
        return True
    with _HANDLER_LOCK:
        if _FRIENDLY_HANDLER_INSTALLED:
            return True
        try:
            from streamlit.runtime.scriptrunner import exec_code

            exec_code.handle_user_script_exception = _friendly_user_script_exception
            _FRIENDLY_HANDLER_INSTALLED = True
            return True
        except (ImportError, AttributeError):
            logging.getLogger(__name__).warning(
                "Friendly Streamlit exception interception is unavailable on this runtime."
            )
            return False


def _is_expected_navigation_limitation(name: str, exc: BaseException) -> bool:
    """Detect the benign missing page-link context used by embedded test renderers."""

    return (
        name == "page_link"
        and isinstance(exc, KeyError)
        and len(exc.args) == 1
        and str(exc.args[0]) == "url_pathname"
    )


def _navigation_fingerprint(name: str, exc: BaseException) -> str:
    return f"{name}:{type(exc).__name__}:{exc}"


def _claim_navigation_notice(fingerprint: str) -> bool:
    with _NAVIGATION_NOTICE_LOCK:
        if fingerprint in _NAVIGATION_NOTICE_FINGERPRINTS:
            return False
        _NAVIGATION_NOTICE_FINGERPRINTS.add(fingerprint)
        return True


def _safe_navigation_wrapper(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return original(*args, **kwargs)
        except (KeyError, RuntimeError, StreamlitAPIException) as exc:
            if _is_expected_navigation_limitation(name, exc):
                return None
            fingerprint = _navigation_fingerprint(name, exc)
            if _claim_navigation_notice(fingerprint):
                error_id = _write_runtime_error(f"streamlit.{name}", exc)
                st.info(
                    "One navigation destination is temporarily unavailable. "
                    "Use the sidebar or module search. "
                    f"Diagnostic reference: {error_id}"
                )
            return None

    return wrapped


def _is_missing_pyarrow(exc: BaseException) -> bool:
    return isinstance(exc, ModuleNotFoundError) and getattr(exc, "name", "") == "pyarrow"


def _fallback_table_html(data: Any, *, max_rows: int = 200, max_columns: int = 30) -> str:
    """Return a bounded, escaped HTML table when Streamlit's Arrow renderer is unavailable."""

    try:
        import pandas as pd

        if isinstance(data, pd.Series):
            frame = data.to_frame()
        elif isinstance(data, pd.DataFrame):
            frame = data
        else:
            frame = pd.DataFrame(data)
        source_rows, source_columns = frame.shape
        bounded = frame.iloc[:max_rows, :max_columns]
        table = bounded.to_html(index=False, escape=True, border=0, classes=["biointel-arrow-fallback-table"])
        disclosure = (
            f"<div class='biointel-arrow-fallback-note'>Compatibility table · showing "
            f"{len(bounded):,}/{source_rows:,} rows and {len(bounded.columns):,}/{source_columns:,} columns. "
            "Install the verified pyarrow dependency for interactive sorting and editing.</div>"
        )
        style = """
        <style>
        .biointel-arrow-fallback-note{font-size:.72rem;color:#aebbd3;margin:.35rem 0 .55rem}
        .biointel-arrow-fallback-wrap{overflow:auto;max-height:520px;border:1px solid rgba(130,155,190,.24);border-radius:12px}
        .biointel-arrow-fallback-table{width:100%;border-collapse:collapse;font-size:.73rem;color:#e8eef8}
        .biointel-arrow-fallback-table th,.biointel-arrow-fallback-table td{padding:7px 9px;border-bottom:1px solid rgba(130,155,190,.17);white-space:nowrap;text-align:left}
        .biointel-arrow-fallback-table th{position:sticky;top:0;background:#13243d;color:#f3f7ff;z-index:1}
        </style>
        """
        return style + disclosure + f"<div class='biointel-arrow-fallback-wrap'>{table}</div>"
    except Exception as fallback_exc:
        return (
            "<div class='biointel-arrow-fallback-note'>Table preview unavailable: "
            + str(type(fallback_exc).__name__)
            + "</div>"
        )


def _install_pyarrow_fallback() -> bool:
    """Keep pages usable when pyarrow is missing or damaged.

    The Windows installer still verifies and installs pyarrow. This boundary is a
    last-resort compatibility surface for partial environments, AppTest and repair
    sessions; it never changes the source data.
    """

    global _PYARROW_FALLBACK_INSTALLED
    if _PYARROW_FALLBACK_INSTALLED:
        return True
    try:
        from streamlit.delta_generator import DeltaGenerator

        original_dataframe = DeltaGenerator.dataframe
        original_data_editor = DeltaGenerator.data_editor
        original_st_dataframe = st.dataframe
        original_st_data_editor = st.data_editor
        chart_names = ("bar_chart", "line_chart", "area_chart", "scatter_chart")
        original_delta_charts = {name: getattr(DeltaGenerator, name) for name in chart_names if hasattr(DeltaGenerator, name)}
        original_st_charts = {name: getattr(st, name) for name in chart_names if hasattr(st, name)}

        @functools.wraps(original_dataframe)
        def safe_dataframe(self: Any, data: Any = None, *args: Any, **kwargs: Any) -> Any:
            try:
                return original_dataframe(self, data, *args, **kwargs)
            except ModuleNotFoundError as exc:
                if not _is_missing_pyarrow(exc):
                    raise
                self.markdown(_fallback_table_html(data), unsafe_allow_html=True)
                return None

        @functools.wraps(original_data_editor)
        def safe_data_editor(self: Any, data: Any = None, *args: Any, **kwargs: Any) -> Any:
            try:
                return original_data_editor(self, data, *args, **kwargs)
            except ModuleNotFoundError as exc:
                if not _is_missing_pyarrow(exc):
                    raise
                self.markdown(_fallback_table_html(data), unsafe_allow_html=True)
                try:
                    return data.copy()
                except AttributeError:
                    return data

        @functools.wraps(original_st_dataframe)
        def safe_st_dataframe(data: Any = None, *args: Any, **kwargs: Any) -> Any:
            try:
                return original_st_dataframe(data, *args, **kwargs)
            except ModuleNotFoundError as exc:
                if not _is_missing_pyarrow(exc):
                    raise
                st.markdown(_fallback_table_html(data), unsafe_allow_html=True)
                return None

        @functools.wraps(original_st_data_editor)
        def safe_st_data_editor(data: Any = None, *args: Any, **kwargs: Any) -> Any:
            try:
                return original_st_data_editor(data, *args, **kwargs)
            except ModuleNotFoundError as exc:
                if not _is_missing_pyarrow(exc):
                    raise
                st.markdown(_fallback_table_html(data), unsafe_allow_html=True)
                try:
                    return data.copy()
                except AttributeError:
                    return data

        def _safe_delta_chart(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(original)
            def wrapped(self: Any, data: Any = None, *args: Any, **kwargs: Any) -> Any:
                try:
                    return original(self, data, *args, **kwargs)
                except ModuleNotFoundError as exc:
                    if not _is_missing_pyarrow(exc):
                        raise
                    self.info(
                        f"{name.replace('_', ' ').title()} is shown as a bounded data preview because "
                        "the optional PyArrow renderer is unavailable in this repair session."
                    )
                    self.markdown(_fallback_table_html(data, max_rows=100, max_columns=20), unsafe_allow_html=True)
                    return None
            return wrapped

        def _safe_st_chart(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(original)
            def wrapped(data: Any = None, *args: Any, **kwargs: Any) -> Any:
                try:
                    return original(data, *args, **kwargs)
                except ModuleNotFoundError as exc:
                    if not _is_missing_pyarrow(exc):
                        raise
                    st.info(
                        f"{name.replace('_', ' ').title()} is shown as a bounded data preview because "
                        "the optional PyArrow renderer is unavailable in this repair session."
                    )
                    st.markdown(_fallback_table_html(data, max_rows=100, max_columns=20), unsafe_allow_html=True)
                    return None
            return wrapped

        DeltaGenerator.dataframe = safe_dataframe
        DeltaGenerator.data_editor = safe_data_editor
        st.dataframe = safe_st_dataframe  # type: ignore[assignment]
        st.data_editor = safe_st_data_editor  # type: ignore[assignment]
        for chart_name, original in original_delta_charts.items():
            setattr(DeltaGenerator, chart_name, _safe_delta_chart(chart_name, original))
        for chart_name, original in original_st_charts.items():
            setattr(st, chart_name, _safe_st_chart(chart_name, original))
        _PYARROW_FALLBACK_INSTALLED = True
        return True
    except (AttributeError, ImportError):
        logging.getLogger(__name__).warning("PyArrow compatibility fallback could not be installed.")
        return False


def install_runtime_guard() -> None:
    """Install release healing and navigation crash boundaries once per process."""

    heal_release_session_state()
    _install_friendly_exception_handler()
    _install_pyarrow_fallback()
    if st.session_state.get(_GUARD_INSTALLED_KEY):
        return

    st.page_link = _safe_navigation_wrapper("page_link", st.page_link)  # type: ignore[assignment]
    st.switch_page = _safe_navigation_wrapper("switch_page", st.switch_page)  # type: ignore[assignment]
    st.session_state[_GUARD_INSTALLED_KEY] = True
