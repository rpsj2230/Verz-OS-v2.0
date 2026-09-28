"""Running the acceptance checks on this install, and the harness every check is handed.

`brain.ops.acceptance` says what a check is and what its result may say; this is the half that
opens a connection. The worker's schedule starts `run_acceptance_now` through
`brain.ops.schedule_runner`, once per newly deployed commit and whenever a Super Admin presses run
now on the Scheduled jobs screen, and it writes one row per check to `ops.acceptance_result`.

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
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final, TextIO

from sqlalchemy import func, insert, select, text, update
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
    CheckNotRunError,
    Occasion,
    Result,
    owed,
    reason_for,
    registered,
    summary,
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

#: The owner's two test logins, by the installation setting holding each one's subject: the user
#: ID the identity provider shows on the user's own page, which is the `sub` its tokens carry.
TEST_LOGINS: Final = {
    "member": "INSTALL_ACCEPTANCE_MEMBER_SUBJECT",
    "head": "INSTALL_ACCEPTANCE_HEAD_SUBJECT",
}

#: What a setting says when nobody has named the login yet, as `brain.install` declares it.
UNSET: Final = "unset"

#: Why a check acting as a person is not run, until the owner names his two test logins.
WAITING_FOR_THE_TWO_TEST_LOGINS: Final = "waiting for the two test logins"

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
    ) -> None:
        self.run = run
        self.now = now
        self.settings = settings
        self.connection = connection
        self.sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
            autoflush=False,
            sync_session_class=ApplicationRoleSession,
        )
        self._undo: list[Callable[[], object]] = []
        #: Test logins' principals placed in a reserved department for this check.
        self._placed: set[str] = set()

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
        """Found both reserved departments through the product's own structure store."""
        from brain.console.organisation import founded
        from brain.identity.organisation_store import Attribution, StoredOrganisation

        store = StoredOrganisation(self.sessions)
        by = Attribution(actor=self.actor, ent_hash=SET_UP_REACH, trace_id=self.trace_id)
        for slug in RESERVED_DEPARTMENTS:
            department, scope = founded(slug, f"Acceptance check {slug[-1].upper()}")
            done = await store.found_department(department=department, scope=scope, by=by)
            if not isinstance(done, datetime):
                raise CheckFailedError("a reserved department could not be founded")

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
        """One grant to a reserved principal or a test login's, lapsing with the check."""
        if (
            not principal_id.startswith(RESERVED_PRINCIPAL_PREFIX)
            and principal_id not in self._placed
        ):
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

    async def test_login(
        self,
        login: str,
        *,
        department: str,
        grants: Sequence[tuple[str, Scope]] = (),
    ) -> str:
        """The person one of the owner's two test logins signs in as, placed in `department`.

        The login's subject is configuration (`TEST_LOGINS`), and without it the check waits:
        `WAITING_FOR_THE_TWO_TEST_LOGINS`. A subject nothing is bound to yet is bound, through
        the product's own `SignInBindings.bind`, to a reserved principal made for this check; a
        subject already bound keeps its principal, placed in `department` for the check. Either
        way the principal is then resolved through `StoredDirectory.principal_for_subject`,
        which is the lookup a sign-in makes, and all of it is rolled back with the check.
        """
        from brain.identity.principal_directory import StoredDirectory
        from brain.identity.sign_in_binding import sign_in_bindings
        from brain.install import value_of

        subject = value_of(TEST_LOGINS[login]).strip()
        if subject in ("", UNSET):
            raise CheckNotRunError(WAITING_FOR_THE_TWO_TEST_LOGINS)
        bindings = sign_in_bindings(self.sessions)
        directory = StoredDirectory(self.sessions)
        found = await directory.principal_for_subject(bindings.issuer, subject)
        if found is None:
            made = self.principal(department, login)
            await self.person(made, department=department)
            await bindings.bind(
                subject,
                principal_id=made,
                bound_by=self.actor,
                now=self.now,
                trace_id=self.trace_id,
            )
            found = await directory.principal_for_subject(bindings.issuer, subject)
            if found is None or found.id != made:
                raise CheckFailedError("a test login did not resolve to the person it was bound to")
        else:
            await self.execute(
                *self.attributed(),
                update(PrincipalRow)
                .where(PrincipalRow.id == found.id)
                .values(primary_department=department),
            )
            self._placed.add(found.id)
        for capability, scope in grants:
            await self.grant(found.id, capability, scope)
        return found.id

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
) -> tuple[str, str]:
    """One check in its own rolled-back transaction: its outcome and stored reason."""
    async with engine.connect() as connection:
        outer = await connection.begin()
        harness = Harness(run=run, now=datetime.now(UTC), settings=settings, connection=connection)
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
) -> tuple[Result, ...]:
    """Every check, each in its own transaction, or every check not run if the run may not start."""
    run = run or secrets.token_hex(4)
    if await in_use(engine, stream):
        at = datetime.now(UTC)
        return tuple(
            Result(
                one.name,
                one.leaves,
                NOT_RUN,
                at,
                A_RESERVED_DEPARTMENT_HOLDING_A_REAL_PERSON_STOPS_THE_RUN[:240],
            )
            for one in checks
        )
    results: list[Result] = []
    for one in checks:
        outcome, reason = await run_one(engine, one, run=run, settings=settings, stream=stream)
        results.append(Result(one.name, one.leaves, outcome, datetime.now(UTC), reason))
    return tuple(results)


# ------------------------------------------------------------------------ recording
async def occasion_now(engine: AsyncEngine, *, serving: str) -> Occasion | None:
    """Whether this commit is owed a run, or a person asked for one since the last."""
    from brain.ops.schedule_control import request_states, requested_at

    sessions = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with sessions() as session:
        checked = (
            await session.execute(
                select(AcceptanceResultRow.commit)
                .where(AcceptanceResultRow.commit == serving)
                .limit(1)
            )
        ).scalars()
        last = (await session.execute(select(func.max(AcceptanceResultRow.started_at)))).scalar()
        request = (await request_states(session)).get(CONTROL)
        await session.rollback()
    return owed(
        serving=serving,
        checked=tuple(checked),
        asked_at=None if request is None else requested_at(request),
        last_started=last,
    )


async def record(
    engine: AsyncEngine,
    results: Sequence[Result],
    *,
    commit: str,
    occasion: Occasion,
    started_at: datetime,
    run_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Append one row per result, committed together, and say which run they belong to."""
    run_id = run_id or uuid.uuid4()
    if not results:
        return run_id
    async with engine.begin() as connection:
        await connection.execute(
            insert(AcceptanceResultRow),
            [
                {
                    "run_id": run_id,
                    "commit": commit,
                    "occasion": occasion.value,
                    "check_name": one.name,
                    "leaves": " ".join(one.leaves),
                    "outcome": one.outcome,
                    "reason": one.reason or None,
                    "started_at": started_at,
                    "checked_at": max(one.checked_at, started_at),
                }
                for one in results
            ],
        )
    return run_id


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
    """Run the suite when it is owed, or when `force`d from a shell, and record it; what was
    owed, and what each check came to."""
    out = stream or sys.stderr
    engine = make_engine(database_url)
    try:
        occasion = Occasion.REQUEST if force else await occasion_now(engine, serving=commit)
        if occasion is None:
            return None, ()
        started_at = datetime.now(UTC)
        results = await run_suite(
            engine, registered() if checks is None else checks, settings=settings, stream=out
        )
        await record(engine, results, commit=commit, occasion=occasion, started_at=started_at)
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
        return f"acceptance: {commit} is checked already and nobody has asked since"
    said = f"acceptance {commit} ({occasion.value}): {summary(results)}"
    if any(one.outcome == FAILED for one in results):
        raise AcceptanceChecksFailedError(said)
    return said


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
