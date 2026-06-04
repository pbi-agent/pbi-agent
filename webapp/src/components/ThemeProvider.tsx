import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AppTheme = "system" | "prism" | "light" | "dark";
type ResolvedTheme = Exclude<AppTheme, "system">;

const STORAGE_KEY = "pbi-agent-theme";
const SYSTEM_DARK_QUERY = "(prefers-color-scheme: dark)";

const THEMES: AppTheme[] = ["system", "prism", "light", "dark"];

type ThemeContextValue = {
  theme: AppTheme;
  setTheme: (theme: AppTheme) => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: "system",
  setTheme: () => {},
});

function readStoredTheme(): AppTheme {
  if (typeof window === "undefined") {
    return "system";
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return THEMES.includes(stored as AppTheme) ? (stored as AppTheme) : "system";
}

function resolveSystemTheme(): Exclude<AppTheme, "system" | "prism"> {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "light";
  }
  return window.matchMedia(SYSTEM_DARK_QUERY).matches ? "dark" : "light";
}

function resolveTheme(theme: AppTheme): ResolvedTheme {
  return theme === "system" ? resolveSystemTheme() : theme;
}

function applyTheme(theme: AppTheme): void {
  const resolvedTheme = resolveTheme(theme);
  const root = document.documentElement;
  root.dataset.theme = resolvedTheme;
  root.classList.toggle("dark", resolvedTheme !== "light");
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>(() => readStoredTheme());

  useEffect(() => {
    applyTheme(theme);
    window.localStorage.setItem(STORAGE_KEY, theme);

    if (theme !== "system" || typeof window.matchMedia !== "function") {
      return;
    }

    const mediaQuery = window.matchMedia(SYSTEM_DARK_QUERY);
    const handleSystemThemeChange = () => applyTheme("system");

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handleSystemThemeChange);
      return () => mediaQuery.removeEventListener("change", handleSystemThemeChange);
    }

    if (typeof mediaQuery.addListener === "function") {
      mediaQuery.addListener(handleSystemThemeChange);
      return () => mediaQuery.removeListener(handleSystemThemeChange);
    }
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
  { value: "system", label: "System" },
  { value: "prism", label: "Prism" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];