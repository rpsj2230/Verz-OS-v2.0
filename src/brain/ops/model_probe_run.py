"""The background prober: every sixty seconds, ask the providers nobody has asked lately.

`brain.models.health.next_probes` has said for weeks which deployments are due a probe, and the
`model_health_probes` control has said what it guards ("a provider which has stopped answering is
found by asking it rather than by a person's question being the probe") while nothing ran it. This
is the run. The worker's schedule starts it through `brain.ops.schedule_runner.model_health_probes`
at the control's cadence, `PROBE_INTERVAL_SECONDS`.

**What one tick does.** It reads the ladder, the attempts and the stored rings through the same
`SessionLadder` a person's question plans from, so the health it judges is the health the next
call would see; it keeps the rungs whose provider holds a key; it replays their health, with the
stored rings' instants laid over it; it asks `next_probes` which are due, most urgent first and at
most `PROBES_PER_TICK`; it claims each in `ops.provider_health`, so a second replica's tick cannot
probe the same deployment; it sends one fixed sentence; and it appends the outcome to the probe
ring. The next plan anywhere replays that ring through `ProviderHealth.record_probe`
(`brain.models.evidence`), which is how a probe opens an idle dead rung or closes a recovered one.

**A probe is a transport fact, judged as the replay judges an attempt.** It is recorded failed
only when the provider failed on its own side: no connection, no answer in time, or a server
error (`brain.models.evidence.ILL_HEALTH`). A rate limit, a refused key and a content refusal are
the provider answering, and recording them as failures would take a working provider out of
rotation over our own configuration. See `A_PROBE_FAILS_ONLY_ON_THE_PROVIDERS_OWN_FAILURE`.

**A probe goes only where a question could.** A provider an administrator switched off is not
probed, because the switch exists to stop anything reaching it; an install whose profile keeps
text on its own hardware probes no hosted provider at all. Both are read on every tick, through the
same ladder read and the same install setting the executor reads.

**With no key held, nothing is probed and the tick says so.** That is every install before an
administrator puts a key in, and it is a successful run: `NOTHING_HELD` is its whole report. The
local inference server takes no key and is not probed here: it is the client's own hardware and
its health is the operating system's to report, and a probe that needs no credential is a
different control.

**The key is read from the vault by the worker, per provider, and kept in memory for at most
`KEY_REREAD_SECONDS`.** The worker policy (`ops/openbao/policies/worker.hcl`) names the four model
provider slots one at a time with `read` and nothing else, and the argument is there. The key never
enters the worker's environment: it is handed to the transport as a lookup, so a rotated key is
picked up within a quarter of an hour and nothing else in the worker can reach it. Rereading every
tick was rejected: every read is a line the vault audit shipper copies into the ledger, and four a
minute is five thousand a day of lines that say nothing. A variable the worker's own environment
sets outranks the vault, which is `brain.ops.provider_keys.load_into_environment`'s rule.

**Nothing about the install reaches the provider.** The sentence is fixed and asks for one word,
the output is capped, and no question, passage or person is in it.

Task ids: M5.4.7, M5.4.3
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.models.adapter import SdkDriver
from brain.models.assembly import LadderRung, local_only
from brain.models.calls import Ladder
from brain.models.driver import DriverMessage, DriverRequest, ProviderUnavailable, Role
from brain.models.evidence import EVIDENCE_WINDOW, ILL_HEALTH, StoredRings, outcome_of, replayed
from brain.models.health import PROBE_INTERVAL_SECONDS, ProviderHealth, next_probes
from brain.models.wire import PROVIDER_WIRES, KeyLookup, http_transport
from brain.ops.openbao import OpenBaoVault
from brain.ops.provider_health_store import probe_claimed, probe_observed
from brain.ops.provider_keys import PROVIDER_SLOTS, ProviderSlot, read_static
from brain.ops.secrets import SecretsUnavailableError, VaultRole
from brain.settings import process_environment

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------- written-down reasons

#: Why a rate limit or a refused key is not a failed probe.
A_PROBE_FAILS_ONLY_ON_THE_PROVIDERS_OWN_FAILURE: Final = (
    "A probe records failure only when the provider failed on its own side: no connection, no "
    "answer in time, or a server error. A rate limit is the provider working and asking for less, "
    "a refused key is our configuration, and a content refusal is the model answering; recording "
    "any of them as a failure would open a breaker on a provider that is up."
)

#: What a tick with no key held reports. A successful run, not a failure.
NOTHING_HELD: Final = "no provider holds a key, so nothing was probed"

#: What a tick on a local-only install reports.
LOCAL_ONLY: Final = "the install keeps text on its own hardware, so no hosted provider is probed"

# ----------------------------------------------------------------------------- the figures

#: What a probe sends. Fixed, so nothing about the install reaches a provider.
PROBE_PROMPT: Final = "Reply with the single word: ready"

#: The output ceiling on a probe. One word needs fewer; the margin is for a model that says more.
PROBE_MAX_OUTPUT_TOKENS: Final = 8

#: The longest a probe waits. Shorter than an answer-lane rung, because a probe is asking whether
#: the provider answers at all, and ten seconds of silence is already the answer.
PROBE_TIMEOUT_SECONDS: Final = 10.0

#: The most probes one tick sends. `next_probes` says why a bound is needed: an estate-wide outage
#: makes every deployment due at once, and a tick that probed them all together would be a retry
#: storm aimed at a provider already struggling. Five at ten seconds each fits inside the minute.
PROBES_PER_TICK: Final = 5

#: How long a key read from the vault is kept before it is read again. See the module docstring.
KEY_REREAD_SECONDS: Final = 900.0


# ------------------------------------------------------------------------------ the ports


class ProbeStore(Protocol):
    """Where a probe is claimed and its outcome appended."""

    async def claim(self, deployment_id: str, provider: str, *, at: datetime) -> bool:
        """Claim this deployment's probe at `at`; False when another tick has it or had it."""
        ...

    async def observed(self, deployment_id: str, *, ok: bool, at: datetime) -> None:
        """Append one probe outcome to the deployment's probe ring."""
        ...


class ProbeSender(Protocol):
    """Sends one probe to one rung and says whether the provider answered on its own terms."""

    def send(self, rung: LadderRung) -> bool:
        """True unless the provider failed on its own side. Synchronous, like `ModelDriver`."""
        ...


class ProviderKeys(Protocol):
    """Which providers the worker holds a key for, and a lookup for each. Names, never values."""

    def held(self, slots: Sequence[ProviderSlot], now: float) -> frozenset[str]:
        """The slugs whose key this worker can read now."""
        ...

    def lookup(self, slot: ProviderSlot) -> KeyLookup:
        """A lookup the transport calls at the moment of the probe."""
        ...


# ------------------------------------------------------------------------------ the policy


@dataclass(frozen=True)
class ProbeRun:
    """What one tick came to, in counts and names of deployments only."""

    probed: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    skipped: str = ""

    def summary(self) -> str:
        """The run's report, as `ops.control_run.detail` keeps it."""
        if self.skipped:
            return self.skipped
        if not self.probed:
            return "no deployment was due a probe"
        bad = f"; failing: {', '.join(self.failed)}" if self.failed else ""
        return f"probed {len(self.probed)} deployment(s), {len(self.failed)} failed{bad}"


def probed_rungs(
    rungs: Iterable[LadderRung], held: frozenset[str], switched_off: frozenset[str] = frozenset()
) -> dict[str, LadderRung]:
    """One rung per deployment, enabled, switched on and with its key held, by deployment.

    A deployment on two tiers is probed once: health is per deployment, and probing it twice a
    tick would put two outcomes of one moment into its ring.
    """
    found: dict[str, LadderRung] = {}
    for one in rungs:
        if (
            one.enabled
            and one.provider in held
            and one.provider not in switched_off
            and one.deployment_id not in found
        ):
            found[one.deployment_id] = one
    return found


def healths_for(
    deployments: Iterable[str],
    replay: Mapping[str, ProviderHealth],
    rings: Mapping[str, StoredRings],
) -> tuple[ProviderHealth, ...]:
    """Each deployment's replayed health with its stored instants laid over it.

    `last_probe_at` is the stored claim, because the interval measures how often we ask, and the
    replay knows only when probes answered. `last_live_at` is the later of the replay's and the
    stored ring's, because the ring outlives the replay window: a deployment whose last live call
    was an hour ago is stale, not unknown.
    """
    found: list[ProviderHealth] = []
    for deployment in deployments:
        health = replay.get(deployment, ProviderHealth.for_deployment(deployment))
        stored = rings.get(deployment)
        if stored is not None:
            last_live = max(
                (one for one in (health.last_live_at, stored.last_live_at) if one is not None),
                default=None,
            )
            health = replace(
                health,
                last_probe_at=stored.last_probe_at
                if stored.last_probe_at is not None
                else health.last_probe_at,
                last_live_at=last_live,
            )
        found.append(health)
    return tuple(found)


async def probe_on(
    *,
    ladder: Ladder,
    store: ProbeStore,
    sender: ProbeSender,
    held: frozenset[str],
    profile: str,
    now: datetime,
    clock: Callable[[], datetime],
    limit: int = PROBES_PER_TICK,
) -> ProbeRun:
    """One tick of the prober. See the module docstring for the order and why."""
    if local_only(profile):
        return ProbeRun(skipped=LOCAL_ONLY)
    if not held:
        return ProbeRun(skipped=NOTHING_HELD)
    state = await ladder.current(now)
    rungs = probed_rungs(state.rungs, held, state.switched_off)
    if not rungs:
        return ProbeRun(skipped="no enabled rung names a provider whose key is held")
    since = now - EVIDENCE_WINDOW
    replay = replayed(state.attempts, [p for one in state.rings for p in one.probes(since)])
    rings = {one.deployment_id: one for one in state.rings}
    due = next_probes(healths_for(rungs, replay, rings), now, limit=limit)
    probed: list[str] = []
    failed: list[str] = []
    for verdict in due:
        rung = rungs[verdict.deployment_id]
        if not await store.claim(rung.deployment_id, rung.provider, at=now):
            continue
        ok = await asyncio.to_thread(sender.send, rung)
        await store.observed(rung.deployment_id, ok=ok, at=clock())
        probed.append(rung.deployment_id)
        if not ok:
            failed.append(rung.deployment_id)
    return ProbeRun(probed=tuple(probed), failed=tuple(failed))


# ----------------------------------------------------------------------------- the parts


class SessionProbes:
    """`ProbeStore` over `ops.provider_health`, on the worker's own login."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def claim(self, deployment_id: str, provider: str, *, at: datetime) -> bool:
        interval = timedelta(seconds=PROBE_INTERVAL_SECONDS)
        async with self.sessions() as session:
            found = await session.execute(
                probe_claimed(deployment_id, provider, at=at, interval=interval)
            )
            claimed = found.first() is not None
            await session.commit()
        return claimed

    async def observed(self, deployment_id: str, *, ok: bool, at: datetime) -> None:
        async with self.sessions() as session:
            await session.execute(probe_observed(deployment_id, ok=ok, at=at))
            await session.commit()


class DriverProbes:
    """`ProbeSender` through the product's own drivers, with the key handed in as a lookup."""

    def __init__(self, client: httpx.Client, keys: ProviderKeys) -> None:
        slots = {one.slug: one for one in PROVIDER_SLOTS}
        self._drivers = {
            slug: SdkDriver(
                provider=slug,
                transport=http_transport(wire, client=client, key=keys.lookup(slots[slug])),
            )
            for slug, wire in PROVIDER_WIRES.items()
            if slug in slots
        }

    def send(self, rung: LadderRung) -> bool:
        driver = self._drivers.get(rung.provider)
        if driver is None:
            return True
        request = DriverRequest(
            deployment_id=rung.deployment_id,
            model=rung.model,
            messages=(DriverMessage(role=Role.USER, content=PROBE_PROMPT),),
            timeout_seconds=min(rung.timeout_seconds, PROBE_TIMEOUT_SECONDS),
            max_output_tokens=PROBE_MAX_OUTPUT_TOKENS,
        )
        try:
            driver.complete(request)
        except ProviderUnavailable as failed:
            return outcome_of(failed.failure) not in ILL_HEALTH
        return True


class WorkerProviderKeys:
    """`ProviderKeys` over the worker's environment and its vault, kept for `KEY_REREAD_SECONDS`.

    A lock, because the transport's lookup runs in the thread `probe_on` hands the call to.
    """

    def __init__(self, vault: OpenBaoVault | None, *, ttl: float = KEY_REREAD_SECONDS) -> None:
        self._vault = vault
        self._ttl = ttl
        self._lock = threading.Lock()
        self._kept: dict[str, tuple[str | None, float]] = {}

    def _read(self, slot: ProviderSlot, now: float) -> str | None:
        own = process_environment().get(slot.env_var, "").strip()
        if own:
            return own
        with self._lock:
            kept = self._kept.get(slot.slug)
            if kept is not None and now - kept[1] < self._ttl:
                return kept[0]
        value: str | None = None
        if self._vault is not None:
            try:
                value = read_static(self._vault, slot.path)
            except SecretsUnavailableError:
                value = None
        with self._lock:
            self._kept[slot.slug] = (value, now)
        return value

    def held(self, slots: Sequence[ProviderSlot], now: float) -> frozenset[str]:
        return frozenset(one.slug for one in slots if self._read(one, now) is not None)

    def lookup(self, slot: ProviderSlot) -> KeyLookup:
        def read() -> str | None:
            return self._read(slot, time.monotonic())

        return read


#: One per worker process, so a key read on one tick serves the next quarter of an hour's.
_PROCESS_KEYS: dict[tuple[str, str], WorkerProviderKeys] = {}


def worker_provider_keys(address: str, token: str) -> WorkerProviderKeys:
    """This worker's key reader, from the two settings its environment carries.

    Both must be set, and an address that is not a URL is no vault, for
    `brain.ops.connector_sync_run.worker_connector_keys`' reasons; the environment still counts.
    """
    found = _PROCESS_KEYS.get((address, token))
    if found is not None:
        return found
    vault: OpenBaoVault | None = None
    if address and token:
        try:
            vault = OpenBaoVault(address, token, role=VaultRole.WORKER)
        except ValueError:
            vault = None
    found = WorkerProviderKeys(vault)
    _PROCESS_KEYS[(address, token)] = found
    return found


def _utc_now() -> datetime:
    return datetime.now(UTC)


def run_model_probes_now(
    database_url: str,
    *,
    now: datetime,
    vault_address: str,
    vault_token: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> ProbeRun:
    """`probe_on`, from a thread with no event loop of its own, with the worker's real parts.

    The keys are asked first, so a tick with none held opens no connection at all.
    """
    from brain.install import value_of
    from brain.ops.model_service import SessionLadder
    from brain.session import make_app_engine, make_session_factory

    try:
        profile = value_of("INSTALL_MODEL_PROFILE")
    except Exception:
        # An unreadable profile is the local one, which sends nothing anywhere.
        profile = ""
    if local_only(profile):
        return ProbeRun(skipped=LOCAL_ONLY)
    keys = worker_provider_keys(vault_address, vault_token)
    held = keys.held(PROVIDER_SLOTS, time.monotonic())
    if not held:
        return ProbeRun(skipped=NOTHING_HELD)

    async def go() -> ProbeRun:
        engine = make_app_engine(database_url)
        client = httpx.Client(follow_redirects=False)
        try:
            sessions = make_session_factory(engine)
            return await probe_on(
                ladder=SessionLadder(sessions),
                store=SessionProbes(sessions),
                sender=DriverProbes(client, keys),
                held=held,
                profile=profile,
                now=now,
                clock=_utc_now,
            )
        finally:
            client.close()
            await engine.dispose()

    ran = asyncio.run(go(), loop_factory=loop_factory)
    log.info("models.probed", probed=len(ran.probed), failed=len(ran.failed))
    return ran
