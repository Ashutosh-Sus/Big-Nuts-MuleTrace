import { Link } from "react-router-dom";
import { CheckCircle2, ChevronRight } from "lucide-react";
import { api } from "../api";
import { useApp, useLoad } from "../state";
import { Empty, ErrorBox, SeverityBadge, Spinner } from "../components/Badges";
import { FAMILY_LABEL } from "../components/Investigation";
import { duration, moneyShort, timeRange } from "../format";
import { progressText, severityMix } from "../lib/cases";
import { casePath } from "../lib/paths";

export default function Cases() {
  const { version } = useApp();
  const { data, error } = useLoad(api.cases, [version]);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Spinner />;
  return (
    <div className="space-y-3">
      <div>
        <h1 className="text-lg font-semibold">Suspicious cases</h1>
        <p className="text-sm text-muted">Connected money flows with at least one flagged account. Ordered by the highest
          severity among flagged members, then cases not yet fully confirmed. Open a case to see its network.</p>
      </div>
      <section className="card">
        {!data.items.length ? (
          <Empty>No suspicious cases — no connected flow in this dataset contains a flagged account.</Empty>
        ) : (
          <ul className="divide-y divide-line" aria-label="Suspicious cases">
            {data.items.map((c) => {
              const m = c.metrics;
              return (
                <li key={c.id}>
                  <Link to={casePath(c.id)} className="group block px-4 py-3 hover:bg-sunken/70 focus-visible:outline-offset-[-2px]">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-mono text-[15px] font-semibold text-accent-ink group-hover:underline">{c.id}</span>
                      <SeverityBadge severity={c.severity} />
                      <span className="text-xs text-ink2">flagged: {severityMix(c.severity_counts)}</span>
                      <span className="flex basis-full items-center gap-1.5 text-xs text-ink2 sm:ml-auto sm:basis-auto">
                        <CheckCircle2 size={13} className={c.fully_confirmed ? "text-high" : "text-muted"} />
                        {progressText(c)}
                      </span>
                      <ChevronRight size={16} className="hidden shrink-0 text-muted sm:block" />
                    </div>
                    <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-sm md:grid-cols-3 xl:grid-cols-5">
                      <div><dt className="label">Accounts</dt>
                        <dd><span className="num">{c.accounts}</span> <span className="text-xs text-muted">({c.flagged} flagged)</span></dd></div>
                      <div><dt className="label">Value from likely origins</dt>
                        <dd>{c.origins > 0 ? <><span className="num">{moneyShort(m.value_from_origins)}</span>{" "}
                          <span className="text-xs text-muted">({c.origins} likely origin{c.origins > 1 ? "s" : ""})</span></>
                          : <span className="text-xs text-muted">no likely origin identified</span>}</dd></div>
                      <div className="col-span-2 md:col-span-1"><dt className="label">Window</dt>
                        <dd><span className="num">{timeRange(m.start, m.end)}</span>{" "}
                          <span className="text-xs text-muted">{m.start != null && m.end != null ? `(${duration(m.end - m.start)})` : ""}</span></dd></div>
                      <div><dt className="label">Median dwell</dt><dd className="num">{duration(m.median_dwell_seconds)}</dd></div>
                      <div><dt className="label">Evidence families</dt>
                        <dd>{c.families.map((f) => FAMILY_LABEL[f] ?? f).join(" · ") || "—"}</dd></div>
                    </dl>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <div className="text-xs text-muted">
        {data.total} case{data.total === 1 ? "" : "s"}
        {data.unflagged_cases > 0 && <> · {data.unflagged_cases} connected flow{data.unflagged_cases === 1 ? "" : "s"} with no
          flagged account {data.unflagged_cases === 1 ? "is" : "are"} not listed</>}
      </div>
    </div>
  );
}
