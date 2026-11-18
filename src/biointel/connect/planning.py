from __future__ import annotations
import uuid
from datetime import datetime,timezone
from typing import Any
from biointel.database.core import utc_now
from .phase_store import PersistentMap
from .services import ConnectError,PermissionDenied

class PlanningService:
    STATES={'todo','in_progress','blocked','completed','cancelled'}
    def __init__(self,services:Any)->None: self.services=services; self.tasks=PersistentMap(services,'planning.tasks'); self.milestones=PersistentMap(services,'planning.milestones')
    def _role(self,user_id:str,project_id:str)->str:
        with self.services.database.connection(read_only=True) as db:
            project=db.execute('SELECT owner_id FROM connect_research_projects WHERE project_id=? AND state<>\'deleted\'',(project_id,)).fetchone()
            if not project: raise ConnectError('Project not found.')
            if project['owner_id']==user_id: return 'owner'
            member=db.execute("SELECT role FROM connect_project_members WHERE project_id=? AND user_id=? AND state='active'",(project_id,user_id)).fetchone()
        if not member: raise PermissionDenied('Active project membership required.')
        return str(member['role'])
    def create_task(self,user_id:str,project_id:str,title:str,assignee_id:str|None=None,due_at_utc:str|None=None,priority:str='medium',dependency_ids:list[str]|None=None)->dict[str,Any]:
        self._role(user_id,project_id)
        if not title.strip(): raise ConnectError('Task title is required.')
        if priority not in {'low','medium','high','critical'}: raise ConnectError('Invalid priority.')
        dependencies=list(dict.fromkeys(dependency_ids or []))
        for dep in dependencies:
            task=self.tasks.get(dep)
            if not task or task['project_id']!=project_id: raise ConnectError('Task dependency must exist in the same project.')
        task_id=f'task_{uuid.uuid4().hex}'; now=utc_now(); task={'task_id':task_id,'project_id':project_id,'creator_id':user_id,'title':title.strip(),'assignee_id':assignee_id,'due_at_utc':due_at_utc,'priority':priority,'status':'todo','dependency_ids':dependencies,'completed_at_utc':None,'created_at_utc':now,'updated_at_utc':now}; self.tasks[task_id]=task; return dict(task)
    def set_task_status(self,user_id:str,task_id:str,status:str)->dict[str,Any]:
        task=self.tasks.get(task_id)
        if not task: raise ConnectError('Task not found.')
        self._role(user_id,task['project_id'])
        if status not in self.STATES: raise ConnectError('Invalid task status.')
        if status=='completed':
            incomplete=[dep for dep in task['dependency_ids'] if self.tasks.get(dep,{}).get('status')!='completed']
            if incomplete: raise ConnectError('Task dependencies must be completed first.')
        task['status']=status; task['completed_at_utc']=utc_now() if status=='completed' else None; task['updated_at_utc']=utc_now(); return dict(task)
    def create_milestone(self,user_id:str,project_id:str,title:str,due_at_utc:str|None=None,task_ids:list[str]|None=None)->dict[str,Any]:
        self._role(user_id,project_id); ids=list(dict.fromkeys(task_ids or []))
        if any(not self.tasks.get(x) or self.tasks[x]['project_id']!=project_id for x in ids): raise ConnectError('Milestone tasks must belong to the project.')
        milestone_id=f'milestone_{uuid.uuid4().hex}'; item={'milestone_id':milestone_id,'project_id':project_id,'creator_id':user_id,'title':title,'due_at_utc':due_at_utc,'task_ids':ids,'status':'open','created_at_utc':utc_now()}; self.milestones[milestone_id]=item; return dict(item)
    def progress(self,user_id:str,project_id:str)->dict[str,Any]:
        self._role(user_id,project_id); tasks=[x for x in self.tasks.values() if x['project_id']==project_id and x['status']!='cancelled']; completed=sum(x['status']=='completed' for x in tasks); percent=round(completed*100/len(tasks),1) if tasks else 0.0
        overdue=0; now=datetime.now(timezone.utc)
        for task in tasks:
            if task.get('due_at_utc') and task['status']!='completed':
                try: overdue+=datetime.fromisoformat(task['due_at_utc'].replace('Z','+00:00'))<now
                except ValueError: pass
        return {'project_id':project_id,'task_count':len(tasks),'completed_tasks':completed,'overdue_tasks':int(overdue),'completion_percent':percent,'calculation':'completed_non_cancelled_tasks / non_cancelled_tasks','generated_at_utc':utc_now()}
    def list_tasks(self,user_id:str,project_id:str)->list[dict[str,Any]]: self._role(user_id,project_id); return [dict(x) for x in self.tasks.values() if x['project_id']==project_id]
