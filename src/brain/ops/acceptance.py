"""Install acceptance checks: which leaves each check proves, and what the page may say about it.

A task counts as done only when it is seen working on the owner's install, and seeing it by hand one
screen at a time is what made the proof slower than the build. The owner decided on 2026-09-28 that
checks run on his server after each deploy, as a clearly labelled test department and test people,
remove their test data afterwards, and record their results so tasks can be closed from them. This
module is the registry and the verdict; `brain.ops.acceptance_run` is the half that opens a
connection, and `brain.ops.acceptance_checks` holds the checks.

**A check is one function with its leaf ids.** `@check(leaves=..., sentence=...)` over an async
function taking the harness registers it, and the sentence is the one the Install page shows beside
the result: what was done on the install, in the words a person closing the task would write. A
later package adds a check by writing one more function in `brain.ops.acceptance_checks`, or a
module of its own named in `CHECK_MODULES`, and nothing else changes. Rejected: a hand-kept tuple of
checks beside the functions, which is a second list to forget.

**The shape is `brain.ops.post_deploy`'s, and so is the rule about words.** A check passes, fails or
was not run, and the reason stored beside it is a sentence the check's source wrote, never a value
it read: a failing check that quoted the row it read would put a client's data on a page anybody can
fetch. `CheckFailedError` and `CheckNotRunError` carry that sentence, a test holds every one of them
to a string literal in the source, and anything else a check raises is recorded by its type name
alone, for `brain.jobs_routes.AN_EXCEPTION_MESSAGE_IS_A_VALUE_UNTIL_SHOWN_OTHERWISE`'s reason. See
`A_RESULT_NAMES_NO_DATA`.

**What the run may touch is written down here, where a reviewer reads it first.** The reserved
departments and the reserved principals, every database write inside a transaction that is always
rolled back, what the database cannot roll back removed by name, the smallest provider call that
proves a path, and nothing that reaches a real person. Each is a constant below and each is held by
a test in `tests/unit/test_acceptance.py`.

Task ids: M38.5.1
"""

from __future__ import annotations

import enum
import importlib
import re
from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from brain.ops.post_deploy import FAILED, NOT_RUN, PASSED

if TYPE_CHECKING:
    from brain.ops.acceptance_run import Harness

__all__ = [
    "FAILED",
    "NOT_RUN",
    "PASSED",
    "Check",
    "CheckFailedError",
    "CheckNotRunError",
    "Occasion",
    "Result",
    "check",
    "registered",
]

# ------------------------------------------------------------------ written-down reasons
#: The owner's decision this module rests on, so nobody reads a test department as a liberty taken.
THE_OWNER_APPROVED_A_TEST_DEPARTMENT_ON_HIS_INSTALL: Final = (
    "On 2026-09-28 the owner approved checks that run on his server after each deploy, using a "
    "clearly labelled test department and test people and removing their test data afterwards. "
    "brain.ops.canary_run refuses a synthetic account because nobody approved one; this is the "
    "approval, and it reaches exactly the departments and principals reserved below."
)

#: Why every row a check writes is in two reserved departments and nowhere else.
TEST_DATA_LIVES_ONLY_IN_RESERVED_DEPARTMENTS: Final = (
    "Every department a check founds is acceptance_a or acceptance_b, every principal it makes "
    "sits in one of them, and every document, grant and switch it writes is scoped to one of "
    "them. A check needing company-wide data writes a word nothing else holds, so no real "
    "question can be about it."
)

#: Why a reserved principal is not an account.
A_RESERVED_PRINCIPAL_CANNOT_SIGN_IN: Final = (
    "A reserved principal exists only inside a check's transaction: no committed identity binding "
    "resolves to it, no staff record places it, and its not_after is an hour ahead. Every person a "
    "check acts as is one of these, made for the check and gone with it, so the owner creates no "
    "login, names no subject and sets no value, and the run never sets, reads or holds a password "
    "or a token for anybody."
)

#: Why the run stops before it writes anything when a reserved department is in use.
A_RESERVED_DEPARTMENT_HOLDING_A_REAL_PERSON_STOPS_THE_RUN: Final = (
    "If a person on this install sits in acceptance_a or acceptance_b, or a department by that "
    "name exists, the checks would grant, read and switch things in a department somebody uses. "
    "So the run looks first, and finding anybody who is not a reserved principal records every "
    "check as not run with this sentence and writes nothing else."
)

#: Why nothing a check writes to the database survives it.
NOTHING_A_CHECK_WRITES_IS_EVER_COMMITTED: Final = (
    "Each check runs inside one database transaction that is rolled back when it ends, however it "
    "ends, and every session it hands the product's services is joined to that transaction, so a "
    "commit inside a service releases a savepoint and nothing more. Departments, people, grants, "
    "documents, switches, request rows and their ledger entries exist for the length of the check "
    "and only inside it. A process killed halfway leaves nothing either, because PostgreSQL rolls "
    "back an open transaction whose connection is gone."
)

#: Why what the database cannot roll back is named and removed.
WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME: Final = (
    "A limit window lives in Valkey, outside any transaction. A check using one uses subjects only "
    "it holds, a reserved principal, a channel and an agent named for this run, and registers "
    "each key it touched, which the run deletes when the check ends whatever happened. No shared "
    "key is ever read, written or deleted."
)

#: Why a provider call is as small as it is.
A_PROVIDER_CALL_IS_THE_SMALLEST_THAT_PROVES_THE_PATH: Final = (
    "A check that reaches a model sends the fixed sentence the Models screen's check sends, asks "
    "for at most sixteen tokens, and sends one call per provider it proves. Each call is metered "
    "like any other and costs a fraction of a cent, and none carries a word of the company's data."
)

#: Why the run is invisible to the people using the install.
NOTHING_THE_RUN_DOES_REACHES_A_REAL_PERSON: Final = (
    "No check sends a notification, an email or a channel message to anybody: a channel reply "
    "goes to a transport that keeps the request and sends nothing. Because every row is "
    "uncommitted, no other connection can read a test document, grant or request row, so nothing "
    "the run writes can reach a real person's answer, screen or report."
)

#: Why a stored result says so little.
A_RESULT_NAMES_NO_DATA: Final = (
    "A result is the check's name, the leaves it proves, passed, failed or not run, when, and a "
    "reason that is a sentence the check's source wrote. It never holds a value the check read, "
    "an exception's message or a row's contents, because the page serving it is public and a "
    "reason quoting a row would be a copy of it."
)

#: Why a check stopped by a model call says how the call ended, and nothing else about it.
A_MODEL_CALL_THAT_STOPS_A_CHECK_IS_NAMED_BY_HOW_IT_ENDED: Final = (
    "A check stopped by a provider's failure used to be recorded as the exception's type, and a "
    "moonshot check that timed out on 2026-09-29 read as a planning fault until the worker's log "
    "was read. How a call ended is a closed vocabulary the Models screen already words for an "
    "administrator, and a planner's refusal carries the product's own sentence, so the reason "
    "names those and never the step, the model or the provider's words."
)

#: What a reason begins with when a model call stopped the check.
A_MODEL_CALL_STOPPED_THE_CHECK: Final = "a model call stopped the check: "

#: What a reason begins with when the planner found no step it could try.
NO_STEP_COULD_BE_TRIED: Final = "no step of the ladder could be tried: "

#: Why the scheduled control runs once per commit.
ONE_RUN_PER_DEPLOYED_COMMIT: Final = (
    "The control ticks often and runs the checks only when the commit this process serves has no "
    "recorded run, or a person asked for one since the last. A deploy is checked once within "
    "minutes of arriving; a quiet install is not checked again and again, and a person who wants "
    "a second look presses run now on the Scheduled jobs screen."
)

# ------------------------------------------------------------------------ the figures
#: The two departments every check writes into. Slugs under `brain.core.department.SLUG_PATTERN`,
#: which admits an underscore and no hyphen.
RESERVED_DEPARTMENTS: Final = ("acceptance_a", "acceptance_b")

#: What every reserved principal's id begins with. `brain.audit.ledger.IDENTIFIER` admits the dot.
RESERVED_PRINCIPAL_PREFIX: Final = "acceptance."

#: A check's name: what the result row and the page key on.
CHECK_NAME: Final = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

#: A WBS leaf id. Positional, so a check naming one is checked against `docs/wbs.json` by a test.
LEAF_ID: Final = re.compile(r"^M[0-9]+(\.[0-9]+){2,3}$")

#: The longest reason a result may carry, which is also the column's width.
REASON_CHARS: Final = 240

#: The longest sentence a check may be described by.
SENTENCE_CHARS: Final = 400

#: The modules whose `@check` functions make up the suite, imported by `registered`.
CHECK_MODULES: Final = (
    "brain.ops.acceptance_checks",
    "brain.ops.acceptance_oversight",
    "brain.ops.acceptance_checks_chat",
    "brain.ops.acceptance_checks_skills",
    "brain.ops.acceptance_models",
    "brain.ops.acceptance_routing",
    "brain.ops.acceptance_audit",
    "brain.ops.acceptance_checks_connectors",
    "brain.ops.acceptance_checks_tools",
    "brain.ops.acceptance_checks_lifecycle",
    "brain.ops.acceptance_checks_tables",
    "brain.ops.acceptance_answers",
    "brain.ops.acceptance_checks_connector_framework",
    "brain.ops.acceptance_checks_capacity",
    "brain.ops.acceptance_retrieval",
    "brain.ops.acceptance_checks_memory",
    "brain.ops.acceptance_checks_deployment",
    "brain.ops.acceptance_ingest",
    "brain.ops.acceptance_threads",
    "brain.ops.acceptance_knowledge",
    "brain.ops.acceptance_checks_automation",
    "brain.ops.acceptance_checks_procedures",
)


class AcceptanceError(Exception):
    """A check was declared in a shape the registry cannot record or a page cannot show."""


class CheckFailedError(Exception):
    """The check saw the install not do what its leaves say. The reason is a literal sentence."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CheckNotRunError(Exception):
    """The check could not be asked on this install, and says why in a literal sentence."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Occasion(enum.StrEnum):
    """Why a run happened: a commit nobody had checked, or a person asking."""

    DEPLOY = "deploy"
    REQUEST = "request"


#: What a check is: an async function over the harness that returns when the install passed.
type CheckBody = Callable[[Harness], Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class Check:
    """One check: its name, the leaves it proves, the sentence the page shows, and the function."""

    name: str
    leaves: tuple[str, ...]
    sentence: str
    run: CheckBody

    def __post_init__(self) -> None:
        if not CHECK_NAME.match(self.name):
            msg = f"a check named {self.name!r} cannot be a result row's key"
            raise AcceptanceError(msg)
        if not self.leaves:
            msg = f"check {self.name!r} proves no leaf, so its result can close nothing"
            raise AcceptanceError(msg)
        for leaf in self.leaves:
            if not LEAF_ID.match(leaf):
                msg = f"check {self.name!r} names {leaf!r}, which is not a WBS leaf id"
                raise AcceptanceError(msg)
        if len(set(self.leaves)) != len(self.leaves):
            msg = f"check {self.name!r} names a leaf twice"
            raise AcceptanceError(msg)
        if not self.sentence.strip() or len(self.sentence) > SENTENCE_CHARS:
            msg = f"check {self.name!r} needs a sentence of at most {SENTENCE_CHARS} characters"
            raise AcceptanceError(msg)


_REGISTERED: list[Check] = []


def check(*, leaves: Sequence[str], sentence: str) -> Callable[[CheckBody], CheckBody]:
    """Register the decorated function as a check named after it, proving `leaves`."""

    def register(body: CheckBody) -> CheckBody:
        one = Check(
            name=getattr(body, "__name__", ""),
            leaves=tuple(leaves),
            sentence=sentence,
            run=body,
        )
        if any(held.name == one.name for held in _REGISTERED):
            msg = f"two checks are named {one.name!r}, and a result row cannot tell them apart"
            raise AcceptanceError(msg)
        _REGISTERED.append(one)
        return body

    return register


def registered(modules: Iterable[str] = CHECK_MODULES) -> tuple[Check, ...]:
    """Every check in the suite: module by module as `modules` names them, each in its own order.

    Ordered by the names rather than by `_REGISTERED`, which is import order: with a second check
    module, whichever a process happened to import first would lead the Install page.
    """
    named = tuple(modules)
    for module in named:
        importlib.import_module(module)
    return tuple(
        one
        for module in named
        for one in _REGISTERED
        if getattr(one.run, "__module__", "") == module
    )


# --------------------------------------------------------------------------- results
@dataclass(frozen=True)
class Result:
    """What one check came to on one run, as the table keeps it and the page shows it."""

    name: str
    leaves: tuple[str, ...]
    outcome: str
    checked_at: datetime
    reason: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in (PASSED, FAILED, NOT_RUN):
            msg = f"{self.outcome!r} is not passed, failed or not run"
            raise AcceptanceError(msg)
        if len(self.reason) > REASON_CHARS:
            msg = f"a reason is at most {REASON_CHARS} characters"
            raise AcceptanceError(msg)


def reason_for(exc: BaseException) -> tuple[str, str]:
    """The outcome and the stored reason for whatever a check raised.

    A verdict carries its own literal sentence, cut to the column. A model call that stopped the
    check is named by how it ended, in the Models screen's words for that ending, and a planner
    that found no step to try by its own public sentence; see
    `A_MODEL_CALL_THAT_STOPS_A_CHECK_IS_NAMED_BY_HOW_IT_ENDED`. Anything else is a failure named
    by its type alone: its message may quote a row, a key or an address.
    """
    from brain.models.driver import ProviderUnavailable
    from brain.models.routing import NoCompliantRoute

    if isinstance(exc, CheckFailedError):
        return FAILED, exc.reason[:REASON_CHARS]
    if isinstance(exc, CheckNotRunError):
        return NOT_RUN, exc.reason[:REASON_CHARS]
    if isinstance(exc, TimeoutError):
        return FAILED, "the check did not finish in the time it is allowed"
    if isinstance(exc, ProviderUnavailable):
        # Imported here: the route module brings FastAPI, and only a failed call needs it.
        from brain.provider_routes import CHECK_TOLD, failure_outcome

        told = CHECK_TOLD[failure_outcome(exc.failure)]
        return FAILED, (A_MODEL_CALL_STOPPED_THE_CHECK + told)[:REASON_CHARS]
    if isinstance(exc, NoCompliantRoute):
        return FAILED, (NO_STEP_COULD_BE_TRIED + exc.public_message)[:REASON_CHARS]
    return FAILED, f"the check stopped on {type(exc).__name__}; the worker's log says where"[
        :REASON_CHARS
    ]


def owed(
    *,
    serving: str,
    checked: Iterable[str],
    asked_at: datetime | None,
    last_started: datetime | None,
) -> Occasion | None:
    """Whether a run is owed now, and why. See `ONE_RUN_PER_DEPLOYED_COMMIT`.

    A request counts when nothing has started since it was made; a commit counts when no run of
    it is recorded. A request is answered first, so a person asking on a commit already checked
    is told about the run they asked for.
    """
    if asked_at is not None and (last_started is None or last_started < asked_at):
        return Occasion.REQUEST
    if serving not in set(checked):
        return Occasion.DEPLOY
    return None


def summary(results: Sequence[Result]) -> str:
    """How a run came out, in counts of checks. A check's name is the product's, never data."""
    counts = dict.fromkeys((PASSED, FAILED, NOT_RUN), 0)
    for one in results:
        counts[one.outcome] += 1
    failing = ", ".join(one.name for one in results if one.outcome == FAILED)
    said = f"{counts[PASSED]} passed, {counts[FAILED]} failed, {counts[NOT_RUN]} not run"
    return f"{said} ({failing})" if failing else said


# ------------------------------------------------------------------------- the page
def served(
    serving: str,
    checks: Sequence[Check],
    recorded: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """The public document for one commit: every check in the suite with its newest result.

    `recorded` is that commit's rows, any order. A check with no row says not run and no reason;
    a row for a check this build no longer declares is still shown, since it is a fact about what
    was checked on that commit. Only the three outcome words and the stored reason reach the page.
    """
    newest: dict[str, Mapping[str, Any]] = {}
    for row in recorded:
        name = str(row.get("check_name", ""))
        held = newest.get(name)
        if held is None or str(row.get("checked_at", "")) > str(held.get("checked_at", "")):
            newest[name] = row

    def entry(name: str, leaves: Sequence[str], sentence: str) -> dict[str, Any]:
        row = newest.get(name)
        if row is None:
            return {
                "name": name,
                "sentence": sentence,
                "leaves": list(leaves),
                "outcome": NOT_RUN,
                "checked_at": "",
                "reason": "",
            }
        outcome = str(row.get("outcome", ""))
        return {
            "name": name,
            "sentence": sentence,
            "leaves": list(leaves),
            "outcome": outcome if outcome in (PASSED, FAILED) else NOT_RUN,
            "checked_at": str(row.get("checked_at", "")),
            "reason": str(row.get("reason") or "")[:REASON_CHARS],
        }

    listed = [entry(one.name, one.leaves, one.sentence) for one in checks]
    declared = {one.name for one in checks}
    for name in sorted(set(newest) - declared):
        row = newest[name]
        leaves = str(row.get("leaves", "")).split()
        listed.append(entry(name, leaves, "A check this build no longer declares."))
    started = [str(row.get("started_at", "")) for row in recorded]
    return {"commit": serving, "ran_at": max(started, default=""), "checks": listed}
