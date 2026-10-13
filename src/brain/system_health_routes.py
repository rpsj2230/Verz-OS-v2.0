"""The System health screen over HTTP: what each part this install depends on is doing now, and
which of its guarantees are held.

`docs/admin-console-architecture.md` F1 names this screen: readiness, the worker, the vault, object
storage, the identity provider, the breakers, and the state of every control that keeps a
guarantee. `GET /health/ready` answers the first of those to anybody and to a machine; the
Overview's strip says a word about it. Nothing answered the rest in one place, so an owner whose
worker had stopped, or whose vault had sealed, found out from a question that failed.

**Held to the Incidents screen at company scope, and one refusal for everything else.** F1 says
"to build a read on the registry's `incidents` screen, company console only". The screen's own
read is asked first, then `held_across_the_install`: a reader who holds Incidents over one
department is told nothing about the vault or the worker, because those are the whole
installation's and not that department's. Every refusal is one answer, so the refusal says
nothing about which half failed. See `SYSTEM_HEALTH_IS_THE_WHOLE_INSTALLATION_S_OR_NOTHING`.

**Every part says what it measured and names what it did not.** A part is one of `ready`,
`not_ready`, `not_configured` or `unknown`, and `unknown` is a part this process has no way to ask:
a process with no database cannot say when the worker last ran, and says so in a sentence. Nothing
here turns a failure to look into a green tick, which is `brain.install_routes.
AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE`'s rule applied to a health screen.

**What each part reads.**

- Readiness parts: `brain.console_overview_routes.readiness`, which is `/health/ready` computed as
  that route computes it, so the two cannot disagree.
- The worker: the newest start or finish of any scheduled run, the evidence the Overview strip uses
  (`worker_last_seen`), over every control because the reader holds the installation.
- The vault: `brain.ops.vault_status.seal_of`, the same four answers the Credentials screen gives,
  asked in a worker thread because the client blocks.
- Object storage: whether the client the process built at start is connected, or the sentence it
  gave for why not. **That is "connected at start" and the screen says so**: no request is made to
  the bucket here, and a store that was reachable at start and is not now is not detected.
- Breakers: each live rung's breaker as `brain.provider_routes.breaker_states` reports it, for a
  reader who may also read the Models screen, and absent with a sentence for one who may not.
- Guarantees: `brain.ops.guarantee_state.guarantees`, the register of controls read against the
  scheduler's record of successful runs. A guarantee whose control is unreachable, never run or
  behind is **not held**, and so is every guarantee when the record could not be read. See
  `brain.ops.guarantee_state.A_GUARANTEE_IS_NOT_HELD_ON_EVIDENCE_THAT_COULD_NOT_BE_READ`.

Rejected: a screen of its own in the registry. F1 puts this beside Incidents on purpose: a person
who has an incident wants the health in the same place, and a second registry entry would be a
second grant to keep in step with the first.

Task ids: M27.13.2, M27.15.54
"""

from __future__ import annotations

import asyncio
import enum
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.department_console import held_across_the_install
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console_overview_routes import readiness
from brain.core.errors import Absent
from brain.credential_routes import reader_of
from brain.jobs_routes import last_run_of_each_control
from brain.ops.guarantee_state import Guarantee, guarantees
from brain.ops.schedule import schedulable
from brain.ops.schedule_store import last_successes
from brain.ops.vault_status import SEAL_SAYS, Seal, seal_of
from brain.provider_routes import breaker_states
from brain.readiness import PartState
from brain.routing_routes import sessions_of

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a reader of one department is refused.
SYSTEM_HEALTH_IS_THE_WHOLE_INSTALLATION_S_OR_NOTHING: Final = (
    "The vault, the worker and the guarantees are the installation's and belong to no department, "
    "so a reader holding the Incidents screen over one department is refused as a person with no "
    "Incidents screen at all, and the refusal does not say which of the two it was."
)

#: The screen this route answers through.
INCIDENTS_SCREEN: Final = "incidents"

#: Where the screen is read.
SYSTEM_HEALTH_PATH: Final = "/console/system-health"

#: Said in place of the worker when no database can be read.
NOTHING_HERE_READS_THE_RUNS: Final = (
    "This process has no database, so it cannot say when the worker last ran or whether any "
    "guarantee is held. Nothing here is a statement that the worker is running."
)

#: What object storage is, said once, because it is the one part measured only at start.
OBJECT_STORE_IS_ASKED_AT_START: Final = (
    "Whether a client for the object store was built when this process started. Nothing asks the "
    "bucket now, so a store that has since gone away is not shown here."
)

#: Said in place of the breakers for a reader who may not read the Models screen.
BREAKERS_BELONG_TO_THE_MODELS_SCREEN: Final = (
    "Breakers are read on the Models screen, which this reader does not hold, so none are shown "
    "here."
)

#: Said in place of the breakers when the model service could not be read.
BREAKERS_COULD_NOT_BE_READ: Final = (
    "The model providers' breakers could not be read by this process just now, which is not a "
    "statement that none is open."
)


class Standing(enum.StrEnum):
    """Where a part stands. `unknown` is a part nothing here could ask, never a healthy one."""

    READY = "ready"
    NOT_READY = "not_ready"
    NOT_CONFIGURED = "not_configured"
    UNKNOWN = "unknown"


class PartView(BaseModel):
    """One part and what was measured of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    state: Standing
    #: Whether this part decides `/health/ready`.
    gates: bool = False
    said: str = ""


class WorkerView(BaseModel):
    """The worker as the scheduled runs show it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: Standing
    last_seen: datetime | None = None
    said: str


class BreakerView(BaseModel):
    """One live rung's breaker, as the Models screen draws it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: str
    provider: str
    model: str
    #: `closed`, `open` or `half_open`.
    state: str
    #: Whether any attempt stands behind `state`. A breaker nothing has measured says closed.
    measured: bool


class GuaranteeView(BaseModel):
    """One protection and whether the control that keeps it is running."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    control: str
    guards: str
    held: bool
    #: Why not, as `brain.ops.controls.Missed` words it, or empty when held.
    because: str = ""
    said: str


class SystemHealthView(BaseModel):
    """The System health screen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: datetime
    status: str
    parts: list[PartView]
    worker: WorkerView
    vault: PartView
    object_store: PartView
    #: The live rungs' breakers, or None with `breakers_said` for a reader who may not see them.
    breakers: list[BreakerView] | None
    breakers_said: str = ""
    guarantees: list[GuaranteeView]
    #: Why the guarantees could not all be judged, or empty. Never a statement that they hold.
    guarantees_said: str = ""


router = APIRouter(prefix=API_PREFIX, tags=["operate"])


def _not_answerable() -> Absent:
    """The one refusal this screen makes, as the Incidents screen makes it."""
    return Absent(f"the {INCIDENTS_SCREEN} screen is not answerable for this caller")


def _standing(state: PartState) -> Standing:
    return {
        PartState.READY: Standing.READY,
        PartState.NOT_READY: Standing.NOT_READY,
        PartState.NOT_CONFIGURED: Standing.NOT_CONFIGURED,
    }[state]


async def _vault_part(request: Request) -> PartView:
    seal = await asyncio.to_thread(seal_of, reader_of(request))
    state = {
        Seal.OPEN: Standing.READY,
        Seal.ABSENT: Standing.NOT_CONFIGURED,
        Seal.UNINITIALISED: Standing.NOT_READY,
        Seal.SEALED: Standing.NOT_READY,
        Seal.UNREACHABLE: Standing.NOT_READY,
    }[seal]
    return PartView(name="vault", state=state, said=SEAL_SAYS[seal])


def _object_store_part(request: Request) -> PartView:
    store = getattr(request.app.state, "object_store", None)
    backend = getattr(store, "backend", None)
    if store is None:
        return PartView(
            name="object_store",
            state=Standing.UNKNOWN,
            said="This process was built without an object store to ask about.",
        )
    if backend is None:
        reason = str(getattr(store, "unconnected", "")) or "no reason was given"
        return PartView(name="object_store", state=Standing.NOT_CONFIGURED, said=reason)
    return PartView(name="object_store", state=Standing.READY, said=OBJECT_STORE_IS_ASKED_AT_START)


async def _worker_and_guarantees(
    request: Request, asked: Asked
) -> tuple[WorkerView, list[GuaranteeView], str]:
    factory = sessions_of(request)
    if factory is None:
        lapsed = guarantees(None, asked.now)
        return (
            WorkerView(state=Standing.UNKNOWN, said=NOTHING_HERE_READS_THE_RUNS),
            [_guarantee_view(one) for one in lapsed],
            NOTHING_HERE_READS_THE_RUNS,
        )
    try:
        async with factory() as session:
            rows = [
                one._tuple() for one in (await session.execute(last_run_of_each_control())).all()
            ]
            succeeded = await last_successes(session)
    except Exception:
        # Broad: whatever stopped the read, the answer is not that the worker is fine.
        log.warning("system health could not read the runs")
        lapsed = guarantees(None, asked.now)
        return (
            WorkerView(state=Standing.UNKNOWN, said=NOTHING_HERE_READS_THE_RUNS),
            [_guarantee_view(one) for one in lapsed],
            NOTHING_HERE_READS_THE_RUNS,
        )
    instants = [moment for _, started, finished, *_ in rows for moment in (started, finished)]
    seen = max((one for one in instants if one is not None), default=None)
    worker = (
        WorkerView(
            state=Standing.UNKNOWN,
            said="No scheduled run has been recorded, so nothing here says the worker has run.",
        )
        if seen is None
        else WorkerView(
            state=Standing.READY,
            last_seen=seen,
            said="The newest scheduled run, started or finished.",
        )
    )
    # A control the scheduler records and that has never succeeded is `never_run`, not unrecorded:
    # its runs are in the table, and there is no success among them.
    recorded = {one.name: succeeded.get(one.name) for one in schedulable()}
    states = guarantees({**recorded, **dict(succeeded)}, asked.now)
    return worker, [_guarantee_view(one) for one in states], ""


def _guarantee_view(one: Guarantee) -> GuaranteeView:
    return GuaranteeView(
        control=one.control,
        guards=one.guards,
        held=one.held,
        because="" if one.because is None else one.because.value,
        said=one.said,
    )


async def _breakers(request: Request, asked: Asked) -> tuple[list[BreakerView] | None, str]:
    try:
        rungs = await breaker_states(request, asked)
    except Exception:
        # Broad: a model service that cannot be built here is not a closed breaker.
        log.warning("system health could not read the breakers")
        return None, BREAKERS_COULD_NOT_BE_READ
    if rungs is None:
        return None, BREAKERS_BELONG_TO_THE_MODELS_SCREEN
    return (
        [
            BreakerView(
                tier=one.tier,
                provider=one.provider,
                model=one.model,
                state=one.state.value,
                measured=one.measured,
            )
            for one in rungs
        ],
        "",
    )


@router.get(SYSTEM_HEALTH_PATH, response_model=SystemHealthView, responses=COMMON_RESPONSES)
async def system_health(request: Request, asked: Asked) -> SystemHealthView:
    """Every part, the worker, the vault, object storage, the breakers and each guarantee.

    The Incidents screen's read, then the whole installation, then every read; see the module.
    """
    found = screen(INCIDENTS_SCREEN)
    if not permitted(found.read, asked.reach, asked.now) or not held_across_the_install(
        found, asked.reach, asked.now
    ):
        log.info("system health not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    status, parts = await readiness(request)
    worker, kept, kept_said = await _worker_and_guarantees(request, asked)
    breakers, breakers_said = await _breakers(request, asked)
    return SystemHealthView(
        as_of=asked.now,
        status=status,
        parts=[
            PartView(name=one.name, state=_standing(one.state), gates=one.gates) for one in parts
        ],
        worker=worker,
        vault=await _vault_part(request),
        object_store=_object_store_part(request),
        breakers=breakers,
        breakers_said=breakers_said,
        guarantees=kept,
        guarantees_said=kept_said,
    )
