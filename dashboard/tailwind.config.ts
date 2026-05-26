import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        sidebar: "#0B0F1A",
        accent: "#00D4FF",
        success: "#00E5A0",
        warning: "#FFB800",
        danger: "#FF4444",
        surface: "#111827",
        "surface-2": "#1F2937",
        border: "#1E2A3A",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
