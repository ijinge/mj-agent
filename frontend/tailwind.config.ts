import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ["var(--font-serif-sc)", "Noto Serif SC", "serif"],
        sans: ["var(--font-sans-sc)", "Noto Sans SC", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "Menlo", "monospace"],
      },
      colors: {
        paper: "rgb(var(--c-paper) / <alpha-value>)",
        paperDeep: "rgb(var(--c-paper-deep) / <alpha-value>)",
        ink: "rgb(var(--c-ink) / <alpha-value>)",
        inkSoft: "rgb(var(--c-ink-soft) / <alpha-value>)",
        jade: {
          DEFAULT: "rgb(var(--c-jade) / <alpha-value>)",
          light: "rgb(var(--c-jade-light) / <alpha-value>)",
          dim: "rgb(var(--c-jade-dim) / <alpha-value>)",
        },
        cinnabar: "rgb(var(--c-cinnabar) / <alpha-value>)",
        silk: "rgb(var(--c-silk) / <alpha-value>)",
        bone: "rgb(var(--c-bone) / <alpha-value>)",
      },
      borderRadius: {
        ink: "12px",
        seal: "4px",
      },
      boxShadow: {
        paper: "0 1px 0 rgb(var(--c-silk) / 0.5), 0 4px 24px -8px rgb(var(--c-ink) / 0.08)",
        seal:
          "0 0 0 1px rgb(var(--c-cinnabar) / 0.2), 0 2px 12px -2px rgb(var(--c-cinnabar) / 0.3)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "ink-pulse": {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
        "sweep": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.6s cubic-bezier(0.16, 1, 0.3, 1) both",
        "ink-pulse": "ink-pulse 1.6s ease-in-out infinite",
        "sweep": "sweep 2.4s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
