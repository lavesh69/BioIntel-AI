from __future__ import annotations
import hashlib,tempfile,unittest
from pathlib import Path
from biointel.database.core import utc_now
from biointel.connect.services import ConnectError,PermissionDenied,build_connect_services
from biointel.connect.phase_b import CollaborativeDocumentService,WhiteboardService,ResearchNotebookService,DataRoomService

class ConnectPhaseBTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.db=self.root/'db.sqlite3'; self.media=self.root/'media'; self.services=build_connect_services(database_path=self.db,storage_root=self.media); self.alpha=self.services.ensure_identity('alpha','Alpha'); self.beta=self.services.ensure_identity('beta','Beta'); self.doc_svc=CollaborativeDocumentService(self.services); self.wb_svc=WhiteboardService(self.services); self.nb_svc=ResearchNotebookService(self.services); self.dr_svc=DataRoomService(self.services)
    def tearDown(self): self.temp.cleanup()
    def test_1_documents_persist_and_exports_are_real(self):
        doc=self.doc_svc.create(self.alpha['user_id'],'Protocol','protocol','# Title',collaborator_ids=[self.beta['user_id']]); patch=self.doc_svc.apply_crdt_patch(self.beta['user_id'],doc['document_id'],'insert','\nMethod',expected_version=1); self.assertEqual(patch['version'],2)
        for fmt in ('markdown','pdf','docx'):
            exported=self.doc_svc.export(self.alpha['user_id'],doc['document_id'],fmt); self.assertTrue(Path(exported['_internal_path']).is_file()); self.assertGreater(exported['size_bytes'],0); self.assertEqual(len(exported['sha256']),64)
        restarted=build_connect_services(database_path=self.db,storage_root=self.media); persisted=CollaborativeDocumentService(restarted).export(self.alpha['user_id'],doc['document_id'],'markdown'); self.assertTrue(Path(persisted['_internal_path']).is_file())
    def test_2_whiteboard_export_is_real(self):
        board=self.wb_svc.create(self.alpha['user_id'],'Pathway','bioinformatics_workflow'); exported=self.wb_svc.export(self.alpha['user_id'],board['whiteboard_id']); self.assertTrue(Path(exported['_internal_path']).is_file()); self.assertGreater(exported['size_bytes'],0)
    def test_3_notebook_server_signature_and_restart(self):
        entry=self.nb_svc.create_entry(self.alpha['user_id'],'PCR','experiment','58C'); locked=self.nb_svc.lock_and_sign(self.alpha['user_id'],entry['entry_id'],'caller_fake'); self.assertNotEqual(locked['signature'],'caller_fake'); self.assertEqual(locked['signature_algorithm'],'HMAC-SHA256/server-managed-key')
        with self.assertRaises(PermissionDenied): self.nb_svc.lock_and_sign(self.beta['user_id'],entry['entry_id'])
        self.nb_svc.amend_entry(self.beta['user_id'],entry['entry_id'],'Observation','Band'); restarted=build_connect_services(database_path=self.db,storage_root=self.media); history=ResearchNotebookService(restarted).get_entry_history(self.alpha['user_id'],entry['entry_id']); self.assertEqual(history['entry']['version'],2); self.assertEqual(len(history['amendments']),1)
    def test_4_data_room_requires_agreement_and_assigned_file(self):
        room=self.dr_svc.create(self.alpha['user_id'],'Cohort','BioIntel')
        with self.assertRaises(PermissionDenied): self.dr_svc.download_file(self.beta['user_id'],room['room_id'],'file_1')
        self.dr_svc.accept_agreement(self.beta['user_id'],room['room_id']); source=self.root/'cohort.txt'; source.write_text('de-identified',encoding='utf-8'); now=utc_now()
        with self.services.database.connection() as db: db.execute("INSERT INTO connect_media_objects(media_id,owner_id,original_name,storage_path,mime_type,size_bytes,sha256,media_kind,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'document','available','private',?,?)",('file_1',self.alpha['user_id'],source.name,str(source),'text/plain',source.stat().st_size,hashlib.sha256(source.read_bytes()).hexdigest(),now,now))
        self.dr_svc.add_file(self.alpha['user_id'],room['room_id'],'file_1'); self.assertTrue(self.dr_svc.download_file(self.beta['user_id'],room['room_id'],'file_1')['is_authorized'])
        restarted=build_connect_services(database_path=self.db,storage_root=self.media); self.assertTrue(DataRoomService(restarted).download_file(self.beta['user_id'],room['room_id'],'file_1')['is_authorized'])
if __name__=='__main__': unittest.main()
