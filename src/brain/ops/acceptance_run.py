"""Running the acceptance checks on this install, and the harness every check is handed.

`brain.ops.acceptance` says what a check is and what its result may say; this is the half that
opens a connection. The worker's schedule starts `run_acceptance_now` through
`brain.ops.schedule_runner`, once per newly deployed commit and whenever a Super Admin presses run
now on the Scheduled jobs screen, and it writes one row per check to `ops.acceptance_result`.

**A row is written as each check finishes, and a run survives the worker's restart.** A run is
thirty-five minutes and more and every deploy restarts the worker, so rows written at the end were
never written on a busy day, and no task could close. The run is opened in `ops.acceptance_run`
before its first check, each result is appended as it ends, and a worker that finds an unfinished
run of the commit it serves finishes it under the same id, running only what has no result. See
`brain.ops.acceptance_resume`, which says what was rejected and why a heartbeat and not a lock.
`run_acceptance` is the one place a run is marked complete, after its last check.

**Every check is one database transaction, and the transaction is always rolled back.** The
harness opens a connection, begins, and hands the product's services an `async_sessionmaker` bound
to that connection in `create_savepoint` mode: a service that opens a session and commits releases
a savepoint, so its triggers fire, its ledger entries are appended and its policies are checked, as
on any request, and none of it outlives the check. The sessions are the application's own
(`brain.session.ApplicationRoleSession`), so every statement a check or a service sends runs as
`brain_app` under row-level security, which is what a request runs as. See
`brain.ops.acceptance.NOTHING_A_CHECK_WRITES_IS_EVER_COMMITTED`.

Rejected: writing the test department and people, committing, and retiring them at the end. Every
table here retires rather than deletes, so each run would leave a department, its people, their
grants and a ledger chapter behind for good, visible on People, Departments and Audit; a process
killed between the two steps would leave a live department holding grants on a client's install; and
the window in which a real person could be answered from a test document would be the whole run.

**What that costs, measured rather than hoped: a check holds two install-wide locks while it
runs.** Every audited write takes the ledger's advisory lock and every grant bumps
`gate.policy_epoch`, and both are held to the end of the transaction, so a real administrator saving
a grant during a check waits for it. Each check is therefore short and bounded:
`CHECK_TIMEOUT_SECONDS` in Python, and `lock_timeout`, `statement_timeout` and
`idle_in_transaction_session_timeout` on the connection, so the server itself ends a check that
stops answering. See `A_CHECK_HOLDS_THE_INSTALL_S_WRITE_LOCKS_FOR_SECONDS`.

**The run looks before it writes.** `in_use` reads, as the login and past every policy, whether a
department with a reserved name exists, whether anybody who is not a reserved principal is placed
in one, holds a grant over one or is listed in one by a staff source, and whether any reserved
principal was ever committed or bound. Any of those records every check as not run with
`brain.ops.acceptance.A_RESERVED_DEPARTMENT_HOLDING_A_REAL_PERSON_STOPS_THE_RUN`.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
import secrets
import sys
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final, TextIO

from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import Result as SqlResult
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.sql import Executable

from brain.core.entitlement import EntitlementSet
from brain.core.principal import Employment, PrincipalKind
from brain.core.scope import Scope
from brain.ops.acceptance import (
    A_RESERVED_DEPARTMENT_HOLDING_A_REAL_PERSON_STOPS_THE_RUN,
    FAILED,
    NOT_RUN,
    PASSED,
    RESERVED_DEPARTMENTS,
    RESERVED_PRINCIPAL_PREFIX,
    Check,
    CheckFailedError,
    Occasion,
    Result,
    owed,
    reason_for,
    registered,
    summary,
)
from brain.ops.acceptance_resume import (
    abandon,
    beat,
    checked_commits,
    claim,
    finish,
    open_run,
    record_check,
    recorded,
    settle,
    unfinished,
)
from brain.ops.safe_error import describe
from brain.session import ApplicationRoleSession, make_app_engine
from brain.settings import Settings
from brain.tables.acceptance import AcceptanceResultRow
from brain.tables.audit import attributed_to
from brain.tables.gate import CapabilityGrantRow
from brain.tables.identity import PrincipalRow

# ------------------------------------------------------------------ written-down reasons
#: What a check costs the people using the install while it runs.
A_CHECK_HOLDS_THE_INSTALL_S_WRITE_LOCKS_FOR_SECONDS: Final = (
    "An audited write takes the ledger's lock and a grant bumps the policy epoch, and a "
    "rolled-back transaction holds both until it ends. So a check is bounded in Python and on "
    "the server: a lock it cannot take in five seconds, a statement running a minute, or a "
    "transaction idle for three is ended by PostgreSQL, and the check fails rather than making "
    "anybody wait longer."
)

#: Why the run's own failure names nothing.
A_RED_RUN_NAMES_ITS_CHECKS_AND_NOTHING_THEY_READ: Final = (
    "A run with a failing check raises, so the Scheduled jobs screen records the control as failed "
    "the way a red canary run is. Its text is the counts and the names of the failing checks, "
    "which are the product's words; what each check saw went to the worker's log and nowhere else."
)

# ------------------------------------------------------------------------ the figures
#: How often the worker asks whether a run is owed. Restated in `brain.ops.controls`, which cannot
#: import this module: the tables it imports import that registry.
RUN_EVERY: Final = timedelta(minutes=5)

#: The longest one check may take before it is failed and its transaction ended.
CHECK_TIMEOUT_SECONDS: Final = 120.0

#: How long a reserved principal's reach lasts, from the start of its check.
RESERVED_REACH_LASTS: Final = timedelta(hours=1)

#: The server's own bounds on a check's connection. See
#: `A_CHECK_HOLDS_THE_INSTALL_S_WRITE_LOCKS_FOR_SECONDS`.
CONNECTION_BOUNDS: Final = (
    "SET LOCAL lock_timeout = '5s'",
    "SET LOCAL statement_timeout = '60s'",
    "SET LOCAL idle_in_transaction_session_timeout = '180s'",
)

#: The reach hash a set-up write is attributed at. The ledger requires 32 hex characters, and a
#: set-up act is the run's and not a person's, so it carries no reach.
SET_UP_REACH: Final = "0" * 32

#: How a line of the run's own is marked on the worker's stream.
LOG_PREFIX: Final = "  ! acceptance"

#: The control's name in `brain.ops.controls.CONTROLS`, whose run request the run reads.
CONTROL: Final = "acceptance_run"


class AcceptanceChecksFailedError(Exception):
    """A run recorded at least one failed check. Its text is `summary`; see the reason above."""


class Harness:
    """What a check is handed: its run, its clock, the install's settings and its transaction.

    Every write goes through `sessions`, which are joined to the check's transaction and run as
    the application role. `removes` registers the undoing of anything the transaction cannot hold,
    which the run performs when the check ends whatever happened.
    """

    def __init__(
        self,
        *,
        run: str,
        now: datetime,
        settings: Settings,
        connection: AsyncConnection,
        earlier: Mapping[str, tuple[str, str]] | None = None,
    ) -> None:
        self.run = run
        self.now = now
        self.settings = settings
        self.connection = connection
        #: What every check that ran before this one in this run came to, by name: its outcome and
        #: its stored reason. A roll-up check reads it; no other check has a use for it. See
        #: `brain.ops.acceptance_roll_up`.
        self.earlier: Mapping[str, tuple[str, str]] = earlier or {}
        self.sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
            autoflush=False,
            sync_session_class=ApplicationRoleSession,
        )
        self._undo: list[Callable[[], object]] = []
        self._departments_founded = False

    # ------------------------------------------------------------------ names
    @property
    def actor(self) -> str:
        """Who the run's own set-up acts are attributed to in the ledger."""
        return f"{RESERVED_PRINCIPAL_PREFIX}{self.run}.run"

    @property
    def trace_id(self) -> str:
        return f"acceptance-{self.run}"

    def principal(self, department: str, role: str) -> str:
        """A reserved principal's id: the prefix, this run, the department's letter and a role."""
        if department not in RESERVED_DEPARTMENTS:
            msg = f"{department!r} is not a reserved department"
            raise ValueError(msg)
        return f"{RESERVED_PRINCIPAL_PREFIX}{self.run}.{department.rsplit('_', 1)[-1]}.{role}"

    def word(self) -> str:
        """A word nothing on the install holds, so a question about it is only about the check."""
        return f"QZ{secrets.token_hex(8).upper()}"

    # --------------------------------------------------------------- writing
    async def execute(self, *statements: Executable) -> SqlResult[Any]:
        """Run statements as the application role in the check's transaction; the last's result."""
        async with self.sessions() as session:
            result: SqlResult[Any] | None = None
            for statement in statements:
                result = await session.execute(statement)
            await session.commit()
        assert result is not None
        return result

    def attributed(self, actor: str | None = None) -> tuple[Executable, ...]:
        """The three settings a trigger reads, naming `actor` or the run."""
        return attributed_to(
            actor_id=actor or self.actor, ent_hash=SET_UP_REACH, trace_id=self.trace_id
        )

    async def found_departments(self) -> None:
        """Found both reserved departments through the product's own structure store.

        **Founded once per check.** A check that awaits another check's body, as a milestone does
        to show two proofs hold on one install, finds the departments already founded, and
        founding them again is refused by the structure store. The harness is one check's, so the
        flag is as long-lived as its transaction.
        """
        if self._departments_founded:
            return
        from brain.console.organisation import founded
        from brain.identity.organisation_store import Attribution, StoredOrganisation

        store = StoredOrganisation(self.sessions)
        by = Attribution(actor=self.actor, ent_hash=SET_UP_REACH, trace_id=self.trace_id)
        for slug in RESERVED_DEPARTMENTS:
            department, scope = founded(slug, f"Acceptance check {slug[-1].upper()}")
            done = await store.found_department(department=department, scope=scope, by=by)
            if not isinstance(done, datetime):
                raise CheckFailedError("a reserved department could not be founded")
        self._departments_founded = True

    async def person(
        self,
        principal_id: str,
        *,
        department: str,
        grants: Sequence[tuple[str, Scope]] = (),
    ) -> None:
        """A reserved principal placed in a reserved department, holding `grants`. See
        `brain.ops.acceptance.A_RESERVED_PRINCIPAL_CANNOT_SIGN_IN`."""
        if not principal_id.startswith(RESERVED_PRINCIPAL_PREFIX):
            msg = f"{principal_id!r} is not a reserved principal"
            raise ValueError(msg)
        await self.execute(
            *self.attributed(),
            insert(PrincipalRow).values(
                id=principal_id,
                kind=PrincipalKind.HUMAN.value,
                employment=Employment.STAFF.value,
                display_name=f"Acceptance check {principal_id.rsplit('.', 1)[-1]}",
                primary_department=department,
                not_after=self.now + RESERVED_REACH_LASTS,
            ),
        )
        for capability, scope in grants:
            await self.grant(principal_id, capability, scope)

    async def grant(self, principal_id: str, capability: str, scope: Scope) -> None:
        """One grant to a reserved principal, lapsing with it."""
        if not principal_id.startswith(RESERVED_PRINCIPAL_PREFIX):
            msg = f"{principal_id!r} is not a reserved principal"
            raise ValueError(msg)
        await self.execute(
            *self.attributed(),
            insert(CapabilityGrantRow).values(
                principal_id=principal_id,
                capability=capability,
                scope=scope.model_dump(mode="json"),
                granted_by=self.actor,
                reason="Granted by an install acceptance check for the length of the check",
                not_after=self.now + RESERVED_REACH_LASTS,
            ),
        )

    async def reach(self, principal_id: str) -> EntitlementSet:
        """A principal's reach through the one resolver, inside the check's transaction."""
        from brain.gate.entitlement_store import StoredEntitlements

        return await StoredEntitlements(self.sessions).load(principal_id, self.now)

    # ---------------------------------------------------------------- undoing
    def removes(self, undo: Callable[[], object]) -> None:
        """Undo something outside the transaction when the check ends, whatever happened."""
        self._undo.append(undo)

    async def undo(self, stream: TextIO) -> None:
        """Every registered undoing, newest first, each one tried whatever the others did."""
        while self._undo:
            one = self._undo.pop()
            try:
                done = one()
                if isinstance(done, Awaitable):
                    await done
            except Exception as exc:
                print(f"{LOG_PREFIX} could not undo: {describe(exc)}", file=stream)


# ------------------------------------------------------------------- looking first
#: Each question `in_use` asks, as the login, and the refusal it stands for. Named rather than
#: folded into one statement, so a refusal in the log says which door was found open.
IN_USE_QUESTIONS: Final = (
    (
        "a department with a reserved name exists",
        "SELECT 1 FROM gate.department WHERE slug = ANY(:slugs) AND deleted_at IS NULL LIMIT 1",
    ),
    (
        "somebody who is not a reserved principal is placed in a reserved department",
        "SELECT 1 FROM auth.principal WHERE primary_department = ANY(:slugs)"
        " AND deleted_at IS NULL AND left(id, :width) <> :prefix LIMIT 1",
    ),
    (
        "a reserved principal was committed",
        "SELECT 1 FROM auth.principal WHERE left(id, :width) = :prefix LIMIT 1",
    ),
    (
        "a sign-in or channel binding names a reserved principal",
        "SELECT 1 FROM auth.principal_identity WHERE left(principal_id, :width) = :prefix LIMIT 1",
    ),
    (
        "a staff source lists somebody in a reserved department",
        "SELECT 1 FROM auth.staff_member WHERE department = ANY(:slugs) AND left_at IS NULL"
        " LIMIT 1",
    ),
    (
        "somebody holds a grant over a reserved department",
        "SELECT 1 FROM gate.capability_grant WHERE deleted_at IS NULL"
        " AND (position(:quoted_a in scope::text) > 0 OR position(:quoted_b in scope::text) > 0)"
        " LIMIT 1",
    ),
)


async def in_use(engine: AsyncEngine, stream: TextIO) -> bool:
    """Whether a reserved department or principal is in use on this install. See the module."""
    parameters = {
        "slugs": list(RESERVED_DEPARTMENTS),
        "width": len(RESERVED_PRINCIPAL_PREFIX),
        "prefix": RESERVED_PRINCIPAL_PREFIX,
        "quoted_a": f'"{RESERVED_DEPARTMENTS[0]}"',
        "quoted_b": f'"{RESERVED_DEPARTMENTS[1]}"',
    }
    found = False
    async with engine.connect() as connection:
        for said, question in IN_USE_QUESTIONS:
            if (await connection.execute(text(question), parameters)).first() is not None:
                print(f"{LOG_PREFIX} not run: {said}", file=stream)
                found = True
        await connection.rollback()
    return found


# ------------------------------------------------------------------------- running
async def run_one(
    engine: AsyncEngine,
    one: Check,
    *,
    run: str,
    settings: Settings,
    stream: TextIO,
    timeout: float = CHECK_TIMEOUT_SECONDS,
    earlier: Mapping[str, tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """One check in its own rolled-back transaction: its outcome and stored reason."""
    async with engine.connect() as connection:
        outer = await connection.begin()
        harness = Harness(
            run=run,
            now=datetime.now(UTC),
            settings=settings,
            connection=connection,
            earlier=earlier,
        )
        try:
            for bound in CONNECTION_BOUNDS:
                await connection.execute(text(bound))
            await asyncio.wait_for(one.run(harness), timeout=timeout)
            said = (PASSED, "")
        except Exception as exc:
            said = reason_for(exc)
            if said[0] == FAILED:
                print(f"{LOG_PREFIX} {one.name} failed: {describe(exc)}", file=stream)
        finally:
            await harness.undo(stream)
            try:
                await outer.rollback()
            except Exception as exc:
                # The server rolls back a transaction whose connection is gone, so a failed
                # rollback leaves nothing either; it is said so the log does not look clean.
                print(f"{LOG_PREFIX} {one.name} rollback: {describe(exc)}", file=stream)
    return said


async def run_suite(
    engine: AsyncEngine,
    checks: Sequence[Check],
    *,
    settings: Settings,
    stream: TextIO,
    run: str | None = None,
    prior: Sequence[Result] = (),
    before: Callable[[Check], Awaitable[None]] | None = None,
    after: Callable[[Result], Awaitable[None]] | None = None,
) -> tuple[Result, ...]:
    """Every check, each in its own transaction, or every check not run if the run may not start.

    `prior` is what a resumed run recorded before it was interrupted: those checks are not run
    again and not counted twice, their outcomes are what a roll-up check reads as having run
    before it, and they lead the tuple returned. `before` is called ahead of each check and `after`
    with each result as it is known, which is how a run is recorded as it goes
    (`brain.ops.acceptance_resume.A_CHECK_IS_RECORDED_WHEN_IT_FINISHES`).
    """
    run = run or secrets.token_hex(4)
    done = {one.name for one in prior}
    todo = [one for one in checks if one.name not in done]
    results: list[Result] = list(prior)
    came_to: dict[str, tuple[str, str]] = {one.name: (one.outcome, one.reason) for one in prior}
    if todo and await in_use(engine, stream):
        at = datetime.now(UTC)
        for one in todo:
            stopped = Result(
                one.name,
                one.leaves,
                NOT_RUN,
                at,
                A_RESERVED_DEPARTMENT_HOLDING_A_REAL_PERSON_STOPS_THE_RUN[:240],
            )
            results.append(stopped)
            if after is not None:
                await after(stopped)
        return tuple(results)
    for one in todo:
        if before is not None:
            await before(one)
        outcome, reason = await run_one(
            engine, one, run=run, settings=settings, stream=stream, earlier=dict(came_to)
        )
        came_to[one.name] = (outcome, reason)
        result = Result(one.name, one.leaves, outcome, datetime.now(UTC), reason)
        results.append(result)
        if after is not None:
            await after(result)
    return tuple(results)


# ------------------------------------------------------------------------ recording
async def occasion_now(engine: AsyncEngine, *, serving: str) -> Occasion | None:
    """Whether this commit is owed a run, or a person asked for one since the last.

    A commit is checked when a *complete* run of it is recorded
    (`brain.ops.acceptance_resume.ONLY_A_COMPLETE_RUN_COUNTS`): a half-written run is finished by
    `run_acceptance`, which looks for one before it asks this.
    """
    from brain.ops.schedule_control import request_states, requested_at

    sessions = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with sessions() as session:
        last = (await session.execute(select(func.max(AcceptanceResultRow.started_at)))).scalar()
        request = (await request_states(session)).get(CONTROL)
        await session.rollback()
    return owed(
        serving=serving,
        checked=await checked_commits(engine, serving),
        asked_at=None if request is None else requested_at(request),
        last_started=last,
    )


async def run_acceptance(
    database_url: str,
    *,
    settings: Settings,
    commit: str,
    checks: Sequence[Check] | None = None,
    stream: TextIO | None = None,
    make_engine: Callable[[str], AsyncEngine] = make_app_engine,
    force: bool = False,
) -> tuple[Occasion | None, tuple[Result, ...]]:
    """Run the suite when it is owed, or when `force`d from a shell, and record it as it goes; what
    was owed, and what each check came to.

    **Unfinished runs are settled first.** A run of another commit that stopped is abandoned; a run
    of this commit that stopped is taken over and finished under its own id and start, running only
    the checks without a result (`A_RESTARTED_WORKER_FINISHES_THE_RUN_OF_ITS_OWN_RELEASE`); a run of
    this commit that is still beating is left to its worker, and nothing is started beside it. A
    `force`d run is always a fresh one and takes no run over. The returned results of a resumed run
    are the whole run's, those recorded before the interruption first.
    """
    out = stream or sys.stderr
    engine = make_engine(database_url)
    try:
        suite = registered() if checks is None else checks
        settlement = settle(commit, await unfinished(engine))
        abandoned = await abandon(engine, settlement.abandon)
        if abandoned:
            print(
                f"{LOG_PREFIX} {abandoned} unfinished run(s) of another release abandoned", file=out
            )
        taken = settlement.resume
        if taken is not None and (force or not await claim(engine, taken.run_id)):
            taken = None
        prior: tuple[Result, ...] = ()
        if taken is not None:
            run_id, occasion, started_at = taken.run_id, taken.occasion, taken.started_at
            prior = await recorded(engine, run_id)
            print(f"{LOG_PREFIX} resuming a run with {len(prior)} result(s) recorded", file=out)
        else:
            if settlement.in_progress and not force:
                return None, ()
            owed_now = Occasion.REQUEST if force else await occasion_now(engine, serving=commit)
            if owed_now is None:
                return None, ()
            occasion, run_id, started_at = owed_now, uuid.uuid4(), datetime.now(UTC)
            await open_run(
                engine, run_id=run_id, commit=commit, occasion=occasion, started_at=started_at
            )

        async def before(_: Check) -> None:
            await beat(engine, run_id)

        async def after(one: Result) -> None:
            await record_check(
                engine,
                one,
                run_id=run_id,
                commit=commit,
                occasion=occasion,
                started_at=started_at,
            )

        results = await run_suite(
            engine, suite, settings=settings, stream=out, prior=prior, before=before, after=after
        )
        if not await finish(engine, run_id):
            print(f"{LOG_PREFIX} the run was abandoned by another worker before it ended", file=out)
        return occasion, results
    finally:
        await engine.dispose()


def run_acceptance_now(
    database_url: str,
    *,
    settings: Settings,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
    stream: TextIO | None = None,
) -> str:
    """`run_acceptance` from a thread with no event loop of its own, and what it came to.

    The shape `brain.ops.canary_run.run_canaries_now` takes. A run with a failed check raises
    `AcceptanceChecksFailedError` after its rows are written, for
    `A_RED_RUN_NAMES_ITS_CHECKS_AND_NOTHING_THEY_READ`.
    """
    commit = settings.resolved_commit()
    occasion, results = asyncio.run(
        run_acceptance(database_url, settings=settings, commit=commit, stream=stream),
        loop_factory=loop_factory,
    )
    if occasion is None:
        return (
            f"acceptance: nothing is owed on {commit}: it is checked already and nobody has asked "
            "since, or a worker is still running it"
        )
    said = f"acceptance {commit} ({occasion.value}): {summary(results)}"
    if any(one.outcome == FAILED for one in results):
        raise AcceptanceChecksFailedError(said)
    return said


async def hold_what_was_saved(database_url: str) -> None:
    """Hold the installation values saved in the wizard and the console, as the worker does.

    A process started by hand has no lifespan and no schedule, so without this it reads the model
    profile and every other saved value from its environment alone, and a check asking a provider
    finds an install saved as hosted keeping text on its own hardware. The worker reloads them
    before every tick (`brain.ops.worker.THE_WORKER_HOLDS_WHAT_WAS_SAVED_BEFORE_EVERY_TICK`); a
    table that cannot be read is said and the run goes on with the environment's values.
    """
    from brain.ops.install_settings import refresh_changed
    from brain.session import make_session_factory

    engine = make_app_engine(database_url)
    try:
        await refresh_changed(make_session_factory(engine))
    except Exception as exc:
        print(
            f"{LOG_PREFIX} the saved settings could not be read: {describe(exc)}", file=sys.stderr
        )
    finally:
        await engine.dispose()


def main() -> int:
    """Run every check now against this container's database, record it, and print each result.

    `python -m brain.ops.acceptance_run` inside the application or worker container: the same run
    the schedule makes, recorded as asked for, whether or not this commit was checked already.
    Prints the words the Install page shows and nothing a check read.
    """
    settings = Settings()
    if not settings.database_url:
        print(f"{LOG_PREFIX} no database is configured, so nothing was checked", file=sys.stderr)
        return 1
    commit = settings.resolved_commit()
    asyncio.run(hold_what_was_saved(settings.database_url))
    _, results = asyncio.run(
        run_acceptance(settings.database_url, settings=settings, commit=commit, force=True)
    )
    for one in results:
        leaves = " ".join(one.leaves)
        print(f"{one.outcome:8} {one.name} [{leaves}] {one.reason}".rstrip())
    print(f"acceptance {commit}: {summary(results)}")
    return 1 if any(one.outcome == FAILED for one in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
