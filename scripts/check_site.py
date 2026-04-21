from __future__ import annotations

import argparse
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_PATHS = [
    "",
    "en/",
    "zh/",
]


def check_url(url: str, *, retries: int, delay: float) -> tuple[bool, str]:
    headers = {"User-Agent": "scibudy-site-health/0.1"}
    last_error = "unknown error"
    for attempt in range(1, retries + 1):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=20) as response:
                status = getattr(response, "status", 200)
                if 200 <= status < 400:
                    return True, f"{url} -> {status}"
                last_error = f"{url} -> unexpected status {status}"
        except HTTPError as exc:
            last_error = f"{url} -> HTTP {exc.code}"
        except URLError as exc:
            last_error = f"{url} -> {exc.reason}"
        if attempt < retries:
            time.sleep(delay)
    return False, last_error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://onemule.github.io/SciBudy/")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--delay", type=float, default=5.0)
    args = parser.parse_args()

    failures: list[str] = []
    for path in DEFAULT_PATHS:
        url = args.base_url.rstrip("/") + "/" + path
        ok, detail = check_url(url, retries=args.retries, delay=args.delay)
        print(detail)
        if not ok:
            failures.append(detail)

    if failures:
        print("site-health: failed", file=sys.stderr)
        raise SystemExit(1)
    print("site-health: ok")


if __name__ == "__main__":
    main()
