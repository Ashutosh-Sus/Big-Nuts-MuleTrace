"""Cases list (`GET /api/cases`): a read-only view of the analysis' cases that contain a flagged account.
It must agree with the case detail endpoint and the Overview count, and never change the analysis."""
import csv
import io
import random

from builder import Scenario
from fastapi.testclient import TestClient
from test_api import client  # noqa: F401  (fixture)
from test_console_fixes import decide, load

from muletrace.api import create_app
from muletrace.demo_data import DECOYS, generate

SEV = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def ids(c) -> list[str]:
    return [i["id"] for i in c.get("/api/cases").json()["items"]]


def assert_matches_detail(c, item):
    d = c.get(f"/api/cases/{item['id']}").json()
    flagged = [m for m in d["members"] if m["flagged"]]
    assert item["accounts"] == len(d["members"]) == d["metrics"]["accounts"]
    assert item["flagged"] == d["flagged"] == len(flagged) > 0
    assert item["origins"] == len(d["origins"])
    for k in ("metrics", "families", "confirmed", "confirmed_flagged", "decided_not_flagged"):
        assert item[k] == d[k], k
    assert item["severity"] == min((m["severity"] for m in flagged), key=SEV.get)
    assert item["severity_counts"] == {s: sum(1 for m in flagged if m["severity"] == s) for s in SEV}
    assert item["fully_confirmed"] == (d["confirmed_flagged"] == d["flagged"])


def test_lists_exactly_the_flagged_cases(client):
    r = client.get("/api/cases").json()
    s = client.get("/api/summary").json()
    assert r["total"] == len(r["items"]) == s["kpis"]["cases"] == 3
    assert ids(client) == ["CASE-03", "CASE-02", "CASE-04"]      # HIGH before MEDIUM, then case order
    assert r["unflagged_cases"] == 2                              # payroll and near-miss flows: not listed
    listed = {m["id"] for i in r["items"] for m in client.get(f"/api/cases/{i['id']}").json()["members"]}
    for decoy in (DECOYS["PAYROLL"], DECOYS["NEAR_MISS"]):
        assert decoy not in listed
    for item in r["items"]:
        assert_matches_detail(client, item)


def test_order_is_severity_then_unconfirmed_then_case_order(client):
    items = client.get("/api/cases").json()["items"]
    keys = [(SEV[i["severity"]], i["fully_confirmed"], int(i["id"].split("-")[1])) for i in items]
    assert keys == sorted(keys)
    # confirming every flagged member of CASE-02 moves it behind the other MEDIUM case, not above or below HIGH
    flagged = [m["id"] for m in client.get("/api/cases/CASE-02").json()["members"] if m["flagged"]]
    for m in flagged[:-1]:
        decide(client, m, "CONFIRMED")
    assert ids(client) == ["CASE-03", "CASE-02", "CASE-04"]      # partly confirmed: still unconfirmed
    decide(client, flagged[-1], "CONFIRMED")
    after = client.get("/api/cases").json()["items"]
    assert [i["id"] for i in after] == ["CASE-03", "CASE-04", "CASE-02"]
    assert after[2]["fully_confirmed"] and after[2]["confirmed_flagged"] == len(flagged)
    # a cleared member is a decision, not a confirmation
    decide(client, flagged[-1], "CLEARED")
    assert ids(client) == ["CASE-03", "CASE-02", "CASE-04"]
    for item in client.get("/api/cases").json()["items"]:
        assert_matches_detail(client, item)


def test_order_is_deterministic_and_independent_of_row_order(tmp_path, client):
    first = client.get("/api/cases").json()
    assert client.get("/api/cases").json() == first
    rows = list(csv.reader(io.StringIO(generate().decode("utf-8"))))
    body = rows[1:]
    random.Random(11).shuffle(body)
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows([rows[0]] + body)
    shuffled = load(tmp_path, buf.getvalue().encode("utf-8"), name="shuffled")
    assert shuffled.get("/api/cases").json() == first


def test_zero_flag_dataset_lists_no_cases(tmp_path):
    c = load(tmp_path, Scenario("calm").background().csv_bytes(), name="calm")
    assert c.get("/api/summary").json()["kpis"]["flagged"] == 0
    r = c.get("/api/cases").json()
    assert r["items"] == [] and r["total"] == 0 and c.get("/api/summary").json()["kpis"]["cases"] == 0


def test_fallback_engine(tmp_path):
    c = load(tmp_path, generate(), engine="window", name="w")
    r = c.get("/api/cases").json()
    assert r["total"] == c.get("/api/summary").json()["kpis"]["cases"] > 0
    keys = [(SEV[i["severity"]], i["fully_confirmed"], int(i["id"].split("-")[1])) for i in r["items"]]
    assert keys == sorted(keys)
    for item in r["items"]:
        assert_matches_detail(c, item)


def test_no_dataset_and_unknown_case(tmp_path, client):
    empty = TestClient(create_app(db_path=tmp_path / "none.db", autoload_demo=False))
    assert empty.get("/api/cases").status_code == 409
    assert client.get("/api/cases/CASE-99").status_code == 404            # case detail unchanged
    assert client.get("/api/cases", params={"unknown": "1"}).json() == client.get("/api/cases").json()
