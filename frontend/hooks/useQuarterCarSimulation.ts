"use client";

/**
 * hooks/useQuarterCarSimulation.ts (P1-ARCH-01)
 * Extracted from quarter-car/page.tsx — simulation domain logic:
 * parameter state, validation, payload building, run + validity fetch,
 * auto-run effect.
 */

import { useState, useEffect, useRef } from "react";
import { saveSimulationToHistory } from "../components/SimHistory";
import type { ValidityReport } from "../components/ModelValidity";
import { apiFetch } from "../lib/api";

import {
  DEFAULT_QCAR_PARAMS,
  validateQCarParams,
  buildQCarPayload,
  type QCarParams,
  type IsoClass,
} from "../lib/qcarParams";

export type SimulationLoadingStage =
  | "VALIDATING"
  | "DISPATCHING"
  | "SOLVING_ODE"
  | "COMPUTING_PSD"
  | "EVALUATING_KPIS"
  | null;

export type SimResult =
  | { error: true; message: string; detail?: string }
  | { error?: false; time: number[]; z_s: number[]; z_u: number[]; dz_s: number[]; dz_u: number[]; f_n_s: number; zeta_s: number; [key: string]: any };

// Re-export for existing consumers
export { DEFAULT_QCAR_PARAMS };
export type { QCarParams, IsoClass };

interface UseQuarterCarSimulationArgs {
  authHeader: () => Record<string, string>;
  showToast: (msg: string, type: "success" | "error" | "info") => void;
  autoRun: boolean;
}

export function useQuarterCarSimulation({ authHeader, showToast, autoRun }: UseQuarterCarSimulationArgs) {
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [loadingStage, setLoadingStage] = useState<SimulationLoadingStage>(null);
  const [results, setResults] = useState<SimResult | null>(null);
  const [lastValidResult, setLastValidResult] = useState<SimResult | null>(null);
  const [simError, setSimError] = useState<string | null>(null);
  const [validity, setValidity] = useState<ValidityReport | null>(null);
  const [retryCount, setRetryCount] = useState<number>(0);
  // Snapshot of params used for the LAST successful simulation (MED-07)
  const [simParams, setSimParams] = useState<QCarParams | null>(null);

  const [params, setParams] = useState<QCarParams>(DEFAULT_QCAR_PARAMS);

  const abortControllerRef = useRef<AbortController | null>(null);

  const validateParams = (): string | null => validateQCarParams(params);
  const buildPayload = () => buildQCarPayload(params);

  const cancelSimulation = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsRunning(false);
    setLoadingStage(null);
    showToast("Simulation cancelled by user.", "info");
  };

  const runSimulation = async (isRetry = false) => {
    const errorMsg = validateParams();
    if (errorMsg) {
      showToast(errorMsg, "error");
      return;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsRunning(true);
    setLoadingStage("VALIDATING");
    setSimError(null);
    if (isRetry) {
      setRetryCount((prev) => prev + 1);
    } else {
      setRetryCount(0);
    }

    try {
      setLoadingStage("DISPATCHING");
      const res = await apiFetch("/api/v1/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
        signal: controller.signal,
      });
      const data = await res.json();
      if (!res.ok) {
        const msg = data.message ?? data.detail ?? "Simulation failed";
        setSimError(msg);
        showToast(msg, "error");
        setLoadingStage(null);
        return;
      }

      const onSimulationSuccess = (simResult: any) => {
        setLoadingStage("EVALUATING_KPIS");
        setResults(simResult);
        setLastValidResult(simResult);
        setSimError(null);
        setSimParams({ ...params });
        saveSimulationToHistory("sl_sim_history_qcar", params, simResult);
        apiFetch("/api/v1/models/validity", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: "quarter_car",
            params: buildPayload().params,
          }),
          signal: controller.signal,
        })
          .then((res) => (res.ok ? res.json() : null))
          .then((v) => setValidity(v))
          .catch(() => setValidity(null))
          .finally(() => setLoadingStage(null));
      };

      if (data.job_id) {
        const jobId = data.job_id;
        const startTime = Date.now();
        setLoadingStage("SOLVING_ODE");
        while (Date.now() - startTime < 20000) {
          if (controller.signal.aborted) return;
          await new Promise((r) => setTimeout(r, 200));
          if (Date.now() - startTime > 3000 && loadingStage !== "COMPUTING_PSD") {
            setLoadingStage("COMPUTING_PSD");
          }
          try {
            const pollRes = await apiFetch(`/api/v1/jobs/${jobId}`, {
              signal: controller.signal,
            });
            if (pollRes.ok) {
              const pollData = await pollRes.json();
              const isSuccess =
                (pollData.status === "COMPLETED" ||
                  pollData.status === "COMPLETED_WITH_WARNINGS" ||
                  pollData.status === "COMPLETED_VALID") &&
                pollData.result;
              if (isSuccess) {
                onSimulationSuccess(pollData.result);
                return;
              } else if (
                pollData.status === "FAILED" ||
                pollData.status === "FAILED_NUMERICAL" ||
                pollData.status === "FAILED_INPUT" ||
                pollData.status === "CANCELED"
              ) {
                const msg = pollData.error || "Simulation failed.";
                setSimError(msg);
                showToast(msg, "error");
                setLoadingStage(null);
                return;
              }
            }
          } catch (e: any) {
            if (e.name === "AbortError") return;
            // retry on network jitter
          }
        }
        setSimError("Simulation timed out.");
        showToast("Simulation timed out.", "error");
        setLoadingStage(null);
      } else {
        onSimulationSuccess(data);
      }
    } catch (err: any) {
      if (err.name === "AbortError") {
        return;
      }
      const msg = String(err);
      setSimError(msg);
      showToast(msg, "error");
      setLoadingStage(null);
    } finally {
      setIsRunning(false);
    }
  };

  const retrySimulation = () => {
    runSimulation(true);
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
    loadingStage,
    cancelSimulation,
    retrySimulation,
    retryCount,
    results: results || (lastValidResult ? { ...lastValidResult, isHistorical: true } : null),
    lastValidResult,
    simError,
    setSimError,
    setResults,
    validity,
    simParams,
    params, setParams,
    validateParams,
    buildPayload,
    runSimulation,
  };
}
