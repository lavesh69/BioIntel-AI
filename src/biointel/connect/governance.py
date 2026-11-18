from __future__ import annotations

import hashlib, json, secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from biointel.database.core import utc_now
from .repositories import ConnectRepository, new_id
from .services import Conflict, ConnectError, NotFound, PermissionDenied

UTC=timezone.utc
def _later(hours:int)->str: return (datetime.now(UTC)+timedelta(hours=hours)).isoformat(timespec="seconds")
def _hash(value:str)->str: return hashlib.sha256(value.encode()).hexdigest()

class VerificationService:
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo
    def issue_email_token(self,user_id:str,email:str,purpose:str="verify",hours:int=2)->dict[str,Any]:
        token=secrets.token_urlsafe(32); vid,now=new_id("emailver"),utc_now()
        with self.repo.database.connection() as db:
            db.execute("INSERT INTO connect_email_verifications(email_verification_id,creator_id,user_id,email_hash,token_hash,purpose,expires_at_utc,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'pending','private',?,?)",(vid,user_id,user_id,_hash(email.strip().lower()),_hash(token),purpose,_later(hours),now,now))
        return {"email_verification_id":vid,"token":token,"expires_at_utc":_later(hours),"delivery":"local_adapter"}
    def verify_email(self,user_id:str,token:str)->dict[str,Any]:
        now=utc_now()
        with self.repo.database.connection() as db:
            row=db.execute("SELECT * FROM connect_email_verifications WHERE user_id=? AND token_hash=? AND state='pending'",(user_id,_hash(token))).fetchone()
            if not row: raise NotFound("Verification token not found.")
            if row["expires_at_utc"]<=now: raise PermissionDenied("Verification token expired.")
            db.execute("UPDATE connect_email_verifications SET state='verified',verified_at_utc=?,updated_at_utc=?,version=version+1 WHERE email_verification_id=?",(now,now,row["email_verification_id"]))
            # Verification state is durable in connect_email_verifications; no raw email is stored.
        self.repo.audit(user_id,"email_verified","user",user_id); return {"verified":True,"verified_at_utc":now}
    def submit(self,user_id:str,verification_type:str,*,subject_id:str="",reason:str="",evidence:list[dict[str,str]]|None=None)->dict[str,Any]:
        allowed={"orcid","institution","laboratory","organization","identity","researcher"}
        if verification_type not in allowed: raise ConnectError("Unsupported verification type.")
        rid,now=new_id("verify"),utc_now()
        with self.repo.database.connection() as db:
            db.execute("INSERT INTO connect_verification_requests(verification_request_id,creator_id,user_id,verification_type,subject_id,submitted_reason,decision,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'pending','pending','moderators',?,?)",(rid,user_id,user_id,verification_type,subject_id,reason[:5000],now,now))
            for item in evidence or []:
                raw=str(item.get("value",item.get("summary",""))); db.execute("INSERT INTO connect_verification_evidence(evidence_id,creator_id,verification_request_id,evidence_type,evidence_hash,redacted_summary,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'active','moderators',?,?)",(new_id("evidence"),user_id,rid,str(item.get("type","document"))[:80],_hash(raw),str(item.get("summary","Evidence supplied"))[:500],now,now))
        return {"verification_request_id":rid,"decision":"pending"}
    def decide(self,reviewer_id:str,request_id:str,decision:str,*,rejection_reason:str="",expires_at_utc:str|None=None)->dict[str,Any]:
        self._reviewer(reviewer_id)
        if decision not in {"approved","rejected","needs_information"}: raise ConnectError("Invalid verification decision.")
        now=utc_now()
        with self.repo.database.connection() as db:
            request=db.execute("SELECT * FROM connect_verification_requests WHERE verification_request_id=? AND state='pending'",(request_id,)).fetchone()
            if not request: raise NotFound("Pending verification request not found.")
            db.execute("UPDATE connect_verification_requests SET reviewer_id=?,decision=?,rejection_reason=?,decided_at_utc=?,state=?,updated_at_utc=?,version=version+1 WHERE verification_request_id=?",(reviewer_id,decision,rejection_reason[:2000],now,decision,now,request_id))
            if decision=="approved": db.execute("INSERT OR REPLACE INTO connect_verification_badges(badge_id,creator_id,user_id,badge_type,subject_id,issued_by_id,issued_at_utc,expires_at_utc,disclaimer,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,'active','public',?,?)",(new_id("badge"),reviewer_id,request["user_id"],request["verification_type"],request["subject_id"],reviewer_id,now,expires_at_utc,"Verification confirms reviewed evidence; it is not scientific endorsement.",now,now))
            updated=db.execute("SELECT * FROM connect_verification_requests WHERE verification_request_id=?",(request_id,)).fetchone()
        self.repo.notification(str(request["user_id"]),reviewer_id,f"verification_{decision}","verification",request_id,f"Verification request {decision}."); return dict(updated)
    def appeal(self,user_id:str,request_id:str,reason:str)->dict[str,Any]:
        with self.repo.database.connection() as db:
            row=db.execute("SELECT * FROM connect_verification_requests WHERE verification_request_id=? AND user_id=?",(request_id,user_id)).fetchone()
            if not row or row["decision"]!="rejected": raise PermissionDenied("Only a rejected verification may be appealed.")
            db.execute("UPDATE connect_verification_requests SET appeal_state='submitted',submitted_reason=?,state='pending',decision='pending',updated_at_utc=?,version=version+1 WHERE verification_request_id=?",(reason[:5000],utc_now(),request_id))
        return {"verification_request_id":request_id,"appeal_state":"submitted"}
    def _reviewer(self,user_id:str)->None:
        user=self.repo.user(user_id)
        if not user or user["role"] not in {"administrator","moderator","local_operator"}: raise PermissionDenied("Verification reviewer role required.")

class OnboardingService:
    TOTAL_STEPS=12
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo
    def progress(self,user_id:str)->dict[str,Any]:
        now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_onboarding_progress(onboarding_id,creator_id,user_id,current_step,completed_steps_json,skipped_steps_json,checklist_json,completion_percent,resumed_at_utc,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,1,'[]','[]','{}',0,?,'active','private',?,?) ON CONFLICT(user_id) DO UPDATE SET resumed_at_utc=excluded.resumed_at_utc,updated_at_utc=excluded.updated_at_utc""",(new_id("onboard"),user_id,user_id,now,now,now)); row=db.execute("SELECT * FROM connect_onboarding_progress WHERE user_id=?",(user_id,)).fetchone()
        result=dict(row); result["completed_steps"]=json.loads(result["completed_steps_json"]); result["skipped_steps"]=json.loads(result["skipped_steps_json"]); return result
    def update(self,user_id:str,step:int,*,completed:bool=True,skipped:bool=False,checklist:dict[str,Any]|None=None)->dict[str,Any]:
        if not 1<=step<=self.TOTAL_STEPS: raise ConnectError("Onboarding step is out of range.")
        current=self.progress(user_id); done=set(json.loads(current["completed_steps_json"])); skipped_steps=set(json.loads(current["skipped_steps_json"]))
        if completed: done.add(step); skipped_steps.discard(step)
        elif skipped: skipped_steps.add(step); done.discard(step)
        percent=round(len(done)/self.TOTAL_STEPS*100); next_step=next((n for n in range(1,self.TOTAL_STEPS+1) if n not in done and n not in skipped_steps),self.TOTAL_STEPS)
        merged=json.loads(current["checklist_json"]); merged.update(checklist or {})
        with self.repo.database.connection() as db:
            db.execute("UPDATE connect_onboarding_progress SET current_step=?,completed_steps_json=?,skipped_steps_json=?,checklist_json=?,completion_percent=?,state=?,updated_at_utc=?,version=version+1 WHERE user_id=?",(next_step,json.dumps(sorted(done)),json.dumps(sorted(skipped_steps)),json.dumps(merged),percent,"completed" if percent==100 else "active",utc_now(),user_id))
        return self.progress(user_id)
class NotificationDeliveryService:
    CATEGORIES={"connections","messages","communities","collaboration","publications","datasets","events","moderation","verification","system"}
    CHANNELS={"in_app","email","push"}
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo
    def preferences(self,user_id:str)->dict[str,Any]:
        now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_notification_preferences(preference_id,creator_id,user_id,categories_json,channels_json,quiet_hours_json,digest_frequency,private_preview_enabled,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,'{}','{\"in_app\": true, \"email\": true, \"push\": false}','{}','none',0,'active','private',?,?) ON CONFLICT(user_id) DO NOTHING""",(new_id("notifpref"),user_id,user_id,now,now)); row=db.execute("SELECT * FROM connect_notification_preferences WHERE user_id=?",(user_id,)).fetchone()
        return dict(row)
    def update_preferences(self,user_id:str,*,categories:dict[str,bool]|None=None,channels:dict[str,bool]|None=None,quiet_hours:dict[str,Any]|None=None,digest_frequency:str="none",private_preview_enabled:bool=False)->dict[str,Any]:
        if categories and set(categories)-self.CATEGORIES: raise ConnectError("Unsupported notification category.")
        if channels and set(channels)-self.CHANNELS: raise ConnectError("Unsupported notification channel.")
        if digest_frequency not in {"none","daily","weekly"}: raise ConnectError("Unsupported digest frequency.")
        self.preferences(user_id)
        with self.repo.database.connection() as db:
            db.execute("UPDATE connect_notification_preferences SET categories_json=?,channels_json=?,quiet_hours_json=?,digest_frequency=?,private_preview_enabled=?,updated_at_utc=?,version=version+1 WHERE user_id=?",(json.dumps(categories or {}),json.dumps(channels or {"in_app":True}),json.dumps(quiet_hours or {}),digest_frequency,int(private_preview_enabled),utc_now(),user_id)); row=db.execute("SELECT * FROM connect_notification_preferences WHERE user_id=?",(user_id,)).fetchone()
        return dict(row)
    def queue(self,recipient_id:str,category:str,subject_type:str,subject_id:str,message:str,*,actor_id:str|None=None,channels:list[str]|None=None,dedupe_key:str|None=None)->dict[str,Any]:
        if category not in self.CATEGORIES: raise ConnectError("Unsupported notification category.")
        pref=self.preferences(recipient_id); enabled=json.loads(pref["channels_json"]); channels=channels or [c for c,v in enabled.items() if v]
        notification_id=self.repo.notification(recipient_id,actor_id,category,subject_type,subject_id,message); now=utc_now(); created=[]
        with self.repo.database.connection() as db:
            for channel in dict.fromkeys(channels):
                if channel not in self.CHANNELS: continue
                key=f"{dedupe_key or notification_id}:{channel}"; private=bool(pref["private_preview_enabled"])
                preview=message[:240] if private else f"New {category.replace('_',' ')} activity in BioIntel Connect."
                db.execute("""INSERT OR IGNORE INTO connect_notification_deliveries(delivery_id,creator_id,notification_id,recipient_id,channel,category,dedupe_key,safe_preview,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,'queued','private',?,?)""",(new_id("delivery"),actor_id,notification_id,recipient_id,channel,category,key,preview,now,now)); row=db.execute("SELECT * FROM connect_notification_deliveries WHERE dedupe_key=?",(key,)).fetchone(); created.append(dict(row))
        return {"notification_id":notification_id,"deliveries":created}
    def deliver_due(self,limit:int=100)->dict[str,int]:
        now=utc_now(); delivered=failed=0
        with self.repo.database.connection() as db:
            rows=db.execute("SELECT * FROM connect_notification_deliveries WHERE state IN ('queued','retry') AND (next_attempt_at_utc IS NULL OR next_attempt_at_utc<=?) ORDER BY created_at_utc LIMIT ?",(now,min(max(limit,1),500))).fetchall()
            for row in rows:
                # Local adapters are deterministic: in-app is persisted; email/push are queued as simulated providers.
                if row["channel"] in self.CHANNELS:
                    db.execute("UPDATE connect_notification_deliveries SET state='delivered',attempt_count=attempt_count+1,delivered_at_utc=?,provider_message_id=?,updated_at_utc=?,version=version+1 WHERE delivery_id=?",(now,f"local:{row['delivery_id']}",now,row["delivery_id"])); delivered+=1
                else:
                    db.execute("UPDATE connect_notification_deliveries SET state='failed',failure_reason='unsupported_channel',attempt_count=attempt_count+1,updated_at_utc=?,version=version+1 WHERE delivery_id=?",(now,row["delivery_id"])); failed+=1
        return {"delivered":delivered,"failed":failed}
    def digest(self,recipient_id:str,frequency:str="daily")->dict[str,Any]:
        if frequency not in {"daily","weekly"}: raise ConnectError("Digest must be daily or weekly.")
        now=utc_now(); start=(datetime.now(UTC)-timedelta(days=1 if frequency=="daily" else 7)).isoformat(timespec="seconds")
        with self.repo.database.connection() as db:
            rows=db.execute("SELECT notification_id,message FROM connect_notifications WHERE recipient_id=? AND created_at_utc>=? ORDER BY created_at_utc DESC LIMIT 100",(recipient_id,start)).fetchall(); ids=[r["notification_id"] for r in rows]; did=new_id("digest"); preview=f"{len(ids)} BioIntel Connect updates in your {frequency} digest."
            db.execute("INSERT INTO connect_notification_digests(digest_id,creator_id,recipient_id,frequency,period_start_utc,period_end_utc,notification_ids_json,rendered_preview,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?, 'ready','private',?,?)",(did,recipient_id,recipient_id,frequency,start,now,json.dumps(ids),preview,now,now)); row=db.execute("SELECT * FROM connect_notification_digests WHERE digest_id=?",(did,)).fetchone()
        return dict(row)

class DraftSchedulerService:
    def __init__(self,repo:ConnectRepository,content:Any)->None: self.repo,self.content=repo,content
    def save(self,owner_id:str,*,body:str,title:str="",post_type:str="text",attachments:list[str]|None=None,settings:dict[str,Any]|None=None,draft_id:str|None=None,autosaved:bool=True)->dict[str,Any]:
        now=utc_now()
        with self.repo.database.connection() as db:
            if draft_id:
                current=db.execute("SELECT * FROM connect_post_drafts WHERE draft_id=? AND owner_id=?",(draft_id,owner_id)).fetchone()
                if not current: raise NotFound("Draft not found.")
                revision=db.execute("SELECT COALESCE(MAX(revision_number),0)+1 FROM connect_draft_revisions WHERE draft_id=?",(draft_id,)).fetchone()[0]
                db.execute("INSERT INTO connect_draft_revisions(draft_revision_id,creator_id,draft_id,revision_number,snapshot_json,autosaved,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'preserved','private',?,?)",(new_id("draftrev"),owner_id,draft_id,revision,json.dumps(dict(current)),int(autosaved),now,now)); db.execute("UPDATE connect_post_drafts SET title=?,body=?,post_type=?,attachments_json=?,settings_json=?,autosaved=?,updated_at_utc=?,version=version+1 WHERE draft_id=?",(title[:300],body[:50000],post_type,json.dumps(attachments or []),json.dumps(settings or {}),int(autosaved),now,draft_id))
            else:
                draft_id=new_id("draft"); db.execute("INSERT INTO connect_post_drafts(draft_id,creator_id,owner_id,post_type,title,body,attachments_json,settings_json,autosaved,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,'active','private',?,?)",(draft_id,owner_id,owner_id,post_type,title[:300],body[:50000],json.dumps(attachments or []),json.dumps(settings or {}),int(autosaved),now,now))
            row=db.execute("SELECT * FROM connect_post_drafts WHERE draft_id=?",(draft_id,)).fetchone()
        return dict(row)
    def schedule(self,owner_id:str,draft_id:str,scheduled_at_utc:str,*,timezone_name:str="UTC",schedule_type:str="post",target_id:str="")->dict[str,Any]:
        with self.repo.database.connection(read_only=True) as db: draft=db.execute("SELECT 1 FROM connect_post_drafts WHERE draft_id=? AND owner_id=? AND state='active'",(draft_id,owner_id)).fetchone()
        if not draft: raise NotFound("Active draft not found.")
        sid,now=new_id("scheduled"),utc_now()
        with self.repo.database.connection() as db: db.execute("INSERT INTO connect_scheduled_posts(scheduled_post_id,creator_id,owner_id,draft_id,schedule_type,target_id,scheduled_at_utc,timezone,publication_audit_status,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?, 'pending','scheduled','private',?,?)",(sid,owner_id,owner_id,draft_id,schedule_type,target_id,scheduled_at_utc,timezone_name,now,now)); row=db.execute("SELECT * FROM connect_scheduled_posts WHERE scheduled_post_id=?",(sid,)).fetchone()
        return dict(row)
    def publish_due(self,limit:int=50)->dict[str,int]:
        now=utc_now(); published=failed=0
        with self.repo.database.connection(read_only=True) as db: due=[dict(r) for r in db.execute("SELECT s.*,d.title,d.body,d.post_type,d.attachments_json,d.settings_json FROM connect_scheduled_posts s JOIN connect_post_drafts d ON d.draft_id=s.draft_id WHERE s.state IN ('scheduled','retry') AND s.scheduled_at_utc<=? AND (s.next_retry_at_utc IS NULL OR s.next_retry_at_utc<=?) ORDER BY s.scheduled_at_utc LIMIT ?",(now,now,min(max(limit,1),100)))]
        for item in due:
            try:
                settings=json.loads(item["settings_json"]); post=self.content.create_post(item["owner_id"],body=item["body"],title=item["title"],post_type=item["post_type"],visibility=settings.get("visibility","public"),media_ids=json.loads(item["attachments_json"]),community_id=settings.get("community_id",""),project_id=settings.get("project_id",""))
                with self.repo.database.connection() as db: db.execute("UPDATE connect_scheduled_posts SET state='published',published_post_id=?,publication_audit_status='published',updated_at_utc=?,version=version+1 WHERE scheduled_post_id=?",(post["post_id"],utc_now(),item["scheduled_post_id"])); db.execute("UPDATE connect_post_drafts SET state='published',updated_at_utc=? WHERE draft_id=?",(utc_now(),item["draft_id"]))
                published+=1
            except Exception as exc:
                attempts=int(item["attempt_count"])+1; retry=(datetime.now(UTC)+timedelta(minutes=min(60,2**min(attempts,5)))).isoformat(timespec="seconds")
                with self.repo.database.connection() as db: db.execute("UPDATE connect_scheduled_posts SET state=?,attempt_count=?,last_error=?,next_retry_at_utc=?,publication_audit_status='failed',updated_at_utc=?,version=version+1 WHERE scheduled_post_id=?",("failed" if attempts>=5 else "retry",attempts,str(exc)[:1000],retry,utc_now(),item["scheduled_post_id"]))
                failed+=1
        return {"published":published,"failed":failed}
class LifecycleService:
    """Owner-controlled post editing, revisions, archiving, restoration and deletion requests."""
    def __init__(self,repo:ConnectRepository,content:Any)->None: self.repo,self.content=repo,content
    def edit_post(self,actor:str,post_id:str,*,title:str|None=None,body:str|None=None)->dict[str,Any]:
        post=self.repo.post(post_id)
        if not post: raise NotFound("Post not found.")
        if post["author_id"]!=actor: raise PermissionDenied("Only the author may edit a post.")
        if post["state"] not in {"published","archived"}: raise Conflict("Post cannot be edited in its current state.")
        now=utc_now(); version=int(post["version"])
        with self.repo.database.connection() as db:
            db.execute("INSERT INTO connect_post_revisions(revision_id,post_id,editor_id,title,body,version,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'preserved','private',?,?)",(new_id("postrev"),post_id,actor,post["title"],post["body"],version,now,now)); db.execute("UPDATE connect_posts SET title=?,body=?,updated_at_utc=?,version=version+1 WHERE post_id=?",((title if title is not None else post["title"])[:300],(body if body is not None else post["body"])[:50000],now,post_id))
        self.repo.audit(actor,"post_edited","post",post_id,{"previous_version":version}); return self.content.get_post(actor,post_id)
    def versions(self,viewer:str,post_id:str)->list[dict[str,Any]]:
        post=self.content.get_post(viewer,post_id)
        if viewer!=post["author_id"]:
            user=self.repo.user(viewer)
            if not user or user["role"] not in {"administrator","moderator","local_operator"}: raise PermissionDenied("Post version history is private to the author and moderators.")
        with self.repo.database.connection(read_only=True) as db: return [dict(r) for r in db.execute("SELECT * FROM connect_post_revisions WHERE post_id=? ORDER BY version DESC",(post_id,))]
    def set_state(self,actor:str,post_id:str,state:str)->dict[str,Any]:
        if state not in {"archived","published","deleted"}: raise ConnectError("Unsupported lifecycle state.")
        post=self.repo.post(post_id)
        if not post: raise NotFound("Post not found.")
        if post["author_id"]!=actor: raise PermissionDenied("Only the author may change post lifecycle.")
        now=utc_now()
        with self.repo.database.connection() as db: db.execute("UPDATE connect_posts SET state=?,deleted_at_utc=CASE WHEN ?='deleted' THEN ? ELSE NULL END,updated_at_utc=?,version=version+1 WHERE post_id=?",(state,state,now,now,post_id)); row=db.execute("SELECT * FROM connect_posts WHERE post_id=?",(post_id,)).fetchone()
        self.repo.audit(actor,f"post_{state}","post",post_id); return dict(row)
    def request_account_deletion(self,user_id:str,*,export_requested:bool=True,grace_days:int=30)->dict[str,Any]:
        rid,now=new_id("delete"),utc_now(); scheduled=(datetime.now(UTC)+timedelta(days=max(1,min(grace_days,90)))).isoformat(timespec="seconds")
        with self.repo.database.connection() as db: db.execute("INSERT INTO connect_account_deletion_requests(deletion_request_id,creator_id,user_id,requested_at_utc,scheduled_for_utc,export_requested,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'scheduled','private',?,?)",(rid,user_id,user_id,now,scheduled,int(export_requested),now,now)); row=db.execute("SELECT * FROM connect_account_deletion_requests WHERE deletion_request_id=?",(rid,)).fetchone()
        return dict(row)
    def cancel_account_deletion(self,user_id:str,request_id:str)->dict[str,Any]:
        now=utc_now()
        with self.repo.database.connection() as db:
            row=db.execute("SELECT * FROM connect_account_deletion_requests WHERE deletion_request_id=? AND user_id=? AND state='scheduled'",(request_id,user_id)).fetchone()
            if not row: raise NotFound("Scheduled deletion request not found.")
            db.execute("UPDATE connect_account_deletion_requests SET state='cancelled',cancelled_at_utc=?,updated_at_utc=?,version=version+1 WHERE deletion_request_id=?",(now,now,request_id)); updated=db.execute("SELECT * FROM connect_account_deletion_requests WHERE deletion_request_id=?",(request_id,)).fetchone()
        return dict(updated)

