"""The install acceptance check for what an agent taught itself: marked, listed, given back.

M16.7.1 asks that every change learning applies to an agent be marked machine-authored, so a person
can list and revert exactly what the agent taught itself apart from what an administrator set.
`brain.learned_instruction_store` is the door a learned change goes through, and
`brain.prompt_routes` is where a person reads the instructions in force and gives them back, so
this applies a learned change through the one and reads and reverts it through the other, as a
reserved administrator of acceptance_a, over an agent the check installs and rolls back.

**Learning has produced no instruction change on any install yet, so the check makes the one it
tests.** It writes through the door itself, with a reserved person as the approver, which is what
the first real applier will do, and it asserts what that leaves: the instructions in force are the
learned words, marked as the agent's own learning and naming who approved them; the ledger names
the approver; the same words applied against a stale page change nothing; and once an
administrator has set the instructions, learning is refused and leaves them as they were. Giving a
learned change back returns the template's words, and the mark goes with the value because an
install holds an owner only for a value it holds (`brain.agents.template.TemplateInstance`). And
while the switch is off nothing is written, yet giving back still works, so turning it off cannot
trap what it let in.

**Nothing about the install is assumed.** The agent, its template and its people are the check's,
the switches are set inside the check's transaction, and nothing it writes outlives it.

Task ids: M16.7.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_agent_console import _asking, _console, _readers, _request
from brain.ops.acceptance_checks_skills import _changes
from brain.ops.acceptance_run import SET_UP_REACH, Harness
from brain.ops.acceptance_workspace import installed_agent

if TYPE_CHECKING:
    from brain.learned_instruction_store import Applied
    from brain.ops.feature_model import Feature
    from brain.prompt_routes import AgentInstructionsView

A, _ = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page, after the Prompts screen's own. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 301

WRITTEN_WHILE_OFF: Final = "a learned change was written while its switch was off"
NOT_MARKED: Final = "a learned change was not in force and marked as the agent's own learning"
NOT_ON_THE_LEDGER: Final = (
    "a learned change did not reach the ledger naming the person who approved it"
)
STALE_WRITTEN: Final = "an approval drawn against instructions that had moved was written anyway"
GIVE_BACK_FAILED: Final = "a learned change given back did not return the template's instructions"
OVERWROTE_A_PERSON: Final = "a learned change replaced instructions an administrator had set"
MARKED_WHAT_A_PERSON_SET: Final = "instructions an administrator set were marked as learned"
SAME_WORDS_WRITTEN: Final = (
    "a learned change saying what the instructions already said was written and marked as learned"
)
TRAPPED: Final = "turning the switch off left a learned change that could not be given back"

#: The words the agent learns, and the ones an administrator sets.
LEARNED: Final = "Answers an install acceptance check, and says which document it read."
SET_BY_A_PERSON: Final = "Answers an install acceptance check, as an administrator set it."


@check(
    leaves=("M16.7.1",),
    sentence=(
        "A change the agent learned and a named person approved is written into an agent of "
        "acceptance_a only while its switch is on, shows on the Prompts screen as the agent's own "
        "learning naming the approver, reaches the ledger under their name, never replaces "
        "instructions an administrator set, and is given back to the template's, switch or not."
    ),
)
async def what_an_agent_taught_itself_is_marked_and_can_be_given_back(h: Harness) -> None:
    import structlog

    from brain.core.errors import Absent
    from brain.learned_instruction_store import Outcome, apply_learned_instructions
    from brain.ops.acceptance_workspace import TEMPLATE_PERSONA
    from brain.ops.features import PROMPT_EDITING, switch
    from brain.ops.features_declared.agent_learned_changes import AGENT_LEARNED_CHANGES
    from brain.prompt_routes import (
        INSTRUCTIONS_AUTHORITY,
        InstructionsEdit,
        InstructionsGiveBack,
        edit_instructions,
        give_back_instructions,
        prompts,
    )
    from brain.tables.audit import attributed_to

    await h.found_departments()
    admin, approver = h.principal(A, "admin"), h.principal(A, "approver")
    await h.person(admin, department=A, grants=_readers(INSTRUCTIONS_AUTHORITY.value))
    await h.person(approver, department=A, grants=_readers())
    agent_id = await installed_agent(h, admin)
    app = _console(h)

    async def switched(one: Feature, on: bool) -> None:
        async with h.sessions() as session:
            for statement in attributed_to(
                actor_id=admin, ent_hash=SET_UP_REACH, trace_id=h.trace_id
            ):
                await session.execute(statement)
            await switch(session, one, on=on, by=admin)
            await session.commit()

    async def shown() -> AgentInstructionsView:
        page = await prompts(_request(app), await _asking(h, admin, strong=True))
        found = [one for one in page.agents if one.agent_id == agent_id]
        if len(found) != 1:
            raise CheckFailedError(NOT_MARKED)
        return found[0]

    async def learn(words: str, expected_hash: str) -> Applied:
        return await apply_learned_instructions(
            h.sessions,
            agent_id=agent_id,
            instructions=words,
            approved_by=approver,
            expected_hash=expected_hash,
            ent_hash=SET_UP_REACH,
            trace_id=h.trace_id,
            now=h.now,
        )

    async def give_back() -> None:
        before = await shown()
        await give_back_instructions(
            _request(app),
            agent_id,
            InstructionsGiveBack(expected_hash=before.effective_hash or ""),
            await _asking(h, admin, strong=True),
        )

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        await switched(AGENT_LEARNED_CHANGES, False)
        start = await shown()
        off = await learn(LEARNED, start.effective_hash or "")
        if off.outcome is not Outcome.SWITCHED_OFF or (await shown()).instructions != (
            TEMPLATE_PERSONA
        ):
            raise CheckFailedError(WRITTEN_WHILE_OFF)

        await switched(AGENT_LEARNED_CHANGES, True)
        start = await shown()
        stale = await learn(LEARNED, "0" * 64)
        if stale.outcome is not Outcome.MOVED or (await shown()).instructions != TEMPLATE_PERSONA:
            raise CheckFailedError(STALE_WRITTEN)
        done = await learn(LEARNED, start.effective_hash or "")
        after = await shown()
        if (
            done.outcome is not Outcome.APPLIED
            or after.instructions != LEARNED
            or not after.machine_authored
            or after.source != "learned"
            or after.set_by != approver
        ):
            raise CheckFailedError(NOT_MARKED)
        edited = [
            actor
            for actor, details in await _changes(h, f"agent:{agent_id}", "instructions")
            if details.get("change") == "edited"
        ]
        if edited != [approver]:
            raise CheckFailedError(NOT_ON_THE_LEDGER)

        await give_back()
        reverted = await shown()
        if reverted.instructions != TEMPLATE_PERSONA or reverted.overridden:
            raise CheckFailedError(GIVE_BACK_FAILED)

        same = await learn(TEMPLATE_PERSONA, reverted.effective_hash or "")
        if same.outcome is not Outcome.REFUSED or (await shown()).machine_authored:
            raise CheckFailedError(SAME_WORDS_WRITTEN)

        await switched(PROMPT_EDITING, True)
        await edit_instructions(
            _request(app),
            agent_id,
            InstructionsEdit(
                instructions=SET_BY_A_PERSON, expected_hash=reverted.effective_hash or ""
            ),
            await _asking(h, admin, strong=True),
        )
        by_a_person = await shown()
        if by_a_person.machine_authored or by_a_person.instructions != SET_BY_A_PERSON:
            raise CheckFailedError(MARKED_WHAT_A_PERSON_SET)
        refused = await learn(LEARNED, by_a_person.effective_hash or "")
        if (
            refused.outcome is not Outcome.REFUSED
            or (await shown()).instructions != SET_BY_A_PERSON
        ):
            raise CheckFailedError(OVERWROTE_A_PERSON)

        await give_back()
        again = await shown()
        taught = await learn(LEARNED, again.effective_hash or "")
        await switched(AGENT_LEARNED_CHANGES, False)
        try:
            await give_back()
        except Absent:
            raise CheckFailedError(TRAPPED) from None
        if taught.outcome is not Outcome.APPLIED or (await shown()).instructions != (
            TEMPLATE_PERSONA
        ):
            raise CheckFailedError(TRAPPED)
