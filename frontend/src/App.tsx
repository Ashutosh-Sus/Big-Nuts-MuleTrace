import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Database, LayoutDashboard, ListChecks, Moon, Search, ShieldOff, Sun, UserRound } from "lucide-react";
import { api, type Severity } from "./api";
import { bestMatch, currentItems, enterAction, normalise, type SearchResults } from "./lib/search";
import { accountPath } from "./lib/paths";
import { SeverityBadge } from "./components/Badges";
import { useApp } from "./state";
import Overview from "./pages/Overview";
import Queue from "./pages/Queue";
import DataPage from "./pages/DataPage";
import Investigate from "./pages/Investigate";
import CasePage from "./pages/CasePage";
import Cases from "./pages/Cases";
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
        <div className="hidden text-2xs text-muted sm:block">Mule-network investigation</div>
      </div>
    </Link>
  );
}

type Hit = { id: string; flagged: boolean; score: number; severity: Severity | null };

function AccountSearch() {
  const [q, setQ] = useState("");
  const qRef = useRef(q);
  qRef.current = q;
  // results carry the query they answer: Enter and the list only ever use results of the current query
  const [results, setResults] = useState<SearchResults<Hit> | null>(null);
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const query = normalise(q);
    if (!query) { setResults(null); return; }
    let live = true;
    const h = setTimeout(() => api.search(query)
      .then((r) => { if (live) setResults({ query, items: r.items }); })
      .catch(() => { if (live) setResults({ query, items: [] }); }), 150);
    return () => { live = false; clearTimeout(h); };
  }, [q]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const go = (id: string) => { setOpen(false); setQ(""); setResults(null); nav(accountPath(id)); };
  const enter = async () => {
    const act = enterAction(q, results);
    if (act.kind === "open") { go(act.id); return; }
    if (act.kind !== "search") return;
    // the shown results are stale or not back yet: search the current text now
    const query = normalise(q);
    try {
      const r = await api.search(query);
      if (normalise(qRef.current) !== query) return;      // the text changed meanwhile; that search decides
      setResults({ query, items: r.items });
      const hit = bestMatch(query, r.items);
      if (hit) go(hit.id); else setOpen(true);
    } catch { setResults({ query, items: [] }); setOpen(true); }
  };
  const items = currentItems(q, results);
  const query = normalise(q);
  return (
    <div ref={box} className="relative min-w-0 flex-1 sm:max-w-xs">
      <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
      <input className="input w-full pl-8" placeholder="Find any account…" value={q} aria-label="Find account"
        aria-expanded={open && !!query} aria-controls="account-search-results" autoComplete="off"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void enter(); } if (e.key === "Escape") setOpen(false); }} />
      {open && query && (
        <div id="account-search-results" className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border border-line bg-raised shadow-card">
          {items == null ? <div className="px-3 py-2 text-sm text-muted">Searching…</div>
            : items.length === 0 ? <div className="px-3 py-2 text-sm text-muted" role="status">No account matches “{query}”.</div>
            : items.map((i) => (
              <button key={i.id} type="button" onClick={() => go(i.id)}
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-sunken focus-visible:bg-sunken">
                <span className="min-w-0 font-mono text-[13px] [overflow-wrap:anywhere]">{i.id}</span>
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
      {/* sticky from the small breakpoint up; on a phone it scrolls away instead of covering a fifth of the screen */}
      <header className="z-40 border-b border-line bg-surface/95 backdrop-blur sm:sticky sm:top-0">
        <div className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-3 px-4 py-2">
          <Brand />
          <nav className="flex flex-wrap items-center gap-1">
            <NavLink to="/" end className={navCls}><LayoutDashboard size={15} /> Overview</NavLink>
            <NavLink to="/queue" className={navCls}><ListChecks size={15} /> Queue</NavLink>
            <NavLink to="/reviewed" className={navCls}><ShieldOff size={15} /> Not flagged</NavLink>
            <NavLink to="/data" className={navCls}><Database size={15} /> Data</NavLink>
          </nav>
          <div className="ml-auto flex min-w-0 flex-1 items-center justify-end gap-2 sm:gap-3">
            <AccountSearch />
            <label className="flex items-center gap-1.5" title="Analyst name recorded with each decision">
              <UserRound size={15} className="shrink-0 text-muted" />
              <input className="input w-24 py-1 sm:w-32" value={analyst} onChange={(e) => setAnalyst(e.target.value)}
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
            <Route path="/cases" element={loaded ? <Cases /> : <Navigate to="/data" replace />} />
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
