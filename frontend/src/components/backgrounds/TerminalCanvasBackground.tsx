import { useEffect, useRef } from "react";

/**
 * Terminal "Perlin flow" background — particles drifting along a smooth-noise
 * flow field with a trailing fade, ported from Odysseus
 * `theme.js::_initPerlinFlow` (+ its `_bgSmoothNoise` helper). Particle color
 * comes from `--bg-effect-color`; the trailing fade is built from `--bg`
 * (stored as "R G B" channels).
 *
 * Fixed, non-interactive canvas behind the app; rAF + resize torn down on unmount.
 */
export default function TerminalCanvasBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let W = 0;
    let H = 0;
    let t = 0;
    let raf = 0;
    let particles: { x: number; y: number; life: number }[] = [];

    const resize = () => {
      W = window.innerWidth;
      H = window.innerHeight;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (particles.length === 0) {
        for (let i = 0; i < 200; i++) {
          particles.push({ x: Math.random() * W, y: Math.random() * H, life: Math.random() });
        }
      }
    };
    resize();
    window.addEventListener("resize", resize);

    const css = () => getComputedStyle(document.documentElement);
    const getColor = () =>
      css().getPropertyValue("--bg-effect-color").trim() ||
      css().getPropertyValue("--ring").trim() ||
      "#00ff41";

    // `--bg` is stored as space-separated RGB channels ("r g b").
    let cachedBgVar = "";
    let fadeStyle = "rgba(0,0,0,0.04)";
    const getFade = () => {
      const bg = css().getPropertyValue("--bg").trim();
      if (bg && bg !== cachedBgVar) {
        cachedBgVar = bg;
        const [r, g, b] = bg.split(/\s+/).map((n) => parseInt(n, 10));
        if ([r, g, b].every((n) => Number.isFinite(n))) {
          fadeStyle = `rgba(${r},${g},${b},0.04)`;
        }
      }
      return fadeStyle;
    };

    const noise2d = (x: number, y: number) => {
      const n = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453;
      return n - Math.floor(n);
    };
    const smoothNoise = (x: number, y: number) => {
      const ix = Math.floor(x);
      const iy = Math.floor(y);
      const fx = x - ix;
      const fy = y - iy;
      const a = noise2d(ix, iy);
      const b = noise2d(ix + 1, iy);
      const cc = noise2d(ix, iy + 1);
      const d = noise2d(ix + 1, iy + 1);
      const ux = fx * fx * (3 - 2 * fx);
      const uy = fy * fy * (3 - 2 * fy);
      return a + (b - a) * ux + (cc - a) * uy + (a - b - cc + d) * ux * uy;
    };

    const draw = () => {
      raf = requestAnimationFrame(draw);
      ctx.fillStyle = getFade();
      ctx.fillRect(0, 0, W, H);
      const c = getColor();

      particles.forEach((p) => {
        const n = smoothNoise(p.x * 0.004 + t * 0.0008, p.y * 0.004 + 100);
        const angle = n * Math.PI * 6;
        const speed = 1 + smoothNoise(p.x * 0.003, p.y * 0.003 + 50) * 1.5;
        p.x += Math.cos(angle) * speed;
        p.y += Math.sin(angle) * speed;
        p.life -= 0.001;
        if (p.life <= 0 || p.x < 0 || p.x > W || p.y < 0 || p.y > H) {
          p.x = Math.random() * W;
          p.y = Math.random() * H;
          p.life = 1;
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, 1, 0, Math.PI * 2);
        ctx.fillStyle = c;
        ctx.globalAlpha = p.life * 0.15;
        ctx.fill();
      });
      ctx.globalAlpha = 1;
      t++;
    };
    draw();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      particles = [];
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
