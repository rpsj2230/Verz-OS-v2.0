"""Install acceptance check for the wave-four milestone: automations running, approvals landing in
Lark.

The milestone leaf says what must be live once wave four is done, and it has two clauses that each
already have a check of their own: an automation installed from the gallery that runs as its owner
and is listed with its next run (`acceptance_workspace`), and an approval whose card is sent when it
is raised to its approver's own chat and to nobody else (`acceptance_checks_cards`). The
milestone asks whether they hold on **one install, in one transaction, as a person meets them**,
which is a different question from whether each holds on its own: both found their departments,
their administrators and their reserved people, and a pair of checks each green on a database of
their own can still collide on the one an install is.

**The press that decides a card is not awaited again here.** The card checks that decide a press
and the one that sends a raised approval each build the same reserved approvers, so two of them
cannot share a transaction, and `a_card_press_decides_as_its_approver_alone_and_closes_the_card`
keeps its own proof of the decision. **This check awaits the two it uses as they stand rather than
copying a line of either**, for the room check's reason in `acceptance_checks_cards`: a copy is a
second place for the rule to be subtly wrong.

**The Lark transport is the chat checks' list, and the sentence says so.** An approval card that
"lands in Lark" on this install is sent to a transport that keeps the request and answers with
Lark's documented success, so nothing reaches a real chat. A card a person's own Lark shows is the
owner's to see, and the milestone's task stays held on it (`docs/proof-sweep-holds.json`).

**The one automation that can run is the one that runs.** Of the product's four automation
templates one has a performer (`brain.ops.automation_run.TASKS`); the other three say what they
still need. The check proves the run the install can make and does not claim the three.

Task ids: M38.2.2.5
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 640


@check(
    leaves=("M38.2.2.5",),
    sentence=(
        "On one install, an automation installed from the gallery is started by a second "
        "administrator, runs as its owner and is listed with its next run; a promotion raised "
        "the same minute sends its card to its approver's own Lark chat and to nobody else. "
        "Lark's transport is a stand-in that keeps what it is sent."
    ),
)
async def automations_run_and_approvals_land_in_lark_on_one_install(h: Harness) -> None:
    from brain.ops.acceptance_checks_cards import (
        a_raised_approval_is_sent_to_its_approver_s_kept_address,
    )
    from brain.ops.acceptance_workspace import (
        an_agents_automation_is_installed_started_run_and_removed,
    )

    await an_agents_automation_is_installed_started_run_and_removed(h)
    await a_raised_approval_is_sent_to_its_approver_s_kept_address(h)
