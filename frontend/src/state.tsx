import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type DatasetView } from "./api";
import { setCurrency } from "./format";

type Theme = "light" | "dark";

interface AppState {
  dataset: DatasetView | null;
  refreshDataset: () => Promise<void>;
  setDataset: (d: DatasetView) => void;
  version: number;              // bumps whenever data or dispositions change
  bump: () => void;
  analyst: string;
  setAnalyst: (s: string) => void;
  theme: Theme;
  toggleTheme: () => void;
}

const Ctx = createContext<AppState | null>(null);

function readLS(key: string, fallback: string): string {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function writeLS(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* storage unavailable */ }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [dataset, setDatasetState] = useState<DatasetView | null>(null);
  const [version, setVersion] = useState(0);
  const [analyst, setAnalystState] = useState(() => readLS("mt-analyst", "Analyst"));
  const [theme, setTheme] = useState<Theme>(() =>
    (document.documentElement.getAttribute("data-theme") as Theme) || "light");

  const setDataset = useCallback((d: DatasetView) => {
    setCurrency(d.currency, d.symbol);
    setDatasetState(d);
    setVersion((v) => v + 1);
  }, []);
  const refreshDataset = useCallback(async () => { setDataset(await api.current()); }, [setDataset]);
  useEffect(() => { refreshDataset().catch(() => setDatasetState({ dataset: null } as DatasetView)); }, [refreshDataset]);

  const setAnalyst = (s: string) => { setAnalystState(s); writeLS("mt-analyst", s); };
  const toggleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    writeLS("mt-theme", next);
    setTheme(next);
  };

  return (
    <Ctx.Provider value={{ dataset, refreshDataset, setDataset, version, bump: () => setVersion((v) => v + 1),
      analyst, setAnalyst, theme, toggleTheme }}>
      {children}
    </Ctx.Provider>
  );
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside provider");
  return v;
}

/** Small data hook: loads on mount and whenever deps change. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let live = true;
    setLoading(true);
    fn().then((d) => { if (live) { setData(d); setError(null); } })
      .catch((e) => { if (live) setError(e.message || String(e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading, setData };
}
