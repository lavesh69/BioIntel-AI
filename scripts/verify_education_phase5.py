from __future__ import annotations

import tempfile
from pathlib import Path

from biointel.education.phase5 import EducationPhase5Service
from biointel.education.platform import Conflict, Denied, EducationPlatform


def expect_error(error_type, fn) -> bool:
    try:
        fn()
    except error_type:
        return True
    return False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    controls: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        platform = EducationPlatform(work / "education.sqlite3", work / "media")
        admin, teacher, student = "admin", "teacher", "student"
        institution = platform.create_institution(admin, "Phase 5 Verification University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, student, "university_student")
        unit = platform.create_unit(admin, institution, "School of Biosciences", "school")
        subject = platform.create_subject(admin, institution, "BIO-501", "Systems Biology", unit["id"])
        platform.assign_teacher(admin, institution, subject["id"], teacher)
        platform.enroll(admin, institution, subject["id"], student)
        service = EducationPhase5Service(platform, root=work)

        controls.append(("database-quick-check", platform.db.quick_check()))
        controls.append(("phase5-permissions", service.permissions.has(admin, institution, "identity.manage") and service.permissions.has(teacher, institution, "storage.write") and not service.permissions.has(student, institution, "backup.manage")))

        campus = service.create_campus(admin, institution, "MAIN", "Main Campus")
        service.link_unit_to_campus(admin, campus["id"], unit["id"])
        controls.append(("multi-campus-hierarchy", service.hierarchy(admin, institution)["campuses"][0]["unit_ids"] == [unit["id"]]))
        other = platform.create_institution("other-admin", "Other Institution")["id"]
        other_unit = platform.create_unit("other-admin", other, "Other School", "school")
        controls.append(("campus-tenant-isolation", expect_error(Denied, lambda: service.link_unit_to_campus(admin, campus["id"], other_unit["id"]))))

        controls.append(("inline-secret-rejection", expect_error(Denied, lambda: service.configure_identity_provider(admin, institution, "oidc", "Unsafe", issuer_url="https://id.example", secret_reference="client_secret=plain"))))
        posture = service.configure_identity_provider(admin, institution, "oidc", "University SSO", issuer_url="https://id.example", client_id="biointel", secret_reference="vault:oidc", allowed_domains=["university.edu"], activate=True)
        controls.append(("identity-configuration", posture["providers"][0]["secret_reference"] == "configured" and posture["external_login_verified"] is False))
        posture = service.save_mfa_policy(admin, institution, required_roles=["institution_administrator"], methods=["totp", "webauthn"])
        controls.append(("mfa-policy", posture["readiness_score"] == 100))

        controls.append(("postgres-secret-required", expect_error(Conflict, lambda: service.configure_database_profile(admin, institution, "postgresql", "Production", activate=True))))
        profile = service.configure_database_profile(admin, institution, "postgresql", "Production", dsn_reference="vault:postgres", ssl_mode="verify-full", activate=True)
        db_posture = service.database_posture(admin, institution)
        controls.append(("postgres-configuration-readiness", profile["state"] == "configuration_ready" and db_posture["postgresql_configuration_ready"]))
        controls.append(("postgres-honest-qualification", not profile["readiness"]["network_verified"] and not db_posture["production_database_verified"]))

        source = work / "evidence.txt"
        source.write_text("governed institutional evidence", encoding="utf-8")
        first = service.store_local_object(teacher, institution, source)
        second = service.store_local_object(teacher, institution, source)
        controls.append(("tenant-object-storage", Path(first["local_path"]).is_file() and institution in first["local_path"]))
        controls.append(("content-deduplication", first["id"] == second["id"] and second["deduplicated"]))
        controls.append(("object-path-traversal", expect_error(Denied, lambda: service.store_local_object(teacher, institution, source, object_key="../escape"))))

        backup = service.create_backup(admin, institution, "verification")
        controls.append(("verified-online-backup", backup["integrity_valid"] and Path(backup["database_path"]).is_file()))
        rehearsal = service.restore_rehearsal(admin, backup["id"])
        controls.append(("non-destructive-restore-rehearsal", rehearsal["integrity"] == "ok" and rehearsal["live_database_replaced"] is False))

        job = service.enqueue_job(teacher, institution, "generate_report", {"student_id": student}, max_attempts=2)
        claimed = service.claim_job("worker-a")
        controls.append(("durable-job-claim", claimed is not None and claimed["id"] == job["id"] and claimed["state"] == "running"))
        controls.append(("job-lock-ownership", expect_error(Denied, lambda: service.complete_job("worker-b", job["id"], claimed["lock_token"], {"ok": True}))))
        retry = service.fail_job("worker-a", job["id"], claimed["lock_token"], "temporary", retry_delay_seconds=0)
        controls.append(("job-retry-policy", retry["state"] == "queued"))
        claimed = service.claim_job("worker-a")
        done = service.complete_job("worker-a", job["id"], claimed["lock_token"], {"ok": True})
        controls.append(("job-completion", done["state"] == "succeeded"))

        integration = service.configure_integration(admin, institution, "moodle", "Moodle", base_url="https://lms.example", secret_reference="vault:moodle", activate=True)
        checked = service.test_integration_readiness(admin, integration["id"])
        controls.append(("lms-configuration-readiness", checked["state"] == "configuration_ready"))
        controls.append(("external-integration-boundary", checked["readiness"]["network_verified"] is False and checked["readiness"]["external_credentials_verified"] is False))

        invalid = service.preview_import(admin, institution, "members", "invalid.csv", "user_id,role\nalice,bad_role\n")
        controls.append(("invalid-import-block", invalid["invalid_rows"] == 1 and expect_error(Conflict, lambda: service.commit_import(admin, invalid["id"]))))
        valid = service.preview_import(admin, institution, "members", "valid.csv", "user_id,role\nalice,university_student\n")
        committed = service.commit_import(admin, valid["id"])
        controls.append(("transactional-roster-import", committed["state"] == "committed" and bool(platform.membership("alice", institution))))

        report = service.generate_governance_report(admin, institution)
        controls.append(("governance-evidence-report", len(report["sha256"]) == 64 and report["payload"]["human_review_required"]))
        controls.append(("external-qualification-flags", not any(report["payload"]["external_qualification"].values())))

    required = [
        root / "pages/346_BioIntel_Institution_Platform_Center.py",
        root / "src/biointel/education/phase5.py",
        root / "src/biointel/education/institution_ui.py",
        root / "tests/test_education_phase5.py",
    ]
    controls.append(("phase5-app-files", all(path.is_file() for path in required)))
    css = (root / "src/biointel/education/experience.py").read_text(encoding="utf-8")
    controls.append(("phase5-responsive-ui", "edu-platform-grid" in css and "@media (max-width: 700px)" in css))
    navigation = (root / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    controls.append(("phase5-primary-navigation", "biointel_institution_platform" in navigation))
    api = (root / "src/biointel/education/api.py").read_text(encoding="utf-8")
    controls.append(("phase5-typed-api", "class DatabaseProfileData" in api and "/identity/providers" in api and "/imports/preview" in api and "/governance-reports" in api))

    failed = [name for name, passed in controls if not passed]
    print(f"Education Phase 5 verification {'passed' if not failed else 'failed'}: {len(controls) - len(failed)}/{len(controls)} controls")
    for name, passed in controls:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
