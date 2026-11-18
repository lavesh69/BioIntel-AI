from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from biointel.database.core import utc_now
from biointel.connect.services import ConnectError, PermissionDenied
from biointel.connect.phase_store import PersistentMap

UTC=timezone.utc

def _sha(path:Path)->str:
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()

class CollaborativeDocumentService:
    def __init__(self,services:Any)->None: self.services=services; self._documents=PersistentMap(services,'phase_b.documents'); self._revisions=PersistentMap(services,'phase_b.document_revisions')
    def _get(self,user_id:str,doc_id:str,write:bool=False)->dict[str,Any]:
        doc=self._documents.get(doc_id)
        if not doc: raise ConnectError('Document not found.')
        allowed=user_id==doc['owner_id'] or user_id in doc.get('collaborator_ids',[])
        if not allowed: raise PermissionDenied('Document membership required.')
        if write and doc.get('state')!='active': raise ConnectError('Document is not editable.')
        return doc
    def create(self,user_id:str,title:str,doc_type:str='manuscript',content:str='',project_id:Optional[str]=None,collaborator_ids:Optional[List[str]]=None)->Dict[str,Any]:
        if not title.strip(): raise ConnectError('Document title is required.')
        doc_id=f'doc_{uuid.uuid4().hex}'; now=utc_now(); folder=Path(self.services.media.storage_root)/'documents'/doc_id; folder.mkdir(parents=True,exist_ok=True); source=folder/'source.md'; source.write_text(content,encoding='utf-8')
        doc={'document_id':doc_id,'owner_id':user_id,'collaborator_ids':sorted(set(collaborator_ids or [])),'title':title.strip(),'doc_type':doc_type,'content':content,'project_id':project_id,'source_path':str(source),'version':1,'state':'active','visibility':'private','created_at_utc':now,'updated_at_utc':now}
        self._documents[doc_id]=doc; self._revisions[doc_id]=[{'version':1,'editor_id':user_id,'content_sha256':hashlib.sha256(content.encode()).hexdigest(),'created_at_utc':now}]; return dict(doc)
    def apply_crdt_patch(self,user_id:str,doc_id:str,patch_op:str,text_delta:str,expected_version:Optional[int]=None)->Dict[str,Any]:
        doc=self._get(user_id,doc_id,True)
        if expected_version is not None and int(doc['version'])!=expected_version: raise ConnectError('Document version conflict; reload before editing.')
        if patch_op=='insert': content=str(doc['content'])+text_delta
        elif patch_op=='replace': content=text_delta
        else: raise ConnectError('Supported operations are insert and replace.')
        doc['content']=content; doc['version']=int(doc['version'])+1; doc['updated_at_utc']=utc_now(); Path(doc['source_path']).write_text(content,encoding='utf-8'); history=self._revisions[doc_id]; history.append({'version':doc['version'],'editor_id':user_id,'content_sha256':hashlib.sha256(content.encode()).hexdigest(),'created_at_utc':doc['updated_at_utc']})
        return {'document_id':doc_id,'applied_by':user_id,'patch_op':patch_op,'version':doc['version'],'conflict_resolved':False,'persistence':'durable_optimistic_version','timestamp_utc':doc['updated_at_utc']}
    def export(self,user_id:str,doc_id:str,format_kind:str='markdown')->Dict[str,Any]:
        doc=self._get(user_id,doc_id); folder=Path(doc['source_path']).parent/'exports'; folder.mkdir(exist_ok=True); fmt='md' if format_kind=='markdown' else format_kind; path=folder/f"v{doc['version']}.{fmt}"
        if format_kind=='markdown': path.write_text(doc['content'],encoding='utf-8')
        elif format_kind=='pdf':
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            c=canvas.Canvas(str(path),pagesize=A4); width,height=A4; y=height-60; c.setTitle(doc['title']); c.setFont('Helvetica-Bold',14); c.drawString(50,y,doc['title']); y-=28; c.setFont('Helvetica',10)
            for raw in str(doc['content']).splitlines() or ['']:
                for start in range(0,max(len(raw),1),95):
                    if y<50: c.showPage(); c.setFont('Helvetica',10); y=height-60
                    c.drawString(50,y,raw[start:start+95]); y-=14
            c.save()
        elif format_kind=='docx':
            from docx import Document
            d=Document(); d.add_heading(doc['title'],0)
            for line in str(doc['content']).splitlines(): d.add_paragraph(line)
            d.save(path)
        else: raise ConnectError(f'Unsupported export format: {format_kind}')
        if not path.is_file() or path.stat().st_size==0: raise ConnectError('Document export did not produce a valid file.')
        return {'document_id':doc_id,'requested_by':user_id,'format':format_kind,'artifact_name':path.name,'size_bytes':path.stat().st_size,'sha256':_sha(path),'state':'available','generated_at_utc':utc_now(),'_internal_path':str(path)}
    def compact_crdt_history(self,user_id:str,doc_id:str)->Dict[str,Any]:
        doc=self._get(user_id,doc_id)
        if user_id!=doc['owner_id']: raise PermissionDenied('Only document owner may compact revision history.')
        return {'document_id':doc_id,'history_compacted':False,'reason':'Immutable revision history is retained; no CRDT engine is claimed.','snapshot_version':doc['version']}

class WhiteboardService:
    def __init__(self,services:Any)->None: self.services=services; self._boards=PersistentMap(services,'phase_b.whiteboards')
    def create(self,user_id:str,title:str,template:str='custom')->Dict[str,Any]:
        wb_id=f'wb_{uuid.uuid4().hex}'; now=utc_now(); board={'whiteboard_id':wb_id,'owner_id':user_id,'title':title,'template':template,'elements':[],'state':'active','created_at_utc':now,'updated_at_utc':now}; self._boards[wb_id]=board; return dict(board)
    def export(self,user_id:str,wb_id:str,format_kind:str='png')->Dict[str,Any]:
        board=self._boards.get(wb_id)
        if not board or board['owner_id']!=user_id: raise PermissionDenied('Whiteboard owner access required.')
        if format_kind!='png': raise ConnectError('Only PNG whiteboard export is currently supported.')
        from PIL import Image,ImageDraw
        folder=Path(self.services.media.storage_root)/'whiteboards'; folder.mkdir(parents=True,exist_ok=True); path=folder/f'{wb_id}.png'; image=Image.new('RGB',(1280,720),'white'); draw=ImageDraw.Draw(image); draw.text((40,35),board['title'],fill='black'); draw.text((40,70),f"Template: {board['template']}",fill='#334155'); image.save(path)
        return {'whiteboard_id':wb_id,'format':'png','artifact_name':path.name,'size_bytes':path.stat().st_size,'sha256':_sha(path),'state':'available','_internal_path':str(path),'generated_at_utc':utc_now()}

class ResearchNotebookService:
    def __init__(self,services:Any)->None:
        self.services=services; self._entries=PersistentMap(services,'phase_b.notebook_entries'); self._amendments=PersistentMap(services,'phase_b.notebook_amendments'); key_dir=Path(services.media.storage_root)/'keys'; key_dir.mkdir(parents=True,exist_ok=True); self._key_path=key_dir/'eln_signing.key'
        if not self._key_path.exists(): self._key_path.write_bytes(os.urandom(32))
    def create_entry(self,user_id:str,title:str,entry_type:str,content:str,project_id:Optional[str]=None)->Dict[str,Any]:
        entry_id=f'entry_{uuid.uuid4().hex}'; now=utc_now(); entry={'entry_id':entry_id,'author_id':user_id,'title':title,'entry_type':entry_type,'content':content,'project_id':project_id,'is_locked':False,'signature':None,'signature_algorithm':None,'version':1,'created_at_utc':now,'updated_at_utc':now}; self._entries[entry_id]=entry; self._amendments[entry_id]=[]; return dict(entry)
    def lock_and_sign(self,user_id:str,entry_id:str,signature_hash:Optional[str]=None)->Dict[str,Any]:
        entry=self._entries.get(entry_id)
        if not entry: raise ConnectError('Notebook entry not found.')
        if entry['author_id']!=user_id: raise PermissionDenied('Only entry author can sign and lock the notebook record.')
        if entry['is_locked']: return dict(entry)
        canonical=json.dumps({k:v for k,v in entry.items() if k not in {'signature','signature_algorithm','updated_at_utc'}},sort_keys=True,separators=(',',':')).encode(); entry['signature']=hmac.new(self._key_path.read_bytes(),canonical,hashlib.sha256).hexdigest(); entry['signature_algorithm']='HMAC-SHA256/server-managed-key'; entry['is_locked']=True; entry['updated_at_utc']=utc_now(); return dict(entry)
    def amend_entry(self,user_id:str,entry_id:str,amendment_reason:str,new_content:str)->Dict[str,Any]:
        entry=self._entries.get(entry_id)
        if not entry: raise ConnectError('Notebook entry not found.')
        if not entry['is_locked']: raise ConnectError('Unlocked notebook entries can be edited directly without amendments.')
        now=utc_now(); amendment={'amendment_id':f'amend_{uuid.uuid4().hex}','entry_id':entry_id,'amended_by':user_id,'reason':amendment_reason,'new_content':new_content,'content_sha256':hashlib.sha256(new_content.encode()).hexdigest(),'timestamp_utc':now}; history=self._amendments[entry_id]; history.append(amendment); entry['version']=int(entry['version'])+1; entry['updated_at_utc']=now; return amendment
    def get_entry_history(self,user_id:str,entry_id:str)->Dict[str,Any]:
        entry=self._entries.get(entry_id)
        if not entry: raise ConnectError('Notebook entry not found.')
        if user_id!=entry['author_id']: raise PermissionDenied('Notebook author access required.')
        return {'entry':dict(entry),'amendments':[dict(x) for x in self._amendments.get(entry_id,[])]}

class DataRoomService:
    def __init__(self,services:Any)->None: self.services=services; self._rooms=PersistentMap(services,'phase_b.data_rooms'); self._agreements=PersistentMap(services,'phase_b.data_room_agreements'); self._files=PersistentMap(services,'phase_b.data_room_files')
    def create(self,user_id:str,title:str,institution:str)->Dict[str,Any]:
        room_id=f'dataroom_{uuid.uuid4().hex}'; now=utc_now(); room={'room_id':room_id,'owner_id':user_id,'title':title,'institution':institution,'state':'active','watermark_enabled':True,'created_at_utc':now}; self._rooms[room_id]=room; self._agreements[room_id]={user_id:{'accepted_at_utc':now,'expires_at_utc':None}}; self._files[room_id]=[]; return dict(room)
    def accept_agreement(self,user_id:str,room_id:str,days:int=30)->Dict[str,Any]:
        if not self._rooms.get(room_id): raise ConnectError('Data room not found.')
        now=datetime.now(UTC); agreements=self._agreements[room_id]; agreements[user_id]={'accepted_at_utc':now.isoformat(),'expires_at_utc':(now+timedelta(days=max(1,min(days,365)))).isoformat()}; return {'room_id':room_id,'user_id':user_id,'agreement_accepted':True,**agreements[user_id]}
    def add_file(self,user_id:str,room_id:str,media_id:str)->Dict[str,Any]:
        room=self._rooms.get(room_id)
        if not room or room['owner_id']!=user_id: raise PermissionDenied('Data-room owner access required.')
        with self.services.database.connection(read_only=True) as db: media=db.execute("SELECT media_id,sha256,size_bytes,mime_type FROM connect_media_objects WHERE media_id=? AND state='available'",(media_id,)).fetchone()
        if not media: raise ConnectError('Available media object required.')
        files=self._files[room_id]
        if media_id not in files: files.append(media_id)
        return {'room_id':room_id,'media_id':media_id,'sha256':media['sha256'],'size_bytes':media['size_bytes'],'mime_type':media['mime_type']}
    def download_file(self,user_id:str,room_id:str,file_id:str)->Dict[str,Any]:
        room=self._rooms.get(room_id)
        if not room: raise ConnectError('Data room not found.')
        agreement=self._agreements.get(room_id,{}).get(user_id)
        if not agreement: raise PermissionDenied('A current confidentiality agreement is required.')
        expiry=agreement.get('expires_at_utc')
        if expiry and datetime.fromisoformat(expiry)<=datetime.now(UTC): raise PermissionDenied('Data-room agreement expired.')
        if file_id not in self._files.get(room_id,[]): raise PermissionDenied('File is not assigned to this data room.')
        return {'room_id':room_id,'media_id':file_id,'watermark':f'CONFIDENTIAL - AUTHORIZED USER {hashlib.sha256(user_id.encode()).hexdigest()[:12]} - {utc_now()}','is_authorized':True,'access_expires_at_utc':expiry}
