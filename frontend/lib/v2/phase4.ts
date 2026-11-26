/**
 * V2 Phase 4 data wiring. Pure functions only, so tests can check the numbers the UI draws.
 * Nothing here invents a value: a missing input gives null.
 */

export interface FullCarSeries {
  time?: number[];
  z_s?: number[];
  theta?: number[];
  phi?: number[];
  z_ufl?: number[];
  z_ufr?: number[];
  z_url?: number[];
  z_urr?: number[];
  z_rfl?: number[];
  z_rfr?: number[];
  z_rrl?: number[];
  z_rrr?: number[];
  [k: string]: unknown;
}

export interface FullCarLoadParams {
  m_s: number;
  m_uf: number;
  m_ur: number;
  a: number;
  b: number;
  k_tf: number;
  k_tr: number;
}

export interface CornerLoads {
  index: number;
  time_s: number | null;
  staticFrontN: number;
  staticRearN: number;
  fl: number;
  fr: number;
  rl: number;
  rr: number;
  /** Left minus right, per axle [N]. */
  frontLeftMinusRightN: number;
  rearLeftMinusRightN: number;
  /** Corners whose tire load is clamped at 0 (contact lost). */
  liftedCorners: Array<"fl" | "fr" | "rl" | "rr">;
}

const G = 9.81;
const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/**
 * Static axle-corner loads and dynamic tire load, using the same formula as
 * run_full_car_analysis (physics/full_car.py): Fz = max(0, F_static + k_t (z_road - z_unsprung)).
 * The solver does not return Fz as a time series, so the series is rebuilt here from the
 * returned z_u / z_r channels. Tire damping is not part of that formula.
 */
export function cornerLoadsAt(res: FullCarSeries | null | undefined, p: FullCarLoadParams, index: number): CornerLoads | null {
  if (!res) return null;
  const need = ["z_ufl", "z_ufr", "z_url", "z_urr", "z_rfl", "z_rfr", "z_rrl", "z_rrr"] as const;
  for (const k of need) {
    const arr = res[k] as number[] | undefined;
    if (!Array.isArray(arr) || index < 0 || index >= arr.length || !num(arr[index])) return null;
  }
  for (const v of [p.m_s, p.m_uf, p.m_ur, p.a, p.b, p.k_tf, p.k_tr]) if (!num(v)) return null;
  const L = p.a + p.b;
  const staticF = L > 1e-4 ? (p.m_s * (p.b / (2 * L)) + p.m_uf) * G : (0.25 * p.m_s + p.m_uf) * G;
  const staticR = L > 1e-4 ? (p.m_s * (p.a / (2 * L)) + p.m_ur) * G : (0.25 * p.m_s + p.m_ur) * G;
  const f = (st: number, kt: number, zr: string, zu: string) =>
    Math.max(0, st + kt * ((res[zr] as number[])[index] - (res[zu] as number[])[index]));
  const fl = f(staticF, p.k_tf, "z_rfl", "z_ufl");
  const fr = f(staticF, p.k_tf, "z_rfr", "z_ufr");
  const rl = f(staticR, p.k_tr, "z_rrl", "z_url");
  const rr = f(staticR, p.k_tr, "z_rrr", "z_urr");
  const lifted: CornerLoads["liftedCorners"] = [];
  if (fl === 0) lifted.push("fl");
  if (fr === 0) lifted.push("fr");
  if (rl === 0) lifted.push("rl");
  if (rr === 0) lifted.push("rr");
  return {
    index,
    time_s: Array.isArray(res.time) && num(res.time[index]) ? res.time[index] : null,
    staticFrontN: staticF,
    staticRearN: staticR,
    fl, fr, rl, rr,
    frontLeftMinusRightN: fl - fr,
    rearLeftMinusRightN: rl - rr,
    liftedCorners: lifted,
  };
}

/** Largest tire load over the whole series, used as the common bar scale. */
export function maxCornerLoadN(res: FullCarSeries | null | undefined, p: FullCarLoadParams): number | null {
  const n = Array.isArray(res?.z_ufl) ? (res!.z_ufl as number[]).length : 0;
  let best: number | null = null;
  for (let i = 0; i < n; i++) {
    const c = cornerLoadsAt(res, p, i);
    if (!c) continue;
    const m = Math.max(c.fl, c.fr, c.rl, c.rr);
    if (best === null || m > best) best = m;
  }
  return best;
}

export interface Attitude {
  index: number;
  heave_mm: number;
  roll_deg: number;
  pitch_deg: number;
}

/** Body heave [m -> mm], roll and pitch [rad -> deg] straight from the 7-DOF series. */
export function attitudeAt(res: FullCarSeries | null | undefined, index: number): Attitude | null {
  if (!res || !Array.isArray(res.z_s) || !Array.isArray(res.theta) || !Array.isArray(res.phi)) return null;
  const z = res.z_s[index], th = res.theta[index], ph = res.phi[index];
  if (!num(z) || !num(th) || !num(ph)) return null;
  return { index, heave_mm: z * 1000, roll_deg: (ph * 180) / Math.PI, pitch_deg: (th * 180) / Math.PI };
}

export const ATTITUDE_EXAGGERATION = 10;

/** Rendered pose = true pose x10. The true numbers stay in the overlay. */
export function exaggeratedPose(a: Attitude) {
  return {
    heave_mm: a.heave_mm * ATTITUDE_EXAGGERATION,
    roll_deg: a.roll_deg * ATTITUDE_EXAGGERATION,
    pitch_deg: a.pitch_deg * ATTITUDE_EXAGGERATION,
  };
}

// ── Motion-ratio field ───────────────────────────────────────────────────────
export interface SteerGridResponse {
  bump_mm: number[];
  rack_travel_mm: number[];
  converged: boolean[][];
  motion_ratio: (number | null)[][];
  steer_angle_deg: (number | null)[][];
  clearances?: { status?: string; reason?: string };
  ackermann?: { status?: string; reason?: string; [k: string]: unknown };
  solver?: string;
}

export interface MrCell {
  row: number; // rack index
  col: number; // bump index
  bump_mm: number;
  rack_mm: number;
  mr: number | null;
  steer_deg: number | null;
  reachable: boolean;
}

export function mrFieldCells(g: SteerGridResponse): { cells: MrCell[]; min: number | null; max: number | null; unreachable: number } {
  const cells: MrCell[] = [];
  let min: number | null = null, max: number | null = null, unreachable = 0;
  g.rack_travel_mm.forEach((rack, row) => {
    g.bump_mm.forEach((bump, col) => {
      const mr = g.motion_ratio?.[row]?.[col];
      const ok = num(mr) && g.converged?.[row]?.[col] !== false;
      const steer = g.steer_angle_deg?.[row]?.[col];
      if (ok) {
        min = min === null ? (mr as number) : Math.min(min, mr as number);
        max = max === null ? (mr as number) : Math.max(max, mr as number);
      } else unreachable++;
      cells.push({ row, col, bump_mm: bump, rack_mm: rack, mr: ok ? (mr as number) : null, steer_deg: ok && num(steer) ? steer : null, reachable: ok });
    });
  });
  return { cells, min, max, unreachable };
}

// ── Why Chain ────────────────────────────────────────────────────────────────
export interface WhyChainLink {
  link: string;
  status: string;
  value: any;
  unit: string | null;
  solver_source: string | null;
  reason_code?: string | null;
  lever?: string | null;
}
export interface WhyChainResponse {
  track?: string;
  chain: WhyChainLink[];
  chain_complete: boolean;
}

/** UI setup keys -> backend lever names, with the unit factor (UI N/mm -> backend N/m). */
const LEVER_MAP: Array<{ ui: string; lever: string; factor: number }> = [
  { ui: "front_arb", lever: "k_arb_front_n_m", factor: 1000 },
  { ui: "rear_arb", lever: "k_arb_rear_n_m", factor: 1000 },
  { ui: "front_spring_rate", lever: "k_spring_front_n_m", factor: 1000 },
  { ui: "rear_spring_rate", lever: "k_spring_rear_n_m", factor: 1000 },
  { ui: "static_rh_front_mm", lever: "static_rh_front_mm", factor: 1 },
  { ui: "static_rh_rear_mm", lever: "static_rh_rear_mm", factor: 1 },
];

/** Only levers the two setups really differ in; nothing else is sent. */
export function whyChainLevers(a: Record<string, any> | null | undefined, b: Record<string, any> | null | undefined) {
  const setup_a: Record<string, number> = {};
  const setup_b: Record<string, number> = {};
  if (!a || !b) return { setup_a, setup_b, changed: [] as string[] };
  const changed: string[] = [];
  for (const m of LEVER_MAP) {
    const va = a[m.ui], vb = b[m.ui];
    if (num(va) && num(vb) && va !== vb) {
      setup_a[m.lever] = va * m.factor;
      setup_b[m.lever] = vb * m.factor;
      changed.push(m.lever);
    }
  }
  return { setup_a, setup_b, changed };
}

export interface ChainRow {
  link: string;
  status: string;
  unit: string | null;
  source: string | null;
  reason: string | null;
  /** Flattened numeric leaves: path -> number. */
  numbers: Array<{ path: string; value: number }>;
}

export function whyChainRows(res: WhyChainResponse): ChainRow[] {
  const flat = (o: any, prefix: string, out: Array<{ path: string; value: number }>) => {
    if (num(o)) out.push({ path: prefix, value: o });
    else if (o && typeof o === "object") for (const k of Object.keys(o)) flat(o[k], prefix ? `${prefix}.${k}` : k, out);
  };
  return res.chain.map((l) => {
    const numbers: Array<{ path: string; value: number }> = [];
    if (l.status !== "NOT_MODELED") flat(l.value, "", numbers);
    return { link: l.link, status: l.status, unit: l.unit ?? null, source: l.solver_source ?? null, reason: l.reason_code ?? null, numbers };
  });
}
