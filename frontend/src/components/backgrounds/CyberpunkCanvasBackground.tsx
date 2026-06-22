import { useEffect, useRef } from "react";

/**
 * Cyberpunk "Synapse" background — grid-aligned neon pulses with trailing glow,
 * ported from Odysseus `theme.js::_initSynapse`. Particle color is read live
 * from the `--bg-effect-color` CSS variable so it tracks the active theme.
 *
 * Rendered as a fixed, non-interactive canvas behind the app. The rAF loop and
 * resize listener are torn down on unmount.
 */
export default function CyberpunkCanvasBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const GRID = 24;
    const MAX_PULSES = 20;
    const SPEED_MIN = 2;
    const SPEED_MAX = 22;
    const TRAIL_LEN = 12;

    let W = 0;
    let H = 0;
    let cols = 0;
    let rows = 0;
    let pulses: { x: number; y: number; dx: number; dy: number }[] = [];
    let raf = 0;

    const resize = () => {
      W = window.innerWidth;
      H = window.innerHeight;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cols = Math.ceil(W / GRID);
      rows = Math.ceil(H / GRID);
    };
    resize();
    window.addEventListener("resize", resize);

    const getColor = () => {
      const s = getComputedStyle(document.documentElement);
      return (
        s.getPropertyValue("--bg-effect-color").trim() ||
        s.getPropertyValue("--ring").trim() ||
        "#0ff0fc"
      );
    };

    const spawnPulse = () => {
      const speed = SPEED_MIN + Math.random() * (SPEED_MAX - SPEED_MIN);
      if (Math.random() > 0.5) {
        const row = Math.floor(Math.random() * (rows + 1));
        pulses.push({ x: -TRAIL_LEN, y: row * GRID, dx: speed, dy: 0 });
      } else {
        const col = Math.floor(Math.random() * (cols + 1));
        pulses.push({ x: col * GRID, y: -TRAIL_LEN, dx: 0, dy: speed });
      }
    };

    const draw = () => {
      raf = requestAnimationFrame(draw);
      ctx.clearRect(0, 0, W, H);
      const c = getColor();

      if (pulses.length < MAX_PULSES && Math.random() < 0.12) spawnPulse();

      for (let i = pulses.length - 1; i >= 0; i--) {
        const p = pulses[i];
        p.x += p.dx;
        p.y += p.dy;
        if (p.x > W + TRAIL_LEN || p.y > H + TRAIL_LEN) {
          pulses.splice(i, 1);
          continue;
        }
        const tx = p.x - (p.dx > 0 ? TRAIL_LEN : 0);
        const ty = p.y - (p.dy > 0 ? TRAIL_LEN : 0);
        const grad = ctx.createLinearGradient(tx, ty, p.x, p.y);
        grad.addColorStop(0, "transparent");
        grad.addColorStop(1, c);
        ctx.strokeStyle = grad;
        ctx.globalAlpha = 0.35;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(tx, ty);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();

        ctx.globalAlpha = 0.55;
        ctx.fillStyle = c;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 1.2, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };
    draw();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      pulses = [];
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 h-full w-full"
    />
  );
}
