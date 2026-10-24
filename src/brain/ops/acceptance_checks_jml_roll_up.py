"""Joiner, mover and leaver handling proved on an install, rolled up from the checks that prove each
clause.

M26.4.1 says a person moved between departments loses the old department's knowledge, agents, cached
answers and memories on their next request and gains the new ones with no reindex, a delegation that
now exceeds their reach is suspended, a leaver's agents pass to the department administrator, an
item they own but can no longer reach leaves their workspace, a run in progress stops using a
revoked grant at its next step, and an external person and a service key stop working when their end
date or owner lapses. M26.2.7 says there is a test covering every one of the mover leaves above it.
Each clause has, or should have, a check written for the narrower leaf it was built under, and a
composite that asked the same questions again would be the same check twice in one run
(`brain.ops.acceptance_roll_up` argues it). So these ask nothing of the install: they read what the
clause checks came to earlier in this run, and sit after every one of them.

**Two clauses of M26.4.1 have no check yet, and these say so instead of passing on the rest.** A
service key stopping with its owner (M1.8.2) and an item a person owns but can no longer reach
leaving their workspace (named by no leaf) are each a clause that no check names today. (A personal
agent following its owner, M26.2.2, has had one since 2026-10-21; a mover's memories of the old
reach, M26.2.5, and an external person's end date, M1.8.1, have had one since 2026-10-24, and
a run stopping on a revoked grant, M13.8.2, one before that.) `clauses_demonstrated` leaves a
composite whose clause has no check not run and names the clause, so M26.4.1 stays open until every
clause is shown, and a pass cannot close it on less than its sentence. M26.2.7 asks the six mover
leaves only, each of which has a check, so it can pass wherever those checks ran and passed.

**Rejected: a roll-up that passes on the clauses that have a check.** It would close both leaves on
the three or four things that happen to be proved, which is the failure
`brain.ops.acceptance_roll_up` exists to prevent.

Task ids: M26.2.7, M26.4.1
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import check
from brain.ops.acceptance_roll_up import clauses_demonstrated
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, after every module they read.
CHECK_ORDER: Final = 2800

#: The clauses of M26.2.7, one for each leaf of the mover group, with the leaf whose check shows it.
MOVER_CLAUSES: Final = {
    "entitlements re-resolve on the next request": ("M26.2.1",),
    "a personal agent follows its owner": ("M26.2.2",),
    "a delegation is suspended and never narrowed": ("M26.2.3",),
    "cached answers are unreachable by construction": ("M26.2.4",),
    "memories of the old reach are not replayed": ("M26.2.5",),
    "knowledge access changes with no reindex": ("M26.2.6",),
}

#: The clauses of M26.4.1. The last has no leaf, because no leaf in the breakdown names it.
CLAUSES: Final = {
    "a mover's knowledge changes with no reindex": ("M26.2.6",),
    "a mover's personal agents follow them": ("M26.2.2",),
    "a mover is not served an answer cached before": ("M26.2.4",),
    "a mover's memories of the old reach are not replayed": ("M26.2.5",),
    "a delegation beyond a mover's reach is suspended": ("M26.2.3",),
    "a leaver's agents pass to the administrator": ("M26.3.2",),
    "a run in progress stops using a revoked grant": ("M13.8.2",),
    "an external person stops on their end date": ("M1.8.1",),
    "a service key stops when its owner lapses": ("M1.8.2",),
    "an item a person can no longer reach leaves their workspace": (),
}


@check(
    leaves=("M26.2.7",),
    sentence=(
        "Every clause of the mover group was shown in this run: entitlements re-resolving on the "
        "next request, a personal agent following its owner, a delegation suspended and never "
        "narrowed, cached answers unreachable, memories of the old reach not replayed, and "
        "knowledge access changing with no reindex."
    ),
)
async def every_mover_leaf_is_shown_clause_by_clause_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(
        h, MOVER_CLAUSES, own="every_mover_leaf_is_shown_clause_by_clause_in_this_run"
    )


@check(
    leaves=("M26.4.1",),
    sentence=(
        "Every clause of joiner, mover and leaver handling was shown in this run: a mover's "
        "knowledge, agents, cached answers and memories changing with no reindex, a delegation "
        "beyond their reach suspended, a leaver's agents passing on, a run stopping on a revoked "
        "grant, and an external person and a service key stopping when their end date or owner "
        "lapses."
    ),
)
async def joiner_mover_leaver_is_shown_clause_by_clause_in_this_run(
    h: Harness,
) -> None:
    await clauses_demonstrated(
        h, CLAUSES, own="joiner_mover_leaver_is_shown_clause_by_clause_in_this_run"
    )
