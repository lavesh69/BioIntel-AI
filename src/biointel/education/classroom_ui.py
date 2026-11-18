from __future__ import annotations
from datetime import date,datetime,time,timezone
from pathlib import Path
from typing import Any,Callable
from ._streamlit_compat import st
from .platform import ADMIN,STUDENT,TEACHER
from .education_suite import EducationSuiteService
from .education_suite_ui import render_classroom_suite
from biointel.ui.frontend_v10 import empty_state
Run=Callable[[Callable[[],Any]],Any]

def _all(p,sql,args=()):return p._all(sql,args)
def _roles(p,a,i):return {x['role'] for x in p.membership(a,i)}
def _admin(r):return bool(r&ADMIN)
def _teacher(r):return bool(r&TEACHER)
def _student(r):return bool(r&STUDENT)
def _options(s):return {x['id']:f"{x['code']} · {x['name']}" for x in s}
def _table(rows,empty):
 if rows:st.dataframe(rows,hide_index=True,width='stretch')
 else:empty_state('No records to display',empty,icon='▤',action_hint='Use the relevant classroom action to create the first governed record.')
def _done(value,message):
 if value:st.toast(message,icon=':material/check_circle:');st.rerun()
def _goto(section):
 st.session_state['classroom-workspace-section']=section

def _empty_visual(title,body,icon,action='',target=''):
 with st.container(border=True,horizontal_alignment='center'):
  st.markdown(icon)
  st.subheader(title,anchor=False,text_alignment='center')
  st.caption(body,text_alignment='center')
  if action and target:st.button(action,icon=':material/arrow_forward:',on_click=_goto,args=(target,),key=f'classroom-empty-{target}-{action}',width='stretch')

def _command_board(p,a,i,r):
 if _admin(r):
  data=p._one("""SELECT
   (SELECT COUNT(*) FROM subjects WHERE institution_id=?) subjects,
   (SELECT COUNT(DISTINCT user_id) FROM memberships WHERE institution_id=? AND role IN ('school_student','college_student','university_student') AND state='active') learners,
   (SELECT COUNT(DISTINCT user_id) FROM memberships WHERE institution_id=? AND role NOT IN ('school_student','college_student','university_student','parent_guardian') AND state='active') faculty,
   (SELECT COUNT(*) FROM timetable_entries WHERE institution_id=? AND state='scheduled') schedule""",(i,i,i,i)) or {}
  cards=[('Subjects',data.get('subjects',0),':material/menu_book:'),('Learners',data.get('learners',0),':material/groups:'),('Faculty',data.get('faculty',0),':material/co_present:'),('Scheduled classes',data.get('schedule',0),':material/calendar_month:')]
 elif _teacher(r):
  data=p._one("""SELECT
   COUNT(DISTINCT ta.subject_id) subjects,COUNT(DISTINCT e.student_id) learners,
   COUNT(DISTINCT ass.id) assignments,COUNT(DISTINCT tt.id) schedule
   FROM teacher_assignments ta LEFT JOIN enrollments e ON e.subject_id=ta.subject_id AND e.state='active'
   LEFT JOIN assignments ass ON ass.subject_id=ta.subject_id AND ass.state='published'
   LEFT JOIN timetable_entries tt ON tt.subject_id=ta.subject_id AND tt.teacher_id=ta.teacher_id AND tt.state='scheduled'
   WHERE ta.institution_id=? AND ta.teacher_id=? AND ta.state='active'""",(i,a)) or {}
  cards=[('Assigned subjects',data.get('subjects',0),':material/menu_book:'),('Your learners',data.get('learners',0),':material/groups:'),('Published assignments',data.get('assignments',0),':material/assignment:'),('Scheduled classes',data.get('schedule',0),':material/calendar_month:')]
 elif _student(r):
  data=p._one("""SELECT
   COUNT(DISTINCT e.subject_id) subjects,
   COUNT(DISTINCT CASE WHEN ass.state='published' AND sub.id IS NULL THEN ass.id END) pending,
   (SELECT COUNT(*) FROM attendance_records WHERE institution_id=? AND student_id=?) attendance,
   (SELECT COUNT(*) FROM results WHERE institution_id=? AND student_id=? AND published=1) results
   FROM enrollments e LEFT JOIN assignments ass ON ass.subject_id=e.subject_id
   LEFT JOIN submissions sub ON sub.assignment_id=ass.id AND sub.student_id=e.student_id
   WHERE e.institution_id=? AND e.student_id=? AND e.state='active'""",(i,a,i,a,i,a)) or {}
  cards=[('Enrolled subjects',data.get('subjects',0),':material/menu_book:'),('Pending assignments',data.get('pending',0),':material/assignment_late:'),('Attendance records',data.get('attendance',0),':material/fact_check:'),('Published results',data.get('results',0),':material/analytics:')]
 else:
  cards=[('Active memberships',len(r),':material/verified_user:')]
 with st.container(horizontal=True,gap='small'):
  for label,value,icon in cards:st.metric(f'{icon} {label}',int(value or 0),border=True)

def _hero(p,a,i,r):
 inst=p._one('SELECT name,kind,timezone,state FROM institutions WHERE id=?',(i,)) or {}
 with st.container(border=True,gap='small'):
  left,right=st.columns([3,1],vertical_alignment='center')
  left.markdown('### :material/school: BioIntel Classroom')
  left.caption(f"{inst.get('name','Institution')} · {inst.get('kind','education').replace('_',' ')} · {inst.get('timezone','UTC')}")
  right.badge(inst.get('state','active'),icon=':material/verified:',color='green' if inst.get('state','active')=='active' else 'orange')
  with st.container(horizontal=True,vertical_alignment='center'):
   st.badge('Durable local records',icon=':material/database:',color='gray')
   for role in sorted(r):st.badge(role.replace('_',' '),icon=':material/verified_user:',color='blue')
  _command_board(p,a,i,r)
 actions=[]
 if _admin(r):actions=[('Create subject','Subjects & people',':material/library_add:'),('Education suite','Education suite',':material/auto_stories:'),('Take attendance','Attendance',':material/fact_check:'),('Publish assignment','Assignments',':material/post_add:')]
 elif _teacher(r):actions=[('My subjects','Subjects & people',':material/menu_book:'),('Education suite','Education suite',':material/auto_stories:'),('Take attendance','Attendance',':material/fact_check:'),('Publish assignment','Assignments',':material/post_add:')]
 elif _student(r):actions=[('Education suite','Education suite',':material/auto_stories:'),('Open assignments','Assignments',':material/assignment:'),('My attendance','Attendance',':material/fact_check:'),('Read circulars','Circulars',':material/campaign:')]
 if actions:
  st.caption('Quick actions')
  with st.container(horizontal=True,horizontal_alignment='distribute'):
   for label,target,icon in actions:st.button(label,key=f'classroom-quick-{target}-{label}',icon=icon,on_click=_goto,args=(target,))

def _progress_activity(p,a,i,r):
 progress_col,activity_col=st.columns([1,1],gap='medium')
 with progress_col:
  with st.container(border=True,height='stretch'):
   st.subheader('Progress snapshot',anchor=False)
   if _student(r) and not _teacher(r):
    work=p._one("""SELECT COUNT(DISTINCT a.id) total,COUNT(DISTINCT CASE WHEN sub.state='submitted' THEN a.id END) complete
     FROM assignments a JOIN enrollments e ON e.subject_id=a.subject_id AND e.student_id=? AND e.state='active'
     LEFT JOIN submissions sub ON sub.assignment_id=a.id AND sub.student_id=?
     WHERE a.institution_id=? AND a.state='published'""",(a,a,i)) or {'total':0,'complete':0}
    attendance=p._one("""SELECT COUNT(*) total,SUM(CASE WHEN status IN ('present','online_present','practical_attendance','examination_attendance','institutional_duty') THEN 1 ELSE 0 END) attended
     FROM attendance_records WHERE institution_id=? AND student_id=?""",(i,a)) or {'total':0,'attended':0}
    if work['total']:
     st.progress(work['complete']/work['total'],text=f"Assignments submitted · {work['complete']} of {work['total']}")
    else:st.caption('No published assignments are assigned yet.')
    if attendance['total']:
     attended=attendance['attended'] or 0;st.progress(attended/attendance['total'],text=f"Recorded attendance · {attended} of {attendance['total']} attended")
    else:st.caption('No attendance sessions have been recorded yet.')
   elif _teacher(r):
    if _admin(r):join='';args=(i,)
    else:join="JOIN teacher_assignments mine ON mine.subject_id=a.subject_id AND mine.teacher_id=? AND mine.state='active'";args=(a,i)
    grading=p._one(f"""SELECT COUNT(DISTINCT sub.id) total,COUNT(DISTINCT g.submission_id) graded
     FROM assignments a {join} LEFT JOIN submissions sub ON sub.assignment_id=a.id AND sub.state='submitted'
     LEFT JOIN grades g ON g.submission_id=sub.id WHERE a.institution_id=?""",args) or {'total':0,'graded':0}
    sessions=p._one(f"""SELECT COUNT(DISTINCT ses.id) sessions,COUNT(DISTINCT rec.id) records
     FROM subjects s {' ' if _admin(r) else join.replace('a.subject_id','s.id')} LEFT JOIN attendance_sessions ses ON ses.subject_id=s.id
     LEFT JOIN attendance_records rec ON rec.session_id=ses.id WHERE s.institution_id=?""",args) or {'sessions':0,'records':0}
    if grading['total']:st.progress(grading['graded']/grading['total'],text=f"Submissions graded · {grading['graded']} of {grading['total']}")
    else:st.caption('No submitted work is waiting in your subjects.')
    st.caption(f"Attendance evidence · {sessions['sessions']} sessions · {sessions['records']} records")
   if _admin(r):
    setup=p._one("""SELECT
     (SELECT COUNT(*) FROM subjects WHERE institution_id=?) subjects,
     (SELECT COUNT(*) FROM teacher_assignments WHERE institution_id=? AND state='active') teacher_links,
     (SELECT COUNT(*) FROM enrollments WHERE institution_id=? AND state='active') enrollments,
     (SELECT COUNT(*) FROM circulars WHERE institution_id=? AND state='published') circulars""",(i,i,i,i)) or {}
    checks=[('Subjects',setup.get('subjects',0)),('Teaching assignments',setup.get('teacher_links',0)),('Student enrollments',setup.get('enrollments',0)),('Published circulars',setup.get('circulars',0))]
    ready=sum(bool(value) for _,value in checks);st.progress(ready/len(checks),text=f'Institution setup · {ready} of {len(checks)} foundations active')
    st.caption(' · '.join(f"{label}: {value}" for label,value in checks))
 with activity_col:
  with st.container(border=True,height='stretch'):
   st.subheader('Recent activity',anchor=False)
   if _admin(r):clause='';args=(i,)
   else:clause='AND actor_id=?';args=(i,a)
   events=_all(p,f"""SELECT action,target_type,actor_id,created_at FROM education_audit_events
    WHERE institution_id=? {clause} ORDER BY created_at DESC LIMIT 6""",args)
   if not events:empty_state('No classroom activity yet','No audited classroom action is visible for this role and institution.',icon='✓',action_hint='Activity will appear after a governed classroom action.')
   for event in events:
    st.markdown(f":material/check_circle: **{event['action'].replace('_',' ')}** · {event['target_type']}")
    detail=event['created_at']
    if _admin(r):detail=f"{event['actor_id']} · {detail}"
    st.caption(detail)

def _journey(p,a,i,r):
 if _admin(r):
  data=p._one("""SELECT
   (SELECT COUNT(*) FROM subjects WHERE institution_id=?) step1,
   (SELECT COUNT(*) FROM teacher_assignments WHERE institution_id=? AND state='active') step2,
   (SELECT COUNT(*) FROM enrollments WHERE institution_id=? AND state='active') step3,
   ((SELECT COUNT(*) FROM attendance_records WHERE institution_id=?)+(SELECT COUNT(*) FROM submissions WHERE institution_id=?)+(SELECT COUNT(*) FROM results WHERE institution_id=?)) step4""",(i,i,i,i,i,i)) or {}
  steps=[('Subjects',data.get('step1',0),':material/menu_book:'),('Teaching links',data.get('step2',0),':material/co_present:'),('Learner access',data.get('step3',0),':material/groups:'),('Learning evidence',data.get('step4',0),':material/fact_check:')]
 elif _teacher(r):
  data=p._one("""SELECT COUNT(DISTINCT ta.subject_id) step1,COUNT(DISTINCT ses.id) step2,COUNT(DISTINCT ass.id) step3,COUNT(DISTINCT g.id) step4
   FROM teacher_assignments ta LEFT JOIN attendance_sessions ses ON ses.subject_id=ta.subject_id
   LEFT JOIN assignments ass ON ass.subject_id=ta.subject_id LEFT JOIN submissions sub ON sub.assignment_id=ass.id
   LEFT JOIN grades g ON g.submission_id=sub.id WHERE ta.institution_id=? AND ta.teacher_id=? AND ta.state='active'""",(i,a)) or {}
  steps=[('Assigned subjects',data.get('step1',0),':material/menu_book:'),('Attendance sessions',data.get('step2',0),':material/fact_check:'),('Assignments',data.get('step3',0),':material/assignment:'),('Released grades',data.get('step4',0),':material/grading:')]
 elif _student(r):
  data=p._one("""SELECT
   (SELECT COUNT(*) FROM enrollments WHERE institution_id=? AND student_id=? AND state='active') step1,
   (SELECT COUNT(*) FROM attendance_records WHERE institution_id=? AND student_id=?) step2,
   (SELECT COUNT(*) FROM submissions WHERE institution_id=? AND student_id=? AND state='submitted') step3,
   (SELECT COUNT(*) FROM results WHERE institution_id=? AND student_id=? AND published=1) step4""",(i,a,i,a,i,a,i,a)) or {}
  steps=[('Enrolled subjects',data.get('step1',0),':material/menu_book:'),('Attendance evidence',data.get('step2',0),':material/fact_check:'),('Submitted work',data.get('step3',0),':material/assignment_turned_in:'),('Published results',data.get('step4',0),':material/analytics:')]
 else:return
 st.subheader('Classroom journey',anchor=False)
 st.caption('Each stage reflects durable records currently visible to this role.')
 columns=st.columns(4,gap='small',border=True)
 for column,(label,value,icon) in zip(columns,steps):
  with column:
   st.markdown(icon);st.metric(label,int(value or 0));st.badge('Evidence recorded' if value else 'Awaiting record',icon=':material/check:' if value else ':material/schedule:',color='green' if value else 'gray')

def _learning_visuals(p,a,i,r):
 if _admin(r):
  attendance=_all(p,"SELECT status Status,COUNT(*) Records FROM attendance_records WHERE institution_id=? GROUP BY status ORDER BY Records DESC",(i,))
  state=p._one("""SELECT COUNT(DISTINCT sub.id) submitted,COUNT(DISTINCT g.submission_id) graded FROM assignments ass
   LEFT JOIN submissions sub ON sub.assignment_id=ass.id AND sub.state='submitted' LEFT JOIN grades g ON g.submission_id=sub.id WHERE ass.institution_id=?""",(i,)) or {}
  results=_all(p,"""SELECT e.title Assessment,ROUND(AVG(100.0*r.marks/NULLIF(e.max_marks,0)),1) 'Score (%)'
   FROM results r JOIN examinations e ON e.id=r.examination_id WHERE r.institution_id=? AND r.published=1 GROUP BY e.id ORDER BY e.title LIMIT 8""",(i,))
  timetable_args=(i,);timetable_clause=''
 elif _teacher(r):
  attendance=_all(p,"""SELECT rec.status Status,COUNT(*) Records FROM attendance_records rec
   JOIN attendance_sessions ses ON ses.id=rec.session_id JOIN teacher_assignments ta ON ta.subject_id=ses.subject_id AND ta.teacher_id=? AND ta.state='active'
   WHERE rec.institution_id=? GROUP BY rec.status ORDER BY Records DESC""",(a,i))
  state=p._one("""SELECT COUNT(DISTINCT sub.id) submitted,COUNT(DISTINCT g.submission_id) graded FROM teacher_assignments ta
   JOIN assignments ass ON ass.subject_id=ta.subject_id LEFT JOIN submissions sub ON sub.assignment_id=ass.id AND sub.state='submitted'
   LEFT JOIN grades g ON g.submission_id=sub.id WHERE ta.institution_id=? AND ta.teacher_id=? AND ta.state='active'""",(i,a)) or {}
  results=_all(p,"""SELECT e.title Assessment,ROUND(AVG(100.0*r.marks/NULLIF(e.max_marks,0)),1) 'Score (%)'
   FROM results r JOIN examinations e ON e.id=r.examination_id JOIN teacher_assignments ta ON ta.subject_id=e.subject_id AND ta.teacher_id=? AND ta.state='active'
   WHERE r.institution_id=? AND r.published=1 GROUP BY e.id ORDER BY e.title LIMIT 8""",(a,i))
  timetable_args=(i,a);timetable_clause='AND tt.teacher_id=?'
 elif _student(r):
  attendance=_all(p,"SELECT status Status,COUNT(*) Records FROM attendance_records WHERE institution_id=? AND student_id=? GROUP BY status ORDER BY Records DESC",(i,a))
  state=p._one("""SELECT COUNT(DISTINCT ass.id) assigned,COUNT(DISTINCT CASE WHEN sub.state='submitted' THEN sub.id END) submitted
   FROM enrollments e JOIN assignments ass ON ass.subject_id=e.subject_id AND ass.state='published'
   LEFT JOIN submissions sub ON sub.assignment_id=ass.id AND sub.student_id=e.student_id WHERE e.institution_id=? AND e.student_id=? AND e.state='active'""",(i,a)) or {}
  results=_all(p,"""SELECT e.title Assessment,ROUND(100.0*r.marks/NULLIF(e.max_marks,0),1) 'Score (%)'
   FROM results r JOIN examinations e ON e.id=r.examination_id WHERE r.institution_id=? AND r.student_id=? AND r.published=1 ORDER BY e.starts_at LIMIT 8""",(i,a))
  timetable_args=(i,a);timetable_clause="AND EXISTS(SELECT 1 FROM enrollments enr WHERE enr.subject_id=tt.subject_id AND enr.student_id=? AND enr.state='active')"
 else:return
 assignment=[{'State':'Submitted','Records':int(state.get('submitted',0) or 0)}]
 if _student(r):assignment.insert(0,{'State':'Published assigned','Records':int(state.get('assigned',0) or 0)})
 else:assignment.append({'State':'Graded','Records':int(state.get('graded',0) or 0)})
 st.subheader('Learning-state graphics',anchor=False)
 st.caption('Charts are generated from persisted attendance, submission and published-result records.')
 attendance_col,assignment_col,result_col=st.columns(3,gap='medium')
 with attendance_col.container(border=True,height='stretch'):
  st.markdown('**:material/fact_check: Attendance states**')
  if attendance:st.bar_chart([{'Status':x['Status'].replace('_',' ').title(),'Records':x['Records']} for x in attendance],x='Status',y='Records',horizontal=True,height=220)
  else:st.caption('No attendance evidence recorded yet.')
 with assignment_col.container(border=True,height='stretch'):
  st.markdown('**:material/assignment: Assignment states**')
  if any(x['Records'] for x in assignment):st.bar_chart(assignment,x='State',y='Records',horizontal=True,height=220)
  else:st.caption('No submitted assignment evidence recorded yet.')
 with result_col.container(border=True,height='stretch'):
  st.markdown('**:material/analytics: Published results**')
  if results:st.bar_chart(results,x='Assessment',y='Score (%)',horizontal=True,height=220)
  else:st.caption('No published assessment results are visible yet.')
 timetable=_all(p,f"""SELECT s.code || ' · ' || s.name Subject,tt.starts_at Starts,tt.ends_at Ends,COALESCE(NULLIF(tt.room,''),'Not assigned') Room,tt.student_group 'Learner group'
  FROM timetable_entries tt LEFT JOIN subjects s ON s.id=tt.subject_id WHERE tt.institution_id=? AND tt.state='scheduled' {timetable_clause}
  ORDER BY tt.starts_at LIMIT 6""",timetable_args)
 with st.container(border=True):
  st.subheader('Timetable runway',anchor=False);st.caption('Scheduled entries currently visible to this role; times use stored institution values.')
  if timetable:st.dataframe(timetable,hide_index=True,width='stretch')
  else:_empty_visual('No scheduled classes','Create or assign timetable entries to populate this runway.',':material/calendar_month:')

def _subjects(p,a,i,r):
 if _admin(r):join='';args=(i,)
 elif _teacher(r):join="JOIN teacher_assignments mine ON mine.subject_id=s.id AND mine.teacher_id=? AND mine.state='active'";args=(a,i)
 elif _student(r):join="JOIN enrollments mine ON mine.subject_id=s.id AND mine.student_id=? AND mine.state='active'";args=(a,i)
 else:return []
 return _all(p,f'''SELECT s.id,s.code,s.name,s.state,COUNT(DISTINCT e.student_id) students,COUNT(DISTINCT t.teacher_id) teachers
 FROM subjects s {join} LEFT JOIN enrollments e ON e.subject_id=s.id AND e.state='active' LEFT JOIN teacher_assignments t ON t.subject_id=s.id AND t.state='active'
 WHERE s.institution_id=? GROUP BY s.id ORDER BY s.code,s.name''',args)

def _overview(p,a,i,r,subjects,run):
 d=run(lambda:p.dashboard(a,i)) or {}
 defs=[('pending_assignments','Pending assignments',':material/assignment_late:'),('attendance_records','Attendance records',':material/fact_check:'),('assigned_subjects','Assigned subjects',':material/menu_book:'),('pending_grading','Pending grading',':material/grading:'),('students','Students',':material/groups:'),('faculty','Faculty',':material/co_present:')]
 visible=[x for x in defs if x[0] in d]
 if visible:
  with st.container(horizontal=True):
   for key,label,icon in visible:st.metric(f'{icon} {label}',d[key],border=True)
 else:st.caption('No role-specific summary metrics are available for this membership.')
 _journey(p,a,i,r)
 if _student(r) and not _teacher(r):
  pending=_all(p,"SELECT guardian_id,state,requested_by,created_at FROM guardian_links WHERE institution_id=? AND student_id=? AND state='pending' ORDER BY created_at DESC",(i,a))
  if pending:
   with st.container(border=True):
    st.subheader('Guardian access requests',anchor=False)
    st.caption('Only you can activate guardian access. Administrators cannot assert consent on your behalf.')
    for link in pending:
     with st.container(horizontal=True,vertical_alignment='center'):
      st.write(f"**{link['guardian_id']}** · requested by {link['requested_by'] or 'institution'}")
      if st.button('Approve',key=f"guardian-approve-{link['guardian_id']}",type='primary',icon=':material/verified_user:'):_done(run(lambda gid=link['guardian_id']:p.approve_guardian_link(a,i,gid)),'Guardian access approved')
 if not subjects:
  if _admin(r):_empty_visual('Build your first classroom','Create a subject, add teaching staff and enroll learners. Every step is stored and audited.',':material/rocket_launch:','Create the first subject','Subjects & people')
  else:_empty_visual('No classroom assigned yet','Ask your institution administrator to assign or enroll this account in a subject.',':material/school:')
 left,right=st.columns([1.5,1],gap='medium')
 with left:
  with st.container(border=True):
   st.subheader('Your subjects',anchor=False);st.caption('Only subjects available to your current role are shown.')
   _table([{'Code':x['code'],'Subject':x['name'],'Students':x['students'],'Teachers':x['teachers']} for x in subjects],'No subjects are assigned or enrolled for this account yet.')
 with right:
  with st.container(border=True):
   st.subheader('Latest circulars',anchor=False)
   rows=(run(lambda:p.list_circulars(a,i,5)) or [])
   if not rows:empty_state('No published circulars','No audience-visible circular is available in this institution.',icon='↗',action_hint='Administrators can draft and publish the first circular.')
   for x in rows:
    color='red' if x['priority']=='urgent' else 'blue';st.markdown(f"**{x['title']}**  \n:{color}-badge[{x['priority']}] :small[{x['circular_number']}]")
    if x['published_at']:st.caption(x['published_at'])
 _progress_activity(p,a,i,r)
 _learning_visuals(p,a,i,r)
 config=d.get('configuration') or {}
 if config:
  with st.expander('Service readiness',icon=':material/settings_suggest:'):
   for service,status in sorted(config.items()):
    icon=':material/check_circle:' if status=='FULLY WORKING' else ':material/build_circle:';st.write(f"{icon} **{service.replace('_',' ').capitalize()}** — {status}")

def _subjects_people(p,a,i,r,subjects,run):
 opts=_options(subjects)
 if _admin(r):
  with st.expander('Create a subject',icon=':material/library_add:'):
   with st.form('classroom-create-subject',border=False):
    c1,c2=st.columns([1,2],vertical_alignment='bottom');code=c1.text_input('Subject code',placeholder='BIO-201');name=c2.text_input('Subject name',placeholder='Molecular biology');syllabus=st.text_area('Syllabus summary',placeholder='Optional learning outcomes')
    if st.form_submit_button('Create subject',type='primary',icon=':material/add:',width='stretch'):
     if not code.strip() or not name.strip():st.error('Subject code and name are required.')
     else:_done(run(lambda:p.create_subject(a,i,code.strip(),name.strip(),syllabus=syllabus.strip())),'Subject created')
 if not opts:_empty_visual('No subject workspace yet','Create a subject or ask an administrator to assign one before managing people.',':material/menu_book:');return
 sid=st.selectbox('Active subject',list(opts),format_func=opts.get,key='classroom-people-subject');subject=next(x for x in subjects if x['id']==sid)
 with st.container(horizontal=True):
  st.badge(subject['code'],icon=':material/tag:',color='blue');st.badge(f"{subject['teachers']} teachers",icon=':material/co_present:',color='gray');st.badge(f"{subject['students']} students",icon=':material/groups:',color='gray')
 teachers=_all(p,'SELECT teacher_id "User ID",state "Status",created_at "Assigned" FROM teacher_assignments WHERE institution_id=? AND subject_id=? ORDER BY created_at DESC',(i,sid));students=_all(p,'SELECT student_id "User ID",state "Status",created_at "Enrolled" FROM enrollments WHERE institution_id=? AND subject_id=? ORDER BY created_at DESC',(i,sid))
 c1,c2=st.columns(2,gap='medium')
 with c1:st.subheader('Teaching team',anchor=False);_table(teachers,'No teacher has been assigned to this subject.')
 with c2:st.subheader('Learners',anchor=False);_table(students,'No students are enrolled in this subject.')
 if not _admin(r):return
 with st.expander('Manage memberships',icon=':material/manage_accounts:'):
  mode=st.segmented_control('Action',['Add member','Assign teacher','Enroll student'],default='Add member',key='classroom-membership-mode')
  if mode=='Add member':
   with st.form('classroom-add-member',border=False):
    uid=st.text_input('User ID');role=st.selectbox('Institution role',['school_student','college_student','university_student','subject_teacher','class_teacher','lecturer','parent_guardian','institution_administrator'])
    if st.form_submit_button('Save membership',type='primary',icon=':material/person_add:'):
     if not uid.strip():st.error('User ID is required.')
     else:_done(run(lambda:p.add_member(a,i,uid.strip(),role)),'Membership saved')
  elif mode=='Assign teacher':
   with st.form('classroom-assign-teacher',border=False):
    uid=st.text_input('Teacher user ID')
    if st.form_submit_button('Assign teacher',type='primary',icon=':material/co_present:'):
     if not uid.strip():st.error('Teacher user ID is required.')
     else:_done(run(lambda:p.assign_teacher(a,i,sid,uid.strip())),'Teacher assigned')
  else:
   with st.form('classroom-enroll-student',border=False):
    uid=st.text_input('Student user ID')
    if st.form_submit_button('Enroll student',type='primary',icon=':material/school:'):
     if not uid.strip():st.error('Student user ID is required.')
     else:_done(run(lambda:p.enroll(a,i,sid,uid.strip())),'Student enrolled')

def _attendance(p,a,i,r,subjects,run):
 opts=_options(subjects)
 if _student(r) and not _teacher(r):
  rows=_all(p,"""SELECT subj.code || ' · ' || subj.name Subject,s.session_date Date,s.period Period,r.status Status,r.note Note
   FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id JOIN subjects subj ON subj.id=s.subject_id
   WHERE r.institution_id=? AND r.student_id=? ORDER BY s.session_date DESC""",(i,a))
  _table(rows,'No attendance has been recorded for your account.');return
 if not _teacher(r):st.info('Attendance is available to assigned educators, administrators and students.',icon=':material/lock:');return
 if not opts:_empty_visual('Attendance needs a subject','Assign a subject before opening a verified attendance session.',':material/fact_check:');return
 sid=st.selectbox('Subject',list(opts),format_func=opts.get,key='classroom-attendance-subject')
 with st.expander('Open an attendance session',icon=':material/event_available:'):
  with st.form('classroom-open-attendance',border=False):
   c1,c2=st.columns(2,vertical_alignment='bottom');day=c1.date_input('Session date');period=c2.text_input('Period',placeholder='1')
   if st.form_submit_button('Open session',type='primary',icon=':material/add_task:'):
    if not period.strip():st.error('Period is required.')
    else:_done(run(lambda:p.attendance_session(a,i,sid,str(day),period.strip())),'Attendance session opened')
 sessions=_all(p,'SELECT id,session_date,period,state,teacher_id FROM attendance_sessions WHERE institution_id=? AND subject_id=? ORDER BY session_date DESC,period DESC',(i,sid))
 if not sessions:_empty_visual('No attendance session yet','Open the first dated session to begin storing attendance evidence.',':material/event_available:');return
 labels={x['id']:f"{x['session_date']} · period {x['period']} · {x['state']}" for x in sessions};session=st.selectbox('Attendance session',list(labels),format_func=labels.get,key='classroom-attendance-session')
 records=_all(p,'SELECT student_id "Student",status "Status",note "Note",marked_by "Marked by",updated_at "Updated" FROM attendance_records WHERE institution_id=? AND session_id=? ORDER BY student_id',(i,session));_table(records,'No attendance has been marked in this session.')
 if next(x for x in sessions if x['id']==session)['state']!='open':st.caption('This session is locked and cannot be edited.');return
 enrolled=_all(p,"SELECT student_id FROM enrollments WHERE institution_id=? AND subject_id=? AND state='active' ORDER BY student_id",(i,sid))
 if not enrolled:_empty_visual('No learners enrolled','Enroll students in this subject before marking attendance.',':material/person_add:');return
 with st.form('classroom-mark-attendance',border=True):
  c1,c2=st.columns(2);student=c1.selectbox('Student',[x['student_id'] for x in enrolled]);status=c2.selectbox('Status',['present','absent','late','excused_absence','medical_leave','institutional_duty','online_present','practical_attendance','examination_attendance']);note=st.text_input('Note',placeholder='Optional factual note')
  if st.form_submit_button('Save attendance',type='primary',icon=':material/save:',width='stretch'):_done(run(lambda:p.mark_attendance(a,session,student,status,note.strip())),'Attendance saved and audited')

def _assignments(p,a,i,r,subjects,run):
 opts=_options(subjects)
 if _teacher(r) and opts:
  with st.expander('Publish an assignment',icon=':material/post_add:'):
   with st.form('classroom-create-assignment',border=False):
    sid=st.selectbox('Subject',list(opts),format_func=opts.get,key='classroom-assignment-subject');title=st.text_input('Assignment title');instructions=st.text_area('Instructions',placeholder='Learning objective, deliverable and assessment criteria')
    c1,c2,c3=st.columns([1.2,1,1],vertical_alignment='bottom');day=c1.date_input('Due date');clock=c2.time_input('Due time (UTC)',value=time(17,0));maximum=c3.number_input('Maximum marks',min_value=1.0,value=100.0);policy=st.selectbox('Late submission policy',['reject','allow','allow_with_penalty','manual_approval'],format_func=lambda value:value.replace('_',' ').title())
    if st.form_submit_button('Publish assignment',type='primary',icon=':material/publish:',width='stretch'):
     if not title.strip():st.error('Assignment title is required.')
     else:
      due=datetime.combine(day,clock).replace(tzinfo=timezone.utc).isoformat();_done(run(lambda:p.create_assignment(a,i,sid,title.strip(),instructions.strip(),due,maximum,allowed_types=['.pdf','.docx','.txt','.csv','.png','.jpg','.jpeg','.zip'],late_policy=policy,publish=True)),'Assignment published')
 if _teacher(r):
  if _admin(r):args=(i,);join=''
  else:args=(a,i);join="JOIN teacher_assignments mine ON mine.subject_id=a.subject_id AND mine.teacher_id=? AND mine.state='active'"
  rows=_all(p,f'''SELECT a.id,s.code subject_code,a.title,a.due_at,a.max_marks,a.state,COUNT(DISTINCT sub.id) submissions,COUNT(DISTINCT g.id) graded
   FROM assignments a JOIN subjects s ON s.id=a.subject_id {join} LEFT JOIN submissions sub ON sub.assignment_id=a.id LEFT JOIN grades g ON g.submission_id=sub.id
   WHERE a.institution_id=? GROUP BY a.id ORDER BY a.due_at DESC''',args)
 elif _student(r):
  rows=_all(p,"""SELECT a.id,s.code subject_code,a.title,a.instructions,a.due_at,a.max_marks,a.state,COALESCE(sub.state,'not submitted') submission_state,sub.id submission_id
   FROM assignments a JOIN subjects s ON s.id=a.subject_id JOIN enrollments e ON e.subject_id=a.subject_id AND e.student_id=? AND e.state='active'
   LEFT JOIN submissions sub ON sub.assignment_id=a.id AND sub.student_id=? WHERE a.institution_id=? AND a.state='published' ORDER BY a.due_at""",(a,a,i))
 else:rows=[]
 if not rows:
  _empty_visual('No assignments available','Publish an assignment or wait for an educator to add work to an enrolled subject.',':material/assignment:');return
 _table([{'ID':x['id'],'Subject':x['subject_code'],'Assignment':x['title'],'Due (UTC)':x['due_at'],'Marks':x['max_marks'],'Status':x.get('submission_state',x['state']),**({'Submissions':x['submissions'],'Graded':x['graded']} if 'submissions' in x else {})} for x in rows],'No assignments are available for this role.')
 labels={x['id']:f"{x['subject_code']} · {x['title']}" for x in rows};aid=st.selectbox('Open assignment',list(labels),format_func=labels.get,key='classroom-open-assignment')
 if _student(r) and not _teacher(r):
  item=next(x for x in rows if x['id']==aid)
  if item.get('submission_state')=='submitted':st.success('Your final submission is stored.',icon=':material/check_circle:')
  else:
   with st.form('classroom-submit-assignment',border=True):
    body=st.text_area('Submission',placeholder='Enter the completed response. A timestamped final record will be stored.')
    upload=st.file_uploader('Optional attachment',type=['pdf','docx','txt','csv','png','jpg','jpeg','zip'])
    confirm=st.checkbox('Submit this response as final')
    if st.form_submit_button('Submit assignment',type='primary',icon=':material/send:',width='stretch'):
     if not body.strip() and upload is None:st.error('Submission text or an attachment is required.')
     elif not confirm:st.error('Confirm the final submission before sending.')
     else:
      temp_path=''
      if upload is not None:
       folder=p.storage/'ui_uploads';folder.mkdir(parents=True,exist_ok=True);target=folder/f"{a}-{aid}-{upload.name}";target.write_bytes(upload.getbuffer());temp_path=str(target)
      try:_done(run(lambda:p.submit_assignment(a,aid,body=body.strip(),file_path=temp_path,final=True)),'Assignment submitted')
      finally:
       if temp_path:Path(temp_path).unlink(missing_ok=True)
 elif _teacher(r):
  subs=_all(p,'SELECT sub.id,sub.student_id,sub.submitted_at,sub.state,sub.late,sub.penalty_percent,sub.file_name,g.marks,g.feedback FROM submissions sub LEFT JOIN grades g ON g.submission_id=sub.id WHERE sub.assignment_id=? ORDER BY sub.submitted_at DESC',(aid,));_table([{'ID':x['id'],'Student':x['student_id'],'Submitted':x['submitted_at'],'Status':x['state'],'Late':bool(x['late']),'Penalty %':x['penalty_percent'],'Attachment':x['file_name'],'Marks':x['marks'],'Feedback':x['feedback']} for x in subs],'No students have submitted this assignment yet.')
  pending=[x for x in subs if x['marks'] is None]
  if pending:
   ids={x['id']:f"{x['student_id']} · {x['submitted_at'] or 'draft'}" for x in pending};maximum=float(next(x for x in rows if x['id']==aid)['max_marks'])
   with st.form('classroom-grade-submission',border=True):
    sub=st.selectbox('Submission',list(ids),format_func=ids.get);marks=st.number_input('Marks',min_value=0.0,max_value=maximum);feedback=st.text_area('Feedback')
    if st.form_submit_button('Release grade',type='primary',icon=':material/grading:',width='stretch'):_done(run(lambda:p.grade_submission(a,sub,marks,feedback.strip())),'Grade released')

def _circulars(p,a,i,r,run):
 if _admin(r):
  with st.expander('Draft a circular',icon=':material/edit_notifications:'):
   with st.form('classroom-create-circular',border=False):
    c1,c2=st.columns([1.4,1]);number=c1.text_input('Circular number',placeholder='BIO/2026/001');priority=c2.selectbox('Priority',['normal','high','urgent']);title=st.text_input('Title');content=st.text_area('Official content',height=160);audience=st.pills('Audience',['students','faculty','parents','department','institution'],default=['students'],selection_mode='multi')
    if st.form_submit_button('Save draft',type='primary',icon=':material/save:',width='stretch'):
     if not number.strip() or not title.strip() or not content.strip():st.error('Number, title and official content are required.')
     elif not audience:st.error('Select at least one audience.')
     else:_done(run(lambda:p.create_circular(a,i,number.strip(),title.strip(),content.strip(),audience,priority)),'Circular draft saved')
 if _admin(r):
  rows=_all(p,'''SELECT c.id,c.circular_number,c.title,c.content,c.priority,c.state,c.published_at,c.created_at,
   EXISTS(SELECT 1 FROM circular_acknowledgements ack WHERE ack.circular_id=c.id AND ack.user_id=?) acknowledged
   FROM circulars c WHERE c.institution_id=? ORDER BY CASE c.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,COALESCE(c.published_at,c.created_at) DESC''',(a,i))
 else:
  rows=run(lambda:p.list_circulars(a,i,200)) or []
  for item in rows:item['acknowledged']=bool(p._one('SELECT 1 ok FROM circular_acknowledgements WHERE circular_id=? AND user_id=?',(item['id'],a)))
 if not rows:_empty_visual('No circulars available','Authorized administrators can draft and publish the first institution circular.',':material/campaign:');return
 for x in rows:
  with st.container(border=True):
   c1,c2=st.columns([4,1],vertical_alignment='center');c1.subheader(x['title'],anchor=False);color={'urgent':'red','high':'orange'}.get(x['priority'],'blue');c2.badge(x['priority'],icon=':material/priority_high:',color=color);st.caption(f"{x['circular_number']} · {x['state']} · {x['published_at'] or x['created_at']}");st.write(x['content'])
   with st.container(horizontal=True,vertical_alignment='center'):
    if x['state']=='draft' and _admin(r):
     if st.button('Approve and publish',key=f"classroom-publish-{x['id']}",type='primary',icon=':material/publish:'):_done(run(lambda cid=x['id']:p.publish_circular(a,cid)),'Circular published')
    elif not x['acknowledged']:
     if st.button('Acknowledge',key=f"classroom-ack-{x['id']}",icon=':material/done_all:'):_done(run(lambda cid=x['id']:p.acknowledge_circular(a,cid)),'Circular acknowledged')
    else:st.badge('Acknowledged',icon=':material/done_all:',color='green')

def _search(p,a,i,run):
 with st.form('classroom-search',border=False):
  with st.container(horizontal=True,vertical_alignment='bottom'):
   query=st.text_input('Search Classroom, Academy and Science Pulse',placeholder='Subject, material, course, publication or news',label_visibility='collapsed');submitted=st.form_submit_button('Search',type='primary',icon=':material/search:')
 if not submitted:st.caption('Search is institution-scoped for academic data and source-linked for Science Pulse.');return
 if not query.strip():st.warning('Enter a search term.',icon=':material/search:');return
 result=run(lambda:p.unified_search(a,i,query.strip()))
 if result is None:return
 counts={k:len(v or []) for k,v in result.items()}
 if not any(counts.values()):_empty_visual('No matching records',f'No accessible record matched “{query.strip()}”. Try a subject, course, publication or news title.',':material/search_off:');return
 with st.container(horizontal=True):
  for label,count in counts.items():
   if count:st.metric(label.replace('_',' ').capitalize(),count,border=True)
 for label,rows in result.items():
  if rows:
   with st.expander(f"{label.replace('_',' ').capitalize()} · {len(rows)}",icon=':material/folder_open:'):st.dataframe(rows,hide_index=True,width='stretch')

def render_classroom_workspace(p:Any,actor:str,institution_id:str,run:Run)->None:
 """Render the role-aware, tenant-scoped Classroom workspace."""
 roles=_roles(p,actor,institution_id)
 if not roles:st.error('Your account has no active membership in this institution.',icon=':material/lock:');return
 subjects=_subjects(p,actor,institution_id,roles)
 st.session_state.setdefault('classroom-workspace-section','Overview')
 _hero(p,actor,institution_id,roles)
 section=st.segmented_control('Classroom section',['Overview','Education suite','Subjects & people','Attendance','Assignments','Circulars','Search'],key='classroom-workspace-section',width='stretch');st.space('small')
 if section=='Overview':_overview(p,actor,institution_id,roles,subjects,run)
 elif section=='Education suite':render_classroom_suite(EducationSuiteService(),actor,institution_id,roles,subjects)
 elif section=='Subjects & people':_subjects_people(p,actor,institution_id,roles,subjects,run)
 elif section=='Attendance':_attendance(p,actor,institution_id,roles,subjects,run)
 elif section=='Assignments':_assignments(p,actor,institution_id,roles,subjects,run)
 elif section=='Circulars':_circulars(p,actor,institution_id,roles,run)
 else:_search(p,actor,institution_id,run)











