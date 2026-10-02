import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle2, FileUp, MinusCircle, PlayCircle, RotateCcw } from "lucide-react";
import { api, ApiError, type IngestReport } from "../api";
import { useApp } from "../state";
import { date, dateTime } from "../format";

const CAP_LABEL: Record<string, string> = {
  device: "Device IDs", ip: "IP addresses", kyc: "KYC identifiers", account_created: "Account opening dates",
  balances: "Balances", currency: "Currency column", label: "Label column (ignored by detection)",
};
const CAP_EFFECT: Record<string, string> = {
  device: "device clustering", ip: "IP clustering", kyc: "KYC clustering",
  account_created: "new-account determination", balances: "balance-covered origin check",
};

export default function DataPage() {
  const { dataset, setDataset, analyst } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ msg: string; body?: any } | null>(null);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const nav = useNavigate();

  const run = async (label: string, fn: () => Promise<any>, goto?: string) => {
    setBusy(label); setErr(null);
    try { setDataset(await fn()); if (goto) nav(goto); }
    catch (e) { const ae = e as ApiError; setErr({ msg: ae.message, body: ae.body }); }
    finally { setBusy(null); }
  };
  const upload = (f: File | undefined) => f && run("Analysing " + f.name, () => api.upload(f));

  const rep = dataset?.report;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
      <div className="space-y-4">
        <section className="card">
          <div className="card-h"><h2 className="card-t">Load transactions</h2></div>
          <div className="space-y-3 p-4">
            <div
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]); }}
              onClick={() => fileRef.current?.click()}
              className={`flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors ${drag ? "border-accent bg-accent-soft" : "border-line-strong hover:bg-sunken"}`}>
              <FileUp size={26} className="text-accent" />
              <div className="text-sm font-medium">Drop a transaction CSV here, or click to choose</div>
              <div className="text-xs text-muted">Required: timestamp, sender, receiver, amount. Optional: device, IP, KYC, account dates, balances.</div>
              <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={(e) => upload(e.target.files?.[0])} />
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn btn-primary" disabled={!!busy} onClick={() => run("Loading demo", api.loadDemo, "/")}>
                <PlayCircle size={15} /> Load demo dataset</button>
              <button className="btn" disabled={!!busy} onClick={() => run("Resetting demo", () => api.reset(analyst), "/")}
                title="Reload the demo dataset and clear all analyst decisions on it">
                <RotateCcw size={15} /> Reset demo</button>
            </div>
            {busy && <div className="text-sm text-muted animate-pulse">{busy}…</div>}
            {err && (
              <div className="rounded-md border border-high/40 bg-high-soft px-3 py-2 text-sm text-high-ink">
                <div className="font-semibold">{err.msg}</div>
                {err.body?.detected_headers && <div className="mt-1 text-xs">Detected headers: {err.body.detected_headers.join(", ")}</div>}
              </div>
            )}
          </div>
        </section>
        {rep && <Coverage rep={rep} historyLimited={!!dataset?.history_limited} establishment={!!dataset?.establishment_evidence} />}
      </div>
      {rep && dataset?.dataset ? <Report rep={rep} name={dataset.dataset.name} /> : (
        <section className="card p-8 text-center text-muted">No dataset loaded yet.</section>
      )}
    </div>
  );
}

function Coverage({ rep, historyLimited, establishment }: { rep: IngestReport; historyLimited: boolean; establishment: boolean }) {
  return (
    <section className="card">
      <div className="card-h"><h2 className="card-t">Analysis coverage</h2></div>
      <ul className="divide-y divide-line">
        {Object.entries(rep.coverage).map(([k, on]) => (
          <li key={k} className="flex items-start gap-2 px-4 py-2 text-sm">
            {on ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-good" /> : <MinusCircle size={16} className="mt-0.5 shrink-0 text-muted" />}
            <div>
              <div className={on ? "text-ink" : "text-ink2"}>{CAP_LABEL[k] ?? k}</div>
              {!on && CAP_EFFECT[k] && <div className="text-xs text-muted">Not in file — {CAP_EFFECT[k]} unavailable or reduced.</div>}
            </div>
          </li>
        ))}
        <li className="flex items-start gap-2 px-4 py-2 text-sm">
          {establishment ? <CheckCircle2 size={16} className="mt-0.5 text-good" /> : <AlertTriangle size={16} className="mt-0.5 text-medium" />}
          <div>{establishment ? "Account establishment can be judged" :
            "No establishment evidence — IP links stay weak evidence; infrastructure suppression unavailable"}</div>
        </li>
        <li className="flex items-start gap-2 px-4 py-2 text-sm">
          {!historyLimited ? <CheckCircle2 size={16} className="mt-0.5 text-good" /> : <AlertTriangle size={16} className="mt-0.5 text-medium" />}
          <div>{!historyLimited ? "Relationship history available (≥ 7 days)" :
            "Dataset spans < 7 days — relationship-history mitigations unavailable"}</div>
        </li>
      </ul>
    </section>
  );
}

function Report({ rep, name }: { rep: IngestReport; name: string }) {
  const stat = (label: string, value: number | string, tone = "") => (
    <div className="rounded-md border border-line bg-raised px-3 py-2">
      <div className="label">{label}</div>
      <div className={`num text-xl font-semibold ${tone}`}>{value}</div>
    </div>
  );
  return (
    <section className="card">
      <div className="card-h">
        <h2 className="card-t">Ingestion report · <span className="font-mono font-normal">{name}</span></h2>
        <span className="text-xs text-muted">{date(rep.time_start)} – {date(rep.time_end)}</span>
      </div>
      <div className="space-y-4 p-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {stat("Rows in file", rep.rows_total.toLocaleString())}
          {stat("Accepted", rep.rows_accepted.toLocaleString(), "text-good-ink")}
          {stat("Rejected", rep.rows_rejected, rep.rows_rejected ? "text-high-ink" : "")}
          {stat("Duplicates dropped", rep.duplicates_dropped)}
        </div>
        <div className="grid gap-3 text-sm sm:grid-cols-3">
          <div><div className="label">Time column</div>{rep.time_mode_label}</div>
          <div><div className="label">Currency</div>{rep.currency} ({rep.currency_symbol.trim()}) · minor units, no conversion</div>
          <div><div className="label">Transaction IDs</div>{rep.txn_id_derived ? "derived from row content" : "from file"}</div>
        </div>
        <div>
          <div className="label mb-1">Column mapping</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(rep.column_mapping).map(([k, v]) => (
              <span key={k} className="rounded border border-line bg-raised px-2 py-0.5 text-xs">
                <span className="font-mono">{v}</span> <span className="text-muted">→ {k}</span></span>
            ))}
            {rep.ignored_columns.map((c) => (
              <span key={c} className="rounded border border-dashed border-line px-2 py-0.5 text-xs text-muted">{c} (ignored)</span>
            ))}
          </div>
        </div>
        <div>
          <div className="label mb-1">Rejected rows {rep.errors.length > 0 && `(${rep.errors.length} shown)`}</div>
          {rep.errors.length === 0 ? <div className="text-sm text-muted">None — every row was accepted.</div> : (
            <div className="max-h-80 overflow-auto rounded-md border border-line">
              <table className="tbl w-full text-sm">
                <thead><tr><th>Row</th><th>Reason</th><th>Content</th></tr></thead>
                <tbody>
                  {rep.errors.map((e) => (
                    <tr key={e.row}><td className="num">{e.row}</td><td className="text-high-ink">{e.reason}</td>
                      <td className="max-w-[420px] truncate font-mono text-xs text-muted" title={e.excerpt}>{e.excerpt}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className="text-xs text-muted">Analysed range {dateTime(rep.time_start)} – {dateTime(rep.time_end)} (IST).</div>
      </div>
    </section>
  );
}
