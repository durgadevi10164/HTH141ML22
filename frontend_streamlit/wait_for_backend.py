"""
wait_for_backend.py
-------------------
Polls a URL until it answers HTTP 200 (or a timeout expires). Standard library only.
Used by run.bat to (a) wait for the Flask API before starting Streamlit and
(b) open the browser once Streamlit is up.

    python frontend_streamlit/wait_for_backend.py --url http://127.0.0.1:5000/api/health --timeout 60
    python frontend_streamlit/wait_for_backend.py --url http://127.0.0.1:8501 --open http://localhost:8501

Exit code 0 = URL answered, 1 = timed out.
"""
import argparse
import sys
import time
import urllib.error
import urllib.request
import webbrowser


def is_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5000/api/health")
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds to keep trying")
    ap.add_argument("--open", dest="open_url", default=None, help="open this URL in the browser once --url is up")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    deadline = time.time() + args.timeout
    while True:
        if is_up(args.url):
            if not args.quiet:
                print(f"OK: {args.url} is responding.")
            if args.open_url:
                webbrowser.open(args.open_url)
            return 0
        if time.time() >= deadline:
            if not args.quiet:
                print(f"Timed out after {args.timeout:.0f}s waiting for {args.url}", file=sys.stderr)
            return 1
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
