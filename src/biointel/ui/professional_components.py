from __future__ import annotations

import streamlit as st
from typing import Dict, List, Any, Optional

def render_module_hero(title: str, subtitle: str, icon: str = "🔬", badge_text: str = "Production Standard", actions: Optional[List[Dict[str, Any]]] = None):
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #161b22 0%, #0d1117 100%); border: 1px solid rgba(56, 139, 253, 0.2); border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 8px 24px rgba(0,0,0,0.3);">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 16px;">
                <div style="font-size: 40px; background: rgba(56, 139, 253, 0.1); border-radius: 12px; padding: 12px 16px; border: 1px solid rgba(56, 139, 253, 0.3);">
                    {icon}
                </div>
                <div>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <h1 style="margin: 0; font-size: 26px; font-weight: 700; color: #f0f6fc;">{title}</h1>
                        <span style="background: rgba(35, 134, 54, 0.2); border: 1px solid #238636; color: #3fb950; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 12px;">
                            {badge_text}
                        </span>
                    </div>
                    <p style="margin: 6px 0 0 0; color: #8b949e; font-size: 14px;">{subtitle}</p>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_metric_cards(metrics: List[Dict[str, Any]]):
    cols = st.columns(len(metrics))
    for idx, m in enumerate(metrics):
        with cols[idx]:
            st.markdown(f"""
            <div style="background: #161b22; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 16px; text-align: left;">
                <div style="font-size: 12px; color: #8b949e; font-weight: 600; text-transform: uppercase;">{m.get('label', '')}</div>
                <div style="font-size: 24px; font-weight: 800; color: #58a6ff; margin: 4px 0;">{m.get('value', '0')}</div>
                <div style="font-size: 12px; color: #3fb950;">{m.get('delta', '')}</div>
            </div>
            """, unsafe_allow_html=True)

def render_setup_required_banner(feature_name: str, missing_dependency: str, instructions: str):
    st.markdown(f"""
    <div style="background: rgba(210, 153, 34, 0.15); border: 1px solid #d29922; border-radius: 10px; padding: 16px; margin: 16px 0; color: #e3b341;">
        <div style="font-weight: 700; font-size: 15px; display: flex; align-items: center; gap: 8px;">
            ⚠️ SETUP REQUIRED — {feature_name}
        </div>
        <div style="font-size: 13px; margin-top: 6px; color: #c9d1d9;">
            This feature requires <strong>{missing_dependency}</strong> which is not currently detected in your local runtime environment.
        </div>
        <div style="font-size: 12px; margin-top: 8px; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 6px; font-family: monospace;">
            Setup Instructions: {instructions}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_empty_state(title: str = "No Records Found", description: str = "Click 'Create Record' or 'Load Demo Data' to populate this workspace."):
    st.markdown(f"""
    <div style="border: 2px dashed rgba(255,255,255,0.1); border-radius: 12px; padding: 40px; text-align: center; margin: 24px 0;">
        <div style="font-size: 48px; margin-bottom: 12px;">📭</div>
        <h3 style="color: #f0f6fc; margin: 0;">{title}</h3>
        <p style="color: #8b949e; margin-top: 8px; font-size: 14px;">{description}</p>
    </div>
    """, unsafe_allow_html=True)
