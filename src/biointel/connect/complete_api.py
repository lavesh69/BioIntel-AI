from __future__ import annotations

import asyncio
from typing import Any, Literal
from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

class ConversationCreate(BaseModel):
    member_ids:list[str]=Field(default_factory=list,max_length=100)
    conversation_type:Literal["direct","group"]="direct"
    title:str=Field(default="",max_length=200); description:str=Field(default="",max_length=1000)
class MessageCreate(BaseModel):
    body:str=Field(default="",max_length=50000); message_type:str="text"; client_event_id:str=Field(min_length=1,max_length=200)
    parent_message_id:str|None=None; attachment_ids:list[str]=Field(default_factory=list,max_length=20); reference_type:str=""; reference_id:str=""
class ReceiptUpdate(BaseModel): state:Literal["delivered","read"]
class Decision(BaseModel): decision:str; reason:str=""
class CommunityCreate(BaseModel):
    name:str=Field(min_length=3,max_length=120); description:str=""; rules:str=""; visibility:str="public"; join_policy:str="open"; research_fields:list[str]=Field(default_factory=list)
class MemberUpdate(BaseModel): state:str="active"; role:str="member"; ban_reason:str=""
class ChannelCreate(BaseModel): name:str; channel_type:str="discussion"; description:str=""; posting_role:str="member"
class CommunityPostCreate(BaseModel): body:str; title:str=""; channel_id:str|None=None
class GenericCreate(BaseModel): payload:dict[str,Any]=Field(default_factory=dict)
class CollaborationCreate(BaseModel): title:str; objective:str; description:str=""; research_field:str=""; data_modality:str=""; required_skills:list[str]=Field(default_factory=list); deadline_utc:str|None=None; visibility:str="public"
class CollaborationApply(BaseModel): introduction:str; experience:str=""; skills:list[str]=Field(default_factory=list); availability:str=""; proposed_contribution:str=""
class RecommendationFeedback(BaseModel): target_type:str; target_id:str; signal:str; reason:str=""
class ShiroRequest(BaseModel): action:str; prompt:str=""; context:dict[str,Any]=Field(default_factory=dict)
class StoryCreate(BaseModel):
    story_type:str; text_body:str=""; media_id:str|None=None; poll:dict[str,Any]=Field(default_factory=dict); alt_text:str=""; mentions:list[str]=Field(default_factory=list); visibility:str="connections"; reply_permission:str="connections"; warning_text:str=""; owner_type:str="user"; owner_id:str|None=None; hours:int=Field(default=24,ge=1,le=168)
class StoryReaction(BaseModel): reaction_type:str; reply_text:str=""
class HighlightCreate(BaseModel): title:str; story_ids:list[str]
class ShortVideoCreate(BaseModel):
    media_id:str; caption:str=""; transcript:str; alt_text:str; hashtags:list[str]=Field(default_factory=list); research_topics:list[str]=Field(default_factory=list); warning_text:str=""; visibility:str="public"; comments_enabled:bool=True
class LiveCreate(BaseModel): stream_type:str; title:str; description:str=""; scheduled_at_utc:str|None=None; quality:str="auto"; recording_enabled:bool=False; visibility:str="public"
class LiveJoin(BaseModel): recording_consent:bool=False; role:str="viewer"
class LiveModerate(BaseModel): participant_id:str|None=None; comment_id:str|None=None; action:str
class CallCreate(BaseModel): participant_ids:list[str]; call_type:str="video"; title:str=""; scheduled_at_utc:str|None=None; conversation_id:str|None=None; recording_requested:bool=False
class CallRespond(BaseModel): decision:str; microphone:bool=False; camera:bool=False; recording_consent:bool=False
class CallSignal(BaseModel): signal_type:str; signal:dict[str,Any]=Field(default_factory=dict); recipient_id:str|None=None
class EmailTokenCreate(BaseModel): email:str; purpose:str="verify"
class EmailVerify(BaseModel): token:str
class VerificationCreate(BaseModel): verification_type:str; subject_id:str=""; reason:str=""; evidence:list[dict[str,str]]=Field(default_factory=list)
class VerificationDecision(BaseModel): decision:str; rejection_reason:str=""; expires_at_utc:str|None=None
class OnboardingUpdate(BaseModel): step:int=Field(ge=1,le=12); completed:bool=True; skipped:bool=False; checklist:dict[str,Any]=Field(default_factory=dict)
class AccessibilityUpdate(BaseModel): language:str="English"; high_contrast:bool=False; reduced_motion:bool=False; data_saving:bool=False; captions_enabled:bool=True; autoplay_audio:bool=False
class DraftSave(BaseModel): draft_id:str|None=None; body:str=""; title:str=""; post_type:str="text"; attachments:list[str]=Field(default_factory=list); settings:dict[str,Any]=Field(default_factory=dict); autosaved:bool=True
class ScheduleCreate(BaseModel): draft_id:str; scheduled_at_utc:str; timezone_name:str="UTC"; schedule_type:str="post"; target_id:str=""
class DeliveryCreate(BaseModel): recipient_id:str|None=None; category:str; subject_type:str; subject_id:str; message:str; channels:list[str]|None=None; dedupe_key:str|None=None
class PreferencesUpdate(BaseModel): categories:dict[str,bool]=Field(default_factory=dict); channels:dict[str,bool]=Field(default_factory=dict); quiet_hours:dict[str,Any]=Field(default_factory=dict); digest_frequency:str="none"; private_preview_enabled:bool=False
class PostEdit(BaseModel): title:str|None=None; body:str|None=None
class StateUpdate(BaseModel): state:str
class CaseDecision(BaseModel): action:str; resolution:str; duration_seconds:int|None=None
class AppealCreate(BaseModel): reason:str; evidence:dict[str,Any]=Field(default_factory=dict)
class AppealDecision(BaseModel): decision:str; resolution:str
class BackupCreate(BaseModel): backup_type:str="full"
class CleanupRequest(BaseModel): cleanup_type:str="expired_stories"; dry_run:bool=True


def register_complete_routes(router:APIRouter,services:Any,identity_fn:Any,call_fn:Any)->None:
    suite=services.complete
    def uid(request:Any)->str: return str(identity_fn(request)["user_id"])
    def public(data:dict[str,Any])->dict[str,Any]: return {key:value for key,value in data.items() if not key.startswith("_")}

    @router.post("/conversations",status_code=201,response_model=dict[str,Any])
    def create_conversation(payload:ConversationCreate,request:Request): return call_fn(lambda:suite.messaging.create_conversation(uid(request),**payload.model_dump()))
    @router.get("/conversations",response_model=dict[str,Any])
    def conversations(request:Request,limit:int=Query(100,ge=1,le=250)):
        items=call_fn(lambda:suite.messaging.list(uid(request),limit)); return {"items":items,"count":len(items)}
    @router.post("/conversations/requests/{request_id}/respond",response_model=dict[str,Any])
    def message_request_decision(request_id:str,payload:Decision,request:Request): return call_fn(lambda:suite.messaging.respond_request(uid(request),request_id,payload.decision,reason=payload.reason))
    @router.get("/conversations/{conversation_id}/messages",response_model=dict[str,Any])
    def conversation_messages(conversation_id:str,request:Request,after_sequence:int=0,limit:int=Query(100,ge=1,le=250)):
        items=call_fn(lambda:suite.messaging.history(uid(request),conversation_id,after_sequence=after_sequence,limit=limit)); return {"items":items,"count":len(items)}
    @router.post("/conversations/{conversation_id}/messages",status_code=201,response_model=dict[str,Any])
    def send_message(conversation_id:str,payload:MessageCreate,request:Request): return call_fn(lambda:suite.messaging.send(uid(request),conversation_id,**payload.model_dump()))
    @router.put("/messages/{message_id}/receipt",response_model=dict[str,Any])
    def message_receipt(message_id:str,payload:ReceiptUpdate,request:Request): return call_fn(lambda:suite.messaging.update_receipt(uid(request),message_id,payload.state))
    @router.get("/messages/search",response_model=dict[str,Any])
    def search_messages(request:Request,q:str=Query("",max_length=500),conversation_id:str|None=None,limit:int=Query(100,ge=1,le=250)):
        items=call_fn(lambda:suite.messaging.search(uid(request),q,conversation_id=conversation_id,limit=limit)); return {"items":items,"count":len(items)}
    @router.get("/websocket/events",response_model=dict[str,Any])
    def realtime_events(request:Request,after_sequence:int=0,limit:int=Query(100,ge=1,le=250),acknowledge:bool=False):
        items=call_fn(lambda:suite.messaging.events(uid(request),after_sequence=after_sequence,limit=limit,acknowledge=acknowledge)); return {"items":items,"count":len(items)}
    @router.websocket("/websocket")
    async def connect_websocket(websocket:WebSocket):
        await websocket.accept(); user=identity_fn(websocket); user_id=str(user["user_id"]); after=int(websocket.query_params.get("after_sequence","0"))
        try:
            while True:
                events=suite.messaging.events(user_id,after_sequence=after,limit=100,acknowledge=False)
                if events:
                    await websocket.send_json({"events":events}); after=max(int(e["event_sequence"]) for e in events)
                try:
                    message=await asyncio.wait_for(websocket.receive_json(),timeout=1.0)
                    if message.get("type")=="ack": suite.messaging.events(user_id,after_sequence=0,limit=250,acknowledge=True)
                    elif message.get("type")=="typing": suite.messaging.typing(user_id,str(message["conversation_id"]),bool(message.get("active",True)))
                except asyncio.TimeoutError: pass
        except WebSocketDisconnect: return

    @router.post("/communities",status_code=201,response_model=dict[str,Any])
    def create_community(payload:CommunityCreate,request:Request): return call_fn(lambda:suite.communities.create(uid(request),**payload.model_dump()))
    @router.get("/communities",response_model=dict[str,Any])
    def list_communities(request:Request,q:str="",limit:int=Query(50,ge=1,le=100)):
        items=call_fn(lambda:suite.communities.list(uid(request),q,limit)); return {"items":items,"count":len(items)}
    @router.post("/communities/{community_id}/join",response_model=dict[str,Any])
    def join_community(community_id:str,request:Request): return call_fn(lambda:suite.communities.join(uid(request),community_id))
    @router.put("/communities/{community_id}/members/{user_id}",response_model=dict[str,Any])
    def update_community_member(community_id:str,user_id:str,payload:MemberUpdate,request:Request): return call_fn(lambda:suite.communities.set_member(uid(request),community_id,user_id,**payload.model_dump()))
    @router.post("/communities/{community_id}/channels",status_code=201,response_model=dict[str,Any])
    def create_community_channel(community_id:str,payload:ChannelCreate,request:Request): return call_fn(lambda:suite.communities.create_channel(uid(request),community_id,**payload.model_dump()))
    @router.post("/communities/{community_id}/posts",status_code=201,response_model=dict[str,Any])
    def create_community_post(community_id:str,payload:CommunityPostCreate,request:Request): return call_fn(lambda:suite.communities.create_post(uid(request),community_id,**payload.model_dump()))
    @router.post("/collaborations",status_code=201,response_model=dict[str,Any])
    def create_collaboration(payload:CollaborationCreate,request:Request): return call_fn(lambda:suite.collaboration.create_collaboration(uid(request),**payload.model_dump()))
    @router.post("/collaborations/{collaboration_id}/applications",status_code=201,response_model=dict[str,Any])
    def apply_collaboration(collaboration_id:str,payload:CollaborationApply,request:Request): return call_fn(lambda:suite.collaboration.apply(uid(request),collaboration_id,**payload.model_dump()))
    @router.post("/collaborations/applications/{application_id}/decision",response_model=dict[str,Any])
    def collaboration_decision(application_id:str,payload:Decision,request:Request): return call_fn(lambda:suite.collaboration.decide_application(uid(request),application_id,payload.decision))
    @router.post("/projects",status_code=201,response_model=dict[str,Any])
    def create_project(payload:GenericCreate,request:Request): return call_fn(lambda:suite.collaboration.create_project(uid(request),**payload.payload))
    @router.post("/projects/{project_id}/members/{user_id}",response_model=dict[str,Any])
    def add_project_member(project_id:str,user_id:str,payload:MemberUpdate,request:Request): return call_fn(lambda:suite.collaboration.add_project_member(uid(request),project_id,user_id,payload.role))
    @router.post("/publications",status_code=201,response_model=dict[str,Any])
    def create_publication(payload:GenericCreate,request:Request): return call_fn(lambda:suite.collaboration.create_publication(uid(request),**payload.payload))
    @router.post("/datasets",status_code=201,response_model=dict[str,Any])
    def create_dataset(payload:GenericCreate,request:Request): return call_fn(lambda:suite.collaboration.create_dataset(uid(request),**payload.payload))
    @router.post("/datasets/{dataset_id}/access",status_code=201,response_model=dict[str,Any])
    def request_dataset_access(dataset_id:str,payload:GenericCreate,request:Request): return call_fn(lambda:suite.collaboration.request_dataset_access(uid(request),dataset_id,**payload.payload))
    @router.post("/datasets/access/{access_request_id}/decision",response_model=dict[str,Any])
    def decide_dataset_access(access_request_id:str,payload:GenericCreate,request:Request): return call_fn(lambda:suite.collaboration.decide_dataset_access(uid(request),access_request_id,**payload.payload))
    @router.post("/workflows",status_code=201,response_model=dict[str,Any])
    def create_workflow(payload:GenericCreate,request:Request): return call_fn(lambda:suite.collaboration.create_workflow(uid(request),**payload.payload))
    @router.post("/workflows/{workflow_id}/fork",status_code=201,response_model=dict[str,Any])
    def fork_workflow(workflow_id:str,request:Request): return call_fn(lambda:suite.collaboration.fork_workflow(uid(request),workflow_id))
    @router.post("/events",status_code=201,response_model=dict[str,Any])
    def create_event(payload:GenericCreate,request:Request): return call_fn(lambda:suite.collaboration.create_event(uid(request),**payload.payload))
    @router.post("/events/{event_id}/register",response_model=dict[str,Any])
    def register_event(event_id:str,request:Request): return call_fn(lambda:suite.collaboration.register_event(uid(request),event_id))
    @router.post("/opportunities",status_code=201,response_model=dict[str,Any])
    def create_opportunity(payload:GenericCreate,request:Request): return call_fn(lambda:suite.collaboration.create_opportunity(uid(request),**payload.payload))
    for resource_kind in ("collaborations","projects","publications","datasets","workflows","events","opportunities"):
        path=f"/{resource_kind}"
        async def resource_list(request:Request,q:str="",limit:int=Query(50,ge=1,le=100),_kind:str=resource_kind):
            items=call_fn(lambda:suite.collaboration.list_resources(uid(request),_kind,q,limit)); return {"items":items,"count":len(items)}
        router.add_api_route(path,resource_list,methods=["GET"],response_model=dict[str,Any],name=f"list_{resource_kind}")
    @router.get("/search",response_model=dict[str,Any])
    def complete_search(request:Request,q:str=Query("",max_length=500),types:list[str]|None=Query(None),limit:int=Query(20,ge=1,le=100)): return call_fn(lambda:suite.discovery.search(uid(request),q,types,limit))
    @router.get("/recommendations",response_model=dict[str,Any])
    def recommendations(request:Request,kind:str="people",limit:int=Query(10,ge=1,le=50)):
        items=call_fn(lambda:suite.discovery.recommend(uid(request),kind,limit)); return {"items":items,"count":len(items),"explainable":True}
    @router.post("/recommendations/feedback",response_model=dict[str,Any])
    def recommendation_feedback(payload:RecommendationFeedback,request:Request): return call_fn(lambda:suite.discovery.feedback(uid(request),**payload.model_dump()))
    @router.post("/shiro",response_model=dict[str,Any])
    def shiro_assist(payload:ShiroRequest,request:Request): return call_fn(lambda:suite.shiro.assist(uid(request),**payload.model_dump()))

    @router.post("/stories",status_code=201,response_model=dict[str,Any])
    def create_story(payload:StoryCreate,request:Request): return call_fn(lambda:suite.stories.create(uid(request),**payload.model_dump()))
    @router.get("/stories",response_model=dict[str,Any])
    def story_feed(request:Request,limit:int=Query(100,ge=1,le=200)):
        items=call_fn(lambda:suite.stories.feed(uid(request),limit)); return {"items":items,"count":len(items)}
    @router.post("/stories/{story_id}/view",response_model=dict[str,Any])
    def view_story(story_id:str,request:Request): return call_fn(lambda:suite.stories.view(uid(request),story_id))
    @router.post("/stories/{story_id}/reactions",response_model=dict[str,Any])
    def react_story(story_id:str,payload:StoryReaction,request:Request): return call_fn(lambda:suite.stories.react(uid(request),story_id,**payload.model_dump()))
    @router.post("/story-highlights",status_code=201,response_model=dict[str,Any])
    def create_highlight(payload:HighlightCreate,request:Request): return call_fn(lambda:suite.stories.highlight(uid(request),payload.title,payload.story_ids))
    @router.post("/short-videos",status_code=201,response_model=dict[str,Any])
    def create_short_video(payload:ShortVideoCreate,request:Request): return call_fn(lambda:suite.short_videos.create(uid(request),**payload.model_dump()))
    @router.get("/short-videos",response_model=dict[str,Any])
    def short_video_feed(request:Request,limit:int=Query(50,ge=1,le=100)):
        items=call_fn(lambda:suite.short_videos.feed(uid(request),limit)); return {"items":items,"count":len(items),"autoplay_audio":False}
    @router.post("/live-streams",status_code=201,response_model=dict[str,Any])
    def create_live(payload:LiveCreate,request:Request): return call_fn(lambda:suite.live_streams.create(uid(request),**payload.model_dump()))
    @router.post("/live-streams/{stream_id}/start",response_model=dict[str,Any])
    def start_live(stream_id:str,request:Request): return call_fn(lambda:suite.live_streams.start(uid(request),stream_id))
    @router.post("/live-streams/{stream_id}/join",response_model=dict[str,Any])
    def join_live(stream_id:str,payload:LiveJoin,request:Request): return call_fn(lambda:suite.live_streams.join(uid(request),stream_id,**payload.model_dump()))
    @router.post("/live-streams/{stream_id}/moderate",response_model=dict[str,Any])
    def moderate_live(stream_id:str,payload:LiveModerate,request:Request): return call_fn(lambda:suite.live_streams.moderate(uid(request),stream_id,**payload.model_dump()))
    @router.post("/live-streams/{stream_id}/end",response_model=dict[str,Any])
    def end_live(stream_id:str,request:Request): return call_fn(lambda:suite.live_streams.end(uid(request),stream_id))
    @router.post("/calls",status_code=201,response_model=dict[str,Any])
    def create_call(payload:CallCreate,request:Request): return call_fn(lambda:suite.calls.create(uid(request),**payload.model_dump()))
    @router.post("/calls/{call_id}/respond",response_model=dict[str,Any])
    def respond_call(call_id:str,payload:CallRespond,request:Request): return call_fn(lambda:suite.calls.respond(uid(request),call_id,**payload.model_dump()))
    @router.post("/calls/{call_id}/start",response_model=dict[str,Any])
    def start_call(call_id:str,request:Request): return call_fn(lambda:suite.calls.start(uid(request),call_id))
    @router.post("/calls/{call_id}/screen-share",response_model=dict[str,Any])
    def screen_share_call(call_id:str,enabled:bool,request:Request): return call_fn(lambda:suite.calls.screen_share(uid(request),call_id,enabled))
    @router.get("/calls/client",response_class=HTMLResponse)
    def call_browser_client(request:Request):
        uid(request); return HTMLResponse((Path(__file__).with_name("webrtc_client.html")).read_text(encoding="utf-8"))
    @router.get("/calls/capabilities",response_model=dict[str,Any])
    def call_capabilities(request:Request): uid(request); return suite.calls.capabilities()
    @router.get("/calls/ice-configuration",response_model=dict[str,Any])
    def call_ice_configuration(request:Request): uid(request); return suite.calls.ice_configuration()
    @router.get("/calls/{call_id}",response_model=dict[str,Any])
    def call_state(call_id:str,request:Request): return call_fn(lambda:suite.calls.state(uid(request),call_id))
    @router.post("/calls/{call_id}/signals",status_code=201,response_model=dict[str,Any])
    def send_call_signal(call_id:str,payload:CallSignal,request:Request): return call_fn(lambda:suite.calls.signal(uid(request),call_id,payload.signal_type,payload.signal,payload.recipient_id))
    @router.get("/calls/{call_id}/signals",response_model=dict[str,Any])
    def receive_call_signals(call_id:str,request:Request,after_created_at:str="",limit:int=Query(100,ge=1,le=250)):
        items=call_fn(lambda:suite.calls.signals(uid(request),call_id,after_created_at,limit)); return {"items":items,"count":len(items)}
    @router.post("/calls/{call_id}/leave",response_model=dict[str,Any])
    def leave_call(call_id:str,request:Request): return call_fn(lambda:suite.calls.leave(uid(request),call_id))
    @router.post("/calls/{call_id}/end",response_model=dict[str,Any])
    def end_call(call_id:str,request:Request): return call_fn(lambda:suite.calls.end(uid(request),call_id))
    @router.post("/documents",status_code=201,response_model=dict[str,Any])
    def create_document(payload:GenericCreate,request:Request): return call_fn(lambda:suite.documents.create(uid(request),**payload.payload))
    @router.post("/documents/{document_id}/revisions",response_model=dict[str,Any])
    def revise_document(document_id:str,payload:GenericCreate,request:Request): return call_fn(lambda:suite.documents.apply_crdt_patch(uid(request),document_id,**payload.payload))
    @router.post("/documents/{document_id}/exports",response_model=dict[str,Any])
    def export_document(document_id:str,payload:GenericCreate,request:Request): return public(call_fn(lambda:suite.documents.export(uid(request),document_id,**payload.payload)))
    @router.post("/notebooks/entries",status_code=201,response_model=dict[str,Any])
    def create_notebook_entry(payload:GenericCreate,request:Request): return call_fn(lambda:suite.notebooks.create_entry(uid(request),**payload.payload))
    @router.post("/notebooks/entries/{entry_id}/sign",response_model=dict[str,Any])
    def sign_notebook_entry(entry_id:str,request:Request): return call_fn(lambda:suite.notebooks.lock_and_sign(uid(request),entry_id))
    @router.post("/data-rooms",status_code=201,response_model=dict[str,Any])
    def create_data_room(payload:GenericCreate,request:Request): return call_fn(lambda:suite.data_rooms.create(uid(request),**payload.payload))
    @router.post("/data-rooms/{room_id}/agreement",response_model=dict[str,Any])
    def accept_data_room_agreement(room_id:str,request:Request): return call_fn(lambda:suite.data_rooms.accept_agreement(uid(request),room_id))
    @router.post("/projects/{project_id}/tasks",status_code=201,response_model=dict[str,Any])
    def create_project_task(project_id:str,payload:GenericCreate,request:Request): return call_fn(lambda:suite.planning.create_task(uid(request),project_id,**payload.payload))
    @router.put("/tasks/{task_id}/status",response_model=dict[str,Any])
    def set_task_status(task_id:str,payload:StateUpdate,request:Request): return call_fn(lambda:suite.planning.set_task_status(uid(request),task_id,payload.state))
    @router.get("/projects/{project_id}/progress",response_model=dict[str,Any])
    def project_progress(project_id:str,request:Request): return call_fn(lambda:suite.planning.progress(uid(request),project_id))
    @router.post("/grants/opportunities",status_code=201,response_model=dict[str,Any])
    def add_grant(payload:GenericCreate,request:Request): uid(request); return call_fn(lambda:suite.grants.add_opportunity(**payload.payload))
    @router.post("/grants/proposals",status_code=201,response_model=dict[str,Any])
    def create_grant_proposal(payload:GenericCreate,request:Request): return call_fn(lambda:suite.grants.create_proposal(uid(request),**payload.payload))
    @router.post("/preprints",status_code=201,response_model=dict[str,Any])
    def submit_preprint(payload:GenericCreate,request:Request): return call_fn(lambda:suite.preprints.submit_preprint(uid(request),**payload.payload))
    @router.post("/marketplace/listings",status_code=201,response_model=dict[str,Any])
    def create_marketplace_listing(payload:GenericCreate,request:Request): return call_fn(lambda:suite.marketplace.create_listing(uid(request),**payload.payload))
    @router.post("/equipment",status_code=201,response_model=dict[str,Any])
    def register_equipment(payload:GenericCreate,request:Request): return call_fn(lambda:suite.equipment.register_equipment(uid(request),**payload.payload))
    @router.post("/events/advanced",status_code=201,response_model=dict[str,Any])
    def create_advanced_event(payload:GenericCreate,request:Request): return call_fn(lambda:suite.events.create_conference(uid(request),**payload.payload))
    @router.post("/developer/api-keys",status_code=201,response_model=dict[str,Any])
    def create_developer_key(payload:GenericCreate,request:Request): return call_fn(lambda:suite.developer.create_api_key(uid(request),**payload.payload))
    @router.post("/developer/webhooks",status_code=201,response_model=dict[str,Any])
    def register_webhook(payload:GenericCreate,request:Request): return call_fn(lambda:suite.webhooks.register_webhook(uid(request),**payload.payload))
    @router.get("/analytics/me",response_model=dict[str,Any])
    def my_connect_analytics(request:Request): return call_fn(lambda:suite.analytics.get_user_analytics(uid(request)))
    @router.get("/analytics/trends",response_model=dict[str,Any])
    def connect_trends(request:Request,category:str="topics"):
        uid(request); items=call_fn(lambda:suite.trends.discover_trends(category)); return {"items":items,"count":len(items)}
    @router.post("/preservation/bundles",status_code=201,response_model=dict[str,Any])
    def create_preservation_bundle(payload:GenericCreate,request:Request): return public(call_fn(lambda:suite.preservation.create_reproducibility_bundle(uid(request),**payload.payload)))
    @router.get("/preservation/bundles/{bundle_id}/verify",response_model=dict[str,Any])
    def verify_preservation_bundle(bundle_id:str,request:Request): return call_fn(lambda:suite.preservation.verify_bundle(uid(request),bundle_id))
    @router.post("/verifications/email/token",status_code=201,response_model=dict[str,Any])
    def email_token(payload:EmailTokenCreate,request:Request): return call_fn(lambda:suite.verification.issue_email_token(uid(request),payload.email,payload.purpose))
    @router.post("/verifications/email/confirm",response_model=dict[str,Any])
    def email_confirm(payload:EmailVerify,request:Request): return call_fn(lambda:suite.verification.verify_email(uid(request),payload.token))
    @router.post("/verifications",status_code=201,response_model=dict[str,Any])
    def verification_submit(payload:VerificationCreate,request:Request): return call_fn(lambda:suite.verification.submit(uid(request),payload.verification_type,subject_id=payload.subject_id,reason=payload.reason,evidence=payload.evidence))
    @router.post("/verifications/{request_id}/decision",response_model=dict[str,Any])
    def verification_decision(request_id:str,payload:VerificationDecision,request:Request): return call_fn(lambda:suite.verification.decide(uid(request),request_id,**payload.model_dump()))
    @router.get("/onboarding",response_model=dict[str,Any])
    def onboarding_progress(request:Request): return call_fn(lambda:suite.onboarding.progress(uid(request)))
    @router.put("/onboarding",response_model=dict[str,Any])
    def onboarding_update(payload:OnboardingUpdate,request:Request): return call_fn(lambda:suite.onboarding.update(uid(request),**payload.model_dump()))
    @router.get("/accessibility",response_model=dict[str,Any])
    def accessibility_preferences(request:Request): return call_fn(lambda:suite.accessibility.preferences(uid(request)))
    @router.put("/accessibility",response_model=dict[str,Any])
    def accessibility_update(payload:AccessibilityUpdate,request:Request): return call_fn(lambda:suite.accessibility.update(uid(request),**payload.model_dump()))
    @router.post("/drafts",status_code=201,response_model=dict[str,Any])
    def save_draft(payload:DraftSave,request:Request):
        data=payload.model_dump(); draft_id=data.pop("draft_id"); return call_fn(lambda:suite.drafts.save(uid(request),draft_id=draft_id,**data))
    @router.post("/scheduled-posts",status_code=201,response_model=dict[str,Any])
    def schedule_post(payload:ScheduleCreate,request:Request): return call_fn(lambda:suite.drafts.schedule(uid(request),**payload.model_dump()))
    @router.post("/scheduled-posts/publish-due",response_model=dict[str,Any])
    def publish_due(request:Request): suite.admin.require(uid(request),False); return call_fn(lambda:suite.drafts.publish_due())
    @router.get("/notification-delivery/preferences",response_model=dict[str,Any])
    def notification_preferences(request:Request): return call_fn(lambda:suite.delivery.preferences(uid(request)))
    @router.put("/notification-delivery/preferences",response_model=dict[str,Any])
    def update_notification_preferences(payload:PreferencesUpdate,request:Request): return call_fn(lambda:suite.delivery.update_preferences(uid(request),**payload.model_dump()))
    @router.post("/notification-delivery",status_code=201,response_model=dict[str,Any])
    def queue_delivery(payload:DeliveryCreate,request:Request):
        data=payload.model_dump(); recipient=data.pop("recipient_id") or uid(request); return call_fn(lambda:suite.delivery.queue(recipient,actor_id=uid(request),**data))
    @router.post("/notification-delivery/process",response_model=dict[str,Any])
    def process_delivery(request:Request): suite.admin.require(uid(request),False); return call_fn(lambda:suite.delivery.deliver_due())
    @router.put("/posts/{post_id}/lifecycle",response_model=dict[str,Any])
    def post_lifecycle(post_id:str,payload:StateUpdate,request:Request): return call_fn(lambda:suite.lifecycle.set_state(uid(request),post_id,payload.state))
    @router.patch("/posts/{post_id}",response_model=dict[str,Any])
    def edit_post(post_id:str,payload:PostEdit,request:Request): return call_fn(lambda:suite.lifecycle.edit_post(uid(request),post_id,**payload.model_dump()))
    @router.get("/posts/{post_id}/versions",response_model=dict[str,Any])
    def post_versions(post_id:str,request:Request):
        items=call_fn(lambda:suite.lifecycle.versions(uid(request),post_id)); return {"items":items,"count":len(items)}
    @router.get("/admin",response_model=dict[str,Any])
    def admin_dashboard(request:Request): return call_fn(lambda:suite.admin.dashboard(uid(request)))
    @router.get("/admin/moderation/cases",response_model=dict[str,Any])
    def admin_cases(request:Request,state:str="open",limit:int=Query(100,ge=1,le=250)):
        items=call_fn(lambda:suite.admin.cases(uid(request),state,limit)); return {"items":items,"count":len(items)}
    @router.post("/admin/moderation/cases/{case_id}/decision",response_model=dict[str,Any])
    def admin_case_decision(case_id:str,payload:CaseDecision,request:Request): return call_fn(lambda:suite.admin.decide_case(uid(request),case_id,**payload.model_dump()))
    @router.post("/admin/moderation/cases/{case_id}/appeals",status_code=201,response_model=dict[str,Any])
    def create_appeal(case_id:str,payload:AppealCreate,request:Request): return call_fn(lambda:suite.admin.appeal(uid(request),case_id,payload.reason,payload.evidence))
    @router.post("/admin/moderation/appeals/{appeal_id}/decision",response_model=dict[str,Any])
    def appeal_decision(appeal_id:str,payload:AppealDecision,request:Request): return call_fn(lambda:suite.admin.decide_appeal(uid(request),appeal_id,**payload.model_dump()))
    @router.post("/admin/backups",status_code=201,response_model=dict[str,Any])
    def create_backup(payload:BackupCreate,request:Request): return call_fn(lambda:suite.operations.create_backup(uid(request),payload.backup_type))
    @router.post("/admin/backups/{backup_id}/restore-test",response_model=dict[str,Any])
    def restore_test(backup_id:str,request:Request): return call_fn(lambda:suite.operations.validate_restore(uid(request),backup_id))
    @router.post("/admin/cleanup",response_model=dict[str,Any])
    def admin_cleanup(payload:CleanupRequest,request:Request): return call_fn(lambda:suite.operations.cleanup(uid(request),**payload.model_dump()))
    @router.get("/health",response_model=dict[str,Any])
    def connect_health(request:Request): uid(request); return call_fn(lambda:suite.operations.health())
    @router.get("/health/live",response_model=dict[str,Any])
    def connect_liveness(): return {"live":True,"service":"connect"}
    @router.get("/health/ready",response_model=dict[str,Any])
    def connect_readiness(request:Request): uid(request); result=call_fn(lambda:suite.operations.health()); return {"ready":result["ready"],"status":result["status"],"checked_at_utc":result["checked_at_utc"]}





