"""`python -m inference_server.ready`: the container's health check.

Asks the supervisor's own `/ready` route and exits 0 only on a 200. The answer is computed from what
is on disk and in the image (`inference_server.parts.readiness_gaps`) and never loads a part, so the
check costs nothing in memory and can run every twenty seconds for the life of the container. What
it prints when it fails is the list of gaps, which `docker inspect` shows as the health log.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

PORT = 8080


def main() -> int:
    """Exit 0 when every chosen part is ready, and print what is missing when one is not."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/ready", timeout=5) as response:
            return 0 if response.status == 200 else 1
    except urllib.error.HTTPError as error:
        try:
            gaps = json.loads(error.read()).get("gaps", [])
        except ValueError:
            gaps = []
        print("; ".join(str(one) for one in gaps) or f"not ready: {error.code}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError) as error:
        print(f"the supervisor does not answer: {error.__class__.__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
