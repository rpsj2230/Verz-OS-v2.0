"""The install checks for the routing matrix written from the console and for what each channel
says it carries, each passing on PostgreSQL at head and each failing with the product broken the
way it would plausibly break.

The database half runs the module as the worker would, against a database at head: both checks
pass and leave nothing. Then each is shown failing: a move written over the old row rather than as
a new one, an export carrying a key, a channel's verbs not its own, and a switched-off channel that
reads what it is sent.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.38, M27.15.43
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_operations_console_4 import KEY_FIELD_WORDS, field_names
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_operations_console_4"
ROUTING = "a_step_is_added_moved_and_retired_and_exported_without_keys"
CHANNELS = "each_channel_says_what_it_carries_and_off_refuses_inbound"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_leaf() -> None:
    """Two checks, each closing its own leaf. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (ROUTING, ("M27.15.38",)),
        (CHANNELS, ("M27.15.43",)),
    ]


def test_the_operations_console_4_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [ROUTING, CHANNELS]


def test_a_field_a_credential_would_be_in_is_found_at_any_depth() -> None:
    """The export's key test reads every field name, nested or listed. Delete this and a key held
    one level down in the export passes the check."""
    found = field_names({"steps": [{"provider": "a", "auth": {"api_key": "x"}}]})
    assert "api_key" in found
    assert any(word in name for name in found for word in KEY_FIELD_WORDS)
    assert not any(
        word in name
        for name in field_names({"steps": [{"provider": "a", "model": "b"}]})
        for word in KEY_FIELD_WORDS
    )


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_ops_console_4") as url:
        yield url


def run_ops(url: str, *names: str) -> dict[str, tuple[str, str]]:
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
ALSO_WRITTEN = ("ops.routing_change",)


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass and nothing a check wrote is left: no
    step, change record, ledger entry or channel record. Delete this and a check that can never
    pass on a real schema, or one that leaves a step on the ladder, reaches the owner's server."""
    before = _counts(install)
    outcomes = run_ops(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_ops(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_an_export_carrying_a_key_fails_the_routing_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The routing export with a key beside each step. Delete this and M27.15.38 closes on an
    export a supplier could authenticate with."""
    from brain import provider_routes

    real = provider_routes.routing_export

    def keyed(*args: Any, **kwargs: Any) -> Any:
        made = real(*args, **kwargs)

        class Keyed:
            def model_dump_json(self) -> str:
                import json

                document = json.loads(made.model_dump_json())
                document["providers"] = [{**one, "api_key": "x"} for one in document["providers"]]
                return json.dumps(document)

        return Keyed()

    monkeypatch.setattr(provider_routes, "routing_export", keyed)
    assert "credential" in _failed(install, ROUTING)


@pytest.mark.needs_db
def test_a_matrix_anybody_may_write_fails_the_routing_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The matrix authority read as held by everybody. Delete this and M27.15.38 closes on a
    ladder anybody can change."""
    from brain import routing_routes

    monkeypatch.setattr(routing_routes, "may_govern", lambda reach, now: True)
    assert "without the matrix authority" in _failed(install, ROUTING)


@pytest.mark.needs_db
def test_verbs_that_are_not_the_channel_s_own_fail_the_channel_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every channel said to carry every verb. Delete this and M27.15.43 closes on a page that
    tells an administrator a chat may approve what it may not."""
    from brain.gate import admission
    from brain.gate.context import Channel

    every = frozenset({"read", "write", "invoke", "approve", "admin"})
    assert admission.CHANNEL_VERBS[Channel.WEBHOOK] != every
    monkeypatch.setattr("brain.binding_routes.CHANNEL_VERBS", dict.fromkeys(Channel, every))
    assert "verbs" in _failed(install, CHANNELS)


@pytest.mark.needs_db
def test_a_switched_off_channel_that_reads_its_message_fails_the_channel_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The channel switch writing nothing. Delete this and M27.15.43 closes on a switch that
    leaves the channel answering."""
    from brain.ops.channel_store import StoredChannels

    async def nothing(self: Any, *args: Any, **kwargs: Any) -> Any:
        return await self.get(args[0])

    monkeypatch.setattr(StoredChannels, "switch", nothing)
    assert "still on" in _failed(install, CHANNELS)
