import React, { useEffect, useRef } from "react";
import type { VerificationState } from "./types";

interface AlgoFortisCoreProps {
  size?: number;
  verificationState?: VerificationState;
  introPhase?: number; // 0, 1, 2, 3
  introElapsed?: number; // seconds from launch
}

type ParticlePalette = "white" | "coolBlue" | "cyan" | "gold" | "amber";

interface Point3D {
  x: number;
  y: number;
  z: number;
  baseRadius: number;
  theta: number;
  phi: number;
  speed: number;
  palette: ParticlePalette;
  rgb: string;
}

export const AlgoFortisCore: React.FC<AlgoFortisCoreProps> = ({
  size = 280,
  verificationState = "ID_ENTRY",
  introPhase = 3,
  introElapsed = 5.0,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animFrameId = useRef<number>(0);
  const rotationAngle = useRef<number>(0);
  const ringTilt = useRef<number>(0.38);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    // Generate 3D point cloud with controlled gold, white and cyan palette
    const pointCount = 76;
    const points: Point3D[] = [];
    const radius = size * 0.37;

    for (let i = 0; i < pointCount; i++) {
      const theta = Math.acos(2 * Math.random() - 1);
      const phi = Math.random() * Math.PI * 2;

      const roll = Math.random();
      let palette: ParticlePalette;
      let rgb: string;

      if (roll < 0.35) {
        palette = "gold";
        rgb = "245, 158, 11"; // Metallic Gold
      } else if (roll < 0.60) {
        palette = "white";
        rgb = "255, 255, 255"; // Soft White
      } else if (roll < 0.80) {
        palette = "cyan";
        rgb = "56, 189, 248"; // Cyan / Teal
      } else if (roll < 0.92) {
        palette = "coolBlue";
        rgb = "186, 215, 250"; // Cool Blue
      } else {
        palette = "amber";
        rgb = "251, 191, 36"; // Subtle Amber
      }

      const speed = (Math.random() * 0.4 + 0.6) * 0.00065;
      points.push({
        x: 0,
        y: 0,
        z: 0,
        baseRadius: radius * (0.82 + Math.random() * 0.36),
        theta,
        phi,
        speed,
        palette,
        rgb,
      });
    }

    let lastTime = performance.now();

    const render = (now: number) => {
      const delta = Math.min(32, now - lastTime);
      lastTime = now;

      // Handle high-DPI
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== size * dpr || canvas.height !== size * dpr) {
        canvas.width = size * dpr;
        canvas.height = size * dpr;
      }

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, size, size);

      const cx = size / 2;
      const cy = size / 2;

      // Intro phase animation scale
      let assembleProgress = 1.0;
      if (introPhase === 0) {
        assembleProgress = Math.min(1.0, introElapsed / 0.5);
      } else if (introPhase === 1) {
        assembleProgress = 1.0;
      }

      let speedFactor = 1.0;
      if (verificationState === "VERIFYING_PASSKEY") {
        speedFactor = 2.4;
      } else if (verificationState === "VERIFICATION_SUCCESS") {
        speedFactor = 0.5;
      } else if (verificationState === "VERIFICATION_FAILED") {
        speedFactor = 0.3;
      }

      rotationAngle.current += delta * 0.00075 * speedFactor;

      // Outer golden ambient glow
      const outerGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 1.3);
      outerGlow.addColorStop(0, "rgba(245, 158, 11, 0.08)");
      outerGlow.addColorStop(0.5, "rgba(56, 189, 248, 0.03)");
      outerGlow.addColorStop(1, "rgba(9, 14, 23, 0)");
      ctx.fillStyle = outerGlow;
      ctx.fillRect(0, 0, size, size);

      // Rotate and project points
      const rotY = rotationAngle.current;
      const tilt = ringTilt.current;
      const cosY = Math.cos(rotY);
      const sinY = Math.sin(rotY);
      const cosT = Math.cos(tilt);
      const sinT = Math.sin(tilt);

      const projected: Array<Point3D & { alpha: number; scale: number }> = [];

      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        p.phi += p.speed * delta * speedFactor;

        // Spherical to Cartesian
        const currentR = p.baseRadius * assembleProgress;
        const x0 = currentR * Math.sin(p.theta) * Math.cos(p.phi);
        const y0 = currentR * Math.sin(p.theta) * Math.sin(p.phi);
        const z0 = currentR * Math.cos(p.theta);

        // Rotate Y
        const x1 = x0 * cosY + z0 * sinY;
        const y1 = y0;
        const z1 = -x0 * sinY + z0 * cosY;

        // Tilt X
        const x2 = x1;
        const y2 = y1 * cosT - z1 * sinT;
        const z2 = y1 * sinT + z1 * cosT;

        // Perspective projection
        const fov = 380;
        const depth = fov / (fov + z2);
        const px = cx + x2 * depth;
        const py = cy + y2 * depth;

        const alpha = Math.max(0.08, Math.min(1.0, (z2 + radius) / (2 * radius)));
        projected.push({
          ...p,
          x: px,
          y: py,
          z: z2,
          alpha,
          scale: depth,
        });
      }

      // Sort back-to-front
      projected.sort((a, b) => a.z - b.z);

      // Draw faint connections
      ctx.lineWidth = 0.6;
      for (let i = 0; i < projected.length; i++) {
        const p1 = projected[i];
        for (let j = i + 1; j < projected.length; j++) {
          const p2 = projected[j];
          const dx = p1.x - p2.x;
          const dy = p1.y - p2.y;
          const distSq = dx * dx + dy * dy;
          if (distSq < (size * 0.16) * (size * 0.16)) {
            const lineAlpha = (1.0 - Math.sqrt(distSq) / (size * 0.16)) * Math.min(p1.alpha, p2.alpha) * 0.22;
            ctx.strokeStyle = `rgba(245, 158, 11, ${lineAlpha})`;
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
          }
        }
      }

      // Render nodes
      for (let i = 0; i < projected.length; i++) {
        const p = projected[i];
        const nodeRadius = (p.palette === "gold" ? 2.8 : 2.0) * p.scale;

        ctx.fillStyle = `rgba(${p.rgb}, ${p.alpha * 0.85})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(0.5, nodeRadius), 0, Math.PI * 2);
        ctx.fill();

        if (p.z > radius * 0.28) {
          ctx.fillStyle = `rgba(${p.rgb}, ${p.alpha * 0.32})`;
          ctx.beginPath();
          ctx.arc(p.x, p.y, nodeRadius * 2.1, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // State-Driven Verification Pulse Waves
      if (verificationState === "VERIFYING_PASSKEY") {
        const pulsePhase = (now % 1400) / 1400;
        const pulseR = radius * 0.35 + pulsePhase * radius * 0.85;
        ctx.beginPath();
        ctx.arc(cx, cy, pulseR, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(245, 158, 11, ${0.45 * (1 - pulsePhase)})`;
        ctx.lineWidth = 1.25;
        ctx.stroke();
      } else if (verificationState === "VERIFICATION_SUCCESS" || verificationState === "WORKSPACE_TRANSITION") {
        const successPhase = Math.min(1.0, ((now % 1600) / 1600));
        const successR = radius * 0.2 + successPhase * radius * 1.15;
        ctx.beginPath();
        ctx.arc(cx, cy, successR, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(16, 185, 129, ${0.65 * (1 - successPhase)})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      ctx.restore();
      animFrameId.current = requestAnimationFrame(render);
    };

    animFrameId.current = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animFrameId.current);
    };
  }, [size, verificationState, introPhase, introElapsed]);

  const logoSize = Math.round(size * 0.38);

  return (
    <div
      className="algofortis-core-wrapper"
      style={{
        width: size,
        height: size,
        position: "relative",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        userSelect: "none",
        pointerEvents: "none",
      }}
    >
      <canvas
        ref={canvasRef}
        style={{
          width: `${size}px`,
          height: `${size}px`,
          display: "block",
          position: "absolute",
          top: 0,
          left: 0,
        }}
      />
      <div
        style={{
          position: "relative",
          zIndex: 2,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          filter: "drop-shadow(0 0 12px rgba(245, 158, 11, 0.45))",
        }}
      >
        <img
          src="/algofortis_logo.png"
          alt="AlgoFortis"
          style={{
            width: `${logoSize}px`,
            height: `${logoSize}px`,
            objectFit: "contain",
          }}
        />
      </div>
    </div>
  );
};
