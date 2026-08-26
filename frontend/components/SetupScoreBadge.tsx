"use client";
import { useEffect, useState } from "react";
import { Trophy, Loader2 } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

/**
 * Setup Score fleet benchmark badge (Tier A1).
 *
 * Given the current simulation metrics, asks the backend to score the setup
 * and place it in the anonymous fleet distribution. Submission is anonymous
 * server-side (no user identifiers stored) — that is stated in the UI because
 * it is the reason engineers opt in.
 */

export interface SetupScoreResult {
  score: number;
  band: string;
  percentile: number;
  fleet_size: number;
  message: string;
  components: { comfort: number; grip: number; control: number };
}

interface SetupScoreBadgeProps {
  /** Sprung-mass RMS acceleration [m/s²] */
  rmsBodyAccel: number;
  /** RMS dynamic tire load [N] */
  rmsTireLoadN: number;
  /** Peak suspension travel [m] (converted to mm internally) */
  peakSuspTravelM: number;
  /** Trigger: changes whenever a new simulation completes */
  runKey: string;
}

const BAND_STYLES: Record<string, string> = {
  Excellent: "text-emerald-400 border-emerald-500/30 bg-emerald-500/5",
  Good:      "text-ansys-yellow border-ansys-yellow/30 bg-ansys-yellow/5",
  Fair:      "text-amber-400 border-amber-500/30 bg-amber-500/5",
  Poor:      "text-red-400 border-red-500/30 bg-red-500/5",
};

export default function SetupScoreBadge({
  rmsBodyAccel, rmsTireLoadN, peakSuspTravelM, runKey,
}: SetupScoreBadgeProps) {
  const { fetchWithAuth } = useAuth();
  const [result, setResult] = useState<SetupScoreResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runKey) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchWithAuth("/api/v1/scores/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        vehicle_class: "road",
        rms_body_accel_ms2: rmsBodyAccel,
        rms_tire_load_var_n: rmsTireLoadN,
        peak_susp_travel_mm: peakSuspTravelM * 1000,
      }),
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Score service returned ${res.status}`);
        return res.json();
      })
      .then((data: SetupScoreResult) => { if (!cancelled) setResult(data); })
      .catch((err: Error) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runKey]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-gray-600 px-3 py-2">
        <Loader2 size={12} className="animate-spin" /> Scoring vs fleet…
      </div>
    );
  }
  if (error || !result) return null;

  const style = BAND_STYLES[result.band] ?? BAND_STYLES.Fair;
  return (
    <div className={`inline-flex items-center gap-2.5 rounded-xl border px-3 py-2 ${style}`}
      title={`Comfort ${Math.round(result.components.comfort)} · Grip ${Math.round(result.components.grip)} · Control ${Math.round(result.components.control)}`}>
      <Trophy size={14} />
      <div className="leading-tight">
        <span className="text-sm font-bold">{result.score.toFixed(0)}</span>
        <span className="text-[10px] uppercase tracking-wider ml-1.5 opacity-80">{result.band}</span>
        <p className="text-[10px] text-gray-500">
          Beats {result.percentile.toFixed(0)}% of the road-car fleet
          {result.fleet_size > 1 ? ` (n=${result.fleet_size})` : ""} · anonymous
        </p>
      </div>
    </div>
  );
}
