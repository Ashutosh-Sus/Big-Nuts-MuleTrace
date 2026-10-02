"""Console consistency fixes: counts that reconcile across screens, decisions on any account, reset, bounded
timelines, URL-unsafe account IDs, capped graphs that stay investigable, directional fallback views.
None of these change detection, scoring or tracing."""
from collections import Counter
from dataclasses import replace
from urllib.parse import quote

import pytest
from builder import Scenario, at
from fastapi.testclient import TestClient
from test_api import client, connected  # noqa: F401  (fixture)

from muletrace.api import REVIEW_KINDS, create_app
from muletrace.config import DEFAULT
from muletrace.demo_data import DECOYS, HERO, generate
from muletrace.network import _select_by_level


def load(tmp_path, data: bytes, engine: str = "flow", name: str = "x") -> TestClient:
    c = TestClient(create_app(db_path=tmp_path / f"{name}.db", cfg=replace(DEFAULT, engine=engine),
                              autoload_demo=False))
    r = c.post("/api/datasets", files={"file": (f"{name}.csv", data, "text/csv")})
    assert r.status_code == 200, r.text
    return c


def decide(c, account: str, status: str, note: str = "", analyst: str = "QA"):
    r = c.post(f"/api/accounts/{quote(account, safe='')}/disposition",
               json={"status": status, "note": note, "analyst": analyst})
    assert r.status_code == 200, r.text
    return r.json()


# Overview <-> Not flagged ------------------------------------------------------------------------------

def test_overview_reviewed_count_is_the_not_flagged_page_scope(client):
    """The Overview count and the "Not flagged" page describe the same accounts: every not-flagged account
    with at least one stated reason (all kinds except "no pattern"). The preview may show fewer rows."""
    s = client.get("/api/summary").json()
    page = client.get("/api/observations", params={"flagged": "false", "kind": ",".join(REVIEW_KINDS),
                                                   "limit": 5000}).json()
    accounts = {o["account"] for o in page["items"]}
    assert s["reviewed_total"] == len(accounts) > len(s["reviewed_not_flagged"])
    assert s["review_kinds"] == list(REVIEW_KINDS) and "NO_PATTERN" not in s["review_kinds"]
    assert {r["account"] for r in s["reviewed_not_flagged"]} <= accounts
    # the office-network accounts are each counted (the preview shows the shared statement once)
    office = [o for o in page["items"] if o["kind"] == "INFRA_ATTRIBUTE"]
    assert len({o["account"] for o in office}) > 1
    assert sum(1 for r in s["reviewed_not_flagged"] if r["kind"] == "INFRA_ATTRIBUTE") == 1
    # every reason kind that occurs can appear in the preview (near misses were previously never shown)
    occurring = {o["kind"] for o in page["items"]}
    assert "NEAR_MISS" in occurring and "NEAR_MISS" in {r["kind"] for r in s["reviewed_not_flagged"]}


# decisions on any account (§10: disposition on /api/accounts/{id}; the queue lists flagged accounts) ------

def test_decision_on_unflagged_account_is_reported_consistently(client):
    near = DECOYS["NEAR_MISS"]
    assert not client.get(f"/api/accounts/{near}").json()["flagged"]
    decide(client, near, "CONFIRMED", "looks real")
    s = client.get("/api/summary").json()
    assert s["decided_not_flagged"] == [{"id": near, "status": "CONFIRMED", "analyst": "QA",
                                         "at": s["decided_not_flagged"][0]["at"]}]
    # flagged-account decision counts equal the queue's, so Overview and Queue agree
    for st in ("OPEN", "CONFIRMED", "CLEARED"):
        assert s["status"][st] == client.get("/api/queue", params={"status": st}).json()["total"]
    assert not any(i["id"] == near for i in client.get("/api/queue").json()["items"])
    # the "Not flagged" page, the case and the case graph all carry the decision
    rows = client.get("/api/observations", params={"q": near}).json()["items"]
    assert rows and all(o["status"] == "CONFIRMED" for o in rows)
    cid = client.get(f"/api/accounts/{near}").json()["cases"][0]
    case = client.get(f"/api/cases/{cid}").json()
    assert case["flagged"] == 0 and case["confirmed_flagged"] == 0 and case["decided_not_flagged"] == 1
    assert case["confirmed"] == 1
    node = next(n for n in client.get(f"/api/cases/{cid}/network").json()["nodes"] if n["id"] == near)
    assert node["status"] == "CONFIRMED"
    acc = client.get(f"/api/accounts/{near}").json()
    assert acc["disposition"]["status"] == "CONFIRMED" and acc["audit"][0]["to_status"] == "CONFIRMED"


def test_case_counts_confirmed_flagged_members_separately(client):
    cid = client.get(f"/api/accounts/{HERO['M2']}").json()["cases"][0]
    decide(client, HERO["M2"], "CONFIRMED")
    decide(client, HERO["V1"], "CLEARED")                 # victim: not flagged, member of the hero case
    case = client.get(f"/api/cases/{cid}").json()
    assert case["confirmed_flagged"] == 1 and case["decided_not_flagged"] == 1
    assert case["confirmed_flagged"] <= case["flagged"]


# reset ---------------------------------------------------------------------------------------------------

def test_reset_returns_every_decision_to_open_with_a_matching_audit_entry(client):
    """DEMO.md: rehearse, then Data -> Reset demo. Every account is Open again and its audit history ends
    with the reset, never with a decision that no longer holds."""
    decide(client, HERO["M2"], "CONFIRMED", "rehearsal")
    decide(client, HERO["M3"], "CLEARED", "rehearsal")
    decide(client, HERO["M4"], "CONFIRMED")
    decide(client, HERO["M4"], "OPEN")                    # already open again: nothing to reset
    assert client.post("/api/reset", json={"analyst": "Presenter"}).status_code == 200
    c = client
    for acc, before in ((HERO["M2"], "CONFIRMED"), (HERO["M3"], "CLEARED")):
        d = c.get(f"/api/accounts/{acc}").json()
        assert d["disposition"]["status"] == "OPEN"
        last = d["audit"][0]                              # newest first
        assert (last["action"], last["from_status"], last["to_status"], last["analyst"]) == \
            ("RESET", before, "OPEN", "Presenter")
        assert d["audit"][-1]["action"] == "DISPOSITION"  # history before the reset is kept (append-only)
    m4 = c.get(f"/api/accounts/{HERO['M4']}").json()
    assert m4["audit"][0]["action"] == "DISPOSITION" and m4["audit"][0]["to_status"] == "OPEN"
    s = c.get("/api/summary").json()
    assert s["status"]["CONFIRMED"] == s["status"]["CLEARED"] == 0 and s["decided_not_flagged"] == []


def test_reset_after_upload_reloads_demo_and_keeps_other_datasets_untouched(tmp_path):
    s = Scenario("own").background()
    s.chain(["V", "M1", "M2", "M3", "X"], 300_000, at(12, 10), 3)
    c = load(tmp_path, s.csv_bytes(), name="own")
    decide(c, "M2", "CONFIRMED", "own data")
    own_sha = c.app.state.mt.dataset["sha256"]
    assert c.post("/api/reset", json={"analyst": "P"}).json()["dataset"]["name"] == "demo.csv"
    assert c.app.state.mt.store.dispositions(own_sha)["M2"]["status"] == "CONFIRMED"


# bounded timelines ----------------------------------------------------------------------------------------

def test_case_timeline_reports_its_total_and_filters_by_member(tmp_path):
    s = Scenario("tl").background()
    s.tx("FUND", "DIST", 30_000_000, at(12, 10))
    for i in range(260):
        s.tx("DIST", f"OUT{i:03d}", 112_000, at(12, 10, 5, i))
    c = load(tmp_path, s.csv_bytes(), name="tl")
    cid = c.get("/api/accounts/DIST").json()["cases"][0]
    case = c.get(f"/api/cases/{cid}").json()
    assert case["timeline_total"] == case["metrics"]["transactions"] > len(case["timeline"]) == 200
    assert case["timeline_member"] is None
    last = case["timeline"][-1]["receiver"]
    late = "OUT259"                                       # its transaction is beyond the first 200
    assert late != last and all(t["receiver"] != late for t in case["timeline"])
    one = c.get(f"/api/cases/{cid}", params={"member": late}).json()
    assert one["timeline_member"] == late and one["timeline_total"] == len(one["timeline"]) == 1
    assert one["timeline"][0]["receiver"] == late
    hub = c.get(f"/api/cases/{cid}", params={"member": "DIST"}).json()
    assert hub["timeline_total"] == case["timeline_total"]
    assert c.get(f"/api/cases/{cid}", params={"member": "NOBODY"}).status_code == 404
    # signal timelines say how many transactions they hold, too
    for sig in c.get("/api/accounts/DIST").json()["signals"]:
        assert sig["timeline_total"] >= len(sig["timeline"]) and len(sig["timeline"]) <= 60
    assert any(sig["timeline_total"] > len(sig["timeline"]) for sig in c.get("/api/accounts/DIST").json()["signals"])


# account IDs that are not URL-safe -------------------------------------------------------------------------

ODD = ["ACC/7#9", "ACC?x=1&y", "100%", "SPACE ID", "ÄÇÇ-ünï"]


def test_url_unsafe_account_ids_work_on_every_account_route(tmp_path):
    s = Scenario("odd").background()
    chain = ["VIC"] + ODD + ["END"]
    s.chain(chain, 300_000, at(12, 10), 3)
    c = load(tmp_path, s.csv_bytes(), name="odd")
    for acc in ODD:
        p = quote(acc, safe="")
        d = c.get(f"/api/accounts/{p}")
        assert d.status_code == 200 and d.headers["content-type"].startswith("application/json"), acc
        assert d.json()["id"] == acc
        assert c.get(f"/api/accounts/{p}/transactions").json()["total"] >= 1
        net = c.get(f"/api/accounts/{p}/network", params={"hops": 1}).json()
        assert net["focus"] == acc and acc in {n["id"] for n in net["nodes"]}
        assert c.get(f"/api/accounts/{p}/trace", params={"dir": "fwd"}).json()["focus"] == acc
        assert decide(c, acc, "CLEARED", "odd id")["disposition"]["account_id"] == acc
        assert c.get(f"/api/accounts/{p}").json()["disposition"]["status"] == "CLEARED"
    assert {i["id"] for i in c.get("/api/search", params={"q": "ACC"}).json()["items"]} >= {"ACC/7#9", "ACC?x=1&y"}
    assert c.get(f"/api/accounts/{quote('NOPE/1', safe='')}").status_code == 404


# capped graphs -------------------------------------------------------------------------------------------

def test_capped_neighbourhood_gives_each_hop_level_a_share(tmp_path):
    """Over the 80-node cap, raising the hop count must change what is drawn (not only the hidden count),
    and every drawn account stays attached to a drawn account one hop closer."""
    s = Scenario("lv").background()
    for i in range(20):
        s.tx("F", f"A{i:02d}", 50_000, at(12, 9, i))
        for j in range(5):
            s.tx(f"A{i:02d}", f"B{i:02d}{j}", 9_000, at(12, 10, i, j))
            for k in range(2):
                s.tx(f"B{i:02d}{j}", f"C{i:02d}{j}{k}", 4_000, at(12, 11, i, j * 2 + k))
    c = load(tmp_path, s.csv_bytes(), name="lv")
    two = c.get("/api/accounts/F/network", params={"hops": 2, "suspicious_only": "false"}).json()
    three = c.get("/api/accounts/F/network", params={"hops": 3, "suspicious_only": "false"}).json()
    for g in (two, three):
        assert len(g["nodes"]) == 80 and g["truncated"] and g["hidden_count"] == g["total_count"] - 80
        assert connected({n["id"] for n in g["nodes"]}, g["edges"])
    levels = Counter(n["hop"] for n in three["nodes"])
    assert levels[3] > 0 and levels[1] == 20
    assert {n["id"] for n in two["nodes"]} != {n["id"] for n in three["nodes"]}


def test_level_selection_mixes_ordinary_accounts_when_filter_is_off():
    dist = {"F": 0, **{f"s{i}": 1 for i in range(10)}, **{f"o{i}": 1 for i in range(10)}}
    parents = {a: {"F"} for a in dist if a != "F"}
    via = {a: a.startswith("s") for a in dist}
    rank = lambda a: (a != "F", dist[a], not a.startswith("s"), a)          # suspicious-first, as in `network`
    only = _select_by_level(dist, parents, via, rank, 1, 9, True)
    mixed = _select_by_level(dist, parents, via, rank, 1, 9, False)
    assert not any(a.startswith("o") for a in only)
    assert sum(a.startswith("o") for a in mixed) == 4 and sum(a.startswith("s") for a in mixed) == 4


def ring_bytes() -> bytes:
    """40 victims, each through two relays into one of four collectors, which cash out to two accounts."""
    s = Scenario("ring").background()
    for i in range(40):
        s.account(f"V{i:02d}", created=at(-1500))
        t0 = 9 + i // 8
        s.tx(f"V{i:02d}", f"R{i:02d}A", 300_000, at(12, t0, i % 8 * 6))
        s.tx(f"R{i:02d}A", f"R{i:02d}B", 297_000, at(12, t0, i % 8 * 6 + 4))
        s.tx(f"R{i:02d}B", f"C{i % 4}", 294_000, at(12, t0, i % 8 * 6 + 8))
    for k in range(4):
        for j in range(2):
            s.tx(f"C{k}", f"X{j}", 1_400_000, at(12, 16, k * 10 + j))
    return s.csv_bytes()


def test_capped_case_graph_draws_whole_money_paths(tmp_path):
    """Over the cap the case graph shows complete paths — victim, relays, collector, cash-out — instead of
    filling the picture with victims and hubs and leaving out where the money went."""
    c = load(tmp_path, ring_bytes(), name="ring")
    cid = c.get("/api/accounts/C0").json()["cases"][0]
    members = {m["id"]: m["role"] for m in c.get(f"/api/cases/{cid}").json()["members"]}
    assert len(members) > 80
    g = c.get(f"/api/cases/{cid}/network").json()
    ids = {n["id"] for n in g["nodes"]}
    assert len(ids) == 80 and g["total_count"] == len(members) and connected(ids, g["edges"])
    roles = Counter(members[a] for a in ids)
    assert roles["SINK"] == 2 and roles["COLLECTOR"] == 4 and roles["ORIGIN"] >= 1 and roles["RELAY"] >= 2
    # every drawn victim's money can be followed on the drawing to a cash-out account
    out = {}
    for e in g["edges"]:
        out.setdefault(e["source"], set()).add(e["target"])

    def reaches_sink(a, seen=()):
        return members[a] == "SINK" or any(b not in seen and reaches_sink(b, seen + (a,)) for b in out.get(a, ()))
    assert all(reaches_sink(a) for a in ids if members[a] == "ORIGIN")


# fallback engine: directional transaction views (§10: transaction-level, not traced) -----------------------

def test_fallback_views_follow_the_requested_direction(tmp_path):
    c = load(tmp_path, generate(), engine="window", name="w")
    m2 = HERO["M2"]
    back = c.get(f"/api/accounts/{m2}/trace", params={"dir": "back"}).json()
    fwd = c.get(f"/api/accounts/{m2}/trace", params={"dir": "fwd"}).json()
    assert back["mode"] == fwd["mode"] == "transactions" and "not traced" in back["label"]
    assert "into" in back["label"] and "out of" in fwd["label"]
    assert {e["id"] for e in back["edges"]} != {e["id"] for e in fwd["edges"]}

    def reach(g, start, forward):
        adj = {}
        for e in g["edges"]:
            a, b = (e["source"], e["target"]) if forward else (e["target"], e["source"])
            adj.setdefault(a, set()).add(b)
        seen, stack = set(), [start]
        while stack:
            a = stack.pop()
            if a not in seen:
                seen.add(a)
                stack.extend(adj.get(a, ()))
        return seen
    # every account in "where money came from" sends towards the account; every one in "went" receives from it
    assert reach(back, m2, forward=False) == {n["id"] for n in back["nodes"]}
    assert reach(fwd, m2, forward=True) == {n["id"] for n in fwd["nodes"]}
    assert any(e["target"] == m2 for e in back["edges"]) and all(e["source"] != m2 for e in back["edges"])
    assert any(e["source"] == m2 for e in fwd["edges"]) and all(e["target"] != m2 for e in fwd["edges"])


def test_flow_engine_trace_unchanged_by_fallback_view(client):
    t = client.get(f"/api/accounts/{HERO['M2']}/trace", params={"dir": "fwd"}).json()
    assert t["mode"] == "flow" and t["accounting"]["exact"]


@pytest.mark.parametrize("hops", [1, 2, 3])
def test_uncapped_neighbourhood_is_drawn_whole(client, hops):
    g = client.get(f"/api/accounts/{HERO['M2']}/network", params={"hops": hops, "suspicious_only": "true"}).json()
    assert not g["truncated"] and g["total_count"] == len(g["nodes"])
