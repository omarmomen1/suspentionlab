"use client";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Grid, Environment } from "@react-three/drei";
import { useRef } from "react";
import * as THREE from "three";

interface SuspensionRigProps {
  times?: number[];
  zs?: number[];
  pitch?: number[];
  roll?: number[];
  zu?: number[];
  zuFL?: number[];
  zuFR?: number[];
  zuRL?: number[];
  zuRR?: number[];
  isFullCar?: boolean;
}

function RigModel({ data }: { data: SuspensionRigProps }) {
  const chassisRef = useRef<THREE.Group>(null!);
  const wheelFLRef = useRef<THREE.Mesh>(null!);
  const wheelFRRef = useRef<THREE.Mesh>(null!);
  const wheelRLRef = useRef<THREE.Mesh>(null!);
  const wheelRRRef = useRef<THREE.Mesh>(null!);

  const { times, zs, pitch, roll, zu, zuFL, zuFR, zuRL, zuRR, isFullCar } = data;
  const hasData = times && times.length > 0;
  
  // Create interpolation functions
  const startTime = useRef(Date.now());
  const maxTime = hasData ? times[times.length - 1] : 0;

  useFrame(() => {
    if (!hasData || !chassisRef.current) return;
    
    // Calculate current playback time (looping)
    const elapsed = (Date.now() - startTime.current) / 1000;
    const t = elapsed % maxTime;
    
    // Find index
    let idx = 0;
    for (let i = 0; i < times.length; i++) {
      if (times[i] >= t) {
        idx = i;
        break;
      }
    }
    
    // Scale factor for visualization
    const S = 10;
    
    const currentZs = zs ? zs[idx] * S : 0;
    const currentPitch = pitch ? pitch[idx] * -2 : 0;
    const currentRoll = roll ? roll[idx] * 2 : 0;

    // Apply chassis transformation
    chassisRef.current.position.y = 2 + currentZs;
    chassisRef.current.rotation.x = currentPitch;
    chassisRef.current.rotation.z = currentRoll;
    
    // Apply wheel transformations
    if (isFullCar) {
      if (wheelFLRef.current && zuFL) wheelFLRef.current.position.y = 0.5 + zuFL[idx] * S;
      if (wheelFRRef.current && zuFR) wheelFRRef.current.position.y = 0.5 + zuFR[idx] * S;
      if (wheelRLRef.current && zuRL) wheelRLRef.current.position.y = 0.5 + zuRL[idx] * S;
      if (wheelRRRef.current && zuRR) wheelRRRef.current.position.y = 0.5 + zuRR[idx] * S;
    } else {
      const currentZu = zu ? zu[idx] * S : 0;
      if (wheelFLRef.current) wheelFLRef.current.position.y = 0.5 + currentZu;
      if (wheelFRRef.current) wheelFRRef.current.position.y = 0.5 + currentZu;
      if (wheelRLRef.current) wheelRLRef.current.position.y = 0.5 + currentZu;
      if (wheelRRRef.current) wheelRRRef.current.position.y = 0.5 + currentZu;
    }
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
      <mesh ref={wheelFLRef} position={[-1.6, 0.5, -2]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      <mesh ref={wheelFRRef} position={[1.6, 0.5, -2]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      <mesh ref={wheelRLRef} position={[-1.6, 0.5, 2]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      <mesh ref={wheelRRRef} position={[1.6, 0.5, 2]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      
      {/* Ground plane reference */}
      <Grid infiniteGrid fadeDistance={20} sectionColor="#444" cellColor="#333" />
    </group>
  );
}

export default function SuspensionRig3D(props: SuspensionRigProps) {
  return (
    <Canvas camera={{ position: [5, 4, 8], fov: 45 }}>
      <color attach="background" args={["#1e1e1e"]} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} castShadow />
      <Environment preset="city" />
      
      <RigModel data={props} />
      
      <OrbitControls enablePan={false} maxPolarAngle={Math.PI / 2 - 0.05} minDistance={4} maxDistance={20} />
    </Canvas>
  );
}
