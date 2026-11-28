"use client";

import React, { useRef, useState, useMemo, useEffect } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Grid, Text } from "@react-three/drei";
import * as THREE from "three";
import {
  Camera,
  Layers,
  RotateCcw,
  Eye,
  Info,
  Compass,
  Check,
  Maximize2,
} from "lucide-react";

// ─── Types & Coordinate Helpers ───────────────────────────────────────────────
export type Vec3 = [number, number, number];

export interface KinematicsGeometryMap {
  UWI_fwd?: Vec3;
  UWI_aft?: Vec3;
  UWO?: Vec3;
  LWI_fwd?: Vec3;
  LWI_aft?: Vec3;
  LWO?: Vec3;
  TRI?: Vec3;
  TRO?: Vec3;
  WC?: Vec3;
  CP?: Vec3;
  PRI?: Vec3;
  PRO?: Vec3;
  ic_fv?: Vec3;
  ic_sv?: Vec3;
  rc?: Vec3;
  steering_pierce?: Vec3;
  wheel_top?: Vec3;
  wheel_bottom?: Vec3;
  [key: string]: Vec3 | undefined;
}

export interface SuspensionKinematics3DProps {
  geometry: KinematicsGeometryMap;
  camberDeg?: number;
  toeDeg?: number;
  rollCenterHeightMm?: number;
  scrubRadiusMm?: number;
  tireRadiusM?: number;
  hoveredNode?: string | null;
  onHoverNode?: (nodeName: string | null) => void;
  className?: string;
}

/**
 * Coordinate mapping: SAE J670 (mm) to Three.js (m)
 * SAE J670: +X = forward, +Y = outboard (right), +Z = up
 * Three.js:  x = +Y (outboard), y = +Z (up), z = +X (forward)
 */
function saeToThree(sae: Vec3 | undefined, fallback: Vec3 = [0, 0, 0]): THREE.Vector3 {
  if (!sae || sae.length < 3) return new THREE.Vector3(fallback[1] * 0.001, fallback[2] * 0.001, fallback[0] * 0.001);
  return new THREE.Vector3(sae[1] * 0.001, sae[2] * 0.001, sae[0] * 0.001);
}

// ─── 3D Cylinder Link Component ───────────────────────────────────────────────
function CylinderLink({
  start,
  end,
  radius = 0.008,
  color = "#94a3b8",
  metalness = 0.8,
  roughness = 0.25,
  opacity = 1.0,
  transparent = false,
}: {
  start: THREE.Vector3;
  end: THREE.Vector3;
  radius?: number;
  color?: string;
  metalness?: number;
  roughness?: number;
  opacity?: number;
  transparent?: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const distance = start.distanceTo(end);

  const { position, quaternion } = useMemo(() => {
    const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);
    const dir = new THREE.Vector3().subVectors(end, start).normalize();
    const up = new THREE.Vector3(0, 1, 0);
    const q = new THREE.Quaternion().setFromUnitVectors(up, dir);
    return { position: mid, quaternion: q };
  }, [start, end]);

  if (distance < 0.0001) return null;

  return (
    <mesh ref={meshRef} position={position} quaternion={quaternion}>
      <cylinderGeometry args={[radius, radius, distance, 16]} />
      <meshStandardMaterial
        color={color}
        metalness={metalness}
        roughness={roughness}
        opacity={opacity}
        transparent={transparent}
      />
    </mesh>
  );
}

// ─── 3D Spherical Node Component ──────────────────────────────────────────────
function SphericalNode({
  position,
  radius = 0.014,
  color = "#38bdf8",
  name,
  label,
  isHovered = false,
  onHover,
}: {
  position: THREE.Vector3;
  radius?: number;
  color?: string;
  name: string;
  label?: string;
  isHovered?: boolean;
  onHover?: (name: string | null) => void;
}) {
  const effectiveRadius = isHovered ? radius * 1.5 : radius;
  const effectiveColor = isHovered ? "#38bdf8" : color;

  return (
    <group position={position}>
      <mesh
        onPointerOver={(e) => {
          e.stopPropagation();
          onHover?.(name);
        }}
        onPointerOut={(e) => {
          e.stopPropagation();
          onHover?.(null);
        }}
      >
        <sphereGeometry args={[effectiveRadius, 24, 24]} />
        <meshStandardMaterial
          color={effectiveColor}
          emissive={isHovered ? effectiveColor : "#000"}
          emissiveIntensity={isHovered ? 0.6 : 0.0}
          metalness={0.7}
          roughness={0.2}
        />
      </mesh>
      {isHovered && (
        <mesh>
          <sphereGeometry args={[effectiveRadius * 1.35, 16, 16]} />
          <meshBasicMaterial color="#38bdf8" wireframe transparent opacity={0.5} />
        </mesh>
      )}
    </group>
  );
}

// ─── 3D Dashed / Solid Construction Line ──────────────────────────────────────
function ConstructionLine({
  start,
  end,
  color = "#f59e0b",
  lineWidth = 2,
}: {
  start: THREE.Vector3;
  end: THREE.Vector3;
  color?: string;
  lineWidth?: number;
}) {
  const lineRef = useRef<THREE.Line>(null);

  const geometry = useMemo(() => {
    const geom = new THREE.BufferGeometry().setFromPoints([start, end]);
    return geom;
  }, [start, end]);

  return (
    // @ts-ignore - Three.js line primitive
    <primitive object={new THREE.Line(geometry, new THREE.LineBasicMaterial({ color, linewidth: lineWidth, transparent: true, opacity: 0.85 }))} />
  );
}

// ─── Wheel & Tire 3D Assembly ─────────────────────────────────────────────────
function TireAssembly({
  wc,
  camberDeg = 0,
  toeDeg = 0,
  tireRadiusM = 0.33,
  tireWidthM = 0.23,
  isHovered = false,
  onHover,
}: {
  wc: THREE.Vector3;
  camberDeg?: number;
  toeDeg?: number;
  tireRadiusM?: number;
  tireWidthM?: number;
  isHovered?: boolean;
  onHover?: (name: string | null) => void;
}) {
  // Convert camber & toe to radians
  // In our coordinates:
  // Outboard = +X, Up = +Y, Forward = +Z
  // Camber: tilt around Z (forward axis). Negative camber tilts top towards -X (inboard).
  // Toe: steer around Y (upward axis). Toe-in steers front towards -X (inboard).
  const camberRad = (camberDeg * Math.PI) / 180.0;
  const toeRad = (toeDeg * Math.PI) / 180.0;

  // Base orientation: cylinder axis is Y. Rotate 90 deg around Z to align axis with X (outboard).
  const groupRef = useRef<THREE.Group>(null);

  return (
    <group
      ref={groupRef}
      position={wc}
      rotation={[camberRad, toeRad, 0]}
      onPointerOver={(e) => {
        e.stopPropagation();
        onHover?.("WC");
      }}
      onPointerOut={(e) => {
        e.stopPropagation();
        onHover?.(null);
      }}
    >
      {/* Outer Tire Tread */}
      <mesh rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[tireRadiusM, tireRadiusM, tireWidthM, 36]} />
        <meshStandardMaterial
          color="#18181c"
          roughness={0.9}
          metalness={0.05}
          wireframe={isHovered}
        />
      </mesh>

      {/* Wheel Rim / Hub */}
      <mesh rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[tireRadiusM * 0.55, tireRadiusM * 0.55, tireWidthM + 0.005, 24]} />
        <meshStandardMaterial color="#334155" roughness={0.3} metalness={0.9} />
      </mesh>

      {/* Center Spindle Cap */}
      <mesh rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.035, 0.035, tireWidthM + 0.02, 16]} />
        <meshStandardMaterial color="#38bdf8" roughness={0.2} metalness={0.8} />
      </mesh>
    </group>
  );
}

// ─── Camera Controller Preset Manager ─────────────────────────────────────────
function CameraPresetController({
  preset,
  controlsRef,
}: {
  preset: "iso" | "front" | "side" | "top";
  controlsRef: React.RefObject<any>;
}) {
  const { camera } = useThree();

  useEffect(() => {
    const target = new THREE.Vector3(0.45, 0.22, 0.0);
    if (controlsRef.current) {
      controlsRef.current.target.copy(target);
    }

    if (preset === "iso") {
      camera.position.set(1.5, 0.9, 1.4);
    } else if (preset === "front") {
      // Look from front (+Z in Three.js = +X forward in SAE) straight toward the suspension
      camera.position.set(0.45, 0.25, 2.3);
    } else if (preset === "side") {
      // Look from outboard (+X in Three.js = +Y outboard in SAE)
      camera.position.set(2.4, 0.25, 0.0);
    } else if (preset === "top") {
      // Look from top (+Y in Three.js = +Z up in SAE)
      camera.position.set(0.45, 2.4, 0.0);
    }
    camera.lookAt(target);
    if (controlsRef.current) {
      controlsRef.current.update();
    }
  }, [preset, camera, controlsRef]);

  return null;
}

// ─── Main Suspension Kinematics Scene ─────────────────────────────────────────
function SuspensionScene({
  geometry,
  camberDeg = 0,
  toeDeg = 0,
  tireRadiusM = 0.33,
  showIC = true,
  showRC = true,
  showSteering = true,
  showGround = true,
  hoveredNode,
  onHoverNode,
  preset,
  controlsRef,
}: {
  geometry: KinematicsGeometryMap;
  camberDeg?: number;
  toeDeg?: number;
  tireRadiusM?: number;
  showIC: boolean;
  showRC: boolean;
  showSteering: boolean;
  showGround: boolean;
  hoveredNode?: string | null;
  onHoverNode?: (name: string | null) => void;
  preset: "iso" | "front" | "side" | "top";
  controlsRef: React.RefObject<any>;
}) {
  // Convert nodal coordinates
  const pUWI_fwd = saeToThree(geometry.UWI_fwd, [-50, 80, 300]);
  const pUWI_aft = saeToThree(geometry.UWI_aft, [50, 80, 300]);
  const pUWO     = saeToThree(geometry.UWO, [0, 650, 295]);

  const pLWI_fwd = saeToThree(geometry.LWI_fwd, [-80, 80, 155]);
  const pLWI_aft = saeToThree(geometry.LWI_aft, [80, 80, 155]);
  const pLWO     = saeToThree(geometry.LWO, [0, 720, 145]);

  const pTRI     = saeToThree(geometry.TRI, [0, 150, 220]);
  const pTRO     = saeToThree(geometry.TRO, [-15, 710, 205]);

  const pWC      = saeToThree(geometry.WC, [0, 760, 220]);
  const pCP      = saeToThree(geometry.CP, [0, 760, 0]);

  const pPRI     = saeToThree(geometry.PRI, [-20, 300, 390]);
  const pPRO     = saeToThree(geometry.PRO, [-15, 690, 250]);

  // True Kinematic Virtual Nodes (Null if absent or diverged)
  const pIC_fv   = geometry.ic_fv && geometry.ic_fv.length >= 3 && !isNaN(geometry.ic_fv[1]) && isFinite(geometry.ic_fv[1])
    ? saeToThree(geometry.ic_fv)
    : null;
  const pIC_sv   = geometry.ic_sv && geometry.ic_sv.length >= 3 && !isNaN(geometry.ic_sv[0]) && isFinite(geometry.ic_sv[0])
    ? saeToThree(geometry.ic_sv)
    : null;
  const pRC      = geometry.rc && geometry.rc.length >= 3 && !isNaN(geometry.rc[2]) && isFinite(geometry.rc[2])
    ? saeToThree(geometry.rc)
    : null;
  const pPierce  = geometry.steering_pierce && geometry.steering_pierce.length >= 3 && !isNaN(geometry.steering_pierce[1]) && isFinite(geometry.steering_pierce[1])
    ? saeToThree(geometry.steering_pierce)
    : null;

  // Midpoints for wishbones to IC construction lines
  const uwi_mid = new THREE.Vector3().addVectors(pUWI_fwd, pUWI_aft).multiplyScalar(0.5);
  const lwi_mid = new THREE.Vector3().addVectors(pLWI_fwd, pLWI_aft).multiplyScalar(0.5);

  return (
    <>
      <CameraPresetController preset={preset} controlsRef={controlsRef} />

      {/* Lighting */}
      {/* Brighter rig lighting so wishbones and axes read crisply on dark mode */}
      <ambientLight intensity={0.95} />
      <directionalLight position={[5, 8, 5]} intensity={1.7} castShadow />
      <directionalLight position={[-5, -2, -5]} intensity={0.75} color="#60a5fa" />
      <directionalLight position={[0, -6, 3]} intensity={0.35} color="#f2a900" />

      {/* Ground plane & Vehicle Centerline */}
      {showGround && (
        <group>
          {/* Ground Plane Grid (Z = 0) */}
          <Grid
            position={[0.5, 0, 0]}
            args={[3.5, 3.5]}
            cellSize={0.1}
            cellThickness={0.8}
            cellColor="#1e293b"
            sectionSize={0.5}
            sectionThickness={1.2}
            sectionColor="#334155"
            fadeDistance={6}
          />
          {/* Centerline Plane Marker (Y = 0) */}
          <mesh position={[0, 0.3, 0]}>
            <planeGeometry args={[0.002, 0.6]} />
            <meshBasicMaterial color="#ef4444" transparent opacity={0.6} side={THREE.DoubleSide} />
          </mesh>
        </group>
      )}

      {/* ── 1. Upper Wishbone (Red/Rose A-arm) ──────────────────────────────── */}
      <group>
        <CylinderLink start={pUWI_fwd} end={pUWO} radius={0.008} color="#f43f5e" metalness={0.7} />
        <CylinderLink start={pUWI_aft} end={pUWO} radius={0.008} color="#f43f5e" metalness={0.7} />
        <CylinderLink start={pUWI_fwd} end={pUWI_aft} radius={0.007} color="#9f1239" metalness={0.6} />

        <SphericalNode position={pUWI_fwd} radius={0.013} color="#f43f5e" name="UWI_fwd" isHovered={hoveredNode === "UWI_fwd"} onHover={onHoverNode} />
        <SphericalNode position={pUWI_aft} radius={0.013} color="#f43f5e" name="UWI_aft" isHovered={hoveredNode === "UWI_aft"} onHover={onHoverNode} />
        <SphericalNode position={pUWO} radius={0.016} color="#fda4af" name="UWO" isHovered={hoveredNode === "UWO"} onHover={onHoverNode} />
      </group>

      {/* ── 2. Lower Wishbone (Cyan/Blue A-arm) ──────────────────────────────── */}
      <group>
        <CylinderLink start={pLWI_fwd} end={pLWO} radius={0.010} color="#06b6d4" metalness={0.7} />
        <CylinderLink start={pLWI_aft} end={pLWO} radius={0.010} color="#06b6d4" metalness={0.7} />
        <CylinderLink start={pLWI_fwd} end={pLWI_aft} radius={0.008} color="#0891b2" metalness={0.6} />

        <SphericalNode position={pLWI_fwd} radius={0.014} color="#06b6d4" name="LWI_fwd" isHovered={hoveredNode === "LWI_fwd"} onHover={onHoverNode} />
        <SphericalNode position={pLWI_aft} radius={0.014} color="#06b6d4" name="LWI_aft" isHovered={hoveredNode === "LWI_aft"} onHover={onHoverNode} />
        <SphericalNode position={pLWO} radius={0.018} color="#67e8f9" name="LWO" isHovered={hoveredNode === "LWO"} onHover={onHoverNode} />
      </group>

      {/* ── 3. Upright / Knuckle Assembly ──────────────────────────────────── */}
      <group>
        {/* Main Kingpin Carrier link: UWO to LWO */}
        <CylinderLink start={pUWO} end={pLWO} radius={0.015} color="#cbd5e1" metalness={0.9} roughness={0.15} />
        {/* Hub spindle arm: LWO to WC and UWO to WC */}
        <CylinderLink start={pLWO} end={pWC} radius={0.012} color="#94a3b8" metalness={0.8} />
        <CylinderLink start={pUWO} end={pWC} radius={0.012} color="#94a3b8" metalness={0.8} />
        {/* Steering arm: Upright to TRO */}
        <CylinderLink start={pLWO} end={pTRO} radius={0.011} color="#64748b" metalness={0.8} />
        {pPRO && <CylinderLink start={pLWO} end={pPRO} radius={0.010} color="#64748b" metalness={0.8} />}

        <SphericalNode position={pWC} radius={0.018} color="#e2e8f0" name="WC" isHovered={hoveredNode === "WC"} onHover={onHoverNode} />
      </group>

      {/* ── 4. Steering Tie Rod (Emerald) ───────────────────────────────────── */}
      <group>
        <CylinderLink start={pTRI} end={pTRO} radius={0.008} color="#10b981" metalness={0.8} />
        <SphericalNode position={pTRI} radius={0.013} color="#10b981" name="TRI" isHovered={hoveredNode === "TRI"} onHover={onHoverNode} />
        <SphericalNode position={pTRO} radius={0.014} color="#34d399" name="TRO" isHovered={hoveredNode === "TRO"} onHover={onHoverNode} />
      </group>

      {/* ── 5. Pushrod / Damper Link (Amber) ────────────────────────────────── */}
      <group>
        <CylinderLink start={pPRO} end={pPRI} radius={0.011} color="#f59e0b" metalness={0.85} roughness={0.2} />
        <SphericalNode position={pPRI} radius={0.014} color="#f59e0b" name="PRI" isHovered={hoveredNode === "PRI"} onHover={onHoverNode} />
        <SphericalNode position={pPRO} radius={0.014} color="#fbbf24" name="PRO" isHovered={hoveredNode === "PRO"} onHover={onHoverNode} />
      </group>

      {/* ── 6. Wheel & Tire Assembly ────────────────────────────────────────── */}
      <TireAssembly
        wc={pWC}
        camberDeg={camberDeg}
        toeDeg={toeDeg}
        tireRadiusM={tireRadiusM}
        isHovered={hoveredNode === "WC" || hoveredNode === "CP"}
        onHover={onHoverNode}
      />
      <SphericalNode position={pCP} radius={0.014} color="#eab308" name="CP" isHovered={hoveredNode === "CP"} onHover={onHoverNode} />

      {/* ── 7. Kinematic Construction Overlays ──────────────────────────────── */}
      {/* Front Instant Center (IC_fv) & Extension Lines */}
      {showIC && pIC_fv && (
        <group>
          {/* Upper wishbone line to IC_fv */}
          <ConstructionLine start={uwi_mid} end={pIC_fv} color="#fb7185" lineWidth={1.5} />
          {/* Lower wishbone line to IC_fv */}
          <ConstructionLine start={lwi_mid} end={pIC_fv} color="#22d3ee" lineWidth={1.5} />
          {/* Front Instant Center marker */}
          <SphericalNode position={pIC_fv} radius={0.020} color="#f43f5e" name="ic_fv" isHovered={hoveredNode === "ic_fv"} onHover={onHoverNode} />
        </group>
      )}

      {/* Roll Center (RC) construction: Line from Contact Patch (CP) through IC_fv to Centerline */}
      {showRC && pRC && pIC_fv && (
        <group>
          {/* Line from CP to IC_fv */}
          <ConstructionLine start={pCP} end={pIC_fv} color="#a855f7" lineWidth={2} />
          {/* Line from CP to Roll Center on vehicle centerline */}
          <ConstructionLine start={pCP} end={pRC} color="#c084fc" lineWidth={2.5} />
          {/* Roll Center Height vertical plumb line to ground */}
          <ConstructionLine start={pRC} end={new THREE.Vector3(pRC.x, 0, pRC.z)} color="#e879f9" lineWidth={1.5} />
          {/* Roll Center spherical diamond marker */}
          <mesh position={pRC}>
            <octahedronGeometry args={[0.025, 0]} />
            <meshStandardMaterial color="#c084fc" emissive="#a855f7" emissiveIntensity={0.6} />
          </mesh>
          <SphericalNode position={pRC} radius={0.018} color="#d8b4fe" name="rc" isHovered={hoveredNode === "rc"} onHover={onHoverNode} />
        </group>
      )}

      {/* Steering Kingpin Axis & Scrub Radius Overlay */}
      {showSteering && pPierce && (
        <group>
          {/* Kingpin line from UWO through LWO to ground piercing point */}
          <ConstructionLine start={pUWO} end={pPierce} color="#eab308" lineWidth={2} />
          {/* Ground piercing point marker */}
          <SphericalNode position={pPierce} radius={0.014} color="#eab308" name="steering_pierce" isHovered={hoveredNode === "steering_pierce"} onHover={onHoverNode} />
          {/* Scrub radius line on ground connecting piercing point to contact patch */}
          <ConstructionLine start={pPierce} end={pCP} color="#facc15" lineWidth={3} />
        </group>
      )}
    </>
  );
}

// ─── Human-readable Node Dictionary ──────────────────────────────────────────
const NODE_INFO: Record<string, { label: string; desc: string }> = {
  UWI_fwd: { label: "Upper Wishbone Inboard — Forward", desc: "Chassis forward pivot mounting point for upper A-arm." },
  UWI_aft: { label: "Upper Wishbone Inboard — Aft", desc: "Chassis aft pivot mounting point for upper A-arm." },
  UWO:     { label: "Upper Wishbone Outboard (Upper Ball Joint)", desc: "Upper ball joint spherical pivot on the upright/knuckle." },
  LWI_fwd: { label: "Lower Wishbone Inboard — Forward", desc: "Chassis forward pivot mounting point for lower A-arm." },
  LWI_aft: { label: "Lower Wishbone Inboard — Aft", desc: "Chassis aft pivot mounting point for lower A-arm." },
  LWO:     { label: "Lower Wishbone Outboard (Lower Ball Joint)", desc: "Lower ball joint spherical pivot on the upright/knuckle." },
  TRI:     { label: "Tie Rod Inboard (Rack End)", desc: "Steering rack outboard end pivot point." },
  TRO:     { label: "Tie Rod Outboard (Steering Arm)", desc: "Upright steering arm ball joint determining bump steer." },
  WC:      { label: "Wheel Center (Spindle Hub)", desc: "Wheel spindle rotation axis center." },
  CP:      { label: "Contact Patch (Tire/Road Interface)", desc: "Loaded tire contact centroid on the ground datum plane." },
  PRI:     { label: "Pushrod Inboard (Rocker Pivot)", desc: "Chassis/rocker interface point for pushrod suspension." },
  PRO:     { label: "Pushrod Outboard (Upright Mount)", desc: "Upright/wishbone mount for suspension spring/damper actuation." },
  ic_fv:   { label: "Front View Instant Center (IC_fv)", desc: "Instantaneous virtual swing center of the upright in front elevation." },
  ic_sv:   { label: "Side View Instant Center (IC_sv)", desc: "Instantaneous virtual pitch center determining anti-dive and anti-lift." },
  rc:      { label: "Roll Center (RC)", desc: "Instantaneous transverse roll axis piercing point on the vehicle centerline." },
  steering_pierce: { label: "Steering Axis Ground Piercing Point", desc: "Ground intersection of kingpin axis defining scrub radius." },
};

// ─── Root Component ───────────────────────────────────────────────────────────
export default function SuspensionKinematics3D({
  geometry,
  camberDeg = 0,
  toeDeg = 0,
  rollCenterHeightMm = 0,
  scrubRadiusMm = 0,
  tireRadiusM = 0.33,
  hoveredNode: externalHoveredNode,
  onHoverNode: externalOnHoverNode,
  className = "",
}: SuspensionKinematics3DProps) {
  const controlsRef = useRef<any>(null);
  const [preset, setPreset] = useState<"iso" | "front" | "side" | "top">("iso");
  const [internalHoveredNode, setInternalHoveredNode] = useState<string | null>(null);

  // Overlay visibility toggles
  const [showIC, setShowIC] = useState(true);
  const [showRC, setShowRC] = useState(true);
  const [showSteering, setShowSteering] = useState(true);
  const [showGround, setShowGround] = useState(true);

  const activeHoveredNode = externalHoveredNode !== undefined ? externalHoveredNode : internalHoveredNode;

  const handleHover = (name: string | null) => {
    setInternalHoveredNode(name);
    externalOnHoverNode?.(name);
  };

  const hoveredCoords = activeHoveredNode ? geometry[activeHoveredNode] : null;
  const hoveredInfo = activeHoveredNode ? NODE_INFO[activeHoveredNode] : null;

  return (
    <div className={`relative w-full h-[520px] rounded-xl overflow-hidden bg-[#07080a] border border-[#1e2029] select-none ${className}`}>
      {/* ── Top Bar: Camera Presets & Construction Overlay Toggles ─────────── */}
      <div className="absolute top-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        {/* Camera Presets */}
        <div className="flex items-center gap-1 bg-[#0f1118]/90 backdrop-blur-md border border-[#252836] p-1 rounded-lg pointer-events-auto shadow-lg">
          <button
            onClick={() => setPreset("iso")}
            className={`px-2.5 py-1 text-xs font-mono rounded transition-colors ${
              preset === "iso" ? "bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            Isometric
          </button>
          <button
            onClick={() => setPreset("front")}
            className={`px-2.5 py-1 text-xs font-mono rounded transition-colors ${
              preset === "front" ? "bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40" : "text-gray-400 hover:text-gray-200"
            }`}
            title="Front View (Camber, IC_fv, Roll Center)"
          >
            Front View
          </button>
          <button
            onClick={() => setPreset("side")}
            className={`px-2.5 py-1 text-xs font-mono rounded transition-colors ${
              preset === "side" ? "bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40" : "text-gray-400 hover:text-gray-200"
            }`}
            title="Side View (Anti-dive, Caster, IC_sv)"
          >
            Side View
          </button>
          <button
            onClick={() => setPreset("top")}
            className={`px-2.5 py-1 text-xs font-mono rounded transition-colors ${
              preset === "top" ? "bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40" : "text-gray-400 hover:text-gray-200"
            }`}
            title="Top Plan View (Toe, Ackermann)"
          >
            Top View
          </button>
        </div>

        {/* Kinematic Overlay Toggles */}
        <div className="flex items-center gap-1.5 bg-[#0f1118]/90 backdrop-blur-md border border-[#252836] px-2.5 py-1 rounded-lg pointer-events-auto shadow-lg">
          <span className="text-xs font-bold uppercase tracking-wider text-gray-400 mr-1 hidden sm:inline">
            Overlays:
          </span>
          <button
            onClick={() => setShowIC(!showIC)}
            className={`px-2 py-0.5 text-xs font-mono rounded border transition-colors ${
              showIC ? "bg-rose-950/60 border-rose-500/50 text-rose-300 font-semibold" : "bg-[#141620] border-transparent text-zinc-400"
            }`}
            title="Toggle Instant Centers (IC_fv, IC_sv)"
          >
            IC
          </button>
          <button
            onClick={() => setShowRC(!showRC)}
            className={`px-2 py-0.5 text-xs font-mono rounded border transition-colors ${
              showRC ? "bg-purple-950/60 border-purple-500/50 text-purple-300 font-semibold" : "bg-[#141620] border-transparent text-zinc-400"
            }`}
            title="Toggle Roll Center (RC)"
          >
            RC
          </button>
          <button
            onClick={() => setShowSteering(!showSteering)}
            className={`px-2 py-0.5 text-xs font-mono rounded border transition-colors ${
              showSteering ? "bg-amber-950/60 border-amber-500/50 text-amber-300 font-semibold" : "bg-[#141620] border-transparent text-zinc-400"
            }`}
            title="Toggle Steering Axis & Scrub Radius"
          >
            Steering
          </button>
          <button
            onClick={() => setShowGround(!showGround)}
            className={`px-2 py-0.5 text-xs font-mono rounded border transition-colors ${
              showGround ? "bg-cyan-950/60 border-cyan-500/50 text-cyan-300 font-semibold" : "bg-[#141620] border-transparent text-zinc-400"
            }`}
            title="Toggle Ground Grid Datum"
          >
            Datum
          </button>
        </div>
      </div>

      {/* ── 3D Canvas ───────────────────────────────────────────────────────── */}
      <Canvas
        camera={{ position: [1.5, 0.9, 1.4], fov: 42 }}
        gl={{ antialias: true, alpha: true }}
      >
        <SuspensionScene
          geometry={geometry}
          camberDeg={camberDeg}
          toeDeg={toeDeg}
          tireRadiusM={tireRadiusM}
          showIC={showIC}
          showRC={showRC}
          showSteering={showSteering}
          showGround={showGround}
          hoveredNode={activeHoveredNode}
          onHoverNode={handleHover}
          preset={preset}
          controlsRef={controlsRef}
        />
        <OrbitControls
          ref={controlsRef}
          enableDamping
          dampingFactor={0.08}
          maxPolarAngle={Math.PI / 2 + 0.1}
          minDistance={0.5}
          maxDistance={8}
        />
      </Canvas>

      {/* ── Bottom Floating HUD: Hover Coordinates & Coordinate Frame ─────── */}
      <div className="absolute bottom-3 left-3 right-3 z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 pointer-events-none">
        {/* Node Hover Tooltip HUD */}
        {activeHoveredNode && hoveredCoords ? (
          <div className="bg-[#0c0e15]/95 backdrop-blur-md border border-cyan-500/40 rounded-lg p-2.5 pointer-events-auto shadow-2xl max-w-md animate-in fade-in">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
              <span className="text-xs font-bold text-gray-100 font-mono">
                {activeHoveredNode}
              </span>
              <span className="text-xs text-gray-400">
                {hoveredInfo?.label || "Suspension Hardpoint"}
              </span>
            </div>
            <div className="mt-1.5 flex items-center gap-4 text-xs font-mono">
              <span className="text-gray-300">
                <strong className="text-cyan-400">X</strong> (fwd): {hoveredCoords[0] >= 0 ? `+${hoveredCoords[0].toFixed(1)}` : hoveredCoords[0].toFixed(1)} mm
              </span>
              <span className="text-gray-300">
                <strong className="text-cyan-400">Y</strong> (outboard): {hoveredCoords[1] >= 0 ? `+${hoveredCoords[1].toFixed(1)}` : hoveredCoords[1].toFixed(1)} mm
              </span>
              <span className="text-gray-300">
                <strong className="text-cyan-400">Z</strong> (up): {hoveredCoords[2] >= 0 ? `+${hoveredCoords[2].toFixed(1)}` : hoveredCoords[2].toFixed(1)} mm
              </span>
            </div>
            <div className="mt-1 text-xs text-zinc-400 font-mono">
              Coordinate Frame: SAE J670 (+X Forward, +Y Outboard, +Z Upward)
            </div>
          </div>
        ) : (
          <div className="bg-[#0c0e15]/80 backdrop-blur-md border border-[#222533] rounded-lg px-3 py-1.5 pointer-events-auto">
            <span className="text-xs text-gray-400 flex items-center gap-2">
              <Info className="w-3.5 h-3.5 text-cyan-500" />
              Hover any suspension joint or construction line for 3D coordinates
            </span>
          </div>
        )}

        {/* Legend / Coordinate Frame Indicator */}
        <div className="bg-[#0c0e15]/85 backdrop-blur-md border border-[#222533] px-3 py-1.5 rounded-lg flex items-center gap-3 text-xs font-mono text-gray-400 pointer-events-auto ml-auto">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-rose-500 inline-block" />
            <span>Upper A-Arm</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400 inline-block" />
            <span>Lower A-Arm</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
            <span>Tie Rod</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
            <span>Pushrod</span>
          </div>
        </div>
      </div>
    </div>
  );
}
