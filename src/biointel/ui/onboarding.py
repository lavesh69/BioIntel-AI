from __future__ import annotations

from biointel.runtime_paths import runtime_report_path

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import streamlit as st

from biointel.ui.brand import BRAND, brand_mark_svg
from biointel.ui.preferences import active_profile_name
from biointel.utils.atomic_io import atomic_write_json


@dataclass(frozen=True)
class OnboardingProfile:
    role: str = "Researcher"
    experience: str = "Intermediate"
    interface_mode: str = "Guided"
    primary_goal: str = "Analyse biological data"
    completed_at_utc: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def onboarding_path(project_root: str | Path) -> Path:
    root = Path(project_root).resolve()
    return runtime_report_path(root, "ui_profiles") / active_profile_name() / "onboarding.json"


def load_onboarding(project_root: str | Path) -> OnboardingProfile | None:
    path = onboarding_path(project_root)
    if not path.is_file():
        return None
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return OnboardingProfile(
        role=str(payload.get("role", "Researcher")),
        experience=str(payload.get("experience", "Intermediate")),
        interface_mode=str(payload.get("interface_mode", "Guided")),
        primary_goal=str(payload.get("primary_goal", "Analyse biological data")),
        completed_at_utc=str(payload.get("completed_at_utc", "")),
    )


def save_onboarding(project_root: str | Path, profile: OnboardingProfile) -> Path:
    path = onboarding_path(project_root)
    return atomic_write_json(path, profile.to_dict())


def apply_onboarding_profile(profile: OnboardingProfile) -> None:
    st.session_state["ui_role"] = profile.role
    st.session_state["ui_interface_mode"] = profile.interface_mode
    st.session_state["ui_experience"] = profile.experience
    st.session_state["ui_primary_goal"] = profile.primary_goal
    st.session_state["ui_onboarding_dismissed"] = True


def render_first_launch_onboarding(project_root: str | Path) -> bool:
    """Render a durable first-launch setup without forcing a modal dependency.

    Returns ``True`` when the workspace can continue normally. The panel is safe
    in Streamlit AppTest and older supported Streamlit builds.
    """

    stored = load_onboarding(project_root)
    if stored is not None:
        apply_onboarding_profile(stored)
        return True
    if bool(st.session_state.get("ui_onboarding_dismissed", False)):
        return True

    st.markdown(
        f"""
        <section class="bio-onboarding-brand" aria-label="Welcome to {BRAND.name}">
          <div class="bio-onboarding-mark">{brand_mark_svg(size=68)}</div>
          <div>
            <div class="bio-onboarding-kicker">{BRAND.descriptor}</div>
            <h1>Welcome to {BRAND.name}</h1>
            <p class="bio-onboarding-tagline">{BRAND.tagline}</p>
            <p>Turn complex biological data into traceable scientific insight. Choose your role, experience and primary workflow to shape the workspace.</p>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        left, right = st.columns(2)
        role = left.selectbox(
            "Workspace role",
            [
                "Researcher",
                "Bioinformatician",
                "Drug-discovery scientist",
                "Lab analyst",
                "ML engineer",
                "Quality reviewer",
                "Administrator",
            ],
            key="onboarding_role",
        )
        experience = right.selectbox(
            "Experience level",
            ["Beginner", "Intermediate", "Advanced"],
            index=1,
            key="onboarding_experience",
        )
        mode = left.radio(
            "Interface mode",
            ["Guided", "Advanced"],
            horizontal=True,
            key="onboarding_mode",
        )
        goal = right.selectbox(
            "Primary goal",
            [
                "Analyse biological data",
                "Discover compounds",
                "Run lab analytics",
                "Train and validate models",
                "Review evidence and release readiness",
            ],
            key="onboarding_goal",
        )
        save, skip = st.columns(2)
        if save.button(
            "Save and enter workspace", type="primary", width="stretch", key="onboarding_save"
        ):
            profile = OnboardingProfile(
                role=role,
                experience=experience,
                interface_mode=mode,
                primary_goal=goal,
                completed_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
            )
            try:
                save_onboarding(project_root, profile)
            except OSError as exc:
                st.error(f"Could not save local onboarding preferences: {exc}")
                return False
            apply_onboarding_profile(profile)
            try:
                from biointel.ui.theme import persist_ui_preferences

                persist_ui_preferences()
            except OSError:
                pass
            st.rerun()
        if skip.button("Use research defaults", width="stretch", key="onboarding_skip"):
            profile = OnboardingProfile(
                completed_at_utc=datetime.now(UTC).isoformat(timespec="seconds")
            )
            try:
                save_onboarding(project_root, profile)
            except OSError as exc:
                st.error(f"Could not save local onboarding preferences: {exc}")
                return False
            apply_onboarding_profile(profile)
            try:
                from biointel.ui.theme import persist_ui_preferences

                persist_ui_preferences()
            except OSError:
                pass
            st.rerun()
    return False
