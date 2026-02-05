import { create } from "zustand";

type Theme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  initTheme: () => void;
}

const THEME_STORAGE_KEY = "momentloop-theme";

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: "light",

  setTheme: (theme: Theme) => {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    set({ theme });
  },

  toggleTheme: () => {
    const currentTheme = get().theme;
    get().setTheme(currentTheme === "light" ? "dark" : "light");
  },

  initTheme: () => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY) as Theme | null;
    const theme = stored || "light";
    get().setTheme(theme);
  },
}));

// Initialize theme on app load
useThemeStore.getState().initTheme();
