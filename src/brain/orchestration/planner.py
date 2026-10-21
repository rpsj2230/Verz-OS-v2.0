"""A model proposes the subtasks, and nothing it says is believed until it has been checked.

`brain.orchestration.plan` has said since M18.1.1 how a planner's proposal is read and what it may
not carry, and nothing produced one. This is the step that asks a model for it: the asker's request
and the specialists an administrator allowed the coordinator to call go in, and a list of subtasks
comes back, each naming **who** does it, **what it must return** and **what it waits for**. Then the
reply is treated as what it is, untrusted text from a model, and passes the checks that already
exist before any child can run.

**The reply is read in two halves, and the half that can set a weight is read by the strict one.**
The structure of a subtask (its id and what it depends on) goes through
`brain.orchestration.plan.read_proposal` exactly as written there, so a key that prices the plan
(`cost`, `seconds`, `weight` and the rest), a key nobody declared and a dependency that is not a
list are refused by the check that was written to refuse them. The contract keys (`callee`,
`objective`, `output`, `tool_hints`) are taken off first and read here. The alternative, a schema
that lists every key a subtask may have, would have put the planner's boundary in two places. See
`brain.orchestration.plan.PLANNER_SETS_NO_WEIGHTS`.

**Prose is not a thing a subtask can return, and the model is refused if it asks for it.** An output
field is a name and one of the six kinds `brain.orchestration.contract.FieldKind` has. A kind that
sounds like prose (`text`, `summary`, `paragraph`) is refused in the contract's own words about why
(M18.1.4), and so is any kind that is not one of the six: the vocabulary has no member for it and
the model cannot add one. See `brain.orchestration.contract.PROSE_IS_NOT_A_CONTRACT`.

**The model chooses who and never what they may reach.** A callee it names must be one of those
offered, which are the coordinator's allowed ones, and a callee outside them is refused in the same
sentence an unknown agent gets (`brain.orchestration.coordinator.callee_refusals`). The capabilities
a subtask is allowed are read from the specialist's own ceiling by
`brain.orchestration.coordinator.contract_for`, so there is no key a model could put a capability or
a scope in.

**What leaves for the provider is the asker's words and the names of the specialists.** The prompt
carries the request and, for each allowed specialist, its id and display name: configuration text
an administrator wrote and no company record. It carries no persona, no tool list, no record and no
reach. The disclosure category is `QUESTION`, which is what the words are.

**A refused reply costs a retry at most, and it is never repaired.** A reply that is not JSON, that
holds no list, that names a callee not offered or that draws a cycle is refused whole with the
reasons, and the person is told the plan could not be used. Quietly fixing a model's plan (dropping
the step it got wrong, guessing a kind) is how a run ends up doing something nobody proposed.

Task ids: M18.1.1, M18.1.4, M18.5.3
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from brain.models.driver import DriverMessage, Role
from brain.models.routing import Tier
from brain.orchestration.contract import (
    PROSE_IS_NOT_A_CONTRACT,
    ContractError,
    FieldKind,
    FieldSpec,
)
from brain.orchestration.coordinator import (
    MOST_STEPS,
    Callee,
    CoordinationError,
    PlanStep,
    contract_for,
    not_allowed_sentence,
)
from brain.orchestration.plan import PlanError, read_proposal

# ------------------------------------------------------------------ written-down reasons
#: Why the model is shown the request and the specialists' names and nothing else.
THE_PROMPT_IS_THE_REQUEST_AND_THE_NAMES_OF_THE_SPECIALISTS: Final = (
    "The planner is shown the words the asker typed and, for each specialist the coordinator may "
    "call, its id and display name. No persona, no tool list, no record and no reach: a model "
    "asked to split a request needs to know who could do each part and not what they can see."
)

#: Why a reply that cannot be used is refused whole.
A_PLAN_THAT_IS_WRONG_IS_REFUSED_AND_NEVER_REPAIRED: Final = (
    "A reply that is not JSON, holds no list of subtasks, names a specialist that was not offered "
    "or asks for prose is refused with its reasons, and one that draws a cycle or leaves a "
    "dependency unmeasured is refused by the graph it is weighed as. Dropping the step it got "
    "wrong or guessing what it meant would run something nobody proposed, so the person is told "
    "the plan could not be used and nothing starts."
)

#: The model the planner's call asks for. The main tier: a plan is short and has to be right.
PLANNER_TIER: Final = Tier.MAIN

#: The most the planner's reply may run to, in tokens. Twelve short subtasks fit well inside it.
REPLY_TOKENS: Final = 1_500

#: The longest request a plan is asked for, in characters.
REQUEST_CHARS: Final = 2_000

#: The keys a subtask carries that are about its contract and not its structure.
CONTRACT_KEYS: Final[frozenset[str]] = frozenset({"callee", "objective", "output", "tool_hints"})

#: A subtask's id. Short, plain, and not an identifier anywhere else in the system.
SUBTASK_ID_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

#: Output kinds a model reaches for when it means prose. Named so the refusal can say why, where a
#: kind that is merely unknown gets the plainer sentence.
PROSE_KIND_WORDS: Final[frozenset[str]] = frozenset(
    {
        "answer",
        "description",
        "free_text",
        "html",
        "markdown",
        "narrative",
        "paragraph",
        "prose",
        "report",
        "sentence",
        "str",
        "string",
        "summary",
        "text",
    }
)

#: The most tool hints and the longest objective one subtask may carry.
MOST_TOOL_HINTS: Final = 8
OBJECTIVE_CHARS: Final = 240
HINT_CHARS: Final = 128


class PlanRefusedError(Exception):
    """A reply that cannot be used as a plan, with every reason it could not."""

    def __init__(self, reasons: Sequence[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons: tuple[str, ...] = tuple(reasons)


@dataclass(frozen=True)
class Offered:
    """One specialist the planner may name: its id and the name an administrator gave it."""

    agent_id: str
    display_name: str


# ------------------------------------------------------------------------ the prompt
def system_prompt() -> str:
    """The instruction. No parameters, so it cannot carry anything about an asker or an install."""
    kinds = ", ".join(one.value for one in FieldKind)
    return (
        "You split a request into subtasks for specialist agents. Reply with one JSON object and "
        'nothing else: {"subtasks": [ ... ]}. Each subtask is an object with exactly these keys: '
        '"subtask_id" (a short lowercase word), "callee" (the id of one specialist from the list '
        'you are given), "objective" (one sentence saying what that specialist is to find out), '
        '"output" (a list of {"name", "kind"} for each value it must return), "depends_on" (a '
        "list of subtask_ids whose results it needs first, or an empty list) and, if useful, "
        '"tool_hints" (a list of short tool names). A kind is one of: '
        f"{kinds}. A subtask returns values and never prose. Give a subtask a dependency only if "
        "it cannot start without that result. Do not give any cost, time, size or priority. Use "
        "only specialists from the list."
    )


def planner_messages(ask: str, offered: Sequence[Offered]) -> tuple[DriverMessage, ...]:
    """The two messages of a plan's one call: the instruction, then the request and the specialists.

    See `THE_PROMPT_IS_THE_REQUEST_AND_THE_NAMES_OF_THE_SPECIALISTS`.
    """
    specialists = [{"id": one.agent_id, "name": one.display_name} for one in offered]
    return (
        DriverMessage(role=Role.SYSTEM, content=system_prompt()),
        DriverMessage(
            role=Role.USER,
            content=json.dumps(
                {"request": ask, "specialists": specialists}, sort_keys=True, ensure_ascii=False
            ),
        ),
    )


def checked_request(ask: str) -> str:
    """The request, or a refusal in words when it is blank or too long. Asked before any model."""
    if not ask.strip():
        msg = "say what you would like done, and it will be split between the specialists"
        raise PlanRefusedError((msg,))
    if len(ask) > REQUEST_CHARS:
        msg = f"a request to split is at most {REQUEST_CHARS} characters; shorten it"
        raise PlanRefusedError((msg,))
    return ask


# ------------------------------------------------------------------------ the reply
def _no_constant(name: str) -> Any:
    """Refuse NaN and Infinity, which Python's JSON reader accepts and no JSON writer emits."""
    msg = f"{name} is not a JSON value"
    raise ValueError(msg)


def _unfenced(text: str) -> str:
    """The reply with one surrounding code fence removed, if the model wrapped it in one."""
    stripped = text.strip()
    if not (stripped.startswith("```") and stripped.endswith("```")):
        return stripped
    inner = stripped[3:-3]
    first, newline, rest = inner.partition("\n")
    return rest if newline and not first.strip().startswith("{") else inner


def _output_of(subtask_id: str, raw: object) -> tuple[tuple[FieldSpec, ...], list[str]]:
    """The fields a subtask promises, and every reason one of them could not be read."""
    if not isinstance(raw, list) or not raw:
        return (), [f"subtask {subtask_id!r} lists no values it will return"]
    fields: list[FieldSpec] = []
    problems: list[str] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"name", "kind"}:
            problems.append(
                f"subtask {subtask_id!r} has an output entry that is not a name and kind"
            )
            continue
        name, kind = item["name"], item["kind"]
        if not isinstance(name, str) or not isinstance(kind, str):
            problems.append(f"subtask {subtask_id!r} has an output entry whose parts are not words")
            continue
        if kind.strip().lower() in PROSE_KIND_WORDS:
            problems.append(f"subtask {subtask_id!r} asks for prose. {PROSE_IS_NOT_A_CONTRACT}")
            continue
        try:
            fields.append(FieldSpec(name=name, kind=FieldKind(kind)))
        except ValueError:
            problems.append(
                f"subtask {subtask_id!r} asks for a kind of value that does not exist; the kinds "
                f"are {', '.join(one.value for one in FieldKind)}"
            )
        except ContractError as refused:
            problems.append(str(refused))
    return tuple(fields), problems


def read_plan(text: str, callees: Mapping[str, Callee]) -> tuple[PlanStep, ...]:
    """Read a model's reply into steps, or refuse it whole with every reason (M18.5.3).

    `callees` is the specialists the coordinator was allowed to call and that could be loaded, and a
    subtask naming any other is refused in the one sentence an unknown agent gets. The structure is
    read by `read_proposal`; the contracts are built by `contract_for`, which reads the capabilities
    from the specialist and not from the reply. See
    `A_PLAN_THAT_IS_WRONG_IS_REFUSED_AND_NEVER_REPAIRED`.
    """
    try:
        reply = json.loads(_unfenced(text), parse_constant=_no_constant)
    except ValueError as error:
        raise PlanRefusedError(("the reply is not JSON",)) from error
    if not isinstance(reply, dict) or set(reply) != {"subtasks"}:
        raise PlanRefusedError(('the reply is not an object holding only a list of "subtasks"',))
    items = reply["subtasks"]
    if not isinstance(items, list) or not items:
        raise PlanRefusedError(("the reply holds no subtasks",))
    if len(items) > MOST_STEPS:
        raise PlanRefusedError((f"the reply holds more than {MOST_STEPS} subtasks",))
    if not all(isinstance(one, dict) for one in items):
        raise PlanRefusedError(("a subtask in the reply is not an object",))
    try:
        proposals = read_proposal(
            [{k: v for k, v in one.items() if k not in CONTRACT_KEYS} for one in items]
        )
    except PlanError as refused:
        raise PlanRefusedError((str(refused),)) from refused
    steps: list[PlanStep] = []
    problems: list[str] = []
    for proposal, item in zip(proposals, items, strict=True):
        subtask_id = proposal.subtask_id
        if not SUBTASK_ID_PATTERN.match(subtask_id):
            problems.append("a subtask has an id that is not a short lowercase word")
            continue
        callee_id = item.get("callee")
        callee = callees.get(callee_id) if isinstance(callee_id, str) else None
        if callee is None or not isinstance(callee_id, str):
            problems.append(not_allowed_sentence(subtask_id))
            continue
        objective = item.get("objective")
        if not isinstance(objective, str) or len(objective) > OBJECTIVE_CHARS:
            problems.append(f"subtask {subtask_id!r} has no objective, or one that is too long")
            continue
        hints = item.get("tool_hints", [])
        if (
            not isinstance(hints, list)
            or len(hints) > MOST_TOOL_HINTS
            or not all(isinstance(one, str) and 0 < len(one) <= HINT_CHARS for one in hints)
        ):
            problems.append(
                f"subtask {subtask_id!r} has tool hints that are not a short list of names"
            )
            continue
        output, wrong = _output_of(subtask_id, item.get("output"))
        problems.extend(wrong)
        if wrong:
            continue
        try:
            steps.append(
                PlanStep(
                    subtask_id=subtask_id,
                    callee_id=callee_id,
                    contract=contract_for(
                        callee,
                        subtask_id=subtask_id,
                        objective=objective,
                        output=output,
                        tool_hints=hints,
                    ),
                    depends_on=proposal.depends_on,
                )
            )
        except (ContractError, CoordinationError) as refused:
            problems.append(str(refused))
    if problems:
        raise PlanRefusedError(problems)
    return tuple(steps)
