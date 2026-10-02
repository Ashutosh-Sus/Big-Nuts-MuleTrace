"""Baseline (S), adversarial (A) and audit-regression (G) scenarios with expected outcomes."""
from datetime import timedelta
from fractions import Fraction

from builder import BASE, Scenario, at, flagged, kinds

from muletrace.flow import trace

OLD = BASE - timedelta(days=800)


def new(day=0):
    return BASE + timedelta(days=day - 5)


# ---------------------------------------------------------------- S: baseline patterns

def test_s1_fan_in_fan_out_hub():
    s = Scenario("s1").background()
    for i in range(5):
        s.tx(f"SRC{i}", "HUB", 100_000, at(12, 10, 2 + i * 4))
    for i, amt in enumerate((130_000, 120_000, 115_000, 115_000)):
        s.tx("HUB", f"DST{i}", amt, at(12, 10, 24 + i * 4))
    an = s.run()
    assert "HUB" in kinds(an, "HUB")
    assert an.results["HUB"].flagged
    for i in range(5):
        assert not an.results[f"SRC{i}"].flagged
    for i in range(4):
        assert not an.results[f"DST{i}"].flagged


def test_s2_cycle_and_negatives():
    s = Scenario("s2").background()
    s.tx("A", "B", 200_000, at(12, 10, 5))
    s.tx("B", "C", 197_000, at(12, 10, 31))
    s.tx("C", "D", 195_000, at(12, 11, 2))
    s.tx("D", "A", 193_000, at(12, 12, 40))
    # reciprocal pair
    s.tx("E", "F", 50_000, at(13, 10))
    s.tx("F", "E", 50_000, at(13, 15))
    # A11: topology G->H->I->G, but I->G happened days before G->H
    s.tx("I", "G", 80_000, at(10, 9))
    s.tx("G", "H", 80_000, at(14, 9))
    s.tx("H", "I", 79_000, at(14, 9, 10))
    an = s.run()
    for a in "ABCD":
        assert "ROUND_TRIP" in kinds(an, a), a
    for a in "EFGHI":
        assert "ROUND_TRIP" not in an.results[a].signals, a
    assert not an.results["E"].flagged and not an.results["F"].flagged
    assert any(o["kind"] == "RECIPROCAL" for o in an.observations("E"))


def test_s3_pass_through_chain_high_and_origin_protected():
    s = Scenario("s3").background()
    s.chain(["V", "M1", "M2", "M3", "M4", "X"], 420_000, at(12, 10, 2), 5)
    an = s.run()
    for m in ("M1", "M2", "M3", "M4"):
        r = an.results[m]
        assert r.severity == "HIGH", (m, r.score)
        assert any(c.rule == "CORROBORATED_LAYERING" for c in r.components)
    assert "LAYERED_RECEIPT" in kinds(an, "X")
    assert not an.results["V"].flagged
    assert an.cases.roles["V"] == "ORIGIN"
    assert an.cases.indicator["V"]["status"] == "INDICATED"
    # background salary -> rent never flagged
    assert not any(a.startswith("BG") for a in flagged(an))


def test_s4_identity_clusters_and_office_network():
    s = Scenario("s4").background()
    for i in range(5):
        s.account(f"N{i}", created=new(12), device="DEV-1")
    s.account("K1", created=new(12), kyc="KYC-9").account("K2", created=new(12), kyc="KYC-9")
    for i in range(20):
        s.account(f"OFF{i}", created=OLD, ip="10.4.0.1")
    s.account("Q1", created=new(12), ip="10.9.9.9").account("Q2", created=new(12), ip="10.9.9.9")
    for i in range(5):
        s.tx(f"N{i}", "SHOP", 500, at(12, 10, i))
    s.tx("K1", "SHOP", 400, at(12, 11)).tx("K2", "SHOP", 400, at(12, 11, 5))
    for i in range(20):
        s.tx(f"OFF{i}", "CANTEEN", 200, at(12, 13, i))
    s.tx("Q1", "SHOP", 300, at(12, 14)).tx("Q2", "SHOP", 300, at(12, 14, 1))
    an = s.run()
    for i in range(5):
        assert "IDENTITY" in kinds(an, f"N{i}")
    assert "IDENTITY" in kinds(an, "K1") and "IDENTITY" in kinds(an, "K2")
    for i in range(20):
        assert not an.results[f"OFF{i}"].flagged
    assert any(o["kind"] == "INFRA_ATTRIBUTE" for o in an.observations("OFF0"))
    assert not an.results["Q1"].flagged


# ---------------------------------------------------------------- A: adversarial suite

def test_a1_threshold_evasion():
    s = Scenario("a1").background()
    s.chain(["V", "R1", "R2", "R3", "X"], 300_000, at(12, 10), 40, keep=0.11)
    s.tx("V2", "ISO", 200_000, at(14, 10)).tx("ISO", "Y", 178_000, at(14, 10, 41))
    an = s.run()
    for r in ("R1", "R2", "R3"):
        assert an.results[r].flagged and an.results[r].signals["RELAY"].final_tier == 1
        assert any(c.rule == "CHAIN" for c in an.results[r].components)
    assert not an.results["ISO"].flagged
    assert any(o["kind"] == "ISOLATED_RELAY" for o in an.observations("ISO"))


def test_a2_slow_layering():
    s = Scenario("a2").background()
    t = at(12, 9)
    accounts = ["V", "L1", "L2", "L3", "L4", "L5", "X"]
    amt = 250_000
    for a, b in zip(accounts, accounts[1:]):
        s.tx(a, b, round(amt), t)
        amt *= 0.99
        t += timedelta(minutes=95)
    an = s.run()
    for a in ("L1", "L2", "L3", "L4", "L5"):
        assert an.results[a].flagged, a
        assert an.results[a].signals["RELAY"].final_tier == 1


def test_a3_split_layering_and_trace_total():
    s = Scenario("a3").background()
    s.tx("V", "M1", 600_000, at(12, 10))
    for k, leg in enumerate("abc"):
        s.tx("M1", f"M2{leg}", 199_000, at(12, 10, 3 + k))
        s.tx(f"M2{leg}", f"M3{leg}", 198_000, at(12, 10, 9 + k))
        s.tx(f"M3{leg}", f"SINK{leg}", 197_000, at(12, 10, 15 + k))
    an = s.run()
    assert an.results["M1"].severity == "HIGH"
    v = [t.idx for t in an.ds.txns if t.sender == "V"]
    tr = trace(an.ds, an.fg, v, "fwd", 8)
    assert tr.accounted() == tr.total_start()
    reached = sum((tr.retained[f"SINK{x}"] for x in "abc"), Fraction(0))
    assert 580_000_00 <= reached <= 600_000_00


def test_a4_converging_paths_consolidation():
    s = Scenario("a4").background()
    for k in range(3):
        s.chain([f"V{k}", f"MA{k}", f"MB{k}", "SINK"], 150_000, at(12, 10 + k, 0), 6)
    an = s.run()
    sink = an.results["SINK"]
    assert "LAYERED_RECEIPT" in kinds(an, "SINK")
    assert any(c.rule == "CONSOLIDATION" for c in sink.components)
    for k in range(3):
        assert not an.results[f"V{k}"].flagged
        assert an.results[f"MA{k}"].flagged


def test_a5_decoy_activity_and_reservoir():
    s = Scenario("a5").background()
    s.tx("FRIEND", "M2", 60_000, at(11, 12))
    s.chain(["V", "M1", "M2", "M3", "X"], 400_000, at(12, 10), 5)
    for k in range(4):
        s.tx("M2", "RECHARGE", 499, at(12, 9 + k, 30))
    an = s.run()
    assert an.results["M2"].severity == "HIGH"
    assert not an.results["RECHARGE"].flagged


def test_a6_shared_infrastructure_with_device_subcluster():
    s = Scenario("a6").background()
    for i in range(24):
        s.account(f"CAMP{i}", created=OLD, ip="172.16.0.1")
    for i in range(6):
        s.account(f"FRESH{i}", created=new(12), ip="172.16.0.1",
                  device="DEV-77" if i < 4 else f"DEV-F{i}")
    for i in range(24):
        s.tx(f"CAMP{i}", "CAFE", 150, at(12, 9, i))
    for i in range(6):
        s.tx(f"FRESH{i}", "CAFE", 150, at(12, 10, i))
    an = s.run()
    for i in range(4):
        assert "IDENTITY" in kinds(an, f"FRESH{i}")
        assert an.results[f"FRESH{i}"].signals["IDENTITY"].metrics["link_types"] == ["device"]
    for i in (4, 5):
        assert not an.results[f"FRESH{i}"].flagged
    for i in range(24):
        assert not an.results[f"CAMP{i}"].flagged


def test_a7_correlated_identity_does_not_stack():
    s = Scenario("a7").background()
    for i in range(4):
        s.account(f"C{i}", created=new(12), device="DV", ip="1.2.3.4", kyc="KY")
        s.tx(f"C{i}", "SHOP2", 100, at(12, 10, i))
    an = s.run()
    for i in range(4):
        r = an.results[f"C{i}"]
        assert r.score == 20 and r.severity == "LOW" and r.families == ["IDENTITY"]


def test_a8_victim_contamination():
    s = Scenario("a8").background()
    s.account("VIC", created=OLD)
    s.tx("EMPLOYER", "VIC", 100_000, at(1, 9))
    s.tx("EMPLOYER", "VIC", 100_000, at(12, 10, 0))     # established relationship by now
    s.tx("VIC", "M1", 95_000, at(12, 10, 20))           # salary -> scam within 20 min
    s.tx("M1", "M2", 94_500, at(12, 10, 24))
    s.tx("M2", "M3", 94_000, at(12, 10, 29))
    s.tx("M3", "CASH", 93_500, at(12, 10, 33))
    s.tx("M1", "VIC", 1, at(12, 9, 50))                 # verification ping
    s.tx("M1", "VIC", 500, at(12, 11, 0))               # small fake refund
    an = s.run()
    assert not an.results["VIC"].flagged
    assert an.cases.roles["VIC"] == "ORIGIN"
    assert an.cases.indicator["VIC"]["status"] == "INDICATED"
    assert an.results["M2"].flagged


def test_a9_merchant_camouflage():
    s = Scenario("a9").background()
    s.account("MERCH", created=OLD)
    for d in range(12):
        for k in range(8):
            s.tx(f"BUY{d}{k}", "MERCH", 900 + 50 * k, at(d, 10, k * 5))
        s.tx("MERCH", "MERCH-BANK", 0.95 * sum(900 + 50 * k for k in range(8)), at(d, 22))
    an = s.run()
    assert an.ds.accounts["MERCH"].pooled
    assert not an.results["MERCH"].flagged
    assert any(o["kind"] == "POOLED" for o in an.observations("MERCH"))


def test_a10_payroll_camouflage_with_and_without_history():
    s = Scenario("a10").background(days=32)
    s.account("PAYCO", created=OLD)
    for month_day in (0, 30):
        s.tx("PARENT", "PAYCO", 3_000_000, at(month_day, 9))
        for e in range(30):
            s.tx("PAYCO", f"EMP{e:02d}", 99_000, at(month_day, 9, 5 + e // 3))
    an = s.run()
    assert not an.results["PAYCO"].flagged
    assert any(o["kind"] in ("MITIGATED", "ISOLATED_RELAY") for o in an.observations("PAYCO"))
    # no history at all: still not flagged (single isolated episode)
    s2 = Scenario("a10b")
    s2.tx("PARENT", "PAYCO", 3_000_000, at(0, 9))
    for e in range(30):
        s2.tx("PAYCO", f"EMP{e:02d}", 99_000, at(0, 9, 5 + e // 3))
    assert not s2.run().results["PAYCO"].flagged


def test_a12_fragmentation_across_routes():
    s = Scenario("a12").background()
    s.tx("V", "M", 500_000, at(12, 10))
    for k, amt in enumerate((100_000, 100_000, 80_000, 70_000, 150_000)):
        s.tx("M", f"R{k}", amt, at(12, 10, 2 + k))
        s.tx(f"R{k}", f"C{k}", amt - 500, at(12, 10, 9 + k))
    an = s.run()
    assert an.results["M"].flagged
    tr = trace(an.ds, an.fg, [t.idx for t in an.ds.txns if t.sender == "V"], "fwd", 8)
    assert tr.accounted() == tr.total_start() == Fraction(50_000_000)


def test_a13_round_trip_with_decay():
    s = Scenario("a13").background()
    s.tx("A", "B", 200_000, at(12, 10))
    s.tx("B", "C", 180_000, at(12, 11))
    s.tx("C", "D", 150_000, at(12, 12, 30))
    s.tx("D", "A", 124_000, at(12, 15))
    an = s.run()
    sig = an.results["A"].signals["ROUND_TRIP"]
    assert sig.final_tier == 0 and abs(sig.metrics["ratio"] - 0.62) < 0.001
    for a in "ABCD":
        assert an.results[a].flagged


def test_a14_attribute_laundering_via_kyc():
    s = Scenario("a14").background()
    for i in range(3):
        s.account(f"LA{i}", created=new(12), device=f"D{i}", ip=f"9.9.9.{i}", kyc="PAN-XYZ")
        s.tx(f"LA{i}", "SHOP3", 100, at(12, 10, i))
    an = s.run()
    for i in range(3):
        assert an.results[f"LA{i}"].signals["IDENTITY"].metrics["link_types"] == ["kyc"]
        assert an.results[f"LA{i}"].flagged


def test_a15_missing_optional_data_keeps_flow_detection():
    s = Scenario("a15")
    s.chain(["V", "M1", "M2", "M3", "X"], 300_000, at(1, 10), 5)
    data = "txn_id,timestamp,sender_account,receiver_account,amount\n" + "\n".join(
        f"{r['txn_id']},{r['timestamp']},{r['sender_account']},{r['receiver_account']},{r['amount']}"
        for r in s.rows)
    from muletrace.config import DEFAULT
    from muletrace.ingest import parse_csv
    from muletrace.pipeline import analyze
    res = parse_csv(data.encode(), DEFAULT)
    assert res.report["coverage"]["device"] is False
    an = analyze(res.txns, DEFAULT)
    assert an.results["M2"].severity == "HIGH"


# ---------------------------------------------------------------- G: audit regressions

def test_g1_large_new_ip_ring_not_suppressed():
    for n in (16, 25):
        s = Scenario(f"g1{n}").background()
        for i in range(n):
            s.account(f"IPR{i}", created=new(12), ip="203.0.113.5")
            s.tx(f"IPR{i}", "SHOP4", 100, at(12, 10, i))
        an = s.run()
        for i in range(n):
            r = an.results[f"IPR{i}"]
            assert r.flagged and r.severity == "LOW"
            assert r.signals["IDENTITY"].metrics["ip_only"]


def test_g1b_ip_without_establishment_evidence_stays_weak_and_collapses():
    s = Scenario("g1b")
    for i in range(20):
        s.account(f"U{i}", ip="198.51.100.7")
        s.tx(f"U{i}", "SHOP5", 100, at(0, 10, i))
    an = s.run()
    assert not an.ds.establishment_evidence
    sig = an.results["U0"].signals["IDENTITY"]
    assert sig.metrics["ip_only"] and sig.metrics["collapsed"]
    assert an.results["U0"].severity == "LOW"


def test_g2_pure_flow_syndicate_reaches_high():
    s = Scenario("g2").background()
    for i, a in enumerate(["P1", "P2", "P3", "P4", "P5", "P6"]):
        s.account(a, created=new(12), device=f"PD{i}", ip=f"5.5.5.{i}")
    s.chain(["V", "P1", "P2", "P3", "P4", "P5", "P6", "X"], 500_000, at(12, 10), 1.4, keep=0.002)
    an = s.run()
    for a in ("P1", "P2", "P3", "P4", "P5", "P6"):
        assert an.results[a].severity == "HIGH", a
        assert an.results[a].families == ["FLOW"]


def test_g3_hub_partitioned_lots():
    s = Scenario("g3").background()
    for k, (src, dst) in enumerate((("A", "X"), ("B", "Y"), ("C", "Z"))):
        s.tx(src, "M", 100_000, at(12, 10, k * 5))
        s.tx("M", dst, 100_000, at(12, 10, k * 5 + 2))
    an = s.run()
    assert "HUB" in kinds(an, "M")


def test_g5_day_one_user_not_flagged():
    s = Scenario("g5").background()
    s.account("NEWBIE", created=new(14))
    s.tx("NEWJOB", "NEWBIE", 50_000, at(14, 10))
    s.tx("NEWBIE", "LANDLORD2", 30_000, at(14, 10, 30))
    s.tx("NEWBIE", "CARDCO", 18_000, at(14, 10, 50))
    an = s.run()
    assert not an.results["NEWBIE"].flagged
    assert any(o["kind"] == "ISOLATED_RELAY" for o in an.observations("NEWBIE"))


def test_g6_refund_through_pooled_aggregator_is_not_a_cycle():
    s = Scenario("g6").background()
    for d in range(12):
        for k in range(6):
            s.tx(f"SHOPPER{d}{k}", "AGG", 1_200, at(d, 12, k))
        s.tx("AGG", "MER", 7_000, at(d, 23))
    s.tx("U", "AGG", 15_000, at(13, 10))
    s.tx("AGG", "MER", 15_000, at(13, 10, 20))
    s.tx("MER", "AGG", 15_000, at(14, 9))
    s.tx("AGG", "U", 15_000, at(14, 9, 30))
    an = s.run()
    assert an.ds.accounts["AGG"].pooled
    for a in ("U", "AGG", "MER"):
        assert "ROUND_TRIP" not in an.results[a].signals
        assert not an.results[a].flagged


def test_g8_fragmented_inflows_in_chain():
    s = Scenario("g8").background()
    for i in range(20):
        s.tx(f"SRCF{i}", "FR", 5_000, at(12, 10, i))
    s.tx("FR", "NEXT1", 99_000, at(12, 10, 22))
    s.tx("NEXT1", "NEXT2", 98_500, at(12, 10, 26))
    s.tx("NEXT2", "OUT", 98_000, at(12, 10, 30))
    an = s.run()
    assert an.results["FR"].signals["RELAY"].final_tier == 0
    assert an.results["FR"].flagged


def test_g11_pre_established_ring_gets_no_mitigation():
    s = Scenario("g11").background()
    s.tx("G1", "G2", 2_000, at(1, 10)).tx("G2", "G3", 2_000, at(1, 11))
    s.tx("G3", "OUTX", 1_500, at(1, 12))
    s.chain(["V", "G1", "G2", "G3", "OUTX"], 300_000, at(15, 10), 40, keep=0.005)
    an = s.run()
    for g in ("G1", "G2", "G3"):
        r = an.results[g]
        assert r.flagged, g
        for eid in an.fg.episodes_by_account[g]:
            assert not an.fg.episodes[eid].mitigations


def test_known_limitation_prior_victim_relationship_reads_first_mule_as_origin():
    """Documented limitation (ARCHITECTURE §12). A victim -> mule relationship older than 7 days makes the
    first mule satisfy the frozen ORIGIN rule (§7.2), exactly like the protected salary-funded victim (G4).
    The rest of the network must still be detected; this test pins that floor."""
    s = Scenario("lim").background()
    s.tx("V", "G1", 1_000, at(1, 10))                              # small payment 14 days earlier
    s.chain(["V", "G1", "G2", "G3", "OUT"], 300_000, at(15, 10), 5)
    an = s.run()
    assert an.cases.roles["G1"] == "ORIGIN" and not an.results["G1"].flagged     # current behaviour
    for a in ("G2", "G3"):
        assert an.results[a].flagged and "RELAY" in kinds(an, a)
    assert "LAYERED_RECEIPT" in kinds(an, "OUT")
    assert an.cases.case_of["G2"] == an.cases.case_of["G1"]


def test_g13a_established_account_mule_is_high():
    s = Scenario("g13a").background()
    s.account("EMULE", created=BASE - timedelta(days=730))
    for d in (0, 10, 20):
        s.tx("EMULE-JOB", "EMULE", 60_000, at(d, 9))
        s.tx("EMULE", "EMULE-RENT", 20_000, at(d, 12))
    s.chain(["V", "M0", "EMULE", "M2", "M3", "X"], 300_000, at(22, 10), 5)
    an = s.run()
    r = an.results["EMULE"]
    assert r.severity == "HIGH"
    assert an.cases.roles["EMULE"] != "ORIGIN"
    assert all(not an.fg.episodes[e].mitigations for e in r.signals["RELAY"].episodes
               if an.fg.episodes[e].start >= at(22).timestamp() - 86400)


def test_g13b_pooled_small_business_mule_still_detected():
    s = Scenario("g13b").background()
    s.account("BIZ", created=OLD)
    for d in range(14):
        for k in range(5):
            s.tx(f"CUST{d}{k}", "BIZ", 800, at(d, 11, k))
    s.chain(["V", "MP", "BIZ", "MN", "OUTB"], 300_000, at(20, 10), 3)
    an = s.run()
    assert an.ds.accounts["BIZ"].pooled
    assert "RELAY" in kinds(an, "BIZ")
    assert an.results["BIZ"].flagged


def test_g13c_identity_restored_inside_flow_case():
    s = Scenario("g13c").background()
    for i in range(6):
        s.account(f"CAFEU{i}", created=OLD, device="CAFE-PC")
        s.tx(f"CAFEU{i}", "SHOP6", 100, at(12, 9, i))
    s.account("EM", created=OLD, device="CAFE-PC")
    s.account("NM1", created=new(14), device="CAFE-PC").account("NM2", created=new(14), device="CAFE-PC")
    s.chain(["V", "NM1", "EM", "NM2", "OUTC"], 300_000, at(14, 10), 5)
    an = s.run()
    sig = an.results["EM"].signals["IDENTITY"]
    assert sig.qualifies and sig.metrics["restored"]
    for i in range(6):
        assert not an.results[f"CAFEU{i}"].flagged


def test_score_invariants_everywhere():
    s = Scenario("inv").background()
    s.chain(["V", "M1", "M2", "M3", "X"], 400_000, at(12, 10), 5)
    an = s.run()
    for r in an.results.values():
        assert r.score == sum(c.points for c in r.components)
        assert 0 <= r.score <= 100
        assert r.flagged == (r.score > 0)
        for c in r.components:
            assert c.detail
