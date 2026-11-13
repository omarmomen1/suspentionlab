/**
 * Typed plot builders for the quarter-car workspace.
 *
 * Every simulation result crossing the backend→frontend boundary conforms to
 * `QuarterCarSeries`; parameters conform to `SpringDamperParams`. These
 * contracts mean a backend field rename is now a COMPILE ERROR here instead
 * of an empty chart at runtime.
 */
import { Trace } from "./TraceManager";
import { PLOT_COLORS } from "./sim/theme";

// ── Data contracts ───────────────────────────────────────────────────────────

/** Time- and frequency-domain series returned by the quarter-car solver. */
export interface QuarterCarSeries {
  time: number[];
  z_s: number[];
  z_u: number[];
  z_r: number[];
  dz_s: number[];
  dz_u: number[];
  ddz_s: number[];
  susp_travel: number[];
  tire_defl: number[];
  tire_load_var: number[];
  freq_hz: number[];
  transmissibility_body: number[];
  transmissibility_wheel: number[];
  bode_magnitude_db: number[];
  bode_phase_deg: number[];
  /** Present only when the run included a road-profile PSD analysis. */
  psd_values?: number[];
  psd_freqs?: number[];
}

/** Spring/damper parameters needed to recompute suspension forces client-side. */
export interface SpringDamperParams {
  k_s: number;
  c: number;
  MR: number;
}

/** PSD payload produced by the road-profile analysis. */
export interface PsdPayload {
  freqs: number[];
  psd: number[];
}

/** Minimal structural type for Plotly trace literals (avoids `any`). */
export interface PlotTrace {
  [key: string]: unknown;
  x?: number[];
  y?: number[];
}

const C = {
  body: PLOT_COLORS.primary,     // #06B6D4 Telemetry Cyan — Primary / Baseline / Setup A
  wheel: PLOT_COLORS.secondary,  // #F43F5E Racing Coral — Secondary / Perturbed / Setup B
  road: "#94A3B8",               // Muted steel road excitation reference
  accel: PLOT_COLORS.primary,    // #06B6D4 Telemetry Cyan
  travel: PLOT_COLORS.primary,   // #06B6D4 Telemetry Cyan
  tire: PLOT_COLORS.secondary,   // #F43F5E Racing Coral
  load: PLOT_COLORS.primary,     // #06B6D4 Telemetry Cyan
  mag: PLOT_COLORS.primary,      // #06B6D4 Telemetry Cyan
  phase: PLOT_COLORS.target,     // #F59E0B Precision Amber — Target / Optimal / Envelope
  total: PLOT_COLORS.target,     // #F59E0B Precision Amber
  start: PLOT_COLORS.validated,  // #10B981 Emerald — Validated / Pass Band / Origin
};

const COMPARISON_PALETTE = [
  PLOT_COLORS.secondary, // #F43F5E — Secondary / Perturbed / Setup B
  PLOT_COLORS.target,    // #F59E0B — Target / Optimal / Envelope
  PLOT_COLORS.validated, // #10B981 — Validated / Pass Band
  PLOT_COLORS.primary,   // #06B6D4 — Cycle fallback
] as const;

function comparisonColor(index: number): string {
  return COMPARISON_PALETTE[index % COMPARISON_PALETTE.length];
}

const DELTA_REF_PRIMARY = { color: "#64748B", width: 1, dash: "dot" };
const DELTA_REF_SECONDARY = { color: "#475569", width: 1, dash: "dot" };

function plotType(x?: number[], fallback = "scatter"): string {
  if (x && x.length > 1000) return "scattergl";
  return fallback;
}

/**
 * High-performance Largest Triangle Three Buckets (LTTB) decimation algorithm.
 * Downsamples (x, y) arrays to `threshold` points while preserving visual extrema and peaks.
 */
export function lttbDecimate(xArr: number[], yArr: number[], threshold = 2000): { x: number[]; y: number[] } {
  const dataLength = xArr ? xArr.length : 0;
  if (!xArr || !yArr || threshold >= dataLength || threshold <= 0) {
    return { x: xArr, y: yArr };
  }

  const sampledX: number[] = new Array(threshold);
  const sampledY: number[] = new Array(threshold);
  let sampledIndex = 0;

  const every = (dataLength - 2) / (threshold - 2);
  let a = 0;
  let maxAreaPoint = { x: xArr[0], y: yArr[0] };
  let nextA = 0;

  sampledX[sampledIndex] = xArr[a];
  sampledY[sampledIndex] = yArr[a];
  sampledIndex++;

  for (let i = 0; i < threshold - 2; i++) {
    let avgX = 0;
    let avgY = 0;
    let avgRangeStart = Math.floor((i + 1) * every) + 1;
    let avgRangeEnd = Math.floor((i + 2) * every) + 1;
    avgRangeEnd = avgRangeEnd < dataLength ? avgRangeEnd : dataLength;

    const avgRangeLength = avgRangeEnd - avgRangeStart;
    for (let j = avgRangeStart; j < avgRangeEnd; j++) {
      avgX += xArr[j];
      avgY += yArr[j];
    }
    avgX /= (avgRangeLength || 1);
    avgY /= (avgRangeLength || 1);

    let rangeOffs = Math.floor((i + 0) * every) + 1;
    const rangeTo = Math.floor((i + 1) * every) + 1;
    const pointAX = xArr[a];
    const pointAY = yArr[a];
    let maxArea = -1;

    for (; rangeOffs < rangeTo && rangeOffs < dataLength; rangeOffs++) {
      const area = Math.abs((pointAX - avgX) * (yArr[rangeOffs] - pointAY) - (pointAX - xArr[rangeOffs]) * (avgY - pointAY)) * 0.5;
      if (area > maxArea) {
        maxArea = area;
        maxAreaPoint = { x: xArr[rangeOffs], y: yArr[rangeOffs] };
        nextA = rangeOffs;
      }
    }

    sampledX[sampledIndex] = maxAreaPoint.x;
    sampledY[sampledIndex] = maxAreaPoint.y;
    sampledIndex++;
    a = nextA;
  }

  sampledX[sampledIndex] = xArr[dataLength - 1];
  sampledY[sampledIndex] = yArr[dataLength - 1];

  return { x: sampledX, y: sampledY };
}

export function optTrace(x: number[], y: number[], name: string, lineOpts: Record<string, unknown> = {}, extra: Record<string, unknown> = {}): PlotTrace {
  const { x: dx, y: dy } = x && x.length > 2000 ? lttbDecimate(x, y, 2000) : { x, y };
  return {
    x: dx,
    y: dy,
    type: plotType(dx),
    mode: (extra.mode as string) || "lines",
    name,
    line: lineOpts,
    ...extra
  };
}

function applyTrace(t: Trace, x: number[], y: number[], name: string, color?: string, dash?: string, type = "scatter", mode = "lines", deltaMode = false): PlotTrace {
  const { x: dx, y: dy } = x && x.length > 2000 ? lttbDecimate(x, y, 2000) : { x, y };
  const finalType = plotType(dx, type);
  return {
    x: dx, y: dy,
    type: finalType,
    mode,
    name: `${t.name} ${name}${deltaMode ? " (Δ vs Base)" : ""}`,
    line: { color: color || comparisonColor(0), width: 1.5, dash: dash || "dash" },
    opacity: 0.85
  };
}

const diffArr = (arr: number[], baseArr: number[], deltaMode: boolean) => {
  if (!deltaMode || !baseArr || !arr || arr.length !== baseArr.length) return arr;
  return arr.map((v, i) => v - baseArr[i]);
};

// -- TAB 0 --

export function bDisp(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => {
    const color = comparisonColor(idx);
    return [
      applyTrace(t, t.data.time, diffArr(t.data.z_s, r.z_s, deltaMode).map((v: number) => v * 1000), "Body", color, "dash", "scatter", "lines", deltaMode),
      applyTrace(t, t.data.time, diffArr(t.data.z_u, r.z_u, deltaMode).map((v: number) => v * 1000), "Wheel", color, "dot", "scatter", "lines", deltaMode)
    ];
  });
  return [...p,
    optTrace(
      r.time,
      diffArr(r.z_s, r.z_s, deltaMode).map((v: number) => v * 1000),
      deltaMode ? "Baseline Ref (0.0 Δ)" : "Body z_s",
      deltaMode ? DELTA_REF_PRIMARY : { color: C.body, width: 2 }
    ),
    optTrace(
      r.time,
      diffArr(r.z_u, r.z_u, deltaMode).map((v: number) => v * 1000),
      deltaMode ? "Wheel Ref (0.0 Δ)" : "Wheel z_u",
      deltaMode ? DELTA_REF_SECONDARY : { color: C.wheel, width: 1.5 }
    ),
    optTrace(
      r.time,
      diffArr(r.z_r, r.z_r, deltaMode).map((v: number) => v * 1000),
      deltaMode ? "Road Ref (0.0 Δ)" : "Road z_r",
      { color: C.road, width: 1, dash: "dash" }
    )
  ];
}

export function bVel(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => {
    const color = comparisonColor(idx);
    return [
      applyTrace(t, t.data.time, diffArr(t.data.dz_s, r.dz_s, deltaMode).map((v: number) => v * 1000), "Body vel", color, "dash", "scatter", "lines", deltaMode),
      applyTrace(t, t.data.time, diffArr(t.data.dz_u, r.dz_u, deltaMode).map((v: number) => v * 1000), "Wheel vel", color, "dot", "scatter", "lines", deltaMode)
    ];
  });
  return [...p,
    optTrace(
      r.time,
      diffArr(r.dz_s, r.dz_s, deltaMode).map((v: number) => v * 1000),
      deltaMode ? "Baseline Vel Ref (0.0 Δ)" : "Body vel ż_s",
      deltaMode ? DELTA_REF_PRIMARY : { color: C.body, width: 2 }
    ),
    optTrace(
      r.time,
      diffArr(r.dz_u, r.dz_u, deltaMode).map((v: number) => v * 1000),
      deltaMode ? "Wheel Vel Ref (0.0 Δ)" : "Wheel vel ż_u",
      deltaMode ? DELTA_REF_SECONDARY : { color: C.wheel, width: 1.5 }
    )
  ];
}

export function bAccel(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => [
    applyTrace(t, t.data.time, diffArr(t.data.ddz_s, r.ddz_s, deltaMode), "Body accel", comparisonColor(idx), "dash", "scatter", "lines", deltaMode)
  ]);
  return [...p,
    optTrace(
      r.time,
      diffArr(r.ddz_s, r.ddz_s, deltaMode),
      deltaMode ? "Baseline Accel Ref (0.0 Δ)" : "Body accel z̈_s",
      deltaMode ? DELTA_REF_PRIMARY : { color: C.accel, width: 2 },
      { fill: deltaMode ? undefined : "tozeroy", fillcolor: "rgba(6, 182, 212, 0.06)" }
    )
  ];
}

export function bTravel(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => {
    const color = comparisonColor(idx);
    return [
      applyTrace(t, t.data.time, diffArr(t.data.susp_travel, r.susp_travel, deltaMode).map((v: number) => v * 1000), "Susp travel", color, "dash", "scatter", "lines", deltaMode),
      applyTrace(t, t.data.time, diffArr(t.data.tire_defl, r.tire_defl, deltaMode).map((v: number) => v * 1000), "Tire defl", color, "dot", "scatter", "lines", deltaMode)
    ];
  });
  return [...p,
    optTrace(
      r.time,
      diffArr(r.susp_travel, r.susp_travel, deltaMode).map((v: number) => v * 1000),
      deltaMode ? "Baseline Travel Ref (0.0 Δ)" : "Susp travel (mm)",
      deltaMode ? DELTA_REF_PRIMARY : { color: C.travel, width: 2 }
    ),
    optTrace(
      r.time,
      diffArr(r.tire_defl, r.tire_defl, deltaMode).map((v: number) => v * 1000),
      deltaMode ? "Tire Defl Ref (0.0 Δ)" : "Tire deflection (mm)",
      deltaMode ? DELTA_REF_SECONDARY : { color: C.tire, width: 1.5 }
    )
  ];
}

// -- TAB 1 --

export function bTrans(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => {
    const color = comparisonColor(idx);
    return [
      applyTrace(t, t.data.freq_hz, diffArr(t.data.transmissibility_body, r.transmissibility_body, deltaMode), "Body |H_s|", color, "dash", "scatter", "lines", deltaMode),
      applyTrace(t, t.data.freq_hz, diffArr(t.data.transmissibility_wheel, r.transmissibility_wheel, deltaMode), "Wheel |H_u|", color, "dot", "scatter", "lines", deltaMode)
    ];
  });
  return [...p,
    optTrace(
      r.freq_hz,
      diffArr(r.transmissibility_body, r.transmissibility_body, deltaMode),
      deltaMode ? "Body TX Ref (0.0 Δ)" : "Body |H_s|",
      deltaMode ? DELTA_REF_PRIMARY : { color: C.body, width: 2 },
      { fill: deltaMode ? undefined : "tozeroy", fillcolor: "rgba(6, 182, 212, 0.06)" }
    ),
    optTrace(
      r.freq_hz,
      diffArr(r.transmissibility_wheel, r.transmissibility_wheel, deltaMode),
      deltaMode ? "Wheel TX Ref (0.0 Δ)" : "Wheel |H_u|",
      deltaMode ? DELTA_REF_SECONDARY : { color: C.wheel, width: 1.5 }
    )
  ];
}

export function bBodeMag(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => [
    applyTrace(t, t.data.freq_hz, diffArr(t.data.bode_magnitude_db, r.bode_magnitude_db, deltaMode), "Mag (dB)", comparisonColor(idx), "dash", "scatter", "lines", deltaMode)
  ]);
  return [...p,
    optTrace(
      r.freq_hz,
      diffArr(r.bode_magnitude_db, r.bode_magnitude_db, deltaMode),
      deltaMode ? "Bode Mag Ref (0.0 Δ)" : "Magnitude (dB)",
      deltaMode ? DELTA_REF_PRIMARY : { color: C.mag, width: 2 }
    )
  ];
}

export function bBodePhase(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => [
    applyTrace(t, t.data.freq_hz, diffArr(t.data.bode_phase_deg, r.bode_phase_deg, deltaMode), "Phase (°)", comparisonColor(idx), "dash", "scatter", "lines", deltaMode)
  ]);
  return [...p,
    optTrace(
      r.freq_hz,
      diffArr(r.bode_phase_deg, r.bode_phase_deg, deltaMode),
      deltaMode ? "Bode Phase Ref (0.0 Δ)" : "Phase (°)",
      deltaMode ? DELTA_REF_PRIMARY : { color: C.phase, width: 2 }
    )
  ];
}

export function bDynLoad(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => [
    applyTrace(t, t.data.time, diffArr(t.data.tire_load_var, r.tire_load_var, deltaMode), "ΔF_z", comparisonColor(idx), "dash", "scatter", "lines", deltaMode)
  ]);
  return [...p,
    {
      x: r.time,
      y: diffArr(r.tire_load_var, r.tire_load_var, deltaMode),
      type: plotType(r.time),
      mode: "lines",
      name: deltaMode ? "Dyn Load Ref (0.0 Δ)" : "Dynamic tire load ΔF_z",
      line: deltaMode ? DELTA_REF_PRIMARY : { color: C.load, width: 2 },
      fill: deltaMode ? undefined : "tozeroy",
      fillcolor: "rgba(6, 182, 212, 0.06)"
    }
  ];
}

// -- TAB 2 --

export function calcForces(r: QuarterCarSeries, p: SpringDamperParams) {
  const kw = p.k_s * p.MR * p.MR;
  const cw = p.c   * p.MR * p.MR;
  const F_spring = r.z_s.map((z: number, i: number) => kw * (z - r.z_u[i]));
  const relVel   = r.dz_s.map((v: number, i: number) => v - r.dz_u[i]);
  const F_damper = relVel.map((v: number) => cw * v);
  const F_total  = F_spring.map((fs: number, i: number) => fs + F_damper[i]);
  const P_c      = F_damper.map((f: number, i: number) => f * relVel[i]);
  return { F_spring, F_damper, F_total, relVel, P_c };
}

export function bForces(r: QuarterCarSeries, p: SpringDamperParams, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const fBase = calcForces(r, p);
  const plt = traces.filter(t => t.visible).flatMap((t, idx) => {
    const { F_total } = calcForces(t.data, t.params as SpringDamperParams);
    return [
      applyTrace(t, t.data.time, diffArr(F_total, fBase.F_total, deltaMode), "Total F", comparisonColor(idx), "dash", "scatter", "lines", deltaMode)
    ];
  });
  return [...plt,
    {
      x: r.time,
      y: diffArr(fBase.F_spring, fBase.F_spring, deltaMode),
      type: plotType(r.time),
      mode: "lines",
      name: deltaMode ? "Spring F Ref (0.0 Δ)" : "Spring F_k",
      line: deltaMode ? DELTA_REF_PRIMARY : { color: C.body, width: 1.5 }
    },
    {
      x: r.time,
      y: diffArr(fBase.F_damper, fBase.F_damper, deltaMode),
      type: plotType(r.time),
      mode: "lines",
      name: deltaMode ? "Damper F Ref (0.0 Δ)" : "Damper F_c",
      line: deltaMode ? DELTA_REF_SECONDARY : { color: C.wheel, width: 1.5 }
    },
    {
      x: r.time,
      y: diffArr(fBase.F_total, fBase.F_total, deltaMode),
      type: plotType(r.time),
      mode: "lines",
      name: deltaMode ? "Total Susp F Ref (0.0 Δ)" : "Total F_susp",
      line: { color: C.total, width: 2, dash: "dot" }
    }
  ];
}

export function bFV(r: QuarterCarSeries, p: SpringDamperParams, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const fBase = calcForces(r, p);
  const plt = traces.filter(t => t.visible).flatMap((t, idx) => {
    const { relVel, F_damper } = calcForces(t.data, t.params as SpringDamperParams);
    return [
      {
        x: relVel.map((v: number) => v * 1000),
        y: diffArr(F_damper, fBase.F_damper, deltaMode),
        type: "scatter",
        mode: "markers",
        name: `${t.name} F-V${deltaMode ? " (Δ vs Base)" : ""}`,
        marker: { color: comparisonColor(idx), size: 2, opacity: 0.6 }
      }
    ];
  });
  return [...plt,
    {
      x: fBase.relVel.map((v: number) => v * 1000),
      y: diffArr(fBase.F_damper, fBase.F_damper, deltaMode),
      type: "scatter",
      mode: "markers",
      name: deltaMode ? "Damper F–V Ref (0.0 Δ)" : "Damper F–V",
      marker: {
        color: fBase.F_damper.map((_: number, i: number) => i / fBase.F_damper.length),
        colorscale: [[0, "#0D1017"], [0.5, PLOT_COLORS.primary], [1, PLOT_COLORS.target]],
        size: 2,
        opacity: 0.8
      }
    }
  ];
}

export function bFx(r: QuarterCarSeries, p: SpringDamperParams, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const fBase = calcForces(r, p);
  const plt = traces.filter(t => t.visible).flatMap((t, idx) => {
    const { F_spring } = calcForces(t.data, t.params as SpringDamperParams);
    return [
      {
        x: t.data.susp_travel.map((v: number) => v * 1000),
        y: diffArr(F_spring, fBase.F_spring, deltaMode),
        type: "scatter",
        mode: "markers",
        name: `${t.name} F-x${deltaMode ? " (Δ vs Base)" : ""}`,
        marker: { color: comparisonColor(idx), size: 2, opacity: 0.6 }
      }
    ];
  });
  return [...plt,
    {
      x: r.susp_travel.map((v: number) => v * 1000),
      y: diffArr(fBase.F_spring, fBase.F_spring, deltaMode),
      type: "scatter",
      mode: "markers",
      name: deltaMode ? "Spring F–x Ref (0.0 Δ)" : "Spring F–x",
      marker: { color: C.body, size: 2, opacity: 0.7 }
    }
  ];
}

export function bPower(r: QuarterCarSeries, p: SpringDamperParams, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const fBase = calcForces(r, p);
  const plt = traces.filter(t => t.visible).flatMap((t, idx) => {
    const { P_c } = calcForces(t.data, t.params as SpringDamperParams);
    return [ applyTrace(t, t.data.time, diffArr(P_c, fBase.P_c, deltaMode), "Power", comparisonColor(idx), "dash", "scatter", "lines", deltaMode) ];
  });
  return [...plt,
    {
      x: r.time,
      y: diffArr(fBase.P_c, fBase.P_c, deltaMode),
      type: plotType(r.time),
      mode: "lines",
      name: deltaMode ? "Damper Power Ref (0.0 Δ)" : "Damper Power P_c",
      line: deltaMode ? DELTA_REF_PRIMARY : { color: C.accel, width: 2 },
      fill: deltaMode ? undefined : "tozeroy",
      fillcolor: "rgba(6, 182, 212, 0.06)"
    }
  ];
}

// -- TAB 3 --

export function bPhaseS(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => [
    applyTrace(t, t.data.z_s.map((v: number) => v * 1000), diffArr(t.data.dz_s, r.dz_s, deltaMode).map((v: number) => v * 1000), "Phase", comparisonColor(idx), "dash", "scatter", "lines", deltaMode)
  ]);
  return [...p,
    { x: r.z_s.map((v: number) => v * 1000), y: diffArr(r.dz_s, r.dz_s, deltaMode).map((v: number) => v * 1000), type: "scatter", mode: "lines", name: "Body phase portrait", line: { color: C.body, width: 1.5 } },
    { x: [r.z_s[0] * 1000], y: [(deltaMode ? 0 : r.dz_s[0]) * 1000], type: "scatter", mode: "markers", name: "Start", marker: { color: C.start, size: 8, symbol: "circle" } }
  ];
}

export function bPhaseU(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => [
    applyTrace(t, t.data.z_u.map((v: number) => v * 1000), diffArr(t.data.dz_u, r.dz_u, deltaMode).map((v: number) => v * 1000), "Phase", comparisonColor(idx), "dash", "scatter", "lines", deltaMode)
  ]);
  return [...p,
    { x: r.z_u.map((v: number) => v * 1000), y: diffArr(r.dz_u, r.dz_u, deltaMode).map((v: number) => v * 1000), type: "scatter", mode: "lines", name: "Wheel phase portrait", line: { color: C.wheel, width: 1.5 } },
    { x: [r.z_u[0] * 1000], y: [(deltaMode ? 0 : r.dz_u[0]) * 1000], type: "scatter", mode: "markers", name: "Start", marker: { color: C.start, size: 8, symbol: "circle" } }
  ];
}

export function bComfortTravel(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => [
    { x: t.data.susp_travel.map((v: number) => v * 1000), y: diffArr(t.data.ddz_s, r.ddz_s, deltaMode), type: "scatter", mode: "markers", name: `${t.name}`, marker: { color: comparisonColor(idx), size: 2, opacity: 0.6 } }
  ]);
  return [...p,
    { x: r.susp_travel.map((v: number) => v * 1000), y: diffArr(r.ddz_s, r.ddz_s, deltaMode), type: "scatter", mode: "markers", name: "Accel vs Travel", marker: { color: C.travel, size: 2, opacity: 0.6 } }
  ];
}

// -- TAB 4 --

export function bPSD(psdData: PsdPayload, traces: Trace[], deltaMode: boolean, r: QuarterCarSeries): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap((t, idx) => {
    if (!t.data.psd_freqs || !t.data.psd_values) return [];
    return [ applyTrace(t, t.data.psd_freqs, diffArr(t.data.psd_values, r.psd_values ?? [], deltaMode), "PSD", comparisonColor(idx), "dash", "scatter", "lines", deltaMode) ];
  });
  return [...p,
    {
      x: psdData.freqs,
      y: diffArr(psdData.psd, r.psd_values ?? [], deltaMode),
      type: plotType(psdData.freqs),
      mode: "lines",
      name: deltaMode ? "PSD Ref (0.0 Δ)" : "PSD ӓ_s",
      fill: deltaMode ? undefined : "tozeroy",
      fillcolor: "rgba(6, 182, 212, 0.06)",
      line: deltaMode ? DELTA_REF_PRIMARY : { color: C.accel, width: 2 }
    }
  ];
}
