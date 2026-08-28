import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Theme = "dark" | "light";

interface ThemeContextValue {
  theme: Theme;
  highContrast: boolean;
  setTheme: (theme: Theme) => void;
  setHighContrast: (enabled: boolean) => void;
  toggle: () => void;
  toggleHighContrast: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);
const STORAGE_KEY = "melosviz-theme";
export const HIGH_CONTRAST_STORAGE_KEY = "melosviz-high-contrast";

export function applyDocumentTheme(theme: Theme, highContrast: boolean): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  if (highContrast) {
    document.documentElement.dataset.highContrast = "true";
  } else {
    delete document.documentElement.dataset.highContrast;
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return "dark";
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "light" ? "light" : "dark";
  });
  const [highContrast, setHighContrastState] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(HIGH_CONTRAST_STORAGE_KEY) === "true";
  });

  useEffect(() => {
    applyDocumentTheme(theme, highContrast);
    window.localStorage.setItem(STORAGE_KEY, theme);
    window.localStorage.setItem(
      HIGH_CONTRAST_STORAGE_KEY,
      highContrast ? "true" : "false",
    );
  }, [theme, highContrast]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
  }, []);

  const setHighContrast = useCallback((enabled: boolean) => {
    setHighContrastState(enabled);
  }, []);

  const toggle = useCallback(() => {
    setThemeState((t) => (t === "dark" ? "light" : "dark"));
  }, []);

  const toggleHighContrast = useCallback(() => {
    setHighContrastState((v) => !v);
  }, []);

  const value = useMemo(
    () => ({
      theme,
      highContrast,
      setTheme,
      setHighContrast,
      toggle,
      toggleHighContrast,
    }),
    [
      theme,
      highContrast,
      setTheme,
      setHighContrast,
      toggle,
      toggleHighContrast,
    ],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
