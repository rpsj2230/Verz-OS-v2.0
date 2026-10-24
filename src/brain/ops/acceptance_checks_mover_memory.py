"""Install acceptance check for a mover's memories of the reach they left (M26.2.5).

A member of acceptance_a says on Ask something to remember, and the install keeps it. They are
shown it, as the Memory screen and a model answering them are. They then move: the grants over
acceptance_a are withdrawn and the same grants over acceptance_b are given, which is the grant
change the staff sync makes for a mover. Their memory is no longer shown to them or to a model, and
it is still there; it is shown again when the move is undone, with the row exactly as it was.

**What this holds and the other check does not.** `a_memory_is_not_recalled_once_its_grant_goes`
withdraws a grant and holds that a memory needing it stops being shown. A mover keeps the same
capabilities over a different place, so a rule that compared only the capability names would show
the old department's memory in the new one. This holds the scope half of the rule, on the install's
own tables.

**Nothing is rewritten, and the check shows it.** The tags and the scope on the row are the same
after the move and after it is undone, which is the argument of
`brain.identity.lifecycle.A_MEMORY_IS_RECALLED_AT_THE_REACH_IT_WAS_FORMED_AT`: a rewrite on a move
would be a second rule about recall.

**The move is made as a grant change, not through the staff sync**, so the check runs on an install
with no Starter pack and in the whole-suite run. The sync's own step is held by
`a_joiner_gets_a_department_pack_and_a_mover_or_leaver_loses_it`.

**The rows are written by the check and rolled back with it.** Nothing reaches a model.

Task ids: M26.2.5
"""

from __future__ import annotations

from typing import Final

from sqlalchemy.exc import DBAPIError

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before the roll-ups that read it (2800).
CHECK_ORDER: Final = 1810

A, B = RESERVED_DEPARTMENTS


@check(
    leaves=("M26.2.5",),
    sentence=(
        "A memory a member formed on Ask in acceptance_a is shown to them while they hold the "
        "grants over acceptance_a, is not shown to them or to a model once those are withdrawn and "
        "the same grants are given over acceptance_b, is still on file with its row unchanged, and "
        "is shown again when the move is undone."
    ),
)
async def a_mover_is_not_told_the_memories_of_the_reach_they_left(h: Harness) -> None:
    from brain.core.entitlement import Capability
    from brain.govern_routes import retire_grant
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
    from brain.ops.acceptance_checks_memory import (
        answered_at,
        ask,
        memories_of,
        memory_app,
        people,
        recalled_for,
        shown_about,
    )

    try:
        placed = await people(h)
        app = await memory_app(h)
        word = h.word()
        await ask(h, app, placed.member, f"Remember that I sign as {word}.", 1)
        statement = f"I sign as {word}"
        before = await memories_of(h, placed.member)
        held = answered_at(await h.reach(placed.member))
        shown_before = await shown_about(h, placed.member, held, h.now)
    except DBAPIError:
        raise CheckFailedError("the database refused the step that forms the memory") from None
    if len(before) != 1:
        raise CheckFailedError("saying remember that on Ask did not keep a stated memory")
    if statement not in shown_before:
        raise CheckFailedError("a memory was not shown to its person while they held its grants")

    async def moved_to(department: str) -> None:
        for capability in KNOWLEDGE_READS:
            await h.execute(*h.attributed(), retire_grant(placed.member, capability))
        for capability, where in _in(department, *KNOWLEDGE_READS):
            await h.grant(placed.member, capability, where)

    try:
        await moved_to(B)
        after = answered_at(await h.reach(placed.member))
        shown_after = await shown_about(h, placed.member, after, h.now)
        recalled_after = await recalled_for(h, after, B, h.now)
        kept_after = await memories_of(h, placed.member)
    except DBAPIError:
        raise CheckFailedError("the database refused the step that moves the person") from None
    if not after.holds(Capability(value=KNOWLEDGE_READS[0]), h.now):
        raise CheckFailedError("a person who moved was not given the new department's grants")
    if statement in shown_after:
        raise CheckFailedError("a mover was still shown a memory formed at the reach they left")
    if recalled_after:
        raise CheckFailedError("a model would still be told a mover's memory of the old reach")
    if kept_after != before:
        raise CheckFailedError("moving a person rewrote or removed a memory instead of not showing")

    try:
        await moved_to(A)
        back = answered_at(await h.reach(placed.member))
        shown_back = await shown_about(h, placed.member, back, h.now)
        kept_back = await memories_of(h, placed.member)
    except DBAPIError:
        raise CheckFailedError("the database refused the step that undoes the move") from None
    if statement not in shown_back:
        raise CheckFailedError("a memory was not shown again once the person's reach returned")
    if kept_back != before:
        raise CheckFailedError("a memory changed across a move and its undoing")
