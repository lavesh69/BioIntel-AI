from __future__ import annotations

import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks: dict[str, bool] = {}

frontend_path = ROOT / "src/biointel/ui/frontend_v10.py"
frontend = frontend_path.read_text(encoding="utf-8")
for token in (
    "Phase 10 full frontend completion", "bx10-compact-hero", "bx10-capability-grid",
    "bx10-kpi-grid", "bx10-action-grid", "bx10-empty", "bx10-timeline",
    "stChatMessage", "stChatInput", "stDataFrame", "stDataEditor", "stFileUploader",
    "stPlotlyChart", "stVegaLiteChart", "stForm", "stMetric", "stPageLink",
    "CAPABILITIES", '"connect"', '"shiro"', '"studio"', '"classroom"',
    '"academy"', '"universe"', '"examinations"', '"intelligence"', '"institution"',
):
    checks[f"frontend:{token}"] = token in frontend

product = (ROOT / "src/biointel/ui/product_experience_v8.py").read_text(encoding="utf-8")
checks["product:phase10_css"] = "FRONTEND_V10_CSS" in product
checks["product:icon_tiles"] = "bx-module-icon" in product and "icon_for_kicker" in product
checks["product:backward_compatible_tiles"] = "tuple[str, str, str] | tuple[str, str, str, str]" in product

experience = (ROOT / "src/biointel/education/experience.py").read_text(encoding="utf-8")
checks["education:capability_deck"] = "capability_grid(page_key)" in experience
checks["education:visual_kpis"] = "kpi_grid" in experience
checks["education:friendly_identity"] = "friendly_actor" in experience
checks["education:permission_navigation"] = "PAGE_PERMISSIONS" in experience and "resolver.has" in experience

connect = (ROOT / "src/biointel/connect/ui.py").read_text(encoding="utf-8")
checks["connect:global_skin"] = 'apply_frontend_v10("connect")' in connect
checks["connect:compact_header"] = "compact_page_header" in connect
checks["connect:capability_cards"] = 'capability_grid("connect")' in connect
checks["connect:visual_author"] = "person_header" in connect
checks["connect:two_row_navigation"] = "range(0, len(links), 5)" in connect
checks["connect:empty_feed"] = "Your scientific feed is ready" in connect

advanced = (ROOT / "src/biointel/connect/advanced_ui.py").read_text(encoding="utf-8")
complete = (ROOT / "src/biointel/connect/complete_ui.py").read_text(encoding="utf-8")
checks["connect:advanced_empty_state"] = "No persisted records yet" in advanced and "empty_state" in advanced
checks["connect:message_empty_state"] = "No conversations yet" in complete and "empty_state" in complete
checks["connect:moderation_empty_state"] = "Moderation queue is clear" in complete

shiro = (ROOT / "src/biointel/shiro/ui/page.py").read_text(encoding="utf-8")
checks["shiro:global_skin"] = 'apply_frontend_v10("shiro")' in shiro
checks["shiro:visible_empty_state"] = "No BioIntel project is available" in shiro and "empty_state" in shiro

primary_pages = (
    "pages/70_BioIntel_Studio.py", "pages/273_Shiro_AI.py", "pages/300_BioIntel_Connect_Home.py",
    "pages/339_BioIntel_Education_Home.py", "pages/340_BioIntel_Classroom.py",
    "pages/341_BioIntel_Science_Pulse.py", "pages/342_BioIntel_Academy_and_Lecture_Studio.py",
    "pages/343_BioIntel_Education_Universe.py", "pages/344_BioIntel_Examination_Command_Center.py",
    "pages/345_BioIntel_Education_Intelligence_Hub.py", "pages/346_BioIntel_Institution_Platform_Center.py",
    "pages/347_BioIntel_Education_Visual_Command_Center.py", "pages/348_BioIntel_Education_Desktop.py",
)
for path in primary_pages:
    checks[f"page:{path}"] = (ROOT / path).is_file()

connect_pages = sorted((ROOT / "pages").glob("3*_Connect_*.py"))
checks["connect:page_count"] = len(connect_pages) >= 28
checks["connect:all_entrypoints"] = all("biointel.connect" in page.read_text(encoding="utf-8-sig") for page in connect_pages)

for relative in (
    "src/biointel/ui/frontend_v10.py", "src/biointel/ui/product_experience_v8.py",
    "src/biointel/education/experience.py", "src/biointel/connect/ui.py",
    "src/biointel/connect/complete_ui.py", "src/biointel/connect/advanced_ui.py",
    "src/biointel/shiro/ui/page.py",
):
    try:
        py_compile.compile(str(ROOT / relative), doraise=True)
        checks[f"compile:{relative}"] = True
    except py_compile.PyCompileError:
        checks[f"compile:{relative}"] = False


manifest_path = ROOT / "EDUCATION_PHASE10_SOURCE_MANIFEST_SHA256.json"
checks["release:source_manifest"] = manifest_path.is_file() and '"file_count"' in manifest_path.read_text(encoding="utf-8")
checks["release:manifest_verifier"] = (ROOT / "scripts/verify_education_phase10_manifest.py").is_file()
checks["release:four_part_markers"] = all((ROOT / f".release_parts/education_phase10_part{part}.ok").is_file() for part in range(1, 5))

education_empty_states = sum(path.read_text(encoding="utf-8", errors="ignore").count("empty_state(") for path in (ROOT / "src/biointel/education").glob("*_ui.py"))
checks["education:illustrated_empty_states"] = education_empty_states >= 25

failed = [name for name, passed in checks.items() if not passed]
print(json.dumps({"phase": 10, "passed": sum(checks.values()), "total": len(checks), "failed": failed}, indent=2))
raise SystemExit(1 if failed else 0)
