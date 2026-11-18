from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .media import UploadRejected, UploadRequiresConfirmation
from .services import Conflict, ConnectError, NotFound, PermissionDenied, build_connect_services

router = APIRouter(prefix="/api/v1/connect", tags=["BioIntel Connect"])
SERVICES = build_connect_services()

class ProfileUpdate(BaseModel):
    username: str | None = Field(default=None,min_length=3,max_length=64)
    full_name: str | None = Field(default=None,min_length=1,max_length=120)
    headline: str | None = Field(default=None,max_length=200)
    institution: str | None = Field(default=None,max_length=240)
    department: str | None = Field(default=None,max_length=240)
    laboratory: str | None = Field(default=None,max_length=240)
    city: str | None = Field(default=None,max_length=120)
    country: str | None = Field(default=None,max_length=120)
    timezone: str | None = Field(default=None,max_length=80)
    about: str | None = Field(default=None,max_length=5000)
    website: str | None = Field(default=None,max_length=500)
    preferred_language: str | None = Field(default=None,max_length=80)
    contact_preference: str | None = Field(default=None,max_length=80)
    profile_image_id: str | None = None
    cover_image_id: str | None = None
    research: dict[str,Any] | None = None
    background: dict[str,Any] | None = None
    identity: dict[str,Any] | None = None
    portfolio: dict[str,Any] | None = None

class PrivacyUpdate(BaseModel):
    profile_visibility: Literal["public","authenticated","connections","only_me"] | None = None
    default_post_visibility: str | None = None
    institution_visibility: str | None = None
    location_visibility: str | None = None
    read_receipts: bool | None = None
    message_permission: str | None = None
    connection_permission: str | None = None
    mention_permission: str | None = None
    download_permission: str | None = None
    search_discoverable: bool | None = None
    activity_visibility: str | None = None

class ConnectionCreate(BaseModel):
    recipient_id: str
    introduction: str = Field(default="",max_length=1000)
    reason: str = Field(default="",max_length=500)
    shared_research_interest: str = Field(default="",max_length=500)
    project_reference: str = Field(default="",max_length=500)
    collaboration_idea: str = Field(default="",max_length=2000)

class ConnectionDecision(BaseModel):
    decision: Literal["accepted","declined"]

class BlockCreate(BaseModel):
    target_id: str
    reason: str = Field(default="",max_length=500)

class PostCreate(BaseModel):
    body: str = Field(default="",max_length=50_000)
    title: str = Field(default="",max_length=300)
    post_type: str = Field(default="text",max_length=80)
    visibility: str = "public"
    comment_permission: str = "everyone"
    download_permission: str = "ask"
    media_ids: list[str] = Field(default_factory=list,max_length=20)
    collaboration_enabled: bool = False
    project_id: str = ""
    community_id: str = ""

class UploadInitialize(BaseModel):
    filename: str = Field(min_length=1,max_length=255)
    mime_type: str = Field(min_length=1,max_length=200)
    size_bytes: int = Field(ge=1,le=250*1024*1024)
    expected_sha256: str = Field(default="",max_length=64)

class UploadComplete(BaseModel):
    visibility: str = "private"
    confirm_sensitive: bool = False

class CommentCreate(BaseModel):
    body: str = Field(min_length=1,max_length=10_000)
    parent_comment_id: str | None = None

class ReactionCreate(BaseModel): reaction_type: str
class BookmarkUpdate(BaseModel): saved: bool = True
class RepostCreate(BaseModel):
    quote: str = Field(default="",max_length=50_000)
    visibility: str = "public"
class ReportCreate(BaseModel):
    target_type: Literal["user","post","comment"]
    target_id: str
    reason: str
    detail: str = Field(default="",max_length=5000)
    evidence: dict[str,Any] = Field(default_factory=dict)
class NotificationsRead(BaseModel): notification_ids: list[str] | None = None


def identity(request: Request) -> dict[str,Any]:
    api_identity=getattr(request.state,"api_identity",None)
    username=str(getattr(api_identity,"client_id","local-operator"))
    display=str(getattr(api_identity,"display_name","Local operator"))
    role=str(getattr(api_identity,"role","local_operator"))
    return SERVICES.ensure_identity(username,display,role)

def call(operation):
    try: return operation()
    except NotFound as exc: raise HTTPException(404,detail=str(exc)) from exc
    except PermissionDenied as exc: raise HTTPException(403,detail=str(exc)) from exc
    except Conflict as exc: raise HTTPException(409,detail=str(exc)) from exc
    except UploadRequiresConfirmation as exc: raise HTTPException(409,detail=exc.result) from exc
    except (ConnectError,UploadRejected,KeyError) as exc: raise HTTPException(422,detail=str(exc)) from exc

@router.get("/profiles/me")
def my_profile(request: Request) -> dict[str,Any]:
    user=identity(request); return call(lambda: SERVICES.profiles.get(user["user_id"],user["user_id"]))

@router.put("/profiles/me")
def update_my_profile(payload: ProfileUpdate,request: Request) -> dict[str,Any]:
    user=identity(request); return call(lambda: SERVICES.profiles.update(user["user_id"],payload.model_dump(exclude_none=True)))

@router.get("/profiles/search")
def search_profiles(request: Request,q: str=Query(default="",max_length=200),limit: int=Query(default=25,ge=1,le=100)) -> dict[str,Any]:
    user=identity(request); items=call(lambda: SERVICES.profiles.search(user["user_id"],q,limit)); return {"items":items,"count":len(items)}

@router.get("/profiles/{user_id}")
def get_profile(user_id: str,request: Request) -> dict[str,Any]:
    user=identity(request); return call(lambda: SERVICES.profiles.get(user["user_id"],user_id))

@router.get("/privacy/me")
def my_privacy(request: Request) -> dict[str,Any]: return SERVICES.profiles.privacy(identity(request)["user_id"])

@router.put("/privacy/me")
def update_privacy(payload: PrivacyUpdate,request: Request) -> dict[str,Any]:
    user=identity(request); return call(lambda: SERVICES.profiles.update_privacy(user["user_id"],payload.model_dump(exclude_none=True)))

@router.post("/follows/{target_id}")
def follow(target_id: str,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.network.follow(identity(request)["user_id"],target_id))

@router.delete("/follows/{target_id}",status_code=204)
def unfollow(target_id: str,request: Request) -> Response:
    call(lambda: SERVICES.network.unfollow(identity(request)["user_id"],target_id)); return Response(status_code=204)

@router.get("/connections")
def network(request: Request) -> dict[str,Any]: return SERVICES.network.overview(identity(request)["user_id"])

@router.post("/connections/requests")
def request_connection(payload: ConnectionCreate,request: Request) -> dict[str,Any]:
    user=identity(request); data=payload.model_dump(); target=data.pop("recipient_id")
    return call(lambda: SERVICES.network.request_connection(user["user_id"],target,**data))

@router.post("/connections/requests/{request_id}/respond")
def respond_connection(request_id: str,payload: ConnectionDecision,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.network.respond_connection(identity(request)["user_id"],request_id,payload.decision))

@router.post("/blocks")
def block(payload: BlockCreate,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.network.block(identity(request)["user_id"],payload.target_id,payload.reason))

@router.post("/mutes/{target_id}")
def mute(target_id: str,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.network.mute(identity(request)["user_id"],target_id))

@router.post("/posts",status_code=201)
def create_post(payload: PostCreate,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.content.create_post(identity(request)["user_id"],**payload.model_dump()))

@router.get("/posts/{post_id}")
def get_post(post_id: str,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.content.get_post(identity(request)["user_id"],post_id))

@router.get("/feed")
def feed(request: Request,mode: str="latest",cursor: str|None=None,limit: int=Query(default=20,ge=1,le=50)) -> dict[str,Any]:
    return call(lambda: SERVICES.content.feed(identity(request)["user_id"],mode=mode,cursor=cursor,limit=limit))

@router.post("/media/uploads",status_code=201)
def initialize_upload(payload: UploadInitialize,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.media.initialize(identity(request)["user_id"],**payload.model_dump()))

@router.get("/media/uploads/{upload_id}")
def upload_status(upload_id: str,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.media.status(identity(request)["user_id"],upload_id))

@router.patch("/media/uploads/{upload_id}")
async def upload_chunk(upload_id: str,request: Request) -> dict[str,Any]:
    user=identity(request); offset=int(request.headers.get("Upload-Offset","-1")); chunk=await request.body()
    return call(lambda: SERVICES.media.append_chunk(user["user_id"],upload_id,offset=offset,chunk=chunk))

@router.post("/media/uploads/{upload_id}/complete")
def complete_upload(upload_id: str,payload: UploadComplete,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.media.complete(identity(request)["user_id"],upload_id,**payload.model_dump()))

@router.get("/media/{media_id}/download")
def download(media_id: str,request: Request):
    user=identity(request); viewer=user["user_id"]
    with SERVICES.database.connection(read_only=True) as db:
        media=db.execute("SELECT * FROM connect_media_objects WHERE media_id=? AND state='available'",(media_id,)).fetchone()
        if not media: raise HTTPException(404,detail="Media not found.")
        authorized=media["owner_id"]==viewer or media["visibility"]=="public"
        if not authorized:
            for row in db.execute("SELECT p.post_id FROM connect_post_attachments a JOIN connect_posts p ON p.post_id=a.post_id WHERE a.media_id=?",(media_id,)):
                try:
                    post=SERVICES.content.get_post(viewer,row["post_id"])
                    if post["download_permission"] != "none": authorized=True; break
                except ConnectError: pass
            if not authorized:
                for row in db.execute("SELECT user_id FROM connect_profiles WHERE profile_image_id=? OR cover_image_id=?",(media_id,media_id)):
                    try: SERVICES.profiles.get(viewer,row["user_id"]); authorized=True; break
                    except ConnectError: pass
        if not authorized: raise HTTPException(403,detail="Download is not permitted.")
        path=SERVICES.media.storage_root.joinpath("objects").resolve(); target=__import__("pathlib").Path(media["storage_path"]).resolve()
        if path not in target.parents or not target.is_file(): raise HTTPException(404,detail="Stored media is unavailable.")
        return FileResponse(target,media_type=media["mime_type"],filename=media["original_name"])

@router.get("/posts/{post_id}/comments")
def comments(post_id: str,request: Request) -> dict[str,Any]:
    items=call(lambda: SERVICES.content.comments(identity(request)["user_id"],post_id)); return {"items":items,"count":len(items)}

@router.post("/posts/{post_id}/comments",status_code=201)
def add_comment(post_id: str,payload: CommentCreate,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.content.add_comment(identity(request)["user_id"],post_id,payload.body,payload.parent_comment_id))

@router.put("/posts/{post_id}/reaction")
def react(post_id: str,payload: ReactionCreate,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.content.react(identity(request)["user_id"],post_id,payload.reaction_type))

@router.put("/posts/{post_id}/bookmark")
def bookmark(post_id: str,payload: BookmarkUpdate,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.content.bookmark(identity(request)["user_id"],post_id,payload.saved))

@router.get("/bookmarks")
def bookmarks(request: Request) -> dict[str,Any]:
    items=SERVICES.content.saved(identity(request)["user_id"]); return {"items":items,"count":len(items)}

@router.post("/posts/{post_id}/repost")
def repost(post_id: str,payload: RepostCreate,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.content.repost(identity(request)["user_id"],post_id,payload.quote,payload.visibility))

@router.post("/moderation/reports",status_code=201)
def report(payload: ReportCreate,request: Request) -> dict[str,Any]:
    return call(lambda: SERVICES.content.report(identity(request)["user_id"],**payload.model_dump()))

@router.get("/notifications")
def notifications(request: Request,limit: int=Query(default=100,ge=1,le=250)) -> dict[str,Any]:
    items=SERVICES.content.notifications(identity(request)["user_id"],limit); return {"items":items,"unread":sum(not i["read_at_utc"] for i in items)}

@router.post("/notifications/read")
def read_notifications(payload: NotificationsRead,request: Request) -> dict[str,Any]:
    return {"updated":SERVICES.content.mark_notifications_read(identity(request)["user_id"],payload.notification_ids)}

# Expanded target routes are registered after the base handlers so they share one service container.
from .complete_api import register_complete_routes
register_complete_routes(router,SERVICES,identity,call)
