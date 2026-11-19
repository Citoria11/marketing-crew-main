/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Rustic Country dark palette
        saddle:  { DEFAULT: "#8B4513", light: "#A0522D", dark: "#5C2D0A" },
        haystack: { DEFAULT: "#D4A035", light: "#E8B84B", dark: "#A07820" },
        dusk:    { DEFAULT: "#1A1008", light: "#2A1C10", dark: "#0D0804" },
        ember:   { DEFAULT: "#C0392B", light: "#E74C3C", dark: "#922B21" },
        pine:    { DEFAULT: "#1E4D2B", light: "#276239", dark: "#143521" },
        parchment: { DEFAULT: "#F5E6C8", light: "#FFF3DC", dark: "#D4C4A0" },
      },
      fontFamily: {
        serif: ['"Playfair Display"', '"Georgia"', "serif"],
        sans:  ['"Inter"', '"Helvetica Neue"', "sans-serif"],
        mono:  ['"JetBrains Mono"', '"Courier New"', "monospace"],
      },
      backgroundImage: {
        "rustic-texture": "url('/wood-texture.svg')",
      },
      boxShadow: {
        glow: "0 0 12px rgba(212,160,53,0.45)",
        "glow-sm": "0 0 6px rgba(212,160,53,0.30)",
      },
      animation: {
        "spin-slow": "spin 3s linear infinite",
        "pulse-amber": "pulseAmber 2s ease-in-out infinite",
      },
      keyframes: {
        pulseAmber: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
      },
    },
  },
  plugins: [],
};
