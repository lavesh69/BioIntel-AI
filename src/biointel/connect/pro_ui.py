from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar

import streamlit as st

from .services import ConnectServices
from .ui import context, post_card
from biointel.ui.product_experience_v8 import module_tiles, render_product_hero

T = TypeVar("T")
ADMIN_ROLES = {"administrator", "moderator", "local_operator"}
FEED_MODES = {
    "Latest": "latest",
    "Following": "following",
    "Connections": "connections",
    "Recommended": "recommended",
}


@dataclass
class HubSnapshot:
    profile: dict[str, Any] = field(default_factory=dict)
    network: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {"connections": [], "following": [], "requests": []}
    )
    notifications: list[dict[str, Any]] = field(default_factory=list)
    conversations: list[dict[str, Any]] = field(default_factory=list)
    joined_communities: int | None = None
    open_calls: int | None = None
    call_capabilities: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _load(snapshot: HubSnapshot, label: str, operation: Callable[[], T], fallback: T) -> T:
    try:
        return operation()
    except Exception as exc:  # Keep other hub sections usable when one service is unavailable.
        snapshot.errors.append(f"{label} ({type(exc).__name__})")
        return fallback


def _joined_community_count(services: ConnectServices, user_id: str) -> int:
    with services.database.connection(read_only=True) as db:
        row = db.execute(
            """
            SELECT COUNT(DISTINCT community_id)
            FROM connect_community_members
            WHERE user_id=? AND state='active' AND deleted_at_utc IS NULL
            """,
            (user_id,),
        ).fetchone()
    return int(row[0])


def _open_call_count(services: ConnectServices, user_id: str) -> int:
    with services.database.connection(read_only=True) as db:
        row = db.execute(
            """
            SELECT COUNT(DISTINCT session.call_id)
            FROM connect_call_sessions AS session
            JOIN connect_call_participants AS participant
              ON participant.call_id=session.call_id
            WHERE participant.user_id=?
              AND participant.state='active'
              AND session.state IN ('ringing','scheduled','ready','active')
              AND session.deleted_at_utc IS NULL
            """,
            (user_id,),
        ).fetchone()
    return int(row[0])


def load_hub_snapshot(services: ConnectServices, user: dict[str, Any]) -> HubSnapshot:
    snapshot = HubSnapshot()
    user_id = str(user["user_id"])
    snapshot.profile = _load(
        snapshot, "profile", lambda: services.profiles.get(user_id, user_id), {}
    )
    snapshot.network = _load(
        snapshot,
        "network",
        lambda: services.network.overview(user_id),
        {"connections": [], "following": [], "requests": []},
    )
    snapshot.notifications = _load(
        snapshot,
        "notifications",
        lambda: services.content.notifications(user_id, 100),
        [],
    )
    if services.complete is not None:
        snapshot.conversations = _load(
            snapshot,
            "messages",
            lambda: services.complete.messaging.list(user_id, 100),
            [],
        )
        snapshot.call_capabilities = _load(
            snapshot, "call capabilities", services.complete.calls.capabilities, {}
        )
    else:
        snapshot.errors.append("extended Connect services (Unavailable)")
    snapshot.joined_communities = _load(
        snapshot,
        "community memberships",
        lambda: _joined_community_count(services, user_id),
        None,
    )
    snapshot.open_calls = _load(
        snapshot,
        "call invitations",
        lambda: _open_call_count(services, user_id),
        None,
    )
    return snapshot


def _value(value: int | None) -> str:
    return "Unavailable" if value is None else f"{value:,}"


def _profile_completion(profile: dict[str, Any]) -> tuple[int, list[str]]:
    research = profile.get("research") if isinstance(profile.get("research"), dict) else {}
    checks = {
        "Professional headline": bool(str(profile.get("headline", "")).strip()),
        "Institution": bool(str(profile.get("institution", "")).strip()),
        "About": bool(str(profile.get("about", "")).strip()),
        "Research fields": bool(research.get("fields")),
        "Scientific skills": bool(research.get("skills")),
    }
    complete = sum(checks.values())
    missing = [label for label, present in checks.items() if not present]
    return round((complete / len(checks)) * 100), missing


def _timestamp_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "Time unavailable"
    return text.replace("T", " ").replace("+00:00", " UTC").replace("Z", " UTC")


def _render_identity(user: dict[str, Any], profile: dict[str, Any]) -> None:
    full_name = str(profile.get("full_name") or user.get("display_name") or user.get("username"))
    username = str(profile.get("username") or user.get("username") or "")
    role = str(user.get("role") or "researcher").replace("_", " ").title()
    state = str(user.get("state") or "unknown").replace("_", " ").title()
    render_product_hero(
        "connect",
        "BioIntel Connect",
        "A professional scientific network for trusted research updates, communities, collaboration and live communication.",
        chips=(f"Signed in as {full_name}", role, state, "Persistent local workspace"),
    )
    module_tiles((
        ("DISCOVER", "Research network", "Find collaborators, experts, communities and scientific opportunities."),
        ("COMMUNICATE", "Messages & calls", "Durable conversations, qualified meetings and permission-aware live rooms."),
        ("PUBLISH", "Scientific feed", "Share evidence-led updates, questions, datasets and collaboration requests."),
        ("TRUST", "Identity & governance", "Verified profiles, moderation, audit history and institutional controls."),
    ))
    st.markdown(f"### Welcome back, {full_name}")
    st.caption((f"@{username} · " if username else "") + "Authenticated Connect member")


def _action_card(page: str, *, title: str, description: str, label: str, icon: str) -> None:
    with st.container(border=True, height="stretch"):
        st.markdown(f"#### {icon} {title}")
        st.caption(description)
        st.page_link(page, label=label, icon=icon, width="stretch")


def _render_primary_actions() -> None:
    st.subheader("Start here", anchor=False)
    columns = st.columns(4, gap="small")
    actions = [
        (
            "pages/302_Connect_Create_Post.py",
            "Share research",
            "Publish an update, question, dataset or collaboration request.",
            "Create a post",
            ":material/add_circle:",
        ),
        (
            "pages/318_Connect_Messages.py",
            "Message",
            "Continue durable direct or group scientific conversations.",
            "Open messages",
            ":material/chat:",
        ),
        (
            "pages/319_Connect_Communities.py",
            "Communities",
            "Join moderated spaces organized around research interests.",
            "Browse communities",
            ":material/groups:",
        ),
        (
            "pages/322_Connect_Live_and_Calls.py",
            "Meet",
            "Manage live rooms and qualified small-room calls.",
            "Open live and calls",
            ":material/video_call:",
        ),
    ]
    for column, (page, title, description, label, icon) in zip(columns, actions):
        with column:
            _action_card(page, title=title, description=description, label=label, icon=icon)


def _render_metrics(snapshot: HubSnapshot) -> None:
    unread = sum(not item.get("read_at_utc") for item in snapshot.notifications)
    values: list[tuple[str, int | None, str]] = [
        ("Connections", len(snapshot.network["connections"]), "Accepted professional connections"),
        ("Unread activity", unread, "Persisted unread Connect notifications"),
        ("Conversations", len(snapshot.conversations), "Active conversations visible to you"),
        ("Joined communities", snapshot.joined_communities, "Active community memberships"),
    ]
    with st.container(horizontal=True, gap="small"):
        for label, value, help_text in values:
            st.metric(label, _value(value), help=help_text, border=True)


def _render_explore(user: dict[str, Any]) -> None:
    st.subheader("Explore Connect", anchor=False)
    columns = st.columns(4, gap="small", border=True)
    links = [
        [
            ("pages/303_Connect_My_Network.py", "My network", ":material/group:"),
            ("pages/315_Connect_Profile.py", "Professional profile", ":material/person:"),
        ],
        [
            ("pages/320_Connect_Discover_and_Collaborate.py", "Discover and collaborate", ":material/travel_explore:"),
            ("pages/321_Connect_Stories_and_Short_Videos.py", "Stories and videos", ":material/auto_stories:"),
        ],
        [
            ("pages/313_Connect_Notifications.py", "Notifications", ":material/notifications:"),
            ("pages/316_Connect_Settings.py", "Privacy and settings", ":material/privacy_tip:"),
        ],
    ]
    for column, group in zip(columns[:3], links):
        with column:
            for page, label, icon in group:
                st.page_link(page, label=label, icon=icon, width="stretch")
    with columns[3]:
        is_admin = str(user.get("role", "")).lower() in ADMIN_ROLES
        st.page_link(
            "pages/324_Connect_Admin_and_Operations.py",
            label="Admin and operations",
            icon=":material/admin_panel_settings:",
            disabled=not is_admin,
            help=None if is_admin else "Administrator, moderator or local-operator role required.",
            width="stretch",
        )
        st.page_link(
            "pages/325_Connect_Accessibility_and_Notifications.py",
            label="Accessibility",
            icon=":material/accessibility_new:",
            width="stretch",
        )


def _render_profile_card(profile: dict[str, Any]) -> None:
    completion, missing = _profile_completion(profile)
    with st.container(border=True):
        st.subheader("Your scientific profile", anchor=False)
        st.write(str(profile.get("headline") or "Add a professional headline"))
        st.caption(str(profile.get("institution") or "Institution not added"))
        st.progress(completion / 100, text=f"{completion}% profile readiness")
        if missing:
            st.caption("Next: " + ", ".join(missing[:2]))
        else:
            st.badge("Core profile complete", icon=":material/check:", color="green")
        st.page_link(
            "pages/315_Connect_Profile.py",
            label="Review profile",
            icon=":material/edit:",
            width="stretch",
        )


def _render_recent_activity(notifications: list[dict[str, Any]]) -> None:
    with st.container(border=True):
        st.subheader("Recent activity", anchor=False)
        if not notifications:
            st.caption("No Connect notifications yet.")
            st.page_link(
                "pages/320_Connect_Discover_and_Collaborate.py",
                label="Discover researchers and work",
                icon=":material/travel_explore:",
                width="stretch",
            )
            return
        for item in notifications[:4]:
            with st.container(gap=None):
                if not item.get("read_at_utc"):
                    st.badge("New", color="blue")
                st.write(str(item.get("message") or "Connect activity"))
                st.caption(_timestamp_label(item.get("created_at_utc")))
        st.page_link(
            "pages/313_Connect_Notifications.py",
            label="View all notifications",
            icon=":material/notifications:",
            width="stretch",
        )


def _render_call_status(snapshot: HubSnapshot) -> None:
    capabilities = snapshot.call_capabilities
    turn = capabilities.get("turn") if isinstance(capabilities.get("turn"), dict) else {}
    recording = capabilities.get("recording") if isinstance(capabilities.get("recording"), dict) else {}
    transcription = capabilities.get("transcription") if isinstance(capabilities.get("transcription"), dict) else {}
    topology = str(capabilities.get("topology") or "Unavailable")
    mesh_limit = capabilities.get("max_peer_participants")
    with st.container(border=True):
        st.subheader("Calls readiness", anchor=False)
        if capabilities:
            st.badge("Small-room calling available", icon=":material/verified:", color="green")
            st.caption(
                f"{topology.replace('-', ' ').title()} · "
                f"maximum {mesh_limit if mesh_limit is not None else 'configured'} peers"
            )
            st.metric("Open invitations and rooms", _value(snapshot.open_calls), border=True)
            missing = []
            if not turn.get("configured"):
                missing.append("TURN")
            if not recording.get("configured"):
                missing.append("recording")
            if not transcription.get("configured"):
                missing.append("transcription")
            if missing:
                st.caption("Not configured: " + ", ".join(missing) + ". Availability is not simulated.")
        else:
            st.warning("Call capability status could not be loaded.", icon=":material/warning:")
        st.page_link(
            "pages/322_Connect_Live_and_Calls.py",
            label="Review calls and device setup",
            icon=":material/video_call:",
            width="stretch",
        )


def _render_feed(services: ConnectServices, user: dict[str, Any], snapshot: HubSnapshot) -> None:
    st.subheader("Scientific feed", anchor=False)
    selected = st.segmented_control(
        "Feed view",
        list(FEED_MODES),
        default="Latest",
        key="connect_hub_feed_mode",
        width="stretch",
    )
    mode = FEED_MODES.get(selected or "Latest", "latest")
    feed = _load(
        snapshot,
        f"{mode} feed",
        lambda: services.content.feed(str(user["user_id"]), mode=mode, limit=20),
        None,
    )
    if feed is None:
        st.error(
            "The feed could not be refreshed. Your other Connect tools remain available.",
            icon=":material/error:",
        )
        return
    items = list(feed.get("items") or [])
    st.caption(f"{len(items)} permission-checked update{'s' if len(items) != 1 else ''} loaded")
    if not items:
        with st.container(border=True):
            st.markdown("#### :material/science: Build your scientific feed")
            st.write("No visible updates have been published yet." if mode == "latest" else f"No updates match the {selected.lower()} view yet.")
            with st.container(horizontal=True, gap="small"):
                st.page_link(
                    "pages/302_Connect_Create_Post.py",
                    label="Create the first update",
                    icon=":material/add_circle:",
                    width="stretch",
                )
                st.page_link(
                    "pages/303_Connect_My_Network.py",
                    label="Find researchers",
                    icon=":material/person_search:",
                    width="stretch",
                )
        return
    for index, post in enumerate(items):
        post_card(services, user, post, f"hub_{mode}_{index}_{post['post_id']}")


def render_connect_hub(root: Path) -> None:
    try:
        services, user = context(root)
    except Exception as exc:
        st.title("BioIntel Connect")
        st.error(
            "Connect could not initialize its local workspace. No network or activity data has been fabricated.",
            icon=":material/database_off:",
        )
        st.caption(f"Initialization status: {type(exc).__name__}")
        if st.button("Retry", icon=":material/refresh:", type="primary"):
            st.rerun()
        return
    snapshot = load_hub_snapshot(services, user)
    _render_identity(user, snapshot.profile)
    _render_primary_actions()
    _render_metrics(snapshot)
    _render_explore(user)
    feed_column, context_column = st.columns([1.75, 1], gap="large")
    with feed_column:
        _render_feed(services, user, snapshot)
    with context_column:
        _render_profile_card(snapshot.profile)
        _render_recent_activity(snapshot.notifications)
        _render_call_status(snapshot)
    if snapshot.errors:
        with st.expander("Some Connect data could not be refreshed", icon=":material/warning:"):
            st.caption("The available sections above remain live. Retry after checking the local service.")
            for issue in dict.fromkeys(snapshot.errors):
                st.write(f"• {issue}")


