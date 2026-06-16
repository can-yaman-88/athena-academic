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
      boxShadow: {
        card: "0 4px 6px rgba(0,0,0,0.25)",
        "card-hover": "0 10px 20px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};
