"""What a roll-up check reads: the checks that already proved each clause of a composite leaf.

Several leaves in the work breakdown say a whole area is "proved on an install" (entity resolution,
memory and context, the learning loop, the evaluation gate). Each clause of those sentences already
has a check, written for the narrower leaf it was built under, and none of them names the
composite. A composite check that asked the same questions again would be the same check twice in
one run, holding the ledger's lock twice, and the second copy would be one more thing to keep in
step with the first.

**So a roll-up asks nothing of the install. It reads what the checks that ran earlier in this run
came to** (`Harness.earlier`) and says whether every clause was shown. The suite runs the modules in
`CHECK_ORDER`, and a roll-up sits after every module it reads. If a check it needs has not run, the
roll-up says so and is not run; it never reads another run's rows, because a composite that read
the last run's results would pass on the strength of a commit that is no longer serving.

**A clause with no check naming it fails to be demonstrated, and that is said, not skipped.** A
roll-up whose clause had no check would otherwise pass on the others, which is the one way a
composite leaf could close on less than its sentence says. `a_clause_with_no_check` is the
sentence, and the unit test builds a clause nobody covers and shows it.

**A check that is not run holds the roll-up up, and one that failed fails it.** Both are named by
the check's own name and never by anything it read. A failed clause is the product's fault and is a
failed roll-up, so a person looking at the Install page sees one red row for the area as well as the
row for the check that went red; a clause that could not be asked on this install leaves the
composite not run for the same reason, which is what the sweep needs to leave the leaf open.

**Rejected:** running the clause checks again from inside the roll-up. It doubles the run, holds
the install's locks for twice as long, and a clause check that needs a switch or a connected store
would then be asked twice and answered twice, once by each author's reading of the same state.

Task ids: M14.8.1, M16.7.7, M16.7.8, M10.7.3, M1.8.5, M11.8.3
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from brain.ops.acceptance import (
    FAILED,
    NOT_RUN,
    PASSED,
    REASON_CHARS,
    Check,
    CheckFailedError,
    CheckNotRunError,
    registered,
)
from brain.ops.acceptance_run import Harness

# ------------------------------------------------------------------ written-down reasons
#: Why a roll-up that finds a clause with no check names it and does not pass.
A_CLAUSE_WITH_NO_CHECK_IS_NOT_DEMONSTRATED: Final = (
    "A composite leaf closes when each clause of its sentence was shown. A clause no check names "
    "was not shown, and a roll-up that passed on the clauses that were would close the leaf on "
    "less than it says."
)

#: Why a roll-up reads this run and no other.
A_ROLL_UP_READS_THIS_RUN_AND_NO_OTHER: Final = (
    "The last run's rows belong to a commit that may no longer be serving, so a roll-up that read "
    "them would pass on a product it is not checking. It reads the checks that ran before it in "
    "this run."
)

#: The composite leaves whose checks are roll-ups. A check naming only these asks nothing of the
#: install itself, so it is never counted as the evidence for a requirement.
ROLL_UP_LEAVES: Final[frozenset[str]] = frozenset(
    {
        "M1.8.5",
        "M10.7.3",
        "M11.8.3",
        "M14.8.1",
        "M16.7.7",
        "M16.7.8",
        "M28.5.1",
        "M28.5.2",
        "M28.5.3",
    }
)

#: How many requirement ids a reason lists before saying how many more there are.
IDS_IN_A_REASON: Final = 6


def is_roll_up(one: Check) -> bool:
    """Whether a check only reads other checks. See `ROLL_UP_LEAVES`."""
    return bool(one.leaves) and set(one.leaves) <= ROLL_UP_LEAVES


def checks_naming(leaf: str, *, excluding: str) -> tuple[Check, ...]:
    """Every check that asks something of the install and names this leaf, by name order."""
    return tuple(
        sorted(
            (
                one
                for one in registered()
                if leaf in one.leaves and one.name != excluding and not is_roll_up(one)
            ),
            key=lambda one: one.name,
        )
    )


def _said(names: Iterable[str], what: str) -> str:
    found = sorted(set(names))
    shown = ", ".join(found[:IDS_IN_A_REASON])
    more = len(found) - IDS_IN_A_REASON
    tail = f" and {more} more" if more > 0 else ""
    return f"{what}: {shown}{tail}"[:REASON_CHARS]


def _verdicts(
    h: Harness, evidence: Mapping[str, Sequence[Check]]
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Which of the keys have a check naming them, and what those checks came to this run.

    Returns the keys with no check, the checks that failed, the checks that were not run (or had
    not run yet), and the keys with at least one pass.
    """
    uncovered: list[str] = []
    failed: list[str] = []
    waiting: list[str] = []
    shown: list[str] = []
    for key, checks in evidence.items():
        if not checks:
            uncovered.append(key)
            continue
        passes = 0
        for one in checks:
            came_to = h.earlier.get(one.name)
            if came_to is None or came_to[0] == NOT_RUN:
                waiting.append(one.name)
            elif came_to[0] == FAILED:
                failed.append(one.name)
            elif came_to[0] == PASSED:
                passes += 1
        if passes:
            shown.append(key)
    return uncovered, failed, waiting, shown


async def clauses_demonstrated(
    h: Harness, clauses: Mapping[str, Sequence[str]], *, own: str
) -> None:
    """Each clause is shown by a check that named one of its leaves and passed in this run.

    `clauses` maps a clause, in a few words, to the leaves whose checks show it. Raises
    `CheckFailedError` if any such check failed, and `CheckNotRunError` if a clause has no check,
    or none of its checks passed because they were not run. See the module docstring.
    """
    evidence = {
        clause: tuple(one for leaf in leaves for one in checks_naming(leaf, excluding=own))
        for clause, leaves in clauses.items()
    }
    uncovered, failed, waiting, shown = _verdicts(h, evidence)
    if failed:
        raise CheckFailedError(_said(failed, "a check showing a clause of this leaf failed"))
    if uncovered:
        raise CheckNotRunError(_said(uncovered, "no check names a clause of this leaf"))
    unshown = [clause for clause in clauses if clause not in shown]
    if unshown:
        raise CheckNotRunError(
            _said(
                waiting or unshown,
                "a clause of this leaf was not shown because its check was not run in this run",
            )
        )
