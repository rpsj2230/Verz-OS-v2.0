"""Makes the files the work breakdown generates, once, before any test is collected.

`docs/wbs.json`, `docs/tracker.html` and `docs/wave-windows.json` are not committed
(`brain.ops.wbs_generate` says why), and a hundred tests read them. Generating here means every
way of running the suite, a shard in CI, a local file, the pre-push invariants and a mutation
worktree, reads output made from the sources it was given and not a copy left by an earlier
checkout. It costs 0.2 seconds.

**A failure ends the session with one sentence rather than letting a hundred tests each report a
missing file.** That is the loud half of the rule; the other half is `brain.status.load_wbs`
refusing an absent file outside pytest.

Task ids: none
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.ops.wbs_generate import GeneratedFilesError, generate

REPO = Path(__file__).resolve().parents[1]


def pytest_sessionstart(session: pytest.Session) -> None:
    try:
        generate(REPO)
    except GeneratedFilesError as error:
        pytest.exit(str(error), returncode=pytest.ExitCode.USAGE_ERROR)
