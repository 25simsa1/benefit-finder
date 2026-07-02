"""Launch the benefit-finder web app. Wired to the `benefit-finder-web`
console script, so `benefit-finder-web` starts the server."""
from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="benefit-finder-web",
        description="Run the benefit-finder web app locally.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="bind port (default 8000)")
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes")
    args = parser.parse_args()

    try:
        import uvicorn
    except ModuleNotFoundError:
        print(
            "The web app needs the 'web' extra. Install it with:\n"
            "  pip install 'benefit-finder[web]'"
        )
        return 1

    print(f"benefit-finder web app on http://{args.host}:{args.port}")
    uvicorn.run(
        "benefit_finder.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
