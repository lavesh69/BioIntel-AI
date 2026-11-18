from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

try:
    import streamlit as st
except ModuleNotFoundError:  # release checks may run without Streamlit
    from biointel.education._streamlit_compat import st


# Phase 10 full frontend completion layer. This intentionally stays presentation-only:
# no permissions, data mutations, scientific calculations or audit semantics are changed.
FRONTEND_V10_CSS = r"""
<style>
/* Phase 10 full frontend completion */
:root{
  --bx10-radius-xl:24px;--bx10-radius-lg:18px;--bx10-radius-md:13px;
  --bx10-surface:linear-gradient(145deg,rgba(15,34,57,.91),rgba(6,19,34,.89));
  --bx10-surface-soft:linear-gradient(145deg,rgba(16,37,62,.72),rgba(7,21,38,.70));
  --bx10-shadow:0 18px 52px rgba(0,0,0,.25);
  --bx10-shadow-soft:0 11px 30px rgba(0,0,0,.17);
}
html{scroll-behavior:smooth}
[data-testid="stHeader"]{background:rgba(5,13,25,.74)!important;border-bottom:1px solid rgba(145,188,230,.12)!important;backdrop-filter:blur(18px)}
[data-testid="stToolbar"]{gap:.25rem}
[data-testid="stMainBlockContainer"]{padding-left:1.55rem!important;padding-right:1.55rem!important}

/* Professional section hierarchy on every covered page. */
[data-testid="stMainBlockContainer"] h2,[data-testid="stMainBlockContainer"] h3{
  position:relative;color:#f1f8ff!important;letter-spacing:-.018em!important;
}
[data-testid="stMainBlockContainer"] h2{margin-top:1.35rem!important;padding:.8rem 1rem .8rem 1.12rem!important;border:1px solid var(--bx-border)!important;border-radius:16px!important;background:linear-gradient(90deg,color-mix(in srgb,var(--bx-accent) 10%,rgba(13,30,51,.88)),rgba(7,20,35,.72))!important;box-shadow:var(--bx10-shadow-soft)!important}
[data-testid="stMainBlockContainer"] h2:before{content:"";position:absolute;left:0;top:.55rem;bottom:.55rem;width:4px;border-radius:99px;background:linear-gradient(var(--bx-accent),var(--bx-accent-2));box-shadow:0 0 18px var(--bx-glow)}
[data-testid="stMainBlockContainer"] h3{padding-left:.82rem!important}
[data-testid="stMainBlockContainer"] h3:before{content:"◆";position:absolute;left:0;top:.05em;color:var(--bx-accent);font-size:.66em;filter:drop-shadow(0 0 8px var(--bx-glow))}
[data-testid="stMainBlockContainer"] h4{color:#e8f4ff!important;letter-spacing:-.01em}
hr{border-color:rgba(145,188,230,.14)!important;margin:1.15rem 0!important}

/* Containers become deliberate cards rather than anonymous rectangles. */
[data-testid="stVerticalBlockBorderWrapper"]{
  border:1px solid var(--bx-border)!important;border-radius:var(--bx10-radius-lg)!important;
  background:var(--bx10-surface)!important;box-shadow:var(--bx10-shadow-soft)!important;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover{border-color:color-mix(in srgb,var(--bx-accent) 34%,var(--bx-border))!important}
[data-testid="stMetric"]{position:relative;overflow:hidden;padding:.78rem .85rem!important;border-radius:15px!important;background:linear-gradient(145deg,rgba(17,39,65,.76),rgba(7,21,37,.74))!important}
[data-testid="stMetric"]:after{content:"";position:absolute;right:-30px;bottom:-42px;width:95px;height:95px;border-radius:50%;background:radial-gradient(circle,var(--bx-glow),transparent 67%)}
[data-testid="stMetricLabel"] p{font-size:.74rem!important;text-transform:uppercase!important;letter-spacing:.07em!important;color:#a9bdd4!important;font-weight:850!important}
[data-testid="stMetricValue"]{font-size:1.65rem!important;letter-spacing:-.045em!important}
[data-testid="stMetricDelta"]{font-weight:750!important}

/* Complete control system. */
.stButton>button,.stDownloadButton>button,[data-testid="stPageLink"] a{
  border:1px solid color-mix(in srgb,var(--bx-accent) 24%,var(--bx-border))!important;
  background:linear-gradient(145deg,rgba(19,42,69,.94),rgba(7,22,39,.94))!important;
  color:#edf7ff!important;border-radius:13px!important;font-weight:800!important;
  box-shadow:0 9px 24px rgba(0,0,0,.19)!important;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease!important;
}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stPageLink"] a:hover{transform:translateY(-2px);border-color:var(--bx-accent)!important;box-shadow:0 13px 32px var(--bx-glow)!important}
.stButton>button[kind="primary"]{background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2))!important;color:#03111c!important;border-color:transparent!important;text-shadow:none!important}
.stButton>button:disabled{opacity:.48!important;transform:none!important;box-shadow:none!important}
[data-testid="stLinkButton"] a{border-radius:13px!important}
[data-baseweb="input"]>div,[data-baseweb="textarea"]>div,[data-baseweb="select"]>div,[data-testid="stNumberInputContainer"],[data-testid="stDateInput"]>div,[data-testid="stTimeInput"]>div{
  min-height:2.75rem;background:rgba(4,15,28,.91)!important;border:1px solid rgba(145,188,230,.26)!important;border-radius:13px!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.025)!important;
}
[data-baseweb="input"]>div:hover,[data-baseweb="textarea"]>div:hover,[data-baseweb="select"]>div:hover{border-color:color-mix(in srgb,var(--bx-accent) 62%,transparent)!important}
[data-baseweb="input"] input,[data-baseweb="textarea"] textarea{color:#f2f8ff!important}
[data-baseweb="input"] input::placeholder,[data-baseweb="textarea"] textarea::placeholder{color:#7189a4!important}
[data-testid="stWidgetLabel"] p{font-size:.78rem!important;letter-spacing:.015em!important;color:#dcecff!important;font-weight:800!important}
[data-testid="stSelectbox"] svg,[data-testid="stMultiSelect"] svg{color:var(--bx-accent)!important}
[data-testid="stCheckbox"] label,[data-testid="stToggle"] label,[data-testid="stRadio"] label{border:1px solid transparent;border-radius:11px;padding:.38rem .45rem!important;transition:.15s ease}
[data-testid="stCheckbox"] label:hover,[data-testid="stToggle"] label:hover,[data-testid="stRadio"] label:hover{border-color:var(--bx-border);background:rgba(255,255,255,.035)}
[data-testid="stSlider"] [role="slider"]{background:var(--bx-accent)!important;box-shadow:0 0 0 5px var(--bx-glow)!important}
[data-testid="stFileUploader"] section{border-radius:16px!important;background:rgba(4,16,29,.72)!important}
[data-testid="stFileUploaderDropzone"]{min-height:118px!important}
[data-testid="stFileUploaderDropzoneInstructions"] span{color:#e9f5ff!important;font-weight:850!important}
[data-testid="stForm"]{position:relative;padding:1.12rem!important;border:1px solid color-mix(in srgb,var(--bx-accent) 20%,var(--bx-border))!important;border-radius:20px!important;background:var(--bx10-surface)!important;box-shadow:var(--bx10-shadow)!important}
[data-testid="stForm"]:before{content:"FORM WORKSPACE";display:block;margin-bottom:.8rem;color:var(--bx-accent);font-size:.64rem;font-weight:950;letter-spacing:.15em}

/* Navigation, tabs and filters. */
[data-baseweb="tab-list"]{position:sticky;top:.35rem;z-index:20;padding:.34rem!important;border-radius:15px!important;background:rgba(5,16,29,.92)!important;backdrop-filter:blur(16px);box-shadow:0 12px 30px rgba(0,0,0,.2)!important}
[data-baseweb="tab"]{min-height:2.75rem!important;border:1px solid transparent!important;font-weight:800!important}
[data-baseweb="tab"]:hover{border-color:var(--bx-border)!important;background:rgba(255,255,255,.035)!important}
[data-baseweb="tab"][aria-selected="true"]{border-color:color-mix(in srgb,var(--bx-accent) 48%,transparent)!important;background:linear-gradient(135deg,color-mix(in srgb,var(--bx-accent) 18%,transparent),color-mix(in srgb,var(--bx-accent-2) 12%,transparent))!important;box-shadow:0 8px 22px var(--bx-glow)!important}
[data-testid="stSegmentedControl"]>div,[data-testid="stPills"]>div{padding:.28rem!important;border:1px solid var(--bx-border)!important;border-radius:14px!important;background:rgba(5,16,29,.74)!important}
[data-testid="stPopover"] button{border-radius:12px!important}

/* Data, code, JSON and media are framed as inspectable evidence. */
[data-testid="stDataFrame"],[data-testid="stDataEditor"]{position:relative;border:1px solid var(--bx-border)!important;border-radius:18px!important;background:rgba(5,17,31,.86)!important;box-shadow:var(--bx10-shadow)!important;overflow:hidden!important}
[data-testid="stDataFrame"]:before,[data-testid="stDataEditor"]:before{content:"DATA VIEW";display:block;padding:.5rem .75rem;border-bottom:1px solid var(--bx-border);color:var(--bx-accent);font-size:.61rem;font-weight:950;letter-spacing:.14em;background:rgba(15,34,57,.9)}
[data-testid="stJson"]{padding:.75rem!important;border:1px solid var(--bx-border)!important;border-radius:16px!important;background:rgba(3,13,25,.9)!important}
[data-testid="stCodeBlock"]{border:1px solid var(--bx-border)!important;border-radius:16px!important;overflow:hidden!important;box-shadow:var(--bx10-shadow-soft)!important}
[data-testid="stImage"],[data-testid="stVideo"]{padding:.45rem;border:1px solid var(--bx-border);border-radius:18px;background:rgba(4,16,29,.8);box-shadow:var(--bx10-shadow-soft)}
[data-testid="stPlotlyChart"],[data-testid="stVegaLiteChart"],[data-testid="stPyplotGlobalUse"]{position:relative;min-height:180px}
[data-testid="stPlotlyChart"]:before,[data-testid="stVegaLiteChart"]:before,[data-testid="stPyplotGlobalUse"]:before{content:"INTERACTIVE VISUAL";position:absolute;top:.5rem;left:.72rem;z-index:4;color:var(--bx-accent);font-size:.58rem;font-weight:950;letter-spacing:.14em;pointer-events:none}

/* Chat and collaboration surfaces. */
[data-testid="stChatMessage"]{margin:.65rem 0!important;padding:.9rem 1rem!important;border:1px solid var(--bx-border)!important;border-radius:18px!important;background:linear-gradient(145deg,rgba(15,34,57,.84),rgba(6,19,34,.86))!important;box-shadow:var(--bx10-shadow-soft)!important}
[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarUser"]{box-shadow:0 0 0 3px color-mix(in srgb,var(--bx-accent) 25%,transparent)!important}
[data-testid="stChatInput"]{padding:.55rem!important;border:1px solid color-mix(in srgb,var(--bx-accent) 38%,var(--bx-border))!important;border-radius:18px!important;background:rgba(4,15,28,.94)!important;box-shadow:0 16px 46px rgba(0,0,0,.34),0 0 28px var(--bx-glow)!important}
[data-testid="stChatInput"] textarea{color:#f3f8ff!important}

/* Alerts, statuses and feedback. */
[data-testid="stAlert"]{position:relative;padding-left:1.05rem!important;box-shadow:var(--bx10-shadow-soft)!important}
[data-testid="stAlert"]:before{content:"";position:absolute;left:0;top:.4rem;bottom:.4rem;width:4px;border-radius:99px;background:linear-gradient(var(--bx-accent),var(--bx-accent-2))}
[data-testid="stToast"]{border:1px solid var(--bx-border)!important;border-radius:15px!important;background:rgba(7,20,35,.96)!important;box-shadow:var(--bx10-shadow)!important}
[data-testid="stProgress"]>div>div{background:rgba(255,255,255,.08)!important;border-radius:999px!important;overflow:hidden!important}
[data-testid="stProgress"]>div>div>div{background:linear-gradient(90deg,var(--bx-accent),var(--bx-accent-2))!important;box-shadow:0 0 17px var(--bx-glow)!important}
[data-testid="stStatusWidget"]{border-radius:16px!important;border:1px solid var(--bx-border)!important;background:var(--bx10-surface-soft)!important}
[data-testid="stExpander"] summary:hover{background:rgba(255,255,255,.035)!important}

/* New reusable Phase 10 components. */
.bx10-compact-hero{position:relative;overflow:hidden;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:1rem;padding:1.05rem 1.15rem;margin:.1rem 0 .8rem;border:1px solid color-mix(in srgb,var(--bx-accent) 32%,var(--bx-border));border-radius:20px;background:linear-gradient(135deg,rgba(18,40,67,.96),rgba(6,19,34,.95));box-shadow:var(--bx10-shadow)}
.bx10-compact-hero:after{content:"";position:absolute;right:-80px;top:-85px;width:230px;height:230px;border-radius:50%;background:radial-gradient(circle,var(--bx-glow),transparent 68%)}
.bx10-compact-icon{position:relative;z-index:2;display:grid;place-items:center;width:3.15rem;height:3.15rem;border-radius:16px;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));color:#03111c;font-size:1.35rem;font-weight:950;box-shadow:0 0 32px var(--bx-glow)}
.bx10-compact-copy{position:relative;z-index:2}.bx10-compact-copy span{display:block;color:var(--bx-accent);font-size:.63rem;font-weight:950;letter-spacing:.15em;text-transform:uppercase}.bx10-compact-copy h1{margin:.18rem 0 .2rem!important;font-size:1.65rem!important;letter-spacing:-.035em!important}.bx10-compact-copy p{margin:0;color:var(--bx-muted);font-size:.86rem;line-height:1.45}
.bx10-compact-status{position:relative;z-index:2;display:flex;gap:.35rem;flex-wrap:wrap;justify-content:flex-end}.bx10-compact-status i{font-style:normal;padding:.32rem .55rem;border:1px solid var(--bx-border);border-radius:999px;color:#dcecff;background:rgba(255,255,255,.045);font-size:.66rem;font-weight:800}
.bx10-capability-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem;margin:.7rem 0 1.05rem}
.bx10-capability{position:relative;overflow:hidden;display:flex;gap:.72rem;min-height:104px;padding:.85rem;border:1px solid var(--bx-border);border-radius:17px;background:var(--bx10-surface-soft);box-shadow:var(--bx10-shadow-soft);transition:.16s ease}
.bx10-capability:hover{transform:translateY(-3px);border-color:color-mix(in srgb,var(--bx-accent) 52%,transparent);box-shadow:0 16px 38px var(--bx-glow)}
.bx10-capability:after{content:"";position:absolute;right:-36px;bottom:-45px;width:105px;height:105px;border-radius:50%;background:radial-gradient(circle,var(--bx-glow),transparent 70%)}
.bx10-capability-icon{position:relative;z-index:2;display:grid;place-items:center;flex:0 0 2.45rem;height:2.45rem;border-radius:13px;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));color:#03111c;font-size:1.05rem;font-weight:950;box-shadow:0 0 21px var(--bx-glow)}
.bx10-capability-copy{position:relative;z-index:2}.bx10-capability-copy b{display:block;color:#eef7ff;font-size:.85rem;margin:.05rem 0 .22rem}.bx10-capability-copy small{display:block;color:var(--bx-muted);font-size:.7rem;line-height:1.42}
.bx10-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem;margin:.65rem 0 1rem}.bx10-kpi{position:relative;overflow:hidden;padding:.88rem;border:1px solid var(--bx-border);border-radius:17px;background:var(--bx10-surface-soft);box-shadow:var(--bx10-shadow-soft)}.bx10-kpi>span{display:inline-grid;place-items:center;width:2rem;height:2rem;border-radius:10px;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));color:#03111c;font-weight:950}.bx10-kpi small{display:block;margin:.55rem 0 .16rem;color:var(--bx-muted);font-size:.67rem;text-transform:uppercase;letter-spacing:.08em;font-weight:850}.bx10-kpi strong{display:block;color:#f3f8ff;font-size:1.32rem;letter-spacing:-.04em}.bx10-kpi em{display:block;color:#819bb7;font-size:.66rem;font-style:normal;margin-top:.25rem}
.bx10-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;margin:1.15rem 0 .65rem;padding:.82rem .95rem;border-left:4px solid var(--bx-accent);border-radius:0 15px 15px 0;background:linear-gradient(90deg,color-mix(in srgb,var(--bx-accent) 10%,rgba(14,32,54,.78)),rgba(7,20,35,.48))}.bx10-section-title{display:flex;gap:.68rem;align-items:flex-start}.bx10-section-icon{display:grid;place-items:center;width:2.15rem;height:2.15rem;border-radius:11px;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));color:#03111c;font-weight:950}.bx10-section-head b{display:block;color:#eef7ff;font-size:.96rem}.bx10-section-head small{display:block;color:var(--bx-muted);font-size:.72rem;margin-top:.15rem}.bx10-section-head i{font-style:normal;padding:.27rem .48rem;border:1px solid var(--bx-border);border-radius:999px;color:var(--bx-accent);font-size:.63rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase}
.bx10-action-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.72rem;margin:.7rem 0 1rem}.bx10-action-card{position:relative;overflow:hidden;padding:1rem;border:1px solid var(--bx-border);border-radius:18px;background:var(--bx10-surface);box-shadow:var(--bx10-shadow-soft)}.bx10-action-card>span{display:grid;place-items:center;width:2.65rem;height:2.65rem;border-radius:14px;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));color:#03111c;font-size:1.15rem;font-weight:950}.bx10-action-card b{display:block;margin:.7rem 0 .25rem;color:#f1f8ff}.bx10-action-card small{display:block;color:var(--bx-muted);font-size:.72rem;line-height:1.48}.bx10-action-card em{display:inline-block;margin-top:.7rem;color:var(--bx-accent);font-size:.68rem;font-style:normal;font-weight:900;text-transform:uppercase;letter-spacing:.08em}
.bx10-empty{position:relative;overflow:hidden;display:grid;place-items:center;min-height:205px;padding:1.4rem;text-align:center;border:1px dashed color-mix(in srgb,var(--bx-accent) 48%,var(--bx-border));border-radius:20px;background:radial-gradient(circle at 50% 18%,var(--bx-glow),transparent 13rem),rgba(5,17,31,.68)}.bx10-empty-icon{display:grid;place-items:center;width:3.4rem;height:3.4rem;margin:0 auto .75rem;border-radius:18px;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));color:#03111c;font-size:1.35rem;font-weight:950;box-shadow:0 0 34px var(--bx-glow)}.bx10-empty b{display:block;color:#f2f8ff;font-size:1.05rem}.bx10-empty small{display:block;max-width:42rem;margin:.35rem auto 0;color:var(--bx-muted);line-height:1.5}.bx10-empty em{display:inline-block;margin-top:.65rem;color:var(--bx-accent);font-size:.68rem;font-weight:900;font-style:normal;text-transform:uppercase;letter-spacing:.08em}
.bx10-person{display:flex;align-items:center;gap:.7rem}.bx10-avatar{display:grid;place-items:center;flex:0 0 2.6rem;height:2.6rem;border-radius:14px;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));color:#03111c;font-weight:950;box-shadow:0 0 22px var(--bx-glow)}.bx10-person b{display:block;color:#f1f8ff}.bx10-person small{display:block;color:var(--bx-muted);font-size:.69rem;margin-top:.1rem}.bx10-meta-row{display:flex;flex-wrap:wrap;gap:.35rem;margin:.5rem 0}.bx10-meta{padding:.25rem .48rem;border:1px solid var(--bx-border);border-radius:999px;background:rgba(255,255,255,.04);color:#cfe3f7;font-size:.64rem;font-weight:750}
.bx10-timeline{position:relative;margin:.5rem 0;padding-left:1.3rem}.bx10-timeline:before{content:"";position:absolute;left:.36rem;top:.4rem;bottom:.4rem;width:2px;background:linear-gradient(var(--bx-accent),var(--bx-accent-2),transparent)}.bx10-timeline-item{position:relative;margin:.2rem 0 .72rem;padding:.7rem .8rem;border:1px solid var(--bx-border);border-radius:14px;background:rgba(8,23,40,.76)}.bx10-timeline-item:before{content:"";position:absolute;left:-1.19rem;top:.9rem;width:.65rem;height:.65rem;border-radius:50%;background:var(--bx-accent);box-shadow:0 0 14px var(--bx-accent)}.bx10-timeline-item b{display:block;color:#edf7ff;font-size:.82rem}.bx10-timeline-item small{display:block;color:var(--bx-muted);font-size:.68rem;margin-top:.15rem}
.bx10-nav-strip{display:flex;gap:.35rem;flex-wrap:wrap;margin:.2rem 0 .9rem;padding:.38rem;border:1px solid var(--bx-border);border-radius:15px;background:rgba(5,16,29,.76)}

/* Icons and spacing for legacy module tiles. */
.bx-module-tile{display:grid!important;grid-template-columns:auto 1fr!important;column-gap:.68rem!important;align-content:start!important}.bx-module-tile .bx-module-icon{grid-row:1/4;display:grid;place-items:center;width:2.45rem;height:2.45rem;border-radius:13px;background:linear-gradient(135deg,var(--bx-accent),var(--bx-accent-2));color:#03111c;font-size:1rem;font-weight:950;box-shadow:0 0 20px var(--bx-glow)}.bx-module-tile>span:not(.bx-module-icon),.bx-module-tile>strong,.bx-module-tile>small{grid-column:2}.bx-module-tile>strong{font-size:.88rem!important}.bx-module-tile>small{line-height:1.45!important}

/* Desktop-first scope requested for Phase 10. */
@media(max-width:1200px){.bx10-capability-grid,.bx10-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.bx10-action-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}.bx10-capability,.stButton>button,.stDownloadButton>button{transition:none!important}}
</style>
"""


@dataclass(frozen=True)
class Capability:
    icon: str
    title: str
    detail: str


CAPABILITIES: dict[str, tuple[Capability, ...]] = {
    "connect": (
        Capability("◎", "Scientific network", "Profiles, communities and explainable collaborator discovery."),
        Capability("✉", "Communication", "Durable messages, calls, events and permission-aware collaboration."),
        Capability("↗", "Publishing", "Evidence-led posts, datasets, workflows and research updates."),
        Capability("✓", "Trust controls", "Verification, privacy, moderation and institutional governance."),
    ),
    "shiro": (
        Capability("✦", "Evidence chat", "Project-isolated conversations grounded in indexed scientific sources."),
        Capability("⌕", "Citation atlas", "Clickable evidence, source preview and confidence-aware retrieval."),
        Capability("◈", "Learning modes", "Guided learning, revision and teacher planning experiences."),
        Capability("▣", "Private runtime", "Local-first operation with explicit external-provider controls."),
    ),
    "studio": (
        Capability("🧬", "Bioinformatics", "Domain workbenches, scientific viewers and reproducible analysis."),
        Capability("⌁", "Intelligence", "Literature, data and evidence-aware research exploration."),
        Capability("✓", "Quality", "Validation, governance and release-readiness workspaces."),
        Capability("⇩", "Evidence packages", "Reports, exports and checksum-bound scientific deliverables."),
    ),
    "completion": (
        Capability("◆", "Identity and infrastructure", "OIDC PKCE, portable migration exports and verified storage transfer contracts."),
        Capability("✓", "Academic assurance", "Originality review, independent exam approvals, moderation and appeals."),
        Capability("✦", "Shiro governance", "Model qualification, RAG safety scanning and retrieval evaluation evidence."),
        Capability("↗", "Release qualification", "Delivery providers, runtime posture and external certification boundaries."),
    ),
    "autonomy": (
        Capability("⌕", "Evidence retrieval", "Multi-format extraction, permission filtering and exact source locators."),
        Capability("▦", "Timetable solver", "Conflict-free teacher, group and room scheduling with atomic commit."),
        Capability("✉", "Notification policy", "Quiet hours, digest planning, idempotency and dead-letter recovery."),
        Capability("✓", "Lifecycle operations", "Verified retention archives and redacted support diagnostics."),
    ),
    "home": (
        Capability("⌂", "Today", "Classes, deadlines, examinations and high-priority academic actions."),
        Capability("✓", "Progress", "Attendance, course completion and role-aware performance snapshots."),
        Capability("!", "Interventions", "Visible risk, consent and governance tasks requiring review."),
        Capability("↗", "Quick launch", "Direct access to teaching, learning and institution workspaces."),
    ),
    "classroom": (
        Capability("▦", "Timetable", "Conflict-aware class scheduling and calendar-based teaching operations."),
        Capability("✓", "Attendance", "Roster workflows, locked sessions and shortage intervention."),
        Capability("▤", "Assignments", "Kanban lifecycle, submissions, rubrics and evidence-led feedback."),
        Capability("▥", "Gradebook", "Bulk grading, revision history, moderation and publication controls."),
    ),
    "pulse": (
        Capability("⌁", "Research signals", "Publication activity, topics and scientific evidence trends."),
        Capability("⌕", "Discovery", "Search, filters and institution-scoped publication intelligence."),
        Capability("!", "Corrections", "Retraction, correction and source-status visibility."),
        Capability("⇩", "Evidence export", "Reference-ready records and governed research summaries."),
    ),
    "academy": (
        Capability("▷", "Course gallery", "Illustrated courses, progress, enrollment and learning continuity."),
        Capability("▤", "Curriculum", "Sections, lectures, assessments, prerequisites and release state."),
        Capability("▶", "Lecture studio", "Chapters, notes, bookmarks, transcripts and playback evidence."),
        Capability("★", "Credentials", "Completion rules, quizzes and verification-ready certificates."),
    ),
    "universe": (
        Capability("◎", "Module map", "Connected educational, scientific and research learning modules."),
        Capability("⚗", "Virtual labs", "Safe simulations, observations and reproducible learning evidence."),
        Capability("🧬", "Scientific tools", "Bioinformatics sandbox and domain-specific visual exploration."),
        Capability("↗", "Workflow records", "Versioned records, state transitions and evidence lineage."),
    ),
    "examinations": (
        Capability("✓", "Secure delivery", "Server time, attempt limits, sealed submissions and access controls."),
        Capability("◉", "Live command", "Candidate states, autosave evidence and integrity monitoring."),
        Capability("▥", "Assessment analytics", "Blueprints, score distributions and question diagnostics."),
        Capability("⚖", "Moderation", "Manual grading, revaluation and controlled result publication."),
    ),
    "intelligence": (
        Capability("◇", "Mastery graph", "Concept prerequisites, evidence confidence and learning progress."),
        Capability("✦", "Shiro tutor", "Citation-grounded student and teacher intelligence workflows."),
        Capability("!", "Interventions", "Weak-topic, attendance and performance support recommendations."),
        Capability("▤", "Reports", "Governed learner summaries and explainable academic insights."),
    ),
    "institution": (
        Capability("▤", "Campus hierarchy", "Campuses, academic units and institution-scoped governance."),
        Capability("◉", "Identity posture", "SSO readiness, MFA policy and permission administration."),
        Capability("▣", "Platform operations", "Storage, backups, queues and qualification evidence."),
        Capability("↔", "Integrations", "LMS readiness, sync history and provider diagnostics."),
    ),
    "visuals": (
        Capability("◫", "Visual workspaces", "Timelines, heatmaps, networks and operational dashboards."),
        Capability("⌕", "Drill-down", "Role-aware views with record context and evidence detail."),
        Capability("▦", "Cross-module view", "Classroom, Academy, Pulse, Universe and institution visibility."),
        Capability("⇩", "Export-ready", "Human-readable visual summaries and governed evidence output."),
    ),
    "desktop": (
        Capability("▣", "Secure session", "Local sign-in, lockout, revocable sessions and desktop context."),
        Capability("⌘", "Command palette", "Lazy workspace routing and fast academic task navigation."),
        Capability("▦", "Workflow editors", "Timetable, gradebook, attendance, rubrics and curriculum."),
        Capability("◉", "Operations", "Live examination, worker, backup and integration surfaces."),
    ),
    "quality": (
        Capability("🎯", "Outcome mapping", "Course, program and institution outcomes linked to governed assessment evidence."),
        Capability("◈", "Psychometrics", "Difficulty, omission, discrimination and reliability with sample warnings."),
        Capability("🤝", "Learner support", "Transparent evidence thresholds and human-authored intervention plans."),
        Capability("▦", "Academic calendar", "Institution events, timetable visibility and portable ICS exports."),
    ),
    "runtime": (
        Capability("◉", "Live event stream", "Institution-scoped durable events with replay, audience filters and SSE delivery."),
        Capability("◇", "Hybrid evidence", "Approved-source lexical and semantic retrieval with governed citations."),
        Capability("✦", "Model runtime", "Local and OpenAI-compatible model profiles with live health qualification."),
        Capability("⌁", "Research providers", "Built-in scientific provider sync and governed media telemetry."),
    ),
    "completion16": (
        Capability("◉", "Replay-safe consumers", "Durable cursors, acknowledgement and presence across event-driven workspaces."),
        Capability("✓", "Measurable RAG", "Diverse evidence retrieval with recall and reciprocal-rank evaluation."),
        Capability("🧬", "Sequence workbench", "Bounded FASTA/FASTQ quality, ORF, translation, k-mer and alignment tools."),
        Capability("▷", "Media pipeline", "Planned and executable FFmpeg outputs with checksum-bound evidence."),
    ),
}


ICONS_BY_KICKER: dict[str, str] = {
    "DISCOVER": "⌕", "ANALYSE": "◈", "ANALYZE": "◈", "VALIDATE": "✓", "PUBLISH": "↗",
    "COMMUNICATE": "✉", "TRUST": "◎", "LEARN": "▷", "CREATE": "+", "MANAGE": "▤",
    "MONITOR": "◉", "SECURE": "◇", "REVIEW": "✓", "EXPLORE": "⌕", "OPERATE": "⌘",
}


def apply_frontend_v10(page_key: str) -> None:
    """Apply the completed desktop visual system without changing application logic."""
    try:
        from biointel.ui.product_experience_v8 import apply_product_skin
        # apply_product_skin includes FRONTEND_V10_CSS so a page receives one
        # coherent stylesheet rather than duplicate style nodes on every rerun.
        apply_product_skin(page_key)
    except Exception:
        st.markdown(FRONTEND_V10_CSS, unsafe_allow_html=True)


def compact_page_header(
    page_key: str,
    title: str,
    subtitle: str,
    *,
    eyebrow: str | None = None,
    status: Sequence[str] = ("Permission-aware", "Evidence-ready"),
) -> None:
    apply_frontend_v10(page_key)
    try:
        from biointel.ui.product_experience_v8 import PROFILES
        profile = PROFILES.get(page_key, PROFILES["home"])
        icon = profile.icon
        label = profile.label
    except Exception:
        icon, label = "◆", page_key.replace("_", " ").title()
    status_html = "".join(f"<i>{html.escape(str(item))}</i>" for item in status)
    st.markdown(
        f'''<section class="bx10-compact-hero">
          <div class="bx10-compact-icon">{html.escape(icon)}</div>
          <div class="bx10-compact-copy"><span>{html.escape(eyebrow or label)}</span><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>
          <div class="bx10-compact-status">{status_html}</div>
        </section>''',
        unsafe_allow_html=True,
    )


def capability_grid(page_key: str, items: Iterable[Capability] | None = None) -> None:
    selected = tuple(items or CAPABILITIES.get(page_key, ()))
    if not selected:
        return
    body = "".join(
        f'<article class="bx10-capability"><span class="bx10-capability-icon">{html.escape(item.icon)}</span><div class="bx10-capability-copy"><b>{html.escape(item.title)}</b><small>{html.escape(item.detail)}</small></div></article>'
        for item in selected
    )
    st.markdown(f'<div class="bx10-capability-grid">{body}</div>', unsafe_allow_html=True)


def kpi_grid(items: Iterable[tuple[str, Any, str, str]]) -> None:
    body = "".join(
        f'<article class="bx10-kpi"><span>{html.escape(icon)}</span><small>{html.escape(label)}</small><strong>{html.escape(str(value))}</strong><em>{html.escape(detail)}</em></article>'
        for icon, label, value, detail in items
    )
    st.markdown(f'<div class="bx10-kpi-grid">{body}</div>', unsafe_allow_html=True)


def section_header(title: str, detail: str = "", *, icon: str = "◆", badge: str = "Workspace") -> None:
    st.markdown(
        f'''<div class="bx10-section-head"><div class="bx10-section-title"><span class="bx10-section-icon">{html.escape(icon)}</span><div><b>{html.escape(title)}</b><small>{html.escape(detail)}</small></div></div><i>{html.escape(badge)}</i></div>''',
        unsafe_allow_html=True,
    )


def action_grid(items: Iterable[tuple[str, str, str, str]]) -> None:
    body = "".join(
        f'<article class="bx10-action-card"><span>{html.escape(icon)}</span><b>{html.escape(title)}</b><small>{html.escape(detail)}</small><em>{html.escape(action)}</em></article>'
        for icon, title, detail, action in items
    )
    st.markdown(f'<div class="bx10-action-grid">{body}</div>', unsafe_allow_html=True)


def empty_state(title: str, detail: str, *, icon: str = "+", action_hint: str = "Use the available action to create the first record.") -> None:
    st.markdown(
        f'<div class="bx10-empty"><div><span class="bx10-empty-icon">{html.escape(icon)}</span><b>{html.escape(title)}</b><small>{html.escape(detail)}</small><em>{html.escape(action_hint)}</em></div></div>',
        unsafe_allow_html=True,
    )


def person_header(name: str, detail: str, *, initials: str = "BI", metadata: Iterable[str] = ()) -> None:
    meta = "".join(f'<span class="bx10-meta">{html.escape(str(item))}</span>' for item in metadata if str(item).strip())
    st.markdown(
        f'<div class="bx10-person"><span class="bx10-avatar">{html.escape(initials[:2].upper())}</span><div><b>{html.escape(name)}</b><small>{html.escape(detail)}</small><div class="bx10-meta-row">{meta}</div></div></div>',
        unsafe_allow_html=True,
    )


def timeline(items: Iterable[tuple[str, str]]) -> None:
    body = "".join(
        f'<div class="bx10-timeline-item"><b>{html.escape(title)}</b><small>{html.escape(detail)}</small></div>'
        for title, detail in items
    )
    st.markdown(f'<div class="bx10-timeline">{body}</div>', unsafe_allow_html=True)


def icon_for_kicker(kicker: str) -> str:
    return ICONS_BY_KICKER.get(str(kicker).upper(), "◆")


__all__ = [
    "FRONTEND_V10_CSS", "Capability", "CAPABILITIES", "apply_frontend_v10",
    "compact_page_header", "capability_grid", "kpi_grid", "section_header",
    "action_grid", "empty_state", "person_header", "timeline", "icon_for_kicker",
]
