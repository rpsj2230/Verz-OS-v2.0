"""Install check for the install's own help pages: a runbook per screen, per alert, the playbook.

The runbooks, the alert runbooks, the incident playbook and the plain statements of what the
system can see and does with what is typed were written, swept against the registry and shipped in
the image, and served nowhere. The check asks each route as the reader it is for, over the
install's own shipped files, and as a reader it is not for.

**The sweep is the authority on the content and this holds the pages to it.** Every screen has
exactly one runbook the route can serve, whose first line is the screen's title, which is the
property `brain.launch.screen_runbook_gaps` and `brain.ops.guide_docs.runbook_gaps` hold the
files to; the alert page names every reason a control can be missed, in the order the type does;
the playbook has a row for every declared failure. What is added here is that a reader is given
them from the install and a stranger is refused with the one refusal. See
`A_HELP_PAGE_IS_AS_OPEN_AS_THE_SCREEN_IT_IS_ABOUT` in `brain.help_routes`.

Task ids: M34.4.1, M34.3.2.1, M34.3.1.1, M34.3.1.2
"""

from __future__ import annotations

from typing import Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    screen_grants,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2130

A, B = RESERVED_DEPARTMENTS

#: What a person reads knowledge with. Restated rather than imported, so a change to the route's
#: authority fails its check instead of moving with it.
READS_KNOWLEDGE: Final = "read:knowledge"


@check(
    leaves=("M34.4.1", "M34.3.2.1"),
    sentence=(
        "A reader of the Overview, Queue and Incidents screens is given the Overview's runbook, "
        "a list of the runbooks they may open, every alert's steps and the incident playbook; a "
        "person who holds none of the screens is given an empty list and the one refusal for "
        "each page, the same as for a screen that does not exist."
    ),
)
async def help_pages_are_served_to_the_readers_of_their_screens(
    h: Harness,
) -> None:
    from brain.console.screens import SCREENS, screen
    from brain.help_routes import (
        alert_index,
        alert_runbook,
        playbook,
        runbook,
        runbook_index,
    )
    from brain.ops.controls import CONTROLS, Missed
    from brain.ops.reliability import MATRIX

    await h.found_departments()
    reader, nobody = h.principal(A, "helped"), h.principal(A, "unhelped")
    keys = ("overview", "queue", "incidents")
    grants = tuple(dict.fromkeys(g for key in keys for g in screen_grants(key)))
    await h.person(reader, department=A, grants=grants)
    await h.person(nobody, department=A)

    wanted = await asking_as(h, reader)
    page = await runbook("overview", wanted)
    if page.title != screen("overview").title or not page.markdown.startswith(
        f"# {screen('overview').title}"
    ):
        raise CheckFailedError("a runbook was not the screen's own, headed by its title")
    listed = {one.key for one in (await runbook_index(wanted)).runbooks}
    if not set(keys) <= listed or not listed <= {one.key for one in SCREENS}:
        raise CheckFailedError("the runbook list did not name the screens the reader may open")
    if (await runbook_index(await asking_as(h, nobody))).runbooks:
        raise CheckFailedError("a person who may open no screen was listed a runbook")

    named = CONTROLS[0].name
    alerts = await alert_runbook(named, wanted)
    if [one.reason for one in alerts.steps] != [one.value for one in Missed]:
        raise CheckFailedError("an alert's runbook did not cover every way a control is missed")
    if any(not one.first_check or not one.then_do for one in alerts.steps):
        raise CheckFailedError("an alert's runbook had a way of being missed with no step")
    if [one.control for one in (await alert_index(wanted)).alerts] != [
        one.name for one in CONTROLS
    ]:
        raise CheckFailedError("the alert list was not every control the install can alert on")
    book = await playbook(wanted)
    if [one.component for one in book.failures] != [one.component for one in MATRIX]:
        raise CheckFailedError("the playbook did not have a row for every declared failure")

    stranger = await asking_as(h, nobody)
    refusals = (
        runbook("overview", stranger),
        runbook("no_such_screen", wanted),
        alert_runbook(named, stranger),
        alert_runbook("no_such_control", wanted),
        playbook(stranger),
    )
    for call in refusals:
        if not await refused(call):
            raise CheckFailedError("a help page was given to somebody it is not for")


@check(
    leaves=("M34.3.1.1", "M34.3.1.2"),
    sentence=(
        "A member of acceptance_a is told in plain sentences that they can ask about "
        "acceptance_a and not about acceptance_b, and a member of acceptance_b the reverse; a "
        "person who reaches nothing is told nothing about reach; and everybody is told what the "
        "install does with what is typed, read off the install's own configuration."
    ),
)
async def what_a_person_may_ask_about_and_what_is_done_is_said_plainly(h: Harness) -> None:
    from brain.adoption import privacy_posture
    from brain.help_routes import what_it_sees

    await h.found_departments()
    here, there, nobody = h.principal(A, "sees"), h.principal(B, "sees"), h.principal(A, "blind")
    await h.person(here, department=A, grants=((READS_KNOWLEDGE, Scope.department(A)),))
    await h.person(there, department=B, grants=((READS_KNOWLEDGE, Scope.department(B)),))
    await h.person(nobody, department=A)
    console = console_for(h)

    async def said(who: str) -> tuple[str, list[str]]:
        found = await what_it_sees(console.request(), await asking_as(h, who))
        return " ".join(one.text for one in found.can_ask_about), [one.key for one in found.privacy]

    mine, posture = await said(here)
    theirs, _ = await said(there)
    if A not in mine or B in mine:
        raise CheckFailedError("a person was not told exactly the departments they may ask about")
    if B not in theirs or A in theirs:
        raise CheckFailedError("a person in another department was told the wrong departments")
    blind, blind_posture = await said(nobody)
    if blind.strip():
        raise CheckFailedError("a person who reaches nothing was told something about reach")
    if posture != list(privacy_posture()) or blind_posture != posture:
        raise CheckFailedError("the privacy statements were not the install's own, for everybody")
