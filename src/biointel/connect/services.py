from __future__ import annotations

import re
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from biointel.database.core import json_text, utc_now
from .database import ConnectDatabase, connect_database_path
from .media import MediaService
from .repositories import ConnectRepository, decode_cursor, encode_cursor, new_id

PROFILE_VISIBILITY = {"public","authenticated","connections","only_me"}
POST_VISIBILITY = {"public","followers","connections","community_members","project_members","institution_members","private_link","only_me","draft"}
REACTIONS = {"like","appreciate","insightful","useful","support","collaborate","question","needs_evidence","reproducible"}
REPORT_REASONS = {"spam","harassment","impersonation","fake_credentials","plagiarism","copyright_infringement",
                  "scientific_misinformation","fabricated_research","privacy_violation","patient_data_exposure",
                  "dangerous_laboratory_content","undisclosed_promotion"}

class ConnectError(ValueError): pass
class NotFound(ConnectError): pass
class PermissionDenied(ConnectError): pass
class Conflict(ConnectError): pass

class ProfileService:
    def __init__(self, repo: ConnectRepository) -> None: self.repo = repo

    def get(self, viewer_id: str, target_id: str) -> dict[str,Any]:
        profile = self.repo.profile(target_id)
        if not profile: raise NotFound("Profile not found.")
        if not self.can_view(viewer_id,target_id): raise PermissionDenied("Profile is not visible to this user.")
        privacy = self.repo.privacy(target_id)
        result = dict(profile)
        if viewer_id != target_id and privacy["institution_visibility"] not in {"public","authenticated"} and not self.repo.connected(viewer_id,target_id):
            result["institution"] = result["department"] = result["laboratory"] = ""
        if viewer_id != target_id and privacy["location_visibility"] != "public" and not self.repo.connected(viewer_id,target_id):
            result["city"] = result["country"] = ""
        return result

    def can_view(self, viewer_id: str, target_id: str) -> bool:
        if viewer_id == target_id: return True
        if self.repo.blocked(viewer_id,target_id): return False
        privacy = self.repo.privacy(target_id)
        visibility = privacy["profile_visibility"]
        return visibility in {"public","authenticated"} or (visibility == "connections" and self.repo.connected(viewer_id,target_id))

    def update(self, user_id: str, payload: dict[str,Any]) -> dict[str,Any]:
        if "username" in payload and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}",str(payload["username"]).lower()):
            raise ConnectError("Username must be 3-64 lowercase letters, numbers, dots, underscores or hyphens.")
        for key, maximum in {"full_name":120,"headline":200,"about":5000,"website":500,"institution":240}.items():
            if key in payload and len(str(payload[key])) > maximum: raise ConnectError(f"{key} exceeds {maximum} characters.")
        profile = self.repo.update_profile(user_id,payload)
        self.repo.audit(user_id,"profile_updated","profile",user_id,{"fields":sorted(payload)})
        return profile

    def privacy(self, user_id: str) -> dict[str,Any]: return self.repo.privacy(user_id)

    def update_privacy(self, user_id: str, payload: dict[str,Any]) -> dict[str,Any]:
        if "profile_visibility" in payload and payload["profile_visibility"] not in PROFILE_VISIBILITY:
            raise ConnectError("Invalid profile visibility.")
        if "default_post_visibility" in payload and payload["default_post_visibility"] not in POST_VISIBILITY:
            raise ConnectError("Invalid post visibility.")
        result = self.repo.update_privacy(user_id,payload)
        self.repo.audit(user_id,"privacy_updated","privacy",user_id,{"fields":sorted(payload)})
        return result

    def search(self, viewer_id: str, query: str, limit: int = 25) -> list[dict[str,Any]]:
        output = []
        for row in self.repo.search_profiles(query,limit*3):
            target = str(row["user_id"])
            if target != viewer_id and not self.can_view(viewer_id,target): continue
            output.append(self.get(viewer_id,target))
            if len(output) >= limit: break
        return output

class NetworkService:
    def __init__(self, repo: ConnectRepository) -> None: self.repo = repo

    def _target(self, actor: str, target: str) -> dict[str,Any]:
        if actor == target: raise ConnectError("You cannot perform this action on yourself.")
        user = self.repo.user(target)
        if not user: raise NotFound("User not found.")
        if self.repo.blocked(actor,target): raise PermissionDenied("This relationship is blocked.")
        return user

    def follow(self, actor: str, target: str) -> dict[str,Any]:
        user = self._target(actor,target); now = utc_now(); follow_id = new_id("fol")
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_follows(follow_id,follower_id,target_id,target_type,created_at_utc,updated_at_utc)
                VALUES(?,?,?,'user',?,?) ON CONFLICT(follower_id,target_id,target_type) DO UPDATE SET
                state='active',deleted_at_utc=NULL,updated_at_utc=excluded.updated_at_utc,version=connect_follows.version+1""",
                (follow_id,actor,target,now,now))
            row = db.execute("SELECT * FROM connect_follows WHERE follower_id=? AND target_id=? AND target_type='user'",(actor,target)).fetchone()
        self.repo.notification(target,actor,"new_follower","user",actor,f"{self.repo.user(actor)['display_name']} followed you.")
        self.repo.audit(actor,"follow_created","user",target)
        return dict(row)

    def unfollow(self, actor: str, target: str) -> None:
        with self.repo.database.connection() as db:
            db.execute("UPDATE connect_follows SET state='removed',deleted_at_utc=?,updated_at_utc=?,version=version+1 WHERE follower_id=? AND target_id=? AND target_type='user'",
                       (utc_now(),utc_now(),actor,target))
        self.repo.audit(actor,"follow_removed","user",target)

    def request_connection(self, actor: str, target: str, **detail: str) -> dict[str,Any]:
        self._target(actor,target)
        permission = self.repo.privacy(target)["connection_permission"]
        if permission == "no_one" or (permission == "followers" and not self.repo.follows(target,actor)):
            raise PermissionDenied("This user is not accepting connection requests from you.")
        if self.repo.connected(actor,target): raise Conflict("Users are already connected.")
        with self.repo.database.connection(read_only=True) as db:
            pending = db.execute("""SELECT request_id FROM connect_connection_requests WHERE state='pending' AND
                ((requester_id=? AND recipient_id=?) OR (requester_id=? AND recipient_id=?))""",(actor,target,target,actor)).fetchone()
        if pending: raise Conflict("A connection request is already pending.")
        request_id, now = new_id("conreq"), utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_connection_requests(request_id,requester_id,recipient_id,introduction,reason,
                shared_research_interest,project_reference,collaboration_idea,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",(request_id,actor,target,detail.get("introduction","")[:1000],detail.get("reason","")[:500],
                detail.get("shared_research_interest","")[:500],detail.get("project_reference","")[:500],detail.get("collaboration_idea","")[:2000],now,now))
            row = db.execute("SELECT * FROM connect_connection_requests WHERE request_id=?",(request_id,)).fetchone()
        self.repo.notification(target,actor,"connection_request","connection_request",request_id,"New professional connection request.")
        self.repo.audit(actor,"connection_requested","user",target)
        return dict(row)

    def respond_connection(self, actor: str, request_id: str, decision: str) -> dict[str,Any]:
        if decision not in {"accepted","declined"}: raise ConnectError("Decision must be accepted or declined.")
        now = utc_now()
        with self.repo.database.connection() as db:
            request = db.execute("SELECT * FROM connect_connection_requests WHERE request_id=? AND state='pending'",(request_id,)).fetchone()
            if not request: raise NotFound("Pending connection request not found.")
            if request["recipient_id"] != actor: raise PermissionDenied("Only the recipient may respond.")
            if self.repo.blocked(request["requester_id"],actor): raise PermissionDenied("This relationship is blocked.")
            db.execute("UPDATE connect_connection_requests SET state=?,updated_at_utc=?,version=version+1 WHERE request_id=?",(decision,now,request_id))
            if decision == "accepted":
                low,high = sorted((str(request["requester_id"]),actor))
                db.execute("""INSERT INTO connect_connections(connection_id,user_low_id,user_high_id,source_request_id,created_at_utc,updated_at_utc)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(user_low_id,user_high_id) DO UPDATE SET state='accepted',deleted_at_utc=NULL,
                    updated_at_utc=excluded.updated_at_utc,version=connect_connections.version+1""",(new_id("con"),low,high,request_id,now,now))
        self.repo.notification(request["requester_id"],actor,f"connection_{decision}","connection_request",request_id,f"Connection request {decision}.")
        self.repo.audit(actor,f"connection_{decision}","connection_request",request_id)
        return {"request_id":request_id,"state":decision}

    def block(self, actor: str, target: str, reason: str = "") -> dict[str,Any]:
        if actor == target: raise ConnectError("You cannot block yourself.")
        if not self.repo.user(target): raise NotFound("User not found.")
        now = utc_now(); low,high = sorted((actor,target)); block_id = new_id("blk")
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_user_blocks(block_id,blocker_id,blocked_id,reason,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?) ON CONFLICT(blocker_id,blocked_id) DO UPDATE SET reason=excluded.reason,state='active',
                deleted_at_utc=NULL,updated_at_utc=excluded.updated_at_utc,version=connect_user_blocks.version+1""",
                (block_id,actor,target,reason[:500],now,now))
            db.execute("UPDATE connect_follows SET state='removed',deleted_at_utc=?,updated_at_utc=? WHERE (follower_id=? AND target_id=?) OR (follower_id=? AND target_id=?)",(now,now,actor,target,target,actor))
            db.execute("UPDATE connect_connections SET state='blocked',deleted_at_utc=?,updated_at_utc=? WHERE user_low_id=? AND user_high_id=?",(now,now,low,high))
            db.execute("UPDATE connect_connection_requests SET state='blocked',updated_at_utc=? WHERE state='pending' AND ((requester_id=? AND recipient_id=?) OR (requester_id=? AND recipient_id=?))",(now,actor,target,target,actor))
            row = db.execute("SELECT * FROM connect_user_blocks WHERE blocker_id=? AND blocked_id=?",(actor,target)).fetchone()
        self.repo.audit(actor,"user_blocked","user",target,{"reason":reason[:500]})
        return dict(row)

    def mute(self, actor: str, target: str) -> dict[str,Any]:
        self._target(actor,target); now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_user_mutes(mute_id,muter_id,muted_id,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?) ON CONFLICT(muter_id,muted_id) DO UPDATE SET state='active',deleted_at_utc=NULL,updated_at_utc=excluded.updated_at_utc""",
                (new_id("mut"),actor,target,now,now))
            row=db.execute("SELECT * FROM connect_user_mutes WHERE muter_id=? AND muted_id=?",(actor,target)).fetchone()
        return dict(row)

    def overview(self, user_id: str) -> dict[str,Any]:
        with self.repo.database.connection(read_only=True) as db:
            following=[dict(r) for r in db.execute("""SELECT f.*,u.username,u.display_name FROM connect_follows f JOIN connect_users u ON u.user_id=f.target_id
                WHERE f.follower_id=? AND f.state='active' AND f.deleted_at_utc IS NULL ORDER BY u.display_name""",(user_id,))]
            requests=[dict(r) for r in db.execute("""SELECT r.*,u.username,u.display_name FROM connect_connection_requests r JOIN connect_users u ON u.user_id=r.requester_id
                WHERE r.recipient_id=? AND r.state='pending' ORDER BY r.created_at_utc DESC""",(user_id,))]
            connected=[dict(r) for r in db.execute("""SELECT u.user_id,u.username,u.display_name,p.headline,p.institution FROM connect_connections c
                JOIN connect_users u ON u.user_id=CASE WHEN c.user_low_id=? THEN c.user_high_id ELSE c.user_low_id END
                JOIN connect_profiles p ON p.user_id=u.user_id WHERE (c.user_low_id=? OR c.user_high_id=?) AND c.state='accepted'""",(user_id,user_id,user_id))]
        return {"following":following,"requests":requests,"connections":connected}

@dataclass(frozen=True)
class ConnectServices:
    database: ConnectDatabase
    repository: ConnectRepository
    profiles: ProfileService
    network: NetworkService
    content: "ContentService"
    media: MediaService
    complete: Any | None = None

    def ensure_identity(self, username: str, display_name: str, role: str = "researcher") -> dict[str,Any]:
        return self.repository.ensure_user(username,display_name,role)

class ContentService:
    def __init__(self, repo: ConnectRepository) -> None: self.repo = repo

    def can_view(self, viewer: str, post: dict[str,Any]) -> bool:
        author, visibility = str(post["author_id"]), str(post["visibility"])
        if viewer == author: return True
        if post["state"] != "published" or self.repo.blocked(viewer,author): return False
        if visibility in {"public","private_link"}: return True
        if visibility == "followers": return self.repo.follows(viewer,author)
        if visibility == "connections": return self.repo.connected(viewer,author)
        if visibility == "institution_members":
            left,right = self.repo.profile(viewer),self.repo.profile(author)
            return bool(left and right and left["institution"] and left["institution"] == right["institution"])
        if visibility == "community_members" and post.get("community_id"):
            with self.repo.database.connection(read_only=True) as db:
                return bool(db.execute("SELECT 1 FROM connect_community_members WHERE community_id=? AND user_id=? AND state='active' AND deleted_at_utc IS NULL",(post["community_id"],viewer)).fetchone())
        if visibility == "project_members" and post.get("project_id"):
            with self.repo.database.connection(read_only=True) as db:
                return bool(db.execute("SELECT 1 FROM connect_project_members WHERE project_id=? AND user_id=? AND state='active' AND deleted_at_utc IS NULL",(post["project_id"],viewer)).fetchone())
        return False

    def create_post(self, author: str, *, body: str, title: str = "", post_type: str = "text",
                    visibility: str = "public", comment_permission: str = "everyone",
                    download_permission: str = "ask", media_ids: list[str] | None = None,
                    collaboration_enabled: bool = False, project_id: str = "", community_id: str = "") -> dict[str,Any]:
        if visibility not in POST_VISIBILITY: raise ConnectError("Invalid post visibility.")
        if not body.strip() and not media_ids: raise ConnectError("A post needs text or an attachment.")
        if len(body) > 50_000 or len(title) > 300: raise ConnectError("Post content exceeds its limit.")
        profile = self.repo.profile(author)
        if not profile: raise NotFound("Author profile not found.")
        media_ids = list(dict.fromkeys(media_ids or []))[:20]
        post_id, now = new_id("pst"), utc_now()
        state = "draft" if visibility == "draft" else "published"
        mention_recipients: list[str] = []
        with self.repo.database.connection() as db:
            for media_id in media_ids:
                media = db.execute("SELECT owner_id,state FROM connect_media_objects WHERE media_id=?",(media_id,)).fetchone()
                if not media or media["owner_id"] != author or media["state"] != "available":
                    raise PermissionDenied("Attachments must be available media owned by the author.")
            db.execute("""INSERT INTO connect_posts(post_id,author_id,post_type,title,body,visibility,community_id,project_id,
                institution,comment_permission,download_permission,collaboration_enabled,state,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(post_id,author,post_type[:80],title.strip(),body.strip(),visibility,
                community_id or None,project_id or None,profile["institution"],comment_permission,download_permission,
                int(collaboration_enabled),state,now,now))
            for position,media_id in enumerate(media_ids):
                db.execute("""INSERT INTO connect_post_attachments(attachment_id,post_id,media_id,position,created_at_utc,updated_at_utc)
                    VALUES(?,?,?,?,?,?)""",(new_id("att"),post_id,media_id,position,now,now))
            for tag in sorted(set(re.findall(r"(?<!\w)#([A-Za-z0-9_]{1,64})",body))):
                normalized=tag.lower(); hashtag_id=new_id("tag")
                db.execute("INSERT OR IGNORE INTO connect_hashtags(hashtag_id,normalized_tag,display_tag,created_at_utc) VALUES(?,?,?,?)",
                           (hashtag_id,normalized,tag,now))
                actual=db.execute("SELECT hashtag_id FROM connect_hashtags WHERE normalized_tag=?",(normalized,)).fetchone()[0]
                db.execute("INSERT OR IGNORE INTO connect_post_hashtags(post_id,hashtag_id) VALUES(?,?)",(post_id,actual))
            for username in sorted(set(re.findall(r"(?<!\w)@([A-Za-z0-9._-]{3,64})",body))):
                mentioned=db.execute("SELECT user_id FROM connect_users WHERE username=? COLLATE NOCASE",(username,)).fetchone()
                if mentioned and mentioned["user_id"] != author and not self.repo.blocked(author,mentioned["user_id"]):
                    privacy=db.execute("SELECT mention_permission FROM connect_privacy_preferences WHERE user_id=?",(mentioned["user_id"],)).fetchone()[0]
                    if privacy == "everyone" or (privacy == "connections" and self.repo.connected(author,mentioned["user_id"])):
                        db.execute("""INSERT INTO connect_mentions(mention_id,source_type,source_id,mentioned_user_id,creator_id,
                            created_at_utc,updated_at_utc) VALUES(?,'post',?,?,?,?,?)""",
                            (new_id("men"),post_id,mentioned["user_id"],author,now,now))
                        mention_recipients.append(str(mentioned["user_id"]))
        for recipient in mention_recipients:
            self.repo.notification(recipient,author,"mention","post",post_id,"You were mentioned in a post.")
        self.repo.audit(author,"post_created","post",post_id,{"visibility":visibility,"attachments":len(media_ids)})
        return self.get_post(author,post_id)

    def get_post(self, viewer: str, post_id: str) -> dict[str,Any]:
        post=self.repo.post(post_id)
        if not post: raise NotFound("Post not found.")
        if not self.can_view(viewer,post): raise PermissionDenied("Post is not visible to this user.")
        post["viewer_bookmarked"] = self.bookmarked(viewer,post_id)
        return post

    def feed(self, viewer: str, *, mode: str = "latest", cursor: str | None = None,
             limit: int = 20) -> dict[str,Any]:
        if mode not in {"latest","following","connections","research_interests","institution","trending","recommended"}:
            raise ConnectError("Invalid feed mode.")
        author_ids: list[str] | None = None
        with self.repo.database.connection(read_only=True) as db:
            if mode == "following":
                author_ids=[viewer]+[str(r[0]) for r in db.execute("SELECT target_id FROM connect_follows WHERE follower_id=? AND target_type='user' AND state='active'",(viewer,))]
            elif mode == "connections":
                author_ids=[viewer]+[str(r[0]) for r in db.execute("""SELECT CASE WHEN user_low_id=? THEN user_high_id ELSE user_low_id END
                    FROM connect_connections WHERE (user_low_id=? OR user_high_id=?) AND state='accepted'""",(viewer,viewer,viewer))]
            muted={str(r[0]) for r in db.execute("SELECT muted_id FROM connect_user_mutes WHERE muter_id=? AND state='active'",(viewer,))}
        candidates=self.repo.candidate_posts(decode_cursor(cursor),author_ids,max(limit*6,60))
        visible=[]
        for post in candidates:
            if post["author_id"] in muted or not self.can_view(viewer,post): continue
            post["viewer_bookmarked"] = self.bookmarked(viewer,post["post_id"])
            post["recommendation_reason"] = "Latest from your selected network" if mode in {"following","connections"} else "Recent permission-aware scientific update"
            visible.append(post)
            if len(visible) >= min(max(limit,1),50): break
        next_cursor = encode_cursor(visible[-1]["created_at_utc"],visible[-1]["post_id"]) if len(visible)==min(max(limit,1),50) else None
        return {"items":visible,"next_cursor":next_cursor,"mode":mode}

    def add_comment(self, author: str, post_id: str, body: str, parent_comment_id: str | None = None) -> dict[str,Any]:
        post=self.get_post(author,post_id)
        if post["comment_permission"] == "none" or (post["comment_permission"] == "connections" and author != post["author_id"] and not self.repo.connected(author,post["author_id"])):
            raise PermissionDenied("Comments are not permitted for this user.")
        if not body.strip() or len(body)>10_000: raise ConnectError("Comment must be 1-10,000 characters.")
        now,comment_id=utc_now(),new_id("cmt")
        with self.repo.database.connection() as db:
            if parent_comment_id:
                parent=db.execute("SELECT post_id FROM connect_comments WHERE comment_id=? AND state='published'",(parent_comment_id,)).fetchone()
                if not parent or parent["post_id"] != post_id: raise NotFound("Parent comment not found on this post.")
            db.execute("""INSERT INTO connect_comments(comment_id,post_id,author_id,parent_comment_id,body,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?)""",(comment_id,post_id,author,parent_comment_id,body.strip(),now,now))
            row=db.execute("SELECT * FROM connect_comments WHERE comment_id=?",(comment_id,)).fetchone()
        recipient=post["author_id"]
        if recipient != author: self.repo.notification(recipient,author,"reply" if parent_comment_id else "comment","post",post_id,"New reply on your post." if parent_comment_id else "New comment on your post.")
        self.repo.audit(author,"comment_created","comment",comment_id,{"post_id":post_id})
        return dict(row)

    def comments(self, viewer: str, post_id: str) -> list[dict[str,Any]]:
        self.get_post(viewer,post_id)
        return [row for row in self.repo.comments(post_id) if not self.repo.blocked(viewer,row["author_id"])]

    def react(self, user: str, post_id: str, reaction: str) -> dict[str,Any]:
        post=self.get_post(user,post_id)
        if reaction not in REACTIONS: raise ConnectError("Unsupported scientific reaction.")
        now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_reactions(reaction_id,user_id,target_type,target_id,reaction_type,created_at_utc,updated_at_utc)
                VALUES(?,?,'post',?,?,?,?) ON CONFLICT(user_id,target_type,target_id) DO UPDATE SET reaction_type=excluded.reaction_type,
                state='active',deleted_at_utc=NULL,updated_at_utc=excluded.updated_at_utc,version=connect_reactions.version+1""",
                (new_id("rea"),user,post_id,reaction,now,now))
            row=db.execute("SELECT * FROM connect_reactions WHERE user_id=? AND target_type='post' AND target_id=?",(user,post_id)).fetchone()
        if post["author_id"] != user: self.repo.notification(post["author_id"],user,"reaction","post",post_id,f"New {reaction.replace('_',' ')} reaction.")
        return dict(row)

    def bookmark(self, user: str, post_id: str, save: bool = True) -> dict[str,Any]:
        self.get_post(user,post_id); now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_bookmarks(bookmark_id,user_id,post_id,state,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,post_id) DO UPDATE SET state=excluded.state,
                deleted_at_utc=CASE WHEN excluded.state='active' THEN NULL ELSE excluded.updated_at_utc END,
                updated_at_utc=excluded.updated_at_utc,version=connect_bookmarks.version+1""",
                (new_id("bmk"),user,post_id,"active" if save else "removed",now,now))
            row=db.execute("SELECT * FROM connect_bookmarks WHERE user_id=? AND post_id=?",(user,post_id)).fetchone()
        return dict(row)

    def bookmarked(self, user: str, post_id: str) -> bool:
        with self.repo.database.connection(read_only=True) as db:
            return bool(db.execute("SELECT 1 FROM connect_bookmarks WHERE user_id=? AND post_id=? AND state='active' AND deleted_at_utc IS NULL",(user,post_id)).fetchone())

    def saved(self, user: str, limit: int = 100) -> list[dict[str,Any]]:
        with self.repo.database.connection(read_only=True) as db:
            ids=[str(r[0]) for r in db.execute("SELECT post_id FROM connect_bookmarks WHERE user_id=? AND state='active' ORDER BY updated_at_utc DESC LIMIT ?",(user,limit))]
        return [post for post_id in ids if (post:=self.repo.post(post_id)) and self.can_view(user,post)]

    def repost(self, user: str, post_id: str, quote: str = "", visibility: str = "public") -> dict[str,Any]:
        original=self.get_post(user,post_id); quote_post_id=None
        if quote.strip(): quote_post_id=self.create_post(user,body=quote,title=f"Re: {original['title']}"[:300],post_type="quote_repost",visibility=visibility)["post_id"]
        now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_reposts(repost_id,user_id,original_post_id,quote_post_id,visibility,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,original_post_id) DO UPDATE SET quote_post_id=excluded.quote_post_id,
                state='active',visibility=excluded.visibility,updated_at_utc=excluded.updated_at_utc""",
                (new_id("rpt"),user,post_id,quote_post_id,visibility,now,now))
            row=db.execute("SELECT * FROM connect_reposts WHERE user_id=? AND original_post_id=?",(user,post_id)).fetchone()
        if original["author_id"] != user: self.repo.notification(original["author_id"],user,"repost","post",post_id,"Your post was reposted with attribution.")
        return dict(row)

    def report(self, reporter: str, target_type: str, target_id: str, reason: str,
               detail: str = "", evidence: dict[str,Any] | None = None) -> dict[str,Any]:
        if reason not in REPORT_REASONS: raise ConnectError("Unsupported report reason.")
        if target_type == "post": self.get_post(reporter,target_id)
        elif target_type == "comment":
            with self.repo.database.connection(read_only=True) as db:
                if not db.execute("SELECT 1 FROM connect_comments WHERE comment_id=? AND deleted_at_utc IS NULL",(target_id,)).fetchone(): raise NotFound("Comment not found.")
        elif target_type == "user":
            if not self.repo.user(target_id): raise NotFound("User not found.")
        else: raise ConnectError("Unsupported report target.")
        report_id,case_id,now=new_id("rep"),new_id("case"),utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_content_reports(report_id,reporter_id,target_type,target_id,reason,detail,evidence_json,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?)""",(report_id,reporter,target_type,target_id,reason,detail[:5000],json_text(evidence or {}),now,now))
            db.execute("INSERT INTO connect_moderation_cases(case_id,report_id,created_at_utc,updated_at_utc) VALUES(?,?,?,?)",(case_id,report_id,now,now))
        self.repo.audit(reporter,"content_reported",target_type,target_id,{"report_id":report_id,"reason":reason})
        return {"report_id":report_id,"case_id":case_id,"state":"submitted"}

    def notifications(self, user: str, limit: int = 100) -> list[dict[str,Any]]: return self.repo.notifications(user,limit)

    def mark_notifications_read(self, user: str, notification_ids: list[str] | None = None) -> int:
        now=utc_now()
        with self.repo.database.connection() as db:
            if notification_ids:
                ids=list(dict.fromkeys(notification_ids))[:250]
                result=db.execute(f"UPDATE connect_notifications SET read_at_utc=?,updated_at_utc=?,version=version+1 WHERE recipient_id=? AND notification_id IN ({','.join('?' for _ in ids)})",
                                  (now,now,user,*ids))
            else:
                result=db.execute("UPDATE connect_notifications SET read_at_utc=?,updated_at_utc=?,version=version+1 WHERE recipient_id=? AND read_at_utc IS NULL",(now,now,user))
        return int(result.rowcount)


def build_connect_services(project_root: str | Path | None = None, *, database_path: str | Path | None = None,
                           storage_root: str | Path | None = None) -> ConnectServices:
    root=Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[3]
    database=ConnectDatabase(database_path or connect_database_path(root)); database.migrate()
    repository=ConnectRepository(database)
    configured_storage=os.environ.get("BIOINTEL_CONNECT_STORAGE","").strip()
    media=MediaService(database,storage_root or (Path(configured_storage) if configured_storage else root/"UserData"/"connect"/"media"))
    base=ConnectServices(database,repository,ProfileService(repository),NetworkService(repository),ContentService(repository),media)
    from .complete_services import build_complete_suite
    object.__setattr__(base,"complete",build_complete_suite(base,media.storage_root))
    return base





