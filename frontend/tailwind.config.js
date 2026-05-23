/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        charcoal: {
          950: "#080b10",
          900: "#0d1118",
          850: "#111722",
          800: "#151d2a",
          700: "#243044",
        },
      },
      boxShadow: {
        panel: "0 18px 48px rgba(0, 0, 0, 0.28)",
      },
    },
  },
  plugins: [],
};
