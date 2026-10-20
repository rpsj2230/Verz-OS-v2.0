"""Telling a person which budget stopped them, and who can raise it, when they may know (M21.2.6).

Off because it changes the sentence everybody is refused with and the question it answers is the
owner's (needs-rupash item 224). While it is off every person a budget stops is told the one plain
sentence that names no budget, which is what an install ships with. While it is on, a person stopped
by their own allowance is told it is theirs and who raises it, and a person whose reach already
admits the spend of the budget's department is told which budget and until when, in
`brain.ops.spend.Refusal`'s own words; everybody else still gets the one sentence. The decision of
who is told what is `brain.console.spend_view.told_about`, which this only calls.

Task ids: M21.2.6
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

NAMED_BUDGET_REFUSAL: Final = Feature(
    name="named_budget_refusal",
    title="Tell a stopped person which budget, and who can raise it, when they may know",
    what=(
        "A person whose question a budget stops is told which budget it was and who can raise it, "
        "and until when, if the budget is their own allowance or the department's spend is "
        "something their reach already lets them read. Everybody else is told, as before, that a "
        "spending limit was reached and whoever manages it has been told."
    ),
    while_off=(
        "Everybody a budget stops is told the same sentence, which names no budget and no person "
        "who can raise it. The Spend screen lists each stop for those who may read it."
    ),
    read_by=("brain.ops.budget_stop_store:named_refusal_is_on",),
)
