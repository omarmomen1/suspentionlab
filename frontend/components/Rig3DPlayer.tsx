"use client";

/**
 * Rig3DPlayer (P1-PERF-02) — self-contained animation driver for the 3D rig.
 *
 * Owns the playback timer and frame state internally so the 1248-line parent
 * dashboard does NOT re-render at 50 fps. The parent passes only the result
 * arrays; everything frame-related stays inside this component.
 */

import { useEffect, useRef, useState } from "react";
import SuspensionRig3D from "./SuspensionRig3D";

interface Rig3DPlayerProps {
  z_s: number[];
  z_u: number[];
}

export default function Rig3DPlayer({ z_s, z_u }: Rig3DPlayerProps) {
  const [frame, setFrame] = useState(0);
  const n = Math.min(z_s.length, z_u.length);

  // Keep latest arrays without restarting the timer on every simulation.
  const dataRef = useRef({ z_s, z_u, n });
  dataRef.current = { z_s, z_u, n };

  useEffect(() => {
    setFrame(0);
    const id = setInterval(() => {
      setFrame((prev) => (prev + 1) % Math.max(dataRef.current.n, 1));
    }, 20); // 50 fps — contained entirely within this subtree
    return () => clearInterval(id);
  }, [n > 0]);

  const i = n > 0 ? frame % n : 0;
  const zs = z_s[i] ?? 0;
  const zu = z_u[i] ?? 0;

  return (
    <SuspensionRig3D zs={zs} zu_fl={zu} zu_fr={zu} zu_rl={zu} zu_rr={zu} />
  );
}
