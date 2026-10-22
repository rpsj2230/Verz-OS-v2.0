"""Install acceptance check for the guide to asking well, served to staff (M34.3.1.3).

One source is connected for one reserved department and three of its records are in the index. Two
reserved people of that department then read the guide through the route the console would call,
signed in through the install's own gate: one who may read that kind of record there, and one who
holds the read only in the other department. **The first is shown a question about the records they
read, with where to check it; the second is shown the sentence for a department with nothing
indexed**, which is also what the first is shown with the switch for questions built from data off.
Neither page carries the demo company's departments, a marker from the shipped page, or this
repository's account of the tests that hold it.

**What this proves and what it does not.** It proves the route cuts the shipped page and fills it
from the caller's own reach on the install's own tables. It does not prove the wording of the seven
habits, which no test can hold and which the page says it keeps true by hand.

**The index rows are written by the check and rolled back with it.** Nothing reaches a source.

Task ids: M34.3.1.3
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from sqlalchemy.exc import DBAPIError

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_people_signed_in import console, within
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2710

A, B = RESERVED_DEPARTMENTS

#: The source the check connects: one that asks for a department and whose records can be read live,
#: so it is attributable to a department and checkable in its own system.
SOURCE: Final = "freshdesk"

#: Why the check cannot run on an install that already reads this source.
CONNECTED_ALREADY: Final = (
    "The source this check connects is connected on this install already, and a source is "
    "connected once, so the check would have to disconnect it first."
)


async def _no_key() -> None:
    """The key a source is connected with: none, because this check reads nothing from a source."""
    return None


async def _guide(c: Any, who: str) -> str:
    """The guide as `who` is served it, through the route, as one markdown string."""
    from brain.help_routes import asking_well

    with c.as_route():
        served = await asking_well(c.request(), await c.asked(who, strong=False))
    return str(served.markdown)


def _table_of(markdown: str) -> str:
    """What follows the heading over the reader's own table, which is the end of the page."""
    from brain.ops.guide_docs import YOUR_DEPARTMENT

    return markdown.partition(YOUR_DEPARTMENT)[2]


@check(
    leaves=("M34.3.1.3",),
    sentence=(
        "A member of acceptance_a who may read tickets there is served the guide to asking well "
        "with a question about tickets and where to check it; a member who holds the read only in "
        "the other department, and the first with the switch off, are served the sentence for "
        "nothing indexed; and no page carries the demo company's departments."
    ),
)
async def staff_are_served_the_asking_guide_with_their_own_examples(h: Harness) -> None:
    from sqlalchemy import insert

    from brain.connectors.manifest import manifest_digest
    from brain.knowledge.rows import entity_capability
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.guide_docs import NO_EXAMPLES_YET
    from brain.tables.projection import ProjectedRecordRow

    try:
        already = (await h.execute(live(SOURCE))).scalar_one_or_none()
    except DBAPIError:
        raise CheckFailedError("the database refused the step that looks for the source") from None
    if already is not None:
        raise CheckNotRunError(CONNECTED_ALREADY)

    try:
        await h.found_departments()
        c = await console(h)
        member, bystander = h.principal(A, "guide_member"), h.principal(A, "guide_bystander")
        ticket = entity_capability("ticket").value
        await h.person(member, department=A, grants=within(A, ticket))
        await h.person(bystander, department=A, grants=within(B, ticket))
    except DBAPIError:
        raise CheckFailedError("the database refused the step that places the readers") from None

    try:
        settings = {"domain": "acceptance.freshdesk.com", "department": A}
        await StoredConnections(h.sessions).connect(
            connector=SOURCE,
            settings=settings,
            digest=manifest_digest(manifest_for(SOURCE, settings)),
            actor=h.actor,
            trace_id=h.trace_id,
            ent_hash=SET_UP_REACH,
            keep_key=_no_key,
        )
    except DBAPIError:
        raise CheckFailedError("the database refused the step that connects the source") from None

    try:
        for index in range(3):
            await h.execute(
                *h.attributed(),
                insert(ProjectedRecordRow).values(
                    source=SOURCE,
                    entity="ticket",
                    source_id=f"acceptance-{h.run}-{uuid.uuid4().hex[:8]}-{index}",
                    fields={"department": A},
                    last_seen_at=h.now,
                ),
            )
    except DBAPIError:
        raise CheckFailedError("the database refused the step that indexes the records") from None

    try:
        c.app.state.starter_questions_from_data_on = True
        served = await _guide(c, member)
        outside = await _guide(c, bystander)
        c.app.state.starter_questions_from_data_on = False
        switched_off = await _guide(c, member)
    except DBAPIError:
        raise CheckFailedError("the database refused the step that reads the guide") from None

    if not served.startswith("# How to ask well"):
        raise CheckFailedError("the guide served to a member was not the guide to asking well")
    if "ticket" not in _table_of(served) or NO_EXAMPLES_YET in _table_of(served):
        raise CheckFailedError("a member was not served a question about the records they read")
    if "ticket" in _table_of(outside) or NO_EXAMPLES_YET not in _table_of(outside):
        raise CheckFailedError("a member was served a question about records they may not read")
    if "ticket" in _table_of(switched_off) or NO_EXAMPLES_YET not in _table_of(switched_off):
        raise CheckFailedError("questions built from data were served while their switch was off")
    for page in (served, outside, switched_off):
        if "checked: examples from" in page or "## What is checked" in page or "demo" in page:
            raise CheckFailedError("the served guide carried the shipped page's own working")
