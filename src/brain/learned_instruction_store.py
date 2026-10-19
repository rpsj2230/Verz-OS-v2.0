"""Writing instructions the agent's own learning proposed and a named person approved (M16.7.1).

`brain.agents.learned` says what a learned change is: marked, owned by the person who approved it,
never over a value somebody here set. This is the half that owns a session, and it is the one place
a learned change reaches the database, as `brain.prompt_routes` is the one place a person's edit of
the instructions does. It writes exactly what an edit writes, the install's overlay, owners,
effective document and hash and the agent row's copy of the persona, in one transaction, so what
`0059`'s trigger records is the same entry an edit leaves, naming the approver, and what a person
reading the Prompts screen sees is the instructions in force with the source marked.

**Behind a switch that ships off, and only the writing is.** `learning_may_change_instructions`
reads `AGENT_LEARNED_CHANGES`; while it is off nothing is written, and listing and giving back are
the Prompts screen's, which the switch does not touch. See
`brain.ops.features_declared.agent_learned_changes`.

**A stale approval writes nothing.** The change names the effective hash the approver was shown,
and the row is read under a lock and refused when the hash has moved, as an edit is, so an approval
given for instructions that have since changed is not applied to the new ones.

**No caller yet but the install check, and that is said rather than hidden.** Nothing the product
learns today is an instruction change: the learning loop proposes knowledge and fast-lane rules, and
`brain.memory.tiers` classifies every other change as needing a person. This is the door the first
one will go through, held by `tests/unit/test_agent_learned.py` to be the only writer of a learned
value, and proved on an install by `brain.ops.acceptance_checks_learned_changes`.

Task ids: M16.7.1
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import record_of
from brain.agents.learned import NotLearnableError, learn_field
from brain.agents.template import TemplateError
from brain.ops.features import is_on
from brain.ops.features_declared.agent_learned_changes import AGENT_LEARNED_CHANGES
from brain.prompt_routes import (
    PERSONA_PATH,
    installed,
    instruction_refusal,
    one_agent_locked,
    one_install_locked,
    write_install,
    write_persona,
    written,
)
from brain.tables.audit import attributed_to

#: What a person is told when the switch is off.
SWITCHED_OFF: Final = (
    "Letting what an agent learns change its instructions is switched off on this install, so "
    "nothing was written."
)
#: What a person is told when the agent is not one a change can be written to.
NO_SUCH_AGENT: Final = "That agent has no install record that constructs, so nothing was written."
#: What a person is told when the instructions moved after the approval was drawn.
IT_MOVED: Final = (
    "The agent's instructions changed after this was proposed, so nothing was written. Look again."
)


class Outcome(enum.StrEnum):
    """What an application of a learned change did."""

    APPLIED = "applied"
    SWITCHED_OFF = "switched_off"
    REFUSED = "refused"
    MOVED = "moved"
    NO_AGENT = "no_agent"


@dataclass(frozen=True)
class Applied:
    """The outcome and the sentence, which is a literal of this module's or the domain's refusal."""

    outcome: Outcome
    sentence: str = ""


async def learning_may_change_instructions(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether what an agent learns may be written into its instructions now. Off by default."""
    async with sessions() as session:
        return await is_on(session, AGENT_LEARNED_CHANGES)


async def apply_learned_instructions(
    sessions: async_sessionmaker[AsyncSession],
    *,
    agent_id: str,
    instructions: str,
    approved_by: str,
    expected_hash: str,
    ent_hash: str,
    trace_id: str,
    now: datetime,
) -> Applied:
    """Write learned instructions on one agent as the agent's own learning, or say why not.

    The order is the argument. The switch first, so a switched-off install writes and locks
    nothing. Then the install is locked and the agent read under it, so two approvals cannot both
    win. Then the hash the approver was shown, then the instructions through the same refusals an
    edit meets, then the door (`brain.agents.learned.learn_field`), which refuses a value a person
    here set. One transaction, attributed to the approver, and rolled back whole on any refusal.
    """
    async with sessions() as session:
        if not await is_on(session, AGENT_LEARNED_CHANGES):
            return Applied(Outcome.SWITCHED_OFF, SWITCHED_OFF)
        await session.execute(one_install_locked(agent_id))
        found = (await session.execute(one_agent_locked(agent_id))).one_or_none()
        record = None if found is None else record_of(found[0])
        install = None if found is None else installed(found[1], found[2])
        if found is None or record is None or install is None:
            await session.rollback()
            return Applied(Outcome.NO_AGENT, NO_SUCH_AGENT)
        signed, instance = install
        if found[1].effective_hash != expected_hash:
            await session.rollback()
            return Applied(Outcome.MOVED, IT_MOVED)
        try:
            refusal = instruction_refusal(instructions, record.persona)
            if refusal:
                await session.rollback()
                return Applied(Outcome.REFUSED, refusal)
            changed = learn_field(
                instance, PERSONA_PATH, instructions.strip(), approved_by=approved_by, at=now
            )
            row, persona, _ = written(signed, changed, record)
        except (NotLearnableError, TemplateError, ValueError) as refused:
            await session.rollback()
            return Applied(Outcome.REFUSED, str(refused))
        for statement in attributed_to(actor_id=approved_by, ent_hash=ent_hash, trace_id=trace_id):
            await session.execute(statement)
        await session.execute(write_install(agent_id, row))
        await session.execute(write_persona(agent_id, persona))
        await session.commit()
    return Applied(Outcome.APPLIED)
