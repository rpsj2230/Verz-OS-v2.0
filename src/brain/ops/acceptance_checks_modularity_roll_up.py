"""Modularity proved on an install, rolled up from the checks that prove each clause.

M29.3.1 says modularity is proved on an install: a connector for a new API and a new channel record
are added and switched off from the console with no release, and a replaced vendor adapter takes
effect with no deploy. Three of the four clauses have a check, written for the narrower leaf it was
built under (a connector for an API nobody shipped, a channel switched off refusing inbound, and a
setting saying when it applies); none names the composite, and a composite check that asked the
same questions again would be the same check twice in one run (`brain.ops.acceptance_roll_up`
argues it). So this asks nothing of the install: it reads what those checks came to earlier in this
run, and sits after every one of them.

**The fourth clause is shown by the nearest check there is, and what it does not show is a
question.** A provider is switched on from the Models screen with a key and answers the screen's own
test with no deploy (M5.7.1). That is not a *replaced* key: rotating a real provider's key from a
check would handle a real key, which `brain.ops.acceptance_models` refuses by design
(`ROTATION_IS_NOT_CHECKED_BECAUSE_A_SLOT_CANNOT_BE_RETIRED`). Whether that is enough is
needs-rupash 227, and until it is answered M29.3.1 is held in `docs/proof-sweep-holds.json`, so a
pass here cannot close the leaf on less than its sentence.

Task ids: M29.3.1
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import check
from brain.ops.acceptance_roll_up import clauses_demonstrated
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, after every module they read.
CHECK_ORDER: Final = 2290

#: The clauses of M29.3.1, each with the leaves whose checks show it.
CLAUSES: Final = {
    "a connector for a new API is live with no release": ("M11.7.8",),
    "a channel is switched off from the console and refuses inbound": ("M27.15.43",),
    "a console setting says when it applies, with no deploy": ("M27.12.7",),
    "a model provider is switched on and tested from the console with no deploy": ("M5.7.1",),
}


@check(
    leaves=("M29.3.1",),
    sentence=(
        "Every clause of the modularity proof was shown in this run: a connector for an API "
        "nobody shipped live with no release, a channel switched off from the console refusing "
        "inbound, a console setting saying when it applies, and a model provider switched on and "
        "tested from the console with no deploy."
    ),
)
async def modularity_is_shown_clause_by_clause_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(h, CLAUSES, own="modularity_is_shown_clause_by_clause_in_this_run")
