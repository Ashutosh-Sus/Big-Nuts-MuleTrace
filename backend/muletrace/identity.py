"""Stage 6 (identity): shared device / IP / KYC clusters with specificity (ARCHITECTURE §6.1)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .profiles import ESTABLISHED, Dataset
from .signals import IDENTITY, Finding, Signal

ATTR_TYPES = ("device", "kyc", "ip")


@dataclass
class AttributeGroup:
    attr: str
    value: str
    sharers: list[str]
    eligible: list[str]
    established: list[str]
    infrastructure: bool
    qualifying: bool


@dataclass
class IdentityResult:
    groups: list[AttributeGroup]
    clusters: list[Finding]
    signals: dict[str, Signal]
    cluster_of: dict[str, str] = field(default_factory=dict)
    collapsed_clusters: set[str] = field(default_factory=set)


def build(ds: Dataset) -> IdentityResult:
    cfg = ds.cfg
    sharers: dict[tuple[str, str], set[str]] = defaultdict(set)
    for acc in ds.sorted_accounts():
        for attr in ATTR_TYPES:
            for v in acc.attrs[attr]:
                sharers[(attr, v)].add(acc.id)

    groups: list[AttributeGroup] = []
    for (attr, value) in sorted(sharers):
        members = sorted(sharers[(attr, value)])
        if len(members) < 2:
            continue
        established = [m for m in members if ds.accounts[m].establishment == ESTABLISHED]
        eligible = [m for m in members if ds.accounts[m].establishment != ESTABLISHED]
        infra = (ds.establishment_evidence
                 and len(established) >= cfg.infra_min_established
                 and len(established) / len(members) >= cfg.infra_established_share)
        qualifying = not infra and len(eligible) >= cfg.min_size(attr)
        groups.append(AttributeGroup(attr, value, members, eligible, established, infra, qualifying))

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for g in groups:
        if not g.qualifying:
            continue
        for m in g.eligible:
            parent.setdefault(m, m)
        root = find(g.eligible[0])
        for m in g.eligible[1:]:
            r = find(m)
            if r != root:
                lo, hi = sorted((root, r))
                parent[hi] = lo
                root = lo

    members_of: dict[str, list[str]] = defaultdict(list)
    for m in sorted(parent):
        members_of[find(m)].append(m)

    result = IdentityResult(groups, [], {})
    for k, root in enumerate(sorted(members_of, key=lambda r: (-len(members_of[r]), r)), start=1):
        members = members_of[root]
        mset = set(members)
        cgroups = [g for g in groups if g.qualifying and g.eligible[0] in mset]
        types = sorted({g.attr for g in cgroups})
        context = sorted({e for g in cgroups for e in g.established})
        fid = f"F-ID-{k:03d}"
        ip_only = types == ["ip"]
        collapsed = ip_only and len(members) > cfg.ip_group_collapse and not ds.establishment_evidence
        result.clusters.append(Finding(fid, "IDENTITY_CLUSTER", members, [], {
            "attributes": [{"type": g.attr, "value": g.value, "members": g.eligible,
                            "established_sharers": g.established} for g in cgroups],
            "link_types": types, "context_members": context, "ip_only": ip_only,
            "collapsed": collapsed, "size": len(members),
            "establishment_evidence": ds.establishment_evidence,
        }, 0 if not ip_only else 1))
        if collapsed:
            result.collapsed_clusters.add(fid)
        for m in members:
            mtypes = sorted({g.attr for g in cgroups if m in g.eligible})
            values = [{"type": g.attr, "value": g.value, "shared_with": [x for x in g.eligible if x != m]}
                      for g in cgroups if m in g.eligible]
            strong = any(t in ("device", "kyc") for t in mtypes)
            result.signals[m] = Signal(
                account=m, kind="IDENTITY", family=IDENTITY, raw_tier=0 if strong else 1,
                metrics={"link_types": mtypes, "values": values, "cluster_size": len(members),
                         "ip_only": not strong, "collapsed": collapsed, "restored": False,
                         "establishment": ds.accounts[m].establishment,
                         "establishment_basis": ds.accounts[m].establishment_basis},
                finding=fid,
            )
            result.cluster_of[m] = fid
    return result
