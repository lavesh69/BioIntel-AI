from __future__ import annotations

import hashlib, json
from typing import Any
from biointel.database.core import utc_now
from .repositories import ConnectRepository, new_id
from .services import Conflict, ConnectError, NotFound, PermissionDenied

class CollaborationService:
    """Collaboration, project, publication, dataset, workflow, event and opportunity workflows."""
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo
    def _insert(self,table:str,key:str,prefix:str,actor:str,values:dict[str,Any],*,visibility:str="public",state:str="active")->dict[str,Any]:
        object_id,now=new_id(prefix),utc_now(); payload={key:object_id,"creator_id":actor,**values,"state":state,"visibility":visibility,"created_at_utc":now,"updated_at_utc":now}
        with self.repo.database.connection() as db:
            columns=','.join(payload); marks=','.join('?' for _ in payload)
            db.execute(f"INSERT INTO {table}({columns}) VALUES({marks})",tuple(payload.values()))
            row=db.execute(f"SELECT * FROM {table} WHERE {key}=?",(object_id,)).fetchone()
        self.repo.audit(actor,f"{prefix}_created",prefix,object_id)
        return dict(row)
    def _get(self,table:str,key:str,object_id:str)->dict[str,Any]:
        with self.repo.database.connection(read_only=True) as db: row=db.execute(f"SELECT * FROM {table} WHERE {key}=? AND deleted_at_utc IS NULL",(object_id,)).fetchone()
        if not row: raise NotFound("Scientific resource not found.")
        return dict(row)
    def _visible(self,viewer:str,row:dict[str,Any],owner_key:str="owner_id")->bool:
        if row["state"] not in {"active","published","open"}: return False
        owner=str(row.get(owner_key) or row.get("creator_id") or "")
        if viewer==owner: return True
        if owner and self.repo.blocked(viewer,owner): return False
        return row["visibility"] in {"public","authenticated"}

    def create_collaboration(self,actor:str,*,title:str,objective:str,description:str="",research_field:str="",data_modality:str="",required_skills:list[str]|None=None,deadline_utc:str|None=None,visibility:str="public")->dict[str,Any]:
        if not title.strip() or not objective.strip(): raise ConnectError("Title and objective are required.")
        return self._insert("connect_collaboration_requests","collaboration_id","collab",actor,{"owner_id":actor,"title":title[:240],"objective":objective[:5000],"description":description[:10000],"research_field":research_field[:200],"data_modality":data_modality[:200],"required_skills_json":json.dumps(required_skills or []),"deadline_utc":deadline_utc},visibility=visibility,state="open")
    def apply(self,actor:str,collaboration_id:str,*,introduction:str,experience:str="",skills:list[str]|None=None,availability:str="",proposed_contribution:str="")->dict[str,Any]:
        request=self._get("connect_collaboration_requests","collaboration_id",collaboration_id)
        if request["owner_id"]==actor: raise Conflict("Owner cannot apply to their own collaboration.")
        if not self._visible(actor,request): raise PermissionDenied("Collaboration is not visible.")
        row=self._insert("connect_collaboration_applications","application_id","collapp",actor,{"collaboration_id":collaboration_id,"applicant_id":actor,"introduction":introduction[:3000],"experience":experience[:5000],"skills_json":json.dumps(skills or []),"availability":availability[:500],"proposed_contribution":proposed_contribution[:5000]},visibility="private",state="pending")
        self.repo.notification(str(request["owner_id"]),actor,"collaboration_application","collaboration",collaboration_id,"New collaboration application.")
        return row
    def decide_application(self,actor:str,application_id:str,decision:str)->dict[str,Any]:
        if decision not in {"accepted","declined"}: raise ConnectError("Decision must be accepted or declined.")
        app=self._get("connect_collaboration_applications","application_id",application_id); request=self._get("connect_collaboration_requests","collaboration_id",app["collaboration_id"])
        if request["owner_id"]!=actor: raise PermissionDenied("Only the collaboration owner may decide.")
        with self.repo.database.connection() as db:
            db.execute("UPDATE connect_collaboration_applications SET state=?,updated_at_utc=?,version=version+1 WHERE application_id=?",(decision,utc_now(),application_id)); row=db.execute("SELECT * FROM connect_collaboration_applications WHERE application_id=?",(application_id,)).fetchone()
        self.repo.notification(str(app["applicant_id"]),actor,f"collaboration_{decision}","collaboration",str(app["collaboration_id"]),f"Collaboration application {decision}.")
        return dict(row)

    def create_project(self,actor:str,*,title:str,abstract:str="",objective:str="",principal_investigator:str="",institution:str="",research_areas:list[str]|None=None,timeline:dict[str,Any]|None=None,visibility:str="public")->dict[str,Any]:
        row=self._insert("connect_research_projects","project_id","project",actor,{"owner_id":actor,"title":title[:300],"abstract":abstract[:10000],"objective":objective[:5000],"principal_investigator":principal_investigator[:240],"institution":institution[:240],"research_areas_json":json.dumps(research_areas or []),"timeline_json":json.dumps(timeline or {})},visibility=visibility)
        now=utc_now()
        with self.repo.database.connection() as db: db.execute("INSERT INTO connect_project_members(membership_id,creator_id,project_id,user_id,role,joined_at_utc,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,? ,?,'active','private',?,?)",(new_id("projmem"),actor,row["project_id"],actor,"owner",now,now,now))
        return row
    def add_project_member(self,actor:str,project_id:str,user_id:str,role:str="member")->dict[str,Any]:
        project=self._get("connect_research_projects","project_id",project_id)
        with self.repo.database.connection(read_only=True) as db: membership=db.execute("SELECT role FROM connect_project_members WHERE project_id=? AND user_id=? AND state='active'",(project_id,actor)).fetchone()
        if project["owner_id"]!=actor and (not membership or membership["role"] not in {"owner","administrator"}): raise PermissionDenied("Project administration role required.")
        now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_project_members(membership_id,creator_id,project_id,user_id,role,joined_at_utc,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'active','private',?,?) ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role,state='active',deleted_at_utc=NULL,updated_at_utc=excluded.updated_at_utc""",(new_id("projmem"),actor,project_id,user_id,role[:40],now,now,now)); row=db.execute("SELECT * FROM connect_project_members WHERE project_id=? AND user_id=?",(project_id,user_id)).fetchone()
        return dict(row)

    def create_publication(self,actor:str,*,title:str,authors:list[str],authorship_confirmed:bool,abstract:str="",journal:str="",publication_date:str="",doi:str="",pubmed_id:str="",metadata:dict[str,Any]|None=None,visibility:str="public")->dict[str,Any]:
        if not authorship_confirmed: raise ConnectError("Explicit authorship confirmation is required.")
        if not title.strip() or not authors: raise ConnectError("Publication title and authors are required.")
        return self._insert("connect_publications","publication_id","publication",actor,{"owner_id":actor,"title":title[:500],"authors_json":json.dumps(authors),"abstract":abstract[:20000],"journal":journal[:500],"publication_date":publication_date[:40],"doi":doi[:200],"pubmed_id":pubmed_id[:100],"metadata_json":json.dumps(metadata or {}),"authorship_confirmed":1},visibility=visibility,state="published")
    def create_dataset(self,actor:str,*,title:str,description:str="",organism:str="",disease:str="",modality:str="",sample_count:int|None=None,total_size_bytes:int|None=None,licence:str="",access_mode:str="metadata_only",metadata:dict[str,Any]|None=None,visibility:str="public")->dict[str,Any]:
        if access_mode not in {"metadata_only","open","request","controlled"}: raise ConnectError("Unsupported dataset access mode.")
        return self._insert("connect_dataset_listings","dataset_id","dataset",actor,{"owner_id":actor,"title":title[:300],"description":description[:10000],"organism":organism[:200],"disease":disease[:200],"modality":modality[:200],"sample_count":sample_count,"total_size_bytes":total_size_bytes,"licence":licence[:200],"access_mode":access_mode,"metadata_json":json.dumps(metadata or {})},visibility=visibility)
    def request_dataset_access(self,actor:str,dataset_id:str,*,reason:str,intended_use:str)->dict[str,Any]:
        dataset=self._get("connect_dataset_listings","dataset_id",dataset_id)
        if dataset["owner_id"]==actor: raise Conflict("Dataset owner already has access.")
        return self._insert("connect_dataset_access_requests","access_request_id","datareq",actor,{"dataset_id":dataset_id,"requester_id":actor,"reason":reason[:5000],"intended_use":intended_use[:5000],"decision":"pending"},visibility="private",state="pending")
    def decide_dataset_access(self,actor:str,access_request_id:str,decision:str,expires_at_utc:str|None=None)->dict[str,Any]:
        if decision not in {"approved","declined","revoked"}: raise ConnectError("Invalid dataset access decision.")
        req=self._get("connect_dataset_access_requests","access_request_id",access_request_id); dataset=self._get("connect_dataset_listings","dataset_id",req["dataset_id"])
        if dataset["owner_id"]!=actor: raise PermissionDenied("Only dataset owner may decide.")
        with self.repo.database.connection() as db:
            db.execute("UPDATE connect_dataset_access_requests SET decision=?,state=?,expires_at_utc=?,updated_at_utc=?,version=version+1 WHERE access_request_id=?",(decision,decision,expires_at_utc,utc_now(),access_request_id)); row=db.execute("SELECT * FROM connect_dataset_access_requests WHERE access_request_id=?",(access_request_id,)).fetchone()
        return dict(row)
    def create_workflow(self,actor:str,*,name:str,scientific_purpose:str,inputs:list[Any]|None=None,steps:list[Any]|None=None,parameters:dict[str,Any]|None=None,engines:list[str]|None=None,requirements:dict[str,Any]|None=None,validation_status:str="unvalidated",licence:str="",limitations:str="",visibility:str="public")->dict[str,Any]:
        row=self._insert("connect_workflow_listings","workflow_id","workflow",actor,{"owner_id":actor,"name":name[:300],"scientific_purpose":scientific_purpose[:10000],"inputs_json":json.dumps(inputs or []),"steps_json":json.dumps(steps or []),"parameters_json":json.dumps(parameters or {}),"engines_json":json.dumps(engines or []),"requirements_json":json.dumps(requirements or {}),"validation_status":validation_status[:60],"licence":licence[:200],"limitations":limitations[:5000]},visibility=visibility)
        definition={"inputs":inputs or [],"steps":steps or [],"parameters":parameters or {},"engines":engines or []}; encoded=json.dumps(definition,sort_keys=True).encode(); now=utc_now()
        with self.repo.database.connection() as db: db.execute("INSERT INTO connect_workflow_versions(workflow_version_id,creator_id,workflow_id,version_label,definition_json,checksum,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'active','public',?,?)",(new_id("wfver"),actor,row["workflow_id"],"1.0.0",encoded.decode(),hashlib.sha256(encoded).hexdigest(),now,now))
        return row
    def fork_workflow(self,actor:str,workflow_id:str)->dict[str,Any]:
        source=self._get("connect_workflow_listings","workflow_id",workflow_id)
        if not self._visible(actor,source): raise PermissionDenied("Workflow is not visible.")
        # Fork only copies definition; it deliberately never executes scientific code.
        row=self.create_workflow(actor,name=f"Fork of {source['name']}",scientific_purpose=source["scientific_purpose"],inputs=json.loads(source["inputs_json"]),steps=json.loads(source["steps_json"]),parameters=json.loads(source["parameters_json"]),engines=json.loads(source["engines_json"]),requirements=json.loads(source["requirements_json"]),validation_status="fork_unvalidated",licence=source["licence"],limitations=source["limitations"],visibility="private")
        with self.repo.database.connection() as db: db.execute("UPDATE connect_workflow_listings SET audit_json=? WHERE workflow_id=?",(json.dumps({"forked_from":workflow_id,"execution_performed":False}),row["workflow_id"]))
        return self._get("connect_workflow_listings","workflow_id",row["workflow_id"])
    def create_event(self,actor:str,*,event_type:str,title:str,starts_at_utc:str,description:str="",ends_at_utc:str|None=None,capacity:int|None=None,meeting_link:str="",community_id:str|None=None,visibility:str="public")->dict[str,Any]:
        return self._insert("connect_events","event_id","event",actor,{"host_id":actor,"community_id":community_id,"event_type":event_type[:60],"title":title[:300],"description":description[:10000],"starts_at_utc":starts_at_utc,"ends_at_utc":ends_at_utc,"capacity":capacity,"meeting_link":meeting_link[:1000]},visibility=visibility)
    def register_event(self,actor:str,event_id:str)->dict[str,Any]:
        event=self._get("connect_events","event_id",event_id)
        if not self._visible(actor,event,"host_id"): raise PermissionDenied("Event is not visible.")
        now=utc_now()
        with self.repo.database.connection() as db:
            if event["capacity"] is not None:
                count=db.execute("SELECT COUNT(*) FROM connect_event_registrations WHERE event_id=? AND state='active'",(event_id,)).fetchone()[0]
                if count>=int(event["capacity"]): raise Conflict("Event capacity reached.")
            db.execute("""INSERT INTO connect_event_registrations(registration_id,creator_id,event_id,user_id,attendance_state,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,'registered','active','private',?,?) ON CONFLICT(event_id,user_id) DO UPDATE SET attendance_state='registered',state='active',deleted_at_utc=NULL,updated_at_utc=excluded.updated_at_utc""",(new_id("eventreg"),actor,event_id,actor,now,now)); row=db.execute("SELECT * FROM connect_event_registrations WHERE event_id=? AND user_id=?",(event_id,actor)).fetchone()
        return dict(row)
    def create_opportunity(self,actor:str,*,opportunity_type:str,title:str,description:str="",research_field:str="",skills:list[str]|None=None,institution:str="",country:str="",remote:bool=False,deadline_utc:str|None=None,funding_status:str="",visibility:str="public")->dict[str,Any]:
        return self._insert("connect_opportunities","opportunity_id","opportunity",actor,{"owner_id":actor,"opportunity_type":opportunity_type[:80],"title":title[:300],"description":description[:10000],"research_field":research_field[:200],"skills_json":json.dumps(skills or []),"institution":institution[:240],"country":country[:120],"remote":int(remote),"deadline_utc":deadline_utc,"funding_status":funding_status[:120]},visibility=visibility,state="open")
    def list_resources(self,viewer:str,kind:str,query:str="",limit:int=50)->list[dict[str,Any]]:
        mapping={"collaborations":("connect_collaboration_requests","title","owner_id"),"projects":("connect_research_projects","title","owner_id"),"publications":("connect_publications","title","owner_id"),"datasets":("connect_dataset_listings","title","owner_id"),"workflows":("connect_workflow_listings","name","owner_id"),"events":("connect_events","title","host_id"),"opportunities":("connect_opportunities","title","owner_id")}
        if kind not in mapping: raise ConnectError("Unsupported resource kind.")
        table,title,owner=mapping[kind]; like=f"%{query.strip()}%"
        with self.repo.database.connection(read_only=True) as db: rows=[dict(r) for r in db.execute(f"SELECT * FROM {table} WHERE deleted_at_utc IS NULL AND {title} LIKE ? ORDER BY updated_at_utc DESC LIMIT ?",(like,min(max(limit,1),100)))]
        return [r for r in rows if self._visible(viewer,r,owner)]
