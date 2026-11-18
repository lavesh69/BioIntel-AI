from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from biointel.media_tools import ffmpeg_executable
from biointel.education import EducationPlatform,Denied,Conflict,EducationError
class EducationEcosystemTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.p=EducationPlatform(self.root/'edu.db',self.root/'media');self.admin='admin';self.teacher='teacher';self.student='student';self.other='other';self.guardian='guardian';self.inst=self.p.create_institution(self.admin,'Bio University')['id'];self.other_inst=self.p.create_institution(self.other,'Other School','school')['id']
  for user,role in ((self.teacher,'subject_teacher'),(self.student,'university_student'),(self.guardian,'parent_guardian')):self.p.add_member(self.admin,self.inst,user,role)
  self.unit=self.p.create_unit(self.admin,self.inst,'Biotechnology','department')['id'];self.subject=self.p.create_subject(self.admin,self.inst,'BIO101','Molecular Biology',self.unit)['id'];self.p.assign_teacher(self.admin,self.inst,self.subject,self.teacher);self.p.enroll(self.admin,self.inst,self.subject,self.student)
 def tearDown(self):self.t.cleanup()
 def test_tenant_roles_attendance_timetable_and_guardian(self):
  with self.assertRaises(Denied):self.p.create_subject(self.other,self.inst,'X','Cross tenant')
  e=self.p.create_timetable(self.teacher,self.inst,self.subject,self.teacher,'batch-a','lab-1','2030-01-01T09:00','2030-01-01T10:00')
  with self.assertRaises(Conflict):self.p.create_timetable(self.teacher,self.inst,self.subject,self.teacher,'batch-b','lab-2','2030-01-01T09:30','2030-01-01T10:30')
  s=self.p.attendance_session(self.teacher,self.inst,self.subject,'2030-01-01','1');r=self.p.mark_attendance(self.teacher,s['id'],self.student,'present');self.assertEqual(r['status'],'present')
  with self.assertRaises(Denied):self.p.student_attendance(self.guardian,self.inst,self.student)
  self.p.add_guardian_link(self.admin,self.inst,self.guardian,self.student,True);self.p.approve_guardian_link(self.student,self.inst,self.guardian);self.assertEqual(len(self.p.student_attendance(self.guardian,self.inst,self.student)),1);self.assertEqual(self.p.request_attendance_correction(self.student,r['id'],'Incorrect')['state'],'pending')
  self.p.lock_attendance(self.teacher,s['id'])
  with self.assertRaises(Conflict):self.p.mark_attendance(self.teacher,s['id'],self.student,'absent')
  self.assertEqual(e['room'],'lab-1');self.assertGreaterEqual(len(self.p.dashboard(self.student,self.inst)),3)
 def test_material_assignment_grading_exam_results_and_circular(self):
  f=self.root/'notes.pdf';f.write_bytes(b'%PDF-1.4\nreal local file');m=self.p.add_material(self.teacher,self.inst,self.subject,'Unit notes',f);self.assertEqual(len(m['sha256']),64);self.assertTrue(Path(m['storage_path']).is_file())
  a=self.p.create_assignment(self.teacher,self.inst,self.subject,'Sequence review','Analyze evidence','2030-01-10T10:00:00+00:00',50);sub=self.p.submit_assignment(self.student,a['id'],'Completed answer');g=self.p.grade_submission(self.teacher,sub['id'],45,'Good');self.assertEqual(g['marks'],45)
  with self.assertRaises(EducationError):self.p.grade_submission(self.teacher,sub['id'],55)
  exam=self.p.create_examination(self.teacher,self.inst,self.subject,'Internal',100,'2030-02-01T09:00','2030-02-01T12:00');self.p.set_result(self.teacher,exam['id'],self.student,88,'A')
  self.assertEqual(self.p.view_results(self.student,self.inst,self.student),[]);self.p.publish_results(self.admin,exam['id']);self.assertEqual(self.p.view_results(self.student,self.inst,self.student)[0]['grade'],'A')
  c=self.p.create_circular(self.admin,self.inst,'C-001','Exam notice','Official content',['students']);self.assertEqual(c['state'],'draft');self.p.publish_circular(self.admin,c['id']);self.assertEqual(self.p.acknowledge_circular(self.student,c['id'])['user_id'],self.student)
  with self.assertRaises(Denied):self.p.acknowledge_circular(self.other,c['id'])
 def test_science_pulse_real_metadata_dedupe_alerts_and_grounding(self):
  src=self.p.add_pulse_source(self.admin,'Crossref','publication_api','https://api.crossref.org',False);alert=self.p.create_alert(self.student,'genomics','publication')
  meta={'title':'Genomics methods','doi':'10.1/example','source_url':'https://doi.org/10.1/example','authors':['A'], 'preprint':True,'retracted':True};one=self.p.ingest_publication(src['id'],meta);two=self.p.ingest_publication(src['id'],meta);self.assertEqual(one['id'],two['id']);self.assertEqual(one['record_type'],'preprint');self.assertEqual(one['retraction_state'],'retracted')
  self.assertTrue(self.p._all('SELECT * FROM alert_deliveries WHERE alert_id=?',(alert['id'],)));saved=self.p.save_research(self.student,'publication',one['id']);self.assertEqual(saved['user_id'],self.student)
  n=self.p.ingest_news(src['id'],'n-1','Biotech update','Lawful excerpt','https://source.example/n-1','2030-01-01',['biotech']);self.assertEqual(len(self.p.pulse_search('Biotech')['news']),1)
  with self.assertRaises(EducationError):self.p.grounded_summary(self.student,'publication',one['id'],'Summary',[])
  summary=self.p.grounded_summary(self.student,'publication',one['id'],'Grounded summary',[one['source_url']]);self.assertEqual(summary['label'],'AI-generated');self.assertEqual(n['external_id'],'n-1')
 def test_academy_rights_upload_progress_quiz_certificate_and_restart(self):
  self.p.create_educator(self.teacher,self.inst,'Scientist');course=self.p.create_course(self.teacher,self.inst,'Bioinformatics','Course','advanced',True);rights=self.p.confirm_rights(self.teacher,self.inst,'Teacher','CC-BY-4.0');video=self.root/'lecture.mp4';__import__('subprocess').run([ffmpeg_executable(),'-y','-f','lavfi','-i','color=c=black:s=160x120:d=1','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
  lecture=self.p.upload_lecture(self.teacher,course['id'],'Lecture 1',video,rights['id']);self.assertEqual(lecture['processing_state'],'original_ready');self.assertGreater(lecture['duration_seconds'],0)
  with self.assertRaises(Denied):self.p.upload_lecture(self.other,course['id'],'Tamper',video,rights['id'])
  self.p.enroll_course(self.student,course['id']);self.p.update_watch(self.student,lecture['id'],120,True);quiz=self.p.create_quiz(self.teacher,course['id'],'Check',[{'prompt':'DNA?','answer':'yes'}]);attempt=self.p.attempt_quiz(self.student,quiz['id'],['yes']);self.assertTrue(attempt['passed']);cert=self.p.issue_certificate(self.teacher,course['id'],self.student);self.assertFalse(cert['revoked'])
  self.assertEqual(self.p.report_content(self.student,'lecture',lecture['id'],'scientific misinformation concern')['state'],'open');self.assertTrue(self.p.unified_search(self.student,self.inst,'Bioinformatics')['courses'])
  restarted=EducationPlatform(self.root/'edu.db',self.root/'media');self.assertTrue(restarted.db.quick_check());self.assertEqual(restarted._one('SELECT COUNT(*) n FROM certificates')['n'],1)
 def test_api_authz_and_health(self):
  import biointel.education.api as api
  old=api.PLATFORM;api.PLATFORM=self.p
  try:
   app=FastAPI();app.include_router(api.router);client=TestClient(app)
   self.assertEqual(client.get('/api/v1/education/health').status_code,200)
   # default local operator is not a member and must be denied.
   response=client.get(f'/api/v1/education/institutions/{self.inst}/dashboard');self.assertEqual(response.status_code,401)
  finally:api.PLATFORM=old
 def test_real_source_adapters_and_graceful_sync_states(self):
  import io,json
  from biointel.education.adapters import CrossrefAdapter,RssNewsAdapter
  class Response(io.BytesIO):
   def __init__(self,payload,content_type):super().__init__(payload);self.headers={'Content-Type':content_type,'Content-Length':str(len(payload))}
   def __enter__(self):return self
   def __exit__(self,*args):self.close();return False
  crossref_payload=json.dumps({'message':{'items':[{'DOI':'10.1000/test','title':['Verified metadata'],'author':[{'given':'A','family':'Scientist'}],'URL':'https://doi.org/10.1000/test','published':{'date-parts':[[2030,2,3]]},'type':'posted-content'}]}}).encode()
  pubs=CrossrefAdapter('https://api.crossref.org',lambda request,timeout:Response(crossref_payload,'application/json')).fetch('genomics',1);self.assertEqual(pubs[0]['doi'],'10.1000/test');self.assertTrue(pubs[0]['preprint'])
  rss=b'<?xml version="1.0"?><rss><channel><item><guid>n-2</guid><title>Verified biotech news</title><link>https://news.example/n-2</link><description>Short lawful excerpt</description><pubDate>2030-02-03</pubDate></item></channel></rss>'
  news=RssNewsAdapter('https://news.example/feed',lambda request,timeout:Response(rss,'application/rss+xml')).fetch();self.assertEqual(news[0]['external_id'],'n-2')
  from biointel.education.adapters import AdapterError,_read,_validate_url
  with self.assertRaises(AdapterError):_validate_url('ftp://invalid.example/feed')
  with self.assertRaises(AdapterError):_validate_url('http://remote.example/feed')
  self.assertEqual(_validate_url('http://localhost/feed'),'http://localhost/feed')
  with self.assertRaises(AdapterError):CrossrefAdapter('https://api.crossref.org',lambda request,timeout:Response(b'not-json','application/json')).fetch('x')
  with self.assertRaises(AdapterError):RssNewsAdapter('https://news.example/feed',lambda request,timeout:Response(b'<broken','application/xml')).fetch()
  def failed(request,timeout):raise OSError('offline')
  with self.assertRaises(AdapterError):_read('https://offline.example',opener=failed)
  with self.assertRaises(Denied):self.p.add_pulse_source(self.student,'Denied','rss','https://news.example/feed')
  source=self.p.add_pulse_source(self.admin,'Not enabled','rss','https://news.example/feed',False);self.assertEqual(self.p.sync_pulse_source(self.admin,source['id'])['state'],'configuration_required')
  import biointel.education.platform as module
  class FakeCrossref:
   def __init__(self,url):pass
   def fetch(self,query,limit):return pubs
  old=module.CrossrefAdapter
  try:
   module.CrossrefAdapter=FakeCrossref;enabled=self.p.add_pulse_source(self.admin,'Enabled','publication_api','https://api.crossref.org',True);job=self.p.sync_pulse_source(self.admin,enabled['id'],'genomics',1);self.assertEqual(job['state'],'completed');self.assertEqual(job['items_received'],1)
  finally:module.CrossrefAdapter=old
 def test_ui_smoke_all_three_modules(self):
  import biointel.education.ui as ui
  class State(dict):
   def __getattr__(self,key):return self.get(key)
   def __setattr__(self,key,value):self[key]=value
  class Context:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def __getattr__(self,key):return lambda *a,**k:None
  class FakeStreamlit:
   def __init__(self):self.session_state=State(education_actor=self.student,education_institution=self.inst,education_subject=self.subject)
   def form(self,*a,**k):return Context()
   def tabs(self,names):return [Context() for _ in names]
   def columns(self,n,*a,**k):return [Context() for _ in (range(n) if isinstance(n,int) else n)]
   def container(self,*a,**k):return Context()
   def segmented_control(self,label,options,*a,**k):return k.get('default') or options[0]
   def pills(self,label,options,*a,**k):return [] if k.get('selection_mode')=='multi' else (k.get('default') or options[0])
   def dataframe(self,*a,**k):return None
   def text_input(self,*a,**k):return k.get('value','')
   def text_area(self,*a,**k):return k.get('value','')
   def selectbox(self,label,options,*a,**k):return options[0]
   def multiselect(self,label,options,*a,**k):return k.get('default',[])
   def number_input(self,*a,**k):return k.get('value',0.0)
   def date_input(self,*a,**k):return '2030-01-01'
   def checkbox(self,*a,**k):return False
   def file_uploader(self,*a,**k):return None
   def button(self,*a,**k):return False
   def form_submit_button(self,*a,**k):return False
   def __getattr__(self,key):return lambda *a,**k:None
  fake=FakeStreamlit();old_st,old_platform=ui.st,ui._platform
  try:
   ui.st=fake;ui._platform=lambda root:self.p
   ui.render_classroom(self.root);ui.render_pulse(self.root);ui.render_academy(self.root)
   fake.session_state=State()
   ui.render_classroom(self.root);ui.render_academy(self.root)
   self.assertIsNone(ui._run(lambda:(_ for _ in ()).throw(EducationError('expected'))))
  finally:ui.st=old_st;ui._platform=old_platform
 def test_navigation_exposes_all_three_modules(self):
  from biointel.ui.navigation import CATEGORIES,PAGE_BY_KEY,SIDEBAR_PRIMARY,catalogue_integrity
  expected={"biointel_classroom":"pages/340_BioIntel_Classroom.py","biointel_science_pulse":"pages/341_BioIntel_Science_Pulse.py","biointel_academy":"pages/342_BioIntel_Academy_and_Lecture_Studio.py"}
  self.assertIn("Education",CATEGORIES);self.assertIn("Scientific Intelligence",CATEGORIES)
  for key,path in expected.items():self.assertIn(key,SIDEBAR_PRIMARY);self.assertEqual(PAGE_BY_KEY[key].path,path)
  project_root=Path(__file__).resolve().parents[1];self.assertTrue(catalogue_integrity(project_root)["healthy"])
  app=(project_root/"app.py").read_text(encoding="utf-8")
  for key in expected:self.assertIn(f'safe_page_link("{key}"',app)
if __name__=='__main__':unittest.main()



