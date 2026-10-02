// The method panel's rows, built only from `/api/config` values. Amounts in the configuration are major units of
// the dataset currency; durations are seconds. Nothing here can change the configuration.
import { duration, money, pct } from "../format.ts";

export type MethodConfig = Record<string, any>;
export interface MethodSection { title: string; rows: [string, string][] }

const major = (v: number) => money(v * 100);
const tiers = ["Strong", "Moderate", "Weak"];

export function methodSections(c: MethodConfig): MethodSection[] {
  const [relayS, relayM] = c.pts_relay, [hubS, hubM] = c.pts_hub, [recS, recM] = c.pts_receipt;
  const [rtS, rtM] = c.pts_round_trip;
  const sizes = Object.fromEntries(c.cluster_min_size as [string, number][]);
  return [
    { title: "Severity", rows: [
      ["High", `score ≥ ${c.severity_high}`],
      ["Medium", `score ${c.severity_medium}–${c.severity_high - 1}`],
      ["Low", `flagged, score below ${c.severity_medium}`],
    ] },
    { title: `Score — evidence-strength index, max ${c.cap_flow + c.cap_circularity + c.cap_identity}`, rows: [
      [`Money flow (cap ${c.cap_flow})`, `pass-through ${relayS} / ${relayM} · fan-in → fan-out ${hubS} / ${hubM} · `
        + `layered receipt ${recS} / ${recM} (strong / moderate)`],
      ["Money-flow bonuses", `+${c.pts_extra_base} each further pattern · +${c.pts_repeated} repeated `
        + `(≥ ${c.repeated_min_episodes} episodes) · +${c.pts_chain} relay chain (≥ ${c.chain_min_relays} relays) · `
        + `+${c.pts_corroborated} corroborated layering (≥ ${c.chain_min_relays} strong relays within `
        + `${duration(c.corroborated_span)}) · +${c.pts_consolidation} consolidation`],
      [`Circularity (cap ${c.cap_circularity})`, `circular flow ${rtS} / ${rtM} (strong / moderate)`],
      [`Shared identity (cap ${c.cap_identity})`, `device or KYC ${c.pts_identity_strong} · IP only `
        + `${c.pts_identity_ip} · +${c.pts_identity_extra} each further attribute type`],
    ] },
    { title: "Pass-through strength", rows: (c.tier_dwell as number[]).map((d, i) => [tiers[i],
      `held ≤ ${duration(d)}, ≥ ${pct(c.tier_conservation[i])} passed on${i === 2 ? " — recorded, not scored" : ""}`]) },
    { title: "Patterns", rows: [
      ["Fan-in → fan-out", `≥ ${c.hub_min_senders} senders and ≥ ${c.hub_min_receivers} receivers within ${duration(c.hub_burst)}`],
      ["Layered receipt", `funds through ≥ ${c.receipt_min_relays} relays: strong ≤ ${duration(c.receipt_strong_span)}, `
        + `moderate ≤ ${duration(c.receipt_moderate_span)}`],
      ["Circular flow", `≤ ${c.rt_max_hops} hops: strong ≤ ${duration(c.rt_strong_span)} and ≥ ${pct(c.rt_strong_return)} `
        + `returned, moderate ≤ ${duration(c.rt_moderate_span)} and ≥ ${pct(c.rt_moderate_return)}`],
      ["Shared attributes", `new or age-unknown accounts sharing a device (≥ ${sizes.device}), IP (≥ ${sizes.ip}) or KYC (≥ ${sizes.kyc})`],
    ] },
    { title: "Money tracing", rows: [
      ["Linking", `first in, first out; funds held longer than ${duration(c.horizon)} are not linked`],
      ["Smallest amounts", `structure ignores links below ${major(c.min_link)} and episodes below ${major(c.min_episode)}`],
      ["Traces", `up to ${c.trace_max_hops} hops`],
    ] },
    { title: "False-positive defences", rows: [
      ["Pooled account", `≥ ${c.pooled_min_counterparties} counterparties over ≥ ${duration(c.pooled_min_span)}; traced money stops there`],
      ["Established relationship", `payments older than ${c.relationship_days} days worth ≥ `
        + `${pct(c.relationship_history_share)} of the pair's last ${c.relationship_days} days`],
      ["History downgrade", `≥ ${pct(c.established_share)} of an episode's funding or payees established: one tier lower`],
      ["Shared infrastructure", `≥ ${c.infra_min_established} established sharers and ≥ ${pct(c.infra_established_share)} `
        + "of them: not evidence"],
      ["New account", `≤ ${c.new_account_days} days old at first activity`],
      ["Likely origin", `≥ ${pct(c.origin_own_funds_share)} of what it sent into the case from its own funds, or ≥ `
        + `${pct(c.established_share)} from established relationships`],
      ["Sink", `forwards less than ${pct(c.sink_forward_max)} of what it receives`],
    ] },
  ];
}
