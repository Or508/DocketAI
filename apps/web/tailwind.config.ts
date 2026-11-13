import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#f4f0e6",
        ink: "#16130f",
        line: "#cfc4ae",
        tide: "#0b3a38",
        clay: "#7a2e1e",
        moss: "#145c38",
        amberink: "#6e470c",
        mist: "#3c362e",
      },
      fontFamily: {
        serif: ['"Iowan Old Style"', "Palatino Linotype", "Palatino", "Georgia", "serif"],
        sans: ['"Segoe UI Variable"', "Segoe UI", "Avenir Next", "Trebuchet MS", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(28, 25, 21, 0.04), 0 18px 40px -28px rgba(28, 25, 21, 0.45)",
      },
    },
  },
  plugins: [],
};

export default config;
