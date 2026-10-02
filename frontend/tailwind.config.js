/** Semantic design tokens: every colour maps to a CSS variable defined per theme in index.css. */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        page: v("page"),
        surface: v("surface"),
        raised: v("raised"),
        sunken: v("sunken"),
        line: v("line"),
        "line-strong": v("line-strong"),
        ink: v("ink"),
        ink2: v("ink2"),
        muted: v("muted"),
        accent: v("accent"),
        "accent-ink": v("accent-ink"),
        "accent-soft": v("accent-soft"),
        "on-accent": v("on-accent"),
        high: v("high"),
        "high-ink": v("high-ink"),
        "high-soft": v("high-soft"),
        "high-fill": v("high-fill"),
        "on-high": v("on-high"),
        medium: v("medium"),
        "medium-ink": v("medium-ink"),
        "medium-soft": v("medium-soft"),
        low: v("low"),
        "low-ink": v("low-ink"),
        "low-soft": v("low-soft"),
        good: v("good"),
        "good-ink": v("good-ink"),
        "good-soft": v("good-soft"),
        trace: v("trace"),
        ident: v("ident"),
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", '"Segoe UI"', "Roboto", "sans-serif"],
        mono: ['"Cascadia Mono"', "Consolas", "ui-monospace", "monospace"],
      },
      fontSize: { "2xs": ["0.75rem", "1rem"] },
      boxShadow: { card: "0 1px 0 rgb(var(--shadow) / 0.04), 0 1px 3px rgb(var(--shadow) / 0.06)" },
    },
  },
  plugins: [],
};
