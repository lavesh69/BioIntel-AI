from __future__ import annotations

from biointel.runtime_paths import runtime_report_path

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st

from biointel.security.passwords import verify_password
from biointel.security.ui_user_store import configured_ui_users, verify_totp
from biointel.ui.brand import BRAND, brand_mark_svg

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SESSION_TTL_SECONDS = 12 * 60 * 60
MAX_FAILED_ATTEMPTS = 8
LOCKOUT_SECONDS = 15 * 60


@dataclass(frozen=True)
class UiIdentity:
    username: str
    display_name: str
    role: str
    source: str


def ui_auth_required() -> bool:
    explicit = os.environ.get("BIOINTEL_UI_AUTH_REQUIRED", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False
    return os.environ.get("BIOINTEL_ENVIRONMENT", "local").strip().lower() == "production"


def _configured_users() -> dict[str, dict[str, str]]:
    return configured_ui_users()


def _event_path() -> Path:
    path = runtime_report_path(PROJECT_ROOT, "security") / "ui_access_events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _audit(event_type: str, *, username: str = "", detail: dict[str, Any] | None = None) -> None:
    payload = {
        "event_type": event_type,
        "username_hash": hashlib.sha256(username.lower().encode("utf-8")).hexdigest()
        if username
        else "",
        "occurred_at_epoch": int(time.time()),
        "detail": detail or {},
    }
    try:
        with _event_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        # Authentication must continue even if the audit destination is read-only.
        pass


def _session_identity() -> UiIdentity | None:
    payload = st.session_state.get("biointel_ui_identity")
    authenticated_at = float(st.session_state.get("biointel_ui_authenticated_at", 0.0) or 0.0)
    if not isinstance(payload, dict) or time.time() - authenticated_at > SESSION_TTL_SECONDS:
        st.session_state.pop("biointel_ui_identity", None)
        st.session_state.pop("biointel_ui_authenticated_at", None)
        return None
    return UiIdentity(
        username=str(payload.get("username", "")),
        display_name=str(payload.get("display_name", "")),
        role=str(payload.get("role", "researcher")),
        source=str(payload.get("source", "password")),
    )


def current_ui_identity() -> UiIdentity:
    identity = _session_identity()
    if identity is not None:
        return identity
    return UiIdentity("local", "Local operator", "admin", "local_trusted")


def _render_login(users_configured: bool) -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display:none !important;}
        .stApp {background: radial-gradient(circle at 15% 10%, #12375a 0, #08111f 38%, #050812 100%);}
        .biointel-login {max-width:560px;margin:7vh auto 1.5rem;padding:2rem;border-radius:24px;
          background:rgba(10,20,36,.92);border:1px solid rgba(100,180,255,.22);box-shadow:0 24px 80px rgba(0,0,0,.35)}
        .biointel-login-mark{width:64px;height:64px;margin-bottom:.8rem}.biointel-login h1{margin:.15rem 0;color:#f8fafc;font-size:2rem}.biointel-login p{color:#a8b7cc}.biointel-login-kicker{font-size:.68rem;letter-spacing:.12em;color:#9db6c8;font-weight:750}.biointel-login-tagline{color:#65e8ff;font-weight:750;margin:.25rem 0 .7rem}.biointel-login small{color:#9db6c8}
        </style>
        <div class="biointel-login">
          <div class="biointel-login-mark">__MARK__</div>
          <div class="biointel-login-kicker">__DESCRIPTOR__</div>
          <h1>__NAME__</h1>
          <div class="biointel-login-tagline">__TAGLINE__</div>
          <p>Sign in to the protected scientific workspace. Credentials stay on the server and are never sent to external providers.</p>
          <small>Designed &amp; Developed by __FOUNDER__</small>
        </div>
        """.replace("__MARK__", brand_mark_svg(size=64))
        .replace("__DESCRIPTOR__", BRAND.descriptor.upper())
        .replace("__NAME__", BRAND.name)
        .replace("__TAGLINE__", BRAND.tagline)
        .replace("__FOUNDER__", BRAND.founder),
        unsafe_allow_html=True,
    )
    if not users_configured:
        st.error(
            "Production access control is enabled, but no UI users are configured. "
            "Create a local collaboration user in BioIntel Live Workspace Admin, or set BIOINTEL_UI_USERS_JSON."
        )
        st.stop()

    with st.form("biointel_ui_login", clear_on_submit=False):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        one_time_code = st.text_input("Authenticator code (only when enabled)", max_chars=8, autocomplete="one-time-code")
        submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
    st.caption("Research-use platform · results are not medical diagnosis or treatment advice.")

    if not submitted:
        st.stop()

    now = time.time()
    blocked_until = float(st.session_state.get("biointel_ui_blocked_until", 0.0) or 0.0)
    if blocked_until > now:
        st.error("Too many failed attempts. Try again after the temporary lockout expires.")
        st.stop()

    users = _configured_users()
    candidate = users.get(username.strip().lower())
    valid = bool(candidate) and verify_password(password, str(candidate["password_hash"]))
    # Constant-time fallback prevents a visible username-enumeration timing gap.
    if candidate is None:
        hmac.compare_digest(hashlib.sha256(password.encode()).digest(), b"\0" * 32)
    if valid and candidate and bool(candidate.get("totp_enabled", False)):
        valid = verify_totp(str(candidate.get("totp_secret", "")), one_time_code)
        if not valid:
            _audit("mfa_failed", username=username)
    if not valid:
        failures = int(st.session_state.get("biointel_ui_failures", 0)) + 1
        st.session_state["biointel_ui_failures"] = failures
        if failures >= MAX_FAILED_ATTEMPTS:
            st.session_state["biointel_ui_blocked_until"] = now + LOCKOUT_SECONDS
        _audit("login_failed", username=username)
        st.error("Invalid username or password.")
        st.stop()

    identity = {
        "username": username.strip().lower(),
        "display_name": candidate["display_name"],
        "role": candidate["role"],
        "source": "password",
    }
    st.session_state["biointel_ui_identity"] = identity
    st.session_state["biointel_ui_authenticated_at"] = now
    st.session_state["biointel_ui_failures"] = 0
    _audit("login_succeeded", username=username, detail={"role": candidate["role"]})
    st.rerun()


def require_ui_access() -> UiIdentity:
    if not ui_auth_required():
        return UiIdentity("local", "Local operator", "admin", "local_trusted")
    identity = _session_identity()
    users = _configured_users()
    if identity is None:
        _render_login(bool(users))
        st.stop()
    with st.sidebar:
        st.caption(f"Signed in as **{identity.display_name}** · {identity.role}")
        if st.button("Sign out", key="biointel_ui_sign_out", width="stretch"):
            _audit("logout", username=identity.username)
            st.session_state.pop("biointel_ui_identity", None)
            st.session_state.pop("biointel_ui_authenticated_at", None)
            st.rerun()
    return identity
