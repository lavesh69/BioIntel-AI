from __future__ import annotations
import hashlib,hmac,json,mimetypes,os,secrets,shutil,subprocess,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from biointel.media_tools import ffmpeg_executable, media_duration
from .database import EducationDatabase
from .adapters import AdapterError,CrossrefAdapter,RssNewsAdapter

def now()->str:return datetime.now(timezone.utc).isoformat()
def ident(prefix:str)->str:return f'{prefix}_{uuid.uuid4().hex}'
def row(r):return dict(r) if r else None
class EducationError(Exception):pass
class Denied(EducationError):pass
class Missing(EducationError):pass
class Conflict(EducationError):pass

ADMIN={'platform_administrator','institution_administrator','principal','director','principal_director','dean','registrar','department_head','examination_controller'}
TEACHER=ADMIN|{'teacher','faculty','subject_teacher','class_teacher','lecturer','assistant_professor','professor','teaching_assistant','laboratory_instructor','academic_mentor','class_coordinator'}
STUDENT={'student','school_student','college_student','university_student'}
ATTENDANCE={'present','absent','late','excused_absence','medical_leave','institutional_duty','online_present','practical_attendance','examination_attendance'}
ROLES=ADMIN|TEACHER|STUDENT|{
 'parent_guardian','guest_educator','guest','viewer','research_mentor','career_counsellor','counsellor',
 'librarian','laboratory_manager','content_moderator','evaluator','invigilator',
}
LATE_POLICIES={'reject','allow','allow_with_penalty','manual_approval'}
ALLOWED_VIDEO_EXTENSIONS={'.mp4','.mov','.m4v','.webm','.mkv','.avi'}
VIDEO_SIGNATURES=(b'\x1aE\xdf\xa3',b'RIFF',b'ftyp',b'\x00\x00\x00')

def parse_time(value:str)->datetime:
 text=str(value or '').strip()
 if not text:raise EducationError('A date and time is required.')
 try:parsed=datetime.fromisoformat(text.replace('Z','+00:00'))
 except ValueError as exc:raise EducationError('Date and time must be ISO-8601.') from exc
 if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
 return parsed.astimezone(timezone.utc)

def _file_signature(path:Path)->bytes:
 with path.open('rb') as handle:return handle.read(32)

def _looks_like_video(path:Path)->bool:
 head=_file_signature(path)
 if path.suffix.lower() in {'.mp4','.mov','.m4v'}:return b'ftyp' in head
 if path.suffix.lower()=='.webm' or path.suffix.lower()=='.mkv':return head.startswith(b'\x1aE\xdf\xa3')
 if path.suffix.lower()=='.avi':return head.startswith(b'RIFF') and b'AVI' in head
 return False

class EducationPlatform:
 def __init__(self,path:Path,storage:Path):
  self.db=EducationDatabase(path);self.db.migrate();self.storage=Path(storage);self.storage.mkdir(parents=True,exist_ok=True)
  secret_path=self.storage/'.education-signing-key'
  if not secret_path.exists():secret_path.write_text(secrets.token_hex(32),encoding='utf-8')
  self._signing_key=secret_path.read_text(encoding='utf-8').strip().encode('utf-8')
 def _signature(self,payload:str)->str:return hmac.new(self._signing_key,payload.encode('utf-8'),hashlib.sha256).hexdigest()
 def _video_duration(self,path:Path)->float:
  return media_duration(path)
 def _prepare_submission_file(self,institution_id:str,assignment_id:str,student_id:str,source_path:str,allowed_types:list[str])->dict[str,Any]:
  src=Path(source_path).expanduser().resolve()
  if not src.is_file():raise Missing('Submission file not found.')
  if src.stat().st_size>250*1024**2:raise EducationError('Submission file exceeds the 250 MiB limit.')
  suffix=src.suffix.lower();blocked={'.exe','.dll','.msi','.bat','.cmd','.ps1','.vbs','.js','.scr','.com'}
  if suffix in blocked:raise Denied('Executable or script attachments are not allowed.')
  mime=mimetypes.guess_type(src.name)[0] or 'application/octet-stream'
  allowed={str(item).strip().lower() for item in allowed_types if str(item).strip()}
  if allowed and suffix not in allowed and mime.lower() not in allowed and src.name.lower() not in allowed:raise EducationError('Submission file type is not allowed for this assignment.')
  head=_file_signature(src)
  signatures={'.pdf':lambda b:b.startswith(b'%PDF-'),'.png':lambda b:b.startswith(b'\x89PNG'),'.jpg':lambda b:b.startswith(b'\xff\xd8\xff'),'.jpeg':lambda b:b.startswith(b'\xff\xd8\xff'),'.zip':lambda b:b.startswith(b'PK'),'.docx':lambda b:b.startswith(b'PK'),'.xlsx':lambda b:b.startswith(b'PK'),'.pptx':lambda b:b.startswith(b'PK')}
  if suffix in signatures and not signatures[suffix](head):raise EducationError('Attachment content does not match its file extension.')
  if mime.startswith('text/') and b'\x00' in head:raise EducationError('Text attachment contains invalid binary content.')
  sid=ident('file');folder=self.storage/institution_id/'submissions'/assignment_id/student_id;folder.mkdir(parents=True,exist_ok=True);dest=folder/f'{sid}{suffix}'
  digest=hashlib.sha256()
  with src.open('rb') as inp,dest.open('wb') as out:
   while chunk:=inp.read(1024*1024):digest.update(chunk);out.write(chunk)
  return {'file_path':str(dest),'file_name':src.name[:255],'mime_type':mime,'size_bytes':dest.stat().st_size,'sha256':digest.hexdigest()}
 def _one(self,sql:str,args=()):
  with self.db.connection() as db:return row(db.execute(sql,args).fetchone())
 def _all(self,sql:str,args=()):
  with self.db.connection() as db:return [dict(x) for x in db.execute(sql,args).fetchall()]
 def _audit(self,actor,action,target_type,target_id,institution_id='',detail=None):
  with self.db.connection() as db:db.execute('INSERT INTO education_audit_events VALUES(?,?,?,?,?,?,?,?)',(ident('aud'),institution_id,actor,action,target_type,target_id,json.dumps(detail or {},sort_keys=True),now()))
 def create_institution(self,actor:str,name:str,kind='university',timezone_name='UTC'):
  if not name.strip():raise EducationError('Institution name is required.')
  iid=ident('inst');t=now()
  with self.db.connection() as db:
   db.execute('INSERT INTO institutions VALUES(?,?,?,?,?,?,?)',(iid,name.strip(),kind,timezone_name,'active',t,t));db.execute('INSERT INTO memberships VALUES(?,?,?,?,?,?,?)',(ident('mem'),iid,actor,'institution_administrator','active',t,t))
  self._audit(actor,'institution_created','institution',iid,iid);return self._one('SELECT * FROM institutions WHERE id=?',(iid,))
 def add_member(self,actor,institution_id,user_id,role):
  self._require(actor,institution_id,ADMIN)
  role=str(role).strip()
  if role not in ROLES:raise EducationError('Unsupported institution role.')
  if not str(user_id).strip():raise EducationError('User ID is required.')
  t=now()
  with self.db.connection() as db:db.execute('INSERT INTO memberships VALUES(?,?,?,?,?,?,?) ON CONFLICT(institution_id,user_id,role) DO UPDATE SET state="active",updated_at=excluded.updated_at',(ident('mem'),institution_id,user_id,role,'active',t,t))
  self._audit(actor,'member_added','user',user_id,institution_id,{'role':role});return self.membership(user_id,institution_id)
 def membership(self,user_id,institution_id):return self._all('SELECT * FROM memberships WHERE user_id=? AND institution_id=? AND state="active"',(user_id,institution_id))
 def _require(self,actor,institution_id,roles:set[str]|None=None):
  ms=self.membership(actor,institution_id)
  if not ms or (roles is not None and not any(x['role'] in roles for x in ms)):raise Denied('Institution permission denied.')
  return ms
 def create_unit(self,actor,institution_id,name,unit_type,parent_id=None,academic_year=''):
  self._require(actor,institution_id,ADMIN);uid=ident('unit');t=now()
  if parent_id:
   p=self._one('SELECT institution_id FROM academic_units WHERE id=?',(parent_id,))
   if not p or p['institution_id']!=institution_id:raise Denied('Invalid parent unit.')
  with self.db.connection() as db:db.execute('INSERT INTO academic_units VALUES(?,?,?,?,?,?,?,?,?)',(uid,institution_id,parent_id,unit_type,name,academic_year,'active',t,t))
  return self._one('SELECT * FROM academic_units WHERE id=?',(uid,))
 def create_subject(self,actor,institution_id,code,name,unit_id=None,syllabus=''):
  self._require(actor,institution_id,ADMIN);sid=ident('subj');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO subjects VALUES(?,?,?,?,?,?,?,?,?)',(sid,institution_id,unit_id,code,name,syllabus,'active',t,t))
  return self._one('SELECT * FROM subjects WHERE id=?',(sid,))
 def assign_teacher(self,actor,institution_id,subject_id,teacher_id):
  self._require(actor,institution_id,ADMIN);self._subject(institution_id,subject_id);t=now()
  with self.db.connection() as db:db.execute('INSERT OR REPLACE INTO teacher_assignments VALUES(?,?,?,?,?,?,?)',(ident('ta'),institution_id,subject_id,teacher_id,'active',t,t))
  return self._one('SELECT * FROM teacher_assignments WHERE subject_id=? AND teacher_id=?',(subject_id,teacher_id))
 def enroll(self,actor,institution_id,subject_id,student_id):
  self._require(actor,institution_id,ADMIN|TEACHER);self._subject(institution_id,subject_id);t=now()
  with self.db.connection() as db:db.execute('INSERT OR REPLACE INTO enrollments VALUES(?,?,?,?,?,?,?)',(ident('enr'),institution_id,subject_id,student_id,'active',t,t))
  return self._one('SELECT * FROM enrollments WHERE subject_id=? AND student_id=?',(subject_id,student_id))
 def _subject(self,institution_id,subject_id):
  s=self._one('SELECT * FROM subjects WHERE id=?',(subject_id,))
  if not s:raise Missing('Subject not found.')
  if s['institution_id']!=institution_id:raise Denied('Cross-institution subject access denied.')
  return s
 def _teacher(self,actor,institution_id,subject_id):
  if any(x['role'] in ADMIN for x in self._require(actor,institution_id)):return
  if not self._one('SELECT 1 ok FROM teacher_assignments WHERE subject_id=? AND teacher_id=? AND state="active"',(subject_id,actor)):raise Denied('Teacher is not assigned to this subject.')
 def create_timetable(self,actor,institution_id,subject_id,teacher_id,student_group,room,starts_at,ends_at,meeting_id=''):
  self._require(actor,institution_id,TEACHER);self._subject(institution_id,subject_id)
  if ends_at<=starts_at:raise EducationError('End must follow start.')
  clash=self._one('SELECT id FROM timetable_entries WHERE institution_id=? AND state="scheduled" AND starts_at<? AND ends_at>? AND (teacher_id=? OR room=? OR student_group=?)',(institution_id,ends_at,starts_at,teacher_id,room,student_group))
  if clash:raise Conflict('Teacher, room or student-group timetable conflict.')
  eid=ident('time');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO timetable_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(eid,institution_id,subject_id,teacher_id,student_group,room,starts_at,ends_at,meeting_id,'scheduled',t,t))
  return self._one('SELECT * FROM timetable_entries WHERE id=?',(eid,))
 def attendance_session(self,actor,institution_id,subject_id,session_date,period):
  self._teacher(actor,institution_id,subject_id);sid=ident('atts');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO attendance_sessions VALUES(?,?,?,?,?,?,?,?,?)',(sid,institution_id,subject_id,actor,session_date,period,'open',t,t))
  return self._one('SELECT * FROM attendance_sessions WHERE id=?',(sid,))
 def mark_attendance(self,actor,session_id,student_id,status,note=''):
  if status not in ATTENDANCE:raise EducationError('Invalid attendance status.')
  s=self._one('SELECT * FROM attendance_sessions WHERE id=?',(session_id,))
  if not s:raise Missing('Attendance session not found.')
  self._teacher(actor,s['institution_id'],s['subject_id'])
  if s['state']!='open':raise Conflict('Attendance session is locked.')
  if not self._one('SELECT 1 ok FROM enrollments WHERE subject_id=? AND student_id=? AND state="active"',(s['subject_id'],student_id)):raise Denied('Student is not enrolled.')
  t=now();rid=ident('attr')
  with self.db.connection() as db:db.execute('INSERT INTO attendance_records VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id,student_id) DO UPDATE SET status=excluded.status,note=excluded.note,marked_by=excluded.marked_by,updated_at=excluded.updated_at',(rid,s['institution_id'],session_id,student_id,status,note,actor,t,t))
  self._audit(actor,'attendance_marked','student',student_id,s['institution_id'],{'session_id':session_id,'status':status});return self._one('SELECT * FROM attendance_records WHERE session_id=? AND student_id=?',(session_id,student_id))
 def lock_attendance(self,actor,session_id):
  s=self._one('SELECT * FROM attendance_sessions WHERE id=?',(session_id,));self._teacher(actor,s['institution_id'],s['subject_id'])
  with self.db.connection() as db:db.execute('UPDATE attendance_sessions SET state="locked",updated_at=? WHERE id=?',(now(),session_id))
  return self._one('SELECT * FROM attendance_sessions WHERE id=?',(session_id,))
 def request_attendance_correction(self,actor,record_id,reason):
  r=self._one('SELECT * FROM attendance_records WHERE id=?',(record_id,))
  if not r or (r['student_id']!=actor and not self._guardian_can(actor,r['institution_id'],r['student_id'])):raise Denied('Correction request access denied.')
  cid=ident('ac');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO attendance_corrections VALUES(?,?,?,?,?,?,?,?,?)',(cid,r['institution_id'],record_id,actor,reason,'pending','',t,t))
  return self._one('SELECT * FROM attendance_corrections WHERE id=?',(cid,))
 def add_guardian_link(self,actor,institution_id,guardian_id,student_id,student_consent=False):
  self._require(actor,institution_id,ADMIN)
  if not any(x['role']=='parent_guardian' for x in self.membership(guardian_id,institution_id)):raise Denied('Guardian must have an active parent/guardian membership.')
  if not any(x['role'] in STUDENT for x in self.membership(student_id,institution_id)):raise Denied('Student must have an active student membership.')
  gid=ident('guard');t=now()
  with self.db.connection() as db:
   db.execute('''INSERT INTO guardian_links(id,institution_id,guardian_id,student_id,verified,student_consent,state,requested_by,consented_at,revoked_at,created_at,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(institution_id,guardian_id,student_id) DO UPDATE SET verified=1,student_consent=0,state='pending',requested_by=excluded.requested_by,consented_at=NULL,revoked_at=NULL,updated_at=excluded.updated_at''',(gid,institution_id,guardian_id,student_id,1,0,'pending',actor,None,None,t,t))
  self._audit(actor,'guardian_link_requested','student',student_id,institution_id,{'guardian_id':guardian_id,'admin_cannot_self_assert_consent':bool(student_consent)})
  return self._one('SELECT * FROM guardian_links WHERE institution_id=? AND guardian_id=? AND student_id=?',(institution_id,guardian_id,student_id))
 def approve_guardian_link(self,actor,institution_id,guardian_id):
  self._require(actor,institution_id,STUDENT)
  link=self._one('SELECT * FROM guardian_links WHERE institution_id=? AND guardian_id=? AND student_id=?',(institution_id,guardian_id,actor))
  if not link:raise Missing('Pending guardian link not found.')
  t=now()
  with self.db.connection() as db:db.execute("UPDATE guardian_links SET student_consent=1,state='active',consented_at=?,revoked_at=NULL,updated_at=? WHERE id=?",(t,t,link['id']))
  self._audit(actor,'guardian_link_consented','guardian_link',link['id'],institution_id,{'guardian_id':guardian_id})
  return self._one('SELECT * FROM guardian_links WHERE id=?',(link['id'],))
 def revoke_guardian_link(self,actor,institution_id,guardian_id,student_id=None):
  target=student_id or actor
  roles={x['role'] for x in self._require(actor,institution_id)}
  if actor!=target and not roles&ADMIN:raise Denied('Only the student or an administrator may revoke guardian access.')
  link=self._one('SELECT * FROM guardian_links WHERE institution_id=? AND guardian_id=? AND student_id=?',(institution_id,guardian_id,target))
  if not link:raise Missing('Guardian link not found.')
  t=now()
  with self.db.connection() as db:db.execute("UPDATE guardian_links SET student_consent=0,state='revoked',revoked_at=?,updated_at=? WHERE id=?",(t,t,link['id']))
  self._audit(actor,'guardian_link_revoked','guardian_link',link['id'],institution_id,{'guardian_id':guardian_id,'student_id':target})
  return self._one('SELECT * FROM guardian_links WHERE id=?',(link['id'],))
 def _guardian_can(self,actor,institution_id,student_id):return bool(self._one('SELECT 1 ok FROM guardian_links WHERE institution_id=? AND guardian_id=? AND student_id=? AND verified=1 AND student_consent=1 AND state="active"',(institution_id,actor,student_id)))
 def student_attendance(self,actor,institution_id,student_id):
  self._require(actor,institution_id)
  if actor!=student_id and not self._guardian_can(actor,institution_id,student_id) and not any(x['role'] in TEACHER for x in self.membership(actor,institution_id)):raise Denied('Student record access denied.')
  return self._all('SELECT r.*,s.subject_id,s.session_date,s.period FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE r.institution_id=? AND r.student_id=? ORDER BY s.session_date DESC',(institution_id,student_id))
 def add_material(self,actor,institution_id,subject_id,title,source_path:Path,download_allowed=True):
  self._teacher(actor,institution_id,subject_id);src=Path(source_path)
  if not src.is_file():raise Missing('Material file not found.')
  size=src.stat().st_size
  if size>2*1024**3:raise EducationError('Material exceeds 2 GiB limit.')
  mid=ident('mat');folder=self.storage/institution_id/'materials';folder.mkdir(parents=True,exist_ok=True);dest=folder/f'{mid}{src.suffix.lower()}'
  h=hashlib.sha256()
  with src.open('rb') as inp,dest.open('wb') as out:
   while chunk:=inp.read(1024*1024):h.update(chunk);out.write(chunk)
  t=now();mime=mimetypes.guess_type(src.name)[0] or 'application/octet-stream'
  with self.db.connection() as db:db.execute('INSERT INTO materials VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(mid,institution_id,subject_id,actor,title,src.name,mime,size,h.hexdigest(),str(dest),int(download_allowed),'published',t,t))
  return self._one('SELECT * FROM materials WHERE id=?',(mid,))
 def create_assignment(self,actor,institution_id,subject_id,title,instructions,due_at,max_marks,allowed_types=None,late_policy='reject',publish=True):
  self._teacher(actor,institution_id,subject_id)
  if not str(title).strip():raise EducationError('Assignment title is required.')
  parse_time(due_at)
  if float(max_marks)<=0:raise EducationError('Maximum marks must be greater than zero.')
  policy=str(late_policy).strip().lower()
  if policy not in LATE_POLICIES:raise EducationError('Unsupported late-submission policy.')
  allowed=[str(x).strip().lower() for x in (allowed_types or []) if str(x).strip()]
  aid=ident('asg');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO assignments VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(aid,institution_id,subject_id,actor,title.strip(),str(instructions),due_at,float(max_marks),json.dumps(allowed),policy,'published' if publish else 'draft',t,t))
  self._audit(actor,'assignment_created','assignment',aid,institution_id,{'due_at':due_at,'late_policy':policy})
  return self._one('SELECT * FROM assignments WHERE id=?',(aid,))
 def submit_assignment(self,actor,assignment_id,body='',file_path='',final=True):
  a=self._one('SELECT * FROM assignments WHERE id=?',(assignment_id,))
  if not a or a['state']!='published':raise Missing('Published assignment not found.')
  if not self._one('SELECT 1 ok FROM enrollments WHERE subject_id=? AND student_id=? AND state="active"',(a['subject_id'],actor)):raise Denied('Student is not enrolled.')
  existing=self._one('SELECT * FROM submissions WHERE assignment_id=? AND student_id=?',(assignment_id,actor))
  if existing and existing['state']=='submitted':raise Conflict('Final submission is immutable. Ask the educator to reopen it before submitting a revision.')
  if not str(body).strip() and not file_path:raise EducationError('Submission content is required.')
  submitted_time=datetime.now(timezone.utc);due=parse_time(a['due_at']);late=submitted_time>due;late_seconds=max(0,int((submitted_time-due).total_seconds()))
  policy=str(a['late_policy'] or 'reject').lower();penalty=0.0
  if final and late:
   if policy in {'reject','manual_approval'}:raise Conflict('The assignment deadline has passed. Educator approval or an extended deadline is required.')
   if policy=='allow_with_penalty':penalty=10.0
  metadata={'file_path':'','file_name':'','mime_type':'','size_bytes':0,'sha256':''}
  if file_path:metadata=self._prepare_submission_file(a['institution_id'],assignment_id,actor,file_path,json.loads(a['allowed_types'] or '[]'))
  t=now();sid=existing['id'] if existing else ident('subm');state='submitted' if final else 'draft'
  prior_version=self._one('SELECT COALESCE(MAX(version),0) n FROM submission_versions WHERE submission_id=?',(sid,)) if existing else {'n':0};version=int(prior_version['n'])+1;final_version=(int(existing.get('final_version',0)) if existing else 0)+(1 if final else 0)
  with self.db.connection() as db:
   if existing:
    db.execute('''UPDATE submissions SET body=?,file_path=?,submitted_at=?,state=?,late=?,late_seconds=?,penalty_percent=?,file_name=?,mime_type=?,size_bytes=?,sha256=?,final_version=?,updated_at=? WHERE id=?''',(str(body),metadata['file_path'],t if final else None,state,int(late and final),late_seconds if final else 0,penalty,metadata['file_name'],metadata['mime_type'],metadata['size_bytes'],metadata['sha256'],final_version,t,sid))
   else:
    db.execute('''INSERT INTO submissions(id,institution_id,assignment_id,student_id,body,file_path,submitted_at,state,late,late_seconds,penalty_percent,file_name,mime_type,size_bytes,sha256,final_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(sid,a['institution_id'],assignment_id,actor,str(body),metadata['file_path'],t if final else None,state,int(late and final),late_seconds if final else 0,penalty,metadata['file_name'],metadata['mime_type'],metadata['size_bytes'],metadata['sha256'],final_version,t,t))
   db.execute('INSERT INTO submission_versions VALUES(?,?,?,?,?,?,?,?,?)',(ident('subver'),sid,version,actor,str(body),metadata['file_path'],metadata['sha256'],state,t))
  self._audit(actor,'assignment_submitted' if final else 'assignment_draft_saved','submission',sid,a['institution_id'],{'version':version,'late':bool(late and final),'penalty_percent':penalty})
  return self._one('SELECT * FROM submissions WHERE id=?',(sid,))
 def reopen_submission(self,actor,submission_id,reason):
  s=self._one('SELECT s.*,a.subject_id FROM submissions s JOIN assignments a ON a.id=s.assignment_id WHERE s.id=?',(submission_id,))
  if not s:raise Missing('Submission not found.')
  self._teacher(actor,s['institution_id'],s['subject_id'])
  if s['state']!='submitted':raise Conflict('Only a final submission can be reopened.')
  if not str(reason).strip():raise EducationError('A reopening reason is required.')
  t=now()
  with self.db.connection() as db:db.execute("UPDATE submissions SET state='draft',submitted_at=NULL,updated_at=? WHERE id=?",(t,submission_id))
  self._audit(actor,'submission_reopened','submission',submission_id,s['institution_id'],{'reason':str(reason)[:1000]})
  return self._one('SELECT * FROM submissions WHERE id=?',(submission_id,))
 def grade_submission(self,actor,submission_id,marks,feedback='',reason=''):
  s=self._one('SELECT s.*,a.subject_id,a.max_marks FROM submissions s JOIN assignments a ON a.id=s.assignment_id WHERE s.id=?',(submission_id,))
  if not s:raise Missing('Submission not found.')
  self._teacher(actor,s['institution_id'],s['subject_id'])
  if s['state']!='submitted':raise Conflict('Only a final submitted assignment can be graded.')
  if not 0<=float(marks)<=float(s['max_marks']):raise EducationError('Marks out of range.')
  existing=self._one('SELECT * FROM grades WHERE submission_id=?',(submission_id,));t=now()
  with self.db.connection() as db:
   if existing:
    if not str(reason).strip():raise Conflict('A reason is required when changing a released grade.')
    db.execute('INSERT INTO grade_revisions VALUES(?,?,?,?,?,?,?,?,?,?)',(ident('grev'),existing['id'],submission_id,actor,float(existing['marks']),float(marks),existing['feedback'],str(feedback),str(reason)[:1000],t))
    db.execute('UPDATE grades SET grader_id=?,marks=?,feedback=?,updated_at=? WHERE id=?',(actor,float(marks),str(feedback),t,existing['id']))
    gid=existing['id']
   else:
    gid=ident('grade');db.execute('INSERT INTO grades VALUES(?,?,?,?,?,?,?,?,?)',(gid,s['institution_id'],submission_id,actor,float(marks),str(feedback),'released',t,t))
  self._audit(actor,'submission_grade_revised' if existing else 'submission_graded','submission',submission_id,s['institution_id'],{'marks':float(marks),'reason':str(reason)[:1000]})
  return self._one('SELECT * FROM grades WHERE id=?',(gid,))
 def create_circular(self,actor,institution_id,number,title,content,audience,priority='normal'):
  self._require(actor,institution_id,ADMIN)
  if not str(number).strip() or not str(title).strip() or not str(content).strip():raise EducationError('Circular number, title and content are required.')
  if not isinstance(audience,(list,dict)) or not audience:raise EducationError('Circular audience is required.')
  if str(priority) not in {'low','normal','high','urgent'}:raise EducationError('Invalid circular priority.')
  cid=ident('circ');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO circulars VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(cid,institution_id,actor,str(number).strip(),str(title).strip(),str(content),json.dumps(audience,sort_keys=True),priority,'draft','',None,t,t))
  return self._one('SELECT * FROM circulars WHERE id=?',(cid,))
 def publish_circular(self,actor,circular_id):
  c=self._one('SELECT * FROM circulars WHERE id=?',(circular_id,))
  if not c:raise Missing('Circular not found.')
  self._require(actor,c['institution_id'],ADMIN);t=now()
  with self.db.connection() as db:db.execute('UPDATE circulars SET state="published",approved_by=?,published_at=?,updated_at=? WHERE id=?',(actor,t,t,circular_id))
  self._audit(actor,'circular_published','circular',circular_id,c['institution_id']);return self._one('SELECT * FROM circulars WHERE id=?',(circular_id,))
 def _circular_allowed(self,actor,circular):
  roles={x['role'] for x in self._require(actor,circular['institution_id'])};audience=json.loads(circular['audience_json'] or '[]')
  aliases={'students':STUDENT,'student':STUDENT,'teachers':TEACHER,'teacher':TEACHER,'staff':TEACHER,'parents':{'parent_guardian'},'guardians':{'parent_guardian'},'admins':ADMIN,'administrators':ADMIN,'all':ROLES,'institution':ROLES}
  if isinstance(audience,list):
   allowed=set()
   for item in audience:allowed|=aliases.get(str(item).lower(),{str(item)})
   return bool(roles&allowed) or actor in {str(item) for item in audience}
  if isinstance(audience,dict):
   users={str(x) for x in audience.get('user_ids',[])};requested_roles=set()
   for item in audience.get('roles',[]):requested_roles|=aliases.get(str(item).lower(),{str(item)})
   return actor in users or bool(roles&requested_roles)
  return False
 def list_circulars(self,actor,institution_id,limit=100):
  self._require(actor,institution_id);rows=self._all('SELECT * FROM circulars WHERE institution_id=? AND state="published" ORDER BY published_at DESC LIMIT ?',(institution_id,max(1,min(int(limit),500))))
  return [item for item in rows if self._circular_allowed(actor,item)]
 def acknowledge_circular(self,actor,circular_id):
  c=self._one('SELECT * FROM circulars WHERE id=? AND state="published"',(circular_id,))
  if not c:raise Missing('Published circular not found.')
  if not self._circular_allowed(actor,c):raise Denied('This circular is not addressed to your role or account.')
  t=now()
  with self.db.connection() as db:db.execute('INSERT OR IGNORE INTO circular_acknowledgements VALUES(?,?,?,?)',(ident('ack'),circular_id,actor,t))
  return {'circular_id':circular_id,'user_id':actor,'acknowledged_at':t}
 # Science Pulse: caller-provided real metadata only; adapters must identify source.
 def _source_manager(self,actor,institution_id=None):
  memberships=self._all('SELECT institution_id,role FROM memberships WHERE user_id=? AND state="active"',(actor,))
  admin_institutions=sorted({m['institution_id'] for m in memberships if m['role'] in ADMIN})
  if institution_id:
   if institution_id not in admin_institutions:raise Denied('Publication-source management requires an administrator in this institution.')
   return institution_id
  if len(admin_institutions)!=1:raise Denied('Specify the institution for publication-source management.')
  return admin_institutions[0]
 def add_pulse_source(self,actor,name,source_type,base_url,configured=False,institution_id=None):
  institution_id=self._source_manager(actor,institution_id)
  if source_type not in {'publication_api','rss','news_api'}:raise EducationError('Unsupported Science Pulse source type.')
  from .adapters import _validate_url
  try:base_url=_validate_url(str(base_url).strip())
  except AdapterError as exc:raise EducationError(str(exc)) from exc
  sid=ident('psrc');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO pulse_sources(id,institution_id,name,source_type,base_url,configured,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(sid,institution_id,str(name).strip(),source_type,base_url,int(configured),'active',t,t))
  self._audit(actor,'pulse_source_added','pulse_source',sid,institution_id,{'source_type':source_type,'configured':bool(configured)})
  return self._one('SELECT * FROM pulse_sources WHERE id=?',(sid,))
 def sync_pulse_source(self,actor,source_id,query='',limit=20):
  src=self._one('SELECT * FROM pulse_sources WHERE id=? AND state="active"',(source_id,))
  if not src:raise Missing('Source not found.')
  self._source_manager(actor,src.get('institution_id') or None)
  jid=ident('sync');t=now()
  if not src['configured']:
   with self.db.connection() as db:db.execute('INSERT INTO source_sync_jobs VALUES(?,?,?,?,?,?,?)',(jid,source_id,'configuration_required',0,'Source is registered but not enabled.',t,t))
   return self._one('SELECT * FROM source_sync_jobs WHERE id=?',(jid,))
  with self.db.connection() as db:db.execute('INSERT INTO source_sync_jobs VALUES(?,?,?,?,?,?,?)',(jid,source_id,'running',0,'',t,t))
  received=0
  try:
   if src['source_type']=='publication_api':
    records=CrossrefAdapter(src['base_url']).fetch(query or 'biotechnology',limit)
    for metadata in records:self.ingest_publication(source_id,metadata);received+=1
   elif src['source_type'] in {'rss','news_api'}:
    records=RssNewsAdapter(src['base_url']).fetch(limit)
    for item in records:self.ingest_news(source_id,**item);received+=1
   else:raise AdapterError('Unsupported source type.')
   state,error='completed',''
  except AdapterError as exc:state,error='external_service_unavailable',str(exc)[:1000]
  with self.db.connection() as db:db.execute('UPDATE source_sync_jobs SET state=?,items_received=?,error=?,updated_at=? WHERE id=?',(state,received,error,now(),jid))
  self._audit(actor,'pulse_source_synced','pulse_source',source_id,src.get('institution_id',''),{'state':state,'items_received':received})
  return self._one('SELECT * FROM source_sync_jobs WHERE id=?',(jid,))
 def ingest_publication(self,source_id,metadata):
  src=self._one('SELECT * FROM pulse_sources WHERE id=? AND state="active"',(source_id,))
  if not src:raise Missing('Source not found.')
  doi=str(metadata.get('doi','')).strip().lower();pmid=str(metadata.get('pmid','')).strip();title=str(metadata.get('title','')).strip();url=str(metadata.get('source_url','')).strip()
  if not title or not url or (not doi and not pmid):raise EducationError('Title, source URL and DOI or PMID are required.')
  prior=self._one('SELECT * FROM publications WHERE (doi<>"" AND doi=?) OR (pmid<>"" AND pmid=?)',(doi,pmid))
  if prior:return prior
  pid=ident('pub');t=now();kind='preprint' if metadata.get('preprint') else 'journal';retraction='retracted' if metadata.get('retracted') else ('corrected' if metadata.get('corrected') else 'none')
  with self.db.connection() as db:db.execute('INSERT INTO publications VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(pid,source_id,doi,pmid,title,str(metadata.get('abstract_excerpt',''))[:2000],json.dumps(metadata.get('authors',[])),url,str(metadata.get('published_at','')),kind,retraction,json.dumps(metadata),t,t))
  self._deliver_alerts(pid,title,'publication');return self._one('SELECT * FROM publications WHERE id=?',(pid,))
 def ingest_news(self,source_id,external_id,title,summary_excerpt,source_url,published_at,topics=None):
  if not title or not source_url:raise EducationError('News title and original source link are required.')
  nid=ident('news');t=now()
  with self.db.connection() as db:db.execute('INSERT OR IGNORE INTO news_items VALUES(?,?,?,?,?,?,?,?,?,?)',(nid,source_id,external_id,title,summary_excerpt[:1000],source_url,published_at,json.dumps(topics or []),t,t))
  item=self._one('SELECT * FROM news_items WHERE source_id=? AND external_id=?',(source_id,external_id));self._deliver_alerts(item['id'],title,'news');return item
 def create_alert(self,user_id,query,resource_type='all'):
  aid=ident('alert');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?)',(aid,user_id,query,resource_type,'active',t,t))
  return self._one('SELECT * FROM alerts WHERE id=?',(aid,))
 def _deliver_alerts(self,resource_id,title,kind):
  for a in self._all('SELECT * FROM alerts WHERE state="active" AND resource_type IN ("all",?)',(kind,)):
   if a['query'].lower() in title.lower():
    with self.db.connection() as db:db.execute('INSERT OR IGNORE INTO alert_deliveries VALUES(?,?,?,?,?)',(ident('ald'),a['id'],resource_id,now(),'delivered'))
 def save_research(self,user_id,resource_type,resource_id):
  sid=ident('save')
  with self.db.connection() as db:db.execute('INSERT OR IGNORE INTO saved_research VALUES(?,?,?,?,?)',(sid,user_id,resource_type,resource_id,now()))
  return self._one('SELECT * FROM saved_research WHERE user_id=? AND resource_type=? AND resource_id=?',(user_id,resource_type,resource_id))
 def pulse_search(self,query):
  q=f'%{query.strip()}%';return {'publications':self._all('SELECT * FROM publications WHERE title LIKE ? COLLATE NOCASE ORDER BY published_at DESC',(q,)),'news':self._all('SELECT * FROM news_items WHERE title LIKE ? COLLATE NOCASE ORDER BY published_at DESC',(q,))}
 def grounded_summary(self,user_id,resource_type,resource_id,summary,citations):
  if not citations:raise EducationError('Grounded AI summary requires source citations.')
  sid=ident('ais');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO ai_summaries VALUES(?,?,?,?,?,?,?,?)',(sid,user_id,resource_type,resource_id,summary,json.dumps(citations),'AI-generated',t))
  return self._one('SELECT * FROM ai_summaries WHERE id=?',(sid,))
 # Academy
 def create_educator(self,actor,institution_id,bio='',verified=False):
  self._require(actor,institution_id,TEACHER);existing=self._one('SELECT * FROM educator_profiles WHERE institution_id=? AND user_id=?',(institution_id,actor));eid=existing['id'] if existing else ident('edu');t=now()
  with self.db.connection() as db:
   if existing:db.execute("UPDATE educator_profiles SET bio=?,state='active',updated_at=? WHERE id=?",(str(bio),t,eid))
   else:db.execute('''INSERT INTO educator_profiles(id,institution_id,user_id,bio,verified,verification_state,verified_by,verified_at,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(eid,institution_id,actor,str(bio),0,'unverified','',None,'active',t,t))
  if verified:self._audit(actor,'educator_self_verification_ignored','educator_profile',eid,institution_id)
  return self._one('SELECT * FROM educator_profiles WHERE id=?',(eid,))
 def verify_educator(self,actor,institution_id,user_id,approve=True):
  self._require(actor,institution_id,ADMIN);profile=self._one('SELECT * FROM educator_profiles WHERE institution_id=? AND user_id=?',(institution_id,user_id))
  if not profile:raise Missing('Educator profile not found.')
  t=now();state='verified' if approve else 'rejected'
  with self.db.connection() as db:db.execute('UPDATE educator_profiles SET verified=?,verification_state=?,verified_by=?,verified_at=?,updated_at=? WHERE id=?',(int(approve),state,actor,t,t,profile['id']))
  self._audit(actor,'educator_verified' if approve else 'educator_verification_rejected','educator_profile',profile['id'],institution_id,{'user_id':user_id})
  return self._one('SELECT * FROM educator_profiles WHERE id=?',(profile['id'],))
 def create_course(self,actor,institution_id,title,description='',difficulty='beginner',publish=False,passing_score=60,minimum_watch_ratio=0.85,require_all_quizzes=True):
  self._require(actor,institution_id,TEACHER)
  if not str(title).strip():raise EducationError('Course title is required.')
  if difficulty not in {'beginner','intermediate','advanced'}:raise EducationError('Unsupported course difficulty.')
  if not 0<=float(passing_score)<=100:raise EducationError('Passing score must be between 0 and 100.')
  if not 0.5<=float(minimum_watch_ratio)<=1:raise EducationError('Minimum watch ratio must be between 0.5 and 1.0.')
  cid=ident('course');t=now()
  with self.db.connection() as db:db.execute('''INSERT INTO courses(id,institution_id,educator_id,title,description,difficulty,passing_score,minimum_watch_ratio,require_all_quizzes,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(cid,institution_id,actor,str(title).strip(),str(description),difficulty,float(passing_score),float(minimum_watch_ratio),int(require_all_quizzes),'published' if publish else 'draft',t,t))
  return self._one('SELECT * FROM courses WHERE id=?',(cid,))
 def confirm_rights(self,actor,institution_id,owner_name,license_name,third_party_declaration='',download_allowed=False):
  self._require(actor,institution_id,TEACHER)
  if not str(owner_name).strip() or not str(license_name).strip():raise EducationError('Rights owner and license are required.')
  rid=ident('rights');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO content_rights VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,institution_id,str(owner_name).strip(),actor,str(license_name).strip(),1,str(third_party_declaration),int(download_allowed),t,t))
  return self._one('SELECT * FROM content_rights WHERE id=?',(rid,))
 def upload_lecture(self,actor,course_id,title,source_path:Path,rights_id,description=''):
  c=self._one('SELECT * FROM courses WHERE id=?',(course_id,))
  if not c or c['educator_id']!=actor:raise Denied('Only the course educator may upload lectures.')
  rights=self._one('SELECT * FROM content_rights WHERE id=? AND educator_id=? AND institution_id=? AND rights_confirmed=1',(rights_id,actor,c['institution_id']))
  if not rights:raise Denied('Content-rights confirmation is required.')
  src=Path(source_path).expanduser().resolve();suffix=src.suffix.lower();mime=mimetypes.guess_type(src.name)[0] or ''
  if not src.is_file() or suffix not in ALLOWED_VIDEO_EXTENSIONS or not mime.startswith('video/') or not _looks_like_video(src):raise EducationError('Video content does not match a supported media container.')
  if src.stat().st_size>8*1024**3:raise EducationError('Lecture video exceeds the 8 GiB limit.')
  lid=ident('lec');folder=self.storage/c['institution_id']/'lectures';folder.mkdir(parents=True,exist_ok=True);dest=folder/f'{lid}{suffix}';h=hashlib.sha256()
  with src.open('rb') as inp,dest.open('wb') as out:
   while chunk:=inp.read(1024*1024):h.update(chunk);out.write(chunk)
  duration=self._video_duration(dest);processing='original_ready' if duration>0 else ('metadata_probe_required' if ffmpeg_executable() else 'processing_dependency_required');state='published' if duration>0 else 'draft';t=now()
  with self.db.connection() as db:db.execute('''INSERT INTO lectures(id,institution_id,course_id,educator_id,title,description,video_path,sha256,size_bytes,mime_type,duration_seconds,processing_state,rights_id,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(lid,c['institution_id'],course_id,actor,str(title).strip(),str(description),str(dest),h.hexdigest(),dest.stat().st_size,mime,duration,processing,rights_id,state,t,t))
  self._audit(actor,'lecture_uploaded','lecture',lid,c['institution_id'],{'duration_seconds':duration,'processing_state':processing})
  return self._one('SELECT * FROM lectures WHERE id=?',(lid,))
 def enroll_course(self,actor,course_id):
  c=self._one('SELECT * FROM courses WHERE id=? AND state="published"',(course_id,))
  if not c:raise Missing('Published course not found.')
  roles={x['role'] for x in self._require(actor,c['institution_id'])}
  if not roles&STUDENT:raise Denied('Only an enrolled student role may join a course.')
  eid=ident('aen');t=now()
  with self.db.connection() as db:db.execute('INSERT OR IGNORE INTO academy_enrollments VALUES(?,?,?,?,?,?,?)',(eid,c['institution_id'],course_id,actor,'active',t,t))
  return self._one('SELECT * FROM academy_enrollments WHERE course_id=? AND student_id=?',(course_id,actor))
 def update_watch(self,actor,lecture_id,seconds,completed=False):
  l=self._one('SELECT l.*,c.minimum_watch_ratio FROM lectures l JOIN courses c ON c.id=l.course_id WHERE l.id=? AND l.state="published"',(lecture_id,))
  if not l or not self._one('SELECT 1 ok FROM academy_enrollments WHERE course_id=? AND student_id=? AND state="active"',(l['course_id'],actor)):raise Denied('Lecture access denied.')
  duration=float(l.get('duration_seconds') or 0)
  if duration<=0:raise Conflict('Lecture duration has not been verified; progress completion is unavailable.')
  reported=max(0.0,min(float(seconds),duration));previous=self._one('SELECT * FROM watch_progress WHERE lecture_id=? AND user_id=?',(lecture_id,actor));previous_seconds=float(previous['seconds']) if previous else 0.0
  if reported>previous_seconds+300:reported=previous_seconds+300
  ratio=reported/duration;derived_complete=ratio>=float(l.get('minimum_watch_ratio') or 0.85);t=now();pid=previous['id'] if previous else ident('watch')
  with self.db.connection() as db:
   db.execute('''INSERT INTO watch_progress(id,lecture_id,user_id,seconds,completed,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(lecture_id,user_id) DO UPDATE SET seconds=MAX(seconds,excluded.seconds),completed=MAX(completed,excluded.completed),updated_at=excluded.updated_at''',(pid,lecture_id,actor,reported,int(derived_complete),t))
   db.execute('INSERT INTO watch_events VALUES(?,?,?,?,?,?)',(ident('we'),lecture_id,actor,'complete' if derived_complete else 'progress',reported,t))
  if completed and not derived_complete:self._audit(actor,'client_completion_claim_rejected','lecture',lecture_id,l['institution_id'],{'reported_seconds':float(seconds),'accepted_seconds':reported,'duration_seconds':duration})
  return self._one('SELECT * FROM watch_progress WHERE lecture_id=? AND user_id=?',(lecture_id,actor))
 def create_quiz(self,actor,course_id,title,questions,publish=True,passing_score=None):
  c=self._one('SELECT * FROM courses WHERE id=?',(course_id,))
  if not c or c['educator_id']!=actor:raise Denied('Course educator permission required.')
  if not isinstance(questions,list) or not questions:raise EducationError('Quiz requires at least one question.')
  for question in questions:
   if not isinstance(question,dict) or not str(question.get('prompt','')).strip() or 'answer' not in question:raise EducationError('Every quiz question requires a prompt and answer key.')
  threshold=float(c['passing_score'] if passing_score is None else passing_score)
  if not 0<=threshold<=100:raise EducationError('Passing score must be between 0 and 100.')
  qid=ident('quiz');t=now()
  with self.db.connection() as db:db.execute('''INSERT INTO quizzes(id,course_id,creator_id,title,questions_json,passing_score,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)''',(qid,course_id,actor,str(title).strip(),json.dumps(questions),threshold,'published' if publish else 'draft',t,t))
  return self._one('SELECT * FROM quizzes WHERE id=?',(qid,))
 def attempt_quiz(self,actor,quiz_id,answers):
  q=self._one('SELECT q.*,c.institution_id FROM quizzes q JOIN courses c ON c.id=q.course_id WHERE q.id=? AND q.state="published"',(quiz_id,))
  if not q or not self._one('SELECT 1 ok FROM academy_enrollments WHERE course_id=? AND student_id=? AND state="active"',(q['course_id'],actor)):raise Denied('Quiz access denied.')
  questions=json.loads(q['questions_json']);correct=sum(1 for i,x in enumerate(questions) if i<len(answers) and answers[i]==x.get('answer'));score=100*correct/max(len(questions),1);aid=ident('qa')
  with self.db.connection() as db:db.execute('INSERT INTO quiz_attempts VALUES(?,?,?,?,?,?,?)',(aid,quiz_id,actor,json.dumps(answers),score,int(score>=float(q.get('passing_score') or 60)),now()))
  return self._one('SELECT * FROM quiz_attempts WHERE id=?',(aid,))
 def issue_certificate(self,actor,course_id,student_id):
  c=self._one('SELECT * FROM courses WHERE id=?',(course_id,))
  if not c or c['educator_id']!=actor:raise Denied('Course educator permission required.')
  if not self._one('SELECT 1 ok FROM academy_enrollments WHERE course_id=? AND student_id=? AND state="active"',(course_id,student_id)):raise Denied('Student is not actively enrolled in this course.')
  lectures=self._all('SELECT id,title,duration_seconds FROM lectures WHERE course_id=? AND state="published" ORDER BY id',(course_id,));progress=self._all('SELECT w.lecture_id,w.seconds,w.completed FROM watch_progress w JOIN lectures l ON l.id=w.lecture_id WHERE l.course_id=? AND w.user_id=?',(course_id,student_id));progress_by={x['lecture_id']:x for x in progress}
  quizzes=self._all('SELECT id,title,passing_score FROM quizzes WHERE course_id=? AND state="published" ORDER BY id',(course_id,));quiz_evidence=[]
  for quiz in quizzes:
   best=self._one('SELECT MAX(score) score,MAX(passed) passed FROM quiz_attempts WHERE quiz_id=? AND student_id=?',(quiz['id'],student_id)) or {'score':None,'passed':0}
   quiz_evidence.append({'quiz_id':quiz['id'],'title':quiz['title'],'best_score':best['score'],'passed':bool(best['passed'])})
  missing_lectures=[item['id'] for item in lectures if not progress_by.get(item['id'],{}).get('completed')]
  missing_quizzes=[item['quiz_id'] for item in quiz_evidence if not item['passed']]
  if not lectures or missing_lectures or not quizzes or (bool(c.get('require_all_quizzes',1)) and missing_quizzes):raise Conflict('Certificate completion rules are not met for every required lecture and quiz.')
  existing=self._one('SELECT * FROM certificates WHERE course_id=? AND student_id=?',(course_id,student_id))
  if existing and not existing['revoked']:return existing
  t=now();code=uuid.uuid4().hex;evidence={'course_id':course_id,'student_id':student_id,'issued_at':t,'lectures':[{'lecture_id':item['id'],'duration_seconds':item['duration_seconds'],'reported_seconds':progress_by[item['id']]['seconds']} for item in lectures],'quizzes':quiz_evidence};canonical=json.dumps(evidence,sort_keys=True,separators=(',',':'));digest=hashlib.sha256(canonical.encode()).hexdigest();signature=self._signature(digest);cid=existing['id'] if existing else ident('cert')
  with self.db.connection() as db:
   if existing:db.execute('UPDATE certificates SET issued_at=?,revoked=0,verification_code=?,evidence_json=?,evidence_sha256=?,signature=?,created_at=? WHERE id=?',(t,code,canonical,digest,signature,t,cid))
   else:db.execute('''INSERT INTO certificates(id,institution_id,course_id,student_id,issued_at,revoked,verification_code,evidence_json,evidence_sha256,signature,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(cid,c['institution_id'],course_id,student_id,t,0,code,canonical,digest,signature,t))
  self._audit(actor,'certificate_issued','certificate',cid,c['institution_id'],{'student_id':student_id,'evidence_sha256':digest})
  return self._one('SELECT * FROM certificates WHERE id=?',(cid,))
 def verify_certificate(self,verification_code):
  cert=self._one('SELECT * FROM certificates WHERE verification_code=?',(verification_code,))
  if not cert:return {'valid':False,'reason':'not_found'}
  digest=hashlib.sha256((cert.get('evidence_json') or '{}').encode()).hexdigest();valid=not bool(cert['revoked']) and hmac.compare_digest(digest,cert.get('evidence_sha256') or '') and hmac.compare_digest(self._signature(digest),cert.get('signature') or '')
  return {'valid':valid,'revoked':bool(cert['revoked']),'certificate_id':cert['id'],'course_id':cert['course_id'],'student_id':cert['student_id'],'issued_at':cert['issued_at'],'reason':'' if valid else 'signature_or_state_invalid'}
 def report_content(self,actor,target_type,target_id,reason):
  rid=ident('report');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO content_reports VALUES(?,?,?,?,?,?,?,?)',(rid,actor,target_type,target_id,reason,'open',t,t))
  return self._one('SELECT * FROM content_reports WHERE id=?',(rid,))
 def create_examination(self,actor,institution_id,subject_id,title,max_marks,starts_at,ends_at):
  self._teacher(actor,institution_id,subject_id)
  if ends_at<=starts_at:raise EducationError('Exam end must follow start.')
  eid=ident('exam');t=now()
  with self.db.connection() as db:db.execute('INSERT INTO examinations VALUES(?,?,?,?,?,?,?,?,?,?,?)',(eid,institution_id,subject_id,actor,title,float(max_marks),starts_at,ends_at,'draft',t,t))
  return self._one('SELECT * FROM examinations WHERE id=?',(eid,))
 def set_result(self,actor,examination_id,student_id,marks,grade='',reason=''):
  e=self._one('SELECT * FROM examinations WHERE id=?',(examination_id,))
  if not e:raise Missing('Examination not found.')
  self._teacher(actor,e['institution_id'],e['subject_id'])
  if not self._one('SELECT 1 ok FROM enrollments WHERE subject_id=? AND student_id=? AND state="active"',(e['subject_id'],student_id)):raise Denied('Student is not enrolled in the examination subject.')
  if not 0<=float(marks)<=float(e['max_marks']):raise EducationError('Marks out of range.')
  existing=self._one('SELECT * FROM results WHERE examination_id=? AND student_id=?',(examination_id,student_id));t=now()
  if existing and existing['locked']:raise Conflict('Published result is locked. An examination administrator must explicitly unlock it with a reason.')
  if existing and existing['published'] and not str(reason).strip():raise Conflict('A revision reason is required for a published result.')
  with self.db.connection() as db:
   if existing:
    db.execute('INSERT INTO result_revisions VALUES(?,?,?,?,?,?,?,?,?)',(ident('rrev'),existing['id'],actor,float(existing['marks']),float(marks),existing['grade'],str(grade),str(reason or 'pre-publication correction')[:1000],t))
    db.execute('UPDATE results SET marks=?,grade=?,updated_at=? WHERE id=?',(float(marks),str(grade),t,existing['id']));rid=existing['id']
   else:
    rid=ident('result');db.execute('INSERT INTO results VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,e['institution_id'],examination_id,student_id,float(marks),str(grade),0,0,t,t))
  self._audit(actor,'result_revised' if existing else 'result_recorded','result',rid,e['institution_id'],{'marks':float(marks),'reason':str(reason)[:1000]})
  return self._one('SELECT * FROM results WHERE id=?',(rid,))
 def unlock_result(self,actor,result_id,reason):
  result=self._one('SELECT * FROM results WHERE id=?',(result_id,))
  if not result:raise Missing('Result not found.')
  self._require(actor,result['institution_id'],ADMIN|{'examination_controller'})
  if not result['locked']:raise Conflict('Result is already unlocked.')
  if not str(reason).strip():raise EducationError('An unlock reason is required.')
  t=now()
  with self.db.connection() as db:db.execute('UPDATE results SET locked=0,updated_at=? WHERE id=?',(t,result_id))
  self._audit(actor,'result_unlocked','result',result_id,result['institution_id'],{'reason':str(reason)[:1000]})
  return self._one('SELECT * FROM results WHERE id=?',(result_id,))
 def publish_results(self,actor,examination_id):
  e=self._one('SELECT * FROM examinations WHERE id=?',(examination_id,))
  if not e:raise Missing('Examination not found.')
  self._require(actor,e['institution_id'],ADMIN|{'examination_controller'});t=now()
  with self.db.connection() as db:db.execute('UPDATE results SET published=1,locked=1,updated_at=? WHERE examination_id=?',(t,examination_id));db.execute('UPDATE examinations SET state="published",updated_at=? WHERE id=?',(t,examination_id))
  self._audit(actor,'results_published','examination',examination_id,e['institution_id']);return {'examination_id':examination_id,'published':True}
 def view_results(self,actor,institution_id,student_id):
  self._require(actor,institution_id)
  if actor!=student_id and not self._guardian_can(actor,institution_id,student_id) and not any(x['role'] in TEACHER for x in self.membership(actor,institution_id)):raise Denied('Result access denied.')
  return self._all('SELECT r.*,e.title,e.max_marks FROM results r JOIN examinations e ON e.id=r.examination_id WHERE r.institution_id=? AND r.student_id=? AND r.published=1',(institution_id,student_id))
 def unified_search(self,actor,institution_id,query):
  self._require(actor,institution_id);q=f'%{query.strip()}%'
  return {'subjects':self._all('SELECT id,code,name FROM subjects WHERE institution_id=? AND name LIKE ? COLLATE NOCASE',(institution_id,q)),'materials':self._all('SELECT id,title,subject_id FROM materials WHERE institution_id=? AND title LIKE ? COLLATE NOCASE',(institution_id,q)),'courses':self._all('SELECT id,title,difficulty FROM courses WHERE institution_id=? AND state="published" AND title LIKE ? COLLATE NOCASE',(institution_id,q)),**self.pulse_search(query)}
 def dashboard(self,actor,institution_id):
  ms=self._require(actor,institution_id);roles={x['role'] for x in ms};d={'roles':sorted(roles),'configuration':{'calls':'CONFIGURATION REQUIRED','publication_sources':'CONFIGURATION REQUIRED','video_processing':'FFMPEG DETECTED; WORKER QUALIFICATION REQUIRED' if ffmpeg_executable() else 'PROCESSING DEPENDENCY REQUIRED'}}
  if roles&STUDENT:d.update({'pending_assignments':self._one('SELECT COUNT(*) n FROM assignments a JOIN enrollments e ON e.subject_id=a.subject_id LEFT JOIN submissions s ON s.assignment_id=a.id AND s.student_id=? WHERE e.student_id=? AND a.state="published" AND s.id IS NULL',(actor,actor))['n'],'attendance_records':len(self.student_attendance(actor,institution_id,actor))})
  if roles&TEACHER:d.update({'assigned_subjects':self._one('SELECT COUNT(*) n FROM teacher_assignments WHERE institution_id=? AND teacher_id=? AND state="active"',(institution_id,actor))['n'],'pending_grading':self._one('SELECT COUNT(*) n FROM submissions s JOIN assignments a ON a.id=s.assignment_id JOIN teacher_assignments t ON t.subject_id=a.subject_id WHERE t.teacher_id=? AND s.state="submitted" AND NOT EXISTS(SELECT 1 FROM grades g WHERE g.submission_id=s.id)',(actor,))['n']})
  if roles&ADMIN:d.update({'students':self._one('SELECT COUNT(DISTINCT user_id) n FROM memberships WHERE institution_id=? AND role IN ("school_student","college_student","university_student")',(institution_id,))['n'],'faculty':self._one('SELECT COUNT(DISTINCT user_id) n FROM memberships WHERE institution_id=? AND role NOT IN ("school_student","college_student","university_student","parent_guardian")',(institution_id,))['n']})
  return d








class UnifiedEducationPlatform(EducationPlatform):
    """Backward-compatible constructor and legacy role helpers.

    New code should use :class:`EducationPlatform` plus ``EducationOS``. Unknown identities are
    guests, never implicit students, so the compatibility surface does not bypass enrolment.
    """

    _CANONICAL_ROLE = {
        "school_student": "student",
        "college_student": "student",
        "university_student": "student",
        "subject_teacher": "teacher",
        "class_teacher": "teacher",
        "lecturer": "instructor",
        "assistant_professor": "instructor",
        "professor": "instructor",
        "content_moderator": "reviewer",
        "examination_controller": "examiner",
        "department_head": "department_administrator",
        "institution_administrator": "institution_administrator",
        "platform_administrator": "platform_administrator",
        "parent_guardian": "parent_guardian",
    }
    _LEGACY_PERMISSIONS = {
        "platform_admin": {"*"},
        "platform_administrator": {"*"},
        "institution_admin": {"*"},
        "institution_administrator": {"*"},
        "teacher": {"view_course", "manage_classroom", "create_assignment", "grade_submission", "message"},
        "student": {"view_course", "submit_assignment", "attempt_exam", "message"},
        "parent_guardian": {"view_linked_student", "message"},
        "guest": {"view_public"},
    }

    def __init__(self, path: Path, storage: Path | None = None):
        database = Path(path)
        super().__init__(database, storage or database.parent / "education-media")

    def get_user_context(self, user_id: str, institution_id: str | None = None) -> dict[str, Any]:
        if institution_id:
            memberships = self.membership(user_id, institution_id)
        else:
            memberships = self._all(
                "SELECT * FROM memberships WHERE user_id=? AND state='active' ORDER BY created_at",
                (user_id,),
            )
        roles = [self._CANONICAL_ROLE.get(str(item["role"]), str(item["role"])) for item in memberships]
        role = roles[0] if roles else "guest"
        return {
            "user_id": user_id,
            "institution_id": institution_id or (str(memberships[0]["institution_id"]) if memberships else ""),
            "role": role,
            "roles": roles,
            "authenticated": bool(memberships),
        }

    @classmethod
    def check_permission(cls, role: str, permission: str) -> bool:
        normalized_role = str(role).strip().lower()
        normalized_permission = str(permission).strip().lower()
        allowed = cls._LEGACY_PERMISSIONS.get(normalized_role, set())
        return "*" in allowed or normalized_permission in allowed
