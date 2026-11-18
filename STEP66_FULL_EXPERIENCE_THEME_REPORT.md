# Step 66 — Full Experience Theme System

## Goal

Step 65 preserved 17 palettes and 11 fonts, but the user correctly identified that most themes still shared the same layout skeleton. Step 66 converts every existing theme into a complete desktop visual experience while preserving scientific functionality, mobile-specific layout behavior and all font options.

## What now changes with a theme

A theme now controls much more than colour:

- Desktop content width and visual density
- Sidebar width, active navigation shape and surface treatment
- Hero-panel composition, geometry and decorative language
- Card, KPI, form, chart and table surfaces
- Border thickness, corner system, depth and shadow language
- Button gradients, shape and interaction feedback
- Input, tab, chip and status-badge geometry
- Background pattern and atmosphere
- Plotly grid, legend and plot-surface treatment
- Light, dark and system appearance variants

The experience layer is restricted to desktop widths (`min-width: 761px`). Existing mobile-specific breakpoints and layouts are not redesigned.

## Preserved options

- Themes: **17/17 preserved**
- Fonts: **11/11 preserved**
- Appearance modes: Dark, Light and System
- Accessibility controls: text scale, compact spacing, higher contrast, reduced motion and chart colour-vision profiles

## Full experience catalogue

| Existing theme option | New complete experience | Visual language |
|---|---|---|
| Executive | Corporate Command | Disciplined executive grid, left-accent cards, decisive controls |
| Clinical | Clinical Cleanroom | Sterile minimal surfaces, low decoration and calm clinical hierarchy |
| Regulatory | Compliance Ledger | Squared audit-led layout, ledger rules and formal labels |
| Aurora | Fluid Aurora | Organic gradients, asymmetric geometry and floating exploratory cards |
| Ocean | Oceanic Panels | Layered blue panels, wave geometry and calm analysis surfaces |
| Emerald | Bio Organic | Leaf-like geometry and living-system biotechnology styling |
| Rose | Rose Atelier | Feminine professional rose-gold editorial styling |
| Midnight Graphite | Obsidian Executive | Masculine professional graphite, metallic rules and clipped geometry |
| Nordic Frost | Nordic Minimal | Airy minimalist layout with flat low-distraction surfaces |
| Solarized Lab | Scientific Editorial | Warm manuscript-inspired layout with editorial rules |
| Deep Space | Modern Tech | Futuristic technical grid, clipped corners and luminous controls |
| BioMatrix | Bio Terminal | Dense scientific terminal language and framed metrics |
| Royal Amethyst | Luxury Glass | Premium jewel glassmorphism and elevated presentation cards |
| Ember Forge | Industrial Forge | Masculine industrial geometry and robust operational controls |
| Arctic Glass | Pure Glass | Full frosted-glass surface system with luminous cyan depth |
| Sakura Research | Sakura Studio | Feminine modern scientific styling with soft structured panels |
| Monochrome Pro | Monochrome Brutalist | Black-and-white hard hierarchy with zero decorative colour noise |

The feminine and masculine labels describe optional visual styling only; no workflow or feature is restricted by gender.

## Appearance Studio improvements

- Selector help now explains complete experience changes.
- Current preview shows the experience title and archetype.
- Theme catalogue cards show experience, target use and visual summary.
- Theme metrics show the active archetype separately from colour palette and font.
- Existing phrase markers required by historical regression tests remain available.

## Chart differentiation

Plotly styling is now experience-aware:

- Clinical, Nordic, editorial and monochrome themes use restrained grid treatments.
- Modern Tech, Bio Terminal, Obsidian and Industrial themes use stronger technical grids and compact legends.
- Aurora, Rose, Sakura, Luxury Glass and Pure Glass use softer plot surfaces and lighter grids.
- All chart colours still respect the selected palette and colour-vision profile.

## Accessibility and compatibility

- Full experience CSS is desktop-only.
- Light and System modes receive light surfaces, readable dark text and theme-aware geometry.
- Reduced-motion mode disables experience animations and transitions.
- Existing high-contrast and text-scale controls continue to operate.
- Cached scientific logic, databases, APIs and analytical workflows are unchanged.

## Verification

- Ruff repository scan: passed
- Python compilation: passed
- Focused UI/theme tests: **67/67 passed**
- New Step 66 tests: **10/10 passed**
- Representative runtime themes: **8/8 passed**
- Theme profiles: **17/17 complete**
- Structural signatures: **17/17 unique**
- Font options: **11/11 preserved**
- Store verification: **0 internally fixable failures**
- SQLite databases: **22/22 healthy**
- Foreign-key violations: **0**

## Scope boundary

This release intentionally does not redesign mobile-specific layouts. It also does not remove or reduce any theme, font, scientific module or accessibility option.
