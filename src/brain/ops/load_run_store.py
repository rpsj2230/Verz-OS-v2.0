"""Where a peak load run's result is kept: one `ops.setting` row a run, in the install's database.

`brain.ops.load_peak` drives an install and judges what came back. A verdict printed to a terminal
is a verdict that goes with the terminal, and the task asks for the result to be recorded against
the service levels (M22.3.3), so the run keeps what it measured here, where the install's own
checks and any later screen read it, through the same row-and-ledger path every other setting
takes.

**`ops.setting`, one row for each run, and not a table.** The same argument
`brain.ops.setting_store` makes for a switch: a table of its own needs a migration, a row-level
security policy and a registration, to hold a handful of rows a person produces by running a
command on purpose. The key is `load_test.run_<id>`, so a run never overwrites another and the
history is the rows. Every write appends a ledger entry naming the key and the writer
(`brain.ops.setting_store.A_SWITCH_SHOWS_ITS_LAST_CHANGE_AND_THE_LEDGER_KEEPS_EVERY_ONE`).
Rejected: overwriting one `last run` row, which would let a good run erase the evidence of a bad
one; and a table, for the reason above.

**A record is figures and verdicts and never a person or a question.** `RunRecord` has no field
that could hold a token, a principal, a question or an answer, so a record cannot leak what a run
asked or as whom. The findings are the sentences `brain.ops.reliability.attainment` and
`brain.ops.load_peak` write, which carry a lane name and numbers.

**A run that was smaller than the stated peak says so on the record.** `at_stated_peak` is true
only for a run that reached the profile's stated arrival rate for its whole length and sent every
arrival it planned. A bounded run that held is evidence the machinery works and nothing more, and
a record that said `held` without saying how much was driven would be read as the peak test.

**The switch is read here, by one function that asks.** `load_test_is_on` is the feature's reader
(`brain.ops.features_declared.load_test`); the command reads it before it sends anything.

Task ids: M22.3.3
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from brain.ops.features import is_on
from brain.ops.features_declared.load_test import LOAD_TEST
from brain.ops.setting_store import SettingState, put, read_namespace
from brain.tables.audit import attributed_to
from brain.tables.config import SettingType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

#: The namespace every run's row sits under.
NAMESPACE: Final = "load_test"

#: Who a run's row is attributed to in the ledger: the command, not a person's name.
WRITER: Final = "load_peak.command"

#: The row's own description, the product's sentence for it.
DESCRIPTION: Final = (
    "What one peak load run measured on this install: the profile it was driven at, what it sent, "
    "each lane's 95th percentile and success rate, and whether the service levels held."
)

#: Why a run is kept as figures only.
A_RECORD_NAMES_NO_ONE_AND_NO_QUESTION: Final = (
    "A run's record holds counts, times, rates and the sentences that compare them with the "
    "service levels. It has no field for a token, a person, a question or an answer, because a "
    "page that shows it must not be able to show what the run asked or as whom."
)


class RunStoreError(Exception):
    """Raised for a record that cannot be a run's or a key that cannot be a row."""


@dataclass(frozen=True)
class LaneFigures:
    """What one lane did over a run, as kept."""

    lane: str
    requests: int
    p95_ms: float | None
    success_rate: float | None
    shed: int

    def as_value(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "requests": self.requests,
            "p95_ms": self.p95_ms,
            "success_rate": self.success_rate,
            "shed": self.shed,
        }


@dataclass(frozen=True)
class RunRecord:
    """One run's measured result. No person, no token and no question: see
    `A_RECORD_NAMES_NO_ONE_AND_NO_QUESTION`."""

    run_id: str
    commit: str
    profile: str
    started_at: datetime
    seconds_run: float
    stated_arrivals_per_second: float
    stated_in_flight: float
    arrivals_per_second: float
    planned: int
    sent: int
    not_sent: int
    most_in_flight: int
    people: int
    at_stated_peak: bool
    held: bool
    interactive_shed: int
    lanes: tuple[LaneFigures, ...]
    findings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.run_id or not self.run_id.isalnum() or self.run_id != self.run_id.lower():
            msg = "a run's id is lowercase letters and digits, so it can end a setting key"
            raise RunStoreError(msg)
        if self.sent < 0 or self.not_sent < 0 or self.planned < 0:
            msg = "a run cannot have sent, skipped or planned a negative number of requests"
            raise RunStoreError(msg)

    @property
    def key(self) -> str:
        return f"{NAMESPACE}.run_{self.run_id}"

    def as_value(self) -> dict[str, Any]:
        """The row's value: JSON, with the instant as text."""
        return {
            "run_id": self.run_id,
            "commit": self.commit,
            "profile": self.profile,
            "started_at": self.started_at.astimezone(UTC).isoformat(),
            "seconds_run": self.seconds_run,
            "stated_arrivals_per_second": self.stated_arrivals_per_second,
            "stated_in_flight": self.stated_in_flight,
            "arrivals_per_second": self.arrivals_per_second,
            "planned": self.planned,
            "sent": self.sent,
            "not_sent": self.not_sent,
            "most_in_flight": self.most_in_flight,
            "people": self.people,
            "at_stated_peak": self.at_stated_peak,
            "held": self.held,
            "interactive_shed": self.interactive_shed,
            "lanes": [one.as_value() for one in self.lanes],
            "findings": list(self.findings),
        }


def record_from(value: object) -> RunRecord | None:
    """A stored value read back as a record, or None when it is not the shape a run writes.

    Defensive, because the row is in a table somebody with a database prompt can write: a value of
    the wrong shape is no record rather than a reason to believe one.
    """
    if not isinstance(value, dict):
        return None
    try:
        lanes = tuple(
            LaneFigures(
                lane=str(one["lane"]),
                requests=int(one["requests"]),
                p95_ms=None if one["p95_ms"] is None else float(one["p95_ms"]),
                success_rate=None if one["success_rate"] is None else float(one["success_rate"]),
                shed=int(one["shed"]),
            )
            for one in value["lanes"]
        )
        return RunRecord(
            run_id=str(value["run_id"]),
            commit=str(value["commit"]),
            profile=str(value["profile"]),
            started_at=datetime.fromisoformat(str(value["started_at"])),
            seconds_run=float(value["seconds_run"]),
            stated_arrivals_per_second=float(value["stated_arrivals_per_second"]),
            stated_in_flight=float(value["stated_in_flight"]),
            arrivals_per_second=float(value["arrivals_per_second"]),
            planned=int(value["planned"]),
            sent=int(value["sent"]),
            not_sent=int(value["not_sent"]),
            most_in_flight=int(value["most_in_flight"]),
            people=int(value["people"]),
            at_stated_peak=value["at_stated_peak"] is True,
            held=value["held"] is True,
            interactive_shed=int(value["interactive_shed"]),
            lanes=lanes,
            findings=tuple(str(one) for one in value["findings"]),
        )
    except (KeyError, TypeError, ValueError, RunStoreError):
        return None


async def load_test_is_on(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether this install lets a peak load run be started. Off until somebody turns it on."""
    async with sessions() as session:
        return await is_on(session, LOAD_TEST)


async def keep_run(session: AsyncSession, record: RunRecord) -> None:
    """Write one run's row in the caller's transaction, attributed to the command.

    The caller commits.
    """
    for statement in attributed_to(
        actor_id=WRITER, ent_hash="0" * 32, trace_id=f"load-test-{record.run_id}"
    ):
        await session.execute(statement)
    await put(
        session,
        record.key,
        value_type=SettingType.JSON,
        value=record.as_value(),
        description=DESCRIPTION,
        updated_by=WRITER,
    )


def runs_in(held: dict[str, SettingState]) -> tuple[RunRecord, ...]:
    """The runs among a namespace's rows, newest first. A row that is not a run is skipped."""
    found = [
        record_from(one.value) for key, one in held.items() if key.startswith("load_test.run_")
    ]
    return tuple(
        sorted((one for one in found if one is not None), key=lambda r: r.started_at, reverse=True)
    )


async def read_runs(session: AsyncSession) -> tuple[RunRecord, ...]:
    """Every run this install has kept, newest first."""
    return runs_in(await read_namespace(session, NAMESPACE))


# ------------------------------------------------------------------------------- the command's hand
@dataclass(frozen=True)
class Keeper:
    """What the command needs of the install's database: whether the switch is on, a place to keep
    the result, the release it is running, and a way to let go of its connection.

    A value of functions rather than a session, so a test of the command hands it three lambdas
    and no database, and the real one is built once by `database_keeper`.
    """

    switch_is_on: Callable[[], Awaitable[bool]]
    keep: Callable[[RunRecord], Awaitable[None]]
    commit: str
    close: Callable[[], Awaitable[None]]


A_COMMAND_THAT_CANNOT_KEEP_ITS_RESULT_SENDS_NOTHING: Final = (
    "A run spends model calls, so one whose result cannot be kept is a spend with nothing to show. "
    "The command is run where the application runs, with its database in reach, and it looks "
    "before it sends anything: with no database to keep the result in, it refuses."
)


def database_keeper() -> Keeper:
    """The keeper over this process's own database, as the application's owner login.

    Refuses, naming no address, where no database is configured: see
    `A_COMMAND_THAT_CANNOT_KEEP_ITS_RESULT_SENDS_NOTHING`.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    from brain.session import make_session_factory
    from brain.settings import Settings

    settings = Settings()
    url = settings.owner_database_url()
    if not url:
        raise RunStoreError(A_COMMAND_THAT_CANNOT_KEEP_ITS_RESULT_SENDS_NOTHING)
    from brain.db import normalise_database_url

    engine = create_async_engine(normalise_database_url(url))
    sessions = make_session_factory(engine)

    async def switch_is_on() -> bool:
        return await load_test_is_on(sessions)

    async def keep(record: RunRecord) -> None:
        async with sessions() as session, session.begin():
            await keep_run(session, record)

    return Keeper(
        switch_is_on=switch_is_on,
        keep=keep,
        commit=settings.resolved_commit(),
        close=engine.dispose,
    )
