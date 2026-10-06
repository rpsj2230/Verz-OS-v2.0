"""The install check for the Credentials screen, passing on PostgreSQL at head over a vault that
answers, saying it cannot run over none, and failing with the product broken the way it would
plausibly break.

The database half runs the module as the worker would, against a database at head: over no vault
the check says the screen offers no write, which is true of that install, and over a vault that
holds every slot it passes and leaves nothing. Then it is shown failing: the screen answering a
department's administrator, and a write that leaves no record for the slot's history.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.11.10, M27.15.50
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_operations_console_5"
CREDENTIALS = "every_slot_is_listed_and_written_from_the_screen_never_read_back"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_for_the_two_leaves() -> None:
    """One check closing both leaves of the screen. Delete this and the check can lose a leaf with
    the page showing the same row, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (CREDENTIALS, ("M27.11.10", "M27.15.50"))
    ]
    assert checks_in(MODULE) == [CREDENTIALS]


def test_the_authority_the_check_holds_is_the_routes_own() -> None:
    """The authority the check's administrator holds, held against the route that asks for it.
    Delete this and a renamed authority fails the check on every install with nothing wrong."""
    from brain.credential_routes import CREDENTIAL_AUTHORITY
    from brain.ops.acceptance_operations_console_5 import MANAGES_CREDENTIALS

    assert CREDENTIAL_AUTHORITY.value == MANAGES_CREDENTIALS


def test_a_key_the_checks_store_keeps_never_reaches_this_process() -> None:
    """A provider key put to use through the check's store goes into the store's own dictionary
    and not into this process's environment. Delete this and a check run in the worker could
    replace the provider key every later question is asked with."""
    from types import SimpleNamespace

    from brain.ops.acceptance_operations_console_5 import KeptHere, store_of_the_checks_own

    harness: Any = SimpleNamespace(sessions=None)
    store = store_of_the_checks_own(harness, KeptHere())
    [slot, *_] = store.slots()
    variable = slot.provider.env_var
    before = os.environ.get(variable)
    store.put_to_use(slot, "a-key-nobody-uses-0123456789abcdef")
    assert os.environ.get(variable) == before


def test_the_checks_vault_keeps_paths_and_says_every_slot_holds_a_version() -> None:
    """The in-memory vault remembers which slots were written and never what, and says every slot
    holds a version, which is what lets a replace-only slot be replaced. Delete this and a vault
    keeping the values, or one saying a slot is empty, changes what the check can prove."""
    from brain.ops.acceptance_operations_console_5 import KeptHere

    kept = KeptHere()
    assert kept.write_static_kv("providers/x", {"key": "secret-value"}) is not None
    assert kept.written == ["providers/x"]
    assert kept.static_kv_version("anything") is not None
    assert "secret-value" not in repr(vars(kept))


def test_a_body_names_one_value_or_every_field() -> None:
    """A slot of one field is sent `value` and a slot of several is sent each field under
    `values`, as the route's `values_of` asks. Delete this and the check sends every slot a shape
    the route refuses, which fails on every install for a reason in the check."""
    from brain.ops.acceptance_operations_console_5 import a_value

    assert set(a_value(("key",))) == {"value"}
    assert set(a_value(("access_key_id", "secret_access_key"))["values"]) == {
        "access_key_id",
        "secret_access_key",
    }


def test_the_reason_the_check_cannot_run_fits_the_results_column() -> None:
    """The sentence recorded when the screen offers no write fits the column it is kept in.
    Delete this and the result is refused for its length on exactly the installs that need it."""
    from brain.ops.acceptance_operations_console_5 import THE_SCREEN_OFFERS_NO_WRITE_HERE

    assert len(THE_SCREEN_OFFERS_NO_WRITE_HERE) <= REASON_CHARS


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_ops_console_5") as url:
        yield url


def run_ops(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    both["ops.credential_write"] = int(sql(url, "SELECT count(*) FROM ops.credential_write")[0][0])
    return both


def _with_a_vault_holding_every_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install's vault, answering, open, and holding a version of every declared slot."""
    from brain.install import value_of
    from brain.ops import acceptance_operations_console_5 as credentials_check
    from brain.ops.credential_catalogue import declared_slots
    from brain.ops.object_store import BACKEND_SETTING
    from tests.unit.test_credentials_screen import Slots

    held = [
        one.path
        for one in declared_slots(
            credentials_check.store_of_the_checks_own(
                credentials_check_harness(), credentials_check.KeptHere()
            ),
            backend=value_of(BACKEND_SETTING),
        )
    ]
    monkeypatch.setattr(credentials_check, "installs_vault", lambda h: Slots(held=held))


def credentials_check_harness() -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(sessions=None)


@pytest.mark.needs_db
def test_over_no_vault_the_check_says_the_screen_offers_no_write(install: str) -> None:
    """An install running no vault is shown every slot and offered no write, and the check says it
    cannot run there rather than passing. Delete this and the check passes on an install where
    nothing could be written."""
    from brain.ops.acceptance_operations_console_5 import THE_SCREEN_OFFERS_NO_WRITE_HERE

    assert run_ops(install) == {CREDENTIALS: (NOT_RUN, THE_SCREEN_OFFERS_NO_WRITE_HERE)}


@pytest.mark.needs_db
def test_over_a_vault_that_answers_the_check_passes_and_leaves_nothing(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The check as the worker runs it, over a vault holding every slot.** It passes, and no
    person, grant, ledger entry or credential write record is left. Delete this and a check that
    can only ever say it did not run is indistinguishable from one that works."""
    _with_a_vault_holding_every_slot(monkeypatch)
    before = _counts(install)
    assert run_ops(install) == {CREDENTIALS: (PASSED, "")}
    assert _counts(install) == before


def _failed(url: str) -> str:
    [(outcome, reason)] = run_ops(url).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_credentials_answering_a_departments_administrator_fail_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority read as held at any scope. Delete this and M27.11.10 closes on a screen
    where one department's administrator replaces the key every question is sent with."""
    from brain import credential_routes

    _with_a_vault_holding_every_slot(monkeypatch)
    monkeypatch.setattr(credential_routes, "may_manage", lambda reach, now: True)
    assert "without the authority" in _failed(install)


@pytest.mark.needs_db
def test_a_write_that_leaves_no_record_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write that is kept and never recorded. Delete this and M27.15.50 closes on a screen whose
    slot history says nobody wrote the key it holds."""
    from brain.ops.credential_write_store import StoredCredentialWrites

    async def nothing(self: Any, **kwargs: Any) -> None:
        del self, kwargs

    _with_a_vault_holding_every_slot(monkeypatch)
    monkeypatch.setattr(StoredCredentialWrites, "record", nothing)
    assert "history did not name" in _failed(install)
