from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from biointel.connect.services import ConnectError,PermissionDenied,build_connect_services
from biointel.connect.planning import PlanningService
class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.db=self.root/'db.sqlite3'; self.media=self.root/'media'; self.services=build_connect_services(database_path=self.db,storage_root=self.media); self.owner=self.services.ensure_identity('owner','Owner'); self.member=self.services.ensure_identity('member','Member'); self.outsider=self.services.ensure_identity('outsider','Outsider'); self.project=self.services.complete.collaboration.create_project(self.owner['user_id'],title='Project'); self.services.complete.collaboration.add_project_member(self.owner['user_id'],self.project['project_id'],self.member['user_id'],'researcher'); self.svc=PlanningService(self.services)
    def tearDown(self): self.temp.cleanup()
    def test_dependencies_progress_authorization_and_restart(self):
        first=self.svc.create_task(self.owner['user_id'],self.project['project_id'],'Prepare'); second=self.svc.create_task(self.member['user_id'],self.project['project_id'],'Analyze',dependency_ids=[first['task_id']]);
        with self.assertRaises(ConnectError): self.svc.set_task_status(self.member['user_id'],second['task_id'],'completed')
        with self.assertRaises(PermissionDenied): self.svc.list_tasks(self.outsider['user_id'],self.project['project_id'])
        self.svc.set_task_status(self.owner['user_id'],first['task_id'],'completed'); self.svc.set_task_status(self.member['user_id'],second['task_id'],'completed'); self.assertEqual(self.svc.progress(self.owner['user_id'],self.project['project_id'])['completion_percent'],100.0)
        restarted=build_connect_services(database_path=self.db,storage_root=self.media); self.assertEqual(len(PlanningService(restarted).list_tasks(self.owner['user_id'],self.project['project_id'])),2)
if __name__=='__main__': unittest.main()
