"""Install acceptance checks for what the install knows: the library and the head's coverage.

Each check calls the route the console page calls, as the reader that page serves, in the shape
`brain.ops.acceptance_checks_governance` sets out, over the check's own transaction. **Nothing is
kept**: every item the checks write is a row of the check's own transaction, so no document the
install holds is changed and none is left.

Task ids: M27.7.20, M27.2.5
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
from brain.ops.acceptance_checks_company_views import _screens_over
from brain.ops.acceptance_checks_governance import _app, _asking, _refused, _request
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 930

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why a check that cannot find its own items in the library says it was not run.
A_FULL_LOAD_MAY_HOLD_NONE_OF_THE_CHECKS_ITEMS: Final = (
    "the library reads the install's documents in reference order to a bound and this install "
    "holds more than that, so the check's own documents may fall outside the page it reads"
)

# ------------------------------------------------------------------------ the figures
#: How long ago each document of the coverage check was last verified, against the document
#: horizon (live for ninety days, stale after a year). Far inside each band, so no wall clock
#: moves one across a line while the check runs.
VERIFIED_AGO: Final = {"live": timedelta(days=5), "ageing": timedelta(days=200)}
STALE_AGO: Final = timedelta(days=900)


async def a_document(
    h: Harness,
    owner: str,
    name: str,
    *,
    visibility: str,
    department: str | None,
    verified_ago: timedelta | None = None,
) -> str:
    """A published document written as the check's own row, named by `name`."""
    from brain.tables.knowledge import KnowledgeItemRow

    item_id = f"acceptance-{h.run}-{name}"
    await h.execute(
        *h.attributed(owner),
        insert(KnowledgeItemRow).values(
            item_id=item_id,
            owner_id=owner,
            visibility=visibility,
            department=department,
            state="published",
            verified_by=None if verified_ago is None else owner,
            verified_at=None if verified_ago is None else h.now - verified_ago,
        ),
    )
    return item_id


# --------------------------------------------------------------- 1. the library (M27.7.20)
@check(
    leaves=("M27.7.20",),
    sentence=(
        "The library lists a department's document, the other department's and a company-wide "
        "one, each with how widely it reaches, to a reader of the library across the company; a "
        "reader of one department is shown that department's document alone, with no count of "
        "what was left out; a person without the screen is refused."
    ),
)
async def the_library_lists_every_department_with_each_items_reach(h: Harness) -> None:
    from brain.estate_routes import library
    from brain.listing import ListAsked

    await h.found_departments()
    whole, narrow, nobody = h.principal(A, "whole"), h.principal(A, "narrow"), h.principal(A, "x")
    await h.person(whole, department=A, grants=_screens_over(Scope.unrestricted(), "library"))
    await h.person(narrow, department=A, grants=_screens_over(Scope.department(A), "library"))
    await h.person(nobody, department=A)
    mine = {
        "a": await a_document(h, whole, "a", visibility="department", department=A),
        "b": await a_document(h, whole, "b", visibility="department", department=B),
        "all": await a_document(h, whole, "all", visibility="company", department=None),
    }
    request = _request(_app(h))
    # Only the check's own documents, found by their references, whatever else the install holds.
    ours = ListAsked(search=f"acceptance-{h.run}", limit=200)
    if not await _refused(library(request, await _asking(h, nobody), ours)):
        raise CheckFailedError("the library was shown to a person without the screen")

    page = await library(request, await _asking(h, whole), ours)
    levels = {one.item_id: one.level.value for one in page.items}
    if not set(mine.values()) <= set(levels):
        if page.truncated:
            raise CheckNotRunError(A_FULL_LOAD_MAY_HOLD_NONE_OF_THE_CHECKS_ITEMS)
        raise CheckFailedError("the library did not list every department's documents")
    if (levels[mine["a"]], levels[mine["b"]], levels[mine["all"]]) != (
        "department",
        "department",
        "company",
    ):
        raise CheckFailedError("the library did not say how widely each document reaches")

    seen = await library(request, await _asking(h, narrow), ours)
    shown = {one.item_id for one in seen.items}
    if mine["a"] not in shown or mine["b"] in shown or mine["all"] in shown:
        raise CheckFailedError("a reader of one department was shown another's documents")
    if seen.total is not None or page.total is not None:
        raise CheckFailedError("the library answered with a count of what it left out")


# ------------------------------------------------ 2. coverage and staleness (M27.2.5)
@check(
    leaves=("M27.2.5",),
    sentence=(
        "The person who leads acceptance_a is shown how many documents its knowledge holds in "
        "each freshness band: one verified recently, one verified months ago, one verified "
        "years ago and one nobody verified are counted live, ageing, stale and unstated; "
        "somebody who does not lead it is refused."
    ),
)
async def a_head_is_shown_how_fresh_what_their_department_knows_is(h: Harness) -> None:
    from brain.department_view_routes import coverage_of_department
    from brain.identity.organisation_store import StoredOrganisation
    from brain.ops.acceptance_run import SET_UP_REACH

    await h.found_departments()
    head, member = h.principal(A, "head"), h.principal(A, "member")
    await h.person(head, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(member, department=A, grants=_in(A, *KNOWLEDGE_READS))
    appointed = await StoredOrganisation(h.sessions).appoint(
        department=A,
        principal_id=head,
        actor=h.actor,
        ent_hash=SET_UP_REACH,
        trace_id=h.trace_id,
        may=lambda *_: True,
    )
    if appointed is None:
        raise CheckFailedError("a head could not be appointed to lead a department")
    for name, ago in (
        ("live", VERIFIED_AGO["live"]),
        ("ageing", VERIFIED_AGO["ageing"]),
        ("stale", STALE_AGO),
        ("unverified", None),
    ):
        await a_document(h, head, name, visibility="department", department=A, verified_ago=ago)

    request = _request(_app(h))
    shown = await coverage_of_department(request, await _asking(h, head), department=A)
    if shown.unread or [one.area for one in shown.areas] != [A]:
        raise CheckFailedError("a head was not shown the knowledge their department holds")
    held = shown.areas[0].by_freshness
    if (held.get("live"), held.get("ageing"), held.get("stale"), held.get("unstated")) != (
        1,
        1,
        1,
        1,
    ):
        raise CheckFailedError("the documents were not counted in the band each one is in")
    if not await _refused(coverage_of_department(request, await _asking(h, member), department=A)):
        raise CheckFailedError("somebody who does not lead the department was shown its coverage")
