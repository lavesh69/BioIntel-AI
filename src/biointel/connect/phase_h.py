from __future__ import annotations

import hashlib
import json
import re
import uuid
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List
from biointel.database.core import utc_now
from biointel.connect.services import ConnectError
from biointel.connect.phase_store import PersistentMap

class NetworkAnalyticsService:
    """Privacy-safe analytics derived only from persisted Connect records."""
    def __init__(self, services: Any) -> None: self.services=services
    def get_user_analytics(self,user_id:str)->Dict[str,Any]:
        with self.services.database.connection(read_only=True) as db:
            posts=int(db.execute("SELECT COUNT(*) FROM connect_posts WHERE author_id=? AND state='published'",(user_id,)).fetchone()[0])
            comments=int(db.execute("SELECT COUNT(*) FROM connect_comments WHERE author_id=? AND state='published'",(user_id,)).fetchone()[0])
            messages=int(db.execute("SELECT COUNT(*) FROM connect_messages WHERE sender_id=? AND state='active'",(user_id,)).fetchone()[0])
            reactions=int(db.execute("SELECT COUNT(*) FROM connect_reactions r JOIN connect_posts p ON p.post_id=r.target_id WHERE r.target_type='post' AND p.author_id=? AND r.state='active'",(user_id,)).fetchone()[0])
            dataset_requests=int(db.execute("SELECT COUNT(*) FROM connect_dataset_access_requests WHERE requester_id=?",(user_id,)).fetchone()[0])
            workflow_count=int(db.execute("SELECT COUNT(*) FROM connect_workflow_listings WHERE owner_id=?",(user_id,)).fetchone()[0])
        return {"user_id":user_id,"posts_published":posts,"comments_created":comments,"messages_sent":messages,"post_reactions_received":reactions,"dataset_requests":dataset_requests,"workflows_owned":workflow_count,"profile_views":None,"profile_views_status":"not_collected","generated_at_utc":utc_now(),"metric_source":"persisted_connect_tables"}
    def get_community_analytics(self,community_id:str)->Dict[str,Any]:
        with self.services.database.connection(read_only=True) as db:
            if not db.execute("SELECT 1 FROM connect_communities WHERE community_id=?",(community_id,)).fetchone(): raise ConnectError("Community not found.")
            members=int(db.execute("SELECT COUNT(*) FROM connect_community_members WHERE community_id=? AND state='active'",(community_id,)).fetchone()[0])
            posts=int(db.execute("SELECT COUNT(*) FROM connect_posts WHERE community_id=? AND state='published'",(community_id,)).fetchone()[0])
            discussions=int(db.execute("SELECT COUNT(*) FROM connect_comments c JOIN connect_posts p ON p.post_id=c.post_id WHERE p.community_id=? AND c.state='published'",(community_id,)).fetchone()[0])
        return {"community_id":community_id,"member_count":members,"posts_count":posts,"discussions_count":discussions,"active_weekly_members":None,"active_weekly_members_status":"not_collected","generated_at_utc":utc_now(),"metric_source":"persisted_connect_tables"}

class ScientificTrendService:
    def __init__(self,services:Any)->None: self.services=services
    def discover_trends(self,category:str="topics")->List[Dict[str,Any]]:
        with self.services.database.connection(read_only=True) as db:
            rows=db.execute("""SELECT h.display_tag,COUNT(*) AS uses,COUNT(DISTINCT p.author_id) AS authors,MAX(p.created_at_utc) AS last_seen FROM connect_hashtags h JOIN connect_post_hashtags ph ON ph.hashtag_id=h.hashtag_id JOIN connect_posts p ON p.post_id=ph.post_id WHERE p.state='published' GROUP BY h.hashtag_id,h.display_tag ORDER BY uses DESC,h.display_tag LIMIT 25""").fetchall()
        return [{"topic":str(r[0]),"source_volume":int(r[1]),"distinct_authors":int(r[2]),"last_seen_at_utc":r[3],"trend_direction":"not_enough_history","scientific_validity_note":"Popularity only; no scientific-validity inference is made.","category":category} for r in rows]

class DigitalPreservationService:
    def __init__(self,services:Any)->None: self.services=services; self._bundles=PersistentMap(services,"phase_h.preservation_bundles")
    def create_reproducibility_bundle(self,user_id:str,title:str,dataset_ids:List[str],workflow_ids:List[str])->Dict[str,Any]:
        bundle_id=f"bundle_{uuid.uuid4().hex}"; now=utc_now(); root=Path(self.services.media.storage_root)/"preservation"; root.mkdir(parents=True,exist_ok=True)
        manifest={"bundle_id":bundle_id,"creator_id":user_id,"title":title,"dataset_ids":list(dict.fromkeys(dataset_ids)),"workflow_ids":list(dict.fromkeys(workflow_ids)),"created_at_utc":now,"format":"BioIntel reproducibility bundle v1","preservation_claim":"local_fixity_package_only"}
        manifest_bytes=json.dumps(manifest,indent=2,sort_keys=True).encode("utf-8"); archive=root/f"{bundle_id}.zip"
        with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED) as z: z.writestr("manifest.json",manifest_bytes); z.writestr("SHA256SUMS.txt",f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n")
        with zipfile.ZipFile(archive) as z:
            bad=z.testzip()
            if bad: raise ConnectError(f"Preservation ZIP verification failed at {bad}.")
        checksum=hashlib.sha256(archive.read_bytes()).hexdigest(); bundle={**manifest,"archive_path":str(archive),"size_bytes":archive.stat().st_size,"sha256_checksum":checksum,"preservation_status":"local_package_created","permanent_archive":False,"fixity_verified":True}
        self._bundles[bundle_id]=bundle; return bundle
    def verify_bundle(self,user_id:str,bundle_id:str)->Dict[str,Any]:
        bundle=self._bundles.get(bundle_id)
        if not bundle: raise ConnectError("Preservation bundle not found.")
        if bundle["creator_id"]!=user_id: raise ConnectError("Preservation bundle is not accessible.")
        path=Path(bundle["archive_path"]); actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        return {"bundle_id":bundle_id,"archive_exists":path.is_file(),"checksum_matches":bool(actual and actual==bundle["sha256_checksum"]),"sha256_checksum":actual,"verified_at_utc":utc_now()}
