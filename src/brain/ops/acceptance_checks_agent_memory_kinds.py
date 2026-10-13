"""The install acceptance check for an agent's kinds of memory: set on the page, kept, and enforced.

The owner decided on needs item 180 (2026-10-12, option B) that an agent is configured with which
of five kinds of memory it may read and write, and that a run cannot read a kind its configuration
leaves out (M39.7.1). This asks it on the install through the page's own route and the run's own
assembler, as two reserved people of acceptance_a: the agent's steward, and a colleague who may see
the agent and may not look after it.

**What is read.** An agent is made with all five kinds. The steward leaves out the person's memory
over HTTP, and the row, read back as the roster reads it, holds four. The colleague's request to do
the same is refused as for an agent that does not exist, and changes nothing. Then the run's
assembler is handed the agent's own kinds, read off the stored row, and two recollections it can
read: with the person left out the person's reader is never called and the part is named as left out
by configuration, and with the kind put back it is read and shown. The call sites that hand the
assembler the record's kinds are the unit tests'; this proves that what the record holds is what the
assembler obeys.

Task ids: M39.7.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1550

NOT_ALL_FIVE: Final = "an agent was not made with all five kinds of memory"
NOT_SET: Final = "the steward's change to what the agent may remember did not reach its row"
A_COLLEAGUE_CHANGED_IT: Final = (
    "somebody who may not look after the agent changed what it remembers"
)
REFUSED_DIFFERENTLY: Final = "a refused change was refused differently from an agent never made"
READ_WHAT_WAS_LEFT_OUT: Final = "a run was shown a kind of memory its agent was set to leave out"
LEFT_OUT_UNNAMED: Final = "a kind left out was not named as left out by configuration"
NOT_READ_WHEN_ON: Final = "a kind of memory switched on was not shown to a run"


class _Counted:
    """A recollection that counts how often it is read."""

    def __init__(self, said: tuple[str, ...]) -> None:
        self.said = said
        self.calls = 0

    async def hints(self) -> tuple[str, ...]:
        self.calls += 1
        return self.said


def _app(h: Harness) -> FastAPI:
    from fastapi import FastAPI

    app = FastAPI()
    app.state.db_sessions = h.sessions
    return app


@check(
    leaves=("M39.7.1",),
    sentence=(
        "An agent made with all five kinds of memory has the person's left out by its steward "
        "over HTTP, which its row holds; a colleague who may not look after it is refused as for "
        "an agent never made; and the run's assembler, handed the stored kinds, never reads the "
        "kind left out and reads it again once it is put back."
    ),
)
async def an_agent_leaves_out_a_kind_of_memory_and_no_run_is_shown_it(h: Harness) -> None:
    from sqlalchemy import select

    from brain.agent_memory_kinds_routes import MemoryKindsAsked, set_agent_memory_kinds
    from brain.agent_routes import record_of
    from brain.agents.memory_kinds import ALL_KINDS
    from brain.gate.turn_context import LeftOut, Part, assemble
    from brain.ops.acceptance_checks_agents import _refusal
    from brain.ops.acceptance_checks_templates import _asking, _request
    from brain.ops.acceptance_workspace import installed_agent
    from brain.tables.agent import AgentRow

    await h.found_departments()
    steward, colleague = h.principal(A, "kinds_steward"), h.principal(A, "kinds_colleague")
    await h.person(steward, department=A, grants=())
    await h.person(colleague, department=A, grants=())
    agent_id = await installed_agent(h, steward, suffix="memory_kinds")
    app = _app(h)

    async def stored() -> Any:
        row = (await h.execute(select(AgentRow).where(AgentRow.id == agent_id))).scalar_one()
        found = record_of(row)
        if found is None:
            raise CheckFailedError(NOT_SET)
        return found

    if tuple((await stored()).memory_kinds) != ALL_KINDS:
        raise CheckFailedError(NOT_ALL_FIVE)

    async def set_kinds(who: str, kinds: tuple[str, ...], expected: tuple[str, ...]) -> Any:
        return await set_agent_memory_kinds(
            _request(app),
            agent_id,
            MemoryKindsAsked(kinds=list(kinds), expected=list(expected)),
            await _asking(h, who),
        )

    without_person = tuple(one for one in ALL_KINDS if one != "person")
    changed = await set_kinds(steward, without_person, ALL_KINDS)
    if getattr(changed, "status_code", 0) != 200 or tuple((await stored()).memory_kinds) != (
        without_person
    ):
        raise CheckFailedError(NOT_SET)

    refused = await _refusal(set_kinds(colleague, (), without_person))
    if refused is None:
        raise CheckFailedError(A_COLLEAGUE_CHANGED_IT)
    never_made = await _refusal(_never_made(h, app, colleague))
    if refused != never_made:
        raise CheckFailedError(REFUSED_DIFFERENTLY)
    if tuple((await stored()).memory_kinds) != without_person:
        raise CheckFailedError(A_COLLEAGUE_CHANGED_IT)

    person, session = _Counted(("a habit of theirs",)), _Counted(("for now",))
    kept = await stored()
    parts = await assemble(
        "a question", session=session, asker=person, knowledge=None, kinds=kept.memory_kinds
    )
    if person.calls or parts.asker_memory:
        raise CheckFailedError(READ_WHAT_WAS_LEFT_OUT)
    if dict(parts.note().left_out).get(Part.ASKER_MEMORY) is not LeftOut.NOT_CONFIGURED:
        raise CheckFailedError(LEFT_OUT_UNNAMED)

    back = await set_kinds(steward, ALL_KINDS, without_person)
    if getattr(back, "status_code", 0) != 200:
        raise CheckFailedError(NOT_SET)
    again = await assemble(
        "a question",
        session=session,
        asker=person,
        knowledge=None,
        kinds=(await stored()).memory_kinds,
    )
    if again.asker_memory != ("a habit of theirs",):
        raise CheckFailedError(NOT_READ_WHEN_ON)


async def _never_made(h: Harness, app: FastAPI, who: str) -> Any:
    from brain.agent_memory_kinds_routes import MemoryKindsAsked, set_agent_memory_kinds
    from brain.agents.memory_kinds import ALL_KINDS
    from brain.ops.acceptance_checks_templates import _asking, _request

    return await set_agent_memory_kinds(
        _request(app),
        f"acceptance_{h.run}_never_made",
        MemoryKindsAsked(kinds=[], expected=list(ALL_KINDS)),
        await _asking(h, who),
    )
