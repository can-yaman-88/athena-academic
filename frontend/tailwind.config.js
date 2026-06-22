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
        // Fira Code for the chatbox (matches Odysseus).
        chat: ["Fira Code", "ui-monospace", "JetBrains Mono", "monospace"],
      },
      colors: {
        // All theme colors resolve to CSS variables (RGB channels) defined in
        // index.css, so swapping the .theme-* class on <html> recolors every
        // utility — and the `rgb(var(--x) / <alpha-value>)` form keeps opacity
        // modifiers (e.g. bg-primary-500/15) working. Hairline `line` tokens
        // hold a baked-in alpha, so they map to the var directly.
        surface: {
          DEFAULT: "rgb(var(--surface) / <alpha-value>)",
          2: "rgb(var(--surface-2) / <alpha-value>)",
        },
        elevated: "rgb(var(--elevated-solid) / <alpha-value>)",
        line: {
          DEFAULT: "var(--line)",
          strong: "var(--line-strong)",
        },
        primary: {
          DEFAULT: "rgb(var(--primary) / <alpha-value>)",
          50: "rgb(var(--primary-50) / <alpha-value>)",
          100: "rgb(var(--primary-100) / <alpha-value>)",
          200: "rgb(var(--primary-200) / <alpha-value>)",
          300: "rgb(var(--primary-300) / <alpha-value>)",
          400: "rgb(var(--primary-400) / <alpha-value>)",
          500: "rgb(var(--primary-500) / <alpha-value>)",
          600: "rgb(var(--primary-600) / <alpha-value>)",
          700: "rgb(var(--primary-700) / <alpha-value>)",
          800: "rgb(var(--primary-800) / <alpha-value>)",
          900: "rgb(var(--primary-900) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          300: "rgb(var(--accent-300) / <alpha-value>)",
          400: "rgb(var(--accent-400) / <alpha-value>)",
          500: "rgb(var(--accent-500) / <alpha-value>)",
        },
      },
      boxShadow: {
        // Soft, layered elevation: tight contact + diffuse, plus a themed glow.
        card: "0 1px 2px rgba(0,0,0,0.45), 0 6px 16px rgba(0,0,0,0.38)",
        "card-hover": "0 1px 2px rgba(0,0,0,0.5), 0 16px 40px rgba(0,0,0,0.5)",
        glow: "0 0 0 1px rgb(var(--primary) / 0.4), 0 8px 28px rgb(var(--primary) / 0.22)",
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
