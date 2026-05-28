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

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from physics.quarter_car import QuarterCarResult

# ─────────────────────────────────────────────────────────────────────────────
# Design Tokens
# ─────────────────────────────────────────────────────────────────────────────

_BG_PRIMARY   = "#07090D"
_BG_PAPER     = "#07090D"
_BG_PLOT      = "#0D1117"
_BG_PANEL     = "#111820"

_CYAN         = "#00E5FF"
_CYAN_DIM     = "rgba(0,229,255,0.18)"
_CYAN_FILL    = "rgba(0,229,255,0.06)"
_PURPLE       = "#BF5AF2"
_PURPLE_FILL  = "rgba(191,90,242,0.06)"
_AMBER        = "#FFB800"
_AMBER_FILL   = "rgba(255,184,0,0.07)"
_GREEN        = "#00FF87"
_GREEN_FILL   = "rgba(0,255,135,0.06)"
_RED          = "#FF2D55"
_RED_FILL     = "rgba(255,45,85,0.07)"
_WHITE        = "#DCE8F5"
_GRID         = "rgba(255,255,255,0.055)"
_AXIS_LINE    = "rgba(255,255,255,0.12)"
_TEXT_PRI     = "#DCE8F5"
_TEXT_SEC     = "#5A7A99"
_FONT_MONO    = "JetBrains Mono, Courier New, monospace"
_FONT_LABEL   = "Rajdhani, Arial, sans-serif"

_HOVER_BG     = "#111820"
_HOVER_BORDER = "#00E5FF"


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

def create_transmissibility_plot(result: QuarterCarResult) -> go.Figure:
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
    fig.add_trace(go.Scatter(
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
    fig.add_trace(go.Scatter(
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
    fig.add_trace(go.Scatter(
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
        go.Scatter(
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
        go.Scatter(
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

def create_step_response_plot(result: QuarterCarResult) -> go.Figure:
    """
    Time-domain displacement response: body (z_s), wheel (z_u), road (z_r).

    Y-axis in millimetres for engineering readability.
    Includes a secondary trace for body acceleration [m/s²].

    Two rows:
      Row 1 : Displacement [mm]  — z_s, z_u, z_r
      Row 2 : Body acceleration  [m/s²]
    """
    t      = result.time
    z_s_mm = result.z_s    * 1e3    # → mm
    z_u_mm = result.z_u    * 1e3
    z_r_mm = result.z_r    * 1e3
    ddz_s  = result.ddz_s           # m/s²

    fig = make_subplots(
        rows             = 2,
        cols             = 1,
        shared_xaxes     = True,
        row_heights      = [0.60, 0.40],
        vertical_spacing = 0.06,
        subplot_titles   = ["DISPLACEMENT  [mm]", "BODY ACCELERATION  [m/s²]"],
    )

    for ann in fig.layout.annotations:
        ann.update(font=dict(family=_FONT_MONO, size=9, color=_TEXT_SEC),
                   x=0.0, xanchor="left")

    # ── Road profile (filled area) ─────────────────────────────────────────
    fig.add_trace(
        go.Scatter(
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
        go.Scatter(
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
        go.Scatter(
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

    # ── Body acceleration ──────────────────────────────────────────────────
    fig.add_trace(
        go.Scatter(
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
    fig.update_xaxes(title_text="TIME  [s]", row=2, col=1)
    fig.update_yaxes(title_text="DISPLACEMENT  [mm]", row=1, col=1)
    fig.update_yaxes(title_text="ACCELERATION  [m/s²]", row=2, col=1)

    fig.update_layout(
        title=dict(
            text    = (
                f"<b>TIME DOMAIN — DISPLACEMENT & ACCELERATION RESPONSE</b>"
                f"<span style='font-size:9px;color:{_TEXT_SEC}'>"
                f"  |  RMS ẍs = {rms_a:.4f} m/s²"
                f"  |  PROFILE: {result.z_r.max()*1e3:.1f} mm"
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
    travel_mm  = result.susp_travel * 1e3    # → mm
    rms_mm     = result.rms_susp_travel * 1e3
    peak_mm    = result.peak_susp_travel * 1e3

    fig = go.Figure()

    # ── Fill band between ±RMS ────────────────────────────────────────────
    fig.add_trace(go.Scatter(
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
    fig.add_trace(go.Scatter(
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

def create_tire_load_plot(result: QuarterCarResult) -> go.Figure:
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
    delta_fz = result.tire_load_var          # dynamic component [N]
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
    fig.add_trace(go.Scatter(
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
    fig.add_trace(go.Scatter(
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
    fig.add_trace(go.Scatter(
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
    ddz_s = result.ddz_s

    # Envelope via Hilbert transform approximation (running RMS over 0.1s window)
    dt = (t[1] - t[0]) if len(t) > 1 else 0.002
    window = max(1, int(0.1 / dt) if dt > 0 else 1)
    rms_env = np.array([
        np.sqrt(np.mean(ddz_s[max(0, i-window):i+1]**2))
        for i in range(len(ddz_s))
    ])

    fig = go.Figure()

    # Envelope fill
    fig.add_trace(go.Scatter(
        x         = np.concatenate([t, t[::-1]]),
        y         = np.concatenate([rms_env, -rms_env[::-1]]),
        fill      = "toself",
        fillcolor = "rgba(0,229,255,0.05)",
        line      = dict(width=0),
        name      = "RMS ENVELOPE",
        hoverinfo = "skip",
    ))

    # Acceleration trace
    fig.add_trace(go.Scatter(
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
    fig.add_trace(go.Scatter(
        x=freq, y=result.transmissibility_wheel,
        name="WHEEL", mode="lines",
        line=dict(color=_PURPLE, width=1.2), opacity=0.7,
        hovertemplate="Freq: %{x:.2f}Hz<br>|Hu|: %{y:.3f}<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
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
    fig.add_trace(go.Scatter(
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
    fig.add_trace(go.Scatter(
        x=t, y=result.z_r*1e3,
        name="ROAD zr", mode="lines",
        line=dict(color=_AMBER, width=0.9, dash="dot"), opacity=0.7,
        hovertemplate="t: %{x:.2f}s<br>zr: %{y:.2f}mm<extra></extra>",
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=t, y=result.z_u*1e3,
        name="WHEEL zu", mode="lines",
        line=dict(color=_PURPLE, width=1.2), opacity=0.75,
        hovertemplate="t: %{x:.2f}s<br>zu: %{y:.3f}mm<extra></extra>",
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=t, y=result.z_s*1e3,
        name="BODY zs", mode="lines",
        line=dict(color=_CYAN, width=1.8),
        hovertemplate="t: %{x:.2f}s<br>zs: %{y:.3f}mm<extra></extra>",
    ), row=2, col=1)

    # ── [1,1] Suspension Travel ───────────────────────────────────────────
    travel_mm = result.susp_travel * 1e3
    rms_mm    = result.rms_susp_travel * 1e3

    fig.add_trace(go.Scatter(
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
