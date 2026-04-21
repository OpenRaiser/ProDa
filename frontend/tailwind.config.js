/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // VSCode Dark+ palette
        vs: {
          bg: "#1e1e1e",            // editor background
          sidebar: "#252526",       // sidebar / explorer
          panel: "#2d2d30",         // inactive tabs / inputs
          title: "#3c3c3c",         // title bar
          activity: "#333333",      // activity bar
          status: "#007acc",        // status bar blue
          border: "#3c3c3c",        // dividers
          "border-dim": "#252526",
          hover: "#2a2d2e",         // list item hover
          selected: "#094771",      // selected list item
          input: "#3c3c3c",
          "input-border": "#3c3c3c",
          tabActive: "#1e1e1e",
          tabInactive: "#2d2d30",
          tabBorder: "#252526",
        },
        fg: {
          DEFAULT: "#cccccc",
          muted: "#9d9d9d",
          dim: "#6e6e6e",
          strong: "#ffffff",
          accent: "#3794ff",       // links / focus blue
          success: "#4ec9b0",
          warning: "#dcdcaa",
          error: "#f48771",
          symbol: "#c586c0",       // purple accent (Cursor feel)
        },
      },
      fontFamily: {
        ui: [
          "Segoe UI",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Inter",
          "Helvetica Neue",
          "sans-serif",
        ],
        mono: [
          "Cascadia Code",
          "JetBrains Mono",
          "Fira Code",
          "Consolas",
          "Menlo",
          "Monaco",
          "monospace",
        ],
      },
      fontSize: {
        xxs: ["10px", "14px"],
      },
      boxShadow: {
        panel: "0 2px 8px rgba(0,0,0,0.3)",
        popover: "0 4px 16px rgba(0,0,0,0.4)",
      },
    },
  },
  plugins: [],
};
