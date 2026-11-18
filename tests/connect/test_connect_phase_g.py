from __future__ import annotations
import json,os,tempfile,threading,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from biointel.connect.services import PermissionDenied,build_connect_services
from biointel.connect.phase_g import InstitutionalTenantService,EnterpriseIdentityService,DeveloperPlatformService,WebhookAutomationService
class Receiver(BaseHTTPRequestHandler):
    received=[]
    def do_POST(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0'))); self.__class__.received.append((dict(self.headers),body)); self.send_response(204); self.end_headers()
    def log_message(self,*args): pass
class ConnectPhaseGTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.db=self.root/'db.sqlite3'; self.media=self.root/'media'; self.services=build_connect_services(database_path=self.db,storage_root=self.media); self.alpha=self.services.ensure_identity('alpha','Alpha'); self.admin=self.services.ensure_identity('admin','Admin','administrator'); self.tenant_svc=InstitutionalTenantService(self.services); self.sso_svc=EnterpriseIdentityService(self.services); self.dev_svc=DeveloperPlatformService(self.services); self.hook_svc=WebhookAutomationService(self.services)
    def tearDown(self): self.temp.cleanup()
    def test_1_multi_institution_tenant_isolation(self):
        t1=self.tenant_svc.create_tenant(self.admin['user_id'],'A','a.example'); t2=self.tenant_svc.create_tenant(self.admin['user_id'],'B','b.example'); self.assertTrue(self.tenant_svc.check_tenant_isolation(t1['tenant_id'],t1['tenant_id']));
        with self.assertRaises(PermissionDenied): self.tenant_svc.check_tenant_isolation(t1['tenant_id'],t2['tenant_id'])
    def test_2_enterprise_identity_and_jit_provisioning(self): self.assertEqual(self.sso_svc.provision_jit_user('oidc','ext','u@example.org','User')['provider'],'oidc'); self.assertEqual(self.sso_svc.revoke_session(self.admin['user_id'],'sess')['state'],'revoked')
    def test_3_developer_api_key_secret_shown_once_and_hashed(self):
        result=self.dev_svc.create_api_key(self.alpha['user_id'],'Importer',['read:datasets']); self.assertTrue(result['raw_secret'].startswith('biointel_secret_')); self.assertNotEqual(result['key_info']['hashed_secret'],result['raw_secret']); restarted=build_connect_services(database_path=self.db,storage_root=self.media); self.assertIn(result['key_info']['key_id'],DeveloperPlatformService(restarted)._api_keys)
    def test_4_webhook_performs_signed_http_delivery(self):
        Receiver.received=[]; server=ThreadingHTTPServer(('127.0.0.1',0),Receiver); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start(); old=os.environ.get('BIOINTEL_WEBHOOK_ALLOW_PRIVATE'); os.environ['BIOINTEL_WEBHOOK_ALLOW_PRIVATE']='1'
        try:
            secret='0123456789abcdef0123456789abcdef'; hook=self.hook_svc.register_webhook(self.alpha['user_id'],f'http://127.0.0.1:{server.server_port}/hook',['post.created'],secret); self.assertNotIn('secret',hook); delivery=self.hook_svc.trigger_event(hook['webhook_id'],'post.created',{'post_id':'post_99'}); self.assertEqual(delivery['delivery_status'],'delivered'); self.assertEqual(delivery['http_status'],204); self.assertEqual(len(Receiver.received),1); headers,body=Receiver.received[0]; self.assertTrue({k.lower():v for k,v in headers.items()}['x-biointel-signature'].startswith('sha256=')); self.assertEqual(json.loads(body)['event'],'post.created')
        finally:
            server.shutdown(); server.server_close();
            if old is None: os.environ.pop('BIOINTEL_WEBHOOK_ALLOW_PRIVATE',None)
            else: os.environ['BIOINTEL_WEBHOOK_ALLOW_PRIVATE']=old
if __name__=='__main__': unittest.main()

