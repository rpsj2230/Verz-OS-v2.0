"""The pre-commit gate: ruff's format and lint, over what is staged rather than what is on disk.

M0.1.3 asks for pre-commit hooks beside the ruff and mypy configuration, and `ops/hooks` held a
commit-msg hook and a pre-push hook. The pre-push hook runs ruff, so an unformatted file was
caught, but after the commit existed: the repair was an amend, and CLAUDE.md records that
`ruff format` is the gate a scripted edit most often trips. At commit time it is one retry.

**The staged blob is what is checked, not the working tree.** `git add` takes the file at the
moment it runs, and CLAUDE.md records a commit that was red while the tests beside it had passed
two minutes earlier, because the tree had moved on. A hook reading the working tree has the same
blind spot in both directions: it passes a fixed file that was never staged and fails a staged
file that is fine. So each staged Python path is read with `git show :path` and handed to ruff
on standard input with `--stdin-filename`, which keeps the path for configuration and
per-file ignores and reads nothing from disk.

**Only ruff, and deliberately not mypy or the tests.** A commit hook that takes a minute is a
hook people skip with `--no-verify`, and then it catches nothing. mypy and the invariants stay in
the pre-push hook, where a minute is paid once per push.

**The logic is here and the hook is a shim**, for the reason `ops/hooks/commit-msg` gives: a hook
does not run in CI and nothing tests it, so a rule written in one is a rule nobody has run.

Rejected: the `pre-commit` framework and a `.pre-commit-config.yaml`. It installs its own copy of
ruff into a cache at a version of its choosing, which is a second answer to which ruff judges
this repository beside `uv.lock`, and it downloads that copy on first use, which Windows
Application Control is the thing on this machine that refuses.

Task ids: M0.1.3
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

#: Where a staged Python file has to live for the gate to judge it: what CI lints.
CHECKED_ROOTS: Final[tuple[str, ...]] = ("src/", "tests/")

#: Why the blob and not the file.
THE_COMMIT_IS_THE_STAGED_BLOB: Final = (
    "git add takes the working tree at the moment it runs, so the file on disk and the file "
    "being committed can differ. The gate reads the staged blob and hands ruff that, so what "
    "it passes is what the commit contains."
)

#: One ruff invocation: its arguments after `python -m ruff`, the blob on standard input.
Ruff = Callable[[Sequence[str], bytes], tuple[int, str]]


def checked(paths: Sequence[str]) -> tuple[str, ...]:
    """The staged paths this gate judges: Python, under a root CI lints."""
    return tuple(path for path in paths if path.endswith(".py") and path.startswith(CHECKED_ROOTS))


def _git(repo: Path, *args: str) -> bytes:
    # Constant arguments and paths git itself listed; nothing here comes from input.
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def _ruff(repo: Path) -> Ruff:
    def run(args: Sequence[str], blob: bytes) -> tuple[int, str]:
        done = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "ruff", *args],
            cwd=repo,
            input=blob,
            capture_output=True,
            check=False,
        )
        return done.returncode, (done.stdout + done.stderr).decode("utf-8", "replace")

    return run


def findings(paths: Sequence[str], blob_of: Callable[[str], bytes], ruff: Ruff) -> list[str]:
    """Every staged file ruff refuses, with what ruff said, formatting first."""
    found: list[str] = []
    for path in checked(paths):
        blob = blob_of(path)
        code, said = ruff(("format", "--check", "--stdin-filename", path, "-"), blob)
        if code:
            found.append(f"{path}: not formatted as ruff format would write it")
        code, said = ruff(("check", "--stdin-filename", path, "-"), blob)
        if code:
            found.append(f"{path}: {said.strip()}")
    return found


def main(repo: Path | None = None) -> int:
    root = repo if repo is not None else Path.cwd()
    staged = (
        _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
        .decode("utf-8")
        .split("\0")
    )
    found = findings(
        [one for one in staged if one],
        lambda path: _git(root, "show", f":{path}"),
        _ruff(root),
    )
    for one in found:
        print(one, file=sys.stderr)
    if found:
        print(
            "pre-commit: the staged files above fail ruff. Run "
            "`uv run python -m brain.tasks fmt`, stage the result, and commit again.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
