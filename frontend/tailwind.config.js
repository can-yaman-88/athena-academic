import typography from "@tailwindcss/typography";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        // Inter for UI text (design-system recommendation); mono kept for the
        // terminal, logs and code-like inputs.
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        // Layered dark surfaces (mirror the CSS variables in index.css) so
        // components can use bg-surface / bg-elevated for a cohesive depth scale.
        surface: {
          DEFAULT: "#0e0e11",
          2: "#131316",
        },
        elevated: "#161619",
        line: {
          DEFAULT: "rgba(255,255,255,0.07)",
          strong: "rgba(255,255,255,0.12)",
        },
      },
      boxShadow: {
        // Soft, layered elevation (Linear/Vercel feel): tight contact + diffuse.
        card: "0 1px 2px rgba(0,0,0,0.4), 0 4px 12px rgba(0,0,0,0.35)",
        "card-hover": "0 1px 2px rgba(0,0,0,0.5), 0 12px 32px rgba(0,0,0,0.45)",
        glow: "0 0 0 1px rgba(16,185,129,0.35), 0 6px 24px rgba(16,185,129,0.18)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 220ms ease both",
      },
      typography: {
        // Compact, dark-tuned defaults for rich notes / markdown chat so the
        // `prose prose-invert` content (editor, task & workout notes, chat) reads
        // well without the plugin's generous default spacing.
        DEFAULT: {
          css: {
            maxWidth: "none",
            color: "rgb(228 228 231)", // zinc-200
            lineHeight: "1.55",
            "p, ul, ol, blockquote, pre": { marginTop: "0.5em", marginBottom: "0.5em" },
            "h1, h2, h3, h4": { marginTop: "0.8em", marginBottom: "0.35em" },
            a: { color: "rgb(110 231 183)" }, // emerald-300
            code: {
              color: "rgb(110 231 183)",
              backgroundColor: "rgba(255,255,255,0.06)",
              padding: "0.15em 0.35em",
              borderRadius: "0.3em",
              fontWeight: "500",
            },
            "code::before": { content: '""' },
            "code::after": { content: '""' },
            pre: {
              backgroundColor: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
            },
          },
        },
      },
    },
  },
  plugins: [typography],
};
