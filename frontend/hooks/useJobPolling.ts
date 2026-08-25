"use client";

/**
 * hooks/useJobPolling.ts (P1-ARCH-02)
 * Shared job-status polling with automatic unmount cleanup.
 *
 * Previously duplicated as raw setInterval blocks in half-car, full-car,
 * and sensitivity pages — each of which leaked the interval if the user
 * navigated away before the job finished (P1-PERF-04).
 */

import { useEffect, useRef, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface PollJobArgs {
  jobId: string;
  authHeader: () => Record<string, string>;
  /** Called with the job result when status === COMPLETED. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onCompleted: (result: any) => void;
  /** Called with an error message when the job fails or polling errors. */
  onFailed: (message: string) => void;
  intervalMs?: number;
  /** Hard ceiling: stop polling and fail after this many attempts (default 600 ≈ 10 min at 1 s). */
  maxAttempts?: number;
}

export function useJobPolling() {
  const pollersRef = useRef<Set<ReturnType<typeof setInterval>>>(new Set());

  // Clear any still-active pollers on unmount (P1-PERF-04).
  useEffect(() => {
    const s = pollersRef.current;
    return () => {
      s.forEach((id) => clearInterval(id));
      s.clear();
    };
  }, []);

  const stop = useCallback((id: ReturnType<typeof setInterval>) => {
    clearInterval(id);
    pollersRef.current.delete(id);
  }, []);

  const pollJob = useCallback(({
    jobId, authHeader, onCompleted, onFailed, intervalMs = 1000, maxAttempts = 600,
  }: PollJobArgs) => {
    let attempts = 0;
    const id = setInterval(async () => {
      attempts += 1;
      // P1-ARCH-02: hung jobs must not poll forever — hard ceiling per poller
      if (attempts > maxAttempts) {
        stop(id);
        onFailed(`Job ${jobId} did not complete within ${maxAttempts} polling attempts. It may still be running — check the jobs panel.`);
        return;
      }
      try {
        const pollRes = await fetch(`${API_BASE}/jobs/${jobId}`, { headers: authHeader() });
        const pollData = await pollRes.json();
        if (pollData.status === "COMPLETED") {
          stop(id);
          onCompleted(pollData.result);
        } else if (pollData.status === "FAILED" || pollData.status === "CANCELED") {
          stop(id);
          onFailed(pollData.error || "Simulation failed.");
        }
      } catch (e) {
        stop(id);
        onFailed(String(e));
      }
    }, intervalMs);
    pollersRef.current.add(id);
  }, [stop]);

  return { pollJob };
}
