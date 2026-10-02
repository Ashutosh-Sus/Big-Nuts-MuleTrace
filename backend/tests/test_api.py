"""API flow: upload -> summary -> account -> network/trace -> disposition -> restart persists."""
from dataclasses import replace

import pytest
from builder import Scenario, at
from fastapi.testclient import TestClient

from muletrace.api import create_app
from muletrace.config import DEFAULT
from muletrace.demo_data import HERO, generate


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
