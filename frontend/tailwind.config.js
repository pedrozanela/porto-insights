/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Consomem as CSS variables definidas em src/index.css (:root).
        primary: "var(--color-primary)",
        primaryDark: "var(--color-primary-dark)",
        accent: "var(--color-accent)",
        surface: "var(--color-surface)",
        surfaceMuted: "var(--color-surface-muted)",
        borderc: "var(--color-border)",
        textc: "var(--color-text)",
        muted: "var(--color-muted)",
      },
      fontFamily: {
        // Inter é adicionada (self-hosted) numa fase posterior; fallback de sistema por ora.
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      borderRadius: { xl: "0.75rem" },
      boxShadow: { soft: "0 1px 3px rgba(16,24,40,.06), 0 1px 2px rgba(16,24,40,.04)" },
    },
  },
  plugins: [],
};
