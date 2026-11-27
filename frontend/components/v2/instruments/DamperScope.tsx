"use client";
import React, { useMemo } from "react";
import StatusPill from "../StatusPill";
import EmptyState from "../EmptyState";
import { damperWorkLoop, shaftSpeedHistogram, thin, travelBudget, type DamperModel } from "../../../lib/v2/instruments";

export interface DamperScopeProps {
  /** Time [s], body/wheel displacement [m] and velocity [m/s] from the solver result. */
  time: number[];
  zS: number[];
  zU: number[];
  dzS: number[];
  dzU: number[];
  /** Relative suspension travel at the wheel [m] (solver `susp_travel`). */
  suspTravelM: number[];
  /** Damper parameters of the run that produced the traces (the snapshot, not live inputs). */
  damper: DamperModel;
  /** Shared design travel limit [mm]. Not a modelled bump stop. */
  travelLimitMm?: number;
}

const W = 300;
const H = 190;
const PAD = 30;

function scale(vals: number[], pad = 0.06): [number, number] {
  let lo = Math.min(...vals);
  let hi = Math.max(...vals);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (hi - lo < 1e-12) { lo -= 1; hi += 1; }
  const p = (hi - lo) * pad;
  return [lo - p, hi + p];
}

function Frame({ title, xLabel, yLabel, children }: { title: string; xLabel: string; yLabel: string; children: React.ReactNode }) {
  return (
    <figure className="rounded border border-hairline bg-panel p-2">
      <figcaption className="px-1 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={title}>
        <rect x={PAD} y={8} width={W - PAD - 8} height={H - PAD - 8} fill="none" stroke="#2a313a" strokeWidth={1} />
        {children}
        <text x={W / 2} y={H - 6} textAnchor="middle" fontSize={9} fill="#8b97a3">{xLabel}</text>
        <text x={9} y={H / 2} textAnchor="middle" fontSize={9} fill="#8b97a3" transform={`rotate(-90 9 ${H / 2})`}>{yLabel}</text>
      </svg>
    </figure>
  );
}

/**
 * Damper scope: force-velocity curve with the run's operating cloud, shaft-speed histogram,
 * travel budget, and the work loop (damper force against displacement), whose enclosed area
 * is the energy dissipated per cycle in joules.
 */
export default function DamperScope({ time, zS, zU, dzS, dzU, suspTravelM, damper, travelLimitMm = 80 }: DamperScopeProps) {
  const a = useMemo(() => {
    const loop = damperWorkLoop(zS, zU, dzS, dzU, damper);
    return { loop, hist: shaftSpeedHistogram(loop.v_mps, 24), budget: travelBudget(time, suspTravelM, travelLimitMm) };
  }, [time, zS, zU, dzS, dzU, suspTravelM, damper, travelLimitMm]);

  if (a.loop.x_mm.length < 2) {
    return <div data-testid="damper-scope"><EmptyState kind="not_run" reason="No solver traces yet" /></div>;
  }

  const { loop, hist, budget } = a;
  const px = (v: number, lo: number, hi: number) => PAD + ((v - lo) / (hi - lo)) * (W - PAD - 8);
  const py = (v: number, lo: number, hi: number) => 8 + (1 - (v - lo) / (hi - lo)) * (H - PAD - 8);

  // Force-velocity: operating cloud + the characteristic over the run's velocity range.
  const [vLo, vHi] = scale(loop.v_mps);
  const [fLo, fHi] = scale(loop.force_N);
  const cloud = thin(loop.v_mps.map((v, i) => [v, loop.force_N[i]] as [number, number]), 500);
  const curve = thin(
    [...loop.v_mps.keys()].sort((i, j) => loop.v_mps[i] - loop.v_mps[j]).map((i) => [loop.v_mps[i], loop.force_N[i]] as [number, number]),
    120,
  );
  // Work loop: force against displacement.
  const [xLo, xHi] = scale(loop.x_mm);
  const path = thin(loop.x_mm.map((x, i) => [x, loop.force_N[i]] as [number, number]), 800)
    .map(([x, f], i) => `${i ? "L" : "M"}${px(x, xLo, xHi).toFixed(1)},${py(f, fLo, fHi).toFixed(1)}`).join(" ");
  const hMax = Math.max(1e-9, ...hist.fraction);

  return (
    <div data-testid="damper-scope" className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {loop.fromCurve && (
        <p data-testid="damper-curve-note" className="md:col-span-2 text-[11px] text-warning">
          <StatusPill status="WARNING" label="LUT" /> Force comes from the tabulated damper curve by linear interpolation, assuming
          shaft velocity (m/s) against shaft force (N). The backend convention was not verified.
        </p>
      )}

      <Frame title="Force-velocity and operating cloud" xLabel="Shaft velocity (m/s)" yLabel="Damper force (N)">
        <polyline fill="none" stroke="#C8F04B" strokeWidth={1} points={curve.map(([v, f]) => `${px(v, vLo, vHi).toFixed(1)},${py(f, fLo, fHi).toFixed(1)}`).join(" ")} />
        {cloud.map(([v, f], i) => <circle key={i} cx={px(v, vLo, vHi)} cy={py(f, fLo, fHi)} r={1.1} fill="#57C8DC" />)}
      </Frame>

      <Frame title="Work loop: force vs displacement" xLabel="Shaft displacement (mm)" yLabel="Damper force (N)">
        <path d={path} fill="none" stroke="#FFB84D" strokeWidth={1} />
      </Frame>

      <Frame title="Shaft-speed histogram" xLabel="Shaft velocity (m/s)" yLabel="Share of samples">
        {hist.centers.map((c, i) => {
          const bw = (W - PAD - 8) / hist.centers.length;
          const h = (hist.fraction[i] / hMax) * (H - PAD - 8);
          return <rect key={i} x={PAD + i * bw + 0.5} y={H - PAD - h} width={Math.max(0.5, bw - 1)} height={h} fill="#57C8DC" />;
        })}
      </Frame>

      <div className="rounded border border-hairline bg-panel p-3 text-xs">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-400">Travel budget and energy</p>
        <dl className="space-y-1.5">
          <div className="flex justify-between"><dt className="text-gray-400">Energy dissipated, ∮F dx over the run</dt>
            <dd className="v2-num text-white" data-testid="work-loop-energy">{loop.energy_J === null ? "Not available" : `${loop.energy_J.toFixed(1)} J`}</dd></div>
          {budget ? (
            <>
              <div className="flex justify-between"><dt className="text-gray-400">Peak travel</dt>
                <dd className="v2-num text-white">{budget.peak_mm.toFixed(1)} mm ({budget.peak_pct_of_limit.toFixed(0)}% of {budget.limit_mm} mm)</dd></div>
              <div className="flex justify-between"><dt className="text-gray-400">Stop contact</dt>
                <dd className="v2-num text-white" data-testid="stop-contact">{budget.contact_pct_of_sim_duration.toFixed(1)}% of sim duration</dd></div>
            </>
          ) : <div><EmptyState reason="Travel budget" /></div>}
        </dl>
        <p className="mt-3 text-[10px] leading-relaxed text-gray-500">
          The area enclosed by one closed cycle of the work loop is the energy dissipated per cycle. For a random road
          trace the loop does not close, so the figure above is the integral over the whole run. The {travelLimitMm} mm limit is the
          shared design travel limit, not a modelled bump stop.
        </p>
      </div>
    </div>
  );
}
