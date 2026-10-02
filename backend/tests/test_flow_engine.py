"""Fund-Flow Engine gate: lots, links, episodes, exact arithmetic, invariants (ARCHITECTURE §5)."""
from collections import defaultdict
from fractions import Fraction

from builder import Scenario, at

from muletrace.config import DEFAULT
from muletrace.flow import trace


def _invariants(an):
    ds, fg = an.ds, an.fg
    txns = ds.txns
    by_lot = defaultdict(int)
    by_out = defaultdict(int)
    for link in fg.links:
        assert link.amount > 0
        assert link.dwell >= 0
        by_lot[link.in_txn] += link.amount
        by_out[link.out_txn] += link.amount
        assert txns[link.in_txn].receiver == link.account == txns[link.out_txn].sender
    for i, v in by_lot.items():
        assert v <= txns[i].amount
    for o, v in by_out.items():
        assert v + fg.own_funds[o] == txns[o].amount
    for acc in ds.accounts.values():
        if not acc.pooled:
            for o in acc.out_txns:
                assert by_out.get(o, 0) + fg.own_funds[o] == txns[o].amount


def test_fifo_basic_links_and_own_funds():
    s = Scenario("f1")
    s.tx("A", "M", 100_000, at(1, 10, 0))
    s.tx("B", "M", 50_000, at(1, 10, 5))
    s.tx("M", "X", 120_000, at(1, 10, 10))
    s.tx("M", "Y", 40_000, at(1, 10, 20))
    an = s.run()
    _invariants(an)
    txns = an.ds.txns
    links = [(txns[l.in_txn].sender, txns[l.out_txn].receiver, l.amount, l.dwell) for l in an.fg.links]
    assert links == [("A", "X", 10_000_000, 600), ("B", "X", 2_000_000, 300), ("B", "Y", 3_000_000, 900)]
    out_y = next(t.idx for t in txns if t.receiver == "Y")
    assert an.fg.own_funds[out_y] == 1_000_000      # 10k not covered by any lot


def test_same_timestamp_chain_links_form():
    """A->B and B->C at the identical second still link (inflow before outflow at B)."""
    s = Scenario("f2")
    s.tx("A", "B", 50_000, at(1, 9, 0), txn_id="Z9")
    s.tx("B", "C", 49_500, at(1, 9, 0), txn_id="A1")   # sorts before Z9 globally
    an = s.run()
    _invariants(an)
    assert len(an.fg.links) == 1
    assert an.fg.links[0].account == "B" and an.fg.links[0].dwell == 0


def test_lot_expiry_after_horizon():
    s = Scenario("f3")
    s.tx("A", "M", 50_000, at(1, 9))
    s.tx("M", "X", 50_000, at(4, 10))          # 73 h later: lot expired
    an = s.run()
    assert an.fg.links == []
    assert an.fg.expired["M"] == 5_000_000


def test_fragmented_inflows_form_one_episode():
    """G8: 20 micro inflows -> one macro outflow is one episode, evaluated on its total."""
    s = Scenario("f4")
    for i in range(20):
        s.tx(f"S{i:02d}", "M", 5_000, at(1, 10, i))
    s.tx("M", "X", 99_000, at(1, 10, 25))
    an = s.run()
    _invariants(an)
    eps = [an.fg.episodes[e] for e in an.fg.episodes_by_account["M"]]
    assert len(eps) == 1
    ep = eps[0]
    assert len(ep.in_txns) == 20 and ep.inflow == 10_000_000
    assert ep.tier == 0                         # 99% conserved, ~15 min dwell


def test_pooled_account_emits_no_links_and_stops_trace():
    s = Scenario("f5")
    for d in range(10):
        for k in range(6):
            s.tx(f"C{d}{k}", "POOL", 2_000, at(d, 10, k))
    s.tx("V", "POOL", 80_000, at(9, 12, 0))
    s.tx("POOL", "Z", 80_000, at(9, 12, 5))
    an = s.run()
    assert an.ds.accounts["POOL"].pooled
    assert not any(l.account == "POOL" for l in an.fg.links)
    v_txn = next(t.idx for t in an.ds.txns if t.sender == "V")
    tr = trace(an.ds, an.fg, [v_txn], "fwd", 8)
    assert tr.stopped["POOL"] == Fraction(8_000_000)
    assert tr.accounted() == tr.total_start()


def test_trace_exact_conservation_with_awkward_splits():
    """G9: proportional splits over many hops conserve value exactly."""
    s = Scenario("f6")
    s.tx("V", "A", 100_000, at(1, 10, 0))
    s.tx("W", "A", 33_333, at(1, 10, 1))
    s.tx("A", "B", 77_777, at(1, 10, 3))
    s.tx("A", "C", 55_556, at(1, 10, 4))
    s.tx("B", "D", 77_000, at(1, 10, 6))
    s.tx("C", "D", 30_001, at(1, 10, 7))
    s.tx("C", "E", 25_000, at(1, 10, 8))
    s.tx("D", "F", 99_999, at(1, 10, 9))
    s.tx("F", "G", 99_000, at(1, 10, 11))
    s.tx("G", "H", 98_000, at(1, 10, 12))
    an = s.run()
    _invariants(an)
    start = [t.idx for t in an.ds.txns if t.sender == "V"]
    tr = trace(an.ds, an.fg, start, "fwd", 8)
    assert tr.accounted() == tr.total_start() == Fraction(10_000_000)
    back = trace(an.ds, an.fg, [t.idx for t in an.ds.txns if t.receiver == "H"], "back", 8)
    assert back.accounted() == back.total_start()


def test_deterministic_and_order_independent():
    s = Scenario("f7").background(days=10, people=12)
    s.chain(["V", "M1", "M2", "M3", "X"], 400_000, at(8, 10), 4)
    a1 = s.run()
    a2 = s.run(shuffle_seed=3)
    sig = lambda an: [(l.account, an.ds.txns[l.in_txn].txn_id, an.ds.txns[l.out_txn].txn_id, l.amount)
                      for l in an.fg.links]
    assert sig(a1) == sig(a2)
    sc = lambda an: {a: (r.score, r.severity, [(c.rule, c.points) for c in r.components])
                     for a, r in an.results.items()}
    assert sc(a1) == sc(a2)


def test_reservoir_decoy_window_conservation():
    """A5: a recent reservoir absorbs FIFO, window conservation still sees the pass-through."""
    s = Scenario("f8")
    s.tx("R", "M", 60_000, at(1, 9, 0))
    s.tx("V", "M", 400_000, at(2, 9, 0))
    s.tx("M", "N", 400_000, at(2, 9, 6))
    an = s.run()
    _invariants(an)
    best = min(an.fg.episodes[e].tier for e in an.fg.episodes_by_account["M"] if an.fg.episodes[e].tier is not None)
    assert best == 0
