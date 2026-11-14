/* Light/dark theme. The choice is saved; without one, the system preference applies. */
export type Theme = "light" | "dark";
const KEY = "dayfold.theme";

export function savedTheme(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

export function effectiveTheme(): Theme {
  return savedTheme() ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(KEY, theme); } catch { /* ignore */ }
}

// Apply the saved choice before first paint.
const s = savedTheme();
if (s) document.documentElement.dataset.theme = s;
