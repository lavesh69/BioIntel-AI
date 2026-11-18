from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from typing import Mapping

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from biointel.ui.brand import BRAND

from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)




def _brand_page(canvas, document) -> None:
    """Apply a restrained BioIntel header/footer to every generated PDF page."""

    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor(BRAND.primary))
    canvas.setLineWidth(1.2)
    canvas.line(18 * mm, height - 11 * mm, width - 18 * mm, height - 11 * mm)
    canvas.setFillColor(colors.HexColor("#0F172A"))
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.drawString(18 * mm, height - 8.2 * mm, BRAND.name)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.setFont("Helvetica", 7.2)
    canvas.drawRightString(width - 18 * mm, height - 8.2 * mm, BRAND.tagline)
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.setLineWidth(.45)
    canvas.line(18 * mm, 11 * mm, width - 18 * mm, 11 * mm)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.setFont("Helvetica", 6.8)
    canvas.drawString(18 * mm, 7.5 * mm, "Generated with BioIntel AI · Evidence-aware scientific intelligence")
    canvas.drawRightString(width - 18 * mm, 7.5 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _flatten(
    prefix: str,
    value: object,
    rows: list[list[str]],
) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            label = f"{prefix} → {key}" if prefix else str(key)
            _flatten(label, nested, rows)
    elif isinstance(value, (list, tuple)):
        text = ", ".join(map(str, value[:30]))
        if len(value) > 30:
            text += f" … ({len(value)} total)"
        rows.append([prefix, text])
    else:
        rows.append([prefix, str(value)])


def build_structured_pdf(
    title: str,
    sections: Mapping[str, Mapping[str, object] | object],
    disclaimer: str | None = None,
) -> bytes:
    """Build a readable PDF with flattened result sections."""

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=title,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor(BRAND.background)
    styles["Heading2"].textColor = colors.HexColor(BRAND.secondary)
    story = [
        Paragraph(BRAND.descriptor, styles["Heading3"]),
        Paragraph(title, styles["Title"]),
        Paragraph(BRAND.tagline, styles["BodyText"]),
        Spacer(1, 6),
        Paragraph(
            "Generated: " + datetime.now(UTC).isoformat(timespec="seconds"),
            styles["BodyText"],
        ),
        Spacer(1, 12),
    ]

    for section_name, section_value in sections.items():
        story.append(Paragraph(str(section_name), styles["Heading2"]))
        rows: list[list[str]] = [["Metric", "Value"]]
        _flatten("", section_value, rows)
        table = Table(
            rows,
            repeatRows=1,
            colWidths=[65 * mm, 105 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor("#E6F8FC"),
                    ),
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.35,
                        colors.grey,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, 0),
                        "Helvetica-Bold",
                    ),
                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, -1),
                        8,
                    ),
                ]
            )
        )
        story.extend([table, Spacer(1, 12)])

    story.extend(
        [
            PageBreak(),
            Paragraph(
                "Scientific and safety notice",
                styles["Heading2"],
            ),
            Paragraph(
                disclaimer
                or (
                    "Computational results require verification "
                    "with curated databases and laboratory methods. "
                    "They do not establish binding, safety, efficacy, "
                    "diagnosis or treatment suitability."
                ),
                styles["BodyText"],
            ),
        ]
    )
    document.build(story, onFirstPage=_brand_page, onLaterPages=_brand_page)
    return buffer.getvalue()


def build_summary_pdf(title: str, summary: Mapping[str, object]) -> bytes:
    return build_structured_pdf(title, {"Summary": summary})
