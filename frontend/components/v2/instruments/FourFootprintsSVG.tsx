"use client";
import React from "react";
import EmptyState from "../EmptyState";
import { cornerLoadsAt, maxCornerLoadN, type FullCarLoadParams, type FullCarSeries } from "../../../lib/v2/phase4";

export interface FourFootprintsSVGProps {
  result: FullCarSeries | null | undefined;
  params: FullCarLoadParams;
  /** Scrubbed sample index into the solver time series. */
  index: number;
}

const W = 320, H = 360;
const PAD = { x: 70, top: 36 };
const FW = 70, FH = 110;           // footprint rectangle (fixed size; load is shown by bar height and number)
const POS = {
  fl: { x: PAD.x, y: PAD.top },
  fr: { x: W - PAD.x - FW, y: PAD.top },
  rl: { x: PAD.x, y: PAD.top + 190 },
  rr: { x: W - PAD.x - FW, y: PAD.top + 190 },
} as const;
const LABEL: Record<string, string> = { fl: "FL", fr: "FR", rl: "RL", rr: "RR" };

/**
 * Four tire footprints driven by the real corner vertical load at the scrubbed sample.
 * Bar height is linear in Fz against the largest Fz of the run. The only forces shown are the
 * vertical loads; no slip angle or lateral force is drawn because the 7-DOF model does not solve them.
 */
export default function FourFootprintsSVG({ result, params, index }: FourFootprintsSVGProps) {
  const c = cornerLoadsAt(result, params, index);
  const scale = maxCornerLoadN(result, params);
  if (!c || !scale || scale <= 0) {
    return <EmptyState kind="not_run" reason="Run the full-car solver to see the four corner loads." />;
  }
  const keys = ["fl", "fr", "rl", "rr"] as const;
  return (
    <figure className="m-0" data-testid="four-footprints">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Four corner vertical tire loads" className="w-full max-w-[340px]">
        {keys.map((k) => {
          const fz = c[k];
          const p = POS[k];
          const barH = (fz / scale) * FH;
          return (
            <g key={k} data-corner={k} data-fz={fz.toFixed(3)}>
              <rect x={p.x} y={p.y} width={FW} height={FH} fill="none" stroke="#3a3f48" strokeWidth={1} />
              <rect data-bar={k} x={p.x} y={p.y + FH - barH} width={FW} height={barH} fill={fz === 0 ? "#d9534f" : "#f2a900"} opacity={0.85} />
              <text x={p.x + FW / 2} y={p.y - 8} textAnchor="middle" fontSize={11} fill="#cfd3da">{LABEL[k]}</text>
              <text x={p.x + FW / 2} y={p.y + FH + 14} textAnchor="middle" fontSize={11} fill="#cfd3da">{Math.round(fz)} N</text>
            </g>
          );
        })}
        <text x={W / 2} y={PAD.top + 150} textAnchor="middle" fontSize={10} fill="#8a909a" data-pair="front">
          Front L-R {Math.round(c.frontLeftMinusRightN)} N
        </text>
        <text x={W / 2} y={PAD.top + 168} textAnchor="middle" fontSize={10} fill="#8a909a" data-pair="rear">
          Rear L-R {Math.round(c.rearLeftMinusRightN)} N
        </text>
      </svg>
      <figcaption className="text-[11px] text-[#8a909a] leading-snug">
        Vertical load Fz = max(0, static + k_t (z_road - z_unsprung)), as in full_car.py. Static per corner: front {Math.round(c.staticFrontN)} N, rear {Math.round(c.staticRearN)} N.
        Bar height is linear against the run maximum ({Math.round(scale)} N). Slip angle and lateral force: not modeled.
        {c.liftedCorners.length > 0 ? ` Contact lost (Fz = 0): ${c.liftedCorners.map((k) => LABEL[k]).join(", ")}.` : ""}
        {c.time_s !== null ? ` t = ${c.time_s.toFixed(3)} s.` : ""}
      </figcaption>
    </figure>
  );
}
