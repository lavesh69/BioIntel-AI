# Visual regression qualification

BioIntel uses two complementary visual gates:

1. **Semantic pixel baselines** run on every test environment without a browser. Streamlit `AppTest` executes the real pages, rejects runtime exceptions/fatal error text, snapshots component structure and visible content, and renders deterministic PNG contracts. Nine approved semantic scenarios cover Home desktop/mobile, Quality Center, Studio, Compliance readiness, Model Training, DTI Predictor, Data Quality and Experiment Registry.
2. **Browser screenshots** run in GitHub Actions with Playwright Chromium. Eight browser journeys include Home desktop/mobile, Quality Center, Studio, Compliance readiness, Model Training, DTI Predictor and Data Quality. The runner disables animation, rejects Streamlit exceptions before capture, stores artifacts and compares approved browser baselines when present.

Update all reviewed baselines deliberately:

```bash
python scripts/update_visual_baselines.py
```

Update only the portable semantic baselines when a managed machine blocks local browsers:

```bash
BIOINTEL_SKIP_BROWSER_BASELINES=1 python scripts/update_visual_baselines.py
```

Browser baselines are written only after health assertions pass, and `manifest.json` binds every approved image to its route, viewport and SHA-256. Never auto-accept visual changes in pull-request CI; inspect screenshots and diffs first.
