"""The rules `/health/ready` reports its parts by, away from the lifespan that registers them.

`tests/unit/test_app_wiring.py` holds the assembled process: the four parts on a running
application, a wrong issuer, a vault that decides readiness. This file holds the pieces those rest
on, where a boundary can be tested without starting anything: how a part is named, how a reading
is shared, and what counts as a vault or an issuer answering.

Task ids: M31.1.1.5, M31.4.1
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import pytest

from brain.identity.roles import IdentityError
from brain.ops.openbao import TokenStanding, VaultRefusedError, VaultUnreachableError
from brain.readiness import (
    A_READING_IS_SHARED_SO_AN_ANONYMOUS_CALLER_CANNOT_AMPLIFY_IT,
    CACHE_PART,
    DATABASE_PART,
    DISCOVERY_PATH,
    HEADLINE_PARTS,
    PROBE_INTERVAL_SECONDS,
    PROBE_TIMEOUT_SECONDS,
    SIGN_IN_PART,
    VAULT_PART,
    PartState,
    ReadinessPart,
    Readings,
    issuer_answers,
    parts_of,
    vault_answers,
    vault_configured,
)

ISSUER = "https://id.example.invalid/realms/brain"


# ------------------------------------------------------------------ naming the parts


def test_the_headline_parts_are_the_four_the_task_names() -> None:
    """Held against the words rather than against the constants' own values, so repointing one
    constant cannot pass by moving both sides. Delete this and a part can be renamed out of the
    list the console draws with every other test here still green."""
    assert HEADLINE_PARTS == ("database", "cache", "vault", "sign_in")
    assert (DATABASE_PART, CACHE_PART, VAULT_PART, SIGN_IN_PART) == HEADLINE_PARTS


def test_a_checked_part_gates_a_reported_one_does_not_and_a_missing_headline_is_unconfigured() -> (
    None
):
    """The three ways a part is described, on one answer. Delete this and `parts_of` can report a
    reported part as gating, which tells the owner sign-in decides whether the site is up, or drop a
    headline part nobody configured, which says nothing about the vault at all."""
    parts = parts_of({DATABASE_PART: True, "row_security": False}, {SIGN_IN_PART: False})

    assert parts == [
        ReadinessPart(name=DATABASE_PART, state=PartState.READY, gates=True),
        ReadinessPart(name=CACHE_PART, state=PartState.NOT_CONFIGURED, gates=False),
        ReadinessPart(name=VAULT_PART, state=PartState.NOT_CONFIGURED, gates=False),
        ReadinessPart(name=SIGN_IN_PART, state=PartState.NOT_READY, gates=False),
        ReadinessPart(name="row_security", state=PartState.NOT_READY, gates=True),
    ]


# ------------------------------------------------------------------ one reading, shared


class Probe:
    def __init__(self, answer: bool = True, *, delay: float = 0.0) -> None:
        self.answer = answer
        self.delay = delay
        self.asked = 0

    async def __call__(self) -> bool:
        self.asked += 1
        await asyncio.sleep(self.delay)
        return self.answer


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_many_requests_inside_the_interval_ask_each_probe_once() -> None:
    """See `A_READING_IS_SHARED_SO_AN_ANONYMOUS_CALLER_CANNOT_AMPLIFY_IT`. Twenty concurrent
    readings and one question to the database, then a second question once the interval has
    passed, which is the positive half. Delete this and the lock or the interval can go, and an
    unauthenticated endpoint becomes a way to send the database a statement per request."""
    clock = Clock()
    readings = Readings(clock)
    probe = Probe(delay=0.01)
    readings.probes[DATABASE_PART] = probe
    into: dict[str, bool] = {}

    async def go() -> None:
        await asyncio.gather(*(readings.refresh(into) for _ in range(20)))
        clock.now += PROBE_INTERVAL_SECONDS
        await readings.refresh(into)

    asyncio.run(go())

    assert probe.asked == 2
    assert into == {DATABASE_PART: True}
    assert "PROBE_INTERVAL_SECONDS" in A_READING_IS_SHARED_SO_AN_ANONYMOUS_CALLER_CANNOT_AMPLIFY_IT


def test_a_probe_that_hangs_or_raises_is_not_ready_and_does_not_hold_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dependency that never answers is the commonest way one goes away. Delete this and a hung
    vault holds readiness past the health check's own timeout, which reads as the application
    being down rather than the vault."""
    monkeypatch.setattr("brain.readiness.PROBE_TIMEOUT_SECONDS", 0.05)
    readings = Readings(Clock())

    async def raises() -> bool:
        msg = "gone"
        raise ConnectionError(msg)

    readings.probes = {VAULT_PART: Probe(delay=5), CACHE_PART: raises, DATABASE_PART: Probe()}
    into: dict[str, bool] = {}
    asyncio.run(readings.refresh(into))

    assert into == {VAULT_PART: False, CACHE_PART: False, DATABASE_PART: True}
    assert PROBE_TIMEOUT_SECONDS < 5


# ------------------------------------------------------------------ the vault


class Vault:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def token_standing(self) -> TokenStanding:
        if self.error is not None:
            raise self.error
        return TokenStanding(ttl_seconds=60, period_seconds=0, renewable=True)


@pytest.mark.parametrize(
    ("vault", "ready"),
    [
        pytest.param(Vault(), True, id="answers"),
        pytest.param(Vault(VaultUnreachableError("down")), False, id="unreachable"),
        pytest.param(Vault(VaultRefusedError("sealed", status=503)), False, id="sealed"),
        pytest.param(Vault(VaultRefusedError("revoked", status=403)), False, id="revoked"),
    ],
)
def test_the_vault_is_ready_only_when_it_answers_this_processs_own_token(
    vault: Vault, ready: bool
) -> None:
    """Delete this and reachability can be judged by a socket opening, which a sealed vault and a
    revoked token both pass while every credential read fails."""
    assert vault_answers("https://vault.invalid", "t", make_vault=lambda _a, _t: vault) is ready


def test_a_vault_address_that_is_not_a_url_is_not_ready_rather_than_raising() -> None:
    """`OpenBaoVault` refuses a non-URL at construction. Delete this and that refusal escapes the
    probe, and the lifespan fails to start over a typo in a setting the wizard can correct."""
    assert vault_answers("vault.invalid", "t") is False


def test_half_a_vault_is_configured_and_neither_half_is_not() -> None:
    """A token with no address is a misconfiguration and must be reported, not treated as no vault.
    Delete this and it can read as not configured, which decides nothing and hides the mistake."""
    assert vault_configured("", "") is False
    assert vault_configured("https://vault.invalid", "") is True
    assert vault_configured("", "t") is True


# ------------------------------------------------------------------ the issuer


def serving(document: object) -> tuple[list[str], Callable[[str], bytes]]:
    asked: list[str] = []

    def get(url: str) -> bytes:
        asked.append(url)
        if isinstance(document, Exception):
            raise document
        return json.dumps(document).encode()

    return asked, get


def test_an_issuer_that_answers_as_itself_is_ready_and_is_asked_where_discovery_says() -> None:
    """The positive case, and the address. Delete this and every refusal below is satisfied by a
    function that answers False."""
    asked, get = serving({"issuer": ISSUER})

    assert issuer_answers(get, ISSUER) is True
    assert asked == [f"{ISSUER}/.well-known/openid-configuration"]
    assert DISCOVERY_PATH == "/.well-known/openid-configuration"


@pytest.mark.parametrize(
    "document",
    [
        pytest.param({"issuer": "https://id.example.invalid/realms/other"}, id="another_issuer"),
        pytest.param({"issuer": f"{ISSUER}/"}, id="trailing_slash"),
        pytest.param({}, id="names_none"),
        pytest.param(["not", "a", "document"], id="not_an_object"),
        pytest.param(IdentityError("answered 404"), id="not_found"),
    ],
)
def test_an_issuer_that_does_not_answer_as_itself_is_not_ready(document: object) -> None:
    """Every way the configured issuer can be wrong while something at that address answers.
    Delete this and a realm name typed wrongly, or a proxy answering for the wrong realm, reports
    sign-in ready while every token is refused as coming from the wrong issuer."""
    _, get = serving(document)

    assert issuer_answers(get, ISSUER) is False
