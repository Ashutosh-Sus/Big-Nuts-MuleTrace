"""Regenerate data/demo.csv (deterministic)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from muletrace.demo_data import generate  # noqa: E402

out = ROOT / "data" / "demo.csv"
out.parent.mkdir(exist_ok=True)
out.write_bytes(generate())
print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
