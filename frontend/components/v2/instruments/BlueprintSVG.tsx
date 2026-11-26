"use client";
import React from "react";
import EmptyState from "../EmptyState";

type P3 = [number, number, number];
export type BlueprintGeometry = Record<string, P3>;

export interface BlueprintSVGProps {
  /** Hardpoint positions [x, y, z] mm at the current travel step (solver geometry_steps[i]). */
  geometry: BlueprintGeometry;
  /** Static (travel = 0) hardpoints, used for the ΔY readouts. */
  staticGeometry?: BlueprintGeometry;
  travelMm: number;
  /** Solver outputs at the current step. Missing means Not available, never 0. */
  rollCenterHeightMm?: number | null;
  rollCenterLateralMm?: number | null;
  icYMm?: number | null;
  icZMm?: number | null;
  motionRatio?: number | null;
  /** Target band for the motion ratio, from the page's target-band settings. */
  motionRatioBand?: [number, number] | null;
  /** Scrubber. Index into the solver travel array. */
  travelValues?: number[];
  travelIdx?: number;
  onTravelIdxChange?: (idx: number) => void;
}

const fin = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);
const mid = (a: P3, b: P3): P3 => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];

/**
 * Front-view (Y-Z plane) double-wishbone section: wishbones, upright, kingpin axis,
 * instant centre, roll centre and ground plane, with a live travel scrubber.
 * Everything is drawn from the supplied solver geometry. There are no baked-in hardpoint,
 * roll-centre or KPI defaults. Lateral offsets are ΔY (front view), never ΔX.
 */
export default function BlueprintSVG({
  geometry, staticGeometry, travelMm, rollCenterHeightMm, rollCenterLateralMm, icYMm, icZMm,
  motionRatio, motionRatioBand, travelValues, travelIdx, onTravelIdxChange,
}: BlueprintSVGProps) {
  const g = geometry;
  const need = ["UWI_fwd", "UWI_aft", "UWO", "LWI_fwd", "LWI_aft", "LWO", "WC", "CP"];
  if (!need.every((k) => Array.isArray(g?.[k]))) {
    return <div data-testid="blueprint-svg"><EmptyState kind="not_run" reason="Run the solver to draw the section" /></div>;
  }
  const uwi = mid(g.UWI_fwd, g.UWI_aft);
  const lwi = mid(g.LWI_fwd, g.LWI_aft);
  const { UWO, LWO, WC, CP } = g;

  // Bounds from drawn points only (IC may be far away, so it is clamped, not used for bounds).
  const pts: [number, number][] = [[uwi[1], uwi[2]], [lwi[1], lwi[2]], [UWO[1], UWO[2]], [LWO[1], LWO[2]], [WC[1], WC[2]], [CP[1], 0], [0, 0]];
  if (fin(rollCenterHeightMm)) pts.push([fin(rollCenterLateralMm) ? rollCenterLateralMm : 0, rollCenterHeightMm]);
  const ys = pts.map((p) => p[0]);
  const zs = pts.map((p) => p[1]);
  const yMin = Math.min(...ys) - 60;
  const yMax = Math.max(...ys) + 60;
  const zMin = Math.min(...zs, 0) - 30;
  const zMax = Math.max(...zs) + 40;
  const VW = 520;
  const s = Math.min(VW / (yMax - yMin), 340 / (zMax - zMin));
  const VH = (zMax - zMin) * s;
  const X = (y: number) => (y - yMin) * s;
  const Z = (z: number) => VH - (z - zMin) * s;

  // Kingpin axis: LWO -> UWO, extended both ways.
  const dy = UWO[1] - LWO[1];
  const dz = UWO[2] - LWO[2];
  const len = Math.hypot(dy, dz) || 1;
  const ext = 40;
  const k0: [number, number] = [LWO[1] - (dy / len) * ext, LWO[2] - (dz / len) * ext];
  const k1: [number, number] = [UWO[1] + (dy / len) * ext, UWO[2] + (dz / len) * ext];

  const sg = staticGeometry;
  const dYWheel = sg?.WC ? WC[1] - sg.WC[1] : null;
  const dYRoll = fin(rollCenterLateralMm) ? rollCenterLateralMm : null;
  const icInView = fin(icYMm) && fin(icZMm) && icYMm >= yMin && icYMm <= yMax && icZMm >= zMin && icZMm <= zMax;
  const mrOut = fin(motionRatio) && motionRatioBand ? motionRatio < motionRatioBand[0] || motionRatio > motionRatioBand[1] : false;
  const line = (a: [number, number], b: [number, number], stroke: string, w = 1.5, dash?: string) => (
    <line x1={X(a[0])} y1={Z(a[1])} x2={X(b[0])} y2={Z(b[1])} stroke={stroke} strokeWidth={w} strokeDasharray={dash} />
  );

  return (
    <div data-testid="blueprint-svg" className="space-y-2">
      <svg viewBox={`0 0 ${VW} ${VH.toFixed(0)}`} className="h-auto w-full rounded border border-hairline bg-carbon" role="img" aria-label="Front-view double-wishbone section">
        {/* ground plane */}
        <line x1={0} y1={Z(0)} x2={VW} y2={Z(0)} stroke="#4b5560" strokeWidth={1} />
        <text x={6} y={Z(0) - 4} fontSize={9} fill="#8b97a3">ground z = 0</text>
        {/* wishbones */}
        {line([uwi[1], uwi[2]], [UWO[1], UWO[2]], "#C8F04B")}
        {line([lwi[1], lwi[2]], [LWO[1], LWO[2]], "#C8F04B")}
        {/* upright and wheel centre */}
        {line([UWO[1], UWO[2]], [LWO[1], LWO[2]], "#E6EAEE", 2)}
        {line([LWO[1], LWO[2]], [WC[1], WC[2]], "#6b7682", 1)}
        {line([WC[1], WC[2]], [CP[1], 0], "#6b7682", 1, "3 3")}
        {/* kingpin axis */}
        {line(k0, k1, "#57C8DC", 1, "6 3")}
        {/* joints */}
        {[[uwi[1], uwi[2]], [lwi[1], lwi[2]], [UWO[1], UWO[2]], [LWO[1], LWO[2]], [WC[1], WC[2]]].map(([y, z], i) => (
          <circle key={i} cx={X(y)} cy={Z(z)} r={3} fill="#0C0F12" stroke="#E6EAEE" strokeWidth={1} />
        ))}
        {/* contact patch */}
        <circle cx={X(CP[1])} cy={Z(0)} r={3} fill="#FFB84D" />
        {/* roll centre */}
        {fin(rollCenterHeightMm) && (
          <g data-testid="blueprint-rc">
            <circle cx={X(dYRoll ?? 0)} cy={Z(rollCenterHeightMm)} r={4} fill="none" stroke="#4AD991" strokeWidth={1.5} />
            <text x={X(dYRoll ?? 0) + 7} y={Z(rollCenterHeightMm) + 3} fontSize={9} fill="#4AD991">RC</text>
          </g>
        )}
        {/* instant centre */}
        {icInView && (
          <g data-testid="blueprint-ic">
            <circle cx={X(icYMm as number)} cy={Z(icZMm as number)} r={4} fill="none" stroke="#FF5C5C" strokeWidth={1.5} />
            <text x={X(icYMm as number) + 7} y={Z(icZMm as number) + 3} fontSize={9} fill="#FF5C5C">IC</text>
          </g>
        )}
        <text x={VW - 6} y={14} textAnchor="end" fontSize={9} fill="#8b97a3">front view, Y (right) / Z (up), mm</text>
      </svg>

      {travelValues && travelValues.length > 1 && onTravelIdxChange && (
        <label className="flex items-center gap-3 text-xs text-gray-300">
          <span className="w-24 shrink-0 text-gray-400">Wheel travel</span>
          <input
            type="range"
            data-testid="blueprint-scrubber"
            min={0}
            max={travelValues.length - 1}
            step={1}
            value={Math.min(travelIdx ?? 0, travelValues.length - 1)}
            onChange={(e) => onTravelIdxChange(Number(e.target.value))}
            className="flex-1 accent-[#C8F04B]"
            aria-label="Wheel travel"
          />
          <span className="v2-num w-20 text-right text-white">{travelMm.toFixed(1)} mm</span>
        </label>
      )}

      <dl data-testid="blueprint-readouts" className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
        {[
          ["ΔY wheel centre", dYWheel, "mm"],
          ["ΔY roll centre", dYRoll, "mm"],
          ["RC height", rollCenterHeightMm, "mm"],
          ["Motion ratio", motionRatio, ""],
        ].map(([label, v, unit]) => (
          <div key={label as string} className="rounded border border-hairline bg-panel px-2 py-1.5">
            <dt className="text-[10px] uppercase tracking-wider text-gray-500">{label as string}</dt>
            <dd className="v2-num text-white">{fin(v as number | null | undefined) ? `${(v as number).toFixed(label === "Motion ratio" ? 3 : 1)} ${unit}` : <EmptyState />}</dd>
          </div>
        ))}
      </dl>
      {motionRatioBand && fin(motionRatio) && (
        <p data-testid="blueprint-mr-band" className={`text-[11px] ${mrOut ? "text-warning" : "text-verified"}`}>
          Motion ratio {motionRatio.toFixed(3)} is {mrOut ? "outside" : "inside"} the target band {motionRatioBand[0].toFixed(2)} to {motionRatioBand[1].toFixed(2)}.
        </p>
      )}
    </div>
  );
}
