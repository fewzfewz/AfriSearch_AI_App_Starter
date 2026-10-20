import colors from "tailwindcss/colors";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: colors.orange, // 700 is the AfriSearch terracotta, #c2410c
        ink: colors.stone,
      },
      fontFamily: {
        sans: ["Inter", "Noto Sans Ethiopic", "ui-sans-serif", "system-ui", "sans-serif"],
        // Headlines: a warm, editorial serif.
        display: ["Fraunces", "Noto Sans Ethiopic", "ui-serif", "Georgia", "serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgb(28 25 23 / 0.04), 0 4px 16px -4px rgb(28 25 23 / 0.08)",
        lift: "0 2px 4px rgb(28 25 23 / 0.04), 0 12px 32px -8px rgb(28 25 23 / 0.16)",
        glow: "0 8px 24px -6px rgb(194 65 12 / 0.45)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
        "scale-in": { from: { opacity: "0", transform: "scale(0.97)" }, to: { opacity: "1", transform: "none" } },
        "slide-in": { from: { transform: "translateX(-100%)" }, to: { transform: "none" } },
        shimmer: { from: { backgroundPosition: "200% 0" }, to: { backgroundPosition: "-200% 0" } },
        blink: { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0" } },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out",
        "scale-in": "scale-in 0.16s ease-out",
        "slide-in": "slide-in 0.22s cubic-bezier(0.2, 0.8, 0.2, 1)",
        shimmer: "shimmer 2.2s linear infinite",
        blink: "blink 1s step-end infinite",
      },
    },
  },
  plugins: [],
};
