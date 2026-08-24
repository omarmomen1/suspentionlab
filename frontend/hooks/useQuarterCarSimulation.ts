"use client";

/**
 * hooks/useQuarterCarSimulation.ts (P1-ARCH-01)
 * Extracted from quarter-car/page.tsx — simulation domain logic:
 * parameter state, validation, payload building, run + validity fetch,
 * auto-run effect.
 */

import { useState, useEffect } from "react";
import { saveSimulationToHistory } from "../components/SimHistory";
import type { ValidityReport } from "../components/ModelValidity";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type IsoClass = "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H";

export type SimResult =
  | { error: true; message: string; detail?: string }
  | { error?: false; time: number[]; z_s: number[]; z_u: number[]; dz_s: number[]; dz_u: number[]; f_n_s: number; zeta_s: number; [key: string]: any };

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

interface UseQuarterCarSimulationArgs {
  authHeader: () => Record<string, string>;
  showToast: (msg: string, type: "success" | "error") => void;
  autoRun: boolean;
}

export function useQuarterCarSimulation({ authHeader, showToast, autoRun }: UseQuarterCarSimulationArgs) {
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [results, setResults] = useState<SimResult | null>(null);
  const [validity, setValidity] = useState<ValidityReport | null>(null);
  // Snapshot of params used for the LAST successful simulation (MED-07)
  const [simParams, setSimParams] = useState<QCarParams | null>(null);

  const [params, setParams] = useState<QCarParams>(DEFAULT_QCAR_PARAMS);

  const validateParams = (): string | null => {
    if (params.m_s <= 0) return "Sprung Mass must be strictly positive.";
    if (params.m_u <= 0) return "Unsprung Mass must be strictly positive.";
    if (params.k_s <= 0) return "Spring Rate must be strictly positive.";
    if (params.k_t <= 0) return "Tire Stiffness must be strictly positive.";
    if (params.c < 0) return "Damping cannot be negative.";
    return null;
  };

  const buildPayload = () => ({
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
  });

  const runSimulation = async () => {
    const errorMsg = validateParams();
    if (errorMsg) {
      showToast(errorMsg, "error");
      return;
    }
    setIsRunning(true);
    setResults(null);
    try {
      const res = await fetch(`${API_BASE}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (!res.ok) {
        setResults({ error: true, message: data.message ?? data.detail ?? "Simulation failed" });
      } else {
        setResults(data);
        setSimParams({ ...params }); // MED-07: snapshot params at the moment simulation completes
        saveSimulationToHistory("sl_sim_history_qcar", params, data);
        // Issue 16: fetch MODEL VALIDITY alongside every result (non-blocking)
        fetch(`${API_BASE}/api/v1/models/validity`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeader() },
          body: JSON.stringify({
            model: "quarter_car",
            params: buildPayload().params,
          }),
        })
          .then((res) => (res.ok ? res.json() : null))
          .then((v) => setValidity(v))
          .catch(() => setValidity(null));
      }
    } catch (err) {
      setResults({ error: true, message: String(err) });
    } finally {
      setIsRunning(false);
    }
  };

  // Auto-run after parameter changes when enabled
  useEffect(() => {
    if (!autoRun) return;
    if (validateParams()) return;
    const timer = setTimeout(() => {
      runSimulation();
    }, 500);
    return () => clearTimeout(timer);
  }, [params, autoRun]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    isRunning, setIsRunning,
    results, setResults,
    validity,
    simParams,
    params, setParams,
    validateParams,
    buildPayload,
    runSimulation,
  };
}
