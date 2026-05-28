"""
ui/pages/02_quarter_car.py
===========================
SuspensionLab PRO — Quarter Car Simulation Dashboard

Streamlit page for the complete 2-DOF quarter car analysis workflow.

Page flow
---------
1. Sidebar  — parameter input panels (expanders)
2. KPI strip — six telemetry metric cards
3. Overview  — 4-panel compact dashboard figure
4. Detail    — full-resolution individual plots
5. Insights  — automatic engineering diagnostics
6. Export    — CSV / JSON / HTML download

Physics API used
----------------
  QuarterCarParams(m_s, m_u, k_s, c, k_t, MR, c_t)
  RoadProfile(profile_type, amplitude, frequency, duration)
  run_quarter_car_analysis(p, profile, f_min, f_max, n_freq)
  → QuarterCarResult  (all 30 fields)

Visualization API used
-----------------------
  create_overview_dashboard(result)       → go.Figure
  create_transmissibility_plot(result)    → go.Figure
  create_bode_plot(result)                → go.Figure
  create_step_response_plot(result)       → go.Figure
  create_suspension_travel_plot(result)   → go.Figure
  create_tire_load_plot(result)           → go.Figure
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

# ── Repository root on path ───────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from physics.quarter_car import (
    QuarterCarParams,
    QuarterCarResult,
    RoadProfile,
    run_quarter_car_analysis,
)
from visualization.telemetry_plots import (
    create_bode_plot,
    create_impulse_response_plot,
    create_overview_dashboard,
    create_step_response_plot,
    create_suspension_travel_plot,
    create_tire_load_plot,
    create_transmissibility_plot,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page-level Streamlit configuration
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title       = "Quarter Car — SuspensionLab PRO",
    page_icon        = "🏎️",
    layout           = "wide",
    initial_sidebar_state = "expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS injection — F1 telemetry dashboard aesthetic
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* ── Import fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=JetBrains+Mono:wght@300;400;500;700&family=Orbitron:wght@400;700&display=swap');

/* ── Root palette ── */
:root {
    --bg-primary:    #07090D;
    --bg-secondary:  #0D1117;
    --bg-card:       #111820;
    --bg-panel:      #0F1419;
    --cyan:          #00E5FF;
    --cyan-dim:      rgba(0,229,255,0.10);
    --cyan-glow:     rgba(0,229,255,0.28);
    --red:           #FF2D55;
    --amber:         #FFB800;
    --green:         #00FF87;
    --purple:        #BF5AF2;
    --border:        #1A2535;
    --border-bright: #243044;
    --text-pri:      #DCE8F5;
    --text-sec:      #5A7A99;
    --mono:          'JetBrains Mono', monospace;
    --label:         'Rajdhani', sans-serif;
    --display:       'Orbitron', monospace;
}

/* ── Global app background ── */
.stApp { background-color: var(--bg-primary) !important; }
section[data-testid="stSidebar"] { background-color: #0A0D14 !important; border-right: 1px solid var(--border-bright); }
section[data-testid="stSidebar"] * { color: var(--text-pri) !important; }

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden !important; }
.block-container { padding-top: 1.4rem !important; padding-bottom: 2rem !important; }

/* ── Page title block ── */
.slp-title {
    font-family: var(--display);
    font-size: 1.35rem;
    font-weight: 700;
    color: var(--cyan);
    letter-spacing: 3px;
    text-shadow: 0 0 22px var(--cyan-glow);
    margin-bottom: 0;
}
.slp-subtitle {
    font-family: var(--mono);
    font-size: 0.72rem;
    color: var(--text-sec);
    letter-spacing: 1.8px;
    margin-top: 2px;
    margin-bottom: 0;
}
.slp-divider {
    border: none;
    border-top: 1px solid var(--border-bright);
    margin: 8px 0 16px 0;
}

/* ── Module tag ── */
.mod-tag {
    display: inline-block;
    font-family: var(--mono);
    font-size: 0.62rem;
    color: var(--cyan);
    background: var(--cyan-dim);
    border: 1px solid rgba(0,229,255,0.22);
    padding: 2px 10px;
    letter-spacing: 2px;
    margin-bottom: 6px;
}

/* ── Section header ── */
.section-hdr {
    font-family: var(--mono);
    font-size: 0.70rem;
    color: var(--text-sec);
    letter-spacing: 2.5px;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
    padding-bottom: 4px;
    margin: 18px 0 10px 0;
}

/* ── KPI card strip ── */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 6px;
    margin-bottom: 14px;
}
.kpi-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 2.5px solid var(--cyan);
    padding: 10px 12px 8px;
    position: relative;
}
.kpi-card.amber { border-left-color: var(--amber); }
.kpi-card.red   { border-left-color: var(--red);   }
.kpi-card.green { border-left-color: var(--green);  }
.kpi-card.purple{ border-left-color: var(--purple); }

.kpi-label {
    font-family: var(--mono);
    font-size: 0.60rem;
    color: var(--text-sec);
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.kpi-value {
    font-family: var(--mono);
    font-size: 1.35rem;
    font-weight: 700;
    color: var(--cyan);
    line-height: 1.05;
}
.kpi-card.amber .kpi-value { color: var(--amber); }
.kpi-card.red   .kpi-value { color: var(--red);   }
.kpi-card.green .kpi-value { color: var(--green);  }
.kpi-card.purple.kpi-value { color: var(--purple); }
.kpi-unit {
    font-family: var(--mono);
    font-size: 0.62rem;
    color: var(--text-sec);
}
.kpi-sub {
    font-family: var(--mono);
    font-size: 0.58rem;
    color: var(--text-sec);
    margin-top: 3px;
    opacity: 0.75;
}

/* ── Insight cards ── */
.insight-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-top: 6px;
}
.insight-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-top: 2px solid var(--cyan);
    padding: 10px 12px;
}
.insight-card.warn { border-top-color: var(--amber); }
.insight-card.crit { border-top-color: var(--red);   }
.insight-card.good { border-top-color: var(--green);  }

.insight-title {
    font-family: var(--mono);
    font-size: 0.65rem;
    letter-spacing: 1.5px;
    color: var(--text-sec);
    text-transform: uppercase;
    margin-bottom: 4px;
}
.insight-rating {
    font-family: var(--label);
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--cyan);
    margin-bottom: 3px;
}
.insight-card.warn .insight-rating { color: var(--amber); }
.insight-card.crit .insight-rating { color: var(--red);   }
.insight-card.good .insight-rating { color: var(--green);  }
.insight-body {
    font-family: var(--mono);
    font-size: 0.65rem;
    color: var(--text-sec);
    line-height: 1.55;
}

/* ── Sidebar parameter labels ── */
.sidebar-sec {
    font-family: var(--mono);
    font-size: 0.62rem;
    color: #00E5FF;
    letter-spacing: 1.8px;
    text-transform: uppercase;
    margin: 2px 0 6px;
}

/* ── Equation block ── */
.eq-block {
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-left: 2px solid var(--cyan);
    padding: 9px 12px;
    font-family: var(--mono);
    font-size: 0.68rem;
    color: var(--cyan);
    line-height: 1.75;
    margin: 8px 0;
}

/* ── Run banner (post-run info bar) ── */
.run-banner {
    background: linear-gradient(90deg, rgba(0,229,255,0.07) 0%, transparent 70%);
    border: 1px solid var(--border-bright);
    border-left: 3px solid var(--cyan);
    padding: 7px 14px;
    font-family: var(--mono);
    font-size: 0.68rem;
    color: var(--text-sec);
    margin-bottom: 12px;
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
}
.run-banner span { color: var(--cyan); }

/* ── Streamlit widget override ── */
.stSlider > div { padding-top: 0 !important; }
div[data-testid="stNumberInput"] input {
    background: rgba(0,0,0,0.35) !important;
    border: 1px solid var(--border-bright) !important;
    color: var(--cyan) !important;
    font-family: var(--mono) !important;
    font-size: 0.80rem !important;
}
div[data-testid="stSelectbox"] > div {
    background: rgba(0,0,0,0.35) !important;
    border: 1px solid var(--border-bright) !important;
}
.stButton > button {
    background: linear-gradient(135deg, #00E5FF, #0099CC) !important;
    color: #000 !important;
    font-family: var(--display) !important;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    letter-spacing: 2px !important;
    border: none !important;
    padding: 10px 28px !important;
    clip-path: polygon(8px 0%, 100% 0%, calc(100% - 8px) 100%, 0% 100%);
    transition: box-shadow 0.2s !important;
}
.stButton > button:hover {
    box-shadow: 0 0 18px rgba(0,229,255,0.4) !important;
}
.stExpander {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
}
div[data-testid="stExpander"] summary {
    font-family: var(--mono) !important;
    font-size: 0.72rem !important;
    letter-spacing: 1.5px !important;
    color: var(--cyan) !important;
}
.stDownloadButton > button {
    background: transparent !important;
    border: 1px solid var(--border-bright) !important;
    color: var(--text-sec) !important;
    font-family: var(--mono) !important;
    font-size: 0.65rem !important;
    letter-spacing: 1px !important;
}
.stDownloadButton > button:hover {
    border-color: var(--cyan) !important;
    color: var(--cyan) !important;
}
</style>
"""

st.markdown(_CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Constants & Defaults
# ─────────────────────────────────────────────────────────────────────────────

_PROFILE_MAP: dict[str, str] = {
    "Step Bump"       : "step",
    "Sine Wave Road"  : "sine",
    "Pothole"         : "pothole",
    "Random ISO Road" : "random",
    "Impulse"         : "impulse",
}

_PROFILE_DESCRIPTIONS: dict[str, str] = {
    "Step Bump"      : "Heaviside step at t=0.5 s — simulates kerb drop or lane change.",
    "Sine Wave Road" : "Continuous sinusoidal road — sweep resonance at set frequency.",
    "Pothole"        : "Negative half-sine depression at t=0.30–0.65 s.",
    "Random ISO Road": "Multi-harmonic ISO 8608 inspired rough road surface.",
    "Impulse"        : "Narrow Gaussian impulse — NVH harshness test.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper — HTML component renderers
# ─────────────────────────────────────────────────────────────────────────────

def _kpi_card(
    label: str,
    value: str,
    unit: str,
    sub: str,
    accent: str = "cyan",   # cyan | amber | red | green | purple
) -> str:
    return (
        f'<div class="kpi-card {accent}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-unit">{unit}</div>'
        f'<div class="kpi-sub">{sub}</div>'
        f'</div>'
    )


def _insight_card(
    title: str,
    rating: str,
    body: str,
    severity: str = "cyan",  # good | warn | crit
) -> str:
    return (
        f'<div class="insight-card {severity}">'
        f'<div class="insight-title">{title}</div>'
        f'<div class="insight-rating">{rating}</div>'
        f'<div class="insight-body">{body}</div>'
        f'</div>'
    )


def _section(label: str) -> None:
    st.markdown(f'<div class="section-hdr">{label}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# KPI Telemetry Strip
# ─────────────────────────────────────────────────────────────────────────────

def _render_kpi_strip(r: QuarterCarResult) -> None:
    """Render the six-card KPI telemetry strip as a single HTML block."""

    # ── fn,s — sprung natural frequency ──
    fn_s_sub = (
        "ROAD CAR" if r.f_n_s < 1.5
        else "SPORT" if r.f_n_s < 2.5
        else "RACE / FS"
    )
    fn_s_accent = "green" if r.f_n_s < 1.5 else "cyan" if r.f_n_s < 3.5 else "amber"

    # ── fn,u — unsprung natural frequency ──
    ratio = r.f_n_u / r.f_n_s if r.f_n_s > 0 else 0.0
    fnu_sub = f"SEP RATIO {ratio:.1f}×"
    fnu_accent = "green" if ratio >= 3.0 else "amber" if ratio >= 2.5 else "red"

    # ── zeta_s — damping ratio ──
    if r.zeta_s < 0.20:
        z_accent, z_sub = "red",   "CRITICAL — UNDERDAMPED"
    elif r.zeta_s < 0.28:
        z_accent, z_sub = "amber", "UNDERDAMPED"
    elif r.zeta_s <= 0.65:
        z_accent, z_sub = "green", "OPTIMAL RANGE"
    elif r.zeta_s <= 0.85:
        z_accent, z_sub = "amber", "OVERDAMPED"
    else:
        z_accent, z_sub = "red",   "CRITICALLY OVERDAMPED"

    # ── peak transmissibility ──
    pk = r.peak_transmissibility
    if pk < 1.8:
        pk_accent, pk_sub = "green", f"@ {r.freq_at_peak_tx:.2f} Hz"
    elif pk < 2.8:
        pk_accent, pk_sub = "amber", f"@ {r.freq_at_peak_tx:.2f} Hz — MODERATE"
    else:
        pk_accent, pk_sub = "red",   f"@ {r.freq_at_peak_tx:.2f} Hz — HIGH"

    # ── RMS body acceleration (ISO 2631-1) ──
    rms_a = r.rms_body_accel
    if rms_a < 0.315:
        a_accent, a_sub = "green", "ISO 2631 — NOT UNCOMFORTABLE"
    elif rms_a < 0.630:
        a_accent, a_sub = "amber", "ISO 2631 — SLIGHTLY UNCO."
    elif rms_a < 1.000:
        a_accent, a_sub = "amber", "ISO 2631 — FAIRLY UNCO."
    else:
        a_accent, a_sub = "red",   "ISO 2631 — UNCOMFORTABLE"

    # ── Peak suspension travel ──
    pk_tr_mm = r.peak_susp_travel * 1e3
    if pk_tr_mm < 30.0:
        tr_accent, tr_sub = "green", "WITHIN NOMINAL STROKE"
    elif pk_tr_mm < 55.0:
        tr_accent, tr_sub = "amber", "APPROACHING BUMP STOP"
    else:
        tr_accent, tr_sub = "red",   "EXCEEDS TYPICAL STROKE"

    cards = "".join([
        _kpi_card("SPRUNG FREQ  fn,s", f"{r.f_n_s:.3f}", "Hz",
                  fn_s_sub, fn_s_accent),
        _kpi_card("UNSPRUNG FREQ  fn,u", f"{r.f_n_u:.2f}", "Hz",
                  fnu_sub, fnu_accent),
        _kpi_card("DAMPING RATIO  ζ", f"{r.zeta_s:.4f}", "—",
                  z_sub, z_accent),
        _kpi_card("PEAK TRANSMISSIBILITY", f"{pk:.3f}", "×",
                  pk_sub, pk_accent),
        _kpi_card("RMS BODY ACCEL", f"{rms_a:.4f}", "m/s²",
                  a_sub, a_accent),
        _kpi_card("PEAK TRAVEL  zs−zu", f"{pk_tr_mm:.1f}", "mm",
                  tr_sub, tr_accent),
    ])

    st.markdown(f'<div class="kpi-strip">{cards}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Run Banner
# ─────────────────────────────────────────────────────────────────────────────

def _render_run_banner(r: QuarterCarResult, elapsed_ms: float) -> None:
    """Single-line telemetry status bar rendered after a successful run."""
    kw_str  = f"{r.k_w:,.0f}"
    cc_str  = f"{r.c_crit_s:,.0f}"
    t_pts   = len(r.time)
    f_pts   = len(r.freq_hz)

    banner = (
        f'<div class="run-banner">'
        f'STATUS: <span>ANALYSIS COMPLETE</span> &nbsp;|&nbsp;'
        f'kw = <span>{kw_str} N/m</span> &nbsp;|&nbsp;'
        f'c_crit,s = <span>{cc_str} Ns/m</span> &nbsp;|&nbsp;'
        f'fn,u/fn,s = <span>{r.f_n_u/r.f_n_s:.2f}×</span> &nbsp;|&nbsp;'
        f'TIME PTS = <span>{t_pts:,}</span> &nbsp;|&nbsp;'
        f'FREQ PTS = <span>{f_pts:,}</span> &nbsp;|&nbsp;'
        f'ELAPSED = <span>{elapsed_ms:.0f} ms</span>'
        f'</div>'
    )
    st.markdown(banner, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Engineering Insights
# ─────────────────────────────────────────────────────────────────────────────

def _render_insights(r: QuarterCarResult) -> None:
    """
    Automatic engineering diagnostics derived exclusively from
    fields present on QuarterCarResult.
    """
    _section("◈  ENGINEERING DIAGNOSTICS")

    cards_html: list[str] = []

    # ── 1. Ride Comfort (ISO 2631-1) ─────────────────────────────────────
    rms_a = r.rms_body_accel
    if rms_a < 0.315:
        c1 = _insight_card(
            "RIDE COMFORT  (ISO 2631-1)", "EXCELLENT",
            f"RMS body accel = {rms_a:.4f} m/s² &lt; 0.315 threshold.<br>"
            f"Isolation effective across excitation bandwidth.",
            "good",
        )
    elif rms_a < 0.630:
        c1 = _insight_card(
            "RIDE COMFORT  (ISO 2631-1)", "ACCEPTABLE",
            f"RMS = {rms_a:.4f} m/s² (0.315–0.63 band).<br>"
            f"Slightly uncomfortable for continuous exposure.<br>"
            f"Consider reducing spring rate or adjusting damping.",
            "warn",
        )
    elif rms_a < 1.000:
        c1 = _insight_card(
            "RIDE COMFORT  (ISO 2631-1)", "HARSH",
            f"RMS = {rms_a:.4f} m/s² — fairly uncomfortable.<br>"
            f"Significant retuning required for road use.<br>"
            f"Acceptable for track / Formula Student application.",
            "warn",
        )
    else:
        c1 = _insight_card(
            "RIDE COMFORT  (ISO 2631-1)", "UNACCEPTABLE",
            f"RMS = {rms_a:.4f} m/s² — classified UNCOMFORTABLE.<br>"
            f"System oscillating excessively. Check damping immediately.<br>"
            f"c_crit,s = {r.c_crit_s:,.0f} Ns/m — current ζ = {r.zeta_s:.4f}.",
            "crit",
        )
    cards_html.append(c1)

    # ── 2. Damping Assessment ─────────────────────────────────────────────
    z = r.zeta_s
    cc = r.c_crit_s
    pct_of_crit = z * 100.0
    if z < 0.20:
        c2 = _insight_card(
            "SUSPENSION DAMPING", "CRITICALLY UNDERDAMPED",
            f"ζ = {z:.4f} ({pct_of_crit:.1f}% of critical).<br>"
            f"Resonance amplification ≫ 1 — oscillation risk.<br>"
            f"Increase damper: c_crit = {cc:,.0f} Ns/m. "
            f"Target c ≈ {cc*0.32:,.0f}–{cc*0.45:,.0f} Ns/m.",
            "crit",
        )
    elif z < 0.28:
        c2 = _insight_card(
            "SUSPENSION DAMPING", "UNDERDAMPED",
            f"ζ = {z:.4f}. Target 0.28–0.45 for balanced ride.<br>"
            f"Increase damping coefficient by ~{max(0,(0.30-z)/z*100):.0f}%.<br>"
            f"Recommended c ≈ {cc*0.30:,.0f}–{cc*0.45:,.0f} Ns/m.",
            "warn",
        )
    elif z <= 0.65:
        c2 = _insight_card(
            "SUSPENSION DAMPING", "OPTIMAL",
            f"ζ = {z:.4f} — within 0.28–0.65 engineering target.<br>"
            f"Good balance of isolation and attenuation.<br>"
            f"c_crit = {cc:,.0f} Ns/m. No action required.",
            "good",
        )
    elif z <= 0.85:
        c2 = _insight_card(
            "SUSPENSION DAMPING", "OVERDAMPED",
            f"ζ = {z:.4f} — above 0.65 optimal ceiling.<br>"
            f"Harsh over sharp inputs; poor secondary ride.<br>"
            f"Reduce damping by ~{(z-0.45)/z*100:.0f}% toward "
            f"c ≈ {cc*0.45:,.0f} Ns/m.",
            "warn",
        )
    else:
        c2 = _insight_card(
            "SUSPENSION DAMPING", "CRITICALLY OVERDAMPED",
            f"ζ = {z:.4f} — severely overdamped.<br>"
            f"Suspension acts nearly rigid — no vibration isolation.<br>"
            f"Reduce to target ζ = 0.30–0.45.",
            "crit",
        )
    cards_html.append(c2)

    # ── 3. Wheel Hop Risk ─────────────────────────────────────────────────
    ratio = r.f_n_u / r.f_n_s if r.f_n_s > 0 else 0.0
    if ratio >= 3.5:
        c3 = _insight_card(
            "WHEEL HOP RISK", "LOW",
            f"fn,u/fn,s = {ratio:.2f}× — modes well separated.<br>"
            f"fn,u = {r.f_n_u:.2f} Hz (wheel hop) is decoupled<br>"
            f"from fn,s = {r.f_n_s:.2f} Hz (ride mode).",
            "good",
        )
    elif ratio >= 3.0:
        c3 = _insight_card(
            "WHEEL HOP RISK", "ACCEPTABLE",
            f"fn,u/fn,s = {ratio:.2f}× — marginal separation.<br>"
            f"Target ≥ 3.5× for clean mode decoupling.<br>"
            f"Monitor transmissibility peak at {r.freq_at_peak_tx:.2f} Hz.",
            "warn",
        )
    elif ratio >= 2.5:
        c3 = _insight_card(
            "WHEEL HOP RISK", "ELEVATED",
            f"fn,u/fn,s = {ratio:.2f}× — insufficient separation.<br>"
            f"Modal coupling can degrade isolation and stability.<br>"
            f"Increase tire stiffness kt or reduce unsprung mass mu.",
            "warn",
        )
    else:
        c3 = _insight_card(
            "WHEEL HOP RISK", "HIGH — MODAL COUPLING",
            f"fn,u/fn,s = {ratio:.2f}× — modes are interacting.<br>"
            f"Sprung / unsprung resonances overlap. Significant<br>"
            f"transmissibility peaks expected. Retune immediately.",
            "crit",
        )
    cards_html.append(c3)

    # ── 4. Suspension Travel Utilisation ─────────────────────────────────
    pk_tr_mm  = r.peak_susp_travel * 1e3
    rms_tr_mm = r.rms_susp_travel  * 1e3
    crest     = pk_tr_mm / rms_tr_mm if rms_tr_mm > 0 else 0.0
    if pk_tr_mm < 25.0:
        c4 = _insight_card(
            "SUSPENSION TRAVEL", "UNDERUTILISED",
            f"Peak = {pk_tr_mm:.1f} mm | RMS = {rms_tr_mm:.2f} mm.<br>"
            f"Suspension is very stiff — consider softening spring rate<br>"
            f"to improve road-following and contact patch load.",
            "warn",
        )
    elif pk_tr_mm < 50.0:
        c4 = _insight_card(
            "SUSPENSION TRAVEL", "NOMINAL",
            f"Peak = {pk_tr_mm:.1f} mm | RMS = {rms_tr_mm:.2f} mm.<br>"
            f"Crest factor = {crest:.2f}× (peak/RMS).<br>"
            f"Travel within expected operational window.",
            "good",
        )
    elif pk_tr_mm < 80.0:
        c4 = _insight_card(
            "SUSPENSION TRAVEL", "HIGH — VERIFY STROKE",
            f"Peak = {pk_tr_mm:.1f} mm | RMS = {rms_tr_mm:.2f} mm.<br>"
            f"Approaching typical bump-stop limit (~60–80 mm).<br>"
            f"Increase wheel rate or install progressive bumpstop.",
            "warn",
        )
    else:
        c4 = _insight_card(
            "SUSPENSION TRAVEL", "EXCEEDS STROKE",
            f"Peak = {pk_tr_mm:.1f} mm — beyond typical stroke limit.<br>"
            f"Bump-stop contact expected → non-linear spring kick.<br>"
            f"Wheel rate k_w = {r.k_w:,.0f} N/m — increase significantly.",
            "crit",
        )
    cards_html.append(c4)

    # ── 5. Tire Contact Quality ───────────────────────────────────────────
    rms_fl  = r.rms_tire_load
    pk_fl   = float(np.max(np.abs(r.tire_load_var)))

    if rms_fl < 400.0:
        c5 = _insight_card(
            "TIRE CONTACT QUALITY", "EXCELLENT",
            f"RMS ΔFz = {rms_fl:.1f} N | Peak ΔFz = {pk_fl:.1f} N.<br>"
            f"Low tire load variation — good grip consistency.<br>"
            f"Wheel maintains stable contact patch pressure.",
            "good",
        )
    elif rms_fl < 900.0:
        c5 = _insight_card(
            "TIRE CONTACT QUALITY", "ACCEPTABLE",
            f"RMS ΔFz = {rms_fl:.1f} N | Peak ΔFz = {pk_fl:.1f} N.<br>"
            f"Moderate load variation affects average lateral grip.<br>"
            f"Jensen's inequality: avg grip &lt; grip at static load.",
            "warn",
        )
    else:
        c5 = _insight_card(
            "TIRE CONTACT QUALITY", "POOR — HIGH VARIATION",
            f"RMS ΔFz = {rms_fl:.1f} N | Peak ΔFz = {pk_fl:.1f} N.<br>"
            f"High load variation severely degrades traction.<br>"
            f"Increase tire stiffness or reduce unsprung mass.",
            "crit",
        )
    cards_html.append(c5)

    # ── 6. Transmissibility Assessment ───────────────────────────────────
    pk_tx = r.peak_transmissibility
    if pk_tx < 1.6:
        c6 = _insight_card(
            "TRANSMISSIBILITY PEAK", "LOW — WELL DAMPED",
            f"Peak |H| = {pk_tx:.3f}× @ {r.freq_at_peak_tx:.2f} Hz.<br>"
            f"Low resonance amplification — good isolation behaviour.<br>"
            f"Damping effectively controls resonance amplitude.",
            "good",
        )
    elif pk_tx < 2.5:
        c6 = _insight_card(
            "TRANSMISSIBILITY PEAK", "MODERATE",
            f"Peak |H| = {pk_tx:.3f}× @ {r.freq_at_peak_tx:.2f} Hz.<br>"
            f"Moderate resonance amplification. Typical for road setups.<br>"
            f"Consider increasing damping if comfort is priority.",
            "warn",
        )
    else:
        c6 = _insight_card(
            "TRANSMISSIBILITY PEAK", "HIGH — RESONANCE RISK",
            f"Peak |H| = {pk_tx:.3f}× @ {r.freq_at_peak_tx:.2f} Hz.<br>"
            f"Resonant amplification ≫ 2.5× — severe oscillation.<br>"
            f"Significantly increase damping (c → {r.c_crit_s*0.35:,.0f} Ns/m).",
            "crit",
        )
    cards_html.append(c6)

    # Render 2 rows of 3
    row1 = "".join(cards_html[:3])
    row2 = "".join(cards_html[3:])
    st.markdown(
        f'<div class="insight-grid">{row1}</div>'
        f'<div class="insight-grid" style="margin-top:8px">{row2}</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Export Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_csv(r: QuarterCarResult) -> bytes:
    """
    Assemble a time-domain telemetry CSV from all time-series arrays.
    Columns: time, z_s, z_u, z_r, dz_s, dz_u, ddz_s,
             susp_travel, tire_defl, tire_load_var
    """
    df = pd.DataFrame({
        "time_s":         r.time,
        "z_s_m":          r.z_s,
        "z_u_m":          r.z_u,
        "z_r_m":          r.z_r,
        "dz_s_ms":        r.dz_s,
        "dz_u_ms":        r.dz_u,
        "ddz_s_ms2":      r.ddz_s,
        "susp_travel_m":  r.susp_travel,
        "tire_defl_m":    r.tire_defl,
        "tire_load_var_N":r.tire_load_var,
    })
    return df.to_csv(index=False).encode("utf-8")


def _build_freq_csv(r: QuarterCarResult) -> bytes:
    """Frequency-domain CSV: freq, transmissibility body/wheel, bode mag/phase."""
    df = pd.DataFrame({
        "freq_hz":             r.freq_hz,
        "transmissibility_body":  r.transmissibility_body,
        "transmissibility_wheel": r.transmissibility_wheel,
        "bode_magnitude_db":   r.bode_magnitude_db,
        "bode_phase_deg":      r.bode_phase_deg,
    })
    return df.to_csv(index=False).encode("utf-8")


def _build_json(r: QuarterCarResult, params: QuarterCarParams,
                profile: RoadProfile) -> bytes:
    """
    Scalar summary metrics + input parameters as JSON.
    Only serialises Python floats/ints — no numpy arrays.
    """
    summary: dict[str, Any] = {
        "inputs": {
            "m_s_kg":   params.m_s,
            "m_u_kg":   params.m_u,
            "k_s_Nm":   params.k_s,
            "c_Nsm":    params.c,
            "k_t_Nm":   params.k_t,
            "MR":       params.MR,
            "c_t_Nsm":  params.c_t,
            "k_w_Nm":   round(params.k_w, 3),
            "road_profile":  profile.profile_type,
            "amplitude_m":   profile.amplitude,
            "frequency_Hz":  profile.frequency,
            "duration_s":    profile.duration,
        },
        "modal": {
            "f_n_s_Hz":      round(r.f_n_s,     6),
            "f_n_u_Hz":      round(r.f_n_u,     6),
            "omega_n_s_rads":round(r.omega_n_s,  6),
            "omega_n_u_rads":round(r.omega_n_u,  6),
            "zeta_s":        round(r.zeta_s,     6),
            "zeta_u":        round(r.zeta_u,     6),
            "c_crit_s_Nsm":  round(r.c_crit_s,  3),
            "c_crit_u_Nsm":  round(r.c_crit_u,  3),
            "k_w_Nm":        round(r.k_w,        3),
        },
        "frequency_domain": {
            "peak_transmissibility":  round(r.peak_transmissibility, 6),
            "freq_at_peak_tx_Hz":     round(r.freq_at_peak_tx,       6),
        },
        "metrics": {
            "rms_body_accel_ms2":   round(r.rms_body_accel,   6),
            "rms_susp_travel_m":    round(r.rms_susp_travel,  6),
            "rms_tire_load_N":      round(r.rms_tire_load,    4),
            "peak_susp_travel_m":   round(r.peak_susp_travel, 6),
            "peak_susp_travel_mm":  round(r.peak_susp_travel * 1e3, 4),
        },
    }
    return json.dumps(summary, indent=2).encode("utf-8")


def _build_html_bundle(r: QuarterCarResult) -> bytes:
    """
    Standalone HTML file containing all six plots as embedded Plotly JS.
    No external network dependencies — fully self-contained.
    """
    import plotly.io as pio

    figs = {
        "TRANSMISSIBILITY":   create_transmissibility_plot(r),
        "BODE DIAGRAM":       create_bode_plot(r),
        "TIME RESPONSE":      create_step_response_plot(r),
        "SUSPENSION TRAVEL":  create_suspension_travel_plot(r),
        "TIRE LOAD":          create_tire_load_plot(r),
        "ACCELERATION":       create_impulse_response_plot(r),
    }

    # Inline Plotly JS (CDN reference — small payload, loads once)
    html_parts = [
        "<!DOCTYPE html><html><head>",
        '<meta charset="UTF-8">',
        "<title>SuspensionLab PRO — Quarter Car Report</title>",
        '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>',
        "<style>body{background:#07090D;color:#DCE8F5;font-family:'JetBrains Mono',monospace;margin:0;padding:20px;}"
        "h1{color:#00E5FF;font-size:1.1rem;letter-spacing:3px;border-bottom:1px solid #1A2535;padding-bottom:8px;}"
        "h2{color:#5A7A99;font-size:0.75rem;letter-spacing:2px;margin:24px 0 6px;}"
        ".plot-wrap{background:#0D1117;border:1px solid #1A2535;margin-bottom:12px;padding:6px;}</style>",
        "</head><body>",
        "<h1>🏎  SUSPENSIONLAB PRO — QUARTER CAR ANALYSIS REPORT</h1>",
    ]

    for title, fig in figs.items():
        div_html = pio.to_html(fig, full_html=False, include_plotlyjs=False)
        html_parts.append(f"<h2>◈  {title}</h2>")
        html_parts.append(f'<div class="plot-wrap">{div_html}</div>')

    html_parts.append("</body></html>")
    return "\n".join(html_parts).encode("utf-8")


def _render_export_section(
    r: QuarterCarResult,
    params: QuarterCarParams,
    profile: RoadProfile,
) -> None:
    """Download buttons for CSV / JSON / HTML exports."""
    _section("◈  EXPORT & DATA")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.download_button(
            label        = "⬇  TIME DOMAIN CSV",
            data         = _build_csv(r),
            file_name    = "slp_qc_time_domain.csv",
            mime         = "text/csv",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            label        = "⬇  FREQUENCY DOMAIN CSV",
            data         = _build_freq_csv(r),
            file_name    = "slp_qc_freq_domain.csv",
            mime         = "text/csv",
            use_container_width=True,
        )
    with col3:
        st.download_button(
            label        = "⬇  METRICS JSON",
            data         = _build_json(r, params, profile),
            file_name    = "slp_qc_metrics.json",
            mime         = "application/json",
            use_container_width=True,
        )
    with col4:
        with st.spinner("Compiling HTML bundle…"):
            html_data = _build_html_bundle(r)
        st.download_button(
            label        = "⬇  INTERACTIVE HTML REPORT",
            data         = html_data,
            file_name    = "slp_qc_report.html",
            mime         = "text/html",
            use_container_width=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — Input Control Panel
# ─────────────────────────────────────────────────────────────────────────────

def _render_sidebar() -> tuple[QuarterCarParams, RoadProfile, float, float, int, bool]:
    """
    Render all sidebar input panels and return the physics parameter objects
    plus analysis settings.

    Returns
    -------
    params       : QuarterCarParams
    profile      : RoadProfile
    f_min        : float   frequency sweep min [Hz]
    f_max        : float   frequency sweep max [Hz]
    n_freq       : int     frequency sweep points
    run_clicked  : bool    whether the Run button was pressed
    """
    with st.sidebar:
        st.markdown(
            '<div class="slp-title" style="font-size:0.9rem">SUSPENSIONLAB PRO</div>'
            '<div class="slp-subtitle">QUARTER CAR MODULE v1.0</div>'
            '<hr class="slp-divider"/>',
            unsafe_allow_html=True,
        )

        # ── Vehicle Mass Parameters ───────────────────────────────────────
        with st.expander("▸  VEHICLE MASS", expanded=True):
            st.markdown('<div class="sidebar-sec">SPRUNG / UNSPRUNG</div>',
                        unsafe_allow_html=True)
            m_s = st.number_input(
                "Sprung Mass  m_s  [kg]",
                min_value=50.0, max_value=2000.0,
                value=300.0, step=10.0,
                help="Body / chassis mass supported by suspension.",
            )
            m_u = st.number_input(
                "Unsprung Mass  m_u  [kg]",
                min_value=5.0, max_value=200.0,
                value=35.0, step=1.0,
                help="Wheel assembly: hub, brake, partial control arm.",
            )
            ratio_disp = m_s / m_u if m_u > 0 else 0
            st.caption(f"Mass ratio  m_s/m_u = {ratio_disp:.1f}  "
                       f"({'good' if 6 < ratio_disp < 20 else 'check'})")

        # ── Suspension Parameters ─────────────────────────────────────────
        with st.expander("▸  SUSPENSION", expanded=True):
            st.markdown('<div class="sidebar-sec">SPRING & DAMPER</div>',
                        unsafe_allow_html=True)
            k_s = st.number_input(
                "Spring Rate  k_s  [N/m]",
                min_value=1_000.0, max_value=500_000.0,
                value=25_000.0, step=500.0,
                format="%g",
                help="Coil spring stiffness at spring seat.",
            )
            MR = st.slider(
                "Motion Ratio  MR  [-]",
                min_value=0.30, max_value=1.10,
                value=0.85, step=0.01,
                help="Wheel travel / spring travel.  k_w = k_s × MR².",
            )
            k_w_preview = k_s * MR ** 2
            st.caption(f"Wheel rate  k_w = {k_w_preview:,.0f} N/m")

            c_s = st.number_input(
                "Damping Coeff  c  [Ns/m]",
                min_value=100.0, max_value=50_000.0,
                value=3_500.0, step=100.0,
                format="%g",
                help="Damper coefficient at damper body.",
            )
            # Live damping ratio preview
            import math
            zeta_preview = c_s / (2.0 * math.sqrt(k_w_preview * m_s)) if k_w_preview > 0 and m_s > 0 else 0.0
            z_color = "green" if 0.28 <= zeta_preview <= 0.65 else "orange" if 0.20 <= zeta_preview <= 0.80 else "red"
            st.markdown(
                f"<span style='font-family:monospace;font-size:0.68rem;color:{z_color}'>"
                f"ζ preview = {zeta_preview:.4f}"
                f"</span>",
                unsafe_allow_html=True,
            )

        # ── Tire Parameters ───────────────────────────────────────────────
        with st.expander("▸  TIRE", expanded=True):
            st.markdown('<div class="sidebar-sec">VERTICAL STIFFNESS</div>',
                        unsafe_allow_html=True)
            k_t = st.number_input(
                "Tire Stiffness  k_t  [N/m]",
                min_value=50_000.0, max_value=700_000.0,
                value=200_000.0, step=5_000.0,
                format="%g",
                help="Radial tire spring stiffness (typically 150–250 kN/m).",
            )
            c_t = st.number_input(
                "Tire Damping  c_t  [Ns/m]",
                min_value=0.0, max_value=3_000.0,
                value=0.0, step=50.0,
                format="%g",
                help="Tire structural damping — typically 0–200 Ns/m.",
            )
            # Modal separation preview
            fn_s_prev = math.sqrt(k_w_preview / m_s) / (2 * math.pi) if m_s > 0 and k_w_preview > 0 else 0
            fn_u_prev = math.sqrt((k_w_preview + k_t) / m_u) / (2 * math.pi) if m_u > 0 else 0
            sep_ratio = fn_u_prev / fn_s_prev if fn_s_prev > 0 else 0
            sep_ok = sep_ratio >= 3.0
            st.caption(
                f"fn,s ≈ {fn_s_prev:.2f} Hz  |  "
                f"fn,u ≈ {fn_u_prev:.2f} Hz  |  "
                f"ratio = {sep_ratio:.2f}× {'✓' if sep_ok else '⚠'}"
            )

        # ── Road Profile ──────────────────────────────────────────────────
        with st.expander("▸  ROAD PROFILE", expanded=True):
            st.markdown('<div class="sidebar-sec">EXCITATION</div>',
                        unsafe_allow_html=True)
            profile_label = st.selectbox(
                "Profile Type",
                options=list(_PROFILE_MAP.keys()),
                index=0,
            )
            st.caption(_PROFILE_DESCRIPTIONS[profile_label])

            amplitude = st.slider(
                "Amplitude  [m]",
                min_value=0.001, max_value=0.30,
                value=0.05, step=0.001,
                format="%.3f",
                help="Road surface displacement amplitude.",
            )

            # Frequency only relevant for sine / random
            profile_type_str = _PROFILE_MAP[profile_label]
            if profile_type_str in ("sine", "random"):
                road_freq = st.slider(
                    "Road Frequency  [Hz]",
                    min_value=0.1, max_value=25.0,
                    value=2.0, step=0.1,
                    format="%.1f",
                )
            else:
                road_freq = 2.0   # default, unused for step/pothole/impulse

            duration = st.slider(
                "Simulation Duration  [s]",
                min_value=1.0, max_value=30.0,
                value=5.0, step=0.5,
                format="%.1f",
            )

        # ── Analysis Options ──────────────────────────────────────────────
        with st.expander("▸  ANALYSIS OPTIONS", expanded=False):
            st.markdown('<div class="sidebar-sec">FREQUENCY SWEEP</div>',
                        unsafe_allow_html=True)
            f_min = st.number_input("Freq Min [Hz]", value=0.1,
                                    min_value=0.01, max_value=5.0, step=0.05)
            f_max = st.number_input("Freq Max [Hz]", value=50.0,
                                    min_value=10.0, max_value=200.0, step=5.0)
            n_freq = st.select_slider(
                "Frequency Points",
                options=[200, 400, 600, 800, 1200],
                value=600,
            )
            st.markdown('<div class="sidebar-sec" style="margin-top:10px">EQUATIONS OF MOTION</div>',
                        unsafe_allow_html=True)
            st.markdown(
                '<div class="eq-block">'
                'm_s·z̈_s + c·(ż_s−ż_u) + k_w·(z_s−z_u) = 0<br>'
                'm_u·z̈_u + c·(ż_u−ż_s) + k_w·(z_u−z_s)<br>'
                '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
                '+ k_t·(z_u−z_r) = 0<br>'
                'k_w = k_s · MR²'
                '</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br/>", unsafe_allow_html=True)
        run_clicked = st.button(
            "▶  RUN ANALYSIS",
            use_container_width=True,
            key="run_btn",
        )

    # ── Build physics objects ─────────────────────────────────────────────
    params = QuarterCarParams(
        m_s = float(m_s),
        m_u = float(m_u),
        k_s = float(k_s),
        c   = float(c_s),
        k_t = float(k_t),
        MR  = float(MR),
        c_t = float(c_t),
    )
    profile = RoadProfile(
        profile_type = profile_type_str,
        amplitude    = float(amplitude),
        frequency    = float(road_freq),
        duration     = float(duration),
    )
    return params, profile, float(f_min), float(f_max), int(n_freq), run_clicked


# ─────────────────────────────────────────────────────────────────────────────
# Page Header
# ─────────────────────────────────────────────────────────────────────────────

def _render_header() -> None:
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(
            '<div class="mod-tag">MODULE 02</div><br/>'
            '<div class="slp-title">QUARTER-CAR SUSPENSION DYNAMICS LAB</div>'
            '<div class="slp-subtitle">'
            'INTERACTIVE RIDE COMFORT, HANDLING &amp; NVH ENGINEERING SIMULATOR'
            '</div>'
            '<hr class="slp-divider"/>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div style="text-align:right;padding-top:10px;">'
            '<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.62rem;'
            'color:#5A7A99;letter-spacing:1.5px;">2-DOF · RK45 · FREQ DOMAIN<br>'
            'ISO 2631-1 COMFORT METRICS</span>'
            '</div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main Simulation Runner
# ─────────────────────────────────────────────────────────────────────────────

def _run_simulation(
    params: QuarterCarParams,
    profile: RoadProfile,
    f_min: float,
    f_max: float,
    n_freq: int,
) -> tuple[QuarterCarResult | None, float, str | None]:
    """
    Execute the quarter car analysis with timing and error capture.

    Returns
    -------
    result       : QuarterCarResult or None on failure
    elapsed_ms   : wall-clock time in milliseconds
    error_msg    : exception string if failed, else None
    """
    t0 = time.perf_counter()
    try:
        result = run_quarter_car_analysis(
            p        = params,
            profile  = profile,
            f_min    = f_min,
            f_max    = f_max,
            n_freq   = n_freq,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return result, elapsed_ms, None
    except Exception:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return None, elapsed_ms, traceback.format_exc()


# ─────────────────────────────────────────────────────────────────────────────
# Main Page Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    _render_header()

    # ── Sidebar inputs ────────────────────────────────────────────────────
    params, profile, f_min, f_max, n_freq, run_clicked = _render_sidebar()

    # ── Session state — cache last valid result ───────────────────────────
    if "qc_result"  not in st.session_state:
        st.session_state["qc_result"]  = None
    if "qc_params"  not in st.session_state:
        st.session_state["qc_params"]  = None
    if "qc_profile" not in st.session_state:
        st.session_state["qc_profile"] = None
    if "qc_elapsed" not in st.session_state:
        st.session_state["qc_elapsed"] = 0.0

    # Auto-run on first load
    first_load = st.session_state["qc_result"] is None

    if run_clicked or first_load:
        with st.spinner("◈  RUNNING QUARTER CAR ANALYSIS  —  RK45 + FREQ DOMAIN…"):
            result, elapsed_ms, err = _run_simulation(
                params, profile, f_min, f_max, n_freq
            )

        if err:
            st.error(
                f"**Analysis failed.**\n\n```\n{err}\n```\n\n"
                "Check parameter values and retry.",
                icon="🚨",
            )
            return

        st.session_state["qc_result"]  = result
        st.session_state["qc_params"]  = params
        st.session_state["qc_profile"] = profile
        st.session_state["qc_elapsed"] = elapsed_ms

    # ── Retrieve cached result ────────────────────────────────────────────
    result:  QuarterCarResult = st.session_state["qc_result"]
    params:  QuarterCarParams = st.session_state["qc_params"]
    profile: RoadProfile      = st.session_state["qc_profile"]
    elapsed: float            = st.session_state["qc_elapsed"]

    if result is None:
        st.info("Configure parameters in the sidebar and press **▶ RUN ANALYSIS**.",
                icon="🏎️")
        return

    # ─────────────────────────────────────────────────────────────────────
    # KPI Telemetry Strip
    # ─────────────────────────────────────────────────────────────────────
    _section("◈  TELEMETRY  —  KEY PERFORMANCE INDICATORS")
    _render_kpi_strip(result)
    _render_run_banner(result, elapsed)

    # ─────────────────────────────────────────────────────────────────────
    # Overview Dashboard (4-panel)
    # ─────────────────────────────────────────────────────────────────────
    _section("◈  OVERVIEW DASHBOARD")
    st.plotly_chart(
        create_overview_dashboard(result),
        use_container_width=True,
        config={"displayModeBar": True, "displaylogo": False},
    )

    # ─────────────────────────────────────────────────────────────────────
    # Detailed Analysis — Row 1: Transmissibility | Bode
    # ─────────────────────────────────────────────────────────────────────
    _section("◈  FREQUENCY DOMAIN ANALYSIS")
    col_tx, col_bode = st.columns(2)
    with col_tx:
        st.plotly_chart(
            create_transmissibility_plot(result),
            use_container_width=True,
            config={"displayModeBar": True, "displaylogo": False},
            key="plot_tx",
        )
    with col_bode:
        st.plotly_chart(
            create_bode_plot(result),
            use_container_width=True,
            config={"displayModeBar": True, "displaylogo": False},
            key="plot_bode",
        )

    # ─────────────────────────────────────────────────────────────────────
    # Detailed Analysis — Row 2: Step Response (full width)
    # ─────────────────────────────────────────────────────────────────────
    _section("◈  TIME DOMAIN RESPONSE")
    st.plotly_chart(
        create_step_response_plot(result),
        use_container_width=True,
        config={"displayModeBar": True, "displaylogo": False},
        key="plot_step",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Detailed Analysis — Row 3: Suspension Travel | Tire Load
    # ─────────────────────────────────────────────────────────────────────
    _section("◈  SUSPENSION TRAVEL  &  TIRE LOAD VARIATION")
    col_tr, col_tl = st.columns(2)
    with col_tr:
        st.plotly_chart(
            create_suspension_travel_plot(result),
            use_container_width=True,
            config={"displayModeBar": True, "displaylogo": False},
            key="plot_travel",
        )
    with col_tl:
        st.plotly_chart(
            create_tire_load_plot(result),
            use_container_width=True,
            config={"displayModeBar": True, "displaylogo": False},
            key="plot_tire",
        )

    # ─────────────────────────────────────────────────────────────────────
    # Acceleration / NVH Detail
    # ─────────────────────────────────────────────────────────────────────
    with st.expander("◈  BODY ACCELERATION DETAIL  (NVH)", expanded=False):
        st.plotly_chart(
            create_impulse_response_plot(result),
            use_container_width=True,
            config={"displayModeBar": True, "displaylogo": False},
            key="plot_nvh",
        )

    # ─────────────────────────────────────────────────────────────────────
    # Engineering Insights
    # ─────────────────────────────────────────────────────────────────────
    _render_insights(result)

    # ─────────────────────────────────────────────────────────────────────
    # Modal Summary Table
    # ─────────────────────────────────────────────────────────────────────
    _section("◈  MODAL ANALYSIS SUMMARY")
    col_a, col_b = st.columns(2)

    with col_a:
        modal_df = pd.DataFrame({
            "Parameter"     : [
                "Sprung Nat. Freq  fn,s",
                "Unsprung Nat. Freq  fn,u",
                "Modal Sep. Ratio  fn,u/fn,s",
                "Sprung ωn,s",
                "Unsprung ωn,u",
                "Sprung Damping  ζ_s",
                "Unsprung Damping  ζ_u",
                "Critical Damping  c_crit,s",
                "Critical Damping  c_crit,u",
                "Wheel Rate  k_w",
            ],
            "Value"         : [
                f"{result.f_n_s:.4f} Hz",
                f"{result.f_n_u:.4f} Hz",
                f"{result.f_n_u/result.f_n_s:.3f} ×",
                f"{result.omega_n_s:.4f} rad/s",
                f"{result.omega_n_u:.4f} rad/s",
                f"{result.zeta_s:.6f}",
                f"{result.zeta_u:.6f}",
                f"{result.c_crit_s:,.1f} Ns/m",
                f"{result.c_crit_u:,.1f} Ns/m",
                f"{result.k_w:,.1f} N/m",
            ],
        })
        st.dataframe(modal_df, use_container_width=True, hide_index=True)

    with col_b:
        metrics_df = pd.DataFrame({
            "Metric"    : [
                "RMS Body Acceleration",
                "ISO 2631-1 Rating",
                "Peak Transmissibility",
                "Freq @ Peak Tx",
                "RMS Suspension Travel",
                "Peak Suspension Travel",
                "RMS Tire Load Variation",
                "Peak Tire Load Variation",
                "Simulation Duration",
                "Time Steps",
            ],
            "Value"     : [
                f"{result.rms_body_accel:.6f} m/s²",
                (
                    "Not Uncomfortable" if result.rms_body_accel < 0.315
                    else "Slightly Uncomfortable" if result.rms_body_accel < 0.630
                    else "Fairly Uncomfortable" if result.rms_body_accel < 1.0
                    else "Uncomfortable"
                ),
                f"{result.peak_transmissibility:.4f} ×",
                f"{result.freq_at_peak_tx:.4f} Hz",
                f"{result.rms_susp_travel*1e3:.3f} mm",
                f"{result.peak_susp_travel*1e3:.3f} mm",
                f"{result.rms_tire_load:.2f} N",
                f"{float(np.max(np.abs(result.tire_load_var))):.2f} N",
                f"{result.time[-1]:.1f} s",
                f"{len(result.time):,}",
            ],
        })
        st.dataframe(metrics_df, use_container_width=True, hide_index=True)

    # ─────────────────────────────────────────────────────────────────────
    # Export Section
    # ─────────────────────────────────────────────────────────────────────
    _render_export_section(result, params, profile)

    # ── Footer ────────────────────────────────────────────────────────────
    st.markdown(
        '<hr class="slp-divider"/>'
        '<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.58rem;'
        'color:#1A2535;text-align:center;padding:4px 0;">'
        'SUSPENSIONLAB PRO · MODULE 02 · QUARTER CAR 2-DOF · '
        'SCIPY RK45 · ISO 2631-1 · © SUSPENSIONLAB ENGINEERING</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
