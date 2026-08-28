// Confetti — burst animation for celebratory feedback.
//
// When `trigger` increments, spawns 24 colorful particles that arc upward,
// rotate, and fade out over 600 ms.  Uses requestAnimationFrame + canvas
// for zero DOM churn.  Layer: fixed inset-0 pointer-events-none z-40.

import { useRef, useEffect } from "react";

// ---- Types ------------------------------------------------------------------

interface ConfettiProps {
  /** Fire a burst each time this value increments. */
  trigger: number;
}

interface Particle {
  /** Position relative to canvas centre (px). */
  x: number;
  y: number;
  /** Velocity (px/s). */
  vx: number;
  vy: number;
  /** HSL colour. */
  hue: number;
  sat: number;
  light: number;
  /** Current rotation (rad). */
  rotation: number;
  /** Rotational speed (rad/s). */
  rotationSpeed: number;
  /** Normalised life [1→0]. */
  life: number;
  /** Size of the confetti rectangle (px). */
  size: number;
}

// ---- Constants --------------------------------------------------------------

const PARTICLE_COUNT = 24;
const LIFETIME_MS = 600;
const GRAVITY = 900; // px/s²
const BASE_SPEED = 250; // px/s
const SPEED_SPREAD = 600; // px/s

// ---- Component --------------------------------------------------------------

export function Confetti({ trigger }: ConfettiProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const rafRef = useRef<number>(0);
  const prevTriggerRef = useRef(0);

  // Spawn a burst whenever trigger increments.
  useEffect(() => {
    if (trigger === prevTriggerRef.current) return;
    prevTriggerRef.current = trigger;

    const particles = particlesRef.current;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = BASE_SPEED + Math.random() * SPEED_SPREAD;
      particles.push({
        x: 0,
        y: 0,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 350, // upward bias so burst arcs
        hue: Math.random() * 360,
        sat: 65 + Math.random() * 35,
        light: 40 + Math.random() * 30,
        rotation: Math.random() * Math.PI * 2,
        rotationSpeed: (Math.random() - 0.5) * 24,
        life: 1,
        size: 5 + Math.random() * 5,
      });
    }
  }, [trigger]);

  // Continuous rAF loop: drives physics + renders to canvas.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Keep canvas sized to its container.
    function resize() {
      const parent = canvas!.parentElement;
      if (!parent) return;
      canvas!.width = parent.clientWidth;
      canvas!.height = parent.clientHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    let lastTime = performance.now();

    function tick(now: number) {
      const dtSec = Math.min((now - lastTime) / 1000, 0.05); // cap to avoid spiral
      lastTime = now;

      const w = canvas!.width;
      const h = canvas!.height;
      const cx = w / 2;
      const cy = h / 2;
      const particles = particlesRef.current;

      // Clear.
      ctx!.clearRect(0, 0, w, h);

      // Update and draw (backward iteration so splice is safe).
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i]!;

        // Decay life.
        p.life -= dtSec / (LIFETIME_MS / 1000);
        if (p.life <= 0) {
          particles.splice(i, 1);
          continue;
        }

        // Physics.
        p.x += p.vx * dtSec;
        p.y += p.vy * dtSec;
        p.vy += GRAVITY * dtSec;
        p.rotation += p.rotationSpeed * dtSec;

        // Draw — small rectangle with current rotation and fading alpha.
        ctx!.save();
        ctx!.translate(cx + p.x, cy + p.y);
        ctx!.rotate(p.rotation);
        ctx!.globalAlpha = Math.max(0, p.life);
        ctx!.fillStyle = `hsl(${p.hue}, ${p.sat}%, ${p.light}%)`;
        // Taller rectangle reads as confetti strip.
        ctx!.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.55);
        ctx!.restore();
      }

      rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none z-40"
    />
  );
}
