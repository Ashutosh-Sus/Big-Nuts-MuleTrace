"""Case money-flow summary: a few fixed-template sentences built from a case's computed data.

Read-only presentation over the analysis (cases, roles, case transactions, scored signals, metrics). It adds no
evidence and changes nothing. A sentence is written only when the data behind it exists; roles are described only
for a case with a flagged member (§7.2), and nothing here calls an account a victim.
"""
from __future__ import annotations

PATTERN_PHRASES = (("RELAY", "pass-through"), ("HUB", "fan-in → fan-out"), ("LAYERED_RECEIPT", "layered receipt"),
                   ("ROUND_TRIP", "circular flow"), ("IDENTITY", "shared attributes"))
MOVE_ROLES = (("HUB", "hub", "hubs"), ("COLLECTOR", "collector", "collectors"),
              ("DISTRIBUTOR", "distributor", "distributors"), ("RELAY", "relay account", "relay accounts"))
SHOW_IDS = 3


def _n(k: int, one: str, many: str | None = None) -> str:
    return f"{k} {one if k == 1 else (many or one + 's')}"


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _ids(accounts: list[str]) -> str:
    head = ", ".join(accounts[:SHOW_IDS])
    return head + (f" +{len(accounts) - SHOW_IDS} more" if len(accounts) > SHOW_IDS else "")


def _span(f, start: int, end: int) -> str:
    if start == end:
        return f.time(start)
    same_day = f.time(start)[:6] == f.time(end)[:6]
    return f"{f.time(start)}–{f.clock(end)}" if same_day else f"{f.time(start)} – {f.time(end)}"


def case_summary(an, case) -> dict:
    f, txns, cfg = an.fmt, an.ds.txns, an.cfg
    edges = sorted(case.edges, key=lambda t: (txns[t].ts, t))
    m = case.metrics
    labelled = case.id in an.flagged_cases
    roles = case.roles if labelled else {}
    by_role: dict[str, list[str]] = {}
    for a in case.members:
        if roles.get(a):
            by_role.setdefault(roles[a], []).append(a)
    for v in by_role.values():
        v.sort()
    origins = sorted(case.origins) if labelled else []
    entry = [t for t in edges if txns[t].sender in origins]
    sinks = by_role.get("SINK", [])
    exits = [t for t in edges if txns[t].receiver in sinks]
    pooled = sorted(a for a in case.members if an.ds.accounts[a].pooled)
    patterns = {k: sum(1 for a in case.members if an.results[a].flagged and k in an.results[a].signals
                       and an.results[a].signals[k].qualifies) for k, _ in PATTERN_PHRASES}
    facts = {
        "labelled": labelled, "engine": an.engine, "origins": origins,
        "entry_amount": sum(txns[t].amount for t in entry), "entry_transactions": len(entry),
        "entry_start": txns[entry[0]].ts if entry else None, "entry_end": txns[entry[-1]].ts if entry else None,
        "roles": {r: len(v) for r, v in sorted(by_role.items())}, "patterns": patterns,
        "sinks": sinks, "exit_amount": sum(txns[t].amount for t in exits), "exit_transactions": len(exits),
        "pooled": pooled, "transactions": len(edges), "start": m["start"], "end": m["end"],
        "median_dwell_seconds": m["median_dwell_seconds"], "value_moved": m["value_moved"],
    }
    lines = []

    if labelled:
        if origins:
            lines.append(("entry", "Entry", (
                f"Funds entered the case from {_n(len(origins), 'likely origin account')} ({_ids(origins)}): "
                f"{f.money(facts['entry_amount'])} in {_n(len(entry), 'transaction')}, "
                f"{_span(f, facts['entry_start'], facts['entry_end'])}.")))
        else:
            first = txns[edges[0]] if edges else None
            lines.append(("entry", "Entry", "No likely origin account identified, so where these funds entered is "
                          "not visible in this case." + (f" The first case transaction was sent by {first.sender} "
                                                         f"on {f.time(first.ts)}." if first else "")))

        parts = [_n(len(by_role[r]), one, many) for r, one, many in MOVE_ROLES if by_role.get(r)]
        move = f"Funds moved through {_join(parts)}." if parts else ""
        scored = [f"{phrase} ({patterns[k]})" for k, phrase in PATTERN_PHRASES if patterns[k]]
        if scored:
            move += f" Scored patterns, by number of flagged members: {', '.join(scored)}."
        if patterns["ROUND_TRIP"]:
            move += " Circular flow: money sent out by an account later came back to it through other accounts."
        if m["median_dwell_seconds"] is not None:
            move += (f" Median time funds stayed in an account before moving on: "
                     f"{f.duration(m['median_dwell_seconds'])}.")
        elif an.engine == "window":
            move += " Holding times are not traced by the fallback engine."
        lines.append(("movement", "Movement", move.strip()))

        if sinks:
            out = (f"{_n(len(sinks), 'sink account')} ({_ids(sinks)}) received {f.money(facts['exit_amount'])} in "
                   f"{_n(len(exits), 'case transaction')}; a sink forwards less than "
                   f"{f.pct(cfg.sink_forward_max)} of what it receives.")
        else:
            out = "No sink account identified: within the data, case funds were not seen coming to rest in one account."
        if pooled:
            out += f" {_n(len(pooled), 'pooled account')} ({_ids(pooled)}): traced money stops there."
        lines.append(("exit", "Exit", out))

    if edges:
        period = (f"{_n(len(edges), 'case transaction')}, {_span(f, m['start'], m['end'])} "
                  f"({f.duration(m['end'] - m['start'])}). Together they total {f.money(m['value_moved'])} — the same "
                  "money is counted again at every hop, so this is transaction volume, not an amount lost.")
        lines.append(("period", "Period", period))
    if not labelled:
        lines.append(("roles", "Roles", "No member is flagged, so roles are not assigned and entry and exit are "
                      "not described."))
    return {"id": case.id, "lines": [{"kind": k, "label": label, "text": t} for k, label, t in lines], "facts": facts}
