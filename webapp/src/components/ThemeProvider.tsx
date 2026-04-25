import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AppTheme = "prism" | "light" | "dark";

const STORAGE_KEY = "pbi-agent-theme";

const THEMES: AppTheme[] = ["prism", "light", "dark"];

type ThemeContextValue = {
  theme: AppTheme;
  setTheme: (theme: AppTheme) => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: "prism",
  setTheme: () => {},
});

function readStoredTheme(): AppTheme {
  if (typeof window === "undefined") {
    return "prism";
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return THEMES.includes(stored as AppTheme) ? (stored as AppTheme) : "prism";
}

function applyTheme(theme: AppTheme): void {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.classList.toggle("dark", theme !== "light");
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>(() => readStoredTheme());

  useEffect(() => {
    applyTheme(theme);
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const setTheme = useCallback((nextTheme: AppTheme) => {
    setThemeState(nextTheme);
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [setTheme, theme]);

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

export const themeOptions: Array<{ value: AppTheme; label: string }> = [
  { value: "prism", label: "Prism" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];