from __future__ import annotations

import hashlib, json, os, secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from biointel.database.core import utc_now
from .repositories import ConnectRepository, new_id
from .services import Conflict, ConnectError, NotFound, PermissionDenied

UTC=timezone.utc
def _future(hours:int)->str: return (datetime.now(UTC)+timedelta(hours=hours)).isoformat(timespec="seconds")
def _expired(value:str)->bool:
    try: return datetime.fromisoformat(value.replace("Z","+00:00"))<=datetime.now(UTC)
    except ValueError: return True

class StoryService:
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo
    def _get(self,story_id:str)->dict[str,Any]:
        with self.repo.database.connection(read_only=True) as db: row=db.execute("SELECT * FROM connect_stories WHERE story_id=? AND deleted_at_utc IS NULL",(story_id,)).fetchone()
        if not row: raise NotFound("Story not found.")
        return dict(row)
    def can_view(self,viewer:str,story:dict[str,Any])->bool:
        if story["state"]!="active" or _expired(story["expires_at_utc"]): return False
        author=str(story["author_id"])
        if viewer==author: return True
        if self.repo.blocked(viewer,author): return False
        visibility=str(story["visibility"])
        if visibility=="public": return True
        if visibility in {"connections","followers"}: return self.repo.connected(viewer,author) if visibility=="connections" else self.repo.follows(viewer,author)
        if visibility=="community_members":
            with self.repo.database.connection(read_only=True) as db: return bool(db.execute("SELECT 1 FROM connect_community_members WHERE community_id=? AND user_id=? AND state='active'",(story["owner_id"],viewer)).fetchone())
        return False
    def create(self,actor:str,*,story_type:str,text_body:str="",media_id:str|None=None,poll:dict[str,Any]|None=None,alt_text:str="",mentions:list[str]|None=None,visibility:str="connections",reply_permission:str="connections",warning_text:str="",owner_type:str="user",owner_id:str|None=None,hours:int=24)->dict[str,Any]:
        if story_type not in {"text","image","video","poll","link","research_update"}: raise ConnectError("Unsupported story type.")
        if not text_body.strip() and not media_id and not poll: raise ConnectError("Story content is required.")
        if media_id and story_type in {"image","video"} and not alt_text.strip(): raise ConnectError("Alt text is required for story media.")
        sid,now=new_id("story"),utc_now()
        with self.repo.database.connection() as db:
            if media_id and not db.execute("SELECT 1 FROM connect_media_objects WHERE media_id=? AND owner_id=? AND state='available'",(media_id,actor)).fetchone(): raise PermissionDenied("Story media is unavailable.")
            db.execute("""INSERT INTO connect_stories(story_id,creator_id,owner_type,owner_id,author_id,story_type,text_body,media_id,poll_json,alt_text,mentions_json,expires_at_utc,reply_permission,warning_text,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",(sid,actor,owner_type,owner_id or actor,actor,story_type,text_body[:5000],media_id,json.dumps(poll or {}),alt_text[:1000],json.dumps(mentions or []),_future(max(1,min(hours,168))),reply_permission,warning_text[:1000],visibility,now,now))
        self.repo.audit(actor,"story_created","story",sid,{"expires_in_hours":hours}); return self.get(actor,sid)
    def get(self,viewer:str,story_id:str)->dict[str,Any]:
        row=self._get(story_id)
        if not self.can_view(viewer,row): raise PermissionDenied("Story is unavailable or not visible.")
        return row
    def feed(self,viewer:str,limit:int=100)->list[dict[str,Any]]:
        with self.repo.database.connection(read_only=True) as db: rows=[dict(r) for r in db.execute("SELECT * FROM connect_stories WHERE state='active' AND deleted_at_utc IS NULL AND expires_at_utc>? ORDER BY created_at_utc DESC LIMIT ?",(utc_now(),min(max(limit,1),200)))]
        return [r for r in rows if self.can_view(viewer,r)]
    def view(self,viewer:str,story_id:str)->dict[str,Any]:
        story=self.get(viewer,story_id); now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_story_views(story_view_id,creator_id,story_id,viewer_id,viewed_at_utc,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,'active','private',?,?) ON CONFLICT(story_id,viewer_id) DO UPDATE SET viewed_at_utc=excluded.viewed_at_utc,updated_at_utc=excluded.updated_at_utc""",(new_id("storyview"),viewer,story_id,viewer,now,now,now)); count=db.execute("SELECT COUNT(*) FROM connect_story_views WHERE story_id=?",(story_id,)).fetchone()[0]
        return {"story_id":story_id,"viewed_at_utc":now,"viewer_count":count,"owner_notified":story["author_id"]!=viewer}
    def react(self,user_id:str,story_id:str,reaction_type:str,reply_text:str="")->dict[str,Any]:
        story=self.get(user_id,story_id)
        if reply_text and story["reply_permission"]=="none": raise PermissionDenied("Story replies are disabled.")
        now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_story_reactions(story_reaction_id,creator_id,story_id,user_id,reaction_type,reply_text,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'active','private',?,?) ON CONFLICT(story_id,user_id) DO UPDATE SET reaction_type=excluded.reaction_type,reply_text=excluded.reply_text,updated_at_utc=excluded.updated_at_utc""",(new_id("storyreact"),user_id,story_id,user_id,reaction_type[:40],reply_text[:2000],now,now)); row=db.execute("SELECT * FROM connect_story_reactions WHERE story_id=? AND user_id=?",(story_id,user_id)).fetchone()
        return dict(row)
    def highlight(self,owner_id:str,title:str,story_ids:list[str])->dict[str,Any]:
        valid=[]
        for sid in dict.fromkeys(story_ids):
            story=self._get(sid)
            if story["author_id"]!=owner_id: raise PermissionDenied("Only your stories may be highlighted.")
            valid.append(sid)
        hid,now=new_id("highlight"),utc_now()
        with self.repo.database.connection() as db:
            db.execute("INSERT INTO connect_story_highlights(highlight_id,creator_id,owner_id,title,story_ids_json,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,'active','public',?,?)",(hid,owner_id,owner_id,title[:120],json.dumps(valid),now,now)); row=db.execute("SELECT * FROM connect_story_highlights WHERE highlight_id=?",(hid,)).fetchone()
        return dict(row)

class ShortVideoService:
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo
    def create(self,actor:str,*,media_id:str,caption:str="",transcript:str="",alt_text:str="",hashtags:list[str]|None=None,research_topics:list[str]|None=None,warning_text:str="",visibility:str="public",comments_enabled:bool=True)->dict[str,Any]:
        if not transcript.strip() or not alt_text.strip(): raise ConnectError("Transcript and alt text are required for short video accessibility.")
        vid,now=new_id("short"),utc_now()
        with self.repo.database.connection() as db:
            media=db.execute("SELECT * FROM connect_media_objects WHERE media_id=? AND owner_id=? AND state='available'",(media_id,actor)).fetchone()
            if not media or not str(media["mime_type"]).startswith("video/"): raise ConnectError("An available video upload is required.")
            db.execute("""INSERT INTO connect_short_videos(short_video_id,creator_id,author_id,media_id,caption,transcript,alt_text,hashtags_json,research_topics_json,warning_text,comments_enabled,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",(vid,actor,actor,media_id,caption[:5000],transcript[:50000],alt_text[:2000],json.dumps(hashtags or []),json.dumps(research_topics or []),warning_text[:1000],int(comments_enabled),visibility,now,now))
            row=db.execute("SELECT * FROM connect_short_videos WHERE short_video_id=?",(vid,)).fetchone()
        return dict(row)
    def feed(self,viewer:str,limit:int=50)->list[dict[str,Any]]:
        with self.repo.database.connection(read_only=True) as db: rows=[dict(r) for r in db.execute("SELECT * FROM connect_short_videos WHERE state='active' AND deleted_at_utc IS NULL ORDER BY created_at_utc DESC LIMIT ?",(min(max(limit,1),100),))]
        return [r for r in rows if r["author_id"]==viewer or (r["visibility"]=="public" and not self.repo.blocked(viewer,r["author_id"]))]
    def comment(self,actor:str,short_video_id:str,body:str,parent_comment_id:str|None=None)->dict[str,Any]:
        with self.repo.database.connection() as db:
            video=db.execute("SELECT * FROM connect_short_videos WHERE short_video_id=? AND state='active'",(short_video_id,)).fetchone()
            if not video: raise NotFound("Short video not found.")
            if not video["comments_enabled"]: raise PermissionDenied("Comments are disabled.")
            cid,now=new_id("shortcmt"),utc_now(); db.execute("INSERT INTO connect_short_video_comments(comment_id,creator_id,short_video_id,author_id,body,parent_comment_id,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'active','public',?,?)",(cid,actor,short_video_id,actor,body[:5000],parent_comment_id,now,now)); row=db.execute("SELECT * FROM connect_short_video_comments WHERE comment_id=?",(cid,)).fetchone()
        return dict(row)
class LiveStreamService:
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo
    def _get(self,stream_id:str)->dict[str,Any]:
        with self.repo.database.connection(read_only=True) as db: row=db.execute("SELECT * FROM connect_live_streams WHERE live_stream_id=? AND deleted_at_utc IS NULL",(stream_id,)).fetchone()
        if not row: raise NotFound("Live stream not found.")
        return dict(row)
    def create(self,host_id:str,*,stream_type:str,title:str,description:str="",scheduled_at_utc:str|None=None,quality:str="auto",recording_enabled:bool=False,visibility:str="public",owner_type:str="user",owner_id:str|None=None)->dict[str,Any]:
        if stream_type not in {"webinar","lab_meeting","journal_club","conference","ask_an_expert","community_live"}: raise ConnectError("Unsupported stream type.")
        sid,now=new_id("live"),utc_now(); state="scheduled" if scheduled_at_utc else "ready"
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_live_streams(live_stream_id,creator_id,host_id,owner_type,owner_id,stream_type,title,description,scheduled_at_utc,quality,recording_enabled,recording_consent_required,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)""",(sid,host_id,host_id,owner_type,owner_id or host_id,stream_type,title[:300],description[:10000],scheduled_at_utc,quality,int(recording_enabled),state,visibility,now,now)); row=db.execute("SELECT * FROM connect_live_streams WHERE live_stream_id=?",(sid,)).fetchone()
        return dict(row)
    def start(self,actor:str,stream_id:str)->dict[str,Any]:
        stream=self._get(stream_id)
        if stream["host_id"]!=actor: raise PermissionDenied("Only host may start stream.")
        if stream["state"] not in {"ready","scheduled","paused"}: raise Conflict("Stream cannot be started from its current state.")
        with self.repo.database.connection() as db: db.execute("UPDATE connect_live_streams SET state='live',started_at_utc=COALESCE(started_at_utc,?),updated_at_utc=?,version=version+1 WHERE live_stream_id=?",(utc_now(),utc_now(),stream_id)); row=db.execute("SELECT * FROM connect_live_streams WHERE live_stream_id=?",(stream_id,)).fetchone()
        return dict(row)
    def join(self,user_id:str,stream_id:str,*,recording_consent:bool=False,role:str="viewer")->dict[str,Any]:
        stream=self._get(stream_id)
        if stream["state"] not in {"live","ready","scheduled"}: raise Conflict("Stream is unavailable.")
        if stream["visibility"]!="public" and user_id!=stream["host_id"]: raise PermissionDenied("Stream is private.")
        if stream["recording_enabled"] and stream["recording_consent_required"] and not recording_consent: raise PermissionDenied("Recording consent is required before joining.")
        now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_live_stream_participants(participant_id,creator_id,live_stream_id,user_id,role,joined_at_utc,recording_consent,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'active','private',?,?) ON CONFLICT(live_stream_id,user_id) DO UPDATE SET role=excluded.role,joined_at_utc=excluded.joined_at_utc,left_at_utc=NULL,recording_consent=excluded.recording_consent,state='active',updated_at_utc=excluded.updated_at_utc""",(new_id("livepart"),user_id,stream_id,user_id,role,now,int(recording_consent),now,now)); row=db.execute("SELECT * FROM connect_live_stream_participants WHERE live_stream_id=? AND user_id=?",(stream_id,user_id)).fetchone()
        return dict(row)
    def comment(self,actor:str,stream_id:str,body:str,comment_type:str="comment")->dict[str,Any]:
        stream=self._get(stream_id)
        if stream["state"]!="live": raise Conflict("Comments require a live stream.")
        cid,now=new_id("livecmt"),utc_now()
        with self.repo.database.connection() as db: db.execute("INSERT INTO connect_live_stream_comments(comment_id,creator_id,live_stream_id,author_id,body,comment_type,moderation_state,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'visible','active','public',?,?)",(cid,actor,stream_id,actor,body[:3000],comment_type,now,now)); row=db.execute("SELECT * FROM connect_live_stream_comments WHERE comment_id=?",(cid,)).fetchone()
        return dict(row)
    def moderate(self,actor:str,stream_id:str,*,participant_id:str|None=None,comment_id:str|None=None,action:str)->dict[str,Any]:
        stream=self._get(stream_id)
        if stream["host_id"]!=actor: raise PermissionDenied("Host moderation role required.")
        with self.repo.database.connection() as db:
            if comment_id and action in {"hide","delete"}: db.execute("UPDATE connect_live_stream_comments SET moderation_state=?,updated_at_utc=?,version=version+1 WHERE live_stream_id=? AND comment_id=?",(action,utc_now(),stream_id,comment_id))
            elif participant_id and action in {"mute","remove"}: db.execute("UPDATE connect_live_stream_participants SET muted=?,state=?,left_at_utc=CASE WHEN ?='remove' THEN ? ELSE left_at_utc END,updated_at_utc=?,version=version+1 WHERE live_stream_id=? AND participant_id=?",(1 if action=="mute" else 0,"removed" if action=="remove" else "active",action,utc_now(),utc_now(),stream_id,participant_id))
            else: raise ConnectError("Unsupported moderation action.")
        self.repo.audit(actor,"live_moderation", "live_stream",stream_id,{"action":action}); return {"live_stream_id":stream_id,"action":action,"completed":True}
    def end(self,actor:str,stream_id:str,emergency_reason:str="")->dict[str,Any]:
        stream=self._get(stream_id)
        if stream["host_id"]!=actor: raise PermissionDenied("Only host may end stream.")
        with self.repo.database.connection() as db: db.execute("UPDATE connect_live_streams SET state='ended',ended_at_utc=?,emergency_reason=?,updated_at_utc=?,version=version+1 WHERE live_stream_id=?",(utc_now(),emergency_reason[:1000],utc_now(),stream_id)); row=db.execute("SELECT * FROM connect_live_streams WHERE live_stream_id=?",(stream_id,)).fetchone()
        return dict(row)

class CallService:
    SIGNAL_TYPES={"offer","answer","ice-candidate","renegotiate","track-added","track-removed","media-state","screen-share","hand","reaction","chat-notification","ice-restart","resume","meeting-ended"}
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo
    def capabilities(self)->dict[str,Any]:
        stun=[value.strip() for value in os.getenv("BIOINTEL_CALL_STUN_URLS","stun:stun.l.google.com:19302").split(",") if value.strip()]
        turn_configured=bool(os.getenv("BIOINTEL_CALL_TURN_URL") and os.getenv("BIOINTEL_CALL_TURN_USERNAME") and os.getenv("BIOINTEL_CALL_TURN_CREDENTIAL"))
        return {"topology":"peer-to-peer-mesh","max_peer_participants":int(os.getenv("BIOINTEL_CALL_MAX_MESH_PARTICIPANTS","4")),"stun":{"configured":bool(stun),"urls":stun},"turn":{"configured":turn_configured,"relay_only_supported":turn_configured},"sfu":{"configured":False,"provider":None,"status":"configuration_required"},"recording":{"configured":False,"modes":[],"status":"unavailable"},"transcription":{"configured":False,"providers":[],"status":"unavailable"},"https_required_outside_loopback":True}
    def ice_configuration(self)->dict[str,Any]:
        servers=[]
        stun=[value.strip() for value in os.getenv("BIOINTEL_CALL_STUN_URLS","stun:stun.l.google.com:19302").split(",") if value.strip()]
        if stun: servers.append({"urls":stun})
        turn_url=os.getenv("BIOINTEL_CALL_TURN_URL",""); turn_user=os.getenv("BIOINTEL_CALL_TURN_USERNAME",""); turn_credential=os.getenv("BIOINTEL_CALL_TURN_CREDENTIAL","")
        if turn_url and turn_user and turn_credential: servers.append({"urls":[turn_url],"username":turn_user,"credential":turn_credential})
        return {"iceServers":servers,"iceTransportPolicy":"relay" if os.getenv("BIOINTEL_CALL_RELAY_ONLY","0")=="1" else "all","credential_source":"server_environment" if turn_url else "none"}
    def _get(self,call_id:str)->dict[str,Any]:
        with self.repo.database.connection(read_only=True) as db: row=db.execute("SELECT * FROM connect_call_sessions WHERE call_id=? AND deleted_at_utc IS NULL",(call_id,)).fetchone()
        if not row: raise NotFound("Call not found.")
        return dict(row)
    def _participant(self,user_id:str,call_id:str,accepted:bool=True)->dict[str,Any]:
        with self.repo.database.connection(read_only=True) as db: row=db.execute("SELECT * FROM connect_call_participants WHERE call_id=? AND user_id=?",(call_id,user_id)).fetchone()
        if not row or (accepted and row["invitation_state"]!="accepted") or row["state"]!="active": raise PermissionDenied("Active accepted call membership required.")
        return dict(row)
    def create(self,host_id:str,participant_ids:list[str],*,call_type:str="video",title:str="",scheduled_at_utc:str|None=None,conversation_id:str|None=None,recording_requested:bool=False)->dict[str,Any]:
        if call_type not in {"audio","video","screen_share","meeting"}: raise ConnectError("Unsupported call type.")
        cid,now,token=new_id("call"),utc_now(),secrets.token_urlsafe(32); state="scheduled" if scheduled_at_utc else "ringing"
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_call_sessions(call_id,creator_id,host_id,conversation_id,call_type,title,scheduled_at_utc,meeting_token_hash,recording_requested,recording_state,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(cid,host_id,host_id,conversation_id,call_type,title[:300],scheduled_at_utc,hashlib.sha256(token.encode()).hexdigest(),int(recording_requested),"unavailable" if recording_requested else "not_requested",state,"private",now,now))
            for uid in dict.fromkeys([host_id,*participant_ids]):
                invitation="accepted" if uid==host_id else "invited"
                db.execute("INSERT INTO connect_call_participants(participant_id,creator_id,call_id,user_id,role,invitation_state,recording_consent,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'active','private',?,?)",(new_id("callpart"),host_id,cid,uid,"host" if uid==host_id else "participant",invitation,0,now,now))
            row=db.execute("SELECT * FROM connect_call_sessions WHERE call_id=?",(cid,)).fetchone()
        for uid in dict.fromkeys(participant_ids):
            if uid!=host_id: self.repo.notification(uid,host_id,"call_invitation","call",cid,"Incoming BioIntel Connect call invitation.")
        result=dict(row); result["meeting_token"]=token; return result
    def respond(self,user_id:str,call_id:str,decision:str,*,microphone:bool=False,camera:bool=False,recording_consent:bool=False)->dict[str,Any]:
        if decision not in {"accepted","rejected","busy"}: raise ConnectError("Invalid call response.")
        call=self._get(call_id)
        with self.repo.database.connection() as db:
            row=db.execute("SELECT * FROM connect_call_participants WHERE call_id=? AND user_id=?",(call_id,user_id)).fetchone()
            if not row: raise PermissionDenied("You were not invited to this call.")
            if call["recording_requested"] and recording_consent: raise ConnectError("Recording is unavailable because no verified recorder is configured.")
            db.execute("UPDATE connect_call_participants SET invitation_state=?,microphone_permission=?,camera_permission=?,recording_consent=0,joined_at_utc=CASE WHEN ?='accepted' THEN ? ELSE joined_at_utc END,updated_at_utc=?,version=version+1 WHERE call_id=? AND user_id=?",(decision,int(microphone),int(camera),decision,utc_now(),utc_now(),call_id,user_id)); updated=db.execute("SELECT * FROM connect_call_participants WHERE call_id=? AND user_id=?",(call_id,user_id)).fetchone()
        return dict(updated)
    def start(self,actor:str,call_id:str)->dict[str,Any]:
        call=self._get(call_id)
        if call["host_id"]!=actor: raise PermissionDenied("Only host may start call.")
        if call["state"]=="active": return call
        if call["state"] not in {"ringing","scheduled","ready"}: raise Conflict("Call cannot be started from its current state.")
        with self.repo.database.connection(read_only=True) as db: accepted=db.execute("SELECT COUNT(*) FROM connect_call_participants WHERE call_id=? AND invitation_state='accepted'",(call_id,)).fetchone()[0]
        if accepted<2: raise Conflict("At least two accepted participants are required.")
        now=utc_now()
        with self.repo.database.connection() as db: db.execute("UPDATE connect_call_sessions SET state='active',started_at_utc=COALESCE(started_at_utc,?),recording_state=?,updated_at_utc=?,version=version+1 WHERE call_id=?",(now,"unavailable" if call["recording_requested"] else "not_requested",now,call_id)); row=db.execute("SELECT * FROM connect_call_sessions WHERE call_id=?",(call_id,)).fetchone()
        return dict(row)
    def screen_share(self,user_id:str,call_id:str,enabled:bool)->dict[str,Any]:
        call=self._get(call_id); self._participant(user_id,call_id)
        if call["state"]!="active": raise Conflict("Screen sharing requires an active call.")
        with self.repo.database.connection() as db: db.execute("UPDATE connect_call_sessions SET screen_sharing_user_id=?,updated_at_utc=?,version=version+1 WHERE call_id=?",(user_id if enabled else None,utc_now(),call_id)); row=db.execute("SELECT * FROM connect_call_sessions WHERE call_id=?",(call_id,)).fetchone()
        return dict(row)
    def signal(self,user_id:str,call_id:str,signal_type:str,payload:dict[str,Any],recipient_id:str|None=None)->dict[str,Any]:
        call=self._get(call_id); self._participant(user_id,call_id)
        if call["state"]!="active": raise Conflict("Signaling requires an active call.")
        if signal_type not in self.SIGNAL_TYPES: raise ConnectError("Unsupported signaling event.")
        if recipient_id:
            self._participant(recipient_id,call_id)
            if recipient_id==user_id: raise ConnectError("A signal recipient must be another participant.")
        encoded=json.dumps(payload,separators=(",",":"))
        if len(encoded)>65536: raise ConnectError("Signal payload exceeds 64 KiB.")
        signal_id,now=new_id("callsignal"),utc_now()
        with self.repo.database.connection() as db:
            db.execute("INSERT INTO connect_call_signals(signal_id,creator_id,call_id,sender_id,recipient_id,signal_type,signal_json,expires_at_utc,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(signal_id,user_id,call_id,user_id,recipient_id,signal_type,encoded,_future(1),"active","private",now,now)); row=db.execute("SELECT * FROM connect_call_signals WHERE signal_id=?",(signal_id,)).fetchone()
        result=dict(row); result["signal"]=payload; result.pop("signal_json",None); return result
    def signals(self,user_id:str,call_id:str,after_created_at:str="",limit:int=100)->list[dict[str,Any]]:
        self._participant(user_id,call_id); now=utc_now()
        with self.repo.database.connection(read_only=True) as db: rows=db.execute("SELECT * FROM connect_call_signals WHERE call_id=? AND sender_id<>? AND (recipient_id IS NULL OR recipient_id=?) AND expires_at_utc>? AND created_at_utc>? ORDER BY created_at_utc,signal_id LIMIT ?",(call_id,user_id,user_id,now,after_created_at,min(max(limit,1),250))).fetchall()
        result=[]
        for row in rows:
            item=dict(row); item["signal"]=json.loads(item.pop("signal_json")); result.append(item)
        return result
    def state(self,user_id:str,call_id:str)->dict[str,Any]:
        call=self._get(call_id); self._participant(user_id,call_id,accepted=False)
        with self.repo.database.connection(read_only=True) as db: participants=[dict(row) for row in db.execute("SELECT participant_id,user_id,role,invitation_state,joined_at_utc,left_at_utc,microphone_permission,camera_permission,network_quality,state FROM connect_call_participants WHERE call_id=? ORDER BY role DESC,created_at_utc",(call_id,))]
        call["current_user_id"]=user_id; call["participants"]=participants; call["capabilities"]=self.capabilities(); return call
    def leave(self,user_id:str,call_id:str)->dict[str,Any]:
        self._participant(user_id,call_id,accepted=False); now=utc_now()
        with self.repo.database.connection() as db: db.execute("UPDATE connect_call_participants SET state='left',left_at_utc=?,updated_at_utc=?,version=version+1 WHERE call_id=? AND user_id=?",(now,now,call_id,user_id))
        return {"call_id":call_id,"user_id":user_id,"state":"left","left_at_utc":now}
    def end(self,actor:str,call_id:str)->dict[str,Any]:
        call=self._get(call_id)
        if call["host_id"]!=actor: raise PermissionDenied("Only host may end call for everyone.")
        if call["state"]=="ended": return call
        now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("UPDATE connect_call_sessions SET state='ended',ended_at_utc=?,screen_sharing_user_id=NULL,recording_state=CASE WHEN recording_requested=1 THEN 'unavailable' ELSE 'not_requested' END,updated_at_utc=?,version=version+1 WHERE call_id=?",(now,now,call_id)); db.execute("UPDATE connect_call_participants SET state=CASE WHEN state='active' THEN 'left' ELSE state END,left_at_utc=COALESCE(left_at_utc,?),updated_at_utc=? WHERE call_id=?",(now,now,call_id)); row=db.execute("SELECT * FROM connect_call_sessions WHERE call_id=?",(call_id,)).fetchone()
        return dict(row)


