"""Install check for the automation gallery's three newer outcomes: each says what starts it, which
kinds of source it uses and, where it drafts, who decides.

The gallery is read through the route the Automations tab draws, as a person who may open the tab
and install onto the agent, and the preview of an install is read through its own route. **Nothing
is installed**: a preview writes nothing, and the check rolls back anyway. What is shown is held to
what the product declares, and the outcomes that draft are held to a sentence naming the person's
step, because a gallery that offered an automation to draft customer records and said nothing of who
approves them would be offering a way round the approvals everything else here is built on.

**Not claimed:** that any of the three can be started. `brain.ops.automation_run.TASKS` says what
each still needs, and the check holds the gallery to saying so rather than to an install that would
start nothing.

Task ids: M17.7.5
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_agent_console import _asking, _console, _request
from brain.ops.acceptance_run import Harness
from brain.ops.acceptance_workspace import installed_agent

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2700

A, _B = RESERVED_DEPARTMENTS

THE_GALLERY_LACKS_AN_OUTCOME: Final = (
    "the gallery did not offer the daily brief, deal capture and email replies"
)
A_TRIGGER_WAS_NOT_DECLARED: Final = "an outcome in the gallery did not say what starts it"
A_SOURCE_WAS_NOT_DECLARED: Final = (
    "an outcome in the gallery did not say which kinds of source it uses"
)
A_DRAFT_HAD_NO_APPROVER: Final = (
    "an outcome that drafts did not say who decides before it takes effect"
)
A_READ_ONLY_OUTCOME_CLAIMED_ONE: Final = "an outcome that only reads claimed an approval step"
A_PRODUCT_NAME_WAS_USED: Final = "an outcome named a product or an address as its source"
THE_PREVIEW_HID_THE_APPROVAL: Final = "the preview of an install did not show the approval step"
THE_GALLERY_SAID_IT_RUNS: Final = "the gallery offered an outcome nothing can run without saying so"


@check(
    leaves=("M17.7.5",),
    sentence=(
        "The gallery an agent's Automations tab draws offers a daily brief, deal capture and "
        "drafted email replies; each says what starts it and which kinds of source it uses, the "
        "two that draft name the step at which a person decides, the brief claims none, and the "
        "preview of an install shows the same, with the tasks declared as not yet runnable."
    ),
)
async def the_gallery_offers_three_outcomes_that_say_who_decides(h: Harness) -> None:
    from brain.automation_gallery_routes import automation_gallery, automation_install_preview
    from brain.console.automation_gallery import AUTOMATION_AUTHORITY
    from brain.console.workspace import Tab, tab
    from brain.ops.acceptance_workspace import _everywhere, _planes
    from brain.ops.automation_run import task_declaration

    await h.found_departments()
    steward = h.principal(A, "steward")
    await h.person(
        steward,
        department=A,
        grants=_everywhere(
            AUTOMATION_AUTHORITY.value, tab(Tab.AUTOMATIONS).read.requires.value, *_planes()
        ),
    )
    agent = await installed_agent(h, steward, suffix="_gallery")
    app = _console(h)
    request = _request(app)
    asked = await _asking(h, steward, strong=True)

    gallery = await automation_gallery(request, agent, asked)
    cards = {one.template_id: one for one in gallery.items}
    wanted = ("daily_brief", "deal_capture", "email_replies")
    if not all(one in cards for one in wanted):
        raise CheckFailedError(THE_GALLERY_LACKS_AN_OUTCOME)
    for name in wanted:
        card = cards[name]
        if card.trigger not in {"schedule", "connector_event", "webhook"}:
            raise CheckFailedError(A_TRIGGER_WAS_NOT_DECLARED)
        if not card.connectors:
            raise CheckFailedError(A_SOURCE_WAS_NOT_DECLARED)
        if any(not part.isalpha() for word in card.connectors for part in word.split()):
            raise CheckFailedError(A_PRODUCT_NAME_WAS_USED)
        declaration = task_declaration(f"automation.{name}")
        if declaration is None or not declaration.needs:
            raise CheckFailedError(THE_GALLERY_SAID_IT_RUNS)
    if not (cards["deal_capture"].approval.strip() and cards["email_replies"].approval.strip()):
        raise CheckFailedError(A_DRAFT_HAD_NO_APPROVER)
    if cards["daily_brief"].approval:
        raise CheckFailedError(A_READ_ONLY_OUTCOME_CLAIMED_ONE)

    shown = await automation_install_preview(request, agent, "deal_capture", asked)
    if shown.approval != cards["deal_capture"].approval or not shown.approval:
        raise CheckFailedError(THE_PREVIEW_HID_THE_APPROVAL)
