"""A learned fast-lane rule is promoted by people, once enough conversations would have used it
(M39.4.2.3).

`brain.memory.tiers` puts a learned fast-path rule at tier two and says what promotion needs: three
independent conversations inside thirty days (`may_promote`), and a person. It had nowhere to count
the conversations and nowhere to record the person, so on every install the answer was "not ready"
for ever. This module is the rules that close it; `brain.memory.promotion_store` holds the session,
`brain.promotion_routes` the console's press, and `0206` the database's half.

**An occurrence is a question the held rule would have answered, counted and changing nothing.**
The answer route matches the asker's department's held rules beside the live ones after the answer
has gone out, and a match is one row naming the learning, the conversation and the day. The write
is best effort: outside the answer's transaction, after the response, and a failure is a log line.
See `A_SHADOW_OCCURRENCE_NEVER_SLOWS_OR_FAILS_AN_ANSWER`.

**Who may press is who may undo a learning there.** `admin:learning` at the rule's department, or
over everything for a rule the whole install asks with, the authority the Learning screen's undo
already asks (`brain.console.govern_estate.UNDO_AUTHORITY`). Rejected: a new capability, which no
administrator on any install holds until somebody grants it, so the promote control would be
unreachable on every install on the day it ships.

**One person, or two when the rule answers with money or a sensitive column; never its proposer.**
A rule answering from an entity its connector declares as carrying money
(`brain.connectors.resolves.ResolvesAs.carries_money`), or with a column classified confidential or
restricted (an uploaded price list's cost column, which the tables already give a grant of its
own), needs a second, different person. That is the leash's boundary (`brain.agents.leash_moves`
asks a second person across money), read for a rule that only reads: a fast-lane rule answers with
no model, so a wrong one says a cost to everybody in the department in the same words every time.
See `A_RULE_THAT_ANSWERS_WITH_MONEY_NEEDS_TWO_PEOPLE` and `NOBODY_PROMOTES_WHAT_THEY_PROPOSED`.

**Applied by being written where live rules are.** The last press copies the rule into
`gate.fast_path_rule` in the promoter's name, with `learned_from` naming the learning, in the same
transaction; H's lane answers it from the next question. Nothing here, and no scheduled job, puts a
rule into effect by itself (the M16.3.4 install check holds that).

Task ids: M39.4.2.3
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final

from brain.core.field_policy import Classification
from brain.gate.fast_lane import FastPathRule

# ------------------------------------------------------------------ written-down reasons
#: Why the occurrence write is best effort.
A_SHADOW_OCCURRENCE_NEVER_SLOWS_OR_FAILS_AN_ANSWER: Final = (
    "Counting that a held rule would have answered a question is bookkeeping about a proposal, "
    "and the person asked a question. So the count is written after the response has gone, in a "
    "transaction of its own, and a failure to write it is a log line: an answer is never slower "
    "or refused because a learning could not be counted."
)

#: Why some rules need a second person.
A_RULE_THAT_ANSWERS_WITH_MONEY_NEEDS_TWO_PEOPLE: Final = (
    "A promoted rule answers with no model, in the same words, to everybody in its department. "
    "One that answers from an entity whose connector declares it carries money, or with a column "
    "classified confidential or restricted, such as a price list's cost, needs a second and "
    "different person to promote it; any other needs one."
)

#: Why the proposer never promotes.
NOBODY_PROMOTES_WHAT_THEY_PROPOSED: Final = (
    "A rule a person proposed is promoted by somebody else, at either press: agreement is the "
    "point of promotion, and a proposer agreeing with themselves is not agreement. Refused here "
    "and by the database's check."
)

#: The classifications that make a rule's answer a sensitive one.
SENSITIVE: Final[frozenset[Classification]] = frozenset(
    {Classification.CONFIDENTIAL, Classification.RESTRICTED}
)

# ------------------------------------------------------------------ what is said
NOT_READY: Final = (
    "Not enough separate conversations would have used this rule yet, so it cannot be promoted."
)
PROPOSED_IT: Final = "You proposed this rule, so somebody else promotes it."
SAME_PERSON: Final = "You took the first step, so a different person takes the second."
ALREADY_PROMOTED: Final = "This rule is already promoted."
AWAITING_SECOND: Final = (
    "The first step is taken. A different person who may promote rules here takes the second."
)
PROMOTED: Final = "The rule is promoted and answers from the next question."


class PromotionState(enum.StrEnum):
    """Where a learned rule stands. `0206` holds the same three words."""

    HELD = "held"
    AWAITING_SECOND = "awaiting_second"
    PROMOTED = "promoted"


class PromotionRefusedError(Exception):
    """A press this person may not make now, said to them in plain words."""


@dataclass(frozen=True)
class LearnedRule:
    """One learned rule as `mem.learned_rule` holds it."""

    memory_id: str
    rule: FastPathRule
    department: str | None
    proposed_by: str | None = None
    state: PromotionState = PromotionState.HELD
    needs_two: bool | None = None
    first_by: str | None = None
    promoted_by: str | None = None


@dataclass(frozen=True)
class Pressed:
    """What one press comes to: the state, who pressed first and who promoted, and its words."""

    state: PromotionState
    needs_two: bool
    first_by: str
    promoted_by: str | None
    said: str


def needs_two(*, carries_money: bool, answering: Classification | None) -> bool:
    """Whether promoting this rule takes two people. See
    `A_RULE_THAT_ANSWERS_WITH_MONEY_NEEDS_TWO_PEOPLE`."""
    return carries_money or answering in SENSITIVE


def press(learned: LearnedRule, *, by: str, ready: bool, two: bool) -> Pressed:
    """One person's press on a learned rule. Raises `PromotionRefusedError` with the words to say.

    `ready` is `tiers.may_promote` over the stored occurrences; `two` is `needs_two` for this rule
    as it stands. A rule waiting for its second person is judged by the `needs_two` its first press
    recorded, so the rule cannot change between the two presses.
    """
    if learned.state is PromotionState.PROMOTED:
        raise PromotionRefusedError(ALREADY_PROMOTED)
    if learned.proposed_by is not None and learned.proposed_by == by:
        raise PromotionRefusedError(PROPOSED_IT)
    if learned.state is PromotionState.AWAITING_SECOND:
        if learned.first_by == by:
            raise PromotionRefusedError(SAME_PERSON)
        first = learned.first_by or by
        return Pressed(PromotionState.PROMOTED, True, first, by, PROMOTED)
    if not ready:
        raise PromotionRefusedError(NOT_READY)
    if two:
        return Pressed(PromotionState.AWAITING_SECOND, True, by, None, AWAITING_SECOND)
    return Pressed(PromotionState.PROMOTED, False, by, by, PROMOTED)
