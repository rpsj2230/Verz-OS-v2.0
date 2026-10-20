"""The switch on telling a budget's administrators that it is nearing its ceiling or has run out.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off because it is a new message sent to people unasked, in the chat tool each last used, and the
owner has not yet seen it work. With it off a budget still stores its warning fractions, still
records a used-up budget with who was to be told (`brain.ops.budget_stop_store`), and shows both on
the Spend screen; nothing is sent. The messages name a budget and how far it has got and never an
amount. See `brain.budget_told`.

Task ids: M21.1.1, M21.2.5
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

BUDGET_WARNINGS_TOLD: Final = Feature(
    name="budget_warnings_told",
    title="Tell a budget's administrators when it is nearing its ceiling or has run out",
    what=(
        "Whoever holds the budget authority over a company or department budget is told, once in "
        "each period, in the chat tool they last used, when spending reaches each warning fraction "
        "the budget carries (seventy and ninety per cent unless set otherwise), and is told when "
        "the budget has run out and whether questions are being refused for it. The message names "
        "the budget and how far it has got, never an amount and never a question."
    ),
    while_off=(
        "Nobody is sent a message about a budget. The warning fractions are still stored with the "
        "budget, a used-up budget is still recorded with who it was to be told to, and the Spend "
        "screen still shows what has stopped."
    ),
    read_by=("brain.budget_told:budget_warnings_are_on",),
)
