"""The install checks for connector safety, each passing on PostgreSQL at head and each failing with
the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: both checks pass
and leave nothing, the connection and the credential-write row included. Then each is shown failing:
a key repeated in a log line, an export that echoes the key it says it does not hold, a run that
keeps the key it first read, a changed declaration still read by a question, a changed declaration
the sources list does not mark, and a read that refuses even the declaration this release makes.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M11.8.9
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_connector_proof import (
    A_CHANGED_DECLARATION_IS_SHOWN_AND_NEVER_ANSWERED,
    A_KEY_IS_SEARCHED_FOR_WHEREVER_IT_COULD_BE_SHOWN,
    A_SOURCE_IS_CONNECTED_HERE_ALREADY,
    CHECK_ORDER,
    THE_LISTENER_HEARD_NOTHING,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_connector_proof"
KEY = "a_key_written_through_connectors_is_shown_back_nowhere"
DECLARED = "a_changed_declaration_is_shown_on_connector_health_not_read"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_clause_group() -> None:
    """Two checks, each naming the leaf. Delete this and a check can lose M11.8.9 with the page
    showing the same rows, so the leaf closes on the checks that remain and not on these."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (KEY, ("M11.8.9",)),
        (DECLARED, ("M11.8.9",)),
    ]


def test_the_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [KEY, DECLARED]


def test_the_module_sits_in_the_range_assigned_to_it() -> None:
    """Held against the range this package was given. Delete this and another package's module
    with the same key sorts beside it by name only, which moves rows on the Install page."""
    assert 740 <= CHECK_ORDER <= 759


def test_the_sentences_a_check_may_end_with_fit_the_result() -> None:
    """Stored whole. Delete this and why a check was not run is cut short on the Install page."""
    assert len(A_SOURCE_IS_CONNECTED_HERE_ALREADY) <= REASON_CHARS
    assert len(THE_LISTENER_HEARD_NOTHING) <= REASON_CHARS
    assert A_KEY_IS_SEARCHED_FOR_WHEREVER_IT_COULD_BE_SHOWN
    assert A_CHANGED_DECLARATION_IS_SHOWN_AND_NEVER_ANSWERED


def test_the_listener_hears_the_log_and_leaves_the_processors_as_it_found_them() -> None:
    """**The listener is a tap and not a takeover.** It hears a structlog event and a library log
    record written inside the block, and the processors are the same objects afterwards. Delete
    this and a listener that replaced the processors, silencing the worker's own log for the
    length of a check, or one that never heard anything, passes every test below."""
    import logging

    import structlog

    from brain.ops.acceptance_checks_connector_proof import _listening

    before = list(structlog.get_config()["processors"])
    with _listening() as heard:
        structlog.get_logger().info("the_check_s_own_event", marker="structlog-marker")
        logging.getLogger("acceptance.proof").warning("library-marker")
    assert any("structlog-marker" in one for one in heard)
    assert any("library-marker" in one for one in heard)
    assert structlog.get_config()["processors"] == before


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_connector_proof") as url:
        yield url


def run_proof(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


#: What these checks write beyond the suite's list.
ALSO_WRITTEN = (
    "ops.connector_connection",
    "ops.connector_sync",
    "ops.credential_write",
)


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_both_connector_proof_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass and nothing a check wrote is left: no
    connection, no credential write, no attempt. Delete this and a check that can never pass on a
    real schema, or one that leaves a connection of its own, reaches the owner's server."""
    before = _counts(install)
    outcomes = run_proof(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert _counts(install) == before


@pytest.mark.needs_db
def test_the_checks_are_not_run_where_the_install_has_xero_connected() -> None:
    """**An install that connected Xero is left alone.** Connecting a tenant beside the owner's is
    refused, and moving his aside would hold its lock. Delete this and either check goes red, or
    worse touches the connection, on the one install whose Xero is real."""
    from brain.ops.acceptance import NOT_RUN
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_connector_proof_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('xero', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcomes = run_proof(url)
    assert outcomes == dict.fromkeys((KEY, DECLARED), (NOT_RUN, A_SOURCE_IS_CONNECTED_HERE_ALREADY))


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_proof(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_key_repeated_in_a_log_line_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The keeper writing the value it was handed into a log event, which is how a key reaches a
    log: somebody adds a debugging line. Delete this and M11.8.9 closes on a check that never
    looks at the log."""
    import structlog

    from brain.ops.credentials import Credentials

    real = Credentials.keep

    async def talkative(self: Credentials, slot: Any, value: str, **kwargs: Any) -> Any:
        structlog.get_logger().info("credentials.kept", slot=slot.path, value=value)
        return await real(self, slot, value, **kwargs)

    monkeypatch.setattr(Credentials, "keep", talkative)
    assert "written to a log" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_listener_that_heard_nothing_fails_the_key_check_rather_than_passing_it(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A listener on the log that hears no event, as one attached to the wrong place would. Delete
    this and a search of an empty list passes for every key, which is a log search that cannot
    find anything and says the log is clean."""
    import contextlib

    from brain.ops import acceptance_checks_connector_proof as proof

    @contextlib.contextmanager
    def deaf() -> Iterator[list[str]]:
        yield []

    monkeypatch.setattr(proof, "_listening", deaf)
    assert _failed(install, KEY) == THE_LISTENER_HEARD_NOTHING


@pytest.mark.needs_db
def test_an_export_that_echoes_the_key_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export saying no key is exported and carrying the last one kept. Delete this and
    M11.8.9 closes on screens nobody searched for the key."""
    from brain import connector_routes
    from brain.ops.credentials import Credentials

    kept: list[str] = []
    real_keep = Credentials.keep
    real_export = connector_routes.export_connector

    async def noting(self: Credentials, slot: Any, value: str, **kwargs: Any) -> Any:
        kept.append(value)
        return await real_keep(self, slot, value, **kwargs)

    async def echoing(*args: Any, **kwargs: Any) -> Any:
        view = await real_export(*args, **kwargs)
        return view.model_copy(update={"credential": kept[-1]})

    monkeypatch.setattr(Credentials, "keep", noting)
    monkeypatch.setattr(connector_routes, "export_connector", echoing)
    assert "shown back in a response" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_run_that_reads_a_cached_key_fails_the_key_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read of the vault that serves what it served first, so a rotation needs a restart: the
    key a run sends is the old one. Delete this and M11.8.9 closes with rotation proved only by
    checks that never ask whether the route's replacement is what the next run sends."""
    from brain.ops.acceptance_checks_connector_framework import _Vault

    real = _Vault.read_static_kv
    served: dict[str, dict[str, Any]] = {}

    def cached(self: _Vault, path: str) -> dict[str, Any]:
        served.setdefault(path, real(self, path))
        return dict(served[path])

    monkeypatch.setattr(_Vault, "read_static_kv", cached)
    assert "did not send the key that replaced" in _failed(install, KEY)


@pytest.mark.needs_db
def test_a_live_read_that_answers_under_a_changed_declaration_fails_the_declaration_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A question's live read judging the connection against the declaration it builds now and not
    the one agreed to. Delete this and M11.8.9 closes with a silent redefinition answered."""
    from brain.connectors.manifest import manifest_digest
    from brain.ops.connectable import manifest_for
    from brain.ops.live_read_run import ConnectedSources

    real = ConnectedSources.read_one

    def unpinned(self: ConnectedSources, connection: Any, declared: Any, request: Any) -> Any:
        today = manifest_digest(manifest_for(connection.connector, connection.settings))
        return real(self, dataclasses.replace(connection, digest=today), declared, request)

    monkeypatch.setattr(ConnectedSources, "read_one", unpinned)
    assert "answered under a changed declaration" in _failed(install, DECLARED)


@pytest.mark.needs_db
def test_a_sources_list_that_does_not_mark_a_change_fails_the_declaration_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list drawing every source as unchanged. Delete this and M11.8.9 closes on a screen
    that shows a silent redefinition as a source in good order."""
    from brain import connector_routes
    from brain.console.connector_detail import source_rows as real

    def unmarked(**kwargs: Any) -> Any:
        return tuple(dataclasses.replace(one, declaration_changed=False) for one in real(**kwargs))

    monkeypatch.setattr(connector_routes, "source_rows", unmarked)
    assert "did not mark a changed declaration" in _failed(install, DECLARED)


@pytest.mark.needs_db
def test_a_read_that_refuses_this_releases_own_declaration_fails_the_declaration_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pin comparing against a digest no declaration has, so every live read is refused. The
    refusals above are satisfied by that. Delete this and the check passes a source nothing can
    read, which is the failure a guard tested only by its refusals always has."""
    from brain.ops import live_read_run

    monkeypatch.setattr(live_read_run, "manifest_digest", lambda manifest: "0" * 64)
    assert "was not read live" in _failed(install, DECLARED)
