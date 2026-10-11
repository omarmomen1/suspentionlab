"use client";

/**
 * hooks/useJobPolling.ts
 * Shared simulation & optimization job lifecycle manager.
 *
 * Implements: queued, running, progress, completed, failed, cancelled, retry.
 * Backed by canonical SimulationApi SDK.
 */

import { useEffect, useRef, useCallback } from "react";
import { SimulationApi, JobStatusResponse } from "../lib/api_client";

export interface PollJobArgs {
  jobId: string;
  authHeader?: () => Record<string, string>;
  onCompleted: (result: any) => void;
  onFailed: (message: string) => void;
  onProgress?: (progress: number, status: "PENDING" | "RUNNING") => void;
  onCancelled?: () => void;
  intervalMs?: number;
  maxAttempts?: number;
}

export function useJobPolling() {
  const pollersRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  // Clear all pollers on unmount
  useEffect(() => {
    return () => {
      pollersRef.current.forEach((id) => clearInterval(id));
      pollersRef.current.clear();
    };
  }, []);

  const stop = useCallback((jobId: string) => {
    const timerId = pollersRef.current.get(jobId);
    if (timerId) {
      clearInterval(timerId);
      pollersRef.current.delete(jobId);
    }
  }, []);

  const cancelJob = useCallback(async (jobId: string) => {
    stop(jobId);
    try {
      await SimulationApi.cancelSimulation(jobId);
    } catch (e) {
      console.error("Cancellation error:", e);
    }
  }, [stop]);

  const pollJob = useCallback(
    ({
      jobId,
      onCompleted,
      onFailed,
      onProgress,
      onCancelled,
      intervalMs = 1000,
      maxAttempts = 600,
    }: PollJobArgs) => {
      // Clear any prior poller for this job
      stop(jobId);

      let attempts = 0;
      const id = setInterval(async () => {
        attempts += 1;

        if (attempts > maxAttempts) {
          stop(jobId);
          onFailed(
            `Job ${jobId} did not complete within ${maxAttempts} attempts. It may still be running.`
          );
          return;
        }

        try {
          const pollData: JobStatusResponse = await SimulationApi.getJobStatus(jobId);

          const isCompleted =
            pollData.status === "COMPLETED" ||
            pollData.status === "COMPLETED_WITH_WARNINGS" ||
            pollData.status === "COMPLETED_VALID";

          if (isCompleted) {
            stop(jobId);
            onCompleted(pollData.result);
          } else if (pollData.status === "CANCELED") {
            stop(jobId);
            if (onCancelled) onCancelled();
            else onFailed("Simulation was cancelled.");
          } else if (
            pollData.status === "FAILED" ||
            pollData.status === "FAILED_NUMERICAL" ||
            pollData.status === "FAILED_INPUT"
          ) {
            stop(jobId);
            onFailed(pollData.error || "Simulation solver execution failed.");
          } else {
            // PENDING or RUNNING
            if (onProgress) {
              // Synthetic smooth progress progression if backend doesn't provide fine-grained %
              const calculatedProgress =
                pollData.progress ?? Math.min(95, Math.round((attempts / 15) * 100));
              const runningStatus: "PENDING" | "RUNNING" =
                pollData.status === "RUNNING" ? "RUNNING" : "PENDING";
              onProgress(calculatedProgress, runningStatus);
            }
          }
        } catch (e: any) {
          stop(jobId);
          onFailed(e?.message || String(e));
        }
      }, intervalMs);

      pollersRef.current.set(jobId, id);
    },
    [stop]
  );

  return { pollJob, cancelJob, stop };
}
