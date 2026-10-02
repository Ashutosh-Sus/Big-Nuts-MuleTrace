"""Case money-flow summary (`GET /api/cases/{id}/summary`): fixed-template sentences from computed case data.
Every number must equal the case data it comes from; the wording must never overstate (no victims, no losses,
no causes), and the existing case views must not change."""
import csv
import io
import random
import re

from builder import Scenario, at
from test_api import client  # noqa: F401  (fixture)
from test_console_fixes import load

from muletrace.demo_data import HERO, generate

BANNED = re.compile(r"victim|stolen|launder|fraud|exposure|because|therefore|so it |in order to|intended", re.I)


def summary(c, cid):
    r = c.get(f"/api/cases/{cid}/summary")
    assert r.status_code == 200, r.text
    return r.json()


def text(s, kind=None):
    return " ".join(line["text"] for line in s["lines"] if kind is None or line["kind"] == kind)


def roles_of(detail, role):
    return sorted(m["id"] for m in detail["members"] if m["role"] == role)


def assert_consistent(c, cid):
    """Every fact in the summary equals the case detail / account data it describes."""
    s, d = summary(c, cid), c.get(f"/api/cases/{cid}").json()
    f, m = s["facts"], d["metrics"]
    assert f["transactions"] == m["transactions"] == d["timeline_total"]
    assert (f["start"], f["end"], f["median_dwell_seconds"], f["value_moved"]) == \
        (m["start"], m["end"], m["median_dwell_seconds"], m["value_moved"])
    assert f["labelled"] == (d["flagged"] > 0)
    assert f["origins"] == sorted(d["origins"]) == roles_of(d, "ORIGIN")
    if f["labelled"]:
        assert f["entry_amount"] == m["value_from_origins"]
        assert f["sinks"] == roles_of(d, "SINK")
        for role, k in f["roles"].items():
            assert k == len(roles_of(d, role))
        flagged = [x["id"] for x in d["members"] if x["flagged"]]
        accounts = {a: c.get(f"/api/accounts/{a}").json() for a in flagged}
        for kind, k in f["patterns"].items():
            assert k == sum(1 for a in flagged if any(sg["kind"] == kind and sg["qualifies"] for sg in accounts[a]["signals"]))
    else:
        assert f["roles"] == {} and f["sinks"] == [] and f["entry_transactions"] == 0
        assert [line["kind"] for line in s["lines"]] == ["period", "roles"]
    assert not BANNED.search(text(s)), text(s)
    if f["transactions"]:
        assert "transaction volume, not an amount lost" in text(s, "period")
    return s, d


def test_hero_case(client):
    s, d = assert_consistent(client, "CASE-03")
    f = s["facts"]
    assert f["origins"] == sorted([HERO["V1"], HERO["V2"]]) and f["entry_amount"] == 60_000_000
    assert [line["kind"] for line in s["lines"]] == ["entry", "movement", "exit", "period"]
    assert "2 likely origin accounts" in text(s, "entry") and "₹6,00,000" in text(s, "entry")
    assert "1 hub and 5 relay accounts" in text(s, "movement") and "7 min" in text(s, "movement")
    assert "3 sink accounts" in text(s, "exit")
    assert "12 case transactions, 25 Mar 10:01–13:34 (3 h 33 min)" in text(s, "period")


def test_case_without_likely_origin_is_circular_and_says_so(client):
    s, d = assert_consistent(client, "CASE-04")
    f = s["facts"]
    assert f["origins"] == [] and f["entry_amount"] == 0 and f["sinks"] == []
    entry = text(s, "entry")
    assert entry.startswith("No likely origin account identified") and "₹0" not in text(s)
    assert "Funds entered" not in entry
    assert f["patterns"]["ROUND_TRIP"] == 4 and "came back to it through other accounts" in text(s, "movement")
    assert text(s, "exit").startswith("No sink account identified")


def test_pass_through_and_fan_out_case(client):
    s, _ = assert_consistent(client, "CASE-02")
    assert s["facts"]["roles"]["HUB"] == 1 and "fan-in → fan-out (1)" in text(s, "movement")
    assert "pass-through (4)" in text(s, "movement") and "+2 more" in text(s, "entry")


def test_case_without_flagged_member_assigns_no_roles(client):
    s, _ = assert_consistent(client, "CASE-01")
    assert "roles are not assigned" in text(s) and "origin" not in text(s).lower()


def test_fallback_engine(tmp_path):
    c = load(tmp_path, generate(), engine="window", name="w")
    for case in c.get("/api/cases").json()["items"]:
        s, _ = assert_consistent(c, case["id"])
        assert s["facts"]["median_dwell_seconds"] is None
        assert "not traced by the fallback engine" in text(s, "movement") and "Median time" not in text(s)
    for cid in ("CASE-01", "CASE-03", "CASE-05"):
        assert_consistent(c, cid)


def test_capped_case_describes_every_case_transaction(tmp_path):
    s = Scenario("big").background()
    s.tx("V", "M1", 3_000_000, at(12, 10))
    s.tx("M1", "M2", 2_990_000, at(12, 10, 4))
    s.tx("M2", "M3", 2_980_000, at(12, 10, 8))
    for i in range(250):
        s.tx("M3", f"OUT{i:03d}", 11_800, at(12, 10, 12, i))
    c = load(tmp_path, s.csv_bytes(), name="big")
    cid = c.get("/api/accounts/M2").json()["cases"][0]
    out, d = assert_consistent(c, cid)
    assert len(d["timeline"]) == 200 < d["timeline_total"] == out["facts"]["transactions"] == 253
    assert "253 case transactions" in text(out, "period")
    assert "in 1 transaction, 13 Mar 10:00." in text(out, "entry")          # one time, not "10:00–10:00"
    assert out["facts"]["exit_transactions"] == 250 and "250 sink accounts" in text(out, "exit") and "+247 more" in text(out, "exit")


def test_every_demo_summary_is_consistent_and_safe(client):
    for i in client.get("/api/cases").json()["items"]:
        assert_consistent(client, i["id"])
    for cid in ("CASE-01", "CASE-05"):
        assert_consistent(client, cid)


def test_deterministic_and_independent_of_row_order(tmp_path, client):
    first = {cid: summary(client, cid) for cid in ("CASE-01", "CASE-02", "CASE-03", "CASE-04", "CASE-05")}
    assert {cid: summary(client, cid) for cid in first} == first
    rows = list(csv.reader(io.StringIO(generate().decode("utf-8"))))
    # the demo carries a conflicting duplicate txn_id; ingestion keeps the first copy, so a shuffle could swap which
    # amount is kept. Dropping the copy ingestion rejects keeps the accepted input the same.
    seen, body = set(), []
    for r in rows[1:]:
        if r[0] not in seen:
            seen.add(r[0])
            body.append(r)
    random.Random(5).shuffle(body)
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows([rows[0]] + body)
    shuffled = load(tmp_path, buf.getvalue().encode("utf-8"), name="shuffled")
    assert {cid: summary(shuffled, cid) for cid in first} == first


def test_existing_case_views_unchanged_and_unknown_case(client):
    before = [client.get(p).content for p in ("/api/cases/CASE-03", "/api/cases/CASE-03/network", "/api/cases")]
    summary(client, "CASE-03")
    assert [client.get(p).content for p in ("/api/cases/CASE-03", "/api/cases/CASE-03/network", "/api/cases")] == before
    assert client.get("/api/cases/CASE-99/summary").status_code == 404
