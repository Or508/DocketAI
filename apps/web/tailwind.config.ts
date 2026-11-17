import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // The page canvas: a quiet warm white, so white cards read as raised.
        paper: "#f6f6f3",
        ink: "#1b1a17",
        line: "#e4e2dc",
        tide: "#0e4f49",
        // A soft tint of the brand green, for selected rows and active navigation.
        mint: "#e6f1ef",
        clay: "#a03a22",
        moss: "#17663f",
        amberink: "#8a5a12",
        // Secondary text: clearly lighter than ink, still AA on white.
        mist: "#67625a",
      },
      fontFamily: {
        // One Hebrew-first family everywhere. Headings that still say font-serif get it too,
        // because the old serif stack had no Hebrew letters and fell back to a system serif.
        sans: ["var(--font-sans)", "Segoe UI", "Arial", "sans-serif"],
        serif: ["var(--font-sans)", "Segoe UI", "Arial", "sans-serif"],
      },
      borderRadius: {
        md: "0.5rem",
        lg: "0.875rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(20, 18, 14, 0.04), 0 6px 20px -12px rgba(20, 18, 14, 0.12)",
        lift: "0 2px 4px rgba(20, 18, 14, 0.05), 0 16px 32px -16px rgba(20, 18, 14, 0.22)",
      },
    },
  },
  plugins: [],
};

export default config;
