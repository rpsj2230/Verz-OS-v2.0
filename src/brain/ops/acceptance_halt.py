"""The install acceptance check for the stop button: who may stop what, what it stops, and resume.

One check, over the product's own pieces inside the check's transaction (M27.15.2, M27.15.10,
M27.15.15, M27.15.16). Four reserved people: an administrator holding the stop in acceptance_a
alone, one holding it everywhere, and a member of each department. The Stop screen's routes are
called as their functions, as the threads check calls the thread routes, and the question is
asked through `/answer`'s own function, so nothing here is a second copy of either.

**What is checked.**
- The department administrator stops their own department in one request with no reason, and
  the stop is stored with the console's fixed sentence; they cannot stop the other department or
  everything, and the screen tells them they may not stop everything and that the agent axis is
  asked by nothing.
- Their department's member is told they were stopped, without the reason; the other
  department's member is not.
- A resume with no reason is refused and lifts nothing; a resume with one, by the other
  administrator, lifts it and says it overrides somebody else's stop, and the member is
  admitted again.
- A stop on everything turns a question away in the halt's own sentence before any lane runs.
- Each state is read through a new session and a reader built for the read, and the store holds
  nothing between reads, so what refuses is the table and not the process. The literal restart,
  an engine disposed and another reading back, is `tests/unit/test_halt_store.py`'s, because a
  row only a second connection can see would have to be committed, and `ops.halt` keeps every
  row and ledgers it: a check that committed one would leave two halts and two entries on the
  install every time it ran.
- A database that is configured and cannot be read refuses, in its own sentence.

**Nothing is committed.** Every row, and every ledger entry its trigger writes, is in the check's
transaction and is rolled back with it, so no member of the install is stopped by the check.

Task ids: M27.15.10, M27.15.15, M27.15.16, M27.15.2
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Final, cast

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 403

A, B = RESERVED_DEPARTMENTS

#: Where nothing listens, so a session factory over it is a database configured and unreadable.
NOWHERE: Final = "postgresql+psycopg://nobody@127.0.0.1:1/none"


async def _signed_in_strongly(h: Harness, principal_id: str) -> Any:
    """What the Stop routes read of an administrator signed in with a second factor.

    `brain.ops.acceptance_threads._asking`'s shape at `Assurance.STRONG`, because
    `brain.gate.admission` withholds every `admin:` capability from a sign-in without one, which
    is how an administrator reaches the Stop screen on an install.
    """
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.STRONG)
    # A cast at the routes' boundary, as the threads check makes it: they read these three, and a
    # `Caller` is minted only from a verified token.
    return cast(
        "Any",
        SimpleNamespace(
            caller=SimpleNamespace(principal=person), reach=reach, now=datetime.now(UTC)
        ),
    )


@check(
    leaves=("M27.15.2", "M27.15.10", "M27.15.15", "M27.15.16"),
    sentence=(
        "A department administrator stops their own department in one press with no reason and "
        "nothing wider; its member is told without the reason and the other department is not; "
        "a resume needs a written reason and says whose stop it lifts; a stop on everything turns "
        "a question away first; and a halt store that cannot be read refuses."
    ),
)
async def a_stop_reaches_only_what_its_holder_may_stop(
    h: Harness,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from brain.api_routes import Answering, Halted, Question, answered_for
    from brain.console.reads import Plane, plane_capability
    from brain.core.errors import Absent
    from brain.gate.context import Channel, open_trace
    from brain.halt_routes import ResumeAsked, StopAsked, halts, resume_now, stop_now
    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_threads import _asking, _request, _web
    from brain.ops.halt import HALT_CAPABILITY, HaltScope, HaltState
    from brain.ops.halt_store import STOPPED_FROM_THE_CONSOLE, Work, read_state, refusal_in

    await h.found_departments()
    stopping = (HALT_CAPABILITY.value, plane_capability(Plane.CONFIGURATION).value)
    scoped, whole = h.principal(A, "stopper"), h.principal(B, "owner")
    member_a, member_b = h.principal(A, "member"), h.principal(B, "member")
    await h.person(scoped, department=A, grants=_in(A, *stopping))
    from brain.core.scope import Scope

    await h.person(
        whole, department=B, grants=tuple((one, Scope.unrestricted()) for one in stopping)
    )
    await h.person(member_a, department=A)
    await h.person(member_b, department=B)
    app = await _web(h)

    async def told(person: str, department: str) -> str:
        # A new session and a reader built for this read: the state is the table's.
        return refusal_in(await read_state(h.sessions), Work(person=person, department=department))

    stopped = await stop_now(
        _request(app),
        await _signed_in_strongly(h, scoped),
        StopAsked(scope=HaltScope.DEPARTMENT, target=A),
    )
    if getattr(stopped, "reason", None) != STOPPED_FROM_THE_CONSOLE:
        raise CheckFailedError("a stop with no reason was not stored with the console's sentence")
    for scope, target in ((HaltScope.DEPARTMENT, B), (HaltScope.EVERYTHING, "")):
        try:
            await stop_now(
                _request(app),
                await _signed_in_strongly(h, scoped),
                StopAsked(scope=scope, target=target),
            )
        except Absent:
            continue
        raise CheckFailedError("a department administrator stopped beyond their department")
    screen = await halts(_request(app), await _signed_in_strongly(h, scoped))
    if screen.may_stop_everything or HaltScope.AGENT not in screen.not_asked_yet:
        raise CheckFailedError("the Stop screen offered more than its reader may stop")
    if [(one.scope, one.target) for one in screen.halts] != [(HaltScope.DEPARTMENT, A)]:
        raise CheckFailedError("the Stop screen did not list the stop its reader had made")

    refused, admitted = await told(member_a, A), await told(member_b, B)
    if not refused or admitted:
        raise CheckFailedError("a department stop did not stop exactly that department")
    if STOPPED_FROM_THE_CONSOLE in refused:
        raise CheckFailedError("a stopped person was told the reason for the stop")

    bare = await resume_now(
        _request(app),
        await _signed_in_strongly(h, whole),
        ResumeAsked(scope=HaltScope.DEPARTMENT, target=A, reason=""),
    )
    if getattr(bare, "status_code", None) != 422 or not await told(member_a, A):
        raise CheckFailedError("a resume with no reason lifted a stop")
    lifted = await resume_now(
        _request(app),
        await _signed_in_strongly(h, whole),
        ResumeAsked(
            scope=HaltScope.DEPARTMENT,
            target=A,
            reason="the acceptance check is lifting its own stop",
        ),
    )
    if not getattr(lifted, "overrides_somebody_else", False):
        raise CheckFailedError("a resume did not say it lifted somebody else's stop")
    if await told(member_a, A):
        raise CheckFailedError("a resumed department was still stopped")

    await stop_now(
        _request(app), await _signed_in_strongly(h, whole), StopAsked(scope=HaltScope.EVERYTHING)
    )
    asking = await _asking(h, member_b)
    now = datetime.now(UTC)
    outcome = await answered_for(
        _request(app),
        open_trace(f"{h.trace_id}-halt", now, Channel.CONSOLE),
        Answering(
            principal=asking.caller.principal, reach=asking.reach, channel=Channel.CONSOLE, now=now
        ),
        Question(question=f"what does {h.word()} say"),
    )
    if not isinstance(outcome, Halted) or STOPPED_FROM_THE_CONSOLE in outcome.told:
        raise CheckFailedError("a question was answered while everything was stopped")

    engine = create_async_engine(NOWHERE)
    try:
        unreadable = await read_state(async_sessionmaker(engine))
    finally:
        await engine.dispose()
    if unreadable.known or refusal_in(unreadable, Work()) != HaltState.unknown().refusal():
        raise CheckFailedError("a halt store that could not be read did not refuse")
