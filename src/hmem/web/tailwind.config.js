/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Node type colors
        conversation: "#64748b",
        entity: "#f97316",
        fact: "#eab308",
        process: "#06b6d4",
        principle: "#a855f7",
        skill: "#22c55e",
      },
    },
  },
  plugins: [],
};
