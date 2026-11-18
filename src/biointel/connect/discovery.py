from __future__ import annotations

import json
from typing import Any
from biointel.database.core import utc_now
from .repositories import ConnectRepository, new_id
from .services import ConnectError, PermissionDenied

class DiscoveryService:
    """Cross-entity search and explainable, feedback-aware recommendations."""
    def __init__(self,repo:ConnectRepository,profiles:Any,communities:Any,collaboration:Any)->None:
        self.repo,self.profiles,self.communities,self.collaboration=repo,profiles,communities,collaboration
    def search(self,viewer:str,query:str,types:list[str]|None=None,limit:int=20)->dict[str,Any]:
        query=query.strip(); selected=set(types or ["people","posts","communities","projects","publications","datasets","workflows","events","opportunities"]); result:dict[str,Any]={}
        if "people" in selected: result["people"]=self.profiles.search(viewer,query,limit)
        if "posts" in selected:
            like=f"%{query}%"
            with self.repo.database.connection(read_only=True) as db: rows=[dict(r) for r in db.execute("SELECT * FROM connect_posts WHERE state='published' AND deleted_at_utc IS NULL AND (title LIKE ? OR body LIKE ?) ORDER BY created_at_utc DESC LIMIT ?",(like,like,limit*3))]
            from .services import ContentService
            content=ContentService(self.repo); result["posts"]=[r for r in rows if content.can_view(viewer,r)][:limit]
        if "communities" in selected: result["communities"]=self.communities.list(viewer,query,limit)
        for kind in ("projects","publications","datasets","workflows","events","opportunities","collaborations"):
            if kind in selected: result[kind]=self.collaboration.list_resources(viewer,kind,query,limit)
        return {"query":query,"results":result,"count":sum(len(v) for v in result.values())}
    def recommend(self,viewer:str,kind:str="people",limit:int=10)->list[dict[str,Any]]:
        profile=self.repo.profile(viewer) or {}; interests=set(json.loads(profile.get("research_interests_json") or "[]")); skills=set(json.loads(profile.get("skills_json") or "[]"))
        feedback=self._feedback(viewer,kind); items=[]
        if kind=="people": candidates=self.profiles.search(viewer,"",max(limit*5,30))
        elif kind=="communities": candidates=self.communities.list(viewer,"",max(limit*5,30))
        else: candidates=self.collaboration.list_resources(viewer,kind,"",max(limit*5,30))
        for row in candidates:
            target_id=str(row.get("user_id") or row.get("community_id") or row.get("project_id") or row.get("publication_id") or row.get("dataset_id") or row.get("workflow_id") or row.get("event_id") or row.get("opportunity_id") or row.get("collaboration_id"))
            if target_id==viewer or feedback.get(target_id)=="not_interested": continue
            text=" ".join(str(v) for v in row.values() if isinstance(v,(str,int))).lower(); matches=sorted(x for x in interests|skills if str(x).lower() in text)
            score=1+len(matches)*3+(2 if feedback.get(target_id)=="helpful" else 0)
            reason=f"Matches {', '.join(matches[:3])}" if matches else "Active permission-safe scientific resource"
            items.append({"target_type":kind,"target_id":target_id,"score":score,"reason":reason,"item":row})
        return sorted(items,key=lambda x:(-x["score"],x["target_id"]))[:limit]
    def _feedback(self,user_id:str,kind:str)->dict[str,str]:
        with self.repo.database.connection(read_only=True) as db: return {str(r["target_id"]):str(r["signal"]) for r in db.execute("SELECT target_id,signal FROM connect_recommendation_feedback WHERE user_id=? AND target_type=? AND state='active'",(user_id,kind))}
    def feedback(self,user_id:str,target_type:str,target_id:str,signal:str,reason:str="")->dict[str,Any]:
        if signal not in {"helpful","not_interested","hide","report"}: raise ConnectError("Unsupported recommendation feedback.")
        now=utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_recommendation_feedback(feedback_id,creator_id,user_id,target_type,target_id,signal,reason,state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'active','private',?,?) ON CONFLICT(user_id,target_type,target_id) DO UPDATE SET signal=excluded.signal,reason=excluded.reason,updated_at_utc=excluded.updated_at_utc,version=connect_recommendation_feedback.version+1""",(new_id("recfb"),user_id,user_id,target_type,target_id,signal,reason[:1000],now,now)); row=db.execute("SELECT * FROM connect_recommendation_feedback WHERE user_id=? AND target_type=? AND target_id=?",(user_id,target_type,target_id)).fetchone()
        return dict(row)

class ShiroConnectService:
    """Approval-gated local assistant. It drafts only and never sends, publishes or changes privacy."""
    def __init__(self,repo:ConnectRepository,discovery:DiscoveryService)->None: self.repo,self.discovery=repo,discovery
    def assist(self,user_id:str,action:str,prompt:str,context:dict[str,Any]|None=None)->dict[str,Any]:
        allowed={"draft_post","draft_message","summarize_profile","suggest_collaborators","explain_recommendation","draft_community_description"}
        if action not in allowed: raise PermissionDenied("Shiro Connect may only perform approval-gated drafting and discovery.")
        context=context or {}; safe_prompt=prompt.strip()[:5000]
        if action=="suggest_collaborators": draft=self.discovery.recommend(user_id,"people",10)
        elif action=="summarize_profile":
            profile=self.repo.profile(user_id) or {}; draft={"summary":f"{profile.get('full_name','Researcher')} — {profile.get('headline','scientific collaborator')}","source":"user-approved profile fields"}
        else: draft={"text":safe_prompt,"context":context,"disclaimer":"Draft only. Review and approve before any external action."}
        self.repo.audit(user_id,"shiro_draft_generated","assistant",action,{"external_action":False})
        return {"action":action,"draft":draft,"requires_user_approval":True,"executed":False,"published":False,"sent":False,"privacy_changed":False,"generated_at_utc":utc_now()}
