"""Iteration harness: build (once) a migrated scratch database and run named acceptance checks.

Usage (cwd = worktree, DATABASE_URL set):
    uv run python <this> build            # create + migrate brain_iter_<tag>
    uv run python <this> run MODULE [check ...]   # run the module's checks, print outcomes
"""

import asyncio
import os
import sys

sys.path.insert(0, os.getcwd())

TAG = os.environ.get("ITER_TAG", "people")
DB = f"brain_iter_{TAG}"


def build() -> None:
    from tests.fixtures.retirable import EXTENSIONS
    from tests.fixtures.scratch_postgres import fresh, migrate, sql

    scratch = fresh(DB)
    for extension in EXTENSIONS:
        sql(scratch, f'CREATE EXTENSION IF NOT EXISTS "{extension}"')
    migrate(DB, "stamp", "0001")
    migrate(DB, "upgrade", "head")
    print(scratch)


def run(module: str, names: list[str]) -> None:
    from brain.db import normalise_database_url
    from brain.ops import acceptance_run
    from brain.ops.acceptance import registered
    from brain.settings import settings_from
    from tests.fixtures.scratch_postgres import admin_url, pointed_at

    url = pointed_at(admin_url(), DB)
    extra = {}
    for pair in os.environ.get("ITER_ENV", "").split(";"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            extra[key] = value
    saved = {}
    for pair in os.environ.get("ITER_SAVED", "").split(";"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            saved[key] = value
    if saved:
        from brain.install import hold_saved

        hold_saved(saved)
    settings = settings_from({"BRAIN_DATABASE_URL": url, **extra})
    checks = [one for one in registered((module,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    for one in results:
        print(one.outcome, one.name, "|", one.reason)


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    else:
        run(sys.argv[2], sys.argv[3:])
