"""The vault tokens are renewed by the processes holding them, the worker's on the schedule.

Every test here uses a fake vault: the real client with its one network call replaced
(`tests.unit.test_openbao.FakeVault`) where the parsing of the vault's answer is the claim, and
an in-memory `SelfRenewing` where the decision is. Nothing talks to OpenBao, so what is proved is
what this code asks and decides, and not that a running vault answers `auth/token/lookup-self` in
this shape: `ops/openbao/REHEARSAL.md` is the run that would.

Task ids: M42.6.2
"""

from __future__ import annotations

import asyncio
import multiprocessing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from brain.deployment.vault_setup import TOKEN_PERIOD_SECONDS
from brain.ops.controls import control
from brain.ops.openbao import TokenStanding, VaultRefusedError
from brain.ops.schedule_runner import RUNNERS, start_control
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.vault_renewal import (
    CHECK_EVERY,
    RENEW_BELOW_SHARE_OF_PERIOD,
    Renewal,
    TokenCannotBeKeptError,
    keep_renewing,
    renew_if_owed,
    renewal_owed,
    renewer_at_start,
    run_renewal_now,
)
from brain.runtime import serves_alone
from tests.unit.test_openbao import FakeVault

HOUR = 3600
PERIOD = 768 * HOUR


@dataclass
class Held:
    """A vault client holding one token, in memory: its standing, and every renewal asked of it."""

    ttl: int
    period: int = PERIOD
    renewable: bool = True
    fail: Exception | None = None
    renewed: list[int] = field(default_factory=list)
    looked_up: int = 0

    def token_standing(self) -> TokenStanding:
        self.looked_up += 1
        if self.fail is not None:
            raise self.fail
        return TokenStanding(self.ttl, self.period, self.renewable)

    def renew_self(self) -> int:
        self.renewed.append(self.period)
        self.ttl = self.period
        return self.period


# ------------------------------------------------------------------------ the decision
def test_a_token_with_less_than_half_its_period_left_is_renewed_and_one_with_more_is_not() -> None:
    """The boundary, on both sides of it. Delete this and renewal can move to the last hour of the
    period, which is one missed check away from a token nobody can renew."""
    half = int(PERIOD * RENEW_BELOW_SHARE_OF_PERIOD)
    assert renewal_owed(TokenStanding(half - 1, PERIOD, renewable=True)) is True
    assert renewal_owed(TokenStanding(half, PERIOD, renewable=True)) is False
    assert renewal_owed(TokenStanding(PERIOD, PERIOD, renewable=True)) is False
    assert renewal_owed(TokenStanding(0, PERIOD, renewable=True)) is True


def test_half_the_period_leaves_a_fortnight_of_missed_checks_on_the_installers_period() -> None:
    """The figures against something outside themselves: the period the installer mints and the
    cadence the schedule runs at. Delete this and the share or the cadence can be changed so a
    worker down for a week lets its token lapse, with every test of the boundary still green."""
    assert TOKEN_PERIOD_SECONDS == PERIOD
    margin = timedelta(seconds=TOKEN_PERIOD_SECONDS * RENEW_BELOW_SHARE_OF_PERIOD)
    assert margin >= timedelta(days=14)
    assert margin > CHECK_EVERY * 4
    assert control("vault_token_renewal").every == CHECK_EVERY


def test_a_token_renewal_cannot_keep_is_refused_in_words_rather_than_reported_as_renewed() -> None:
    """Delete this and a token minted by hand without a period, or non-renewable, is reported as
    renewed on every run until the day the vault's maximum lifetime ends it."""
    with pytest.raises(TokenCannotBeKeptError, match="has no period"):
        renewal_owed(TokenStanding(10, 0, renewable=True))
    with pytest.raises(TokenCannotBeKeptError, match="not renewable"):
        renewal_owed(TokenStanding(10, PERIOD, renewable=False))
    assert issubclass(TokenCannotBeKeptError, SecretsUnavailableError)


def test_an_owed_token_is_renewed_once_and_one_not_owed_is_only_looked_up() -> None:
    """Delete this and a renewal can be skipped when owed, or asked of the vault on every check."""
    owed = Held(ttl=10 * HOUR)
    fresh = Held(ttl=700 * HOUR)

    done = renew_if_owed(owed)
    skipped = renew_if_owed(fresh)

    assert (done.outcome, done.left_seconds, owed.renewed) == (Renewal.RENEWED, PERIOD, [PERIOD])
    assert (skipped.outcome, skipped.left_seconds, fresh.renewed) == (
        Renewal.NOT_OWED,
        700 * HOUR,
        [],
    )
    assert done.summary() == "vault token renewed: 768h left of a 768h period"
    assert "700h left of a 768h period, renewed once fewer than 384h are left" in skipped.summary()


# ------------------------------------------------------------------------ the client
def test_the_client_reads_the_standing_from_lookup_self_and_renews_through_renew_self() -> None:
    """The producer written from the vault's raw answer, for CLAUDE.md's reason. Delete this and
    the client can read a field the vault does not send, or renew by a path that takes the token in
    the body, which is the renewal that needs somebody else's token."""
    vault = FakeVault(
        [
            {"data": {"ttl": 5 * HOUR, "period": PERIOD, "renewable": True, "id": "never-read"}},
            {"auth": {"lease_duration": PERIOD, "client_token": "never-read"}},
        ]
    )

    standing = vault.token_standing()
    granted = vault.renew_self()

    assert standing == TokenStanding(5 * HOUR, PERIOD, renewable=True)
    assert granted == PERIOD
    assert vault.calls == [("GET", "auth/token/lookup-self"), ("POST", "auth/token/renew-self")]
    assert "never-read" not in repr(standing)


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {"data": {"ttl": "5", "period": PERIOD, "renewable": True}},
        {"data": {"ttl": 5, "period": PERIOD, "renewable": "yes"}},
        {"data": {"ttl": True, "period": PERIOD, "renewable": True}},
        {"data": {"ttl": -1, "period": PERIOD, "renewable": True}},
    ],
    ids=["no data", "ttl as text", "renewable as text", "ttl as a boolean", "negative ttl"],
)
def test_a_standing_the_vault_did_not_state_readably_raises_rather_than_reading_as_empty(
    answer: dict[str, object],
) -> None:
    """Delete this and a malformed answer reads as a token with no time left, so it is renewed on
    a figure nobody stated, or as one with a whole period, so it is not."""
    with pytest.raises(SecretsUnavailableError):
        FakeVault(answer).token_standing()


def test_a_token_with_no_period_field_reads_as_period_zero_and_is_then_refused() -> None:
    """A token minted without `-period` answers with no period at all. Delete this and it reads as
    a malformed answer, which sends somebody to the network rather than to the mint command."""
    standing = FakeVault({"data": {"ttl": 10, "renewable": True}}).token_standing()
    assert standing.period_seconds == 0
    with pytest.raises(TokenCannotBeKeptError):
        renewal_owed(standing)


def test_a_renewal_answer_with_no_grant_raises() -> None:
    """Delete this and a renewal the vault did not confirm is reported with a figure it never
    gave."""
    with pytest.raises(SecretsUnavailableError, match="without saying how long"):
        FakeVault({"auth": {}}).renew_self()


# ------------------------------------------------------------------------ the worker's run
def test_the_worker_renews_its_own_token_through_a_client_built_from_its_own_settings() -> None:
    """Delete this and the scheduled run can build a client from somebody else's settings, or
    report a renewal it never asked for."""
    held = Held(ttl=HOUR)
    built: list[tuple[str, str]] = []

    def make(address: str, token: str) -> Held:
        built.append((address, token))
        return held

    said = run_renewal_now("http://vault:8200", "worker-token", make_vault=make)

    assert built == [("http://vault:8200", "worker-token")]
    assert held.renewed == [PERIOD]
    assert said == "vault token renewed: 768h left of a 768h period"


def test_a_worker_with_no_vault_has_nothing_to_renew_and_half_a_vault_fails_naming_the_half() -> (
    None
):
    """The positive and the refusal. Delete this and a lite-shaped worker with no vault fails every
    run, or a worker whose overlay lost its token succeeds while nothing renews anything."""
    asked: list[str] = []

    def never(address: str, token: str) -> Held:
        asked.append(address)
        return Held(ttl=0)

    assert "no token to renew" in run_renewal_now("", "", make_vault=never)
    with pytest.raises(SecretsUnavailableError, match="BRAIN_VAULT_TOKEN is not set"):
        run_renewal_now("http://vault:8200", "", make_vault=never)
    with pytest.raises(SecretsUnavailableError, match="BRAIN_VAULT_ADDRESS is not set"):
        run_renewal_now("", "worker-token", make_vault=never)
    assert asked == []


def test_a_silent_or_refusing_vault_fails_the_run_so_the_schedule_records_it() -> None:
    """Delete this and a renewal that could not reach the vault is swallowed and recorded as ok,
    which is a lapse nobody is told about until it has happened."""
    refusing = Held(ttl=HOUR, fail=VaultRefusedError("vault refused GET: HTTP 403", status=403))
    with pytest.raises(VaultRefusedError):
        run_renewal_now("http://vault:8200", "t", make_vault=lambda a, t: refusing)


def test_the_schedule_starts_the_renewal_by_name_and_renews_in_report_only_mode_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the real `start_control`, with the worker's settings from its environment. Report
    only exists for controls that remove data; a renewal declined there would be a token lapsing.
    Delete this and the arm can drop out of the dispatch, or honour report-only by not renewing."""
    held = Held(ttl=HOUR)
    monkeypatch.setenv("BRAIN_VAULT_ADDRESS", "http://vault:8200")
    monkeypatch.setenv("BRAIN_VAULT_TOKEN", "worker-token")
    monkeypatch.setattr("brain.ops.vault_renewal._worker_vault", lambda a, t: held)

    said = start_control(
        "vault_token_renewal",
        now=datetime(2999, 1, 1, tzinfo=UTC),
        report_only=True,
        database_url="postgresql://nobody@127.0.0.1:1/none",
    )

    assert held.renewed == [PERIOD]
    assert said.startswith("report only, renewed anyway: vault token renewed")
    assert any(one.name == "vault_token_renewal" and one.run is not None for one in RUNNERS)


def test_the_control_names_both_holders_so_neither_can_lose_its_caller_unnoticed() -> None:
    """Delete this and the application's half can be dropped from the registry, leaving a control
    that reads as running while the application's token is renewed by nothing."""
    assert control("vault_token_renewal").symbols == (
        "brain.ops.vault_renewal:run_renewal_now",
        "brain.ops.vault_renewal:keep_renewing",
    )


# ------------------------------------------------------------------------ the application's loop
def test_the_application_checks_at_start_then_on_the_cadence_and_survives_a_failed_check() -> None:
    """Delete this and one sealed hour ends the loop for the life of the process, or the first
    check waits a whole cadence after start."""
    held = Held(ttl=HOUR, fail=VaultRefusedError("sealed", status=503))
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        held.fail = None

    asyncio.run(keep_renewing(held, sleep=sleep, rounds=2))

    assert held.looked_up == 2
    assert held.renewed == [PERIOD]
    assert slept == [CHECK_EVERY.total_seconds(), CHECK_EVERY.total_seconds()]


def test_the_application_builds_a_renewer_only_from_both_settings_and_never_raises() -> None:
    """Delete this and a process with half a vault, or an address that is not a URL, refuses to
    start over a token, which is what `credentials_at_start` already refuses to do."""
    assert renewer_at_start("", "") is None
    assert renewer_at_start("http://vault:8200", "") is None
    assert renewer_at_start("vault:8200", "application-token") is None
    built = renewer_at_start("http://vault:8200", "application-token")
    assert built is not None
    assert "application-token" not in repr(built)


# ------------------------------------------------------------------------ serving alone
def _answer_from_a_child(sink: multiprocessing.Queue[bool]) -> None:
    sink.put(serves_alone())


def test_a_process_a_supervisor_started_knows_it_has_siblings_and_one_started_alone_does_not() -> (
    None
):
    """Measured with a real child, started the way uvicorn's supervisor starts its workers. Delete
    this and `serves_alone` can answer True in a worker with siblings, which lands a person on a
    console whose next question reaches a process holding no key."""
    context = multiprocessing.get_context("spawn")
    sink: multiprocessing.Queue[bool] = context.Queue()
    child = context.Process(target=_answer_from_a_child, args=(sink,))
    child.start()
    answered = sink.get(timeout=60)
    child.join(timeout=60)

    assert serves_alone() is True
    assert answered is False
    assert serves_alone(lambda: object()) is False
