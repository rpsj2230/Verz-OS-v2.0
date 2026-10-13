"""Memory, context and learning proved on an install, rolled up from the checks that prove each
clause.

M16.7.7 says memory and context are proved on an install and M16.7.8 says the learning loop is.
(That every requirement in the register is demonstrated, M16.7.9 and M16.7.11, is the requirement-
area checks' own.) M16.3.2, M16.7.3 and M16.7.14 are smaller sentences whose clauses were each
shown by a check written for a neighbouring leaf: tier one automatic for one person only, a learned
rule offered for review and applied only after a person approves it, and a promotion that records
who agreed and takes effect on the next run.

This module holds those five roll-ups and asks nothing of the install: each reads what the clause
checks came to earlier in this run, through `brain.ops.acceptance_roll_up`, which says why a roll-
up does not run its clauses again and what it says of a clause nothing proves. **Three of the five
are not run today, and each names what is missing**: a memory the source contradicts being demoted
(M16.4.3) and a project's context read from its source (M16.6.2, which waits on needs-rupash 137)
for memory and context; a failed workflow step and an evaluation opening a candidate (M17.6.7,
M28.4.1) for the learning loop; and a tier-three item decided from the console, which no surface
does, for the promotion. That is the state of the product and not an omission here, and the roll-
ups close on the day the last clause has a check.

Task ids: M16.3.2, M16.7.3, M16.7.7, M16.7.8, M16.7.14
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import check
from brain.ops.acceptance_roll_up import clauses_demonstrated
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, after every module they read.
CHECK_ORDER: Final = 880

#: M16.3.2's clauses, each with the leaves whose checks show it.
TIER_ONE: Final = {
    "a preference is one person's own (M16.1.2, M16.6.3)": ("M16.1.2", "M16.6.3"),
    "an entity link needs a hard identifier (M14.3.1)": ("M14.3.1",),
    "a mark is counted and changes nothing (M16.7.4)": ("M16.7.4",),
    "signals are counted by kind and never by person (M16.2.8)": ("M16.2.8",),
}

#: M16.7.3's clauses.
OFFERED: Final = {
    "a rule is offered once conversations agree (M16.3.4)": ("M16.3.4",),
    "it takes effect only when a person approves, who is recorded (M39.4.2.3)": ("M39.4.2.3",),
}

#: M16.7.14's clauses. The second has no check and no surface to check: see the module docstring
#: of `brain.memory.review`, whose queue lists a tier-three item and cannot decide it.
PROMOTED: Final = {
    "a tier-two rule is promoted in a person's name and applies next (M39.4.2.3)": ("M39.4.2.3",),
    "a tier-three item is decided from the console (M16.7.14)": ("M16.7.14",),
}

#: M16.7.7's clauses.
MEMORY_AND_CONTEXT: Final = {
    "session memory ends with its thread (M16.1.1)": ("M16.1.1",),
    "a preference applies only to its owner (M16.1.2)": ("M16.1.2",),
    "project context follows its source (M16.6.2)": ("M16.6.2",),
    "a memory the source contradicts is demoted (M16.4.3)": ("M16.4.3",),
    "removing an entitlement stops replay (M16.4.4)": ("M16.4.4",),
    "a person edits and forgets their memory (M16.4.2)": ("M16.4.2",),
    "the trace names the context kinds (M16.6.1)": ("M16.6.1",),
}

#: M16.7.8's clauses.
LEARNING_LOOP: Final = {
    "an unhelpful mark changes nothing (M16.7.4)": ("M16.7.4",),
    "a correction is held, grouped and decided (M16.6.5, M16.6.6)": ("M16.6.5", "M16.6.6"),
    "the digest lists it with undo (M16.5.1)": ("M16.5.1",),
    "a failed workflow step opens a candidate (M17.6.7)": ("M17.6.7",),
    "an evaluation opens a candidate (M28.4.1)": ("M28.4.1",),
    "an unanswered question is a knowledge gap (M27.7.18)": ("M27.7.18",),
}


@check(
    leaves=("M16.3.2",),
    sentence=(
        "Tier one is automatic for one person only: a person's preference is theirs alone, an "
        "entity link needs a hard identifier, and a mark and a negative signal are counted and "
        "move nothing, each shown by the check naming it in this run."
    ),
)
async def tier_one_is_one_persons_own_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(h, TIER_ONE, own="tier_one_is_one_persons_own_in_this_run")


@check(
    leaves=("M16.7.3",),
    sentence=(
        "A learned rule is offered for review once separate conversations agree and takes effect "
        "only when a person approves it, with the approval recorded, each shown by the check "
        "naming it in this run."
    ),
)
async def a_learned_rule_waits_for_approval_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(h, OFFERED, own="a_learned_rule_waits_for_approval_in_this_run")


@check(
    leaves=("M16.7.14",),
    sentence=(
        "A tier-two rule promoted from the console records who agreed and takes effect on the "
        "next run, and a tier-three item decided from the console does the same, each shown by "
        "the check naming it in this run."
    ),
)
async def a_promotion_and_a_gated_decision_record_who_agreed_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(
        h, PROMOTED, own="a_promotion_and_a_gated_decision_record_who_agreed_in_this_run"
    )


@check(
    leaves=("M16.7.7",),
    sentence=(
        "Every clause of memory and context's install proof was shown in this run: session "
        "memory, a preference's owner, project context, a demoted memory, replay stopping with "
        "an entitlement, a person's own edit and forget, and the trace naming its context."
    ),
)
async def memory_and_context_are_shown_clause_by_clause_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(
        h, MEMORY_AND_CONTEXT, own="memory_and_context_are_shown_clause_by_clause_in_this_run"
    )


@check(
    leaves=("M16.7.8",),
    sentence=(
        "Every clause of the learning loop's install proof was shown in this run: a mark that "
        "changes nothing, a correction held and decided, the digest's undo, a failed step and an "
        "evaluation each opening a candidate, and an unanswered question as a knowledge gap."
    ),
)
async def the_learning_loop_is_shown_clause_by_clause_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(
        h, LEARNING_LOOP, own="the_learning_loop_is_shown_clause_by_clause_in_this_run"
    )
