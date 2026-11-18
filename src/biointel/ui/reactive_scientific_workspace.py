from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import streamlit as st

from biointel.nextgen.interaction_v131 import (
    JOURNAL_PRESETS,
    add_review_comment,
    build_figure_layout_bundle,
    create_review_thread,
    get_viewer_sync_state,
    infer_entity_column,
    infer_score_column,
    list_figure_layouts,
    list_review_comments,
    list_review_threads,
    list_selection_history,
    list_visual_provenance,
    progressive_sample,
    save_figure_layout,
    save_viewer_sync_state,
    save_visual_provenance,
    uncertainty_profile,
    update_review_thread,
)
from biointel.ui.components import metric_cards, scientific_table, smart_dataframe, smart_json
from biointel.ui.scientific_visuals import build_scientific_visuals
from biointel.ui.visual_workspace import (
    clear_linked_selection,
    get_linked_selection,
    linked_selection_history,
    redo_linked_selection,
    undo_linked_selection,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _run_id(run_state: Any) -> str | None:
    if run_state is None:
        return None
    return str((getattr(run_state, "summary", {}) or {}).get("run_id") or "") or None


def _numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [str(column) for column in frame.columns if pd.to_numeric(frame[column], errors="coerce").notna().sum() >= 3]


def _json_records(frame: pd.DataFrame, columns: list[str]) -> str:
    safe = frame[columns].copy()
    safe = safe.replace({np.nan: None, np.inf: None, -np.inf: None})
    return json.dumps(safe.to_dict(orient="records"), ensure_ascii=False, default=str).replace("</", "<\\/")


def render_client_reactive_canvas(module_key: str, frame: pd.DataFrame, *, key: str) -> None:
    """Render a dependency-free browser-side linked scatter/table canvas.

    Point click and drag-box selection update the linked table, summary and uncertainty overlay
    immediately in the browser without a Streamlit rerun. Python state remains unchanged until
    a normal module control is used, preserving deterministic server-side analysis.
    """
    data = pd.DataFrame(frame)
    numeric = _numeric_columns(data)
    entity = infer_entity_column(data)
    if len(numeric) < 2 or not entity:
        st.info("Reactive canvas requires an entity field and at least two numeric fields.")
        return

    controls = st.columns([1, 1, 1, 1])
    x_col = controls[0].selectbox("Reactive X", numeric, index=0, key=f"{key}_x")
    y_col = controls[1].selectbox("Reactive Y", numeric, index=min(1, len(numeric) - 1), key=f"{key}_y")
    score = controls[2].selectbox("Colour/score", ["None", *numeric], index=0, key=f"{key}_score")
    limit = controls[3].select_slider("Browser points", options=[500, 1000, 2500, 5000], value=2500, key=f"{key}_limit")
    linked = get_linked_selection(module_key) or {}
    selected_values = linked.get("values", []) if linked.get("column") == entity else []
    sampled, manifest = progressive_sample(
        data,
        limit=int(limit),
        entity_column=entity,
        score_column=None if score == "None" else score,
        selected_values=selected_values,
    )
    sampled[x_col] = pd.to_numeric(sampled[x_col], errors="coerce")
    sampled[y_col] = pd.to_numeric(sampled[y_col], errors="coerce")
    columns = [entity, x_col, y_col, "__source_row__"]
    if score != "None" and score not in columns:
        sampled[score] = pd.to_numeric(sampled[score], errors="coerce")
        columns.append(score)
    sampled = sampled.dropna(subset=[x_col, y_col]).reset_index(drop=True)
    if sampled.empty:
        st.warning("No finite numeric points are available for the selected axes.")
        return

    metric_cards([
        ("Source rows", f"{manifest.source_rows:,}", "Full result table"),
        ("Browser rows", f"{len(sampled):,}", manifest.strategy),
        ("Extrema kept", manifest.preserved_extrema, "Outlier-preserving LOD"),
        ("Selection mode", "Client-side", "No rerun for click/box filtering"),
    ])

    payload = _json_records(sampled, columns)
    uid = f"reactive_{abs(hash((module_key, key, x_col, y_col, len(sampled))))}"
    score_js = "null" if score == "None" else json.dumps(score)
    html_block = f"""
<!doctype html><html><head><meta charset='utf-8'><style>
*{{box-sizing:border-box}} body{{margin:0;font:13px system-ui,-apple-system,Segoe UI,sans-serif;color:#e8eef7;background:transparent}}
.wrap{{border:1px solid rgba(148,163,184,.35);border-radius:16px;overflow:hidden;background:rgba(15,23,42,.78)}}
.toolbar{{display:flex;gap:8px;align-items:center;padding:9px 12px;background:rgba(30,41,59,.88);flex-wrap:wrap}}
button{{border:1px solid rgba(148,163,184,.45);background:#172033;color:#e8eef7;border-radius:8px;padding:6px 10px;cursor:pointer}}
button:hover{{background:#243047}} .status{{margin-left:auto;color:#a5b4fc;font-weight:600}}
.grid{{display:grid;grid-template-columns:minmax(420px,1.45fr) minmax(300px,1fr);min-height:520px}}
.plot{{position:relative;padding:10px}} svg{{width:100%;height:500px;display:block;touch-action:none}}
.axis{{stroke:#64748b;stroke-width:1}} .gridline{{stroke:#334155;stroke-width:.7;opacity:.7}}
.point{{cursor:pointer;stroke:rgba(255,255,255,.35);stroke-width:.5}} .point.sel{{stroke:#fff;stroke-width:2;opacity:1!important}}
.brush{{fill:rgba(99,102,241,.18);stroke:#a5b4fc;stroke-dasharray:4 3}}
.side{{border-left:1px solid rgba(148,163,184,.25);padding:10px;overflow:auto;max-height:520px}}
.summary{{display:grid;grid-template-columns:repeat(2,1fr);gap:7px;margin-bottom:9px}} .metric{{padding:8px;border-radius:9px;background:rgba(30,41,59,.8)}}
table{{border-collapse:collapse;width:100%;font-size:11px}} th,td{{padding:5px;border-bottom:1px solid rgba(148,163,184,.18);text-align:left;max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}} th{{position:sticky;top:0;background:#172033}}
.tip{{position:absolute;display:none;pointer-events:none;background:#020617;border:1px solid #64748b;padding:7px;border-radius:7px;z-index:5;max-width:280px}}
</style></head><body><div id='{uid}' class='wrap'>
<div class='toolbar'><button data-act='clear'>Clear</button><button data-act='invert'>Invert</button><button data-act='undo'>Undo</button><button data-act='redo'>Redo</button><button data-act='all'>Select all</button><button data-act='csv'>Download selected CSV</button><span>Drag a rectangle or click points</span><span class='status'></span></div>
<div class='grid'><div class='plot'><svg aria-label='Reactive linked scientific scatter'></svg><div class='tip'></div></div><div class='side'><div class='summary'></div><table><thead></thead><tbody></tbody></table></div></div>
</div><script>
(()=>{{
const root=document.getElementById({json.dumps(uid)}), data={payload};
const entity={json.dumps(entity)}, xKey={json.dumps(x_col)}, yKey={json.dumps(y_col)}, scoreKey={score_js};
const svg=root.querySelector('svg'), tip=root.querySelector('.tip'), status=root.querySelector('.status'), tbody=root.querySelector('tbody'), thead=root.querySelector('thead'), summary=root.querySelector('.summary');
const W=760,H=500,M={{l:58,r:24,t:24,b:50}}, NS='http://www.w3.org/2000/svg';
let selected=new Set(), undo=[], redo=[];
const finite=(v)=>Number.isFinite(Number(v)); const xs=data.map(d=>Number(d[xKey])).filter(Number.isFinite), ys=data.map(d=>Number(d[yKey])).filter(Number.isFinite);
let xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys); if(xmin===xmax){{xmin-=1;xmax+=1}} if(ymin===ymax){{ymin-=1;ymax+=1}}
const sx=v=>M.l+(Number(v)-xmin)/(xmax-xmin)*(W-M.l-M.r), sy=v=>H-M.b-(Number(v)-ymin)/(ymax-ymin)*(H-M.t-M.b);
const el=(name,attrs={{}})=>{{const n=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));return n}};
function colour(d){{if(!scoreKey||!finite(d[scoreKey]))return '#818cf8'; const vals=data.map(r=>Number(r[scoreKey])).filter(Number.isFinite), lo=Math.min(...vals),hi=Math.max(...vals),t=hi===lo?.5:(Number(d[scoreKey])-lo)/(hi-lo);return `hsl(${{250-190*t}} 78% ${{58+8*t}}%)`}}
function push(){{undo.push([...selected]);if(undo.length>50)undo.shift();redo=[]}}
function setSel(values,record=true){{if(record)push();selected=new Set(values);update()}}
function update(){{root.querySelectorAll('.point').forEach((p,i)=>p.classList.toggle('sel',selected.has(i))); const rows=selected.size?[...selected].map(i=>data[i]):data.slice(0,200); status.textContent=selected.size?`${{selected.size}} selected`:`${{data.length}} visible`;
 const xvals=(selected.size?[...selected].map(i=>Number(data[i][xKey])):xs).filter(Number.isFinite), yvals=(selected.size?[...selected].map(i=>Number(data[i][yKey])):ys).filter(Number.isFinite);
 const mean=a=>a.length?a.reduce((s,v)=>s+v,0)/a.length:NaN; summary.innerHTML=`<div class='metric'><b>Selected</b><br>${{selected.size||'All'}}</div><div class='metric'><b>Visible</b><br>${{data.length}}</div><div class='metric'><b>Mean ${{xKey}}</b><br>${{Number.isFinite(mean(xvals))?mean(xvals).toPrecision(5):'N/A'}}</div><div class='metric'><b>Mean ${{yKey}}</b><br>${{Number.isFinite(mean(yvals))?mean(yvals).toPrecision(5):'N/A'}}</div>`;
 const cols=[entity,xKey,yKey,...(scoreKey?[scoreKey]:[])]; thead.innerHTML='<tr>'+cols.map(c=>`<th>${{c}}</th>`).join('')+'</tr>'; tbody.innerHTML=rows.slice(0,500).map(r=>'<tr>'+cols.map(c=>`<td title="${{String(r[c]??'').replace(/"/g,'&quot;')}}">${{r[c]??''}}</td>`).join('')+'</tr>').join('');}}
svg.setAttribute('viewBox',`0 0 ${{W}} ${{H}}`); for(let i=0;i<=5;i++){{let x=M.l+i*(W-M.l-M.r)/5,y=M.t+i*(H-M.t-M.b)/5;svg.append(el('line',{{x1:x,y1:M.t,x2:x,y2:H-M.b,class:'gridline'}}));svg.append(el('line',{{x1:M.l,y1:y,x2:W-M.r,y2:y,class:'gridline'}}));}}
svg.append(el('line',{{x1:M.l,y1:H-M.b,x2:W-M.r,y2:H-M.b,class:'axis'}}));svg.append(el('line',{{x1:M.l,y1:M.t,x2:M.l,y2:H-M.b,class:'axis'}}));
const xt=el('text',{{x:(M.l+W-M.r)/2,y:H-10,'text-anchor':'middle',fill:'#cbd5e1'}});xt.textContent=xKey;svg.append(xt); const yt=el('text',{{x:14,y:(M.t+H-M.b)/2,transform:`rotate(-90 14 ${{(M.t+H-M.b)/2}})`,'text-anchor':'middle',fill:'#cbd5e1'}});yt.textContent=yKey;svg.append(yt);
data.forEach((d,i)=>{{const c=el('circle',{{cx:sx(d[xKey]),cy:sy(d[yKey]),r:4.2,fill:colour(d),opacity:.72,class:'point','data-i':i}});c.addEventListener('click',e=>{{e.stopPropagation();push();selected.has(i)?selected.delete(i):selected.add(i);update()}});c.addEventListener('mousemove',e=>{{tip.style.display='block';tip.style.left=(e.offsetX+14)+'px';tip.style.top=(e.offsetY+8)+'px';tip.innerHTML=`<b>${{d[entity]}}</b><br>${{xKey}}: ${{d[xKey]}}<br>${{yKey}}: ${{d[yKey]}}${{scoreKey?'<br>'+scoreKey+': '+d[scoreKey]:''}}`}});c.addEventListener('mouseleave',()=>tip.style.display='none');svg.append(c)}});
let start=null,brush=null;svg.addEventListener('pointerdown',e=>{{if(e.target.classList.contains('point'))return;const r=svg.getBoundingClientRect();start={{x:(e.clientX-r.left)*W/r.width,y:(e.clientY-r.top)*H/r.height}};brush=el('rect',{{x:start.x,y:start.y,width:0,height:0,class:'brush'}});svg.append(brush);svg.setPointerCapture(e.pointerId)}});svg.addEventListener('pointermove',e=>{{if(!start||!brush)return;const r=svg.getBoundingClientRect(),x=(e.clientX-r.left)*W/r.width,y=(e.clientY-r.top)*H/r.height;brush.setAttribute('x',Math.min(x,start.x));brush.setAttribute('y',Math.min(y,start.y));brush.setAttribute('width',Math.abs(x-start.x));brush.setAttribute('height',Math.abs(y-start.y))}});svg.addEventListener('pointerup',e=>{{if(!start||!brush)return;const x=Number(brush.getAttribute('x')),y=Number(brush.getAttribute('y')),w=Number(brush.getAttribute('width')),h=Number(brush.getAttribute('height'));brush.remove();brush=null;start=null;if(w<3||h<3)return;setSel(data.map((d,i)=>({{i,x:sx(d[xKey]),y:sy(d[yKey])}})).filter(p=>p.x>=x&&p.x<=x+w&&p.y>=y&&p.y<=y+h).map(p=>p.i))}});
root.querySelectorAll('button').forEach(b=>b.onclick=()=>{{const a=b.dataset.act;if(a==='clear')setSel([]);if(a==='all')setSel(data.map((_,i)=>i));if(a==='invert')setSel(data.map((_,i)=>i).filter(i=>!selected.has(i)));if(a==='undo'&&undo.length){{redo.push([...selected]);selected=new Set(undo.pop());update()}}if(a==='redo'&&redo.length){{undo.push([...selected]);selected=new Set(redo.pop());update()}}if(a==='csv'){{const rows=selected.size?[...selected].map(i=>data[i]):data;const cols=Object.keys(rows[0]||{{}}),esc=v=>'"'+String(v??'').replace(/"/g,'""')+'"',csv=[cols.map(esc).join(','),...rows.map(r=>cols.map(c=>esc(r[c])).join(','))].join('\n'),u=URL.createObjectURL(new Blob([csv],{{type:'text/csv'}})),link=document.createElement('a');link.href=u;link.download={json.dumps(module_key + '_reactive_selection.csv')};link.click();URL.revokeObjectURL(u)}}}});update();
}})();</script></body></html>"""
    # Use an iframe rather than st.html. st.html injects the component CSS into
    # the application document; the component's generic ``svg`` selector previously
    # enlarged Streamlit heading anchors and metric help icons across the page.
    st.iframe(html_block, width="stretch", height=590, tab_index=0)
    st.caption(
        "This browser-side canvas performs click and drag-box cross-filtering without a Streamlit rerun. "
        "The server-side scientific result remains immutable; use the regular linked selector to persist a selection into run provenance."
    )


def render_selection_sync(module_key: str, *, key: str) -> None:
    st.markdown("#### Linked selection history and synchronized viewer state")
    current = get_linked_selection(module_key)
    history = linked_selection_history(module_key)
    c1, c2, c3 = st.columns(3)
    if c1.button("Undo selection", key=f"{key}_undo", width="stretch"):
        undo_linked_selection(module_key); st.rerun()
    if c2.button("Redo selection", key=f"{key}_redo", width="stretch"):
        redo_linked_selection(module_key); st.rerun()
    if c3.button("Clear selection", key=f"{key}_clear", width="stretch"):
        clear_linked_selection(module_key); st.rerun()
    smart_json(current or {"status": "No linked selection"}, title="Current linked context", key=f"{key}_current")
    if history:
        smart_dataframe(pd.DataFrame(history), height=220, key=f"{key}_session_history")
    persistent = list_selection_history(PROJECT_ROOT, module_key)
    if not persistent.empty:
        scientific_table(persistent.drop(columns=["values_json"], errors="ignore"), key=f"{key}_persistent", height=260, file_name=f"{module_key}_selection_history.csv")

    state = get_viewer_sync_state(PROJECT_ROOT, module_key)
    with st.form(f"{key}_viewer_sync"):
        cols = st.columns(4)
        entity = cols[0].text_input("Shared entity/sample", value=str(state.get("entity", "")))
        region = cols[1].text_input("Region/residue/slide coordinate", value=str(state.get("region", "")))
        timepoint = cols[2].text_input("Shared time point", value=str(state.get("timepoint", "")))
        colour_scale = cols[3].text_input("Shared colour scale", value=str(state.get("colour_scale", "Viridis")))
        zoom = st.slider("Synchronized zoom", 0.1, 20.0, float(state.get("zoom", 1.0) or 1.0), 0.1)
        if st.form_submit_button("Save synchronized viewer state", width="stretch"):
            save_viewer_sync_state(project_root=PROJECT_ROOT, module_key=module_key, state={
                "entity": entity, "region": region, "timepoint": timepoint,
                "colour_scale": colour_scale, "zoom": zoom,
            })
            st.success("Shared viewer state saved.")


def render_uncertainty_and_lod(frame: pd.DataFrame, *, key: str) -> None:
    st.markdown("#### Uncertainty-native and large-data rendering")
    profile = uncertainty_profile(frame)
    if profile.empty:
        st.info("No explicit lower/upper uncertainty pair was detected. Add estimate, CI-low and CI-high fields to activate interval-native rendering.")
    else:
        metric_cards([
            ("Interval models", len(profile), "Detected estimate/lower/upper groups"),
            ("Mean coverage", f"{profile['coverage_pct'].mean():.1f}%", "Rows with valid intervals"),
            ("Median width", f"{pd.to_numeric(profile['median_width'], errors='coerce').median():.4g}", "Across interval groups"),
            ("Integrity", "Passed" if (pd.to_numeric(profile['estimate_inside_pct'], errors='coerce').fillna(100) >= 95).all() else "Review", "Estimate inside bounds"),
        ])
        scientific_table(profile, key=f"{key}_uncertainty", height=260, file_name="uncertainty_profile.csv")
    sample, manifest = progressive_sample(frame, limit=5000)
    smart_json(manifest.__dict__, title="Progressive rendering manifest", key=f"{key}_lod_manifest")
    st.caption("The deterministic sampler preserves active selections, score extrema and stratified groups instead of taking a biased first-N preview.")


def render_point_provenance(module_key: str, run_state: Any, *, key: str) -> None:
    st.markdown("#### Point-level visual provenance")
    if run_state is None or pd.DataFrame(run_state.result).empty:
        st.info("Complete an analysis to create point-level provenance records.")
        return
    frame = pd.DataFrame(run_state.result)
    entity = infer_entity_column(frame)
    if not entity:
        st.info("No stable entity identifier was detected in the current result.")
        return
    options = frame[entity].dropna().astype(str).drop_duplicates().head(5000).tolist()
    chosen = st.selectbox("Entity", options, key=f"{key}_entity")
    row = frame.loc[frame[entity].astype(str) == str(chosen)].head(1)
    if row.empty:
        return
    smart_json(row.iloc[0].replace({np.nan: None}).to_dict(), title="Source result row", key=f"{key}_source_row")
    chart_key = st.text_input("Figure/chart key", value=f"{module_key}_primary", key=f"{key}_chart")
    if st.button("Register immutable point provenance", key=f"{key}_save", width="stretch"):
        provenance_id = save_visual_provenance(
            project_root=PROJECT_ROOT,
            module_key=module_key,
            run_id=_run_id(run_state),
            chart_key=chart_key,
            entity_id=str(chosen),
            source_row=row.iloc[0].replace({np.nan: None}).to_dict(),
            transformations=getattr(run_state, "parameters", {}) or {},
            figure_refs=[chart_key],
        )
        st.success(f"Point provenance saved: {provenance_id}")
    records = list_visual_provenance(PROJECT_ROOT, module_key)
    if not records.empty:
        scientific_table(records.drop(columns=["source_row_json", "transformation_json", "figure_refs_json"], errors="ignore"), key=f"{key}_records", height=280, file_name=f"{module_key}_visual_provenance.csv")


def render_collaborative_review(module_key: str, run_state: Any, *, key: str) -> None:
    st.markdown("#### Collaborative scientific review")
    entity_default = "module-level"
    if run_state is not None:
        frame = pd.DataFrame(run_state.result)
        entity = infer_entity_column(frame)
        if entity and not frame.empty:
            entity_default = str(frame[entity].dropna().astype(str).iloc[0]) if frame[entity].notna().any() else entity_default
    with st.form(f"{key}_new_thread"):
        cols = st.columns(3)
        title = cols[0].text_input("Review title", value="Scientific result review")
        entity_id = cols[1].text_input("Entity", value=entity_default)
        assignee = cols[2].text_input("Assignee", value="reviewer")
        author = st.text_input("Created by", value="local-reviewer")
        if st.form_submit_button("Create review thread", width="stretch"):
            thread_id = create_review_thread(
                project_root=PROJECT_ROOT, module_key=module_key, run_id=_run_id(run_state),
                entity_id=entity_id, title=title, created_by=author, assignee=assignee,
            )
            st.success(f"Review thread created: {thread_id}")
    threads = list_review_threads(PROJECT_ROOT, module_key)
    if threads.empty:
        st.info("No review threads yet.")
        return
    labels = {f"{r['title']} · {r['entity_id']} · {r['status']} · {r['thread_id']}": r['thread_id'] for _, r in threads.iterrows()}
    label = st.selectbox("Review thread", list(labels), key=f"{key}_thread")
    thread_id = labels[label]
    selected = threads.loc[threads["thread_id"] == thread_id].iloc[0]
    c1, c2 = st.columns(2)
    statuses = ["Open", "In review", "Changes requested", "Approved", "Rejected", "Closed"]
    current_status = str(selected["status"])
    status_index = statuses.index(current_status) if current_status in statuses else 0
    status = c1.selectbox("Status", statuses, index=status_index, key=f"{key}_status")
    assignee = c2.text_input("Assigned reviewer", value=str(selected["assignee"]), key=f"{key}_assignee")
    if st.button("Update assignment/status", key=f"{key}_update", width="stretch"):
        update_review_thread(project_root=PROJECT_ROOT, thread_id=thread_id, status=status, assignee=assignee)
        st.success("Review thread updated.")
    with st.form(f"{key}_comment"):
        author = st.text_input("Comment author", value="local-reviewer")
        decision = st.selectbox("Comment type", ["Comment", "Question", "Evidence requested", "Approve", "Reject"])
        body = st.text_area("Comment", placeholder="Record evidence, uncertainty, requested change or approval rationale.")
        if st.form_submit_button("Add threaded comment", width="stretch"):
            try:
                comment_id = add_review_comment(project_root=PROJECT_ROOT, thread_id=thread_id, author=author, body=body, decision=decision)
                st.success(f"Comment added: {comment_id}")
            except Exception as exc:
                st.error(str(exc))
    comments = list_review_comments(PROJECT_ROOT, thread_id)
    if not comments.empty:
        smart_dataframe(comments, height=300, key=f"{key}_comments")


def render_figure_layout_editor(module: Any, run_state: Any, data: pd.DataFrame, *, key: str) -> None:
    st.markdown("#### Journal figure layout editor")
    if run_state is None:
        st.info("Complete an analysis before composing a multi-panel figure.")
        return
    visuals = build_scientific_visuals(
        module.key,
        data=data,
        result=run_state.result,
        secondary=run_state.secondary,
        extras=run_state.extras,
    )
    titles = [str(visual.title) for visual in visuals]
    if not titles:
        st.info("No visual panels are available for this run.")
        return
    preset = st.selectbox("Journal/layout preset", list(JOURNAL_PRESETS), key=f"{key}_preset")
    selected = st.multiselect("Panels", titles, default=titles[: min(4, len(titles))], key=f"{key}_panels")
    c1, c2 = st.columns(2)
    name = c1.text_input("Figure name", value=f"{module.title} multi-panel figure", key=f"{key}_name")
    caption = c2.text_area("Caption", value=f"Multi-panel research figure generated from {_run_id(run_state) or 'the current run'}.", key=f"{key}_caption")
    methods = st.text_area("Methods note", value="Panels use the current deterministic analysis result and bounded visual previews. Verify all statistical claims before submission.", key=f"{key}_methods")
    panel_payload = []
    for title in selected:
        visual = next((item for item in visuals if str(item.title) == title), None)
        values: list[float] = []
        if visual is not None:
            vf = pd.DataFrame(visual.data)
            numeric = _numeric_columns(vf)
            if numeric:
                values = pd.to_numeric(vf[numeric[0]], errors="coerce").dropna().head(20).astype(float).tolist()
        panel_payload.append({"title": title, "values": values})
    cols = st.columns(2)
    if cols[0].button("Save figure layout", key=f"{key}_save", disabled=not panel_payload, width="stretch"):
        layout_id = save_figure_layout(
            project_root=PROJECT_ROOT, module_key=module.key, run_id=_run_id(run_state),
            name=name, preset=preset, panels=panel_payload, caption=caption, methods=methods,
        )
        st.success(f"Figure layout saved: {layout_id}")
    if panel_payload:
        bundle = build_figure_layout_bundle(
            module_key=module.key, layout_name=name, preset=preset, panels=panel_payload,
            caption=caption, methods=methods, boundary=str(module.boundary),
        )
        cols[1].download_button(
            "Download editable layout ZIP", bundle, file_name=f"{module.key}_figure_layout.zip",
            mime="application/zip", key=f"{key}_download", width="stretch",
        )
    layouts = list_figure_layouts(PROJECT_ROOT, module.key)
    if not layouts.empty:
        scientific_table(layouts.drop(columns=["panel_json"], errors="ignore"), key=f"{key}_layouts", height=260, file_name=f"{module.key}_figure_layouts.csv")


def render_reactive_scientific_workspace(*, module: Any, data: pd.DataFrame, run_state: Any, key: str) -> None:
    st.caption(
        "Step 131 interaction layer: browser-side no-rerun cross-filtering, deterministic progressive rendering, "
        "uncertainty audit, point provenance, synchronized viewers, threaded review and journal figure layout."
    )
    result = pd.DataFrame() if run_state is None else pd.DataFrame(run_state.result)
    tabs = st.tabs(["Reactive canvas", "Selection & sync", "Uncertainty & LOD", "Point provenance", "Collaborative review", "Figure layout"])
    with tabs[0]:
        render_client_reactive_canvas(module.key, result, key=f"{key}_canvas")
    with tabs[1]:
        render_selection_sync(module.key, key=f"{key}_selection")
    with tabs[2]:
        render_uncertainty_and_lod(result, key=f"{key}_uncertainty")
    with tabs[3]:
        render_point_provenance(module.key, run_state, key=f"{key}_provenance")
    with tabs[4]:
        render_collaborative_review(module.key, run_state, key=f"{key}_collaboration")
    with tabs[5]:
        render_figure_layout_editor(module, run_state, data, key=f"{key}_figure")


def render_global_interaction_center() -> None:
    st.markdown("### Real-Time Scientific Canvas & Collaboration Center")
    threads = list_review_threads(PROJECT_ROOT)
    layouts = list_figure_layouts(PROJECT_ROOT)
    provenance = list_visual_provenance(PROJECT_ROOT)
    selections = list_selection_history(PROJECT_ROOT)
    metric_cards([
        ("Review threads", len(threads), "Persistent team review queue"),
        ("Figure layouts", len(layouts), "Saved journal/presentation compositions"),
        ("Point provenance", len(provenance), "Immutable selected-result lineage"),
        ("Selection events", len(selections), "Cross-visual interaction history"),
    ])
    tabs = st.tabs(["Review queue", "Figure layouts", "Visual provenance", "Selection history"])
    with tabs[0]:
        scientific_table(threads, key="global_review_threads", height=480, file_name="collaborative_review_threads.csv") if not threads.empty else st.info("No review threads.")
    with tabs[1]:
        scientific_table(layouts.drop(columns=["panel_json"], errors="ignore"), key="global_figure_layouts", height=480, file_name="figure_layout_registry.csv") if not layouts.empty else st.info("No figure layouts.")
    with tabs[2]:
        scientific_table(provenance.drop(columns=["source_row_json", "transformation_json", "figure_refs_json"], errors="ignore"), key="global_visual_provenance", height=480, file_name="visual_provenance_registry.csv") if not provenance.empty else st.info("No point provenance records.")
    with tabs[3]:
        scientific_table(selections.drop(columns=["values_json"], errors="ignore"), key="global_selection_history", height=480, file_name="selection_history.csv") if not selections.empty else st.info("No persisted selection events.")
