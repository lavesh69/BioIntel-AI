from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .platform import ADMIN, STUDENT, TEACHER, Conflict, Denied, EducationError, Missing

MIGRATION_ID = "education_universe_v1"
SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_universe_records(
 id TEXT PRIMARY KEY,module_key TEXT NOT NULL,institution_id TEXT NOT NULL REFERENCES institutions(id),
 owner_id TEXT NOT NULL,record_type TEXT NOT NULL,title TEXT NOT NULL,state TEXT NOT NULL,
 visibility TEXT NOT NULL DEFAULT 'private',payload_json TEXT NOT NULL DEFAULT '{}',
 source_status TEXT NOT NULL DEFAULT 'user_entered',version INTEGER NOT NULL DEFAULT 1,
 deleted_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_universe_records_tenant ON education_universe_records(institution_id,module_key,state,updated_at);
CREATE INDEX IF NOT EXISTS idx_universe_records_owner ON education_universe_records(institution_id,owner_id,module_key);
CREATE TABLE IF NOT EXISTS education_universe_events(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),
 record_id TEXT NOT NULL REFERENCES education_universe_records(id),actor_id TEXT NOT NULL,
 event_type TEXT NOT NULL,from_state TEXT NOT NULL DEFAULT '',to_state TEXT NOT NULL DEFAULT '',
 detail_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_universe_events_record ON education_universe_events(record_id,created_at);
CREATE TABLE IF NOT EXISTS education_universe_sync_operations(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),actor_id TEXT NOT NULL,
 client_operation_id TEXT NOT NULL,record_id TEXT NOT NULL REFERENCES education_universe_records(id),
 base_version INTEGER NOT NULL,patch_json TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'queued',
 conflict_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(institution_id,actor_id,client_operation_id));
CREATE INDEX IF NOT EXISTS idx_universe_sync_queue ON education_universe_sync_operations(institution_id,actor_id,state,created_at);
"""

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"

@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    name: str
    record_types: tuple[str, ...]
    create_group: str
    purpose: str
    boundary: str
    required_fields: tuple[str, ...] = ()
    default_visibility: str = "private"

    def public(self) -> dict[str, Any]:
        return {
            "key": self.key,"name": self.name,"record_types": list(self.record_types),
            "purpose": self.purpose,"boundary": self.boundary,
            "required_fields": list(self.required_fields),"default_visibility": self.default_visibility,
        }

MODULES: tuple[ModuleDefinition, ...] = (
 ModuleDefinition("adaptive_learning","Adaptive Learning Engine",("learning_goal","mastery_evidence","recommendation","revision_plan"),"member","Explainable, adjustable learning paths based on permitted academic activity.","No diagnosis or permanent negative learner labels.",("evidence","rationale","expected_outcome","dismissible")),
 ModuleDefinition("virtual_science_lab","Virtual Science Lab",("simulation","observation","lab_report","teacher_review"),"teacher","Safe simulated practicals with observations and review.","Simulation is not permission to perform hazardous physical experiments.",("objective","safety_briefing","simulation_only"),"institution"),
 ModuleDefinition("bioinformatics_sandbox","Bioinformatics Learning Sandbox",("workspace","dataset","workflow_result","notebook_export"),"member","Resource-bounded educational sequence and demo-dataset workflows.","No unrestricted shell or unlabelled dataset.",("dataset_label","method","parameters","resource_limit_seconds")),
 ModuleDefinition("shiro_tutor","Shiro AI Teacher and Student Tutor",("tutoring_request","lesson_draft","practice_draft","revision_plan"),"member","Permission-aware educational assistance with visible AI labelling.","Cannot alter grades, attendance or approvals, or reveal protected answers.",("request","ai_generated","review_status")),
 ModuleDefinition("academic_erp","Academic ERP and Student Information System",("student_record","enrollment_record","academic_status","approval"),"admin","Institution-controlled academic administration records.","Finance is separate and raw payment-card data is forbidden.",("subject_user_id","academic_session"),"restricted"),
 ModuleDefinition("digital_library","Digital Scientific Library",("catalog_item","reading_list","citation","course_reserve"),"teacher","Source-linked cataloguing, citations and licensed access.","No unauthorized copyrighted full text.",("source_url","license_or_access"),"institution"),
 ModuleDefinition("research_hub","Student Research and Innovation Hub",("research_project","milestone","research_diary","mentor_request"),"member","Guided research projects with evidence, mentors and milestones.","Student work is not called peer reviewed unless verified.",("academic_level","research_question","ethics_consideration")),
 ModuleDefinition("competition_hub","Science Fair, Competition and Hackathon Center",("event","registration","submission","scorecard"),"teacher","Auditable events, submissions, scoring and feedback.","Rankings must come from stored submissions and scores.",("rules","deadline"),"institution"),
 ModuleDefinition("career_hub","Career, Internship, Scholarship and Placement Hub",("opportunity","saved_opportunity","application_checklist","application_status"),"teacher","Verified-source opportunities and application tracking.","Opportunities cannot be fabricated.",("source_url","eligibility","deadline"),"institution"),
 ModuleDefinition("academic_portfolio","Academic Portfolio and Verified Credentials",("achievement","project_evidence","skill_evidence","credential_request"),"member","Student-controlled evidence portfolios and reviewed credential requests.","Verified status requires authorized institutional approval.",("evidence",)),
 ModuleDefinition("laboratory_management","Practical Laboratory Management",("inventory_item","booking","training_record","incident_report"),"teacher","Rooms, equipment, bookings, training and incident audit workflows.","No high-risk automation or dangerous instructions.",("responsible_staff",),"restricted"),
 ModuleDefinition("question_bank","Question Bank and Assessment Intelligence",("question","blueprint","paper_draft","review"),"teacher","Institution-scoped assessment content with protected answer keys.","Students cannot list or retrieve protected question-bank records.",("subject","learning_outcome","review_status"),"restricted"),
 ModuleDefinition("lecture_intelligence","Multilingual Lecture Intelligence",("processing_job","chapter_draft","caption_draft","translation_draft"),"teacher","Review-gated transcript, caption and translation processing records.","Completion requires a real output artifact.",("lecture_id","processing_status"),"restricted"),
 ModuleDefinition("learning_analytics","Learning Analytics and Early Support",("metric_definition","metric_snapshot","support_review","intervention"),"teacher","Date-bounded analytics derived from real education events.","No unexplained risk score, diagnosis or fake metric.",("metric_definition","date_range","source_events"),"restricted"),
 ModuleDefinition("collaboration_network","Institutional Collaboration Network",("collaboration_proposal","agreement","joint_event","shared_resource_offer"),"admin","Explicit inter-institution proposals and agreements.","No tenant data is exposed automatically.",("partner_institution_id","terms"),"restricted"),
 ModuleDefinition("open_science","Open Science and Reproducibility Hub",("reproducibility_package","method_record","dataset_metadata","results_comparison"),"member","Versioned provenance, methods and export checklists.","Private student data cannot be published.",("method","provenance","license")),
 ModuleDefinition("offline_learning","Offline Learning and Campus LAN Mode",("offline_draft","cached_item_manifest","sync_note"),"member","Versioned offline drafts and explicit conflict resolution.","Never silently overwrites server state; LAN live classes need configuration.",("device_scope",)),
 ModuleDefinition("safety_moderation","Safety, Moderation and Minor Protection Center",("content_report","message_report","safety_concern","appeal"),"member","Private reports, evidence preservation and action history.","No legal child-safety certification is claimed.",("reason",),"restricted"),
 ModuleDefinition("quality_support","Education Quality and Accreditation Support",("course_outcome","curriculum_map","quality_review","improvement_action"),"admin","Internal evidence organization, reviews and improvement actions.","Does not claim accreditation.",("review_period","evidence"),"restricted"),
 ModuleDefinition("gamified_learning","Gamified Scientific Learning",("learning_goal","achievement_evidence","team_challenge","badge_request"),"member","Evidence-backed goals and age-appropriate motivation.","No fabricated achievements, public shaming or addictive patterns.",("evidence",)),
)
MODULE_BY_KEY = {item.key: item for item in MODULES}
VISIBILITIES = {"private","restricted","institution"}
STATES = {"draft","submitted","under_review","active","published","completed","rejected","archived","open","resolved"}
TRANSITIONS = {
 "draft":{"submitted","active","published","archived"},"submitted":{"under_review","rejected","active"},
 "under_review":{"active","published","completed","rejected"},"active":{"completed","resolved","archived"},
 "published":{"completed","archived"},"open":{"under_review","resolved","archived"},
 "rejected":{"draft","archived"},"completed":{"archived"},"resolved":{"archived"},"archived":set(),
}
DANGEROUS = ("pathogen culture","toxin synthesis","weaponize","explosive recipe","unrestricted shell","disable sandbox")
PAYMENT_KEYS = {"card_number","cvv","cvc","pin","track_data"}
NEGATIVE_LABELS = {"weak_student","poor_learner","learning_disorder","medical_diagnosis"}

class EducationUniverse:
    """Durable shared workflow service for the twenty Education Universe domains."""
    def __init__(self, platform: Any):
        self.platform=platform;self.db=platform.db;self.migrate()

    def migrate(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO education_migrations VALUES(?,datetime('now'))",(MIGRATION_ID,))
        return MIGRATION_ID

    def rollback(self) -> str:
        """Explicit development rollback; never invoked by install or runtime startup."""
        with self.db.connection() as db:
            db.execute("DROP TABLE IF EXISTS education_universe_sync_operations")
            db.execute("DROP TABLE IF EXISTS education_universe_events")
            db.execute("DROP TABLE IF EXISTS education_universe_records")
            db.execute("DELETE FROM education_migrations WHERE id=?",(MIGRATION_ID,))
        return MIGRATION_ID

    def _roles(self, actor: str, institution_id: str) -> set[str]:
        return {str(item["role"]) for item in self.platform._require(actor,institution_id)}

    @staticmethod
    def _group_allowed(group: str, roles: set[str]) -> bool:
        return bool(roles) if group=="member" else bool(roles & (TEACHER if group=="teacher" else ADMIN))

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value,sort_keys=True,separators=(",",":"))

    @staticmethod
    def _decode(record: dict[str, Any]) -> dict[str, Any]:
        result=dict(record);result["payload"]=json.loads(result.pop("payload_json") or "{}");return result

    def _definition(self, module_key: str) -> ModuleDefinition:
        if module_key not in MODULE_BY_KEY: raise EducationError("Unknown Education Universe module.")
        return MODULE_BY_KEY[module_key]

    def modules(self, actor: str, institution_id: str) -> list[dict[str, Any]]:
        roles=self._roles(actor,institution_id);result=[]
        for definition in MODULES:
            item=definition.public();item["can_create"]=self._group_allowed(definition.create_group,roles);result.append(item)
        return result

    def _validate(self, definition: ModuleDefinition, record_type: str, payload: dict[str, Any], publishing: bool=False) -> None:
        if record_type not in definition.record_types: raise EducationError("Unsupported record type for this module.")
        if not isinstance(payload,dict): raise EducationError("Record payload must be a JSON object.")
        encoded=self._json(payload).lower();keys={str(k).lower() for k in payload}
        if len(encoded.encode('utf-8'))>262144: raise EducationError("Record payload exceeds the 256 KiB safety limit.")
        if any(term in encoded for term in DANGEROUS): raise Denied("Unsafe operational content is blocked by the education safety boundary.")
        if keys & PAYMENT_KEYS: raise Denied("Raw payment-card or authentication data is forbidden.")
        if keys & NEGATIVE_LABELS: raise Denied("Permanent negative or diagnostic learner labels are forbidden.")
        missing=[field for field in definition.required_fields if field not in payload]
        if missing: raise EducationError(f"Required evidence fields are missing: {', '.join(missing)}.")
        if definition.key=="virtual_science_lab" and payload.get("simulation_only") is not True: raise Denied("Virtual lab records must remain simulation-only.")
        if definition.key=="bioinformatics_sandbox":
            seconds=int(payload.get("resource_limit_seconds",0))
            if seconds<1 or seconds>3600: raise EducationError("Sandbox resource limit must be between 1 and 3600 seconds.")
            if "command" in payload or "shell" in payload: raise Denied("Arbitrary shell execution is not accepted by the sandbox.")
        if definition.key in {"digital_library","career_hub"} and not str(payload.get("source_url","")).startswith(("https://","http://")): raise EducationError("A legitimate HTTP(S) source URL is required.")
        if definition.key=="shiro_tutor" and payload.get("ai_generated") is not True: raise EducationError("Shiro drafts must be visibly marked AI-generated.")
        if definition.key=="learning_analytics" and payload.get("risk_score") is not None and (not payload.get("risk_definition") or not payload.get("human_review")): raise Denied("Risk scores require a definition and human review.")
        if publishing and definition.key=="lecture_intelligence" and (not payload.get("output_uri") or not payload.get("processed_at")): raise Conflict("Lecture intelligence cannot complete without a real output artifact.")
        if publishing and definition.key=="career_hub" and not payload.get("verified_by"): raise Conflict("An authorized reviewer must verify an opportunity before publication.")
        if publishing and definition.key in {"academic_portfolio","gamified_learning"} and not payload.get("evidence"): raise Conflict("Real evidence is required before publication.")
        if publishing and definition.key=="collaboration_network" and (not payload.get("source_approved_by") or not payload.get("partner_approved_by")): raise Conflict("Both institutions must approve shared collaboration state.")
        if publishing and definition.key=="open_science" and payload.get("contains_private_data"): raise Denied("A package containing private data cannot be published.")

    def create_record(self, actor: str, institution_id: str, module_key: str, record_type: str, title: str, payload: dict[str, Any], visibility: str|None=None) -> dict[str, Any]:
        definition=self._definition(module_key);roles=self._roles(actor,institution_id)
        if not self._group_allowed(definition.create_group,roles): raise Denied("Your institution role cannot create this module record.")
        if not title.strip(): raise EducationError("A record title is required.")
        selected=visibility or definition.default_visibility
        if selected not in VISIBILITIES: raise EducationError("Invalid record visibility.")
        if module_key in {"question_bank","academic_erp","safety_moderation"}: selected="restricted"
        self._validate(definition,record_type,payload)
        rid=_id("edu");timestamp=_now();state="open" if module_key=="safety_moderation" else "draft"
        with self.db.connection() as db:
            db.execute("INSERT INTO education_universe_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,module_key,institution_id,actor,record_type,title.strip(),state,selected,self._json(payload),"user_entered",1,None,timestamp,timestamp))
            db.execute("INSERT INTO education_universe_events VALUES(?,?,?,?,?,?,?,?,?)",(_id("eduevt"),institution_id,rid,actor,"created","",state,"{}",timestamp))
        self.platform._audit(actor,"universe_record_created",module_key,rid,institution_id)
        return self.get_record(actor,rid)

    def _raw(self, record_id: str) -> dict[str, Any]:
        record=self.platform._one("SELECT * FROM education_universe_records WHERE id=? AND deleted_at IS NULL",(record_id,))
        if not record: raise Missing("Education Universe record not found.")
        return record

    @staticmethod
    def _privileged(roles: set[str]) -> bool: return bool(roles & TEACHER)

    def _check_read(self, actor: str, record: dict[str, Any]) -> set[str]:
        roles=self._roles(actor,record["institution_id"])
        if record["module_key"]=="question_bank" and roles & STUDENT and not self._privileged(roles): raise Denied("Protected question-bank access denied.")
        if record["visibility"] in {"private","restricted"} and record["owner_id"]!=actor and not self._privileged(roles): raise Denied("Private or restricted education record access denied.")
        return roles

    def get_record(self, actor: str, record_id: str) -> dict[str, Any]:
        record=self._raw(record_id);self._check_read(actor,record);return self._decode(record)

    def list_records(self, actor: str, institution_id: str, module_key: str|None=None, query: str="", limit: int=100) -> list[dict[str, Any]]:
        roles=self._roles(actor,institution_id)
        if module_key:
            self._definition(module_key)
            if module_key=="question_bank" and roles & STUDENT and not self._privileged(roles): raise Denied("Protected question-bank access denied.")
        clauses=["institution_id=?","deleted_at IS NULL"];args:list[Any]=[institution_id]
        if module_key: clauses.append("module_key=?");args.append(module_key)
        if query.strip(): clauses.append("(title LIKE ? OR payload_json LIKE ?)");token=f"%{query.strip()}%";args.extend((token,token))
        if not self._privileged(roles): clauses.append("(owner_id=? OR (visibility='institution' AND state IN ('active','published','completed')))");args.append(actor)
        args.append(max(1,min(int(limit),500)))
        records=self.platform._all(f"SELECT * FROM education_universe_records WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?",tuple(args))
        return [self._decode(record) for record in records]

    def update_record(self, actor: str, record_id: str, expected_version: int, title: str|None=None, payload: dict[str,Any]|None=None, visibility: str|None=None) -> dict[str, Any]:
        record=self._raw(record_id);roles=self._check_read(actor,record)
        if actor!=record["owner_id"] and not self._privileged(roles): raise Denied("Record edit permission denied.")
        if int(expected_version)!=int(record["version"]): raise Conflict("Version conflict; refresh before editing.")
        if record["state"] not in {"draft","rejected","open"} and not self._privileged(roles): raise Conflict("Only an educator can edit this workflow state.")
        next_title=(title if title is not None else record["title"]).strip()
        if not next_title: raise EducationError("A record title is required.")
        next_payload=payload if payload is not None else json.loads(record["payload_json"]);self._validate(self._definition(record["module_key"]),record["record_type"],next_payload)
        next_visibility=visibility or record["visibility"]
        if next_visibility not in VISIBILITIES: raise EducationError("Invalid record visibility.")
        if record["module_key"] in {"question_bank","academic_erp","safety_moderation"}: next_visibility="restricted"
        timestamp=_now();version=int(record["version"])+1
        with self.db.connection() as db:
            changed=db.execute("UPDATE education_universe_records SET title=?,payload_json=?,visibility=?,version=?,updated_at=? WHERE id=? AND version=?",(next_title,self._json(next_payload),next_visibility,version,timestamp,record_id,expected_version)).rowcount
            if changed!=1: raise Conflict("Concurrent update detected; no data was overwritten.")
            db.execute("INSERT INTO education_universe_events VALUES(?,?,?,?,?,?,?,?,?)",(_id("eduevt"),record["institution_id"],record_id,actor,"updated",record["state"],record["state"],self._json({"version":version}),timestamp))
        self.platform._audit(actor,"universe_record_updated",record["module_key"],record_id,record["institution_id"])
        return self.get_record(actor,record_id)

    def transition_record(self, actor: str, record_id: str, expected_version: int, to_state: str, note: str="") -> dict[str, Any]:
        record=self._raw(record_id);roles=self._check_read(actor,record)
        if int(expected_version)!=int(record["version"]): raise Conflict("Version conflict; refresh before changing state.")
        if to_state not in STATES or to_state not in TRANSITIONS.get(record["state"],set()): raise Conflict(f"Invalid transition from {record['state']} to {to_state}.")
        privileged=self._privileged(roles)
        if to_state in {"active","published","completed","resolved","rejected","archived"} and not privileged and not (record["owner_id"]==actor and to_state in {"completed","archived"}): raise Denied("Educator review is required for this transition.")
        if record["owner_id"]!=actor and not privileged: raise Denied("Workflow transition permission denied.")
        payload=json.loads(record["payload_json"]);self._validate(self._definition(record["module_key"]),record["record_type"],payload,to_state in {"published","completed"})
        if to_state in {"published","completed"} and record["module_key"]=="collaboration_network":
            partner=str(payload.get("partner_institution_id",""));source_approver=str(payload.get("source_approved_by",""));partner_approver=str(payload.get("partner_approved_by",""))
            if not partner or partner==record["institution_id"] or not self.platform._one("SELECT 1 ok FROM institutions WHERE id=? AND state='active'",(partner,)): raise Conflict("A distinct active partner institution is required.")
            source_roles={x["role"] for x in self.platform.membership(source_approver,record["institution_id"])};partner_roles={x["role"] for x in self.platform.membership(partner_approver,partner)}
            if not source_roles & ADMIN or not partner_roles & ADMIN: raise Denied("Both approvals must belong to authorized institution administrators.")
        timestamp=_now();version=int(record["version"])+1
        with self.db.connection() as db:
            changed=db.execute("UPDATE education_universe_records SET state=?,version=?,updated_at=? WHERE id=? AND version=?",(to_state,version,timestamp,record_id,expected_version)).rowcount
            if changed!=1: raise Conflict("Concurrent state change detected; no data was overwritten.")
            db.execute("INSERT INTO education_universe_events VALUES(?,?,?,?,?,?,?,?,?)",(_id("eduevt"),record["institution_id"],record_id,actor,"state_changed",record["state"],to_state,self._json({"note":note[:1000],"version":version}),timestamp))
        self.platform._audit(actor,"universe_state_changed",record["module_key"],record_id,record["institution_id"],{"from":record["state"],"to":to_state})
        return self.get_record(actor,record_id)

    def delete_record(self, actor: str, record_id: str, expected_version: int) -> dict[str, Any]:
        record=self._raw(record_id);roles=self._check_read(actor,record)
        if int(expected_version)!=int(record["version"]): raise Conflict("Version conflict; refresh before deleting.")
        if actor!=record["owner_id"] and not bool(roles & ADMIN): raise Denied("Only the owner or an administrator may delete this record.")
        if record["state"] not in {"draft","rejected","archived"} and not bool(roles & ADMIN): raise Conflict("Active records must be archived before deletion.")
        timestamp=_now()
        with self.db.connection() as db:
            db.execute("UPDATE education_universe_records SET deleted_at=?,version=version+1,updated_at=? WHERE id=?",(timestamp,timestamp,record_id))
            db.execute("INSERT INTO education_universe_events VALUES(?,?,?,?,?,?,?,?,?)",(_id("eduevt"),record["institution_id"],record_id,actor,"soft_deleted",record["state"],record["state"],"{}",timestamp))
        self.platform._audit(actor,"universe_record_deleted",record["module_key"],record_id,record["institution_id"])
        return {"id":record_id,"deleted":True,"deleted_at":timestamp}

    def record_history(self, actor: str, record_id: str) -> list[dict[str, Any]]:
        record=self._raw(record_id);self._check_read(actor,record);events=self.platform._all("SELECT * FROM education_universe_events WHERE record_id=? ORDER BY created_at",(record_id,))
        for event in events: event["detail"]=json.loads(event.pop("detail_json") or "{}")
        return events

    def dashboard(self, actor: str, institution_id: str) -> dict[str, Any]:
        roles=self._roles(actor,institution_id)
        if self._privileged(roles):
            rows=self.platform._all("SELECT module_key,state,COUNT(*) count FROM education_universe_records WHERE institution_id=? AND deleted_at IS NULL GROUP BY module_key,state ORDER BY module_key,state",(institution_id,))
        else:
            grouped: dict[tuple[str,str], int] = {}
            for definition in MODULES:
                if definition.key == "question_bank" and roles & STUDENT:
                    continue
                for record in self.list_records(actor,institution_id,module_key=definition.key,limit=500):
                    key=(record["module_key"],record["state"]);grouped[key]=grouped.get(key,0)+1
            rows=[{"module_key":module,"state":state,"count":count} for (module,state),count in sorted(grouped.items())]
        pending=self.platform._one("SELECT COUNT(*) count FROM education_universe_sync_operations WHERE institution_id=? AND actor_id=? AND state IN ('queued','conflict')",(institution_id,actor))
        return {"module_count":len(MODULES),"stored_counts":rows,"pending_sync":int(pending["count"] if pending else 0),"generated_at":_now(),"metric_definition":"Counts include only records visible to the current institution member."}

    def queue_sync(self, actor: str, institution_id: str, client_operation_id: str, record_id: str, base_version: int, patch: dict[str,Any]) -> dict[str, Any]:
        record=self._raw(record_id)
        if record["institution_id"]!=institution_id: raise Denied("Cross-institution synchronization denied.")
        self._check_read(actor,record)
        if record["owner_id"]!=actor: raise Denied("Offline drafts may only be queued by their owner.")
        if not patch or set(patch)-{"title","payload","visibility"}: raise EducationError("Offline patch may only contain title, payload and visibility.")
        existing=self.platform._one("SELECT * FROM education_universe_sync_operations WHERE institution_id=? AND actor_id=? AND client_operation_id=?",(institution_id,actor,client_operation_id))
        if existing:
            if existing["record_id"]!=record_id or int(existing["base_version"])!=int(base_version) or existing["patch_json"]!=self._json(patch): raise Conflict("Client operation ID was already used for different content.")
            return existing
        oid=_id("sync");timestamp=_now()
        with self.db.connection() as db: db.execute("INSERT INTO education_universe_sync_operations VALUES(?,?,?,?,?,?,?,?,?,?,?)",(oid,institution_id,actor,client_operation_id,record_id,int(base_version),self._json(patch),"queued","{}",timestamp,timestamp))
        return self.platform._one("SELECT * FROM education_universe_sync_operations WHERE id=?",(oid,))

    def apply_sync(self, actor: str, operation_id: str) -> dict[str, Any]:
        operation=self.platform._one("SELECT * FROM education_universe_sync_operations WHERE id=?",(operation_id,))
        if not operation: raise Missing("Synchronization operation not found.")
        if operation["actor_id"]!=actor: raise Denied("Synchronization queue access denied.")
        if operation["state"]!="queued": return operation
        record=self._raw(operation["record_id"])
        if int(record["version"])!=int(operation["base_version"]):
            conflict={"reason":"server_version_changed","server_version":int(record["version"]),"base_version":int(operation["base_version"]),"server_updated_at":record["updated_at"]}
            with self.db.connection() as db: db.execute("UPDATE education_universe_sync_operations SET state='conflict',conflict_json=?,updated_at=? WHERE id=?",(self._json(conflict),_now(),operation_id))
            result=self.platform._one("SELECT * FROM education_universe_sync_operations WHERE id=?",(operation_id,));result["conflict"]=json.loads(result.pop("conflict_json"));return result
        patch=json.loads(operation["patch_json"]);updated=self.update_record(actor,record["id"],int(record["version"]),patch.get("title"),patch.get("payload"),patch.get("visibility"))
        with self.db.connection() as db: db.execute("UPDATE education_universe_sync_operations SET state='applied',updated_at=? WHERE id=?",(_now(),operation_id))
        return {"operation_id":operation_id,"state":"applied","record":updated}

    def resolve_sync(self, actor: str, operation_id: str, choice: str) -> dict[str, Any]:
        operation=self.platform._one("SELECT * FROM education_universe_sync_operations WHERE id=?",(operation_id,))
        if not operation: raise Missing("Synchronization operation not found.")
        if operation["actor_id"]!=actor or operation["state"]!="conflict": raise Denied("Synchronization conflict access denied.")
        if choice not in {"keep_server","apply_client"}: raise EducationError("Resolution must be keep_server or apply_client.")
        record=self._raw(operation["record_id"])
        if choice=="apply_client":
            patch=json.loads(operation["patch_json"]);updated=self.update_record(actor,record["id"],int(record["version"]),patch.get("title"),patch.get("payload"),patch.get("visibility"))
        else: updated=self.get_record(actor,record["id"])
        with self.db.connection() as db: db.execute("UPDATE education_universe_sync_operations SET state='resolved',conflict_json=?,updated_at=? WHERE id=?",(self._json({"resolution":choice}),_now(),operation_id))
        self.platform._audit(actor,"offline_sync_resolved","education_universe_sync",operation_id,operation["institution_id"],{"resolution":choice})
        return {"operation_id":operation_id,"state":"resolved","resolution":choice,"record":updated}