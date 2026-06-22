import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type ThemeName = "aurora" | "cyberpunk" | "terminal";

export const THEMES: { id: ThemeName; label: string }[] = [
  { id: "aurora", label: "Aurora" },
  { id: "cyberpunk", label: "Cyberpunk" },
  { id: "terminal", label: "Terminal" },
];

const STORAGE_KEY = "jarvis_theme";

interface ThemeState {
  theme: ThemeName;
  setTheme: (t: ThemeName) => void;
}

const ThemeCtx = createContext<ThemeState | null>(null);

function applyThemeClass(theme: ThemeName) {
  const el = document.documentElement;
  el.classList.remove("theme-aurora", "theme-cyberpunk", "theme-terminal");
  el.classList.add(`theme-${theme}`);
}

function readInitialTheme(): ThemeName {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === "aurora" || saved === "cyberpunk" || saved === "terminal") {
    return saved;
  }
  return "aurora";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeName>(readInitialTheme);

  // Apply the class up-front and whenever the theme changes.
  useEffect(() => {
    applyThemeClass(theme);
  }, [theme]);

  const setTheme = useCallback((t: ThemeName) => {
    setThemeState(t);
    try {
      localStorage.setItem(STORAGE_KEY, t);
    } catch {
      /* storage may be unavailable; theme still applies for the session */
    }
  }, []);

  return <ThemeCtx.Provider value={{ theme, setTheme }}>{children}</ThemeCtx.Provider>;
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
