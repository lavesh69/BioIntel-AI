from __future__ import annotations

import json, uuid
from pathlib import Path
from typing import Any
import streamlit as st
from .ui import context, header, run
from biointel.ui.frontend_v10 import empty_state, section_header

TEXT={
 "English":{"save":"Save preferences","language":"Language","access":"Accessibility & notifications"},
 "Hindi":{"save":"Preferences save karein","language":"Bhasha","access":"Accessibility aur notifications"},
 "Hinglish":{"save":"Preferences save karo","language":"Language","access":"Accessibility & notifications"},
}
def _suite(root:Path):
    services,user=context(root); return services,user,services.complete

def render_messages(root:Path)->None:
    services,user,suite=_suite(root); header("Messages","Durable direct and group scientific conversations with requests, receipts and offline replay.")
    with st.container(border=True):
        st.subheader("Start a conversation")
        people=services.profiles.search(user["user_id"],"",100); choices={f"{p['full_name']} (@{p['username']})":p["user_id"] for p in people if p["user_id"]!=user["user_id"]}
        selected=st.multiselect("Researchers",list(choices)); conversation_type=st.segmented_control("Type",["direct","group"],default="direct"); title=st.text_input("Group title",disabled=conversation_type!="group")
        if st.button("Create conversation",type="primary",icon=":material/add_comment:"):
            result=run(lambda:suite.messaging.create_conversation(user["user_id"],[choices[x] for x in selected],conversation_type=conversation_type or "direct",title=title),"Conversation created")
            if result: st.session_state["connect_conversation_id"]=result["conversation_id"]; st.rerun()
    conversations=run(lambda:suite.messaging.list(user["user_id"],100),"") or []
    if not conversations:
        empty_state("No conversations yet", "Connected researchers can exchange durable messages; other contacts begin with a request.", icon="✉", action_hint="Choose researchers above and create the first conversation.")
        return
    labels={f"{c.get('title') or c['conversation_type']} · {c['conversation_id'][-8:]}":c["conversation_id"] for c in conversations}
    current=st.selectbox("Conversation",list(labels),key="connect_message_conversation"); cid=labels[current]
    history=run(lambda:suite.messaging.history(user["user_id"],cid,limit=200),"") or []
    for message in history:
        role="user" if message["sender_id"]==user["user_id"] else "assistant"
        with st.chat_message(role):
            st.markdown(message["body"] or f"*{message['message_type']} attachment*"); st.caption(f"Sequence {message['sequence']} · {message['delivery_state']}")
    prompt=st.chat_input("Message your scientific collaborator")
    if prompt:
        result=run(lambda:suite.messaging.send(user["user_id"],cid,prompt,client_event_id=str(uuid.uuid4())),"Message sent")
        if result: st.rerun()


def render_communities(root:Path)->None:
    services,user,suite=_suite(root); header("Scientific communities","Create moderated research spaces with channels, membership policies and role-based posting.")
    create_tab,browse_tab=st.tabs(["Create","Browse"])
    with create_tab:
        with st.form("community_create"):
            name=st.text_input("Community name",max_chars=120); description=st.text_area("Description",max_chars=5000); rules=st.text_area("Rules",max_chars=10000)
            visibility=st.selectbox("Visibility",["public","private","invite_only","institution_members","verified_members"]); policy=st.selectbox("Join policy",["open","approval","invite_only"])
            submitted=st.form_submit_button("Create community",type="primary",icon=":material/groups:")
        if submitted:
            if run(lambda:suite.communities.create(user["user_id"],name=name,description=description,rules=rules,visibility=visibility,join_policy=policy),"Community created"): st.rerun()
    with browse_tab:
        query=st.text_input("Search communities",placeholder="Genomics, microbiome, bioinformatics…"); items=run(lambda:suite.communities.list(user["user_id"],query,100),"") or []
        for item in items:
            with st.container(border=True):
                st.subheader(item["name"]); st.caption(f"{item['member_count']} members · {item['visibility']} · {item['join_policy']}"); st.write(item["description"] or "Scientific community")
                membership=suite.communities.membership(item["community_id"],user["user_id"])
                if membership: st.badge(membership["state"].replace("_"," ").title(),color="green" if membership["state"]=="active" else "orange")
                elif st.button("Join",key=f"join_{item['community_id']}",icon=":material/person_add:"):
                    if run(lambda item=item:suite.communities.join(user["user_id"],item["community_id"]),"Membership updated"): st.rerun()


def render_discover_collaborate(root:Path)->None:
    services,user,suite=_suite(root); header("Discover and collaborate","Permission-aware search, explainable recommendations and scientific resource publishing.")
    search_tab,recommend_tab,create_tab=st.tabs(["Search","Recommendations","Create resource"])
    with search_tab:
        query=st.text_input("Search BioIntel Connect",placeholder="Researcher, project, dataset, workflow…")
        types=st.pills("Types",["people","posts","communities","projects","publications","datasets","workflows","events","opportunities"],selection_mode="multi",default=["people","projects","datasets"])
        result=run(lambda:suite.discovery.search(user["user_id"],query,list(types or []),50),"")
        if result:
            st.metric("Visible results",result["count"],border=True)
            for kind,items in result["results"].items():
                if items:
                    with st.expander(f"{kind.replace('_',' ').title()} ({len(items)})"):
                        st.dataframe(items,hide_index=True)
    with recommend_tab:
        kind=st.segmented_control("Recommend",["people","communities","projects","datasets","workflows","opportunities"],default="people")
        for item in run(lambda:suite.discovery.recommend(user["user_id"],kind or "people",20),"") or []:
            with st.container(border=True): st.markdown(f"**{item['reason']}**"); st.caption(f"Explainable score: {item['score']} · {item['target_type']}"); st.json(item["item"],expanded=False)
    with create_tab:
        resource=st.selectbox("Resource type",["Collaboration request","Research project","Publication","Dataset","Workflow","Event","Opportunity"])
        title=st.text_input("Title",key="resource_title"); description=st.text_area("Description or objective",key="resource_description")
        if st.button("Create scientific resource",type="primary",icon=":material/science:"):
            creators={
              "Collaboration request":lambda:suite.collaboration.create_collaboration(user["user_id"],title=title,objective=description),
              "Research project":lambda:suite.collaboration.create_project(user["user_id"],title=title,abstract=description),
              "Publication":lambda:suite.collaboration.create_publication(user["user_id"],title=title,authors=[user["display_name"]],authorship_confirmed=True,abstract=description),
              "Dataset":lambda:suite.collaboration.create_dataset(user["user_id"],title=title,description=description),
              "Workflow":lambda:suite.collaboration.create_workflow(user["user_id"],name=title,scientific_purpose=description),
              "Event":lambda:suite.collaboration.create_event(user["user_id"],event_type="scientific_event",title=title,description=description,starts_at_utc="2099-01-01T00:00:00+00:00"),
              "Opportunity":lambda:suite.collaboration.create_opportunity(user["user_id"],opportunity_type="collaboration",title=title,description=description),
            }
            if run(creators[resource],"Resource created"): st.success("Resource created and added to permission-aware discovery.",icon=":material/check_circle:")
def render_stories_videos(root:Path)->None:
    services,user,suite=_suite(root); header("Stories and short videos","24-hour research stories and accessible short-form scientific video. Audio never autoplays.")
    story_tab,video_tab=st.tabs(["Stories","Short videos"])
    with story_tab:
        with st.form("story_create"):
            story_type=st.selectbox("Story type",["text","research_update","poll","link","image","video"]); body=st.text_area("Story update",max_chars=5000); media_id=st.text_input("Uploaded media ID (optional)"); alt=st.text_input("Alt text for media"); visibility=st.selectbox("Story visibility",["connections","followers","public","only_me"]); submitted=st.form_submit_button("Share story",type="primary",icon=":material/auto_stories:")
        if submitted:
            if run(lambda:suite.stories.create(user["user_id"],story_type=story_type,text_body=body,media_id=media_id or None,alt_text=alt,visibility=visibility),"Story shared"): st.rerun()
        stories=run(lambda:suite.stories.feed(user["user_id"],100),"") or []
        with st.container(horizontal=True): st.metric("Active stories",len(stories),border=True); st.metric("Expiry","24 hours",border=True); st.metric("Audio autoplay","Off",border=True)
        for item in stories:
            with st.container(border=True):
                st.markdown(item["text_body"] or f"**{item['story_type'].replace('_',' ').title()}**"); st.caption(f"Expires {item['expires_at_utc']} · {item['visibility']}")
                if item["warning_text"]: st.warning(item["warning_text"],icon=":material/warning:")
                if st.button("Mark viewed",key=f"story_view_{item['story_id']}",icon=":material/visibility:"): run(lambda item=item:suite.stories.view(user["user_id"],item["story_id"]),"Viewed")
    with video_tab:
        st.info("Upload video through Create post first, then paste its media ID. Transcript and alt text are mandatory.",icon=":material/accessibility_new:")
        with st.form("short_video_create"):
            media=st.text_input("Video media ID"); caption=st.text_area("Caption"); transcript=st.text_area("Transcript",help="Required for accessible playback"); alt_text=st.text_input("Alt text",help="Required"); comments=st.toggle("Allow comments",value=True); submit=st.form_submit_button("Publish short video",type="primary",icon=":material/movie:")
        if submit: run(lambda:suite.short_videos.create(user["user_id"],media_id=media,caption=caption,transcript=transcript,alt_text=alt_text,comments_enabled=comments),"Short video published")
        for item in run(lambda:suite.short_videos.feed(user["user_id"],50),"") or []:
            with st.container(border=True): st.subheader(item["caption"] or "Scientific short video"); st.caption("Audio autoplay off · captions available"); st.text_area("Transcript",item["transcript"],disabled=True,key=f"transcript_{item['short_video_id']}")


def render_live_calls(root:Path)->None:
    services,user,suite=_suite(root); header("Live and calls","Consent-aware live science, video/audio meetings and screen sharing with waiting-room controls.")
    live_tab,call_tab=st.tabs(["Live streams","Calls"])
    with live_tab:
        with st.form("live_create"):
            stream_type=st.selectbox("Live format",["webinar","lab_meeting","journal_club","conference","ask_an_expert","community_live"]); title=st.text_input("Live title"); description=st.text_area("Description"); recording=st.toggle("Request recording",help="Every participant must consent before joining"); submit=st.form_submit_button("Create live room",type="primary",icon=":material/live_tv:")
        if submit:
            result=run(lambda:suite.live_streams.create(user["user_id"],stream_type=stream_type,title=title,description=description,recording_enabled=recording),"Live room created")
            if result: st.session_state["connect_live_id"]=result["live_stream_id"]
        live_id=st.text_input("Live stream ID",value=st.session_state.get("connect_live_id",""));
        with st.container(horizontal=True):
            if st.button("Start live",disabled=not live_id,icon=":material/play_arrow:"): run(lambda:suite.live_streams.start(user["user_id"],live_id),"Stream started")
            if st.button("End live",disabled=not live_id,icon=":material/stop:"): run(lambda:suite.live_streams.end(user["user_id"],live_id),"Stream ended")
    with call_tab:
        capabilities=suite.calls.capabilities()
        st.warning("Qualified mode: small-room peer-to-peer mesh. TURN, SFU, recording, and transcription remain unavailable until configured and independently verified.",icon=":material/warning:")
        with st.container(horizontal=True):
            st.metric("Topology",capabilities["topology"],border=True); st.metric("Mesh limit",capabilities["max_peer_participants"],border=True); st.metric("TURN","Configured" if capabilities["turn"]["configured"] else "Not configured",border=True); st.metric("Recording",capabilities["recording"]["status"],border=True)
        people=services.profiles.search(user["user_id"],"",100); choices={f"{p['full_name']} (@{p['username']})":p["user_id"] for p in people if p["user_id"]!=user["user_id"]}; selected=st.multiselect("Invite researchers",list(choices),key="call_people"); call_type=st.segmented_control("Call type",["audio","video","screen_share","meeting"],default="video")
        st.toggle("Request call recording",value=False,disabled=True,help="Unavailable: no verified recorder is configured. No recording state or file will be fabricated.")
        if st.button("Create invitation",type="primary",icon=":material/video_call:"):
            result=run(lambda:suite.calls.create(user["user_id"],[choices[x] for x in selected],call_type=call_type or "video",recording_requested=False),"Call invitation created")
            if result: st.session_state["connect_call_id"]=result["call_id"]
        call_id=st.text_input("Call ID",value=st.session_state.get("connect_call_id","")); decision=st.segmented_control("Invitation response",["accepted","rejected","busy"],default="accepted")
        with st.container(horizontal=True):
            if st.button("Respond",disabled=not call_id,icon=":material/how_to_reg:"): run(lambda:suite.calls.respond(user["user_id"],call_id,decision or "accepted"),"Response saved")
            if st.button("Start accepted call",disabled=not call_id,icon=":material/call:"): run(lambda:suite.calls.start(user["user_id"],call_id),"Call started")
            if st.button("Leave",disabled=not call_id,icon=":material/call_end:"): run(lambda:suite.calls.leave(user["user_id"],call_id),"Left call")
            if st.button("End for all",disabled=not call_id,icon=":material/stop_circle:"): run(lambda:suite.calls.end(user["user_id"],call_id),"Call ended")
        st.info("After the API service is running, open `/api/v1/connect/calls/client` in an authenticated browser. Confirm devices on the pre-join screen, enter this Call ID, then connect from two independent browser sessions.",icon=":material/open_in_new:")
        if call_id:
            state=run(lambda:suite.calls.state(user["user_id"],call_id),"")
            if state: st.dataframe(state["participants"],hide_index=True,width="stretch")

def render_onboarding_verification(root:Path)->None:
    services,user,suite=_suite(root); header("Onboarding and verification","Resume a 12-step scientific profile journey and submit evidence-based verification requests.")
    onboarding_tab,verification_tab=st.tabs(["Onboarding","Verification"])
    with onboarding_tab:
        progress=suite.onboarding.progress(user["user_id"]); st.progress(progress["completion_percent"]/100,text=f"{progress['completion_percent']}% complete")
        steps=["Create account","Verify email","Select language","Professional profile","Research fields","Scientific skills","Institution or laboratory","Connect ORCID","Collaboration interests","Privacy defaults","Follow researchers","Join communities"]
        step=st.selectbox("Current step",range(1,13),format_func=lambda n:f"{n}. {steps[n-1]}",index=max(0,int(progress["current_step"])-1)); action=st.segmented_control("Step action",["Complete","Skip"],default="Complete")
        if st.button("Save onboarding progress",type="primary",icon=":material/checklist:"):
            if run(lambda:suite.onboarding.update(user["user_id"],step,completed=action=="Complete",skipped=action=="Skip"),"Progress saved"): st.rerun()
    with verification_tab:
        token_tab,request_tab=st.tabs(["Email","Professional"])
        with token_tab:
            email=st.text_input("Professional email");
            if st.button("Create verification token",icon=":material/mail:"):
                result=run(lambda:suite.verification.issue_email_token(user["user_id"],email),"Token issued")
                if result: st.code(result["token"],language=None); st.caption("Local/offline adapter token shown for this build. Production provider integration can deliver it externally.")
            token=st.text_input("Verification token",type="password");
            if st.button("Verify email",disabled=not token,icon=":material/verified:"): run(lambda:suite.verification.verify_email(user["user_id"],token),"Email verified")
        with request_tab:
            kind=st.selectbox("Verification type",["researcher","orcid","institution","laboratory","organization","identity"]); reason=st.text_area("Reason and redacted evidence summary")
            if st.button("Submit for review",type="primary",icon=":material/fact_check:"): run(lambda:suite.verification.submit(user["user_id"],kind,reason=reason,evidence=[{"type":"summary","summary":reason,"value":reason}]),"Verification submitted")
def render_admin_operations(root:Path)->None:
    services,user,suite=_suite(root); header("Connect administration","Role-gated moderation, delivery queues, encrypted backup drills, health alerts and cleanup previews.")
    dashboard=run(lambda:suite.admin.dashboard(user["user_id"]),"")
    if not dashboard: st.warning("Administrator, moderator or local-operator role required.",icon=":material/admin_panel_settings:"); return
    with st.container(horizontal=True):
        for label,key in [("Users","users"),("Open reports","open_reports"),("Verification queue","pending_verifications"),("Delivery queue","queued_deliveries")]: st.metric(label,dashboard[key],border=True)
    moderation_tab,backup_tab,health_tab=st.tabs(["Moderation","Backup & restore","Health & cleanup"])
    with moderation_tab:
        cases=suite.admin.cases(user["user_id"],"open",100)
        if not cases:
            empty_state("Moderation queue is clear", "No permission-visible cases currently require an evidence-based decision.", icon="✓", action_hint="New reports will appear here automatically.")
        else:
            st.dataframe(cases,hide_index=True)
            case_id=st.selectbox("Case",[c["case_id"] for c in cases]); action=st.selectbox("Action",["no_action","warning","content_hidden","content_removed","account_restricted","account_suspended","account_disabled"]); resolution=st.text_area("Evidence-based resolution")
            if st.button("Resolve case",type="primary",icon=":material/gavel:"): run(lambda:suite.admin.decide_case(user["user_id"],case_id,action=action,resolution=resolution),"Case resolved")
    with backup_tab:
        st.write("Backups are SQLite-consistent, ZIP-structured, encrypted with Fernet and verified through a non-production restore drill.")
        backup_type=st.segmented_control("Backup scope",["database","full"],default="database")
        if st.button("Create encrypted backup",type="primary",icon=":material/backup:"):
            result=run(lambda:suite.operations.create_backup(user["user_id"],backup_type or "database"),"Backup created")
            if result: st.session_state["connect_backup_id"]=result["backup_id"]; st.success(f"Encrypted backup {result['backup_id']} created ({result['size_bytes']:,} bytes).",icon=":material/lock:")
        backup_id=st.text_input("Backup ID",value=st.session_state.get("connect_backup_id",""))
        if st.button("Run isolated restore test",disabled=not backup_id,icon=":material/restore:"):
            restored=run(lambda:suite.operations.validate_restore(user["user_id"],backup_id),"Restore drill passed")
            if restored: st.json({"integrity_check":restored["integrity_check"],"migration_count":restored["migration_count"],"production_database_untouched":restored["production_database_untouched"]})
    with health_tab:
        capacity=st.slider("Capacity estimate",0,100,40)
        if st.button("Record health check",icon=":material/monitor_heart:"):
            health=run(lambda:suite.operations.health(capacity_percent=float(capacity)),"Health recorded")
            if health: st.json(health)
        cleanup_type=st.selectbox("Cleanup preview",["expired_stories","expired_signals","deleted_media"])
        if st.button("Dry-run cleanup",icon=":material/preview:"):
            result=run(lambda:suite.operations.cleanup(user["user_id"],cleanup_type,True),"Cleanup preview ready")
            if result: st.metric("Targets found",result["target_count"],border=True)


def render_accessibility_notifications(root:Path)->None:
    services,user,suite=_suite(root); prefs=suite.accessibility.preferences(user["user_id"]); lang=prefs["language"] if prefs["language"] in TEXT else "English"; header(TEXT[lang]["access"],"Persistent language, accessibility, data-saving and notification delivery controls.")
    access_tab,notifications_tab,drafts_tab=st.tabs(["Accessibility","Notifications","Drafts & scheduling"])
    with access_tab:
        language=st.selectbox(TEXT[lang]["language"],["English","Hindi","Hinglish"],index=["English","Hindi","Hinglish"].index(lang)); high=st.toggle("High contrast preference",value=bool(prefs["high_contrast"])); motion=st.toggle("Reduced motion",value=bool(prefs["reduced_motion"])); saving=st.toggle("Data-saving mode",value=bool(prefs["data_saving"])); captions=st.toggle("Captions by default",value=bool(prefs["captions_enabled"])); st.toggle("Audio autoplay",value=False,disabled=True,help="Audio autoplay is intentionally disabled.")
        if st.button(TEXT[language]["save"],type="primary",icon=":material/accessibility_new:"):
            if run(lambda:suite.accessibility.update(user["user_id"],language=language,high_contrast=high,reduced_motion=motion,data_saving=saving,captions_enabled=captions),"Preferences saved"): st.rerun()
        with st.container(border=True): st.badge("WCAG-aware",color="green"); st.write("Keyboard-first native controls, visible labels, alt-text/transcript requirements, captions enabled and audio autoplay disabled.")
    with notifications_tab:
        pref=suite.delivery.preferences(user["user_id"]); channels=json.loads(pref["channels_json"]); categories=json.loads(pref["categories_json"])
        selected=st.pills("Delivery channels",["in_app","email","push"],selection_mode="multi",default=[k for k,v in channels.items() if v]); digest=st.segmented_control("Digest",["none","daily","weekly"],default=pref["digest_frequency"]); private=st.toggle("Show private content previews",value=bool(pref["private_preview_enabled"]),help="Off uses a generic privacy-safe preview.")
        enabled_categories=st.multiselect("Categories",sorted(suite.delivery.CATEGORIES),default=[k for k,v in categories.items() if v] or sorted(suite.delivery.CATEGORIES))
        if st.button("Save notification preferences",type="primary",icon=":material/notifications_active:"): run(lambda:suite.delivery.update_preferences(user["user_id"],categories={x:True for x in enabled_categories},channels={x:x in (selected or []) for x in suite.delivery.CHANNELS},digest_frequency=digest or "none",private_preview_enabled=private),"Notification preferences saved")
    with drafts_tab:
        body=st.text_area("Draft text",height=180); title=st.text_input("Draft title"); visibility=st.selectbox("Future visibility",["public","followers","connections","only_me"]); schedule_at=st.text_input("Schedule UTC timestamp",placeholder="2030-01-01T09:00:00+00:00")
        with st.container(horizontal=True):
            if st.button("Autosave draft",icon=":material/save:"):
                result=run(lambda:suite.drafts.save(user["user_id"],body=body,title=title,settings={"visibility":visibility}),"Draft saved")
                if result: st.session_state["connect_draft_id"]=result["draft_id"]
            if st.button("Schedule",disabled=not schedule_at,icon=":material/schedule:"):
                draft_id=st.session_state.get("connect_draft_id")
                if not draft_id: st.warning("Autosave the draft first.",icon=":material/info:")
                else: run(lambda:suite.drafts.schedule(user["user_id"],draft_id,schedule_at),"Post scheduled")

