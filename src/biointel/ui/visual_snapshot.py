from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._suppressed = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"style", "script"}:
            self._suppressed += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"style", "script"} and self._suppressed:
            self._suppressed -= 1

    def handle_data(self, data: str) -> None:
        if not self._suppressed:
            self.parts.append(data)


def visible_text(value: object) -> str:
    raw = str(value or "")
    parser = _VisibleTextParser()
    try:
        parser.feed(raw)
        text = " ".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\b20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b", "<timestamp>", text)
    # Operational registries can increment during a page run. Preserve labels and layout
    # while normalizing telemetry counters that are intentionally volatile.
    text = re.sub(r"\b\d[\d,]*\s+indexed rows\b", "<count> indexed rows", text, flags=re.IGNORECASE)
    text = re.sub(r"\bIndexed knowledge\s+\d[\d,]*\b", "Indexed knowledge <count>", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b\d[\d,]*\s+(Events|Alerts|Assets|Tags)(?=\b)",
        lambda match: f"<count> {match.group(1)}",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def _values(elements: Iterable[Any], *, kind: str = "", limit: int = 80) -> list[str]:
    values: list[str] = []
    volatile_metric_labels = {
        "indexed rows",
        "events",
        "alerts",
        "assets",
        "tags",
        "runs",
        "records",
        "requests",
        "jobs",
    }
    for element in elements:
        value = visible_text(getattr(element, "value", getattr(element, "label", "")))
        if kind == "metric":
            label = visible_text(getattr(element, "label", ""))
            if label.lower() in volatile_metric_labels and re.fullmatch(r"[\d,]+", value):
                value = "<count>"
            if label:
                value = f"{label}: {value}"
        if value and value not in values:
            values.append(value[:500])
        if len(values) >= limit:
            break
    return values


def build_semantic_snapshot(app_test: Any, *, scenario: str, source: str, viewport: dict[str, int]) -> dict[str, Any]:
    exceptions = [visible_text(getattr(item, "message", item)) for item in app_test.exception]
    if exceptions:
        raise RuntimeError(f"Streamlit semantic snapshot failed for {source}: {' | '.join(exceptions)}")

    selectors = {
        "markdown": app_test.markdown,
        "caption": app_test.caption,
        "metric": app_test.metric,
        "button": app_test.button,
        "text_input": app_test.text_input,
        "text_area": app_test.text_area,
        "selectbox": app_test.selectbox,
        "multiselect": app_test.multiselect,
        "checkbox": app_test.checkbox,
        "radio": app_test.radio,
        "slider": app_test.slider,
        "dataframe": app_test.dataframe,
        "table": app_test.table,
        "tabs": app_test.tabs,
        "expander": app_test.expander,
        "warning": app_test.warning,
        "error": app_test.error,
        "success": app_test.success,
        "info": app_test.info,
    }
    counts = {name: len(elements) for name, elements in selectors.items()}
    visible_sections: dict[str, list[str]] = {}
    for name, elements in selectors.items():
        if name in {"dataframe", "table"}:
            continue
        values = _values(elements, kind=name)
        if values:
            visible_sections[name] = values

    combined = " ".join(value for values in visible_sections.values() for value in values).lower()
    forbidden = ("traceback:", "has encountered an error", "nameerror:", "importerror:")
    detected = [token for token in forbidden if token in combined]
    if detected:
        raise RuntimeError(f"Fatal UI error text detected for {source}: {', '.join(detected)}")

    payload = {
        "schema": "biointel.semantic-visual.v1",
        "scenario": scenario,
        "source": source,
        "viewport": {"width": int(viewport["width"]), "height": int(viewport["height"])},
        "component_counts": counts,
        "visible_sections": visible_sections,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    payload["content_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def _wrapped(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_semantic_snapshot(snapshot: dict[str, Any], destination: str | Path) -> Path:
    width = int(snapshot["viewport"]["width"])
    height = int(snapshot["viewport"]["height"])
    canvas = Image.new("RGB", (width, height), (7, 11, 22))
    draw = ImageDraw.Draw(canvas)
    regular = ImageFont.load_default(size=14)
    small = ImageFont.load_default(size=11)
    title_font = ImageFont.load_default(size=22)

    margin = 28 if width >= 700 else 18
    draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=18, fill=(13, 20, 37), outline=(43, 61, 91), width=2)
    y = margin + 22
    draw.text((margin + 22, y), "BioIntel Semantic Visual Contract", font=title_font, fill=(239, 246, 255))
    y += 34
    draw.text((margin + 22, y), f"{snapshot['scenario']} · {snapshot['source']}", font=regular, fill=(56, 189, 248))
    y += 30

    counts = snapshot["component_counts"]
    count_text = "  ·  ".join(f"{key} {value}" for key, value in counts.items() if value)
    for line in _wrapped(draw, count_text, small, width - 2 * margin - 44)[:3]:
        draw.text((margin + 22, y), line, font=small, fill=(166, 185, 214))
        y += 16
    y += 8

    sections = snapshot["visible_sections"]
    max_sections = 10 if width >= 700 else 7
    for section_name, values in list(sections.items())[:max_sections]:
        if y > height - margin - 70:
            break
        draw.rounded_rectangle((margin + 18, y, width - margin - 18, min(height - margin - 18, y + 68)), radius=10, fill=(17, 28, 50), outline=(38, 55, 82))
        draw.text((margin + 30, y + 9), section_name.upper(), font=small, fill=(45, 212, 191))
        line_y = y + 27
        excerpt = " · ".join(values[:4])
        for line in _wrapped(draw, excerpt, small, width - 2 * margin - 64)[:2]:
            draw.text((margin + 30, line_y), line, font=small, fill=(218, 228, 241))
            line_y += 15
        y += 78

    digest = snapshot["content_sha256"]
    draw.text((margin + 22, height - margin - 30), f"SHA-256 {digest[:24]}…", font=small, fill=(126, 148, 181))
    output = Path(destination).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=False)
    return output


def write_snapshot(snapshot: dict[str, Any], json_path: str | Path, image_path: str | Path) -> tuple[Path, Path]:
    json_destination = Path(json_path).resolve()
    json_destination.parent.mkdir(parents=True, exist_ok=True)
    json_destination.write_text(json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    image_destination = render_semantic_snapshot(snapshot, image_path)
    return json_destination, image_destination
