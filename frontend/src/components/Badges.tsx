import { AlertOctagon, AlertTriangle, CheckCircle2, Circle, CircleDot, Info, ShieldCheck } from "lucide-react";
import type { Severity } from "../api";
import { ROLE_LABEL } from "../format";

const SEV: Record<Severity, { cls: string; Icon: typeof Circle; label: string }> = {
  HIGH: { cls: "bg-high-soft text-high-ink border-high/40", Icon: AlertOctagon, label: "High" },
  MEDIUM: { cls: "bg-medium-soft text-medium-ink border-medium/50", Icon: AlertTriangle, label: "Medium" },
  LOW: { cls: "bg-low-soft text-low-ink border-low/40", Icon: Info, label: "Low" },
};

export function SeverityBadge({ severity, score }: { severity: Severity | null | undefined; score?: number }) {
  if (!severity) {
    return <span className="inline-flex items-center gap-1 rounded border border-line px-1.5 py-0.5 text-2xs font-semibold text-muted">
      <Circle size={11} /> Not flagged</span>;
  }
  const s = SEV[severity];
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide ${s.cls}`}>
      <s.Icon size={11} strokeWidth={2.5} />
      {s.label}{score != null && <span className="num font-bold">· {score}</span>}
    </span>
  );
}

export function StatusBadge({ status }: { status: string | undefined }) {
  if (status === "CONFIRMED") {
    return <span className="inline-flex items-center gap-1 rounded bg-high-soft px-1.5 py-0.5 text-2xs font-semibold text-high-ink">
      <ShieldCheck size={11} /> Confirmed</span>;
  }
  if (status === "CLEARED") {
    return <span className="inline-flex items-center gap-1 rounded bg-good-soft px-1.5 py-0.5 text-2xs font-semibold text-good-ink">
      <CheckCircle2 size={11} /> Cleared</span>;
  }
  if (status === "MIXED") {
    return <span className="inline-flex items-center gap-1 rounded bg-sunken px-1.5 py-0.5 text-2xs font-semibold text-ink2">Mixed</span>;
  }
  return <span className="inline-flex items-center gap-1 rounded bg-sunken px-1.5 py-0.5 text-2xs font-semibold text-ink2">
    <CircleDot size={11} /> Open</span>;
}

export function RoleBadge({ role }: { role: string | null | undefined }) {
  if (!role) return null;
  return <span className="inline-flex items-center rounded border border-line bg-raised px-1.5 py-0.5 text-2xs font-medium text-ink2">
    {ROLE_LABEL[role] ?? role}</span>;
}

export function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) return <span className="text-2xs text-muted">—</span>;
  const cls = tier === "STRONG" ? "text-high-ink bg-high-soft" : tier === "MODERATE" ? "text-medium-ink bg-medium-soft"
    : "text-low-ink bg-low-soft";
  return <span className={`rounded px-1.5 py-0.5 text-2xs font-semibold ${cls}`}>{tier.replace("_", " ").toLowerCase()}</span>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="px-4 py-8 text-center text-sm text-muted">{children}</div>;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return <div className="px-4 py-8 text-center text-sm text-muted animate-pulse">{label}</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return <div className="m-4 rounded-md border border-high/40 bg-high-soft px-3 py-2 text-sm text-high-ink">{message}</div>;
}
