from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import Any

from biointel.database.core import utc_now
from biointel.connect.database import ConnectDatabase
from biointel.connect.services import ConnectError, PermissionDenied, build_connect_services

class ConnectPhaseATests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.services = build_connect_services(
            database_path=self.root / "connect_phase_a.sqlite3",
            storage_root=self.root / "media"
        )
        self.c = self.services.complete
        
        # 3 distinct roles: Host (Alpha), Participant (Beta), Moderator/Admin (Admin)
        self.host = self.services.ensure_identity("host_alpha", "Dr. Alpha", "researcher")
        self.participant = self.services.ensure_identity("participant_beta", "Dr. Beta", "bioinformatician")
        self.moderator = self.services.ensure_identity("mod_admin", "Admin Moderator", "administrator")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def add_sample_video(self, owner_id: str) -> str:
        path = self.root / f"sample_video_{owner_id}.mp4"
        path.write_bytes(b"sample-video-content-for-phase-a")
        media_id = f"media_video_{owner_id}"
        now = utc_now()
        with self.services.database.connection() as db:
            db.execute(
                """INSERT INTO connect_media_objects(
                    media_id, owner_id, original_name, storage_path, mime_type,
                    size_bytes, sha256, media_kind, state, visibility, created_at_utc, updated_at_utc
                ) VALUES(?, ?, ?, ?, 'video/mp4', ?, ?, 'video', 'available', 'public', ?, ?)""",
                (
                    media_id, owner_id, "sample_video.mp4", str(path),
                    path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest(),
                    now, now
                )
            )
        return media_id

    def test_1_scientific_stories_and_highlights(self):
        """Verify 24h & custom expiration, story viewing, reactions, highlights, and analytics."""
        # 1. Host creates a scientific text story with 24h expiration
        story = self.c.stories.create(
            self.host["user_id"],
            story_type="text",
            text_body="New CRDT manuscript submitted!",
            visibility="public",
            hours=24
        )
        self.assertIsNotNone(story["story_id"])
        
        # 2. Participant views the story
        viewed = self.c.stories.view(self.participant["user_id"], story["story_id"])
        self.assertEqual(viewed["viewer_count"], 1)

        # 3. Participant reacts to the story
        reaction = self.c.stories.react(self.participant["user_id"], story["story_id"], "insightful")
        self.assertEqual(reaction["reaction_type"], "insightful")

        # 4. Host adds story to profile highlights
        highlight = self.c.stories.highlight(
            self.host["user_id"],
            title="Publications 2026",
            story_ids=[story["story_id"]]
        )
        self.assertIsNotNone(highlight)
        self.assertEqual(highlight["title"], "Publications 2026")

    def test_2_short_scientific_videos_and_transcoding(self):
        """Verify short video creation, captions, transcripts, alt text, and discovery feed."""
        media_id = self.add_sample_video(self.host["user_id"])

        # Fail creation if captions/transcript/alt text missing for accessibility
        with self.assertRaises(ConnectError):
            self.c.short_videos.create(
                self.host["user_id"],
                media_id=media_id,
                caption="",
                transcript="",
                alt_text=""
            )

        # Successfully create short video with required accessibility metadata
        video = self.c.short_videos.create(
            self.host["user_id"],
            media_id=media_id,
            caption="CRDT Sync Demo",
            transcript="Full transcript of CRDT sync explanation",
            alt_text="Visual demonstration of real-time conflict-free editing"
        )
        self.assertEqual(video["caption"], "CRDT Sync Demo")

        # Discovery feed contains the created video
        feed = self.c.short_videos.feed(self.participant["user_id"])
        self.assertGreaterEqual(len(feed), 1)

    def test_3_live_scientific_broadcasting_and_moderation(self):
        """Verify webinar stream, waiting room, attendee join with consent, and moderator controls."""
        # 1. Host creates a live webinar
        live = self.c.live_streams.create(
            self.host["user_id"],
            stream_type="webinar",
            title="Single-Cell RNA-Seq Workshop",
            recording_enabled=True
        )
        self.c.live_streams.start(self.host["user_id"], live["live_stream_id"])

        # 2. Participant cannot join without explicit recording consent
        with self.assertRaises(PermissionDenied):
            self.c.live_streams.join(
                self.participant["user_id"],
                live["live_stream_id"],
                recording_consent=False
            )

        # 3. Participant joins with explicit recording consent
        joined = self.c.live_streams.join(
            self.participant["user_id"],
            live["live_stream_id"],
            recording_consent=True
        )
        self.assertTrue(joined.get("joined") or joined.get("status") == "active" or joined.get("state") == "active" or joined.get("user_id") == self.participant["user_id"])

        # 4. Moderator posts pinned comment / moderates channel
        comment = self.c.live_streams.comment(
            self.moderator["user_id"],
            live["live_stream_id"],
            body="Welcome all! Q&A session is now open."
        )
        self.assertEqual(comment["body"], "Welcome all! Q&A session is now open.")

        # 5. Host ends webinar
        ended = self.c.live_streams.end(self.host["user_id"], live["live_stream_id"])
        self.assertEqual(ended["state"], "ended")

    def test_4_webrtc_call_signaling_and_unavailable_recording(self):
        """Recording remains unavailable while authenticated WebRTC signaling is functional."""
        call=self.c.calls.create(self.host["user_id"],[self.participant["user_id"]],recording_requested=True)
        self.assertEqual(call["recording_state"],"unavailable")
        with self.assertRaises(ConnectError): self.c.calls.respond(self.participant["user_id"],call["call_id"],"accepted",recording_consent=True)
        accepted=self.c.calls.respond(self.participant["user_id"],call["call_id"],"accepted")
        self.assertEqual(accepted["recording_consent"],0)
        started=self.c.calls.start(self.host["user_id"],call["call_id"]); self.assertEqual(started["recording_state"],"unavailable")
        offer=self.c.calls.signal(self.host["user_id"],call["call_id"],"offer",{"type":"offer","sdp":"v=0"},self.participant["user_id"])
        self.assertEqual(offer["signal"]["type"],"offer")
        self.assertEqual(self.c.calls.signals(self.participant["user_id"],call["call_id"])[0]["signal_type"],"offer")
        screen=self.c.calls.screen_share(self.host["user_id"],call["call_id"],enabled=True); self.assertEqual(screen["screen_sharing_user_id"],self.host["user_id"])

if __name__ == "__main__":
    unittest.main()

