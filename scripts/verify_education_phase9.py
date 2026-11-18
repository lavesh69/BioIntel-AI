from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
checks={}
ui=(ROOT/'src/biointel/ui/product_experience_v8.py').read_text(encoding='utf-8')
for token in [
 'Phase 9 full visibility pass','bx-status-rail','Visible workspace','bx-section-shell',
 'bx-empty','stFileUploader','stExpander','stPlotlyChart','stDataEditor','section_shell_header',
 'visible_empty_state','min-width:21rem','white-space:normal','bx-course-card','bx-course-cover'
]: checks[token]=token in ui
exp=(ROOT/'src/biointel/education/experience.py').read_text(encoding='utf-8')
checks['shared_education_header']='render_product_hero' in exp
checks['permission_navigation']='PAGE_PERMISSIONS' in exp and 'resolver.has' in exp
for path in ['pages/339_BioIntel_Education_Home.py','pages/340_BioIntel_Classroom.py','pages/341_BioIntel_Science_Pulse.py','pages/342_BioIntel_Academy_and_Lecture_Studio.py','pages/343_BioIntel_Education_Universe.py','pages/344_BioIntel_Examination_Command_Center.py','pages/345_BioIntel_Education_Intelligence_Hub.py','pages/346_BioIntel_Institution_Platform_Center.py','pages/347_BioIntel_Education_Visual_Command_Center.py','pages/348_BioIntel_Education_Desktop.py']:
 checks[path]=(ROOT/path).exists()
failed=[k for k,v in checks.items() if not v]
print(json.dumps({'phase':9,'passed':sum(checks.values()),'total':len(checks),'failed':failed},indent=2))
raise SystemExit(1 if failed else 0)
