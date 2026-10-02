"""Measure detection against a ground-truth label column, if the dataset has one.

    python scripts/evaluate.py path/to/data.csv

Detection never reads the label. An account counts as labelled positive when it sends or
receives at least one labelled transaction (label in 1/true/yes).
"""
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from muletrace.config import DEFAULT  # noqa: E402
from muletrace.ingest import parse_csv  # noqa: E402
from muletrace.pipeline import analyze  # noqa: E402

POSITIVE = {"1", "true", "yes", "y", "fraud", "laundering"}


def main(path: str) -> None:
    res = parse_csv(Path(path).read_bytes(), DEFAULT)
    if not res.report["coverage"].get("label"):
        sys.exit("No label column found (expected isFraud / is_laundering / label).")
    an = analyze(res.txns, DEFAULT, res.report["currency"])
    truth = set()
    for t in res.txns:
        if (t.label or "").strip().lower() in POSITIVE:
            truth.update((t.sender, t.receiver))
    flagged = {a for a, r in an.results.items() if r.flagged}
    tp, fp, fn = len(flagged & truth), len(flagged - truth), len(truth - flagged)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    print(f"accounts {len(an.results)}  labelled-positive {len(truth)}  flagged {len(flagged)}")
    print(f"precision {precision:.3f}  recall {recall:.3f}  (TP {tp}  FP {fp}  FN {fn})")
    per = defaultdict(lambda: [0, 0])
    for a in flagged:
        for k, s in an.results[a].signals.items():
            if s.qualifies:
                per[k][0 if a in truth else 1] += 1
    for k, (good, bad) in sorted(per.items()):
        print(f"  {k:<16} flagged {good + bad:>5}  labelled-positive {good:>5}  precision {good / (good + bad):.3f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
