"""Install acceptance check for the Memory screen's viewer and the change history beside it.

The check starts from a memory a reserved person formed on Ask, edits it through their own Edit,
and reads the route the Memory screen calls (`brain.estate_routes.memory`) as the person and as a
a reader of the other department who holds the screen over it. **A memory the reader may not
recall and a person nobody remembers anything about are one answer**, so that answer is held
equal to the answer for a subject nobody has memories of, field for field.

Everything written is in the check's rolled-back transaction, for reserved people of acceptance_a.

Task ids: M27.7.22
"""

from __future__ import annotations

from typing import Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_learning import stated_memory
from brain.ops.acceptance_checks_memory import people
from brain.ops.acceptance_operations_console import asking_as, console_for, refused, screen_grants
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1310

A, B = RESERVED_DEPARTMENTS


@check(
    leaves=("M27.7.22",),
    sentence=(
        "A person's memory formed on Ask is shown to its owner on the Memory screen, an edit of it "
        "appears there as a step in its history marked as replaced with the words that changed, "
        "and a reader of another department who holds the screen is answered exactly as for "
        "somebody nobody remembers anything about; a person without the screen is refused."
    ),
)
async def memory_history_shows_an_edit_and_hides_what_is_not_recallable(
    h: Harness,
) -> None:
    from brain.estate_routes import memory
    from brain.mine_routes import edited
    from brain.ops.memory_store import StoredMemoryRecords

    placed = await people(h)
    for one, department in ((placed.member, A), (placed.colleague, A), (placed.other, B)):
        for capability, scope in screen_grants("memory", Scope.department(department)):
            await h.grant(one, capability, scope)
    bystander = h.principal(B, "bystander")
    await h.person(bystander, department=B)
    word, later = h.word(), h.word()
    first = await stated_memory(h, placed.member, f"I work from {word} on Fridays", 1)
    console = console_for(h)

    async def viewed(reader: str, subject: str) -> Any:
        return await memory(console.request(), await asking_as(h, reader), subject=subject)

    own = await viewed(placed.member, placed.member)
    if [one.statement for one in own.curated + own.extracted] != [f"I work from {word} on Fridays"]:
        raise CheckFailedError("a person was not shown the memory they formed on Ask")
    if own.history and any(one.correction for one in own.history):
        raise CheckFailedError("a memory nobody had changed showed a change in its history")

    reach = await h.reach(placed.member)
    changed = await edited(
        h.sessions,
        StoredMemoryRecords(h.sessions),
        memory_id=first,
        statement=f"I work from {later} on Fridays",
        principal_id=placed.member,
        ent_hash=reach.ent_hash(),
        trace_id=h.trace_id,
        now=h.now,
    )
    if changed is None or changed.replacement_id is None:
        raise CheckFailedError("a person could not edit a memory they formed")
    after = await viewed(placed.member, placed.member)
    steps = [one for one in after.history if one.replaced_id == first]
    if len(steps) != 1 or steps[0].memory_id != changed.replacement_id:
        raise CheckFailedError("the history did not show the edit as a step replacing the memory")
    if not steps[0].diff:
        raise CheckFailedError("the history's step did not show the words that changed")
    shown = [one.statement for one in after.curated + after.extracted]
    if shown != [f"I work from {later} on Fridays"]:
        raise CheckFailedError("the viewer showed words an edit had replaced")

    # Somebody of acceptance_b holds the screen over their own department and none of this
    # person's memory, and is told what anybody is told of a person nobody remembers anything of.
    # A colleague of acceptance_a, whose screen reaches the department, is shown it: that is what
    # the screen is for.
    colleague = await viewed(placed.colleague, placed.member)
    if not colleague.history:
        raise CheckFailedError("a reader of the person's own department was shown no history")
    other = await viewed(placed.other, placed.member)
    nobody = await viewed(placed.other, f"{placed.member}.nobody")
    if other.model_dump(exclude={"subject_id"}) != nobody.model_dump(exclude={"subject_id"}):
        raise CheckFailedError("a reader without the memory was answered differently from nobody")
    if other.curated or other.extracted or other.history:
        raise CheckFailedError("a reader of another department was shown somebody's memory")
    if not await refused(viewed(bystander, placed.member)):
        raise CheckFailedError("a person without the Memory screen was answered")
