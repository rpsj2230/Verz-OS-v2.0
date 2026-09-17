"""The pre-commit gate, run against a real repository with staged files.

Task ids: M0.1.3
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from brain.ops import precommit

REPO = Path(__file__).resolve().parents[2]

WELL_FORMED = b'"""A module."""\n\nVALUE = 1\n'
BADLY_FORMED = b'"""A module."""\nVALUE   =    1\n'


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "src").mkdir()
    return tmp_path


def _stage(repo: Path, path: str, content: bytes) -> None:
    (repo / path).write_bytes(content)
    _git(repo, "add", path)


def test_a_staged_file_ruff_would_reformat_refuses_the_commit(repo: Path) -> None:
    """The refusal, end to end through git and ruff: the reason the hook exists.

    Delete this and the gate can read nothing, or read the wrong thing, and exit 0."""
    _stage(repo, "src/bad.py", BADLY_FORMED)

    assert precommit.main(repo) == 1


def test_a_well_formed_staged_file_is_let_through(repo: Path) -> None:
    """The positive half. A gate that refuses everything passes the test above.

    Delete this and a hook refusing every commit ships, and gets skipped for ever after."""
    _stage(repo, "src/good.py", WELL_FORMED)

    assert precommit.main(repo) == 0


def test_the_staged_blob_is_judged_and_not_the_file_on_disk(repo: Path) -> None:
    """Both directions of `THE_COMMIT_IS_THE_STAGED_BLOB`: a well-formed blob with a broken
    file on disk is committed clean and passes, and a broken blob with a repaired file on disk
    is committed broken and refuses.

    Delete this and the gate can read the working tree, which passes the commit the pre-push
    hook then has to amend."""
    _stage(repo, "src/good.py", WELL_FORMED)
    (repo / "src" / "good.py").write_bytes(BADLY_FORMED)
    assert precommit.main(repo) == 0

    _stage(repo, "src/bad.py", BADLY_FORMED)
    (repo / "src" / "bad.py").write_bytes(WELL_FORMED)
    assert precommit.main(repo) == 1


def test_a_lint_finding_refuses_and_is_named() -> None:
    """Format is one of the two checks; the lint half is watched separately, over a fake ruff,
    so a gate that dropped the `check` call is seen.

    Delete this and the hook can stop linting with the format tests above still green."""

    def ruff(args: Sequence[str], blob: bytes) -> tuple[int, str]:
        del blob
        return (1, "F401 unused import") if args[0] == "check" else (0, "")

    found = precommit.findings(["src/a.py"], lambda path: b"", ruff)
    assert found == ["src/a.py: F401 unused import"]


def test_only_python_under_the_linted_roots_is_judged() -> None:
    """CI lints `src` and `tests`. Judging a migration here would refuse commits for findings
    no other gate reads; skipping `tests` would let through what CI then refuses."""
    assert precommit.checked(
        ["src/a.py", "tests/b.py", "migrations/versions/c.py", "docs/d.md", "src/e.js"]
    ) == ("src/a.py", "tests/b.py")


def test_the_hook_is_an_executable_shim_calling_the_module() -> None:
    """The hook is what git runs, and it is only this module if it calls it. Checked on the
    lines that are not comments, so a comment naming the module cannot satisfy it."""
    hook = REPO / "ops" / "hooks" / "pre-commit"
    live = [
        line.strip()
        for line in hook.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert "if ! uv run python -m brain.ops.precommit; then" in live
    staged = subprocess.run(
        ["git", "ls-files", "-s", "ops/hooks/pre-commit"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert staged.startswith("100755"), staged
