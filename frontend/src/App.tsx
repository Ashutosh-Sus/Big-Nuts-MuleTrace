import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Database, LayoutDashboard, ListChecks, Moon, Search, ShieldOff, Sun, UserRound } from "lucide-react";
import { api, type Severity } from "./api";
import { SeverityBadge } from "./components/Badges";
import { useApp } from "./state";
import Overview from "./pages/Overview";
import Queue from "./pages/Queue";
import DataPage from "./pages/DataPage";
import Investigate from "./pages/Investigate";
import CasePage from "./pages/CasePage";
import Reviewed from "./pages/Reviewed";

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2 pr-4">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="6" className="fill-accent" />
        <circle cx="8" cy="10" r="3" fill="#f3f1ea" /><circle cx="16" cy="22" r="3" fill="#f3f1ea" />
        <circle cx="24" cy="10" r="3" fill="#f3f1ea" />
        <path d="M10 12l4 8M18 20l4-8" stroke="#f3f1ea" strokeWidth="2" fill="none" />
      </svg>
      <div className="leading-tight">
        <div className="text-[15px] font-bold tracking-tight">MuleTrace</div>
        <div className="text-2xs text-muted">Mule-network investigation</div>
      </div>
    </Link>
  );
}

function AccountSearch() {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<{ id: string; flagged: boolean; score: number; severity: Severity | null }[]>([]);
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!q.trim()) { setItems([]); return; }
    const h = setTimeout(() => api.search(q.trim()).then((r) => setItems(r.items)).catch(() => setItems([])), 150);
    return () => clearTimeout(h);
  }, [q]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const go = (id: string) => { setOpen(false); setQ(""); nav(`/account/${encodeURIComponent(id)}`); };
  return (
    <div ref={box} className="relative w-full max-w-xs">
      <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
      <input className="input w-full pl-8" placeholder="Find any account…" value={q} aria-label="Find account"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" && items[0]) go(items[0].id); if (e.key === "Escape") setOpen(false); }} />
      {open && items.length > 0 && (
        <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border border-line bg-raised shadow-card">
          {items.map((i) => (
            <button key={i.id} onClick={() => go(i.id)}
              className="flex w-full items-center justify-between px-3 py-1.5 text-left text-sm hover:bg-sunken">
              <span className="font-mono text-[13px]">{i.id}</span>
              <SeverityBadge severity={i.severity} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const { dataset, analyst, setAnalyst, theme, toggleTheme } = useApp();
  const navCls = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-1.5 sm:px-2.5 text-[13px] font-medium ${isActive ? "bg-sunken text-ink" : "text-ink2 hover:text-ink hover:bg-sunken/60"}`;
  const loaded = dataset?.dataset != null;
  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-40 border-b border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-3 px-4 py-2">
          <Brand />
          <nav className="flex flex-wrap items-center gap-1">
            <NavLink to="/" end className={navCls}><LayoutDashboard size={15} /> Overview</NavLink>
            <NavLink to="/queue" className={navCls}><ListChecks size={15} /> Queue</NavLink>
            <NavLink to="/reviewed" className={navCls}><ShieldOff size={15} /> Not flagged</NavLink>
            <NavLink to="/data" className={navCls}><Database size={15} /> Data</NavLink>
          </nav>
          <div className="ml-auto flex flex-1 items-center justify-end gap-3">
            <AccountSearch />
            <label className="hidden items-center gap-1.5 md:flex" title="Analyst name recorded with each decision">
              <UserRound size={15} className="text-muted" />
              <input className="input w-32 py-1" value={analyst} onChange={(e) => setAnalyst(e.target.value)}
                aria-label="Analyst name" />
            </label>
            <button className="btn btn-ghost px-2" onClick={toggleTheme} aria-label="Toggle colour theme"
              title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1680px] flex-1 px-4 py-4">
        {dataset == null ? <div className="py-20 text-center text-muted">Connecting…</div> : (
          <Routes>
            <Route path="/" element={loaded ? <Overview /> : <Navigate to="/data" replace />} />
            <Route path="/queue" element={loaded ? <Queue /> : <Navigate to="/data" replace />} />
            <Route path="/reviewed" element={loaded ? <Reviewed /> : <Navigate to="/data" replace />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="/account/:id" element={<Investigate />} />
            <Route path="/case/:id" element={<CasePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>
      <footer className="border-t border-line px-4 py-2 text-center text-2xs text-muted">
        Deterministic rule-based analysis · scores are evidence-strength indices, not probabilities of fraud
        {dataset?.dataset && <> · config {dataset.dataset.config_hash} · engine {dataset.dataset.engine}</>}
      </footer>
    </div>
  );
}
