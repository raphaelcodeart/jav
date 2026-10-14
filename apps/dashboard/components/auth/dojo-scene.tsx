"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Float, RoundedBox } from "@react-three/drei";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { usePrefersReducedMotion } from "@/lib/motion";

/** The tatami: a grid of mats in the club colors with a slow wave running
 *  through it. One instanced mesh, so 120 mats cost one draw call. */
function Tatami({ animate }: { animate: boolean }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const cols = 12;
  const rows = 10;
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const colors = useMemo(() => {
    const red = new THREE.Color("#e43f21");
    const cream = new THREE.Color("#fbf7ec");
    const gray = new THREE.Color("#dcd9d2");
    const arr = new Float32Array(cols * rows * 3);
    for (let i = 0; i < cols * rows; i++) {
      const x = i % cols;
      const z = Math.floor(i / cols);
      // A red border ring around a cream competition area, like a real shiai-jo.
      const border = x < 2 || x >= cols - 2 || z < 2 || z >= rows - 2;
      const c = border ? red : (x + z) % 2 === 0 ? cream : gray;
      c.toArray(arr, i * 3);
    }
    return arr;
  }, []);

  useFrame(({ clock }) => {
    const mesh = ref.current;
    if (!mesh) return;
    const t = animate ? clock.getElapsedTime() : 0;
    for (let i = 0; i < cols * rows; i++) {
      const x = (i % cols) - cols / 2 + 0.5;
      const z = Math.floor(i / cols) - rows / 2 + 0.5;
      const d = Math.sqrt(x * x + z * z);
      const y = Math.sin(d * 0.9 - t * 1.6) * 0.06;
      dummy.position.set(x, y - 0.6, z);
      dummy.rotation.set(0, 0, 0);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  });

  return (
    <group>
      {/* The floor under the mats: the gaps between them read as seams,
          not as holes onto the page behind the canvas. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.72, 0]} receiveShadow>
        <planeGeometry args={[cols * 1.2, rows * 1.2]} />
        <meshStandardMaterial color="#8f897d" roughness={1} />
      </mesh>
      <instancedMesh ref={ref} args={[undefined, undefined, cols * rows]} receiveShadow>
      <boxGeometry args={[1, 0.18, 1]}>
        <instancedBufferAttribute attach="attributes-color" args={[colors, 3]} />
      </boxGeometry>
      <meshStandardMaterial vertexColors roughness={0.85} metalness={0.02} />
      </instancedMesh>
    </group>
  );
}

/** A floating belt: a long rounded band with a knot block in the middle. */
function Belt({ color, position, rotation, speed }: { color: string; position: [number, number, number]; rotation: [number, number, number]; speed: number }) {
  return (
    <Float speed={speed} rotationIntensity={0.9} floatIntensity={1.4} floatingRange={[-0.2, 0.35]}>
      <group position={position} rotation={rotation}>
        <RoundedBox args={[3.4, 0.16, 0.42]} radius={0.06} smoothness={4} castShadow>
          <meshStandardMaterial color={color} roughness={0.55} />
        </RoundedBox>
        <RoundedBox args={[0.5, 0.3, 0.56]} radius={0.08} smoothness={4} castShadow>
          <meshStandardMaterial color={color} roughness={0.5} />
        </RoundedBox>
        <RoundedBox args={[0.22, 0.12, 1.3]} radius={0.05} smoothness={4} position={[0.12, -0.05, 0.55]} rotation={[0.25, 0.3, 0]} castShadow>
          <meshStandardMaterial color={color} roughness={0.55} />
        </RoundedBox>
      </group>
    </Float>
  );
}

/** The camera drifts toward the pointer: a little parallax, a lot of depth. */
function Rig({ animate }: { animate: boolean }) {
  useFrame(({ camera, pointer }) => {
    if (!animate) return;
    camera.position.x += (pointer.x * 1.2 - camera.position.x) * 0.03;
    camera.position.y += (5.6 + pointer.y * 0.6 - camera.position.y) * 0.03;
    camera.lookAt(0, -0.4, 0);
  });
  return null;
}

export default function DojoScene() {
  const reduced = usePrefersReducedMotion();
  const animate = !reduced;
  return (
    <Canvas
      shadows
      dpr={[1, 1.75]}
      frameloop={animate ? "always" : "demand"}
      camera={{ position: [0, 5.6, 11], fov: 40 }}
      gl={{ antialias: true, alpha: true }}
      onCreated={({ camera }) => camera.lookAt(0, -0.4, 0)}
    >
      <ambientLight intensity={0.75} />
      <directionalLight position={[5, 9, 4]} intensity={1.6} castShadow shadow-mapSize={[1024, 1024]} />
      <directionalLight position={[-6, 4, -3]} intensity={0.5} color="#f9e40f" />
      <pointLight position={[0, 3, 3]} intensity={0.6} color="#e43f21" />

      <Tatami animate={animate} />
      <Belt color="#e43f21" position={[-1.6, 1.4, 0.4]} rotation={[0.2, 0.5, 0.15]} speed={1.6} />
      <Belt color="#f9e40f" position={[1.8, 2.1, -0.8]} rotation={[-0.15, -0.6, -0.2]} speed={1.3} />
      <Belt color="#161515" position={[0.3, 2.9, -2]} rotation={[0.3, 0.2, 0.35]} speed={1.1} />
      <Belt color="#ffffff" position={[2.6, 0.9, 1.4]} rotation={[0.1, 1.1, -0.1]} speed={1.8} />
      <ContactShadows position={[0, -0.49, 0]} opacity={0.35} scale={14} blur={2.4} far={4} />
      <Rig animate={animate} />
    </Canvas>
  );
}
