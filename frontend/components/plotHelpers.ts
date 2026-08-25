/**
 * Typed plot builders for the quarter-car workspace.
 *
 * Every simulation result crossing the backend→frontend boundary conforms to
 * `QuarterCarSeries`; parameters conform to `SpringDamperParams`. These
 * contracts mean a backend field rename is now a COMPILE ERROR here instead
 * of an empty chart at runtime.
 */
import { Trace } from "./TraceManager";

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
  body: "#f2a900", // yellow
  wheel: "#00aeff", // blue
  road: "#333", // dark gray
  accel: "#ff2d55", // red
  travel: "#bf5af2", // purple
  tire: "#64d2ff", // light blue
  load: "#ff6b35", // orange
  mag: "#00ff87", // green
  phase: "#ff9f0a", // orange/yellow
};

function applyTrace(t: Trace, x: number[], y: number[], name: string, color?: string, dash?: string, type = "scatter", mode = "lines"): PlotTrace {
  return { x, y, type, mode, name: `${t.name} ${name}`, line: { color: color || t.color, width: 1.5, dash: dash || "dash" }, opacity: 0.7 };
}

const diffArr = (arr: number[], baseArr: number[], deltaMode: boolean) => {
  if (!deltaMode || !baseArr || !arr || arr.length !== baseArr.length) return arr;
  return arr.map((v, i) => v - baseArr[i]);
};

// -- TAB 0 --

export function bDisp(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    applyTrace(t, t.data.time, diffArr(t.data.z_s, r.z_s, deltaMode).map((v:number)=>v*1000), "Body", t.color, "dash"),
    applyTrace(t, t.data.time, diffArr(t.data.z_u, r.z_u, deltaMode).map((v:number)=>v*1000), "Wheel", t.color, "dot")
  ]);
  return [...p,
    { x: r.time, y: diffArr(r.z_s, r.z_s, deltaMode).map((v:number)=>v*1000), type: "scatter", mode: "lines", name: "Body z_s", line: { color: C.body, width: 2 } },
    { x: r.time, y: diffArr(r.z_u, r.z_u, deltaMode).map((v:number)=>v*1000), type: "scatter", mode: "lines", name: "Wheel z_u", line: { color: C.wheel, width: 1.5 } },
    { x: r.time, y: diffArr(r.z_r, r.z_r, deltaMode).map((v:number)=>v*1000), type: "scatter", mode: "lines", name: "Road z_r", line: { color: C.road, width: 1, dash: "dash" } }
  ];
}

export function bVel(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    applyTrace(t, t.data.time, diffArr(t.data.dz_s, r.dz_s, deltaMode).map((v:number)=>v*1000), "Body vel", t.color, "dash"),
    applyTrace(t, t.data.time, diffArr(t.data.dz_u, r.dz_u, deltaMode).map((v:number)=>v*1000), "Wheel vel", t.color, "dot")
  ]);
  return [...p,
    { x: r.time, y: diffArr(r.dz_s, r.dz_s, deltaMode).map((v:number)=>v*1000), type: "scatter", mode: "lines", name: "Body vel ż_s", line: { color: C.body, width: 2 } },
    { x: r.time, y: diffArr(r.dz_u, r.dz_u, deltaMode).map((v:number)=>v*1000), type: "scatter", mode: "lines", name: "Wheel vel ż_u", line: { color: C.wheel, width: 1.5 } }
  ];
}

export function bAccel(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    applyTrace(t, t.data.time, diffArr(t.data.ddz_s, r.ddz_s, deltaMode), "Body accel", t.color, "dash")
  ]);
  return [...p,
    { x: r.time, y: diffArr(r.ddz_s, r.ddz_s, deltaMode), type: "scatter", mode: "lines", name: "Body accel z̈_s", line: { color: C.accel, width: 2 }, fill: "tozeroy", fillcolor: "rgba(255,45,85,0.04)" }
  ];
}

export function bTravel(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    applyTrace(t, t.data.time, diffArr(t.data.susp_travel, r.susp_travel, deltaMode).map((v:number)=>v*1000), "Susp travel", t.color, "dash"),
    applyTrace(t, t.data.time, diffArr(t.data.tire_defl, r.tire_defl, deltaMode).map((v:number)=>v*1000), "Tire defl", t.color, "dot")
  ]);
  return [...p,
    { x: r.time, y: diffArr(r.susp_travel, r.susp_travel, deltaMode).map((v:number)=>v*1000), type: "scatter", mode: "lines", name: "Susp travel (mm)", line: { color: C.travel, width: 2 } },
    { x: r.time, y: diffArr(r.tire_defl, r.tire_defl, deltaMode).map((v:number)=>v*1000), type: "scatter", mode: "lines", name: "Tire deflection (mm)", line: { color: C.tire, width: 1.5 } }
  ];
}

// -- TAB 1 --

export function bTrans(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    applyTrace(t, t.data.freq_hz, diffArr(t.data.transmissibility_body, r.transmissibility_body, deltaMode), "Body |H_s|", t.color, "dash"),
    applyTrace(t, t.data.freq_hz, diffArr(t.data.transmissibility_wheel, r.transmissibility_wheel, deltaMode), "Wheel |H_u|", t.color, "dot")
  ]);
  return [...p,
    { x: r.freq_hz, y: diffArr(r.transmissibility_body, r.transmissibility_body, deltaMode), type: "scatter", mode: "lines", name: "Body |H_s|", line: { color: C.body, width: 2 }, fill: "tozeroy", fillcolor: "rgba(242,169,0,0.04)" },
    { x: r.freq_hz, y: diffArr(r.transmissibility_wheel, r.transmissibility_wheel, deltaMode), type: "scatter", mode: "lines", name: "Wheel |H_u|", line: { color: C.wheel, width: 1.5 } }
  ];
}

export function bBodeMag(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    applyTrace(t, t.data.freq_hz, diffArr(t.data.bode_magnitude_db, r.bode_magnitude_db, deltaMode), "Mag (dB)", t.color, "dash")
  ]);
  return [...p,
    { x: r.freq_hz, y: diffArr(r.bode_magnitude_db, r.bode_magnitude_db, deltaMode), type: "scatter", mode: "lines", name: "Magnitude (dB)", line: { color: C.mag, width: 2 } }
  ];
}

export function bBodePhase(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    applyTrace(t, t.data.freq_hz, diffArr(t.data.bode_phase_deg, r.bode_phase_deg, deltaMode), "Phase (°)", t.color, "dash")
  ]);
  return [...p,
    { x: r.freq_hz, y: diffArr(r.bode_phase_deg, r.bode_phase_deg, deltaMode), type: "scatter", mode: "lines", name: "Phase (°)", line: { color: C.phase, width: 2 } }
  ];
}

export function bDynLoad(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    applyTrace(t, t.data.time, diffArr(t.data.tire_load_var, r.tire_load_var, deltaMode), "ΔF_z", t.color, "dash")
  ]);
  return [...p,
    { x: r.time, y: diffArr(r.tire_load_var, r.tire_load_var, deltaMode), type: "scatter", mode: "lines", name: "Dynamic tire load ΔF_z", line: { color: C.load, width: 2 }, fill: "tozeroy", fillcolor: "rgba(255,107,53,0.05)" }
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
  const plt = traces.filter(t => t.visible).flatMap(t => {
    const { F_total } = calcForces(t.data, t.params as SpringDamperParams);
    return [
      applyTrace(t, t.data.time, diffArr(F_total, fBase.F_total, deltaMode), "Total F", t.color, "dash")
    ];
  });
  return [...plt,
    { x: r.time, y: diffArr(fBase.F_spring, fBase.F_spring, deltaMode), type: "scatter", mode: "lines", name: "Spring F_k", line: { color: C.body, width: 1.5 } },
    { x: r.time, y: diffArr(fBase.F_damper, fBase.F_damper, deltaMode), type: "scatter", mode: "lines", name: "Damper F_c", line: { color: C.wheel, width: 1.5 } },
    { x: r.time, y: diffArr(fBase.F_total, fBase.F_total, deltaMode), type: "scatter", mode: "lines", name: "Total F_susp", line: { color: "#fff", width: 2, dash: "dot" } }
  ];
}

export function bFV(r: QuarterCarSeries, p: SpringDamperParams, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const fBase = calcForces(r, p);
  const plt = traces.filter(t => t.visible).flatMap(t => {
    const { relVel, F_damper } = calcForces(t.data, t.params as SpringDamperParams);
    return [
      { x: relVel.map((v:number)=>v*1000), y: diffArr(F_damper, fBase.F_damper, deltaMode), type: "scatter", mode: "markers", name: `${t.name} F-V`, marker: { color: t.color, size: 2, opacity: 0.6 } }
    ];
  });
  return [...plt,
    { x: fBase.relVel.map((v:number)=>v*1000), y: diffArr(fBase.F_damper, fBase.F_damper, deltaMode), type: "scatter", mode: "markers", name: "Damper F–V", marker: { color: fBase.F_damper.map((_:number, i:number) => i / fBase.F_damper.length), colorscale: [[0, "#0a1628"], [0.5, "#00aeff"], [1, "#f2a900"]], size: 2, opacity: 0.8 } }
  ];
}

export function bFx(r: QuarterCarSeries, p: SpringDamperParams, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const fBase = calcForces(r, p);
  const plt = traces.filter(t => t.visible).flatMap(t => {
    const { F_spring } = calcForces(t.data, t.params as SpringDamperParams);
    return [
      { x: t.data.susp_travel.map((v:number)=>v*1000), y: diffArr(F_spring, fBase.F_spring, deltaMode), type: "scatter", mode: "markers", name: `${t.name} F-x`, marker: { color: t.color, size: 2, opacity: 0.6 } }
    ];
  });
  return [...plt,
    { x: r.susp_travel.map((v:number)=>v*1000), y: diffArr(fBase.F_spring, fBase.F_spring, deltaMode), type: "scatter", mode: "markers", name: "Spring F–x", marker: { color: C.body, size: 2, opacity: 0.7 } }
  ];
}

export function bPower(r: QuarterCarSeries, p: SpringDamperParams, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const fBase = calcForces(r, p);
  const plt = traces.filter(t => t.visible).flatMap(t => {
    const { P_c } = calcForces(t.data, t.params as SpringDamperParams);
    return [ applyTrace(t, t.data.time, diffArr(P_c, fBase.P_c, deltaMode), "Power", t.color, "dash") ];
  });
  return [...plt,
    { x: r.time, y: diffArr(fBase.P_c, fBase.P_c, deltaMode), type: "scatter", mode: "lines", name: "Damper Power P_c", line: { color: C.accel, width: 2 }, fill: "tozeroy", fillcolor: "rgba(255,45,85,0.05)" }
  ];
}

// -- TAB 3 --

export function bPhaseS(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    applyTrace(t, t.data.z_s.map((v:number)=>v*1000), diffArr(t.data.dz_s, r.dz_s, deltaMode).map((v:number)=>v*1000), "Phase", t.color, "dash")
  ]);
  return [...p,
    { x: r.z_s.map((v:number)=>v*1000), y: diffArr(r.dz_s, r.dz_s, deltaMode).map((v:number)=>v*1000), type: "scatter", mode: "lines", name: "Body phase portrait", line: { color: C.body, width: 1.5 } },
    { x: [r.z_s[0]*1000], y: [(deltaMode ? 0 : r.dz_s[0])*1000], type: "scatter", mode: "markers", name: "Start", marker: { color: C.mag, size: 8, symbol: "circle" } }
  ];
}

export function bPhaseU(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    applyTrace(t, t.data.z_u.map((v:number)=>v*1000), diffArr(t.data.dz_u, r.dz_u, deltaMode).map((v:number)=>v*1000), "Phase", t.color, "dash")
  ]);
  return [...p,
    { x: r.z_u.map((v:number)=>v*1000), y: diffArr(r.dz_u, r.dz_u, deltaMode).map((v:number)=>v*1000), type: "scatter", mode: "lines", name: "Wheel phase portrait", line: { color: C.wheel, width: 1.5 } },
    { x: [r.z_u[0]*1000], y: [(deltaMode ? 0 : r.dz_u[0])*1000], type: "scatter", mode: "markers", name: "Start", marker: { color: C.mag, size: 8, symbol: "circle" } }
  ];
}

export function bComfortTravel(r: QuarterCarSeries, traces: Trace[], deltaMode: boolean): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => [
    { x: t.data.susp_travel.map((v:number)=>v*1000), y: diffArr(t.data.ddz_s, r.ddz_s, deltaMode), type: "scatter", mode: "markers", name: `${t.name}`, marker: { color: t.color, size: 2, opacity: 0.6 } }
  ]);
  return [...p,
    { x: r.susp_travel.map((v:number)=>v*1000), y: diffArr(r.ddz_s, r.ddz_s, deltaMode), type: "scatter", mode: "markers", name: "Accel vs Travel", marker: { color: C.travel, size: 2, opacity: 0.6 } }
  ];
}

// -- TAB 4 --

export function bPSD(psdData: PsdPayload, traces: Trace[], deltaMode: boolean, r: QuarterCarSeries): PlotTrace[] {
  const p = traces.filter(t => t.visible).flatMap(t => {
    if (!t.data.psd_freqs || !t.data.psd_values) return [];
    return [ applyTrace(t, t.data.psd_freqs, diffArr(t.data.psd_values, r.psd_values ?? [], deltaMode), "PSD", t.color, "dash") ];
  });
  return [...p,
    { x: psdData.freqs, y: diffArr(psdData.psd, r.psd_values ?? [], deltaMode), type: "scatter", mode: "lines", name: "PSD ӓ_s", fill: "tozeroy", fillcolor: "rgba(255,45,85,0.06)", line: { color: C.accel, width: 2 } }
  ];
}
