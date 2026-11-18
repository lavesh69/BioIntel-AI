from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import io
import importlib.util
import json
import re
import zipfile
from typing import Any, Iterable

import pandas as pd

from .catalog import MODULE_BY_KEY
from .scientific import AnalysisBundle
from .visuals import VisualArtifact
from .interoperability import standards_bundle
from .portable_workflows import default_plan, workflow_pack
from .uncertainty import uncertainty_table


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text[:80] or "figure"


def _frame_sha(frame: pd.DataFrame) -> str:
    return sha256(frame.to_csv(index=False, lineterminator="\n", na_rep="<NA>").encode("utf-8")).hexdigest()


def build_publication_bundle(
    *,
    module_key: str,
    source: pd.DataFrame,
    bundle: AnalysisBundle,
    visuals: Iterable[VisualArtifact],
    parameters: dict[str, Any],
    reference_status: list[dict[str, Any]] | None = None,
    review_summary: dict[str, Any] | None = None,
    include_static: bool = True,
) -> bytes:
    module = MODULE_BY_KEY[module_key]
    visual_list = list(visuals)
    generated = datetime.now(timezone.utc).isoformat()
    static_renderer_available = importlib.util.find_spec("kaleido") is not None
    manifest: dict[str, Any] = {
        "schema": "biointel.bioinformatics.publication_bundle.v140",
        "module_key": module_key,
        "title": module.title,
        "generated_at_utc": generated,
        "input_rows": len(source),
        "input_sha256": _frame_sha(source),
        "result_rows": len(bundle.result),
        "result_sha256": _frame_sha(bundle.result),
        "quality_status": bundle.summary.get("quality_status"),
        "parameters": parameters,
        "scientific_boundary": module.boundary,
        "references": reference_status or [],
        "review_summary": review_summary or {},
        "figures": [],
        "peak_v140": {
            "standards": ["VRS compatibility subset", "Phenopacket validation", "DRS/htsget manifests"],
            "portable_workflow": True,
            "uncertainty": True,
            "container_digest_locking": True,
        },
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("data/results.csv", bundle.result.to_csv(index=False))
        archive.writestr("data/quality_gates.csv", bundle.quality.to_csv(index=False))
        archive.writestr("data/source_preview.csv", source.head(25_000).to_csv(index=False))
        standards = standards_bundle(module_key, bundle.result)
        archive.writestr("interoperability/standards_bundle.json", json.dumps(standards, indent=2, sort_keys=True, default=str))
        portable = workflow_pack(default_plan(module_key, input_name="analysis_input.csv"))
        archive.writestr("workflow/portable_workflow_pack.json", json.dumps(portable, indent=2, sort_keys=True, default=str))
        try:
            uncertainty_frame, uncertainty_summary = uncertainty_table(bundle.result, iterations=500)
            archive.writestr("validation/uncertainty_metrics.csv", uncertainty_frame.to_csv(index=False))
            archive.writestr("validation/uncertainty_summary.json", json.dumps(uncertainty_summary, indent=2, sort_keys=True, default=str))
            manifest["peak_v140"]["uncertainty_summary"] = uncertainty_summary
        except Exception as exc:
            manifest["peak_v140"]["uncertainty_status"] = f"Unavailable: {type(exc).__name__}: {exc}"
        for name, frame in bundle.extras.items():
            if isinstance(frame, pd.DataFrame):
                archive.writestr(f"data/derived/{_slug(name)}.csv", frame.head(250_000).to_csv(index=False))

        figure_sections: list[str] = []
        methods_lines = [f"# Methods — {module.title}", "", f"Generated: {generated}", "", "## Analysis parameters", ""]
        methods_lines.extend(f"- **{key}**: {value}" for key, value in sorted(parameters.items()))
        methods_lines.extend(["", "## Scientific boundary", "", module.boundary, ""])

        for index, visual in enumerate(visual_list, start=1):
            slug = f"figure-{index:02d}-{_slug(visual.title)}"
            data_path = f"figures/{slug}/underlying_data.csv"
            json_path = f"figures/{slug}/figure.plotly.json"
            html_path = f"figures/{slug}/interactive.html"
            caption_path = f"figures/{slug}/caption.md"
            archive.writestr(data_path, visual.data.to_csv(index=False))
            archive.writestr(json_path, visual.figure.to_json())
            archive.writestr(html_path, visual.figure.to_html(full_html=True, include_plotlyjs="cdn"))
            caption = (
                f"# Figure {index}. {visual.title}\n\n"
                f"**Interpretation:** {visual.interpretation}\n\n"
                f"**Method:** {visual.method}\n\n"
                f"**Source table:** {visual.source_name}\n\n"
                f"**Records represented:** {len(visual.data):,}\n"
            )
            archive.writestr(caption_path, caption)
            static_files: list[str] = []
            static_error = ""
            if include_static and static_renderer_available:
                for extension, image_format, scale in (("svg", "svg", 1), ("png", "png", 3), ("pdf", "pdf", 1)):
                    try:
                        payload = visual.figure.to_image(format=image_format, width=1400, height=850, scale=scale)
                        path = f"figures/{slug}/{slug}.{extension}"
                        archive.writestr(path, payload)
                        static_files.append(path)
                    except Exception as exc:
                        static_error = f"Static export unavailable: {type(exc).__name__}: {exc}"
                        break
            elif include_static:
                static_error = "Static export unavailable: optional Kaleido renderer is not installed"
            figure_record = {
                "figure_number": index,
                "title": visual.title,
                "interpretation": visual.interpretation,
                "method": visual.method,
                "source_table": visual.source_name,
                "records": len(visual.data),
                "data_path": data_path,
                "plotly_json_path": json_path,
                "interactive_html_path": html_path,
                "caption_path": caption_path,
                "static_files": static_files,
                "static_export_status": "available" if static_files else static_error or "not requested",
            }
            manifest["figures"].append(figure_record)
            methods_lines.extend([f"## Figure {index}: {visual.title}", "", visual.method, ""])
            figure_sections.append(
                "<section class='figure'><h2>Figure %d. %s</h2><p>%s</p><p class='meta'>%s · Source: %s · n=%s</p></section>"
                % (index, escape(visual.title), escape(visual.interpretation), escape(visual.method), escape(visual.source_name), f"{len(visual.data):,}")
            )

        archive.writestr("methods.md", "\n".join(methods_lines))
        archive.writestr(
            "report.html",
            "<!doctype html><html><head><meta charset='utf-8'><title>%s</title><style>"
            "body{font-family:Inter,Arial,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#102033;}"
            "h1,h2{color:#0b3b65}.meta{color:#5c6f82}.figure{border:1px solid #d8e2eb;border-radius:14px;padding:18px;margin:18px 0;}"
            ".status{display:inline-block;padding:6px 10px;border-radius:999px;background:#e9f5ff}</style></head><body>"
            "<h1>%s</h1><p class='status'>Quality status: %s</p><p>Generated %s</p><h2>Scientific boundary</h2><p>%s</p>%s</body></html>"
            % (
                escape(module.title), escape(module.title), escape(str(bundle.summary.get("quality_status", "Review"))),
                escape(generated), escape(module.boundary), "".join(figure_sections),
            ),
        )
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True, default=str))
        archive.writestr(
            "README.txt",
            "BioIntel AI publication bundle\n\nInteractive HTML and Plotly JSON are always included. "
            "SVG/PNG/PDF files require the optional Kaleido renderer. Missing static exports are recorded honestly in manifest.json.\n",
        )
    return buffer.getvalue()


__all__ = ["build_publication_bundle"]
