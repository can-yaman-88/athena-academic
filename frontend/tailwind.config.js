import typography from "@tailwindcss/typography";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        // Inter for UI text; JetBrains Mono for the terminal, logs and metrics.
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        // Layered dark surfaces (mirror the CSS variables in index.css) so
        // components can use bg-surface / bg-elevated for a cohesive depth scale.
        surface: {
          DEFAULT: "#0e0e18",
          2: "#14141f",
        },
        elevated: "#171724",
        line: {
          DEFAULT: "rgba(255,255,255,0.07)",
          strong: "rgba(255,255,255,0.13)",
        },
        // Iris / violet primary — the new brand accent (replaces emerald).
        primary: {
          DEFAULT: "#8b7cf6",
          50: "#f2f0fe",
          100: "#e6e2fd",
          200: "#cfc7fb",
          300: "#b3a6f9",
          400: "#8b7cf6",
          500: "#6d5de0",
          600: "#5847c4",
          700: "#473a9e",
          800: "#3a3080",
          900: "#2e2763",
        },
        // Teal data/secondary accent for charts, metrics and positive deltas.
        accent: {
          DEFAULT: "#2dd4bf",
          300: "#5eead4",
          400: "#2dd4bf",
          500: "#14b8a6",
        },
      },
      boxShadow: {
        // Soft, layered elevation: tight contact + diffuse, plus a violet glow.
        card: "0 1px 2px rgba(0,0,0,0.45), 0 6px 16px rgba(0,0,0,0.38)",
        "card-hover": "0 1px 2px rgba(0,0,0,0.5), 0 16px 40px rgba(0,0,0,0.5)",
        glow: "0 0 0 1px rgba(139,124,246,0.4), 0 8px 28px rgba(139,124,246,0.22)",
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
            color: "rgb(228 228 235)",
            lineHeight: "1.55",
            "p, ul, ol, blockquote, pre": { marginTop: "0.5em", marginBottom: "0.5em" },
            "h1, h2, h3, h4": { marginTop: "0.8em", marginBottom: "0.35em" },
            a: { color: "rgb(179 166 249)" }, // primary-300
            code: {
              color: "rgb(179 166 249)",
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
