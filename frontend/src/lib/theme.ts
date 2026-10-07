import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";

function current(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(current);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("ml-theme", theme);
    } catch {
      /* storage unavailable */
    }
    window.dispatchEvent(new CustomEvent("ml-theme", { detail: theme }));
  }, [theme]);

  useEffect(() => {
    const onChange = (e: Event) => setTheme((e as CustomEvent<Theme>).detail);
    window.addEventListener("ml-theme", onChange);
    return () => window.removeEventListener("ml-theme", onChange);
  }, []);

  const toggle = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);
  return { theme, toggle };
}

/** Read a CSS custom property (used to theme canvas charts). */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
