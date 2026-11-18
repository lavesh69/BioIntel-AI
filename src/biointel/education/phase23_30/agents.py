from __future__ import annotations

import time
from typing import Any

from ..platform import Conflict, Denied, EducationError, ident, now
from .base import Phase30Base, decode_json, encode_json, normalized_key

MAX_AGENT_DEPTH = 4
AGENT_STATES = {
    "created",
    "planned",
    "awaiting_approval",
    "running",
    "awaiting_human_input",
    "completed",
    "failed",
    "cancelled",
    "partially_completed",
}
PROHIBITED_AUTONOMOUS_ACTIONS = {
    "publish_official_grades",
    "expel_student",
    "suspend_student",
    "medical_diagnosis",
    "psychiatric_diagnosis",
    "admissions_decision",
    "certify_academic_completion",
    "send_institution_wide_message",
    "delete_records",
    "change_access_permissions",
    "irreversible_bulk_operation",
}

TOOLS: dict[str, dict[str, Any]] = {
    "search_course_material": {
        "description": "Search tenant-permitted course material.",
        "permission": "view",
        "write": False,
        "approval": False,
    },
    "search_science_pulse": {
        "description": "Search locally indexed scientific records.",
        "permission": "view",
        "write": False,
        "approval": False,
    },
    "query_shiro_collection": {
        "description": "Query a governed Shiro collection.",
        "permission": "view",
        "write": False,
        "approval": False,
    },
    "create_draft_lesson": {
        "description": "Create an unpublished lesson draft.",
        "permission": "create",
        "write": True,
        "approval": True,
    },
    "create_draft_quiz": {
        "description": "Create an unpublished quiz draft.",
        "permission": "create",
        "write": True,
        "approval": True,
    },
    "create_learning_plan": {
        "description": "Create a reviewable student learning-plan draft.",
        "permission": "create",
        "write": True,
        "approval": True,
    },
    "retrieve_progress": {
        "description": "Read permitted progress aggregates.",
        "permission": "view",
        "write": False,
        "approval": False,
    },
    "verify_citation": {
        "description": "Validate supplied identifiers against local evidence.",
        "permission": "review",
        "write": False,
        "approval": False,
    },
    "draft_assessment": {
        "description": "Create an unpublished assessment draft.",
        "permission": "create",
        "write": True,
        "approval": True,
    },
    "draft_lecture": {
        "description": "Create an unpublished lecture package.",
        "permission": "create",
        "write": True,
        "approval": True,
    },
}

AGENTS: dict[str, dict[str, Any]] = {
    "student_tutor": {
        "name": "Student Tutor Agent",
        "description": "Course-aware Socratic tutoring and remediation.",
        "tools": [
            "search_course_material",
            "query_shiro_collection",
            "retrieve_progress",
            "create_learning_plan",
        ],
        "prohibited": ["complete_restricted_graded_work"],
    },
    "teacher_assistant": {
        "name": "Teacher Assistant Agent",
        "description": "Draft lessons, worksheets, rubrics, quizzes and interventions.",
        "tools": [
            "search_course_material",
            "create_draft_lesson",
            "create_draft_quiz",
            "retrieve_progress",
        ],
        "prohibited": ["publish_without_teacher_approval"],
    },
    "examination_authoring": {
        "name": "Examination Authoring Agent",
        "description": "Draft mapped, reviewable examination questions.",
        "tools": ["search_course_material", "draft_assessment"],
        "prohibited": ["publish_official_grades", "publish_without_examiner_approval"],
    },
    "research_assistant": {
        "name": "Research Assistant Agent",
        "description": "Build citation-linked evidence tables and literature comparisons.",
        "tools": ["search_science_pulse", "verify_citation"],
        "prohibited": ["fabricate_paper", "fabricate_identifier"],
    },
    "parent_progress": {
        "name": "Parent Progress Assistant",
        "description": "Produce parent-safe, permission-filtered progress summaries.",
        "tools": ["retrieve_progress"],
        "prohibited": ["expose_restricted_internal_analytics"],
    },
    "academic_advisor": {
        "name": "Academic Advisor Agent",
        "description": "Draft prerequisite-aware learning pathways for advisor review.",
        "tools": ["search_course_material", "retrieve_progress", "create_learning_plan"],
        "prohibited": ["make_admissions_decision"],
    },
    "lecture_production": {
        "name": "Lecture Production Agent",
        "description": "Draft cited lecture, slide and quiz packages.",
        "tools": [
            "search_course_material",
            "verify_citation",
            "draft_lecture",
            "create_draft_quiz",
        ],
        "prohibited": ["publish_without_teacher_approval"],
    },
    "scientific_verification": {
        "name": "Scientific Content Verification Agent",
        "description": "Map claims to evidence and flag unsupported content.",
        "tools": ["search_science_pulse", "verify_citation"],
        "prohibited": ["invent_supporting_evidence"],
    },
}


class AgentMixin(Phase30Base):
    def seed_agent_registry(self) -> dict[str, int]:
        timestamp = now()
        with self.db.connection() as db:
            for key, tool in TOOLS.items():
                db.execute(
                    """INSERT INTO education_p30_agent_tools
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(key) DO UPDATE SET
                    name=excluded.name,description=excluded.description,
                    permission=excluded.permission,write_operation=excluded.write_operation,
                    human_approval_required=excluded.human_approval_required,
                    timeout_seconds=excluded.timeout_seconds,state='active',
                    updated_at=excluded.updated_at""",
                    (
                        f"agenttool_{key}",
                        key,
                        key.replace("_", " ").title(),
                        tool["description"],
                        tool["permission"],
                        int(tool["write"]),
                        int(tool["approval"]),
                        60,
                        "active",
                        timestamp,
                        timestamp,
                    ),
                )
            for key, agent in AGENTS.items():
                db.execute(
                    """INSERT INTO education_p30_agent_definitions
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(institution_id,key,version) DO UPDATE SET
                    name=excluded.name,description=excluded.description,
                    allowed_tools_json=excluded.allowed_tools_json,
                    prohibited_actions_json=excluded.prohibited_actions_json,
                    output_schema_json=excluded.output_schema_json,
                    provider_policy_json=excluded.provider_policy_json,
                    memory_policy_json=excluded.memory_policy_json,state='active',
                    updated_at=excluded.updated_at""",
                    (
                        f"agentdef_{key}_v1",
                        "",
                        key,
                        agent["name"],
                        agent["description"],
                        encode_json(agent["tools"]),
                        encode_json(
                            sorted(set(agent["prohibited"]) | PROHIBITED_AUTONOMOUS_ACTIONS)
                        ),
                        encode_json(
                            {
                                "required": [
                                    "summary",
                                    "artifacts",
                                    "citations",
                                    "limitations",
                                ]
                            }
                        ),
                        encode_json(
                            {
                                "default": "local",
                                "external_optional": True,
                                "truthful_unconfigured_state": True,
                            }
                        ),
                        encode_json(
                            {
                                "default": "task_only",
                                "student_private_memory": False,
                                "retention_controlled": True,
                            }
                        ),
                        "1.0.0",
                        "active",
                        timestamp,
                        timestamp,
                    ),
                )
        return {"agents": len(AGENTS), "tools": len(TOOLS)}

    def agent_registry(
        self,
        actor: str,
        institution_id: str,
    ) -> list[dict[str, Any]]:
        self._require(actor, institution_id, "member")
        self.seed_agent_registry()
        return self._all(
            """SELECT * FROM education_p30_agent_definitions
            WHERE institution_id IN ('',?) AND state='active' ORDER BY name""",
            (institution_id,),
        )

    def create_agent_task(
        self,
        actor: str,
        institution_id: str,
        *,
        agent_key: str,
        task_input: dict[str, Any],
        requested_tools: list[str] | None = None,
        provider: str = "local",
        provider_model: str = "",
        subject_user_id: str = "",
        parent_task_id: str = "",
        idempotency_key: str,
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "member")
        self.seed_agent_registry()
        key = normalized_key(agent_key)
        definition = self._one(
            """SELECT * FROM education_p30_agent_definitions
            WHERE key=? AND institution_id IN ('',?) AND state='active'
            ORDER BY CASE WHEN institution_id=? THEN 0 ELSE 1 END LIMIT 1""",
            (key, institution_id, institution_id),
        )
        if not definition:
            raise EducationError("Agent definition is not active.")
        requested_action = normalized_key(
            str(task_input.get("requested_action", "draft"))
        )
        if requested_action in PROHIBITED_AUTONOMOUS_ACTIONS:
            raise Denied("Requested action is prohibited for autonomous agents.")
        if (
            key == "student_tutor"
            and task_input.get("graded_work")
            and task_input.get("request_direct_answer")
        ):
            raise Denied("Student Tutor cannot directly complete restricted graded work.")
        allowed_tools = set(decode_json(definition["allowed_tools_json"], []))
        tools = requested_tools or sorted(allowed_tools)
        unknown = sorted(set(tools) - allowed_tools)
        if unknown:
            raise Denied(f"Agent tool is not allowlisted: {', '.join(unknown)}")
        parent_id: str | None = None
        depth = 0
        root_task_id = ""
        if parent_task_id:
            parent = self._tenant_row(
                "education_p30_agent_tasks",
                parent_task_id,
                institution_id,
            )
            depth = int(parent["depth"]) + 1
            if depth > MAX_AGENT_DEPTH:
                raise Denied("Maximum agent delegation depth exceeded.")
            parent_id = parent_task_id
            root_task_id = str(parent["root_task_id"])
        tool_rows = self._all(
            f"""SELECT * FROM education_p30_agent_tools
            WHERE key IN ({','.join('?' for _ in tools)}) AND state='active'""",
            tuple(tools),
        ) if tools else []
        approval_required = any(
            bool(row["human_approval_required"]) or bool(row["write_operation"])
            for row in tool_rows
        )
        task_id = ident("agenttask")
        root_task_id = root_task_id or task_id
        state = "awaiting_approval" if approval_required else "planned"
        timestamp = now()
        plan = [
            {
                "sequence": index,
                "tool": tool,
                "state": "pending",
            }
            for index, tool in enumerate(tools, start=1)
        ]
        plan.append(
            {
                "sequence": len(plan) + 1,
                "tool": "",
                "state": "pending",
                "operation": "validate_output",
            }
        )
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_agent_tasks
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task_id,
                    institution_id,
                    key,
                    parent_id,
                    root_task_id,
                    depth,
                    actor,
                    subject_user_id,
                    encode_json(task_input),
                    encode_json(plan),
                    encode_json(tools),
                    provider,
                    provider_model,
                    state,
                    int(approval_required),
                    "pending" if approval_required else "not_required",
                    "{}",
                    "{}",
                    "",
                    0,
                    0.0,
                    0,
                    0,
                    min(900, max(5, int(timeout_seconds))),
                    normalized_key(idempotency_key, maximum=160),
                    timestamp,
                    timestamp,
                ),
            )
            db.executemany(
                """INSERT INTO education_p30_agent_steps
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        ident("agentstep"),
                        task_id,
                        int(step["sequence"]),
                        str(step.get("tool", "")),
                        "pending",
                        "{}",
                        "{}",
                        "",
                        None,
                        None,
                    )
                    for step in plan
                ],
            )
            if approval_required:
                db.execute(
                    """INSERT INTO education_p30_agent_approvals
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        ident("agentapproval"),
                        task_id,
                        "pre_execution",
                        actor,
                        "pending",
                        "",
                        "",
                        timestamp,
                        None,
                    ),
                )
        self._audit(
            actor,
            institution_id,
            "agent_task_created",
            "agent_task",
            task_id,
            {"agent": key, "approval_required": approval_required, "depth": depth},
        )
        return self._tenant_row(
            "education_p30_agent_tasks",
            task_id,
            institution_id,
        )

    def approve_agent_task(
        self,
        actor: str,
        task_id: str,
        *,
        decision: str,
        note: str = "",
    ) -> dict[str, Any]:
        task = self._tenant_row("education_p30_agent_tasks", task_id)
        institution_id = str(task["institution_id"])
        self._require(actor, institution_id, "staff")
        if task["state"] != "awaiting_approval":
            raise Conflict("Agent task is not awaiting approval.")
        if actor == task["requested_by"]:
            raise Denied("Approval-controlled agent tasks require a second authorized human.")
        if decision not in {"approved", "rejected"}:
            raise EducationError("Agent approval decision must be approved or rejected.")
        timestamp = now()
        next_state = "planned" if decision == "approved" else "cancelled"
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_agent_approvals
                SET decision=?,decided_by=?,decision_note=?,decided_at=?
                WHERE task_id=? AND checkpoint='pre_execution'""",
                (decision, actor, note, timestamp, task_id),
            )
            db.execute(
                """UPDATE education_p30_agent_tasks
                SET approval_state=?,state=?,updated_at=? WHERE id=?""",
                (decision, next_state, timestamp, task_id),
            )
        self._audit(
            actor,
            institution_id,
            "agent_task_approval",
            "agent_task",
            task_id,
            {"decision": decision},
        )
        return self._tenant_row(
            "education_p30_agent_tasks",
            task_id,
            institution_id,
        )

    def _agent_output(
        self,
        agent_key: str,
        task_input: dict[str, Any],
        citations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        topic = str(
            task_input.get("topic")
            or task_input.get("question")
            or task_input.get("title")
            or "Requested learning task"
        ).strip()
        modes = {
            "student_tutor": "Socratic tutoring plan",
            "teacher_assistant": "Teacher-review lesson package",
            "examination_authoring": "Examiner-review assessment draft",
            "research_assistant": "Citation-linked evidence table",
            "parent_progress": "Parent-safe progress summary",
            "academic_advisor": "Advisor-review prerequisite pathway",
            "lecture_production": "Faculty-review lecture package",
            "scientific_verification": "Claim-evidence verification",
        }
        artifacts = [
            {
                "type": modes[agent_key],
                "title": topic,
                "state": "draft",
                "human_review_required": True,
            }
        ]
        limitations = []
        if not citations and agent_key in {
            "research_assistant",
            "lecture_production",
            "scientific_verification",
        }:
            limitations.append("No supplied evidence could be verified; publication is blocked.")
        return {
            "summary": f"{modes[agent_key]} prepared for: {topic}",
            "artifacts": artifacts,
            "citations": citations,
            "limitations": limitations,
            "safety": {
                "official_action_performed": False,
                "publication_performed": False,
                "human_review_required": True,
            },
        }

    def execute_agent_task(
        self,
        actor: str,
        task_id: str,
    ) -> dict[str, Any]:
        task = self._tenant_row("education_p30_agent_tasks", task_id)
        institution_id = str(task["institution_id"])
        self._require(actor, institution_id, "member")
        if actor != task["requested_by"] and not self._roles(actor, institution_id).intersection(
            {"platform_administrator", "institution_administrator", "subject_teacher", "professor", "lecturer"}
        ):
            raise Denied("Agent task execution access denied.")
        if task["state"] == "awaiting_approval":
            raise Conflict("Human approval is required before execution.")
        if task["state"] not in {"planned", "failed"}:
            raise Conflict("Agent task cannot be executed from its current state.")
        if task["provider"] != "local":
            raise Conflict("External agent provider is configured but not locally verified.")
        if task["cancel_requested"]:
            raise Conflict("Agent task was cancelled.")
        started = time.perf_counter()
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_p30_agent_tasks SET state='running',updated_at=? WHERE id=?",
                (timestamp, task_id),
            )
        task_input = decode_json(task["input_json"], {})
        citations = [
            item
            for item in task_input.get("citations", [])
            if isinstance(item, dict)
            and str(item.get("source_id", "")).strip()
            and str(item.get("citation", "")).strip()
        ]
        steps = self._all(
            "SELECT * FROM education_p30_agent_steps WHERE task_id=? ORDER BY sequence",
            (task_id,),
        )
        try:
            with self.db.connection() as db:
                for step in steps:
                    if step["tool_key"]:
                        output = {
                            "tool": step["tool_key"],
                            "status": "completed",
                            "external_side_effect": False,
                        }
                    else:
                        output = {"operation": "validate_output", "status": "completed"}
                    finished = now()
                    db.execute(
                        """UPDATE education_p30_agent_steps
                        SET status='completed',input_json=?,output_json=?,
                        started_at=COALESCE(started_at,?),completed_at=? WHERE id=?""",
                        ("{}", encode_json(output), timestamp, finished, step["id"]),
                    )
                for evidence in citations:
                    db.execute(
                        """INSERT INTO education_p30_agent_evidence
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                        (
                            ident("agentevidence"),
                            task_id,
                            str(evidence.get("source_type", "reference")),
                            str(evidence["source_id"]),
                            str(evidence["citation"]),
                            str(evidence.get("claim", "")),
                            float(evidence.get("confidence", 0.5)),
                            str(evidence.get("verification_state", "unverified")),
                            now(),
                        ),
                    )
            output = self._agent_output(str(task["agent_key"]), task_input, citations)
            valid = all(key in output for key in ("summary", "artifacts", "citations", "limitations"))
            evidence_required = task["agent_key"] in {
                "research_assistant",
                "lecture_production",
                "scientific_verification",
            }
            state = "completed" if valid and (citations or not evidence_required) else "partially_completed"
            validation = {
                "schema_valid": valid,
                "evidence_required": evidence_required,
                "evidence_count": len(citations),
                "official_side_effect": False,
            }
            elapsed = time.perf_counter() - started
            with self.db.connection() as db:
                db.execute(
                    """UPDATE education_p30_agent_tasks SET state=?,output_json=?,
                    validation_json=?,resource_seconds=?,updated_at=? WHERE id=?""",
                    (state, encode_json(output), encode_json(validation), elapsed, now(), task_id),
                )
        except Exception as exc:
            with self.db.connection() as db:
                db.execute(
                    """UPDATE education_p30_agent_tasks
                    SET state='failed',error=?,updated_at=? WHERE id=?""",
                    (str(exc)[:2000], now(), task_id),
                )
            raise
        self._audit(
            actor,
            institution_id,
            "agent_task_executed",
            "agent_task",
            task_id,
            {"state": state, "evidence_count": len(citations)},
        )
        return self._tenant_row(
            "education_p30_agent_tasks",
            task_id,
            institution_id,
        )

    def cancel_agent_task(
        self,
        actor: str,
        task_id: str,
    ) -> dict[str, Any]:
        task = self._tenant_row("education_p30_agent_tasks", task_id)
        institution_id = str(task["institution_id"])
        self._require(actor, institution_id, "member")
        if actor != task["requested_by"] and not self._roles(actor, institution_id).intersection(
            {"platform_administrator", "institution_administrator"}
        ):
            raise Denied("Agent cancellation access denied.")
        if task["state"] in {"completed", "cancelled"}:
            raise Conflict("Completed or cancelled task cannot be cancelled again.")
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_agent_tasks
                SET cancel_requested=1,state='cancelled',updated_at=? WHERE id=?""",
                (now(), task_id),
            )
        return self._tenant_row(
            "education_p30_agent_tasks",
            task_id,
            institution_id,
        )

    def create_multi_agent_workflow(
        self,
        actor: str,
        institution_id: str,
        *,
        workflow: str,
        task_input: dict[str, Any],
        idempotency_prefix: str,
    ) -> list[dict[str, Any]]:
        workflows = {
            "research_to_lecture": [
                "research_assistant",
                "scientific_verification",
                "teacher_assistant",
                "lecture_production",
            ],
            "assessment_to_learning_plan": [
                "student_tutor",
                "teacher_assistant",
            ],
            "education_content_package": [
                "research_assistant",
                "scientific_verification",
                "lecture_production",
                "examination_authoring",
            ],
        }
        chain = workflows.get(normalized_key(workflow))
        if not chain:
            raise EducationError("Unsupported multi-agent workflow.")
        if len(chain) > MAX_AGENT_DEPTH:
            raise Denied("Workflow exceeds the maximum delegation depth.")
        tasks = []
        parent = ""
        for index, agent_key in enumerate(chain):
            task = self.create_agent_task(
                actor,
                institution_id,
                agent_key=agent_key,
                task_input={
                    **task_input,
                    "workflow": workflow,
                    "workflow_step": index + 1,
                },
                parent_task_id=parent,
                idempotency_key=f"{idempotency_prefix}-{index + 1}-{agent_key}",
            )
            tasks.append(task)
            parent = str(task["id"])
        return tasks
