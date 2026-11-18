from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from biointel.education import Conflict, Denied, EducationError, EducationPlatform
from biointel.education.universe import EducationUniverse


class EducationUniverseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.platform=EducationPlatform(self.root/'education.sqlite3',self.root/'media')
        self.admin='admin';self.teacher='teacher';self.student='student';self.outsider='outsider'
        self.institution=self.platform.create_institution(self.admin,'BioIntel University')['id']
        self.other_institution=self.platform.create_institution(self.outsider,'Other School','school')['id']
        self.platform.add_member(self.admin,self.institution,self.teacher,'subject_teacher')
        self.platform.add_member(self.admin,self.institution,self.student,'university_student')
        self.universe=EducationUniverse(self.platform)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def adaptive_payload():
        return {'evidence':['quiz_attempt:qa-1'],'rationale':'Review follows a missed prerequisite.','expected_outcome':'Improve topic recall.','dismissible':True}

    def test_all_twenty_modules_are_role_aware_and_persistent(self):
        modules=self.universe.modules(self.student,self.institution)
        self.assertEqual(len(modules),20);self.assertEqual(len({item['key'] for item in modules}),20)
        adaptive=next(item for item in modules if item['key']=='adaptive_learning');erp=next(item for item in modules if item['key']=='academic_erp')
        self.assertTrue(adaptive['can_create']);self.assertFalse(erp['can_create'])
        record=self.universe.create_record(self.student,self.institution,'adaptive_learning','learning_goal','Cell biology recovery',self.adaptive_payload())
        restarted=EducationUniverse(EducationPlatform(self.root/'education.sqlite3',self.root/'media'))
        self.assertEqual(restarted.get_record(self.student,record['id'])['title'],'Cell biology recovery')
        migrations={row['id'] for row in self.platform._all('SELECT id FROM education_migrations')};self.assertIn('education_universe_v1',migrations)

    def test_tenant_isolation_and_protected_question_bank(self):
        with self.assertRaises(Denied):self.universe.modules(self.outsider,self.institution)
        question=self.universe.create_record(self.teacher,self.institution,'question_bank','question','Protected answer key',{'subject':'BIO101','learning_outcome':'Explain DNA replication','review_status':'draft'})
        with self.assertRaises(Denied):self.universe.list_records(self.student,self.institution,'question_bank')
        with self.assertRaises(Denied):self.universe.get_record(self.student,question['id'])
        with self.assertRaises(Denied):self.universe.create_record(self.student,self.institution,'academic_erp','student_record','Unauthorized',{'subject_user_id':'x','academic_session':'2030'})
        self.assertEqual(self.universe.list_records(self.outsider,self.other_institution),[])

    def test_scientific_safety_and_external_evidence_boundaries(self):
        valid={'objective':'Observe simulated cell division','safety_briefing':'Simulation only; no physical procedure.','simulation_only':True}
        lab=self.universe.create_record(self.teacher,self.institution,'virtual_science_lab','simulation','Mitosis simulation',valid)
        self.assertEqual(lab['state'],'draft')
        with self.assertRaises(Denied):self.universe.create_record(self.teacher,self.institution,'virtual_science_lab','simulation','Unsafe',dict(valid,notes='pathogen culture instructions'))
        with self.assertRaises(Denied):self.universe.create_record(self.student,self.institution,'bioinformatics_sandbox','workspace','Shell',{'dataset_label':'public demo','method':'GC content','parameters':{},'resource_limit_seconds':30,'shell':'cmd.exe'})
        with self.assertRaises(EducationError):self.universe.create_record(self.teacher,self.institution,'career_hub','opportunity','Unverified',{'source_url':'invented','eligibility':'all','deadline':'2030-01-01'})
        with self.assertRaises(Denied):self.universe.create_record(self.admin,self.institution,'academic_erp','student_record','Payment leak',{'subject_user_id':'s','academic_session':'2030','card_number':'4111'})

    def test_review_state_machine_audit_and_optimistic_locking(self):
        record=self.universe.create_record(self.student,self.institution,'adaptive_learning','learning_goal','Revision plan',self.adaptive_payload())
        submitted=self.universe.transition_record(self.student,record['id'],record['version'],'submitted','Ready for review')
        reviewed=self.universe.transition_record(self.teacher,record['id'],submitted['version'],'under_review','Evidence checked')
        active=self.universe.transition_record(self.teacher,record['id'],reviewed['version'],'active','Approved')
        self.assertEqual(active['state'],'active');self.assertEqual(len(self.universe.record_history(self.student,record['id'])),4)
        with self.assertRaises(Conflict):self.universe.update_record(self.student,record['id'],1,title='Stale overwrite')
        self.assertEqual(self.universe.get_record(self.student,record['id'])['title'],'Revision plan')

    def test_completion_requires_real_processing_or_source_verification(self):
        lecture=self.universe.create_record(self.teacher,self.institution,'lecture_intelligence','processing_job','Hindi captions',{'lecture_id':'lec-1','processing_status':'configuration_required'})
        with self.assertRaises(Conflict):self.universe.transition_record(self.teacher,lecture['id'],lecture['version'],'published')
        opportunity=self.universe.create_record(self.teacher,self.institution,'career_hub','opportunity','Verified internship',{'source_url':'https://example.edu/internship','eligibility':'BSc students','deadline':'2030-02-01'})
        with self.assertRaises(Conflict):self.universe.transition_record(self.teacher,opportunity['id'],opportunity['version'],'published')
        updated=self.universe.update_record(self.teacher,opportunity['id'],opportunity['version'],payload={'source_url':'https://example.edu/internship','eligibility':'BSc students','deadline':'2030-02-01','verified_by':self.teacher})
        published=self.universe.transition_record(self.teacher,updated['id'],updated['version'],'published');self.assertEqual(published['state'],'published')

    def test_offline_sync_conflict_is_preserved_and_explicitly_resolved(self):
        record=self.universe.create_record(self.student,self.institution,'offline_learning','offline_draft','Local notes',{'device_scope':'current_windows_user'})
        operation=self.universe.queue_sync(self.student,self.institution,'device-op-1',record['id'],record['version'],{'title':'Offline title'})
        server=self.universe.update_record(self.teacher,record['id'],record['version'],title='Server title')
        conflict=self.universe.apply_sync(self.student,operation['id']);self.assertEqual(conflict['state'],'conflict');self.assertEqual(conflict['conflict']['server_version'],server['version'])
        resolved=self.universe.resolve_sync(self.student,operation['id'],'keep_server');self.assertEqual(resolved['record']['title'],'Server title');self.assertEqual(resolved['resolution'],'keep_server')

    def test_api_contract_and_navigation_visibility(self):
        import biointel.education.api as api
        old_platform,old_universe=api.PLATFORM,api.UNIVERSE;api.PLATFORM=self.platform;api.UNIVERSE=self.universe
        try:
            app=FastAPI()
            @app.middleware('http')
            async def identity(request:Request,call_next):
                request.state.api_identity=SimpleNamespace(client_id=request.headers.get('x-test-user','local-operator'))
                return await call_next(request)
            app.include_router(api.router);client=TestClient(app)
            path=f'/api/v1/education/universe/institutions/{self.institution}/modules'
            self.assertEqual(client.get(path).status_code,403)
            response=client.get(path,headers={'x-test-user':self.student});self.assertEqual(response.status_code,200);self.assertEqual(len(response.json()),20)
        finally:
            api.PLATFORM,api.UNIVERSE=old_platform,old_universe
        from biointel.ui.navigation import PAGE_BY_KEY,SIDEBAR_PRIMARY,catalogue_integrity
        self.assertIn('biointel_education_universe',SIDEBAR_PRIMARY)
        self.assertEqual(PAGE_BY_KEY['biointel_education_universe'].path,'pages/343_BioIntel_Education_Universe.py')
        project_root=Path(__file__).resolve().parents[1];self.assertTrue(catalogue_integrity(project_root)['healthy'])
        self.assertIn('safe_page_link("biointel_education_universe"',(project_root/'app.py').read_text(encoding='utf-8'))

    def test_collaboration_approvals_are_real_memberships_and_sync_is_idempotent(self):
        record=self.universe.create_record(self.admin,self.institution,'collaboration_network','agreement','Joint course',{'partner_institution_id':self.other_institution,'terms':'One shared guest lecture'})
        wrong=self.universe.update_record(self.admin,record['id'],record['version'],payload={'partner_institution_id':self.other_institution,'terms':'One shared guest lecture','source_approved_by':self.admin,'partner_approved_by':'not-an-admin'})
        with self.assertRaises(Denied):self.universe.transition_record(self.admin,wrong['id'],wrong['version'],'published')
        approved=self.universe.update_record(self.admin,wrong['id'],wrong['version'],payload={'partner_institution_id':self.other_institution,'terms':'One shared guest lecture','source_approved_by':self.admin,'partner_approved_by':self.outsider})
        self.assertEqual(self.universe.transition_record(self.admin,approved['id'],approved['version'],'published')['state'],'published')
        offline=self.universe.create_record(self.student,self.institution,'offline_learning','offline_draft','Idempotent draft',{'device_scope':'current_windows_user'})
        first=self.universe.queue_sync(self.student,self.institution,'same-op',offline['id'],offline['version'],{'title':'Once'})
        second=self.universe.queue_sync(self.student,self.institution,'same-op',offline['id'],offline['version'],{'title':'Once'})
        self.assertEqual(first['id'],second['id'])
        with self.assertRaises(Conflict):self.universe.queue_sync(self.student,self.institution,'same-op',offline['id'],offline['version'],{'title':'Different'})

if __name__=='__main__':unittest.main()