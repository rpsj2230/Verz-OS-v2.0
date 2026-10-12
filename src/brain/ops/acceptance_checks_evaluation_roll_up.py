"""The evaluation gate and per-person reach proved on an install, rolled up from the checks that
prove each clause.

M28.5.1 says per-person reach is proved on an install: the same question asked as a junior and as a
finance lead on the web and in a chat channel, the junior's answer withholding what the lead's
shows, a tool the junior cannot use absent from the run, a refused source reading as one that does
not exist, and a grant revoked mid-session stopping a cached answer. M28.5.2 says the evaluation
gate is proved: golden questions and permission canaries asked through the real gate as each
persona block a regressed change, and the scheduled canary run alerts when a canary fails.

Each clause already has a check, or has none, and this module holds the two roll-ups and asks
nothing of the install: see `brain.ops.acceptance_roll_up`. **M28.5.2 is not run today and says
why**: no golden question is asked on an install and nothing records a score by release (M28.1.4),
so the gate it describes does not yet have its first half. M28.5.3 has no roll-up here for the same
reason; it is a build, and needs a table.

Task ids: M28.5.1, M28.5.2
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import check
from brain.ops.acceptance_roll_up import clauses_demonstrated
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, after every module they read.
CHECK_ORDER: Final = 881

#: M28.5.1's clauses.
PER_PERSON_REACH: Final = {
    "one agent answers at each asker's own reach on the web and in chat (M13.7.5)": ("M13.7.5",),
    "the narrower reader is withheld fields and records (M7.5.2, M15.2.7)": (
        "M7.5.2",
        "M15.2.7",
    ),
    "a tool the asker cannot use is absent from the run (M28.2.3)": ("M28.2.3",),
    "a refused source reads as an absent one (M28.2.1, M11.5.5)": ("M28.2.1", "M11.5.5"),
    "a revoked grant stops a cached answer (M6.5.2)": ("M6.5.2",),
}

#: M28.5.2's clauses.
THE_GATE: Final = {
    "golden questions are asked on the install (M28.1.4)": ("M28.1.4",),
    "canaries ask as each persona (M28.2.1, M28.2.3)": ("M28.2.1", "M28.2.3"),
    "the scheduled run alerts when a canary fails (M28.2.4)": ("M28.2.4",),
}


@check(
    leaves=("M28.5.1",),
    sentence=(
        "Every clause of per-person reach's install proof was shown in this run: one agent at each "
        "asker's reach, the narrower reader withheld fields and records, a tool absent from a run, "
        "a refusal reading as an absence, and a revoked grant stopping a cached answer."
    ),
)
async def per_person_reach_is_shown_clause_by_clause_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(
        h, PER_PERSON_REACH, own="per_person_reach_is_shown_clause_by_clause_in_this_run"
    )


@check(
    leaves=("M28.5.2",),
    sentence=(
        "Every clause of the evaluation gate's install proof was shown in this run: golden "
        "questions asked on the install, canaries asked as each persona, and the scheduled run "
        "alerting when a canary fails."
    ),
)
async def the_evaluation_gate_is_shown_clause_by_clause_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(
        h, THE_GATE, own="the_evaluation_gate_is_shown_clause_by_clause_in_this_run"
    )
