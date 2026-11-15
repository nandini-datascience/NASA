import React, { useRef, useState, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

// Model asset paths
const GLB_CANDIDATE_URLS = [
  '/api/astronaut/model',
  'http://127.0.0.1:8000/api/astronaut/model',
  'assets/models/Astronaut.glb',
  'dist/Astronaut.glb',
  '/assets/models/Astronaut.glb'
];

export default function AstronautModel({
  selectedRegion,
  onSelectRegion,
  wireframe = false,
  radiationIntensity = 0.3,
  showAura = true
}) {
  const astronautGroup = useRef();
  const [hoveredRegion, setHoveredRegion] = useState(null);
  const [gltfScene, setGltfScene] = useState(null);

  // Attempt loading the realistic GLB model with automatic fallback
  useEffect(() => {
    let isMounted = true;
    const loader = new GLTFLoader();

    const tryLoad = async () => {
      for (const url of GLB_CANDIDATE_URLS) {
        try {
          const gltf = await new Promise((resolve, reject) => {
            loader.load(url, resolve, undefined, reject);
          });
          if (isMounted && gltf && gltf.scene) {
            console.log('✅ Realistic Astronaut.glb loaded successfully from:', url);
            // Compute bounding box and normalize scale & origin
            const bbox = new THREE.Box3().setFromObject(gltf.scene);
            const size = new THREE.Vector3();
            bbox.getSize(size);
            const center = new THREE.Vector3();
            bbox.getCenter(center);

            // Scale to standard human spacesuit height: 2.1m
            const targetHeight = 2.1;
            const scale = size.y > 0 ? targetHeight / size.y : 1.0;
            gltf.scene.scale.set(scale, scale, scale);

            // Center vertically so feet are at -1.05 and head at +1.05
            gltf.scene.position.x = -center.x * scale;
            gltf.scene.position.y = -center.y * scale;
            gltf.scene.position.z = -center.z * scale;

            // Enable shadows
            gltf.scene.traverse((child) => {
              if (child.isMesh) {
                child.castShadow = true;
                child.receiveShadow = true;
                if (child.material) {
                  child.material.roughness = Math.min(child.material.roughness, 0.45);
                }
              }
            });

            setGltfScene(gltf.scene);
            return;
          }
        } catch (e) {
          // Continue to next candidate URL
        }
      }
      console.log('ℹ️ Utilizing high-detail procedural human astronaut model.');
    };

    tryLoad();
    return () => { isMounted = false; };
  }, []);

  // Subtle weightless floating oscillation
  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (astronautGroup.current) {
      astronautGroup.current.position.y = Math.sin(t * 1.1) * 0.035;
      astronautGroup.current.rotation.z = Math.sin(t * 0.7) * 0.01;
      astronautGroup.current.rotation.y = Math.sin(t * 0.5) * 0.015;
    }
  });

  const handlePointerOver = (e, region) => {
    e.stopPropagation();
    document.body.style.cursor = 'pointer';
    setHoveredRegion(region);
  };

  const handlePointerOut = (e) => {
    e.stopPropagation();
    document.body.style.cursor = 'auto';
    setHoveredRegion(null);
  };

  const handleClick = (e, region) => {
    e.stopPropagation();
    if (onSelectRegion) {
      onSelectRegion(region);
    }
  };

  const isHighlighted = (region) => selectedRegion === region || hoveredRegion === region;
  const isSelected = (region) => selectedRegion === region;

  // Materials for realistic human astronaut spacesuit
  const suitColor = wireframe ? '#00f2fe' : '#f1f5f9';
  const suitMaterial = new THREE.MeshStandardMaterial({
    color: suitColor,
    roughness: 0.5,
    metalness: 0.12,
    wireframe: wireframe
  });

  const suitJointMaterial = new THREE.MeshStandardMaterial({
    color: wireframe ? '#38bdf8' : '#64748b',
    roughness: 0.55,
    metalness: 0.5,
    wireframe: wireframe
  });

  // Clear transparent helmet dome material
  const clearHelmetGlass = new THREE.MeshPhysicalMaterial({
    color: '#ffffff',
    transparent: true,
    opacity: 0.35,
    roughness: 0.05,
    transmission: 0.85,
    thickness: 0.4,
    clearcoat: 1.0,
    clearcoatRoughness: 0.1,
    wireframe: wireframe
  });

  // Human skin tone for head inside helmet
  const humanSkinMaterial = new THREE.MeshStandardMaterial({
    color: '#d4a373',
    roughness: 0.65,
    metalness: 0.05
  });

  // Gold reflective visor material
  const goldVisorMaterial = new THREE.MeshPhysicalMaterial({
    color: wireframe ? '#00f2fe' : '#f59e0b',
    emissive: wireframe ? '#00f2fe' : '#b45309',
    emissiveIntensity: 0.25,
    roughness: 0.04,
    metalness: 0.98,
    clearcoat: 1.0,
    clearcoatRoughness: 0.05,
    wireframe: wireframe
  });

  const darkRubberMaterial = new THREE.MeshStandardMaterial({
    color: '#1e293b',
    roughness: 0.8,
    metalness: 0.2
  });

  return (
    <group ref={astronautGroup} position={[0, 0, 0]}>
      {/* If GLB model successfully loaded, display it alongside interactive colliders */}
      {gltfScene ? (
        <group>
          <primitive object={gltfScene} />
          {/* Transparent interactive hitbox overlays mapped onto the 9 anatomical regions */}
          <mesh
            position={[0, 0.72, 0]}
            onPointerOver={(e) => handlePointerOver(e, 'head')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'head')}
          >
            <sphereGeometry args={[0.34, 16, 16]} />
            <meshBasicMaterial
              color={isSelected('head') ? '#00f2fe' : '#38bdf8'}
              wireframe
              transparent
              opacity={isHighlighted('head') ? 0.45 : 0.0}
            />
          </mesh>

          <mesh
            position={[0, 0.32, 0.05]}
            onPointerOver={(e) => handlePointerOver(e, 'chest')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'chest')}
          >
            <boxGeometry args={[0.62, 0.45, 0.38]} />
            <meshBasicMaterial
              color={isSelected('chest') ? '#00f2fe' : '#38bdf8'}
              wireframe
              transparent
              opacity={isHighlighted('chest') ? 0.4 : 0.0}
            />
          </mesh>

          {/* Heart node */}
          <group
            position={[-0.13, 0.36, 0.22]}
            onPointerOver={(e) => handlePointerOver(e, 'heart')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'heart')}
          >
            <mesh>
              <sphereGeometry args={[0.065, 16, 16]} />
              <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={0.8} />
            </mesh>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <ringGeometry args={[0.08, 0.10, 32]} />
              <meshBasicMaterial color="#ef4444" side={THREE.DoubleSide} />
            </mesh>
          </group>

          {/* Lungs node */}
          <group
            position={[0.13, 0.36, 0.22]}
            onPointerOver={(e) => handlePointerOver(e, 'lungs')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'lungs')}
          >
            <mesh>
              <sphereGeometry args={[0.065, 16, 16]} />
              <meshStandardMaterial color="#06b6d4" emissive="#06b6d4" emissiveIntensity={0.8} />
            </mesh>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <ringGeometry args={[0.08, 0.10, 32]} />
              <meshBasicMaterial color="#06b6d4" side={THREE.DoubleSide} />
            </mesh>
          </group>

          {/* Abdomen hitbox */}
          <mesh
            position={[0, 0.02, 0.02]}
            onPointerOver={(e) => handlePointerOver(e, 'abdomen')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'abdomen')}
          >
            <boxGeometry args={[0.48, 0.25, 0.32]} />
            <meshBasicMaterial
              color={isSelected('abdomen') ? '#00f2fe' : '#38bdf8'}
              wireframe
              transparent
              opacity={isHighlighted('abdomen') ? 0.4 : 0.0}
            />
          </mesh>

          {/* Left Arm hitbox */}
          <mesh
            position={[-0.44, 0.22, 0.04]}
            onPointerOver={(e) => handlePointerOver(e, 'left_arm')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'left_arm')}
          >
            <cylinderGeometry args={[0.14, 0.12, 0.72, 16]} />
            <meshBasicMaterial
              color={isSelected('left_arm') ? '#00f2fe' : '#38bdf8'}
              wireframe
              transparent
              opacity={isHighlighted('left_arm') ? 0.4 : 0.0}
            />
          </mesh>

          {/* Right Arm hitbox */}
          <mesh
            position={[0.44, 0.22, 0.04]}
            onPointerOver={(e) => handlePointerOver(e, 'right_arm')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'right_arm')}
          >
            <cylinderGeometry args={[0.14, 0.12, 0.72, 16]} />
            <meshBasicMaterial
              color={isSelected('right_arm') ? '#00f2fe' : '#38bdf8'}
              wireframe
              transparent
              opacity={isHighlighted('right_arm') ? 0.4 : 0.0}
            />
          </mesh>

          {/* Left Leg hitbox */}
          <mesh
            position={[-0.20, -0.52, 0.02]}
            onPointerOver={(e) => handlePointerOver(e, 'left_leg')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'left_leg')}
          >
            <cylinderGeometry args={[0.16, 0.13, 0.88, 16]} />
            <meshBasicMaterial
              color={isSelected('left_leg') ? '#00f2fe' : '#38bdf8'}
              wireframe
              transparent
              opacity={isHighlighted('left_leg') ? 0.4 : 0.0}
            />
          </mesh>

          {/* Right Leg hitbox */}
          <mesh
            position={[0.20, -0.52, 0.02]}
            onPointerOver={(e) => handlePointerOver(e, 'right_leg')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'right_leg')}
          >
            <cylinderGeometry args={[0.16, 0.13, 0.88, 16]} />
            <meshBasicMaterial
              color={isSelected('right_leg') ? '#00f2fe' : '#38bdf8'}
              wireframe
              transparent
              opacity={isHighlighted('right_leg') ? 0.4 : 0.0}
            />
          </mesh>
        </group>
      ) : (
        /* ==============================================================
           COMPLETE HIGH-FIDELITY PROCEDURAL HUMAN ASTRONAUT
           Total Height: 2.1m (feet at -1.05m, head top at +1.05m)
           Center: [0, 0, 0]
           ============================================================== */
        <group>
          {/* ==========================================================
              1. HEAD & HELMET (with visible human face inside)
              ========================================================== */}
          <group
            position={[0, 0.76, 0]}
            onPointerOver={(e) => handlePointerOver(e, 'head')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'head')}
          >
            {/* INNER HUMAN HEAD (Anatomical human head inside helmet) */}
            <group position={[0, 0.02, 0]}>
              {/* Human Head Sculpt */}
              <mesh position={[0, 0, 0]}>
                <sphereGeometry args={[0.17, 24, 24]} />
                <primitive object={humanSkinMaterial} attach="material" />
              </mesh>
              {/* Nose Bridge */}
              <mesh position={[0, -0.01, 0.16]}>
                <boxGeometry args={[0.035, 0.05, 0.04]} />
                <primitive object={humanSkinMaterial} attach="material" />
              </mesh>
              {/* Communication Snoopy Cap (White & Black) */}
              <mesh position={[0, 0.05, -0.02]}>
                <sphereGeometry args={[0.175, 20, 20, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
                <meshStandardMaterial color="#1e293b" />
              </mesh>
              {/* Headset Ear Cushions */}
              <mesh position={[-0.17, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
                <cylinderGeometry args={[0.045, 0.045, 0.03, 16]} />
                <meshStandardMaterial color="#334155" />
              </mesh>
              <mesh position={[0.17, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
                <cylinderGeometry args={[0.045, 0.045, 0.03, 16]} />
                <meshStandardMaterial color="#334155" />
              </mesh>
            </group>

            {/* TRANSPARENT HELMET BUBBLE DOME */}
            <mesh>
              <sphereGeometry args={[0.29, 32, 32]} />
              <primitive object={clearHelmetGlass} attach="material" />
            </mesh>

            {/* RETRACTABLE GOLD SUN VISOR (Upper Shield) */}
            <mesh position={[0, 0.04, 0.09]} rotation={[0.18, 0, 0]}>
              <sphereGeometry args={[0.295, 32, 16, 0, Math.PI * 2, 0, Math.PI * 0.45]} />
              <primitive object={goldVisorMaterial} attach="material" />
            </mesh>

            {/* Helmet Anodized Neck Collar / Ring */}
            <mesh position={[0, -0.26, 0]}>
              <cylinderGeometry args={[0.22, 0.24, 0.06, 32]} />
              <primitive object={suitJointMaterial} attach="material" />
            </mesh>

            {/* EVA Helmet Side Worklights */}
            <mesh position={[-0.28, 0.08, 0.05]} rotation={[0, 0, Math.PI / 2]}>
              <cylinderGeometry args={[0.035, 0.035, 0.08, 16]} />
              <meshStandardMaterial color="#94a3b8" metalness={0.8} />
            </mesh>
            <mesh position={[0.28, 0.08, 0.05]} rotation={[0, 0, Math.PI / 2]}>
              <cylinderGeometry args={[0.035, 0.035, 0.08, 16]} />
              <meshStandardMaterial color="#94a3b8" metalness={0.8} />
            </mesh>

            {/* Selection Highlight */}
            {isHighlighted('head') && (
              <mesh position={[0, 0.02, 0]}>
                <sphereGeometry args={[0.34, 24, 24]} />
                <meshBasicMaterial
                  color={isSelected('head') ? '#00f2fe' : '#38bdf8'}
                  wireframe
                  transparent
                  opacity={isSelected('head') ? 0.6 : 0.3}
                />
              </mesh>
            )}

            {isHighlighted('head') && (
              <Html position={[0, 0.42, 0]} center>
                <div className="twin-3d-hotspot-label">
                  <span>HEAD & HELMET (EEG / CNS)</span>
                </div>
              </Html>
            )}
          </group>

          {/* ==========================================================
              2. CHEST & UPPER TORSO (Hard Upper Torso + PLSS)
              ========================================================== */}
          <group
            position={[0, 0.35, 0]}
            onPointerOver={(e) => handlePointerOver(e, 'chest')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'chest')}
          >
            {/* Hard Upper Torso (HUT) Main Contoured Body */}
            <mesh castShadow receiveShadow>
              <cylinderGeometry args={[0.34, 0.30, 0.52, 32]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>

            {/* Shoulder Yokes */}
            <mesh position={[-0.32, 0.16, 0]} rotation={[0, 0, 0.35]}>
              <cylinderGeometry args={[0.14, 0.12, 0.22, 20]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>
            <mesh position={[0.32, 0.16, 0]} rotation={[0, 0, -0.35]}>
              <cylinderGeometry args={[0.14, 0.12, 0.22, 20]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>

            {/* Display & Control Module (DCM) on Chest */}
            <mesh position={[0, 0.04, 0.19]}>
              <boxGeometry args={[0.30, 0.24, 0.10]} />
              <meshStandardMaterial color="#1e293b" roughness={0.3} metalness={0.7} />
            </mesh>
            {/* DCM Screen */}
            <mesh position={[0, 0.08, 0.245]}>
              <planeGeometry args={[0.22, 0.09]} />
              <meshBasicMaterial color="#00f2fe" />
            </mesh>
            {/* DCM Switches */}
            <mesh position={[-0.07, -0.04, 0.245]} rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[0.018, 0.018, 0.02, 16]} />
              <meshStandardMaterial color="#64748b" metalness={0.9} />
            </mesh>
            <mesh position={[0.07, -0.04, 0.245]} rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[0.018, 0.018, 0.02, 16]} />
              <meshStandardMaterial color="#64748b" metalness={0.9} />
            </mesh>

            {/* NASA Meatball Insignia Patch */}
            <mesh position={[-0.18, 0.16, 0.17]}>
              <circleGeometry args={[0.045, 24]} />
              <meshBasicMaterial color="#1d4ed8" />
            </mesh>

            {/* Life Support Backpack (PLSS) on Rear */}
            <mesh position={[0, 0.06, -0.24]} castShadow>
              <boxGeometry args={[0.54, 0.68, 0.22]} />
              <meshStandardMaterial color="#cbd5e1" roughness={0.4} metalness={0.3} />
            </mesh>
            {/* Dual Oxygen Cylinders on PLSS */}
            <mesh position={[-0.14, 0.08, -0.36]}>
              <cylinderGeometry args={[0.07, 0.07, 0.58, 20]} />
              <meshStandardMaterial color="#f8fafc" metalness={0.5} roughness={0.25} />
            </mesh>
            <mesh position={[0.14, 0.08, -0.36]}>
              <cylinderGeometry args={[0.07, 0.07, 0.58, 20]} />
              <meshStandardMaterial color="#f8fafc" metalness={0.5} roughness={0.25} />
            </mesh>

            {isHighlighted('chest') && (
              <mesh>
                <cylinderGeometry args={[0.38, 0.34, 0.58, 32]} />
                <meshBasicMaterial
                  color={isSelected('chest') ? '#00f2fe' : '#38bdf8'}
                  wireframe
                  transparent
                  opacity={isSelected('chest') ? 0.6 : 0.3}
                />
              </mesh>
            )}

            {isHighlighted('chest') && (
              <Html position={[0, 0.35, 0.25]} center>
                <div className="twin-3d-hotspot-label">
                  <span>CHEST / THORAX (DCM & Respiration)</span>
                </div>
              </Html>
            )}
          </group>

          {/* ==========================================================
              3. HEART REGION HOTSPOT
              ========================================================== */}
          <group
            position={[-0.12, 0.42, 0.22]}
            onPointerOver={(e) => handlePointerOver(e, 'heart')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'heart')}
          >
            <mesh>
              <sphereGeometry args={[0.065, 20, 20]} />
              <meshStandardMaterial
                color="#ef4444"
                emissive="#ef4444"
                emissiveIntensity={isHighlighted('heart') ? 0.9 : 0.5}
              />
            </mesh>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <ringGeometry args={[0.075, 0.095, 32]} />
              <meshBasicMaterial color="#ef4444" side={THREE.DoubleSide} />
            </mesh>

            {isHighlighted('heart') && (
              <Html position={[0, 0.16, 0]} center>
                <div className="twin-3d-hotspot-label" style={{ borderColor: '#ef4444' }}>
                  <span>HEART REGION (ECG & BPM)</span>
                </div>
              </Html>
            )}
          </group>

          {/* ==========================================================
              4. LUNGS REGION HOTSPOT
              ========================================================== */}
          <group
            position={[0.12, 0.42, 0.22]}
            onPointerOver={(e) => handlePointerOver(e, 'lungs')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'lungs')}
          >
            <mesh>
              <sphereGeometry args={[0.065, 20, 20]} />
              <meshStandardMaterial
                color="#06b6d4"
                emissive="#06b6d4"
                emissiveIntensity={isHighlighted('lungs') ? 0.9 : 0.5}
              />
            </mesh>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <ringGeometry args={[0.075, 0.095, 32]} />
              <meshBasicMaterial color="#06b6d4" side={THREE.DoubleSide} />
            </mesh>

            {isHighlighted('lungs') && (
              <Html position={[0, 0.16, 0]} center>
                <div className="twin-3d-hotspot-label" style={{ borderColor: '#06b6d4' }}>
                  <span>LUNGS REGION (SpO2 & Resp)</span>
                </div>
              </Html>
            )}
          </group>

          {/* ==========================================================
              5. ABDOMEN & WAIST ASSEMBLY
              ========================================================== */}
          <group
            position={[0, 0.02, 0]}
            onPointerOver={(e) => handlePointerOver(e, 'abdomen')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'abdomen')}
          >
            {/* Waist Section */}
            <mesh castShadow receiveShadow>
              <cylinderGeometry args={[0.29, 0.31, 0.24, 32]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>
            {/* Waist Flex Creases */}
            <mesh position={[0, 0.08, 0]}>
              <torusGeometry args={[0.30, 0.022, 16, 32]} />
              <primitive object={suitJointMaterial} attach="material" />
            </mesh>
            {/* Utility Equipment Belt */}
            <mesh position={[0, -0.06, 0]}>
              <torusGeometry args={[0.31, 0.025, 16, 32]} />
              <meshStandardMaterial color="#475569" />
            </mesh>
            {/* Belt Pouches */}
            <mesh position={[-0.22, -0.06, 0.18]}>
              <boxGeometry args={[0.08, 0.10, 0.07]} />
              <meshStandardMaterial color="#334155" />
            </mesh>
            <mesh position={[0.22, -0.06, 0.18]}>
              <boxGeometry args={[0.08, 0.10, 0.07]} />
              <meshStandardMaterial color="#334155" />
            </mesh>

            {isHighlighted('abdomen') && (
              <mesh>
                <cylinderGeometry args={[0.34, 0.36, 0.28, 32]} />
                <meshBasicMaterial
                  color={isSelected('abdomen') ? '#00f2fe' : '#38bdf8'}
                  wireframe
                  transparent
                  opacity={isSelected('abdomen') ? 0.6 : 0.3}
                />
              </mesh>
            )}

            {isHighlighted('abdomen') && (
              <Html position={[0, 0.20, 0.25]} center>
                <div className="twin-3d-hotspot-label">
                  <span>ABDOMEN (Core Temp & Visceral)</span>
                </div>
              </Html>
            )}
          </group>

          {/* ==========================================================
              6. LEFT ARM & GLOVE WITH FINGERS
              ========================================================== */}
          <group
            position={[-0.42, 0.44, 0]}
            onPointerOver={(e) => handlePointerOver(e, 'left_arm')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'left_arm')}
          >
            {/* Shoulder Bearing */}
            <mesh>
              <sphereGeometry args={[0.12, 20, 20]} />
              <primitive object={suitJointMaterial} attach="material" />
            </mesh>
            {/* Upper Arm Sleeve */}
            <mesh position={[-0.08, -0.18, 0.02]} rotation={[0, 0, 0.25]}>
              <cylinderGeometry args={[0.11, 0.095, 0.28, 20]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>
            {/* Elbow Articulation */}
            <mesh position={[-0.14, -0.34, 0.04]}>
              <sphereGeometry args={[0.095, 16, 16]} />
              <primitive object={suitJointMaterial} attach="material" />
            </mesh>
            {/* Forearm Sleeve */}
            <mesh position={[-0.18, -0.52, 0.08]} rotation={[-0.15, 0, 0.2]}>
              <cylinderGeometry args={[0.095, 0.085, 0.28, 20]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>
            {/* Glove Gauntlet */}
            <mesh position={[-0.22, -0.68, 0.12]}>
              <boxGeometry args={[0.10, 0.10, 0.08]} />
              <meshStandardMaterial color="#64748b" roughness={0.7} />
            </mesh>
            {/* Individual Glove Fingers */}
            <mesh position={[-0.22, -0.76, 0.13]}>
              <cylinderGeometry args={[0.035, 0.03, 0.08, 12]} />
              <meshStandardMaterial color="#475569" roughness={0.8} />
            </mesh>

            {isHighlighted('left_arm') && (
              <mesh position={[-0.12, -0.38, 0.05]}>
                <cylinderGeometry args={[0.15, 0.13, 0.78, 16]} />
                <meshBasicMaterial
                  color={isSelected('left_arm') ? '#00f2fe' : '#38bdf8'}
                  wireframe
                  transparent
                  opacity={isSelected('left_arm') ? 0.6 : 0.3}
                />
              </mesh>
            )}

            {isHighlighted('left_arm') && (
              <Html position={[-0.25, -0.2, 0.1]} center>
                <div className="twin-3d-hotspot-label">
                  <span>LEFT ARM (Brachial BP & Glove)</span>
                </div>
              </Html>
            )}
          </group>

          {/* ==========================================================
              7. RIGHT ARM & BIOMETRIC GAUNTLET
              ========================================================== */}
          <group
            position={[0.42, 0.44, 0]}
            onPointerOver={(e) => handlePointerOver(e, 'right_arm')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'right_arm')}
          >
            {/* Shoulder Bearing */}
            <mesh>
              <sphereGeometry args={[0.12, 20, 20]} />
              <primitive object={suitJointMaterial} attach="material" />
            </mesh>
            {/* Upper Arm Sleeve */}
            <mesh position={[0.08, -0.18, 0.02]} rotation={[0, 0, -0.25]}>
              <cylinderGeometry args={[0.11, 0.095, 0.28, 20]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>
            {/* Elbow Articulation */}
            <mesh position={[0.14, -0.34, 0.04]}>
              <sphereGeometry args={[0.095, 16, 16]} />
              <primitive object={suitJointMaterial} attach="material" />
            </mesh>
            {/* Forearm Sleeve */}
            <mesh position={[0.18, -0.52, 0.08]} rotation={[-0.15, 0, -0.2]}>
              <cylinderGeometry args={[0.095, 0.085, 0.28, 20]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>
            {/* Glove Gauntlet */}
            <mesh position={[0.22, -0.68, 0.12]}>
              <boxGeometry args={[0.10, 0.10, 0.08]} />
              <meshStandardMaterial color="#64748b" roughness={0.7} />
            </mesh>
            {/* Right Glove Biometric Display */}
            <mesh position={[0.25, -0.66, 0.16]} rotation={[0, 0.4, 0]}>
              <planeGeometry args={[0.045, 0.06]} />
              <meshBasicMaterial color="#00f2fe" />
            </mesh>
            {/* Individual Glove Fingers */}
            <mesh position={[0.22, -0.76, 0.13]}>
              <cylinderGeometry args={[0.035, 0.03, 0.08, 12]} />
              <meshStandardMaterial color="#475569" roughness={0.8} />
            </mesh>

            {isHighlighted('right_arm') && (
              <mesh position={[0.12, -0.38, 0.05]}>
                <cylinderGeometry args={[0.15, 0.13, 0.78, 16]} />
                <meshBasicMaterial
                  color={isSelected('right_arm') ? '#00f2fe' : '#38bdf8'}
                  wireframe
                  transparent
                  opacity={isSelected('right_arm') ? 0.6 : 0.3}
                />
              </mesh>
            )}

            {isHighlighted('right_arm') && (
              <Html position={[0.25, -0.2, 0.1]} center>
                <div className="twin-3d-hotspot-label">
                  <span>RIGHT ARM (Gauntlet & SpO2)</span>
                </div>
              </Html>
            )}
          </group>

          {/* ==========================================================
              8. LEFT LEG & BOOT (Complete Human Leg)
              ========================================================== */}
          <group
            position={[-0.18, -0.18, 0]}
            onPointerOver={(e) => handlePointerOver(e, 'left_leg')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'left_leg')}
          >
            {/* Hip Joint */}
            <mesh position={[0, 0.02, 0]}>
              <sphereGeometry args={[0.13, 20, 20]} />
              <primitive object={suitJointMaterial} attach="material" />
            </mesh>
            {/* Thigh Sleeve */}
            <mesh position={[0, -0.22, 0]} rotation={[0, 0, -0.03]}>
              <cylinderGeometry args={[0.135, 0.115, 0.38, 20]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>
            {/* Thigh Flap Pocket */}
            <mesh position={[-0.11, -0.20, 0.02]}>
              <boxGeometry args={[0.045, 0.16, 0.13]} />
              <meshStandardMaterial color="#475569" />
            </mesh>
            {/* Knee Joint Bearing & Protective Knee Pad */}
            <mesh position={[0, -0.44, 0]}>
              <sphereGeometry args={[0.11, 20, 20]} />
              <primitive object={suitJointMaterial} attach="material" />
            </mesh>
            <mesh position={[0, -0.44, 0.09]}>
              <boxGeometry args={[0.14, 0.13, 0.04]} />
              <meshStandardMaterial color="#334155" />
            </mesh>
            {/* Shin / Calf Sleeve */}
            <mesh position={[0, -0.68, 0]}>
              <cylinderGeometry args={[0.11, 0.10, 0.40, 20]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>
            {/* Heavy Lunar EVA Boot */}
            <mesh position={[0, -0.92, 0.05]} castShadow>
              <boxGeometry args={[0.17, 0.15, 0.32]} />
              <primitive object={darkRubberMaterial} attach="material" />
            </mesh>
            {/* Boot Sole Tread */}
            <mesh position={[0, -1.00, 0.05]}>
              <boxGeometry args={[0.19, 0.035, 0.34]} />
              <meshStandardMaterial color="#0f172a" roughness={0.95} />
            </mesh>

            {isHighlighted('left_leg') && (
              <mesh position={[0, -0.48, 0.02]}>
                <cylinderGeometry args={[0.16, 0.14, 0.98, 16]} />
                <meshBasicMaterial
                  color={isSelected('left_leg') ? '#00f2fe' : '#38bdf8'}
                  wireframe
                  transparent
                  opacity={isSelected('left_leg') ? 0.6 : 0.3}
                />
              </mesh>
            )}

            {isHighlighted('left_leg') && (
              <Html position={[0, -0.6, 0.25]} center>
                <div className="twin-3d-hotspot-label">
                  <span>LEFT LEG & BOOT</span>
                </div>
              </Html>
            )}
          </group>

          {/* ==========================================================
              9. RIGHT LEG & BOOT (Complete Human Leg)
              ========================================================== */}
          <group
            position={[0.18, -0.18, 0]}
            onPointerOver={(e) => handlePointerOver(e, 'right_leg')}
            onPointerOut={handlePointerOut}
            onClick={(e) => handleClick(e, 'right_leg')}
          >
            {/* Hip Joint */}
            <mesh position={[0, 0.02, 0]}>
              <sphereGeometry args={[0.13, 20, 20]} />
              <primitive object={suitJointMaterial} attach="material" />
            </mesh>
            {/* Thigh Sleeve */}
            <mesh position={[0, -0.22, 0]} rotation={[0, 0, 0.03]}>
              <cylinderGeometry args={[0.135, 0.115, 0.38, 20]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>
            {/* Thigh Flap Pocket */}
            <mesh position={[0.11, -0.20, 0.02]}>
              <boxGeometry args={[0.045, 0.16, 0.13]} />
              <meshStandardMaterial color="#475569" />
            </mesh>
            {/* Knee Joint Bearing & Protective Knee Pad */}
            <mesh position={[0, -0.44, 0]}>
              <sphereGeometry args={[0.11, 20, 20]} />
              <primitive object={suitJointMaterial} attach="material" />
            </mesh>
            <mesh position={[0, -0.44, 0.09]}>
              <boxGeometry args={[0.14, 0.13, 0.04]} />
              <meshStandardMaterial color="#334155" />
            </mesh>
            {/* Shin / Calf Sleeve */}
            <mesh position={[0, -0.68, 0]}>
              <cylinderGeometry args={[0.11, 0.10, 0.40, 20]} />
              <primitive object={suitMaterial} attach="material" />
            </mesh>
            {/* Heavy Lunar EVA Boot */}
            <mesh position={[0, -0.92, 0.05]} castShadow>
              <boxGeometry args={[0.17, 0.15, 0.32]} />
              <primitive object={darkRubberMaterial} attach="material" />
            </mesh>
            {/* Boot Sole Tread */}
            <mesh position={[0, -1.00, 0.05]}>
              <boxGeometry args={[0.19, 0.035, 0.34]} />
              <meshStandardMaterial color="#0f172a" roughness={0.95} />
            </mesh>

            {isHighlighted('right_leg') && (
              <mesh position={[0, -0.48, 0.02]}>
                <cylinderGeometry args={[0.16, 0.14, 0.98, 16]} />
                <meshBasicMaterial
                  color={isSelected('right_leg') ? '#00f2fe' : '#38bdf8'}
                  wireframe
                  transparent
                  opacity={isSelected('right_leg') ? 0.6 : 0.3}
                />
              </mesh>
            )}

            {isHighlighted('right_leg') && (
              <Html position={[0, -0.6, 0.25]} center>
                <div className="twin-3d-hotspot-label">
                  <span>RIGHT LEG & BOOT</span>
                </div>
              </Html>
            )}
          </group>
        </group>
      )}

      {/* DYNAMIC RADIATION AURA (Subtle holographic field lines around astronaut) */}
      {showAura && (
        <group position={[0, 0, 0]}>
          <mesh>
            <sphereGeometry args={[1.55, 32, 32]} />
            <meshBasicMaterial
              color={radiationIntensity > 0.5 ? '#ef4444' : '#00f2fe'}
              wireframe
              transparent
              opacity={Math.min(0.22, Math.max(0.06, radiationIntensity * 0.25))}
            />
          </mesh>
        </group>
      )}
    </group>
  );
}
