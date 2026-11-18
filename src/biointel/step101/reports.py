from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from biointel.jobs.local_queue import LocalJobQueue
from biointel.reference_assets.manager import ReferenceAssetRegistry
from biointel.reports.workspace_report import build_workspace_report_data, build_workspace_report_html


@dataclass(frozen=True)
class ReportBundle:
    title: str
    generated_at_utc: str
    files: dict[str, bytes]
    manifest: dict[str, Any]

    def zip_bytes(self) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in self.files.items():
                archive.writestr(name, payload)
            archive.writestr("manifest.json", json.dumps(self.manifest, indent=2, sort_keys=True))
        return buffer.getvalue()


class UnifiedScientificReportBuilder:
    """Build a single evidence package in HTML, PDF, DOCX, XLSX, CSV and JSON."""

    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()

    def collect(self, *, title: str, notes: str = "", reviewer: str = "", sections: Iterable[str] | None = None) -> dict[str, Any]:
        selected = set(sections or {"workspace", "jobs", "references", "provenance", "limitations"})
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "title": title.strip() or "BioIntel AI Unified Scientific Report",
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "reviewer": reviewer.strip(),
            "notes": notes.strip(),
            "selected_sections": sorted(selected),
        }
        if "workspace" in selected:
            payload["workspace"] = build_workspace_report_data(self.root, payload["title"], notes)
        if "jobs" in selected:
            queue = LocalJobQueue(runtime_database_path(self.root, "jobs.sqlite3"))
            payload["jobs"] = {
                "summary": queue.orchestration_summary(),
                "recent": [job.__dict__ for job in queue.list(limit=100)],
                "workers": queue.workers(),
            }
        if "references" in selected:
            reference_root = Path(
                __import__("os").environ.get("BIOINTEL_REFERENCE_ASSETS_DIR", self.root / "data" / "reference_assets")
            )
            registry = ReferenceAssetRegistry(reference_root / "reference_assets.sqlite3")
            payload["references"] = registry.list_assets()
        if "provenance" in selected:
            version = (self.root / "VERSION").read_text(encoding="utf-8").strip() if (self.root / "VERSION").is_file() else "unknown"
            payload["provenance"] = {
                "biointel_version": version,
                "project_root": str(self.root),
                "configuration_hashes": self._configuration_hashes(),
            }
        if "limitations" in selected:
            payload["limitations"] = [
                "Computational output does not replace independent wet-lab or clinical validation.",
                "Reference database release, genome build and licence must be reviewed for each project.",
                "External tools and model weights are qualified only when their recorded hashes and versions match.",
            ]
        return payload

    def _configuration_hashes(self) -> list[dict[str, str]]:
        rows = []
        for path in sorted((self.root / "config").glob("*")):
            if path.is_file():
                rows.append({"path": path.relative_to(self.root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        return rows

    @staticmethod
    def _flatten_summary(data: dict[str, Any]) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                rows.append((key, "" if value is None else str(value)))
        return rows

    def _docx(self, data: dict[str, Any]) -> bytes:
        from docx import Document

        document = Document()
        document.add_heading(str(data["title"]), 0)
        document.add_paragraph(f"Generated: {data['generated_at_utc']}")
        if data.get("reviewer"):
            document.add_paragraph(f"Reviewer: {data['reviewer']}")
        if data.get("notes"):
            document.add_heading("Research notes", level=1)
            document.add_paragraph(str(data["notes"]))
        for section, value in data.items():
            if section in {"title", "generated_at_utc", "reviewer", "notes", "schema_version", "selected_sections"}:
                continue
            document.add_heading(section.replace("_", " ").title(), level=1)
            if isinstance(value, list):
                for item in value[:200]:
                    document.add_paragraph(json.dumps(item, default=str) if isinstance(item, dict) else str(item), style="List Bullet")
            else:
                document.add_paragraph(json.dumps(value, indent=2, default=str)[:100000])
        buffer = io.BytesIO()
        document.save(buffer)
        return buffer.getvalue()

    def _xlsx(self, data: dict[str, Any]) -> bytes:
        from openpyxl import Workbook
        from openpyxl.styles import Font

        workbook = Workbook()
        summary = workbook.active
        summary.title = "Summary"
        summary.append(["Field", "Value"])
        for cell in summary[1]:
            cell.font = Font(bold=True)
        for row in self._flatten_summary(data):
            summary.append(row)
        for section, value in data.items():
            if not isinstance(value, list) or not value:
                continue
            sheet = workbook.create_sheet(section[:31])
            if isinstance(value[0], dict):
                headers = sorted({key for item in value if isinstance(item, dict) for key in item})
                sheet.append(headers)
                for item in value[:5000]:
                    sheet.append([json.dumps(item.get(key), default=str) if isinstance(item.get(key), (dict, list)) else item.get(key) for key in headers])
            else:
                sheet.append([section])
                for item in value[:5000]:
                    sheet.append([str(item)])
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def _pdf(self, data: dict[str, Any]) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
        styles = getSampleStyleSheet()
        story = [Paragraph(str(data["title"]), styles["Title"]), Spacer(1, 8), Paragraph(f"Generated {data['generated_at_utc']}", styles["Normal"])]
        for section, value in data.items():
            if section in {"title", "generated_at_utc", "schema_version", "selected_sections"}:
                continue
            story.extend([Spacer(1, 10), Paragraph(section.replace("_", " ").title(), styles["Heading2"])])
            text = json.dumps(value, indent=2, default=str) if not isinstance(value, str) else value
            for chunk_start in range(0, min(len(text), 100000), 3500):
                safe = text[chunk_start : chunk_start + 3500].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
                story.append(Paragraph(safe, styles["Code"]))
        doc.build(story)
        return buffer.getvalue()

    def _csv_files(self, data: dict[str, Any]) -> dict[str, bytes]:
        outputs: dict[str, bytes] = {}
        for section, value in data.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                headers = sorted({key for item in value if isinstance(item, dict) for key in item})
                text = io.StringIO()
                writer = csv.DictWriter(text, fieldnames=headers, extrasaction="ignore")
                writer.writeheader()
                for item in value:
                    writer.writerow({key: json.dumps(item.get(key), default=str) if isinstance(item.get(key), (dict, list)) else item.get(key) for key in headers})
                outputs[f"tables/{section}.csv"] = text.getvalue().encode("utf-8-sig")
        jobs = data.get("jobs")
        if isinstance(jobs, dict) and isinstance(jobs.get("recent"), list):
            nested = {"jobs_recent": jobs["recent"], "workers": jobs.get("workers", [])}
            outputs.update(self._csv_files(nested))
        return outputs

    def build(self, *, title: str, notes: str = "", reviewer: str = "", sections: Iterable[str] | None = None) -> ReportBundle:
        data = self.collect(title=title, notes=notes, reviewer=reviewer, sections=sections)
        workspace = data.get("workspace")
        html = build_workspace_report_html(workspace) if isinstance(workspace, dict) else f"<html><body><pre>{json.dumps(data, indent=2)}</pre></body></html>"
        files: dict[str, bytes] = {
            "report.html": html.encode("utf-8"),
            "report.json": json.dumps(data, indent=2, sort_keys=True, default=str).encode("utf-8"),
            "report.docx": self._docx(data),
            "report.xlsx": self._xlsx(data),
            "report.pdf": self._pdf(data),
        }
        files.update(self._csv_files(data))
        file_manifest = [
            {"path": name, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
            for name, payload in sorted(files.items())
        ]
        manifest = {
            "schema_version": "1.0",
            "title": data["title"],
            "generated_at_utc": data["generated_at_utc"],
            "files": file_manifest,
            "limitations": data.get("limitations", []),
        }
        return ReportBundle(str(data["title"]), str(data["generated_at_utc"]), files, manifest)
