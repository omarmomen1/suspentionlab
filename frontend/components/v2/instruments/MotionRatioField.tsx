"use client";
import React from "react";
import EmptyState from "../EmptyState";
import { mrFieldCells, type SteerGridResponse } from "../../../lib/v2/phase4";

const CW = 34, CH = 28, LM = 54, TM = 22;

function colour(mr: number, lo: number, hi: number) {
  const t = hi > lo ? (mr - lo) / (hi - lo) : 0.5;
  const l = 22 + t * 48;
  return `hsl(38, 90%, ${l.toFixed(1)}%)`;
}

/** Heatmap of MR(bump, steer). Cells the solver could not reach are hatched and carry no number. */
export default function MotionRatioField({ data }: { data: SteerGridResponse | null | undefined }) {
  if (!data || !Array.isArray(data.bump_mm) || !Array.isArray(data.rack_travel_mm)) {
    return <EmptyState kind="not_run" reason="Compute the field to see MR(bump, steer)." />;
  }
  const { cells, min, max, unreachable } = mrFieldCells(data);
  const nB = data.bump_mm.length, nR = data.rack_travel_mm.length;
  const W = LM + nB * CW + 8, H = TM + nR * CH + 30;
  return (
    <figure className="m-0" data-testid="mr-field">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Motion ratio versus bump and rack travel" className="w-full">
        <defs>
          <pattern id="mr-unreachable" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="#15171a" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="#d9534f" strokeWidth="1.5" />
          </pattern>
        </defs>
        {cells.map((c) => {
          const x = LM + c.col * CW;
          const y = TM + (nR - 1 - c.row) * CH; // +rack at the top
          return (
            <g key={`${c.row}-${c.col}`} data-cell data-row={c.row} data-col={c.col} data-reachable={c.reachable ? "1" : "0"} {...(c.mr !== null ? { "data-mr": c.mr.toFixed(5) } : {})}>
              <rect x={x} y={y} width={CW - 1} height={CH - 1} fill={c.mr !== null && min !== null && max !== null ? colour(c.mr, min, max) : "url(#mr-unreachable)"} />
              {c.mr !== null && <text x={x + CW / 2} y={y + CH / 2 + 3} textAnchor="middle" fontSize={8} fill="#0b0c0e">{c.mr.toFixed(3)}</text>}
            </g>
          );
        })}
        {data.bump_mm.map((b, i) => (
          <text key={`b${i}`} x={LM + i * CW + CW / 2} y={H - 16} textAnchor="middle" fontSize={8} fill="#8a909a">{b}</text>
        ))}
        {data.rack_travel_mm.map((r, i) => (
          <text key={`r${i}`} x={LM - 6} y={TM + (nR - 1 - i) * CH + CH / 2 + 3} textAnchor="end" fontSize={9} fill="#8a909a">{r} mm</text>
        ))}
        <text x={LM + (nB * CW) / 2} y={H - 3} textAnchor="middle" fontSize={9} fill="#8a909a">wheel bump [mm]</text>
        <text x={4} y={12} fontSize={9} fill="#8a909a">rack travel</text>
      </svg>
      <figcaption className="text-[11px] text-[#8a909a] leading-snug" data-testid="mr-field-caption">
        {min !== null && max !== null ? `MR range ${min.toFixed(3)} to ${max.toFixed(3)}. ` : "No reachable cell. "}
        {unreachable > 0 ? `${unreachable} hatched cell${unreachable === 1 ? "" : "s"}: unreachable, the solver did not converge. ` : ""}
        Clearances: {data.clearances?.status ?? "NOT_MODELED"}.
      </figcaption>
    </figure>
  );
}
