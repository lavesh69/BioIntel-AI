from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS: list[tuple[str, bool]] = []

def check(name: str, condition: bool) -> None:
    CHECKS.append((name, bool(condition)))

visual = ROOT / "src/biointel/ui/product_experience_v8.py"
experience = ROOT / "src/biointel/education/experience.py"
phase2 = ROOT / "src/biointel/education/phase2_ui.py"
academy = ROOT / "src/biointel/education/academy_ui.py"
connect = ROOT / "src/biointel/connect/pro_ui.py"
shiro = ROOT / "src/biointel/shiro/ui/page.py"
studio = ROOT / "pages/70_BioIntel_Studio.py"

for path in (visual, experience, phase2, academy, connect, shiro, studio):
    check(f"exists:{path.relative_to(ROOT)}", path.is_file())
    if path.is_file():
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))

text = visual.read_text(encoding="utf-8")
check("profile-count", text.count("ProductProfile(") >= 13)
check("sidebar-width", 'min-width:21rem' in text and 'white-space:normal' in text)
check("scientific-hero", 'bx-hero' in text and 'bx-orbit' in text and 'bx-helix' in text)
check("academy-course-card", 'bx-course-card' in text and 'course_card_markup' in text)
check("reduced-motion", 'prefers-reduced-motion' in text)
check("education-shared-hero", 'render_product_hero(' in experience.read_text(encoding="utf-8-sig"))
check("academy-visual-gallery", 'bx-course-grid' in phase2.read_text(encoding="utf-8-sig"))
check("academy-catalog-covers", 'course_cover_markup' in academy.read_text(encoding="utf-8-sig"))
check("connect-themed", 'render_product_hero' in connect.read_text(encoding="utf-8-sig"))
check("shiro-themed", 'render_product_hero' in shiro.read_text(encoding="utf-8-sig"))
check("studio-themed", 'render_product_hero' in studio.read_text(encoding="utf-8-sig"))

failed = [name for name, ok in CHECKS if not ok]
result = {"phase": 8, "passed": len(CHECKS) - len(failed), "total": len(CHECKS), "failed": failed}
print(json.dumps(result, indent=2))
raise SystemExit(1 if failed else 0)
