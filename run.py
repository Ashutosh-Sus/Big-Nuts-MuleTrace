"""Start MuleTrace: API + analyst console on http://127.0.0.1:8000

    python run.py              # serve (uses the built frontend in frontend/dist)
    python run.py --engine window   # fallback window engine
    python run.py --port 8080
"""
import argparse
import sys
import webbrowser
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))


def main() -> None:
    parser = argparse.ArgumentParser(description="MuleTrace analyst console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--engine", choices=("flow", "window"), default="flow")
    parser.add_argument("--open", action="store_true", help="open the browser after start")
    args = parser.parse_args()

    import uvicorn

    from muletrace.api import DEMO_CSV, DIST, create_app
    from muletrace.config import DEFAULT

    if not DEMO_CSV.exists():
        from muletrace.demo_data import generate
        DEMO_CSV.parent.mkdir(exist_ok=True)
        DEMO_CSV.write_bytes(generate())
    if not (DIST / "index.html").exists():
        print("frontend/dist not found - build it once with:  cd frontend && npm install && npm run build")
    app = create_app(cfg=replace(DEFAULT, engine=args.engine))
    url = f"http://{args.host}:{args.port}"
    print(f"MuleTrace running at {url}  (engine: {args.engine})")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
