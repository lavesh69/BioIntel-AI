from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Iterable

try:
    import streamlit as st
except ModuleNotFoundError:  # backend and release tests may run without the UI runtime
    from biointel.education._streamlit_compat import st


@dataclass(frozen=True)
class ProductProfile:
    key: str
    label: str
    icon: str
    accent: str
    accent_2: str
    glow: str
    visual: str
    tagline: str


PROFILES: dict[str, ProductProfile] = {
    "connect": ProductProfile("connect", "BIOINTEL CONNECT", "◉", "#4fe4ff", "#708cff", "rgba(79,228,255,.28)", "network", "Scientific collaboration, communities and trusted communication"),
    "shiro": ProductProfile("shiro", "SHIRO AI", "✦", "#8b7cff", "#35e8ff", "rgba(139,124,255,.30)", "orb", "Evidence-grounded intelligence with project-isolated citations"),
    "studio": ProductProfile("studio", "BIOINTEL STUDIO", "✧", "#7dff87", "#29d5ff", "rgba(125,255,135,.24)", "helix", "Research operations, bioinformatics and evidence-ready workbenches"),
    "home": ProductProfile("home", "EDUCATION OS", "⌂", "#4fe4ff", "#6d8cff", "rgba(79,228,255,.25)", "dashboard", "A role-aware academic operating system"),
    "classroom": ProductProfile("classroom", "CLASSROOM", "▦", "#38e3ad", "#4fa7ff", "rgba(56,227,173,.25)", "calendar", "Classes, assignments, attendance and academic progress"),
    "pulse": ProductProfile("pulse", "SCIENCE PULSE", "⌁", "#56f0c5", "#45a3ff", "rgba(86,240,197,.26)", "pulse", "Live research intelligence and scientific evidence signals"),
    "academy": ProductProfile("academy", "ACADEMY", "▷", "#41dff6", "#7a78ff", "rgba(65,223,246,.28)", "academy", "Immersive courses, lectures, laboratories and credentials"),
    "universe": ProductProfile("universe", "EDUCATION UNIVERSE", "◎", "#a678ff", "#36e3ff", "rgba(166,120,255,.28)", "universe", "Connected learning, research and scientific simulation modules"),
    "examinations": ProductProfile("examinations", "EXAMINATION COMMAND", "✓", "#ffcb6b", "#ff7da4", "rgba(255,203,107,.24)", "exam", "Secure assessment, monitoring, grading and moderation"),
    "intelligence": ProductProfile("intelligence", "INTELLIGENCE HUB", "◇", "#a7ff68", "#38d4ff", "rgba(167,255,104,.22)", "brain", "Adaptive learning, Shiro tutoring and evidence-led intervention"),
    "institution": ProductProfile("institution", "INSTITUTION CENTER", "▤", "#48e2ff", "#2be09d", "rgba(72,226,255,.22)", "institution", "Campus governance, identity, storage and platform operations"),
    "visuals": ProductProfile("visuals", "VISUAL COMMAND", "◫", "#5be5ff", "#a074ff", "rgba(91,229,255,.24)", "dashboard", "Interactive academic and scientific visual workspaces"),
    "desktop": ProductProfile("desktop", "EDUCATION DESKTOP", "▣", "#4fe4ff", "#6d8cff", "rgba(79,228,255,.25)", "desktop", "Desktop-first academic workflows with secured sessions"),
    "completion": ProductProfile("completion", "FINAL COMPLETION", "◆", "#55e6a5", "#4fe4ff", "rgba(85,230,165,.25)", "institution", "Production qualification, academic assurance and external evidence"),
    "autonomy": ProductProfile("autonomy", "LOCAL AUTONOMY", "◉", "#6df7c1", "#54a8ff", "rgba(109,247,193,.25)", "network", "Governed evidence retrieval, scheduling and resilient local operations"),
    "quality": ProductProfile("quality", "ACADEMIC QUALITY", "◫", "#ffd166", "#59d9ff", "rgba(255,209,102,.24)", "dashboard", "Outcome evidence, psychometrics and transparent learner support"),
    "runtime": ProductProfile("runtime", "RUNTIME & RESEARCH", "◌", "#4fe4ff", "#7d8cff", "rgba(79,228,255,.25)", "network", "Real-time events, semantic evidence, model runtimes and scientific providers"),
}


PRODUCT_V8_CSS = r"""
<style>
:root{
  --bx-accent:#4fe4ff;--bx-accent-2:#6d8cff;--bx-glow:rgba(79,228,255,.25);
  --bx-bg:#050d19;--bx-panel:rgba(9,22,39,.82);--bx-panel-2:rgba(14,31,53,.92);
  --bx-border:rgba(145,188,230,.18);--bx-text:#f3f8ff;--bx-muted:#9fb3ca;
}
[data-testid="stAppViewContainer"]{
 background:
 radial-gradient(circle at 8% -8%,var(--bx-glow),transparent 34rem),
 radial-gradient(circle at 91% 7%,color-mix(in srgb,var(--bx-accent-2) 18%,transparent),transparent 36rem),
 linear-gradient(180deg,#050d19 0%,#071321 45%,#050c16 100%)!important;
}
[data-testid="stAppViewContainer"]:before{
 content:"";position:fixed;inset:0;pointer-events:none;opacity:.22;z-index:0;
 background-image:linear-gradient(rgba(126,176,226,.055) 1px,transparent 1px),linear-gradient(90deg,rgba(126,176,226,.055) 1px,transparent 1px);
 background-size:42px 42px;mask-image:linear-gradient(to bottom,black,transparent 78%);
}
[data-testid="stMainBlockContainer"]{position:relative;z-index:1;max-width:1580px!important;padding-top:1rem!important}
[data-testid="stSidebar"]{min-width:21rem!important;max-width:21rem!important;background:linear-gradient(180deg,rgba(5,13,25,.985),rgba(7,20,35,.985))!important;border-right:1px solid var(--bx-border)!important}
[data-testid="stSidebarNav"] a{border:1px solid rgba(145,188,230,.16)!important;border-radius:14px!important;margin:.24rem .3rem!important;min-height:3rem!important;background:linear-gradient(145deg,rgba(17,34,56,.7),rgba(8,21,37,.72))!important;transition:.18s ease!important}
[data-testid="stSidebarNav"] a:hover{transform:translateX(3px);border-color:color-mix(in srgb,var(--bx-accent) 58%,transparent)!important;background:linear-gradient(145deg,color-mix(in srgb,var(--bx-accent) 13%,rgba(17,34,56,.8)),rgba(8,21,37,.9))!important}
[data-testid="stSidebarNav"] a[aria-current="page"]{border-color:var(--bx-accent)!important;box-shadow:inset 3px 0 0 var(--bx-accent),0 8px 28px var(--bx-glow)!important}
[data-testid="stSidebarNav"] a span{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;line-height:1.22!important;font-size:.93rem!important}
.bx-hero{position:relative;overflow:hidden;display:grid;grid-template-columns:minmax(0,1.6fr) minmax(300px,.72fr);gap:1.2rem;min-height:265px;padding:1.6rem 1.7rem;margin:.1rem 0 1.05rem;border:1px solid color-mix(in srgb,var(--bx-accent) 28%,var(--bx-border));border-radius:28px;background:linear-gradient(132deg,rgba(17,38,65,.96),rgba(7,19,34,.94) 58%,color-mix(in srgb,var(--bx-accent-2) 12%,rgba(7,19,34,.94)));box-shadow:0 28px 80px rgba(0,0,0,.34),inset 0 1px 0 rgba(255,255,255,.04)}
.bx-hero:before{content:"";position:absolute;inset:0;background:linear-gradient(105deg,transparent 40%,color-mix(in srgb,var(--bx-accent) 9%,transparent));pointer-events:none}
.bx-hero-copy{position:relative;z-index:2;display:flex;flex-direction:column;justify-content:center;align-items:flex-start}
.bx-eyebrow{display:flex;align-items:center;gap:.55rem;color:var(--bx-accent);font-size:.72rem;font-weight:900;letter-spacing:.17em;text-transform:uppercase;margin-bottom:.65rem}
.bx-eyebrow i{display:inline-grid;place-items:center;width:1.7rem;height:1.7rem;border-radius:9px;font-style:normal;color:#03101a;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));box-shadow:0 0 24px var(--bx-glow)}
.bx-hero h1{font-size:clamp(2rem,3.6vw,3.45rem)!important;line-height:1.02!important;letter-spacing:-.045em!important;color:var(--bx-text)!important;margin:0 0 .7rem!important;max-width:900px}
.bx-hero p{font-size:1.02rem;line-height:1.62;color:var(--bx-muted);max-width:780px;margin:0}
.bx-hero-chips{display:flex;flex-wrap:wrap;gap:.48rem;margin-top:1.05rem}
.bx-chip{display:inline-flex;align-items:center;gap:.35rem;padding:.38rem .68rem;border:1px solid var(--bx-border);border-radius:999px;color:#dcecff;background:rgba(255,255,255,.045);font-size:.75rem;font-weight:700}
.bx-chip b{color:var(--bx-accent);font-weight:900}
.bx-visual{position:relative;min-height:225px;display:grid;place-items:center;border-left:1px solid rgba(145,188,230,.12)}
.bx-orbit{position:absolute;border:1px solid color-mix(in srgb,var(--bx-accent) 35%,transparent);border-radius:50%;animation:bx-spin 18s linear infinite}
.bx-orbit.o1{width:205px;height:205px}.bx-orbit.o2{width:145px;height:145px;animation-direction:reverse;animation-duration:13s}.bx-orbit.o3{width:82px;height:82px;animation-duration:9s}
.bx-orbit:after{content:"";position:absolute;width:10px;height:10px;border-radius:50%;top:12%;left:12%;background:var(--bx-accent);box-shadow:0 0 20px var(--bx-accent)}
.bx-core{position:relative;z-index:3;display:grid;place-items:center;width:78px;height:78px;border-radius:24px;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));color:#04121e;font-size:2rem;font-weight:950;box-shadow:0 0 60px var(--bx-glow);transform:rotate(-6deg)}
.bx-data-node{position:absolute;z-index:4;padding:.35rem .55rem;border-radius:10px;border:1px solid var(--bx-border);background:rgba(5,16,29,.86);color:#dcecff;font-size:.62rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;box-shadow:0 12px 30px rgba(0,0,0,.25)}
.bx-data-node.n1{top:13%;right:4%}.bx-data-node.n2{bottom:12%;left:5%}.bx-data-node.n3{right:9%;bottom:25%}
.bx-wave{position:absolute;inset:25% 3%;opacity:.75;background:repeating-linear-gradient(90deg,transparent 0 10px,var(--bx-accent) 11px 13px,transparent 14px 24px);clip-path:polygon(0 50%,5% 50%,8% 35%,12% 74%,16% 42%,21% 50%,28% 50%,32% 20%,36% 82%,41% 39%,46% 50%,55% 50%,60% 32%,64% 67%,69% 45%,75% 50%,100% 50%);filter:drop-shadow(0 0 10px var(--bx-accent))}
.bx-grid-visual{position:absolute;width:220px;height:150px;border:1px solid var(--bx-border);border-radius:18px;background-image:linear-gradient(var(--bx-border) 1px,transparent 1px),linear-gradient(90deg,var(--bx-border) 1px,transparent 1px);background-size:44px 30px;transform:perspective(520px) rotateX(58deg) rotateZ(-6deg);box-shadow:0 30px 50px rgba(0,0,0,.4),0 0 35px var(--bx-glow)}
.bx-helix{position:absolute;width:190px;height:210px;filter:drop-shadow(0 0 12px var(--bx-glow))}
.bx-helix:before,.bx-helix:after{content:"";position:absolute;left:50%;top:5%;width:3px;height:90%;background:repeating-linear-gradient(to bottom,var(--bx-accent) 0 10px,transparent 10px 22px);border-radius:10px;transform-origin:center;animation:bx-helix 5s ease-in-out infinite}
.bx-helix:after{background:repeating-linear-gradient(to bottom,var(--bx-accent-2) 0 10px,transparent 10px 22px);animation-delay:-2.5s}
.bx-module-band{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem;margin:.85rem 0 1.05rem}
.bx-module-tile{position:relative;overflow:hidden;min-height:106px;padding:.9rem;border:1px solid var(--bx-border);border-radius:18px;background:linear-gradient(145deg,rgba(17,36,60,.88),rgba(8,21,38,.86));box-shadow:0 12px 34px rgba(0,0,0,.2)}
.bx-module-tile:after{content:"";position:absolute;right:-25px;bottom:-28px;width:90px;height:90px;border-radius:50%;background:radial-gradient(circle,var(--bx-glow),transparent 68%)}
.bx-module-tile strong{position:relative;z-index:1;display:block;color:var(--bx-text);font-size:.92rem;margin-bottom:.28rem}.bx-module-tile small{position:relative;z-index:1;color:var(--bx-muted);font-size:.73rem;line-height:1.4}.bx-module-tile span{position:relative;z-index:1;color:var(--bx-accent);font-size:.66rem;font-weight:900;letter-spacing:.1em;text-transform:uppercase}
.bx-course-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;margin:.8rem 0}
.bx-course-card{position:relative;overflow:hidden;min-height:285px;border:1px solid var(--bx-border);border-radius:24px;background:linear-gradient(150deg,rgba(14,32,55,.96),rgba(6,18,32,.96));box-shadow:0 18px 45px rgba(0,0,0,.23)}
.bx-course-cover{position:relative;height:118px;padding:1rem 1.1rem;background:linear-gradient(125deg,color-mix(in srgb,var(--course-a) 75%,#071321),color-mix(in srgb,var(--course-b) 58%,#071321));overflow:hidden}
.bx-course-cover:before{content:"";position:absolute;right:-26px;top:-42px;width:150px;height:150px;border:1px solid rgba(255,255,255,.25);border-radius:50%;box-shadow:0 0 0 28px rgba(255,255,255,.035),0 0 0 58px rgba(255,255,255,.025)}
.bx-course-cover:after{content:"";position:absolute;left:0;right:0;bottom:0;height:32px;background:linear-gradient(transparent,rgba(5,15,28,.72))}
.bx-course-symbol{position:absolute;right:1rem;bottom:.72rem;font-size:2.6rem;color:white;opacity:.88;filter:drop-shadow(0 8px 22px rgba(0,0,0,.35))}
.bx-course-kicker{font-size:.66rem;font-weight:900;letter-spacing:.13em;text-transform:uppercase;color:rgba(255,255,255,.78)}
.bx-course-cover h3{position:relative;z-index:2;margin:.38rem 0;color:#fff;font-size:1.22rem;max-width:78%;line-height:1.18}
.bx-course-body{padding:1rem 1.1rem 1.1rem}.bx-course-meta{display:flex;flex-wrap:wrap;gap:.42rem;margin-bottom:.72rem}.bx-course-meta span{font-size:.7rem;padding:.28rem .5rem;border-radius:999px;border:1px solid var(--bx-border);color:#d9e9fb;background:rgba(255,255,255,.035)}
.bx-course-progress-label{display:flex;justify-content:space-between;color:#dceaff;font-size:.74rem;font-weight:750;margin-bottom:.35rem}.bx-course-progress{height:.55rem;border-radius:999px;background:rgba(255,255,255,.075);overflow:hidden}.bx-course-progress i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--course-a),var(--course-b));box-shadow:0 0 18px color-mix(in srgb,var(--course-a) 50%,transparent)}
.bx-course-footer{display:flex;justify-content:space-between;align-items:center;margin-top:.8rem;color:var(--bx-muted);font-size:.72rem}.bx-course-footer b{color:var(--bx-accent)}
[data-testid="stVerticalBlockBorderWrapper"]{background:linear-gradient(145deg,rgba(13,29,50,.80),rgba(7,20,36,.79))!important;border-color:var(--bx-border)!important;box-shadow:0 13px 38px rgba(0,0,0,.17)}
[data-testid="stMetric"]{background:linear-gradient(145deg,rgba(18,38,64,.72),rgba(8,22,39,.72));border-radius:16px;padding:.72rem .82rem!important;border:1px solid rgba(145,188,230,.12)}
[data-testid="stMetricValue"]{color:var(--bx-text)!important;font-weight:850!important}
[data-baseweb="tab-list"]{background:rgba(6,18,32,.78)!important;border:1px solid var(--bx-border)!important;border-radius:15px!important;padding:.28rem!important}
[data-baseweb="tab"][aria-selected="true"]{background:color-mix(in srgb,var(--bx-accent) 14%,transparent)!important;color:var(--bx-accent)!important;box-shadow:inset 0 -2px 0 var(--bx-accent)}
.stButton>button,.stDownloadButton>button,[data-testid="stPageLink"] a{border-radius:13px!important;border-color:var(--bx-border)!important;background:linear-gradient(145deg,rgba(18,36,59,.8),rgba(8,21,37,.86))!important;color:#eaf5ff!important}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stPageLink"] a:hover{border-color:var(--bx-accent)!important;box-shadow:0 10px 28px var(--bx-glow)!important;transform:translateY(-1px)}
.stButton>button[kind="primary"]{background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2))!important;color:#03111c!important;border:0!important}
[data-testid="stDataFrame"]{border:1px solid var(--bx-border)!important;border-radius:18px!important;overflow:hidden!important}
@keyframes bx-spin{to{transform:rotate(360deg)}}
@keyframes bx-helix{0%,100%{transform:translateX(-50%) rotate(22deg) scaleY(.96)}50%{transform:translateX(-50%) rotate(-22deg) scaleY(1.03)}}

/* Phase 9 full visibility pass */
html{scroll-behavior:smooth}
[data-testid="stHeader"]{background:linear-gradient(180deg,rgba(5,13,25,.96),rgba(5,13,25,.62),transparent)!important}
[data-testid="stMainBlockContainer"] h2{margin-top:1.45rem!important;padding:.7rem .85rem!important;border-left:4px solid var(--bx-accent)!important;border-radius:0 14px 14px 0!important;background:linear-gradient(90deg,color-mix(in srgb,var(--bx-accent) 12%,transparent),transparent 75%)!important;color:var(--bx-text)!important;letter-spacing:-.02em!important}
[data-testid="stMainBlockContainer"] h3{color:#eaf5ff!important;letter-spacing:-.012em!important}
[data-testid="stMainBlockContainer"] p,[data-testid="stCaptionContainer"]{color:var(--bx-muted)!important}
[data-testid="stWidgetLabel"] p{color:#dcecff!important;font-weight:750!important}
[data-baseweb="input"]>div,[data-baseweb="textarea"]>div,[data-baseweb="select"]>div,[data-testid="stNumberInputContainer"],[data-testid="stDateInput"]>div{background:rgba(5,16,29,.88)!important;border-color:rgba(145,188,230,.24)!important;border-radius:13px!important}
[data-baseweb="input"]>div:focus-within,[data-baseweb="textarea"]>div:focus-within,[data-baseweb="select"]>div:focus-within{border-color:var(--bx-accent)!important;box-shadow:0 0 0 3px var(--bx-glow)!important}
[data-testid="stFileUploader"]{padding:.9rem!important;border:1px dashed color-mix(in srgb,var(--bx-accent) 48%,var(--bx-border))!important;border-radius:18px!important;background:linear-gradient(145deg,rgba(15,34,58,.72),rgba(6,18,32,.72))!important}
[data-testid="stExpander"]{border:1px solid var(--bx-border)!important;border-radius:16px!important;background:linear-gradient(145deg,rgba(14,31,53,.76),rgba(7,20,35,.76))!important;overflow:hidden!important}
[data-testid="stExpander"] summary{font-weight:800!important;color:#eaf5ff!important}
[data-testid="stAlert"]{border:1px solid var(--bx-border)!important;border-radius:16px!important;background:rgba(12,28,48,.86)!important}
[data-testid="stDataEditor"],[data-testid="stDataFrame"]{box-shadow:0 16px 44px rgba(0,0,0,.18)!important}
[data-testid="stPlotlyChart"],[data-testid="stVegaLiteChart"],[data-testid="stPyplotGlobalUse"]{padding:.55rem!important;border:1px solid var(--bx-border)!important;border-radius:18px!important;background:linear-gradient(145deg,rgba(12,29,50,.82),rgba(5,18,32,.84))!important;box-shadow:0 16px 42px rgba(0,0,0,.2)!important}
[data-testid="stRadio"]>div,[data-testid="stCheckbox"]>label,[data-testid="stToggle"]>label{padding:.28rem .38rem;border-radius:10px}
[data-testid="stHorizontalBlock"]{row-gap:.75rem!important}
.bx-status-rail{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem;margin:-.35rem 0 1.15rem}
.bx-status-cell{display:flex;align-items:center;gap:.72rem;min-height:72px;padding:.76rem .85rem;border:1px solid var(--bx-border);border-radius:16px;background:linear-gradient(145deg,rgba(16,34,57,.88),rgba(7,20,35,.86));box-shadow:0 12px 30px rgba(0,0,0,.17)}
.bx-status-icon{display:grid;place-items:center;flex:0 0 2.15rem;height:2.15rem;border-radius:11px;color:#03111c;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));font-weight:950;box-shadow:0 0 22px var(--bx-glow)}
.bx-status-cell strong{display:block;color:#edf7ff;font-size:.82rem}.bx-status-cell small{display:block;color:var(--bx-muted);font-size:.69rem;margin-top:.12rem;line-height:1.35}
.bx-section-shell{margin:.9rem 0;padding:1rem 1.05rem;border:1px solid var(--bx-border);border-radius:20px;background:linear-gradient(145deg,rgba(15,33,56,.82),rgba(6,19,34,.82));box-shadow:0 15px 38px rgba(0,0,0,.18)}
.bx-section-head{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:.7rem}.bx-section-head h3{margin:0!important;color:#f1f8ff!important}.bx-section-head span{font-size:.67rem;letter-spacing:.12em;text-transform:uppercase;color:var(--bx-accent);font-weight:900}
.bx-empty{display:grid;place-items:center;text-align:center;min-height:180px;padding:1.2rem;border:1px dashed color-mix(in srgb,var(--bx-accent) 45%,var(--bx-border));border-radius:18px;background:radial-gradient(circle at 50% 20%,var(--bx-glow),transparent 12rem),rgba(7,20,35,.62)}
.bx-empty b{display:block;color:#eef7ff;font-size:1rem}.bx-empty small{display:block;color:var(--bx-muted);max-width:36rem;margin-top:.3rem}
[data-testid="stPageLink"] a{min-height:3.05rem!important;justify-content:flex-start!important;padding:.7rem .8rem!important}
@media(max-width:1150px){.bx-status-rail{grid-template-columns:repeat(2,minmax(0,1fr))}}

@media(prefers-reduced-motion:reduce){.bx-orbit,.bx-helix:before,.bx-helix:after{animation:none!important}}
@media(max-width:1100px){.bx-hero{grid-template-columns:1fr}.bx-visual{display:none}.bx-module-band{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
"""


def _visual_markup(profile: ProductProfile) -> str:
    if profile.visual == "pulse":
        center = '<div class="bx-wave"></div><div class="bx-core">⌁</div>'
    elif profile.visual in {"calendar", "dashboard", "desktop", "institution", "exam"}:
        center = f'<div class="bx-grid-visual"></div><div class="bx-core">{html.escape(profile.icon)}</div>'
    elif profile.visual == "helix":
        center = '<div class="bx-helix"></div><div class="bx-core">DNA</div>'
    else:
        center = f'<div class="bx-orbit o1"></div><div class="bx-orbit o2"></div><div class="bx-orbit o3"></div><div class="bx-core">{html.escape(profile.icon)}</div>'
    labels = {
        "connect": ("COLLAB", "TRUST", "LIVE"), "shiro": ("RAG", "CITE", "PRIVATE"),
        "studio": ("DATA", "MODELS", "EVIDENCE"), "home": ("TODAY", "PROGRESS", "ACTION"),
        "classroom": ("CLASS", "GRADE", "ATTEND"), "pulse": ("PAPERS", "TRENDS", "ALERTS"),
        "academy": ("COURSES", "LABS", "CERTIFY"), "universe": ("LEARN", "RESEARCH", "SIMULATE"),
        "examinations": ("SECURE", "MONITOR", "GRADE"), "intelligence": ("MASTERY", "SHIRO", "INSIGHT"),
        "institution": ("CAMPUS", "IDENTITY", "OPS"), "visuals": ("MAP", "GRAPH", "EXPLORE"),
        "desktop": ("SESSION", "WORKFLOW", "AUDIT"),
        "completion": ("QUALIFY", "GOVERN", "VERIFY"),
        "autonomy": ("INGEST", "AUTOMATE", "RECOVER"),
        "quality": ("OUTCOMES", "ANALYSE", "IMPROVE"),
        "runtime": ("EVENTS", "RAG", "MODELS"),
    }.get(profile.key, ("DATA", "EVIDENCE", "READY"))
    return f'<div class="bx-visual">{center}<span class="bx-data-node n1">{labels[0]}</span><span class="bx-data-node n2">{labels[1]}</span><span class="bx-data-node n3">{labels[2]}</span></div>'


def apply_product_skin(page_key: str) -> ProductProfile:
    profile = PROFILES.get(page_key, PROFILES["home"])
    st.markdown(PRODUCT_V8_CSS, unsafe_allow_html=True)
    # Phase 10 extends the established product skin rather than replacing it.
    # The local import avoids a module cycle because frontend_v10 reuses profiles.
    try:
        from biointel.ui.frontend_v10 import FRONTEND_V10_CSS
        st.markdown(FRONTEND_V10_CSS, unsafe_allow_html=True)
    except Exception:
        pass
    st.markdown(
        f"<style>:root{{--bx-accent:{profile.accent};--bx-accent-2:{profile.accent_2};--bx-glow:{profile.glow};--edu-cyan:{profile.accent};--edu-blue:{profile.accent_2};}}</style>",
        unsafe_allow_html=True,
    )
    return profile


def render_product_hero(
    page_key: str,
    title: str,
    subtitle: str,
    *,
    eyebrow: str | None = None,
    chips: Iterable[str] = (),
) -> None:
    profile = apply_product_skin(page_key)
    safe_chips = list(chips) or ["Local-first", "Permission-aware", "Evidence trail", "Professional workspace"]
    chips_html = "".join(f'<span class="bx-chip"><b>●</b>{html.escape(str(item))}</span>' for item in safe_chips)
    st.markdown(
        f'''<section class="bx-hero">
          <div class="bx-hero-copy">
            <div class="bx-eyebrow"><i>{html.escape(profile.icon)}</i>{html.escape(eyebrow or profile.label)}</div>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(subtitle)}</p>
            <div class="bx-hero-chips">{chips_html}</div>
          </div>
          {_visual_markup(profile)}
        </section>''',
        unsafe_allow_html=True,
    )
    rail = (
        ("◆", "Visible workspace", "High-contrast hierarchy and section framing"),
        ("◎", "Module identity", f"{profile.label.title()} visual language"),
        ("✓", "Action ready", "Forms, tables and controls remain functional"),
        ("↗", "Evidence aware", "Status, provenance and audit cues stay visible"),
    )
    rail_html = "".join(
        f'<div class="bx-status-cell"><span class="bx-status-icon">{html.escape(icon)}</span><div><strong>{html.escape(label)}</strong><small>{html.escape(detail)}</small></div></div>'
        for icon, label, detail in rail
    )
    st.markdown(f'<div class="bx-status-rail">{rail_html}</div>', unsafe_allow_html=True)


def module_tiles(items: Iterable[tuple[str, str, str] | tuple[str, str, str, str]]) -> None:
    # Backward compatible with the original three-field cards while allowing an
    # explicit icon as the fourth field for richer module-specific frontends.
    from biointel.ui.frontend_v10 import icon_for_kicker
    cards: list[str] = []
    for item in items:
        kicker, title, detail = item[:3]
        icon = item[3] if len(item) > 3 else icon_for_kicker(kicker)
        cards.append(
            f'<article class="bx-module-tile"><span class="bx-module-icon">{html.escape(str(icon))}</span><span>{html.escape(str(kicker))}</span><strong>{html.escape(str(title))}</strong><small>{html.escape(str(detail))}</small></article>'
        )
    st.markdown(f'<div class="bx-module-band">{"".join(cards)}</div>', unsafe_allow_html=True)


def course_card_markup(
    *, title: str, difficulty: str, lectures: int, state: str, progress: float, enrollments: int, index: int = 0
) -> str:
    palettes = [
        ("#35e4ff", "#6f7dff", "🧬"), ("#7dff9f", "#34b8ff", "⌬"),
        ("#c083ff", "#4fe4ff", "⚗"), ("#ffca72", "#ff7aa5", "🔬"),
        ("#58f2cf", "#6477ff", "◈"), ("#a8ff6a", "#35d3ff", "⌘"),
    ]
    a, b, symbol = palettes[index % len(palettes)]
    percentage = max(0, min(100, round(float(progress) * 100)))
    state_label = str(state or "draft").replace("_", " ").title()
    return f'''<article class="bx-course-card" style="--course-a:{a};--course-b:{b}">
      <div class="bx-course-cover">
        <div class="bx-course-kicker">BIOINTEL ACADEMY · {html.escape(str(difficulty).upper())}</div>
        <h3>{html.escape(title)}</h3><div class="bx-course-symbol">{symbol}</div>
      </div>
      <div class="bx-course-body">
        <div class="bx-course-meta"><span>✓ {html.escape(state_label)}</span><span>▶ {int(lectures)} lectures</span><span>◎ Evidence-led</span></div>
        <div class="bx-course-progress-label"><span>Learning progress</span><span>{percentage}%</span></div>
        <div class="bx-course-progress"><i style="width:{percentage}%"></i></div>
        <div class="bx-course-footer"><span>{int(enrollments)} persisted enrollments</span><b>Open course →</b></div>
      </div>
    </article>'''


def course_cover_markup(*, title: str, difficulty: str, index: int = 0, label: str = "BIOINTEL ACADEMY") -> str:
    palettes = [
        ("#35e4ff", "#6f7dff", "🧬"), ("#7dff9f", "#34b8ff", "⌬"),
        ("#c083ff", "#4fe4ff", "⚗"), ("#ffca72", "#ff7aa5", "🔬"),
        ("#58f2cf", "#6477ff", "◈"), ("#a8ff6a", "#35d3ff", "⌘"),
    ]
    a, b, symbol = palettes[index % len(palettes)]
    return f'''<div class="bx-course-cover" style="--course-a:{a};--course-b:{b};border-radius:16px;margin:-.35rem -.35rem .8rem">
      <div class="bx-course-kicker">{html.escape(label)} · {html.escape(str(difficulty).upper())}</div>
      <h3>{html.escape(title)}</h3><div class="bx-course-symbol">{symbol}</div>
    </div>'''


def section_shell_header(title: str, detail: str = "", kicker: str = "WORKSPACE") -> None:
    st.markdown(
        f'<div class="bx-section-shell"><div class="bx-section-head"><div><span>{html.escape(kicker)}</span><h3>{html.escape(title)}</h3></div><small>{html.escape(detail)}</small></div></div>',
        unsafe_allow_html=True,
    )


def visible_empty_state(title: str, detail: str, action_hint: str = "Use the controls above to create the first record.") -> None:
    st.markdown(
        f'<div class="bx-empty"><div><div class="bx-status-icon" style="margin:0 auto .7rem">＋</div><b>{html.escape(title)}</b><small>{html.escape(detail)} {html.escape(action_hint)}</small></div></div>',
        unsafe_allow_html=True,
    )
