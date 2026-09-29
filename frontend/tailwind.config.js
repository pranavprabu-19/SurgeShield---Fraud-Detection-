/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,jsx}", "./components/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#070b14",
        panel: "#0d1424",
        raised: "#121a2e",
        line: "#1c2740",
        mint: "#3ee0c5",
        ember: "#fb7185",
        amber: "#fbbf24",
        ok: "#34d399",
        low: "#38bdf8",
        high: "#fb923c",
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
