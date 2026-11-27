/**
 * lib/qcarParams.ts — pure quarter-car parameter types, defaults,
 * validation and payload building (P2-ARCH-05: unit-testable, no React).
 *
 * Extracted from hooks/useQuarterCarSimulation.ts so tests can exercise
 * validation/payload logic without importing component trees.
 */

export type IsoClass = "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H";

export type QCarParams = {
  m_s: number; m_u: number; k_s: number; c: number;
  k_t: number; MR: number; c_t: number;
  road_profile: string; amplitude: number; frequency: number;
  duration: number; iso_class: IsoClass; speed_mps: number;
  damper_curve_v: number[] | null; damper_curve_f: number[] | null;
};

export const DEFAULT_QCAR_PARAMS: QCarParams = {
  m_s: 300.0,
  m_u: 35.0,
  k_s: 25000.0,
  c: 2050.0,
  k_t: 200000.0,
  MR: 0.85,
  c_t: 0.0,
  road_profile: "step",
  amplitude: 0.05,
  frequency: 2.0,
  duration: 5.0,
  iso_class: "B",
  speed_mps: 20.0,
  damper_curve_v: null,
  damper_curve_f: null,
};

/** Returns an error message when parameters are physically invalid, else null. */
export function validateQCarParams(params: QCarParams): string | null {
  if (!Number.isFinite(params.m_s) || params.m_s <= 0) return "Sprung Mass must be strictly positive.";
  if (!Number.isFinite(params.m_u) || params.m_u <= 0) return "Unsprung Mass must be strictly positive.";
  if (!Number.isFinite(params.k_s) || params.k_s <= 0) return "Spring Rate (k_s) must be strictly positive (k_s > 0).";
  if (!Number.isFinite(params.c) || params.c <= 0) return "Damping (c) must be strictly positive (c > 0).";
  if (!Number.isFinite(params.k_t) || params.k_t <= 0) return "Tire Stiffness must be strictly positive.";
  if (!Number.isFinite(params.MR) || params.MR <= 0) return "Motion Ratio must be strictly positive.";
  return null;
}

/** Builds the /simulate API request body from quarter-car parameters. */
export function buildQCarPayload(params: QCarParams) {
  return {
    params: {
      m_s: params.m_s, m_u: params.m_u, k_s: params.k_s, c: params.c,
      k_t: params.k_t, MR: params.MR, c_t: params.c_t,
      damper_curve_v: params.damper_curve_v, damper_curve_f: params.damper_curve_f,
    },
    profile: {
      profile_type: params.road_profile,
      amplitude: params.amplitude,
      frequency: params.frequency,
      duration: params.duration,
      iso_class: params.iso_class,
      speed_mps: params.speed_mps,   // ARCH-05: pass ISO 8608 speed to backend
    },
  };
}
