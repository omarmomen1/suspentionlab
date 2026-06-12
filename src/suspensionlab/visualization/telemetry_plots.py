"""
visualization/telemetry_plots.py
=================================
SuspensionLab PRO — Telemetry Visualization Module

All plots follow Formula 1 pit-wall telemetry aesthetics:
  - Matte black background (#07090D)
  - Cyan primary traces (#00E5FF)
  - Purple secondary traces (#BF5AF2)
  - Amber tertiary / road input (#FFB800)
  - Green positive metric (#00FF87)
  - Red warning / phase (#FF2D55)
  - Engineering grid at low opacity
  - JetBrains Mono / monospace axis labels
  - Compact layout for dashboard embedding
"""

from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from suspensionlab.shared.models import QuarterCarResultSchema as QuarterCarResult
from suspensionlab.shared.models import HalfCarResultSchema as HalfCarResult

# Arrays from API are List[float]; use np.asarray() before arithmetic

# ─────────────────────────────────────────────────────────────────────────────
# Design Tokens
# ─────────────────────────────────────────────────────────────────────────────

_BG_PRIMARY   = "#07090D"
_BG_PAPER     = "#07090D"
_BG_PLOT      = "#0D1117"
_BG_PANEL     = "#111820"

_CYAN         = "#90FF40"
_CYAN_DIM     = "rgba(144,255,64,0.18)"
_CYAN_FILL    = "rgba(144,255,64,0.06)"
_PURPLE       = "#BF5AF2"
_PURPLE_FILL  = "rgba(191,90,242,0.06)"
_AMBER        = "#FFB800"
_AMBER_FILL   = "rgba(255,184,0,0.07)"
_GREEN        = "#00FF87"
_GREEN_FILL   = "rgba(0,255,135,0.06)"
_RED          = "#FF2D55"
_RED_FILL     = "rgba(255,45,85,0.07)"
_WHITE        = "#DCE8F5"
_YELLOW       = "#FFD60A"
_GRID         = "rgba(255,255,255,0.055)"
_AXIS_LINE    = "rgba(255,255,255,0.12)"
_TEXT_PRI     = "#DCE8F5"
_TEXT_SEC     = "#5A7A99"
_FONT_MONO    = "JetBrains Mono, Courier New, monospace"
_FONT_LABEL   = "Rajdhani, Arial, sans-serif"

_HOVER_BG     = "#111820"
_HOVER_BORDER = "#90FF40"


def AdaptiveScatter(x=None, y=None, **kwargs):
    """
    Adaptive Scatter trace logic to prevent WebGL context loss.
    Always uses standard Scatter (SVG). WebGL has been disabled.
    """
    return go.Scatter(x=x, y=y, **kwargs)



# ─────────────────────────────────────────────────────────────────────────────
# Global F1 Theme Helper
# ─────────────────────────────────────────────────────────────────────────────

def apply_f1_theme(
    fig: go.Figure,
    height: int = 340,
    show_legend: bool = True,
    margin: dict | None = None,
) -> go.Figure:
    """
    Apply the SuspensionLab PRO Formula 1 telemetry theme to any Plotly figure.

    Parameters
    ----------
    fig         : plotly.graph_objects.Figure  — figure to style in-place
    height      : int   — figure height in pixels
    show_legend : bool  — whether to display legend
    margin      : dict  — custom margin override (l, r, t, b)

    Returns
    -------
    The same figure with theme applied (mutates and returns).
    """
    _margin = margin or dict(l=58, r=24, t=36, b=52)

    fig.update_layout(
        # Canvas
        paper_bgcolor = _BG_PAPER,
        plot_bgcolor  = _BG_PLOT,
        height        = height,

        # Font defaults
        font = dict(
            family = _FONT_MONO,
            size   = 10,
            color  = _TEXT_PRI,
        ),

        # Margin
        margin = _margin,

        # Legend
        showlegend = show_legend,
        legend = dict(
            bgcolor     = "rgba(13,17,23,0.85)",
            bordercolor = _AXIS_LINE,
            borderwidth = 1,
            font        = dict(family=_FONT_MONO, size=9, color=_TEXT_SEC),
            x           = 1.0,
            xanchor     = "right",
            y           = 1.0,
            yanchor     = "top",
            tracegroupgap = 2,
        ),

        # Hover
        hoverlabel = dict(
            bgcolor    = _HOVER_BG,
            bordercolor= _HOVER_BORDER,
            font       = dict(family=_FONT_MONO, size=10, color=_TEXT_PRI),
        ),
        hovermode = "x unified",

        # No Plotly logo / modebar clutter
        modebar = dict(
            bgcolor     = "rgba(0,0,0,0)",
            color       = _TEXT_SEC,
            activecolor = _CYAN,
            orientation = "v",
        ),
    )

    # Apply axis styling to every xaxis / yaxis found in the figure layout
    axis_common = dict(
        gridcolor      = _GRID,
        gridwidth      = 0.5,
        zerolinecolor  = _AXIS_LINE,
        zerolinewidth  = 1,
        linecolor      = _AXIS_LINE,
        linewidth      = 1,
        tickfont       = dict(family=_FONT_MONO, size=9, color=_TEXT_SEC),
        title_font     = dict(family=_FONT_MONO, size=9, color=_TEXT_SEC),
        showgrid       = True,
        mirror         = False,
        ticks          = "outside",
        ticklen        = 3,
        tickwidth      = 1,
        tickcolor      = _AXIS_LINE,
        minor_gridcolor= "rgba(255,255,255,0.022)",
        minor_showgrid = True,
    )

    # Find all axis keys in layout
    layout_dict = fig.layout.to_plotly_json()
    for key in layout_dict:
        if key.startswith("xaxis") or key.startswith("yaxis"):
            fig.update_layout({key: axis_common})

    return fig


def _vline(x: float, color: str = _AMBER, dash: str = "dot") -> go.layout.Shape:
    """Return a vertical dashed reference line shape."""
    return go.layout.Shape(
        type      = "line",
        x0=x, x1=x, y0=0, y1=1,
        xref      = "x",
        yref      = "paper",
        line      = dict(color=color, width=1.0, dash=dash),
        opacity   = 0.7,
    )


def _hline(y: float, color: str = _AMBER, dash: str = "dot",
           xref: str = "paper") -> go.layout.Shape:
    """Return a horizontal dashed reference line shape."""
    return go.layout.Shape(
        type      = "line",
        x0=0, x1=1, y0=y, y1=y,
        xref      = xref,
        yref      = "y",
        line      = dict(color=color, width=1.0, dash=dash),
        opacity   = 0.65,
    )


def _freq_annotation(
    x: float, label: str, color: str, yref: str = "paper"
) -> go.layout.Annotation:
    """Frequency marker annotation."""
    return go.layout.Annotation(
        x          = x,
        y          = 0.97,
        xref       = "x",
        yref       = yref,
        text       = label,
        showarrow  = False,
        font       = dict(family=_FONT_MONO, size=8, color=color),
        bgcolor    = "rgba(13,17,23,0.75)",
        bordercolor= color,
        borderwidth= 1,
        borderpad  = 3,
        xanchor    = "left",
        yanchor    = "top",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Transmissibility Plot
# ─────────────────────────────────────────────────────────────────────────────

def create_transmissibility_plot(result: QuarterCarResult, baseline: QuarterCarResult = None) -> go.Figure:
    """
    Transmissibility vs frequency for body (sprung) and wheel (unsprung).

    X-axis : log-scale frequency [Hz]
    Y-axis : |H(jω)| transmissibility ratio [-]

    Engineering interpretation
    --------------------------
    Values > 1.0 indicate amplification (resonance region).
    Values < 1.0 indicate isolation (desired for ride comfort).
    The crossover between amplification and isolation occurs near sqrt(2) * f_n.
    """
    freq  = result.freq_hz
    tx_b  = result.transmissibility_body
    tx_w  = result.transmissibility_wheel
    f_ns  = result.f_n_s
    f_nu  = result.f_n_u
    peak  = result.peak_transmissibility
    f_pk  = result.freq_at_peak_tx

    fig = go.Figure()

    # ── Wheel transmissibility (background trace) ──────────────────────────
    fig.add_trace(AdaptiveScatter(
        x            = freq,
        y            = tx_w,
        name         = "WHEEL HOP  |Zu/Zr|",
        mode         = "lines",
        line         = dict(color=_PURPLE, width=1.4, dash="solid"),
        opacity      = 0.75,
        fill         = "tozeroy",
        fillcolor    = _PURPLE_FILL,
        hovertemplate= (
            "<b>WHEEL HOP</b><br>"
            "Freq : %{x:.3f} Hz<br>"
            "|Hu| : %{y:.4f}<br>"
            "<extra></extra>"
        ),
    ))

    # ── Body transmissibility (primary trace) ──────────────────────────────
    fig.add_trace(AdaptiveScatter(
        x            = freq,
        y            = tx_b,
        name         = "BODY RIDE  |Zs/Zr|",
        mode         = "lines",
        line         = dict(color=_CYAN, width=2.0),
        fill         = "tozeroy",
        fillcolor    = _CYAN_FILL,
        hovertemplate= (
            "<b>BODY TRANSMISSIBILITY</b><br>"
            "Freq : %{x:.3f} Hz<br>"
            "|Hs| : %{y:.4f}<br>"
            "<extra></extra>"
        ),
    ))

    # ── Unity reference line (isolation threshold) ─────────────────────────
    fig.add_hline(
        y           = 1.0,
        line_dash   = "dot",
        line_color  = _AMBER,
        line_width  = 0.8,
        opacity     = 0.6,
        annotation_text      = "ISOLATION THRESHOLD  |H|=1",
        annotation_position  = "bottom right",
        annotation_font      = dict(family=_FONT_MONO, size=8, color=_AMBER),
    )

    # ── Peak transmissibility marker ───────────────────────────────────────
    fig.add_trace(AdaptiveScatter(
        x    = [f_pk],
        y    = [peak],
        name = f"PEAK  {peak:.2f}× @ {f_pk:.2f} Hz",
        mode = "markers",
        marker = dict(
            color  = _RED,
            size   = 8,
            symbol = "diamond",
            line   = dict(color=_WHITE, width=1),
        ),
        hovertemplate = (
            "<b>RESONANCE PEAK</b><br>"
            "Freq : %{x:.3f} Hz<br>"
            "Peak : %{y:.4f}<br>"
            "<extra></extra>"
        ),
    ))

    # ── Sprung / unsprung natural frequency markers ────────────────────────
    shapes = [
        _vline(f_ns, color=_CYAN,   dash="dash"),
        _vline(f_nu, color=_PURPLE, dash="dash"),
    ]
    annotations = [
        _freq_annotation(f_ns, f"fn,s = {f_ns:.2f} Hz", _CYAN),
        _freq_annotation(f_nu, f"fn,u = {f_nu:.2f} Hz", _PURPLE),
    ]

    fig.update_layout(
        shapes      = shapes,
        annotations = annotations,
        xaxis = dict(
            type        = "log",
            title_text  = "FREQUENCY  [Hz]",
            range       = [np.log10(freq[0]), np.log10(freq[-1])],
            dtick       = "D2",   # minor ticks on log scale
        ),
        yaxis = dict(
            title_text = "TRANSMISSIBILITY  |H(jω)|  [-]",
            rangemode  = "tozero",
        ),
        yaxis2 = dict(
            title_text = "DELTA",
            overlaying = "y",
            side       = "right",
        ),
        title = dict(
            text      = (
                f"<b>TRANSMISSIBILITY — BODY & WHEEL HOP</b>"
                f"<span style='font-size:9px;color:{_TEXT_SEC}'>"
                f"  |  PEAK = {peak:.3f}× @ {f_pk:.2f} Hz"
                f"  |  fn,s = {f_ns:.2f} Hz  |  fn,u = {f_nu:.2f} Hz"
                f"</span>"
            ),
            font      = dict(family=_FONT_MONO, size=11, color=_TEXT_PRI),
            x         = 0.0,
            xanchor   = "left",
            pad       = dict(l=0, t=4),
        ),
    )

    if baseline is not None:
        fig.add_trace(AdaptiveScatter(
            x            = baseline.freq_hz,
            y            = baseline.transmissibility_body,
            name         = "BASELINE |Hs/Zr|",
            mode         = "lines",
            line         = dict(color=_AMBER, width=1.2, dash="dot"),
        ))
        delta = np.asarray(tx_b) - np.asarray(baseline.transmissibility_body)
        fig.add_trace(AdaptiveScatter(
            x            = freq,
            y            = delta,
            name         = "ΔTRANSMISSIBILITY",
            mode         = "none",
            fill         = "tozeroy",
            fillcolor    = "rgba(255,45,85,0.5)",
            yaxis        = "y2"
        ))

    apply_f1_theme(fig, height=360)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Bode Plot (Magnitude + Phase — two-row subplot)
# ─────────────────────────────────────────────────────────────────────────────

def create_bode_plot(result: QuarterCarResult) -> go.Figure:
    """
    Bode diagram: magnitude [dB] and phase [deg] vs log-frequency.

    Row 1 : 20·log₁₀(|Hs(jω)|) — body acceleration / road input  [dB]
    Row 2 : ∠Hs(jω)             — phase angle                     [deg]

    Engineering interpretation
    --------------------------
    0 dB crossings indicate unit gain (transmissibility = 1).
    Phase crosses through -90° at natural frequency (underdamped).
    Phase shift of -180° at high frequencies indicates full isolation.
    """
    freq   = result.freq_hz
    mag_db = result.bode_magnitude_db
    phase  = result.bode_phase_deg
    f_ns   = result.f_n_s
    f_nu   = result.f_n_u

    fig = make_subplots(
        rows             = 2,
        cols             = 1,
        shared_xaxes     = True,
        row_heights      = [0.58, 0.42],
        vertical_spacing = 0.06,
        subplot_titles   = ["MAGNITUDE  [dB]", "PHASE  [deg]"],
    )

    # Style subplot title annotations
    for ann in fig.layout.annotations:
        ann.update(
            font   = dict(family=_FONT_MONO, size=9, color=_TEXT_SEC),
            x      = 0.0,
            xanchor= "left",
        )

    # ── Magnitude trace ────────────────────────────────────────────────────
    fig.add_trace(
        AdaptiveScatter(
            x            = freq,
            y            = mag_db,
            name         = "MAGNITUDE  |Hs(jω)|",
            mode         = "lines",
            line         = dict(color=_GREEN, width=1.8),
            fill         = "tozeroy",
            fillcolor    = _GREEN_FILL,
            hovertemplate= (
                "<b>BODE MAGNITUDE</b><br>"
                "Freq : %{x:.3f} Hz<br>"
                "Mag  : %{y:.2f} dB<br>"
                "<extra></extra>"
            ),
        ),
        row=1, col=1,
    )

    # 0 dB reference
    fig.add_hline(
        y=0.0, row=1, col=1,
        line_dash="dot", line_color=_AMBER, line_width=0.8, opacity=0.55,
        annotation_text="0 dB",
        annotation_position="bottom right",
        annotation_font=dict(family=_FONT_MONO, size=8, color=_AMBER),
    )

    # ── Phase trace ────────────────────────────────────────────────────────
    fig.add_trace(
        AdaptiveScatter(
            x            = freq,
            y            = phase,
            name         = "PHASE  ∠Hs(jω)",
            mode         = "lines",
            line         = dict(color=_RED, width=1.8),
            hovertemplate= (
                "<b>BODE PHASE</b><br>"
                "Freq  : %{x:.3f} Hz<br>"
                "Phase : %{y:.2f}°<br>"
                "<extra></extra>"
            ),
        ),
        row=2, col=1,
    )

    # Phase reference lines at -90° and -180°
    for ph_ref, label in [(-90.0, "-90°"), (-180.0, "-180°")]:
        fig.add_hline(
            y=ph_ref, row=2, col=1,
            line_dash="dot", line_color=_AMBER, line_width=0.7, opacity=0.5,
            annotation_text=label,
            annotation_position="bottom right",
            annotation_font=dict(family=_FONT_MONO, size=8, color=_AMBER),
        )

    # ── Natural frequency vertical markers (both rows) ────────────────────
    for fn, col_hex, label in [
        (f_ns, _CYAN,   f"fn,s={f_ns:.2f}Hz"),
        (f_nu, _PURPLE, f"fn,u={f_nu:.2f}Hz"),
    ]:
        for row_idx in [1, 2]:
            fig.add_vline(
                x=fn, row=row_idx, col=1,
                line_dash="dash", line_color=col_hex,
                line_width=0.9, opacity=0.65,
            )
        # Annotation on magnitude row only
        fig.add_annotation(
            x       = fn,
            y       = 1.0,
            xref    = "x",
            yref    = "y domain",
            text    = label,
            showarrow=False,
            font    = dict(family=_FONT_MONO, size=8, color=col_hex),
            bgcolor = "rgba(13,17,23,0.75)",
            bordercolor=col_hex,
            borderwidth=1,
            borderpad=3,
            xanchor ="left",
            yanchor ="top",
            row=1, col=1,
        )

    # ── Axis labels ────────────────────────────────────────────────────────
    fig.update_xaxes(
        type       = "log",
        title_text = "FREQUENCY  [Hz]",
        dtick      = "D2",
        row        = 2, col=1,
    )
    fig.update_xaxes(type="log", dtick="D2", row=1, col=1)
    fig.update_yaxes(title_text="MAGNITUDE  [dB]",   row=1, col=1)
    fig.update_yaxes(title_text="PHASE  [deg]", range=[-195, 15], row=2, col=1)

    fig.update_layout(
        title=dict(
            text    = (
                f"<b>BODE DIAGRAM — BODY TRANSMISSIBILITY Hs(jω)</b>"
                f"<span style='font-size:9px;color:{_TEXT_SEC}'>"
                f"  |  fn,s = {f_ns:.3f} Hz  |  fn,u = {f_nu:.3f} Hz"
                f"  |  ζ = {result.zeta_s:.4f}"
                f"</span>"
            ),
            font    = dict(family=_FONT_MONO, size=11, color=_TEXT_PRI),
            x       = 0.0,
            xanchor = "left",
            pad     = dict(l=0, t=4),
        ),
    )

    apply_f1_theme(fig, height=440, margin=dict(l=62, r=24, t=44, b=52))
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Step Response Plot
# ─────────────────────────────────────────────────────────────────────────────

def create_step_response_plot(result: QuarterCarResult, baseline: QuarterCarResult = None) -> go.Figure:
    """
    Time-domain displacement response: body (z_s), wheel (z_u), road (z_r).

    Y-axis in millimetres for engineering readability.
    Includes a secondary trace for body acceleration [m/s²].

    Two rows:
      Row 1 : Displacement [mm]  — z_s, z_u, z_r
      Row 2 : Body acceleration  [m/s²]
    """
    t      = result.time
    z_s_mm = np.asarray(result.z_s)    * 1e3    # → mm
    z_u_mm = np.asarray(result.z_u)    * 1e3
    z_r_mm = np.asarray(result.z_r)    * 1e3
    ddz_s  = np.asarray(result.ddz_s)       # m/s²

    fig = make_subplots(
        rows             = 3 if baseline else 2,
        cols             = 1,
        shared_xaxes     = True,
        row_heights      = [0.50, 0.30, 0.20] if baseline else [0.60, 0.40],
        vertical_spacing = 0.06,
        subplot_titles   = ["DISPLACEMENT  [mm]", "BODY ACCELERATION  [m/s²]", "DELTA zs  [mm]"] if baseline else ["DISPLACEMENT  [mm]", "BODY ACCELERATION  [m/s²]"],
    )

    for ann in fig.layout.annotations:
        ann.update(font=dict(family=_FONT_MONO, size=9, color=_TEXT_SEC),
                   x=0.0, xanchor="left")

    # ── Road profile (filled area) ─────────────────────────────────────────
    fig.add_trace(
        AdaptiveScatter(
            x            = t,
            y            = z_r_mm,
            name         = "ROAD  zr",
            mode         = "lines",
            line         = dict(color=_AMBER, width=1.0, dash="dot"),
            fill         = "tozeroy",
            fillcolor    = _AMBER_FILL,
            opacity      = 0.85,
            hovertemplate= (
                "<b>ROAD PROFILE</b><br>"
                "t    : %{x:.3f} s<br>"
                "zr   : %{y:.2f} mm<br>"
                "<extra></extra>"
            ),
        ),
        row=1, col=1,
    )

    # ── Unsprung (wheel) displacement ─────────────────────────────────────
    fig.add_trace(
        AdaptiveScatter(
            x            = t,
            y            = z_u_mm,
            name         = "WHEEL  zu",
            mode         = "lines",
            line         = dict(color=_PURPLE, width=1.4),
            opacity      = 0.85,
            hovertemplate= (
                "<b>WHEEL DISPLACEMENT</b><br>"
                "t    : %{x:.3f} s<br>"
                "zu   : %{y:.3f} mm<br>"
                "<extra></extra>"
            ),
        ),
        row=1, col=1,
    )

    # ── Sprung (body) displacement — primary trace ─────────────────────────
    fig.add_trace(
        AdaptiveScatter(
            x            = t,
            y            = z_s_mm,
            name         = "BODY  zs",
            mode         = "lines",
            line         = dict(color=_CYAN, width=2.0),
            hovertemplate= (
                "<b>BODY DISPLACEMENT</b><br>"
                "t    : %{x:.3f} s<br>"
                "zs   : %{y:.3f} mm<br>"
                "<extra></extra>"
            ),
        ),
        row=1, col=1,
    )

    if baseline is not None:
        baseline_z_s_mm = np.asarray(baseline.z_s) * 1e3
        fig.add_trace(
            AdaptiveScatter(
                x            = baseline.time,
                y            = baseline_z_s_mm,
                name         = "BASELINE zs",
                mode         = "lines",
                line         = dict(color=_AMBER, width=1.5, dash="dot"),
            ),
            row=1, col=1,
        )
        
        # Truncate to shorter array if different profile durations
        min_len = min(len(z_s_mm), len(baseline_z_s_mm))
        z_s_trimmed = z_s_mm[:min_len]
        baseline_trimmed = baseline_z_s_mm[:min_len]
        t_trimmed = np.asarray(result.time)[:min_len]
        
        delta_zs = z_s_trimmed - baseline_trimmed
        fig.add_trace(
            AdaptiveScatter(
                x            = t_trimmed,
                y            = delta_zs,
                name         = "Δzs (CURRENT - BASELINE)",
                mode         = "lines",
                line         = dict(color=_RED, width=1.5),
                fill         = "tozeroy",
                fillcolor    = "rgba(255,45,85,0.3)",
            ),
            row=3, col=1,
        )

    # ── Body acceleration ──────────────────────────────────────────────────
    fig.add_trace(
        AdaptiveScatter(
            x            = t,
            y            = ddz_s,
            name         = "ACCEL  z̈s",
            mode         = "lines",
            line         = dict(color=_GREEN, width=1.5),
            fill         = "tozeroy",
            fillcolor    = _GREEN_FILL,
            hovertemplate= (
                "<b>BODY ACCELERATION</b><br>"
                "t     : %{x:.3f} s<br>"
                "z̈s    : %{y:.4f} m/s²<br>"
                "<extra></extra>"
            ),
        ),
        row=2, col=1,
    )

    # RMS acceleration reference line
    rms_a = result.rms_body_accel
    fig.add_hline(
        y=rms_a, row=2, col=1,
        line_dash="dash", line_color=_RED, line_width=0.9, opacity=0.7,
        annotation_text=f"RMS = {rms_a:.4f} m/s²",
        annotation_position="top right",
        annotation_font=dict(family=_FONT_MONO, size=8, color=_RED),
    )
    fig.add_hline(
        y=-rms_a, row=2, col=1,
        line_dash="dash", line_color=_RED, line_width=0.9, opacity=0.7,
    )

    # ── Zero displacement reference ────────────────────────────────────────
    fig.add_hline(y=0.0, row=1, col=1,
                  line_dash="dot", line_color=_AXIS_LINE,
                  line_width=0.6, opacity=0.5)

    # ── Axis labels ────────────────────────────────────────────────────────
    if baseline:
        fig.update_xaxes(title_text="TIME  [s]", row=3, col=1)
    else:
        fig.update_xaxes(title_text="TIME  [s]", row=2, col=1)
    
    fig.update_yaxes(title_text="DISPLACEMENT  [mm]", row=1, col=1)
    fig.update_yaxes(title_text="ACCELERATION  [m/s²]", row=2, col=1)
    if baseline:
        fig.update_yaxes(title_text="DELTA [mm]", row=3, col=1)

    fig.update_layout(
        title=dict(
            text    = (
                f"<b>TIME DOMAIN — DISPLACEMENT & ACCELERATION RESPONSE</b>"
                f"<span style='font-size:9px;color:{_TEXT_SEC}'>"
                f"  |  RMS ẍs = {rms_a:.4f} m/s²"
                f"  |  PROFILE: {float(np.max(result.z_r))*1e3:.1f} mm"
                f"</span>"
            ),
            font    = dict(family=_FONT_MONO, size=11, color=_TEXT_PRI),
            x       = 0.0,
            xanchor = "left",
            pad     = dict(l=0, t=4),
        ),
    )

    apply_f1_theme(fig, height=440, margin=dict(l=66, r=24, t=44, b=52))
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Suspension Travel Plot
# ─────────────────────────────────────────────────────────────────────────────

def create_suspension_travel_plot(result: QuarterCarResult) -> go.Figure:
    """
    Suspension travel (z_s - z_u) vs time, with RMS and peak-to-peak bands.

    Engineering significance
    ------------------------
    Suspension travel must remain within available stroke (bump/droop stops).
    Typical passenger car: ±50–80 mm.  Race car: ±25–40 mm.
    Exceeding travel limits causes bump-stop contact → step change in spring rate.
    """
    t          = result.time
    travel_mm  = np.asarray(result.susp_travel) * 1e3    # → mm
    rms_mm     = result.rms_susp_travel * 1e3
    peak_mm    = result.peak_susp_travel * 1e3

    fig = go.Figure()

    # ── Fill band between ±RMS ────────────────────────────────────────────
    fig.add_trace(AdaptiveScatter(
        x         = np.concatenate([t, t[::-1]]),
        y         = np.concatenate([
            np.full_like(t,  rms_mm),
            np.full_like(t, -rms_mm)[::-1],
        ]),
        fill      = "toself",
        fillcolor = "rgba(0,229,255,0.04)",
        line      = dict(width=0),
        name      = f"±RMS BAND  ±{rms_mm:.2f} mm",
        showlegend= True,
        hoverinfo = "skip",
    ))

    # ── Suspension travel trace ────────────────────────────────────────────
    fig.add_trace(AdaptiveScatter(
        x            = t,
        y            = travel_mm,
        name         = "SUSPENSION TRAVEL  zs−zu",
        mode         = "lines",
        line         = dict(color=_CYAN, width=2.0),
        hovertemplate= (
            "<b>SUSPENSION TRAVEL</b><br>"
            "t       : %{x:.3f} s<br>"
            "Travel  : %{y:.3f} mm<br>"
            "<extra></extra>"
        ),
    ))

    # ── RMS reference lines ────────────────────────────────────────────────
    fig.add_hline(
        y=rms_mm,
        line_dash="dash", line_color=_AMBER, line_width=1.0, opacity=0.7,
        annotation_text=f"+RMS = {rms_mm:.2f} mm",
        annotation_position="top right",
        annotation_font=dict(family=_FONT_MONO, size=8, color=_AMBER),
    )
    fig.add_hline(
        y=-rms_mm,
        line_dash="dash", line_color=_AMBER, line_width=1.0, opacity=0.7,
        annotation_text=f"−RMS = {rms_mm:.2f} mm",
        annotation_position="bottom right",
        annotation_font=dict(family=_FONT_MONO, size=8, color=_AMBER),
    )
    fig.add_hline(
        y=0.0,
        line_dash="dot", line_color=_AXIS_LINE, line_width=0.6, opacity=0.5,
    )

    # ── Peak travel annotation ─────────────────────────────────────────────
    idx_max = int(np.argmax(np.abs(travel_mm)))
    fig.add_annotation(
        x         = t[idx_max],
        y         = travel_mm[idx_max],
        text      = f"PEAK  {travel_mm[idx_max]:+.2f} mm",
        showarrow = True,
        arrowhead = 2,
        arrowsize = 1.0,
        arrowwidth= 1.0,
        arrowcolor= _RED,
        font      = dict(family=_FONT_MONO, size=8, color=_RED),
        bgcolor   = "rgba(13,17,23,0.8)",
        bordercolor=_RED,
        borderwidth=1,
        borderpad = 3,
    )

    fig.update_layout(
        xaxis=dict(title_text="TIME  [s]"),
        yaxis=dict(title_text="SUSPENSION TRAVEL  [mm]"),
        title=dict(
            text    = (
                f"<b>SUSPENSION TRAVEL  zs − zu</b>"
                f"<span style='font-size:9px;color:{_TEXT_SEC}'>"
                f"  |  RMS = {rms_mm:.2f} mm"
                f"  |  PEAK-TO-PEAK = {peak_mm:.2f} mm"
                f"</span>"
            ),
            font    = dict(family=_FONT_MONO, size=11, color=_TEXT_PRI),
            x       = 0.0,
            xanchor = "left",
            pad     = dict(l=0, t=4),
        ),
    )

    apply_f1_theme(fig, height=320)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Tire Load Variation Plot
# ─────────────────────────────────────────────────────────────────────────────

def create_tire_load_plot(result: QuarterCarResult, params: Any) -> go.Figure:
    """
    Dynamic tire load variation ΔFz = k_t·(z_u − z_r) vs time.

    Also shows total tire load = static + dynamic, with wheel-lift detection.

    Engineering significance
    ------------------------
    Traction and cornering force are proportional to instantaneous vertical load.
    High ΔFz RMS relative to static load degrades average grip (Jensen's inequality).
    Wheel lift (Fz < 0) results in zero lateral/longitudinal capability.

    Static load is estimated as m_s·g/4 (quarter-car static loading).
    """
    t        = result.time
    delta_fz = np.asarray(result.tire_load_var) # dynamic component [N]
    rms_fz   = result.rms_tire_load          # [N]

    # Static tire load: inferred from wheel rate and mean tire deflection.
    # tire_load_var = k_t*(z_u - z_r) is the dynamic perturbation about
    # static equilibrium — static component is already zeroed by ICs.
    # For annotation purposes estimate static via mean |ΔFz| range.
    total_fz = delta_fz   # ΔFz about static equilibrium

    # Detect wheel lift events (ΔFz < -static_fz → total Fz < 0)
    wheel_lift = delta_fz < -result.rms_tire_load * 3.0

    fig = go.Figure()

    # ── Fill under zero line to show compression / extension ──────────────
    pos_mask = delta_fz >= 0
    neg_mask = delta_fz <  0

    # Positive load increase (compression)
    fig.add_trace(AdaptiveScatter(
        x         = np.concatenate([t, t[::-1]]),
        y         = np.concatenate([
            np.where(pos_mask, delta_fz, 0.0),
            np.zeros(len(t))[::-1],
        ]),
        fill      = "toself",
        fillcolor = "rgba(0,255,135,0.07)",
        line      = dict(width=0),
        name      = "LOAD INCREASE",
        showlegend= True,
        hoverinfo = "skip",
    ))

    # Negative load reduction (extension / lift risk)
    fig.add_trace(AdaptiveScatter(
        x         = np.concatenate([t, t[::-1]]),
        y         = np.concatenate([
            np.where(neg_mask, delta_fz, 0.0),
            np.zeros(len(t))[::-1],
        ]),
        fill      = "toself",
        fillcolor = "rgba(255,45,85,0.07)",
        line      = dict(width=0),
        name      = "LOAD REDUCTION",
        showlegend= True,
        hoverinfo = "skip",
    ))

    # ── Dynamic tire load trace ────────────────────────────────────────────
    fig.add_trace(AdaptiveScatter(
        x            = t,
        y            = delta_fz,
        name         = "ΔFz  TIRE LOAD VAR",
        mode         = "lines",
        line         = dict(color=_GREEN, width=2.0),
        hovertemplate= (
            "<b>TIRE LOAD VARIATION</b><br>"
            "t    : %{x:.3f} s<br>"
            "ΔFz  : %{y:.2f} N<br>"
            "<extra></extra>"
        ),
    ))

    # ── RMS band ──────────────────────────────────────────────────────────
    fig.add_hline(
        y= rms_fz,
        line_dash="dash", line_color=_AMBER, line_width=0.9, opacity=0.65,
        annotation_text=f"+RMS = {rms_fz:.1f} N",
        annotation_position="top right",
        annotation_font=dict(family=_FONT_MONO, size=8, color=_AMBER),
    )
    fig.add_hline(
        y=-rms_fz,
        line_dash="dash", line_color=_AMBER, line_width=0.9, opacity=0.65,
        annotation_text=f"−RMS = {rms_fz:.1f} N",
        annotation_position="bottom right",
        annotation_font=dict(family=_FONT_MONO, size=8, color=_AMBER),
    )
    fig.add_hline(
        y=0.0,
        line_dash="dot", line_color=_AXIS_LINE, line_width=0.7, opacity=0.5,
    )

    # ── Wheel lift warning annotation ──────────────────────────────────────
    min_fz  = float(np.min(delta_fz))
    idx_min = int(np.argmin(delta_fz))

    if min_fz < -rms_fz * 2.5:
        fig.add_annotation(
            x         = t[idx_min],
            y         = delta_fz[idx_min],
            text      = f"⚠  MIN ΔFz = {min_fz:.1f} N",
            showarrow = True,
            arrowhead = 2,
            arrowsize = 1.0,
            arrowwidth= 1.0,
            arrowcolor= _RED,
            font      = dict(family=_FONT_MONO, size=8, color=_RED),
            bgcolor   = "rgba(13,17,23,0.85)",
            bordercolor=_RED,
            borderwidth=1,
            borderpad = 3,
        )

    fig.update_layout(
        xaxis=dict(title_text="TIME  [s]"),
        yaxis=dict(title_text="TIRE LOAD VARIATION  ΔFz  [N]"),
        title=dict(
            text    = (
                f"<b>TIRE LOAD VARIATION  ΔFz = kt·(zu − zr)</b>"
                f"<span style='font-size:9px;color:{_TEXT_SEC}'>"
                f"  |  RMS = {rms_fz:.1f} N"
                f"  |  PEAK = {float(np.max(np.abs(delta_fz))):.1f} N"
                f"  |  kw = {result.k_w:,.0f} N/m"
                f"</span>"
            ),
            font    = dict(family=_FONT_MONO, size=11, color=_TEXT_PRI),
            x       = 0.0,
            xanchor = "left",
            pad     = dict(l=0, t=4),
        ),
    )

    apply_f1_theme(fig, height=320)
    # ── CALCULATE WHEEL LIFT THRESHOLD ──
    g = 9.81
    static_load = (params.m_s + params.m_u) * g
    lift_threshold = -static_load

    # 1. Add Shaded Danger Region (Below the threshold)
    y_min_plot = min(float(np.min(result.tire_load_var)) * 1.1, lift_threshold * 1.2)
    
    fig.add_hrect(
        y0=y_min_plot, 
        y1=lift_threshold,
        fillcolor="rgba(255, 45, 85, 0.15)",  # Semi-transparent red
        layer="below", 
        line_width=1,
        line_color="rgba(255, 45, 85, 0.5)",
        annotation_text="AIRBORNE / NO CONTACT",
        annotation_position="bottom left",
        annotation_font_color="#FF2D55",
        annotation_font_size=10
    )

    # 2. Add Conditional Telemetry Annotation
    if float(np.min(result.tire_load_var)) <= lift_threshold:
        # Find the first timestamp where lift occurs
        lift_indices = np.where(np.asarray(result.tire_load_var) <= lift_threshold)[0]
        first_lift_idx = lift_indices[0]
        
        fig.add_annotation(
            x=result.time[first_lift_idx],
            y=result.tire_load_var[first_lift_idx],
            text="⚠ MIN ΔFz — WHEEL LIFT / CONTACT LOSS",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor="#FF2D55",
            ax=0,
            ay=40,
            font=dict(family="JetBrains Mono", size=10, color="#FF2D55"),
            bgcolor="rgba(17, 24, 32, 0.85)", # Dark card background
            bordercolor="#FF2D55",
            borderwidth=1,
            borderpad=4
        )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Impulse Response Plot  (bonus — called from page if needed)
# ─────────────────────────────────────────────────────────────────────────────

def create_impulse_response_plot(result: QuarterCarResult) -> go.Figure:
    """
    Sprung body acceleration time response (proxy for impulse harshness).
    Useful for assessing NVH (noise-vibration-harshness) character.
    """
    t     = result.time
    ddz_s = np.asarray(result.ddz_s)

    # Envelope via Hilbert transform approximation (running RMS over 0.1s window)
    dt = (t[1] - t[0]) if len(t) > 1 else 0.002
    window = max(1, int(0.1 / dt) if dt > 0 else 1)
    rms_env = np.array([
        np.sqrt(np.mean(ddz_s[max(0, i-window):i+1]**2))
        for i in range(len(ddz_s))
    ])

    fig = go.Figure()

    # Envelope fill
    fig.add_trace(AdaptiveScatter(
        x         = np.concatenate([t, t[::-1]]),
        y         = np.concatenate([rms_env, -rms_env[::-1]]),
        fill      = "toself",
        fillcolor = "rgba(0,229,255,0.05)",
        line      = dict(width=0),
        name      = "RMS ENVELOPE",
        hoverinfo = "skip",
    ))

    # Acceleration trace
    fig.add_trace(AdaptiveScatter(
        x            = t,
        y            = ddz_s,
        name         = "BODY ACCELERATION  z̈s",
        mode         = "lines",
        line         = dict(color=_CYAN, width=1.6),
        hovertemplate= (
            "<b>BODY ACCELERATION</b><br>"
            "t    : %{x:.3f} s<br>"
            "z̈s   : %{y:.4f} m/s²<br>"
            "<extra></extra>"
        ),
    ))

    # RMS line
    rms_a = result.rms_body_accel
    fig.add_hline(
        y= rms_a, line_dash="dash", line_color=_RED, line_width=0.9, opacity=0.7,
        annotation_text=f"RMS = {rms_a:.4f} m/s²",
        annotation_position="top right",
        annotation_font=dict(family=_FONT_MONO, size=8, color=_RED),
    )
    fig.add_hline(y=-rms_a, line_dash="dash", line_color=_RED,
                  line_width=0.9, opacity=0.7)

    fig.update_layout(
        xaxis=dict(title_text="TIME  [s]"),
        yaxis=dict(title_text="ACCELERATION  [m/s²]"),
        title=dict(
            text    = (
                f"<b>BODY ACCELERATION RESPONSE</b>"
                f"<span style='font-size:9px;color:{_TEXT_SEC}'>"
                f"  |  RMS = {rms_a:.4f} m/s²"
                f"  |  ζ = {result.zeta_s:.4f}"
                f"</span>"
            ),
            font    = dict(family=_FONT_MONO, size=11, color=_TEXT_PRI),
            x       = 0.0,
            xanchor = "left",
            pad     = dict(l=0, t=4),
        ),
    )

    apply_f1_theme(fig, height=300)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Combined Overview Dashboard Plot (4-panel)
# ─────────────────────────────────────────────────────────────────────────────

def create_overview_dashboard(result: QuarterCarResult) -> go.Figure:
    """
    Single figure with 4 subplots for compact dashboard overview:
      [0,0] Transmissibility (log-freq)
      [0,1] Bode magnitude
      [1,0] Body displacement + road
      [1,1] Suspension travel
    """
    fig = make_subplots(
        rows          = 2,
        cols          = 2,
        subplot_titles= [
            "TRANSMISSIBILITY  |H(jω)|",
            "BODE MAGNITUDE  [dB]",
            "DISPLACEMENT RESPONSE  [mm]",
            "SUSPENSION TRAVEL  [mm]",
        ],
        vertical_spacing  = 0.14,
        horizontal_spacing= 0.10,
    )

    for ann in fig.layout.annotations:
        ann.update(font=dict(family=_FONT_MONO, size=9, color=_TEXT_SEC),
                   xanchor="left")

    freq  = result.freq_hz
    f_ns  = result.f_n_s
    f_nu  = result.f_n_u

    # ── [0,0] Transmissibility ─────────────────────────────────────────────
    fig.add_trace(AdaptiveScatter(
        x=freq, y=result.transmissibility_wheel,
        name="WHEEL", mode="lines",
        line=dict(color=_PURPLE, width=1.2), opacity=0.7,
        hovertemplate="Freq: %{x:.2f}Hz<br>|Hu|: %{y:.3f}<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(AdaptiveScatter(
        x=freq, y=result.transmissibility_body,
        name="BODY", mode="lines",
        line=dict(color=_CYAN, width=1.8),
        hovertemplate="Freq: %{x:.2f}Hz<br>|Hs|: %{y:.3f}<extra></extra>",
    ), row=1, col=1)

    fig.add_hline(y=1.0, row=1, col=1,
                  line_dash="dot", line_color=_AMBER, line_width=0.7, opacity=0.5)
    fig.add_vline(x=f_ns, row=1, col=1,
                  line_dash="dash", line_color=_CYAN, line_width=0.8, opacity=0.55)
    fig.add_vline(x=f_nu, row=1, col=1,
                  line_dash="dash", line_color=_PURPLE, line_width=0.8, opacity=0.55)

    # ── [0,1] Bode Magnitude ──────────────────────────────────────────────
    fig.add_trace(AdaptiveScatter(
        x=freq, y=result.bode_magnitude_db,
        name="MAG dB", mode="lines",
        line=dict(color=_GREEN, width=1.6),
        hovertemplate="Freq: %{x:.2f}Hz<br>Mag: %{y:.2f}dB<extra></extra>",
    ), row=1, col=2)

    fig.add_hline(y=0.0, row=1, col=2,
                  line_dash="dot", line_color=_AMBER, line_width=0.7, opacity=0.5)
    fig.add_vline(x=f_ns, row=1, col=2,
                  line_dash="dash", line_color=_CYAN, line_width=0.8, opacity=0.55)
    fig.add_vline(x=f_nu, row=1, col=2,
                  line_dash="dash", line_color=_PURPLE, line_width=0.8, opacity=0.55)

    # ── [1,0] Displacement ────────────────────────────────────────────────
    t = result.time
    fig.add_trace(AdaptiveScatter(
        x=t, y=np.asarray(result.z_r)*1e3,
        name="ROAD zr", mode="lines",
        line=dict(color=_AMBER, width=0.9, dash="dot"), opacity=0.7,
        hovertemplate="t: %{x:.2f}s<br>zr: %{y:.2f}mm<extra></extra>",
    ), row=2, col=1)

    fig.add_trace(AdaptiveScatter(
        x=t, y=np.asarray(result.z_u)*1e3,
        name="WHEEL zu", mode="lines",
        line=dict(color=_PURPLE, width=1.2), opacity=0.75,
        hovertemplate="t: %{x:.2f}s<br>zu: %{y:.3f}mm<extra></extra>",
    ), row=2, col=1)

    fig.add_trace(AdaptiveScatter(
        x=t, y=np.asarray(result.z_s)*1e3,
        name="BODY zs", mode="lines",
        line=dict(color=_CYAN, width=1.8),
        hovertemplate="t: %{x:.2f}s<br>zs: %{y:.3f}mm<extra></extra>",
    ), row=2, col=1)

    # ── [1,1] Suspension Travel ───────────────────────────────────────────
    travel_mm = np.asarray(result.susp_travel) * 1e3
    rms_mm    = result.rms_susp_travel * 1e3

    fig.add_trace(AdaptiveScatter(
        x=t, y=travel_mm,
        name="TRAVEL zs-zu", mode="lines",
        line=dict(color=_CYAN, width=1.8),
        hovertemplate="t: %{x:.2f}s<br>Travel: %{y:.3f}mm<extra></extra>",
    ), row=2, col=2)

    fig.add_hline(y= rms_mm, row=2, col=2,
                  line_dash="dash", line_color=_AMBER, line_width=0.8, opacity=0.6)
    fig.add_hline(y=-rms_mm, row=2, col=2,
                  line_dash="dash", line_color=_AMBER, line_width=0.8, opacity=0.6)

    # ── Axis types ────────────────────────────────────────────────────────
    fig.update_xaxes(type="log", row=1, col=1)
    fig.update_xaxes(type="log", row=1, col=2)

    fig.update_xaxes(title_text="FREQ [Hz]",  row=1, col=1)
    fig.update_xaxes(title_text="FREQ [Hz]",  row=1, col=2)
    fig.update_xaxes(title_text="TIME [s]",   row=2, col=1)
    fig.update_xaxes(title_text="TIME [s]",   row=2, col=2)
    fig.update_yaxes(title_text="|H(jω)|",    row=1, col=1)
    fig.update_yaxes(title_text="dB",         row=1, col=2)
    fig.update_yaxes(title_text="mm",         row=2, col=1)
    fig.update_yaxes(title_text="mm",         row=2, col=2)

    fig.update_layout(
        title=dict(
            text    = (
                f"<b>QUARTER CAR — OVERVIEW DASHBOARD</b>"
                f"<span style='font-size:9px;color:{_TEXT_SEC}'>"
                f"  |  fn,s={f_ns:.2f}Hz  fn,u={f_nu:.2f}Hz"
                f"  |  ζ={result.zeta_s:.4f}"
                f"  |  RMS ẍ={result.rms_body_accel:.4f}m/s²"
                f"</span>"
            ),
            font    = dict(family=_FONT_MONO, size=11, color=_TEXT_PRI),
            x       = 0.0,
            xanchor = "left",
            pad     = dict(l=0, t=4),
        ),
    )

    apply_f1_theme(fig, height=580, show_legend=True,
                   margin=dict(l=58, r=24, t=52, b=52))
    return fig


import io
from datetime import datetime
from typing import Union

def create_half_car_heave_plot(result: HalfCarResult) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(AdaptiveScatter(
        x=result.time, y=np.asarray(result.z_s)*1000, 
        name="Heave (CG)", mode="lines",
        line=dict(color=_CYAN, width=2.0)
    ))
    fig.add_trace(AdaptiveScatter(
        x=result.time, y=np.asarray(result.z_rf)*1000, 
        name="Front Road", mode="lines",
        line=dict(color="#334155", dash="dash", width=1.5)
    ))
    fig.add_trace(AdaptiveScatter(
        x=result.time, y=np.asarray(result.z_rr)*1000, 
        name="Rear Road", mode="lines",
        line=dict(color="#94A3B8", dash="dot", width=1.5)
    ))
    fig.update_layout(
        title=dict(
            text="<b>HALF-CAR HEAVE RESPONSE</b><br><span style='font-size:9px'>Displacement [mm]</span>",
            font=dict(family=_FONT_MONO, size=11, color=_TEXT_PRI)
        ),
        yaxis_title="DISPLACEMENT [mm]",
        xaxis_title="TIME [s]"
    )
    apply_f1_theme(fig, height=400)
    return fig

def create_half_car_pitch_plot(result: HalfCarResult) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(AdaptiveScatter(
        x=result.time, y=np.asarray(result.theta) * (180.0/np.pi), 
        name="Pitch Angle", mode="lines",
        line=dict(color=_AMBER, width=2.0)
    ))
    fig.update_layout(
        title=dict(
            text="<b>HALF-CAR PITCH RESPONSE</b><br><span style='font-size:9px'>Angle [deg]</span>",
            font=dict(family=_FONT_MONO, size=11, color=_TEXT_PRI)
        ),
        yaxis_title="ANGLE [deg]",
        xaxis_title="TIME [s]"
    )
    apply_f1_theme(fig, height=350)
    return fig

def create_half_car_susp_plot(result: HalfCarResult) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(AdaptiveScatter(
        x=result.time, y=np.asarray(result.susp_travel_f)*1000, 
        name="Front Deflection", mode="lines",
        line=dict(color=_RED, width=1.8)
    ))
    fig.add_trace(AdaptiveScatter(
        x=result.time, y=np.asarray(result.susp_travel_r)*1000, 
        name="Rear Deflection", mode="lines",
        line=dict(color=_PURPLE, width=1.8)
    ))
    fig.update_layout(
        title=dict(
            text="<b>SUSPENSION TRAVEL</b><br><span style='font-size:9px'>Deflection [mm]</span>",
            font=dict(family=_FONT_MONO, size=11, color=_TEXT_PRI)
        ),
        yaxis_title="TRAVEL [mm]",
        xaxis_title="TIME [s]"
    )
    apply_f1_theme(fig, height=350)
    return fig

def create_half_car_tire_plot(result) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(AdaptiveScatter(
        x=result.time, y=np.asarray(result.tire_load_f), 
        name="Front Tire", mode="lines",
        line=dict(color=_CYAN, width=1.8)
    ))
    fig.add_trace(AdaptiveScatter(
        x=result.time, y=np.asarray(result.tire_load_r), 
        name="Rear Tire", mode="lines",
        line=dict(color=_YELLOW, width=1.8)
    ))
    fig.update_layout(
        title=dict(
            text="<b>DYNAMIC TIRE LOAD</b><br><span style='font-size:9px'>Force [N]</span>",
            font=dict(family=_FONT_MONO, size=11, color=_TEXT_PRI)
        ),
        yaxis_title="FORCE [N]",
        xaxis_title="TIME [s]"
    )
    apply_f1_theme(fig, height=350)
    return fig


def build_report_pdf(result: Union[QuarterCarResult, HalfCarResult, FullCarResult], baseline: Union[QuarterCarResult, HalfCarResult] = None, model_type="quarter") -> bytes:
    """Generate a multi-page PDF report using reportlab."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
    except ImportError:
        raise ImportError("reportlab is required for PDF generation. pip install reportlab")

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Premium branding colors
    primary_color = (0.835, 0.0, 0.11) if model_type == "full" else (0, 0.9, 1.0) # Porsche Red for Full Car, Cyan for others
    bg_color = (0.06, 0.07, 0.08) # Dark mode background
    text_color = (0.9, 0.9, 0.92) # Light text
    
    def draw_background(canvas_obj):
        canvas_obj.setFillColorRGB(*bg_color)
        canvas_obj.rect(0, 0, width, height, fill=1, stroke=0)
        canvas_obj.setFillColorRGB(*text_color)

    
    footer_text = f"Generated by SuspensionLab PRO v1.0.0  |  {timestamp}"

    def draw_footer(canvas_obj):
        canvas_obj.setFont("Courier", 8)
        canvas_obj.setFillColorRGB(0.5, 0.5, 0.5)
        canvas_obj.drawString(30, 20, footer_text)
        canvas_obj.setStrokeColorRGB(0.2, 0.2, 0.2)
        canvas_obj.line(30, 30, width - 30, 30)
        canvas_obj.setStrokeColorRGB(1, 1, 1) # reset
        
    # --- Page 1: Executive Summary ---
    draw_background(c)
    c.setFillColorRGB(*text_color)
    c.setFont("Helvetica-Bold", 24)
    c.setFillColorRGB(*primary_color)
    c.drawString(30, height - 50, "SuspensionLab PRO" if model_type != "full" else "SL PRO // MOTORSPORT")
    c.setFont("Helvetica", 14)
    c.setFillColorRGB(*text_color)
    
    if model_type == "full":
        c.drawString(30, height - 70, "7-DOF Full-Car Dynamics Report")
    elif model_type == "half":
        c.drawString(30, height - 70, "Half-Car Pitch-Plane Executive Summary")
    else:
        c.drawString(30, height - 70, "Quarter-Car Simulation Executive Summary")
    
    c.setStrokeColorRGB(*primary_color)
    c.setLineWidth(2)
    c.line(30, height - 80, width - 30, height - 80)
    
    # KPIs
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30, height - 120, "Key Performance Indicators (KPIs)")
    c.setFont("Courier", 10)
    
    if model_type == "quarter":
        kpis = [
            f"Sprung Nat. Freq (fn,s): {result.f_n_s:.2f} Hz",
            f"Unsprung Nat. Freq (fn,u): {result.f_n_u:.2f} Hz",
            f"Damping Ratio (zeta_s): {result.zeta_s:.3f}",
            f"Peak Transmissibility: {result.peak_transmissibility:.2f}x",
            f"RMS Body Accel: {result.rms_body_accel:.3f} m/s^2",
            f"Peak Susp Travel: {result.peak_susp_travel*1000:.1f} mm"
        ]
    elif model_type == "half":
        kpis = [
            f"Heave Freq: {result.f_n_heave:.2f} Hz",
            f"Pitch Freq: {result.f_n_pitch:.2f} Hz",
            f"Front Unsprung Freq: {result.f_n_uf:.2f} Hz",
            f"Rear Unsprung Freq: {result.f_n_ur:.2f} Hz",
            f"RMS Heave Accel: {result.rms_heave_accel:.3f} m/s^2",
            f"RMS Pitch Accel: {result.rms_pitch_accel:.3f} rad/s^2"
        ]
    else:
        import numpy as np
        kpis = [
            f"Heave Freq: {result.f_n_heave:.2f} Hz",
            f"Pitch Freq: {result.f_n_pitch:.2f} Hz",
            f"Roll Freq: {result.f_n_roll:.2f} Hz",
            f"Roll Stiff: {result.roll_stiffness_dist:.1f}% F",
            f"Max LLT F: {max(np.max(np.abs(result.lateral_load_transfer_f)), 0):.0f} N",
            f"Max LLT R: {max(np.max(np.abs(result.lateral_load_transfer_r)), 0):.0f} N"
        ]
        
    y = height - 140
    for k in kpis:
        c.drawString(40, y, k)
        y -= 20
        
    # Verdict
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30, y, "Comfort & Setup Verdict")
    y -= 20
    c.setFont("Courier", 10)
    
    if model_type == "quarter":
        if result.rms_body_accel < 0.315:
            verdict = "EXCELLENT - Not uncomfortable"
        elif result.rms_body_accel < 0.630:
            verdict = "ACCEPTABLE - Slightly uncomfortable"
        elif result.rms_body_accel < 1.000:
            verdict = "HARSH - Fairly uncomfortable"
        else:
            verdict = "UNACCEPTABLE - Uncomfortable"
            
        c.drawString(40, y, f"ISO 2631-1 Rating: {verdict}")
        y -= 20
        if result.zeta_s < 0.2:
            setup = "CONFLICT - Critically Underdamped"
        elif result.zeta_s > 0.8:
            setup = "CONFLICT - Critically Overdamped"
        else:
            setup = "ALIGNED - Nominal Damping"
        c.drawString(40, y, f"Setup Verdict: {setup}")
    else:
        if result.rms_heave_accel < 0.315:
            verdict = "EXCELLENT - Not uncomfortable"
        elif result.rms_heave_accel < 0.630:
            verdict = "ACCEPTABLE - Slightly uncomfortable"
        elif result.rms_heave_accel < 1.000:
            verdict = "HARSH - Fairly uncomfortable"
        else:
            verdict = "UNACCEPTABLE - Uncomfortable"
            
        c.drawString(40, y, f"ISO 2631-1 Rating (Heave): {verdict}")
        y -= 20
        c.drawString(40, y, f"Note: Baseline optimization not active for Half-Car")
    
    draw_footer(c)
    c.showPage()
    
    # --- Page 2: Frequency Domain or Half-Car Pitch ---
    draw_background(c)
    c.setFillColorRGB(*text_color)
    c.setFont("Helvetica-Bold", 16)
    if model_type == "quarter":
        c.drawString(30, height - 50, "Frequency Domain Analysis")
    elif model_type == "half":
        c.drawString(30, height - 50, "Time Domain Analysis (Pitch & Susp)")
    else:
        c.drawString(30, height - 50, "Body Dynamics (Roll & Load Transfer)")
        
    c.line(30, height - 60, width - 30, height - 60)
    
    try:
        if model_type == "quarter":
            tx_fig = create_transmissibility_plot(result, baseline)
            tx_img_bytes = tx_fig.to_image(format="png", width=700, height=400, scale=2)
            c.drawImage(ImageReader(io.BytesIO(tx_img_bytes)), 30, height - 380, width=500, height=300, preserveAspectRatio=True)
            
            bode_fig = create_bode_plot(result)
            bode_img_bytes = bode_fig.to_image(format="png", width=700, height=500, scale=2)
            c.drawImage(ImageReader(io.BytesIO(bode_img_bytes)), 30, height - 730, width=500, height=330, preserveAspectRatio=True)
        elif model_type == "half":
            pitch_fig = create_half_car_pitch_plot(result)
            pitch_img_bytes = pitch_fig.to_image(format="png", width=700, height=400, scale=2)
            c.drawImage(ImageReader(io.BytesIO(pitch_img_bytes)), 30, height - 380, width=500, height=300, preserveAspectRatio=True)
            
            susp_fig = create_half_car_susp_plot(result)
            susp_img_bytes = susp_fig.to_image(format="png", width=700, height=400, scale=2)
            c.drawImage(ImageReader(io.BytesIO(susp_img_bytes)), 30, height - 730, width=500, height=300, preserveAspectRatio=True)
        else:
            roll_fig = create_full_car_roll_plot(result)
            roll_img_bytes = roll_fig.to_image(format="png", width=700, height=400, scale=2)
            c.drawImage(ImageReader(io.BytesIO(roll_img_bytes)), 30, height - 380, width=500, height=300, preserveAspectRatio=True)
            
            llt_fig = create_full_car_load_transfer_plot(result)
            llt_img_bytes = llt_fig.to_image(format="png", width=700, height=400, scale=2)
            c.drawImage(ImageReader(io.BytesIO(llt_img_bytes)), 30, height - 730, width=500, height=300, preserveAspectRatio=True)
    except Exception as e:
        c.setFont("Courier", 10)
        c.drawString(30, height - 100, f"Error generating plots: {e}")

    draw_footer(c)
    c.showPage()
    
    # --- Page 3: Time Domain (Heave for Half-Car) ---
    draw_background(c)
    c.setFillColorRGB(*text_color)
    c.setFont("Helvetica-Bold", 16)
    if model_type == "quarter":
        c.drawString(30, height - 50, "Time Domain Analysis")
    elif model_type == "half":
        c.drawString(30, height - 50, "Time Domain Analysis (Heave Response)")
    else:
        c.drawString(30, height - 50, "Unsprung Mass Telemetry")
    c.line(30, height - 60, width - 30, height - 60)
    
    try:
        if model_type == "quarter":
            step_fig = create_step_response_plot(result, baseline)
            step_img_bytes = step_fig.to_image(format="png", width=700, height=400, scale=2)
            c.drawImage(ImageReader(io.BytesIO(step_img_bytes)), 30, height - 380, width=500, height=300, preserveAspectRatio=True)
            
            travel_fig = create_suspension_travel_plot(result)
            travel_img_bytes = travel_fig.to_image(format="png", width=700, height=400, scale=2)
            c.drawImage(ImageReader(io.BytesIO(travel_img_bytes)), 30, height - 730, width=500, height=300, preserveAspectRatio=True)
        elif model_type == "half":
            heave_fig = create_half_car_heave_plot(result)
            heave_img_bytes = heave_fig.to_image(format="png", width=700, height=400, scale=2)
            c.drawImage(ImageReader(io.BytesIO(heave_img_bytes)), 30, height - 380, width=500, height=300, preserveAspectRatio=True)
        else:
            susp_fig = create_full_car_susp_plot(result)
            susp_img_bytes = susp_fig.to_image(format="png", width=700, height=400, scale=2)
            c.drawImage(ImageReader(io.BytesIO(susp_img_bytes)), 30, height - 380, width=500, height=300, preserveAspectRatio=True)
    except Exception as e:
        c.setFont("Courier", 10)
        c.drawString(30, height - 100, f"Error generating plots: {e}")
        
    draw_footer(c)
    c.showPage()
    
    # --- Page 4: Baseline Comparison (Only for Quarter-Car) ---
    if model_type == "quarter" and baseline:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(30, height - 50, "Comparative Analysis")
        c.line(30, height - 60, width - 30, height - 60)
        
        c.setFont("Courier-Bold", 10)
        c.drawString(40, height - 100, "Metric")
        c.drawString(200, height - 100, "Baseline")
        c.drawString(300, height - 100, "Current")
        c.drawString(400, height - 100, "Delta")
        
        metrics = [
            ("RMS Body Accel", baseline.rms_body_accel, result.rms_body_accel, "m/s^2"),
            ("Peak Transmissibility", baseline.peak_transmissibility, result.peak_transmissibility, "x"),
            ("Damping Ratio", baseline.zeta_s, result.zeta_s, ""),
            ("Peak Susp Travel", baseline.peak_susp_travel*1000, result.peak_susp_travel*1000, "mm")
        ]
        
        c.setFont("Courier", 10)
        y = height - 120
        for name, b_val, c_val, unit in metrics:
            delta = c_val - b_val
            c.drawString(40, y, name)
            c.drawString(200, y, f"{b_val:.3f}")
            c.drawString(300, y, f"{c_val:.3f}")
            c.drawString(400, y, f"{delta:+.3f} {unit}")
            y -= 20
            
        draw_footer(c)
        c.showPage()
        
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

# ─────────────────────────────────────────────────────────────────────────────
# Full-Car (7-DOF) Dashboard Specific Plots
# ─────────────────────────────────────────────────────────────────────────────

from suspensionlab.shared.models import FullCarResultSchema as FullCarResult

def create_full_car_roll_plot(result: FullCarResult) -> go.Figure:
    """Creates a roll and pitch response plot."""
    fig = go.Figure()

    t = np.asarray(result.time)
    phi = np.asarray(result.phi) * (180.0 / np.pi)  # Convert to degrees
    theta = np.asarray(result.theta) * (180.0 / np.pi)
    
    fig.add_trace(AdaptiveScatter(
        x=t, y=phi,
        mode="lines",
        name="Roll",
        line=dict(color=_CYAN, width=2)
    ))
    
    fig.add_trace(AdaptiveScatter(
        x=t, y=theta,
        mode="lines",
        name="Pitch",
        line=dict(color=_PURPLE, width=2, dash="dot")
    ))

    fig.update_layout(
        title="Body Roll & Pitch Angles",
        xaxis_title="TIME [s]",
        yaxis_title="ANGLE [deg]"
    )
    return apply_f1_theme(fig, show_legend=True)

def create_full_car_load_transfer_plot(result: FullCarResult) -> go.Figure:
    """Plots Lateral Load Transfer across Front and Rear axles."""
    fig = go.Figure()

    t = np.asarray(result.time)
    llt_f = np.asarray(result.lateral_load_transfer_f)
    llt_r = np.asarray(result.lateral_load_transfer_r)

    fig.add_trace(AdaptiveScatter(
        x=t, y=llt_f,
        mode="lines",
        name="Front Axle",
        line=dict(color=_CYAN, width=2)
    ))
    
    fig.add_trace(AdaptiveScatter(
        x=t, y=llt_r,
        mode="lines",
        name="Rear Axle",
        line=dict(color=_AMBER, width=2)
    ))

    fig.update_layout(
        title="Lateral Load Transfer",
        xaxis_title="TIME [s]",
        yaxis_title="LOAD TRANSFER [N]"
    )
    return apply_f1_theme(fig, show_legend=True)

def create_full_car_susp_plot(result: FullCarResult) -> go.Figure:
    """Plots suspension displacements for all 4 corners."""
    fig = go.Figure()

    t = np.asarray(result.time)
    z_ufl = np.asarray(result.z_ufl) * 1000.0
    z_ufr = np.asarray(result.z_ufr) * 1000.0
    z_url = np.asarray(result.z_url) * 1000.0
    z_urr = np.asarray(result.z_urr) * 1000.0

    fig.add_trace(AdaptiveScatter(x=t, y=z_ufl, mode="lines", name="FL Unsprung", line=dict(color=_CYAN, width=1.5)))
    fig.add_trace(AdaptiveScatter(x=t, y=z_ufr, mode="lines", name="FR Unsprung", line=dict(color=_PURPLE, width=1.5)))
    fig.add_trace(AdaptiveScatter(x=t, y=z_url, mode="lines", name="RL Unsprung", line=dict(color=_AMBER, width=1.5)))
    fig.add_trace(AdaptiveScatter(x=t, y=z_urr, mode="lines", name="RR Unsprung", line=dict(color=_GREEN, width=1.5)))

    fig.update_layout(
        title="Unsprung Mass Displacement",
        xaxis_title="TIME [s]",
        yaxis_title="DISPLACEMENT [mm]"
    )
    return apply_f1_theme(fig, show_legend=True)
