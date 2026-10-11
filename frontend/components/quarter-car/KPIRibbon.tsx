"use client";

/**
 * components/quarter-car/KPIRibbon.tsx (P1-ARCH-01)
 * Extracted from quarter-car/page.tsx — the 8-card KPI summary row with
 * engineering status colouring.
 */

import React from "react";
import KPICard from "../sim/KPICard";

type Status = "good" | "warn" | "bad" | "neutral";

function getDampingStatus(z: number): Status {
  if (z >= 0.25 && z <= 0.6) return "good";
  if (z >= 0.1 && z <= 0.8) return "warn";
  return "bad";
}
function getComfortStatus(rmsWk: number): Status {
  if (rmsWk < 0.315) return "good";
  if (rmsWk < 1.0) return "warn";
  return "bad";
}
function getTXStatus(tx: number): Status {
  if (tx < 2.0) return "good";
  if (tx < 3.5) return "warn";
  return "bad";
}

interface KPIRibbonProps {
  /** Simulation result record (any-typed to match page-level SimResult). */
  
  r: any;
  MR: number;
}

export default function KPIRibbon({ r, MR }: KPIRibbonProps) {
  const f_n_s = r.f_n_s != null ? Number(r.f_n_s).toFixed(2) : "–";
  const f_n_u = r.f_n_u != null ? Number(r.f_n_u).toFixed(2) : "–";
  const zeta_s = r.zeta_s != null ? Number(r.zeta_s).toFixed(3) : "–";
  const peak_tx = r.peak_transmissibility != null ? Number(r.peak_transmissibility).toFixed(2) : "–";
  const rms_accel_val = r.rms_body_accel_wk ?? r.rms_body_accel;
  const rms_accel = rms_accel_val != null ? Number(rms_accel_val).toFixed(3) : "–";
  const rms_travel = r.rms_susp_travel != null ? (Number(r.rms_susp_travel) * 1000).toFixed(1) : "–";
  const peak_travel_sub = r.peak_susp_travel != null ? `Peak: ${(Number(r.peak_susp_travel) * 1000).toFixed(1)} mm` : "Peak: –";
  const rms_tire_load = r.rms_tire_load != null ? Math.round(Number(r.rms_tire_load)).toLocaleString() : "–";
  const k_w = r.k_w != null ? Math.round(Number(r.k_w)).toLocaleString() : "–";

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 shrink-0">
      <KPICard
        label="Ride Freq ƒₙ"
        value={f_n_s}
        unit="Hz"
        sub={`ωₙ = ${r.omega_n_s?.toFixed(2) ?? 'N/A'} rad/s`}
        status={r.f_n_s >= 1.0 && r.f_n_s <= 1.5 ? "good" : "warn"}
      />
      <KPICard
        label="Wheel-Hop ƒₙ"
        value={f_n_u}
        unit="Hz"
        sub="Unsprung mode"
        status={r.f_n_u >= 8 && r.f_n_u <= 15 ? "good" : "warn"}
      />
      <KPICard
        label="Damping Ratio ζ"
        value={zeta_s}
        sub={`c_crit = ${r.c_crit_s ? Math.round(r.c_crit_s).toLocaleString() : 'N/A'} N·s/m`}
        status={getDampingStatus(r.zeta_s ?? 0)}
      />
      <KPICard
        label="Peak TX"
        value={peak_tx}
        sub={`@ ${r.freq_at_peak_tx?.toFixed(2) ?? 'N/A'} Hz`}
        status={getTXStatus(r.peak_transmissibility ?? 0)}
      />
      <KPICard
        label="Wk RMS Accel"
        value={rms_accel}
        unit="m/s²"
        sub={r.comfort_rating || "ISO 2631-1 Wk"}
        status={getComfortStatus(rms_accel_val ?? 0)}
      />
      <KPICard
        label="RMS Susp Travel"
        value={rms_travel}
        unit="mm"
        sub={peak_travel_sub}
        status={(r.peak_susp_travel ?? 0) < 0.08 ? "good" : (r.peak_susp_travel ?? 0) < 0.15 ? "warn" : "bad"}
      />
      <KPICard
        label="RMS Tire Load"
        value={rms_tire_load}
        unit="N"
        sub="k_t·Δz tire"
        status={(r.rms_tire_load ?? 0) < 500 ? "good" : (r.rms_tire_load ?? 0) < 1500 ? "warn" : "bad"}
      />
      <KPICard
        label="Wheel Rate k_w"
        value={k_w}
        unit="N/m"
        sub={`MR = ${Number(MR ?? 1).toFixed(2)}`}
        status="neutral"
      />
    </div>
  );
}
