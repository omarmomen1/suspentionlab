import type { LedgerRow } from "../../components/v2/instruments/LedgerTable";

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Ledger rows for a quarter-car result. Input rows are marked as user input; solver rows carry the run source. */
export function quarterCarLedgerRows(r: Record<string, any> | null, params: Record<string, any> | null, runStatus: string, source: string): LedgerRow[] {
  if (!r) return [];
  const solver = (id: string, parameter: string, value: unknown, unit: string, decimals = 2): LedgerRow => ({ id, parameter, value: num(value), unit, status: runStatus, source, decimals });
  const input = (id: string, parameter: string, value: unknown, unit: string, decimals = 0): LedgerRow => ({ id, parameter, value: num(value), unit, status: "NOT_RUN", source: "user input", decimals });
  const rmsAccel = r.rms_body_accel_wk ?? r.rms_body_accel;
  return [
    solver("f_n_s", "Sprung natural frequency", r.f_n_s, "Hz"),
    solver("f_n_u", "Unsprung natural frequency", r.f_n_u, "Hz"),
    solver("zeta_s", "Sprung damping ratio ζ", r.zeta_s, "-", 3), // null (overdamped) shows Not available
    solver("peak_tx", "Peak transmissibility", r.peak_transmissibility, "-"),
    solver("rms_accel", "RMS body accel (Wk)", rmsAccel, "m/s²", 3),
    solver("rms_travel", "RMS suspension travel", num(r.rms_susp_travel) === null ? null : (r.rms_susp_travel as number) * 1000, "mm", 1),
    solver("peak_travel", "Peak suspension travel", num(r.peak_susp_travel) === null ? null : (r.peak_susp_travel as number) * 1000, "mm", 1),
    solver("rms_tire", "RMS tire load variation", r.rms_tire_load, "N", 0),
    solver("k_w", "Wheel rate k_w", r.k_w, "N/m", 0),
    input("in_ks", "Spring rate k_s", params?.k_s, "N/m"),
    input("in_c", "Damping c", params?.c, "N s/m"),
    input("in_mr", "Motion ratio MR", params?.MR, "-", 3),
  ];
}

export function fullCarLedgerRows(r: Record<string, any> | null, params: Record<string, any> | null, runStatus: string, source: string): LedgerRow[] {
  if (!r) return [];
  const solver = (id: string, parameter: string, value: unknown, unit: string, decimals = 2): LedgerRow => ({ id, parameter, value: num(value), unit, status: runStatus, source, decimals });
  const input = (id: string, parameter: string, value: unknown, unit: string, decimals = 0): LedgerRow => ({ id, parameter, value: num(value), unit, status: "NOT_RUN", source: "user input", decimals });
  return [
    solver("f_heave", "Heave natural frequency", r.f_n_heave, "Hz"),
    solver("f_roll", "Roll natural frequency", r.f_n_roll, "Hz"),
    solver("f_pitch", "Pitch natural frequency", r.f_n_pitch, "Hz"),
    input("in_ms", "Sprung mass m_s", params?.m_s, "kg"),
    input("in_ksf", "Front spring rate k_sf", params?.k_sf, "N/m"),
    input("in_ksr", "Rear spring rate k_sr", params?.k_sr, "N/m"),
  ];
}

/** Ledger rows for the kinematics solve at one travel step. */
export function kinematicsLedgerRows(result: Record<string, any> | null, idx: number, runStatus: string, source: string): LedgerRow[] {
  if (!result) return [];
  const at = (a: unknown): number | null => (Array.isArray(a) ? num(a[idx]) : null);
  const row = (id: string, parameter: string, arr: unknown, unit: string, decimals = 2): LedgerRow => ({ id, parameter, value: at(arr), unit, status: runStatus, source, decimals });
  return [
    { id: "travel", parameter: "Wheel travel", value: at(result.wheel_travel_mm), unit: "mm", status: runStatus, source, decimals: 1 },
    row("camber", "Camber", result.camber_deg, "deg", 3),
    row("toe", "Toe", result.toe_deg, "deg", 3),
    row("caster", "Caster", result.caster_deg, "deg", 3),
    row("kpi", "Kingpin inclination", result.kpi_deg, "deg", 3),
    row("rc_h", "Roll-centre height", result.roll_center_height_mm, "mm", 1),
    row("mr", "Motion ratio", result.motion_ratio, "-", 3),
    row("scrub", "Scrub radius", result.scrub_radius_mm, "mm", 1),
    row("track", "Track change (ΔY)", result.track_change_mm, "mm", 2),
  ];
}

export function toPinnedPdfRows(rows: LedgerRow[]): { parameter: string; value: string; unit: string; source: string }[] {
  return rows.map((r) => ({
    parameter: r.parameter,
    value: typeof r.value === "number" && Number.isFinite(r.value) ? r.value.toFixed(r.decimals ?? 2) : "Not available",
    unit: r.unit,
    source: r.source,
  }));
}
