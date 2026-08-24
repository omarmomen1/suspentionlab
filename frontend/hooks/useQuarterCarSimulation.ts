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

import {
  DEFAULT_QCAR_PARAMS,
  validateQCarParams,
  buildQCarPayload,
  type QCarParams,
  type IsoClass,
} from "../lib/qcarParams";

export type SimResult =
  | { error: true; message: string; detail?: string }
  | { error?: false; time: number[]; z_s: number[]; z_u: number[]; dz_s: number[]; dz_u: number[]; f_n_s: number; zeta_s: number; [key: string]: any };

// Re-export for existing consumers
export { DEFAULT_QCAR_PARAMS };
export type { QCarParams, IsoClass };

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

  const validateParams = (): string | null => validateQCarParams(params);
  const buildPayload = () => buildQCarPayload(params);

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
