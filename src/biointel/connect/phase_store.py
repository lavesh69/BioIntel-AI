from __future__ import annotations

import json
from collections.abc import MutableMapping, MutableSequence
from typing import Any, Callable, Iterator
from biointel.database.core import utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS connect_phase_resources(
  namespace TEXT NOT NULL,
  resource_key TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  PRIMARY KEY(namespace, resource_key)
);
"""

def ensure_phase_store(services: Any) -> None:
    with services.database.connection() as db:
        db.executescript(_SCHEMA)

def _plain(value: Any) -> Any:
    if isinstance(value, dict): return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list): return [_plain(v) for v in value]
    return value

class TrackedDict(dict):
    def __init__(self, value: dict[str, Any], callback: Callable[[], None]) -> None:
        self._callback=callback
        super().__init__({k:_tracked(v,callback) for k,v in value.items()})
    def __setitem__(self,key:Any,value:Any)->None: super().__setitem__(key,_tracked(value,self._callback)); self._callback()
    def __delitem__(self,key:Any)->None: super().__delitem__(key); self._callback()
    def clear(self)->None: super().clear(); self._callback()
    def pop(self,key:Any,default:Any=None)->Any: result=super().pop(key,default); self._callback(); return result
    def popitem(self)->tuple[Any,Any]: result=super().popitem(); self._callback(); return result
    def setdefault(self,key:Any,default:Any=None)->Any:
        if key not in self: self[key]=default
        return self[key]
    def update(self,*args:Any,**kwargs:Any)->None:
        for key,value in dict(*args,**kwargs).items(): super().__setitem__(key,_tracked(value,self._callback))
        self._callback()

class TrackedList(list):
    def __init__(self,value:list[Any],callback:Callable[[],None])->None: self._callback=callback; super().__init__(_tracked(v,callback) for v in value)
    def __setitem__(self,key:Any,value:Any)->None: super().__setitem__(key,_tracked(value,self._callback)); self._callback()
    def __delitem__(self,key:Any)->None: super().__delitem__(key); self._callback()
    def append(self,value:Any)->None: super().append(_tracked(value,self._callback)); self._callback()
    def extend(self,values:Any)->None: super().extend(_tracked(v,self._callback) for v in values); self._callback()
    def insert(self,index:int,value:Any)->None: super().insert(index,_tracked(value,self._callback)); self._callback()
    def pop(self,index:int=-1)->Any: result=super().pop(index); self._callback(); return result
    def remove(self,value:Any)->None: super().remove(value); self._callback()
    def clear(self)->None: super().clear(); self._callback()

def _tracked(value:Any,callback:Callable[[],None])->Any:
    if isinstance(value,TrackedDict|TrackedList): return value
    if isinstance(value,dict): return TrackedDict(value,callback)
    if isinstance(value,list): return TrackedList(value,callback)
    return value

class PersistentMap(MutableMapping[str,Any]):
    def __init__(self,services:Any,namespace:str)->None: self.services=services; self.namespace=namespace; ensure_phase_store(services)
    def _save(self,key:str,value:Any)->None:
        now=utc_now(); payload=json.dumps(_plain(value),sort_keys=True,separators=(",",":"))
        with self.services.database.connection() as db:
            db.execute("""INSERT INTO connect_phase_resources(namespace,resource_key,payload_json,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?) ON CONFLICT(namespace,resource_key) DO UPDATE SET payload_json=excluded.payload_json,updated_at_utc=excluded.updated_at_utc""",(self.namespace,key,payload,now,now))
    def __getitem__(self,key:str)->Any:
        with self.services.database.connection(read_only=True) as db: row=db.execute("SELECT payload_json FROM connect_phase_resources WHERE namespace=? AND resource_key=?",(self.namespace,key)).fetchone()
        if not row: raise KeyError(key)
        raw=json.loads(row[0]); holder:dict[str,Any]={}
        def save()->None: self._save(key,holder['value'])
        holder['value']=_tracked(raw,save); return holder['value']
    def __setitem__(self,key:str,value:Any)->None: self._save(key,value)
    def __delitem__(self,key:str)->None:
        with self.services.database.connection() as db:
            result=db.execute("DELETE FROM connect_phase_resources WHERE namespace=? AND resource_key=?",(self.namespace,key))
        if not result.rowcount: raise KeyError(key)
    def __iter__(self)->Iterator[str]:
        with self.services.database.connection(read_only=True) as db: rows=db.execute("SELECT resource_key FROM connect_phase_resources WHERE namespace=? ORDER BY resource_key",(self.namespace,)).fetchall()
        return iter([str(row[0]) for row in rows])
    def __len__(self)->int:
        with self.services.database.connection(read_only=True) as db: return int(db.execute("SELECT COUNT(*) FROM connect_phase_resources WHERE namespace=?",(self.namespace,)).fetchone()[0])

class PersistentList(TrackedList):
    def __init__(self,services:Any,namespace:str,key:str="items")->None:
        self._map=PersistentMap(services,namespace); self._key=key
        initial=self._map.get(key,[])
        super().__init__(_plain(initial),self._persist)
        if key not in self._map: self._persist()
    def _persist(self)->None: self._map[self._key]=_plain(self)
