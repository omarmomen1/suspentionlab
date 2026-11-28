"use client";
import React, { useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";
import EmptyState from "../EmptyState";
import FourFootprintsSVG from "./FourFootprintsSVG";
import { attitudeAt, exaggeratedPose, ATTITUDE_EXAGGERATION, type FullCarLoadParams, type FullCarSeries } from "../../../lib/v2/phase4";

export interface AttitudeModel3DProps {
  result: FullCarSeries | null | undefined;
  index: number;
  /** Needed for the narrow-screen fallback, which shows the four footprints instead of the canvas. */
  loadParams?: FullCarLoadParams | null;
}

/** Tailwind lg breakpoint. Below it the 3D canvas is not mounted. */
export const LG_MIN_PX = 1024;

/** True once the viewport is at least lg (1024 px) wide. Below that the 3D canvas is not mounted. */
export function useWideViewport(minPx = LG_MIN_PX): boolean | null {
  const [wide, setWide] = useState<boolean | null>(null);
  useEffect(() => {
    const mq = window.matchMedia(`(min-width: ${minPx}px)`);
    const on = () => setWide(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [minPx]);
  return wide;
}

/** Numeric overlay: the true values, plus the exaggeration label. Rendered with or without the canvas. */
export function AttitudeReadout({ result, index }: AttitudeModel3DProps) {
  const a = attitudeAt(result, index);
  if (!a) return <EmptyState kind="not_run" reason="No 7-DOF heave, roll and pitch series." />;
  return (
    <dl data-testid="attitude-readout" className="v2-num grid grid-cols-3 gap-2 text-xs text-zinc-200 m-0">
      <div><dt className="text-[#8a909a]">Heave (true)</dt><dd className="m-0" data-heave={a.heave_mm.toFixed(4)}>{a.heave_mm.toFixed(2)} mm</dd></div>
      <div><dt className="text-[#8a909a]">Roll (true)</dt><dd className="m-0" data-roll={a.roll_deg.toFixed(5)}>{a.roll_deg.toFixed(3)}°</dd></div>
      <div><dt className="text-[#8a909a]">Pitch (true)</dt><dd className="m-0" data-pitch={a.pitch_deg.toFixed(5)}>{a.pitch_deg.toFixed(3)}°</dd></div>
      <div className="col-span-3 text-[#C8F04B]" data-testid="exaggeration-label">Model drawn with ×{ATTITUDE_EXAGGERATION} exaggeration. Signs follow the solver output.</div>
    </dl>
  );
}

/**
 * Platform pose from the 7-DOF series: heave, roll and pitch, drawn x10. One canvas.
 * The box size is a fixed schematic, not a vehicle dimension.
 */
export default function AttitudeModel3D({ result, index, loadParams }: AttitudeModel3DProps) {
  const wide = useWideViewport();
  const a = attitudeAt(result, index);
  if (!a) return <AttitudeReadout result={result} index={index} />;
  const pose = exaggeratedPose(a);
  const rad = Math.PI / 180;
  return (
    <div data-testid="attitude-model">
      {wide ? (
        <div className="h-[220px] border border-white/10">
          <Canvas camera={{ position: [3.2, 2.2, 3.2], fov: 35 }} dpr={[1, 1.5]}>
            <ambientLight intensity={0.8} />
            <directionalLight position={[3, 5, 2]} intensity={0.8} />
            <gridHelper args={[6, 12, "#2a3036", "#1a2026"]} />
            {/* Scene units: 1 unit = 1 m for heave. Pitch about Z, roll about X (schematic axes). */}
            <mesh position={[0, 0.5 + pose.heave_mm / 1000, 0]} rotation={[pose.roll_deg * rad, 0, pose.pitch_deg * rad]}>
              <boxGeometry args={[2.4, 0.3, 1.2]} />
              <meshStandardMaterial color="#C8F04B" wireframe />
            </mesh>
          </Canvas>
        </div>
      ) : (
        <div data-testid="attitude-2d-fallback">
          {loadParams ? <FourFootprintsSVG result={result} params={loadParams} index={index} /> : null}
        </div>
      )}
      <AttitudeReadout result={result} index={index} />
    </div>
  );
}
