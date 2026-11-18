from __future__ import annotations

DRAGON_PALETTE = {
    "void_black": "#05070D",
    "deep_space": "#0B1020",
    "electric_cyan": "#00D9FF",
    "dragon_violet": "#7C5CFF",
    "plasma_magenta": "#F044FF",
    "starlight": "#F5F8FF",
    "success": "#43E7A6",
}


def generate_dragon_universe_css(*, reduced_motion: bool = False) -> str:
    motion = "none" if reduced_motion else "dragon-drift 18s ease-in-out infinite alternate"
    return f"""
    <style id="biointel-dragon-universe-theme">
    :root {{
      --dragon-void: {DRAGON_PALETTE['void_black']};
      --dragon-space: {DRAGON_PALETTE['deep_space']};
      --dragon-cyan: {DRAGON_PALETTE['electric_cyan']};
      --dragon-violet: {DRAGON_PALETTE['dragon_violet']};
      --dragon-magenta: {DRAGON_PALETTE['plasma_magenta']};
      --dragon-text: {DRAGON_PALETTE['starlight']};
    }}
    .bio-dragon-shell {{
      position: relative; overflow: hidden; isolation: isolate;
      border: 1px solid color-mix(in srgb, var(--dragon-cyan) 32%, transparent);
      border-radius: 24px; padding: clamp(1rem, 3vw, 2.5rem);
      background:
        radial-gradient(circle at 18% 18%, color-mix(in srgb, var(--dragon-violet) 28%, transparent), transparent 40%),
        radial-gradient(circle at 82% 22%, color-mix(in srgb, var(--dragon-cyan) 20%, transparent), transparent 38%),
        linear-gradient(145deg, color-mix(in srgb, var(--dragon-space) 94%, transparent), color-mix(in srgb, var(--dragon-void) 98%, transparent));
      box-shadow: 0 24px 80px rgba(0,0,0,.36), inset 0 1px 0 rgba(255,255,255,.08);
      color: var(--dragon-text); backdrop-filter: blur(18px); /* glassmorphism */
    }}
    .bio-dragon-shell::before {{
      content: ""; position: absolute; inset: -35%; z-index: -1;
      background: conic-gradient(from 90deg, transparent, rgba(0,217,255,.12), transparent, rgba(240,68,255,.10), transparent);
      animation: {motion}; transform: rotate(-8deg);
    }}
    .bio-dragon-divider {{ height: 1px; border: 0; margin: 1.2rem 0;
      background: linear-gradient(90deg, transparent, var(--dragon-cyan), var(--dragon-violet), transparent); opacity: .7; }}
    .bio-dragon-kicker {{ letter-spacing: .16em; text-transform: uppercase; font-size: .78rem; color: var(--dragon-cyan); }}
    .bio-dragon-title {{ margin: .35rem 0; font-size: clamp(1.8rem, 4vw, 3.6rem); line-height: 1.02; }}
    .bio-dragon-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:.8rem; }}
    .bio-dragon-card {{ border:1px solid rgba(255,255,255,.09); border-radius:16px; padding:1rem; background:rgba(255,255,255,.035); backdrop-filter:blur(12px); }}
    @keyframes dragon-drift {{ from {{ transform: rotate(-8deg) scale(1); }} to {{ transform: rotate(8deg) scale(1.08); }} }}
    @media (prefers-reduced-motion: reduce) {{ .bio-dragon-shell::before {{ animation: none !important; }} }}
    </style>
    """
