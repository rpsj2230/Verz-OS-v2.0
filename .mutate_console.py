"""Hand mutation of the console for the run again control and the interrupted list.

Each mutation breaks one line in this tree (nobody else reads this worktree), runs the named
vitest file, prints the FAILED test names, restores the file and checks the md5 is unchanged.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "console"
ENV = {**os.environ, "NODE_OPTIONS": "--no-experimental-webstorage", "PATH": "/opt/homebrew/bin:" + os.environ["PATH"]}

PAGE = "src/pages/operations/JobsPage.tsx"
QUERY = "src/pages/jobsQuery.ts"
RUNS = "src/pages/liveRunsQuery.ts"
RUNS_PAGE = "src/pages/operations/LiveRunsPage.tsx"
TEST = "tests/operations-pages.test.tsx"

MUTATIONS = [
    (
        "the Run again column needs the authority",
        QUERY,
        "return body.run_again_switched_on && body.may_run_again;",
        "return body.run_again_switched_on;",
        TEST,
    ),
    (
        "the Run again column needs the switch on",
        QUERY,
        "return body.run_again_switched_on && body.may_run_again;",
        "return body.may_run_again;",
        TEST,
    ),
    (
        "a row whose references are gone is not offered Run again",
        QUERY,
        "return row.actionable;",
        "return true;",
        TEST,
    ),
]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def run(test: str) -> str:
    done = subprocess.run(
        ["npx", "vitest", "run", test],
        cwd=ROOT,
        env=ENV,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    out = done.stdout + done.stderr
    return "\n".join(sorted(set(re.findall(r"^\s*(?:×|FAIL)\s+(.+)$", out, re.M)))) or ("PASSED" if done.returncode == 0 else "NO FAILED LINE (exit %d)" % done.returncode)


def main() -> None:
    baseline = run(TEST)
    print("baseline:", baseline)
    if baseline != "PASSED":
        sys.exit(1)
    for label, file, before, after, test in MUTATIONS:
        path = ROOT / file
        original = path.read_bytes()
        digest = md5(path)
        text = original.decode("utf-8")
        if text.count(before) != 1:
            print(f"SKIPPED {label}: the text to break appears {text.count(before)} times")
            continue
        try:
            path.write_bytes(text.replace(before, after).encode("utf-8"))
            caught = run(test)
        finally:
            path.write_bytes(original)
        restored = md5(path) == digest
        print(f"{'CAUGHT ' if caught != 'PASSED' else 'SURVIVED'} | {label} | restored={restored}")
        for line in caught.splitlines():
            print("    ", line.strip()[:200])


main()
