from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from biointel.connect.services import ConnectError, NotFound, PermissionDenied, build_connect_services

class MessagingFullTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name)
  self.system=build_connect_services(database_path=root/'connect.sqlite3',storage_root=root/'media')
  self.a=self.system.ensure_identity('msg-a','Message A'); self.b=self.system.ensure_identity('msg-b','Message B'); self.c=self.system.ensure_identity('msg-c','Message C'); self.m=self.system.complete.messaging
  r=self.system.network.request_connection(self.a['user_id'],self.b['user_id']); self.system.network.respond_connection(self.b['user_id'],r['request_id'],'accepted')
 def tearDown(self): self.temp.cleanup()
 def test_complete_message_lifecycle(self):
  aid,bid,cid=self.a['user_id'],self.b['user_id'],self.c['user_id']
  with self.assertRaises(ConnectError): self.m.create_conversation(aid,[bid],conversation_type='invalid')
  with self.assertRaises(ConnectError): self.m.create_conversation(aid,[],conversation_type='direct')
  cv=self.m.create_conversation(aid,[bid]); cvid=cv['conversation_id']; self.assertEqual(self.m.create_conversation(aid,[bid])['conversation_id'],cvid); self.assertTrue(self.m.list(aid))
  with self.assertRaises(PermissionDenied): self.m.get(cid,cvid)
  with self.assertRaises(ConnectError): self.m.send(aid,cvid,'',message_type='bad')
  with self.assertRaises(ConnectError): self.m.send(aid,cvid,'')
  with self.assertRaises(NotFound): self.m.send(aid,cvid,'reply',parent_message_id='missing')
  first=self.m.send(aid,cvid,'Initial result',client_event_id='idempotent'); self.assertEqual(self.m.send(aid,cvid,'ignored',client_event_id='idempotent')['message_id'],first['message_id'])
  reply=self.m.send(bid,cvid,'Confirmed',parent_message_id=first['message_id']); self.assertEqual(len(self.m.history(aid,cvid)),2); self.assertEqual(len(self.m.search(aid,'confirm',conversation_id=cvid)),1)
  self.m.update_receipt(bid,first['message_id'],'delivered'); self.m.update_receipt(bid,first['message_id'],'read')
  with self.assertRaises(ConnectError): self.m.update_receipt(bid,first['message_id'],'invalid')
  with self.assertRaises(PermissionDenied): self.m.update_receipt(bid,reply['message_id'],'read')
  self.assertEqual(self.m.edit(aid,first['message_id'],'Corrected result')['body'],'Corrected result')
  with self.assertRaises(PermissionDenied): self.m.edit(bid,first['message_id'],'tamper')
  with self.assertRaises(ConnectError): self.m.edit(aid,first['message_id'],' ')
  self.assertEqual(self.m.react(bid,first['message_id'],'verified')['reaction_type'],'verified'); self.assertEqual(self.m.save(bid,first['message_id'])['state'],'active'); self.assertEqual(self.m.save(bid,first['message_id'],False)['state'],'removed')
  self.assertTrue(self.m.typing(aid,cvid,True)); self.assertTrue(self.m.events(bid,acknowledge=True)); self.assertEqual(self.m.report_message(bid,first['message_id'],'other')['state'],'submitted')
  group=self.m.create_conversation(aid,[bid],conversation_type='group',title='Research group'); self.assertEqual(self.m.add_member(aid,group['conversation_id'],cid,'read_only')['role'],'read_only')
  with self.assertRaises(PermissionDenied): self.m.send(cid,group['conversation_id'],'cannot send')
  with self.assertRaises(ConnectError): self.m.add_member(aid,group['conversation_id'],cid,'invalid')
  self.assertEqual(self.m.remove_member(cid,group['conversation_id'],cid)['state'],'left'); self.assertEqual(self.m.delete(aid,first['message_id'])['state'],'deleted')
 def test_message_request_decisions(self):
  aid,cid=self.a['user_id'],self.c['user_id']; cv=self.m.create_conversation(aid,[cid])
  with self.system.database.connection(read_only=True) as db: request_id=db.execute('SELECT message_request_id FROM connect_message_requests WHERE conversation_id=?',(cv['conversation_id'],)).fetchone()[0]
  with self.assertRaises(PermissionDenied): self.m.respond_request(aid,request_id,'accepted')
  with self.assertRaises(ConnectError): self.m.respond_request(cid,request_id,'maybe')
  self.assertEqual(self.m.respond_request(cid,request_id,'accepted')['decision'],'accepted')
  with self.assertRaises(NotFound): self.m.respond_request(cid,request_id,'accepted')
if __name__=='__main__': unittest.main()

