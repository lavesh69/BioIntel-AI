from __future__ import annotations

from biointel.runtime_paths import runtime_reports_directory

import hashlib
import html
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from .constants import SYNTHETIC_NOTICE
from .models import PlatformValidationError, canonical_json, new_id, require_text, utc_now
from .provenance import environment_manifest
from .storage import DiscoveryPlatformStore

REVIEW_NOTICE = (
    "DRAFT SCIENTIFIC REPORT - GENERATED CONTENT IS EDITABLE AND REQUIRES RESEARCHER REVIEW"
)
REPORT_SECTIONS = (
    "Project summary",
    "Research question",
    "Hypothesis",
    "Dataset description",
    "Sample description",
    "Methods",
    "Parameters",
    "QC",
    "Results",
    "Figures",
    "Tables",
    "Candidate findings",
    "Recommendations",
    "Evidence",
    "Validation",
    "Limitations",
    "Reproducibility statement",
    "Software versions",
    "Database versions",
    "References",
    "Supplementary files",
)
EXPORT_FORMATS = ("pdf", "docx", "html", "xlsx", "csv", "json", "reproducibility_zip")


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _excel_safe(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, str):
        value = value[:32_000]
        if value.startswith(("=", "+", "-", "@")):
            return "'" + value
    return value


def _records_frame(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame([{key: _excel_safe(value) for key, value in row.items()} for row in records])
    return frame.iloc[:1_000_000, :200]


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")[:100] or "report"


class ScientificReportBuilder:
    def __init__(
        self,
        store: DiscoveryPlatformStore,
        *,
        actor: str = "local_user",
        role: str = "Administrator",
    ):
        self.store = store
        self.actor = actor
        self.role = role

    def collect_project(self, project_id: str) -> dict[str, Any]:
        project = self.store.row("projects", "project_id", project_id)
        if project is None:
            raise KeyError(project_id)
        direct_tables = (
            "datasets", "runs", "candidates", "recommendations", "evidence",
            "hypotheses", "experiments", "validation_results", "models",
            "notebooks", "reports", "comments", "review_actions", "artifacts",
        )
        records = {
            table: self.store.rows(
                table,
                filters={"project_id": project_id},
                order_by=(
                    "created_at_utc"
                    if table not in {"datasets", "runs"}
                    else ("imported_at_utc" if table == "datasets" else "started_at_utc")
                ),
                limit=5000,
            )
            for table in direct_tables
        }
        with self.store.connect(read_only=True) as connection:
            sample_rows = connection.execute(
                """
                SELECT samples.* FROM samples
                JOIN datasets ON datasets.dataset_id=samples.dataset_id
                WHERE datasets.project_id=? ORDER BY samples.created_at_utc
                LIMIT 50000
                """,
                (project_id,),
            ).fetchall()
            run_step_rows = connection.execute(
                """
                SELECT run_steps.* FROM run_steps
                JOIN runs ON runs.run_id=run_steps.run_id
                WHERE runs.project_id=? ORDER BY run_steps.started_at_utc
                LIMIT 50000
                """,
                (project_id,),
            ).fetchall()
        records["samples"] = [dict(row) for row in sample_rows]
        records["run_steps"] = [dict(row) for row in run_step_rows]
        records["audit_events"] = self.store.rows(
            "audit_events",
            filters={"project_id": project_id},
            order_by="occurred_at_utc",
            descending=False,
            limit=5000,
        )
        counts = {name: len(rows) for name, rows in records.items()}
        environment = environment_manifest()
        return {
            "schema": "biointel.scientific-report.v1",
            "generated_at_utc": utc_now(),
            "review_notice": REVIEW_NOTICE,
            "synthetic_notice": SYNTHETIC_NOTICE if project["is_synthetic"] else "",
            "project": project,
            "counts": counts,
            "records": records,
            "integrity": {
                "database": self.store.integrity(),
                "audit": self.store.verify_audit_chain(),
            },
            "environment": environment,
        }

    def _sections(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        project = snapshot["project"]
        records = snapshot["records"]
        return {
            "Project summary": {
                "title": project["title"],
                "stage": project["current_stage"],
                "owner": project["owner"],
                "organism": project["organism"],
                "disease_context": project["disease_context"],
                "data_origin": project["data_origin"],
            },
            "Research question": project["research_question"],
            "Hypothesis": records["hypotheses"],
            "Dataset description": records["datasets"],
            "Sample description": {
                "sample_count": len(records["samples"]),
                "samples": records["samples"],
            },
            "Methods": [
                {
                    "run_id": row["run_id"],
                    "module_id": row["module_id"],
                    "tool": row["tool"],
                    "tool_version": row["tool_version"],
                    "status": row["status"],
                }
                for row in records["runs"]
            ],
            "Parameters": [
                {"run_id": row["run_id"], "parameters": row.get("parameters", {})}
                for row in records["runs"]
            ],
            "QC": {
                "dataset_qc": [
                    {"dataset_id": row["dataset_id"], "qc_status": row["qc_status"]}
                    for row in records["datasets"]
                ],
                "sample_qc": [
                    {"sample_id": row["sample_id"], "qc_status": row["qc_status"]}
                    for row in records["samples"]
                ],
            },
            "Results": records["artifacts"],
            "Figures": [
                row for row in records["artifacts"]
                if str(row.get("media_type", "")).startswith("image/")
            ],
            "Tables": snapshot["counts"],
            "Candidate findings": records["candidates"],
            "Recommendations": records["recommendations"],
            "Evidence": records["evidence"],
            "Validation": {
                "experiments": records["experiments"],
                "validation_results": records["validation_results"],
            },
            "Limitations": {
                "statement": (
                    "Interpretation is restricted to supplied data, recorded methods, and "
                    "the explicit validation state of each result."
                ),
                "research_only": True,
            },
            "Reproducibility statement": {
                "database_integrity": snapshot["integrity"]["database"],
                "audit_integrity": snapshot["integrity"]["audit"],
                "artifact_hashes_recorded": all(
                    bool(row.get("sha256")) for row in records["artifacts"]
                ),
            },
            "Software versions": snapshot["environment"].get("packages", {}),
            "Database versions": [
                {
                    "dataset_id": row["dataset_id"],
                    "reference_build": row["reference_build"],
                    "annotation_release": row["annotation_release"],
                    "dataset_version": row["dataset_version"],
                }
                for row in records["datasets"]
            ],
            "References": [
                {
                    "evidence_id": row["evidence_id"],
                    "title": row["title"],
                    "pmid": row["pmid"],
                    "doi": row["doi"],
                    "verification_state": row["verification_state"],
                }
                for row in records["evidence"]
            ],
            "Supplementary files": records["artifacts"],
        }

    def create_report(
        self,
        project_id: str,
        *,
        title: str,
        selected_sections: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        snapshot = self.collect_project(project_id)
        sections = self._sections(snapshot)
        selected = tuple(selected_sections or REPORT_SECTIONS)
        unsupported = [name for name in selected if name not in REPORT_SECTIONS]
        if unsupported:
            raise PlatformValidationError(
                "Unsupported report sections: " + ", ".join(unsupported)
            )
        report_id = new_id("REPORT")
        now = utc_now()
        payload = {
            "schema": snapshot["schema"],
            "report_id": report_id,
            "title": require_text(title, "report title", 500),
            "project_id": project_id,
            "generated_at_utc": now,
            "review_notice": REVIEW_NOTICE,
            "synthetic_notice": snapshot["synthetic_notice"],
            "sections": {name: sections[name] for name in selected},
            "integrity": snapshot["integrity"],
            "environment": snapshot["environment"],
        }
        self.store.insert(
            "reports",
            {
                "report_id": report_id,
                "project_id": project_id,
                "title": payload["title"],
                "sections_json": payload,
                "review_required": 1,
                "status": "Draft",
                "artifact_ids_json": [],
                "created_by": self.actor,
                "created_at_utc": now,
                "updated_at_utc": now,
            },
        )
        self.store.audit(
            "scientific_report_created", "report", report_id,
            project_id=project_id, actor=self.actor, role=self.role,
            detail={
                "sections": list(payload["sections"]),
                "review_required": True,
                "synthetic": bool(snapshot["synthetic_notice"]),
            },
        )
        return self.store.row("reports", "report_id", report_id) or {}

    def _payload(self, report_id: str) -> dict[str, Any]:
        report = self.store.row("reports", "report_id", report_id)
        if report is None:
            raise KeyError(report_id)
        payload = dict(report.get("sections") or {})
        if payload.get("report_id") != report_id:
            raise PlatformValidationError("Report payload is incomplete or inconsistent")
        return payload

    @staticmethod
    def _render_json(payload: Mapping[str, Any]) -> bytes:
        return json.dumps(_json_safe(payload), indent=2, sort_keys=True).encode("utf-8")

    @staticmethod
    def _render_csv(payload: Mapping[str, Any]) -> bytes:
        rows = [
            {"field": "report_id", "value": payload["report_id"]},
            {"field": "title", "value": payload["title"]},
            {"field": "project_id", "value": payload["project_id"]},
            {"field": "generated_at_utc", "value": payload["generated_at_utc"]},
            {"field": "review_notice", "value": payload["review_notice"]},
            {"field": "synthetic_notice", "value": payload.get("synthetic_notice", "")},
        ]
        for name, value in payload["sections"].items():
            rows.append(
                {
                    "field": "section:" + name,
                    "value": json.dumps(value, sort_keys=True, default=str),
                }
            )
        return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")

    @staticmethod
    def _render_html(payload: Mapping[str, Any]) -> bytes:
        synthetic = payload.get("synthetic_notice", "")
        banner = (
            '<div class="synthetic">' + html.escape(str(synthetic)) + "</div>"
            if synthetic else ""
        )
        section_html = []
        for name, value in payload["sections"].items():
            if isinstance(value, (dict, list)):
                body = "<pre>" + html.escape(
                    json.dumps(value, indent=2, sort_keys=True, default=str)
                ) + "</pre>"
            else:
                body = "<p>" + html.escape(str(value)) + "</p>"
            section_html.append(
                "<section><h2>" + html.escape(name) + "</h2>" + body + "</section>"
            )
        document = (
            '<!doctype html><html><head><meta charset="utf-8">'
            "<title>" + html.escape(str(payload["title"])) + "</title>"
            "<style>body{font-family:Arial,sans-serif;color:#17202a;max-width:1100px;"
            "margin:32px auto;padding:0 24px}h1{font-size:28px}h2{font-size:18px;"
            "border-bottom:1px solid #d5d8dc;padding-bottom:6px}pre{white-space:pre-wrap;"
            "word-break:break-word;background:#f5f7f9;padding:12px;border:1px solid #d5d8dc}"
            ".review{background:#fff4ce;border-left:4px solid #8a6d00;padding:12px}"
            ".synthetic{background:#ffe9e7;color:#8b1e1e;border:2px solid #b42318;"
            "padding:12px;font-weight:700;margin-bottom:16px}</style></head><body>"
            + banner
            + '<div class="review">'
            + html.escape(str(payload["review_notice"]))
            + "</div><h1>"
            + html.escape(str(payload["title"]))
            + "</h1><p>Project "
            + html.escape(str(payload["project_id"]))
            + "</p>"
            + "".join(section_html)
            + "</body></html>"
        )
        return document.encode("utf-8")

    @staticmethod
    def _render_xlsx(payload: Mapping[str, Any]) -> bytes:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            notice = pd.DataFrame(
                [
                    {"Notice": payload["review_notice"]},
                    {"Notice": payload.get("synthetic_notice", "")},
                ]
            )
            notice.to_excel(writer, sheet_name="Read me", index=False)
            section_index = []
            for offset, (name, value) in enumerate(payload["sections"].items(), 1):
                sheet = _slug(name)[:31] or f"Section {offset}"
                if isinstance(value, list) and all(isinstance(row, Mapping) for row in value):
                    frame = _records_frame(value)
                elif isinstance(value, Mapping):
                    frame = pd.DataFrame(
                        [
                            {
                                "field": key,
                                "value": _excel_safe(item),
                            }
                            for key, item in value.items()
                        ]
                    )
                else:
                    frame = pd.DataFrame([{"value": _excel_safe(value)}])
                frame.to_excel(writer, sheet_name=sheet, index=False)
                section_index.append({"section": name, "sheet": sheet, "rows": len(frame)})
            pd.DataFrame(section_index).to_excel(writer, sheet_name="Index", index=False)
            for worksheet in writer.book.worksheets:
                worksheet.freeze_panes = "A2"
                worksheet.auto_filter.ref = worksheet.dimensions
                for column in worksheet.columns:
                    width = min(
                        60,
                        max(
                            10,
                            max(
                                len(str(cell.value)) if cell.value is not None else 0
                                for cell in list(column)[:200]
                            )
                            + 2,
                        ),
                    )
                    worksheet.column_dimensions[column[0].column_letter].width = width
        return buffer.getvalue()

    @staticmethod
    def _render_docx(payload: Mapping[str, Any]) -> bytes:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt, RGBColor

        document = Document()
        section = document.sections[0]
        section.top_margin = Inches(0.65)
        section.bottom_margin = Inches(0.65)
        title = document.add_heading(str(payload["title"]), 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        review = document.add_paragraph(str(payload["review_notice"]))
        review.runs[0].bold = True
        review.runs[0].font.color.rgb = RGBColor(138, 109, 0)
        if payload.get("synthetic_notice"):
            synthetic = document.add_paragraph(str(payload["synthetic_notice"]))
            synthetic.runs[0].bold = True
            synthetic.runs[0].font.color.rgb = RGBColor(180, 35, 24)
        document.add_paragraph("Project " + str(payload["project_id"]))
        for name, value in payload["sections"].items():
            document.add_heading(name, level=1)
            content = (
                json.dumps(value, indent=2, sort_keys=True, default=str)
                if isinstance(value, (dict, list))
                else str(value)
            )
            paragraph = document.add_paragraph(content[:200_000])
            paragraph.style.font.name = "Aptos"
            paragraph.style.font.size = Pt(9)
        buffer = io.BytesIO()
        document.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def _render_pdf(payload: Mapping[str, Any]) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=str(payload["title"]),
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph(html.escape(str(payload["title"])), styles["Title"]),
            Spacer(1, 8),
            Paragraph(html.escape(str(payload["review_notice"])), styles["Heading3"]),
        ]
        if payload.get("synthetic_notice"):
            story.extend(
                [
                    Spacer(1, 6),
                    Paragraph(
                        '<font color="#b42318"><b>'
                        + html.escape(str(payload["synthetic_notice"]))
                        + "</b></font>",
                        styles["Heading3"],
                    ),
                ]
            )
        story.extend(
            [
                Spacer(1, 8),
                Paragraph(
                    "Project " + html.escape(str(payload["project_id"])),
                    styles["Normal"],
                ),
            ]
        )
        for name, value in payload["sections"].items():
            story.extend([Spacer(1, 10), Paragraph(html.escape(name), styles["Heading2"])])
            content = (
                json.dumps(value, indent=2, sort_keys=True, default=str)
                if isinstance(value, (dict, list))
                else str(value)
            )
            for chunk_start in range(0, min(len(content), 300_000), 4000):
                chunk = content[chunk_start : chunk_start + 4000]
                story.append(
                    Paragraph(
                        html.escape(chunk).replace(chr(10), "<br/>"),
                        styles["Code"],
                    )
                )

        synthetic_notice = str(payload.get("synthetic_notice", ""))

        def decorate(canvas: Any, doc: Any) -> None:
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#5f6b73"))
            canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
            if synthetic_notice:
                canvas.setFillColor(colors.Color(0.7, 0.1, 0.1, alpha=0.16))
                canvas.setFont("Helvetica-Bold", 26)
                canvas.translate(A4[0] / 2, A4[1] / 2)
                canvas.rotate(35)
                canvas.drawCentredString(0, 0, "SYNTHETIC DEMO DATA")
            canvas.restoreState()

        document.build(story, onFirstPage=decorate, onLaterPages=decorate)
        return buffer.getvalue()

    def _render_reproducibility_zip(self, payload: Mapping[str, Any]) -> bytes:
        files = {
            "report/report.json": self._render_json(payload),
            "report/report.html": self._render_html(payload),
            "report/report.csv": self._render_csv(payload),
            "environment.json": json.dumps(
                payload.get("environment", {}), indent=2, sort_keys=True, default=str
            ).encode("utf-8"),
            "integrity.json": json.dumps(
                payload.get("integrity", {}), indent=2, sort_keys=True, default=str
            ).encode("utf-8"),
        }
        manifest = {
            "schema": "biointel.report-reproducibility.v1",
            "report_id": payload["report_id"],
            "project_id": payload["project_id"],
            "generated_at_utc": utc_now(),
            "files": {
                name: {
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
                for name, content in sorted(files.items())
            },
        }
        files["manifest.json"] = json.dumps(
            manifest, indent=2, sort_keys=True
        ).encode("utf-8")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(files.items()):
                archive.writestr(name, content)
        return buffer.getvalue()

    def render(self, report_id: str, output_format: str) -> tuple[bytes, str, str]:
        selected = str(output_format).lower()
        if selected not in EXPORT_FORMATS:
            raise PlatformValidationError("Unsupported report export format")
        payload = self._payload(report_id)
        renderers = {
            "pdf": self._render_pdf,
            "docx": self._render_docx,
            "html": self._render_html,
            "xlsx": self._render_xlsx,
            "csv": self._render_csv,
            "json": self._render_json,
            "reproducibility_zip": self._render_reproducibility_zip,
        }
        content = renderers[selected](payload)
        extension = "zip" if selected == "reproducibility_zip" else selected
        media_types = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "html": "text/html",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "json": "application/json",
            "reproducibility_zip": "application/zip",
        }
        filename = _slug(str(payload["title"])) + "." + extension
        return content, filename, media_types[selected]

    def export(
        self,
        report_id: str,
        output_format: str,
        *,
        destination: str | Path | None = None,
    ) -> dict[str, Any]:
        payload = self._payload(report_id)
        content, filename, media_type = self.render(report_id, output_format)
        report_folder = (
            self.store.artifact_runtime_reports_directory(root) / Path(report_id).name
        ).resolve()
        if not report_folder.is_relative_to(self.store.artifact_root):
            raise PlatformValidationError("Report path escaped the artifact root")
        report_folder.mkdir(parents=True, exist_ok=True)
        target = Path(destination).resolve() if destination else report_folder / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        artifact_id = new_id("ART")
        self.store.insert(
            "artifacts",
            {
                "artifact_id": artifact_id,
                "project_id": payload["project_id"],
                "run_id": None,
                "artifact_type": "scientific_report",
                "name": target.name,
                "path": str(target),
                "sha256": digest,
                "size_bytes": len(content),
                "media_type": media_type,
                "provenance_json": {
                    "origin": "synthetic_demo_output"
                    if payload.get("synthetic_notice")
                    else "user_entered_interpretation",
                    "report_id": report_id,
                    "review_required": True,
                },
                "created_at_utc": utc_now(),
            },
        )
        report = self.store.row("reports", "report_id", report_id) or {}
        artifact_ids = list(report.get("artifact_ids", []))
        artifact_ids.append(artifact_id)
        self.store.update(
            "reports", "report_id", report_id,
            {"artifact_ids_json": list(dict.fromkeys(artifact_ids)), "updated_at_utc": utc_now()},
        )
        self.store.audit(
            "scientific_report_exported", "report", report_id,
            project_id=payload["project_id"], actor=self.actor, role=self.role,
            detail={
                "format": output_format,
                "artifact_id": artifact_id,
                "sha256": digest,
                "review_required": True,
            },
        )
        return {
            "report_id": report_id,
            "artifact_id": artifact_id,
            "path": str(target),
            "filename": target.name,
            "media_type": media_type,
            "sha256": digest,
            "size_bytes": len(content),
            "review_required": True,
        }


__all__ = [
    "EXPORT_FORMATS",
    "REPORT_SECTIONS",
    "REVIEW_NOTICE",
    "ScientificReportBuilder",
]
