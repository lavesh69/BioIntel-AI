from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from biointel.ui.appearance_engine import theme_variable_override_css
from biointel.ui.experience_themes import experience_theme_css
from biointel.ui.style_catalog import FONTS, THEMES

ROOT = Path(__file__).resolve().parents[1]


def _style_body(fragment: str) -> str:
    match = re.search(r"<style[^>]*>(.*)</style>", fragment, flags=re.DOTALL)
    return match.group(1) if match else fragment


def _html(theme_name: str, appearance: str, *, reduce_effects: bool = False) -> str:
    theme = THEMES[theme_name]
    experience = _style_body(
        experience_theme_css(theme, appearance_mode=appearance, compact=False, reduce_motion=False)
    )
    variables = _style_body(
        theme_variable_override_css(
            theme,
            heading_font=FONTS["Century Gothic"] if theme_name in {"Rose", "Sakura Research"} else FONTS["Inter"],
            body_font=FONTS["Inter"],
            data_font=FONTS["Courier New"],
            appearance_mode=appearance,
            reduce_effects=reduce_effects,
        )
    )
    return f"""
    <!doctype html><html><head><meta charset='utf-8'><style>
      *{{box-sizing:border-box}}html,body{{margin:0;min-height:100%;background:#020617}}
      {experience}\n{variables}
      .stApp{{min-height:100vh;padding:24px;color:var(--bio-text)}}
      .main .block-container{{margin:auto}}
      [data-testid='stSidebar']{{position:fixed;left:0;top:0;bottom:0;padding:20px 14px;border-right:1px solid var(--bio-border);background:var(--bio-surface-strong)}}
      .main{{margin-left:300px}}.bio-hero{{position:relative;padding:28px;border:1px solid var(--bio-border);overflow:hidden}}
      .bio-hero-title{{font-size:38px;margin:8px 0}}.bio-hero-subtitle{{color:var(--bio-muted);max-width:820px;line-height:1.6}}
      .bio-board{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:16px}}.bio-card,.bio-kpi{{border:1px solid var(--bio-border);padding:18px}}
      .bio-card-title{{font-size:17px}}.bio-card-copy{{color:var(--bio-muted);line-height:1.5}}.bio-kpi-value{{font-size:26px}}
      [data-testid='stButton'] button{{padding:12px 18px;border:1px solid var(--bio-border);font-weight:700}}
      [data-testid='stDataFrame']{{margin-top:16px;border:1px solid var(--bio-border);overflow:hidden}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid var(--bio-border);text-align:left}}th{{color:var(--bio-text)}}td{{color:var(--bio-muted)}}
      [data-testid='stSlider']{{margin-top:18px}}[data-testid='stSlider'] .track{{height:6px;background:var(--bio-surface);border-radius:999px}}[data-testid='stSlider'] [role='slider']{{width:18px;height:18px;border-radius:50%;margin-top:-6px}}
      [data-testid='stFileUploaderDropzone'],[data-testid='stAlert']{{padding:14px;margin-top:14px;border:1px solid var(--bio-border);background:var(--bio-surface)}}
      nav a{{display:block;padding:9px;color:var(--bio-muted);text-decoration:none;border:1px solid transparent;margin:4px 0}}nav a[aria-current='page']{{color:var(--bio-text)}}
      button:focus-visible,a:focus-visible{{outline:3px solid var(--bio-secondary);outline-offset:2px}}
    </style></head><body><div class='stApp'><aside data-testid='stSidebar'><b>BioIntel AI</b><nav><a aria-current='page' href='#'>Overview</a><a href='#'>Discovery</a><a href='#'>Lab Analytics</a><a href='#'>Quality</a></nav></aside><div class='main'><div class='block-container'>
      <section class='bio-hero'><div class='bio-eyebrow'>Appearance certification · {theme_name}</div><h1 class='bio-hero-title'>Scientific intelligence with a complete visual identity.</h1><p class='bio-hero-subtitle'>Long-title, status, scientific glyph and component stress test: α β γ Δ μ Å °C ± × 10⁻⁶ · ΔΔCt · IC₅₀ · R² · A→G.</p><div data-testid='stButton'><button kind='primary'>Run qualified analysis</button></div></section>
      <div class='bio-board'><article class='bio-kpi'><div class='bio-kpi-value'>98.4%</div><p>Calibrated confidence</p></article><article class='bio-card'><h3 class='bio-card-title'>Evidence review</h3><p class='bio-card-copy'>Provider release, provenance and quality boundaries remain legible.</p></article><article class='bio-card'><h3 class='bio-card-title'>Long workflow card heading that must wrap safely</h3><p class='bio-card-copy'>Buttons, forms, tables, alerts and charts retain the selected theme language.</p></article></div>
      <div data-testid='stDataFrame'><table><thead><tr><th>Identifier</th><th>Status</th><th>Confidence</th></tr></thead><tbody><tr><td>BRCA1:c.68_69delAG</td><td>Reviewed</td><td>0.91</td></tr><tr><td>EGFR-L858R</td><td>Qualified</td><td>0.87</td></tr></tbody></table></div>
      <div data-testid='stSlider'><div class='track'><span role='slider' tabindex='0'></span></div></div><div data-testid='stFileUploaderDropzone'>Drop scientific files here</div><div data-testid='stAlert'>Scientific boundary: demonstration data is not clinical evidence.</div>
    </div></div></div></body></html>
    """


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "visual" / "browser_baselines" / "step67"))
    parser.add_argument("--json", default=str(ROOT / "reports" / "step67_browser_theme_verification.json"))
    parser.add_argument("--theme", choices=list(THEMES))
    parser.add_argument("--appearance", choices=["Dark", "Light"])
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--reduce-effects", action="store_true")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        selected_themes = [args.theme] if args.theme else list(THEMES)
        selected_appearances = [args.appearance] if args.appearance else ["Dark", "Light"]
        for theme_name in selected_themes:
            for appearance in selected_appearances:
                page.set_content(
                    _html(theme_name, appearance, reduce_effects=args.reduce_effects),
                    wait_until="domcontentloaded",
                )
                page.locator("button").focus()
                overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
                outline = page.locator("button").evaluate("el => getComputedStyle(el).outlineStyle")
                screenshot = output / f"{theme_name.lower().replace(' ', '-')}-{appearance.lower()}.png"
                if not (args.skip_existing and screenshot.is_file()):
                    page.screenshot(path=str(screenshot), full_page=False, animations="disabled")
                results.append(
                    {
                        "theme": theme_name,
                        "appearance": appearance,
                        "screenshot": screenshot.relative_to(ROOT).as_posix(),
                        "horizontal_overflow": bool(overflow),
                        "focus_outline": outline,
                        "passed": not overflow and outline != "none",
                    }
                )
        browser.close()
    report = {
        "themes": len({row["theme"] for row in results}),
        "appearances": len({row["appearance"] for row in results}),
        "screenshots": len(results),
        "passed": all(bool(row["passed"]) for row in results),
        "results": results,
    }
    report_path = Path(args.json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("themes", "appearances", "screenshots", "passed")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
