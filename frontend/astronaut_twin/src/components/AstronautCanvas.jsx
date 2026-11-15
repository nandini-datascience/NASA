import React, { useRef, useEffect } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Stars } from '@react-three/drei';
import * as THREE from 'three';
import AstronautModel from './AstronautModel';

// Camera controller that manages views (front, back, left, right, reset)
// and ensures the complete astronaut is ALWAYS framed comfortably from helmet to boots.
function CameraController({ viewPreset, resetTrigger, controlsRef }) {
  const { camera } = useThree();
  const targetCamPos = useRef(new THREE.Vector3(0, 0, 3.6));
  const targetLookAt = useRef(new THREE.Vector3(0, 0, 0));

  useEffect(() => {
    switch (viewPreset) {
      case 'front':
        targetCamPos.current.set(0, 0, 3.6);
        targetLookAt.current.set(0, 0, 0);
        break;
      case 'back':
        targetCamPos.current.set(0, 0, -3.6);
        targetLookAt.current.set(0, 0, 0);
        break;
      case 'left':
        targetCamPos.current.set(-3.6, 0, 0);
        targetLookAt.current.set(0, 0, 0);
        break;
      case 'right':
        targetCamPos.current.set(3.6, 0, 0);
        targetLookAt.current.set(0, 0, 0);
        break;
      default:
        targetCamPos.current.set(0, 0, 3.6);
        targetLookAt.current.set(0, 0, 0);
        break;
    }

    if (controlsRef && controlsRef.current) {
      controlsRef.current.target.set(0, 0, 0);
    }
  }, [viewPreset, resetTrigger, controlsRef]);

  useFrame(() => {
    camera.position.lerp(targetCamPos.current, 0.08);
  });

  return null;
}

export default function AstronautCanvas({
  selectedRegion,
  onSelectRegion,
  autoRotate = false,
  wireframe = false,
  showAura = true,
  radiationIntensity = 0.3,
  resetTrigger = 0,
  viewPreset = 'front',
  controlsRef
}) {
  return (
    <div className="twin-canvas-container">
      <Canvas
        shadows
        gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
      >
        {/* Front-facing default perspective camera positioned to fit the FULL astronaut */}
        <PerspectiveCamera makeDefault position={[0, 0, 3.6]} fov={42} />

        {/* Orbit Controls with 360 degree drag rotation and strict zoom limits */}
        <OrbitControls
          ref={controlsRef}
          makeDefault
          enablePan={false}
          enableZoom={true}
          minDistance={2.0}
          maxDistance={5.2}
          autoRotate={autoRotate}
          autoRotateSpeed={1.0}
          target={[0, 0, 0]}
          dampingFactor={0.08}
        />

        {/* Camera Preset Controller */}
        <CameraController
          viewPreset={viewPreset}
          resetTrigger={resetTrigger}
          controlsRef={controlsRef}
        />

        {/* Professional Aerospace Lighting */}
        <ambientLight intensity={1.2} color="#1e293b" />
        <directionalLight
          position={[5, 8, 5]}
          intensity={2.4}
          color="#ffffff"
          castShadow
          shadow-mapSize={[1024, 1024]}
        />
        {/* Cyan Neon Space Environment Fill Light */}
        <directionalLight position={[-5, 2, -3]} intensity={1.6} color="#00f2fe" />
        {/* Subtle Violet Rim Accent */}
        <pointLight position={[0, -2, -3]} intensity={1.2} color="#8b5cf6" />
        {/* Front Warm Helmet Visor Light */}
        <pointLight position={[0, 1.2, 2.5]} intensity={0.9} color="#f59e0b" />

        {/* Dark Space Starfield */}
        <Stars radius={45} depth={45} count={2800} factor={4} saturation={0.4} fade speed={0.8} />

        {/* Concentric Holographic Floor Grid Beneath Astronaut's Boots (y = -1.08) */}
        <group position={[0, -1.08, 0]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[0.75, 0.78, 64]} />
            <meshBasicMaterial color="#00f2fe" transparent opacity={0.65} side={THREE.DoubleSide} />
          </mesh>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[1.15, 1.17, 64]} />
            <meshBasicMaterial color="#38bdf8" transparent opacity={0.35} side={THREE.DoubleSide} />
          </mesh>
          <gridHelper args={[2.8, 14, '#00f2fe', '#0e244d']} />
        </group>

        {/* Complete Realistic Astronaut 3D Model */}
        <AstronautModel
          selectedRegion={selectedRegion}
          onSelectRegion={onSelectRegion}
          wireframe={wireframe}
          radiationIntensity={radiationIntensity}
          showAura={showAura}
        />
      </Canvas>
    </div>
  );
}
