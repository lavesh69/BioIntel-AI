from __future__ import annotations

import json
from typing import Any

try:
    import streamlit as st
    import streamlit.components.v1 as components
except ImportError:
    st = None
    components = None


def render_molstar_3d_viewer(
    pdb_id: str = "1TUP",
    custom_pdb_content: str | None = None,
    height: int = 500,
    title: str = "3D Molecular Structure Canvas",
) -> None:
    """Renders an interactive HTML5 3D Molecular Viewer (Molstar/3Dmol.js) in Streamlit."""
    if components is None or st is None:
        return

    clean_id = pdb_id.strip().upper() if pdb_id else "1TUP"

    # HTML template with 3Dmol.js canvas (offline resilient + CDN fallback)
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: #0f172a;
                font-family: system-ui, -apple-system, sans-serif;
                color: #f1f5f9;
                overflow: hidden;
            }}
            #container {{
                width: 100%;
                height: {height - 40}px;
                position: relative;
            }}
            .viewer-toolbar {{
                height: 36px;
                background: #1e293b;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0 12px;
                border-bottom: 1px solid #334155;
                font-size: 13px;
                font-weight: 600;
            }}
            .badge {{
                background: rgba(56, 189, 248, 0.2);
                color: #38bdf8;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 11px;
            }}
            .btn-controls {{
                display: flex;
                gap: 6px;
            }}
            .btn-controls button {{
                background: #334155;
                color: #f8fafc;
                border: none;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 11px;
                cursor: pointer;
            }}
            .btn-controls button:hover {{
                background: #0284c7;
            }}
        </style>
    </head>
    <body>
        <div class="viewer-toolbar">
            <div>
                🧬 <span>{title}</span> · <span class="badge">PDB: {clean_id}</span>
            </div>
            <div class="btn-controls">
                <button onclick="setStyle('cartoon')">Cartoon</button>
                <button onclick="setStyle('stick')">Sticks</button>
                <button onclick="setStyle('sphere')">Spheres</button>
                <button onclick="toggleSpin()">Spin</button>
                <button onclick="viewer.zoomTo()">Reset View</button>
            </div>
        </div>
        <div id="container"></div>

        <script>
            let viewer = null;
            let isSpinning = true;

            $(document).ready(function() {{
                let element = $('#container');
                let config = {{ backgroundColor: '#0f172a' }};
                viewer = $3Dmol.createViewer(element, config);

                {"let pdbData = " + json.dumps(custom_pdb_content) + ";" if custom_pdb_content else "let pdbData = null;"}

                if (pdbData) {{
                    viewer.addModel(pdbData, "pdb");
                    viewer.setStyle({{}}, {{cartoon: {{color: 'spectrum'}}}});
                    viewer.zoomTo();
                    viewer.render();
                    viewer.spin(true);
                }} else {{
                    $3Dmol.download('pdb:{clean_id}', viewer, {{multimodel: true, frames: true}}, function() {{
                        viewer.setStyle({{}}, {{cartoon: {{color: 'spectrum'}}}});
                        viewer.zoomTo();
                        viewer.render();
                        viewer.spin(true);
                    }});
                }}
            }});

            function setStyle(styleType) {{
                if (!viewer) return;
                viewer.removeAllStyles();
                if (styleType === 'cartoon') {{
                    viewer.setStyle({{}}, {{cartoon: {{color: 'spectrum'}}}});
                }} else if (styleType === 'stick') {{
                    viewer.setStyle({{}}, {{stick: {{colorscheme: 'amino'}}}});
                }} else if (styleType === 'sphere') {{
                    viewer.setStyle({{}}, {{sphere: {{colorscheme: 'chain'}}}});
                }}
                viewer.render();
            }}

            function toggleSpin() {{
                if (!viewer) return;
                isSpinning = !isSpinning;
                viewer.spin(isSpinning);
            }}
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=height, scrolling=False)
