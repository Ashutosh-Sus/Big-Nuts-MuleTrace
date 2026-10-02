import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useApp, useLoad } from "../state";
import { ErrorBox, SeverityBadge, Spinner, StatusBadge } from "../components/Badges";
import { Timeline } from "../components/Investigation";
import { duration, moneyShort, ROLE_LABEL } from "../format";

export default function CasePage() {
  const { id = "" } = useParams();
  const { version } = useApp();
  const { data: c, error } = useLoad(() => api.caseDetail(id), [id, version]);
  if (error) return <ErrorBox message={error} />;
  if (!c) return <Spinner />;
  const m = c.metrics;
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Case {c.id}</h1>
        <p className="text-sm text-muted">{m.accounts} accounts · {c.flagged} flagged · {c.confirmed} confirmed ·
          {" "}{moneyShort(m.value_from_origins)} entered from likely origins · {m.start && m.end ? duration(m.end - m.start) : ""} window ·
          {" "}median dwell {duration(m.median_dwell_seconds)}</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-[420px_minmax(0,1fr)]">
        <section className="card">
          <div className="card-h"><h2 className="card-t">Members and observed roles</h2></div>
          <table className="tbl w-full text-sm">
            <thead><tr><th>Account</th><th>Role</th><th>Severity</th><th>Status</th></tr></thead>
            <tbody>
              {c.members.map((mem) => (
                <tr key={mem.id}>
                  <td className="font-mono"><Link className="link" to={`/account/${mem.id}`}>{mem.id}</Link></td>
                  <td>{ROLE_LABEL[mem.role] ?? mem.role}</td>
                  <td><SeverityBadge severity={mem.severity} score={mem.flagged ? mem.score : undefined} /></td>
                  <td><StatusBadge status={mem.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <Timeline title="all case transactions" rows={c.timeline} focus="" />
      </div>
    </div>
  );
}
