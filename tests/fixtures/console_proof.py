"""What a console proof module's test file shares: the run as the worker makes it, and the counts.

Each `acceptance_checks_console_*` module has its own test file, so a package adds a check and its
test without editing a list every package appends to. This holds the two things every one of them
does the same way: run one module's checks against a database at head, and read back what the
checks may have left.
"""

from __future__ import annotations

import asyncio

from brain.ops import acceptance_run
from brain.ops.acceptance import registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, counts


def run_module(url: str, module: str) -> dict[str, tuple[str, str]]:
    """Every check of one module run as the worker runs them, name to outcome and reason."""
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url, **INSTALL})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((module,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


__all__ = ["counts", "run_module"]
