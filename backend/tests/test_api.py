"""API flow: upload -> summary -> account -> network/trace -> disposition -> restart persists."""
import csv
import io
from dataclasses import replace
from decimal import Decimal

import pytest
from builder import Scenario, at
from fastapi.testclient import TestClient

from muletrace.api import create_app, csv_safe
from muletrace.config import DEFAULT
from muletrace.demo_data import DECOYS, HERO, generate


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "t.db", autoload_demo=False)
    c = TestClient(app)
    r = c.post("/api/datasets", files={"file": ("demo.csv", generate(), "text/csv")})
    assert r.status_code == 200, r.text
    c.db = tmp_path / "t.db"
    return c


def test_summary_queue_and_account(client):
    s = client.get("/api/summary").json()
    assert s["kpis"]["flagged"] > 0 and s["severity"]["HIGH"] >= 5
    assert s["reviewed_not_flagged"]
    q = client.get("/api/queue").json()["items"]
    assert q[0]["severity"] == "HIGH"
    d = client.get(f"/api/accounts/{HERO['M2']}").json()
    assert d["severity"] == "HIGH" and d["components"] and d["signals"]
    assert sum(c["points"] for c in d["components"]) == d["score"]
    assert all(sig["timeline"] for sig in d["signals"] if sig["qualifies"] and sig["kind"] != "IDENTITY")
    v = client.get(f"/api/accounts/{HERO['V1']}").json()
    assert not v["flagged"] and v["indicator"]["status"] == "INDICATED"
    assert "not a determination" in v["indicator"]["text"]


def test_network_and_trace_bounds(client):
    n = client.get(f"/api/accounts/{HERO['M2']}/network?hops=3").json()
    assert len(n["nodes"]) <= 80
    t = client.get(f"/api/accounts/{HERO['V1']}/trace?dir=fwd").json()
    assert t["mode"] == "flow" and "FIFO attribution" in t["label"]
    assert t["accounting"]["exact"]
    ids = {x["id"] for x in t["nodes"]}
    assert HERO["M1"] in ids and HERO["M2"] in ids
    b = client.get(f"/api/accounts/{HERO['C1']}/trace?dir=back").json()
    assert HERO["V1"] in {x["id"] for x in b["nodes"]}


def test_disposition_persists_across_restart(client):
    r = client.post(f"/api/accounts/{HERO['M2']}/disposition",
                    json={"status": "CONFIRMED", "note": "layering hub", "analyst": "R. Analyst"})
    assert r.status_code == 200
    assert r.json()["audit"][0]["to_status"] == "CONFIRMED"
    c2 = TestClient(create_app(db_path=client.db, autoload_demo=False))
    d = c2.get(f"/api/accounts/{HERO['M2']}").json()
    assert d["disposition"]["status"] == "CONFIRMED"
    assert d["audit"][0]["analyst"] == "R. Analyst"
    assert c2.post(f"/api/accounts/{HERO['M2']}/disposition", json={"status": "BOGUS"}).status_code == 400


def test_upload_rejects_missing_columns(client):
    r = client.post("/api/datasets", files={"file": ("x.csv", b"a,b,c\n1,2,3\n", "text/csv")})
    assert r.status_code == 422
    assert "Missing required columns" in r.json()["detail"]


def test_g10_trace_on_large_payroll_is_capped(tmp_path):
    s = Scenario("g10")
    s.tx("FUNDER", "PROC", 10_000_000, at(1, 9))
    for i in range(1000):
        s.tx("PROC", f"PAYEE{i:04d}", 9_900, at(1, 9, 5, i % 60))
    app = create_app(db_path=tmp_path / "g.db", autoload_demo=False)
    c = TestClient(app)
    assert c.post("/api/datasets", files={"file": ("p.csv", s.csv_bytes(), "text/csv")}).status_code == 200
    t = c.get("/api/accounts/FUNDER/trace?dir=fwd").json()
    assert len(t["nodes"]) <= 51
    assert t["truncated"] and any(n.get("aggregate") for n in t["nodes"])
    assert t["accounting"]["exact"]
    n = c.get("/api/accounts/PROC/network?hops=2").json()
    assert len(n["nodes"]) <= 80 and n["hidden_count"] > 0


def test_g12_fallback_engine_same_contract(tmp_path):
    cfg = replace(DEFAULT, engine="window")
    app = create_app(db_path=tmp_path / "w.db", cfg=cfg, autoload_demo=False)
    c = TestClient(app)
    assert c.post("/api/datasets", files={"file": ("demo.csv", generate(), "text/csv")}).status_code == 200
    q = c.get("/api/queue").json()["items"]
    assert any(i["id"] == HERO["M2"] for i in q)
    d = c.get(f"/api/accounts/{HERO['M2']}").json()
    assert d["flagged"] and d["components"]
    t = c.get(f"/api/accounts/{HERO['M2']}/trace?dir=fwd").json()
    assert t["mode"] == "transactions" and "not traced" in t["label"]
    assert c.get("/api/summary").status_code == 200


def test_observations_filters_and_counts(client):
    """§10 /api/observations: suppressed / near-miss activity behind the "Reviewed and not flagged" page."""
    all_obs = client.get("/api/observations", params={"limit": 5000}).json()
    unflagged = client.get("/api/observations", params={"flagged": "false", "limit": 5000}).json()
    assert unflagged["total"] <= all_obs["total"]
    assert unflagged["items"] and not any(o["flagged"] for o in unflagged["items"])
    assert sum(unflagged["counts"].values()) == unflagged["total"]       # no kind filter: counts cover all
    # kind filter narrows items but not counts; comma list accepted
    two = client.get("/api/observations", params={"flagged": "false", "kind": "POOLED,ORIGIN_ZEROED"}).json()
    assert {o["kind"] for o in two["items"]} == {"POOLED", "ORIGIN_ZEROED"}
    assert two["total"] == unflagged["counts"]["POOLED"] + unflagged["counts"]["ORIGIN_ZEROED"]
    assert two["counts"] == unflagged["counts"]
    # the demo's set-aside accounts carry their stated reason
    victim = client.get("/api/observations", params={"q": HERO["V1"].lower()}).json()["items"]
    assert any(o["account"] == HERO["V1"] and o["kind"] == "ORIGIN_ZEROED" for o in victim)
    page = client.get("/api/observations", params={"limit": 5, "offset": 5}).json()
    assert page["items"] == all_obs["items"][5:10]


def export_rows(c, **params):
    r = c.get("/api/export/queue.csv", params=params)
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"\xef\xbb\xbf")
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))


@pytest.mark.parametrize("params", [
    {}, {"severity": "HIGH"}, {"severity": "MEDIUM,LOW"}, {"pattern": "RELAY"}, {"pattern": "ROUND_TRIP,IDENTITY"},
    {"status": "OPEN"}, {"q": "ac55"}, {"severity": "HIGH", "pattern": "HUB", "status": "OPEN", "q": "AC5"},
    {"severity": "HIGH", "q": "no-such-account"},
])
def test_t21_export_matches_queue(client, params):
    """§10 export: same membership, order, scores and severities as /api/queue for the same filters."""
    q = client.get("/api/queue", params=params).json()["items"]
    rows = export_rows(client, **params)
    assert [r["id"] for r in rows] == [i["id"] for i in q]
    assert [int(r["score"]) for r in rows] == [i["score"] for i in q]
    assert [r["severity"] for r in rows] == [i["severity"] for i in q]
    assert [int(r["rank"]) for r in rows] == list(range(1, len(q) + 1))
    assert [Decimal(r["exposure"]) for r in rows] == [Decimal(i["exposure"]).scaleb(-2) for i in q]


def test_t21_export_headers_and_currency(client):
    r = client.get("/api/export/queue.csv")
    assert r.headers["content-type"].startswith("text/csv")
    ds = client.get("/api/datasets/current").json()["dataset"]
    disp = r.headers["content-disposition"]
    assert disp.startswith("attachment;")
    assert ds["sha256"][:12] in disp and ds["config_hash"] in disp
    rows = export_rows(client)
    hero = next(x for x in rows if x["id"] == HERO["M2"])
    assert hero["currency"] == "INR" and hero["exposure_display"].startswith("₹")
    assert "₹" in r.content.decode("utf-8")                 # encode/decode round trip


def test_t21_export_carries_analyst_decision(client):
    assert export_rows(client, q=HERO["M2"])[0]["decision"] == "OPEN"
    client.post(f"/api/accounts/{HERO['M2']}/disposition",
                json={"status": "CONFIRMED", "note": "Rapid layering confirmed", "analyst": "R. Iyer"})
    row = export_rows(client, q=HERO["M2"])[0]
    assert (row["decision"], row["decision_analyst"], row["decision_note"]) == \
        ("CONFIRMED", "R. Iyer", "Rapid layering confirmed")
    assert row["decision_at_utc"]
    assert [r["id"] for r in export_rows(client, status="CONFIRMED")] == [HERO["M2"]]


def test_t21_csv_safe_prefixes_formula_cells():
    for v in ("=SUM(A1)", "+1", "-2+3", "@cmd", "\tx", "\rx"):
        assert csv_safe(v) == "'" + v
    for v in ("AC5530", "₹4,80,000", "", "a=b"):
        assert csv_safe(v) == v
    assert csv_safe(95) == 95 and csv_safe(Decimal("4800.00")) == Decimal("4800.00")


def test_t21_export_protects_formula_like_accounts(tmp_path):
    s = Scenario("t21f").background()
    s.chain(["V", "=M1", "+M2", "-M3", "@M4", "X"], 420_000, at(12, 10, 2), 5)
    c = TestClient(create_app(db_path=tmp_path / "f.db", autoload_demo=False))
    assert c.post("/api/datasets", files={"file": ("f.csv", s.csv_bytes(), "text/csv")}).status_code == 200
    queue_ids = [i["id"] for i in c.get("/api/queue").json()["items"]]
    assert {"=M1", "+M2", "-M3", "@M4"} <= set(queue_ids)
    rows = export_rows(c)
    assert [r["id"] for r in rows] == ["'" + i if i[0] in "=+-@" else i for i in queue_ids]
    for r in rows:
        int(r["score"]), Decimal(r["exposure"]), int(r["rank"])      # numeric cells stay numeric
        assert not any(v.startswith(("=", "+", "-", "@")) for v in r.values()), r


def test_t21_export_group_item_is_one_row(tmp_path):
    s = Scenario("t21g")
    for i in range(20):
        s.account(f"U{i}", ip="198.51.100.7")
        s.tx(f"U{i}", "SHOP5", 100, at(0, 10, i))
    c = TestClient(create_app(db_path=tmp_path / "g.db", autoload_demo=False))
    assert c.post("/api/datasets", files={"file": ("g.csv", s.csv_bytes(), "text/csv")}).status_code == 200
    groups = [i for i in c.get("/api/queue").json()["items"] if i["type"] == "group"]
    assert len(groups) == 1
    rows = [r for r in export_rows(c) if r["type"] == "group"]
    assert len(rows) == 1 and rows[0]["id"] == groups[0]["id"]
    assert rows[0]["members"].split("; ") == groups[0]["members"]


def hero_case(c):
    return c.get(f"/api/accounts/{HERO['M2']}").json()["cases"][0]


def test_case_network_shows_whole_case(client):
    cid = hero_case(client)
    detail = client.get(f"/api/cases/{cid}").json()
    g = client.get(f"/api/cases/{cid}/network").json()
    assert g["mode"] == "network" and g["case"] == cid and g["focus"] == "" and not g["truncated"]
    assert {n["id"] for n in g["nodes"]} == {m["id"] for m in detail["members"]}
    # every case transaction appears once, on the edge between its sender and receiver
    timeline = {t["txn_id"]: t for t in detail["timeline"]}
    assert sum(e["count"] for e in g["edges"]) == detail["metrics"]["transactions"] == len(timeline)
    for e in g["edges"]:
        assert all((timeline[t]["sender"], timeline[t]["receiver"]) == (e["source"], e["target"]) for t in e["txn_ids"])
        assert e["total"] == sum(timeline[t]["amount"] for t in e["txn_ids"])
        assert e["suspicious"]
    roles = {n["id"]: n["role"] for n in g["nodes"]}
    assert roles == {m["id"]: m["role"] for m in detail["members"]}
    assert roles[HERO["V1"]] == "ORIGIN" and roles[HERO["M2"]] == "HUB"
    assert not any(n["focus"] for n in g["nodes"])
    assert client.get("/api/cases/CASE-99/network").status_code == 404


def test_case_network_reflects_decisions(client):
    cid = hero_case(client)
    client.post(f"/api/accounts/{HERO['M1']}/disposition", json={"status": "CONFIRMED", "note": "", "analyst": "a"})
    g = client.get(f"/api/cases/{cid}/network").json()
    assert next(n for n in g["nodes"] if n["id"] == HERO["M1"])["status"] == "CONFIRMED"


def test_case_network_caps_large_case(tmp_path):
    s = Scenario("cn").background()
    s.tx("FUND", "DIST", 12_000_000, at(12, 10))
    for i in range(110):
        s.tx("DIST", f"OUT{i:03d}", 108_000, at(12, 10, 5, i))
    c = TestClient(create_app(db_path=tmp_path / "c.db", autoload_demo=False))
    assert c.post("/api/datasets", files={"file": ("c.csv", s.csv_bytes(), "text/csv")}).status_code == 200
    cid = c.get("/api/accounts/DIST").json()["cases"][0]
    members = c.get(f"/api/cases/{cid}").json()["members"]
    assert len(members) > 80
    g = c.get(f"/api/cases/{cid}/network").json()
    ids = {n["id"] for n in g["nodes"]}
    assert len(ids) == 80 and g["truncated"] and g["hidden_count"] == len(members) - 80
    assert {"FUND", "DIST"} <= ids
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    assert connected(ids, g["edges"])


def test_case_network_fallback_engine(tmp_path):
    c = TestClient(create_app(db_path=tmp_path / "w.db", cfg=replace(DEFAULT, engine="window"), autoload_demo=False))
    assert c.post("/api/datasets", files={"file": ("demo.csv", generate(), "text/csv")}).status_code == 200
    cases = c.get(f"/api/accounts/{HERO['M2']}").json()["cases"]
    assert cases
    for cid in cases:
        g = c.get(f"/api/cases/{cid}/network").json()
        assert g["mode"] == "network" and g["nodes"]


def connected(nodes: set[str], edges: list[dict]) -> bool:
    adj = {n: set() for n in nodes}
    for e in edges:
        adj[e["source"]].add(e["target"])
        adj[e["target"]].add(e["source"])
    seen, stack = set(), [next(iter(nodes))]
    while stack:
        a = stack.pop()
        if a not in seen:
            seen.add(a)
            stack.extend(adj[a] - seen)
    return seen == nodes


def test_case_network_large_case_stays_connected(tmp_path):
    """Over the node cap the drawn part is grown along case transactions, not picked by score alone."""
    import random
    names = [f"R{i:03d}" for i in range(120)]
    random.Random(5).shuffle(names)                     # score / name order unrelated to chain order
    s = Scenario("cc").background()
    s.chain(["V"] + names + ["X"], 400_000, at(12, 10), 3)
    c = TestClient(create_app(db_path=tmp_path / "cc.db", autoload_demo=False))
    assert c.post("/api/datasets", files={"file": ("cc.csv", s.csv_bytes(), "text/csv")}).status_code == 200
    big = max((c.get(f"/api/cases/{cid}").json() for cid in
               {cid for n in names for cid in c.get(f"/api/accounts/{n}").json()["cases"]}),
              key=lambda d: len(d["members"]))
    assert len(big["members"]) > 80
    g = c.get(f"/api/cases/{big['id']}/network").json()
    ids = {n["id"] for n in g["nodes"]}
    assert len(ids) == 80 and g["hidden_count"] == len(big["members"]) - 80
    assert connected(ids, g["edges"])


def case_of(c, account):
    cid = c.get(f"/api/accounts/{account}").json()["cases"][0]
    return c.get(f"/api/cases/{cid}").json(), c.get(f"/api/cases/{cid}/network").json()


@pytest.mark.parametrize("decoy", [DECOYS["PAYROLL"], DECOYS["NEAR_MISS"]])
def test_g15_unflagged_case_assigns_no_roles(client, decoy):
    """§7.2: a flow nobody was flagged for does not label its participants (payroll decoy, near miss)."""
    detail, graph = case_of(client, decoy)
    assert detail["flagged"] == 0 and not any(m["flagged"] for m in detail["members"])
    assert all(m["role"] is None for m in detail["members"])
    assert detail["origins"] == [] and detail["metrics"]["value_from_origins"] is None
    assert {m["id"]: m["role"] for m in detail["members"]} == {n["id"]: n["role"] for n in graph["nodes"]}
    # the account page agrees, and no possible-victim wording appears for any member
    for m in detail["members"]:
        acc = client.get(f"/api/accounts/{m['id']}").json()
        assert acc["role"] == m["role"] and acc["indicator"]["status"] == "NOT_ASSESSED"
    # everything else about the case is still reported
    assert detail["metrics"]["transactions"] > 0 and detail["timeline"] and detail["metrics"]["value_moved"] > 0


def test_g15_flagged_case_keeps_roles_origins_and_value(client):
    detail, graph = case_of(client, HERO["M2"])
    roles = {m["id"]: m["role"] for m in detail["members"]}
    assert roles[HERO["V1"]] == roles[HERO["V2"]] == "ORIGIN" and roles[HERO["M2"]] == "HUB"
    assert set(detail["origins"]) == {HERO["V1"], HERO["V2"]}
    assert detail["metrics"]["value_from_origins"] > 0
    assert roles == {n["id"]: n["role"] for n in graph["nodes"]}


def test_g15_pooled_member_of_unflagged_case_still_shows_pooled(tmp_path):
    s = Scenario("g15p").background()
    s.account("MERCH", created=at(-900))
    for d in range(12):
        for k in range(8):
            s.tx(f"BUY{d}{k}", "MERCH", 900 + 50 * k, at(d, 10, k * 5))
        s.tx("MERCH", "MERCH-BANK", 0.95 * sum(900 + 50 * k for k in range(8)), at(d, 22))
    s.tx("ORIG", "ISO", 200_000, at(12, 11, 0))         # one isolated pass-through into the merchant
    s.tx("ISO", "MERCH", 198_000, at(12, 11, 10))
    c = TestClient(create_app(db_path=tmp_path / "p.db", autoload_demo=False))
    assert c.post("/api/datasets", files={"file": ("p.csv", s.csv_bytes(), "text/csv")}).status_code == 200
    detail, graph = case_of(c, "ISO")
    roles = {m["id"]: m["role"] for m in detail["members"]}
    assert detail["flagged"] == 0 and "MERCH" in roles
    assert roles["MERCH"] == "POOLED"
    assert all(r is None for a, r in roles.items() if a != "MERCH")
    assert detail["origins"] == [] and detail["metrics"]["value_from_origins"] is None
    assert roles == {n["id"]: n["role"] for n in graph["nodes"]}
