from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from ..platform import Conflict, Denied, EducationError, Missing, ident, now
from .base import (
    STAFF_ROLES,
    STUDENT_ROLES,
    Phase30Base,
    decode_json,
    encode_json,
    normalized_key,
    sha256_bytes,
)

LAB_COLLECTION = [
    ("micropipetting", "laboratory_skills", "Micropipetting", "calculation_simulation"),
    ("solution_preparation", "chemistry", "Solution preparation", "calculation_simulation"),
    ("dilution_calculations", "chemistry", "Dilution calculations", "calculation_simulation"),
    ("buffer_preparation", "biochemistry", "Buffer preparation", "calculation_simulation"),
    ("ph_adjustment", "chemistry", "pH adjustment", "calculation_simulation"),
    ("spectrophotometry", "biochemistry", "Spectrophotometry", "calculation_simulation"),
    ("microscopy", "cell_biology", "Microscopy", "structured_guided_workflow"),
    ("gram_staining", "microbiology", "Gram staining", "structured_guided_workflow"),
    ("cell_counting", "cell_biology", "Cell counting", "calculation_simulation"),
    ("dna_extraction", "molecular_biology", "DNA extraction", "structured_guided_workflow"),
    ("rna_extraction", "molecular_biology", "RNA extraction", "structured_guided_workflow"),
    ("pcr", "molecular_biology", "PCR", "structured_guided_workflow"),
    ("qpcr_interpretation", "molecular_biology", "qPCR interpretation", "calculation_simulation"),
    ("agarose_gel_electrophoresis", "molecular_biology", "Agarose gel electrophoresis", "structured_guided_workflow"),
    ("restriction_digestion", "molecular_biology", "Restriction digestion", "calculation_simulation"),
    ("bacterial_culture_basics", "microbiology", "Bacterial culture basics", "structured_guided_workflow"),
    ("enzyme_kinetics", "biochemistry", "Enzyme kinetics", "calculation_simulation"),
    ("protein_quantification", "biochemistry", "Protein quantification", "calculation_simulation"),
    ("elisa_interpretation", "immunology", "ELISA interpretation", "calculation_simulation"),
    ("chromatography_fundamentals", "analytical_biology", "Chromatography fundamentals", "structured_guided_workflow"),
    ("dna_sequencing_workflow", "genomics", "DNA sequencing workflow", "structured_guided_workflow"),
    ("sequence_quality_control", "bioinformatics", "Sequence quality control", "calculation_simulation"),
    ("bioinformatics_practical", "bioinformatics", "Bioinformatics practical exercises", "structured_guided_workflow"),
]

UNIT_FACTORS = {
    "l": 1.0,
    "ml": 1e-3,
    "ul": 1e-6,
    "mol/l": 1.0,
    "mmol/l": 1e-3,
    "umol/l": 1e-6,
    "g": 1.0,
    "mg": 1e-3,
    "ug": 1e-6,
}


def default_protocol(key: str) -> list[dict[str, Any]]:
    return [
        {
            "key": "review_protocol",
            "action": "review",
            "safety_critical": False,
            "instruction": f"Review the versioned {key.replace('_', ' ')} protocol.",
        },
        {
            "key": "safety_check",
            "action": "confirm_safety",
            "safety_critical": True,
            "instruction": "Confirm PPE, hazards and waste handling.",
        },
        {
            "key": "prepare",
            "action": "prepare",
            "safety_critical": False,
            "instruction": "Prepare apparatus and reagents in the specified order.",
        },
        {
            "key": "perform",
            "action": "perform",
            "safety_critical": False,
            "instruction": "Perform the governed practical or simulation step.",
        },
        {
            "key": "measure",
            "action": "measure",
            "safety_critical": False,
            "instruction": "Record measurement values and units.",
        },
        {
            "key": "interpret",
            "action": "interpret",
            "safety_critical": False,
            "instruction": "Interpret results, uncertainty and limitations.",
        },
        {
            "key": "cleanup",
            "action": "cleanup",
            "safety_critical": True,
            "instruction": "Complete safe cleanup and disposal.",
        },
    ]


class LabMixin(Phase30Base):
    def seed_virtual_labs(self) -> dict[str, int]:
        timestamp = now()
        with self.db.connection() as db:
            for key, discipline, title, capability in LAB_COLLECTION:
                experiment_id = f"lab_{key}"
                db.execute(
                    """INSERT INTO education_p30_lab_experiments
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(institution_id,key) DO UPDATE SET
                    discipline=excluded.discipline,title=excluded.title,
                    capability_class=excluded.capability_class,
                    learning_outcomes_json=excluded.learning_outcomes_json,
                    theory=excluded.theory,safety_json=excluded.safety_json,
                    hazard_json=excluded.hazard_json,references_json=excluded.references_json,
                    state='active',updated_at=excluded.updated_at""",
                    (
                        experiment_id,
                        "",
                        key,
                        discipline,
                        title,
                        capability,
                        encode_json(
                            [
                                f"Explain the principles of {title}.",
                                "Execute or describe the protocol safely.",
                                "Record and interpret reproducible results.",
                            ]
                        ),
                        "[]",
                        f"Versioned learning theory for {title}.",
                        encode_json(["context-appropriate apparatus"]),
                        encode_json(["context-appropriate reagents"]),
                        encode_json(["PPE", "waste handling", "stop on unsafe action"]),
                        encode_json(["Training scenario hazards; follow institutional SOPs."]),
                        encode_json(
                            [
                                {
                                    "label": "Institution-approved practical manual required",
                                    "state": "local_reference_placeholder",
                                }
                            ]
                        ),
                        1,
                        "active",
                        "system",
                        timestamp,
                        timestamp,
                    ),
                )
                protocol = default_protocol(key)
                content = encode_json(
                    {
                        "protocol": protocol,
                        "capability_class": capability,
                        "accuracy_boundary": (
                            "Deterministic calculation simulation with configurable variation."
                            if capability == "calculation_simulation"
                            else "Guided practical workflow; not a physically accurate simulation."
                        ),
                    }
                )
                db.execute(
                    """INSERT INTO education_p30_lab_versions
                    VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(experiment_id,version) DO UPDATE SET
                    protocol_json=excluded.protocol_json,
                    calculation_schema_json=excluded.calculation_schema_json,
                    scenario_json=excluded.scenario_json,
                    content_sha256=excluded.content_sha256""",
                    (
                        f"labver_{key}_1",
                        experiment_id,
                        1,
                        encode_json(protocol),
                        encode_json(
                            {
                                "unit_conversion": True,
                                "dilution_c1v1_c2v2": key
                                in {"solution_preparation", "dilution_calculations"},
                                "random_variation": capability == "calculation_simulation",
                            }
                        ),
                        encode_json(
                            {
                                "configurable_error_introduction": True,
                                "invalid_action_detection": True,
                            }
                        ),
                        sha256_bytes(content.encode("utf-8")),
                        "system",
                        timestamp,
                    ),
                )
        return {
            "experiments": len(LAB_COLLECTION),
            "calculation_simulations": sum(
                item[3] == "calculation_simulation" for item in LAB_COLLECTION
            ),
            "guided_workflows": sum(
                item[3] == "structured_guided_workflow" for item in LAB_COLLECTION
            ),
        }

    def lab_catalog(
        self,
        actor: str,
        institution_id: str,
        *,
        discipline: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        self._require(actor, institution_id, "member")
        self.seed_virtual_labs()
        limit, offset = self.paginate(page, page_size)
        if discipline:
            return self._all(
                """SELECT * FROM education_p30_lab_experiments
                WHERE institution_id IN ('',?) AND discipline=? AND state='active'
                ORDER BY title LIMIT ? OFFSET ?""",
                (institution_id, normalized_key(discipline), limit, offset),
            )
        return self._all(
            """SELECT * FROM education_p30_lab_experiments
            WHERE institution_id IN ('',?) AND state='active'
            ORDER BY title LIMIT ? OFFSET ?""",
            (institution_id, limit, offset),
        )

    def start_lab_attempt(
        self,
        actor: str,
        institution_id: str,
        experiment_id: str,
        *,
        student_id: str = "",
        assigned_by: str = "",
        scenario_seed: int | None = None,
    ) -> dict[str, Any]:
        roles = self._require(actor, institution_id, "member")
        self.seed_virtual_labs()
        experiment = self._one(
            """SELECT * FROM education_p30_lab_experiments
            WHERE id=? AND institution_id IN ('',?) AND state='active'""",
            (experiment_id, institution_id),
        )
        if not experiment:
            raise Missing("Virtual Lab experiment not found.")
        target_student = student_id or actor
        if target_student != actor and not roles.intersection(STAFF_ROLES):
            raise Denied("Only staff may assign a lab attempt to another user.")
        student_roles = self._roles(target_student, institution_id)
        if not student_roles.intersection(STUDENT_ROLES) and not roles.intersection(STAFF_ROLES):
            raise Denied("A student membership is required for this attempt.")
        attempt_id = ident("labattempt")
        seed = int(scenario_seed if scenario_seed is not None else int(hashlib.sha256(attempt_id.encode()).hexdigest()[:8], 16))
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_lab_attempts
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    attempt_id,
                    institution_id,
                    experiment_id,
                    int(experiment["current_version"]),
                    target_student,
                    assigned_by or (actor if actor != target_student else ""),
                    seed,
                    "in_progress",
                    0,
                    0,
                    0,
                    "{}",
                    "{}",
                    "",
                    None,
                    timestamp,
                    timestamp,
                ),
            )
        self._audit(
            actor,
            institution_id,
            "lab_attempt_started",
            "lab_attempt",
            attempt_id,
            {"experiment_id": experiment_id, "student_id": target_student},
        )
        return self._tenant_row(
            "education_p30_lab_attempts",
            attempt_id,
            institution_id,
        )

    @staticmethod
    def convert_unit(value: float, source_unit: str, target_unit: str) -> float:
        source = source_unit.strip().casefold()
        target = target_unit.strip().casefold()
        if source not in UNIT_FACTORS or target not in UNIT_FACTORS:
            raise EducationError("Unsupported laboratory unit.")
        source_dimension = "volume" if source.endswith("l") and "/" not in source else (
            "concentration" if "/l" in source else "mass"
        )
        target_dimension = "volume" if target.endswith("l") and "/" not in target else (
            "concentration" if "/l" in target else "mass"
        )
        if source_dimension != target_dimension:
            raise EducationError("Incompatible laboratory unit conversion.")
        converted = float(value) * UNIT_FACTORS[source] / UNIT_FACTORS[target]
        # Unit factors are decimal quantities; remove binary floating-point
        # residue so deterministic calculations and exports remain stable.
        return round(converted, 12)

    @staticmethod
    def dilution_result(c1: float, v1: float, c2: float) -> float:
        if c1 <= 0 or v1 <= 0 or c2 <= 0:
            raise EducationError("Dilution inputs must be greater than zero.")
        return float(c1) * float(v1) / float(c2)

    def record_lab_step(
        self,
        actor: str,
        attempt_id: str,
        *,
        action: str,
        values: dict[str, Any] | None = None,
        safety_acknowledged: bool = False,
        introduce_error: bool = False,
    ) -> dict[str, Any]:
        attempt = self._tenant_row("education_p30_lab_attempts", attempt_id)
        institution_id = str(attempt["institution_id"])
        roles = self._require(actor, institution_id, "member")
        if actor != attempt["student_id"] and not roles.intersection(STAFF_ROLES):
            raise Denied("Lab attempt access denied.")
        if attempt["state"] != "in_progress":
            raise Conflict("Lab attempt is not active.")
        version = self._one(
            """SELECT * FROM education_p30_lab_versions
            WHERE experiment_id=? AND version=?""",
            (attempt["experiment_id"], attempt["experiment_version"]),
        )
        if not version:
            raise Missing("Versioned lab protocol not found.")
        protocol = decode_json(version["protocol_json"], [])
        sequence = int(attempt["current_step"]) + 1
        if sequence > len(protocol):
            raise Conflict("All laboratory steps are already complete.")
        expected = protocol[sequence - 1]
        normalized_action = normalized_key(action)
        valid = normalized_action == expected["action"]
        safety_violation = bool(expected["safety_critical"] and not safety_acknowledged)
        feedback = ""
        if not valid:
            feedback = f"Expected action: {expected['action']}."
        elif safety_violation:
            feedback = "Safety acknowledgement is required before this step."
            valid = False
        payload = dict(values or {})
        output: dict[str, Any] = {}
        if valid and expected["key"] == "measure":
            numeric = float(payload.get("value", 0))
            variation = 0.0
            experiment = self._one(
                "SELECT capability_class FROM education_p30_lab_experiments WHERE id=?",
                (attempt["experiment_id"],),
            )
            if experiment and experiment["capability_class"] == "calculation_simulation":
                generator = random.Random(int(attempt["scenario_seed"]) + sequence)
                variation = generator.uniform(-0.02, 0.02)
                if introduce_error:
                    variation += generator.choice([-0.15, 0.15])
                numeric *= 1 + variation
            output = {
                "observed_value": round(numeric, 8),
                "unit": str(payload.get("unit", "")),
                "variation_fraction": round(variation, 6),
                "introduced_error": bool(introduce_error),
            }
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_lab_steps
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ident("labstep"),
                    attempt_id,
                    sequence,
                    expected["key"],
                    normalized_action,
                    encode_json(payload),
                    encode_json(output),
                    int(valid),
                    int(safety_violation),
                    feedback,
                    timestamp,
                ),
            )
            if valid:
                measurements = decode_json(attempt["measurements_json"], {})
                if output:
                    measurements[expected["key"]] = output
                db.execute(
                    """UPDATE education_p30_lab_attempts SET current_step=?,
                    measurements_json=?,updated_at=? WHERE id=?""",
                    (sequence, encode_json(measurements), timestamp, attempt_id),
                )
            else:
                db.execute(
                    """UPDATE education_p30_lab_attempts SET
                    invalid_actions=invalid_actions+1,
                    safety_violations=safety_violations+?,
                    updated_at=? WHERE id=?""",
                    (int(safety_violation), timestamp, attempt_id),
                )
        return self._one(
            """SELECT * FROM education_p30_lab_steps
            WHERE attempt_id=? AND sequence=?""",
            (attempt_id, sequence),
        ) or {}

    def add_lab_notebook_entry(
        self,
        actor: str,
        attempt_id: str,
        *,
        entry_type: str,
        body: str = "",
        data: dict[str, Any] | None = None,
        attachment_path: str = "",
        protocol_deviation: bool = False,
    ) -> dict[str, Any]:
        attempt = self._tenant_row("education_p30_lab_attempts", attempt_id)
        institution_id = str(attempt["institution_id"])
        roles = self._require(actor, institution_id, "member")
        if actor != attempt["student_id"] and not roles.intersection(STAFF_ROLES):
            raise Denied("Lab notebook access denied.")
        if attempt["state"] not in {"in_progress", "submitted"}:
            raise Conflict("Lab notebook is not editable.")
        managed_path = ""
        attachment_sha = ""
        if attachment_path:
            suffix = Path(attachment_path).suffix.casefold()
            destination = self._safe_storage_path(
                institution_id,
                "labs",
                attempt_id,
                ident("attachment") + suffix,
            )
            copied = self._copy_managed_file(
                attachment_path,
                destination,
                maximum_bytes=25 * 1024 * 1024,
                allowed_suffixes={".png", ".jpg", ".jpeg", ".pdf", ".csv", ".txt"},
            )
            managed_path = str(copied["path"])
            attachment_sha = str(copied["sha256"])
        previous = self._one(
            "SELECT MAX(version) version FROM education_p30_lab_notebook_entries WHERE attempt_id=?",
            (attempt_id,),
        )
        version = int((previous or {}).get("version") or 0) + 1
        entry_id = ident("labnote")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_lab_notebook_entries
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entry_id,
                    attempt_id,
                    actor,
                    normalized_key(entry_type),
                    str(body),
                    encode_json(data or {}),
                    managed_path,
                    attachment_sha,
                    version,
                    int(protocol_deviation),
                    "",
                    now(),
                ),
            )
        return self._one(
            "SELECT * FROM education_p30_lab_notebook_entries WHERE id=?",
            (entry_id,),
        ) or {}

    def submit_lab_attempt(
        self,
        actor: str,
        attempt_id: str,
        *,
        results: dict[str, Any],
        discussion: str,
        references: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        attempt = self._tenant_row("education_p30_lab_attempts", attempt_id)
        institution_id = str(attempt["institution_id"])
        if actor != attempt["student_id"]:
            raise Denied("Only the student may sign and submit the lab attempt.")
        self._require(actor, institution_id, "student")
        version = self._one(
            """SELECT protocol_json FROM education_p30_lab_versions
            WHERE experiment_id=? AND version=?""",
            (attempt["experiment_id"], attempt["experiment_version"]),
        )
        if not version:
            raise Missing("Lab protocol version not found.")
        protocol = decode_json(version["protocol_json"], [])
        if int(attempt["current_step"]) != len(protocol):
            raise Conflict("All valid protocol steps must be completed before submission.")
        notebook = self._all(
            """SELECT * FROM education_p30_lab_notebook_entries
            WHERE attempt_id=? ORDER BY version""",
            (attempt_id,),
        )
        if not notebook:
            raise Conflict("At least one lab notebook entry is required.")
        payload = {
            "attempt_id": attempt_id,
            "student_id": actor,
            "experiment_id": attempt["experiment_id"],
            "version": attempt["experiment_version"],
            "steps": self._all(
                "SELECT * FROM education_p30_lab_steps WHERE attempt_id=? ORDER BY sequence",
                (attempt_id,),
            ),
            "notebook": notebook,
            "results": results,
            "discussion": discussion,
            "references": references or [],
        }
        signature = self.platform._signature(encode_json(payload))
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_lab_attempts SET
                state='submitted',results_json=?,signed_submission_sha256=?,
                submitted_at=?,updated_at=? WHERE id=?""",
                (
                    encode_json(
                        {
                            "results": results,
                            "discussion": discussion,
                            "references": references or [],
                        }
                    ),
                    signature,
                    timestamp,
                    timestamp,
                    attempt_id,
                ),
            )
        self._audit(
            actor,
            institution_id,
            "lab_attempt_submitted",
            "lab_attempt",
            attempt_id,
            {"signature": signature},
        )
        return self._tenant_row(
            "education_p30_lab_attempts",
            attempt_id,
            institution_id,
        )

    def assess_lab_attempt(
        self,
        actor: str,
        attempt_id: str,
        *,
        procedural_score: float,
        calculation_score: float,
        safety_score: float,
        interpretation_score: float,
        rubric_score: float,
        viva: list[dict[str, Any]] | None = None,
        feedback: str = "",
        override_reason: str = "",
    ) -> dict[str, Any]:
        attempt = self._tenant_row("education_p30_lab_attempts", attempt_id)
        institution_id = str(attempt["institution_id"])
        self._require(actor, institution_id, "staff")
        if attempt["state"] != "submitted":
            raise Conflict("Only a submitted lab attempt may be assessed.")
        values = [
            float(procedural_score),
            float(calculation_score),
            float(safety_score),
            float(interpretation_score),
            float(rubric_score),
        ]
        if any(value < 0 or value > 100 for value in values):
            raise EducationError("Lab assessment scores must be between 0 and 100.")
        if int(attempt["safety_violations"]) and safety_score > 80 and not override_reason.strip():
            raise Conflict("A safety-score override reason is required.")
        total = round(
            values[0] * 0.25
            + values[1] * 0.20
            + values[2] * 0.25
            + values[3] * 0.20
            + values[4] * 0.10,
            2,
        )
        assessment_id = ident("labassessment")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_lab_assessments
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(attempt_id) DO UPDATE SET
                assessor_id=excluded.assessor_id,
                procedural_score=excluded.procedural_score,
                calculation_score=excluded.calculation_score,
                safety_score=excluded.safety_score,
                interpretation_score=excluded.interpretation_score,
                rubric_score=excluded.rubric_score,
                viva_json=excluded.viva_json,feedback=excluded.feedback,
                override_reason=excluded.override_reason,total_score=excluded.total_score,
                updated_at=excluded.updated_at""",
                (
                    assessment_id,
                    attempt_id,
                    institution_id,
                    actor,
                    values[0],
                    values[1],
                    values[2],
                    values[3],
                    values[4],
                    encode_json(viva or []),
                    feedback,
                    override_reason,
                    total,
                    "released",
                    timestamp,
                    timestamp,
                ),
            )
            db.execute(
                "UPDATE education_p30_lab_attempts SET state='assessed',updated_at=? WHERE id=?",
                (timestamp, attempt_id),
            )
        self._audit(
            actor,
            institution_id,
            "lab_attempt_assessed",
            "lab_attempt",
            attempt_id,
            {"total_score": total},
        )
        return self._one(
            "SELECT * FROM education_p30_lab_assessments WHERE attempt_id=?",
            (attempt_id,),
        ) or {}

    def replay_lab_attempt(
        self,
        actor: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        attempt = self._tenant_row("education_p30_lab_attempts", attempt_id)
        institution_id = str(attempt["institution_id"])
        roles = self._require(actor, institution_id, "member")
        if actor != attempt["student_id"] and not roles.intersection(STAFF_ROLES):
            raise Denied("Lab replay access denied.")
        return {
            "attempt": attempt,
            "steps": self._all(
                "SELECT * FROM education_p30_lab_steps WHERE attempt_id=? ORDER BY sequence",
                (attempt_id,),
            ),
            "notebook": self._all(
                """SELECT * FROM education_p30_lab_notebook_entries
                WHERE attempt_id=? ORDER BY version""",
                (attempt_id,),
            ),
            "assessment": self._one(
                "SELECT * FROM education_p30_lab_assessments WHERE attempt_id=?",
                (attempt_id,),
            ),
        }

    def export_lab_report(
        self,
        actor: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        replay = self.replay_lab_attempt(actor, attempt_id)
        attempt = replay["attempt"]
        institution_id = str(attempt["institution_id"])
        destination = self._safe_storage_path(
            institution_id,
            "labs",
            attempt_id,
            "lab-report.pdf",
        )
        pdf = canvas.Canvas(str(destination), pagesize=A4)
        width, height = A4
        y = height - 48
        pdf.setTitle(f"BioIntel Virtual Lab {attempt_id}")
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(48, y, "BioIntel Virtual Science Laboratory report")
        y -= 24
        pdf.setFont("Helvetica", 9)
        lines = [
            f"Attempt: {attempt_id}",
            f"Student: {attempt['student_id']}",
            f"Experiment: {attempt['experiment_id']} version {attempt['experiment_version']}",
            f"State: {attempt['state']}",
            f"Signed submission: {attempt['signed_submission_sha256'] or 'not submitted'}",
            f"Valid protocol progress: {attempt['current_step']}",
            f"Invalid actions: {attempt['invalid_actions']}",
            f"Safety violations: {attempt['safety_violations']}",
        ]
        for line in lines:
            pdf.drawString(48, y, line[:120])
            y -= 14
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(48, y, "Notebook entries")
        y -= 16
        pdf.setFont("Helvetica", 8)
        for entry in replay["notebook"]:
            text = f"v{entry['version']} {entry['entry_type']}: {entry['body']}"
            pdf.drawString(48, y, text[:140])
            y -= 13
            if y < 60:
                pdf.showPage()
                y = height - 48
                pdf.setFont("Helvetica", 8)
        if replay["assessment"]:
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(48, y, f"Assessment total: {replay['assessment']['total_score']:.2f}")
        pdf.save()
        return {
            "path": str(destination),
            "size_bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "format": "pdf",
        }
