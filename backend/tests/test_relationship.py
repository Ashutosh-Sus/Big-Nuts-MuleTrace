"""Relationship strength (ARCHITECTURE §4): a relationship counts as ESTABLISHED for a payment only when
history older than 7 days is commensurate with what the pair moved in the last 7 days (R1–R6)."""
from datetime import timedelta

import pytest
from builder import BASE, Scenario, at, kinds

from muletrace.config import DEFAULT
from muletrace.demo_data import HERO, generate
from muletrace.ingest import parse_csv
from muletrace.pipeline import analyze
from muletrace.profiles import ESTABLISHED, NOVEL

OLD = BASE - timedelta(days=800)


def state(an, sender, receiver, amount=None):
    """Relationship state of the largest (or given-amount) payment sender -> receiver."""
    txs = [t for t in an.ds.txns if t.sender == sender and t.receiver == receiver
           and (amount is None or t.amount == amount * 100)]
    return an.ds.relationship_of(max(txs, key=lambda t: (t.amount, t.idx)))


def seeded_chain(prior: list[tuple[int, float]], amount: float = 300_000, name: str = "r"):
    s = Scenario(name).background()
    for day, value in prior:
        s.tx("V", "G1", value, at(day, 10))
    s.chain(["V", "G1", "G2", "G3", "OUT"], amount, at(15, 10), 5)
    return s.run()


def assert_network_detected(an):
    for a in ("G2", "G3"):
        assert an.results[a].flagged and "RELAY" in kinds(an, a), a
    assert "LAYERED_RECEIPT" in kinds(an, "OUT")


def assert_seeding_defeated(an):
    assert state(an, "V", "G1", 300_000) == NOVEL
    assert an.cases.roles["G1"] != "ORIGIN"
    assert "G1" not in an.cases.origin_of
    assert an.cases.roles["V"] == "ORIGIN" and not an.results["V"].flagged
    assert an.cases.indicator["V"]["status"] == "INDICATED"
    assert an.cases.case_of["V"] == an.cases.case_of["G1"] == an.cases.case_of["G2"]
    for a in ("G1", "G2", "G3"):
        r = an.results[a]
        assert r.severity == "HIGH", (a, r.score, [(c.rule, c.points) for c in r.components])
        assert any(c.rule == "CORROBORATED_LAYERING" for c in r.components), a
    assert_network_detected(an)


# ---------------------------------------------------------------- R1 relationship-seeding attack

def test_r1_tiny_prior_payment_does_not_establish_relationship():
    an = seeded_chain([(1, 1_000)])
    assert_seeding_defeated(an)
    # the suspicious episode keeps its full tier: no relationship mitigation on G1
    for eid in an.fg.episodes_by_account["G1"]:
        assert not an.fg.episodes[eid].mitigations


# ---------------------------------------------------------------- R2 genuine established relationship

def test_r2_repeated_comparable_history_is_established_and_protected():
    s = Scenario("r2").background()
    s.account("STUDENT", created=OLD).account("FAMILY", created=OLD).account("HOSTEL", created=OLD)
    for d in (0, 7, 14):
        s.tx("FAMILY", "STUDENT", 60_000, at(d, 10))
        s.tx("STUDENT", "HOSTEL", 58_000, at(d, 10, 20))
    s.tx("FAMILY", "STUDENT", 60_000, at(21, 10))
    s.tx("STUDENT", "HOSTEL", 58_000, at(21, 10, 20))
    an = s.run()
    assert state(an, "FAMILY", "STUDENT") == ESTABLISHED
    assert state(an, "STUDENT", "HOSTEL") == ESTABLISHED
    eps = [an.fg.episodes[e] for e in an.fg.episodes_by_account["STUDENT"]
           if an.fg.episodes[e].start >= at(21).timestamp()]
    assert eps and all(set(e.mitigations) == {"ESTABLISHED_FUNDING", "ESTABLISHED_PAYEES"}
                       for e in eps if e.tier is not None)
    for a in ("STUDENT", "FAMILY", "HOSTEL"):
        assert not an.results[a].flagged, a


def test_r2b_single_comparable_salary_with_raise_is_established():
    """A salary that grew (82k -> 125k, the hero victim's history) is still an established relationship."""
    s = Scenario("r2b").background()
    s.tx("EMPX", "VICX", 82_000, at(0, 9))
    s.tx("EMPX", "VICX", 125_000, at(24, 9, 40))
    an = s.run()
    assert state(an, "EMPX", "VICX", 125_000) == ESTABLISHED


# ---------------------------------------------------------------- R3 hero victim / G4 regression

@pytest.fixture(scope="module")
def demo():
    res = parse_csv(generate(), DEFAULT)
    return analyze(res.txns, DEFAULT, res.report["currency"])


def test_r3_hero_unchanged(demo):
    an = demo
    assert an.results[HERO["M2"]].score == 95 and an.results[HERO["M2"]].severity == "HIGH"
    for v in ("V1", "V2"):
        a = HERO[v]
        assert an.cases.roles[a] == "ORIGIN" and not an.results[a].flagged
        assert an.cases.indicator[a]["status"] == "INDICATED"
    # V2's scam-day salary still comes over an established relationship
    assert state(an, HERO["EMP_V2"], HERO["V2"], 125_000) == ESTABLISHED
    case = an.cases.case(an.cases.case_of[HERO["M2"]][0])
    assert sorted(case.origins) == sorted([HERO["V1"], HERO["V2"]])


# ---------------------------------------------------------------- R4 established-account mule (G13)

def test_r4_established_account_mule_with_seeded_boundaries_stays_high():
    s = Scenario("r4").background()
    s.account("EMULE", created=BASE - timedelta(days=730))
    for d in (0, 10, 20):
        s.tx("EMULE-JOB", "EMULE", 60_000, at(d, 9))
        s.tx("EMULE", "EMULE-RENT", 20_000, at(d, 12))
    s.tx("V", "M0", 1_000, at(5, 10))                  # seeded victim -> first mule
    s.tx("M3", "X", 500, at(5, 11))                    # seeded last mule -> cash-out
    s.chain(["V", "M0", "EMULE", "M2", "M3", "X"], 300_000, at(22, 10), 5)
    an = s.run()
    assert an.results["EMULE"].severity == "HIGH"
    assert an.cases.roles["EMULE"] != "ORIGIN" and an.cases.roles["M0"] != "ORIGIN"
    assert an.cases.roles["V"] == "ORIGIN"
    for a in ("M0", "EMULE", "M2", "M3"):
        assert an.results[a].severity == "HIGH", a


# ---------------------------------------------------------------- R5 ratio sweep / threshold exploits

@pytest.mark.parametrize("prior", [300, 1_000, 15_000, 75_000, 145_000])
def test_r5_history_below_half_the_new_value_never_establishes(prior):
    assert_seeding_defeated(seeded_chain([(1, prior)], name=f"r5a{prior}"))


@pytest.mark.parametrize("prior", [150_000, 300_000, 600_000])
def test_r5_commensurate_history_is_established_and_network_still_detected(prior):
    """At or above the ratio the history is genuine by definition; the cost to an attacker is moving at least
    half the attack value through the pair a week in advance. The rest of the network is still detected."""
    an = seeded_chain([(1, prior)], name=f"r5b{prior}")
    assert state(an, "V", "G1", 300_000) == ESTABLISHED
    assert_network_detected(an)


def test_r5_splitting_cannot_stretch_thin_history():
    """₹1 L of history, then ₹3 L sent as six ₹50k transfers: each transfer is judged against the pair's
    whole recent volume, so the transfers beyond 2x the history are NOVEL and the case keeps the victim."""
    s = Scenario("r5s").background()
    s.tx("V", "G1", 100_000, at(1, 10))
    for k in range(6):
        s.tx("V", "G1", 50_000, at(15, 10, k))
    s.chain(["G1", "G2", "G3", "OUT"], 298_000, at(15, 10, 10), 5)
    an = s.run()
    split = [t for t in an.ds.txns if t.sender == "V" and t.receiver == "G1" and t.ts >= at(15).timestamp()]
    states = [an.ds.relationship_of(t) for t in split]
    assert states == [ESTABLISHED] * 4 + [NOVEL] * 2
    assert an.cases.roles["G1"] != "ORIGIN" and an.cases.roles["V"] == "ORIGIN"
    assert an.results["G1"].flagged
    assert_network_detected(an)


def test_r5_recent_padding_does_not_count_as_history():
    """Volume sent inside the 7-day window is recent activity, not history — it raises the bar instead."""
    an = seeded_chain([(1, 1_000), (12, 150_000)], name="r5p")
    assert state(an, "V", "G1", 300_000) == NOVEL
    assert an.cases.roles["G1"] != "ORIGIN"


# ---------------------------------------------------------------- R6 many tiny vs few meaningful

def test_r6_many_tiny_payments_do_not_establish():
    prior = [(1 + k // 10, 200) for k in range(60)]          # 60 payments over 6 days, ₹12,000 in total
    an = seeded_chain(prior, name="r6a")
    assert_seeding_defeated(an)


def test_r6_few_meaningful_payments_establish():
    an = seeded_chain([(1, 100_000), (3, 100_000)], name="r6b")   # 2 payments, ₹2 L in total
    assert state(an, "V", "G1", 300_000) == ESTABLISHED
    assert_network_detected(an)
