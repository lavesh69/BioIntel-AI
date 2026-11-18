from __future__ import annotations

from pathlib import Path

from biointel.education.platform import EducationPlatform
from biointel.education.selective_mega import EducationMegaService


class State(dict):
    def __getattr__(self, key: str):
        return self.get(key)

    def __setattr__(self, key: str, value) -> None:
        self[key] = value


class Context:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __getattr__(self, key: str):
        return lambda *args, **kwargs: None


class FakeStreamlit:
    def __init__(self) -> None:
        self.session_state = State(
            education_actor="demo-teacher",
            education_institution="demo-institution",
            education_demo_mode=True,
            education_presentation_mode=True,
            education_demo_persona_picker="demo-teacher",
            education_demo_institution_picker="demo-institution",
            education_show_demo_manifest=True,
        )
        self.errors: list[str] = []

    def container(self, *args, **kwargs):
        return Context()

    def columns(self, columns, *args, **kwargs):
        count = columns if isinstance(columns, int) else len(columns)
        return [Context() for _ in range(count)]

    def caption(self, *args, **kwargs):
        return None

    def error(self, message: str, *args, **kwargs):
        self.errors.append(message)


def test_selected_workspaces_force_real_database_context(tmp_path: Path, monkeypatch) -> None:
    from biointel.education import ui

    platform = EducationPlatform(tmp_path / "real-education.sqlite3", tmp_path / "media")
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)

    assert ui._production_only_context(platform, "classroom") is True
    assert fake.session_state.education_demo_mode is False
    assert fake.session_state.education_presentation_mode is False
    assert fake.session_state.education_actor == "local-operator"
    assert fake.session_state.education_institution == ""
    assert "education_demo_persona_picker" not in fake.session_state
    assert "education_demo_institution_picker" not in fake.session_state
    assert platform.db.path.name == "real-education.sqlite3"
    assert platform.db.quick_check() is True
    assert fake.errors == []

def test_academy_hides_only_the_shared_live_workspace_banner(
    tmp_path: Path, monkeypatch
) -> None:
    from biointel.education import ui

    platform = EducationPlatform(tmp_path / "academy.sqlite3", tmp_path / "media")
    fake = FakeStreamlit()
    banner_calls: list[str] = []

    class BannerContext(Context):
        def subheader(self, text: str, *args, **kwargs):
            banner_calls.append(text)

    fake.container = lambda *args, **kwargs: BannerContext()
    fake.columns = lambda *args, **kwargs: [BannerContext(), BannerContext()]
    monkeypatch.setattr(ui, "st", fake)

    assert ui._production_only_context(platform, "academy") is True
    assert banner_calls == []
    assert fake.session_state.education_demo_mode is False
    assert fake.session_state.education_presentation_mode is False
    assert platform.db.quick_check() is True


def test_active_and_legacy_pages_have_no_demo_entry_path() -> None:
    root = Path(__file__).resolve().parents[1]
    ui_source = (root / "src" / "biointel" / "education" / "ui.py").read_text(
        encoding="utf-8"
    )
    home_start = ui_source.rfind("\ndef render_education_home(root: Path) -> None:")
    classroom_start = ui_source.find("\ndef render_classroom(root: Path) -> None:", home_start)
    exam_start = ui_source.find("\ndef render_examinations(root: Path) -> None:", classroom_start)
    home_block = ui_source[home_start:classroom_start]
    classroom_block = ui_source[classroom_start:exam_start]
    for block in (home_block, classroom_block):
        assert "_demo_controls" not in block
        assert "_page_platform(root, demo" not in block
        assert "_production_only_context" in block

    phase2 = (root / "src" / "biointel" / "education" / "phase2_ui.py").read_text(
        encoding="utf-8"
    )
    visual_start = phase2.index("def render_classroom_visuals")
    visual_end = phase2.index("def render_academy_visuals", visual_start)
    classroom_visuals = phase2[visual_start:visual_end].casefold()
    assert "synthetic" not in classroom_visuals
    assert "demo" not in classroom_visuals

    for relative, renderer in (
        ("pages/150_BioIntel_Education_Home_v17.py", "render_education_home"),
        ("pages/151_BioIntel_Classroom_v17.py", "render_classroom"),
        ("pages/339_BioIntel_Education_Home.py", "render_education_home"),
        ("pages/340_BioIntel_Classroom.py", "render_classroom"),
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert renderer in source
        assert "demo" not in source.casefold()
        assert "seed_education_demo_data" not in source
        assert "std_101" not in source
        assert "2026-07-29" not in source


def test_education_home_exposes_real_school_and_college_sources() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "biointel" / "education" / "selective_mega_ui.py").read_text(
        encoding="utf-8"
    )
    assert "Official school & college sources" in source
    assert "Official website" in source
    assert "Imported real school & college directory" in source
    assert "list_directory_records" in source
    assert "BioIntel will not" in source


def test_home_and_classroom_records_survive_restart(tmp_path: Path) -> None:
    database = tmp_path / "education.sqlite3"
    media = tmp_path / "media"
    root = Path(__file__).resolve().parents[1]
    config = root / "config" / "education_official_sources.json"

    platform = EducationPlatform(database, media)
    institution_id = platform.create_institution("admin", "Live Science College")["id"]
    platform.add_member("admin", institution_id, "teacher", "teacher")
    platform.add_member("admin", institution_id, "student", "student")
    subject = platform.create_subject(
        "admin", institution_id, "BIO-401", "Molecular Diagnostics"
    )
    platform.assign_teacher("admin", institution_id, subject["id"], "teacher")
    platform.enroll("admin", institution_id, subject["id"], "student")
    attendance = platform.attendance_session(
        "teacher", institution_id, subject["id"], "2031-01-10", "1"
    )
    platform.mark_attendance("teacher", attendance["id"], "student", "present")

    service = EducationMegaService(platform, config)
    classroom = service.create_class(
        "teacher",
        institution_id,
        "Molecular Diagnostics 401",
        "MDX-401",
        academic_session="2030-31",
    )
    invitation = service.invite_class_member(
        "teacher", institution_id, classroom["id"], "student", "student"
    )
    with platform.db.connection() as connection:
        connection.execute(
            "UPDATE education_class_members_r9 SET state='active' WHERE id=?",
            (invitation["id"],),
        )
    service.add_stream_post(
        "teacher", institution_id, classroom["id"], "Lab begins at 09:00.", title="Schedule"
    )
    service.create_classwork(
        "teacher",
        institution_id,
        classroom["id"],
        "assignment",
        "Validated assay report",
        state="published",
        max_marks=25,
    )

    reopened = EducationPlatform(database, media)
    reopened_service = EducationMegaService(reopened, config)
    assert reopened.db.quick_check() is True
    assert reopened._one("SELECT COUNT(*) n FROM institutions")["n"] == 1
    assert reopened._one("SELECT COUNT(*) n FROM attendance_records")["n"] == 1
    assert reopened._one("SELECT COUNT(*) n FROM education_audit_events")["n"] > 0
    assert reopened_service.class_access("student", institution_id, classroom["id"])["id"] == classroom["id"]
    snapshot = reopened_service.module_snapshot("teacher", institution_id)
    assert snapshot["classes"] == 1
    assert snapshot["pending_classwork"] == 1
    assert reopened._one("SELECT COUNT(*) n FROM education_stream_posts_r9")["n"] == 1
    assert reopened._one("SELECT COUNT(*) n FROM education_classwork_r9")["n"] == 1


def test_compatibility_aliases_resolve_to_production_renderers() -> None:
    from biointel.education import ui

    assert ui.render_education_home_r8 is ui.render_education_home
    assert ui.render_classroom_r8 is ui.render_classroom
