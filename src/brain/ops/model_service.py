"""The model driver as the application holds it: built once at start, over this install's database.

`brain.models.calls.ModelCalls` is the executor and decides nothing about where its inputs live.
This is the half that does: the statements that read the ladder, the provider switches and the
recent attempts, the two that write an attempt, the HTTP client every provider call shares, and
`model_service_at_start`, which `brain.app.lifespan` calls. The split is the layout's own rule,
"nothing that decides policy owns a client", and for the reason it gives: a breaker's half-open
transition cannot be tested through a module that opens a socket.

**What is built at start and what is read per call.** The drivers and their client are built
once, because a connection pool per request is a TLS handshake per question. The install's model
profile, which keys this process holds, the live rungs, the switches and the attempts are read
when a call is planned, because each can change while the process runs and three of them are
changed from the console. See `brain.models.assembly` for the argument.

**A provider is switched off in `ops.setting`, under `provider.<slug>`, and a provider nobody has
switched is governed by the profile and its key.** `brain.ops.setting_store` argues why a
console switch belongs in that table rather than one of its own, and `brain.ops.features` is the
precedent. The default is on, and that is the decision rather than an oversight: the install's
profile is the consent to send text to a hosted provider at all, and a key in the vault is an
administrator choosing that provider, so a second switch defaulting off would be a third
agreement to the same thing and an install that answers nothing after its wizard finished. What
the switch is for is taking a provider out, at once and everywhere. See
`A_PROVIDER_NOBODY_SWITCHED_IS_GOVERNED_BY_THE_PROFILE_AND_ITS_KEY`.

**A switch that cannot be read is every provider switched off.** Reading the switches is a
database round trip, and a database that does not answer does not say an administrator has not
switched something off. Falling back to "all on" would send questions to a provider somebody may
have taken out for a reason. So the call finds no rung and says it could not reach a model, which
is `Degraded`, and the log says why. See `A_SWITCH_NOBODY_COULD_READ_IS_OFF`.

**An attempt row that cannot be written does not stop the call.** The row is evidence, and the
rule for evidence is `brain.ops.question_store.
A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT`, imported rather than
restated. The row's id comes back from the insert and the finish updates that row by id, never by
trace and sequence: a caller may propose its own trace id, and a finish matched on the pair would
overwrite an earlier request's attempt with this one's outcome.

**Which keys are held is read from the environment names, never from the values.**
`brain.ops.provider_keys.names_in_environment` returns names, and `held_providers` turns them
into slugs, so this module never has a key in hand.

**The provider registry is read with the ladder, in the same session** (`ops.model_provider`,
`brain.models.registry`): each rung's documented region, each provider's lane overrides, and the
providers an administrator added from the console. An added provider is reached through a driver
built on first sight and kept while its address is unchanged (`AddedProviderDrivers`), and its
slot is handed to `brain.ops.provider_keys.PROCESS_ADDED_SLOTS` so the minute's key refresh loads
its key. A row the registry cannot hold is left out and logged, and its provider then has no row,
which is `global` and the rung's own numbers: the conservative reading of an unreadable claim.

**The tier rows, the residency constraints and the stored health rings are read in that same
session** (`brain.ops.provider_health_store`), so the tier a request lands in, the regions it may
go to and the probes that fenced a rung off are the ones in force at the moment it planned. The
executor is handed the ring and alert stores too, so every attempt reaches `ops.provider_health`
and every chain that went deep reaches `ops.chain_depth_alert`.

Task ids: M27.8.8, M5.3.4, M5.1.2, M5.7.2, M5.6.4, M5.2.2, M5.4.3, M5.4.8, M5.5.1
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import httpx
import structlog
from sqlalchemy import Select, Update, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert

from brain.install import value_of
from brain.knowledge.embed_policy import ENDPOINT_SETTING, endpoint_refusals
from brain.models.adapter import SdkDriver
from brain.models.assembly import LadderRung
from brain.models.calls import LadderState, ModelCalls
from brain.models.disclosure import DataCategory, categories_of
from brain.models.driver import ModelDriver
from brain.models.evidence import EVIDENCE_WINDOW, Attempt
from brain.models.registry import ProviderKind, ProviderRecord, RegistryError, record_of
from brain.models.routing import Tier
from brain.models.wire import (
    LOCAL_PROVIDER,
    PROVIDER_WIRES,
    added_wire,
    http_transport,
    local_wire,
)
from brain.ops.provider_health_store import (
    SessionDepthAlerts,
    SessionHealth,
    constraint_of,
    live_constraints,
    live_tiers,
    rings_of,
    stored_rings,
    tier_rules_of,
)
from brain.ops.provider_keys import (
    PROCESS_ADDED_SLOTS,
    PROVIDER_SLOTS,
    AddedProviderSlots,
    ProviderSlot,
    added_slot,
    names_in_environment,
)
from brain.ops.question_store import (
    A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT,
)
from brain.ops.setting_store import SettingState, put, read_namespace, values_under
from brain.tables.config import SettingType
from brain.tables.model_registry import ModelProviderRow
from brain.tables.routing import ModelAttemptRow, RoutingRungRow

log = structlog.get_logger(__name__)

__all__ = [
    "A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT",
    "ModelService",
    "model_service_at_start",
]

# ------------------------------------------------------------------- written-down reasons

#: Why a provider with no switch row is on.
A_PROVIDER_NOBODY_SWITCHED_IS_GOVERNED_BY_THE_PROFILE_AND_ITS_KEY: Final = (
    "The install's profile is the decision to let text reach a hosted provider, and a key put "
    "into the vault is an administrator choosing one. A switch that also defaulted off would be "
    "a third agreement to the same thing, and an install whose wizard had finished would answer "
    "nothing until somebody found it. The switch exists to take a provider out, at once and in "
    "every process, so it defaults to the two decisions already made."
)

#: Why a switch that could not be read counts as off.
A_SWITCH_NOBODY_COULD_READ_IS_OFF: Final = (
    "A database that does not answer has not said that nobody switched a provider off. Reading "
    "that silence as every provider on would send questions to a provider an administrator took "
    "out, possibly for the reason that it must not receive them. So every provider is off for "
    "that call, which answers that no model could be reached, and the log says why."
)

#: The `ops.setting` namespace a provider's switch is kept under.
PROVIDER_NAMESPACE: Final = "provider"

#: Every provider this install can be told about on the Models screen, in the order it lists
#: them: the key slots in their declared order, then the install's own inference server.
KNOWN_PROVIDERS: Final[tuple[str, ...]] = (*(one.slug for one in PROVIDER_SLOTS), LOCAL_PROVIDER)

#: The most live rungs a call plans from. A resource bound and not a permission: a ladder is
#: tiers times rungs and both are operator-controlled, so this is far above any real one.
MAX_RUNGS: Final = 200

#: The most attempts a call replays health from. Forty minutes of attempts at this system's
#: traffic is tens of rows; the bound is what stops a burst turning a plan into a scan.
MAX_ATTEMPTS_REPLAYED: Final = 2000


# ------------------------------------------------------------------------ the statements


def live_rungs() -> Select[tuple[RoutingRungRow]]:
    """Every live rung, in ladder order, bounded. `deleted_at` tested here as well as by policy."""
    return (
        select(RoutingRungRow)
        .where(RoutingRungRow.deleted_at.is_(None))
        .order_by(RoutingRungRow.tier, RoutingRungRow.position)
        .limit(MAX_RUNGS)
    )


#: The most provider rows a call reads. A resource bound far above any real registry.
MAX_PROVIDERS: Final = 100


def live_providers() -> Select[tuple[ModelProviderRow]]:
    """Every live provider row, by slug, bounded. `deleted_at` tested here as well as by policy."""
    return (
        select(ModelProviderRow)
        .where(ModelProviderRow.deleted_at.is_(None))
        .order_by(ModelProviderRow.slug)
        .limit(MAX_PROVIDERS)
    )


def provider_record_of(row: ModelProviderRow) -> ProviderRecord | None:
    """One row as a record, or None, logged, when the registry cannot hold it."""
    try:
        return record_of(
            {
                "slug": row.slug,
                "kind": row.kind,
                "label": row.label,
                "base_url": row.base_url,
                "models": row.models,
                "processing_region": row.processing_region,
                "residency_class": row.residency_class,
                "storage_location": row.storage_location,
                "retention_terms": row.retention_terms,
                "training_terms": row.training_terms,
                "agreement_url": row.agreement_url,
                "lane_overrides": row.lane_overrides,
            }
        )
    except (RegistryError, ValueError, KeyError) as exc:
        log.warning("models.provider_row_unreadable", slug=row.slug, error=type(exc).__name__)
        return None


def disclosures() -> Select[tuple[str, str, int]]:
    """Per provider and category, how many attempts sent it (M5.6.4). Kinds, never content."""
    category = func.jsonb_array_elements_text(ModelAttemptRow.data_categories).label("category")
    sent = (
        select(RoutingRungRow.provider.label("provider"), category)
        .join(RoutingRungRow, RoutingRungRow.id == ModelAttemptRow.rung_id)
        .subquery()
    )
    return (
        select(sent.c.provider, sent.c.category, func.count())
        .group_by(sent.c.provider, sent.c.category)
        .order_by(sent.c.provider, sent.c.category)
    )


def disclosure_counts(
    rows: Sequence[tuple[str, str, int]],
) -> dict[str, dict[DataCategory, int]]:
    """The grouped rows as counts per provider, dropping a category this release does not know."""
    found: dict[str, dict[DataCategory, int]] = {}
    for provider, value, count in rows:
        for category in categories_of((value,)):
            found.setdefault(provider, {})[category] = int(count)
    return found


def recent_attempts(since: datetime) -> Select[tuple[str, datetime | None, str | None]]:
    """Every attempt that finished since `since`, with the deployment its rung names.

    Joined through the rung, because the attempt row names a rung and health is per deployment.
    Unfinished attempts are left out: an attempt still in flight is not yet evidence either way.
    """
    return (
        select(RoutingRungRow.deployment_id, ModelAttemptRow.finished_at, ModelAttemptRow.outcome)
        .join(RoutingRungRow, RoutingRungRow.id == ModelAttemptRow.rung_id)
        .where(ModelAttemptRow.finished_at.is_not(None))
        .where(ModelAttemptRow.finished_at >= since)
        .order_by(ModelAttemptRow.finished_at)
        .limit(MAX_ATTEMPTS_REPLAYED)
    )


def attempt_started(
    trace_id: str,
    rung_id: str,
    sequence: int,
    at: datetime,
    categories: tuple[str, ...] = (),
) -> ReturningInsert[tuple[uuid.UUID]]:
    """The in-flight row for one attempt, returning its id. No outcome and no finish yet."""
    return (
        insert(ModelAttemptRow)
        .values(
            trace_id=trace_id,
            rung_id=uuid.UUID(rung_id),
            sequence=sequence,
            started_at=at,
            data_categories=list(categories),
        )
        .returning(ModelAttemptRow.id)
    )


def attempt_finished(token: str, at: datetime, outcome: str, status: int | None) -> Update:
    """Finish one attempt by the id its insert returned, and never by its trace and sequence."""
    return (
        update(ModelAttemptRow)
        .where(ModelAttemptRow.id == uuid.UUID(token))
        .values(finished_at=at, outcome=outcome, status_code=status)
    )


def ladder_rung_of(row: RoutingRungRow) -> LadderRung:
    """One row, copied field by field. `timeout_seconds` is NUMERIC and arrives as a Decimal."""
    return LadderRung(
        rung_id=str(row.id),
        tier=Tier(row.tier),
        position=row.position,
        deployment_id=row.deployment_id,
        provider=row.provider,
        model=row.model,
        attempts=row.attempts,
        timeout_seconds=float(row.timeout_seconds),
        max_concurrency=row.max_concurrency,
        enabled=row.enabled,
    )


def switched_off_in(states: Mapping[str, SettingState]) -> frozenset[str]:
    """The providers whose switch row holds the JSON `false`, from rows keyed by provider slug.

    `is False` rather than falsiness, for the reason `brain.ops.features.switched_on_in` gives:
    the column is jsonb, and a string written at a prompt is not a switch.
    """
    return frozenset(
        name
        for name, state in states.items()
        if state.value_type == SettingType.BOOLEAN.value and state.value is False
    )


def provider_key(provider: str) -> str:
    """The `ops.setting` key one provider's switch is kept under."""
    return f"{PROVIDER_NAMESPACE}.{provider}"


async def switch_states(session: AsyncSession) -> dict[str, SettingState]:
    """Every live switch row, by provider slug."""
    return values_under(await read_namespace(session, PROVIDER_NAMESPACE), PROVIDER_NAMESPACE)


async def switch_provider(
    session: AsyncSession,
    provider: str,
    *,
    on: bool,
    by: str,
    known: Sequence[str] = KNOWN_PROVIDERS,
) -> None:
    """Switch one provider on or off in the caller's transaction. The caller commits.

    Off and on are both rows, for `brain.ops.features.switch`'s reason: a retired row would say
    the same thing as never having been touched, and the row is who changed it last. `known` is
    the built-in providers and, from the Models screen, the added ones as well.
    """
    if provider not in known:
        msg = f"{provider!r} is not a provider this install can call"
        raise ValueError(msg)
    await put(
        session,
        provider_key(provider),
        value_type=SettingType.BOOLEAN,
        value=on,
        description=f"Whether questions may be sent to {provider}",
        updated_by=by,
    )


def held_providers(slots: Sequence[ProviderSlot] = PROVIDER_SLOTS) -> frozenset[str]:
    """The providers whose key variable this process's environment sets. Names, never values."""
    names = names_in_environment(slots)
    return frozenset(one.slug for one in slots if one.env_var in names)


# ------------------------------------------------------------------------- the stores


class SessionLadder:
    """`brain.models.calls.Ladder` over the application's sessions."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def current(self, now: datetime) -> LadderState:
        """The rungs, the switches and the recent attempts, in one session.

        A read that fails is no rungs and every provider off, together, so no part of a ladder
        half read can reach a plan. See `A_SWITCH_NOBODY_COULD_READ_IS_OFF`.
        """
        try:
            async with self.sessions() as session:
                rows = (await session.execute(live_rungs())).scalars().all()
                states = await switch_states(session)
                found = (await session.execute(recent_attempts(now - EVIDENCE_WINDOW))).all()
                registered = (await session.execute(live_providers())).scalars().all()
                tiers = (await session.execute(live_tiers())).scalars().all()
                constraints = (await session.execute(live_constraints())).scalars().all()
                rings = (await session.execute(stored_rings())).scalars().all()
        except Exception as exc:
            log.warning("models.ladder_unreadable", error=type(exc).__name__)
            return LadderState(rungs=(), switched_off=frozenset(KNOWN_PROVIDERS), attempts=())
        providers = tuple(
            record for record in (provider_record_of(row) for row in registered) if record
        )
        return LadderState(
            providers=providers,
            tiers=tier_rules_of(tiers),
            residency=tuple(
                found for found in (constraint_of(row) for row in constraints) if found
            ),
            rings=tuple(rings_of(row) for row in rings),
            rungs=tuple(ladder_rung_of(row) for row in rows),
            switched_off=switched_off_in(states),
            attempts=tuple(
                Attempt(deployment_id=deployment, finished_at=at, outcome=outcome)
                for deployment, at, outcome in found
                # Both are tested in the statement; the columns are nullable, so the types are.
                if at is not None and outcome is not None
            ),
        )


class NoLadder:
    """The ladder of a process with no database: nothing to call, and nothing switched."""

    async def current(self, now: datetime) -> LadderState:
        """No rungs, so every call finds nothing configured."""
        return LadderState(rungs=(), switched_off=frozenset(), attempts=())


class SessionAttempts:
    """`brain.models.calls.AttemptLog` over `ops.model_attempt`."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def started(
        self,
        *,
        trace_id: str,
        rung_id: str,
        sequence: int,
        at: datetime,
        categories: tuple[str, ...] = (),
    ) -> str:
        """Insert the in-flight row and return its id, or an empty token when it was not kept."""
        try:
            async with self.sessions() as session:
                found = await session.execute(
                    attempt_started(trace_id, rung_id, sequence, at, categories)
                )
                kept = found.scalar_one()
                await session.commit()
        except Exception as exc:
            # See A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT.
            log.warning("models.attempt_unrecorded", trace_id=trace_id, error=type(exc).__name__)
            return ""
        return str(kept)

    async def finished(self, token: str, *, at: datetime, outcome: str, status: int | None) -> None:
        """Finish the row by its id. An empty token was never written, so nothing is finished."""
        if not token:
            return
        try:
            async with self.sessions() as session:
                await session.execute(attempt_finished(token, at, outcome, status))
                await session.commit()
        except Exception as exc:
            log.warning("models.attempt_unfinished", error=type(exc).__name__)


class NoAttempts:
    """The attempt log of a process with no database. Writes nothing."""

    async def started(
        self,
        *,
        trace_id: str,
        rung_id: str,
        sequence: int,
        at: datetime,
        categories: tuple[str, ...] = (),
    ) -> str:
        """Nothing to write to."""
        return ""

    async def finished(self, token: str, *, at: datetime, outcome: str, status: int | None) -> None:
        """Nothing to finish."""
        return None


# ------------------------------------------------------------------------ the service


@dataclass(frozen=True)
class ModelService:
    """What `app.state.models` holds: the executor, and the client the lifespan closes."""

    calls: ModelCalls
    client: httpx.Client

    def close(self) -> None:
        self.client.close()


def drivers_for(
    client: httpx.Client,
    *,
    inference_address: str,
    make_transport: Callable[..., Any] = http_transport,
) -> dict[str, ModelDriver]:
    """One driver per provider this product can reach, and the local one when its address is usable.

    A hosted provider's driver is built whether or not a key is held, because a key can arrive
    while the process runs; assembly leaves the rung out until it does. The local server's is
    built only when `endpoint_refusals` has nothing to say about the address, so a rung naming
    it on an install with an unusable address is told so rather than dialling it.
    """
    drivers: dict[str, ModelDriver] = {
        slug: SdkDriver(provider=slug, transport=make_transport(wire, client=client))
        for slug, wire in PROVIDER_WIRES.items()
    }
    if not endpoint_refusals(inference_address):
        drivers[LOCAL_PROVIDER] = SdkDriver(
            provider=LOCAL_PROVIDER,
            transport=make_transport(local_wire(inference_address), client=client),
        )
    return drivers


class AddedProviderDrivers:
    """`brain.models.calls.AddedProviders` over this process's HTTP client and environment.

    A driver per added provider, built the first time its row is seen and rebuilt only when the
    row's address differs, which it can only by the provider being removed and added again. The
    slots are handed to `slots` on every read, which is how the key refresh learns them.
    """

    def __init__(
        self,
        client: httpx.Client,
        *,
        slots: AddedProviderSlots = PROCESS_ADDED_SLOTS,
        make_transport: Callable[..., Any] = http_transport,
    ) -> None:
        self._client = client
        self._slots = slots
        self._make_transport = make_transport
        self._lock = threading.Lock()
        self._built: dict[str, tuple[str, ModelDriver]] = {}

    def drivers(self, records: Sequence[ProviderRecord]) -> Mapping[str, ModelDriver]:
        """A driver for each added provider, and this process told their slots."""
        added = [one for one in records if one.kind is ProviderKind.OPENAI_COMPATIBLE]
        self._slots.learn(one.slug for one in added)
        found: dict[str, ModelDriver] = {}
        with self._lock:
            for one in added:
                if one.base_url is None:  # pragma: no cover - the record refuses it
                    continue
                known = self._built.get(one.slug)
                if known is None or known[0] != one.base_url:
                    wire = added_wire(one.slug, one.base_url, added_slot(one.slug))
                    driver = SdkDriver(
                        provider=one.slug,
                        transport=self._make_transport(wire, client=self._client),
                    )
                    known = (one.base_url, driver)
                    self._built[one.slug] = known
                found[one.slug] = known[1]
        return found

    def held(self, records: Sequence[ProviderRecord]) -> frozenset[str]:
        """The added providers whose variable this process's environment sets. Names only."""
        slots = [
            added_slot(one.slug) for one in records if one.kind is ProviderKind.OPENAI_COMPATIBLE
        ]
        return held_providers(slots)


def wall_clock() -> datetime:
    return datetime.now(UTC)


def model_service_at_start(
    sessions: async_sessionmaker[AsyncSession] | None,
    *,
    client: httpx.Client | None = None,
) -> ModelService:
    """The executor this process calls models through. Never raises.

    The inference address is read once, here, because it names where a driver dials and the
    driver is built once. The profile and the keys are read per call. Without a database there
    is no ladder, so every call finds no model configured, which is the honest answer on such a
    process.
    """
    owned = client if client is not None else httpx.Client(follow_redirects=False)
    try:
        address = value_of(ENDPOINT_SETTING)
    except Exception as exc:
        log.warning("models.inference_address_unreadable", error=type(exc).__name__)
        address = ""
    drivers = drivers_for(owned, inference_address=address)
    calls = ModelCalls(
        ladder=SessionLadder(sessions) if sessions is not None else NoLadder(),
        attempts=SessionAttempts(sessions) if sessions is not None else NoAttempts(),
        drivers=drivers,
        profile=lambda: value_of("INSTALL_MODEL_PROFILE"),
        held=held_providers,
        clock=wall_clock,
        added=AddedProviderDrivers(owned),
        health=SessionHealth(sessions) if sessions is not None else None,
        alerts=SessionDepthAlerts(sessions),
    )
    log.info(
        "model drivers built",
        providers=sorted(drivers),
        ladder="database" if sessions is not None else "none",
    )
    return ModelService(calls=calls, client=owned)
