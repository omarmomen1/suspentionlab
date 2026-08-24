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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  r: any;
  MR: number;
}

export default function KPIRibbon({ r, MR }: KPIRibbonProps) {
  return (
    <div className="grid grid-cols-8 gap-2 shrink-0">
      <KPICard
        label="Ride Freq ƒₙ"
        value={r.f_n_s ?? 0}
        unit="Hz"
        sub={`ωₙ = ${r.omega_n_s?.toFixed(2) ?? 'N/A'} rad/s`}
        status={r.f_n_s >= 1.0 && r.f_n_s <= 1.5 ? "good" : "warn"}
      />
      <KPICard
        label="Wheel-Hop ƒₙ"
        value={r.f_n_u}
        unit="Hz"
        sub="Unsprung mode"
        status={r.f_n_u >= 8 && r.f_n_u <= 15 ? "good" : "warn"}
      />
      <KPICard
        label="Damping Ratio ζ"
        value={r.zeta_s ?? 0}
        sub={`c_crit = ${r.c_crit_s?.toFixed(0) ?? 'N/A'} N·s/m`}
        status={getDampingStatus(r.zeta_s ?? 0)}
      />
      <KPICard
        label="Peak TX"
        value={r.peak_transmissibility ?? 0}
        sub={`@ ${r.freq_at_peak_tx?.toFixed(2) ?? 'N/A'} Hz`}
        status={getTXStatus(r.peak_transmissibility ?? 0)}
      />
      <KPICard
        label="Wk RMS Accel"
        value={r.rms_body_accel_wk ?? r.rms_body_accel}
        unit="m/s²"
        sub={r.comfort_rating || "ISO 2631-1 Wk"}
        status={getComfortStatus(r.rms_body_accel_wk ?? r.rms_body_accel)}
      />
      <KPICard
        label="RMS Susp Travel"
        value={(r.rms_susp_travel ?? 0) * 1000}
        unit="mm"
        sub={`Peak: ${((r.peak_susp_travel ?? 0) * 1000).toFixed(1)} mm`}
        status={(r.peak_susp_travel ?? 0) < 0.08 ? "good" : (r.peak_susp_travel ?? 0) < 0.15 ? "warn" : "bad"}
      />
      <KPICard
        label="RMS Tire Load"
        value={r.rms_tire_load}
        unit="N"
        sub={`k_t·Δz tire`}
        status={r.rms_tire_load < 500 ? "good" : r.rms_tire_load < 1500 ? "warn" : "bad"}
      />
      <KPICard
        label="Wheel Rate k_w"
        value={r.k_w}
        unit="N/m"
        sub={`MR = ${MR.toFixed(2)}`}
        status="neutral"
      />
    </div>
  );
}
