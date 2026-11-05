import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#f3efe6",
        ink: "#1c1915",
        line: "#e4dccb",
        tide: "#0f4c4a",
        clay: "#8f3d2a",
        moss: "#1f6b45",
        amberink: "#8a5a12",
        mist: "#6d665c",
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
