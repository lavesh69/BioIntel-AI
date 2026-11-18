from __future__ import annotations

import json, re
from typing import Any
from biointel.database.core import utc_now
from .repositories import ConnectRepository, new_id
from .services import Conflict, ConnectError, NotFound, PermissionDenied

VISIBILITIES={"public","private","invite_only","institution_members","verified_members"}
ROLES={"owner","administrator","moderator","expert","member"}
POLICIES={"open","approval","invite_only"}

class CommunityService:
    """Scientific communities with private membership, channels and role enforcement."""
    def __init__(self,repo:ConnectRepository)->None: self.repo=repo

    def _row(self,community_id:str)->dict[str,Any]:
        with self.repo.database.connection(read_only=True) as db:
            row=db.execute("SELECT * FROM connect_communities WHERE community_id=? AND deleted_at_utc IS NULL",(community_id,)).fetchone()
        if not row: raise NotFound("Community not found.")
        return dict(row)

    def membership(self,community_id:str,user_id:str)->dict[str,Any]|None:
        with self.repo.database.connection(read_only=True) as db:
            row=db.execute("SELECT * FROM connect_community_members WHERE community_id=? AND user_id=? AND deleted_at_utc IS NULL",(community_id,user_id)).fetchone()
        return dict(row) if row else None

    def _role(self,community_id:str,actor:str,roles:set[str])->dict[str,Any]:
        row=self.membership(community_id,actor)
        if not row or row["state"]!="active" or row["role"] not in roles: raise PermissionDenied("Community role does not permit this action.")
        return row

    def can_view(self,viewer:str,community:dict[str,Any])->bool:
        if community["state"]!="active": return False
        member=self.membership(str(community["community_id"]),viewer)
        if member and member["state"]=="active": return True
        visibility=str(community["visibility"])
        if visibility=="public": return True
        if visibility=="institution_members":
            owner=self.repo.profile(str(community["owner_id"])); profile=self.repo.profile(viewer)
            return bool(owner and profile and owner["institution"] and owner["institution"]==profile["institution"])
        if visibility=="verified_members":
            with self.repo.database.connection(read_only=True) as db:
                return bool(db.execute("SELECT 1 FROM connect_verification_badges WHERE user_id=? AND state='active' AND (expires_at_utc IS NULL OR expires_at_utc>?)",(viewer,utc_now())).fetchone())
        return False

    def create(self,actor:str,*,name:str,description:str="",rules:str="",visibility:str="public",join_policy:str="open",research_fields:list[str]|None=None)->dict[str,Any]:
        name=name.strip()
        if not 3<=len(name)<=120: raise ConnectError("Community name must be 3-120 characters.")
        if visibility not in VISIBILITIES or join_policy not in POLICIES: raise ConnectError("Unsupported community visibility or join policy.")
        slug=re.sub(r"[^a-z0-9]+","-",name.lower()).strip("-")[:100]; community_id,now=new_id("com"),utc_now()
        with self.repo.database.connection() as db:
            if db.execute("SELECT 1 FROM connect_communities WHERE slug=? COLLATE NOCASE",(slug,)).fetchone(): raise Conflict("A community with this name already exists.")
            db.execute("""INSERT INTO connect_communities(community_id,creator_id,name,slug,description,rules,owner_id,research_fields_json,member_count,join_policy,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,1,?,'active',?,?,?)""",(community_id,actor,name,slug,description[:5000],rules[:10000],actor,json.dumps(research_fields or []),join_policy,visibility,now,now))
            db.execute("""INSERT INTO connect_community_members(membership_id,creator_id,community_id,user_id,role,joined_at_utc,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?, 'active','private',?,?)""",(new_id("commem"),actor,community_id,actor,"owner",now,now,now))
            db.execute("""INSERT INTO connect_community_channels(channel_id,creator_id,community_id,name,channel_type,description,posting_role,position,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,'General','discussion','General scientific discussion','member',0,'active','private',?,?)""",(new_id("channel"),actor,community_id,now,now))
        self.repo.audit(actor,"community_created","community",community_id)
        return self.get(actor,community_id)

    def get(self,viewer:str,community_id:str)->dict[str,Any]:
        result=self._row(community_id)
        if not self.can_view(viewer,result): raise PermissionDenied("Community is not visible to this user.")
        result["viewer_membership"]=self.membership(community_id,viewer)
        with self.repo.database.connection(read_only=True) as db:
            result["channels"]=[dict(r) for r in db.execute("SELECT * FROM connect_community_channels WHERE community_id=? AND state='active' ORDER BY position,name",(community_id,))]
        return result

    def list(self,viewer:str,query:str="",limit:int=50)->list[dict[str,Any]]:
        like=f"%{query.strip()}%"
        with self.repo.database.connection(read_only=True) as db:
            rows=[dict(r) for r in db.execute("SELECT * FROM connect_communities WHERE deleted_at_utc IS NULL AND state='active' AND (name LIKE ? OR description LIKE ?) ORDER BY member_count DESC,updated_at_utc DESC LIMIT ?",(like,like,min(max(limit,1),100)))]
        return [r for r in rows if self.can_view(viewer,r)]

    def join(self,actor:str,community_id:str,*,invited:bool=False)->dict[str,Any]:
        community=self._row(community_id); existing=self.membership(community_id,actor)
        if existing and existing["state"] in {"active","pending"}: return existing
        if community["join_policy"]=="invite_only" and not invited: raise PermissionDenied("An invitation is required.")
        state="pending" if community["join_policy"]=="approval" and not invited else "active"; now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_community_members(membership_id,creator_id,community_id,user_id,role,joined_at_utc,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'private',?,?) ON CONFLICT(community_id,user_id) DO UPDATE SET state=excluded.state,deleted_at_utc=NULL,updated_at_utc=excluded.updated_at_utc""",(new_id("commem"),actor,community_id,actor,"member",now,state,now,now))
            if state=="active": db.execute("UPDATE connect_communities SET member_count=member_count+1,updated_at_utc=?,version=version+1 WHERE community_id=?",(now,community_id))
            row=db.execute("SELECT * FROM connect_community_members WHERE community_id=? AND user_id=?",(community_id,actor)).fetchone()
        self.repo.notification(str(community["owner_id"]),actor,"community_join" if state=="active" else "community_join_request","community",community_id,f"Community membership is {state}.")
        return dict(row)

    def set_member(self,actor:str,community_id:str,user_id:str,*,state:str="active",role:str="member",ban_reason:str="")->dict[str,Any]:
        actor_member=self._role(community_id,actor,{"owner","administrator","moderator"})
        if role not in ROLES or state not in {"active","declined","banned","removed"}: raise ConnectError("Invalid membership state or role.")
        if role in {"owner","administrator"} and actor_member["role"]!="owner": raise PermissionDenied("Only the owner may grant this role.")
        current=self.membership(community_id,user_id)
        if not current: raise NotFound("Community membership not found.")
        now=utc_now(); was=current["state"]=="active"
        with self.repo.database.connection() as db:
            db.execute("UPDATE connect_community_members SET state=?,role=?,ban_reason=?,updated_at_utc=?,version=version+1 WHERE community_id=? AND user_id=?",(state,role,ban_reason[:1000],now,community_id,user_id))
            if was!=(state=="active"): db.execute("UPDATE connect_communities SET member_count=MAX(0,member_count+?),updated_at_utc=?,version=version+1 WHERE community_id=?",(1 if state=="active" else -1,now,community_id))
            row=db.execute("SELECT * FROM connect_community_members WHERE community_id=? AND user_id=?",(community_id,user_id)).fetchone()
        self.repo.audit(actor,"community_member_updated","community",community_id,{"user_id":user_id,"state":state,"role":role})
        return dict(row)

    def create_channel(self,actor:str,community_id:str,*,name:str,channel_type:str="discussion",description:str="",posting_role:str="member")->dict[str,Any]:
        self._role(community_id,actor,{"owner","administrator","moderator"})
        if posting_role not in ROLES: raise ConnectError("Unsupported posting role.")
        now,cid=utc_now(),new_id("channel")
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_community_channels(channel_id,creator_id,community_id,name,channel_type,description,posting_role,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'active','private',?,?)""",(cid,actor,community_id,name.strip()[:100],channel_type[:40],description[:2000],posting_role,now,now))
            row=db.execute("SELECT * FROM connect_community_channels WHERE channel_id=?",(cid,)).fetchone()
        return dict(row)

    def create_post(self,actor:str,community_id:str,*,body:str,title:str="",channel_id:str|None=None)->dict[str,Any]:
        member=self._role(community_id,actor,ROLES)
        if channel_id:
            with self.repo.database.connection(read_only=True) as db: channel=db.execute("SELECT * FROM connect_community_channels WHERE channel_id=? AND community_id=? AND state='active'",(channel_id,community_id)).fetchone()
            if not channel: raise NotFound("Community channel not found.")
            ranks={"member":1,"expert":2,"moderator":3,"administrator":4,"owner":5}
            if ranks[member["role"]]<ranks.get(channel["posting_role"],1): raise PermissionDenied("Your role cannot post in this channel.")
        from .services import ContentService
        content=ContentService(self.repo); result=content.create_post(actor,body=body,title=title,visibility="community_members",community_id=community_id)
        if channel_id:
            with self.repo.database.connection() as db: db.execute("UPDATE connect_posts SET payload_json=?,updated_at_utc=?,version=version+1 WHERE post_id=?",(json.dumps({"community_channel_id":channel_id}),utc_now(),result["post_id"]))
        return content.get_post(actor,result["post_id"])

    def feed(self,viewer:str,community_id:str,limit:int=50)->list[dict[str,Any]]:
        community=self._row(community_id)
        if not self.can_view(viewer,community): raise PermissionDenied("Community is not visible to this user.")
        from .services import ContentService
        content=ContentService(self.repo)
        with self.repo.database.connection(read_only=True) as db: rows=[dict(r) for r in db.execute("SELECT * FROM connect_posts WHERE community_id=? AND state='published' AND deleted_at_utc IS NULL ORDER BY created_at_utc DESC LIMIT ?",(community_id,min(max(limit,1),100)))]
        return [r for r in rows if content.can_view(viewer,r)]
