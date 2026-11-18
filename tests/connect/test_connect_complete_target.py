from __future__ import annotations

import hashlib, tempfile, unittest
from pathlib import Path
from typing import Any
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from biointel.database.core import utc_now
from biointel.connect.complete_api import register_complete_routes
from biointel.connect.database import ConnectDatabase, MIGRATION_ID
from biointel.connect.services import ConnectError, PermissionDenied, build_connect_services

class ConnectCompleteTargetTests(unittest.TestCase):
    def setUp(self)->None:
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.services=build_connect_services(database_path=self.root/"connect.sqlite3",storage_root=self.root/"media"); self.c=self.services.complete
        self.admin=self.services.ensure_identity("admin","Admin","administrator"); self.alpha=self.services.ensure_identity("alpha","Alpha"); self.beta=self.services.ensure_identity("beta","Beta")
    def tearDown(self)->None: self.temp.cleanup()
    def connect(self)->None:
        request=self.services.network.request_connection(self.alpha["user_id"],self.beta["user_id"]); self.services.network.respond_connection(self.beta["user_id"],request["request_id"],"accepted")
    def add_video(self)->str:
        path=self.root/"video.mp4"; path.write_bytes(b"safe-video-placeholder"); media_id="media_test_video"; now=utc_now()
        with self.services.database.connection() as db: db.execute("""INSERT INTO connect_media_objects(media_id,owner_id,original_name,storage_path,mime_type,size_bytes,sha256,media_kind,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?, 'available','private',?,?)""",(media_id,self.alpha["user_id"],"video.mp4",str(path),"video/mp4",path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest(),"video",now,now))
        return media_id
    def test_forward_migration_and_rollback(self):
        database=ConnectDatabase(self.root/"migration.sqlite3"); self.assertEqual(database.migrate(),MIGRATION_ID); self.assertTrue(database.migration_status()["current"])
        with database.connection(read_only=True) as db: tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'connect_%'")}
        self.assertEqual(len(tables),94); self.assertTrue({"connect_messages","connect_communities","connect_stories","connect_backup_records"}<=tables); database.rollback()
        with database.connection(read_only=True) as db: remaining={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'connect_%'")}
        self.assertEqual(remaining,{"connect_schema_migrations"})
    def test_messaging_delivery_offline_dedupe_and_block(self):
        self.connect(); conv=self.c.messaging.create_conversation(self.alpha["user_id"],[self.beta["user_id"]]); first=self.c.messaging.send(self.alpha["user_id"],conv["conversation_id"],"Result",client_event_id="stable"); duplicate=self.c.messaging.send(self.alpha["user_id"],conv["conversation_id"],"Result",client_event_id="stable")
        self.assertEqual(first["message_id"],duplicate["message_id"]); self.assertEqual(self.c.messaging.update_receipt(self.beta["user_id"],first["message_id"],"read")["state"],"read"); self.assertTrue(self.c.messaging.events(self.beta["user_id"])); self.c.messaging.events(self.beta["user_id"],acknowledge=True)
        self.services.network.block(self.beta["user_id"],self.alpha["user_id"])
        with self.assertRaises(PermissionDenied): self.c.messaging.send(self.alpha["user_id"],conv["conversation_id"],"blocked",client_event_id="blocked")
    def test_community_collaboration_and_workflow_permissions(self):
        community=self.c.communities.create(self.alpha["user_id"],name="Private Proteomics",visibility="private",join_policy="approval")
        with self.assertRaises(PermissionDenied): self.c.communities.get(self.beta["user_id"],community["community_id"])
        self.assertEqual(self.c.communities.join(self.beta["user_id"],community["community_id"])["state"],"pending"); self.c.communities.set_member(self.alpha["user_id"],community["community_id"],self.beta["user_id"],state="active"); post=self.c.communities.create_post(self.beta["user_id"],community["community_id"],body="Member-only result"); self.assertEqual(self.services.content.get_post(self.alpha["user_id"],post["post_id"])["visibility"],"community_members")
        collaboration=self.c.collaboration.create_collaboration(self.alpha["user_id"],title="Cohort replication",objective="Independent validation"); application=self.c.collaboration.apply(self.beta["user_id"],collaboration["collaboration_id"],introduction="Available"); self.assertEqual(self.c.collaboration.decide_application(self.alpha["user_id"],application["application_id"],"accepted")["state"],"accepted")
        workflow=self.c.collaboration.create_workflow(self.alpha["user_id"],name="Variant QC",scientific_purpose="Validate variants",steps=["validate"]); fork=self.c.collaboration.fork_workflow(self.beta["user_id"],workflow["workflow_id"]); self.assertEqual(fork["validation_status"],"fork_unvalidated"); self.assertIn('"execution_performed": false',fork["audit_json"])
    def test_story_short_video_live_and_call_consent(self):
        story=self.c.stories.create(self.alpha["user_id"],story_type="text",text_body="Time-bound",visibility="public",hours=1); self.assertEqual(self.c.stories.view(self.beta["user_id"],story["story_id"])["viewer_count"],1)
        with self.services.database.connection() as db: db.execute("UPDATE connect_stories SET expires_at_utc='2000-01-01T00:00:00+00:00' WHERE story_id=?",(story["story_id"],))
        with self.assertRaises(PermissionDenied): self.c.stories.get(self.beta["user_id"],story["story_id"])
        media=self.add_video()
        with self.assertRaises(ConnectError): self.c.short_videos.create(self.alpha["user_id"],media_id=media,transcript="",alt_text="")
        video=self.c.short_videos.create(self.alpha["user_id"],media_id=media,caption="QC",transcript="Transcript",alt_text="QC chart"); self.assertEqual(self.c.short_videos.feed(self.beta["user_id"])[0]["short_video_id"],video["short_video_id"])
        live=self.c.live_streams.create(self.alpha["user_id"],stream_type="webinar",title="Live",recording_enabled=True); self.c.live_streams.start(self.alpha["user_id"],live["live_stream_id"])
        with self.assertRaises(PermissionDenied): self.c.live_streams.join(self.beta["user_id"],live["live_stream_id"])
        self.c.live_streams.join(self.beta["user_id"],live["live_stream_id"],recording_consent=True)
        call=self.c.calls.create(self.alpha["user_id"],[self.beta["user_id"]],recording_requested=True)
        self.assertEqual(call["recording_state"],"unavailable")
        with self.assertRaises(ConnectError): self.c.calls.respond(self.beta["user_id"],call["call_id"],"accepted",recording_consent=True)
        self.c.calls.respond(self.beta["user_id"],call["call_id"],"accepted"); self.assertEqual(self.c.calls.start(self.alpha["user_id"],call["call_id"])["recording_state"],"unavailable")
    def test_call_signaling_membership_isolation_and_end(self):
        outsider=self.services.ensure_identity("outsider","Outsider")
        call=self.c.calls.create(self.alpha["user_id"],[self.beta["user_id"]])
        with self.assertRaises(PermissionDenied): self.c.calls.state(outsider["user_id"],call["call_id"])
        self.c.calls.respond(self.beta["user_id"],call["call_id"],"accepted",microphone=True,camera=True)
        self.c.calls.start(self.alpha["user_id"],call["call_id"])
        offer=self.c.calls.signal(self.alpha["user_id"],call["call_id"],"offer",{"type":"offer","sdp":"v=0 test"},self.beta["user_id"])
        self.assertNotIn("signal_json",offer)
        self.assertEqual(self.c.calls.signals(self.beta["user_id"],call["call_id"])[0]["signal"]["type"],"offer")
        with self.assertRaises(PermissionDenied): self.c.calls.signal(outsider["user_id"],call["call_id"],"answer",{})
        with self.assertRaises(PermissionDenied): self.c.calls.end(self.beta["user_id"],call["call_id"])
        self.assertEqual(self.c.calls.end(self.alpha["user_id"],call["call_id"])["state"],"ended")
    def test_verification_onboarding_accessibility_and_delivery(self):
        token=self.c.verification.issue_email_token(self.alpha["user_id"],"alpha@example.org"); self.assertTrue(self.c.verification.verify_email(self.alpha["user_id"],token["token"])["verified"])
        request=self.c.verification.submit(self.alpha["user_id"],"researcher",reason="Evidence",evidence=[{"type":"orcid","value":"0000","summary":"ORCID"}]); self.assertEqual(self.c.verification.decide(self.admin["user_id"],request["verification_request_id"],"approved")["decision"],"approved")
        self.assertGreater(self.c.onboarding.update(self.alpha["user_id"],1)["completion_percent"],0); prefs=self.c.accessibility.update(self.alpha["user_id"],language="Hinglish",reduced_motion=True,data_saving=True); self.assertEqual(prefs["language"],"Hinglish"); self.assertEqual(prefs["autoplay_audio"],0)
        queued=self.c.delivery.queue(self.alpha["user_id"],"system","system","migration","Ready",dedupe_key="ready"); duplicate=self.c.delivery.queue(self.alpha["user_id"],"system","system","migration","Ready",dedupe_key="ready"); self.assertEqual({x["delivery_id"] for x in queued["deliveries"]},{x["delivery_id"] for x in duplicate["deliveries"]}); self.assertGreaterEqual(self.c.delivery.deliver_due()["delivered"],1); self.assertEqual(self.c.delivery.digest(self.alpha["user_id"])["frequency"],"daily")
    def test_drafts_lifecycle_and_shiro_safety(self):
        draft=self.c.drafts.save(self.alpha["user_id"],body="Scheduled",settings={"visibility":"public"}); self.c.drafts.save(self.alpha["user_id"],draft_id=draft["draft_id"],body="Revised",settings={"visibility":"public"}); self.c.drafts.schedule(self.alpha["user_id"],draft["draft_id"],"2000-01-01T00:00:00+00:00"); self.assertEqual(self.c.drafts.publish_due()["published"],1)
        with self.services.database.connection(read_only=True) as db: post_id=db.execute("SELECT published_post_id FROM connect_scheduled_posts").fetchone()[0]
        self.assertEqual(self.c.lifecycle.edit_post(self.alpha["user_id"],post_id,body="Corrected")["version"],2); self.assertEqual(len(self.c.lifecycle.versions(self.alpha["user_id"],post_id)),1); self.assertEqual(self.c.lifecycle.set_state(self.alpha["user_id"],post_id,"archived")["state"],"archived")
        shiro=self.c.shiro.assist(self.alpha["user_id"],"draft_post","Proposal"); self.assertTrue(shiro["requires_user_approval"]); self.assertFalse(shiro["sent"] or shiro["published"] or shiro["privacy_changed"])
        with self.assertRaises(PermissionDenied): self.c.shiro.assist(self.alpha["user_id"],"publish_post","Do it")
    def test_admin_backup_restore_health_and_cleanup(self):
        with self.assertRaises(PermissionDenied): self.c.admin.dashboard(self.alpha["user_id"])
        health=self.c.operations.health(); self.assertEqual(health["source"],"server_derived"); self.assertFalse(health["persisted_health_event"]); backup=self.c.operations.create_backup(self.admin["user_id"],"database"); restored=self.c.operations.validate_restore(self.admin["user_id"],backup["backup_id"]); self.assertEqual(restored["integrity_check"],"ok"); self.assertTrue(restored["production_database_untouched"]); self.assertEqual(self.c.operations.cleanup(self.admin["user_id"],"expired_stories",True)["dry_run"],1)
    def test_complete_api_registry_and_http(self):
        router=APIRouter(prefix="/api/v1/connect")
        def identity(request:Request): return self.services.ensure_identity("api-user","API user","local_operator")
        register_complete_routes(router,self.services,identity,lambda operation:operation()); app=FastAPI(); app.include_router(router); client=TestClient(app)
        self.assertEqual(client.get("/api/v1/connect/health").status_code,200); self.assertEqual(client.post("/api/v1/connect/stories",json={"story_type":"text","text_body":"API story","visibility":"public"}).status_code,201)
        paths={route.path for route in router.routes}; required={"/api/v1/connect/websocket","/api/v1/connect/communities","/api/v1/connect/collaborations","/api/v1/connect/projects","/api/v1/connect/stories","/api/v1/connect/short-videos","/api/v1/connect/live-streams","/api/v1/connect/calls","/api/v1/connect/admin","/api/v1/connect/health"}; self.assertTrue(required<=paths)

if __name__=="__main__": unittest.main()



