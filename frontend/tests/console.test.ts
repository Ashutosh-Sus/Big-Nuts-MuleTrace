// Console behaviour regressions. Run: npm test (Node's built-in test runner; no extra dependencies).
import { test } from "node:test";
import assert from "node:assert/strict";
import { bestMatch, enterAction, currentItems } from "../src/lib/search.ts";
import { timelineKind, toggleEvidence } from "../src/lib/evidence.ts";
import { reasonsFor, submitDecision, CONFIRM_REASONS, CLEAR_REASONS } from "../src/lib/decision.ts";
import { expandAction, mergeNetwork, withStatus } from "../src/lib/graphState.ts";
import { accountPath, casePath, queuePath } from "../src/lib/paths.ts";
import { wrapColumns } from "../src/lib/layout.ts";
import { auditTime, timeRange } from "../src/format.ts";
import { progressText, severityMix } from "../src/lib/cases.ts";
import { methodSections } from "../src/lib/method.ts";

const hits = (...ids: string[]) => ids.map((id) => ({ id }));

test("search: Enter never opens a result of the previous query", () => {
  // AC1 -> wait (results arrive) -> select all -> AC5530 -> Enter before the new results arrive
  const stale = { query: "AC1", items: hits("AC1000", "AC1001", "AC1002") };
  assert.equal(currentItems("AC5530", stale), null);
  assert.deepEqual(enterAction("AC5530", stale), { kind: "search" });
  // once results for the current query exist, Enter opens the exact match
  const fresh = { query: "AC5530", items: hits("AC5530") };
  assert.deepEqual(enterAction("AC5530", fresh), { kind: "open", id: "AC5530" });
  assert.deepEqual(enterAction("  AC5530 ", fresh), { kind: "open", id: "AC5530" });
});

test("search: exact ID preferred, no results and empty query do nothing", () => {
  assert.equal(bestMatch("ac55", hits("AC5521", "AC55"))!.id, "AC55");
  assert.equal(bestMatch("AC55", hits("AC5521", "AC5530"))!.id, "AC5521");
  assert.deepEqual(enterAction("zzz", { query: "zzz", items: [] }), { kind: "none" });
  assert.deepEqual(enterAction("   ", null), { kind: "none" });
});

test("evidence: select, deselect, select another, deselect", () => {
  let sel: string | null = null;
  sel = toggleEvidence(sel, "RELAY"); assert.equal(sel, "RELAY");
  sel = toggleEvidence(sel, "RELAY"); assert.equal(sel, null);           // neutral: nothing highlighted
  sel = toggleEvidence(sel, "HUB"); assert.equal(sel, "HUB");
  sel = toggleEvidence(sel, "HUB"); assert.equal(sel, null);             // does not snap back to the first card
  sel = toggleEvidence("RELAY", "HUB"); assert.equal(sel, "HUB");
  const scored = [{ kind: "IDENTITY", timeline: [] }, { kind: "RELAY", timeline: [1] }, { kind: "HUB", timeline: [1] }];
  assert.equal(timelineKind(null, scored), "RELAY");                     // neutral graph, timeline still useful
  assert.equal(timelineKind("HUB", scored), "HUB");
  assert.equal(timelineKind("GONE", scored), "RELAY");
});

test("decision: reasons match the action they belong to", () => {
  assert.deepEqual(reasonsFor("OPEN"), { confirm: CONFIRM_REASONS, clear: CLEAR_REASONS });
  assert.deepEqual(reasonsFor("CONFIRMED"), { confirm: [], clear: CLEAR_REASONS });
  assert.deepEqual(reasonsFor("CLEARED"), { confirm: CONFIRM_REASONS, clear: [] });
});

test("decision: a failed request is reported, not thrown, so the note can be kept", async () => {
  const failed = await submitDecision(() => Promise.reject(new Error("Request failed (500)")));
  assert.deepEqual(failed, { ok: false, error: "Request failed (500)" });
  assert.deepEqual(await submitDecision(() => Promise.reject("offline")), { ok: false, error: "offline" });
  assert.deepEqual(await submitDecision(() => Promise.resolve({})), { ok: true });
});

const node = (id: string, extra = {}) => ({ id, ...extra });
const edge = (s: string, t: string, extra = {}) => ({ id: `${s}->${t}`, source: s, target: t, first_ts: 0, last_ts: 0, txn_ids: [], ...extra });

test("trace: a traced flow is never merged with another account's trace", () => {
  // P3000 traced 1.5 L exactly; MR141's own trace carries 8.2 L
  const p3000 = { mode: "flow" as const, focus: "P3000", nodes: [node("P3000"), node("MR141", { traced: 150_04_113 })],
    edges: [edge("P3000", "MR141", { amount: 150_04_113 })], accounting: { start: 150_04_113, retained: 150_04_113, stopped_at_pooled: 0, beyond_hop_limit: 0, exact: true } };
  const mr141 = { mode: "flow" as const, focus: "MR141", nodes: [node("MR141"), node("MC25", { traced: 217_53_037 })],
    edges: [edge("MR141", "MC25", { amount: 217_53_037 })] };
  assert.equal(expandAction("fwd"), "open-trace");
  assert.equal(expandAction("back"), "open-trace");
  assert.equal(expandAction("network"), "merge");
  const merged = mergeNetwork(p3000, mr141);
  assert.equal(merged, p3000);
  const maxTraced = Math.max(...merged.nodes.map((n) => (n as { traced?: number }).traced ?? 0));
  assert.ok(maxTraced <= merged.accounting!.start);
});

test("network: expansion merges, and a decision keeps expanded accounts", () => {
  const base = { mode: "network" as const, focus: "A", nodes: [node("A", { focus: true }), node("B")], edges: [edge("A", "B")] };
  const more = { mode: "network" as const, focus: "B", nodes: [node("B", { focus: true }), node("C")], edges: [edge("B", "C")] };
  const g = mergeNetwork(base, more);
  assert.deepEqual(g.nodes.map((n) => n.id), ["A", "B", "C"]);
  assert.equal(g.nodes.find((n) => n.id === "B")!.focus, undefined);    // B keeps its original (non-focus) entry
  const after = withStatus(g, "C", "CONFIRMED");
  assert.deepEqual(after.nodes.map((n) => n.id), ["A", "B", "C"]);
  assert.equal(after.nodes.find((n) => n.id === "C")!.status, "CONFIRMED");
  assert.equal(withStatus(g, "ZZ", "CONFIRMED"), g);
});

test("links: account IDs survive any characters", () => {
  for (const id of ["ACC/7#9", "ACC?x=1&y", "100%", "SPACE ID", "ÄÇÇ-ünï", "=HYPERLINK(\"x\")"]) {
    const path = accountPath(id);
    assert.match(path, /^\/account\/[^/?#]+$/);
    assert.equal(decodeURIComponent(path.slice("/account/".length)), id);
  }
  assert.equal(accountPath("A/B", "fwd"), "/account/A%2FB?view=fwd");
  assert.equal(casePath("CASE-01"), "/case/CASE-01");
  assert.equal(queuePath({ q: "ACC?x=1&y" }), "/queue?q=ACC%3Fx%3D1%26y");
  assert.equal(queuePath({}), "/queue");
});

test("layout: a 24-way fan-out wraps into a grid and keeps left-to-right order", () => {
  const pos = [{ id: "SRC", x: 0, y: 0 }, { id: "HUB", x: 100, y: 0 },
    ...Array.from({ length: 24 }, (_, i) => ({ id: `E${String(i).padStart(2, "0")}`, x: 200, y: i * 40 - 460 })),
    { id: "AFTER", x: 300, y: 0 }];
  const out = wrapColumns(pos, 8, 60, 44);
  const fan = out.filter((p) => p.id.startsWith("E"));
  const columns = new Map<number, number>();
  for (const p of fan) columns.set(p.x, (columns.get(p.x) ?? 0) + 1);
  assert.equal(columns.size, 3);
  assert.ok([...columns.values()].every((n) => n <= 8));
  const at = (id: string) => out.find((p) => p.id === id)!;
  assert.ok(at("SRC").x < at("HUB").x && at("HUB").x < Math.min(...fan.map((p) => p.x)));
  assert.ok(at("AFTER").x > Math.max(...fan.map((p) => p.x)));          // later columns move right
  const height = Math.max(...fan.map((p) => p.y)) - Math.min(...fan.map((p) => p.y));
  assert.ok(height < 8 * 44);                                            // no longer one 24-account column
  assert.deepEqual(wrapColumns(pos.slice(0, 2), 8, 60, 44), pos.slice(0, 2));
});

test("time: audit entries and windows use the console's IST format", () => {
  const t = Date.UTC(2024, 2, 25, 4, 35) / 1000;                          // 10:05 IST
  assert.equal(auditTime(t), "25 Mar 2024 10:05 IST");
  assert.equal(timeRange(t, t + 3 * 3600 + 29 * 60), "25 Mar 10:05–13:34");
  assert.equal(timeRange(t, t + 2 * 86400), "25 Mar 10:05 – 27 Mar 10:05");
  assert.equal(timeRange(null, t), "—");
});

test("cases list: severity mix and decision progress wording", () => {
  assert.equal(severityMix({ HIGH: 5, MEDIUM: 0, LOW: 4 }), "5 high · 4 low");
  assert.equal(severityMix({ HIGH: 0, MEDIUM: 4, LOW: 0 }), "4 medium");
  assert.equal(progressText({ flagged: 9, confirmed_flagged: 0, decided_not_flagged: 0 }), "0 of 9 flagged confirmed");
  assert.equal(progressText({ flagged: 4, confirmed_flagged: 4, decided_not_flagged: 1 }),
    "4 of 4 flagged confirmed · 1 decision on not-flagged members");
  assert.equal(progressText({ flagged: 7, confirmed_flagged: 2, decided_not_flagged: 2 }),
    "2 of 7 flagged confirmed · 2 decisions on not-flagged members");
});

test("method panel: every figure comes from the configuration it is given", () => {
  // unusual values, so a figure that is not read from the configuration cannot pass
  const cfg = {
    severity_high: 61, severity_medium: 37, cap_flow: 57, cap_circularity: 21, cap_identity: 19,
    pts_relay: [34, 19], pts_hub: [24, 14], pts_receipt: [18, 9], pts_extra_base: 4, pts_repeated: 6,
    repeated_min_episodes: 4, pts_chain: 11, chain_min_relays: 5, pts_corroborated: 23, corroborated_span: 2700,
    pts_consolidation: 9, pts_round_trip: [17, 13], pts_identity_strong: 16, pts_identity_ip: 7, pts_identity_extra: 3,
    tier_dwell: [1200, 18000, 172800], tier_conservation: [0.95, 0.85, 0.75],
    hub_min_senders: 4, hub_min_receivers: 5, hub_burst: 14400, receipt_min_relays: 3,
    receipt_strong_span: 10800, receipt_moderate_span: 172800, rt_max_hops: 7, rt_strong_span: 43200,
    rt_strong_return: 0.55, rt_moderate_span: 129600, rt_moderate_return: 0.35,
    cluster_min_size: [["device", 6], ["ip", 9], ["kyc", 8]], horizon: 172800, min_link: 1500, min_episode: 12000,
    trace_max_hops: 9, pooled_min_counterparties: 44, pooled_min_span: 432000, relationship_days: 6,
    relationship_history_share: 0.45, established_share: 0.85, infra_min_established: 7, infra_established_share: 0.65,
    new_account_days: 28, origin_own_funds_share: 0.55, sink_forward_max: 0.15,
  };
  const s = Object.fromEntries(methodSections(cfg).map((x) => [x.title, Object.fromEntries(x.rows)]));
  assert.deepEqual(s.Severity, { High: "score ≥ 61", Medium: "score 37–60", Low: "flagged, score below 37" });
  const score = s["Score — evidence-strength index, max 97"];
  assert.equal(score["Money flow (cap 57)"], "pass-through 34 / 19 · fan-in → fan-out 24 / 14 · layered receipt 18 / 9 (strong / moderate)");
  assert.equal(score["Money-flow bonuses"], "+4 each further pattern · +6 repeated (≥ 4 episodes) · +11 relay chain (≥ 5 relays) · "
    + "+23 corroborated layering (≥ 5 strong relays within 45 min) · +9 consolidation");
  assert.equal(score["Circularity (cap 21)"], "circular flow 17 / 13 (strong / moderate)");
  assert.equal(score["Shared identity (cap 19)"], "device or KYC 16 · IP only 7 · +3 each further attribute type");
  assert.deepEqual(s["Pass-through strength"], { Strong: "held ≤ 20 min, ≥ 95% passed on", Moderate: "held ≤ 5 h, ≥ 85% passed on",
    Weak: "held ≤ 2 d, ≥ 75% passed on — recorded, not scored" });
  assert.equal(s.Patterns["Fan-in → fan-out"], "≥ 4 senders and ≥ 5 receivers within 4 h");
  assert.equal(s.Patterns["Circular flow"], "≤ 7 hops: strong ≤ 12 h and ≥ 55% returned, moderate ≤ 1 d 12 h and ≥ 35%");
  assert.equal(s.Patterns["Shared attributes"], "new or age-unknown accounts sharing a device (≥ 6), IP (≥ 9) or KYC (≥ 8)");
  assert.equal(s["Money tracing"]["Smallest amounts"], "structure ignores links below ₹1,500 and episodes below ₹12,000");
  assert.equal(s["False-positive defences"]["Pooled account"], "≥ 44 counterparties over ≥ 5 d; traced money stops there");
  assert.equal(s["False-positive defences"].Sink, "forwards less than 15% of what it receives");
  // read-only: the panel only formats what it receives
  const frozen = Object.freeze(structuredClone(cfg));
  assert.doesNotThrow(() => methodSections(frozen));
  assert.deepEqual(frozen, cfg);
});
