from __future__ import annotations

from pathlib import Path

from biointel.education.database import MIGRATION_ID, EducationDatabase
from biointel.education.platform import UnifiedEducationPlatform


def test_database_migration_is_current_and_integrity_safe(tmp_path: Path):
    database = EducationDatabase(tmp_path / "education.db")
    migration = database.migrate()
    assert migration == MIGRATION_ID
    assert database.quick_check()
    assert database.migrate() == migration


def test_unified_platform_legacy_constructor_is_secure(tmp_path: Path):
    platform = UnifiedEducationPlatform(tmp_path / "education.db")
    institution = platform.create_institution("admin", "Compatibility University")
    platform.add_member("admin", institution["id"], "student", "university_student")

    student = platform.get_user_context("student", institution["id"])
    assert student["role"] == "student"
    assert student["authenticated"] is True

    unknown = platform.get_user_context("unknown", institution["id"])
    assert unknown["role"] == "guest"
    assert unknown["authenticated"] is False


def test_legacy_permission_aliases_do_not_grant_admin_access():
    assert UnifiedEducationPlatform.check_permission("platform_admin", "any_action")
    assert UnifiedEducationPlatform.check_permission("student", "submit_assignment")
    assert not UnifiedEducationPlatform.check_permission("student", "approve_results")
    assert not UnifiedEducationPlatform.check_permission("guest", "submit_assignment")
