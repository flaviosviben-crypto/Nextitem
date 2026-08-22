import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        plane: "var(--plane)",
        surface: "var(--surface)",
        raised: "var(--raised)",
        line: "var(--line)",
        ink: "var(--ink)",
        "ink-2": "var(--ink-2)",
        "ink-3": "var(--ink-3)",
        accent: "var(--accent)",
        good: "var(--good)",
        warning: "var(--warning)",
        serious: "var(--serious)",
        critical: "var(--critical)",
      },
      fontFamily: { sans: ["var(--font-sans)"], mono: ["var(--font-mono)"] },
      borderRadius: { xl: "12px", "2xl": "16px" },
      fontSize: {
        micro: ["11px", { lineHeight: "16px", letterSpacing: "0.02em" }],
      },
    },
  },
  plugins: [],
};
export default config;
