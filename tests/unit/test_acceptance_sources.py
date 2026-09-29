"""The connected-sources acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a Xero
organisation and a Freshdesk helpdesk made up for the run are connected, read from recorded
answers and asked about through the answer route's own functions, and every table the check writes
holds afterwards what it held before. Then it is run against the product broken where it proves:
connected sources contributing no question shapes, a live read that is never made, and an index
answer dated by the question rather than by its row. Each fails with its own sentence.

The second check, a question over many records, is run the same way and ends not run with the
sentence saying the embeddings clause waits for an inference server, which is the outcome it is
meant to have on every install until one runs; broken where it proves, it fails instead.

Task ids: M11.6.5, M11.6.2, M11.4.9, M11.9.2, M11.8.3
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_sources"
NAME = "a_connected_source_answers_on_ask_from_its_index_and_its_source"
HEADERS = "a_question_over_many_records_is_answered_from_the_index_headers"

#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = ("proj.record", "ops.connector_connection", "ops.connector_sync")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_sources_check_is_registered_with_the_leaves_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        NAME: ("M11.6.5", "M11.6.2", "M11.4.9"),
        HEADERS: ("M11.8.3",),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in mine().values() for leaf in one.leaves} <= leaves


def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


@pytest.mark.needs_db
def test_on_a_real_database_a_connected_source_answers_and_nothing_is_left_behind() -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** The first passes, the
    second reaches its last line and says the embeddings clause was not run, and the projection,
    the connections, the attempts and the ledger hold what they held before. Delete this and the
    one path from a connected source to Ask can break with nothing on the owner's install saying
    so, the header check can pass on a clause nothing ran, or a check that commits a connection
    can reach his server."""
    from brain.ops.acceptance_checks_sources import EMBEDDINGS_WAIT_FOR_THE_INFERENCE_SERVER

    with at_head("brain_acceptance_sources") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {
        NAME: (PASSED, ""),
        HEADERS: (NOT_RUN, EMBEDDINGS_WAIT_FOR_THE_INFERENCE_SERVER),
    }
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("questions", "a source nobody connected contributed a question shape"),
        ("live", "an invoice's amount was not read live for a reader granted it"),
        ("age", "an answer from a row read days ago did not say it may be old"),
        ("body", "a ticket's body was not read from the helpdesk when it was asked"),
    ],
)
def test_the_sources_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Four breaks, one per property: every connector's questions offered whether it is connected
    or not, a live reader that never reads, an index answer dated by the question, and a ticket's
    live read that no longer takes its body. Each fails the check with its own sentence. Delete
    this and the check can pass with the property gone."""
    import brain.api_routes as api_routes
    import brain.knowledge.connector_rows as connector_rows
    import brain.knowledge.rows as rows
    import brain.ops.live_records as live_records

    if broken == "questions":
        every = connector_rows.connected_questions(connector_rows.CONNECTOR_ROW_ENTITIES)

        async def always(state: Any) -> Any:
            del state
            return every

        monkeypatch.setattr(api_routes, "connected_questions_of", always)
    elif broken == "live":

        async def never(self: Any, result: Any, **kwargs: Any) -> Any:
            del self, result, kwargs
            return None

        monkeypatch.setattr(live_records.SourceRecords, "refresh", never)
    elif broken == "age":
        monkeypatch.setattr(
            rows,
            "answered_as_of",
            lambda fetched, now: now.isoformat() if now is not None else "",
        )
    else:
        import brain.connectors.freshdesk as freshdesk

        monkeypatch.setattr(freshdesk, "TICKET_LIVE_MAPPING", freshdesk.TICKET_MAPPING)
    with at_head(f"brain_acceptance_sources_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_sources_check_steps_aside_where_the_install_has_a_source_connected() -> None:
    """`A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN`. Delete this and the check could move the
    owner's real connection aside, or fail on an install whose Xero is connected."""
    from brain.ops.acceptance_checks_sources import A_SOURCE_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_sources_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('xero', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, tuple(mine().values()))
    assert outcome == dict.fromkeys(mine(), (NOT_RUN, A_SOURCE_IS_CONNECTED_HERE_ALREADY))


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("listing", "which invoices hold a status was not answered with their numbers"),
        ("filter", "invoices a reader may not name were told apart from none"),
        ("live", "a question over many invoices called Xero"),
    ],
)
def test_the_header_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, one per property: a list that names nobody, a filter on a status the reader
    may not read that is compiled rather than refused into nothing, and a question over many
    records answered as a question about one, which reads its records from their source. Each
    fails the check with its own sentence rather than reaching the not-run line. Delete this and
    the header check can reach its last line with the property gone, and read on the page as
    nothing worse than waiting."""
    import brain.gate.answer as answer
    import brain.knowledge.rows as rows

    if broken == "listing":
        monkeypatch.setattr(answer, "many_from", lambda found, payload: "")
    elif broken == "filter":
        from brain.core.scope_sql import compile_where

        def compiled(tool: Any, request: Any, columns: Any) -> Any:
            del tool, columns
            return compile_where(request.filters, rows.ROW_LAYOUT, param_prefix=rows.FILTER_PREFIX)

        monkeypatch.setattr(rows, "_compile_filters", compiled)
    else:
        import dataclasses

        import brain.gate.fast_lane as fast_lane

        plain = fast_lane._read

        async def one_at_a_time(*args: Any, **kwargs: Any) -> Any:
            return dataclasses.replace(await plain(*args, **kwargs), many=None)

        monkeypatch.setattr(fast_lane, "_read", one_at_a_time)
    with at_head(f"brain_acceptance_headers_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[HEADERS],))
        after = written(url)
    assert outcome[HEADERS] == (FAILED, reason)
    assert after == before
