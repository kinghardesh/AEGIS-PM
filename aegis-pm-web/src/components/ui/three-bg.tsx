"use client";

import * as React from "react";
import * as THREE from "three";

export function ThreeBg() {
  const containerRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Create canvas
    const canvas = document.createElement("canvas");
    canvas.style.position = "absolute";
    canvas.style.top = "0";
    canvas.style.left = "0";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.pointerEvents = "none";
    canvas.style.zIndex = "0";
    canvas.style.opacity = "0.75";
    container.appendChild(canvas);

    // Renderer
    const renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
    });
    const pixelRatio = typeof window !== "undefined" ? Math.min(window.devicePixelRatio, 2) : 1;
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(container.clientWidth, container.clientHeight);

    // Scene & Camera
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      55,
      container.clientWidth / container.clientHeight,
      0.1,
      200
    );
    camera.position.set(0, 0, 22);

    const group = new THREE.Group();
    scene.add(group);

    // --- Build node cloud ---
    const NODE_COUNT = 120;
    const RADIUS = 15;
    const palette = [
      0x6366f1, // Indigo
      0x8b5cf6, // Violet
      0x06b6d4, // Cyan
      0x10b981, // Emerald
      0xf59e0b, // Amber
      0xec4899, // Pink
    ];

    const nodes: {
      mesh: THREE.Mesh;
      halo: THREE.Mesh;
      halo2: THREE.Mesh;
      color: number;
      phase: number;
      base: THREE.Vector3;
    }[] = [];

    const nodeGeo = new THREE.IcosahedronGeometry(0.2, 1);

    for (let i = 0; i < NODE_COUNT; i++) {
      const phi = Math.acos(2 * Math.random() - 1);
      const theta = 2 * Math.PI * Math.random();
      const r = RADIUS * (0.4 + Math.random() * 0.6);
      const color = palette[i % palette.length];

      // Central core node
      const mat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending,
      });
      const m = new THREE.Mesh(nodeGeo, mat);
      m.position.set(
        r * Math.sin(phi) * Math.cos(theta),
        r * Math.sin(phi) * Math.sin(theta),
        r * Math.cos(phi)
      );

      // Inner halo
      const haloMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.15,
        blending: THREE.AdditiveBlending,
      });
      const halo = new THREE.Mesh(new THREE.SphereGeometry(0.6, 12, 12), haloMat);
      halo.position.copy(m.position);

      // Outer halo
      const halo2Mat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.04,
        blending: THREE.AdditiveBlending,
      });
      const halo2 = new THREE.Mesh(new THREE.SphereGeometry(1.2, 12, 12), halo2Mat);
      halo2.position.copy(m.position);

      group.add(m);
      group.add(halo);
      group.add(halo2);

      nodes.push({
        mesh: m,
        halo,
        halo2,
        color,
        phase: Math.random() * Math.PI * 2,
        base: m.position.clone(),
      });
    }

    // --- Build connection lines ---
    const lineSegs: number[] = [];
    const colors: number[] = [];
    const MAX_DIST = 5.2;

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const d = nodes[i].mesh.position.distanceTo(nodes[j].mesh.position);
        if (d < MAX_DIST) {
          lineSegs.push(
            nodes[i].mesh.position.x,
            nodes[i].mesh.position.y,
            nodes[i].mesh.position.z,
            nodes[j].mesh.position.x,
            nodes[j].mesh.position.y,
            nodes[j].mesh.position.z
          );
          const c1 = new THREE.Color(nodes[i].color);
          const c2 = new THREE.Color(nodes[j].color);
          colors.push(c1.r, c1.g, c1.b, c2.r, c2.g, c2.b);
        }
      }
    }

    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(lineSegs), 3));
    lineGeo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(colors), 3));

    const lineMat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.45,
      blending: THREE.AdditiveBlending,
    });
    const lines = new THREE.LineSegments(lineGeo, lineMat);
    group.add(lines);

    // --- Particle dust field ---
    const DUST = 800;
    const dustPos = new Float32Array(DUST * 3);
    for (let i = 0; i < DUST; i++) {
      dustPos[i * 3] = (Math.random() - 0.5) * 60;
      dustPos[i * 3 + 1] = (Math.random() - 0.5) * 60;
      dustPos[i * 3 + 2] = (Math.random() - 0.5) * 60;
    }
    const dustGeo = new THREE.BufferGeometry();
    dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
    const dustMat = new THREE.PointsMaterial({
      color: 0xc7d2fe,
      size: 0.06,
      transparent: true,
      opacity: 0.6,
      blending: THREE.AdditiveBlending,
    });
    const dust = new THREE.Points(dustGeo, dustMat);
    group.add(dust);

    // --- Mouse Parallax ---
    let mx = 0;
    let my = 0;
    const onMouseMove = (e: MouseEvent) => {
      mx = e.clientX / window.innerWidth - 0.5;
      my = e.clientY / window.innerHeight - 0.5;
    };
    window.addEventListener("mousemove", onMouseMove);

    // --- Resize Handler ---
    const onResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    // --- Animation loop ---
    let t = 0;
    let animationFrameId: number;

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      t += 0.005;

      // Slow rotation
      group.rotation.y += 0.0012;
      group.rotation.x += 0.0005;

      // Parallax effect on camera
      camera.position.x += (mx * 3 - camera.position.x) * 0.03;
      camera.position.y += (-my * 3 - camera.position.y) * 0.03;
      camera.lookAt(0, 0, 0);

      // Pulse nodes
      nodes.forEach((n) => {
        const pulse = 0.85 + Math.sin(t * 2 + n.phase) * 0.25;
        n.mesh.scale.setScalar(pulse);
        n.halo.scale.setScalar(pulse * 1.4);
        n.halo2.scale.setScalar(pulse * 2.2);

        // Adjust halo opacities dynamically
        if (n.halo.material instanceof THREE.MeshBasicMaterial) {
          n.halo.material.opacity = 0.12 + Math.sin(t * 2 + n.phase) * 0.06;
        }
        if (n.halo2.material instanceof THREE.MeshBasicMaterial) {
          n.halo2.material.opacity = 0.03 + Math.sin(t * 2 + n.phase) * 0.03;
        }
      });

      // Subtle breathing for lines
      lineMat.opacity = 0.25 + Math.sin(t * 1.5) * 0.07;

      // Rotate dust
      dust.rotation.y += 0.0003;

      renderer.render(scene, camera);
    };

    animate();

    // Clean up
    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("resize", onResize);

      // Dispose resources
      nodeGeo.dispose();
      lineGeo.dispose();
      dustGeo.dispose();
      lineMat.dispose();
      dustMat.dispose();

      nodes.forEach((n) => {
        if (n.mesh.material instanceof THREE.Material) n.mesh.material.dispose();
        if (n.halo.material instanceof THREE.Material) n.halo.material.dispose();
        if (n.halo2.material instanceof THREE.Material) n.halo2.material.dispose();
      });

      renderer.dispose();
      if (container.contains(canvas)) {
        container.removeChild(canvas);
      }
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 -z-10 h-full w-full overflow-hidden bg-[radial-gradient(ellipse_at_center,#0b1020_0%,#050811_70%)]"
    />
  );
}
