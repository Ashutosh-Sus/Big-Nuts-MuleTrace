"""All detection thresholds and scoring weights (ARCHITECTURE §4–§8).

Amounts are expressed in major currency units here and converted to minor units
(x100) by `Config.minor()`. Durations are seconds.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

MIN = 60
HOUR = 3600
DAY = 86400


@dataclass(frozen=True)
class Config:
    engine: str = "flow"                     # "flow" | "window" (fallback)

    # time
    local_offset_minutes: int = 330          # IST, fixed offset
    step_unit_seconds: int = HOUR
    step_base_epoch: int = 1_704_047_400     # 2024-01-01 00:00 IST

    # flow engine
    horizon: int = 72 * HOUR
    min_link: int = 1_000                    # major units
    min_episode: int = 10_000                # major units
    tier_dwell: tuple = (30 * MIN, 6 * HOUR, 72 * HOUR)        # STRONG, MODERATE, WEAK
    tier_conservation: tuple = (0.90, 0.80, 0.70)

    # hub
    hub_burst: int = 6 * HOUR
    hub_min_senders: int = 3
    hub_min_receivers: int = 3

    # layered receipt
    receipt_min_relays: int = 2
    receipt_strong_span: int = 6 * HOUR
    receipt_moderate_span: int = 72 * HOUR

    # round trip
    rt_max_hops: int = 6
    rt_strong_span: int = 24 * HOUR
    rt_strong_return: float = 0.50
    rt_moderate_span: int = 72 * HOUR
    rt_moderate_return: float = 0.30
    rt_branch_cap: int = 10

    # relay chains
    chain_min_relays: int = 3
    corroborated_span: int = 60 * MIN
    repeated_min_episodes: int = 3
    sink_forward_max: float = 0.20

    # profiles
    new_account_days: int = 30
    establishment_span_days: int = 14
    relationship_days: int = 7
    # a pair is ESTABLISHED for a payment only if its history older than relationship_days is at least
    # this share of what the pair moved in the last relationship_days, that payment included (§4)
    relationship_history_share: float = 0.50
    pooled_min_counterparties: int = 50
    pooled_min_span: int = 7 * DAY

    # identity
    cluster_min_size: tuple = (("device", 3), ("ip", 4), ("kyc", 2))
    infra_min_established: int = 5
    infra_established_share: float = 0.60
    ip_group_collapse: int = 15

    # roles / mitigations
    origin_own_funds_share: float = 0.50
    established_share: float = 0.80
    victim_return_dust: int = 1_000          # major units

    # scoring
    pts_relay: tuple = (35, 20)              # STRONG, MODERATE
    pts_hub: tuple = (25, 15)
    pts_receipt: tuple = (20, 10)
    pts_extra_base: int = 5
    pts_repeated: int = 5
    pts_chain: int = 10
    pts_corroborated: int = 25
    pts_consolidation: int = 10
    cap_flow: int = 60
    pts_round_trip: tuple = (20, 12)
    cap_circularity: int = 20
    pts_identity_strong: int = 15
    pts_identity_ip: int = 8
    pts_identity_extra: int = 5
    cap_identity: int = 20
    severity_high: int = 60
    severity_medium: int = 35

    # graph limits
    network_max_nodes: int = 80
    trace_max_nodes: int = 50
    trace_max_hops: int = 8

    # ingestion limits
    max_upload_bytes: int = 20 * 1024 * 1024
    max_rows: int = 200_000

    def minor(self, major: int) -> int:
        return major * 100

    def min_size(self, attr: str) -> int:
        return dict(self.cluster_min_size)[attr]

    def as_dict(self) -> dict:
        return asdict(self)

    def hash(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


DEFAULT = Config()
