"use client";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Grid, Environment } from "@react-three/drei";
import { useRef } from "react";
import * as THREE from "three";

interface RigProps {
  zs?: number | number[];
  pitch?: number | number[];
  roll?: number | number[];
  zu_fl?: number | number[];
  zu_fr?: number | number[];
  zu_rl?: number | number[];
  zu_rr?: number | number[];
  isPlaying?: boolean;
  playbackSpeed?: number;
}

function getVal(val: number | number[] | undefined, index: number): number {
  if (val === undefined) return 0;
  if (typeof val === 'number') return val;
  if (val.length === 0) return 0;
  return val[index % val.length];
}

function CarModel({ zs = 0, pitch = 0, roll = 0, zu_fl = 0, zu_fr = 0, zu_rl = 0, zu_rr = 0, isPlaying = true, playbackSpeed = 1 }: RigProps) {
  const chassisRef = useRef<THREE.Group>(null!);
  const flRef = useRef<THREE.Mesh>(null!);
  const frRef = useRef<THREE.Mesh>(null!);
  const rlRef = useRef<THREE.Mesh>(null!);
  const rrRef = useRef<THREE.Mesh>(null!);
  const timeRef = useRef(0);
  
  useFrame((_, delta) => {
    if (isPlaying) {
      timeRef.current += delta * playbackSpeed;
    }
    // Assuming 50fps (20ms per frame)
    const index = Math.floor(timeRef.current * 50);

    const v_zs = getVal(zs, index);
    const v_pitch = getVal(pitch, index);
    const v_roll = getVal(roll, index);
    const v_zu_fl = getVal(zu_fl, index);
    const v_zu_fr = getVal(zu_fr, index);
    const v_zu_rl = getVal(zu_rl, index);
    const v_zu_rr = getVal(zu_rr, index);

    const alpha = 1 - Math.exp(-8 * delta);
    
    if (chassisRef.current) {
      chassisRef.current.position.y = THREE.MathUtils.lerp(chassisRef.current.position.y, 2 + v_zs * 10, alpha);
      chassisRef.current.rotation.x = THREE.MathUtils.lerp(chassisRef.current.rotation.x, v_pitch * -2, alpha);
      chassisRef.current.rotation.z = THREE.MathUtils.lerp(chassisRef.current.rotation.z, v_roll * 2, alpha);
    }
    
    if (flRef.current) flRef.current.position.y = THREE.MathUtils.lerp(flRef.current.position.y, 1.5 + v_zu_fl * 10, alpha);
    if (frRef.current) frRef.current.position.y = THREE.MathUtils.lerp(frRef.current.position.y, 1.5 + v_zu_fr * 10, alpha);
    if (rlRef.current) rlRef.current.position.y = THREE.MathUtils.lerp(rlRef.current.position.y, 1.5 + v_zu_rl * 10, alpha);
    if (rrRef.current) rrRef.current.position.y = THREE.MathUtils.lerp(rrRef.current.position.y, 1.5 + v_zu_rr * 10, alpha);
  });

  return (
    <group>
      {/* Chassis */}
      <group ref={chassisRef} position={[0, 2, 0]}>
        <mesh>
          <boxGeometry args={[3, 0.5, 6]} />
          <meshStandardMaterial color="#222" metalness={0.8} roughness={0.2} />
        </mesh>
      </group>
      
      {/* Wheels */}
      <mesh ref={flRef} position={[-1.6, 1.5, -2]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      <mesh ref={frRef} position={[1.6, 1.5, -2]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      <mesh ref={rlRef} position={[-1.6, 1.5, 2]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      <mesh ref={rrRef} position={[1.6, 1.5, 2]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
    </group>
  );
}

function describeRig(props: RigProps): string {
  const last = (v: number | number[] | undefined): number =>
    typeof v === "number" ? v : Array.isArray(v) && v.length > 0 ? v[v.length - 1] : 0;
  const mm = (m: number | number[] | undefined) => `${(last(m) * 1000).toFixed(0)} mm`;
  const deg = (a: number) => `${(a * (180 / Math.PI)).toFixed(1)} degrees`;
  return (
    `Interactive 3D suspension rig. Chassis heave ${mm(props.zs)}, ` +
    `pitch ${deg(last(props.pitch))}, roll ${deg(last(props.roll))}. ` +
    `Wheel travel — front left ${mm(props.zu_fl)}, front right ${mm(props.zu_fr)}, ` +
    `rear left ${mm(props.zu_rl)}, rear right ${mm(props.zu_rr)}.`
  );
}

export default function SuspensionRig3D(props: RigProps) {
  return (
    <div
      role="img"
      aria-label={describeRig(props)}
      className="h-full w-full"
    >
      {/* Screen-reader fallback: the live KPI/plot panels carry the same data;
          this label summarises the current rig state for non-visual users. */}
      <Canvas camera={{ position: [5, 4, 8], fov: 45 }} gl={{ alpha: true }}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 5]} intensity={1} castShadow />
        <Environment preset="city" />

        <CarModel {...props} />

        <Grid infiniteGrid fadeDistance={20} sectionColor="#444" cellColor="#333" />
        <OrbitControls enablePan={false} maxPolarAngle={Math.PI / 2 - 0.05} minDistance={4} maxDistance={20} />
      </Canvas>
    </div>
  );
}
