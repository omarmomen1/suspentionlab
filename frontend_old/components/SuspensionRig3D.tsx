"use client";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Grid, Environment } from "@react-three/drei";
import { useRef } from "react";
import * as THREE from "three";

function Chassis({ zPosition = 0, pitch = 0, roll = 0 }: { zPosition: number, pitch?: number, roll?: number }) {
  const meshRef = useRef<THREE.Group>(null!);
  
  useFrame((_, delta) => {
    if (meshRef.current) {
      const alpha = 1 - Math.exp(-8 * delta);
      // Smooth interpolation for chassis movement
      meshRef.current.position.y = THREE.MathUtils.lerp(meshRef.current.position.y, 2 + zPosition * 10, alpha);
      meshRef.current.rotation.x = THREE.MathUtils.lerp(meshRef.current.rotation.x, pitch * -2, alpha);
      meshRef.current.rotation.z = THREE.MathUtils.lerp(meshRef.current.rotation.z, roll * 2, alpha);
    }
  });

  return (
    <group ref={meshRef} position={[0, 2, 0]}>
      <mesh>
        <boxGeometry args={[3, 0.5, 6]} />
        <meshStandardMaterial color="#222" metalness={0.8} roughness={0.2} />
      </mesh>
      {/* Front Wheels placeholder */}
      <mesh position={[-1.6, -0.5, -2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      <mesh position={[1.6, -0.5, -2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      {/* Rear Wheels placeholder */}
      <mesh position={[-1.6, -0.5, 2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      <mesh position={[1.6, -0.5, 2]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#111" />
      </mesh>
    </group>
  );
}

export default function SuspensionRig3D({ zs = 0, pitch = 0, roll = 0 }: { zs: number, pitch?: number, roll?: number }) {
  return (
    <Canvas camera={{ position: [5, 4, 8], fov: 45 }}>
      <color attach="background" args={["#1e1e1e"]} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} castShadow />
      <Environment preset="city" />
      
      <Chassis zPosition={zs} pitch={pitch} roll={roll} />
      
      <Grid infiniteGrid fadeDistance={20} sectionColor="#444" cellColor="#333" />
      <OrbitControls enablePan={false} maxPolarAngle={Math.PI / 2 - 0.05} minDistance={4} maxDistance={20} />
    </Canvas>
  );
}
