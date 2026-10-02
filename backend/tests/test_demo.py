"""The bundled demonstration dataset behaves exactly as the demo script describes."""
import pytest

from muletrace.config import DEFAULT
from muletrace.demo_data import DECOYS, HERO, generate
from muletrace.ingest import parse_csv
from muletrace.pipeline import analyze


@pytest.fixture(scope="module")
def demo():
    res = parse_csv(generate(), DEFAULT)
    return res, analyze(res.txns, DEFAULT, res.report["currency"])


def test_generator_is_deterministic():
    assert generate() == generate()


def test_ingestion_report_shows_rejections(demo):
    res, _ = demo
    r = res.report
    assert r["rows_rejected"] == 6 and r["duplicates_dropped"] == 1
    reasons = " ".join(e["reason"] for e in r["errors"])
    for needle in ("timestamp", "positive", "self-transfer", "conflicting duplicate", "empty account", "amount"):
        assert needle in reasons


def test_hero_network(demo):
    _, an = demo
    m2 = an.results[HERO["M2"]]
    assert m2.severity == "HIGH" and set(m2.families) == {"FLOW", "CIRCULARITY", "IDENTITY"}
    for k in ("M1", "M3", "M4", "M5"):
        assert an.results[HERO[k]].severity == "HIGH", k
    for k in ("C1", "C3"):
        assert an.results[HERO[k]].flagged
    assert len({cid for k in ("M1", "M2", "M3", "M4", "M5") for cid in an.cases.case_of[HERO[k]]}) == 1


@pytest.mark.parametrize("key", ["V1", "V2"])
def test_hero_victims_are_protected_origins(demo, key):
    _, an = demo
    a = HERO[key]
    assert not an.results[a].flagged, an.results[a].components
    assert an.cases.roles[a] == "ORIGIN"
    assert an.cases.indicator[a]["status"] == "INDICATED"


def test_layered_receipt_does_not_count_origin_as_relay(demo):
    _, an = demo
    for k in ("C1", "C3"):
        sig = an.results[HERO[k]].signals["LAYERED_RECEIPT"]
        assert HERO["V2"] not in sig.metrics["path_accounts"][1:-1]


def test_decoys_not_flagged(demo):
    _, an = demo
    for k in ("MERCHANT", "PAYROLL", "NEAR_MISS", "PARENT", "MERCHANT_BANK"):
        assert not an.results[DECOYS[k]].flagged, k
    office = [a for a, acc in an.ds.accounts.items() if DECOYS["OFFICE_IP"] in acc.attrs["ip"]]
    assert len(office) >= 20
    assert not any(an.results[a].flagged for a in office)


def test_pattern_coverage(demo):
    _, an = demo
    seen = {k for r in an.results.values() for k, s in r.signals.items() if s.qualifies}
    assert seen == {"RELAY", "HUB", "LAYERED_RECEIPT", "ROUND_TRIP", "IDENTITY"}
    ip_only = [r for r in an.results.values() if "IDENTITY" in r.signals and r.signals["IDENTITY"].qualifies
               and r.signals["IDENTITY"].metrics["ip_only"]]
    assert ip_only and all(r.severity == "LOW" for r in ip_only)
