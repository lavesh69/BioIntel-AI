# Visual Regression Testing

Playwright renders the real Streamlit application at deterministic desktop and mobile viewports. Reviewed PNG baselines are stored under `visual/baselines`. The test disables animations and unstable toolbar content, then enforces a bounded pixel-difference threshold. CI uploads actual screenshots and diff images on failure.

Update baselines only after reviewing the rendered change:

```bash
python scripts/update_visual_baselines.py
```
