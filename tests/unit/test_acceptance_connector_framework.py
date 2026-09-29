"""The connector framework's acceptance checks: registered, passing, and able to fail.

The pure half holds the eight checks to the suite and to the leaves they were scoped to, runs the
six that need no database against the install's own code, and then breaks the product one way per
rule and watches the check that proves the rule fail with its own sentence: an address check that
admits anything, an adapter that drops an argument it does not know instead of refusing it, a
scope that admits everything, a vault token nobody judges, a key kept from the first read, a
delegated read upgraded to the service key, an executor that waits past its timeout, a herd that is
not coalesced, a bucket that admits every call, a plan against an invented ceiling, a breaker that
counts quota refusals, and a retry with no jitter. A check that cannot fail proves nothing, and
each of these is that check shown able to.

The database half builds PostgreSQL to head and runs all eight as the worker would: they pass, and
every table they write to holds afterwards what it held before. Then the connecting check is run
against a worker that forgets which failure a 401 is, against a keeper that writes the key into a
settings row as well as the vault, and against an install with the source connected, which is not
run; and the notice check against a notice that names every source it failed.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1, M11.1.1, M11.1.3, M11.2.1, M11.2.2, M11.2.3, M11.2.5, M11.2.6, M11.3.1
Task ids: M11.3.2, M11.3.3, M11.3.5, M11.5.1, M11.5.4, M11.5.5
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_connector_framework as framework
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, reason_for, registered
from brain.ops.acceptance_run import Harness
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_connectors import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_connector_framework"

#: Each check and the leaves it proves, as the package was scoped.
LEAVES = {
    "a_source_is_read_by_its_declaration_and_its_key_is_in_no_table": ("M11.1.1", "M11.2.1"),
    "a_rest_read_is_built_from_a_spec_and_refused_before_a_call": ("M11.1.3",),
    "a_source_is_connected_to_one_named_thing_and_never_to_everything": ("M11.2.3",),
    "a_run_leases_its_key_and_the_next_run_reads_a_replaced_one": ("M11.2.2", "M11.2.6"),
    "a_live_read_uses_the_service_key_ends_on_time_and_is_made_once": (
        "M11.2.5",
        "M11.5.1",
        "M11.5.4",
    ),
    "a_burst_is_paced_by_the_source_s_documented_ceiling": ("M11.3.1", "M11.3.5"),
    "failures_open_the_breaker_and_a_refusal_is_retried_in_budget": ("M11.3.2", "M11.3.3"),
    "an_unreached_source_is_named_only_to_an_asker_who_could_see_it": ("M11.5.5",),
}

#: The checks that read and write no table, which the pure half runs with no database.
PURE = (
    "a_rest_read_is_built_from_a_spec_and_refused_before_a_call",
    "a_source_is_connected_to_one_named_thing_and_never_to_everything",
    "a_run_leases_its_key_and_the_next_run_reads_a_replaced_one",
    "a_live_read_uses_the_service_key_ends_on_time_and_is_made_once",
    "a_burst_is_paced_by_the_source_s_documented_ceiling",
    "failures_open_the_breaker_and_a_refusal_is_retried_in_budget",
)

#: Tables the framework checks write that `test_acceptance.WRITTEN_BY_CHECKS` does not list.
WRITTEN_BY_FRAMEWORK_CHECKS = ("ops.credential_write",)

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def without_a_database() -> Harness:
    # The pure checks read nothing: each is handed a harness with no connection on purpose.
    return Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]


def ran(name: str) -> tuple[str, str]:
    """One pure check's outcome and reason, as the run records them."""
    try:
        asyncio.run(mine()[name].run(without_a_database()))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


# ------------------------------------------------------------------------ without a server
def test_the_framework_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Each check names the leaves it was scoped to, in order, and each is a leaf of the work
    breakdown. Delete this and a check can close a leaf it does not exercise, or name an id no
    task has."""
    assert {name: one.leaves for name, one in mine().items()} == LEAVES
    assert list(mine()) == list(LEAVES)
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in LEAVES.values() for leaf in one} <= leaves


@pytest.mark.parametrize("name", PURE)
def test_a_check_needing_no_database_passes_against_the_install_s_own_code(name: str) -> None:
    """The positive run of each pure check: every refusal it expects is seen, and every read it
    expects is made. Delete this and a check can refuse its own accepted case, which reads on the
    Install page as the connector framework being broken."""
    assert ran(name) == (PASSED, "")


def test_every_source_the_console_connects_has_a_form_the_checks_fill() -> None:
    """`A_CHECK_FILLS_EACH_FORM_WITH_IDENTIFIERS_OF_ITS_OWN`: every connectable source has a form
    here and each form builds that source's manifest. Delete this and a source added to the console
    fails the first check on the owner's install before it fails here."""
    from brain.ops.connectable import CONNECTABLE, manifest_for

    assert set(CONNECTABLE) <= set(framework.FORMS)
    for name in CONNECTABLE:
        first, second = framework.FORMS[name](), framework.FORMS[name]()
        assert manifest_for(name, first).scope.selectors
        assert first != second, name


def test_the_inside_address_is_one_the_address_rule_refuses() -> None:
    """The address the checks answer with to be refused has to be one the product's own rule calls
    inside, or the refusal checks pass for a reason that is not the rule. Delete this and a public
    address can be written here, and the checks fail on every install."""
    from brain.tools.fetch import _is_reachable_only_from_inside

    assert _is_reachable_only_from_inside(framework.INSIDE_ADDRESS)
    assert framework._Inside().resolve("any.example.invalid") == [framework.INSIDE_ADDRESS]


# ------------------------------------------------------------ the product broken one way each
def test_the_rest_check_fails_when_the_address_rule_admits_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.1.3 broken at the address rule the spec loader and the adapter both ask. Delete this and
    a connector specification can point the worker inside the network with the check green."""
    import brain.connectors.rest as rest
    from brain.tools.fetch import Fetchable

    def admitting(url: str, resolver: Any) -> Fetchable:
        from urllib.parse import urlsplit

        host = urlsplit(url).hostname or ""
        return Fetchable(url=url, host=host, address=resolver.resolve(host)[0])

    monkeypatch.setattr(rest, "assert_fetchable", admitting)
    assert ran("a_rest_read_is_built_from_a_spec_and_refused_before_a_call") == (
        FAILED,
        "a specification whose server resolves inside the network loaded",
    )


def test_the_rest_check_fails_when_an_undeclared_argument_is_dropped_rather_than_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.1.3 broken in the adapter: an argument the specification does not define is quietly
    dropped. Delete this and a spec-driven adapter can guess at arguments with the check green."""
    from brain.connectors.rest import RestOperation

    original = RestOperation.url_for

    def forgiving(self: RestOperation, arguments: Any) -> str:
        known = {k: v for k, v in arguments.items() if self.operation.parameter(k) is not None}
        return original(self, known)

    monkeypatch.setattr(RestOperation, "url_for", forgiving)
    assert ran("a_rest_read_is_built_from_a_spec_and_refused_before_a_call") == (
        FAILED,
        "an argument the specification does not define was prepared",
    )


def test_the_scope_check_fails_when_a_selector_of_everything_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.2.3 broken at `ConnectorScope`: only a blank selector means everything. Delete this and
    a source can be connected to `all` with the check green."""
    import brain.connectors.contract as contract

    monkeypatch.setattr(contract, "UNBOUNDED_SELECTORS", frozenset({""}))
    assert ran("a_source_is_connected_to_one_named_thing_and_never_to_everything") == (
        FAILED,
        "the connect route did not refuse a scope of everything",
    )


def test_the_lease_check_fails_when_a_widened_run_token_is_not_judged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.2.2 broken: every token the vault mints is used, renewable or not. Delete this and a
    run can read its key with a token that outlives the run, with the check green."""
    import brain.ops.connector_sync_run as sync_run

    monkeypatch.setattr(sync_run, "judge_minted", lambda **kwargs: "")
    assert ran("a_run_leases_its_key_and_the_next_run_reads_a_replaced_one") == (
        FAILED,
        "a run token wider than the run role was not refused",
    )


def test_the_lease_check_fails_when_the_process_keeps_the_first_key_it_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.2.6 broken the way it breaks in practice: a process keeps the key it first read, so a
    key replaced in the vault is used only after a restart. Delete this and rotation can need a
    redeploy with the check green."""
    import brain.ops.connector_sync_run as sync_run

    real = sync_run._Held.key
    first: list[str] = []

    def kept(self: Any) -> str:
        value = real(self)
        if not first:
            first.append(value)
        return first[0]

    monkeypatch.setattr(sync_run._Held, "key", kept)
    assert ran("a_run_leases_its_key_and_the_next_run_reads_a_replaced_one") == (
        FAILED,
        "the next read did not send the key that replaced the last one",
    )


def test_the_live_read_check_fails_when_a_delegated_read_is_upgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.2.5 broken: a read asked under the asker's own credentials is made with the service key.
    Delete this and `A_DELEGATED_READ_IS_NEVER_SHARED_OR_UPGRADED` can go with the check green."""
    from brain.core.envelope import IdentityMode
    from brain.ops.live_read_run import ConnectedSources

    original = ConnectedSources.source_for

    def upgrading(self: ConnectedSources, connector: str, *, mode: Any, asker: str) -> Any:
        del mode
        return original(self, connector, mode=IdentityMode.SERVICE, asker=asker)

    monkeypatch.setattr(ConnectedSources, "source_for", upgrading)
    assert ran("a_live_read_uses_the_service_key_ends_on_time_and_is_made_once") == (
        FAILED,
        "a read under the asker's own credentials used the service key",
    )


def test_the_live_read_check_fails_when_a_silent_source_is_waited_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.5.1 broken: the executor gives each call three times the timeout and the question four
    times the budget. Delete this and a person can be kept waiting on a silent source with the
    check green. Takes the two and a half seconds it waits."""
    real = framework.read_live

    async def patient(calls: Any, **kwargs: Any) -> Any:
        slower = tuple(dataclasses.replace(one, timeout_ms=3 * one.timeout_ms) for one in calls)
        return await real(slower, **{**kwargs, "budget_ms": 4 * kwargs["budget_ms"]})

    monkeypatch.setattr(framework, "read_live", patient)
    assert ran("a_live_read_uses_the_service_key_ends_on_time_and_is_made_once") == (
        FAILED,
        "a read of a silent source did not end at its timeout in budget",
    )


def test_the_live_read_check_fails_when_twenty_askers_are_not_coalesced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.5.4 broken: every asker leads a fetch of their own. Delete this and twenty questions at
    nine in the morning become twenty calls against the tenant's day with the check green."""
    from brain.connectors.federation import FlightRole
    from brain.connectors.live_read import LiveFlights

    async def alone(self: LiveFlights, key: str, start: Any, *, wait_seconds: float) -> Any:
        del self, key
        return await asyncio.wait_for(start(), wait_seconds), FlightRole.LEADER

    monkeypatch.setattr(LiveFlights, "join", alone)
    assert ran("a_live_read_uses_the_service_key_ends_on_time_and_is_made_once") == (
        FAILED,
        "twenty askers of one record at once made other than one call",
    )


def test_the_ceiling_check_fails_when_the_bucket_admits_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.3.1 broken: the throttle asks the breaker and never the bucket. Delete this and a
    fan-out can spend a minute's allowance in a second with the check green."""
    from brain.connectors.live_read import Admission, LiveThrottle

    def breaker_only(self: LiveThrottle, connector: str, *, now: datetime) -> Admission:
        claimed, admitted = self.breaker(connector).try_admit(now)
        self.breakers[connector] = claimed
        return Admission() if admitted else Admission(refused=framework.FailureReason.CIRCUIT_OPEN)

    monkeypatch.setattr(LiveThrottle, "admit", breaker_only)
    assert ran("a_burst_is_paced_by_the_source_s_documented_ceiling") == (
        FAILED,
        "a burst of live reads was not the bucket's burst",
    )


def test_the_ceiling_check_fails_when_the_plan_reads_against_an_invented_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.3.5 broken: the windows a read is checked against are twice the documented row. Delete
    this and a ceiling can drift from its documentation with the check green."""
    import brain.connectors.throttle as throttle

    original = throttle.source_limits

    def doubled(connector: str, *, principal_id: str) -> Any:
        return tuple(
            dataclasses.replace(one, limit=2 * one.limit)
            for one in original(connector, principal_id=principal_id)
        )

    monkeypatch.setattr(throttle, "source_limits", doubled)
    assert ran("a_burst_is_paced_by_the_source_s_documented_ceiling") == (
        FAILED,
        "the worker's plan reads a source against another ceiling",
    )


def test_the_breaker_check_fails_when_quota_refusals_count_as_ill_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.3.2 broken the way `throttle.A_QUOTA_REFUSAL_IS_NOT_ILL_HEALTH` warns of: a 429 counts
    against the breaker. Delete this and the busiest source can be taken out of service for being
    asked, with the check green."""
    import brain.connectors.throttle as throttle

    ill = (throttle.CallOutcome.UNAVAILABLE, throttle.CallOutcome.QUOTA)
    monkeypatch.setattr(throttle, "is_breaker_failure", lambda outcome: outcome in ill)
    assert ran("failures_open_the_breaker_and_a_refusal_is_retried_in_budget") == (
        FAILED,
        "a run of refusals for volume opened the breaker",
    )


def test_the_breaker_check_fails_when_a_retry_has_no_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.3.3 broken: the executor retries after the stated wait and drops the jitter it was
    handed. Delete this and every asker refused in one second returns in the same second, with
    the check green."""
    import brain.connectors.live_read as live_read

    real = live_read.retry_delay

    def plain(
        *, retry_after_seconds: float | None, consecutive_refusals: int, jitter: float
    ) -> Any:
        del jitter
        return real(
            retry_after_seconds=retry_after_seconds, consecutive_refusals=consecutive_refusals
        )

    monkeypatch.setattr(live_read, "retry_delay", plain)
    assert ran("failures_open_the_breaker_and_a_refusal_is_retried_in_budget") == (
        FAILED,
        "a retry did not wait the stated time lengthened by jitter",
    )


# --------------------------------------------------------------------------- a real run
def framework_counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_BY_FRAMEWORK_CHECKS
    }


@pytest.mark.needs_db
def test_on_a_real_database_every_framework_check_passes_and_leaves_nothing_behind() -> None:
    """**The eight checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and the connections, the attempts, the credential record, the people, the grants and
    the ledger hold exactly what they held before. Delete this and a check that cannot pass on the
    real schema, or one that commits a connection or a credential record to a client's install,
    reaches the owner's server first."""
    with at_head("brain_acceptance_framework") as url:
        before = (counts(url), framework_counts(url))
        outcomes = run_checks(url, tuple(mine().values()))
        after = (counts(url), framework_counts(url))

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


def keeping_a_copy(original: Any) -> Any:
    """`Credentials.keep_fields`, and then the value written into a settings row as well.

    The copy is the defect M11.2.1 exists to find: a key kept in the vault and in configuration.
    Written as the login, inside the check's transaction, so it is rolled back with it.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    async def keep_fields(self: Any, slot: Any, values: Any, **kwargs: Any) -> Any:
        kept = await original(self, slot, values, **kwargs)
        bound = self._writes._sessions.kw["bind"]
        async with AsyncSession(bind=bound, join_transaction_mode="create_savepoint") as session:
            await session.execute(text("RESET ROLE"))
            await session.execute(
                text(
                    "INSERT INTO ops.setting (key, value_type, value, description, updated_by)"
                    " VALUES ('acceptance.key', 'string', to_jsonb(CAST(:value AS text)),"
                    " 'a copy', 'u_admin')"
                ).bindparams(value=next(iter(values.values())))
            )
            await session.commit()
        return kept

    return keep_fields


@pytest.mark.needs_db
def test_the_connecting_check_fails_on_a_forgotten_refusal_or_a_kept_copy_and_waits_if_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.1.1 broken: the worker records a 401 as the source not answering, so the screen does not
    say the key was declined. M11.2.1 broken: the keeper writes the key into a settings row as well
    as the vault. Each fails the check with its own sentence, and an install with the source
    connected is not run. Delete this and the health a screen shows, or the key's one home, can
    go with the check green, or the check can move the owner's live connection aside."""
    import brain.ops.connector_sync_run as sync_run
    from brain.ops.connector_sync import SOURCE_UNREACHABLE
    from brain.ops.credentials import Credentials
    from tests.fixtures.scratch_postgres import sql

    [connecting] = [one for one in mine().values() if one.leaves == ("M11.1.1", "M11.2.1")]
    with at_head("brain_acceptance_framework_connect") as url:
        before = (counts(url), framework_counts(url))
        with monkeypatch.context() as patched:
            patched.setattr(sync_run, "failure_detail", lambda *a, **k: SOURCE_UNREACHABLE)
            forgotten = run_checks(url, (connecting,))
        with monkeypatch.context() as patched:
            patched.setattr(Credentials, "keep_fields", keeping_a_copy(Credentials.keep_fields))
            copied = run_checks(url, (connecting,))
        after = (counts(url), framework_counts(url))
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('xero', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        connected = run_checks(url, (connecting,))

    assert forgotten[connecting.name] == (
        FAILED,
        "a key the source declined did not leave the source down",
    )
    assert copied[connecting.name] == (
        FAILED,
        "the key the check connected with was found in a table",
    )
    assert connected[connecting.name] == (NOT_RUN, framework.CONNECTED_ALREADY)
    assert after == before


@pytest.mark.needs_db
def test_the_notice_check_fails_when_the_notice_names_every_source_it_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.5.5 broken: the notice names every source that failed, whoever asked. Delete this and
    an answer can tell somebody entitled to nothing which systems the company connects, with the
    check green."""
    from brain.connectors.federation import PartialAnswer

    def naming(self: PartialAnswer, *, disclosable: frozenset[str]) -> str:
        del disclosable
        listed = ", ".join(sorted({one.connector for one in self.failed}))
        return f"I could not reach {listed}."

    [notice] = [one for one in mine().values() if one.leaves == ("M11.5.5",)]
    monkeypatch.setattr(PartialAnswer, "notice", naming)
    with at_head("brain_acceptance_framework_notice") as url:
        before = (counts(url), framework_counts(url))
        outcome = run_checks(url, (notice,))
        after = (counts(url), framework_counts(url))

    assert outcome[notice.name] == (
        FAILED,
        "an asker who could not see the source was told more than unavailable",
    )
    assert after == before
