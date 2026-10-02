import { useId, useRef, useState } from "react";
import { BookOpen, X } from "lucide-react";
import { api } from "../api";
import { methodSections, type MethodConfig } from "../lib/method";

type ConfigView = { config: MethodConfig; hash: string; engine: string };
let loading: Promise<ConfigView> | null = null;   // the configuration is fixed for the running server

/** "Method" button opening a read-only panel of the analysis configuration (`/api/config`). */
export function MethodButton() {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [view, setView] = useState<ConfigView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = () => {
    dialog.current?.showModal();
    if (view) return;
    setError(null);
    (loading ??= api.config()).then(setView).catch((e) => { loading = null; setError(e.message); });
  };
  const close = () => dialog.current?.close();
  return (
    <>
      <button type="button" className="flex items-center gap-1 rounded px-2 py-1.5 text-xs text-accent-ink hover:bg-sunken"
        onClick={open} aria-haspopup="dialog">
        <BookOpen size={13} /> Method
      </button>
      <dialog ref={dialog} aria-labelledby={titleId}
        onClick={(e) => { if (e.target === dialog.current) close(); }}
        className="m-auto max-h-[85vh] w-[min(640px,calc(100vw-32px))] overflow-hidden rounded-lg border border-line bg-surface p-0 text-ink shadow-card backdrop:bg-black/50">
        <div className="flex max-h-[85vh] flex-col">
          <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
            <div>
              <h2 id={titleId} className="text-sm font-semibold">How MuleTrace scores</h2>
              <p className="mt-0.5 text-xs text-ink2">Fixed rules: the same data and configuration always give the same result.
                Scores are evidence-strength indices, not probabilities of fraud.</p>
            </div>
            <button type="button" className="btn btn-ghost shrink-0 px-2" onClick={close} aria-label="Close method panel" autoFocus>
              <X size={16} />
            </button>
          </div>
          <div className="overflow-y-auto px-4 py-3">
            {error && <div className="text-sm text-high-ink">{error}</div>}
            {!view && !error && <div className="text-sm text-muted">Loading…</div>}
            {view && (
              <div className="space-y-4">
                {methodSections(view.config).map((s) => (
                  <section key={s.title}>
                    <h3 className="label mb-1">{s.title}</h3>
                    <dl className="grid grid-cols-[minmax(0,1fr)] gap-x-3 text-[13px] sm:grid-cols-[150px_minmax(0,1fr)]">
                      {s.rows.map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt className="pt-1 font-medium text-ink">{k}</dt>
                          <dd className="pb-1 text-ink2 [overflow-wrap:anywhere] sm:pt-1">{v}</dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                ))}
              </div>
            )}
          </div>
          <div className="border-t border-line px-4 py-2 text-2xs text-muted">
            {view ? <>Engine {view.engine} · configuration {view.hash} · read-only</> : "Read-only"}
          </div>
        </div>
      </dialog>
    </>
  );
}
