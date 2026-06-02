import type { Config } from "tailwindcss";

/**
 * FinAlly terminal theme.
 *
 * Aesthetic: refined industrial trading desk. A deep carbon base (no pure
 * black), hairline gray panel borders, amber as the signature "live" accent,
 * electric blue for interactive/selected state, purple for commit actions, and
 * semantic green/red reserved exclusively for price/P&L direction so they read
 * as data, never decoration.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Surfaces — layered carbon, increasing elevation toward the user.
        base: "#0d1117",
        surface: "#11161f",
        panel: "#151b26",
        elevated: "#1a2230",
        hairline: "#232c3b",
        hairlineStrong: "#2f3a4d",

        // Brand accents (from PLAN §2 color scheme).
        amber: "#ecad0a",
        blue: "#209dd7",
        purple: "#753991",

        // Semantic market direction.
        up: "#1fd49a",
        upDim: "#0f7a5a",
        down: "#ff5d6c",
        downDim: "#9e2f3a",

        // Text ramp.
        ink: "#e9edf4",
        inkMute: "#9aa6ba",
        inkFaint: "#5c6878",
      },
      fontFamily: {
        // Distinctive display for headers; high-quality monospace for all data.
        display: ['"Space Grotesk"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', '"SFMono-Regular"', "Menlo", "monospace"],
      },
      fontSize: {
        micro: ["10px", { lineHeight: "12px", letterSpacing: "0.08em" }],
        data: ["13px", { lineHeight: "16px" }],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(236,173,10,0.25), 0 0 24px -6px rgba(236,173,10,0.45)",
        panel: "0 1px 0 0 rgba(255,255,255,0.02) inset, 0 12px 32px -16px rgba(0,0,0,0.8)",
      },
      keyframes: {
        flashUp: {
          "0%": { backgroundColor: "rgba(31,212,154,0.28)" },
          "100%": { backgroundColor: "rgba(31,212,154,0)" },
        },
        flashDown: {
          "0%": { backgroundColor: "rgba(255,93,108,0.28)" },
          "100%": { backgroundColor: "rgba(255,93,108,0)" },
        },
        pulseDot: {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
        riseIn: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        flashUp: "flashUp 600ms ease-out",
        flashDown: "flashDown 600ms ease-out",
        pulseDot: "pulseDot 1.8s ease-in-out infinite",
        riseIn: "riseIn 320ms ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
