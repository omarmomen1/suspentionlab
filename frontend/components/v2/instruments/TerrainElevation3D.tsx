"use client";
import React, { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import EmptyState from "../EmptyState";
import { useWideViewport } from "./AttitudeModel3D";

export interface TerrainTrace {
  x_m?: number[];
  y_m?: number[];
  z_m?: number[];
  vertical_g?: number[];
  compression_mm?: number[];
  [k: string]: unknown;
}

export const TERRAIN_Z_EXAGGERATION = 5;
export const TERRAIN_DISCLAIMER =
  "Elevation: 19 altitude stations from the official Spa circuit map, spline-interpolated. Too coarse to resolve the local Eau Rouge compression.";

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

export function TerrainReadout({ trace }: { trace: TerrainTrace | null | undefined }) {
  const r = terrainReadout(trace);
  if (!r || !r.z) return <EmptyState kind="unavailable" reason="No elevation channel. Turn on Include Elevation (Spa) and run again." />;
  const f = (x: { min: number; max: number } | null, u: string, d = 2) => (x ? `${x.min.toFixed(d)} to ${x.max.toFixed(d)} ${u}` : "not available");
  const flat = r.z.max === r.z.min;
  return (
    <dl data-testid="terrain-readout" className="text-[11px] text-[#cfd3da] m-0 grid grid-cols-3 gap-2">
      <div><dt className="text-[#8a909a]">z</dt><dd className="m-0" data-zmin={r.z.min} data-zmax={r.z.max}>{f(r.z, "m", 1)}</dd></div>
      <div><dt className="text-[#8a909a]">Vertical g</dt><dd className="m-0">{f(r.vg, "g", 3)}</dd></div>
      <div><dt className="text-[#8a909a]">Compression</dt><dd className="m-0">{f(r.comp, "mm", 1)}</dd></div>
      <div className="col-span-3 text-[#8a909a]" data-testid="terrain-disclaimer">{flat ? "Flat track: z = 0, no elevation data for this circuit." : TERRAIN_DISCLAIMER}</div>
    </dl>
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
  if (!pts) return readout;
  return (
    <div data-testid="terrain-3d">
      {wide ? (
        <div className="h-[240px] border border-[#2a2d33]">
          <Canvas camera={{ position: [5, 4, 5], fov: 35 }} dpr={[1, 1.5]}>
            <gridHelper args={[8, 16, "#3a3f48", "#23262c"]} />
            <line>
              <bufferGeometry>
                <bufferAttribute attach="attributes-position" count={pts.length / 3} array={pts} itemSize={3} />
              </bufferGeometry>
              <lineBasicMaterial color="#f2a900" />
            </line>
          </Canvas>
        </div>
      ) : (
        <p className="text-[11px] text-[#8a909a] m-0" data-testid="terrain-2d-fallback">3D view hidden on narrow screens.</p>
      )}
      <p className="text-[11px] text-[#f2a900] m-0" data-testid="terrain-exaggeration">Height drawn ×{TERRAIN_Z_EXAGGERATION}.</p>
      {readout}
    </div>
  );
}
