"""Entity resolution proved on an install, rolled up from the checks that prove each clause.

M14.8.1 says entity resolution is proved on an install, and lists what that means: one client under
two names resolves to one entity keeping both aliases, a hard identifier links on its own while a
name-only match goes to review with its weighted evidence in words, a merge touching financial
records waits for a person, an unmerge restores the prior state and an old citation still resolves,
and an ambiguous question names both records with the review link and combines no figures. Every
clause has a check, written for the narrower leaf it was built under. M14.8.2 says every entity
resolution requirement in the register is demonstrated on an install.

This module holds the two roll-ups and nothing else, and **neither asks anything of the install**:
each reads what the clause checks came to earlier in this run, through
`brain.ops.acceptance_roll_up`, which is why this module sits after every one of them. See that
module for why a roll-up does not run its clauses again.

Task ids: M14.8.1, M14.8.2
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import check
from brain.ops.acceptance_roll_up import clauses_demonstrated, requirements_demonstrated
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, after every module they read.
CHECK_ORDER: Final = 879

#: The clauses of M14.8.1, each with the leaves whose checks show it.
CLAUSES: Final = {
    "one client under two names keeps both aliases": ("M14.1.2", "M14.5.2"),
    "a hard identifier links on its own": ("M14.3.1", "M14.6.2"),
    "a name-only match goes to review with its evidence in words": ("M14.3.4", "M14.6.4"),
    "a merge touching financial records waits for a person": ("M14.5.6",),
    "an unmerge restores the prior state and an old citation resolves": ("M14.5.3",),
    "an ambiguous question names both records and combines no figures": ("M14.6.5",),
}


@check(
    leaves=("M14.8.1",),
    sentence=(
        "Every clause of entity resolution's install proof was shown in this run: aliases kept "
        "across a merge, a hard identifier alone linking, a name-only match reviewed with its "
        "evidence in words, a merge across the money boundary held, an unmerge restoring the "
        "prior state, and an ambiguous question naming both records and combining no figures."
    ),
)
async def entity_resolution_is_shown_clause_by_clause_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(
        h, CLAUSES, own="entity_resolution_is_shown_clause_by_clause_in_this_run"
    )


@check(
    leaves=("M14.8.2",),
    sentence=(
        "Every entity resolution requirement in the register that rests on this leaf has a check "
        "naming each leaf of M14 it builds, and every such check passed in this run."
    ),
)
async def every_entity_resolution_requirement_is_demonstrated_in_this_run(h: Harness) -> None:
    await requirements_demonstrated(
        h,
        "M14.8.2",
        own="every_entity_resolution_requirement_is_demonstrated_in_this_run",
        prefix="M14.",
    )
