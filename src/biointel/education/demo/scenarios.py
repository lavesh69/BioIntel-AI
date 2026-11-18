"""Stable fictional institutions, personas and connected demo scenarios."""

from __future__ import annotations

INSTITUTIONS = (
    {"id": "demo-inst-university", "name": "BioIntel Demonstration University", "kind": "university", "timezone": "Asia/Kolkata", "academic_session": "2026-27"},
    {"id": "demo-inst-school", "name": "BioIntel Demonstration School", "kind": "school", "timezone": "Asia/Kolkata", "academic_session": "2026-27"},
)

PERSONAS = (
    ("demo-persona-university-admin", "Aditi Varma", "University administrator", "institution_administrator", "demo-inst-university"),
    ("demo-persona-school-admin", "Neelam Kapoor", "School administrator", "principal", "demo-inst-school"),
    ("demo-persona-department-head", "Kabir Sen", "Department head", "department_head", "demo-inst-university"),
    ("demo-persona-professor", "Mira Iyer", "Professor", "professor", "demo-inst-university"),
    ("demo-persona-teacher", "Rohan Das", "Teacher", "subject_teacher", "demo-inst-school"),
    ("demo-persona-lab-instructor", "Farah Malik", "Laboratory instructor", "laboratory_instructor", "demo-inst-university"),
    ("demo-persona-research-mentor", "Aarav Menon", "Research mentor", "academic_mentor", "demo-inst-university"),
    ("demo-persona-librarian", "Leela Anand", "Librarian", "librarian", "demo-inst-university"),
    ("demo-persona-career-coordinator", "Vikram Kohli", "Career coordinator", "career_coordinator", "demo-inst-university"),
    ("demo-persona-academic-coordinator", "Naina Rao", "Academic coordinator", "class_coordinator", "demo-inst-school"),
    ("demo-persona-moderator", "Devika Bose", "Moderator", "moderator", "demo-inst-university"),
    ("demo-persona-university-student", "Isha Nair", "University student", "university_student", "demo-inst-university"),
    ("demo-persona-school-student", "Arjun Mehta", "School student", "school_student", "demo-inst-school"),
    ("demo-persona-guardian", "Suman Mehta", "Guardian", "parent_guardian", "demo-inst-school"),
)

SCENARIOS = (
    {"id": "student-learning-lifecycle", "title": "Student learning lifecycle", "modules": ["classroom", "academy", "shiro_tutor", "learning_analytics", "academic_portfolio"], "persona_id": "demo-persona-university-student", "institution_id": "demo-inst-university"},
    {"id": "teacher-course-workflow", "title": "Teacher course workflow", "modules": ["academy", "shiro_tutor", "lecture_intelligence", "classroom"], "persona_id": "demo-persona-professor", "institution_id": "demo-inst-university"},
    {"id": "student-research-workflow", "title": "Student research workflow", "modules": ["science_pulse", "digital_library", "research_hub", "shiro_tutor", "academic_portfolio"], "persona_id": "demo-persona-university-student", "institution_id": "demo-inst-university"},
    {"id": "live-lecture-workflow", "title": "Live lecture workflow", "modules": ["classroom", "lecture_intelligence", "academy", "shiro_tutor"], "persona_id": "demo-persona-teacher", "institution_id": "demo-inst-school"},
)


def persona_manifest() -> list[dict[str, str | bool]]:
    return [
        {
            "id": item[0], "name": item[1], "persona_type": item[2], "role": item[3],
            "institution_id": item[4], "switch_label": f"{item[1]} - {item[2]}",
            "is_fictional": True,
        }
        for item in PERSONAS
    ]
