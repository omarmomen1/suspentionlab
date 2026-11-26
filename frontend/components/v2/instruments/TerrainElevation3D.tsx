"use client";
import React, { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import EmptyState from "../EmptyState";
import { useWideViewport } from "./AttitudeModel3D";

export interface TerrainTrace {
  s_m?: number[];
  x_m?: number[];
  y_m?: number[];
  z_m?: number[];
  vertical_g?: number[];
  compression_mm?: number[];
  [k: string]: unknown;
}

export const TERRAIN_Z_EXAGGERATION = 5;
export const TERRAIN_DISCLAIMER =
  "Elevation: 19 altitude stations from the official Spa circuit map (7004 m lap), spline-interpolated between stations. Too coarse to resolve the local Eau Rouge compression.";

const fin = (a: unknown): a is number[] => Array.isArray(a) && a.length > 1 && a.every((v) => typeof v === "number" && Number.isFinite(v));
export const range = (a: number[]) => ({ min: Math.min(...a), max: Math.max(...a) });

/** Channel ranges, always rendered as numbers. Returns null for a missing channel. */
export function terrainReadout(t: TerrainTrace | null | undefined) {
  if (!t) return null;
  return {
    z: fin(t.z_m) ? range(t.z_m) : null,
    vg: fin(t.vertical_g) ? range(t.vertical_g) : null,
    comp: fin(t.compression_mm) ? range(t.compression_mm) : null,
  };
}

/** True only when the trace carries a real, non-constant elevation profile. A constant z (all 0) is "no data", not a flat road. */
export function hasElevationData(t: TerrainTrace | null | undefined): boolean {
  const r = terrainReadout(t);
  return !!r && !!r.z && r.z.max !== r.z.min;
}

export function TerrainReadout({ trace }: { trace: TerrainTrace | null | undefined }) {
  const r = terrainReadout(trace);
  if (!hasElevationData(trace) || !r || !r.z) return <EmptyState kind="unavailable" reason="No elevation data for this run. Only Spa has an elevation profile: turn on Include Elevation (Spa) and run again." />;
  const f = (x: { min: number; max: number } | null, u: string, d = 2) => (x ? `${x.min.toFixed(d)} to ${x.max.toFixed(d)} ${u}` : "not available");
  return (
    <dl data-testid="terrain-readout" className="v2-num text-[11px] text-zinc-200 m-0 grid grid-cols-3 gap-2">
      <div><dt className="text-[#8a909a]">z</dt><dd className="m-0" data-zmin={r.z.min} data-zmax={r.z.max}>{f(r.z, "m", 1)}</dd></div>
      <div><dt className="text-[#8a909a]">Vertical g</dt><dd className="m-0">{f(r.vg, "g", 3)}</dd></div>
      <div><dt className="text-[#8a909a]">Compression</dt><dd className="m-0">{f(r.comp, "mm", 1)}</dd></div>
      <div className="col-span-3 text-[#8a909a]" data-testid="terrain-disclaimer">{TERRAIN_DISCLAIMER}</div>
    </dl>
  );
}

/** Narrow-screen replacement for the canvas: z(s) as a 2D profile, real samples only. */
export function ElevationProfile2D({ trace }: { trace: TerrainTrace | null | undefined }) {
  if (!trace || !fin(trace.s_m) || !fin(trace.z_m) || !hasElevationData(trace)) return null;
  const n = Math.min(trace.s_m.length, trace.z_m.length);
  const step = Math.max(1, Math.floor(n / 300));
  const zr = range(trace.z_m), sr = range(trace.s_m);
  const W = 320, H = 90, M = 6;
  const pts: string[] = [];
  for (let i = 0; i < n; i += step) {
    const x = M + ((trace.s_m[i] - sr.min) / Math.max(sr.max - sr.min, 1e-9)) * (W - 2 * M);
    const y = H - M - ((trace.z_m[i] - zr.min) / Math.max(zr.max - zr.min, 1e-9)) * (H - 2 * M);
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return (
    <svg data-testid="terrain-2d-profile" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Elevation versus distance" className="w-full">
      <polyline points={pts.join(" ")} fill="none" stroke="#C8F04B" strokeWidth="1" />
    </svg>
  );
}

/** Track ribbon lifted by z(s), drawn x5 vertically (labelled). One canvas, hidden below 640 px. */
export default function TerrainElevation3D({ trace }: { trace: TerrainTrace | null | undefined }) {
  const wide = useWideViewport();
  const pts = useMemo(() => {
    if (!trace || !fin(trace.x_m) || !fin(trace.y_m) || !fin(trace.z_m)) return null;
    const n = Math.min(trace.x_m.length, trace.y_m.length, trace.z_m.length);
    const step = Math.max(1, Math.floor(n / 800));
    const cx = (range(trace.x_m).min + range(trace.x_m).max) / 2;
    const cy = (range(trace.y_m).min + range(trace.y_m).max) / 2;
    const z0 = range(trace.z_m).min;
    const span = Math.max(range(trace.x_m).max - range(trace.x_m).min, range(trace.y_m).max - range(trace.y_m).min, 1);
    const out: number[] = [];
    for (let i = 0; i < n; i += step) {
      out.push((trace.x_m[i] - cx) / span * 6, ((trace.z_m[i] - z0) * TERRAIN_Z_EXAGGERATION) / span * 6, (trace.y_m[i] - cy) / span * 6);
    }
    return new Float32Array(out);
  }, [trace]);
  const readout = <TerrainReadout trace={trace} />;
  if (!pts || !hasElevationData(trace)) return readout;
  return (
    <div data-testid="terrain-3d">
      {wide ? (
        <div className="h-[240px] border border-white/10">
          <Canvas camera={{ position: [5, 4, 5], fov: 35 }} dpr={[1, 1.5]}>
            <gridHelper args={[8, 16, "#2a3036", "#1a2026"]} />
            <line>
              <bufferGeometry>
                <bufferAttribute attach="attributes-position" count={pts.length / 3} array={pts} itemSize={3} />
              </bufferGeometry>
              <lineBasicMaterial color="#C8F04B" />
            </line>
          </Canvas>
        </div>
      ) : (
        <div data-testid="terrain-2d-fallback"><ElevationProfile2D trace={trace} /></div>
      )}
      <p className="text-[11px] text-[#C8F04B] m-0" data-testid="terrain-exaggeration">Height drawn ×{TERRAIN_Z_EXAGGERATION}.</p>
      {readout}
    </div>
  );
}
