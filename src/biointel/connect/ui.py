from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import streamlit as st

from biointel.ui.access_control import current_ui_identity
from biointel.ui.theme import apply_theme
from biointel.ui.frontend_v10 import (
    apply_frontend_v10, capability_grid, compact_page_header, empty_state,
    person_header, section_header,
)
from .media import UploadRejected, UploadRequiresConfirmation
from .services import ConnectError, ConnectServices, build_connect_services

POST_TYPES = ["text","scientific_update","image","image_carousel","video","pdf","document","publication_announcement",
              "dataset_announcement","workflow_announcement","research_project_update","biointel_report","protocol",
              "research_question","poll","collaboration_request","event_announcement","job_opportunity","grant_announcement"]
VISIBILITIES = ["public","followers","connections","institution_members","only_me","draft"]
REACTIONS = ["like","appreciate","insightful","useful","support","collaborate","question","needs_evidence","reproducible"]
REPORTS = ["spam","harassment","impersonation","fake_credentials","plagiarism","copyright_infringement",
           "scientific_misinformation","fabricated_research","privacy_violation","patient_data_exposure",
           "dangerous_laboratory_content","undisclosed_promotion"]

@st.cache_resource(show_spinner=False)
def _services(root_text: str) -> ConnectServices:
    return build_connect_services(Path(root_text))

def context(root: Path) -> tuple[ConnectServices,dict[str,Any]]:
    apply_theme()
    apply_frontend_v10("connect")
    identity=current_ui_identity()
    services=_services(str(root.resolve()))
    user=services.ensure_identity(identity.username,identity.display_name,identity.role)
    return services,user

def header(title: str, description: str) -> None:
    compact_page_header(
        "connect", title, description,
        status=("Scientific network", "Permission-aware", "Local-first"),
    )
    capability_grid("connect")
    section_header("Connect navigation", "Move between collaboration, publishing and communication workspaces.", icon="◎", badge="Applications")
    links = (
        ("pages/300_BioIntel_Connect_Home.py", "Home", ":material/home:"),
        ("pages/302_Connect_Create_Post.py", "Create", ":material/add_circle:"),
        ("pages/303_Connect_My_Network.py", "Network", ":material/group:"),
        ("pages/315_Connect_Profile.py", "Profile", ":material/person:"),
        ("pages/313_Connect_Notifications.py", "Notifications", ":material/notifications:"),
        ("pages/318_Connect_Messages.py", "Messages", ":material/chat:"),
        ("pages/319_Connect_Communities.py", "Communities", ":material/groups:"),
        ("pages/320_Connect_Discover_and_Collaborate.py", "Discover", ":material/travel_explore:"),
        ("pages/321_Connect_Stories_and_Short_Videos.py", "Stories", ":material/auto_stories:"),
        ("pages/322_Connect_Live_and_Calls.py", "Live", ":material/video_call:"),
    )
    for offset in range(0, len(links), 5):
        columns = st.columns(5, gap="small")
        for column, (path, label, icon) in zip(columns, links[offset:offset + 5]):
            with column:
                st.page_link(path, label=label, icon=icon, width="stretch")

def run(action: Callable[[],Any], success: str) -> Any | None:
    try:
        result=action()
        return result
    except UploadRequiresConfirmation as exc:
        st.warning("Sensitive-content confirmation required: "+", ".join(exc.result.get("warnings",[])),icon=":material/privacy_tip:")
    except (ConnectError,UploadRejected,KeyError,PermissionError) as exc:
        st.error(str(exc),icon=":material/error:")
    return None

def _media_path(services: ConnectServices, media_id: str) -> Path | None:
    with services.database.connection(read_only=True) as db:
        row=db.execute("SELECT storage_path FROM connect_media_objects WHERE media_id=? AND state='available'",(media_id,)).fetchone()
    return Path(row["storage_path"]) if row and Path(row["storage_path"]).is_file() else None

def post_card(services: ConnectServices,user: dict[str,Any],post: dict[str,Any],prefix: str) -> None:
    with st.container(border=True):
        author_name = str(post.get("author_name") or post.get("author_username") or "BioIntel researcher")
        initials = "".join(part[:1] for part in author_name.split()[:2]) or "BI"
        person_header(
            author_name,
            "@" + str(post.get("author_username") or "researcher"),
            initials=initials,
            metadata=filter(None, [post.get("author_headline", ""), post.get("author_institution", ""), post.get("visibility", "")]),
        )
        st.caption(str(post.get("created_at_utc") or "Time unavailable"))
        if post.get("title"): st.subheader(post["title"])
        st.markdown(post["body"])
        for attachment in post.get("attachments",[]):
            path=_media_path(services,attachment["media_id"])
            if not path: continue
            if attachment["media_kind"] == "image": st.image(str(path),caption=attachment["original_name"])
            elif attachment["media_kind"] == "video": st.video(str(path))
            else:
                st.caption(f":material/description: {attachment['original_name']} · {attachment['size_bytes']:,} bytes")
                if post["download_permission"] != "none":
                    st.download_button("Download",data=path.read_bytes(),file_name=attachment["original_name"],mime=attachment["mime_type"],key=f"{prefix}_dl_{attachment['media_id']}")
        st.caption(f"{post['reaction_count']} reactions · {post['comment_count']} comments")
        with st.container(horizontal=True):
            reaction=st.selectbox("Reaction",REACTIONS,key=f"{prefix}_reaction",label_visibility="collapsed",width=180)
            if st.button("React",key=f"{prefix}_react",icon=":material/thumb_up:"):
                if run(lambda: services.content.react(user["user_id"],post["post_id"],reaction),"Reaction saved"): st.rerun()
            if st.button("Unsave" if post.get("viewer_bookmarked") else "Save",key=f"{prefix}_save",icon=":material/bookmark:"):
                if run(lambda: services.content.bookmark(user["user_id"],post["post_id"],not post.get("viewer_bookmarked")),"Saved state updated"): st.rerun()
            if st.button("Open discussion",key=f"{prefix}_open",icon=":material/forum:"):
                st.query_params["post_id"]=post["post_id"]; st.switch_page("pages/317_Connect_Post_Detail.py")
        with st.expander("Report",icon=":material/flag:"):
            reason=st.selectbox("Reason",REPORTS,key=f"{prefix}_report_reason")
            detail=st.text_area("Details",key=f"{prefix}_report_detail")
            if st.button("Submit report",key=f"{prefix}_report"):
                run(lambda: services.content.report(user["user_id"],"post",post["post_id"],reason,detail),"Report submitted for review")

def _upload_files(services: ConnectServices,user_id: str,files: list[Any],visibility: str,confirm: bool) -> list[str]:
    media_ids=[]
    for index,file in enumerate(files):
        progress=st.progress(0,text=f"Scanning and storing {file.name}")
        media=services.media.upload_bytes(user_id,filename=file.name,mime_type=file.type,data=file.getvalue(),visibility=visibility,
            confirm_sensitive=confirm,progress=lambda done,total,p=progress: p.progress(done/total,text=f"Uploading {file.name}: {done:,}/{total:,} bytes"))
        progress.progress(1.0,text=f"{file.name} uploaded securely")
        media_ids.append(media["media_id"])
    return media_ids

def render_home(root: Path) -> None:
    services,user=context(root); header("BioIntel Connect","Connect. Collaborate. Discover. Permission-aware scientific updates from your network.")
    profile=services.profiles.get(user["user_id"],user["user_id"])
    left,center,right=st.columns([1,2.2,1],gap="medium")
    with left:
        with st.container(border=True):
            st.subheader(profile["full_name"]); st.caption("@"+profile["username"])
            st.write(profile["headline"] or "Complete your scientific profile")
            st.page_link("pages/315_Connect_Profile.py",label="Edit profile",icon=":material/edit:")
    with center:
        with st.container(border=True):
            st.write("Share a research update, question, dataset, workflow or collaboration idea.")
            st.page_link("pages/302_Connect_Create_Post.py",label="Create post",icon=":material/add_circle:")
        mode=st.segmented_control("Feed",["latest","following","connections","recommended"],default="latest") or "latest"
        feed=run(lambda: services.content.feed(user["user_id"],mode=mode,limit=25),"")
        if feed:
            if not feed["items"]:
                empty_state("Your scientific feed is ready", "No permission-visible posts are available yet.", icon="↗", action_hint="Follow researchers or publish the first evidence-led update.")
            for index,post in enumerate(feed["items"]): post_card(services,user,post,f"feed_{index}_{post['post_id']}")
    with right:
        network=services.network.overview(user["user_id"])
        with st.container(border=True):
            st.metric("Connections",len(network["connections"]),border=False)
            st.metric("Following",len(network["following"]),border=False)
            st.metric("Requests",len(network["requests"]),border=False)
        with st.container(border=True):
            st.subheader("Scientific relevance")
            st.caption("Latest and network modes are chronological. Recommended mode explains every suggestion and never exposes restricted content.")

def render_create_post(root: Path) -> None:
    services,user=context(root); header("Create post","Publish scientific work with backend-enforced visibility and secure, resumable media storage.")
    default=services.profiles.privacy(user["user_id"])["default_post_visibility"]
    with st.form("connect_post_composer"):
        post_type=st.selectbox("Post type",POST_TYPES,index=0)
        title=st.text_input("Title",max_chars=300)
        body=st.text_area("Main text",height=220,placeholder="Use Markdown, equations, citations, code, #hashtags and @mentions.",max_chars=50_000)
        files=st.file_uploader("Images, video, PDF or research documents",type=[ext.lstrip(".") for ext in [".jpg",".jpeg",".png",".webp",".gif",".mp4",".webm",".pdf",".docx",".pptx",".xlsx",".csv",".tsv",".zip"]],accept_multiple_files=True)
        visibility=st.selectbox("Visibility",VISIBILITIES,index=VISIBILITIES.index(default) if default in VISIBILITIES else 0)
        comment_permission=st.selectbox("Who may comment",["everyone","followers","connections","none"])
        download_permission=st.selectbox("Attachment downloads",["ask","allowed","none"])
        collaboration=st.toggle("Open to collaboration")
        confirm=st.checkbox("I reviewed these files for participant, patient, genomic, consent, licence and institutional restrictions.")
        submitted=st.form_submit_button("Publish" if visibility!="draft" else "Save draft",type="primary",icon=":material/publish:")
    if submitted:
        def create():
            media_ids=_upload_files(services,user["user_id"],files,visibility,confirm)
            return services.content.create_post(user["user_id"],body=body,title=title,post_type=post_type,visibility=visibility,
                comment_permission=comment_permission,download_permission=download_permission,media_ids=media_ids,collaboration_enabled=collaboration)
        post=run(create,"Post published" if visibility!="draft" else "Draft saved")
        if post: st.query_params["post_id"]=post["post_id"]; st.switch_page("pages/317_Connect_Post_Detail.py")

def render_network(root: Path) -> None:
    services,user=context(root); header("My network","Find researchers, follow their work, and manage two-way professional connections.")
    query=st.text_input("Search researchers",placeholder="Name, institution, field or skill",icon=":material/search:")
    results=run(lambda: services.profiles.search(user["user_id"],query,50),"") or []
    for item in results:
        if item["user_id"] == user["user_id"]: continue
        with st.container(border=True):
            st.subheader(item["full_name"]); st.caption(f"@{item['username']} · {item['headline']} · {item['institution']}")
            st.write(item["about"][:400])
            with st.container(horizontal=True):
                if st.button("Follow",key=f"follow_{item['user_id']}",icon=":material/person_add:"):
                    if run(lambda target=item["user_id"]: services.network.follow(user["user_id"],target),"Now following"): st.rerun()
                if st.button("Connect",key=f"connect_{item['user_id']}",icon=":material/handshake:"):
                    run(lambda target=item["user_id"]: services.network.request_connection(user["user_id"],target,reason="Shared scientific network interest"),"Connection request sent")
                if st.button("Mute",key=f"mute_{item['user_id']}",icon=":material/volume_off:"):
                    run(lambda target=item["user_id"]: services.network.mute(user["user_id"],target),"Researcher muted")
                if st.button("Block",key=f"block_{item['user_id']}",icon=":material/block:"):
                    if run(lambda target=item["user_id"]: services.network.block(user["user_id"],target),"Researcher blocked"): st.rerun()
    st.subheader("Network overview")
    overview=services.network.overview(user["user_id"])
    tabs=st.tabs([f"Connections ({len(overview['connections'])})",f"Requests ({len(overview['requests'])})",f"Following ({len(overview['following'])})"])
    with tabs[0]:
        for item in overview["connections"]: st.write(f"**{item['display_name']}** · @{item['username']} · {item['headline']}")
    with tabs[1]:
        for item in overview["requests"]:
            with st.container(border=True):
                st.write(f"**{item['display_name']}** · {item['reason']}")
                with st.container(horizontal=True):
                    if st.button("Accept",key=f"accept_{item['request_id']}",type="primary"):
                        if run(lambda rid=item["request_id"]: services.network.respond_connection(user["user_id"],rid,"accepted"),"Connection accepted"): st.rerun()
                    if st.button("Decline",key=f"decline_{item['request_id']}"):
                        if run(lambda rid=item["request_id"]: services.network.respond_connection(user["user_id"],rid,"declined"),"Request declined"): st.rerun()
    with tabs[2]:
        for item in overview["following"]: st.write(f"**{item['display_name']}** · @{item['username']}")

def render_profile(root: Path) -> None:
    services,user=context(root); header("Professional profile","Your scientific identity, background, portfolio and collaboration interests.")
    profile=services.profiles.get(user["user_id"],user["user_id"])
    research=profile.get("research",{})
    with st.form("connect_profile"):
        a,b=st.columns(2)
        with a:
            full_name=st.text_input("Full name",value=profile["full_name"],max_chars=120)
            username=st.text_input("Username",value=profile["username"],max_chars=64)
            headline=st.text_input("Professional headline",value=profile["headline"],max_chars=200)
            institution=st.text_input("Institution",value=profile["institution"],max_chars=240)
            department=st.text_input("Department",value=profile["department"],max_chars=240)
            laboratory=st.text_input("Laboratory",value=profile["laboratory"],max_chars=240)
        with b:
            city=st.text_input("City",value=profile["city"]); country=st.text_input("Country",value=profile["country"])
            timezone=st.text_input("Timezone",value=profile["timezone"])
            website=st.text_input("Website",value=profile["website"])
            language=st.selectbox("Preferred language",["English","Hindi","Hinglish"],index=["English","Hindi","Hinglish"].index(profile["preferred_language"]) if profile["preferred_language"] in ["English","Hindi","Hinglish"] else 0)
            contact=st.selectbox("Contact preference",["everyone","followers","connections","no_one"],index=["everyone","followers","connections","no_one"].index(profile["contact_preference"]) if profile["contact_preference"] in ["everyone","followers","connections","no_one"] else 2)
        about=st.text_area("About",value=profile["about"],height=160,max_chars=5000)
        fields=st.text_input("Research fields (comma-separated)",value=", ".join(research.get("fields",[])))
        interests=st.text_input("Research interests (comma-separated)",value=", ".join(research.get("interests",[])))
        skills=st.text_input("Computational and laboratory skills (comma-separated)",value=", ".join(research.get("skills",[])))
        diseases=st.text_input("Diseases studied (comma-separated)",value=", ".join(research.get("diseases",[])))
        organisms=st.text_input("Organisms studied (comma-separated)",value=", ".join(research.get("organisms",[])))
        profile_image=st.file_uploader("Profile photograph",type=["jpg","jpeg","png","webp"],accept_multiple_files=False)
        submitted=st.form_submit_button("Save profile",type="primary",icon=":material/save:")
    if submitted:
        def save():
            image_id=profile.get("profile_image_id")
            if profile_image:
                image_id=services.media.upload_bytes(user["user_id"],filename=profile_image.name,mime_type=profile_image.type,
                    data=profile_image.getvalue(),visibility="public",confirm_sensitive=True)["media_id"]
            split=lambda value:[part.strip() for part in value.split(",") if part.strip()]
            return services.profiles.update(user["user_id"],{"full_name":full_name,"username":username.lower(),"headline":headline,
                "institution":institution,"department":department,"laboratory":laboratory,"city":city,"country":country,
                "timezone":timezone,"website":website,"preferred_language":language,"contact_preference":contact,"about":about,
                "profile_image_id":image_id,"research":{"fields":split(fields),"interests":split(interests),"skills":split(skills),
                "diseases":split(diseases),"organisms":split(organisms)}})
        if run(save,"Professional profile saved"): st.rerun()

def render_post_detail(root: Path) -> None:
    services,user=context(root); header("Post discussion","Read a permission-checked post, join threaded discussion and preserve scientific attribution.")
    initial=str(st.query_params.get("post_id","")); post_id=st.text_input("Post ID",value=initial,placeholder="pst_…")
    if not post_id: st.info("Open a post from the feed or enter its ID."); return
    post=run(lambda: services.content.get_post(user["user_id"],post_id),"")
    if not post: return
    post_card(services,user,post,f"detail_{post_id}")
    st.subheader("Discussion")
    with st.form("new_comment",clear_on_submit=True):
        comment=st.text_area("Add a comment",max_chars=10_000)
        if st.form_submit_button("Comment",type="primary",icon=":material/send:"):
            if run(lambda: services.content.add_comment(user["user_id"],post_id,comment),"Comment added"): st.rerun()
    comments=services.content.comments(user["user_id"],post_id)
    for item in comments:
        indent="↳ " if item["parent_comment_id"] else ""
        with st.container(border=True):
            st.markdown(f"{indent}**{item['author_name']}** · @{item['author_username']}")
            st.markdown(item["body"]); st.caption(item["created_at_utc"])
            with st.expander("Reply",icon=":material/reply:"):
                reply=st.text_area("Reply text",key=f"reply_text_{item['comment_id']}",max_chars=10_000)
                if st.button("Send reply",key=f"reply_{item['comment_id']}"):
                    if run(lambda cid=item["comment_id"],text=reply: services.content.add_comment(user["user_id"],post_id,text,cid),"Reply added"): st.rerun()

def render_notifications(root: Path) -> None:
    services,user=context(root); header("Notifications","Real-time-ready, persistent activity notifications with explicit read state.")
    items=services.content.notifications(user["user_id"],250)
    with st.container(horizontal=True):
        st.metric("Unread",sum(not item["read_at_utc"] for item in items),border=False)
        if st.button("Mark all as read",icon=":material/done_all:"):
            services.content.mark_notifications_read(user["user_id"]); st.rerun()
    for item in items:
        with st.container(border=True):
            st.markdown(("**New** · " if not item["read_at_utc"] else "")+item["message"])
            st.caption(f"{item['notification_type'].replace('_',' ')} · {item['created_at_utc']}")

def render_settings(root: Path) -> None:
    services,user=context(root); header("Network settings","Control discoverability, profile fields, connection permissions and content defaults.")
    privacy=services.profiles.privacy(user["user_id"])
    with st.form("connect_privacy"):
        profile_visibility=st.selectbox("Profile visibility",["public","authenticated","connections","only_me"],index=["public","authenticated","connections","only_me"].index(privacy["profile_visibility"]))
        default_post=st.selectbox("Default post visibility",VISIBILITIES,index=VISIBILITIES.index(privacy["default_post_visibility"]) if privacy["default_post_visibility"] in VISIBILITIES else 0)
        institution_visibility=st.selectbox("Institution visibility",["public","authenticated","connections","only_me"],index=["public","authenticated","connections","only_me"].index(privacy["institution_visibility"]) if privacy["institution_visibility"] in ["public","authenticated","connections","only_me"] else 0)
        location_visibility=st.selectbox("Location visibility",["public","connections","only_me"],index=["public","connections","only_me"].index(privacy["location_visibility"]))
        connection_permission=st.selectbox("Who can connect",["everyone","followers","no_one"],index=["everyone","followers","no_one"].index(privacy["connection_permission"]))
        mention_permission=st.selectbox("Who can mention you",["everyone","connections","no_one"],index=["everyone","connections","no_one"].index(privacy["mention_permission"]))
        search=st.toggle("Appear in researcher search",value=bool(privacy["search_discoverable"]))
        receipts=st.toggle("Read receipts",value=bool(privacy["read_receipts"]))
        if st.form_submit_button("Save privacy settings",type="primary",icon=":material/privacy_tip:"):
            if run(lambda: services.profiles.update_privacy(user["user_id"],{"profile_visibility":profile_visibility,
                "default_post_visibility":default_post,"institution_visibility":institution_visibility,
                "location_visibility":location_visibility,"connection_permission":connection_permission,
                "mention_permission":mention_permission,"search_discoverable":search,"read_receipts":receipts}),"Privacy settings saved"): st.rerun()
    st.subheader("Saved scientific content")
    for index,post in enumerate(services.content.saved(user["user_id"],50)):
        post["viewer_bookmarked"]=True; post_card(services,user,post,f"saved_{index}_{post['post_id']}")



