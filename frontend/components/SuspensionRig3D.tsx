"use client";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Grid, Environment } from "@react-three/drei";
import { useRef } from "react";
import * as THREE from "three";

interface RigProps {
  zs?: number;
  pitch?: number;
  roll?: number;
  zu_fl?: number;
  zu_fr?: number;
  zu_rl?: number;
  zu_rr?: number;
}

function CarModel({ zs = 0, pitch = 0, roll = 0, zu_fl = 0, zu_fr = 0, zu_rl = 0, zu_rr = 0 }: RigProps) {
  const chassisRef = useRef<THREE.Group>(null!);
  const flRef = useRef<THREE.Mesh>(null!);
  const frRef = useRef<THREE.Mesh>(null!);
  const rlRef = useRef<THREE.Mesh>(null!);
  const rrRef = useRef<THREE.Mesh>(null!);
  
  useFrame((_, delta) => {
    const alpha = 1 - Math.exp(-8 * delta);
    
    if (chassisRef.current) {
      // Scale up displacements for visual clarity (10x)
      chassisRef.current.position.y = THREE.MathUtils.lerp(chassisRef.current.position.y, 2 + zs * 10, alpha);
      chassisRef.current.rotation.x = THREE.MathUtils.lerp(chassisRef.current.rotation.x, pitch * -2, alpha);
      chassisRef.current.rotation.z = THREE.MathUtils.lerp(chassisRef.current.rotation.z, roll * 2, alpha);
    }
    
    // Independent wheel animation
    if (flRef.current) flRef.current.position.y = THREE.MathUtils.lerp(flRef.current.position.y, 1.5 + zu_fl * 10, alpha);
    if (frRef.current) frRef.current.position.y = THREE.MathUtils.lerp(frRef.current.position.y, 1.5 + zu_fr * 10, alpha);
    if (rlRef.current) rlRef.current.position.y = THREE.MathUtils.lerp(rlRef.current.position.y, 1.5 + zu_rl * 10, alpha);
    if (rrRef.current) rrRef.current.position.y = THREE.MathUtils.lerp(rrRef.current.position.y, 1.5 + zu_rr * 10, alpha);
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

export default function SuspensionRig3D(props: RigProps) {
  return (
    <Canvas camera={{ position: [5, 4, 8], fov: 45 }}>
      <color attach="background" args={["transparent"]} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} castShadow />
      <Environment preset="city" />
      
      <CarModel {...props} />
      
      <Grid infiniteGrid fadeDistance={20} sectionColor="#444" cellColor="#333" />
      <OrbitControls enablePan={false} maxPolarAngle={Math.PI / 2 - 0.05} minDistance={4} maxDistance={20} />
    </Canvas>
  );
}
