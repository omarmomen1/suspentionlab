/**
 * Pure numeric helpers for the V2 instruments. No React, no I/O, so the
 * physics of each instrument can be unit-tested directly.
 */

/** Trapezoid integral of y dx over paired samples. Returns null for fewer than 2 finite points. */
export function trapezoid(x: number[], y: number[]): number | null {
  const n = Math.min(x.length, y.length);
  if (n < 2) return null;
  let s = 0;
  for (let i = 0; i < n - 1; i++) {
    const dx = x[i + 1] - x[i];
    const f = 0.5 * (y[i] + y[i + 1]);
    if (!Number.isFinite(dx) || !Number.isFinite(f)) return null;
    s += f * dx;
  }
  return s;
}

/** Linear interpolation of a monotonic-x table; clamps to the end values. */
export function interp1(xq: number, xs: number[], ys: number[]): number {
  const n = Math.min(xs.length, ys.length);
  if (n === 0) return NaN;
  if (xq <= xs[0]) return ys[0];
  if (xq >= xs[n - 1]) return ys[n - 1];
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] <= xq) lo = mid;
    else hi = mid;
  }
  const t = (xq - xs[lo]) / (xs[hi] - xs[lo]);
  return ys[lo] + t * (ys[hi] - ys[lo]);
}

export interface DamperModel {
  /** Damper coefficient [N s/m] at the damper (shaft). Wheel-referred c is c * MR^2. */
  c: number;
  /** Motion ratio: damper shaft travel / wheel travel. */
  MR: number;
  /** Optional measured/tabulated damper curve: shaft velocity [m/s] vs force [N]. */
  curve_v?: number[] | null;
  curve_f?: number[] | null;
}

export interface WorkLoop {
  /** Shaft displacement [mm] (compression positive: z_s - z_u, scaled by MR). */
  x_mm: number[];
  /** Damper force at the shaft [N]. */
  force_N: number[];
  /** Shaft velocity [m/s]. */
  v_mps: number[];
  /** Closed-contour integral of F dx over the whole trace [J]. Equals dissipated energy. */
  energy_J: number | null;
  /** True when the force came from a tabulated curve rather than the linear c. */
  fromCurve: boolean;
}

/**
 * Force against displacement, so the area enclosed by one closed cycle is the energy
 * dissipated per cycle in joules (oint F dx). Velocity-vs-displacement has no such meaning
 * and is never used. Referred to the damper shaft: x_d = MR x_rel, v_d = MR v_rel,
 * F_d = c v_d (or the tabulated curve). Because F_d dx_d = F_w dx_w, the energy is the
 * same whether referred to the shaft or the wheel.
 */
export function damperWorkLoop(zS: number[], zU: number[], dzS: number[], dzU: number[], model: DamperModel): WorkLoop {
  const n = Math.min(zS.length, zU.length, dzS.length, dzU.length);
  const mr = Number.isFinite(model.MR) && model.MR > 0 ? model.MR : 1;
  const useCurve = Boolean(model.curve_v && model.curve_f && model.curve_v.length >= 2 && model.curve_v.length === model.curve_f.length);
  const x_m: number[] = [];
  const v: number[] = [];
  const F: number[] = [];
  for (let i = 0; i < n; i++) {
    const vd = mr * (dzS[i] - dzU[i]);
    x_m.push(mr * (zS[i] - zU[i]));
    v.push(vd);
    F.push(useCurve ? interp1(vd, model.curve_v as number[], model.curve_f as number[]) : model.c * vd);
  }
  return { x_mm: x_m.map((x) => x * 1000), force_N: F, v_mps: v, energy_J: trapezoid(x_m, F), fromCurve: useCurve };
}

export interface Histogram {
  /** Bin centres [m/s]. */
  centers: number[];
  /** Fraction of samples in each bin (sums to 1 when n > 0). */
  fraction: number[];
  n: number;
}

/** Shaft-speed histogram, symmetric about zero, with `bins` bins spanning +/- max |v|. */
export function shaftSpeedHistogram(v: number[], bins = 24): Histogram {
  const vals = v.filter((x) => Number.isFinite(x));
  const n = vals.length;
  if (n === 0 || bins < 2) return { centers: [], fraction: [], n: 0 };
  const vmax = Math.max(1e-9, ...vals.map((x) => Math.abs(x)));
  const w = (2 * vmax) / bins;
  const counts = new Array<number>(bins).fill(0);
  for (const x of vals) counts[Math.min(bins - 1, Math.max(0, Math.floor((x + vmax) / w)))]++;
  return { centers: counts.map((_, i) => -vmax + (i + 0.5) * w), fraction: counts.map((c) => c / n), n };
}

export interface TravelBudget {
  peak_mm: number;
  limit_mm: number;
  /** Share of the simulated duration with |travel| at or beyond the limit, in percent of SIM DURATION. */
  contact_pct_of_sim_duration: number;
  /** Peak travel as a share of the limit, in percent. */
  peak_pct_of_limit: number;
}

/** Time-weighted travel budget against a travel limit. Duration is the simulation, not a lap. */
export function travelBudget(time: number[], travel_m: number[], limit_mm: number): TravelBudget | null {
  const n = Math.min(time.length, travel_m.length);
  if (n < 2 || !(limit_mm > 0)) return null;
  const lim = limit_mm / 1000;
  let contact = 0;
  let peak = 0;
  for (let i = 0; i < n - 1; i++) {
    const dt = time[i + 1] - time[i];
    if (Math.abs(travel_m[i]) >= lim && Number.isFinite(dt)) contact += dt;
    peak = Math.max(peak, Math.abs(travel_m[i]));
  }
  peak = Math.max(peak, Math.abs(travel_m[n - 1]));
  const total = time[n - 1] - time[0];
  if (!(total > 0)) return null;
  return {
    peak_mm: peak * 1000,
    limit_mm,
    contact_pct_of_sim_duration: (100 * contact) / total,
    peak_pct_of_limit: (100 * peak) / lim,
  };
}

/** Evenly thins an array to at most `max` points (keeps first and last). */
export function thin<T>(a: T[], max: number): T[] {
  if (a.length <= max) return a;
  const out: T[] = [];
  const step = (a.length - 1) / (max - 1);
  for (let i = 0; i < max; i++) out.push(a[Math.round(i * step)]);
  return out;
}

export interface EllipseLimit {
  /** Peak lateral grip [g] (half-axis along lat G). */
  latG: number;
  /** Peak longitudinal accel [g] and brake [g] half-axes. */
  accelG: number;
  brakeG: number;
}

/**
 * Model limit ellipse points in (lat, long) g. Upper half uses the accel half-axis,
 * lower half the brake half-axis. Returns [] if any axis is not a positive finite number,
 * so nothing is drawn rather than guessed.
 */
export function limitEllipse({ latG, accelG, brakeG }: EllipseLimit, steps = 96): { lat: number[]; long: number[] } {
  if (![latG, accelG, brakeG].every((v) => Number.isFinite(v) && v > 0)) return { lat: [], long: [] };
  const lat: number[] = [];
  const long: number[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = (2 * Math.PI * i) / steps;
    const s = Math.sin(t);
    lat.push(latG * Math.cos(t));
    long.push(s >= 0 ? accelG * s : brakeG * s);
  }
  return { lat, long };
}

export interface CornerDelta {
  corner: string;
  delta_s: number;
}

/** Cumulative-delta samples at the given distances, then the delta accrued between corner windows. */
export function cornerDeltasFromCumulative(
  distance_m: number[],
  cumulative_s: number[],
  windows: { corner: string; start_m: number; end_m: number }[],
): CornerDelta[] {
  const out: CornerDelta[] = [];
  for (const w of windows) {
    if (!(w.end_m > w.start_m)) continue;
    const a = interp1(w.start_m, distance_m, cumulative_s);
    const b = interp1(w.end_m, distance_m, cumulative_s);
    if (Number.isFinite(a) && Number.isFinite(b)) out.push({ corner: w.corner, delta_s: b - a });
  }
  return out;
}

/** GT3 front-view motion-ratio target band shown on the Blueprint (Omar's spec: 0.60 to 0.85). */
export const GT3_MOTION_RATIO_BAND: [number, number] = [0.6, 0.85];
