"""Run named checks of a module on DATABASE_URL (a database at head), printing full errors.

usage: python dbg_check.py <module> [check names...]   (never committed)
"""

import asyncio
import os
import sys

from brain.db import normalise_database_url
from brain.ops import acceptance_run
from brain.ops.acceptance import registered
from brain.settings import settings_from

module, names = sys.argv[1], sys.argv[2:]
acceptance_run.describe = lambda exc: repr(exc)[:1800]  # type: ignore[attr-defined]
from tests.fixtures.retirable import retirable

checks = [one for one in registered((module,)) if not names or one.name in names]
with retirable("dbg_" + os.environ.get("DBG_NAME", "x")) as url:
    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url), settings=settings, commit="dbg", checks=checks, force=True
        )
    )
for one in results:
    print(one.outcome, one.name, one.reason)
