from __future__ import annotations

import hashlib, json, os, shutil, sqlite3, tempfile, zipfile
from pathlib import Path
from typing import Any
from cryptography.fernet import Fernet, InvalidToken
from biointel.database.core import utc_now
from .repositories import ConnectRepository, new_id
from .services import ConnectError, NotFound, PermissionDenied

class AccessibilityService:
    LANGUAGES={"English","Hindi","Hinglish"}
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo
    def preferences(self,user_id:str)->dict[str,Any]:
        now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_accessibility_preferences(accessibility_preference_id,creator_id,user_id,language,high_contrast,reduced_motion,data_saving,captions_enabled,autoplay_audio,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,'English',0,0,0,1,0,'active','private',?,?) ON CONFLICT(user_id) DO NOTHING""",(new_id("access"),user_id,user_id,now,now)); row=db.execute("SELECT * FROM connect_accessibility_preferences WHERE user_id=?",(user_id,)).fetchone()
        return dict(row)
    def update(self,user_id:str,*,language:str="English",high_contrast:bool=False,reduced_motion:bool=False,data_saving:bool=False,captions_enabled:bool=True,autoplay_audio:bool=False)->dict[str,Any]:
        if language not in self.LANGUAGES: raise ConnectError("Language must be English, Hindi or Hinglish.")
        if autoplay_audio: raise ConnectError("Autoplay audio stays disabled for accessibility and user control.")
        self.preferences(user_id)
        with self.repo.database.connection() as db:
            db.execute("UPDATE connect_accessibility_preferences SET language=?,high_contrast=?,reduced_motion=?,data_saving=?,captions_enabled=?,autoplay_audio=0,updated_at_utc=?,version=version+1 WHERE user_id=?",(language,int(high_contrast),int(reduced_motion),int(data_saving),int(captions_enabled),utc_now(),user_id)); db.execute("UPDATE connect_profiles SET preferred_language=?,updated_at_utc=?,version=version+1 WHERE user_id=?",(language,utc_now(),user_id)); row=db.execute("SELECT * FROM connect_accessibility_preferences WHERE user_id=?",(user_id,)).fetchone()
        return dict(row)

class AdminService:
    ROLES={"administrator","moderator","local_operator"}
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo
    def require(self,user_id:str,moderator_ok:bool=True)->dict[str,Any]:
        user=self.repo.user(user_id)
        allowed=self.ROLES if moderator_ok else {"administrator","local_operator"}
        if not user or user["role"] not in allowed: raise PermissionDenied("Administrative role required.")
        return user
    def dashboard(self,actor:str)->dict[str,Any]:
        self.require(actor)
        with self.repo.database.connection(read_only=True) as db:
            count=lambda table,where="1=1": int(db.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0])
            return {"users":count("connect_users","state='active'"),"open_reports":count("connect_moderation_cases","state='open'"),"pending_verifications":count("connect_verification_requests","state='pending'"),"queued_deliveries":count("connect_notification_deliveries","state IN ('queued','retry')"),"scheduled_posts":count("connect_scheduled_posts","state IN ('scheduled','retry')"),"active_communities":count("connect_communities","state='active'"),"health_alerts":count("connect_service_health_events","alert_state='open'"),"generated_at_utc":utc_now()}
    def cases(self,actor:str,state:str="open",limit:int=100)->list[dict[str,Any]]:
        self.require(actor)
        with self.repo.database.connection(read_only=True) as db: return [dict(r) for r in db.execute("SELECT c.*,r.target_type,r.target_id,r.reason,r.detail FROM connect_moderation_cases c JOIN connect_content_reports r ON r.report_id=c.report_id WHERE c.state=? ORDER BY c.created_at_utc LIMIT ?",(state,min(max(limit,1),250)))]
    def decide_case(self,actor:str,case_id:str,*,action:str,resolution:str,duration_seconds:int|None=None)->dict[str,Any]:
        self.require(actor)
        if action not in {"no_action","warning","content_hidden","content_removed","account_restricted","account_suspended","account_disabled"}: raise ConnectError("Unsupported moderation action.")
        now=utc_now()
        with self.repo.database.connection() as db:
            case=db.execute("SELECT c.*,r.target_type,r.target_id FROM connect_moderation_cases c JOIN connect_content_reports r ON r.report_id=c.report_id WHERE c.case_id=?",(case_id,)).fetchone()
            if not case: raise NotFound("Moderation case not found.")
            db.execute("UPDATE connect_moderation_cases SET assigned_moderator_id=?,action=?,resolution=?,state='resolved',updated_at_utc=?,version=version+1 WHERE case_id=?",(actor,action,resolution[:5000],now,case_id))
            db.execute("INSERT INTO connect_administrative_actions(administrative_action_id,creator_id,administrator_id,action_type,target_type,target_id,reason,duration_seconds,effective_at_utc,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,'active','administrators',?,?)",(new_id("adminaction"),actor,actor,action,case["target_type"],case["target_id"],resolution[:5000],duration_seconds,now,now,now)); row=db.execute("SELECT * FROM connect_moderation_cases WHERE case_id=?",(case_id,)).fetchone()
        self.repo.audit(actor,"moderation_case_resolved","moderation_case",case_id,{"action":action}); return dict(row)
    def appeal(self,user_id:str,case_id:str,reason:str,evidence:dict[str,Any]|None=None)->dict[str,Any]:
        aid,now=new_id("appeal"),utc_now()
        with self.repo.database.connection() as db:
            case=db.execute("SELECT 1 FROM connect_moderation_cases WHERE case_id=? AND state='resolved'",(case_id,)).fetchone()
            if not case: raise NotFound("Resolved moderation case not found.")
            db.execute("INSERT INTO connect_moderation_appeals(appeal_id,creator_id,case_id,appellant_id,reason,evidence_json,decision,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'pending','pending','moderators',?,?)",(aid,user_id,case_id,user_id,reason[:5000],json.dumps(evidence or {}),now,now)); row=db.execute("SELECT * FROM connect_moderation_appeals WHERE appeal_id=?",(aid,)).fetchone()
        return dict(row)
    def decide_appeal(self,actor:str,appeal_id:str,decision:str,resolution:str)->dict[str,Any]:
        self.require(actor)
        if decision not in {"upheld","overturned","modified"}: raise ConnectError("Invalid appeal decision.")
        with self.repo.database.connection() as db:
            row=db.execute("SELECT * FROM connect_moderation_appeals WHERE appeal_id=? AND state='pending'",(appeal_id,)).fetchone()
            if not row: raise NotFound("Pending appeal not found.")
            db.execute("UPDATE connect_moderation_appeals SET reviewer_id=?,decision=?,resolution=?,state='resolved',updated_at_utc=?,version=version+1 WHERE appeal_id=?",(actor,decision,resolution[:5000],utc_now(),appeal_id)); updated=db.execute("SELECT * FROM connect_moderation_appeals WHERE appeal_id=?",(appeal_id,)).fetchone()
        return dict(updated)
    def legal_hold(self,actor:str,target_type:str,target_id:str,reason:str,starts_at_utc:str,ends_at_utc:str|None=None)->dict[str,Any]:
        self.require(actor,False); hid,now=new_id("hold"),utc_now()
        with self.repo.database.connection() as db: db.execute("INSERT INTO connect_legal_holds(legal_hold_id,creator_id,administrator_id,target_type,target_id,reason,starts_at_utc,ends_at_utc,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,'active','administrators',?,?)",(hid,actor,actor,target_type,target_id,reason[:5000],starts_at_utc,ends_at_utc,now,now)); row=db.execute("SELECT * FROM connect_legal_holds WHERE legal_hold_id=?",(hid,)).fetchone()
        return dict(row)
class OperationsService:
    """Encrypted backups, restore drills, health/capacity events and safe cleanup previews."""
    def __init__(self,repo:ConnectRepository,storage_root:str|Path,admin:AdminService)->None:
        self.repo,self.database,self.storage_root,self.admin=repo,repo.database,Path(storage_root).resolve(),admin
        self.backup_root=self.storage_root.parent/"backups"; self.backup_root.mkdir(parents=True,exist_ok=True)
    def _fernet(self)->Fernet:
        configured=os.environ.get("BIOINTEL_CONNECT_BACKUP_KEY","").encode()
        key_path=self.backup_root/".backup.key"
        if configured:
            key=configured
        elif key_path.is_file(): key=key_path.read_bytes().strip()
        else:
            key=Fernet.generate_key(); key_path.write_bytes(key)
        return Fernet(key)
    def create_backup(self,actor:str|None=None,backup_type:str="full")->dict[str,Any]:
        if actor: self.admin.require(actor,False)
        backup_id,now=new_id("backup"),utc_now(); target=self.backup_root/f"{backup_id}.biobak"
        snapshot_path:Path|None=None; zip_path:Path|None=None
        try:
            with tempfile.TemporaryDirectory(prefix="biointel_backup_") as tmp:
                tmp_root=Path(tmp); snapshot_path=tmp_root/"connect.sqlite3"; zip_path=tmp_root/"snapshot.zip"
                source=sqlite3.connect(str(self.database.path)); dest=sqlite3.connect(str(snapshot_path))
                try: source.backup(dest)
                finally: dest.close(); source.close()
                with zipfile.ZipFile(zip_path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
                    archive.write(snapshot_path,"database/connect.sqlite3")
                    if backup_type=="full" and self.storage_root.exists():
                        for path in self.storage_root.rglob("*"):
                            if path.is_file() and self.backup_root not in path.parents: archive.write(path,"media/"+path.relative_to(self.storage_root).as_posix())
                    archive.writestr("manifest.json",json.dumps({"backup_id":backup_id,"created_at_utc":now,"backup_type":backup_type,"database":str(self.database.path),"encrypted":True},indent=2))
                target.write_bytes(self._fernet().encrypt(zip_path.read_bytes()))
            checksum=hashlib.sha256(target.read_bytes()).hexdigest(); size=target.stat().st_size
            with self.database.connection() as db:
                db.execute("INSERT INTO connect_backup_records(backup_id,creator_id,administrator_id,backup_type,storage_path,checksum,encrypted,validated_at_utc,size_bytes,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,1,?,?,'created','administrators',?,?)",(backup_id,actor,actor,backup_type,str(target),checksum,now,size,now,now)); row=db.execute("SELECT * FROM connect_backup_records WHERE backup_id=?",(backup_id,)).fetchone()
            return dict(row)
        except Exception as exc:
            if target.exists(): target.unlink()
            with self.database.connection() as db: db.execute("INSERT INTO connect_backup_records(backup_id,creator_id,administrator_id,backup_type,storage_path,encrypted,failure_reason,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,1,?,'failed','administrators',?,?)",(backup_id,actor,actor,backup_type,str(target),str(exc)[:2000],now,now))
            raise
    def validate_restore(self,actor:str|None,backup_id:str)->dict[str,Any]:
        if actor: self.admin.require(actor,False)
        with self.database.connection(read_only=True) as db: record=db.execute("SELECT * FROM connect_backup_records WHERE backup_id=?",(backup_id,)).fetchone()
        if not record: raise NotFound("Backup record not found.")
        target=Path(record["storage_path"])
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=record["checksum"]: raise ConnectError("Backup checksum validation failed.")
        try: plaintext=self._fernet().decrypt(target.read_bytes())
        except InvalidToken as exc: raise ConnectError("Backup encryption key is invalid.") from exc
        with tempfile.TemporaryDirectory(prefix="biointel_restore_") as tmp:
            archive_path=Path(tmp)/"restore.zip"; archive_path.write_bytes(plaintext)
            with zipfile.ZipFile(archive_path) as archive:
                if archive.testzip() is not None: raise ConnectError("Backup archive CRC validation failed.")
                names=archive.namelist()
                if "database/connect.sqlite3" not in names: raise ConnectError("Backup database is missing.")
                for name in names:
                    normalized=Path(name)
                    if normalized.is_absolute() or ".." in normalized.parts: raise ConnectError("Unsafe backup path detected.")
                archive.extract("database/connect.sqlite3",tmp)
            restored=sqlite3.connect(str(Path(tmp)/"database"/"connect.sqlite3"))
            try:
                integrity=restored.execute("PRAGMA integrity_check").fetchone()[0]
                migration_count=restored.execute("SELECT COUNT(*) FROM connect_schema_migrations").fetchone()[0]
            finally: restored.close()
        if integrity!="ok": raise ConnectError(f"Restored database integrity failed: {integrity}")
        now=utc_now()
        with self.database.connection() as db: db.execute("UPDATE connect_backup_records SET state='restore_tested',validated_at_utc=?,restore_tested_at_utc=?,updated_at_utc=?,version=version+1 WHERE backup_id=?",(now,now,now,backup_id)); updated=db.execute("SELECT * FROM connect_backup_records WHERE backup_id=?",(backup_id,)).fetchone()
        result=dict(updated); result["integrity_check"]=integrity; result["migration_count"]=migration_count; result["production_database_untouched"]=True; return result
    def health(self,service_name:str="connect")->dict[str,Any]:
        """Return server-derived health without writing a health row or trusting caller metrics."""
        checked=utc_now(); errors=[]
        try:
            with self.database.connection(read_only=True) as db:
                integrity=str(db.execute("PRAGMA quick_check").fetchone()[0]); migrations=int(db.execute("SELECT COUNT(*) FROM connect_schema_migrations").fetchone()[0])
        except Exception as exc:
            integrity="unavailable"; migrations=0; errors.append(type(exc).__name__)
        try:
            usage=shutil.disk_usage(self.storage_root); disk={"total_bytes":usage.total,"free_bytes":usage.free,"used_percent":round(usage.used*100/usage.total,2) if usage.total else None}
            if usage.free<1024**3: errors.append("low_disk_space")
        except OSError:
            disk={"total_bytes":None,"free_bytes":None,"used_percent":None}; errors.append("disk_status_unavailable")
        status="healthy" if integrity=="ok" and not errors else "degraded" if integrity=="ok" else "unhealthy"
        return {"service_name":service_name,"status":status,"ready":status!="unhealthy","live":True,"database":{"integrity":integrity,"migration_count":migrations},"storage":disk,"queue":{"delivery_pending":self._count_pending_deliveries()},"errors":errors,"checked_at_utc":checked,"source":"server_derived","persisted_health_event":False}
    def _count_pending_deliveries(self)->int:
        try:
            with self.database.connection(read_only=True) as db: return int(db.execute("SELECT COUNT(*) FROM connect_notification_deliveries WHERE state IN ('queued','retry')").fetchone()[0])
        except Exception: return -1
    def rate_limit_event(self,user_id:str|None,route_key:str,request_count:int,limited:bool,window_start_utc:str|None=None)->dict[str,Any]:
        rid,now=new_id("ratelimit"),utc_now()
        with self.database.connection() as db: db.execute("INSERT INTO connect_rate_limit_events(rate_limit_event_id,creator_id,user_id,route_key,window_start_utc,request_count,limited,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'recorded','administrators',?,?)",(rid,user_id,user_id,route_key,window_start_utc or now,request_count,int(limited),now,now)); row=db.execute("SELECT * FROM connect_rate_limit_events WHERE rate_limit_event_id=?",(rid,)).fetchone()
        return dict(row)
    def cleanup(self,actor:str,cleanup_type:str="expired_stories",dry_run:bool=True)->dict[str,Any]:
        self.admin.require(actor,False)
        if cleanup_type not in {"expired_stories","expired_signals","deleted_media"}: raise ConnectError("Unsupported cleanup type.")
        now=utc_now(); queries={"expired_stories":("connect_stories","expires_at_utc<?","expired"),"expired_signals":("connect_call_signals","expires_at_utc<?","expired"),"deleted_media":("connect_media_objects","state='deleted'","deleted")}; table,where,new_state=queries[cleanup_type]
        with self.database.connection() as db:
            params=(now,) if "?" in where else (); count=db.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}",params).fetchone()[0]
            if not dry_run: db.execute(f"UPDATE {table} SET state=?,updated_at_utc=?,version=version+1 WHERE {where}",(new_state,now,*params))
            cid=new_id("cleanup"); db.execute("INSERT INTO connect_content_cleanup_events(cleanup_event_id,creator_id,administrator_id,cleanup_type,target_count,freed_bytes,detail_json,dry_run,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,0,?,?, 'recorded','administrators',?,?)",(cid,actor,actor,cleanup_type,count,json.dumps({"table":table}),int(dry_run),now,now)); row=db.execute("SELECT * FROM connect_content_cleanup_events WHERE cleanup_event_id=?",(cid,)).fetchone()
        return dict(row)


