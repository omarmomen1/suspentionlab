"use client";

/**
 * LandingHero3D: self-contained interactive double-wishbone canvas for the landing page.
 *
 * Honesty notes (also printed in the UI):
 * - Geometry is the repo's default formula-car right-front hardpoint set (same numbers as
 *   DEFAULT_HP in app/kinematics/page.tsx), in SAE J670 mm: +X forward, +Y outboard, +Z up.
 * - Motion is a planar FRONT-VIEW (Y-Z) rigid-link solve done in this file. It is a schematic,
 *   NOT the backend kinematics solver, and it prints no solver KPIs.
 * - Mount it with next/dynamic(..., { ssr: false }). At most one canvas per route.
 */

import React, { useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";

type P2 = [number, number]; // [y, z] in mm (front view)

export const HERO_ACCENT = "#C8F04B";
export const HERO_BG = "#0C0F12";

export interface HeroGeometry {
  uwi: P2; // upper inboard (mean of fwd/aft)
  uwo: P2;
  lwi: P2;
  lwo: P2;
  tri: P2;
  tro: P2;
  wc: P2;
  cp: P2;
}

/** Right-front default hardpoints from app/kinematics/page.tsx, collapsed to the Y-Z plane. */
export const DEFAULT_HERO_GEOMETRY: HeroGeometry = {
  uwi: [80, 300],
  uwo: [650, 295],
  lwi: [80, 155],
  lwo: [720, 145],
  tri: [150, 220],
  tro: [710, 205],
  wc: [760, 220],
  cp: [760, 0],
};

const dist = (a: P2, b: P2) => Math.hypot(a[0] - b[0], a[1] - b[1]);

/** Rotate point p about pivot c by angle a (rad). */
function rot(p: P2, c: P2, a: number): P2 {
  const dy = p[0] - c[0], dz = p[1] - c[1];
  const ca = Math.cos(a), sa = Math.sin(a);
  return [c[0] + dy * ca - dz * sa, c[1] + dy * sa + dz * ca];
}

/** Circle-circle intersection; returns the intersection nearest to `near`, or null if none. */
function circleIntersect(c0: P2, r0: number, c1: P2, r1: number, near: P2): P2 | null {
  const d = dist(c0, c1);
  if (d > r0 + r1 || d < Math.abs(r0 - r1) || d === 0) return null;
  const a = (r0 * r0 - r1 * r1 + d * d) / (2 * d);
  const h2 = r0 * r0 - a * a;
  if (h2 < 0) return null;
  const h = Math.sqrt(h2);
  const mx = c0[0] + (a * (c1[0] - c0[0])) / d, mz = c0[1] + (a * (c1[1] - c0[1])) / d;
  const ox = (h * (c1[1] - c0[1])) / d, oz = (h * (c1[0] - c0[0])) / d;
  const A: P2 = [mx + ox, mz - oz], B: P2 = [mx - ox, mz + oz];
  return dist(A, near) <= dist(B, near) ? A : B;
}

/**
 * Solve the front-view linkage for a given lower-arm rotation (rad, + = outboard end up = bump).
 * Upright is rigid: the upper ball joint lies on the circle about the upper inboard pivot,
 * at the fixed upright distance from the lower ball joint. Returns null if the pose is unreachable.
 */
export function solvePose(g: HeroGeometry, lowerArmRad: number) {
  const lwo = rot(g.lwo, g.lwi, lowerArmRad);
  const uwo = circleIntersect(g.uwi, dist(g.uwi, g.uwo), lwo, dist(g.lwo, g.uwo), g.uwo);
  if (!uwo) return null;
  // Rigid-body transform of the upright from the rest pose (translation + rotation about LWO).
  const a0 = Math.atan2(g.uwo[1] - g.lwo[1], g.uwo[0] - g.lwo[0]);
  const a1 = Math.atan2(uwo[1] - lwo[1], uwo[0] - lwo[0]);
  const da = a1 - a0;
  const move = (p: P2): P2 => {
    const q = rot(p, g.lwo, da);
    return [q[0] + (lwo[0] - g.lwo[0]), q[1] + (lwo[1] - g.lwo[1])];
  };
  return { lwo, uwo, tro: move(g.tro), wc: move(g.wc), cp: move(g.cp), uprightRad: da };
}

/** Wheel-center vertical travel [mm] for a lower-arm rotation, relative to rest. */
export function wheelTravelMm(g: HeroGeometry, lowerArmRad: number): number | null {
  const s = solvePose(g, lowerArmRad);
  return s ? s.wc[1] - g.wc[1] : null;
}

const toV3 = (p: P2, x = 0) => new THREE.Vector3(p[0] * 0.001, p[1] * 0.001, x);

function Link({ a, b, r = 0.007, color = "#8a909a" }: { a: THREE.Vector3; b: THREE.Vector3; r?: number; color?: string }) {
  const { pos, quat, len } = useMemo(() => {
    const d = new THREE.Vector3().subVectors(b, a);
    const l = d.length();
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.clone().normalize());
    return { pos: new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5), quat: q, len: l };
  }, [a, b]);
  return (
    <mesh position={pos} quaternion={quat}>
      <cylinderGeometry args={[r, r, len, 10]} />
      <meshBasicMaterial color={color} />
    </mesh>
  );
}

function Joint({ p, color = HERO_ACCENT }: { p: THREE.Vector3; color?: string }) {
  return (
    <mesh position={p}>
      <sphereGeometry args={[0.014, 14, 14]} />
      <meshBasicMaterial color={color} />
    </mesh>
  );
}

function Rig({ g, travelMm, reduced }: { g: HeroGeometry; travelMm: number; reduced: boolean }) {
  const group = useRef<THREE.Group>(null);
  const [angle, setAngle] = useState(0);
  const t = useRef(0);
  const maxRad = useMemo(() => {
    // Largest symmetric lower-arm rotation that stays reachable and gives about +-travelMm of wheel travel.
    let lo = 0;
    for (let a = 0; a < 0.5; a += 0.002) {
      const w = wheelTravelMm(g, a), w2 = wheelTravelMm(g, -a);
      if (w === null || w2 === null || Math.abs(w) > travelMm || Math.abs(w2) > travelMm) break;
      lo = a;
    }
    return lo;
  }, [g, travelMm]);

  useFrame((_, dt) => {
    if (reduced) return;
    t.current += dt;
    setAngle(Math.sin(t.current * 1.1) * maxRad);
    if (group.current) group.current.rotation.y = -0.55 + Math.sin(t.current * 0.2) * 0.12;
  });

  const pose = solvePose(g, angle) ?? solvePose(g, 0)!;
  const L = (p: P2, z: number) => toV3(p, z);
  const zf = 0.08, za = -0.08; // fore/aft arm legs are drawn at +-80 mm for depth only
  const tireR = 0.33;
  return (
    <group ref={group} position={[-0.35, -0.1, 0]}>
      {/* chassis pickup bar (fixed) */}
      <Link a={L(g.uwi, zf)} b={L(g.lwi, zf)} color="#2a3036" r={0.01} />
      <Link a={L(g.uwi, za)} b={L(g.lwi, za)} color="#2a3036" r={0.01} />
      {/* upper wishbone */}
      <Link a={L(g.uwi, zf)} b={L(pose.uwo, 0)} />
      <Link a={L(g.uwi, za)} b={L(pose.uwo, 0)} />
      {/* lower wishbone */}
      <Link a={L(g.lwi, zf)} b={L(pose.lwo, 0)} />
      <Link a={L(g.lwi, za)} b={L(pose.lwo, 0)} />
      {/* upright and tie rod */}
      <Link a={L(pose.lwo, 0)} b={L(pose.uwo, 0)} r={0.012} color="#e4e6e8" />
      <Link a={L(g.tri, 0)} b={L(pose.tro, 0)} color={HERO_ACCENT} r={0.005} />
      {/* wheel: ring at wheel center, contact patch below */}
      <group position={L(pose.wc, 0)} rotation={[0, 0, 0]}>
        <mesh rotation={[0, Math.PI / 2, 0]}>
          <torusGeometry args={[tireR, 0.004, 8, 64]} />
          <meshBasicMaterial color="#e4e6e8" />
        </mesh>
      </group>
      {[g.uwi, g.lwi].flatMap((p, i) => [zf, za].map((z, j) => <Joint key={`${i}${j}`} p={L(p, z)} color="#e4e6e8" />))}
      <Joint p={L(pose.uwo, 0)} />
      <Joint p={L(pose.lwo, 0)} />
      <Joint p={L(pose.wc, 0)} />
      <Joint p={L(pose.cp, 0)} color={HERO_ACCENT} />
      {/* ground line */}
      <Link a={toV3([-100, -0], -0.5)} b={toV3([1000, 0], -0.5)} color="#2a3036" r={0.003} />
    </group>
  );
}

export interface LandingHero3DProps {
  geometry?: HeroGeometry;
  /** Peak wheel travel the animation aims for, mm. */
  travelMm?: number;
  className?: string;
}

export default function LandingHero3D({ geometry = DEFAULT_HERO_GEOMETRY, travelMm = 50, className }: LandingHero3DProps) {
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  return (
    <figure data-testid="landing-hero-3d" className={className} style={{ margin: 0, background: HERO_BG, border: "1px solid rgba(255,255,255,0.10)" }}>
      <div style={{ height: 360 }}>
        <Canvas camera={{ position: [0.2, 0.35, 1.9], fov: 38 }} dpr={[1, 1.75]} gl={{ antialias: true }}>
          <color attach="background" args={[HERO_BG]} />
          <Rig g={geometry} travelMm={travelMm} reduced={!!reduced} />
          <OrbitControls enablePan={false} enableZoom={false} minPolarAngle={0.9} maxPolarAngle={1.8} />
        </Canvas>
      </div>
      <figcaption className="v2-num" style={{ fontSize: 11, color: "#8a909a", padding: "8px 12px", borderTop: "1px solid rgba(255,255,255,0.10)" }}>
        Schematic double-wishbone, front view, default formula-car hardpoints. Animated bump and droop of about +/-{travelMm} mm. Not a solver output.
      </figcaption>
    </figure>
  );
}
