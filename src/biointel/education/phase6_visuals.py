from __future__ import annotations

import html
import math
from collections import Counter
from datetime import datetime
from typing import Any, Iterable


def _safe(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, float(value)))


def metric_cards(items: Iterable[tuple[str, Any, str, str]]) -> str:
    cards = []
    for label, value, detail, icon in items:
        cards.append(
            f'<article class="edu6-metric"><div class="edu6-metric-icon">{_safe(icon)}</div>'
            f'<div><span>{_safe(label)}</span><strong>{_safe(value)}</strong><small>{_safe(detail)}</small></div></article>'
        )
    return '<div class="edu6-metric-grid">' + "".join(cards) + "</div>"


def timetable_calendar(calendar: dict[str, Any]) -> str:
    days = calendar.get("days", [])
    by_day = calendar.get("by_day", {})
    columns = []
    for day in days:
        try:
            parsed = datetime.fromisoformat(day)
            heading = parsed.strftime("%a")
            subheading = parsed.strftime("%d %b")
        except ValueError:
            heading, subheading = day, ""
        entries = []
        for row in by_day.get(day, []):
            start = str(row.get("starts_at", ""))[11:16]
            end = str(row.get("ends_at", ""))[11:16]
            entries.append(
                '<div class="edu6-calendar-event">'
                f'<strong>{_safe(row.get("subject_code") or row.get("subject_name") or "Session")}</strong>'
                f'<span>{_safe(start)}–{_safe(end)}</span>'
                f'<small>{_safe(row.get("room") or "Room TBA")} · {_safe(row.get("teacher_id") or "Faculty")}</small>'
                '</div>'
            )
        empty = '<div class="edu6-calendar-empty">No sessions</div>' if not entries else ""
        columns.append(
            '<section class="edu6-calendar-day">'
            f'<header><strong>{_safe(heading)}</strong><span>{_safe(subheading)}</span></header>'
            + "".join(entries) + empty + '</section>'
        )
    return '<div class="edu6-calendar">' + "".join(columns) + "</div>"


def assignment_funnel(counts: dict[str, int]) -> str:
    stages = [
        ("Draft", counts.get("draft", 0)),
        ("Published", counts.get("published", 0)),
        ("Submitted", counts.get("submitted", 0)),
        ("Late", counts.get("late", 0)),
        ("Graded", counts.get("graded", 0)),
    ]
    maximum = max((value for _, value in stages), default=1) or 1
    blocks = []
    for index, (label, value) in enumerate(stages):
        width = max(42, int(100 - index * 10))
        intensity = 0.25 + 0.7 * (value / maximum)
        blocks.append(
            f'<div class="edu6-funnel-step" style="width:{width}%;--intensity:{intensity:.2f}">'
            f'<span>{_safe(label)}</span><strong>{value}</strong></div>'
        )
    return '<div class="edu6-funnel">' + "".join(blocks) + "</div>"


def attendance_heatmap(summary: list[dict[str, Any]], *, limit: int = 20) -> str:
    if not summary:
        return '<div class="edu6-empty">No attendance evidence yet.</div>'
    rows = []
    for item in summary[:limit]:
        value = _clamp(float(item.get("attendance_percent", 0)) / 100.0)
        rows.append(
            '<div class="edu6-heat-row">'
            f'<span>{_safe(item.get("student_id"))}</span>'
            f'<div class="edu6-heat-track"><i style="width:{value*100:.1f}%"></i></div>'
            f'<strong>{value*100:.0f}%</strong></div>'
        )
    return '<div class="edu6-heatmap">' + "".join(rows) + "</div>"


def mastery_graph(graph: dict[str, Any]) -> str:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not nodes:
        return '<div class="edu6-empty">Create concepts and mastery evidence to render the knowledge graph.</div>'
    width, height = 920, 440
    count = len(nodes)
    positions: dict[str, tuple[float, float]] = {}
    rings = max(1, math.ceil(count / 8))
    for index, node in enumerate(nodes):
        ring = index // 8
        ring_nodes = min(8, count - ring * 8)
        angle = 2 * math.pi * (index % 8) / max(1, ring_nodes) - math.pi / 2
        radius = 90 + ring * 115
        positions[str(node["id"])] = (width / 2 + math.cos(angle) * radius, height / 2 + math.sin(angle) * radius)
    edge_html = []
    for edge in edges:
        source = positions.get(str(edge.get("source")))
        target = positions.get(str(edge.get("target")))
        if source and target:
            edge_html.append(
                f'<line x1="{source[0]:.1f}" y1="{source[1]:.1f}" x2="{target[0]:.1f}" y2="{target[1]:.1f}" class="edu6-graph-edge" marker-end="url(#arrow)" />'
            )
    node_html = []
    for node in nodes:
        x, y = positions[str(node["id"])]
        mastery = _clamp(node.get("mastery", 0))
        confidence = _clamp(node.get("confidence", 0))
        radius = 24 + 8 * confidence
        hue = 8 + mastery * 150
        label = str(node.get("label", "Concept"))[:22]
        node_html.append(
            f'<g class="edu6-graph-node"><circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
            f'style="--node-hue:{hue:.0f};--node-alpha:{0.45 + confidence*0.5:.2f}" />'
            f'<text x="{x:.1f}" y="{y+4:.1f}">{_safe(node.get("code") or label[:8])}</text>'
            f'<title>{_safe(label)} · mastery {mastery*100:.0f}% · confidence {confidence*100:.0f}%</title></g>'
        )
    return (
        f'<div class="edu6-graph-wrap"><svg viewBox="0 0 {width} {height}" role="img" aria-label="Concept prerequisite and mastery graph">'
        '<defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" /></marker></defs>'
        + "".join(edge_html) + "".join(node_html) + '</svg></div>'
    )


def exam_lifecycle(exams: list[dict[str, Any]]) -> str:
    order = ["draft", "published", "live", "grading", "released"]
    counts = Counter(str(item.get("state", "draft")) for item in exams)
    blocks = []
    for state in order:
        blocks.append(
            '<div class="edu6-lifecycle-step">'
            f'<span>{_safe(state.replace("_", " ").title())}</span><strong>{counts.get(state, 0)}</strong></div>'
        )
    return '<div class="edu6-lifecycle">' + '<i></i>'.join(blocks) + '</div>'


def exam_monitor_grid(sessions: list[dict[str, Any]]) -> str:
    if not sessions:
        return '<div class="edu6-empty">No candidate sessions yet.</div>'
    cards = []
    for row in sessions:
        state = str(row.get("state", "unknown"))
        flags = row.get("integrity_flags_json", "[]")
        try:
            flag_count = len(json.loads(flags))
        except Exception:
            flag_count = 0
        cards.append(
            f'<article class="edu6-candidate state-{_safe(state)}">'
            f'<header><strong>{_safe(row.get("student_id"))}</strong><span>{_safe(state)}</span></header>'
            f'<small>Attempt {int(row.get("attempt_number", 1))} · flags {flag_count}</small>'
            f'<div class="edu6-candidate-time">Last save {_safe(str(row.get("last_seen_at", ""))[11:19])}</div>'
            '</article>'
        )
    return '<div class="edu6-candidate-grid">' + "".join(cards) + "</div>"


def histogram(values: list[int], labels: list[str] | None = None, *, title: str = "Distribution") -> str:
    if not values:
        return '<div class="edu6-empty">No distribution data.</div>'
    maximum = max(values) or 1
    labels = labels or [str(index) for index in range(len(values))]
    bars = []
    for index, value in enumerate(values):
        height = max(3, (value / maximum) * 100)
        label = labels[index] if index < len(labels) else str(index)
        bars.append(
            f'<div class="edu6-bar"><i style="height:{height:.1f}%"></i><strong>{value}</strong><span>{_safe(label)}</span></div>'
        )
    return f'<div class="edu6-chart-title">{_safe(title)}</div><div class="edu6-bars">' + "".join(bars) + "</div>"


def blueprint_matrix(question_rows: list[dict[str, Any]]) -> str:
    blooms = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
    difficulties = ["easy", "medium", "hard"]
    matrix: dict[tuple[str, str], int] = Counter((str(row.get("difficulty")), str(row.get("bloom_level"))) for row in question_rows)
    header = '<div class="edu6-matrix-cell head">Difficulty</div>' + "".join(f'<div class="edu6-matrix-cell head">{_safe(item.title())}</div>' for item in blooms)
    cells = [header]
    maximum = max(matrix.values(), default=1)
    for difficulty in difficulties:
        row = [f'<div class="edu6-matrix-cell head">{_safe(difficulty.title())}</div>']
        for bloom in blooms:
            value = matrix.get((difficulty, bloom), 0)
            alpha = 0.08 + 0.65 * value / maximum if value else 0.03
            row.append(f'<div class="edu6-matrix-cell" style="--cell-alpha:{alpha:.2f}"><strong>{value}</strong></div>')
        cells.append("".join(row))
    return '<div class="edu6-matrix">' + "".join(cells) + '</div>'


def organization_tree(hierarchy: dict[str, Any]) -> str:
    institution = hierarchy.get("institution", {})
    campuses = hierarchy.get("campuses", [])
    campus_nodes = []
    for campus in campuses:
        units = campus.get("units") or campus.get("unit_ids") or []
        unit_nodes = "".join(
            f'<li><span class="edu6-tree-node unit">{_safe(unit.get("name") if isinstance(unit, dict) else unit)}</span></li>'
            for unit in units
        ) or '<li><span class="edu6-tree-node muted">No mapped units</span></li>'
        campus_nodes.append(
            '<li><span class="edu6-tree-node campus">'
            f'{_safe(campus.get("code"))} · {_safe(campus.get("name"))}</span><ul>{unit_nodes}</ul></li>'
        )
    return (
        '<div class="edu6-tree"><ul><li><span class="edu6-tree-node root">'
        f'{_safe(institution.get("name") or "Institution")}</span><ul>'
        + ("".join(campus_nodes) or '<li><span class="edu6-tree-node muted">Create a campus to begin.</span></li>')
        + '</ul></li></ul></div>'
    )


def queue_board(operations: dict[str, Any]) -> str:
    jobs = operations.get("jobs", [])
    states = ["queued", "running", "succeeded", "failed", "cancelled"]
    columns = []
    for state in states:
        cards = []
        for job in [row for row in jobs if row.get("state") == state][:12]:
            progress = float(job.get("progress_percent") or (100 if state == "succeeded" else 0))
            cards.append(
                '<article class="edu6-job-card">'
                f'<strong>{_safe(job.get("job_type"))}</strong><small>{_safe(job.get("queue_name"))} · priority {_safe(job.get("priority"))}</small>'
                f'<div class="edu6-mini-progress"><i style="width:{_clamp(progress/100)*100:.1f}%"></i></div>'
                f'<span>{progress:.0f}% · {_safe(job.get("progress_message") or job.get("error_text") or state)}</span></article>'
            )
        columns.append(
            f'<section class="edu6-queue-column"><header>{_safe(state.title())}<b>{sum(1 for row in jobs if row.get("state") == state)}</b></header>'
            + ("".join(cards) or '<div class="edu6-calendar-empty">Empty</div>') + '</section>'
        )
    return '<div class="edu6-queue-board">' + "".join(columns) + "</div>"


def integration_topology(integrations: list[dict[str, Any]], runs: list[dict[str, Any]]) -> str:
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        latest.setdefault(str(run.get("integration_id")), run)
    nodes = []
    for item in integrations:
        run = latest.get(str(item.get("id")), {})
        nodes.append(
            '<article class="edu6-integration-node">'
            f'<div class="edu6-provider">{_safe(item.get("provider_type", "provider").replace("_", " ").title())}</div>'
            f'<strong>{_safe(item.get("name"))}</strong>'
            f'<span>{_safe(item.get("state"))}</span>'
            f'<small>Last sync: {_safe(run.get("state") or "Not started")}</small></article>'
        )
    return '<div class="edu6-topology"><div class="edu6-core-node">BioIntel<br><small>Institution OS</small></div><div class="edu6-topology-links">' + "".join(nodes) + '</div></div>'


def activity_timeline(rows: list[dict[str, Any]], *, empty: str = "No recent activity.") -> str:
    if not rows:
        return f'<div class="edu6-empty">{_safe(empty)}</div>'
    items = []
    for row in rows[:25]:
        title = row.get("title") or row.get("action") or row.get("event_type") or "Activity"
        detail = row.get("detail") or row.get("target_type") or row.get("body") or ""
        stamp = row.get("created_at") or row.get("visited_at") or row.get("started_at") or ""
        items.append(
            '<div class="edu6-timeline-item"><i></i><div>'
            f'<strong>{_safe(title).replace("_", " ")}</strong><span>{_safe(detail)}</span><small>{_safe(stamp)}</small></div></div>'
        )
    return '<div class="edu6-timeline">' + "".join(items) + "</div>"


def chat_messages(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return '<div class="edu6-empty">Start a grounded conversation with Shiro.</div>'
    bubbles = []
    for message in messages:
        role = str(message.get("role", "assistant"))
        evidence = message.get("evidence_status", "")
        citation_count = len(message.get("citations", []))
        meta = ""
        if role == "assistant":
            meta = f'<small>{_safe(evidence or "response")} · {citation_count} citation(s)</small>'
        bubbles.append(
            f'<article class="edu6-chat-bubble {"user" if role == "user" else "assistant"}">'
            f'<header>{"You" if role == "user" else "Shiro AI"}</header><p>{_safe(message.get("body")).replace(chr(10), "<br>")}</p>{meta}</article>'
        )
    return '<div class="edu6-chat-thread">' + "".join(bubbles) + "</div>"


PHASE6_CSS = r"""
<style>
:root{--edu6-surface:rgba(14,31,52,.88);--edu6-border:rgba(151,190,231,.2);--edu6-muted:#9fb6cf;--edu6-text:#f3f8ff;--edu6-accent:#4fe4ff;--edu6-accent2:#7d91ff;--edu6-good:#55e6a5;--edu6-warn:#ffcc72;--edu6-danger:#ff7f9a}
html{font-size:calc(16px * var(--edu-font-scale,1))}
.edu6-metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem;margin:.7rem 0 1rem}.edu6-metric{display:flex;gap:.75rem;padding:.9rem;border:1px solid var(--edu6-border);border-radius:17px;background:linear-gradient(145deg,rgba(20,42,69,.92),rgba(9,25,43,.9))}.edu6-metric-icon{display:grid;place-items:center;width:2.45rem;height:2.45rem;border-radius:13px;background:rgba(79,228,255,.12);color:var(--edu6-accent);font-size:1.25rem}.edu6-metric span,.edu6-metric small{display:block;color:var(--edu6-muted);font-size:.72rem}.edu6-metric strong{display:block;color:var(--edu6-text);font-size:1.28rem;margin:.08rem 0}
.edu6-calendar{display:grid;grid-template-columns:repeat(7,minmax(9rem,1fr));gap:.5rem;overflow-x:auto;padding-bottom:.35rem}.edu6-calendar-day{min-height:15rem;border:1px solid var(--edu6-border);border-radius:16px;background:rgba(10,25,43,.72);padding:.55rem}.edu6-calendar-day>header{display:flex;justify-content:space-between;color:var(--edu6-text);padding:.2rem .25rem .5rem}.edu6-calendar-day>header span{color:var(--edu6-muted);font-size:.72rem}.edu6-calendar-event{padding:.58rem;margin:.35rem 0;border-radius:12px;border-left:3px solid var(--edu6-accent);background:linear-gradient(135deg,rgba(79,228,255,.11),rgba(125,145,255,.08))}.edu6-calendar-event strong,.edu6-calendar-event span,.edu6-calendar-event small{display:block}.edu6-calendar-event strong{color:var(--edu6-text);font-size:.82rem}.edu6-calendar-event span{color:#b7eaff;font-size:.7rem}.edu6-calendar-event small{color:var(--edu6-muted);font-size:.65rem;margin-top:.2rem}.edu6-calendar-empty,.edu6-empty{padding:1rem;text-align:center;color:var(--edu6-muted);border:1px dashed var(--edu6-border);border-radius:12px;font-size:.78rem}
.edu6-funnel{display:flex;flex-direction:column;align-items:center;gap:.38rem;padding:.5rem}.edu6-funnel-step{display:flex;justify-content:space-between;padding:.6rem .85rem;border-radius:9px;background:linear-gradient(90deg,rgba(79,228,255,var(--intensity)),rgba(125,145,255,.16));color:var(--edu6-text)}
.edu6-heatmap{display:grid;gap:.48rem}.edu6-heat-row{display:grid;grid-template-columns:minmax(8rem,1fr) 3fr 3rem;gap:.55rem;align-items:center;color:var(--edu6-muted);font-size:.76rem}.edu6-heat-row strong{color:var(--edu6-text);text-align:right}.edu6-heat-track{height:.72rem;border-radius:999px;background:rgba(255,255,255,.07);overflow:hidden}.edu6-heat-track i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--edu6-danger),var(--edu6-warn),var(--edu6-good))}
.edu6-graph-wrap{overflow:auto;border:1px solid var(--edu6-border);border-radius:18px;background:radial-gradient(circle at center,rgba(79,228,255,.08),transparent 55%),rgba(7,20,35,.78)}.edu6-graph-wrap svg{min-width:700px;width:100%;height:auto}.edu6-graph-edge{stroke:rgba(159,182,207,.38);stroke-width:1.4}.edu6-graph-wrap marker path{fill:rgba(159,182,207,.55)}.edu6-graph-node circle{fill:hsla(var(--node-hue),85%,55%,var(--node-alpha));stroke:rgba(255,255,255,.55);stroke-width:2}.edu6-graph-node text{fill:#06121e;text-anchor:middle;font-size:10px;font-weight:850}
.edu6-lifecycle{display:flex;align-items:center;gap:.45rem;overflow-x:auto;padding:.6rem}.edu6-lifecycle-step{min-width:9rem;padding:.75rem;border:1px solid var(--edu6-border);border-radius:14px;background:var(--edu6-surface);display:flex;justify-content:space-between;color:var(--edu6-muted)}.edu6-lifecycle-step strong{font-size:1.2rem;color:var(--edu6-text)}.edu6-lifecycle>i{min-width:1.7rem;height:2px;background:linear-gradient(90deg,var(--edu6-accent),var(--edu6-accent2))}
.edu6-candidate-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.55rem}.edu6-candidate{padding:.72rem;border:1px solid var(--edu6-border);border-radius:14px;background:var(--edu6-surface)}.edu6-candidate header{display:flex;justify-content:space-between;color:var(--edu6-text)}.edu6-candidate header span{font-size:.68rem;text-transform:uppercase;color:var(--edu6-accent)}.edu6-candidate small,.edu6-candidate-time{display:block;color:var(--edu6-muted);font-size:.66rem;margin-top:.35rem}.edu6-candidate.state-submitted{border-color:rgba(85,230,165,.45)}.edu6-candidate.state-expired{border-color:rgba(255,127,154,.45)}
.edu6-chart-title{color:var(--edu6-text);font-weight:800;margin:.35rem 0}.edu6-bars{display:flex;align-items:end;gap:.45rem;height:13rem;border-bottom:1px solid var(--edu6-border);padding:.6rem}.edu6-bar{flex:1;height:100%;display:flex;flex-direction:column;justify-content:end;align-items:center;gap:.2rem;color:var(--edu6-muted);font-size:.65rem}.edu6-bar i{display:block;width:80%;min-height:3px;border-radius:7px 7px 2px 2px;background:linear-gradient(180deg,var(--edu6-accent),var(--edu6-accent2))}.edu6-bar strong{color:var(--edu6-text)}
.edu6-matrix{display:grid;grid-template-columns:repeat(7,minmax(5rem,1fr));gap:.3rem;overflow-x:auto}.edu6-matrix-cell{min-height:3.3rem;display:grid;place-items:center;border:1px solid var(--edu6-border);border-radius:9px;background:rgba(79,228,255,var(--cell-alpha,.03));color:var(--edu6-text)}.edu6-matrix-cell.head{background:rgba(255,255,255,.05);color:var(--edu6-muted);font-size:.68rem;font-weight:800}
.edu6-tree ul{position:relative;padding-top:1rem;display:flex;justify-content:center}.edu6-tree li{list-style:none;text-align:center;position:relative;padding:1rem .45rem 0}.edu6-tree li:before,.edu6-tree li:after{content:"";position:absolute;top:0;width:50%;height:1rem;border-top:1px solid var(--edu6-border)}.edu6-tree li:before{right:50%}.edu6-tree li:after{left:50%;border-left:1px solid var(--edu6-border)}.edu6-tree li:only-child:before,.edu6-tree li:only-child:after{display:none}.edu6-tree-node{display:inline-block;padding:.58rem .75rem;border:1px solid var(--edu6-border);border-radius:12px;background:var(--edu6-surface);color:var(--edu6-text);font-size:.74rem}.edu6-tree-node.root{background:linear-gradient(135deg,rgba(79,228,255,.2),rgba(125,145,255,.18));font-weight:850}.edu6-tree-node.campus{border-color:rgba(79,228,255,.4)}.edu6-tree-node.muted{color:var(--edu6-muted)}
.edu6-queue-board{display:grid;grid-template-columns:repeat(5,minmax(12rem,1fr));gap:.55rem;overflow-x:auto}.edu6-queue-column{padding:.55rem;border:1px solid var(--edu6-border);border-radius:15px;background:rgba(7,20,35,.72)}.edu6-queue-column>header{display:flex;justify-content:space-between;color:var(--edu6-text);font-size:.78rem;font-weight:800;margin-bottom:.5rem}.edu6-queue-column>header b{padding:.12rem .42rem;border-radius:999px;background:rgba(79,228,255,.12);color:var(--edu6-accent)}.edu6-job-card{display:block;padding:.58rem;margin:.38rem 0;border-radius:11px;background:var(--edu6-surface);border:1px solid var(--edu6-border)}.edu6-job-card strong,.edu6-job-card small,.edu6-job-card span{display:block}.edu6-job-card strong{color:var(--edu6-text);font-size:.74rem}.edu6-job-card small,.edu6-job-card span{color:var(--edu6-muted);font-size:.62rem}.edu6-mini-progress{height:.38rem;background:rgba(255,255,255,.07);border-radius:99px;overflow:hidden;margin:.42rem 0}.edu6-mini-progress i{display:block;height:100%;background:linear-gradient(90deg,var(--edu6-accent),var(--edu6-good))}
.edu6-topology{display:grid;grid-template-columns:12rem 1fr;gap:1rem;align-items:center}.edu6-core-node{display:grid;place-items:center;text-align:center;min-height:8rem;border-radius:50%;border:2px solid rgba(79,228,255,.45);background:radial-gradient(circle,rgba(79,228,255,.2),rgba(9,25,43,.9));color:var(--edu6-text);font-weight:900}.edu6-core-node small{color:var(--edu6-muted)}.edu6-topology-links{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.55rem}.edu6-integration-node{padding:.72rem;border:1px solid var(--edu6-border);border-radius:14px;background:var(--edu6-surface)}.edu6-integration-node strong,.edu6-integration-node span,.edu6-integration-node small{display:block}.edu6-integration-node strong{color:var(--edu6-text)}.edu6-integration-node span,.edu6-integration-node small{color:var(--edu6-muted);font-size:.67rem}.edu6-provider{font-size:.62rem;color:var(--edu6-accent);text-transform:uppercase;font-weight:850}
.edu6-timeline{position:relative;padding-left:1rem}.edu6-timeline:before{content:"";position:absolute;left:.35rem;top:.4rem;bottom:.4rem;width:1px;background:var(--edu6-border)}.edu6-timeline-item{display:grid;grid-template-columns:.8rem 1fr;gap:.45rem;margin:.65rem 0}.edu6-timeline-item>i{width:.65rem;height:.65rem;border-radius:50%;background:var(--edu6-accent);box-shadow:0 0 0 4px rgba(79,228,255,.1)}.edu6-timeline-item strong,.edu6-timeline-item span,.edu6-timeline-item small{display:block}.edu6-timeline-item strong{color:var(--edu6-text);font-size:.78rem}.edu6-timeline-item span,.edu6-timeline-item small{color:var(--edu6-muted);font-size:.66rem}
.edu6-chat-thread{display:flex;flex-direction:column;gap:.7rem;max-height:34rem;overflow:auto;padding:.7rem}.edu6-chat-bubble{max-width:82%;padding:.8rem 1rem;border-radius:17px;border:1px solid var(--edu6-border)}.edu6-chat-bubble.user{align-self:flex-end;background:linear-gradient(135deg,rgba(79,228,255,.18),rgba(125,145,255,.15));border-bottom-right-radius:5px}.edu6-chat-bubble.assistant{align-self:flex-start;background:var(--edu6-surface);border-bottom-left-radius:5px}.edu6-chat-bubble header{color:var(--edu6-accent);font-size:.68rem;font-weight:850}.edu6-chat-bubble p{color:var(--edu6-text);font-size:.82rem;line-height:1.55;margin:.35rem 0}.edu6-chat-bubble small{color:var(--edu6-muted)}
[data-edu-density="compact"] .edu6-metric,[data-edu-density="compact"] .edu6-calendar-event{padding:.55rem}.edu-high-contrast{--edu6-border:rgba(255,255,255,.6);--edu6-muted:#e1e9f2;--edu6-text:#fff}.edu-light{--edu6-surface:rgba(255,255,255,.92);--edu6-border:rgba(31,65,95,.2);--edu6-muted:#51677c;--edu6-text:#102235}.edu-reduced-motion *{scroll-behavior:auto!important;animation:none!important;transition:none!important}.edu-dyslexia{font-family:Verdana,Tahoma,Arial,sans-serif!important;letter-spacing:.02em;word-spacing:.06em}
@media(max-width:1100px){.edu6-metric-grid,.edu6-candidate-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.edu6-topology-links{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.edu6-metric-grid,.edu6-candidate-grid{grid-template-columns:1fr}.edu6-calendar{grid-template-columns:repeat(7,minmax(10rem,1fr))}.edu6-topology{grid-template-columns:1fr}.edu6-topology-links{grid-template-columns:1fr}.edu6-matrix{grid-template-columns:repeat(7,minmax(4.7rem,1fr))}.edu6-chat-bubble{max-width:95%}}
button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible,[tabindex]:focus-visible{outline:3px solid #67e8f9!important;outline-offset:3px!important;border-radius:.45rem}
@media (prefers-reduced-motion: reduce){*,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
</style>
"""
