from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from biointel.connect.database import ConnectDatabase
from biointel.connect.media import UploadRejected, UploadRequiresConfirmation
from biointel.connect.services import PermissionDenied, build_connect_services


class ConnectPhase1Phase2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary=tempfile.TemporaryDirectory()
        self.root=Path(self.temporary.name)
        self.system=build_connect_services(self.root,database_path=self.root/"connect.sqlite3",storage_root=self.root/"media")
        self.alice=self.system.ensure_identity("alice.lab","Alice Genomics")
        self.bob=self.system.ensure_identity("bob.lab","Bob Proteomics")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def png(color=(21,124,190)) -> bytes:
        buffer=io.BytesIO(); Image.new("RGB",(4,4),color).save(buffer,format="PNG"); return buffer.getvalue()

    def connect_users(self) -> None:
        request=self.system.network.request_connection(self.alice["user_id"],self.bob["user_id"],reason="Shared omics")
        self.system.network.respond_connection(self.bob["user_id"],request["request_id"],"accepted")

    def test_migration_forward_and_rollback(self) -> None:
        database=ConnectDatabase(self.root/"rollback.sqlite3"); database.migrate()
        self.assertTrue(database.migration_status()["current"])
        with database.connection(read_only=True) as db:
            names={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"connect_users","connect_profiles","connect_posts","connect_media_objects","connect_moderation_cases"} <= names)
        database.rollback()
        with database.connection(read_only=True) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='connect_posts'").fetchone())

    def test_profiles_follow_connection_and_block(self) -> None:
        profile=self.system.profiles.update(self.alice["user_id"],{"headline":"Cancer genomics","institution":"Bio Lab","research":{"fields":["genomics"],"skills":["Python"]}})
        self.assertEqual(profile["headline"],"Cancer genomics")
        self.assertEqual(self.system.profiles.search(self.bob["user_id"],"genomics")[0]["user_id"],self.alice["user_id"])
        self.assertEqual(self.system.network.follow(self.alice["user_id"],self.bob["user_id"])["state"],"active")
        self.connect_users(); self.assertTrue(self.system.repository.connected(self.alice["user_id"],self.bob["user_id"]))
        self.system.network.block(self.bob["user_id"],self.alice["user_id"],"No further contact")
        self.assertTrue(self.system.repository.blocked(self.alice["user_id"],self.bob["user_id"]))
        self.assertFalse(self.system.repository.connected(self.alice["user_id"],self.bob["user_id"]))
        with self.assertRaises(PermissionDenied): self.system.network.follow(self.alice["user_id"],self.bob["user_id"])

    def test_post_permissions_discussion_reaction_bookmark_repost_report(self) -> None:
        post=self.system.content.create_post(self.alice["user_id"],body="Connection evidence",visibility="connections")
        with self.assertRaises(PermissionDenied): self.system.content.get_post(self.bob["user_id"],post["post_id"])
        self.connect_users(); self.assertEqual(self.system.content.get_post(self.bob["user_id"],post["post_id"])["body"],"Connection evidence")
        comment=self.system.content.add_comment(self.bob["user_id"],post["post_id"],"Insightful evidence")
        reply=self.system.content.add_comment(self.alice["user_id"],post["post_id"],"Thank you",comment["comment_id"])
        self.assertEqual(reply["parent_comment_id"],comment["comment_id"])
        self.assertEqual(self.system.content.react(self.bob["user_id"],post["post_id"],"reproducible")["reaction_type"],"reproducible")
        self.assertEqual(self.system.content.bookmark(self.bob["user_id"],post["post_id"])["state"],"active")
        self.assertEqual(self.system.content.saved(self.bob["user_id"])[0]["post_id"],post["post_id"])
        self.assertEqual(self.system.content.repost(self.bob["user_id"],post["post_id"],quote="Worth reproducing")["original_post_id"],post["post_id"])
        report=self.system.content.report(self.bob["user_id"],"post",post["post_id"],"scientific_misinformation","Needs citation")
        with self.system.database.connection(read_only=True) as db:
            self.assertEqual(db.execute("SELECT state FROM connect_moderation_cases WHERE case_id=?",(report["case_id"],)).fetchone()[0],"open")

    def test_chunked_resume_dedup_sensitive_warning_and_malware_block(self) -> None:
        data=self.png(); upload=self.system.media.initialize(self.alice["user_id"],filename="result.png",mime_type="image/png",size_bytes=len(data))
        middle=len(data)//2
        self.system.media.append_chunk(self.alice["user_id"],upload["upload_id"],offset=0,chunk=data[:middle])
        self.assertEqual(self.system.media.status(self.alice["user_id"],upload["upload_id"])["received_bytes"],middle)
        self.system.media.append_chunk(self.alice["user_id"],upload["upload_id"],offset=middle,chunk=data[middle:])
        media=self.system.media.complete(self.alice["user_id"],upload["upload_id"],visibility="public")
        self.assertTrue(Path(media["storage_path"]).is_file())
        duplicate=self.system.media.upload_bytes(self.alice["user_id"],filename="copy.png",mime_type="image/png",data=data,visibility="public")
        self.assertEqual(duplicate["media_id"],media["media_id"])
        sensitive=b"participant,email\nP-001,person@example.org\n"
        warning=self.system.media.initialize(self.alice["user_id"],filename="participants.csv",mime_type="text/csv",size_bytes=len(sensitive))
        self.system.media.append_chunk(self.alice["user_id"],warning["upload_id"],offset=0,chunk=sensitive)
        with self.assertRaises(UploadRequiresConfirmation): self.system.media.complete(self.alice["user_id"],warning["upload_id"],visibility="public")
        self.assertEqual(self.system.media.complete(self.alice["user_id"],warning["upload_id"],visibility="public",confirm_sensitive=True)["media_kind"],"document")
        with self.assertRaises(UploadRejected): self.system.media.upload_bytes(self.alice["user_id"],filename="malware.png",mime_type="image/png",data=b"MZnot-an-image")

    def test_carousel_feed_and_notifications(self) -> None:
        media=[]
        for index in range(2):
            media.append(self.system.media.upload_bytes(self.alice["user_id"],filename=f"image-{index}.png",mime_type="image/png",data=self.png((index*80,20,150)),visibility="public")["media_id"])
        post=self.system.content.create_post(self.alice["user_id"],body="Two scientific images",post_type="image_carousel",media_ids=media)
        self.assertEqual(len(post["attachments"]),2)
        self.assertEqual(self.system.content.feed(self.bob["user_id"],limit=1)["items"][0]["post_id"],post["post_id"])
        self.system.content.add_comment(self.bob["user_id"],post["post_id"],"Great images")
        self.assertTrue(any(item["notification_type"]=="comment" for item in self.system.content.notifications(self.alice["user_id"])))
        self.assertGreaterEqual(self.system.content.mark_notifications_read(self.alice["user_id"]),1)

    def test_versioned_api(self) -> None:
        import biointel.connect.api as connect_api
        with patch.object(connect_api,"SERVICES",self.system):
            app=FastAPI(); app.include_router(connect_api.router); client=TestClient(app)
            response=client.put("/api/v1/connect/profiles/me",json={"full_name":"Local Researcher","headline":"Systems biology"})
            self.assertEqual(response.status_code,200); self.assertEqual(response.json()["headline"],"Systems biology")
            created=client.post("/api/v1/connect/posts",json={"body":"API scientific update","visibility":"public"})
            self.assertEqual(created.status_code,201)
            self.assertEqual(client.get("/api/v1/connect/feed").json()["items"][0]["body"],"API scientific update")


if __name__ == "__main__": unittest.main()
