import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, ChevronRight, HelpCircle, ShieldAlert, ShieldCheck } from "lucide-react";
import type { AccountDetail, CaseDetail, SignalView, TxnRow } from "../api";
import { auditTime, clock, dateTime, duration, money, moneyShort, OBS_LABEL, PATTERN_LABEL, pct, ROLE_LABEL, RULE_LABEL, timeRange } from "../format";
import { useApp } from "../state";
import { reasonsFor, type DecisionStatus, type SubmitResult } from "../lib/decision";
import { flaggedFirst } from "../lib/members";
import { accountPath, casePath } from "../lib/paths";
import { RoleBadge, SeverityBadge, StatusBadge, TierBadge } from "./Badges";

const FAMILY_LABEL: Record<string, string> = { FLOW: "Money flow", CIRCULARITY: "Circularity", IDENTITY: "Shared identity" };
const FAMILY_CAP: Record<string, number> = { FLOW: 60, CIRCULARITY: 20, IDENTITY: 20 };

export function ScoreCard({ d }: { d: AccountDetail }) {
  const fams = ["FLOW", "CIRCULARITY", "IDENTITY"];
  return (
    <section className="card">
      <div className="card-h">
        <h2 className="card-t">Why this account · score</h2>
        <span title="Rule points from independent evidence families (max 100). An evidence-strength index, not a probability of fraud."
          className="flex items-center gap-1 text-2xs text-muted"><HelpCircle size={12} /> not a probability</span>
      </div>
      <div className="px-4 py-3">
        <div className="flex items-baseline gap-2">
          <span className="num text-4xl font-semibold tracking-tight">{d.score}</span>
          <span className="text-sm text-muted">/ 100</span>
          <span className="ml-auto"><SeverityBadge severity={d.severity} /></span>
        </div>
        <div className="mt-1 text-xs text-muted">
          {d.families.length ? `${d.families.length} independent evidence famil${d.families.length === 1 ? "y" : "ies"}` : "No scored evidence"}
          {d.exposure > 0 && <> · <span title="Exposure: the largest amount in this account's scored evidence (shown, never scored)">exposure {money(d.exposure)}</span></>}
        </div>
      </div>
      {d.components.length > 0 && (
        <div className="space-y-3 border-t border-line px-4 py-3">
          {fams.map((f) => {
            const comps = d.components.filter((c) => c.family === f);
            if (!comps.length) return null;
            const total = comps.reduce((a, c) => a + c.points, 0);
            return (
              <div key={f}>
                <div className="mb-1 flex items-center justify-between">
                  <span className="label">{FAMILY_LABEL[f]}</span>
                  <span className="num text-xs text-muted">{total} / {FAMILY_CAP[f]}</span>
                </div>
                <ul className="space-y-1">
                  {comps.map((c, i) => (
                    <li key={i} className="flex gap-2 text-sm">
                      <span className={`num w-9 shrink-0 text-right font-semibold ${c.points < 0 ? "text-muted" : "text-ink"}`}>
                        {c.points > 0 ? `+${c.points}` : c.points}</span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5 font-medium">{RULE_LABEL[c.rule] ?? c.rule} {c.tier && <TierBadge tier={c.tier} />}</div>
                        {c.rule !== "FAMILY_CAP" && <div className="text-xs leading-snug text-ink2">{c.detail}</div>}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export function ProfileCard({ d }: { d: AccountDetail }) {
  const p = d.profile;
  const row = (k: string, v: React.ReactNode) => (
    <div className="flex justify-between gap-3 py-1 text-sm"><span className="text-muted">{k}</span><span className="text-right">{v}</span></div>
  );
  return (
    <section className="card">
      <div className="card-h"><h2 className="card-t">Account profile</h2>{p.pooled && <span className="text-2xs text-muted">pooled</span>}</div>
      <div className="divide-y divide-line px-4 py-2">
        {row("Establishment", <span title={p.establishment_basis}>{p.establishment.toLowerCase()}{p.age_days != null ? ` · opened ${p.age_days} d before first activity` : ""}</span>)}
        {row("Active", `${dateTime(p.first_seen)} – ${dateTime(p.last_seen)}`)}
        {row("Received", <span className="num">{money(p.in_total)} · {p.in_count} txns</span>)}
        {row("Sent", <span className="num">{money(p.out_total)} · {p.out_count} txns</span>)}
        {row("Counterparties", <span className="num">{p.counterparties}</span>)}
        {(["device", "ip", "kyc"] as const).map((k) => p.attributes[k]?.length ? row(
          k === "kyc" ? "KYC" : k === "ip" ? "IP" : "Device",
          <span className="font-mono text-xs">{p.attributes[k].slice(0, 3).join(", ")}{p.attributes[k].length > 3 ? ` +${p.attributes[k].length - 3}` : ""}</span>) : null)}
      </div>
    </section>
  );
}

export function SignalCard({ s, points, active, onSelect }: { s: SignalView; points: number; active: boolean; onSelect: () => void }) {
  const m = s.metrics;
  const chips: string[] = [];
  if (s.kind === "RELAY") {
    if (m.forwarded) chips.push(`${pct(m.conservation)} conserved`, `dwell ${duration(m.dwell_seconds)}`);
    else if (m.window) chips.push(`${pct(m.window.conservation)} amount match`, `within ${duration(m.window.bound_seconds)}`);
    if (m.linked_relays?.length) chips.push(`linked to ${m.linked_relays.length} relay${m.linked_relays.length > 1 ? "s" : ""}`);
    if (m.mitigations?.length) chips.push(`downgraded: ${m.mitigations.join(", ").toLowerCase().replace(/_/g, " ")}`);
  } else if (s.kind === "HUB") {
    chips.push(`${m.senders.length} senders`, `${m.receivers.length} receivers`, `${pct(m.conservation)} moved on`);
  } else if (s.kind === "ROUND_TRIP") {
    chips.push(`${pct(m.ratio)} returned`, duration(m.span_seconds), `${m.hops} accounts`);
  } else if (s.kind === "LAYERED_RECEIPT") {
    chips.push(`${m.relays_upstream} relays upstream`, duration(m.span_seconds));
    if (m.consolidation) chips.push(`${m.upstream_senders.length} chains converge`);
  } else if (s.kind === "IDENTITY") {
    chips.push(...(m.link_types as string[]).map((t) => `shared ${t === "kyc" ? "KYC" : t}`));
    if (m.ip_only) chips.push("weak evidence");
    if (m.restored) chips.push("linked inside flow case");
  }
  return (
    <button type="button" onClick={onSelect} aria-pressed={active}
      className={`block w-full rounded-md border px-3 py-2.5 text-left transition-colors ${active ? "border-accent bg-accent-soft/60" : "border-line bg-raised hover:border-line-strong"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-sm font-semibold">{PATTERN_LABEL[s.kind] ?? s.label} <TierBadge tier={s.final_tier} /></span>
        <span className="num text-sm font-semibold">{points > 0 ? `+${points}` : ""}</span>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-ink2">{s.reason}</p>
      {chips.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{chips.map((c) => (
        <span key={c} className="rounded bg-sunken px-1.5 py-0.5 text-2xs text-ink2">{c}</span>))}</div>}
      {s.path.length > 1 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-0.5 font-mono text-2xs text-ink2">
          {s.path.map((a, i) => <span key={i} className="flex items-center gap-0.5">{i > 0 && <ChevronRight size={10} className="text-muted" />}{a}</span>)}
        </div>
      )}
      <div className="mt-1 text-2xs text-muted">
        {s.timeline_total > 0 && <>{s.timeline_total} transaction{s.timeline_total > 1 ? "s" : ""} · </>}
        {active ? "highlighted in the graph · click again to show everything" : "click to highlight in the graph"}</div>
    </button>
  );
}

export function Timeline({ title, rows, focus, total, empty }: { title: string; rows: TxnRow[]; focus: string; total?: number; empty?: string }) {
  if (!rows.length && !empty) return null;
  const count = total != null && total > rows.length ? `first ${rows.length} of ${total} transactions, in time order`
    : `${rows.length} transaction${rows.length === 1 ? "" : "s"}`;
  return (
    <section className="card">
      <div className="card-h"><h2 className="card-t">What happened · {title}</h2><span className="text-right text-xs text-muted">{count} · times in IST</span></div>
      {!rows.length && <div className="px-4 py-6 text-sm text-muted">{empty}</div>}
      <ol className="relative max-h-[340px] overflow-auto px-4 py-3">
        {rows.map((r, i) => {
          const prev = i > 0 ? rows[i - 1].ts : null;
          return (
            <li key={r.txn_id} className="relative flex gap-3 pb-3 pl-4 last:pb-0">
              <span className="absolute left-0 top-1.5 h-2 w-2 rounded-full bg-accent" />
              {i < rows.length - 1 && <span className="absolute left-[3px] top-3.5 h-full w-px bg-line-strong" />}
              <div className="w-24 shrink-0">
                <div className="num text-sm font-semibold">{clock(r.ts)}</div>
                <div className="text-2xs text-muted">{dateTime(r.ts).slice(0, 6)}{prev != null && r.ts - prev > 0 ? ` · +${duration(r.ts - prev)}` : ""}</div>
              </div>
              <div className="min-w-0 text-sm">
                <div className="[overflow-wrap:anywhere]"><span className={`font-mono ${r.sender === focus ? "font-bold" : ""}`}>{r.sender}</span>
                  <ArrowRight size={12} className="mx-1 inline text-muted" />
                  <span className={`font-mono ${r.receiver === focus ? "font-bold" : ""}`}>{r.receiver}</span></div>
                <div className="text-xs text-ink2"><span className="num font-semibold text-ink">{money(r.amount)}</span>
                  {r.dwell_seconds != null && <> · held {duration(r.dwell_seconds)} at {r.sender}</>}
                  <span className="ml-1 font-mono text-muted">{r.txn_id}</span></div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function WhyNot({ d }: { d: AccountDetail }) {
  if (!d.observations.length) return null;
  return (
    <section className="card">
      <div className="card-h"><h2 className="card-t">{d.flagged ? "Also considered (not scored)" : "Why this account is not flagged"}</h2></div>
      <ul className="divide-y divide-line">
        {d.observations.map((o, i) => (
          <li key={i} className="px-4 py-2.5">
            <span className="rounded bg-good-soft px-1.5 py-0.5 text-2xs font-semibold text-good-ink">{OBS_LABEL[o.kind] ?? o.kind}</span>
            <p className="mt-1 text-xs leading-relaxed text-ink2">{o.text}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function DispositionPanel({ d, busy, onDecide }: {
  d: AccountDetail; busy: boolean; onDecide: (status: string, note: string) => Promise<SubmitResult>;
}) {
  const { analyst } = useApp();
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const status = d.disposition.status as DecisionStatus;
  const reasons = reasonsFor(status);
  // the note is cleared only once the decision is saved; a failure keeps it and says why
  const run = async (to: string) => {
    setErr(null);
    const r = await onDecide(to, note);
    if (r.ok) setNote(""); else setErr(r.error);
  };
  const chips = (label: string, list: string[]) => list.length > 0 && (
    <div className="flex flex-wrap items-center gap-1">
      <span className="mr-1 text-2xs text-muted">{label}</span>
      {list.map((r) => <button key={r} type="button" className={`chip ${note === r ? "chip-on" : ""}`} onClick={() => setNote(r)}>{r}</button>)}
    </div>
  );
  return (
    <section className="card">
      <div className="card-h"><h2 className="card-t">Analyst decision</h2><StatusBadge status={status} /></div>
      <div className="space-y-2.5 p-4">
        {!d.flagged && <p className="text-xs leading-relaxed text-ink2">This account is not flagged. A decision is kept in its audit
          trail and listed on the Overview; the account does not enter the queue.</p>}
        <textarea className="input h-16 w-full resize-none" placeholder="Note for the audit trail (recommended)"
          aria-label="Note for the audit trail" value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
        <div className="space-y-1">
          {chips("Confirm:", reasons.confirm)}
          {chips("Clear:", reasons.clear)}
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn border-high-fill bg-high-fill text-on-high hover:bg-high-ink" disabled={busy || status === "CONFIRMED"}
            onClick={() => run("CONFIRMED")}><ShieldAlert size={15} /> Confirm</button>
          <button type="button" className="btn border-good bg-good-soft text-good-ink hover:bg-good/20" disabled={busy || status === "CLEARED"}
            onClick={() => run("CLEARED")}><ShieldCheck size={15} /> Clear</button>
          {status !== "OPEN" && <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => run("OPEN")}>Reopen</button>}
        </div>
        {busy && <div className="text-xs text-muted animate-pulse">Saving decision…</div>}
        {err && (
          <div role="alert" className="rounded-md border border-high/40 bg-high-soft px-3 py-2 text-xs text-high-ink">
            <b>The decision was not saved.</b> {err}. Your note is kept — try again.
          </div>
        )}
        <div className="text-2xs text-muted">Recorded as <b className="text-ink2">{analyst.trim() || "analyst"}</b> (name at the top of the page)</div>
        {d.audit.length > 0 && (
          <div className="border-t border-line pt-2">
            <div className="label mb-1">Audit trail</div>
            <ul className="max-h-40 space-y-1.5 overflow-auto">
              {d.audit.map((a) => (
                <li key={a.id} className="text-xs [overflow-wrap:anywhere]">
                  <span className="text-muted">{auditTime(a.at)}</span> · <b>{a.analyst}</b>{" "}
                  {a.action === "RESET" && <span className="text-ink2">demo reset: </span>}
                  {a.from_status?.toLowerCase()} → <b>{a.to_status?.toLowerCase()}</b>
                  {a.note && a.action !== "RESET" && <div className="text-ink2">“{a.note}”</div>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

export function CaseCard({ c, focus }: { c: CaseDetail; focus: string }) {
  const m = c.metrics;
  const fam = c.families.map((f) => FAMILY_LABEL[f] ?? f).join(" · ");
  const others = c.decided_not_flagged > 0 ? `${c.decided_not_flagged} decision${c.decided_not_flagged > 1 ? "s" : ""} on not-flagged members` : "";
  return (
    <section className="card">
      <div className="card-h">
        <h2 className="card-t">Connected case · {c.id}</h2>
        <Link to={casePath(c.id)} className="link py-1 text-xs">Open case</Link>
      </div>
      <div className="grid grid-cols-2 gap-2 px-4 py-3 text-sm">
        <div><div className="label">Accounts</div><span className="num">{m.accounts}</span> <span className="text-xs text-muted">({c.flagged} flagged)</span></div>
        <div><div className="label">Value from origins</div><span className="num">{moneyShort(m.value_from_origins)}</span></div>
        <div className="col-span-2"><div className="label">Window</div><span className="num">{timeRange(m.start, m.end)}</span> <span className="text-xs text-muted">{m.start && m.end ? `(${duration(m.end - m.start)})` : ""}</span></div>
        <div><div className="label">Median dwell</div><span className="num">{duration(m.median_dwell_seconds)}</span></div>
        <div className="col-span-2"><div className="label">Evidence families</div>{fam || "—"}</div>
        {c.flagged > 0 ? (
          <div className="col-span-2 flex items-center gap-1.5 text-xs text-ink2">
            <CheckCircle2 size={13} className={c.confirmed_flagged ? "text-high" : "text-muted"} />
            {c.confirmed_flagged} of {c.flagged} flagged members confirmed{others && ` · ${others}`}
          </div>
        ) : (
          <div className="col-span-2 text-xs text-muted">No member flagged — roles are not assigned.{others && ` ${others}.`}</div>
        )}
      </div>
      <ul className="max-h-56 divide-y divide-line overflow-auto border-t border-line">
        {flaggedFirst(c.members).map((mem) => (
          <li key={mem.id}>
            <Link to={accountPath(mem.id)} className={`flex items-center justify-between gap-2 px-4 py-1.5 text-sm hover:bg-sunken ${mem.id === focus ? "bg-accent-soft/50" : ""}`}>
              <span className="min-w-0 font-mono text-[13px] [overflow-wrap:anywhere]">{mem.id}</span>
              <span className="flex items-center gap-1.5">
                {mem.role && <span className="text-2xs text-muted">{ROLE_LABEL[mem.role] ?? mem.role}</span>}
                {mem.status !== "OPEN" && <StatusBadge status={mem.status} />}
                <SeverityBadge severity={mem.severity} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function IndicatorNote({ d }: { d: AccountDetail }) {
  if (d.indicator.status === "NOT_ASSESSED") return null;
  const ok = d.indicator.status === "INDICATED";
  return (
    <div className={`rounded-md border px-3 py-2 text-xs ${ok ? "border-accent/40 bg-accent-soft text-accent-ink" : "border-medium/50 bg-medium-soft text-medium-ink"}`}>
      <div className="font-semibold">Observed role: {ROLE_LABEL[d.role ?? ""] ?? d.role} — possible-victim indicator {ok ? "present" : "contra-indicated"}</div>
      <div className="mt-0.5">{d.indicator.text}{d.indicator.reasons.length > 0 && ` Reasons: ${d.indicator.reasons.join("; ")}.`}</div>
    </div>
  );
}

export { RoleBadge };
