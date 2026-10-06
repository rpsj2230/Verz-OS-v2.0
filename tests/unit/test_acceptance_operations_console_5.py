"""The install checks for the operations screens that keep the install's own things, each passing
on PostgreSQL at head and each failing with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: every check
passes, or for Backup and recovery says it cannot run where no object store is connected, and
nothing is left. Then each is shown failing: Storage answering a department's administrator, an
export offered to anybody, the log exported for anybody, notifications managed by anybody,
subscribers listed to anybody, and the recovery screen answering a person without it.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.8.15, M27.8.16, M27.15.48, M27.8.11, M27.7.12, M27.7.26
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_operations_console_5"
STORAGE = "the_storage_screen_shows_every_bucket_and_what_it_keeps"
EXPORT = "an_export_is_taken_from_the_console_and_listed_as_the_takers"
LOG = "the_log_exports_what_its_reader_could_page_to"
NOTICES = "a_notice_is_switched_off_and_the_relay_saved_from_the_console"
SUBSCRIBERS = "a_subscriber_is_told_what_it_asked_for_until_switched_off"
RECOVERY = "the_recovery_screen_reads_this_installs_backups"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_leaf() -> None:
    """Six checks, each closing its own leaf. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (STORAGE, ("M27.8.15",)),
        (EXPORT, ("M27.8.16",)),
        (LOG, ("M27.15.48",)),
        (NOTICES, ("M27.8.11",)),
        (SUBSCRIBERS, ("M27.7.12",)),
        (RECOVERY, ("M27.7.26",)),
    ]


def test_the_operations_console_5_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [STORAGE, EXPORT, LOG, NOTICES, SUBSCRIBERS, RECOVERY]


def test_the_authorities_the_checks_hold_are_the_routes_own() -> None:
    """The authorities the checks' people hold, held against the routes that ask for them.
    Delete this and a renamed authority fails its check on every install with nothing wrong in
    the product, or a check passes holding an authority the route no longer asks for."""
    from brain.log_routes import LOG_AUTHORITY
    from brain.notification_routes import NOTIFICATION_AUTHORITY
    from brain.ops import acceptance_operations_console_5 as ops
    from brain.ops.data_transfer import EXPORT_AUTHORITY
    from brain.ops.outbox import MANAGE_SUBSCRIBERS
    from brain.storage_routes import STORAGE_AUTHORITY

    assert STORAGE_AUTHORITY.value == ops.MANAGES_STORAGE
    assert EXPORT_AUTHORITY.value == ops.TAKES_EXPORTS
    assert LOG_AUTHORITY.value == ops.READS_THE_LOG
    assert NOTIFICATION_AUTHORITY.value == ops.MANAGES_NOTIFICATIONS
    assert MANAGE_SUBSCRIBERS.value == ops.MANAGES_SUBSCRIBERS


def test_the_log_readers_grants_open_the_log_over_everything_and_not_over_one_department() -> None:
    """The grants the log check gives its two readers are the ones the log's own decision asks:
    the reader over everything may read the log and the department's reader may not. Delete this
    and the check's readers can stop matching the route, which on 2026-10-06 they did: the first
    version asked for a registered screen the log does not have and stopped on a KeyError."""
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.log_routes import may_read_application_log
    from brain.ops.acceptance_operations_console_5 import log_grants

    def holding(scope: Scope) -> EntitlementSet:
        return EntitlementSet(
            principal_id="u_reader",
            grants=tuple(
                Grant(capability=Capability(value=one), scope=where)
                for one, where in log_grants(scope)
            ),
        )

    now = datetime(2999, 1, 1, tzinfo=UTC)
    assert may_read_application_log(holding(Scope.unrestricted()), now)
    assert not may_read_application_log(holding(Scope.department("acceptance_a")), now)


def test_the_exported_kinds_are_kinds_the_audit_trail_governs() -> None:
    """The audit kinds the exporter is granted are kinds the ledger records and the view asks a
    capability for. Delete this and a renamed kind leaves the exporter able to read nothing, and
    the export check fails on every install for a reason that is not the screen's."""
    from brain.audit.ledger import SUBJECT_KINDS
    from brain.audit.view import CAPABILITY_BY_KIND
    from brain.ops.acceptance_operations_console_5 import EXPORTED_KINDS

    assert set(EXPORTED_KINDS) <= SUBJECT_KINDS
    assert all(one in CAPABILITY_BY_KIND for one in EXPORTED_KINDS)


def test_what_the_checks_send_is_what_the_forms_accept() -> None:
    """The relay, the webhook and the export reference the checks send pass the product's own
    judgement of them. Delete this and a tightened rule fails a check on every install with a
    problem in the check's figures rather than the screen."""
    from brain.ops import acceptance_operations_console_5 as ops
    from brain.ops.data_transfer import request_problems
    from brain.ops.mail import Security, settings_problems
    from brain.ops.outbox import EventKind
    from brain.ops.webhook_admin import registration_problems

    harness = cast("Any", SimpleNamespace(trace_id="acc-0123456789abcdef"))
    assert (
        registration_problems(
            subscriber_id=ops.subscriber_id_for(harness),
            endpoint=ops.WEBHOOK_ENDPOINT,
            kinds=[next(iter(EventKind)).value],
            secret=secrets.token_urlsafe(32),
        )
        == ()
    )
    assert (
        settings_problems(
            host=ops.RELAY_HOST,
            port=587,
            security=Security.STARTTLS.value,
            sender=ops.RELAY_SENDER,
            username="acceptance",
        )
        == ()
    )
    now = datetime(2999, 1, 1, tzinfo=UTC)
    assert (
        request_problems(
            data_set="audit_trail",
            reason="internal_investigation",
            reason_reference=ops.MATTER,
            since=now - timedelta(minutes=5),
            until=now,
        )
        == ()
    )


def test_a_subscriber_id_is_the_runs_own_and_the_shape_the_route_accepts() -> None:
    """Two runs register two subscribers, and each id is one the Webhooks route accepts. Delete
    this and a run sharing an id with an earlier one is refused as taken."""
    from brain.ops.acceptance_operations_console_5 import subscriber_id_for
    from brain.ops.webhook_admin import subscriber_id_problems

    one = subscriber_id_for(cast("Any", SimpleNamespace(trace_id="acc-one")))
    two = subscriber_id_for(cast("Any", SimpleNamespace(trace_id="acc-two")))
    assert one != two
    assert subscriber_id_problems(one) == () == subscriber_id_problems(two)


def test_the_stand_in_keeper_says_it_is_configured_and_keeps_nothing() -> None:
    """The keeper the subscribers check hands the route records the id and touches no vault.
    Delete this and a keeper that wrote to the vault would leave a secret behind on every
    install the check ran on."""
    from brain.ops.acceptance_operations_console_5 import KeptNowhere

    keeper = KeptNowhere()
    assert keeper.configured
    assert keeper.keep("acceptance_x", "s" * 48, actor="someone") is not None
    assert keeper.handed == ["acceptance_x"]
    assert keeper._vault is None


def test_the_reason_a_recovery_check_cannot_run_fits_the_results_column() -> None:
    """The sentence a run records when no store is connected fits the column it is kept in.
    Delete this and the result is refused for its length on exactly the installs that need it."""
    from brain.ops.acceptance_operations_console_5 import NO_BACKUP_BUCKET_IS_READ_HERE

    assert len(NO_BACKUP_BUCKET_IS_READ_HERE) <= REASON_CHARS


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
ALSO_WRITTEN = ("obs.application_log", "ops.data_export", "ops.webhook_subscriber", "ops.setting")


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


def _with_a_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    """The store the application would connect to, holding a copy and its rehearsal."""
    from brain.ops import object_store
    from tests.unit.test_object_store_wiring import _at_start, a_bucket

    monkeypatch.setattr(object_store, "object_store_at_start", _at_start(a_bucket()))


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** Five pass, the recovery check says it cannot run
    where no store is connected, and nothing a check wrote is left: no log row, export, setting,
    subscriber or person. Delete this and a check that can never pass on a real schema, or one
    that leaves a relay saved, reaches the owner's server first."""
    from brain.ops.acceptance_operations_console_5 import NO_BACKUP_BUCKET_IS_READ_HERE

    before = _counts(install)
    outcomes = run_ops(install)
    assert outcomes == {
        STORAGE: (PASSED, ""),
        EXPORT: (PASSED, ""),
        LOG: (PASSED, ""),
        NOTICES: (PASSED, ""),
        SUBSCRIBERS: (PASSED, ""),
        RECOVERY: (NOT_RUN, NO_BACKUP_BUCKET_IS_READ_HERE),
    }
    assert _counts(install) == before


@pytest.mark.needs_db
def test_the_recovery_check_passes_over_a_bucket_holding_a_copy_and_its_rehearsal(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sibling of the not-run case: a store holding a copy and a rehearsal record, read as
    the application reads it, passes. Delete this and a check that can only ever say it did not
    run is indistinguishable from one that works."""
    _with_a_bucket(monkeypatch)
    assert run_ops(install, RECOVERY, STORAGE) == {
        STORAGE: (PASSED, ""),
        RECOVERY: (PASSED, ""),
    }


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_ops(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_storage_answering_a_departments_administrator_fails_the_storage_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The storage authority read as held at any scope. Delete this and M27.8.15 closes on a
    screen that tells one department's administrator where the whole install keeps its files."""
    from brain import storage_routes

    monkeypatch.setattr(storage_routes, "may_read", lambda reach, now: True)
    assert "without the authority" in _failed(install, STORAGE)


@pytest.mark.needs_db
def test_an_export_offered_to_anybody_fails_the_export_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export authority not asked. Delete this and M27.8.16 closes on a screen that hands the
    audit trail to anybody who may read it."""
    from brain import data_transfer_routes

    monkeypatch.setattr(data_transfer_routes, "may_take_audit_export", lambda reach, now: True)
    assert "may not take one" in _failed(install, EXPORT)


@pytest.mark.needs_db
def test_a_log_exported_for_anybody_fails_the_log_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log's decision not asked. Delete this and M27.15.48 closes on an export that hands the
    whole install's log to a department's administrator."""
    from brain import log_routes

    monkeypatch.setattr(log_routes, "may_read_application_log", lambda reach, now: True)
    assert "without it over everything" in _failed(install, LOG)


@pytest.mark.needs_db
def test_notifications_managed_by_anybody_fail_the_notifications_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The notification authority not asked. Delete this and M27.8.11 closes on a screen where
    anybody switches off the company's notices."""
    from brain import notification_routes

    monkeypatch.setattr(notification_routes, "may_manage_notifications", lambda reach, now: True)
    assert "without the authority" in _failed(install, NOTICES)


@pytest.mark.needs_db
def test_subscribers_listed_to_anybody_fail_the_subscribers_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Who is told what shown whatever the reader holds. Delete this and M27.7.12 closes on a
    screen that tells anybody which outside addresses hear about the company.

    Both decisions are removed: the route's early answer and the console module's, which asks the
    same question again for every line. Removing only the first leaves the second hiding every
    line, which is that module doing its job, and the check rightly passes."""
    from brain import govern_people_routes
    from brain.console import subscribers

    monkeypatch.setattr(govern_people_routes, "may_manage", lambda reach, now=None: True)
    monkeypatch.setattr(subscribers, "may_manage", lambda reach, now=None: True)
    assert "may not manage them" in _failed(install, SUBSCRIBERS)


@pytest.mark.needs_db
def test_recovery_answering_anybody_fails_the_recovery_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen's permission not asked. Delete this and M27.7.26 closes on a screen that tells
    anybody whether the company can recover."""
    from brain import install_routes

    _with_a_bucket(monkeypatch)
    monkeypatch.setattr(install_routes, "_permitted", lambda reach, key, now: None)
    assert "without the screen" in _failed(install, RECOVERY)
