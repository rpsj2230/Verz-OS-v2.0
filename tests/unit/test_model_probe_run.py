"""The background prober: which deployments one tick probes, what a probe counts as, and the keys.

Driven with a ladder, a probe store, a sender and a key reader held in memory, so a tick is
inspected without a database, a vault or a provider. The runner's own arm in
`brain.ops.schedule_runner` is started by name at the end, on an install with no key.

Task ids: M5.4.7, M5.4.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from brain.models.adapter import TransportConnectionError, TransportStatusError
from brain.models.assembly import HOSTED_PROFILE, LOCAL_PROFILE, LadderRung
from brain.models.calls import LadderState
from brain.models.evidence import Attempt, RingEntry, StoredRings
from brain.models.health import PROBE_INTERVAL_SECONDS
from brain.models.routing import Tier
from brain.models.wire import KeyLookup
from brain.ops import model_probe_run
from brain.ops.model_probe_run import (
    A_PROBE_FAILS_ONLY_ON_THE_PROVIDERS_OWN_FAILURE,
    LOCAL_ONLY,
    NOTHING_HELD,
    PROBES_PER_TICK,
    DriverProbes,
    ProbeRun,
    WorkerProviderKeys,
    probe_on,
)
from brain.ops.provider_keys import PROVIDER_SLOTS, ProviderSlot
from brain.ops.secrets import SecretsUnavailableError

#: Far outside any plausible wall clock, because nothing here is about the present.
T0 = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)


def rung(provider: str, *, tier: Tier = Tier.MAIN, position: int = 0) -> LadderRung:
    return LadderRung(
        rung_id=f"{provider}-{tier.value}-{position}",
        tier=tier,
        position=position,
        deployment_id=f"{provider}-{tier.value}-{position}",
        provider=provider,
        model=f"{provider}-model",
        attempts=1,
        timeout_seconds=20.0,
        max_concurrency=2,
        enabled=True,
    )


@dataclass
class Ladder:
    rungs: tuple[LadderRung, ...]
    switched_off: frozenset[str] = frozenset()
    attempts: tuple[Attempt, ...] = ()
    rings: tuple[StoredRings, ...] = ()
    reads: int = 0

    async def current(self, now: datetime) -> LadderState:
        self.reads += 1
        return LadderState(
            rungs=self.rungs,
            switched_off=self.switched_off,
            attempts=self.attempts,
            rings=self.rings,
        )


@dataclass
class Store:
    """Claims granted unless named in `taken`; every outcome appended, in order."""

    taken: frozenset[str] = frozenset()
    claimed: list[str] = field(default_factory=list)
    observed: list[tuple[str, bool]] = field(default_factory=list)

    async def claim(self, deployment_id: str, provider: str, *, at: datetime) -> bool:
        if deployment_id in self.taken:
            return False
        self.claimed.append(deployment_id)
        return True

    async def observed_(self, deployment_id: str, ok: bool) -> None:
        self.observed.append((deployment_id, ok))


class StoreSink:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def claim(self, deployment_id: str, provider: str, *, at: datetime) -> bool:
        return await self.store.claim(deployment_id, provider, at=at)

    async def observed(self, deployment_id: str, *, ok: bool, at: datetime) -> None:
        await self.store.observed_(deployment_id, ok)


@dataclass
class Sender:
    failing: frozenset[str] = frozenset()
    sent: list[str] = field(default_factory=list)

    def send(self, rung: LadderRung) -> bool:
        self.sent.append(rung.deployment_id)
        return rung.deployment_id not in self.failing


def tick(
    ladder: Ladder,
    *,
    store: Store | None = None,
    sender: Sender | None = None,
    held: frozenset[str] = frozenset({"anthropic", "moonshot"}),
    profile: str = HOSTED_PROFILE,
    limit: int = PROBES_PER_TICK,
) -> tuple[ProbeRun, Store, Sender]:
    kept = store or Store()
    sending = sender or Sender()
    ran = asyncio.run(
        probe_on(
            ladder=ladder,
            store=StoreSink(kept),
            sender=sending,
            held=held,
            profile=profile,
            now=T0,
            clock=lambda: T0,
            limit=limit,
        )
    )
    return ran, kept, sending


# ------------------------------------------------------------------------ what is probed
def test_a_deployment_nobody_has_called_is_claimed_probed_and_its_outcome_appended() -> None:
    """**The leaf.** A rung with no live evidence and no probe is due; the tick claims it, sends
    one probe and appends the outcome, and a failing one is named in the report.

    Delete this and the control can report a successful run having probed nothing."""
    ran, store, sender = tick(
        Ladder((rung("anthropic"), rung("moonshot", position=1))),
        sender=Sender(failing=frozenset({"moonshot-main-1"})),
    )

    assert store.claimed == ["anthropic-main-0", "moonshot-main-1"]
    assert sender.sent == store.claimed
    assert store.observed == [("anthropic-main-0", True), ("moonshot-main-1", False)]
    assert ran.summary() == "probed 2 deployment(s), 1 failed; failing: moonshot-main-1"


def test_with_no_key_held_nothing_is_read_or_sent_and_the_tick_says_so() -> None:
    """Today's state on every install before a key is put in. Delete this and a keyless tick could
    read the ladder, or send an unauthenticated request, or report a failure for doing nothing."""
    ladder = Ladder((rung("anthropic"),))

    ran, store, sender = tick(ladder, held=frozenset())

    assert ran.summary() == NOTHING_HELD
    assert ladder.reads == 0
    assert store.claimed == [] and sender.sent == []


def test_a_local_only_install_probes_no_hosted_provider() -> None:
    """Delete this and the prober would send text to a hosted provider on an install whose profile
    is the decision that nothing leaves its hardware."""
    ran, _, sender = tick(Ladder((rung("anthropic"),)), profile=LOCAL_PROFILE)

    assert ran.summary() == LOCAL_ONLY
    assert sender.sent == []


def test_a_switched_off_provider_a_keyless_provider_and_a_disabled_rung_are_not_probed() -> None:
    """Delete this and the prober would reach a provider an administrator took out, or dial one
    whose key it does not hold, or a rung taken out of rotation."""
    off = rung("moonshot", position=1)
    disabled = LadderRung(**{**rung("anthropic", position=2).__dict__, "enabled": False})
    ran, _, sender = tick(
        Ladder(
            (rung("anthropic"), off, disabled, rung("deepseek", position=3)),
            switched_off=frozenset({"moonshot"}),
        )
    )

    assert sender.sent == ["anthropic-main-0"]
    assert ran.probed == ("anthropic-main-0",)


def test_a_deployment_on_two_tiers_is_probed_once() -> None:
    """Delete this and one moment's outcome lands twice in the ring, which reads as two failures
    and opens the breaker on one event."""
    heavy = LadderRung(**{**rung("anthropic").__dict__, "tier": Tier.HEAVY, "rung_id": "h"})

    _, _, sender = tick(Ladder((rung("anthropic"), heavy)))

    assert sender.sent == ["anthropic-main-0"]


def test_a_claim_another_tick_holds_is_not_probed() -> None:
    """Delete this and two replicas' ticks could both probe one deployment in one minute."""
    _, store, sender = tick(
        Ladder((rung("anthropic"), rung("moonshot", position=1))),
        store=Store(taken=frozenset({"anthropic-main-0"})),
    )

    assert sender.sent == ["moonshot-main-1"]
    assert store.observed == [("moonshot-main-1", True)]


def test_a_deployment_probed_inside_the_interval_or_with_live_traffic_is_not_due() -> None:
    """The stored claim instant and the stored live instant both count, so a rung probed thirty
    seconds ago, or called by a person a minute ago, is left alone.

    Delete this and the prober would ignore what the table says and probe every rung every tick."""
    recent = T0 - timedelta(seconds=PROBE_INTERVAL_SECONDS / 2)
    live = T0 - timedelta(seconds=60)
    _, _, sender = tick(
        Ladder(
            (rung("anthropic"), rung("moonshot", position=1)),
            rings=(
                StoredRings(
                    deployment_id="anthropic-main-0", provider="anthropic", last_probe_at=recent
                ),
                StoredRings(
                    deployment_id="moonshot-main-1",
                    provider="moonshot",
                    live=(RingEntry(ok=True, at=live),),
                    last_live_at=live,
                ),
            ),
            attempts=(Attempt(deployment_id="moonshot-main-1", finished_at=live, outcome="ok"),),
        )
    )

    assert sender.sent == []


def test_a_tick_probes_no_more_than_its_limit() -> None:
    """Delete this and an estate-wide outage turns one tick into a retry storm."""
    many = tuple(rung("anthropic", position=n) for n in range(PROBES_PER_TICK + 3))

    _, _, sender = tick(Ladder(many))

    assert len(sender.sent) == PROBES_PER_TICK


# --------------------------------------------------------------- what a probe counts as
class Replies:
    """A transport answering each probe with the next item, and keeping what it was sent."""

    def __init__(self, *script: Any) -> None:
        self.script = list(script)

    def __call__(self, request: Any) -> Any:
        answer = self.script.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


@pytest.mark.parametrize(
    ("failure", "ok"),
    [
        (TransportConnectionError(), False),
        (TransportStatusError(503), False),
        (TransportStatusError(429), True),
        (TransportStatusError(401), True),
    ],
)
def test_a_probe_fails_only_on_the_providers_own_failure(failure: Exception, ok: bool) -> None:
    """`A_PROBE_FAILS_ONLY_ON_THE_PROVIDERS_OWN_FAILURE`. Delete this and a refused key or a rate
    limit would open a breaker on a provider that is up."""
    assert A_PROBE_FAILS_ONLY_ON_THE_PROVIDERS_OWN_FAILURE
    sender = DriverProbes(httpx.Client(), _Keys({"anthropic": "k"}))
    from brain.models.adapter import SdkDriver

    sender._drivers["anthropic"] = SdkDriver(provider="anthropic", transport=Replies(failure))

    assert sender.send(rung("anthropic")) is ok


def test_a_probe_is_sent_the_fixed_sentence_with_a_short_timeout_and_a_small_cap() -> None:
    """Delete this and a probe could carry something about the install, or wait a rung's full
    timeout, or let a model write a page on every tick."""
    seen: list[Any] = []

    def reply(request: Any) -> Any:
        seen.append(request)
        from brain.models.adapter import Completion

        return Completion(text="ready", finish_reason="stop", input_tokens=5, output_tokens=1)

    from brain.models.adapter import SdkDriver

    sender = DriverProbes(httpx.Client(), _Keys({"anthropic": "k"}))
    sender._drivers["anthropic"] = SdkDriver(provider="anthropic", transport=reply)

    assert sender.send(rung("anthropic")) is True
    (request,) = seen
    assert [one.content for one in request.messages] == [model_probe_run.PROBE_PROMPT]
    assert request.timeout_seconds == model_probe_run.PROBE_TIMEOUT_SECONDS
    assert request.max_output_tokens == model_probe_run.PROBE_MAX_OUTPUT_TOKENS


# ------------------------------------------------------------------------------ the keys
class _Keys:
    def __init__(self, keys: dict[str, str]) -> None:
        self.keys = keys

    def held(self, slots: Sequence[ProviderSlot], now: float) -> frozenset[str]:
        return frozenset(one.slug for one in slots if one.slug in self.keys)

    def lookup(self, slot: ProviderSlot) -> KeyLookup:
        return lambda: self.keys.get(slot.slug)


class Vault:
    """Answers `read_static_kv` from a dict and counts reads; a missing slot is unavailable."""

    def __init__(self, slots: dict[str, str]) -> None:
        self.slots = slots
        self.reads: list[str] = []

    def read_static_kv(self, path: str) -> dict[str, Any]:
        self.reads.append(path)
        if path not in self.slots:
            raise SecretsUnavailableError("absent")
        return {"api_key": self.slots[path]}


def test_the_worker_holds_a_key_the_vault_has_and_reads_it_again_only_after_its_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the prober would read every slot every minute, a ledger line each, or keep
    a rotated key for ever."""
    for slot in PROVIDER_SLOTS:
        monkeypatch.delenv(slot.env_var, raising=False)
    vault = Vault({"providers/anthropic": "sk-a"})
    keys = WorkerProviderKeys(vault, ttl=100.0)  # type: ignore[arg-type]

    assert keys.held(PROVIDER_SLOTS, 0.0) == frozenset({"anthropic"})
    assert keys.held(PROVIDER_SLOTS, 50.0) == frozenset({"anthropic"})
    assert len(vault.reads) == len(PROVIDER_SLOTS)
    keys.held(PROVIDER_SLOTS, 150.0)
    assert len(vault.reads) == 2 * len(PROVIDER_SLOTS)


def test_a_key_the_worker_environment_sets_outranks_the_vault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`load_into_environment`'s rule. Delete this and a developer's shell key would be ignored
    for whatever the vault holds."""
    for slot in PROVIDER_SLOTS:
        monkeypatch.delenv(slot.env_var, raising=False)
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-shell")
    keys = WorkerProviderKeys(None)

    assert keys.held(PROVIDER_SLOTS, 0.0) == frozenset({"moonshot"})
    moonshot = next(one for one in PROVIDER_SLOTS if one.slug == "moonshot")
    assert keys.lookup(moonshot)() == "sk-shell"


def test_the_runner_on_an_install_with_no_key_opens_nothing_and_reports_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The control, started by name.** The worker's schedule arm on an install with no key held
    and no vault answers with the sentence and never opens the database, which is why a URL that
    points nowhere is enough.

    Delete this and the arm could be dispatched to a runner that fails every minute on the state
    every install starts in."""
    from brain.ops.schedule_runner import A_PROBE_IN_REPORT_ONLY_MODE_STILL_PROBES, start_control

    for slot in PROVIDER_SLOTS:
        monkeypatch.delenv(slot.env_var, raising=False)
    monkeypatch.delenv("BRAIN_VAULT_ADDRESS", raising=False)
    monkeypatch.delenv("BRAIN_VAULT_TOKEN", raising=False)
    monkeypatch.setattr("brain.install.value_of", lambda name: HOSTED_PROFILE)
    monkeypatch.setattr(model_probe_run, "_PROCESS_KEYS", {})

    said = start_control(
        "model_health_probes",
        now=T0,
        report_only=False,
        database_url="postgresql://nobody@127.0.0.1:1/none",
    )
    asked_to_report = start_control(
        "model_health_probes",
        now=T0,
        report_only=True,
        database_url="postgresql://nobody@127.0.0.1:1/none",
    )

    assert said == NOTHING_HELD
    assert asked_to_report == f"report only, probed anyway: {NOTHING_HELD}"
    assert A_PROBE_IN_REPORT_ONLY_MODE_STILL_PROBES
